# Ví dụ yêu cầu và phản hồi trong DSL API và dữ liệu

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vai trò của ví dụ request và response trong thiết kế, mô tả và kiểm thử API DSL.
- Đọc một API contract và xác định endpoint, method, input, output, status code và schema.
- Viết ví dụ request/response có cấu trúc JSON rõ ràng, nhất quán và có thể tái sử dụng.
- Mô tả các thao tác tạo, đọc, cập nhật và xóa dữ liệu bằng ví dụ cụ thể.
- Phân biệt request hợp lệ, request sai cú pháp, request sai kiểu và request vi phạm quy tắc nghiệp vụ.
- Thiết kế response thành công, response lỗi, response rỗng và response một phần.
- Biểu diễn filter, sort, pagination, authentication và concurrency control trong ví dụ API.
- Mô tả idempotency, thao tác bất đồng bộ, batch request và streaming response.
- Giữ ví dụ đồng bộ với schema, phiên bản API và hành vi thực tế của server.
- Dùng ví dụ làm cơ sở cho documentation, contract testing, mock server và client generation.

## 1. Ví dụ yêu cầu và phản hồi là gì?

Trong một API, request (yêu cầu) là thông điệp client gửi đến server để yêu cầu thực hiện một thao tác hoặc lấy dữ liệu. Response (phản hồi) là thông điệp server gửi lại để mô tả kết quả xử lý, dữ liệu được trả về hoặc lỗi đã xảy ra.

Một API DSL có thể mô tả các operation, kiểu dữ liệu, tham số, ràng buộc và cấu trúc kết quả. Ví dụ request và response biến phần mô tả đó thành tình huống cụ thể mà người tích hợp có thể đọc, thử nghiệm và đối chiếu.

Một ví dụ đơn giản:

**Request**

~~~http
GET /api/v1/customers/CUS-1042
Accept: application/json
Authorization: Bearer <access-token>
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "CUS-1042",
  "name": "Nguyen An",
  "email": "an@example.com",
  "active": true
}
~~~

Request cho biết client muốn đọc khách hàng có ID CUS-1042. Response cho biết server đã tìm thấy tài nguyên và trả về một biểu diễn JSON.

Ví dụ không chỉ là phần minh họa trang trí. Chúng giúp làm rõ những chi tiết thường bị bỏ sót trong mô tả trừu tượng, chẳng hạn tên field, kiểu dữ liệu, giá trị mặc định, status code, format ngày giờ và cách biểu diễn lỗi.

## 2. Vì sao API DSL cần ví dụ cụ thể?

API contract có thể mô tả chính xác schema nhưng vẫn khó hiểu nếu người đọc không thấy dữ liệu thực tế. Ví dụ request/response giúp nhiều nhóm làm việc trên cùng một hợp đồng.

- **Người tích hợp:** biết cần gửi header, query parameter và body nào.
- **Người phát triển server:** hiểu dữ liệu đầu vào và đầu ra mà implementation phải tuân thủ.
- **Người phát triển client:** biết cách parse response và xử lý lỗi.
- **Người kiểm thử:** có dữ liệu đầu vào và kết quả mong đợi.
- **Người vận hành:** hiểu status code, correlation ID và thông tin lỗi.
- **Người thiết kế DSL:** kiểm tra xem cú pháp khai báo có diễn đạt được tình huống thực tế hay không.

Ví dụ cũng giúp phát hiện mâu thuẫn. Nếu schema khai báo quantity là integer nhưng response mẫu chứa chuỗi "five", contract và ví dụ không nhất quán. Nếu operation được mô tả trả 201 Created nhưng ví dụ lại trả 200 OK mà không giải thích, người tích hợp không biết hành vi nào là chuẩn.

### 2.1. Ví dụ phải phản ánh hành vi được cam kết

Ví dụ nên thể hiện dữ liệu và hành vi mà API thực sự hỗ trợ. Không nên đưa một field chỉ có trong ví dụ nhưng không có trong schema, hoặc mô tả một lỗi mà server không bao giờ trả theo contract.

### 2.2. Ví dụ không thay thế schema

Schema mô tả tập giá trị hợp lệ và các ràng buộc tổng quát. Ví dụ chỉ thể hiện một hoặc một số trường hợp cụ thể. Một ví dụ hợp lệ không chứng minh mọi trường hợp khác đều hợp lệ.

### 2.3. Ví dụ là một phần của hợp đồng giao tiếp

Khi ví dụ được dùng trong tài liệu chính thức, người dùng thường xem nó như cách API vận hành. Vì vậy, ví dụ cần được quản lý cùng phiên bản API và được kiểm tra khi contract thay đổi.

## 3. Thành phần của một request

Một HTTP request thường gồm method, URL, headers và có thể có body.

~~~http
POST /api/v1/orders?notifyCustomer=true HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>
Idempotency-Key: 8d6f0c20-2d65-4a62-8a0f-82ac7f9d6a15

{
  "customerId": "CUS-1042",
  "items": [
    {
      "productId": "PRD-100",
      "quantity": 2
    }
  ],
  "shippingAddressId": "ADDR-08"
}
~~~

### 3.1. Method

Method thể hiện ý định của client. Các method thường gặp:

| Method | Mục đích thường dùng | Ví dụ |
|---|---|---|
| GET | Đọc tài nguyên | Lấy thông tin khách hàng |
| POST | Tạo tài nguyên hoặc thực hiện action | Tạo đơn hàng |
| PUT | Thay thế toàn bộ biểu diễn tài nguyên | Cập nhật toàn bộ hồ sơ |
| PATCH | Cập nhật một phần tài nguyên | Đổi email |
| DELETE | Xóa hoặc yêu cầu xóa tài nguyên | Xóa địa chỉ |

Semantics chính xác cần được định nghĩa trong API. Không nên chọn method chỉ dựa vào tên endpoint.

### 3.2. Path parameter

Path parameter xác định tài nguyên hoặc phạm vi:

~~~http
GET /api/v1/orders/ORD-2048
~~~

Trong ví dụ này, ORD-2048 là order ID. Path parameter thường là thành phần bắt buộc của route.

### 3.3. Query parameter

Query parameter thường dùng để lọc, sắp xếp, phân trang hoặc điều chỉnh cách trả kết quả:

~~~http
GET /api/v1/orders?status=PAID&limit=20&offset=40
~~~

