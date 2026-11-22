# Schema validation, output filtering và error handling

Một API an toàn cần kiểm soát dữ liệu ở cả hai chiều. Khi request đi vào, server phải xác định payload có đúng contract, đúng kiểu, đúng giới hạn và phù hợp với nghiệp vụ hay không. Trước khi response đi ra, server phải chỉ trả những field mà caller được phép biết. Nếu có lỗi, API cần phản hồi theo một error contract ổn định mà không làm lộ stack trace, câu SQL, secret, internal hostname hoặc sự tồn tại của resource mà caller không được biết.

Ba nhóm control này liên kết với nhau nhưng không thay thế nhau:

- **Schema validation** xác nhận cấu trúc và giới hạn dữ liệu đầu vào/đầu ra theo contract.
- **Output filtering** quyết định field và record nào được phép xuất hiện trong response theo principal, tenant và ngữ cảnh nghiệp vụ.
- **Error handling** biến lỗi thành response an toàn, nhất quán và có thể vận hành.

Trong kiến trúc tham chiếu API security, các control cần được áp dụng ở đúng ranh giới: gateway có thể kiểm tra protocol, body size và một phần schema; application xác thực và kiểm tra nghiệp vụ; service thực hiện object/property authorization; response mapper chỉ xuất DTO đã được cho phép; error handler chuẩn hóa lỗi ở biên HTTP.

## 1. Kiến trúc xử lý request và response

Một luồng tham chiếu có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A[Client request] --> B[Gateway: protocol, size, route limits]
    B --> C[Parse and schema validation]
    C --> D[Authentication]
    D --> E[Function authorization]
    E --> F[Business validation]
    F --> G[Scoped resource lookup]
    G --> H[Object/property authorization]
    H --> I[Business operation]
    I --> J[Output projection and filtering]
    J --> K[Response serialization]
    K --> L[Client response]
    C --> X[Central error mapping]
    D --> X
    E --> X
    F --> X
    G --> X
    H --> X
    I --> X
    J --> X
    X --> L
~~~

Thứ tự chi tiết có thể thay đổi theo framework và mục tiêu chống resource enumeration. Ví dụ, một số endpoint cần kiểm tra authentication trước khi đọc body lớn; một số endpoint cần scoped lookup để không xác nhận resource ngoài tenant. Nhưng mọi side effect phải xảy ra sau các kiểm tra bắt buộc, và mọi response thành công phải đi qua output contract.

| Thành phần | Trách nhiệm chính | Không nên giao phó hoàn toàn |
|---|---|---|
| API gateway | Giới hạn body/header, route/method, content type, coarse rate limit | Object authorization và business validation |
| Parser/schema validator | Kiểm tra syntax, type, required field, range và structure | Quyền sở hữu resource hoặc quyền của user |
| Authentication | Xác định principal/client/workload | Quyết định mọi field có thể đọc |
| Authorization | Kiểm tra function, object, property và tenant scope | Thay thế validation của dữ liệu |
| Domain/service layer | Kiểm tra invariant và state transition | Tin trực tiếp DTO chưa được kiểm tra |
| Output mapper | Chiếu dữ liệu thành response DTO được phép | Serialize trực tiếp entity/database row |
| Error handler | Chuẩn hóa status, error code và correlation ID | Trả exception nội bộ cho client |

## 2. Phân biệt schema validation và business validation

Schema validation kiểm tra request có đúng hình dạng mà API công bố hay không. Business validation kiểm tra dữ liệu đó có hợp lệ trong trạng thái hệ thống hiện tại hay không.

Ví dụ request tạo đơn:

~~~json
{
  "customerReference": "cus-1042",
  "items": [
    {
      "productId": "prd-7",
      "quantity": 2
    }
  ],
  "currency": "VND"
}
~~~

Schema validation có thể xác minh:

- customerReference là chuỗi có độ dài giới hạn.
- items là array và có ít nhất một phần tử.
- productId đúng format.
- quantity là integer trong khoảng cho phép.
- currency thuộc enum được hỗ trợ.
- Không có field vượt kích thước hoặc nesting limit.

Business validation cần xác minh:

- Customer thuộc tenant của principal hoặc principal có quan hệ hợp lệ.
- Product đang được phép bán và có thể đặt.
- Giá được lấy từ nguồn server tin cậy, không lấy giá client gửi.
- Số lượng không vượt tồn kho hoặc hạn mức.
- Tenant có được phép dùng currency này không.
- Trạng thái workflow hiện tại cho phép tạo đơn.

Schema hợp lệ không có nghĩa request được phép. Một payload có thể hoàn toàn đúng JSON Schema nhưng vẫn cố đổi tenant, thao túng giá hoặc thực hiện thao tác ngoài quyền.

### 2.1. Validation không phải authorization

Không dùng các quy tắc như “tenantId phải là UUID hợp lệ” để thay cho việc xác minh caller có quyền với tenant đó. Format đúng chỉ chứng minh giá trị đúng cú pháp.

Tương tự, một role field có thể đúng enum nhưng client không được quyền tự đặt role. Không bind trực tiếp các field hệ thống như tenantId, ownerId, role, status, approvedBy hoặc internalFlags từ request DTO vào entity.

## 3. Xây dựng API schema contract

Schema là hợp đồng giữa client, gateway và backend. Có thể mô tả bằng OpenAPI/JSON Schema, protobuf hoặc contract tương ứng với giao thức. Contract cần được version hóa và kiểm tra trong CI để tránh client và server diễn giải payload khác nhau.

Một schema request minh họa:

~~~yaml
type: object
additionalProperties: false
required:
  - customerReference
  - items
  - currency
properties:
  customerReference:
    type: string
    minLength: 1
    maxLength: 80
  items:
    type: array
    minItems: 1
    maxItems: 50
    items:
      type: object
      additionalProperties: false
      required: [productId, quantity]
      properties:
        productId:
          type: string
          pattern: '^[A-Za-z0-9_-]{1,64}$'
        quantity:
          type: integer
          minimum: 1
          maximum: 100
  currency:
    type: string
    enum: [VND, USD]
~~~

Đây là ví dụ contract; cú pháp cụ thể cần phù hợp với JSON Schema/OpenAPI version mà dự án sử dụng.

### 3.1. Unknown field và forward compatibility

Với endpoint nhạy cảm, từ chối unknown field thường giúp phát hiện client gửi nhầm dữ liệu và giảm nguy cơ mass assignment. Tuy nhiên, chính sách phải được xác định rõ theo version:

- Request schema có thể đặt additional properties là false cho contract chặt.
- Nếu cần forward compatibility, chỉ cho phép extension field có namespace và quy tắc rõ ràng.
- Không âm thầm bind field lạ vào entity.
- Unknown field không được làm thay đổi permission, tenant, owner hoặc state.
- Version mới cần được rollout theo contract và migration plan.

Không bật chế độ “ignore mọi field lạ” rồi giả định dữ liệu an toàn. Cũng không thay đổi ý nghĩa field cũ giữa các version mà không có contract rõ.

### 3.2. Giới hạn cấu trúc và tài nguyên

Schema cần có giới hạn rõ cho:

- Body size trước khi parse.
- Độ dài string và số lượng property.
- Số phần tử array và độ sâu object.
- Số query parameter và độ dài header.
- Pagination size, batch size và số filter.
- Regex/pattern có thể gây ReDoS.
- Multipart part count, file size và decompressed size.

Giới hạn cần được thực thi ở cả gateway và application phù hợp. Đừng chỉ dựa vào schema validator sau khi toàn bộ body lớn đã được đọc vào memory.

### 3.3. Duplicate key và parser differential

Một số JSON parser xử lý duplicate key bằng cách lấy giá trị đầu tiên, một số lấy giá trị cuối cùng. Nếu gateway, validator và object mapper không thống nhất, cùng một request có thể được kiểm tra theo một giá trị nhưng thực thi theo giá trị khác.

Ví dụ:

~~~json
{
  "tenantId": "tenant-A",
  "tenantId": "tenant-B"
}
~~~

