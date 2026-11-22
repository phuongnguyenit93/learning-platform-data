# Kiểm tra lại endpoint, phân quyền phương thức và tích hợp ngoài sau nâng cấp — Spring Security Servlet

## 1. Mục tiêu và phạm vi

Nâng cấp **Spring Boot / Spring Security** không chỉ là thay version và bảo đảm ứng dụng khởi động được. Điều quan trọng hơn là kiểm tra **hợp đồng bảo mật còn giữ nguyên**: endpoint public vẫn public theo chủ ý, endpoint bảo vệ không bị mở rộng quyền, annotation bảo vệ service thực sự được thực thi, và các hệ thống danh tính/đối tác bên ngoài vẫn hoạt động qua TLS, token, callback và session đúng chuẩn.

Bài dành cho **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring MVC/Servlet**. Các ví dụ dùng DSL `SecurityFilterChain` và `@EnableMethodSecurity`. Một số API và hành vi có thể khác giữa các bản 3.x/6.x; phải đối chiếu phiên bản **thực sự được dependency BOM quản lý**, migration notes/release notes tương ứng và cấu hình của dự án. Đừng hiểu ví dụ này là cam kết mọi bản Spring Boot 3.x có mọi API phụ trợ giống hệt nhau.

Sau bài học, bạn có thể:

1. Lập baseline endpoint và quyền **trước nâng cấp**, đối chiếu **sau nâng cấp** theo principal × HTTP method × URL × resource.
2. Kiểm tra `SecurityFilterChain`, thứ tự matcher, CSRF, CORS, session, entry points và 401/403/302/405.
3. Bảo đảm `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` hoạt động qua Spring AOP proxy, không bị self-invocation hay thay đổi principal/authority semantics.
4. Viết **Spring Boot integration test với MockMvc và Spring Security Test** để phát hiện regression ở HTTP và method security, kể cả các ca quyền chéo owner/tenant.
5. Kiểm tra integrations: OAuth2/OIDC, JWT Resource Server, SAML2, LDAP khi có, và API downstream; phân biệt login, token validation, certificate, network và contract failures.
6. Thiết kế smoke tests, canary, logging an toàn và rollback có điều kiện, không hạ bảo mật chỉ để đạt tỷ lệ test pass.

**Nguyên tắc:** `BUILD SUCCESSFUL`, tất cả beans khởi tạo được hoặc một endpoint `/health` trả 200 **không chứng minh authorization đúng**. Cần có test cho cả **được phép** và **bị từ chối**.

## 2. Bản đồ những thay đổi đáng chú ý khi chuyển lên Spring Security 6

| Khía cạnh | Cần đối chiếu khi nâng cấp | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| Java / Servlet namespace | Java 17+, Spring Framework 6 dùng `jakarta.servlet.*` thay `javax.servlet.*` | Filter custom, servlet listener và thư viện ngoài lỗi compile/runtime |
| Khai báo HTTP security | `SecurityFilterChain` bean thay cách mở rộng `WebSecurityConfigurerAdapter` cũ | Chain mới không chứa matcher/handler của ứng dụng trước đó |
| Matcher | `authorizeHttpRequests`, `requestMatchers`, `securityMatcher`, MVC matcher và thứ tự | Endpoint lọt nhầm chain hoặc rule tổng quát che rule cụ thể |
| Method security | `@EnableMethodSecurity` và method-security advisors | `@PreAuthorize` có trong code nhưng thực tế không chạy |
| Context persistence | `SecurityContextHolderFilter` / explicit save phổ biến trong 6.x | Custom login set ThreadLocal nhưng request tiếp theo anonymous |
| CSRF | Mặc định bảo vệ request thay đổi trạng thái trong web/session context | POST 403 sau nâng cấp, hoặc nguy hiểm hơn: tắt CSRF để “sửa” |
| CORS / preflight | OPTIONS, origin allowlist, credentials/cookie | Browser không thể gọi API dù curl GET được |
| Authentication | Password encoder, principal mapping, roles/scopes prefix | `hasRole`/`hasAuthority` đánh giá khác dự kiến |
| OAuth2 / SAML2 | Callback paths, state/nonce, issuer/metadata, cookies, keys | SSO loop, mismatch signature, invalid state |
| JWT Resource Server | Issuer, audience, algorithms, JWKS, scopes, authority converter | Token của sai API/tenant được nhận hoặc token đúng bị 401 |
| External HTTP client | TLS, truststore, mTLS, redirect, header, timeout, retry, JSON schema | Gọi đối tác lỗi hoặc rò token/credential |
| Session / cluster | SameSite/Domain, session serialization và Redis namespace | Chỉ mất login khi đổi node hoặc qua reverse proxy |

**Không nâng cấp mù quáng từ hướng dẫn của một bản khác.** Ghi lại các version đang chạy, BOM của Spring Boot, Java runtime, Servlet container, IdP adapter, OpenSAML, JDBC driver, Redis client, HTTP client, test libraries và policy security đang có. Với Boot 3, kiểm tra các dependency có dùng `javax.servlet` cũ nhưng chỉ bị nạp trong runtime path hiếm gặp.

### 2.1. Một migration không phải chỉ thay tên API

