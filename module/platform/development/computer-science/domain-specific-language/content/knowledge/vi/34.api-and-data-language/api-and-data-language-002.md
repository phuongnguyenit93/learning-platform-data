# Mô tả endpoint

## 1. Endpoint trong DSL API là gì?

Trong một hệ thống API, endpoint là một điểm truy cập mà client có thể gọi để yêu cầu một thao tác hoặc lấy một tài nguyên. Endpoint thường được xác định bởi một địa chỉ, phương thức, tham số đầu vào, kiểu dữ liệu request, các response có thể trả về và quy tắc bảo mật.

Trong DSL (*Domain-Specific Language*) dành cho API, endpoint được mô tả bằng một cấu trúc khai báo có thể đọc được và có thể xử lý tự động. Từ mô tả đó, hệ thống có thể tạo tài liệu API, kiểm tra tính hợp lệ, sinh server routing, sinh client SDK, tạo mock server và xây dựng contract tests.

Ví dụ một mô tả endpoint mang tính minh họa:

~~~text
api "Order API" version "v1" {
    endpoint GET "/orders/{orderId}" {
        operationId: "getOrder"
        summary: "Lấy thông tin đơn hàng"

        pathParam orderId: UUID

        response 200: Order
        response 404: ErrorResponse
    }
}
~~~

Cú pháp trên chỉ là ví dụ để giải thích khái niệm; mỗi DSL có thể chọn grammar và từ khóa riêng. Ý nghĩa của mô hình là endpoint có method GET, route chứa path parameter orderId, operation ID ổn định và hai response contract.

Mô tả endpoint không chỉ là ghi một URL. Nó là một phần của hợp đồng API (*API contract*), xác định client được phép gửi gì, server cam kết trả gì, điều kiện nào tạo ra lỗi và cách hai phía tương tác.

Một endpoint được mô tả tốt giúp:
- Client biết cách gọi API mà không phải đọc implementation.
- Server có một contract rõ để triển khai.
- Tài liệu được sinh nhất quán.
- Kiểm tra breaking changes trước khi phát hành.
- Sinh client/server stubs.
- Tạo mock và contract tests.
- Quản lý authentication, authorization, rate limits và deprecation.
- Theo dõi endpoint qua version và môi trường triển khai.

## 2. Endpoint contract và các thành phần cốt lõi

Một endpoint contract thường gồm các nhóm thông tin:

| Thành phần | Vai trò |
|---|---|
| API/service | Nhóm endpoint thuộc về API nào |
| Method | Loại thao tác HTTP hoặc RPC |
| Path/route | Địa chỉ và cấu trúc định tuyến |
| Operation ID | Định danh ổn định của operation |
| Summary/description | Giải thích mục đích và hành vi |
| Parameters | Input qua path, query, header hoặc cookie |
| Request body | Dữ liệu client gửi lên |
| Responses | Status code, headers và body server trả về |
| Schemas | Kiểu dữ liệu của request/response |
| Security | Authentication và authorization requirements |
| Errors | Mã lỗi và cấu trúc lỗi |
| Examples | Ví dụ request, response và error |
| Lifecycle | Version, deprecation và sunset policy |
| Runtime binding | Handler hoặc operation thực thi |

Không phải endpoint nào cũng cần mọi thành phần. Ví dụ GET thường không có request body; endpoint công khai có thể không cần authentication; endpoint trả 204 không có response body.

DSL cần phân biệt phần bắt buộc, phần tùy chọn và default. Nếu field bị bỏ qua, người đọc phải biết nó được suy ra, dùng default hay không áp dụng.

## 3. Tổ chức API và namespace

Endpoint thường thuộc một API, service hoặc resource group. DSL nên cung cấp cách tổ chức để tránh route và operation ID trùng lặp.

Ví dụ:

~~~text
api "Commerce API" {
    basePath: "/api/v1"

    resource "orders" {
        endpoint GET "/{orderId}" {
            operationId: "getOrder"
        }

        endpoint POST "/" {
            operationId: "createOrder"
        }
    }
}
~~~

Một số mô hình tổ chức thường gặp:
- API-level: tên, version, server URL, contact và license.
- Service-level: nhóm endpoint theo bounded context hoặc service.
- Resource-level: nhóm theo orders, customers, payments.
- Tag-level: nhóm phục vụ tài liệu và navigation.
- Module-level: tái sử dụng schema, parameter và security definition.

### 3.1. Base path

Base path là prefix chung cho các route. Nếu basePath là `/api/v1` và endpoint path là `/orders/{orderId}`, effective route là `/api/v1/orders/{orderId}`.

Cần quy định cách ghép slash, xử lý trailing slash và route normalization. Không nên để `/api/v1` + `orders` có thể sinh ra các kết quả khác nhau tùy implementation.

### 3.2. Server environments

Một API có thể có nhiều server:
- Development.
- Staging.
- Production.
- Regional endpoint.
- Tenant-specific endpoint.

Server URL có thể chứa biến môi trường hoặc placeholder. Không nên nhúng credential hoặc secret trực tiếp vào server URL trong tài liệu công khai.

### 3.3. Namespace và import

DSL lớn có thể chia endpoint và schema thành module. Import cần giải quyết tên rõ ràng, phát hiện circular dependency và tránh xung đột tên giữa hai module.