Với field nhạy cảm hoặc input nhập nhằng, nên từ chối duplicate key hoặc chuẩn hóa đúng một lần ở ranh giới tin cậy. Kiểm tra cùng một payload qua gateway và backend để phát hiện khác biệt decode, Unicode normalization, query parameter và header parsing.

## 4. Validation theo từng lớp

Không nên gom mọi validation vào một annotation ở controller. Mỗi lớp kiểm tra điều nó có đủ ngữ cảnh để xác minh.

| Lớp | Kiểm tra | Ví dụ |
|---|---|---|
| Edge/protocol | Method, content type, body/header size, encoding | Từ chối body vượt 1 MB |
| Syntax/parser | JSON/XML/protobuf parse | Từ chối JSON malformed |
| Schema/DTO | Required, type, format, range, enum | quantity từ 1 tới 100 |
| Authentication | Token/session/workload credential | issuer, audience, signature, expiry |
| Function authorization | Quyền gọi hành động | orders:create |
| Resource lookup | Phạm vi tenant/owner | Tìm order trong tenant hiện tại |
| Object/property authorization | Quan hệ và field được truy cập | Chỉ owner hoặc support role được xem |
| Domain/business | Invariant và state transition | Không hủy đơn đã giao |
| Persistence boundary | Constraint và transaction | Unique key, foreign key, row-level security |

### 4.1. Fail closed khi validation không chắc chắn

Nếu parser không hiểu payload, schema version không hỗ trợ hoặc validation service quan trọng không sẵn sàng, không tự động chấp nhận request. Hãy trả lỗi theo contract và không thực hiện side effect.

Với dependency dùng để xác minh quyền hoặc tính hợp lệ bảo mật, không dùng fallback “allow” khi dependency timeout. Fallback cần được thiết kế theo threat model và không được làm yếu authorization.

### 4.2. Không tin dữ liệu đã được frontend kiểm tra

Client-side validation chỉ cải thiện trải nghiệm. Attacker có thể gửi HTTP trực tiếp hoặc sửa request. Server luôn phải parse, validate và authorize độc lập.

## 5. Ví dụ validation trong Spring Boot

Với Spring Boot 3, Bean Validation dùng namespace jakarta.validation. DTO nên chỉ chứa field client được phép gửi; field server-managed được tạo từ principal hoặc domain state.

~~~java
public record CreateOrderRequest(
    @NotBlank
    @Size(max = 80)
    String customerReference,

    @NotEmpty
    @Size(max = 50)
    List<@Valid CreateOrderItemRequest> items,

    @NotNull
    CurrencyCode currency
) {}

