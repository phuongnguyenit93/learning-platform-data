# Lỗi từ Filter không tự được @ControllerAdvice xử lý trong Spring Security

## 1. Hiện tượng thường gặp

Một ứng dụng Spring Boot có bộ xử lý lỗi như sau:

```java
@RestControllerAdvice
class ApiExceptionAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
}
```

Khi `@RestController` ném `IllegalArgumentException`, client nhận HTTP 400 cùng JSON từ advice. Nhưng khi một `Filter` hoặc `OncePerRequestFilter` ném **cùng loại exception**, client có thể thấy HTTP 500, HTML error page, response mặc định của container, hoặc một dispatch đến `/error` thay vì JSON mong muốn.

Đây không phải lỗi “annotation không hoạt động”. Nguyên nhân là **ranh giới pipeline**: `@RestControllerAdvice` thuộc cơ chế giải quyết exception của Spring MVC, trong khi một Servlet Filter chạy **bên ngoài/bao quanh** `DispatcherServlet`. Ngoại lệ ném trước khi vào `DispatcherServlet` không tự chui vào chuỗi `HandlerExceptionResolver` của MVC.

**Quy tắc cần ghi nhớ:**

- Lỗi phát sinh trong **handler/controller của Spring MVC** thường được `DispatcherServlet` giao cho `HandlerExceptionResolver`, nơi `@ExceptionHandler`/`@ControllerAdvice` có thể tham gia.
- Lỗi phát sinh **ngay trong Servlet Filter** không tự được `DispatcherServlet` bắt và chuyển cho advice.
- Lỗi xác thực/phân quyền của **Spring Security** có đường xử lý riêng: `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, hoặc failure handler của bộ lọc xác thực.
- Lỗi chưa được xử lý có thể đi ra **Servlet container**, dẫn đến ERROR dispatch/`/error` hoặc HTTP 500. Đây **không phải bằng chứng** advice đã xử lý exception trực tiếp từ filter.

Bài tập trung Spring Boot 3.x / Spring Security 6.x Servlet (Java 17+). Phần riêng cuối bài nêu khác biệt WebFlux.

## 2. Filter, Spring Security và Controller nằm ở đâu?

Một request Servlet thông thường đi theo thứ tự khái quát:

```text
HTTP client
   |
   v
Servlet container (Tomcat/Jetty/Undertow)
   |
   v
Container FilterChain
   |
   +-- Application Filter A
   |
   +-- DelegatingFilterProxy
   |      |
   |      v
   |   FilterChainProxy (Spring Security)
   |      |
   |      +-- SecurityContextHolderFilter
   |      +-- CsrfFilter / auth filters / ...
   |      +-- ExceptionTranslationFilter
   |      +-- AuthorizationFilter
   |      +-- custom security filters (vị trí theo cấu hình)
   |
   +-- Application Filter B
   |
   v
DispatcherServlet
   |
   +-- HandlerMapping
   +-- HandlerAdapter
   +-- @Controller / @RestController
   |      |
   |      +-- Có exception trong MVC handling?
   |             |
   |             v
   |       HandlerExceptionResolver chain
   |             |
   |             +-- ExceptionHandlerExceptionResolver
   |             |       -> @ExceptionHandler / @ControllerAdvice
   |             +-- ResponseStatusExceptionResolver
   |             +-- DefaultHandlerExceptionResolver
   |
   v
HTTP response
```

Đây là sơ đồ vai trò, **không phải cam kết về thứ tự chính xác mọi security filter**: chuỗi thực tế phụ thuộc config, Spring Security version, các matcher và cách chèn filter. Kiểm tra `FilterChainProxy` logs hoặc introspection của `SecurityFilterChain` nếu đang debug thứ tự.

### Một ngoại lệ có thể đi qua nhiều ranh giới

Một controller ném `IllegalArgumentException`:

```text
Controller throw
   -> DispatcherServlet catches
   -> HandlerExceptionResolver
   -> @RestControllerAdvice
   -> JSON 400
```

Một custom filter ném `IllegalArgumentException` **trước khi gọi** `chain.doFilter(...)`:

```text
Custom Filter throw
   -> DispatcherServlet chưa được gọi
   -> MVC HandlerExceptionResolver KHÔNG được tự kích hoạt
   -> lỗi nổi lên FilterChain/container
   -> container error handling (tùy cấu hình)
```

Một filter bọc `chain.doFilter` cũng có thể nhận exception nổi ngược từ controller; nhưng khi exception đã được MVC resolver xử lý, nó thường **không còn exception để nổi ra filter**. Ngược lại, một filter không nên dựa vào cơ chế MVC để tự động xử lý lỗi do chính filter đó ném.

## 3. HandlerExceptionResolver thực sự làm gì?

Spring MVC giải quyết exception thông qua các `HandlerExceptionResolver`. Những implementation hay gặp:

| Thành phần | Công dụng |
| --- | --- |
| `ExceptionHandlerExceptionResolver` | Gọi `@ExceptionHandler` tại controller hoặc `@ControllerAdvice` |
| `ResponseStatusExceptionResolver` | Ánh xạ exception gắn `@ResponseStatus` hoặc `ResponseStatusException` trong ngữ cảnh MVC |
| `DefaultHandlerExceptionResolver` | Chuyển các lỗi MVC chuẩn sang HTTP status thích hợp |
| `HandlerExceptionResolverComposite` | Tổ chức chuỗi các resolver theo cấu hình |

`@RestControllerAdvice` kết hợp `@ControllerAdvice` và `@ResponseBody`; nó áp dụng cho **MVC exception resolution**, không phải servlet container exception handler toàn cục. `@ExceptionHandler(Exception.class)` không phải phép “try/catch mọi nơi trong JVM”.

Ví dụ:

```java
@RestController
class ExampleController {
    @GetMapping("/api/from-controller")
    String fail() {
        throw new IllegalArgumentException("invalid business field");
    }
}

@RestControllerAdvice
class ExampleAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> bad(IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "MVC_BAD_REQUEST"));
    }
}
```

Khi request **đến được handler MVC** và exception được resolver này hỗ trợ, client nhận HTTP 400. Điều đó không suy ra `@RestControllerAdvice` sẽ bắt lỗi ở `Filter#doFilter`.

