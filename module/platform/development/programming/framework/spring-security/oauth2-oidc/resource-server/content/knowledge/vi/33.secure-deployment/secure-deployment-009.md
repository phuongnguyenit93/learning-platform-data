# Cô lập tenant và kiểm tra quyền đối với dữ liệu nghiệp vụ

## 1. Vì sao xác thực token chưa đủ để bảo vệ dữ liệu nhiều tenant?

Một OAuth 2.0 Resource Server có thể xác minh access token hoàn toàn chính xác nhưng vẫn để lộ dữ liệu nếu tầng nghiệp vụ không giới hạn truy vấn theo tenant.

Giả sử hệ thống SaaS quản lý đơn hàng cho nhiều doanh nghiệp:

- Tenant **blue** có order 1001.
- Tenant **red** có order 2001.
- User Alice thuộc tenant blue.
- User Bob thuộc tenant red.

Alice gửi:

~~~http
GET /api/orders/2001 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <valid-access-token-for-alice>
~~~

Token có chữ ký hợp lệ, issuer đúng, audience là orders-api và scope có orders.read. Authentication thành công. Nhưng nếu code chỉ truy vấn:

~~~sql
SELECT * FROM orders WHERE id = :orderId
~~~

thì Alice có thể đọc order của tenant red nếu biết hoặc đoán được ID 2001.

Đây là lỗi **Broken Object Level Authorization (BOLA)**, thường được gọi là IDOR trong các tình huống truy cập object bằng ID. Token hợp lệ không tự chứng minh caller có quyền với mọi object trong API.

Một quyết định cho phép truy cập dữ liệu tenant cần ít nhất:

~~~text
Valid access token
  AND required API scope
  AND authenticated actor belongs to requested tenant
  AND resource belongs to that tenant
  AND actor has permission for this operation
  AND business state permits the operation
~~~

**Tenant isolation là một ranh giới bảo mật ở mọi tầng truy cập dữ liệu.** Nó cần được thực thi trong routing/context, service, repository/query, cache, background jobs, event consumers và các luồng export/search.

## 2. Phân biệt authentication, tenant resolution và authorization

Ba khái niệm thường bị gộp nhầm:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Authentication** | Ai đang gọi API? | Issuer + subject hoặc client identity |
| **Tenant resolution** | Request đang làm việc trong tenant nào? | Tenant từ path hoặc host được kiểm tra |
| **Authorization** | Actor này được làm gì trên resource đó? | Đọc order của tenant, sửa order đang mở |

Một access token có thể chứng minh actor được issuer xác thực. Nó có thể chứa tenant claim, nhưng claim đó vẫn cần được diễn giải theo contract của issuer và domain.

Một tenant ID trong URL:

~~~text
/api/tenants/blue/orders/1001
~~~

chỉ thể hiện **tenant context được yêu cầu**. Nó không chứng minh caller là thành viên của tenant blue.

Tương tự, header:

~~~http
X-Tenant-Id: blue
~~~

là dữ liệu do request cung cấp. Nếu không xác minh membership, header này có thể trở thành cách caller chọn tenant của người khác.

### Ba quyết định phải được thực hiện riêng

1. Spring Security xác minh access token.
2. Ứng dụng xác định tenant context và kiểm tra actor có quyền sử dụng tenant đó.
3. Domain service/repository chỉ thao tác trên resource thuộc tenant đã được xác minh, rồi kiểm tra quyền nghiệp vụ cụ thể.

Không lấy thành công ở bước 1 làm kết luận tự động cho bước 2 và 3.

## 3. Danh tính ổn định: issuer, subject và actor kind

Trong OAuth/OIDC, claim sub thường nhận diện subject trong phạm vi issuer. Hai issuers có thể cùng phát sub=user-42 nhưng đó có thể là hai người hoặc hai account độc lập.

Khi map external identity sang local identity, nên dùng:

~~~text
ExternalIdentity = (issuer, subject)
~~~

Ví dụ:

~~~text
(https://auth-a.example.com/, user-42)
(https://auth-b.example.com/, user-42)
~~~

là hai identity keys khác nhau.

Với client credentials, token có thể đại diện machine client thay vì human user. Khi đó actor key có thể dựa trên issuer + client_id theo contract:

~~~text
USER actor:
  issuer + sub

CLIENT actor:
  issuer + client_id
~~~

Không dùng email hoặc username làm identity key duy nhất nếu issuer không cam kết tính duy nhất, ổn định và account-linking semantics.

### Tenant membership không đồng nghĩa với subject claim

Một JWT có thể chứa:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["orders-api"],
  "tenant_id": "blue",
  "scope": "orders.read orders.write"
}
~~~

Nếu issuer phát hành tenant_id sau khi kiểm tra membership và Resource Server tin cậy đúng issuer/profile đó, claim có thể là một đầu vào authorization. Nhưng cần biết:
- Tenant claim đại diện tenant mặc định, tenant đang được chọn hay toàn bộ memberships?
- Claim có được cập nhật khi membership bị thu hồi không?
- Token lifetime dài bao lâu?
- API có yêu cầu membership freshness ngay lúc request không?
- Một user có thể thuộc nhiều tenant không?
- Token có thể được cấp cho user và machine client với semantics khác nhau không?

Nếu membership thay đổi nhanh, chỉ dựa trên claim snapshot trong JWT có thể không đáp ứng revoke SLA. Có thể cần truy vấn membership hiện hành hoặc một version/cache invalidation policy.

## 4. Nguồn tenant context và mức độ tin cậy

Tenant context thường được lấy từ một trong các nguồn:

| Nguồn | Có thể dùng để làm gì? | Điều kiện |
|---|---|---|
| Path parameter | Tenant được yêu cầu cho resource | Kiểm tra actor membership |
| Subdomain/host | Chọn tenant workspace | Host mapping phải được cấu hình và xác minh |
| JWT claim | Tenant context do issuer phát hành | Token đã verify, claim semantics rõ |
| Opaque introspection attribute | Tenant metadata từ AS | Introspection active và issuer contract đáng tin |
| Header do gateway thêm | Context do gateway xác minh | Strip header caller gửi, trust gateway-to-service |
| Request body | Tenant target cho thao tác tạo/di chuyển | Chỉ dùng sau authorization rõ ràng |
| Query parameter | Bộ lọc tenant được yêu cầu | Không xem là proof of membership |

### Requested tenant khác authenticated tenant

Một API có thể nhận tenant trong path:

~~~http
GET /api/tenants/blue/orders/1001
Authorization: Bearer <token>
~~~

Service phải xác minh actor thuộc tenant blue hoặc có quyền cross-tenant được cấp rõ.

Không nên:
- Lấy tenant từ path rồi tin ngay.
- Tin X-Tenant-Id mà không xác minh nguồn.
- Cho phép body tenantId ghi đè tenant context đã được xác thực.
- Dùng tenant từ request trước đó trong ThreadLocal hoặc mutable singleton.
- Chọn tenant bằng cách decode JWT payload chưa verify.

### Gateway header

Nếu trusted gateway thêm X-Verified-Tenant:
1. Backend chỉ nhận traffic qua gateway được bảo vệ.
2. Gateway loại bỏ header cùng tên do client tự gửi.
3. Gateway tạo header từ identity/context đã xác minh.
4. Gateway-to-backend connection được bảo vệ bằng mTLS hoặc network boundary phù hợp.
5. Backend chỉ chấp nhận header này trên route có contract tương ứng.

Header nội bộ không tự đáng tin chỉ vì tên có chữ Verified.

## 5. Tenant context phải được tạo từ principal đã xác thực

Trong WebFlux, controller có thể nhận OAuth2AuthenticatedPrincipal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class TenantOrdersController {

    private final TenantAccessService tenantAccessService;
    private final OrdersService ordersService;

    public TenantOrdersController(
            TenantAccessService tenantAccessService,
            OrdersService ordersService) {
        this.tenantAccessService = tenantAccessService;
        this.ordersService = ordersService;
    }

    @GetMapping("/api/tenants/{tenantId}/orders/{orderId}")
    public Mono<OrderView> getOrder(
            @PathVariable String tenantId,
            @PathVariable String orderId,
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {

        return tenantAccessService.resolve(principal, tenantId)
                .flatMap(context ->
                        ordersService.findOrder(context, orderId));
    }
}
~~~

OAuth2AuthenticatedPrincipal là abstraction phù hợp khi ứng dụng hỗ trợ cả JWT principal và opaque-token principal. Với JWT-only API, controller cũng có thể nhận Jwt/JwtAuthenticationToken. Hãy dùng đúng principal type của security strategy đã cấu hình.

**Không truyền raw Bearer token xuống domain service** nếu service chỉ cần actor identity và tenant context. Giảm phạm vi credential giúp tránh log hoặc lưu token ngoài ý muốn.

### Principal có thể không có tenant_id

Nếu API dùng tenant trong path và membership store, principal không cần phải chứa một tenant mặc định. Điều quan trọng là issuer + subject hoặc client identity đã xác thực và membership được kiểm tra theo tenant yêu cầu.

## 6. Resolve tenant bằng membership service

Một service có thể xây dựng TenantContext sau khi xác minh membership:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class TenantAccessService {

    private final TenantMembershipRepository memberships;

    public TenantAccessService(TenantMembershipRepository memberships) {
        this.memberships = memberships;
    }

    public Mono<TenantContext> resolve(
            OAuth2AuthenticatedPrincipal principal,
            String requestedTenantId) {

        String issuer = principal.getAttribute("iss");
        String subject = principal.getAttribute("sub");

        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            return Mono.error(new AccessDeniedException(
                    "A user identity is required"));
        }

        return memberships.existsActiveMembership(
                        issuer, subject, requestedTenantId)
                .filter(Boolean::booleanValue)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Tenant access is not permitted")))
                .thenReturn(new TenantContext(
                        issuer, subject, requestedTenantId));
    }
}
~~~

Các type minh họa:

~~~java
public record TenantContext(
        String issuer,
        String subject,
        String tenantId) {
}
~~~

Repository contract:

~~~java
public interface TenantMembershipRepository {
    Mono<Boolean> existsActiveMembership(
            String issuer,
            String subject,
            String tenantId);
}
~~~

Điểm cần chú ý:
- Kiểm tra identity fields trước khi dùng.
- Membership key dùng issuer + subject + tenant.
- Chỉ membership active mới được tạo TenantContext.
- Không tạo tenant context mặc định khi principal thiếu dữ liệu.
- Repository phải query membership theo identity namespace đúng.
- Nếu actor là machine client, cần resolver/contract riêng theo client identity thay vì giả định luôn có sub.

Đây là ví dụ reactive. Repository implementation phải trả Mono<Boolean> và không gọi blocking database driver trong event loop.

### Không để controller tự quyết định membership

Nếu mỗi controller tự viết điều kiện tenant khác nhau, một endpoint mới dễ bỏ sót check. Đưa resolution vào service dùng chung, policy component hoặc method-security layer phù hợp giúp các routes có cùng semantics.

## 7. TenantContext là dữ liệu đã được kiểm tra, không phải header thô

Một TenantContext trong domain có thể chứa:

~~~java
public record TenantContext(
        String issuer,
        String subject,
        String tenantId) {
}
~~~

Trong ứng dụng phức tạp, có thể bổ sung:
- actorKind (USER hoặc CLIENT).
- localActorId.
- membershipId.
- membershipVersion.
- permitted roles/permissions.
- request correlation ID.
- authentication method/context nếu business policy cần.

Không nên lưu raw access token trong TenantContext.

Tạo TenantContext sau khi:
1. Authentication thành công.
2. Identity được normalize theo issuer/subject hoặc client identity.
3. Requested tenant được xác minh.
4. Membership/tenant permission hiện hành được kiểm tra.
5. Context được gắn với request/reactive chain hiện tại.

TenantContext là kết quả của một bước authorization. Nó không nên là singleton mutable state dùng chung giữa requests.

## 8. Cấu hình WebFlux Resource Server và coarse-grained scope

Spring Security có thể bảo vệ route theo scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ResourceServerSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.write")
                        .pathMatchers(HttpMethod.PUT, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.write")
                        .pathMatchers(HttpMethod.DELETE, "/api/tenants/**")
                            .hasAuthority("SCOPE_orders.delete")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Đây là coarse-grained authorization: route yêu cầu scope tương ứng. Nó chưa biết order cụ thể thuộc tenant nào, user có membership nào hoặc order đang ở state nào.

Vì vậy scope check phải được kết hợp với tenant/object/business checks trong service hoặc method authorization.

### Scope không thay ownership

Token có SCOPE_orders.read không có nghĩa actor đọc được mọi order trong mọi tenant.

~~~text
SCOPE_orders.read
  -> Được phép gọi loại API đọc order

Tenant membership
  -> Được phép làm việc trong tenant blue

Order tenant filter
  -> Order 1001 thật sự thuộc tenant blue

Domain policy
  -> Actor được phép xem order 1001 theo ownership/state
~~~

Mỗi điều kiện trả lời một câu hỏi khác nhau.
## 9. Reactive method security và tenant-aware service

Có thể bật reactive method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Dùng @PreAuthorize cho scope/coarse permission:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrdersService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderView> findOrder(
            TenantContext tenant,
            String orderId) {
        return repository.findByIdAndTenantId(
                orderId, tenant.tenantId());
    }
}
~~~

Đây là ví dụ minh họa. Repository method phải thực sự lọc tenant trong database query, không tải object theo ID trước rồi chỉ tin tham số tenant ở controller.

**@PreAuthorize scope check không thay object-level authorization.** Nếu method được gọi từ một internal path hoặc một service khác không đi qua cùng security proxy, tenant isolation vẫn phải được giữ trong service/repository contract.

### Không chỉ dựa trên method security

Business methods có thể được gọi từ:
- HTTP controller.
- Scheduled task.
- Message consumer.
- Internal service.
- Admin workflow.
- Batch import/export.

Nếu chỉ có filter chain hoặc annotation trên một controller, các đường gọi khác có thể bỏ qua nó. Đặt tenant predicate và domain checks ở lớp dữ liệu/service dùng chung.

## 10. Luôn đưa tenantId vào truy vấn dữ liệu

Sai:

~~~java
Mono<Order> findOrder(String orderId) {
    return databaseClient.sql(
            "SELECT id, tenant_id, status FROM orders WHERE id = :id")
            .bind("id", orderId)
            .map(this::mapOrder)
            .one();
}
~~~

Đoạn trên tìm theo ID đơn thuần. Nếu orderId có thể được đoán hoặc lấy từ log, caller có thể truy cập object tenant khác.

Đúng hơn:

~~~java
Mono<Order> findOrder(TenantContext tenant, String orderId) {
    return databaseClient.sql(
            "SELECT id, tenant_id, status FROM orders " +
            "WHERE id = :id AND tenant_id = :tenantId")
            .bind("id", orderId)
            .bind("tenantId", tenant.tenantId())
            .map(this::mapOrder)
            .one();
}
~~~

Kết quả:
- Order thuộc tenant hiện tại: trả về.
- Order thuộc tenant khác: không tìm thấy trong tenant scope.
- ID không tồn tại: cũng không tìm thấy.

Tùy API disclosure policy, hai trường hợp cuối có thể trả 404 để không tiết lộ sự tồn tại của object thuộc tenant khác.

### Tenant predicate phải áp dụng cho mọi query path

Không chỉ SELECT:
- UPDATE.
- DELETE.
- INSERT.
- COUNT/aggregate.
- Search.
- Export.
- Join.
- Batch operations.
- Subqueries.
- Reporting views.

Một query list an toàn:

~~~sql
SELECT id, status, total
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC
LIMIT :limit
~~~

Một query update an toàn:

~~~sql
UPDATE orders
SET status = :newStatus
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND status = 'DRAFT'
~~~

Một query delete an toàn:

~~~sql
DELETE FROM orders
WHERE id = :orderId
  AND tenant_id = :tenantId
~~~

Đừng query theo ID trước, sau đó quên kiểm tra tenant ở một nhánh error hoặc mapper phụ.

## 11. Insert: tenant lấy từ trusted context

Một lỗi phổ biến là cho client tự quyết định tenant khi tạo dữ liệu:

~~~json
{
  "tenantId": "blue",
  "productId": "p-100",
  "quantity": 2
}
~~~

Nếu service copy tenantId từ body vào INSERT, caller có thể tạo record cho tenant khác.

Đúng hơn:
- Tenant được lấy từ TenantContext đã xác minh.
- Body không chứa tenantId, hoặc nếu có thì phải so sánh với context và reject mismatch.
- INSERT gán tenantId từ server-side context.
- Foreign keys đảm bảo quan hệ giữa record và tenant hợp lệ.

Ví dụ:

~~~java
Mono<Order> createOrder(
        TenantContext tenant,
        CreateOrderRequest request) {

    return databaseClient.sql(
            "INSERT INTO orders (id, tenant_id, product_id, quantity) " +
            "VALUES (:id, :tenantId, :productId, :quantity) " +
            "RETURNING id, tenant_id, product_id, quantity")
            .bind("id", UUID.randomUUID().toString())
            .bind("tenantId", tenant.tenantId())
            .bind("productId", request.productId())
            .bind("quantity", request.quantity())
            .map(this::mapOrder)
            .one();
}
~~~

Đoạn code giả định DatabaseClient/R2DBC và database hỗ trợ RETURNING. Điều chỉnh syntax theo database driver thực tế.

## 12. Update phải kiểm tra tenant và business state trong cùng câu lệnh

Nếu code làm:
1. SELECT order by ID.
2. Check tenant trong Java.
3. UPDATE order by ID.

thì có thể xuất hiện race condition nếu tenant/ownership/state thay đổi giữa hai bước hoặc một code path khác bỏ check.

Với các điều kiện đơn giản, đưa tenant và state vào cùng UPDATE:

~~~sql
UPDATE orders
SET status = :newStatus,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND status = 'DRAFT'
~~~

Nếu số rows updated bằng 1, thao tác thành công. Nếu 0, resource không tồn tại trong tenant hoặc không còn ở trạng thái cho phép. API có thể cần một bước phân biệt 404/409 theo disclosure/business policy, nhưng phải giữ tenant isolation.

Đối với chuyển trạng thái phức tạp, dùng transaction và optimistic locking:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND version = :expectedVersion
  AND status = 'DRAFT'
~~~

Tenant predicate phải xuất hiện cả trong update cuối, không chỉ trong SELECT ban đầu.

## 13. Database schema: tenant-aware keys và foreign keys

Một schema đơn giản:

~~~sql
CREATE TABLE tenants (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, id),
    CONSTRAINT fk_orders_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
~~~

Dùng composite key (tenant_id, id) có thể giúp thể hiện object identity trong tenant namespace.

Nếu bảng khác tham chiếu order:

~~~sql
CREATE TABLE order_items (
    tenant_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    item_id VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, item_id),
    CONSTRAINT fk_item_order
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, id)
);
~~~

