# Xử lý lỗi bảo mật trước Controller và giới hạn của ControllerAdvice

## 1. Vấn đề: Vì sao đã có RestControllerAdvice mà 401/403 vẫn không có JSON mong muốn?

Bạn đang làm API Spring Boot và viết `@RestControllerAdvice` để chuẩn hóa body lỗi. Khi controller ném `IllegalArgumentException`, response có thể là JSON thống nhất. Tuy nhiên, gọi endpoint yêu cầu đăng nhập mà không có credentials lại nhận 401 với `WWW-Authenticate`; user đã đăng nhập nhưng thiếu role nhận 403; một POST thiếu CSRF token có thể bị chặn trước khi breakpoint trong controller chạy.

Đây là tình huống bình thường trong **Tích hợp bảo mật**: Spring Security ở tầng **Servlet Filter** hoặc **WebFlux WebFilter**, trước quy trình gọi controller của Spring MVC/WebFlux. **Không phải mọi exception HTTP đều đi qua `@ControllerAdvice`.**

Cần phân biệt:
- **Authentication failure / challenge**: ai đang gọi? Credentials có hợp lệ không? Thường thuộc `AuthenticationEntryPoint`.
- **Authorization denial**: người đã xác thực có quyền làm việc này không? Thường thuộc `AccessDeniedHandler`.
- **Controller/application exception**: input không hợp lệ, resource thiếu, conflict nghiệp vụ. Thường thuộc `@ExceptionHandler`/`@RestControllerAdvice` hoặc các exception resolvers của framework.
- **Lỗi từ các tầng khác**: CSRF/CORS filter, authentication mechanism riêng, reverse proxy, TLS handshake, container, gateway. Phải xác định đúng điểm sinh response.

**Mục tiêu bài học:** giải thích chính xác ranh giới giữa Security filter và MVC Advice; hướng dẫn trả 401/403 đúng semantic và schema; có demo Java 17+ thực thi được với Spring Boot/Spring Security; trình bày các ngoại lệ như method security, CSRF, Bearer token, WebFlux và kiểm thử tự động.

> **Phiên bản thực hành:** Java 17+, Spring Boot **3.5.x**, Spring Security do Boot 3.5 quản lý và Spring MVC. Dependencies dùng `spring-boot-starter-web` và `spring-boot-starter-security`. Với Spring Boot 4.x, starter MVC có tên `spring-boot-starter-webmvc`; hãy đối chiếu API với Spring Security 7.x. Ví dụ dùng HTTP Basic và các route GET để quan sát; production bắt buộc có HTTPS và policy auth/CSRF thích hợp.

## 2. Luồng xử lý Servlet: Filter trước DispatcherServlet

Sơ đồ khái niệm:

~~~text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty)
    |
    v
Servlet Filter chain
    |
    +-- DelegatingFilterProxy
    |      |
    |      v
    |   FilterChainProxy (Spring Security)
    |      |
    |      +-- SecurityFilterChain phù hợp request
    |           +-- CORS/CSRF/authentication/... filters
    |           +-- ExceptionTranslationFilter
    |           +-- AuthorizationFilter
    |                      |
    +----------------------+-------------------------+
                                                   |
                                                   v
                                            DispatcherServlet
                                                   |
                                             HandlerMapping
                                                   |
                                           Controller / Service
                                                   |
                                           HandlerExceptionResolver
                                                   |
                                           @ExceptionHandler
                                           @ControllerAdvice
                                                   |
                                                   v
                                               HTTP response
~~~

Đây **không phải** một danh sách filter cố định: sự hiện diện và thứ tự filters phụ thuộc Spring Security version và DSL config. Điều phải nhớ là `FilterChainProxy` có thể **ngăn request trước khi DispatcherServlet được gọi**.

Một Spring MVC `@RestControllerAdvice` được `ExceptionHandlerExceptionResolver` cùng cơ chế MVC exception resolution sử dụng, khi exception xuất hiện trong quá trình dispatcher xử lý và phù hợp với một `@ExceptionHandler`. Nó không tự trở thành servlet filter bắt mọi thứ.

### Trường hợp 1: Security ngăn ở tầng Filter

~~~text
GET /api/admin
   |
   v
SecurityFilterChain
   |
   +-- User đã auth nhưng thiếu ROLE_ADMIN
   |
   +-- AccessDeniedException / access denied handling
   |
   +-- HTTP 403
   |
   X  Không gọi @GetMapping("/api/admin")
   X  Không gọi @RestControllerAdvice vì chưa có MVC exception
~~~

### Trường hợp 2: Request qua Security, lỗi trong Controller

~~~text
GET /api/orders/123  (auth thành công)
   |
   v
SecurityFilterChain cho qua
   |
   v
DispatcherServlet -> OrderController
   |
   +-- throw ResourceNotFoundException
   |
   v
HandlerExceptionResolver -> @RestControllerAdvice
   |
   v
HTTP 404 + ProblemDetail
~~~

**Không suy ra** việc một HTTP response có body JSON tức là nó đã đi qua controller. Security handlers cũng có thể tự ghi JSON ngay ở filter.

## 3. So sánh 401, 403 và các lỗi thường bị nhầm