## 4. HTTP method và semantics

Với HTTP API, method biểu đạt loại thao tác mà client yêu cầu.

| Method | Ý nghĩa phổ biến | Đặc tính cần mô tả |
|---|---|---|
| GET | Đọc tài nguyên hoặc representation | Safe, thường không có body |
| POST | Tạo tài nguyên hoặc thực hiện action | Có thể không idempotent |
| PUT | Thay thế representation tại URI | Thường idempotent |
| PATCH | Cập nhật một phần | Semantics phụ thuộc patch format |
| DELETE | Xóa tài nguyên | Idempotency theo contract |
| HEAD | Lấy metadata như GET nhưng không có body | Header tương ứng với GET |
| OPTIONS | Hỏi khả năng giao tiếp | Allow/CORS hoặc capability metadata |

### 4.1. Safe method

Safe method không được thiết kế để yêu cầu thay đổi trạng thái nghiệp vụ của server. GET không nên tạo đơn hàng hoặc trừ tiền chỉ vì client gọi nó.

Server có thể tạo log, cache hoặc cập nhật metric khi xử lý GET; điều đó không làm thay đổi semantics safe của HTTP.

### 4.2. Idempotent method

Một operation idempotent có cùng hiệu ứng dự kiến khi được gọi nhiều lần với cùng request. PUT và DELETE thường được thiết kế idempotent theo HTTP semantics. POST có thể được làm idempotent bằng idempotency key.

Mô tả endpoint cần nói rõ retry có an toàn hay không, đặc biệt với payment, reservation và các operation tạo side effect.

### 4.3. Method không chuẩn

Một DSL có thể hỗ trợ custom method hoặc RPC action. Nếu vậy, cần mô tả semantics, proxy compatibility, cache behavior và tooling support. Không nên tự tạo method chỉ vì muốn tên operation giống business action.

## 5. Path và route template

Path xác định tài nguyên hoặc operation được truy cập.

Ví dụ:

~~~text
GET /customers/{customerId}/orders/{orderId}
~~~

Route template có hai segment tĩnh và hai path parameters.

### 5.1. Path parameter

Path parameter là một phần của route và thường bắt buộc:

~~~text
endpoint GET "/orders/{orderId}" {
    pathParam orderId: UUID
}
~~~

Cần quy định:
- Tên parameter khớp chính xác với placeholder.
- Kiểu dữ liệu.
- Format hoặc constraint.
- Required semantics.
- Encoding và normalization.
- Hành vi khi giá trị không hợp lệ.

Nếu route có placeholder nhưng không có parameter declaration, contract nên báo lỗi.

### 5.2. Route specificity và ambiguity

Hai route có thể overlap:

~~~text
GET /orders/{orderId}
GET /orders/search
~~~

Nếu router xử lý parameter route trước route tĩnh, chuỗi search có thể bị hiểu là orderId. DSL hoặc runtime cần có quy tắc ưu tiên route tĩnh, constraint rõ hoặc phát hiện route ambiguity khi compile.

### 5.3. Path constraints

Parameter có thể giới hạn bằng type hoặc pattern:

~~~text
pathParam orderId: UUID
pathParam year: Integer min 2000 max 2100
~~~

Nếu dùng regex pattern, cần tránh pattern quá tốn kém hoặc dễ gây denial of service. Type và constraint phải được thực thi nhất quán ở router và validation layer.

### 5.4. Trailing slash và normalization

Cần quyết định `/orders` và `/orders/` có được coi là cùng route hay khác route. Việc normalize URL cần thống nhất với reverse proxy, router và API gateway.

## 6. Parameters

Parameter là input được truyền ngoài request body. HTTP API thường có bốn vị trí:

- Path: định danh segment trong route.
- Query: filter, pagination, search hoặc option.
- Header: metadata, version, conditional request hoặc correlation.
- Cookie: session hoặc một số trạng thái client.

Ví dụ:

~~~text
endpoint GET "/orders/{orderId}" {
    pathParam orderId: UUID
    queryParam expand: String optional
    headerParam If-None-Match: String optional
}
~~~

### 6.1. Parameter metadata

Mỗi parameter nên mô tả:
- Name.
- Location.
- Data type và format.
- Required/optional.
- Default value.
- Allowed values.
- Minimum/maximum.
- Pattern.
- Description.
- Example.
- Deprecated flag.

### 6.2. Required và optional

Path parameter thường required. Query/header parameter có thể optional. DSL cần định nghĩa rõ việc thiếu parameter khác với truyền giá trị rỗng hoặc null như thế nào.

### 6.3. Default value

Nếu parameter có default, cần xác định default được áp dụng ở client, gateway hay server. Default trong tài liệu không tự động có nghĩa server sẽ dùng giá trị đó.

### 6.4. Repeated parameters

Query có thể cho phép lặp:

~~~text
GET /orders?status=NEW&status=PAID
~~~

Cần quy định cách serialize collection: repeated key, comma-separated, space-delimited hoặc format khác. Client generator và server parser phải dùng cùng quy ước.

### 6.5. Serialization và encoding

Array, object và reserved characters có thể được encode theo nhiều kiểu. Endpoint DSL nên hỗ trợ hoặc chọn default rõ ràng cho query serialization, percent-encoding và case sensitivity của header names.

