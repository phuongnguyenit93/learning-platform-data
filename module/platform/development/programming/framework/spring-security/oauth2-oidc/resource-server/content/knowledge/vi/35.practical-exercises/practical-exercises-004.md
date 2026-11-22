# Kiểm tra chủ sở hữu và tenant ở lớp nghiệp vụ

Trong ứng dụng multi-tenant, xác thực JWT thành công và có scope phù hợp vẫn chưa đủ để cho phép người dùng đọc hoặc thay đổi mọi tài nguyên. API phải kiểm tra **người gọi có phải chủ sở hữu tài nguyên hay không** và **tài nguyên có thuộc tenant mà người gọi được phép truy cập hay không**. Các quyết định này thuộc lớp nghiệp vụ vì chúng phụ thuộc vào quan hệ giữa user, tenant và dữ liệu cụ thể trong hệ thống.

Một lỗi phổ biến là chỉ kiểm tra quyền ở URL, chẳng hạn `SCOPE_orders.read`, rồi truy vấn đơn hàng theo ID do client gửi. Người dùng có thể thay ID trong path để đọc đơn hàng của người khác hoặc của tenant khác. Đây là dạng lỗi object-level authorization thường được gọi là IDOR/BOLA. Scope cho biết loại thao tác được phép; ownership và tenant policy xác định thao tác đó được áp dụng lên **đối tượng nào**.

Bài này xây dựng cách kiểm tra theo nhiều lớp: lấy identity từ `Authentication` đã được Spring Security xác minh, áp dụng tenant context, truy vấn dữ liệu có tenant constraint, kiểm tra ownership trong service/domain policy, bảo vệ cả read/write/delete, xử lý concurrency và kiểm thử bằng MockMvc cùng service/repository tests.

> **Ngữ cảnh minh họa:** Orders API dùng Spring Boot 3.x và Spring Security 6.x. JWT đã được Resource Server xác minh chữ ký, issuer, audience và thời hạn. Token cung cấp subject `sub`, tenant claim `tenant_id` và scope như `orders.read` hoặc `orders.write`. Cơ sở dữ liệu có bảng `orders` với `id`, `tenant_id` và `owner_subject`. Các giá trị này là ví dụ; ứng dụng cần ánh xạ theo contract token và schema thực tế.

## 1. Authentication, scope, ownership và tenant là các quyết định khác nhau

Một request truy cập tài nguyên cần qua nhiều câu hỏi:

1. **Authentication:** token có hợp lệ và xác định được principal không?
2. **Coarse-grained authorization:** principal có scope/role cho thao tác này không?
3. **Tenant authorization:** principal có quyền trong tenant chứa tài nguyên không?
4. **Object-level authorization:** principal có phải owner hoặc được chia sẻ/quản lý tài nguyên đó không?
5. **Business policy:** trạng thái tài nguyên có cho phép thao tác vào thời điểm này không?

Ví dụ, `alice` có `SCOPE_orders.read` và `tenant_id=tenant-a`. Alice gửi:

~~~http
GET /api/orders/order-42
Authorization: Bearer <access-token>
~~~

Chỉ scope `orders.read` không chứng minh `order-42` thuộc Alice hoặc tenant-a. Service phải kiểm tra bản ghi tương ứng trước khi trả dữ liệu.

| Kiểm tra | Ví dụ | Trả lời câu hỏi |
|---|---|---|
| Authentication | JWT signature, issuer, exp | Ai đang gọi? |
| Scope | `SCOPE_orders.read` | Có được đọc loại tài nguyên này không? |
| Tenant | `tenant_id=tenant-a` | Có thuộc phạm vi tenant được phép không? |
| Ownership | `owner_subject=alice` | Có được truy cập object cụ thể không? |
| Business state | Order chưa archived/cancelled | Trạng thái hiện tại có cho phép thao tác không? |

Không nên gộp các kiểm tra này thành một `isAuthenticated()` hoặc một scope duy nhất.

## 2. Lấy subject và tenant từ Authentication đã xác minh

Với JWT Resource Server, Spring Security tạo `JwtAuthenticationToken`. Controller có thể nhận `Jwt` bằng `@AuthenticationPrincipal`:

~~~java
@GetMapping("/api/orders/{orderId}")
public OrderResponse getOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    String tenantId = jwt.getClaimAsString("tenant_id");

    return orderService.getOrder(orderId, subject, tenantId);
}
~~~

`sub` và `tenant_id` phải đến từ JWT đã được decoder xác minh. Không lấy subject/tenant từ request body, query parameter hoặc header tùy ý do client gửi rồi dùng trực tiếp làm identity.

### 2.1. Không tin tenantId từ URL như tenant context

Endpoint có thể có tenant trong path:

~~~http
GET /api/tenants/tenant-a/orders/order-42
~~~

Path variable chỉ là đối tượng client muốn truy cập. Nó không chứng minh client được phép vào tenant đó. So sánh tenant trong path với tenant context đã xác thực, hoặc dùng membership policy để xác định user được phép hoạt động trong tenant được chọn.

