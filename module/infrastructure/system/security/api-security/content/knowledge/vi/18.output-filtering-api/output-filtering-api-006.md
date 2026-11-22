# Consistent error envelope

Một API an toàn cần có hợp đồng lỗi nhất quán như hợp đồng response thành công. Khi request thất bại, client cần biết request bị từ chối vì dữ liệu không hợp lệ, thiếu xác thực, không đủ quyền, xung đột trạng thái, vượt giới hạn hay lỗi tạm thời của dịch vụ. Nếu mỗi endpoint trả một cấu trúc khác nhau, client khó xử lý đúng; nếu response lỗi chứa stack trace, câu SQL, tên service nội bộ hoặc dữ liệu nhạy cảm, hệ thống lại vô tình mở thêm kênh rò rỉ thông tin.

**Error envelope** là cấu trúc response chuẩn hóa cho lỗi. Nó cung cấp các trường ổn định để client phân loại và xử lý lỗi, đồng thời giữ thông tin kỹ thuật chi tiết trong log nội bộ. Một envelope tốt thống nhất cách biểu diễn lỗi giữa các endpoint, dùng HTTP status code đúng ngữ nghĩa, có mã lỗi máy đọc được, có correlation ID để tra cứu và chỉ tiết lộ thông tin mà caller được phép biết.

Với HTTP API, có thể dùng RFC 9457 Problem Details (`application/problem+json`) làm nền tảng. API có thể bổ sung các extension member như `code`, `traceId` hoặc danh sách lỗi validation, nhưng cần công bố schema và giữ chúng ổn định.

## 1. Vì sao cần một error envelope thống nhất?

Giả sử cùng một lỗi validation nhưng các endpoint trả về những cấu trúc khác nhau:

```json
{ "error": "Invalid input" }
```

```json
{ "message": "quantity must be positive", "status": 400 }
```

```json
{ "success": false, "errors": [{ "field": "quantity" }] }
```

Client phải viết logic riêng cho từng endpoint và có thể bỏ sót trường hợp. Một SDK khó biết trường nào chứa mã lỗi, trường nào chỉ là thông báo cho người dùng, và khi nào nên retry.

Một error envelope thống nhất giúp:

- Client và SDK phân loại lỗi bằng status code và error code ổn định.
- UI hiển thị thông báo phù hợp mà không phải phân tích chuỗi exception.
- Client biết lỗi nào cần sửa request, lỗi nào cần đăng nhập lại, lỗi nào có thể retry.
- Support và vận hành tra cứu request bằng correlation/trace ID.
- Gateway, backend và các service trả lỗi theo một hợp đồng nhất quán.
- API tránh đưa chi tiết triển khai hoặc dữ liệu nhạy cảm vào response.

Envelope chỉ chuẩn hóa cách diễn đạt lỗi. Nó không thay thế authorization, validation, logging hoặc cơ chế xử lý sự cố.

## 2. Chọn RFC 9457 Problem Details làm nền tảng

RFC 9457 định nghĩa định dạng Problem Details cho HTTP API. Response thường dùng media type `application/problem+json` và có các member chuẩn:

| Member | Ý nghĩa | Lưu ý |
|---|---|---|
| `type` | URI định danh loại vấn đề | Nên ổn định; có thể trỏ tới tài liệu giải thích lỗi |
| `title` | Tóm tắt ngắn gọn loại vấn đề | Không thay đổi theo từng occurrence nếu không cần thiết |
| `status` | HTTP status code được mô tả trong body | Phải nhất quán với status code thực tế của response |
| `detail` | Giải thích occurrence cụ thể | Chỉ chứa nội dung an toàn để gửi cho caller |
| `instance` | URI-reference định danh occurrence cụ thể | Không đưa secret hoặc dữ liệu nhạy cảm vào đây |

Các member chuẩn có thể vắng mặt tùy trường hợp. `type` không có thì được hiểu như `about:blank`; `title` khi đó thường là cụm từ ngắn tương ứng với status. RFC 9457 cũng cho phép extension member để API bổ sung dữ liệu có cấu trúc riêng.

