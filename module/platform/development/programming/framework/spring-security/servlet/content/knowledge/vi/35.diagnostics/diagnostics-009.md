# Quyền không khớp do ROLE_, SCOPE_, ánh xạ claims hoặc bộ nhớ đệm

> **Phạm vi:** Chẩn đoán và sửa lỗi phân quyền trong **Spring Security Servlet**, Spring Boot 3.x, Spring Security 6.x, Java 17+. Bài đi từ HTTP 401/403 tới `Authentication.getAuthorities()`, giải thích `ROLE_`/`SCOPE_`, chuyển đổi JWT/OIDC claims và xác định quyền bị cũ trong `HttpSession`, access token, directory hoặc cache. **Không** sửa lỗi 403 bằng cách vô hiệu hóa security.

## 1. Bài toán và dấu hiệu nhận biết

Hệ thống có thể xuất hiện những triệu chứng rất khác nhau:

- Người dùng vừa được thêm vào nhóm `ADMIN` ở IdP nhưng `@PreAuthorize("hasRole('ADMIN')")` vẫn trả 403.
- Token có `scope: "report.read"`, trong khi service lại kiểm `hasRole('report.read')`.
- `@WithMockUser(roles = "ADMIN")` cho test PASS, JWT thật từ IdP vẫn bị từ chối.
- Quyền đã bị xóa ở directory nhưng người dùng còn session cũ vẫn thực hiện được thao tác.
- Một trang web đăng nhập bằng `oauth2Login()` có các authorities khác API dùng `oauth2ResourceServer().jwt()`.
- Claim `roles` bị mất vì IdP thực tế phát `realm_access.roles` hoặc `resource_access.<client>.roles`.
- Một yêu cầu POST bị 403 vì **CSRF**, nhưng team lại đổi `GrantedAuthorityDefaults`.
- Hai endpoint cùng một user nhưng khác `SecurityFilterChain` nên cách xác thực/phân quyền khác nhau.

Một lỗi **“không có quyền”** có thể bắt nguồn từ sáu tầng:

```text
HTTP request
     |
SecurityFilterChain được chọn
     |
Authentication filter -> AuthenticationManager / JwtDecoder
     |
Authentication principal + GrantedAuthority
     |
URL authorization / method security expression
     |
Business permission / resource ownership
     |
     Vấn đề độ mới: token, session, user/group cache, policy cache
```

Đầu tiên phải phân biệt lỗi xác thực với lỗi phân quyền:

| Kết quả | Gợi ý | Cảnh báo khi chẩn đoán |
|---|---|---|
| 401 Unauthorized | Thiếu credential, JWT signature/issuer/audience/expiry sai, Basic/Bearer entry point | Không suy ra ngay `hasRole` sai |
| 302 tới login | Browser chưa có session và form/OIDC entry point chuyển hướng | Không phải endpoint tự trả dữ liệu |
| 403 Forbidden | Authenticated nhưng thiếu authority, hoặc CSRF/WAF/deny rule | Không phải lúc nào cũng do prefix |
| 200 OK | Request qua được các lớp đang kiểm tra | Không chứng minh object-level authorization ở mọi tài nguyên |

**Nguyên tắc:** xác định filter và rule thực sự phát sinh quyết định, quan sát authority thực tế và thời điểm quyền được cấp, rồi mới sửa đúng vị trí.

## 2. Phân biệt principal, role, authority, scope và claim

`Authentication` chứa principal và tập `GrantedAuthority`. Với `SimpleGrantedAuthority`, mỗi authority là một **chuỗi** được so khớp với rule.