~~~java
@GetMapping("/api/tenants/{tenantId}/orders/{orderId}")
public OrderResponse getTenantOrder(
        @PathVariable String tenantId,
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    String tokenTenant = jwt.getClaimAsString("tenant_id");

    if (!tenantId.equals(tokenTenant)) {
        throw new AccessDeniedException("Tenant access denied");
    }

    return orderService.getOrder(orderId, subject, tenantId);
}
~~~

Đoạn code này phù hợp với mô hình token chỉ đại diện một tenant. Nếu user có membership ở nhiều tenant, claim `tenant_id` có thể không phải nguồn context duy nhất; cần kiểm tra membership qua một policy/service tin cậy.

### 2.2. Principal name không nhất thiết là email hoặc username

Dùng claim `sub` như stable subject identifier nếu issuer contract quy định như vậy. Không giả định email là duy nhất hoặc không đổi. Trong hệ thống có nhiều issuer, subject có thể chỉ duy nhất trong phạm vi issuer; identity key khi đó nên bao gồm issuer cùng subject.

### 2.3. Thiếu claim phải được xử lý an toàn

Nếu tenant claim là bắt buộc nhưng token thiếu hoặc sai kiểu, không mặc định tenant chung hoặc dùng tenant từ client input. Từ chối truy cập theo policy và ghi nhận lỗi token/domain context phù hợp.

~~~java
private String requiredTenant(Jwt jwt) {
    String tenantId = jwt.getClaimAsString("tenant_id");

    if (tenantId == null || tenantId.isBlank()) {
        throw new AccessDeniedException("Tenant context is missing");
    }

    return tenantId;
}
~~~

Trong production, exception mapping cần nhất quán. Nếu claim thiếu chứng tỏ token không đáp ứng access-token contract, có thể coi đó là authentication/token validation failure bằng custom validator; nếu tenant là membership context nghiệp vụ, policy service có thể từ chối authorization.

## 3. Thiết kế dữ liệu có tenant và owner rõ ràng

Một bảng đơn hàng tối thiểu có thể chứa:

~~~sql
CREATE TABLE orders (
    id              VARCHAR(64) PRIMARY KEY,
    tenant_id       VARCHAR(64) NOT NULL,
    owner_subject   VARCHAR(255) NOT NULL,
    status          VARCHAR(32) NOT NULL,
    total_amount    DECIMAL(19, 2) NOT NULL,
    created_at      TIMESTAMP NOT NULL
);

CREATE INDEX idx_orders_tenant_owner
    ON orders (tenant_id, owner_subject);

CREATE INDEX idx_orders_tenant_id
    ON orders (tenant_id, id);
~~~

Các cột `tenant_id` và `owner_subject` là dữ liệu authorization quan trọng, không chỉ metadata hiển thị. Cần kiểm soát việc tạo/cập nhật chúng để client không tự chuyển resource sang tenant hoặc owner khác.

### 3.1. Tenant phải là một phần của query

Tránh truy vấn chỉ theo ID:

~~~java
Optional<Order> findById(String id);
~~~

Với dữ liệu tenant-scoped, ưu tiên query có tenant predicate:

~~~java
Optional<Order> findByIdAndTenantId(String id, String tenantId);
~~~

Nếu endpoint chỉ cho owner truy cập:

~~~java
Optional<Order> findByIdAndTenantIdAndOwnerSubject(
    String id,
    String tenantId,
    String ownerSubject
);
~~~

Database query giới hạn tập bản ghi ngay từ đầu, giảm nguy cơ một đường code quên kiểm tra sau khi load entity.

### 3.2. Repository method thể hiện policy

Ví dụ Spring Data JPA:

~~~java
public interface OrderRepository extends JpaRepository<Order, String> {

    Optional<Order> findByIdAndTenantId(
        String id,
        String tenantId
    );

    Optional<Order> findByIdAndTenantIdAndOwnerSubject(
        String id,
        String tenantId,
        String ownerSubject
    );

    Page<Order> findAllByTenantId(
        String tenantId,
        Pageable pageable
    );

    Page<Order> findAllByTenantIdAndOwnerSubject(
        String tenantId,
        String ownerSubject,
        Pageable pageable
    );
}
~~~

Đặt tên method làm rõ query scope. Với repository dùng custom SQL/QueryDSL/specification, tenant predicate vẫn phải được áp dụng cho mọi đường đọc/ghi.

### 3.3. Tenant filter toàn cục có thể hỗ trợ nhưng không thay domain policy

Hibernate filter, database row-level security hoặc tenant-aware datasource có thể tạo lớp bảo vệ bổ sung. Tuy nhiên, chúng cần được cấu hình đúng cho mọi transaction/connection và không tự giải quyết ownership. Một user có thể được phép trong tenant nhưng vẫn không được đọc object của user khác.

Dùng defense in depth: tenant-scoped query ở repository/domain layer và database controls khi phù hợp. Đừng dựa vào một filter ngầm mà không có test chứng minh filter luôn bật.

## 4. Viết service kiểm tra tenant và ownership

