# Chuẩn hóa phản hồi lỗi ánh xạ mà không lộ cấu trúc nội bộ

Trong ứng dụng Spring, JSON request thường được đọc bởi Jackson trước khi controller method được gọi. Nếu body sai cú pháp, không ánh xạ được vào DTO hoặc chứa giá trị không chuyển đổi được, Spring MVC thường bọc lỗi Jackson trong `HttpMessageNotReadableException`. Nếu ứng dụng trả nguyên exception message, stack trace, tên class hoặc đường dẫn property nội bộ cho client, phản hồi có thể tiết lộ cấu trúc implementation và thông tin không cần thiết.

Một API tốt cần có **hợp đồng lỗi ổn định**: status HTTP phù hợp, error code có thể được client xử lý, thông điệp công khai ngắn gọn, field path chỉ khi an toàn và request/correlation ID để tra cứu log nội bộ. Phần chi tiết kỹ thuật phải ở phía server, nơi có quyền truy cập và chính sách bảo vệ dữ liệu phù hợp.

Trong Spring MVC, có thể tập trung xử lý bằng `@RestControllerAdvice` và trả về `ProblemDetail` hoặc một error DTO thống nhất. Điều quan trọng là phân loại lỗi theo nguồn phát sinh, chỉ công khai thông tin đã được cho phép và không biến mọi exception thành lỗi 400.

## 1. Vì sao không nên trả exception Jackson trực tiếp?

Một lỗi ánh xạ có thể chứa nhiều chi tiết nội bộ:

- Tên class Java và package.
- Tên property hoặc field của DTO.
- Tên constructor, creator parameter hoặc setter.
- Kiểu Java đích như BigDecimal, LocalDate hoặc enum implementation.
- Giá trị input không hợp lệ.
- Đường dẫn file, line number hoặc thông tin thư viện.
- Stack trace và cấu trúc call stack.
- Chi tiết custom deserializer hoặc module.

Ví dụ không nên trả cho client:

~~~json
{
  "error": "com.fasterxml.jackson.databind.exc.InvalidFormatException",
  "message": "Cannot deserialize value of type `java.time.LocalDate` from String \"not-a-date\": Failed to deserialize java.time.LocalDate",
  "path": "com.example.internal.api.CreateOrderRequest[\"deliveryDate\"]"
}
~~~

Phản hồi này tiết lộ package nội bộ, kiểu Java, tên field và giá trị input. Nó còn buộc client phụ thuộc vào message của Jackson, vốn có thể thay đổi giữa các phiên bản.

Một phản hồi công khai tốt hơn:

~~~json
{
  "type": "https://api.example.test/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "The request body contains a value in an unsupported format.",
  "code": "INVALID_REQUEST",
  "requestId": "req-7f3a2"
}
~~~

Client chỉ cần biết request không hợp lệ và có mã để hiển thị hoặc xử lý. Nhóm vận hành dùng requestId để tìm exception chi tiết trong log nội bộ.

## 2. Tách lỗi cú pháp, lỗi ánh xạ và lỗi nghiệp vụ

Không phải mọi lỗi liên quan JSON đều giống nhau.

| Nhóm lỗi | Ví dụ | Thường xử lý |
|---|---|---|
| JSON syntax | Thiếu dấu ngoặc, dấu phẩy sai, string không đóng | 400 Bad Request |
| Databinding/type mismatch | Chuỗi không chuyển được thành ngày hoặc số | 400 Bad Request |
| Unknown property | JSON có field không được DTO hỗ trợ trong strict mode | 400 hoặc policy tương thích riêng |
| Validation | Field thiếu, độ dài vượt giới hạn, quantity âm | 400 hoặc 422 theo API contract |
| Unsupported media type | Content-Type không được endpoint nhận | 415 Unsupported Media Type |
| Payload too large | Body vượt giới hạn transport | 413 Payload Too Large |
| Server mapping/configuration | Serializer, DTO definition hoặc module cấu hình sai | 500 Internal Server Error |
| Business conflict | Tài nguyên đã tồn tại hoặc trạng thái không cho phép | 409 Conflict hoặc status theo contract |

Spring MVC thường đọc body qua HttpMessageConverter. Với JSON, converter dùng Jackson. Nếu Jackson không thể đọc body, lỗi xảy ra trước khi controller nhận DTO và được Spring biểu diễn bằng HttpMessageNotReadableException.

Ngược lại, một lỗi xảy ra trong business service sau khi controller đã nhận DTO không nên bị phân loại thành lỗi JSON. Cần tách các tầng để không trả status sai hoặc che giấu bug phía server.

## 3. Dùng @RestControllerAdvice làm điểm xử lý tập trung

`@RestControllerAdvice` áp dụng cho controller và ghi response body tự động. Nó là vị trí phù hợp để chuẩn hóa lỗi HTTP:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> handleUnreadableBody(
            HttpMessageNotReadableException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "The request body is invalid."
        );

        problem.setTitle("Invalid request");
        problem.setType(URI.create(
            "https://api.example.test/problems/invalid-request"
        ));
        problem.setProperty("code", "INVALID_REQUEST");

        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

