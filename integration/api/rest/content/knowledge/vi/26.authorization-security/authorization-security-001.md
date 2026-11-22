# Quyền theo thao tác, vai trò, scope và thuộc tính

## 1. Đặt đúng câu hỏi phân quyền trong REST API

JWT hợp lệ không có nghĩa caller được xem đơn tenant khác, sửa giá hoặc hủy đơn đã giao. **Authentication** xác minh danh tính; **authorization** quyết định quyền.

Trong module **INTEGRATION_API_REST**, phân quyền phải đi cùng resource/URI, HTTP method/status, OpenAPI, phân trang, cache, idempotency và test: **Ai được làm gì trên resource nào, khi nào?**

OmniOrder phục vụ nhiều tenant: người mua xem đơn của mình, hỗ trợ xem đơn được phân công, quản trị viên quản lý đơn trong tenant. Biết ID không tạo ra quyền truy cập.

Sau bài học, người học cần:

1. Phân biệt **permission theo hành động**, **role (RBAC)**, **OAuth2 scope**, **attribute-based rule (ABAC)** và quan hệ owner/member (ReBAC).
2. Lập **ma trận quyền** theo resource, method, dữ liệu và trạng thái nghiệp vụ; chọn chính sách **deny by default**, đặc quyền tối thiểu.
3. Thiết kế các điểm thực thi quyền trong gateway, Spring Security, service và truy vấn dữ liệu; chống **BOLA/IDOR**, **BFLA** và over-posting.
4. Trả HTTP **401/403/404/409/412** có ngữ nghĩa, không lộ thông tin vượt quyền.
5. Kiểm thử authorization theo nhiều danh tính, tenant, resource, thuộc tính và thời điểm cập nhật.

> **Nguyên tắc:** Có scope để gọi **loại thao tác** chưa đủ chứng minh được phép thao tác trên **tài nguyên cụ thể**. Server phải kiểm **cả action lẫn object/attributes**, tại đúng thời điểm thực hiện.

## 2. Một ma trận quyền có thể kiểm thử được

Thiết kế resource theo hành vi thay vì gắn mọi quyền vào một nhãn **ADMIN**:

| HTTP operation | Permission nghiệp vụ | Điều kiện bổ sung |
|---|---|---|
| **GET /api/orders** | orders.read | Chỉ trả đơn có thể xem; lọc tenant/owner/assignment trong truy vấn |
| **GET /api/orders/{id}** | orders.read | Đơn thuộc tenant được phép và owner/assignee/manager hợp lệ |
| **POST /api/orders** | orders.create | Customer thuộc phạm vi caller; giá/tenant do server xác định |
| **PATCH /api/orders/{id}** | orders.update | Chỉ field được phép sửa, đúng trạng thái và version |
| **POST /api/orders/{id}/cancellations** | orders.cancel | Đơn chưa giao, còn thời hạn, caller có quan hệ phù hợp |
| **GET /api/orders/{id}/audit-events** | orders.audit.read | Vai trò kiểm toán, mục đích hợp lệ và tenant cho phép |

Đường dẫn ở bảng là **hợp đồng minh họa**. Việc biểu diễn hủy đơn dưới dạng resource cancellation là một lựa chọn; có thể dùng một mô hình transition khác nếu vẫn giữ method semantics và điều kiện nghiệp vụ rõ. **Không dùng GET để hủy đơn**: GET phải safe.

Một request được phép khi thỏa **tất cả** điều kiện liên quan:

~~~text
allow =
    authenticated_subject
    AND requested_action_is_granted
    AND resource_is_in_allowed_tenant
    AND required_relationship_is_true
    AND resource_state_allows_action
    AND policy_context_is_valid
~~~

Đây là **mô hình minh họa**, không thay thế policy phức tạp; cần định nghĩa các nhánh ngoại lệ minh bạch (ví dụ nhân viên hỗ trợ được giao ca, quyền truy cập khẩn cấp được kiểm soát). Quy tắc cơ bản vẫn là **thiếu dữ liệu cần kiểm quyền → từ chối**, không chuyển thành allow.

### 2.1. Hợp đồng HTTP: authorization không phải lỗi input

~~~http
GET /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Nếu token hợp lệ và đơn thuộc phạm vi được phép:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":"11111111-1111-4111-8111-111111111111","status":"CONFIRMED","totalAmount":350000}
~~~

Nếu caller không được phép thấy đơn, API có thể trả **403 Forbidden** hoặc **404 Not Found** theo chính sách che giấu sự tồn tại của tài nguyên; phải **nhất quán** để không trở thành kênh dò ID.

