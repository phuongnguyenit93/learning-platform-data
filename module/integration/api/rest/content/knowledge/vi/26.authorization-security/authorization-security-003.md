# Kiểm tra quyền theo trường dữ liệu và chống mass assignment

> **Module:** `INTEGRATION_API_REST` — chương **Phân quyền và an toàn**. Bài học thực hành thiết kế REST API dựa trên resource/URI và hợp đồng dữ liệu rõ ràng, tập trung vào **quyền đọc/ghi từng thuộc tính** và phòng chống **mass assignment** trong Java/Spring. Ví dụ xuyên suốt sử dụng API đơn hàng với phân quyền theo người dùng, tenant, trạng thái nghiệp vụ; có HTTP, OpenAPI, kiểm thử và bài tập.

## 1. Tình huống: sửa một ghi chú nhưng thay được cả giá tiền

Một người dùng hợp lệ chỉ được sửa `deliveryNote` trên đơn hàng của mình:

~~~http
PATCH /v1/orders/ord_42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
Accept: application/json

{"deliveryNote":"Giao sau 18 giờ"}
~~~

Nếu controller nhận JSON rồi gán mọi property trực tiếp vào entity, kẻ tấn công có thể thử:

~~~http
PATCH /v1/orders/ord_42 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json

{
  "deliveryNote": "Giao sau 18 giờ",
  "tenantId": "tenant_vip",
  "status": "PAID",
  "totalAmount": "1",
  "internalApproved": true
}
~~~

Ngay cả khi caller có scope `orders.write` và sở hữu đơn, bind cả `tenantId`, `status`, `totalAmount` hoặc `internalApproved` vào entity vẫn là **mass assignment/over-posting** và gây leo thang quyền theo property.

Ở chiều đọc, serialize entity có thể làm lộ `fraudScore`, `internalComment`, `supplierCost`. Được đọc **đơn hàng** chưa chắc được đọc **mọi trường**.

### Mục tiêu học tập

Sau bài, bạn có thể kiểm quyền theo **object/field**, thiết kế **DTO allowlist/projection**, kiểm PATCH và nested objects, triển khai Java/Spring Security, mô tả OpenAPI và kiểm thử hành vi an toàn ở HTTP/database.

## 2. Threat model: người gọi kiểm soát những gì?

Caller kiểm soát **body JSON**, query, path, `fields` và JSON Pointer; ẩn ô nhập trên frontend không ngăn gửi request khác bằng curl/script.

~~~mermaid
flowchart TD
    A["Client: URI, body, fields, headers"] --> B["Authentication: ai gọi?"]
    B --> C["Object authorization: được dùng đơn này?"]
    C --> D["Field authorization: được đọc/ghi trường nào?"]
    D --> E["Domain rules: trạng thái, tenant, quan hệ?"]
    E --> F["DTO projection / explicit update"]
    F --> G["Persistence + audit + HTTP response"]
    B -. "Không hợp lệ" .-> X["401"]
    C -. "Không hợp lệ" .-> Y["403 hoặc 404 theo policy"]
    D -. "Không hợp lệ" .-> Z["400/403 theo contract"]
~~~

| Ranh giới | Câu hỏi | Bẫy thường gặp |
|---|---|---|
| Authentication | Token có hợp lệ, issuer/audience/scope được xác minh? | Đọc `tenantId` trong body thay vì dùng identity đã xác thực |
| Object-level authorization | Caller có được xem/sửa `ord_42`? | BOLA/IDOR: chỉ lấy `findById(id)` |
| Property-level read | Caller có được thấy `fraudScore`? | Trả JPA entity nguyên vẹn |
| Property-level write | Caller có được ghi `status`? | `BeanUtils.copyProperties` hoặc `ObjectMapper.updateValue` trên entity |
| Domain invariant | Sửa địa chỉ khi đơn đã giao có hợp lệ? | Chỉ kiểm role, không kiểm trạng thái |
| Nested reference | `shippingAddressId` có thuộc cùng tenant/chủ sở hữu? | Gán foreign key đến object người khác |

OWASP API Security Top 10 (2023) gọi lỗi property là **API3: BOPLA**, lỗi truy cập sai object là **API1: BOLA**. Hai tầng kiểm soát **bổ sung nhau**.

### 2.1. Ba dạng tấn công