Service là nơi phù hợp để kết hợp repository lookup với business policy, vì nhiều controller có thể gọi cùng một nghiệp vụ.

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderMapper orderMapper;

    @Transactional(readOnly = true)
    public OrderResponse getOrder(
            String orderId,
            String subject,
            String tenantId) {

        Order order = orderRepository
            .findByIdAndTenantIdAndOwnerSubject(
                orderId,
                tenantId,
                subject
            )
            .orElseThrow(ResourceNotFoundException::new);

        return orderMapper.toResponse(order);
    }
}
~~~

Query đã ràng buộc cả ID, tenant và owner. Một bản ghi thuộc tenant khác hoặc owner khác không được trả về.

### 4.1. 404 hay 403 khi object không thuộc caller?

Có hai API behavior thường gặp:

- Trả `404 Not Found` cho cả object không tồn tại và object caller không được phép nhìn thấy. Cách này tránh tiết lộ resource ID có tồn tại hay không.
- Trả `403 Forbidden` khi caller được phép biết resource tồn tại nhưng không có quyền thực hiện hành động.

Chọn theo threat model và API contract. Nếu muốn chống resource enumeration, query scoped có thể trả cùng một kết quả not-found cho cả hai trường hợp. Không để response body, timing hoặc log phía client tiết lộ thông tin ngoài chủ đích.

### 4.2. Khi tenant đúng nhưng owner khác

Một số vai trò có thể đọc mọi đơn hàng trong tenant, trong khi user thông thường chỉ đọc đơn của mình. Khi đó policy phải phân biệt rõ:

~~~java
public OrderResponse getOrder(String orderId, Actor actor) {
    Order order = orderRepository
        .findByIdAndTenantId(orderId, actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    boolean isOwner = order.getOwnerSubject()
        .equals(actor.subject());

    boolean canReadAll = actor.hasAuthority("ROLE_TENANT_ORDER_ADMIN");

    if (!isOwner && !canReadAll) {
        throw new AccessDeniedException("Order access denied");
    }

    return orderMapper.toResponse(order);
}
~~~

Ví dụ này giả định `Actor` đã được xây dựng từ authenticated principal và authorities. Không tạo `Actor` từ request body do client kiểm soát.

### 4.3. Policy nên là code có tên và có thể kiểm thử

Khi quy tắc phức tạp, tách thành component:

~~~java
@Component
public class OrderAccessPolicy {

    public boolean canRead(Order order, Actor actor) {
        if (!order.getTenantId().equals(actor.tenantId())) {
            return false;
        }

        return order.getOwnerSubject().equals(actor.subject())
            || actor.hasAuthority("ROLE_TENANT_ORDER_ADMIN");
    }

    public boolean canModify(Order order, Actor actor) {
        return order.getTenantId().equals(actor.tenantId())
            && (
                order.getOwnerSubject().equals(actor.subject())
                || actor.hasAuthority("ROLE_TENANT_ORDER_ADMIN")
            )
            && order.getStatus() != OrderStatus.CANCELLED;
    }
}
~~~

Policy có thể được unit test với các tổ hợp owner, tenant, role và trạng thái. Service vẫn phải lấy entity từ repository an toàn trước khi gọi policy.

## 5. Không cho client tự gán owner hoặc tenant

Khi tạo order, owner và tenant phải lấy từ authenticated actor/context:

~~~java
@PostMapping("/api/orders")
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    Actor actor = actorFactory.from(jwt);
    return orderService.createOrder(request, actor);
}
~~~

~~~java
@Transactional
public OrderResponse createOrder(
        CreateOrderRequest request,
        Actor actor) {

    Order order = new Order();
    order.setId(idGenerator.nextId());
    order.setTenantId(actor.tenantId());
    order.setOwnerSubject(actor.subject());
    order.setStatus(OrderStatus.PENDING);
    order.setTotalAmount(request.totalAmount());

    return orderMapper.toResponse(orderRepository.save(order));
}
~~~

`CreateOrderRequest` không nên cho phép caller set `tenantId`, `ownerSubject`, `createdBy` hoặc các trường security-sensitive. Nếu DTO có những trường này vì tương thích, server phải bỏ qua hoặc từ chối chúng; không bind trực tiếp request body vào entity.

### 5.1. Cẩn thận mass assignment

Tránh:

~~~java
Order order = objectMapper.convertValue(request, Order.class);
orderRepository.save(order);
~~~

Cách map toàn bộ request sang entity có thể cho phép client ghi vào `tenantId`, `ownerSubject`, `status` hoặc các thuộc tính nội bộ. Dùng DTO allowlist và gán trường server-controlled rõ ràng.

## 6. Kiểm tra ownership cho update

Update phải load object trong tenant context và xác nhận actor có quyền sửa trước khi áp dụng thay đổi.