Ví dụ response lỗi validation:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more fields do not satisfy the request rules.",
  "instance": "/api/v1/orders",
  "code": "VALIDATION_FAILED",
  "traceId": "01JQ7N8W6M5Y4K3P2R1S0T9U8V",
  "errors": [
    {
      "pointer": "/items/0/quantity",
      "code": "must_be_positive",
      "message": "Quantity must be greater than zero."
    }
  ]
}
```

`code`, `traceId` và `errors` trong ví dụ là extension member do API định nghĩa, không phải member bắt buộc của RFC 9457. Hãy mô tả chúng trong OpenAPI hoặc tài liệu hợp đồng của API. Không dùng extension tùy tiện khiến mỗi endpoint tự đặt một tên field khác nhau.

## 3. Phân biệt HTTP status với application error code

HTTP status code mô tả kết quả request ở mức giao thức. Application error code mô tả nguyên nhân nghiệp vụ cụ thể hơn.

Ví dụ, nhiều lỗi khác nhau có thể cùng dùng `409 Conflict`:

- `ORDER_ALREADY_CANCELLED`
- `DUPLICATE_EXTERNAL_REFERENCE`
- `INVENTORY_RESERVATION_CONFLICT`

Client có thể dùng status để xử lý tổng quát và dùng `code` để quyết định hành động chi tiết. Không nhét mã lỗi vào chuỗi `title` hoặc bắt client phân tích `detail`.

Nên dùng mã lỗi:

- Ổn định qua các phiên bản API trong phạm vi hợp đồng đã công bố.
- Dạng máy đọc được, ví dụ `ORDER_STATE_CONFLICT`.
- Không chứa thông tin bí mật, ID nội bộ hoặc nội dung do attacker kiểm soát.
- Có tài liệu mô tả ý nghĩa, status, khả năng retry và cách client xử lý.
- Không phụ thuộc tên exception Java hoặc cấu trúc database.

Tránh trả class name như `DataIntegrityViolationException` hoặc mã SQL làm application error code. Đây là chi tiết triển khai có thể thay đổi và có thể tiết lộ thông tin nội bộ.

## 4. Quy ước envelope cho toàn bộ API

Một quy ước thực tế có thể gồm các trường:

| Field | Bắt buộc theo hợp đồng nội bộ? | Mục đích |
|---|---|---|
| `type` | Có | Định danh loại vấn đề |
| `title` | Có | Tóm tắt lỗi |
| `status` | Có | Lặp lại HTTP status trong body |
| `detail` | Tùy lỗi | Giải thích an toàn cho caller |
| `instance` | Tùy hợp đồng | Định danh lần phát sinh lỗi |
| `code` | Nên có | Mã lỗi ổn định cho client |
| `traceId` | Nên có | Tra cứu log/trace nội bộ |
| `errors` | Chỉ lỗi validation | Danh sách lỗi theo field/parameter |

Không bắt buộc mọi lỗi phải có `errors`. Một lỗi xác thực không cần trả danh sách field; một lỗi hệ thống không nên trả `exception`, `stackTrace` hoặc `sql`.

Hãy quy định rõ:

- Media type lỗi là `application/problem+json`.
- Tên field, kiểu dữ liệu, quy tắc vắng mặt/null và giới hạn độ dài.
- Mã lỗi và status code tương ứng.
- Ngôn ngữ của `title`, `detail` và `errors[].message`.
- Cách truyền `traceId` khi client liên hệ support.
- Những extension member được phép theo từng nhóm lỗi.

Không trả một success envelope như `{ "success": false }` với HTTP `200 OK` cho mọi lỗi. Client, proxy, cache, monitoring và retry logic dựa vào status code HTTP thực tế. Body không thể sửa lại ngữ nghĩa của status line.

## 5. Chọn HTTP status code đúng ngữ nghĩa

Status code cần phản ánh nguyên nhân ở mức HTTP và được áp dụng nhất quán:

| Status | Khi nào dùng | Ví dụ |
|---|---|---|
| `400 Bad Request` | Request sai cú pháp hoặc không thể parse | JSON hỏng, query sai định dạng |
| `401 Unauthorized` | Thiếu hoặc không có credential hợp lệ | Bearer token thiếu, hết hạn hoặc sai chữ ký |
| `403 Forbidden` | Đã xác thực nhưng không được phép | Thiếu quyền chức năng hoặc policy từ chối |
| `404 Not Found` | Không tìm thấy tài nguyên hoặc cố ý che sự tồn tại | ID không tồn tại; object ngoài phạm vi theo chính sách |
| `405 Method Not Allowed` | Method không được hỗ trợ trên resource | Gửi `DELETE` tới route chỉ hỗ trợ `GET` |
| `406 Not Acceptable` | Không tạo được representation mà client chấp nhận | Client chỉ chấp nhận media type không được hỗ trợ |
| `409 Conflict` | Xung đột với trạng thái hiện tại | Đơn hàng đã hủy hoặc tham chiếu bị trùng |
| `412 Precondition Failed` | Điều kiện request không thỏa | `If-Match` không khớp ETag hiện tại |
| `413 Content Too Large` | Request body vượt giới hạn | Upload quá lớn |
| `415 Unsupported Media Type` | Content-Type không được hỗ trợ | Gửi XML vào endpoint chỉ nhận JSON |
| `422 Unprocessable Content` | Cú pháp hợp lệ nhưng nội dung không thỏa quy tắc xử lý | Số lượng âm hoặc trường không hợp lệ theo nghiệp vụ |
| `429 Too Many Requests` | Vượt rate limit hoặc quota theo hợp đồng | Gọi API quá nhanh hoặc hết quota |
| `500 Internal Server Error` | Lỗi không dự kiến ở server | Exception chưa được xử lý |
| `502 Bad Gateway` | Gateway nhận phản hồi không hợp lệ từ upstream | Backend trả response sai giao thức |
| `503 Service Unavailable` | Service tạm thời không sẵn sàng | Bảo trì hoặc quá tải |
| `504 Gateway Timeout` | Gateway không nhận được phản hồi kịp thời từ upstream | Backend quá thời gian chờ |

Một số API dùng `400` cho validation error thay vì `422`. Điều quan trọng là chọn quy ước rõ ràng, công bố trong contract và dùng nhất quán. Không dùng `200` cho lỗi nghiệp vụ chỉ để tránh xử lý exception.

### 401 và 403 không giống nhau

`401` liên quan đến xác thực: client cần cung cấp credential hợp lệ. Response thường cần header `WWW-Authenticate` theo cơ chế xác thực được dùng. `403` nghĩa là server đã hiểu danh tính nhưng từ chối hành động. Không trả thông tin chi tiết giúp attacker suy ra role, policy hoặc tài nguyên nhạy cảm.

### 404 có thể được dùng để che object

Trong một số hệ thống, trả `404` cho object không thuộc phạm vi caller giúp tránh tiết lộ object có tồn tại hay không. Nếu chọn cách này, hãy áp dụng nhất quán và tránh để body, timing hoặc metadata tiết lộ khác biệt.

## 6. Không để body mâu thuẫn với HTTP response

Nếu status line là `HTTP/1.1 403 Forbidden`, member `status` trong Problem Details cũng phải là `403`. Không trả body `status: 200` chỉ vì một lớp middleware đã tạo envelope trước khi gateway thay đổi status.

Gateway, reverse proxy và application cần phối hợp để giữ status và body đồng bộ. Nếu gateway chặn request trước khi vào backend, gateway cũng nên dùng cùng error contract hoặc một contract tương thích. Không để backend trả `application/problem+json` còn gateway trả HTML hoặc plain text ngoài dự kiến cho cùng nhóm lỗi.

Khi upstream đã trả một Problem Details hợp lệ, gateway có thể chuyển tiếp có kiểm soát nếu hợp đồng và ranh giới tin cậy cho phép. Không mù quáng chuyển tiếp body upstream chứa stack trace, hostname, token hoặc thông tin nội bộ. Với lỗi hạ tầng, gateway nên tạo lỗi công khai an toàn và ghi chi tiết vào log nội bộ.

## 7. Thiết kế validation error có cấu trúc

Validation error thường cần chỉ ra trường hoặc parameter nào không hợp lệ để client sửa request. Hãy dùng danh sách extension có schema ổn định:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/customer/email",
      "code": "invalid_format",
      "message": "Enter a valid email address."
    },
    {
      "pointer": "/items/0/quantity",
      "code": "must_be_positive",
      "message": "Quantity must be greater than zero."
    }
  ]
}
```

