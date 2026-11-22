# ProblemDetail, ErrorResponse và trường mở rộng

## 1. Vì sao cần một hợp đồng lỗi thống nhất?

Trong REST API, cùng một yêu cầu tạo đơn có thể thất bại vì **JSON không hợp lệ**, **thiếu field bắt buộc**, **sản phẩm không tồn tại**, **mã đơn bị trùng**, **không có quyền** hoặc **database gián đoạn**. Nếu các controller trả JSON tùy hứng như **{"error":"bad"}**, **{"message":"conflict"}** hay một trang HTML lỗi, client khó phân biệt hành vi và khó đối soát.

**Problem Details (RFC 9457)** cung cấp cấu trúc chung cho response lỗi HTTP. Trong **Spring Framework 6**, **ProblemDetail** biểu diễn body, **ErrorResponse** mô tả cả status/headers/body và **ResponseEntityExceptionHandler** hỗ trợ xử lý nhiều lỗi MVC. Các trường mở rộng cho phép API công bố **mã lỗi ổn định, danh sách field validation và request ID** mà không tự tạo một envelope trái chuẩn.

Bài thuộc chương **Dữ liệu và lỗi Spring** của module **INTEGRATION_API_REST**. Nội dung gắn với thiết kế resource/URI, HTTP method và status, hợp đồng JSON/OpenAPI, xác thực/phân quyền và kiểm thử API với Java 17+, Spring Boot 3.x hoặc công nghệ tương đương.

Mục tiêu sau bài:

1. Phân biệt **type/title/status/detail/instance** với các **extension members**.
2. Sử dụng **ProblemDetail, ErrorResponse và ErrorResponseException** đúng trách nhiệm.
3. Chuẩn hóa lỗi Spring MVC bằng **@RestControllerAdvice**.
4. Ánh xạ lỗi validation, nghiệp vụ, optimistic locking và database sang status chính xác.
5. Giữ HTTP 401/403 theo Spring Security, không làm lộ SQL, stack trace hoặc thông tin ngoài quyền.
6. Thiết kế OpenAPI 3.1 và kiểm thử **MockMvc, security, concurrency**.

**Mã lỗi như ORDER_REFERENCE_CONFLICT, VALIDATION_FAILED và URI ví dụ là quy ước của API trong bài**, không phải tên do Spring hoặc RFC bắt buộc.

## 2. Cấu trúc Problem Details theo RFC 9457

Ví dụ client gửi POST tạo đơn có mã tham chiếu đã được dùng:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{
  "externalReference": "checkout-739",
  "productId": "prod-42",
  "quantity": 2
}
~~~

Server trả:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/order-reference-conflict",
  "title": "Order reference conflict",
  "status": 409,
  "detail": "Mã tham chiếu đơn hàng đã được sử dụng.",
  "instance": "/api/v1/orders",
  "code": "ORDER_REFERENCE_CONFLICT",
  "requestId": "req-9fb2"
}
~~~

| Trường | Ý nghĩa |
| --- | --- |
| **type** | URI định danh **loại vấn đề**, nên ổn định và có thể trỏ tới tài liệu xử lý. |
| **title** | Tên ngắn của loại lỗi; có thể bản địa hóa. |
| **status** | Status HTTP tương ứng; phải nhất quán với dòng trạng thái thật. |
| **detail** | Giải thích lỗi cụ thể theo cách an toàn cho client. |
| **instance** | URI-reference xác định trường hợp lỗi/đường dẫn request theo contract. |
| **code, requestId** | **Extension members**, không phải trường chuẩn của RFC. |

Năm trường chuẩn không phải lúc nào cũng bắt buộc xuất hiện. Khi thiếu **type**, ý nghĩa mặc định là **about:blank**; client vẫn dùng **HTTP status thực tế**, không chỉ tin body.status. Với body lỗi status 409 mà HTTP line là 200, đó là **hợp đồng sai**.

**Đừng dùng detail hoặc title làm khóa nhánh code của client.** Câu chữ, ngôn ngữ có thể thay đổi. Dùng **type URI**, **code** được tài liệu hóa và HTTP status. Lỗi của GET thành công hoặc response **204/304** không nên bị trộn với Problem Details vì các response không có body.

