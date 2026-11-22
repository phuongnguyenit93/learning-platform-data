# Kiểm thử filter, interceptor, CORS và ranh giới Spring Security

> **Ngữ cảnh:** Spring Boot – web-runtime → **Kiểm thử web runtime**. Bài này giúp kiểm thử đúng ranh giới giữa **Servlet Filter**, **Spring MVC HandlerInterceptor**, **CORS** và **Spring Security FilterChainProxy**, tránh test đạt xanh chỉ vì vô tình tắt security filters. Ví dụ dùng **Java 17+, Spring Boot 3.3.x (Maven parent 3.3.13), Spring Framework 6.1.x, Spring Security 6.3.x**. Có Maven POM, file ứng dụng hoàn chỉnh, bộ MockMvc test, smoke test real HTTP, curl và ma trận lỗi. Trọng tâm là Spring MVC/Servlet; WebFlux được so sánh riêng để không nhầm API.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả request flow từ Tomcat → Servlet filters → Spring Security → DispatcherServlet → HandlerMapping → HandlerInterceptor → controller.
2. Phân biệt Filter ở **Servlet layer** và Interceptor ở **MVC handler layer**: Security có thể trả 401/403 trước khi interceptor chạy.
3. Chọn `OncePerRequestFilter`, `@Order` hoặc `FilterRegistrationBean` đúng nhu cầu và tránh đăng ký hai lần.
4. Test `HandlerInterceptor.preHandle`, `postHandle` và `afterCompletion` trong lifecycle phù hợp, biết khi nào không có matched handler.
5. Phân biệt browser **CORS preflight OPTIONS** và actual cross-origin GET/POST; dùng Origin và Access-Control-Request-* headers chính xác.
6. Bảo đảm CORS được giải quyết **trước authentication** trong Security chain, vì preflight thường không chứa cookies/session.
7. Phân biệt 401 (chưa xác thực), 403 (không đủ quyền, CSRF sai hoặc CORS bị chặn) và 200 (được phép); không coi cùng status là cùng nguyên nhân.
8. Kiểm CORS allowlist origin/method/headers, `Access-Control-Allow-Credentials`, cache và xử lý error responses.
9. Tách **CORS** khỏi authentication, authorization và **CSRF**; preflight thành công không miễn CSRF cho actual POST.
10. Chạy `@SpringBootTest + @AutoConfigureMockMvc` có đầy đủ filters và `spring-security-test` với `user()`, `httpBasic()`, `csrf()`.
11. Biết giới hạn của `@WebMvcTest` slice và `MockMvcBuilders.standaloneSetup`; không dùng `addFilters=false` để chứng minh hệ thống được bảo vệ.
12. Bổ sung `RANDOM_PORT` HTTP smoke test và browser/proxy test vì MockMvc không tạo network socket thật.
13. Phát hiện sai thứ tự SecurityFilterChain/route matchers, filter double registration, async/error dispatch và forwarded-header mismatches.
14. Lập regression matrix cho happy path, negative security tests, CORS preflight, actual request, lỗi và runtime.

## 2. Đường đi của request trong Spring MVC

~~~text
HTTP client / Browser
         |
         v
Servlet container: Tomcat
         |
         v
Servlet Filter chain
  +-- custom request marker / tracing Filter (nếu đăng ký sớm)
  +-- DelegatingFilterProxy("springSecurityFilterChain")
  |      |
  |      v
  |   FilterChainProxy
  |      |
  |      +-- CorsFilter (khi .cors(...) được cấu hình)
  |      +-- security context / authentication
  |      +-- CSRF / authorization / exception translation
  |      |
  |      +-- có thể chặn bằng 401/403 tại đây
  +-- other Servlet filters
         |
         v
DispatcherServlet
         |
         v
HandlerMapping + MVC CORS checks (khi liên quan)
         |
         v
HandlerInterceptor.preHandle(...)
         |
         v
HandlerAdapter -> Controller
         |
         v
postHandle / exception resolver / afterCompletion
         |
         v
Response đi ngược qua các Filters
~~~

Đây là **mô hình điển hình**, không phải thứ tự tuyệt đối của mọi app. Filter order do registration quyết định; một filter có thể chặn trước Security; `CorsFilter` có thể hoàn tất preflight mà không vào DispatcherServlet. Với async/error dispatch có nhiều pha. Khi nhiều `SecurityFilterChain` tồn tại, Spring Security chọn **chain đầu tiên khớp matcher**.

### Bảng phân biệt trách nhiệm

| Thành phần | API | Thời điểm | Phù hợp | Không nên dùng làm |
|---|---|---|---|---|
| Servlet Filter | `Filter`, `OncePerRequestFilter` | Trước MVC handler resolution | Trace/correlation, wrapper, request log có redaction, cross-cutting | Layer chính quyết định role/permission nếu đã có Spring Security |
| Spring MVC Interceptor | `HandlerInterceptor` | Sau khi HandlerMapping có MVC handler | Audit gắn handler, locale, metrics, MVC context | Bảo vệ toàn bộ Servlet/static/non-MVC endpoints |
| Spring Security | `SecurityFilterChain`, `FilterChainProxy` | Trong Servlet filter chain, thường trước MVC | Authentication, authorization, CSRF, session, headers | Một interceptor viết tay |
| Spring MVC CORS | `@CrossOrigin`, `addCorsMappings` | HandlerMapping/handler-specific | Browser origins/methods/headers | Authentication |
| CorsFilter | `CorsFilter` / Security `.cors(...)` | Trước auth trong security chain | Preflight và CORS response headers | CSRF protection |

Một browser JavaScript từ origin khác được CORS cho phép **không có nghĩa** user đó đã đăng nhập hoặc có quyền đọc dữ liệu. curl/server-side clients không enforce browser CORS, nhưng vẫn phải chịu server authentication/authorization.

## 3. Servlet Filter cần kiểm những gì?

`jakarta.servlet.Filter` có thể quan sát request/response, wrap chúng, set attributes/headers, rồi chuyển tiếp bằng `chain.doFilter(request,response)`. Nó có thể chặn sớm, kể cả khi chưa có MVC controller tương ứng.

~~~java
// Snippet của một class implements Filter, không phải file độc lập.
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    long began = System.nanoTime();
    try {
        chain.doFilter(request, response);
    } finally {
        long elapsed = System.nanoTime() - began;
        // Ghi metric; không log Authorization/Cookie/PII.
    }
}
~~~