`pointer` có thể dùng JSON Pointer để chỉ tới field trong JSON body. Với query/path parameter, có thể dùng `location` và `name`, ví dụ `{ "location": "query", "name": "page", "code": "must_be_non_negative" }`. Không trộn lẫn hai cách biểu diễn mà không mô tả schema.

Validation response không nên phản chiếu toàn bộ giá trị sai mà client gửi. Ví dụ, không trả password, token, số thẻ hoặc dữ liệu cá nhân trong `rejectedValue`. Thông báo nên hướng dẫn cách sửa nhưng không tiết lộ quy tắc nội bộ nhạy cảm hoặc giá trị được lưu trong hệ thống.

Một request có nhiều lỗi có thể trả tối đa một số lượng lỗi nhất định để tránh response quá lớn. Nếu cần, nhóm lỗi theo field hoặc chỉ trả các lỗi đầu tiên theo thứ tự ổn định. Không để một body lớn tạo ra hàng trăm nghìn error entry.

## 8. Error code phải độc lập với exception nội bộ

Không đưa tên exception hoặc message nguyên bản từ thư viện vào response. Hãy ánh xạ exception nội bộ sang lỗi API công khai:

| Exception/tình huống nội bộ | Error code công khai | HTTP |
|---|---|---:|
| JSON parser lỗi | `MALFORMED_REQUEST` | 400 |
| Token không hợp lệ | `AUTHENTICATION_REQUIRED` | 401 |
| Policy từ chối | `ACCESS_DENIED` | 403 |
| Không tìm thấy object trong phạm vi | `RESOURCE_NOT_FOUND` | 404 |
| Optimistic lock conflict | `RESOURCE_VERSION_CONFLICT` | 409 |
| Validation thất bại | `VALIDATION_FAILED` | 422 |
| Quota hết | `QUOTA_EXCEEDED` | 429 |
| Dependency timeout | `DEPENDENCY_TIMEOUT` | 504 hoặc status phù hợp với vai trò service |
| Exception không dự kiến | `INTERNAL_ERROR` | 500 |

