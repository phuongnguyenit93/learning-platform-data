# Tách endpoint, issuer hoặc tenant để chọn chiến lược rõ ràng

## 1. Vấn đề khi một ứng dụng có nhiều cơ chế xác thực

Một **Spring Security OAuth 2.0 / OIDC Resource Server** có thể nhận requests từ nhiều nhóm caller. Không phải nhóm nào cũng dùng một loại credential hoặc có cùng mức độ tin cậy:

- Ứng dụng mobile gửi **JWT access token** cho Orders API.
- Đối tác gửi **opaque access token**, Resource Server kiểm tra bằng introspection.
- Nhân viên truy cập trang quản trị qua **OIDC Login và session/cookie**.
- Microservice nội bộ gửi JWT do một issuer dành riêng cho service accounts phát hành.
- Nhiều tổ chức (**tenants**) dùng nhiều Authorization Servers khác nhau hoặc cùng issuer nhưng yêu cầu cô lập quyền dữ liệu.

Nếu cứ “thử mọi kiểu xác thực cho mọi endpoint”, hệ thống dễ mắc các lỗi **authentication confusion**, **token substitution**, **downgrade**, hoặc **cross-tenant access**. Một token đã được ký hợp lệ chưa chắc dành cho API này; một principal được xác thực thành công chưa chắc được đọc dữ liệu của tenant khác.

Bài này giải thích ba chiều phân tách độc lập:

| Chiều | Câu hỏi | Vai trò |
|---|---|---|
| **Endpoint** | Request đang vào nhóm URL nào? | Chọn cơ chế xác thực theo hợp đồng API |
| **Issuer** | Access token đến từ Authorization Server nào? | Chọn trusted manager/decoder và kiểm tra `iss`, signature, `aud` |
| **Tenant** | Caller yêu cầu thao tác với tổ chức nào? | Áp dụng ranh giới dữ liệu, membership, entitlement và ACL |

**Nguyên tắc bao trùm:** thông tin dùng **định tuyến** không tự trở thành thông tin dùng **cấp quyền**. URL, header, Host, hoặc claim `iss`/`tenant_id` chưa xác thực đều có thể do caller điều khiển.

## 2. Chọn chiến lược theo mục đích, không theo thử-sai

Một thiết kế rõ ràng có thể quy định:

~~~text
/api/orders/**     -> JWT Resource Server, issuer Orders
/api/partners/**   -> Opaque token Resource Server, partner introspection
/console/**        -> Browser OIDC Login + session
/actuator/health   -> Health policy riêng
unmatched paths    -> Deny
~~~

Một hệ thống khác có thể cho **cùng một endpoint** nhận JWT từ hai trusted issuers. Khi đó cần một **multi-issuer resolver** nằm trong JWT chain, chứ không phải tách URL theo issuer một cách máy móc.

### 2.1. Cây quyết định ở mức kiến trúc

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Endpoint group"}
    B -->|"/api/partners/**"| C["Opaque introspection"]
    B -->|"/api/orders/**"| D["JWT / trusted issuer resolver"]
    B -->|"/console/**"| E["OIDC session login"]
    B -->|"Unknown"| X["Fallback deny"]
    C --> F["Token active + token contract"]
    D --> G["Verify signature + issuer + audience + time"]
    E --> H["Session authentication"]
    F --> I["Authenticated principal"]
    G --> I
    H --> I
    I --> J{"Scope / role của action?"}
    J -->|Không| K["403 hoặc policy response"]
    J -->|Có| L{"Tenant + owner + ACL?"}
    L -->|Không| K
    L -->|Có| M["Business handler"]
~~~

**Không được** kết luận rằng API đã được bảo vệ chỉ vì đã tìm ra một nhánh hợp lệ. Mỗi nhánh phải có validators và authorization policy thích hợp.

### 2.2. Bốn yêu cầu bảo mật cho mọi nhánh

1. **Trust** — chỉ chấp nhận issuers/providers đã được phê duyệt.
2. **Intended audience** — token phải được phát hành cho đúng Resource Server.
3. **Authority semantics** — scope/role phải được hiểu đúng theo profile của issuer.
4. **Resource isolation** — vẫn kiểm tra tenant, owner, membership, ACL của tài nguyên.

Từng phần có thể thất bại độc lập. Token có chữ ký đúng nhưng audience sai vẫn phải từ chối; token có audience đúng và scope đọc vẫn có thể bị từ chối vì không thuộc tenant đó.

## 3. Spring Security Servlet: hai tầng chọn policy

Trong **Spring MVC / Servlet**, `FilterChainProxy` duyệt các `SecurityFilterChain` được cấu hình. Một request được gắn vào **chain đầu tiên khớp**; nó không chạy nối tiếp mọi chains để tích lũy hoặc chọn policy dễ nhất.

~~~text
Servlet request
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |
    +-- @Order(1): /api/partners/**  -> opaqueToken()
    +-- @Order(2): /api/orders/**    -> jwt()
    +-- @Order(3): /console/**       -> oauth2Login()
    +-- @Order(99): /**             -> denyAll()
~~~

Các tên lớp nền tảng:

~~~java
org.springframework.security.web.SecurityFilterChain
org.springframework.security.config.annotation.web.builders.HttpSecurity
org.springframework.security.web.FilterChainProxy
~~~

### 3.1. `securityMatcher` khác `requestMatchers`

~~~java
http.securityMatcher("/api/partners/**");
~~~

định nghĩa: **chain này áp dụng cho nhóm URL nào?**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/partners/reports/**")
        .hasAuthority("SCOPE_partner.reports.read")
    .anyRequest().denyAll()
);
~~~

định nghĩa: **bên trong chain được chọn, yêu cầu authority gì?**

Một chain `securityMatcher("/api/**")` có thứ tự cao hơn chain `securityMatcher("/api/admin/**")` có thể khiến chain admin **không bao giờ được chọn**. Không dựa vào một rule mạnh nằm ở chain sau nếu chain trước đã match request.

### 3.2. Chọn theo endpoint khi nào?

Phù hợp khi các vùng URL thực sự có **credential contract khác nhau**, chẳng hạn:

- Bearer JWT so với opaque introspection.
- Machine API so với browser OIDC login.
- Public health so với internal API.
- Có/không có session/cookie và CSRF policy.
- Bearer JSON error 401/403 so với browser redirect.

Nếu mọi endpoint đều dùng một issuer JWT, chỉ khác scopes theo HTTP method, **một chain với nhiều `requestMatchers`** thường đơn giản và ít rủi ro hơn nhiều chains.

## 4. Ví dụ: tách JWT và opaque token theo hai endpoint groups

Giả định hợp đồng:

~~~text
/api/orders/**:
    JWT access token
    issuer = https://id.example.test/realms/orders
    audience = orders-api

/api/partners/**:
    opaque access token
    introspection endpoint = https://partner-id.example.test/oauth2/introspect
    scopes = partner.reports.read, partner.reports.write
~~~

Cả hai cơ chế đều là Resource Server authentication, nhưng **chọn theo URL** và không fallback sang cơ chế khác khi token sai.

### 4.1. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Nếu thêm OIDC browser login, có thể cần:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
~~~

Không thêm OAuth2 Client chỉ vì muốn xác minh access token trên API; hai chức năng khác nhau.

### 4.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/orders
          audiences:
            - orders-api
        opaquetoken:
          introspection-uri: https://partner-id.example.test/oauth2/introspect
          client-id: orders-partner-introspector
          client-secret: ${PARTNER_INTROSPECTION_CLIENT_SECRET}
~~~

URLs là ví dụ. Secret phải lấy từ environment hoặc secret manager, không commit vào Git và không đưa vào browser. Property `audiences` cần phiên bản Spring Boot hỗ trợ; nếu tự tạo decoder bean, phải bảo đảm audience validation không bị mất.

### 4.3. Ba chains với thứ tự cố định

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class EndpointSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain partnerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/partners/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/partners/reports/**")
                    .hasAuthority("SCOPE_partner.reports.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/orders/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(99)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

Đây là **một kiến trúc thay thế** cho cấu hình đơn chain thông thường. Đừng đăng ký thêm một chain `/**` với thứ tự cao hơn rồi vô ý che các chains này.

Các lưu ý:

- Hai API chains giả định **Bearer-only, không cookie/session authentication**, nên disable CSRF có thể phù hợp sau khi đánh giá threat model. Không áp dụng cách đó cho browser login chain.
- `/api/orders/**` và `/api/partners/**` cần kiểm thử exact root paths như `/api/orders` hoặc `/api/partners` nếu controller có mapping tại root; path matcher behavior có thể khác theo phiên bản/trailing slash.
- Fallback denyAll bảo đảm các paths chưa công bố không tự được phép. Nếu cần health, actuator, API docs hoặc OIDC callbacks, thêm policies rõ.
- Response của fallback không nhất thiết luôn là 401; mục tiêu là **deny** theo contract.
- Scope chỉ kiểm tra quyền ở cấp hành động; tenant, owner và ACL cần kiểm tra trong business service.

### 4.4. Ma trận request

| URL | Token | Chiến lược bắt buộc |
|---|---|---|
| `GET /api/orders/42` | Orders JWT hợp lệ | JWT validation + `orders.read` |
| `POST /api/orders/42` | Orders JWT chỉ có `orders.read` | 403 nếu thiếu write scope |
| `GET /api/orders/42` | Partner opaque token | Không fallback sang opaque introspection |
| `GET /api/partners/reports/2026` | Partner opaque active | Introspection + partner scope |
| `GET /api/partners/reports/2026` | Orders JWT | Không fallback sang JWT decoding |
| `GET /api/unlisted` | Token bất kỳ | Fallback deny |
| Partner introspection timeout | Partner token | Không fail open |

Việc một request vượt qua filter chain không bảo đảm controller trả HTTP 200; service có thể trả 404, 409 hoặc deny vì policy nghiệp vụ.

## 5. Không suy đoán strategy từ hình dạng access token

Một cách làm dễ sai:

~~~java
if (token.split("\\.").length == 3) {
    // Try JWT
} else {
    // Try opaque token
}
~~~

Không an toàn để xem đây là hợp đồng xác thực:

- Opaque token có thể chứa dấu chấm.
- Một chuỗi ba phần không chứng minh JWS hợp lệ.
- JWT/JWE có thể có nhiều token profiles khác nhau.
- Attacker điều khiển toàn bộ token string.
- Provider có thể thay đổi token format mà không đổi contract của API.

**Tránh logic “JWT verify thất bại thì thử opaque và chấp nhận nếu được”**. Điều đó biến signature failure thành cơ hội chọn cơ chế khác, có thể dẫn tới downgrade. Nếu một endpoint thực sự phải chấp nhận nhiều formats, phải có một `AuthenticationManagerResolver<HttpServletRequest>` hoặc cơ chế tương đương với **routing policy định sẵn, providers allowlist và validators riêng**.

Không dùng query parameter hay header do caller tự chọn kiểu:

~~~http
X-Authentication-Mode: bypass-jwt
~~~

để đổi sang nhánh yếu hơn. Nếu gateway gửi security metadata, phải bảo vệ trust boundary bằng TLS/mTLS, header stripping và cấm backend bị truy cập trực tiếp vòng ngoài.

## 6. Khi cùng một endpoint chấp nhận nhiều JWT issuers

Giả sử `GET /api/orders/**` được phép dùng token của hai Authorization Servers:

~~~text
Retail issuer:
https://id.example.test/realms/retail

Enterprise issuer:
https://id.example.test/realms/enterprise
~~~

Nếu cấu hình chỉ một `issuer-uri`, issuer còn lại thường bị từ chối. Nếu bỏ kiểm tra `iss` để “nhận cả hai”, API có thể chấp nhận token từ nguồn ngoài hợp đồng.

Giải pháp là **multi-issuer authentication với trusted issuers allowlist**.

### 6.1. `JwtIssuerAuthenticationManagerResolver`

Trong Servlet Spring Security:

~~~java
org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver
~~~

Resolver chọn một `AuthenticationManager` phù hợp từ issuer claim để đi tới decoder có trust profile tương ứng.

**Điểm bảo mật quan trọng:** `iss` được đọc từ token **trước** khi xác minh chữ ký chỉ được dùng như **routing hint chưa tin cậy**. Nó không chứng minh token do issuer đó phát hành. Resolver chỉ được chọn từ trusted allowlist, sau đó decoder phải xác minh signature, issuer, expiry và audience.

### 6.2. Cấu hình issuers tường minh

Với Spring Security có API `fromTrustedIssuers(...)`, ví dụ:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

@Configuration
public class TrustedIssuerConfig {

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            "https://id.example.test/realms/retail",
            "https://id.example.test/realms/enterprise"
        );
    }
}
~~~

Gắn vào chain nhận nhiều issuers:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersMultiIssuerSecurity {

    @Bean
    SecurityFilterChain ordersJwtChain(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver resolver)
            throws Exception {

        return http
            .securityMatcher("/api/orders/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

Đây là **cấu hình thay thế** cho chain JWT single-issuer ở phần 4. Khi sử dụng, không khai báo cả hai chain cùng matcher mà không xác định precedence.

API `fromTrustedIssuers` và các overloads có thể khác giữa Spring Security 6.x/7.x; với dự án thực tế dùng đúng version-matched API. Ý tưởng quan trọng là **trusted issuer registry + manager xác minh đúng issuer**.

### 6.3. Issuer allowlist chưa đồng nghĩa audience validation

Token:

~~~json
{
  "iss": "https://id.example.test/realms/retail",
  "aud": ["billing-api"],
  "scope": "invoices.read"
}
~~~

có thể được ký đúng bởi **trusted issuer** nhưng vẫn **không dành cho Orders API**. Phải kiểm tra `aud` contains `orders-api` hoặc một token audience contract tương đương.

Đừng mặc định factory issuer resolver tự áp mọi **custom audience/profile validator**. Khi cần nhiều profiles, mỗi issuer manager có thể được cấu hình bằng decoder riêng với validators tương ứng.

### 6.4. Tạo decoder có issuer + audience validator

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public final class OrdersDecoders {

    private OrdersDecoders() {}

    public static NimbusJwtDecoder forIssuer(
            String trustedJwksUri,
            String trustedIssuer,
            String requiredAudience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(trustedJwksUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(trustedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(requiredAudience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Incorrect access token audience",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
~~~

Đây là **factory tạo một decoder cho một issuer**. Chỉ tạo bean decoder không có nghĩa một multi-issuer resolver đã tự sử dụng nó; cần wiring manager/decoder tương ứng trong registry. Khi custom `JwtDecoder`, phải giữ signature/algorithm/trust, issuer, expiry/not-before, audience và token profile validators.

### 6.5. Manager registry cho từng issuer

Một phương án tường minh trên các Spring Security 6.x versions có constructor nhận `AuthenticationManagerResolver<String>`:

~~~java
package com.example.orders.security;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

@Configuration
public class ManagerRegistryConfig {

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {

        AuthenticationManager retail = manager(
            "https://id.example.test/realms/retail",
            "https://id.example.test/realms/retail/protocol/openid-connect/certs",
            "orders-api"
        );

        AuthenticationManager enterprise = manager(
            "https://id.example.test/realms/enterprise",
            "https://id.example.test/realms/enterprise/protocol/openid-connect/certs",
            "orders-api"
        );

        Map<String, AuthenticationManager> trusted = Map.of(
            "https://id.example.test/realms/retail", retail,
            "https://id.example.test/realms/enterprise", enterprise
        );

        return new JwtIssuerAuthenticationManagerResolver(trusted::get);
    }

    private static AuthenticationManager manager(
            String issuer,
            String jwksUri,
            String audience) {

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(
                OrdersDecoders.forIssuer(jwksUri, issuer, audience)
            );

        return provider::authenticate;
    }
}
~~~

Mẫu constructor/API này có thể deprecated hoặc thay thế ở version mới; dùng version-matched equivalent nếu cần. Không bật đồng thời hai beans `issuerResolver` cùng type trong một cấu hình mà không wiring cụ thể.

Điểm bảo mật của mẫu:

- Map chỉ có những issuers đã được cấu hình.
- Unknown issuer → không có manager để xác thực.
- JWKS URI là giá trị do server quyết định, **không lấy từ claim `jku` hay request header**.
- Manager được chọn vẫn verify chữ ký và `iss`/`aud`.
- Không đọc `iss` rồi coi là bằng chứng token hợp lệ.

### 6.6. Lưu ý hiệu năng và availability

Multi-issuer có thể kéo theo nhiều JWKS caches, DNS/TLS dependencies, lịch key rotation và token profiles khác nhau. Cần timeout, metrics và chính sách xử lý key fetch failure riêng.

Nếu AS không khả dụng khi cần khóa mới, **không được fail open**. Phân biệt lỗi `invalid_token` với lỗi hạ tầng `jwks_unavailable` trong telemetry, tránh yêu cầu client đăng nhập lại liên tục khi nguyên nhân là key service outage.

## 7. Tenant là phạm vi dữ liệu, không phải authentication proof

Giả sử request:

~~~http
GET /tenants/tenant-b/orders/42 HTTP/1.1
Authorization: Bearer <TOKEN>
X-Tenant-Id: tenant-b
~~~

Caller có thể tự sửa path/header thành tenant khác. Chúng chỉ là **requested tenant context**, không phải quyền hợp lệ.

JWT đã được verify:

~~~json
{
  "iss": "https://id.example.test/realms/retail",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

Không được dùng token tenant-a để đọc tenant-b chỉ vì path chứa `tenant-b`.

### 7.1. Những nguồn tenant information

| Nguồn | Độ tin cậy ban đầu | Cách dùng đúng |
|---|---|---|
| `/tenants/{tenant}/...` | Client điều khiển | Chọn requested tenant, bind sau auth |
| `X-Tenant-Id` | Client điều khiển trừ khi gateway đã bảo vệ | Không dùng làm authority |
| Host/subdomain | Cần normalize và trusted proxy policy | Chỉ route trong allowlist |
| JWT `tenant_id` trước signature verification | Chưa tin cậy | Không cấp quyền |
| JWT `tenant_id` sau validation | Được issuer xác nhận theo contract | Ràng buộc với URL và resource |
| Database membership | Dữ liệu nội bộ | Kiểm tra quyền hiện thời |
| Server-side tenant-to-issuer registry | Policy tin cậy | Chọn managers/validators, không cấp quyền trực tiếp |

### 7.2. Bind tenant từ request với principal đã xác thực

Một policy bean có thể dùng `@PreAuthorize` trong Servlet Resource Server:

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public class TenantAccessPolicy {

    private final OrderAccessRepository access;

    public TenantAccessPolicy(OrderAccessRepository access) {
        this.access = access;
    }

    public boolean canRead(
            Authentication authentication,
            String requestedTenant,
            long orderId) {

        if (authentication == null ||
                !(authentication.getPrincipal() instanceof Jwt jwt)) {
            return false;
        }

        Object tenantClaim = jwt.getClaims().get("tenant_id");
        String subject = jwt.getSubject();

        if (!(tenantClaim instanceof String tokenTenant)
                || tokenTenant.isBlank()
                || subject == null
                || subject.isBlank()) {
            return false;
        }

        if (!tokenTenant.equals(requestedTenant)) {
            return false;
        }

        // Phải kiểm tra entitlement, owner và order thật thuộc tenant.
        return access.canReadOrder(subject, tokenTenant, orderId);
    }
}
~~~

`OrderAccessRepository` là interface nghiệp vụ do ứng dụng tự triển khai.

Service:

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class TenantOrdersService {

    private final OrderRepository orders;

    public TenantOrdersService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @tenantAccess.canRead(authentication, #tenant, #orderId)"
    )
    public OrderDto load(String tenant, long orderId) {
        return orders.findDtoByTenantAndId(tenant, orderId);
    }
}
~~~

Controller gọi qua Spring-managed service proxy:

~~~java
@RestController
@RequestMapping("/tenants/{tenant}/orders")
public class TenantOrdersController {

    private final TenantOrdersService orders;

    public TenantOrdersController(TenantOrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    public OrderDto load(
            @PathVariable String tenant,
            @PathVariable long orderId) {
        return orders.load(tenant, orderId);
    }
}
~~~

Các imports cho controller tương ứng thuộc `org.springframework.web.bind.annotation.*`. Cần bật `@EnableMethodSecurity` và bảo đảm `@PreAuthorize` được gọi **qua AOP proxy**, không bypass bởi `this.load(...)` trong cùng target bean.

Ngoài ra, `#tenant` và `#orderId` trong SpEL cần parameter names được resolve chính xác (ví dụ Java compiler `-parameters`). Policy kiểm tra trong service chưa thay thế database query isolation; repository cũng phải lọc bằng tenant/owner.

### 7.3. Khi một user được quyền nhiều tenants

Nếu business yêu cầu cross-tenant access, không chỉ dùng:

~~~java
if (hasRole("ADMIN")) return true;
~~~

mà cần **explicit delegation policy**:

~~~text
(trusted issuer, subject)
  -> membership/delegation record
  -> allowed tenant set
  -> allowed action set
  -> expiry and approval state
  -> audit
~~~

Một token có `tenant_id=tenant-a` không tự được truy cập mọi tenant bằng một global role không rõ nguồn. Với admin support cross-tenant, cần chính sách phê duyệt và audit độc lập.

## 8. Khi tenant quyết định issuer

Ví dụ server registry:

~~~text
tenant-a -> https://id.example.test/realms/retail
tenant-b -> https://id.example.test/realms/enterprise
~~~

Tenant từ URL hoặc Host có thể dùng như **gợi ý định tuyến đến issuer**, nhưng nó vẫn do caller lựa chọn. Quy trình an toàn:

1. Đọc tenant request và chuẩn hóa cú pháp.
2. Kiểm tra tenant có trong registry **server-managed**.
3. Từ registry lấy đúng issuer và JWKS URI tin cậy.
4. Chọn manager/decoder tương ứng, không dynamic discovery từ arbitrary host.
5. Verify token signature, `iss`, `aud`, expiry/not-before.
6. Bind authenticated tenant claim và subject với requested tenant.
7. Kiểm tra current DB membership, owner, ACL và action scope.
8. Chỉ sau đó xử lý tài nguyên tenant.

**Ví dụ nguy hiểm:**

~~~java
String issuer = "https://" + tenantFromRequest + "/oauth2";
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

Nếu attacker điều khiển `tenantFromRequest`, code có thể tải metadata/JWKS từ URL không được tin cậy, dẫn tới **SSRF hoặc trust expansion**.

**Registry tường minh:**

~~~java
Map<String, String> tenantIssuers = Map.of(
    "tenant-a", "https://id.example.test/realms/retail",
    "tenant-b", "https://id.example.test/realms/enterprise"
);

String issuer = tenantIssuers.get(requestedTenant);
if (issuer == null) {
    // Reject unknown tenant.
}
~~~

Đoạn này chỉ chọn issuer có trong registry. Token vẫn phải được manager tương ứng **xác minh**. Không coi `issuer != null` là authorization thành công.

### 8.1. Khi nhiều tenants dùng cùng issuer

Nếu mọi tenant đều dùng:

~~~text
issuer = https://id.example.test/realms/common
tenant_id = tenant-a, tenant-b, tenant-c
~~~

thì không cần tạo decoder khác nhau cho mỗi tenant khi signature, issuer, audience và profile giống hệt nhau. Có thể verify JWT bằng một decoder rồi thực thi tenant membership/ACL trong service.

Đừng tăng complexity multi-issuer chỉ vì hệ thống multi-tenant. **Multi-tenant data isolation** và **multi-issuer credential trust** là hai vấn đề riêng.

### 8.2. Khi một tenant chấp nhận nhiều issuers

Enterprise federation có thể cho một tenant tin cả corporate issuer và partner issuer. Registry lúc này cần **tập issuers tin cậy cho tenant đó**. Một token chỉ được chấp nhận nếu issuer nằm trong tập được phê duyệt, audience đúng và principal thật sự có entitlement trong tenant.

Không dùng giá trị tenant claim như lời bảo đảm rằng mọi issuer đều được tin.

## 9. Phòng token substitution và identity collision

### 9.1. `iss` đúng nhưng `aud` sai

Token:

~~~json
{
  "iss": "https://id.example.test/realms/retail",
  "aud": ["billing-api"],
  "scope": "invoices.read"
}
~~~

Không được dùng gọi `/api/orders/**`, dù cùng issuer ký và token còn hạn. Resource Server phải kiểm tra intended audience.

### 9.2. `sub` giống nhau từ hai issuers

Hai issuers có thể phát:

~~~text
Retail issuer:     sub = 123
Enterprise issuer: sub = 123
~~~

Đó **không nhất thiết** là cùng một người hoặc service account. Sai khi dùng một `sub` duy nhất làm global key trong database.

An toàn hơn:

~~~text
identity key = (validated issuer, subject)
~~~

hoặc ánh xạ cặp đó sang một internal account ID thông qua registry tin cậy.

Nếu bỏ phần issuer, token enterprise với `sub=123` có thể truy cập dữ liệu thuộc retail subject `123`. Đây là **cross-issuer identity collision**.

### 9.3. Role trùng tên khác ý nghĩa

Hai issuers có thể có:

~~~json
{"roles": ["ADMIN"]}
~~~

Nhưng `ADMIN` trong Retail có thể chỉ là quản trị cửa hàng; trong Enterprise có thể là quản trị nhân sự. Không tự map cả hai thành `ROLE_GLOBAL_ADMIN`.

Một hợp đồng mapping nên có:

| Issuer | Claim | Authority có thể cấp | Giới hạn |
|---|---|---|---|
| Retail | `scope` | `SCOPE_orders.read` | Token dành cho Orders |
| Enterprise | `scp` | `SCOPE_orders.read` nếu cùng scope contract | Đúng profile của enterprise |
| Retail | `app_roles` | `ROLE_STORE_MANAGER` qua allowlist | Không thành global admin |
| Enterprise | `groups` | Chỉ qua mapping được duyệt | Không lấy tên group làm role |
| Bất kỳ | `tenant_id` | Không tự thành global authority | Dùng trong tenant policy |

**Scope cùng chuỗi giữa hai issuers** chỉ có cùng ý nghĩa khi cả hai AS đã chấp nhận **cùng hợp đồng quyền của API**. Nếu không, cần namespace riêng hoặc policy tường minh.

## 10. OIDC Login/session và Bearer Resource Server không cùng một flow

### 10.1. Browser OIDC Login

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

Ứng dụng đóng vai trò **OAuth2/OIDC Client**, thường có browser login redirect, session cookie và principal như `OidcUser`.

### 10.2. API Bearer Resource Server

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()));
~~~

Ứng dụng đóng vai trò **Resource Server**, nhận OAuth access token và thường trả **401 Bearer challenge** khi authentication thất bại.

| Khía cạnh | Browser OIDC Login | Bearer Resource Server |
|---|---|---|
| Credential request | Session/cookie | Bearer access token |
| Khi thiếu authentication | Login redirect/session flow | 401 `WWW-Authenticate: Bearer` |
| Chống CSRF | Quan trọng khi dùng cookie | Bearer-only API có thể cân nhắc disable |
| Principal | `OidcUser`/login Authentication | `JwtAuthenticationToken` hoặc `BearerTokenAuthentication` |
| Phạm vi token | ID Token phục vụ OIDC Client | Access Token dành cho API |

**ID Token không phải API access token.** Không cho Resource Server chấp nhận ID Token chỉ vì nó là JWT ký đúng bởi cùng issuer; audience/token type/profile có thể khác.

### 10.3. Browser chain cần cả authorization redirect và callback

Một đoạn cấu hình có vẻ hợp lý:

~~~java
@Bean
@Order(3)
SecurityFilterChain console(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/console/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("SUPPORT"))
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

**Đây không phải cấu hình login đầy đủ để copy nguyên trạng.** OIDC Login thường dùng endpoints như:

~~~text
/oauth2/authorization/{registrationId}
/login/oauth2/code/{registrationId}
~~~

Chúng nằm **ngoài `/console/**` theo default. Nếu console chain không match callback, fallback chain có thể deny, khiến login hỏng.

Giải pháp: thiết kế matcher bao phủ authorization endpoint/callback hoặc tùy chỉnh login paths theo vùng console, đồng thời đăng ký redirect URI tương ứng ở IdP. Test đầy đủ login redirect, callback, logout và CSRF, không chỉ GET trang console.

## 11. mTLS và API key trong hệ thống có nhiều cơ chế

Ví dụ contract:

~~~text
/internal/jobs/** -> mTLS/service identity
/api/orders/**    -> JWT access token
/console/**       -> OIDC session
~~~

Một service-to-service API có thể dùng mTLS client certificates, nhưng:

- Certificate phải được xác minh bởi TLS stack/trusted CA, đúng client usage và certificate policy.
- Khi gateway terminate TLS, backend chỉ có thể tin forwarded identity khi gateway xóa headers client tự giả, kênh gateway→backend được bảo vệ và backend không thể bị gọi trực tiếp.
- API key có lifecycle/rate limit và revocation riêng; không tự biến nó thành OAuth scope.
- Service identity không đồng nghĩa danh tính người dùng khi service thực hiện delegated actions.

**Không bật “nếu mTLS thiếu thì chấp nhận X-Client-Cert header tùy ý”**. Đó là đường downgrade.

## 12. Tránh “try every provider until success”

Một anti-pattern:

~~~text
JWT verification thất bại
    -> thử opaque introspection
    -> nếu thất bại thử browser session
    -> nếu thất bại thử API key
    -> cái nào thành công thì cấp quyền
~~~

Không mặc định triển khai thế này vì:

1. Signature failure của JWT có thể biến thành cơ hội đi qua cơ chế khác.
2. Token dành cho audience khác có thể được một provider không chặt chẽ chấp nhận.
3. Không rõ scope/role semantics của principal cuối cùng.
4. Response 401/403 không nhất quán.
5. Có thể tăng tải introspection hoặc tạo side channel.
6. Client có thể chọn đường xác thực yếu hơn.

Một endpoint hỗ trợ nhiều mechanisms không phải lúc nào cũng sai. Nhưng cần có **routing policy rõ ràng**, danh sách providers được phê duyệt, xử lý trường hợp credentials xung đột và negative tests chứng minh không thể downgrade. Khi không có lý do mạnh, **tách endpoint** dễ audit hơn.

## 13. Authorization theo HTTP method không được bỏ sót

Một JWT chain có:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
)
~~~

có thể cho POST chưa khai báo chỉ với một token authenticated; đó là rủi ro nếu API có mutation endpoints.

Nên mô tả action-specific scopes:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        HttpMethod.POST, "/api/orders/*/approve"
    ).hasAuthority("SCOPE_orders.approve")
    .requestMatchers(
        HttpMethod.POST, "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .requestMatchers(
        HttpMethod.GET, "/api/orders/**"
    ).hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

