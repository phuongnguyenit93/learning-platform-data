# `@ExceptionHandler` và `@RestControllerAdvice`

> **Module:** `INTEGRATION_API_REST` — chương **Dữ liệu và lỗi Spring**. Bài học xây dựng hợp đồng lỗi cho REST API bằng **Spring MVC, Java 17+, `@ExceptionHandler`, `@RestControllerAdvice`, `ResponseEntityExceptionHandler` và `ProblemDetail`**. Người học phân biệt lỗi từ HTTP, validation, nghiệp vụ, truy cập dữ liệu và bảo mật; viết API có mã trạng thái, dữ liệu lỗi ổn định, kiểm thử MockMvc và tài liệu OpenAPI rõ ràng.

## 1. Khi REST API trả lỗi thiếu nhất quán

Ví dụ `GET /v1/orders/ord_missing` không tìm thấy đơn, `POST /v1/orders` với `{"quantity":0}` sai validation, còn `POST /v1/orders/ord_916/cancellations` muốn hủy đơn đã giao. Nếu tất cả đều thành `500 Internal Server Error` hoặc `200 {"success":false}`, client không biết nên **sửa input**, **đọc lại trạng thái**, hay **báo sự cố hạ tầng**.

Một hợp đồng tốt cần đồng thời:

1. **Status HTTP phản ánh nguyên nhân** — 400, 404, 409… thay vì 500 cho mọi thứ.
2. **Body lỗi ổn định, máy đọc được**, ví dụ `application/problem+json` với `type` và `code`.
3. **Không tiết lộ dữ liệu nhạy cảm** — không trả stack trace, SQL, token hoặc bản ghi của tenant khác.
4. **Tách nơi phát hiện lỗi và nơi chuyển lỗi** — service nêu ý nghĩa nghiệp vụ; HTTP boundary ánh xạ sang response.

**Mục tiêu:** triển khai handler cục bộ/toàn cục, `ProblemDetail`, bảo mật, xử lý lỗi JPA và kiểm thử hợp đồng.

## 2. `@ExceptionHandler` và `@RestControllerAdvice` giải quyết gì?

`@ExceptionHandler` xử lý một hoặc nhiều exception tại **controller cụ thể** hoặc **advice toàn cục**. `@RestControllerAdvice` kết hợp `@ControllerAdvice` và hành vi `@ResponseBody`, cho phép handler trả JSON/`ProblemDetail` không cần chú thích `@ResponseBody` riêng. Ví dụ đầy đủ ở mục 6; tránh sao chép một handler vào từng controller.

| Cách xử lý | Phạm vi | Thường dùng khi |
|---|---|---|
| `@ExceptionHandler` trong controller | Controller đó | Exception đặc thù chỉ có nghĩa tại endpoint này |
| `@RestControllerAdvice` | Nhiều controller, có thể giới hạn phạm vi | Chuẩn hóa lỗi domain, validation, input và kỹ thuật |
| `ResponseEntityExceptionHandler` | Lớp cơ sở cho advice MVC | Tùy biến xử lý những exception Spring MVC đã hỗ trợ |
| Spring Security entry point / access denied handler | Security filter chain | Lỗi authentication/authorization xảy ra **trước MVC** |
| Spring Boot error dispatch (`/error`) | Đường xử lý lỗi còn lại tùy cấu hình | Fallback không được MVC exception resolver xử lý |

Không ép mọi nguồn lỗi vào một `@RestControllerAdvice`. **Lỗi xác thực trước controller** hoặc một số lỗi ở servlet filter thường không đi theo đường exception handling của MVC.

### 2.1. Luồng xử lý exception

