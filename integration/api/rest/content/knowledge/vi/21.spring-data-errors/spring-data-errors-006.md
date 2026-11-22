# Tách kiểm tra cấu trúc khỏi kiểm tra có truy cập dữ liệu

**POST /v1/orders** chứa cartId và shippingAddressId. Spring có thể kiểm tra JSON, UUID và độ dài ghi chú, **nhưng chưa biết** giỏ thuộc ai, còn mở, địa chỉ được phép dùng hoặc tồn kho đủ. Đưa mọi kiểm tra vào validator truy vấn DB vừa tăng chi phí, vừa có thể rò dữ liệu và vẫn gặp race.

Chương **Dữ liệu và lỗi Spring** của **INTEGRATION_API_REST** kết hợp HTTP, Java/Spring MVC, Spring Data/JPA và xử lý lỗi REST nhất quán.

## 1. Mục tiêu và nguyên tắc phân tầng

Mục tiêu:

1. Phân biệt **kiểm tra cấu trúc** dựa trên request và **kiểm tra cần dữ liệu** dựa trên trạng thái nghiệp vụ, quyền hoặc repository.
2. Dùng **Jakarta Bean Validation** với **@Valid**, **@NotNull**, **@Size**, **@Pattern** trên DTO; hiểu ranh giới với JSON deserialization và method validation.
3. Đặt **data-access/business validation** trong service hoặc domain workflow, với transaction và truy vấn theo quyền.
4. Chọn HTTP **400, 401, 403, 404, 409, 412, 422, 503** theo nguyên nhân; dùng **Problem Details (RFC 9457)** mà không lộ dữ liệu.
5. Chống race bằng unique constraint, conditional update và optimistic locking thay vì **SELECT kiểm tra rồi INSERT/UPDATE vô điều kiện**.
6. Kiểm thử riêng validation không truy cập DB và validation có DB/concurrency/security.

**Nguyên tắc:** cú pháp/kiểu dữ liệu thuộc DTO/MVC; ràng buộc phụ thuộc **quyền, resource, trạng thái hoặc ghi đồng thời** thuộc service/database.

~~~mermaid
flowchart LR
    C["Client HTTP"] --> S["Security filters: xác thực"]
    S --> M["Spring MVC: parse JSON + @Valid DTO"]
    M --> V["Service: quyền, trạng thái, ràng buộc nghiệp vụ"]
    V --> D[("DB: khóa, unique, conditional update")]
    D --> R["HTTP response / Problem Details"]
    M -. "400" .-> R
    V -. "404 / 409 / 422" .-> R
~~~

**Security filter** thường chạy trước MVC, có thể trả 401/403 trước khi DTO được kiểm tra.

## 2. Bảng phân loại các loại kiểm tra

| Câu hỏi | Ví dụ | Nơi kiểm tra hợp lý | Có cần DB? |
|---|---|---|---|
| JSON có parse được? | Thiếu dấu ngoặc, UUID không đúng định dạng | Jackson / HTTP message conversion | Không |
| Thiếu trường bắt buộc? | cartId = null | **@NotNull** ở request DTO | Không |
| Chuỗi có đúng giới hạn? | note dài 300 ký tự | **@Size(max = 200)** | Không |
| Định dạng có hợp lệ? | currency = "XYZ?" | DTO validator nếu chỉ là cú pháp/enum | Không |
| Quan hệ giữa hai trường hợp lệ? | startDate sau endDate | Custom validator thuần dữ liệu hoặc service | Không nhất thiết |
| Cart có tồn tại? | cartId không có trong DB | Repository qua service | Có |
| Cart có thuộc user/tenant? | ID của tài khoản khác | **Authorization + scoped lookup** | Có |
| Cart còn OPEN? | Đã thanh toán | Service/domain state machine | Có |
| Địa chỉ được dùng cho đơn này? | Address khác owner hoặc vùng không hỗ trợ | Scoped lookup + business policy | Có |
| Tồn kho có đủ khi commit? | Hai người cùng mua item cuối | **Conditional update/transaction** | Có, phải nguyên tử |
| Order đã được tạo với idempotency key? | Client retry POST sau timeout | Unique constraint + lưu kết quả operation | Có |

Quy tắc giữa hai trường như **startDate ≤ endDate** có thể dùng class-level validator thuần dữ liệu. Nếu phụ thuộc giá, quyền hay lịch trong DB, dùng service.

