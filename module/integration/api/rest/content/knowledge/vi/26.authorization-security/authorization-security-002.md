# Kiểm tra quyền theo từng đối tượng để ngăn BOLA, IDOR

## 1. Một API đúng HTTP vẫn có thể lộ dữ liệu

Alice đã đăng nhập và có scope `orders:read`. Đơn `o-101` thuộc Alice, `o-202` thuộc Bob. Alice gửi:

```http
GET /api/orders/o-202 HTTP/1.1
Authorization: Bearer <alice-token>
Accept: application/json
```

Nếu server chỉ kiểm tra token/scope rồi gọi `repository.findById("o-202")`, Alice nhận đơn Bob dù API trả đúng JSON và HTTP 200. Đó là **Broken Object Level Authorization (BOLA)**, thường biểu hiện như **Insecure Direct Object Reference (IDOR)**: đổi ID để truy cập object ngoài quyền.

Bài thuộc chương **Phân quyền và an toàn**, module **INTEGRATION_API_REST** (resource/URI, HTTP methods/status, API contracts, phân trang, cache, idempotency, OpenAPI, bảo mật và Java/Spring tests). Mục tiêu: xây policy actor–action–object–tenant, scoped queries/updates, xử lý 401/403/404, ngăn rò list/batch/file/async và kiểm thử cross-user/tenant.

**UUID, JWT hợp lệ, HTTPS hay UI ẩn nút không thay authorization tại server.**

## 2. BOLA, IDOR và các lỗi liên quan

| Tình huống | Loại lỗi |
|---|---|
| Alice đổi `/orders/o-101` thành `/orders/o-202` để đọc đơn Bob | **BOLA/IDOR**: không kiểm tra quyền object |
| Người mua gọi `POST /admin/recalculate` | **Broken Function Level Authorization** |
| JSON có `{"ownerId":"bob","isAdmin":true}` được bind vào entity | **Property-level authorization/mass assignment** |
| Client đổi `X-Tenant-ID` để truy vấn tổ chức khác | **BOLA/tenant isolation** |

BOLA nhấn mạnh **quyết định quyền sai ở object boundary**; IDOR nhấn mạnh cách tham chiếu object bị thay. ID còn có thể nằm trong query, body, cursor, event stream, không chỉ path. **ID khó đoán không có nghĩa người biết ID được phép xem.**

## 3. Xác thực, scope và quyền object là ba bước

1. **Authentication:** token/session thực sự hợp lệ, đúng issuer/audience/expiry; biết caller là ai.
2. **Function authorization:** có scope/role `orders:read` hay `orders:write`.
3. **Object authorization:** resource thuộc tenant/owner, ACL hoặc quan hệ chia sẻ được cấp; operation có được thực hiện trong state hiện tại không?

Alice có scope đọc **không đồng nghĩa** được xem mọi đơn. Một policy minh họa:

```text
allow = authenticated(subject)
    AND hasPermission(subject, action)
    AND object.tenantId IN authorizedTenants(subject)
    AND (object.owner == subject
         OR hasValidShareGrant(subject, object)
         OR tenantScopedSupportRole(subject, object.tenantId))
```

Policy thật có thể là RBAC/ABAC/ReBAC/ACL, nhưng luôn phải dùng **identity và dữ liệu quan hệ đã tin cậy**. Không suy quyền chỉ từ URL, token scope chung hoặc tên controller.

## 4. Ranh giới tin cậy của tenant và subject

`orderId` là **đối tượng được yêu cầu**, không phải bằng chứng quyền. `tenantId`, `owner` hay `role` trong URL/body/header đều do client có thể sửa.

Với OAuth2 Resource Server/JWT, dùng `sub` và claims được issuer xác minh, kiểm tra `iss`/`aud`/expiry/signature, ánh xạ `scope` thành authorities. `tenant_id` chỉ đáng tin nếu token đúng nguồn và chính sách xác nhận subject được phép dùng tenant đó.

```http
GET /api/tenants/tenant-b/orders/o-202 HTTP/1.1
Authorization: Bearer <alice-token>
X-Tenant-ID: tenant-b
```