~~~mermaid
flowchart TD
    A["HTTP request"] --> S{"Security filter chain"}
    S -- "401/403" --> SE["AuthenticationEntryPoint / AccessDeniedHandler"]
    S -- "Được qua" --> M["DispatcherServlet, handler mapping, MVC"]
    M --> C["Controller -> Service -> Repository"]
    C --> X{"Exception?"}
    X -- "Không" --> OK["2xx response"]
    X -- "Có" --> R["HandlerExceptionResolver chain"]
    R --> H{"@ExceptionHandler phù hợp?"}
    H -- "Có" --> PD["Status + ProblemDetail"]
    H -- "Không" --> F["Resolver mặc định hoặc fallback /error"]
~~~

Trong Spring MVC, các exception resolver liên quan gồm `ExceptionHandlerExceptionResolver` (hỗ trợ `@ExceptionHandler`), `ResponseStatusExceptionResolver` (ví dụ `@ResponseStatus`, `ResponseStatusException`) và `DefaultHandlerExceptionResolver` (nhiều lỗi MVC chuẩn). Cấu hình ứng dụng có thể bổ sung/tùy chỉnh resolver. **Không khẳng định mọi exception đều đi qua một phương thức duy nhất.**

### 2.2. Local handler, global advice và thứ tự ưu tiên

Trong các handler MVC phù hợp, `@ExceptionHandler` **cục bộ trên controller** thường được ưu tiên trước global advice. Khi có nhiều `@ControllerAdvice`, `@Order`/`Ordered` ảnh hưởng mức ưu tiên; exception type cụ thể và cause chain cũng tham gia chọn handler.

Thiết kế tránh tranh chấp:

- Chỉ có **một nơi** chịu trách nhiệm cho mỗi nhóm lỗi framework (validation, JSON parsing, media type) trong phạm vi phù hợp.
- Dùng một global advice chung cho lỗi domain phổ biến; local handler chỉ dùng khi khác biệt có lý do nghiệp vụ.
- Tránh nhiều advice có catch-all `Exception.class` ở ưu tiên cao, vì nó dễ che handler chuyên biệt ở advice khác.
- Không dựa vào tên phương thức Java để quyết định handler; **loại exception và phạm vi** mới là điều quan trọng.

`@RestControllerAdvice(basePackages = "com.example.orders.api")` có thể giới hạn controller được áp dụng. Các bộ lọc như `assignableTypes` và `annotations` cũng khả dụng; cần thử trên cấu trúc package thực. Đừng đặt advice quá rộng rồi vô tình đổi hợp đồng lỗi của các endpoint quản trị/actuator hoặc controller phục vụ HTML.

## 3. Chọn mã HTTP trước khi viết exception handler

Exception là công cụ chuyển điều khiển trong Java; **mã HTTP phải dựa vào ý nghĩa của thất bại**.

| Điều kiện | Status thường phù hợp | Gợi ý xử lý phía client |
|---|---|---|
| JSON malformed, thiếu body hoặc query/path không parse được | **400 Bad Request** | Sửa request |
| DTO vi phạm Bean Validation (ví dụ `quantity=0`) | **400** (hoặc 422 theo contract) | Hiển thị lỗi field |
| Đã xác thực nhưng tài nguyên ngoài quyền | **403** hoặc **404** theo chính sách che tồn tại | Không suy đoán resource khác |
| Không có token hợp lệ | **401 Unauthorized** | Xác thực lại theo flow phù hợp |
| Không tìm thấy resource được phép biết | **404 Not Found** | Ngừng dùng ID hoặc kiểm tra URI |
| Trạng thái nghiệp vụ không cho hành động | **409 Conflict** | GET lại resource hoặc đổi thao tác |
| `If-Match` được gửi nhưng không khớp | **412 Precondition Failed** | Tải bản mới và giải quyết xung đột |
| Endpoint bắt buộc điều kiện nhưng request thiếu | **428 Precondition Required** | Gửi strong ETag/If-Match theo contract |
| Request hợp cú pháp nhưng vi phạm quy tắc nội dung được định nghĩa | **422 Unprocessable Content** nếu contract chọn | Sửa dữ liệu |
| Vượt rate/quota | **429 Too Many Requests** | Backoff, xem `Retry-After` |
| Lỗi DB/network/bug không dự đoán được | **500/503** tùy loại | Không retry vô hạn; quan sát server |

