# Ứng dụng web dùng phiên, API dùng token và mô hình kết hợp

> **Phạm vi:** Spring Security trên **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x / Spring Security 6.x. Thuộc nhóm **Thiết kế ứng dụng**. Mục tiêu là hiểu đúng và chọn đúng giữa **web session + cookie**, **API Bearer access token** và **hybrid architecture** (nhiều SecurityFilterChain hoặc Backend for Frontend), gồm vòng đời xác thực, CSRF, CORS, JWT, quyền và kiểm thử.

## 1. Vấn đề thiết kế

Giả sử một sản phẩm có:

- **Giao diện nhân viên** mở trong browser, truy cập `/web/**`, cần form login hoặc OIDC redirect và giữ đăng nhập qua nhiều request.
- **API cho mobile/đối tác**, truy cập `/api/**`, mỗi request gửi `Authorization: Bearer ...`.
- **Một ứng dụng kết hợp** chứa cả giao diện web và API hoặc một **BFF** trung gian giữa browser với resource server.

Mặc dù cả ba đều cần authentication và authorization, **không nên dùng cùng một cơ chế truyền credential cho mọi đường dẫn**. Ví dụ:

- Nếu API token-only bị cấu hình `formLogin`, request chưa xác thực có thể nhận **302 HTML login** thay vì **401 Bearer challenge**.
- Nếu đặt `SessionCreationPolicy.STATELESS` cho cả web form login, app có thể không giữ được phiên đăng nhập giữa hai request.
- Nếu tắt CSRF trên toàn bộ hệ thống vì “API dùng token”, những thao tác web được browser tự gửi cookie có thể thiếu bảo vệ.
- Nếu API chấp nhận session cookie ngầm định dù được thiết kế token-only, một browser session có thể vượt ranh giới xác thực mà đội phát triển không dự tính.
- Nếu Bearer access token ở API tự được chấp nhận bởi web chain, có thể tạo đường vào không mong đợi hoặc làm khó phân biệt logout/session security.
- Nếu `securityMatcher` và đường `/login`, `/logout`, callback OAuth2 bị đặt sai, login/redirect có thể không chạy hoặc rơi vào vòng lặp.

### Mục tiêu sau bài

1. Vẽ được đường đi của credential và `SecurityContext` trong session web và Bearer API.
2. Chọn stateful, stateless hoặc BFF theo loại client và threat model; giải thích trade-off về scale, logout, XSS/CSRF và token storage.
3. Tạo **nhiều `SecurityFilterChain`** với `securityMatcher`, thứ tự `@Order`, entry point, session policy và CSRF policy riêng.
4. Bảo vệ JWT bằng chữ ký, algorithm, issuer, audience, expiry và scopes; không dùng ID token để gọi resource server.
5. Viết test chứng minh: web session **không** tự cấp quyền vào API Bearer; Bearer token **không** tự trở thành web session.
6. Biết khi nào nên có live HTTP/browser test ngoài MockMvc.

## 2. Các thuật ngữ cốt lõi

### 2.1. Cookie phiên không giống access token

Với ứng dụng web truyền thống:

```text
Browser                            Spring Security + Servlet container
   |                               |
   | POST /login + form + CSRF      |
   |------------------------------>|
   |  authentication thành công    |
   |  lưu SecurityContext / session|
   |<---- 302 + Set-Cookie --------|
   |                               |
   | GET /web/home                 |
   | Cookie: JSESSIONID=...        |
   |------------------------------>|
   |  đọc session -> Authentication|
   |<---- 200 (data/HTML) ---------|
```

Session identifier thường nằm trong cookie `JSESSIONID`. Cookie không nhất thiết chứa tên/quyền của user; server dùng session ID để truy cập trạng thái phiên. `SecurityContextHolder` giữ authentication của request, thường qua thread-local; `SecurityContextRepository` quyết định cách khôi phục/lưu context giữa các request.

**Chú ý:** Spring Security 6 dùng cơ chế lưu `SecurityContext` tường minh trong những tình huống tự xây authentication. Một custom controller chỉ gọi `SecurityContextHolder.getContext().setAuthentication(...)` chưa đủ bảo đảm phiên request sau đã login; cần dùng authentication flow và repository thích hợp. Dùng `formLogin` hoặc `oauth2Login` chuẩn giúp tránh tự viết lại các bước quản lý phiên.

### 2.2. Bearer token khác session identifier