Ánh xạ cần dựa trên loại lỗi đã biết và ngữ cảnh, không chỉ dựa vào chuỗi message. Một `DataIntegrityViolationException` có thể là lỗi dữ liệu trùng mà API đã dự kiến, nhưng cũng có thể là lỗi constraint do bug. Không biến mọi exception database thành `409` mà chưa phân biệt nguyên nhân.

## 9. Không tiết lộ thông tin nội bộ trong error response

Response lỗi là output của API và phải chịu cùng nguyên tắc output filtering như response thành công. Không gửi cho client:

- Stack trace, class name, package Java hoặc tên framework.
- SQL query, tên bảng/cột, constraint và thông tin database.
- Đường dẫn file, thư mục triển khai, hostname, IP nội bộ hoặc topology service.
- Access token, API key, cookie, session ID hoặc secret.
- Nội dung exception từ downstream có chứa dữ liệu nhạy cảm.
- Payload đầy đủ, password, số thẻ, MFA code hoặc thông tin cá nhân không cần thiết.
- Chi tiết policy có thể giúp attacker dò quyền hoặc né kiểm soát.

Ví dụ response không an toàn:

```json
{
  "error": "org.springframework.dao.DataIntegrityViolationException",
  "message": "duplicate key value violates unique constraint users_email_key",
  "sql": "insert into users ...",
  "stackTrace": "at com.company.user.UserRepository.save(...) ..."
}
```

Response an toàn hơn:

```json
{
  "type": "https://api.example.com/problems/conflict",
  "title": "Resource conflict",
  "status": 409,
  "code": "EMAIL_ALREADY_REGISTERED",
  "detail": "An account with this email address already exists.",
  "traceId": "01JQ7N8W6M5Y4K3P2R1S0T9U8V"
}
```

Thông báo thứ hai vẫn cần xem xét chính sách enumeration. Với endpoint đăng nhập hoặc đăng ký, việc xác nhận email đã tồn tại có thể tạo điều kiện dò tài khoản; tùy threat model, API có thể trả thông báo tổng quát hơn.

## 10. Tách thông tin công khai và thông tin nội bộ

Một exception có thể chứa thông tin hữu ích cho developer nhưng không an toàn cho caller. Nên tách hai luồng:

| Kênh | Nội dung phù hợp |
|---|---|
| HTTP error response | Status, problem type, error code, thông báo an toàn, trace ID |
| Application log | Exception, stack trace, dependency, nguyên nhân kỹ thuật đã được kiểm soát |
| Security audit | Actor, action, resource, policy decision, thời điểm và correlation ID |
| Metrics | Error code/status được chuẩn hóa, route template, service và latency |
| Trace | Span lỗi, dependency, timing và metadata đã lọc secret |

