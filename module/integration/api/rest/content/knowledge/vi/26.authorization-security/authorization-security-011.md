# Kiểm soát dữ liệu trả về và thông báo lỗi để giảm rò rỉ

## 1. API có thể bảo vệ endpoint nhưng vẫn làm lộ dữ liệu

JWT hợp lệ và mã HTTP đúng chưa bảo đảm API an toàn. Nếu `GET /v1/orders/{id}` trả thông tin thanh toán, ghi chú nội bộ hoặc dữ liệu tenant khác, **response đã tự làm lộ bí mật**. Lỗi `404`/`409` chứa trạng thái order không được phép biết cũng nguy hiểm.

~~~http
GET /v1/orders/o-42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <redacted-token>
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id": "o-42",
  "status": "PAID",
  "total": 125000
}
~~~

Response cho **customer được phép xem**, không có `riskScore`, `paymentToken`, `internalNotes` hay field tenant khác; lỗi cũng không được tiết lộ thông tin đơn bị che giấu.

Bài thuộc chương **Phân quyền và an toàn** của **INTEGRATION_API_REST**, liên hệ resource URI, HTTP status, hợp đồng REST, cache/pagination, OpenAPI và Java/Spring. Trọng tâm là **giảm rò rỉ ở response thành công lẫn lỗi**.

Bạn sẽ thiết kế DTO tối thiểu, object/field authorization, Problem Details trung tính, cache/log an toàn và test cross-tenant.

## 2. Phân biệt ba câu hỏi bảo mật

| Câu hỏi | Nơi kiểm tra | Ví dụ |
|---|---|---|
| **Ai đang gọi?** (authentication) | Spring Security / IdP | JWT có issuer, audience, signature, expiry hợp lệ |
| **Được truy cập resource nào?** (object-level authorization) | Policy + service/repository scoped | Customer A chỉ thấy order thuộc tenant và scope của A |
| **Được nhìn thấy trường nào?** (field-level authorization + minimization) | Policy + DTO assembler | Customer thấy `status/total`, nhân viên fraud thấy thêm `riskScore` nếu có quyền |

`@PreAuthorize("isAuthenticated()")` không cho phép đọc order bất kỳ: `findById(id)` không scoped gây **BOLA/IDOR**; trả trường nội bộ của order được phép xem gây **BOPLA/excessive data exposure**.

### 2.1. Ma trận quyền theo resource và trường

Ví dụ một hệ bán hàng nhiều tenant:

| Người gọi | Order thuộc scope | `id/status/total` | `shippingAddress` | `riskScore/internalNotes` |
|---|---|---|---|---|
| Customer A | Của A | Cho phép | Cho phép theo mục đích | Không |
| Customer A | Của B | Không tiết lộ | Không | Không |
| Support tenant A | Được phân công | Cho phép | Chỉ theo nghiệp vụ, audit | Không mặc định |
| Fraud analyst tenant A | Được phân công + quyền riêng | Cho phép | Chỉ khi cần | Theo policy cụ thể |
| Caller không xác thực | Bất kỳ | Không | Không | Không |

Role `SUPPORT` không thay tenant/assignment/field policy. Quyền dựa trên **principal xác thực**, không dựa `X-Tenant-Id` hay `customerId` do client khai.

### 2.2. Tách ranh giới công khai và nội bộ

Dùng `CustomerOrderView`, `SupportOrderView`, `FraudOrderView` hoặc field policy rõ. **Projection cố định** tránh field DB mới tự xuất trên public API.

Email, địa chỉ, KYC, risk flags, ID nội bộ và quan hệ khách hàng đều có thể là dữ liệu nhạy cảm, kể cả khi xuất gián tiếp qua `Link`/URL lỗi.

## 3. Thiết kế response tối thiểu theo mục đích

### 3.1. Tránh trả JPA entity trực tiếp