### 6.6. Parameter validation

Validation có thể gồm:
- Required.
- Length.
- Numeric range.
- Pattern.
- Enum.
- Format.
- Cross-parameter constraints.

Ví dụ startDate phải nhỏ hơn endDate. Constraint liên tham số cần có diagnostic và error contract rõ.

## 7. Request body

Request body chứa dữ liệu mà client gửi cho server, thường dùng trong POST, PUT và PATCH.

Ví dụ:

~~~text
endpoint POST "/orders" {
    requestBody: CreateOrderRequest
    contentType: "application/json"
}
~~~

### 7.1. Request schema

Schema mô tả:
- Object fields.
- Primitive types.
- Nested objects.
- Arrays.
- Required fields.
- Nullable fields.
- Enum values.
- Format.
- Constraints.
- Default values.
- Additional properties policy.

Ví dụ:

~~~text
schema CreateOrderRequest {
    customerId: UUID required
    items: OrderItem[] required minItems 1
    note: String optional maxLength 500
}
~~~

### 7.2. Required và nullable

Required trả lời field có bắt buộc xuất hiện hay không. Nullable trả lời field có được phép mang giá trị null hay không.

Một field có thể required nhưng nullable, hoặc optional nhưng non-null khi xuất hiện. DSL cần biểu diễn hai khái niệm này riêng.

### 7.3. Content-Type

Endpoint có thể nhận JSON, XML, form data, multipart hoặc binary content. Mỗi media type có schema hoặc encoding riêng.

Không nên mặc định mọi request body đều là JSON nếu endpoint nhận upload file hoặc stream.

### 7.4. Multipart và file upload

Với multipart, mô tả:
- Tên part.
- Content type.
- File size limit.
- Required/optional.
- Metadata fields.
- Number of files.
- Streaming behavior nếu có.

### 7.5. PATCH semantics

PATCH cần xác định format cập nhật:
- JSON Merge Patch.
- JSON Patch.
- Custom partial-update schema.
- Field mask.

Nếu không nói rõ, client không biết field bị bỏ qua, null hoặc empty có nghĩa gì.

### 7.6. Request body và idempotency

Với operation tạo tài nguyên hoặc side effect, có thể khai báo idempotency key hoặc request token. Server cần mô tả phạm vi uniqueness, thời gian lưu và behavior khi key được gửi lại với payload khác.

## 8. Response contract

Một endpoint có thể trả nhiều response tùy kết quả.

Ví dụ:

~~~text
endpoint GET "/orders/{orderId}" {
    response 200: Order
    response 304: NoBody
    response 404: ErrorResponse
    response 500: ErrorResponse
}
~~~

Response contract nên mô tả:
- HTTP status code.
- Description.
- Response headers.
- Media type.
- Body schema.
- Example.
- Điều kiện tạo response.
- Có body hay không.

### 8.1. Success responses

Không phải mọi success đều là 200:
- 200 OK: request thành công, có thể có body.
- 201 Created: tạo resource; thường có Location.
- 202 Accepted: đã nhận xử lý bất đồng bộ.
- 204 No Content: thành công không có body.
- 206 Partial Content: trả một phần representation.

DSL nên hỗ trợ khai báo status cụ thể và không giả định mọi success response có cùng schema.

### 8.2. Multiple success responses

Một operation có thể trả 200 hoặc 206 tùy Range, 200 hoặc 204 tùy có representation, hoặc 202 khi xử lý nền. Mỗi response cần condition và schema riêng.

### 8.3. Response headers

Một số header có ý nghĩa trong contract:
- Location.
- ETag.
- Last-Modified.
- Retry-After.
- Cache-Control.
- RateLimit headers.
- Correlation/request ID.

Cần mô tả kiểu dữ liệu và điều kiện xuất hiện.

### 8.4. No-content response

Response 204 không có body. Contract không nên gắn schema body cho status này. Tương tự, HEAD response không có body dù headers có thể mô tả representation.

### 8.5. Streaming response

Endpoint có thể trả:
- Server-Sent Events.
- NDJSON.
- Binary stream.
- File download.
- Long-lived stream.

Cần mô tả media type, framing, kết thúc stream, lỗi giữa chừng và cancellation semantics.

## 9. Error contract

Lỗi là một phần của API contract. Client cần phân biệt lỗi validation, authentication, authorization, missing resource, conflict, rate limit và lỗi hệ thống.

Một error schema có thể gồm:

~~~text
schema ApiError {
    code: String required
    message: String required
    requestId: String optional
    details: ErrorDetail[] optional
}
~~~

Ví dụ response:

~~~json
{
  "code": "ORDER_NOT_FOUND",
  "message": "The requested order does not exist",
  "requestId": "req-8c12"
}
~~~

### 9.1. HTTP status và error code

HTTP status biểu diễn nhóm kết quả ở protocol level. Error code biểu diễn nguyên nhân cụ thể trong domain.

Ví dụ nhiều error code có thể cùng dùng 409 Conflict:
- ORDER_ALREADY_CANCELLED.
- INVENTORY_VERSION_CONFLICT.
- DUPLICATE_REQUEST.

Không nên dùng HTTP status làm mã lỗi duy nhất.