Cần mô tả kiểu, giá trị mặc định, giới hạn và hành vi khi parameter lặp hoặc không hợp lệ.

### 3.4. Header

Header mang metadata về nội dung, xác thực, cache, tracing hoặc điều kiện cập nhật:

~~~http
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>
If-Match: "version-7"
X-Correlation-ID: corr-91a2
~~~

Header không nên bị dùng thay cho dữ liệu nghiệp vụ thông thường nếu dữ liệu đó thuộc resource representation.

### 3.5. Request body

Body chứa dữ liệu được gửi đến server. API cần chỉ rõ media type được chấp nhận, schema của body, field bắt buộc và tùy chọn, giới hạn kích thước, quy tắc encoding và hành vi khi body rỗng hoặc thiếu.

### 3.6. Request không có body

GET và DELETE thường không cần body. Một API có thể định nghĩa body cho các method này nhưng cần cân nhắc khả năng tương thích giữa proxy, client và công cụ trung gian. Những bộ lọc phức tạp đôi khi phù hợp hơn với endpoint truy vấn chuyên biệt.

## 4. Thành phần của một response

Một HTTP response thường gồm status code, headers và body nếu có.

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/orders/ORD-2048
ETag: "order-v1"

{
  "id": "ORD-2048",
  "status": "PENDING",
  "createdAt": "2026-11-15T10:30:00Z"
}
~~~

### 4.1. Status code

Status code cho biết kết quả ở mức giao thức:

| Mã | Ý nghĩa thường dùng |
|---|---|
| 200 OK | Request thành công, có thể kèm dữ liệu |
| 201 Created | Tài nguyên mới đã được tạo |
| 202 Accepted | Đã nhận yêu cầu xử lý bất đồng bộ |
| 204 No Content | Thành công nhưng không có body |
| 400 Bad Request | Request sai định dạng hoặc không hợp lệ ở mức request |
| 401 Unauthorized | Thiếu hoặc không hợp lệ thông tin xác thực |
| 403 Forbidden | Đã xác thực nhưng không có quyền |
| 404 Not Found | Không tìm thấy tài nguyên hoặc route |
| 409 Conflict | Xung đột với trạng thái hiện tại |
| 412 Precondition Failed | Điều kiện request như If-Match không thỏa |
| 422 Unprocessable Content | Nội dung đọc được nhưng không đáp ứng quy tắc xử lý |
| 429 Too Many Requests | Vượt giới hạn tốc độ |
| 500 Internal Server Error | Lỗi nội bộ không dự kiến |
| 503 Service Unavailable | Dịch vụ tạm thời không sẵn sàng |

Mã cụ thể cần theo semantics operation. Không nên trả 200 cho mọi tình huống chỉ vì server đã nhận được request.

### 4.2. Response headers

Một số header hữu ích:
- Content-Type: kiểu dữ liệu response.
- Location: URI của tài nguyên mới.
- ETag: phiên bản hoặc fingerprint biểu diễn tài nguyên.
- Cache-Control: chính sách cache.
- Retry-After: thời gian client nên chờ trước khi thử lại.
- X-Correlation-ID: định danh liên kết request và log.

### 4.3. Response body

Body có thể chứa resource, collection, metadata, error object hoặc trạng thái công việc. API cần phân biệt field luôn có, field có thể null và field có thể vắng mặt.

### 4.4. Response không có body

204 No Content không nên kèm JSON body. Nếu client cần biết tài nguyên sau khi cập nhật, API có thể trả 200 cùng representation hoặc cung cấp endpoint GET để đọc lại.

## 5. Khai báo request và response trong API DSL

Một DSL API có thể biểu diễn operation, route, request schema và response schema theo cách khai báo.

Ví dụ giả định:

~~~text
api CustomerApi {
    basePath = "/api/v1"

    operation getCustomer {
        method = GET
        path = "/customers/{customerId}"

        pathParameter customerId: CustomerId required

        response 200: Customer
        response 404: ApiError
    }
}
~~~

Một operation đầy đủ có thể khai báo tên định danh, method và path, path/query/header parameter, request body, response theo status code, security requirement và media type.

### 5.1. Schema riêng cho request và response

Không phải lúc nào kiểu dữ liệu dùng khi ghi cũng giống kiểu dữ liệu dùng khi đọc.

~~~text
type CreateCustomerRequest {
    name: String required
    email: EmailAddress required
    password: Secret required
}

type CustomerResponse {
    id: CustomerId
    name: String
    email: EmailAddress
    createdAt: Instant
}
~~~

Request tạo customer có thể nhận password hoặc invitation code, nhưng response không bao giờ trả password. Tách request và response giúp kiểm soát field nào client được phép gửi và field nào server được phép tiết lộ.

### 5.2. Read-only và write-only field

Một schema có thể đánh dấu:
- Read-only: server tạo hoặc quản lý, client không được gửi khi tạo/cập nhật.
- Write-only: client có thể gửi nhưng server không trả lại, ví dụ mật khẩu.
- Immutable: chỉ được đặt khi tạo, không thay đổi qua update thông thường.

### 5.3. Schema composition

Có thể tái sử dụng kiểu chung:

~~~text
type Address {
    line1: String required
    city: String required
    postalCode: String
    countryCode: String required
}

type CustomerResponse {
    id: CustomerId
    name: String
    address: Address
}
~~~

Composition giúp các operation dùng cùng một định nghĩa địa chỉ thay vì sao chép schema.

## 6. Ví dụ tạo tài nguyên (Create)

Tạo tài nguyên thường dùng POST tới collection endpoint.

**Request**

~~~http
POST /api/v1/customers HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "name": "Nguyen An",
  "email": "an@example.com",
  "phone": "+84901234567"
}
~~~

**Response**

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/customers/CUS-1042

{
  "id": "CUS-1042",
  "name": "Nguyen An",
  "email": "an@example.com",
  "phone": "+84901234567",
  "active": true,
  "createdAt": "2026-11-15T10:30:00Z"
}
~~~

### 6.1. Client không tự cấp ID nếu server quản lý ID

Nếu ID được server sinh, request không nên yêu cầu client gửi ID. Response trả ID đã cấp để client dùng trong các request sau.

### 6.2. Giá trị mặc định

Ví dụ response có active = true dù request không gửi active. Đây là default do server áp dụng. Contract cần nói rõ giá trị mặc định và thời điểm áp dụng.

### 6.3. Server-generated field