- **Principal:** danh tính caller, như username, user ID hoặc `issuer + subject`. Đã xác thực không đồng nghĩa có mọi quyền.
- **Role:** nhóm quyền `ADMIN`, `REPORT_READER`, thường được biểu diễn với quy ước `ROLE_` trong Spring Security.
- **Authority:** tên thực tế từ `Authentication.getAuthorities()`, ví dụ `ROLE_ADMIN` hoặc `SCOPE_report.read`.
- **OAuth2 scope:** phạm vi access token được phép dùng, như `report.read`, thường phản ánh khả năng của client/token với API.
- **Claim:** trường trong JWT/ID token như `groups`, `roles`, `scp`, `scope`, `aud`. Claim là dữ liệu đầu vào; cần converter/mapper để thành `GrantedAuthority`.
- **Permission nghiệp vụ:** quyền tác động lên resource cụ thể, như báo cáo thuộc tenant nào, trạng thái giao dịch hoặc quyền sở hữu. Có role đúng nhưng khác tenant vẫn phải bị từ chối nếu policy yêu cầu.

Luồng scope:

```text
Access token: {"scope":"report.read report.export"}
           |
JwtGrantedAuthoritiesConverter (mặc định)
           |
SCOPE_report.read, SCOPE_report.export
           |
@PreAuthorize("hasAuthority('SCOPE_report.read')")
           |
         Cho phép
```

Luồng role custom:

```text
Access token: {"app_roles":["ADMIN"]}
           |
Trusted issuer + audience validation
           |
Custom role converter (allowlist ADMIN, AUDITOR)
           |
ROLE_ADMIN
           |
@PreAuthorize("hasRole('ADMIN')")
           |
         Cho phép
```

Đừng mặc định root claim `roles`, một group trong LDAP hay một JSON value có tên `admin` đã đủ quyền admin. Chỉ nguồn được tin và được phép cấp role cho API mới có thể được chuyển thành quyền nội bộ.

## 3. ROLE_: hasRole khác hasAuthority như thế nào?

Trong cấu hình **default role prefix** quen thuộc:

- `hasRole("ADMIN")` thường tìm authority **`ROLE_ADMIN`**.
- `hasAuthority("ROLE_ADMIN")` yêu cầu chuỗi đúng là `ROLE_ADMIN`.
- `hasAuthority("ADMIN")` chỉ yêu cầu `ADMIN`, **không** thêm tiền tố.
- `@WithMockUser(roles = "ADMIN")` tạo authority `ROLE_ADMIN`.
- `@WithMockUser(authorities = "ADMIN")` tạo đúng `ADMIN`, nên không khớp `hasRole("ADMIN")`.
- Prefix, case, dấu chấm/gạch dưới đều phải khớp chính xác.

| Authorities hiện có | Rule | Kết quả (default prefix) |
|---|---|---|
| `ROLE_ADMIN` | `hasRole('ADMIN')` | Cho phép |
| `ROLE_ADMIN` | `hasAuthority('ROLE_ADMIN')` | Cho phép |
| `ADMIN` | `hasRole('ADMIN')` | Không khớp |
| `ADMIN` | `hasAuthority('ADMIN')` | Cho phép |
| `SCOPE_report.read` | `hasAuthority('SCOPE_report.read')` | Cho phép |
| `SCOPE_report.read` | `hasRole('report.read')` | Không khớp |
| `ROLE_ROLE_ADMIN` | `hasRole('ADMIN')` | Không khớp |

Nếu ứng dụng tùy chỉnh `GrantedAuthorityDefaults`, `RoleHierarchy` hoặc expression handler, bảng phải được kiểm chứng lại. Các API web, method security và JSR-250 có thể lấy cấu hình prefix theo các extension point khác nhau tùy phiên bản; đừng đổi prefix toàn hệ thống để chữa một endpoint mà không test hồi quy.

**Lỗi prefix hai lần:**

```java
// Phản ví dụ: role từ IdP đã là "ROLE_ADMIN".
String role = "ROLE_ADMIN";
String authority = "ROLE_" + role; // ROLE_ROLE_ADMIN
```

Cách làm an toàn: chốt contract đầu vào cho role, chuẩn hóa có chủ đích tại **một** converter và sử dụng exact allowlist. Không tự loại bỏ mọi chuỗi `ROLE_` hoặc dùng substring matching với đầu vào không tin cậy.

## 4. SCOPE_: scope của JWT resource server không phải role

Với `oauth2ResourceServer().jwt()`, `JwtAuthenticationConverter` thông thường dùng `JwtGrantedAuthoritiesConverter` lấy giá trị từ claim `scope` hoặc `scp`:

- `scope` hay là chuỗi cách nhau bằng khoảng trắng: `"report.read report.export"`.
- `scp` có thể là danh sách: `["report.read", "report.export"]`.
- Mỗi scope được gắn `SCOPE_`: `SCOPE_report.read`.
- `report.read`, `REPORT_READ` và `report_read` là ba tên khác nhau; không có tự động uppercase.
- Không phải mọi IdP đều dùng cùng claim shape. Converter custom có thể thay hành vi mặc định.

Nếu đang bảo vệ scope, rule rõ nghĩa:

```java
@PreAuthorize("hasAuthority('SCOPE_report.read')")
public String viewReport() {
    return "report";
}
```

Đây là method trong Spring bean đã được `@EnableMethodSecurity` bảo vệ, không phải class Java độc lập.

Khi thay tên claim:

```java
JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERM_");
```

Converter minh họa này sẽ đọc `permissions` thay cho scope/scp mặc định. Nếu vẫn cần `SCOPE_*`, phải **kết hợp** kết quả của converter scope gốc và converter permission mới, nếu không một thay đổi “thêm permission” có thể làm mất toàn bộ scope.

**Không đồng nhất scope và quyền nghiệp vụ:** ngay cả user có `SCOPE_report.read`, hệ thống vẫn phải kiểm report có thuộc đúng tổ chức/tenant và caller được phép xem report đó không.

## 5. Ánh xạ claims: nơi dễ mất quyền hoặc cấp nhầm quyền nhất

Một số kiểu JWT payload minh họa:

```json
{
  "sub": "user-123",
  "aud": ["reports-api"],
  "scope": "report.read",
  "roles": ["ADMIN"],
  "groups": ["/company/reviewers"],
  "realm_access": {"roles": ["reader"]},
  "resource_access": {
    "reports-api": {"roles": ["approver"]}
  }
}
```

Đây chỉ là JSON về **cấu trúc claims**, không phải access token đã ký. Với các IdP khác nhau, group/role có thể ở root, nested object hoặc không xuất hiện trong access token mà chỉ ở userinfo/ID token.

Một contract mapping cần xác định rõ:

1. **Token loại gì?** Access token dành cho API hay ID token dùng xác thực browser? Không dùng ID token tùy tiện thay bearer access token.
2. **Issuer và signature?** `iss` được allowlist, signature hợp lệ với trusted JWKS, algorithm không được suy từ token do client tự khai.
3. **Audience?** `aud` phải có API đang bảo vệ; không chấp nhận token ký đúng nhưng cấp cho service khác.
4. **Claim path?** `roles`, `groups`, `realm_access.roles` hay `resource_access.reports-api.roles`?
5. **Kiểu dữ liệu?** List string, chuỗi có separator, nested map hoặc null? Sai kiểu phải fail closed về quyền.
6. **Semantics và authority source?** Có phải issuer thực sự có quyền cấp `ADMIN` cho application này? Một group tùy ý không được tự trở thành admin.
7. **Namespace và tenant?** Tên nhóm giống nhau trong hai tenant/issuer không mặc nhiên cùng một quyền.
8. **Freshness:** token được phát trước hay sau khi group/permission thay đổi?

**Phản ví dụ không an toàn:**