### 2.1. Vì sao không đặt kiểm tra tồn tại DB trong annotation?

Ví dụ không nên lấy làm mặc định:

~~~java
// Ví dụ anti-pattern: validator phải truy cập DB để kiểm tra DTO.
@CartExists
private UUID cartId;
~~~

**ConstraintValidator** có thể gọi repository, nhưng cách này gây rủi ro:

- Truy vấn DB trước khi workflow xác định quyền/transaction, dễ rò ID của người khác.
- Khó phối hợp cart, địa chỉ và tồn kho trong một transaction; dễ N+1 query.
- Kiểm tra tại T1 **không chặn** resource thay đổi ở T2.
- Unit test DTO phải mock repository.

Validator truy vấn DB chỉ nên là **ngoại lệ có thiết kế bảo mật/transaction rõ**, không phải bằng chứng dữ liệu còn đúng lúc commit.

## 3. Tầng cấu trúc: JSON, kiểu dữ liệu và Jakarta Bean Validation

### 3.1. DTO chỉ mô tả hợp đồng đầu vào

Ví dụ Java 17, Spring Boot 3 và thư viện **spring-boot-starter-validation**:

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record CreateOrderRequest(
        @NotNull UUID cartId,
        @NotNull UUID shippingAddressId,
        @Size(max = 200) String note
) {}
~~~

Quy tắc DTO:

- Thiếu **cartId/shippingAddressId** thành null rồi bị **@NotNull** từ chối.
- UUID sai kiểu bị **Jackson** từ chối trước @Valid.
- **note** cho phép null, tối đa 200 ký tự.
- DTO **không kiểm tra sự tồn tại của cart**.

**@NotBlank** khác @NotNull/@NotEmpty; JSON lồng nhau cần cascade **@Valid** khi phù hợp.

### 3.2. Controller gọi validation trước workflow

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {
    private final OrderService service;
    private final ActorResolver actors;

    public OrderController(OrderService service, ActorResolver actors) {
        this.service = service;
        this.actors = actors;
    }

    @PostMapping
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request,
            Authentication authentication) {
        Actor actor = actors.fromTrustedAuthentication(authentication);
        OrderView created = service.create(actor, request);
        URI location = URI.create("/v1/orders/" + created.id());
        return ResponseEntity.created(location)
                .cacheControl(CacheControl.noStore())
                .body(created);
    }
}
~~~

**@Valid** chạy sau Jackson; input sai thì service không được gọi. **201 + Location** phải trỏ resource thực sự.

**Location tương đối** hợp lệ; nếu cần URI tuyệt đối, dùng public origin đáng tin thay vì Host tùy ý.

### 3.3. Phân biệt lỗi deserialization và lỗi constraint

~~~http
POST /v1/orders HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>

{"cartId":"not-a-uuid","shippingAddressId":"d5c8a4d8-84b9-4c6d-8cb1-aef95085ef4e"}
~~~

Đây là lỗi chuyển kiểu JSON, thường là **400** qua **HttpMessageNotReadableException**, chưa cần DB.

Với JSON đúng kiểu nhưng thiếu cartId:

~~~json
{"shippingAddressId":"d5c8a4d8-84b9-4c6d-8cb1-aef95085ef4e"}
~~~

**@NotNull** thường gây **MethodArgumentNotValidException**, cũng map thành 400; handler cần phân loại hai nguồn lỗi mà không phản chiếu raw request.

### 3.4. Validation có phạm vi và giới hạn

Annotation không chặn body quá lớn, JSON sâu hoặc rate abuse; dùng giới hạn gateway/server.

**@RequestParam/@PathVariable** có conversion/method validation riêng; kiểm thử type mismatch và **HandlerMethodValidationException** (tùy phiên bản), không mặc định qua MethodArgumentNotValidException.

## 4. Tầng truy cập dữ liệu: quyền, tồn tại và trạng thái

Giả sử **cartId** là UUID hợp lệ. Client có thể gửi bất kỳ UUID, kể cả ID giỏ hàng của người khác. Nếu chỉ gọi:

~~~java
cartRepository.findById(request.cartId());
~~~