Đặt rule đặc thù trước rule rộng, kiểm tra path root/trailing slash và tất cả methods. `hasAuthority` so chính xác chuỗi; không dùng `contains("read")`, không tự map `orders.read.all` thành `orders.read`.

Local entitlement và owner/tenant ACL vẫn có thể phải đúng **đồng thời** với scope:

~~~text
ALLOW_APPROVE =
    valid token with correct issuer/audience
    AND SCOPE_orders.approve
    AND current local entitlement APPROVE
    AND tenant and order ACL allow action
~~~

Không biến thành `SCOPE_orders.approve OR LOCAL_APPROVE` khi hợp đồng yêu cầu cả hai.

## 14. Phản hồi lỗi đúng theo từng cơ chế

| Tình huống | HTTP thường gặp | Lưu ý |
|---|---|---|
| Không gửi Bearer vào protected API | 401 | Bearer challenge, thường không có error |
| JWT signature sai hoặc hết hạn | 401 | `invalid_token` khi phù hợp RFC 6750 |
| JWT issuer chưa tin | 401 | Không dynamic trust issuer |
| JWT audience sai | 401 | Token không dành cho API |
| Opaque token `active:false` | 401 | Từ chối token |
| Opaque introspection timeout | Lỗi infrastructure theo cấu hình | Không fail open |
| Token hợp lệ thiếu scope | 403 | `insufficient_scope` nếu đúng loại lỗi |
| Token đúng scope nhưng sai tenant | 403/404 theo policy | Không tự nói thiếu OAuth scope |
| Browser chưa login | Redirect hoặc browser policy | Không ép thành Bearer API JSON |
| Unknown route | Fallback deny | Không mở mặc định |