Composite foreign key ngăn một order_item của tenant blue tham chiếu order của tenant red chỉ bằng order ID.

### Index phải hỗ trợ tenant predicate

Nếu query thường là:

~~~sql
WHERE tenant_id = :tenantId AND status = :status
ORDER BY created_at DESC
~~~

cân nhắc index:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Index không thay security check, nhưng giúp tenant-scoped query chạy hiệu quả. Xem execution plan và workload thực tế trước khi thêm index.

### ID ngẫu nhiên không phải authorization

UUID/ULID khó đoán hơn integer tuần tự nhưng không giải quyết BOLA. Một ID bị lộ qua URL, logs, email hoặc analytics vẫn có thể được gọi lại. Luôn lọc theo tenant và kiểm tra permission.

## 14. Row-Level Security là defense in depth

Một số database hỗ trợ Row-Level Security (RLS), ví dụ PostgreSQL. RLS có thể buộc database chỉ trả rows thuộc tenant context hiện tại.

Ví dụ policy PostgreSQL:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

Ứng dụng phải đặt tenant context trong transaction/connection trước khi query:

~~~sql
SELECT set_config('app.tenant_id', :tenantId, true);
~~~

Tham số true làm setting có phạm vi transaction trong PostgreSQL. Điều này quan trọng với connection pool: không để tenant context của request trước rò sang request sau.

