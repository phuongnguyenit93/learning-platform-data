# Validation error không lộ implementation detail

Validation error cần đủ rõ để client sửa request, nhưng không được biến thành kênh tiết lộ cấu trúc nội bộ của API. Một thông báo như `Invalid request` cho mọi trường hợp khiến client khó tích hợp; ngược lại, trả nguyên exception, SQL, tên bảng, đường dẫn file, tên class, stack trace hoặc giá trị nhạy cảm mà client đã gửi có thể giúp attacker hiểu cách hệ thống hoạt động và tìm điểm yếu tiếp theo.

Mục tiêu là thiết kế một hợp đồng lỗi có thông tin hữu ích ở mức nghiệp vụ: mã lỗi ổn định, field công khai có thể sửa và thông điệp an toàn. Chi tiết kỹ thuật phục vụ debug được ghi ở log nội bộ có kiểm soát, gắn với correlation ID để đội vận hành tra cứu.

Trong phạm vi `SECURITY_API_SECURITY`, validation phải được thiết kế theo endpoint, object và luồng nghiệp vụ. API cần kiểm tra đầu vào trước khi thực hiện side effect, giới hạn dữ liệu không tin cậy và trả lỗi nhất quán mà không tiết lộ secret, dữ liệu của người khác hoặc cách triển khai bên trong.

## 1. Validation error có thể làm lộ những gì?

Thông báo lỗi được trả ra ngoài là một phần của bề mặt tấn công. Nếu API đưa nguyên thông tin nội bộ vào response, attacker có thể thu thập các manh mối sau:

| Thông tin bị lộ | Ví dụ không an toàn | Rủi ro |
|---|---|---|
| Stack trace | Tên package, class, method, dòng code | Lộ cấu trúc ứng dụng và đường thực thi |
| Database detail | Tên bảng/cột, SQL, constraint name | Lộ schema và cách truy vấn |
| Framework detail | `MethodArgumentNotValidException`, Hibernate/Jackson message | Fingerprint framework và phiên bản/cấu hình |
| Filesystem/path | `C:\\app\\secrets\\...`, `/srv/app/uploads/...` | Lộ cấu trúc máy chủ và vị trí file |
| Rejected value | Token, password, email, số thẻ hoặc payload đầy đủ | Rò rỉ dữ liệu bí mật và cá nhân |
| Internal field/property | `isRootAdmin`, `passwordHash`, `tenantSecret` | Lộ model và field nhạy cảm |
| Upstream response | Body lỗi nguyên bản từ payment/OCR/provider | Lộ thông tin của dependency hoặc credential |
| Tài nguyên tồn tại | Khác biệt lỗi giữa ID có thật và ID không có | Hỗ trợ enumeration object hoặc account |
| Policy nội bộ | Tên rule, ngưỡng phát hiện abuse, expression | Giúp attacker điều chỉnh request để né kiểm soát |

Ví dụ response không nên trả:

```json
{
  "error": "org.hibernate.exception.ConstraintViolationException",
  "message": "duplicate key violates constraint uk_users_email at users.email",
  "sql": "insert into users(email, password_hash, tenant_id) ...",
  "stackTrace": "com.example.identity.UserRepository.save(UserRepository.java:87)"
}
```

Client không cần biết tên exception, câu SQL hay tên constraint để sửa request. Những chi tiết này nên nằm trong log nội bộ, được bảo vệ và liên kết với request ID.

## 2. Nguyên tắc thiết kế lỗi an toàn nhưng vẫn hữu ích

Một response validation tốt nên tuân theo các nguyên tắc:

1. **Thông tin theo hợp đồng công khai:** chỉ trả field và quy tắc mà client được phép biết.
2. **Mã lỗi ổn định:** client xử lý theo `code`, không phụ thuộc câu chữ hoặc ngôn ngữ.
3. **Không phản chiếu dữ liệu nhạy cảm:** không trả password, token, rejected value hoặc toàn bộ payload.
4. **Không lộ implementation:** không trả exception class, stack trace, SQL, path, tên bảng/cột nội bộ hay dependency response.
5. **Không tiết lộ tài nguyên ngoài quyền:** lỗi validation không được trở thành cách xác nhận object, user hoặc tenant tồn tại.
6. **Tách thông tin bên ngoài và bên trong:** client nhận thông điệp an toàn; log nội bộ giữ chi tiết cần thiết để debug.
7. **Nhất quán giữa endpoint:** cùng một loại lỗi có schema và semantics giống nhau.
8. **Không tạo side effect khi request không hợp lệ:** validation và authorization cần diễn ra trước hành động nhạy cảm.