~~~java
// PHẢN MẪU: @Entity có thể thêm field mới không dành cho public API.
@GetMapping("/v1/orders/{id}")
OrderEntity get(@PathVariable UUID id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

Entity có thể mang `paymentToken`, `internalNotes` và quan hệ lazy; Jackson serialize getter làm **public contract tự đổi theo entity**. `@JsonIgnore` là blacklist dễ sót; dùng DTO.

Thiết kế tốt hơn:

~~~java
public record CustomerOrderView(
    UUID id,
    String status,
    long totalMinorUnits,
    String currency
) {}

static CustomerOrderView toCustomerView(OrderEntity order) {
    return new CustomerOrderView(
        order.getId(),
        order.getStatus().name(),
        order.getTotalMinorUnits(),
        order.getCurrency());
}
~~~

Mô tả rõ minor units/decimal thay vì `double`; không xuất `entity.toString()`. DTO chặn field entity mới xuất ngoài hợp đồng.

### 3.2. Đừng nhầm ẩn trong OpenAPI với bảo vệ runtime

`@Schema(hidden=true)`/`@Hidden` chỉ ẩn **OpenAPI**, không chặn runtime. `@JsonIgnore` chỉ ảnh hưởng serialization, không ngăn đọc order user khác nếu query không scoped.

### 3.3. Có thể trả null hay cần bỏ field?

`email=null` khác field vắng mặt: mô tả optional/nullable rõ. `"restricted":true` cũng có thể tiết lộ có dữ liệu bị ẩn.

Không gửi object đầy đủ rồi ẩn bằng frontend: dữ liệu đã qua mạng. **Giảm response tại server**.

### 3.4. Quan hệ, URL và dữ liệu gián tiếp

Một response có thể chỉ chứa `downloadUrl`, nhưng URL đó là **bearer credential dạng signed URL**. Đặt TTL ngắn, scope đúng object/method, không in URL vào log và bảo đảm user có quyền tại thời điểm phát hành. Nếu `items[]` chứa `supplierId` hoặc `warehouseCode` không công bố, đó cũng là rò rỉ dù field nhạy cảm không nằm ở root.

## 4. Authorization phải xảy ra trước khi trả dữ liệu hoặc lỗi nghiệp vụ

Một cách kiểm tra nguy hiểm:

~~~java
OrderEntity order = repository.findById(id).orElseThrow(NotFound::new);
if (order.getStatus() == PAID) {
    throw new OrderAlreadyPaidException();
}
if (!order.getTenantId().equals(actor.tenantId())) {
    throw new ForbiddenException();
}
~~~

Kiểm tra trạng thái trước quyền khiến tenant khác biết order **có tồn tại và đã thanh toán**. Trước tiên phải truy vấn trong **scope xác thực**.

### 4.1. Truy vấn theo tenant và subject

~~~sql
SELECT id, status, total_minor_units, currency
FROM orders
WHERE id = :orderId
  AND tenant_id = :trustedTenantId
  AND customer_id = :trustedCustomerId;
~~~

`trustedTenantId`/`trustedCustomerId` đến từ principal/policy; order ngoài scope trả **0 hàng**. Với staff, dùng predicate assignment/role và vẫn giới hạn tenant khi hệ thống đa tenant.

~~~java
public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    Optional<OrderEntity> findByIdAndTenantIdAndCustomerId(
        UUID id, UUID tenantId, UUID customerId);
}

@Service
public class CustomerOrderService {
    private final OrderRepository repository;

    CustomerOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public CustomerOrderView getVisible(Actor actor, UUID id) {
        OrderEntity order = repository
            .findByIdAndTenantIdAndCustomerId(
                id, actor.tenantId(), actor.customerId())
            .orElseThrow(ResourceNotVisibleException::new);
        return new CustomerOrderView(
            order.getId(), order.getStatus().name(),
            order.getTotalMinorUnits(), order.getCurrency());
    }
}
~~~

`Actor`/`ResourceNotVisibleException` là kiểu ứng dụng; actor đến từ principal tin cậy. Policy phức tạp cần thành phần authorization dùng chung, áp cả **export/bulk/async**.

### 4.2. Field-level permission được thực thi trên response

~~~java
record SupportOrderView(
    UUID id,
    String status,
    String maskedPhone,
    String riskFlag
) {}

