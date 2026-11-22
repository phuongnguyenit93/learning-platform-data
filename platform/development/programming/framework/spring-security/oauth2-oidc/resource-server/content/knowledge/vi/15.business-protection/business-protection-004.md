# Kiểm tra chủ sở hữu, tenant và quan hệ với tài nguyên

Trong **Spring Security OAuth 2.0 Resource Server**, việc một access token JWT có chữ ký hợp lệ và chứa `SCOPE_orders.read` **không có nghĩa** người dùng được phép đọc **mọi đơn hàng**. Token xác định danh tính và quyền truy cập ở mức chức năng; còn quyền truy cập **một bản ghi cụ thể** phải được đánh giá dựa trên **chủ sở hữu, tenant và quan hệ nghiệp vụ** giữa người gọi với tài nguyên.

Đây là vấn đề trọng tâm của **object-level authorization**. Một API đã bật `authenticated()`, `hasAuthority(...)` hay `@PreAuthorize(...)` vẫn có thể tồn tại lỗ hổng **Broken Object Level Authorization (BOLA)**, thường biểu hiện như **Insecure Direct Object Reference (IDOR)**, nếu truy vấn dữ liệu chỉ dựa vào ID do client gửi mà không kiểm tra quyền trên đối tượng.

Bài này giải thích cách phối hợp **OAuth 2.0 scopes**, danh tính từ JWT/OIDC, **tenant isolation**, ownership, sharing, phân quyền theo quan hệ và giới hạn truy vấn trong ứng dụng Spring Security Servlet Resource Server.

## 1. Ba câu hỏi bảo mật khác nhau

Xét request:

~~~http
GET /api/tenants/t-7/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Resource Server cần trả lời:

1. **Authentication – Ai gọi?** JWT có hợp lệ không, issuer có đáng tin, audience có dành cho Orders API, token còn hạn và subject/client là ai?
2. **Function-level authorization – Được làm gì?** Token có scope như `orders.read`, role hoặc authority cần thiết cho thao tác đọc đơn hàng?
3. **Object-level authorization – Được làm trên tài nguyên nào?** Đơn hàng 123 thuộc tenant nào? Người gọi có là owner, thành viên có vai trò thích hợp hoặc người được chia sẻ quyền đọc không?

~~~mermaid
flowchart TD
    A["GET /tenants/t-7/orders/123"] --> B["JwtDecoder xác minh token"]
    B --> C{"Signature / iss / aud / exp hợp lệ?"}
    C -- "Không" --> X["401 Unauthorized"]
    C -- "Có" --> D{"Có SCOPE_orders.read?"}
    D -- "Không" --> Y["403 Forbidden"]
    D -- "Có" --> E["Ánh xạ (iss, sub) tới user nội bộ"]
    E --> F["Kiểm tra active membership tenant t-7"]
    F --> G["Truy vấn order theo ID và tenant"]
    G --> H["Kiểm tra owner / role / sharing"]
    H --> I{"Có quyền đọc order này?"}
    I -- "Không" --> Z["403 hoặc 404 theo chính sách"]
    I -- "Có" --> J["Trả DTO chỉ chứa dữ liệu được phép"]
~~~

| Lớp bảo vệ | Ví dụ | Nếu thiếu |
| --- | --- | --- |
| Xác minh access token | Signature, issuer, audience, thời hạn | Chấp nhận token giả, token sai issuer hoặc sai mục đích |
| Quyền chức năng | `SCOPE_orders.read` | Cho phép gọi thao tác chưa được cấp scope |
| Quyền đối tượng | Owner, tenant membership, share | Đọc/sửa bản ghi của người khác hoặc tenant khác |
| Quyền từng trường | Che giá vốn hoặc PII nếu không đủ quyền | Lộ dữ liệu nhạy cảm bên trong đối tượng hợp lệ |

**Scope không thay thế ownership. Tenant membership không tự động đồng nghĩa sở hữu mọi bản ghi của tenant.** Các điều kiện phải kết hợp theo chính sách nghiệp vụ.

## 2. Danh tính từ JWT: tin cậy tới đâu?

Access token JWT ví dụ:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read orders.write",
  "tenant_id": "t-7"
}
~~~

Đây chỉ là payload minh họa; việc đọc được chuỗi Base64URL không chứng minh JWT hợp lệ. **`JwtDecoder` phải xác minh chữ ký, issuer, audience, thời hạn và các điều kiện phù hợp trước khi ứng dụng sử dụng claim để phân quyền.**

Các giá trị cần phân biệt:

| Giá trị | Nguồn | Vai trò trong phân quyền |
| --- | --- | --- |
| `iss` và `sub` đã được xác minh | Access token qua Resource Server | Nhận diện subject trong phạm vi issuer |
| `scope`/`scp` | Token do Authorization Server phát hành | Quyền chức năng đã cấp theo hợp đồng token |
| `tenant_id` trong JWT | Claim issuer cung cấp | Có thể làm tenant context nếu đáng tin và đúng hợp đồng; chưa thay thế membership hiện hành |
| `tenantId` trong URL/body/header | Dữ liệu do client chọn/gửi | **Không phải bằng chứng** user thuộc tenant |
| `ownerUserId` trong request body | Dữ liệu client kiểm soát | Không được tự dùng để xác lập ownership |
| Owner, membership, share trong DB | Dữ liệu nghiệp vụ được quản lý | Cơ sở để xác định quyền đối tượng hiện hành |

### Vì sao nên dùng cặp `(issuer, subject)`?

`sub` là định danh của subject **trong phạm vi issuer**. Hai issuer khác nhau có thể cùng phát `sub: "user-42"` cho hai người khác nhau. Với hệ thống hỗ trợ nhiều issuer, nên ánh xạ **(iss, sub)** sang **internal user ID**:

~~~text
JWT đã xác minh
    iss = https://auth.example.com/realms/shop
    sub = user-42
           |
           v
    user_identity_mapping(issuer, subject, user_id)
           |
           v
    users.id (ID nội bộ)
           |
           +--> tenant_memberships.user_id
           +--> orders.owner_user_id
           +--> order_shares.grantee_user_id
~~~

Không nên dùng email hoặc tên đăng nhập làm khóa ownership mặc định vì chúng có thể thay đổi, trùng nhau hoặc có quy tắc xác minh khác nhau.

Đặc biệt, với **Client Credentials**, token có thể mô tả **machine client** chứ không phải một người dùng. Không giả định mọi `sub` là user owner; API cần chính sách riêng dựa trên client identity, tenant binding và chức năng service được phép.

## 3. Mô hình tenant, owner và relationship

Một hệ thống đơn hàng có thể có:

~~~text
Tenant(id)
  |-- TenantMembership(userId, tenantId, role, status)
  |-- Order(id, tenantId, ownerUserId, customerId, status)
  |       |-- OrderLine(id, orderId)
  |       |-- OrderAttachment(id, orderId)
  |       +-- OrderShare(orderId, granteeUserId, permission, expiresAt)
  +-- Customer(id, tenantId)

UserIdentity(issuer, subject) -> InternalUser(id)
~~~

Chính sách minh họa:

> Một người dùng có thể **đọc đơn hàng** khi access token được xác thực, có scope `orders.read`, người dùng là **thành viên còn hoạt động** của tenant chứa đơn hàng, và người dùng là owner **hoặc** manager của tenant có quyền đọc order **hoặc** được chia sẻ quyền READ còn hiệu lực.

Biểu thức logic:

~~~text
canReadOrder(actor, order) =
    tokenHasScope(actor, "orders.read")
    AND activeMember(actor.userId, order.tenantId)
    AND (
        order.ownerUserId == actor.userId
        OR hasTenantRole(actor.userId, order.tenantId, "ORDER_MANAGER")
        OR hasActiveShare(actor.userId, order.id, "READ")
    )
~~~

Đây là **policy ví dụ**; một hệ thống khác có thể cho đối tác được truy cập qua delegation xuyên tenant hoặc có các cấp quyền chi tiết hơn. Điều quan trọng là mỗi quan hệ có **ngữ nghĩa, phạm vi, hiệu lực và hành động được phép** rõ ràng.

| Quan hệ | Ví dụ | Cần kiểm tra |
| --- | --- | --- |
| **Owner** | Người sở hữu order | Owner ID trong DB, trạng thái và policy chuyển quyền |
| **Tenant member** | Nhân viên công ty t-7 | Membership còn hoạt động, đúng tenant, role có hiệu lực |
| **Manager** | Quản lý đơn hàng t-7 | Quyền trong đúng tenant, không suy rộng sang tenant khác |
| **Sharing** | Owner chia sẻ order cho B | Đúng grantee, quyền READ/EDIT, thời hạn, revoked flag |
| **Delegation** | Người được ủy quyền phê duyệt | Bên ủy quyền, phạm vi, hiệu lực và quyền của delegate |
| **Parent-child** | OrderLine của Order | Child thuộc đúng parent/tenant đã được phép truy cập |
| **Assignment** | Nhân viên phụ trách customer | Assignment còn hợp lệ, resource thuộc phạm vi assignment |
| **Service client** | Background job xử lý order | Client identity đáng tin, tenant binding, scope chức năng và phạm vi service |

## 4. Lỗ hổng IDOR/BOLA: khi chỉ kiểm tra scope

