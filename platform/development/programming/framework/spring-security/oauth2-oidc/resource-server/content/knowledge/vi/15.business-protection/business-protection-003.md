# @PreAuthorize, authority và dữ liệu đầu vào của lời gọi

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, JWT Access Token giúp API xác thực caller và nhận các authorities như `SCOPE_orders.read` hoặc `SCOPE_orders.write`. Tuy nhiên, token có scope đọc đơn hàng **không mặc nhiên cho phép xem mọi đơn hàng**. Một request có thể cố truy cập ID của người khác, chọn tenant khác qua URL, hoặc đưa dữ liệu không được phép vào body.

**`@PreAuthorize`** là công cụ quan trọng để bảo vệ **lời gọi phương thức nghiệp vụ** theo cả hai loại thông tin:

- **Dữ liệu tin cậy từ quá trình xác thực:** `Authentication`, authorities, principal và claims JWT đã qua xác minh.
- **Dữ liệu đầu vào của lời gọi:** `orderId`, `tenantId`, `command`, các đối số của method — thường bắt nguồn từ HTTP path, query hoặc body và **không đáng tin chỉ vì chúng đã được parse thành đối tượng Java**.

Bài học giải thích cách kết hợp `@PreAuthorize`, `hasAuthority`, SpEL và một **policy bean** để quyết định quyền truy cập theo dữ liệu; đồng thời phân biệt method security với HTTP security và kiểm tra nghiệp vụ trong transaction. Ví dụ dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Resource Server Servlet** nhận JWT Access Token. Dữ liệu issuer, audience, ID, tenant và scope đều là ví dụ.

## 1. Vì sao cần bảo vệ ở tầng phương thức?

Giả sử ứng dụng có hai endpoint:

~~~http
GET /api/orders/7e9b... HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
~~~

~~~http
PATCH /api/orders/7e9b... HTTP/1.1
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json

{"note":"Giao trước 17:00"}
~~~

Spring Security có thể yêu cầu:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.PATCH, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Đây là điều kiện **ở HTTP layer**, phù hợp để chặn sớm request thiếu scope. Nhưng cùng scope `orders.read`, hai người dùng A và B không nhất thiết được xem cùng một đơn hàng. Nếu `orderId` thuộc user B, user A phải bị chặn dù JWT của A có chữ ký, issuer, audience và scope đều hợp lệ.

Một phương thức nghiệp vụ có thể khai báo:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(UUID orderId) {
    // ...
}
~~~

Phương thức này yêu cầu **đồng thời** có authority đọc và thỏa policy đối với **orderId cụ thể**. Đó là cách giải quyết một phần nguy cơ **Broken Object Level Authorization (BOLA/IDOR)**.

### 1.1. Ba tầng trách nhiệm

~~~text
HTTP request + Authorization: Bearer JWT
         |
         v
1. JWT authentication
   - Chữ ký/JWKS, issuer, audience, thời hạn, token profile
   - Tạo JwtAuthenticationToken, GrantedAuthority
         |
         v