**Mass assignment** ghi input trái quyền (`"isAdmin":true`); **property exposure** lộ output (`passwordHash`); **nested bypass** gán quan hệ như `roleIds:["admin"]`. `@PreAuthorize` trên endpoint không tự chặn chúng: **scope cho phép action, field policy giới hạn dữ liệu**.

## 3. Thiết kế ma trận quyền trước khi viết controller

Ví dụ hệ thống có **khách hàng**, **nhân viên hỗ trợ** và **dịch vụ thanh toán**. Các vai trò chỉ là một yếu tố; tenant, chủ sở hữu, trạng thái đơn và purpose còn quan trọng.

| Property | Customer (owner) đọc | Customer (owner) ghi | Support đọc | Payment service ghi |
|---|---|---|---|---|
| `id`, `status` | Có | Không | Có trong phạm vi hỗ trợ | Không tùy ý |
| `deliveryNote` | Có | Chỉ trước khi giao | Có nếu được giao xử lý | Không |
| `shippingAddressId` | Có nếu được phép xem | Chỉ khi đơn còn chỉnh sửa, địa chỉ thuộc owner | Theo nhiệm vụ | Không |
| `totalAmount` | Có | **Không** | Có theo phạm vi | Không (do pricing service quyết định) |
| `paymentStatus` | Có bản công khai | **Không** | Theo quyền | Chỉ qua workflow xác minh |
| `internalRiskScore` | **Không** | **Không** | Chỉ người có quyền risk | Không |
| `tenantId`, `createdBy` | Không cần trả cho customer | **Không** | Theo policy | **Không** |

**Deny by default:** field chưa được cấp quyền không xuất hiện ở output và không được ghi từ input; policy xét action, object, property, state, principal, tenant.

`deliveryNote` được sửa khi `DRAFT` nhưng không khi `SHIPPED`; support chỉ xem đơn được giao, không sửa tiền. Kiểm state **tại thời điểm ghi**, phối hợp transaction/optimistic locking.

### 3.1. Ai là nguồn đáng tin của tenant?

`?tenantId=tenant_other` trong query/body **không chứng minh quyền**. Dùng identity/JWT đã xác thực chữ ký, issuer, audience, lifetime; đối chiếu membership DB nếu quyền có thể bị thu hồi.

Query nên lọc tenant (`findByIdAndTenantId`) rồi **vẫn** kiểm owner/ACL/field. Có thể dùng chung 404 cho object không tồn tại và object không được phép tiết lộ.

## 4. Hợp đồng resource: không đồng nhất entity với JSON

Entity nội bộ có thể chứa:

~~~text
OrderEntity
  id, tenantId, ownerUserId, status, totalAmount, paymentStatus
  deliveryNote, shippingAddressId, internalRiskScore
  createdAt, updatedAt, version
~~~

Nhưng **public response** cho customer chỉ nên có:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
ETag: "order-42-v7"

{
  "id": "ord_42",
  "status": "DRAFT",
  "totalAmount": "250000",
  "deliveryNote": "Giao sau 18 giờ",
  "shippingAddressId": "addr_7"
}
~~~

Response DTO không chứa `internalRiskScore`/`ownerUserId`; `?fields=internalRiskScore` cũng không được nâng quyền.

### 4.1. Request DTO riêng cho từng command

Không dùng lại `OrderResponse` làm request update. Thay vào đó:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
    @NotBlank String productId,
    @Size(max = 500) String deliveryNote,
    @NotBlank String shippingAddressId
) {}
~~~

DTO create có **allowlist riêng**; service tính giá server-side. DTO update phải theo từng command, không dùng DTO lớn chứa field internal.

### 4.2. Cấu hình Jackson strict input và tolerant output

Spring Boot sử dụng Jackson cho JSON trong nhiều dự án. Có thể cấu hình kiểm tra unknown input:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Unknown input như `"internalRiskScore":0` có thể bị Jackson từ chối, nhưng **setting không phải authorization**. `@JsonIgnore`/`READ_ONLY` có thể im lặng bỏ qua field; hãy dùng DTO allowlist, validation và explicit update.

Client đọc response có thể cần tolerant reader; server nhận request ghi thường nên từ chối unknown input. Test **runtime mapper**, không chỉ file config.

## 5. Spring Security: kiểm quyền trên action và trên object