Ví dụ controller:

~~~java
@GetMapping("/api/orders/{id}")
OrderDto getOrder(@PathVariable long id) {
    return orderRepository.findById(id)
        .map(OrderDto::from)
        .orElseThrow(OrderNotFoundException::new);
}
~~~

Dù Spring Security bảo vệ endpoint:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

người gọi có scope đọc vẫn có thể thử:

~~~text
GET /api/orders/101   -- order của user A
GET /api/orders/102   -- order của user B
GET /api/orders/201   -- order thuộc tenant khác
~~~

Nếu `findById(id)` không ràng buộc tenant và ownership, client có thể đọc dữ liệu chỉ bằng việc biết ID. Đây là dạng BOLA/IDOR. **Thay ID số bằng UUID khó đoán không thay cho authorization**; ID có thể bị lộ qua link, log, email hoặc dữ liệu khác.

BOLA có thể xảy ra ở bất kỳ hành động nào: xem chi tiết, cập nhật, duyệt, chuyển chủ sở hữu, tải tệp, xuất báo cáo, xóa bản ghi, tạo link chia sẻ, tìm kiếm và cả endpoint chỉ trả count/metadata.

## 5. Nhận principal đã xác thực ở Spring Security

Với JWT Resource Server, controller có thể nhận `Jwt` từ Spring Security:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    OrderDto getOrder(
            @PathVariable String tenantId,
            @PathVariable long orderId,
            @AuthenticationPrincipal Jwt jwt) {
        return orders.readOrder(jwt, tenantId, orderId);
    }
}
~~~

Lưu ý:

1. `Jwt` này đến từ Resource Server authentication, **không phải JSON body** do client tự đưa lên.
2. `tenantId` và `orderId` trong path là dữ liệu người gọi có thể đổi. Chúng **không chứng minh quyền**.
3. Ví dụ dùng nhánh JWT. Với opaque access token, principal có thể là `OAuth2AuthenticatedPrincipal`; ứng dụng nên dùng identity abstraction thống nhất nếu hỗ trợ cả hai cách xác thực.
4. Decoder phải có đủ chính sách issuer, audience, time và profile trước khi ứng dụng tin danh tính.

Tầng service mới ánh xạ `(iss, sub)` thành user nội bộ và kiểm tra quyền hiện hành dựa trên DB.

## 6. Service kiểm tra scope, tenant và quyền đối tượng

Trong Spring Security Servlet hiện đại, có thể bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Ví dụ service:

~~~java
import java.util.Objects;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final UserIdentityRepository identities;
    private final TenantMembershipRepository memberships;
    private final OrderRepository orders;
    private final OrderShareRepository shares;

    public OrderService(
            UserIdentityRepository identities,
            TenantMembershipRepository memberships,
            OrderRepository orders,
            OrderShareRepository shares) {
        this.identities = identities;
        this.memberships = memberships;
        this.orders = orders;
        this.shares = shares;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(Jwt jwt, String tenantId, long orderId) {
        String issuer = Objects.requireNonNull(jwt.getIssuer()).toString();
        String subject = Objects.requireNonNull(jwt.getSubject());

        InternalUser actor = identities
            .findByIssuerAndSubject(issuer, subject)
            .orElseThrow(() -> new AccessDeniedException("Unknown principal"));

        TenantMembership membership = memberships
            .findActiveMembership(actor.getId(), tenantId)
            .orElseThrow(() -> new AccessDeniedException("Tenant denied"));

        Order order = orders.findByIdAndTenantId(orderId, tenantId)
            .orElseThrow(OrderNotFoundException::new);

        boolean owns = actor.getId().equals(order.getOwnerUserId());
        boolean manages = membership.hasRole("ORDER_MANAGER");
        boolean shared = shares.existsActiveReadShare(
            order.getId(), actor.getId());

        if (!(owns || manages || shared)) {
            throw new AccessDeniedException("Order denied");
        }

        return OrderDto.from(order);
    }
}
~~~

**Các kiểu miền nghiệp vụ ở ví dụ là placeholders do ứng dụng định nghĩa**, bao gồm `UserIdentityRepository`, `TenantMembershipRepository`, `OrderRepository`, `OrderShareRepository`, `InternalUser`, `TenantMembership`, `Order`, `OrderDto` và `OrderNotFoundException`. Đoạn code minh họa sự phối hợp policy, không phải thư viện mặc định của Spring Security.

Các lớp bảo vệ:

- `@PreAuthorize` đòi scope `orders.read`.
- `findByIssuerAndSubject(...)` xác định user nội bộ theo issuer và subject đã được xác thực.
- `findActiveMembership(...)` xác định membership **hiện hành** ở tenant được yêu cầu.
- `findByIdAndTenantId(...)` chỉ tải order thuộc đúng tenant.
- `owns || manages || shared` quyết định ai được đọc **order cụ thể**.
- `OrderDto.from(order)` chỉ tạo dữ liệu API cho phép công bố; các field nhạy cảm cần chính sách riêng.

**Chú ý về method security:** `@EnableMethodSecurity` phải được bật; lời gọi phải đi qua proxy phù hợp. Self-invocation từ một method sang method khác cùng object có thể bỏ qua interception của proxy. Không đặt toàn bộ bảo vệ chỉ ở một controller nếu các workflow khác có thể gọi thẳng repository/service.

## 7. Ràng buộc truy vấn ở repository

Tránh kiểu truy vấn không ràng buộc:

~~~java
Order order = orderRepository.findById(orderId).orElseThrow();
~~~

Trong multi-tenant, ít nhất cần scope tenant:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByIdAndTenantId(Long id, String tenantId);

    @Query("""
        select o from Order o
        where o.id = :orderId
          and o.tenantId = :tenantId
          and o.ownerUserId = :userId
        """)
    Optional<Order> findOwnedOrder(
        @Param("orderId") Long orderId,
        @Param("tenantId") String tenantId,
        @Param("userId") Long userId
    );
}
~~~

`findByIdAndTenantId(...)` ngăn lộ order thuộc tenant khác dù client đoán đúng ID. `findOwnedOrder(...)` gắn thêm owner nếu endpoint chỉ dành cho owner. Với policy manager/share, có thể bổ sung truy vấn có điều kiện rõ ràng hoặc kiểm tra qua service.

**Không nên lấy toàn bộ dữ liệu nhiều tenant vào Java rồi mới lọc**:

~~~java
// Thiết kế kém cho list và pagination.
List<Order> all = orderRepository.findAll();
return all.stream()
    .filter(o -> canRead(actor, o))
    .toList();
~~~

Nó vừa tốn tài nguyên vừa tăng rủi ro lộ dữ liệu qua log, export, lỗi hoặc kết quả phân trang không nhất quán. Nên gắn tenant và relationship ngay trong truy vấn khi hợp đồng cho phép.

Ví dụ SQL cho danh sách order mà actor là owner hoặc được chia sẻ READ:

~~~sql
SELECT o.*
FROM orders o
WHERE o.tenant_id = :tenant_id
  AND (
       o.owner_user_id = :actor_id
       OR EXISTS (
           SELECT 1
           FROM order_shares s
           WHERE s.order_id = o.id
             AND s.grantee_user_id = :actor_id
             AND s.permission = 'READ'
             AND s.revoked_at IS NULL
             AND (s.expires_at IS NULL OR s.expires_at > CURRENT_TIMESTAMP)
       )
  )
ORDER BY o.id
LIMIT :page_size OFFSET :offset;
~~~

Truy vấn chỉ minh họa hai nhánh owner/share, giả định membership tenant đã được kiểm tra. Với manager, cần thêm nhánh thích hợp; không tự thêm điều kiện OR khiến mọi thành viên tenant có thể xem mọi order. Sử dụng **parameter binding**, không nối `tenant_id`/`actor_id` trực tiếp vào câu SQL.

Truy vấn **count, search, autocomplete, download và export** cũng phải áp dụng cùng giới hạn dữ liệu. Một endpoint chỉ trả số lượng order của tenant khác vẫn có thể rò rỉ thông tin.

## 8. Tenant context không phải bằng chứng membership

Các kiến trúc multi-tenant phổ biến gồm:

- **Shared schema:** bảng chứa `tenant_id`.
- **Schema per tenant:** mỗi tenant dùng schema riêng.
- **Database per tenant:** mỗi tenant dùng database riêng.

Mô hình lưu trữ không thay thế authorization. Ví dụ request:

~~~http
GET /api/tenants/t-8/orders/201 HTTP/1.1
Authorization: Bearer <token-for-user-in-t-7>
~~~

Nếu user chỉ có active membership t-7 thì API phải từ chối t-8, trừ khi có chính sách **cross-tenant delegation** được cấp rõ ràng. Header `X-Tenant-ID: t-8`, path `/tenants/t-8` hoặc cookie chọn tenant chỉ thể hiện **ngữ cảnh mong muốn của client**, không tạo quyền.

Một người có thể thuộc nhiều tenant. Khi giao diện cho user “chọn tenant hiện tại”, API phải xác minh user còn là thành viên tenant ấy và chỉ truy vấn resource trong tenant tương ứng. Nếu JWT chứa tenant-scoped claim, cần kiểm tra claim theo hợp đồng issuer; quyền thực tế có thể đã thay đổi sau khi token được phát hành.