## 3. ProblemDetail, ErrorResponse và các lớp của Spring

| Thành phần | Vai trò |
| --- | --- |
| **ProblemDetail** | Value object chứa status, type, title, detail, instance và properties mở rộng. |
| **ErrorResponse** | Interface của Spring gồm **HttpStatusCode, HttpHeaders, ProblemDetail body** và hỗ trợ message resolution. |
| **ErrorResponseException** | Exception triển khai ErrorResponse, mang status/ProblemDetail khi cần throw trực tiếp. |
| **ResponseStatusException** | Exception gắn với HTTP status/reason; phù hợp lỗi đơn giản. |
| **ResponseEntityExceptionHandler** | Base advice xử lý lỗi chuẩn Spring MVC, cung cấp điểm override để nhất quán body. |
| **@RestControllerAdvice** | Áp dụng handler cho controller; không tự bắt mọi lỗi từ Spring Security filter. |

**ProblemDetail là nội dung lỗi; ErrorResponse bao trùm nội dung cùng status và headers.** Ví dụ 401 cần **WWW-Authenticate**, 429/503 có thể cần **Retry-After**. Những header này không được thay thế bằng các property JSON tùy ý.

Tạo body bằng Spring:

~~~java
ProblemDetail body = ProblemDetail.forStatusAndDetail(
    HttpStatus.CONFLICT,
    "Mã tham chiếu đơn hàng đã được sử dụng.");

body.setType(URI.create(
    "https://api.example.com/problems/order-reference-conflict"));
body.setTitle("Order reference conflict");
body.setProperty("code", "ORDER_REFERENCE_CONFLICT");
~~~

Khi Spring/Jackson serialize ProblemDetail, các entries trong **properties** được đưa thành **top-level extension members**: **"code"** xuất hiện ngang **"type"**, không phải bắt buộc nằm trong **"properties"**. Tránh đặt extension trùng tên năm trường chuẩn và viết contract test để bắt sai lệch serializer.

Spring Boot có thể bật hỗ trợ Problem Details cho các exception của framework qua cấu hình **spring.mvc.problemdetails.enabled=true** theo phiên bản Boot. Đây không có nghĩa mọi domain exception, filter security hoặc lỗi từ mọi thành phần tự mang đúng **code** riêng; vẫn cần exception mapping phù hợp.

## 4. Trường mở rộng: thiết kế để máy xử lý được

Ví dụ validation với nhiều lỗi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "Dữ liệu yêu cầu không hợp lệ.",
  "instance": "/api/v1/orders",
  "code": "VALIDATION_FAILED",
  "requestId": "req-bc12",
  "violations": [
    {"field":"externalReference","reason":"không được để trống"},
    {"field":"quantity","reason":"phải lớn hơn hoặc bằng 1"}
  ]
}
~~~

Quy tắc thiết kế:

- **code** là chuỗi machine-readable ổn định, ví dụ **VALIDATION_FAILED** hoặc **ORDER_REFERENCE_CONFLICT**. Không đổi chỉ vì sửa câu chữ.
- **violations** là danh sách có schema rõ (field/reason); có thể bổ sung path hoặc violationCode nếu cần, nhưng không trả mọi giá trị bị từ chối.
- **requestId/traceId** lấy từ hạ tầng tin cậy, dùng để liên hệ log. Không tin raw ID do client gửi mà không xác thực/chuẩn hóa.
- **retryable** chỉ có giá trị nếu có quy tắc retry được công bố; 409 không mặc nhiên retryable và timeout không chứng minh chưa commit.
- **type URI** là định danh ổn định, độc lập tên class Java, version build và tenant. Nếu có tài liệu tại URI, nội dung nên giải thích cách khắc phục.

**Không phản chiếu token, password, email, SQL, rejectedValue hoặc stack trace trong detail/violations**. Mọi extension phải có kiểu nhất quán giữa response và OpenAPI; đừng đổi violations từ array thành object mà không version/migration.

## 5. Ánh xạ HTTP status theo nguyên nhân thực