**Một nuance quan trọng:** nếu exception được ném *trong controller/method security*, một `@ControllerAdvice` quá rộng như `@ExceptionHandler(Exception.class)` đôi khi có thể **bắt cả lỗi security** trước khi nó kịp nổi tới `ExceptionTranslationFilter`. Tránh nuốt `AuthenticationException`/`AccessDeniedException` rồi biến thành lỗi 500 vô nghĩa. Thiết kế rõ ranh giới giữa exception nghiệp vụ và lỗi xác thực/ủy quyền.

## 4. Spring Security xử lý 401/403 ở lớp Filter như thế nào?

Spring Security Servlet có `ExceptionTranslationFilter`. Theo hợp đồng của nó, filter này chuyển `AuthenticationException` và `AccessDeniedException` **được ném từ phần chuỗi xử lý mà nó bao bọc** thành hành vi HTTP.

```text
ExceptionTranslationFilter
     |
     +-- chain.doFilter(request, response)
             |
             +-- Downstream AuthorizationFilter
             +-- Downstream MVC / method security
             +-- Các filters nằm SAU ExceptionTranslationFilter
     |
     +-- catch AuthenticationException
     |       -> AuthenticationEntryPoint.commence(...)
     |
     +-- catch AccessDeniedException
             |
             +-- user chưa authenticated/anonymous?
             |       -> AuthenticationEntryPoint
             |
             +-- user đã authenticated nhưng thiếu quyền?
                     -> AccessDeniedHandler.handle(...)
```

Điểm mấu chốt: `ExceptionTranslationFilter` không bọc được **filter chạy phía trước nó**, vì exception từ filter phía trước phát sinh trước khi control đi vào lời gọi `chain.doFilter` của nó. Nó cũng **không phải generic exception handler** cho mọi `RuntimeException`, `IOException` hoặc lỗi DB.

### AuthenticationEntryPoint và AccessDeniedHandler

| Tình huống | Thành phần thích hợp | HTTP thường dùng |
| --- | --- | --- |
| Request tới tài nguyên protected nhưng chưa xác thực | `AuthenticationEntryPoint` | 401 JSON/Bearer challenge hoặc redirect login (browser) |
| Authentication không hợp lệ | Entry point hoặc `AuthenticationFailureHandler` tùy filter | 401 hoặc response theo login flow |
| User đã xác thực nhưng thiếu quyền | `AccessDeniedHandler` | 403 |
| Controller input sai | `@ControllerAdvice`/`HandlerExceptionResolver` | 400/422 theo contract |
| Custom filter từ chối header/request | Filter-local handler, writer hoặc resolver bridge | 400/401/403 tùy bản chất |
| Filter ném `NullPointerException` | Không nên đổi thành 401/403 | 500 + log nội bộ, không lộ stack trace |
| CSRF từ `CsrfFilter` | Xem handler của chính `CsrfFilter` và chain hiện hành | Thường 403 |
| Reject URL bởi `StrictHttpFirewall` | `RequestRejectedHandler`/container layer | Thường 400 theo handler đã cấu hình |

**Không coi mọi lỗi ở filter là 401.** 401 nói về **chưa/cannot authenticate**, trong khi 403 nói về **authenticated nhưng bị từ chối vì authorization** (có ngoại lệ anonymous/cơ chế browser), 400 nói về request client sai, 500 là lỗi server không mong đợi.

### Phân biệt ba “failure hook”

- `AuthenticationEntryPoint` khởi đầu quá trình xác thực khi request chưa được authenticated hoặc security error cần challenge.
- `AuthenticationFailureHandler` thường thuộc filter **thực hiện login**, ví dụ `UsernamePasswordAuthenticationFilter`, để xử lý login/password sai. Lỗi này có thể bị filter bắt trước khi tới `ExceptionTranslationFilter`.
- `AccessDeniedHandler` xử lý quyền truy cập bị từ chối đối với user đã authenticated trong phạm vi tương ứng.

Trong hệ thống API Bearer, Spring Security có handlers chuẩn RFC 6750 như `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler`; không thay bằng JSON tự viết mà làm mất các header `WWW-Authenticate` có ý nghĩa giao thức.

## 5. Filter order: vì sao addFilterBefore có thể thay đổi kết quả?

Giả sử:

```java
http.addFilterBefore(customFilter, UsernamePasswordAuthenticationFilter.class);
```

Ở thứ tự Spring Security Servlet thường gặp, `UsernamePasswordAuthenticationFilter` nằm **trước** `ExceptionTranslationFilter`. Filter custom chèn vào vị trí này, nếu trực tiếp ném `AuthenticationException` hoặc `AccessDeniedException`, không nên mặc định kỳ vọng `ExceptionTranslationFilter` sẽ bắt.

Một số ví dụ gây hiểu nhầm:

```java
// Ví dụ SAI / KHÔNG ĐỦ nếu filter chạy trước ExceptionTranslationFilter:
if (tokenMissing) {
    throw new BadCredentialsException("Missing credential");
}
```

Người lập trình nghĩ rằng “`BadCredentialsException` là `AuthenticationException` nên chắc chắn Spring Security trả 401”. Nhưng **loại exception không đủ quyết định nơi bắt exception**; vị trí filter và code xử lý xung quanh mới quyết định.

Giải pháp đúng thường là:

1. Đối với **bearer token**, dùng filter/configuration resource server chuẩn của Spring Security thay vì tự viết parser.
2. Đối với **authentication flow custom**, dùng `AuthenticationManager`/`AuthenticationEntryPoint` hoặc `AuthenticationFailureHandler` tại ranh giới filter đó.
3. Đối với **validation không phải authentication**, trực tiếp viết 400 có cấu trúc hoặc chủ động gọi `HandlerExceptionResolver` khi muốn reuse cơ chế MVC.
4. Nếu cố tình để exception nổi ra container, dùng error handling chung ở container/`/error`, nhưng phải kiểm tra chính xác dispatch và response schema; đừng coi đó là `@ControllerAdvice` tự bắt.

## 6. Bài tập Java 17: mô phỏng đúng các ranh giới exception

Mục tiêu của ví dụ **thuần Java**, không phụ thuộc Spring: nhìn thấy rõ vì sao cùng một loại lỗi `IllegalArgumentException` có kết quả khác nhau khi phát sinh trong controller hay filter.

