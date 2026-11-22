# Cách ly tenant và xác minh chủ sở hữu tài nguyên

## 1. Bài toán: một API, nhiều tenant, nhiều chủ sở hữu

Giả sử hệ thống SaaS **Shop API** dùng chung ứng dụng và cơ sở dữ liệu cho nhiều cửa hàng (tenant). Tenant A có nhân viên An và Bình; Tenant B có nhân viên Chi. An sở hữu đơn hàng A-101, Bình sở hữu A-102, Chi sở hữu B-201.

An đăng nhập hợp lệ và có access token với quyền `orders.read`. Nếu An đổi request từ `/api/tenants/A/orders/A-101` sang `/api/tenants/B/orders/B-201`, liệu API có trả dữ liệu Tenant B? Nếu An giữ tenant A nhưng đổi `orderId` sang A-102, liệu An có được đọc đơn riêng của Bình? Cả hai câu trả lời đều phụ thuộc **phân quyền trên server**, không phụ thuộc việc An có JWT hợp lệ, UUID khó đoán hay UI đã ẩn nút xem.

Lỗi bỏ kiểm tra quyền trên tài nguyên được gọi là **Broken Object Level Authorization (BOLA)**, thường xuất hiện dưới dạng **Insecure Direct Object Reference (IDOR)**. Đây là lớp lỗi làm lộ/sửa dữ liệu giữa khách hàng hoặc giữa người dùng cùng tổ chức. Rủi ro không chỉ ở GET: POST có thể tạo dữ liệu dưới tenant khác, PATCH đổi owner, DELETE xóa nhầm, truy vấn tìm kiếm xuất dữ liệu vượt phạm vi, hoặc cache trả kết quả của tenant trước.

**Mục tiêu học tập:** Người học có thể thiết kế REST URI/resource đa tenant, phân biệt xác thực với membership/ownership, triển khai kiểm soát Java/Spring Security và SQL, xử lý HTTP status đúng, xây kiểm thử BOLA/cross-tenant, và áp dụng các biện pháp phụ trợ như ràng buộc khóa ngoại, RLS, cache key và tenant context cho background jobs.

## 2. Năm ranh giới cần tách bạch

| Lớp | Câu hỏi | Dữ liệu đáng tin | Ví dụ |
|---|---|---|---|
| **Authentication** | Người gọi là ai? | Access token đã được Resource Server xác minh: chữ ký/introspection, `iss`, `aud`, `exp`, `sub` | `sub=alice-sub`, `aud=shop-api` |
| **Tenant membership** | Người này có thuộc tenant đang yêu cầu? | Bảng membership/nguồn quyền được server xác thực; có trạng thái ACTIVE | An là MEMBER tại Tenant A |
| **Action permission** | Có được dùng loại thao tác này? | Scope + role/permission theo tenant | `orders.read`, `orders.write` |
| **Tenant isolation** | Tài nguyên có thuộc đúng tenant? | `resource.tenant_id` trong DB; bộ lọc truy vấn/RLS | A-101 có `tenant_id=A` |
| **Object ownership** | Caller có được xem/sửa bản ghi cụ thể? | `owner_user_id`, role/policy trên tenant và đối tượng | A-101 thuộc An; A-102 thuộc Bình |

**Scope là quyền thao tác tổng quát, không phải vé đọc mọi bản ghi.** Token có `orders.read` nhưng không có membership Tenant B phải bị từ chối. Thành viên Tenant A có thể không được xem đơn cá nhân của thành viên khác. `TENANT_ADMIN` tại A cũng không là admin tại B. Đối với tài nguyên dùng chung không có owner cá nhân (ví dụ cấu hình cửa hàng), chính sách có thể dựa vào tenant và role thay vì `owner_user_id`.

Quy tắc tham khảo cho endpoint **owner-only**:

`ALLOW = valid_access_token AND correct_scope AND active_membership(user, tenant) AND resource.tenant_id = tenant AND resource.owner_user_id = user`

Khi tenant admin được xem đơn của thành viên khác, policy phải viết rõ:

`ALLOW_READ = valid_token AND active_membership AND same_tenant AND (is_owner OR tenant_role_allows_read_any)`

Không dùng điều kiện `isAdmin` toàn cục để vô tình bỏ qua ranh giới tenant. Cần định nghĩa riêng chức năng **platform support/cross-tenant** có phê duyệt, kiểm toán và phạm vi xác định nếu hệ thống thật sự có yêu cầu hỗ trợ đa tenant.

### 2.1. Principal không lấy từ tham số do client gửi

Một request có thể chứa ba nguồn thông tin:

- **`Authorization: Bearer <access-token>`**: nguồn danh tính/quyền chỉ sau khi được xác minh. API không dùng ID token OIDC dành cho web client làm access token.
- **`tenantId` trong URL hoặc header**: lựa chọn tenant do client yêu cầu; phải kiểm tra membership tương ứng. `X-Tenant-Id` cũng là dữ liệu không đáng tin nếu client trực tiếp có thể đặt.
- **`userId`, `ownerId` trong body/query**: dữ liệu nghiệp vụ; không được dùng làm danh tính người đang gọi. Các trường owner chỉ có thể được thay đổi qua action riêng có policy.

Ứng dụng cần ánh xạ cặp **`(iss, sub)`** từ token đã được xác minh sang user ID nội bộ. Cùng một `sub` có thể xuất hiện ở những issuer khác nhau; email không phải khóa danh tính bất biến. Với access token cấp theo `client_credentials`, `sub` có thể đại diện cho một client/service thay vì người dùng. Các endpoint yêu cầu owner cá nhân phải xác minh kiểu principal phù hợp và có ánh xạ nội bộ hợp lệ.

### 2.2. Người dùng thuộc nhiều tenant

An có thể đồng thời là thành viên của Tenant A và Tenant C. Ứng dụng gửi tenant mà An đang chọn qua URI, nhưng backend vẫn kiểm tra membership ACTIVE **trong tenant đó**. Nếu access token chứa danh sách tenant/role, chỉ sử dụng sau kiểm tra token; đối chiếu với chính sách và độ trễ thu hồi cho phép. Với yêu cầu cần thu hồi quyền gần tức thời, nên xác minh membership tại server mỗi lần hoặc dùng cache có cơ chế invalidation phù hợp. Không tin tenant hiện ra trên giao diện như bằng chứng quyền truy cập.

## 3. Mô hình dữ liệu và bất biến tenant

Ví dụ PostgreSQL với shared schema:

~~~sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE users (
    id UUID PRIMARY KEY,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    UNIQUE (issuer, subject)
);

CREATE TABLE tenant_memberships (
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'LEFT')),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    owner_user_id UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_tenant_owner_created
    ON orders (tenant_id, owner_user_id, created_at DESC);

CREATE INDEX idx_orders_tenant_id
    ON orders (tenant_id, id);
~~~

Trong schema trên, `orders.id` là UUID duy nhất toàn cục nhưng truy vấn truy cập tài nguyên **vẫn phải giới hạn bằng tenant**. Với hệ thống cho phép ID chỉ duy nhất trong mỗi tenant, dùng `PRIMARY KEY (tenant_id, id)` hoặc `UNIQUE (tenant_id, id)` và buộc các bảng con mang `tenant_id` trong khóa ngoại. Ví dụ:

~~~sql
-- Nếu orders đã có ràng buộc UNIQUE(tenant_id, id):
CREATE TABLE order_items (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    sku TEXT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders (tenant_id, id)
);
~~~

Khóa ngoại tổng hợp tránh tình huống item ở Tenant A lại trỏ đến order thuộc Tenant B. Tuy nhiên, nó không chứng minh người gọi được phép xem/sửa item: mọi query vẫn cần kiểm tra tenant, quan hệ cha và quyền với parent.

Bảng `tenant_memberships` là nguồn xác nhận một người đang thuộc tenant nào và vai trò gì. FK `orders.owner_user_id REFERENCES users(id)` **chỉ** xác minh owner là user có tồn tại, không đảm bảo owner thuộc tenant của order. Khi tạo/chuyển giao owner, service phải kiểm tra membership tenant đích; có thể thiết kế ràng buộc tổng hợp sâu hơn nếu phù hợp quy tắc lưu trữ membership và lịch sử nhân sự.

## 4. Hợp đồng REST và quyết định HTTP

Các endpoint minh họa:

| HTTP | URI | Quy tắc truy cập |
|---|---|---|
| GET | `/api/tenants/{tenantId}/orders` | Lọc tenant, owner/role **trước** phân trang và tính total |
| GET | `/api/tenants/{tenantId}/orders/{orderId}` | Kiểm tra membership, tenant của order và ownership/permission |
| POST | `/api/tenants/{tenantId}/orders` | Server gán tenant + owner; client chỉ gửi dữ liệu được phép |
| PATCH | `/api/tenants/{tenantId}/orders/{orderId}` | Cập nhật có điều kiện theo tenant, owner/role và trạng thái |
| DELETE | `/api/tenants/{tenantId}/orders/{orderId}` | Quyền xóa riêng, trạng thái cho phép và audit |
| GET | `/api/tenants/{tenantId}/orders/{orderId}/attachments/{attachmentId}` | Cả attachment và order phải thuộc cùng tenant, có quyền đọc parent |

Ví dụ người dùng An gọi một đơn hàng:

~~~http
GET /api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Accept: application/json
~~~

**Lưu ý:** `tenantId` trong path chỉ là tenant người gọi **yêu cầu**. Nó chưa được tin cậy để query cho đến khi có authentication, membership và policy thích hợp.