## 3. Permission, role, scope, attribute và quan hệ khác nhau ở đâu?

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Permission** | Được làm *hành động* gì? | orders.read, orders.cancel |
| **Role / RBAC** | Người dùng được gán nhóm permissions nào? | BUYER, SUPPORT_AGENT, TENANT_MANAGER |
| **OAuth2 scope** | Access token được cấp cho lớp năng lực API nào? | orders.read, orders.write |
| **Resource attribute / ABAC** | Điều kiện thuộc tính có thỏa? | order.tenantId, order.status, amount, caller.department |
| **Relationship / ReBAC** | Caller có quan hệ gì với resource? | order.owner, team member, assigned agent |
| **Policy context** | Yêu cầu đang diễn ra trong hoàn cảnh nào? | Đang trong cửa sổ hủy, MFA đủ mạnh, phiên được ủy quyền |

### 3.1. Permission là đơn vị diễn đạt hành vi

Permission **orders.read** rõ hơn **CAN_USE_ORDERS**; **orders.cancel** khác **orders.update** vì hủy có rủi ro cao hơn sửa ghi chú. Mỗi permission cần action/resource rõ, phạm vi (tenant/field), owner và test policy.

Đừng để **route naming** quyết định quyền một cách máy móc. **GET /orders/{id}/audit-events** không nên mặc nhiên cấp cho bất kỳ ai có orders.read. **POST /orders/{id}/cancellations** đòi quyền cancel dù URL lồng trong orders.

### 3.2. Role-based access control (RBAC)

RBAC gom permissions thành vai trò:

~~~text
BUYER          -> orders.create, orders.read (đơn thuộc mình)
SUPPORT_AGENT  -> orders.read (đơn được phân công)
TENANT_MANAGER -> orders.read, orders.update, orders.cancel (trong tenant)
AUDITOR        -> orders.audit.read (theo policy kiểm toán)
~~~

**Role không tự xác định phạm vi object.** TENANT_MANAGER ở A không được xem tenant B; với nhiều role, phải xác định tenant gắn với từng role.

RBAC có thể gây **role explosion** nếu tạo role cho mọi trạng thái/khu vực; dùng ABAC/quan hệ cho điều kiện theo bản ghi.

### 3.3. Scope của OAuth2 access token

Trong OAuth2, **scope thể hiện năng lực được authorization server cấp cho client/token**, không phải mặc nhiên toàn bộ quyền của user trên mọi object. Resource server còn phải xác minh:

1. **Token hợp lệ:** chữ ký (hoặc introspection tùy loại token), issuer, expiration/not-before theo cấu hình.
2. **Đúng audience/resource server:** token cấp cho API A không được đem sang API B.
3. **Đúng client/subject/tenant context** theo chính sách nghiệp vụ.
4. **Scope phù hợp operation**, sau đó kiểm object-level/attribute policy.

Ví dụ một access token hợp lệ có **scope=orders.read** vẫn phải bị chặn khi yêu cầu **GET /api/orders/ord-of-other-tenant**. Cũng không nên đánh đồng OAuth2 scopes với chuỗi role nội bộ: **Spring Security mặc định thường map scope/scp sang authority dạng SCOPE_...**, còn role/permission riêng phải được khai báo và map có kiểm chứng.

**ID token không phải access token cho REST API**, và không được lấy claim người dùng từ JWT client tự tạo hoặc từ header X-Role để tin là đã được cấp quyền. Khi dùng opaque token, kiểm qua cơ chế introspection đáng tin thay vì tự đoán scope từ chuỗi.

### 3.4. Attribute-based và relationship-based access

Ví dụ **orders.cancel** chỉ được cho phép nếu:

~~~text
caller.tenant == order.tenant
AND (caller.subject == order.owner
     OR caller is assigned support manager)
AND order.status IN {CREATED, CONFIRMED}
AND current_time <= order.cancellation_deadline
AND caller has permission orders.cancel
~~~

Phần trạng thái/thời hạn là **điều kiện nghiệp vụ**; scope/role là **điều kiện cấp quyền**. Có thể phối hợp trong cùng quyết định nhưng phải báo lỗi có ngữ nghĩa: nếu caller không có quyền, ưu tiên từ chối **403/404** trước khi tiết lộ rằng đơn đang ở trạng thái nào; khi đã được phép xem nhưng trạng thái không cho hủy, thường dùng **409 Conflict**.

ReBAC hữu ích khi quyền đến từ quan hệ owner, member, assignee hoặc folder/project sharing. Những quan hệ phải được lấy từ **nguồn sự thật đáng tin**, không tin request body tự khai ownerId.