Nếu hệ thống cho user **chọn active tenant** từ path/header, phải **kiểm tra membership/ủy quyền cho tenant được chọn**; không được tin request header vì client đã đăng nhập. Với token có quyền nhiều tenants, áp policy tenant cụ thể cho từng operation.

## 5. Policy matrix trước khi triển khai

| Operation | Quyền chức năng | Điều kiện object |
|---|---|---|
| `GET /orders/{id}` | `orders:read` | Tenant + owner/grant |
| `GET /orders` | `orders:read` | Chỉ tập visible |
| `PATCH /orders/{id}` | `orders:write` | Tenant + editor + trạng thái |
| `DELETE /orders/{id}` | `orders:delete` | Tenant + quyền hủy |
| `GET /orders/{id}/files/{fileId}` | `orders:read` | File thuộc đúng đơn, quyền riêng nếu cần |
| `GET /orders/{id}/events` | `orders:read` | Stream thuộc object được xem |
| Export/batch | `orders:export` hoặc quyền tương ứng | Mỗi item và kết quả chỉ thuộc phạm vi |
| Tenant support | Role chuyên biệt | **Chỉ trong tenant được cấp quyền**, có audit |

`orders:read` **không phải** `read all tenants`. Với quyền hỗ trợ đặc biệt, cần giới hạn thời gian, tenant, người cấp và audit. Ownership/ACL thay đổi thì phải quyết định rõ thời điểm thu hồi quyền.

## 6. Đưa quyết định quyền vào truy vấn dữ liệu

Phản mẫu:

```java
@GetMapping("/{id}")
OrderView get(@PathVariable UUID id) {
    return repository.findById(id)
        .map(mapper::toView)
        .orElseThrow(NotFoundException::new);
}
```

Đoạn này chỉ tìm theo ID: ai có route hợp lệ cũng có thể đọc order. **Không sửa bằng cách kiểm tra ID có đủ dài hay là UUID v4**.

Thiết kế đơn giản nhất khi chỉ chủ sở hữu được xem:

```sql
SELECT id, tenant_id, owner_subject, status, total_minor
FROM orders
WHERE id = :orderId
  AND tenant_id = :trustedTenant
  AND owner_subject = :trustedSubject;
```

Truy vấn **scope ngay trong database**, nên object ngoài quyền trông giống “không tồn tại” với caller. Với policy phức tạp, điều kiện có thể bao gồm membership/ACL/tenant role theo quan hệ; tránh thêm một điều kiện `OR is_admin = true` rồi vô tình bỏ tenant boundary.

**Đặc biệt với list và COUNT:** cùng predicate quyền phải áp cho `SELECT` dữ liệu, count, `EXISTS`, search và aggregate. Nếu list lọc nhưng `totalElements` đếm toàn bộ tenant, metadata vẫn rò thông tin.

Một nguyên tắc giúp review code:

> Không tải object theo ID thuần ở public application flow rồi mới hy vọng mọi caller nhớ gọi authorization. Mỗi đường lấy/ghi object phải dùng scoped repository hoặc một authorization guard bắt buộc, được kiểm thử.

## 7. Spring Security: bảo vệ đường vào nhưng chưa đủ BOLA