Đây là ví dụ cơ bản cho Spring Framework 6 trở lên, nơi có API `ProblemDetail`. Spring Boot 3 sử dụng Spring Framework 6. Với ứng dụng Spring cũ hơn, có thể dùng một DTO lỗi riêng và trả về qua ResponseEntity.

Không cần tạo ObjectMapper mới trong exception handler. Handler chỉ tạo response đã chuẩn hóa; mapper được Spring cấu hình để đọc request vẫn được quản lý ở tầng MVC.

## 4. ProblemDetail và RFC 7807

`ProblemDetail` của Spring biểu diễn problem response theo RFC 7807. Các trường chuẩn gồm:

| Field | Ý nghĩa |
|---|---|
| type | URI định danh loại problem |
| title | Tiêu đề ngắn, ổn định |
| status | HTTP status |
| detail | Giải thích công khai cho lần xảy ra cụ thể |
| instance | URI tham chiếu đến occurrence |
| properties mở rộng | Mã lỗi, request ID hoặc metadata công khai |

Ví dụ:

~~~java
ProblemDetail problem =
    ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

problem.setType(URI.create(
    "https://api.example.test/problems/invalid-request"
));
problem.setTitle("Invalid request");
problem.setDetail("The request body could not be processed.");
problem.setProperty("code", "INVALID_REQUEST");
problem.setProperty("requestId", requestId);
~~~

Spring có thể serialize ProblemDetail thành JSON với content type phù hợp như `application/problem+json` tùy cấu hình message converter và framework version.

Các field mở rộng nên có tên và ý nghĩa ổn định. Đừng đưa tên exception class, stack trace, Java package hoặc raw Jackson message vào properties.

`type` nên là URI ổn định có tài liệu mô tả loại lỗi. Không cần tạo URI riêng cho từng request. `instance` nếu được dùng nên tham chiếu occurrence theo cách không chứa query string, token hoặc dữ liệu nhạy cảm.

## 5. Thiết kế error code ổn định

HTTP status cho biết nhóm kết quả ở mức giao thức; error code giúp client phân biệt các lỗi cụ thể.

Ví dụ:

| Code | HTTP status | Ý nghĩa công khai |
|---|---:|---|
| INVALID_JSON | 400 | Body không phải JSON hợp lệ |
| INVALID_REQUEST | 400 | Body không phù hợp hợp đồng endpoint |
| INVALID_FIELD_VALUE | 400 | Một giá trị không đúng định dạng |
| VALIDATION_FAILED | 400 hoặc 422 | Dữ liệu không thỏa ràng buộc |
| UNSUPPORTED_MEDIA_TYPE | 415 | Content-Type không được hỗ trợ |
| PAYLOAD_TOO_LARGE | 413 | Request vượt giới hạn kích thước |
| INTERNAL_ERROR | 500 | Lỗi xử lý phía server |

Chọn một quy ước và dùng nhất quán. Nếu API đã dùng 400 cho mọi lỗi validation, không tự đổi một phần endpoint sang 422. Có thể dùng 422 Unprocessable Content nếu hợp đồng API xác định rõ request cú pháp đúng nhưng nội dung không thể xử lý, song client phải được thông báo và tài liệu phải thống nhất.

Không dùng message làm mã lỗi. Message có thể thay đổi theo ngôn ngữ hoặc wording; code nên là hằng số ổn định để client có thể xử lý.

## 6. HttpMessageNotReadableException là điểm vào thường gặp

Khi Jackson không đọc được request body, Spring MVC thường ném `HttpMessageNotReadableException`. Cause bên trong có thể là:

- `JsonParseException`: lỗi cú pháp JSON.
- `JsonMappingException`: lỗi ánh xạ vào kiểu Java.
- `InvalidFormatException`: giá trị không chuyển được sang kiểu đích.
- `UnrecognizedPropertyException`: property không được nhận diện.
- `StreamConstraintsException`: vượt giới hạn parser.
- Một IOException từ nguồn input hoặc custom deserializer.

Không nên dựa vào message của HttpMessageNotReadableException để xác định lỗi. Message thường chứa nội dung từ exception lồng bên trong và có thể thay đổi theo Jackson version.

Có thể duyệt cause chain để phân loại theo kiểu exception:

~~~java
static <T extends Throwable> T findCause(
        Throwable error,
        Class<T> expectedType) {

    Set<Throwable> visited =
        Collections.newSetFromMap(new IdentityHashMap<>());

    Throwable current = error;

    while (current != null && visited.add(current)) {
        if (expectedType.isInstance(current)) {
            return expectedType.cast(current);
        }
        current = current.getCause();
    }

    return null;
}
~~~