Tạo file **`FilterBoundaryDemo.java`**:

```java
public final class FilterBoundaryDemo {
    record Result(int status, String source) {}

    static final class Unauthenticated extends RuntimeException {}
    static final class Forbidden extends RuntimeException {}

    // Container là ranh giới cuối: lỗi lọt ra sẽ trở thành lỗi chung.
    static Result container(String path, boolean authenticated, boolean admin) {
        try {
            return outerFilter(path, authenticated, admin);
        } catch (RuntimeException ex) {
            return new Result(500, "CONTAINER_ERROR");
        }
    }

    // Filter bên ngoài DispatcherServlet và security translator.
    static Result outerFilter(String path, boolean authenticated, boolean admin) {
        if (path.equals("/filter-error")) {
            throw new IllegalArgumentException("bad value before MVC");
        }
        return securityBoundary(path, authenticated, admin);
    }

    // Mô phỏng ExceptionTranslationFilter; không phải implementation Spring.
    static Result securityBoundary(
            String path, boolean authenticated, boolean admin) {
        try {
            if (!authenticated) {
                throw new Unauthenticated();
            }
            if (path.equals("/admin") && !admin) {
                throw new Forbidden();
            }
            return dispatcherServlet(path);
        } catch (Unauthenticated ex) {
            return new Result(401, "AUTH_ENTRY_POINT");
        } catch (Forbidden ex) {
            return new Result(403, "ACCESS_DENIED_HANDLER");
        }
    }

    // Mô phỏng DispatcherServlet + MVC HandlerExceptionResolver.
    static Result dispatcherServlet(String path) {
        try {
            if (path.equals("/mvc-error")) {
                throw new IllegalArgumentException("bad controller input");
            }
            return new Result(200, "CONTROLLER");
        } catch (IllegalArgumentException ex) {
            return new Result(400, "MVC_CONTROLLER_ADVICE");
        }
    }

    private static void show(String label, Result result) {
        System.out.println(label + "="
                + result.status() + ":" + result.source());
    }

    public static void main(String[] args) {
        show("controllerException",
                container("/mvc-error", true, false));
        show("filterException",
                container("/filter-error", true, false));
        show("missingAuthentication",
                container("/hello", false, false));
        show("missingRole",
                container("/admin", true, false));
        show("success",
                container("/hello", true, false));
    }
}
```

Chạy với JDK 17+:

```bash
javac FilterBoundaryDemo.java
java FilterBoundaryDemo
```

**Stdout xác định:**

```text
controllerException=400:MVC_CONTROLLER_ADVICE
filterException=500:CONTAINER_ERROR
missingAuthentication=401:AUTH_ENTRY_POINT
missingRole=403:ACCESS_DENIED_HANDLER
success=200:CONTROLLER
```

**Ý nghĩa của từng dòng:**

- `controllerException`: exception ném bên trong mô hình DispatcherServlet và được resolver biến thành 400.
- `filterException`: exception ném trước DispatcherServlet; không đi vào MVC advice nên nổi tới container.
- `missingAuthentication`: security boundary nhận diện authentication cần thiết và gọi entry point 401.
- `missingRole`: đã authenticated nhưng thiếu role, handler trả 403.
- `success`: request đi qua các lớp mà không có exception.

Đây là **mô hình giáo dục**, không dùng interface `jakarta.servlet.Filter` hay class Spring Security thật. Việc mô phỏng không chứng minh mọi URL, filter placement hoặc status mặc định trên Spring Boot; phần dưới dùng cấu hình framework thực.

## 7. Dự án Spring Boot 3.x minh họa các loại lỗi thật

Ta xây một ứng dụng Servlet tối thiểu có:

- `/api/controller-error`: ném `IllegalArgumentException` **trong controller**, do `@RestControllerAdvice` xử lý.
- `/api/filter-error`: bị **custom filter** chặn và tự trả JSON 400.
- `/api/hello`: yêu cầu HTTP Basic authentication; thiếu credential trả JSON 401 từ `AuthenticationEntryPoint`.
- `/api/admin`: yêu cầu role ADMIN; người dùng bình thường nhận JSON 403 từ `AccessDeniedHandler`.
- `/api/public`: truy cập công khai.

**Lưu ý:** HTTP Basic + user in-memory với password minh họa chỉ dùng môi trường học/test. Production phải sử dụng encoder an toàn, HTTPS, lưu credential bảo vệ và cơ chế authentication phù hợp.

### 7.1. Gradle dependencies

Trong project Spring Boot **3.x**, Java 17+ đã cấu hình Spring Boot/Dependency Management plugin đúng phiên bản, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không thêm `spring-boot-starter-webflux` vào project này chỉ để tái sử dụng các snippet; đây là **Servlet/MVC**. Dùng Jakarta Servlet (`jakarta.servlet.*`), không dùng `javax.servlet.*` khi chạy Spring Boot 3.x.

### 7.2. Ứng dụng chính

File **`src/main/java/demo/boundary/FilterBoundaryApplication.java`**:

```java
package demo.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterBoundaryApplication.class, args);
    }
}
```

### 7.3. Controller và MVC advice

File **`src/main/java/demo/boundary/ApiController.java`**:

```java
package demo.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/hello")
    String hello() {
        return "hello";
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }

    @GetMapping("/api/controller-error")
    String controllerError() {
        throw new IllegalArgumentException("invalid request parameter");
    }
}
```

File **`src/main/java/demo/boundary/ApiExceptionAdvice.java`**:

```java
package demo.boundary;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        // Không trả ex.getMessage() tùy tiện để tránh lộ nội bộ.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "MVC_BAD_REQUEST"));
    }
}
```

Advice này có **global MVC scope**. Nó chỉ bắt `IllegalArgumentException` khi MVC exception resolution được kích hoạt; không có cơ chế tự động nối exceptions từ mọi Filter.

### 7.4. Custom Filter tự xử lý lỗi đúng trách nhiệm

File **`src/main/java/demo/boundary/EarlyFailureFilter.java`**:

```java
package demo.boundary;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class EarlyFailureFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if ("/api/filter-error".equals(request.getServletPath())) {
            // Filter chủ động phản hồi, KHÔNG ném exception với hy vọng
            // @ControllerAdvice sẽ tự xử lý.
            ApiSecurity.json(response, 400, "FILTER_REJECTED");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Tại sao trả response trực tiếp:

- Filter biết điều kiện request nào bị từ chối và loại lỗi đang xử lý.
- `ApiSecurity.json(...)` đặt status/Content-Type/no-store và một mã lỗi ổn định, tránh lộ thông tin nhạy cảm.
- `return` ngay sau khi tạo response để **không chạy tiếp controller**. Không vừa write rồi vừa gọi `chain.doFilter`.
- Filter không được gắn `@Component` trong ví dụ: nó sẽ được tạo **một lần trong `SecurityFilterChain`** để tránh đồng thời bị tự động đăng ký vào servlet container và chèn vào security chain. Đăng ký hai chỗ có thể gây thứ tự bất ngờ hoặc gọi hai lần.

Trong production, không phải mọi lỗi phát sinh từ Filter đều là 400: phân loại chính xác và chuyển cho handler có trách nhiệm khi liên quan authentication, CSRF, rate-limit, firewall hoặc lỗi server.

### 7.5. SecurityFilterChain và entry point/denied handler

File **`src/main/java/demo/boundary/ApiSecurity.java`**:

```java
package demo.boundary;

import java.io.IOException;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration(proxyBeanMethods = false)
public class ApiSecurity {

    static void json(HttpServletResponse response, int status, String code)
            throws IOException {
        if (response.isCommitted()) {
            return; // phải ghi log nội bộ; đã quá muộn để đổi HTTP response
        }
        response.setStatus(status);
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json");
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        // Code là giá trị HẰNG DO SERVER CHỌN trong ví dụ này.
        response.getWriter().write("{\"code\":\"" + code + "\"}");
    }

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {

        AuthenticationEntryPoint unauthenticated = (request, response, ex) -> {
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo-api\"");
            json(response, 401, "UNAUTHENTICATED");
        };

        AccessDeniedHandler forbidden = (request, response, ex) ->
                json(response, 403, "FORBIDDEN");

        return http
                .authorizeHttpRequests(auth -> auth
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        .requestMatchers("/api/public", "/api/filter-error")
                            .permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(unauthenticated))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(unauthenticated)
                        .accessDeniedHandler(forbidden))
                .addFilterBefore(new EarlyFailureFilter(),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}alice-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("root")
                        .password("{noop}root-pass")
                        .roles("ADMIN")
                        .build());
    }
}
```

**Giới hạn cấu hình:**

- Đây là ví dụ HTTP **GET-only**, vì vậy không minh họa gửi CSRF tokens. Spring Security vẫn bật CSRF mặc định; **không** tự `csrf.disable()` cho browser HTTP Basic chỉ vì API có JSON, bởi browser vẫn có thể tự gửi Basic credentials cho site.
- Password `{noop}` chỉ để test. Sử dụng BCrypt/Argon2/PBKDF2 theo policy và secret management đúng khi triển khai thật.
- `DispatcherType.ERROR` được phép qua authorization rule để container có thể đi đến error dispatch khi cần; không biến `/error` thành nơi lộ stack trace. Kiểm tra filter registrations với dispatcher types trên container thật.
- `AuthenticationEntryPoint` có header `WWW-Authenticate: Basic ...` đúng ngữ cảnh HTTP Basic; không dùng header Basic cho bearer JWT. Hai phương thức có protocol challenge khác nhau.
- `HttpSecurity.exceptionHandling(...)` cấu hình đường lỗi authentication/authorization thuộc scope bảo vệ phù hợp; nó **không** là handler tổng quát cho `NullPointerException` từ custom filter.
- Filter `EarlyFailureFilter` được đặt trước `UsernamePasswordAuthenticationFilter`; trong trường hợp nó **tự ném** một exception và không có handler tại chỗ, không dựa vào `ExceptionTranslationFilter` phía sau để bắt.
- Nếu cần session/form login, CORS, OAuth2 login hoặc resource server, phải điều chỉnh các chuỗi filter và entry point theo flow đó; không bật nhiều cơ chế trái ngữ cảnh rồi mong tất cả trả cùng một lỗi.
- Trong hệ thống nhiều `SecurityFilterChain`, thứ tự `@Order` và `securityMatcher` quyết định chain được chọn. Một request chỉ đi qua chain phù hợp đầu tiên; **không** đương nhiên qua mọi chain.

## 8. Kết quả HTTP mong đợi khi chạy demo Spring Boot

Chạy ứng dụng:

```bash
./gradlew bootRun
```

Trong Windows:

```powershell
./gradlew.bat bootRun
```

Kiểm thử các URL:

```bash
# Public endpoint
curl -i http://localhost:8080/api/public

# Chưa xác thực: entry point
curl -i http://localhost:8080/api/hello

# User có role USER, nhưng endpoint đòi ADMIN
curl -i -u alice:alice-pass http://localhost:8080/api/admin

# MVC error: advice xử lý
curl -i -u alice:alice-pass http://localhost:8080/api/controller-error

# Filter error: Filter tự trả JSON 400
curl -i http://localhost:8080/api/filter-error

# User đủ quyền
curl -i -u root:root-pass http://localhost:8080/api/admin
```

Các status và response body tương ứng:

| Endpoint | Authentication | Status | Body tiêu biểu | Nguồn xử lý |
| --- | --- | --- | --- | --- |
| `/api/public` | Không cần | 200 | `public` | Controller |
| `/api/hello` | Không có | 401 | `{"code":"UNAUTHENTICATED"}` | AuthenticationEntryPoint |
| `/api/admin` | alice/USER | 403 | `{"code":"FORBIDDEN"}` | AccessDeniedHandler |
| `/api/controller-error` | alice/USER | 400 | `{"code":"MVC_BAD_REQUEST"}` | @RestControllerAdvice |
| `/api/filter-error` | Không cần | 400 | `{"code":"FILTER_REJECTED"}` | EarlyFailureFilter |
| `/api/admin` | root/ADMIN | 200 | `admin` | Controller |

Ví dụ HTTP Basic với URL `http://localhost:8080` chỉ dành cho máy local/test. **Không** gửi password qua HTTP công khai: production phải dùng HTTPS. Demo đặt cookie policy/session riêng nếu có browser login; không suy ra code Basic ở trên phù hợp production.