Ví dụ Spring Boot 3.x/Spring Security 6.x resource server; cần dependencies và cấu hình JWT decoder kiểm tra issuer/audience theo triển khai:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:delete")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                Customizer.withDefaults()))
            .build();
    }
}
```

Các imports chính gồm `@Configuration`, `@Bean`, `@EnableMethodSecurity`, `SecurityFilterChain`, `HttpSecurity`, `SessionCreationPolicy`, `HttpMethod` và `Customizer` từ Spring tương ứng. **Cấu hình này chỉ minh họa read/patch/delete**, không khai đủ mọi route/role production.

Với API **chỉ** dùng bearer token không dựa vào cookie/session, cân nhắc cấu hình CSRF phù hợp với threat model. **Không tắt CSRF vô điều kiện** nếu browser gửi cookie tự động. JWT signature, issuer, audience, timestamp, key rotation và authority mapping đều phải được cấu hình/kiểm thử thực tế; một `SecurityFilterChain` trông hợp lệ **không chứng minh** token được thẩm định đúng.

`hasAuthority("SCOPE_orders:read")` mới kiểm tra **function permission**. Nó **không kiểm tra** `orderId` thuộc caller. Vì vậy cần bảo vệ object ở service/repository.

## 8. Mẫu Spring/JPA: scope tenant + owner ngay trong repository

Định nghĩa tối thiểu cho ví dụ (các getters/constructors/mapping DB được lược bỏ):

```java
@Entity
@Table(name = "orders")
class OrderEntity {
    @Id
    private UUID id;
    @Column(nullable = false)
    private String tenantId;
    @Column(nullable = false)
    private String ownerSubject;
    @Column(nullable = false)
    private String status;
    // getters, lifecycle và fields khác...
}

interface OrderRepository extends JpaRepository<OrderEntity, UUID> {

    Optional<OrderEntity> findByIdAndTenantIdAndOwnerSubject(
        UUID id, String tenantId, String ownerSubject);

    Slice<OrderEntity> findByTenantIdAndOwnerSubject(
        String tenantId, String ownerSubject, Pageable page);

    Optional<OrderEntity> findByIdAndTenantId(
        UUID id, String tenantId); // chỉ dùng sau policy tenant-wide
}
```

Cần imports Spring Data JPA (`JpaRepository`, `Slice`, `Pageable`), Jakarta Persistence (`@Entity`, `@Table`, `@Id`, `@Column`) và Java (`UUID`, `Optional`). Với `@Entity`, production cần constructor không tham số/khả năng truy cập JPA thích hợp và entity mapping hoàn chỉnh.

Phương thức `findByIdAndTenantIdAndOwnerSubject` tạo predicate của **đối tượng và caller** cùng một lúc. Tuy nhiên:

- Chỉ dùng `findByIdAndTenantId` cho quyền đọc **mọi đơn trong tenant** sau khi có policy cho phép rõ.
- Khi dữ liệu chia sẻ theo nhóm, thay điều kiện owner bằng ACL/relation query đã kiểm chứng.
- Dùng indexes theo access path (ví dụ tenant, owner, ID), giữ predicate bảo mật dù có tối ưu SQL.
- Không expose repository này trực tiếp cho controller hoặc để endpoint tự chọn phương thức “ít kiểm tra hơn”.

## 9. Service và controller: phân quyền từng request

Ví dụ code ghép từ Spring Security JWT, JPA và Spring MVC; trong thực tế các lớp nằm ở file riêng với imports/dependency đầy đủ:

```java
record OrderView(UUID id, String status) {}

@Service
class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public OrderView findVisible(UUID orderId, Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");
        String subject = jwt.getSubject();

        if (tenant == null || tenant.isBlank()
                || subject == null || subject.isBlank()) {
            throw new AccessDeniedException("Missing identity claims");
        }

        OrderEntity entity = repository
            .findByIdAndTenantIdAndOwnerSubject(orderId, tenant, subject)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"));

        return new OrderView(entity.getId(), entity.getStatus());
    }
}