API nhận:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
Accept: application/json
```

Resource server kiểm tra access token rồi tạo `Authentication` cho request đó. Với JWT, việc kiểm tra bao gồm các yếu tố thích hợp như chữ ký/thuật toán được tin cậy, issuer `iss`, audience `aud`, thời điểm `exp`/`nbf`, scopes và business policy.

- **JWT:** thường tự chứa các claims; **payload mặc định không được mã hóa**, dù đã ký. Không đặt secret/PII không cần thiết trong claim.
- **Opaque token:** resource server thường kiểm tra bằng token introspection; trade-off gồm network, cache và khả năng thu hồi.
- **Access token:** credential dành cho resource server; không tự đồng nghĩa **ID token** của OIDC. Một ID token có thể hợp lệ với client nhưng không có audience của API.
- **Refresh token:** dùng với authorization server/client đúng vai trò; không nên gửi refresh token cho resource server như access token.
- **Scopes:** claim/token authority cho biết chức năng như `reports.read`; không thay thế quyền theo từng tenant/owner/record.

`SessionCreationPolicy.STATELESS` hướng API tới cách không tạo/dùng `HttpSession` làm nơi giữ security context. Nó không có nghĩa hệ thống hoàn toàn không có state ở database, cache, quota, revocation hoặc key rotation.

### 2.3. Authentication không thay authorization

Một API Bearer token có chữ ký đúng nhưng thiếu `SCOPE_reports.read` phải bị từ chối. Một web session đã login vẫn có thể thiếu `ROLE_ADMIN`. Ngay cả khi có scope READ, user chưa chắc được đọc tài liệu của tenant khác; phải kiểm tra object-level authorization tại service/query.

```text
Authentication: người gọi là ai?
  Web: SecurityContext nạp từ session.
  API: JWT/opaque token đã được xác minh.

Authorization: người gọi được làm gì?
  Request: hasAuthority, hasRole, URL/method.
  Service: tenant, owner, dữ liệu, trạng thái, nghiệp vụ.
```

## 3. Bảng so sánh quyết định

| Tiêu chí | Web session/cookie | Bearer API | Hybrid |
| --- | --- | --- | --- |
| Client thường gặp | Server-rendered browser, admin portal | Mobile, machine-to-machine, API consumer | Web + mobile/partner; SPA + BFF |
| Credential trên request | Cookie chứa session ID, browser tự gửi theo policy | `Authorization: Bearer` do client gắn | Theo từng ranh giới, không trộn ngầm |
| Authentication state | Thường lưu server-side | Thường xác thực token mỗi request | Web stateful, API stateless |
| Chưa đăng nhập | Thường 302 đến login | Thường 401 + `WWW-Authenticate: Bearer` | Phản hồi theo loại client/chain |
| CSRF | Thường cần cho thao tác dùng cookie | Có thể không cần nếu chỉ dùng header Bearer và không auto-send credential | Bật cho web/BFF cookie; phân tích riêng API |
| XSS | Có thể gửi request trong session; HttpOnly hạn chế đọc cookie | Token ở JS-accessible storage có thể bị đọc khi XSS | BFF giảm việc đưa token cho JS nhưng không loại bỏ XSS |
| Logout | Hủy session và context | JWT có thể còn hiệu lực tới expiry nếu không có revocation | Logout web, token, SSO là các việc khác nhau |
| Scaling | Shared session store/sticky routing khi nhiều instance | JWT validation offline có thể giảm lookup | Vận hành nhiều policy hoặc nhiều service |
| Điểm cần bảo vệ | Cookie flags, session fixation, timeout, CSRF | Signature, issuer, audience, scope, expiry, token storage | Matcher, trust boundary, CSRF/CORS, forwarding |
| Test quan trọng | Session persistence, cookie, CSRF | Bearer validation và scope | **Cross-credential isolation** |

Không có kiến trúc duy nhất đúng. Chọn theo browser tự gửi credential hay không, mức độ tin cậy client, luồng đăng nhập, phạm vi APIs, nhu cầu logout tức thời và vận hành.

## 4. Thiết kế A — web session

### 4.1. Luồng đăng nhập

Một website Spring MVC dùng `formLogin` hoặc `oauth2Login` sẽ đưa người chưa xác thực tới login hoặc identity provider. Sau xác thực, Spring Security thực hiện xử lý session phù hợp: bảo vệ session fixation, quản lý `SecurityContext` và chuyển hướng theo handler.

```text
GET /web/home (anonymous)
   -> 302 /login
GET /login
   -> 200 login form + CSRF field
POST /login (credentials + CSRF)
   -> authentication filter -> success handler
   -> session được tạo/đổi ID theo policy
   -> 302 /web/home
GET /web/home + Cookie
   -> server nạp Authentication từ session
   -> 200