createdAt, updatedAt, version hoặc audit metadata thường do server quản lý. Client không nên có quyền giả mạo các field này qua request thông thường.

### 6.4. Tạo tài nguyên có quan hệ

Nếu request gửi customerId hoặc addressId, API cần xác định server kiểm tra tài nguyên tham chiếu có tồn tại và client có quyền sử dụng hay không.

## 7. Ví dụ đọc tài nguyên (Read)

Đọc một tài nguyên thường dùng GET với ID.

**Request**

~~~http
GET /api/v1/customers/CUS-1042 HTTP/1.1
Accept: application/json
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "customer-v3"

{
  "id": "CUS-1042",
  "name": "Nguyen An",
  "email": "an@example.com",
  "phone": "+84901234567",
  "active": true,
  "createdAt": "2026-11-15T10:30:00Z",
  "updatedAt": "2026-11-15T11:00:00Z"
}
~~~

### 7.1. Không tìm thấy

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/not-found",
  "title": "Customer not found",
  "status": 404,
  "detail": "No customer exists with the supplied identifier.",
  "instance": "/api/v1/customers/CUS-9999"
}
~~~

### 7.2. Tài nguyên bị ẩn bởi chính sách truy cập

Một hệ thống có thể trả 404 thay vì 403 để không tiết lộ sự tồn tại của tài nguyên. Đây là quyết định bảo mật cần được áp dụng nhất quán.

### 7.3. Đọc collection

~~~http
GET /api/v1/customers?active=true&limit=2 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [
    {
      "id": "CUS-1042",
      "name": "Nguyen An",
      "active": true
    },
    {
      "id": "CUS-1050",
      "name": "Tran Binh",
      "active": true
    }
  ],
  "page": {
    "limit": 2,
    "nextCursor": "eyJpZCI6IkNVUy0xMDUwIn0"
  }
}
~~~

Collection response thường cần metadata phân trang thay vì chỉ trả một mảng không có thông tin tiếp tục.

## 8. Ví dụ cập nhật toàn bộ và một phần (PUT/PATCH)

PUT thường biểu diễn thay thế toàn bộ tài nguyên theo semantics của API. PATCH biểu diễn thay đổi một phần.

### 8.1. PUT

**Request**

~~~http
PUT /api/v1/customers/CUS-1042 HTTP/1.1
Content-Type: application/json
If-Match: "customer-v3"

{
  "name": "Nguyen An",
  "email": "an.new@example.com",
  "phone": "+84909998877",
  "active": true
}
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "customer-v4"

{
  "id": "CUS-1042",
  "name": "Nguyen An",
  "email": "an.new@example.com",
  "phone": "+84909998877",
  "active": true,
  "updatedAt": "2026-11-15T11:15:00Z"
}
~~~

Với PUT, cần nói rõ field bị bỏ khỏi representation có được xóa, đặt mặc định hay giữ nguyên. Semantics thay thế toàn bộ thường yêu cầu client gửi đầy đủ các field được quản lý trong representation.

### 8.2. PATCH

**Request**

~~~http
PATCH /api/v1/customers/CUS-1042 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "customer-v3"

{
  "phone": "+84909998877"
}
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "customer-v4"

{
  "id": "CUS-1042",
  "name": "Nguyen An",
  "email": "an@example.com",
  "phone": "+84909998877",
  "active": true
}
~~~

### 8.3. Phân biệt bỏ qua field và đặt null

Trong một số định dạng PATCH:
- Field không xuất hiện nghĩa là không thay đổi.
- Field có giá trị null nghĩa là xóa hoặc đặt null.

Quy tắc phụ thuộc patch format. Ví dụ JSON Merge Patch và JSON Patch có semantics khác nhau, vì vậy API cần chỉ rõ media type.

### 8.4. PATCH nhiều thao tác

Một API có thể hỗ trợ JSON Patch:

~~~json
[
  {
    "op": "replace",
    "path": "/phone",
    "value": "+84909998877"
  },
  {
    "op": "remove",
    "path": "/nickname"
  }
]
~~~

Nếu dùng định dạng này, cần xác định các operation được hỗ trợ và hành vi khi một thao tác trong danh sách thất bại. Có API áp dụng toàn bộ patch theo transaction, có API định nghĩa semantics khác.

## 9. Ví dụ xóa tài nguyên (DELETE)

**Request**

~~~http
DELETE /api/v1/customers/CUS-1042 HTTP/1.1
If-Match: "customer-v4"
~~~

**Response**

~~~http
HTTP/1.1 204 No Content
~~~

Một API khác có thể trả 200 cùng trạng thái xóa hoặc 202 nếu xóa cần xử lý bất đồng bộ.

### 9.1. Xóa mềm

Nếu tài nguyên chỉ được đánh dấu deleted thay vì xóa vật lý, API cần mô tả semantics. Client có thể nhận 204 nhưng tài nguyên vẫn còn trong hệ thống để audit hoặc phục hồi.

### 9.2. Xóa lặp lại

Nếu client gửi DELETE lần thứ hai, API có thể trả 404, 204 hoặc một response khác theo contract. Tính idempotent của DELETE nói về trạng thái cuối cùng, không bắt buộc mọi response phải giống nhau.

### 9.3. Ràng buộc tham chiếu

Nếu tài nguyên còn được tham chiếu, server có thể từ chối với 409 Conflict, xóa theo cascade nếu được quy định, chuyển trạng thái inactive hoặc yêu cầu xóa các tài nguyên con trước.

Ví dụ lỗi:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/resource-in-use",
  "title": "Customer is still referenced",
  "status": 409,
  "detail": "The customer has active orders and cannot be deleted."
}
~~~

## 10. Request validation và response lỗi

Một request có thể thất bại ở nhiều lớp khác nhau. Ví dụ tốt cần cho thấy lỗi nào được trả và cấu trúc lỗi ra sao.

### 10.1. Lỗi cú pháp JSON

~~~http
POST /api/v1/customers HTTP/1.1
Content-Type: application/json

{
  "name": "Nguyen An",
  "email":
~~~

Response có thể là 400 Bad Request vì body không parse được.

### 10.2. Thiếu field bắt buộc

Request:

~~~json
{
  "name": "Nguyen An"
}
~~~

Response:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 422,
  "errors": [
    {
      "field": "email",
      "code": "required",
      "message": "Email is required."
    }
  ]
}
~~~

### 10.3. Sai kiểu dữ liệu

