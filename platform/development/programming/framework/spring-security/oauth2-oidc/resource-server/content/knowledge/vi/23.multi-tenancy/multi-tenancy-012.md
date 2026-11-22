# Kiểm thử token hợp lệ nhưng thuộc tenant khác với tài nguyên yêu cầu

Trong hệ thống **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server** phục vụ nhiều tenant, một access token có thể **hoàn toàn hợp lệ về mật mã và giao thức** nhưng vẫn **không được phép truy cập một tài nguyên**. Ví dụ: JWT được ký đúng, chưa hết hạn, đúng issuer và audience, có scope `orders.read`, nhưng đại diện cho người dùng đang hoạt động ở **tenant-A**, trong khi đơn hàng được yêu cầu lại thuộc **tenant-B**.

Đây không nhất thiết là lỗi **authentication**. Resource Server đã xác định được caller là ai; vấn đề nằm ở **authorization theo tenant và tài nguyên**. Nếu backend chỉ kiểm tra `hasAuthority("SCOPE_orders.read")` rồi đọc bản ghi bằng ID mà không ràng buộc tenant, attacker có thể dùng một access token hợp lệ của tenant mình để truy cập dữ liệu tenant khác. Đây là một dạng **Broken Object Level Authorization (BOLA/IDOR)** và **cross-tenant data leakage**.

Bài học này tập trung vào cách **thiết kế và kiểm thử những trường hợp token hợp lệ nhưng tenant không phù hợp**, từ Spring Security filter chain đến repository, business service, API response và side effects. Mục tiêu không chỉ là nhìn thấy HTTP 403 hoặc 404, mà là chứng minh **không có dữ liệu, thao tác cập nhật, event hoặc cache entry thuộc tenant khác bị lộ hoặc sử dụng sai**.

> **Bất biến bảo mật:** Một access token hợp lệ **chỉ xác thực caller và cung cấp những quyền đã được cấp**, không tự cho phép truy cập **mọi tenant**. Mỗi thao tác trên tài nguyên phải chứng minh caller có quyền đối với **đúng tenant của tài nguyên đó**. Khi không chứng minh được, **fail closed**; không truy vấn rộng rồi cố che kết quả ở UI.

## 1. Ví dụ tối thiểu: token tenant-A, đơn hàng tenant-B

Giả sử Orders API phục vụ nhiều cửa hàng/đơn vị kinh doanh:

| Tenant | Người dùng | Order | Chủ sở hữu |
| --- | --- | --- | --- |
| `tenant-A` | `alice` | `order-A100` | `alice` |
| `tenant-A` | `bob` | `order-A200` | `bob` |
| `tenant-B` | `carol` | `order-B100` | `carol` |
| `tenant-B` | `alice` (nếu có membership riêng) | `order-B200` | `alice` trong tenant B |

JWT access token mà Alice sử dụng cho tenant A có claims minh họa:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel",
  "tenant_id": "tenant-A",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

Với hợp đồng ví dụ này, `tenant_id` là **tenant context đã được Authorization Server tin cậy xác lập** khi phát access token, không phải chuỗi caller có thể tự đặt trong request. Orders API còn cần bảo đảm token được **xác minh chữ ký, issuer, audience, thời hạn và profile** trước khi tin claim ấy.

Hai request cần phân biệt:

~~~http
# Request 1: URL nêu tenant-B, token gắn với tenant-A.
GET /api/tenants/tenant-B/orders/order-B100 HTTP/1.1
Authorization: Bearer <valid-token-of-alice-in-tenant-A>
~~~

~~~http
# Request 2: URL nêu tenant-A, nhưng ID thực tế là order của tenant-B.
GET /api/tenants/tenant-A/orders/order-B100 HTTP/1.1
Authorization: Bearer <valid-token-of-alice-in-tenant-A>
~~~

**Cả hai phải bị từ chối.**

- Ở **Request 1**, tenant trong URL khác tenant được chứng minh từ token/context.
- Ở **Request 2**, URL và token cùng ghi tenant A nhưng **bản ghi đích thuộc tenant B**. Nếu code chỉ so `pathTenant.equals(jwtTenant)` mà sau đó gọi `findById("order-B100")`, hệ thống vẫn có thể lộ Order B100. Vì vậy đây là một negative test rất quan trọng mà các bộ test chỉ kiểm tra path thường bỏ sót.

Request hợp lệ:

~~~http
GET /api/tenants/tenant-A/orders/order-A100 HTTP/1.1
Authorization: Bearer <valid-token-of-alice-in-tenant-A>
~~~

Với token còn hiệu lực, scope `orders.read` và policy owner/tenant phù hợp, request này có thể trả 200.

## 2. Ba ranh giới phải kiểm tra độc lập

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer token"]
    B["JwtDecoder hoặc opaque introspection"]
    C{"Token hợp lệ, đúng issuer/audience?"}
    X["Authentication failure"]
    D["Authentication + SCOPE_orders.read"]
    E{"Endpoint cho phép scope này?"}
    F["Authorization denied"]
    G["Xác định tenant context đáng tin"]
    H{"Tenant context được phép?"}
    I["Tìm resource với điều kiện tenant + quyền đối tượng"]
    J{"Resource thuộc phạm vi caller?"}
    K["Không trả data / không có side effect"]
    L["Thực hiện nghiệp vụ hợp lệ"]

    A --> B --> C
    C -->|Không| X
    C -->|Có| D --> E
    E -->|Không| F
    E -->|Có| G --> H
    H -->|Không| K
    H -->|Có| I --> J
    J -->|Không| K
    J -->|Có| L
~~~

### 2.1. Authentication: token có được tin không?

Với signed JWT, Resource Server cần xác minh:

- Chữ ký bằng khóa được tin cậy theo issuer/JWKS.
- `iss` thuộc tập issuer được API chấp nhận.
- `aud` dành cho **Orders API**, không phải một API khác.
- Thời hạn `exp`, `nbf` và validators cần thiết.
- Access-token profile/type theo hợp đồng; không dùng OIDC ID token làm access token.

Với opaque access token, Resource Server cần introspect qua Authorization Server đáng tin, kiểm tra `active` và resource/audience binding tương ứng. Không parse một opaque token theo suy đoán.

Nếu thất bại ở đây, **không có Authentication hợp lệ**. Tình huống này khác với bài kiểm thử chính: **token hợp lệ nhưng không được truy cập tenant khác**.

### 2.2. Authorization ở endpoint: loại thao tác có được phép không?