Một cấu hình cũ có thể dùng các phương thức matcher/authorization đã deprecated hoặc bị loại bỏ. Việc chuyển sang:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
    return http.build();
}
```

Đây chỉ là **đoạn cấu hình minh họa**. Để ứng dụng thực sự xử lý authentication, bạn còn phải cấu hình cơ chế phù hợp (`httpBasic`, `formLogin`, `oauth2Login`, `oauth2ResourceServer`...) và xác định CSRF, CORS, session, exception handling. **Không** mặc định rằng việc đổi `.antMatchers(...)` thành `.requestMatchers(...)` có ý nghĩa path-matching giống tuyệt đối với mọi URL; test những mẫu có wildcard, trailing slash, path variables và encoded path.

## 3. Baseline phải được lưu từ trước nâng cấp

Một bảng regression tối thiểu cần lấy từ **business policy** (không lấy từ “test hiện tại đang pass” nếu nghi ngờ security đã sai từ trước):

| ID | Principal/role | Request | Tài nguyên | Kết quả dự kiến |
| --- | --- | --- | --- | --- |
| E01 | Anonymous | `GET /healthz` | Public health | 200 |
| E02 | Anonymous | `GET /api/reports/101` | Báo cáo Alice | 401 (HTTP Basic/Bearer) hoặc 302 (form login) |
| E03 | Alice, có `SCOPE_reports:read` | `GET /api/reports/101` | Report owner Alice | 200 |
| E04 | Alice, có scope read | `GET /api/reports/202` | Report của Ops | 403 hoặc 404 theo policy |
| E05 | Alice, thiếu export scope | `POST /api/reports/export` + CSRF | Export | 403 |
| E06 | Ops, có `SCOPE_reports:export` | `POST /api/reports/export` + CSRF | Export | 200 |
| E07 | Ops, có scope export | POST export nhưng **thiếu CSRF** trong web session chain | Mutation | 403 |
| E08 | Alice, không có role integration | `GET /api/partner/status` | Downstream status | 403; **không gọi đối tác** |
| E09 | Ops, `ROLE_INTEGRATION` | `GET /api/partner/status` | Downstream status | 200 khi partner mock trả 200 |
| E10 | User đã xác thực | Endpoint không được khai báo | Unknown route | Bị từ chối mặc định |
| E11 | Tenant A | Endpoint có ID thuộc tenant B | Cross-tenant | Bị từ chối, không lộ dữ liệu |
| E12 | JWT sai `aud` | Bearer trên API | Wrong recipient | 401 dù chữ ký đúng |
| E13 | JWT hết hạn/sai issuer | Bearer trên API | Invalid token | 401 |
| E14 | Browser cross-origin | OPTIONS/GET API có CORS hợp lệ | Preflight/actual | Chỉ origin được phép được đáp ứng |
| E15 | Đã login bằng session | Logout rồi dùng ID cũ | Session đã hủy | Không authenticated |

Đây là **baseline mẫu**, không phải hợp đồng cố định cho mọi hệ thống. Form login thường redirect 302 khi chưa xác thực; Resource Server thường trả 401. Có thể che sự tồn tại của đối tượng bằng 404 thay vì 403 để hạn chế ID enumeration. Phải ghi rõ **cách response bị từ chối** và không vô tình đổi semantics sau nâng cấp.

**Test âm là bắt buộc:** nếu chỉ test “Ops export được” mà quên “Alice không export được”, một rule quá rộng có thể lọt production dù tất cả happy-path tests đều xanh.

## 4. Kiểm tra lại endpoint từ ngoài vào trong

### 4.1. `securityMatcher` chọn chain, `requestMatchers` chọn rule trong chain

Ví dụ hai chain (code minh họa, cần imports phù hợp):

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/**")
                .permitAll()
            .anyRequest().authenticated()
        )
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            Customizer.withDefaults()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

**Chú ý:** `@Order` xác định chain nào được xét trước; chain đầu tiên match sẽ xử lý request. Các URL callback/logout cần nằm trong chain thích hợp. Nếu một callback SSO nằm ngoài các chain đã có hoặc lọt vào chain JWT stateless, state/session và authentication có thể bị xử lý sai.

Với Spring MVC, matcher có thể nhạy với cấu hình `HandlerMappingIntrospector`, servlet path, context path và các thay đổi của Spring Framework/Boot. Đừng tin `requestMatchers("/api/**")` sẽ xử lý đúng mọi encoded path/trailing slash mà không test URL thật.

### 4.2. Bốn tình huống phải test với mỗi endpoint nhạy cảm

1. **Anonymous:** endpoint bảo vệ không trả dữ liệu, đúng entry point/redirect.
2. **Authenticated nhưng thiếu authority:** trả 403 hoặc thông báo từ chối theo policy.
3. **Có authority nhưng sai owner/tenant/resource:** vẫn bị từ chối. Scope chung **không** cho phép đọc bản ghi của người khác.
4. **Đúng quyền và đúng resource:** trả 2xx cùng dữ liệu đúng; không cần bypass security để làm test pass.

Ngoài ra phải test **HTTP method**: GET an toàn không tự cho phép POST, DELETE, PATCH; `requestMatchers(HttpMethod.GET, ...)` chỉ bảo vệ GET. Một `anyRequest().permitAll()` không chủ ý có thể mở endpoint mới sau nâng cấp.

### 4.3. 401, 403, 302 và 404

| Response | Khi nào thường gặp | Không nên suy luận |
| --- | --- | --- |
| 401 Unauthorized | Cần authentication hoặc Bearer token không hợp lệ trong API | Mọi 401 đều do token hết hạn; có thể do chain/decoder |
| 403 Forbidden | Authenticated thiếu quyền, hoặc CSRF request bị từ chối | Mọi 403 đều do `hasRole` |
| 302 Found | Form login redirect tới `/login`, hoặc OAuth2/SAML chuyển IdP | Mọi redirect đều là login thành công |
| 404 Not Found | Route không tồn tại hoặc hệ thống chủ động che object không được phép | Mọi 404 đều chứng minh object thực sự không tồn tại |
| 405 Method Not Allowed | Route có tồn tại nhưng method không được mapping | Mọi 405 đều là lỗi security; có thể do MVC route |
| 5xx | App/IdP/Redis/downstream fail, serialization/exception | Không “fix” bằng cách tắt authentication |

Trong regression report, ghi rõ error contract: HTTP status, `WWW-Authenticate`, `Location`, JSON error schema, CORS headers, cache policy và khả năng browser redirect. Không chỉ assert status của happy path.

### 4.4. OPTIONS, CORS và CSRF sau nâng cấp

CORS preflight có thể xuất hiện **trước request thật** khi frontend gọi cross-origin với custom headers/methods. Spring Security cần cấu hình CORS rõ với origins cho phép; credentialed responses không dùng wildcard origin. Một preflight OPTIONS trả 401 không chứng minh GET endpoint không cho user truy cập; nó cho thấy browser sẽ không gửi/đọc request theo policy đang có.

CSRF cần được giữ cho **web app dùng cookie/session authentication**. POST/PUT/PATCH/DELETE không kèm CSRF token có thể trả 403 dù principal có đủ authority. Với API **chỉ** nhận Bearer token trong `Authorization` header và không dùng cookie tự gửi, CSRF strategy có thể khác, nhưng phải xét riêng theo từng chain. **Không tắt CSRF toàn hệ thống chỉ vì test POST fail.**

## 5. Method security: annotation có ở source nhưng phải chứng minh chạy

### 5.1. Từ global method security sang `@EnableMethodSecurity`

Spring Security 6 thường cấu hình:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` được xử lý bởi method-security interceptors/advisors. Việc bật annotation không có nghĩa mọi lời gọi nội bộ đều được intercept; Spring AOP proxy là một phần quan trọng của thiết kế.

| Annotation | Khi nào kiểm tra | Lưu ý |
| --- | --- | --- |
| `@PreAuthorize` | Trước khi method thực thi | Phù hợp cho mutation, ownership guard hoặc authority bắt buộc |
| `@PostAuthorize` | Sau khi method trả kết quả | Side effects có thể **đã xảy ra**, nên không đủ bảo vệ thao tác ghi |
| `@PreFilter` | Lọc từng item tham số trước method | Có thể **âm thầm bỏ item**, không tự 403 toàn bộ batch |
| `@PostFilter` | Lọc từng item kết quả sau method | Không ngăn query đọc dữ liệu chưa được phép; không phù hợp mọi pagination type |