Không mặc định mọi `DataIntegrityViolationException` là 409: unique constraint nghiệp vụ có thể là conflict, lỗi FK/schema do bug có thể là 5xx. Service cần phân loại theo constraint và domain.

### 3.1. Lỗi là một phần của API contract

REST API công bố tài nguyên, URI, phương thức và status thành công, nhưng cũng phải công bố **những thất bại client có thể dự đoán**. Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-not-cancellable",
  "title": "Order cannot be cancelled",
  "status": 409,
  "code": "ORDER_NOT_CANCELLABLE",
  "detail": "Đơn hàng đã giao, không thể yêu cầu hủy."
}
~~~

`code` là **extension member** do ứng dụng định nghĩa; Spring không tự cấp một bộ mã nghiệp vụ chuẩn. Client nên dựa vào HTTP status, `type` và/hoặc `code` ổn định, **không so sánh nguyên văn `detail`** vì detail có thể đổi ngôn ngữ hoặc cách diễn đạt.

## 4. Dùng `ProblemDetail` thay cho JSON lỗi tùy hứng

Spring Framework 6 hỗ trợ `ProblemDetail` và `ErrorResponse` để biểu diễn **Problem Details for HTTP APIs (RFC 9457)**. Với các hệ cũ, RFC 7807 là tiền thân; API mới có thể theo RFC 9457.

| Thuộc tính | Ý nghĩa | Quy tắc khuyến nghị |
|---|---|---|
| `type` | URI xác định loại vấn đề | Ổn định, có thể dẫn tới tài liệu |
| `title` | Mô tả ngắn, hướng người đọc | Không chứa dữ liệu nhạy cảm |
| `status` | Mã HTTP của lần trả lỗi | Đồng nhất với status line |
| `detail` | Giải thích lỗi cụ thể | An toàn, không lộ SQL/stack trace |
| `instance` | URI tham chiếu occurrence nếu có | Không chứa token, secret hoặc path nhạy cảm |
| `code` | Mã nghiệp vụ mở rộng của API | Dành cho hành vi client, version ổn định |
| `errors` | Danh sách field lỗi mở rộng | Giới hạn số phần tử, chỉ trả field/code an toàn |
| `traceId` | ID truy vết mở rộng | Dùng giá trị do hệ thống cấp, không tin raw header tùy ý |

Ví dụ validation:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Invalid request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "productId", "code": "NotBlank"},
    {"field": "quantity", "code": "Min"}
  ]
}
~~~

Không nhất thiết trả lại `rejectedValue`: các input như mật khẩu, thẻ, số định danh hoặc nội dung tự do có thể xuất hiện trong validation errors. Với field lỗi lồng nhau, chuẩn hóa tên/đường dẫn field và giới hạn độ dài để tránh response quá lớn.

`ResponseStatusException` hữu ích với lỗi HTTP đơn giản ở controller. Không nên để service/repository phụ thuộc trực tiếp vào HTTP; dùng domain exception và advice để cùng service còn phục vụ được batch/job consumer.

## 5. Ví dụ Java/Spring: controller, service và domain exception

Ví dụ dùng Java 17, Spring Boot 3.x, Spring MVC 6.x, Bean Validation và Spring Security. Đây là các lát cắt để học cách phân công trách nhiệm; muốn chạy thật phải thêm dependency, cấu hình xác thực, entity/repository và transaction.

### 5.1. Request DTO không nhận field nội bộ

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record NewOrderRequest(
    @NotBlank String productId,
    @NotNull @Min(1) Integer quantity
) {}

public record OrderView(
    String id,
    String status,
    String currency,
    String totalAmount
) {}
~~~