| Tình huống | Status thường phù hợp | Lưu ý |
| --- | --- | --- |
| JSON sai cú pháp/type deserialize lỗi | **400 Bad Request** | Lỗi request thực sự. |
| Bean Validation thất bại | **400 Bad Request** | Tạo danh sách violations có kiểm soát. |
| Resource không tồn tại trong scope được phép biết | **404 Not Found** | Không rò sự tồn tại của tenant khác. |
| Unique business key trùng, trạng thái không cho phép thao tác | **409 Conflict** | Chỉ khi đã xác định đúng conflict. |
| **If-Match** không khớp validator hiện tại | **412 Precondition Failed** | Do HTTP precondition thất bại. |
| Dữ liệu đúng cú pháp nhưng không xử lý được về ngữ nghĩa | **422 Unprocessable Content** hoặc mã khác theo contract | Không tự dùng thay 400/409. |
| Chưa xác thực hợp lệ | **401 Unauthorized** | Giữ challenge theo scheme. |
| Có xác thực nhưng thiếu quyền | **403 Forbidden** | Có thể dùng 404 để che resource theo chính sách. |
| Rate limit | **429 Too Many Requests** | Retry-After nếu có thời gian chờ phù hợp. |
| Database mất kết nối/tạm ngừng | **503** hoặc **500** tùy trường hợp | Không trả SQL lỗi cho client. |
| Bug hoặc lỗi không dự kiến | **500 Internal Server Error** | Thông điệp chung, log chi tiết nội bộ. |

**409 không đồng nghĩa 412.** Nếu client gửi If-Match với ETag cũ, 412 diễn đạt điều kiện HTTP không còn đúng; nếu một lệnh chuyển trạng thái vi phạm luật nghiệp vụ và không có HTTP precondition, 409 có thể phù hợp. Một optimistic-lock exception nội bộ **không tự chứng minh** client đã gửi If-Match.

**400 và 422** có thể được chọn khác nhau tùy API; cần ghi rõ logic trong tài liệu. Không trả mọi exception thành 400, không biến lỗi database thành response 200 với body có **status: 500**.

## 6. API tạo đơn hàng với validation

Record DTO mô tả input client được phép gửi:

~~~java
public record CreateOrderRequest(
    @NotBlank String externalReference,
    @NotBlank String productId,
    @NotNull @Min(1) Integer quantity
) {}

public record OrderResponse(
    String id, String externalReference, String status
) {}

@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest body,
            Authentication caller) {

        OrderResponse created =
            service.createForAuthorizedTenant(caller, body);

        URI location = URI.create("/api/v1/orders/" + created.id());
        return ResponseEntity.created(location)
            .cacheControl(CacheControl.noStore())
            .body(created);
    }
}
~~~

**OrderService** là thành phần ứng dụng cần tự cài: kiểm tra quyền dựa trên principal, không tin tenantId từ body, ghi database trong transaction và trả DTO sau khi tạo thành công. **@Valid** chạy Bean Validation; nó không thay thế authorization, ràng buộc unique hoặc transaction.

Với nhiều POST đồng thời dùng một externalReference, code **exists → insert** có race. Database nên có **UNIQUE (tenant_id, external_reference)**, và service phải phân biệt đúng conflict constraint này với các lỗi dữ liệu khác.

## 7. ResponseEntityExceptionHandler: chuẩn hóa validation và JSON lỗi

Một advice kế thừa **ResponseEntityExceptionHandler** để tùy chỉnh lỗi Spring MVC:

~~~java
@RestControllerAdvice
public class ApiErrors extends ResponseEntityExceptionHandler {

    private static final MediaType PROBLEM_JSON =
        MediaType.parseMediaType("application/problem+json");

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status, "Dữ liệu yêu cầu không hợp lệ.");
        problem.setType(URI.create(
            "https://api.example.com/problems/validation-failed"));
        problem.setTitle("Validation failed");
        problem.setProperty("code", "VALIDATION_FAILED");

        List<Map<String, String>> violations =
            ex.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "reason", error.getDefaultMessage() == null
                        ? "không hợp lệ" : error.getDefaultMessage()))
                .toList();

        problem.setProperty("violations", violations);

        HttpHeaders outgoing = new HttpHeaders();
        outgoing.putAll(headers);
        outgoing.setContentType(PROBLEM_JSON);
        return handleExceptionInternal(
            ex, problem, outgoing, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status, "JSON không hợp lệ hoặc sai kiểu dữ liệu.");
        problem.setType(URI.create(
            "https://api.example.com/problems/invalid-json"));
        problem.setTitle("Invalid JSON");
        problem.setProperty("code", "INVALID_JSON");

        HttpHeaders outgoing = new HttpHeaders();
        outgoing.putAll(headers);
        outgoing.setContentType(PROBLEM_JSON);
        return handleExceptionInternal(
            ex, problem, outgoing, status, request);
    }
}
~~~