Sau nâng cấp, kiểm tra cả `@Secured`/JSR-250 nếu ứng dụng dùng: chúng có điều kiện enable riêng, không giả định `@EnableMethodSecurity` mặc định bật mọi cơ chế annotation. Với `@RolesAllowed`/`@Secured`, rà lại prefix `ROLE_` và việc bật các chế độ `jsr250Enabled`/`securedEnabled` phù hợp.

### 5.2. `hasRole` khác `hasAuthority`

- `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN` khi dùng default role prefix.
- `hasAuthority("ROLE_ADMIN")` kiểm tra **đúng chuỗi**.
- JWT `scope=reports:read` trong Resource Server mặc định thường thành `SCOPE_reports:read`.
- `hasAuthority("SCOPE_reports:read")` không được thay nhầm bằng `hasRole("reports:read")`.
- Nếu upgrade đổi custom `JwtAuthenticationConverter`, claims, issuer hoặc authority mapper, test **Authentication.getAuthorities() thật** sau xác minh token.

Không tự cộng `ROLE_ADMIN` cho mọi user có scope `admin` nếu đó không phải hợp đồng IdP. Role, scope và permission có semantics riêng, đặc biệt với multi-tenant.

### 5.3. Self-invocation và proxy bypass

```java
@Service
class ReportsService {

    public void controllerEntry() {
        restrictedAction(); // this-call: thường không đi qua Spring AOP proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void restrictedAction() {
        // Hành động nhạy cảm.
    }
}
```

Đây là ví dụ **anti-pattern minh họa**. Test `controllerEntry()` có thể vẫn chạy dù `restrictedAction()` bị đánh dấu đặc quyền, bởi lời gọi trong cùng bean không đi qua proxy. Phải đặt guard ở public method trên Spring-managed bean được gọi qua proxy hoặc dùng cơ chế authorization rõ ràng tại service boundary.

Tránh `new ReportsService(...)` trong controller thay vì inject bean; object tạo bằng tay cũng không có method-security advice. Với proxy mode, final/private methods và một số kiểu self-invocation có thể không được chặn như bạn nghĩ.

### 5.4. Kiểm tra owner/tenant ngoài authority

Có `SCOPE_reports:read` không cho phép đọc **mọi report**. Khi định danh tài nguyên đến từ path parameter, policy cần đối chiếu **owner/tenant từ nguồn server đáng tin**, không tin `owner`/`tenantId` do client ghi trong JSON.

Một biểu thức minh họa:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports:read') and " +
    "@ownershipPolicy.isOwner(#p0, authentication.name)"
)
```

`#p0` là tham số thứ nhất, không phụ thuộc tên tham số có được lưu trong compiled bytecode. `ownershipPolicy` phải là Spring bean. Với ứng dụng nhiều tenant, hàm policy thật phải đối chiếu cả tenant/ACL và kiểm soát race giữa check/use (transaction, optimistic locking hoặc update có điều kiện).

## 6. Dự án runnable: Spring Boot 3.x + Java 17 với endpoint, method security và đối tác ngoài

Ví dụ nhỏ sau tạo một **regression fixture** độc lập để kiểm tra ba lớp: HTTP endpoint, service method, external integration. Nó dùng **HTTP Basic trong test/local** để không cần IdP thật, giữ CSRF mặc định, và **mock client đối tác trong tests**. Mục đích là chứng minh authorization không bị mất trong quá trình nâng cấp.

Tạo project Spring Initializr với Java 17+, Spring Boot 3.x, Gradle Groovy, Spring Web, Spring Security. `@MockBean` được hỗ trợ trong các bản Boot 3.x thường gặp dù đã deprecated ở một số bản mới; ở stack Spring Framework 6.2/Boot 3.4+ có thể chuyển theo kế hoạch sang `@MockitoBean` và điều chỉnh imports.

### 6.1. Dependencies

Phần `dependencies` của `build.gradle` (plugins, BOM, repository/version do Initializr tạo):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Cấu trúc:

```text
src/main/java/com/example/upgradeaudit/
  UpgradeAuditApplication.java
  SecurityConfig.java
  OwnershipPolicy.java
  ReportService.java
  PartnerStatusClient.java
  HttpPartnerStatusClient.java
  PartnerService.java
  ApiController.java
src/main/resources/
  application.yml
src/test/java/com/example/upgradeaudit/
  SecurityRegressionTests.java
```

### 6.2. `UpgradeAuditApplication.java`

```java
package com.example.upgradeaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UpgradeAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(UpgradeAuditApplication.class, args);
    }
}
```

### 6.3. `SecurityConfig.java`

```java
package com.example.upgradeaudit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("local-alice-password"))
                .authorities("SCOPE_reports:read")
                .build(),
            User.withUsername("ops")
                .password(encoder.encode("local-ops-password"))
                .authorities(
                    "ROLE_INTEGRATION",
                    "SCOPE_reports:read",
                    "SCOPE_reports:export"
                )
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/healthz", "/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // CSRF mặc định được giữ. POST có mutation cần token nếu
        // dùng chain này trong mô hình browser/session.
        return http.build();
    }
}
```

Cấu hình demo có username/password chỉ để test nội bộ; trong môi trường thật, dùng IdP/user store, MFA và secret management theo chính sách. HTTP Basic phải qua HTTPS, không dùng credential demo lên mạng công cộng. `SCOPE_reports:*` ở đây là **authority được cố ý cấp trong fixture**, không phải claim JWT đã được xác minh.

**Hai lớp bảo vệ:** HTTP yêu cầu `.authenticated()` cho `/api/**`, còn service quyết định **quyền và tài nguyên cụ thể** bằng `@PreAuthorize`. Nếu method-security advice mất sau nâng cấp, test negative case sẽ phát hiện dù HTTP filter vẫn cho người đã xác thực đi qua.

### 6.4. `OwnershipPolicy.java` — nguồn quyền server-side

```java
package com.example.upgradeaudit;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component("ownershipPolicy")
public class OwnershipPolicy {

    private static final Map<Long, String> OWNERS =
        Map.of(101L, "alice", 202L, "ops");

    public boolean isOwner(long id, String username) {
        return username != null
            && username.equals(OWNERS.get(id));
    }

    public String ownerOf(long id) {
        return OWNERS.get(id);
    }
}
```

Đây là dữ liệu **in-memory nhỏ cho test**, không phải ACL production. Với hệ thống thật, xác minh owner và tenant trong repository hoặc policy service, không tin trường `owner` trong HTTP body. Nếu ID không tồn tại, `isOwner` trả false: demo chọn fail-closed thay vì lộ dữ liệu. Quyết định trả 403 hay 404 cho ID sai phải nhất quán với product contract.

### 6.5. `ReportService.java` — method-level guards

