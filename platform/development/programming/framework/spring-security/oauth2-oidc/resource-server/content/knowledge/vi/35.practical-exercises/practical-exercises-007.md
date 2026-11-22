# Hỗ trợ hai issuer được phê duyệt và kiểm tra cách ly dữ liệu

Một Resource Server có thể cần chấp nhận access token JWT từ hai Authorization Server (issuer) độc lập. Ví dụ, một API phục vụ cả hệ thống nhân viên nội bộ và khách hàng doanh nghiệp, mỗi nhóm có identity provider riêng. Spring Security có thể chọn decoder/authentication manager theo claim `iss` của JWT, nhưng việc hỗ trợ nhiều issuer phải đi kèm allowlist, validation policy riêng và cách ly dữ liệu theo đúng trust domain.

Điểm cần giữ rõ là **issuer được phép xác thực token không đồng nghĩa mọi principal từ issuer đó được phép đọc dữ liệu của issuer khác**. Hai issuer có thể cùng phát hành subject `alice`, cùng có role `ADMIN` hoặc cùng dùng `kid` giống nhau. Những giá trị đó không có ý nghĩa toàn cục. Danh tính cần được định danh tối thiểu bằng cặp `(issuer, subject)`, còn tenant/data partition phải được xác định từ một mapping tin cậy.

Bài học này xây dựng một Resource Server chấp nhận đúng hai issuer đã phê duyệt, dùng JWKS riêng cho từng issuer, kiểm tra issuer/audience/time/signature, tách authority mapping, ràng buộc tenant context và kiểm thử các tình huống cross-issuer/cross-tenant.

## 1. Bài toán multi-issuer

Giả sử một Orders API cần phục vụ hai nhóm:

| Thuộc tính | Issuer A: Workforce | Issuer B: Partner |
|---|---|---|
| Issuer URI | `https://login.corp.example` | `https://identity.partner.example` |
| JWKS URI | `https://login.corp.example/oauth2/jwks` | `https://identity.partner.example/keys` |
| Audience | `workforce-orders-api` | `partner-orders-api` |
| Tenant mapping | `internal` | `partner` |
| Scope đọc đơn hàng | `orders.read` | `partner.orders.read` |
| Subject namespace | Do issuer A quản lý | Do issuer B quản lý |

Cả hai issuer đều có thể phát hành JWT hợp lệ, nhưng token phải được xác minh bằng key set và policy tương ứng với issuer đã phát hành nó.

~~~text
                       Orders Resource Server
                                  |
                     Read untrusted JWT iss
                                  |
                    +-------------+-------------+
                    |                           |
             exact issuer A              exact issuer B
                    |                           |
                    v                           v
              Decoder A                    Decoder B
              JWKS A                       JWKS B
              Audience A                   Audience B
              Authorities A                Authorities B
                    |                           |
                    +-------------+-------------+
                                  |
                         Authenticated principal
                                  |
                       Trusted issuer-to-tenant
                              mapping
                                  |
                          Tenant-scoped service
                                  |
                    Repository query with tenant_id
~~~

### 1.1. Hai issuer là hai trust domain

Mỗi issuer có:

- Signing keys và JWKS riêng.
- Issuer identifier riêng.
- Audience/resource identifiers riêng.
- Token issuance policy và claim conventions riêng.
- Subject namespace riêng.
- Quy trình rotation, incident response và availability riêng.

Không giả định hai issuer dùng chung key, `kid`, `sub`, scope hoặc role semantics. Ngay cả khi chúng cùng dùng OpenID Connect, token profile và claim mapping vẫn có thể khác nhau.

### 1.2. Authentication và data authorization là hai lớp

Authentication trả lời: token này có được ký bởi một issuer được tin cậy, còn hạn và dành cho API này không?

Data authorization trả lời: principal đã xác thực có được phép truy cập record thuộc tenant/organization/resource cụ thể không?

Một token từ issuer A được xác thực thành công không có nghĩa principal có thể truy cập record của issuer B. Phải giữ tenant boundary ở service/repository layer, kể cả khi controller đã được bảo vệ bằng scope.

## 2. Trust model: allowlist issuer trước khi tạo decoder

Claim `iss` nằm trong JWT payload và có thể được đọc trước khi xác minh chữ ký. Vì vậy, nó có thể được dùng làm **selector** để chọn một authentication manager đã được provision, nhưng không thể được coi là bằng chứng tin cậy cho tới khi decoder xác minh chữ ký và issuer claim.

Quy trình an toàn:

1. Đọc issuer string từ token như dữ liệu chưa xác thực.
2. Tra cứu exact string trong allowlist/registry do hệ thống quản trị.
3. Nếu không có issuer tương ứng, từ chối token và không gọi network.
4. Chọn decoder/authentication manager gắn với issuer đó.
5. Xác minh chữ ký bằng JWKS tin cậy của issuer.
6. Validate `iss`, `aud`, `exp`, `nbf`, algorithm và token profile.
7. Tạo Authentication và ánh xạ tenant theo cấu hình tin cậy.

~~~text
JWT arrives
   |
   v
Read unverified iss (routing hint only)
   |
   v
Exact lookup in approved issuer registry
   |
   +-- not found --> reject; no discovery/network fetch
   |
   v
Select issuer-specific AuthenticationManager
   |
   v
Verify signature using issuer's configured JWKS
   |
   v
Validate issuer, audience, time, algorithm, token type
   |
   v
Authenticated principal
~~~

### 2.1. Không tự động tin issuer URL trong token

Một cách triển khai nguy hiểm là đọc `iss` rồi tạo decoder bằng URL đó:

~~~java
// Không làm như vậy:
String issuer = readUnverifiedIssuer(token);
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

Attacker có thể gửi JWT với `iss` trỏ tới server do họ kiểm soát. Resource Server có thể bị dụ gọi metadata/JWKS URL bên ngoài, tạo SSRF, truy cập endpoint nội bộ hoặc tin key do attacker cung cấp.

Chỉ tạo decoder cho issuer đã được đăng ký và phê duyệt. Không cho token, request header, query parameter hoặc tenant name tùy ý điều khiển JWKS URL.

### 2.2. So sánh issuer bằng exact identifier

Issuer URI là identifier, không phải URL để tùy ý chuẩn hóa. Tránh các thao tác như:

- Bỏ path hoặc query rồi so sánh hostname.
- Chấp nhận mọi subdomain của một domain.
- Chuyển HTTP sang HTTPS ngầm.
- Bỏ trailing path segment để “gần giống”.
- So sánh theo prefix.

Ví dụ `https://login.example/tenant-a` và `https://login.example/tenant-b` có thể là hai issuer khác nhau. Dùng đúng issuer string được provision và metadata của issuer công bố.

### 2.3. Allowlist phải được quản trị như cấu hình bảo mật

Registry issuer nên được quản lý qua deployment configuration hoặc control plane có quyền hạn rõ ràng. Khi thêm issuer, cần phê duyệt issuer URI, JWKS URI, audience, tenant mapping và claim policy. Không tự động thêm issuer mới chỉ vì có request mang `iss` lạ.

## 3. Cấu hình hai issuer trong Spring Security Servlet

Spring Security cung cấp `JwtIssuerAuthenticationManagerResolver` để chọn `AuthenticationManager` theo issuer trong JWT. Với danh sách issuer cố định, factory `fromTrustedIssuers` là lựa chọn ngắn gọn.

### 3.1. Cấu hình issuer được tin cậy

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

import jakarta.servlet.http.HttpServletRequest;

@Configuration
class MultiIssuerSecurityConfiguration {

    static final String WORKFORCE_ISSUER =
        "https://login.corp.example";
    static final String PARTNER_ISSUER =
        "https://identity.partner.example";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
    authenticationManagerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            WORKFORCE_ISSUER,
            PARTNER_ISSUER
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

Resolver chỉ chấp nhận hai issuer trong danh sách. Mỗi issuer được dùng để xây dựng authentication manager và decoder tương ứng. API không cần nhận private key; mỗi decoder lấy public key từ JWKS endpoint của issuer.

### 3.2. Khi nào cần custom resolver?

`fromTrustedIssuers` phù hợp khi hai issuer có policy validation tương tự và cần issuer validation mặc định. Trong thực tế, issuer A và B có thể có audience khác nhau, thuật toán khác nhau hoặc claim/authority mapping riêng. Khi đó, tạo một `AuthenticationManager` cho mỗi issuer rồi chọn từ một map cố định.

### 3.3. AuthenticationManager riêng cho từng issuer

Ví dụ sau tạo decoder với JWKS URI, thuật toán và audience riêng:

~~~java
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

import jakarta.servlet.http.HttpServletRequest;

@Configuration
class IssuerSpecificManagers {

    static final String ISSUER_A = "https://login.corp.example";
    static final String ISSUER_B = "https://identity.partner.example";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> issuerResolver() {
        Map<String, AuthenticationManager> managers = Map.of(
            ISSUER_A, manager(
                ISSUER_A,
                "https://login.corp.example/oauth2/jwks",
                "workforce-orders-api"),
            ISSUER_B, manager(
                ISSUER_B,
                "https://identity.partner.example/keys",
                "partner-orders-api")
        );

        AuthenticationManagerResolver<String> trustedLookup =
            managers::get;

        return new JwtIssuerAuthenticationManagerResolver(trustedLookup);
    }

    private AuthenticationManager manager(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience is not accepted by this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audienceValidator));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        provider.setJwtAuthenticationConverter(
            new JwtAuthenticationConverter());

        return provider::authenticate;
    }
}
~~~

`JwtIssuerAuthenticationManagerResolver` dùng issuer string để tra cứu manager. `managers::get` chỉ trả về manager khi issuer trùng chính xác một key đã đăng ký; issuer khác nhận `null` và bị từ chối. Không thay map này bằng logic tạo decoder từ URL tùy ý.

Mẫu trên dùng RS256 cho cả hai issuer để minh họa. Nếu issuer có thuật toán khác, cấu hình allowlist riêng cho manager đó. Audience validator cũng riêng theo issuer; token A có audience B không được chấp nhận chỉ vì chữ ký đúng.

### 3.4. Authority converter riêng theo issuer

Hai issuer có thể dùng claim scope khác nhau. Nếu issuer A dùng `scope` dạng chuỗi phân tách khoảng trắng còn issuer B dùng `permissions` dạng array, đừng ép một converter chung diễn giải cả hai theo cùng quy ước.

Có thể cấu hình converter riêng trên mỗi `JwtAuthenticationProvider` trước khi đưa provider vào map. Với default converter, Spring Security thường map `scope`/`scp` thành authority có prefix `SCOPE_`. Với custom claim, viết converter rõ ràng và test mapping positive/negative.

Không ánh xạ một claim `roles=["ADMIN"]` của issuer B thành quyền admin nội bộ chỉ vì tên role giống nhau. Authority namespace nên thể hiện trust domain, ví dụ `WORKFORCE_ADMIN` và `PARTNER_ORDER_READER`, hoặc map qua policy service đã được kiểm soát.

## 4. Cấu hình hai issuer trong Spring Security WebFlux

WebFlux có `JwtIssuerReactiveAuthenticationManagerResolver` và reactive authentication managers. Không dùng Servlet resolver hoặc blocking decoder trong reactive filter chain.

### 4.1. Danh sách issuer được tin cậy

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