Với Spring Boot 3/Spring Security 6, cấu hình Resource Server xác minh JWT trước khi controller dùng `@AuthenticationPrincipal Jwt`. Method security có thể bật `@EnableMethodSecurity`, nhưng chỉ kiểm scope trên handler **chưa đủ**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
~~~

Đây là lát cắt cấu hình; ứng dụng thật vẫn phải có `SecurityFilterChain`, `oauth2ResourceServer(...jwt...)`, xác minh issuer/audience, quyền và chính sách CSRF phù hợp cơ chế xác thực. Không tự tin tưởng JWT lấy từ header mà chưa qua validation.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.*;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderApplicationService service;

    OrderController(OrderApplicationService service) {
        this.service = service;
    }

    @GetMapping(path = "/{id}", produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    ResponseEntity<CustomerOrderView> get(@PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(service.getVisible(
                tenant(jwt), jwt.getSubject(), id));
    }

    @PatchMapping(path = "/{id}",
        consumes = "application/merge-patch+json",
        produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    ResponseEntity<CustomerOrderView> patch(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody JsonNode patch) {
        CustomerOrderView updated = service.patchCustomerEditable(
            tenant(jwt), jwt.getSubject(), id, patch);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(updated);
    }

    private static String tenant(Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");
        if (tenantId == null || tenantId.isBlank()) {
            throw new AccessDeniedException("Missing tenant context");
        }
        return tenantId;
    }
}
~~~

`@PreAuthorize` chỉ kiểm **scope**; service còn kiểm tenant, owner và field policy. 401/403 ở security filter cần `AuthenticationEntryPoint`/`AccessDeniedHandler`, không chỉ MVC advice.

### 5.1. Repository luôn đọc theo tenant

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, String> {
    Optional<OrderEntity> findByIdAndTenantId(
        String id, String tenantId);
}

interface ShippingAddressRepository
        extends JpaRepository<ShippingAddress, String> {
    Optional<ShippingAddress> findByIdAndTenantId(
        String id, String tenantId);
}
~~~

`OrderEntity` và `ShippingAddress` cần ánh xạ JPA thật. Lọc tenant chưa đủ: service kiểm owner/assignment; danh sách/phân trang cũng phải lọc **ngay trong query**.

### 5.2. DTO projection: output chỉ chứa dữ liệu được phép

~~~java
public record CustomerOrderView(
    String id,
    String status,
    String totalAmount,
    String deliveryNote,
    String shippingAddressId
) {
    static CustomerOrderView from(OrderEntity order) {
        return new CustomerOrderView(
            order.getId(),
            order.getStatus().name(),
            order.getTotalAmount().toPlainString(),
            order.getDeliveryNote(),
            order.getShippingAddressId());
    }
}
~~~

`CustomerOrderView` chỉ chứa những property đã duyệt. Không dùng `BeanUtils.copyProperties(entity, response)` hoặc serializer duyệt toàn bộ entity với blacklist `@JsonIgnore`: field mới thêm vào entity có thể vô tình xuất hiện trên wire.

Support/customer nên có DTO/projection theo quyền. `?fields=fraudScore` chỉ được chọn field **đã cấp quyền**, không thể nâng quyền.

## 6. Đọc dữ liệu: không lộ field qua các ngả phụ

Đừng chỉ kiểm GET detail:

- **Pagination và search:** filter, sort hoặc thông báo lỗi không được để lộ giá trị private (ví dụ `sort=internalRiskScore`). Chỉ công bố các field filter/sort có quyền.
- **Export/CSV/NDJSON:** dùng cùng read policy với JSON detail; export thường bị bỏ quên vì đi qua code khác.
- **Cache và ETag:** cache theo principal/tenant nếu dữ liệu thay theo quyền; `Cache-Control: private` hoặc `no-store` theo độ nhạy. `Vary: Authorization` **không** thay cho chính sách cache cá nhân an toàn.
- **Log, audit, trace:** không ghi raw request/response chứa PII, token, risk score; log sự kiện được phép với mã field/decision, không nhất thiết ghi giá trị.
- **Error/validation:** không phản chiếu entity nội bộ, rejected value nhạy cảm hoặc SQL/ORM message.
- **OpenAPI và SDK:** schema public không chứa field server-only; test generated clients không tự serialize nguyên entity.

`200 OK` nhưng lộ `internalRiskScore` vẫn là lỗi bảo mật.

## 7. PATCH và nested object: kiểm mọi field trước khi thay đổi

JSON Merge Patch (RFC 7396) dùng **vắng mặt** để giữ nguyên, **giá trị mới** để thay, `null` để xóa property và merge đệ quy với object lồng nhau.

Endpoint này giới hạn Merge Patch vào **hai field top-level** `deliveryNote`/`shippingAddressId`; cấm nested object/array và mọi field server-owned. Đây là tập con có chủ đích, không phải engine RFC 7396 tổng quát.

### 7.1. Kiểm tra toàn bộ input trước khi đụng entity

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;

record AllowedPatch(
    boolean hasDeliveryNote,
    String deliveryNote,
    boolean hasAddress,
    String addressId
) {}

final class CustomerPatchParser {
    private static final Set<String> ALLOWED =
        Set.of("deliveryNote", "shippingAddressId");

    static AllowedPatch parse(JsonNode body) {
        if (body == null || !body.isObject()
                || body.size() == 0) {
            throw new InvalidPatchException(
                "Expected nonempty JSON object");
        }
        var fields = body.fieldNames();
        while (fields.hasNext()) {
            String field = fields.next();
            if (!ALLOWED.contains(field)) {
                // Cả field chưa biết lẫn field cấm đều bị từ chối,
                // không công bố chi tiết quyền nội bộ.
                throw new InvalidPatchException(
                    "Unsupported patch property");
            }
        }
        boolean hasNote = body.has("deliveryNote");
        JsonNode note = body.get("deliveryNote");
        if (hasNote && !note.isNull() && !note.isTextual()) {
            throw new InvalidPatchException(
                "deliveryNote must be string or null");
        }
        String value = hasNote && !note.isNull()
            ? note.textValue() : null;
        if (value != null && value.length() > 500) {
            throw new InvalidPatchException("Note too long");
        }

        boolean hasAddress = body.has("shippingAddressId");
        JsonNode address = body.get("shippingAddressId");
        if (hasAddress && (!address.isTextual()
                || address.textValue().isBlank())) {
            throw new InvalidPatchException(
                "shippingAddressId must be nonblank string");
        }
        return new AllowedPatch(hasNote, value,
            hasAddress, hasAddress ? address.textValue() : null);
    }
}

class InvalidPatchException extends RuntimeException {
    InvalidPatchException(String message) { super(message); }
}
~~~

Parser **kiểm tất cả field trước khi mutate**; bật duplicate-key detection nếu cần để các tầng không hiểu khác nhau về cùng một property.

`@JsonIgnoreProperties(ignoreUnknown=true)` có thể nuốt field cấm. Chọn **400** cho property không hỗ trợ, **403** cho thiếu quyền trên property đã biết nếu contract chọn, không lộ field bí mật.

### 7.2. Service kiểm object, field, trạng thái và quan hệ

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.fasterxml.jackson.databind.JsonNode;

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final ShippingAddressRepository addresses;

    public OrderApplicationService(
            OrderRepository orders,
            ShippingAddressRepository addresses) {
        this.orders = orders;
        this.addresses = addresses;
    }

    @Transactional(readOnly = true)
    public CustomerOrderView getVisible(
            String tenant, String user, String id) {
        return CustomerOrderView.from(
            authorizedCustomerOrder(tenant, user, id));
    }

    @Transactional
    public CustomerOrderView patchCustomerEditable(
            String tenant, String user, String id, JsonNode body) {
        // Validate toàn bộ shape và field trước khi mutate.
        AllowedPatch p = CustomerPatchParser.parse(body);
        OrderEntity order = authorizedCustomerOrder(
            tenant, user, id);

        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new OrderStateConflictException();
        }
        if (p.hasAddress()) {
            ShippingAddress address = addresses
                .findByIdAndTenantId(p.addressId(), tenant)
                .orElseThrow(OrderNotFoundException::new);
            if (!address.getOwnerUserId().equals(user)) {
                throw new OrderNotFoundException();
            }
        }

        if (p.hasDeliveryNote()) {
            // null theo contract nghĩa là xóa ghi chú.
            order.setDeliveryNote(p.deliveryNote());
        }
        if (p.hasAddress()) {
            order.setShippingAddressId(p.addressId());
        }
        // JPA dirty checking sẽ persist khi transaction commit.
        return CustomerOrderView.from(order);
    }

    private OrderEntity authorizedCustomerOrder(
            String tenant, String user, String id) {
        OrderEntity order = orders.findByIdAndTenantId(id, tenant)
            .orElseThrow(OrderNotFoundException::new);
        if (!order.getOwnerUserId().equals(user)) {
            throw new OrderNotFoundException();
        }
        return order;
    }
}