## 4. Kiến trúc thực thi quyền: PEP, PDP, PIP

Một chính sách tốt cần tách **quyết định** khỏi **thực thi** để tránh kiểm tra rải rác:

~~~mermaid
flowchart LR
    C[Client] --> G[Gateway / AuthN]
    G --> P[PEP: Spring Security / service]
    P --> D[PDP: evaluate policy]
    D --> I[PIP: identity, tenant, membership, order state]
    D -->|Allow| B[Business transaction]
    D -->|Deny| E[403/404 response]
~~~

- **PEP (Policy Enforcement Point):** điểm chặn và thực thi quyết định, ví dụ filter, method interceptor và use case/repository.
- **PDP (Policy Decision Point):** tính allow/deny từ action, resource, subject và context; có thể là logic domain, policy library hoặc dịch vụ chính sách.
- **PIP (Policy Information Point):** cung cấp thuộc tính đã xác minh: tenant membership, owner, trạng thái, loại giao dịch, thời hạn.
- **PAP/administration:** quản lý chính sách, owner, phiên bản, review và audit thay đổi.

Ứng dụng nhỏ có thể dùng Spring Security + authorization service. Với PDP từ xa, cần **timeout, cache TTL và fail closed**; không cho phép ghi khi PDP không phản hồi.

### 4.1. Defense in depth, nhưng một nguồn sự thật cho quyết định

| Tầng | Kiểm tra phù hợp | Không được thay thế |
|---|---|---|
| **Gateway/WAF** | TLS, rate limit, token sơ bộ, routing | Object-level ACL và nghiệp vụ |
| **Spring Security filter** | Authentication, audience/scope và route-level guard | Tenant/owner của từng order |
| **Controller boundary** | Validate DTO, mapping HTTP, permission type | Domain invariant hoặc SQL tenant filter |
| **Application service** | Authorization theo object/action, workflow | Transaction/concurrency ở database |
| **Repository/database** | Tenant predicates, row ownership, unique/FK, RLS nếu dùng | Principal validation và policy review |

Tránh **TOCTOU**: kiểm quyền ở trạng thái cũ rồi ghi sau khi owner/status đã đổi. Dùng transaction, optimistic version, lock hoặc conditional SQL phù hợp.

### 4.2. Default deny và đặc quyền tối thiểu

**Deny by default**; scopes/roles tối thiểu theo tenant. Quyền khẩn cấp phải cấp tạm, audit mục đích, có phê duyệt và thu hồi.

Một quyền chỉ áp cho field: hỗ trợ có thể sửa địa chỉ giao hàng trước dispatch nhưng **không** sửa totalAmount hoặc merchantId. **Field-level authorization** khác validation: một field đúng kiểu Java vẫn có thể là field không được phép sửa.

## 5. Spring Security: scope ở route, quyền dữ liệu trong use case

### 5.1. Resource server kiểm access token trước khi vào controller

Trong một ứng dụng Spring Boot dùng **Spring MVC và Spring Security OAuth2 Resource Server**, có thể cấu hình các guard theo HTTP method/path như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class ApiSecurityConfiguration {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            // Chỉ khi API thuần bearer token, không dùng cookie/session
            // cho authentication trên browser:
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                // Route chuyên biệt phải trước route tổng quát.
                .requestMatchers(HttpMethod.GET,
                        "/api/orders/*/audit-events")
                    .hasAuthority("SCOPE_orders.audit.read")
                .requestMatchers(HttpMethod.POST,
                        "/api/orders/*/cancellations")
                    .hasAuthority("SCOPE_orders.cancel")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.update")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Chú ý kỹ thuật:**

- Cần dependency **spring-boot-starter-security** và **spring-boot-starter-oauth2-resource-server**, cùng JwtDecoder/issuer và audience validator phù hợp. Một bean SecurityFilterChain không tự cấu hình nguồn xác minh token.
- **Thứ tự matcher quan trọng**: nếu GET /api/orders/** đứng trước GET /api/orders/*/audit-events, người có orders.read có thể vào endpoint audit mà không có quyền audit.
- Với cấu hình converter thông thường, JWT **scope/scp** được map sang **SCOPE_orders.read**. Nếu authorization server phát claim khác, phải cấu hình JwtAuthenticationConverter, không giả định hasAuthority tự hiểu.
- **Không tự động tin role admin trong token** là quyền xuyên tenant. Nếu hệ thống cần role, có thể dùng hasRole("TENANT_MANAGER") khi đã map thành ROLE_TENANT_MANAGER và kiểm phạm vi tenant riêng.
- Tắt CSRF chỉ thích hợp khi API xác thực bằng bearer header và **không dựa vào cookie tự gửi**. Với phiên đăng nhập browser/cookie, cần thiết kế bảo vệ CSRF đúng mô hình.
- Nếu có actuator, OpenAPI UI hay health routes, phải khai báo **chủ đích** quyền tương ứng; denyAll mặc định giúp endpoint mới không lộ ngoài ý muốn.

### 5.2. Từ Jwt đến Actor đáng tin

Controller có thể nhận principal do Spring Security đã kiểm chứng:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import java.util.UUID;

record Actor(String subject, String tenantId) {}
record OrderView(UUID id, String status, long totalAmount) {}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrderQueryService queries;

    OrdersController(OrderQueryService queries) {
        this.queries = queries;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable UUID id,
            @AuthenticationPrincipal Jwt jwt) {
        Actor actor = verifiedActor(jwt);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(queries.findVisible(id, actor));
    }

    private Actor verifiedActor(Jwt jwt) {
        String subject = jwt.getSubject();
        String tenant = jwt.getClaimAsString("tenant_id");
        if (subject == null || subject.isBlank()
                || tenant == null || tenant.isBlank()) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Missing required authorization context");
        }
        return new Actor(subject, tenant);
    }
}
~~~