```

Đây là sơ đồ điển hình, không phải mọi ứng dụng đều dùng đúng đường `/login` hoặc 302. Với OIDC, request sẽ đi qua authorization server và callback; bảo vệ `state`/`nonce`, redirect URI và cookie khi cross-site redirect cũng quan trọng.

### 4.2. Cấu hình cookie

- `Secure`: chỉ gửi cookie qua HTTPS; cần đúng proxy/TLS termination.
- `HttpOnly`: JavaScript không thể trực tiếp đọc cookie; **không ngăn XSS gửi hành động** bằng cookie tự kèm.
- `SameSite`: ảnh hưởng CSRF và SSO redirect; `Lax`, `Strict`, `None` cần theo hành vi browser thực tế, `None` thường đòi `Secure`.
- `Path`/`Domain`: giới hạn phạm vi; nếu cấu hình sai, cookie không đi cùng request sau login gây vòng lặp.
- Timeout, session concurrency, invalid-session handling và session store phải phù hợp chính sách.
- Không log raw session ID hoặc tự gán session ID vào query string.

Khi scale nhiều instance, cần session affinity hoặc kho session chia sẻ (ví dụ Spring Session + Redis) nếu yêu cầu truy cập phiên ở mọi node. Xem xét dữ liệu phiên khi deploy phiên bản mới, idle/absolute timeout, quyền thu hồi phiên khi account bị vô hiệu hóa.

### 4.3. CSRF cho web là ranh giới quan trọng

Browser thường **tự gắn** session cookie vào request hợp lệ theo cookie policy. Trang web độc hại có thể khiến trình duyệt gửi POST; nếu backend chỉ dựa vào cookie, request có thể bị hiểu là hành động của user. Vì thế các thao tác thay đổi trạng thái qua cookie thường cần CSRF protection.

Với form, `CsrfToken` được đưa vào hidden input/header phù hợp. Với SPA dùng session, token có thể gửi trong custom header. Spring Security 6 có deferred CSRF token và BREACH protection, và token cũ thường bị xóa sau login/logout. Client có thể cần **lấy token mới sau hai sự kiện**.

Không tắt CSRF toàn hệ thống chỉ vì ở một namespace khác có Bearer API.

## 5. Thiết kế B — OAuth2 Resource Server cho API

Một resource server lý tưởng không tự cấp token từ endpoint username/password nghiệp vụ. Nó tin một authorization server/IdP phát hành access token, còn resource server chỉ **xác thực token và ra quyết định truy cập**.

```text
OAuth2/OIDC authorization server
      |
      | access token có issuer, audience, scope, exp
      v
Mobile / partner / permitted SPA client
      |
      | Authorization: Bearer ...
      v
Spring Security Resource Server
      |
      +-- BearerTokenAuthenticationFilter
      +-- JwtDecoder hoặc opaque introspection
      +-- authorities / method authorization
      v
Controller -> service -> tenant-scoped repository
```

### 5.1. Cấu hình production thường dùng

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/product
          audiences:
            - https://api.example.org
```

Đây là **mẫu**: thay issuer/audience bằng giá trị do IdP cung cấp. Với issuer-uri, Resource Server có thể đọc metadata/JWKS do issuer công bố để chọn key công khai và xác minh JWT. Hãy kiểm tra cấu hình trust, key rotation, network availability, algorithm và bảo vệ endpoint JWKS trong sản phẩm thật.

**Issuer và audience khác nhau:** token hợp lệ do issuer A phát hành có thể được dành cho resource server B; nếu API của bạn không kiểm tra audience, nó có thể chấp nhận nhầm token hợp lệ của một API khác. Sau validation, cần kiểm tra `scope`, tenant/owner và các rule riêng.

### 5.2. JWT không phải thuốc thay mọi session

- Token bị đánh cắp có thể được dùng cho tới khi hết hạn trừ khi có cơ chế từ chối/thu hồi.
- Claims có thể đã cũ nếu người dùng mất quyền sau khi token phát hành.
- Token signing key rotation và thời gian đồng hồ (clock skew) cần xử lý.
- JWT signature không bảo mật payload như encryption; đừng đặt password, secret, dữ liệu riêng tư không cần thiết trong claims.
- `SCOPE_reports.read` không tự cấp `SCOPE_reports.write` hoặc quyền truy cập bản ghi ngoài tenant.
- Đừng để access token trong URL, HTML logs, analytics, localStorage tùy tiện; cần threat model về XSS và nơi lưu credential.

### 5.3. Khi nào API có thể không dùng CSRF?

Nếu **API chỉ chấp nhận Bearer token trong Authorization header**, không xác thực bằng cookie hoặc một credential trình duyệt tự gửi khác, và client chủ động gắn token, nguy cơ CSRF kiểu cookie session có thể không áp dụng. Khi đó có thể tắt CSRF **trong đúng API SecurityFilterChain**.

Nếu sau này API cho phép session cookie, cookie-based bearer, HTTP Basic browser credentials hoặc tự nhận refresh token qua cookie, giả định ban đầu có thể không còn đúng. **Stateless không tự chứng minh CSRF vô hại**; câu hỏi là browser có tự gửi credential trong yêu cầu cross-site hay không.

## 6. Thiết kế C — mô hình kết hợp

### C1. Một Spring Boot app, hai SecurityFilterChain

```text
                       +--> /web/** + /login + /logout
Browser + cookie ------|      SecurityFilterChain WEB
                       |      formLogin, session IF_REQUIRED, CSRF ON
                       |
Spring Boot Servlet ---+
                       |
Mobile/partner --------|----> /api/**
Bearer token           |      SecurityFilterChain API
                       |      oauth2ResourceServer(jwt), STATELESS
                       |      CSRF OFF chỉ khi Bearer-header only
                       |
                       +--> fallback denyAll()
```

Một `FilterChainProxy` chứa nhiều `SecurityFilterChain`. Request đi qua **chain đầu tiên có `securityMatcher` khớp**. Thứ tự bean `@Order` và phạm vi matcher là phần của security design.