### Các điều kiện RLS cần chú ý

- Database role của ứng dụng không được là superuser hoặc có BYPASSRLS.
- Table owner có thể bypass RLS trong một số trường hợp; FORCE ROW LEVEL SECURITY giúp áp dụng cho owner theo policy.
- Transaction phải set tenant context đúng trước mọi query.
- Không cho caller tự set arbitrary tenant ID mà không qua application membership check.
- Mọi connection pool path phải đảm bảo transaction scope.
- Migration/admin jobs cần role/policy riêng và audit.
- Tests phải chạy bằng role thực tế, không chỉ database owner.

RLS là defense in depth. Vẫn nên có tenant predicate ở repository để query semantics rõ và dễ review.

### Reactive transaction và connection pooling

Trong WebFlux/R2DBC, transaction và connection có lifecycle reactive. Không dùng một SQL SET session-wide rồi trả connection về pool mà quên reset. Dùng transaction-scoped setting và Spring reactive transaction manager phù hợp; kiểm tra mọi query trong transaction thực sự dùng cùng connection.

Không dùng ThreadLocal để truyền tenant ID cho R2DBC connection. Reactive execution có thể đổi thread; dùng transaction/context-aware mechanisms.

## 15. Join và subquery cũng phải tenant-scoped

Một query có tenant filter ở bảng orders nhưng join sang bảng customer không có tenant predicate vẫn có thể làm lộ dữ liệu nếu customer IDs không global unique hoặc quan hệ bị sai.

~~~sql
SELECT o.id, c.name
FROM orders o
JOIN customers c
  ON c.id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = :tenantId
  AND o.id = :orderId
~~~

Subquery cũng phải giữ tenant:

~~~sql
SELECT o.id
FROM orders o
WHERE o.tenant_id = :tenantId
  AND EXISTS (
      SELECT 1
      FROM order_permissions p
      WHERE p.tenant_id = o.tenant_id
        AND p.order_id = o.id
        AND p.subject_id = :subjectId
  )
~~~

Nếu có shared/global reference data, cần định nghĩa rõ bảng nào là global và bảng nào tenant-owned. Không mặc định mọi bảng đều phải có tenant_id, nhưng mọi join phải bảo toàn ownership boundary.

## 16. Object-level authorization: kiểm tra từng resource

Scope thường là quyền coarse-grained. Object-level policy cần xét:
- Resource thuộc tenant nào?
- Actor có ownership hoặc assignment không?
- Actor có vai trò trên resource không?
- Resource đang ở state nào?
- Có rule phân tách duties hay approval không?

Một order có thể có policy:

~~~text
Read order:
  hasAuthority(SCOPE_orders.read)
  AND tenant membership active
  AND order.tenantId == tenantContext.tenantId
  AND actor can view order

Update order:
  hasAuthority(SCOPE_orders.write)
  AND tenant membership active
  AND order.tenantId == tenantContext.tenantId
  AND actor is owner or assigned operator
  AND order.status == DRAFT
~~~

Một user có quyền đọc mọi order trong tenant chưa chắc được sửa mọi order. Có thể có role ORDER_VIEWER, ORDER_EDITOR, ORDER_APPROVER hoặc policy theo ownership.

### Check quyền ở server-side

Không dựa vào:
- Button bị ẩn trên frontend.
- Order ID khó đoán.
- Tenant ID do browser gửi.
- Role name trong request body.
- URL path đã được người dùng chọn.
- Một lần check ở controller mà repository khác không enforce.

Mọi request tới resource phải được server-side authorize.

## 17. BOLA/IDOR và cách tránh

Một API dễ mắc lỗi:

~~~http
GET /api/orders/1001
~~~

Nếu order ID là global sequence, attacker có thể thử 1002, 1003. Nhưng ngay cả UUID ngẫu nhiên, attacker vẫn có thể nhận ID từ email, log, shared link hoặc client-side state.

Sai:

~~~java
return repository.findById(orderId)
        .map(orderMapper::toView);
~~~

Đúng:

~~~java
return repository.findByIdAndTenantId(
                orderId, tenantContext.tenantId())
        .switchIfEmpty(Mono.error(
                new OrderNotFoundException()))
        .flatMap(order ->
                authorizationService.canRead(
                        tenantContext, order)
                        .filter(Boolean::booleanValue)
                        .switchIfEmpty(Mono.error(
                                new AccessDeniedException(
                                        "Order access denied")))
                        .thenReturn(orderMapper.toView(order)));
~~~

Nếu cần che giấu sự tồn tại object, có thể trả cùng một 404 cho object không tồn tại và object thuộc tenant khác. Nếu policy yêu cầu 403 để biểu thị đã tồn tại nhưng caller không có quyền, cần bảo đảm không tiết lộ metadata ngoài ý muốn.

## 18. Reactive authorization service

Một policy service có thể kiểm tra membership, ownership và business role:

~~~java
public interface OrderAuthorizationService {

    Mono<Boolean> canRead(
            TenantContext tenant,
            Order order);

    Mono<Boolean> canUpdate(
            TenantContext tenant,
            Order order);
}
~~~

Ví dụ implementation:

~~~java
@Service
public class DefaultOrderAuthorizationService
        implements OrderAuthorizationService {

    private final OrderAssignmentRepository assignments;

    public DefaultOrderAuthorizationService(
            OrderAssignmentRepository assignments) {
        this.assignments = assignments;
    }

    @Override
    public Mono<Boolean> canRead(
            TenantContext tenant,
            Order order) {

        if (!tenant.tenantId().equals(order.tenantId())) {
            return Mono.just(false);
        }

        return assignments.existsActiveAssignment(
                tenant.issuer(),
                tenant.subject(),
                tenant.tenantId(),
                order.id());
    }

    @Override
    public Mono<Boolean> canUpdate(
            TenantContext tenant,
            Order order) {

        if (!tenant.tenantId().equals(order.tenantId())
                || !"DRAFT".equals(order.status())) {
            return Mono.just(false);
        }

        return assignments.existsEditAssignment(
                tenant.issuer(),
                tenant.subject(),
                tenant.tenantId(),
                order.id());
    }
}
~~~

Ví dụ này giả định actor là user và assignment store có dữ liệu hiện hành. Với client credentials, có thể cần policy machine actor riêng.

### Tránh subscribe lồng nhau

Không làm:

~~~java
authorizationService.canUpdate(tenant, order)
        .subscribe(allowed -> {
            if (allowed) {
                repository.save(order).subscribe();
            }
        });
~~~

Đây là fire-and-forget nested subscriptions, làm mất composition, error propagation và transaction context. Dùng flatMap/filter/switchIfEmpty:

~~~java
authorizationService.canUpdate(tenant, order)
        .filter(Boolean::booleanValue)
        .switchIfEmpty(Mono.error(
                new AccessDeniedException("Update denied")))
        .flatMap(allowed -> repository.save(order));
~~~

Trong code thực tế, nếu repository query đã lọc tenant và state thì có thể kết hợp authorization để giảm race conditions.
## 19. Reactive SecurityContext và tenant context propagation

Trong WebFlux, SecurityContext được lưu trong Reactor Context. Dùng ReactiveSecurityContextHolder khi cần lấy Authentication trong reactive chain:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication());
}
~~~

Không dựa vào ThreadLocal/SecurityContextHolder kiểu imperative như cách đảm bảo duy nhất trong reactive pipeline.

### Tenant context truyền qua method parameters

Cách tường minh thường dễ review:

~~~java
return tenantAccessService.resolve(principal, tenantId)
        .flatMap(tenant ->
                ordersService.findOrder(tenant, orderId));
~~~

Ưu điểm:
- Method signature cho thấy tenant boundary.
- Unit tests có thể tạo context rõ ràng.
- Repository buộc nhận tenant.
- Không phụ thuộc vào thread-local state.
- Background tasks có thể nhận explicit context.

Nếu dùng Reactor Context để truyền tenant, phải:
- Set sau khi xác minh.
- Scope theo request chain.
- Không dùng static mutable state.
- Bảo đảm context propagation qua operators/libraries.
- Không tin context do caller tự set.
- Không tái sử dụng context giữa subscriptions.

## 20. Tenant context trong scheduled jobs và message consumers

Không phải mọi truy cập dữ liệu đều đi qua HTTP filter chain. Ví dụ:
- Scheduled billing task.
- Kafka/Rabbit message consumer.
- Webhook processor.
- Batch export.
- Async order fulfillment.
- Retry worker.

