# Điều tra một lỗi xác thực từ request tới provider, ngữ cảnh và response

Khi người dùng báo **“mật khẩu đúng nhưng vẫn không đăng nhập được”**, không nên kết luận ngay `PasswordEncoder` hoặc `DaoAuthenticationProvider` hỏng. Một request có thể bị chặn **trước** khi xác minh mật khẩu vì CSRF; có thể xác thực thành công nhưng không lưu `SecurityContext`; có thể có phiên hợp lệ nhưng thiếu quyền vào trang đích; hoặc server đã gửi redirect trong khi browser không giữ cookie.

Mục tiêu của bài **Thực hành tổng hợp** là học cách điều tra **một lỗi xác thực từ request tới provider, ngữ cảnh và response**, xác định **ranh giới đầu tiên thực sự thất bại** và chứng minh bản sửa bằng kiểm thử. Bài sử dụng **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Servlet/MVC, JUnit Jupiter và MockMvc**. Phần lab có form login, HTTP Basic, sự kiện xác thực, audit stage an toàn, request thứ hai và logout.

**Nguyên tắc xuyên suốt:** chỉ dùng thông tin đã được quan sát; không suy đoán từ một HTTP status. Không log, gửi ticket hoặc chia sẻ raw password, hash, OTP, access/refresh token, API key, recovery code, session ID, Cookie/Authorization headers, full Authentication hoặc request body.

## 1. Nhìn toàn bộ chuỗi trước khi sửa một thành phần

~~~text
Client / browser
   │  HTTP method + path + content type + credentials + CSRF + cookies
   ▼
Proxy / ingress / servlet container
   │
   ▼
FilterChainProxy chọn SecurityFilterChain đầu tiên match request
   │
   ├── SecurityContextHolderFilter: nạp context từ repository
   ├── CsrfFilter: POST không có token hợp lệ → 403
   │
   ▼
UsernamePasswordAuthenticationFilter (POST /login, form)
   hoặc BasicAuthenticationFilter (HTTP Basic)
   │
   ▼
AuthenticationManager, thường là ProviderManager
   │
   ├── Chọn AuthenticationProvider hỗ trợ token
   ▼
DaoAuthenticationProvider cho username/password
   │
   ├── UserDetailsService.loadUserByUsername(...)
   ├── PasswordEncoder.matches(raw, storedEncoded)
   ├── account status / policies
   └── Authentication thành công hoặc AuthenticationException
   │
   ▼
Nếu thành công: SessionAuthenticationStrategy
   │
   ├── Tạo/đặt SecurityContext
   ├── Lưu qua SecurityContextRepository nếu stateful
   └── Success handler → response / redirect
   │
   ▼
Browser nhận response, cookie, chuyển trang
   │
   ▼
Request thứ hai → phục hồi context → authorization
   │
   ├── Anonymous → entry point (login redirect hoặc 401)
   ├── Authenticated thiếu role/scope/MFA → 403
   └── Authenticated + authorized → controller/HTTP 200
~~~

Đây là **luồng tham khảo cho form login Servlet**, không phải thứ tự tuyệt đối của mọi cơ chế. JWT Resource Server, HTTP Basic, OAuth2 Login, filter tự viết và multiple `SecurityFilterChain` có đường xử lý khác nhau. Một `ProviderManager` có thể chứa nhiều providers và tùy cấu hình có parent manager; không giả định provider đang đọc trong code chính là provider request thật đang dùng.

### 1.1. Thứ tự câu hỏi cần trả lời

| Stage | Câu hỏi chẩn đoán | Bằng chứng |
| --- | --- | --- |
| **Request** | Đúng host/path/method/proxy/service chưa? | Route category, HTTP status, ingress telemetry |
| **Security chain** | Request có match đúng chain/filter không? | Security config, matcher, integration test |
| **CSRF** | Request POST dựa session có CSRF token hợp lệ không? | Negative/positive CSRF test, 403 trước provider |
| **Authentication filter** | POST `/login` hay Basic header thực sự tới filter? | Handler/provider event và request method/path đã scrub |
| **Manager/provider** | Có provider hỗ trợ `UsernamePasswordAuthenticationToken` không? | `AuthenticationSuccessEvent`/failure category, canary test |
| **User store/encoder** | Nạp đúng account? Hash/encoder tương thích? | Dữ liệu fixture và metadata có kiểm soát, không in hash |
| **Account policy** | Enabled/locked/expired/MFA? | Account state category, policy tests |
| **Session/context** | Repository đã save và request sau có restore? | Hai requests dùng cùng session trong MockMvc |
| **Authorization** | Principal có đủ authorities ở URL đích không? | 403 vs authenticated, role tests |
| **Response/client** | Handler trả redirect/401/403? Browser nhận cookie? | HTTP response + browser E2E đã scrub |

Không có một `LoginCompletedEvent` chung cho mọi authentication mechanism. `AuthenticationSuccessEvent` của manager chỉ cho biết một lần xác thực đã được chấp nhận **tại tầng đó**, không chứng minh session đã tồn tại hay client đã đến trang đích.

## 2. Phân biệt bốn loại hiện tượng dễ bị đánh đồng

### 2.1. CSRF 403 trước khi so password

Form login dùng POST dựa cookie/session thường cần CSRF token. `CsrfFilter` có thể chặn trước `UsernamePasswordAuthenticationFilter`; vì vậy:

~~~text
POST /login, username/password đúng, thiếu CSRF
→ HTTP 403
→ AuthenticationManager chưa được gọi
→ Không thể kết luận password đúng hay sai từ request này
~~~

Khi kiểm bằng `MockMvc`, `formLogin()` của Spring Security Test tự tạo POST login với CSRF hợp lệ; còn `post("/login")` không kèm `with(csrf())` thường bị chặn. **Không tắt toàn bộ CSRF để “sửa” lỗi đăng nhập**; phải sửa handshake hoặc token gửi từ client.

### 2.2. Sai credential hoặc account state

`DaoAuthenticationProvider` dùng `UserDetailsService` và `PasswordEncoder`. Trường hợp password không hợp lệ thường dẫn đến `BadCredentialsException` và form failure handler có thể redirect `/login?error`. Nhưng người dùng không đăng nhập được cũng có thể do account disabled/locked, lookup sai tenant, hash sai metadata hoặc provider không được chọn.

Không phản hồi công khai “username tồn tại nhưng password sai” hoặc “account bị khóa” khi việc đó làm lộ tài khoản. Bên trong audit có thể có code hữu hạn được phê duyệt; không log raw username/password/hash/exception chain.

### 2.3. Authentication thành công nhưng SecurityContext không duy trì

Trong Spring Security 6, `SecurityContextHolderFilter` nạp context, **không tự động lưu mọi thay đổi** khi request kết thúc. Built-in form login xử lý save đúng flow; custom controller/filter tự tạo context mà chỉ gọi `SecurityContextHolder.setContext(...)` có thể làm request đầu authenticated và request thứ hai anonymous.

Chẩn đoán bằng **hai HTTP requests**, không chỉ nhìn response của login:

~~~text
POST /login           → 302 /private
GET /private (session)→ 200          [đã phục hồi principal]
GET /private (no session) → redirect [không có credential]
~~~

Nếu redirect form đã tạo nhưng browser lại đến `/login`, cần kiểm cookie `SameSite/Secure/Domain/Path`, session store giữa replicas, repository/explicit save và URL sau redirect. Không thay mật khẩu khi lỗi nằm ở session.

### 2.4. Authentication thành công nhưng authorization thất bại

Một user có `ROLE_USER` có thể đăng nhập đúng nhưng `GET /admin` trả 403 vì endpoint yêu cầu `ROLE_ADMIN`. Đây không phải một lần kiểm password thất bại:

~~~text
Basic learner /api/me       → 200, authenticated
Basic learner /admin        → 403, missing ROLE_ADMIN
Basic admin /admin          → 200, sufficient authority
~~~

Cần áp đúng `authorizeHttpRequests`/`hasRole`, mapping authorities và chính sách MFA, không cấp mọi role chỉ để làm request xanh.

## 3. Những tín hiệu có ích và giới hạn của chúng

| Tín hiệu | Có thể suy ra | Không được suy ra |
| --- | --- | --- |
| `AuthenticationSuccessEvent` | Manager/provider chấp nhận một authentication | Browser login hoàn tất |
| `AuthenticationFailureBadCredentialsEvent` | Publisher ghi nhận failure được map là BadCredentials | Mọi loại lỗi đăng nhập đều là sai password |
| `InteractiveAuthenticationSuccessEvent` | Interactive authentication filter tới mốc phát event | Response/cookie/browser/protected GET đã thành công |
| Form `AuthenticationSuccessHandler` chạy | Handler đang xử lý success response | Client đã nhận redirect |
| HTTP 302 `/private` | Server đã phát redirect | Session/cookie chắc chắn hoạt động |
| HTTP 302 `/login?error` | Form failure handler đã chạy | Lý do chắc chắn là encoder |
| HTTP 401 với Basic | Entry point/challenge của request API | Mọi request khác cùng account đều fail |
| HTTP 403 | Access bị từ chối | Chắc chắn đã gọi PasswordEncoder |
| `SecurityContextHolder.getContext()` trong request | Principal có trong context hiện tại | Context đã được lưu vào session |
| Request protected thứ hai trả 200 | Principal/authorization hợp lệ cho request đó | Mọi request tương lai đều hợp lệ |

Nếu ứng dụng dùng `DefaultAuthenticationEventPublisher` và `@EventListener`, hãy đặt tên event stage là `PROVIDER_ACCEPTED` hoặc `PROVIDER_REJECTED` thay vì `LOGIN_COMPLETED`. Với API Bearer, một token hợp lệ có thể được kiểm ở **mỗi request**, nên đếm một event như một lần user đăng nhập mới là sai.

### 3.1. Response handler và entry point không giống nhau

- `AuthenticationFailureHandler`: thường được authentication filter gọi sau POST login thất bại; form mặc định có thể redirect đến `/login?error`.
- `AuthenticationSuccessHandler`: quyết định phản hồi sau authentication thành công, thường tạo redirect.
- `AuthenticationEntryPoint`: khi client chưa authenticated đòi tài nguyên protected, `ExceptionTranslationFilter` khởi động authentication, ví dụ redirect `/login` hoặc HTTP 401.
- `AccessDeniedHandler`/`AuthorizationFilter`: từ chối thao tác của principal đã authenticated nhưng không đủ quyền, thường 403.

Vì vậy `GET /private → /login` không tự chứng minh `POST /login` thất bại. Đây có thể là request đến sau nhưng không mang session cookie.