| Endpoint | Chain | Khi không xác thực | CSRF |
| --- | --- | --- | --- |
| `GET /web/home` | Web | 302 tới `/login` | Filter hiện diện; GET thường không cần token |
| `GET /login` | Web | 200 form | Cấp token cho POST |
| `POST /login` | Web | Xử lý form login | **Có** |
| `POST /logout` | Web | Cleanup và redirect | **Có** |
| `GET /api/reports` | API | 401 Bearer challenge | Không áp dụng với GET |
| `POST /api/reports` | API | 401 nếu thiếu JWT, 403 nếu thiếu scope | Tắt có điều kiện ở token-only API |
| Đường ngoài phạm vi | Fallback | Deny | Theo fallback |

**Quan trọng:** `securityMatcher(...)` quyết định **filter chain áp dụng**, còn `requestMatchers(...)` trong `authorizeHttpRequests` quyết định **rule bên trong chain**. Nếu chỉ cấu hình web chain matcher `/web/**` nhưng login filter xử lý `POST /login` thì login POST có thể **không đến filter**.

### C2. Backend for Frontend (BFF)

```text
Browser (chỉ cookie HttpOnly)
       |
       | session + CSRF
       v
BFF (stateful; token được giữ phía server)
       |
       | Authorization: Bearer access token
       v
OAuth2 Resource Server -> business API -> DB
```

BFF hữu ích khi muốn browser không giữ access token trong JavaScript, tập trung refresh, token relay và session policy. BFF **vẫn phải** bảo vệ CSRF và XSS, đồng thời quản lý token store an toàn. Resource server vẫn phải kiểm tra JWT và quyền độc lập; không tin toàn bộ request chỉ vì đến từ BFF.

BFF có thêm chi phí vận hành (session store, scaling, availability, auth callback, logout và token lifecycle). Với website MVC truyền thống nhỏ, một web session có thể đơn giản hơn; với SPA phức tạp, BFF đáng cân nhắc.

### C3. Tách deployable

Có thể tách web/BFF và API resource server thành hai ứng dụng hoặc dùng chung một app với hai chains. Tách service tạo ranh giới triển khai rõ, nhưng **không tự bảo đảm** token audience/scopes đúng, quyền data-level đúng hoặc cookie không bị lộ.

## 7. Các nguyên tắc không nên phá vỡ

1. **Mỗi route có một policy credential rõ ràng.** Đừng cho API token-only tự chấp nhận web session.
2. **Mỗi chain có matcher và order rõ.** Chain tổng quát `/**` đứng đầu có thể chiếm request của chain cụ thể.
3. **Web session và API Bearer có entry point khác:** 302 login vs 401 Bearer; thiếu quyền thường 403.
4. **CSRF bật cho vùng cookie-authenticated,** chỉ miễn cho vùng phù hợp threat model.
5. **CORS không thay CSRF hoặc authorization.** Browser preflight không có session, và CORS phải được xử lý trước security khi có cross-origin.
6. **JWT phải được xác minh**, không chỉ parse claims; kiểm tra issuer/audience/time/algorithm/scopes.
7. **ID token không phải access token** cho resource server.
8. **Không dùng shared HS256 key demo trong production** nếu chưa có cơ chế quản lý ký/phát token được duyệt; ưu tiên IdP/JWKS/asymmetric signing khi phù hợp.
9. **Không hard-code password hoặc token thật.** Không log raw `Authorization` hoặc `JSESSIONID`.
10. **Dữ liệu cần authorization riêng:** tenant, owner, record, action; scope/role chỉ là một phần quyết định.
11. **Logout web không thu hồi mọi JWT**; phải có chính sách TTL, revocation và refresh token.
12. **Test ranh giới credential hai chiều** và live HTTP khi cần xác minh browser/proxy/cookie.

## 8. Demo Java 17: web session + API JWT trong một ứng dụng

Để demo **chạy test tự chứa mà không phụ thuộc IdP bên ngoài**, phần API sử dụng JWT HS256 ký bằng secret từ biến môi trường; test có test key cố định. Đây **chỉ là local/lab**, không hướng dẫn phát hành access token tự do trong hệ thống thật. Với production hãy dùng issuer-uri/JWKS/AS chuẩn và bỏ decoder bí mật chia sẻ nếu kiến trúc không cho phép.

### 8.1. Cấu trúc tệp

```text
hybrid-security-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/hybrid/
    HybridApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/com/example/hybrid/
    HybridSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'hybrid-security-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Plugin versions cố định giúp học đúng một API của Boot 3.3/Security 6; **không phải khuyến nghị phiên bản production mới nhất**. Sử dụng bản vá được tổ chức duy trì. Đoạn mã cần JDK 17+ và Gradle/wrapper tương thích.

### 8.2. `HybridApplication.java`

```java
package com.example.hybrid;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HybridApplication {

    public static void main(String[] args) {
        SpringApplication.run(HybridApplication.class, args);
    }
}
```

### 8.3. `SecurityConfig.java` — ba chain và decoder

```java
package com.example.hybrid;