| Tình huống | Tầng thường quyết định | Kết quả điển hình |
|---|---|---|
| Không có credentials cho route bắt buộc xác thực | Security entry point | **401 Unauthorized**, có challenge phù hợp |
| HTTP Basic password sai | Basic authentication filter/entry point | **401** |
| OAuth2 Bearer token sai/hết hạn | Bearer authentication filter/entry point | **401**, `WWW-Authenticate: Bearer ...` phù hợp |
| User đã auth nhưng thiếu role/scope | Authorization/Security AccessDeniedHandler | **403 Forbidden** |
| CSRF token thiếu/sai trên request cần protection | CsrfFilter / handler tương ứng | Thường **403**, trước controller |
| Origin/preflight không được phép | CORS layer (filter/gateway/framework) | Có thể **403** hoặc browser không đọc được response |
| JSON request invalid sau khi được Security cho qua | MVC request conversion/validation | Thường **400**, có thể tới Advice |
| Business conflict | Controller/service | `409` nếu API định nghĩa như vậy |
| Không có handler | MVC/router/security/gateway tùy config | **404** hoặc bị security chặn trước |
| Reverse proxy không liên lạc được upstream | Reverse proxy | `502/503`, Spring Advice không tham gia |

Không đồng nhất 401 với “thiếu role”: `401 Unauthorized` về bản chất là trạng thái **cần authentication** (tên lịch sử khá gây nhầm). `403 Forbidden` thường dành cho request bị cấm **dù đã có danh tính phù hợp**. Với user anonymous truy cập endpoint cần ROLE_ADMIN, cùng một authorization rule có thể dẫn tới 401 chứ không phải 403.

### 401 cần giữ HTTP authentication challenge

Ví dụ HTTP Basic:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/problem+json

{"type":"about:blank","title":"Unauthorized","status":401}
~~~

Nếu server dùng OAuth2 Bearer, `WWW-Authenticate` cần là **Bearer** theo RFC 6750, có thể kèm `realm`, `error` hoặc `scope` khi thích hợp. Đừng thay mọi entry point bằng một servlet JSON writer không hiểu authentication scheme; có thể làm API client không thể tự xử lý token/challenge đúng chuẩn.

## 4. ExceptionTranslationFilter: giới hạn rất cụ thể

Trong Spring Security Servlet, `ExceptionTranslationFilter` là một thành phần trong `FilterChainProxy` giúp chuyển `AuthenticationException` và `AccessDeniedException` từ phần downstream mà nó giám sát thành hành vi HTTP.

Pseudo-flow:

~~~text
ExceptionTranslationFilter
  |
  +-- filterChain.doFilter(request, response)
        |
        +-- downstream authentication / authorization / app
  |
  +-- catch(AuthenticationException)
        -> AuthenticationEntryPoint
  |
  +-- catch(AccessDeniedException)
        |
        +-- anonymous/chưa xác thực
        |      -> AuthenticationEntryPoint
        |
        +-- đã xác thực nhưng thiếu quyền
               -> AccessDeniedHandler
~~~

Đây là **logic minh họa**, không phải code implementation nguyên văn. `ExceptionTranslationFilter` không bắt mọi `Exception`. `IllegalArgumentException` từ nghiệp vụ thông thường sẽ được MVC resolver xử lý hoặc lan sang cơ chế lỗi chung, không được filter này mặc định map thành 401/403.

### Không phải lỗi nào cũng chạy qua ExceptionTranslationFilter

Điểm cần nắm vững:
- `BasicAuthenticationFilter` có thể tự gọi entry point của mình ngay khi credentials sai.
- `BearerTokenAuthenticationFilter` có thể có entry point/handler thuộc Resource Server.
- `CsrfFilter` có thể dùng access denied handler riêng để kết thúc request.
- Filter custom đứng **trước** `ExceptionTranslationFilter` có thể tự ghi response hoặc ném exception ngoài phạm vi filter dịch lỗi.
- Request đã bị CDN/gateway từ chối thì không chạy vào `FilterChainProxy` của ứng dụng.

Vì vậy `http.exceptionHandling(...authenticationEntryPoint(...).accessDeniedHandler(...))` là cấu hình trung tâm hữu ích, **không bảo đảm mọi lỗi authentication/CSRF từ mọi filter tự dùng nó**. Nếu cần toàn bộ 401/403 theo một schema, cần xác định từng **component sinh lỗi thực tế** rồi nối đúng error writer.

## 5. AuthenticationEntryPoint, AccessDeniedHandler và ControllerAdvice

| Thành phần | Package/stack | Khi nào phù hợp |
|---|---|---|
| `AuthenticationEntryPoint` | `org.springframework.security.web`, Servlet | Bắt đầu/challenge authentication |
| `AccessDeniedHandler` | `org.springframework.security.web.access`, Servlet | Security authorization denied |
| `ExceptionTranslationFilter` | Servlet Security | Chọn entry point hay denied handler nếu exception downstream thích hợp |
| `BasicAuthenticationFilter` | Servlet Security | Phân tích/xác thực HTTP Basic credentials |
| `CsrfFilter` | Servlet Security | Kiểm tra CSRF ở các request cần protection |
| `AuthorizationFilter` | Servlet Security | Request-level authorization |
| `@RestControllerAdvice` | Spring MVC (và annotated WebFlux có cơ chế riêng) | Lỗi ném khi controller/handler được dispatch |
| `HandlerExceptionResolver` | Spring MVC | Định tuyến exception trong MVC handling |
| `ServerAuthenticationEntryPoint` | WebFlux Security | Reactive tương đương entry point |
| `ServerAccessDeniedHandler` | WebFlux Security | Reactive tương đương denied handler |

Phân biệt hai nhiệm vụ:
- **Authentication**: danh tính/credentials có hợp lệ?
- **Authorization**: danh tính đã được xác định có được phép gọi endpoint/thao tác?

Một API có thể trả cùng **định dạng body** ở 401, 403, 400, nhưng phải giữ **status và headers đúng semantic**. Không biến tất cả thành 200 + `{"success":false}` hoặc 500 chỉ để dễ xử lý ở frontend.

## 6. Giới hạn chính xác của @ControllerAdvice

Câu “`@ControllerAdvice` không bắt security exceptions” thường dùng để nhắc ranh giới filter/controller, nhưng cần diễn đạt đúng:

**Đúng:** `@RestControllerAdvice` không tự bắt những errors mà filter đã xử lý và trả response **trước DispatcherServlet**. Ví dụ request-level AuthorizationFilter chặn `/api/admin` trước controller.

**Cũng đúng:** nếu một exception bảo mật **phát sinh trong controller/service** sau khi DispatcherServlet đã dispatch (ví dụ method security `@PreAuthorize` từ service), nó có thể đi qua MVC `HandlerExceptionResolver`. Khi đó một `@ExceptionHandler(AccessDeniedException.class)` có thể bắt được **nếu exception được MVC resolver xử lý**.

**Không thể suy ra:** mọi `AccessDeniedException` đều thuộc Advice hoặc đều thuộc ExceptionTranslationFilter. Vị trí phát sinh exception, nơi nó bị catch và trạng thái response đã commit quyết định cái gì có cơ hội xử lý.

Ví dụ fragment:

~~~java
@RestControllerAdvice
class ApiAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> badInput(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid input");
    }
}
~~~

Đoạn trên dành cho lỗi controller/business. Nó không phải class runnable độc lập; cần imports, Spring MVC app và controller ném lỗi.

### Vì sao không nên “bắt mọi Exception” bằng Advice?

Phản ví dụ:

~~~java
// Phản ví dụ, KHÔNG sao chép vào production:
@ExceptionHandler(Exception.class)
ResponseEntity<String> everything(Exception ex) {
    return ResponseEntity.status(500).body(ex.getMessage());
}
~~~

Tác hại:
1. Một số lỗi có trạng thái hợp lệ 400/404/409 có thể bị chuyển thành 500.
2. Raw exception message có thể lộ token, tên bảng, SQL, path hoặc cấu trúc nội bộ.
3. Nếu method-security `AccessDeniedException` đến Advice, broad handler có thể can thiệp vào status và semantics của Security.
4. Filter errors vẫn không được bao phủ, vì filter đã hoàn tất response trước MVC.

Trong dự án thật, phân nhóm exception theo ownership: MVC validation/business vs authentication/authorization vs network/proxy/container.

## 7. Ví dụ runnable Java 17: cùng API trả 401, 403 và 400 đúng tầng

Tạo dự án bằng **Spring Initializr**: Java 17+, Gradle, **Spring Boot 3.5.x**, dependencies **Spring Web** và **Spring Security**, không cần Redis/JWT. Với project đã cấu hình Boot Gradle plugin/dependency management, Gradle fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đây là **dependency fragment**, không phải toàn bộ build script. Dự án từ Initializr đã có Gradle wrapper. Tạo file Java duy nhất `src/main/java/demo/security/SecurityBoundaryApplication.java`:

~~~java
package demo.security;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class SecurityBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityBoundaryApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    AuthenticationEntryPoint jsonAuthenticationEntryPoint() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType("application/problem+json");
            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""
            );
            response.getWriter().write(
                "{\"type\":\"about:blank\","
                + "\"title\":\"Unauthorized\",\"status\":401}"
            );
        };
    }

    @Bean
    AccessDeniedHandler jsonAccessDeniedHandler() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType("application/problem+json");
            response.getWriter().write(
                "{\"type\":\"about:blank\","
                + "\"title\":\"Forbidden\",\"status\":403}"
            );
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint entryPoint,
            AccessDeniedHandler deniedHandler) throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .requestMatchers("/api/admin").hasRole("ADMIN")
            .requestMatchers("/api/me", "/api/fail").authenticated()
            .anyRequest().denyAll()
        );

        // Explicit entry point: gồm cả Basic credentials không hợp lệ.
        http.httpBasic(basic -> basic.authenticationEntryPoint(entryPoint));

        // Nhánh authorization/challenge do ExceptionTranslationFilter.
        http.exceptionHandling(ex -> ex
            .authenticationEntryPoint(entryPoint)
            .accessDeniedHandler(deniedHandler)
        );

        http.sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

        http.formLogin(form -> form.disable());

        // Giữ CSRF mặc định: demo chỉ dùng GET.
        return http.build();
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("area", "admin");
    }

    @GetMapping("/api/fail")
    Map<String, String> fail() {
        throw new IllegalArgumentException("sensitive internal detail");
    }
}

@RestControllerAdvice
class ApiControllerAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> badInput(IllegalArgumentException ex) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, "Request is not valid"
        );
        pd.setTitle("Invalid request");
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(pd);
    }
}
~~~

Đây là **một source file Java hoàn chỉnh** trong project có đúng dependencies. Java cho phép nhiều top-level classes khi chỉ một class `public` có tên trùng file; các class `@Configuration`, `@RestController`, `@RestControllerAdvice` không public vẫn được component scanning tìm thấy trong cùng package.

### Những lựa chọn có chủ đích trong code

- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` dùng password hashing phù hợp cho demo, không dùng `{noop}`.
- Hai username/password mẫu **được ghi trong source chỉ cho local test**, không đưa vào production. Production nên kết nối identity provider/user store và secrets management.
- `AuthenticationEntryPoint` trả **401** kèm `WWW-Authenticate: Basic realm="demo-api"` vì đây là HTTP Basic.
- `AccessDeniedHandler` trả **403** mà không lộ role policy cụ thể.
- `@RestControllerAdvice` chỉ bắt `IllegalArgumentException` từ controller và dùng `ProblemDetail` cho 400.
- `SessionCreationPolicy.STATELESS` không dùng `HttpSession` để lưu SecurityContext của demo. Điều này **không tự vô hiệu hóa CSRF nguy cơ** với một browser dùng credentials tự động.
- `formLogin(form -> form.disable())` tránh chuyển API thành flow redirect tới trang login.
- `anyRequest().denyAll()` tránh những URL ngoài danh sách được phép đi qua Security mà không có policy.
- Vì demo dùng các endpoint GET, chúng ta **không tắt CSRF toàn cục** chỉ để đơn giản hóa việc test.

### Chạy project

Nếu muốn cố định cổng, tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

Từ thư mục root dự án:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi ứng dụng đã khởi động, dùng terminal khác gửi request. Các lệnh HTTP Basic qua `http://localhost` ở đây **chỉ phục vụ môi trường học local**; production phải dùng HTTPS vì Basic header có thể giải mã dễ dàng nếu bị lộ trên đường truyền.

