# Nhận diện tenant từ nguồn tin cậy và tách tenant khỏi dữ liệu chưa xác minh — Spring Security WebFlux

## Mục tiêu

Bài học thuộc **Spring Security – reactive**, chủ đề cha **Gateway và nhiều tenant**. Sau bài này, bạn có thể:

1. Phân biệt **requested tenant** do client chỉ định, **verified tenant** rút ra từ danh tính đã được xác thực và **resource tenant** nằm trên bản ghi dữ liệu.
2. Phân loại độ tin cậy của Host, path, query param, cookie, HTTP headers, các claim JWT trước/sau signature verification, opaque token introspection và server-side tenant registry.
3. Hiểu tại sao `iss` chưa xác minh chỉ được dùng để chọn một verifier **đã nằm trong allowlist**, tuyệt đối không trở thành tenant authority hoặc JWKS URL tùy ý.
4. Cấu hình multi-issuer với `JwtIssuerReactiveAuthenticationManagerResolver`, `JwtReactiveAuthenticationManager`, `NimbusReactiveJwtDecoder` và các validators `iss`, `aud`, `exp`, `nbf`.
5. Sau khi xác thực Bearer, đối chiếu issuer→tenant với claim `tenant_id` đã xác minh, tenant được yêu cầu trong URL và quyền scope.
6. Chống giả mạo `X-Tenant-ID`, `X-Verified-Tenant`, `X-Forwarded-Host`; không dùng header nội bộ làm proof nếu downstream không xác thực gateway workload.
7. Viết Java 17+ / Spring Boot 3.5.16 WebFlux gateway mẫu có downstream `WebClient` cố định, rồi kiểm thử bằng JWT RS256, hai JWKS riêng, `MockWebServer` và `WebTestClient`.
8. Áp dụng tenant-aware query/ACL, issuer+subject identity namespace, mTLS, signed internal assertions, logging, cache, SSO sessions và opaque introspection.

> **Phạm vi:** demo là một ứng dụng **WebFlux Resource Server đóng vai trò gateway bảo vệ HTTP**; nó không dùng Spring Cloud Gateway starter. Mục 12 giải thích cách áp dụng nguyên tắc cho Spring Cloud Gateway thực. Demo dùng keys và server HTTP trên loopback **chỉ cho kiểm thử**, không phải một thiết kế hạ tầng production.

---

## 1. Ba loại tenant không được đánh đồng

Giả sử một client gửi:

```http
GET /api/tenants/alpha/documents/invoice-42 HTTP/1.1
Host: alpha.example.test
X-Tenant-ID: alpha
X-Verified-Tenant: alpha
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Tại thời điểm mới nhận request, các thông tin đều có thể bị client kiểm soát:

- `alpha` trong URL chỉ là **requested tenant**, mô tả tài nguyên client muốn truy cập.
- `Host`/subdomain có thể định tuyến tại edge; không tự chứng minh user thuộc tenant alpha.
- `X-Tenant-ID` và `X-Verified-Tenant` chỉ là chuỗi HTTP header. Tên “Verified” không mang bằng chứng mật mã.
- Bearer token có thể là JWT, nhưng payload decode được **chưa được xác thực**.
- Bản ghi database có `tenant_id=alpha` chỉ là **resource tenant**, không xác minh quyền caller.

Chỉ sau khi Spring Security xác thực Bearer token, đúng issuer/audience/chữ ký/thời gian, và ứng dụng kiểm tra membership/tenant policy, ta mới có **verified tenant**.

```text
                         UNSIGNED REQUEST DATA
                         ---------------------
Client: Host/path/X-Tenant-ID/JWT bytes
                |
                v
Ingress: TLS, hostname allowlist, strip forged headers
                |
                v
Spring Security Reactive Resource Server
  - JWT issuer hint -> CHỈ chọn verifier từ allowlist
  - signature / iss / aud / exp / nbf validation
  - scope -> SCOPE_... authority
                |
                v
VERIFIED Authentication (Jwt principal)
                |
                v
Tenant policy
  - issuer -> tenant đã được ops duyệt
  - tenant_id claim đã ký phù hợp registry?
  - requested tenant == verified tenant?
  - caller được phép tài nguyên này?
                |
                v
Trusted downstream / tenant-scoped database
                |
                v
HTTP 200 / 401 / 403 / 404
```

**Tách bạch lỗi:**

- **401:** không có hoặc chưa thể xác thực JWT, sai chữ ký, issuer không được tin, audience sai, token hết hạn.
- **403:** token đã xác thực nhưng thiếu scope, tenant claim hoặc path tenant không phù hợp quyền.
- **404:** tài liệu không tồn tại hoặc hệ thống chủ động che giấu sự tồn tại của tài nguyên không thuộc quyền; phải có policy nhất quán.

## 2. Phân loại nguồn tin cậy

| Nguồn thông tin | Trước khi kiểm tra | Có thể dùng để làm gì? |
| --- | --- | --- |
| `/tenants/alpha` | Untrusted selector | Chỉ ra tenant client yêu cầu; phải so với quyền |
| `?tenant=alpha` / JSON body | Input của client | Validation nghiệp vụ; không quyết định identity |
| `X-Tenant-ID` / `X-Verified-Tenant` | Untrusted header | Bỏ/ghi đè ở trust boundary; không trực tiếp cấp quyền |
| `Host` / subdomain | Request-controlled | Routing hint sau host allowlist, không bằng chứng membership |
| `Forwarded`/`X-Forwarded-*` | Untrusted khi nhận từ Internet | Chỉ sử dụng nếu proxy đáng tin sanitize |
| JWT claim `iss` chưa verify | Untrusted hint | Tra cứu một verifier đã được allowlist |
| JWT claim `tenant_id` chưa verify | Untrusted payload | Không dùng làm identity/cache/access predicate |
| `Jwt` từ verified Authentication | Đã qua signature và validator | Kiểm claim dưới hợp đồng IdP và tenant entitlement |
| Opaque introspection result từ trusted IdP | Đã kiểm active | Áp issuer/audience/tenant policy trước cấp quyền |
| Registry issuer→tenant của vận hành | Server-owned config | Map issuer/JWKS/tenant tin cậy |
| Tenant ID trong DB row | Resource attribute | So với tenant đã verify trong query |
| Header nội bộ do gateway tạo | Tin cậy **có điều kiện** | B phải xác thực workload/source của gateway |

**Hai lớp cần thiết:** gateway kiểm tra danh tính/tenant/scope, backend hoặc database vẫn kiểm tra tenant-of-row và quyền owner/ACL. Một trong hai bị bỏ sót có thể gây cross-tenant data leak.

## 3. JWT chưa verify không chứng minh tenant

Ví dụ JWT payload:

```json
{
  "iss": "https://issuer.example.invalid/alpha",
  "sub": "alice",
  "aud": ["api://tenant-gateway"],
  "tenant_id": "alpha",
  "scope": "docs.read",
  "exp": 1893456000
}
```

Ai cũng có thể dựng một chuỗi JWT chứa claims trên. Payload Base64URL không được bảo vệ cho tới khi chữ ký JWS được verify với **đúng public key của issuer tin cậy**.

### Thứ tự đúng trong multi-issuer Resource Server

1. Đọc `iss` chưa verify **chỉ để tìm cấu hình verifier** trong allowlist.
2. Issuer không được duyệt → fail closed; không tự gọi discovery/JWKS của host tùy ý.
3. Verifier tương ứng kiểm chữ ký, `iss` đúng chính xác, `aud` của API, `nbf` và `exp`.
4. Chỉ sau đó Authentication được tạo; code có thể đọc `@AuthenticationPrincipal Jwt`.
5. Ánh xạ verified issuer và verified tenant claims vào tenant policy.
6. Đối chiếu tenant được request trong URL/host với verified membership.
7. Kiểm tra scope, quyền bản ghi/owner và ranh giới propagation.

Spring Security 6.5 có API:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                        "https://idp.example.test/alpha",
                        "https://idp.example.test/beta");
```