import java.util.Base64;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    public static final String DEMO_ISSUER =
        "https://issuer.example.test";
    public static final String DEMO_AUDIENCE = "hybrid-api";

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("SCOPE_reports.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache.disable())
            // Chỉ cho Bearer token nằm trong Authorization header;
            // không nhận session cookie làm credential của API.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/web/**", "/login", "/logout", "/")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/web/home", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("web-user")
            .password(encoder.encode("web-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${DEMO_JWT_SECRET_BASE64}") String base64Secret) {

        byte[] bytes = Base64.getDecoder().decode(base64Secret);
        if (bytes.length < 32) {
            throw new IllegalArgumentException(
                "Demo HS256 key must contain at least 32 bytes"
            );
        }

        SecretKey key = new SecretKeySpec(bytes, "HmacSHA256");
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withSecretKey(key)
            .macAlgorithm(MacAlgorithm.HS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
            jwt.getAudience().contains(DEMO_AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token", "Invalid audience", null
                ));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(DEMO_ISSUER),
            audienceCheck
        ));

        return decoder;
    }
}
```

**Từng quyết định có chủ đích:**

- `apiChain` đứng đầu, chỉ nhận `/api/**`. Không dùng form login hoặc Basic ở API; Bearer token được `oauth2ResourceServer` xử lý.
- `apiChain` áp `STATELESS`. Web session cookie không tự làm API authenticated, ngay cả khi cả hai cùng một domain.
- `apiChain` tắt CSRF **chỉ vì giả định token-only header**, không phải vì cứ là API thì an toàn.
- `webChain` nhận `/web/**` **và** `/login`/`/logout`. Form/login/logout filters thực sự thấy đường cần xử lý.
- `webChain` dùng `IF_REQUIRED` và giữ CSRF; authentication được lưu bằng session theo cơ chế của Spring Security.
- `fallbackChain` chặn các path khác; không dùng `anyRequest().permitAll()` làm fallback. `ERROR` dispatch được cho phép cho error processing; cần đánh giá riêng chính sách lỗi production.
- JWT decoder kiểm tra HS256 secret, `iss`, `aud` và thời gian hiệu lực. Secret đọc từ môi trường; demo **không tự mint token từ API endpoint**.
- `SCOPE_reports.read` và `SCOPE_reports.write` tách hai capability. Spring Resource Server chuyển `scope=reports.read` thành authority `SCOPE_reports.read` theo quy ước mặc định.
- JWT HS256 chung một key giữa issuer/test và resource server chỉ để minh họa. Production nên dùng issuer/JWKS và xác minh key rotation, trust boundary, logging, issuer/audience chính thức.

### 8.4. `DemoController.java`

```java
package com.example.hybrid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String index() {
        return "hybrid demo";
    }

    @GetMapping(value = "/login", produces = MediaType.TEXT_HTML_VALUE)
    public String login(CsrfToken csrf) {
        return """
            <!doctype html>
            <html lang="vi">
              <body>
                <form method="post" action="/login">
                  <input name="username">
                  <input name="password" type="password">
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Đăng nhập</button>
                </form>
              </body>
            </html>
            """.formatted(csrf.getParameterName(), csrf.getToken());
    }

    @GetMapping("/web/home")
    public String home(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/web/csrf")
    public CsrfToken webCsrf(CsrfToken csrf) {
        return csrf;
    }

    @GetMapping("/api/reports")
    public String reports(Authentication authentication) {
        return "reports:" + authentication.getName();
    }

    @PostMapping("/api/reports")
    @ResponseStatus(HttpStatus.CREATED)
    public String createReport(Authentication authentication) {
        return "created:" + authentication.getName();
    }
}
```

`GET /login` là HTML tối giản cho demo, không phải template production. Trong hệ thống thật, dùng template engine có HTML escaping và thiết kế giao diện hợp lệ. `CsrfToken` do Spring Security cung cấp; form gửi `_csrf` qua hidden input trong POST.

`GET /web/csrf` hữu ích nếu SPA web session cần lấy token mới sau login/logout; endpoint này yêu cầu authentication trong ví dụ. Không có controller `/api/login` phát token, vì resource server không phải nơi mặc định chịu trách nhiệm mint token.

### 8.5. Lệnh khởi chạy

Trên Bash/local (giả sử đã có Gradle wrapper và openssl):

```bash
# Sinh key demo 32 byte và truyền qua biến môi trường.
export DEMO_JWT_SECRET_BASE64="$(openssl rand -base64 32)"
./gradlew bootRun
```

Nếu app chạy không có `DEMO_JWT_SECRET_BASE64`, bean decoder sẽ không khởi tạo — **fail closed**. Không commit key này vào repo/log hay dùng làm secret production. Với PowerShell có thể tạo một giá trị Base64 ngẫu nhiên từ bộ tạo cryptographic của JDK/.NET và gán vào biến môi trường tương ứng.

Quan sát web flow với cookie jar:

```bash
# Anonymous truy cập web private: mong đợi 302 /login.
curl -i http://localhost:8080/web/home

# GET form login, giữ cookie phiên.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/login
```

Khi muốn gửi login thật bằng curl, cần lấy hidden CSRF token từ HTML và giữ cùng cookie jar. Với shell có sed:

```bash
HTML=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/login)

TOKEN=$(printf '%s\n' "$HTML" |
  sed -n 's/.*name="_csrf" value="\([^"]*\)".*/\1/p')

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=web-user" \
  --data-urlencode "password=web-pass" \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/login

# Có web session -> 200.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/web/home