Sau authentication, Spring Security có thể map `scope` hoặc `scp` thành `GrantedAuthority` như:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/tenants/*/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

chỉ nói caller được thực hiện **loại thao tác đọc đơn** theo hợp đồng scope. Nó **không** nói caller có thể đọc đơn thuộc mọi tenant. Điều kiện tiếp theo phải là **tenant- và resource-scoped authorization**.

### 2.3. Authorization theo tài nguyên: đơn thuộc tenant nào?

Một policy:

~~~text
canReadOrder(caller, requestedOrder)
  = JWT hợp lệ cho Orders API
  AND scope orders.read
  AND tenant context được caller phép dùng
  AND requestedOrder.tenantId == authorizedTenantId
  AND requestedOrder.owner/assignment phù hợp caller
~~~

Trong hệ thống có hỗ trợ support staff, owner condition có thể thay bằng rule `owner OR explicitly assigned support`, nhưng **mỗi nhánh phải gắn đúng tenant**. Không để role `ADMIN` thiếu namespace trở thành quyền xem tất cả tenant.

## 3. Phân biệt issuer, audience, tenant và subject

Các thuộc tính này trả lời những câu hỏi khác nhau:

| Thuộc tính | Câu hỏi | Không được nhầm với |
| --- | --- | --- |
| `iss` | Token do nguồn phát hành nào phát? | ID tenant |
| `aud` | Token dành cho Resource Server/API nào? | Tenant được phép truy cập |
| `sub` | Chủ thể token là ai trong namespace issuer? | Owner của mọi bản ghi |
| `client_id` / `azp` theo profile | OAuth2 Client nào sử dụng/được cấp token? | User ID hoặc tenant ID |
| `scope` | Token cho phép loại thao tác nào? | Danh sách tài nguyên/tenant cụ thể |
| `tenant_id` (custom) | Tenant context token ràng buộc, **nếu AS có hợp đồng như vậy** | Bằng chứng độc lập rằng mọi order đều thuộc tenant đó |
| Local membership | User/service có membership/role nào trong tenant? | Chữ ký JWT hoặc issuer |
| Resource `tenant_id` | Bản ghi thực tế thuộc tenant nào? | Tenant path do Client gửi |

Một chuỗi `sub` giống nhau ở hai issuer **không nhất thiết là một người**. Khi liên kết user từ AS vào dữ liệu nội bộ, thường cần một mapping an toàn theo **`(iss, sub)`**. Trong một API đơn issuer như ví dụ thực hành, có thể dùng `sub` sau khi issuer đã được xác minh; API đa issuer phải mở rộng khóa owner hoặc map sang internal user ID.

### 3.1. `tenant_id` là claim tùy chỉnh, không phải yêu cầu mặc định OAuth2/OIDC

OAuth 2.0 không bắt buộc mọi access token phải chứa `tenant_id`. Một Authorization Server có thể dùng `organization_id`, `org_id`, `tenant`, memberships metadata hoặc token dành cho resource/tenant riêng. Các tên này **không tự có ngữ nghĩa chung**.

Nếu hệ thống chọn `tenant_id`, phải viết rõ:

1. AS nào phát hành claim này?
2. Claim thể hiện **active tenant** hay **một membership trong nhiều tenant**?
3. User có thể tự chọn giá trị tùy ý khi xin token không, và AS có kiểm tra quyền chọn tenant không?
4. Claim có thể thay đổi khi đổi tenant hay cần phát access token mới?
5. Khi user bị loại khỏi tenant, token/cached membership được thu hồi hoặc hết hạn theo SLA nào?
6. Client Credentials service token có `tenant_id` không, hay dùng service permission riêng?

Không chỉ viết `jwt.getClaimAsString("tenant_id")` rồi cho rằng mọi ranh giới đã được bảo vệ.

### 3.2. Tenant trong URL/header là đầu vào, không tự là quyền

Request:

~~~http
GET /api/tenants/tenant-B/orders/order-B100 HTTP/1.1
Authorization: Bearer <token-tenant-A>
X-Tenant-Id: tenant-B
~~~

`tenant-B` ở URL/header là **giá trị caller yêu cầu**. Nó có thể được dùng làm selector nhưng phải được so với tenant context/membership **đã xác minh**. Không tin `X-Tenant-Id` làm nguồn duy nhất của tenant authorization.

Sai:

~~~java
String tenantId = request.getHeader("X-Tenant-Id");
return orderRepository.findByTenantId(tenantId);
~~~

Đúng về mặt nguyên tắc:

~~~text
Requested tenant (untrusted)
  -> đối chiếu với verified tenant context / active membership
  -> dùng tenant được phê duyệt làm điều kiện truy vấn dữ liệu
~~~

## 4. Hai loại cross-tenant test bắt buộc

Đây là **trọng tâm** của bài học.

### 4.1. Kiểu A: token tenant A, URL tenant B

~~~text
verified JWT tenant_id = tenant-A
GET /api/tenants/tenant-B/orders/order-B100
~~~

Expected:

- Token được xác thực, không bị đánh đồng thành token giả.
- Endpoint có thể thấy `SCOPE_orders.read`, nhưng tenant authorization phải từ chối.
- Không gọi repository đọc theo `tenant-B` chỉ vì URL ghi như vậy.
- Không trả nội dung, số dư, chủ sở hữu hay metadata của Order B100.
- HTTP có thể là **403** hoặc **404** theo policy disclosure của API.

Một kiểm thử chỉ đưa token hợp lệ rồi so status 403 có thể chưa đủ: cần xác nhận **tenant context phía server không bị thay bằng path/header do caller gửi**.

### 4.2. Kiểu B: token và URL tenant A, resource ID thuộc tenant B

~~~text
verified JWT tenant_id = tenant-A
GET /api/tenants/tenant-A/orders/order-B100
Database: order-B100.tenant_id = tenant-B
~~~

Expected:

- Tenant path check có thể thành công.
- Repository phải tìm Order B100 **trong tenant A**, nhận kết quả rỗng.
- Không đọc/trả bản ghi thực thuộc tenant B.
- Không cập nhật cache với dữ liệu tenant B.
- Nếu là POST/DELETE, không có mutation hoặc event.

**Đây là negative test phát hiện lỗi `findById(id)` không lọc tenant**, kể cả khi developer đã so JWT tenant với URL tenant. Không được bỏ test này.

### 4.3. Kiểu C: đúng tenant nhưng sai owner

~~~text
JWT: tenant-A, sub=alice
URL: tenant-A
Order: tenant-A, owner=bob
~~~

Expected: từ chối nếu endpoint dành cho owner. Đúng tenant là **điều kiện cần**, không phải đủ. Các API B2B có thể cho phép support staff đọc dữ liệu người khác nhưng phải có **assignment hoặc role theo tenant** được chứng minh riêng.

## 5. Chọn 401, 403 hay 404 cho trường hợp khác tenant

| Tình huống | Lớp lỗi | Phản hồi thường phù hợp |
| --- | --- | --- |
| Không gửi token | Authentication | **401 Unauthorized** |
| JWT sai chữ ký, hết hạn hoặc audience không đúng | Authentication/token validation | **401** điển hình |
| Token hợp lệ nhưng thiếu `SCOPE_orders.read` | Authorization ở route | **403 Forbidden** |
| Token hợp lệ và scope đủ nhưng tenant path không được phép | Tenant authorization | **403** hoặc **404** theo API policy |
| Token hợp lệ, path tenant đúng, resource ID thuộc tenant khác | Object authorization | Thường **404 Not Found** để tránh tiết lộ bản ghi |
| Token hợp lệ, cùng tenant nhưng owner/assignment sai | Object authorization | **403** hoặc **404**, nhất quán với contract |
| Không truy cập được membership DB cần cho authorization | Dependency/policy failure | Fail closed; status tùy exception handling |

**Token hợp lệ nhưng sai tenant không nên bị mô tả như token sai chữ ký.** Đây thường là **authorization denial**, không nhất thiết 401. Một số API chọn **404** cho mọi object ngoài phạm vi caller để không tiết lộ object có tồn tại hay không. Một số API quản trị chọn **403** để Client biết đã xác thực nhưng không được phép.

Quyết định 403 hay 404 phải **nhất quán** với chính sách chống enumeration. Nếu object khác tenant trả 403 còn ID không tồn tại trả 404, attacker có thể suy luận object tồn tại. Cần cân nhắc cả body, độ trễ, pagination và thông tin trong log/trace.

**Không dùng redirect login hoặc refresh token tự động như cách sửa lỗi sai tenant**: token vẫn hợp lệ. User chỉ có thể chuyển tenant qua một luồng được AS/app cho phép, hoặc được cấp membership/permission thích hợp.

## 6. Thiết kế dữ liệu test để phát hiện lộ tenant

Một bộ fixture tốt cần có nhiều hơn một tenant và nhiều hơn một user:

| ID | tenant_id | owner_subject | status | Mục đích |
| --- | --- | --- | --- | --- |
| `order-A100` | `tenant-A` | `alice` | `OPEN` | Happy path |
| `order-A200` | `tenant-A` | `bob` | `OPEN` | Same tenant, wrong owner |
| `order-B100` | `tenant-B` | `carol` | `OPEN` | Cross-tenant ID |
| `order-B200` | `tenant-B` | `alice` | `OPEN` | Cùng subject nhưng tenant khác |
| `order-A300` | `tenant-A` | `alice` | `CANCELLED` | Trạng thái nghiệp vụ không cho thao tác |

Tại sao có `order-B200` với `owner_subject=alice`? Để phát hiện một câu truy vấn **chỉ lọc owner nhưng quên tenant**. Cùng một user có thể tham gia nhiều tenant, hoặc hai hệ thống có thể dùng subject giống nhau. Nếu API chỉ làm:

~~~sql
SELECT * FROM orders
WHERE id = :orderId AND owner_subject = :subject;
~~~

thì token context tenant A của Alice vẫn có thể tìm Order B200. Điều kiện tenant bắt buộc phải nằm trong query hoặc một cơ chế row-level authorization tương đương.

### 6.1. SQL an toàn: ràng buộc cùng lúc ID, tenant, owner

~~~sql
SELECT id, tenant_id, owner_subject, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :authorizedTenant
  AND owner_subject = :authorizedSubject;
~~~

Nếu role hỗ trợ có thể xem đơn không phải owner, cần một nhánh policy **được phép và được ràng buộc tenant**. Không sửa thành:

~~~sql
-- SAI: OR có thể làm mất ranh giới tenant.
WHERE id = :orderId
  AND (tenant_id = :authorizedTenant
       OR owner_subject = :authorizedSubject);
~~~

Một `OR` sai vị trí có thể cho user thấy đơn tenant khác chỉ vì trùng subject. Những query có `OR`, `JOIN` hoặc dynamic filters rất cần negative tests với fixture nhiều tenant.

### 6.2. Đừng chỉ test ID không tồn tại

Nếu negative test chỉ gọi `/orders/nonexistent` và nhận 404, nó **không chứng minh tenant isolation**. Dùng **ID chắc chắn tồn tại trong tenant B** và yêu cầu bằng token tenant A. Chính tình huống dữ liệu có thật mới phát hiện truy vấn thiếu tenant predicate.

## 7. Ví dụ Spring Boot 3 / Spring Security 6 với một tenant context trong JWT

Ví dụ sau dùng **Spring MVC/Servlet Resource Server**, Java 17+, Spring Data JPA và access token JWT. Nó minh họa policy **một token chỉ đại diện một active tenant**, với một trusted issuer duy nhất. Đây là **một profile cụ thể**, không phải chuẩn bắt buộc của mọi hệ thống multi-tenant.

### 7.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Database driver và phiên bản dependency được lựa chọn theo môi trường/dòng Spring Boot của dự án.

### 7.2. Cấu hình JWT issuer và audience

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: orders-api
~~~

Ví dụ URI:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

Đây là địa chỉ minh họa. Không dùng JWKS URL do Client gửi, không chấp nhận issuer dev tại production, và không coi `tenant_id` là đáng tin nếu JWT chưa được xác minh. Trong nhiều cấu hình, issuer validator đã có nhưng **audience vẫn cần được xác nhận tường minh** theo hợp đồng.

Một `JwtDecoder` minh họa kiểm tra issuer + audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Access token audience is not accepted",
                            null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience));
        return decoder;
    }
}
~~~

Khi tự tạo `JwtDecoder` bean, cần chịu trách nhiệm giữ đầy đủ validators phù hợp cho issuer, thời gian và audience; đây không phải nơi nên bỏ qua các kiểm tra chỉ để test cross-tenant dễ pass. Có thể dùng decoder/profile khác tùy phiên bản Spring Security, nhưng **token validation phải có thật** trong production.

### 7.3. `SecurityFilterChain`: scope chỉ là lớp đầu

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
class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST,
                        "/api/tenants/*/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đoạn này có ba điều kiện/giả định cần ghi nhớ:

1. API chỉ nhận **Bearer token trong Authorization header**, không chấp nhận session/cookie làm credential cho các route này; vì vậy CSRF được tắt **theo threat model cụ thể**, không vì JWT stateless.
2. `hasAuthority("SCOPE_orders.read")` và `hasAuthority("SCOPE_orders.cancel")` **không so tenant**. Service/repository bên dưới phải làm việc đó.
3. `securityMatcher("/api/**")` chỉ bao phủ URL trong `/api/**`; cần policy/filter chain khác cho những endpoint ngoài phạm vi nếu có.

Mọi scope/role đều phải được ánh xạ từ claims đã xác minh với converter phù hợp; một scope tên giống nhau ở API khác không loại bỏ kiểm tra JWT audience.

## 8. Repository: luôn ràng buộc tenant với bản ghi

Một entity minh họa:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private String id;

    @Column(nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String ownerSubject;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {}

    public OrderEntity(String id, String tenantId,
                       String ownerSubject, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.ownerSubject = ownerSubject;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOwnerSubject() { return ownerSubject; }
    public String getStatus() { return status; }

    public void cancel() { this.status = "CANCELLED"; }
}
~~~

Repository:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, String> {

    Optional<OrderEntity> findByIdAndTenantIdAndOwnerSubject(
            String id,
            String tenantId,
            String ownerSubject);

    List<OrderEntity> findByTenantIdAndOwnerSubjectOrderByIdAsc(
            String tenantId,
            String ownerSubject);
}
~~~

Trong thiết kế production, `ownerSubject` chỉ phù hợp khi **issuer đã cố định và subject mapping được quản lý rõ**. Nếu nhiều issuer hoặc subject có thể trùng, nên lưu **internalUserId** sau quá trình liên kết an toàn theo `(iss, sub)`, hoặc ràng buộc đủ issuer trong schema/query.

**Điểm bảo mật chính:** repository cung cấp method **có tenant trong điều kiện tìm kiếm**, thay vì `findById(id)` rồi quên hoặc kiểm tra muộn. Với tenant-scoped primary key/composite index, có thể còn thuận tiện hơn khi truy vấn luôn cần `(tenant_id, id)`.

### 8.1. Resource ID có đoán được hay không không thay đổi yêu cầu

Ngay cả khi order ID là UUID khó đoán, nó **không được coi là credential**. Nếu UUID của tenant khác bị lộ qua log, URL hay response liên kết, Resource Server vẫn phải chặn. **Không dùng “ID ngẫu nhiên” thay tenant authorization**.

### 8.2. Query danh sách và tìm kiếm phải lọc tenant

Endpoint list có thể dùng:

~~~java
orderRepository.findByTenantIdAndOwnerSubjectOrderByIdAsc(
    authorizedTenantId, subject);
~~~

Không dùng `findAll()` rồi lọc trong Java sau khi đã phân trang:

~~~text
SELECT tất cả tenant
  -> phân trang/sort toàn hệ thống
  -> filter tenant trên kết quả
~~~

Kiểu xử lý này có thể làm rò **count, thứ tự, pagination, aggregation** hoặc trả những trang trống khó hiểu. Tenant predicate nên xuất hiện **trong truy vấn DB hoặc trong một cơ chế row-level security đáng tin**, trước pagination và aggregation.

## 9. Service kiểm tra tenant path và tenant của tài nguyên

Ví dụ policy đơn giản: **một access token có `tenant_id` active duy nhất**, và user chỉ được đọc/hủy đơn của chính mình trong tenant đó.

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrdersService {

    private final OrderRepository orders;

    public OrdersService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderDto read(String requestedTenant,
                         String orderId, Jwt jwt) {

        String authorizedTenant =
                requireAuthorizedTenant(requestedTenant, jwt);

        OrderEntity entity = orders
            .findByIdAndTenantIdAndOwnerSubject(
                orderId, authorizedTenant, jwt.getSubject())
            .orElseThrow(OrdersService::notVisible);

        return new OrderDto(
            entity.getId(), entity.getTenantId(), entity.getStatus());
    }

    @Transactional
    public void cancel(String requestedTenant,
                       String orderId, Jwt jwt) {

        String authorizedTenant =
                requireAuthorizedTenant(requestedTenant, jwt);

        OrderEntity entity = orders
            .findByIdAndTenantIdAndOwnerSubject(
                orderId, authorizedTenant, jwt.getSubject())
            .orElseThrow(OrdersService::notVisible);

        if (!"OPEN".equals(entity.getStatus())) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT, "Order cannot be cancelled");
        }

        entity.cancel();
        // JPA dirty checking trong @Transactional sẽ lưu thay đổi.
    }

    private static String requireAuthorizedTenant(
            String requestedTenant, Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant_id");
        String subject = jwt.getSubject();

        if (tokenTenant == null || tokenTenant.isBlank()
                || subject == null || subject.isBlank()
                || !tokenTenant.equals(requestedTenant)) {
            throw notVisible();
        }
        return tokenTenant;
    }

    private static ResponseStatusException notVisible() {
        return new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Order not found");
    }
}

record OrderDto(String id, String tenantId, String status) {}
~~~

Điểm an toàn của code:

- `requireAuthorizedTenant` chỉ lấy `tenant_id` từ **`Jwt` đã được Resource Server xác minh**, không dùng path/header làm nguồn quyền.
- Nếu tenant trong path khác claim, không tiếp tục đọc tài nguyên.
- `findByIdAndTenantIdAndOwnerSubject` bảo đảm **ID tìm trong đúng tenant và owner**, nên dù path khớp token vẫn không đọc được order tenant khác.
- Với thao tác hủy, chỉ entity được truy vấn theo tenant/owner mới có thể được cập nhật.
- Trả 404 thống nhất cho resource không thuộc phạm vi caller theo **disclosure policy của ví dụ**.

**Giới hạn của ví dụ:** code dùng policy **owner-only** và một trusted issuer; chưa mô hình hóa assigned support, manager, đa issuer hoặc multi-membership. Không sửa bảo mật bằng cách cho mọi ROLE_ADMIN vượt qua tenant predicate nếu chưa có **system-level cross-tenant permission** riêng, được phê duyệt và audit.

### 9.1. Nghiệp vụ ghi cần chống race condition

Code đọc record rồi sửa dưới transaction có thể phù hợp với trường hợp đơn giản, nhưng nếu tenant membership, owner hoặc status có thể đổi đồng thời, thao tác quan trọng nên cân nhắc **atomic conditional update**:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = :orderId
  AND tenant_id = :authorizedTenant
  AND owner_subject = :authorizedSubject
  AND status = 'OPEN';
~~~

Kiểm tra **số hàng cập nhật**. Nếu bằng 0, không công bố bản ghi tồn tại ở tenant khác. Dữ liệu tenant và subject trong điều kiện phải đến từ **server-verified identity/policy**, không chỉ từ body.

### 9.2. Tránh exception/log tiết lộ tenant B

Sai:

~~~json
{
  "error": "You cannot read order-B100 because it belongs to tenant-B"
}
~~~

Nội dung này có thể làm lộ sự tồn tại và chủ sở hữu tenant của bản ghi. Response thông thường nên là thông báo chung:

~~~json
{
  "error": "Order not found"
}
~~~

Trong log nội bộ có kiểm soát, vẫn có thể ghi **loại vi phạm tenant** và correlation ID cho audit, nhưng không log nguyên Bearer token hoặc dữ liệu khách hàng của tenant khác.

## 10. Controller giữ ranh giới giữa request và principal

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
public class OrdersController {

    private final OrdersService orders;