Không cho client tự gán `ownerId`, `tenantId`, `status=PAID` hoặc `totalAmount` bằng cách bind thẳng request JSON vào entity. Server phải xác minh identity, kiểm tra product và tính toán nghiệp vụ.

### 5.2. Controller mô tả happy path, không tự xây JSON lỗi

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderView read(@PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        return service.getVisible(jwt.getSubject(), id);
    }

    @PostMapping(consumes = "application/json",
                 produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public ResponseEntity<OrderView> create(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody NewOrderRequest input) {
        OrderView created = service.create(jwt.getSubject(), input);
        return ResponseEntity.created(
            URI.create("/v1/orders/" + created.id()))
            .body(created);
    }

    @PostMapping("/{id}/cancellations")
    @PreAuthorize("hasAuthority('SCOPE_orders.cancel')")
    public ResponseEntity<Void> requestCancellation(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        service.cancel(jwt.getSubject(), id);
        return ResponseEntity.noContent().build();
    }
}

public interface OrderService {
    OrderView getVisible(String subject, String id);
    OrderView create(String subject, NewOrderRequest request);
    void cancel(String subject, String id);
}
~~~

Endpoint `GET` thành công trả `200`, `POST` tạo resource trả `201 Location`, yêu cầu hủy được xử lý đồng bộ trả `204` theo hợp đồng ví dụ. Nếu hủy chạy bất đồng bộ, contract có thể dùng `202 Accepted` và operation monitor. `@Valid` khiến Spring kiểm tra DTO; các lỗi có thể được chuyển thành `MethodArgumentNotValidException` rồi xử lý ở advice.

**Lưu ý bảo mật:** `jwt.getSubject()` chỉ đáng tin khi OAuth2 Resource Server đã kiểm tra token. Service cần thêm tenant/project scope từ nguồn đáng tin và **object-level authorization**. Nếu đơn ngoài quyền, có thể ném `OrderNotFoundException` theo chính sách che sự tồn tại. `@PreAuthorize` yêu cầu method security đã bật; nó không thay quyền trên từng đơn.

### 5.3. Domain exception không phụ thuộc HTTP

Service có thể ném các lớp `RuntimeException` chuyên biệt như `OrderNotFoundException`, `OrderNotCancellableException`, `InvalidOrderRuleException` hoặc `StaleOrderVersionException`. Mỗi lớp cần được định nghĩa riêng trong ứng dụng; chúng **không chứa HTTP status hoặc message công khai**. Advice chuyển nguyên nhân domain sang HTTP, không tự lấy `exception.getMessage()` làm `detail`.

## 6. `@RestControllerAdvice` chuẩn hóa lỗi domain

Spring Framework 6 hỗ trợ `ProblemDetail.forStatusAndDetail(...)`. Advice dưới đây vừa xử lý các exception domain vừa kế thừa `ResponseEntityExceptionHandler` để tùy biến một số lỗi MVC.

~~~java
import java.net.URI;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice
public class OrderErrorAdvice
        extends ResponseEntityExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            OrderNotFoundException ex) {
        return response(HttpStatus.NOT_FOUND,
            "order-not-found", "ORDER_NOT_FOUND",
            "Order not found",
            "Không tìm thấy đơn hàng được phép truy cập.");
    }

    @ExceptionHandler(OrderNotCancellableException.class)
    public ResponseEntity<ProblemDetail> notCancellable(
            OrderNotCancellableException ex) {
        return response(HttpStatus.CONFLICT,
            "order-not-cancellable", "ORDER_NOT_CANCELLABLE",
            "Order cannot be cancelled",
            "Trạng thái hiện tại không cho phép hủy đơn.");
    }

    private ResponseEntity<ProblemDetail> response(
            HttpStatus status, String typeSlug, String code,
            String title, String publicDetail) {
        ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(status, publicDetail);
        problem.setType(URI.create(
            "https://api.example.test/problems/" + typeSlug));
        problem.setTitle(title);
        problem.setProperty("code", code);

        return ResponseEntity.status(status)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(problem);
    }
}
~~~