Dùng identity set giúp tránh vòng lặp nếu custom exception có cause chain bất thường. Trong handler, có thể kiểm tra một số loại exception đã biết rồi ánh xạ sang public error code.

Không cần phân loại mọi subclass Jackson. Nếu không tìm thấy loại cụ thể, trả một thông báo invalid request tổng quát và giữ chi tiết trong log.

## 7. Phân biệt JSON syntax error với mapping error

Có thể phân loại ở mức vừa đủ:

~~~java
@ExceptionHandler(HttpMessageNotReadableException.class)
public ResponseEntity<ProblemDetail> handleUnreadableBody(
        HttpMessageNotReadableException exception) {

    JsonParseException parseError =
        findCause(exception, JsonParseException.class);

    StreamConstraintsException constraintError =
        findCause(exception, StreamConstraintsException.class);

    if (constraintError != null) {
        return problem(
            HttpStatus.BAD_REQUEST,
            "INVALID_REQUEST",
            "The request body exceeds an allowed structure or value limit."
        );
    }

    if (parseError != null) {
        return problem(
            HttpStatus.BAD_REQUEST,
            "INVALID_JSON",
            "The request body is not valid JSON."
        );
    }

    return problem(
        HttpStatus.BAD_REQUEST,
        "INVALID_REQUEST",
        "The request body does not match the expected format."
    );
}
~~~

Helper `problem` có thể tạo ProblemDetail với type, title và code chung:

~~~java
private ResponseEntity<ProblemDetail> problem(
        HttpStatus status,
        String code,
        String detail) {

    ProblemDetail body =
        ProblemDetail.forStatusAndDetail(status, detail);

    body.setTitle(status.getReasonPhrase());
    body.setProperty("code", code);

    return ResponseEntity.status(status).body(body);
}
~~~

Trong code thực tế, nên bổ sung request ID bằng một provider riêng. Ví dụ này không trả exception message hoặc raw value cho client.

Không phải mọi JsonParseException đều cần message khác nhau. Việc phân loại nên giúp client có hành động hữu ích, không tạo ra hàng chục error code phụ thuộc implementation.

## 8. StreamConstraintsException cần thông báo công khai có giới hạn

Khi cấu hình Jackson Core với `StreamReadConstraints`, parser có thể từ chối string, number hoặc cấu trúc lồng vượt giới hạn.

Ví dụ:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(80)
    .maxStringLength(500_000)
    .maxNumberLength(500)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();
~~~

Nếu client gửi payload vượt giới hạn, không nên trả nguyên message kiểu "String value length exceeds the maximum allowed" nếu không muốn công khai chính sách nội bộ. Có thể trả:

~~~json
{
  "code": "INVALID_REQUEST",
  "title": "Invalid request",
  "detail": "The request body exceeds an allowed limit.",
  "status": 400
}
~~~

Nếu giới hạn là body byte ở gateway/server, status 413 thường phù hợp hơn. Nếu giới hạn là nesting hoặc token parser, có thể giữ 400 theo hợp đồng API. Hãy thống nhất cách phân loại với gateway và client.

Không tự động đổi mọi StreamConstraintsException thành 413 nếu giới hạn đó không phải body size.

## 9. Unknown property và field name không đáng tin cậy

Khi bật `FAIL_ON_UNKNOWN_PROPERTIES`, Jackson có thể ném `UnrecognizedPropertyException`. Exception này có thể chứa tên property mà client gửi.

Tên đó là dữ liệu không đáng tin cậy. Nó có thể rất dài, chứa ký tự điều khiển, có nội dung nhạy cảm do client vô tình gửi hoặc trùng với tên field nội bộ.

Không nên echo tên property tùy ý vào response hoặc log mà không giới hạn. Cách an toàn mặc định là trả lỗi tổng quát:

~~~json
{
  "code": "INVALID_REQUEST",
  "detail": "The request contains a field that is not supported."
}
~~~

Nếu API cần chỉ ra field, hãy dùng allowlist tên public field. Ví dụ ánh xạ internal property sang tên wire đã công bố:

~~~java
private static final Map<String, String> PUBLIC_FIELD_NAMES =
    Map.of(
        "deliveryDate", "deliveryDate",
        "quantity", "quantity"
    );

static Optional<String> publicFieldName(String internalName) {
    return Optional.ofNullable(PUBLIC_FIELD_NAMES.get(internalName));
}
~~~

Nếu không có mapping, không trả tên field. Đừng giả định tên property trong exception luôn là tên public JSON; mix-in, naming strategy và alias có thể làm tên wire khác tên Java.

## 10. InvalidFormatException và giá trị input

`InvalidFormatException` có thể chứa giá trị không chuyển đổi được và target type.

Ví dụ client gửi:

~~~json
{
  "deliveryDate": "tomorrow-ish"
}
~~~

Jackson có thể báo không thể chuyển string thành LocalDate. Không trả `getValue()` hoặc `getTargetType().getName()` cho client. Giá trị có thể chứa token, PII hoặc dữ liệu lớn; kiểu đích có thể tiết lộ model nội bộ.