Không ghi raw request body hoặc toàn bộ header vào log chỉ để giữ ngữ cảnh. Nếu cần ghi payload phục vụ điều tra, phải che dữ liệu nhạy cảm và áp dụng quyền truy cập, retention phù hợp. Log nội bộ cũng là tài sản cần bảo vệ.

## 11. Correlation ID và trace ID

Client cần một mã để gửi cho support khi gặp lỗi. `traceId` hoặc `requestId` giúp nối response với log và distributed trace. Mã này nên là giá trị opaque, không chứa username, email, tenant secret hoặc thông tin có ý nghĩa nghiệp vụ nhạy cảm.

Một số nguyên tắc:

- Gateway hoặc service tin cậy tạo request ID nếu request chưa có ID hợp lệ.
- Nếu chấp nhận ID do client gửi, hãy giới hạn độ dài/ký tự, chuẩn hóa và tránh log injection.
- Dùng W3C Trace Context (`traceparent`) khi cần trace xuyên nhiều service.
- Không dùng correlation ID làm credential, session ID hoặc bằng chứng phân quyền.
- Trả cùng trace ID trong response header và error envelope nếu contract quy định.
- Ghi ID vào log có cấu trúc để tra cứu nhanh.

Ví dụ:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-Id: 01JQ7N8W6M5Y4K3P2R1S0T9U8V