```java
package com.example.upgradeaudit;

import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final OwnershipPolicy ownership;

    public ReportService(OwnershipPolicy ownership) {
        this.ownership = ownership;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_reports:read') and " +
        "@ownershipPolicy.isOwner(#p0, authentication.name)"
    )
    public Map<String, Object> getReport(long id) {
        return Map.of(
            "id", id,
            "owner", ownership.ownerOf(id)
        );
    }

    @PreAuthorize("hasAuthority('SCOPE_reports:export')")
    public String export() {
        return "exported";
    }
}
```

Phần `getReport` không nên được gọi trực tiếp bằng `new ReportService(...)`; hãy inject bean qua Spring. Method `export()` chỉ trả string demo, **không có side effect thực**. Khi thật sự xuất dữ liệu hoặc ghi file, cần additional policy cho tập report, tenant, dữ liệu nhạy cảm, audit và nơi lưu output.

Nếu `@PreAuthorize` không hoạt động, Alice có thể xem report 202 hoặc export. Vì vậy đây là fixture phát hiện regression method security, không chỉ một ví dụ happy path.

### 6.6. `PartnerStatusClient.java` — cổng tích hợp ngoài

```java
package com.example.upgradeaudit;

public interface PartnerStatusClient {
    String status();
}
```

Tách interface khiến test có thể thay dependency bên ngoài bằng mock. Việc mock giúp kiểm tra security behavior ổn định, nhưng **không kiểm tra contract TLS/JSON/status code thật**; cần test riêng ở mục 10.

### 6.7. `HttpPartnerStatusClient.java` — HTTP client Java 17

```java
package com.example.upgradeaudit;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class HttpPartnerStatusClient implements PartnerStatusClient {

    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

    private final URI endpoint;

    public HttpPartnerStatusClient(
            @Value("${partner.status-url}") String url) {
        endpoint = URI.create(url);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                "Partner endpoint must use HTTPS");
        }
    }

    @Override
    public String status() {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        try {
            HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                    "Partner HTTP " + response.statusCode());
            }
            return response.body();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Partner call interrupted", ex);
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Partner transport failure", ex);
        }
    }
}
```

Class này **biên dịch với JDK 17**, có connection/request timeouts và yêu cầu URL HTTPS. Không forward `Cookie`/Authorization của người dùng cho đối tác một cách ngầm định. Nếu cần OAuth2 client credentials, service token hoặc mTLS, phải cấu hình **riêng** và test audience/scope/trust theo hợp đồng.

Trong production, nên xử lý response body/content-type/schema, giới hạn response size, retry/backoff cho tác vụ idempotent, circuit breaker và telemetry an toàn. HTTP status khác 200 trong mẫu sẽ thành `IllegalStateException`; nó không tự map sang gateway status chuẩn. Đó là chủ ý **đơn giản hóa test**, không phải mẫu xử lý lỗi vận hành đầy đủ.

### 6.8. `PartnerService.java` — không gọi đối tác nếu thiếu quyền

```java
package com.example.upgradeaudit;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PartnerService {

    private final PartnerStatusClient client;

    public PartnerService(PartnerStatusClient client) {
        this.client = client;
    }

    @PreAuthorize("hasRole('INTEGRATION')")
    public String readStatus() {
        return client.status();
    }
}
```

`hasRole('INTEGRATION')` tương ứng authority `ROLE_INTEGRATION` theo prefix thông thường. Annotation đặt **trước** network call. Alice không có role này; method phải từ chối trước khi `client.status()` được gọi. Đó là một negative test quan trọng sau nâng cấp.

### 6.9. `ApiController.java` — routes thật qua SecurityFilterChain

```java
package com.example.upgradeaudit;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final ReportService reports;
    private final PartnerService partner;

    public ApiController(
            ReportService reports,
            PartnerService partner) {
        this.reports = reports;
        this.partner = partner;
    }

    @GetMapping("/healthz")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports/{id}")
    public Map<String, Object> report(@PathVariable long id) {
        return reports.getReport(id);
    }

    @PostMapping("/api/reports/export")
    public String export() {
        return reports.export();
    }

    @GetMapping("/api/partner/status")
    public String partner() {
        return partner.readStatus();
    }
}
```

`/healthz` là public để kiểm tra tiến trình, không lộ secrets/config. Ứng dụng sản xuất có thể tách liveness/readiness và quyền truy cập, nhưng public health không nên bao gồm danh sách user/tenant, token hay cấu hình IdP/Redis.

### 6.10. `application.yml`

```yaml
partner:
  status-url: https://partner.example.test/status
```

Đây là **URL minh họa**, không phải server có thật. Tests dưới đây dùng mock nên không gọi mạng ngoài. Khi chạy `/api/partner/status` trên app demo mà không mock, phải cấu hình đối tác test thực qua biến môi trường/config bên ngoài; không ép production HTTP client trust mọi certificate để được 200.

## 7. Regression tests runnable: MockMvc, CSRF, method security, external boundary

File `src/test/java/com/example/upgradeaudit/SecurityRegressionTests.java`:

```java
package com.example.upgradeaudit;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRegressionTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService reports;

    @MockBean
    PartnerStatusClient partnerClient;

    @Test
    void publicHealthIsAccessible() throws Exception {
        mvc.perform(get("/healthz"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOnlyOwnReport() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(httpBasic("alice", "local-alice-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        mvc.perform(get("/api/reports/202")
                .with(httpBasic("alice", "local-alice-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void exportNeedsCsrfAndAuthority() throws Exception {
        // 403 do thiếu CSRF, dù Ops có quyền export.
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("ops", "local-ops-password")))
            .andExpect(status().isForbidden());

        // 403 do thiếu authority, dù Alice có CSRF token.
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("alice", "local-alice-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports/export")
                .with(httpBasic("ops", "local-ops-password"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("exported"));
    }

    @Test
    void missingIntegrationRoleNeverCallsPartner() throws Exception {
        when(partnerClient.status()).thenReturn("UP");

        mvc.perform(get("/api/partner/status")
                .with(httpBasic("alice", "local-alice-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/partner/status")
                .with(httpBasic("ops", "local-ops-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("UP"));

        verify(partnerClient, times(1)).status();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"SCOPE_reports:read"}
    )
    void directServiceProxyEnforcesOwnership() {
        assertThrows(AccessDeniedException.class,
            () -> reports.getReport(202L));
    }
}
```

### 7.1. Test bảo đảm được điều gì?

- **HTTP filter chain:** anonymous bị 401 trong Basic-auth fixture, health vẫn public.
- **Object-level permission:** Alice không đọc được ID 202 do server-side owner policy, dù có `SCOPE_reports:read`.
- **CSRF:** POST thiếu CSRF token bị chặn, và POST đủ CSRF nhưng thiếu authority cũng bị chặn.
- **Method security:** annotation thực thi trên bean `ReportService` được Spring inject; test fail nếu interceptor không chạy.
- **External boundary:** user thiếu `ROLE_INTEGRATION` **không gọi HTTP client đối tác**; chỉ Ops được phép gọi.
- **Positive path:** Ops có authority export và CSRF token thực hiện được demo export.