Có thể trả public field path đã được kiểm soát và một thông báo chung:

~~~json
{
  "code": "INVALID_FIELD_VALUE",
  "detail": "A field contains a value in an unsupported format.",
  "field": "deliveryDate"
}
~~~

Nếu field không nằm trong public allowlist, bỏ field property khỏi response và chỉ trả INVALID_REQUEST.

Nếu API cần thông báo kiểu dữ liệu, dùng từ ngữ theo hợp đồng như "must be a date in YYYY-MM-DD format", không trả tên class Java.

## 11. Không trả JsonMappingException.getPath() trực tiếp

`JsonMappingException` có thể cung cấp path gồm field name và index. Path rất hữu ích cho debug nội bộ, nhưng không phải lúc nào cũng an toàn để công khai.

Ví dụ path nội bộ có thể chứa tên property Java không phải tên wire, nested class hoặc property không được public API công bố, key động do client gửi, index cực lớn hoặc chuỗi field rất dài.

Có thể dùng path để tra cứu log, nhưng public field path nên được tạo qua allowlist. Nếu cần trả nested path, map từng segment qua schema public và giới hạn độ dài/tổng số segment.

Không nên gọi `exception.getPathReference()` rồi đưa nguyên chuỗi vào response. Chuỗi đó được tạo từ dữ liệu mapping và có thể chứa tên property hoặc key do client kiểm soát.

## 12. Chuẩn hóa lỗi Bean Validation

Lỗi validation thường xảy ra sau khi Jackson đã tạo DTO. Trong Spring MVC, `@Valid` hoặc `@Validated` trên request body có thể dẫn đến `MethodArgumentNotValidException`.

Ví dụ controller:

~~~java
@PostMapping("/orders")
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

DTO:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerName,
    @Min(1) @Max(100) int quantity
) {}
~~~

Handler có thể chuyển FieldError thành danh sách lỗi công khai:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
public ResponseEntity<ProblemDetail> handleValidation(
        MethodArgumentNotValidException exception) {

    List<Map<String, String>> errors =
        exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(this::toPublicFieldError)
            .filter(Objects::nonNull)
            .limit(20)
            .toList();

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "One or more fields failed validation."
    );
    problem.setTitle("Validation failed");
    problem.setProperty("code", "VALIDATION_FAILED");
    problem.setProperty("errors", errors);

    return ResponseEntity.badRequest().body(problem);
}
~~~

Giới hạn số lỗi trả về để một request có rất nhiều vi phạm không tạo response quá lớn. Không trả toàn bộ BindingResult hoặc exception object.

## 13. Tạo public validation message thay vì dùng default message

`FieldError.getDefaultMessage()` có thể chứa message nội bộ, tên constraint, placeholder hoặc nội dung được tạo từ dữ liệu đầu vào. Không nên mặc định đưa message này ra public API.

Tạo mapping từ validation code sang thông báo công khai:

~~~java
private Map<String, String> toPublicFieldError(FieldError error) {
    Optional<String> field = publicFieldName(error.getField());

    if (field.isEmpty()) {
        return null;
    }

    String code = error.getCode();

    String message = switch (code == null ? "" : code) {
        case "NotBlank", "NotNull" -> "This field is required.";
        case "Size" -> "This field has an invalid length.";
        case "Min", "Max", "Positive" ->
            "This field is outside the allowed range.";
        case "Email" -> "This field must contain a valid email address.";
        default -> "This field is invalid.";
    };

    return Map.of(
        "field", field.get(),
        "code", safeValidationCode(code),
        "message", message
    );
}
~~~

Helper `safeValidationCode` nên trả một code thuộc allowlist, không trả tên class hoặc message tùy ý. Có thể dùng các code như REQUIRED, INVALID_LENGTH, OUT_OF_RANGE và INVALID_FORMAT.

Không đưa rejected value vào response. Một lỗi email không cần echo email; lỗi password không bao giờ nên trả lại password; lỗi số tài khoản không cần hiển thị giá trị đã gửi.

## 14. Phân biệt lỗi deserialize với lỗi validation

Jackson có thể từ chối trước khi DTO được tạo, ví dụ `quantity` nhận string không chuyển được thành int. Bean Validation chạy sau khi binding và có thể kiểm tra quantity nằm trong khoảng 1 đến 100.

Hai trường hợp khác nhau:

~~~json
{"quantity":"many"}
~~~

Đây là lỗi type conversion trong quá trình binding.

~~~json
{"quantity":1000}
~~~

Nếu kiểu int đọc được nhưng vượt @Max(100), đây là lỗi validation.

Nên dùng error code riêng nếu client cần xử lý khác nhau, ví dụ INVALID_FIELD_VALUE và VALIDATION_FAILED. Cả hai vẫn có thể trả 400 nếu API contract quy định validation error là 400.

