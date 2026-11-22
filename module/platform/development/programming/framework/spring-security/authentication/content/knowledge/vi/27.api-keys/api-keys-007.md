# Ngăn cơ chế API key trở thành đường bỏ qua xác thực mạnh hơn

## 1. Vấn đề và mục tiêu

Ứng dụng Spring Security có thể đang bảo vệ các API quan trọng bằng OAuth2 JWT, OIDC, MFA hoặc xác thực lại trước thao tác nhạy cảm. Để phục vụ một job hay hệ thống đối tác, đội kỹ thuật thêm API key. Nếu không thiết kế ranh giới, một API key đúng có thể trở thành **đường xác thực thay thế** và bỏ qua chính sách mạnh ban đầu.

Tình huống sai điển hình: endpoint `POST /api/payments/approve` chỉ nên nhận access token của người dùng đã MFA và có quyền duyệt. Một filter mới nhìn `X-API-Key`, thấy hợp lệ thì gán `ROLE_ADMIN` và cho qua mọi URL. Người có key không cần JWT, MFA hoặc tài khoản còn hoạt động. Đây là **authentication downgrade / bypass**.

Bài học thuộc mục **API key** của module Spring Security - authentication. Sau bài, bạn sẽ biết cách xác định API nào được phép dùng key, tách filter chain, giới hạn machine principal, ngăn credential fallback, kiểm JWT/MFA ở endpoint nhạy cảm, xây bộ test âm tính và quản lý vòng đời key.

**Nguyên tắc:** tài nguyên quyết định loại bằng chứng xác thực bắt buộc. Một credential bất kỳ đã được xác minh không tự thỏa các yêu cầu mạnh hơn của tài nguyên.

## 2. API key chứng minh được gì?

Một API key ngẫu nhiên đủ mạnh có thể định danh một **client application** hoặc đối tác đã đăng ký, ví dụ `partner-reports-reader`. Nó không tự chứng minh nhân viên nào đã đăng nhập, đã MFA, có quyền duyệt giao dịch, thuộc tenant nào hoặc có phiên người dùng còn hiệu lực.

| Credential | Đại diện thường gặp | Điểm cần kiểm |
| --- | --- | --- |
| API key | Machine/service/partner | Bí mật đúng, client còn hiệu lực, scope, tenant, hết hạn/thu hồi |
| OAuth2 access token | Người dùng hoặc service principal theo grant | Chữ ký/introspection, issuer, audience, thời hạn, scope |
| OIDC ID token | Người dùng được xác thực tại relying party | Dùng ở client để đăng nhập; không thay access token của API |
| Web session | Phiên user tại ứng dụng | Session, CSRF khi áp dụng, trạng thái user, thời gian xác thực |
| mTLS | Workload sở hữu private key | CA, client certificate, trust domain, key rotation |
| MFA/step-up | User đã thực hiện xác thực mạnh | Bằng chứng từ IdP/AS tin cậy, mức assurance và tính mới |

Không có bảng xếp hạng độ mạnh tuyệt đối cho mọi trường hợp: key đủ entropy + mTLS có thể hợp lệ cho service hẹp. Nhưng nếu một tác vụ **đòi người dùng hoàn tất MFA**, chỉ key không đủ bằng chứng về người dùng. Cần một workflow máy được ủy quyền riêng hoặc chính sách kết hợp credential có kiểm chứng, thay vì mạo danh người dùng.

## 3. Mô hình đe dọa: key thành đường vòng bằng cách nào?

Các đường bypass thường xuất hiện khi:

1. **Filter chạy quá rộng:** API key filter được đăng ký toàn cục và cấp authentication cho cả endpoint quản trị.
2. **Dùng lựa chọn OR không có policy:** `jwtValid || apiKeyValid`, trong khi tài nguyên yêu cầu JWT và MFA.
3. **Fallback từ lỗi mạnh sang yếu:** JWT sai issuer/hết hạn/không MFA thì thử API key; nếu key đúng, request vẫn thành công.
4. **Authority giống nhau:** key của job được gán `ROLE_ADMIN` hoặc `SCOPE_admin.write` tương đương user đã MFA.
5. **Confused principal:** code coi machine identity là nhân viên, dùng `getName()` làm user ID mà không phân loại token type.
6. **Matcher thiếu đường dẫn:** một số URL không rơi vào bất kỳ `SecurityFilterChain` nào nên không được Spring Security bảo vệ.
7. **Trust header giả:** client tự gửi `X-Authenticated-User`, `X-MFA: true`, `X-Role: ADMIN`, rồi backend tin đó là kết quả xác thực.
8. **Key bị sao chép/lộ:** key lâu dài nằm trong log, ứng dụng frontend hoặc repo, còn quyền quá rộng và không có revocation.