### 9.2. Error catalog

Một DSL có thể khai báo error catalog dùng chung:
- Code.
- Status.
- Message template.
- Retryable flag.
- Documentation link.
- Safe details.
- Localization key.

### 9.3. Validation errors

Validation error nên chỉ rõ field/path, code và message. Với nested object, path có thể là `items[2].quantity`. Không nên trả raw exception hoặc stack trace cho client.

### 9.4. Retryability

Contract có thể cho biết lỗi có thể retry hay không. Retry policy cần cân nhắc:
- Idempotency.
- Retry-After.
- Backoff.
- Maximum attempts.
- Deadline.
- Side effects đã xảy ra hay chưa.

### 9.5. Problem Details

Một API có thể dùng RFC 9457 Problem Details cho HTTP errors. DSL có thể ánh xạ schema lỗi về các field chuẩn như type, title, status, detail và instance, đồng thời bổ sung extension fields cho domain error code.

## 10. Authentication và authorization

Endpoint có thể yêu cầu một hoặc nhiều security schemes:
- API key.
- HTTP Basic.
- Bearer token.
- OAuth 2.0.
- OpenID Connect.
- Mutual TLS.
- Cookie/session authentication.

Ví dụ minh họa:

~~~text
security {
    scheme BearerAuth
    scopes: ["orders:read"]
}

endpoint GET "/orders/{orderId}" {
    security: BearerAuth
}
~~~

### 10.1. Authentication

Authentication xác định client hoặc principal là ai. Contract cần nói scheme, vị trí credential và cách client cung cấp credential.

Không bao giờ ghi secret thực tế vào DSL source hoặc generated documentation.

### 10.2. Authorization

Authorization xác định principal được phép thực hiện operation nào trên resource nào. Có thể mô tả scopes, roles hoặc permission names.

Ví dụ:
- orders:read.
- orders:write.
- payments:refund.

Scope trong contract là metadata cho client và tooling; server vẫn phải enforce authorization ở runtime.

### 10.3. Security inheritance

Security có thể khai báo ở API-level rồi override ở endpoint-level. Cần phân biệt:
- Inherit security.
- Add requirements.
- Replace requirements.
- Explicitly disable security.

Nếu DSL dùng danh sách security schemes, phải định nghĩa rõ AND/OR semantics. Ví dụ hai scheme trong cùng requirement có thể cần đồng thời, trong khi hai requirement object khác nhau có thể là lựa chọn thay thế.

### 10.4. Public endpoint

Endpoint public cần được khai báo rõ. Không nên vô tình bỏ field security rồi để mỗi generator suy diễn khác nhau.

### 10.5. Security responses

Các response 401 và 403 nên được mô tả khi phù hợp. Cần phân biệt thiếu hoặc credential không hợp lệ với principal hợp lệ nhưng không có quyền.

## 11. Headers, caching và conditional requests

Endpoint có thể dùng header để điều khiển cache và tính nhất quán.

### 11.1. ETag

ETag là validator cho representation. Client có thể gửi If-None-Match để hỏi representation có thay đổi không. Nếu không đổi, server có thể trả 304.

### 11.2. Conditional update

If-Match có thể được dùng để ngăn ghi đè dữ liệu đã thay đổi từ lần đọc trước. Nếu version không khớp, server có thể trả 412 Precondition Failed.

### 11.3. Cache policy

Contract có thể mô tả:
- Cacheable hay không.
- Cache-Control directives.
- Shared/private cache.
- Max age.
- Vary headers.
- Invalidation behavior.

Không nên khai báo cacheable cho response chứa dữ liệu nhạy cảm nếu policy không cho phép.

### 11.4. Correlation headers

Request ID hoặc trace context giúp liên kết API request với logs và distributed traces. DSL có thể mô tả header được chấp nhận hoặc trả về, nhưng runtime cần tạo và propagate giá trị đúng chuẩn.

## 12. Pagination, filtering và sorting

Collection endpoints thường cần pagination để tránh trả quá nhiều dữ liệu.

### 12.1. Offset pagination

Ví dụ:

~~~text
GET /orders?offset=20&limit=10
~~~

Contract cần quy định:
- Default limit.
- Maximum limit.
- Offset base.
- Stable ordering.
- Behavior khi offset vượt số phần tử.

Offset pagination đơn giản nhưng có thể bỏ sót hoặc lặp item khi dữ liệu thay đổi giữa các request.

### 12.2. Cursor pagination

Ví dụ:

~~~text
GET /orders?cursor=eyJpZCI6IjEwMCJ9&limit=20
~~~

Cursor thường đại diện vị trí trong một thứ tự ổn định. Contract cần mô tả cursor opaque hay readable, expiry, next/previous token và cách xử lý cursor không hợp lệ.

### 12.3. Response metadata

Một response pagination có thể gồm:
- items.
- nextCursor.
- previousCursor.
- hasMore.
- totalCount nếu được hỗ trợ.

Không nên cam kết totalCount nếu việc tính tổng quá tốn kém hoặc kết quả không nhất quán.

### 12.4. Filtering

Filter DSL có thể mô tả filter parameters và operators được phép:
- eq.
- ne.
- gt/gte.
- lt/lte.
- in.
- contains.
- prefix.