Chữ ký override phù hợp Spring Framework 6.x, cần imports tương ứng. **Map.of không cho giá trị null**, nên example có default message thay thế. Chỉ trả **field/reason**, không đưa raw rejected value, nhất là password/PII. Nên giới hạn số violations nếu request có collection lớn và đảm bảo validator messages an toàn.

Khi thay headers của exception framework, **giữ các header có ý nghĩa HTTP** (ví dụ Allow ở 405 hoặc thông tin negotiation) thay vì làm mất chúng. Code trên sao chép headers. Spring Boot có cơ chế xử lý ProblemDetail mặc định, nhưng advice là nơi chuẩn hóa **type/code/violations** theo hợp đồng API.

### Ánh xạ domain exception trong cùng advice

Có thể bổ sung một handler cho exception nghiệp vụ **thuần Java**:

~~~java
public final class DuplicateOrderReference
        extends RuntimeException {}

@ExceptionHandler(DuplicateOrderReference.class)
public ResponseEntity<ProblemDetail> onDuplicate(
        DuplicateOrderReference ex) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Mã tham chiếu đơn hàng đã được sử dụng.");
    problem.setType(URI.create(
        "https://api.example.com/problems/order-reference-conflict"));
    problem.setTitle("Order reference conflict");
    problem.setProperty("code", "ORDER_REFERENCE_CONFLICT");

    return ResponseEntity.status(HttpStatus.CONFLICT)
        .contentType(MediaType.parseMediaType("application/problem+json"))
        .cacheControl(CacheControl.noStore())
        .body(problem);
}
~~~

Đoạn code handler **nằm trong class ApiErrors**, sau hai override, không phải một phương thức top-level ngoài class. Thực tế có thể tách formatter chung để tránh lặp các field chuẩn nhưng không làm mất status/header.

## 8. ErrorResponseException là một lựa chọn khác

Nếu muốn exception mang thẳng HTTP error body, **ErrorResponseException** triển khai ErrorResponse:

~~~java
public final class OrderConflictException
        extends ErrorResponseException {

    public OrderConflictException() {
        super(HttpStatus.CONFLICT, problem(), null);
    }

    private static ProblemDetail problem() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Mã tham chiếu đã được sử dụng.");
        p.setType(URI.create(
            "https://api.example.com/problems/order-reference-conflict"));
        p.setProperty("code", "ORDER_REFERENCE_CONFLICT");
        return p;
    }
}
~~~

Constructor này nhận **HttpStatusCode, ProblemDetail, Throwable cause**. Spring MVC có hỗ trợ ErrorResponseException thông qua cơ chế xử lý lỗi, đặc biệt khi ứng dụng dùng ResponseEntityExceptionHandler.

**Chọn một trong hai cách cho cùng lỗi:** hoặc ném domain exception rồi advice chuyển đổi, hoặc ném ErrorResponseException đã chứa contract. Với tầng nghiệp vụ có thể tái sử dụng từ batch/message consumer, **domain exception thuần Java** thường giúp tránh phụ thuộc Spring Web. Không nên rải logic HTTP serialization khắp repository và service.

## 9. Lỗi dữ liệu: không map theo tên exception một cách máy móc

Spring Data/JDBC sử dụng họ **DataAccessException**, nhưng cùng một exception có thể có nhiều nguyên nhân:

| Nhóm | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **DataIntegrityViolationException** | Vi phạm unique, foreign key, NOT NULL, check | Chỉ trả **409** nếu đúng constraint xung đột nghiệp vụ; không coi mọi lỗi DB là “đơn trùng”. |
| **ObjectOptimisticLockingFailureException** | Version entity đã thay đổi | **412** nếu If-Match không khớp; 409 có thể phù hợp cho conflict khác. |
| **DataAccessResourceFailureException** | Database/kết nối không dùng được | 503 hoặc 500 tùy bản chất; không trả 400. |
| **QueryTimeoutException** | Query vượt thời hạn | Kết quả giao dịch có thể chưa rõ; không khẳng định rollback chỉ vì timeout. |

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    external_reference VARCHAR(120) NOT NULL,
    product_id VARCHAR(120) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    UNIQUE (tenant_id, external_reference)
);
~~~