~~~java
@Transactional
public OrderResponse updateOrder(
        String orderId,
        UpdateOrderRequest request,
        Actor actor) {

    Order order = orderRepository
        .findByIdAndTenantId(orderId, actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    if (!orderAccessPolicy.canModify(order, actor)) {
        throw new AccessDeniedException("Order update denied");
    }

    order.setDeliveryAddress(request.deliveryAddress());
    order.setCustomerNote(request.customerNote());

    return orderMapper.toResponse(order);
}
~~~

Không copy toàn bộ DTO vào entity. Chỉ cập nhật các field mà use case cho phép. Trường `tenantId`, `ownerSubject`, `createdBy`, `createdAt` và security status cần có luồng nghiệp vụ riêng.

### 6.1. Cập nhật có điều kiện ngay trong SQL

Với thao tác đơn giản, có thể dùng update query ràng buộc tenant/owner:

~~~java
@Modifying
@Query("""
    update Order o
       set o.customerNote = :note
     where o.id = :orderId
       and o.tenantId = :tenantId
       and o.ownerSubject = :subject
    """)
int updateNoteIfOwned(
    String orderId,
    String tenantId,
    String subject,
    String note
);
~~~

Nếu số dòng cập nhật là 0, resource không tồn tại hoặc actor không có quyền theo query. Cách này giúp predicate authorization và mutation diễn ra trong cùng câu SQL. Với business policy phức tạp, cần load và kiểm tra entity trong transaction rồi vẫn dùng optimistic locking/conditional update phù hợp.

### 6.2. Ownership có thể thay đổi trong lifecycle

Nếu order có thể được chuyển owner, reassigned hoặc chuyển tenant, cần một use case riêng có authorization mạnh hơn. Không cho update thông thường thay đổi `ownerSubject` hoặc `tenantId`.

Ghi audit actor, old owner, new owner, tenant và lý do. Chỉ cho phép chuyển tenant khi business rule cho phép và có kiểm tra quyền ở cả tenant nguồn lẫn tenant đích.

## 7. Kiểm tra ownership cho delete

Delete cũng cần tenant/owner predicate:

~~~java
@Transactional
public void deleteOrder(String orderId, Actor actor) {
    Order order = orderRepository
        .findByIdAndTenantId(orderId, actor.tenantId())
        .orElseThrow(ResourceNotFoundException::new);

    if (!orderAccessPolicy.canModify(order, actor)) {
        throw new AccessDeniedException("Order deletion denied");
    }

    orderRepository.delete(order);
}
~~~

Nếu delete là soft delete, query list/detail phải luôn lọc bản ghi đã xóa theo policy. Nếu có cascade, kiểm tra child resources cũng thuộc cùng tenant và không thể bị lợi dụng để xóa dữ liệu ngoài phạm vi.

Với bulk delete, không load danh sách ID rồi chỉ kiểm tra một vài item. Dùng tenant-scoped query và xác định hành vi khi danh sách chứa object không được phép: từ chối toàn bộ request hoặc chỉ xử lý các object hợp lệ theo contract rõ ràng.

## 8. Bảo vệ list, search, count và export

IDOR không chỉ xảy ra ở endpoint lấy một object. List/search/count/export có thể làm lộ dữ liệu tenant nếu query không giới hạn.

Không dùng:

~~~java
List<Order> findAll(Pageable pageable);
~~~

Ưu tiên:

~~~java
Page<Order> findAllByTenantId(
    String tenantId,
    Pageable pageable
);
~~~

Nếu user chỉ được thấy order của mình:

~~~java
Page<Order> findAllByTenantIdAndOwnerSubject(
    String tenantId,
    String subject,
    Pageable pageable
);
~~~

Mọi truy vấn phụ cũng cần tenant scope:

- Count theo status.
- Dashboard aggregates.
- Search index query.
- CSV/PDF export.
- Report và analytics.
- Background job nhận tenant ID.
- Download file hoặc attachment gắn với order.

Một endpoint list có tenant filter nhưng endpoint export dùng repository `findAll()` vẫn là lỗ hổng object-level authorization.

### 8.1. Pagination không thay thế authorization

Không lọc tenant sau khi lấy page từ database. Cách đó có thể làm tổng số, số trang, thứ tự hoặc dữ liệu trả về tiết lộ thông tin cross-tenant và khiến pagination sai. Tenant/owner predicate phải nằm trong query trước khi phân trang.

### 8.2. Search index cần tenant filter bắt buộc

Nếu dùng Elasticsearch/OpenSearch hoặc search service, truyền tenant context từ authenticated actor và bắt buộc filter ở server-side query builder. Không nhận nguyên query DSL từ client mà không thêm điều kiện tenant. Cần test cả aggregation, facets và suggestion endpoint.

## 9. Kiểm tra quyền ở method security

Spring Method Security có thể bảo vệ service method bằng `@PreAuthorize`:

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderResponse getOrder(String orderId, Actor actor) {
        return orderService.getOrder(orderId, actor);
    }
}
~~~

Annotation này kiểm tra scope ở mức thao tác. Nó chưa tự chứng minh `orderId` thuộc actor. Service/domain policy vẫn phải kiểm tra object-level access.

### 9.1. Gọi policy bean từ @PreAuthorize