Cần giới hạn field và operator để tránh query injection hoặc truy vấn tốn tài nguyên.

### 12.5. Sorting

Sort contract cần xác định field được phép sort, chiều asc/desc, default order và tie-break ổn định. Pagination thường cần stable sort để không trùng hoặc mất kết quả.

## 13. Versioning và compatibility

API có thể thay đổi theo thời gian. Endpoint DSL cần thể hiện version ở cấp API, route, header hoặc media type theo chiến lược đã chọn.

### 13.1. Versioning strategies

Các cách phổ biến:
- URI versioning: `/api/v1/orders`.
- Header versioning.
- Media type versioning.
- Query parameter versioning.

Mỗi cách có trade-off về caching, routing, documentation và client compatibility.

### 13.2. Backward-compatible changes

Một số thay đổi thường ít rủi ro hơn:
- Thêm endpoint mới.
- Thêm optional request field.
- Thêm response field nếu client bỏ qua field chưa biết.
- Thêm enum value chỉ khi client có thể xử lý unknown values.

Ngay cả thay đổi tưởng tương thích cũng cần xem xét client code generator và strict schema validation.

### 13.3. Breaking changes

Ví dụ:
- Xóa hoặc đổi tên field.
- Đổi field type.
- Làm optional thành required.
- Đổi route hoặc method.
- Xóa response status.
- Thay semantics của operation.
- Đổi security requirement.
- Đổi enum theo cách làm client cũ không xử lý được.

### 13.4. Deprecation

Một endpoint hoặc field có thể được đánh dấu deprecated kèm:
- Lý do.
- Replacement.
- Ngày deprecation.
- Sunset date.
- Migration guide.
- Link tài liệu.

Deprecation không tự động có nghĩa endpoint đã bị xóa. Runtime và gateway cần policy riêng cho thời điểm ngừng phục vụ.

### 13.5. Compatibility checking

Contract diff tool có thể so sánh hai version và phân loại:
- Compatible.
- Potentially breaking.
- Breaking.
- Documentation-only.
- Security-impacting.

Không nên chỉ so sánh schema; cần xét route, method, status codes, security, headers và semantics được khai báo.

## 14. Operation ID, tags và documentation metadata

Operation ID là định danh duy nhất cho operation trong API document và thường được dùng để sinh method trong SDK.

Ví dụ:
- getOrder.
- createOrder.
- cancelOrder.
- listCustomerOrders.

Nên dùng tên ổn định và duy nhất trong phạm vi API. Đổi operation ID có thể làm thay đổi public method name trong generated SDK dù route không đổi.

### 14.1. Summary và description

Summary nên ngắn, mô tả hành động. Description giải thích:
- Điều kiện sử dụng.
- Business rules.
- Side effects.
- Authorization.
- Retry behavior.
- Consistency guarantees.
- Những giới hạn đặc biệt.

### 14.2. Tags

Tags nhóm endpoint theo resource hoặc capability để tài liệu dễ điều hướng. Một endpoint có thể có nhiều tag nếu phù hợp.

### 14.3. External documentation

Có thể liên kết tới:
- Guide.
- Runbook.
- Schema registry.
- Error catalog.
- Changelog.
- Security policy.

Link phải ổn định và không trỏ đến tài liệu chỉ người viết DSL mới truy cập được nếu tài liệu API công khai.

## 15. Examples và sample payloads

Example giúp client hiểu cách sử dụng endpoint và giúp test/mock tooling tạo dữ liệu.

Một endpoint có thể có:
- Request example.
- Success response example.
- Error example.
- Parameter example.
- Example theo từng media type.

Ví dụ:

~~~http
POST /api/v1/orders
Content-Type: application/json
Authorization: Bearer <token>

{
  "customerId": "7d2a9d2a-6d18-4c11-a0c2-123456789abc",
  "items": [
    {"productId": "SKU-100", "quantity": 2}
  ]
}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ORD-204
Content-Type: application/json

{
  "id": "ORD-204",
  "status": "PENDING"
}
~~~

Examples cần khớp schema và không chứa credential hoặc dữ liệu cá nhân thật. Có thể dùng synthetic data với format hợp lệ.

### 15.1. Examples và defaults

Example minh họa một trường hợp. Default là giá trị được áp dụng khi input bị bỏ qua theo contract. Không được nhầm hai khái niệm này.

### 15.2. Multiple examples

Có thể khai báo nhiều example cho:
- Các trạng thái nghiệp vụ.
- Các lỗi.
- Các loại client.
- Các biến thể payload.
- Các trường hợp boundary.

### 15.3. Example validation

Tooling có thể parse example và validate theo schema để phát hiện tài liệu lỗi thời.

## 16. OpenAPI và các chuẩn mô tả API

OpenAPI là một đặc tả phổ biến để mô tả HTTP APIs theo định dạng máy đọc được. DSL API có thể ánh xạ model endpoint sang OpenAPI document.

Các khái niệm thường có mapping:
- API metadata → info.
- Server definitions → servers.
- Endpoint method/path → paths và operations.
- Parameters → parameters.
- Request body → requestBody.
- Response contracts → responses.
- Data types → components/schemas.
- Security schemes → components/securitySchemes.
- Tags → tags.
- Examples → examples.
- Deprecation → deprecated.
- Operation ID → operationId.