### Vì sao custom Filter có thể trả cùng JSON shape?

Có thể dùng chung **schema lỗi** (ví dụ `code`, `message`, `traceId`, `timestamp`) thông qua một `ErrorResponseWriter` chung; nhưng **chia sẻ format không đồng nghĩa chia sẻ nơi bắt lỗi**. `@ControllerAdvice` xử lý MVC, entry point xử lý auth, denied handler xử lý authorization, filter-specific handler xử lý vấn đề thuộc filter. Các nơi này có thể gọi một hàm serializer chung hoặc dùng `ObjectMapper` được cấu hình thống nhất.

Nếu viết JSON bằng nối chuỗi, **chỉ an toàn với mã cố định do server định nghĩa** như trong demo. Không ghép thẳng `exception.getMessage()`, user input, header hay URL vào JSON; hãy dùng Jackson serializer và whitelist mã lỗi.

## 9. Integration tests dùng MockMvc để chứng minh đường xử lý

Đây là mã test cho ứng dụng vừa tạo, sử dụng `spring-security-test` và `spring-boot-starter-test`. File **`src/test/java/demo/boundary/ApiErrorBoundaryTest.java`**:

```java
package demo.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ApiErrorBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerErrorsUseMvcAdvice() throws Exception {
        mvc.perform(get("/api/controller-error")
                    .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MVC_BAD_REQUEST"));
    }

    @Test
    void filterErrorsUseFilterWriter() throws Exception {
        mvc.perform(get("/api/filter-error"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("FILTER_REJECTED"));
    }

    @Test
    void anonymousRequestsUseAuthenticationEntryPoint() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    }

    @Test
    void authenticatedWithoutRoleUsesAccessDeniedHandler()
            throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void authenticatedAdminCanAccess() throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("root", "root-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.boundary.ApiErrorBoundaryTest
```

Nếu dự án có Spring Boot 3.x, Java 17+, deps đúng và chạy như mã ở trên, **5 tests được kỳ vọng PASS**. Đây là integration-test design đã soát logic và API; môi trường bài học không cung cấp một project Spring Boot/Gradle để compile/test toàn bộ đoạn này. Unit test Java thuần tại mục 6 đã được chạy và xác minh riêng.

**Điều test này thật sự chứng minh:** HTTP status/body khác nhau theo điểm phát sinh exception/handler. Không dùng test này để kết luận mọi filter error toàn hệ thống được MVC advice bắt.

### Một test bổ sung cho lỗi Filter ném exception

Nếu tạm thay implementation filter thành:

```java
if ("/api/filter-error".equals(request.getServletPath())) {
    throw new IllegalArgumentException("thrown before DispatcherServlet");
}
```

thì test `filterErrorsUseFilterWriter()` không còn đúng: Filter không gọi writer nữa. Kết quả có thể thành servlet container ERROR dispatch tới `/error`, lỗi 500 hoặc biểu diễn theo environment. **Không khẳng định chính xác mọi container đều trả cùng body**, vì phụ thuộc đăng ký error pages, dispatcher types, Boot error handling và response commitment.

Trong test thực tế, có thể gắn spy/counter vào `@RestControllerAdvice` để chứng minh handler này **không được gọi trực tiếp** cho exception Filter; kiểm tra error dispatch riêng nếu cần.

## 10. Có thể chủ động đưa lỗi Filter vào HandlerExceptionResolver không?

Có — nhưng đây là **hành động tường minh**, không phải Spring tự nối hai pipeline.

Một filter có thể inject bean `HandlerExceptionResolver` đúng của MVC và **gọi `resolveException(request, response, handler, exception)`**. Một global `@RestControllerAdvice` có thể được sử dụng qua `ExceptionHandlerExceptionResolver` nếu exception phù hợp và resolver được cấu hình đúng.

Ví dụ **đoạn Filter minh họa**:

```java
public final class MvcDelegatingValidationFilter extends OncePerRequestFilter {

    private final HandlerExceptionResolver resolver;

    public MvcDelegatingValidationFilter(HandlerExceptionResolver resolver) {
        this.resolver = resolver;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if ("/api/invalid-header".equals(request.getServletPath())) {
            IllegalArgumentException problem =
                    new IllegalArgumentException("invalid header");

            if (response.isCommitted()) {
                return; // log nội bộ: không thể thay đổi response
            }

            ModelAndView handled =
                    resolver.resolveException(request, response, null, problem);

            if (handled == null && !response.isCommitted()) {
                response.setStatus(400);
                response.setContentType("application/json");
                response.getWriter().write("{\"code\":\"FILTER_BAD_REQUEST\"}");
            }
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Cần imports: `jakarta.servlet.FilterChain`, `jakarta.servlet.ServletException`, `jakarta.servlet.http.HttpServletRequest`, `jakarta.servlet.http.HttpServletResponse`, `java.io.IOException`, `org.springframework.web.filter.OncePerRequestFilter`, `org.springframework.web.servlet.HandlerExceptionResolver` và `org.springframework.web.servlet.ModelAndView`.

Inject bean MVC qua `@Qualifier("handlerExceptionResolver")` khi cấu hình nó; đừng tự tạo một resolver rỗng rồi kỳ vọng mọi advice có mặt. `handler=null` vì Filter có thể chưa có MVC handler được chọn; advice có selector giới hạn theo controller/package/annotation có thể không khớp. `resolveException(...)` trả `null` nghĩa là resolver **không xử lý được**. Nếu handler đã ghi response, gọi lại resolver không an toàn.

### Khi nào KHÔNG nên dùng resolver bridge?

- Lỗi **authentication/authorization**: dùng `AuthenticationEntryPoint`/`AccessDeniedHandler` hoặc authentication failure hook để giữ đúng giao thức.
- Lỗi **StrictHttpFirewall/RequestRejectedException**: có handler riêng ở tầng firewall.
- Filter có response đã committed hoặc streaming: resolver không thể “quay ngược” bytes đã gửi.
- Filter chạy trên request không đi tới MVC, ví dụ static resources, non-MVC servlet, một số ERROR/ASYNC dispatch: lời gọi advice có thể không có cùng ngữ cảnh và phụ thuộc resolver implementation.
- Để che một bug ở filter: nên sửa exception handling tại nguồn, không nuốt mọi `Exception` thành HTTP 400.

**Ưu tiên:** chia sẻ `ErrorResponseWriter`/`ErrorResponse DTO` để thống nhất JSON, nhưng giữ **đúng handler cho đúng lớp**. Resolver bridge chỉ dùng khi có lý do rõ ràng và được integration-test.

## 11. Lỗi đăng nhập cần AuthenticationFailureHandler riêng

Một request đi qua `UsernamePasswordAuthenticationFilter` có thể fail vì sai mật khẩu, tài khoản bị khóa hoặc tài khoản không tồn tại. Filter đăng nhập **thường bắt lỗi authentication của chính nó** rồi gọi `AuthenticationFailureHandler`, không đợi `@ControllerAdvice`.

Ví dụ browser app có form login:

```java
http.formLogin(form -> form
        .failureHandler((request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"code\":\"LOGIN_FAILED\"}");
        }));