rồi trả thông tin lỗi khác nhau cho “có nhưng không thuộc user” và “không có”, API có thể bị **IDOR/BOLA** hoặc rò khả năng tồn tại của tài nguyên.

Thiết kế tốt hơn là truy vấn theo **phạm vi người gọi đã xác thực**:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.repository.Repository;

interface CartRepository extends Repository<Cart, UUID> {
    Optional<Cart> findByIdAndTenantIdAndOwnerId(
            UUID id, UUID tenantId, UUID ownerId);
}

interface AddressRepository extends Repository<Address, UUID> {
    Optional<Address> findByIdAndTenantIdAndOwnerId(
            UUID id, UUID tenantId, UUID ownerId);
}
~~~

**Actor** lấy từ authentication đáng tin, không từ JSON. Spring Data có thể dùng derived query, SQL cần scope tương đương.

### 4.1. Trả 404 hay 403?

Resource không tồn tại hoặc không được công bố có thể trả **404**; **403** khi thiếu quyền có thể công bố; **401** khi thiếu xác thực, thường từ Spring Security.

UUID đúng cú pháp nhưng cart không tồn tại **không phải lỗi 400 cấu trúc**. Không tiết lộ owner khác trong thông báo.

### 4.2. Trạng thái dữ liệu là quy tắc workflow

Cart có tồn tại và thuộc user vẫn có thể đã **CHECKED_OUT** hoặc **CANCELLED**. Khi tạo order, nghiệp vụ có thể yêu cầu cart ở **OPEN** và có item. Đó là kiểm tra **dựa trên trạng thái hiện tại**, không nên thực hiện bằng annotation @NotNull hay @Pattern.

Với cart đã thanh toán, **409 Conflict** thường diễn đạt xung đột trạng thái hiện tại. Với địa chỉ nằm ngoài vùng hỗ trợ dù đúng owner, API có thể chọn **422 Unprocessable Content** nếu đó là quy tắc semantics của payload, hoặc mã business error khác được contract công bố. Không có một mapping status duy nhất đúng cho mọi domain.

### 4.3. Phân biệt kiểm tra đọc và điều kiện ghi

Giả sử cả hai request đọc thấy **stock=1** rồi cùng tạo order. Nếu chỉ:

~~~text
if (stock.available >= 1) {
    stock.available -= 1;
    save(stock);
}
~~~

trong các transaction không có cơ chế bảo vệ thích hợp, bạn vẫn có thể **bán quá số lượng**. Kiểm tra trước chỉ là **preflight**, không thay được cập nhật nguyên tử tại nơi ghi.

## 5. Service và transaction: kiểm tra theo dữ liệu được phép nhìn thấy

Controller xử lý HTTP/DTO; **OrderService** điều phối nghiệp vụ và repository.

### 5.1. Contract giữa service và repository

~~~java
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.security.core.Authentication;

record Actor(UUID tenantId, UUID userId) {}

interface ActorResolver {
    Actor fromTrustedAuthentication(Authentication authentication);
}

record OrderView(UUID id, String status) {}
record CartLine(UUID productId, long quantity) {}
record CartSnapshot(UUID id, String status, List<CartLine> lines) {}

interface CartStore {
    Optional<CartSnapshot> findVisible(
            UUID tenant, UUID owner, UUID cartId);
    // Cập nhật có điều kiện trong DB, trả số hàng bị thay đổi.
    int claimOpen(UUID tenant, UUID owner, UUID cartId);
}

interface AddressStore {
    boolean existsForOwner(UUID tenant, UUID owner, UUID addressId);
}

interface InventoryStore {
    // Trừ tồn kho nếu còn đủ; 1 = thành công, 0 = không đủ/không hợp lệ.
    int reserveIfAvailable(UUID tenant, UUID productId, long quantity);
}

interface OrderStore {
    UUID insert(UUID tenant, UUID owner, UUID addressId, UUID cartId);
}

interface OutboxStore {
    void appendOrderCreated(UUID orderId);
}
~~~

Các interface cần implementation, entity/mapping và transaction thực. **CartSnapshot** phải nhất quán với lần checkout.