Không bắt mọi lỗi rồi trả "Validation failed". Làm vậy khiến client và nhóm vận hành khó phân biệt JSON sai cú pháp, kiểu dữ liệu sai và vi phạm quy tắc nghiệp vụ.

## 15. Method validation và ConstraintViolationException

Ngoài validation trên request body, Spring còn có method validation cho tham số controller hoặc service. Tùy Spring Framework version và cách kích hoạt, lỗi có thể là `HandlerMethodValidationException` hoặc `ConstraintViolationException`.

Không nên giả định tất cả lỗi validation đều là MethodArgumentNotValidException. Hãy xử lý những loại mà ứng dụng thực sự sử dụng:

~~~java
@ExceptionHandler(ConstraintViolationException.class)
public ResponseEntity<ProblemDetail> handleConstraintViolation(
        ConstraintViolationException exception) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "One or more request parameters are invalid."
    );
    problem.setTitle("Validation failed");
    problem.setProperty("code", "VALIDATION_FAILED");

    return ResponseEntity.badRequest().body(problem);
}
~~~

`ConstraintViolation.getPropertyPath()` có thể chứa tên class, method và tham số nội bộ. Không trả nguyên path đó. Nếu cần chỉ ra query parameter hoặc path variable, dùng metadata public của endpoint hoặc mapping allowlist.

Với `HandlerMethodValidationException` trong Spring Framework 6.1+, có thể viết handler riêng và trích xuất lỗi theo API tương ứng. Nếu ứng dụng dùng version cũ hơn, không tham chiếu type chưa có trong classpath.

## 16. Các lỗi HTTP khác cần xử lý nhất quán

Chuẩn hóa lỗi ánh xạ không có nghĩa chỉ xử lý Jackson. Một API thường cần quy ước cho:

| Exception / tình huống | Status thường dùng |
|---|---:|
| HttpMessageNotReadableException | 400 |
| MethodArgumentNotValidException | 400 hoặc 422 |
| HttpMediaTypeNotSupportedException | 415 |
| HttpMediaTypeNotAcceptableException | 406 |
| MissingServletRequestParameterException | 400 |
| MethodArgumentTypeMismatchException | 400 |
| MaxUploadSizeExceededException | 413 |
| NoHandlerFoundException / route không tồn tại | 404 |
| AccessDeniedException | 403 |
| AuthenticationException | 401 |
| DataIntegrityViolationException | 409 hoặc lỗi domain tương ứng |
| Unexpected Exception | 500 |

Status cụ thể còn phụ thuộc cấu hình Spring, container, security filter và API contract. Một số lỗi upload/body size có thể bị chặn ở proxy hoặc servlet container trước khi đi đến controller advice.

Không nên ánh xạ tất cả exception sang 400. Lỗi cấu hình mapper hoặc lỗi database là vấn đề server; trả 400 sẽ khiến client nghĩ họ cần sửa request và làm sai số liệu vận hành.

## 17. Lỗi body quá lớn có thể xảy ra ngoài controller advice

Giới hạn request body có thể được thực thi ở:
- API gateway hoặc reverse proxy.
- Servlet container.
- Multipart resolver.
- Filter đọc body.
- Bounded InputStream.
- Jackson StreamReadConstraints.

Nếu gateway trả 413 trước khi request tới ứng dụng, `@RestControllerAdvice` không thể thay đổi response đó. Muốn response nhất quán, cần cấu hình error response ở gateway/server hoặc dùng một contract chấp nhận khác biệt có tài liệu.

Phân biệt body byte limit với parser constraint:
- Body byte limit thường có thể trả 413 Payload Too Large.
- Nesting/string/number constraint là giới hạn cấu trúc/token, thường được phân loại là invalid request theo contract.
- Giới hạn collection nghiệp vụ thường là validation hoặc request error.

Không báo 413 cho mọi lỗi parser chỉ vì chúng đều liên quan đến "quá lớn".

## 18. Fallback cho lỗi không mong đợi

Nên có một handler cuối cùng cho exception không được xử lý cụ thể:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<ProblemDetail> handleUnexpected(
        Exception exception,
        HttpServletRequest request) {

    String requestId = requestIdProvider.currentRequestId();

    log.error(
        "Unhandled request failure, requestId={}",
        requestId,
        exception
    );

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.INTERNAL_SERVER_ERROR,
        "The server could not complete the request."
    );
    problem.setTitle("Internal server error");
    problem.setProperty("code", "INTERNAL_ERROR");
    problem.setProperty("requestId", requestId);

    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
        .body(problem);
}
~~~

Stack trace chỉ xuất hiện trong log nội bộ. Response không chứa exception message, class name hoặc cause.

Không nên bắt Throwable để biến mọi lỗi thành JSON response. Những lỗi nghiêm trọng như OutOfMemoryError hoặc lỗi JVM không nên bị xử lý như một request validation thông thường. Fallback nên bắt Exception hoặc các nhóm exception phù hợp với kiến trúc.