```java
// Nếu string chứa "not-admin", contains("admin") cũng trả true.
String rawRole = jwt.getClaimAsString("roles");
if (rawRole != null && rawRole.contains("admin")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

Đây chỉ là phản ví dụ. Mapper thật phải kiểm type và so khớp **tên chính xác** theo allowlist, sau khi token được xác minh.

### 5.1. OIDC login và resource server thường không chia sẻ converter

`oauth2Login()` tạo authentication của browser login, có thể là `OAuth2AuthenticationToken` với `OidcUser` và session. `oauth2ResourceServer().jwt()` tạo `JwtAuthenticationToken` từ bearer access token. Hai đường xử lý này dùng extension points khác nhau; cấu hình `JwtAuthenticationConverter` trong JWT resource server không bảo đảm nó được dùng cho authorities của `OidcUser`.

`@WithMockUser` trong unit test lại tạo một context giả, thường **không chạy converter**. Vì vậy muốn chẩn đoán chính xác phải hỏi “Authentication này đến từ đâu?” trước khi so sánh authorities.

## 6. Quy trình điều tra một HTTP 403 có bằng chứng

### Bước 1: Tìm chính xác nguồn 403

Kiểm tra request method, context path, proxy/gateway và exception handler. POST/PUT/DELETE qua browser session có thể bị CSRF filter từ chối trước controller, dù role admin chính xác. 403 của WAF cũng không liên quan `JwtGrantedAuthoritiesConverter`. Với request chưa login, 401/302 là entry point chứ chưa chắc authorization failure.

### Bước 2: Chọn đúng SecurityFilterChain

`securityMatcher(...)` và thứ tự `@Order` xác định chain được áp dụng; `requestMatchers(...)` kiểm policy trong chain. `/api/**` có thể dùng bearer JWT, `/web/**` dùng OIDC session, fallback `denyAll`. Reverse-proxy rewrite khiến URL thực đi vào app khác URL browser, dẫn đến chain khác.

### Bước 3: So actual Authentication/authorities

Trong test hoặc staging đã được cấp quyền, kiểm tra loại authentication và authority names. **Không log raw JWT, Authorization header, token, credentials hoặc toàn bộ claims**.

Snippet minh họa trong test:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
if (authentication != null) {
    String type = authentication.getClass().getSimpleName();
    List<String> authorityNames =
        authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted().toList();
    // Assertion test nội bộ trên type và authorityNames.
    // Không xuất principal PII, password, bearer token.
}
```

Cần import `Authentication`, `GrantedAuthority`, `SecurityContextHolder` và `List` nếu dùng snippet. Đây không phải endpoint debug public cho khách hàng.

### Bước 4: So rule đang chạy

Nếu context có `SCOPE_report.read`, `ROLE_REVIEWER` nhưng rule là `hasRole('REPORT_READ')` thì cần `ROLE_REPORT_READ`. Làm rõ nghiệp vụ muốn scope, role hay permission, rồi sửa **một nơi**: expression hoặc converter theo contract chính thức.

### Bước 5: Kiểm tra tuổi dữ liệu quyền

So `iat/exp` của token, thời điểm tạo `HttpSession`, lần login gần nhất, cache TTL, directory/IdP group sync và thời điểm đổi quyền. Self-contained JWT **không tự thay claims sau khi được ký**. Một `SecurityContext` lưu trong session cũng có thể giữ authorities từ lần đăng nhập cũ.

### Bước 6: Viết test allow và deny

Một user đủ quyền phải được phép; user thiếu quyền/khác tenant/claim giả, malformed hoặc cũ phải bị từ chối theo chính sách. Chỉ sửa để testcase admin 200 nhưng bỏ test quyền thấp dễ tạo privilege escalation.

## 7. Bộ nhớ đệm: không có một “roles cache” duy nhất

| Nơi lưu trạng thái | Dữ liệu bị cũ | Cách kiểm tra |
|---|---|---|
| Self-contained JWT | Claims `scope/roles/groups` từ lúc phát hành | Token `iat/exp`, T1/T2, TTL, revocation |
| `HttpSession`/`SecurityContextRepository` | `Authentication` từ lần login | Re-auth, logout, invalidate session |
| `UserDetailsService`/`UserCache` (nếu bật) | User details và authorities | Cache key, TTL, eviction, account status |
| Backend `@Cacheable`/Redis | Group→permissions, tenant policy | Cache key namespace, TTL và invalidation |
| Directory/IdP sync | Membership chưa đến issuer | Sync schedule, source of truth, claim issuance |
| Gateway policy cache | Quyết định truy cập cũ | Key theo account, resource, operation, tenant |
| JWKS cache | Public key dùng verify JWT signature | Key rotation/`kid` — **không phải** cache role |

**JWKS cache khác authorization cache.** Refresh JWKS giải quyết lỗi signature/key rotation, **không làm token đang có claims cũ nhận roles mới**.

### 7.1. Quyền vừa được cấp nhưng chưa thấy

Kiểm tra user được thêm đúng group chưa, issuer đã phát **token T2** có claim mới chưa, converter đọc đúng claim chưa, session đã re-auth hoặc context đã reload chưa, và cache backend/IdP sync có còn snapshot cũ không. Token T1 được ký trước khi thay đổi thường giữ claim cũ tới khi hết hạn.

### 7.2. Quyền đã bị thu hồi nhưng vẫn hoạt động

Đây thường là rủi ro cao hơn. Token T2 còn hiệu lực có thể giữ `ROLE_ADMIN` dù directory đã xóa nhóm. Tùy SLA, dùng token TTL ngắn, introspection/revocation, server-side policy lookup hoặc invalidate session/token. Logout browser chỉ hủy session trong phạm vi liên quan, không mặc định revoke mọi bearer token trên thiết bị khác.

### 7.3. Quyền user A xuất hiện cho user B

Đây có thể là lỗi cache key không bao gồm issuer/subject/tenant/resource hoặc security context trong thread pool bị xử lý sai. Không đơn giản “clear cache là xong”. Kiểm tra `SecurityContextHolder` propagation và cleanup, cache isolation, tenant namespace và event invalidation ở nhiều nodes.

**Cache key** nên xét `issuer + stable subject + tenant + resource + action + policy version` khi những chiều đó ảnh hưởng kết quả. Tránh key chỉ có username hoặc tên role. Thiết kế TTL và thu hồi theo mức độ nhạy, đo riêng độ trễ **cấp** và **thu hồi** quyền.

## 8. Ví dụ Java 17 + Spring Boot 3.3.5: phân biệt ROLE_ và SCOPE_

Demo Servlet API có hai quyền độc lập:

- `scope/scp` từ JWT → `SCOPE_*` theo `JwtGrantedAuthoritiesConverter`.
- `app_roles` từ JWT → `ROLE_*` sau khi issuer/audience được kiểm tra và role nằm trong allowlist.
- `GET /api/reports` đòi `SCOPE_report.read`.
- `GET /api/admin` đòi `ROLE_ADMIN`.

**Hạn chế môi trường:** `.invalid` ở config là domain học tập không hoạt động; server không thể validate bearer JWT thật khi chưa thay bằng trusted issuer/JWKS. Bộ test dùng `@MockBean JwtDecoder` để chứng minh converter/authorization, **không** chứng minh signature. Muốn test chữ ký phải dùng signed test token và test JWKS, không mock decoder.

### 8.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') { useJUnitPlatform() }
```

Cây file:

```text
src/main/java/demo/authority/
  AuthorityApplication.java
  SecurityConfig.java
  ReportService.java
  ApiController.java
src/main/resources/application.yml
src/test/java/demo/authority/
  AuthorityIntegrationTest.java
  MethodRulesTest.java
```

### 8.2. application.yml và ứng dụng chính

`src/main/resources/application.yml`:

```yaml
app:
  security:
    issuer: "https://id.example.invalid/"
    audience: "reports-api"
    jwk-set-uri: "https://id.example.invalid/jwks.json"
```

`src/main/java/demo/authority/AuthorityApplication.java`:

```java
package demo.authority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityApplication.class, args);
    }
}
```

### 8.3. SecurityConfig: audience validation + mapper hai namespace

`src/main/java/demo/authority/SecurityConfig.java`:

```java
package demo.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    OAuth2TokenValidator<Jwt> jwtValidator(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {
        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Required audience missing", null));

        return new DelegatingOAuth2TokenValidator<>(
            standard, audienceCheck);
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwk-set-uri}") String jwksUri,
            OAuth2TokenValidator<Jwt> validator) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
        decoder.setJwtValidator(validator);
        return decoder;
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();
        Set<String> allowed = Set.of("ADMIN", "AUDITOR");

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                scopeConverter.convert(jwt);
            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object claim = jwt.getClaim("app_roles");
            if (claim instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if (item instanceof String role &&
                            allowed.contains(role)) {
                        authorities.add(new SimpleGrantedAuthority(
                            "ROLE_" + role));
                    }
                }
            }
            return authorities;
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        converter.setPrincipalClaimName("sub");
        return converter;
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http, JwtAuthenticationConverter converter)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
            .build();
    }
}
```

Giải thích:

- `NimbusJwtDecoder` lấy public signing keys từ **configured trusted JWKS**; validator kiểm tra issuer/standard claims và **audience reports-api**. Không chọn URL từ `jku` của token.
- `JwtGrantedAuthoritiesConverter` giữ scopes thành `SCOPE_*`; custom mapper chỉ thêm `ROLE_*` nếu claim `app_roles` là Collection và giá trị thuộc allowlist.
- `app_roles` là **giả định hợp đồng** giữa API và issuer đáng tin; allowlist ở code không thay thế việc IdP kiểm soát ai được nhận role ADMIN.
- Nếu claim đã là `ROLE_ADMIN`, code sẽ **không map** thành `ROLE_ROLE_ADMIN` vì giá trị không nằm trong allowlist.
- Cả hai endpoint đòi authenticated; method security mới kiểm quyền cụ thể. Không có `permitAll` cho `/api/**`.

### 8.4. Service và controller

`src/main/java/demo/authority/ReportService.java`:

```java
package demo.authority;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('SCOPE_report.read')")
    public String read() {
        return "report";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String admin() {
        return "admin";
    }
}
```

`src/main/java/demo/authority/ApiController.java`:

```java
package demo.authority;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    private final ReportService service;

    public ApiController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/api/reports")
    public String reports() {
        return service.read();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return service.admin();
    }
}
```

Endpoint role không tự có scope, và endpoint scope không tự có role. Với production, authorization theo report ID/tenant còn là bước riêng.

## 9. MockMvc kiểm thử mapper và method security

### 9.1. HTTP bearer tests với decoder giả

`src/test/java/demo/authority/AuthorityIntegrationTest.java`:

```java
package demo.authority;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorityIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired JwtAuthenticationConverter converter;
    @Autowired OAuth2TokenValidator<Jwt> validator;

    @MockBean JwtDecoder decoder; // Chỉ test converter/filter, không test chữ ký.

    private Jwt token(String value, String scope,
                      List<String> roles, String issuer,
                      List<String> audience) {
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .claim("iss", issuer)
            .claim("sub", "test-user")
            .claim("aud", audience)
            .claim("scope", scope)
            .claim("app_roles", roles)
            .issuedAt(Instant.now().minusSeconds(60))
            .expiresAt(Instant.now().plusSeconds(600))
            .build();
    }

    @BeforeEach
    void setUp() {
        String issuer = "https://id.example.invalid/";
        List<String> aud = List.of("reports-api");
        when(decoder.decode("read")).thenReturn(
            token("read", "report.read", List.of(), issuer, aud));
        when(decoder.decode("admin")).thenReturn(
            token("admin", "", List.of("ADMIN"), issuer, aud));
        when(decoder.decode("both")).thenReturn(
            token("both", "report.read", List.of("ADMIN"), issuer, aud));
        when(decoder.decode("unknown-role")).thenReturn(
            token("unknown-role", "", List.of("SUPER_ADMIN"),
                  issuer, aud));
    }

    @Test
    void scopeCanReadButCannotAdmin() throws Exception {
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer read"))
            .andExpect(status().isOk())
            .andExpect(content().string("report"));
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer read"))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleCanAdminButNotReadWithoutScope() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer admin"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    void combinedClaimsWork() throws Exception {
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer both"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer both"))
            .andExpect(status().isOk());
    }

    @Test
    void unapprovedRoleDoesNotGrantAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer unknown-role"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousIs401() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void converterUsesBothPrefixes() {
        Jwt jwt = token("inspect", "report.read", List.of("ADMIN"),
            "https://id.example.invalid/", List.of("reports-api"));
        var names = converter.convert(jwt).getAuthorities().stream()
            .map(a -> a.getAuthority()).toList();
        assertTrue(names.contains("SCOPE_report.read"));
        assertTrue(names.contains("ROLE_ADMIN"));
        assertFalse(names.contains("ROLE_ROLE_ADMIN"));
    }

    @Test
    void issuerAndAudienceValidatorRejectsWrongClaims() {
        Jwt good = token("good", "report.read", List.of(),
            "https://id.example.invalid/", List.of("reports-api"));
        Jwt otherAudience = token("bad-aud", "report.read", List.of(),
            "https://id.example.invalid/", List.of("other-api"));
        Jwt otherIssuer = token("bad-iss", "report.read", List.of(),
            "https://other.example.invalid/", List.of("reports-api"));
        assertFalse(validator.validate(good).hasErrors());
        assertTrue(validator.validate(otherAudience).hasErrors());
        assertTrue(validator.validate(otherIssuer).hasErrors());
    }
}
```

**Phạm vi:** `@MockBean JwtDecoder` thay decoder nên test HTTP **không kiểm JWT signature hoặc trusted JWKS**. Validator test gọi trực tiếp các quy tắc issuer/audience, cũng chưa kiểm ký số. Để test thật, dùng token ký bởi test key, test JWKS/IdP, **không mock decoder** và kiểm wrong signature, wrong `iss/aud`, expired/`nbf`.

### 9.2. Method tests: không nhầm mock user với JWT converter

`src/test/java/demo/authority/MethodRulesTest.java`:

```java
package demo.authority;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodRulesTest {
    @Autowired ReportService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void defaultRolePrefixWorks() {
        assertEquals("admin", service.admin());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void bareAuthorityIsNotAdminRole() {
        assertThrows(AccessDeniedException.class, service::admin);
    }

    @Test
    @WithMockUser(authorities = "SCOPE_report.read")
    void exactScopeIsAccepted() {
        assertEquals("report", service.read());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotAutomaticallyHaveScope() {
        assertThrows(AccessDeniedException.class, service::read);
    }
}
```

Chạy với Gradle Wrapper và Java 17:

```bash
./gradlew test
./gradlew test --tests demo.authority.AuthorityIntegrationTest
./gradlew test --tests demo.authority.MethodRulesTest
```

Một testcase cố ý kỳ vọng 401/403 hoặc `AccessDeniedException` **PASS khi đúng hành vi từ chối**. Không có stdout Gradle cố định, do phiên bản và cache.

## 10. Kiểm chứng JWT thực và độ mới của quyền

### 10.1. Tách decoder test khỏi converter test

Khi dùng test IdP hoặc một JWKS test server, tạo access tokens ký bằng test private key và **không mock `JwtDecoder`**. Ma trận:

| Tình huống | Kỳ vọng |
|---|---|
| Signature/issuer/audience đúng, có scope/role cần | 200 |
| Signature không hợp lệ | 401 |
| `alg` không cho phép | 401 |
| Issuer lạ hoặc audience khác API | 401 |
| Token expired/`nbf` ngoài thời gian hợp lệ | 401 |
| Token hợp lệ nhưng thiếu authority cần | 403 |
| Claim role lạ/sai kiểu | Không tự cấp admin |
| Token có quyền nhưng truy cập object khác tenant | 403 theo policy tài nguyên |

Chỉ dùng **test keys/test user**; không đưa JWT hoặc private key production vào CI/log.

### 10.2. Diễn tập thay đổi quyền

1. Đăng nhập user thử với quyền thấp, ghi mốc thời gian của token **T1**/session **S1** và kết quả API; không log token thô.
2. Thêm role ở IdP/directory. Quan sát T1/S1 có thể tiếp tục dùng quyền cũ.
3. Phát token **T2** hoặc đăng nhập lại S2. Đối chiếu claim mới và authority converter.
4. Thu hồi role. Xem T2/S2 có giữ snapshot quyền cũ không; so với **revocation SLA**.
5. Thực thi token expiry/introspection/revocation, session invalidation hoặc policy lookup theo yêu cầu; kiểm tra mọi node/thiết bị.
6. Lặp lại với cache warm/cold, group sync và hai tenant để phát hiện lệch cache key.

