# Trả stack trace, token hoặc topology trong lỗi

Khi một API gặp lỗi, response thường được gửi tới client trước khi người vận hành có đủ thông tin để điều tra. Nếu ứng dụng trả nguyên stack trace, nội dung exception, access token, SQL statement, đường dẫn file hoặc địa chỉ service nội bộ, một lỗi tưởng như bình thường có thể trở thành nguồn cung cấp thông tin cho attacker. Những chi tiết đó giúp suy ra framework, thư viện, cấu trúc thư mục, tên bảng, hostname, port, service account hoặc cách hệ thống xác thực.

**Error information disclosure** là việc tiết lộ thông tin nội bộ qua response lỗi, header, redirect, log hoặc kênh chẩn đoán mà người nhận không được phép xem. Các dữ liệu thường bị lộ gồm stack trace, token/cookie, secret, topology, internal hostname, IP/private range, filesystem path, SQL, cấu hình runtime và exception message chứa dữ liệu đầu vào.

API cần tách rõ hai mục đích: client nhận một error contract ổn định, đủ để hiểu request thất bại và biết cách xử lý; đội vận hành nhận diagnostics nội bộ có kiểm soát để điều tra. Không nên dùng response công khai làm nơi chuyển nguyên log hoặc exception ra ngoài.

Trong API Security, lỗi có thể xảy ra ở authentication, authorization, validation, business workflow, database, downstream service hoặc hạ tầng. Mỗi lớp cần trả thông tin phù hợp nhưng tuân theo cùng nguyên tắc: chỉ tiết lộ dữ liệu cần thiết cho caller, không để lộ credential hoặc kiến trúc nội bộ, và giữ correlation ID để nối response với sự kiện nội bộ.

Sau bài học, người đọc có thể:

- Nhận diện thông tin nhạy cảm thường bị lộ qua error response và header.
- Phân biệt thông báo an toàn cho client với diagnostics nội bộ.
- Thiết kế error contract có mã lỗi ổn định, status phù hợp và correlation ID.
- Dùng centralized exception handling trong Spring Boot mà không trả stack trace.
- Redact token, cookie, secret và dữ liệu cá nhân khỏi response, log và trace.
- Hạn chế lộ topology, dependency, filesystem path, SQL và phiên bản phần mềm.
- Xử lý lỗi authentication/authorization mà không hỗ trợ account enumeration.
- Viết test xác minh response không chứa thông tin nội bộ trong nhiều tình huống.

## 1. Vì sao trả lỗi quá chi tiết là anti-pattern?

Attacker thường không cần khai thác thành công ngay từ request đầu tiên. Họ có thể gửi input sai, token không hợp lệ, ID không tồn tại hoặc request tới route chưa biết để quan sát sự khác nhau trong phản hồi. Mỗi khác biệt có thể tiết lộ một phần kiến trúc và trạng thái hệ thống.

Ví dụ response nguy hiểm:

~~~text
org.springframework.dao.InvalidDataAccessResourceUsageException:
PreparedStatementCallback; bad SQL grammar
[select * from customer_account where tenant_id = 17 and id = ?]
at com.example.billing.repository.CustomerRepository.findById(...)
at com.example.billing.service.CustomerService.getCustomer(...)
Caused by: org.postgresql.util.PSQLException:
ERROR: relation "customer_account" does not exist
Host: db-prod-03.internal.example
~~~

Response trên có thể tiết lộ:

- Framework và thư viện database.
- Tên package, class và phương thức nội bộ.
- Tên bảng và cấu trúc dữ liệu.
- Hostname của database production.
- Loại lỗi và vị trí lỗi xảy ra.

Attacker có thể dùng thông tin này để điều chỉnh payload, dò endpoint khác hoặc nhắm vào công nghệ cụ thể. Nếu response còn chứa request header hoặc context, nguy cơ có thể nghiêm trọng hơn nhiều.

### 1.1. Những loại thông tin không nên trả cho caller

| Loại thông tin | Ví dụ | Rủi ro |
|---|---|---|
| Stack trace | Class, package, line number, call chain | Fingerprint công nghệ và vị trí code |
| Exception message | SQL, hostname, file path, raw input | Lộ schema, hạ tầng hoặc dữ liệu |
| Credential | Bearer token, refresh token, cookie, API key | Chiếm phiên hoặc gọi API thay caller |
| Secret/key material | Private key, webhook secret, database password | Giả mạo, giải mã hoặc truy cập hệ thống |
| Network topology | Internal IP, hostname, port, service name | Hỗ trợ lateral movement và SSRF targeting |
| Filesystem detail | Absolute path, mount, username, temp directory | Reconnaissance và khai thác lỗi path |
| Runtime/config | Profile, environment variable, feature flag, config value | Tiết lộ trust boundary và cấu hình yếu |
| Database detail | Query, table, column, constraint name | Hỗ trợ injection và data model discovery |
| Identity detail | Tài khoản tồn tại, trạng thái lock, role nội bộ | Account enumeration và privilege mapping |
| Dependency detail | Phiên bản thư viện, upstream URL, vendor response | Fingerprint và nhắm vào lỗ hổng cụ thể |