## 8. Kiểm chứng HTTP status, header và body

### 8.1. Public endpoint — Controller trả 200

~~~bash
curl -sS -i http://localhost:8080/api/public
~~~

Status `200 OK`, body JSON:

~~~json
{"message":"public"}
~~~

### 8.2. Không credentials — Security trả 401

~~~bash
curl -sS -i http://localhost:8080/api/me
~~~

Status `401 Unauthorized`, header quan trọng:

~~~http
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/problem+json
~~~

Body JSON **chính xác do entry point của ví dụ viết**:

~~~json
{"type":"about:blank","title":"Unauthorized","status":401}
~~~

Controller `DemoController.me()` không chạy, do filter đã chặn.

### 8.3. HTTP Basic credentials sai — vẫn 401

~~~bash
curl -sS -i -u alice:wrong-password \
  http://localhost:8080/api/me
~~~

Status 401 và body JSON `Unauthorized` tương tự. Trong cấu hình này, cả Basic authentication failure cũng dùng entry point JSON nhờ:

~~~java
http.httpBasic(basic -> basic.authenticationEntryPoint(entryPoint));
~~~

Nếu **chỉ** cấu hình `exceptionHandling.authenticationEntryPoint` rồi quên authentication mechanism entry point, body cho Basic password sai có thể khác body cho request không có credentials, tùy Security config thực tế.

### 8.4. User đã đăng nhập nhưng thiếu quyền — 403

~~~bash
curl -sS -i -u alice:alice-pass \
  http://localhost:8080/api/admin
~~~

`alice` có `ROLE_USER`, không có `ROLE_ADMIN`. Status `403 Forbidden`. Body từ `AccessDeniedHandler`:

~~~json
{"type":"about:blank","title":"Forbidden","status":403}
~~~

Controller `admin()` **không chạy**. Advice không có cơ hội xử lý vì lỗi nằm ở request authorization filter.

### 8.5. Admin đủ quyền — 200

~~~bash
curl -sS -i -u admin:admin-pass \
  http://localhost:8080/api/admin
~~~

Status `200 OK`, body:

~~~json
{"area":"admin"}
~~~

### 8.6. Lỗi trong Controller — Advice trả 400

~~~bash
curl -sS -i -u alice:alice-pass \
  http://localhost:8080/api/fail
~~~

Sau khi Security xác thực thành công, method `fail()` ném `IllegalArgumentException`. `@RestControllerAdvice` bắt lỗi và trả `400 Bad Request` với `ProblemDetail`:

~~~json
{
  "type": "about:blank",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request is not valid"
}
~~~

Spring có thể thêm trường `instance`, và thứ tự field JSON phụ thuộc converter; không so sánh nguyên văn byte response mà chỉ assert các fields liên quan. **Nội dung exception gốc “sensitive internal detail” không được lộ cho client**.

### 8.7. Tổng hợp luồng

| Request | Ai quyết định? | HTTP status | Có tới Controller? |
|---|---|---|---|
| `GET /api/public` | Security permitAll → controller | 200 | Có |
| `GET /api/me` không credentials | Entry point | 401 | Không |
| `GET /api/me` sai mật khẩu | BasicAuthenticationFilter/entry point | 401 | Không |
| `GET /api/admin` với alice | AuthorizationFilter/AccessDeniedHandler | 403 | Không |
| `GET /api/admin` với admin | Controller | 200 | Có |
| `GET /api/fail` với alice | Controller throw → Advice | 400 | Có |

Từ bảng này thấy rằng status và JSON giống định dạng không có nghĩa cùng một tầng chịu trách nhiệm.

## 9. Điểm dễ nhầm: cùng một loại exception nhưng khác nơi phát sinh

Giả sử một service method được bảo vệ bằng Spring method security:

~~~java
// Fragment minh họa: có @EnableMethodSecurity, class @Service
// và reportRepository phù hợp trong project thật.
@PreAuthorize("hasRole('ADMIN')")
public Report loadReport() {
    return reportRepository.load();
}
~~~

`Report` và `reportRepository` ở đây chỉ là thành phần nghiệp vụ minh họa, **không phải một chương trình độc lập**.

Nếu controller đã được gọi và service proxy ném `AccessDeniedException` do `@PreAuthorize`, exception có thể đi qua Spring MVC handler exception resolution. Nếu project có `@ExceptionHandler(AccessDeniedException.class)`, nó **có thể** được gọi và tạo response; nếu không bị MVC resolve, exception có thể lan tới `ExceptionTranslationFilter` ở phía ngoài.

**Kết luận chính xác:** không tuyên bố “Advice tuyệt đối không bao giờ bắt `AccessDeniedException`”. Nhưng cũng không dựa vào Advice như **nguồn chính** của error semantics khi có request-level Security filters. Cần test cả request-level authorization và method-level authorization, tránh viết advice catch-all gây ra các kết quả khác nhau.

## 10. CSRF: 403 trước Controller không nhất thiết dùng handler authorization chung