Hai request đồng thời cùng tenant và externalReference có thể cùng qua kiểm tra **exists** trước khi INSERT. **Unique constraint** mới quyết định nguyên tử chỉ một giao dịch thắng.

~~~text
POST /orders
  -> Authentication/authorization + validate
  -> INSERT trong transaction
     -> Commit thành công: 201 + Location
     -> Đúng unique(tenant, external_reference) xung đột:
          DuplicateOrderReference -> 409
     -> Ràng buộc khác/database hỏng:
          phân loại lỗi, không giả 409
~~~

Trong JPA, lỗi unique có thể xuất hiện ở **flush/commit**, không nhất thiết tại **repository.save**. Chỗ dịch exception và transaction boundary phải được test bằng database thực. Không đưa raw SQL/constraint message vào ProblemDetail; chỉ log nội bộ có kiểm soát.

Nếu client dùng **If-Match** và precondition thất bại, trả **412 Precondition Failed**. Một optimistic-lock exception xảy ra mà không có If-Match **không tự chứng minh** HTTP precondition đã sai.

## 10. 401/403 và ranh giới Spring Security

Nhiều lỗi xác thực đến từ **Spring Security filter chain** trước controller. **AuthenticationEntryPoint** xử lý trường hợp chưa xác thực, **AccessDeniedHandler** xử lý truy cập bị từ chối theo cấu hình. **@RestControllerAdvice không tự bắt mọi AuthenticationException/AccessDeniedException** phát sinh ở filter.

Với Bearer token, 401 cần giữ **WWW-Authenticate**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "code": "AUTHENTICATION_REQUIRED"
}
~~~

Nếu tùy biến body bằng ProblemDetail, vẫn phải bảo toàn challenge theo scheme; có thể tận dụng AuthenticationEntryPoint hỗ trợ Bearer của Spring Security và test output thực. **403** phù hợp caller đã xác thực nhưng không có quyền; đôi khi **404** được dùng để che sự tồn tại resource khác tenant. Không để detail/extension tiết lộ owner, dữ liệu hoặc ID ngoài quyền.

Response lỗi có thông tin riêng tư nên có chính sách **Cache-Control: no-store** phù hợp. **requestId** lấy từ hạ tầng tin cậy; không biến raw header do client gửi thành bằng chứng điều tra. Giới hạn body size, số violations và log; không xuất token/PII/stack trace.

### Bản địa hóa có cấu trúc

Spring **ErrorResponse** và **ResponseEntityExceptionHandler** hỗ trợ MessageSource cho thông điệp theo locale khi được cấu hình. Có thể đổi **title/detail** sang tiếng Việt theo Accept-Language nhưng giữ **type, code, status** ổn định. Nếu cache response theo ngôn ngữ, dùng **Vary: Accept-Language** phù hợp; không để client dựa vào câu chữ làm logic.

Metric nên tổng hợp theo **HTTP status, code, endpoint template**. Không dùng detail, user ID, raw URL có PII hoặc requestId làm label có cardinality cao.

## 11. OpenAPI 3.1 cho ErrorResponse và extension

~~~yaml
openapi: 3.1.0
info: { title: Orders API, version: 1.0.0 }
paths:
  /api/v1/orders:
    post:
      summary: Tạo đơn hàng
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [externalReference, productId, quantity]
              properties:
                externalReference: { type: string, minLength: 1 }
                productId: { type: string, minLength: 1 }
                quantity: { type: integer, minimum: 1 }
      responses:
        '201':
          description: Đơn đã tạo
          headers:
            Location:
              required: true
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: { type: string }
                  externalReference: { type: string }
                  status: { type: string }
        '400':
          description: JSON hoặc validation không hợp lệ
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/ApiProblem' }
        '401':
          description: Chưa xác thực
          headers:
            WWW-Authenticate:
              schema: { type: string }
        '403': { description: Không có quyền }
        '404': { description: Resource liên quan không tìm thấy }
        '409':
          description: Business key hoặc trạng thái xung đột
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/ApiProblem' }
        '415': { description: Media type của request không hỗ trợ }
        '500':
          description: Lỗi server ngoài dự kiến
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/ApiProblem' }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    ApiProblem:
      type: object
      description: RFC 9457 với extension riêng của API
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
        instance: { type: string, format: uri-reference }
        code: { type: string }
        requestId: { type: string }
        violations:
          type: array
          items:
            type: object
            required: [field, reason]
            properties:
              field: { type: string }
              reason: { type: string }