Đảm bảo handler cụ thể hơn được khai báo và được Spring chọn đúng. Một fallback quá rộng có thể che các handler chuyên biệt nếu cấu hình advice hoặc thứ tự advice không đúng.

## 19. Request ID và correlation ID

Client cần một mã để liên hệ với support hoặc tra cứu trạng thái request. Có thể dùng trace ID từ Micrometer Tracing/OpenTelemetry hoặc tạo request ID tại filter.

Quy tắc:
- Mỗi request có một correlation ID ổn định trong suốt pipeline.
- Đưa ID vào MDC để log tự động gắn kèm.
- Trả ID trong ProblemDetail.
- Nếu chấp nhận header từ client, validate độ dài và ký tự.
- Không dùng request ID làm metric label.
- Không đưa token hoặc thông tin xác thực vào ID.

Ví dụ tạo ID đơn giản trong servlet filter:

~~~java
public class RequestIdFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Request-Id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();

        MDC.put("requestId", requestId);
        response.setHeader(HEADER, requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Ví dụ này luôn sinh ID ở server. Nếu cần chấp nhận ID do gateway gửi, hãy kiểm tra allowlist ký tự và độ dài, rồi quyết định có giữ hay thay thế. Không phản chiếu header tùy ý vào response.

Nếu ứng dụng đã có tracing infrastructure, ưu tiên tái sử dụng trace context thay vì tạo nhiều ID cạnh tranh. Request ID và trace ID có thể khác mục đích; tài liệu API nên xác định trường nào client cần gửi cho support.

## 20. Logging an toàn cho lỗi mapping

Log nội bộ cần đủ thông tin để điều tra nhưng không ghi dữ liệu nhạy cảm.

Với lỗi request dự kiến:
- Log ở mức INFO/WARN hoặc mức đã thống nhất.
- Ghi endpoint group, error code, exception class và request ID.
- Có thể ghi JsonLocation hoặc public field path đã làm sạch.
- Không ghi raw request body.
- Không ghi rejected value.
- Không ghi toàn bộ exception message nếu message chứa input.

Với lỗi server bất ngờ:
- Log stack trace một lần ở boundary phù hợp.
- Gắn request ID và trace ID.
- Không log lại cùng exception ở mọi layer.
- Giữ cause để điều tra.

Một log event tốt:

~~~text
event=request_mapping_failed
requestId=req-7f3a2
endpoint=create-order
errorCode=INVALID_FIELD_VALUE
exceptionType=InvalidFormatException
locationLine=1
locationColumn=42
~~~

Đây là ví dụ cấu trúc. Nếu tên field/path có thể chứa dữ liệu client, chỉ ghi sau khi giới hạn và làm sạch. Không dùng exception message làm metric tag vì message có thể chứa giá trị động và tạo high cardinality.

## 21. Sanitization và giới hạn kích thước metadata lỗi

Ngay cả metadata tưởng như vô hại cũng có thể do client kiểm soát. Tên property, map key, path segment và query parameter có thể rất dài hoặc chứa ký tự điều khiển.

Khi đưa field path vào response:
- Chỉ dùng tên field đã công bố trong API schema.
- Giới hạn số segment.
- Giới hạn tổng chiều dài.
- Loại bỏ ký tự điều khiển.
- Không đưa map key động vào path công khai nếu không cần.
- Nếu không xác định được public path, bỏ field và trả lỗi tổng quát.

Khi trả danh sách validation errors:
- Giới hạn số lỗi.
- Giới hạn chiều dài mỗi message.
- Sắp xếp ổn định nếu client cần output deterministic.
- Không trả rejected value.
- Không để duplicate violation tạo response quá lớn.

Nếu API dùng nested field như `items[2].quantity`, có thể cho phép path theo schema và index trong phạm vi hợp lệ. Không nối trực tiếp mọi segment từ exception vào một chuỗi mà không kiểm soát.

## 22. Không để lỗi handler tự tạo lỗi thứ hai

Exception handler cũng là code ứng dụng và có thể thất bại. Ví dụ:
- Lấy request ID từ bean chưa khởi tạo.
- Serialize một object error không được Jackson hỗ trợ.
- Dùng message source với code không tồn tại.
- Đọc body lần thứ hai sau khi stream đã bị tiêu thụ.
- Tạo ProblemDetail extension chứa object phức tạp hoặc cyclic.

Giữ error response đơn giản: string, number, boolean và list/map nhỏ có cấu trúc rõ. Đừng đưa exception object hoặc DTO request vào ProblemDetail.

Nếu handler cần localize message, hãy dùng message catalog với fallback an toàn. Nếu lookup thất bại, vẫn trả được một detail tổng quát. Không để việc dịch thông báo làm mất response lỗi chính.

Cũng cần đảm bảo logging trong handler không ném thêm exception. Nếu log appender đang lỗi, response công khai vẫn nên được tạo khi có thể.

## 23. Cấu hình ObjectMapper trong Spring Boot

Spring Boot thường auto-configure ObjectMapper và các HttpMessageConverter dựa trên classpath, properties và bean tùy chỉnh. Nếu ứng dụng cần cấu hình Jackson, hãy dùng cơ chế builder/customizer hoặc bean theo version Boot đang sử dụng.

Ví dụ:

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.failOnUnknownProperties(true);
            builder.featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
            );
        };
    }
}
~~~