Mẫu code thực thi hai mapping `OrderNotFoundException → 404` và `OrderNotCancellableException → 409`. Trong API thật, thêm `@ExceptionHandler(InvalidOrderRuleException.class)` trả **422** theo contract và `@ExceptionHandler(StaleOrderVersionException.class)` trả **412** khi `If-Match` thực sự không khớp; thiếu precondition bắt buộc là **428**.

Đừng ném `StaleOrderVersionException` cho mọi `OptimisticLockingFailureException` ở mọi endpoint: chỉ dùng `412` khi có điều kiện HTTP tương ứng. Với một command không dùng `If-Match`, cần xét contract và nguyên nhân xung đột trước khi chọn `409` hoặc cơ chế retry riêng.

`@Order(Ordered.HIGHEST_PRECEDENCE)` chỉ minh họa thứ tự advice; handler quá rộng ở ưu tiên cao có thể che handler khác.

### 6.1. Field validation khác domain validation

`@Valid @RequestBody` kiểm tra DTO (ví dụ `quantity < 1`) → **400 VALIDATION_FAILED** trong hợp đồng này. Product ngừng kinh doanh là lỗi domain → **422 ORDER_RULE_VIOLATION**. API khác có thể dùng 422 cho cả hai; cần tài liệu và test nhất quán.

## 7. Tùy biến lỗi Spring MVC bằng `ResponseEntityExceptionHandler`

Spring MVC có sẵn exception cho việc đọc body, validation, media type, argument conversion và nhiều trường hợp khác. Nếu advice **đã kế thừa `ResponseEntityExceptionHandler`**, cách phù hợp là **override các phương thức `handle...` được hỗ trợ** thay vì thêm một `@ExceptionHandler(MethodArgumentNotValidException.class)` khác cho loại exception mà lớp cha đã đăng ký. Thêm cả hai có thể khiến handler bị trùng hoặc mơ hồ.

### 7.1. Override validation và JSON parsing

Thêm các phương thức sau **vào `OrderErrorAdvice` ở mục 6**, không khai báo một advice thứ hai có các handler trùng:

~~~java
// Các import cho URI, List, Map, HTTP types, WebRequest
// và MVC exceptions cần bổ sung vào class OrderErrorAdvice.
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST, "Dữ liệu đầu vào không hợp lệ.");
    problem.setType(URI.create(
        "https://api.example.test/problems/validation-failed"));
    problem.setTitle("Invalid request");
    problem.setProperty("code", "VALIDATION_FAILED");

    List<Map<String, String>> errors =
        ex.getBindingResult().getFieldErrors().stream()
            .limit(20)
            .map(err -> Map.of(
                "field", err.getField(),
                "code", err.getCode() == null
                    ? "INVALID" : err.getCode()))
            .toList();
    problem.setProperty("errors", errors);
    return mvcProblem(ex, headers, problem, request);
}

@Override
protected ResponseEntity<Object> handleHttpMessageNotReadable(
        HttpMessageNotReadableException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST, "Body không đọc được hoặc sai kiểu.");
    problem.setType(URI.create(
        "https://api.example.test/problems/malformed-body"));
    problem.setTitle("Invalid request body");
    problem.setProperty("code", "MALFORMED_BODY");
    return mvcProblem(ex, headers, problem, request);
}

private ResponseEntity<Object> mvcProblem(
        Exception ex, HttpHeaders originalHeaders,
        ProblemDetail body, WebRequest request) {
    HttpHeaders safe = new HttpHeaders();
    safe.putAll(originalHeaders);
    safe.setContentType(MediaType.parseMediaType(
        "application/problem+json"));
    safe.setCacheControl(CacheControl.noStore());
    return handleExceptionInternal(ex, body, safe,
        HttpStatus.BAD_REQUEST, request);
}
~~~

