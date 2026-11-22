# Tích hợp AuthenticationProvider tùy chỉnh với filter, AuthenticationManager và success/failure handler

## 1. Mục tiêu và phạm vi

Một `AuthenticationProvider` tự viết chỉ giải quyết **một phần** quy trình đăng nhập: kiểm tra một kiểu `Authentication` và trả kết quả xác thực. Để người dùng thực sự đăng nhập qua HTTP, ứng dụng còn phải tạo token từ request, chuyển token tới manager, xử lý kết quả thành công/thất bại và quyết định có lưu phiên hay không.

Trong **Spring Security Servlet**, các mắt xích thường là:

1. **Filter**: xác định request đăng nhập và biến dữ liệu đầu vào thành `Authentication` chưa xác thực.
2. **AuthenticationManager** (thường là `ProviderManager`): lựa chọn `AuthenticationProvider` theo `supports(Class<?>)` và yêu cầu xác thực.
3. **AuthenticationProvider**: xác minh credential bằng quy tắc của cơ chế cụ thể, trả `Authentication` đã xác thực hoặc ném `AuthenticationException`.
4. **SessionAuthenticationStrategy** và **SecurityContextRepository** (khi dùng session): xử lý session fixation, CSRF và lưu `SecurityContext` để request tiếp theo nhận lại danh tính.
5. **AuthenticationSuccessHandler** / **AuthenticationFailureHandler**: quyết định HTTP response, ví dụ JSON 200/401 hoặc redirect phù hợp.

Bài này hướng đến **Java 17+, Spring Boot 3.5.x, Spring Security 6.x, ứng dụng Servlet MVC**. Ví dụ dùng một mã đăng nhập demo từ header để tập trung vào việc **nối đúng các thành phần**; không giới thiệu đây là phương án lưu trữ credential cho production. `AuthenticationWebFilter` và `ReactiveAuthenticationManager` của WebFlux dùng API khác.

## 2. Sơ đồ luồng tổng thể

~~~text
Client
  | POST /api/login
  | Header: X-Login-Code: <code>
  | Cookie: JSESSIONID=...
  | Header: X-CSRF-TOKEN: <token>
  v
SecurityFilterChain
  |
  +-- CsrfFilter: chặn POST thiếu/sai CSRF token nếu dùng cookie/session
  |
  +-- DemoCodeLoginFilter (chỉ khớp POST /api/login)
  |      |
  |      +-- đọc X-Login-Code
  |      +-- DemoCodeAuthenticationToken.unauthenticated(...)
  |      |
  |      v
  |   AuthenticationManager / ProviderManager
  |      |
  |      +-- provider.supports(DemoCodeAuthenticationToken.class)
  |      |       false -> thử provider khác
  |      |       true  -> provider.authenticate(token)
  |      |
  |      +-- kiểm tra credential
  |      |       sai -> AuthenticationException
  |      |       đúng -> Authentication đã authenticated=true
  |      v
  |   AbstractAuthenticationProcessingFilter
  |      |
  |      +-- Thành công:
  |      |     SessionAuthenticationStrategy
  |      |     SecurityContextHolder + SecurityContextRepository
  |      |     AuthenticationSuccessHandler -> HTTP 200 JSON
  |      |
  |      +-- Thất bại:
  |            xóa SecurityContextHolder
  |            AuthenticationFailureHandler -> HTTP 401 JSON
  |
  +-- GET /api/me ở request tiếp theo:
        SecurityContextRepository tải context từ HttpSession
        AuthorizationFilter kiểm tra đã xác thực -> controller
~~~

**Phân biệt rõ hai loại handler:**

- `AuthenticationSuccessHandler` và `AuthenticationFailureHandler` chịu trách nhiệm **kết quả của một lần authentication được filter xử lý**.
- `AuthenticationEntryPoint` chịu trách nhiệm khi một request tới tài nguyên bảo vệ **chưa được xác thực** (ví dụ `GET /api/me` khi không có session hợp lệ).
- `AccessDeniedHandler` thường xử lý người dùng **đã xác thực** nhưng **không đủ quyền** (HTTP 403).
- `CsrfFilter` có thể trả 403 **trước khi filter login được gọi**. Đừng cho rằng mọi lỗi đăng nhập đều đi qua `AuthenticationFailureHandler`.

## 3. Các API cần nối với nhau