### 16.1. DSL có thể biểu đạt nhiều hơn OpenAPI

DSL có thể chứa runtime binding, authorization policy, internal workflow, retry strategy hoặc data lineage mà OpenAPI không biểu đạt trực tiếp. Khi export, có thể cần vendor extensions hoặc giữ metadata trong một artifact riêng.

### 16.2. OpenAPI không thay thế implementation

OpenAPI mô tả contract. Nó không tự bảo đảm server thực thi đúng contract. Cần contract tests hoặc runtime validation để phát hiện sai lệch giữa mô tả và implementation.

### 16.3. Import và round-trip

Nếu DSL import OpenAPI, cần xác định construct nào được giữ nguyên, construct nào không hỗ trợ và cách xử lý extension. Round-trip có thể không lossless nếu DSL và OpenAPI có khả năng biểu đạt khác nhau.

### 16.4. Schema dialect

Cần xác định JSON Schema dialect hoặc schema semantics mà DSL sử dụng. Một từ khóa schema có thể mang semantics khác nhau giữa các dialect hoặc generator.

## 17. Từ endpoint contract đến runtime routing

Mô tả endpoint có thể được dùng để tạo route table hoặc server stubs.

Pipeline khái niệm:

~~~text
Endpoint DSL
    |
    v
Parser / Semantic Validator
    |
    v
Endpoint Model
    |
    +----> OpenAPI Generator
    |
    +----> Client SDK Generator
    |
    +----> Server Stub Generator
    |
    +----> Mock Server
    |
    v
Runtime Route Registry
    |
    v
Handler Binding
~~~

### 17.1. Route registry

Runtime route registry cần biết:
- Method.
- Normalized path.
- Path parameter matcher.
- Handler ID.
- Authentication policy.
- Request validator.
- Response serializer.
- Middleware chain.

### 17.2. Handler binding

Endpoint contract có thể gắn với handler:

~~~text
endpoint POST "/orders" {
    operationId: "createOrder"
    requestBody: CreateOrderRequest
    response 201: Order

    handler: OrderController.create
}
~~~

Binding cần được kiểm tra khi khởi động hoặc build. Nếu handler không tồn tại, có signature không tương thích hoặc không thể serialize response schema, hệ thống nên báo lỗi rõ.

### 17.3. Middleware

Endpoint có thể kế thừa hoặc chỉ định middleware:
- Authentication.
- Authorization.
- Validation.
- Rate limiting.
- Logging.
- Tracing.
- Transaction.
- Idempotency.
- Error mapping.

Thứ tự middleware có thể ảnh hưởng behavior. DSL cần định nghĩa precedence và cách override.

### 17.4. Contract enforcement

Runtime có thể validate request và response theo contract:
- Request không hợp lệ trả 4xx.
- Handler trả response không khớp schema được phát hiện.
- Status code chưa khai báo được cảnh báo hoặc chặn theo policy.
- Header bắt buộc được kiểm tra.

Response validation có thể tốn chi phí nên cần policy theo môi trường hoặc mức độ quan trọng.

## 18. Validation khi mô tả endpoint

Validation có thể diễn ra ở nhiều tầng.

### 18.1. Syntax validation

Kiểm tra grammar:
- Method hợp lệ.
- Route string hợp lệ.
- Block và declaration đúng cú pháp.
- Field declaration có cấu trúc hợp lệ.

### 18.2. Semantic validation

Kiểm tra:
- operationId không trùng.
- Path placeholder có parameter tương ứng.
- Parameter location hợp lệ.
- Request schema tồn tại.
- Response status không trùng mâu thuẫn.
- Referenced schema resolve được.
- Security scheme được khai báo.
- Route không ambiguity.
- Handler binding tồn tại.

### 18.3. Contract validation

Kiểm tra schema và protocol:
- GET/HEAD body theo policy.
- 204 không có body.
- Status code hợp lệ.
- Content type phù hợp.
- Required field nhất quán.
- Example khớp schema.
- Response headers đúng type.

### 18.4. Policy validation

Policy có thể quy định:
- Mọi endpoint ghi dữ liệu phải yêu cầu authentication.
- Endpoint public phải được phê duyệt.
- Operation có side effect cần idempotency strategy.
- Response lỗi không được chứa stack trace.
- Endpoint production phải có rate limit.
- Deprecated endpoint phải có replacement.

### 18.5. Diagnostics

Diagnostic nên có:
- Stable error code.
- Severity.
- Source range.
- Endpoint/operation ID.
- Message.
- Related location.
- Suggested fix nếu xác định được.

## 19. Security considerations

Endpoint description là nơi định nghĩa bề mặt tấn công của API. Một contract tốt giúp tooling và reviewer nhìn thấy rủi ro sớm.

### 19.1. Input validation

Xác định type, range, length, enum và format. Không dựa vào client validation vì request có thể được gửi trực tiếp đến server.

### 19.2. Injection

Query, path và body data phải được xem là untrusted. DSL có thể mô tả schema nhưng implementation phải dùng parameterized queries, safe serialization và output encoding phù hợp.

### 19.3. Mass assignment