Không phải mọi thông tin kỹ thuật đều là bí mật. Tuy nhiên, response công khai cần được thiết kế theo mục đích của caller; chi tiết không cần thiết nên được giữ ở kênh nội bộ.

### 1.2. Lỗi tiết lộ thông tin có thể kết hợp với lỗi khác

Stack trace tự nó chưa chắc cho phép chiếm quyền. Nhưng khi kết hợp với SSRF, path traversal, SQL injection, broken access control hoặc dependency vulnerability, thông tin nội bộ có thể làm giảm đáng kể công sức khai thác.

Ví dụ:

1. Endpoint nhận URL trả lỗi DNS kèm hostname và IP nội bộ.
2. Attacker biết service metadata hoặc admin endpoint tồn tại.
3. Họ điều chỉnh input để hướng request tới vùng mạng vừa phát hiện.
4. Nếu egress policy và SSRF validation yếu, lỗi ban đầu có thể trở thành truy cập trái phép.

Do đó, error handling là một phần của defense-in-depth. Nó không thay thế authentication, authorization, input validation hay network segmentation, nhưng giúp giảm thông tin hỗ trợ attacker.

## 2. Response lỗi và diagnostics nội bộ có mục đích khác nhau

Một thiết kế tốt tạo hai representation từ cùng một failure:

- **Client-facing error:** status, mã lỗi ổn định, thông điệp ngắn, correlation ID và hướng xử lý phù hợp.
- **Internal diagnostic event:** exception type, stack trace khi cần, service/route, actor context đã xác minh, dependency, trace ID và reason code; được lưu ở hệ thống nội bộ có quyền truy cập.

Ví dụ client nhận:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "code": "INTERNAL_ERROR",
  "detail": "The request could not be completed.",
  "instance": "/api/orders",
  "requestId": "req-7f31"
}
~~~

Trong log nội bộ, cùng request có thể có event chứa exception class, stack trace, downstream service alias và database operation name. Event đó không được gửi ngược cho caller và cần được bảo vệ như dữ liệu nhạy cảm.

### 2.1. Chỉ tiết lộ điều caller cần biết

Caller thường cần:

- Request có thất bại hay không.
- Lỗi thuộc nhóm nào: input không hợp lệ, chưa xác thực, không đủ quyền, conflict hay lỗi tạm thời.
- Có thể sửa input hoặc thử lại hay không.
- Mã lỗi để client xử lý và support tra cứu.
- Request/correlation ID để liên hệ bộ phận hỗ trợ.

Caller thường không cần:

- Tên class hoặc method trong ứng dụng.
- Stack trace hoặc line number.
- SQL query hoặc tên bảng.
- Internal hostname, private IP hoặc service port.
- Nội dung token hoặc cookie.
- Secret, key ID nội bộ hoặc đường dẫn secret store.
- Exception message nguyên văn từ database, HTTP client hoặc parser.

### 2.2. Không biến thông báo an toàn thành thông báo vô ích

Generic error không có nghĩa mọi lỗi đều trả cùng một status và cùng một message. API vẫn cần contract rõ ràng:

- 400 Bad Request: request không hợp lệ theo contract.
- 401 Unauthorized: credential thiếu hoặc không hợp lệ; có thể kèm WWW-Authenticate phù hợp.
- 403 Forbidden: caller đã xác thực nhưng không được phép, nếu policy không che giấu sự tồn tại của resource.
- 404 Not Found: resource không tồn tại hoặc được cố ý che giấu để tránh xác nhận sự tồn tại.
- 409 Conflict: trạng thái hiện tại xung đột với thao tác.
- 413 Content Too Large: request vượt giới hạn kích thước.
- 415 Unsupported Media Type: media type không được hỗ trợ.
- 429 Too Many Requests: rate limit bị vượt; có thể cung cấp Retry-After.
- 500 Internal Server Error: lỗi không dự kiến ở phía server.
- 502/503/504: lỗi gateway, service unavailable hoặc timeout theo vai trò của API.