| Thành phần | Đầu vào | Đầu ra hoặc trách nhiệm |
| --- | --- | --- |
| `AuthenticationFilter` hoặc filter tùy chỉnh | `HttpServletRequest`, request matcher | Tạo `Authentication` chưa xác thực; gọi manager |
| `AuthenticationManager.authenticate(Authentication)` | `Authentication` chưa xác thực | `Authentication` đã xác thực hoặc `AuthenticationException` |
| `AuthenticationProvider.supports(Class<?>)` | Java class của token | Quyết định provider có thể xem xét loại token đó |
| `AuthenticationProvider.authenticate(...)` | Đối tượng token đúng loại | Xác minh credential, trả kết quả hoặc exception/`null` theo hợp đồng |
| `SecurityContextHolder` | Authentication thành công | Giữ danh tính trong context của request/thread đang xử lý |
| `SecurityContextRepository` | `SecurityContext` | Lưu/đọc context giữa các request khi sử dụng session |
| `SessionAuthenticationStrategy` | Auth vừa thành công + servlet request/response | Xử lý session fixation, session limit, CSRF token theo chính sách |
| `AuthenticationSuccessHandler` | Request, response, auth thành công | HTTP 200/204, redirect hay response JSON |
| `AuthenticationFailureHandler` | Request, response, `AuthenticationException` | HTTP 401, redirect lỗi, thông báo an toàn |
| `AuthenticationEntryPoint` | Request tới URL bảo vệ khi chưa được xác thực | Yêu cầu đăng nhập hoặc trả HTTP 401 |

**Contract quan trọng:** một filter tạo token **chưa xác thực**; provider không lấy role/`isAuthenticated` từ client. `supports` chỉ chọn class phù hợp, chưa xác minh secret. Handler quyết định response và không thay thế chức năng xác thực credential.

### Vì sao cần hiểu ProviderManager?

Một `ProviderManager` có thể chứa nhiều provider. Nó hỏi lần lượt `supports(authentication.getClass())`, bỏ qua provider không hỗ trợ, gọi `authenticate` trên provider phù hợp, dừng khi nhận kết quả thành công. Provider có thể trả `null` để nhường xử lý; tùy exception và cấu hình, manager có thể thử provider sau. Nếu không provider nào xác thực được và không có parent manager giải quyết, có thể nhận `ProviderNotFoundException`.

Do đó, lỗi `ProviderNotFoundException` thường cần kiểm tra **kiểu token và cách đăng ký manager/provider**, thay vì chỉ kiểm tra password. Không nên “chữa” bằng `supports(...) { return true; }` cho mọi loại token.

## 4. Chọn filter tích hợp: có hai cách hợp lệ

**Cách A — tái sử dụng filter có sẵn.** Nếu provider tùy chỉnh nhận `UsernamePasswordAuthenticationToken`, có thể dùng `formLogin`/`UsernamePasswordAuthenticationFilter` và đăng ký provider trong manager. Filter sẵn có đã xử lý mẫu `username`/`password` form-urlencoded, tích hợp success/failure và session. Cách này phù hợp nếu đầu vào giống form login thông thường nhưng cách kiểm chứng user khác.

**Cách B — một token/protocol riêng.** Nếu sử dụng API key, OTP, signed challenge hoặc một cơ chế mới, dùng token riêng và một filter đọc đúng dữ liệu đầu vào. Spring Security hỗ trợ giải pháp ghép `AuthenticationFilter` với `AuthenticationConverter`; một lựa chọn khác là kế thừa `AbstractAuthenticationProcessingFilter`.

Bài thực hành chọn **`AbstractAuthenticationProcessingFilter`** vì nó có sẵn các điểm cấu hình `setAuthenticationManager`, `setSessionAuthenticationStrategy`, `setSecurityContextRepository`, `setAuthenticationSuccessHandler` và `setAuthenticationFailureHandler`. Đây là minh họa trực tiếp cả năm thành phần được yêu cầu. Khi dùng `AuthenticationFilter` thay thế, phải chú ý cơ chế session và context persistence của nó; đừng cho rằng các filter có cùng mọi hook.

## 5. Ví dụ hoàn chỉnh: custom provider + login filter + manager + handlers

Demo hỗ trợ:
- `POST /api/login` nhận header `X-Login-Code` và CSRF token, trả JSON khi đăng nhập thành công hoặc thất bại.
- `GET /api/csrf` cho client lấy CSRF token và session cookie trước khi POST.
- `GET /api/me` chỉ cho phép người đã đăng nhập, đọc danh tính từ session.
- Một `DemoCodeAuthenticationProvider` duy nhất nhận `DemoCodeAuthenticationToken`; credential đúng là `learn-12345` (chỉ dùng cho demo).

Không dùng `POST /api/login` trên hệ thống thật với một secret chung viết cứng trong mã nguồn. Nên dùng một identity service/credential store có quản lý secret, audit, hết hạn/thu hồi và chống dò mật khẩu. Đây là mô hình có **HTTP session**, không phải mô hình JWT stateless.

### 5.1. Cấu trúc dự án và Maven

~~~text
auth-chain-demo/
├── pom.xml
└── src/
    ├── main/java/demo/authchain/AuthChainDemoApplication.java
    └── test/java/demo/authchain/AuthChainDemoApplicationTests.java