Với Servlet Resource Server, Spring Security có `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` để hỗ trợ RFC 6750. Khi thêm JSON Problem Details, **không làm mất `WWW-Authenticate`**, và HTTP status thật phải trùng `body.status`.

Không áp Bearer handler toàn cục lên browser login flow; cũng không áp login redirect entry point lên API machine clients.

## 15. Kiểm thử bằng MockMvc và JWT Test

### 15.1. Bốn nhóm tests cần có

- **Chain selection:** URL nào vào JWT, opaque, browser hoặc fallback.
- **Authentication:** chữ ký, issuer, audience, expiry và introspection status.
- **Authorization:** scopes, role mapping, tenant/ACL.
- **End-to-end qua gateway:** URL rewrites, host headers, CORS, redirects, mTLS forwarding.

Test chỉ với credentials hợp lệ không phát hiện nhầm trust domain. **Negative tests** là trọng tâm của hệ thống nhiều cơ chế.

### 15.2. Test scope bằng Spring Security Test

Với Servlet `MockMvc`, helper `jwt()` có thể tạo Authentication giả lập:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;

import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void missingReadScopeIsForbidden() throws Exception {
    mvc.perform(
        get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            ))
    )
        .andExpect(status().isForbidden());
}
~~~

`mvc` là `MockMvc` đã khởi tạo trong test context. Helper `jwt()` **không tự xác minh chữ ký, issuer, audience hoặc JWKS**. Nó chỉ hữu ích để kiểm tra authorization rules.