SupportOrderView toSupportView(OrderEntity order, Actor actor) {
    var phone = actor.hasPermission("orders.contact.read")
        ? maskPhone(order.getCustomerPhone())
        : null;
    var flag = actor.hasPermission("orders.fraud.read")
        ? order.getRiskFlag()
        : null;
    return new SupportOrderView(
        order.getId(), order.getStatus().name(), phone, flag);
}
~~~

Nếu **null** không đúng contract, dùng DTO khác/field omission. `maskPhone` không đồng nghĩa ẩn danh; `includeSensitive=true` không cấp quyền. Ưu tiên DB projection khi tránh được load entity nhạy cảm.

### 4.3. Trạng thái thay đổi giữa kiểm tra và trả kết quả

Quyền/trạng thái có thể đổi sau khi đọc. **Lệnh ghi** phải xác minh policy/state/version tại điểm ghi bằng transaction/CAS; cache đọc không được tồn tại quá policy. Worker không xử lý ID trần thiếu scope.

## 5. 401, 403 hay 404: không vô tình tạo công cụ dò resource

| Tình huống | HTTP status thường phù hợp | Điều không được tiết lộ |
|---|---|---|
| Không có credential hoặc token không hợp lệ | **401 Unauthorized**; `WWW-Authenticate` phù hợp | Token raw, rule xác minh chi tiết, user data |
| Có credential hợp lệ nhưng thiếu quyền thao tác **trên resource caller được biết** | **403 Forbidden** | Danh sách role nội bộ, dữ liệu private |
| Resource không tồn tại **hoặc không được phép tiết lộ sự tồn tại** | **404 Not Found** trung tính | Phân biệt “không có” với “có nhưng thuộc tenant khác” |
| Resource caller được phép thấy, nhưng đã đóng | **409 Conflict** | Chỉ tiết lộ trạng thái trong phạm vi đã được phép |
| ETag client gửi không còn khớp | **412 Precondition Failed** | Không phản chiếu nội dung/version nhạy cảm ngoài phạm vi quyền |
| Gửi request quá hạn mức | **429 Too Many Requests** | Quota/tenant nội bộ không liên quan, token |
| Lỗi hạ tầng | **500/503** | SQL, DSN, stack trace, private IP, secrets |

**Không phải mọi thiếu quyền đều là 404**: biết resource nhưng không được sửa có thể dùng 403; resource không được nhìn thấy dùng 404 trung tính theo policy.

### 5.1. Cùng một response cho “không tồn tại” và “ngoài scope”

~~~http
GET /v1/orders/o-foreign HTTP/1.1
Authorization: Bearer <redacted-token>

HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/resource-not-visible",
  "title": "Resource not found",
  "status": 404,
  "code": "RESOURCE_NOT_FOUND"
}
~~~

Không trả `ownerId`/`status` hay thông báo tenant khác. Hai trường hợp phải có `type/code`, header và kích thước tương đồng; timing tuyệt đối không bảo đảm, cần rate limiting/detection.

### 5.2. Đừng trả lỗi domain trước khi xác minh visibility

Nếu ID của tenant A trả `409 ORDER_ALREADY_PAID` nhưng ID giả trả `404 RESOURCE_NOT_FOUND`, caller B có thể dò order A. Cần **kiểm tra visibility trước**, chỉ sau đó mới xét conflict 409.

### 5.3. Không mặc định HTTP status đủ chống enumeration

Enumeration có thể dựa vào latency, kích thước, ETag, redirect hay `Retry-After`. Kết hợp ID khó đoán, scoped query, rate limiting, audit và response nhất quán. **UUID không thay authorization**.

## 6. Problem Details: thông báo đủ sửa lỗi, không đủ dò hệ thống

RFC 9457 định nghĩa định dạng **Problem Details** với media type `application/problem+json`. Các trường chuẩn là `type`, `title`, `status`, `detail`, `instance`; ứng dụng có thể bổ sung extension như `code`, `invalidParams`. **HTTP status line vẫn là trạng thái giao thức**, không được thay bằng trường `status` trong JSON.

### 6.1. Thiết kế public error taxonomy