**T1 bất biến sau khi ký**, làm mới JWKS không thay role trong T1. Logout một browser session cũng không mặc định revoke access token đang nằm ở máy khác.

## 11. Lỗi thường gặp và cách sửa

**1. `hasRole('report.read')` cho JWT scope.** Tìm `ROLE_report.read` nhưng token có `SCOPE_report.read`. Sửa theo semantics scope.

**2. `@WithMockUser(roles='ADMIN')` PASS nên kết luận JWT converter đúng.** Sai: annotation tạo ROLE_ADMIN trực tiếp, không chạy converter.

**3. Dính `ROLE_ROLE_ADMIN`.** Converter thêm prefix khi claim đã có prefix. Chuẩn hóa đầu vào và allowlist một lần.

**4. Mất scope sau khi đổi `authoritiesClaimName`.** Converter mới chỉ đọc claim tùy chỉnh. Merge scopes và quyền riêng.

**5. Claim nested bị đọc như root.** Kiểm issuer contract, claim path và type; không fallback admin.

**6. Tin role từ token đúng chữ ký nhưng sai audience.** Thêm audience validator và trust policy cho API.

**7. Gán role theo substring.** `not-admin` khớp `admin`; dùng exact allowlist.

**8. Dùng `JwtAuthenticationConverter` cho OIDC browser mà không có mapper tương ứng.** Hai authentication flow khác nhau.