Thông điệp có thể ngắn nhưng phải đúng nghĩa để client xử lý. Không trả 500 cho mọi validation error; cũng không trả chi tiết nội bộ chỉ để giải thích một 500.

## 3. Thiết kế error contract ổn định

API nên có một format lỗi nhất quán, được version hóa hoặc duy trì tương thích. RFC 9457 Problem Details for HTTP APIs cung cấp format chuẩn với các field như type, title, status, detail và instance. Có thể bổ sung extension field như code và requestId.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 400,
  "code": "VALIDATION_ERROR",
  "detail": "One or more fields are invalid.",
  "requestId": "req-93ac",
  "errors": [
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "Quantity must be between 1 and 20."
    }
  ]
}
~~~

Chỉ đưa tên field và lý do validation có ích cho client. Không echo raw value nếu value có thể chứa password, token, personal data hoặc payload nhạy cảm. Không đưa rejected object đầy đủ vào errors.

### 3.1. Mã lỗi ổn định, message có thể thay đổi

Client nên dựa vào code hoặc type, không parse câu văn tự nhiên. Ví dụ:

| Code | Ý nghĩa |
|---|---|
| VALIDATION_ERROR | Input không đáp ứng contract |
| AUTHENTICATION_REQUIRED | Thiếu credential hợp lệ |
| INVALID_CREDENTIAL | Credential không hợp lệ |
| ACCESS_DENIED | Không được phép thực hiện action |
| RESOURCE_NOT_FOUND | Resource không tồn tại hoặc không được tiết lộ |
| STATE_CONFLICT | Thao tác không phù hợp trạng thái hiện tại |
| RATE_LIMITED | Vượt giới hạn request |
| DEPENDENCY_UNAVAILABLE | Dependency cần thiết không sẵn sàng |
| INTERNAL_ERROR | Lỗi không dự kiến |

Không dùng code tiết lộ thông tin nội bộ như POSTGRES_TABLE_MISSING, JWT_KEY_ALIAS_NOT_FOUND hoặc PAYMENT_DB_NODE_3_DOWN. Những reason cụ thể thuộc internal diagnostics.

### 3.2. Correlation ID và request ID

Mỗi request nên có ID để support và operator nối response với log/trace. ID cần:

- Không chứa token, user email, account number hoặc dữ liệu do caller tùy ý đưa vào.
- Có độ dài và format giới hạn.
- Được tạo ở edge/service hoặc validate trước khi chấp nhận ID ngoài.
- Không được dùng làm credential hoặc authorization input.
- Được truyền xuyên service theo trust boundary.

Nếu caller gửi X-Request-Id, có thể lưu thành externalRequestId sau khi validate; server vẫn có thể tạo requestId nội bộ riêng. Không tin correlation ID để xác định actor hoặc tenant.

### 3.3. Không đưa raw URL nhạy cảm vào instance

Field instance có thể là URI reference định danh request. Nếu path/query chứa email, reset code, token hoặc object identifier nhạy cảm, không phản chiếu raw URI. Dùng route template hoặc path đã loại giá trị nhạy cảm, ví dụ /api/users/{userId}/reset-password.

## 4. Stack trace và exception message

Stack trace có thể chứa:

- Package/class/method nội bộ.
- Đường dẫn source/build agent hoặc thư mục deploy.
- Framework, library và phiên bản.
- Tên database, table, constraint hoặc query.
- URL/hostname downstream.
- Nội dung exception có kèm input của caller.

Đây là dữ liệu phục vụ developer/operator. Không serialize exception trực tiếp vào response.

### 4.1. Anti-pattern phổ biến

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<String> handle(Exception ex) {
    return ResponseEntity.internalServerError()
            .body(ex.getMessage() + "\n" + stackTraceToString(ex));
}
~~~

Đoạn code trên trả nguyên exception message và stack trace. Nó có thể làm lộ thông tin nhạy cảm trong cả lỗi ứng dụng lẫn lỗi dependency.

Một anti-pattern khác:

~~~java
catch (SQLException ex) {
    return ResponseEntity.badRequest()
            .body("SQL failed: " + ex.getMessage());
}
~~~

Lỗi database không phải lỗi input contract mà caller có thể tự sửa bằng cách đọc SQL. Hãy trả lỗi server phù hợp và lưu diagnostics nội bộ.

### 4.2. Phân loại exception

Không nên gom mọi exception vào một message chung nếu có thể phân loại an toàn:

| Exception category | Client response | Internal diagnostic |
|---|---|---|
| Validation | 400, field/code an toàn | Constraint, validator và field context đã redact |
| Authentication | 401 hoặc contract tương ứng | Credential failure reason, issuer/key metadata không nhạy cảm |
| Authorization | 403 hoặc 404 theo policy | Actor, action, object/tenant reference và decision |
| Business conflict | 409 | State hiện tại và transition bị từ chối |
| Rate limit | 429 | Limit profile, key scope và counter context |
| Dependency timeout | 502/503/504 theo vai trò | Dependency alias, timeout, trace và retry context |
| Unexpected exception | 500 | Exception type, stack trace, service version và trace ID |

Không đưa exception message trực tiếp vào client response chỉ vì exception thuộc loại expected. Ngay cả lỗi validation cũng có thể chứa raw value hoặc tên property nội bộ; hãy tạo message từ error code và metadata đã allowlist.

## 5. Token, cookie và secret tuyệt đối không được phản chiếu

Token và secret có thể xuất hiện trong:

- Authorization header.
- Cookie/session header.
- Query string hoặc form body.
- OAuth callback parameters.
- Refresh/access token response.
- Exception message từ HTTP client hoặc token parser.
- Request/response logging.
- Trace baggage hoặc diagnostic context.

### 5.1. Không echo credential sai

Không trả lại token bị từ chối để giúp client debug. Không đưa token vào error detail, response header, redirect URL hoặc validation message. Khi token invalid, client chỉ cần biết credential không được chấp nhận và cách lấy credential mới theo contract.

Ví dụ response an toàn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-credential",
  "title": "Authentication failed",
  "status": 401,
  "code": "INVALID_CREDENTIAL",
  "detail": "The supplied credentials are not valid.",
  "requestId": "req-12ab"
}
~~~

Không đưa token, kid nội bộ, secret reference hoặc nguyên nhân chi tiết như signature matched old compromised key vào response công khai.

### 5.2. Không ghi secret vào log hoặc trace

Redaction phải áp dụng cho:

- Authorization và Proxy-Authorization.
- Cookie và Set-Cookie.
- Access/refresh token và API key.
- Password, OTP, recovery code.
- Private key, webhook signing secret, database credential.
- Signed URL có query token hoặc temporary credential.

Dùng allowlist field cho log thay vì serialize toàn bộ request rồi cố gắng xóa secret. Kiểm tra cả structured attributes, nested exception, HTTP client wire log, APM trace và error reporting service.

### 5.3. Không đưa secret vào URL

URL thường xuất hiện trong access log, browser history, proxy log, referrer và monitoring. Tránh gửi access token hoặc API key trong query string. Nếu upstream API bắt buộc dùng signed URL, giới hạn thời gian, scope và quyền; không phản chiếu URL đầy đủ vào error response hoặc log.

## 6. Topology, internal hostname và filesystem path

Error message có thể vô tình tiết lộ cách các thành phần kết nối:

- db-primary-02.internal, redis-session-1, kafka-broker-3.
- Private IP, port, subnet hoặc Kubernetes namespace.
- Internal service URL, cluster DNS name và ingress backend.
- Absolute path như /var/app/secrets, /opt/service/config.
- Tên volume, mount point, container user hoặc thư mục upload tạm.
- Cloud region, account ID, metadata endpoint hoặc bucket name.

Thông tin topology giúp attacker chọn mục tiêu và hiểu đường đi nội bộ. Không đưa những chi tiết này vào response công khai.

### 6.1. Không dựa vào obscurity làm kiểm soát duy nhất

Ẩn hostname hoặc path không thay thế network segmentation, authentication, authorization và egress policy. Tuy nhiên, không cần tiết lộ topology cho caller không có lý do hợp lệ. Hãy giữ thông tin cần thiết trong inventory nội bộ và diagnostics có kiểm soát.

### 6.2. Lỗi từ downstream service

HTTP client hoặc SDK có thể trả exception chứa URL, hostname, response body hoặc header của upstream. Không chuyển nguyên nội dung đó về client:

~~~java
catch (WebClientResponseException ex) {
    return ResponseEntity.status(ex.getStatusCode())
            .body(ex.getResponseBodyAsString());
}
~~~

Đoạn code này có thể phản chiếu response từ provider, bao gồm stack trace, internal ID hoặc dữ liệu của bên thứ ba. Hãy map lỗi downstream sang error code của API hiện tại và lưu phần diagnostics cần thiết nội bộ sau khi redact.

### 6.3. Header không nên tiết lộ stack/framework

Kiểm tra các header như:

- Server.
- X-Powered-By.
- Header debug hoặc build version.
- Header proxy/upstream chứa hostname nội bộ.
- Header trace/debug chứa service topology.

