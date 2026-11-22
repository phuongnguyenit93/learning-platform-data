# Global exception handler và error envelope

Trong module `SECURITY_API_SECURITY`, API cần trả lỗi nhất quán để client xử lý được, operator tra cứu được và hệ thống không vô tình tiết lộ thông tin nội bộ. Với Java/Spring, global exception handler giúp chuẩn hóa lỗi phát sinh trong Spring MVC, còn error envelope định nghĩa contract ổn định giữa server và client. Tuy nhiên, không phải mọi lỗi đều đi qua controller: authentication và authorization có thể thất bại ngay trong Spring Security filter chain, trước khi request tới controller. Một thiết kế đầy đủ phải xử lý cả hai đường.

Nguyên tắc chính là **phân loại lỗi theo ngữ nghĩa, trả thông tin tối thiểu cần thiết và giữ một mã tham chiếu opaque để điều tra**. Client cần biết request thất bại vì thiếu quyền, dữ liệu không hợp lệ hay xung đột trạng thái; client không cần biết SQL, stack trace, class name, hostname nội bộ, token hoặc giá trị bí mật mà server đã nhận.

## 1. Vì sao cần global exception handler?

Nếu mỗi controller tự bắt exception, response dễ không nhất quán: endpoint trả `{"error":"bad request"}`, endpoint khác trả stack trace, endpoint khác lại trả HTML mặc định của framework. Client phải viết nhiều nhánh xử lý và đội vận hành khó phân biệt lỗi nghiệp vụ với lỗi hạ tầng.

Global exception handler tạo một nơi chuẩn hóa các exception phát sinh trong Spring MVC:

- Map exception domain sang HTTP status và error code ổn định.
- Chuyển lỗi validation thành danh sách field/error code có cấu trúc.
- Không đưa exception message thô hoặc rejected value vào response.
- Gắn request ID để support có thể tra log có kiểm soát.
- Ghi log một lần tại nơi sở hữu failure path, tránh log trùng.
- Giữ contract nhất quán giữa các controller và API version.

