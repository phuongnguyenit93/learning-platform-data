# Spring MVC — Phân loại lỗi đầu vào, lỗi nghiệp vụ và lỗi hệ thống

## 1. Mục tiêu

Một REST API tốt cần trả lỗi có ý nghĩa cho client mà vẫn giữ kín chi tiết nội bộ. Trong Spring MVC, cùng một HTTP 400 hay 500 có thể xuất phát từ những tầng xử lý khác nhau. **Phân loại lỗi theo nguyên nhân và trách nhiệm khắc phục** giúp chọn HTTP status, vị trí bắt exception, dữ liệu trả về, log và cơ chế retry phù hợp.

Sau bài này, bạn có thể:

- Phân biệt **lỗi đầu vào** (request không hợp lệ), **lỗi nghiệp vụ** (request hiểu được nhưng vi phạm quy tắc/trạng thái domain) và **lỗi hệ thống** (hạ tầng, lỗi lập trình, dependency không đáp ứng).
- Chọn HTTP status có cơ sở: 400, 401, 403, 404, 409, 415, 422, 429, 500, 502, 503, 504; tránh coi mọi lỗi là 400 hoặc 500.
- Xác định điểm phát sinh lỗi trong luồng Spring MVC và xử lý với `@RestControllerAdvice`, `@ExceptionHandler`, `ResponseEntity`, `ProblemDetail` hoặc `ResponseEntityExceptionHandler`.
- Thiết kế JSON error contract có `code` ổn định, `message` an toàn, danh sách lỗi field và thông tin tương quan để quan sát.
- Tách lỗi validation/binding khỏi lỗi domain/service, không làm rò dữ liệu nhạy cảm; đặt retry đúng chỗ và kiểm thử các tình huống.
- Xây dựng ví dụ Spring Boot 3.5.0, Spring Framework 6.2, Java 17+ có lỗi 400/404/409/422/503 và test MockMvc.

**Phạm vi:** Spring MVC Servlet stack. Lỗi bảo mật do Spring Security, sự cố mạng tại gateway và Spring WebFlux có các điểm xử lý bổ sung, sẽ được phân biệt khi cần. Đây là tài liệu kỹ thuật về xử lý lỗi, không phải bộ mã trạng thái bắt buộc cho mọi API: hợp đồng HTTP phải khớp ngữ nghĩa tài nguyên và nghiệp vụ thực tế.

## 2. Ba nhóm lỗi: nhận diện bằng nguyên nhân

| Nhóm | Bản chất | Ví dụ cụ thể | Ai thường khắc phục? | HTTP thường gặp |
| --- | --- | --- | --- | --- |
| **Lỗi đầu vào** | HTTP request sai cú pháp, định dạng, kiểu dữ liệu hoặc ràng buộc của API | JSON hỏng, query `page=abc`, body thiếu field bắt buộc, số lượng âm, sai Content-Type | Client cần sửa request | 400, 415, đôi khi 422 |
| **Lỗi nghiệp vụ** | Request đọc được, nhưng hành động không được phép theo quy tắc/trạng thái domain, hoặc resource không tồn tại | Hủy đơn đã hủy, vượt hạn mức đơn hàng, mã coupon hết hiệu lực, id không tồn tại | Client điều chỉnh hành động/dữ liệu hoặc đợi trạng thái thay đổi | 404, 409, 422 (tùy tình huống) |
| **Lỗi hệ thống** | Dịch vụ không thể thực hiện vì lỗi bất ngờ hoặc hạ tầng/downstream | DB không kết nối được, timeout service khác, lỗi lập trình, cạn tài nguyên | Server/operations; client có thể retry có điều kiện | 500, 502, 503, 504 |

**Hai nhận xét quan trọng:**

1. **HTTP 4xx không đồng nghĩa tất cả đều là "validation error".** 401/403 là authentication/authorization; 404 là resource không tìm thấy; 409 là trạng thái xung đột; 415 là media type.
2. **Lỗi domain không tự động là 422.** Nếu hai thao tác cùng sửa một resource tạo xung đột trạng thái, 409 thường diễn tả tốt hơn. Nếu resource không tồn tại, 404 hợp lý. Một rule không thể đáp ứng dù request có cú pháp hợp lệ có thể chọn 422. Hãy quy định ổn định theo contract.

Ví dụ luồng đặt hàng:

- `POST /orders` với `{"sku":"ABC","quantity":"abc"}` → không chuyển quantity thành số được → **đầu vào** (400).
- `POST /orders` với `{"sku":"ABC","quantity":0}`, trong DTO có `@Min(1)` → **đầu vào** (400).
- `POST /orders` với `{"sku":"ABC","quantity":11}`, khi quy tắc đơn tối đa 10 sản phẩm → **nghiệp vụ** (có thể 422).
- `POST /orders/15/cancel` nhưng đơn đã hủy → **xung đột trạng thái nghiệp vụ** (409).
- Không kết nối được database khi tạo đơn → **hệ thống** (500 hoặc 503 nếu dịch vụ tạm thời không sẵn sàng và có chính sách phù hợp).

Phân loại phải dựa trên quy tắc đã xác định, không suy luận tùy tiện từ exception class. Một `IllegalArgumentException` có thể đến từ bug hoặc kiểm tra dữ liệu có chủ ý; đừng tự động ánh xạ tất cả sang 400.