Kỹ thuật này dùng allowlist làm trust boundary. **Không hiểu sai rằng đọc `iss` rồi chọn verifier đã là authentication thành công.** Nếu signing key không khớp hoặc token sai audience, nó vẫn phải bị từ chối.

### Anti-pattern: tạo decoder từ issuer do attacker khai

```java
// Không làm: raw iss chưa verify có thể trỏ tới máy chủ attacker.
String issuer = parseUnverifiedJwt(token).get("iss");
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(issuer);
```

Đây là fragment **phản ví dụ**, không có hàm `parseUnverifiedJwt(...)` để chạy. Nếu gọi metadata từ arbitrary issuer, attacker có thể lợi dụng SSRF hoặc tự tạo issuer/JWKS riêng rồi được server tin nhầm. Ngược lại, việc chọn một `ReactiveAuthenticationManager` từ map immutable đã được admin duyệt không biến raw claim thành authority.

### Khi một IdP đại diện nhiều tenant

Không phải luôn có quy tắc một issuer = một tenant. Có IdP cấp nhiều organization/tenant dưới cùng issuer. Khi đó:

- Dùng signature + issuer + audience validators chung.
- Đọc verified `tenant_id` hoặc organization memberships từ Authentication.
- Kiểm chứng tenant ID tồn tại trong registry và caller có entitlement vào tenant được yêu cầu.
- Một user có quyền nhiều tenant phải có cơ chế chọn active tenant **được authorize lại**.
- Không để client tự bổ sung một tenant vào token/session/registry thông qua request.

Lab dùng **hai issuer, mỗi issuer một tenant** để thấy rõ hai ranh giới.

## 4. Registry đáng tin là gì?

Server-side tenant registry do vận hành quản lý:

| Tenant | Canonical issuer | JWKS URL |
| --- | --- | --- |
| alpha | `https://issuer.example.invalid/alpha` | Cấu hình JWKS được duyệt cho alpha |
| beta | `https://issuer.example.invalid/beta` | Cấu hình JWKS được duyệt cho beta |

Registry không được tự thêm issuer dựa vào Host, `X-Issuer`, token claims hay tenant vừa xuất hiện trong path. Nếu hỗ trợ dynamic onboarding, cần một control plane có authentication, approval, validation của issuer domain/JWKS và audit.

Với hệ thống có nhiều issuer, subject ID có thể trùng. Hai token cùng `sub=alice` từ alpha/beta không nhất thiết cùng một user. Khóa logical identity nên chứa `issuer + subject`; các token/cache liên quan quyền tenant thường cần `issuer + tenant + subject + scope/policy version`.

```text
Identity key:      (issuer, subject)
Data key:          (tenant_id, document_id)
Cache permission:  (issuer, tenant_id, subject, resource, policy_version)
```

Không cache profile/document chỉ theo `sub` hoặc `documentId` nếu nhiều tenants dùng chung namespace.

## 5. Host, path và proxy headers vẫn là request selectors

### Path-based tenant

```http
GET /api/tenants/beta/documents/doc1
Authorization: Bearer <token-da-verify-thuoc-alpha>
```

Client yêu cầu tài liệu của beta. Nếu JWT xác thực chỉ thuộc alpha, kết quả phải từ chối, không vì path là beta mà “đổi tenant” tự động.

### Header giả

```http
X-Tenant-ID: beta
X-Verified-Tenant: beta
X-Forwarded-Host: beta.example.invalid
```

Các header này không có giá trị chứng minh membership. Bất kỳ client nào cũng có thể tự viết chúng. Ngay cả khi gateway thấy Host thuộc domain cho phép, Host chỉ xác định endpoint **được yêu cầu**; membership phải dựa vào Authentication.

### Reverse proxy

Khi TLS kết thúc ở reverse proxy, `Forwarded`/`X-Forwarded-*` có thể giúp ứng dụng khôi phục external URI. Tuy nhiên proxy phải strip headers không tin cậy từ client và ghi mới theo connection thực; trusted proxy policy **không tự tạo trusted tenant policy**.

### SSO session/cookie

Cookie `active_tenant=beta` không đủ. Thao tác switch tenant phải kiểm membership/role của user authenticated rồi mới lưu active tenant trong server session. Nếu mất session hoặc membership bị revoke, phải đánh giá lại. Không coi một query param/cookie là chứng cứ đăng nhập.

## 6. Tenant ở tầng dữ liệu: chống IDOR

Ở gateway có thể đã có:

```text
verified issuer = alpha
verified tenant = alpha
scope = docs.read
requested tenant = alpha
```

Nhưng user Alice vẫn có thể không được xem tài liệu của Bob trong tenant alpha.

Không dùng chỉ `docId`:

```java
// ANTI-PATTERN: thiếu tenant/ownership predicate.
return documentRepository.findById(docId);
```

Ví dụ ý tưởng tốt hơn với R2DBC:

```java
// Fragment, documentRepository thuộc ứng dụng nghiệp vụ thật.
return documentRepository
        .findByTenantIdAndDocumentId(verifiedTenantId, docId)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

Nếu document cần owner/ACL, truy vấn nên bao gồm điều kiện owner hoặc join ACL phù hợp. Không dùng `tenant_id` lấy trực tiếp từ header. Khi dùng PostgreSQL RLS, cấu hình tenant context theo đúng transaction/connection lifecycle để tránh rò context giữa requests khi connection pool reuse.

**Gateway không thay trách nhiệm kiểm quyền ở data service**, nhất là khi backend có thể được gọi từ job, event consumer hoặc một gateway khác.

---

## 7. Project Spring Boot WebFlux chạy độc lập

Project mô phỏng một WebFlux gateway bảo vệ tenant routes, rồi gọi downstream qua WebClient. Spring Cloud Gateway routing engine **không** nằm trong project này; mục 12 có fragment dành cho Spring Cloud Gateway.

Điểm thực hành:

- Hai issuer alpha/beta được config sẵn.
- Hai JWT verifiers riêng, mỗi cái có JWKS URI và issuer validator riêng.
- Audience của gateway là `api://tenant-gateway`; scope yêu cầu `docs.read`.
- Tenant policy chỉ tạo `VerifiedTenant` sau khi JWT đã xác thực và tenant/path khớp.
- Downstream nhận `X-Verified-Tenant`/`X-Verified-Subject` từ gateway **trong test loopback**; không copy raw inbound headers.
- WebClient dùng path cố định, không follow redirect, không nhận arbitrary outbound URL.

### 7.1. Cấu trúc file

```text
trusted-tenant-gateway/
  settings.gradle
  build.gradle
  src/main/java/example/tenantgateway/
    TenantGatewayApplication.java
    TrustedTenantCatalog.java
    TenantSecurityConfiguration.java
    TenantAccessPolicy.java
    TrustedDownstreamClient.java
    TenantGatewayController.java
  src/main/resources/
    application.yml
  src/test/java/example/tenantgateway/
    TenantGatewayIntegrationTest.java
```

### 7.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'trusted-tenant-gateway'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

JDK 17+ và Gradle Wrapper tương thích là bắt buộc. Spring Security JOSE/JWT classes đến từ Resource Server starter dependencies. Không thêm MVC starter khi muốn Reactor Netty/WebFlux thuần.

Spring Boot 3.5.16 là **bản OSS cuối của nhánh 3.5**, đã hết OSS support; production nên chọn dòng còn được hỗ trợ và cập nhật bản vá.

### 7.3. application.yml

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080

security:
  tenants:
    alpha:
      issuer: https://issuer.example.invalid/alpha
      jwk-set-uri: https://issuer.example.invalid/alpha/jwks
    beta:
      issuer: https://issuer.example.invalid/beta
      jwk-set-uri: https://issuer.example.invalid/beta/jwks

downstream:
  base-url: ${DOWNSTREAM_BASE_URL:https://profiles.example.invalid}
  allow-insecure-loopback-for-tests: false
```

Namespace `security.tenants.*` là **custom app config** do ta tự khai báo, không phải Boot Resource Server property có sẵn. Các địa chỉ `.invalid` không hoạt động bên ngoài test; test override JWKS/downstream bằng MockWebServer local qua `@DynamicPropertySource`.

Trong production, phải thay issuer/JWKS bằng IdP thật, HTTPS/TLS certificate verification, egress rules và JWKS rotation policy. `allow-insecure-loopback-for-tests` chỉ là công tắc cho test localhost, không bật ở môi trường Internet.

### 7.4. Main class

**`src/main/java/example/tenantgateway/TenantGatewayApplication.java`:**

```java
package example.tenantgateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantGatewayApplication.class, args);
    }
}
```

### 7.5. TrustedTenantCatalog

**`src/main/java/example/tenantgateway/TrustedTenantCatalog.java`:**

```java
package example.tenantgateway;

import java.util.Collection;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class TrustedTenantCatalog {

    public record TenantSpec(
            String tenantId,
            String issuer,
            String jwkSetUri) {}

    private final Map<String, TenantSpec> byIssuer;

    public TrustedTenantCatalog(
            @Value("${security.tenants.alpha.issuer}") String alphaIssuer,
            @Value("${security.tenants.alpha.jwk-set-uri}") String alphaJwks,
            @Value("${security.tenants.beta.issuer}") String betaIssuer,
            @Value("${security.tenants.beta.jwk-set-uri}") String betaJwks) {

        if (alphaIssuer.isBlank() || betaIssuer.isBlank()
                || Objects.equals(alphaIssuer, betaIssuer)) {
            throw new IllegalArgumentException(
                    "Trusted issuer identifiers must be distinct");
        }

        byIssuer = Map.of(
                alphaIssuer, new TenantSpec(
                        "alpha", alphaIssuer, alphaJwks),
                betaIssuer, new TenantSpec(
                        "beta", betaIssuer, betaJwks));
    }

    public Collection<TenantSpec> trustedEntries() {
        return byIssuer.values();
    }

    public TenantSpec findByVerifiedIssuer(String issuer) {
        return byIssuer.get(issuer);
    }
}
```

Registry được tạo từ server config, **không thêm tenant/issuer theo request**. Với một IdP dùng chung nhiều tenant, cần triển khai membership model thay vì chỉ map 1:1. Trong demo, method `findByVerifiedIssuer` cố tình nhắc rằng caller phải lấy issuer **sau** khi decoder đã xác minh JWT.

### 7.6. TenantSecurityConfiguration

**`src/main/java/example/tenantgateway/TenantSecurityConfiguration.java`:**

```java
package example.tenantgateway;