Request:

~~~json
{
  "name": "Nguyen An",
  "age": "twenty"
}
~~~

Nếu age được khai báo là integer, server có thể trả lỗi chỉ rõ field và kiểu mong đợi.

### 10.4. Vi phạm constraint

Ví dụ email không đúng format, quantity nhỏ hơn 1 hoặc chuỗi vượt giới hạn độ dài. Các constraint cần được mô tả trong schema và phản ánh trong response lỗi.

### 10.5. Lỗi nghiệp vụ

Request có thể đúng schema nhưng không hợp lệ theo trạng thái nghiệp vụ. Ví dụ không thể hủy đơn đã giao. API có thể trả 409 Conflict hoặc 422 tùy semantics đã định.

### 10.6. Một format lỗi nhất quán

Problem Details là một cách phổ biến để biểu diễn lỗi HTTP:

~~~json
{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Order cannot be submitted",
  "status": 409,
  "detail": "The order is already in a terminal state.",
  "instance": "/api/v1/orders/ORD-2048",
  "code": "ORDER_ALREADY_FINAL"
}
~~~

API có thể bổ sung field như code, errors, traceId hoặc invalidParams. Cần giữ các field chuẩn và định nghĩa extension rõ ràng.

## 11. Ví dụ theo từng lớp lỗi

Một bộ ví dụ hoàn chỉnh nên có nhiều trường hợp, không chỉ một response thành công.

| Tình huống | Status minh họa | Điều cần giải thích |
|---|---:|---|
| JSON không parse được | 400 | Vị trí hoặc nguyên nhân cú pháp |
| Thiếu token | 401 | Cách xác thực lại |
| Không đủ quyền | 403 | Quyền cần thiết |
| Không tìm thấy resource | 404 | Resource hoặc route không tồn tại |
| Trùng dữ liệu | 409 | Conflict và cách giải quyết |
| Version cũ | 412 | Cách đọc lại và retry an toàn |
| Sai constraint | 422 | Field, code và message |
| Quá nhiều request | 429 | Retry-After hoặc rate limit metadata |
| Lỗi server | 500 | Correlation ID, không lộ stack trace |
| Dịch vụ tạm ngừng | 503 | Retry policy và Retry-After |

Không nên trả thông tin nội bộ như stack trace, câu SQL, secret hoặc tên máy chủ trong response production. Người dùng cần đủ thông tin để sửa request hoặc liên hệ hỗ trợ, còn chi tiết nội bộ thuộc log bảo mật.

## 12. Ví dụ filter, sort và pagination

API collection thường cần query parameter để chọn tập dữ liệu.

**Request**

~~~http
GET /api/v1/orders?status=PAID&createdAfter=2026-11-01T00%3A00%3A00Z&sort=-createdAt,id&limit=20&cursor=eyJpZCI6Ik9SRC0xMDAifQ HTTP/1.1
Accept: application/json
~~~

**Response**

~~~json
{
  "items": [
    {
      "id": "ORD-2048",
      "status": "PAID",
      "total": 1250000,
      "createdAt": "2026-11-15T10:30:00Z"
    }
  ],
  "page": {
    "limit": 20,
    "nextCursor": "eyJpZCI6Ik9SRC0tMTAwIn0",
    "hasMore": true
  }
}
~~~

### 12.1. Filter

Filter cần định nghĩa field nào được phép lọc, toán tử được hỗ trợ và cách mã hóa giá trị. Không nên cho phép client tự truyền tên field hoặc biểu thức tùy ý nếu server không có whitelist.

### 12.2. Sort

Sort cần quy định field được phép sort, hướng tăng hoặc giảm, thứ tự mặc định, tie-breaker để kết quả ổn định và hành vi với null.

### 12.3. Offset pagination

~~~http
GET /api/v1/orders?limit=20&offset=40
~~~

Offset dễ hiểu nhưng có thể chậm khi offset lớn và dễ thay đổi kết quả giữa các trang khi dữ liệu mới được thêm.

### 12.4. Cursor pagination

Cursor thường dựa trên giá trị của bản ghi cuối cùng ở trang trước. Nó có thể ổn định hơn với dữ liệu lớn nếu sort key phù hợp và có index.

### 12.5. Metadata trang

Response nên nói rõ limit hiện tại, cursor tiếp theo, có còn trang sau không và tổng số phần tử nếu API hỗ trợ và việc đếm có hợp lý về chi phí.

Không phải API nào cũng cần totalCount. Với dữ liệu lớn, count chính xác có thể tốn kém.

## 13. Ví dụ authentication và authorization

Authentication xác định client hoặc người dùng là ai. Authorization xác định họ được phép thực hiện thao tác nào.

**Request**

~~~http
GET /api/v1/orders/ORD-2048 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

**Response khi thiếu hoặc token không hợp lệ**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/authentication",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid access token is required."
}
~~~

**Response khi không có quyền**

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/forbidden",
  "title": "Access denied",
  "status": 403,
  "detail": "The caller cannot view this order."
}
~~~

### 13.1. Không gửi secret trong body response

Access token, password, API key và secret không nên được phản hồi trong representation thông thường.

### 13.2. Scope và role

API DSL có thể khai báo security requirement theo operation:

~~~text
operation refundOrder {
    method = POST
    path = "/orders/{orderId}/refund"
    requires = [orders:write, refunds:create]
}
~~~

Ví dụ request/response nên làm rõ operation cần quyền nào nếu người tích hợp cần biết.

### 13.3. Multi-tenant

Nếu API phục vụ nhiều tenant, server phải xác định tenant từ context đáng tin cậy. Không nên chỉ tin tenantId trong body mà không kiểm tra quyền.

## 14. Ví dụ optimistic concurrency với ETag

Hai client có thể cùng đọc và cập nhật một tài nguyên. Nếu không kiểm soát version, cập nhật sau có thể ghi đè thay đổi của cập nhật trước.

### 14.1. Đọc version

~~~http
GET /api/v1/orders/ORD-2048 HTTP/1.1
~~~

~~~http
HTTP/1.1 200 OK
ETag: "order-v7"
Content-Type: application/json

{
  "id": "ORD-2048",
  "status": "PENDING",
  "note": "Call customer"
}
~~~

### 14.2. Cập nhật có điều kiện

~~~http
PATCH /api/v1/orders/ORD-2048 HTTP/1.1
If-Match: "order-v7"
Content-Type: application/merge-patch+json