Đây là **fragment** cho ứng dụng đã cấu hình JWT authentication; không gọi trực tiếp controller bằng JWT chưa xác minh. **tenant_id claim chỉ có thể tin nếu issuer/audience/claim contract đáng tin**; với tài khoản có quyền ở nhiều tenant, cần đối chiếu membership và tenant đang hoạt động trong hệ thống. Không đọc tenant từ request query/body rồi gán vào Actor.

Nếu token không có tenant hợp lệ theo chính sách, từ chối; không fallback sang tenant mặc định hoặc lấy tenant từ order ID. Với service-to-service token, subject có thể đại diện ứng dụng chứ không phải người dùng: policy cần nêu rõ delegated user, client identity, purpose và quyền được ủy quyền.

### 5.3. Chặn BOLA bằng truy vấn lọc dữ liệu

Một use case đọc **đơn của owner** có thể thực hiện điều kiện quyền ngay trong repository:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

interface OrderRepository {
    // Query cần WHERE id, tenant_id, owner_subject đồng thời.
    java.util.Optional<OrderRecord> findByIdAndTenantIdAndOwnerSubject(
            UUID id, String tenantId, String ownerSubject);
}

@Service
class OrderQueryService {
    private final OrderRepository repository;

    OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderView findVisible(UUID id, Actor actor) {
        OrderRecord order = repository
            .findByIdAndTenantIdAndOwnerSubject(
                id, actor.tenantId(), actor.subject())
            .orElseThrow(OrderNotVisibleException::new);
        return new OrderView(
            order.getId(), order.getStatus(), order.getTotalAmount());
    }
}
~~~

**OrderRecord và OrderNotVisibleException là kiểu ứng dụng cần định nghĩa.** Ví dụ chỉ mô tả nhánh **owner**; để hỗ trợ assignee/tenant manager cần thêm quan hệ đã xác minh hoặc một repository query **visible to actor**. Không xóa tenant predicate chỉ vì user có role quản trị tenant. Khi không tìm thấy bản ghi được phép xem, map thành **404** theo policy; việc kiểm tra scope có thể trả **403** trước khi query.

**Lọc tenant trong SQL** giảm lộ entity và bảo đảm pagination đúng phạm vi. Test query thực cho từng quan hệ; tên repository method không bảo đảm câu SQL an toàn.

### 5.4. Method security và kiểm tra object-level

**@EnableMethodSecurity** kích hoạt các annotation như **@PreAuthorize**. Ví dụ use case hủy:

~~~java
@Service
class CancelOrderService {
    private final OrderPolicy policy;
    private final OrderRepositoryForUpdate orders;

    CancelOrderService(
            OrderPolicy policy, OrderRepositoryForUpdate orders) {
        this.policy = policy;
        this.orders = orders;
    }

    @Transactional
    @PreAuthorize("hasAuthority('SCOPE_orders.cancel')")
    public void cancel(UUID id, Actor caller) {
        var order = orders.findByIdAndTenantForUpdate(
                id, caller.tenantId())
            .orElseThrow(OrderNotVisibleException::new);
        policy.requireCanCancel(caller, order); // tenant, owner, state
        order.cancel();                        // domain transition
    }
}
~~~