```

Đây là mảnh cấu hình cho Servlet `HttpSecurity`, không phải code thay thế toàn bộ `SecurityFilterChain` trong project Basic ở mục 7. Nếu là browser form, redirect đến `/login?error` có thể tốt hơn JSON; nếu là API, JSON có thể thích hợp. Luôn giới hạn chi tiết lỗi để tránh **username enumeration**, không trả “user không tồn tại” và “sai password” khác nhau không cần thiết.

**Phân biệt:**

- Đăng nhập không thành công: filter login có thể gọi failure handler.
- Request chưa đăng nhập đến URL protected: `AuthenticationEntryPoint`.
- User đăng nhập hợp lệ nhưng không có quyền: `AccessDeniedHandler`.
- Lỗi dữ liệu hợp lệ ở controller: `@RestControllerAdvice`.
- Lỗi custom filter xảy ra trước các handler kia: bộ xử lý của **chính filter** hoặc bridge có chủ đích.

## 12. 401, 403, 400 và 500: đừng nhầm HTTP status

**401 Unauthorized** thường nghĩa là cần authentication hoặc credential không đủ/hợp lệ. Với HTTP Basic cần `WWW-Authenticate: Basic ...`; với bearer token theo OAuth 2.0 RFC 6750 có `WWW-Authenticate: Bearer ...`. Tùy browser flow có thể redirect login thay vì 401.

**403 Forbidden** thường nghĩa là đã authenticated nhưng không được phép. Tuy nhiên với anonymous user và lỗi `AccessDeniedException`, `ExceptionTranslationFilter` có thể chọn entry point (401/redirect) thay vì trả 403. CSRF failure cũng thường 403 nhưng được xử lý ở vị trí khác trong chain.

**400 Bad Request** cho đầu vào không hợp lệ, ví dụ header định dạng sai do custom validation. Không biến lỗi null pointer hoặc DB connection thành 400; đó là lỗi server.

**500 Internal Server Error** cho lỗi hệ thống không mong đợi. Cần log correlation ID nội bộ, không trả stack trace, SQL, secrets hoặc tên class exception cho client.

### Hợp đồng JSON lỗi

Ví dụ dạng chung:

```json
{
  "code": "UNAUTHENTICATED",
  "message": "Authentication is required",
  "traceId": "safe-correlation-id"
}
```

Các giá trị này do server tạo và không chứa username/password/token/stack trace. Nếu ứng dụng dùng Spring `ProblemDetail` theo RFC 9457, có thể thống nhất cấu trúc `application/problem+json` nhưng mỗi tầng vẫn phải chủ động render đúng hoặc ủy quyền cho một writer được dùng chung. Đừng viết content type `application/problem+json` rồi phát một body không đúng cấu trúc Problem Details.

## 13. Những ngoại lệ đặc biệt ở tầng bảo mật

### 13.1. CsrfFilter

`CsrfFilter` có thể xử lý một `AccessDeniedException` do CSRF token thiếu/sai thông qua handler riêng theo cấu hình. Nó nằm trong chuỗi security filters, nhưng **không nên giả định mọi lỗi CSRF đều đi tới `ExceptionTranslationFilter`**. Khi cần JSON 403 nhất quán, xem đúng cơ chế `CsrfFilter`/`AccessDeniedHandler` và thực hiện integration test `POST` thiếu/sai CSRF token.

Không tắt CSRF chỉ để “sửa” trang lỗi HTML khi frontend mong JSON. Nếu browser gửi session cookie, CSRF vẫn là một nguy cơ thực tế. Trước khi chỉnh handler, xác định đường xử lý thực sự.

### 13.2. StrictHttpFirewall và RequestRejectedException

Spring Security `FilterChainProxy` có thể dùng `StrictHttpFirewall` để từ chối các request URL bất thường trước khi đi qua bộ lọc thông thường. `RequestRejectedException` có đường xử lý riêng thông qua `RequestRejectedHandler`/cấu hình container. Nó có thể xảy ra **trước MVC và trước cả ExceptionTranslationFilter**, nên không trông chờ `@ControllerAdvice` hoặc global `.exceptionHandling(...)` tự biến nó thành JSON 400.

Không nới firewall tùy tiện chỉ vì một URL bị reject; kiểm tra encode/path traversal/semicolons và contract routing.

### 13.3. Authentication filters tự bắt lỗi

Các bộ lọc như `UsernamePasswordAuthenticationFilter` và `BearerTokenAuthenticationFilter` có thể tự xử lý thất bại xác thực theo contract của chúng. Với OAuth2 resource server, ưu tiên cấu hình `oauth2ResourceServer(jwt/opaque)` và các entry point/denied handlers chuẩn; không bắt tràn lan `AuthenticationException` rồi thay response mà làm mất `WWW-Authenticate` hoặc mã `invalid_token`.

### 13.4. Method security từ controller/service

`@PreAuthorize` có thể gây `AccessDeniedException` trong quá trình gọi method qua MVC. Nếu advice của bạn tự bắt `Exception.class`, nó có thể chặn việc exception nổi ra tới `ExceptionTranslationFilter`. Tránh generic exception handler làm mất 403. Nếu muốn thống nhất JSON lỗi, dùng đường security exception handling có chủ đích và test thật.

### 13.5. Lỗi từ OncePerRequestFilter

`OncePerRequestFilter` giúp tránh lặp lại việc filter thi hành trên một số dispatch tùy cấu hình, **không** tạo một vùng `try/catch` biến tất cả lỗi thành MVC advice. Với ASYNC/ERROR dispatch, quyết định có chạy lại filter hay không còn phụ thuộc dispatcher registration và các phương thức như `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()`. Nếu response đã committed, không cố tạo body lỗi lần thứ hai.

## 14. ERROR dispatch, BasicErrorController và /error

Khi một exception **không được xử lý** trong filter hoặc servlet, Servlet container có thể thực hiện một **ERROR dispatch** đến đường cấu hình như `/error`. Spring Boot MVC thường có `BasicErrorController` hoặc cơ chế error handling tương đương tại đường đó.

```text
Filter throw unhandled exception
   |
   v