{
  "note": "Customer confirmed"
}
~~~

Nếu tài nguyên vẫn ở version 7, server cập nhật và trả ETag mới.

### 14.3. Conflict version

Nếu một client khác đã cập nhật lên version 8, server có thể trả:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/version-conflict",
  "title": "Resource has changed",
  "status": 412,
  "detail": "Reload the resource and apply the update again."
}
~~~

Client cần đọc lại dữ liệu và quyết định merge hoặc yêu cầu người dùng giải quyết. Không nên tự retry vô hạn với cùng ETag cũ.

## 15. Idempotency và retry request

Idempotency mô tả việc gửi lại cùng một yêu cầu có tạo thêm tác dụng phụ hay không. Đây là vấn đề quan trọng với thao tác tạo đơn, thanh toán hoặc gửi lệnh.

### 15.1. Idempotency key

~~~http
POST /api/v1/payments HTTP/1.1
Idempotency-Key: pay-ORD-2048-attempt-1
Content-Type: application/json

{
  "orderId": "ORD-2048",
  "amount": 1250000,
  "currency": "VND"
}
~~~

Nếu client không nhận được response do timeout, nó có thể gửi lại cùng key. Server nhận diện đây là cùng một thao tác logic và trả kết quả đã lưu nếu contract hỗ trợ.

### 15.2. Phạm vi key

Cần quy định key duy nhất theo client hay theo account, thời gian lưu key, hai request cùng key nhưng body khác nhau được xử lý thế nào, response cũ được phát lại trong bao lâu và key có được tái sử dụng sau expiration không.

### 15.3. Không phải mọi request đều cần key

GET thường không cần idempotency key. POST tạo tài nguyên hoặc thực hiện action có tác dụng phụ có thể cần. Quyết định phụ thuộc semantics operation.

### 15.4. Ví dụ response phát lại

~~~http
HTTP/1.1 201 Created
Idempotency-Replayed: true
Content-Type: application/json

{
  "paymentId": "PAY-9001",
  "status": "AUTHORIZED"
}
~~~

Header replay chỉ là ví dụ; API cần định nghĩa cách nhận biết response được phát lại nếu client cần phân biệt.

## 16. Request và response bất đồng bộ

Một thao tác có thể mất nhiều thời gian hơn giới hạn kết nối HTTP. API có thể nhận yêu cầu, tạo job và trả về trạng thái xử lý.

**Request**

~~~http
POST /api/v1/reports HTTP/1.1
Content-Type: application/json

{
  "reportType": "MONTHLY_SALES",
  "month": "2026-10",
  "format": "CSV"
}
~~~

**Response**

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/v1/jobs/JOB-7201
Retry-After: 3

{
  "jobId": "JOB-7201",
  "status": "QUEUED",
  "statusUrl": "/api/v1/jobs/JOB-7201"
}
~~~

Client kiểm tra trạng thái:

~~~http
GET /api/v1/jobs/JOB-7201 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "jobId": "JOB-7201",
  "status": "SUCCEEDED",
  "progress": 100,
  "resultUrl": "/api/v1/reports/RPT-2026-10"
}
~~~

### 16.1. Trạng thái job

Một lifecycle có thể gồm QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED và EXPIRED. Chuyển trạng thái cần được định nghĩa. Ví dụ, job đã SUCCEEDED không nên chuyển lại RUNNING nếu không tạo job mới hoặc có một thao tác retry riêng.

### 16.2. Lấy kết quả

Result URL có thể trả file, metadata hoặc một tài nguyên report. Cần định nghĩa thời hạn lưu kết quả và quyền truy cập.

### 16.3. Hủy job

API có thể cung cấp:

~~~http
DELETE /api/v1/jobs/JOB-7201
~~~

Response có thể là 202 nếu yêu cầu hủy được tiếp nhận nhưng tác vụ chưa dừng hoàn toàn.

## 17. Batch request và response

Batch API cho phép gửi nhiều thao tác trong một request để giảm số lần round trip.

**Request**

~~~http
POST /api/v1/batch HTTP/1.1
Content-Type: application/json

{
  "operations": [
    {
      "id": "op-1",
      "method": "GET",
      "path": "/customers/CUS-1042"
    },
    {
      "id": "op-2",
      "method": "GET",
      "path": "/orders/ORD-2048"
    },
    {
      "id": "op-3",
      "method": "POST",
      "path": "/notifications",
      "body": {
        "customerId": "CUS-1042",
        "template": "ORDER_UPDATE"
      }
    }
  ]
}
~~~

**Response**

~~~json
{
  "results": [
    {
      "id": "op-1",
      "status": 200,
      "body": {
        "id": "CUS-1042",
        "name": "Nguyen An"
      }
    },
    {
      "id": "op-2",
      "status": 404,
      "error": {
        "code": "ORDER_NOT_FOUND",
        "message": "Order was not found."
      }
    },
    {
      "id": "op-3",
      "status": 202,
      "body": {
        "notificationId": "NTF-301",
        "status": "QUEUED"
      }
    }
  ]
}
~~~

### 17.1. Batch không nhất thiết là transaction

Một batch có thể thực hiện từng operation độc lập. Nếu operation thứ hai lỗi, operation thứ nhất có thể vẫn thành công. Không nên giả định toàn bộ batch được rollback trừ khi API cam kết atomic batch.

### 17.2. Liên kết kết quả

Mỗi operation cần ID để client ghép response với request tương ứng. Không nên chỉ dựa vào thứ tự mảng nếu server có thể xử lý hoặc trả kết quả không theo thứ tự.

### 17.3. Giới hạn batch

Cần giới hạn số operation, tổng body size, thời gian xử lý và độ sâu lồng nhau để tránh request quá lớn.

### 17.4. Phụ thuộc giữa operation

Một số batch API cho phép operation sau tham chiếu kết quả operation trước. Khi đó, cần quy định thứ tự thực thi và cách xử lý nếu operation nguồn thất bại.

## 18. Streaming request và response

Với dữ liệu lớn hoặc sự kiện liên tục, response có thể được stream thay vì chờ toàn bộ kết quả.

### 18.1. NDJSON

Mỗi dòng là một JSON object:

~~~http
GET /api/v1/events/stream HTTP/1.1
Accept: application/x-ndjson
~~~

Response minh họa:

~~~text
{"id":"EVT-1","type":"ORDER_CREATED"}
{"id":"EVT-2","type":"PAYMENT_AUTHORIZED"}
{"id":"EVT-3","type":"ORDER_SHIPPED"}
~~~

### 18.2. Server-Sent Events

SSE gửi event theo định dạng text/event-stream:

~~~text
event: progress
data: {"jobId":"JOB-7201","percent":25}

event: progress
data: {"jobId":"JOB-7201","percent":60}

event: completed
data: {"jobId":"JOB-7201","resultUrl":"/reports/RPT-2026-10"}
~~~

### 18.3. Streaming semantics

Cần định nghĩa khi nào stream bắt đầu, kiểu từng message, heartbeat, cách báo lỗi sau khi headers đã được gửi, cách client reconnect, event ID và resume cursor, backpressure và giới hạn buffer.

### 18.4. Lỗi giữa stream

Sau khi response headers đã gửi, server có thể không còn đổi status code. Lỗi có thể được biểu diễn thành một event hoặc message cuối. Client phải biết cách phân biệt kết thúc bình thường với stream bị ngắt.

## 19. Content negotiation và serialization

API có thể hỗ trợ nhiều định dạng representation.

### 19.1. Content-Type

Content-Type mô tả định dạng body được gửi:

~~~http
Content-Type: application/json
~~~

### 19.2. Accept

Accept mô tả định dạng client muốn nhận:

~~~http
Accept: application/json
~~~

Nếu server không hỗ trợ định dạng yêu cầu, nó có thể trả 406 Not Acceptable. Nếu request body dùng media type không được hỗ trợ, có thể trả 415 Unsupported Media Type.

### 19.3. JSON serialization

Cần quy định tên field dùng camelCase hay snake_case, cách biểu diễn enum, decimal, ngày giờ, null và field vắng mặt, Unicode escaping và số lớn vượt giới hạn chính xác của một số runtime.

### 19.4. Decimal và tiền tệ

Số tiền có thể được biểu diễn dưới dạng number hoặc string decimal. Chọn dạng nào cần xét độ chính xác của client và contract. Nếu dùng number trong JSON, cần quy định precision và cách làm tròn.

### 19.5. Date và time

Một timestamp có timezone có thể được biểu diễn:

~~~json
{
  "createdAt": "2026-11-15T10:30:00Z"
}
~~~

Ngày lịch không có thời gian có thể là:

~~~json
{
  "birthDate": "1995-04-21"
}
~~~

Không nên trộn date-only với timestamp hoặc bỏ timezone một cách mơ hồ.

### 19.6. Enum và unknown value

Khi server thêm enum value mới, client cũ có thể không nhận diện. Contract nên nói client có cần chấp nhận unknown enum, dùng fallback hay báo lỗi.

## 20. Null, field vắng mặt và giá trị mặc định

Ba trạng thái này có thể mang ý nghĩa khác nhau:

- Field vắng mặt: server không gửi field hoặc client không yêu cầu thay đổi field.
- Field có null: giá trị được xác định là không có.
- Field có giá trị mặc định: server hoặc schema gán một giá trị khi không có input.

Ví dụ response:

~~~json
{
  "id": "CUS-1042",
  "middleName": null,
  "nickname": "An"
}
~~~

Nếu field nickname bị bỏ hoàn toàn, client không nên tự giả định nó là null trừ khi contract quy định như vậy.

### 20.1. PATCH và field vắng mặt

Trong PATCH, field bị bỏ qua thường có nghĩa không thay đổi. Gửi null có thể có nghĩa xóa giá trị. Cần thể hiện điều này bằng ví dụ riêng.

### 20.2. Default value

Schema có thể quy định default cho một field khi tạo. Response nên thể hiện giá trị thực đã được lưu, không chỉ lặp lại body request.

### 20.3. Optional và nullable không giống nhau

Optional nói field có thể không xuất hiện. Nullable nói field có thể mang giá trị null. Một field có thể optional nhưng không nullable, hoặc required nhưng nullable.

## 21. Response collection rỗng và partial response

### 21.1. Collection rỗng

Nếu không có tài nguyên phù hợp, API collection thường trả 200 cùng danh sách rỗng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [],
  "page": {
    "limit": 20,
    "hasMore": false
  }
}
~~~

Không tìm thấy một collection rỗng khác với GET một tài nguyên cụ thể không tồn tại, thường trả 404.

### 21.2. Partial response

Một API có thể hỗ trợ field selection:

~~~http
GET /api/v1/customers/CUS-1042?fields=id,name,email
~~~

Response chỉ gồm field được yêu cầu. Contract cần quy định field bắt buộc nào luôn được trả và client có thể yêu cầu field không được phép hay không.

### 21.3. Partial success

Một batch hoặc operation tổng hợp có thể có kết quả một phần. Response cần chỉ rõ phần nào thành công, phần nào thất bại và có thể retry phần nào.

### 21.4. Không dùng null để che giấu lỗi

Nếu server không lấy được một field vì lỗi downstream, trả null có thể làm client tưởng giá trị thực sự rỗng. Nên định nghĩa partial error hoặc trạng thái field nếu API hỗ trợ.

## 22. Versioning và backward compatibility

API contract thay đổi theo thời gian. Ví dụ cần được gắn với version phù hợp.

### 22.1. Version trong path

~~~http
GET /api/v1/customers/CUS-1042
~~~

Đây là cách dễ nhìn thấy và thường dễ quản lý tài liệu.

### 22.2. Version trong header

Một API có thể chọn version qua media type hoặc header riêng. Khi đó, tài liệu cần thể hiện rõ request header và cách server chọn schema.

### 22.3. Thay đổi tương thích

Các thay đổi thường có thể tương thích nếu thêm field optional trong response, thêm operation mới, thêm query parameter có default an toàn hoặc mở rộng enum theo cách client có thể chịu được.

Các thay đổi có nguy cơ phá vỡ client:
- Xóa field.
- Đổi tên field.
- Đổi kiểu dữ liệu.
- Thay đổi ý nghĩa null.
- Thêm field bắt buộc vào request cũ.
- Đổi status code hoặc error format mà client phụ thuộc.

### 22.4. Ví dụ phải theo version

Nếu schema v2 đổi amount từ integer sang decimal string, ví dụ v1 không nên bị sửa theo schema mới. Tài liệu cần cho biết mỗi ví dụ thuộc version nào.

### 22.5. Deprecation