    public OrdersController(OrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    public OrderDto read(
            @PathVariable String tenantId,
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        return orders.read(tenantId, orderId, jwt);
    }

    @PostMapping("/{orderId}/cancel")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void cancel(
            @PathVariable String tenantId,
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        orders.cancel(tenantId, orderId, jwt);
    }
}
~~~

**`@AuthenticationPrincipal Jwt` chỉ phù hợp khi chain đã xác thực JWT và principal vẫn là `Jwt`.** Nếu API dùng opaque token hoặc authentication converter đổi principal type, controller phải nhận loại principal phù hợp. Bài kiểm thử vẫn giữ cùng bất biến tenant, bất kể token format.

Trong Spring Security JWT Resource Server, `JwtAuthenticationToken.getPrincipal()` thường là `Jwt`. Không tự giải mã raw Authorization header trong controller để lấy `tenant_id`, vì việc giải mã Base64 không chứng minh chữ ký và audience.

## 11. Kiểm thử bằng MockMvc: token hợp lệ nhưng không đúng tenant

Spring Security Test có `SecurityMockMvcRequestPostProcessors.jwt()` để tạo một **JwtAuthenticationToken giả lập**. Nó cho phép thử **authorization theo tenant và resource** mà không cần dựng Authorization Server hoặc ký JWT cho mỗi test.

**Ranh giới rất quan trọng:** `jwt()` **không chứng minh chữ ký JWT đã được xác minh**, không kiểm tra issuer, audience, thời hạn hay JWKS. Unit/HTTP authorization tests với `jwt()` phải được bổ sung bằng **integration test dùng JWT ký thật qua JwtDecoder**.

### 11.1. Fixture phải có dữ liệu của ít nhất hai tenant

Ví dụ skeleton test dùng Spring Boot, MockMvc và JPA repository ở mục 8. Các entity được tạo riêng cho mỗi test; ứng dụng có thể dùng H2 test DB hoặc Testcontainers/PostgreSQL để khớp schema thật.

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class TenantIsolationHttpTest {

    @Autowired MockMvc mvc;
    @Autowired OrderRepository orders;

    @BeforeEach
    void seed() {
        orders.deleteAll();
        orders.save(new OrderEntity(
            "order-A100", "tenant-A", "alice", "OPEN"));
        orders.save(new OrderEntity(
            "order-A200", "tenant-A", "bob", "OPEN"));
        orders.save(new OrderEntity(
            "order-B100", "tenant-B", "carol", "OPEN"));
        orders.save(new OrderEntity(
            "order-B200", "tenant-B", "alice", "OPEN"));
    }

    private SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor
    token(String tenant, String subject, String... scopes) {
        return jwt()
            .jwt(builder -> builder
                .issuer("https://identity.example.test/realms/shop")
                .subject(subject)
                .audience(List.of("orders-api"))
                .claim("tenant_id", tenant)
                .claim("scope", String.join(" ", scopes)))
            .authorities(Arrays.stream(scopes)
                .map(s -> new SimpleGrantedAuthority("SCOPE_" + s))
                .toList());
    }

    @Test
    void aliceCanReadOwnOrderWithinTenantA() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A100")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("order-A100"))
            .andExpect(jsonPath("$.tenantId").value("tenant-A"));
    }

    @Test
    void rejectsRequestedTenantBDifferentFromTokenTenantA()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-B/orders/order-B100")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsForeignOrderEvenWhenPathMatchesTokenTenant()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-B100")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsSameSubjectFromDifferentTenant()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-B200")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsSameTenantButDifferentOwner() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A200")
                .with(token("tenant-A", "alice", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void deniesValidTokenWithoutReadScope() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A100")
                .with(token("tenant-A", "alice", "orders.cancel")))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsMissingToken() throws Exception {
        mvc.perform(get("/api/tenants/tenant-A/orders/order-A100"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void crossTenantCancelCannotMutateForeignOrder()
            throws Exception {
        mvc.perform(post(
                "/api/tenants/tenant-A/orders/order-B100/cancel")
                .with(token("tenant-A", "alice", "orders.cancel")))
            .andExpect(status().isNotFound());

        org.junit.jupiter.api.Assertions.assertEquals(
            "OPEN",
            orders.findById("order-B100").orElseThrow().getStatus());
    }
}
~~~

Mã trên là **fixture tích hợp Spring context** cho ví dụ controller/service/JPA ở các mục trước. Khi đưa vào dự án, phải bảo đảm test datasource được cô lập, schema được tạo phù hợp và Spring Security filters đang thực sự được bật. Nếu test có giao dịch bao ngoài khác với transaction service, kiểm tra lại cách quan sát trạng thái DB sau request.

**Những test quan trọng nhất là `rejectsForeignOrderEvenWhenPathMatchesTokenTenant` và `rejectsSameSubjectFromDifferentTenant`**: cả hai sẽ phát hiện những lỗi mà test chỉ so tenant path với JWT không thể phát hiện.

### 11.2. Vì sao cấp authorities tường minh trong test?

Helper:

~~~java
.authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))
~~~

làm rõ rằng **HTTP scope đã hợp lệ**. Nếu một test khác tenant trả 403 vì tình cờ **không có scope**, nó không chứng minh tenant policy. Cần giữ scope **đủ** ở cross-tenant negative tests để tầng tenant là nguyên nhân bị chặn.

Tương tự, một test thiếu token xác minh đường authentication 401, còn test thiếu scope xác minh HTTP authorization 403; **không được dùng hai test ấy để thay kiểm thử cross-tenant**.

### 11.3. Test resource có thật trong tenant khác

Không dùng ID `unknown-order` khi cần kiểm tra cross-tenant. Database phải chứa bản ghi đó trong **tenant B**, rồi token tenant A cố gọi. Sau request, có thể dùng repository dành cho **test setup/verification** kiểm tra bản ghi B vẫn tồn tại, còn API public **không được truy vấn theo ID không tenant guard**.

### 11.4. Test đọc và test ghi đều cần negative case

Một hệ thống có thể chặn GET đúng nhưng POST lại cập nhật:

~~~java
@PostMapping("/{orderId}/cancel")
void cancel(@PathVariable String orderId) {
    orderRepository.findById(orderId)
        .ifPresent(OrderEntity::cancel);
}
~~~

Đây là thiết kế **không an toàn** nếu code bỏ tenant/owner, kể cả khi GET endpoint đã xử lý đúng. Vì vậy **mỗi operation/method** phải có tenant-scoped authorization, đặc biệt với PATCH, DELETE, bulk update và trạng thái workflow.

## 12. Kiểm thử service/repository độc lập

HTTP test chứng minh kết quả từ filter chain đến controller; repository/service test giúp định vị nguyên nhân.

### 12.1. Repository không trả bản ghi khác tenant

Một integration test JPA có thể kiểm tra:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

// Phần thân test với OrderRepository đã seed dữ liệu.
@Test
void repositoryNeverFindsOrderInAnotherTenant() {
    assertTrue(orders
        .findByIdAndTenantIdAndOwnerSubject(
            "order-B100", "tenant-A", "carol")
        .isEmpty());
}
~~~

Điều này khác với kiểm tra query có trả null vì order ID không tồn tại: `order-B100` phải có thật trong tenant B.

### 12.2. Unit test service không gọi truy vấn thiếu tenant

Nếu sử dụng Mockito, có thể mock repository và xác nhận service **gọi đúng method đã có tenant predicate**:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

@Test
void wrongTenantCannotTriggerUnscopedLookup() {
    OrderRepository repo = mock(OrderRepository.class);
    OrdersService service = new OrdersService(repo);

    Jwt verifiedJwt = testJwt(
        "tenant-A", "alice"); // helper unit-test tạo Jwt object

    assertThrows(ResponseStatusException.class,
        () -> service.read("tenant-B", "order-B100", verifiedJwt));

    verifyNoInteractions(repo);
}
~~~

`testJwt(...)` là helper tạo `Jwt` giả cho unit test; tương tự `jwt()` của MockMvc, nó **không kiểm tra chữ ký**. Test này chứng minh service chặn path tenant khác **trước khi gọi repository**. Một test khác cần mock kết quả rỗng cho `findByIdAndTenantIdAndOwnerSubject` khi **path trùng tenant nhưng order ID thuộc tenant khác**, để xác nhận tầng resource cũng fail closed.

### 12.3. Test “không có side effect”

Khi POST cancel bị từ chối, ngoài HTTP status nên assert:

~~~text
Order B100 vẫn có status OPEN
Không có hàng dữ liệu nào bị update/delete
Không phát OrderCancelled event
Không tạo outbox event
Không gửi email / webhook
Không có entry audit sai nói rằng Alice đã cancel đơn B100
~~~

Nếu ứng dụng dùng transactional outbox, kiểm tra bảng outbox theo tenant. Nếu gọi message broker/HTTP downstream trước khi trả 403, negative test phải phát hiện side effect ấy. **Một status 403 cuối request không đủ** nếu hành động trái phép đã xảy ra trước đó.

## 13. Integration test JWT ký thật: phân biệt token hợp lệ và token giả

`jwt()` của Spring Security Test giả lập Authentication, nên không chứng minh token đã vượt qua cryptographic verification hay validators. Cần một nhóm integration tests khác:

1. Sinh cặp RSA/EC **chỉ cho test** hoặc dùng test JWKS server.
2. Cấu hình `JwtDecoder` thực tế trỏ tới **mock JWKS** và trusted issuer của môi trường test.
3. Ký JWT access token test với `iss`, `aud`, `scope`, `tenant_id`, `sub`, `exp` đúng profile.
4. Gửi chuỗi JWT thật qua `Authorization: Bearer ...`, **không dùng `jwt()`**.
5. Tạo resource trong tenant A và B; kiểm tra JWT ký đúng của tenant A **không thể truy cập B**.
6. Test token đổi một byte ở payload mà không ký lại → authentication phải thất bại.
7. Test issuer/audience/thời hạn sai → decoder phải từ chối **trước khi service được gọi**.

### 13.1. Ma trận hai trục: JWT hợp lệ và tenant authorization

| Token | Resource | Kỳ vọng |
| --- | --- | --- |
| JWT có chữ ký đúng, issuer/audience đúng, tenant A, scope đọc | Order A của caller | Được phép nếu policy dữ liệu đúng |
| **JWT hợp lệ**, tenant A, scope đọc | Order B | **Từ chối ở tenant/resource authorization** |
| JWT hợp lệ, tenant A, scope đọc | Order A của user khác | Từ chối theo owner/assignment |
| JWT hợp lệ nhưng thiếu `orders.read` | Order A | 403 ở scope authorization |
| JWT sai chữ ký, claims ghi tenant A | Order A | Authentication thất bại, không tới business policy |
| JWT ký đúng nhưng `aud=billing-api` | Order A | JWT validation từ chối |
| JWT hết hạn | Order A | Authentication thất bại |
| JWT issuer dev tại production | Order A | Authentication thất bại |

**Tình huống được yêu cầu trong bài là dòng thứ hai:** token **thật sự hợp lệ** nhưng tài nguyên **khác tenant**. Nếu chỉ test token giả/expired và thấy 401, chưa kiểm thử được lỗ hổng tenant isolation.

### 13.2. Không làm JWT “hợp lệ” bằng cách bypass decoder trong production

Đừng sửa validator:

~~~java
// SAI: Không dùng như giải pháp để test pass.
decoder.setJwtValidator(jwt ->
    OAuth2TokenValidatorResult.success());
~~~

Mục tiêu test là phân biệt xác thực token với tenant authorization, **không phải vô hiệu hóa authentication**. Chỉ dùng mock principal trong test lớp authorization, và test riêng pipeline ký/xác minh thật.

### 13.3. Opaque access token cũng phải chịu tenant policy

Nếu hệ thống dùng introspection:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "alice",
  "tenant_id": "tenant-A"
}
~~~