Trong ứng dụng dùng session cookie hoặc browser credentials, Spring Security mặc định có CSRF protection cho nhiều HTTP methods thay đổi trạng thái như POST/PUT/PATCH/DELETE. Nếu request cần CSRF token nhưng thiếu hoặc sai, `CsrfFilter` có thể trả `403` trước controller.

~~~http
POST /api/orders HTTP/1.1
Cookie: JSESSIONID=...
Content-Type: application/json

{"sku":"A"}
~~~

**Đừng tắt CSRF vô điều kiện** chỉ để làm status/body dễ xử lý:

~~~java
// PHẢN VÍ DỤ: KHÔNG dùng để "sửa mọi lỗi CSRF" production.
http.csrf(csrf -> csrf.disable());
~~~

Nếu API chỉ dùng token được JavaScript/client tự đính kèm và không dựa vào tự động gửi browser credentials, CSRF threat model có thể khác. Tuy nhiên cần đánh giá thực tế, không suy từ việc “API trả JSON” rằng có thể bỏ CSRF. Với session cookie, thường cần CSRF token hoặc cơ chế tương đương được phê duyệt.

### CSRF có thể có AccessDeniedHandler riêng

Các Security filters không nhất thiết đều phát denial qua `ExceptionTranslationFilter`. `CsrfFilter` có thể trực tiếp dùng handler denial riêng. Vì vậy chỉ cấu hình:

~~~java
http.exceptionHandling(ex -> ex.accessDeniedHandler(myHandler));
~~~

không chứng minh mọi lỗi CSRF sẽ có body do `myHandler` viết. Nếu sản phẩm yêu cầu schema thống nhất, xem cấu hình CSRF và exceptionHandling của **đúng phiên bản** Security, xác định handler thực sự phát response, sau đó test POST thiếu token và POST có token. Không thay security policy chỉ để thống nhất JSON.

## 11. CORS và các request bị chặn trước DispatcherServlet

Khi browser muốn gửi cross-origin POST JSON, nó có thể gửi preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,authorization
~~~

Preflight không phải request có cùng credentials như actual request; nếu Security cố auth preflight trước khi CORS handler chạy, nó có thể trả 401/403. Browser không gửi actual POST, đôi khi console chỉ hiện “CORS error”.

Với Servlet Spring Security, có thể tích hợp:

~~~java
// Fragment trong SecurityFilterChain Servlet đã có CORS policy.
http.cors(org.springframework.security.config.Customizer.withDefaults());
~~~

CORS config có thể được cung cấp bằng `WebMvcConfigurer.addCorsMappings` hoặc `CorsConfigurationSource` theo kiến trúc. Đừng giải quyết bằng `permitAll("/**")` hoặc `allowedOrigins("*")` cùng credentials. Với Spring WebFlux, có `ServerHttpSecurity.cors(...)` và `CorsWebFilter`.

**Một điều dễ gây nhầm:** response 401 của gateway/Filter có thể thiếu `Access-Control-Allow-Origin`, khiến browser JavaScript **không đọc được 401 body/status**, trong khi `curl -i` vẫn cho thấy 401. Khi debug phải so sánh headers của actual response qua proxy, không chỉ nhìn console.

## 12. OAuth2 Resource Server/Bearer JWT: giữ đúng challenge

Ví dụ chính dùng HTTP Basic vì dễ thực hành, nhưng ứng dụng production có thể dùng JWT Bearer token.

Khi không có token hoặc Bearer token không hợp lệ:
- Spring Security Resource Server có logic riêng cho `BearerTokenAuthenticationFilter` và `BearerTokenAuthenticationEntryPoint`.
- Header `WWW-Authenticate: Bearer ...` có thể chứa `error="invalid_token"`, `realm` hoặc thông tin khác khi RFC 6750 cho phép.
- Khi đã có token hợp lệ nhưng thiếu OAuth2 scope, handler phù hợp có thể là `BearerTokenAccessDeniedHandler` và dùng mã `insufficient_scope` trong challenge theo chuẩn.

Không dùng `AuthenticationEntryPoint` của demo Basic để xử lý mọi Bearer response; việc ghi `WWW-Authenticate: Basic` lên endpoint Bearer là **sai security scheme**. Khi muốn JSON body đồng nhất:
1. Xác định authentication mechanism thực sự và handlers của nó.
2. Giữ status/challenge headers theo OAuth2/RFC 6750.
3. Viết JSON/ProblemDetail theo một shared schema mà **không phá protocol semantics**.
4. Test token thiếu, sai, hết hạn, chữ ký không hợp lệ và thiếu scope.

Với form-login browser truyền thống, entry point có thể redirect `302` đến trang đăng nhập, không bắt buộc trả JSON 401. API và UI có trải nghiệm khác nhau có thể cần **hai security chains hoặc entry point matching riêng**.

## 13. Khi cần cùng một JSON error contract

Một thiết kế tốt:

~~~text
                      Shared error contract
                  (status, type, code, detail)
                             |
           +-----------------+--------------------+
           |                                      |
   Spring Security handlers               MVC RestControllerAdvice
   AuthenticationEntryPoint               HandlerExceptionResolver
   AccessDeniedHandler                    @ExceptionHandler
           |                                      |
           +-----------------+--------------------+
                             |
                             v
                          HTTP response
~~~

Có thể tạo một `ErrorResponseFactory` hoặc serializer chung để chia sẻ JSON structure. Nhưng quyền quyết định:
- 401, `WWW-Authenticate`, redirect login: thuộc authentication scheme.
- 403: thuộc security policy/denial handler.
- 400, 404, 409 domain errors: thuộc MVC/business mapping.
- Response error từ gateway: thuộc gateway.