class OrderNotFoundException extends RuntimeException {}
class OrderStateConflictException extends RuntimeException {}
~~~

Các entity/repository là skeleton. Service chỉ gán hai field rõ ràng, không `entityManager.merge(requestBody)`; địa chỉ phải đúng tenant và owner.

`@Transactional` rollback khi validation/auth ném runtime exception, **không tự kiểm quyền hoặc chống lost update**. Dùng JPA `@Version`; nếu có `If-Match`, đối chiếu validator trong transaction và xử lý xung đột cả lúc flush/commit.

### 7.3. PUT, JSON Patch và nested fields

Chọn cơ chế cập nhật và validate đúng ngữ nghĩa:

| Định dạng hoặc cách ghi | Rủi ro | Thiết kế an toàn |
|---|---|---|
| `PUT` toàn resource JSON | Client gửi cả field server-owned | Cung cấp representation cập nhật riêng; từ chối field cấm, định nghĩa rõ full replacement |
| JSON Merge Patch | `null` xóa field; nested object bị merge | Allowlist **đường dẫn** được sửa, schema từng field, quyền tại thời điểm commit |
| JSON Patch `application/json-patch+json` | `op=move/copy`, `path`, `from` hoặc index array đi qua field nhạy cảm | Validate từng operation và cả source/destination; canonicalize JSON Pointer trước authorization |
| Form/query binding | Binder tự bind property nested hoặc collection | Chỉ bind vào DTO cụ thể và giới hạn tên field |
| Mapping DTO → entity | Mapper tự động thêm field mới sau refactor | Chỉ mapping field được phê duyệt, test regression |