### 5.2. Service thực hiện data checks và tạo đơn

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final CartStore carts;
    private final AddressStore addresses;
    private final InventoryStore inventory;
    private final OrderStore orders;
    private final OutboxStore outbox;

    public OrderService(CartStore carts, AddressStore addresses,
            InventoryStore inventory, OrderStore orders,
            OutboxStore outbox) {
        this.carts = carts;
        this.addresses = addresses;
        this.inventory = inventory;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public OrderView create(Actor actor, CreateOrderRequest request) {
        CartSnapshot cart = carts.findVisible(
                actor.tenantId(), actor.userId(), request.cartId())
                .orElseThrow(() ->
                    new ResourceNotFoundException("CART_NOT_FOUND"));

        if (!addresses.existsForOwner(
                actor.tenantId(), actor.userId(),
                request.shippingAddressId())) {
            throw new ResourceNotFoundException("ADDRESS_NOT_FOUND");
        }
        if (!"OPEN".equals(cart.status()) || cart.lines().isEmpty()) {
            throw new DomainConflictException("CART_NOT_OPEN");
        }

        // Database quyết định atomically request nào thắng.
        int claimed = carts.claimOpen(
                actor.tenantId(), actor.userId(), request.cartId());
        if (claimed != 1) {
            throw new DomainConflictException("CART_CHANGED");
        }

        for (CartLine line : cart.lines()) {
            if (inventory.reserveIfAvailable(
                    actor.tenantId(), line.productId(),
                    line.quantity()) != 1) {
                throw new DomainConflictException("OUT_OF_STOCK");
            }
        }

        UUID id = orders.insert(
                actor.tenantId(), actor.userId(),
                request.shippingAddressId(), request.cartId());
        outbox.appendOrderCreated(id);
        return new OrderView(id, "CREATED");
    }
}

class ResourceNotFoundException extends RuntimeException {
    ResourceNotFoundException(String code) { super(code); }
}

class DomainConflictException extends RuntimeException {
    DomainConflictException(String code) { super(code); }
}
~~~

Điều quan trọng:

- Service nhận **Actor từ security context đáng tin**, không lấy owner do client khai.
- Tìm giỏ hàng và địa chỉ trong **phạm vi tenant/owner**, tránh lộ resource ngoài quyền.
- **claimOpen** phải là thao tác cập nhật có điều kiện ở DB; nếu hai request tranh cùng cart, chỉ một request được nhận.
- **reserveIfAvailable** cũng phải nguyên tử; một lần SELECT thấy đủ hàng không có nghĩa vẫn đủ khi UPDATE.
- Tạo order, trừ stock, đánh dấu cart và ghi outbox cần thuộc **một transaction DB** nếu sử dụng cùng datasource. Thất bại giữa chừng phải rollback tất cả.
- Outbox ghi **bản ghi sự kiện** trong transaction; gửi message ra broker từ worker riêng. Không gọi email/PSP trực tiếp rồi giả định cùng transaction DB sẽ rollback tác động bên ngoài.

Mã chỉ minh họa, chưa chạy độc lập. Các API sửa cart lines phải dùng cùng quy tắc lock/status, hoặc checkout đọc lines sau claim với isolation phù hợp.

### 5.3. Conditional update mạnh hơn check-then-act

Ví dụ PostgreSQL cho claim cart:

~~~sql
UPDATE carts
   SET status = 'CHECKING_OUT', updated_at = now()
 WHERE cart_id = :cart_id
   AND tenant_id = :tenant_id
   AND owner_id = :owner_id
   AND status = 'OPEN';
~~~

Với stock:

~~~sql
UPDATE inventory
   SET available = available - :quantity
 WHERE tenant_id = :tenant_id
   AND product_id = :product_id
   AND available >= :quantity
   AND :quantity > 0;
~~~

Sau mỗi UPDATE, kiểm tra **affected rows = 1**. Các câu lệnh này cần được triển khai bằng repository/SQL phù hợp database và transaction isolation. Nếu cart lines có thể bị thay đổi cùng lúc, các luồng sửa cart phải phối hợp lock/status để không thêm item sau khi checkout bắt đầu.

**Unique constraint/FK** bảo vệ dữ liệu khi race; ví dụ mỗi cart chỉ checkout một lần. Chuyển lỗi constraint theo operation, không trả SQL/stack trace.

### 5.4. Data checks không phải ảnh chụp bất biến

**@Transactional** không khóa mọi SELECT hay tạo transaction xuyên broker/ERP. Bảo vệ bất biến cụ thể bằng:

- **Constraint/conditional update:** quota, uniqueness, số lượng tồn.
- **Optimistic locking @Version:** resource được cập nhật khi version còn khớp; client có thể dùng **If-Match** trong HTTP.
- **Row lock phù hợp:** khi nghiệp vụ cần cô lập sửa cart lines và checkout.
- **Idempotency record:** POST retry sau timeout không tạo thêm logical order.
- **Transactional outbox:** side effect sau commit có thể được phát lại và consumer dedupe.

Kiểm tra và ghi là **một workflow**, không phải hai bước không ràng buộc.

## 6. Thiết kế status HTTP theo nguồn lỗi

Hãy phân biệt **request sai** với **tài nguyên không có quyền truy cập**, **trạng thái đã thay đổi** và **hệ thống tạm không sẵn sàng**.

| Nguồn lỗi | Status điển hình | Mã ứng dụng | Hành động client |
|---|---|---|---|
| JSON sai cú pháp/UUID sai kiểu | **400 Bad Request** | INVALID_JSON | Sửa request |
| @NotNull/@Size/@Pattern không đạt | **400** (hoặc 422 nếu contract chọn cho validation semantics) | INVALID_REQUEST | Sửa field |
| Không có xác thực phù hợp | **401 Unauthorized** | AUTH_REQUIRED | Xác thực lại |
| Có danh tính nhưng thiếu quyền operation | **403 Forbidden** | FORBIDDEN | Không tự retry |
| Cart/address không tìm thấy trong scope | **404 Not Found** | RESOURCE_NOT_FOUND | Kiểm tra resource/đường dẫn |
| Cart đã CHECKED_OUT hoặc stock không đủ khi ghi | **409 Conflict** | CART_CHANGED / OUT_OF_STOCK | Đọc lại trạng thái, quyết định mới |
| Trạng thái payload hợp lệ cú pháp nhưng không thể xử lý về domain | **422 Unprocessable Content** (khi contract chọn) | UNSUPPORTED_SHIPPING_REGION | Chọn dữ liệu hợp lệ |
| If-Match cũ không còn phù hợp | **412 Precondition Failed** | VERSION_CONFLICT | GET phiên bản mới, giải quyết conflict |
| Bắt buộc có If-Match nhưng thiếu | **428 Precondition Required** | PRECONDITION_REQUIRED | Gửi điều kiện sau khi đọc resource |
| Repository/DB không sẵn sàng | **503 Service Unavailable** khi tạm thời | DEPENDENCY_UNAVAILABLE | Retry có giới hạn/backoff |
| Lỗi code bất ngờ | **500 Internal Server Error** | INTERNAL_ERROR | Thông báo, dùng trace ID để điều tra |

**Không phải mọi data validation đều là 409**: địa chỉ ngoài scope có thể 404, vùng giao hàng không hỗ trợ có thể 422, cart đã đóng thường 409.

### 6.1. Đừng đổi lỗi hạ tầng thành lỗi người dùng

Database timeout không phải 400/404. Dùng 503 cho outage tạm thời hoặc 500 khi phù hợp; đừng catch mọi **DataAccessException** thành lỗi của client.

### 6.2. Không retry mù request ghi sau 503/504

Gateway 504 có thể đến **sau commit**. Retry POST cần **Idempotency-Key** với scope/fingerprint hoặc operation ID để đối soát; nếu không có thể tạo order trùng.

### 6.3. 412/428 khác 409

**If-Match** là HTTP precondition: ETag không còn khớp thường được báo bằng **412**; thiếu điều kiện mà API bắt buộc có thể là **428**. **409** dành cho xung đột trạng thái nghiệp vụ không nhất thiết liên quan tới precondition HTTP. Không tự retry 412 bằng cách bỏ If-Match, vì có thể ghi đè cập nhật của người khác.

## 7. Spring @RestControllerAdvice và Problem Details

**RFC 9457 Problem Details** cung cấp các trường tiêu chuẩn **type, title, status, detail, instance** và cho phép mở rộng bằng mã lỗi ứng dụng. Spring Framework 6 có **ProblemDetail** và **ResponseEntityExceptionHandler** để xử lý lỗi HTTP của MVC. Hãy đưa **status/domain code ổn định** cho client; tránh phơi bày rejected value, SQL, stack trace hoặc tên bảng.