## 4. Cây chẩn đoán theo first failing boundary

~~~text
START: "Không vào được trang sau khi đăng nhập"
│
├─ HTTP request chưa tới service?
│   └─ ROUTING / PROXY / NETWORK / TLS
│
├─ Sai URL/method hoặc SecurityFilterChain?
│   └─ FILTER_CHAIN / LOGIN_PROCESSING_URL / MATCHERS
│
├─ POST bị CSRF chặn?
│   └─ CSRF_DENIED (provider chưa chạy)
│
├─ AuthenticationManager chưa xử lý?
│   └─ FILTER_ORDER / UNSUPPORTED_TOKEN / PROVIDER_CONFIG
│
├─ Provider từ chối?
│   ├─ USER_LOOKUP / ACCOUNT_STATUS
│   ├─ ENCODER_ID / HASH_INTEGRITY / PASSWORD_NORMALIZATION
│   └─ POLICY / MFA / EXTERNAL_IDP
│
├─ Provider accepted nhưng session strategy từ chối?
│   └─ SESSION_POLICY
│
├─ Context đặt nhưng không persist?
│   └─ SECURITY_CONTEXT_REPOSITORY / EXPLICIT_SAVE
│
├─ Server đã trả redirect nhưng client không giữ session?
│   └─ COOKIE / SESSION_STORE / PROXY
│
├─ Authenticated mà protected endpoint trả 403?
│   └─ AUTHORIZATION / ROLES / MFA
│
└─ Mọi bước trên tốt nhưng controller trả 500?
    └─ APPLICATION_ERROR / RESPONSE_HANDLING
~~~

**First failing boundary** là điểm sớm nhất có bằng chứng cho thấy hành vi sai với contract, không phải lớp xuất hiện cuối cùng trong stack trace. Ví dụ lỗi nằm ở `CsrfFilter` thì những lời giải thích về `BCryptPasswordEncoder` chưa có liên quan trực tiếp.

## 5. Chuẩn an toàn khi thu thập dấu vết

Một audit hợp lý ghi:

~~~text
audit_id=<random-server-uuid>
security_stage=HTTP_ENTER  route=LOGIN method=POST
security_stage=PROVIDER_ACCEPTED
security_stage=FORM_SUCCESS_HANDLER
security_stage=HTTP_EXIT status=302
~~~

Các dòng trên là mẫu tự thiết kế, **không phải sự kiện mặc định đầy đủ** của Spring. Không lấy session ID hoặc token làm correlation ID, vì bản thân chúng là credential. Với nhiều requests, cần một flow ID riêng do server sinh và được bảo vệ nếu phải liên kết xuyên redirect; một request audit ID chỉ nối các stage của request hiện tại.

**Nghiêm cấm log:**

- `request.getParameter("password")`, DTO login, `UserDetails.getPassword()` hoặc hash đầy đủ;
- header `Authorization`/`Cookie`/`Set-Cookie`/`X-API-Key` và request/response body chứa secret;
- raw `Authentication`, `SecurityContext`, token JWT, OTP, recovery/reset code;
- exception messages chưa đánh giá, `FieldError.getRejectedValue()`, stack trace chứa raw request;
- query string/URL chứa `code` hoặc `token`; user-controlled Request-ID/User-Agent chưa scrub;
- password thật trong testcase, command line, CI logs, error reporting/APM.

Chỉ dùng **mã stage/route/outcome trong allowlist**, UUID ngẫu nhiên do server sinh và status. `MDC` cần được xóa trong `finally` để không rò context giữa các request cùng thread pool; reactive/async pipelines cần context propagation riêng. Log collector/proxy/APM cũng phải được kiểm tra, vì một logger Java an toàn **không bảo đảm** toàn hệ thống không rò secret.

## 6. Java 17 độc lập: phân loại dấu vết của một incident

Chương trình Java 17 sau **không dùng Spring** và không chứa credential. Nó mô phỏng việc đã biết bước nào thành công để xác định tầng cần điều tra tiếp.

Tệp `AuthBoundaryClassifier.java`:

~~~java
public class AuthBoundaryClassifier {
    record Trace(boolean requestArrived,
                 boolean filterMatched,
                 boolean csrfAccepted,
                 boolean providerAccepted,
                 boolean contextRestored,
                 int lastStatus) {
    }

    static String diagnose(Trace t) {
        if (!t.requestArrived()) return "PROXY_OR_ROUTING";
        if (!t.filterMatched()) return "FILTER_CHAIN";
        if (!t.csrfAccepted()) return "CSRF";
        if (!t.providerAccepted()) return "AUTHENTICATION_PROVIDER";
        if (!t.contextRestored()) return "SECURITY_CONTEXT_OR_SESSION";
        if (t.lastStatus() == 403) return "AUTHORIZATION";
        if (t.lastStatus() >= 500) return "APPLICATION_OR_RESPONSE";
        return "NO_FAILURE_IN_OBSERVED_STAGES";
    }