# Web session cookie không đủ cho API Bearer-only -> 401.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/reports
```

Các lệnh dùng **mật khẩu demo**; không dùng `-u user:password` hay in cookie/token thật vào CI logs. Parser sed ở đây dựa trên HTML form mẫu, không dành để parse HTML phức tạp production.

Để gọi API thật cần **access token do issuer tin cậy cấp**, với signature, `iss`, `aud`, `exp` và scopes phù hợp. Demo chưa có IdP thực nên không có token hợp lệ tạo sẵn ngoài test:

```bash
# ACCESS_TOKEN phải do authorization server phù hợp cấp.
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports
```

Không nên bổ sung một endpoint `/api/dev/issue-token` public chỉ để làm curl đơn giản. Phần test tiếp theo ký JWT trong **test sources** bằng một key test, để xác minh decoder thực sự từ chối/chấp nhận các token tương ứng.

## 9. Kiểm thử đúng ranh giới với MockMvc

Tệp `src/test/java/com/example/hybrid/HybridSecurityTest.java`. Test ký HS256 access token với key test 32 byte cố định; app nhận key qua `@TestPropertySource`. Key test có thể công khai, **không dùng trên môi trường thực**.

```java
package com.example.hybrid;

import java.time.Instant;
import java.util.Base64;
import java.util.List;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties =
    "DEMO_JWT_SECRET_BASE64=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
class HybridSecurityTest {

    private static final String TEST_SECRET =
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=";

    @Autowired
    MockMvc mvc;

    private String token(
            String issuer, String audience, String scope, Instant expiry) {

        SecretKey key = new SecretKeySpec(
            Base64.getDecoder().decode(TEST_SECRET),
            "HmacSHA256"
        );
        JwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableSecret<>(key)
        );

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("api-reader")
            .audience(List.of(audience))
            .issuedAt(expiry.isBefore(now)
                ? now.minusSeconds(1000) : now)
            .expiresAt(expiry)
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader
            .with(MacAlgorithm.HS256)
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims)
        ).getTokenValue();
    }

    private String readToken() {
        return token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.read",
            Instant.now().plusSeconds(300)
        );
    }

    @Test
    void anonymousWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login")
            ));
    }

    @Test
    void loginPageIsPublic() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("<form")
            ));
    }

    @Test
    void formLoginCreatesSessionButDoesNotAuthenticateApi() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "web-user")
                .param("password", "web-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:web-user"));

        mvc.perform(get("/api/reports").session(session))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Bearer")
            ));
    }

    @Test
    void apiWithoutBearerGets401() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void bearerWithReadScopeGets200() throws Exception {
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + readToken()))
            .andExpect(status().isOk())
            .andExpect(content().string("reports:api-reader"));
    }

    @Test
    void signedTokenMissingScopeGets403() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.write",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidAudienceGets401() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            "another-api",
            "reports.read",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerGets401() throws Exception {
        String jwt = token(
            "https://attacker.invalid",
            SecurityConfig.DEMO_AUDIENCE,
            "reports.read",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredJwtGets401() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.read",
            Instant.now().minusSeconds(600)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void bearerWriteScopeCanPost() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.write",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(post("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:api-reader"));
    }

    @Test
    void bearerDoesNotLogUserIntoWeb() throws Exception {
        mvc.perform(get("/web/home")
                .header("Authorization", "Bearer " + readToken()))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login")
            ));
    }
}
```

### Điều gì được chứng minh?

| Test | Status/kết quả | Kiểm chứng |
| --- | --- | --- |
| Web anonymous | 302 login | Web entry point |
| GET login public | 200 | Tránh redirect loop do login page bị chặn |
| Form login thật + session | 302 rồi web 200 | Spring form login + session persistence |
| **Web session chỉ gửi tới API** | **401** | API không chấp nhận cookie làm Bearer |
| API anonymous | 401 | Bearer entry point |
| JWT hợp lệ + `reports.read` | 200 | Decoder + scope |
| JWT hợp lệ nhưng thiếu scope GET | 403 | Authorization khác authentication |
| JWT có sai `iss` hoặc `aud` | 401 | Ranh giới trust |
| JWT hết hạn | 401 | Token timestamp validation |
| JWT `reports.write` POST | 201 | Quyền ghi tách đọc; CSRF policy riêng |
| **Chỉ JWT header gửi tới web** | **302 login** | Bearer không trở thành web session |

`with(jwt())` trong `spring-security-test` rất tiện để tạo một JWT authentication giả khi kiểm tra authorization/controller, nhưng **không kiểm chứng signature/decoder thật**. Bộ test này gắn header chứa JWT có chữ ký test thật để đi qua resource-server filter và decoder. Để test production, bổ sung test với IdP/JWKS hợp lệ, key rotation, thuật toán khác, malformed token, tenant policy và revocation rules.

### Chạy bài test

```bash
# Khi project có Gradle wrapper:
./gradlew test