Resource Server cần kiểm tra active, audience và metadata contract; sau đó vẫn phải chặn Order B100. Unit test có thể mock `OpaqueTokenIntrospector` trả principal hợp lệ tenant A, integration test mock introspection endpoint HTTP thật và thử request khác tenant.

**Token format không giải quyết BOLA**. JWT và opaque token đều cần data policy.

## 14. Test khi URL không chứa tenant

Không phải API nào cũng có path `/tenants/{tenantId}`. Một endpoint có thể là:

~~~http
GET /api/orders/order-B100
Authorization: Bearer <token-tenant-A>
~~~

Khi đó API phải lấy **authorized tenant context** từ verified token hoặc membership policy, rồi truy vấn:

~~~sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :authorizedTenant;
~~~

Không có path tenant **không** có nghĩa bỏ kiểm tra tenant. Negative test vẫn dùng ID của resource tenant B và token tenant A.

### 14.1. Header selector

Một API có thể dùng:

~~~http
X-Tenant-Id: tenant-B
~~~

Header này chỉ là **yêu cầu chọn tenant**, không là quyền. Với token chỉ được cấp tenant A, API phải từ chối tenant B. Nếu token có quyền nhiều tenant, cần kiểm tra user đang là member active của tenant B hoặc token đã được phát cho tenant B theo profile.

### 14.2. Tenant từ subdomain

~~~text
tenant-a.shop.example.test
tenant-b.shop.example.test
~~~

Hostname cũng có thể là tenant selector, nhưng phải tính đến proxy, trusted Host headers, domain routing và authorization. Không dùng một Host header tùy ý do Client gửi làm bằng chứng quyền. Test request vào host tenant B với token A, kể cả khi route/framework phân tích host thành công.

## 15. Token nhiều tenant và user có membership ở nhiều tổ chức

Một biến thể:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_ids": ["tenant-A", "tenant-B"]
}
~~~

Danh sách này có thể mô tả membership tại thời điểm phát token, nhưng cần biết nó là **authorization grant thực sự** hay chỉ thông tin profile. Các quyết định thiết kế:

- User có thể chọn tenant B bằng URL/header không, hay phải đi qua luồng “switch tenant” để nhận token mới?
- Role `ORDER_ADMIN` ở tenant A có áp dụng tại tenant B không? **Thông thường không.**
- Membership có thể bị thu hồi trong lúc JWT chưa hết hạn không?
- Có cần kiểm tra memberships động trong database không?
- Có tenant-admin service hoặc automation được phép truy cập nhiều tenant có kiểm toán không?

**Không tự biến một danh sách tenant trong JWT thành quyền đọc mọi tài nguyên của tất cả tenant ấy.** Role/scope có thể tenant-scoped, và ngay trong tenant B user vẫn cần quyền trên order tương ứng.

### 15.1. Multi-tenant policy với active tenant

Một thiết kế dễ kiểm thử:

~~~text
Token có tenant_id = activeTenant đã được AS xác nhận.
Khi user chuyển tenant:
    AS/app xác minh membership
    -> phát token mới hoặc cập nhật server-side context đáng tin
Mỗi request:
    activeTenant phải match requested tenant
    resource.tenant_id phải match activeTenant
~~~

Thiết kế khác cho phép chọn tenant theo request rồi **tra cứu membership từng request**; khi đó scope và role phải được đánh giá **trong đúng tenant được chọn**. Dù chọn cách nào, test phải có **user thuộc A nhưng không thuộc B**, và **user thuộc cả A/B nhưng role khác nhau**, để phát hiện quyền “rò” giữa tenants.

### 15.2. Role admin không mặc định vượt tenant boundary

Một user:

~~~text
tenant-A -> ROLE_ORDER_ADMIN
tenant-B -> ROLE_VIEWER
~~~

nếu được chuyển thành global `ROLE_ORDER_ADMIN`, có nguy cơ xem/sửa dữ liệu tenant B. Test cần xác minh:

~~~text
Admin tại A + resource A -> allowed theo policy
Admin tại A + resource B -> denied nếu không có role B phù hợp
Viewer tại B + thao tác cancel B -> denied
~~~

Chỉ một vai trò **platform-wide** đã được thiết kế rõ, cấp theo quy trình nghiêm ngặt và audit mới được phép thực hiện một số thao tác cross-tenant. Đừng dùng global `ROLE_ADMIN` một cách vô thức.

## 16. Test dữ liệu trả về: không chỉ GET theo ID

Nhiều lỗi cross-tenant nằm ở những API “phụ”:

| Dạng endpoint | Nguy cơ | Negative test |
| --- | --- | --- |
| `GET /orders/{id}` | Đọc order B bằng token A | ID B có thật, không trả dữ liệu |
| `GET /orders` | List lẫn đơn B | Response chỉ có orders A |
| `GET /orders?search=...` | Search cross-tenant | Query với từ khóa chỉ có ở B không trả kết quả |
| `GET /orders/count` | Rò tổng số đơn toàn hệ thống | Count chỉ trong tenant được phép |
| `GET /reports/revenue` | Aggregate lẫn doanh thu B | Tổng và grouping chỉ trong tenant |
| `GET /orders/{id}/items` | Child resource không lọc tenant | Không trả items của order B |
| `GET /attachments/{id}` | File/attachment truy cập trực tiếp | Attachment của B bị từ chối |
| `GET /exports/{jobId}` | Export/download chứa dữ liệu B | Job/file ràng buộc tenant + owner |
| `POST /orders/bulk-cancel` | Một ID của B lẫn trong batch A | Không sửa B; policy all-or-nothing/partial rõ ràng |
| `PATCH /orders/{id}` | Mutation B dù read đã chặn | Không update row B |
| `DELETE /orders/{id}` | Xóa B bằng ID | Không delete row B |
| `POST /orders/{id}/refund` | Hệ quả tài chính | Không tạo refund/payment command B |

**Danh sách rỗng không đủ để khẳng định không có rò rỉ**. Cần kiểm tra cả `totalElements`, `totalPages`, sort/pagination, aggregate và response headers nếu chứa thông tin tổng hợp.

### 16.1. Bài test pagination dễ bỏ sót

Sai:

~~~text
SELECT all orders ORDER BY created_at LIMIT 20 OFFSET 0
  -> filter tenant A trong Java
~~~

Có thể trả 3 đơn A dù tenant A thật sự có 50 đơn, và pagination metadata lại tính trên tất cả tenants. Đúng hơn là:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :authorizedTenant
ORDER BY created_at
LIMIT :limit OFFSET :offset;
~~~

Test với dữ liệu A/B đan xen thứ tự tạo, page size nhỏ và nhiều trang, để phát hiện lỗi filter sau pagination.

### 16.2. Search và count

Cho tenant B có một order với từ khóa duy nhất `secret-B-keyword`, tenant A không có. Token A tìm từ khóa đó phải nhận **không có dữ liệu**, đồng thời không trả `totalHits=1` hoặc suggestion autocomplete chứa thông tin B.

### 16.3. Nested resources

`GET /api/orders/{orderId}/attachments/{attachmentId}` cần xác nhận:

~~~text
order.tenant_id == authorizedTenant
AND attachment.order_id == requestedOrderId
AND attachment.tenant_id == authorizedTenant (nếu có)
AND caller có quyền xem order/attachment
~~~