@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) { this.orders = orders; }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable UUID id,
            @AuthenticationPrincipal Jwt jwt) {
        return ResponseEntity.ok(orders.findVisible(id, jwt));
    }
}
```

Imports chính ngoài phần trước: `@Service`, `@Transactional`, `@PreAuthorize`, `Jwt`, `AccessDeniedException`, `ResponseStatusException`, `HttpStatus`, `@RestController`, `@GetMapping`, `@PathVariable`, `@AuthenticationPrincipal` và `ResponseEntity`.

**Tại sao tách controller và service?** Controller biết HTTP request/path; service kiểm tra policy trước khi trả DTO. Cùng service phải được các entry points khác (scheduler, message handler, GraphQL, admin API) gọi theo **context/ủy quyền phù hợp**. Đừng bypass service bằng cách gọi repository trực tiếp ở một endpoint mới.

`@PreAuthorize` chỉ chạy khi method security được bật và lời gọi đi qua Spring proxy phù hợp; **self-invocation nội bộ cùng class có thể bỏ qua proxy advice**. `@PreAuthorize` kiểm tra scope, scoped query kiểm tra object. Khi có ủy quyền theo ACL phức tạp, có thể dùng `@orderAuth.canRead(authentication, orderId)` hoặc `AuthorizationManager`, nhưng vẫn nên hạn chế query/operation ở database theo tenant khi có thể.

## 10. HTTP 401, 403, 404 và việc che object existence

| Tình huống | Status hợp đồng tham khảo |
|---|---|
| Thiếu hoặc sai token | **401** từ authentication entry point |
| Có token nhưng thiếu `orders:read` | **403** |
| Có scope nhưng object không tồn tại | **404** |
| Có scope nhưng object của user/tenant khác | **404** khi che sự tồn tại |
| Được phép biết object nhưng không thực hiện action | **403** có thể phù hợp |
| State conflict hoặc `If-Match` sai sau khi đã có quyền | **409** / **412** |

Cho **cùng body/code 404** ở trường hợp ID không tồn tại và ngoài quyền, tránh `"Order belongs to Bob"`:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{"title":"Resource not found","status":404,
 "code":"RESOURCE_NOT_FOUND"}
```

`code` là Problem Details extension. 404 không loại bỏ timing/count/cache side channels. **Không bắt mọi exception thành 404** vì sẽ che 500. Security filters có thể trả 401/403 trước `@RestControllerAdvice`; integration tests phải kiểm tra cả chuỗi.

## 11. PATCH/DELETE: quyền đọc chưa đủ để sửa

Một user có thể đọc đơn đã hoàn thành nhưng không có quyền sửa tiền/tình trạng đơn. Mỗi **operation** cần policy riêng:

```text
canEdit =
    caller has "orders:write"
    AND order.tenantId == trustedTenant
    AND order.owner == trustedSubject
    AND order.status == "DRAFT"
    AND request updates only editable fields
```

Phản mẫu:

```java
OrderEntity order = repo.findById(orderId).orElseThrow();
order.setStatus(request.status()); // thiếu tenant, owner, state guard
repo.save(order);
```

Đúng hơn: dùng **scoped query trong transaction** và chỉ cập nhật fields cho phép. Khi trạng thái hoặc owner có thể thay đổi đồng thời, dùng optimistic locking (`@Version`), row lock hoặc **conditional update**:

```java
@Modifying
@Query("""
  update OrderEntity o
     set o.status = 'CANCELLED'
   where o.id = :id
     and o.tenantId = :tenant
     and o.ownerSubject = :subject
     and o.status = 'DRAFT'
""")
int cancelOwnedDraft(@Param("id") UUID id,
                     @Param("tenant") String tenant,
                     @Param("subject") String subject);
```

Truy vấn minh họa dùng JPQL; cần import `org.springframework.data.repository.query.Param` và transaction service ở phía gọi. Khi kết quả cập nhật bằng 0, có thể là ID không tồn tại, thiếu quyền **hoặc** trạng thái không còn DRAFT. Chọn lỗi chung 404 hoặc phân biệt 409 sau **một phép kiểm tra quyền an toàn**, tránh lộ sự tồn tại.

**JPA bulk update không tự áp `@Version` như entity-managed update.** Nếu cần optimistic concurrency, thêm version vào predicate và tăng version đúng cách, hoặc dùng entity lock/version mechanism phù hợp. Không coi `@Transactional` một mình là giải pháp mọi TOCTOU.

## 12. Resource lồng: kiểm tra cả cha lẫn con

Xét:

```http
GET /api/orders/o-101/attachments/f-202
GET /api/projects/p-01/tasks/t-99
GET /api/tenants/t-a/reports/r-77
```

Server phải kiểm tra **object con thuộc đúng object cha** và caller có quyền với quan hệ đó. Không chỉ xác thực order được xem rồi lấy file `f-202` bằng `findById` thuần.