@Configuration
class MultiIssuerReactiveSecurityConfiguration {

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange>
    reactiveIssuerResolver() {
        return JwtIssuerReactiveAuthenticationManagerResolver
            .fromTrustedIssuers(
                "https://login.corp.example",
                "https://identity.partner.example"
            );
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

### 4.2. Reactive manager riêng cho mỗi issuer

Khi audience hoặc decoder configuration khác nhau, có thể dựng map issuer sang `ReactiveAuthenticationManager`:

~~~java
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration
class IssuerSpecificReactiveManagers {

    private static final String ISSUER_A = "https://login.corp.example";
    private static final String ISSUER_B = "https://identity.partner.example";

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver() {
        Map<String, ReactiveAuthenticationManager> managers = Map.of(
            ISSUER_A, manager(
                ISSUER_A,
                "https://login.corp.example/oauth2/jwks",
                "workforce-orders-api"),
            ISSUER_B, manager(
                ISSUER_B,
                "https://identity.partner.example/keys",
                "partner-orders-api")
        );

        ReactiveAuthenticationManagerResolver<String> trustedLookup =
            issuer -> Mono.justOrEmpty(managers.get(issuer));

        return new JwtIssuerReactiveAuthenticationManagerResolver(
            trustedLookup);
    }

    private ReactiveAuthenticationManager manager(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience is not accepted by this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return new JwtReactiveAuthenticationManager(decoder);
    }
}
~~~

Resolver chỉ tra cứu trong map issuer đã được cấu hình. Reactive decoder thực hiện JWKS retrieval qua reactive infrastructure. Nếu cần authority converter riêng, cấu hình trên từng `JwtReactiveAuthenticationManager`; không block để gọi Servlet converter hoặc network client đồng bộ trên event-loop.

### 4.3. Version compatibility

Tên package và overload của resolver có thể thay đổi theo Spring Security major/minor version. Dùng API của version dự án đang chạy và kiểm tra Javadoc tương ứng. Các nguyên tắc không thay đổi: issuer phải được allowlist, manager phải gắn với issuer cụ thể và decoder phải xác minh issuer/audience/key policy.

## 5. Ánh xạ issuer sang tenant identity

Sau khi decoder xác thực token, ứng dụng cần tạo tenant context từ dữ liệu đã xác thực và cấu hình tin cậy. Với ví dụ hai issuer tương ứng hai tenant partition:

~~~java
import java.util.Map;

import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

record TenantIdentity(
    String issuer,
    String subject,
    String tenantId
) {}

@Component
class TenantIdentityResolver {

    private static final Map<String, String> TENANT_BY_ISSUER = Map.of(
        "https://login.corp.example", "internal",
        "https://identity.partner.example", "partner"
    );

    TenantIdentity resolve(JwtAuthenticationToken authentication) {
        Jwt jwt = authentication.getToken();
        String issuer = jwt.getClaimAsString("iss");
        String tenantId = TENANT_BY_ISSUER.get(issuer);

        if (tenantId == null) {
            throw new IllegalStateException(
                "Authenticated issuer has no tenant mapping");
        }

        String subject = jwt.getSubject();
        if (subject == null || subject.isBlank()) {
            throw new IllegalStateException(
                "Authenticated token has no subject");
        }

        return new TenantIdentity(issuer, subject, tenantId);
    }
}
~~~

Đây là mapping cố định theo issuer. Vì decoder đã validate issuer claim, ứng dụng có thể dùng claim đó để tra cứu tenant. Không lấy tenant ID từ X-Tenant-ID, query parameter hoặc request body rồi coi đó là tenant identity.

### 5.1. Subject phải đi cùng issuer

Hai issuer có thể cùng cấp sub=alice. Đây là hai identity khác nhau:

~~~text
("https://login.corp.example", "alice")
    -> internal user 1042

("https://identity.partner.example", "alice")
    -> partner user 8891
~~~

Nếu database có bảng user identity, dùng composite key hoặc unique constraint trên (issuer, subject). Không dùng sub đơn lẻ làm global user ID.

Ví dụ schema:

~~~sql
CREATE TABLE external_identity (
    id BIGINT PRIMARY KEY,
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    local_user_id BIGINT NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

Issuer phải được lưu theo identifier chính xác đã được xác thực. Giới hạn độ dài cột và input trước khi persist để tránh dữ liệu bất thường.

### 5.2. Nếu một issuer đại diện nhiều tenant

Không thể luôn map một issuer sang đúng một tenant. Ví dụ issuer B có thể phát hành token cho nhiều partner organizations. Khi đó, token có thể chứa tenant_id hoặc organization claim do issuer ký.

Claim tenant vẫn cần được kiểm tra theo policy:

- Issuer B có được phép phát hành token cho tenant đó không?
- Subject/client có membership trong tenant không?
- Tenant có đang active và được phép dùng API không?
- Audience của token có đúng resource không?
- Có cần kiểm tra tenant claim với registry nội bộ không?

Nếu request có X-Tenant-ID, có thể dùng header như selector để chọn một tenant trong tập membership đã xác minh của principal. Header không được mở rộng tập tenant mà principal có quyền truy cập.

### 5.3. Không tin tenant claim chỉ vì JWT có chữ ký

Chữ ký chứng minh issuer đã phát hành claim. Nó không chứng minh ứng dụng hiểu đúng semantics của claim. Cần thống nhất với issuer về claim name, kiểu dữ liệu, namespace, thời điểm cập nhật membership và cách xử lý user thuộc nhiều organizations.

Không cho issuer A cấp tenant ID thuộc namespace chỉ dành cho issuer B trừ khi có mapping/ủy quyền được thiết kế rõ ràng.

## 6. Enforce tenant boundary tại service và repository

Authentication ở filter chain chỉ là điểm đầu. Mỗi truy vấn dữ liệu phải được ràng buộc với tenant identity đã xác thực.

### 6.1. Luôn đưa tenant ID vào repository query

Ví dụ với Spring Data repository:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;

interface OrderRepository extends Repository<OrderEntity, Long> {

    List<OrderEntity> findAllByTenantId(String tenantId);

    Optional<OrderEntity> findByIdAndTenantId(
        Long id,
        String tenantId);
}
~~~

Service dùng tenant identity đã resolve:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TenantOrdersService {

    private final OrderRepository repository;

    TenantOrdersService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    List<OrderEntity> list(TenantIdentity identity) {
        return repository.findAllByTenantId(identity.tenantId());
    }

    @Transactional(readOnly = true)
    Optional<OrderEntity> get(Long orderId, TenantIdentity identity) {
        return repository.findByIdAndTenantId(
            orderId,
            identity.tenantId());
    }
}
~~~

Không làm theo kiểu lấy order theo ID trước rồi chỉ kiểm tra tenant ở controller sau khi trả entity. Query phải giới hạn tenant ngay từ data access boundary.

### 6.2. Controller không nhận tenant identity do client tự khai

Ví dụ:

~~~java
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    private final TenantIdentityResolver tenantResolver;
    private final TenantOrdersService orders;

    OrdersController(
            TenantIdentityResolver tenantResolver,
            TenantOrdersService orders) {
        this.tenantResolver = tenantResolver;
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    List<OrderEntity> list(JwtAuthenticationToken authentication) {
        TenantIdentity identity = tenantResolver.resolve(authentication);
        return orders.list(identity);
    }

    @GetMapping("/api/orders/{id}")
    ResponseEntity<OrderEntity> get(
            @PathVariable Long id,
            JwtAuthenticationToken authentication) {
        TenantIdentity identity = tenantResolver.resolve(authentication);
        return orders.get(id, identity)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Trong Spring MVC, controller có thể nhận JwtAuthenticationToken qua method argument resolver hoặc lấy principal từ Authentication. Nếu dùng @AuthenticationPrincipal Jwt, có thể chuyển trực tiếp JWT đã xác thực sang resolver. Không cần nhận một tenant ID khác từ client để quyết định data scope.

### 6.3. Bảo vệ cả update và delete

Tenant filter cần có trong mọi thao tác:

~~~sql
UPDATE orders
SET status = :new_status
WHERE id = :order_id
  AND tenant_id = :authenticated_tenant_id;
~~~

~~~sql
DELETE FROM orders
WHERE id = :order_id
  AND tenant_id = :authenticated_tenant_id;
~~~

Nếu update/delete không kiểm tra tenant, attacker có thể truy cập record khác bằng cách thay ID dù GET list đã được cách ly.

### 6.4. Tenant isolation ở database

Với PostgreSQL, Row-Level Security (RLS) có thể là lớp phòng vệ bổ sung. Ví dụ policy:

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

Application phải đặt app.tenant_id trong đúng transaction/connection trước khi query. Dùng transaction-local setting (ví dụ SET LOCAL) để context không rò qua connection pool sang request khác. Tài khoản database của ứng dụng không nên là superuser hoặc role có quyền bypass RLS.

RLS không thay thế authorization ở application; nó là defense-in-depth. Test cả read, insert, update và delete, bao gồm connection reuse và rollback.

## 7. Cách ly authority và policy giữa hai issuer

Scope và role names từ hai issuer không mặc nhiên tương đương. Nếu cả hai phát hành ADMIN, một converter chung có thể vô tình cấp quyền quản trị nội bộ cho partner user.

### 7.1. Namespace authority theo issuer

Ví dụ mapping policy:

| Issuer | Claim từ token | Authority nội bộ |
|---|---|---|
| Workforce | scope=orders.read | WORKFORCE_ORDERS_READ |
| Workforce | roles=[ADMIN] | WORKFORCE_ADMIN |
| Partner | permissions=[orders:view] | PARTNER_ORDERS_READ |
| Partner | roles=[ADMIN] | PARTNER_ADMIN |

Policy endpoint có thể dùng authority namespaced:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/internal/**")
        .hasAuthority("WORKFORCE_ADMIN")
    .requestMatchers("/api/partner/**")
        .hasAuthority("PARTNER_ORDERS_READ")
    .anyRequest().authenticated()
);
~~~

Các endpoint dùng chung có thể chấp nhận nhiều authority cụ thể:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/orders/**")
        .hasAnyAuthority(
            "WORKFORCE_ORDERS_READ",
            "PARTNER_ORDERS_READ")
    .anyRequest().authenticated()
);
~~~

### 7.2. Không dựa vào role name chung

Tránh policy chỉ kiểm tra role ADMIN nếu ADMIN được cấp bởi nhiều issuer với ý nghĩa khác nhau. Nếu ứng dụng thật sự có một platform-wide administrator, quyền đó nên được cấp bởi một nguồn policy tin cậy riêng, có approval/audit, và không được suy ra từ role string trùng tên.

### 7.3. Quyền từ issuer không thay thế tenant membership

Ngay cả authority PARTNER_ORDERS_READ cũng chỉ cho biết token có quyền đọc loại tài nguyên đó. Nó không tự xác định partner nào. Service vẫn phải ràng buộc tenant ID hoặc kiểm tra membership trên resource cụ thể.

## 8. Tenant isolation trong WebFlux

WebFlux chạy trên reactive pipeline. Không lưu tenant identity vào ThreadLocal hoặc static mutable field rồi giả định request kế tiếp sẽ có cùng thread. Hai request thuộc hai issuer có thể được xử lý xen kẽ trên cùng event-loop.

### 8.1. Truyền tenant identity tường minh

Một resolver có thể nhận Jwt đã xác thực:

~~~java
import java.util.Map;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
class ReactiveTenantIdentityResolver {

    private final Map<String, String> tenantByIssuer = Map.of(
        "https://login.corp.example", "internal",
        "https://identity.partner.example", "partner"
    );

    TenantIdentity resolve(Jwt jwt) {
        String issuer = jwt.getClaimAsString("iss");
        String tenantId = tenantByIssuer.get(issuer);
        if (tenantId == null) {
            throw new IllegalStateException("No tenant mapping for issuer");
        }
        return new TenantIdentity(issuer, jwt.getSubject(), tenantId);
    }
}
~~~

Reactive controller/service truyền TenantIdentity qua các method:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class ReactiveOrdersController {

    private final ReactiveTenantIdentityResolver tenantResolver;
    private final ReactiveTenantOrdersService orders;

    ReactiveOrdersController(
            ReactiveTenantIdentityResolver tenantResolver,
            ReactiveTenantOrdersService orders) {
        this.tenantResolver = tenantResolver;
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    Flux<OrderEntity> list(@AuthenticationPrincipal Jwt jwt) {
        TenantIdentity identity = tenantResolver.resolve(jwt);
        return orders.list(identity);
    }
}
~~~

Service reactive:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
class ReactiveTenantOrdersService {

    private final ReactiveOrderRepository repository;

    ReactiveTenantOrdersService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    Flux<OrderEntity> list(TenantIdentity identity) {
        return repository.findAllByTenantId(identity.tenantId());
    }
}
~~~

Ví dụ dùng explicit parameter để tenant boundary dễ nhìn và dễ test. Nếu ứng dụng dùng Reactor Context cho cross-cutting metadata, phải đảm bảo context được gắn vào đúng subscription và không dùng mutable singleton state.

### 8.2. Tránh ThreadLocal tenant context

Không làm:

~~~java
static final ThreadLocal<String> CURRENT_TENANT = new ThreadLocal<>();
~~~

ThreadLocal có thể hoạt động sai khi reactive pipeline đổi thread, và dữ liệu có thể rò giữa request nếu không clear đúng cách. Dùng explicit parameter, Reactor Context hoặc framework context propagation được cấu hình và kiểm thử.

### 8.3. Reactive repository luôn lọc tenant

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

interface ReactiveOrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    Flux<OrderEntity> findAllByTenantId(String tenantId);

    Mono<OrderEntity> findByIdAndTenantId(
        Long id,
        String tenantId);
}
~~~

Không lấy record bằng ID toàn cục rồi trả ra trước khi xác minh tenant. Dùng query có tenant predicate ở repository.

## 9. Cách ly dữ liệu ngoài database

Tenant isolation thường thất bại ở những nơi không phải bảng relational chính. Mọi cache, object storage, search index, message queue và background job đều phải giữ tenant boundary.

### 9.1. Cache key

Không cache order chỉ theo order ID nếu ID có thể trùng giữa tenant hoặc nếu authorization result phụ thuộc tenant. Cache key nên chứa tenant namespace:

~~~text
orders:{tenantId}:{orderId}
profile:{issuerAlias}:{subject}
permissions:{issuerAlias}:{subject}:{tenantId}
~~~

Với identity cache, dùng cặp issuer/subject. Với resource cache, dùng tenant/resource key. Không đưa raw access token vào cache key.

### 9.2. Object storage

Đặt object key theo tenant prefix:

~~~text
tenant/internal/orders/1001/invoice.pdf
tenant/partner/orders/1001/invoice.pdf
~~~

Không cho client tự gửi storage path tùy ý. Service phải tạo path từ tenant identity đã xác thực và kiểm tra ownership trước khi cấp pre-signed URL.

### 9.3. Search index

Search query phải filter tenant ID ở server side. Không dựa vào frontend tự gửi filter. Nếu dùng shared index, mọi query và aggregation đều cần tenant predicate; nếu có index riêng theo tenant, resolver phải chọn index từ trusted tenant mapping.

### 9.4. Message queue và event consumer

Event domain cần mang tenant identity rõ ràng:

~~~json
{
  "eventId": "evt-10001",
  "tenantId": "partner",
  "issuer": "https://identity.partner.example",
  "subject": "alice",
  "orderId": "1001",
  "eventType": "OrderCreated"
}
~~~

Consumer không nên tin tenant ID trong event nếu producer không được xác thực. Kiểm tra event source, schema, tenant membership và quyền truy cập trước khi xử lý. Tránh dùng global cache hoặc consumer state có thể trộn event của hai tenant.

### 9.5. Background jobs và scheduled tasks

Job chạy ngoài HTTP request không có bearer token để lấy tenant context. Khi enqueue job, lưu tenant ID và resource ownership đã xác thực vào job payload; worker phải validate tenant/resource mapping trước khi xử lý. Không dựa vào ThreadLocal còn sót từ request đã tạo job.

## 10. Cache và identity mapping phải cách ly theo issuer

Ngay cả khi hai issuer có cùng subject và cùng kid, cache không được trộn kết quả:

| Cache concern | Namespace nên có |
|---|---|
| Principal/user lookup | Issuer + subject |
| JWK/key selection | Issuer/JWKS source + kid |
| Authorization/permission snapshot | Issuer + subject + tenant + policy version |
| Tenant data | Tenant ID + resource key |
| Session/linking state | Issuer + subject + client/session context |

### 10.1. kid không phải global key identifier

Issuer A và issuer B có thể cùng dùng kid là signing-2026-01 nhưng public key khác nhau. Không dùng một map global chỉ theo kid. Key selection phải ở trong decoder/JWK source của đúng issuer.

### 10.2. Không dùng sub làm cache key duy nhất

Nếu issuer A và B đều có sub=alice, cache key user:alice có thể trả profile, permission hoặc tenant của issuer đầu tiên cho issuer còn lại. Dùng issuer alias hoặc issuer URI cùng subject.

### 10.3. Invalidate đúng namespace

Khi user bị disable hoặc tenant bị offboard, xóa các entries thuộc đúng issuer/tenant. Đảm bảo invalidation không bỏ sót node hoặc vô tình xóa policy của issuer khác có cùng subject/kid.

## 11. Kiểm thử hai issuer và data isolation

Một bộ test multi-issuer cần xác nhận cả token validation lẫn tenant boundary. Test chỉ dùng một JWT hợp lệ từ issuer A không chứng minh issuer B được cấu hình đúng; test chỉ kiểm tra controller với mock principal cũng không chứng minh issuer resolver/JWKS hoạt động.

### 11.1. Ma trận test tối thiểu

| Trường hợp | Token/request | Kết quả mong đợi |
|---|---|---|
| Workforce token hợp lệ | Issuer A, key A, audience A | Được xác thực, tenant internal |
| Partner token hợp lệ | Issuer B, key B, audience B | Được xác thực, tenant partner |
| Issuer không được duyệt | Issuer C | Bị từ chối, không fetch metadata/JWKS |
| Token A có audience B | Issuer A, chữ ký A, audience B | Bị từ chối |
| Token B có audience A | Issuer B, chữ ký B, audience A | Bị từ chối |
| Issuer A nhưng ký bằng key B | Issuer A, private key B | Bị từ chối |
| Issuer B nhưng ký bằng key A | Issuer B, private key A | Bị từ chối |
| Token hết hạn | Issuer/key/audience đúng, exp quá khứ | Bị từ chối |
| Cùng sub ở hai issuer | A/sub=alice và B/sub=alice | Hai identity/tenant riêng |
| Cùng kid ở hai issuer | kid giống nhau, key material khác | Mỗi token chỉ verify bằng key set đúng |
| Tenant header bị sửa | Token A, X-Tenant-ID=partner | Không truy cập dữ liệu partner |
| ID record tenant khác | Token A yêu cầu order thuộc partner | Không trả dữ liệu record đó |
| Role ADMIN từ partner | Token B có role ADMIN | Không tự nhận quyền WORKFORCE_ADMIN |

### 11.2. Dùng JWT ký thật để test resolver

Để test đường đi thực tế:

1. Tạo key pair A và B riêng cho test.
2. Dựng JWKS endpoint cục bộ A và B.
3. Cấu hình allowlist/manager map với hai JWKS URI cục bộ.
4. Ký token A bằng private A, đặt issuer/audience A.
5. Ký token B bằng private B, đặt issuer/audience B.
6. Gửi token qua Authorization Bearer header tới endpoint thật của test context.
7. Assert status, tenant-specific response và repository invocation.

Không gọi issuer production trong test và không dùng production private keys. JWKS mock server phải được giới hạn ở localhost/test network.

### 11.3. Mock JWT có phạm vi hẹp

Spring Security Test có thể tạo Authentication giả bằng mockJwt để test controller/service và authority rules nhanh. Tuy nhiên helper này thường bỏ qua issuer resolver, JWKS retrieval và signature verification. Vì vậy:

- Dùng mock JWT để test downstream mapping khi mục tiêu là controller/service.
- Dùng signed JWT qua Bearer header để test multi-issuer routing và decoder.
- Không coi test mock JWT là bằng chứng issuer allowlist hoặc JWKS isolation đang hoạt động.

### 11.4. Test hai subject giống nhau

Tạo hai token:

~~~text
Token A:
    iss = https://login.corp.example
    sub = alice
    aud = workforce-orders-api

Token B:
    iss = https://identity.partner.example
    sub = alice
    aud = partner-orders-api
~~~

Assert:

- Resolver trả tenant internal cho token A.
- Resolver trả tenant partner cho token B.
- User lookup dùng cặp issuer và subject.
- Không có profile, permission hoặc order nào được chia sẻ chỉ vì sub giống nhau.

### 11.5. Test tampering tenant header

Gửi token A với header:

~~~http
Authorization: Bearer <SIGNED_TOKEN_A>
X-Tenant-ID: partner
~~~

Response vẫn phải giới hạn dữ liệu theo tenant internal hoặc từ chối header không hợp lệ. Không được chuyển sang tenant partner chỉ vì request có header đó.

### 11.6. Test repository query có tenant predicate

Với token A, gọi endpoint bằng order ID thuộc tenant B. Kết quả có thể là 404 để không tiết lộ record tồn tại, hoặc 403 theo API policy; điều quan trọng là response không chứa dữ liệu tenant B và query luôn ràng buộc tenant.

Có thể verify repository được gọi với tenant ID lấy từ identity đã xác thực. Với database integration test, seed hai rows có cùng business identifier nhưng tenant khác nhau rồi xác nhận mỗi token chỉ nhìn thấy row thuộc tenant của nó.

### 11.7. Test multi-issuer cache isolation

Tạo hai token cùng subject và cùng kid nhưng key/issuer khác nhau. Sau khi token A được xác thực và cache principal:

- Token B vẫn phải đi qua decoder B.
- Không trả principal A cho token B.
- Cache key phải namespace theo issuer/JWKS source.
- Invalidation user A không được xóa hoặc ghi đè state user B ngoài ý muốn.

## 12. Liên kết account giữa hai issuer

Hai issuer có thể đại diện cho cùng một con người, nhưng Resource Server không nên tự động hợp nhất account chỉ vì email hoặc subject giống nhau.

### 12.1. Không auto-link bằng email đơn thuần

Email có thể:

- Chưa được xác minh ở một issuer.
- Được thay đổi hoặc tái cấp cho người khác.
- Dùng chung trong shared mailbox.
- Có semantics khác nhau giữa workforce và partner directory.

Nếu cần account linking, dùng một quy trình có xác minh rõ ràng, consent/approval phù hợp và audit. Lưu các external identities riêng và liên kết tới local account bằng một record có kiểm soát.

### 12.2. External identity và local account

Mô hình dữ liệu:

~~~text
LocalAccount
    id = 5001
    status = ACTIVE

ExternalIdentity
    issuer = https://login.corp.example
    subject = alice
    localAccountId = 5001

ExternalIdentity
    issuer = https://identity.partner.example
    subject = alice-partner-9
    localAccountId = 5001
~~~

Hai external identities chỉ trỏ cùng local account khi quy trình linking đã được xác thực và phê duyệt. Không suy ra linking tự động từ cùng sub hoặc email.

### 12.3. Quyền không tự hợp nhất khi link account

Liên kết danh tính không có nghĩa cộng tất cả authorities của hai issuer. Mỗi request vẫn phải giữ issuer context và policy tương ứng. Nếu business cần một quyền hợp nhất, policy service phải cấp quyền đó rõ ràng và ghi audit.

## 13. Security pitfalls trong multi-issuer deployments

### 13.1. Issuer allowlist bị mở rộng từ input không tin cậy

Không tạo decoder hoặc thêm tenant vào registry dựa trên issuer URL do token/request gửi lên. Provision issuer qua trusted admin/control plane.

### 13.2. Dùng chung JWKS hoặc key cache không namespace

Hai issuer có thể trùng kid. Mỗi issuer phải có JWK source/decoder riêng hoặc cache namespace chứa issuer/JWKS source.

### 13.3. Chỉ kiểm tra chữ ký mà bỏ audience

Token được ký bởi issuer hợp lệ nhưng dành cho một API khác không nên được chấp nhận. Mỗi manager cần audience validator phù hợp.

### 13.4. Chỉ kiểm tra issuer mà không kiểm tra signature

Issuer claim có thể bị giả mạo nếu không xác minh chữ ký. Resolver dùng claim chưa xác thực để chọn manager; decoder phải validate chữ ký và issuer trước khi Authentication được tin cậy.

### 13.5. Dùng authority chung cho cả hai issuer

Role name trùng nhau không có nghĩa quyền tương đương. Namespace hoặc custom converter theo issuer để tránh quyền partner trở thành quyền workforce.

### 13.6. Tenant ID lấy từ request

Header/path/query tenant ID chỉ là input. Tenant context phải được ràng buộc với identity đã xác thực và membership policy.

### 13.7. Repository chỉ lọc tenant ở một vài endpoint

GET có filter nhưng export, search, update, delete hoặc background job không có filter vẫn có thể làm lộ dữ liệu. Tenant predicate phải xuyên suốt mọi data access path.

### 13.8. Dùng ThreadLocal trong WebFlux

Reactive requests không có bảo đảm một thread duy nhất. ThreadLocal có thể mất context hoặc rò tenant giữa requests. Dùng explicit context hoặc Reactor Context.

### 13.9. Tin email để hợp nhất identity

Email trùng nhau không phải bằng chứng hai issuer cùng một principal. Account linking cần quy trình riêng.

### 13.10. Không kiểm tra offboarding

Khi issuer hoặc tenant bị offboard, phải xóa/disable resolver mapping, tenant mapping, cache entries, client permissions và background jobs liên quan. Không chỉ xóa issuer khỏi cấu hình nhưng vẫn giữ dữ liệu/caches có thể truy cập qua đường khác.

## 14. Phân biệt OIDC ID Token và OAuth 2.0 Access Token

Một OIDC issuer thường phát hành cả ID Token và Access Token, nhưng Resource Server API cần access token. Không chấp nhận ID Token chỉ vì nó là JWT có chữ ký hợp lệ từ cùng issuer.

| Thuộc tính | ID Token | Access Token |
|---|---|---|
| Audience | OIDC client nhận đăng nhập | Resource/API được gọi |
| Mục đích | Xác nhận sự kiện authentication cho client | Cấp quyền truy cập resource |
| Nơi sử dụng | OIDC client/Relying Party | OAuth 2.0 Resource Server |
| Scope/authority | Không phải nguồn API authorization mặc định | Có thể mang scope/permissions cho API |

Nếu API audience là orders API, token có audience là browser client phải bị từ chối, dù cùng issuer và chữ ký hợp lệ.

### 14.1. Token profile phải thống nhất giữa hai issuer

Issuer A và B có thể dùng profile access token khác nhau. Cần xác định:

- Token type/header typ nếu profile yêu cầu.
- Audience claim format và expected resource identifier.
- Scope/permissions claim name và data type.
- Subject semantics và stability.
- Issuer and time claims.
- Required client identifier claim nếu policy cần.

Nếu dùng RFC 9068 JWT Profile for OAuth 2.0 Access Tokens, kiểm tra các yêu cầu của profile tương ứng và cấu hình validator theo profile. Không suy luận token là access token chỉ từ việc nó parse được thành JWT.

### 14.2. Audience khác nhau là ranh giới quan trọng

Ví dụ:

~~~text
Issuer A access token:
    iss = https://login.corp.example
    aud = workforce-orders-api

Issuer B access token:
    iss = https://identity.partner.example
    aud = partner-orders-api
~~~

Một token từ issuer A không được chấp nhận chỉ vì issuer A nằm trong allowlist nếu audience không dành cho API. Ngược lại, audience B không được chấp nhận trong decoder A.

## 15. Issuer lifecycle và thay đổi cấu hình

Danh sách hai issuer được phê duyệt là một phần của security boundary. Thay đổi issuer, JWKS URI, audience hoặc tenant mapping cần quy trình quản trị và rollout có kiểm soát.

### 15.1. Onboard issuer mới

Trước khi thêm issuer:

1. Xác minh ownership và issuer URI chính xác.
2. Lấy metadata/JWKS URI từ tài liệu chính thức hoặc control plane đã xác thực.
3. Kiểm tra TLS, DNS, network reachability và JWKS public keys.
4. Xác định audience, token profile và thuật toán được phép.
5. Định nghĩa tenant mapping và authority converter.
6. Thêm issuer vào allowlist và decoder manager map.
7. Test token thật bằng test key/issuer environment.
8. Deploy theo canary và quan sát authentication failures.

Không cho phép issuer mới truy cập production chỉ vì metadata endpoint trả JSON hợp lệ.

### 15.2. Đổi JWKS URI

JWKS URI là trust-sensitive configuration. Khi chuyển endpoint:

- Publish cùng public key set ở endpoint mới trước.
- Kiểm tra TLS certificate và issuer metadata.
- Cập nhật manager configuration.
- Xác nhận các nodes tải được JWKS mới.
- Giữ endpoint cũ trong thời gian overlap nếu cần.
- Thu hồi endpoint cũ sau khi propagation hoàn tất.

Nếu thay issuer URI, đó có thể là một trust domain identity mới; không tự sửa chuỗi issuer rồi tiếp tục coi token cũ là tương đương nếu chưa có migration policy.

### 15.3. Offboard issuer

Khi issuer không còn được phép:

- Gỡ issuer khỏi trusted resolver/manager registry.
- Từ chối token mới từ issuer đó.
- Xóa decoder/cache entries theo namespace.
- Thu hồi hoặc kết thúc sessions/token families theo khả năng issuer.
- Xác nhận tenant data đã được export/retention theo policy.
- Dừng background consumers và scheduled jobs của tenant.
- Giữ audit records đủ lâu theo retention policy.

Không xóa dữ liệu tenant chỉ vì issuer bị offboard; data retention/deletion là quyết định riêng.

### 15.4. Rotate key ở từng issuer độc lập

Issuer A và B có thể có lịch key rotation khác nhau. Mỗi decoder/JWK source cần refresh đúng endpoint của issuer tương ứng. Khi A rotate, không được làm mất public key B hoặc vô tình thay JWKS cache B.

Unknown kid tăng bất thường ở một issuer cần được điều tra riêng theo issuer alias. Đừng gộp metrics khiến sự cố issuer A bị che bởi traffic issuer B.

## 16. Observability và audit cho multi-issuer

Khi có hai trust domains, log và metric cần phân biệt issuer nhưng không lộ token hoặc dữ liệu cá nhân quá mức.

### 16.1. Metrics gợi ý

| Metric | Labels bounded |
|---|---|
| JWT authentication attempts | issuer alias, outcome |
| JWT signature failures | issuer alias, failure category |
| Unknown issuer attempts | environment, outcome |
| JWKS fetch latency/errors | issuer alias |
| Audience validation failures | issuer alias, API alias |
| Tenant authorization denials | tenant alias, operation |
| Cross-tenant access denials | tenant alias, resource type |
| Repository queries by tenant | tenant alias, operation |
| Tenant cache hits/misses | tenant alias, cache type |

Không dùng raw JWT, access token, subject, email hoặc token ID làm metric labels. Giá trị có cardinality cao và có thể chứa thông tin nhạy cảm.

### 16.2. Structured authentication logs

Ví dụ:

~~~text
event=jwt_authentication issuer=workforce outcome=success
event=jwt_authentication issuer=partner outcome=success
event=jwt_authentication issuer=unknown outcome=rejected
event=jwt_validation issuer=partner outcome=invalid_audience
event=tenant_authorization tenant=internal outcome=denied resource=order
event=tenant_authorization tenant=partner outcome=allowed resource=order
~~~

Issuer alias là nhãn vận hành nội bộ ánh xạ tới issuer URI đã cấu hình. Không log toàn bộ JWT hoặc Authorization header.

### 16.3. Audit principal identity

Audit record nên định danh principal bằng issuer và subject hoặc local identity ID đã resolve:

~~~json
{
  "actor": {
    "issuerAlias": "partner",
    "subject": "alice",
    "localUserId": 8891,
    "tenantId": "partner"
  },
  "action": "ORDER_READ",
  "resourceId": "1001",
  "outcome": "ALLOWED"
}
~~~

Nếu subject là dữ liệu cá nhân theo policy tổ chức, dùng local ID hoặc pseudonymous identifier trong log thường ngày; chỉ giữ mapping chi tiết trong hệ thống có quyền truy cập kiểm soát.

## 17. Runbook khi có truy cập chéo tenant

Khi phát hiện principal từ issuer A đọc được dữ liệu tenant B:

1. Xác định request, issuer alias, subject/local identity và tenant được resolve.
2. Kiểm tra JWT audience và authorities đã được decoder xác minh.
3. Kiểm tra issuer-to-tenant mapping và tenant claim policy.
4. Kiểm tra controller/service có nhận tenant ID từ header/path/body không.
5. Kiểm tra repository query có tenant predicate ở read/update/delete/export/search không.
6. Kiểm tra cache key có namespace theo tenant/issuer không.
7. Kiểm tra object storage path, search index và background jobs.
8. Kiểm tra identity linking có auto-link theo email/sub không.
9. Tạm khóa endpoint hoặc tenant path bị ảnh hưởng nếu cần.
10. Thu thập audit evidence, xác định records đã bị truy cập và xử lý theo incident process.

### 17.1. Phân biệt lỗi authentication và data isolation

| Triệu chứng | Lớp cần kiểm tra |
|---|---|
| Token issuer lạ được chấp nhận | Trusted issuer resolver/allowlist |
| Token A xác minh bằng key B | Decoder/JWKS namespace |
| Token A có audience B được chấp nhận | Audience validator |
| Partner role cấp quyền workforce | Authority converter/policy |
| Subject trùng làm lộ profile | Identity key (issuer, subject) |
| Tenant header đổi dữ liệu trả về | Tenant context resolver |
| GET an toàn nhưng export bị lộ | Export/search repository path |
| Request isolation đúng nhưng cache trả sai | Cache key/invalidation |
| WebFlux request nhận tenant của request khác | ThreadLocal/context propagation |

### 17.2. Hành động giảm thiểu

Tùy mức độ:

- Gỡ issuer hoặc tenant khỏi trusted registry nếu trust bị compromise.
- Disable authority mapping bị cấp quá rộng.
- Bắt buộc tenant predicate ở repository/service.
- Purge cache entries theo namespace bị ảnh hưởng.
- Thu hồi sessions/tokens hoặc client credentials theo policy issuer.
- Khóa account linking sai và điều tra local identity mapping.
- Rà soát audit logs để xác định phạm vi dữ liệu đã bị đọc.

## 18. Checklist triển khai hai issuer

### 18.1. Trust và token validation

- [ ] Chỉ hai issuer đã phê duyệt có mặt trong allowlist.
- [ ] Issuer được so sánh bằng exact identifier.
- [ ] Issuer chưa xác thực chỉ dùng làm routing selector.
- [ ] Mỗi issuer có decoder/JWKS source riêng.
- [ ] Mỗi issuer có audience validator riêng.
- [ ] Signature, issuer, exp, nbf và algorithm được kiểm tra.
- [ ] Chỉ access token profile được API chấp nhận.
- [ ] Không fetch metadata/JWKS URL tùy ý từ token/request.
- [ ] Unknown issuer bị từ chối trước khi tạo outbound network call.

### 18.2. Identity và tenant

- [ ] User identity được định danh bằng issuer + subject.
- [ ] Tenant mapping lấy từ trusted registry hoặc claim đã validate theo policy.
- [ ] Header/path/query tenant không tự cấp quyền tenant.
- [ ] Account linking có workflow xác minh và audit.
- [ ] Authorities được namespace/map theo issuer.
- [ ] Tenant membership được kiểm tra khi resource yêu cầu.

### 18.3. Data access và context

- [ ] Mọi repository query có tenant predicate.
- [ ] Read, insert, update, delete, export và search đều được cách ly.
- [ ] Cache key chứa issuer/tenant/resource context phù hợp.
- [ ] Object storage path được tạo từ trusted tenant identity.
- [ ] Search index và message consumer áp dụng tenant filter.
- [ ] Background jobs mang tenant context đã xác minh.
- [ ] WebFlux không dùng ThreadLocal cho tenant context.
- [ ] RLS (nếu dùng) được test với connection pool/transaction.

### 18.4. Testing và operations

- [ ] Có signed-token integration tests cho cả hai issuer.
- [ ] Test unknown issuer, wrong key, wrong audience và expired token.
- [ ] Test same-subject/same-kid collision giữa hai issuer.
- [ ] Test tenant header tampering và cross-tenant record access.
- [ ] Test authority collision và account-linking behavior.
- [ ] Test cache/search/storage/event tenant isolation.
- [ ] Metrics/logs phân biệt issuer bằng alias bounded.
- [ ] Có runbook onboard/offboard và cross-tenant incident.

## 19. Kết luận

Spring Security có thể hỗ trợ nhiều issuer bằng cách chọn AuthenticationManager theo issuer trong JWT. Với hai issuer cố định, trusted issuer resolver là điểm bắt đầu phù hợp; khi audience, thuật toán hoặc authority mapping khác nhau, tạo manager/decoder riêng cho từng issuer và tra cứu bằng allowlist tĩnh.

Claim issuer chưa xác thực chỉ được dùng làm routing hint. Decoder vẫn phải xác minh chữ ký bằng JWKS của issuer, kiểm tra issuer, audience, thời gian, thuật toán và access token profile. Không tự động fetch metadata/JWKS từ URL do token cung cấp.

Data isolation bắt đầu sau authentication: định danh principal bằng issuer cộng subject, ánh xạ tenant từ trusted policy, namespace authority theo issuer và thêm tenant predicate vào mọi data access path. Cache, object storage, search, events và background jobs cũng phải mang đúng tenant boundary. Với WebFlux, truyền tenant identity tường minh hoặc dùng Reactor Context đã cấu hình; không dùng ThreadLocal.

**Hai issuer được phép gọi cùng một API không có nghĩa hai issuer được phép nhìn thấy cùng một dữ liệu.** Kiểm thử signed JWT từ cả hai issuer cùng các trường hợp subject/kid trùng, audience sai và tenant tampering là cách chứng minh trust routing và data isolation hoạt động độc lập.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Multi-Tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Multi-Tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — JwtIssuerAuthenticationManagerResolver Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security — JwtIssuerReactiveAuthenticationManagerResolver Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)