# Thử servlet container thật:
./gradlew bootRun
```

Nếu chưa có wrapper, dùng Gradle tương thích hoặc tạo wrapper theo quy trình project. MockMvc không mô phỏng đầy đủ browser cookie policy, proxy/TLS hoặc CORS preflight, nên cần live HTTP test khi behavior phụ thuộc những tầng đó. Các test không có stdout cố định; assertion status/body mới là kết quả mong đợi.

## 10. CSRF và CORS trong mô hình kết hợp

### 10.1. CSRF dựa trên cơ chế gửi credential

Câu hỏi hữu ích nhất: **browser có tự gửi credential khi bị website khác kích hoạt request không?**

- Session cookie `JSESSIONID`: thường tự gửi theo cookie policy ⇒ cần CSRF protection cho unsafe methods.
- Bearer access token chỉ nằm trong header `Authorization` do JavaScript/native client chủ động gắn ⇒ CSRF cookie pattern có thể không áp dụng.
- Bearer token được đặt **trong cookie** rồi browser tự gửi ⇒ phải đánh giá CSRF giống cookie-authenticated request.
- HTTP Basic do browser giữ credential cũng có tính chất auto-send tùy hoàn cảnh ⇒ không kết luận “không có session thì không có CSRF”.
- BFF nhận browser cookie ⇒ BFF cần CSRF, ngay cả khi API downstream chỉ nhận Bearer.

Với SPA/session cookie, token CSRF có thể được cung cấp qua endpoint/CSRF cookie và đưa về custom header. Spring Security 6 có BREACH token encoding/deferred CSRF token; khi dùng `CookieCsrfTokenRepository`, cần handler phù hợp và refresh token sau login/logout, không chỉ gọi `withHttpOnlyFalse()` rồi xem hoàn tất.

### 10.2. CORS là chính sách origin của browser

Nếu frontend ở `https://app.example.org` gọi API ở `https://api.example.org`, browser có thể gửi OPTIONS preflight trước request có header Authorization. Spring Security khuyến nghị CORS được xử lý **trước security** vì preflight không có session cookie.

Không cấu hình `allowedOrigins("*")` cùng credentialed CORS một cách tùy tiện. Chỉ cho phép origin, method và headers cần thiết. CORS **không** tạo authentication, không phải quyền dữ liệu và không chặn curl/server-side clients.

Nếu dùng BFF same-origin, browser thường chỉ gọi BFF và ít cần CORS tới resource server; token giữa BFF và API vẫn phải được xác minh.

### 10.3. Cookie bảo vệ cả sự riêng tư và tính nhất quán

Khi web login thành công nhưng GET private tiếp theo lại 302 về login, kiểm tra `Set-Cookie`/`Cookie`, `Secure`/`SameSite`/`Domain`/`Path`, TLS termination, shared session store và trusted forwarded headers. Token API không tự giúp sửa một login loop của web session.

## 11. Logout và thu hồi

**Web logout** thường được thực hiện qua `LogoutFilter` cùng `LogoutHandler` dọn `HttpSession` và `SecurityContext`; POST logout phụ thuộc CSRF policy. `LogoutSuccessHandler` quyết định redirect/body sau cleanup. Không chỉ tạo controller trả 200 rồi gọi `session.invalidate()` mà bỏ qua remember-me/CSRF/context cleanup.

**API JWT:** client bỏ token khỏi bộ nhớ không đảm bảo token đã vô hiệu hóa ở mọi resource server. Nếu cần logout/revocation tức thời, chọn token TTL ngắn, refresh token rotation, introspection/denylist hoặc policy revocation do authorization server cung cấp. Với OAuth2/OIDC, logout khỏi web app và kết thúc SSO session ở IdP là hai hành động khác nhau.

**BFF:** logout cần dọn browser session, token store server-side, refresh token và/hoặc IdP session theo chính sách. Tránh trả `LOGOUT_OK` trong khi token nằm ở server store vẫn có thể được dùng bởi một session cũ.

## 12. Scale, failure và vận hành

### Web session

- Nhiều server cần sticky session hoặc shared session store nếu cùng session phải được đọc ở các node khác nhau.
- Xem xét session fixation, timeout, concurrent session, remote logout và cách cập nhật quyền user đang có session.
- Mất session store có thể làm user bị logout hoặc lỗi service; cần fail-closed thay vì mở quyền.
- Cookie/path/domain sai sau proxy có thể gây vòng login.

### Bearer API

- JWT verification có thể không cần hỏi IdP mỗi request, nhưng JWKS/key rotation, token issuer và network caching vẫn là dependencies.
- Token đã phát hành có thể chứa quyền cũ; muốn revocation tức thời có thể phải thêm state.
- Rate limiting, audit, object-level authorization, request validation và monitoring vẫn bắt buộc.
- Không dùng secret HS256 chia sẻ lung tung giữa issuer và resource servers production; lựa chọn khoá ký/xác minh theo trust model.

### Hybrid

- Cần ownership rõ cho từng URL, login/logout endpoint, OAuth2 callback, static resource, health/error dispatch.
- Cần thống nhất response status để API không bất ngờ nhận HTML 302 và web không bất ngờ nhận Bearer challenge.
- Có logging để xác định chain nào khớp, nhưng không ghi token/cookie/password vào logs.
- Test status **và** side effects; request bị từ chối không được làm thay đổi dữ liệu.

## 13. Các sai lầm cần tránh