Không phải mọi lỗi đều cần thông báo chung chung. Nếu `pageSize` vượt giới hạn được công bố, response có thể nói rõ giới hạn tối đa. Nếu `email` sai định dạng, có thể trả `INVALID_FORMAT`. Điều cần tránh là tiết lộ giới hạn nội bộ, cách lưu trữ hoặc dữ liệu không thuộc quyền của caller.

## 3. Phân biệt validation, authentication, authorization và conflict

Các loại lỗi khác nhau cần được biểu diễn đúng ngữ nghĩa. Dùng một mã lỗi validation cho mọi tình huống có thể che mất lỗi bảo mật hoặc làm client xử lý sai.

| Loại lỗi | Câu hỏi | HTTP status thường dùng |
|---|---|---|
| Syntax/parse error | Request có đọc được theo định dạng API không? | `400 Bad Request` |
| Validation error | Giá trị có đáp ứng hợp đồng đầu vào không? | `400` hoặc `422`, theo quy ước API |
| Authentication error | Caller có credential hợp lệ không? | `401 Unauthorized` |
| Function/object authorization | Caller có quyền thực hiện action trên object không? | `403 Forbidden` hoặc `404` để che giấu object |
| State conflict | Dữ liệu hợp lệ nhưng trạng thái hiện tại không cho phép thao tác? | `409 Conflict` |
| Rate limit/quota | Caller có vượt giới hạn sử dụng không? | `429 Too Many Requests` |
| Unexpected server failure | Có lỗi nội bộ không dự kiến? | `500 Internal Server Error` |

Ví dụ: `quantity` là chuỗi thay vì số có thể là `400`; `quantity=-5` có thể là `422` nếu API phân biệt validation ngữ nghĩa; user thiếu quyền sửa hóa đơn là `403`; hóa đơn đã thanh toán nên không thể sửa là `409`. Một token sai không phải validation error của body.

Chọn `400` cho cả lỗi cú pháp và validation cũng có thể chấp nhận nếu hợp đồng API quy định như vậy. Nếu dùng `422` cho nội dung hợp lệ về cú pháp nhưng vi phạm quy tắc, phải áp dụng nhất quán và ghi rõ trong tài liệu API.

## 4. Chuẩn hóa response bằng Problem Details

Một định dạng phổ biến là Problem Details for HTTP APIs với media type `application/problem+json`. Ví dụ:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store
```

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/profiles",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "displayName",
      "code": "INVALID_LENGTH",
      "message": "Display name must contain between 1 and 80 characters."
    },
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Enter a valid email address."
    }
  ],
  "traceId": "01J..."
}
```

Các trường `type`, `title`, `status`, `detail` và `instance` thuộc cấu trúc Problem Details. API có thể bổ sung `code`, `errors` và `traceId` như extension đã được tài liệu hóa.

### 4.1. Ý nghĩa từng trường

- `type`: URI định danh loại lỗi công khai; không dùng URL nội bộ hoặc endpoint quản trị.
- `title`: tiêu đề ngắn, ổn định cho loại lỗi.
- `status`: phải khớp HTTP status thực tế.
- `detail`: giải thích ngắn gọn ở mức client có thể hành động.
- `instance`: URI tham chiếu request; không chứa query string hoặc dữ liệu nhạy cảm.
- `code`: mã lỗi ổn định để client xử lý bằng logic.
- `errors`: danh sách field-level error đã lọc theo schema công khai.
- `traceId`: mã tra cứu log, không phải token hoặc bằng chứng cấp quyền.

`detail` và `message` không nên chứa raw exception message. `traceId` nên là định danh khó đoán và chỉ dùng để liên hệ với support/log; không cho phép client dùng nó để lấy dữ liệu log hoặc trạng thái nội bộ.