Không chỉ ngăn key sai. **Phải kiểm thử key đúng trên endpoint mạnh vẫn bị từ chối**.

## 4. Thiết kế hợp đồng xác thực theo tuyến

Định nghĩa ma trận bảo vệ trước khi viết filter:

| Tuyến | Principal dự kiến | Credential được chấp nhận | Policy |
| --- | --- | --- | --- |
| `GET /partner/status` | Service đối tác | Chỉ API key của đối tác | `PARTNER_READ` + quota |
| `GET /api/reports` | Chủ thể OAuth2 theo hợp đồng AS | Chỉ bearer access token | `SCOPE_reports.read` + kiểm tenant/ownership |
| `GET /api/high-assurance` | User đã step-up | Chỉ bearer JWT người dùng | `SCOPE_admin.write` và assurance MFA đáng tin |
| `/internal/**` | Hạ tầng nội bộ | Không public trong ví dụ | Deny ở ứng dụng và bảo vệ mạng |
| URL khác | Không định nghĩa | Không | Deny mặc định |

Tách `/partner/**` và `/api/**` thành hai namespace làm rõ chính sách. Đừng chọn cơ chế theo header do client kiểm soát. Anti-pattern:

```java
// KHÔNG triển khai: client tự quyết định sử dụng mức bảo vệ nào
if (request.getHeader("X-API-Key") != null) {
    return useApiKeyForAnyPath(request);
}
return useJwtAndMfa(request);
```

Đây là **pseudocode** minh họa lỗi; không phải phương thức Java độc lập. Đường dẫn tài nguyên được ứng dụng xác định trước, còn header chỉ là credential được xử lý **trong chain đã chọn**.

Nếu một endpoint thực sự cần vừa machine identity vừa user đã MFA, quy tắc phải là **A AND B**, có hai bước xác minh độc lập và policy dùng cả hai danh tính. Không đơn giản tạo hai provider và hy vọng `authenticated()` có nghĩa cả hai đã xác minh.

## 5. Spring Security: securityMatcher khác requestMatchers

Với nhiều bean `SecurityFilterChain`, Spring Security Servlet chọn **chain khớp đầu tiên** theo thứ tự `@Order`. `securityMatcher` chọn một chain; các `requestMatchers` bên trong `authorizeHttpRequests` là luật phân quyền **chỉ trong chain đó**.

Ví dụ chính:

```text
@Order(1): securityMatcher("/partner/**")
  API key filter + API key provider
  anyRequest().hasAuthority("PARTNER_READ")

@Order(2): securityMatcher("/api/**")
  oauth2ResourceServer().jwt()
  "/api/reports" → SCOPE_reports.read
  "/api/high-assurance" → SCOPE_admin.write AND verified MFA assurance
  other /api/** → denyAll

@Order(3): chain KHÔNG CÓ securityMatcher
  anyRequest().denyAll()
```

Các điểm cần nhớ:

- Chỉ thêm `anyRequest().denyAll()` vào chain `/api/**` **không** bảo vệ URL ngoài `/api/**`.
- Nếu không có catch-all chain, request không khớp chain nào có thể nằm ngoài toàn bộ Spring Security filters.
- Trong `authorizeHttpRequests`, rule đầu tiên khớp được dùng. Đặt pattern cụ thể trước `anyRequest()`.
- Không biến custom API key filter thành Servlet `Filter` chạy ngoài `FilterChainProxy`. Nếu đã đưa filter vào security chain, tránh auto-register lần hai của Spring Boot.
- Kiểm thử HTTP method, trailing slash, percent encoding, reverse proxy rewrite, context path và các servlet khác; matcher phải tương ứng request sau khi Servlet container xử lý.

Bài thực hành dùng Servlet/Spring MVC, Java 17+, Spring Boot 3.x và Spring Security 6.x. WebFlux có `ServerHttpSecurity`, `SecurityWebFilterChain` riêng; không copy cấu hình Servlet sang reactive.

## 6. Phát sinh và lưu API key an toàn