public record CreateOrderItemRequest(
    @NotBlank
    @Pattern(regexp = "^[A-Za-z0-9_-]{1,64}$")
    String productId,

    @NotNull
    @Min(1)
    @Max(100)
    Integer quantity
) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderApplicationService orderService;

    public OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal ApiPrincipal principal) {

        OrderResponse response = orderService.create(request, principal);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

Service vẫn phải kiểm tra quyền và nghiệp vụ:

~~~java
@Transactional
public OrderResponse create(
        CreateOrderRequest request,
        ApiPrincipal principal) {

    TenantId tenantId = principal.requireTenantId();
    authorization.require(principal, "orders:create", tenantId);

    Customer customer = customerRepository
            .findByReferenceAndTenantId(request.customerReference(), tenantId)
            .orElseThrow(ResourceNotFoundException::new);

    List<ValidatedOrderItem> items =
            productPolicy.validatePurchasableItems(request.items(), tenantId);

    Order order = orderFactory.create(
            tenantId,
            customer,
            items,
            request.currency());

    return orderMapper.toResponse(order, principal);
}
~~~

Đoạn code là mẫu kiến trúc. Các kiểu ApiPrincipal, TenantId, authorization và mapper cần được triển khai theo ứng dụng. Không lấy tenant từ request body và không tin tổng tiền do client gửi.

## 6. Output filtering: chỉ trả dữ liệu được phép

Output filtering quyết định response được phép chứa những field và record nào. Đây là control độc lập với input validation.

Một entity có thể chứa:

~~~java
class UserEntity {
    UUID id;
    String email;
    String displayName;
    String passwordHash;
    String mfaSecret;
    String recoveryCodeHash;
    String internalRiskScore;
    UUID tenantId;
    boolean locked;
}
~~~

Nếu controller serialize entity trực tiếp, field mới được thêm trong tương lai có thể vô tình xuất hiện trong API response. Hãy dùng response DTO allowlist chỉ chứa field được phép công bố.

~~~java
public record UserProfileResponse(
    UUID id,
    String displayName,
    String maskedEmail
) {}
~~~

DTO allowlist giảm nguy cơ overexposure nhưng vẫn cần authorization. Một user có thể được phép xem profile cơ bản nhưng không được xem email đầy đủ; support role có thể có quyền khác; tenant admin chỉ được xem user trong tenant của họ.

### 6.1. Output filtering theo principal và property

Có thể chia response theo use case:

| Caller/context | Field được phép |
|---|---|
| User xem profile của mình | displayName, email đã xác minh theo policy, preferences |
| User xem profile người khác | displayName và thông tin công khai |
| Tenant admin | Field quản trị trong tenant, không có secret authentication |
| Support operator | Field hỗ trợ cần thiết, có audit và masking |
| Public client | Chỉ field public được công bố |

Không trả password hash, MFA seed, recovery code, API secret, signing key hoặc internal risk flag trong DTO công khai.

### 6.2. Field-level authorization

Một số field chỉ được trả nếu caller có permission cụ thể. Có thể tạo projection khác nhau hoặc mapper có policy rõ ràng. Tránh dùng reflection để serialize mọi field rồi cố gắng xóa một số field nhạy cảm ở cuối.

~~~java
public UserAdminResponse toAdminResponse(UserEntity user, ApiPrincipal actor) {
    authorization.requireCanViewUserAdminFields(actor, user);

    return new UserAdminResponse(
            user.id(),
            user.displayName(),
            user.email(),
            user.locked());
}
~~~

Nếu caller không có quyền xem email, lựa chọn an toàn là dùng DTO khác hoặc masked value theo contract. Không đưa field vào response rồi hy vọng frontend ẩn nó.

### 6.3. Collection và pagination

Output filtering phải diễn ra trước khi tính total, facet, aggregate hoặc pagination metadata. Nếu database đếm toàn bộ resource rồi chỉ lọc các item trả về, total có thể tiết lộ số lượng dữ liệu ngoài tenant.

Tương tự, export/report/search phải áp dụng cùng tenant và object policy. Không coi endpoint export là đường phụ ít quan trọng hơn endpoint đọc từng resource.

## 7. Error handling là một phần của security boundary

Error response cần đủ thông tin để client xử lý và hỗ trợ người dùng, nhưng không được tiết lộ implementation detail.

Không trả trực tiếp:

- Stack trace, class name hoặc package nội bộ.
- SQL query, table/column name hoặc database error detail.
- Internal hostname, IP, port, filesystem path hoặc cloud resource ID.
- Access token, API key, cookie, secret hoặc request signing material.
- Nội dung request/response nhạy cảm.
- Chi tiết resource hoặc tenant mà caller không được biết.
- Exception message từ dependency nếu nó chứa URL, header hoặc credential.

Thay vào đó, trả error code ổn định, thông điệp tổng quát, status phù hợp và correlation ID để hỗ trợ điều tra.

## 8. Chuẩn hóa error response bằng Problem Details

RFC 9457 định nghĩa Problem Details cho HTTP API. Một response có thể dùng media type application/problem+json:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Invalid request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "correlationId": "req-7f3a",
  "invalidParams": [
    {
      "name": "items[0].quantity",
      "reason": "must be greater than or equal to 1"
    }
  ]
}
~~~

Extension field như code, correlationId và invalidParams cần được định nghĩa trong API contract. Không đưa rejected value hoặc dữ liệu nhạy cảm vào invalidParams. Với endpoint cần che giấu resource existence, không để error code hoặc detail phân biệt “resource tồn tại nhưng bị cấm” với “resource không tồn tại”.

### 8.1. Status code theo loại lỗi