Không bind trực tiếp request object vào toàn bộ domain entity nếu client có thể gửi field nhạy cảm như role, ownerId hoặc internalStatus. Request schema nên chỉ công bố các field client được phép sửa.

### 19.4. Authorization at resource level

Scope ở endpoint-level chưa chắc đủ. Server còn phải kiểm tra principal có quyền truy cập đúng resource ID hay không. Không nên coi việc xác thực token là bằng chứng user được đọc mọi order.

### 19.5. Rate limiting và quotas

Có thể mô tả limit theo:
- Client/API key.
- User.
- Tenant.
- Endpoint.
- Time window.
- Burst và sustained rate.

Cần xác định response khi vượt limit, thường kèm status 429 và retry metadata.

### 19.6. Sensitive data

Schema nên đánh dấu field nhạy cảm để documentation, logs, tracing và generated examples biết cách redaction. Không đưa secret hoặc dữ liệu cá nhân thật vào examples.

### 19.7. CORS và browser access

Nếu API được gọi từ browser, cần cấu hình CORS ở gateway/server. CORS không thay thế authentication hoặc authorization. Contract có thể ghi metadata liên quan nhưng policy thực tế thường nằm ở API gateway hoặc server configuration.

## 20. Observability và vận hành endpoint

Endpoint contract có thể cung cấp metadata để runtime tạo telemetry nhất quán.

Thông tin hữu ích:
- Operation ID.
- API version.
- Route template.
- Request/trace ID.
- Status code.
- Latency.
- Error category.
- Retry count.
- Consumer/client category nếu được phép.

Không nên dùng raw path có ID động làm metric label vì cardinality cao. Dùng route template như `/orders/{orderId}`.

### 20.1. Logging

Log có thể ghi operation ID, status, duration và correlation ID. Request/response body cần redaction theo schema và policy.

### 20.2. Metrics

Các metric phổ biến:
- Request count theo operation.
- Error rate.
- Latency histogram.
- Rate-limit count.
- Validation failure count.
- Request/response size.
- Active requests.

### 20.3. Distributed tracing

Một HTTP request có thể tạo server span gắn operation ID, rồi propagate trace context đến downstream service. Contract metadata giúp dashboard nhóm trace theo operation.

### 20.4. Health và readiness

Health endpoint thường có contract riêng và security policy riêng. Cần tránh trả thông tin nội bộ như database credentials hoặc stack trace trong health response.

## 21. Async operations, callbacks và webhooks

Không phải mọi endpoint đều trả kết quả ngay.

### 21.1. Long-running operation

Endpoint có thể trả 202 Accepted và operation reference:

~~~text
POST /reports {
    response 202: OperationReference
}

GET /operations/{operationId} {
    response 200: OperationStatus
}
~~~

Contract cần mô tả:
- Operation ID.
- Polling endpoint.
- Status lifecycle.
- Retry interval.
- Expiration.
- Cancellation nếu hỗ trợ.
- Final result reference.

### 21.2. Webhooks

Webhook là endpoint do client cung cấp để server gọi khi có event. Contract cần mô tả:
- Event types.
- Payload schema.
- Signature verification.
- Retry policy.
- Delivery timeout.
- Duplicate delivery semantics.
- Ordering guarantee.
- Replay protection.

### 21.3. Callback URLs

Nếu request cho phép client gửi callback URL, cần kiểm tra SSRF risk. Server không nên gọi tùy ý URL do người dùng cung cấp mà thiếu allowlist, DNS/IP validation và egress policy.

### 21.4. Event-driven API

Với asynchronous messaging, endpoint contract có thể được mở rộng hoặc liên kết với message channel/schema. Cần phân biệt HTTP endpoint với event channel để client hiểu transport và delivery semantics.

## 22. Versioning của schema và reusable components

Schema thường được dùng lại bởi nhiều endpoint. DSL nên hỗ trợ component reuse để tránh định nghĩa trùng.

Ví dụ:

~~~text
schema Address {
    line1: String required
    city: String required
    postalCode: String optional
}

schema Customer {
    id: UUID required
    address: Address optional
}
~~~

### 22.1. Reusable parameters

Các parameter dùng chung như pageSize, correlationId hoặc locale có thể được định nghĩa một lần và tham chiếu từ nhiều endpoint.

### 22.2. Reusable responses

Response lỗi chung như Unauthorized, Forbidden hoặc InternalServerError có thể được tái sử dụng.

### 22.3. Schema composition

Có thể hỗ trợ:
- Reuse/reference.
- Composition như allOf/oneOf/anyOf.
- Enum.
- Discriminator.
- Generic schema nếu DSL hỗ trợ.
- Recursive schema có giới hạn.

Cần quy định semantics composition để validation và code generation thống nhất.

### 22.4. Schema evolution

Khi schema được dùng bởi nhiều endpoint, thay đổi một component có thể ảnh hưởng nhiều operation. Tooling nên hiển thị dependency và breaking change impact.

## 23. Code generation và client SDK

Endpoint DSL có thể sinh client SDK cho các ngôn ngữ khác nhau.

Generated client có thể cung cấp:
- Method theo operationId.
- Typed request object.
- Typed response/result.
- Error model.
- Authentication configuration.
- Retry behavior theo contract.
- Pagination helpers.
- Async operation polling.
- Serialization và validation.