    public static void main(String[] args) {
        System.out.println(diagnose(
                new Trace(false, false, false, false, false, 502)));
        System.out.println(diagnose(
                new Trace(true, true, false, false, false, 403)));
        System.out.println(diagnose(
                new Trace(true, true, true, false, false, 302)));
        System.out.println(diagnose(
                new Trace(true, true, true, true, false, 302)));
        System.out.println(diagnose(
                new Trace(true, true, true, true, true, 403)));
        System.out.println(diagnose(
                new Trace(true, true, true, true, true, 200)));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 AuthBoundaryClassifier.java
java AuthBoundaryClassifier
~~~

Stdout chính xác:

~~~text
PROXY_OR_ROUTING
CSRF
AUTHENTICATION_PROVIDER
SECURITY_CONTEXT_OR_SESSION
AUTHORIZATION
NO_FAILURE_IN_OBSERVED_STAGES
~~~

**Giới hạn của classifier:** ngoài đời, trạng thái có thể là “chưa quan sát được” chứ không phải true/false; provider, context restoration và response status có thể nằm ở **hai HTTP requests khác nhau**. Chương trình dùng để luyện đặt giả thuyết, không dùng làm công cụ tự kết luận root cause production.

## 7. Lab Spring Boot 3.5 / Spring Security 6.5: từ filter đến response

Ứng dụng mẫu bật cả **form login** lẫn **HTTP Basic** để đối chiếu. Một `SafeAuthRequestProbe` là filter quan sát **trước CsrfFilter** (nhưng không thể quan sát những thành phần nằm phía trước nó ở ingress). Một bean `AuthenticationEventPublisher` phát sự kiện manager/provider. Success/failure handlers ghi mã stage và trả redirect mặc định đã cấu hình.

**Thông tin đăng nhập chỉ dành cho lab:**

| Username | Password giả được biết công khai | Role |
| --- | --- | --- |
| `learner` | `lab-only-password-2026` | `ROLE_USER` |
| `admin` | `lab-only-admin-2026` | `ROLE_ADMIN` |

Không copy mật khẩu lab vào môi trường Internet. Production cần repository tài khoản, mật khẩu độc nhất được quản lý an toàn, HTTPS, rate limiting, MFA/session policy theo threat model và audit đã được scrub.

### 7.1. Gradle dependencies

Trong `build.gradle` của Spring Boot 3.5.x project có Gradle Boot plugin/BOM và Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Không tự thêm `spring-security-test` khác major/minor với runtime; dùng dependency management từ Boot.

### 7.2. Một file Java có ứng dụng, filter probe, provider event listeners và endpoint

Tệp `src/main/java/example/authdiag/AuthenticationDiagnosisApplication.java`:

~~~java
package example.authdiag;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class AuthenticationDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationDiagnosisApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DiagnosticSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("lab-only-password-2026"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("lab-only-admin-2026"))
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher events) {
        return new DefaultAuthenticationEventPublisher(events);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SafeAuthenticationAudit audit)
            throws Exception {

        SimpleUrlAuthenticationSuccessHandler success =
                new SimpleUrlAuthenticationSuccessHandler("/private");
        SimpleUrlAuthenticationFailureHandler failure =
                new SimpleUrlAuthenticationFailureHandler("/login?error");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    audit.stage("FORM_SUCCESS_HANDLER");
                    success.onAuthenticationSuccess(
                            request, response, authentication);
                })
                .failureHandler((request, response, exception) -> {
                    audit.stage("FORM_FAILURE_HANDLER");
                    failure.onAuthenticationFailure(
                            request, response, exception);
                })
                .permitAll());

        http.httpBasic(Customizer.withDefaults());
        http.logout(Customizer.withDefaults());

        // Trong security chain: trước CSRF để thấy request bị CSRF chặn.
        http.addFilterBefore(new SafeAuthRequestProbe(audit),
                CsrfFilter.class);
        return http.build();
    }
}

@Component
class SafeAuthenticationAudit {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeAuthenticationAudit.class);

    void stage(String code) {
        LOG.info("security_stage={} audit_id={}", code, auditId());
    }

    void enter(String route, String method) {
        LOG.info("security_stage=HTTP_ENTER audit_id={} route={} method={}",
                auditId(), route, method);
    }

    void exit(int status) {
        LOG.info("security_stage=HTTP_EXIT audit_id={} status={}",
                auditId(), status);
    }

    private String auditId() {
        String id = MDC.get("audit_id");
        return id == null ? "NO_HTTP_CONTEXT" : id;
    }

    @EventListener
    void providerAccepted(AuthenticationSuccessEvent ignored) {
        stage("PROVIDER_ACCEPTED");
    }

    @EventListener
    void badCredentials(AuthenticationFailureBadCredentialsEvent ignored) {
        stage("PROVIDER_BAD_CREDENTIALS");
    }
}

final class SafeAuthRequestProbe extends OncePerRequestFilter {
    private final SafeAuthenticationAudit audit;

    SafeAuthRequestProbe(SafeAuthenticationAudit audit) {
        this.audit = audit;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Không lấy request ID từ client, không log URL/query/headers.
        String old = MDC.get("audit_id");
        MDC.put("audit_id", UUID.randomUUID().toString());
        try {
            audit.enter(route(request), method(request));
            chain.doFilter(request, response);
        }
        finally {
            audit.exit(response.getStatus());
            if (old == null) MDC.remove("audit_id");
            else MDC.put("audit_id", old);
        }
    }

    private String route(HttpServletRequest request) {
        return switch (request.getServletPath()) {
            case "/login" -> "LOGIN";
            case "/private" -> "PRIVATE";
            case "/api/me" -> "ME";
            case "/admin" -> "ADMIN";
            default -> "OTHER";
        };
    }