JSON Patch không dùng `path.startsWith("/deliveryNote")` vì khớp nhầm `/deliveryNoteInternal`. Parse JSON Pointer (`~0`/`~1`), so từng đoạn và kiểm cả `path/from`, kể cả `move/copy` và array path như `/roles/0`.

Validate **invariant toàn document** sau patch, không chỉ field đơn lẻ.

## 8. Quyền theo field không chỉ là role: ABAC, state và purpose

RBAC cho `orders.read/write` là điều kiện đầu; property nhạy cảm thường cần **ABAC** theo object và ngữ cảnh:

~~~text
allow(customer, UPDATE, order.deliveryNote)
  iff customer.id == order.ownerUserId
  and customer.tenantId == order.tenantId
  and order.status == DRAFT

allow(support, READ, order.internalComment)
  iff support.tenantId == order.tenantId
  and support.assignedOrderIds contains order.id
  and support.hasPrivilege("orders.internal.read")
~~~

`ADMIN` không luôn có quyền với mọi mục đích. Đặt policy trong service/component tái sử dụng giữa REST, batch, message consumer và export.

Chỉ dùng `@JsonView` để che property vẫn có thể lấy/log dữ liệu trái quyền ở tầng khác. Với dữ liệu nhạy cảm, chọn DB projection tối thiểu; field mới mặc định **không đọc/ghi**.

### 8.1. Lỗi TOCTOU và phiên bản tài nguyên

Nếu state đổi từ `DRAFT` sang `SHIPPED` giữa check và write, cần optimistic locking:

~~~java
@jakarta.persistence.Version
private Long version;
~~~

Client cũng có thể gửi HTTP precondition:

~~~http
PATCH /v1/orders/ord_42 HTTP/1.1
If-Match: "order-42-v7"
Content-Type: application/merge-patch+json

{"deliveryNote":"Giao cổng phía Đông"}
~~~

ETag sai → **412**; thiếu precondition bắt buộc → **428**. `@Version`/ETag phải nhất quán; lỗi commit phải rollback, không retry bằng cách bỏ qua quyền/state.

## 9. HTTP response khi field hoặc quyền không hợp lệ

