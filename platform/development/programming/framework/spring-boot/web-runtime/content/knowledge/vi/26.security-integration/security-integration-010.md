# Ranh giới giữa cấu hình web runtime và thiết kế cơ chế xác thực chuyên sâu trong Spring Boot

## 1. Cấu hình Spring Security có nghĩa là đã hoàn thành authentication design?

**Không.** Một ứng dụng có thể khai báo `SecurityFilterChain` để chặn URL chưa xác thực, kiểm tra bearer token và trả HTTP 401/403. Việc đó chỉ giải quyết **cách bảo vệ HTTP request tại web runtime**. Nó không tự quyết định người dùng được đăng ký ra sao, password/passkey/MFA hoạt động thế nào, ai phát hành token, keys được rotate/revoke thế nào, cách khôi phục tài khoản hoặc quyền truy cập đến từng đơn hàng và tenant.

Hai nhóm trách nhiệm cần tách bạch:

- **Cấu hình web runtime:** request đi qua proxy, Servlet Filters hay WebFlux WebFilters nào; đường dẫn nào public; token/cookie đi vào SecurityContext ra sao; URL rules, response semantics, CORS/CSRF, session/cookie, HTTPS/forwarded headers, exception handlers và security headers hoạt động thế nào.
- **Thiết kế authentication/identity chuyên sâu:** xác định nguồn danh tính (IdP, user store), phương pháp chứng thực, password hash, passkey, MFA, reset/recovery, SSO/OIDC, token issuance/rotation/revocation, chống brute force, session lifecycle, audit/risk policy và mô hình quyền theo nghiệp vụ.

**Spring Security là bộ khung thực thi và tích hợp các chính sách đó trong ứng dụng Spring, không phải một identity platform hoàn chỉnh được bật bằng một property.**

Bài thuộc nhóm `Tích hợp bảo mật` của Spring Boot web-runtime, nên tập trung vào **điểm nối giữa lớp HTTP và hệ danh tính**, cách thiết kế boundary trong code, các quyết định cần chuyển sang workstream security/identity, cùng ví dụ Java 17+ Spring Boot 3.x có thể chạy và kiểm thử.

## 2. Các khái niệm không được gộp làm một

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Authentication (AuthN)** | Request hiện tại thuộc principal nào đã được xác minh? | Basic credential, session, OAuth2 access token |
| **Authorization (AuthZ)** | Principal đó được phép làm gì với resource cụ thể? | USER không đọc account của người khác; ADMIN có quyền riêng |
| **Session management** | Giữ hoặc tải lại trạng thái giữa requests ra sao? | `HttpSession`, Spring Session Redis/JDBC, stateless |
| **Credential/token lifecycle** | Ai phát hành, giới hạn, rotate, revoke, reset? | IdP, authorization server, token repository |
| **Transport/browser security** | Kênh truyền và chính sách browser có an toàn? | TLS, Secure cookies, CORS, CSRF, HSTS |
| **Abuse detection/audit** | Phát hiện hành vi đáng ngờ và điều tra thế nào? | Rate limit, risk events, login audit, tracing |

Một principal hợp lệ không được mặc nhiên xem tài nguyên của mọi người. Khi Alice đã đăng nhập và gọi `GET /api/accounts/bob`, URL rule `authenticated()` vẫn cho request đi qua **nếu không có owner-level policy**. Đây là dạng lỗi *broken object level authorization* (BOLA/IDOR).

CORS không chứng minh danh tính; nó là browser policy cho cross-origin responses. HTTPS bảo vệ đường truyền, không cấp quyền đọc dữ liệu. JWT có chữ ký hợp lệ không chứng minh token được phát hành cho đúng API hoặc user còn quyền.

## 3. Sơ đồ các lớp và ranh giới xử lý

~~~text
Browser / Mobile / Service Client
        |
        | HTTPS + Cookie / Authorization
        v
CDN / Load balancer / API gateway / Reverse proxy
        | TLS termination, routing, WAF, request limits
        v
Tomcat Servlet container / Reactor Netty HTTP server
        | HTTP parse, connection, headers
        v
Spring Security FilterChainProxy / Security WebFilters
        | CORS/CSRF, SecurityContext, authentication,
        | URL authorization, response handling
        v
DispatcherServlet / WebFlux handler mapping
        | request -> controller, DTO
        v
Application service / Domain authorization
        | object owner, tenant, workflow permission
        v
Repository / Database / downstream services

Identity Provider / Auth Server / Session Store
        | identity, credentials, keys, claims, sessions
        +----------------------------------------------+
~~~

Có thể bị từ chối ở nhiều lớp:

1. Proxy trả 429, 413 hoặc TLS error **trước khi request đến app**.
2. Spring Security trả 401 vì chưa xác thực hoặc 403 vì thiếu quyền URL/CSRF.
3. Controller trả 400 do input sai.
4. Domain service trả 403 hoặc 404 theo chính sách không được truy cập object.
5. Store/IdP gặp sự cố dẫn đến lỗi availability; **không được tự bỏ authentication để tăng uptime**.

Do vậy status code một mình chưa cho biết lỗi ở lớp nào. Request ID, security logs đã lọc token và tracing là chìa khóa điều tra.

## 4. Spring Security trong Servlet web runtime

Spring Security Servlet được gắn vào Servlet Filter Chain thông qua `DelegatingFilterProxy`. Bên trong, `FilterChainProxy` chọn **`SecurityFilterChain` đầu tiên khớp request**; các security filters được thi hành theo thứ tự do framework quản lý.