Không chỉ kiểm tra attachment ID và bỏ qua order/tenant binding. Tương tự với invoice, payment, shipping label hoặc customer profile.

## 17. Test mutation và side effects

Các thao tác ghi thường nguy hiểm hơn đọc dữ liệu vì chúng có hậu quả:

~~~text
POST /api/tenants/tenant-A/orders/order-B100/cancel
Bearer token hợp lệ tenant-A + orders.cancel
~~~

Kỳ vọng:

- Request bị từ chối theo tenant/resource.
- Order B100 vẫn ở `OPEN`.
- Không có `OrderCancelled` event cho B100.
- Không có outbox entry tenant B.
- Không gửi email, webhook hoặc yêu cầu refund.
- Không tạo audit record khẳng định một hành động nghiệp vụ đã thành công.

### 17.1. Bulk request

Một body:

~~~json
{
  "orderIds": ["order-A100", "order-B100"]
}
~~~

API phải có chính sách rõ:

- **All-or-nothing:** nếu có ID không thuộc tenant A thì cả batch bị từ chối, không update A/B.
- **Partial success:** chỉ xử lý những item có quyền và báo kết quả phù hợp, nhưng **không bao giờ sửa B** và không tiết lộ dữ liệu không cần thiết về B.

Test cả hai kiểu theo contract; không để service dùng `findAllById(ids)` rồi cập nhật tất cả.

### 17.2. Idempotency keys

Nếu dùng `Idempotency-Key`, cache của idempotency response phải ràng buộc **tenant + caller/request context**. Một key dùng ở tenant A không được trả lại response của tenant B. Test cùng idempotency key ở hai tenant và xác minh không cross-contaminate.

### 17.3. Async jobs, events và message consumers

Sau khi một request authorized tạo job, job async thường chạy **không có HTTP Bearer token trực tiếp**. Tenant context phải được truyền dưới dạng **dữ liệu nội bộ được kiểm soát**, gắn với job đã được cấp quyền; worker phải xác minh tenant trước khi đọc/ghi.

Test một export job thuộc tenant B không thể được lấy file bằng token tenant A, dù job ID bị biết. Tránh gán tenant từ header request ban đầu rồi giữ trong static/global biến không có request scope.

## 18. Cache, CDN, file storage và search index cũng cần tenant isolation

Một API có repository lọc tenant đúng nhưng cache sai vẫn có thể rò dữ liệu.

### 18.1. Cache key thiếu tenant

Sai về nguyên tắc:

~~~java
@Cacheable(cacheNames = "order", key = "#orderId")
public OrderDto read(String tenantId, String orderId) {
    // ...
}
~~~

Nếu một cache key chứa mỗi order ID và ID chỉ unique trong tenant hoặc response phụ thuộc quyền, hai tenants có thể nhận nhầm dữ liệu. Nên ràng buộc key theo **tenant, resource ID và các chiều authorization cần thiết**:

~~~java
@Cacheable(
    cacheNames = "order",
    key = "#tenantId + ':' + #orderId")
public OrderDto readTenantScoped(String tenantId, String orderId) {
    // tenantId đã được xác minh, không lấy tùy ý từ request.
    // ...
}
~~~

Nếu response còn phụ thuộc owner, role hoặc field-level entitlements, **chỉ tenant+order cũng có thể chưa đủ**. Cache phải phản ánh đúng phạm vi visibility và invalidation khi quyền thay đổi. Không đặt token raw làm cache key/log.

### 18.2. Cache poisoning và cache hit không được bỏ policy

Một sai lầm khác:

~~~text
if (cache contains orderId):
    return cachedOrder; // bỏ qua tenant authorization
else:
    validate tenant -> query DB
~~~

Policy phải áp dụng cả **cache hit** và **cache miss**. Test: gọi thành công Order B bằng token B để làm nóng cache, sau đó gọi cùng ID bằng token A; token A vẫn phải bị từ chối, không được dùng dữ liệu cached của B.

### 18.3. CDN/object storage

Nếu API trả link tới object storage hoặc signed URL, kiểm tra:

- Link chỉ được tạo sau tenant/object authorization.
- Object path/bucket/metadata không trộn tenants một cách không kiểm soát.
- Signed URL có thời hạn, scope và chủ thể sử dụng phù hợp risk model.
- Cache/CDN không phân phối response private của B cho A vì key thiếu Authorization/Vary hoặc policy.

Test download theo direct object URL, không chỉ test endpoint metadata.

### 18.4. Search index

Elasticsearch/OpenSearch hoặc một search service riêng phải nhận tenant filter từ **server-verified context**. Không dựa vào frontend luôn thêm `tenantId`; một Client có thể gửi truy vấn trực tiếp. Test từ khóa chỉ thuộc tenant B như mục 16.2.

## 19. Database row-level security như một lớp bổ sung

Một số hệ thống dùng **PostgreSQL Row-Level Security (RLS)** để bổ sung hàng rào trong DB. Ví dụ khái niệm:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation ON orders
USING (
  tenant_id =
  current_setting('app.current_tenant', true)
)
WITH CHECK (
  tenant_id =
  current_setting('app.current_tenant', true)
);
~~~

Đây là **minh họa cơ chế**, không phải cấu hình DB production đầy đủ. RLS cần kiểm soát role, ownership, table privileges, migrations, pooling và cách đưa tenant context vào transaction. Nếu dùng connection pool, phải **set tenant context an toàn theo transaction** và đảm bảo không rò state sang request kế tiếp; không nhận `app.current_tenant` từ Client không xác thực.

**RLS là defense in depth, không thay application authorization.** API vẫn phải kiểm tra scope, tenant membership, owner và hành vi business trước khi làm việc với dữ liệu.

### 19.1. Test RLS khi tenant setting thiếu

Kỳ vọng thiếu tenant context phải là **deny**, không phải “xem tất cả”. Test:

- Tenant A chỉ đọc hàng A.
- Tenant B chỉ đọc hàng B.
- Không set tenant → không đọc được hàng tenant khác.
- Transaction A rồi B dùng lại physical connection → context không bị sót.
- DB user của ứng dụng không có bypass quyền RLS ngoài chính sách.

Nếu ứng dụng đã có RLS, vẫn nên chạy HTTP cross-tenant tests để xác nhận **toàn bộ pipeline**.

## 20. WebFlux cũng cần cùng bộ negative tests

Với **Spring Security WebFlux**, token được xác minh qua `ReactiveJwtDecoder` và authorization qua `SecurityWebFilterChain`/`ServerHttpSecurity.authorizeExchange(...)`. Cơ chế không chặn không làm tenant isolation tự xuất hiện.

Ví dụ reactive repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

interface ReactiveOrderRepository
        extends ReactiveCrudRepository<ReactiveOrderEntity, String> {

    Mono<ReactiveOrderEntity> findByIdAndTenantIdAndOwnerSubject(
        String id, String tenantId, String ownerSubject);
}
~~~

Một service:

~~~java
Mono<OrderDto> read(String requestedTenant, String orderId, Jwt jwt) {
    String tokenTenant = jwt.getClaimAsString("tenant_id");
    if (tokenTenant == null || !tokenTenant.equals(requestedTenant)) {
        return Mono.error(new ResponseStatusException(
            HttpStatus.NOT_FOUND));
    }

    return reactiveOrders
        .findByIdAndTenantIdAndOwnerSubject(
            orderId, tokenTenant, jwt.getSubject())
        .map(order -> new OrderDto(
            order.getId(), order.getTenantId(), order.getStatus()))
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND)));
}
~~~

Đoạn WebFlux là **phần thân minh họa** của service với repository/entity tương ứng; không phải class standalone. Không dùng `.block()` để lấy order trong request event loop. **Không giữ tenant hiện tại trong static/ThreadLocal mutable global** giữa các Reactor subscriptions. Nếu cần context, dùng Reactor Context/`ReactiveSecurityContextHolder` hoặc tham số từ Authentication đã xác minh.

### 20.1. `WebTestClient` và `mockJwt()`

Spring Security Test cung cấp `mockJwt()` cho WebFlux:

~~~java
webTestClient.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claim("tenant_id", "tenant-A"))
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/tenants/tenant-A/orders/order-B100")
    .exchange()
    .expectStatus().isNotFound();
~~~

Test này hữu ích khi service có data fixture Order B100 thực sự thuộc tenant B. `mockJwt()` **giả lập Authentication**, không kiểm tra chữ ký/issuer/audience; cần integration test signed token qua `ReactiveJwtDecoder` riêng.

### 20.2. Test reactive repository và cache

Dùng **StepVerifier** với reactive service:

~~~java
StepVerifier.create(
        service.read("tenant-A", "order-B100", tenantAJwt))
    .expectError(ResponseStatusException.class)
    .verify();
~~~

`tenantAJwt` là test Jwt đã dựng, chưa phải bằng chứng decoder chấp nhận chữ ký. Bên cạnh đó, test `Mono.empty()` khi query không tìm được order theo tenant và test **không có mutation** khi pipeline bị từ chối. Đừng tự `subscribe()` vào repository rồi trả kết quả trước khi policy hoàn thành.