    private String method(HttpServletRequest request) {
        return switch (request.getMethod()) {
            case "GET" -> "GET";
            case "POST" -> "POST";
            default -> "OTHER";
        };
    }
}

@RestController
class DiagnosticEndpoints {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "private:" + authentication.getName();
    }

    @GetMapping("/api/me")
    String whoAmI(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin-only";
    }
}
~~~

**Vì sao mã trên làm việc theo kiến trúc:**

1. `AuthenticationDiagnosisApplication` là public class duy nhất trong file; các class khác package-private.
2. `UserDetailsService` cung cấp user lab và stored BCrypt hash; `DaoAuthenticationProvider` trong cấu hình thông thường của Spring Security sử dụng encoder để verify.
3. `DefaultAuthenticationEventPublisher` tạo các authentication events; listener chỉ ghi **event code**. Failure khác BadCredentials có thể dùng các event class khác, vì thế thiếu `PROVIDER_BAD_CREDENTIALS` không chứng minh request chưa tới provider.
4. `SimpleUrlAuthenticationSuccessHandler("/private")` và `SimpleUrlAuthenticationFailureHandler("/login?error")` thực hiện redirect. Lambda chỉ quan sát stage và **ủy quyền cho handler thật**, không bỏ quên HTTP response.
5. `SafeAuthRequestProbe` được tạo trực tiếp bằng `new` và gắn vào Security filter chain, không thêm `@Component`/servlet filter registration thứ hai gây double execution.
6. Probe log method/route **đã whitelist**, không log input URL query, username, password, session ID hoặc auth object.
7. Probe chạy **trước CsrfFilter trong chain**, nhưng có các filters trước nó và cả proxy bên ngoài. Không thấy `HTTP_ENTER` không có nghĩa request chắc chắn chưa tới server.
8. `MDC` chứa UUID ngẫu nhiên từ server, được khôi phục/xóa trong `finally`; Spring events đồng bộ mặc định của app lab có thể mang cùng audit ID theo một request.
9. `httpBasic` và form login có thể cùng được bật trong lab, nhưng request thiếu credentials có HTTP entry point phụ thuộc URL, Accept và cấu hình. Test explicit JSON Accept cho Basic negative case.
10. `LogoutFilter` đã có cleanup session mặc định; bài lab không custom logout controller.

**Chưa có compile/test thực tế được chạy trong project của người đọc.** Mã mẫu cần project Boot 3.5/Security 6.5 đúng dependencies; production phải có TLS, user store, rate limits, CSRF/frontend config, MFA/account lifecycle và không dùng accounts lab.

### 7.3. Chạy và đọc stage logs

Trong project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows dùng `gradlew.bat bootRun`. Mở `http://localhost:8080/login` ở **localhost**, thử user `learner` và mật khẩu lab. Với form login đúng và CSRF hợp lệ, log có thể có dạng:

~~~text
security_stage=HTTP_ENTER audit_id=<uuid> route=LOGIN method=POST
security_stage=PROVIDER_ACCEPTED audit_id=<uuid>
security_stage=FORM_SUCCESS_HANDLER audit_id=<uuid>
security_stage=HTTP_EXIT audit_id=<uuid> status=302
~~~

Nếu password sai:

~~~text
security_stage=HTTP_ENTER audit_id=<uuid> route=LOGIN method=POST
security_stage=PROVIDER_BAD_CREDENTIALS audit_id=<uuid>
security_stage=FORM_FAILURE_HANDLER audit_id=<uuid>
security_stage=HTTP_EXIT audit_id=<uuid> status=302
~~~

Nếu POST thiếu CSRF:

~~~text
security_stage=HTTP_ENTER audit_id=<uuid> route=LOGIN method=POST
security_stage=HTTP_EXIT audit_id=<uuid> status=403
~~~

Đây là **minh họa**, không phải stdout cố định: mỗi request có UUID khác nhau, logger thường thêm timestamp/logger/thread. Nếu authentication manager/publisher của project khác demo hoặc event listener chạy async, thứ tự và số lượng events có thể thay đổi; không dùng log line position làm bằng chứng tuyệt đối.

## 8. Test tích hợp MockMvc: HTTP response, provider event và session

Tệp `src/test/java/example/authdiag/AuthenticationDiagnosisApplicationTest.java`:

~~~java
package example.authdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthenticationDiagnosisApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired ApplicationEvents events;

    @Test
    void formSuccessPersistsAuthenticationToSecondRequest()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("learner")
                .password("lab-only-password-2026"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        assertTrue(events.stream(AuthenticationSuccessEvent.class)
                .anyMatch(e ->
                        "learner".equals(e.getAuthentication().getName())));

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        // GET thứ hai không mang password, chỉ dùng cùng session.
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("learner"))
            .andExpect(content().string("private:learner"));
    }

    @Test
    void wrongPasswordReachesProviderAndRedirectsToFailure()
            throws Exception {
        mvc.perform(formLogin()
                .user("learner").password("incorrect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        assertTrue(events.stream(
                AuthenticationFailureBadCredentialsEvent.class)
                .findAny().isPresent());
    }

    @Test
    void missingCsrfStopsBeforeProvider()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "lab-only-password-2026"))
            .andExpect(status().isForbidden());

        assertEquals(0,
                events.stream(AuthenticationSuccessEvent.class).count());
    }

    @Test
    void basicCorrectPasswordIs200()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "lab-only-password-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("learner"))
            .andExpect(content().string("me:learner"));
    }

    @Test
    void basicWrongPasswordIs401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "incorrect"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedLearnerIsDeniedAdmin()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("learner", "lab-only-password-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedAdminCanAccessAdmin()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "lab-only-admin-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void anonymousHtmlRequestIsRedirected()
            throws Exception {
        mvc.perform(get("/private")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutInvalidatesRealLoggedInSession()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("learner")
                .password("lab-only-password-2026"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // Không tái sử dụng session đã invalidated.
        mvc.perform(get("/private")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Có **9 bài test**. Chạy:

~~~bash
./gradlew test --tests example.authdiag.AuthenticationDiagnosisApplicationTest
~~~

Nếu đúng dependencies và environment, kỳ vọng test pass. **Đây là expected outcome, không phải lời tuyên bố đã chạy Gradle thực tế.** Test dùng `@RecordApplicationEvents` nên có thể quan sát sự kiện do publisher phát trong method; trong app thật có nhiều managers/custom publisher thì phải test wiring cụ thể.

### 8.1. Vì sao cần cả sự kiện và HTTP assert?

- `AuthenticationSuccessEvent` xác nhận manager chấp nhận một lần authentication, **không xác nhận session có thể dùng**.
- `redirectedUrl("/private")` xác nhận handler đã gửi redirect, **không xác nhận browser nhận cookie**.
- `GET /private` với **cùng `MockHttpSession`** xác nhận repository/authorization trong ứng dụng khôi phục được principal.
- `@WithMockUser` hoặc `with(user("learner"))` bỏ qua password check; không thể dùng thay test form/Basic.
- Một POST thiếu CSRF trả 403 không được gắn nhãn “bad password”.
- Basic 200 không đồng nghĩa đã tạo browser form-session; Basic có thể xác thực mỗi request.

### 8.2. Giới hạn MockMvc

MockMvc chạy filters và controllers trong một application context, nhưng không chứng minh proxy, Browser Cookie `Secure/SameSite/Domain/Path`, HTTPS termination, load balancer, Redis/JDBC Spring Session, network failure, OAuth2/OIDC state/nonce hay remote MFA. Với incident chỉ xuất hiện trong browser/prod, phải bổ sung staging E2E và telemetry đã scrub.

## 9. Chẩn đoán provider: từ username tới PasswordEncoder

`DaoAuthenticationProvider` dùng `UserDetailsService` và `PasswordEncoder`. Một password “đúng” theo trí nhớ user có thể không match stored hash nếu:

1. UserDetailsService tìm nhầm user hoặc nhầm tenant.
2. Hash raw bcrypt legacy không có `{bcrypt}` mà login dùng `DelegatingPasswordEncoder` yêu cầu `{id}`.
3. Stored hash bị cắt do cột `VARCHAR(60)` nhưng hash prefixed `{bcrypt}` dài 68.
4. Registration encode hai lần trong khi login kiểm raw một lần.
5. Encoder/parameters/pepper khác giữa write và read, hoặc app nodes dùng version config khác.
6. Client/backend làm `trim()`/lowercase/Unicode normalization khác lúc tạo hash.
7. Account bị disabled, locked, expired hoặc credentials expired.
8. Request thực vào một SecurityFilterChain/provider khác với test.

**Phép thử an toàn:** tạo user canary trên database test, đăng ký qua đường thật, kiểm metadata format/length (không export hash), xác minh login qua form/Basic rồi restart/đổi node và thử lại. Nếu raw hash legacy được xác minh chắc chắn đúng thuật toán, migrate metadata `{id}` với backup/transaction. Nếu hash không thể xác định, dùng password reset an toàn; **không bật NoOpPasswordEncoder hoặc trả hash qua endpoint debug**.

~~~java
// Minh họa bên trong service có rawPassword và storedEncodedPassword.
// Không log một trong hai biến này.
boolean verified =
        passwordEncoder.matches(rawPassword, storedEncodedPassword);
~~~

Đừng làm:

~~~java
// SAI vì các password encoders có salt ngẫu nhiên.
boolean same = passwordEncoder.encode(rawPassword)
        .equals(storedEncodedPassword);
~~~

Ngay cả khi `matches=true` trong unit test, HTTP vẫn có thể bị CSRF chặn, role deny, session mất hoặc handler lỗi. Unit test và HTTP integration test phải được đọc ở **hai tầng** khác nhau.

## 10. SecurityContext: vì sao redirect thành công nhưng request sau anonymous?

Trong Spring Security 6, `SecurityContextHolderFilter` đọc context từ `SecurityContextRepository` nhưng không tự save mọi thay đổi khi kết thúc request. **Form login chuẩn vẫn thực hiện persistence**; custom controller/filter tự viết cần rõ trách nhiệm:

~~~java
// Đoạn trong custom controller sau khi AuthenticationManager
// đã thực sự authenticate và session policy đã được áp.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
repository.saveContext(context, request, response);
~~~

Snippet giả định các biến `verifiedAuthentication`, `repository`, `request`, `response` đã có đúng kiểu và repository **cùng nơi filter đọc**. Save trước HTTP response commit để session cookie được xử lý. **Chỉ set holder mà không save không chứng minh login persistence.** Hơn nữa `saveContext` không tự cung cấp session fixation protection, concurrent session control, MFA hoặc remember-me; custom flow phải xử lý chính sách bổ sung hoặc dùng built-in filters.

| Repository | Có lưu qua HTTP requests độc lập? | Điều cần kiểm |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Có, nếu session/cookie hợp lệ và đã save | Session creation, ID rotation, expiry, store |
| `RequestAttributeSecurityContextRepository` | Không, chỉ cùng request/dispatch | Không dùng thay session login |
| `DelegatingSecurityContextRepository` | Tùy delegates; mặc định 6.x thường gồm RequestAttribute + HttpSession | Filter và custom component dùng cùng config |
| `NullSecurityContextRepository` | Không | Phù hợp stateless; không dùng làm session persistence |

Khi browser không giữ cookie do `SameSite/Domain/Path/Secure` hoặc sau redirect request đi sang node không có shared session, MockMvc có thể pass mà E2E vẫn fail. **Không sửa stored password hash cho lỗi do cookie/proxy**.

## 11. Trạng thái HTTP phải gắn với cả ngữ cảnh

| HTTP / redirect | Có thể do | Không tự chứng minh |
| --- | --- | --- |
| 200 từ POST custom login | Handler đã trả body | Context có thể restore ở request sau |
| 200 từ GET protected | Request đó authorized và controller OK | Mọi user actions khác OK |
| 302 `/login` | Entry point mời login | Password đã bị reject |
| 302 `/login?error` | Failure handler đã được gọi | Chắc chắn sai password (có thể account/session policy) |
| 302 `/private` | Success handler redirect | Browser follow/cookie/role OK |
| 401 HTTP Basic | Chưa authenticated theo request API/entry point | Form login mọi client cũng sai |
| 403 POST login | Thường CSRF | Provider đã chạy |
| 403 GET admin | Thường authorization denied | Mật khẩu sai |
| 500 | Controller, filter, store hoặc handler exception | Chắc chắn issuer/encoder lỗi |
| 502/504 ở ingress | Proxy/gateway/upstream timeout | Request đã tới provider |

Báo cáo phải ghi **request thứ mấy**, **authentication method**, **entry point/failure handler** và **mốc filter**; không chỉ copy status code.

## 12. Runbook xử lý năm sự cố điển hình

### A. Login POST trả 403

**Quan sát:** `HTTP_ENTER` và `HTTP_EXIT=403`, không có provider success. **Thử:** formLogin helper có CSRF; raw POST thiếu CSRF. **Fix:** frontend nhận và gửi token đúng với session, giữ CsrfFilter. **Regression:** thiếu CSRF=403, có CSRF+password đúng=redirect, GET protected=200. Không disable CSRF toàn chain.

### B. Mật khẩu đúng, POST redirect thành công, GET tiếp theo lại về /login

**Quan sát:** provider accepted và success handler chạy. **Thử:** GET request khác với cùng `MockHttpSession`. Nếu pass, điều tra browser cookie/proxy/session store; nếu fail ngay trong MockMvc, kiểm `SecurityContextRepository`/explicit save/session policy. **Fix:** dùng same repo và save đúng chỗ cho custom flow, hoặc sửa cookie/session backend. **Regression:** hai-request test + E2E qua proxy.

### C. Đăng nhập được nhưng /admin=403

**Quan sát:** user đã authenticated nhưng thiếu `ROLE_ADMIN`/MFA. **Thử:** cùng Basic credentials gọi `/api/me`=200, `/admin`=403; admin test=200. **Fix:** sửa role mapping/authorization policy nếu thực sự sai; không cấp admin tùy tiện. **Regression:** test positive + negative authorization.

### D. Một nhóm users lỗi sau thay PasswordEncoder

**Quan sát:** chỉ legacy records fail, không phải CSRF. **Thử:** thống kê encoded password IDs/lengths trong kênh an toàn; account canary qua registration→DB roundtrip→login. **Fix:** migrate verified raw bcrypt sang `{bcrypt}`, map encoder legacy đúng, giữ column đủ dài; nếu không khôi phục được dùng reset. **Regression:** hash cohorts và multi-node migration tests. Không dùng `{noop}`.

### E. HTTP Basic trả 401 nhưng UI form vẫn login OK

**Quan sát:** request vào API chain; Basic entry point. **Thử:** `httpBasic(...)` với JSON Accept, provider events, rule/filter chain. **Fix:** sửa chain/httpBasic config, user store hoặc input nếu có chứng cứ; không bật session tùy tiện cho API stateless. **Regression:** Basic 200/401/403 và browser form tests riêng.

## 13. Ma trận kiểm thử 30 trường hợp

| ID | Tình huống | Kỳ vọng điều tra |
| --- | --- | --- |
| D01 | Request không tới service | Tìm ingress/proxy evidence |
| D02 | Path/method không match login filter | Phát hiện mapping sai |
| D03 | Multiple chains chọn sai chain | Sửa matcher/order |
| D04 | POST /login thiếu CSRF | 403 trước provider |
| D05 | CSRF không hợp lệ | 403, không coi là bad password |
| D06 | Form đúng password | Provider accepted, handler redirect |
| D07 | Form sai password | Failure event/handler, không session authenticated |
| D08 | Username/tenant lookup sai | Phát hiện user store mismatch |
| D09 | Account locked/disabled | Provider deny dù password có thể đúng |
| D10 | Stored hash thiếu `{id}` | Chẩn đoán encoder metadata |
| D11 | Hash bị truncate/database converter sửa | Canary roundtrip fail |
| D12 | Password normalization khác | Unicode/whitespace test |
| D13 | Provider không hỗ trợ token | ProviderNotFound/manager config |
| D14 | Session strategy từ chối sau provider accepted | Không tính login completed |
| D15 | Form success handler ném exception | Provider accepted nhưng response failure |
| D16 | Custom flow set context nhưng không save | Request sau anonymous |
| D17 | Custom flow save đúng repository | Request sau authenticated |
| D18 | Session cookie không gửi lại | Browser E2E login loop |
| D19 | Session store không chia sẻ giữa nodes | Fail khi đổi replica |
| D20 | STATELESS bearer thiếu token request sau | 401 là behavior đúng |
| D21 | HTTP Basic đúng | 200 vào endpoint phù hợp |
| D22 | HTTP Basic sai | 401 với entry point API |
| D23 | Learner vào admin | 403 authorization |
| D24 | Admin vào admin | 200 |
| D25 | Form logout đúng session | Session invalidated |
| D26 | Logout rồi lại gửi Basic đúng | Có thể authenticate request mới |
| D27 | Provider success event nhưng browser không follow redirect | Không coi là login complete |
| D28 | Raw URL/cookie/credentials xuất hiện trong log | Security QA FAIL, xử lý leak |
| D29 | Test `@WithMockUser` pass nhưng form login fail | Phát hiện mock không test provider |
| D30 | 5xx do controller/DB sau authenticated | Điều tra app error, không reset password |

## 14. Mẫu biên bản post-incident

| Trường | Ví dụ cho lỗi CSRF |
| --- | --- |
| Symptom | Browser POST login trả 403 sau thay đổi frontend |
| Scope | Route LOGIN, method POST, một nhóm browser clients |
| Observations | Filter probe ghi HTTP_ENTER và HTTP_EXIT=403, không có provider event |
| First failing boundary | `CsrfFilter` |
| Root cause | Frontend không gửi CSRF token gắn với phiên |
| Fix | Khôi phục CSRF handshake/request token |
| Security checks | Không tắt CSRF, không log raw password/Cookie |
| Regression | raw POST thiếu CSRF=403; formLogin=redirect; GET protected với session=200 |
| Residual risk | Cần browser E2E kiểm proxy/cookie/session ở staging |
| Closure | Reproduce fail trước fix, tests/E2E pass sau fix và metrics ổn định |

Bản báo cáo cần **bằng chứng theo stage**, thay đổi đã thực hiện, kiểm thử hồi quy và hạn chế còn lại. Viết “Spring Security bị lỗi” hoặc “user gõ sai mật khẩu” mà không có phép thử không đủ kết luận.

## 15. Các sai lầm cần tránh

- **Chỉ đọc HTTP status** rồi sửa PasswordEncoder: status có thể do CSRF/authorization/entry point.
- **Tắt CSRF hoặc `permitAll()` toàn chain** để tạm chạy được: vô hiệu hóa các phòng vệ quan trọng.
- **Dùng `@WithMockUser`** làm bằng chứng xác minh password: bỏ qua authentication provider.
- **Đếm AuthenticationSuccessEvent như completed login**: provider event chưa chứng minh session/client.
- **Chỉ assert POST login trả 200/302**: cần GET protected request tiếp theo.
- **Log `Authentication`, request/headers/token/password/hash**: có thể làm lộ credential trong collector/APM.
- **Cho tất cả users ROLE_ADMIN** để khắc phục 403: làm sai phân quyền.
- **Dùng NoOpPasswordEncoder** để vượt lỗi hash: tạo rủi ro và che giấu migration sai.
- **Nhầm Basic/JWT stateless với session login**: request sau không có credential có thể đúng là anonymous.
- **Bỏ qua session cookie/proxy** khi MockMvc pass: cần browser E2E.
- **Không phân biệt app/controller 500 với provider deny**: phải xác định exception stage, không log raw secret.
- **Kết luận đã fix chỉ vì một request thành công**: phải có test hồi quy và quan sát sau triển khai.

## 16. Checklist nghiệm thu

- [ ] Đã đọc đúng request path/method/chain/CSRF và auth mechanism.
- [ ] Có stage audit với ID server-generated, route/method trong allowlist.
- [ ] Không log password, encoded hash, JWT, API key, session ID, recovery code, Cookie hoặc Authorization.
- [ ] Provider events phân biệt accepted/rejected, không biến chúng thành business login completed.
- [ ] Test cả `formLogin()`, `httpBasic()` và CSRF, gồm positive/negative.
- [ ] Test user authenticated nhưng thiếu role với HTTP 403.
- [ ] Test request protected **thứ hai** dùng cùng `MockHttpSession`.
- [ ] Biết khi nào cần `SecurityContextRepository.saveContext` trong custom flow.
- [ ] Có test logout invalidates session; không coi Basic/JWT là đã revoke.
- [ ] Có browser/staging E2E cho cookie, proxy và distributed sessions.
- [ ] Có bảng symptom/hypothesis/evidence, first failing boundary, root cause và regression tests.
- [ ] Không bypass authentication, CSRF, MFA hoặc authorization để chữa lỗi.

## 17. Tài liệu tham khảo

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Testing Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/logout.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