### Cẩn trọng khi dùng TenantContext/ThreadLocal

Servlet container tái sử dụng thread. Nếu ứng dụng lưu tenant trong `ThreadLocal` mà quên dọn sau request, request khác có thể kế thừa nhầm tenant. Khi dùng tenant context, cần quản lý vòng đời rõ ràng, xóa trong `finally` và xử lý async/thread propagation an toàn. Trong nhiều trường hợp, truyền tenant ID đã được xác minh **tường minh** vào service/repository dễ kiểm soát hơn.

## 9. Quan hệ cha–con của tài nguyên

Một request có thể chứa cả parent ID và child ID:

~~~http
GET /api/orders/101/lines/999 HTTP/1.1
Authorization: Bearer <valid-access-token>
~~~

API đã kiểm tra người gọi được xem order 101. Nhưng nếu dòng code đọc line:

~~~java
OrderLine line = orderLineRepository.findById(999L)
    .orElseThrow(OrderLineNotFoundException::new);
~~~

thì line 999 có thể thuộc order 201 trong tenant khác. **Kiểm tra parent không chứng minh child ID thuộc parent ấy.**

Cách truy vấn an toàn hơn:

~~~java
OrderLine line = orderLineRepository
    .findByIdAndOrderIdAndTenantId(lineId, orderId, tenantId)
    .orElseThrow(OrderLineNotFoundException::new);
~~~

Hoặc:

~~~sql
SELECT l.*
FROM order_lines l
JOIN orders o ON o.id = l.order_id
WHERE l.id = :line_id
  AND o.id = :order_id
  AND o.tenant_id = :tenant_id;
~~~

Áp dụng cho invoice lines, document versions, attachments, comments, payments, tasks, folder/file, parent-child organization và các resource liên quan khác. Các thao tác **sửa/xóa** child cần kiểm tra quyền hành động và mối quan hệ thật giữa child – parent – tenant.

## 10. Sharing và delegation phải có phạm vi, thời hạn

Đôi khi owner không phải người duy nhất được truy cập. Hệ thống có thể hỗ trợ chia sẻ, giao việc hoặc ủy quyền:

~~~text
order_shares(
    order_id,
    grantee_user_id,
    permission,      -- READ / EDIT / EXPORT
    created_by_user_id,
    expires_at,
    revoked_at
)
~~~

Khi kiểm tra share, API cần:

1. Xác nhận share thuộc **đúng order**, đúng người nhận, đúng tenant/context.
2. Xác nhận permission phù hợp **hành động hiện tại**; READ không tự bao gồm EDIT hoặc APPROVE.
3. Kiểm tra share **chưa bị thu hồi, chưa hết hạn**.
4. Kiểm tra membership hoặc điều kiện liên tenant theo policy.
5. Nếu quyền phụ thuộc người ủy quyền, kiểm tra hiệu lực ủy quyền theo quy định nghiệp vụ.

Nếu user vừa bị xóa khỏi tenant nhưng access token vẫn còn hạn 15 phút, token có thể vẫn xác thực thành công. Tuy nhiên membership đã bị thu hồi phải có hiệu lực theo chính sách cập nhật quyền hiện hành. Với yêu cầu thu hồi quyền nhanh, thường cần đọc membership/share từ DB hoặc service policy kèm cache/invalidation phù hợp, không chỉ dựa vào claim token cũ.

## 11. Tránh mass assignment với owner và tenant

Giả sử API nhận body:

~~~json
{
  "title": "New order",
  "tenantId": "t-8",
  "ownerUserId": "another-user",
  "status": "APPROVED"
}
~~~

Nếu server bind trực tiếp mọi field của request lên entity, client có thể tự đặt owner hoặc tenant rồi làm sai phạm vi quyền. Đây là một kiểu **mass assignment/broken object authorization**.

Hướng xử lý:

- Dùng DTO cho phép **chỉ những field người gọi được sửa**, ví dụ `title`, `note`.
- Xác định owner/tenant từ logic server sau khi xác minh danh tính và membership.
- Chuyển owner, chuyển tenant, approve, share phải là **hành động riêng** với quyền riêng.
- Kiểm tra trạng thái workflow; user được sửa order DRAFT không mặc định được sửa order APPROVED.

Ví dụ skeleton:

~~~java
public record UpdateOrderRequest(String title, String note) {}