API customizer có thể khác theo Spring Boot version. Dùng cùng mapper configuration cho request handling và integration tests.

Không tạo một ObjectMapper riêng trong controller hoặc advice để parse lại body. Làm vậy có thể bỏ qua JavaTimeModule, naming strategy, mix-in, constraints và custom modules đã cấu hình cho MVC.

Nếu cần factory riêng cho endpoint đặc biệt, hãy gắn rõ vào HttpMessageConverter phù hợp và kiểm thử đường request thật. Chỉ khai báo một bean JsonFactory không bảo đảm converter đang dùng nó nếu cấu hình MVC đã được tùy biến.

## 24. Quan hệ giữa @ControllerAdvice và Spring Security

Một số lỗi xảy ra trước khi request vào controller, chẳng hạn authentication hoặc authorization ở security filter chain. Các lỗi này thường không đi qua cùng đường xử lý với HttpMessageNotReadableException.

Để response thống nhất:
- Cấu hình AuthenticationEntryPoint cho 401.
- Cấu hình AccessDeniedHandler cho 403.
- Dùng ControllerAdvice cho lỗi MVC sau khi request được dispatch.
- Cấu hình gateway/proxy cho lỗi 413/502/504 nếu cần.
- Dùng cùng error code/schema ở các lớp nếu hợp đồng yêu cầu.

Không đưa chi tiết principal, role nội bộ, token validation hoặc policy security vào response. Một lỗi 401 nên nói rằng cần xác thực; một lỗi 403 nên nói rằng thao tác không được phép. Không xác nhận tài nguyên có tồn tại nếu điều đó có thể tiết lộ thông tin cho người chưa được phép.

## 25. Kiểm thử response bằng MockMvc

Kiểm thử handler nên xác nhận status, content type, error code và việc không lộ thông tin nội bộ.

Ví dụ kiểm tra JSON sai cú pháp:

~~~java
@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderControllerErrorTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsSafeProblemForMalformedJson() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            ))
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(jsonPath("$.detail").exists())
            .andExpect(jsonPath("$.trace").doesNotExist())
            .andExpect(jsonPath("$.exception").doesNotExist());
    }
}
~~~

Ví dụ giả định handler phân loại JsonParseException thành INVALID_JSON và Spring version serialize ProblemDetail với media type application/problem+json. Tùy test setup và version, có thể cần cấu hình converter hoặc kiểm tra content type theo contract đang dùng.

Đừng chỉ assert status 400. Một handler có thể trả đúng status nhưng vô tình chứa stack trace hoặc raw input trong body.

## 26. Kiểm thử validation và field allowlist

Một test validation nên kiểm tra:
- Status và error code.
- Chỉ public field path được xuất hiện.
- Message thuộc danh sách công khai.
- Rejected value không xuất hiện.
- Số lỗi trả về không vượt giới hạn.

Ví dụ:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerName": "",
              "quantity": 0
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.errors.length()").value(2))
    .andExpect(jsonPath("$.errors[0].message").exists());
~~~

Không phụ thuộc thứ tự FieldError nếu Spring/validator không đảm bảo thứ tự. Nếu API yêu cầu output ổn định, sort errors theo public field và code trước khi serialize.

Thêm test với unknown field có tên dài hoặc chứa ký tự bất thường để bảo đảm handler không echo tên đó. Thêm test với password/token sai format để chắc chắn rejected value không xuất hiện trong response hoặc log được thu thập ở test.

## 27. Kiểm tra lỗi server không bị giả thành lỗi client

Một handler fallback phải trả 500 với thông điệp tổng quát:

~~~java
mockMvc.perform(get("/test/unexpected-error"))
    .andExpect(status().isInternalServerError())
    .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
    .andExpect(jsonPath("$.detail").value(
        "The server could not complete the request."
    ))
    .andExpect(jsonPath("$.stackTrace").doesNotExist());
~~~

Test cần xác nhận exception nội bộ vẫn được log với request ID trong môi trường test phù hợp, nhưng không xuất hiện trong response.

Đừng kiểm tra message nguyên văn của Jackson trong test API. Hãy kiểm tra public code/status/shape để có thể nâng Jackson mà không phá contract client.

## 28. Kiểm thử cấu hình thực tế và các đường đi khác nhau

@WebMvcTest hữu ích cho slice MVC nhưng không luôn tải đầy đủ:
- Security filter chain.
- Gateway/container body limit.
- Custom HttpMessageConverter.
- ObjectMapper production bean.
- MessageSource hoặc tracing integration.