| HTTP status | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| 400 | Request syntax/parameter không hợp lệ | JSON malformed, query sai format |
| 401 | Thiếu hoặc credential không hợp lệ | Token hết hạn hoặc signature sai |
| 403 | Đã xác thực nhưng thiếu quyền chức năng | Thiếu orders:cancel |
| 404 | Resource không tồn tại hoặc được conceal theo policy | Resource ngoài tenant khi cần che existence |
| 405 | Method không được hỗ trợ | Endpoint không có DELETE |
| 409 | Xung đột trạng thái hoặc idempotency | Đơn đã được xử lý |
| 413 | Payload quá lớn | Body vượt giới hạn |
| 415 | Media type không hỗ trợ | Content-Type không được chấp nhận |
| 422 | Cú pháp hợp lệ nhưng nội dung không thể xử lý theo contract | Field combination không hợp lệ theo semantics |
| 429 | Caller vượt rate limit | Quota theo user/tenant |
| 500 | Lỗi nội bộ không dự kiến | Bug hoặc invariant violation |
| 502 | Gateway nhận response không hợp lệ từ upstream | Upstream protocol error |
| 503 | Service tạm thời không khả dụng | Circuit breaker open hoặc capacity exhausted |
| 504 | Timeout khi chờ upstream | Dependency vượt timeout budget |

Status cụ thể phải theo hợp đồng API và semantics của framework. Không dùng 500 cho mọi lỗi validation; không trả 200 kèm một error object nếu API contract không quy định như vậy.

### 8.2. 403 và 404 trong object authorization

Có thể dùng 403 cho thiếu permission chức năng ở endpoint, nhưng dùng 404 để che resource ngoài phạm vi được biết. Nếu chọn concealment, response của resource không tồn tại và resource bị che phải tương đương ở status, body, header và hành vi cache theo threat model.

Không thực hiện side effect rồi mới trả 404. Scoped lookup và object authorization phải diễn ra trước khi đọc/ghi dữ liệu nhạy cảm.

## 9. Centralized error mapping trong Spring Boot

Spring Boot 3 hỗ trợ ProblemDetail và @RestControllerAdvice. Có thể ánh xạ exception đã phân loại vào một contract chung.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(
            MethodArgumentNotValidException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setType(URI.create(
                "https://api.example.test/problems/validation-failed"));
        problem.setTitle("Invalid request");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty(
                "invalidParams",
                ex.getBindingResult().getFieldErrors().stream()
                        .limit(20)
                        .map(error -> Map.of(
                                "name", safeFieldName(error.getField()),
                                "reason", safeValidationCode(error)))
                        .toList());

        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound() {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Resource not found");
        problem.setProperty("code", "RESOURCE_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception exception) {
        String correlationId = RequestCorrelation.currentId();

        log.error("Unhandled API failure, correlationId={}", correlationId,
                exception);

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("An unexpected error occurred");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("correlationId", correlationId);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }

    private String safeFieldName(String field) {
        if (field == null || field.length() > 100) return "unknown";
        return field.replaceAll("[^A-Za-z0-9_.\\[\\]-]", "_");
    }

    private String safeValidationCode(FieldError error) {
        return switch (error.getCode() == null ? "" : error.getCode()) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED_VALUE";
            case "Size" -> "INVALID_LENGTH";
            case "Min", "Max", "DecimalMin", "DecimalMax" -> "OUT_OF_RANGE";
            case "Pattern" -> "INVALID_FORMAT";
            default -> "INVALID_VALUE";
        };
    }
}
~~~

Ví dụ cần được điều chỉnh theo exception taxonomy của ứng dụng. Không log exception chứa credential hoặc payload nhạy cảm nếu logging pipeline chưa có redaction. Với production, cần có handler riêng cho authentication, access denied, rate limit, dependency timeout và domain conflict.

### 9.1. Không để exception handler nuốt lỗi bảo mật

Một handler tổng quát có thể vô tình biến lỗi authorization thành 500 hoặc trả 200. Định nghĩa thứ tự handler rõ ràng và test các exception quan trọng. Không bắt mọi exception rồi trả response thành công hoặc fallback mặc định.

## 10. Logging và correlation cho lỗi

Error response công khai và log nội bộ có mức chi tiết khác nhau:

| Thông tin | Client response | Internal log/audit |
|---|---|---|
| Stable error code | Có | Có |
| HTTP status | Có | Có |
| Correlation ID | Có | Có |
| Stack trace | Không | Có kiểm soát, khi cần |
| SQL/internal host | Không | Chỉ khi cần và được bảo vệ |
| Principal/tenant reference | Hạn chế theo contract | Có thể pseudonymize |
| Secret/token | Không | Không ghi |
| Rejected value | Thường không | Không ghi nếu nhạy cảm |
| Authorization decision | Thông báo tổng quát | Audit event chi tiết theo policy |

Log cần dùng route template, method, policy version, principal/tenant reference đã xác minh và mã lỗi. Không ghi raw query string, Authorization header hoặc toàn bộ body. Correlation ID giúp tìm log nhưng không phải credential và không được dùng làm bằng chứng danh tính.

## 11. Reference pattern cho schema evolution

Schema thay đổi theo thời gian. Một thay đổi có thể tương thích hoặc breaking:

- Thêm optional field có thể tương thích nếu server/client xử lý unknown field đúng.
- Thêm required field thường có thể phá client cũ.
- Đổi type, enum semantics hoặc range có thể làm request cũ bị từ chối.
- Bỏ field hoặc thay ý nghĩa field có thể phá consumer.
- Siết validation có thể chặn payload trước đây được chấp nhận.

Quy trình an toàn:

1. Version hóa contract và schema.
2. Kiểm tra backward/forward compatibility theo vai trò producer/consumer.
3. Tạo test corpus từ request hợp lệ đã sanitize.
4. Chạy contract test giữa client, gateway và backend.
5. Rollout theo canary hoặc version route khi cần.
6. Theo dõi validation failure theo schema version.
7. Có kế hoạch deprecation và rollback.

Không nới schema vô hạn chỉ để tránh lỗi tương thích; điều đó có thể mở rộng attack surface. Unknown field và enum mới cần policy rõ ràng.

## 12. Kiểm thử schema validation, output filtering và error handling

Kiểm thử phải xác minh cả response lẫn trạng thái hệ thống sau request. Một request bị trả 400 nhưng đã ghi database hoặc phát event vẫn là lỗi nghiêm trọng.

| Nhóm test | Tình huống | Kết quả cần xác minh |
|---|---|---|
| Syntax | JSON malformed, encoding sai | Từ chối có kiểm soát, không crash |
| Schema | Thiếu field, sai type, enum lạ | Error code ổn định, không side effect |
| Boundary | Min/max, max+1, array/depth lớn | Giới hạn được thực thi trước khi cạn tài nguyên |
| Unknown field | Gửi tenantId, ownerId, role hoặc status | Không mass assignment |
| Authentication | Token thiếu, hết hạn, sai audience | 401 theo contract |
| Function authorization | Thiếu scope/action | 403 hoặc policy đã công bố |
| Object authorization | Resource ngoài tenant | Deny; concealment nhất quán nếu áp dụng |
| Property authorization | Gửi field không được sửa | Field không đổi và không lộ |
| Output filtering | Serialize entity có secret field | Secret/internal field không xuất hiện |
| Collection/export | Count, pagination, report đa tenant | Chỉ tính và trả dữ liệu caller được phép |
| Error mapping | Database/HTTP client exception | Không lộ stack, SQL, host hoặc credential |
| Error consistency | Resource nonexistent vs concealed | Response tương đương theo concealment policy |
| Dependency failure | Timeout, circuit open, malformed response | Error code/status phù hợp, không fail-open |
| Correlation | Nhiều service xử lý cùng request | Trace/log nối được nhưng không tin ID làm identity |
| Schema evolution | Client cũ gửi payload cũ | Compatibility/deprecation đúng contract |

### 12.1. Kiểm tra không có side effect khi request bị từ chối

Với endpoint ghi dữ liệu, test nên kiểm tra:

- Database row và transaction state.
- Outbox/event/message count.
- Downstream call count.
- Cache/idempotency record.
- Audit record và actor/resource scope.
- Secret hoặc field nhạy cảm trong response/log.

Không chỉ assert status code. Với authorization và validation failure, trạng thái hệ thống phải giữ đúng invariant.