Servlet container
   |
   +-- Error page mapping
           |
           +-- ERROR dispatch tới /error
                 |
                 v
             DispatcherServlet
                 |
                 v
             BasicErrorController / custom ErrorController
```

Điểm quan trọng là **error dispatch là request phase khác**; nó không chứng minh exception ban đầu được `@RestControllerAdvice` bắt trực tiếp trong `Filter#doFilter`. Error page có thể là JSON/HTML tùy Accept header, Boot config, auth, container, cách response đã được commit.

Các lỗi hay gặp:

- `/error` cũng bị Spring Security yêu cầu authenticated, dẫn đến **401/403 thay vì lỗi gốc**.
- Filter custom chạy lại trên ERROR dispatch rồi ném thêm exception.
- Response đã ghi một phần body rồi lỗi, container không thể thay hoàn toàn response.
- App tự gọi `sendError` và sau đó tiếp tục ghi body; kết quả khác nhau tùy container.

**Khi debug**, kiểm tra `DispatcherType.REQUEST`/`ERROR`, đường URL, filter chain được chọn, content committed state, và log stack trace của **exception gốc**, không chỉ nhìn status cuối cùng.

## 15. Khi response đã committed, không thể sửa lỗi như chưa có gì xảy ra

`HttpServletResponse.isCommitted()` cho biết status/headers đã được gửi ra client hoặc bị flush. Nếu một filter phía sau ném exception sau khi response đã committed, rất khó đổi từ 200 sang JSON 500 hoặc 401.

Quy tắc:

1. Kiểm tra điều kiện bắt buộc trước khi bắt đầu streaming/downloading response.
2. Không ghi JSON lỗi **sau** khi đã gửi một phần CSV, ZIP, file, SSE hoặc response stream.
3. Nếu có thể, dùng shared error writer **trước khi commit**.
4. Sau commit, chủ yếu log và kết thúc/kết nối bị đóng theo server; xử lý lại ở client nếu protocol hỗ trợ.
5. Tránh `response.reset()` vô điều kiện; sau commit có thể gây `IllegalStateException` và làm nhiễu lỗi gốc.

Với `sendError(status)`, container có thể kích hoạt error page handling; với `setStatus(status)` + body, ứng dụng có thể tự chịu trách nhiệm output. Hai phương pháp không phải lúc nào cũng tương đương về ERROR dispatch.

## 16. Filter registration và order là một phần của correctness

Có hai cách đăng ký custom Servlet Filter thông dụng:

1. **Container-level Filter** thông qua `@Component`, `@WebFilter` hoặc `FilterRegistrationBean`; nó chạy trong servlet container filter chain.
2. **Security filter** thêm qua `HttpSecurity.addFilterBefore/After/At(...)` và tham gia `FilterChainProxy`.

Đừng vô tình đăng ký cùng một filter bằng cả hai cách nếu không có chủ đích. Điều này làm thứ tự phức tạp và có thể gây lặp việc xác thực, ghi response hai lần hoặc gây khó khi debug request dispatch. `OncePerRequestFilter` không phải phương pháp sửa hoàn chỉnh cho lỗi double registration.

**Kiểm tra đúng nơi đặt filter:**

- Bộ lọc đọc credential riêng cần phối hợp với `AuthenticationManager` và failure handling phù hợp.
- Bộ lọc kiểm tra correlation ID/logging thường nên không tự đưa ra quyết định authentication.
- Bộ lọc validation sơ bộ cần trả lỗi đúng status và có kiểm tra response committed.
- Bộ lọc authorization tùy biến thường nên dùng `AuthorizationManager`/method security trước khi tự viết filter có quy tắc riêng.
- Bộ lọc ở ngoài `FilterChainProxy` không thể trông đợi `ExceptionTranslationFilter` xử lý exception của nó.

Cấu hình logging hỗ trợ:

```yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security: INFO
```

Khi cần trace sâu hơn, bật logging ngắn hạn tại môi trường test và **redact token/cookie/password**; không bật TRACE vô hạn trên production vì có thể lộ request metadata nhạy cảm.

## 17. WebFlux: cùng nguyên lý, khác API xử lý

Spring WebFlux không dùng `DispatcherServlet`/`HttpSecurity`. Nó có pipeline WebFilter, `WebExceptionHandler`, `DispatcherHandler`, `ServerHttpSecurity`, `SecurityWebFilterChain` và các exception-handling components riêng.

Ví dụ tương đương:

| Servlet/MVC | Reactive WebFlux |
| --- | --- |
| `Filter` / `OncePerRequestFilter` | `WebFilter` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| `SecurityContextHolder` dựa ThreadLocal | `ReactiveSecurityContextHolder` |
| `HandlerExceptionResolver` | Exception handling ở WebFlux stack và reactive error handlers |
| `HttpServletResponse` | `ServerHttpResponse` |

`@RestControllerAdvice` trong WebFlux được dùng khi xử lý exception trong controller/handler qua cơ chế WebFlux; nó cũng **không phải global try/catch cho mọi WebFilter**. Dùng `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` và `WebExceptionHandler` đúng lớp, tránh ép code Servlet vào reactive pipeline.

Với `Mono/Flux`, lỗi có thể xuất hiện **sau** khi handler return và downstream bắt đầu subscribe; phải hiểu các operators `onErrorResume`, transaction và committed response để không xuất status/body sai. Không gọi `block()` trong event-loop chỉ để biến lỗi thành response đồng bộ.