```sql
SELECT a.*
FROM order_attachments a
JOIN orders o ON o.id = a.order_id
WHERE o.id = :orderId
  AND a.id = :attachmentId
  AND o.tenant_id = :trustedTenant
  AND o.owner_subject = :trustedSubject;
```

Một object con có thể có quyền riêng chặt hơn cha, ví dụ attachment chứa chứng từ tài chính chỉ dành cho kế toán. Khi đó policy phải xét **cả parent visibility, attachment scope và quyền tải nội dung**.

Đừng tin đường dẫn chứa cha/tenant ID là bằng chứng quan hệ; attacker có thể hoán đổi một trong hai ID. `Location` hoặc HATEOAS link trả từ API không thay thế authorization ở endpoint đích.


## 13. List, search, count và pagination cũng phải scoped

`GET /orders` có thể lộ hàng trăm object nếu query chỉ lọc status mà quên caller. Ví dụ:

```java
@Transactional(readOnly = true)
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public Slice<OrderView> listVisible(Jwt jwt, Pageable pageable) {
    String tenant = requireTrustedTenant(jwt);
    String subject = requireSubject(jwt);
    return repository.findByTenantIdAndOwnerSubject(
            tenant, subject, pageable)
        .map(e -> new OrderView(e.getId(), e.getStatus()));
}
```

`requireTrustedTenant/requireSubject` là helpers kiểm tra claims; không lấy identity từ query. Thêm filter/sort vào **scoped database query**, không load toàn bộ rồi lọc Java.

Áp cùng predicate với **search, total count, exists, aggregates, export, report, pagination và cache**. Nếu `totalElements` đếm đơn ngoài quyền, metadata vẫn rò. `Slice` tránh COUNT khi không cần total, nhưng **không tự enforce quyền**. Cache key/invalidation phải phân biệt tenant/subject.

## 14. Batch và nhiều ID trong một body

```http
POST /api/orders/batch-read HTTP/1.1
Content-Type: application/json

{"ids":["o-101","o-202","o-303"]}
```

Giả sử chỉ `o-101` thuộc Alice. **Không kiểm tra ID đầu rồi gọi `findAllById(ids)`**; mọi item đều cần object-level decision.

Chọn hợp đồng **all-or-nothing** (từ chối batch nếu có item ngoài quyền) hoặc **partial results** (chỉ trả visible items). Nếu trả status theo từng ID, tránh tiết lộ ID ẩn có tồn tại. Giới hạn số ID/response size, tenant scope và concurrency. Với bulk write, xác định atomicity/partial commit, idempotency, audit và transaction policy. Một lần check quyền trước transaction không giải quyết race với ACL thay đổi.

## 15. POST/PUT và bảo vệ fields đặc quyền

Endpoint tạo mới cũng liên quan object-level authorization. Client có thể gửi:

```json
{
  "customerId":"c-42",
  "tenantId":"tenant-b",
  "ownerSubject":"bob",
  "status":"APPROVED",
  "items":[{"sku":"SKU-1","quantity":2}]
}
```

Nếu server bind trực tiếp JSON vào entity rồi `save`, caller có thể tạo resource ở tenant khác hoặc tự cấp trạng thái đặc quyền. **Không cho client điều khiển owner/tenant/role/status nội bộ** chỉ vì property tồn tại trong database.

Thiết kế DTO whitelist:

```java
record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<@Valid OrderLineRequest> items
) {}

record OrderLineRequest(
    @NotBlank String sku,
    @Positive int quantity
) {}
```

Ở service: lấy tenant và subject **từ security context đã xác minh**, kiểm tra caller được phép tạo đơn cho `customerId`, rồi mới gắn owner/tenant và khởi tạo state do domain quyết định. `@Valid` chỉ kiểm tra dữ liệu hợp lệ; nó **không xác nhận caller có quyền** với `customerId`.

Với PUT/PATCH, dùng DTO khác chỉ chứa fields chỉnh sửa được; kiểm tra owner/scope và state transition; không dùng generic reflection mapper cập nhật mọi property từ JSON. Đây là cách giảm nguy cơ **property-level authorization** đồng thời giữ tính nhất quán với object-level checks.

## 16. Async job, export, SSE và signed downloads