`@MockBean` tạo mock `PartnerStatusClient`, không chứng minh HTTPS, JSON schema, DNS, mTLS hay timeout của API thực. `@WithMockUser` ở test service chỉ cấp authentication giả: không chứng minh password/JWT được xác minh. Vì vậy test HTTP auth thực trong fixture vẫn dùng `.with(httpBasic(...))` và password encoder của application.

### 7.2. Chạy test

Trong project Gradle có Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu tạo đủ các file và dependencies như ở trên trong dự án Spring Boot 3.x phù hợp, các test **dự kiến pass**. Đây không phải stdout thực đã được ghi lại trên hệ thống người học. Test chạy trong JVM, không cần host đối tác thật; không sử dụng `idp.example.test` hay chứng thư thực.

Sau nâng cấp, chạy cùng test suite trên **phiên bản cũ và phiên bản mới**, so kết quả. Test cũng nên fail có chủ ý khi tạm tắt `@EnableMethodSecurity` trong môi trường thử nghiệm: nếu test âm vẫn pass, có thể fixture chưa đi qua advice thật.

### 7.3. Tại sao không chỉ dùng `@WithMockUser`?

`@WithMockUser` rất tốt để kiểm tra **authorization**. Nhưng nó không xác minh `AuthenticationManager`, session cookie, Bearer JWT signature/issuer/audience hoặc IdP login. Nếu cả regression suite chỉ dùng mock user, một thay đổi decoder/authority converter nguy hiểm có thể không bị phát hiện.

Nên tách:
- Method security test với principal giả để thử policy matrix.
- HTTP integration với authentication mechanism thật hoặc test token/decoder đã được kiểm soát.
- Contract/E2E login/token test với IdP thử nghiệm và certificates/key rotation.
- Browser/proxy test cho CORS/SameSite/redirect/CSRF khi có cookie-authenticated flows.

## 8. Java 17 độc lập: policy matrix không cần Spring

Để học cách viết test **được phép và bị từ chối**, tạo file `UpgradePolicySmoke.java`:

```java
import java.util.Map;
import java.util.Set;

public class UpgradePolicySmoke {

    private static final Map<Long, String> OWNER =
        Map.of(101L, "alice", 202L, "ops");

    static int read(
            String username,
            Set<String> authorities,
            long reportId) {

        if (username == null) return 401;
        if (!authorities.contains("SCOPE_reports:read")) return 403;
        if (!username.equals(OWNER.get(reportId))) return 403;
        return 200;
    }

    static int export(
            String username,
            Set<String> authorities,
            boolean csrfValid) {

        if (username == null) return 401;
        if (!csrfValid) return 403;
        return authorities.contains("SCOPE_reports:export")
            ? 200 : 403;
    }

    public static void main(String[] args) {
        System.out.println("anonymous=" +
            read(null, Set.of(), 101L));
        System.out.println("alice-own=" +
            read("alice", Set.of("SCOPE_reports:read"), 101L));
        System.out.println("alice-other=" +
            read("alice", Set.of("SCOPE_reports:read"), 202L));
        System.out.println("alice-export=" +
            export("alice", Set.of("SCOPE_reports:read"), true));
        System.out.println("ops-export=" +
            export("ops", Set.of("SCOPE_reports:export"), true));
        System.out.println("ops-no-csrf=" +
            export("ops", Set.of("SCOPE_reports:export"), false));
    }
}
```

Biên dịch/chạy:

```bash
javac UpgradePolicySmoke.java
java UpgradePolicySmoke
```

**Stdout chính xác:**

```text
anonymous=401
alice-own=200
alice-other=403
alice-export=403
ops-export=200
ops-no-csrf=403
```

**Giới hạn:** Đây chỉ là policy matrix bằng Java thuần, không có `SecurityFilterChain`, `AuthenticationManager`, CSRF token repository hay HTTP thật. Nó **không** thay thế suite MockMvc ở mục 7; tác dụng là giúp người học thấy rõ các negative cases phải tiếp tục được kiểm thử sau nâng cấp.

## 9. Kiểm tra JWT Resource Server sau nâng cấp

Một API nhận Bearer JWT cần xác thực token **và** áp quyền. Nếu dùng Resource Server, regression test tối thiểu:

1. **Chữ ký và thuật toán:** token được ký bởi key tin cậy, không chấp nhận `alg` không được cho phép; JWKS URL/key rotation phù hợp.
2. **Issuer:** `iss` bằng issuer dự kiến; không tự tin issuer lạ chỉ vì nó trỏ tới JWKS công khai.
3. **Audience:** `aud` phải chứa API audience đã thỏa thuận. Token dành cho frontend hoặc API khác không đủ quyền dùng tại API này.
4. **Thời gian:** hết hạn `exp`, chưa tới `nbf`, chênh lệch đồng hồ theo validator thích hợp; test JWT expired/not-yet-valid.
5. **Loại token:** không chấp nhận ID Token như access token chỉ vì chữ ký và subject hợp lệ.
6. **Authorities:** `scope` hoặc `scp` mặc định thường thành `SCOPE_xxx`; custom claims role/permission phải qua converter có kiểm soát.
7. **Object/tenant:** token có `reports:read` vẫn bị từ chối khi request report thuộc tenant khác.
8. **401/403:** invalid token phải 401; valid token nhưng thiếu quyền phải 403 theo contract.
9. **Key rollover:** JWKS metadata/cache/algorithm và keys mới/cũ được phối hợp có overlap; không tắt signature validation.
10. **Opaque token:** nếu dùng introspection, kiểm tra endpoint, client credential, `active`, TTL/cache và permission mapping riêng; JWT converter không chạy ở nhánh opaque.