Có thể gọi bean trong SpEL:

~~~java
@PreAuthorize("@orderAccessPolicy.canReadById(#orderId, authentication)")
public OrderResponse getOrder(String orderId) {
    // ...
}
~~~

Method `canReadById` cần nhận authenticated principal và query theo tenant/owner. Cần cân nhắc query lặp lại khi service sau đó tải entity lần nữa. Với rule phức tạp, thường dễ đọc hơn khi service tải entity một lần trong tenant scope rồi gọi policy trên entity.

### 9.2. Method security cần Spring proxy

`@PreAuthorize` được thực thi qua Spring AOP proxy. Gọi method qua Spring-managed bean. Self-invocation trong cùng object có thể bỏ qua proxy và làm annotation không được áp dụng. Unit test tạo service bằng `new` cũng không chứng minh method security đang hoạt động.

Dùng MockMvc hoặc integration test inject bean qua Spring context để kiểm tra boundary thật.

## 10. Dùng Actor object để truyền identity đã xác thực

Không nên truyền rời rạc subject và tenant qua nhiều lớp rồi có nguy cơ đổi thứ tự tham số. Tạo một context bất biến:

~~~java
public record Actor(
    String issuer,
    String subject,
    String tenantId,
    Set<String> authorities
) {
    public boolean hasAuthority(String authority) {
        return authorities.contains(authority);
    }
}
~~~

Factory chuyển từ Jwt authentication đã xác minh:

~~~java
@Component
public class ActorFactory {

    public Actor from(JwtAuthenticationToken jwtAuth) {
        Jwt jwt = jwtAuth.getToken();
        String tenantId = jwt.getClaimAsString("tenant_id");

        if (jwt.getSubject() == null
                || tenantId == null
                || tenantId.isBlank()) {
            throw new AccessDeniedException(
                "Required identity claims are missing"
            );
        }

        Set<String> authorities = jwtAuth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toUnmodifiableSet());

        return new Actor(
            jwt.getIssuer() == null ? null : jwt.getIssuer().toString(),
            jwt.getSubject(),
            tenantId,
            authorities
        );
    }
}
~~~

Cách này lấy subject/claims từ Jwt principal và authorities từ authentication converter đang chạy trong security configuration. Kiểm tra authentication type trước khi cast nếu endpoint có thể dùng nhiều authentication mechanism.

### 10.1. Identity key trong hệ thống nhiều issuer

Nếu nhiều issuer có thể cấp cùng giá trị `sub`, không dùng subject đơn lẻ làm global owner key. Kết hợp issuer và subject hoặc ánh xạ chúng sang internal user ID duy nhất. Cùng một email/username từ hai issuer không tự động đại diện cùng một người dùng.

## 11. Tenant context trong request và background jobs

### 11.1. Tenant context phải có nguồn tin cậy

Tenant context có thể đến từ claim, membership service hoặc một bước tenant selection đã được xác thực. Nếu user có nhiều tenant, chọn tenant từ request chỉ là yêu cầu chọn phạm vi; server vẫn phải kiểm tra membership và tạo `Actor`/context sau khi kiểm tra.

Không để header `X-Tenant-Id` tự động ghi đè tenant trong JWT mà không có policy xác minh. Header có thể hữu ích để chọn tenant trong số các tenant mà user là member, nhưng phải được đối chiếu với membership store.

### 11.2. Không dựa vào ThreadLocal không được quản lý

Nếu dùng `TenantContextHolder` dựa trên ThreadLocal, phải set/clear trong `try/finally` hoặc filter/interceptor có lifecycle rõ. Thread pool tái sử dụng thread; không clear context có thể làm request tiếp theo chạy nhầm tenant.

Trong async/reactive execution, ThreadLocal không tự truyền đúng context. Dùng context propagation phù hợp hoặc truyền `Actor`/tenant context tường minh qua call boundary.

### 11.3. Background job không có end-user Jwt

Job scheduler, message consumer hoặc batch task có thể không có `SecurityContext` của user. Cần dùng service identity và tenant scope được ghi rõ trong job envelope, sau đó kiểm tra job có quyền trên tenant đó. Không giả lập một user tùy ý để vượt qua ownership checks.

Job message chứa tenant ID vẫn là input cần xác minh. Kiểm tra nguồn phát, chữ ký/message authentication hoặc quyền service producer; sau đó validate tenant tồn tại và job type được phép chạy.

## 12. Kiểm tra ownership khi gọi downstream service

Nếu Orders API gọi Inventory API hoặc Document Service, không chuyển tiếp tenant ID tùy ý từ client. Xác định downstream call chạy theo user delegation, service identity hoặc token exchange:

- **User delegation:** truyền access token có audience/scope phù hợp.
- **Service identity:** dùng client credentials/service token và truyền business context đã được xác minh.
- **Token exchange:** đổi token theo audience/resource và policy của authorization server.

Downstream service vẫn phải tự xác minh token và tenant/object authorization của nó. Việc Orders API đã kiểm tra owner không tự cấp quyền cho Document Service trên mọi file.