Chữ ký override dùng `HttpStatusCode` của Spring Framework 6; bổ sung import phù hợp version. Đây là **các phương thức thêm vào advice**, không phải file độc lập. Parse/validation có thể xảy ra trước khi controller chạy.

Đối với validation trên `@RequestParam`/`@PathVariable` hay method-level constraints, Spring có thể phát sinh exception **khác `MethodArgumentNotValidException`** (ví dụ `HandlerMethodValidationException` ở các phiên bản hỗ trợ). Cần test đúng version và loại validation thực dùng; đừng giả định một override trên bao hết mọi trường hợp.

### 7.2. Điều gì xảy ra với 405, 406, 415?

`ResponseEntityExceptionHandler` đã có xử lý framework cho **405** (method không hỗ trợ), **406** (`Accept` không phù hợp) và **415** (`Content-Type` request không hỗ trợ). Không cần đăng ký lại chỉ để trả status mặc định. Khi tùy biến body, test content negotiation: client chỉ chấp nhận XML có thể không đọc được `application/problem+json`; `406` không body có thể phù hợp hơn ép JSON.

## 8. Bảo mật: `@RestControllerAdvice` không thay Spring Security

Spring Security thường kiểm tra request trong **filter chain trước khi vào controller**. Vì vậy:

- Không có token hoặc token không hợp lệ → **401** qua `AuthenticationEntryPoint`.
- Caller đã được xác thực nhưng thiếu quyền → **403** qua `AccessDeniedHandler` hoặc cơ chế security phù hợp.
- Caller biết ID đơn của tenant khác → kiểm tra **object-level authorization** tại service/repository; có thể trả **404** nếu policy chọn che sự tồn tại.

Một handler MVC chung `@ExceptionHandler(SecurityException.class)` **không bảo đảm** xử lý được các lỗi do security filter phát ra trước `DispatcherServlet`. Cần cấu hình entry point và denied handler cho JSON API.

### 8.1. Gắn error handlers vào filter chain

Ví dụ **một phần cấu hình `HttpSecurity`** (các bean entry point/denied handler và rules xác thực phải được định nghĩa riêng):

~~~java
http.exceptionHandling(errors -> errors
    .authenticationEntryPoint(apiAuthenticationEntryPoint)
    .accessDeniedHandler(apiAccessDeniedHandler));
// Sau đó cấu hình authorizeHttpRequests, OAuth2 Resource Server/JWT
// và gọi http.build() trong bean SecurityFilterChain.
~~~

`apiAuthenticationEntryPoint` viết status **401**, header `WWW-Authenticate` đúng Bearer contract và một `ProblemDetail` công khai; `apiAccessDeniedHandler` viết **403**. Có thể dùng Jackson `ObjectMapper` để serialize `ProblemDetail` sau khi đặt `Content-Type: application/problem+json` và `Cache-Control: no-store`. Tách factory tạo problem dùng chung nếu muốn cùng format với MVC. **Không** đưa `exception.getMessage()`, token hoặc stack trace vào body; xử lý các quy tắc `WWW-Authenticate` chi tiết theo OAuth2 Bearer.

### 8.2. Che thông tin nhưng vẫn quan sát được

Một `404` có thể che cả resource không tồn tại và resource ngoài quyền. Audit nội bộ phân biệt nguyên nhân nếu cần, nhưng không lộ owner/tenant. Với `traceId`, dùng ID đã được gateway/server xác minh, không dùng nguyên raw header, URL hoặc query chứa token.

## 9. Dữ liệu Spring: phân loại exception từ persistence

Spring Data/JPA có các exception kỹ thuật. Chúng **không tự quyết định** mã HTTP:

| Exception/cơ chế | Nguyên nhân thường gặp | Quyết định tại service/boundary |
|---|---|---|
| `EmptyResultDataAccessException` / Optional rỗng | Không có row phù hợp | Chuyển thành `OrderNotFoundException` nếu đúng policy |
| `DataIntegrityViolationException` | Unique/FK/constraint | Kiểm tra constraint cụ thể; conflict domain có thể là 409, bug khác là 5xx |
| `OptimisticLockingFailureException` | Version cũ hoặc update cạnh tranh | `412` cho failed `If-Match` đúng hợp đồng, ngược lại xét 409/retry |
| `DataAccessResourceFailureException` | DB kết nối/hạ tầng | 503/500 theo tình trạng; log và alert, không tiết lộ JDBC URL |
| Lỗi rollback/commit transaction | Transaction không hoàn tất | Không gửi thành công trước khi commit; xác định trạng thái và idempotency |

Ví dụ service có `@Transactional`: kiểm tra quyền theo tenant, đọc entity, kiểm tra trạng thái, cập nhật và commit. Nếu optimistic locking ném exception khi flush/commit, **transaction đã thất bại**; không chỉ bắt exception rồi trả `200` như thể đã ghi xong. Với conditional write có `If-Match`, adapter/service cần phân biệt precondition không thỏa để map đúng `412`.

**Không map mọi `RuntimeException` thành 400**, vì bug, cấu hình sai, lỗi SQL hoặc lỗi serialize response sẽ bị ngụy trang thành lỗi phía client. Các lỗi bất ngờ nên được xử lý ở đường fallback 5xx, log có correlation ID, che chi tiết và đo metric; đừng bắt rộng rồi nuốt lỗi mà không báo vận hành.

## 10. OpenAPI 3.1: mô tả lỗi như một phần hợp đồng

Mô tả các status có ý nghĩa cho client, không chỉ `200` và `500`. Một đoạn OpenAPI rút gọn:

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /v1/orders:
    post:
      security: [{bearerAuth: []}]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [productId, quantity]
              additionalProperties: false
              properties:
                productId: {type: string, minLength: 1}
                quantity: {type: integer, minimum: 1}
      responses:
        '201':
          description: Tạo đơn thành công
          headers:
            Location:
              schema: {type: string, format: uri-reference}
        '400': {$ref: '#/components/responses/ProblemResponse'}
        '401': {description: Chưa xác thực}
        '403': {description: Không có quyền}
        '422': {$ref: '#/components/responses/ProblemResponse'}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  responses:
    ProblemResponse:
      description: Lỗi theo Problem Details
      content:
        application/problem+json:
          schema: {$ref: '#/components/schemas/Problem'}
  schemas:
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
~~~

Trong bản đầy đủ, mô tả thêm `GET /orders/{id}` (404), cancellation (409), conditional update (412/428) và 429/503 cùng `Retry-After` khi có. `errors` là extension không bắt buộc của `ProblemDetail`. **OpenAPI không tự ánh xạ exception**; runtime và tests phải thực thi hợp đồng.

## 11. Kiểm thử với MockMvc và test persistence

Ma trận cần đủ **HTTP status, body an toàn và dữ liệu không đổi khi thất bại**:

| Test | Kỳ vọng |
|---|---|
| GET ID được phép nhưng không tồn tại | `404` + `ORDER_NOT_FOUND` |
| GET ID ngoài tenant | `404` theo policy; không lộ owner/tenant |
| POST body malformed | `400` + `MALFORMED_BODY` |
| POST thiếu productId/quantity=0 | `400` + `VALIDATION_FAILED`, danh sách field giới hạn |
| POST vi phạm quy tắc domain | `422` + `ORDER_RULE_VIOLATION` |
| POST cancellation khi đơn đã giao | `409` + `ORDER_NOT_CANCELLABLE` |
| Cập nhật có `If-Match` stale | `412` và không ghi đè |
| Token thiếu/không hợp lệ | `401` do security filter, không gọi service |
| Thiếu scope | `403`, không gọi service |
| Exception DB bất ngờ | 5xx che chi tiết SQL/stack; có log nội bộ |
| `Accept: application/xml` khi chỉ có JSON | Lỗi negotiation phù hợp; không ép JSON |
| Có hai advice trùng handler | Test context khởi động, không bị ambiguous mapping |