**9. 403 do CSRF nhưng lại sửa ROLE_.** Test POST với CSRF hợp lệ để phân biệt.

**10. Mở `permitAll` để tránh 403.** Tạo lỗ hổng; sửa mapper, rule hoặc nguồn quyền, luôn có negative tests.

**11. JWT còn claims cũ.** Token self-contained không tự làm mới; cần TTL/revocation/policy lookup.

**12. `HttpSession` giữ SecurityContext cũ.** Kiểm re-auth, session expiration và invalidation khi quyền thay đổi.

**13. JWKS cache bị nhầm với permission cache.** Public key cache liên quan signature, không sửa claims.

**14. Cache thiếu issuer/tenant/resource key.** Có thể làm user khác dùng nhầm quyết định quyền.

**15. Method rule bị bypass vì thiếu `@EnableMethodSecurity` hoặc service gọi bằng `new`.** Inject bean proxy và test deny case.

**16. Thay role prefix toàn app mà không rà rules.** Cần migration và tests trên web/method/JSR-250 theo version.

## 12. Checklist chẩn đoán và kết luận

- [ ] Kiểm tra 401/302/403 xuất phát ở gateway, CSRF, filter hoặc method rule.
- [ ] Xác định đúng `SecurityFilterChain` và type `Authentication`.
- [ ] Đối chiếu actual authorities với rule (prefix, case, scope/role namespace).
- [ ] Xác minh JWT signature, issuer, audience, expiry và token type **trước** khi tin claim.
- [ ] Xác định claim path, type, semantics và allowlist chuyển `roles/groups` thành authorities.
- [ ] Kiểm tra converter được gắn vào đúng authentication flow (JWT API vs OIDC browser).
- [ ] So timestamp của token/session với lúc đổi group/permission.
- [ ] Kiểm tra `HttpSession`/`SecurityContextRepository`, user cache, IdP sync, Redis/gateway policy cache; không nhầm JWKS cache.
- [ ] Đảm bảo cache key phân biệt issuer, subject, tenant, resource/action khi cần.
- [ ] Kiểm thử user đủ quyền và thiếu quyền, sai issuer/aud, malformed role, token cũ/mới, khác tenant.
- [ ] Đặt và đo SLA thu hồi quyền, đặc biệt cho ADMIN/financial operations.
- [ ] Giữ deny-by-default; không tắt CSRF hoặc bỏ `@PreAuthorize` để “chữa” 403.

**Kết luận:** Bảo mật quyền truy cập đúng đòi **nguồn danh tính được tin → converter tạo đúng `ROLE_/SCOPE_` → rule kiểm đúng authority → token/session/cache giữ quyền đủ mới**. Một HTTP 403 không phải lời mời nới quyền; hãy kiểm tra bằng chứng ở từng tầng và sửa root cause, đồng thời chứng minh user không có quyền vẫn bị từ chối.