| Loại lỗi | Response công khai | Thông tin chỉ ghi ở log/audit nội bộ |
|---|---|---|
| Input sai kiểu/cú pháp | `400`, `INVALID_REQUEST` hoặc field code an toàn | Stack trace, raw malformed payload nếu được phép lưu |
| Vi phạm Bean Validation | `400`/`422` theo contract, tên **field public**, constraint an toàn | Nguồn rule, internal DTO class |
| Không có/không thấy resource | `404`, `RESOURCE_NOT_FOUND` | Phân biệt missing vs outside tenant, actor/policy decision |
| Thiếu quyền thao tác đã được phép biết | `403`, `FORBIDDEN` | Policy ID, quyền nội bộ thiếu, sự kiện audit |
| State conflict được phép thấy | `409`, code domain ổn định | Internal workflow, entity version chi tiết |
| SQL constraint/DB outage | `409` **chỉ nếu** là business conflict được xác định; ngược lại 5xx phù hợp | SQL, table/constraint, host, stack trace |
| Downstream timeout/circuit open | `502/503/504` theo nơi phát sinh/lớp proxy và contract | URI private, token đối tác, circuit trạng thái |

Ví dụ body lỗi 500 tối thiểu:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-71f

{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal Server Error",
  "status": 500,
  "code": "INTERNAL_ERROR",
  "requestId": "req-71f"
}
~~~

Không trả `SQLException: duplicate key on orders(tenant_id, customer_email)`, `java.lang.NullPointerException at PaymentService.java:213`, host/port DB, stack trace hoặc full HTTP headers. `requestId` có thể giúp hỗ trợ tra log, nhưng nên do **server phát và giới hạn ký tự**; không coi `X-Request-Id` client gửi là danh tính đáng tin.

### 6.2. Validation lỗi có thể chứa dữ liệu nhạy cảm

Sai:

~~~json
{
  "detail": "Giá trị 4111-1111-1111-1111 của creditCard không hợp lệ",
  "rejectedValue": "4111-1111-1111-1111",
  "constraint": "com.example.internal.PaymentRule",
  "trace": "..."
}
~~~

Tốt hơn:

~~~json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "invalidParams": [
    {"name": "paymentMethod", "code": "INVALID_FORMAT"}
  ]
}
~~~

`invalidParams` **không phải trường bắt buộc của RFC 9457**, mà là extension do API quy định. Tên field chỉ lấy từ **public DTO schema**, không chèn `rejectedValue`, số tài khoản, token, email chưa mask hay class name. Khi client gửi field không được phép thay đổi như `isAdmin`, có thể trả lỗi input chung thay vì liệt kê field nội bộ được framework biết.

### 6.3. Không nuốt lỗi để “an toàn” bằng cách trả thành công

Che stack trace không có nghĩa chuyển mọi exception thành `200 {"success":false}` hoặc `404`. Khi DB hỏng, phải giữ 5xx và báo cho giám sát; khi caller không có quyền, phải giữ 401/403/404 theo policy. Trả 200 cho lỗi phá semantics, làm cache/retry/monitoring sai. **Chi tiết để debug thuộc log kiểm soát quyền**, không thuộc response công khai.

## 7. Spring Boot: một pipeline từ principal đến response an toàn

### 7.1. Controller chỉ nhận identity đã xác thực

~~~java
@RestController
@RequestMapping("/v1/orders")
class CustomerOrdersController {
    private final CustomerOrderService service;
    private final ActorFactory actorFactory;

    CustomerOrdersController(CustomerOrderService service,
                             ActorFactory actorFactory) {
        this.service = service;
        this.actorFactory = actorFactory;
    }

    @GetMapping("/{id}")
    ResponseEntity<CustomerOrderView> get(
            @PathVariable("id") UUID id,
            @AuthenticationPrincipal Jwt jwt) {
        Actor actor = actorFactory.fromVerifiedJwt(jwt);
        CustomerOrderView view = service.getVisible(actor, id);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(view);
    }
}
~~~