Nếu operation cũ sắp ngừng hỗ trợ, có thể dùng header hoặc metadata deprecation và tài liệu migration. Ví dụ nên hướng người dùng đến operation thay thế.

## 23. Ví dụ trong OpenAPI hoặc API description

Nhiều API description format cho phép gắn example vào schema, parameter hoặc response.

Ví dụ OpenAPI rút gọn:

~~~yaml
paths:
  /customers:
    post:
      summary: Create a customer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCustomerRequest'
            example:
              name: Nguyen An
              email: an@example.com
      responses:
        '201':
          description: Customer created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CustomerResponse'
              example:
                id: CUS-1042
                name: Nguyen An
                email: an@example.com
                active: true
        '422':
          description: Validation error
          content:
            application/problem+json:
              example:
                title: Request validation failed
                status: 422
                errors:
                  - field: email
                    code: invalid_format
~~~

Đây là ví dụ minh họa cách tổ chức; API DSL nội bộ có thể dùng cú pháp khác. Điều quan trọng là schema và example cần liên kết rõ để công cụ có thể kiểm tra tính nhất quán.

### 23.1. Example và schema

Schema định nghĩa ràng buộc tổng quát. Example là một giá trị mẫu. Một công cụ có thể validate example theo schema để phát hiện lỗi tài liệu.

### 23.2. Một schema, nhiều example

Một operation nên có nhiều ví dụ nếu có nhiều tình huống quan trọng: thành công tối thiểu, thành công với field tùy chọn, request sai, không tìm thấy, conflict, kết quả phân trang và trường hợp bất đồng bộ.

### 23.3. Named example

Tên ví dụ nên mô tả tình huống, chẳng hạn **successful-create**, **missing-email** hoặc **version-conflict**, để tài liệu dễ điều hướng.

## 24. Viết ví dụ dễ hiểu và an toàn

Ví dụ tốt cần đủ thực tế để người đọc áp dụng, nhưng không tiết lộ dữ liệu thật.

### 24.1. Dùng dữ liệu giả lập

Dùng tên, email, ID và số liệu giả lập. Không sao chép access token, thông tin khách hàng, số tài khoản hoặc dữ liệu production.

### 24.2. Dùng giá trị nhất quán

Nếu customer ID trong request là CUS-1042, response và ví dụ tiếp theo nên dùng cùng ID khi mô tả cùng một luồng.

### 24.3. Tránh dữ liệu gây hiểu lầm

Nếu field là timestamp UTC, thêm ký hiệu Z. Nếu amount là VND, contract phải nói rõ đơn vị hoặc currency field.

### 24.4. Không đưa secret thật

Token trong ví dụ nên là placeholder dễ nhận biết như <access-token>. Không dùng token hoạt động hoặc key có thể truy cập hệ thống.

### 24.5. Giải thích phần thay đổi

Với ví dụ PATCH, cần nêu field nào được đổi và field nào giữ nguyên. Với response lỗi, cần nêu client nên làm gì tiếp theo.

### 24.6. Giữ ví dụ ngắn vừa đủ

Một ví dụ nên tập trung vào một mục tiêu. Không cần đưa mọi field vào một response nếu chúng không liên quan đến điều đang giải thích. Có thể có một ví dụ đầy đủ riêng cho toàn bộ resource.

## 25. Dùng ví dụ để sinh mock server và client

Ví dụ request/response có thể được dùng để hỗ trợ phát triển song song giữa client và server.

### 25.1. Mock response

Mock server đọc API contract và trả response mẫu. Frontend có thể phát triển trước khi backend hoàn tất.

### 25.2. Mock phải phản ánh trạng thái

Nếu request tạo đơn, mock có thể sinh ID và trạng thái giả lập. Nhưng hành vi mock cần nhất quán với schema và semantics thật.

### 25.3. Client generation

Từ schema, công cụ có thể sinh request model, response model, API client, enum và validation helper. Ví dụ giúp lập trình viên biết cách gọi operation và xử lý kết quả, nhưng không thay thế type-safe client model.

### 25.4. Contract testing

Consumer-driven contract test có thể xác nhận server thực hiện đúng những response mà client phụ thuộc. Provider test kiểm tra server có trả đúng status, header và schema hay không.

### 25.5. Example-based test

Một ví dụ tài liệu có thể được chạy như test:
1. Gửi request mẫu đến mock hoặc test server.
2. Kiểm tra status code.
3. Validate response theo schema.
4. Kiểm tra các field và giá trị quan trọng.
5. Lưu kết quả để phát hiện contract drift.

## 26. Kiểm thử request và response

Kiểm thử API cần bao gồm nhiều lớp.

### 26.1. Schema validation

Kiểm tra request và response theo schema: required field, kiểu dữ liệu, format, enum, min/max, pattern, array item và nested object.

### 26.2. Status code

Xác nhận operation trả đúng status cho từng tình huống. Không chỉ kiểm tra body.

### 26.3. Header

Kiểm tra Content-Type, Location, ETag, Retry-After, Cache-Control và correlation ID khi contract yêu cầu.

### 26.4. Negative test

Gửi request thiếu field, sai kiểu, sai format, body quá lớn hoặc parameter không hợp lệ. Xác nhận error format ổn định và không lộ thông tin nội bộ.

### 26.5. Authorization test

Kiểm tra không có token, token sai hoặc hết hạn, có token nhưng thiếu scope, truy cập tài nguyên thuộc tenant khác và quyền đọc/ghi khác nhau.

### 26.6. Concurrency test

Đọc cùng ETag rồi gửi hai cập nhật. Xác nhận chỉ cập nhật phù hợp với version hiện tại thành công và request cũ nhận conflict/precondition error.

### 26.7. Idempotency test

Gửi hai request cùng idempotency key. Xác nhận không tạo hai giao dịch hoặc hai tài nguyên nếu operation cam kết idempotent theo key.

### 26.8. Pagination test

Kiểm tra trang đầu, trang cuối, cursor sai, cursor hết hạn, sort tie và dữ liệu thay đổi giữa các lần đọc.

### 26.9. Serialization test

Kiểm tra Unicode, decimal, timestamp, null, field vắng mặt và enum không nhận diện.

### 26.10. Compatibility test

Chạy client cũ với server mới và ngược lại trong phạm vi tương thích được cam kết. Kiểm tra thêm field response có làm client cũ lỗi không.

## 27. Quy trình xây dựng bộ ví dụ API