@PreAuthorize("hasAuthority('SCOPE_orders.write')")
@Transactional
public void updateOrder(
        Jwt jwt, String tenantId, long orderId, UpdateOrderRequest request) {

    // 1. Resolve actor từ (iss, sub).
    // 2. Kiểm tra membership tenant.
    // 3. Tải Order theo (orderId, tenantId).
    // 4. Kiểm tra quan hệ owner/manager/share cho hành động EDIT.
    // 5. Chỉ cho sửa trạng thái được phép, ví dụ DRAFT.
    // 6. Validate và cập nhật title/note.
    // KHÔNG gán owner, tenant hoặc APPROVED từ input client.
}
~~~

Đoạn code là ví dụ thứ tự kiểm tra, không phải implementation đầy đủ.

## 12. Tránh TOCTOU khi quyền/tài nguyên thay đổi đồng thời

**Time-of-check to time-of-use** xảy ra khi kết quả kiểm tra quyền không còn đúng ở thời điểm cập nhật:

~~~text
10:00:00  API xác minh user A được sửa order 101
10:00:01  Admin thu hồi share hoặc chuyển order sang tenant khác
10:00:02  API ghi order theo kết quả kiểm tra cũ
~~~

Các kỹ thuật phòng vệ:

- Kiểm tra và cập nhật trong **transaction** phù hợp.
- Dùng **optimistic locking** với `@Version` khi cần phát hiện thay đổi đồng thời.
- Với thao tác nhạy cảm, thực hiện **conditional update** có điều kiện tenant, owner/relationship, status và version.
- Sử dụng lock DB phù hợp nếu cần bảo đảm consistency cao hơn.
- Không gửi event, email, thanh toán hoặc cập nhật hệ thống ngoài **trước khi** quyền và điều kiện nghiệp vụ được xác nhận.

Ví dụ conditional update khi owner chỉ được sửa order DRAFT:

~~~sql
UPDATE orders
SET title = :title,
    version = version + 1
WHERE id = :order_id
  AND tenant_id = :tenant_id
  AND owner_user_id = :actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
~~~

Chỉ coi cập nhật thành công khi **số dòng tác động là 1**. Nếu 0 dòng, có thể do không tồn tại, không có quyền hoặc version đã đổi; trả lỗi theo chính sách mà không tiết lộ thông tin tenant khác. Điều kiện trên là **policy ví dụ** cho owner, cần sửa nếu hệ thống cho manager hoặc người được share EDIT.

Transaction không tự tạo authorization khi câu truy vấn thiếu tenant/owner. Ngược lại, kiểm tra quyền ngoài transaction có thể không đủ với nghiệp vụ nhạy cảm trước race condition.

## 13. Tập trung chính sách bằng policy service

Với Spring Method Security, có thể đưa kiểm tra đối tượng vào một bean chính sách:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "@orderAccess.canRead(authentication, #tenantId, #orderId)"
)
public OrderDto readOrder(String tenantId, long orderId) {
    return orderService.readWithScopedQuery(tenantId, orderId);
}
~~~

`orderAccess` là bean do ứng dụng định nghĩa. Nó có thể ánh xạ principal thành actor, kiểm tra membership, ownership và share. Một số hệ thống dùng `PermissionEvaluator` cùng `hasPermission(...)`; các phiên bản Spring Security mới cũng có `AuthorizationManager` cho HTTP/method authorization.

Khi dùng SpEL hoặc annotation:

- Tránh query DB quá nhiều lần cho mỗi đối tượng trong danh sách (**N+1 authorization queries**).
- Đảm bảo tài nguyên **được dùng** đúng là tài nguyên **đã được kiểm tra**.
- Đừng bỏ qua phạm vi tenant ở repository vì chỉ có một boolean check trong annotation.
- Method security proxy có thể không intercept self-invocation.
- Các entrypoint khác như batch job, event consumer và internal API cần áp dụng cùng policy nếu chúng thao tác cùng dữ liệu.

Một thiết kế thường dễ duy trì là **policy service** cho decision và **scoped repository** cho truy vấn/ghi, với transaction và audit khi cần.

## 14. 403 hay 404 khi không có quyền?

| HTTP status | Ý nghĩa sử dụng |
| --- | --- |
| **401 Unauthorized** | Request thiếu access token hợp lệ hoặc authentication thất bại |
| **403 Forbidden** | Chủ thể đã xác thực nhưng không được phép thực hiện thao tác |
| **404 Not Found** | API không tìm thấy resource trong phạm vi cho phép, hoặc có chủ đích không tiết lộ resource của tenant/người khác |

Ví dụ, `findByIdAndTenantId(101, "t-7")` trả rỗng nếu order 101 thực tế thuộc t-8. API có thể trả **404** mà không xác nhận order 101 tồn tại ở tenant khác. Đây là lựa chọn giúp giảm enumeration, nhưng cần áp dụng nhất quán và không làm rò thông tin qua body, timing, count hay message.