Ví dụ method policy:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports:read') and " +
    "@ownershipPolicy.isOwner(#p0, authentication.name)"
)
```

Nếu Authentication của Resource Server có username lấy từ `sub`, còn ownership DB dùng một internal user ID khác, cần identity mapping rõ. Không coi email/username display là khóa owner bất biến khi IdP cho phép đổi email hoặc user thuộc nhiều tenant.

**Thử đúng bộ test:** `SecurityMockMvcRequestPostProcessors.jwt()` tiện để test HTTP authorization nhưng thường tạo Authentication test và có thể **bỏ qua JWT decoder/validator/converter thật**. Bổ sung decoder unit tests với token ký bằng test key, hoặc end-to-end với IdP thử nghiệm. Không tuyên bố JWT validation đã pass chỉ vì `.with(jwt())` cho 200.

## 10. Kiểm tra OAuth2/OIDC, SAML2 và tích hợp danh tính khác

### 10.1. OAuth2 Client / OIDC login

Kiểm tra từ đầu tới cuối:

- `authorization-uri`, `token-uri`, `jwk-set-uri`, discovery metadata, client ID, client authentication method và client secret rotation.
- Redirect URI **khớp chính xác** với URL IdP đã đăng ký, kể cả scheme/host/port/path sau reverse proxy.
- `state` ràng buộc authorization request/callback để chống CSRF; **không bỏ** kiểm tra state khi login lỗi.
- PKCE verifier/challenge nếu flow/client yêu cầu; với public clients thường bắt buộc hoặc được khuyến nghị mạnh tùy profile.
- OIDC `nonce` khi dùng ID Token; `iss`, `aud`, `exp`, signature và nonce được xác minh đúng.
- Scope/claims và cách chúng trở thành `GrantedAuthority` trên `OAuth2AuthenticationToken`/`OidcUser` theo logic app.
- Session, SameSite cookie và `authorization_request_not_found` khi callback không mang cookie.
- Refresh token handling/revocation/log redaction, khi tích hợp gọi downstream bằng delegated token.

Không nhầm **OAuth2 login của browser** với **JWT Resource Server xác minh Bearer token**. Chúng có filter chain và chính sách session khác nhau.

### 10.2. SAML2 Service Provider

Nếu dùng SAML2:

- IdP/SP entityID, Assertion Consumer Service URL, SSO/SLO endpoints, binding và public URL sau proxy.
- SAML Response/assertion signature và certificate verification (IdP signing cert), khả năng xoay vòng nhiều khóa.
- SP signing credential nếu cần signed AuthnRequest/LogoutRequest; decryption credential nếu assertion được mã hóa.
- `InResponseTo`, `Destination`, `Audience`, time conditions, `NameID`, `SessionIndex` và correlation.
- HTTP-POST callback/SLO với browser `SameSite` cookie policy; **không bỏ signature/correlation** để chữa lỗi.
- Multi-node: session/correlation data có chung store và serializer tương thích.

Nâng cấp dependency có thể kéo theo thay đổi OpenSAML, metadata parser, XML security defaults hoặc certificate algorithm support. Hãy test cả login hợp lệ và response sai chữ ký/issuer/destination; không chỉ test happy path.

### 10.3. LDAP / directory integration

Nếu app xác thực qua LDAP/AD:

- Provider URL/TLS/StartTLS, truststore, certificate, bind service account.
- User DN pattern, filter escaping, group-to-role mapping, case sensitivity và nested groups.
- Tài khoản disabled/locked/password expired; failure semantics đúng policy.
- Không log password/bind credentials. Với input user/tenant, dùng LDAP filter escaping đúng chuẩn để chống injection.
- Khi directory unavailable, không fallback cho phép người dùng bất kỳ.

### 10.4. API downstream / đối tác ngoài

| Contract | Test tối thiểu | Nếu thay đổi |
| --- | --- | --- |
| DNS/URL | Đúng host/path/port/scheme, redirects | Sai endpoint hoặc chuyển HTTP không an toàn |
| TLS/mTLS | Trusted CA, hostname verification, certificate/key rotation | SSLHandshakeException, client bị từ chối |
| Authentication | Service token, client credentials, mTLS, API key theo vault | 401/403 từ đối tác |
| OAuth2 audience/scope | Token đúng resource và quyền outbound | Token hợp lệ nhưng bị partner 403 |
| Headers | `Content-Type`, `Accept`, correlation ID, idempotency key | Partner từ chối hoặc parse sai |
| HTTP status | 200/201/204, 400/401/403, 409/429, 5xx | Retry sai, duplicate write, data loss |
| JSON/XML schema | Bắt buộc/optional fields, enum, dates/timezone, nullability | Deserialization lỗi hoặc silent data corruption |
| Timeout | Connect/read/request timeout, cancel | Thread bị treo, exhaustion pool |
| Retry | Chỉ retry hợp đồng cho phép, backoff/jitter, rate limit | Gửi lặp POST ghi dữ liệu |
| Circuit breaker | Giảm tải khi partner unhealthy, fallback đúng policy | Fail-open hoặc bùng lỗi dây chuyền |
| Telemetry | Trace/correlation ID, latency, error rate | Không phân biệt lỗi network với auth |
| Redaction | Không log Authorization/Cookie/secrets/PII | Rò token hoặc dữ liệu người dùng |

**Không chuyển thẳng browser session cookie hoặc user access token sang đối tác** trừ khi đã có thiết kế token delegation/on-behalf-of đúng audience và scope. API outbound nên sử dụng credential riêng có quản lý secret và vòng đời rotation rõ ràng.

## 11. Contract tests cho tích hợp ngoài không phụ thuộc production

Có ba tầng kiểm thử bổ sung nhau:

1. **Test security boundary bằng mock bean:** như mục 7, xác minh user thiếu quyền không gọi client; partner trả `"UP"` chỉ khi Ops được phép. Nhanh, determinist, tốt cho CI.
2. **HTTP client contract test bằng local fake server:** kiểm tra method/path/header, body/schema, timeout, 429/5xx, redirect, retry/idempotency. Có thể dùng WireMock, MockWebServer hoặc JDK `HttpServer` trong môi trường test; không cần truy cập đối tác production.
3. **Staging/partner sandbox E2E:** kiểm tra DNS, TLS chain/mTLS, service token, issuer/audience, real schema và rate limits; có test account, data cleanup, approved network/secret management.

Ví dụ `HttpPartnerStatusClient.status()` hiện tại từ chối non-200; trong sandbox cần test phân biệt 401 do credential, 403 do scope, 429 do rate limit và 503 do outage. Không lập trình retry vô hạn và không mask 401 thành kết quả `"UP"`.

Nếu bật Java TLS debug để điều tra handshake, chỉ dùng trong môi trường cô lập vì trace có thể nhạy cảm và rất lớn. Không gửi private key/client secret vào issue tracker.

## 12. Tách test endpoint, method security và integration failures

Một pipeline regression có thể chia theo lớp:

| Lớp | Công cụ | Cần xác minh | Không tự chứng minh |
| --- | --- | --- | --- |
| Compile/static | Gradle, javac, dependency check | Java/Jakarta imports, API tồn tại | Access policy đúng |
| Unit policy | JUnit 5 | Chính sách role, owner, tenant | Spring AOP/filter chạy |
| Method integration | `@SpringBootTest`, `@WithMockUser` | Proxy/interceptor và `@PreAuthorize` | Token/cookie/IdP thật |
| HTTP integration | MockMvc + Spring Security | 401/403/200/CSRF/route | Reverse proxy/browser SameSite |
| JWT decoder test | Test keys/JWKS | iss/aud/expiry/signature/converter | IdP production rotation |
| External client contract | Local fake service | headers/body/status/timeouts/retry | Real partner TLS/network |
| Browser E2E | Browser + staging ingress | Cookie, SameSite, CORS, redirects, SSO | Failure handling tại prod topology |
| Multi-node | Hai pod và shared session store | Cookie/session continuity, logout, serialization | Mọi incident Redis failover |
| Canary/monitoring | Runtime metrics và rollback | Drift security/error/latency ngoài staging | Thay thế negative test policy |

**Lưu ý về test false positive:** một test dùng `.with(user("alice"))` không chứng minh Alice login thật; `.with(jwt())` không chứng minh chữ ký token đã được validate; mock partner không chứng minh TLS. Viết rõ **tầng nào được kiểm chứng** trong kết quả QA.

### 12.1. Negative cases bắt buộc

- Anonymous truy cập endpoint private, user thiếu role, user đủ role nhưng sai owner/tenant.
- Form POST thiếu/invalid CSRF; CORS preflight từ origin lạ.
- JWT expired, wrong issuer/audience, wrong algorithm/key, thiếu scope.
- SAML Response sai signature/destination; OAuth2 state mismatch/PKCE verifier sai.
- Endpoint không có matcher cụ thể, URL có trailing slash/encoded path, method GET khác POST.
- Method bị gọi từ bean khác và self-invocation path để phát hiện proxy bypass.
- Partner trả 401/403/429/5xx, TLS handshake failure, JSON lỗi, timeout, retry.
- Session hết hạn, logout cookie cũ, đổi node khi có Redis shared store.
- Browser callback POST cross-site với SameSite đúng/không đúng.
- Nhiều tenant cùng username nhưng resource khác nhau.

### 12.2. Kiểm tra security response thay vì chỉ body

Test cần assert thêm khi hợp đồng yêu cầu:

- `Cache-Control`/`Pragma` không cho cache dữ liệu nhạy cảm.
- Không in stack trace, token, JWT claims nhạy cảm trong error JSON.
- CORS origin/credentials chỉ khớp allowlist.
- `WWW-Authenticate`/redirect cho 401 theo mechanism.
- Session cookie `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, expiry.
- 403 không rò thông tin object của tenant khác.
- Endpoint actuator/debug/docs được bảo vệ như baseline, không vô tình permit all.
- Downstream calls chỉ được kích hoạt **sau** authorization guard; không tạo side effect khi denied.

