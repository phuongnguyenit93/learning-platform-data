# Không lộ stack trace, SQL hoặc service topology

Một API có thể xác thực và phân quyền đúng nhưng vẫn tiết lộ thông tin nội bộ qua response lỗi. Ví dụ, một request sai làm server trả stack trace chứa đường dẫn source code; một truy vấn thất bại làm lộ câu SQL, tên bảng hoặc database host; một lỗi downstream trả hostname của service nội bộ, tên namespace Kubernetes hoặc phiên bản framework. Những chi tiết này giúp người ngoài hiểu cấu trúc triển khai và tìm điểm yếu tiếp theo.

Output filtering là việc kiểm soát dữ liệu mà API đưa ra ngoài, bao gồm response thành công, response lỗi, header, metadata, file export và thông tin chẩn đoán. Với lỗi, server cần trả đủ thông tin để client hiểu cách xử lý nhưng giữ chi tiết kỹ thuật cho kênh quan sát nội bộ có kiểm soát.

Trong module `SECURITY_API_SECURITY`, bảo mật API được thiết kế theo từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. Vì vậy, không thể chỉ lọc field của response thành công rồi để exception handler trả nguyên thông báo từ framework hoặc database. Mọi đường phản hồi đều phải có hợp đồng rõ ràng, phân loại lỗi nhất quán và giới hạn thông tin theo đối tượng nhận.

## Mục tiêu học tập

Sau bài này, người học có thể:

- Nhận diện rò rỉ thông tin qua stack trace, SQL error, hostname, header và metadata triển khai.
- Phân biệt thông tin lỗi cần thiết cho client với chẩn đoán chỉ dành cho vận hành.
- Thiết kế error contract ổn định bằng Problem Details hoặc schema tương đương.
- Ánh xạ exception sang HTTP status và mã lỗi nghiệp vụ mà không làm lộ exception message.
- Cấu hình Spring để không trả stack trace, SQL, đường dẫn source hoặc chi tiết downstream.
- Ghi log/trace nội bộ có kiểm soát, che secret và dữ liệu cá nhân.
- Kiểm thử response, header, validation error, GraphQL/gRPC và các đường lỗi ít gặp.

## 1. Output filtering bao gồm những gì?

Output của API không chỉ là JSON body. Thông tin có thể rò rỉ qua nhiều kênh:

| Kênh | Ví dụ thông tin bị lộ | Rủi ro |
|---|---|---|
| Error body | Stack trace, class name, file path, SQL statement | Tiết lộ implementation và cấu trúc dữ liệu |
| Error message | Database host, tên bảng, internal URL, exception từ provider | Giúp dò topology và dependency |
| HTTP header | `Server`, `X-Powered-By`, debug header, proxy metadata | Tiết lộ server, framework hoặc hạ tầng |
| Validation response | Giá trị input bị từ chối, constraint nội bộ, regex hoặc tên entity | Lộ dữ liệu người dùng và quy tắc triển khai |
| Health/debug endpoint | Environment variables, connection status chi tiết, bean/configuration list | Tiết lộ trạng thái và cấu hình hệ thống |
| GraphQL/gRPC error | Resolver path, exception detail, stack hoặc metadata | Lộ đường xử lý và service phía sau |
| File/export | Log, report hoặc file chứa internal ID và ghi chú vận hành | Rò rỉ dữ liệu ngoài response chính |
| Redirect/URL | Internal hostname hoặc địa chỉ callback | Tiết lộ topology hoặc đích mạng |

Output filtering cần áp dụng cho cả response thành công và lỗi. Bài này tập trung vào ba nhóm thông tin thường bị lộ trong lỗi API: stack trace, SQL/database details và service topology.

## 2. Vì sao không nên trả chi tiết kỹ thuật cho client?

### 2.1. Stack trace tiết lộ implementation

Stack trace thường chứa:

- Tên package, class, method và framework đang sử dụng.
- Đường dẫn source hoặc thư mục build trên máy chủ.
- Tên module, thư viện, phiên bản và thứ tự gọi hàm.
- Tên controller, service, repository hoặc middleware.
- Một phần dữ liệu exception có thể chứa input hoặc thông tin nghiệp vụ.

Khi attacker biết framework và phiên bản, họ có thể tập trung tìm lỗ hổng tương ứng. Đường dẫn như `/opt/apps/customer-api/releases/2026-11/...` còn có thể tiết lộ cách triển khai, tên dịch vụ và cấu trúc thư mục.