Ví dụ phản hồi validation:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request fields failed validation.",
  "code": "INVALID_REQUEST",
  "errors": [
    {"field": "cartId", "message": "must not be null"}
  ]
}
~~~

Ví dụ service xác định cart không còn OPEN:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-conflict",
  "title": "Order cannot be created",
  "status": 409,
  "detail": "Refresh the cart and review its state.",
  "code": "CART_CHANGED"
}
~~~

### 7.1. Handler riêng cho lỗi request và domain

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
class ApiErrors extends ResponseEntityExceptionHandler {
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        ProblemDetail p = problem(HttpStatus.BAD_REQUEST,
                "invalid-request", "Invalid request",
                "Request fields failed validation.", "INVALID_REQUEST");

        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors().stream()
                .map(field -> Map.of(
                        "field", field.getField(),
                        "message", field.getDefaultMessage() == null
                                ? "invalid" : field.getDefaultMessage()))
                .toList();
        p.setProperty("errors", errors);
        return handleExceptionInternal(ex, p, headers,
                HttpStatus.BAD_REQUEST, request);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        ProblemDetail p = problem(HttpStatus.BAD_REQUEST,
                "invalid-json", "Malformed request",
                "JSON cannot be parsed or converted.", "INVALID_JSON");
        return handleExceptionInternal(ex, p, headers,
                HttpStatus.BAD_REQUEST, request);
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(
            ResourceNotFoundException ex) {
        ProblemDetail p = problem(HttpStatus.NOT_FOUND,
                "resource-not-found", "Resource not found",
                "Resource is unavailable.", "RESOURCE_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(p);
    }

    @ExceptionHandler(DomainConflictException.class)
    ResponseEntity<ProblemDetail> conflict(
            DomainConflictException ex) {
        ProblemDetail p = problem(HttpStatus.CONFLICT,
                "order-conflict", "Order cannot be created",
                "Refresh the cart and review its state.",
                ex.getMessage());
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(p);
    }

    private static ProblemDetail problem(
            HttpStatus status, String slug, String title,
            String detail, String code) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(status, detail);
        p.setType(URI.create("https://api.example.test/problems/" + slug));
        p.setTitle(title);
        p.setProperty("code", code);
        return p;
    }
}
~~~

**Chú ý khi triển khai:**

- `errors` và `code` là extension, không phải member bắt buộc của RFC 9457. Nên lọc **message** theo danh sách an toàn, tránh custom constraint message chèn giá trị nhạy cảm.
- Trong ví dụ, ex.getMessage() của **DomainConflictException** chỉ chứa **mã lỗi do service kiểm soát** như CART_CHANGED/OUT_OF_STOCK. Không tái sử dụng cách này cho exception có message chứa SQL hoặc thông tin nội bộ.
- **handleExceptionInternal** cần được cấu hình thêm no-store chung cho lỗi chứa dữ liệu người dùng nếu hợp đồng yêu cầu; đoạn code trên minh họa rõ no-store cho hai domain error, chưa áp dụng cho mọi nhánh MVC.
- **401/403** thường đến từ Spring Security authentication/authorization handlers **trước controller**, không nên kỳ vọng @RestControllerAdvice bắt tất cả SecurityException.
- Không catch toàn bộ RuntimeException rồi giả mọi lỗi là 400. Lỗi bất ngờ cần log/tracing an toàn và mã 500 phù hợp.

### 7.2. Chuyển lỗi database thành domain error có chọn lọc

Ví dụ một unique constraint của **idempotency key** bị vi phạm khi hai POST đồng thời. Khi **biết chính xác constraint** và operation, backend có thể nạp lại kết quả đã lưu hoặc trả 409 theo hợp đồng. Nhưng **DataIntegrityViolationException** có thể là unique, FK, null, constraint khác hoặc bug mapping: **không map tất cả thành 409** và không trả tên constraint/SQL cho client.

Với **OptimisticLockingFailureException**, service phải biết đang bảo vệ version nào và chuyển thành 409 hoặc **412 nếu vi phạm If-Match** theo contract. Một số lỗi database làm transaction hiện tại bị đánh dấu rollback-only; đừng cố tiếp tục ghi trong cùng transaction sau khi bắt exception.

## 8. Kiểm thử theo đúng ranh giới