Ví dụ dùng Java 17+, Spring Boot 3/Spring Security, `CustomerOrderService`, `ActorFactory` và DTO đã nêu. `ActorFactory` không phải API Spring có sẵn: nó cần kiểm tra mapping giữa principal, tenant và customer từ nguồn đáng tin; **không tự gán tenant theo path ID**. JWT cần được Resource Server xác minh chữ ký, issuer, audience, expiry và scope. Nếu dùng session/cookie, principal phải đến từ security context tương đương và cần CSRF protection cho lệnh ghi.

### 7.2. Cấu hình HTTP authorization ở cổng vào

~~~java
@Configuration
class OrderSecurityConfig {
    @Bean
    SecurityFilterChain orders(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Lớp này bảo vệ **route/method** và yêu cầu scope, nhưng **không biết `o-42` thuộc ai**. Policy theo resource vẫn bắt buộc ở service; nếu chỉ kiểm scope `orders.read` rồi truy vấn bằng ID không scoped, user cùng scope có thể xem đơn của nhau. Với endpoint POST/PATCH/DELETE cần policy riêng và kiểm tra ngay tại điểm ghi.

### 7.3. @RestControllerAdvice cho lỗi đã qua service

~~~java
@RestControllerAdvice
class ApiErrorAdvice {
    @ExceptionHandler(ResourceNotVisibleException.class)
    ResponseEntity<ProblemDetail> invisible() {
        ProblemDetail p = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        p.setTitle("Resource not found");
        p.setType(URI.create(
            "https://api.example.com/problems/resource-not-visible"));
        p.setProperty("code", "RESOURCE_NOT_FOUND");
        return ResponseEntity.status(404)
            .contentType(MediaType.parseMediaType("application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(p);
    }

    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> conflict(OrderStateConflictException ex) {
        ProblemDetail p = ProblemDetail.forStatus(HttpStatus.CONFLICT);
        p.setTitle("Order cannot be changed in its current state");
        p.setProperty("code", "ORDER_STATE_CONFLICT");
        return ResponseEntity.status(409)
            .contentType(MediaType.parseMediaType("application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Không trả `ex.getMessage()` nguyên văn: service exception có thể chứa tên tenant, SQL, trạng thái hoặc giá trị người dùng. `ResourceNotVisibleException` nên thống nhất cả **không có bản ghi** và **ngoài visibility scope**. Chỉ phát `OrderStateConflictException` sau khi đã xác nhận caller có quyền biết order và trạng thái.

**Quan trọng:** lỗi 401/403 do `SecurityFilterChain` phát sinh có thể được xử lý **trước MVC**, nên `@RestControllerAdvice` không bảo đảm format chung. Nếu sản phẩm yêu cầu Problem Details cho auth error, cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` riêng để ghi response an toàn. Với bearer token, giữ `WWW-Authenticate` đúng giao thức; không phản chiếu token hoặc chi tiết chữ ký/JWT validation.

### 7.4. Lỗi không mong đợi và quy tắc “fail closed”

Lỗi policy service, lookup principal hoặc tenant mapping không nên khiến API bỏ qua filter rồi trả dữ liệu “để người dùng tiếp tục”. Nếu không xác định được quyền, **từ chối cấp dữ liệu** và ghi audit phù hợp. Nhưng không bắt mọi `RuntimeException` rồi trả `403`/`404`: điều đó che lỗi hệ thống và làm sai vận hành. Dùng handler cho lỗi biết trước; lỗi chưa biết để pipeline trả 5xx công khai tối thiểu, có correlation ID và monitoring.

## 8. Cache, collection và metadata cũng có thể tiết lộ dữ liệu

### 8.1. Response cá nhân không được cache dùng chung ngoài ý muốn

~~~http
GET /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <redacted-token>

HTTP/1.1 200 OK
Cache-Control: private, no-store
Content-Type: application/json

{"id":"o-42","status":"PAID"}
~~~

Với dữ liệu nhạy cảm, `Cache-Control: no-store` là lựa chọn đơn giản; `private` chỉ nói response dành cho cache riêng, còn `no-store` yêu cầu không lưu. **Không mặc định rằng mọi endpoint có Authorization đều được cache public/CDN an toàn**. Nếu có caching theo hợp đồng, phải đưa identity/tenant và các biến thể `Vary` thích hợp vào cache key, kiểm soát TTL/invalidation và kiểm thử khi user đổi quyền.

`ETag`/`304` có thể lộ resource ngoài scope. **Kiểm visibility trước khi đánh giá precondition**; ETag của representation customer có thể khác support vì field khác nhau.

### 8.2. Phân trang phải lọc trước khi đếm

~~~text
SAI:
SELECT COUNT(*) FROM orders;       -- đếm mọi tenant
SELECT ... WHERE tenant_id = A;    -- trả danh sách tenant A

ĐÚNG:
SELECT COUNT(*) FROM orders WHERE tenant_id = A AND visibility_policy(...);
SELECT ... FROM orders WHERE tenant_id = A AND visibility_policy(...);
~~~

`totalElements` toàn hệ thống có thể tiết lộ quy mô tenant khác. **Filter/sort/count/cursor/links/aggregate phải cùng scope**; cursor opaque gắn tenant/filter/sort được xác minh khi dùng.

**Lọc tại query**, không lấy tất cả rồi `stream().filter(...)` khiến phân trang/đếm sai. Có thể dùng cursor + `hasNext` thay total count nếu contract không công bố tổng.

### 8.3. Kênh phụ: HEAD, Link, search suggestion và error list

Một endpoint `HEAD` không có body nhưng có thể lộ `Content-Length`, `ETag`, `Last-Modified`. Header `Link` có thể lộ URI của resource khác; search autocomplete có thể tiết lộ email/ID; validation “đã có email này” có thể giúp dò tài khoản. Cùng visibility policy cần áp trên **GET, HEAD, export, search, hypermedia, download và event stream**; không chỉ trên một controller GET JSON.

## 9. Log, audit, tác vụ nền và downstream

Không chuyển dữ liệu cấm trả client thành log tự do. Audit “denied by tenant policy” phải nằm trong kho hạn chế; không log `internalNotes`, JWT, raw body hay SQL nhạy cảm.

~~~text
Public response:
  404 RESOURCE_NOT_FOUND, requestId=req-a31

Security audit (quyền truy cập hạn chế):
  actorId=..., tenantId=..., operation=orders.read,
  decision=DENY, policyId=..., requestId=req-a31

Không ghi:
  Authorization token; full JWT claims; private order data;
  SQL query với PII; request body thô; secret/signed URL
~~~

Ứng dụng cần **allowlist** log field, giới hạn retention, kiểm soát quyền xem audit và tránh metric label có ID cá nhân/cardinality vô hạn. Khi nhận lỗi từ đối tác, **không trả nguyên downstream body**: nó có thể chứa service hostname, stack trace, credentials hoặc user data ngoài phạm vi. Chuyển thành lỗi public trung tính (ví dụ 502/503 tùy contract), giữ mã/trace nội bộ ở hệ quan sát được bảo vệ.

### 9.1. Export và asynchronous job phải giữ identity context

Nguy cơ thường gặp: API `POST /v1/exports` kiểm tra quyền tạo export, sau đó background worker dùng `SELECT * FROM orders` bằng service account và lưu file chứa dữ liệu mọi tenant. Quy trình an toàn cần ghi **job owner, tenant scope, policy constraints**, thực thi scoped query ở worker và **kiểm tra lại quyền lúc tải kết quả**.

~~~text
POST /v1/exports            -> 202 + Location: /v1/exports/e-7
GET  /v1/exports/e-7        -> metadata chỉ của owner/tenant
GET  /v1/exports/e-7/file   -> kiểm quyền lại, phát URL ngắn hạn nếu cần
~~~

Không nhét raw JWT vào message broker/job payload để “mang quyền đi khắp nơi”. Dùng identity/scope đã xác minh với cơ chế delegation/credential nội bộ được thiết kế rõ ràng; hạn chế privilege của worker, TTL file, audit download và khả năng revoke khi quyền user thay đổi.

## 10. Kiểm thử: phát hiện rò rỉ trong cả success lẫn error response

### 10.1. Ma trận HTTP/security contract

| Ca | Request / trạng thái | Assertion |
|---|---|---|
| D01 | Customer A GET đơn A | **200**, chỉ field public, không `riskScore/internalNotes` |
| D02 | Customer A GET đơn B | **404** trung tính, không có ID/status/tenant B |
| D03 | GET ID không tồn tại | Cùng **status/body/type/code/headers công khai** như D02 |
| D04 | GET thiếu bearer | **401**, challenge phù hợp; không phản chiếu token |
| D05 | Token hợp lệ nhưng thiếu `orders.read` | **403**, không có dữ liệu order |
| D06 | Customer A GET order A đã đóng | **200** với view cho phép; lệnh sửa có thể **409** |
| D07 | Customer B sửa order A đã đóng | **404** trung tính, **không 409** tiết lộ trạng thái |
| D08 | `GET /v1/orders` có filter/page | Chỉ order A, count/cursor/links cùng scope |
| D09 | `HEAD`/`If-None-Match` của order B | Không lộ ETag/Last-Modified/size của B |
| D10 | Binding/validation lỗi chứa card/token | Problem Details không chứa rejected value/stack trace |
| D11 | DB/downstream exception có SQL/host | 5xx public trung tính, chi tiết chỉ ở audit nội bộ |
| D12 | Export/file link do A tạo, B tải | **404/403** theo policy, không phát signed URL |
| D13 | Quyền A bị thu hồi sau khi cache/export tạo | Không còn trả representation/file trái policy |
| D14 | Response entity có field nội bộ mới | DTO/snapshot contract test phát hiện, không tự xuất field |

### 10.2. MockMvc kiểm tra public DTO và quyền

Ví dụ với **Spring Boot 3.5.x, Spring Security Test, JUnit 5, Mockito**; `Actor`/`ActorFactory` là thành phần ứng dụng:

~~~java
@WebMvcTest(CustomerOrdersController.class)
@Import({OrderSecurityConfig.class, ApiErrorAdvice.class})
class SafeOrderHttpTest {
    @Autowired MockMvc mvc;
    @MockitoBean CustomerOrderService service;
    @MockitoBean ActorFactory actors;
    @MockitoBean JwtDecoder jwtDecoder; // đáp ứng cấu hình resource server

    @Test
    void successfulResponseExposesOnlyPublicFields() throws Exception {
        UUID id = UUID.fromString(
            "a4912fc2-9a1f-46b5-9c82-25c44dbc0771");
        Actor actor = testActorForTenantA(); // fixture ứng dụng
        when(actors.fromVerifiedJwt(any(Jwt.class))).thenReturn(actor);
        when(service.getVisible(actor, id)).thenReturn(
            new CustomerOrderView(id, "PAID", 125000, "VND"));

        mvc.perform(get("/v1/orders/{id}", id)
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PAID"))
            .andExpect(jsonPath("$.riskScore").doesNotHaveJsonPath())
            .andExpect(jsonPath("$.internalNotes").doesNotHaveJsonPath())
            .andExpect(jsonPath("$.paymentToken").doesNotHaveJsonPath())
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")));
    }

    @Test
    void unauthenticatedCallerCannotReadAnOrder() throws Exception {
        mvc.perform(get("/v1/orders/{id}", UUID.randomUUID()))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(service);
    }
}
~~~

Cần import MockMvc, JUnit, Mockito, Spring Security Test và hamcrest theo project. `testActorForTenantA()` là fixture giả định; test phải có dữ liệu actor hợp lệ. `mockJwt()`/`jwt()` trong MockMvc là **test authentication post-processor**, không kiểm tra chữ ký JWT thực; tích hợp Resource Server cần test thêm issuer/audience/expiry trên security pipeline thật.

**Đừng chỉ mock service trả 404** rồi kết luận đã chặn BOLA. Dùng integration test service/repository với fixture gồm **hai tenant**, truy vấn bằng actor A và ID order B, xác minh không lấy được entity B, không tạo side effect, không xuất log chứa dữ liệu B. Với những operation ghi, chạy concurrency test trên DB để kiểm tra quyền/version tại điểm ghi.

### 10.3. Test riêng “không có” và “không nhìn thấy”

Tạo hai request với cùng principal: một ID không có thật, một ID thuộc tenant khác. Assert cùng **404 `type/title/code`**, body không chứa owner hoặc trạng thái bí mật. Test cả `HEAD`, conditional GET và collection; phân tích khác biệt latency trong test tải phù hợp, nhưng không viết assertion nanosecond tuyệt đối vốn rất dễ flaky. Bổ sung rate-limit/audit cho hành vi dò ID hàng loạt.

## 11. Bài tập: tìm và sửa ba đường rò rỉ

Một ứng dụng Spring có handler:

~~~java
@GetMapping("/v1/orders/{id}")
OrderEntity get(@PathVariable UUID id, Authentication auth) {
    OrderEntity order = repository.findById(id).orElseThrow();
    if (order.getStatus() == PAID) {
        throw new ConflictException("Order paid for " + order.getEmail());
    }
    if (!order.getCustomerId().equals(auth.getName())) {
        throw new ForbiddenException("Owned by " + order.getCustomerId());
    }
    return order;
}
~~~

**Yêu cầu:** (1) chỉ ra các điểm rò rỉ, (2) sửa kiến trúc bằng Java/Spring, (3) đề xuất response khi customer B gọi order A, (4) nêu ít nhất ba test để tránh tái phát.

**Đáp án tham khảo:** query `findById` không scoped, kiểm tra `PAID` trước authorization, thông báo lỗi phản chiếu email/owner và trả trực tiếp `OrderEntity` đều nguy hiểm. Lấy actor/tenant từ principal tin cậy, truy vấn bằng `id + tenant + customer`, trả `CustomerOrderView` cố định; nếu không thấy trong scope thì trả **404 trung tính** bất kể order thật tồn tại hay không. Chỉ xử lý `409` khi caller có quyền biết/trạng thái hợp lệ để công bố. Test 200 không có `internalNotes/paymentToken`; 404 cho ID khác tenant có cùng payload như ID không tồn tại; kiểm tra collection count và không xuất dữ liệu A sang B; thêm test thiếu scope/401, validation lỗi không chứa rejected value.

## 12. Checklist vận hành và nguồn tham khảo

- [ ] Chỉ trả **DTO/projection công khai**; không serialize entity hay để field mới tự xuất hiện.
- [ ] Kiểm **object authorization** theo tenant/owner/assignment và **field authorization** khi cần.
- [ ] Truy vấn có scope, kể cả list/count/sort/cursor/export/async/download và search suggestion.
- [ ] Không kiểm state/conflict trước visibility rồi tiết lộ order của người khác.
- [ ] 401/403/404/409/412 có ý nghĩa và chính sách tiết lộ thống nhất; 404 trung tính khi cần.
- [ ] `ProblemDetail` giữ public `type/code`, không chứa SQL, stack trace, rejected value, secrets hoặc nội dung đối tác.
- [ ] Auth filter có entry point/denied handler phù hợp; `@RestControllerAdvice` không che hết lỗi security.
- [ ] Cache/CDN/ETag/304/HEAD không vượt scope hoặc thời hạn quyền; dữ liệu nhạy cảm áp `no-store`.
- [ ] Log và audit được tách quyền; metric/trace không chứa token/PII; có rate limiting và phát hiện enumeration.
- [ ] Test MockMvc và integration test DB có fixture nhiều tenant, lỗi domain, DTO và metadata.

**Tham khảo:** [OWASP API Security Top 10 — BOLA/BOPLA](https://owasp.org/API-Security/), [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html), [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457), [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [Spring Security Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html).

**Kết luận:** API bảo mật không chỉ xác nhận **ai được gọi endpoint**, mà còn kiểm soát **resource nào được nhìn thấy, field nào được xuất và lỗi nào được phép biết**. Thiết kế DTO tối thiểu, query scoped, Problem Details trung tính, cache đúng quyền và test cross-tenant giúp giảm rò rỉ dữ liệu ngay cả khi HTTP status và authentication đều có vẻ hợp lệ.