## 21. Test ma trận tenant đầy đủ

Một bảng có thể đưa vào kế hoạch test:

| Mã | Token | URL/đối tượng | Phân quyền | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| T01 | JWT hợp lệ tenant A, `orders.read` | A / Order A của caller | Đúng | 200 |
| T02 | **JWT hợp lệ tenant A**, `orders.read` | **B / Order B** | Sai tenant path | Deny, thường 404/403 |
| T03 | **JWT hợp lệ tenant A**, `orders.read` | **A / ID Order B** | Path đúng, resource sai tenant | Deny, không lộ B |
| T04 | JWT hợp lệ tenant A, `orders.read` | A / Order của Bob | Sai owner | Deny |
| T05 | JWT hợp lệ tenant A, `orders.cancel` | A / Order B | Sai tenant, write | Deny, không mutation/event |
| T06 | JWT hợp lệ tenant A, thiếu `orders.read` | A / Order A | Sai scope | 403 |
| T07 | Không token | A / Order A | Chưa xác thực | 401 điển hình |
| T08 | JWT sai chữ ký | A / Order A | Authentication fail | 401 điển hình |
| T09 | JWT `aud=billing-api` | A / Order A | Audience fail | 401 điển hình |
| T10 | JWT issuer dev | A / Order A | Issuer fail | 401 điển hình |
| T11 | JWT tenant claim thiếu/sai kiểu | A / Order A | Không đủ trusted tenant context | Deny |
| T12 | JWT tenant A, `ROLE_ADMIN` tenant A | B / Order B | Role cross-tenant không được phép | Deny |
| T13 | JWT tenant A, user cũng là member B | A / Order B | Token active tenant vẫn là A | Deny theo profile single-tenant |
| T14 | JWT tenant B được AS cấp hợp lệ, scope đúng | B / Order B user được phép | Đúng tenant/owner | Allowed |
| T15 | JWT tenant A | List/search/report có dữ liệu A+B | Filter tenant | Chỉ dữ liệu/count A |
| T16 | JWT tenant A | Attachment/export file thuộc B | Sai tenant gián tiếp | Không được download |
| T17 | JWT tenant A | Bulk IDs có A và B | Batch policy | Không mutate B |
| T18 | JWT tenant A | Order B đã nằm cache | Cache hit | Không lộ B |
| T19 | JWT tenant A, membership đã thu hồi | Order A | Dynamic membership policy | Deny theo hợp đồng thu hồi |
| T20 | Token service/client-credentials | Order tenant B | Service permission riêng | Deny trừ khi được cấp quyền rõ |

**Không phải test nào cũng bắt buộc có cùng một HTTP status.** Với resource bị che giấu có thể dùng 404; với thiếu scope thường là 403. Điều không được thay đổi là **không có dữ liệu/side effect ngoài quyền**.

### 21.1. Test nhiều dạng định danh

Nếu hệ thống cho phép:

- Order ID dạng UUID hoặc số tăng dần.
- Tenant ID dạng UUID, slug hoặc hostname.
- API nhận tenant trong URL, header hoặc claim.
- Multi-issuer subjects.

thì phải test chính **dạng định danh production**, bao gồm URL encoding/normalization, case sensitivity và mapping tenant slug → ID. Một so sánh chuỗi sai có thể biến hai tenant khác nhau thành cùng một giá trị sau normalization hoặc khiến policy bị bypass.

### 21.2. Test thay đổi tenant giữa hai request của cùng một user

Nếu Alice hợp lệ ở A và B, nhưng token đang ở A:

~~~text
Request 1: token tenant-A -> Order A -> allowed
Request 2: cùng token tenant-A -> Order B -> denied
User chuyển tenant qua luồng được phép
Request 3: token mới tenant-B -> Order B -> allowed nếu policy B đủ
~~~

Không dùng một biến static `currentTenant` để chuyển context giữa requests. Cache/session phải không trộn tenant active của hai phiên/user hoặc hai tab browser.

## 22. Quyền trên tenant thay đổi trong lúc token chưa hết hạn

JWT có thể còn hiệu lực 15 phút nhưng user đã bị xóa khỏi tenant. Nếu policy của Orders API yêu cầu **membership hiện tại**, chỉ đọc tenant claim từ JWT có thể chậm phản ánh thay đổi.

Các chiến lược có thể cân nhắc:

1. Access token sống ngắn và AS quản lý tenant claims đúng lúc cấp.
2. Opaque introspection phản ánh active/membership theo hợp đồng AS.
3. Tra cứu membership reactive/DB ở lớp authorization khi cần.
4. Cache membership có TTL ngắn và invalidation khi membership thay đổi.
5. Token/session revocation khi tài khoản bị khóa hoặc rời tổ chức.

Mỗi lựa chọn có đánh đổi giữa latency, availability và thời gian thu hồi. **Một token hợp lệ về thời hạn không tự chứng minh membership vẫn còn ở thời điểm thực thi nghiệp vụ**, nếu hợp đồng yêu cầu quyền động.

### 22.1. Kịch bản negative test với membership revoked

~~~text
T0: Alice thuộc tenant-A, token được phát
T1: Admin thu hồi membership của Alice tại A
T2: Alice dùng token còn hạn gọi Order A
~~~

Kết quả phụ thuộc policy thu hồi đã định. Nếu yêu cầu gần tức thời, authorization phải phát hiện membership đã revoked hoặc có cơ chế cache invalidation. Test phải xác nhận **không còn được thao tác** trong SLA đã cam kết, không chỉ dựa vào lúc JWT hết hạn.

### 22.2. Lỗi membership service không đồng nghĩa được phép

Nếu membership DB/remote service timeout, không được fallback:

~~~java
// SAI: Không làm điều này khi policy bắt buộc membership.
catch (Exception timeout) {
    return true;
}
~~~

Khi chưa có bằng chứng quyền đáng tin, phải **fail closed**. Status HTTP có thể phản ánh dependency failure theo contract, nhưng không được thực hiện thao tác.

## 23. Threat model: attacker dùng chính tài khoản hợp lệ

Các bài test khác tenant không giả định attacker có thể làm giả chữ ký JWT. Attacker có thể là:

- Nhân viên hợp lệ ở tenant A, cố đoán order ID của B.
- Client của tenant A sửa path `/tenant-B` hoặc `X-Tenant-Id`.
- User có membership ở A và B nhưng chỉ có vai trò đọc ở B, cố sử dụng quyền admin của A.
- Service account có token cho một tenant, gọi endpoint tài nguyên khác.
- Người dùng vô tình nhận link/order ID của tenant B từ email hoặc log rồi thử truy cập.

**Đây là lý do cross-tenant authorization phải được test với token có chữ ký đúng và scope đúng**. Một API chỉ chặn token giả không hề chứng minh nó chống được người dùng hợp lệ ở tenant khác.

### 23.1. Không coi CORS hoặc UI hiding là tenant isolation

Ẩn nút hủy trên frontend không chặn người gọi API trực tiếp. CORS không phải authentication/authorization; curl hoặc machine Client vẫn có thể gửi request. Tenant policy phải được thực thi **trên server và trên đường truy cập dữ liệu**, độc lập UI.

### 23.2. Không coi API gateway là lớp duy nhất

Gateway có thể kiểm tra token và đưa header tenant đã xác minh vào request nội bộ. Tuy nhiên backend phải có **trust boundary rõ**: chỉ tin header do gateway đáng tin ghi, chặn Client bypass gateway và loại bỏ header giả từ bên ngoài. Test direct-to-service và các đường internal invocation nếu chúng nằm trong threat model. **Một header `X-Tenant-Id` tùy ý không tự là credential bảo mật**.

## 24. Audit và quan sát khi phát hiện cross-tenant attempt

Những thông tin hữu ích:

~~~text
request_id
api_route
http_method
response_status
decision = DENY_TENANT_MISMATCH
trusted_issuer
trusted_subject_or_internal_user_id
authorized_tenant_id
requested_tenant_id (untrusted input, xử lý an toàn)
resource_type
policy_version
~~~

Chỉ ghi `resource.tenant_id` khi đã truy cập bằng một đường được phép để audit nội bộ và có lý do bảo mật phù hợp; không làm việc “fetch bản ghi tenant B trước rồi log mọi chi tiết” như một cách kiểm tra mặc định. Không ghi nguyên access token, Authorization header, private key, client secret hoặc dữ liệu nhạy cảm của tenant khác.

### 24.1. Đo chỉ số nhưng tránh metric cardinality

Không đưa raw `sub`, token hoặc hàng triệu order IDs vào metric labels. Có thể quan sát tổng số `tenant_mismatch`, `owner_denied`, `missing_scope` và `jwt_invalid` theo service/môi trường. Với audit cần định danh, dùng hệ thống log có phân quyền và retention phù hợp.

### 24.2. Phân biệt false positive và tấn công

Một cross-tenant request có thể do UI giữ nhầm tenant active sau khi chuyển tổ chức, không nhất thiết là tấn công. Nhưng **không vì thế nới rule authorization**. Sửa Client state và thông báo lỗi an toàn; tiếp tục deny request không đúng tenant.

## 25. Các sai lầm phổ biến mà bài kiểm thử phải bắt được