### 12.2. Property-based và fuzz testing

Có thể sinh nhiều payload theo schema rồi mutate type, range, duplicate key, Unicode, nesting và unknown fields. Các property quan trọng:

- Input không hợp lệ không tạo side effect.
- Field hệ thống không thể bị mass assignment.
- Caller không đọc được field ngoài allowlist.
- Tenant A không đọc hoặc sửa resource tenant B.
- Error response không chứa secret/internal exception.
- Mọi response tuân theo schema output đã công bố.

Giữ seed gây lỗi và chuyển thành regression test. Chạy fuzzing trong môi trường cô lập với giới hạn CPU, memory và thời gian.

## 13. Quan sát và vận hành control

Theo dõi các tín hiệu:

- Validation failure rate theo route, schema version và client.
- Tỷ lệ unknown field/type mismatch hoặc payload vượt limit.
- Authorization deny theo route/action và tenant reference.
- Output filtering decision hoặc số field bị loại ở mức aggregate khi cần.
- Error response theo stable error code và status.
- Dependency error, timeout và circuit breaker state.
- Request bị từ chối nhưng có side effect (nếu phát hiện được qua reconciliation).
- Schema drift giữa gateway, OpenAPI và backend.

Metric label nên có cardinality giới hạn: route template, method, error code, schema version, dependency. Không dùng raw user ID, email, resource ID hoặc request ID làm label. Log chi tiết cần quyền truy cập và retention phù hợp.

## 14. Checklist kiến trúc tham chiếu

- [ ] Có schema contract versioned cho từng endpoint/method.
- [ ] Gateway giới hạn protocol, header và body trước khi parse sâu.
- [ ] Parser, gateway và backend diễn giải path/query/header/body nhất quán.
- [ ] Schema validation kiểm tra required, type, range, enum, length, depth và collection size.
- [ ] Unknown field và duplicate key có policy rõ; field hệ thống không bind trực tiếp từ client.
- [ ] Business validation kiểm tra trạng thái và dữ liệu authoritative ở server.
- [ ] Authentication và function/object/property authorization được thực hiện độc lập với validation.
- [ ] Tenant scope lấy từ principal/context đã xác minh, không lấy trực tiếp từ body.
- [ ] Mọi truy vấn và collection metadata đều giới hạn theo quyền/tenant.
- [ ] Response dùng DTO allowlist; không serialize entity/database row trực tiếp.
- [ ] Output filtering áp dụng cho field, collection, export và error path.
- [ ] Error contract ổn định, dùng Problem Details hoặc format đã công bố.
- [ ] Status code phân biệt validation, authentication, authorization, conflict, quota và dependency failure theo contract.
- [ ] Error response không lộ stack trace, SQL, internal host, secret hoặc resource existence ngoài policy.
- [ ] Concealment policy nhất quán giữa nonexistent và forbidden resource khi cần.
- [ ] Correlation ID nối được log/trace nhưng không được coi là credential.
- [ ] Schema evolution có compatibility test, rollout và deprecation plan.
- [ ] Có test xác minh response và side effect, không chỉ status code.
- [ ] Có fuzz/property tests cho payload, parser differential và output filtering.
- [ ] Logging/metrics không làm lộ dữ liệu nhạy cảm hoặc tạo cardinality không giới hạn.

## 15. Nguyên tắc thiết kế

Schema validation xác nhận payload đúng contract và nằm trong giới hạn; business validation xác nhận dữ liệu phù hợp với trạng thái nghiệp vụ; authorization quyết định caller được làm gì trên resource; output filtering quyết định dữ liệu nào được phép rời khỏi server; error handling cung cấp phản hồi ổn định mà không tiết lộ implementation detail.

Hãy dùng contract versioned, DTO allowlist, scoped resource lookup, centralized error mapping và test cả response lẫn side effect. Gateway và backend phải diễn giải request nhất quán; mọi đường success, error, collection và export đều phải tuân thủ cùng tenant/property policy. **Một API an toàn phải kiểm soát dữ liệu trước khi sử dụng, trước khi trả ra và cả khi có lỗi.**