## 13. Các vấn đề đặc thù khi cập nhật Java, Servlet và proxy

### 13.1. Jakarta namespace

Khi chuyển stack Boot 2.x → 3.x:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Các thư viện/filter custom còn import `javax.servlet.*` có thể không biên dịch hoặc không hoạt động đúng trên Servlet container mới. Đây là khác biệt **namespace**, không phải lý do bỏ filter security; cần nâng cấp dependency tương thích Jakarta.

### 13.2. Reverse proxy và forwarded headers

Sau nâng cấp, public URL có thể vẫn là `https://app.example.test` nhưng app thấy `http://service:8080`. Hậu quả: redirect tới HTTP nội bộ, `Secure` cookie không quay lại, OAuth2 `redirect_uri` mismatch hoặc SAML Destination mismatch.

Spring Boot có property:

```yaml
server:
  forward-headers-strategy: framework
```

Chỉ dùng khi reverse proxy **được tin cậy** đã loại forwarded headers do client internet giả mạo và phát sinh lại đúng. Không bật trust `X-Forwarded-Host`/`X-Forwarded-Proto` tùy ý để sửa một callback; đó là rủi ro host injection/open redirect.

### 13.3. Session và explicit save

Spring Security 6 có cơ chế explicit-save của SecurityContext phổ biến. Nếu một custom login handler chỉ gọi:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

rồi trả response, request kế tiếp có thể anonymous. Cần dùng đúng `SecurityContextRepository.saveContext(...)` trong flow xác thực, session fixation strategy và response commit ordering. Standard `formLogin`/`oauth2Login` filters thường xử lý phần việc đó; đừng tự viết login nếu không cần.

### 13.4. Session cookie và nhiều node

Với form/OIDC/SAML login, browser cần gửi cookie correlation/session đúng vào callback. Test `Secure`, SameSite `Lax`/`None` khi có cross-site POST, host-only Domain, Path, `JSESSIONID`/`SESSION` và Redis/Spring Session namespace. Nếu chỉ mất login khi đổi pod, nghĩ đến session store/serializer thay vì đổi mật khẩu.

Nâng cấp không nên đồng thời thay cookie name, Redis namespace, serializer và security DSL trong một lần rollout không có kế hoạch; điều đó khiến phân tích nguyên nhân khó và có thể gây logout hàng loạt.

## 14. Quy trình nâng cấp và rollback có kiểm soát

### 14.1. Trước khi nâng cấp

1. Khóa bản đồ dependency/BOM/JDK/Jakarta, snapshot config security chain và các IdP/partner endpoints.
2. Thu thập baseline matrix ở mục 3, đặc biệt các **negative tests** và tenant/owner policy.
3. Xác nhận endpoints public/health/admin, callback, CORS, CSRF, logout, cookie/session policy.
4. Ghi nhận certificates/JWKS, expiry, truststore, mTLS, client credentials và kế hoạch rotation.
5. Kiểm tra external API schema/version, rate-limit/timeout và sandbox test data.
6. Chụp baseline metrics của `401`, `403`, login success/error, token validation, latency, Redis failures, partner 4xx/5xx.

### 14.2. Trong khi nâng cấp

1. Cập nhật dependency theo BOM của Spring Boot và migration guides phù hợp, không trộn Spring Framework/Servlet API version thủ công.
2. Chuyển config `SecurityFilterChain`, method security, Jakarta imports, principal/authority mapper theo cách có thể kiểm soát.
3. Chạy unit + method + MockMvc + JWT decoder tests; kiểm tra **negative cases**.
4. Test external services ở mock/sandbox, TLS/mTLS, issuer/audience, callback state/nonce/SAML signature.
5. Test browser flow với proxy/ingress và session nhiều node.
6. So sánh kết quả với baseline, lập danh sách các thay đổi **được phê duyệt** và regression phải sửa.

### 14.3. Canary và production

- Rollout một phần traffic hoặc một nhóm test accounts trước, giữ metrics per version/pod để so sánh.
- Cảnh báo tăng bất thường `401/403`, SSO callback errors, CSRF denials, JVM exceptions, Redis misses, TLS handshake, partner timeout/retry rate.
- Có correlation IDs xuyên qua browser → gateway → Spring → partner, nhưng **không log raw Cookie, Authorization, assertion, refresh token hoặc private key**.
- Test canary cả positive và negative route, không chỉ `/health`.
- Khi có regression bảo mật (mở quyền không dự kiến), **rollback/disable route theo runbook**; không giữ release vì happy-path vẫn chạy.
- Nếu thay session serializer/cookie name/database schema khiến rollback đọc dữ liệu cũ không được, cần migration/dual-read strategy hoặc kế hoạch đăng nhập lại có kiểm soát. Không giả định rollback binary luôn khôi phục trạng thái.
- Phân biệt lỗi 401/403 tăng do policy cố ý thay đổi với lỗi thật bằng baseline đã duyệt và diagnostics, không tự nới authorization để giảm metrics.