`POST /report-jobs` có thể nhận nhiều order IDs, sau đó worker chạy vài phút. **Bảo vệ cả lúc submit lẫn đường đọc kết quả**:

- Kiểm tra quyền trên từng order khi submit; không tin job payload tự khai quyền.
- `GET /report-jobs/{id}` và `/download` kiểm tra chủ job/tenant và policy với dữ liệu kết quả.
- SSE `/events` authorize subscription, định nghĩa TTL/reauthorization khi quyền bị thu hồi.
- Link object storage có chữ ký là **capability**: tạo sau authorize, scope đúng file và TTL ngắn.
- Nếu job được chạy tiếp sau khi user mất quyền, phải có quy tắc **authorization snapshot vs recheck** được công bố; không suy từ HTTP connection lifetime.

Một job ID ngẫu nhiên hay signed URL khó đoán **không thay thế** quyền truy cập ở nơi phát hành/tiêu thụ kết quả.

## 17. TOCTOU: kiểm tra quyền rồi ghi có thể quá muộn

```java
if (aclService.canWrite(user, orderId)) {
    repository.update(orderId, request); // ACL/owner/state có thể đã đổi
}
```

Giữa check và update có thể xảy ra chuyển owner, thu hồi grant, thay trạng thái. Giảm rủi ro bằng:

- **Conditional update** có `WHERE` tenant/owner/state và kiểm tra affected rows.
- Transaction + lock/version khi cần đồng bộ nhiều bảng/ACL.
- `@Version`/`If-Match` tránh lost update, **không thay authorization**.
- Nếu quyền nằm ở service khác, xác định consistency/revocation SLA; không assume check HTTP trước đó bảo đảm commit.
- Không cache `allow` vô thời hạn; dùng scope, TTL/invalidation thích hợp.

Mục tiêu là quyền còn đúng **tại thời điểm thực thi side effect** khi policy yêu cầu.

## 18. Cache, metadata và chống enumeration

Dùng chung 404 cho ID không tồn tại/ngoài quyền nhưng không được rò qua đường phụ:

- Error code/body không ghi owner khác; logs nội bộ phải có bảo vệ.
- `Cache-Control: private/no-store` theo mức nhạy cảm, CDN không chia response giữa tenants.
- `ETag`/`If-None-Match`: **kiểm tra quyền trước khi trả 304**.
- `HEAD`, link, count, pagination metadata và export không tiết lộ object ẩn.
- Rate limits/audit giúp giảm đoán ID nhưng **không thay** object authorization.

Giữ policy thống nhất qua GET/HEAD, conditional requests và các representation khác.

## 19. Unit tests cho policy: quyết định quyền phải rõ

Tách policy thành bảng test có cả trường hợp cho phép lẫn từ chối:

| Caller | Object | Operation | Kỳ vọng |
|---|---|---|---|
| Alice có `orders:read` | Order Alice, tenant A | GET | Allow |
| Alice có `orders:read` | Order Bob, tenant A | GET | Deny |
| Alice có `orders:read` | Order Alice, tenant B | GET | Deny |
| Alice thiếu `orders:write` | Order Alice, tenant A | PATCH | Deny |
| Alice có `orders:write` | Order Alice, `DRAFT` | PATCH | Allow nếu field hợp lệ |
| Alice có `orders:write` | Order Alice, `PAID` | PATCH | Deny hoặc domain conflict |
| Tenant support có quyền `read:any` | Order Bob cùng tenant | GET | Allow theo policy/audit |
| Tenant support có `read:any` | Order tenant khác | GET | Deny |
| Token không có tenant claim bắt buộc | Bất kỳ | GET | Deny |

Unit tests có thể gọi một `OrderAuthorizationPolicy` thuần với principal, tenant, ACL và state giả lập. Nếu policy dùng DB, kiểm tra query phải bao gồm tenant/owner và test cả trường hợp ACL bị revoke. **Không chỉ viết tests cho owner thành công:** test quan trọng nhất là **cùng một token, đổi object ID** mà không truy cập được dữ liệu người khác.