Không phải mọi header version đều tạo lỗ hổng nghiêm trọng, nhưng chỉ expose những gì cần cho client. Không dùng header như X-Backend-Node: order-api-pod-17.internal trong response công khai.

## 7. Account enumeration và khác biệt thông báo lỗi

Lỗi xác thực và khôi phục tài khoản có thể tiết lộ user tồn tại hay không qua:

- Message khác nhau giữa email không tồn tại và password sai.
- Status code khác nhau.
- Response length hoặc JSON shape khác nhau.
- Thời gian phản hồi khác biệt rõ.
- Header hoặc redirect khác nhau.
- OTP/reset flow chỉ gửi thông báo khi account tồn tại.

Ví dụ không an toàn:

~~~json
{"error":"No account exists for alice@example.com"}
~~~

Một response an toàn hơn:

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "detail": "The supplied credentials could not be verified.",
  "requestId": "req-3d11"
}
~~~

Với password reset, có thể trả thông báo chung rằng nếu account đủ điều kiện thì hướng dẫn sẽ được gửi qua kênh đã đăng ký. Hệ thống vẫn phải xử lý nội bộ đúng và không gửi thông báo cho account không tồn tại.

### 7.1. Cân bằng bảo mật và UX

Không phải mọi API đều cần che giấu resource existence. Một API quản trị có thể cần 404 hoặc 403 theo policy; một API công khai có thể trả 404 cho ID không tồn tại. Quyết định phải dựa trên threat model và hợp đồng client.

Nếu dùng cùng response cho account không tồn tại và password sai, cần kiểm tra cả status, body, header và timing ở mức phù hợp. Không tạo timing test quá cứng trong unit test thường vì CI có nhiễu; dùng kiểm thử chuyên biệt và rate limiting để giảm enumeration.

## 8. Spring Boot: centralized exception handling an toàn

Spring Boot hỗ trợ @RestControllerAdvice để chuẩn hóa error response. Handler nên map exception sang Problem Detail hoặc DTO an toàn, không trả exception object.