~~~

`pom.xml` sau dành cho **Java 17 và Spring Boot 3.5.7**; starter quản lý các phiên bản thư viện Spring Security tương thích qua dependency management:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>auth-chain-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Với sản phẩm đang dùng bản Spring Boot/Spring Security mới hơn, hãy áp dụng các bản vá bảo mật được dự án hỗ trợ; ví dụ được cố định theo nhánh 3.5/6.5 để minh họa và kiểm tra tính tương thích API.

### 5.2. Toàn bộ mã Java

Tạo file `src/main/java/demo/authchain/AuthChainDemoApplication.java`:

~~~java
package demo.authchain;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthChainDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthChainDemoApplication.class, args);
    }

    // 1. Provider -> Manager: chỉ provider này được gọi cho token của nó.
    @Bean
    AuthenticationManager loginAuthenticationManager() {
        AuthenticationProvider provider = new DemoCodeProvider();
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager loginAuthenticationManager,
            ObjectMapper objectMapper) throws Exception {

        // 2. Repository dùng để LƯU context khi login thành công
        // và ĐỌC lại context trong các request có session tiếp theo.
        SecurityContextRepository contextRepository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        // 3. Dùng cookie/session -> giữ CSRF, không tắt cho /api/login.
        CsrfTokenRepository csrfRepository = new HttpSessionCsrfTokenRepository();

        // 4. Filter nhận đúng AuthenticationManager ở trên.
        DemoCodeLoginFilter loginFilter =
            new DemoCodeLoginFilter(loginAuthenticationManager);

        loginFilter.setSecurityContextRepository(contextRepository);
        loginFilter.setSessionAuthenticationStrategy(
            new CompositeSessionAuthenticationStrategy(
                List.of(
                    new ChangeSessionIdAuthenticationStrategy(),
                    new CsrfAuthenticationStrategy(csrfRepository)
                )
            )
        );

        // 5. Thành công: filter đã chạy session strategy và lưu SecurityContext.
        loginFilter.setAuthenticationSuccessHandler(
            (request, response, authentication) -> {
                response.setStatus(HttpServletResponse.SC_OK);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                objectMapper.writeValue(
                    response.getWriter(),
                    Map.of(
                        "status", "authenticated",
                        "principal", authentication.getName()
                    )
                );
            }
        );

        // 6. Thất bại: không trả secret hay tiết lộ khác biệt về user.
        loginFilter.setAuthenticationFailureHandler(
            (request, response, exception) -> {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                objectMapper.writeValue(
                    response.getWriter(),
                    Map.of("error", "invalid_credentials")
                );
            }
        );

        http
            .authenticationManager(loginAuthenticationManager)
            .securityContext(context ->
                context.securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(errors -> errors.authenticationEntryPoint(
                (request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            // Tránh filter form/basic không phục vụ giao thức demo.
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // Đặt filter tại vị trí login đã biết trong security chain.
            .addFilterAt(loginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    // Token có ý nghĩa riêng: credential là code từ client.
    static final class DemoCodeAuthenticationToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private String code;

        private DemoCodeAuthenticationToken(
                Object principal,
                String code,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {
            super(authorities);
            this.principal = principal;
            this.code = code;
            // Chỉ factory private của lớp quyết định trạng thái trusted.
            super.setAuthenticated(authenticated);
        }

        static DemoCodeAuthenticationToken unauthenticated(String code) {
            return new DemoCodeAuthenticationToken(
                "unverified", code, List.of(), false);
        }

        private static DemoCodeAuthenticationToken verified(String name) {
            return new DemoCodeAuthenticationToken(
                name,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_CLIENT")),
                true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return code;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            this.code = null;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Cannot trust an unverified login token");
            }
            super.setAuthenticated(false);
        }
    }

    // Provider chỉ hiểu DemoCodeAuthenticationToken.
    static final class DemoCodeProvider implements AuthenticationProvider {

        private static final String LEARNING_ONLY_CODE = "learn-12345";

        @Override
        public boolean supports(Class<?> type) {
            return DemoCodeAuthenticationToken.class.equals(type);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (authentication == null ||
                    authentication.getClass() != DemoCodeAuthenticationToken.class) {
                return null;
            }

            DemoCodeAuthenticationToken attempt =
                (DemoCodeAuthenticationToken) authentication;

            if (attempt.isAuthenticated()
                    || !(attempt.getCredentials() instanceof String supplied)
                    || supplied.isBlank()) {
                throw new BadCredentialsException("Invalid credentials");
            }

            byte[] expected =
                LEARNING_ONLY_CODE.getBytes(StandardCharsets.UTF_8);
            byte[] actual =
                supplied.getBytes(StandardCharsets.UTF_8);

            if (!MessageDigest.isEqual(expected, actual)) {
                throw new BadCredentialsException("Invalid credentials");
            }

            // Principal và quyền được quyết định từ phía server.
            return DemoCodeAuthenticationToken.verified("training-client");
        }
    }

    // Filter: matcher + trích xuất code + gọi manager.
    static final class DemoCodeLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        DemoCodeLoginFilter(AuthenticationManager manager) {
            super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response) {

            String code = request.getHeader("X-Login-Code");
            if (code == null || code.isBlank()) {
                throw new BadCredentialsException("Invalid credentials");
            }

            Authentication candidate =
                DemoCodeAuthenticationToken.unauthenticated(code);
            return getAuthenticationManager().authenticate(candidate);
        }
    }

    @RestController
    static class DemoApi {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName()
            );
            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken()
            );
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("principal", authentication.getName());
        }
    }
}
~~~

### 5.3. Điểm tích hợp chính xác trong code

**(1) Provider và Manager.** Bean `loginAuthenticationManager()` tạo `ProviderManager` chứa `DemoCodeProvider`. `DemoCodeProvider.supports(...)` dùng so sánh class chính xác nên chỉ xử lý `DemoCodeAuthenticationToken`. Khi credential sai, provider ném `BadCredentialsException`. Khi đúng, nó trả token trusted có principal và authorities do server cung cấp. Không trả lại secret trong token kết quả.

**(2) Filter quyết định khi nào xác thực.** `DemoCodeLoginFilter` kế thừa `AbstractAuthenticationProcessingFilter` và có matcher `POST /api/login`. Nó đọc header, tạo token chưa xác thực rồi gọi `getAuthenticationManager().authenticate(candidate)`. Một `GET /api/me` không bị filter này “ăn” hoặc chuyển thành một lần login mới.

**(3) Manager nối chính xác.** Cùng đối tượng manager được cấp cho filter và khai báo qua `http.authenticationManager(...)`. Nếu có nhiều `SecurityFilterChain`, mỗi chain có thể có manager riêng; luôn kiểm tra chain thực tế đang xử lý URL. Việc tạo provider thành Spring bean nhưng không kết nối tới manager mà filter dùng có thể khiến `ProviderNotFoundException` xuất hiện.

**(4) Handler quyết định response.** Khi manager xác minh thành công, filter chạy session strategy, dựng/lưu context, rồi gọi success handler trả `200 OK` kèm JSON. Nếu xác thực thất bại, filter gọi failure handler trả `401 Unauthorized` và response JSON nhất quán. Không để exception message tùy ý hoặc raw credentials đi ra client.

**(5) Context và session.** `SecurityContextHolder` phục vụ request hiện tại; `SecurityContextRepository` quyết định khả năng tải lại danh tính ở request tiếp theo. Lưu ở `HttpSession` và đọc cùng repository giúp `GET /api/me` nhận người dùng đã đăng nhập. `RequestAttributeSecurityContextRepository` hỗ trợ việc giữ context qua các kiểu dispatcher của cùng request, còn `HttpSessionSecurityContextRepository` giữ context giữa các request.

**(6) Chiến lược phiên.** `ChangeSessionIdAuthenticationStrategy` thay session ID để giảm session fixation. `CsrfAuthenticationStrategy` làm mất hiệu lực token CSRF cũ khi xác thực thành công, nên frontend cần lấy token mới trước các request thay đổi trạng thái tiếp theo. Với `AbstractAuthenticationProcessingFilter`, dùng `setSessionAuthenticationStrategy` bảo đảm chiến lược phiên được gọi trong luồng xác thực thành công trước success handler.

**(7) Chặn truy cập chưa đăng nhập.** `.anyRequest().authenticated()` vẫn kiểm tra các endpoint bảo vệ. Một request `GET /api/me` thiếu session không phải login thất bại, do đó được trả `401` bởi `AuthenticationEntryPoint` trong cấu hình này.

## 6. Chạy thủ công và đọc đúng HTTP response

Trong thư mục dự án:

~~~bash
mvn test
mvn spring-boot:run
~~~

Ứng dụng Spring Boot cần Maven và JDK 17+; không thể `javac` độc lập nếu classpath không có Spring Security, Jackson và Jakarta Servlet.

Trước tiên lấy cookie session và CSRF token:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

Body sẽ có **hình dạng** sau; token thực tế là chuỗi ngẫu nhiên thay đổi theo phiên:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<csrf-token-thuc-te>"}
~~~

Gửi POST với cookie và **token thực tế** lấy từ bước trước:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -X POST http://localhost:8080/api/login \
  -H 'X-Login-Code: learn-12345' \
  -H 'X-CSRF-TOKEN: <csrf-token-thuc-te>'
~~~

Khi đúng, kỳ vọng HTTP 200 với nội dung JSON (thứ tự thuộc tính không quan trọng):

~~~json
{"status":"authenticated","principal":"training-client"}
~~~

Dùng cookie session đã cập nhật để gọi endpoint bảo vệ:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Kỳ vọng:

~~~json
{"principal":"training-client"}
~~~

Các trường hợp quan trọng khác:

| Hành động | Kết quả mong đợi |
| --- | --- |
| POST đúng code và CSRF token hợp lệ | `200 OK`, JSON thành công, session được lưu |
| POST sai code nhưng CSRF hợp lệ | `401 Unauthorized`, `{"error":"invalid_credentials"}` |
| POST thiếu `X-Login-Code` nhưng CSRF hợp lệ | `401 Unauthorized`, JSON lỗi tương tự |
| POST không có/sai CSRF token | `403 Forbidden` do `CsrfFilter` xử lý trước login filter |
| GET `/api/me` không có session hợp lệ | `401 Unauthorized` do `AuthenticationEntryPoint` |
| GET `/api/me` với session đã xác thực | `200 OK` và principal |
| GET `/api/login` | Không khớp login filter; nếu không có quyền, `401` |
| POST tới URL khác `/api/login` | Không chạy login filter, áp dụng authorization/CSRF riêng |

**Chú ý:** Không điền nguyên văn chuỗi `<csrf-token-thuc-te>`. Trên Windows PowerShell, cú pháp quoting của lệnh `curl` có thể khác; dùng `curl.exe` hoặc công cụ HTTP client phù hợp. Sau lần login thành công, lấy CSRF token mới nếu cần POST/PUT/PATCH/DELETE khác.

## 7. Kiểm thử bằng MockMvc: manager, filter, handler và session

Các bài test sau có hai mục đích: kiểm tra việc **tích hợp HTTP** (đúng filter, đúng status, lưu context) và kiểm tra **routing loại token** (manager chỉ chọn provider hỗ trợ class). Thêm `spring-boot-starter-test` và `spring-security-test` scope test như `pom.xml` bên trên.

Tạo `src/test/java/demo/authchain/AuthChainDemoApplicationTests.java`:

~~~java
package demo.authchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthChainDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void loginSucceedsAndSessionWorksOnNextRequest() throws Exception {
        MvcResult result = mvc.perform(post("/api/login")
                .with(csrf())
                .header("X-Login-Code", "learn-12345"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("authenticated"))
            .andExpect(jsonPath("$.principal").value("training-client"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("training-client"));
    }

    @Test
    void incorrectCredentialUsesFailureHandler() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .header("X-Login-Code", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void missingCredentialUsesFailureHandler() throws Exception {
        mvc.perform(post("/api/login").with(csrf()))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void missingCsrfIsRejectedBeforeLoginFilter() throws Exception {
        mvc.perform(post("/api/login")
                .header("X-Login-Code", "learn-12345"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedEndpointWithoutSessionUsesAuthenticationEntryPoint()
            throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void providerSupportsOnlyItsOwnTokenType() {
        var provider = new AuthChainDemoApplication.DemoCodeProvider();

        assertTrue(provider.supports(
            AuthChainDemoApplication.DemoCodeAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
        assertFalse(provider.supports(Authentication.class));
    }

    @Test
    void managerRejectsUnregisteredTokenType() {
        AuthenticationManager manager = new ProviderManager(
            new AuthChainDemoApplication.DemoCodeProvider());

        assertThrows(ProviderNotFoundException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "password")));
    }

    @Test
    void managerRejectsBadCodeEvenWithCorrectTokenClass() {
        AuthenticationManager manager = new ProviderManager(
            new AuthChainDemoApplication.DemoCodeProvider());

        assertThrows(BadCredentialsException.class,
            () -> manager.authenticate(
                AuthChainDemoApplication.DemoCodeAuthenticationToken
                    .unauthenticated("bad")));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng trong môi trường phù hợp:** 8 test pass; không có failure/error. Các test minh họa ở đây là mã nguồn cần được chạy trong dự án, không phải kết quả test đã thực thi ở hệ thống của người học.

Tại sao những test này quan trọng?

- `loginSucceedsAndSessionWorksOnNextRequest` chứng minh **tổng thể**: filter nhận POST, provider kiểm tra code, success handler trả JSON, và context được lưu để đọc lại.
- `incorrectCredentialUsesFailureHandler` tách nhánh provider từ chối credential khỏi nhánh xử lý kết quả.
- `missingCsrfIsRejectedBeforeLoginFilter` đảm bảo JSON hay header login không tự động bỏ qua CSRF khi dùng session cookie.
- `protectedEndpointWithoutSessionUsesAuthenticationEntryPoint` xác nhận `AuthenticationEntryPoint` giải quyết request chưa đăng nhập, khác failure handler.
- `providerSupportsOnlyItsOwnTokenType` và `managerRejectsUnregisteredTokenType` xác nhận việc đăng ký và routing theo **token class**, tránh một provider tùy chỉnh nhận nhầm username/password.

Nếu dự án thật có proxy, context path, nhiều security chain, CORS, logout hoặc session policy khác demo, bổ sung integration test tương ứng.

## 8. Tích hợp cách đơn giản hơn với form login có sẵn

Không phải mọi provider tùy chỉnh đều cần filter mới. Nếu bài toán là thay quy tắc kiểm chứng của username/password nhưng **vẫn dùng HTML form login**, `UsernamePasswordAuthenticationFilter` đã tạo `UsernamePasswordAuthenticationToken` và gọi manager. Chỉ cần đăng ký một provider có `supports(UsernamePasswordAuthenticationToken.class)` đúng, rồi cấu hình handler.

Ví dụ **đoạn cấu hình minh họa**, giả định biến `customUsernamePasswordProvider` đã là một `AuthenticationProvider` hợp lệ:

~~~java
http
    .authenticationProvider(customUsernamePasswordProvider)
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .successHandler((request, response, authentication) -> {
            response.sendRedirect(request.getContextPath() + "/home");
        })
        .failureHandler((request, response, exception) -> {
            response.sendRedirect(request.getContextPath() + "/login?error");
        })
        .permitAll()
    );
~~~

Chú ý:
- Đây **không phải** một chương trình độc lập; cần cung cấp `customUsernamePasswordProvider` và các import trong `SecurityFilterChain` hiện có.
- Bộ lọc form login mặc định đọc `username`/`password` từ form parameters, **không tự đọc JSON**.
- Nếu có cả `DaoAuthenticationProvider` và custom provider hỗ trợ cùng `UsernamePasswordAuthenticationToken`, phải hiểu thứ tự và hành vi fallback của manager. Một provider trả `null` khác một provider ném `BadCredentialsException`; provider khác vẫn có thể được thử tùy tình huống.
- `sendRedirect` đến `/home` là đích cố định từ server. Nếu dùng `next` hoặc `returnUrl` từ client, phải xác minh đích để tránh open redirect.
- Các strategy dành cho form login được Spring Security cấu hình theo cơ chế của filter chuẩn; khi tự dựng filter cần xem lại session và context persistence.

Chọn cách tái sử dụng khi đã có đúng filter cho giao thức đầu vào; chọn custom filter khi có một loại token và cơ chế đọc request thực sự khác.

## 9. Lựa chọn khác: AuthenticationFilter + AuthenticationConverter

Khi muốn ghép các thành phần thay vì kế thừa `AbstractAuthenticationProcessingFilter`, Spring Security có `AuthenticationFilter`:

~~~java
// Minh họa cách nối thành phần, chưa phải cấu hình chạy độc lập.
AuthenticationConverter converter = request -> {
    String code = request.getHeader("X-Login-Code");
    if (code == null || code.isBlank()) {
        throw new BadCredentialsException("Invalid credentials");
    }
    return DemoCodeAuthenticationToken.unauthenticated(code);
};

AuthenticationFilter filter = new AuthenticationFilter(manager, converter);
filter.setRequestMatcher(
    new AntPathRequestMatcher("/api/login", "POST"));
filter.setSecurityContextRepository(contextRepository);
filter.setSuccessHandler(successHandler);
filter.setFailureHandler(failureHandler);
~~~

`AuthenticationFilter` phù hợp để **tách riêng bước chuyển đổi request thành `Authentication`**. Tuy vậy, cần hiểu sự khác biệt giữa các filter:

- `AuthenticationFilter` có `setSecurityContextRepository`, và mặc định **không tự lưu** `SecurityContext` trừ khi được cấu hình repository.
- `AbstractAuthenticationProcessingFilter` trong ví dụ chính có `setSessionAuthenticationStrategy`, chạy chiến lược phiên trong luồng xác thực thành công.
- Nếu thay ví dụ bằng `AuthenticationFilter` và vẫn dùng cookie/session, phải tích hợp tương đương cơ chế session fixation và CSRF cho phù hợp; không bê nguyên code cấu hình từ filter này sang filter kia rồi giả định hành vi giống hệt.
- Nếu cơ chế thực sự stateless và client gửi token trên **mọi request**, mô hình xác thực có thể không cần session repository, nhưng cần filter xác minh token cho mọi request cần bảo vệ. Không thể chỉ trả 200 ở `POST /api/login` rồi chờ Spring Security tự nhận diện người dùng ở request kế tiếp.

## 10. Statefulness, SecurityContext và luồng lỗi

### 10.1. Điều gì được lưu và khi nào?

`SecurityContextHolder` mặc định dùng chiến lược gắn với thread, phù hợp với phần lớn request Servlet thông thường. Nó không tự có nghĩa là đăng nhập vĩnh viễn. Với Spring Security 6, nếu custom filter/controller tự hoàn tất authentication, việc **lưu SecurityContext** vào repository tương ứng là quyết định phải thực hiện rõ. Ví dụ chính đặt chung `DelegatingSecurityContextRepository` cho filter và `HttpSecurity`.

Không dùng cùng lúc chính sách “stateless” và kỳ vọng session tự giữ login:

| Chế độ | Client gửi gì ở request sau? | Context tồn tại ở đâu? |
| --- | --- | --- |
| Session cookie | Cookie phiên, được trình duyệt gửi lại | Server đọc `HttpSession` thông qua repository |
| Bearer token stateless | Token ở `Authorization` header mỗi request | Filter xác minh token từng request, thường không lưu session |
| HTTP Basic | Username/password trong header từng request | Basic authentication filter xác minh theo cấu hình |
| Một lần login trả 200 nhưng không lưu gì | Không có credential mới | Request tiếp theo có thể thành `401` |

### 10.2. Xử lý lỗi và tránh rò rỉ thông tin

- **Authentication thất bại do credential:** dùng `AuthenticationFailureHandler` để trả lỗi đồng nhất, ví dụ `401` và một mã `invalid_credentials`. Không echo code/password, không tiết lộ user có tồn tại hay không.
- **Request không có authentication tới URL cần bảo vệ:** `AuthenticationEntryPoint`, thường là 401 cho API hoặc redirect sang login cho web UI.
- **Đã xác thực nhưng thiếu quyền:** `AccessDeniedHandler` và authorization rules (thường 403). Provider không cấp quyền chỉ vì client tự gửi role.
- **CSRF thất bại:** mặc định thường 403, xảy ra trước login handler khi CSRF filter chặn.
- **Sai Content-Type hoặc JSON lỗi cấu trúc:** nếu filter dùng JSON converter, có thể phân biệt 400/415 với 401 bằng loại exception và handler. Ví dụ này không parse JSON.
- **Lỗi nội bộ:** không biến mọi `RuntimeException` thành 401; cấu hình logging/observability và phản hồi 5xx phù hợp.

### 10.3. Chống session fixation và giữ CSRF

Với đăng nhập dựa trên cookie, session fixation là nguy cơ nếu ID phiên trước và sau xác thực không thay đổi. `ChangeSessionIdAuthenticationStrategy` làm mới session ID khi phiên đã tồn tại. `CsrfAuthenticationStrategy` xóa CSRF token cũ khi xác thực thành công để buộc client lấy token mới.

Nếu production giới hạn số phiên đăng nhập đồng thời, session strategy cần thêm `SessionRegistry` và cách ghi nhận/thu hồi phiên phù hợp. Nếu có logout, đảm bảo hủy session và security context đúng cơ chế, kết hợp CSRF/token rotation. Đừng chỉ cấu hình một success handler trả JSON rồi coi mọi bước session lifecycle đã được xử lý.

## 11. Những sai lầm thường gặp khi ghép thành phần

| Sai lầm | Triệu chứng hoặc rủi ro | Cách khắc phục |
| --- | --- | --- |
| Tạo provider nhưng không gắn vào manager mà filter sử dụng | `ProviderNotFoundException`, dù class provider tồn tại | Đăng ký provider vào đúng manager hoặc cấu hình chain phù hợp |
| Filter tạo nhầm `UsernamePasswordAuthenticationToken` cho API key | Provider API key không hỗ trợ token hoặc provider khác xử lý nhầm | Định nghĩa token riêng đúng giao thức |
| `supports` luôn trả `true` | Provider nhận token không đúng loại | So sánh đúng concrete token class hoặc subtype có chủ đích |
| Provider đánh dấu token đầu vào authenticated trước khi kiểm chứng | Có thể nâng quyền | Chỉ tạo token trusted sau khi so sánh credential thành công |
| Gọi provider trực tiếp từ controller bỏ qua manager tùy tiện | Bỏ qua routing và cơ chế authentication chuẩn | Gọi `AuthenticationManager.authenticate` khi xây dựng auth flow |
| Handler thành công trả 200 nhưng không lưu context | `/api/me` request kế tiếp trả 401 | Cấu hình `SecurityContextRepository` cho cả save/load |
| Custom filter không chạy session strategy | Không xoay session ID/CSRF như mong đợi | Dùng hook của filter hoặc cơ chế session tương đương |
| Đăng ký filter vừa bằng `@Bean` (Servlet filter) vừa qua `HttpSecurity.addFilterAt` | Filter có thể chạy hai lần, thứ tự khác dự kiến | Chỉ đăng ký đúng trong SecurityFilterChain; nếu cần Bean thì vô hiệu servlet registration ngoài chain |
| Chỉ có failure handler, không có AuthenticationEntryPoint | Truy cập URL bảo vệ không có session trả response không như API yêu cầu | Cấu hình riêng entry point |
| Tắt CSRF cho mọi API chỉ vì dùng JSON/header | Endpoint session cookie dễ bị CSRF theo threat model | Giữ CSRF cho cookie/session, điều chỉnh theo cơ chế credential thực tế |
| Success handler lấy redirect URL từ client | Open redirect sau login | Cố định hoặc allowlist redirect target phía server |
| Ghi toàn bộ header/token khi debug | Lộ credential, secret hoặc session | Redact log và hạn chế quyền đọc trace |
| Đặt `SessionCreationPolicy.STATELESS` nhưng mong duy trì `JSESSIONID` login | Request sau mất authentication | Chọn rõ stateful hoặc stateless và test đầu cuối |
| Filter chạy trên mọi path | Request không liên quan bị đọc credential/đăng nhập nhầm | Matcher đúng HTTP method + path, test nhiều URL |
| Không kiểm tra nhiều SecurityFilterChain | Filter nằm trong chain không nhận request | Đảm bảo `securityMatcher` và thứ tự chain đúng URL |
| Tin rằng success handler tự cấp quyền | Sau login user vẫn có thể không đủ quyền | Cấu hình authorization dựa trên authorities từ server |

## 12. Checklist review và bảo mật trước production

- [ ] Mỗi request login đi qua đúng `SecurityFilterChain` và đúng filter matcher.
- [ ] Filter chỉ trích xuất credentials từ nguồn đã thiết kế, không đưa password/token vào URL hay log.
- [ ] Filter tạo `Authentication` **chưa xác thực** và gọi đúng `AuthenticationManager`.
- [ ] `ProviderManager` đăng ký đúng provider; `supports` nhất quán với class token filter tạo.
- [ ] Provider kiểm tra credential thực sự, trả authenticated principal và authorities do server quyết định.
- [ ] Success handler và failure handler trả status/body/redirect đúng sản phẩm, không lộ secret hoặc stack trace.
- [ ] `AuthenticationEntryPoint` và `AccessDeniedHandler` phân biệt trạng thái chưa login với thiếu quyền.
- [ ] Với session login: context được lưu vào repository, request tiếp theo đọc lại được; test có cookie thật.
- [ ] Session fixation, CSRF token rotation và logout/session invalidation được thiết kế nhất quán.
- [ ] Rate limiting, secret hashing/lookup, thu hồi/xoay credential, MFA (khi cần), audit và HTTPS được cấu hình.
- [ ] Có integration test cho login đúng, login sai, sai loại token, CSRF lỗi, không có session, session hết hạn, nhiều security chain.
- [ ] Không bật filter cùng lúc ở Servlet container và Spring Security chain do đăng ký trùng.
- [ ] Với stateless: token được xác minh ở **mỗi** request phù hợp, không dựa vào login response 200.

## 13. Câu hỏi tự kiểm tra

1. Vì sao chỉ triển khai `AuthenticationProvider` mà chưa có filter/manager sẽ không tự tạo endpoint đăng nhập?
2. Trong ví dụ, filter tạo token ở trạng thái nào và provider trả token ở trạng thái nào?
3. Manager dựa vào thông tin nào để chọn `DemoCodeProvider`?
4. Vì sao POST login trả 200 chưa đủ nếu yêu cầu là session-based login? Thành phần nào thực sự lưu context?
5. Sự khác nhau giữa `AuthenticationFailureHandler` và `AuthenticationEntryPoint` là gì?
6. Vì sao POST không có CSRF token có thể nhận 403 trước khi đến provider?
7. Khi chuyển sang `AuthenticationFilter`, những điều gì về session strategy và context repository phải xem lại?
8. Nếu form login đã tạo đúng `UsernamePasswordAuthenticationToken`, khi nào không cần viết filter mới?
9. Nếu người dùng có session thành công nhưng thiếu authority của một endpoint, provider hay authorization mới đưa ra quyết định cuối?
10. Bạn cần kiểm thử gì để bảo đảm một provider mới không gây ảnh hưởng tới cơ chế xác thực khác trong cùng ứng dụng?

## 14. Tài liệu chính thức

1. Spring Security 6.5 — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
2. Spring Security 6.5 API — `AuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
3. Spring Security 6.5 API — `ProviderManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
4. Spring Security 6.5 API — `AbstractAuthenticationProcessingFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
5. Spring Security 6.5 API — `AuthenticationFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html
6. Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
7. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
8. Spring Security 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
9. Spring Boot — Dependency management and starters: https://docs.spring.io/spring-boot/3.5.7/reference/using/build-systems.html

**Ghi nhớ:** custom provider chỉ là một khâu. Luồng đăng nhập đúng phải nối **request → authentication filter → manager → provider → session/context → success/failure handler**, sau đó bảo đảm authorization của những request tiếp theo vẫn được kiểm tra độc lập.