Stack trace có giá trị cho developer và operator, nhưng không cần thiết để người dùng cuối xử lý lỗi. Hãy ghi nó vào log/trace nội bộ được bảo vệ và trả một mã lỗi công khai cùng correlation ID.

### 2.2. SQL error tiết lộ schema và dữ liệu

Thông báo từ database có thể chứa:

- Câu SQL, tên schema, bảng, cột và constraint.
- Database engine, phiên bản driver hoặc dialect.
- Hostname, port, database name và tên tài khoản kết nối.
- Giá trị tham số truy vấn, đôi khi chứa email, token hoặc dữ liệu cá nhân.
- Chi tiết constraint giúp suy đoán cấu trúc dữ liệu và trạng thái record.

Ví dụ một lỗi unique constraint có thể tiết lộ tên bảng `customer_payment_methods` và cột `provider_reference`. Một lỗi cú pháp SQL có thể làm lộ tên cột hoặc đoạn query do ứng dụng tạo. Client thường chỉ cần biết dữ liệu xung đột hoặc request không hợp lệ; họ không cần biết database đang dùng PostgreSQL hay tên constraint nội bộ.

### 2.3. Service topology tiết lộ đường đi nội bộ

Topology có thể lộ qua error message, header và response của dependency:

- `http://payment-service.prod.svc.cluster.local:8080`.
- Tên namespace, pod, node, cloud account hoặc internal load balancer.
- Tên queue, topic, database, cache và service discovery record.
- Tên nhà cung cấp, internal API path và phiên bản protocol.
- Sơ đồ gọi giữa gateway, service, worker và database.

Thông tin này có thể giúp attacker lập bản đồ hệ thống, xác định điểm tập trung quyền hoặc nhắm vào service chưa được bảo vệ tốt. Không nên trả nguyên thông báo lỗi từ HTTP client, message broker hoặc service downstream.

### 2.4. Error detail có thể trở thành oracle

Hai response khác nhau quá chi tiết có thể giúp attacker suy luận resource tồn tại, tài khoản có hợp lệ, field nào bị ràng buộc hoặc trạng thái nghiệp vụ hiện tại. Ví dụ, response “email tồn tại trong tenant khác” tiết lộ dữ liệu; response “user không tồn tại” khác hẳn “password sai” có thể hỗ trợ enumeration.

Hãy thiết kế thông điệp nhất quán theo threat model. Khi cần che sự tồn tại của object, có thể trả cùng một response `404` cho trường hợp không tồn tại và không được phép xem. Tuy nhiên, quyết định này phải nhất quán và không được làm sai semantics của client hợp lệ.

## 3. Nguyên tắc thiết kế error response an toàn

### 3.1. Trả thông tin hữu ích, không trả chi tiết triển khai

Một error response tốt nên cho client biết:

- Request thất bại ở mức nào: cú pháp, validation, authentication, authorization, conflict, quota hay lỗi hệ thống.
- Mã lỗi ổn định để client xử lý bằng code.
- Thông điệp ngắn, không chứa dữ liệu nhạy cảm hoặc tên thành phần nội bộ.
- Correlation ID hoặc request ID để bộ phận hỗ trợ tìm log nội bộ.
- Hướng khắc phục an toàn nếu client có thể tự xử lý, ví dụ sửa field hoặc thử lại sau thời gian quy định.

Không nên trả:

- Stack trace, exception class, cause chain hoặc source path.
- SQL statement, bind parameter, tên bảng/cột/constraint nội bộ.
- Internal hostname, IP, port, URL, namespace hoặc service discovery data.
- Access token, API key, cookie, session ID hoặc secret.
- Environment variable, cấu hình database, file system path hoặc command line.
- Raw request payload hoặc giá trị field nhạy cảm bị từ chối.

### 3.2. Dùng mã lỗi ổn định

Client nên dựa vào mã lỗi thay vì phân tích chuỗi message. Ví dụ:

| Code | Ý nghĩa dành cho client | Ví dụ xử lý |
|---|---|---|
| `VALIDATION_FAILED` | Một hoặc nhiều field không hợp lệ | Hiển thị lỗi theo field và yêu cầu sửa |
| `AUTHENTICATION_REQUIRED` | Thiếu hoặc không xác thực được credential | Chuyển tới flow đăng nhập phù hợp |
| `ACCESS_DENIED` | Principal không được phép thực hiện action | Dừng thao tác và hiển thị thông báo phù hợp |
| `RESOURCE_NOT_FOUND` | Resource không tồn tại hoặc không được phép nhìn thấy theo policy | Hiển thị trạng thái không tìm thấy |
| `STATE_CONFLICT` | Thao tác không phù hợp với trạng thái hiện tại | Tải lại dữ liệu hoặc yêu cầu hành động khác |
| `RATE_LIMIT_EXCEEDED` | Vượt giới hạn request/quota | Tôn trọng `Retry-After` |
| `DEPENDENCY_UNAVAILABLE` | Phụ thuộc tạm thời không sẵn sàng | Retry có backoff nếu operation an toàn |
| `INTERNAL_ERROR` | Lỗi không dự kiến | Hiển thị thông báo chung và cung cấp correlation ID |

Không đưa tên exception hoặc tên constraint vào `code`. Code cần được version hóa như một phần của API contract; message có thể được bản địa hóa hoặc thay đổi mà không phá client.

### 3.3. Dùng Problem Details

Với HTTP API, có thể dùng định dạng Problem Details theo RFC 9457 (`application/problem+json`). Ví dụ response an toàn:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-ID: req_01JEXAMPLE

{
  "type": "https://api.example.com/problems/state-conflict",
  "title": "Request conflicts with the current state",
  "status": 409,
  "detail": "The order cannot be cancelled in its current state.",
  "instance": "/api/orders/ord-1001/cancel",
  "code": "STATE_CONFLICT",
  "requestId": "req_01JEXAMPLE"
}
```

`type`, `title`, `status`, `detail` và `instance` có semantics theo Problem Details. Extension như `code` hoặc `requestId` cần được định nghĩa trong contract. `instance` nên là URI tương đối hoặc định danh an toàn; không đưa internal host, query chứa secret hoặc đường dẫn file vào đó.

Không đưa exception message vào `detail`. Detail nên mô tả điều client cần biết, không mô tả cách server thất bại bên trong.

## 4. Ánh xạ exception sang HTTP status

Không nên để framework tự chọn status code dựa trên exception bất kỳ hoặc trả tất cả lỗi thành `200`. Hãy xác định mapping rõ ràng cho loại lỗi đã biết và có fallback an toàn cho lỗi không dự kiến.

| Tình huống | HTTP status thường dùng | Thông tin công khai |
|---|---|---|
| Request không parse được hoặc sai cấu trúc | `400 Bad Request` | Mã lỗi và mô tả cú pháp ở mức an toàn |
| Thiếu hoặc credential không hợp lệ | `401 Unauthorized` | Thông báo xác thực chung; thêm `WWW-Authenticate` phù hợp |
| Principal hợp lệ nhưng không có quyền | `403 Forbidden` | Thông báo không được phép; không nêu policy nội bộ |
| Resource không tồn tại hoặc được che giấu | `404 Not Found` | Thông báo không tìm thấy theo contract |
| Method không được hỗ trợ | `405 Method Not Allowed` | `Allow` header theo HTTP semantics |
| Trùng hoặc xung đột trạng thái nghiệp vụ | `409 Conflict` | Mã conflict ổn định và cách xử lý phù hợp |
| Payload quá lớn | `413 Content Too Large` | Giới hạn công khai nếu có thể |
| Media type không hỗ trợ | `415 Unsupported Media Type` | Content type được hỗ trợ |
| Validation nghiệp vụ không đạt | `422 Unprocessable Content` hoặc `400` theo contract | Field path và mã lỗi an toàn |
| Vượt rate limit | `429 Too Many Requests` | `Retry-After` nếu xác định được |
| Lỗi tạm thời của dependency hoặc service quá tải | `503 Service Unavailable` | Thông báo chung và hướng retry an toàn |
| Lỗi không dự kiến | `500 Internal Server Error` | Thông báo chung, correlation ID |

`401` và `403` có ý nghĩa khác nhau; `404` đôi khi được dùng để che sự tồn tại của resource. Chọn status theo semantics HTTP, security policy và hợp đồng client. Không dùng `500` cho lỗi validation đã biết vì client sẽ hiểu nhầm là lỗi server.

## 5. Không trả stack trace hoặc exception message

### 5.1. Tách public error khỏi internal diagnostic

Một exception có thể mang nhiều thông tin hữu ích cho developer nhưng không phù hợp với client. Hãy chuyển nó thành một public error object an toàn:

```text
try:
    executeUseCase()
catch knownValidationError:
    logDiagnostic(knownValidationError, requestContext)
    return publicProblem(422, "VALIDATION_FAILED")