Nếu dùng service token chung, cần gửi subject/tenant context theo trust contract đã xác thực, không coi header do client gửi là bằng chứng. Audit cần ghi cả end-user actor (nếu có) và service identity.

## 13. Chống TOCTOU và race conditions

TOCTOU xảy ra khi ứng dụng kiểm tra ownership, sau đó dữ liệu thay đổi trước lúc mutation hoàn tất.

Ví dụ:

1. Service đọc order và xác nhận owner là Alice.
2. Một transaction khác chuyển owner sang Bob.
3. Transaction đầu tiếp tục cập nhật order dựa trên kết quả kiểm tra cũ.

Các biện pháp:

- Thực hiện lookup, policy check và mutation trong cùng transaction.
- Dùng optimistic locking (`@Version`) để phát hiện update cạnh tranh.
- Dùng conditional update/delete có predicate tenant/owner.
- Dùng pessimistic lock khi business semantics thực sự cần.
- Đặt unique/foreign-key constraints cho tenant relationships.
- Đảm bảo mọi mutation path tuân thủ cùng policy.

### 13.1. Optimistic locking

Entity có version:

~~~java
@Entity
public class Order {

    @Id
    private String id;

    @Version
    private long version;

    private String tenantId;
    private String ownerSubject;
    private String status;
}
~~~

Nếu một transaction khác cập nhật entity sau khi được load, Hibernate có thể phát hiện version conflict khi flush/commit. Xử lý conflict theo business rule; không retry mutation mù nếu ownership có thể đã thay đổi.

### 13.2. Conditional mutation

Một câu update có predicate tenant/owner có thể tránh khoảng hở giữa check và write:

~~~sql
UPDATE orders
   SET customer_note = ?
 WHERE id = ?
   AND tenant_id = ?
   AND owner_subject = ?
   AND status = 'PENDING';
~~~

Kiểm tra affected row count. Nếu bằng 0, resource không tồn tại, không thuộc actor hoặc không còn ở trạng thái cho phép. Chọn response theo API contract nhưng không tiết lộ dữ liệu ngoài phạm vi.

## 14. Ownership cho quan hệ và child resources

Một order có thể có line items, invoices, shipments và attachments. Không được cho phép truy cập child chỉ bằng child ID.

Ví dụ truy vấn invoice phải xác nhận invoice thuộc order trong tenant của actor:

~~~java
Optional<Invoice> findByIdAndOrderTenantIdAndOrderOwnerSubject(
    String invoiceId,
    String tenantId,
    String subject
);
~~~

Nếu child resource có tenant riêng, kiểm tra quan hệ nhất quán với parent. Không chỉ xác nhận child.tenantId trùng tenant rồi bỏ qua việc child có thuộc order được phép hay không.

Với file attachment, kiểm tra authorization trước khi tạo signed download URL. URL có thời hạn cũng là bearer capability; TTL, audience và scope của nó phải giới hạn. Không phát hành URL trước khi xác nhận user có quyền đọc attachment tại thời điểm yêu cầu.

## 15. Multi-tenant membership thay vì một tenant claim cố định

Một số hệ thống cho user thuộc nhiều tenant. Khi đó `tenant_id` trong token có thể đại diện tenant đang active, hoặc token có thể chỉ chứa subject và application tra membership.

Mô hình membership:

~~~text
user_tenant_membership
----------------------
issuer
subject
tenant_id
role
status
valid_from
valid_until
~~~

Service kiểm tra membership:

~~~java
public Actor selectTenant(
        Jwt jwt,
        String requestedTenantId) {

    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();

    TenantMembership membership = membershipRepository
        .findActiveMembership(
            issuer,
            subject,
            requestedTenantId,
            clock.instant()
        )
        .orElseThrow(AccessDeniedException::new);

    return new Actor(
        issuer,
        subject,
        membership.tenantId(),
        membership.authorities()
    );
}
~~~

Membership cần kiểm tra trạng thái active, thời gian hiệu lực, role và policy. Nếu membership bị revoke, cache membership cũng có revocation window; phải đặt TTL/invalidation theo SLA.

### 15.1. Đừng trộn tenant claim và membership policy

Nếu token chứa tenant ID, xác định claim là tenant duy nhất hay chỉ là hint. Nếu membership database là nguồn sự thật, không coi claim cũ là đủ để cấp quyền sau khi membership đã bị revoke. Có thể kết hợp token claim để chọn candidate tenant rồi xác nhận membership hiện tại.

## 16. Audit và bảo vệ dữ liệu authorization

Ghi nhận các sự kiện nhạy cảm:

- Actor issuer/subject đã được xác thực.
- Tenant context.
- Resource ID và operation.
- Allow/deny outcome.
- Policy/reason code.
- Correlation ID.
- Thời điểm và service identity.

Không log raw JWT, access token, client secret hoặc dữ liệu cá nhân không cần thiết. Với denied cross-tenant access, log có thể cần phân biệt reason code nội bộ nhưng response cho client không nên tiết lộ tenant hoặc owner thực tế.