Bổ sung integration test khi các lớp này ảnh hưởng error response. Cần test cả:
- JSON malformed.
- JSON hợp lệ nhưng sai kiểu.
- Unknown property.
- Validation failure.
- Missing body.
- Unsupported Content-Type.
- Body quá lớn ở tầng server/gateway nếu test environment hỗ trợ.
- Lỗi service bất ngờ.
- Lỗi authentication/authorization.

Mỗi lỗi có thể phát sinh ở tầng khác nhau. Một bộ test chỉ gọi controller method trực tiếp sẽ bỏ qua Jackson HttpMessageConverter và không xác nhận hành vi mapping thật.

## 29. Tài liệu hóa error contract cho client

OpenAPI hoặc API reference nên mô tả:
- Status HTTP có thể trả.
- Problem response schema.
- Danh sách error code ổn định.
- Trường nào luôn có và trường nào optional.
- Field path có thể vắng mặt khi không an toàn hoặc không xác định.
- Request ID dùng để liên hệ support.
- Quy tắc retry cho lỗi tạm thời và lỗi request.

Ví dụ contract:

~~~yaml
Problem:
  type: object
  required:
    - title
    - status
    - code
    - requestId
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
    code:
      type: string
    requestId:
      type: string
    field:
      type: string
~~~

Schema này chỉ là ví dụ. Nếu dùng RFC 7807, hãy giữ các field chuẩn tương ứng và định nghĩa properties mở rộng rõ ràng. Client nên dựa vào status và code, không parse message tự do hoặc phụ thuộc vào tên exception.

Khi thêm error code mới, hãy cân nhắc backward compatibility. Không đổi code hiện tại chỉ vì Jackson đổi subclass exception hoặc message.

## 30. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách làm phù hợp |
|---|---|---|
| Trả exception.getMessage() | Lộ kiểu Java, field và input | Message công khai cố định |
| Trả stack trace | Lộ package, class và cấu trúc hệ thống | Chỉ log nội bộ |
| Trả rejected value | Có thể lộ password, token hoặc PII | Không echo giá trị |
| Trả nguyên JsonMappingException path | Lộ property/key nội bộ | Public field allowlist |
| Bắt mọi exception rồi trả 400 | Che lỗi server | Phân loại 4xx và 5xx |
| Dùng message làm error code | Client phụ thuộc wording/version | Code ổn định |
| Log raw body cho mọi lỗi | Rủi ro dữ liệu và log volume | Log metadata đã làm sạch |
| Dùng một handler riêng cho từng DTO | Logic lỗi bị phân tán | Advice tập trung và mapping theo contract |
| Tạo ObjectMapper trong advice | Khác cấu hình MVC production | Dùng mapper được Spring quản lý |
| Trả hàng nghìn validation errors | Response lớn và tốn tài nguyên | Giới hạn số lỗi |

## 31. Quy trình triển khai

Khi chuẩn hóa lỗi Jackson trong Spring:

1. Xác định các tầng có thể từ chối request: gateway, servlet container, message converter, Databind, validation và business layer.
2. Chọn error schema thống nhất, ưu tiên ProblemDetail nếu Spring version hỗ trợ.
3. Định nghĩa HTTP status và error code ổn định.
4. Tạo @RestControllerAdvice để xử lý lỗi MVC.
5. Phân loại HttpMessageNotReadableException theo cause type, không theo message.
6. Map parser constraint, syntax và type mismatch thành public response tổng quát.
7. Chỉ công khai field path qua allowlist.
8. Chuẩn hóa MethodArgumentNotValidException và method validation.
9. Giữ lỗi server ở 500 và log stack trace nội bộ một lần.
10. Gắn request/correlation ID xuyên suốt request.
11. Không log raw body, rejected value hoặc metadata không giới hạn.
12. Cấu hình Security/gateway error handlers cho các lỗi phát sinh ngoài MVC.
13. Kiểm thử bằng MockMvc và integration tests qua HttpMessageConverter thật.
14. Tài liệu hóa error code và schema cho client.

## Kết luận

Chuẩn hóa phản hồi lỗi ánh xạ trong Spring giúp client nhận được một hợp đồng ổn định mà không phụ thuộc vào Jackson internals. `@RestControllerAdvice` là điểm tập trung phù hợp cho lỗi MVC; `ProblemDetail` giúp biểu diễn status, title, detail và error code theo cấu trúc chuẩn. `HttpMessageNotReadableException` cần được phân loại qua cause chain, còn validation errors cần được chuyển thành public field path và message đã kiểm soát.

Không trả exception message, stack trace, Java type, raw input hoặc mapping path nội bộ cho client. Dùng error code ổn định, request ID để tra cứu log, giới hạn metadata lỗi và tách rõ lỗi client với lỗi server. Kiểm thử cả malformed JSON, mapping, validation, body limit, security và fallback để bảo đảm response công khai an toàn, nhất quán và hữu ích.