catch knownBusinessConflict:
    logDiagnostic(knownBusinessConflict, requestContext)
    return publicProblem(409, "STATE_CONFLICT")
catch unexpectedError:
    requestId = logAndCreateCorrelationId(unexpectedError)
    return publicProblem(500, "INTERNAL_ERROR", requestId)
```

Không cần log toàn bộ exception ở mọi tầng nếu sẽ tạo log trùng lặp. Chọn một boundary chịu trách nhiệm ghi diagnostic đầy đủ; các tầng dưới có thể bổ sung context có cấu trúc. Đảm bảo exception không bị nuốt và lỗi vẫn được chuyển tới error handler.

### 5.2. Tránh trả `exception.getMessage()`

Không làm như sau:

```java
@ExceptionHandler(Exception.class)
ResponseEntity<Map<String, String>> handle(Exception ex) {
    return ResponseEntity.internalServerError()
        .body(Map.of("error", ex.getMessage()));
}
```

`ex.getMessage()` có thể chứa SQL, hostname, file path, giá trị input hoặc thông báo từ provider. Cách an toàn hơn là log exception nội bộ rồi trả mã lỗi chung:

```java
@ExceptionHandler(Exception.class)
ResponseEntity<ProblemDetail> handleUnexpected(
        Exception ex,
        HttpServletRequest request) {
    String requestId = requestIdFromTrustedContext(request);
    log.error("Unhandled API error requestId={}", requestId, ex);

    ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
    problem.setTitle("Internal server error");
    problem.setDetail("The request could not be completed.");
    problem.setProperty("code", "INTERNAL_ERROR");
    problem.setProperty("requestId", requestId);

    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
}
```

Đây là ví dụ Spring MVC rút gọn. `requestIdFromTrustedContext` cần lấy ID đã được middleware tạo hoặc xác minh; không phản chiếu nguyên một header tùy ý của client. Logger phải được cấu hình redaction và truy cập hạn chế.

### 5.3. Không dùng stack trace trong response kể cả khi debug

Development profile có thể hiển thị thêm thông tin cho developer trong môi trường local được kiểm soát, nhưng không nên có đường cấu hình dễ bật nhầm trên production. Production cần default an toàn ở code và cấu hình; không phụ thuộc vào một biến môi trường mà nếu thiếu lại bật stack trace.

Nếu cần debug production, dùng log/trace có quyền truy cập, thời hạn lưu và audit. Có thể bật diagnostic tạm thời cho một request hoặc nhóm canary qua cơ chế vận hành được kiểm soát, nhưng response công khai vẫn phải theo error contract an toàn.

## 6. Không lộ SQL và chi tiết database

### 6.1. Map database exception sang lỗi nghiệp vụ

Database exception cần được diễn giải ở lớp repository/service. Ví dụ:

- Unique constraint conflict có thể trở thành `409` nếu client có thể xử lý tình huống trùng.
- Foreign key conflict có thể là lỗi trạng thái hoặc validation tùy nghiệp vụ.
- Connection timeout hoặc database unavailable có thể trở thành `503`.
- SQL syntax error hoặc mapping bug không nên được trả như lỗi người dùng; thường là `500` và cần điều tra nội bộ.

Không trả tên constraint, tên bảng, SQLSTATE chi tiết hoặc SQL statement cho client. Nếu cần mã lỗi ổn định, map database condition sang mã nghiệp vụ do API định nghĩa.

### 6.2. Ví dụ mapping trong Spring

```java
@ExceptionHandler(DataIntegrityViolationException.class)
ResponseEntity<ProblemDetail> handleIntegrityViolation(
        DataIntegrityViolationException ex) {
    // Ghi diagnostic ở boundary nội bộ; không đưa ex.getMessage() vào response.
    log.warn("Data integrity conflict", ex);

    ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.CONFLICT);
    problem.setTitle("Resource conflict");
    problem.setDetail("The requested change conflicts with existing data.");
    problem.setProperty("code", "DATA_CONFLICT");
    return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
}
```

Ví dụ chỉ phù hợp khi ứng dụng có thể xác định các integrity violation này thuộc nhóm conflict có thể trả cho client. Trong production, nên phân biệt constraint cụ thể bằng mã/exception vendor ở phía server rồi map sang mã nghiệp vụ phù hợp. Không nên biến mọi lỗi integrity thành cùng một response nếu một số lỗi là bug hoặc dữ liệu hỏng cần cảnh báo mức cao.

### 6.3. Không ghi SQL và bind values tùy tiện vào log

SQL log có thể hữu ích trong môi trường phát triển, nhưng production cần kiểm soát vì bind value có thể chứa dữ liệu cá nhân, token hoặc thông tin thanh toán. Nếu cần query diagnostics:

- Ưu tiên query fingerprint, operation name hoặc repository method thay vì raw SQL có dữ liệu.
- Che hoặc loại bỏ bind parameters nhạy cảm.
- Không ghi password, access token, API key hoặc payment credential.
- Giới hạn quyền đọc log database và thời hạn lưu.
- Dùng tracing/metrics để quan sát latency và query count mà không phải ghi toàn bộ nội dung.

Parameterized query vẫn là yêu cầu chống SQL injection; output filtering không thay thế việc dùng prepared statement và validation.

## 7. Không lộ service topology và thông tin hạ tầng

### 7.1. Chuẩn hóa lỗi từ downstream

Nếu API gọi `payment-service` và nhận lỗi như:

```text
Connection refused to http://payment-service.prod.svc.cluster.local:8080
```

Không chuyển nguyên chuỗi này cho client. Service có thể trả:

```json
{
  "type": "https://api.example.com/problems/dependency-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "code": "DEPENDENCY_UNAVAILABLE",
  "requestId": "req_01JEXAMPLE"
}
```

Thông tin về dependency cụ thể, hostname, port, timeout, retry và trace span thuộc kênh vận hành nội bộ. Nếu client cần biết thao tác có thể retry hay không, trả hướng dẫn chung như `Retry-After` hoặc mã lỗi dependency tạm thời.

### 7.2. Rà soát HTTP headers

Các header có thể tiết lộ công nghệ hoặc topology:

- `Server` và `X-Powered-By`.
- Header debug, profiling hoặc framework-specific.
- Header nội bộ như `X-Upstream-Service`, `X-Backend-Host` hoặc proxy routing metadata.
- Cookie chứa tên môi trường, host nội bộ hoặc thông tin triển khai.
- Header lỗi từ downstream được proxy chuyển tiếp nguyên vẹn.

Tắt hoặc chuẩn hóa header không cần thiết ở ứng dụng, reverse proxy và API gateway. Không dựa vào việc ẩn version header như một biện pháp bảo vệ lỗ hổng; vẫn cần cập nhật dependency và cấu hình bảo mật.

### 7.3. Bảo vệ health, metrics và debug endpoint

Public health endpoint chỉ nên trả trạng thái tối thiểu cần cho load balancer, ví dụ `UP` hoặc `DOWN`. Chi tiết dependency, connection pool, queue, environment, build info và metrics nên được đặt sau authentication/network policy và chỉ cấp cho hệ thống vận hành.

Không expose actuator `env`, `configprops`, `beans`, `mappings`, `heapdump`, `threaddump` hoặc endpoint tương tự ra Internet nếu không có kiểm soát chặt. Chỉ bật endpoint cần thiết, giới hạn network, authentication và quyền truy cập; tách liveness/readiness với diagnostics sâu.

### 7.4. Không để URL hoặc redirect làm lộ host nội bộ

Không trả raw callback URL, proxy target hoặc URL từ exception của HTTP client. Khi API trả link, chỉ tạo từ public base URL đã cấu hình và resource được phép. Tránh dựng public URL bằng cách tin `Host` hoặc `X-Forwarded-Host` tùy ý từ request nếu proxy chưa chuẩn hóa chúng.

## 8. Validation error và dữ liệu đầu vào nhạy cảm

Validation response nên giúp client sửa request mà không tiết lộ giá trị bị từ chối hoặc quy tắc nội bộ quá chi tiết.

Ví dụ response an toàn:

```json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Request validation failed",
  "status": 422,
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "Quantity must be within the allowed range."
    }
  ]
}
```

Không đưa `rejectedValue` vào response một cách mặc định. Giá trị đó có thể là password, email, token, số thẻ hoặc nội dung cá nhân. Không trả regex, tên class DTO, tên entity hoặc tên constraint nội bộ. Field path nên là tên field công khai trong API contract, không phải tên cột database.

Với dữ liệu nhạy cảm, thông điệp cần nhất quán. Ví dụ login không nên cho biết “email tồn tại nhưng password sai”; account recovery không nên xác nhận một số điện thoại có đăng ký hay không nếu điều đó tạo nguy cơ enumeration.

## 9. Correlation ID và chẩn đoán an toàn

### 9.1. Correlation ID giúp tìm lỗi mà không lộ lỗi

Mỗi request nên có request ID hoặc trace ID để liên kết response với log/trace nội bộ. Client có thể gửi correlation ID, nhưng server cần kiểm tra định dạng, giới hạn độ dài/ký tự hoặc tạo ID mới. Không dùng ID do client gửi làm bằng chứng danh tính hoặc quyền truy cập.

Ví dụ:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-ID: req_01JEXAMPLE

{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "code": "INTERNAL_ERROR",
  "requestId": "req_01JEXAMPLE"
}
```