import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class TenantSecurityConfiguration {

    private static final String REQUIRED_AUDIENCE =
            "api://tenant-gateway";

    @Bean
    JwtIssuerReactiveAuthenticationManagerResolver tenantIssuerResolver(
            TrustedTenantCatalog catalog) {

        Map<String, ReactiveAuthenticationManager> managers =
                new HashMap<>();

        for (TrustedTenantCatalog.TenantSpec spec
                : catalog.trustedEntries()) {

            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder
                            .withJwkSetUri(spec.jwkSetUri())
                            .build();

            OAuth2TokenValidator<Jwt> issuerAndTime =
                    JwtValidators.createDefaultWithIssuer(spec.issuer());

            OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                    jwt.getAudience() != null
                            && jwt.getAudience().contains(REQUIRED_AUDIENCE)
                            ? OAuth2TokenValidatorResult.success()
                            : OAuth2TokenValidatorResult.failure(
                                    new OAuth2Error("invalid_token",
                                            "Invalid gateway audience", null));

            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            issuerAndTime, audienceValidator));

            managers.put(
                    spec.issuer(),
                    new JwtReactiveAuthenticationManager(decoder));
        }

        // Chỉ tra cứu manager đã được cho phép từ ops config.
        Map<String, ReactiveAuthenticationManager> approved =
                Map.copyOf(managers);

        return new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(approved.get(issuer)));
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            JwtIssuerReactiveAuthenticationManagerResolver resolver) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/tenants/*/documents/*")
                            .hasAuthority("SCOPE_docs.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationManagerResolver(resolver))
                .build();
    }
}
```

Các lớp/packages dùng đúng API reactive Spring Security 6.5:

- `org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver` tra `iss` từ Bearer để chọn manager.
- `org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager` thực hiện authentication bằng `ReactiveJwtDecoder`.
- `NimbusReactiveJwtDecoder.withJwkSetUri` lấy key từ **JWKS URL đã cấu hình**, không tải metadata từ arbitrary raw issuer.
- `JwtValidators.createDefaultWithIssuer` kiểm `iss` và thời gian; audience validator kiểm token thực sự dành cho gateway.
- `hasAuthority("SCOPE_docs.read")` kiểm scope ngoài việc xác thực.
- Token không có issuer thuộc map không tạo một verifier mới. Đây là phân biệt quan trọng giữa **untrusted routing hint** và **trusted security policy**.
- Một `SecurityWebFilterChain` áp route demo; nếu hệ thống có nhiều chain, cần kiểm tra policy ở từng chain.

**Không tạo global `ReactiveJwtDecoder` bean khác cho demo** vì có hai issuers, mỗi issuer có decoder và validators riêng. Khi dùng `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` với IdP thật, manager có thể được tạo lazy qua discovery; nhưng ở lab này JWKS được pin để test không cần IdP thật.

### 7.7. TenantAccessPolicy

**`src/main/java/example/tenantgateway/TenantAccessPolicy.java`:**

```java
package example.tenantgateway;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public final class TenantAccessPolicy {

    public record VerifiedTenant(
            String tenantId,
            String issuer,
            String subject) {}

    private final TrustedTenantCatalog catalog;

    public TenantAccessPolicy(TrustedTenantCatalog catalog) {
        this.catalog = catalog;
    }

    public Mono<VerifiedTenant> requireTenant(
            Jwt verifiedJwt, String requestedTenant) {

        return Mono.defer(() -> {
            if (verifiedJwt == null || verifiedJwt.getIssuer() == null) {
                return deny();
            }

            // Chỉ được gọi sau authentication tại SecurityWebFilterChain.
            String issuer = verifiedJwt.getIssuer().toString();
            TrustedTenantCatalog.TenantSpec trusted =
                    catalog.findByVerifiedIssuer(issuer);

            String signedTenant =
                    verifiedJwt.getClaimAsString("tenant_id");
            String subject = verifiedJwt.getSubject();

            if (trusted == null
                    || signedTenant == null
                    || !trusted.tenantId().equals(signedTenant)
                    || !trusted.tenantId().equals(requestedTenant)
                    || subject == null || subject.isBlank()) {
                return deny();
            }

            return Mono.just(new VerifiedTenant(
                    trusted.tenantId(), issuer, subject));
        });
    }

    private static Mono<VerifiedTenant> deny() {
        return Mono.error(
                new AccessDeniedException("Tenant access denied"));
    }
}
```

Ở đây `requestedTenant` **chỉ là giá trị cần so sánh**, không được sao chép trực tiếp vào kết quả. `VerifiedTenant` chỉ được tạo khi JWT đã được Security xác thực, issuer được registry tin, claim `tenant_id` và path cùng khớp.

Các tình huống:

- Alpha token yêu cầu beta URL → 403.
- Token issuer alpha, có claim `tenant_id=beta` dù signature đúng → 403 vì không đúng hợp đồng 1:1 của lab.
- JWT không có tenant_id hoặc sub → 403.
- Token từ issuer lạ → 401, không tới policy này.
- Token đúng tenant nhưng scope `docs.write` thay `docs.read` → 403 ngay tại HTTP security.

Với ứng dụng nhiều issuer/multi-tenant phức tạp, tenant entitlement có thể đến từ một authorization service, nhưng phải là dữ liệu trusted và được đánh giá theo principal/tenant, không từ client-supplied headers.

### 7.8. TrustedDownstreamClient

**`src/main/java/example/tenantgateway/TrustedDownstreamClient.java`:**

```java
package example.tenantgateway;

import java.net.URI;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

@Service
public final class TrustedDownstreamClient {

    private final WebClient webClient;

    public TrustedDownstreamClient(
            @Value("${downstream.base-url}") String rawBaseUrl,
            @Value("${downstream.allow-insecure-loopback-for-tests:false}")
                    boolean allowTestHttp) {

        URI base = URI.create(rawBaseUrl);
        boolean https = "https".equalsIgnoreCase(base.getScheme());
        boolean httpLoopbackForTest = allowTestHttp
                && "http".equalsIgnoreCase(base.getScheme())
                && "127.0.0.1".equals(base.getHost());

        if (!(https || httpLoopbackForTest)
                || base.getHost() == null
                || base.getRawUserInfo() != null
                || base.getRawQuery() != null
                || base.getRawFragment() != null
                || !(base.getRawPath() == null
                    || base.getRawPath().isEmpty()
                    || "/".equals(base.getRawPath()))) {
            throw new IllegalArgumentException(
                    "Downstream base URL is not permitted");
        }

        HttpClient httpClient = HttpClient.create()
                .followRedirect(false)
                .responseTimeout(Duration.ofSeconds(5));

        webClient = WebClient.builder()
                .baseUrl(base.toString())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }

    public Mono<String> document(
            TenantAccessPolicy.VerifiedTenant tenant, String docId) {

        if (docId == null || !docId.matches("[A-Za-z0-9_-]{1,40}")) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid document id"));
        }

        return webClient.get()
                .uri("/internal/docs/{id}", docId)
                .headers(headers -> {
                    // Không copy raw inbound headers từ caller.
                    headers.set("X-Verified-Tenant", tenant.tenantId());
                    headers.set("X-Verified-Subject", tenant.subject());
                })
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(String.class)
                                .switchIfEmpty(Mono.error(
                                        new ResponseStatusException(
                                                HttpStatus.BAD_GATEWAY,
                                                "Empty downstream response")));
                    }
                    return response.releaseBody()
                            .then(Mono.error(
                                    new ResponseStatusException(
                                            HttpStatus.BAD_GATEWAY,
                                            "Downstream rejected request")));
                })
                .onErrorMap(WebClientRequestException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Downstream unavailable"));
    }
}
```

**Phân tích:**

1. `downstream.base-url` là **ops-owned configuration**, không phải URL lấy từ HTTP request. Cho HTTPS bình thường; HTTP chỉ cho loopback khi bật cờ test.
2. `.uri("/internal/docs/{id}", docId)` cố định path và validate doc ID; một WebClient có base URL **không** tự chặn code khác dùng absolute URI.
3. Mọi internal header chỉ được set từ `VerifiedTenant`, không copy `X-Tenant-ID`/`X-Verified-Tenant` đầu vào.
4. `followRedirect(false)` ngăn client tự đi tới Location bên khác; các status non-2xx được map lỗi an toàn, không phản chiếu body headers nhạy cảm.
5. **B downstream phải xác thực gateway A** qua mTLS/workload identity hoặc signed internal token; một header `X-Verified-Tenant` qua mạng công khai không đủ bảo mật.
6. Demo **không relay access token gốc**. Nếu B cần quyền end-user, phải có Bearer token hợp lệ với audience của B, token exchange (RFC 8693) hoặc signed internal delegation.
7. Production cần kiểm thêm egress firewall/service mesh và DNS policy; kiểm scheme/host ở application chưa đủ chống SSRF/rebinding.
8. Không tự `block()` hoặc `subscribe()` trong event loop; trả publisher để Reactor quản lý lifetime.

### 7.9. TenantGatewayController

**`src/main/java/example/tenantgateway/TenantGatewayController.java`:**

```java
package example.tenantgateway;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public final class TenantGatewayController {

    private final TenantAccessPolicy policy;
    private final TrustedDownstreamClient downstream;

    public TenantGatewayController(
            TenantAccessPolicy policy,
            TrustedDownstreamClient downstream) {
        this.policy = policy;
        this.downstream = downstream;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/tenants/{tenantId}/documents/{docId}")
    public Mono<String> document(
            @PathVariable String tenantId,
            @PathVariable String docId,
            @AuthenticationPrincipal Jwt verifiedJwt) {

        return policy.requireTenant(verifiedJwt, tenantId)
                .flatMap(tenant -> downstream.document(tenant, docId));
    }
}
```

Spring Security xác thực JWT và kiểm scope trước controller. Không có endpoint cho caller nhập tùy ý `issuer`, `jwk-set-uri` hoặc `downstream URL`. Phần downstream chỉ nhận verified context do policy phát.

---

## 8. Integration test với hai issuer và JWKS riêng

Test tạo RSA key pairs alpha/beta trong bộ nhớ và publish **public JWKS** qua một MockWebServer. Một MockWebServer mô phỏng downstream; một capture server khác dùng để phát hiện redirect bị follow.

**`src/test/java/example/tenantgateway/TenantGatewayIntegrationTest.java`:**

```java
package example.tenantgateway;

import java.io.IOException;
import java.time.Instant;
import java.util.Date;
import java.util.concurrent.TimeUnit;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TenantGatewayIntegrationTest {

    private static final String ISSUER_ALPHA =
            "https://issuer.example.invalid/alpha";
    private static final String ISSUER_BETA =
            "https://issuer.example.invalid/beta";
    private static final String AUDIENCE =
            "api://tenant-gateway";

    private static final RSAKey KEY_ALPHA = generate("key-alpha");
    private static final RSAKey KEY_BETA = generate("key-beta");

    private static final MockWebServer CAPTURE = startCapture();
    private static final MockWebServer DOWNSTREAM = startDownstream();
    private static final MockWebServer JWKS = startJwks();

    @DynamicPropertySource
    static void overrideTrustedEndpoints(DynamicPropertyRegistry registry) {
        registry.add("security.tenants.alpha.issuer",
                () -> ISSUER_ALPHA);
        registry.add("security.tenants.beta.issuer",
                () -> ISSUER_BETA);
        registry.add("security.tenants.alpha.jwk-set-uri",
                () -> JWKS.url("/jwks/alpha").toString());
        registry.add("security.tenants.beta.jwk-set-uri",
                () -> JWKS.url("/jwks/beta").toString());
        registry.add("downstream.base-url",
                () -> DOWNSTREAM.url("/").toString());
        registry.add("downstream.allow-insecure-loopback-for-tests",
                () -> "true");
    }

    @LocalServerPort
    int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() throws InterruptedException {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
        while (DOWNSTREAM.takeRequest(0, TimeUnit.MILLISECONDS) != null) {
            // Drain the recorded-request queue from earlier tests.
        }
    }

    @AfterAll
    static void shutdown() throws IOException {
        JWKS.shutdown();
        DOWNSTREAM.shutdown();
        CAPTURE.shutdown();
    }

    private static RSAKey generate(String kid) {
        try {
            return new RSAKeyGenerator(2048)
                    .keyID(kid).generate();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static MockWebServer startCapture() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startJwks() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                RSAKey publicKey;
                if ("/jwks/alpha".equals(request.getPath())) {
                    publicKey = KEY_ALPHA.toPublicJWK();
                } else if ("/jwks/beta".equals(request.getPath())) {
                    publicKey = KEY_BETA.toPublicJWK();
                } else {
                    return new MockResponse().setResponseCode(404);
                }

                return new MockResponse()
                        .setResponseCode(200)
                        .setHeader("Content-Type", "application/json")
                        .setBody(new JWKSet(publicKey).toString());
            }
        });
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startDownstream() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                String path = request.getPath();

                if ("/internal/docs/redirect".equals(path)) {
                    return new MockResponse()
                            .setResponseCode(302)
                            .setHeader("Location",
                                    CAPTURE.url("/capture").toString());
                }

                if (path != null
                        && path.startsWith("/internal/docs/")) {
                    return new MockResponse()
                            .setResponseCode(200)
                            .setHeader("Content-Type", "text/plain")
                            .setBody("tenant="
                                    + request.getHeader("X-Verified-Tenant")
                                    + ";subject="
                                    + request.getHeader("X-Verified-Subject")
                                    + ";path=" + path);
                }

                return new MockResponse().setResponseCode(404);
            }
        });
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static String signJwt(
            RSAKey key, String issuer, String subject,
            String tenantId, String audience, String scope,
            boolean expired) {
        try {
            Instant now = Instant.now();
            Instant start = expired
                    ? now.minusSeconds(3600) : now.minusSeconds(30);
            Instant end = expired
                    ? now.minusSeconds(600) : now.plusSeconds(600);

            JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
                    .issuer(issuer)
                    .subject(subject)
                    .audience(audience)
                    .issueTime(Date.from(start.minusSeconds(10)))
                    .notBeforeTime(Date.from(start))
                    .expirationTime(Date.from(end))
                    .claim("scope", scope);

            if (tenantId != null) {
                claims.claim("tenant_id", tenantId);
            }

            SignedJWT jwt = new SignedJWT(
                    new JWSHeader.Builder(JWSAlgorithm.RS256)
                            .type(JOSEObjectType.JWT)
                            .keyID(key.getKeyID())
                            .build(),
                    claims.build());
            jwt.sign(new RSASSASigner(key));
            return jwt.serialize();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String alphaToken() {
        return signJwt(KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.read", false);
    }

    private static String betaToken() {
        return signJwt(KEY_BETA, ISSUER_BETA, "bob",
                "beta", AUDIENCE, "docs.read", false);
    }

    @Test
    void publicPingWorks() {
        client.get().uri("/public/ping")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingBearerReturns401() {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void alphaTokenReadsOnlyAlpha() throws InterruptedException {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("tenant=alpha;subject=alice;path=/internal/docs/doc1");

        RecordedRequest r = DOWNSTREAM.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(r);
        assertEquals("alpha", r.getHeader("X-Verified-Tenant"));
        assertEquals("alice", r.getHeader("X-Verified-Subject"));
    }

    @Test
    void betaTokenReadsOnlyBeta() {
        client.get().uri("/api/tenants/beta/documents/doc1")
                .headers(h -> h.setBearerAuth(betaToken()))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("tenant=beta;subject=bob;path=/internal/docs/doc1");
    }

    @Test
    void alphaCannotRequestBetaPath() {
        int before = DOWNSTREAM.getRequestCount();
        client.get().uri("/api/tenants/beta/documents/doc1")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isForbidden();
        assertEquals(before, DOWNSTREAM.getRequestCount());
    }

    @Test
    void betaCannotRequestAlphaPath() {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(betaToken()))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void spoofedHeadersDoNotChangeVerifiedTenant()
            throws InterruptedException {
        client.get().uri("/api/tenants/alpha/documents/doc2")
                .header("X-Tenant-ID", "beta")
                .header("X-Verified-Tenant", "beta")
                .header("X-Verified-Subject", "mallory")
                .header("X-Forwarded-Host", "beta.example.invalid")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("tenant=alpha;subject=alice;path=/internal/docs/doc2");

        RecordedRequest r = DOWNSTREAM.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(r);
        assertEquals("alpha", r.getHeader("X-Verified-Tenant"));
        assertEquals("alice", r.getHeader("X-Verified-Subject"));
        assertNull(r.getHeader("X-Tenant-ID"));
    }

    @Test
    void conflictingSignedTenantClaimReturns403() {
        String token = signJwt(KEY_ALPHA, ISSUER_ALPHA, "alice",
                "beta", AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void missingTenantClaimReturns403() {
        String token = signJwt(KEY_ALPHA, ISSUER_ALPHA, "alice",
                null, AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void unknownIssuerCannotSelectArbitraryVerifier() {
        String token = signJwt(
                KEY_ALPHA, "https://attacker.example.invalid", "alice",
                "alpha", AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void alphaIssuerWithBetaSignatureReturns401() {
        String token = signJwt(
                KEY_BETA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceReturns401() {
        String token = signJwt(
                KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", "api://billing", "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingReadScopeReturns403() {
        String token = signJwt(
                KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.write", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void expiredTokenReturns401() {
        String token = signJwt(
                KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.read", true);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void unknownRequestedTenantReturns403() {
        client.get().uri("/api/tenants/gamma/documents/doc1")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void forgedHeaderWithoutJwtStillReturns401() {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .header("X-Verified-Tenant", "alpha")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void downstreamRedirectIsNotFollowed() {
        int before = CAPTURE.getRequestCount();

        client.get().uri("/api/tenants/alpha/documents/redirect")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isEqualTo(502);

        assertEquals(before, CAPTURE.getRequestCount());
    }
}
```

### 8.1. Chạy kiểm thử

Từ thư mục có Gradle Wrapper:

```bash
./gradlew test --tests example.tenantgateway.TenantGatewayIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.tenantgateway.TenantGatewayIntegrationTest
```

Hoặc Gradle cài sẵn tương thích:

```bash
gradle test --tests example.tenantgateway.TenantGatewayIntegrationTest
```

**Kỳ vọng:** 17 tests PASS nếu project, JDK 17+, Maven dependencies và khả năng bind loopback đúng. Đây là **kết quả dự đoán theo source**, không phải log biên dịch/chạy test thực tế trong workspace. Nếu bật JUnit parallel execution, phải cô lập MockWebServers hoặc đồng bộ việc đọc request count; bộ test này thiết kế tuần tự.

### 8.2. Những thuộc tính an toàn được kiểm tra

| Nhóm | Điều chứng minh |
| --- | --- |
| Public vs protected | Không có token ở route bảo vệ nhận 401 |
| Alpha/Beta hợp lệ | Mỗi issuer dùng JWKS riêng, tenant tương ứng |
| Alpha path beta / beta path alpha | JWT hợp lệ không cho truy cập tenant khác |
| Fake X-Tenant-ID/X-Verified-* | Header caller không được nâng thành trusted identity |
| Claim tenant_id thiếu/sai | Token signed vẫn phải thỏa tenant policy |
| Issuer lạ | Không tự fetch arbitrary JWKS/issuer |
| Chữ ký bằng key khác | Không thể giả issuer alpha với key beta |
| Wrong aud | JWT không dành cho gateway bị từ chối |
| Wrong scope | Token hợp lệ nhưng không có docs.read bị 403 |
| Expired | Timestamp validation từ chối |
| Tenant gamma | URL path không tự thêm tenant vào registry |
| Fake header không Bearer | Không tự tạo Authentication |
| Redirect | Không follow Location sang capture server |

### 8.3. Giới hạn kiểm thử

- Test không gọi IdP thật; JWKS được publish bởi mock HTTP loopback, private signing keys chỉ có trong test.
- Mock downstream **không** xác minh mTLS hoặc signed internal assertion; chỉ quan sát header để xác minh gateway không forward header giả.
- Test không kết nối DB/RLS, chưa chứng minh record-level ACL thật.
- Test không kiểm JWKS rotation/cache/timeout hoặc single-issuer multi-tenant entitlements.
- Cần staging TLS/ingress tests trước production, đặc biệt để bảo đảm **backend không bị truy cập trực tiếp** ngoài gateway.

---

## 9. Propagate tenant sang downstream qua ranh giới tin cậy

Gateway có thể muốn chuyển:

```http
X-Verified-Tenant: alpha
X-Verified-Subject: alice
```

**Chỉ hai header này không bao giờ là bằng chứng độc lập.** Nếu B public HTTP và tin một chuỗi header, bất kỳ client nào có thể tự nhận là alpha/alice.

Để B được phép tin metadata do A tạo, cần:

1. B chỉ nhận kết nối từ A/approved gateways qua network policy.
2. Xác thực **workload identity** của A bằng mTLS, SPIFFE/SPIRE hoặc service JWT/signed internal assertion có `aud=B`.
3. Tại edge, strip/normalize những header privileged do client có thể gửi.
4. A chỉ set verified tenant sau authentication và tenant entitlement.
5. B vẫn kiểm tra tenant resource, membership/role, owner/ACL, không chỉ một header.
6. Có defense-in-depth: short TTL, audit và revoke khi quyền thay đổi.

Trong môi trường nhiều domain tin cậy, cân nhắc **RFC 8693 OAuth2 Token Exchange** hoặc signed internal JWT ngắn hạn có audience của B, scope đã được giới hạn, tenant và subject đã xác minh. Đây là thiết kế riêng, không tự xuất hiện khi thêm `X-Verified-Tenant`.

### Opaque token

Nếu inbound là opaque access token thay vì JWT, dùng `ReactiveOpaqueTokenIntrospector` gọi endpoint IdP **đáng tin** để xác minh `active=true` và nhận `OAuth2AuthenticatedPrincipal`.

Không thể parse `iss` trực tiếp từ chuỗi opaque. Một routing hint từ host/path chỉ có thể chọn một **introspection provider allowlisted**; kết quả introspection vẫn phải kiểm issuer/resource/audience/tenant theo hợp đồng và phải so với requested tenant.

Không gửi token hoặc introspection client secret tới URL do caller tự khai.

### API key/mTLS/SSO session

Nguyên tắc tương tự:

- API key: sau khi hash/lookup server-side key hợp lệ, map key→tenant và quyền.
- mTLS: certificate đã verify chain/CA, rồi map verified subject/SPIFFE ID→tenant.
- OIDC session: dùng authenticated principal + server-side tenant memberships.
- User "switch tenant": yêu cầu authorization trước khi cập nhật active tenant trong session.
- Machine workload: sử dụng service identity và tenant entitlement riêng, không mượn user token/tenant mặc định.

---

## 10. Bảo vệ tenant data và cache

### Tenant-aware database query

Ngay cả khi gateway xác định verified tenant alpha, data service vẫn phải query theo `tenant_id`. Ví dụ:

```sql
SELECT document_id, content
FROM documents
WHERE tenant_id = :verifiedTenant
  AND document_id = :documentId
  AND owner_subject = :verifiedSubject;
```

Bind parameters, không tự nối SQL. Nếu yêu cầu ACL thay vì owner, dùng join/row-level predicates phù hợp. Khi dùng R2DBC pool hoặc PostgreSQL RLS, cần quản lý tenant context theo transaction và reset connection/session setting đúng cách.

### Cache isolation

Sai:

```text
cacheKey = "doc:" + documentId
```

Đúng hơn theo policy:

```text
cacheKey = tenantId + ":" + documentId + ":" + authorizationScope
```

Nếu cached response phụ thuộc owner hoặc nhóm quyền, thêm verified identity/policy version hoặc không cache shared. Không dùng tenant ID từ client header làm cache key quyền.

### Audit và observability

Log event với issuer, tenant, subject đã verify theo chính sách riêng tư, resource ID, decision, correlation ID và error category; **không log raw JWT, Authorization header, token secret hoặc nội dung nhạy cảm của document**.

Với cross-tenant access attempts, alert trên chỉ số 403, không tạo log có PII không cần thiết. Khi tenant registry thay đổi, version/audit mapping và update policy cache.

## 11. Lỗi thường gặp

| Tình huống | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Alpha token đọc beta document | Path/header được tin như Authentication | Compare verified tenant với requested tenant |
| X-Verified-Tenant giả được backend tin | Backend public, không có workload auth | Network isolation + mTLS/signed assertion |
| JWT issuer lạ được chấp nhận | Arbitrary issuer/JWKS discovery | Issuer allowlist và pinned verifiers |
| Tenant ID đúng nhưng signature sai vẫn qua | Parse claim trước verify | Validate token trước policy |
| JWKS beta verify alpha issuer | Key/issuer không tách biệt | Separate decoders, exact issuer validators |
| JWT signature hợp lệ, tenant claim khác registry | Chỉ kiểm chữ ký | Explicit trusted issuer→tenant check |
| Token không tenant claim thành tenant mặc định | Fail-open fallback | Missing tenant => deny |
| JWT sai audience | Bỏ audience validation | Validate aud gateway |
| Token scope không đủ | Thiếu authorization | Check SCOPE_docs.read |
| Host beta được coi là quyền beta | Host là routing hint, không membership | Host allowlist và token tenant policy |
| Forwarded-Host giả | Proxy không strip headers | Trusted proxy metadata normalization |
| User alpha/beta trùng subject trong cache | Thiếu issuer namespace | Cache key issuer+tenant+sub |
| Downstream chỉ query docId | Thiếu tenant predicate | Tenant-scoped query + ACL |
| Multi-tenant IdP chung bị map cứng 1:1 | Sai data model | Signed membership/tenant entitlement |
| 401 nhầm thành 403 | Authentication và authorization trộn | Phân lớp failure rõ |
| 302 tới host khác bị follow | Outbound redirect không kiểm soát | Disable redirects và allowlist |
| Opaque token bị decode như JWT | Sai token strategy | Introspection server |
| API key ID bị tin trước lookup | Key spoofing | Hash/verify với server-owned store |
| Session active tenant chỉnh bằng cookie | Không check membership | Reauthorize tenant switch |
| JWT bị log | Credential leakage | Mask Authorization và payload |
| JWKS URL HTTP public | MITM thay public key | HTTPS + certificate validation |
| RLS tenant variable bị giữ trên pooled connection | Cross-tenant connection state | Transaction-bound context/reset |
| Test mockJwt vẫn PASS dù verifier sai | Test bỏ qua signature | RSA/JWKS integration tests |
| IdP/JWKS downtime rồi cho permitAll | Fail open | Không cấp quyền khi verify thất bại |

## 12. Spring Cloud Gateway: strip headers trước khi truyền tiếp

Spring Cloud Gateway WebFlux có route predicates, `GatewayFilter`/`GlobalFilter` và `RemoveRequestHeader`. Khi thực sự dùng Gateway starter, có thể đặt filter loại bỏ privileged headers do caller gửi:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: tenant-documents
              uri: https://documents.internal.example.test
              predicates:
                - Path=/api/tenants/{tenantId}/documents/**
              filters:
                - RemoveRequestHeader=X-Verified-Tenant
                - RemoveRequestHeader=X-Verified-Subject
                - RemoveRequestHeader=X-Tenant-ID
```

**Fragment này chỉ có chức năng strip headers khi forward**, không tự authenticate JWT hay cấp tenant entitlement. Không dán cấu hình vào project runnable ở mục 7 vì project đó không dùng Spring Cloud Gateway. Route variable `{tenantId}` cũng là input client, không phải verified identity. Custom filter/handler chỉ được sinh internal tenant identity **sau** khi Security và tenant policy hoàn tất; phải kiểm thứ tự filter, không dùng `AddRequestHeader=X-Verified-Tenant,{tenantId}` để cấp quyền.

Trusted proxy config ở Gateway phục vụ việc nhận định metadata Host/IP/scheme từ proxy, **không chứng minh user thuộc tenant được chỉ bởi Host**. Nếu có nhiều proxy, edge phải xóa `Forwarded`/`X-Forwarded-*` từ client và tạo lại từ kết nối thật, kết hợp host allowlist.

## 13. Checklist production

1. Phân biệt requested tenant, verified tenant, resource tenant.
2. Không cấp quyền dựa vào raw Host/path/header/query/cookie/JWT payload chưa verify.
3. Issuer/JWKS URL được whitelist từ server admin config, không từ JWT/user.
4. Verify JWT signature, issuer, audience, exp, nbf; check scope và tenant claims.
5. Mỗi issuer/principal được namespaced; subject không coi globally unique.
6. Nếu một issuer có nhiều tenant, dùng verified membership entitlements.
7. Requested tenant selector luôn được so với verified tenant.
8. Không tự gán default tenant khi claim vắng hoặc verify thất bại.
9. Route/HTTP và service/data-layer authorization đều hoạt động.
10. Query DB có predicate tenant, owner/ACL; RLS/pool lifecycle an toàn.
11. Backend không public và có mTLS/signed internal identity.
12. Strip inbound privileged headers; không copy raw headers vào downstream.
13. Outbound URL từ trusted config, path cố định, no auto redirect, HTTPS/egress restrictions.
14. Opaque token dùng trusted introspection, không parse JWT-like string tùy tiện.
15. SSO tenant switch có check membership; session cookies không tự tạo quyền.
16. Cache keys phân tách issuer/tenant/subject/resource và TTL phù hợp revoke.
17. Không log Bearer tokens, JWKS private key, credentials hoặc raw PII.
18. Negative tests: wrong issuer/signature/aud, missing scope, tenant mismatch, spoofed headers, expired token.
19. Review onboarding/rotation/deletion tenant trong control plane và audit mapping.
20. Test staging có TLS/proxy/mTLS thật; đừng coi mock downstream là auth proof.

## 14. Bài tập

1. Chạy test alpha token/alpha path và giải thích vì sao path beta bị 403.
2. Giả `X-Verified-Tenant: beta` với alpha token; vì sao downstream vẫn nhận alpha?
3. Dùng JWT có raw `iss` từ attacker và tự phát key: vì sao map không tạo manager mới?
4. Đổi chữ ký sang key beta nhưng issuer alpha, phân tích 401.
5. Thử JWT đúng chữ ký nhưng `tenant_id=beta` của issuer alpha: policy nào chặn?
6. Bỏ audience validator trong nhánh thử nghiệm, quan sát rủi ro token từ API khác.
7. Bỏ `SCOPE_docs.read` trong JWT, kiểm chứng 403 trước khi downstream được gọi.
8. Thêm PostgreSQL R2DBC query theo tenant/owner, kiểm tra không rò docId trùng.
9. Cùng `sub=alice` ở hai issuer, định nghĩa cache key không trộn danh tính.
10. Thay mapping 1:1 bằng một issuer nhiều tenant với verified org membership.
11. Thiết kế admin tenant onboarding có approval/audit và trusted JWKS rotation.
12. Thêm opaque introspection flow, so tenant attribute và route path sau active check.
13. Thử session login switch active tenant: cần kiểm tra membership trước khi cập nhật.
14. Đặt Resource Server B thật sau gateway; thử gọi B trực tiếp với fake internal header.
15. Thay header propagation bằng short-lived signed internal token với `aud=B`.
16. Đặt edge dưới CDN/proxy, kiểm fake Host/X-Forwarded-Host không nâng quyền.
17. Viết metrics cho cross-tenant denies nhưng không log JWT raw.
18. Thiết kế behavior 404 che giấu resource existence mà không cho phép enumeration.

## Tổng kết

**Không có header, path hay JWT claim chưa verify nào tự xác lập tenant.** Gateway có thể dùng untrusted selector để định tuyến hoặc issuer hint để chọn **verifier đã được allowlist**, nhưng chỉ sau khi Spring Security kiểm JWT và ứng dụng kiểm tenant entitlement, dữ liệu mới có thể trở thành verified tenant context.

Trong WebFlux, `JwtIssuerReactiveAuthenticationManagerResolver` chọn manager theo issuer; `JwtReactiveAuthenticationManager` và `NimbusReactiveJwtDecoder` kiểm chữ ký/issuer/audience/time. `TenantAccessPolicy` đối chiếu verified issuer/claim với requested tenant. Backend vẫn phải bảo vệ dữ liệu theo tenant và chỉ tin metadata từ gateway **trên kênh đã xác thực**.

**Bảo mật nhiều tenant là chuỗi kiểm soát từ ingress đến data storage**, không phải phép gán `tenant_id = request.header("X-Tenant-ID")`.

## Tài liệu chính thức

- [Spring Security 6.5 — Reactive OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security 6.5 — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [JwtIssuerReactiveAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [JwtReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html)
- [NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Cloud Gateway 4.3 — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html)
- [Spring Cloud Gateway — RemoveRequestHeader Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removerequestheader-factory.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth2 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [OWASP — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP — SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