1. **Dùng `SessionCreationPolicy.STATELESS` ở web form login** rồi cố lưu session bằng code thủ công.
2. **Tắt CSRF toàn ứng dụng** chỉ vì có API Bearer.
3. **Trộn cookie session và Bearer vào cùng chain** mà không có chính sách rõ cho CSRF/entry point.
4. **Chỉ cấu hình `requestMatchers` mà quên `securityMatcher`** khi muốn tách hai chain.
5. **Để chain fallback `permitAll()`** và làm lộ route mới ngoài ý định.
6. **Để `/login` ngoài web matcher** khiến form login filter không nhận POST.
7. **Dùng `@WithMockUser` để khẳng định login/password đã được xác thực**.
8. **Dùng `with(jwt())` để khẳng định chữ ký JWT đã được xác minh**.
9. **Không kiểm tra audience** vì đã kiểm tra issuer.
10. **Gửi ID token OIDC tới API** thay access token đúng audience.
11. **Tin `SCOPE_reports.read` cho phép xem mọi tenant**.
12. **Để JWT trong URL/log/localStorage mà không xét XSS và leakage**.
13. **Tưởng CORS thay authentication hoặc CSRF**.
14. **Tưởng logout session thu hồi được mọi JWT**.
15. **Đưa key/password demo vào production**.
16. **Chỉ test MockMvc mà không test browser cookie, CORS, proxy/TLS thật**.
17. **Thay entry point Bearer thành 302 HTML cho API không có hợp đồng rõ**.
18. **Không bảo vệ error dispatch, OAuth2 callback, logout và link tải dữ liệu** trong chính sách chain.

## 14. Checklist trước khi quyết định kiến trúc

- [ ] Xác định client nào: browser web, SPA, mobile, BFF, machine/partner.
- [ ] Chọn đúng credential: session cookie, Bearer access token, hoặc cả hai với ranh giới tường minh.
- [ ] Xác định từng URL thuộc chain nào, rule nào, và thứ tự `@Order`.
- [ ] Web login/logout/callback thực sự được chain web xử lý.
- [ ] API token-only không nhận web session cookie làm authentication.
- [ ] Web không tự nhận Bearer token làm session, trừ khi đã thiết kế rõ.
- [ ] Web/BFF bật CSRF; API Bearer-only miễn CSRF khi threat model thỏa.
- [ ] CORS preflight được xử lý đúng trước security nếu cần cross-origin.
- [ ] JWT kiểm tra chữ ký, algorithm, issuer, audience, thời gian hiệu lực và scope.
- [ ] Access token/ID token/refresh token không bị dùng nhầm.
- [ ] Cookie có Secure, HttpOnly, SameSite, Path và Domain đúng deployment.
- [ ] Có logout/revocation, session timeout, JWT TTL và key rotation.
- [ ] Authorization theo tenant, owner, action và dữ liệu ở service/repository.
- [ ] Có test anonymous, authenticated, wrong scope, wrong issuer/audience, expired token.
- [ ] Có test **session-only → API 401** và **Bearer-only → web redirect**.
- [ ] Có test session lifecycle và CSRF với form login/logout.
- [ ] Có live HTTP/browser test cho proxy, CORS, cookie và login redirect.
- [ ] Secret/token không nằm trong source, logs hoặc URL sản phẩm thật.

### Câu hỏi tự kiểm tra

1. Vì sao một session cookie không được coi là access token Bearer?
2. Khi nào CSRF có thể tắt cho API, và khi nào API vẫn cần CSRF?
3. Vì sao API token-only thường trả 401 thay vì chuyển tới HTML login?
4. `securityMatcher` và `requestMatchers` khác nhau như thế nào?
5. Tại sao phải đưa `/login` và `/logout` vào web chain matcher nếu URL nằm ngoài `/web/**`?
6. Vì sao `STATELESS` không đồng nghĩa không có DB/cache hoặc revocation?
7. Đã kiểm tra JWT signature và issuer, tại sao còn phải kiểm tra audience?
8. Vì sao `with(jwt())` không thay thế test token có chữ ký thật?
9. BFF hạn chế rủi ro token theft do XSS ra sao, và còn phải chống gì?
10. Vì sao logout session không tự làm JWT đã phát hành hết hiệu lực?
11. Một JWT có scope READ có được xem tài liệu tenant khác không?
12. Một web session đã login có nên được API token-only chấp nhận không?

**Gợi ý:** (1) cookie là ID của state server, Bearer token là credential API cần verify; (2) dựa trên việc credential có được browser tự gửi không; (3) contract/client khác; (4) chọn filter chain và chọn authorization rule; (5) login/logout filter cần nhìn thấy request; (6) stateless chỉ nói về security context/session request; (7) token hợp lệ của API khác vẫn có cùng issuer; (8) mock bypass decoder; (9) token ở server nhưng CSRF/XSS vẫn tồn tại; (10) JWT self-contained còn hạn đến exp nếu không revoke; (11) không, cần object-level authorization; (12) không nếu policy token-only.

## Tài liệu chính thức

- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — Servlet Security Architecture / FilterChainProxy: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security — CSRF, including SPA considerations: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — Testing OAuth2 Resource Server with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