Tránh tự tạo `Authentication` có quyền admin trong mọi fixture: nó vô tình làm test “pass” dù thiếu kiểm tra ownership.

## 20. MockMvc: thử BOLA qua HTTP cùng Spring Security

Ví dụ HTTP integration test với Spring Boot/Spring Security test (Spring 6.x). Giả định fixture có `aliceOrderId`, `bobOrderId` cùng tenant A và `tenantBOrderId` thuộc tenant B:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void aliceCannotReadBobsOrder() throws Exception {
    mockMvc.perform(get("/api/orders/{id}", bobOrderId)
            .with(jwt()
                .jwt(token -> token
                    .subject("alice")
                    .claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:read"))))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.id").doesNotExist());
}

@Test
void aliceCanReadOwnOrder() throws Exception {
    mockMvc.perform(get("/api/orders/{id}", aliceOrderId)
            .with(jwt()
                .jwt(token -> token
                    .subject("alice")
                    .claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(aliceOrderId.toString()));
}
```

Các method trên là **fragment test**, không phải class độc lập: cần `@SpringBootTest`, `@AutoConfigureMockMvc` hoặc test slice có security filter, `MockMvc` được inject, và fixture dữ liệu gắn đúng tenant/owner. `jwt()` trong `spring-security-test` **giả lập security authentication**, không thực sự xác minh chữ ký JWT. Bổ sung integration tests token thật/decoder để kiểm tra issuer, audience, scope mapping, expiry và CSRF/cookie policy thực tế.

Cần ít nhất thêm các tests: token thiếu (401), thiếu scope (403), tenant B (404), PATCH đổi owner/tenant (400/403 theo hợp đồng), child attachment khác cha (404), list chỉ chứa Alice, count không lộ Bob, batch chứa Bob, concurrent cancel/update, cache/CDN không dùng lại body của tenant khác.

## 21. Phản mẫu code review cần chặn

| Phản mẫu | Sửa bằng |
|---|---|
| Chỉ kiểm JWT hoặc `isAuthenticated()` | Scope **và** object policy |
| Role admin không giới hạn tenant | Tenant-scoped support role + audit |
| Controller gọi `findById(id)` | Scoped query/mandatory guard |
| Tin `X-Tenant-ID` hoặc `ownerId` trong body | Trusted identity + membership |
| UUID khó đoán hoặc UI ẩn nút | Server-side authorization |
| Chỉ check parent, không check child | Relation/ACL query đúng cả hai |
| List lọc nhưng count/export không lọc | Dùng chung authorization predicate |
| Check ACL rồi update ID thuần | Conditional update/transaction |
| Bắt mọi exception thành 404 | Phân biệt 4xx với 500 |
| Cache theo ID bỏ qua tenant/user | Scoped cache và revocation |
| Async job submit có auth, download public | Recheck job/result/download |
| Chỉ test owner thành công | Negative tests cross-user/tenant |

## 22. Audit và phản ứng khi có dấu hiệu BOLA

Ghi denied decisions có kiểm soát: subject pseudonym, tenant, operation, resource type, decision, reason code, correlation ID, timestamp; **không log raw token/PII**. Đo bất thường 401/403/404, nhiều ID liên tiếp, thử tenant khác và tăng đột biến batch/download. Metrics không nên dùng full ID làm label cardinality cao.

Khi phát hiện, giới hạn abuse, truy vết những entry points dùng chung repository, kiểm tra CDN/cache/export/log rò rỉ và thêm **negative regression tests**. Có thể trả 404 cho caller nhưng lưu reason `NOT_VISIBLE` trong audit bảo mật.

## 23. Bài thực hành: đóng lỗi BOLA trong hệ thống Orders

### Code ban đầu

```java
@GetMapping("/api/orders/{id}")
public OrderEntity get(@PathVariable UUID id) {
    return repository.findById(id).orElseThrow();
}

@PatchMapping("/api/orders/{id}")
public OrderEntity patch(@PathVariable UUID id,
                         @RequestBody OrderEntity update) {
    OrderEntity order = repository.findById(id).orElseThrow();
    order.setStatus(update.getStatus());
    return repository.save(order);
}
```

**Bối cảnh:** Alice và Bob cùng tenant A nhưng chỉ được đọc/sửa đơn của mình; Carol thuộc tenant B. Một account hỗ trợ có quyền xem mọi đơn **trong tenant được cấp quyền**, không được xem tenant khác.

**Yêu cầu thực hành:**

1. Viết threat model BOLA/IDOR cho GET, PATCH, list, attachment và export; nêu resource identifiers có thể bị thay ở path/query/body.
2. Thiết kế policy matrix cho owner, tenant support, read-only và write permission; chọn 401/403/404 sao cho không rò existence.
3. Thay `findById` bằng scoped query JPA; lấy `sub`/tenant từ principal đáng tin, không từ JSON hay `X-Tenant-ID` tự khai.
4. Viết Spring Security filter rules và `@PreAuthorize` phù hợp; chứng minh role/scope không tự enforce ownership.
5. Sửa PATCH: dùng DTO whitelist, ràng buộc owner/tenant/state, xử lý concurrency `@Version` hoặc conditional update.
6. Bảo vệ `GET /orders/{id}/attachments/{fileId}` bằng JOIN đúng quan hệ cha–con.
7. Sửa list/count/search/export để cùng dùng predicate quyền; limit batch size và số stream/job đang mở.
8. Viết MockMvc tests cho Alice→Bob, Alice→Carol, support→tenant B, thiếu token/scope, UUID khó đoán, file khác cha và count leak.
9. Thử hai request PATCH đồng thời trong lúc ownership bị thay đổi; xác định expected outcomes.
10. Rà soát cache, signed download links, logs/metrics và policy khi quyền bị thu hồi.

### Gợi ý nghiệm thu

Với fixture cùng tenant A, `GET /orders/{bobId}` từ token Alice có `orders:read` phải **không trả bất kỳ trường của Bob**; nếu policy che existence thì 404 giống trường hợp ID không có. PATCH không được ghi dữ liệu của Bob; count/list/export cũng chỉ chứa phạm vi Alice. Với token support, chỉ tenant được cấp quyền xuất hiện. Các tests nên chạy qua **Spring Security filter chain và DB thực** ở bước integration, không chỉ mock policy object.

## 24. Checklist phát hành

- [ ] Policy actor–action–object–tenant–state có cho mỗi operation.
- [ ] JWT đúng issuer/audience/expiry; scope/role/membership được test.
- [ ] Tenant/subject lấy từ identity đáng tin; active tenant có guard.
- [ ] GET và nested resource dùng scoped query/ACL.
- [ ] PATCH/DELETE kiểm tra quyền trước write, chống TOCTOU/unsafe fields.
- [ ] List/count/search/batch/export/caches cùng phạm vi dữ liệu được xem.
- [ ] Error 401/403/404/409/412 không tiết lộ object ẩn.
- [ ] Async/SSE/download, signed URLs và revocation policy được kiểm tra.
- [ ] MockMvc + DB/security integration tests cover cross-user/tenant, token và concurrency.
- [ ] Audit/logs/rate limits không lộ PII hoặc che lỗi quyền.

## 25. Kết luận

**BOLA/IDOR xuất hiện khi API cho phép thao tác trên object chỉ dựa vào ID hoặc vào quyền chức năng chung**, thiếu quyết định “caller này có quyền với chính resource này không?”. JWT, HTTPS, UUID, `@PreAuthorize` theo scope và HTTP status chính xác là cần thiết nhưng **không thay thế authorization ở object boundary**.

Thiết kế vững chắc kết hợp **principal đã xác thực**, tenant/owner/ACL policy, **truy vấn và cập nhật có scope**, DTO không cho sửa trường đặc quyền, phản hồi 401/403/404 không rò thông tin và kiểm thử chéo user/tenant ở mọi endpoint, kể cả list, file, batch, cache và async job. Khi quyền là điều kiện bắt buộc của mọi đường đọc/ghi, REST API vừa tuân HTTP contract vừa bảo vệ dữ liệu đúng đối tượng.