Đoạn mã là **fragment**: OrderPolicy, repository lock, trạng thái và entity cần triển khai. Query **findByIdAndTenantForUpdate** phải lọc tenant ngay trong SQL; **OrderPolicy kiểm quan hệ owner/assignee và điều kiện hủy trước khi lộ trạng thái**. Phần chuyển trạng thái phải dùng optimistic/row locking hoặc điều kiện ghi để tránh race condition; test bằng DB transaction thật.

Với biểu thức @PreAuthorize có bean kiểm object, ví dụ **@orderPolicy.canRead(authentication, #id)**, phải coi DB lookup trong policy là một phần thiết kế hiệu năng/bảo mật; không chạy một query vô hạn mỗi item. Lưu ý **Spring proxy-based method security không áp dụng cho self-invocation thông thường**; lời gọi nội bộ trong cùng bean có thể bỏ qua interceptor. Vì vậy **service policy/DB filter không được chỉ dựa vào proxy annotation**.

**Field-level update:** DTO nhận input như shippingAddress, không chứa tenantId, totalAmount hoặc ownerSubject. Validation @NotBlank chỉ kiểm định dạng; việc ai được sửa field nào phụ thuộc policy. Tránh bind **@RequestBody trực tiếp vào JPA entity** (mass assignment/over-posting).

## 6. Mã HTTP, Problem Details và không tiết lộ thông tin vượt quyền

| Tình huống | HTTP status | Giải thích |
|---|---|---|
| Thiếu access token ở API protected | **401 Unauthorized** | Cần xác thực; giữ WWW-Authenticate thích hợp |
| Token hết hạn/sai chữ ký/issuer/audience | **401** | Không biến token lỗi thành 403 |
| Token hợp lệ nhưng thiếu scope/permission | **403 Forbidden** | Không cấp hành động được yêu cầu |
| Scope đủ nhưng object thuộc tenant khác | **403 hoặc 404** | Theo chính sách che giấu; không trả 200/null |
| Object không tồn tại | **404 Not Found** | Không khẳng định đã kiểm quyền chỉ vì trả 404 |
| Caller đủ quyền nhưng trạng thái không cho thao tác | **409 Conflict** | Ví dụ đơn đã giao, không thể hủy |
| Caller đủ quyền nhưng If-Match không khớp | **412 Precondition Failed** | Không ghi đè phiên bản mới |
| Request JSON hoặc field sai kiểu | **400** (hoặc 422 theo contract) | Validation khác authorization |
| Policy engine/DB xác minh quyền mất kết nối | **5xx có kiểm soát** hoặc fail-closed | Không mặc nhiên allow; không giả thành 404 nếu không biết dữ liệu |

### 6.1. 401 phải phản ánh authentication challenge

~~~http
GET /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Accept: application/json

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
~~~

Với bearer token không hợp lệ, entry point có thể bổ sung mã lỗi chuẩn theo giao thức; **không đưa token hoặc lý do xác minh bí mật vào body**. Một client không thể tự khắc phục 403 bằng cách retry nguyên request; với 401, việc refresh token chỉ nên diễn ra theo cơ chế cấp token hợp lệ, có giới hạn.

### 6.2. 403/404 và chính sách chống enumeration

Nếu tenant A hỏi ID của tenant B, hệ thống có thể che bằng 404:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Không tìm thấy đơn có thể truy cập",
  "code": "ORDER_NOT_FOUND"
}
~~~

Theo **Problem Details (RFC 9457)**, **type/title/status/detail/instance** có ngữ nghĩa chuẩn; **code** là extension do API định nghĩa. Không phân biệt thông báo “order tồn tại nhưng không có quyền” với “ID không tồn tại” nếu chính sách muốn che giấu. Ngoài body/status, xem xét cả **thời gian phản hồi, header, kích thước response, cache và logging exposure**.

Tuy nhiên, **404 không phải luôn tốt hơn 403**. Ví dụ một người đã được quyền biết project tồn tại nhưng thiếu quyền export: 403 có thể rõ ràng, hữu ích hơn. Chọn một policy được document và test cho từng loại resource/operation.

### 6.3. Security filter và exception advice có phạm vi khác nhau

**Spring Security AuthenticationEntryPoint/AccessDeniedHandler** thường xử lý lỗi 401/403 trước hoặc ngoài controller. **@RestControllerAdvice** phù hợp ánh xạ lỗi domain/validation từ controller/service, ví dụ **OrderNotVisibleException → 404** và **OrderStateConflictException → 409**.

Đừng nghĩ một advice bắt RuntimeException là đủ chuẩn hóa mọi auth error. Nếu muốn 401/403 trả **application/problem+json**, phải cấu hình security handlers tương ứng, **giữ WWW-Authenticate cho 401**, dùng cùng error taxonomy, và kiểm thử response HTTP thật.