| Tình huống | Mã HTTP phù hợp | Lý do |
|---|---|---|
| Không có token, token sai/hết hạn hoặc sai audience | **401 Unauthorized** | Xác thực với API chưa hợp lệ |
| Token hợp lệ nhưng thiếu `orders.read` | **403 Forbidden** | Không có quyền thao tác |
| Không có membership vào tenant bí mật; ID của đơn khác tenant/owner | **404 Not Found** theo chính sách che giấu | Không tiết lộ sự tồn tại của tenant/order |
| Caller biết tài nguyên tồn tại nhưng policy nói không được thao tác | **403 Forbidden** nếu contract chủ động dùng 403 | Từ chối quyền minh bạch |
| Owner được phép xem order | **200 OK** | Trả DTO đã giới hạn |
| Tạo thành công | **201 Created** + Location | Resource mới do server gán owner/tenant |
| Body không đúng schema | **400 Bad Request** | Dữ liệu đầu vào không hợp lệ |
| ETag/`If-Match` không khớp | **412 Precondition Failed** | Bảo vệ cập nhật đồng thời |

**401** thường có `WWW-Authenticate: Bearer`; thiếu scope có thể trả `403` với `insufficient_scope` theo RFC 6750. Với tài nguyên nhạy cảm, chọn **404 cho cả không tồn tại và không được xem** để hạn chế lộ thông tin. Chính sách phải nhất quán ở endpoint, thời gian xử lý và body; không cung cấp `actualTenantId`, tên owner hay chi tiết nội bộ cho người không được phép.

Ví dụ:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404
}
~~~

Dùng RFC 9457 Problem Details cho lỗi có cấu trúc và correlation/request ID để tra cứu nội bộ. Không phản hồi toàn bộ payload token hay chi tiết DB constraint nhạy cảm.

## 5. Luồng xác minh đúng: từ token tới bản ghi

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Security filter
    participant S as OrderService
    participant M as Membership DB
    participant O as Orders DB
    C->>F: GET /tenants/A/orders/A-101 + Bearer
    F->>F: Xác minh chữ ký, iss, aud, exp và scope
    alt Token sai hoặc thiếu scope
        F-->>C: 401 hoặc 403
    else Token hợp lệ, scope đúng
        F->>S: Principal + tenant A + order A-101
        S->>M: Map iss/sub thành user; kiểm membership ACTIVE(A,user)
        alt Không có membership
            S-->>C: 404
        else ACTIVE
            S->>O: SELECT id WHERE id=A-101 AND tenant=A AND owner=user
            alt Không có dòng được phép
                O-->>S: Empty
                S-->>C: 404
            else Có dòng hợp lệ
                O-->>S: Order
                S-->>C: 200 + OrderDTO
            end
        end
    end
~~~

Query dạng **owner-only**:

~~~sql
SELECT id, tenant_id, owner_user_id, status, note
FROM orders
WHERE id = :orderId
  AND tenant_id = :validatedTenantId
  AND owner_user_id = :authenticatedUserId;
~~~

Cả `:validatedTenantId` và `:authenticatedUserId` do server xác minh/ràng buộc, không lấy từ body. Dùng prepared parameters; không nối chuỗi SQL.

Sai lầm:

~~~java
// SAI: biết UUID không phải quyền truy cập.
OrderEntity order = repo.findById(orderId).orElseThrow();
return mapper.toView(order);
~~~

Dù có thêm `if` kiểm tra owner sau khi đọc, truy vấn không scope tenant vẫn dễ bị tái sử dụng sai trong các nhánh mới, cache, mapping hoặc logging. Tốt nhất đặt điều kiện tenant/owner ngay tại repository và kiểm tra membership ở service.

### 5.1. Danh sách và phân trang

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :validatedTenantId
  AND owner_user_id = :authenticatedUserId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

**Phải lọc quyền trước `LIMIT/OFFSET` hoặc cursor**, nếu không trang kết quả có thể trống bất thường, trả tổng số dòng không được xem hoặc vượt tenant trong pagination metadata. `COUNT(*)`, tìm kiếm, sort, export và aggregation đều phải dùng cùng policy. Với cursor do client mang lại, ràng buộc cursor với tenant/filter/caller (ví dụ state ký hoặc kiểm tra lại server) để không mang cursor của Tenant A sang Tenant B.

## 6. Java/Spring Security: xác thực access token và scope