Nếu quên `chain.doFilter` trong một nhánh, controller/Interceptor/Security filters phía sau nhánh đó không chạy. Đây có thể là intentional policy reject, nhưng phải có test chứng minh lý do.

### OncePerRequestFilter: “once” có giới hạn

`OncePerRequestFilter` giúp tránh thực thi lặp **trong một request dispatch** theo API contract, nhưng async dispatch, error dispatch và dispatcher type configuration có thể thay đổi việc gọi filter. Cần biết:

- `DispatcherType.REQUEST` cho request chính.
- `DispatcherType.ASYNC` cho async processing.
- `DispatcherType.ERROR` cho error dispatch.
- `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()`.
- Một Servlet request có thể chuyển qua nhiều dispatch phases.

Do đó đừng mặc nhiên khẳng định filter callback xảy ra đúng một lần cho toàn bộ logical request trong mọi hình thức async/ERROR. Với tracing/MDC hãy test cleanup để tránh ThreadLocal context tồn tại trên thread được tái sử dụng.

### Registration và thứ tự

Boot có thể tự đăng ký Spring bean kiểu `Filter`. `@Order(Ordered.HIGHEST_PRECEDENCE)` giúp đặt marker filter rất sớm. `FilterRegistrationBean` dành cho URL patterns, dispatcher types và explicit order.