Audit log cần chống sửa đổi theo yêu cầu hệ thống và không được dùng làm nơi duy nhất thực thi authorization.

## 17. Kiểm thử service/domain policy

### 17.1. Ma trận owner và tenant

| Actor | Resource tenant | Resource owner | Kỳ vọng |
|---|---|---|---|
| Alice / tenant-a | tenant-a | Alice | Cho phép |
| Alice / tenant-a | tenant-a | Bob | Từ chối nếu không có admin role |
| Alice / tenant-a | tenant-b | Alice | Từ chối |
| Alice / tenant-a | tenant-b | Bob | Từ chối |
| Admin / tenant-a | tenant-a | Bob | Cho phép nếu role cho phép |
| Admin / tenant-a | tenant-b | Bob | Từ chối nếu admin chỉ có phạm vi tenant-a |

Test matrix này giúp tránh chỉ test owner case và bỏ sót cross-tenant access.

### 17.2. Unit test policy

~~~java
class OrderAccessPolicyTests {

    private final OrderAccessPolicy policy = new OrderAccessPolicy();

    @Test
    void ownerCanReadWithinTenant() {
        Order order = order("tenant-a", "alice");
        Actor actor = actor("tenant-a", "alice");

        assertThat(policy.canRead(order, actor)).isTrue();
    }

    @Test
    void differentOwnerCannotReadWithoutAdminRole() {
        Order order = order("tenant-a", "bob");
        Actor actor = actor("tenant-a", "alice");

        assertThat(policy.canRead(order, actor)).isFalse();
    }

    @Test
    void sameOwnerCannotReadAcrossTenant() {
        Order order = order("tenant-b", "alice");
        Actor actor = actor("tenant-a", "alice");

        assertThat(policy.canRead(order, actor)).isFalse();
    }
}
~~~

Các helper `order(...)` và `actor(...)` chỉ là fixture. Bổ sung test admin role, cancelled order, owner reassignment và membership inactive theo policy thực tế.

### 17.3. Repository integration test

Dùng database test để xác nhận query luôn giới hạn tenant/owner. Tạo hai tenant với cùng subject hoặc ID pattern tương tự và xác nhận query của tenant-a không trả row tenant-b. Nếu dùng native SQL, specification hoặc search repository, test từng query path.

Không chỉ mock repository trong mọi test; mock không chứng minh predicate SQL/JPA được áp dụng đúng.

### 17.4. Service integration test

Kiểm tra service:

- Owner đúng tenant đọc được order.
- Owner khác bị từ chối.
- Cross-tenant bị từ chối.
- Admin trong tenant đọc được order của user khác.
- Admin tenant-a không đọc được tenant-b.
- Update không đổi được owner/tenant.
- Delete không xóa child resource ngoài phạm vi.
- Không có side effect khi policy từ chối.

## 18. Kiểm thử MockMvc với JWT principal

MockMvc có thể dùng `jwt()` postprocessor để dựng JWT authentication giả lập:

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
~~~

Postprocessor này phù hợp để kiểm tra authorization/controller/service behavior. Nó không verify chữ ký, issuer hoặc audience của raw Bearer token. Cần test decoder riêng nếu muốn xác minh JWT validation pipeline.

### 18.1. Owner khác trong cùng tenant

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("charlie")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isNotFound());
~~~

Kỳ vọng `404` giả định API ẩn sự tồn tại của resource đối với non-owner. Nếu contract dùng `403`, điều chỉnh assertion nhưng giữ nguyên policy.

### 18.2. Tenant khác

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-b")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isNotFound());
~~~

Nếu `order-42` thuộc tenant-a, actor tenant-b không được nhìn thấy dữ liệu. Kiểm tra response body không chứa owner, tenant thật hoặc các field của order.

### 18.3. Thiếu tenant claim

~~~java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isForbidden());
~~~

Status phụ thuộc cách application xử lý claim thiếu. Nếu claim được coi là bắt buộc trong token profile, decoder validator có thể từ chối token và trả authentication failure thay vì domain 403. Điều quan trọng là không mặc định tenant hoặc cho request tiếp tục.

### 18.4. Scope hợp lệ nhưng owner sai