Ví dụ:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    private final RequestIdProvider requestIdProvider;
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(InvalidOrderException.class)
    ResponseEntity<ProblemDetail> handleInvalidOrder(
            InvalidOrderException ex) {

        String requestId = requestIdProvider.currentRequestId();
        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.BAD_REQUEST);
        problem.setType(URI.create(
                "https://api.example.com/problems/invalid-order"));
        problem.setTitle("Invalid order request");
        problem.setDetail("The order request cannot be processed.");
        problem.setProperty("code", "INVALID_ORDER");
        problem.setProperty("requestId", requestId);

        log.atInfo()
                .addKeyValue("event_type", "api.request.rejected")
                .addKeyValue("request_id", requestId)
                .addKeyValue("reason_code", "INVALID_ORDER")
                .log("Order request rejected");

        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception ex) {
        String requestId = requestIdProvider.currentRequestId();

        log.atError()
                .addKeyValue("event_type", "api.unhandled_exception")
                .addKeyValue("request_id", requestId)
                .addKeyValue("exception_type", ex.getClass().getName())
                .setCause(ex)
                .log("Unhandled API exception");

        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setType(URI.create(
                "https://api.example.com/problems/internal-error"));
        problem.setTitle("Internal server error");
        problem.setDetail("The request could not be completed.");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("requestId", requestId);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

Đây là skeleton minh họa. RequestIdProvider phải trả ID đã được validate hoặc do server tạo. Logger phải được cấu hình để stack trace chỉ tới sink nội bộ có kiểm soát. Không bật HTTP wire logging hoặc log request body ở production nếu chưa có redaction được kiểm chứng.

### 8.1. Security exception từ Spring Security

Authentication và authorization exception thường được xử lý ở filter chain qua AuthenticationEntryPoint và AccessDeniedHandler, không nhất thiết đi qua MVC @RestControllerAdvice. Vì vậy, cần chuẩn hóa cả hai nơi:

- AuthenticationEntryPoint: trả response 401 theo error contract.
- AccessDeniedHandler: trả response 403 hoặc policy 404.
- @RestControllerAdvice: xử lý lỗi từ controller/service.
- Gateway/WAF: map lỗi edge theo cùng schema nếu client cần một contract nhất quán.

Không để filter chain trả HTML login page hoặc stack trace trong khi controller trả JSON. Với API, content type và error schema cần nhất quán theo contract.

### 8.2. Validation exception

MethodArgumentNotValidException, ConstraintViolationException hoặc binding exception có thể chứa rejected value. Chỉ đưa tên field, error code và message đã allowlist ra response. Không serialize FieldError nguyên bản nếu nó bao gồm rejected value.

Ví dụ:

~~~java
List<Map<String, String>> errors = ex.getBindingResult()
        .getFieldErrors()
        .stream()
        .map(error -> Map.of(
                "field", safeFieldName(error.getField()),
                "code", safeValidationCode(error.getCode())))
        .toList();
~~~

Không đưa error.getRejectedValue() vào response. safeFieldName và safeValidationCode nên map qua danh sách hợp lệ để tránh lộ property nội bộ hoặc phản chiếu input bất thường.

### 8.3. Không trả nguyên upstream response

Với lỗi từ RestClient/WebClient/Feign/SDK, map status và reason code sang contract nội bộ. Chỉ expose thông tin nghiệp vụ đã được duyệt, ví dụ “Payment provider is temporarily unavailable”. Không trả response body upstream, request URL, response header hoặc exception message nguyên văn.

## 9. Error handling trong gateway và microservices

Trong kiến trúc nhiều service, mỗi hop có thể tạo một lỗi khác nhau. Nếu gateway chỉ chuyển nguyên response upstream, thông tin nội bộ có thể vượt qua trust boundary.

Một mô hình an toàn:

1. Service phát sinh lỗi ghi diagnostic event nội bộ với trace ID.
2. Service trả error code public và request ID/trace context cần thiết.
3. Gateway xác thực response format, loại bỏ header nội bộ và không phản chiếu body nhạy cảm.
4. Gateway trả contract thống nhất cho caller.
5. Trace liên kết các hop nhưng không chứa token hoặc payload nhạy cảm.

### 9.1. Giữ internal error code tách khỏi public code

Ví dụ nội bộ:

~~~json
{
  "internalReason": "DB_CONNECTION_POOL_EXHAUSTED",
  "dependency": "orders-db-primary",
  "exceptionType": "SQLTransientConnectionException",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Client chỉ nhận DEPENDENCY_UNAVAILABLE hoặc INTERNAL_ERROR tùy contract. Không dùng internal reason làm public code nếu nó tiết lộ topology hoặc implementation.

### 9.2. Không làm mất correlation khi map lỗi

Khi gateway đổi response, giữ request ID hoặc trace ID đã được xác thực/được tạo tại edge. Không thay ID một cách tùy tiện ở mỗi hop khiến operator không thể tìm sự kiện. Nếu cần nhiều ID, phân biệt requestId, traceId và upstreamRequestId.

### 9.3. Không chuyển lỗi chi tiết qua message queue

Dead-letter queue, retry topic và event failure metadata thường được xem là nội bộ, nhưng vẫn có thể bị nhiều consumer hoặc operator truy cập. Không nhét access token, full payload, secret hoặc exception dump vào message headers. Dùng error code, event ID, attempt count và reference tới diagnostic record có kiểm soát.

## 10. Logging diagnostics mà không tạo thêm rò rỉ

Giữ stack trace trong log nội bộ có thể cần thiết để debug, nhưng log cũng là một kho dữ liệu có rủi ro. Không phải mọi exception đều cần ghi toàn bộ stack trace hoặc payload.

### 10.1. Log theo mức độ và loại lỗi

| Loại lỗi | Logging gợi ý |
|---|---|
| Validation expected | INFO/WARN có reason code; thường không cần stack trace |
| Authentication failure | Security event có actor/client context phù hợp; không log token |
| Authorization deny | Actor, action, object/tenant reference và decision đã chuẩn hóa |
| Business conflict | INFO với object/action/state code nếu cần audit |
| Dependency timeout | WARN/ERROR với dependency alias, timeout, trace ID |
| Unexpected exception | ERROR với exception type và stack trace trong sink nội bộ |
| Repeated attack pattern | Security alert theo aggregation, tránh log payload độc hại đầy đủ |

### 10.2. Redaction và allowlist

Không ghi toàn bộ request/response object theo mặc định. Dùng allowlist field và redaction ở logger/exporter. Các field cần loại bỏ hoặc mask gồm:

- Authorization, Cookie, Set-Cookie.
- Password, OTP, refresh/access token.
- API key, private key, shared secret.
- Signed URL và query parameter chứa credential.
- Personal data không cần cho điều tra.
- File content, multipart body và raw webhook payload.

Exception message từ thư viện có thể chứa URL hoặc input. Trước khi ghi, cân nhắc log exception type/reason code thay vì toàn bộ message; stack trace cũng cần được bảo vệ và retention giới hạn.

### 10.3. Quyền truy cập và retention

Áp dụng:

- RBAC cho log viewer và APM.
- Audit việc tìm kiếm/export log.
- Encryption khi truyền và lưu.
- Retention theo loại log và mục đích.
- Tách production diagnostics khỏi môi trường developer không cần truy cập.
- Không đưa log nhạy cảm vào ticket công khai hoặc chat không được phê duyệt.
- Mask dữ liệu trong dashboard và alert notification.

Một response sạch không đủ nếu alert Slack/email lại chứa exception message hoặc token. Kiểm tra toàn bộ đường đi từ application logger tới SIEM, APM, ticketing và notification.

## 11. Error response và cache

Response lỗi có thể chứa thông tin về trạng thái xác thực hoặc dữ liệu riêng tư. Cần cân nhắc cache:

- Dùng Cache-Control: no-store cho lỗi authentication, token, session và dữ liệu nhạy cảm.
- Không để shared cache lưu response cá nhân hóa theo actor nếu thiếu cache key phù hợp.
- Cân nhắc Vary khi response thay đổi theo Origin hoặc header liên quan.
- Không để reverse proxy cache 401, 403 hoặc response có request-specific detail ngoài policy.

Không phải mọi lỗi public đều cần no-store; có thể cache một số response tĩnh nếu thiết kế cho phép. Với lỗi liên quan identity hoặc thông tin nội bộ, mặc định thận trọng và xác minh hành vi CDN/gateway thực tế.

## 12. Kiểm thử chống error information disclosure

Test không chỉ kiểm tra status code. Cần kiểm tra body, header, redirect, log, trace và gateway response.

### 12.1. Negative test theo loại lỗi

| Tình huống | Kiểm tra response |
|---|---|
| JWT malformed/expired | Không có token, claim, key material hoặc parser stack trace |
| Password sai | Không phân biệt account tồn tại nếu policy chống enumeration yêu cầu |
| Authorization denied | Không lộ object thuộc tenant khác hoặc policy nội bộ |
| Validation fail | Không echo password, token, raw rejected value hoặc nested object |
| SQL/database error | Không có query, table, column, JDBC URL, host hoặc SQL exception |
| Downstream timeout | Không có upstream URL, IP, response body hoặc credential |
| File parser error | Không có absolute path, temp directory hoặc parser stack trace |
| SSRF blocked | Không trả private IP, DNS answer hoặc metadata service detail |
| Rate limit | Có code và retry guidance cần thiết, không lộ internal counter/key |
| Unexpected exception | Generic server error và request ID |

### 12.2. Kiểm tra chuỗi nhạy cảm

Tạo test marker giả cho:

- Bearer token.
- Cookie/session ID.
- Password/OTP.
- API key.
- Private hostname và IP nội bộ.
- Filesystem path.
- SQL fragment.
- Personal data.

Gửi các marker qua header/body/path/query trong test environment, kích hoạt các nhánh lỗi và xác minh chúng không xuất hiện trong response, header, log public hoặc trace export không được phép. Chỉ dùng credential giả, không dùng secret thật để thử redaction.

### 12.3. Kiểm tra mọi lớp exception handler

Bao gồm:

- Spring Security authentication entry point.
- Access denied handler.
- MVC controller advice.
- Validation/binding handler.
- Gateway/WAF error mapping.
- HTTP client/downstream exception mapping.
- Async worker/dead-letter handling.
- Management/actuator error response.

Một handler an toàn ở controller không có tác dụng nếu lỗi JWT xảy ra trước đó và filter trả stack trace. Cần test từng boundary.

### 12.4. Test account enumeration

Gọi login/reset flow với:

- Account tồn tại và password sai.
- Account không tồn tại.
- Account disabled/locked.
- Account pending verification.

So sánh status, body shape, error code, redirect và các side effect quan sát được. Kiểm tra rate limit. Timing nên được đánh giá bằng kiểm thử chuyên biệt nhiều mẫu, không dùng một assertion mili-giây mong manh trong unit test thông thường.

## 13. Ví dụ integration test với MockMvc

Ví dụ kiểm tra lỗi nội bộ không trả stack trace:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ErrorDisclosureIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void unexpectedExceptionReturnsSafeProblemDetail() throws Exception {
        mockMvc.perform(get("/test/force-internal-error"))
                .andExpect(status().isInternalServerError())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.requestId").isNotEmpty())
                .andExpect(content().string(
                        not(containsString("java.lang."))))
                .andExpect(content().string(
                        not(containsString("at com.example."))))
                .andExpect(content().string(
                        not(containsString("jdbc:"))));
    }
}
~~~

Endpoint /test/force-internal-error chỉ nên tồn tại trong test profile và không được expose trong production. Các assertion chuỗi là kiểm tra bổ sung; nên parse JSON và xác minh allowlist field để bảo đảm không có property lạ.

### 13.1. Test response header

Kiểm tra:

- Không có header debug/internal hostname.
- Server/X-Powered-By không tiết lộ version nếu policy yêu cầu loại bỏ.
- Không có Set-Cookie ngoài dự kiến trong error flow.
- Cache-Control phù hợp.
- WWW-Authenticate không chứa secret.
- Request ID có format hợp lệ.

### 13.2. Test logs và traces

Dùng test appender hoặc log capture để xác minh:

- Exception type/reason code có thể được ghi nội bộ.
- Token/password/cookie marker không xuất hiện.
- Request ID/trace ID khớp response.
- Log không có raw request body hoặc upstream response ngoài policy.
- Error event không cho phép caller chèn newline tạo record giả.

Nếu stack trace được giữ trong log, test xác minh nó chỉ xuất hiện ở test sink nội bộ và không được serialize vào HTTP response. Không lưu test artifact chứa secret giả ở nơi công khai nếu nó có thể bị nhầm với credential thật.

## 14. Các anti-pattern thường gặp và cách sửa

| Anti-pattern | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Trả ex.getMessage() | Message có thể chứa SQL, path, host hoặc input | Map exception sang public error code |
| Trả printStackTrace() | Lộ class, line number và dependency | Stack trace chỉ ở internal diagnostics |
| Trả upstream response body | Lộ thông tin của provider hoặc service nội bộ | Map sang error contract của API hiện tại |
| Echo Authorization header | Có thể làm lộ bearer token | Không phản chiếu credential |
| Ghi full request vào log | Token/PII/file có thể bị lưu | Structured allowlist và redaction |
| Khác message cho user tồn tại/không tồn tại | Account enumeration | Response tổng quát và rate limit |
| Trả internal hostname/IP | Hỗ trợ reconnaissance/SSRF | Dùng dependency alias hoặc generic detail |
| Expose actuator/config trong public error | Lộ profile và runtime config | Restrict management plane |
| Chỉ bảo vệ MVC handler | Filter/gateway vẫn có thể lộ lỗi | Chuẩn hóa mọi error boundary |
| Error response cache sai | Lộ response theo user/request khác | Cache policy rõ, thường no-store cho auth error |
| Debug mode bật production | Lộ diagnostics chi tiết | Config validation và deployment gate |

## 15. Checklist thiết kế error handling

- [ ] Có error contract ổn định với status, code, title/detail an toàn và request ID.
- [ ] Dùng RFC 9457 Problem Details hoặc schema nhất quán tương đương.
- [ ] Không trả stack trace, exception object hoặc raw exception message.
- [ ] Không trả SQL, database schema, JDBC URL hoặc constraint detail.
- [ ] Không trả bearer/refresh token, cookie, API key, password, OTP hoặc secret.
- [ ] Không trả internal hostname, private IP, port, filesystem path hoặc service topology.
- [ ] Không phản chiếu upstream response body/header hoặc signed URL.
- [ ] Validation response không chứa rejected value nhạy cảm.
- [ ] Authentication error không hỗ trợ account enumeration ngoài policy đã định.
- [ ] Security filter, MVC, gateway, async worker và management endpoint có error handling phù hợp.
- [ ] Internal diagnostics có redaction, access control, encryption và retention.
- [ ] Correlation ID không chứa dữ liệu nhạy cảm và không được dùng làm credential.
- [ ] Log/trace không ghi toàn bộ request hoặc response theo mặc định.
- [ ] Error response có cache policy phù hợp.
- [ ] CI có test response body, header, log và trace cho nhiều failure path.
- [ ] Có test regression cho lỗi từng làm lộ thông tin.

## Kết luận

Trả stack trace, token hoặc topology trong lỗi làm tăng lượng thông tin attacker có thể thu thập và đôi khi trực tiếp làm lộ credential. Hãy tách client-facing error khỏi internal diagnostics: client nhận status, error code, thông điệp phù hợp và request ID; operator nhận dữ liệu điều tra trong log/trace nội bộ được bảo vệ và redact. Chuẩn hóa exception handling ở security filter, controller, gateway và worker; không phản chiếu upstream response hoặc rejected input; kiểm thử body, header, log, trace và account-enumeration behavior. Error handling tốt vẫn giúp client xử lý được sự cố mà không biến response API thành bản đồ hệ thống.