Ví dụ assertion (giả định có `@WebMvcTest`, Spring Security Test, `OrderErrorAdvice` và mock `OrderService`):

~~~java
// Static imports MockMvc, Mockito BDD, SecurityMockMvc,
// jsonPath, status, content...
given(service.getVisible("user_A", "ord_missing"))
    .willThrow(new OrderNotFoundException());

mockMvc.perform(get("/v1/orders/ord_missing")
        .with(jwt()
            .jwt(token -> token.subject("user_A"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read")))
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/problem+json")))
    .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
    .andExpect(jsonPath("$.status").value(404));

mockMvc.perform(post("/v1/orders")
        .with(jwt().authorities(new SimpleGrantedAuthority(
            "SCOPE_orders.write")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"productId\":\"\",\"quantity\":0}"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
~~~

MockMvc kiểm tra HTTP boundary, **không chứng minh DB rollback hoặc ACL đúng**. Dùng integration test cho constraint, version, tenant và commit; xác minh `errors` không lộ input nhạy cảm. Test 401/403 phải chạy security filter thật.

## 12. Bài thực hành: chuẩn hóa lỗi API đặt hàng

**Bối cảnh:** API có `GET /v1/orders/{id}`, `POST /v1/orders` và `POST /v1/orders/{id}/cancellations`. Hiện nay controller bắt mọi `Exception` trả `200 {"error": "..."}`. Hãy sửa để:

1. Tách request DTO, entity và response DTO; dùng Bean Validation cho `productId` và `quantity`.
2. Định nghĩa exception `OrderNotFound`, `OrderNotCancellable` và một lỗi domain validation; chọn `404/409/422` có lý do.
3. Viết `@RestControllerAdvice` trả `ProblemDetail` với `type`, `status`, `code`, `detail` an toàn.
4. Kế thừa `ResponseEntityExceptionHandler` và override lỗi malformed JSON/`@Valid`; không đăng ký handler trùng.
5. Thiết kế `AuthenticationEntryPoint`/`AccessDeniedHandler` để 401/403 thống nhất với policy; không tin ID đoán được.
6. Viết OpenAPI cho các mã lỗi; dùng MockMvc kiểm tra ít nhất tám tình huống, trong đó có lỗi DB và người dùng khác tenant.

**Gợi ý:** với `POST` thiếu field, controller chưa được gọi mà advice vẫn xử lý được. Với đơn đã giao, service ném domain exception, advice trả 409. Nếu DB tạm mất kết nối, không được biến thành 400 hoặc trả lỗi SQL. **Khóa bảo mật không nằm ở cấu trúc JSON lỗi**: mọi GET/POST vẫn phải kiểm tra quyền và tenant ở server.

## 13. Ghi nhớ

`@ExceptionHandler` xử lý exception **có ý nghĩa trong phạm vi controller**, còn `@RestControllerAdvice` chuẩn hóa việc ánh xạ lỗi giữa các controller. Với Spring 6, `ProblemDetail` và `ResponseEntityExceptionHandler` giúp sử dụng HTTP status và Problem Details nhất quán; các exception MVC đã có handler kế thừa thì nên **override**, không đăng ký trùng.

Phân loại lỗi theo nguyên nhân, **không theo tên exception Java đơn thuần**. Dùng 400 cho request không hợp lệ, 404/409/412 cho tình huống tài nguyên/trạng thái phù hợp, 401/403 qua bảo mật và 5xx cho sự cố không mong đợi. Luôn xác minh **status, body không lộ dữ liệu, quyền truy cập và tính nguyên vẹn của cập nhật** bằng kiểm thử.