Một response lỗi cần **code ổn định**, correlation/trace identifier theo policy, nhưng không lộ role nội bộ, tenant khác, SQL, stack trace hoặc raw claim/token. **Cache-Control: no-store** là lựa chọn an toàn phổ biến cho response nhạy cảm; cache policy phải xét representation và điều kiện sản phẩm.

## 7. Phân quyền phải đi qua cả danh sách, cache, cập nhật và batch

### 7.1. Collection query: lọc ở database, trước phân trang

Ví dụ GET /api/orders?limit=20&cursor=... phải lọc theo tenant và quan hệ có quyền **trước khi LIMIT/cursor được áp dụng**. Nếu lấy 20 bản ghi toàn hệ thống rồi mới lọc ở Java, client có thể nhận trang ít dữ liệu, total count sai hoặc suy được thông tin tenant khác.

~~~sql
SELECT o.id, o.status, o.total_amount
FROM orders AS o
WHERE o.tenant_id = :verified_tenant
  AND (
       o.owner_subject = :verified_subject
       OR EXISTS (
           SELECT 1 FROM order_assignments AS a
           WHERE a.order_id = o.id
             AND a.agent_subject = :verified_subject
       )
  )
  AND (o.created_at, o.id) < (:cursor_time, :cursor_id)
ORDER BY o.created_at DESC, o.id DESC
LIMIT :page_limit;
~~~

Đây là **keyset pagination minh họa**, yêu cầu chỉ áp cursor predicate khi có cursor; cú pháp so tuple và index tùy database. Với manager được phép xem mọi order trong tenant, nhánh policy phải được bổ sung **một cách có kiểm soát** chứ không bỏ điều kiện tenant. Không trả tổng số record toàn cục hoặc cursor có thể dùng để vượt ACL.

### 7.2. ETag, 304 và chia sẻ cache

GET có If-None-Match chỉ được trả **304 Not Modified sau khi đã xác thực, xác minh quyền và xác định selected representation**. Nếu user bị thu hồi quyền, không được trả 304 chỉ vì ETag của lần đọc cũ khớp: điều đó có thể xác nhận tài nguyên vẫn tồn tại và cho phép cache cũ được dùng trái quyền.

Với dữ liệu riêng tư, cân nhắc **Cache-Control: no-store**. Nếu dùng private cache/revalidation, cache key phải phụ thuộc đúng **identity/authorization dimensions** theo thiết kế. **Vary: Authorization không tự giải quyết mọi rủi ro chia sẻ cache**; cần cấu hình gateway/CDN, quyền và cache invalidation thực tế.

### 7.3. PATCH, field-level authorization và lost update

~~~http
PATCH /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "order-v7"

{"shippingAddress":{"city":"Hue"}}
~~~

Trước khi áp dụng, server cần kiểm **quyền update**, quyền chỉnh **shippingAddress**, tenant/owner và trạng thái đơn, sau đó đánh giá precondition/version. Nếu caller không có quyền xem order, không trả thông tin version; nếu đã được phép nhưng ETag không khớp, **412**. Không cho client PATCH tenantId, ownerSubject, totalAmount hoặc role/permission fields chỉ vì JSON hợp lệ.

Một authorization check trước transaction và một lệnh UPDATE sau đó có thể bị race. Dùng row lock/optimistic version hoặc **UPDATE ... WHERE tenant_id = ... AND version = ... AND status = ...**, rồi kiểm row count, để quyết định không lệch khỏi thời điểm ghi.

### 7.4. Batch, export và dữ liệu phát sinh

Với **POST /api/orders/batch-cancel** hoặc export CSV, không chỉ kiểm scope ở endpoint một lần: phải đánh giá **quyền trên từng item** và xác định all-or-nothing hay partial success theo contract. Job bất đồng bộ cần kiểm danh tính/quyền tại thời điểm nhận **và trước lúc xuất dữ liệu hoặc thực hiện side effect**, nhất là khi token/quyền có thể bị thu hồi. Export, notification, search index, pre-signed URL và websocket cũng không được bỏ qua ACL chỉ vì không đi qua controller GET thông thường.

**Authorization là bất biến hệ thống**, không chỉ là annotation trên một handler.

## 8. OpenAPI ghi quyền thao tác, không tự thực thi object ACL

OpenAPI có thể mô tả OAuth2 scopes cho từng HTTP operation:

~~~yaml
openapi: 3.1.0
info:
  title: OmniOrder API
  version: 1.0.0