~~~text
HTTP request
    |
    v
Servlet filters
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |-- choose matching SecurityFilterChain
    |
    +-- security context
    +-- authentication and authorization filters
    +-- CSRF/CORS, exception translation, headers
    |
    v
Spring MVC DispatcherServlet
    |
    v
Controller -> Service
~~~

Các filter cụ thể và thứ tự có thể khác theo Spring Security version/configuration. Không lấy một ví dụ filter list cũ làm danh sách cố định.

Phân biệt:

- `http.securityMatcher("/api/**")` xác định **request nào đi vào một chain cụ thể**.
- `authorizeHttpRequests(...requestMatchers(...))` khai báo **quyền bên trong chain đã chọn**.
- `permitAll()` cho qua authorization decision của rule; không có nghĩa toàn bộ security filters đã bị tắt.
- `denyAll()` chủ động chặn, phù hợp cho default policy khi route không được khai báo.
- `@PreAuthorize` áp bảo vệ cho **method invocation/service**; gần dữ liệu/domain hơn URL matcher.
- `WebMvcConfigurer` cấu hình web handling/CORS; không thay `SecurityFilterChain`.

**Bẫy chain mismatch:** nếu một chain chỉ match `/api/**` và không còn chain nào khác, endpoint `/internal/**` có thể nằm **ngoài phạm vi security chain**. Khi có nhiều chain, thứ tự `@Order` và matcher phải được kiểm thử. Ưu tiên default-deny và rõ ràng mọi đường truy cập được phép.

## 5. Việc gì thuộc cấu hình web runtime?

### 5.1. HTTP policy và status

Web runtime quyết định:

- Request nào public, authenticated, yêu cầu role/scope.
- Authentication mechanism nào tích hợp vào filter: form login, HTTP Basic, bearer JWT/opaque token, OAuth2 login.
- Không authentication hoặc invalid credential được trả 401, redirect login hoặc một API error contract cụ thể.
- Thiếu quyền thường 403, còn endpoint 404/405 tùy mapping và data access.
- CORS preflight đi qua security thế nào, CSRF được áp theo client/credential mode.
- Response headers, session strategy, cookie flags, request timeout và webserver/proxy forwarding.

`AuthenticationEntryPoint` và `AccessDeniedHandler` tham gia response khi thiếu xác thực và khi bị từ chối. Không tất cả trường hợp đều giống nhau: với anonymous principal, một lỗi permission có thể được chuyển sang authentication entry point.

### 5.2. URL policy khác authorization theo đối tượng

HTTP rule `hasRole("USER")` có thể đúng cho `/api/accounts/**`, nhưng không biết account trong DB thuộc ai. Quy tắc `authenticated()` không đủ nếu user có thể thay `accountId` trên URL.

Service/domain policy phải đánh giá owner, tenant, delegated permissions, trạng thái quy trình. DB query nên scope theo principal/tenant; cache key phải phản ánh context quyền. Lớp HTTP và domain **bổ sung cho nhau**, không thay nhau.

### 5.3. TLS, proxy và external URL

Production có thể thấy browser dùng `https://shop.example.test` trong khi Spring Boot chỉ nhận `http://service:8080`. Điều này ảnh hưởng redirect OAuth2, cookie Secure, callback, absolute URL, CORS và security headers. Chỉ bật/trust forwarded headers qua reverse proxy do mình kiểm soát.

### 5.4. Session/cookie/headers

Web runtime cấu hình thời gian idle, cookie flags, SecurityContext persistence và session repository. Nhưng **global logout, revoke các thiết bị, absolute session age, MFA step-up**, token issuance không tự hoàn thành khi chỉnh session timeout.

## 6. Việc gì thuộc authentication design chuyên sâu?

| Hạng mục | Framework/tích hợp hỗ trợ | Thiết kế phải ra quyết định |
| --- | --- | --- |
| Password authentication | `UserDetailsService`, `PasswordEncoder`, authentication provider | Đăng ký, reset, breach detection, abuse control, migration hash |
| Identity federation | `oauth2Login`, client registration/OIDC | IdP nào được tin, account linking, callback, SSO/logout |
| MFA/passkeys | Authentication flows / external IdP | Enrollment, recovery, phishing resistance, step-up policy |
| Access token | OAuth2 Resource Server validation | Issuer, audience, scopes, grant flow, expiry, key rotation |
| Session/token revocation | Session repository / adapters | Logout all devices, forced revoke, incidents, persistence |
| Authorization model | URL/method rules, authorities | Role/attribute policy, owner/tenant/data permission |
| Monitoring | Events, logs, filter hooks | Alerts, retention, forensics, fraud/anomaly detection |
| Recovery and security operations | Extension points | Account lockout, recovery channel, customer support policy |

Một endpoint `POST /login` tự kiểm password rồi phát JWT **không tự nhiên** là một triển khai OAuth2/OIDC an toàn. Muốn thành authorization server cần nhiều đặc tính và hợp đồng hơn: client registration, grants, redirect/PKCE, signing keys, consent, refresh/revocation, metadata, claims, audit, threat review.

## 7. Chọn kiến trúc trước khi chọn Spring filter

### 7.1. Server-side session cho browser

~~~text
Browser -- login --> server/auth service
Browser <-- Set-Cookie: sessionId
Browser -- Cookie: sessionId --> Spring Security session lookup
                                  |
                                  v
                             principal + authorities
~~~