### 4.2. Không đưa query string vào instance

Ví dụ không an toàn:

```text
/api/reset-password?email=alice@example.com&token=secret-value
```

Nếu đưa nguyên URI này vào `instance`, response và log có thể làm lộ email hoặc reset token. Hãy chỉ lưu path đã chuẩn hóa hoặc một request reference không chứa query/body. Không echo URL upload, callback hoặc URL có signed query parameters.

### 4.3. Cache và header

Response lỗi có thể chứa thông tin liên quan user hoặc request. Với endpoint nhạy cảm, thường nên dùng `Cache-Control: no-store`. Không để proxy hoặc CDN cache response chứa dữ liệu cá nhân hoặc thông tin xác thực. Đặt `Content-Type` đúng và không trả HTML debug page cho API.

## 5. Field-level error: trả đúng điều client cần biết

Một lỗi theo field giúp client hiển thị và sửa dữ liệu. Tuy nhiên, field path nội bộ có thể chứa tên property, class hoặc cấu trúc object mà API không muốn công khai.

Ví dụ response hữu ích:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "Quantity must be greater than zero."
    }
  ]
}
```

Ví dụ không nên trả:

```json
{
  "field": "userEntity.credentials.passwordHash",
  "rejectedValue": "$2a$12$...",
  "message": "must match internal password policy validator PasswordRulesV4"
}
```

### 5.1. Dùng tên field thuộc API contract

Field trả ra cần thuộc request schema công khai. Nếu validator báo lỗi ở property nội bộ hoặc field không nằm trong allowlist, ánh xạ về tên field công khai an toàn hoặc lỗi chung `request`.

Với object lồng nhau, có thể trả path như `addresses[0].postalCode` nếu path đó thuộc schema công khai, index được giới hạn và không chứa tên class/property nội bộ. Không phản chiếu một path tùy ý từ exception vào response.

### 5.2. Chỉ trả mã lỗi và thông điệp đã kiểm soát

Nên ánh xạ lỗi validator nội bộ sang mã công khai:

| Validator nội bộ | Public error code | Message an toàn |
|---|---|---|
| NotBlank | `REQUIRED` | This field is required. |
| Email | `INVALID_FORMAT` | Enter a valid email address. |
| Size | `INVALID_LENGTH` | The value has an invalid length. |
| Positive | `OUT_OF_RANGE` | Enter a value greater than zero. |
| Pattern | `INVALID_FORMAT` | The value has an invalid format. |
| Unknown/internal validator | `INVALID` | The supplied value is invalid. |

Thông điệp có thể chi tiết hơn nếu quy tắc là một phần của API contract. Không nên trả tên annotation, tên validator, regex nội bộ hoặc toàn bộ policy expression.

### 5.3. Không trả rejected value

Không đưa `FieldError.getRejectedValue()` hoặc giá trị tương tự vào response. Giá trị đó có thể là password, API key, token, số thẻ, thông tin cá nhân hoặc payload rất lớn. Ngay cả khi field không được xem là bí mật, phản chiếu giá trị không tin cậy có thể gây XSS ở client, log injection hoặc làm response phình to.

Nếu cần giúp client nhận diện field lỗi, chỉ trả tên field công khai và mã lỗi. Nếu cần debug giá trị đầu vào, log một bản đã mask hoặc fingerprint có kiểm soát; chỉ làm khi có mục đích hợp lệ và không ghi secret.

## 6. Không biến validation thành oracle để dò dữ liệu

Thông báo lỗi quá chi tiết có thể giúp attacker phân biệt trạng thái nội bộ hoặc dò tài nguyên.

### 6.1. Account enumeration

Endpoint đăng ký, login hoặc reset password không nên trả khác biệt rõ ràng giữa email tồn tại và không tồn tại nếu chính sách bảo mật yêu cầu che giấu.

Ví dụ không an toàn:

```json
{ "code": "EMAIL_NOT_REGISTERED", "message": "No user row found for alice@example.com" }
```

Response phù hợp hơn có thể là thông báo chung như `If an account matches the submitted information, further instructions will be sent.` Hệ thống vẫn có thể ghi lý do chi tiết ở log nội bộ có kiểm soát.

### 6.2. Object/tenant enumeration

Nếu một endpoint nhận `orderId`, không để validation response tiết lộ object tồn tại trong tenant khác. Việc trả `403` cho ID có thật nhưng `404` cho ID không tồn tại có thể tạo oracle. Tùy chính sách, hãy trả cùng response `404` cho object không tồn tại và object ngoài phạm vi.

Tương tự, không trả `tenant not found`, `user belongs to another tenant` hoặc tên chủ sở hữu nếu caller không có quyền biết. Kiểm tra object authorization trước khi trả field-level validation details có thể ngăn việc tiết lộ schema/trạng thái của tài nguyên ngoài quyền.

### 6.3. Không tiết lộ constraint nội bộ

Database có thể từ chối do unique constraint, foreign key hoặc check constraint. Đừng trả tên constraint hoặc tên cột. Nếu xung đột là một phần hợp đồng nghiệp vụ, ánh xạ sang lỗi công khai như `EMAIL_ALREADY_IN_USE` hoặc `STATE_CONFLICT` mà không xác nhận thêm dữ liệu không cần thiết.

Không phải mọi `DataIntegrityViolationException` đều là lỗi client. Nó cũng có thể phản ánh bug, race condition hoặc dữ liệu nội bộ không nhất quán. Chỉ ánh xạ constraint đã biết sang lỗi nghiệp vụ; trường hợp không xác định cần xử lý như lỗi server và ghi log bảo vệ.

## 7. Validation trước side effect và đúng ranh giới tin cậy

Validation cần diễn ra ở server, kể cả khi frontend đã kiểm tra. Client có thể bị sửa, bỏ qua hoặc không dùng giao diện chính thức.

Một trình tự thường dùng:

1. Kiểm tra request size, content type và cú pháp.
2. Xác thực caller.
3. Xác định tenant/principal từ nguồn tin cậy.
4. Kiểm tra quyền trên object/action và chính sách che giấu object.
5. Validate DTO và business rule có thể kiểm tra trước thao tác.
6. Thực hiện transaction/side effect sau khi các điều kiện đạt.
7. Ghi audit và trả response theo kết quả thực tế.

Thứ tự chi tiết có thể thay đổi theo endpoint để tránh tiết lộ object hoặc account. Nhưng không được thực hiện side effect rồi mới phát hiện request sai hoặc actor không có quyền. Với điều kiện phụ thuộc trạng thái trong database, kiểm tra và cập nhật cần được bảo vệ bằng transaction, lock hoặc optimistic version phù hợp để tránh race condition.

### 7.1. DTO allowlist thay vì bind entity

Chỉ nhận các field client được phép gửi. Ví dụ endpoint cập nhật hồ sơ nên dùng `UpdateProfileRequest` chỉ chứa `displayName` và `phoneNumber`, không bind trực tiếp vào entity có `role`, `tenantId`, `passwordHash` hoặc `isVerified`.

Validation kiểm tra kiểu, độ dài, định dạng và business rule; authorization quyết định actor có được sửa field đó hay không. Một field có giá trị hợp lệ vẫn có thể bị cấm sửa. Không dùng validation error để thay thế property-level authorization.

### 7.2. Unknown field và mass assignment

Hợp đồng API cần quy định field không biết sẽ bị từ chối hay bỏ qua. Với endpoint nhạy cảm, từ chối request có field ngoài schema thường giúp phát hiện client gửi sai và giảm nguy cơ mass assignment. Response có thể dùng `UNKNOWN_FIELD` hoặc `INVALID_REQUEST` nhưng không nên tiết lộ field nội bộ tồn tại.

Nếu trả tên field không hỗ trợ, chỉ echo tên đã giới hạn độ dài, loại bỏ control character và xác nhận nó không trùng tên property nội bộ nhạy cảm. Một lựa chọn an toàn hơn là trả lỗi chung cho unknown field trong endpoint quản trị.

## 8. Xử lý lỗi parser và framework

Lỗi có thể phát sinh trước khi DTO validation chạy: JSON hỏng, enum không hợp lệ, date parse lỗi, body không đúng media type hoặc field không thể convert. Framework thường đính kèm message kỹ thuật, token gần vị trí lỗi hoặc tên class. Không nên trả nguyên nội dung đó.

Ví dụ lỗi parser không nên trả:

```text
Cannot deserialize value of type java.time.LocalDate from String "yesterday"
at [Source: (InputStream); line: 1, column: 42] through reference chain: Request["birthDate"]
```

Có thể trả:

```json
{
  "code": "INVALID_REQUEST_FORMAT",
  "detail": "The request body is not in the expected format."
}
```

Nếu field path thuộc schema công khai và an toàn, có thể trả field đó với code `INVALID_FORMAT`. Không trả raw parser location, class name hoặc đoạn body gây lỗi.

## 9. Ví dụ triển khai với Spring Boot

### 9.1. DTO và validation contract

```java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @Email
    @Size(max = 254)
    String email
) {}
```

DTO công khai giới hạn field đầu vào. Các giới hạn `80` và `254` chỉ là ví dụ; cần khớp với hợp đồng sản phẩm. Không đưa `role`, `tenantId`, `passwordHash` hoặc field do server quản lý vào DTO này.

### 9.2. Ánh xạ lỗi sang public code

Ví dụ sau chỉ trả field nằm trong allowlist, mã lỗi do server định nghĩa và thông điệp đã kiểm soát. Nó không trả rejected value hoặc exception message:

```java
@RestControllerAdvice
class ApiValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> Map.of(
                "field", publicField(error.getField()),
                "code", publicCode(error.getCode()),
                "message", publicMessage(error.getCode())
            ))
            .toList();

        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.BAD_REQUEST);
        problem.setTitle("Request validation failed");
        problem.setDetail("One or more request fields are invalid.");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", errors);

        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .cacheControl(CacheControl.noStore())
            .body(problem);
    }

    private String publicField(String field) {
        return switch (field) {
            case "displayName" -> "displayName";
            case "email" -> "email";
            default -> "request";
        };
    }

    private String publicCode(String validatorCode) {
        if (validatorCode == null) return "INVALID";
        return switch (validatorCode) {
            case "NotBlank", "NotNull" -> "REQUIRED";
            case "Email", "Pattern" -> "INVALID_FORMAT";
            case "Size" -> "INVALID_LENGTH";
            case "Positive", "PositiveOrZero", "Min", "Max" -> "OUT_OF_RANGE";
            default -> "INVALID";
        };
    }

    private String publicMessage(String validatorCode) {
        return switch (publicCode(validatorCode)) {
            case "REQUIRED" -> "This field is required.";
            case "INVALID_FORMAT" -> "The value has an invalid format.";
            case "INVALID_LENGTH" -> "The value has an invalid length.";
            case "OUT_OF_RANGE" -> "The value is outside the allowed range.";
            default -> "The supplied value is invalid.";
        };
    }
}
```

Đây là ví dụ rút gọn. Trong ứng dụng thật, `publicField` nên được thiết kế theo từng request DTO hoặc schema API; không dùng một allowlist toàn cục cho mọi endpoint. Nếu field path có nested index, cần chuẩn hóa và giới hạn index trước khi trả. Cần loại trùng error, giới hạn số lỗi tối đa và dùng message localization theo hợp đồng.

`HttpStatus.BAD_REQUEST` được chọn theo quy ước minh họa. Nếu API dùng `422` cho validation ngữ nghĩa, hãy đổi nhất quán cả tài liệu và test. `ProblemDetail` có sẵn trong các phiên bản Spring Framework phù hợp; API cụ thể cần khớp phiên bản framework của dự án.

### 9.3. Lỗi JSON parse

```java
@ExceptionHandler(HttpMessageNotReadableException.class)
ResponseEntity<ProblemDetail> handleUnreadableBody() {
    ProblemDetail problem = ProblemDetail.forStatus(
        HttpStatus.BAD_REQUEST);
    problem.setTitle("Invalid request format");
    problem.setDetail("The request body could not be parsed.");
    problem.setProperty("code", "INVALID_REQUEST_FORMAT");

    return ResponseEntity.badRequest()
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .cacheControl(CacheControl.noStore())
        .body(problem);
}
```

Không đưa `exception.getMessage()`, `getMostSpecificCause()` hoặc raw JSON fragment vào response. Nếu cần vị trí lỗi để debug, ghi vào log đã lọc với correlation ID.

### 9.4. Lỗi bất ngờ

Lỗi không dự kiến cần response chung:

```json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "The request could not be completed.",
  "code": "INTERNAL_ERROR",
  "traceId": "01J..."
}
```

Stack trace và exception cause được ghi ở log nội bộ có quyền truy cập hạn chế. Không trả `exception.getMessage()` chỉ vì đây là API nội bộ; internal network không làm mọi caller trở nên đáng tin.

## 10. Log nội bộ: đủ để debug nhưng không tạo kho bí mật thứ hai

Tách response client khỏi log kỹ thuật. Log có thể chứa chi tiết hơn, nhưng vẫn phải tuân theo data minimization và kiểm soát truy cập.

### 10.1. Nên ghi gì?

- Timestamp, service, environment và endpoint/method.
- Correlation ID/trace ID và request ID.
- Error code nội bộ và public error code tương ứng.
- Exception type và stack trace khi cần điều tra.
- Actor/service identity, tenant scope ở dạng được phép.
- Field name đã chuẩn hóa, validator code và kết quả allow/deny.
- Kết quả xử lý, thời gian và trạng thái transaction.

### 10.2. Không ghi gì?

- Password, access token, refresh token, API key, cookie, private key và secret.
- Toàn bộ request body hoặc rejected value nếu không có nhu cầu cụ thể.
- Số thẻ, CVV, thông tin xác thực thanh toán hoặc dữ liệu cá nhân nhạy cảm.
- Raw query string có token hoặc dữ liệu riêng tư.
- Nội dung file upload hoặc dữ liệu nhạy cảm chỉ để tái tạo lỗi.

Nếu cần điều tra một giá trị, cân nhắc mask, truncate, tokenize hoặc HMAC fingerprint với key được bảo vệ. Hash thuần của email hoặc số điện thoại có thể bị dò từ điển vì miền giá trị dễ đoán.

### 10.3. Chống log injection

Attacker có thể gửi newline, tab, control character hoặc chuỗi giả log vào field được ghi. Dùng structured logging, serializer an toàn và chuẩn hóa control character. Không ghép raw input vào log line bằng string concatenation. Giới hạn độ dài field và không cho caller tự đặt `traceId` để giả mạo event của request khác.

## 11. Lỗi từ database và dịch vụ bên ngoài

### 11.1. Database constraint

Database error thường chứa tên constraint, bảng, cột, câu SQL hoặc giá trị gây lỗi. Hãy chuyển các trường hợp đã biết sang lỗi domain/public code.

Ví dụ:

```text
Unique email conflict -> EMAIL_ALREADY_IN_USE
Invalid workflow transition -> STATE_CONFLICT
Unknown integrity failure -> INTERNAL_ERROR
```

Chỉ map một constraint cụ thể khi semantics nghiệp vụ đã được xác định. Nếu unique conflict có thể tiết lộ account tồn tại, cần response chung theo chính sách enumeration. Race condition vẫn có thể xảy ra dù đã validate trước khi ghi; database constraint là lớp bảo vệ cuối, còn response cần ánh xạ an toàn.

### 11.2. Upstream/provider error

Không forward nguyên body lỗi từ payment provider, cloud storage, email service hoặc OCR provider. Response upstream có thể chứa request ID nội bộ, URL, bucket, account reference hoặc thông tin cấu hình. Map sang lỗi public ổn định như `UPSTREAM_UNAVAILABLE`, `OPERATION_REJECTED` hoặc `INTERNAL_ERROR` theo hợp đồng.

Nếu upstream trả lỗi có thể hành động cho client, chỉ expose phần đã được phê duyệt. Chi tiết provider và raw response lưu trong log bảo vệ, kèm provider request ID nếu cần điều tra.

### 11.3. Không coi mọi lỗi là validation

Database timeout, lỗi network, bug mapping hoặc dependency unavailable không phải lỗi dữ liệu client. Trả `422` cho lỗi nội bộ làm client sửa request vô ích và khiến monitoring đánh giá sai. Giữ riêng nhóm 4xx và 5xx, đồng thời theo dõi tỷ lệ lỗi theo service/endpoint.

## 12. Bảo vệ error response khỏi cache và client-side injection

Response JSON vẫn có thể được hiển thị trong web app hoặc log console. Không phản chiếu chuỗi do user gửi vào `message` mà không kiểm soát. Nếu client hiển thị message trong HTML, phải render như text hoặc escape theo ngữ cảnh; không đưa trực tiếp vào `innerHTML`.

Các nguyên tắc:

- Dùng JSON serializer chuẩn, không tự nối JSON string.
- Không trả HTML error page có nội dung exception.
- Dùng `Cache-Control: no-store` cho response chứa dữ liệu riêng tư hoặc xác thực.
- Không để CDN cache response `401`, `403` hoặc validation chứa dữ liệu user nếu cache key không bảo đảm cô lập.
- Không chứa token/PII trong URL, `instance`, redirect location hoặc header debug.
- Giới hạn số lượng lỗi field và tổng response size để request sai không tạo response khổng lồ.

## 13. Phiên bản hóa và tính ổn định của error contract

Client có thể phụ thuộc vào error code trong thời gian dài. Do đó:

- Giữ `code` ổn định qua các bản phát hành nếu semantics không đổi.
- Không yêu cầu client parse `message` để quyết định hành động.
- Thêm field mới theo cách tương thích ngược.
- Không đổi status code tùy tiện giữa `400` và `422`.
- Nếu đổi validation rule công khai, cập nhật API documentation và versioning policy.
- Câu chữ có thể được localization; code vẫn ổn định.
- Không đưa tên validator/framework vào public code.

Ví dụ client nên xử lý `EMAIL_ALREADY_IN_USE` hoặc `INVALID_LENGTH`, thay vì kiểm tra message có chứa từ `email` hay tên annotation `Size`.

## 14. Kiểm thử validation error không rò rỉ

Kiểm thử phải xác minh cả tính hữu ích lẫn việc không tiết lộ thông tin. Tạo payload chứa dữ liệu giả nhạy cảm để xác nhận chúng không xuất hiện trong response hoặc log không được phép.

| Tình huống | Kết quả mong đợi |
|---|---|
| Field bắt buộc bị bỏ trống | Public code `REQUIRED`, field công khai và message an toàn |
| Email sai định dạng | `INVALID_FORMAT`; không echo toàn bộ giá trị nếu không cần |
| JSON sai cú pháp | `400` với thông báo chung; không trả parser trace |
| Gửi field nội bộ như `passwordHash` hoặc `isAdmin` | Bị từ chối theo schema; không tiết lộ model nội bộ |
| Gửi password/token sai format | Không trả rejected value hoặc secret |
| Database unique constraint | Public domain code; không lộ SQL, table hoặc constraint name |
| Upstream trả stack trace/body nhạy cảm | API không forward raw body |
| Lỗi không dự kiến | `500` chung với trace ID; stack trace chỉ ở log bảo vệ |
| Object ID ngoài tenant | Không lộ object tồn tại hoặc tenant owner |
| Email reset không tồn tại | Response không hỗ trợ account enumeration |
| Giá trị có newline/control character | Không gây log injection |
| Giá trị rất dài/nhiều field lỗi | Response và log được giới hạn kích thước |
| Response validation | `status` trong body khớp HTTP status; đúng content type và cache policy |
| Validation fail | Không có database write, message, email hoặc side effect ngoài ý muốn |
| Client retry sau timeout | Không tạo side effect trùng nếu operation có idempotency |

### 14.1. Kiểm tra response bằng từ khóa nhạy cảm

Trong test, có thể gửi sentinel values như `TEST_SECRET_9f3...`, `FAKE_PASSWORD_...` hoặc một path giả lập rồi xác nhận chúng không xuất hiện trong response. Kiểm tra cả nested field, `detail`, `instance`, header và error extension.

Không chỉ tìm từ khóa `password` hoặc `token`; hãy kiểm tra chính giá trị secret giả đã gửi. Một response có thể không nhắc tên field nhưng vẫn echo giá trị.

### 14.2. Kiểm tra log riêng biệt

Response an toàn không chứng minh log an toàn. Dùng test logger/appender hoặc pipeline test để xác nhận secret đã được redact và control character được encode. Kiểm tra quyền truy cập log và retention ở cấp vận hành.

### 14.3. Kiểm thử enumeration

Gửi request với account/object tồn tại và không tồn tại, so sánh status, schema, message và các tín hiệu dễ quan sát. Nếu policy yêu cầu che giấu, response phải nhất quán ở mức cần thiết. Tránh tạo khác biệt rõ ràng qua timing, nhưng không hứa rằng mọi nhánh có thời gian tuyệt đối bằng nhau.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả nguyên `exception.getMessage()` | Lộ framework, SQL, path hoặc dữ liệu | Ánh xạ sang public error code/message |
| Trả stack trace trong response | Lộ class, method và dòng code | Chỉ ghi stack trace ở log bảo vệ |
| Echo rejected value | Lộ password, token, PII hoặc payload | Không trả giá trị đầu vào |
| Trả field path nội bộ | Lộ entity/model và field nhạy cảm | Allowlist public field path |
| Forward lỗi database/upstream | Lộ schema, provider detail hoặc secret | Map sang domain/public error |
| Dùng một lỗi chung cho auth và validation | Client xử lý sai, có thể lộ object | Tách `400/422`, `401`, `403/404`, `409` |
| Khác biệt response làm lộ account/object | Enumeration | Dùng response masking theo policy |
| Chỉ validate ở frontend | Request trực tiếp bypass kiểm tra | Validate tại server |
| Validate sau side effect | Request lỗi vẫn gây thay đổi | Validate/authorize trước và dùng transaction |
| Ghi toàn bộ payload vào log | Tạo kho secret thứ hai | Data minimization, masking và access control |
| Không giới hạn số lỗi | Response lớn và tốn tài nguyên | Giới hạn error count/response size |

## 16. Checklist review validation error

- [ ] API dùng một schema lỗi thống nhất và có tài liệu.
- [ ] HTTP status phản ánh đúng syntax, validation, authentication, authorization, conflict và rate limit.
- [ ] `code` ổn định; client không phải parse message hoặc tên exception.
- [ ] Field path chỉ thuộc schema công khai và được allowlist.
- [ ] Không trả rejected value, password, token, cookie, secret hoặc payload nhạy cảm.
- [ ] Không trả stack trace, SQL, table/column/constraint name, filesystem path hoặc framework detail.
- [ ] Parser/database/upstream error được ánh xạ an toàn.
- [ ] `instance`, trace ID và header không chứa query/body hoặc credential.
- [ ] Account/object enumeration được xử lý theo chính sách che giấu.
- [ ] Validation và authorization chạy trước side effect; transaction bảo vệ điều kiện trạng thái.
- [ ] DTO allowlist ngăn mass assignment; validation không thay authorization.
- [ ] Log nội bộ có correlation ID, redaction, structured logging, access control và retention.
- [ ] Response có giới hạn số lỗi/kích thước, content type đúng và cache policy phù hợp.
- [ ] Test xác nhận secret sentinel không xuất hiện trong response/log.
- [ ] Có test parser error, DB/upstream error, enumeration và không side effect khi validation fail.

Validation error an toàn không cần che giấu mọi thông tin với client. API nên nói rõ field công khai nào cần sửa và trả mã lỗi ổn định để client xử lý; đồng thời giữ stack trace, SQL, rejected value, cấu trúc framework và dữ liệu nhạy cảm trong hệ thống log được bảo vệ. Khi hợp đồng lỗi được chuẩn hóa, field được allowlist, lỗi được ánh xạ theo ngữ nghĩa và kiểm thử cả response lẫn log, API vừa dễ tích hợp vừa giảm nguy cơ biến thông báo lỗi thành kênh do thám hệ thống.