Ví dụ Spring Boot 3.x, Spring Security 6.x, Java 17+ với `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-starter-web` và `spring-boot-starter-data-jpa`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {
    static final String ISSUER = "https://login.example.test";
    static final String AUDIENCE = "shop-api";

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            // Chỉ phù hợp API stateless xác thực bằng Bearer header,
            // không dùng browser cookie để xác thực request.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(s ->
                s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/tenants/*/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PATCH, "/api/tenants/*/orders/*")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://login.example.test/.well-known/jwks.json")
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience() != null && jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token", "Wrong audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audience));
        return decoder;
    }
}
~~~

API xác minh chữ ký qua JWKS tin cậy, issuer, expiry và audience. Spring Security ánh xạ scope thông thường thành authority `SCOPE_...`. Khi provider dùng claim scope/permission khác, cấu hình converter rõ ràng. JWT hợp lệ **không đủ**: SecurityFilterChain chỉ xác minh quyền thao tác; tầng business phải kiểm tra membership và owner. Không dùng ID token OIDC có audience của web client làm bearer cho API. Với access token opaque, dùng introspection có xác thực tới Authorization Server và kiểm tra audience/quyền theo hợp đồng provider.

`csrf.disable()` chỉ phù hợp ví dụ stateless bearer API không sử dụng cookie làm credential tự động. Nếu web app dùng session cookie, cần chính sách CSRF riêng. Trong production còn phải cấu hình HTTPS, giới hạn thuật toán JWT được phép, key rotation và không log token.

## 7. Java/Spring Data JPA: tenant + owner ở repository

### 7.1. Danh tính và quyền vào tenant

Giả sử có `UserEntity` chứa `id`, `issuer`, `subject`; `TenantMembershipEntity` chứa `tenantId`, `userId`, `active`, `role`; `OrderEntity` chứa `id`, `tenantId`, `ownerUserId` và `status`. Đây là ví dụ các lớp theo schema ở trên; khai báo entity và khóa chính cụ thể cần hoàn thiện trong dự án.

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface UserRepository extends JpaRepository<UserEntity, UUID> {
    Optional<UserEntity> findByIssuerAndSubject(String issuer, String subject);
}

interface MembershipRepository
        extends JpaRepository<TenantMembershipEntity, MembershipKey> {
    boolean existsByTenantIdAndUserIdAndActiveTrue(
        UUID tenantId, UUID userId);
}

interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    Optional<OrderEntity> findByIdAndTenantIdAndOwnerUserId(
        UUID orderId, UUID tenantId, UUID ownerUserId);
}
~~~

`MembershipKey` là khóa tổng hợp tenant + user được map bằng `@EmbeddedId` hoặc `@IdClass`. Nếu entity lưu `status=ACTIVE` thay vì boolean `active`, đổi method thành `existsByTenantIdAndUserIdAndStatus(tenantId, userId, ACTIVE)`. Không duy trì hai định nghĩa status mâu thuẫn trong code thực tế.

Service owner-only:

~~~java
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

record OrderView(UUID id, UUID tenantId, String status) {}

@Service
class OrderService {
    private final UserRepository users;
    private final MembershipRepository memberships;
    private final OrderRepository orders;

    OrderService(UserRepository users,
                 MembershipRepository memberships,
                 OrderRepository orders) {
        this.users = users;
        this.memberships = memberships;
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderView getOwned(Jwt jwt, UUID tenantId, UUID orderId) {
        // Jwt đã qua JwtDecoder của Resource Server.
        UUID userId = users
            .findByIssuerAndSubject(
                jwt.getIssuer().toString(),
                jwt.getSubject())
            .map(UserEntity::getId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));

        if (!memberships.existsByTenantIdAndUserIdAndActiveTrue(
                tenantId, userId)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        OrderEntity order = orders
            .findByIdAndTenantIdAndOwnerUserId(orderId, tenantId, userId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));

        return new OrderView(order.getId(), order.getTenantId(),
            order.getStatus());
    }
}
~~~

Controller:

~~~java
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{orderId}")
    OrderView get(@PathVariable UUID tenantId,
                  @PathVariable UUID orderId,
                  @AuthenticationPrincipal Jwt jwt) {
        return service.getOwned(jwt, tenantId, orderId);
    }
}
~~~

Các bản ghi có user/tenant không tồn tại đều trở thành 404 theo chính sách che giấu. Nếu token được cấp cho service account không có ánh xạ người dùng, endpoint owner-only phải từ chối theo quy tắc principal đã thiết kế; có thể tách riêng endpoint service-to-service với role và kiểm toán rõ ràng.

### 7.2. Tenant admin cần policy riêng

Nếu `TENANT_ADMIN` có quyền `orders.read.any` tại Tenant A, service cần đọc **role tại membership(A, userId)** rồi chọn query `findByIdAndTenantId(orderId,A)`. Thành viên thường vẫn đi qua `findByIdAndTenantIdAndOwnerUserId`. Không viết `if (isAdmin) repo.findById(id)` vì admin của A vẫn bị cách ly khỏi B. Kiểm tra role trong claim JWT có thể dùng bổ trợ, nhưng phải xác minh claim dành cho đúng tenant và đủ mới so với chính sách thu hồi. `@PreAuthorize` hữu ích để tổ chức authorization method, nhưng biểu thức chỉ kiểm scope không thay thế policy ở mức từng đối tượng.

### 7.3. Tạo tài nguyên: server tự gán tenant và owner

~~~http
POST /api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Content-Type: application/json

{
  "sku": "BOOK-001",
  "quantity": 2
}
~~~

DTO chỉ có field client được phép điều khiển:

~~~java
record CreateOrderRequest(String sku, int quantity) {}
~~~

Sau khi kiểm `orders.write` và membership của tenant trong URI, service mới tạo `OrderEntity` và **gán `tenantId`, `ownerUserId` từ context đã xác minh**. Tránh bind toàn bộ entity JPA từ JSON vì client có thể chèn `ownerUserId`, `tenantId`, `role` hoặc trạng thái đặc quyền (mass assignment). Có thể cấu hình JSON/schema từ chối trường không khai báo bằng 400; nếu bỏ qua trường thừa, vẫn tuyệt đối không dùng chúng trong chính sách quyền.

Tạo thay người khác cần một nghiệp vụ **delegated creation** riêng, có quyền rõ ràng, xác minh chủ thể đích thuộc cùng tenant và audit actor + subject. Không cho phép thay owner/tenant tự do bằng PATCH.

~~~http
HTTP/1.1 201 Created
Location: /api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/orders/33333333-3333-4333-8333-333333333333
Content-Type: application/json

{
  "id": "33333333-3333-4333-8333-333333333333",
  "status": "NEW"
}
~~~

### 7.4. Cập nhật/xóa: điều kiện ngay trong DML

Kiểu code dễ mắc lỗi:

~~~java
// SAI: cập nhật theo ID mà quên tenant/owner.
OrderEntity order = repo.findById(orderId).orElseThrow();
order.setNote(request.note());
repo.save(order);
~~~

Cần xác minh membership trước và dùng `UPDATE` giới hạn theo tenant + owner, có kiểm tra số dòng bị ảnh hưởng:

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

interface OrderWriteRepository extends JpaRepository<OrderEntity, UUID> {
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        update OrderEntity o
           set o.note = :note
         where o.id = :orderId
           and o.tenantId = :tenantId
           and o.ownerUserId = :userId
        """)
    int updateOwnedNote(
        @Param("orderId") UUID orderId,
        @Param("tenantId") UUID tenantId,
        @Param("userId") UUID userId,
        @Param("note") String note
    );
}
~~~

Service thực hiện trong `@Transactional`: ánh xạ danh tính và membership; kiểm quyền `orders.write`; gọi update; nếu affected rows = 0 thì trả 404/403 theo chính sách; không truy vấn order ở tenant khác chỉ để trả lỗi chi tiết. Xóa cần quyền `orders.delete` hoặc policy riêng, cùng tenant/owner và quy tắc trạng thái (ví dụ không xóa đơn đã thanh toán).

**TOCTOU và cạnh tranh:** Membership/owner có thể thay đổi giữa lúc service kiểm tra và ghi; cân nhắc lock, transaction isolation, kiểm điều kiện membership trong cùng DML hoặc RLS nếu hành động đòi hiệu lực thu hồi tức thời. Để tránh hai client ghi đè, dùng optimistic locking (`@Version`) hoặc `ETag/If-Match`. Bulk JPQL update **không tự xử lý `@Version`** như entity update thông thường; khi cần, đưa điều kiện version và tăng version tường minh, trả 412 cho `If-Match` sai.

Chuyển tenant thường cần workflow riêng có xác thực quyền bên nguồn và bên đích; tránh cập nhật trực tiếp `tenant_id`. Nếu dùng `Idempotency-Key` cho POST, khóa/cache idempotency cần ràng buộc tenant + caller + fingerprint request để hai tenant không nhận cùng kết quả từ một key do client chọn.

## 8. PostgreSQL RLS như phòng tuyến bổ sung

Trong shared database, PostgreSQL **Row-Level Security** (RLS) hỗ trợ giới hạn dòng theo tenant ngay tại DB, giảm nguy cơ một câu SQL quên `WHERE tenant_id` trả dữ liệu ngoài phạm vi.

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy ON orders
USING (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
);

ALTER TABLE orders FORCE ROW LEVEL SECURITY;
~~~

Sau khi đã xác minh tenant của request, ứng dụng đặt tenant context **trong cùng transaction và trước mọi query**:

~~~sql
SELECT set_config('app.tenant_id', :validatedTenantUuidText, true);
~~~

Tham số phải được bind, lấy từ tenant đã xác minh membership. `true` đặt giá trị theo phạm vi transaction, giúp giảm nguy cơ rò tenant giữa các request dùng chung connection pool. Nếu thiếu tenant context, predicate với NULL không khớp dòng. Khi dùng Spring, cần thiết kế transaction boundary để lệnh `set_config` và truy vấn thật chạy trên **cùng kết nối trong cùng transaction**; kiểm thử trường hợp tái sử dụng kết nối là thiết yếu.

RLS mẫu chỉ hạn chế tenant, **chưa** kiểm owner, scope hoặc vai trò tenant admin. RLS cũng phụ thuộc quyền role DB: superuser, role có `BYPASSRLS` có thể vượt policy; table owner mặc định có khả năng bypass, `FORCE ROW LEVEL SECURITY` giúp buộc table owner theo policy nhưng không vô hiệu các quyền bypass cao hơn. Tránh dùng role ứng dụng có quyền vượt RLS. Đừng cho client tuỳ ý chạy SQL đặt `app.tenant_id`; luôn phòng SQL injection, tuân thủ least privilege và giám sát tác vụ đặc quyền.

Các phương án database-per-tenant/schema-per-tenant có mức cô lập vật lý khác nhau nhưng vẫn cần authentication, authorization, routing đúng tenant, migration và backup an toàn. Không coi cách chia database là lý do bỏ kiểm tra owner tại API.

## 9. Các đường rò tenant thường bị bỏ quên

| Bề mặt | Lỗi thực tế | Cách bảo vệ |
|---|---|---|
| List/search/filter/count | Query chi tiết có tenant, query count lại không | Dùng cùng predicate tenant + quyền cho danh sách, total và aggregation |
| Pagination/cursor | Lọc sau LIMIT hoặc dùng cursor Tenant A tại B | Lọc trước phân trang; cursor ràng buộc tenant/filter/caller |
| Nested resource | `attachmentId` của B được lấy qua đường dẫn order A | JOIN kiểm tenant cả parent và child; kiểm quyền trên parent |
| Cache/Redis/CDN | Key `orders:page:1` dùng chung nhiều tenant | Key gồm tenant, loại quyền, actor khi dữ liệu riêng; cache header phù hợp |
| Object storage | Tạo presigned URL trước khi kiểm owner | Kiểm order/tenant/owner rồi mới cấp URL TTL ngắn |
| Background job/queue | Worker không có HTTP principal, tái dùng tenant context cũ | Message mang tenant context đáng tin; service identity có quyền; đặt/xóa context mỗi job |
| Export/report | CSV/PDF gom dữ liệu toàn hệ thống | Job/query và đường tải file cùng policy tenant/actor |
| Search index | Index trả hit của B qua truy vấn ở A | Tenant filter trong search và xác minh quyền khi tải chi tiết |
| Import/webhook | Integration chọn nhầm tenant | Subscription/credential gắn tenant; xác minh webhook và mapping nguồn |
| Admin/support | `ADMIN` toàn cục vô tình bỏ tenant predicate | Route đặc quyền riêng, policy, audit, giới hạn tenant đích |
| Batch update/delete | `WHERE status='NEW'` sửa mọi tenant | Luôn ràng buộc tenant và quyền; kiểm affected-row count |
| Logs/traces | Ghi token, PII hoặc dữ liệu tenant khác | Không log token; audit actor, tenant, action, resource với quyền đọc log |
| Async/thread pool | ThreadLocal cũ còn tenant của request trước | Set/clear trong `try/finally`, test context propagation |
| GraphQL/batch loaders | Resolver chỉ gọi `findById` | Policy theo tenant tại mọi resolver/batch lookup |

Ví dụ JOIN an toàn khi lấy item của order:

~~~sql
SELECT i.id, i.sku, i.quantity
FROM order_items i
JOIN orders o
  ON o.id = i.order_id
 AND o.tenant_id = i.tenant_id
WHERE o.id = :orderId
  AND o.tenant_id = :tenantId
  AND o.owner_user_id = :userId;
~~~

Không dùng `itemId` độc lập để bỏ qua quyền ở order. Cache và export đặc biệt nguy hiểm vì request đầu có thể hợp lệ, nhưng kết quả được tái sử dụng sau khi user đổi tenant hoặc membership bị thu hồi. Phân quyền phải đi theo **kết quả dữ liệu** tới khi trả cho caller, không chỉ ở endpoint khởi động tác vụ.

## 10. Kiểm thử security và hành vi HTTP

### 10.1. Bộ dữ liệu tối thiểu

| Tenant | User | Membership | Order |
|---|---|---|---|
| A | An (`alice-sub`) | ACTIVE MEMBER | A1 (owner An) |
| A | Bình (`bob-sub`) | ACTIVE MEMBER | A2 (owner Bình) |
| B | Chi (`charlie-sub`) | ACTIVE MEMBER | B1 (owner Chi) |
| B | An | Không có membership | Không được đọc B1 |

Bổ sung user có membership cả A/B nhưng owner chỉ ở một số bản ghi, admin ở A nhưng member ở B, membership SUSPENDED và service principal. Mỗi test cần quan sát **response và trạng thái DB** sau khi request trái quyền, không chỉ kiểm status.

### 10.2. MockMvc kiểm logic membership/ownership

Với `spring-security-test`, `jwt()` tạo principal thử nghiệm để kiểm filter scope và logic service. Giả sử fixture đã gán `tenantA`, `tenantB`, `orderA1`, `orderA2` và user `alice-sub`:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderIsolationTest {
    @Autowired MockMvc mvc;

    @Test
    void missingTokenReturns401() throws Exception {
        mvc.perform(get("/api/tenants/{t}/orders/{o}", tenantA, orderA1))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void cannotReadAnotherOwnerInSameTenant() throws Exception {
        mvc.perform(get("/api/tenants/{t}/orders/{o}", tenantA, orderA2)
            .with(jwt()
                .jwt(j -> j.issuer("https://login.example.test")
                           .subject("alice-sub"))
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isNotFound());
    }

    @Test
    void cannotReadUsingAnotherTenantPath() throws Exception {
        mvc.perform(get("/api/tenants/{t}/orders/{o}", tenantB, orderA1)
            .with(jwt()
                .jwt(j -> j.issuer("https://login.example.test")
                           .subject("alice-sub"))
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isNotFound());
    }

    @Test
    void missingScopeReturns403() throws Exception {
        mvc.perform(get("/api/tenants/{t}/orders/{o}", tenantA, orderA1)
            .with(jwt()
                .jwt(j -> j.issuer("https://login.example.test")
                           .subject("alice-sub"))
                .authorities(new SimpleGrantedAuthority("SCOPE_profile"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Các `tenantA`, `tenantB`, `orderA1`, `orderA2` là biến fixture cần khai báo/khởi tạo bằng setup hoặc `@Sql` khi đưa vào test suite thật. `jwt()` **bỏ qua giải mã và kiểm chữ ký JWT thật**: để thử issuer, audience, hết hạn, chữ ký và key rotation, dùng JWT ký bằng test key, JWKS server thử nghiệm và request `Authorization: Bearer` qua decoder thật.

### 10.3. Ma trận kiểm thử tích hợp

| Kịch bản | Kỳ vọng |
|---|---|
| Token hợp lệ, scope đúng, ACTIVE A, An đọc A1 | 200, đúng DTO |
| An đọc A2 của Bình trong A | 404, không lộ owner |
| An yêu cầu B1 trong B, không có membership B | 404, không truy xuất B |
| User có membership A+B nhưng không là owner B1 | Vẫn 404 với B1 |
| Token sai issuer/audience, hết hạn, sai chữ ký | 401 |
| Token hợp lệ thiếu `orders.read` | 403 |
| Membership bị SUSPENDED hoặc LEFT | Bị từ chối theo SLA thu hồi |
| GET list + filter/sort/cursor/count | Không có order/total của người/tenant khác |
| POST gửi `tenantId`/`ownerId` giả | Không thể tạo bản ghi dưới quyền giả |
| PATCH/DELETE order B1 qua tenant A | Không sửa/xóa dòng nào |
| Tenant admin A đọc đơn của Bình (nếu policy cho phép) | 200 tại A; không tự thành admin tại B |
| GET attachment B qua URL parent A | 403/404 theo policy; không có file |
| Cache đã ấm với user/tenant khác | Không dùng lại dữ liệu riêng |
| Export/job của Tenant A | File và download URL chỉ thuộc A |
| RLS với connection pool và nhiều transaction | Không rò tenant context giữa các lần dùng |

Khi dùng PostgreSQL RLS, nên chạy integration test với PostgreSQL thật qua Testcontainers thay vì H2 vì policy và session setting có khác biệt. Thêm bài test cạnh tranh: membership bị thu hồi khi đang update, chuyển owner cùng lúc với PATCH, và kiểm affected-row count/transaction semantics phù hợp cam kết hệ thống.

### 10.4. Thử khai thác kiểm soát trên môi trường test

Cho token An, thay tuần tự `tenantId`, `orderId`, cả hai; thử item/attachment nằm trong tenant khác; thử POST có field owner/tenant mạo danh; thử PATCH một tài nguyên sau khi membership bị khóa; thử truy vấn list với filter, sort, total, export, cursor; thử cache sau khi đổi tenant. BOLA đã được ngăn chỉ khi **không có dữ liệu rò và không có side effect trái phép**, ngay cả khi mã lỗi của các request có thể khác nhau theo contract.

## 11. Bài tập thực hành

### Bài tập 1 — Nhận diện lỗ hổng BOLA

API hiện triển khai:

~~~java
@GetMapping("/orders/{orderId}")
OrderEntity get(@PathVariable UUID orderId) {
    return orderRepository.findById(orderId).orElseThrow();
}
~~~

Hãy sửa URI thành `/api/tenants/{tenantId}/orders/{orderId}`, lấy principal đáng tin từ Resource Server, xác minh ACTIVE membership, và truy vấn với ba điều kiện `orderId + tenantId + authenticatedUserId`. Thiết kế tối thiểu sáu test gồm owner đúng, owner sai cùng tenant, tenant khác, token sai audience, thiếu scope, membership bị khóa.

**Tiêu chí đạt:** Không có đường query `findById` không tenant ở controller/service; user ID không lấy từ query/body; test bắt được đọc chéo tenant/owner.

### Bài tập 2 — Tenant admin chỉ ở một tenant

An có `TENANT_ADMIN` trong Tenant A và `MEMBER` tại Tenant B. An muốn xem đơn A2 của Bình và B1 của Chi. Xây policy `orders.read.any` theo membership tenant; mô tả query riêng cho admin và member. Nếu An bị thu hồi vai trò admin ở A nhưng access token vẫn còn hạn, làm sao hệ thống đáp ứng yêu cầu thu hồi trong vòng một phút?

**Gợi ý:** Policy/role được xét ở tenant đích; use membership source-of-truth hoặc cache quyền có TTL/invalidation phù hợp. Tenant B không thừa kế quyền admin tại A.

### Bài tập 3 — PATCH đồng thời

Một service đọc order qua `findById`, kiểm `owner` trong Java, rồi gọi `save`. Đồng thời thread khác chuyển owner. Hãy viết lệnh cập nhật có `WHERE id, tenant_id, owner_user_id, status='NEW'` và nếu cần thêm `version`. Kiểm số dòng bị ảnh hưởng; mô tả mã HTTP khi 0 dòng hoặc `If-Match` sai. Thiết kế test hai thread chứng minh không sửa tài nguyên không thuộc quyền tại thời điểm ghi.

**Tiêu chí đạt:** Không còn UPDATE chỉ theo ID; membership và quyền sửa được xác minh; có kế hoạch nhất quán khi dữ liệu bị thay đổi.

### Bài tập 4 — Audit toàn bộ bề mặt tenant

Hệ thống đã lọc tenant ở GET detail nhưng `GET /orders?status=NEW` quên tenant; Redis cache key `orders:page:1`; worker export CSV chạy không có SecurityContext. Hãy đề xuất query, cache key, job payload, xác minh quyền và ít nhất ba test nhằm bảo đảm kết quả chỉ thuộc tenant/owner được phép. Thảo luận trường hợp user đổi tenant trước khi lấy CSV.

**Tiêu chí đạt:** Query/count, cache và file export cùng dùng chính sách tenant; job có context đã được server xác thực; không tái sử dụng context của task trước.

### Bài tập 5 — RLS là phòng tuyến thứ hai

Bật RLS trên bảng orders và đặt `app.tenant_id` trong transaction A rồi `SELECT * FROM orders` không WHERE. Kết thúc transaction, tái sử dụng connection cho transaction B. Thử thêm trường hợp không đặt tenant và role `BYPASSRLS`. Ghi kết quả, lý giải vì sao vẫn phải kiểm membership/owner tại service.

**Tiêu chí đạt:** RLS chỉ trả dòng thuộc tenant được đặt; khi không context phải fail closed; nhận diện giới hạn role đặc quyền và thiếu owner policy.

## 12. Câu hỏi tự kiểm tra và tài liệu

1. **Có `orders.read` thì được xem mọi order?** Không; còn membership, tenant và quyền đối tượng.
2. **Tenant ID từ URI có đáng tin ngay không?** Không; phải ràng buộc với principal đã được xác minh và membership.
3. **UUID dài có thay kiểm tra owner?** Không; ID là định danh, không phải quyền.
4. **Admin của Tenant A có quyền đọc Tenant B?** Không, trừ quy trình đặc quyền được cấp rõ ràng và kiểm toán.
5. **RLS tự kiểm ownership?** Không với policy tenant-only; service hoặc policy DB bổ sung phải kiểm owner.
6. **Test dùng `jwt()` có kiểm được chữ ký JWT?** Không; cần test decoder/JWKS qua Bearer token thật.
7. **Tại sao query phải lọc trước `LIMIT`?** Để pagination/total và kết quả không bị ảnh hưởng bởi dữ liệu caller không được phép.
8. **Làm sao phát hiện update trái phép?** Kiểm affected-row count, dữ liệu DB và điều kiện tenant/owner trong DML, không chỉ HTTP status.

Tài liệu tham khảo:

- **OWASP API Security Top 10 2023 — API1 Broken Object Level Authorization:** https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- **OWASP API Security Top 10 2023 — API5 Broken Function Level Authorization:** https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
- **OWASP Authorization Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **OAuth 2.0 Bearer Token Usage, RFC 6750:** https://www.rfc-editor.org/rfc/rfc6750
- **Problem Details for HTTP APIs, RFC 9457:** https://www.rfc-editor.org/rfc/rfc9457
- **PostgreSQL Row-Level Security:** https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- **Spring Security Resource Server:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html

**Ghi nhớ:** Cách ly tenant là bất biến xuyên suốt từ access token, membership, HTTP route, service, SQL, cache, xử lý nền tới file xuất; xác minh owner là quyết định cho **từng tài nguyên**. Muốn chặn BOLA, mọi đường đọc/ghi phải chứng minh caller có quyền trong đúng tenant và đúng đối tượng.