### 23.1. Naming

Operation ID và schema names ảnh hưởng public API của SDK. Cần quy tắc chuyển camelCase/PascalCase, reserved words và collision giữa các operation.

### 23.2. Unknown enum values

Client nên có cách xử lý enum value mới nếu server mở rộng. Nếu generator tạo enum đóng, một giá trị mới có thể khiến client cũ lỗi khi deserialize.

### 23.3. Error handling

SDK nên giữ status code, error code, request ID và safe details. Không nên biến mọi lỗi thành một exception chung làm mất thông tin cần thiết.

### 23.4. Generated code compatibility

Version SDK cần liên kết với API contract revision. Khi đổi generator version, có thể tạo diff lớn dù contract không đổi; cần phân biệt generator change với API change.

## 24. Documentation và API portal

Từ endpoint DSL có thể sinh tài liệu:
- API overview.
- Endpoint list.
- Request/response schemas.
- Authentication guide.
- Error catalog.
- Examples.
- Version history.
- Deprecation notices.
- Rate limit policy.

Tài liệu cần được sinh từ cùng contract model với code generation để tránh drift.

### 24.1. Try-it-out

API portal có thể cho người dùng thử request. Cần:
- Dùng environment phù hợp.
- Không lộ token.
- Cảnh báo operation có side effect.
- Giới hạn quyền.
- Redact response nhạy cảm.
- Có cơ chế reset dữ liệu test.

### 24.2. Documentation completeness

Có thể đặt policy yêu cầu endpoint public có summary, description, examples, auth requirements và error responses. Thiếu thông tin có thể là warning hoặc release blocker tùy mức độ.

## 25. Những sai lầm thường gặp

1. **Chỉ mô tả method và path:** client không biết request/response contract.
2. **Không có operation ID ổn định:** generated SDK đổi tên method ngoài ý muốn.
3. **Không phân biệt required và nullable:** client gửi hoặc bỏ field sai semantics.
4. **Không mô tả parameter serialization:** array/object query được encode khác nhau.
5. **Bỏ qua error contract:** client phải parse message không ổn định.
6. **Dùng một schema cho mọi success response:** không thể hiện 201, 202, 204 hoặc 206 chính xác.
7. **Không định nghĩa idempotency:** retry có thể tạo side effect trùng.
8. **Security chỉ ghi ở tài liệu:** runtime không enforce policy.
9. **Không kiểm tra route ambiguity:** request đi nhầm handler.
10. **Để handler tự quyết contract:** docs, client và server bị drift.
11. **Không version schema:** thay đổi component làm vỡ nhiều endpoint.
12. **Examples không validate:** tài liệu không chạy được.
13. **Dùng raw URL làm metric label:** cardinality tăng không kiểm soát.
14. **Lộ secret trong examples/logs:** dữ liệu nhạy cảm bị phát tán.
15. **Coi OpenAPI là implementation:** contract không được bảo đảm ở runtime.
16. **Không có deprecation policy:** client không có lộ trình migration.

## 26. Quy trình thiết kế và triển khai endpoint DSL

Một quy trình thực tế:

1. **Xác định API boundary:** service, namespace, version và server environments.
2. **Thiết kế resource và route:** method, path, naming và route specificity.
3. **Định nghĩa operation identity:** operationId ổn định, tags và description.
4. **Mô tả parameters:** path, query, header, cookie, type và serialization.
5. **Mô tả request body:** media type, schema, required/nullable và validation.
6. **Mô tả responses:** status, headers, content type, body và examples.
7. **Định nghĩa error catalog:** HTTP status, domain code, retryability và safe details.
8. **Khai báo security:** authentication schemes, scopes, inheritance và public endpoints.
9. **Định nghĩa behavior:** idempotency, caching, pagination, async operation và webhook semantics.
10. **Quản lý version:** compatibility, deprecation và sunset.
11. **Resolve reusable components:** schema, parameters, responses và security schemes.
12. **Validate contract:** syntax, semantic, route overlap, schema và policy.
13. **Sinh artifacts:** OpenAPI, docs, SDK, server stubs và mock server.
14. **Bind runtime handlers:** routing, middleware, request validation và response enforcement.
15. **Tích hợp observability:** operation IDs, logs, metrics và traces.
16. **Kiểm thử:** contract, compatibility, security, examples và runtime conformance.
17. **Review và publish:** version contract, release notes và migration guide.

## 27. Kết luận

Mô tả endpoint trong DSL API là cách khai báo hợp đồng giao tiếp giữa client và server bằng một mô hình có cấu trúc, có thể kiểm tra và sinh tự động. Một endpoint đầy đủ cần xác định method, path, operation identity, parameters, request body, response status/schema, error contract, security và các hành vi như idempotency, pagination, caching hoặc asynchronous processing.

DSL endpoint có giá trị khi cùng một contract model được dùng để sinh OpenAPI, tài liệu, SDK, server routing và contract tests. Điều đó đòi hỏi schema và semantics rõ ràng, validation nhiều tầng, versioning có kiểm soát, runtime enforcement và bảo vệ dữ liệu. Khi endpoint được mô tả nhất quán từ thiết kế đến vận hành, client và server có thể phát triển độc lập hơn mà vẫn giữ được khả năng tương thích.