### 15.3. Test issuer lạ

~~~text
Route: /api/orders/42
iss: https://untrusted.example.test
aud: orders-api
Signature: hợp lệ đối với key của untrusted issuer
Expected: Reject, không tải metadata/JWKS từ issuer lạ
~~~

Token có signature đúng của một issuer không nằm trong allowlist vẫn phải bị từ chối.

### 15.4. Test đúng issuer nhưng sai audience

~~~text
Route: /api/orders/42
iss: trusted retail issuer
aud: billing-api
Expected: Reject
~~~

Nếu test này thành công, audience validation có thể đang thiếu. Đây là một cách phát hiện **token substitution**.

### 15.5. Test hai issuers có cùng `sub`

~~~text
Retail issuer: sub=123
Enterprise issuer: sub=123
Expected: identity mapping không nhập hai principals làm một
~~~

Có thể test database ownership bằng identity key `(iss, sub)` thay vì `sub` đơn lẻ.

### 15.6. Test cross-tenant

~~~text
URL tenant: tenant-b
JWT tenant_id: tenant-a
JWT scope: orders.read
Expected: Deny
~~~

Các biến thể:

- Token tenant đúng nhưng database membership đã bị revoke → deny.
- Token tenant đúng nhưng order thật thuộc tenant khác → deny.
- Tenant issuer registry chỉ cho phép Retail, JWT từ Enterprise → deny.
- Cross-tenant delegation hợp lệ → chỉ cho phép đúng tenant/actions trong phạm vi grant.
- Header `X-Tenant-Id` tự đổi → không nâng quyền.