paths:
  /api/orders/{id}:
    get:
      operationId: getOrder
      security:
        - ordersOAuth: [orders.read]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200': {description: Order visible to current caller}
        '401': {description: Authentication required}
        '403': {description: Forbidden}
        '404': {description: Not found or hidden by access policy}
  /api/orders/{id}/cancellations:
    post:
      operationId: cancelOrder
      security:
        - ordersOAuth: [orders.cancel]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '201': {description: Cancellation created}
        '401': {description: Authentication required}
        '403': {description: Forbidden}
        '404': {description: Order not visible}
        '409': {description: Order state does not permit cancel}
components:
  securitySchemes:
    ordersOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.test/oauth2/authorize
          tokenUrl: https://identity.example.test/oauth2/token
          scopes:
            orders.read: Read orders permitted by resource policy
            orders.cancel: Request permitted order cancellations
~~~

Đây là **ví dụ OAS 3.1 chưa mô tả đủ** response body, media type, schema và header; flow authorizationCode chỉ phù hợp một loại client. Với service-to-service có thể dùng clientCredentials hoặc phương án khác phù hợp nhà cấp token. **Một scope trong OAS không nói rằng mọi order đều được phép đọc**: tenant, owner/assignment, state và field-level policy phải được giải thích trong tài liệu nghiệp vụ và thi hành ở runtime.

Khi thêm endpoint mới, review cả **router guard, service policy, query predicate, OpenAPI security và tests**. Một linter kiểm thiếu security declaration có ích, nhưng không chứng minh enforcement hoặc chống IDOR/BOLA.

## 9. Kiểm thử authorization: chứng minh không thể vượt ranh giới

### 9.1. Ma trận negative tests

| Subject/resource/action | Mong đợi |
|---|---|
| Không có token, GET đơn private | **401** và challenge hợp lệ |
| Token giả/hết hạn/sai issuer hoặc audience | **401**; không vào service |
| Có orders.read, không có orders.cancel, gọi cancel | **403** |
| Có orders.read, order thuộc tenant khác | **404/403** đúng policy, không lộ dữ liệu |
| TENANT_MANAGER ở A truy vấn order B | **Không được phép** |
| Owner ở đúng tenant, order hợp lệ | **200** và body chỉ chứa field được phép |
| SUPPORT_AGENT chưa được phân công | **Không được phép** dù vai trò hỗ trợ hợp lệ |
| Có quyền cancel nhưng order đã giao | **409** sau khi đã xác nhận quyền |
| Có quyền update nhưng sửa field price/owner | **Từ chối**, không ghi thay đổi |
| If-Match cũ sau khi có quyền update | **412**, không mất bản ghi mới |
| List với limit/cursor | Chỉ record có quyền, count/cursor không rò tenant khác |
| Policy dependency lỗi hoặc claim tenant thiếu | **Fail closed**, có log/alert an toàn |
| Quyền bị thu hồi rồi GET với ETag cũ | Không trả **304** nếu không còn quyền |
| Hai thao tác cập nhật đồng thời | Kiểm authorization + trạng thái đúng tại thời điểm commit |

**BOLA** là truy cập object khác qua ID; **BFLA** là vượt quyền ở endpoint; **Broken Object Property Level Authorization** là đọc/ghi field trái phép. Luôn kiểm test âm tính.

### 9.2. MockMvc với JWT principal giả lập

Ví dụ fragment JUnit/Spring Security Test, giả định đã cấu hình MockMvc, OrdersController, OrderQueryService và repository fixtures; ID hợp lệ theo kiểu UUID của controller:

~~~java
UUID otherTenantOrder =
    UUID.fromString("11111111-1111-4111-8111-111111111111");

mockMvc.perform(get("/api/orders/{id}", otherTenantOrder)
        .with(jwt()
            .jwt(token -> token.subject("buyer-17")
                .claim("tenant_id", "tenant-A"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isNotFound())
    .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));

mockMvc.perform(get("/api/orders/{id}", otherTenantOrder)
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_unrelated"))))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/api/orders/{id}", otherTenantOrder))
    .andExpect(status().isUnauthorized());
~~~

**Test fixture phải bảo đảm repository không trả order B cho Actor tenant A**; nếu mock service luôn ném 404, test trên không chứng minh SQL tenant predicate. Bổ sung integration test với DB thật/Testcontainers gồm order của A và B, cùng ID/quan hệ cụ thể, để kiểm cả query, pagination và field serialization.

**jwt() là mock authentication**, không kiểm chữ ký/issuer/audience/expiry; cần JwtDecoder/integration test riêng. Mã test là fragment cần imports và fixtures.