{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal Server Error",
  "status": 500,
  "code": "INTERNAL_ERROR",
  "detail": "The request could not be completed.",
  "traceId": "01JQ7N8W6M5Y4K3P2R1S0T9U8V"
}
```

Client cung cấp trace ID cho support; chỉ người có quyền mới được tra cứu log và chi tiết nội bộ tương ứng.

## 12. Ngôn ngữ và khả năng hiển thị thông báo

`title` và `detail` hướng tới con người, trong khi `type` và `code` hướng tới máy. Client không nên dựa vào chuỗi `detail` để quyết định logic vì nội dung có thể được bản địa hóa hoặc cải thiện.

Nếu API hỗ trợ đa ngôn ngữ, quy định cách chọn ngôn ngữ qua `Accept-Language` và cách phản ánh cache variation. Error code phải giữ nguyên giữa các ngôn ngữ. Ví dụ:

```json
{
  "status": 422,
  "code": "VALIDATION_FAILED",
  "title": "Dữ liệu gửi lên chưa hợp lệ",
  "detail": "Vui lòng kiểm tra các trường được liệt kê trong errors."
}
```

Không dịch hoặc đổi mã lỗi theo ngôn ngữ. Nếu response được cache theo ngôn ngữ, cần cấu hình `Vary: Accept-Language` và cache policy phù hợp. Với lỗi chứa thông tin cá nhân hoặc dữ liệu xác thực, thường nên dùng `Cache-Control: no-store`.

## 13. Retry guidance và các header HTTP cần giữ

Client cần phân biệt lỗi có thể retry và lỗi cần sửa request hoặc quyền. Không phải mọi lỗi `5xx` đều an toàn để retry nếu thao tác có side effect và chưa có idempotency.

| Tình huống | Hướng dẫn cho client |
|---|---|
| `400`, `422` | Sửa request; không retry nguyên trạng |
| `401` | Làm mới hoặc cung cấp credential hợp lệ theo cơ chế xác thực |
| `403` | Không retry tự động; cần quyền phù hợp hoặc quy trình hỗ trợ |
| `404` | Kiểm tra URI/ID hoặc phạm vi truy cập theo contract |
| `409` | Tải trạng thái mới hoặc xử lý xung đột nghiệp vụ |
| `412` | Lấy representation/ETag mới trước khi thử lại |
| `429` | Tôn trọng `Retry-After` và giới hạn đã công bố |
| `502`, `503`, `504` | Có thể retry có backoff nếu thao tác an toàn/idempotent hoặc có idempotency key |
| `500` | Không retry liên tục; dùng backoff và trace ID nếu contract cho phép |

Giữ các header có ý nghĩa giao thức:

- `WWW-Authenticate` cho challenge xác thực khi trả `401`.
- `Allow` khi trả `405`.
- `Retry-After` khi có thể chỉ ra thời điểm thử lại.
- Header RateLimit theo contract khi trả `429`.
- `ETag` hoặc metadata phiên bản khi hỗ trợ conditional request.

Không chỉ đặt nội dung các header này trong JSON body. Client, proxy và HTTP library đọc chúng từ response header.

## 14. Xử lý lỗi từ downstream service

Trong kiến trúc nhiều service, lỗi có thể phát sinh ở dependency. Không nên chuyển nguyên văn body lỗi của downstream cho client nếu nó chứa hostname, stack trace, mã nội bộ hoặc dữ liệu khác trust boundary.

Gateway hoặc service trung gian cần:

1. Phân loại lỗi downstream: timeout, unavailable, invalid response, business rejection hay lỗi xác thực giữa service.
2. Ánh xạ sang status và error code công khai phù hợp với vai trò của API hiện tại.
3. Tạo trace/correlation context để nối các span.
4. Giữ nguyên lỗi nghiệp vụ đã được phép công khai nếu contract quy định và nội dung đã được lọc.
5. Không lộ credential, URL nội bộ, tên cluster, IP private hoặc body thô của upstream.
6. Không biến lỗi timeout thành lỗi validation hoặc `400` khiến client sửa request vô ích.

Ví dụ, nếu `orders-api` gọi `inventory-service` và dependency timeout, API có thể trả `503` hoặc `504` theo kiến trúc và hợp đồng. Body có thể dùng `DEPENDENCY_UNAVAILABLE` hoặc `DEPENDENCY_TIMEOUT`; tên service nội bộ được giữ trong log/trace, không nhất thiết gửi cho client.

## 15. Ví dụ triển khai với Spring Boot 3 và ProblemDetail

Spring Framework 6/Spring Boot 3 hỗ trợ `ProblemDetail` cho RFC 9457. Có thể tạo một `@RestControllerAdvice` để ánh xạ exception sang cấu trúc thống nhất.

Ví dụ lỗi nghiệp vụ:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderStateConflictException.class)
    public ResponseEntity<ProblemDetail> handleOrderConflict(
            OrderStateConflictException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The order cannot be changed in its current state."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/order-state-conflict"));
        problem.setTitle("Order state conflict");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_STATE_CONFLICT");
        problem.setProperty("traceId", currentTraceId());

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

Đây là code minh họa; cần các import và dependency Spring phù hợp. `currentTraceId()` là hàm tích hợp với tracing/MDC của ứng dụng, không lấy trace ID nhạy cảm hoặc tùy ý từ body. `request.getRequestURI()` chỉ nên dùng làm `instance` nếu URI không chứa query string hoặc dữ liệu nhạy cảm; có thể thay bằng một URI occurrence opaque do server tạo.

### Xử lý validation error

```java
@ExceptionHandler(MethodArgumentNotValidException.class)
public ResponseEntity<ProblemDetail> handleValidation(
        MethodArgumentNotValidException ex) {

    List<Map<String, String>> errors = ex.getBindingResult()
        .getFieldErrors()
        .stream()
        .map(error -> Map.of(
            "field", error.getField(),
            "code", "invalid_value",
            "message", "The supplied value is invalid."
        ))
        .toList();

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.UNPROCESSABLE_ENTITY,
        "One or more fields do not satisfy the request rules."
    );
    problem.setType(URI.create(
        "https://api.example.com/problems/validation-error"));
    problem.setTitle("Request validation failed");
    problem.setProperty("code", "VALIDATION_FAILED");
    problem.setProperty("traceId", currentTraceId());
    problem.setProperty("errors", errors);

    return ResponseEntity.unprocessableEntity()
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
}
```

Không đưa `error.getRejectedValue()` vào response vì nó có thể là password, token hoặc dữ liệu cá nhân. Trong hệ thống thật, hãy ánh xạ validator code sang mã ổn định thay vì dùng một mã chung cho mọi lỗi. Nếu API chọn `400` cho validation, hãy dùng status đó nhất quán với hợp đồng.

### Xử lý lỗi không dự kiến

```java
@ExceptionHandler(Exception.class)
public ResponseEntity<ProblemDetail> handleUnexpected(
        Exception ex,
        HttpServletRequest request) {

    String traceId = currentTraceId();
    log.error("Unhandled API error; traceId={}", traceId, ex);

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.INTERNAL_SERVER_ERROR,
        "The request could not be completed."
    );
    problem.setType(URI.create(
        "https://api.example.com/problems/internal-error"));
    problem.setTitle("Internal Server Error");
    problem.setInstance(URI.create("/problems/" + traceId));
    problem.setProperty("code", "INTERNAL_ERROR");
    problem.setProperty("traceId", traceId);

    return ResponseEntity.internalServerError()
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
}
```

Log nội bộ giữ exception và stack trace; response chỉ chứa thông tin an toàn. Trong triển khai thật, cần bảo đảm exception handler không nuốt các exception framework cần xử lý riêng, không ghi log cùng một exception nhiều lần và không để `traceId` rỗng khi hệ thống có tracing.

## 16. Lỗi phát sinh trước controller trong Spring Security

Không phải mọi lỗi đều đi qua `@RestControllerAdvice`. Authentication filter, authorization filter, servlet container, reverse proxy hoặc gateway có thể từ chối request trước khi controller được gọi.

Với Spring Security, cần cấu hình `AuthenticationEntryPoint` để tạo response `401` và `AccessDeniedHandler` để tạo response `403` theo cùng error contract. Cũng cần xem lỗi CSRF, CORS, request size, method không hỗ trợ và lỗi từ gateway có được chuẩn hóa phù hợp hay không.

Nếu chỉ cấu hình `@RestControllerAdvice`, response từ security filter có thể vẫn là body mặc định hoặc HTML, làm API thiếu nhất quán. Hãy kiểm thử cả request bị chặn trước controller và request đi vào controller rồi mới phát sinh exception.

## 17. API Gateway và lỗi từ lớp edge

Gateway có thể tạo lỗi khi route không tồn tại, token không hợp lệ, vượt rate limit, upstream timeout hoặc request vượt giới hạn. Nếu backend dùng Problem Details nhưng gateway trả một JSON khác, client vẫn phải xử lý nhiều format.

Hãy thống nhất:

- Gateway và backend dùng cùng naming convention cho `type`, `code`, `traceId` và error schema.
- Gateway tạo trace ID hoặc chuyển tiếp trace context đã được kiểm tra.
- Lỗi do gateway tạo có type/code riêng, không giả thành lỗi nghiệp vụ của backend.
- Không chuyển tiếp stack trace hoặc body lỗi thô từ upstream.
- Status code và header giao thức được giữ đúng.
- Health check và lỗi hạ tầng không tiết lộ topology nội bộ.

## 18. Error envelope trong các giao thức khác

Không phải mọi API đều dùng HTTP JSON. Nếu hệ thống có gRPC, GraphQL hoặc WebSocket, cần ánh xạ lỗi theo cơ chế của giao thức và giữ cùng taxonomy nội bộ.

| Giao thức | Cơ chế lỗi | Điều cần thống nhất |
|---|---|---|
| REST/HTTP | Status code và Problem Details | Status, type, code, trace ID, validation errors |
| gRPC | Status code và status details/trailers | Mapping lỗi nội bộ sang canonical status; không đưa secret vào details |
| GraphQL | `errors` array và `extensions` | Error code ổn định; không lộ stack trace; xử lý partial data theo contract |
| WebSocket | Application error message hoặc close code | Schema message, mã lỗi và cách đóng kết nối rõ ràng |
| Message API | Dead-letter, negative acknowledgment hoặc error event | Phân biệt lỗi retryable, poison message và lỗi nghiệp vụ |

Không ép tất cả giao thức dùng cùng một JSON body. Hãy thống nhất taxonomy, mức độ công khai và cách truy vết, sau đó biểu diễn theo chuẩn của từng giao thức.

## 19. Kiểm thử error contract

Test cần xác minh cả HTTP status, media type, body schema, header và nội dung không được phép xuất hiện.

| Nhóm test | Ca kiểm thử |
|---|---|
| Schema | Lỗi có đúng `type`, `title`, `status`, `code` và `traceId` theo contract |
| Status | Body `status` khớp HTTP status thực tế |
| Validation | Có danh sách lỗi field/parameter; không có rejected value nhạy cảm |
| Authentication | `401` có `WWW-Authenticate` phù hợp và envelope nhất quán |
| Authorization | `403` hoặc `404` theo policy; không tiết lộ object ngoài phạm vi |
| Method/media | `405` giữ `Allow`; `415`/`406` có lỗi phù hợp |
| Rate/quota | `429` giữ `Retry-After` và metadata limit theo contract |
| Unexpected error | `500` không có stack trace, SQL, hostname hoặc class name |
| Gateway | Lỗi route, rate limit và upstream timeout cùng schema đã công bố |
| Localization | `code` không đổi khi `title/detail` đổi ngôn ngữ |
| Correlation | `traceId` trong body/header khớp log/trace và không thể dùng làm credential |
| Caching | Error nhạy cảm không bị cache ngoài ý muốn |

Ví dụ kiểm tra bằng Spring MockMvc:

```java
mockMvc.perform(post("/api/v1/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"items\":[{\"quantity\":0}]}"))
    .andExpect(status().isUnprocessableEntity())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.type").value(
        "https://api.example.com/problems/validation-error"))
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.errors").isArray())
    .andExpect(jsonPath("$.stackTrace").doesNotExist());