Thông thường dùng HttpOnly/Secure cookie, CSRF protection, session fixation protection, idle timeout, logout invalidation. Khi nhiều instance, session nằm RAM có thể mất khi đổi node; sticky sessions chỉ giữ route, còn Spring Session Redis/JDBC có thể giúp dùng shared repository.

### 7.2. Bearer access token cho API

~~~text
Client -- Authorization: Bearer token --> Resource Server
                                          |
                                          v
                                    signature / issuer /
                                    audience / time
                                          |
                                          v
                                      authorities
                                          |
                                          v
                                   domain authorization
~~~

Spring Security có thể validate JWT/opaque token và map claims/scopes. Token issuer/IdP quản lý việc cấp token, MFA, refresh, key rotation và revoke theo hợp đồng. Signed JWT **không tự được mã hóa**, nên payload có thể đọc được; đừng đặt secrets trong claims.

### 7.3. OIDC login khác OAuth2 Resource Server

- `oauth2Login` là flow ứng dụng đóng vai **OAuth2 Client/OIDC Relying Party**, điều hướng người dùng tới IdP và nhận kết quả login.
- `oauth2ResourceServer` bảo vệ **API nhận bearer access token**.
- **Authorization Server/IdP** là nơi **phát token**, quản lý danh tính và có thể đảm nhiệm MFA/login UI.
- Service-to-service client credentials hoặc workload identity lại là mô hình khác user login.

**Cấu hình Resource Server không tự tạo endpoint cấp token, đăng ký người dùng hoặc reset password.**

## 8. Ví dụ Java 17+ chạy được: URL security đối chiếu với owner security

Ví dụ dùng Spring Boot 3.3.x, Spring Security 6.x và **HTTP Basic cho localhost lab**, không phải hệ xác thực production. Người dùng `alice` và `bob` có ROLE_USER; `admin` có ROLE_ADMIN. Không có registration/password recovery/MFA/IdP — chính những phần đó nằm **ngoài scope ví dụ web runtime**.

### 8.1. Cấu trúc

~~~text
security-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/boundary/BoundaryApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/boundary/BoundarySecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-boundary'
~~~

`build.gradle` (Spring Boot 3.3.13 minh họa, Java 17):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 8.2. Java source hoàn chỉnh

Tệp `src/main/java/demo/boundary/BoundaryApplication.java`:

~~~java
package demo.boundary;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}

