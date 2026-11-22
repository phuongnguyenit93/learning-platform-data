# Rà soát bộ lọc Servlet, HttpSession và thư viện chặn luồng khi chuyển sang WebFlux

> **Phạm vi:** Chuyển đổi và gỡ lỗi ứng dụng Spring Security từ Spring MVC/Servlet sang Spring WebFlux (reactive). Mục tiêu là nhận diện những đoạn mã còn phụ thuộc `Filter`, `HttpServletRequest`, `HttpSession` hoặc API I/O blocking; chuyển sang mô hình thực thi, bảo mật và lưu trạng thái phù hợp với WebFlux. Ví dụ sử dụng Java 17+, Spring Boot 3.x/Spring Security 6.x tương thích qua BOM; khi dùng Boot 4+/Security 7+, đối chiếu package và auto-configuration theo phiên bản cụ thể.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt **Servlet Filter Chain** và **WebFlux `WebFilter`/`SecurityWebFilterChain`**, tránh mang nguyên bộ lọc servlet sang ứng dụng reactive.
2. Lập danh sách các điểm phụ thuộc `HttpSession`, `HttpServletRequest`, `SecurityContextHolder` và `ThreadLocal`, rồi quyết định có thực sự cần session hay không.
3. Phân biệt `WebSession`, `ServerSecurityContextRepository` và `ReactiveSecurityContextHolder`; không suy diễn authentication từ thread hiện tại.
4. Tìm các thao tác blocking như JDBC/JPA, `RestTemplate`, `Thread.sleep`, `Future.get`, `Mono.block()`; chọn API non-blocking hoặc cô lập sang `Schedulers.boundedElastic()` khi phải giữ thư viện cũ.
5. Xây dựng cấu hình bảo mật reactive dùng `ServerHttpSecurity`, một `WebFilter` đơn giản, và kiểm thử cả route công khai, route được bảo vệ lẫn hành vi phiên.
6. Khoanh vùng lỗi sau chuyển đổi: filter không chạy, trạng thái `401/403` khác mong đợi, rò thông tin principal, sai CSRF/CORS, chậm event loop hoặc session mất khi scale nhiều instance.

## 2. Hai mô hình thực thi khác nhau ở đâu?

Trong ứng dụng Servlet truyền thống:

```text
HTTP request
   → Servlet container (Tomcat/Jetty/Undertow)
   → javax.servlet.Filter / jakarta.servlet.Filter
   → Spring Security servlet FilterChainProxy
   → DispatcherServlet → MVC Controller
   → blocking service / JDBC / RestTemplate
   → HTTP response
```

Một request thường được gắn với một luồng servlet trong thời gian handler xử lý. Mã cũ hay gọi `HttpServletRequest`, `HttpSession` hoặc lưu ngữ cảnh vào `ThreadLocal` vì giả định đó.

Trong WebFlux:

```text
HTTP request
   → reactive HTTP server (thường Reactor Netty)
   → WebFilter chain
   → Spring Security reactive securityWebFilterChain
   → DispatcherHandler / HandlerFunction
   → Mono/Flux + reactive service / WebClient / R2DBC
   → HTTP response (reactive signals)
```

WebFlux có thể chạy trên một số servlet container qua adapter, nhưng **vẫn sử dụng API WebFlux**. Việc đổi server không làm mã `Filter`/`HttpSession` thành tương đương `WebFilter`/`WebSession`.

Các khác biệt ảnh hưởng trực tiếp tới an toàn và hiệu năng:

- WebFlux dùng **ít event-loop worker threads**; chúng phải xử lý nhiều kết nối, nên không được để một request chặn luồng trong thời gian dài.
- Reactor pipeline có thể chuyển thread qua `publishOn`/`subscribeOn` hoặc khi có asynchronous completion. **Luồng hiện tại không phải identity ổn định của một request**.
- `Mono`/`Flux` là mô tả công việc sẽ được đăng ký chạy; nhiều thao tác thực sự bắt đầu khi subscribe. Cần chú ý việc kiểm tra quyền và xử lý lỗi tại thời điểm subscribe.
- Spring Security cho WebFlux sử dụng `WebFilter` và **Reactor Context** để truyền ngữ cảnh bảo mật, không sử dụng Servlet `FilterChainProxy` hoặc giả định `SecurityContextHolder` chứa identity trên mọi thread.

**Sai lầm dễ gặp:** Sửa return type từ `User` thành `Mono<User>` nhưng bên trong vẫn gọi JPA, `Thread.sleep` hoặc `.block()` trên event loop. Mã như vậy vẫn blocking dù API ở ngoài là reactive.

## 3. Bản đồ chuyển đổi API và quyết định kiến trúc