Support team dùng `requestId` để tìm diagnostic trong hệ thống nội bộ. Không cần gửi stack trace hoặc database error để người dùng copy vào ticket.

### 9.2. Log nội bộ cần được bảo vệ

Giữ diagnostic ở log không có nghĩa có thể ghi mọi thứ. Log nên:

- Có quyền truy cập theo vai trò và audit người xem.
- Che access token, cookie, API key, password, authorization header và secret.
- Hạn chế dữ liệu cá nhân và payload; ghi ID tham chiếu khi đủ dùng.
- Chuẩn hóa/sanitize dữ liệu để tránh log injection qua newline hoặc ký tự điều khiển.
- Có retention và quy trình xóa phù hợp.
- Tách log ứng dụng, security audit và debug trace theo mục đích.

Không đưa toàn bộ request body hoặc header vào log chỉ để dễ debug. Với lỗi validation, ghi tên field và error code có thể đủ; với lỗi downstream, ghi service logical name và trace span ID trong hệ thống nội bộ mà không trả hostname ra client.

### 9.3. Tránh log injection và thông tin giả mạo

Attacker có thể đưa newline hoặc chuỗi giống log level vào input để làm sai lệch log. Hãy dùng structured logging, encode/sanitize giá trị do client kiểm soát và không nối chuỗi raw vào log line. Correlation ID từ client nên được xác thực định dạng hoặc thay bằng ID do server tạo.