## 3. Điểm phát sinh lỗi trong Spring MVC

~~~text
Client
  |
  v
Servlet Filters / Security Filters
  |  authentication / authorization
  v
DispatcherServlet -> Handler Mapping
  |  404, 405, 415, 406 tùy route, method, media type
  v
Argument Resolution + HttpMessageConverter / Data Binding
  |  JSON parse, missing parameter, type mismatch
  v
Bean Validation (@Valid, constraints)
  |  input field errors / method validation
  v
Controller -> Service -> Domain
  |  resource missing, rule violation, state conflict
  v
Repository / Database / External Service
  |  timeout, unavailable, unexpected errors
  v
Return Value Handling + Response Serialization
  |  JSON serialization, content negotiation failures
  v
HTTP Response
~~~

Từ sơ đồ trên:

- Lỗi parse JSON có thể xảy ra **trước khi controller method được gọi**, nên `try/catch` bên trong handler không bắt được lỗi đó.
- `@RestControllerAdvice` xử lý nhiều exception từ Spring MVC handler invocation, nhưng không thay thế xử lý exception phát sinh trực tiếp trong Security filter chain.
- Không nên catch exception ở mọi layer rồi trả 200 với `{"success":false}`; như vậy phá nghĩa HTTP, metrics và nhiều HTTP client.
- Service không nên phụ thuộc chặt vào `ResponseEntity` hoặc mã status HTTP; service có thể ném **domain exception có ý nghĩa**, lớp web ánh xạ nó thành status.
- Lỗi hệ thống phát sinh trong quá trình **ghi response body** có thể xảy ra khi headers đã gửi, lúc đó server không bảo đảm còn đổi response thành JSON lỗi chuẩn được.

## 4. Lỗi đầu vào: phân tầng rõ ràng

### 4.1. Sai cú pháp HTTP/JSON và media type

Ví dụ request hỏng:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"sku":"JAVA-17","quantity":
~~~

Đây là JSON chưa hoàn chỉnh, Jackson không thể deserialize. Spring MVC thường ném `HttpMessageNotReadableException` và trả **400 Bad Request**.

Nếu endpoint khai báo `consumes="application/json"` nhưng client gửi `text/plain`, Spring có thể trả **415 Unsupported Media Type**. Nếu client yêu cầu response `Accept: application/xml` mà API chỉ có JSON, có thể là **406 Not Acceptable**. Không gộp 415 và 406 vào 400.

### 4.2. Sai kiểu dữ liệu

~~~java
@GetMapping("/api/orders/{id}")
public OrderDto find(@PathVariable long id) {
    return service.find(id);
}
~~~

Request `GET /api/orders/abc` khớp route có biến id, nhưng không thể chuyển `abc` sang `long`. Spring MVC thường dùng `MethodArgumentTypeMismatchException` trong tình huống này, dẫn đến HTTP 400. Đây là **lỗi binding đầu vào**, không phải "không tìm thấy đơn id abc".

Với `@RequestBody` JSON `{"quantity":"many"}` khi target là `Integer`, lỗi thường xuất hiện từ Jackson và được Spring bọc trong `HttpMessageNotReadableException`. Phân biệt nguồn lỗi dù cả hai đều có thể trả 400.

### 4.3. Validation sau khi bind thành công

DTO:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}
~~~

Handler:

~~~java
@PostMapping("/api/orders")
public OrderDto create(@Valid @RequestBody CreateOrderRequest request) {
    return service.create(request);
}
~~~

Import `jakarta.validation.Valid`. Đây là đoạn handler minh họa, project chạy độc lập nằm ở mục 10.

- `quantity=0`: JSON parse thành Integer thành công, nhưng không qua `@Min(1)`.
- `quantity=null` hoặc thiếu field: không qua `@NotNull`.
- `sku=""`: không qua `@NotBlank`.
- `quantity="abc"`: có thể thất bại ngay ở Jackson deserialization, trước khi tới Bean Validation.

Trong Spring MVC, `@Valid @RequestBody` thường phát sinh `MethodArgumentNotValidException` khi object validation thất bại. Khi validation áp dụng lên các method arguments khác (ví dụ constraint trực tiếp trên parameter), Spring MVC từ 6.1 có thể dùng `HandlerMethodValidationException`. Với method validation trong Spring MVC, cần thiết kế exception handling tính tới cả hai thay vì mặc định luôn bắt một class. Controller có class-level `@Validated` có thể kích hoạt đường AOP validation khác; xem tài liệu framework theo phiên bản.

### 4.4. Những lỗi validation thực tế cần tránh

- Dùng primitive `int` khi cần phân biệt "không gửi" và `0`; DTO có `Integer` + `@NotNull` biểu diễn rõ hơn.
- Chỉ dùng `@NotNull` cho String rồi tưởng từ chối `""`; sử dụng `@NotBlank` khi cần chữ không rỗng/không toàn khoảng trắng.
- Cho rằng Bean Validation thay thế kiểm tra nghiệp vụ hoặc phân quyền.
- Trả rejected values nguyên văn trong response error: có thể chứa token, thông tin cá nhân hoặc chuỗi quá dài.
- Dùng message validation làm code lỗi ổn định cho client; nội dung message có thể được nội địa hóa hoặc thay đổi.