Ví dụ một response lỗi an toàn:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
X-Request-ID: 7b2a3d4e-5f60-4a71-8b92-1c3d4e5f6071
```

```json
{
  "type": "https://api.example.test/problems/resource-not-found",
  "title": "Không tìm thấy tài nguyên",
  "status": 404,
  "detail": "Tài nguyên không tồn tại hoặc không nằm trong phạm vi truy cập.",
  "instance": "urn:request:7b2a3d4e-5f60-4a71-8b92-1c3d4e5f6071",
  "code": "RESOURCE_NOT_FOUND",
  "requestId": "7b2a3d4e-5f60-4a71-8b92-1c3d4e5f6071"
}
```

Response không cho biết câu SQL, bảng dữ liệu, ID tenant nội bộ hay exception class. Request ID là giá trị opaque do server/gateway tin cậy tạo; nó chỉ dùng để tìm log, không phải credential hoặc quyền truy cập.

## 2. Chọn error contract: RFC 9457 Problem Details

Với HTTP API, có thể dùng **Problem Details for HTTP APIs** theo RFC 9457 thay vì tự nghĩ ra nhiều envelope không tương thích. Spring Framework 6 và Spring Boot 3 hỗ trợ `ProblemDetail` để biểu diễn loại response này.

Các member chuẩn thường dùng:

| Member | Ý nghĩa | Quy tắc an toàn |
|---|---|---|
| `type` | URI định danh loại vấn đề | Ổn định, có thể trỏ tới tài liệu lỗi công khai |
| `title` | Tóm tắt loại vấn đề | Ngắn, không chứa dữ liệu request |
| `status` | HTTP status tương ứng | Phải khớp status thực tế của response |
| `detail` | Giải thích cho lần xảy ra cụ thể | Chỉ đưa thông tin an toàn, không echo input/exception |
| `instance` | URI tham chiếu occurrence | Có thể dùng URN từ request ID opaque; tránh URL/query nhạy cảm |

Ứng dụng có thể thêm extension members như `code`, `requestId` hoặc `errors`. Những field này phải được tài liệu hóa và giữ ổn định. Không ghi đè ý nghĩa các member chuẩn bằng field tùy tiện.

### 2.1. Error envelope nên phục vụ client, không phục vụ debug nội bộ

Một envelope tốt giúp client quyết định hành động tiếp theo:

- `code`: mã lỗi máy đọc được, ổn định qua các bản release.
- `title`/`detail`: nội dung ngắn gọn cho người dùng hoặc developer tích hợp.
- `status`: HTTP status.
- `requestId`: mã tham chiếu để support điều tra.
- `errors`: danh sách lỗi field khi request không hợp lệ.
- `type`: định danh loại lỗi và tài liệu giải thích contract.

Không thêm `stackTrace`, `exception`, `sql`, `debugMessage`, `internalHost`, `accessToken`, `rejectedValue` hoặc toàn bộ request body. Nếu operator cần chi tiết, họ tra log/tracing platform với quyền riêng dựa trên request ID.

### 2.2. Không nhầm error code với HTTP status

HTTP status thể hiện nhóm kết quả giao thức; `code` thể hiện lỗi cụ thể của API. Nhiều lỗi có thể cùng status `400`, nhưng client có thể xử lý khác nhau dựa trên code.

Ví dụ:

| HTTP status | Error code | Ý nghĩa |
|---:|---|---|
| 400 | `MALFORMED_REQUEST` | JSON hoặc tham số không parse được |
| 400 | `VALIDATION_FAILED` | Field không thỏa contract validation |
| 401 | `AUTHENTICATION_REQUIRED` | Thiếu hoặc không có credential hợp lệ |
| 403 | `ACCESS_DENIED` | Principal đã xác thực nhưng không được phép |
| 404 | `RESOURCE_NOT_FOUND` | Resource không tồn tại hoặc được che theo policy |
| 409 | `STATE_CONFLICT` | Trạng thái hiện tại không cho phép thao tác |
| 412 | `PRECONDITION_FAILED` | ETag/version condition không thỏa |
| 413 | `PAYLOAD_TOO_LARGE` | Body vượt giới hạn |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Content-Type không được hỗ trợ |
| 422 | `BUSINESS_RULE_VIOLATION` | Nội dung parse được nhưng không thỏa quy tắc nghiệp vụ (nếu contract dùng 422) |
| 429 | `RATE_LIMIT_EXCEEDED` | Vượt giới hạn request/quota |
| 500 | `INTERNAL_ERROR` | Lỗi không dự kiến ở server |
| 502 | `UPSTREAM_FAILURE` | Dependency trả kết quả không hợp lệ hoặc lỗi gateway |
| 503 | `SERVICE_UNAVAILABLE` | Service tạm thời không thể xử lý |
| 504 | `UPSTREAM_TIMEOUT` | Dependency không phản hồi trong deadline |

Chọn `400` hay `422` cho validation là quyết định contract; điều quan trọng là nhất quán. Không dùng `200` với body chứa `success=false` cho lỗi HTTP thông thường vì proxy, retry logic, monitoring và client sẽ hiểu sai kết quả.

## 3. Phân loại exception trước khi map status

Không nên có một quy tắc kiểu “mọi exception thành 400” hoặc “mọi lỗi thành 500”. Hãy xác định exception đại diện cho lỗi client, lỗi domain, lỗi authentication/authorization hay lỗi hệ thống.

### 3.1. Lỗi request và validation

Ví dụ:

- JSON sai cú pháp hoặc không deserialize được.
- Thiếu query parameter bắt buộc.
- Path variable sai kiểu UUID/number.
- Field không thỏa `@NotNull`, `@Size`, `@Email` hoặc custom validator.
- Content-Type hoặc HTTP method không được hỗ trợ.

Các lỗi này thường ánh xạ sang `400`, `404`, `405`, `406` hoặc `415` theo tình huống. Nếu body hợp lệ về cú pháp nhưng không thỏa business rule, có thể dùng `422` nếu API contract đã chọn semantics đó.

### 3.2. Lỗi authentication và authorization

- Thiếu credential, token sai chữ ký, sai issuer/audience hoặc hết hạn: `401`.
- Principal đã xác thực nhưng thiếu permission: `403`.
- Resource ngoài phạm vi mà policy yêu cầu che giấu sự tồn tại: có thể trả `404`.
- CSRF token sai/thiếu với session-based request: thường `403`.

`401` cần semantics challenge phù hợp, ví dụ `WWW-Authenticate: Bearer` cho bearer-token resource server. Không trả chi tiết cho biết user nào tồn tại, role nào được yêu cầu hoặc token sai ở byte nào nếu điều đó giúp dò tài khoản/credential.

### 3.3. Lỗi domain và trạng thái

Các exception như `OrderNotFoundException`, `InsufficientBalanceException`, `InvalidOrderStateException` hoặc `IdempotencyConflictException` nên có mapping rõ. Ví dụ:

- Resource không tồn tại/không được tiết lộ: `404`.
- Chuyển trạng thái không hợp lệ hoặc idempotency key xung đột: `409`.
- `If-Match` hoặc version condition không khớp: `412`.
- Quy tắc nội dung nghiệp vụ không thỏa: `422` nếu contract chọn.

Không để domain service tự trả `ResponseEntity`; domain layer nên ném exception có ý nghĩa nghiệp vụ. Lớp web chịu trách nhiệm chuyển thành HTTP.

### 3.4. Lỗi hạ tầng và dependency

Database unavailable, provider timeout, broker failure hoặc lỗi không dự kiến thường là `500`, `502`, `503` hoặc `504` tùy vai trò của API và dependency. Không trả raw exception message từ JDBC/HTTP client vì có thể chứa SQL, connection string, URL nội bộ, hostname, credential hoặc response body của provider.

Không map mọi `DataIntegrityViolationException` thành `409` một cách mù quáng. Chỉ chuyển thành conflict khi xác định được constraint nghiệp vụ cụ thể, ví dụ unique business key. Lỗi constraint khác có thể là bug hoặc data corruption và cần xử lý như lỗi hệ thống.

### 3.5. Lỗi không được phân loại

Exception không dự kiến phải trở thành response `500` chung với mã lỗi ổn định. Log nội bộ có thể chứa exception class và stack trace theo quyền truy cập phù hợp, nhưng response không được chứa chi tiết đó. Không bắt `Throwable` để tiếp tục xử lý các lỗi JVM nghiêm trọng như `OutOfMemoryError`.

## 4. Thiết kế error code ổn định

Error code là contract mà client có thể dùng để hiển thị thông báo, yêu cầu người dùng sửa input hoặc quyết định retry. Vì vậy code phải ổn định hơn message text.

### 4.1. Quy tắc đặt code

- Dùng chữ in hoa và dấu gạch dưới, ví dụ `ORDER_STATE_CONFLICT`.
- Mỗi code có một ý nghĩa rõ, không tái sử dụng cho lỗi khác.
- Không đưa ID, email, tenant hoặc input vào code.
- Không dùng exception class name làm code công khai.
- Không tạo code động từ message hoặc tên bảng database.
- Có tài liệu về HTTP status, retryability và hành động client nên làm.

Ví dụ catalog:

| Code | HTTP | Retryable? | Hành động client |
|---|---:|---|---|
| `VALIDATION_FAILED` | 400 | Không | Sửa field theo `errors` |
| `AUTHENTICATION_REQUIRED` | 401 | Sau khi xác thực lại | Làm mới/đăng nhập credential |
| `ACCESS_DENIED` | 403 | Không tự retry | Yêu cầu quyền phù hợp |
| `RESOURCE_NOT_FOUND` | 404 | Không | Kiểm tra resource và phạm vi |
| `STATE_CONFLICT` | 409 | Tùy nghiệp vụ | Đọc trạng thái mới rồi quyết định |
| `RATE_LIMIT_EXCEEDED` | 429 | Có thể | Tuân thủ `Retry-After` |
| `UPSTREAM_TIMEOUT` | 504 | Chỉ khi thao tác idempotent/an toàn | Retry có backoff hoặc tra trạng thái |
| `INTERNAL_ERROR` | 500 | Không mặc định | Gửi request ID cho support |

### 4.2. Không để message text trở thành API contract

Client nên rẽ nhánh theo `code`, không parse `detail` hoặc `title`. Text có thể được dịch, cải thiện hoặc rút gọn mà không phá client. Không đặt nội dung do user nhập vào message error.

### 4.3. Versioning error contract

Khi thêm field, giữ tương thích bằng extension optional. Khi đổi semantics hoặc xóa code, cần quản lý API version/deprecation. Không âm thầm đổi một code từ lỗi có thể retry sang lỗi không thể retry nếu client dựa vào đó để điều khiển hành vi.

## 5. Validation error không được echo giá trị đầu vào

Validation response cần cho biết field nào sai và loại lỗi gì, nhưng không cần trả lại giá trị mà client đã gửi. Giá trị có thể là password, OTP, email, signed URL hoặc payload độc hại.

Ví dụ response:

```json
{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều field không đáp ứng yêu cầu.",
  "code": "VALIDATION_FAILED",
  "requestId": "7b2a3d4e-5f60-4a71-8b92-1c3d4e5f6071",
  "errors": [
    { "field": "displayName", "code": "SIZE_OUT_OF_RANGE" },
    { "field": "email", "code": "INVALID_FORMAT" }
  ]
}
```

Không trả `rejectedValue`, raw JSON path có thể chứa dữ liệu động, hoặc `defaultMessage` nếu custom validator đã nhúng giá trị đầu vào vào message. Hãy ánh xạ constraint sang error code an toàn và giới hạn số lỗi trả về để tránh response quá lớn.

### 5.1. Validation ở nhiều tầng

Spring có thể phát sinh nhiều loại exception:

- `MethodArgumentNotValidException`: validation DTO với `@Valid`/`@Validated` trong request body.
- `HandlerMethodValidationException`: method validation trong Spring Framework 6.1+.
- `ConstraintViolationException`: method/service validation hoặc validation provider; cần phân biệt với constraint violation từ database.
- `HttpMessageNotReadableException`: JSON không parse được hoặc kiểu dữ liệu không phù hợp.
- `MethodArgumentTypeMismatchException`: path/query parameter không chuyển được sang kiểu đích.

Không map `ConstraintViolationException` từ persistence/database thành lỗi client nếu nguyên nhân là dữ liệu không nhất quán hoặc bug nội bộ. Nên phân biệt validation boundary với database constraint và chỉ trả field errors đã được xác minh an toàn.

## 6. Spring MVC: triển khai `@RestControllerAdvice`

Spring MVC hỗ trợ `@ControllerAdvice`/`@RestControllerAdvice` để xử lý exception tập trung. Với Spring Framework 6 / Spring Boot 3, `ProblemDetail` là kiểu phù hợp cho RFC 9457. Ví dụ sau minh họa một error factory dùng chung và handler cho domain/validation error.

### 6.1. Error factory

```java
@Component
public class ApiProblemFactory {
    public ProblemDetail create(
            HttpStatus status,
            String type,
            String code,
            String title,
            String detail,
            String requestId) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(status, detail);
        problem.setType(URI.create("https://api.example.test/problems/" + type));
        problem.setTitle(title);
        problem.setInstance(URI.create("urn:request:" + requestId));
        problem.setProperty("code", code);
        problem.setProperty("requestId", requestId);
        return problem;
    }
}
```

`type` ở đây phải đến từ catalog cố định trong code, không nối trực tiếp input client. `requestId` phải được tạo và validate tại trust boundary, chỉ gồm ký tự an toàn như UUID canonical. Không dùng URI occurrence chứa full URL/query của request.

### 6.2. Global exception handler

```java
@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    private final ApiProblemFactory problems;
    private final RequestIdProvider requestIds;

    public ApiExceptionHandler(
            ApiProblemFactory problems,
            RequestIdProvider requestIds) {
        this.problems = problems;
        this.requestIds = requestIds;
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(ResourceNotFoundException ex) {
        String requestId = requestIds.current();
        ProblemDetail body = problems.create(
            HttpStatus.NOT_FOUND,
            "resource-not-found",
            "RESOURCE_NOT_FOUND",
            "Không tìm thấy tài nguyên",
            "Tài nguyên không tồn tại hoặc không nằm trong phạm vi truy cập.",
            requestId);
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(body);
    }

    @ExceptionHandler(InvalidOrderStateException.class)
    ResponseEntity<ProblemDetail> handleStateConflict(InvalidOrderStateException ex) {
        String requestId = requestIds.current();
        ProblemDetail body = problems.create(
            HttpStatus.CONFLICT,
            "state-conflict",
            "ORDER_STATE_CONFLICT",
            "Không thể thực hiện thao tác ở trạng thái hiện tại",
            "Hãy tải lại trạng thái tài nguyên trước khi thử lại.",
            requestId);
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(MethodArgumentNotValidException ex) {
        String requestId = requestIds.current();
        ProblemDetail body = problems.create(
            HttpStatus.BAD_REQUEST,
            "validation-failed",
            "VALIDATION_FAILED",
            "Dữ liệu không hợp lệ",
            "Một hoặc nhiều field không đáp ứng yêu cầu.",
            requestId);

        List<Map<String, String>> errors = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .limit(50)
            .map(error -> Map.of(
                "field", safeFieldPath(error.getField()),
                "code", safeValidationCode(error.getCode())))
            .toList();

        body.setProperty("errors", errors);
        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(body);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception ex) {
        String requestId = requestIds.current();
        log.error("Unhandled API exception requestId={} exceptionType={}",
            requestId, ex.getClass().getName(), ex);

        ProblemDetail body = problems.create(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "internal-error",
            "INTERNAL_ERROR",
            "Đã xảy ra lỗi khi xử lý yêu cầu",
            "Vui lòng thử lại sau hoặc cung cấp request ID cho bộ phận hỗ trợ.",
            requestId);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(body);
    }

    private static String safeFieldPath(String field) {
        // Field path đến từ DTO đã biết; vẫn giới hạn độ dài/ký tự đầu ra.
        return field.length() <= 120 ? field : field.substring(0, 120);
    }

    private static String safeValidationCode(String code) {
        if (code == null) return "INVALID_VALUE";
        return switch (code) {
            case "NotNull", "NotBlank", "NotEmpty" -> "REQUIRED_FIELD";
            case "Size" -> "SIZE_OUT_OF_RANGE";
            case "Email" -> "INVALID_FORMAT";
            case "Min", "Max", "DecimalMin", "DecimalMax" -> "VALUE_OUT_OF_RANGE";
            default -> "INVALID_VALUE";
        };
    }
}
```

Đây là ví dụ cấu trúc cho Spring Boot 3/Java 17+. Các exception domain và `RequestIdProvider` là kiểu của ứng dụng. Cần bổ sung handler cụ thể cho các lỗi request phổ biến và giữ header giao thức cần thiết. `safeFieldPath` cần được giới hạn theo DTO contract; với nested path phức tạp, chỉ trả path đã allowlist. `safeValidationCode` cố ý không dùng `defaultMessage` hoặc `rejectedValue`.

### 6.3. Lưu ý về `@ExceptionHandler(Exception.class)`

Handler tổng quát là fallback cuối cùng cho lỗi không dự kiến trong Spring MVC. Exception handler cụ thể hơn sẽ được chọn theo type; không bắt `Throwable`. Không log lại cùng exception ở mọi tầng. Stack trace có thể chứa query, URL hoặc dữ liệu nhạy cảm nên log backend phải có access control, redaction và retention phù hợp.

Trong ứng dụng lớn, có thể kế thừa `ResponseEntityExceptionHandler` để tùy biến các exception chuẩn của Spring MVC và giữ lại các HTTP header framework tạo ra, như `Allow` hoặc thông tin media type. Không đăng ký handler xung đột cho cùng exception nếu không hiểu thứ tự/precedence của advice.

## 7. Xử lý lỗi validation và lỗi framework chuẩn

Không chỉ có `MethodArgumentNotValidException`. Một API hoàn chỉnh cần xác định mapping cho các exception phổ biến.

| Spring exception | Trường hợp | Mapping thường dùng |
|---|---|---:|
| `HttpMessageNotReadableException` | JSON sai cú pháp/kiểu | 400 |
| `MethodArgumentNotValidException` | DTO body validation fail | 400 hoặc 422 theo contract |
| `HandlerMethodValidationException` | Method parameter validation (Spring 6.1+) | 400 hoặc 422 |
| `MethodArgumentTypeMismatchException` | Path/query parameter sai kiểu | 400 |
| `MissingServletRequestParameterException` | Thiếu query parameter bắt buộc | 400 |
| `HttpRequestMethodNotSupportedException` | Method không được hỗ trợ | 405 |
| `HttpMediaTypeNotSupportedException` | Content-Type không hỗ trợ | 415 |
| `HttpMediaTypeNotAcceptableException` | Không có representation phù hợp | 406 |
| `NoHandlerFoundException` | Không tìm thấy route nếu cấu hình bật cơ chế này | 404 |
| `MaxUploadSizeExceededException` | Upload vượt giới hạn | 413 |

Khi override handler chuẩn, giữ response header có ý nghĩa. Ví dụ `405` có thể cần `Allow`; `401` cần `WWW-Authenticate`; `429` có thể cần `Retry-After`. Không tạo response body nhất quán bằng cách xóa các header giao thức mà client cần.

### 7.1. Lỗi parse body

Không trả nguyên message từ Jackson như tên class, token hoặc fragment JSON. Client chỉ cần biết body không đúng format hoặc field/type không hợp lệ. Không echo một đoạn payload có thể chứa password hoặc token.

### 7.2. Lỗi type mismatch

Với `GET /orders/{id}` khi `id` không phải UUID, trả `400` với code như `INVALID_PARAMETER`. Không trả stack trace hoặc tên converter. Tên parameter có thể được trả nếu thuộc API contract, nhưng không trả giá trị thô nếu có thể nhạy cảm.

### 7.3. Giới hạn số lượng validation errors

Một body lớn có thể tạo hàng nghìn field errors. Giới hạn số lỗi trong response, giới hạn độ dài field path và không đưa toàn bộ message text. Nếu cần, thêm `truncated: true` để client biết danh sách đã bị giới hạn.

## 8. Lỗi Authentication và Authorization nằm ngoài MVC advice

Một điểm dễ bỏ sót: `@RestControllerAdvice` chủ yếu xử lý exception trong Spring MVC dispatch. Spring Security filter chain chạy trước controller. Lỗi authentication/authorization tại filter chain thường không đi qua `@RestControllerAdvice`.

Ví dụ:

- Token thiếu/sai chữ ký bị từ chối bởi authentication filter.
- JWT sai issuer/audience bị resource server từ chối.
- `AuthorizationFilter` phát hiện principal thiếu authority.
- CSRF filter từ chối request dùng session cookie.

Nếu chỉ có global MVC advice, các lỗi này có thể trả body mặc định hoặc response khác contract. Cần cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` riêng để cùng dùng error factory.

### 8.1. AuthenticationEntryPoint cho 401

`AuthenticationEntryPoint` chịu trách nhiệm bắt đầu authentication khi request không có principal hợp lệ. Với bearer token, cần giữ challenge header `WWW-Authenticate` đúng semantics của resource server. Không trả token, claim hoặc chi tiết chữ ký sai.

Ví dụ cấu trúc:

```java
@Component
public class ApiAuthenticationEntryPoint implements AuthenticationEntryPoint {
    private final ObjectMapper objectMapper;
    private final ApiProblemFactory problems;
    private final RequestIdProvider requestIds;

    public ApiAuthenticationEntryPoint(
            ObjectMapper objectMapper,
            ApiProblemFactory problems,
            RequestIdProvider requestIds) {
        this.objectMapper = objectMapper;
        this.problems = problems;
        this.requestIds = requestIds;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        String requestId = requestIds.currentOrCreate(request, response);
        ProblemDetail body = problems.create(
            HttpStatus.UNAUTHORIZED,
            "authentication-required",
            "AUTHENTICATION_REQUIRED",
            "Cần xác thực để thực hiện yêu cầu",
            "Credential không hợp lệ hoặc đã hết hạn.",
            requestId);

        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        if (response.getHeader(HttpHeaders.WWW_AUTHENTICATE) == null) {
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer");
        }
        objectMapper.writeValue(response.getOutputStream(), body);
    }
}
```

Đây là ví dụ tối giản. Với OAuth2 Resource Server, ưu tiên tái sử dụng `BearerTokenAuthenticationEntryPoint` hoặc cấu hình tương đương để giữ `WWW-Authenticate` và error parameters đúng chuẩn. Nếu custom handler thay thế default, phải giữ các header/challenge cần thiết cho client. `currentOrCreate` cần bảo đảm ID opaque và không lấy header tùy ý từ Internet.

### 8.2. AccessDeniedHandler cho 403

`AccessDeniedHandler` xử lý principal đã xác thực nhưng không được phép. Body có thể dùng code `ACCESS_DENIED` và detail chung. Không ghi trong response policy expression, role nội bộ hoặc resource metadata. Với object authorization, nếu policy cần che giấu sự tồn tại resource, service có thể trả domain not-found thay vì để handler luôn trả 403.

Ví dụ cấu hình Spring Security 6:

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        ApiAuthenticationEntryPoint entryPoint,
        ApiAccessDeniedHandler deniedHandler) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .exceptionHandling(errors -> errors
            .authenticationEntryPoint(entryPoint)
            .accessDeniedHandler(deniedHandler))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults())
            .authenticationEntryPoint(entryPoint)
            .accessDeniedHandler(deniedHandler))
        .build();
}
```

Khi cấu hình cả `exceptionHandling` và resource server, bảo đảm cùng policy được dùng cho bearer-token failure. CSRF denial cũng có thể đi qua access denied handling; nếu API dùng session cookie, không tắt CSRF chỉ để thống nhất error response. Các route public cần được khai báo rõ; fallback nên yêu cầu xác thực hoặc deny theo thiết kế.

### 8.3. Filter exception và lỗi trước DispatcherServlet

Exception phát sinh trong servlet filter, gateway, reverse proxy hoặc container có thể không tới `@RestControllerAdvice`. Filter custom cần xử lý hoặc chuyển tiếp lỗi theo đúng cơ chế của Spring Security/Servlet; không viết một catch-all filter tự biến mọi exception thành response mà bỏ qua committed response, async dispatch hoặc security handler.

Nếu một filter tạo request ID, nó nên chạy đủ sớm để cả lỗi 401/403 cũng có ID. Nếu response đã commit, không thể ghi lại body; cần log theo request ID và giữ semantics HTTP.

## 9. HTTP status và header cần giữ đúng

Error envelope không thay thế các semantics của HTTP. Client, browser, proxy và retry middleware dựa vào status/header để xử lý.

| Tình huống | HTTP status | Header/behavior cần lưu ý |
|---|---:|---|
| Authentication required | 401 | `WWW-Authenticate` phù hợp scheme |
| Authenticated but forbidden | 403 | Không tiết lộ policy nội bộ |
| Method không hỗ trợ | 405 | `Allow` nếu framework cung cấp |
| Body quá lớn | 413 | Không parse/ghi payload không giới hạn |
| Rate limit | 429 | `Retry-After` nếu policy có thời điểm retry |
| Upstream timeout | 504 | Retry chỉ khi operation an toàn/idempotent |
| Service tạm không khả dụng | 503 | Có thể có `Retry-After`; không hứa retry nếu chưa an toàn |

Không đổi mọi lỗi thành `400` vì client có thể không refresh token, không backoff hoặc không biết operation đã tạo side effect hay chưa. Với `429`, giá trị `Retry-After` cần được giới hạn và nhất quán với quota policy.

### 9.1. Retryability là metadata nghiệp vụ

Không nên suy ra cứ `5xx` là retry an toàn. Payment timeout có thể là ambiguous outcome; thao tác có thể đã được provider thực hiện. Client cần idempotency key hoặc endpoint tra cứu trạng thái. Error code có thể được tài liệu hóa là retryable, nhưng phải xét method, idempotency và side effect.

### 9.2. Không tiết lộ resource existence ngoài policy

Với API đa tenant, `403` cho object tồn tại nhưng `404` cho object không tồn tại có thể tạo oracle. Nếu policy yêu cầu che giấu, dùng response thống nhất cho object ngoài phạm vi và object không tồn tại. Không thay đổi status tùy tiện nếu nó làm lộ dữ liệu qua timing hoặc body khác nhau.

## 10. Logging an toàn trong exception handler

Exception handler thường là nơi cuối cùng nhìn thấy lỗi. Đây cũng là nơi dễ vô tình log raw input hoặc secret nhất.

### 10.1. Log một lần tại nơi sở hữu lỗi

- Validation thông thường: có thể log event code ở `INFO`/`WARN`, không cần stack trace.
- Authentication failure: log reason category, route template và request ID; không log token.
- Authorization denial: log operation/policy outcome với dữ liệu resource đã phân loại.
- Unexpected server error: log stack trace trong hệ thống nội bộ có quyền truy cập phù hợp.
- Downstream failure: log dependency name, operation, status category và duration; không log full URL/header/body.

Không log cùng exception ở controller, service, filter và advice rồi ném tiếp. Chọn một owner cho mỗi failure path; lớp khác có thể bổ sung context có cấu trúc mà không nhân bản stack trace.

### 10.2. Không log rejected value hoặc raw exception message

`FieldError.getRejectedValue()` có thể là password, OTP, email hoặc signed URL. `getDefaultMessage()` có thể được custom validator tạo từ input. Chỉ log field path và error code đã allowlist.

Exception từ JDBC/HTTP client có thể chứa SQL, URL, query parameter, credential hoặc response body. Cần redaction ở logger/collector và không đưa exception message vào response.

### 10.3. Correlation ID không phải identity

Request ID cần opaque, được tạo tại trust boundary và giới hạn format. Không tạo từ user ID, tenant ID hoặc order number. Không dùng request ID để xác thực hoặc tra cứu log công khai. Support lookup phải có authentication, authorization và audit.

## 11. Error handling trong API version và microservices

Global exception handler là một phần của API contract. Các version có thể có schema response khác nhau vì compatibility, nhưng semantics bảo mật và không tiết lộ dữ liệu phải nhất quán.

### 11.1. Giữ error code ổn định giữa version

Nếu V1 và V2 cùng biểu diễn lỗi `ORDER_STATE_CONFLICT`, không nên để V1 trả stack trace còn V2 trả Problem Details. Có thể có adapter map về envelope version cũ, nhưng code, status và data minimization phải tuân thủ policy hiện hành.

Không để version cũ trả thêm rejected value hoặc internal detail chỉ vì client legacy từng dựa vào đó.

### 11.2. Không forward nguyên error body của downstream

Service A gọi Service B và nhận lỗi. Không trả nguyên response body/header của B cho caller nếu nó có thể chứa host, stack trace, provider token hoặc internal identifier. Map sang error code của API A và lưu downstream correlation/reference trong log nội bộ có quyền phù hợp.

Không chuyển tiếp `WWW-Authenticate` của một service nội bộ cho client nếu challenge đó không thuộc resource server public. Chỉ giữ header giao thức phù hợp với contract của API hiện tại.

### 11.3. Phân biệt request ID và trace ID

Request ID có thể được trả cho support; trace ID/span ID do tracing SDK quản lý. Có thể ghi cả hai trong log, nhưng không đưa toàn bộ baggage vào error response. Error envelope nên nhỏ và ổn định.

## 12. Kiểm thử global exception handler và error envelope

Test cần xác minh status, content type, schema, headers, data minimization và log behavior.

### 12.1. Test domain mapping

Với mỗi domain exception, xác minh:

- HTTP status đúng contract.
- `type`, `title`, `code` ổn định.
- `status` trong body khớp status thực tế.
- `requestId` có format opaque.
- Không có exception message, stack trace hoặc internal field.
- Không có side effect mới khi request bị từ chối.

### 12.2. Test validation mapping

Gửi body có field thiếu, sai format, vượt length, unknown property và JSON malformed. Xác minh:

- Status và code đúng contract.
- `errors` có field path và error code an toàn.
- Không có `rejectedValue`, raw body hoặc message chứa dữ liệu người dùng.
- Số lỗi và độ dài field path bị giới hạn.
- Database và downstream không thay đổi.

### 12.3. Test authentication/authorization filter chain

Không chỉ test controller advice. Dùng MockMvc hoặc integration test với Spring Security thực tế:

- Không credential → 401 với `WWW-Authenticate` phù hợp.
- Token sai issuer/audience/expiry → 401 và body cùng schema.
- Principal thiếu scope → 403.
- CSRF sai/thiếu trong cookie session → 403.
- Object ngoài tenant → 403 hoặc 404 theo policy.
- Mọi response có request ID theo contract.

Test phải chứng minh filter-chain error được xử lý bởi entry point/denied handler, không phải controller advice.

### 12.4. Test unexpected exception

Tạo một exception bất ngờ trong test endpoint. Xác minh client nhận `500` chung, có request ID và không thấy exception class, SQL, path hoặc stack trace. Kiểm tra log có event tương ứng và không có secret canary.

### 12.5. Test header semantics

- `401` giữ `WWW-Authenticate`.
- `405` giữ `Allow` khi có.
- `429` có `Retry-After` đúng policy.
- `413` không parse payload quá giới hạn.
- `application/problem+json` được trả nhất quán.
- Không duplicate hoặc phản chiếu header request ID do client gửi.

### 12.6. Ma trận test tổng hợp

| Trường hợp | Kết quả mong đợi |
|---|---|
| Resource not found | 404 + `RESOURCE_NOT_FOUND` |
| Invalid body | 400/422 theo contract + `VALIDATION_FAILED` |
| Malformed JSON | 400 + `MALFORMED_REQUEST` |
| Missing/invalid token | 401 + challenge header |
| Authenticated without permission | 403 + `ACCESS_DENIED` |
| State conflict | 409 + domain error code |
| Rate limit exceeded | 429 + `Retry-After` nếu áp dụng |
| Unexpected exception | 500 generic + request ID |
| Sensitive canary input | Không xuất hiện trong response/log |
| Filter-chain denial | Cùng error contract với MVC |

## 13. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Mỗi controller tự tạo error body | Contract không nhất quán | `@RestControllerAdvice` và error factory |
| Chỉ bắt exception ở MVC | 401/403 filter-chain có body khác | `AuthenticationEntryPoint`/`AccessDeniedHandler` |
| Trả `ex.getMessage()` | Lộ SQL, path, URL hoặc secret | Message an toàn và error code ổn định |
| Trả stack trace cho client | Lộ class, dependency và topology | Chỉ log nội bộ có kiểm soát |
| Echo `rejectedValue` | Lộ password/OTP/PII | Field path + validation code |
| Map mọi exception thành 400 | Che lỗi server và sai retry semantics | Exception taxonomy rõ |
| Map mọi database error thành 409 | Che data corruption hoặc bug | Chỉ map constraint nghiệp vụ đã xác định |
| `401` thiếu `WWW-Authenticate` | Client/resource server behavior không đúng | Giữ challenge header phù hợp |
| `status` body khác HTTP status | Client/proxy hiểu sai | Test consistency |
| Error code thay đổi tùy message | Client dễ hỏng khi text thay đổi | Catalog code ổn định |
| Log exception ở nhiều lớp | Log flooding và trùng stack trace | Một owner cho mỗi failure path |
| Request ID lấy từ client tùy ý | Log spoofing và header injection | Tạo/ghi đè tại trust boundary |
| Error body quá nhiều validation item | Tạo response lớn và lộ dữ liệu | Giới hạn số lỗi và field path |
| Forward nguyên error của downstream | Lộ thông tin service nội bộ | Map sang public error contract |

## 14. Checklist review trước khi phát hành

- [ ] API dùng error contract thống nhất, ưu tiên RFC 9457 Problem Details.
- [ ] `type`, `title`, `status`, `detail`, `instance` có semantics rõ.
- [ ] Extension `code`, `requestId`, `errors` được tài liệu hóa và ổn định.
- [ ] Error code không chứa input, identity hoặc exception class.
- [ ] Domain exception được map theo taxonomy và HTTP status phù hợp.
- [ ] Validation response không chứa rejected value hoặc raw request body.
- [ ] Số validation errors và độ dài field path được giới hạn.
- [ ] Không trả stack trace, SQL, hostname, filesystem path hoặc secret.
- [ ] `@RestControllerAdvice` xử lý MVC exception; security filter errors có entry point/denied handler riêng.
- [ ] 401 giữ `WWW-Authenticate`; 405/429 giữ header phù hợp.
- [ ] Request ID opaque được tạo tại trust boundary và có mặt trên error response.
- [ ] Unexpected exception chỉ log một lần ở nơi sở hữu failure path.
- [ ] Log/trace có redaction, access control và retention phù hợp.
- [ ] Downstream error được map, không forward nguyên body/header nội bộ.
- [ ] API versions giữ security semantics và data minimization nhất quán.
- [ ] Có test cho validation, domain error, 401/403, filter chain, 500 và sensitive canary.
- [ ] Test xác minh response status khớp body status và content type đúng.
- [ ] Test xác minh request bị từ chối không tạo business side effect.

## Kết luận

Global exception handler giúp Spring API trả lỗi nhất quán, nhưng chỉ giải quyết phần lỗi đi qua Spring MVC. Hãy dùng Problem Details với error code ổn định, map exception theo ngữ nghĩa, giới hạn validation detail và không trả thông tin nội bộ. Cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` cho lỗi phát sinh trong Spring Security filter chain, giữ đúng HTTP challenge/header và gắn request ID opaque. Khi test cả response, header, log và side effect, error envelope vừa hữu ích cho client vừa không trở thành kênh rò rỉ dữ liệu.