### 14.4. Tiêu chí Go/No-Go

**Go** khi:

- Không có endpoint public/private bị đổi ngoài quyết định đã duyệt.
- Tất cả test user × role × scope × tenant × action đạt kỳ vọng.
- JWT/SAML/OIDC validation vẫn chặn invalid token/message.
- CSRF/CORS/cookie/browser callbacks không bị phá.
- External sandbox contract, TLS, auth, timeout, lỗi và retry pass.
- Multi-node session/canary metrics chấp nhận được.
- Rollback/incident response có thể thực hiện theo kế hoạch.

**No-Go** nếu phát hiện `permitAll` không chủ ý, `@PreAuthorize` bị bỏ qua, token sai audience vẫn được chấp nhận, CSRF bị tắt không được duyệt, dữ liệu tenant khác lộ, client outbound gửi credential sai đích hoặc key/cert verification bị bỏ.

## 15. Bảng chẩn đoán nhanh sau nâng cấp

| Triệu chứng | Nguyên nhân có thể | Kiểm chứng |
| --- | --- | --- |
| Endpoint trước đây protected giờ trả 200 anonymous | Matcher/thứ tự chain/permitAll sai | HTTP test anonymous và effective SecurityFilterChain |
| Endpoint trước public giờ 401 | Rule tổng quát che permitAll hoặc chain API match nhầm | Kiểm tra securityMatcher và rule order |
| Method có @PreAuthorize nhưng thiếu quyền vẫn chạy | @EnableMethodSecurity thiếu, proxy bypass, self-invocation | Gọi Spring-managed service bean trong test negative |
| HTTP GET chạy, POST trả 403 | CSRF hoặc permission/matcher riêng theo method | Test POST có/không CSRF và scope |
| Scope JWT đúng mà API 403 | Converter mất `SCOPE_`, claim `scp`/`scope`, principal mapping | Kiểm tra authorities sau decoder và policy expression |
| Token sai audience được nhận | Không bật audience validator đúng API | JWT negative test với `aud` khác |
| API 401 dù browser đã login web | API chain stateless Bearer-only | Kiểm tra securityMatcher/Authorization header |
| Login xong request sau anonymous | Custom auth không saveContext hoặc cookie/session mất | MockMvc two-request, DevTools Set-Cookie/Cookie |
| OAuth2 callback state mismatch | Cookie không quay lại, repo auth request khác | SameSite/redirect URI/Redis correlation |
| SAML login fail sau nâng cấp | Signing certificate/binding/parser/metadata khác | Xem IdP/SP logs đã redacted và signature validation |
| Browser CORS fail nhưng curl OK | Preflight OPTIONS/CORS credentials/allowed origin | Browser network + MockMvc preflight |
| HTTPS trên browser nhưng app redirect HTTP | Proxy forwarded headers sai | Kiểm tra public scheme và trust proxy |
| Partner 401/403 | Service token/cert/scope/audience/client auth sai | Sandbox contract test, partner logs |
| Partner timeout/chậm | Connect/read timeout/retry không kiểm soát | Fake server delay/429, tracing |
| API trả 500 sau JSON change | Schema/null/enums/serialization không tương thích | Contract test request/response |
| Chỉ một pod lỗi login | Session namespace/serializer/keys/config lệch | So effective config/version ở từng pod |
| MockMvc pass nhưng production fail | Browser/TLS/IdP/Redis/multi-node chưa được test | E2E/canary, kiểm tra test scope |
| Test `.with(jwt())` pass dù decoder lỗi | Đã bypass JWT decoder thật | Test token ký bằng key thử nghiệm/IdP |
| Role ADMIN của app khác có tác dụng | Trust/claim mapper lấy role ngoài đúng audience | Giới hạn issuer/audience và claim path |

## 16. Checklist bàn giao cho nhóm vận hành và QA

- [ ] Lưu version cũ/mới: Java, Spring Boot, Spring Security, Servlet container, Jackson, Redis, OpenSAML, OAuth2/JWT libraries và external HTTP clients.
- [ ] Kiểm tra `SecurityFilterChain` và thứ tự `securityMatcher`/`requestMatchers`, including unknown endpoint deny-by-default.
- [ ] Test anonymous, thiếu authority, đủ authority, sai owner/tenant và đúng owner/tenant cho từng endpoint nhạy cảm.
- [ ] Test HTTP method GET/POST/PUT/PATCH/DELETE, CSRF, CORS OPTIONS và error contract 401/403/302/404/405.
- [ ] Bật `@EnableMethodSecurity`, xác minh `@PreAuthorize` và các annotation thực dùng qua bean proxy, không self-invocation.
- [ ] Rà `hasRole`/`hasAuthority` prefixes, JWT scope `SCOPE_`, custom principal/claims và tenant-bound permissions.
- [ ] Với JWT, test signature, issuer, audience, expiry, key rollover, opaque introspection nếu có.
- [ ] Với OAuth2/OIDC, test redirect URI, state, PKCE/nonce, cookie/session correlation và IdP secret rotation.
- [ ] Với SAML2, test ACS/SLO metadata, signatures, certificates, session correlation và binding.
- [ ] Với LDAP/directory, test TLS/bind/filter/group mapping và error behavior khi directory unavailable.
- [ ] Với đối tác ngoài, test TLS/mTLS, credentials, audience/scope, payload schema, HTTP errors, timeout, retry và **không leak token**.
- [ ] Chạy MockMvc, real token/IdP sandbox, browser behind proxy, và multi-node session tests; ghi rõ giới hạn mỗi lớp test.
- [ ] Quan sát canary metrics 401/403, CSRF, login callbacks, partner 4xx/5xx, timeout, Redis và TLS handshake theo release.
- [ ] Có rollback được kiểm tra với session/schema compatibility, không phải chỉ khả năng redeploy code cũ.
- [ ] Không bỏ signature, CSRF, tenant/object-level policy hoặc TLS verification để làm regression suite xanh.

**Kết luận:** sau nâng cấp Spring Security Servlet, phải kiểm tra theo ba vòng độc lập nhưng liên kết: **HTTP endpoint được match và xác thực đúng → method security áp đúng authority và object-level policy → tích hợp danh tính/downstream xác minh token, certificate, request/response và xử lý lỗi đúng**. Bộ kiểm thử đáng tin phải cố gắng chứng minh cả **“đúng người được phép”** và **“sai người bị từ chối”**, rồi dùng E2E/canary để xác minh những phần MockMvc không thể mô phỏng như browser, proxy, IdP và hạ tầng đa node.