2. HTTP authorization
   - authorizeHttpRequests
   - GET /api/orders/** yêu cầu SCOPE_orders.read
         |
         v
3. Method/domain authorization
   - @PreAuthorize kiểm tra scope và orderId/tenant
   - Service kiểm tra trạng thái thực tế của đơn hàng
   - Truy vấn/update có ràng buộc owner, tenant, trạng thái
         |
         v
        Thực thi nghiệp vụ hoặc từ chối
~~~

| Tầng | Biết được gì? | Ví dụ điều kiện |
| --- | --- | --- |
| **JWT decoder** | Token đã được ký/xác minh, claims và loại token. | `iss`, `aud`, `exp`, `nbf`, chữ ký hợp lệ. |
| **HTTP authorization** | URL, HTTP method, `Authentication`. | GET cần `SCOPE_orders.read`. |
| **Method security** | Method được gọi, arguments và `Authentication`. | Có quyền đọc **orderId này** không? |
| **Domain/data authorization** | Bản ghi, owner, tenant, trạng thái tại thời điểm thao tác. | Đơn hàng thuộc tenant và owner được phép không? |

Không nên chọn **chỉ một** tầng để bảo vệ mọi thứ. Những phương thức nghiệp vụ có thể được gọi từ HTTP controller, message consumer, scheduled job hoặc nơi khác; policy nên được đặt ở vị trí có đủ ngữ cảnh và được thực thi nhất quán. Trong các luồng không có HTTP hoặc SecurityContext, phải có cơ chế xác thực/ngữ cảnh riêng, không giả định luôn có JWT.

## 2. Bật method security với @EnableMethodSecurity

Ở Spring Security 6.x, dùng annotation **`@EnableMethodSecurity`**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Mặc định, cấu hình này bật xử lý các annotation cần thiết như **`@PreAuthorize`** và **`@PostAuthorize`** trên những method được Spring AOP/security infrastructure hỗ trợ. Không cần bật phương thức cũ `@EnableGlobalMethodSecurity(prePostEnabled = true)` cho dự án Spring Security 6 mới.

Dependency Gradle phổ biến (Spring Boot quản lý version):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ JWT Resource Server trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

`issuer-uri` giúp cấu hình nguồn phát hành JWT đáng tin cậy và kiểm tra issuer. `audiences` được hỗ trợ trong các phiên bản Spring Boot phù hợp để bắt buộc token có audience `orders-api`; nếu phiên bản khác, cấu hình audience validator tường minh. **Method security không thay thế JWT validation**: trước khi tin `Authentication` hoặc claims của Access Token, Resource Server phải xác minh chữ ký, thuật toán, issuer, audience và thời hạn.

### 2.1. Bảo vệ HTTP cơ bản để method security bổ sung

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Đoạn cấu hình chỉ mô tả một API dùng Bearer header, không dùng cookie session. `csrf.disable()` **không phải khuyến nghị chung cho OIDC Login dạng web có session cookie**; với cookie-based authentication cần CSRF strategy tương ứng.

**Thứ tự HTTP matchers** vẫn quan trọng: rule cụ thể phải đứng trước rule rộng; `anyRequest().denyAll()` hạn chế mở nhầm endpoint mới. Nhưng dù HTTP layer cho phép GET, `@PreAuthorize` ở service vẫn có thể từ chối vì người dùng không sở hữu tài nguyên.

## 3. Cơ chế @PreAuthorize

Spring Security đánh giá biểu thức `@PreAuthorize` **trước khi method body chạy**. Biểu thức là một dạng **Spring Expression Language (SpEL)** được đánh giá với bối cảnh security.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportDto readReport(UUID reportId) {
    // Chỉ chạy khi có authority đọc báo cáo.
}
~~~

Nếu expression trả về `false`, phương thức không được thực thi và yêu cầu bị từ chối bằng exception thuộc cơ chế authorization (thường là `AccessDeniedException`).

### 3.1. Các biểu thức thường gặp

| SpEL | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `isAuthenticated()` | Cần Authentication đã xác thực. | Endpoint nội bộ không yêu cầu scope cụ thể. |
| `hasAuthority('SCOPE_orders.read')` | Phải có chính xác authority đó. | Đọc tài nguyên với OAuth scope. |
| `hasAnyAuthority('SCOPE_orders.read', 'SCOPE_orders.audit')` | Có ít nhất một authority. | Nhiều nhóm được phép đọc theo contract. |
| `hasRole('ADMIN')` | Theo tiền tố mặc định yêu cầu `ROLE_ADMIN`. | Role đã được ánh xạ đúng từ nguồn tin cậy. |
| `hasAnyRole('ADMIN', 'SUPPORT')` | Có một trong các roles tương ứng. | Domain role policy. |
| `authentication` | Object Authentication hiện tại. | Truyền vào policy bean để đọc principal/authorities. |
| `principal` | Principal đang được xác thực. | Truy cập một phần thông tin principal theo kiểu đã biết. |
| `#orderId` | Argument có tên `orderId` của method. | Kiểm tra quyền trên bản ghi. |
| `#p0`, `#a0` | Argument đầu tiên theo vị trí. | Dùng khi không có metadata tên tham số. |
| `@orderAccess.canRead(authentication, #orderId)` | Gọi bean tên `orderAccess`. | Kết hợp quyền với dữ liệu database. |

`@PreAuthorize` có thể dùng `and`, `or`, `!` và nhiều phép so sánh SpEL. **Không dùng biểu thức quá dài phức tạp để thay cho chính sách nghiệp vụ có thể kiểm thử bằng Java.** Khi điều kiện cần đọc database hoặc xử lý quan hệ tenant/owner, một bean policy rõ ràng sẽ dễ bảo trì hơn.

### 3.2. hasAuthority khác hasRole và hasAnyAuthority

Một JWT Access Token có thể chứa:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000
}
~~~

Trong cấu hình Resource Server JWT phổ biến, `JwtGrantedAuthoritiesConverter` chuyển `scope` (hoặc `scp` theo profile) thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Do đó:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
~~~

sẽ khớp scope đọc. Ngược lại:

~~~java
@PreAuthorize("hasRole('ADMIN')")
~~~

thường kiểm tra authority `ROLE_ADMIN` và **không tự có** nếu JWT chỉ mang scope. Một claim custom `roles: ["ADMIN"]` cũng **không tự thành `ROLE_ADMIN`** cho đến khi hệ thống có converter/policy gắn authority tương ứng.

| JWT/authority đã được cung cấp | Biểu thức | Kết quả về authority |
| --- | --- | --- |
| `SCOPE_orders.read` | `hasAuthority('SCOPE_orders.read')` | Đúng. |
| `SCOPE_orders.write` | `hasAuthority('SCOPE_orders.read')` | Sai, nếu không có quyền đọc. |
| `ROLE_ADMIN` | `hasRole('ADMIN')` | Đúng với tiền tố role mặc định. |
| `SCOPE_admin.manage` | `hasRole('ADMIN')` | Sai, trừ khi có converter/authority khác. |
| `SCOPE_orders.read` | `hasAnyAuthority('SCOPE_orders.read', 'SCOPE_orders.audit')` | Đúng. |

**Không tự ánh xạ role/permission từ chuỗi do client truyền trong request** thành `GrantedAuthority`. Authorities chỉ được xây từ nguồn đã được xác thực và theo contract mà API tin cậy; quyền trên dữ liệu vẫn phải xét riêng.

## 4. Dữ liệu đầu vào của method không trở thành tin cậy vì token hợp lệ

Ví dụ controller:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderDto get(@PathVariable UUID orderId) {
    return orders.getOrder(orderId);
}
~~~

Argument `orderId` được parse thành `UUID`, nhưng **client vẫn quyết định giá trị của nó**. Một người đã xác thực có thể thử ID của đơn hàng thuộc người khác. Cũng vậy, `tenantId`, `ownerUserId`, `role` hoặc `approved` nằm trong request body là **dữ liệu chưa đáng tin**.

### 4.1. Tấn công BOLA/IDOR thông qua ID hợp lệ

~~~text
JWT user A:
  sub = person-A
  scope = orders.read

Database:
  Order 111 -> owner A
  Order 222 -> owner B

Request 1: GET /api/orders/111
  -> Có thể được cho phép.

Request 2: GET /api/orders/222
  -> PHẢI bị từ chối nếu user A không được đọc order 222.
~~~

Thay ID đơn hàng **không cần thay JWT**. Vì thế một rule chỉ kiểm tra scope:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto getOrder(UUID orderId) { ... }
~~~

chưa đủ khi dữ liệu thuộc từng user/tenant.

### 4.2. Những argument dễ bị hiểu nhầm

| Argument | Có thể do client điều khiển? | Cần chính sách gì? |
| --- | --- | --- |
| `orderId` trong path | Có. | Tra owner/tenant theo orderId; không tin ID là bằng chứng quyền. |
| `tenantId` trong URL/query | Có. | Kiểm tra membership/tenant được phép của principal. |
| `ownerUserId` trong JSON body | Có. | Không cho client tự đổi owner trừ quy trình được phép. |
| `status`, `approved` trong body | Có. | Kiểm tra transition trạng thái và quyền approve. |
| `limit`, `sort` trong query | Có. | Validate phạm vi, field được sort và rủi ro dữ liệu. |
| `Authentication` do Spring Security cung cấp | Framework tạo sau xác thực. | Chỉ tin khi request đã đi qua security chain đúng và principal type được kiểm soát. |
| `Jwt` lấy qua `@AuthenticationPrincipal` | Từ Authentication, sau decoder. | Dùng claims đã kiểm tra; xác thực không thay authorization. |

Ví dụ một thiết kế không an toàn:

~~~java
// KHÔNG LÀM: tin userId do client truyền.
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and #request.userId == principal.subject")
public OrderDto getOrder(ReadOrderRequest request) {
    return repository.findById(request.orderId()).orElseThrow();
}
~~~

Ngay cả khi `request.userId` trùng subject trong JWT, client vẫn có thể cung cấp `orderId` của người khác. Điều kiện chỉ so `userId` do client gửi với JWT **không chứng minh bản ghi thuộc user đó**.

**Quy tắc:** dữ liệu đầu vào giúp định vị tài nguyên; **nguồn dữ liệu nghiệp vụ đáng tin cậy** mới xác định owner, tenant và trạng thái thực tế của tài nguyên.

## 5. Dữ liệu nhận từ Authentication và JwtAuthenticationToken

Khi Resource Server đã xác thực Bearer JWT, `Authentication` thường là **`JwtAuthenticationToken`**. Nó chứa token đã được decoder xác minh, `getAuthorities()`, `getName()` và các claims.

Ví dụ method policy:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

public boolean hasVerifiedTenant(
        Authentication authentication, String expectedTenant) {

    if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
            || !authentication.isAuthenticated()) {
        return false;
    }

    Jwt jwt = jwtAuth.getToken();
    Object tenant = jwt.getClaims().get("tenant_id");

    return tenant instanceof String tenantId
        && !tenantId.isBlank()
        && tenantId.equals(expectedTenant);
}
~~~

Trong ví dụ:

- `authentication` là context mà Spring Security truyền vào expression, **không phải object do client tự tạo gửi trong JSON body**.
- `jwtAuth.getToken()` lấy JWT mà Resource Server đã xử lý.
- Custom claim `tenant_id` được kiểm tra **kiểu string** và giá trị thay vì ép mọi thứ sang chuỗi.
- Phép so sánh chỉ xác định token có tenant mong muốn; chưa chứng minh một **đơn hàng** thực sự thuộc tenant đó.

**Không mặc định mọi Authentication là JwtAuthenticationToken.** Ứng dụng có thể đồng thời hỗ trợ opaque token, session/OIDC Login hoặc Authentication khác. Với mỗi mô hình, policy phải nhận dạng principal đúng kiểu và có cách lấy identity/tenant từ nguồn đáng tin đã quy ước.

### 5.1. Vì sao cần issuer và subject khi ánh xạ user nội bộ?

Nếu domain lưu `owner_user_id` là UUID nội bộ, claim `sub` ngoài không phải khóa nội bộ. Khi cần ánh xạ, nên tìm tài khoản theo **`(iss, sub)`** đã được xác thực:

~~~text
JWT:
  iss = https://identity.example.test/realms/demo
  sub = external-person-42

external_identity:
  (issuer, subject) -> local_user_id

orders:
  owner_user_id = local_user_id
~~~

Tránh tra tài khoản chỉ bằng `sub` nếu có nhiều issuer; không tự động gộp tài khoản bằng `email` từ token. Với client credentials không có human user, policy cần mô hình service principal riêng, không giả định có một local user.

## 6. Ví dụ hoàn chỉnh theo luồng: chỉ chủ đơn được đọc hoặc sửa

Ví dụ dưới đây minh họa thiết kế **`@PreAuthorize` gọi policy bean có truy vấn database**. Nó dùng:

- `JwtAuthenticationToken` đã xác thực;
- một external identity mapping `(issuer, subject) → localUserId` nếu domain có người dùng nội bộ;
- bảng đơn hàng lưu `ownerUserId`, `tenantId`;
- repository kiểm tra tồn tại đơn hàng có đúng owner và tenant;
- service bảo vệ bằng **scope + policy trên orderId**.

### 6.1. Những bảng cần có

Lược đồ dữ liệu minh họa (PostgreSQL):

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE TABLE external_identity (
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    PRIMARY KEY (issuer, subject)
);

CREATE TABLE app_order (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    owner_user_id UUID NOT NULL REFERENCES app_user(id),
    note TEXT NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL
);

CREATE INDEX idx_app_order_owner_tenant
    ON app_order(owner_user_id, tenant_id);
~~~

**Một cặp (issuer, subject) chỉ ánh xạ tới một local user** nhờ khóa chính. Quan hệ dữ liệu với đơn hàng dùng `user_id` nội bộ. Hệ thống thật cần migration, transaction, domain constraints và quyền truy cập database phù hợp; SQL này chỉ tập trung vào cấu trúc để kiểm tra quyền.

### 6.2. Entity đơn hàng và repository

Các đoạn Java bên dưới được đặt thành những file class riêng trong cùng ứng dụng.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "app_order")
public class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_user_id", nullable = false)
    private UUID ownerUserId;

    @Column(nullable = false)
    private String note;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {}

    public UUID getId() { return id; }
    public String getTenantId() { return tenantId; }
    public UUID getOwnerUserId() { return ownerUserId; }
    public String getNote() { return note; }
    public String getStatus() { return status; }

    public void changeNote(String nextNote) {
        this.note = nextNote;
    }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    boolean existsByIdAndTenantIdAndOwnerUserId(
        UUID id, String tenantId, UUID ownerUserId);
}
~~~

`existsByIdAndTenantIdAndOwnerUserId` kiểm tra **quan hệ thật trong database**. Nó không sử dụng `ownerUserId` do client tự khai. Method query dạng Spring Data JPA phụ thuộc tên property Java của entity và Spring Data JPA được cấu hình.

### 6.3. Tra cứu local user đã liên kết

Chỉ cần xác định contract cho một service tra cứu liên kết:

~~~java
import java.util.Optional;
import java.util.UUID;

public interface LocalIdentityLookup {

    Optional<UUID> findActiveUserId(
        String issuer, String subject);
}
~~~

Một triển khai của interface này sẽ truy vấn **`external_identity`** theo cả `issuer` và `subject`, join **`app_user`**, và **chỉ trả user ID nếu tài khoản ACTIVE**. Không tự tạo tài khoản từ JWT khi chưa có quy trình provisioning/linking được chấp thuận.

Ví dụ SQL tương ứng:

~~~sql
SELECT u.id
FROM external_identity ei
JOIN app_user u ON u.id = ei.user_id
WHERE ei.issuer = :issuer
  AND ei.subject = :subject
  AND u.status = 'ACTIVE';
~~~

Phần này tách identity lookup khỏi policy đối với từng đơn hàng. Nếu hệ thống chỉ có issuer và subject làm domain ID ngay từ đầu, có thể thiết kế khác, nhưng vẫn cần tránh trộn chủ thể giữa các issuer.

### 6.4. Policy bean được gọi từ SpEL

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component("orderAccess")
public class OrderAccessPolicy {

    private final LocalIdentityLookup identities;
    private final OrderRepository orders;

    public OrderAccessPolicy(
            LocalIdentityLookup identities,
            OrderRepository orders) {
        this.identities = identities;
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public boolean canRead(
            Authentication authentication, UUID orderId) {
        return isOwner(authentication, orderId);
    }

    @Transactional(readOnly = true)
    public boolean canWrite(
            Authentication authentication, UUID orderId) {
        // Trong ứng dụng thật còn phải kiểm tra trạng thái
        // đơn hàng hoặc quyền chuyển trạng thái.
        return isOwner(authentication, orderId);
    }

    private boolean isOwner(
            Authentication authentication, UUID orderId) {

        if (orderId == null
                || !(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        Object tenantClaim = jwt.getClaims().get("tenant_id");

        if (issuer == null
                || subject == null
                || subject.isBlank()
                || !(tenantClaim instanceof String tenantId)
                || tenantId.isBlank()) {
            return false;
        }

        Optional<UUID> localUserId =
            identities.findActiveUserId(issuer, subject);

        return localUserId.isPresent()
            && orders.existsByIdAndTenantIdAndOwnerUserId(
                orderId, tenantId, localUserId.get());
    }
}
~~~

Vì được khai báo `@Component("orderAccess")`, bean có thể được tham chiếu trong SpEL là **`@orderAccess`**. Nếu mapping không có, tài khoản bị khóa, claim tenant sai kiểu, order không tồn tại hoặc khác owner, policy trả **false**, không mở quyền mặc định.

Ví dụ chỉ là chính sách **owner-only**; domain thật có thể cho phép hỗ trợ viên hoặc người được ủy quyền xem đơn hàng. Nếu có ngoại lệ như vậy, định nghĩa **quy tắc tường minh, kiểm chứng được** thay vì sửa fallback thành `true`.

### 6.5. Service với @PreAuthorize và input orderId

~~~java
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderDto(UUID id, String tenantId, String note, String status) {}
record UpdateNoteCommand(String note) {}

@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderAccess.canRead(authentication, #orderId)")
    public OrderDto getOrder(UUID orderId) {
        OrderEntity order = orders.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        return new OrderDto(
            order.getId(),
            order.getTenantId(),
            order.getNote(),
            order.getStatus());
    }

    @Transactional
    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') " +
        "and @orderAccess.canWrite(authentication, #orderId)")
    public OrderDto updateNote(
            UUID orderId, UpdateNoteCommand command) {

        if (command == null || command.note() == null) {
            throw new IllegalArgumentException("Invalid command");
        }

        OrderEntity order = orders.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        // Đối với cập nhật có rủi ro cao, kiểm tra lại
        // owner, tenant và domain state trong transaction.
        order.changeNote(command.note());

        return new OrderDto(
            order.getId(),
            order.getTenantId(),
            order.getNote(),
            order.getStatus());
    }
}
~~~

Ở đây:

- `hasAuthority('SCOPE_orders.read')` hoặc `SCOPE_orders.write` kiểm tra scope đã được chuyển thành authority.
- `@orderAccess.canRead(authentication, #orderId)` hoặc `canWrite` kiểm tra quyền đối với **bản ghi cụ thể**.
- `#orderId` là **đối số method**, có thể đến từ path, không phải ID đã được bảo đảm thuộc caller.
- `UpdateNoteCommand` chỉ chứa `note`, không chứa `ownerUserId` hoặc `tenantId` cho phép client tự thay chủ/tenant.

**Ranh giới giao dịch quan trọng:** việc policy query trước lời gọi và service tải bản ghi sau đó là **hai lần đọc**. Nếu quyền sở hữu, trạng thái hoặc tenant có thể thay đổi đồng thời, hệ thống phải bảo vệ cả bước **thực hiện thay đổi** — chẳng hạn kiểm tra lại trong transaction với lock/version hoặc dùng lệnh `UPDATE` có điều kiện owner/tenant/state. `@PreAuthorize` là **gate trước method**, không phải bảo đảm nguyên tử cho mọi điều kiện dữ liệu.

### 6.6. Controller truyền đúng dữ liệu, không tự nhận quyền

~~~java
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    OrderDto get(@PathVariable UUID orderId) {
        return orders.getOrder(orderId);
    }

    @PatchMapping("/{orderId}")
    OrderDto patch(
            @PathVariable UUID orderId,
            @RequestBody UpdateNoteCommand command) {
        return orders.updateNote(orderId, command);
    }
}
~~~

Controller chỉ chuyển dữ liệu đến **Spring-managed service bean**, không tự chấp nhận `ownerId` hoặc `roles` do client gửi. Với code ứng dụng chạy thực, cần bổ sung validation của request body, error handling, entity/lifecycle và database transaction policy. Dù có security annotation trên controller, đặt guard ở service quan trọng để những nơi gọi service khác không vô tình bỏ qua.

## 7. Dùng dữ liệu đầu vào trong SpEL đúng cách

Spring Security method expressions có thể tham chiếu parameters theo tên, thuộc tính object và vị trí.

### 7.1. Tham chiếu đối số #orderId

~~~java
@PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(UUID orderId) { ... }
~~~

`#orderId` phải được SpEL nhận diện là tham số method. Với Java, nên biên dịch có **parameter name metadata** (ví dụ `-parameters`, tùy Spring Boot/Gradle/Maven configuration), hoặc đặt tên tham số bằng annotation `@P`:

~~~java
import org.springframework.security.core.parameters.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(@P("orderId") UUID id) {
    // ...
}
~~~

Có thể dùng **`#p0`** hoặc **`#a0`** để tham chiếu tham số thứ nhất khi không có tên:

~~~java
@PreAuthorize("@orderAccess.canRead(authentication, #p0)")
public OrderDto getOrder(UUID id) { ... }
~~~

Tuy nhiên, tham chiếu theo vị trí dễ sai khi refactor thay đổi thứ tự arguments. **Nên giữ tên/annotation rõ ràng** và có test chứng minh biểu thức nhận đúng đối số. Một biểu thức tham chiếu tới parameter không tồn tại có thể bị lỗi đánh giá hoặc dẫn đến từ chối request; không nên kỳ vọng nó tự tìm giá trị ở URL.

### 7.2. Truy cập thuộc tính một command object

Ví dụ method tạo đơn hàng:

~~~java
public record CreateOrderCommand(
    String tenantId,
    String productCode,
    int quantity) {}
~~~

Một policy có thể đọc tenant client muốn thao tác:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and @tenantAccess.canCreate(authentication, #command.tenantId)")
public UUID createOrder(CreateOrderCommand command) {
    // ...
}
~~~

Điều quan trọng là `#command.tenantId` vẫn là **giá trị do client yêu cầu**. Bean `tenantAccess` phải **kiểm tra membership và quyền với nguồn dữ liệu tin cậy**, không chỉ trả `true` khi command có tenantId không rỗng. Trong Java, SpEL có thể đọc thuộc tính qua accessor phù hợp với record/JavaBean; nếu dùng kiểu đối tượng khác hoặc SpEL version khác, khai báo accessor nhất quán và test expression. Khi không muốn phụ thuộc property resolution, có thể truyền nguyên `#command` vào một method policy Java.

### 7.3. Đừng dùng input làm tên biểu thức hoặc tên quyền tùy ý

Ví dụ không nên làm:

~~~java
// KHÔNG LÀM: coi quyền do client yêu cầu là quyền phải có,
// hoặc ghép input thành chuỗi SpEL động.
@PreAuthorize("hasAuthority(#command.requestedAuthority)")
public void perform(AdminCommand command) {
    // ...
}
~~~

Điều kiện trên chỉ kiểm tra caller có authority **mà chính caller chọn** trong command. Nếu có một authority thấp hơn `SCOPE_profile.read`, caller có thể đặt `requestedAuthority` thành quyền đó và qua check, trong khi thao tác thật có thể là xóa user.

Thay bằng policy dựa trên **hành động server đã định nghĩa**:

~~~java
@PreAuthorize("hasAuthority('SCOPE_admin.users.delete')")
public void deleteUser(UUID targetUserId) {
    // ...
}
~~~

Tương tự, tuyệt đối không lấy chuỗi trong URL/body và **ghép thành SpEL để evaluation**. Các biểu thức `@PreAuthorize` nên được định nghĩa tĩnh từ code/cấu hình được kiểm soát; dữ liệu người gọi chỉ được xem là **giá trị tham số** trong policy.

## 8. Dùng @PreAuthorize cho read, write và admin

Một hệ thống có nhiều quy tắc có thể xây những guard sau:

### 8.1. Chỉ đọc đúng chủ tài nguyên

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(UUID orderId) { ... }
~~~

Sử dụng khi quyền đọc gắn với chủ đơn hoặc tenant. Không bỏ qua `canRead` chỉ vì token có scope đọc.

### 8.2. Ghi dữ liệu và kiểm tra trạng thái

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and @orderAccess.canWrite(authentication, #orderId)")
public void updateOrder(UUID orderId, UpdateNoteCommand command) {
    // ...
}
~~~

Bean `canWrite` cần kiểm tra domain-specific policy như quyền chủ sở hữu, tenant, trạng thái có thể sửa. Với dữ liệu thay đổi đồng thời, transaction và cập nhật có điều kiện vẫn cần thiết; xem mục 10.

### 8.3. Admin override phải tường minh

Nếu domain có quyền quản trị có thể xem đơn hàng của người khác:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_admin.orders.read') " +
    "or (hasAuthority('SCOPE_orders.read') " +
    "and @orderAccess.canRead(authentication, #orderId))")
public OrderDto getOrder(UUID orderId) { ... }
~~~

Đây là một chính sách ví dụ **cho phép admin đọc**; không có nghĩa mọi hệ thống nên cấp quyền đó. Nếu admin chỉ được quản trị trong tenant được phân công, nhánh admin cũng phải có **tenant policy**, không được là bypass toàn hệ thống. Tránh dùng `or` quá rộng như `hasRole('USER') or ...` khiến điều kiện owner vô hiệu.

### 8.4. Quyền phụ thuộc dữ liệu chứ không chỉ argument

Một yêu cầu `approveOrder(orderId)` có thể đòi:

- `SCOPE_orders.approve`.
- Người ký duyệt không phải chính người tạo đơn (separation of duties).
- Có vai trò người duyệt trong tenant của đơn.
- Đơn ở trạng thái `PENDING_APPROVAL`.
- Hạn mức và chính sách tài chính của người duyệt cho phép.

Các điều kiện trên cần đọc **trạng thái bản ghi và dữ liệu policy thật**, không thể xác minh chỉ bằng `orderId` hoặc `approve=true` do client gửi. `@PreAuthorize` có thể gọi bean policy để từ chối sớm; service phải tiếp tục bảo đảm transition hợp lệ **trong transaction** để không duyệt sai do cạnh tranh cập nhật.

## 9. Viết policy bean thay vì SpEL quá dài

Một expression dài:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and #request.tenantId == authentication.tokenAttributes['tenant_id'] " +
    "and #request.ownerId == authentication.name " +
    "and #request.status != 'CLOSED'")
~~~

có vẻ bao phủ nhiều điều kiện, nhưng thực tế:

- `request.tenantId`, `ownerId` và `status` có thể do client tự chọn.
- `authentication.name` có thể là external `sub`, không phải local user ID.
- `request.status` không phải trạng thái đơn hàng **đang lưu trong database**.
- Type của claim `tenant_id` hoặc object property có thể không đúng contract.
- Không thể thay thế kiểm tra trạng thái bản ghi thật và concurrency.

Cách rõ ràng hơn:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') " +
    "and @orderPolicy.canApply(authentication, #orderId, #command)")
public void apply(UUID orderId, UpdateOrderCommand command) {
    // ...
}
~~~

`orderPolicy.canApply` có thể thực hiện:

1. Xác định principal đáng tin cậy và loại token.
2. Resolve local account nếu domain dùng local user.
3. Kiểm tra tenant membership từ cơ sở dữ liệu.
4. Tải order thật, owner thật và trạng thái thật.
5. Kiểm tra những trường command mà caller được phép thay đổi.
6. Trả `false` nếu không đủ dữ liệu hoặc không có quyền.

**Không vì có policy bean mà tự tin mọi lần thực hiện thay đổi sẽ an toàn.** Nếu policy và thao tác ghi tách nhau về transaction hoặc dữ liệu có thể đổi, cần ràng buộc cập nhật ở service/repository như mục tiếp theo.

## 10. TOCTOU: @PreAuthorize không làm kiểm tra và ghi trở thành nguyên tử

**Time-of-check to time-of-use (TOCTOU)** là tình huống quyền/trạng thái đúng lúc kiểm tra nhưng thay đổi trước lúc sử dụng.

~~~text
T0: @PreAuthorize gọi canWrite
    -> Order thuộc user A, status DRAFT -> true

T1: Một transaction khác chuyển order sang CLOSED
    hoặc chuyển owner/tenant theo policy.

T2: updateOrder tải và ghi order
    -> Nếu không kiểm tra lại, có thể ghi trái trạng thái hiện tại.
~~~

Vì việc kiểm tra method security thường được thực hiện **trước thân method**, không nên coi một `@Transactional` trên service tự động đảm bảo mọi truy vấn của policy bean và body đã được khóa trong cùng một giao dịch/điều kiện dữ liệu. Thứ tự advisor và giao dịch cần được hiểu theo cấu hình; ngay cả khi nằm cùng transaction, mức isolation cũng có thể không ngăn mọi race condition.

### 10.1. Kiểm tra lại trong transaction hoặc cập nhật có điều kiện

Một kỹ thuật là dùng query chỉ cập nhật khi **owner, tenant và status** đang đúng:

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface GuardedOrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    @Modifying
    @Query("""
        update OrderEntity o
           set o.note = :nextNote
         where o.id = :id
           and o.tenantId = :tenantId
           and o.ownerUserId = :ownerId
           and o.status = 'DRAFT'
        """)
    int updateDraftNoteIfOwned(
        @Param("id") UUID id,
        @Param("tenantId") String tenantId,
        @Param("ownerId") UUID ownerId,
        @Param("nextNote") String nextNote);
}
~~~

Service có thể gọi phương thức này **trong transaction**, lấy `tenantId` và `ownerId` từ context đã xác minh/resolve, **không từ body chưa kiểm soát**, rồi kiểm tra số hàng được cập nhật:

~~~java
int affected = repository.updateDraftNoteIfOwned(
    orderId, verifiedTenant, currentLocalUserId, newNote);

if (affected != 1) {
    throw new AccessDeniedException(
        "Operation is not permitted");
}
~~~

Như vậy, database chỉ update nếu điều kiện owner/tenant/state **còn đúng tại thời điểm thực hiện câu lệnh**. Không nên tự đổi `affected == 0` thành thành công; nó có thể nghĩa là order không tồn tại, caller sai quyền hoặc trạng thái không còn cho sửa.

Trong ứng dụng thật, `@Modifying` cần transaction phù hợp và cần hiểu tác động của bulk JPQL update lên persistence context/cache; có thể phải refresh/clear entity. Ngoài ra, điều kiện concurrent update phức tạp có thể cần optimistic locking (`@Version`), pessimistic locking hoặc transaction isolation thích hợp. **Không có một lựa chọn áp dụng cho mọi domain**.

### 10.2. @PreAuthorize vẫn hữu ích

Tầng `@PreAuthorize` chặn sớm request thiếu scope hoặc hiển nhiên không có quyền, giảm việc chạy nghiệp vụ không cần thiết. Tầng transaction/data policy đảm bảo **thao tác thực sự** không bỏ qua các điều kiện quan trọng. Đây là **defense in depth**, không phải lặp lại vô ích.

## 11. @PostAuthorize, @PreFilter và @PostFilter khác gì?

Ngoài `@PreAuthorize`, Spring Security method security còn có những annotation giúp đánh giá dữ liệu tại thời điểm khác nhau.

| Annotation | Thời điểm | Ví dụ sử dụng | Lưu ý |
| --- | --- | --- | --- |
| **`@PreAuthorize`** | Trước method body. | Caller có scope và được phép gọi với `orderId`. | Không thấy return object; thường phù hợp chặn sớm. |
| **`@PostAuthorize`** | Sau khi method đã tạo kết quả. | Kiểm tra owner của đối tượng trả về. | Method đã chạy; **không dùng làm rào chắn duy nhất cho thao tác ghi/side effect**. |
| **`@PreFilter`** | Lọc collections đầu vào trước method. | Bỏ các item không được phép trong một tập đầu vào. | Dễ che giấu lỗi client, nên cân nhắc từ chối cả batch thay vì lọc âm thầm. |
| **`@PostFilter`** | Lọc collection kết quả. | Chỉ trả những item được phép xem. | Có thể đã tải quá nhiều dữ liệu, gây hiệu năng và rủi ro bên ngoài layer lọc. |

### 11.1. Ví dụ @PostAuthorize cho đọc dữ liệu

~~~java
@PostAuthorize(
    "returnObject.ownerUserId == @currentAccount.id(authentication)")
public OrderDto getOrder(UUID orderId) {
    // ...
}
~~~

**Đây chỉ là ví dụ ý tưởng**: `OrderDto` trong đoạn service trước không chứa `ownerUserId`, vì vậy cần một DTO/domain object thực sự có thuộc tính `ownerUserId` và một bean `currentAccount` đã được triển khai nếu muốn chạy đoạn này. `@PostAuthorize` có thể hữu ích với kết quả đọc, nhưng phương thức đã thực thi và có thể đã tải dữ liệu nhạy cảm vào bộ nhớ. Tránh sử dụng nếu việc gọi method gây email, ghi database hoặc external side effect trước khi check.

Với danh sách nhiều bản ghi, thường tốt hơn khi **ràng buộc câu truy vấn theo tenant/owner ngay tại database** thay vì lấy tất cả rồi `@PostFilter`; điều đó bảo đảm phân trang/số đếm đúng chính sách và giảm nguy cơ lộ dữ liệu qua các side effects khác.

### 11.2. Vì sao @PreAuthorize + policy bean thường là lựa chọn tốt?

Với phương thức `getOrder(orderId)`, ta **biết ID đầu vào trước khi đọc**. Một policy bean có thể truy vấn điều kiện owner/tenant và từ chối ngay. Nếu muốn gộp query business và authorization để tránh hai lần đọc, có thể dùng repository method có owner/tenant trong điều kiện và ném `AccessDeniedException` khi không tìm thấy. `@PreAuthorize` không bắt buộc phải chứa toàn bộ logic domain; quan trọng là **không có đường đi nào tới dữ liệu mà bỏ kiểm tra quyền**.

## 12. Method security dùng proxy: đừng để annotation bị bỏ qua

Trong cấu hình Spring Security Servlet thông thường, method authorization được áp dụng bằng cơ chế **Spring AOP proxies**. Điều này có nhiều hệ quả thực tế.

### 12.1. Gọi từ bean khác qua proxy

~~~text
OrderController
    |
    | gọi OrderService bean do Spring quản lý
    v
Spring proxy của OrderService
    |
    | kiểm tra @PreAuthorize
    v
OrderService.getOrder(...)
~~~

Nếu tạo instance bằng `new OrderService(...)` ngoài Spring container, annotation không được Spring AOP tự áp. Nên dùng dependency injection cho service có method security.

### 12.2. Self-invocation có thể bỏ qua bảo vệ

Ví dụ:

~~~java
@Service
public class UnsafeOrderService {

    public void batchProcess(UUID orderId) {
        // Gọi nội bộ bằng this, có thể không đi qua proxy.
        updateSensitiveOrder(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public void updateSensitiveOrder(UUID orderId) {
        // ...
    }
}
~~~

Trong mô hình proxy phổ biến, `batchProcess` gọi `updateSensitiveOrder` **bên trong cùng instance** nên `@PreAuthorize` có thể bị bỏ qua. Không xem annotation là sự bảo vệ chắc chắn nếu method được gọi qua `this`.

Giải pháp rõ ràng:

- Đưa method nhạy cảm sang **Spring-managed bean khác** và gọi qua dependency injection.
- Bảo vệ cả entrypoint `batchProcess` nếu nó cho phép thực hiện hành động nhạy cảm.
- Giữ **domain authorization check** trong operation thực sự, nhất là khi có nhiều đường gọi.
- Kiểm thử các đường gọi **nội bộ và bên ngoài** để không có bypass.

Các method `private`, `final` hoặc class `final` có thể không được intercept như mong đợi, phụ thuộc kiểu proxy và cấu hình. Với method cần `@PreAuthorize`, đặt trên method public của Spring bean và gọi qua proxy; nếu dùng AspectJ hoặc proxy strategy đặc biệt, cần hiểu cơ chế của dự án. Đừng chỉ kiểm tra annotation “có tồn tại trong source” mà bỏ qua việc nó có thực sự được thực thi không.

### 12.3. Lời gọi ngoài request thread

Với `@Async`, scheduled job, message listener hoặc xử lý đa luồng, `SecurityContext` từ HTTP request không mặc nhiên có sẵn ở mọi thread. Không tự gán một Authentication giả với quyền admin để “cho code chạy”. Thay vào đó, các luồng hệ thống cần danh tính service và policy riêng hoặc cơ chế propagation context phù hợp khi được phép.

Method security là một phần của **quy tắc thực thi ứng dụng**, không phải cơ chế tự cấp Authentication cho mọi nơi sử dụng service.

## 13. Kiểm thử @PreAuthorize và dữ liệu lời gọi

Test phải chứng minh **biểu thức được kích hoạt**, **đọc đúng authority**, **nhận đúng argument** và **policy bảo vệ tài nguyên**. Có thể tách hai nhóm test:

1. **Method security/unit-integration tests:** Spring context với `@EnableMethodSecurity`, service bean và Authentication giả có chủ đích.
2. **HTTP + JWT integration tests:** gửi Bearer JWT được ký thật qua Resource Server để kiểm tra cả decoder, scopes và policy.

### 13.1. Test bằng @WithMockUser: được gì, mất gì?

`spring-security-test` cho phép:

~~~java
@WithMockUser(authorities = "SCOPE_orders.read")
@Test
void readScopeCanCallMethod() {
    // Gọi service qua bean Spring, kỳ vọng cho phép
    // khi policy theo orderId được mock/fixture cho phép.
}
~~~

Đây là test tốt cho **biểu thức authority** và cơ chế proxy. Tuy nhiên `@WithMockUser` thường tạo Authentication mô phỏng username/password, **không phải JwtAuthenticationToken**. Nếu policy kiểm tra:

~~~java
authentication instanceof JwtAuthenticationToken
~~~

thì `@WithMockUser` **không đủ để test thành công** luồng thực tế; policy có thể trả false vì principal type khác. Cần dùng JwtAuthenticationToken giả lập hoặc MockMvc `jwt()` phù hợp.

### 13.2. Tạo JwtAuthenticationToken trong test service

Một fixture có thể tạo `JwtAuthenticationToken` với các claims giả hợp lệ về mặt cấu trúc, rồi đặt vào SecurityContext cho **test method security**, không test chữ ký:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

public final class JwtMethodSecurityFixture {

    private JwtMethodSecurityFixture() {}

    public static void authenticate(
            String issuer,
            String subject,
            String tenantId,
            String authority) {

        Instant now = Instant.now();

        Jwt jwt = new Jwt(
            "synthetic-test-token",
            now,
            now.plusSeconds(600),
            Map.of("alg", "RS256"),
            Map.of(
                "iss", issuer,
                "sub", subject,
                "aud", List.of("orders-api"),
                "tenant_id", tenantId));

        JwtAuthenticationToken authentication =
            new JwtAuthenticationToken(
                jwt,
                List.of(new SimpleGrantedAuthority(authority)));

        SecurityContextHolder.getContext()
            .setAuthentication(authentication);
    }

    public static void clear() {
        SecurityContextHolder.clearContext();
    }
}
~~~

Đây là **test helper**, không dùng trong production để tạo quyền tùy ý. Sau mỗi test phải clear SecurityContext (ví dụ dùng JUnit `@AfterEach`), tránh rò rỉ Authentication giữa các test cùng thread. Các authorities trong fixture do test đặt thủ công, nên **không chứng minh JwtGrantedAuthoritiesConverter** chuyển scope đúng.

### 13.3. Unit/integration test policy theo argument orderId

Ví dụ test ý tưởng với Spring-managed service, repository/test fixtures:

~~~text
Given JWT subject = person-A, tenant_id = tenant-A,
      authority = SCOPE_orders.read
And identity(person-A) -> local-user-A ACTIVE
And order-111 belongs to local-user-A and tenant-A
And order-222 belongs to local-user-B and tenant-A

When OrderService.getOrder(order-111)
Then allowed (nếu order-111 tồn tại và truy vấn thành công)

When OrderService.getOrder(order-222)
Then AccessDeniedException

When JWT authority only = SCOPE_orders.write
And OrderService.getOrder(order-111)
Then AccessDeniedException
~~~

Một class test mẫu với Spring context có thể gọi service và dùng `assertThrows`; ví dụ này giả định **dữ liệu test ở repositories đã được chuẩn bị**:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class OrderMethodSecurityTest {

    @Autowired OrderService service;

    private final UUID orderOwnedByOtherUser =
        UUID.fromString("22222222-2222-4222-8222-222222222222");

    @AfterEach
    void tearDown() {
        JwtMethodSecurityFixture.clear();
    }

    @Test
    void readerCannotReadSomeoneElsesOrder() {
        JwtMethodSecurityFixture.authenticate(
            "https://identity.example.test/realms/demo",
            "person-A",
            "tenant-A",
            "SCOPE_orders.read");

        assertThrows(
            AccessDeniedException.class,
            () -> service.getOrder(orderOwnedByOtherUser));
    }
}
~~~

**Lưu ý:** test trên cần database fixture ánh xạ principal A và dữ liệu order 222 thuộc user khác; nó không phải một test độc lập chạy được chỉ từ code snippet. Nó minh họa việc **gọi Spring-managed service bean** để Spring method interceptor có cơ hội thực thi. Nếu không có dữ liệu fixture, test có thể thất bại vì lý do không liên quan quyền.

### 13.4. MockMvc(jwt()) để thử HTTP + @PreAuthorize

Với controller gọi service bean, có thể dùng helper:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", ownOrderId)
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://identity.example.test/realms/demo")
                .subject("person-A")
                .claim("tenant_id", "tenant-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Với `otherOrderId`, trong cùng security context:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", otherOrderId)
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://identity.example.test/realms/demo")
                .subject("person-A")
                .claim("tenant_id", "tenant-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());
~~~

Hai ví dụ giả định test đã nạp dữ liệu identity/order và Spring Security/MVC context phù hợp. Helper `jwt()` của `spring-security-test` tạo principal đã xác thực **mà không đi qua JwtDecoder để kiểm tra chữ ký**. Nó thích hợp để test quyền theo **method argument và database policy**, nhưng không chứng minh token từ issuer thật sẽ được chấp nhận.

Muốn xác minh chữ ký, audience, thời hạn và JWT claim conversion, cần một test riêng với **JWT được ký bằng private key test** và `NimbusJwtDecoder` thật hoặc JWKS test server.

### 13.5. Ma trận test bắt buộc cho dữ liệu input

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| JWT hợp lệ, `SCOPE_orders.read`, order thuộc caller | Đọc được nếu domain cho phép. |
| JWT hợp lệ, có scope đọc, order thuộc user khác | **403** do method/domain policy. |
| JWT hợp lệ, có scope đọc, order ở tenant khác | **403** (hoặc 404 theo chính sách che giấu tài nguyên). |
| JWT hợp lệ, thiếu scope đọc, order thuộc caller | **403** do `hasAuthority`. |
| JWT có scope ghi nhưng chỉ gọi read endpoint được policy khác | Theo policy được định nghĩa; không tự suy write bao hàm read. |
| JWT hợp lệ, user nội bộ bị SUSPENDED | Từ chối vì identity/domain policy. |
| JWT hợp lệ nhưng `tenant_id` thiếu hoặc sai kiểu | Validator hoặc policy từ chối, không cấp quyền. |
| JWT từ issuer khác có trùng `sub` | Không dùng identity link của issuer tin cậy khác. |
| JWT giả chữ ký nhưng `sub` đúng user | **401** từ decoder; không được vào method như principal hợp lệ. |
| Client đặt `ownerId` trong body thành user khác | Không thay owner ngoài quy trình được phép. |
| Client đặt `requestedAuthority` trong body thành quyền thấp để bypass | Phương thức nhạy cảm vẫn yêu cầu authority do server định nghĩa. |
| `orderId` không tồn tại | Không trả dữ liệu; 404/403 tùy policy không tiết lộ tài nguyên. |
| Order đổi trạng thái/owner giữa check và write | Transaction/update guard chặn thay đổi trái policy. |
| Service tự gọi method có `@PreAuthorize` qua `this` | Test phát hiện bypass, sau đó sửa kiến trúc/proxy. |

**Kiểm thử âm tính quan trọng nhất:** cùng một JWT và cùng scope, thay **argument `orderId`** từ đơn hàng được phép sang không được phép phải làm kết quả đổi từ **allow** sang **deny**. Nếu cả hai vẫn thành công, policy chưa thực sự ràng buộc quyền vào dữ liệu.

## 14. Lỗi HTTP và cách phản hồi phù hợp

Với Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

thường xảy ra khi không có token hợp lệ hoặc token sai chữ ký, issuer, audience, thời hạn. Request không thể trở thành principal đáng tin cậy.

Nếu JWT đã được xác thực nhưng thiếu authority hoặc `@PreAuthorize` trả false:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"forbidden","message":"Không đủ quyền thực hiện thao tác."}
~~~

Chi tiết `WWW-Authenticate` và response body phụ thuộc Spring Security exception handling và API contract. Với lỗi xuất hiện ở filter chain trước controller, `@RestControllerAdvice` không bao phủ mọi trường hợp. Với `AccessDeniedException` xuất hiện trong service/controller, cần có integration test bảo đảm xử lý thành mã HTTP mong muốn.

Tránh phản hồi:

~~~json
{
  "error": "Order 222 belongs to user-B in tenant-secret"
}
~~~

Thông điệp như vậy làm lộ sự tồn tại tài nguyên và thông tin chủ sở hữu. Với hệ thống cần che giấu tài nguyên, có thể dùng **404 Not Found** ở những tình huống không được đọc, nhưng phải nhất quán, tránh rò rỉ qua timing/size/error details và vẫn ghi audit nội bộ khi cần.

Không log nguyên Bearer JWT, Authorization header hoặc claims cá nhân chỉ để debug `@PreAuthorize`. Log có thể ghi **request ID, mã loại lỗi và kết quả policy được chuẩn hóa**, kèm định danh nội bộ đã được kiểm soát ở hệ thống audit có giới hạn truy cập.

## 15. Những lỗi phổ biến khi kết hợp authority và input

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Chỉ kiểm tra `hasAuthority` cho method nhận `orderId`. | Caller có scope có thể xem/sửa bản ghi của người khác. | Kiểm tra owner/tenant với dữ liệu thật. |
| So JWT subject với `userId` do client gửi. | Không chứng minh order thuộc subject. | Lookup order và identity mapping đã xác thực. |
| Tin `tenantId`/role/owner trong body như quyền đã được xác thực. | Client tự khai quyền. | So với claims đã được xác minh và membership/domain state. |
| Chọn quyền động từ `command.requestedAuthority`. | Client có thể chọn điều kiện quyền quá thấp. | Quyền bắt buộc cố định theo thao tác server. |
| Gộp `hasRole` và `hasAuthority` mà không hiểu prefix. | Quy tắc sai hoặc vô tình cấp quyền. | Phân biệt `ROLE_` và `SCOPE_`, test converter. |
| Quên `@EnableMethodSecurity`. | Annotation có thể không được thực thi. | Bật method security và test qua Spring context. |
| Gọi method annotated qua `this` cùng bean. | Bypass Spring AOP proxy. | Gọi qua bean khác/thiết kế method guard rõ. |
| Đặt annotation trên `private` hoặc final method và mặc nhiên tin được intercept. | Guard có thể không chạy. | Bảo vệ public method phù hợp proxy, test behavior. |
| `#orderId` không resolve được vì thiếu metadata tên parameter. | Lỗi expression/deny ngoài dự kiến. | Dùng `-parameters`, `@P` hoặc `#p0` có chủ đích. |
| Dùng `@PostAuthorize` làm guard duy nhất cho thao tác ghi. | Side effect đã xảy ra trước khi chặn. | `@PreAuthorize` + domain transaction guard. |
| Chỉ kiểm tra owner trước transaction mà không bảo vệ thao tác update. | TOCTOU/race condition. | Recheck trong transaction, conditional update/locking. |
| Test bằng `@WithMockUser` nhưng policy đòi JwtAuthenticationToken. | Test không mô phỏng principal đúng loại. | Dùng JwtAuthenticationToken fixture hoặc `jwt()`. |
| Test MockMvc `jwt()` rồi kết luận decoder an toàn. | Helper bỏ qua chữ ký/issuer/audience. | Test JWT ký thật và decoder riêng. |
| Cho phép mọi URL vì đã có `@PreAuthorize` ở một service. | Endpoint khác có thể gọi logic không có guard. | HTTP rules với fallback deny và method/domain security. |
| Không phân biệt service principal và human user. | Client credentials token có thể chiếm quyền người dùng. | Chính sách theo token profile và identity type. |

## 16. Phương pháp thiết kế policy cho một phương thức mới

Khi cần bảo vệ method `approveOrder(UUID orderId, ApproveCommand command)`, đừng bắt đầu bằng một biểu thức SpEL dài. Hãy trả lời tuần tự:

1. **Caller được xác thực bằng gì?** JWT Access Token hay opaque token? Issuer/audience/expiry đã được kiểm tra chưa? Cần user hay service principal?
2. **Thao tác đòi quyền tổng quát nào?** Ví dụ `SCOPE_orders.approve`; đó là authority do token/converter đáng tin cung cấp.
3. **Method nhận input nào?** `orderId`, `command.reason`, `command.status` — tất cả là dữ liệu cần validate, không phải quyền.
4. **Dữ liệu nghiệp vụ thật ở đâu?** Database chứa order owner, tenant, workflow state; policy phải đọc đúng record đó.
5. **Có ngoại lệ quyền nào được phép?** Supervisor/admin, delegation, hạn mức; định nghĩa rõ và kiểm tra đúng tenant, không làm quyền admin chung thành bypass ngoài ý định.
6. **Chặn ở đâu trước method?** `@PreAuthorize` gồm authority cố định và call policy bean với arguments.
7. **Bảo vệ lúc ghi bằng gì?** Transaction, constraint, optimistic locking hoặc conditional update khi trạng thái/owner có thể thay đổi.
8. **Những đường gọi nào tồn tại?** HTTP, batch, async, self-invocation; mọi entrypoint cần guard phù hợp.
9. **Trường hợp nào phải bị bác?** Scope thiếu, issuer sai, subject không có mapping, sai tenant, sai owner, trạng thái không cho thao tác, input bất thường, race.
10. **Làm sao biết guard thực sự chạy?** Test qua Spring proxy, test các `orderId` khác nhau và thêm signed-JWT integration test cho authentication.

Ví dụ biểu thức cuối cùng có thể ngắn gọn:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.approve') " +
    "and @approvalPolicy.canApprove(authentication, #orderId, #command)")
public ApprovalResult approveOrder(
        UUID orderId, ApproveCommand command) {
    // Domain transaction vẫn ràng buộc state/owner/tenant.
}
~~~

`approvalPolicy`, `ApproveCommand` và `ApprovalResult` trong đoạn trên là các thành phần **minh họa cần được triển khai theo nghiệp vụ**, không phải API có sẵn của Spring Security. Chính sách Java bên dưới annotation cần xử lý cả dữ liệu đã xác thực và điều kiện hiện thời của đơn hàng.

## 17. Tổng kết

Ba quy tắc nên giữ nhất quán:

1. **Authority trả lời “caller có quyền loại thao tác này không?”** Ví dụ `SCOPE_orders.read` hoặc `SCOPE_orders.write`, được lấy từ Authentication đã được xác thực.
2. **Dữ liệu đầu vào trả lời “caller muốn thao tác trên đối tượng nào?”** Ví dụ `#orderId`, `#command.tenantId`; các giá trị này thường do client kiểm soát và không chứng minh quyền.
3. **Policy nghiệp vụ trả lời “caller có quyền trên đúng đối tượng đó ở trạng thái hiện tại không?”** Cần đối chiếu owner, tenant, local account, membership và trạng thái database; đối với thao tác ghi, kết quả phải được bảo vệ trong transaction.

`@PreAuthorize` hiệu quả nhất khi được dùng trên **Spring-managed service methods**, kết hợp `hasAuthority` với một **policy bean kiểm tra arguments theo dữ liệu tin cậy**, và có **kiểm thử thực sự đi qua proxy**. JWT validation, HTTP rules và transaction/data guards là các lớp bổ sung — không lớp nào nên được bỏ chỉ vì lớp khác đã cho phép request.

## Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JWT Authentication Converter](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html#oauth2resourceserver-jwt-authorization).
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