Một API key dành cho máy nên được sinh bằng CSPRNG, có entropy cao. 32 byte ngẫu nhiên (256 bit) được Base64URL không padding thành chuỗi 43 ký tự. Đừng dùng email, mật khẩu dễ đoán, ID tăng dần, timestamp hay một chuỗi được commit trong source.

**KeyGenerator.java** – chương trình Java 17 độc lập:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

public class KeyGenerator {
    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        String key = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(secret);
        byte[] sha = MessageDigest.getInstance("SHA-256")
                .digest(key.getBytes(StandardCharsets.UTF_8));

        System.out.println("Key: " + key);
        System.out.println("SHA256: " + HexFormat.of().formatHex(sha));
    }
}
```

Chạy:

```bash
javac KeyGenerator.java
java KeyGenerator
```

Dòng `Key` có phần giá trị ngẫu nhiên khác nhau mỗi lượt; SHA-256 hex dài 64 ký tự. Không có stdout cố định để chép lại. Chạy công cụ ở nơi tin cậy, chuyển secret cho client qua secret manager/kênh bảo vệ; không đưa cả hai dòng vào CI log, ticket hay repo.

Với key thật sự có entropy cao, lưu digest SHA-256 thay plaintext có thể hợp lý; đây **không** phải cách hash mật khẩu người dùng. User password cần password hashing chậm như Argon2/bcrypt với chính sách riêng. Trong hệ thống nhiều key, thêm key ID (public), scope, client, tenant, ngày hết hạn và trạng thái thu hồi; có thể dùng HMAC/pepper theo threat model.

**Không cấp authority người dùng cho key.** Hệ thống có thể đặt tên machine authority như `PARTNER_READ`, chỉ cho một nhóm API cụ thể. Mọi key phải có khả năng rotate/revoke và rate limit phù hợp.

## 7. Project mẫu: Spring Boot 3 + Resource Server JWT + API key riêng

Ví dụ có ba chain: `/partner/**` dùng key, `/api/**` dùng JWT và endpoint step-up, phần còn lại deny. Mã được chia thành các tệp Java 17 trong package `com.example.boundary`.

### 7.1. Gradle dependencies và cấu hình

Trong project Spring Boot có plugin/dependency management, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo `src/main/resources/application.yml`:

```yaml
security:
  partner:
    api-key-sha256: ${PARTNER_API_KEY_SHA256}
  jwt:
    issuer: ${JWT_ISSUER}
    jwk-set-uri: ${JWT_JWK_SET_URI}
    audience: ${JWT_AUDIENCE}
```

Đây là custom properties của ví dụ. Digest lấy từ quy trình cấp key; issuer/JWKS/audience lấy từ AS đáng tin. JWT trong ví dụ phải là **access token dành cho API**, không phải OIDC ID token. Không lấy JWKS URL từ token do client tự khai.

### 7.2. Request token chưa xác thực, result token đã xác thực

**ApiKeyAuthenticationToken.java**

```java
package com.example.boundary;

import java.util.Collection;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    public ApiKeyAuthenticationToken(String rawKey) {
        super(null);
        this.principal = null;
        this.credentials = rawKey;
        super.setAuthenticated(false);
    }

    private ApiKeyAuthenticationToken(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {
        super(authorities);
        this.principal = clientId;
        this.credentials = null;
        super.setAuthenticated(true);
    }

    static ApiKeyAuthenticationToken verified(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyAuthenticationToken(clientId, authorities);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                    "Only a trusted provider may authenticate");
        }
        super.setAuthenticated(false);
    }
}
```

Filter tạo token với một tham số và `isAuthenticated=false`. Provider trả token đã được đánh dấu authenticated **sau khi** kiểm credential. Không dùng một constructor public nhận tên khách hàng + quyền rồi tự đặt authenticated=true từ header chưa xác minh.

### 7.3. Provider kiểm secret và chỉ phát machine authority

**PartnerApiKeyProvider.java**

```java
package com.example.boundary;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class PartnerApiKeyProvider implements AuthenticationProvider {

    private final byte[] expectedDigest;

    public PartnerApiKeyProvider(String hex) {
        if (hex == null || !hex.matches("[0-9a-fA-F]{64}")) {
            throw new IllegalArgumentException("Invalid SHA-256 digest");
        }
        this.expectedDigest = HexFormat.of().parseHex(hex);
    }

    @Override
    public Authentication authenticate(Authentication request) {
        if (!(request instanceof ApiKeyAuthenticationToken token)) {
            return null;
        }

        Object value = token.getCredentials();
        if (!(value instanceof String raw)
                || !raw.matches("[A-Za-z0-9_-]{43,128}")) {
            throw new BadCredentialsException("Invalid key");
        }

        byte[] actual;
        try {
            actual = MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }

        if (!MessageDigest.isEqual(expectedDigest, actual)) {
            throw new BadCredentialsException("Invalid key");
        }

        return ApiKeyAuthenticationToken.verified(
                "partner-report-client",
                List.of(new SimpleGrantedAuthority("PARTNER_READ")));
    }

    @Override
    public boolean supports(Class<?> type) {
        return ApiKeyAuthenticationToken.class.isAssignableFrom(type);
    }
}
```

Ví dụ dùng một digest cấu hình để làm rõ cơ chế. Production nên tra key registry theo key ID, kiểm scope, tenant, trạng thái client, expiration/revocation, không chỉ hash. `MessageDigest.isEqual` so sánh hai digest cùng độ dài; yêu cầu sinh key có entropy cao để ngăn brute force offline. Không log raw key.

### 7.4. Filter giới hạn trong partner chain và cấm trộn credential

**PartnerApiKeyFilter.java**

```java
package com.example.boundary;

import java.io.IOException;
import java.util.Enumeration;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class PartnerApiKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager manager;

    public PartnerApiKeyFilter(AuthenticationManager manager) {
        this.manager = manager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if (request.getHeader("Authorization") != null) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST);
            return;
        }

        Enumeration<String> values = request.getHeaders("X-Partner-Key");
        if (!values.hasMoreElements()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        String key = values.nextElement();
        if (values.hasMoreElements() || key == null
                || key.isBlank() || key.indexOf(',') >= 0) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        ApiKeyAuthenticationToken input = new ApiKeyAuthenticationToken(key);
        Authentication result;
        try {
            result = manager.authenticate(input);
        } catch (AuthenticationException rejected) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        } finally {
            input.eraseCredentials();
        }

        if (result == null || !result.isAuthenticated()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

Filter này **không được tạo thành Servlet filter toàn cục**; phần SecurityConfig tạo tại chỗ trong partner chain. Khi key thiếu/sai, trả 401 ngay, không thử cơ chế yếu/khác. Trong namespace partner, request vừa có API key vừa có Authorization header bị từ chối 400 để không nhập nhằng. Kiểm duplicate header và dấu phẩy là hàng rào cơ bản; gateway vẫn phải chuẩn hóa, loại bỏ header giả và giới hạn size. Dùng TLS, không gửi key qua query string.

### 7.5. Cấu hình nhiều SecurityFilterChain

**SecurityConfig.java**

```java
package com.example.boundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PartnerApiKeyProvider provider(
            @Value("${security.partner.api-key-sha256}") String digest) {
        return new PartnerApiKeyProvider(digest);
    }

    @Bean
    @Order(1)
    SecurityFilterChain partner(
            HttpSecurity http, PartnerApiKeyProvider provider) throws Exception {
        AuthenticationManager manager = new ProviderManager(provider);
        PartnerApiKeyFilter filter = new PartnerApiKeyFilter(manager);

        return http
                .securityMatcher("/partner/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .securityContext(context -> context
                        .securityContextRepository(
                                new NullSecurityContextRepository()))
                .csrf(AbstractHttpConfigurer::disable)
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasAuthority("PARTNER_READ"))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
                .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain userJwt(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                        .requestMatchers("/api/high-assurance")
                        .access(highAssurance())
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    private static AuthorizationManager<RequestAuthorizationContext> highAssurance() {
        return (authentication, context) -> {
            Authentication candidate = authentication.get();
            boolean allowed =
                    candidate instanceof JwtAuthenticationToken jwt
                    && jwt.isAuthenticated()
                    && "urn:example:acr:mfa".equals(
                            jwt.getToken().getClaimAsString("acr"))
                    && jwt.getAuthorities().stream()
                            .anyMatch(a -> "SCOPE_admin.write".equals(
                                    a.getAuthority()));
            return new AuthorizationDecision(allowed);
        };
    }

    @Bean
    @Order(3)
    SecurityFilterChain catchAll(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()).build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${security.jwt.issuer}") String issuer,
            @Value("${security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> correctAudience = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token", "Wrong audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                standard, correctAudience));
        return decoder;
    }
}
```

**Giải thích điểm quyết định:**

1. `@Order(1)` chọn chain partner **chỉ** với `/partner/**`, dùng `PartnerApiKeyFilter` và authority `PARTNER_READ`. Tạo filter bên trong method tránh Spring Boot tự đăng ký một lần ở Servlet container ngoài chain.
2. `@Order(2)` chỉ khớp `/api/**`. Chain này bật resource server JWT, **không chứa API key filter**. Vì thế API key không thể trở thành `JwtAuthenticationToken` ở endpoint user.
3. `@Order(3)` là chain catch-all không có `securityMatcher` và `denyAll()`. Không để lộ endpoint ngoài các namespace đã định nghĩa.
4. `highAssurance()` yêu cầu `JwtAuthenticationToken`, đúng `SCOPE_admin.write` và `acr` có ý nghĩa MFA theo hợp đồng AS. Nếu authentication là machine-key token thì bị từ chối.
5. `NimbusJwtDecoder` xác minh chữ ký theo JWKS tin cậy; `JwtValidators.createDefaultWithIssuer` kiểm issuer và thời gian, `correctAudience` thêm kiểm tra audience của API. Token đúng chữ ký nhưng dành cho resource khác không được vào.
6. `csrf(...disable)` chỉ thích hợp trong **hai API stateless xác thực bằng header, không dùng cookie/session**. Website có session phải có chain và CSRF policy riêng; đừng sao chép tắt CSRF toàn ứng dụng.

**Lưu ý:** claim `acr=urn:example:acr:mfa` là giá trị **minh họa**, không phải một mã MFA được IdP nào cũng hỗ trợ. Để chứng minh MFA, AS cần thật sự xác thực mạnh rồi ký assurance vào **access token dành cho API**; RS kiểm token và claim theo hợp đồng. Nếu yêu cầu MFA mới trong 5 phút, cần chính sách `auth_time`/step-up bổ sung, ví dụ hiện tại chưa kiểm tính mới.

### 7.6. Main và controller minh họa

**BoundaryApplication.java**

```java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

**DemoController.java**

```java
package com.example.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/partner/status")
    public String partner() {
        return "partner: permitted";
    }

    @GetMapping("/api/reports")
    public String report() {
        return "report: permitted";
    }

    @GetMapping("/api/high-assurance")
    public String strong() {
        return "high assurance: permitted";
    }
}
```

Khi dependencies và cấu hình được đặt trong project Boot 3.x phù hợp, các lớp là các tệp Java riêng trong một package. Phần cấp token/JWKS thuộc AS ngoài ứng dụng; mã minh họa **không** tự phát access token. Trong production, các endpoint phải kiểm quyền đối tượng, tenant, trạng thái account, rate limit và chính sách gateway riêng.

## 8. Ma trận kiểm thử chống bypass

Chỉ kiểm key đúng trên endpoint partner là **chưa đủ**. Bộ kiểm thử quan trọng nhất là **key đúng + endpoint đòi JWT/MFA = bị từ chối**.

| Request | Credential | Kỳ vọng |
| --- | --- | --- |
| `GET /partner/status` | API key đúng | 200 |
| `GET /partner/status` | Thiếu API key | 401 |
| `GET /partner/status` | API key sai | 401 |
| `GET /partner/status` | JWT mà không có API key | 401 |
| `GET /partner/status` | API key + Bearer header | 400 trong ví dụ |
| `GET /api/reports` | Chỉ API key đúng | 401 |
| `GET /api/high-assurance` | Chỉ API key đúng | 401 |
| `GET /api/high-assurance` | JWT có admin scope nhưng không có MFA assurance | 403 |
| `GET /api/high-assurance` | JWT có MFA assurance nhưng thiếu scope | 403 |
| `GET /api/high-assurance` | JWT đúng scope + MFA assurance | 200 |
| `GET /api/reports` | JWT có reports.read | 200 |
| URL ngoài namespace | Bất kỳ | Không cho qua catch-all |

### 8.1. Spring Security Test với MockMvc

**src/test/java/com/example/boundary/AuthBoundaryTest.java**

```java
package com.example.boundary;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthBoundaryTest {

    private static final String TEST_KEY =
            "test_only_key_abcdefghijklmnopqrstuvwxyz0123456789ABCD";

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) {
        registry.add("security.partner.api-key-sha256",
                () -> sha256Hex(TEST_KEY));
        registry.add("security.jwt.issuer",
                () -> "https://idp.example.test/realm/training");
        registry.add("security.jwt.jwk-set-uri",
                () -> "https://idp.example.test/jwks");
        registry.add("security.jwt.audience",
                () -> "protected-api");
    }

    private static String sha256Hex(String raw) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(
                            raw.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    @Autowired
    MockMvc mvc;

    @Test
    void keyWorksOnlyForPartnerEndpoint() throws Exception {
        mvc.perform(get("/partner/status").header("X-Partner-Key", TEST_KEY))
                .andExpect(status().isOk())
                .andExpect(content().string("partner: permitted"));

        mvc.perform(get("/api/reports").header("X-Partner-Key", TEST_KEY))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/high-assurance")
                        .header("X-Partner-Key", TEST_KEY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidAndMixedPartnerCredentialsFail() throws Exception {
        mvc.perform(get("/partner/status"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/partner/status")
                        .header("X-Partner-Key", "wrong"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/partner/status")
                        .header("X-Partner-Key", TEST_KEY)
                        .header(HttpHeaders.AUTHORIZATION, "Bearer anything"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mfaAndScopeAreBothRequired() throws Exception {
        mvc.perform(get("/api/high-assurance").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_admin.write"))))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/high-assurance").with(jwt()
                        .jwt(token -> token.claim(
                                "acr", "urn:example:acr:mfa"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_other"))))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/high-assurance").with(jwt()
                        .jwt(token -> token.claim(
                                "acr", "urn:example:acr:mfa"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_admin.write"))))
                .andExpect(status().isOk())
                .andExpect(content().string("high assurance: permitted"));
    }

    @Test
    void jwtCanReadReportsWithScope() throws Exception {
        mvc.perform(get("/api/reports").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_reports.read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("report: permitted"));
    }
}
```

Chạy bằng Gradle wrapper:

```bash
./gradlew test
```

Windows PowerShell: `.\gradlew.bat test`. Đây là **kết quả test kỳ vọng theo mã minh họa**, chưa phải test đã chạy trong hệ thống thật. Test key dùng chuỗi rõ ràng chỉ dành cho test; production phải dùng CSPRNG key và không commit secret.

### 8.2. Vì sao chưa đủ để chứng minh JWT/MFA thật?

Helper `jwt()` của Spring Security Test tạo `Authentication` giả lập cho MockMvc, không thực hiện kiểm chữ ký, JWKS, issuer, audience hoặc expiry. Vì vậy nó chỉ test **authorization và tách chain**, không chứng minh một AS đã thực hiện MFA thật.

Cần thêm integration test gửi HTTP Bearer JWT ký bằng private key thử nghiệm tới API, dùng JWKS endpoint thử nghiệm và kiểm:

- Signature không hợp lệ, `alg` bị cấm, `kid` không tồn tại.
- Issuer sai, audience khác, hết hạn, chưa đến `nbf`.
- Token đúng nhưng không có assurance MFA (hoặc quá cũ nếu policy yêu cầu tính mới).
- Token client credentials thay cho user khi yêu cầu người dùng.
- JWT sai + API key đúng trên endpoint JWT: **không chuyển sang API key**.
- Key bị thu hồi/hết hạn và client/key thuộc tenant khác.
- URL sau gateway rewrite, servlet context path, trailing slash, path encoding, HTTP method khác.

Không dùng khóa ký production trong test. Bộ test phải chứng minh controller nhạy cảm **không được thực thi** trong các tình huống bị từ chối, thay vì chỉ khớp một mã HTTP.

## 9. Kiểm soát MFA, step-up và human-in-the-loop

Một API key chứng minh sở hữu một bí mật của **service**; MFA chứng minh user đã hoàn thành quy trình xác thực mạnh theo chính sách của IdP. Không tự gán cho key `ROLE_USER` hoặc thêm header `X-MFA:true` để giả vờ có người dùng đã xác thực.

Nếu nghiệp vụ cần phê duyệt của con người:

1. Yêu cầu user thực hiện step-up qua IdP hoặc nền tảng xác thực nội bộ.
2. AS phát access token dành cho API có bằng chứng assurance đáng tin và thời hạn phù hợp.
3. RS kiểm chữ ký, issuer, audience, scope, claim assurance và thời gian xác thực khi chính sách cần.
4. Service kiểm quyền trên đối tượng và nguyên tắc phân tách nhiệm vụ; log audit có dấu vết user thật.
5. Job hoặc đối tác vẫn dùng key riêng cho tác vụ máy được phép, không tự thay người duyệt.

Nếu AS không phát assurance claim vào access token, RS **không thể suy ra MFA** chỉ từ việc người dùng đã đăng nhập. Cần thiết kế bước xác thực lại/token exchange hoặc một bằng chứng khác do hệ thống tin cậy cung cấp.

Đối với hành động nguy cơ cao, còn cần chống replay, hạn mức và kiểm business transaction, vì JWT có MFA vẫn có thể bị đánh cắp hoặc có scope quá rộng. Xác thực mạnh là một lớp, không thay thế phân quyền dữ liệu.

## 10. Vòng đời API key và quyền ở production

Một bản ghi key có thể chứa:

```sql
CREATE TABLE api_client_key (
    key_id VARCHAR(80) PRIMARY KEY,
    client_id VARCHAR(120) NOT NULL,
    sha256_hex CHAR(64) NOT NULL,
    scope VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(80),
    expires_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE
);
```

Schema chỉ minh họa cách lưu metadata, chưa phải thiết kế DB hoàn chỉnh. Thực tế nên có key ID công khai và secret riêng, trạng thái client, rotation, audit, giới hạn số key, transaction/locking và policy cache. Không trả giá trị hash/token đầy đủ trong thông báo lỗi.

**Quy trình cấp/đổi/thu hồi:**

- Sinh key từ CSPRNG, cấp cho đúng client và môi trường. Quyền mặc định thấp nhất.
- Truy vấn key ID và so digest/hmac theo cách giảm timing leak; kiểm scope, tenant, `expiresAt`, `revokedAt`.
- Có thể chạy song song key mới/cũ trong khoảng thời gian chuyển tiếp được kiểm soát, sau đó revoke key cũ.
- Khi key lộ, thu hồi nhanh, điều tra bằng key ID, không ghi key vào ticket/log. Nếu cache key, phải đặt TTL phù hợp để thu hồi có hiệu lực.
- Rate limit, anomaly detection, alert số lần dùng key sai, quota theo client/tenant; không dùng IP allowlist như phương thức xác thực duy nhất.

Key của partner chỉ có quyền dữ liệu của partner. Chặn object-level authorization bypass bằng cách kiểm tenant/owner ở service hoặc database. Một authority `PARTNER_READ` không nên cho phép xem mọi report trên toàn hệ thống.

## 11. Khi kết hợp OAuth2 JWT, session, Basic hoặc gateway

- `oauth2ResourceServer().jwt()` xác thực **bearer access token** cho API. `oauth2Login()` phục vụ đăng nhập web; `oauth2Client()` phục vụ client dùng token gọi API ngoài. Không nhầm vai trò.
- Một ứng dụng có UI dùng cookie session cần CSRF, session fixation/logout và security chain riêng. Không tắt CSRF toàn cục vì partner API dùng key.
- Một route đã đòi JWT/MFA không được tiếp nhận API key do một filter được thêm vào chain sai vị trí hoặc do entry point fallback.
- Với gateway, phải đảm bảo đường dẫn thực, forwarding headers và security matcher phù hợp; backend không tin `X-User`, `X-Role`, `X-MFA` do client tự đặt.
- mTLS bổ sung ràng buộc máy đáng tin cho service; nếu gateway thực hiện xác thực thay backend, phải có hợp đồng trust, network isolation và chống header spoofing.
- `CORS` chỉ điều chỉnh trình duyệt, không ngăn lệnh curl hoặc client khác dùng key.
- Không để API key trong frontend JavaScript hoặc app mobile công khai rồi xem đó là bí mật máy chủ.

## 12. Xử lý lỗi theo nguyên tắc fail closed

| Trường hợp | Hành vi nên có |
| --- | --- |
| Không có key trên partner route | 401, không fallback |
| Key sai/hết hạn/thu hồi | 401, không cấp principal |
| Key đúng trên JWT route | Vẫn yêu cầu Bearer JWT hợp lệ |
| JWT sai issuer/audience/signature/time | Từ chối, không thử key |
| JWT hợp lệ nhưng thiếu scope/MFA | Thường 403 |
| Key store/JWKS/AS không phản hồi | Không cho qua khi chưa xác minh; quan sát lỗi hạ tầng riêng |
| Request có hai loại credential mâu thuẫn | Từ chối hoặc theo policy rõ ràng, không tự chọn cách dễ nhất |
| URL không nằm trong route dự kiến | Catch-all deny |

Đặc biệt tránh kiểu:

```java
// KHÔNG triển khai: mọi lỗi của bước mạnh đều chuyển sang key
try {
    return verifyJwtAndMfa(request);
} catch (Exception failure) {
    return verifyApiKey(request);
}
```

Đây là pseudocode để chỉ ra anti-pattern. Đừng nuốt `AuthenticationException`, lỗi JWK/introspection hoặc lỗi DB thành `permitAll()`. Tùy cấu hình, 401 thường là thiếu/sai credential, 403 là xác thực đã có nhưng thiếu quyền; không dựa vào status code duy nhất để kết luận không có bypass, hãy kiểm chính sách và tác vụ nhạy cảm có thực sự bị chặn.

## 13. Checklist review pull request

Khi review thay đổi thêm API key, hãy kiểm:

- [ ] Có ma trận endpoint và credential được phép hay chưa? Route nhạy cảm đòi MFA có còn chỉ chấp nhận phương thức mạnh không?
- [ ] `securityMatcher` của key chain có bị mở rộng quá mức? Có catch-all `denyAll()` không?
- [ ] Custom key filter có chạy hai lần hoặc chạy ngoài Spring Security không?
- [ ] Key provider có phân biệt request token chưa xác thực với result token đã xác thực không?
- [ ] Principal từ key là machine/service, authority có hẹp và khác user role không?
- [ ] JWT decoder có kiểm signature, issuer, audience và thời hạn; policy MFA có nguồn đáng tin không?
- [ ] Request có key + JWT, key sai, JWT hết hạn, JWT thiếu MFA đều fail closed theo từng route không?
- [ ] Mỗi key có key ID, owner, scope, tenant, expiry, revocation, rotation, rate limit và audit an toàn chưa?
- [ ] Không log full key, bearer token, secret, hashes có thể gây lộ thông tin không?
- [ ] Đã test đường dẫn sau proxy, method, trailing slash, encoded path và object-level authorization chưa?
- [ ] Đã test bằng JWT thật qua decoder, ngoài test MockMvc `jwt()` giả lập chưa?

Mục tiêu của checklist là kiểm **toàn bộ đường đi từ request đến dữ liệu**, bao gồm hạ tầng, filter selection, principal type, claims và domain authorization.

## 14. Bài tập và lỗi phổ biến

**Bài tập 1:** Thêm `POST /api/approve` yêu cầu `SCOPE_approval.write` và user assurance MFA. Viết test mà API key đúng vẫn bị 401 và JWT thiếu MFA bị 403. Không cấp `ROLE_ADMIN` cho key.

**Bài tập 2:** Tạo key registry cho hai đối tác có tenant khác nhau. Test key A không thể xem dữ liệu B, dù cả hai cùng có `PARTNER_READ`.

**Bài tập 3:** Bỏ catch-all chain trong môi trường kiểm thử. Gọi một URL ngoài `/api/**` và `/partner/**`; giải thích nguy cơ và khôi phục deny-all.

**Bài tập 4:** Viết integration test JWT ký bằng khóa test với issuer, audience, exp và acr. Thêm trường hợp JWT đúng chữ ký nhưng sai audience, chỉ dùng key đúng và key + JWT đồng thời.

**Bài tập 5:** Thiết kế workflow cần cả service mTLS identity và user step-up. Nêu rõ hai bằng chứng, chính sách AND, thời gian xác minh và cách chống credential confusion.

Các lỗi phổ biến cần nhận diện: filter key toàn cục; `jwtValid || keyValid`; gán role quản trị cho key; không kiểm audience; tin header `X-MFA`; không phân biệt service/user principal; không có revocation; và chỉ viết test happy path.

## 15. Kết luận

**API key phù hợp cho machine-to-machine khi có phạm vi được giới hạn rõ, nhưng không phải lối đăng nhập thay thế cho tài nguyên đòi JWT/OIDC/MFA.** Trong Spring Security, tách route bằng `securityMatcher`, dùng `AuthenticationProvider` kiểm key trước khi cấp quyền, giới hạn authority theo client và có catch-all deny-all. Endpoint nhạy cảm phải kiểm đúng token type, issuer/audience, scope và assurance được nhà phát hành tin cậy xác nhận. Bảo vệ thêm bằng rotation, rate limit, tenant/object authorization, gateway rules và negative tests chứng minh key đúng vẫn **không** vượt qua yêu cầu mạnh hơn.

**Tài liệu tham khảo chính thức:**

- [Spring Security 6.5 – Java Configuration (nhiều SecurityFilterChain)](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [OWASP API Security Top 10 (Broken Authentication và Object-level Authorization)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)