~~~

Nếu API **cam kết mọi lỗi có code**, thêm **required: [code]** rồi bảo đảm **cả MVC advice, Security filter và gateway** đáp ứng. Nếu **violations** chỉ xuất hiện với 400 validation, không đánh dấu bắt buộc cho toàn bộ 500; có thể dùng schema riêng **ValidationProblem**.

**HTTP status và body.status phải khớp.** OpenAPI mô tả chứ không tự tạo extension, không tự bật Problem Details hay xác thực/phân quyền. Nên đặt JSON success và error dưới đúng response code/media type; không dùng một schema lỗi chung dưới status 200.

## 12. MockMvc: kiểm tra body, status và media type

~~~java
@Test
void invalidOrderReturnsProblemDetails() throws Exception {
    mockMvc.perform(post("/api/v1/orders")
            .with(user("buyer").roles("BUYER"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"externalReference":"",
                 "productId":"prod-42",
                 "quantity":0}
                """))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.parseMediaType("application/problem+json")))
        .andExpect(jsonPath("$.status").value(400))
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.violations").isArray());
}

@Test
void invalidJsonIsSafeProblem() throws Exception {
    mockMvc.perform(post("/api/v1/orders")
            .with(user("buyer").roles("BUYER"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"quantity\":"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_JSON"));
}
~~~

Test cần controller/advice, fixture và Spring Security test. Với cookie session/CSRF protection, POST cần CSRF token hợp lệ; với Bearer API, mô phỏng đúng authentication. **Không tắt security để test pass**.

## 13. Ma trận kiểm thử thực tế

MockMvc với service mock chỉ chứng minh handler định dạng đúng, chưa chứng minh unique constraint hay transaction. Kết hợp **@WebMvcTest hoặc MockMvc context**, **integration test database** và test đi qua **Security filter chain**.

| Tình huống | Kỳ vọng |
| --- | --- |
| Missing field/quantity=0 | 400 VALIDATION_FAILED; violations không chứa input nhạy cảm |
| JSON sai cú pháp hoặc type | 400 INVALID_JSON, không lộ Jackson stack trace |
| Content-Type text/plain | 415 theo contract, không thành lỗi validation |
| Product không tồn tại hoặc ngoài quyền | 404 theo chính sách, không lộ owner |
| externalReference đã tồn tại | 409 ORDER_REFERENCE_CONFLICT, không tạo row mới |
| Hai POST đồng thời cùng business key | Đúng một commit, một request nhận conflict |
| If-Match cũ khi sửa tài nguyên | 412, không ghi đè |
| Thiếu/hết hạn Bearer token | 401 + WWW-Authenticate hợp lệ |
| Có token nhưng thiếu quyền | 403 hoặc 404 theo chính sách, không lộ dữ liệu |
| Database outage hoặc bug | 503/500, body generic, log nội bộ có correlation |
| JSON extensions của ProblemDetail | code/violations ở cấp top-level, status khớp HTTP |
| Thay đổi Accept-Language | title/detail có thể đổi; type/code không đổi |

Nếu test **409** bằng mock service ném DuplicateOrderReference thì chỉ kiểm tra mapping; phải thêm test trên database thật hoặc môi trường tương đương để xác minh unique và thời điểm lỗi khi **flush/commit**. Test 401 cần đi qua Spring Security, vì controller advice không đảm bảo bắt lỗi filter.

Đưa OpenAPI schema validator vào CI; so status, media type, headers và extensions với response runtime. Khi thêm mã lỗi mới, cập nhật **code/type**, tài liệu và tests trong cùng thay đổi.

## 14. Sai lầm cần tránh

| Sai lầm | Rủi ro | Sửa |
| --- | --- | --- |
| HTTP 200 nhưng body.status=400 | Client/cache hiểu sai | Dùng HTTP status thật |
| Client phân nhánh bằng detail/title | Hỏng khi đổi ngôn ngữ | Dùng code/type ổn định |
| Trả SQL hoặc rejectedValue trong lỗi | Rò PII/secret | Detail an toàn, log nội bộ |
| Mọi DataIntegrityViolationException thành 409 | Che lỗi FK/NOT NULL/hạ tầng | Phân loại constraint |
| Mọi optimistic locking thành 412 | Sai nếu không có precondition | Xét If-Match và contract |
| Extension trùng tên field chuẩn | JSON nhập nhằng | Dùng tên riêng như code, violations |
| Chỉ có MVC advice cho authentication | Không xử lý hết filter errors | EntryPoint/AccessDeniedHandler |
| Tùy biến 401 làm mất WWW-Authenticate | Sai HTTP auth semantics | Giữ challenge |
| Response lỗi chứa tenant/owner | Information disclosure | Authz và 403/404 nhất quán |

## 15. Bài thực hành: đặt ghế có xung đột dữ liệu

Thiết kế **POST /api/v1/reservations**:

~~~json
{
  "eventId": "evt-204",
  "seatCode": "A-12",
  "attendeeName": "Nguyễn An"
}
~~~

Yêu cầu: eventId/seatCode/attendeeName bắt buộc; một ghế thuộc một event chỉ được đặt một lần nhờ **UNIQUE(event_id, seat_code)**. Caller chỉ được đặt trong phạm vi quyền; không cho người khác biết ai đã giữ ghế. Hai request đồng thời cùng ghế chỉ tạo **một** reservation.

Nhiệm vụ:

1. Viết DTO, controller/service và constraint/transaction nguyên tử; nêu cách xử lý ràng buộc phát sinh ở commit.
2. Lập bảng **nguyên nhân → status → ProblemDetail.type → code → extensions**: 400 validation, 404 event vắng mặt, 409 SEAT_ALREADY_RESERVED, 401/403 bảo mật và 500/503 hạ tầng.
3. Dùng **ResponseEntityExceptionHandler** cho lỗi JSON/Bean Validation và **@ExceptionHandler** cho xung đột ghế; giải thích phương án thay thế bằng ErrorResponseException.
4. Viết OpenAPI 3.1 cho success 201 + Location và các lỗi; định nghĩa code/violations/requestId, không đưa attendeeName vào lỗi.
5. Viết tối thiểu **8 MockMvc/integration tests** gồm 400, 401, 403, 404, 409, 415, 500/503, unique race, extension ở top-level, không lộ PII.
6. Thử concurrency với database thực: chỉ một row, không biến lỗi foreign key thành SEAT_ALREADY_RESERVED.
7. Viết ADR ngắn về status, mã lỗi ổn định, bản địa hóa, logging và giới hạn retry.

**Đầu ra:** hợp đồng HTTP, Java/Spring, OpenAPI, schema database, test matrix và các tình huống lỗi đã kiểm chứng.

## 16. Checklist và kết luận

Trước khi đưa API vào production:

- HTTP status **đúng** và body.status (nếu có) khớp.
- **ProblemDetail** có type/title/detail an toàn, instance không lộ dữ liệu.
- **ErrorResponse** được hiểu là **status + headers + body**, không chỉ JSON.
- **code/violations/requestId** là extension có schema và hành vi ổn định.
- Lỗi parsing, validation, nghiệp vụ và database được phân loại đúng.
- 401/403 qua Spring Security giữ challenge và quyền.
- Unique constraint, optimistic locking và concurrency được test thực tế.
- OpenAPI, MVC advice, HTTP test và monitoring thống nhất.

**Kết luận:** **ProblemDetail** chuẩn hóa cách trình bày lỗi; **ErrorResponse** kết hợp body với status/headers; **trường mở rộng** cung cấp mã lỗi và thông tin validation để client xử lý có cấu trúc. Thiết kế đúng nguyên nhân, bảo mật và kiểm thử giúp API ổn định mà không phụ thuộc chuỗi thông báo hoặc chi tiết exception nội bộ.