Các luồng này phải có actor/tenant context riêng.

Event có thể mang tenant identifier từ nguồn producer đáng tin:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderPaid",
  "tenantId": "blue",
  "orderId": "1001",
  "actor": {
    "issuer": "https://auth.example.com/",
    "subject": "user-42"
  }
}
~~~

Consumer phải:
- Xác minh message đến từ trusted producer/broker.
- Kiểm tra tenantId và order tenant trong database.
- Không tin event tenant nếu producer không đáng tin.
- Không dùng raw access token đã hết hạn được nhúng trong event.
- Dùng service identity cho background execution khi phù hợp.
- Ghi audit actor/tenant/source event.
- Giữ tenant predicate ở mọi query và side effect.

### Revalidate quyền tại thời điểm xử lý

Một event có thể được phát lúc user còn membership, nhưng xử lý sau khi membership đã bị revoke. Cần quyết định policy:
- Event là command được ủy quyền tại thời điểm phát?
- Hay consumer phải kiểm tra current membership lúc thực thi?
- Có phải ghi nhận actor là người yêu cầu nhưng thực thi dưới service identity?
- Nếu tenant bị suspend thì event pending xử lý thế nào?

Đây là business/security contract, không suy ra tự động từ JWT ban đầu.

## 21. Cache, search index và export cũng phải tenant-scoped

### Application cache

Sai:

~~~text
cache key = order:1001
~~~

Nếu cache không namespace tenant, tenant red có thể nhận object đã cache bởi tenant blue khi ID trùng hoặc mapping sai.

Đúng hơn:

~~~text
cache key = tenant:blue:order:1001
~~~

Cache key nên gồm tenant và mọi dimension ảnh hưởng authorization:
- Tenant.
- Resource ID.
- Actor/permission context nếu cache response đã lọc theo user.
- Locale/representation nếu cần.
- Policy/version nếu cache kết quả authorization.

Không cache response đã được authorize cho Alice rồi trả cho Bob chỉ vì cùng URL/resource key.

### Search index

Elasticsearch/OpenSearch hoặc hệ thống search cần filter tenant trong mọi query. Đừng chỉ filter trên UI hoặc post-filter một tập kết quả giới hạn; kết quả tổng hợp/facets/counts cũng có thể tiết lộ tenant khác.

### Export/report

Một export có thể chứa hàng nghìn rows. Cần:
- Tenant-scoped query ngay từ đầu.
- Authorize export action.
- Giới hạn fields và PII.
- Tenant-aware storage path/bucket prefix.
- Download URL có thời hạn và quyền phù hợp.
- Kiểm tra tenant khi user tải file.
- Không chia sẻ object storage key có thể truy cập chéo tenant.

## 22. Multi-tenant transaction và consistency

Một business action có thể gồm:
1. Resolve tenant membership.
2. Load order.
3. Check ownership/state.
4. Update order.
5. Insert audit record.
6. Publish event.

Nếu các bước không được phối hợp, có thể tạo race condition hoặc side effect ở tenant sai.

Nên:
- Dùng reactive transaction manager trong R2DBC khi nhiều DB operations cần atomicity.
- Đặt tenant predicates ở query cuối cùng.
- Dùng optimistic locking/version khi state có thể thay đổi đồng thời.
- Ghi audit record cùng transaction nếu cùng database và yêu cầu atomic.
- Dùng outbox pattern cho event publication.
- Đưa tenantId vào outbox record và event key.
- Consumer vẫn xác minh tenant/object ownership.

Một lần check ở đầu request không bảo đảm state vẫn như cũ tại lúc UPDATE. Với action nhạy cảm, kiểm tra state và tenant trong câu lệnh ghi hoặc transaction có isolation phù hợp.

## 23. Database constraints và defense in depth

Một thiết kế nhiều lớp:

~~~text
HTTP / Security:
  Verify issuer, audience, signature, expiry
  Require coarse scope

Tenant resolver:
  Map issuer + subject/client
  Check active tenant membership

Domain service:
  Check object ownership, role, business state

Repository:
  Every query includes tenant predicate

Database:
  Composite keys / foreign keys / optional RLS

Cache/search/export:
  Tenant namespace and filters

Operations:
  Audit, metrics, negative tests
~~~

Không nên chỉ dựa trên một lớp. Nếu controller quên gọi membership service, repository tenant predicate vẫn giảm khả năng data leak. Nếu một query thiếu predicate, database RLS có thể cung cấp defense in depth nếu được cấu hình đúng.

## 24. Cross-tenant administration phải là quyền riêng

Một số platform operator có quyền hỗ trợ nhiều tenant. Không nên tạo lối tắt:

~~~text
if role == ADMIN:
    skip all tenant checks
~~~

Một cross-tenant admin policy nên:
- Dùng authority riêng, ví dụ SCOPE_platform.tenants.read hoặc role vận hành được quản lý.
- Tách actor kind (platform operator) khỏi tenant user.
- Yêu cầu lý do/support ticket cho sensitive access nếu phù hợp.
- Ghi audit actor, target tenant, resource, action, reason và request ID.
- Giới hạn thời gian/quyền bằng just-in-time elevation nếu tổ chức hỗ trợ.
- Kiểm tra endpoint admin riêng và network/MFA requirements.
- Không dùng tenantId từ request như proof; operator vẫn phải chọn target tenant theo policy và audit.

Ví dụ:

~~~text
Normal tenant user:
  access only within active membership

Platform support operator:
  explicit cross-tenant permission
  explicit target tenant
  audited access
  restricted actions
~~~

**Admin không có nghĩa bỏ mọi tenant isolation.** Cross-tenant access là capability có kiểm soát và có dấu vết.

## 25. Tenant-aware error handling