## 10. Ví dụ cấu hình Spring Boot và Spring Security

### 10.1. Tắt stack trace trong error response

Với Spring Boot, cấu hình mặc định production nên không include exception message hoặc stack trace trong response. Ví dụ cấu hình:

```yaml
server:
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
```

Các thuộc tính này kiểm soát response lỗi mặc định của Spring Boot. Nếu ứng dụng có `@ControllerAdvice`, custom error controller hoặc gateway chuyển tiếp lỗi downstream, vẫn phải bảo đảm các đường đó tuân theo cùng policy. Không chỉ dựa vào cấu hình mặc định.

### 10.2. Dùng `@RestControllerAdvice` làm error boundary

Ví dụ rút gọn:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(
            MethodArgumentNotValidException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.UNPROCESSABLE_ENTITY);
        problem.setTitle("Request validation failed");
        problem.setDetail("One or more fields are invalid.");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", safeFieldErrors(ex));
        return ResponseEntity.unprocessableEntity().body(problem);
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<ProblemDetail> handleAccessDenied() {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.FORBIDDEN);
        problem.setTitle("Access denied");
        problem.setDetail("You are not allowed to perform this action.");
        problem.setProperty("code", "ACCESS_DENIED");
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(problem);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception ex) {
        String requestId = RequestContext.currentRequestId();
        log.error("Unhandled API error requestId={}", requestId, ex);

        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Internal server error");
        problem.setDetail("The request could not be completed.");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("requestId", requestId);
        return ResponseEntity.internalServerError().body(problem);
    }
}
```

`safeFieldErrors` chỉ nên trả field path công khai, mã lỗi và message đã được kiểm soát. Không trả `FieldError.getRejectedValue()`, `getDefaultMessage()` nguyên trạng nếu message có thể chứa dữ liệu hoặc tên constraint nội bộ. Trong ứng dụng thực tế, cần có handler riêng cho lỗi xác thực, resource not found, conflict, rate limit và dependency failure; thứ tự mapping phải được kiểm thử.

### 10.3. Không để security exception bị biến thành 500

Spring Security có filter chain và exception handling riêng cho authentication/authorization. Cần cấu hình `AuthenticationEntryPoint` cho `401` và `AccessDeniedHandler` cho `403`, cùng error schema nhất quán. `@ControllerAdvice` không nhất thiết bắt được exception phát sinh trước khi request vào controller.

Ví dụ về response contract:

```text
AuthenticationEntryPoint:
    return 401 + code AUTHENTICATION_REQUIRED
    set WWW-Authenticate according to scheme
    do not include token parsing details