**403 và 404 không hoàn toàn tương đương.** Quyết định trả mã nào là một phần của hợp đồng bảo mật và API; log/audit nội bộ vẫn có thể ghi lý do chính xác ở mức cho phép mà không tiết lộ cho caller.

## 15. Kiểm thử quyền đối tượng

Không thể chứng minh object-level authorization chỉ với test JWT hợp lệ có scope đọc. Cần xây dữ liệu và các mối quan hệ thật trong DB test.

Giả sử:

- A, B thuộc tenant t-7.
- C thuộc tenant t-8.
- Order 101 thuộc t-7, owner A.
- Order 102 thuộc t-7, owner B.
- Order 201 thuộc t-8, owner C.

| Caller và token | Request | Kỳ vọng policy ví dụ |
| --- | --- | --- |
| A có `orders.read` | Đọc order 101 ở t-7 | Cho phép |
| A có `orders.read` | Đọc order 102 ở t-7 | Từ chối nếu không share/manager |
| A có `orders.read` | Đọc order 201 ở t-8 | Từ chối: tenant mismatch |
| A thiếu `orders.read` | Đọc order 101 do A sở hữu | 403: thiếu quyền chức năng |
| A dùng JWT hết hạn | Đọc order 101 | 401: token không hợp lệ |
| B được share READ order 101 | Đọc order 101 | Cho phép nếu share còn hiệu lực |
| B bị revoke share READ | Đọc order 101 | Từ chối |
| B chỉ có share READ | Sửa order 101 | Từ chối nếu không có quyền EDIT |
| Manager t-7 | Đọc order 102 t-7 | Cho phép nếu policy cấp quyền manager |
| Manager t-7 | Đọc order 201 t-8 | Từ chối: role không xuyên tenant |
| A | Đọc line của order 201 dưới path order 101 | Từ chối/404: sai parent-child relation |
| A | List/export order t-7 | Chỉ trả resource được phép, kể cả count và metadata |

Đối với thao tác ghi, test phải xác nhận **dữ liệu DB không bị thay đổi** sau request bị từ chối; một response 403 nhưng side effect đã xảy ra không phải là bảo vệ đúng.

### Phân biệt các lớp test

| Loại test | Có thể kiểm tra | Không tự chứng minh |
| --- | --- | --- |
| `@WithMockUser` / method security test | Authority/role expressions | JWT signature, issuer/audience, mapping identity thực |
| `jwt()` MockMvc post-processor | HTTP authorization với JWT principal thử nghiệm | Thường bỏ qua `JwtDecoder`/JWS signature thật |
| Service + repository integration test | Ownership, membership, share, scoped queries | Bearer filter/decoder ở HTTP |
| End-to-end test với JWT được ký bằng khóa thử nghiệm | Kết hợp token validation, scope và object-level policy | Cần dữ liệu quan hệ test được quản lý đúng |

Ví dụ dạng MockMvc test quyền đối tượng (cần data fixture và các import của Spring Security Test):