**RFC 9457 Problem Details** là lựa chọn tốt cho JSON API. Những field thường gặp:
- `type`: URI định danh loại lỗi hoặc `about:blank`.
- `title`: tên ngắn của loại lỗi.
- `status`: HTTP status.
- `detail`: mô tả không làm lộ dữ liệu nhạy cảm.
- `instance`: định danh một lần xảy ra, khi phù hợp.
- Extensions như `code`, `traceId` theo hợp đồng cụ thể.

Lưu ý: cùng JSON structure **không có nghĩa cùng HTTP status**. Không trả `200 OK` kèm `{"status":401}` khi authentication thất bại. Bảo đảm HTTP status, caching directives, challenge headers và CORS policy vẫn đúng.

## 14. Khi nào ResponseEntityExceptionHandler hoặc /error tham gia?

Spring MVC có `ResponseEntityExceptionHandler` giúp tùy biến các MVC exceptions phổ biến (ví dụ body validation, phương thức/loại media không phù hợp). Spring Boot cũng có error dispatch qua `/error` và `BasicErrorController` cho một số lỗi không được resolver xử lý.

Chúng là **những đường xử lý khác nhau**:
- `@RestControllerAdvice`: MVC error resolution khi handler processing phù hợp.
- `ResponseEntityExceptionHandler`: base class cho việc chuẩn hóa một số lỗi MVC.
- `BasicErrorController` / `ErrorAttributes`: lỗi qua Boot error dispatch/container trong một số tình huống.
- `AuthenticationEntryPoint` / `AccessDeniedHandler`: lỗi bảo mật ở filter.
- Proxy/CDN: có thể tự sinh 401/403/429/502 trước backend.

Không dựa vào `/error` để bắt chắc chắn mọi filter exception. Một filter có thể `sendError` hoặc ghi trực tiếp body; container có thể thực hiện error dispatch hay không tùy cách xử lý và response đã commit. Nếu response đã được gửi, không thể tùy tiện đổi status/headers và viết một body khác.

## 15. WebFlux: cùng ý tưởng nhưng API khác

Spring WebFlux dùng reactive security components:

| Servlet/MVC | Reactive/WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `FilterChainProxy` | `WebFilterChainProxy` |
| `ExceptionTranslationFilter` | `ExceptionTranslationWebFilter` |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| `HttpServletResponse` | `ServerHttpResponse` |
| `DispatcherServlet` | `DispatcherHandler` |

`@RestControllerAdvice` cũng có thể dùng cho **WebFlux annotated controllers**, nhưng nó vẫn không tự bắt mọi lỗi trong `WebFilter`. Thao tác ghi response trong reactive code phải trả publisher phù hợp, tránh blocking event-loop.

### Fragment minh họa WebFlux

Đây là fragment đặt trong `@Configuration` của một **dự án WebFlux riêng**, với Spring Security reactive dependencies; nó không ghép vào project Servlet ở trên:

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/public").permitAll()
            .pathMatchers("/api/admin").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .httpBasic(org.springframework.security.config.Customizer.withDefaults())
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(
                new HttpBasicServerAuthenticationEntryPoint())
            .accessDeniedHandler(
                new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN))
        )
        .build();
}
~~~

Các imports quan trọng: `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint`, `org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler`, `org.springframework.http.HttpStatus` và `org.springframework.context.annotation.Bean`.

Đoạn đó chỉ minh họa **nhánh status/challenge** trong WebFlux, **chưa tự xây JSON body**. Nếu muốn lỗi JSON ở reactive layer, dùng `ServerAuthenticationEntryPoint` hoặc `ServerAccessDeniedHandler` ghi qua `ServerWebExchange.getResponse()` và reactive `Mono<Void>`, không gọi `block()`. Với HTTP Basic invalid credentials, kiểm tra cả entry point của cấu hình `httpBasic`, không giả định mọi lỗi đều đi qua `ExceptionTranslationWebFilter`.

## 16. Có nhiều SecurityFilterChain: lỗi rơi vào chain nào?

Một Spring Boot app có thể có hai nhóm endpoint:
- `/api/**` dùng Basic/Bearer và JSON errors.
- `/ui/**` dùng form login, redirect và session.
- Cổng management/Actuator có chain hoặc management context riêng.

Spring Security chọn chain theo matchers và thứ tự, thông thường **chain đầu tiên khớp request** là chain áp dụng. Mỗi chain có authentication mechanisms và error handlers riêng. Cấu hình entry point cho `/api/**` không tự động áp dụng cho `/ui/**`.

Ví dụ **fragment**, không phải toàn bộ cấu hình production:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    // Cấu hình authentication/authorization phù hợp cho API.
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain ui(HttpSecurity http) throws Exception {
    http.securityMatcher("/ui/**");
    // Cấu hình login phù hợp UI.
    return http.build();
}
~~~

**Cảnh báo:** nếu chỉ có hai chain trên, request **không khớp chain nào** có thể không được Spring Security bảo vệ. Phải thiết kế fallback chain rõ ràng. Không copy fragment thiếu authentication/authorization vào production.

Khi API trả HTML login thay vì 401 JSON, đừng vội đổ lỗi cho Advice; có thể request đã match chain form-login hoặc bị proxy route sang service khác.

## 17. Kiểm thử tự động: không bỏ Spring Security filters khỏi MockMvc

Một lỗi kiểm thử phổ biến là chỉ test controller bằng `MockMvcBuilders.standaloneSetup(controller)`. Nếu không thêm Security filter chain, test có thể trả 200 dù production trả 401/403. Muốn kiểm tra pre-controller security, dùng Spring Boot integration test hoặc gắn security config đúng cách.

Trong project Boot 3.5, khai báo test dependencies (fragment Gradle):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tạo file `src/test/java/demo/security/SecurityBoundaryApplicationTests.java`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousGets401WithBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void wrongBasicPasswordGets401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void authenticatedWithoutRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.status").value(403));
    }

    @Test
    void administratorCanAccessEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.area").value("admin"));
    }

    @Test
    void controllerExceptionGoesToAdvice() throws Exception {
        mvc.perform(get("/api/fail")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.title").value("Invalid request"));
    }
}
~~~