## 5. Lỗi nghiệp vụ: diễn tả vi phạm domain một cách tường minh

Ví dụ các quy tắc ở service:

~~~java
public OrderDto cancel(long orderId) {
    OrderDto order = repository.find(orderId);
    if (order == null) {
        throw new OrderNotFoundException("Order not found");
    }
    if ("CANCELLED".equals(order.status())) {
        throw new OrderConflictException("Order is already cancelled");
    }
    return repository.cancel(orderId);
}
~~~

Đây là pseudocode Java trong ngữ cảnh service có `repository`; dự án đầy đủ ở mục 10 dùng memory store có thể chạy. Cách tách exception:

| Domain condition | Exception có ý nghĩa | HTTP mapping có thể dùng |
| --- | --- | --- |
| Không tìm thấy order id | `OrderNotFoundException` | 404 |
| Hủy order đã hủy | `OrderConflictException` | 409 |
| Số lượng vượt hạn mức business | `OrderRuleException` | 422 |
| Thao tác được phép nhưng actor không có quyền | Authorization failure | 403, tùy Spring Security |
| Resource bị thay đổi theo version và cập nhật cũ | Version/optimistic lock conflict | 409 hoặc precondition 412 nếu dùng `If-Match` |
| Duplicate unique key đã được xác định là business conflict | Duplicate/conflict exception | 409 |

**Ranh giới trách nhiệm:** service biết "đơn đã hủy" là trạng thái trái quy tắc; web layer biết cách biểu diễn thành HTTP 409. Domain không nên import `HttpStatus` chỉ để ném lỗi.

**Không mapping mọi `DataIntegrityViolationException` thành 409.** Database constraint error có thể biểu thị nhiều nguyên nhân khác nhau, bao gồm bug/data corruption. Chỉ quy đổi sang mã lỗi business sau khi xác định đúng constraint/ngữ cảnh, nếu không có thể che lỗi hệ thống.

### 5.1. 409 và 422 khác nhau thế nào?

- **409 Conflict:** yêu cầu xung đột với *trạng thái hiện tại* của tài nguyên, ví dụ cố hủy đơn đã hủy, tạo resource trùng định danh, cập nhật dựa trên version cũ.
- **422 Unprocessable Content:** server hiểu media type và cú pháp hợp lệ, nhưng không thể xử lý nội dung mang nghĩa không hợp lệ, ví dụ số lượng vượt quy tắc cụ thể. Không nhất thiết mọi rule đều phải là 422; API có thể chọn 400 cho một số business validations nếu contract giải thích rõ.
- **404 Not Found:** resource theo URL không tồn tại hoặc không được phép tiết lộ sự tồn tại trong một số chính sách truy cập.

Sự khác biệt quan trọng là **tính nhất quán của hợp đồng**, không phải việc dùng nhiều mã HTTP để trông phức tạp.

## 6. Lỗi hệ thống: 500, 502, 503, 504 và retry

Ví dụ hệ thống:

- Database driver ném lỗi kết nối bất ngờ: ứng dụng chưa thực hiện được thao tác → có thể trả 500 hoặc 503 theo nguyên nhân và chính sách "temporarily unavailable".
- Service downstream trả response bất thường làm gateway/proxy không nhận response hợp lệ: **502 Bad Gateway** thường phù hợp ở **gateway**.
- Gateway chờ upstream quá lâu: **504 Gateway Timeout** thường được phát ra bởi **gateway/proxy**.
- Application chủ động từ chối vì đang bảo trì hoặc thiếu tài nguyên tạm thời: **503 Service Unavailable** (có thể kèm `Retry-After` khi biết thời điểm thích hợp).
- Lỗi lập trình bất ngờ, NullPointerException, assumption sai: **500 Internal Server Error**.

Không gắn nhãn `503` cho mọi `RuntimeException`, cũng không tự chọn 504 cho bất kỳ `SocketTimeoutException` phát sinh trong service: vai trò của server trong chuỗi HTTP và ý nghĩa trạng thái phải được xác định.

### 6.1. Thông tin trả cho client

Response error hệ thống nên chứa mô tả tổng quát:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "Đã xảy ra lỗi máy chủ. Vui lòng thử lại sau.",
  "status": 500,
  "path": "/api/orders"
}
~~~

Tránh đưa vào public response: stack trace, SQL statement, connection URL, mật khẩu, bearer token, class/package nội bộ, địa chỉ hạ tầng, thông tin PII hoặc nguyên văn `exception.getMessage()` từ dependency. Log nội bộ cần stacktrace và correlation/trace id để kỹ sư điều tra, nhưng **đừng log bí mật hay toàn bộ request body vô điều kiện**.

### 6.2. Retry đúng loại lỗi

- 400/422 do input hoặc domain rule cố định: thường **không retry y nguyên**.
- 401: refresh/login lại nếu phù hợp; 403: không tự retry để "thử quyền" vô hạn.
- 409 do optimistic lock: có thể đọc version mới và thử lại với cập nhật đã được kiểm soát; không blind retry lệnh nguy hiểm.
- 429: tuân theo `Retry-After` và rate limit policy nếu có.
- 503/504 do lỗi tạm thời: có thể retry **bounded exponential backoff + jitter**, timeout, circuit breaker.
- Với POST không idempotent, retry sau timeout có thể tạo **đơn trùng**. Dùng **idempotency key**, deduplication hoặc điều kiện bảo đảm an toàn trước khi tự động retry.