| Test | Cách thực hiện | Kết quả cần chứng minh |
|---|---|---|
| Sai cú pháp JSON/UUID | Gửi body không parse được | 400, không gọi OrderService |
| Thiếu cartId / note quá dài | MockMvc gửi DTO vi phạm @Valid | 400 + field error an toàn |
| Cart không tồn tại trong scope | Service dùng repository fixture | 404, không reserve stock |
| Cart thuộc tenant khác | Hai principal cùng thử UUID | Không lộ cart, không tạo order |
| Cart đã CHECKED_OUT | Gửi DTO đúng nhưng cart đóng | 409, transaction không tạo order |
| Hai request cùng checkout | Concurrent POST trên một cart | Tối đa một claim thành công |
| Stock chỉ còn một | Hai cart tranh cùng item cuối | Không âm kho; một transaction rollback |
| DB outage | Repository trả lỗi kết nối | 5xx/503 phù hợp, không trả 400 giả |
| POST commit rồi mất response | Fault injection sau commit | Đối soát/idempotency tránh tạo đơn trùng |

Ví dụ MockMvc cho **lớp cấu trúc** (cần Spring context, security principal và service fixture):

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationTest {
    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(authorities = "orders:write")
    void missingCartIdReturns400() throws Exception {
        mvc.perform(post("/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"shippingAddressId":
                      "d5c8a4d8-84b9-4c6d-8cb1-aef95085ef4e"}
                    """))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }
}
~~~

**Test này không tự chứng minh race hoặc quyền**. Phải kiểm tra MockMvc đã đi qua filter bảo mật đúng cấu hình (CSRF nếu dùng cookie/session), còn test integration cho DB dùng transaction thật và barrier để đồng thời hóa hai request. Test ở tầng service có thể dùng fake repository để kiểm tra luồng, nhưng bất biến **không bán quá tồn/unique constraint** cần kiểm chứng trên database thật.

## 9. Bài tập: ranh giới nào xử lý?

Client tạo đơn với cartId hợp lệ, địa chỉ của tenant khác và note dài 300 ký tự. Một giây sau, cart được thanh toán bởi request khác; cùng lúc hai người mua sản phẩm cuối.

**Yêu cầu:** (1) phân loại lỗi cấu trúc và data-access; (2) chọn status cho note dài, địa chỉ không trong scope, cart đã đóng, stock hết; (3) viết một DTO dùng Jakarta Validation; (4) đề xuất repository truy vấn theo tenant; (5) viết điều kiện UPDATE giữ stock không âm; (6) nêu ba test bảo mật/race.

**Gợi ý:** @Size từ chối note trước service (**400**); địa chỉ ngoài scope có thể được che bằng **404**; cart đóng và hết stock tại lúc commit thường **409**. Tất cả kiểm tra quyền dùng tenant từ authentication; conditional UPDATE stock và cart phải nằm trong transaction. Hai request đồng thời chỉ được tạo kết quả phù hợp với tồn kho, không dựa vào SELECT preflight.

## 10. Checklist và tham khảo

- [ ] DTO dùng @Valid cho cấu trúc, không tùy tiện gọi repository từ validator.
- [ ] Tồn tại/quyền/trạng thái kiểm tra trong service với scoped lookup.
- [ ] Race được chặn tại database bằng transaction, constraint, conditional update.
- [ ] Lỗi HTTP phân loại rõ, Problem Details không chứa dữ liệu nội bộ.
- [ ] Test phân biệt lỗi trước service với lỗi có DB, concurrent write và cross-tenant.

Tham khảo: **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **Spring MVC Validation**, https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html; **Spring Data JPA Repositories**, https://docs.spring.io/spring-data/jpa/reference/repositories.html; **Spring Transaction Management**, https://docs.spring.io/spring-framework/reference/data-access/transaction.html.

**Kết luận:** **Kiểm tra cấu trúc** quyết định request có đúng định dạng/hợp đồng dữ liệu đầu vào; **kiểm tra có truy cập dữ liệu** quyết định request có hợp lệ với quyền và trạng thái thực tế. Spring @Valid và repository là công cụ cho **hai trách nhiệm khác nhau**. Tính đúng cuối cùng cần thêm **transaction, điều kiện ghi nguyên tử, lỗi HTTP đúng nguyên nhân và kiểm thử cạnh tranh**.