Đây là test class đầy đủ với imports ở **đầu từng dòng** và annotation đúng project Spring Boot MVC. Các lệnh:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Khi môi trường và dependencies đã đúng, Gradle báo `BUILD SUCCESSFUL` nếu cả 5 tests pass. Output console cụ thể có thể khác giữa Gradle versions. Test ở đây xác minh 401 không credentials, 401 Basic sai, 403 thiếu role, 200 đủ role, 400 qua Advice.

### Cần test thêm ở môi trường thật

| Trường hợp | Kỳ vọng |
|---|---|
| POST thiếu CSRF khi dùng cookie | Denied đúng security policy, thường 403 |
| Preflight OPTIONS có Origin hợp lệ | CORS trước auth, không bị 401 do thiếu cookie |
| Bearer token thiếu/sai | 401 và `WWW-Authenticate: Bearer` phù hợp |
| Bearer token hợp lệ thiếu scope | 403/challenge theo resource server |
| Method security deny trong service | Response theo policy, không bị catch-all biến thành 500 |
| API và UI security chains | Entry point/schema đúng route |
| 401 do proxy thay vì backend | Phân biệt response origin và edge |
| Error sau khi response commit | Không ghi hai response bodies |
| Missing API route | Không vô ý leak route hoặc biến 404 thành 200 |
| Backend 403 đi qua CDN | Headers/body nguyên vẹn theo chính sách caching |

## 18. Debug lỗi bảo mật theo đúng tầng

Trong môi trường local/test, có thể bật:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Spring Security có log giúp xác định chain/filter xử lý request. Với nhiều filters custom, có thể cần mức log cụ thể; **không bật debug/trace nhạy cảm trên production lâu dài**. Tránh ghi `Authorization`, cookie, session ID, credentials hoặc token vào logs.

Quy trình debug:

1. **Nhìn HTTP status:** 401, 403, 400, 404 hay 500? Có redirect 302 không?
2. **Nhìn headers:** 401 có `WWW-Authenticate` đúng scheme? Response có `Content-Type` và CORS headers phù hợp không?
3. **Kiểm tra đường đi:** request đã tới application hay bị gateway/CDN chặn?
4. **Xác định SecurityFilterChain:** matcher và thứ tự có chọn đúng API/UI chain không?
5. **Xác định filter:** Basic/JWT/CSRF/Authorization/CORS/custom.
6. **Breakpoint có kiểm soát:** controller có chạy không? Advice có chạy không? Security handler nào ghi response?
7. **Xem exception:** AuthenticationException, AccessDeniedException hay business exception? Có bị resolver khác xử lý trước không?
8. **Xem response commit:** đã gửi headers/body chưa, có error dispatch `/error` không?
9. **Thử với MockMvc/WebTestClient và HTTP client thật** qua proxy, không chỉ test controller riêng.
10. **Sửa đúng tầng** rồi kiểm tra Security/CSRF không bị hạ cấp.

Những thông số hữu ích: tỷ lệ 401/403 theo route template, nguyên nhân tổng hợp (không đưa user/token vào metric label), độ trễ authentication provider/identity provider, CORS preflight rejects, CSRF denials và lỗi gateway. Một đợt 401 tăng sau deploy có thể do rotate keys, token issuer/audience hoặc cookie policy, không nhất thiết do Advice.

## 19. Bảng lỗi thường gặp

| Triệu chứng | Vì sao? | Cách xử lý |
|---|---|---|
| 401 có HTML, không có JSON từ Advice | Entry point hoặc form login xử lý trước Controller | Chọn entry point/API chain đúng scheme |
| 403 không qua `@ExceptionHandler` | AuthorizationFilter chặn request | Cấu hình AccessDeniedHandler |
| Basic password sai trả body khác “chưa login” | Basic filter có entry point riêng | Cấu hình `httpBasic(...authenticationEntryPoint(...))` và test |
| Bearer token sai nhận challenge Basic | Dùng nhầm Basic handler cho Resource Server | Dùng BearerTokenAuthenticationEntryPoint phù hợp RFC 6750 |
| 401 JSON không có `WWW-Authenticate` | Custom writer bỏ header challenge | Giữ challenge đúng scheme |
| POST có session cookie nhưng 403 | CSRF filter hoặc policy có hiệu lực | Xem CSRF token, không tắt để né lỗi |
| Handler denial custom không thấy ở CSRF 403 | CsrfFilter xử lý deny riêng | Xác định handler CSRF của Security version |
| Browser báo CORS thay vì 401 | Preflight bị auth hoặc 401 thiếu CORS response headers | Cấu hình CORS trước Security, kiểm tra gateway |
| Controller lỗi 400 nhưng API trả 500 | Broad Advice hoặc mapper sai status | Bắt đúng exception/ProblemDetail |
| Advice thấy AccessDeniedException do method security | Exception phát sinh trong MVC handler processing | Kiểm tra MVC resolver và Security propagation |
| API redirect 302 login | Form-login entry point được chọn | Đặt đúng authentication scheme và chain |
| Service local chạy, qua gateway trả 403 | Gateway IAM/WAF/route rules | Xem edge logs, đừng chỉ sửa Spring code |
| Một nhóm path không được bảo vệ | Thiếu fallback security chain/matcher | Thêm rule/chain phù hợp, test routes |
| Test controller pass nhưng production fail 403 | Standalone MockMvc không có filters | Integration test có Spring Security |
| Response body lỗi bị ghi hai lần | Attempt write sau khi committed | Sửa handler/error dispatch, tránh duplicate writers |
| Log lộ JWT/Basic Authorization | Logging request headers nhạy cảm | Redact và hạn chế DEBUG |