~~~java
// Snippet minh họa cách registration thay thế.
// Không đồng thời @Component auto-register và registration lại cùng filter.
@Bean
FilterRegistrationBean<MyFilter> registerMyFilter(
        MyFilter filter) {
    FilterRegistrationBean<MyFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.addUrlPatterns("/api/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    bean.setOrder(Ordered.HIGHEST_PRECEDENCE);
    return bean;
}
~~~

`MyFilter` cần được định nghĩa bởi app, và method cần imports đúng. Trong project runnable ở dưới ta **chỉ dùng @Component + @Order** cho filter, không dùng snippet này để tránh double registration. Nếu đặt filter trong `HttpSecurity.addFilterBefore(...)`, đó là registration trong **Security filter chain**, không giống container-level filter; phải chọn owner và thứ tự có chủ đích.

## 4. HandlerInterceptor có scope khác Filter

`HandlerInterceptor` có ba callback cơ bản:

- `preHandle(request,response,handler)`: trước MVC controller, có thể trả `false` để dừng handler chain.
- `postHandle(...)`: sau handler, trước render theo lifecycle phù hợp; với REST body response có thể đã commit.
- `afterCompletion(...)`: cleanup sau khi request hoàn tất theo contract, không được gọi như nhau trên mọi error/async path.

Với async MVC còn có `AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)`. Nếu interceptor chỉ được đăng ký cho `/api/**` thì các routes ngoài pattern không mặc nhiên đi qua nó.

~~~java
// Fragment của một HandlerInterceptor.
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {
    response.setHeader("X-Mvc-Interceptor", "entered");
    return true;
}
~~~

Header chỉ là marker trong lab. Nếu Security trả 401/403 trước DispatcherServlet, interceptor có thể **không bao giờ chạy**, do đó thiếu marker là expected. Một 404 không có matched handler cũng không chứng minh interceptor lỗi.

**Không coi HandlerInterceptor là security boundary chính**. Spring Framework khuyến nghị dùng Spring Security/filter chain cho security vì MVC path matching, static resources và non-MVC endpoints có phạm vi khác.

## 5. Spring Security FilterChainProxy là tầng bảo vệ chính

Trong Servlet applications, một `DelegatingFilterProxy` thường được container đăng ký để gọi bean `springSecurityFilterChain`, tức `FilterChainProxy`. Bên trong có các security filters tùy config: authentication, CSRF, exception handling, authorization, session, CORS.

Một request có thể bị chặn trước khi controller nhận nó:

| HTTP request | Trạng thái người dùng | Kết quả lab | Nguyên nhân |
|---|---|---:|---|
| GET /api/public | anonymous | 200 | permitAll |
| GET /api/private | anonymous | 401 | cần authentication |
| GET /api/private | Basic password sai | 401 | authentication thất bại |
| GET /api/private | Basic viewer đúng | 200 | authenticated |
| GET /api/admin/report | ROLE_USER | 403 | thiếu ROLE_ADMIN |
| GET /api/admin/report | ROLE_ADMIN | 200 | được cho phép |
| POST /api/notes | authenticated, không CSRF token | 403 | CSRF bị từ chối |
| POST /api/notes | authenticated + valid CSRF token | 200 trong lab | authorization + CSRF hợp lệ |

**Không suy luận 403 = thiếu role**. 403 có thể do không đủ quyền, CSRF token sai hoặc CORS origin/method/header bị từ chối. Kiểm origin, method, authentication, CSRF và exception category.

`@RestControllerAdvice` không tự xử lý mọi lỗi từ Security filters trước DispatcherServlet. Nếu production cần ProblemDetail/JSON nhất quán cho 401/403, định nghĩa `AuthenticationEntryPoint` và `AccessDeniedHandler` thích hợp trong Spring Security, không dựa duy nhất vào exception handler MVC.

## 6. CORS preflight và actual request

CORS là browser security mechanism để JavaScript ở một origin có được đọc response của origin khác hay không. Origin gồm scheme, host, port. Browser có thể gửi preflight trước actual request nếu request không thuộc những trường hợp safelisted.

### Actual cross-origin GET

~~~http
GET /api/public HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
~~~

Response có thể chứa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json
~~~

Đây là trích phần headers có ý nghĩa; response thực có thêm các security/cache headers. Server authentication vẫn chạy độc lập. curl thêm Origin header vẫn không tự chặn việc đọc response theo CORS; browser mới enforce browser policy.

### Browser preflight OPTIONS

~~~http
OPTIONS /api/private HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Nếu được cho phép, server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

**Preflight thường không gửi cookies/session**, do đó Spring Security docs yêu cầu xử lý CORS **trước bước xác thực**. Nếu Security đánh OPTIONS như request unauthenticated rồi trả 401 trước khi xem CORS, browser có thể báo “CORS error” dù actual endpoint đúng.

Để test preflight, cần **Origin** và **Access-Control-Request-Method**, khi có custom headers thì thêm **Access-Control-Request-Headers**. Một OPTIONS không có những headers này không phải bằng chứng preflight đúng.

### CORS allowlist

Các thuộc tính chính của `CorsConfiguration`:

| Thuộc tính | Kiểm soát | Gợi ý |
|---|---|---|
| allowedOrigins | Origins được phép | Dùng exact HTTPS origins đáng tin |
| allowedMethods | Actual HTTP methods được phép | Chỉ allow GET/POST/etc thực tế dùng |
| allowedHeaders | Headers frontend muốn gửi | Authorization/Content-Type/... được kiểm |
| exposedHeaders | Response headers JS được phép đọc | Không expose secrets |
| allowCredentials | Browser credentials cross-origin | Không kết hợp wildcard origin bừa bãi |
| maxAge | Preflight cache lifetime | Test cache/rollout policy |
| Vary | Tránh cache nhầm giữa origins | Kiểm gateway/CDN đúng behavior |

**Không dùng `Access-Control-Allow-Origin: *` với `Access-Control-Allow-Credentials: true`**. Khi cần credentials, chọn allowlist origins cụ thể hoặc origin pattern được kiểm soát chặt. Đừng phản chiếu mọi Origin vào response rồi gọi đó là allowlist.

## 7. CORS không thay authentication hoặc CSRF

Một flow hoàn toàn hợp lệ:

~~~text
OPTIONS preflight from trusted origin
  -> CORS allowed, 200

POST actual /api/notes from same origin
  -> authenticated user valid
  -> CSRF token thiếu hoặc sai
  -> 403
~~~

Preflight chỉ cho phép browser **thử gửi actual request**, không cấp quyền thay user và không tạo CSRF token. Với cookie/session authentication, CSRF protection có vai trò quan trọng; không disable CSRF chỉ để “sửa CORS”.

Trong `spring-security-test`:

~~~java
// Snippet trong test có MockMvc mvc và spring-security-test imports.
mvc.perform(post("/api/notes")
        .with(user("viewer").roles("USER"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"hello\"}"))
    .andExpect(status().isForbidden());

mvc.perform(post("/api/notes")
        .with(user("viewer").roles("USER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"hello\"}"))
    .andExpect(status().isOk());
~~~

`with(csrf())` tạo valid token **cho test**, không thiết kế cách frontend production lấy token. Nếu app thật dùng session/cookie, cần phát token và cho browser gửi nó theo security design; nếu JWT bearer stateless, đánh giá threat model trước khi quyết định CSRF policy.

## 8. Chọn tầng test phù hợp

| Cách test | Bao phủ | Không bao phủ đầy đủ |
|---|---|---|
| JUnit trực tiếp với mock FilterChain | Logic một Filter | Filter ordering/context thật |
| `@WebMvcTest` + MockMvc | MVC controller, selected MVC beans | Toàn custom configuration ngoài slice |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | App context + registered filters + Security chain + MVC trong mock environment | Real socket/TLS/proxy/container-specific behavior |
| `@SpringBootTest(RANDOM_PORT)` | Embedded HTTP server thật và actual headers | Browser enforcement/CORS qua ingress |
| Browser E2E | Browser CORS, credentials, redirects, cookies | Không thay unit/security negative tests |
| Staging qua gateway | TLS/proxy/CORS duplication/forwarded headers | Chậm, environment dependent |

**Không test security bằng `@AutoConfigureMockMvc(addFilters=false)`**: nó có thể loại filters trong MockMvc, bao gồm Spring Security. Nếu mục tiêu thật chỉ là controller unit behavior thì một test disabled-filter có thể chấp nhận khi được đặt tên rõ, nhưng phải có test khác bật filters để chứng minh bảo mật.

`@WebMvcTest` là slice: có thể scan một số Filter/HandlerInterceptor/WebMvcConfigurer, nhưng custom `@Configuration` và authentication beans có thể không có nếu không import. Một test slice trả 200 không tự chứng minh production `SecurityFilterChain` đúng. Bài này dùng full context để giảm nguy cơ kiểm sai cấu hình.

## 9. Lab runnable: Spring MVC + Security + CORS

Bốn endpoints:

~~~text
GET  /api/public         : anonymous 200
GET  /api/private        : authenticated user
GET  /api/admin/report   : requires ROLE_ADMIN
POST /api/notes          : authenticated + CSRF

RequestMarkerFilter @Order(HIGHEST_PRECEDENCE)
   -> Spring Security CorsFilter/auth/CSRF/role
   -> DispatcherServlet
   -> HandlerMarkerInterceptor for /api/**
   -> Controller
~~~

Marker headers trong response: `X-Request-Filter: seen` nếu custom Servlet filter chạy, `X-Mvc-Interceptor: entered` nếu đi vào preHandle. Những headers này **không phải chứng chỉ xác thực**, chỉ là dấu vết cho phép test ranh giới.

### 9.1. Project layout

~~~text
web-boundary-lab/
  pom.xml
  src/main/java/example/webboundary/WebBoundaryApplication.java
  src/main/resources/application.properties
  src/test/java/example/webboundary/WebBoundaryApplicationTests.java
  src/test/java/example/webboundary/RealHttpCorsSmokeTests.java
~~~

### 9.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>web-boundary-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Boot parent BOM quản lý Security 6.3 và Spring Framework 6.1 versions trong nhánh 3.3; không override từng dependency không có lý do tương thích/security. `spring-security-test` thuộc test scope, không đóng gói thành production runtime library.

### 9.3. application.properties

~~~properties
server.port=8080
server.error.include-message=never
server.error.include-exception=false
server.error.include-stacktrace=never
~~~

### 9.4. Full Java application

Tạo `src/main/java/example/webboundary/WebBoundaryApplication.java`:

~~~java
package example.webboundary;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class WebBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebBoundaryApplication.class, args);
    }

    @Component
    @Order(Ordered.HIGHEST_PRECEDENCE)
    static class RequestMarkerFilter extends OncePerRequestFilter {
        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            response.setHeader("X-Request-Filter", "seen");
            chain.doFilter(request, response);
        }
    }

    @Component
    static class HandlerMarkerInterceptor
            implements HandlerInterceptor {

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {

            response.setHeader("X-Mvc-Interceptor", "entered");
            return true;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class MvcConfiguration implements WebMvcConfigurer {
        private final HandlerMarkerInterceptor marker;

        MvcConfiguration(HandlerMarkerInterceptor marker) {
            this.marker = marker;
        }

        @Override
        public void addInterceptors(InterceptorRegistry registry) {
            registry.addInterceptor(marker)
                    .addPathPatterns("/api/**");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SecurityConfiguration {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {

            return http
                .cors(Customizer.withDefaults())
                // Không tắt CSRF: POST phải có token phù hợp.
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                        HttpMethod.GET, "/api/public").permitAll()
                    .requestMatchers("/api/admin/**")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
        }

        @Bean
        UrlBasedCorsConfigurationSource corsConfigurationSource() {
            CorsConfiguration config = new CorsConfiguration();
            config.setAllowedOrigins(
                List.of("https://app.example.test"));
            config.setAllowedMethods(
                List.of("GET", "POST", "OPTIONS"));
            config.setAllowedHeaders(
                List.of("Authorization",
                        "Content-Type", "X-Request-ID"));
            config.setExposedHeaders(
                List.of("X-Request-Filter",
                        "X-Mvc-Interceptor"));
            config.setAllowCredentials(true);
            config.setMaxAge(600L);

            UrlBasedCorsConfigurationSource source =
                    new UrlBasedCorsConfigurationSource();
            source.registerCorsConfiguration("/api/**", config);
            return source;
        }

        @Bean
        PasswordEncoder passwordEncoder() {
            return PasswordEncoderFactories
                    .createDelegatingPasswordEncoder();
        }

        @Bean
        UserDetailsService userDetailsService(
                PasswordEncoder encoder) {

            // Credentials tĩnh CHỈ CHO LAB, không dùng production.
            return new InMemoryUserDetailsManager(
                User.withUsername("viewer")
                    .password(encoder.encode("viewer-pass"))
                    .roles("USER")
                    .build(),
                User.withUsername("admin")
                    .password(encoder.encode("admin-pass"))
                    .roles("ADMIN")
                    .build()
            );
        }
    }

    public record NoteInput(String text) {
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/public")
        public Map<String, String> publicInfo() {
            return Map.of("visibility", "public");
        }

        @GetMapping("/api/private")
        public Map<String, String> privateInfo(
                Authentication authentication) {
            return Map.of(
                "user", authentication.getName(),
                "visibility", "private");
        }

        @GetMapping("/api/admin/report")
        public Map<String, String> adminReport() {
            return Map.of("report", "admin-only");
        }

        @PostMapping(value = "/api/notes",
                     consumes = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, String>> createNote(
                @RequestBody NoteInput note,
                Authentication authentication) {
            return ResponseEntity.ok(Map.of(
                "owner", authentication.getName(),
                "text", note.text()));
        }
    }
}
~~~

### 9.5. Giải thích các lớp code

**RequestMarkerFilter** được Boot đăng ký vào Servlet container vì là Spring bean kiểu Filter. Với `@Order(HIGHEST_PRECEDENCE)` trong lab, nó chạy trước Security chain và đặt header trước `chain.doFilter`. Security có thể trả 401/403 nhưng header đã được đặt, do đó test quan sát `X-Request-Filter: seen`.

**HandlerMarkerInterceptor** chỉ áp dụng sau khi MVC mapping chọn handler cho `/api/**`. Unauthorized trước Security không đến interceptor, do đó không có `X-Mvc-Interceptor`. Bất kỳ marker nào ở đây cũng không xác minh token/password/role.

**SecurityConfiguration** cung cấp `SecurityFilterChain` rõ ràng và `UrlBasedCorsConfigurationSource` bean. `http.cors(Customizer.withDefaults())` tích hợp CORS trước các authentication checks trong Security. Authorization dùng `GET /api/public` public, admin yêu cầu ROLE_ADMIN, còn lại authenticated; HTTP Basic được bật cho lab, form login tắt để API trả 401. CSRF vẫn enabled, bảo vệ POST.

**InMemoryUserDetailsManager** có hai users giả lập với encoded passwords; **không deploy user/password này ở production**. Usernames/passwords được đưa vào tài liệu chỉ để tự chạy curl trên localhost. Production cần IdP, secret manager, HTTPS và security review. `CORS.allowCredentials=true` đi với một exact trusted Origin, không wildcard.

**ApiController** có một POST tạo body JSON để test CSRF; dữ liệu chưa được lưu DB, nên “createNote” trong lab chỉ echo dữ liệu. Nếu sản phẩm thật lưu user input cần Bean Validation, authorization theo object/tenant và input bounds.

## 10. MockMvc test file đầy đủ: giữ nguyên filters

Tạo `src/test/java/example/webboundary/WebBoundaryApplicationTests.java`:

~~~java
package example.webboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebBoundaryApplicationTests {
    private static final String ORIGIN =
            "https://app.example.test";

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteCrossesFilterAndMvcInterceptor()
            throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Request-Filter", "seen"))
            .andExpect(header().string(
                "X-Mvc-Interceptor", "entered"))
            .andExpect(jsonPath("$.visibility")
                .value("public"));
    }

    @Test
    void anonymousRequestIsStoppedBeforeMvc() throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "X-Request-Filter", "seen"))
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void wrongBasicPasswordFails() throws Exception {
        mvc.perform(get("/api/private")
                .with(httpBasic("viewer", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicPasswordReachesController() throws Exception {
        mvc.perform(get("/api/private")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Mvc-Interceptor", "entered"))
            .andExpect(jsonPath("$.user").value("viewer"));
    }

    @Test
    void viewerIsForbiddenFromAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void adminIsAuthorized() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report")
                .value("admin-only"));
    }

    @Test
    void allowedPreflightDoesNotRequireCredentials()
            throws Exception {
        mvc.perform(options("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "Authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ORIGIN))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"))
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void rejectedOriginPreflightHasNoAllowOrigin()
            throws Exception {
        mvc.perform(options("/api/private")
                .header(HttpHeaders.ORIGIN,
                    "https://evil.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void actualCorsGetHasAllowOrigin() throws Exception {
        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ORIGIN));
    }

    @Test
    void actualCorsGetStillRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ORIGIN));
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("viewer").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void authenticatedPostWithCsrfPasses()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("viewer").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Request-Filter", "seen"))
            .andExpect(header().string(
                "X-Mvc-Interceptor", "entered"))
            .andExpect(jsonPath("$.text").value("hello"))
            .andExpect(jsonPath("$.owner").value("viewer"));
    }
}
~~~

### Ý nghĩa 12 tests

- Test public endpoint xác minh **cả filter lẫn interceptor** có mặt khi controller chạy.
- Test anonymous kiểm 401 và marker filter có nhưng interceptor không có, minh họa Security short-circuit.
- Test wrong/valid HTTP Basic đi qua authentication thực, không chỉ giả định user.
- Test viewer/admin tách authorization role check khỏi authentication.
- Test allowed preflight không gửi Basic credentials, nhưng vẫn được CORS policy trả allow-origin; MVC interceptor không chạy.
- Test unknown Origin preflight bị 403, **không** có allow-origin.
- Test actual cross-origin GET được CORS cho phép nhưng private endpoint vẫn trả 401 nếu thiếu auth.
- Test POST thiếu CSRF trả 403; có CSRF token dùng `with(csrf())` thì vào MVC controller và trả JSON.

**Phân biệt hai test helpers:** `with(user(...))` tạo một authenticated principal trong Security test context để test authorization, **không** verify password hash hoặc JWT signature. `with(httpBasic(...))` tạo Basic Authorization header để thực sự đi qua authentication provider của lab. Với OAuth2/JWT production, cần tests đi qua decoder/issuer/audience/signature validation, không chỉ dùng mock user rồi tuyên bố token verification đạt.

`@AutoConfigureMockMvc` không đặt `addFilters=false`, vì thế security filters thực được đăng ký trong mock environment. Test này **không** khởi động real TCP server.

## 11. Smoke test trên HTTP server thật

MockMvc hoạt động ở test MVC infrastructure; nó không mô phỏng hết các chi tiết network/container. Dùng test `RANDOM_PORT` với `TestRestTemplate`.

Tạo `src/test/java/example/webboundary/RealHttpCorsSmokeTests.java`:

~~~java
package example.webboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpCorsSmokeTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void realHttpResponseContainsCorsAndMarkerHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://app.example.test");

        ResponseEntity<String> response = http.exchange(
                "/api/public",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("https://app.example.test",
                response.getHeaders().getFirst(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
        assertEquals("seen",
                response.getHeaders().getFirst(
                    "X-Request-Filter"));
        assertEquals("entered",
                response.getHeaders().getFirst(
                    "X-Mvc-Interceptor"));
    }
}
~~~

`RANDOM_PORT` khởi động embedded HTTP server thật trên cổng ngẫu nhiên và `TestRestTemplate` gửi HTTP request. Nó kiểm CORS/marker headers trên wire; **nó không thay một browser E2E test**, vì HTTP test clients không enforce CORS giống browser. `@SpringBootTest` contexts của test mock và real server có thể khác nhau và tốn thời gian khởi động riêng.

### Chạy bộ test

~~~bash
mvn clean test
mvn clean package
~~~

Khi Java17/Maven/dependencies hợp lệ và source đúng package, bộ trên có **12 MockMvc tests + 1 real HTTP test**; Maven phải báo tests pass. Build output/timestamps/log lines thay đổi theo hệ điều hành và tool versions; không cần so stdout trùng từng ký tự.

Nếu một test fail, xem first failure của status/header, security chain và CORS config trước khi xóa assertion. Không chỉnh test thành `addFilters=false` để ép green.

## 12. Chạy thật bằng curl

Chạy trong thư mục project:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
# 200: filter + MVC interceptor.
curl -i http://localhost:8080/api/public

# 401: filter chạy; MVC interceptor không chạy.
curl -i http://localhost:8080/api/private

# 200: HTTP Basic đúng (CHỈ local lab credentials).
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/private

# 403: USER không có ROLE_ADMIN.
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/admin/report

# 200: ADMIN được phép.
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/report
~~~

JSON body thành công tương đương (thứ tự fields có thể khác):

~~~json
{"visibility":"public"}
~~~

~~~json
{"user":"viewer","visibility":"private"}
~~~

~~~json
{"report":"admin-only"}
~~~

### Preflight allowed Origin

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/private" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
~~~

Kỳ vọng status 200 và headers `Access-Control-Allow-Origin: https://app.example.test`, `Access-Control-Allow-Credentials: true` theo cấu hình lab. Preflight **không cần** gửi Authorization/cookie để được CORS xử lý.

### Preflight denied Origin

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/private" \
  -H "Origin: https://evil.example.test" \
  -H "Access-Control-Request-Method: GET"
~~~

Kỳ vọng 403 và không có allow-origin cho evil origin. Browser sẽ không cho JavaScript ở evil origin đọc response theo policy; curl vẫn có thể xem response bytes vì nó không phải browser.

### Actual cross-origin private GET thiếu Basic

~~~bash
curl -i \
  "http://localhost:8080/api/private" \
  -H "Origin: https://app.example.test"
~~~

Kỳ vọng **401** mặc dù Origin được phép. Đây là bằng chứng “CORS allowed” khác “authenticated”.

### POST authenticated thiếu CSRF

~~~bash
curl -i \
  -u viewer:viewer-pass \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}' \
  "http://localhost:8080/api/notes"
~~~

Kỳ vọng **403** do không có valid CSRF token. curl không tự tạo CSRF token; test positive path dùng `with(csrf())`. Nếu frontend thực cần POST với cookie/session, phải có CSRF token exchange phù hợp. Không tắt CSRF tùy tiện.

### Method/header không nằm trong allowlist

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/private" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: DELETE" \
  -H "Access-Control-Request-Headers: X-Unapproved-Header"
~~~

Kỳ vọng CORS reject (403) vì policy lab không cho DELETE/custom header. Test allowed origin **và** disallowed method/header là cần thiết; chỉ kiểm good origin chưa đủ.

## 13. @WebMvcTest, standaloneSetup và false positives

`@WebMvcTest` là slice tập trung MVC, thường nhanh hơn full context, nhưng có giới hạn scanned beans. `Filter`, `HandlerInterceptor`, `WebMvcConfigurer` có thể nằm trong slice theo component type, còn custom `@Configuration` hay service dependencies không mặc nhiên được load. Nếu không import security config, test có thể đang chạy **một SecurityFilterChain khác** so với production.

Snippet:

~~~java
// Minh họa setup; không phải test class hoàn chỉnh.
@WebMvcTest(WebBoundaryApplication.ApiController.class)
@Import({
    WebBoundaryApplication.SecurityConfiguration.class,
    WebBoundaryApplication.MvcConfiguration.class
})
class ApiSliceTest {
    @Autowired MockMvc mvc;
}
~~~

Với các service dependencies khác, phải dùng `@MockBean`/test config theo Boot 3.3. Đừng import mọi auto-configuration bằng tay; test slice có cách Boot quản lý riêng.

### So sánh những cách test dễ nhầm

| Test setup | Cạm bẫy |
|---|---|
| `MockMvcBuilders.standaloneSetup(controller)` | Không tự có Spring Security FilterChainProxy |
| `@WebMvcTest` thiếu custom config | Có thể không phản ánh actual role/CORS rules |
| `@AutoConfigureMockMvc(addFilters=false)` | Có thể tắt Security/CORS/Servlet filters |
| `with(user("admin").roles("ADMIN"))` | Không verify Basic password/JWT signature |
| `with(httpBasic(...))` | Đi qua Basic auth provider nhưng chưa test browser cookie policy |
| `MockMvc` | Không kiểm TCP/TLS/container-specific behavior |
| `RANDOM_PORT` TestRestTemplate | Có HTTP thật nhưng không enforce browser CORS |
| Browser test | CORS/cookies/redirect thực nhưng cần backend authorization tests riêng |

Manual MockMvc với WebApplicationContext nên apply Spring Security test configurer:

~~~java
// Snippet; cần WebApplicationContext context.
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

Trong lab, `@AutoConfigureMockMvc` tích hợp Security filter chain của full context; không cần manual builder. Với OAuth2 resource server, cần dedicated test decode/signature/issuer/audience/scope, không chỉ mock roles.

## 14. Khi có nhiều SecurityFilterChain

Spring Security chọn chain đầu tiên match request theo `securityMatcher`/`@Order`. Ví dụ:

~~~java
// Fragment minh họa cấu trúc, không phải SecurityConfig hoàn chỉnh.
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/admin/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Một chain chỉ match `/admin/**` **không tự bảo vệ** routes khác. Fallback chain rất quan trọng. Trong multi-chain app, CORS/CSRF/session policies có thể khác giữa các chains; cần cấu hình và test từng nhóm, tránh hai `CorsConfigurationSource` beans khiến Spring Security không chọn đúng source tự động.

### Những negative tests cần có

- GET /admin/report với USER → 403; ADMIN → 200.
- GET /api/private với anonymous → 401 **từ fallback**.
- New route ngoài /api/** hoặc /admin/** không được public ngoài ý định.
- OPTIONS preflight trên admin/public API theo đúng policy của chain thực.
- Case URL path encoding, servlet path, trailing slash và proxy rewrite nếu có.
- Authenticated role vs object ownership: `ROLE_ADMIN`/`ROLE_USER` chưa đủ chứng minh phân quyền theo tenant/resource.

Đừng thay chính sách bằng interceptor custom vì không match SecurityFilterChain. Mỗi protected resource có một owner xác định.

## 15. Async, error dispatch, 404 và response commit

Một REST controller có thể dùng `Callable`, `DeferredResult` hoặc reactive return adapter trong Spring MVC. Khi async dispatch xảy ra, `OncePerRequestFilter`, interceptor callbacks và MDC/ThreadLocal cần test riêng. Với `ERROR` dispatch, controller advice, Servlet error page và Security filters có thể chạy ở những pha khác nhau.

- Servlet filter có thể đặt header trước chain; nếu đặt **sau** chain khi response đã commit, header có thể không còn hiệu lực.
- `postHandle` không phải một nơi bảo đảm thêm header cho mọi REST response; response body có thể đã được ghi.
- Interceptor có thể không chạy nếu Security chặn hoặc HandlerMapping không tìm được handler.
- `afterCompletion` cần đúng preHandle/lifecycle để được gọi.
- Filter trên `/error` hoặc actuator endpoints có thể chạy theo URL patterns/dispatcher types khác `/api/**`.
- Với exception trong filter trước DispatcherServlet, `@RestControllerAdvice` không phải luôn là error handler tương ứng.
- Với async timeouts/cancellation, kiểm cleanup request attributes, pooled resources và correlation context, không chỉ status.

### URL matching mismatches

Các URL variations như `/api/private`, `/api/private/`, `/api//private`, uppercase, encoded dot segments hoặc semicolon parameters có thể được proxy/Tomcat/MVC/Security normalize khác nhau tùy phiên bản/config. Không mặc định chúng cùng outcome. Khi test chính sách authorization, kiểm route đã normalize và có matcher rõ; dùng `StrictHttpFirewall`/framework defaults theo Spring Security recommendations, không tự bỏ request firewall để “fix” 400/404.

## 16. CORS qua proxy và browser

Một test MockMvc thành công không chứng minh app chạy đúng sau ingress:

~~~text
Browser https://app.example.test
  | OPTIONS /api/private
  v
CDN / Ingress / NGINX
  | có thể redirect, cache, rewrite hoặc thêm CORS headers
  v
Spring Security CorsFilter
  |
  v
Controller (actual request sau preflight)
  |
  v
Response lại qua proxy/browser
~~~

Các trường hợp cần test:

1. Reverse proxy trả 301/302 khi OPTIONS tới HTTP→HTTPS hoặc path khác.
2. Gateway tự set `Access-Control-Allow-Origin: *` còn Spring trả exact origin, gây duplicate/conflicting headers.
3. CDN cache response CORS nhưng bỏ `Vary: Origin`, dẫn tới origin khác nhận sai allow-origin.
4. Browser requests dùng headers không nằm trong allowlist, ví dụ Authorization + X-Client-Version.
5. Actual request bị 401/403 nhưng response lỗi thiếu CORS header; browser báo “CORS error” thay vì nhận error body được phép đọc.
6. Cookie `SameSite`, `Secure`, domain/path và browser credentials mode không khớp; không phải mọi login failure đều là CORS.
7. Proxy rewrite `Host`, scheme/forwarded headers sai; chỉ tin trusted ingress, không tin arbitrary X-Forwarded-* từ internet.
8. Browser preflight cache dẫn tới hành vi khác sau khi bạn thay allowlist; kiểm browser network tab và cache behavior.
9. NGINX/Envoy/service mesh và app đều có CORS policies nhưng không cùng owner, làm preflight pass và actual fail.

**Luôn kiểm cuối đường public HTTPS URL**, không chỉ localhost, và dùng browser/E2E cho browser enforcement. curl trực tiếp rất hữu ích để thấy raw headers/status nhưng không áp hạn chế CORS của browser.

## 17. Ma trận nghiệm thu

| Case | Security outcome | CORS outcome | Filter marker | MVC marker |
|---|---|---|---|---|
| Anonymous GET public | 200 | Không Origin | Có | Có |
| Anonymous GET private | 401 | Không Origin | Có | Không |
| Basic password sai | 401 | Không Origin | Có | Không |
| Basic viewer đúng | 200 | Không Origin | Có | Có |
| Viewer gọi admin | 403 | Không Origin | Có | Không |
| Admin gọi admin | 200 | Không Origin | Có | Có |
| Allowed preflight OPTIONS | Không yêu cầu auth | 200 + allow-origin | Có trong setup lab | Không |
| Denied origin preflight | Chặn sớm | 403, không allow-origin | Có trong setup lab | Không |
| Actual CORS GET public | 200 | Allow-origin | Có | Có |
| Actual CORS GET private anonymous | 401 | Allow-origin | Có | Không |
| Authenticated POST without CSRF | 403 | Không Origin | Có | Không |
| Authenticated POST with CSRF | 200 | Không Origin | Có | Có |
| CORS disallowed DELETE/header | Chặn sớm | 403 | Có trong setup lab | Không |
| Route không có MVC handler | 404 hoặc error theo config | Tùy route/CORS mapping | Filter có thể chạy | Không bảo đảm |
| Error/async dispatch | Theo container/security context | Theo dispatch | Phụ thuộc dispatcher types | Theo async/error lifecycle |

Đây là outcomes của lab, **không phải defaults của mọi app**. Một dự án có AuthenticationEntryPoint hoặc CSRF exemptions khác có thể trả response khác; hãy ghi contract và test actual policy.

## 18. Những anti-pattern phải tránh

| Sai lầm | Hậu quả | Sửa |
|---|---|---|
| Tắt filters để test security pass | Bỏ qua FilterChainProxy và CORS | Dùng full context + MockMvc có filters |
| Dùng `with(user())` để chứng minh password/JWT | Authentication provider không được exercise | `httpBasic()` hoặc JWT decoder tests |
| Chỉ kiểm 200 | Không thấy 401/403/CSRF/CORS failure | Positive + negative matrix |
| OPTIONS thiếu Origin/Request-Method | Không thực sự kiểm preflight | Dùng đủ headers |
| Bắt preflight phải có cookie | Browser preflight thường không có | CORS trước authentication |
| Tắt CSRF để chữa lỗi CORS | Có thể tạo CSRF vulnerability | Kiểm request policy/filter order |
| Xem CORS allow-origin như đăng nhập thành công | API vẫn có thể chưa auth | Authn/Authz độc lập |
| AllowedOrigins wildcard với credentials true | Sai security/browser semantics | Exact trusted origins |
| Chỉ test allowed origin | Policy vô tình quá rộng khó phát hiện | Denied-origin/header/method tests |
| Filter tự đặt “authenticated” header | Header trước Security không có giá trị auth | Dùng authenticated SecurityContext khi thích hợp |
| Interceptor kiểm role thay Spring Security | Bỏ sót non-MVC/static/matcher mismatch | SecurityFilterChain |
| Filter đăng ký container + security cùng lúc | Chạy hai lần, audit/rate-limit sai | Một registration owner |
| Slice test thiếu @Import custom config | Có thể test một chain khác production | @Import hoặc full @SpringBootTest |
| @ControllerAdvice bắt mọi 401/403 | Lỗi Security có thể được xử lý trước MVC | EntryPoint + AccessDeniedHandler |
| MockMvc đủ cho HTTP2/TLS/cookies | Không có real socket/browser | RANDOM_PORT + E2E |
| Proxy/app cùng ghi CORS headers | Duplicates, browser reject | Một owner và tests |
| Không test fallback SecurityFilterChain | Endpoint mới có thể public | Negative tests cho unknown routes |
| Không xử lý ASYNC/ERROR dispatch | Mất trace/cleanup sai | Dispatcher types + async/error tests |

## 19. Phân biệt WebFlux

Nếu ứng dụng là Spring WebFlux/Reactive, đừng đem nguyên MVC Interceptor/Servlet Filter sang:

| Quan tâm | Spring MVC | Spring WebFlux |
|---|---|---|
| Request filter | `jakarta.servlet.Filter`/`OncePerRequestFilter` | `org.springframework.web.server.WebFilter` |
| Filter chain | `FilterChain` | `WebFilterChain` |
| Handler intercept | `HandlerInterceptor` | Reactive handler filters/WebFilter; không dùng MVC interceptor |
| Security | `SecurityFilterChain`/`HttpSecurity` | `SecurityWebFilterChain`/`ServerHttpSecurity` |
| CORS | `CorsFilter`/MVC CORS | WebFlux CORS/`CorsWebFilter` |
| Tests | `MockMvc`, `spring-security-test` | `WebTestClient`, reactive Security test support |
| Request context | Servlet request/thread-local | `ServerWebExchange`/Reactor Context |
| Cancellation | Servlet async lifecycle | Reactive publisher cancellation |

Một WebFlux filter snippet:

~~~java
// Fragment, không phải file Java độc lập.
@Bean
WebFilter reactiveMarker() {
    return (exchange, chain) -> {
        exchange.getResponse().getHeaders()
                .add("X-Reactive-Filter", "seen");
        return chain.filter(exchange);
    };
}
~~~

Nó không thay authentication. Trong reactive stack, Security WebFilterChain và CORS filter ordering có cơ chế riêng. Dùng `@WebFluxTest` hoặc `@SpringBootTest + @AutoConfigureWebTestClient` phù hợp, nhập custom reactive security configs vào slice nếu cần. Với cả starter-web và starter-webflux trên Boot 3.3, MVC thường được ưu tiên làm server stack mặc định: đừng chỉ nhìn code `Mono` rồi tưởng đã test WebFlux server.

## 20. Troubleshooting theo triệu chứng

**A. Browser báo CORS nhưng curl GET 200.**  
Kiểm actual Origin, preflight OPTIONS, Access-Control-Request-Method/Headers, Allow-Origin response, credentials mode và proxy. Curl không enforce CORS.

**B. Preflight trả 401.**  
Kiểm `http.cors(...)`, CorsConfigurationSource/MVC CORS integration và thứ tự Security; đừng bắt browser preflight phải có session cookie.

**C. Preflight 200 nhưng POST 403.**  
Kiểm CSRF, authentication, role và actual request; preflight không miễn CSRF.

**D. Test thiếu auth mà vẫn 200.**  
Kiểm có `addFilters=false`, `standaloneSetup`, global mock principal, default/test chain khác production không.

**E. Không có X-Mvc-Interceptor trên 401.**  
Có thể Security đã chặn trước DispatcherServlet, đây là behavior đúng.

**F. Không có marker trên OPTIONS preflight.**  
CorsFilter có thể xử lý trước MVC nên interceptor không chạy; đừng giả định OPTIONS luôn vào controller.

**G. 403 khi origin lạ.**  
Có thể CORS rejected trước Security authz, không phải role issue. Phân loại response headers và logs.

**H. Local pass nhưng production fail.**  
Xem gateway rewrite/redirect, cache/Vary, cookie SameSite, TLS/forwarded headers và duplicate CORS policies.

**I. Filter bị gọi hai lần.**  
Tìm @Component, FilterRegistrationBean, addFilterBefore/addFilterAfter và dispatcher types; loại duplicate registration.

**J. Route admin mới lọt qua Security.**  
Kiểm securityMatcher, order, fallback chain và path normalization; thêm negative test cho route mới.

## 21. Checklist CI và review

- [ ] Maven/JUnit chạy trên Java17+ và các Boot 3.3 dependencies phù hợp.
- [ ] MockMvc tests có Servlet filters enabled và actual SecurityFilterChain.
- [ ] 200 public, 401 anonymous private, 401 invalid Basic.
- [ ] 403 authenticated USER vào admin, 200 ADMIN.
- [ ] Preflight allowed origin/method/header, không đòi cookie.
- [ ] Preflight denied origin/method/header, không trả allow-origin.
- [ ] Actual cross-origin request vẫn bị authentication khi thiếu credentials.
- [ ] POST authenticated without CSRF bị 403; with CSRF token đi qua.
- [ ] RequestMarkerFilter chạy trên early-denial, HandlerMarkerInterceptor không.
- [ ] Success path có marker Filter và Interceptor.
- [ ] Slice tests có @Import/config đúng hoặc full-context tests thay thế.
- [ ] Real HTTP RANDOM_PORT smoke test chạy với actual embedded server.
- [ ] Browser/gateway E2E tests kiểm Origin/cookies/redirect/cache.
- [ ] Security matcher fallback và non-API routes được bảo vệ theo contract.
- [ ] Không duplicate filters hoặc CORS headers.
- [ ] Không để lab credentials, raw auth/cookies hay secrets trong production logs.
- [ ] Có negative regression tests cho thay đổi CORS, CSRF và SecurityFilterChain.

Nếu CI fail, không “fix” bằng tắt filters hoặc trả permitAll. Đối chiếu request path/matcher, preflight headers, security context, CSRF, filter ordering và exception owner.

## 22. Câu hỏi tự kiểm tra

**1. Filter và Interceptor có cùng scope không?**  
Không. Filter ở Servlet layer; Interceptor ở Spring MVC handler layer.

**2. Security trả 401 trước DispatcherServlet có buộc preHandle chạy không?**  
Không. Interceptor thường không chạy khi security chain chặn sớm.

**3. CORS có thay authentication không?**  
Không. Nó là browser cross-origin access policy.

**4. Một OPTIONS không có Origin có phải browser preflight hợp lệ?**  
Không đủ. Preflight có Origin và Access-Control-Request-Method.

**5. Preflight thường chứa JSESSIONID cookie không?**  
Không. Vì thế CORS phải được xử lý trước authentication checks.

**6. Preflight thành công thì actual POST có được miễn CSRF?**  
Không. CSRF và CORS là hai vấn đề riêng.

**7. 403 có luôn là thiếu role?**  
Không. CSRF hoặc CORS rejection cũng có thể trả 403.

**8. Vì sao không dùng HandlerInterceptor làm security boundary duy nhất?**  
Nó không bảo phủ nhất quán các endpoint ngoài MVC và có rủi ro path-matcher mismatch.

**9. @WebMvcTest có luôn nhập custom SecurityFilterChain?**  
Không. Slice có thể thiếu @Configuration khác; cần import hoặc full context.

**10. addFilters=false có chứng minh authentication production đúng không?**  
Không. Nó có thể loại FilterChainProxy khỏi MockMvc.

**11. with(user(...)) có verify mật khẩu thật?**  
Không. Nó mô phỏng authenticated principal; httpBasic helper đi qua Basic provider.

**12. with(csrf()) làm gì?**  
Tạo valid test CSRF token cho unsafe method khi được bảo vệ.

**13. MockMvc có dùng TCP socket thật không?**  
Không trong mock web environment. Dùng RANDOM_PORT để test real HTTP server.

**14. curl có enforce browser CORS không?**  
Không. Browser mới thực thi access restrictions.

**15. Cho phép credentials với Origin=* có đúng không?**  
Không phù hợp browser CORS credential semantics; dùng trusted exact origins.

**16. Một filter có thể chạy trên 404 không?**  
Có, filter ở trước HandlerMapping; interceptor chưa chắc chạy.

**17. Hai SecurityFilterChain thì chọn chain nào?**  
Chain đầu tiên match request theo order; cần fallback để không bỏ sót URLs.

**18. CORS allowed nhưng actual private GET anonymous nên trả gì trong lab?**  
401, và có thể vẫn có Allow-Origin header.

**19. Vì sao cần test Origin bị từ chối?**  
Để bắt lỗi policy vô tình mở rộng, không chỉ xác nhận happy path.

**20. Khi WebFlux chạy, có nên copy MVC HandlerInterceptor?**  
Không. Dùng WebFilter, SecurityWebFilterChain và WebTestClient theo reactive stack.

## 23. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @WebMvcTest, @SpringBootTest, @AutoConfigureMockMvc và RANDOM_PORT.
- [Spring Framework – Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): preflight và actual request handling.
- [Spring Framework – MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): HandlerInterceptor callbacks và security caveat.
- [Spring Framework – Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): Servlet filter integration, async dispatcher types.
- [Spring Framework 6.1 – OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): async/error dispatch và once-per-dispatch semantics.
- [Spring Security 6.3 – CORS Servlet Integration](https://docs.spring.io/spring-security/reference/6.3/servlet/integrations/cors.html): preflight cần được xử lý trước authentication.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain.
- [Spring Security – MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): springSecurity() configurer.
- [Spring Security – MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html): user(), httpBasic() và authentication test.
- [Spring Security – Testing with CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): with(csrf()) và negative tests.
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): requestMatchers, role constraints và fallback.
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Servlet stack and filters.
- [Spring Boot 3.3 – Test Auto-Configuration](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html): slice boundaries.
- [MDN – Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): browser semantics.
- [OWASP – CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF threat model.

**Kết luận:** Muốn kiểm thử web runtime đáng tin cậy, phải biết request bị xử lý ở **tầng nào**. Filter chạy ở Servlet level, Interceptor ở MVC handler level, CORS là chính sách cross-origin của browser và Spring Security giữ trách nhiệm authentication, authorization cùng CSRF. Một preflight được phép **không** đồng nghĩa actual request được phép; một test tắt filters **không** là bằng chứng bảo mật.