## 18. Ma trận chẩn đoán nhanh

| Triệu chứng | Kiểm tra đầu tiên | Cách sửa đúng lớp |
| --- | --- | --- |
| Controller throw, advice trả JSON mong muốn | Mapping và resolver đã đúng | Giữ advice cho MVC errors |
| Filter throw, advice không chạy | Exception có ném trước `DispatcherServlet` không? | Filter writer, entry point, failure handler hoặc resolver bridge |
| Thiếu login mà nhận HTML thay vì JSON | Entry point nào đang active? `formLogin` hay Basic/Bearer? | Chọn entry point cho API, giữ protocol headers |
| User có login nhưng endpoint trả 401 thay 403 | Anonymous state/Authentication type/entrypoint? | Kiểm tra security context và authorization |
| Login password sai nhưng không vào global advice | Login filter xử lý lỗi nội bộ | `AuthenticationFailureHandler` |
| 403 CSRF không giống JSON denied handler | `CsrfFilter` handler và position | Chỉnh đúng CSRF handler/SPA token flow |
| 400 firewall không đi qua MVC | `StrictHttpFirewall`, `RequestRejectedHandler` | Dùng handler đúng tầng, không tắt firewall bừa bãi |
| 500 tại `/error`, không thấy exception gốc | Container ERROR dispatch | Đọc stack gốc và dispatcher type, tránh chặn /error |
| Filter ném exception trong lúc stream | `response.isCommitted()` | Kiểm tra trước streaming, log và abort đúng cách |
| Một request ghi response hai lần | Filter gọi `chain.doFilter` sau khi write? | `return` ngay sau khi trả lỗi |
| Filter chạy hai lần | Vừa `@Component` vừa `addFilterBefore`? | Chọn một registration |
| Security exception bị advice đổi thành 500 | Có generic `@ExceptionHandler(Exception.class)`? | Không nuốt lỗi xác thực/phân quyền |
| Controller test pass nhưng production filter test fail | MockMvc có chạy FilterChain thật không? | Dùng `@AutoConfigureMockMvc` và cấu hình production |
| Bearer error bị mất header | Custom entry point có ghi đè? | Dùng Bearer handlers chuẩn RFC 6750 |
| Async/ERROR dispatch bị filter xử lý sai | DispatcherType/OncePerRequestFilter hooks | Điều chỉnh filter dispatch đúng yêu cầu |

### Quy trình debug theo từng bước

1. Ghi lại **request method + URL + authenticated state** trong môi trường test, không thu thập credentials raw.
2. Xác định exception đầu tiên được ném ở **Filter**, **SecurityFilterChain**, **DispatcherServlet**, controller hay service.
3. Xác định filter order và handler thực sự gọi: `EntryPoint`, `AccessDeniedHandler`, `FailureHandler`, `HandlerExceptionResolver` hay `/error`.
4. Kiểm tra response đã committed trước khi handler viết body hay chưa.
5. Kiểm tra `DispatcherType.REQUEST/ERROR/ASYNC` và khả năng filter được gọi lại.
6. Thực hiện **negative test** cho mỗi lỗi quan trọng.
7. Chuẩn hóa schema JSON bằng helper chung, không ép tất cả vào một `@ControllerAdvice`.
8. Log correlation ID, loại lỗi và route đã ẩn thông tin nhạy cảm; không log exception messages chứa token/password.

## 19. Checklist cho dự án production

- [ ] Có sơ đồ ranh giới `Filter → Spring Security → DispatcherServlet → Controller` đúng với app thực tế.
- [ ] `@RestControllerAdvice` được dùng cho MVC exception, không kỳ vọng nó bắt toàn bộ filter errors.
- [ ] `AuthenticationEntryPoint` xử lý 401/redirect đúng cho browser, Basic hoặc Bearer.
- [ ] `AccessDeniedHandler` xử lý 403 khi user đã authenticated nhưng bị từ chối.
- [ ] Filter đăng nhập có `AuthenticationFailureHandler` đúng flow.
- [ ] Lỗi Filter custom có writer/handler rõ, không ném exception rồi hy vọng advice tự bắt.
- [ ] `HandlerExceptionResolver` bridge (nếu có) được gọi tường minh, có fallback, test cả handler null.
- [ ] Không nuốt `AuthenticationException`/`AccessDeniedException` bằng generic MVC advice.
- [ ] CSRF/firewall errors được xử lý tại đúng layer, không vô hiệu control chỉ vì response lỗi chưa đẹp.
- [ ] Không tạo response lỗi khi `isCommitted()` đã true; không vừa viết vừa gọi `chain.doFilter`.
- [ ] Filter không bị đăng ký hai lần; kiểm tra `REQUEST/ERROR/ASYNC` dispatch.
- [ ] API JSON error không làm mất `WWW-Authenticate` của Basic/Bearer.
- [ ] 400/401/403/500 có semantics chính xác, message không chứa stack trace, token hoặc PII.
- [ ] MockMvc integration tests có đủ controller error, filter error, auth error, denied error và success.
- [ ] Với WebFlux, dùng `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`/`WebExceptionHandler` đúng pipeline reactive.

### Tài liệu chính thức để tra cứu

- Spring Security 6.5 — Servlet Security Architecture và Handling Security Exceptions: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — `ExceptionTranslationFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html
- Spring Security 6.5 — HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — Servlet OAuth2 Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/index.html
- Spring Framework — MVC Exception Handlers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — DispatcherServlet Exception Resolvers và Error Dispatch: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Boot — Error Handling in Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html#error-handling
- Spring Security — Test Support, MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html

**Kết luận:** lỗi ném từ Filter **không tự động đi vào** `@ControllerAdvice`. Với exception MVC, dùng `HandlerExceptionResolver`/advice; với lỗi xác thực và phân quyền của Spring Security, dùng entry point, denied handler hoặc authentication failure handler; với Filter custom, chủ động xử lý tại filter hoặc gọi resolver bridge khi thật sự cần. Hiểu chính xác **vị trí ném exception** và **filter order** mới bảo đảm response đúng status, đúng JSON và không bỏ qua các cơ chế bảo mật.