AccessDeniedHandler:
    return 403 + code ACCESS_DENIED
    do not include role names or internal policy expressions
```

Không trả chi tiết “JWT signature invalid at key rotation index 3” hoặc “role mapping failed in policy X”. Client cần biết credential không được chấp nhận hoặc action không được phép; operator cần trace để điều tra.

## 11. Output filtering ngoài REST JSON

### 11.1. GraphQL

GraphQL error có thể chứa `message`, `locations`, `path` và `extensions`. Không đưa exception message hoặc stack trace vào `extensions`. Production nên dùng mã lỗi ổn định và ẩn chi tiết resolver/internal service. `path` có thể hữu ích cho client nhưng cần đánh giá có tiết lộ field nhạy cảm hay cấu trúc nội bộ không.

### 11.2. gRPC

gRPC status và trailers có thể mang error details. Không truyền raw exception, SQL error hoặc hostname trong status description hoặc metadata. Map lỗi nghiệp vụ sang status code phù hợp, kèm mã lỗi ổn định trong metadata đã định nghĩa và giữ diagnostic trong trace nội bộ.

### 11.3. WebSocket và streaming

Không gửi exception stack hoặc internal URL trong message lỗi hay close reason. Dùng mã lỗi và thông điệp ngắn theo protocol. Khi stream đã bắt đầu, ghi nhận request/trace ID và đóng stream theo semantics được công bố; không gửi một phần payload lỗi chứa dữ liệu nội bộ.

### 11.4. File và export

CSV, PDF, report và file tải xuống cũng là output. Không thêm stack trace, SQL query, local file path hoặc debug metadata vào file khi quá trình tạo file thất bại. Nếu file không tạo được, trả error contract qua API và ghi diagnostic nội bộ.

## 12. Kiểm thử rò rỉ thông tin

Kiểm thử cần kiểm tra response body, header, log boundary và các lỗi phát sinh từ dependency. Không chỉ test happy path.

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| Unexpected exception | Controller/service ném exception không dự kiến | Trả 500 chung, có request ID, không có stack trace |
| SQL syntax/connection error | Database từ chối kết nối hoặc query lỗi | Không lộ SQL, host, port, schema hoặc driver detail |
| Constraint violation | Gửi dữ liệu gây unique/FK conflict | Trả mã lỗi nghiệp vụ phù hợp, không lộ constraint/table name |
| Downstream failure | HTTP client nhận connection refused hoặc timeout | Không lộ internal URL, hostname, IP hoặc service namespace |
| Validation | Gửi password/token/PII sai định dạng | Không phản chiếu rejected value hoặc raw payload |
| Authentication | Token sai chữ ký, hết hạn hoặc sai audience | Error chung, không lộ parser/JWK internals |
| Authorization | User không có quyền trên resource | Không lộ policy expression, role mapping hoặc dữ liệu resource |
| Header inspection | Kiểm tra `Server`, `X-Powered-By` và debug headers | Không có metadata triển khai không cần thiết |
| Health/debug endpoints | Gọi actuator/debug từ mạng công khai | Chỉ endpoint công khai tối thiểu; diagnostics được bảo vệ |
| GraphQL/gRPC | Resolver hoặc RPC ném exception | Không có stack, SQL hoặc internal topology trong error detail |
| Correlation ID | Client gửi ID dài, ký tự điều khiển hoặc giả mạo | ID được validate/replace; log không bị injection |
| Log redaction | Request chứa API key, cookie hoặc bearer token | Secret được che hoặc loại bỏ khỏi log/trace |
| Error consistency | Cùng loại lỗi qua controller, filter và gateway | Status/code/schema nhất quán theo contract |
| Resource enumeration | So sánh lỗi object không tồn tại và object bị che | Không tiết lộ sự tồn tại ngoài policy đã chọn |

Có thể thêm automated test quét response body/header bằng các mẫu nhạy cảm như ` at com.`, `.java:`, `SELECT `, `jdbc:`, `.svc.cluster.local`, `internal`, `password=` hoặc tên host thử nghiệm. Đây là heuristic giúp phát hiện hồi quy, không thay thế review error mapping vì các từ này có thể xuất hiện hợp lệ trong nội dung nghiệp vụ.

Với log, test redaction ở appender/collector và xác minh token, password, API key không xuất hiện trong output cuối. Không in log thật chứa secret vào kết quả test hoặc CI artifact.

## 13. Logging, metrics và phản ứng sự cố

### 13.1. Những gì nên ghi nội bộ

Tùy loại lỗi, log/trace có thể chứa:

- Request ID/trace ID và service logical name.
- Exception type, stack trace và cause chain đã được giới hạn quyền truy cập.
- Endpoint template, method, status và operation.
- Database error category/SQLSTATE hoặc query fingerprint nếu cần.
- Dependency logical name, timeout và span ID; hạn chế raw host/URL nếu không cần.
- Principal ID, tenant ID và resource ID ở mức cần thiết cho điều tra.
- Kết quả authorization và validation code.

Ngay cả log nội bộ cũng cần redaction, access control và retention. Chỉ ghi chi tiết đủ để điều tra; không ghi raw token, password, secret hoặc payload đầy đủ.

### 13.2. Metrics cần theo dõi

- Tỷ lệ 4xx/5xx theo route và mã lỗi.
- Số lỗi database, timeout và downstream failure theo logical dependency.
- Tỷ lệ response có error code không xác định.
- Số lần fallback handler được kích hoạt.
- Tỷ lệ lỗi validation/authentication/authorization bất thường.
- Số lần health/debug endpoint bị truy cập ngoài dự kiến.
- Tỷ lệ log redaction và cảnh báo secret scanning.

Không dùng metric label có cardinality cao như raw request ID, user ID hoặc URL đầy đủ. Dùng route template, error code và logical service name.

### 13.3. Khi phát hiện rò rỉ

1. Xác định response, endpoint, thời gian và nhóm client đã nhận thông tin.
2. Phân loại thông tin lộ: stack trace, SQL/schema, credential, PII hay topology.
3. Nếu secret hoặc credential bị lộ, xử lý như credential compromise: thu hồi/rotate và rà soát việc sử dụng.
4. Giới hạn hoặc bảo vệ endpoint/debug route đang làm lộ thông tin.
5. Xem log/tracing để xác định phạm vi nhưng giữ nguyên quy tắc truy cập và redaction.
6. Sửa exception mapping, gateway/header policy hoặc downstream error normalization.
7. Thêm regression test và theo dõi sau khi triển khai.

Nếu topology bị lộ, không nên cho rằng chỉ cần đổi hostname là đủ. Hãy rà soát authentication, authorization, network policy và quyền của service được tiết lộ.

## 14. Checklist trước khi phát hành

- [ ] Mọi response lỗi có schema và mã lỗi ổn định; không trả exception message trực tiếp.
- [ ] Stack trace, source path, class name và cause chain không xuất hiện trong response production.
- [ ] SQL statement, bind values, schema/table/column/constraint và database host không bị lộ.
- [ ] Lỗi từ downstream được chuẩn hóa; không trả raw internal URL, hostname, IP hoặc namespace.
- [ ] Validation response không phản chiếu password, token, PII hoặc rejected value nhạy cảm.
- [ ] `401`, `403`, `404`, `409`, `422`, `429`, `503` và `500` được ánh xạ theo contract rõ ràng.
- [ ] `WWW-Authenticate`, `Retry-After` và các header cần thiết được giữ đúng semantics; debug headers được loại bỏ.
- [ ] `Server`, `X-Powered-By` và metadata triển khai không cần thiết được tắt/chuẩn hóa.
- [ ] Health/debug/actuator/metrics endpoints được giới hạn network và authentication.
- [ ] Correlation ID được tạo hoặc validate; không tin raw client header.
- [ ] Log/trace có diagnostic cần thiết nhưng được redaction, phân quyền và giới hạn retention.
- [ ] GraphQL, gRPC, WebSocket, export và file error paths cũng được lọc.
- [ ] Có automated test quét response/header và test redaction cho log.
- [ ] Có quy trình incident khi stack, SQL, credential hoặc topology bị lộ.

## Kết luận

Không lộ stack trace, SQL hoặc service topology là yêu cầu của toàn bộ error handling và output pipeline. Client cần status, mã lỗi ổn định, thông điệp an toàn và correlation ID; developer/operator cần diagnostic trong log và trace nội bộ được bảo vệ. Hãy chuẩn hóa exception ở boundary, map database và downstream errors sang lỗi nghiệp vụ, kiểm soát header và debug endpoint, che dữ liệu validation, rồi kiểm thử mọi đường phản hồi. Cách này giữ API dễ xử lý cho client mà không biến response lỗi thành bản đồ cấu trúc nội bộ.