~~~java
mockMvc.perform(get("/api/tenants/t-7/orders/101")
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://auth.example.com/realms/shop")
                .subject("user-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/tenants/t-8/orders/201")
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://auth.example.com/realms/shop")
                .subject("user-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());
~~~

Đây là mã **minh họa với dữ liệu đã seed theo ví dụ**; nếu API cố tình trả 404 để không tiết lộ tài nguyên, kỳ vọng test thứ hai là 404. Post-processor `jwt()` tạo authentication thử nghiệm, không chứng minh signature/issuer đã được xác thực bằng decoder thật.

### Những điều dễ bỏ sót

- Kiểm tra **cross-tenant** với user có cùng role nhưng thuộc tenant khác.
- Kiểm tra **cross-user** trong cùng tenant khi chỉ owner được xem.
- Kiểm tra share **còn hạn, hết hạn, bị revoke**, READ so với EDIT.
- Kiểm tra **owner transfer** và user bị khóa/hủy membership.
- Kiểm tra **parent-child mismatch** khi cả hai ID đều hợp lệ nhưng không có quan hệ.
- Kiểm tra **list, search, export, count, download** chứ không chỉ detail.
- Kiểm tra cập nhật đồng thời và **số dòng DB bị ảnh hưởng**.
- Kiểm tra dữ liệu lỗi và thông báo lỗi không lộ thông tin tenant khác.

## 16. Defense in depth: database RLS và audit

Một số ứng dụng multi-tenant dùng **Row-Level Security (RLS)**, chẳng hạn PostgreSQL, để giới hạn các dòng DB theo tenant và actor. Đây là lớp phòng thủ bổ sung hữu ích, nhưng không thay thế policy ở application:

- Tenant context đặt vào connection pool không đúng vòng đời có thể bị rò sang request khác.
- Database role có quyền bypass RLS có thể làm chính sách không được áp dụng.
- RLS chỉ kiểm tra tenant có thể vẫn bỏ sót owner/share.
- Một batch job hoặc service riêng có thể dùng credential khác và truy vấn vượt policy.

Nếu dùng RLS, cần xác định database role, transaction scope, session variables, reset/cleanup và các đường truy cập đặc biệt. RLS nên là **defense in depth**, không là lý do bỏ kiểm tra user–resource relationship.

Log/audit ở mức phù hợp nên ghi request ID, actor ID nội bộ, tenant, action, resource ID, kết quả `ALLOW/DENY` và lý do tổng quát. **Không log nguyên access token, refresh token, secrets hay dữ liệu riêng tư của tenant khác.** Với thao tác như approve, export, transfer ownership hoặc break-glass access, audit cần lưu thông tin cần thiết để truy vết.

## 17. Những hiểu lầm thường gặp

**“JWT có `SCOPE_orders.read` nghĩa là được xem mọi order.”** Không. Scope chỉ cho phép thao tác ở mức chức năng; phải ràng buộc tenant và quan hệ với từng order.

**“UUID không đoán được nên không cần owner check.”** Không. ID có thể bị lộ, và bảo mật không được phụ thuộc hoàn toàn vào việc giấu định danh.

**“User thuộc tenant t-7 nên đọc được toàn bộ t-7.”** Không tự động. Chính sách có thể yêu cầu owner hoặc share; tenant membership chỉ là một điều kiện.

**“`ROLE_ADMIN` là quản trị tất cả tenant.”** Không, trừ khi hệ thống cấp rõ quyền toàn cục. Vai trò thường có phạm vi tenant hoặc resource cụ thể.

**“Đã kiểm tra order cha là đủ, line con có ID nào cũng được.”** Sai. Phải xác minh line thuộc đúng order/tenant và caller có quyền với line.

**“Claim `tenant_id` trong token luôn phản ánh membership hiện tại.”** Không chắc. Membership có thể bị thu hồi khi token còn hạn; cần chính sách stale data và refresh/invalidation phù hợp.

**“@PreAuthorize bảo vệ mọi lời gọi.”** Không nếu method security chưa bật, self-invocation bỏ qua proxy hoặc có code path khác đi thẳng vào DB.

**“Client được chọn owner/tenant khi tạo order.”** Không nên. Quan hệ owner/tenant phải được server quyết định hoặc xác thực theo thao tác được cấp quyền riêng.

**“403 luôn tốt hơn 404.”** Không. Với tài nguyên ngoài phạm vi, 404 có thể giúp tránh tiết lộ sự tồn tại. Cần hợp đồng thống nhất và audit nội bộ thích hợp.

## 18. Khung tư duy khi bảo vệ endpoint nghiệp vụ

Trước khi trả hoặc thay đổi một resource:

1. **Nhận diện principal:** dùng token đã xác minh, issuer + subject hoặc client identity; ánh xạ sang actor nội bộ.
2. **Xác định action:** READ, WRITE, DELETE, EXPORT, SHARE, APPROVE, TRANSFER hay hành động khác.
3. **Kiểm tra scope/authority:** token có chức năng phù hợp không?
4. **Xác định tenant thật của resource:** từ dữ liệu được hệ thống quản lý, không chỉ request path/header.
5. **Xác minh membership hiện hành:** actor có quyền thao tác trong tenant đó không?
6. **Xác minh relationship:** owner, manager, assignment, sharing, delegation hoặc quan hệ cha–con.
7. **Kiểm tra trạng thái:** share/relation có bị revoke, hết hạn hoặc resource đã chuyển trạng thái?
8. **Ràng buộc truy vấn và ghi:** điều kiện tenant, actor/relationship, transaction, optimistic lock và số dòng tác động.
9. **Lọc dữ liệu trả ra:** field-level policy, dữ liệu danh sách, báo cáo, count và error message.
10. **Áp dụng ở mọi đường đi:** HTTP, background jobs, event consumers, internal services và các endpoint xuất dữ liệu.

**Điểm cần nhớ:** JWT hợp lệ cho biết **ai đang gọi** và quyền nào đã được cấp ở mức token. Quyết định cho phép đọc/sửa **một tài nguyên cụ thể** phải dựa trên **identity đáng tin + scope chức năng + tenant isolation + owner/share/relationship hiện hành + trạng thái nghiệp vụ**. Việc chống BOLA/IDOR nằm ở **quy tắc phân quyền dữ liệu và truy vấn được ràng buộc đúng**, không chỉ ở `authenticated()` hay việc ID khó đoán.