Retry phải có giới hạn, quan sát được và tôn trọng deadline; tránh "retry storm" khiến hệ thống đang lỗi càng quá tải.

## 7. Chuẩn hóa JSON error response

API có thể dùng **custom DTO** hoặc chuẩn **RFC 9457 Problem Details**. Không buộc phải trả cả hai trong cùng endpoint.

### 7.1. Custom API error DTO

Một dạng rõ ràng:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "status": 400,
  "path": "/api/orders",
  "violations": [
    {"field": "sku", "reason": "NotBlank"},
    {"field": "quantity", "reason": "Min"}
  ]
}
~~~

Các field có vai trò:

- `code`: mã máy đọc ổn định như `INVALID_INPUT`, `ORDER_CONFLICT`, `DEPENDENCY_UNAVAILABLE`. Client nên phụ thuộc vào code, không parse tiếng Việt trong message.
- `message`: thông điệp an toàn, dễ hiểu; có thể được localize, nên không phải định danh máy.
- `status`: số HTTP status để dễ quan sát; phải **khớp status HTTP thực**.
- `path`: URL path, tránh nhúng query chứa token hoặc dữ liệu nhạy cảm.
- `violations`: danh sách tên field và mã constraint; không bắt buộc trả raw rejected value.

Trong production thường thêm `requestId`/`traceId` có thể tìm trong log hoặc distributed tracing, thời gian ISO-8601 và tài liệu về error codes. Chỉ tin request id client cung cấp nếu đã được xác thực/giới hạn/chuẩn hóa; thường hệ thống cần tạo hoặc kiểm soát correlation id ở gateway/filter.

### 7.2. ProblemDetail theo RFC 9457

Spring Framework 6 hỗ trợ `ProblemDetail` / `ErrorResponse`. Ví dụ:

~~~java
@ExceptionHandler(OrderConflictException.class)
public ProblemDetail handleConflict(OrderConflictException ex) {
    ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.CONFLICT);
    pd.setTitle("Order state conflict");
    pd.setDetail("Đơn hàng không thể hủy trong trạng thái hiện tại");
    pd.setProperty("code", "ORDER_CONFLICT");
    return pd;
}
~~~

Đoạn này minh họa method trong `@RestControllerAdvice`, cần import `org.springframework.http.ProblemDetail`, `org.springframework.http.HttpStatus` và exception tương ứng. Spring có thể điền `instance` theo request URL khi chưa được set; response thường dùng `application/problem+json`. Hình dạng thường gặp:

~~~json
{
  "type": "about:blank",
  "title": "Order state conflict",
  "status": 409,
  "detail": "Đơn hàng không thể hủy trong trạng thái hiện tại",
  "instance": "/api/orders/1/cancel",
  "code": "ORDER_CONFLICT"
}
~~~

Nếu muốn xử lý nhiều Spring MVC built-in exceptions thống nhất theo Problem Details, xem `ResponseEntityExceptionHandler` hoặc cấu hình lỗi chuẩn do framework cung cấp. **Không đơn giản kéo `Exception.class` về 500 rồi vô tình che mất 400/405/406/415**. Custom DTO và ProblemDetail đều chấp nhận được nếu API contract chọn rõ một cách và kiểm thử thực tế.

## 8. @RestControllerAdvice và phạm vi @ExceptionHandler

### 8.1. Chọn đúng exception và HTTP status

~~~java
@RestControllerAdvice
public class OrderAdvice {
    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(OrderNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("ORDER_NOT_FOUND", "Không tìm thấy đơn"));
    }

    @ExceptionHandler(OrderConflictException.class)
    public ResponseEntity<ApiError> conflict(OrderConflictException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError("ORDER_CONFLICT", "Đơn đã hủy"));
    }
}
~~~

Đây là ví dụ rút gọn về mapping (cần class `ApiError`, exception và imports phù hợp; project hoàn chỉnh ở mục 10). Spring chọn handler theo exception type; annotation `@RestControllerAdvice` có hiệu lực cho nhiều controllers trong scope áp dụng. Khi exception được bắt tại controller và xử lý hoàn toàn, nó không tự đi qua advice nữa.

Các lỗi do framework dựng ra thường có status riêng. Nếu kế thừa `ResponseEntityExceptionHandler`, dùng các protected hook thích hợp để override cách trả body thay vì khai báo `@ExceptionHandler` mới trùng với mappings đã được class cơ sở xử lý, vì có thể gây ambiguous exception handler mapping.

### 8.2. Không nuốt exception thành thành công giả

Sai:

~~~java
try {
    service.chargeOrder(order);
} catch (Exception ex) {
    return ResponseEntity.ok(Map.of("success", false));
}
~~~

Nếu lỗi hệ thống, response **HTTP 200** đánh lừa monitoring và client. Ngoài ra, catch mọi exception có thể che bug, làm mất stacktrace hoặc để transaction đi tiếp sai trạng thái.

Nên để lỗi domain có ý nghĩa đi lên advice; lỗi không mong đợi được log/quan sát và xử lý bằng fallback phù hợp. Khi bắt exception để **bổ sung ngữ cảnh**, giữ lại cause:

~~~java
try {
    paymentGateway.charge(order);
} catch (GatewayTimeoutException ex) {
    throw new PaymentDependencyException(
            "Payment provider temporarily unavailable", ex);
}
~~~

Đoạn minh họa giả định các class/service; không phải code độc lập. Không phân loại lỗi bằng so khớp chuỗi `ex.getMessage()` vì message có thể thay đổi theo phiên bản hoặc ngôn ngữ.

### 8.3. Ranh giới Spring Security

Khi có Spring Security, Authentication và AccessDenied exceptions thường được xử lý bởi **security filter chain** thông qua `AuthenticationEntryPoint` và `AccessDeniedHandler`. Việc dùng `@RestControllerAdvice` không bảo đảm bắt được lỗi xảy ra **trước DispatcherServlet**. Trong REST API có security, hãy chuẩn hóa response 401/403 qua cấu hình Security tương ứng.

- **401 Unauthorized**: request chưa có thông tin xác thực hợp lệ; chuẩn thực tế thường cần `WWW-Authenticate` tùy scheme.
- **403 Forbidden**: đã xác định quyền không đủ hoặc bị cấm.
- **404** đôi khi được dùng có chủ ý để tránh tiết lộ sự tồn tại resource nhưng phải có policy nhất quán.

## 9. Phân tầng exception và transaction

Một kiến trúc dễ duy trì:

~~~text
Controller / Web
  - @RequestBody, @Valid, parameter binding
  - HTTP mapping, @RestControllerAdvice
      |
      v
Application Service
  - authorization + orchestration
  - domain exceptions (NotFound, Conflict, RuleViolation)
      |
      v
Domain Model
  - invariants, state transitions
      |
      v
Repository / External Adapter
  - translate known infrastructure failures if needed
  - propagate unexpected exceptions with causal context
~~~

Không cho domain model phải biết `HttpStatus.CONFLICT`. Domain ném `OrderAlreadyCancelledException`; web mapping thành 409. Lỗi adapter đi lên dưới dạng exception có ngữ nghĩa hoặc nguyên nhân gốc được bảo toàn.

Với transaction Spring, **unchecked exceptions** mặc định khiến `@Transactional` rollback; checked exceptions có quy tắc rollback khác trừ khi cấu hình. Đừng bắt một exception nghiêm trọng bên trong service rồi tiếp tục trả thành công, vì có thể khiến transaction commit dữ liệu nửa vời. Một business rejection có thể không cần ghi gì và vẫn rollback; một conflict đã được xử lý an toàn thì response phù hợp tùy nghiệp vụ.

Với concurrent updates, nghiệp vụ có thể cần optimistic locking, DB unique constraint và tính atomic; kiểm tra "đơn đang NEW" trước rồi update hai bước không đồng nghĩa không có race condition. Ví dụ in-memory ở mục 10 dùng `ConcurrentHashMap.compute` để hủy nguyên tử ở phạm vi map.

## 10. Dự án chạy được: phân loại và trả lỗi qua HTTP

**Yêu cầu:** Java 17+, Maven. Ví dụ dùng Spring Boot 3.5.0, Spring MVC và Bean Validation. Dữ liệu lưu trong RAM, seed đơn số 1 để thử 404/409; có endpoint mô phỏng 503 cho mục đích học. Bài thực hành độc lập, không yêu cầu database.

Cấu trúc:

~~~text
error-demo/
├── pom.xml
└── src/
    ├── main/java/demo/ErrorHandlingApplication.java
    └── test/java/demo/OrderApiTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>error-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. ErrorHandlingApplication.java

Toàn bộ mã dưới đây thuộc **một file** `src/main/java/demo/ErrorHandlingApplication.java`: một public class trùng tên file, các record/class khác package-private. Những endpoint đã chỉ rõ JSON để dễ thử bằng curl.

~~~java
package demo;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.stereotype.Service;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@SpringBootApplication
public class ErrorHandlingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}

record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}

record OrderDto(long id, String sku, int quantity, String status) {
}

record FieldViolation(String field, String reason) {
}

record ApiFailure(
        String code,
        String message,
        int status,
        String path,
        List<FieldViolation> violations) {
}

class OrderMissingException extends RuntimeException {
    OrderMissingException() { super("Order not found"); }
}

class OrderConflictException extends RuntimeException {
    OrderConflictException() { super("Order is already cancelled"); }
}

class OrderRuleException extends RuntimeException {
    OrderRuleException() { super("Quantity exceeds business limit"); }
}

class DependencyUnavailableException extends RuntimeException {
    DependencyUnavailableException() { super("Dependency unavailable"); }
}

@Service
class OrderService {
    private final Map<Long, OrderDto> store = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(1L);

    OrderService() {
        store.put(1L, new OrderDto(1L, "JAVA-17", 2, "NEW"));
    }

    OrderDto find(long id) {
        OrderDto found = store.get(id);
        if (found == null) {
            throw new OrderMissingException();
        }
        return found;
    }

    OrderDto create(CreateOrderRequest request) {
        // Validation đơn giản đã xảy ra ở controller.
        // Rule max 10 là quy tắc nghiệp vụ tại service.
        if (request.quantity() > 10) {
            throw new OrderRuleException();
        }
        long id = nextId.incrementAndGet();
        OrderDto created = new OrderDto(
                id,
                request.sku().trim().toUpperCase(Locale.ROOT),
                request.quantity(),
                "NEW");
        store.put(id, created);
        return created;
    }