@Configuration
@EnableMethodSecurity
class BoundarySecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll());

        http.httpBasic(Customizer.withDefaults());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Ví dụ chỉ có GET; không tắt CSRF một cách tùy tiện.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-password"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-password"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-password"))
                .roles("USER", "ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}

@RestController
class BoundaryController {
    private final AccountService accountService;

    BoundaryController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping("/public/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/admin/stats")
    Map<String, Integer> adminStats() {
        return Map.of("demoAccounts", 3);
    }

    @GetMapping("/api/accounts/{owner}")
    ResponseEntity<Map<String, String>> account(
            @PathVariable String owner) {
        return ResponseEntity.ok(accountService.readFor(owner));
    }
}

@Service
class AccountService {
    // #p0 tham chiếu tham số method thứ nhất.
    @PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
    public Map<String, String> readFor(String owner) {
        return Map.of("owner", owner, "plan", "DEMO");
    }
}
~~~

**Đây là một file Java hợp lệ:** một public class `BoundaryApplication` và các package-private classes trong cùng package. Spring Boot tạo bean cho `@Configuration`, `@RestController`, `@Service`, và Spring Security method interceptor bảo vệ `AccountService.readFor`.

### 8.3. Đọc ví dụ theo ranh giới

1. `SecurityFilterChain` cho `/public/ping` public; `/api/admin/**` cần ADMIN; `/api/**` cần authenticated. Đây là **web URL policy**.
2. `UserDetailsService` chứa users trong RAM **để lab có credential**. Trong sản phẩm thật nó có thể được nối tới IdP/LDAP/DB và phải có quy trình bảo vệ credential. Đừng commit password cố định vào ứng dụng thật.
3. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` giúp hash password theo format mà Spring Security hiểu; việc hash là cần thiết nhưng không thay các quy trình reset, lockout, MFA, cost-tuning/rehash.
4. `SessionCreationPolicy.STATELESS` yêu cầu security filter không dùng HttpSession để duy trì SecurityContext trong flow này; Basic credential vẫn được client gửi lại. Stateless không tự bảo vệ XSS/CSRF.
5. `@EnableMethodSecurity` kích hoạt `@PreAuthorize` của service. Alice được xác thực có thể vào `/api/accounts/**`, nhưng `AccountService` từ chối owner Bob. Đây là **domain/object authorization**.
6. `#p0` tránh phụ thuộc tên tham số runtime. Method bảo vệ chỉ được đánh giá khi đi qua method-security interceptor/proxy. Self-invocation trong cùng bean có thể bypass AOP proxy; đặt boundary ở bean/service và test đường gọi thực tế.
7. `admin` có ROLE_ADMIN nên được đọc resource theo rule minh họa. Một hệ thống multi-tenant có thể vẫn phải kiểm tra tenant cho ADMIN; role name không tự chứng minh truy cập xuyên tenant hợp lệ.
8. Lab chỉ có GET và không thay đổi state; không tắt CSRF global. Khi thêm POST/PUT/DELETE, phải thiết kế CSRF theo credential mode (đặc biệt cookie hoặc HTTP Basic tự được browser đính kèm).

### 8.4. Chạy thử

Nếu có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có wrapper, cài Gradle tương thích và tạo wrapper hoặc dùng `gradle bootRun`. Đảm bảo port 8080 rảnh.

Public:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng HTTP **200 OK**, body:

~~~json
{"status":"ok"}
~~~

API thiếu credential:

~~~bash
curl -i http://localhost:8080/api/me
~~~

Kỳ vọng HTTP **401 Unauthorized** (thường có `WWW-Authenticate: Basic ...`).

Alice đã xác thực:

~~~bash
curl -i -u alice:alice-password http://localhost:8080/api/me
~~~

Kỳ vọng HTTP 200 và:

~~~json
{"user":"alice"}
~~~

Alice đọc tài khoản chính mình:

~~~bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/accounts/alice
~~~

Kỳ vọng HTTP 200:

~~~json
{"owner":"alice","plan":"DEMO"}
~~~

Alice cố đọc tài khoản Bob:

~~~bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/accounts/bob
~~~

Kỳ vọng **403 Forbidden**, vì method security trong service chặn dù URL matcher đã cho authenticated request đi qua.

Alice thử endpoint admin:

~~~bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/admin/stats
~~~

Kỳ vọng 403 tại URL policy.

Admin:

~~~bash
curl -i -u admin:admin-password \
  http://localhost:8080/api/admin/stats
~~~

Kỳ vọng 200:

~~~json
{"demoAccounts":3}
~~~

**Chỉ dùng những password này trên localhost lab.** HTTP Basic gửi credential lặp lại và cần HTTPS; giá trị trong `curl -u` có thể nằm trong command history/process list, nên không dùng cách minh họa này để xử lý mật khẩu production.

## 9. MockMvc tests: URL rule không thay owner rule

`src/test/java/demo/boundary/BoundarySecurityTest.java`:

~~~java
package demo.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BoundarySecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPingWorks() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void privateApiRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerAccount() throws Exception {
        mvc.perform(get("/api/accounts/alice")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceCannotReadBobAccount() throws Exception {
        mvc.perform(get("/api/accounts/bob")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void regularUserCannotReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats")
                .with(httpBasic("admin", "admin-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.demoAccounts").value(3));
    }

    @Test
    void adminCanReadBobAccountUnderDemoPolicy()
            throws Exception {
        mvc.perform(get("/api/accounts/bob")
                .with(httpBasic("admin", "admin-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.boundary.BoundarySecurityTest
~~~

Hai lớp kiểm tra quan trọng:

- **HTTP boundary:** anonymous → 401; authenticated USER vào admin → 403.
- **Domain boundary:** authenticated Alice vào account Bob → 403; authenticated Alice vào account Alice → 200.

Test `MockMvc` xác minh Spring Security và controller/service integration; không thay test identity provider thật, TLS/proxy, MFA, token expiry hoặc session failover. Production cần test các hệ thống ấy ở đúng layer.

## 10. HTTP 401, 403, redirect, 404: đọc đúng nguyên nhân

| Phản hồi | Ý nghĩa thường gặp | Cần phân biệt |
| --- | --- | --- |
| **401 Unauthorized** | Thiếu hoặc credential không hợp lệ; có authentication challenge | Không mặc định là thiếu role |
| **403 Forbidden** | Authenticated nhưng không có quyền, hoặc CSRF/CORS request bị chặn trong một số tình huống | URL policy hay service policy hay CORS/CSRF? |
| **302 Found** | Form login redirect | Khác API bearer token yêu cầu 401 |
| **404 Not Found** | Route/object không tồn tại hoặc chính sách cố tình che giấu tồn tại | Không tự suy là lỗi JWT |
| **429 Too Many Requests** | Rate limiting tại proxy/auth service | Không tự được Spring Security bật cho mọi login |
| **503 Service Unavailable** | Dependency như IdP/session store gặp lỗi | Không tự coi user sai password |

Khi browser báo lỗi CORS và Network thấy 401 hoặc 403, cần kiểm tra **preflight OPTIONS** và **actual request** riêng. Preflight có thể bị proxy/Security chặn trước khi authentication flow cần thiết. Không sửa OAuth2 issuer khi vấn đề là CORS config, và không tắt authorization chỉ vì một status chưa được chẩn đoán.

## 11. CSRF: đừng chỉ nhìn chữ stateless

**CSRF** xảy ra khi browser bị điều hướng để gửi request thay đổi trạng thái với credentials mà browser tự đính kèm, đặc biệt session cookies; HTTP Basic sau lần xác thực cũng có thể được browser tự gửi trong một số bối cảnh.

- CORS kiểm soát quyền **JavaScript đọc cross-origin response**, không ngăn mọi request CSRF từ form/simple requests.
- `SameSite` giúp giảm một số rủi ro cookie cross-site, nhưng không thay phân tích CSRF khi endpoint nhạy cảm.
- `SessionCreationPolicy.STATELESS` chỉ là chính sách session của Spring Security, không chứng minh request không có ambient credentials.
- Token chỉ gửi qua `Authorization` do JavaScript chủ động đính kèm có threat model CSRF khác; nhưng phải xem XSS/token storage, refresh flow, cookie usage.
- Nếu browser dùng **JWT trong cookie**, tính chất CSRF của cookie vẫn có, dù backend không dùng HttpSession.

Không tắt CSRF toàn bộ chỉ vì API dùng JSON hoặc vì một câu “REST thì không cần”. Với cookie-based application, dùng cơ chế CSRF token, SameSite và kiểm thử requests thay đổi trạng thái; nếu vô hiệu hóa một nhóm route, phải có lý do và threat model rõ.

## 12. CORS và FilterChain: integration chứ không phải login policy

~~~text
Browser
   |
   | OPTIONS /api/resource (preflight)
   | Origin + Access-Control-Request-Method
   v
CORS processing
   | allowed -> browser gửi actual request
   | denied  -> browser không gửi actual theo preflight flow
   v
Spring Security authentication + authorization
   |
   v
Controller / domain policy
~~~

Một allowed origin không được tự coi là user đáng tin; `curl` và server-to-server clients có thể giả mạo Origin. Preflight thường không mang session cookie, nên Spring Security phải xử lý CORS trước khi authentication của actual request. Với Servlet + Spring MVC CORS config:

~~~java
// Snippet trong SecurityFilterChain configuration.
http.cors(Customizer.withDefaults());
~~~

Đừng đơn giản permit all `OPTIONS/**` rồi bỏ qua CORS response headers; browser vẫn có thể chặn. Đừng dùng `allowedOrigins("*")` cùng credentials. CORS, login, CSRF và authorization có mục tiêu khác nhau.

## 13. Forwarded headers, HTTPS, cookie và OAuth callback

Production thường có TLS termination ở proxy:

~~~text
Browser -- https://app.example.test --> Reverse proxy
                                         |
                                         v
                                 http://spring:8080
~~~

Spring Boot có thể cần hiểu external scheme/host để sinh redirect sau login/OIDC callback, absolute URLs và Secure cookie. Cấu hình ví dụ **chỉ khi đã có trusted proxy**:

~~~properties
server.forward-headers-strategy=framework
~~~

Tùy container/platform, `native` có thể phù hợp hơn. Không tin trực tiếp `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` do Internet client tự gửi: gateway phải strip/overwrite và backend chỉ trust proxy được kiểm soát. Nếu không, attacker có thể gây host/proto spoofing hoặc sai redirect.

Khi hệ thống xác thực tại gateway rồi truyền `X-User` xuống backend, phải đảm bảo backend **không thể bị gọi vòng ngoài gateway**, header được tạo bằng trust mechanism an toàn và có threat model xác thực giữa services. Tin raw `X-User` từ client không phải authentication.

## 14. Session cookie: cấu hình transport khác lifecycle

Spring Boot Servlet có các property minh họa:

~~~properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

Đây là settings phù hợp **production HTTPS** với cookie policy cụ thể; test trên localhost HTTP có thể bị ảnh hưởng bởi Secure cookies. Khi dùng Spring Session, cookie resolver/`CookieSerializer` có thể kiểm soát cookie `SESSION` khác với container `JSESSIONID`, nên xác minh `Set-Cookie` của môi trường thật.

Những điều **chưa** được thiết kế chỉ nhờ các property:

- Idle timeout khác absolute session lifetime.
- Session fixation protection và rotate ID lúc privilege change.
- Logout phải invalidate session tại server, không chỉ xóa cookie browser.
- “Logout all devices”, concurrent session limits, account deactivation và forced revoke.
- Session persistence giữa node: sticky session không sao lưu RAM; Spring Session Redis/JDBC lưu tập trung nhưng có TTL/HA/serialization issues.
- MFA reauthentication hoặc step-up cho hành động nhạy cảm.
- Cache policy của response chứa thông tin cá nhân, frontend state sau logout.

Cookie SameSite dựa trên **site**, CORS dựa trên **origin**; không xem chúng là một khái niệm.

## 15. Spring Security OAuth2 Resource Server: ranh giới validator với issuer

**Resource Server** xác minh access token đã được một **Authorization Server/IdP** phát hành. Bật Spring OAuth2 Resource Server không tạo endpoints cấp token và không xây user registry/MFA.

Đoạn cấu hình **tham khảo**, yêu cầu IdP có thật và token hợp lệ; nó không phải ví dụ standalone có thể chạy độc lập như lab Basic ở mục 8:

`build.gradle` cần dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.test/issuer
spring.security.oauth2.resourceserver.jwt.audiences[0]=api://orders
~~~

Đoạn `SecurityFilterChain` thay cho HTTP Basic flow khi dự án thật dùng bearer JWT:

~~~java
@Bean
SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll());

    http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));

    http.sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

    return http.build();
}
~~~

Cần kiểm tra:

1. **Signature và thuật toán:** dùng decoder/provider chuẩn, không chỉ Base64 decode payload; không tin thuật toán/keys do token tùy ý chỉ định.
2. **`iss`:** token đúng issuer được tin; không tự lấy issuer từ token rồi tải arbitrary JWK URI.
3. **`aud`:** token được cấp cho API này, không phải token của service khác.
4. **`exp`, `nbf` và time skew:** token có hiệu lực theo chính sách và đồng hồ.
5. **Scopes/roles:** Spring thường map scopes sang `SCOPE_...` authorities; nếu domain cần ROLE_ADMIN/tenant, cấu hình converter và policy rõ.
6. **Key rotation/JWK:** IdP quản lý ký và rotate; API cần hỗ trợ cache/fetch và xử lý lỗi.
7. **Revocation/logout:** JWT tự validate có thể còn hiệu lực tới hết hạn; logout một session không tự hủy mọi access token.
8. **Error handling:** token invalid/expired thường 401; thiếu scope/permission thường 403; không log raw token.

Các property trên **không** cung cấp IdP thật, login UI, user provisioning, MFA, refresh token hoặc global logout.

### Opaque token

Một API có thể dùng introspection thay JWT validation tại chỗ. Khi đó auth server cần endpoint introspection, client credentials để gọi, timeout/cache và policy fail-closed. Opaque/JWT/session là những mô hình có trade-off khác nhau về latency, availability, revocation và dữ liệu nhạy cảm.

## 16. Authorization theo tenant/owner mới là điều bảo vệ dữ liệu

Ví dụ request:

~~~http
GET /api/orders/ORD-42
Authorization: Bearer <valid-token>
~~~

Chữ ký đúng và role `USER` chỉ nói **người gọi được xác thực**, chưa bảo đảm order `ORD-42` thuộc tenant của họ.

Sơ đồ defense in depth:

~~~text
SecurityFilterChain:
  /api/** must be authenticated
         |
         v
Controller:
  validate path/query/DTO
         |
         v
Domain service:
  is principal.tenantId == order.tenantId ?
  AND is principal owner/delegate/allowed-role ?
         |
         v
Repository:
  query by (tenantId, orderId), not just orderId
         |
         v
Response:
  data minimization + no-store on sensitive content
~~~

Không dùng `X-Tenant-Id` hoặc `X-User-Id` client khai báo như bằng chứng owner. Nếu data cache dùng `@Cacheable` mà key không có tenant/identity, response có thể bị lẫn **ngay ở origin** dù HTTP Cache-Control là no-store.

`@PreAuthorize` tiện nhưng không phải mọi rule business nên viết thành một SpEL khó audit. Với quyền phụ thuộc trạng thái DB và nhiều điều kiện, có thể dùng policy service rõ ràng, transaction isolation và truy vấn có tenant scope.

**Method security proxy pitfall:** method trong cùng bean gọi method khác qua `this` có thể không qua Spring AOP proxy, làm annotation ở method đích không thực thi. Phân tách beans/entry points, test object-level denial và không chỉ tin annotation hiện diện trong code.

## 17. Identity system: password, MFA, recovery và SSO

Các workstream chuyên sâu cần có owner riêng và security review:

### 17.1. Password và account recovery

- Password phải được hash bằng thuật toán password hashing được duy trì (BCrypt/Argon2/PBKDF2 theo yêu cầu), cost được calibrate và có lộ trình migration.
- Không lưu plaintext, không để password trong URL/log/config nguồn.
- Password reset token có entropy cao, TTL ngắn, một lần dùng, account-bound; tránh account enumeration.
- Rate limiting, credential stuffing detection, chống user enumeration và lockout policy cần cân nhắc cách attacker lợi dụng lockout để DoS.
- Account disable, đổi password, nguy cơ credential compromise cần dẫn tới revoke tokens/sessions theo chính sách.

### 17.2. MFA và step-up

- Chọn mức độ MFA: WebAuthn/passkeys/FIDO2 chống phishing tốt hơn nhiều phương thức OTP tùy threat model.
- Có flow enrollment, mất thiết bị, recovery codes, trusted device và chống bypass qua reset password.
- Một principal authenticated **không đồng nghĩa** đã qua MFA đủ cho mọi hành động. Với chuyển tiền, export dữ liệu lớn hoặc thay email, có thể yêu cầu reauthentication/step-up.
- IdP có thể phát claims `amr`/`acr` phản ánh authentication context; ứng dụng phải có hợp đồng xác thực và kiểm tra đúng, không chỉ nhìn role.

### 17.3. Federation và OAuth2/OIDC

- Với browser/mobile, chọn authorization code + PKCE và client security phù hợp; không tự tạo “đường tắt” token trong URL.
- Xác thực redirect URI, state/nonce, issuer/subject; account linking không tự gắn hai tài khoản chỉ bằng email không verified.
- Có quy trình SSO logout, deprovisioning, synchronization roles/groups và account lifecycle.
- Nếu có multi-tenant IdP, issuer, audience, subject và tenant claims phải được ràng buộc; tránh token của tenant này được dùng cho tenant khác.

Những quy trình này không thể hoàn tất bằng một bean `SecurityFilterChain`.

## 18. Spring WebFlux: cùng ranh giới nhưng API khác

WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity` thay vì Servlet `SecurityFilterChain`/`HttpSecurity`. SecurityContext đi qua **Reactor Context** theo reactive propagation, không nên giả định ThreadLocal luôn gắn đúng request qua các scheduler.

Snippet cấu hình reactive (đặt trong class `@Configuration` với Spring Security WebFlux; **không phải class độc lập**):

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http.authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/**").permitAll()
                    .pathMatchers("/api/**").authenticated()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Các imports chính: `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.context.annotation.Bean` và `org.springframework.security.config.Customizer`.

Với WebFlux Resource Server, dùng reactive JWT decoder và `oauth2ResourceServer(...jwt())` đúng stack. Không dùng Servlet `HttpSession` hoặc `OncePerRequestFilter` trong Netty WebFlux thuần; dùng `WebSession`, reactive principal, `ReactiveSecurityContextHolder` hoặc framework context propagation đúng cách.

**Ranh giới trách nhiệm giữ nguyên:** reactive web filters áp HTTP/security policy; IdP quản lý token/lifecycle; service thực thi quyền theo dữ liệu/tenant. Dùng `Mono.cache()` toàn cục cho kết quả theo user có thể rò dữ liệu giữa request; kiểm soát caching và reactive contexts riêng.

## 19. Quan sát và điều tra lỗi theo lớp

| Triệu chứng | Tầng cần kiểm tra trước | Cách xác minh |
| --- | --- | --- |
| Browser preflight trả 401 | CORS/Security chain/proxy | OPTIONS, `http.cors`, ingress |
| API 401 dù JWT “decode được” | Resource Server token validation | `iss`, `aud`, signature, expiry, JWK |
| API 403 với principal hợp lệ | URL role/scope hoặc method security | selected chain, authorities, service policy |
| Alice đọc được dữ liệu Bob | Data-level authorization | owner/tenant checks, repository/cache |
| Logout rồi JWT cũ còn gọi được | Token lifecycle | expiry, revoke/introspection strategy |
| Session mất khi load balancer đổi node | Session persistence | local vs Spring Session/shared store |
| OAuth login redirect về HTTP | Proxy forwarded scheme | trusted headers, redirect URI |
| POST 403 còn GET 200 | CSRF hoặc authZ/method | CSRF token, Cookie, rule order |
| Token khác issuer bị nhận | JWT validation thiếu trust boundary | decoder issuer/audience configuration |
| @PreAuthorize bỏ qua khi gọi nội bộ | AOP proxy/self-invocation | Spring-managed service boundary |
| User đúng role nhưng query trả tenant khác | Repository/data scoping | tenantId từ principal và query/cache key |

### Observability nên ghi gì?

- Request ID/trace ID, endpoint, status, lý do auth thất bại được chuẩn hóa, chain/node, latency.
- Bảo vệ log: **không ghi raw Authorization, Cookie, Set-Cookie, password, refresh token, session ID**.
- Phân biệt rate limit, CSRF, CORS, expired JWT, invalid audience, business unauthorized, dependency outage.
- Audit nghiệp vụ nên ghi actor, operation, resource identifier hợp lệ và outcome theo policy, không dump nguyên body chứa PII.

Một 403 do CSRF không phải bằng chứng người dùng thiếu role. Một 401 do IdP/JWK không khả dụng không được “sửa” bằng cách bỏ signature verification. **Fail closed** khi không thể xác thực credential là quy tắc an toàn mặc định.

## 20. Kiểm thử theo ranh giới trách nhiệm

| Scenario | HTTP web runtime test | Identity/domain test |
| --- | --- | --- |
| Anonymous vào private API | Security filter trả 401 | Không để lộ object qua response |
| User A đọc account A | URL authenticated | Owner policy cho phép |
| User A đọc account B | URL authenticated | Owner policy từ chối |
| USER gọi admin endpoint | Role matcher trả 403 | Role mapping chính xác |
| JWT hết hạn | Resource Server 401 | TTL/clock policy của IdP |
| JWT sai audience | Token validation từ chối | Issuer cấp đúng audience |
| Password sai liên tiếp | Authentication failures | Rate limit/abuse/audit |
| Login chưa hoàn thành MFA | Flow chặn thao tác yêu cầu step-up | MFA policy/claims đúng |
| POST với session cookie | CSRF/CORS behavior đúng | Business action có permission |
| Node lỗi hoặc rolling deploy | Proxy/filter/session không bypass | Session/token continuity/revocation |
| User chuyển tenant | Principal vẫn hợp lệ | Data scope/caches theo tenant mới |
| Account bị khóa | Security filter xử lý failure | Deprovision/revoke và recovery |

**MockMvc/WebTestClient không thay kiểm thử proxy/IdP thật.** Unit test của service cũng không thay test filter chain. Phân chia tests theo boundary giúp xác định lỗi do code, infrastructure, identity provider hay business authorization.

## 21. Những anti-pattern cần tránh

| Anti-pattern | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Tự decode JWT payload và tin `sub` | Không verify signature/issuer/audience | Dùng framework resource server decoder và validators |
| Dùng `authenticated()` thay toàn bộ domain permission | Không bảo vệ owner/tenant | Service/domain authorization |
| Tin `X-User-Id` từ Internet | Header client giả mạo được | Principal đã xác thực, trusted gateway assertions |
| Tắt CSRF vì app stateless | Browser có thể tự gửi cookie/Basic | Threat model theo credential mode |
| Dùng CORS làm firewall | cURL/server client không bị CORS browser chặn | AuthN/AuthZ độc lập |
| Có một chain `/api/**` nhưng thiếu fallback | Route ngoài chain có thể không được bảo vệ | Default deny và test route coverage |
| Tự phát JWT dài hạn với secret hard-coded | Keys/revoke/rotation không được quản lý | IdP/authorization server, secret/KMS |
| Logout chỉ xóa cookie | Server token/session có thể vẫn hợp lệ | Invalidate/revoke server-side |
| `@PreAuthorize` ở method self-invoked | Proxy/interceptor có thể không chạy | Bean boundary rõ và test |
| App cache key thiếu tenant | Lẫn dữ liệu giữa user/tenant | Scope cache key và auth mỗi access |
| Disable mọi security headers để cache CSS | Route private có thể bị cache/lộ | Chỉ allowlist public assets |
| Nuốt mọi auth exception thành HTTP 200 | Sai semantics, khó audit | Dùng 401/403 và error contract |
| Cho API tin Forwarded headers từ client | Redirect/host/proto spoofing | Trusted reverse proxy strip/overwrite |
| “Đã bật oauth2Login nghĩa là token server” | Nhầm client với issuer | Phân biệt OAuth2 roles |

## 22. Checklist trước khi tuyên bố authentication integration hoàn chỉnh

1. **Identity owner:** Có ai chịu trách nhiệm user store, passkey/password, MFA, SSO, reset/recovery?
2. **Client model:** Web session, bearer token, OAuth2 login, machine identity hay Basic? Đã phân tích trade-off?
3. **Filter coverage:** Mọi URL được match trong chain phù hợp, thứ tự chain đúng, không vô tình public?
4. **HTTP status:** 200/401/403/302/404 rõ, không lộ secret/error details?
5. **Object authorization:** owner/tenant/role/attribute ở service/DB đúng, có IDOR/BOLA regression tests?
6. **CORS/CSRF:** Browser credential modes, SameSite/Secure cookies và preflight được test?
7. **Proxy/TLS:** Forwarded headers tin cậy, callback URLs, HSTS, cookie security đúng từ public endpoint?
8. **Token:** Với JWT có signature, alg, issuer, audience, expiry, clock policy, scopes, key rotation và revoke?
9. **Session:** Idle/absolute timeout, fixation protection, logout, multi-node persistence và global revoke?
10. **Password/MFA:** Hash, recovery, throttling, enrollment, step-up và audit có thiết kế?
11. **Cache/logs:** Không log bearer/session/PII; cache backend theo scope; response nhạy cảm no-store?
12. **Resilience:** Khi IdP/session store lỗi có fail closed và sự cố được theo dõi?
13. **Testing:** Unit/service, MockMvc, proxy/IdP staging, token expiry và object permissions?
14. **Governance:** Security review, threat model, incident handling và ownership có đầy đủ?

Nếu mới làm xong `SecurityFilterChain` mà chưa có các quyết định danh tính và owner permissions, hệ thống **mới hoàn tất một phần web runtime integration**, chưa phải thiết kế authentication an toàn toàn diện.

## 23. Bài tập tự kiểm tra

**1.** `authenticated()` đã bật ở `/api/accounts/**`. Có đủ để ngăn Alice xem account của Bob?

**Đáp án:** Không. Đây là URL auth requirement, không phải object ownership. Cần service/DB authorization theo owner/tenant.

**2.** Bật `oauth2ResourceServer(...jwt())` có tạo hệ thống cấp access token và reset password không?

**Đáp án:** Không. Resource Server xác minh token do Authorization Server/IdP phát; reset/MFA/token issuance thuộc nền tảng identity.

**3.** JWT có chữ ký đúng nhưng `aud` dành cho API khác. API hiện tại nên làm gì?

**Đáp án:** Từ chối; cần validate audience, issuer, expiry, algorithm/signature và policy liên quan.

**4.** Browser dùng cookie chứa JWT; có thể tắt CSRF chỉ vì backend stateless không?

**Đáp án:** Không. Cookie vẫn có thể tự được browser gửi; CSRF threat model vẫn tồn tại.

**5.** Spring Security chặn OPTIONS preflight bằng 401. Đây có phải lỗi mật khẩu user?

**Đáp án:** Chưa chắc. Kiểm tra CORS filter integration và gateway; preflight có thể không mang user credentials.

**6.** Một `@PreAuthorize` trên method được gọi qua `this` không chạy. Lỗi ở đâu?

**Đáp án:** Method security AOP/proxy boundary. Cần thiết kế entry qua bean được proxy và test unauthorized paths.

**7.** Ingress TLS termination gửi forwarded headers nhưng app tin cả header client tự đặt. Rủi ro gì?

**Đáp án:** Host/proto spoofing, sai redirects/callbacks. Gateway phải strip/overwrite và app chỉ trust proxy có kiểm soát.

**8.** Khi token JWK không kiểm chứng được do IdP outage, cho request đi qua để tăng availability có được không?

**Đáp án:** Không. Đó là fail-open của authentication, không an toàn. Thiết kế resilience và fail-closed.

**9.** Spring Security Basic lab chạy được. Đã phù hợp để dùng làm hệ thống SSO/MFA cho production chưa?

**Đáp án:** Chưa. Lab chỉ cho thấy HTTP filter và method security; SSO/MFA/credential lifecycle là workstream riêng.

**10.** Vì sao phải test cả 401 URL, 403 owner và 403 admin?

**Đáp án:** Chúng kiểm tra **ba quyết định khác nhau**: thiếu authentication, domain ownership denial và URL role denial. Chỉ pass một loại không chứng minh các loại còn lại.

## 24. Tài liệu chính thức tham khảo

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, multi-chain selection.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matcher và HTTP authorization.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity và @PreAuthorize.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF theo browser credentials và use cases.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, audience, signature, JWK, claims, scope mapping.
- [Spring Boot — Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): server.forward-headers-strategy, trusted proxy, scheme/callback.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): HttpSession, fixation protection, session persistence.
- [Spring Security — Reactive Architecture](https://docs.spring.io/spring-security/reference/reactive/architecture.html): SecurityWebFilterChain và reactive security.
- [OAuth2 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): authorization flows và security recommendations.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): passwords, MFA, recovery, rate limits.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, default deny, owner/tenant checks.

**Kết luận:** `SecurityFilterChain`, HTTP filter/webfilter, CORS, CSRF, session và proxy là **tích hợp bảo mật ở runtime**. IdP, MFA, token lifecycle, password recovery và quyền truy cập theo domain là **thiết kế identity/authentication/authorization chuyên sâu**. Spring Security cung cấp điểm nối; bảo vệ thật cần hai lớp cộng kiểm thử và vận hành.