Khi order ID không tồn tại hoặc thuộc tenant khác, API có thể chọn:
- **404 Not Found** để không tiết lộ object existence.
- **403 Forbidden** nếu policy cho phép tiết lộ object tồn tại nhưng actor không có quyền.

Cần nhất quán theo API contract. Không trả:

~~~json
{
  "error": "Order exists but belongs to tenant red",
  "tenantId": "red"
}
~~~

cho Alice thuộc tenant blue.

Không log sensitive details vào client response. Internal audit có thể ghi tenant/resource IDs theo data handling policy.

### Authentication failure khác tenant authorization failure

- Token invalid: 401.
- Token hợp lệ nhưng không có membership tenant được yêu cầu: thường 403 hoặc 404 theo disclosure policy.
- Membership database unavailable: fail closed; phân loại dependency failure, không tạo TenantContext mặc định.
- Resource thuộc tenant khác: không trả dữ liệu.
- User có membership nhưng thiếu orders.write: 403.

Không chuyển membership service outage thành “user không thuộc tenant” nếu cần phân biệt vận hành. Client response có thể generic, logs/metrics cần failure category rõ.

## 26. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách đúng |
|---|---|---|
| Tin tenantId từ path/header | Caller tự chọn tenant | Check membership |
| Chỉ verify JWT rồi truy vấn theo object ID | BOLA/IDOR | Tenant-scoped query |
| Dùng sub không kèm issuer | Identity collision | Issuer + subject |
| Dùng email làm identity key | Email có thể đổi/trùng | Stable issuer identity |
| Coi tenant claim là membership vĩnh viễn | Claim stale sau revoke | Current membership/version policy |
| Body tenantId ghi đè context | Cross-tenant write | Tenant từ server-side context |
| SELECT có tenant filter nhưng UPDATE không có | Write cross-tenant | Tenant predicate ở mọi write |
| Chỉ check tenant ở controller | Internal path có thể bỏ qua | Service/repository enforcement |
| Cache key chỉ có orderId | Cross-tenant cache leak | Tenant namespace |
| Search filter chỉ ở UI | Data/facet leakage | Server-side tenant filter |
| Export query không tenant-scoped | Bulk data leak | Scope query and download |
| ThreadLocal tenant trong WebFlux | Context bleed | Explicit parameter/Reactor Context |
| Event consumer tin tenantId từ message bất kỳ | Forged event | Trusted producer + revalidation |
| Admin role bypass tất cả | Privilege escalation | Explicit audited cross-tenant capability |
| Dùng UUID thay authorization | BOLA vẫn tồn tại | Object-level checks |
| RLS với pooled session setting không reset | Tenant context leak | Transaction-scoped setting |
| Chỉ test happy path | Không phát hiện tenant crossing | Cross-tenant negative tests |

## 27. Kiểm thử tenant isolation

Các tests phải chứng minh dữ liệu tenant A không thể được truy cập bởi actor tenant B, kể cả khi actor có token hợp lệ.

| Test case | Setup | Kỳ vọng |
|---|---|---|
| User blue đọc order blue | Membership blue active, scope read | Cho phép nếu object policy đạt |
| User blue đọc order red | Token hợp lệ, order tenant red | Không trả dữ liệu |
| User không membership blue | Request tenant blue | 403/404 theo contract |
| User có membership nhưng token thiếu scope | Tenant đúng, scope thiếu | 403 |
| JWT sub giống nhau từ issuer khác | Issuer namespace khác | Không dùng membership của issuer còn lại |
| Client credentials gọi user-only route | Không có user subject | Reject theo actor policy |
| Body gửi tenant red khi context blue | Create/update | Reject hoặc bỏ field theo contract; không ghi tenant red |
| Path tenant khác claim/default tenant | Membership không có | Deny |
| Header X-Tenant-Id giả | Caller tự set | Không được tin |
| Order ID đoán được | Cross-tenant ID | Không truy cập |
| Update order red bằng ID | Tenant blue context | 0 rows updated/deny |
| Delete cross-tenant | Tenant blue context | Không xóa |
| Join customer/order khác tenant | Foreign relation sai | DB constraint/query không trả chéo tenant |
| Cache cùng order ID ở hai tenant | Cache key tenant-aware | Không dùng nhầm response |
| Search/facets | Dataset nhiều tenants | Counts/results chỉ tenant hiện tại |
| Export | Tenant blue export | File chỉ chứa dữ liệu blue |
| Async event tenant mismatch | Event tenant red, order blue | Reject/quarantine |
| Membership bị revoke | Cache/context cũ | Hành vi theo freshness SLA |
| DB RLS | App DB role thực tế | Query không đọc/ghi chéo tenant |
| R2DBC connection reuse | Tenant A rồi tenant B trên pool | Không rò context |
| Platform admin | Explicit cross-tenant permission | Chỉ action được cấp và audit |
| Tenant membership store outage | Không xác minh được | Fail closed, không default allow |

### Integration tests nên đi qua toàn bộ boundary

- SecurityWebFilterChain thật để verify JWT/opaque authentication.
- Tenant resolver thật hoặc controlled membership repository.
- Service và repository với database test.
- Cache/search adapters khi kiểm tra cross-tenant leakage.
- R2DBC transaction/connection pool nếu dùng reactive DB.
- Event consumer tests cho async context.
- Assertions về side effects, không chỉ HTTP status.

MockJwt hữu ích cho authorization tests nhưng không kiểm tra chữ ký thật. Cần signed JWT/JWKS integration tests riêng khi kiểm tra authentication.

## 28. Observability và audit mà không làm lộ dữ liệu

Log/audit có thể ghi:
- requestId/correlationId.
- configured issuer ID.
- actor kind (USER/CLIENT/PLATFORM_OPERATOR).
- internal actor ID nếu policy cho phép.
- tenant ID đã được xác minh.
- resource type và resource ID theo data classification.
- action (read/update/delete/export).
- authorization outcome và failure category.
- membership/policy version nếu hữu ích.
- timestamp và source service.