    OrderDto cancel(long id) {
        // compute thao tác atomically cho một key, không read-then-write.
        return store.compute(id, (key, old) -> {
            if (old == null) {
                throw new OrderMissingException();
            }
            if ("CANCELLED".equals(old.status())) {
                throw new OrderConflictException();
            }
            return new OrderDto(
                    old.id(), old.sku(), old.quantity(), "CANCELLED");
        });
    }
}

@RestController
@RequestMapping(path = "/api/orders",
                produces = MediaType.APPLICATION_JSON_VALUE)
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    OrderDto one(@PathVariable long id) {
        return service.find(id);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderDto> create(
            @Valid @RequestBody CreateOrderRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(request));
    }

    @PostMapping("/{id}/cancel")
    OrderDto cancel(@PathVariable long id) {
        return service.cancel(id);
    }

    // Chỉ mô phỏng lỗi tạm thời để học/kiểm thử.
    @GetMapping("/dependency-demo")
    OrderDto dependencyDemo() {
        throw new DependencyUnavailableException();
    }
}

@RestControllerAdvice
class ApiErrorAdvice {
    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiFailure> invalidJson(
            HttpMessageNotReadableException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.BAD_REQUEST, "INVALID_JSON",
                "Không đọc được JSON của yêu cầu",
                request, List.of());
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ApiFailure> invalidParameter(
            MethodArgumentTypeMismatchException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.BAD_REQUEST, "INVALID_PARAMETER",
                "Tham số đường dẫn hoặc query không đúng kiểu",
                request, List.of());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiFailure> invalidBody(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {
        List<FieldViolation> fields =
                ex.getBindingResult().getFieldErrors().stream()
                    .map(error -> new FieldViolation(
                            error.getField(),
                            error.getCode() == null
                                    ? "Invalid"
                                    : error.getCode()))
                    .toList();
        return fail(HttpStatus.BAD_REQUEST, "INVALID_INPUT",
                "Dữ liệu yêu cầu không hợp lệ",
                request, fields);
    }

    @ExceptionHandler(OrderMissingException.class)
    ResponseEntity<ApiFailure> missing(
            OrderMissingException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND",
                "Không tìm thấy đơn hàng", request, List.of());
    }

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ApiFailure> conflict(
            OrderConflictException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.CONFLICT, "ORDER_CONFLICT",
                "Đơn hàng đã hủy", request, List.of());
    }

    @ExceptionHandler(OrderRuleException.class)
    ResponseEntity<ApiFailure> rule(
            OrderRuleException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.UNPROCESSABLE_ENTITY, "ORDER_RULE",
                "Mỗi đơn được tối đa 10 sản phẩm",
                request, List.of());
    }

    @ExceptionHandler(DependencyUnavailableException.class)
    ResponseEntity<ApiFailure> dependency(
            DependencyUnavailableException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.SERVICE_UNAVAILABLE, "DEPENDENCY_UNAVAILABLE",
                "Dịch vụ tạm thời không khả dụng",
                request, List.of());
    }

    private ResponseEntity<ApiFailure> fail(
            HttpStatus status,
            String code,
            String message,
            HttpServletRequest request,
            List<FieldViolation> violations) {
        return ResponseEntity.status(status)
                .body(new ApiFailure(code, message, status.value(),
                        request.getRequestURI(), violations));
    }
}
~~~

**Giải thích những quyết định trong dự án:**

- `@Valid @RequestBody` tách Bean Validation ra khỏi logic domain; lỗi parse JSON/type có handler riêng.
- `OrderService` ném domain exceptions, không import `HttpStatus`; advice chịu trách nhiệm ánh xạ 404/409/422.
- Mẫu `ApiFailure` có code ổn định, message an toàn và path; không trả exception message thô hoặc stacktrace.
- Chỉ giả lập `DependencyUnavailableException` cho 503. Trong ứng dụng thật, lỗi dependency phải được phát hiện và phân loại từ adapter/circuit breaker theo contract, không tạo endpoint lỗi cố ý.
- Chưa khai báo catch-all `Exception.class` để tránh can thiệp vô tình vào status của lỗi MVC mặc định như 405/406/415. Khi cần response 500 chung, cấu hình error handling ở mức phù hợp và **giữ nguyên** nghĩa của framework exceptions.
- `List<FieldViolation>` có thể có nhiều lỗi với cùng một field; không mặc định thứ tự lỗi là hợp đồng cho client.
- Không có database hoặc xác thực trong demo. Production cần transaction, data integrity và Spring Security theo yêu cầu.

### 10.3. Chạy và thử từng nhóm lỗi

Từ thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Một số lời gọi với curl (ví dụ dùng Bash):

**Thành công:**

~~~bash
curl -i 'http://localhost:8080/api/orders/1'
~~~

HTTP 200, JSON tương đương:

~~~json
{"id":1,"sku":"JAVA-17","quantity":2,"status":"NEW"}
~~~

**Lỗi đầu vào — id sai kiểu:**

~~~bash
curl -i 'http://localhost:8080/api/orders/abc'
~~~

HTTP 400, body tương đương:

~~~json
{
  "code":"INVALID_PARAMETER",
  "message":"Tham số đường dẫn hoặc query không đúng kiểu",
  "status":400,
  "path":"/api/orders/abc",
  "violations":[]
}
~~~

**Lỗi đầu vào — body thiếu/sai constraint:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"","quantity":0}'
~~~

HTTP 400, `code=INVALID_INPUT`; `violations` thường chứa `sku/NotBlank` và `quantity/Min`. Thứ tự field lỗi không bảo đảm.

**Lỗi đầu vào — JSON sai cú pháp:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"JAVA-17","quantity":'
~~~

HTTP 400, `code=INVALID_JSON`.

**Lỗi nghiệp vụ — rule vượt hạn mức:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"JAVA-17","quantity":11}'
~~~

HTTP 422, `code=ORDER_RULE`, vì request hợp lệ theo DTO nhưng vượt business limit.

**Lỗi nghiệp vụ — không tìm thấy đơn:**

~~~bash
curl -i 'http://localhost:8080/api/orders/999'
~~~

HTTP 404, `code=ORDER_NOT_FOUND`.

**Lỗi nghiệp vụ — state conflict:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders/1/cancel'
curl -i -X POST 'http://localhost:8080/api/orders/1/cancel'
~~~

Lần đầu HTTP 200 với `status=CANCELLED`; lần hai HTTP 409 với `code=ORDER_CONFLICT`.

**Lỗi hệ thống mô phỏng — dependency unavailable:**

~~~bash
curl -i 'http://localhost:8080/api/orders/dependency-demo'
~~~

HTTP 503 với `code=DEPENDENCY_UNAVAILABLE`. Trong ví dụ, lỗi này được phát ra có chủ đích; service thật có thể cân nhắc `Retry-After` và circuit breaker theo điều kiện.