```

Test thực tế cần cấu hình đúng validation, security filter và exception handler của ứng dụng. Nên có contract test cho gateway và backend để phát hiện schema drift khi một service thay đổi.

## 20. Versioning và tương thích ngược của error contract

Client có thể phụ thuộc vào error code và cấu trúc `errors`. Vì vậy, thay đổi error envelope cũng cần quản lý như thay đổi API contract.

Thông thường có thể:

- Thêm extension member tùy chọn mà client cũ có thể bỏ qua.
- Giữ nguyên ý nghĩa và spelling của error code đã công bố.
- Không đổi status code của một lỗi theo cách làm thay đổi hành vi retry mà không có đánh giá tương thích.
- Không đổi kiểu dữ liệu của field hoặc chuyển field từ optional sang required một cách âm thầm.
- Deprecate mã lỗi cũ theo chính sách versioning và thông báo cho client.
- Dùng OpenAPI schema và contract test để phát hiện thay đổi ngoài ý muốn.

Client nên bỏ qua extension member chưa biết thay vì lỗi parse toàn bộ response, miễn là contract cho phép. Server cũng không nên xóa field hoặc thay đổi semantics mà không có lộ trình.

## 21. Checklist thiết kế consistent error envelope

- [ ] Tất cả lỗi HTTP dùng media type và schema thống nhất, ví dụ `application/problem+json`.
- [ ] `type`, `title`, `status`, `detail` và `instance` được dùng đúng ý nghĩa RFC 9457.
- [ ] Body `status` khớp status line HTTP.
- [ ] Application error code ổn định, máy đọc được và độc lập với exception nội bộ.
- [ ] Validation errors có cấu trúc rõ, giới hạn số lượng và không phản chiếu dữ liệu nhạy cảm.
- [ ] `401`, `403`, `404`, `409`, `422`, `429` và `5xx` được ánh xạ theo quy ước đã công bố.
- [ ] Các header giao thức như `WWW-Authenticate`, `Allow`, `Retry-After` được giữ đúng.
- [ ] Response không chứa stack trace, SQL, hostname, token, secret hoặc thông tin hạ tầng.
- [ ] Trace/correlation ID có thể tra cứu nội bộ nhưng không chứa dữ liệu cá nhân và không được dùng làm credential.
- [ ] Log, audit, metric và trace giữ chi tiết nội bộ đã được kiểm soát.
- [ ] Gateway, security filter, controller và downstream mapping tuân theo contract.
- [ ] Retry guidance phân biệt lỗi có thể retry và lỗi cần sửa request/quyền.
- [ ] Error contract được mô tả trong OpenAPI và kiểm thử tương thích ngược.

## Kết luận

Consistent error envelope giúp API trả lỗi có cấu trúc, dễ xử lý và an toàn. Dùng HTTP status đúng ngữ nghĩa, RFC 9457 Problem Details, application error code ổn định và trace ID để client cùng đội vận hành hiểu điều gì đã xảy ra. Validation error cần chỉ rõ field theo schema nhưng không phản chiếu secret; lỗi nội bộ cần được ghi log có kiểm soát thay vì đưa stack trace hoặc chi tiết hạ tầng vào response. Khi gateway, security filter và backend cùng tuân thủ một contract được kiểm thử và version hóa, client có thể xử lý lỗi nhất quán mà không làm tăng nguy cơ lộ thông tin.