**“Token hợp lệ và có scope đọc là được xem mọi order.”** Sai; phải kiểm tra tenant và resource owner/assignment.

**“Đã so tenant URL với JWT, không cần lọc query theo tenant.”** Sai; ID order có thể thuộc tenant B dù URL ghi tenant A.

**“Một user có cùng `sub` ở A và B thì được dùng token A đọc B.”** Không; active tenant context và quyền B phải được chứng minh. Multi-issuer còn cần bảo vệ collision `(iss, sub)`.

**“Role ADMIN ở tenant A là admin toàn nền tảng.”** Không mặc định; role phải tenant-scoped trừ một quyền platform riêng được cấp rõ.

**“Trả 404 khi ID không tồn tại nghĩa là test cross-tenant đã pass.”** Không; phải dùng **ID có thật ở tenant B**.

**“Token giả không truy cập được B, vậy tenant isolation ổn.”** Không; JWT giả bị decoder chặn trước khi tenant policy chạy.

**“Có thể lấy tenantId từ header do frontend gửi.”** Không làm nguồn quyền; header/path chỉ là selector và phải được đối chiếu với context đáng tin.

**“Repository findById rồi kiểm tra tenant trước khi trả JSON là luôn đủ.”** Dễ bỏ sót, có thể tạo side effects, cache data sai hoặc tiết lộ chi tiết. Ưu tiên tenant predicate ngay trong query và policy trước mutation.

**“Chỉ GET cần tenant check; POST/DELETE đã có scope write.”** Sai; mutation khác tenant có thể gây thiệt hại lớn hơn leak.

**“Một status 403 chứng minh không có thay đổi DB.”** Không; phải assert trạng thái DB/outbox/event không đổi.

**“Cache theo orderId là đủ.”** Không nếu ID hoặc response phụ thuộc tenant/owner; cache hit phải chịu tenant policy.

**“JWT còn hạn thì membership tenant không thể thay đổi.”** Sai; cần policy freshness/revocation phù hợp.

**“Nếu DB lookup tenant thất bại thì cho qua để tránh downtime.”** Fail open và nguy hiểm.

**“`jwt()` trong MockMvc chứng minh signature/audience đúng.”** Không; cần signed-JWT integration test riêng.

**“CORS đã khóa origin nên tenant khác không gọi API được.”** CORS không thay access control phía server.

**“Frontend giấu order ID thì không ai biết.”** Không; UUID/ID có thể lộ qua link/log; object-level authorization vẫn bắt buộc.

**“Row Level Security trong DB có nghĩa không cần Spring Security.”** Không; JWT validation, scopes, business entitlements và RLS bổ sung nhau.

## 26. Checklist bàn giao và tiêu chí đạt

Một test suite tenant isolation nên chứng minh:

1. **JWT/opaque token được xác minh đúng** (issuer, audience, thời hạn, active/profile) trong integration test.
2. Token tenant A **đủ scope** và có Authentication hợp lệ, nhưng Order B vẫn bị từ chối.
3. Có test **tenant path B khác tenant claim A**.
4. Có test **tenant path A đúng claim A, nhưng order ID thực thuộc B**.
5. Có test **cùng tenant nhưng sai owner/assignment**.
6. Có test **cùng subject ở tenant khác** và, nếu đa issuer, cùng subject ở issuer khác.
7. Query cho GET, list, search, count và aggregation **lọc tenant trước pagination**.
8. POST/PATCH/DELETE/bulk operations **không cập nhật tenant khác**.
9. Không có **event, outbox, webhook, export/download** của tenant khác khi bị deny.
10. Cache hit, CDN/object storage/search index không làm lộ tenant khác.
11. Role, permission và memberships được gắn **đúng tenant**, không dùng global admin vô tình.
12. Tenant selector trong path/header/host được đối chiếu **với trusted principal/membership**.
13. 401 cho authentication failure được phân biệt với 403/404 cho authorization denial.
14. Lỗi dependency hay thiếu membership cần thiết dẫn tới **fail closed**.
15. API response/log không tiết lộ token, data hoặc tồn tại tài nguyên thuộc tenant khác ngoài policy.
16. Unit tests dùng mock Authentication được bổ sung bằng **signed-token hoặc introspection HTTP integration tests**.

**Tiêu chí đạt không chỉ là “status không phải 200”.** Đó là: **không có unauthorized data disclosure, không có unauthorized mutation, và không có chứng cứ quyền tenant được suy ra từ đầu vào không đáng tin**.

## 27. Bài tập tình huống

**Tình huống A:** JWT của Alice đã xác minh thành công, có `SCOPE_orders.read`, `tenant_id=tenant-A`. Alice gọi `GET /api/tenants/tenant-B/orders/order-B100`. Nên xử lý thế nào?

**Từ chối ở tenant authorization.** Không cần coi JWT sai chữ ký. Chọn 403 hoặc 404 theo policy disclosure; không trả dữ liệu Order B100.

**Tình huống B:** Developer kiểm tra tenant path đúng JWT, rồi gọi `findById(orderId)`. Với URL tenant-A nhưng `order-B100` thuộc B, test path-mismatch có đủ không?

**Không.** Cần test **path khớp token nhưng resource ID thuộc tenant B**. Phải lọc record theo tenant tại repository/policy.

**Tình huống C:** Order B200 có ownerSubject `alice`, token Alice là tenant A. Query chỉ lọc `owner_subject=alice`, thiếu tenant. Rủi ro?

Alice có thể đọc đơn tenant B. Cần ràng buộc **tenant và owner cùng lúc**, không coi subject toàn cục là quyền trên mọi tổ chức.

**Tình huống D:** Token tenant A có `orders.cancel`, POST hủy Order B trả 404 nhưng database chuyển trạng thái B thành CANCELLED. Test đạt không?

**Không.** Dù HTTP status là 404, side effect vẫn trái phép. Test phải assert DB/outbox/event không thay đổi.

**Tình huống E:** Token A và scope đúng, API list chỉ trả orders A nhưng `totalElements` đếm cả A+B. Có đạt tenant isolation không?

**Không.** Metadata pagination đã làm lộ dữ liệu tổng hợp và có thể suy ra hoạt động tenant khác. Filter tenant phải áp dụng trước count/page.

**Tình huống F:** Alice là admin tenant A, reader tenant B. Token/role mapping tạo một `ROLE_ADMIN` global. Có được hủy đơn B không?

**Không mặc định.** Admin quyền A không lan sang B. Cần role/membership gắn tenant và test quyền ở từng tenant.

**Tình huống G:** Unit test dùng `jwt()` với tenant A và thấy 404 khi đọc order B. Có thể kết luận JwtDecoder đã validate chữ ký/audience không?

**Không.** `jwt()` giả lập Authentication. Cần integration test gửi JWT ký thật qua decoder và trường hợp issuer/audience/signature sai.

**Tình huống H:** Hai tenants dùng cùng một ID order cục bộ `42`. Cache chỉ có key `42` và trả Order B đã cache cho tenant A. Đây là lỗi ở đâu?

**Cache isolation.** Key và policy phải có tenant context được xác minh; cache hit không được bỏ kiểm tra quyền.

**Tình huống I:** User rời tenant A nhưng JWT `exp` còn 20 phút. Hệ thống yêu cầu thu hồi membership trong 1 phút. Chỉ xác minh `exp` có đủ không?

**Không.** Cần validation membership cập nhật hoặc cơ chế thu hồi/cache invalidation đáp ứng SLA đã cam kết.

**Tình huống J:** Một request có `X-Tenant-Id: tenant-B`, trong khi token hợp lệ chỉ cho tenant A. Backend dùng header đó trực tiếp trong SQL. Điều gì sai?

Header là dữ liệu caller tự gửi; backend đã dùng **tenant selector như bằng chứng quyền**. Phải so nó với trusted tenant context/active membership trước khi truy vấn.

---

## Kết luận

**Kiểm thử token hợp lệ nhưng thuộc tenant khác** là bài kiểm tra **authorization isolation**, không phải chỉ là kiểm thử chữ ký JWT hoặc status 401. Một Bearer access token có thể **đúng issuer, audience, thời hạn và scope** nhưng vẫn **không có quyền** đọc hay thay đổi tài nguyên thuộc tenant khác. Do đó Spring Security route rules như `hasAuthority("SCOPE_orders.read")` mới là **lớp đầu**; backend còn phải ràng buộc **trusted tenant context, owner/role/membership và tenant thực tế của bản ghi**.

Hai negative tests bắt buộc là: **(1) token tenant A, URL tenant B** và **(2) token tenant A, URL tenant A nhưng resource ID thực thuộc tenant B**. Test thứ hai đặc biệt quan trọng để phát hiện lỗi query `findById` không lọc tenant. Đối với ghi dữ liệu, phải xác minh **không có mutation/event/outbox** khi bị deny; với list/search/cache/export phải chứng minh không rò dữ liệu hoặc metadata tenant khác. Dùng `jwt()`/`mockJwt()` để cô lập business authorization, nhưng bổ sung **signed JWT/integration introspection tests** để bảo đảm authentication thật. **Token hợp lệ chỉ là điểm khởi đầu; quyền đối với đúng tenant và đúng tài nguyên mới quyết định request được thực hiện hay không.**