| Thành phần ở Servlet/Spring MVC | Trong WebFlux/reactive | Lưu ý chuyển đổi |
| --- | --- | --- |
| `jakarta.servlet.Filter`, `OncePerRequestFilter` | `org.springframework.web.server.WebFilter` | Trả `Mono<Void>` qua `WebFilterChain.filter(exchange)`; không viết Servlet filter vào WebFlux chain |
| `FilterRegistrationBean` | Spring-managed `WebFilter`; `@Order` khi phù hợp | Kiểm tra thứ tự so với Spring Security; filter nghiệp vụ bảo mật nên ở security chain |
| `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse` | Request/response reactive, không dùng Servlet input stream |
| `HttpSession` | `WebSession` qua `ServerWebExchange.getSession()` | Session API khác, thời điểm lưu khác; không tự coi là stateless |
| `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` hoặc `NoOpServerSecurityContextRepository` | Chọn phù hợp login stateful hay bearer token stateless |
| `SecurityContextHolder` (ThreadLocal) | `ReactiveSecurityContextHolder` (Reactor Context), `Mono<Principal>` | Không tin rằng context tự đi theo thread pool |
| `HttpSecurity` | `ServerHttpSecurity` | Cấu hình `SecurityWebFilterChain` thay cho servlet `SecurityFilterChain` |
| `UsernamePasswordAuthenticationFilter`, servlet authentication filter | `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, `ServerAuthenticationConverter` | Không copy servlet filter và ép chạy trong WebFlux |
| `HandlerInterceptor` | `WebFilter` hoặc cơ chế handler/route reactive tương ứng | Chỉ chuyển trách nhiệm cần thiết; không tạo filter chồng chức năng |
| `RestTemplate` / synchronous HTTP client | `WebClient` | `WebClient` non-blocking khi sử dụng thuần reactive; gọi `block()` vẫn chặn luồng |
| `JdbcTemplate` / Hibernate/JPA | R2DBC/driver async phù hợp hoặc adapter `boundedElastic` | R2DBC không thay thế mọi tính năng JPA; chọn theo nghiệp vụ |
| `JpaTransactionManager` / imperative `@Transactional` | `ReactiveTransactionManager` cho reactive data access | Không trộn transaction context theo thread với reactive transaction |
| Servlet `HttpServletRequest.getInputStream()` | `Flux<DataBuffer>` / codec WebFlux | Không `InputStream.read()` kéo dài trên event loop |
| Servlet `@Async` / `ExecutorService` được gọi rời rạc | Reactor composition, scheduler rõ ràng | Không tự `subscribe()` bên trong service để “cho chạy nền” |

Phải phân biệt ba loại yêu cầu:

1. **Bảo mật:** xác thực, ủy quyền, xử lý `401/403`, đăng nhập, CSRF, lưu SecurityContext. Ưu tiên cơ chế Spring Security reactive.
2. **HTTP cross-cutting:** request-id, metric tag, sửa header an toàn, giới hạn size/time, logging đã che dữ liệu nhạy cảm. Có thể dùng `WebFilter`.
3. **Nghiệp vụ/I/O:** gọi DB, HTTP, SDK, file, message broker. Nằm trong service với API non-blocking hoặc ranh giới offload; không nhét vào security filter.

## 4. Bước kiểm kê trước khi sửa code

Trong repository ứng dụng **được giao chuyển đổi** (không áp dụng vào mọi module khác), tìm các dấu hiệu còn phụ thuộc servlet. Ví dụ lệnh với `rg`; chúng là **lệnh gợi ý để học viên chạy trên project của mình**, không phải kết quả kiểm kê của một repository cụ thể:

```bash
rg -n "javax\.servlet|jakarta\.servlet|OncePerRequestFilter|FilterRegistrationBean|HttpServletRequest|HttpServletResponse|HttpSession" src
rg -n "SecurityFilterChain|HttpSecurity|SecurityContextHolder|RequestContextHolder|HandlerInterceptor" src
rg -n "RestTemplate|RestClient|JdbcTemplate|EntityManager|JpaRepository|Future\.get|Thread\.sleep|\.block\(|\.toFuture\(" src
rg -n "synchronized|ThreadLocal|MDC\.|\.join\(|InputStream|OutputStream" src
```

Một kết quả match **chưa chắc là lỗi**: `.block()` trong test đồng bộ hoặc bootstrap được kiểm soát có thể chấp nhận; Java I/O trong startup cũng khác I/O trên Netty event loop. Phải lần theo call graph tới nơi thực thi thực tế.

Kiểm tra cấu hình dependency:

- Dự án WebFlux thuần thường có `spring-boot-starter-webflux` và `spring-boot-starter-security`.
- Nếu có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên kiểu ứng dụng Servlet/MVC. Kiểm tra **actual `WebApplicationType`**, handler mappings và server đã khởi động; không kết luận “đã reactive” chỉ vì có `WebClient`.
- Một thư viện transitively kéo vào Servlet API không nhất thiết làm ứng dụng blocking; điều quan trọng là code thực thi path nào và server/stack nào được chọn.
- Gỡ dependency servlet-specific chỉ khi đã thay thế các tính năng cần thiết; các adapter cố tình hỗ trợ Servlet là một trường hợp riêng, không bắt buộc phải xóa bằng mọi giá.

**Mẫu phiếu kiểm kê cho từng điểm:**

| Trường cần ghi | Câu hỏi |
| --- | --- |
| Thành phần/call site | Class, bean, annotation, nơi gọi thực tế |
| Vai trò | Authentication, authorization, session, audit, logging, network hay DB? |
| Thực thi | Trên event loop, boundedElastic, thread pool riêng hay startup? |
| State | Đọc `HttpSession`, `SecurityContextHolder`, `ThreadLocal` hay request attribute nào? |
| Dependency | Servlet-only, blocking I/O, hỗ trợ reactive API hay có adapter? |
| Cách thay | Bỏ hẳn, `WebFilter`, Spring Security reactive, `WebSession`, `WebClient`/R2DBC, hoặc offload |
| Kiểm thử | Endpoint, status, session/cookie, identity, header, latency/load test |
| Rủi ro | Bypass auth, chuyển sai token, lộ state giữa request, event-loop starvation |

Sắp ưu tiên các điểm **đăng nhập/ủy quyền và leak request state** trước; sau đó mới tối ưu throughput.

## 5. Chuyển `OncePerRequestFilter` sang `WebFilter` đúng trách nhiệm

### 5.1. Ví dụ logic cũ chỉ mang tính minh họa

```java
// Servlet MVC: mảnh code tham khảo; KHÔNG đưa vào ứng dụng WebFlux.
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain) throws ServletException, IOException {
    String correlationId = UUID.randomUUID().toString();
    request.setAttribute("correlationId", correlationId);
    response.setHeader("X-Correlation-Id", correlationId);
    chain.doFilter(request, response);
}
```

Code cũ dựa vào Servlet request/response và `FilterChain.doFilter` là lời gọi đồng bộ. Không thể chỉ đổi kiểu trả về thành `Mono<Void>` mà giữ `HttpServletRequest` hay `FilterChain`.

### 5.2. Một `WebFilter` tương đương cho request-id

Tạo file `src/main/java/demo/migration/CorrelationIdWebFilter.java`:

```java
package demo.migration;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class CorrelationIdWebFilter implements WebFilter {
    private static final String HEADER = "X-Correlation-Id";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String supplied = exchange.getRequest().getHeaders().getFirst(HEADER);

        // Chỉ phản hồi ID do caller cung cấp nếu nó hợp lệ.
        String correlationId =
                supplied != null && supplied.matches("[A-Za-z0-9_-]{1,64}")
                        ? supplied
                        : UUID.randomUUID().toString();

        exchange.getAttributes().put("correlationId", correlationId);
        exchange.getResponse().getHeaders().set(HEADER, correlationId);

        return chain.filter(exchange);
    }
}
```

Giải thích:

- `ServerWebExchange` thay Servlet request/response. `exchange.getAttributes()` phù hợp để chia sẻ metadata **trong một request**, không cần ThreadLocal.
- `WebFilterChain.filter(exchange)` trả publisher `Mono<Void>` cho pipeline phía sau. Chỉ gọi chain **một lần** trên đường xử lý bình thường; không tự `subscribe()`.
- Bộ lọc kiểm tra ký tự và chiều dài của header đầu vào để tránh phản chiếu CRLF hoặc dữ liệu quá lớn vào response.
- `@Order(-100)` minh họa thứ tự của **ứng dụng WebFilter**; không dùng magic number này làm đảm bảo filter đã chạy trước/sau đúng một phase cụ thể của Spring Security. Với authentication logic, chọn vị trí bằng `SecurityWebFiltersOrder` hoặc cấu hình security DSL và test hành vi thật.
- Trước khi response committed, có thể thêm header; để thay header muộn hơn trong pipeline có thể dùng `response.beforeCommit(...)`, nhưng phải tôn trọng publisher và không block.

**Không áp dụng mẫu này để tự parse Authorization rồi set `SecurityContextHolder`.** Bộ lọc correlation ID và bộ lọc xác thực có nhiệm vụ khác nhau; tự xây authentication bên ngoài Spring Security dễ bỏ qua exception handling, phân quyền và quản lý context.

### 5.3. Chuyển bộ lọc xác thực và phân quyền

Servlet thường có cấu hình:

```java
// Servlet/MVC: minh họa trước chuyển đổi
@Bean
SecurityFilterChain servletChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().authenticated())
            .build();
}
```

Trong WebFlux, sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và `authorizeExchange`. Chuyển toàn bộ semantics quan trọng: route matcher, phương thức HTTP, authentication type, filter order, xử lý access denied, CSRF, CORS, session, HTTPS và logout. **Không có phép thay tên lớp 1:1** cho mọi servlet security filter.

Ví dụ:

- Servlet JWT bearer authentication → `oauth2ResourceServer(o -> o.jwt(...))` trên `ServerHttpSecurity` (cần reactive JWT decoder và issuer/JWKS phù hợp).
- Custom login authentication → `AuthenticationWebFilter`, `ReactiveAuthenticationManager` và `ServerAuthenticationConverter`; đồng thời test trường hợp credentials lỗi/thiếu.
- Custom principal ở `ThreadLocal` → giữ `Authentication` trong Reactor Context qua Spring Security, đọc bằng `ReactiveSecurityContextHolder` hoặc đối số `Principal` ở controller.
- Servlet `AccessDeniedHandler` / `AuthenticationEntryPoint` → các biến thể reactive `ServerAccessDeniedHandler` / `ServerAuthenticationEntryPoint`.
- Header policy, CORS, CSRF và HTTPS redirect → dùng WebFlux security DSL và cấu hình WebFlux-native, không copy filter servlet.

Khi có nhiều `SecurityWebFilterChain`, security matcher và `@Order` quyết định chain nào xử lý request; **chain đầu tiên phù hợp được chọn**. Đừng đặt chain bắt tất cả trước chain bảo vệ `/api/admin/**` hoặc bỏ sót một đường dẫn. Kiểm thử từng endpoint sau khi thay matcher.

## 6. Ví dụ tối thiểu: WebFlux security có thể chạy và kiểm thử

Ví dụ dùng Spring Boot 3.x, Java 17+, Gradle Kotlin DSL; dependency version do Spring Boot BOM/Gradle plugin của project quản lý. Phần này là **một ứng dụng demo hoàn chỉnh khi đã có build Spring Boot**, các file đặt dưới cùng package `demo.migration`.

Thêm các starter trong `build.gradle.kts` (mảnh `dependencies`, không phải toàn bộ build script):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Không thêm `spring-boot-starter-web` vào demo này. Tạo file `src/main/java/demo/migration/MigrationApplication.java`:

```java
package demo.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MigrationApplication.class, args);
    }
}
```

Tạo file `src/main/java/demo/migration/ReactiveSecurityConfig.java`:

```java
package demo.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}test-only-password")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
```

**Chỉ dùng `{noop}` và mật khẩu cố định ở ứng dụng demo/test.** Production phải dùng password hash thích ứng (ví dụ `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, bcrypt/Argon2 theo policy) hoặc OAuth2/OIDC với identity provider; không commit user/password thật.

Tạo file `src/main/java/demo/migration/DemoController.java`:

```java
package demo.migration;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/private/hello")
    public Mono<String> hello(Mono<Principal> principal) {
        return principal.map(user -> "hello " + user.getName());
    }
}
```

Ở đây tên user đến từ principal của **request reactive**; không truy cập `HttpSession` hoặc `SecurityContextHolder.getContext()`.

Tạo file `src/test/java/demo/migration/ReactiveSecurityMigrationTest.java`:

```java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveSecurityMigrationTest {
    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointNeedsNoLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void privateEndpointRejectsAnonymousRequest() {
        client.get().uri("/private/hello")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAcceptsValidTestCredentials() {
        client.get().uri("/private/hello")
                .headers(headers -> headers.setBasicAuth(
                        "learner", "test-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("hello learner");
    }
}
```

Chạy: `./gradlew test --tests demo.migration.ReactiveSecurityMigrationTest`; trên Windows dùng `gradlew.bat test --tests demo.migration.ReactiveSecurityMigrationTest`. **Kết quả mong đợi:** ba test pass, không có stdout ứng dụng bắt buộc; request anonymous đến `/private/hello` trả `401` vì HTTP Basic được bật. Kết quả này giả định chỉ có configuration demo và không có route/filter/security chain ngoài ví dụ can thiệp. Nếu dự án đang dùng Boot 4+, package của test auto-configuration có thể khác: thay theo tài liệu version đang chạy, không đổi toàn bộ logic security để sửa lỗi import.

Đây là ví dụ đơn giản kiểm tra migration của **security boundary**. Để kiểm chứng thứ tự `CorrelationIdWebFilter`, thêm phép thử header `X-Correlation-Id` có format hợp lệ/không hợp lệ và test trên request thành công/lỗi; không lấy riêng `@Order` làm bằng chứng thứ tự thực tế.

## 7. `HttpSession` không còn là API của WebFlux

### 7.1. `WebSession` xử lý state theo cách reactive

Trong Servlet có thể dùng:

```java
// Servlet MVC, mảnh minh họa
HttpSession session = request.getSession();
session.setAttribute("locale", "vi");
String locale = (String) session.getAttribute("locale");
```

WebFlux sử dụng `ServerWebExchange.getSession()` trả `Mono<WebSession>`. Ví dụ controller dưới đây là **một class Java riêng** trong package demo:

```java
package demo.migration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class SessionCounterController {
    @GetMapping("/session/visits")
    public Mono<String> visits(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Integer previous = session.getAttribute("visits");
            int current = (previous == null ? 0 : previous) + 1;
            session.getAttributes().put("visits", current);
            return "visits=" + current;
        });
    }
}
```

Ý nghĩa: ứng dụng đọc/ghi attribute trong phiên `WebSession` và trả lời với publisher. Tùy cấu hình, client cần giữ và gửi lại session cookie để số lần truy cập tăng giữa nhiều request. Với test manual, lần đầu nhận `visits=1`; request tiếp theo **chỉ** có thể nhận `visits=2` nếu cùng session được khôi phục. Đây là minh họa nhỏ, **không bảo đảm cập nhật đồng thời an toàn**: nhiều request đồng thời đọc-sửa-ghi một counter trong session có thể mất update. Trong production, dùng storage/atomic operation thích hợp nếu cần đếm chính xác.

`WebSession` cũng không phải là `HttpSession` dưới tên khác: các API và persistence lifecycle không tương đương tuyệt đối. Đừng giả định session đã được ghi hoặc tồn tại lâu chỉ vì gọi `getSession()`; kiểm tra việc start, mutate, expiration, session cookie và session store.

### 7.2. Stateful login hay stateless API?

- **Đăng nhập browser dựa vào cookie:** Có thể cần `WebSession`, session fixation protection, session cookie `Secure`/`HttpOnly`/`SameSite`, CSRF protection, logout và session invalidation đúng. Mặc định của Spring Security không thay thế thiết kế cookie/session.
- **API dùng Bearer/JWT trong `Authorization`:** Thường thích hợp **stateless**, không persist `SecurityContext` giữa request. Có thể dùng `NoOpServerSecurityContextRepository` cho policy này; token được xác minh lại mỗi request.
- **Ứng dụng nhiều Pod:** in-memory session không tự đồng bộ giữa instance. Xem xét Spring Session với `ReactiveSessionRepository` (ví dụ Redis reactive integration), cookie, key TTL và khả năng kết nối mạng; hoặc loại bỏ session nếu nghiệp vụ cho phép.
- **Client credential/token OAuth2:** `WebClient` outbound có thể dùng `OAuth2AuthorizedClient`; việc lưu authorized client khác với session chứa login principal. Không chuyển mọi token vào `WebSession` cho tiện.

Mảnh cấu hình **riêng cho resource server bearer-only**, không gộp vào demo HTTP Basic phía trên:

```java
@Bean
SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
    return http
            .securityContextRepository(
                    NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .oauth2ResourceServer(spec -> spec.jwt(withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
}
```

Đây là **mảnh method**, cần import `NoOpServerSecurityContextRepository`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `withDefaults`, dependency `spring-boot-starter-oauth2-resource-server` cùng issuer/JWK configuration hợp lệ. Chỉ disable CSRF khi API thật sự dùng credential không gửi tự động theo browser (ví dụ bearer trong Authorization header) và không có cookie-based browser flow; nếu có browser session hoặc cookie auth, giữ CSRF defense theo threat model. Chính sách này phải được test tách biệt khỏi Basic demo.

### 7.3. Security context và Reactor Context

Trong Servlet, code cũ thường làm:

```java
// Không dùng để lấy principal của một request reactive:
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Với WebFlux, có thể lấy trực tiếp `Mono<Principal>` làm method argument (như `DemoController`), hoặc dùng `ReactiveSecurityContextHolder` khi cần xử lý trong service:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

// Phương thức đặt trong service hoặc bean đang chạy ở reactive pipeline:
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

Cách này đọc authentication từ **subscriber context** do Spring Security thiết lập. Khi không có context/authentication, pipeline có thể empty; caller cần xử lý `switchIfEmpty`/authorization theo nghiệp vụ. Không gọi `block()` để lấy username, không dùng `ThreadLocal` tạm để “giữ principal”.

**Phân biệt security context với WebSession:** Reactor Context mang identity qua reactive chain; WebSession là nơi có thể lưu state qua nhiều HTTP request. Một request có authentication không đồng nghĩa mọi thông tin đó tự động được lưu session.

## 8. ThreadLocal, MDC và thông tin request khi đổi thread

Code Servlet thường sử dụng `RequestContextHolder`, `SecurityContextHolder`, `MDC.put("user", ...)` hoặc custom `ThreadLocal` để lưu request-id/current user. Trong WebFlux, thread có thể xử lý nhiều request và pipeline có thể đổi thread. Kết quả là:

- Thông tin request A có thể **mất** sau khi chuyển scheduler.
- Dữ liệu còn sót trong ThreadLocal có thể làm log của request B mang nhầm user/request-id nếu không cleanup chính xác.
- Ngay cả khi development chạy “đúng”, stress test hoặc pipeline bất đồng bộ có thể bộc lộ lỗi.

Cách thay:

1. Với state chỉ cần trong cùng HTTP exchange, dùng `exchange.getAttributes()`, biến local truyền qua method hoặc context của request.
2. Với data cần đi theo các reactive operators, dùng **Reactor Context** (thường `contextWrite`/`deferContextual`) và framework integration phù hợp.
3. Với authentication, dùng **`ReactiveSecurityContextHolder`** từ Spring Security, không xây cơ chế song song.
4. Với MDC, dùng bridge context propagation được hỗ trợ và cấu hình phù hợp; không giả định Reactor tự sao chép mọi `ThreadLocal`/MDC. Bảo đảm scope/cleanup và test khi đổi thread.
5. Không đưa mật khẩu/token/private data vào MDC, Reactor Context, request attributes hoặc log chỉ để debug.

Ví dụ **Reactor Core** độc lập trong một project đã có Reactor:

```java
import reactor.core.publisher.Mono;

Mono<String> message = Mono.deferContextual(context -> Mono.just(
        "request-id=" + context.get("requestId")))
        .contextWrite(context -> context.put("requestId", "req-123"));
```

Khi subscribe và nhận kết quả, message bằng `request-id=req-123`. Đây là mảnh Java (cần đặt trong phương thức và subscribe/test), cho thấy dữ liệu context gắn với **subscriber**, không phụ thuộc Java thread. Nó không tự thay thế Spring Security context; dùng `ReactiveSecurityContextHolder` cho principal.

## 9. Điều tra thư viện chặn luồng (blocking) trong request path

### 9.1. Danh sách điểm nguy hiểm

| Nhóm | Ví dụ | Tại sao cần xét lại |
| --- | --- | --- |
| Database | `JdbcTemplate`, Hibernate/JPA, JDBC DriverManager | Thường chờ socket/connection và block thread |
| HTTP | `RestTemplate`, `RestClient`, sync SDK clients | Chờ response trên thread gọi; có thể đi xuyên qua nhiều service |
| Filesystem | `Files.readAllBytes` trên file lớn, stream blocking | Disk I/O có thể block và tốn bộ nhớ |
| Sleep/lock | `Thread.sleep`, `Future.get`, `CompletableFuture.join`, lock lâu | Dừng thread; event loop không xử lý kịp request khác |
| Reactor | `Mono.block()`, `Flux.blockFirst()` trong handler/filter | Bẻ gãy chain non-blocking, có thể gây `IllegalStateException` trên non-blocking threads |
| SDK bên thứ ba | JDBC clients, cloud/LDAP/crypto/HSM SDK đồng bộ | Hình thức method không cho biết có block hay không; xem docs/call graph |
| Serialization | nén/giải nén hoặc ký/verify rất nặng CPU | Không nhất thiết blocking I/O nhưng chiếm event loop; cân nhắc scheduler CPU-limited |

**Chỉ dùng tên `Mono`/`Flux` không bảo đảm an toàn.** Ví dụ sai:

```java
// Sai: legacyDao.load(id) chạy ngay khi method được gọi.
Mono<Account> wrong(String id) {
    return Mono.just(legacyDao.load(id));
}

// Sai: block() bên trong WebFlux handler vẫn block thread.
Mono<Account> alsoWrong(String id) {
    return Mono.just(webClient.get()
            .uri("/accounts/{id}", id)
            .retrieve()
            .bodyToMono(Account.class)
            .block());
}
```

Đây là **mảnh minh họa**, cần có `legacyDao`, `Account`, `webClient` để biên dịch; mục tiêu là nhận diện anti-pattern, không phải ví dụ ứng dụng độc lập.

### 9.2. Ưu tiên API non-blocking

- HTTP outbound: `WebClient` và xử lý kết quả bằng `flatMap`/`map`/`onErrorResume` mà không gọi `block()`.
- Database: driver R2DBC và Spring Data R2DBC (khi phù hợp tính năng), gọi qua `Mono`/`Flux`.
- Cache/Redis/broker: dùng reactive client thật nếu được cung cấp, không chỉ bọc SDK blocking trong `Mono.just`.
- Stream dữ liệu: dùng WebFlux codec/reactive publisher, đặt giới hạn body size, không copy nguyên payload lớn vào heap nếu không cần.
- Reactive transaction: dùng manager và data-access reactive; transaction theo Reactor context, không dựa vào ThreadLocal như imperative JDBC transaction.

Ví dụ service WebClient reactive (mảnh class/method với dependency `WebClient` được inject):

```java
Mono<String> loadSummary(String accountId) {
    return webClient.get()
            .uri("/accounts/{id}/summary", accountId)
            .retrieve()
            .bodyToMono(String.class);
}
```

Phương thức trả publisher về caller, không `block()`; framework subscribe khi HTTP request cần response. Cần đặt base URL, timeout, codec size và error mapping theo hệ thống thật; không lấy response giả lập làm bằng chứng kết nối production.

### 9.3. Bắt buộc giữ JDBC/SDK synchronous: cô lập bằng `boundedElastic`

Đối với thư viện **chưa có** reactive API tương đương, dùng `Mono.fromCallable` để hoãn chạy blocking work đến lúc subscribe, rồi `subscribeOn(Schedulers.boundedElastic())` để thực thi ngoài event loop:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

// Phương thức trong service; legacyDao.load(id) là lời gọi blocking.
Mono<Account> loadViaLegacyDao(String id) {
    return Mono.fromCallable(() -> legacyDao.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Nếu `legacyDao.load(id)` trả `null`, `Mono.fromCallable` hoàn thành **empty**; xử lý `switchIfEmpty` khi null là lỗi nghiệp vụ. Nếu thư viện ném exception, publisher báo `onError`. Đây là cách **cô lập chặn luồng**, không làm JDBC thành non-blocking; throughput vẫn chịu giới hạn thread pool, queue và connection pool.

Sử dụng `subscribeOn` ở gần **nguồn blocking** để source được schedule đúng nơi. `Mono.defer(() -> Mono.just(legacyDao.load(id)))` chỉ trì hoãn tạo giá trị, không tự chuyển thread. `publishOn` chuyển execution context cho các operator **phía sau** nó; nếu blocking source chạy phía trước `publishOn`, event loop vẫn bị chặn.

Chú ý bổ sung:

- Không tạo `Schedulers.newBoundedElastic(...)` cho từng HTTP request; dùng scheduler dùng chung có capacity thích hợp, metric và shutdown lifecycle rõ.
- Giới hạn concurrency phù hợp pool DB/HTTP service; quá nhiều request có thể dồn vào queue dù event loop không bị block.
- Timeout của `Mono.timeout` không nhất thiết **ngắt được** blocking I/O vốn không hỗ trợ interruption; phải cấu hình timeout ở chính JDBC/socket/SDK.
- `subscribeOn` không tự mang ThreadLocal security/MDC sang worker. Truyền giá trị cần thiết như đối số hoặc dùng context propagation đúng.
- Không dùng `.block()` trong `WebFilter`, `ReactiveAuthenticationManager`, `@RestController` WebFlux hoặc callback của `WebClient`.

Một JUnit 5 test nhỏ cho ranh giới scheduler. Tạo `src/test/java/demo/migration/BlockingBoundaryTest.java`:

```java
package demo.migration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotSame;

class BlockingBoundaryTest {
    @Test
    void blockingCallableRunsOffTheSubscriberThread() {
        Thread testThread = Thread.currentThread();

        Mono<String> pipeline = Mono.fromCallable(() -> {
                    assertNotSame(testThread, Thread.currentThread());
                    return "result-ok";
                })
                .subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(pipeline)
                .expectNext("result-ok")
                .verifyComplete();
    }
}
```

Chạy: `./gradlew test --tests demo.migration.BlockingBoundaryTest` (Windows: `gradlew.bat test --tests demo.migration.BlockingBoundaryTest`). **Kết quả dự kiến:** test pass, không có stdout ứng dụng. Nó chứng minh callable được schedule ra thread khác trong điều kiện test; **không** chứng minh một JDBC driver đã trở thành async, không chứng minh latency khi 1000 request và không xác nhận tất cả call sites đều được offload.

## 10. Session, cookie, CSRF, CORS: các hành vi dễ thay đổi sau migration

Không nên dùng “trả 200 ở local” làm định nghĩa hoàn tất migration. Với ứng dụng có session/cookie/login, cần kiểm tra:

**Session và authentication**

- Khi login, principal có được lưu/khôi phục trên request kế tiếp đúng yêu cầu không?
- Cookie name, path, domain, `Secure`, `HttpOnly`, `SameSite` và expiration có đúng reverse proxy/HTTPS origin không?
- Logout có xóa session và cookie theo flow của WebFlux không, hay chỉ xóa `HttpSession` cũ không còn được sử dụng?
- Nếu có nhiều instance, client gửi request sang instance khác có mất session? Spring Session reactive + Redis có được cấu hình đúng không?
- Session fixation và session ID renewal khi login có được test không?

**CSRF**

- Browser dựa vào cookie session là đối tượng của CSRF, kể cả endpoint trả JSON. Đừng tắt CSRF hàng loạt chỉ vì WebFlux trả API.
- Nếu chuyển từ form/HTML sang SPA, kiểm tra CSRF token repository, header/cookie truyền token, các method thay đổi trạng thái và request từ trình duyệt.
- Với bearer-only API không tự được browser gửi credential, có thể thiết kế khác; phân tích cả trường hợp cùng endpoint còn chấp nhận cookie.

**CORS và preflight**

- CORS xử lý cả preflight `OPTIONS`; bảo đảm Spring WebFlux/Security không từ chối request **trước** khi CORS có cơ hội trả lời.
- Đừng dùng `allowedOrigins("*")` với credential cookies; cấu hình origin cụ thể, methods, headers, `allowCredentials` và cache preflight theo môi trường.
- Phân biệt lỗi CORS trong trình duyệt và `401/403` do backend: kiểm tra network trace/preflight, không suy từ UI message đơn thuần.

**Forwarded headers và proxy**

- Ứng dụng sau TLS termination cần hiểu scheme, host, port/path đúng khi redirect hoặc tạo URL; cấu hình forwarded headers và trust proxy một cách giới hạn.
- Tránh tin `X-Forwarded-*` từ client ngoài trực tiếp khi proxy không loại/ghi đè; đây có thể ảnh hưởng redirect URI, cookie và chính sách HTTPS.

## 11. Thứ tự bộ lọc và nơi đặt logic bảo mật

Trong Servlet, lập trình viên thường dùng `FilterRegistrationBean#setOrder` và `OncePerRequestFilter` để chạy trước/sau Spring Security. Trong WebFlux, có **hai lớp điều phối**:

1. `WebFilter` của Spring WebFlux bao quanh handler; thứ tự thường đến từ `@Order`/`Ordered` trên các bean.
2. Bên trong Spring Security reactive, `SecurityWebFilterChain` chứa các bước xác thực/ủy quyền, với thứ tự xác định bởi `SecurityWebFiltersOrder` và các configurers.

Đừng giả định một `@Order(-1)` trên `WebFilter` tương ứng với một order servlet như `UsernamePasswordAuthenticationFilter`. Nếu phải thêm authentication filter tùy biến:

- Dùng Spring Security reactive `AuthenticationWebFilter` với `ReactiveAuthenticationManager` và `ServerAuthenticationConverter`.
- Đăng ký filter trong `ServerHttpSecurity.addFilterAt(webFilter, SecurityWebFiltersOrder.AUTHENTICATION)` hoặc vị trí phù hợp **sau khi hiểu các filter hiện có**; không đẩy authentication vào global `WebFilter` rồi tự viết lại xử lý `401/403`.
- Kiểm tra security matcher, nhiều chain, Bearer/basic/form/OAuth2 handlers và exception semantics; log có kiểm soát tại điểm xử lý lỗi.
- Đảm bảo mọi publisher nhánh success/failure đều được trả lại để framework subscribe; tự gọi `subscribe()` có thể tạo race, mất context hoặc trả response trước khi authentication hoàn tất.

**Ví dụ về bug thứ tự:**

- Filter audit đọc `SecurityContextHolder` và thấy `null` trên reactor event loop; không thể “sửa” bằng chuyển filter sang `@Order(0)` theo kinh nghiệm servlet. Dùng `ReactiveSecurityContextHolder` đúng context hoặc truy xuất principal tại phase phù hợp.
- Route `/api/admin/**` trả `200` khi authentication bị bỏ qua do chain global `permitAll()` match trước chain admin. Thêm test `403` cho user thiếu role và test route matcher.
- Custom `WebFilter` tự thay response status `401` khi `WebClient` downstream trả `401`, gây nhầm giữa inbound authorization và lỗi dịch vụ khác. Đặt xử lý downstream error trong service/handler, không đồng nhất mọi HTTP 401.

## 12. Các bài test bắt buộc khi chuyển stack

| Trường hợp | Thiết lập | Điều phải kiểm chứng |
| --- | --- | --- |
| Public route | Request không auth | `200` cho route công khai đã khai báo |
| Private route anonymous | Không session/token/Basic | `401` hoặc redirect login đúng cơ chế; không bất ngờ `200` |
| Authenticated user thiếu quyền | User có role không đủ | `403` theo policy thực, không lộ tài nguyên |
| Role/scope đúng | Test principal/token có authority phù hợp | Endpoint cho truy cập, dữ liệu đúng user |
| Session sau login | Giữ cookie qua nhiều request | Login tồn tại, timeout/logout hoạt động; không leak giữa clients |
| Stateless Bearer | Token hợp lệ/hết hạn/sai signature | 200/401 theo JWT decoder, không dựa session vô tình |
| CSRF browser | POST/PUT/DELETE không có token khi dùng cookie | Request bị chặn; gửi token hợp lệ mới được tiếp nhận |
| CORS preflight | `OPTIONS` với Origin và Access-Control-Request-* | Response có policy CORS đúng, không bị filter auth chặn sai |
| Correlation header | Header hợp lệ/không hợp lệ | Response phản ánh ID đã validate, không phản chiếu chuỗi nguy hiểm |
| HTTP downstream | Mock server trả 2xx/4xx/5xx và trễ | WebClient mapping đúng, không `block()` và có timeout |
| Blocking integration | Load test với legacy DAO | Theo dõi event loop, boundedElastic queue, connection pool và latency |
| Multi-instance state | Nhiều Pod, chuyển request giữa instance | Session phân tán hoặc stateless đúng thiết kế |
| Cancellation | Client ngắt kết nối khi xử lý đang chờ | Không giữ tài nguyên/callback dư thừa vô hạn |
| Error/timeout | IdP/DB/HTTP downstream chậm, không sẵn sàng | Error signal được xử lý, không làm nghẽn cả server |

Dùng `WebTestClient` cho HTTP reactive và `StepVerifier` cho publisher logic. Với Spring Security Test, `mockUser()`, `mockJwt()`, `mockOAuth2Login()` phục vụ từng loại authentication **khi đã áp dụng Spring Security WebTestClient configurer đúng cách**; không sử dụng Servlet `MockMvc`/`with(user(...))` cho một controller WebFlux.

Đặt các bài test về **nhánh từ chối** cạnh happy path. Có thêm kiểm tra cookie, response headers và security context khi đổi thread/scheduler; test chỉ đo HTTP status có thể bỏ sót việc lưu sai session hoặc bỏ qua filter.

## 13. Quy trình chuyển đổi an toàn theo từng bước

1. **Xác nhận stack đang chạy.** Kiểm tra Boot `WebApplicationType`, dependency tree, log server, WebFlux handler mappings; loại các giả định “có WebClient nghĩa là WebFlux”.
2. **Giữ hợp đồng HTTP.** Liệt kê endpoint, verbs, auth requirement, scopes/roles, session/cookies, redirects, error payload, headers. Chụp test hành vi servlet hiện tại làm baseline.
3. **Tách responsibility từng Servlet filter.** Bộ lọc audit/correlation → `WebFilter`; authentication/authorization → Spring Security reactive DSL; request body handling → codec/handler phù hợp. Tránh copy nguyên filter phức tạp sang WebFilter.
4. **Chuyển authentication và security context.** Sử dụng `SecurityWebFilterChain`/`ServerHttpSecurity` và reactive manager/repository. Loại dependency logic vào servlet `SecurityContextHolder` ThreadLocal.
5. **Quyết định session.** Token API thường stateless; browser login có thể giữ `WebSession`. Cấu hình persistence/TTL/cookie/security context repository có chủ đích.
6. **Rà call graph blocking từ controller/filter.** Chuyển HTTP/DB sang reactive clients khi được; offload thư viện cũ bằng `fromCallable + boundedElastic`, đặt concurrency và timeout hữu hạn.
7. **Chuyển tests trước khi rollout.** Kiểm chứng auth/deny, CORS, CSRF, session, filter order, exception mapping và timeout. Test security reactive không sao chép Mockito tests của servlet.
8. **Kiểm thử staging dưới tải và nhiều instance.** Đo throughput, p95/p99, event-loop delay, boundedElastic saturation, connection pool, reactor scheduling, thread leaks.
9. **Rollout có rollback.** Canary hoặc feature flag ở routing/service boundary; theo dõi 401/403, 5xx, latency, login errors, session churn. Khi rollback, bảo đảm phiên/cookie/data contract còn tương thích.

Một chuyển đổi chỉ được coi là xong khi **bảo mật giữ nguyên yêu cầu và blocking đã được xử lý có chủ đích**, không chỉ khi compiler hết báo thiếu import.

## 14. Triệu chứng và cách gỡ lỗi

| Triệu chứng | Nguyên nhân thường gặp | Hướng xác minh |
| --- | --- | --- |
| `@Component OncePerRequestFilter` không được chạy | Ứng dụng dùng WebFlux, filter thuộc Servlet API | Xem stack runtime, đổi sang `WebFilter` hoặc reactive security config |
| `HttpSession` không injectable | Controller chạy với WebFlux | Sử dụng `WebSession`/`ServerWebExchange.getSession()` nếu cần state |
| `SecurityContextHolder.getContext()` trả empty | Principal nằm trong Reactor Context, execution đổi thread | Dùng `ReactiveSecurityContextHolder` hoặc reactive Principal argument |
| App vẫn hiện Tomcat/DispatcherServlet | Có cả MVC và WebFlux starter, Boot chọn Servlet | Kiểm tra dependency/web application type và cấu hình lựa chọn stack |
| Public endpoint trả 401 | Matcher khác, nhiều chain sai order, Basic/JWT filter áp policy sai | Dò `SecurityWebFilterChain` thực sự match endpoint, test từng matcher |
| Request có role vẫn trả 403 | Authorities khác format, method security, scope mapping | So sánh authorities thực tế với `hasRole`/`hasAuthority`, không log raw token |
| Login thành công nhưng request sau mất login | Cookie không được gửi hoặc session store/bean khác stack | Quan sát Set-Cookie/Cookie, TTL, WebSession, Spring Session setup |
| POST browser trả 403 | CSRF token thiếu, cookie session vẫn dùng | Kiểm tra CSRF token repository, request header/cookie, policy thực |
| Preflight OPTIONS bị chặn | CORS filter/security order sai | Kiểm tra OPTIONS response, allowed origin/headers/methods |
| `block()/blockFirst() are blocking` | `block()` gọi trên Reactor non-blocking thread | Xem stack trace để tìm blocking call, sửa theo reactive hoặc offload |
| Response chậm dù CPU thấp | JDBC/HTTP sync/lock chạy trên event loop | Thread dump có phân loại, event-loop queue, latency profile |
| boundedElastic queue tăng dần | Blocking workload nhiều hơn capacity/connection pool | Đặt concurrency limit/timeout, đo và thay dần sang non-blocking driver |
| Logger ghi user của request khác | MDC/ThreadLocal còn dữ liệu hoặc propagation sai | Reproduce concurrent requests đổi thread, kiểm tra scope cleanup |
| Lỗi do auto-subscribe trong filter | `subscribe()` rời chain mất context, response race | Trả đúng `Mono<Void>`, compose bằng `then`/`flatMap` và xử lý error signal |
| Container đổi từ Tomcat sang Netty, health OK nhưng 5xx | Blocking dependency/Servlet filter chưa chuyển hoặc default resource policy đổi | Test protected HTTP flows và integration xuống DB/IdP/HTTP thật |

### Khi cần theo dõi hiệu năng

Dùng metric event loop/reactor scheduler, request latency theo percentile, Netty connection pool, database pool và số request đang chờ. Thread dump trong lúc tải cao giúp xác định thread `reactor-http-*` đang chờ JDBC/socket/lock. Công cụ như BlockHound có thể giúp phát hiện một số blocking calls trong môi trường kiểm thử, nhưng hỗ trợ instrument/Java version cần được xác nhận; nó không thay được profiling, load test và code review. Không bật DEBUG dump request body/Authorization headers trên production khi đang gỡ lỗi xác thực.

## 15. Checklist nghiệm thu một module WebFlux

- [ ] Đã xác định runtime dùng WebFlux/reactive, không chỉ có dependency `WebClient`.
- [ ] Không còn Servlet `Filter`/`HttpServletRequest`/`HttpSession` ở request path cần chuyển; các trường hợp cố ý dùng Servlet adapter có giải thích riêng.
- [ ] Logic authentication/authorization nằm trong `SecurityWebFilterChain` và reactive security components; từng matcher có test deny/allow.
- [ ] Bộ lọc không dùng `block()`, `subscribe()` thủ công hoặc ThreadLocal để giữ authentication/request state.
- [ ] CORS, CSRF, session fixation, logout, headers và HTTPS/forwarded host được kiểm thử theo flow browser/API thực tế.
- [ ] Mọi API blocking còn lại có inventory và biện pháp xử lý rõ ràng: thay reactive hoặc offload có concurrency/timeout.
- [ ] Resource Server token validation/authority mapping hoặc OAuth2 login được kiểm tra lại trong stack reactive, không trộn servlet test utilities.
- [ ] Session store/cookie behavior đúng trên nhiều instance, hoặc stateless API không lưu security context vô tình.
- [ ] Có các bài test `401`, `403`, `200`, error/timeout, principal isolation, concurrent requests và event-loop health.
- [ ] Deploy metrics/alerts cho latency, event-loop saturation, boundedElastic queue, DB connection pool, authentication failures; có rollback path.

## 16. Câu hỏi tự luyện

1. Vì sao `OncePerRequestFilter` không tự hoạt động khi ứng dụng chạy bằng Spring WebFlux?
2. Khi nào một HTTP middleware nên là `WebFilter`, khi nào nên là `AuthenticationWebFilter`/`ServerHttpSecurity`?
3. Thay `HttpSession` bằng `WebSession` đã đủ để đảm bảo session được share giữa nhiều Pod chưa?
4. Vì sao `SecurityContextHolder` có thể rỗng trong một reactive chain dù request đã authenticated?
5. So sánh `Mono.just(dao.load())` với `Mono.fromCallable(() -> dao.load()).subscribeOn(boundedElastic())` về thời điểm blocking call được thực hiện.
6. Vì sao `publishOn(boundedElastic())` sau một blocking source không sửa được blocking đã xảy ra phía trước?
7. Nếu app có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, cần kiểm tra điều gì trước khi sửa Servlet filter?
8. Hai bài test nào bắt buộc để phát hiện việc route admin trở thành public sau migration?
9. Khi nào có thể xem xét `NoOpServerSecurityContextRepository`, và tại sao không nên tắt CSRF khi vẫn dùng cookie auth?
10. Để chứng minh hệ thống không nghẽn event loop, cần những metric/test nào ngoài HTTP `200`?

## Tài liệu chính thức

- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – Reactive Authentication Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security – Reactive HTTP/CORS/CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/index.html
- Spring Framework – WebFlux Concurrency Model và Blocking APIs: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework – WebFlux Filters: https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
- Spring Framework – WebSession: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Session – WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Project Reactor – FAQ: Wrapping a Synchronous, Blocking Call: https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking

> Khi triển khai thật, đối chiếu API và configuration của **Spring Boot/Spring Security/Framework version đang sử dụng**. Ví dụ demo không tự thay thế policy OAuth2/OIDC, session store, proxy, driver và test suite của ứng dụng thực tế.