| Tình huống | Status điển hình | Lưu ý |
|---|---|---|
| Chưa xác thực/token không hợp lệ | `401 Unauthorized` | Qua security entry point, challenge phù hợp |
| Thiếu scope/action privilege | `403 Forbidden` | Không tự retry bằng token khác |
| Object không tồn tại hoặc không được tiết lộ | `404 Not Found` | Cùng thông điệp cho cross-tenant nếu policy chọn |
| Body JSON malformed / field không hỗ trợ / sai kiểu | `400 Bad Request` | Không silent ignore |
| Property đã biết nhưng caller không được ghi | `403` hoặc `400` theo policy | Không lộ metadata nhạy cảm |
| Object đang ở trạng thái không cho sửa | `409 Conflict` | GET lại trạng thái, không tự ép update |
| Field đúng kiểu nhưng vi phạm domain invariant | `422 Unprocessable Content` nếu API chọn | Contract phải thống nhất |
| `If-Match` stale / thiếu | `412` / `428` | Không ghi đè phiên bản mới |
| Lỗi DB, mapper, bug không mong đợi | `500` hoặc `503` | Không phơi SQL/stack trace |

Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-order-patch",
  "title": "Invalid patch document",
  "status": 400,
  "code": "INVALID_PATCH",
  "detail": "Yêu cầu chứa thuộc tính không được hỗ trợ."
}
~~~

Ứng dụng có thể dùng `@RestControllerAdvice`/`@ExceptionHandler` để map `InvalidPatchException` → 400, `OrderNotFoundException` → 404 và `OrderStateConflictException` → 409. Problem Details (RFC 9457) giúp client xử lý `type/status/code`; không phản chiếu raw body, field private, rejected value hoặc exception stack. Với 401/403 ở Spring Security filter, cần cấu hình error handler thích hợp — advice MVC không bảo đảm bắt lỗi phát sinh trước `DispatcherServlet`.

## 10. OpenAPI 3.1: mô tả input cho phép và output công khai

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /v1/orders/{id}:
    parameters:
      - in: path
        name: id
        required: true
        schema: {type: string}
    get:
      security: [{bearerAuth: []}]
      responses:
        '200':
          description: Thông tin đơn cho customer được phép xem
          content:
            application/json:
              schema: {$ref: '#/components/schemas/CustomerOrder'}
        '404': {description: Không tìm thấy hoặc không được công bố}
    patch:
      security: [{bearerAuth: []}]
      summary: Chỉ sửa ghi chú và địa chỉ khi đơn ở DRAFT
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema: {$ref: '#/components/schemas/CustomerPatch'}
      responses:
        '200':
          description: Cập nhật thành công
          content:
            application/json:
              schema: {$ref: '#/components/schemas/CustomerOrder'}
        '400': {description: JSON, kiểu hoặc property không hợp lệ}
        '403': {description: Thiếu quyền thao tác}
        '404': {description: Đơn hoặc địa chỉ không được phép truy cập}
        '409': {description: Trạng thái đơn không cho sửa}
        '412': {description: Precondition không còn khớp, nếu áp dụng}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    CustomerPatch:
      type: object
      additionalProperties: false
      minProperties: 1
      properties:
        deliveryNote:
          type: [string, 'null']
          maxLength: 500
          description: Null để xóa ghi chú
        shippingAddressId:
          type: string
          minLength: 1
          description: Phải thuộc cùng tenant và owner
    CustomerOrder:
      type: object
      required: [id, status, totalAmount]
      properties:
        id: {type: string, readOnly: true}
        status: {type: string, readOnly: true}
        totalAmount: {type: string, readOnly: true}
        deliveryNote: {type: [string, 'null']}
        shippingAddressId: {type: string}
~~~

`additionalProperties: false`/`minProperties: 1` khớp parser allowlist. OpenAPI `readOnly` chỉ là annotation, **không thực thi quyền**.

## 11. Kiểm thử quyền theo field ở HTTP và database

Test phải chứng minh **không đổi DB khi bị từ chối**, không lộ output và không có bypass qua nested/alternate endpoint.

| Input / hành vi | Kỳ vọng |
|---|---|
| Customer sửa `deliveryNote` trên đơn DRAFT của mình | 200; chỉ note thay đổi |
| Body chứa `deliveryNote` và `totalAmount=1` | 400; **không** cập nhật cả note |
| Gửi `status=PAID`, `tenantId=tenant_other` hoặc `internalRiskScore` | 400; database không đổi |
| Gửi `shippingAddressId` của chủ sở hữu khác | 404/403 theo policy; không đổi FK |
| Sửa đơn của tenant hoặc owner khác | 404/403 theo policy; không lộ đơn |
| Đơn đã SHIPPED nhưng patch note hợp lệ | 409; không ghi |
| `deliveryNote:null` | Xóa note; không xóa field khác |
| `shippingAddressId:null` hoặc nested object | 400, không sửa |
| JSON object có duplicate keys khác giá trị | Từ chối hoặc có parser policy nhất quán, không phụ thuộc thứ tự parser |
| GET đơn có `internalRiskScore` trong entity | JSON **không chứa** property đó |
| `?fields=internalRiskScore` hoặc export/CSV | Không nâng quyền đọc |
| Thiếu token, thiếu scope, token tenant khác | 401/403/404 thích hợp, không gọi mutation |
| Hai lần PATCH cạnh tranh, ETag stale | Không có lost update; 412 khi hợp đồng dùng `If-Match` |