## 20. Checklist thiết kế API bảo mật

- [ ] Có sơ đồ **FilterChainProxy → DispatcherServlet → ControllerAdvice** cho Spring MVC.
- [ ] 401/403 được xử lý ở Security components đúng loại credentials.
- [ ] HTTP Basic/Bearer giữ `WWW-Authenticate` khi cần.
- [ ] AuthenticationEntryPoint có thể xử lý cả missing và invalid credentials của mechanism được dùng.
- [ ] AccessDeniedHandler trả 403 cho authenticated-but-forbidden.
- [ ] Không dùng Advice catch-all để nuốt AccessDeniedException không có chủ đích.
- [ ] CSRF protection được đánh giá theo browser credentials/session.
- [ ] CORS preflight và error responses được xử lý đúng trước auth khi cần.
- [ ] Multiple SecurityFilterChain có matcher/order/fallback rõ.
- [ ] Dùng `ProblemDetail`/JSON contract nhất quán mà không thay semantics HTTP.
- [ ] Không lộ exception raw message, role policy, token, session IDs, stack trace.
- [ ] Với WebFlux dùng `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`.
- [ ] Có integration tests giữ Security filter chain, không chỉ controller unit test.
- [ ] Test response qua gateway/CDN và trên các paths lỗi 401/403/400/500.
- [ ] Không tắt Security/CSRF hoặc mở rộng permitAll để làm “đẹp” response.

## 21. Câu hỏi ôn tập

**1.** Vì sao một `@RestControllerAdvice` xử lý `IllegalArgumentException` không thấy lỗi 401 khi gọi API chưa đăng nhập?

**Đáp án:** Spring Security filter có thể chặn trước DispatcherServlet; không có MVC exception nào được đưa tới Advice.

**2.** Nếu một user đã đăng nhập nhưng không có `ROLE_ADMIN`, handler chính cho denied ở request level là gì?

**Đáp án:** Thường `AccessDeniedHandler`, với 403. Với anonymous request trên cùng endpoint có thể chọn `AuthenticationEntryPoint`/401.

**3.** Đã cấu hình `exceptionHandling.authenticationEntryPoint`, vì sao nhập sai Basic password vẫn trả body khác?

**Đáp án:** BasicAuthenticationFilter có thể dùng entry point riêng. Phải kiểm tra và cấu hình cả `httpBasic(...authenticationEntryPoint(...))` như ví dụ.

**4.** `@ControllerAdvice` có **bao giờ** bắt được `AccessDeniedException` không?

**Đáp án:** Có thể khi exception phát sinh trong controller/service sau dispatch và MVC exception resolver xử lý nó. Không suy ra Advice bắt được error đã xử lý tại filter trước Controller.

**5.** Tắt `csrf()` để JSON lỗi giống Advice có đúng không?

**Đáp án:** Không. CSRF là cơ chế bảo vệ; cần threat model và token/policy phù hợp, không hạ bảo mật chỉ để đồng nhất body.

**6.** Khi OAuth2 Bearer token không hợp lệ, có nên trả `WWW-Authenticate: Basic` vì đã có handler JSON Basic ở hệ thống khác không?

**Đáp án:** Không. Dùng Bearer challenge/handler đúng theo RFC 6750.

**7.** HTTP POST từ browser bị báo “CORS error” nhưng curl thấy 401. Điều đó có thể xảy ra không?

**Đáp án:** Có. Preflight có thể bị Security 401 hoặc actual 401 thiếu headers CORS, khiến browser không cho frontend đọc response.

**8.** Nên test `@RestControllerAdvice` và Security error bằng cùng một standalone MockMvc không có filter không?

**Đáp án:** Không đủ. Cần integration setup với Spring Security filter chain cho 401/403.

**9.** Nếu API đang có nhiều SecurityFilterChain, entry point chung có tự áp cho mọi chain không?

**Đáp án:** Không. Chain được chọn theo matcher/order và cấu hình có thể khác nhau; cần thiết kế và test từng namespace.

**10.** Có thể trả `{"status":401}` với HTTP status 200 để frontend dễ code không?

**Đáp án:** Không nên. HTTP status phải đúng; response body là bổ sung. Giữ 401/403 thật và challenge headers khi cần.

### Bài tập mở rộng

Từ ví dụ mục 7, thêm route `GET /api/report` yêu cầu `ROLE_ADMIN`, test `alice` nhận 403 và `admin` nhận 200. Sau đó tạo một POST có CSRF protection và test trường hợp thiếu token, rồi kiểm tra handler nào trả 403. Tiếp theo thử một exception từ service có `@PreAuthorize` để xem nó được MVC resolver hay Security xử lý trong cấu hình cụ thể. Cuối cùng kiểm tra response từ reverse proxy/gateway trước backend và nêu vì sao Advice không nhận được.

## 22. Tài liệu chuẩn để tra cứu

- [Spring Security — Servlet Architecture, Security Filter Chain, ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — In-Memory UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html)
- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Framework — MVC @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework — RFC 9457 ProblemDetail trong MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9110 — HTTP Semantics: 401/403 và authentication](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)

**Ghi nhớ:** Security filters có thể xử lý lỗi **trước Controller**, còn `@RestControllerAdvice` là cơ chế exception resolution **trong MVC/WebFlux handler processing**. Muốn thống nhất JSON error, hãy dùng **AuthenticationEntryPoint/AccessDeniedHandler** hoặc handler của cơ chế Security tương ứng cho 401/403, và Advice cho lỗi controller. Giữ nguyên semantic HTTP, tránh hạ bảo mật và luôn xác thực bằng test có filter chain thật.