Nếu chạy trong PowerShell, nên dùng `curl.exe` thay vì alias `curl`; dấu `\` nối dòng dùng cho shell Unix, có thể viết lệnh trên một dòng để tránh khác biệt shell.

### 10.4. Test MockMvc cho HTTP status và error code

Tạo file `src/test/java/demo/OrderApiTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    void invalidPathVariableIsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));
    }

    @Test
    void validationErrorIsBadRequest() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"","quantity":0}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
            .andExpect(jsonPath("$.violations.length()").value(2));
    }

    @Test
    void malformedJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"JAVA-17\",\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void quantityOverBusinessLimitIs422() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"JAVA-17","quantity":11}
                    """))
            .andExpect(status().isUnprocessableEntity())
            .andExpect(jsonPath("$.code").value("ORDER_RULE"));
    }

    @Test
    void missingResourceIs404() throws Exception {
        mvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void repeatedCancelIsConflict() throws Exception {
        mvc.perform(post("/api/orders/1/cancel"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("CANCELLED"));

        mvc.perform(post("/api/orders/1/cancel"))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("ORDER_CONFLICT"));
    }

    @Test
    void temporaryDependencyFailureIs503() throws Exception {
        mvc.perform(get("/api/orders/dependency-demo"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("DEPENDENCY_UNAVAILABLE"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test đo **kết quả HTTP thực tế** thay vì chỉ so sánh mã trong phương thức handler. Dùng `$.violations.length()` để kiểm tra số lỗi, không phụ thuộc thứ tự. Dữ liệu demo lưu RAM trong một application context, test hủy id 1 chỉ chạy một lần trong suite này; nếu viết nhiều test thay đổi cùng resource thì nên tách dữ liệu/reset fixture để các test độc lập.

## 11. Hướng production: giữ ranh giới và quan sát lỗi

### 11.1. Dùng ResponseEntityExceptionHandler khi muốn thống nhất lỗi framework

Spring MVC cung cấp `ResponseEntityExceptionHandler` để xử lý một nhóm lỗi có sẵn theo `ErrorResponse`/`ProblemDetail`. Ví dụ khung:

~~~java
@RestControllerAdvice
class GlobalProblemAdvice extends ResponseEntityExceptionHandler {
    @ExceptionHandler(OrderConflictException.class)
    public ProblemDetail conflict(OrderConflictException ex) {
        ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.CONFLICT);
        pd.setTitle("Order conflict");
        pd.setDetail("Đơn hàng đang ở trạng thái không cho phép");
        pd.setProperty("code", "ORDER_CONFLICT");
        return pd;
    }
}
~~~

Đoạn này là minh họa **phương án thay thế** cho `ApiErrorAdvice` ở mục 10, không đặt cả hai advice cạnh tranh trong cùng ứng dụng. Cần imports `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler`, `RestControllerAdvice`, `ExceptionHandler`, `ProblemDetail`, `HttpStatus` và domain exception. Khi tùy biến built-in exceptions, ưu tiên override các protected handler methods đúng chữ ký trong phiên bản Spring sử dụng; tránh tạo hai mappings @ExceptionHandler cho cùng exception.

### 11.2. 500 chung không nên che status sẵn có

Một catch-all `@ExceptionHandler(Exception.class)` có thể hữu ích để tạo body 500 và log stacktrace, nhưng cũng có thể chặn các exception mà framework vốn sẽ map thành 400, 404, 405, 406, 415. Nếu cần fallback toàn cục, thiết kế rõ phạm vi và xử lý/ủy quyền cho `ErrorResponse` của Spring trước, hoặc dùng `ResponseEntityExceptionHandler` để kế thừa xử lý mặc định. Không ghi toàn bộ exception message vào client.

### 11.3. Logging, metrics và tracing

Đề xuất thông tin tối thiểu có cấu trúc cho server logs/metrics:

| Trường | Ý nghĩa |
| --- | --- |
| `requestId / traceId` | Gắn response lỗi với log/traces |
| `route / method` | Phân biệt endpoint, tránh high-cardinality từ raw path chứa id |
| `http.status` | Quan sát tỷ lệ lỗi theo 4xx/5xx |
| `error.code` | Gom nhóm lỗi ổn định theo hợp đồng |
| `exception.class` | Phục vụ chẩn đoán server, không đưa vào public JSON |
| `durationMs` | Nhận diện timeout/chậm |
| `downstream.name` | Xác định dependency liên quan |

4xx thường phản ánh request/client/domain state; 5xx thường cần alert server. Tuy nhiên tăng 409 do bug concurrency hay 401 đột biến có thể cũng là dấu hiệu cần điều tra. Tránh log mật khẩu, token, cookie hoặc request/response body chứa dữ liệu cá nhân; masking/redaction theo policy.

### 11.4. Trạng thái HTTP và tính an toàn của retry

Quy tắc thực hành:

- Chỉ trả **200/201** khi thao tác thực sự thành công theo contract.
- Trả **4xx** khi request không đáp ứng điều kiện client cần sửa hoặc một trạng thái domain ngăn việc thực hiện.
- Trả **5xx** khi server/upstream không hoàn tất yêu cầu.
- Với 503 tạm thời, có thể thêm `Retry-After` hợp lệ nếu biết khoảng chờ hợp lý.
- Với thao tác ghi có thể được gửi lại, dùng idempotency key hoặc optimistic concurrency để giảm rủi ro trùng.
- Với ứng dụng async, có thể trả **202 Accepted** nếu công việc mới chỉ được nhận vào hàng đợi; cần mô tả cách client kiểm tra kết quả và trạng thái lỗi về sau. Không coi 202 là "đã hoàn tất".

## 12. Bài tập tự kiểm tra

**Bài 1 — Phân nhóm:** Với mỗi tình huống, chọn lỗi đầu vào/nghiệp vụ/hệ thống và HTTP status phù hợp: `page=abc`, JSON thiếu dấu ngoặc, đơn đã hủy, database mất kết nối, `Accept: application/xml` nhưng API chỉ trả JSON.

**Bài 2 — Thiết kế contract:** Đề xuất response `ApiFailure` cho `INVALID_INPUT` gồm hai field errors. Lý giải tại sao không đưa rejected password/token value vào JSON.

**Bài 3 — Domain exception:** Tạo `OrderAlreadyPaidException` tại service và ánh xạ 409 tại advice; thay đổi business rule nếu đã thanh toán thì không được hủy.

**Bài 4 — Framework exceptions:** So sánh `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `HttpMessageNotReadableException` và `MethodArgumentTypeMismatchException`. Lỗi nào xảy ra trước khi method controller chạy?

**Bài 5 — Hệ thống:** Với timeout payment gateway sau khi request thanh toán đã gửi đi, giải thích vì sao client retry POST ngay lập tức có thể gây tính tiền hai lần; đề xuất idempotency key và tracing.

**Bài 6 — Test:** Mở rộng suite kiểm tra HTTP 415 với `Content-Type: text/plain`, 404 resource, 409 cancel trùng và 503 dependency; không so sánh thứ tự field JSON object.

**Bài 7 — Spring Security:** Giải thích tại sao `@RestControllerAdvice` không bảo đảm bắt được authentication failure từ filter chain, và xác định nơi nên cấu hình body lỗi 401/403.

## 13. Ghi nhớ

- **Đầu vào:** request sai cú pháp/kiểu/constraint → sửa request; Spring có thể phát sinh lỗi trước handler, thường dùng HTTP 400.
- **Nghiệp vụ:** yêu cầu hiểu được nhưng xung đột trạng thái hoặc vi phạm rule → domain exception có ý nghĩa; web mapping 404/409/422 theo contract.
- **Hệ thống:** sự cố server/dependency → 5xx thích hợp, log và trace nội bộ, trả client message an toàn; retry phải có điều kiện và bảo vệ tính idempotent.
- **Spring MVC:** `@RestControllerAdvice`, `@ExceptionHandler`, `ResponseEntity`, `ProblemDetail` và `ResponseEntityExceptionHandler` là các công cụ thiết kế error boundary; không "bắt tất cả thành 500" mà đánh mất trạng thái framework vốn có.
- API lỗi tốt có **HTTP status đúng + stable error code + safe message + context quan sát**, được kiểm thử bằng request thực.

## 14. Tài liệu chính thức

- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): `ErrorResponse`, `ProblemDetail`, `ResponseEntityExceptionHandler`.
- [Spring Framework 6.2 — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [Spring Framework 6.2 — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): ngoại lệ ở controller/advice.
- [Spring Framework 6.2 — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): chia sẻ cấu hình cho nhiều controllers.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa 4xx/5xx và status codes.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): error object chuẩn machine-readable.