### 11.1. MockMvc với JWT test principal

Các assertion sau giả định `@SpringBootTest`/`@AutoConfigureMockMvc` đã dựng app, test security dùng `spring-security-test`, và có fixture đơn `ord_42` thuộc `user_1`/`tenant_a`. Đây là snippet kiểm thử, không tự tạo fixture hay `@Version`:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
mockMvc.perform(patch("/v1/orders/ord_42")
        .with(jwt().jwt(token -> token
            .subject("user_1")
            .claim("tenant_id", "tenant_a"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.write")))
        .contentType("application/merge-patch+json")
        .accept("application/json")
        .content("""
            {"deliveryNote":"Hợp lệ","totalAmount":"1"}
            """))
    .andExpect(status().isBadRequest());

// Đọc lại DB bằng repository ở integration test:
// assertEquals("250000", order.getTotalAmount().toPlainString());
// assertEquals("Ghi chú cũ", order.getDeliveryNote());
~~~

Mock service **không chứng minh** authorization/rollback. Dùng integration test service thật và DB cho tenant/FK, optimistic locking; `@WebMvcTest` chỉ xác minh HTTP/security slice.

### 11.2. Fuzz input có cấu trúc

Kiểm thử thêm các dạng tấn công: tên field khác chữ hoa/thường, field lồng như `{"payment":{"status":"PAID"}}`, array chứa ID liên kết trái quyền, string quá dài, unknown property, JSON Pointer với escape `~0`/`~1`, null và duplicate keys. Đừng chỉ viết một test `"isAdmin": true`; một refactor tự động thêm field vào DTO có thể mở lỗ hổng mới mà test cũ không phát hiện.

## 12. Bài thực hành: khóa quyền ở thuộc tính của API

**Bối cảnh:** API `/v1/accounts/{id}` cho customer đổi `displayName` và `phone`. Entity còn `role`, `tenantId`, `creditLimit`, `isVerified`, `passwordHash`. Nhân viên support chỉ được xem số điện thoại của tài khoản được giao xử lý; chỉ workflow nghiệp vụ nội bộ được đổi `creditLimit`.

**Yêu cầu:**

1. Lập ma trận quyền **đọc/ghi** theo customer, support, internal service và trạng thái tài khoản.
2. Thiết kế request DTO create/update và response DTO riêng; không trả `passwordHash`, không bind `role/creditLimit`.
3. Viết `PATCH` chỉ cho `displayName`/`phone`, xác định semantics của null/vắng mặt và kiểm nested field.
4. Thực thi kiểm tenant/owner/assignment ở service, không lấy tenant từ JSON.
5. Chọn HTTP status khi input field cấm, caller ngoài tenant, không đủ quyền và state conflict; dùng Problem Details an toàn.
6. Tài liệu hóa OpenAPI 3.1 (`additionalProperties: false`, request vs response) nhưng không coi schema là authorization.
7. Viết tối thiểu mười test HTTP/database, gồm over-posting hợp lệ+cấm cùng body, cross-tenant reference, serialization leak và concurrent update.

**Tiêu chí đạt:** field hợp lệ sửa được, property nhạy cảm không đọc/ghi được, request lỗi không cập nhật từng phần; thêm field entity không mở quyền.

## 13. Ghi nhớ

**Có quyền trên resource không đồng nghĩa có quyền trên mọi field.** Chống mass assignment và rò property bằng **DTO allowlist/projection, kiểm tenant/owner/field/state tại service và transaction**.

Frontend, `@JsonIgnore`, OpenAPI `readOnly` hay scope tổng quát không thay authorization server. Chứng minh bằng **HTTP/database tests** cho nested payload, field mới, concurrency và export.