~~~java
mvc.perform(put("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("charlie")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.write")
        ))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerNote": "Change delivery note"
            }
            """))
    .andExpect(status().isNotFound());
~~~

Test này chứng minh scope `orders.write` không thay thế ownership check. Xác nhận repository/entity không bị thay đổi sau request bị từ chối.

## 19. Kiểm tra list và bulk operations

Với list endpoint, tạo fixture có nhiều tenant và owner:

~~~java
@Test
void listOnlyReturnsOrdersForCurrentTenant() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "orders.read")
            )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content[*].tenantId")
            .value(everyItem(is("tenant-a"))));
}
~~~

Nếu response không expose `tenantId`, assert các order IDs thuộc fixture tenant-a. Kiểm tra cả `totalElements`, aggregation, filter và export; dữ liệu ngoài tenant không được ảnh hưởng metadata trả về nếu điều đó có thể làm lộ thông tin.

Với bulk update/delete, policy phải được áp dụng cho toàn bộ tập IDs. Một lựa chọn là query scoped theo tenant/owner và so sánh số lượng IDs được tìm thấy với số lượng request. Nếu mismatch, từ chối toàn bộ mutation theo contract để tránh partial changes ngoài ý muốn.

## 20. Security configuration và method security phối hợp

Ví dụ filter chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                .hasAuthority("SCOPE_orders.delete")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Service:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderResponse getOrder(String id, Actor actor) {
    return orderService.getOrder(id, actor);
}
~~~

Filter chain kiểm soát scope theo route; service kiểm tra tenant/owner. Hai lớp bảo vệ các quyết định khác nhau và cần test riêng lẫn end-to-end.

## 21. Những lỗi thiết kế thường gặp

1. **Chỉ kiểm tra scope:** `orders.read` không chứng minh user được đọc mọi order.
2. **Tin tenant ID từ request:** client có thể đổi header, path hoặc body để chọn tenant khác.
3. **Query chỉ theo object ID:** dễ tạo IDOR/BOLA.
4. **Load entity rồi quên kiểm tra owner:** một controller khác có thể trả entity ngoài phạm vi.
5. **Chỉ bảo vệ GET:** update/delete/export/bulk operations cũng cần object-level policy.
6. **Map request body trực tiếp vào entity:** có thể cho phép mass assignment `tenantId`/`ownerSubject`.
7. **Lọc tenant sau pagination:** count, ordering và page metadata có thể tiết lộ dữ liệu.
8. **Dùng ThreadLocal không clear:** request tiếp theo có thể thừa tenant context.
9. **Tin tenant claim mãi mãi:** membership/revocation có thể đã thay đổi.
10. **Method security self-invocation:** lời gọi nội bộ có thể bỏ qua Spring proxy.
11. **Chỉ mock repository:** không chứng minh query thật có tenant predicate.
12. **Kiểm tra owner rồi mutation ngoài transaction:** tạo TOCTOU race.
13. **Chỉ kiểm tra parent, quên child resource:** invoice/attachment có thể bị truy cập trực tiếp bằng ID.
14. **Bulk operation partial update không rõ contract:** một số resource ngoài quyền có thể bị thay đổi.
15. **Không test admin boundary:** admin tenant-a không mặc nhiên có quyền tenant-b.
16. **Dùng email làm stable subject:** email có thể đổi hoặc không duy nhất giữa issuer.
17. **Chuyển tenant bằng update thông thường:** có thể làm resource thoát khỏi boundary.
18. **Không kiểm tra downstream:** service khác có thể tin tenant header do caller tự gửi.

## 22. Checklist kiểm tra owner và tenant

- [ ] Subject được lấy từ authenticated principal đã được Resource Server xác minh.
- [ ] Tenant context đến từ claim hoặc membership policy đã được kiểm tra.
- [ ] Request body không tự quyết định `ownerSubject` hoặc `tenantId`.
- [ ] Repository query luôn giới hạn tenant.
- [ ] Owner predicate được áp dụng cho object-level operations.
- [ ] Admin role có phạm vi tenant rõ ràng.
- [ ] Read, list, search, count, export, update và delete đều được bảo vệ.
- [ ] Child resources và file attachments có kiểm tra parent/tenant/owner.
- [ ] DTO chỉ cho phép cập nhật các trường được phép.
- [ ] Tenant/owner reassignment là use case riêng có audit.
- [ ] Transaction, optimistic lock hoặc conditional mutation xử lý TOCTOU.
- [ ] Async jobs và downstream calls có tenant trust contract rõ.
- [ ] Method security chạy qua Spring-managed proxy.
- [ ] Unit, repository, service và MockMvc tests bao phủ cross-tenant/owner cases.
- [ ] Denied requests không tạo side effects.
- [ ] Error response không tiết lộ resource existence ngoài policy.
- [ ] Audit log ghi actor, tenant, resource, operation và outcome mà không log token.

## 23. Tài liệu tham khảo

- [OWASP API1:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm soát quyền trên từng object và ngăn IDOR/BOLA.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): nguyên tắc deny-by-default và kiểm tra quyền ở mọi request.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, method interceptor và authorization.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT principal, claims và authority conversion.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): hỗ trợ kiểm thử authentication/authorization.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/): repository query derivation, transactions và persistence.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): claims `iss` và `sub` trong JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token profile và validation requirements.

**Kết luận:** Scope/role quyết định người gọi có thể thực hiện loại thao tác nào; tenant và ownership quyết định thao tác đó áp dụng lên tài nguyên nào. Lấy subject từ principal đã xác minh, xác lập tenant context qua trust policy, ràng buộc tenant/owner ngay trong repository query và thực hiện mutation trong transaction có kiểm soát. Bảo vệ đồng đều detail, list, search, export, update, delete và child resources; kiểm thử cross-tenant, wrong-owner, admin boundary và side effects để ngăn IDOR/BOLA trong lớp nghiệp vụ.