Một quy trình có thể thực hiện như sau:

1. Liệt kê operation và use case chính.
2. Xác định method, path, parameter, header và body.
3. Định nghĩa request schema và response schema riêng khi cần.
4. Chọn status code cho từng kết quả.
5. Viết ví dụ thành công tối thiểu.
6. Viết ví dụ thành công có field tùy chọn hoặc quan hệ lồng.
7. Viết ví dụ lỗi validation, authentication, authorization, not found và conflict.
8. Bổ sung ví dụ filter, sort, pagination và concurrency.
9. Bổ sung idempotency hoặc async flow nếu operation có tác dụng phụ hoặc chạy lâu.
10. Validate mọi example theo schema.
11. Chạy example-based và contract tests.
12. Gắn ví dụ với API version và cập nhật cùng thay đổi contract.

## 28. Ví dụ tổng hợp: tạo và đọc đơn hàng

### 28.1. Tạo đơn

**Request**

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>
Idempotency-Key: order-create-2026-11-15-001

{
  "customerId": "CUS-1042",
  "items": [
    {
      "productId": "PRD-100",
      "quantity": 2
    },
    {
      "productId": "PRD-205",
      "quantity": 1
    }
  ],
  "shippingAddressId": "ADDR-08",
  "note": "Deliver after 5 PM"
}
~~~

**Response**

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/orders/ORD-2048
ETag: "order-v1"

{
  "id": "ORD-2048",
  "customerId": "CUS-1042",
  "status": "PENDING",
  "items": [
    {
      "productId": "PRD-100",
      "quantity": 2,
      "unitPrice": "125000.00",
      "lineTotal": "250000.00"
    },
    {
      "productId": "PRD-205",
      "quantity": 1,
      "unitPrice": "300000.00",
      "lineTotal": "300000.00"
    }
  ],
  "subtotal": "550000.00",
  "currency": "VND",
  "shippingAddressId": "ADDR-08",
  "note": "Deliver after 5 PM",
  "createdAt": "2026-11-15T10:30:00Z"
}
~~~

Server trả ID, giá đã áp dụng và tổng tiền. Client không tự quyết định unitPrice nếu giá được quản lý ở server.

### 28.2. Đọc đơn

**Request**

~~~http
GET /api/v1/orders/ORD-2048 HTTP/1.1
Accept: application/json
Authorization: Bearer <access-token>
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v1"

{
  "id": "ORD-2048",
  "customerId": "CUS-1042",
  "status": "PENDING",
  "subtotal": "550000.00",
  "currency": "VND",
  "createdAt": "2026-11-15T10:30:00Z"
}
~~~

### 28.3. Cập nhật ghi chú

**Request**

~~~http
PATCH /api/v1/orders/ORD-2048 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "order-v1"

{
  "note": "Deliver after 6 PM"
}
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v2"

{
  "id": "ORD-2048",
  "status": "PENDING",
  "note": "Deliver after 6 PM",
  "updatedAt": "2026-11-15T10:45:00Z"
}
~~~

### 28.4. Lỗi số lượng không hợp lệ

**Request**

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": "CUS-1042",
  "items": [
    {
      "productId": "PRD-100",
      "quantity": 0
    }
  ]
}
~~~

**Response**

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 422,
  "errors": [
    {
      "field": "items[0].quantity",
      "code": "minimum",
      "message": "Quantity must be at least 1."
    }
  ]
}
~~~

### 28.5. Lỗi cập nhật trên version cũ

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/version-conflict",
  "title": "Order has changed",
  "status": 412,
  "detail": "The supplied ETag is no longer current."
}
~~~

### 28.6. Những gì ví dụ thể hiện

- POST tạo resource và trả 201 cùng Location.
- Server cấp ID và tính giá.
- GET đọc resource bằng ID.
- PATCH chỉ thay đổi field được gửi.
- ETag bảo vệ cập nhật đồng thời.
- 422 mô tả lỗi validation theo field.
- 412 cho biết client cần đọc lại version mới.

## 29. Bài tập tự kiểm tra

### Bài 1: Request anatomy

Viết request GET một đơn hàng, có path parameter, authorization header và Accept header. Giải thích vai trò từng thành phần.

### Bài 2: Create response

Thiết kế request và response cho operation tạo sản phẩm. Xác định field do client gửi và field do server sinh.

### Bài 3: PUT và PATCH

Một customer có name, email và phone. Viết ví dụ PUT thay thế toàn bộ và PATCH chỉ đổi phone. Giải thích ý nghĩa field bị bỏ qua và field null.

### Bài 4: Error response

Thiết kế response lỗi validation khi email sai format và response lỗi nghiệp vụ khi đơn đã giao không thể hủy.

### Bài 5: Pagination

Viết request lấy trang tiếp theo bằng cursor và response chứa nextCursor, hasMore. Giải thích vì sao sort cần có tie-breaker ổn định.

### Bài 6: Authentication

Phân biệt response 401 và 403 bằng ví dụ. Nêu thông tin nào không nên đưa vào error body.

### Bài 7: Idempotency

Một client tạo thanh toán nhưng bị timeout. Hãy viết request retry cùng Idempotency-Key và giải thích cách server tránh tạo thanh toán trùng.

### Bài 8: Async operation

Thiết kế request tạo report, response 202 và response GET job khi hoàn tất. Xác định trạng thái và result URL.

### Bài 9: Batch API

Thiết kế batch có ba operation, trong đó một operation lỗi. Nêu cách client liên kết từng kết quả và xác định batch có atomic hay không.

### Bài 10: Contract testing

Chọn một operation và lập test cho schema, status, headers, success, validation error, authorization, concurrency và backward compatibility.

## Kết luận

Ví dụ request và response biến API contract thành những tình huống cụ thể mà client, server, tester và người tích hợp có thể cùng hiểu. Một bộ ví dụ đầy đủ cần thể hiện method, path, header, body, status code, response schema và các trường hợp lỗi quan trọng. Trong DSL API và dữ liệu, cần phân biệt schema request với schema response, mô tả rõ null và field vắng mặt, đồng thời giữ ví dụ nhất quán với validation, pagination, authentication, idempotency, concurrency và versioning. Khi ví dụ được kiểm tra theo schema và chạy như contract test, chúng trở thành tài liệu có thể kiểm chứng, giúp giảm hiểu nhầm và phát hiện sớm sự lệch nhau giữa API description với implementation.