### 15.7. Test endpoint token crossover

~~~text
Partner opaque token -> /api/orders/**
Expected: không fallback sang partner introspection

Orders JWT -> /api/partners/**
Expected: không fallback sang Orders JWT decoder
~~~

### 15.8. Test browser và fallback

~~~text
Unauthenticated GET /api/orders/42
Expected: 401 Bearer challenge

Unauthenticated GET /console/orders
Expected: Browser login policy/redirect

OIDC callback /login/oauth2/code/...
Expected: đi đúng login chain

Unknown URL không match chains cụ thể
Expected: fallback deny
~~~

### 15.9. Ma trận kiểm thử tổng hợp

| Case | Kết quả bảo mật |
|---|---|
| JWT đúng issuer, aud, scope và tenant | Qua authentication/authorization |
| JWT issuer ngoài allowlist | 401 |
| JWT đúng issuer nhưng sai audience | 401 |
| JWT expired/sai signature | 401 |
| JWT hợp lệ thiếu scope | 403 |
| JWT có `orders.read` nhưng sai tenant | Deny |
| JWT issuer Enterprise dùng sub trùng Retail | Không trộn identity |
| Partner opaque token gọi JWT route | Không fallback |
| Orders JWT gọi opaque route | Không fallback |
| Partner AS outage | Fail closed |
| Cross-tenant delegation không có grant | Deny |
| JWT custom `roles=["ADMIN"]` từ issuer không có quyền cấp global admin | Không tạo `ROLE_GLOBAL_ADMIN` |
| API request thiếu token | Bearer challenge |
| Browser login callback | Không rơi vào fallback deny |
| Unknown endpoint | Default deny |
| CORS preflight hợp lệ | Theo CORS policy, không ép Bearer authentication sai |
| Gateway rewrite URL | Chọn đúng chain và đúng scope |

**Đừng hiểu “qua authorization” đồng nghĩa HTTP 200**: controller có thể trả 404/409 từ logic nghiệp vụ.

## 16. Vận hành: quản lý trusted issuers và tenant registry

Một registry có thể chứa:

~~~yaml
trusted-issuers:
  retail:
    issuer: https://id.example.test/realms/retail
    jwks-uri: https://id.example.test/realms/retail/protocol/openid-connect/certs
    allowed-audiences:
      - orders-api
    allowed-tenants:
      - tenant-a
  enterprise:
    issuer: https://id.example.test/realms/enterprise
    jwks-uri: https://id.example.test/realms/enterprise/protocol/openid-connect/certs
    allowed-audiences:
      - orders-api
    allowed-tenants:
      - tenant-b
~~~

**Đây là format ứng dụng tự định nghĩa**, không phải Spring Boot property built-in. Registry là **security configuration** và phải được quản lý như một trust anchor.

Yêu cầu vận hành:

1. Chỉ người/role được phê duyệt có thể thêm hoặc thay đổi trusted issuer.
2. Không cho tenant admin tự thêm arbitrary internet JWKS endpoint rồi mặc nhiên được tin.
3. Xác thực mọi issuer/JWKS URI, chống SSRF.
4. Có audit trail và review cho thay đổi tenant-to-issuer mapping.
5. Theo dõi key rotation, JWKS fetch failures và introspection timeout.
6. Áp dụng cache policy và timeouts theo từng provider.
7. Test regression cho issuers/tenants bị xóa hoặc thay đổi.
8. Không cache principal/tenant entitlement quá lâu nếu cần thu hồi quyền nhanh.

### 16.1. Metrics nên phân biệt chain và issuer

Các dimensions hữu ích:

| Dimension | Vì sao cần |
|---|---|
| `security_chain` | Biết request rơi vào JWT/opaque/browser/fallback |
| `trusted_issuer_alias` | Thống kê issuer đã được verify |
| `tenant_alias` | Chẩn đoán tenant policy có kiểm soát cardinality |
| `authentication_failure` | Signature, expired, wrong issuer/audience, inactive |
| `authorization_failure` | Scope, role, tenant, ACL |
| `jwks_latency` | Phụ thuộc key service |
| `introspection_latency` | Phụ thuộc Authorization Server của đối tác |
| `fallback_deny_rate` | Phát hiện routes chưa được khai báo |
| `cross_tenant_deny_rate` | Phát hiện lỗi quyền và thử truy cập sai tenant |

Không ghi raw Bearer token, refresh token, ID Token hoặc client secret vào log/traces/metric labels. Không tin issuer URI do token tự khai làm một label không giới hạn; dùng alias của registry sau xác minh.

## 17. Các lỗi thiết kế thường gặp

### Lỗi 1 — Broad chain đứng trước protected chain

`/api/**` với `permitAll` có thứ tự trước `/api/admin/**` khiến admin chain không chạy. Sửa `securityMatcher` và `@Order`, thêm negative tests.

### Lỗi 2 — Chỉ nhìn `iss` rồi cấp quyền

`iss` trước JWS verification là dữ liệu chưa tin. Chỉ dùng hint trong trusted allowlist; manager phải xác minh signature và issuer.

### Lỗi 3 — Quên audience

Một token cho `billing-api` có thể được issuer hợp lệ ký nhưng không được dùng ở `orders-api`.

### Lỗi 4 — Tự lấy JWKS URI từ JWT hoặc tenant String

Mở đường SSRF/trust expansion. JWKS/issuer đến từ trusted server-side registry, không từ arbitrary request.

### Lỗi 5 — Dùng `sub` làm global identity key

`sub` có thể trùng giữa issuers. Dùng `(issuer, subject)` hoặc internal mapping tin cậy.

### Lỗi 6 — Scope/role cùng tên giữa issuers được xem tương đương mặc định

Chỉ tương đương khi authorization contract chung đã được định nghĩa; không map tùy ý thành global admin.

### Lỗi 7 — Tenant header là bằng chứng quyền

`X-Tenant-Id`/path/Host có thể bị caller giả. Phải bind với token đã xác minh và DB membership.

### Lỗi 8 — Dùng mọi provider cho mọi endpoint

Tạo nguy cơ downgrade, cross-audience token substitution và lỗi 401/403 khó hiểu. Tách routes hoặc dùng resolver đã được thiết kế rõ.

### Lỗi 9 — OIDC ID Token được API chấp nhận như access token

ID Token hướng tới OIDC client; API cần access token đúng audience/profile.

### Lỗi 10 — Browser login chain quá hẹp

`/console/**` không bao phủ default OAuth2 authorization/callback endpoints; login có thể rơi vào fallback deny. Thiết kế lại matchers/paths và test callbacks.

### Lỗi 11 — `anyRequest().authenticated()` làm mở nhầm mutation routes

Nếu POST chưa có write scope, chỉ cần authenticated token có thể đi qua URL policy. Đặt action-specific scopes và default deny khi cần.

### Lỗi 12 — Authentication thay thế object-level authorization

Token có `orders.read` không tự cho phép đọc mọi tenants. Service/repository vẫn phải kiểm tra owner, tenant, current entitlement và ACL.

## 18. Checklist cho production

- [ ] Định nghĩa credential contract của từng endpoint group.
- [ ] Security chains có matchers và `@Order` không chồng lấn sai.
- [ ] Có fallback deny cho paths ngoài hợp đồng.
- [ ] Không chọn strategy theo header/query do client tự khai mà không có trust boundary.
- [ ] Không fallback opaque/session khi JWT verify thất bại ngoài contract.
- [ ] Issuer allowlist cố định hoặc registry được quản trị an toàn.
- [ ] JWT manager xác minh signature, issuer, audience, exp/nbf và token profile.
- [ ] Không dynamic JWKS fetch từ arbitrary issuer URI/`jku`.
- [ ] Identity key phân biệt issuers, không chỉ dựa `sub`.
- [ ] Authority mapping theo issuer, không tự tạo global admin.
- [ ] Tenant request được bind với validated principal và membership.
- [ ] Repository filters theo tenant/owner, không chỉ kiểm scope.
- [ ] Browser OIDC login có authorization/callback routes đúng chain.
- [ ] CSRF/session policy đúng cho mỗi chain, không disable toàn cục bừa bãi.
- [ ] 401/403/redirect theo đúng Bearer hoặc browser client type.
- [ ] Có negative tests issuer lạ, aud sai, tenant mismatch, crossover và downgrade.
- [ ] Secrets, token và trust registry không bị lộ vào log.
- [ ] Có monitoring issuer/JWKS/introspection/fallback/tenant denial.

## 19. Kết luận

Trong hệ thống nhiều cơ chế xác thực, **tách endpoint, issuer và tenant** là ba việc khác nhau:

- **Endpoint** chọn **authentication mechanism** phù hợp: JWT, opaque introspection, browser session hoặc một giao thức nội bộ.
- **Issuer** chọn **trusted decoder/manager và bộ validators**. `iss` chưa xác thực chỉ có thể làm routing hint trong allowlist.
- **Tenant** xác định **phạm vi dữ liệu và entitlement**, phải đối chiếu với principal đã được xác thực và dữ liệu nghiệp vụ.

Trong Spring Security Servlet, dùng **`SecurityFilterChain` + `securityMatcher`/`@Order`** để tách endpoints. Dùng **`JwtIssuerAuthenticationManagerResolver` với trusted issuers** khi cùng API nhận JWT từ nhiều Authorization Servers. Dùng **tenant/ACL policy** ở service/repository khi khác biệt nằm ở quyền trên dữ liệu.

Mục tiêu không phải hỗ trợ càng nhiều cách đăng nhập càng tốt, mà là **mỗi request chỉ đi qua một chiến lược có chủ đích, mỗi credential được xác minh đầy đủ, và không có đường đi vòng qua trust boundary**.

### Tài liệu tham khảo

- [Spring Security Reference — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security Reference — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Multi-tenancy for Resource Servers](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security API — AuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManagerResolver.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)