### 9.3. Kiểm thử policy như một hàm quyết định

Một OrderPolicy thuần logic có thể được test theo **decision table**:

~~~text
subject + scopes + roles + membership
        + order.tenant + order.owner + state
        -> ALLOW / DENY + reason code nội bộ
~~~

Những ca quan trọng: permission đúng nhưng tenant sai; role đúng nhưng assignment thiếu; owner đúng nhưng status không hủy được; quyền được thu hồi; policy context thiếu; role cùng tên ở tenant khác; đơn chuyển owner giữa lúc xử lý. Với authorization theo thời gian, inject Clock cố định để test ranh giới trước/đúng/sau deadline.

Lỗi chính sách quan trọng cần audit **ai**, **hành động**, **resource type**, **kết quả**, **policy version** và correlation ID theo quy định, nhưng tránh log PII hoặc hàng triệu metric labels theo từng order ID. Cần quản lý retention và quyền đọc audit.

## 10. Bài tập thực hành

**Bài 1 — RBAC không đủ.** Người quản lý tenant A có vai trò TENANT_MANAGER và scope orders.read, gọi GET /api/orders/{id} với ID thuộc tenant B. Vì sao phải từ chối? **Đáp án:** Role/scope chỉ cấp loại hành động; ABAC bắt buộc so tenant và quan hệ có quyền từ dữ liệu được xác minh. Không trả order B.

**Bài 2 — Sai thứ tự matcher.** Route GET /api/orders/** cho orders.read được khai báo trước GET /api/orders/*/audit-events cho orders.audit.read. **Đáp án:** Route tổng quát có thể match trước, mở lối truy cập audit bằng scope read. Đưa matcher audit lên trước, test riêng.

**Bài 3 — 403 hay 409?** Caller có scope cancel nhưng đơn đã giao; caller khác thiếu quyền cancel cũng yêu cầu ID đó. **Đáp án:** Caller thiếu quyền → 403/404 theo policy, không tiết lộ status; caller được phép nhưng state không cho hủy → 409.

**Bài 4 — Pagination và field update.** API lấy 20 đơn toàn hệ thống rồi lọc tenant trong Java; PATCH bind thẳng JSON vào JPA entity. **Đáp án:** Query phải lọc quyền trước phân trang; dùng request DTO allowlist field, policy và conditional update để chống BOLA và over-posting.

**Bài 5 — JWT và test.** MockMvc với jwt() trả 200, vậy đã chứng minh token sai chữ ký không được chấp nhận? **Đáp án:** Chưa. MockJwt không xác minh chữ ký; cần JwtDecoder/integration tests thực và kiểm scope/tenant ở service.

**Bài 6 — Policy unavailable.** Dịch vụ phân quyền từ xa timeout trong lúc tạo đơn, code trả allow để tránh gián đoạn. **Đáp án:** Sai với thao tác nhạy cảm; fail closed, trả lỗi 5xx an toàn, retry theo contract và alert vận hành. Không ghi nghiệp vụ khi quyết định quyền chưa chắc chắn.

## 11. Checklist và kết luận

- [ ] Mỗi endpoint/resource/action có permission, owner và policy rõ?
- [ ] Role khác scope; token có issuer/audience/signature/expiry được kiểm tra?
- [ ] Default deny; đặc quyền tối thiểu; role/tenant membership được xác minh?
- [ ] Service/query lọc tenant/owner/assignment, không chỉ kiểm quyền tại gateway?
- [ ] Field-level access, trạng thái và version được kiểm trong transaction?
- [ ] 401/403/404/409/412 đúng ngữ nghĩa, không để lộ thông tin resource khác?
- [ ] Pagination, cache/304, batch/export/background job cũng thực thi ACL?
- [ ] OpenAPI mô tả scopes và lỗi; runtime thực thi ABAC/ReBAC độc lập?
- [ ] Test cả path đúng quyền, sai scope, sai tenant, role khác, concurrency và policy outage?
- [ ] Audit có mục đích, giới hạn dữ liệu nhạy cảm và theo dõi thay đổi policy?

**Kết luận:** **Permission** chỉ hành động, **role** nhóm năng lực, **OAuth2 scope** giới hạn token; **attributes và relationships** quyết định có thể thực hiện hành động ấy trên **bản ghi cụ thể** hay không. Một REST API an toàn cần authorization ở route **và** service/query, deny by default, kiểm lại tại thời điểm ghi, mã HTTP có ngữ nghĩa và negative tests bao phủ mọi ranh giới tenant, đối tượng, field và trạng thái.