Không log:
- Raw access token hoặc refresh token.
- Authorization header.
- Password/client secret.
- Toàn bộ JWT claims.
- Dữ liệu business record nhạy cảm.
- Tenant ID chưa verify như authenticated context.
- Request body đầy đủ nếu chứa PII.

Metrics nên dùng labels có cardinality giới hạn. Không dùng userId/orderId/token làm metric labels. Có thể đo:
- Tenant authorization allow/deny count.
- Cross-tenant lookup denied.
- Membership cache age.
- RLS violations.
- Query thiếu tenant predicate qua code review/static analysis hoặc query instrumentation.
- Export row count theo tenant.
- Cache namespace mismatch.
- Async event tenant mismatch.

Audit logs cần được bảo vệ khỏi sửa/xóa trái phép theo yêu cầu compliance của hệ thống.

## 29. Quy trình thiết kế một endpoint tenant-aware

Ví dụ endpoint cập nhật order:

~~~text
PUT /api/tenants/{tenantId}/orders/{orderId}
  |
  v
1. Verify Bearer token
   issuer, audience, signature, exp/nbf
  |
  v
2. Require SCOPE_orders.write
  |
  v
3. Normalize actor identity
   issuer + subject/client identity
  |
  v
4. Resolve requested tenant
   active membership / explicit platform permission
  |
  v
5. Load/update only within tenant
   WHERE id = orderId AND tenant_id = tenantId
  |
  v
6. Check object/business permission
   owner/assignment/status/version
  |
  v
7. Persist with tenant predicate
   transaction / optimistic lock
  |
  v
8. Audit and publish tenant-scoped event
  |
  v
9. Return only allowed representation
~~~

Ở mỗi bước, lỗi phải giữ đúng semantics:
- Invalid token: authentication failure.
- Missing scope: authorization failure.
- No tenant membership: tenant access denied.
- Resource absent/outside tenant: 404 hoặc denial theo disclosure policy.
- DB/membership dependency down: fail closed.
- Business state conflict: conflict/domain response nếu API contract quy định.

Không trả dữ liệu trước khi mọi checks liên quan hoàn tất.

## 30. Tổng kết

~~~text
Trusted OAuth/OIDC token
        |
        v
Authentication
  issuer + subject/client
  audience + token validity
        |
        v
Tenant resolution
  requested tenant
  + verified membership
        |
        v
TenantContext
        |
        v
Coarse authorization
  scopes / authorities
        |
        v
Object authorization
  tenant ownership
  assignment / role
  business state
        |
        v
Tenant-scoped repository
  SELECT / INSERT / UPDATE / DELETE
        |
        v
Database constraints / optional RLS
        |
        v
Tenant-safe cache, search, export and events
~~~

Các nguyên tắc cần nhớ:

1. **Token hợp lệ không tự cho phép truy cập mọi object** trong API.
2. **Authentication, tenant resolution và authorization là ba quyết định riêng**.
3. Map identity theo issuer + subject; phân biệt human user và machine client.
4. Tenant trong path/header/body là requested context, cần kiểm tra membership hoặc capability.
5. TenantContext chỉ được tạo sau khi identity và tenant access được xác minh.
6. Scope là quyền coarse-grained; object ownership, tenant membership và business state cần check riêng.
7. Mọi SELECT/INSERT/UPDATE/DELETE/join/search/export phải giữ tenant boundary.
8. Cache key, search filters, download paths và async events phải tenant-aware.
9. R2DBC/WebFlux cần reactive context/transaction đúng; tránh ThreadLocal và session state rò qua connection pool.
10. Database composite keys, foreign keys và RLS có thể bổ sung defense in depth.
11. Cross-tenant admin là capability riêng, giới hạn và audit được.
12. Negative tests phải chứng minh tenant A không đọc/ghi dữ liệu tenant B, kể cả khi token của A hợp lệ.

**Kết luận:** Spring Security xác minh access token và cung cấp principal/authorities, nhưng ứng dụng phải biến danh tính đó thành tenant context được kiểm tra rồi thực thi quyền trên từng resource. Cô lập tenant chỉ bền vững khi tenant predicate và business authorization xuất hiện xuyên suốt từ request tới service, repository, database, cache, search, export và background processing.

## 31. Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server:** JWT/opaque token authentication trong WebFlux. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security Reference — Reactive Authorization:** authorizeExchange, authorities và reactive access decisions. https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- **Spring Security Reference — Reactive Method Security:** @EnableReactiveMethodSecurity và method authorization. https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- **Spring Security Reference — Reactive Security Context:** ReactiveSecurityContextHolder và Reactor Context. https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- **Spring Framework Reference — R2DBC:** reactive relational database access và DatabaseClient. https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- **Spring Framework Reference — Reactive Transactions:** reactive transaction management. https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- **PostgreSQL Documentation — Row Security Policies:** ENABLE/FORCE ROW LEVEL SECURITY, USING và WITH CHECK. https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- **PostgreSQL Documentation — SET and SET LOCAL:** transaction-scoped configuration settings. https://www.postgresql.org/docs/current/sql-set.html
- **OWASP API Security Top 10 — API1 Broken Object Level Authorization:** object-level authorization failures. https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- **OWASP Authorization Cheat Sheet:** deny by default, least privilege và server-side authorization. https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **OWASP Multi-Tenant Security Cheat Sheet:** tenant isolation, context propagation và cross-tenant access controls. https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html
- **RFC 7519 — JSON Web Token:** issuer, subject, audience và claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token profile and audience. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** active state and introspection attributes. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer credentials and scope semantics. https://www.rfc-editor.org/rfc/rfc6750
