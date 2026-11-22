# ExceptionTranslationWebFilter và phản hồi thiếu quyền trong Spring Security WebFlux

## 1. Mục tiêu của bài học

Trong một API WebFlux, người gọi có thể bị từ chối vì **chưa xác thực** hoặc vì **đã xác thực nhưng không có quyền**. Hai tình huống này khác nhau về ý nghĩa, HTTP status và hướng xử lý ở client. Spring Security sử dụng `ExceptionTranslationWebFilter` để chuyển những ngoại lệ bảo mật phù hợp trong reactive WebFilter chain thành phản hồi HTTP thông qua hai thành phần:

- `ServerAuthenticationEntryPoint`: khởi động quá trình yêu cầu **xác thực** (thường gặp HTTP `401 Unauthorized`, hoặc chuyển hướng đăng nhập trong ứng dụng web).
- `ServerAccessDeniedHandler`: xử lý việc **đã được xác thực nhưng bị từ chối quyền** (thường gặp `403 Forbidden`).

Bài thuộc nhóm **HTTP trên WebFlux** của Spring Security Authorization. Sau bài, bạn sẽ:

1. Hiểu vai trò của `ExceptionTranslationWebFilter`, `AuthorizationWebFilter`, authentication filter và `SecurityWebFilterChain`.
2. Phân biệt `AuthenticationException`, `AccessDeniedException`, anonymous/unauthenticated và authenticated-but-forbidden.
3. Cấu hình `ServerHttpSecurity.exceptionHandling(...)` bằng entry point và access-denied handler riêng, thay vì tự thêm filter hoặc bắt ngoại lệ tùy tiện trong controller.
4. Thiết kế phản hồi JSON tối thiểu, ổn định, không lộ tên tài nguyên/stack trace/internal error.
5. Hiểu cách `httpBasic`, form login, bearer token, CSRF và các filter khác có thể tạo phản hồi khác nhau cho tình huống “không được phép”.
6. Kiểm thử end-to-end trong WebFlux bằng `WebTestClient`, `mockUser` và `csrf()`, phân biệt lỗi permission và lỗi CSRF.
7. Biết giới hạn: filter **không phải handler chung cho mọi lỗi Java**, không tự làm phân quyền ở service, không xử lý mọi authentication failure giống nhau và không thể gửi lại status khi response đã committed.

**Ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x và Spring WebFlux. Ví dụ sử dụng authentication giả lập trong test, không cung cấp login endpoint hoặc hệ thống token production.

## 2. Nằm ở đâu trong reactive security chain?

```text
HTTP request
     |
     v
SecurityWebFilterChain
     |
     +-- Authentication WebFilters (nếu được cấu hình)
     |        |
     |        +-- xác thực thành công -> Authentication/SecurityContext
     |        +-- xác thực thất bại -> authentication failure handling
     |
     v
ExceptionTranslationWebFilter
     |
     v
AuthorizationWebFilter
     |        (authorizeExchange: authenticated/hasAuthority/access)
     |
     +-- ALLOW ------------------------> Controller/handler
     |
     +-- DENY -> AccessDeniedException
                    |
                    v
          ExceptionTranslationWebFilter
                    |
           +--------+-----------+
           |                    |
      Anonymous/thiếu auth   Đã xác thực nhưng
      hoặc cần xác thực      thiếu quyền
           |                    |
           v                    v
  ServerAuthenticationEntryPoint  ServerAccessDeniedHandler
           |                    |
      Thường 401/302          Thường 403
```

Sơ đồ trình bày **luồng logic của những lỗi được filter nhận diện**. Trật tự cụ thể và nguồn tạo status còn phụ thuộc cấu hình. Ví dụ, một request POST thiếu CSRF token có thể bị `CsrfWebFilter` chặn **trước khi đến authorization rule**; một mật khẩu HTTP Basic sai có thể được xử lý bởi authentication failure handler; còn lỗi dữ liệu trong controller thường thuộc WebFlux exception handling.

### 2.1. Bộ ba khái niệm quan trọng

| Thành phần | Đầu vào chính | Trách nhiệm |
| --- | --- | --- |
| `AuthorizationWebFilter` | `ServerWebExchange` và reactive authorization manager | Đánh giá cho phép/từ chối HTTP request theo `authorizeExchange` |
| `ExceptionTranslationWebFilter` | `AuthenticationException` / `AccessDeniedException` có thể bắt trong chain | Chọn cách xử lý ngoại lệ bảo mật bằng entry point hoặc denied handler |
| `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` | Exchange + exception tương ứng | Tạo phản hồi HTTP hoặc chuyển hướng/challenge |

`ExceptionTranslationWebFilter` **không quyết định người dùng có quyền READ hay DELETE**: nó xử lý hậu quả khi hệ thống bảo mật yêu cầu xác thực hoặc từ chối. Quy tắc quyền nằm ở `authorizeExchange`, custom `ReactiveAuthorizationManager`, hoặc ở domain service.

### 2.2. WebFlux khác Servlet

| Chủ đề | Reactive WebFlux | Servlet MVC |
| --- | --- | --- |
| Bộ dịch ngoại lệ bảo mật | `ExceptionTranslationWebFilter` | `ExceptionTranslationFilter` |
| Cấu hình HTTP | `ServerHttpSecurity` | `HttpSecurity` |
| Handler thiếu xác thực | `ServerAuthenticationEntryPoint` | `AuthenticationEntryPoint` |
| Handler thiếu quyền | `ServerAccessDeniedHandler` | `AccessDeniedHandler` |
| Request/response | `ServerWebExchange` / `ServerHttpResponse` | `HttpServletRequest` / `HttpServletResponse` |
| Xử lý kết quả | `Mono<Void>` | API synchronous |

Không dùng nhầm `HttpServletResponse.sendError(...)`, `AuthenticationEntryPoint` Servlet hoặc `AccessDeniedHandler` Servlet trong một `SecurityWebFilterChain` WebFlux.

## 3. 401, 403 và những phản hồi khác: phân biệt bằng nguyên nhân

### 3.1. `401 Unauthorized` — cần xác thực

Một route yêu cầu `authenticated()` hoặc `hasAuthority("DOC_READ")`, nhưng request không có authentication hợp lệ. Spring Security có thể dùng `ServerAuthenticationEntryPoint` để yêu cầu credentials.

```http
GET /api/docs/read
Accept: application/json

HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED"}
```

Đây là **minh họa phản hồi từ cấu hình JSON của bài**, không phải body mặc định của mọi ứng dụng Spring Security. Trong HTTP Basic, 401 thường đi kèm `WWW-Authenticate: Basic ...`; với Bearer token có thể có `WWW-Authenticate: Bearer ...`; form login thường chuyển hướng đến login page thay vì JSON 401. Custom handler phải phù hợp với authentication scheme.

### 3.2. `403 Forbidden` — đã xác thực nhưng thiếu quyền

Alice đăng nhập thành công, nhưng chỉ có `DOC_READ` trong khi endpoint yêu cầu `DOC_ADMIN`. `AuthorizationWebFilter` từ chối, và `ServerAccessDeniedHandler` có thể trả 403:

```http
GET /api/docs/admin
Accept: application/json

HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED"}
```

HTTP 403 nói rằng client **không có quyền cho thao tác hiện tại**. Không nên tự động khuyên client đăng nhập lại nếu quyền thực sự bị từ chối. 403 cũng không chứng minh account được phép nhìn thấy object ID trong URL; một API có thể chọn che giấu resource bằng 404 nhất quán, theo threat model.

### 3.3. Bảng quyết định và những ngoại lệ quan trọng

| Tình huống | Lớp thường xử lý | Kết quả có thể gặp |
| --- | --- | --- |
| Request không có authentication, route bảo vệ | Exception translation + entry point | 401 hoặc redirect 302 tùy cơ chế |
| User đã xác thực, thiếu `DOC_READ` | Authorization + access-denied handler | 403 |
| User có `DOC_READ`, thiếu `DOC_ADMIN` | Authorization + access-denied handler | 403 |
| User đã xác thực nhưng bị `denyAll()` | Authorization + access-denied handler | 403 |
| POST không có CSRF token hợp lệ | `CsrfWebFilter` và cơ chế xử lý lỗi CSRF | Thường 403; không suy ra custom handler đã chạy |
| HTTP Basic sai password | Authentication filter/failure handler | Thường 401; body/challenge có thể khác entry point tùy cấu hình |
| Bearer token không hợp lệ | Resource Server authentication handling | Thường 401 với Bearer challenge thích hợp |
| Controller ném `IllegalArgumentException` | WebFlux application exception handling | Tùy `@ControllerAdvice`/error configuration, không phải mặc định auth 403 |
| Handler trả `Mono.empty()` | Controller/handler semantics | Không có nghĩa access denied |
| Document không tồn tại | Business layer/policy | 404 hoặc deny theo thiết kế; không tự xem như authentication failure |
| JSON body không hợp lệ | WebFlux validation/codec | 400, không phải thiếu quyền |
| Response đã gửi headers/body | Hệ thống không thể đổi lại status một cách tùy ý | Cần tránh ghi response trước authorization |

**Quy tắc:** phân loại theo **security state và loại exception**, không bắt tất cả exception rồi trả 403. Việc làm này vừa che bug vừa khiến client không thể phân biệt lỗi hệ thống với thiếu permission.

## 4. Spring Security áp dụng entry point và access-denied handler như thế nào?

### 4.1. API cấu hình chính thức

Trong Spring Security 6.5, `ServerHttpSecurity.ExceptionHandlingSpec` cung cấp:

```java
exceptionHandling(spec -> spec
    .authenticationEntryPoint(authenticationEntryPoint)
    .accessDeniedHandler(accessDeniedHandler)
)
```

Đây là **fragment** thuộc cấu hình `ServerHttpSecurity`, chưa phải chương trình độc lập. Hai tham số phải lần lượt thực thi:

```java
ServerAuthenticationEntryPoint:
Mono<Void> commence(
    ServerWebExchange exchange,
    AuthenticationException authenticationException);

ServerAccessDeniedHandler:
Mono<Void> handle(
    ServerWebExchange exchange,
    AccessDeniedException accessDeniedException);
```

Các kiểu được đặt ở những package khác nhau:

- `ServerAuthenticationEntryPoint`: `org.springframework.security.web.server`.
- `ServerAccessDeniedHandler`: `org.springframework.security.web.server.authorization`.
- `ExceptionTranslationWebFilter`: `org.springframework.security.web.server.authorization`.

Dùng `exceptionHandling(Customizer)` thay vì một chuỗi gọi `.exceptionHandling().and()` cũ khi viết cấu hình mới.

### 4.2. Không tự chèn thêm `ExceptionTranslationWebFilter` nếu không cần

Khi sử dụng `ServerHttpSecurity`/Spring Security WebFlux, framework đã xây dựng security filter chain theo cấu hình. Việc tạo thêm một `ExceptionTranslationWebFilter` dưới dạng `@Bean WebFilter` ngoài ý muốn có thể làm **xử lý exception nhiều lần**, trùng handler hoặc thay đổi thứ tự bảo mật.

Ưu tiên cấu hình tại:

```java
@Bean
SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
    return http
        .exceptionHandling(spec -> spec
            .authenticationEntryPoint(myEntryPoint)
            .accessDeniedHandler(myAccessDeniedHandler))
        .authorizeExchange(spec -> spec
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .build();
}
```

Đây là fragment: `myEntryPoint`, `myAccessDeniedHandler` cần có bean/biến tương ứng. Project mục 8 cung cấp một triển khai đầy đủ.

### 4.3. Dùng HTTP status-only handler khi không cần body

Spring Security có những implementation sẵn:

```java
new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);
new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);
```

Chúng phù hợp khi chỉ cần status HTTP. Khi cần body JSON ổn định, tự triển khai handler **không tiết lộ chi tiết exception** như ví dụ bên dưới. Một số authentication scheme cần header challenge; status-only không phải giải pháp thay thế phù hợp cho mọi HTTP Basic/Bearer client.

## 5. Thiết kế phản hồi thiếu quyền cho REST API

### 5.1. Hợp đồng JSON tối thiểu

Một API có thể chuẩn hóa:

| Status | Code nội bộ | Ý nghĩa dành cho client |
| --- | --- | --- |
| 401 | `AUTHENTICATION_REQUIRED` | Cần xác thực hợp lệ |
| 403 | `ACCESS_DENIED` | Không có quyền cho thao tác |
| 404 | `RESOURCE_NOT_FOUND` | Không tìm thấy hoặc cố ý che giấu resource theo policy |
| 429 | `RATE_LIMITED` | Bị giới hạn tốc độ, không phải thiếu quyền |
| 503 | `AUTHORIZATION_BACKEND_UNAVAILABLE` | Nguồn policy không sẵn sàng; quyết định fail closed |

Hai status đầu được cấu hình trực tiếp trong ví dụ; những mã còn lại chỉ là **gợi ý hợp đồng API**, không phải tất cả do `ExceptionTranslationWebFilter` tự sinh.

**Không đưa** `exception.getMessage()`, subject/token, username khác tenant, SQL, ACL expression, role nội bộ hoặc stack trace vào body 401/403. Dùng mã lỗi ổn định, thông điệp chung (nếu cần), request correlation ID đáng tin; đưa thông tin chẩn đoán vào server log hạn chế truy cập, có lọc dữ liệu nhạy cảm.

### 5.2. CORS, CSRF và cache headers

- **CORS preflight OPTIONS** cần được cấu hình đúng, nếu không frontend có thể nhận lỗi CORS mà nhầm là thiếu authorization. Chỉ cho phép origin/header/method được xác định rõ; không mở tùy tiện `Access-Control-Allow-Origin: *` cùng credentials.
- **CSRF** bảo vệ request thay đổi trạng thái khi browser tự gửi credentials như cookie; POST thiếu token có thể bị 403 ngay cả khi user có authority.
- **Cache-Control: no-store** hữu ích để tránh trung gian cache nhầm body lỗi chứa thông tin liên quan đến phiên người dùng.
- **WWW-Authenticate** là một phần quan trọng của HTTP Basic/Bearer 401; ví dụ demo tắt hai cơ chế login để kiểm thử riêng exception translation. Khi bật Basic/Bearer thực, cần để challenge của scheme phù hợp được phát ra thay vì tự xóa header.
- Trên request không có auth, `401` không có nghĩa backend đã kiểm tra quyền của object: nó mới yêu cầu xác thực.

### 5.3. Tại sao `@RestControllerAdvice` không thay thế cấu hình này?

`@RestControllerAdvice` xử lý lỗi xảy ra trong quá trình gọi handler/controller, nhưng **authorization có thể từ chối ngay trong WebFilter chain trước khi handler được gọi**. Vì thế không thể chỉ viết:

```java
// PHẢN VÍ DỤ: không thay thế exceptionHandling cho WebFilter.
@ExceptionHandler(AccessDeniedException.class)
public ResponseEntity<?> handle(AccessDeniedException ex) { ... }
```

Đoạn trên chỉ là biểu diễn ý tưởng, thiếu class/imports. Hãy cấu hình security exception handling tại WebFlux security chain, và dùng application exception handling cho validation/business/errors ở đúng ranh giới.

## 6. Phân biệt thiếu xác thực, thiếu quyền và CSRF trong kiểm thử

Một test HTTP đáng tin không chỉ xem `403`; nó cần xác định **ai chặn** và **controller có chạy không**.

```text
Trường hợp A:
  anonymous GET /api/docs/read
    -> 401 AUTHENTICATION_REQUIRED
    -> handler không chạy

Trường hợp B:
  alice (ROLE_USER) GET /api/docs/read
    -> 403 ACCESS_DENIED
    -> handler không chạy

Trường hợp C:
  alice (DOC_READ) GET /api/docs/read
    -> 200
    -> handler chạy

Trường hợp D:
  alice (DOC_CREATE) POST /api/docs
  không có CSRF token
    -> 403 (CSRF)
    -> handler không chạy

Trường hợp E:
  alice (DOC_CREATE) POST /api/docs
  kèm CSRF token
    -> 200
    -> handler chạy
```

**Đặc biệt:** nếu không gửi `csrf()` trong test POST, bạn không thể kết luận `@PreAuthorize` hoặc `hasAuthority("DOC_CREATE")` đã từ chối. CSRF có thể chặn trước khi authorization rule được xét.

## 7. Project Java 17+ dùng WebFlux Security và WebTestClient

Project chỉ có **một file Java test độc lập** trong `src/test/java`, khởi tạo Spring Boot WebFlux context và dùng `WebTestClient` gọi qua security filters. Không tạo tài khoản production; `mockUser` được Spring Security Test inject trên **test exchange** để mô phỏng authenticated principal.

### 7.1. Cấu trúc file

```text
webflux-denial-response/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ExceptionTranslationWebFilterTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'webflux-denial-response'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Spring Boot BOM quản lý các phiên bản phụ thuộc tương thích. Nếu đưa vào module chạy thật, thay `testImplementation` của các starter bằng `implementation` và xây dựng authentication tương ứng; demo không tự cung cấp một authentication provider production.

### 7.2. Java test hoàn chỉnh

Tạo `src/test/java/demo/ExceptionTranslationWebFilterTest.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    classes = ExceptionTranslationWebFilterTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "spring.main.web-application-type=reactive"
)
public class ExceptionTranslationWebFilterTest {

    public static class Probe {
        private final Map<String, AtomicInteger> hits =
            new ConcurrentHashMap<>();

        void hit(String route) {
            hits.computeIfAbsent(
                route, ignored -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String route) {
            AtomicInteger n = hits.get(route);
            return n == null ? 0 : n.get();
        }

        void reset() {
            hits.clear();
        }
    }

    @RestController
    public static class DemoController {
        private final Probe probe;

        public DemoController(Probe probe) {
            this.probe = probe;
        }

        @GetMapping("/public/ping")
        public Mono<Map<String, String>> publicPing() {
            probe.hit("public");
            return Mono.just(Map.of("ok", "true"));
        }

        @GetMapping("/api/docs/read")
        public Mono<Map<String, String>> read() {
            probe.hit("read");
            return Mono.just(Map.of("document", "D42"));
        }

        @GetMapping("/api/docs/admin")
        public Mono<Map<String, String>> admin() {
            probe.hit("admin");
            return Mono.just(Map.of("admin", "true"));
        }

        @GetMapping("/api/docs/account")
        public Mono<Map<String, String>> account() {
            probe.hit("account");
            return Mono.just(Map.of("authenticated", "true"));
        }

        @GetMapping("/api/docs/blocked")
        public Mono<Map<String, String>> blocked() {
            probe.hit("blocked");
            return Mono.just(Map.of("blocked", "false"));
        }

        @PostMapping("/api/docs")
        public Mono<Map<String, String>> create() {
            probe.hit("create");
            return Mono.just(Map.of("created", "true"));
        }
    }

    private static Mono<Void> jsonError(
            ServerWebExchange exchange,
            HttpStatus status,
            String fixedCode) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_JSON);
        response.getHeaders().setCacheControl("no-store");

        // fixedCode CHỈ nhận constant do server định nghĩa.
        // Không phản chiếu exception message/client input vào JSON.
        byte[] payload = (
            "{\"code\":\"" + fixedCode + "\"}"
        ).getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(payload)));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableWebFluxSecurity
    public static class Config {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DemoController demoController(Probe probe) {
            return new DemoController(probe);
        }

        @Bean
        SecurityWebFilterChain securityWebFilterChain(
                ServerHttpSecurity http) {
            return http
                .exceptionHandling(errors -> errors
                    .authenticationEntryPoint(
                        (exchange, authenticationException) ->
                            jsonError(
                                exchange,
                                HttpStatus.UNAUTHORIZED,
                                "AUTHENTICATION_REQUIRED"))
                    .accessDeniedHandler(
                        (exchange, deniedException) ->
                            jsonError(
                                exchange,
                                HttpStatus.FORBIDDEN,
                                "ACCESS_DENIED"))
                )
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/ping").permitAll()
                    .pathMatchers("/api/docs/read")
                        .hasAuthority("DOC_READ")
                    .pathMatchers("/api/docs/admin")
                        .hasAuthority("DOC_ADMIN")
                    .pathMatchers("/api/docs/account")
                        .authenticated()
                    .pathMatchers("/api/docs/blocked")
                        .denyAll()
                    .pathMatchers(
                        org.springframework.http.HttpMethod.POST,
                        "/api/docs")
                        .hasAuthority("DOC_CREATE")
                    .anyExchange().denyAll()
                )
                // Test chỉ kiểm tra exception translation với
                // mockUser; không mô phỏng cơ chế HTTP Basic/login.
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .csrf(Customizer.withDefaults())
                .build();
        }
    }

    @Autowired ApplicationContext applicationContext;
    @Autowired Probe probe;

    private WebTestClient web;

    @BeforeEach
    void setUp() {
        probe.reset();

        web = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient as(String name, String authority) {
        return web.mutateWith(
            mockUser(name).authorities(
                new SimpleGrantedAuthority(authority)));
    }

    @Test
    void publicEndpointPermitsAnonymous() {
        web.get().uri("/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.ok").isEqualTo("true");
        assertThat(probe.count("public")).isEqualTo(1);
    }

    @Test
    void anonymousReadTriggersAuthenticationEntryPoint() {
        web.get().uri("/api/docs/read").exchange()
            .expectStatus().isUnauthorized()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
        assertThat(probe.count("read")).isZero();
    }

    @Test
    void authenticatedWithoutReadGets403Json() {
        as("alice", "ROLE_USER")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
        assertThat(probe.count("read")).isZero();
    }

    @Test
    void authenticatedWithReadRunsHandler() {
        as("alice", "DOC_READ")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.document").isEqualTo("D42");
        assertThat(probe.count("read")).isEqualTo(1);
    }

    @Test
    void roleAdminDoesNotImplicitlyGrantDocRead() {
        as("admin", "ROLE_ADMIN")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isForbidden();
        assertThat(probe.count("read")).isZero();
    }

    @Test
    void accountRequiresOnlyAuthentication() {
        as("bob", "ROLE_USER")
            .get().uri("/api/docs/account").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.authenticated").isEqualTo("true");
        assertThat(probe.count("account")).isEqualTo(1);
    }

    @Test
    void anonymousAccountRequiresAuthentication() {
        web.get().uri("/api/docs/account").exchange()
            .expectStatus().isUnauthorized();
        assertThat(probe.count("account")).isZero();
    }

    @Test
    void docReadDoesNotGrantDocAdmin() {
        as("alice", "DOC_READ")
            .get().uri("/api/docs/admin").exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
        assertThat(probe.count("admin")).isZero();
    }

    @Test
    void docAdminAuthorityAllowsAdminRoute() {
        as("alice", "DOC_ADMIN")
            .get().uri("/api/docs/admin").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.admin").isEqualTo("true");
        assertThat(probe.count("admin")).isEqualTo(1);
    }

    @Test
    void denyAllRouteRejectsAuthenticatedCaller() {
        as("alice", "DOC_ADMIN")
            .get().uri("/api/docs/blocked").exchange()
            .expectStatus().isForbidden();
        assertThat(probe.count("blocked")).isZero();
    }

    @Test
    void unknownPathUsesDenyAllInsteadOfOpenAccess() {
        as("alice", "DOC_READ")
            .get().uri("/internal/debug").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithoutCsrfIsForbiddenEvenWithAuthority() {
        as("alice", "DOC_CREATE")
            .post().uri("/api/docs").exchange()
            .expectStatus().isForbidden();
        assertThat(probe.count("create")).isZero();
    }

    @Test
    void postWithCsrfAndAuthorityRunsHandler() {
        as("alice", "DOC_CREATE")
            .mutateWith(csrf())
            .post().uri("/api/docs").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.created").isEqualTo("true");
        assertThat(probe.count("create")).isEqualTo(1);
    }

    @Test
    void postWithCsrfButWrongAuthorityGets403() {
        as("alice", "DOC_READ")
            .mutateWith(csrf())
            .post().uri("/api/docs").exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
        assertThat(probe.count("create")).isZero();
    }

    @Test
    void anAllowedCallDoesNotAuthorizeLaterWrongPrincipal() {
        as("alice", "DOC_READ")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isOk();

        as("bob", "ROLE_USER")
            .get().uri("/api/docs/read").exchange()
            .expectStatus().isForbidden();

        assertThat(probe.count("read")).isEqualTo(1);
    }
}
```

**Tại sao test này có giá trị?** `bindToApplicationContext(...).apply(springSecurity())` đưa request qua reactive Spring Security filters; `mockUser` chỉ gắn Authentication tin cậy **trong test**. Khi handler bị chặn, `Probe` không tăng, chứng minh không có side effect của controller. Chúng ta không kết luận rằng controller tự bảo vệ được khi bị gọi qua một đường không-HTTP.

**Lưu ý import:** project trên cố ý **không sử dụng `MapReactiveUserDetailsService`** vì authentication được giả lập bằng Spring Security Test. Khi bổ sung user store reactive cho ứng dụng thực, phải dùng package phù hợp với Spring Security version, không lấy tên class từ tài liệu cũ/Servlet.

### 7.3. Chạy test

```bash
gradle test --tests demo.ExceptionTranslationWebFilterTest
```

Nếu có Gradle Wrapper: Linux/macOS dùng `./gradlew test --tests demo.ExceptionTranslationWebFilterTest`, Windows dùng `gradlew.bat test --tests demo.ExceptionTranslationWebFilterTest`.

**Kết quả kỳ vọng:** **15 test JUnit** thành công khi JDK, Gradle và các dependencies được thiết lập phù hợp, Gradle kết thúc bằng `BUILD SUCCESSFUL`. Đây là **kết quả thiết kế kỳ vọng, không phải stdout đã thực sự quan sát từ một lần chạy Java**. Báo cáo JUnit HTML: `build/reports/tests/test/index.html`.

### 7.4. Những điều được kiểm thử, và điều chưa được kiểm thử

| Nhóm test | Bằng chứng |
| --- | --- |
| Public route | `permitAll()` không yêu cầu xác thực |
| Anonymous + protected | `ServerAuthenticationEntryPoint` trả 401 JSON |
| Có identity, thiếu authority | `ServerAccessDeniedHandler` trả 403 JSON |
| Có authority | Handler thực sự được thực thi |
| ROLE_ADMIN ≠ DOC_READ | Authority không tự suy ra từ role tổng quát |
| `authenticated()` | Không đồng nghĩa với `hasAuthority(...)` |
| Admin route | `DOC_READ` không cấp `DOC_ADMIN` |
| `denyAll` và `anyExchange` | Không vô tình mở route lạ |
| POST không CSRF | 403 nhưng **không kết luận** custom access denied handler đã chạy |
| POST kèm CSRF, đủ authority | Handler chạy thành công |
| POST kèm CSRF, sai authority | 403 do authorization, body JSON chính sách |
| Đổi principal giữa requests | Quyền của Alice không tự áp dụng cho Bob |
| Probe | Những request bị từ chối không chạy controller body |

Bài test **không chạy network server thực**, không có JWT Bearer filter, OIDC login, HTTP Basic credentials, browser cookie, multi-tenant database, R2DBC hay distributed authz. Đó là những tầng phải bổ sung khi production dùng chúng. `WebTestClient` gắn với ApplicationContext vẫn kiểm tra đường WebFilter/handler của WebFlux thay vì gọi trực tiếp Java method.

## 8. Cấu hình thực tế với Basic, Bearer hoặc form login

### 8.1. Với HTTP Basic

Nếu dùng HTTP Basic và một `ServerAuthenticationEntryPoint` tùy biến, trả **401** kèm header `WWW-Authenticate: Basic realm="..."` để client biết cách lấy credentials, hoặc tái sử dụng `HttpBasicServerAuthenticationEntryPoint` phù hợp. Đừng sao chép nguyên handler JSON ở bài rồi bỏ header challenge trên hệ thống cần HTTP Basic.

Nếu client gửi Basic password sai, authentication failure handler có thể tạo 401 **trước khi một request được coi là authenticated**; không buộc mọi trường hợp 401 đều có cùng JSON body nếu chưa cấu hình đủ authentication failures.

### 8.2. Với OAuth2 Resource Server / Bearer

API Bearer token nên dùng Spring Security Resource Server và các server handlers hỗ trợ **Bearer challenge**, tuân theo RFC 6750. Ví dụ khung cấu hình:

```java
// Fragment: cần cấu hình JWT decoder, issuer/audience và
// dependency OAuth2 Resource Server thực tế.
http.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()));
```

Đừng tự bắt mọi lỗi JWT rồi trả `403`: missing/invalid token thường là tình huống **401**, trong khi token hợp lệ nhưng thiếu scope/quyền thường dẫn tới **403**. Các header `WWW-Authenticate` có ngữ nghĩa protocol và có thể do handler của resource server tạo.

### 8.3. Với form login và trình duyệt

Một ứng dụng HTML sử dụng `formLogin` có thể redirect `302` tới `/login` khi thiếu xác thực. Nếu cùng ứng dụng cung cấp JSON API và HTML pages, có thể cần **nhiều `SecurityWebFilterChain`** với `securityMatcher` rõ ràng hoặc một entry-point strategy theo `ServerWebExchangeMatcher`, tránh trả JSON 401 cho web login hoặc redirect HTML cho API clients mà không kiểm soát.

### 8.4. Đừng để custom handler phá phần còn lại của security

- Bảo tồn headers bảo mật và challenge của authentication scheme.
- Không bỏ CSRF trên endpoints dùng cookie credentials chỉ vì test POST bị 403.
- Không set mọi `AccessDeniedException` thành 200 kèm `{"allowed":false}`, vì status 2xx có thể bị client/intermediary coi là thành công.
- Không đưa exception message và stack trace vào response cho user.
- Không gọi `block()`/đồng bộ I/O trong custom handler; viết kết quả bằng `Mono<Void>`.
- Không ghi response body sau khi response đã committed; log ở server và xử lý lỗi theo WebFlux policies.
- Không biến `Mono.empty()` trong reactive authorization thành ALLOW khi policy thiếu dữ liệu.

## 9. Truy cập dữ liệu thật và lỗi object-level authorization

`ExceptionTranslationWebFilter` chỉ là lớp **dịch kết quả từ chối sang HTTP**. Một route `.hasAuthority("DOC_READ")` **chưa chứng minh** user được đọc mọi Document. Trong hệ thống đa tenant, cần kiểm tra object:

```java
// Fragment policy trong một ReactiveAuthorizationManager:
// authentication là Mono<Authentication>, exchange/context
// cung cấp tenant và docId từ path variables (không tự tin cậy).
return authentication.flatMap(auth ->
    repository.findByTenantAndId(
        trustedTenant(auth), requestedId)
      .map(doc -> allowedByOwnerAndState(auth, doc))
      .defaultIfEmpty(false));
```

Đây là code ý tưởng, cần application-specific methods. `requestedId` không được phép tự dùng để truy vấn tenant khác; `trustedTenant(auth)` phải được xác minh từ identity/membership. `403` hoặc `404` khi không có quyền là chính sách response riêng, không thay thế tenant-scoped SQL/RLS và kiểm tra dữ liệu tại nơi sử dụng.

Nếu HTTP manager kiểm tra quyền trước khi handler DELETE chạy, trạng thái object có thể đổi từ DRAFT sang APPROVED trong khoảng đó. Hãy thực hiện **conditional DELETE/UPDATE** theo tenant/owner/status trong transaction; exception translator không chống TOCTOU.

## 10. Troubleshooting

| Triệu chứng | Cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không đăng nhập nhưng nhận 403, không phải 401 | CSRF, custom anonymous config, entry point/chain được chọn | Xác định filter nào từ chối, không đoán từ status |
| Có credentials vẫn nhận 401 | Token/password không hợp lệ, authentication filter/failure handler | Test authentication riêng trước authz |
| Đăng nhập thành công nhưng nhận 403 | Thiếu authority, role prefix, tenant, policy hoặc CSRF | Kiểm tra `Authentication.getAuthorities()` và filter path |
| POST đủ quyền vẫn 403 | CSRF token chưa gửi | Test với `csrf()`, xác minh authz sau đó |
| Body custom không xuất hiện | Exception không đi qua handler này hoặc bị filter khác chặn | Tách test permission denial vs CSRF/auth failure |
| 302 thay vì JSON 401 | Form login entry point được kích hoạt | Phân tách security chain hoặc đổi entry point theo API |
| 401 thiếu `WWW-Authenticate` | JSON entry point tùy biến đã thay Basic/Bearer challenge | Dùng scheme-aware entry point/headers |
| 500 thay vì 403 | Business exception không phải `AccessDeniedException`, response committed, bug JSON | Dùng WebFlux error handling, không swallow mọi exception |
| 404 với route chưa khai báo dù muốn 403 | Matcher/chain khác đang xử lý, `anyExchange` không áp dụng | Test exact request mapping và securityMatcher |
| Permission handler chạy nhưng controller vẫn có side effect | Authorization áp dụng sau side effect, controller tự gọi, thiếu precheck | Thêm guard ở service, kiểm tra thứ tự và Probe |
| Client thấy tên resource dù không có quyền | Lộ dữ liệu qua exception body/log | Trả code chung, không phản chiếu exception.message |
| CORS preflight bị chặn | CORS configuration hoặc chain match sai | Cấu hình CORS có kiểm soát và test OPTIONS |
| Route khác vẫn mở khi thêm endpoint | `anyExchange().permitAll()` hoặc chain order | Dùng least privilege / denyAll mặc định |
| Test qua HTTP pass nhưng job truy cập trái quyền | Job không chạy WebFilter | Bảo vệ domain service và SQL riêng |

## 11. Kiểm thử nên có trước production

1. **Anonymous:** gọi từng route nhạy cảm không authentication; kiểm tra 401/challenge hoặc redirect đúng với authentication scheme.
2. **Authenticated, thiếu authority:** 403 và không thực thi handler.
3. **Authenticated, đúng authority:** 200/201/204 và side effect đúng.
4. **CSRF:** với browser credentials, test POST/PUT/PATCH/DELETE có token và không token; phân biệt nguồn 403.
5. **Error contract:** content type, JSON schema, `Cache-Control: no-store` nếu áp dụng; không xuất exception message, token, SQL.
6. **Wrong tenant/object:** user có quyền chức năng nhưng không có quyền trên object vẫn bị chặn.
7. **Method/route mismatch:** một endpoint có `GET` và `DELETE` nhưng quyền khác nhau; `anyExchange` không mở route ngoài ý định.
8. **Authentication failure:** Basic sai password, Bearer token invalid/expired, wrong issuer/audience; test 401 khác authorization deny.
9. **Multiple filter chains:** API vs browser, đúng entry point và request matcher trong từng chain.
10. **Error source:** Policy backend down không thành ALLOW; chọn 403/503 theo hợp đồng và log/alert.
11. **Cross-cutting:** CORS preflight, cache-control, security headers, rate limit, request size, proxy headers.
12. **Reactive correctness:** không `block()`, không tự `subscribe()`, không trả lỗi sau response đã committed.
13. **Method/repository-level security:** background jobs hoặc message consumers không được dựa duy nhất vào HTTP filter.
14. **Audit:** log correlation ID và loại từ chối an toàn; tránh ghi PII/token hoặc chính sách nội bộ nhạy cảm.

## 12. Bài tập

**Bài tập A — Basic challenge:** Thay demo thành HTTP Basic thật, tạo `MapReactiveUserDetailsService` và `PasswordEncoder` đúng version. Viết test missing credentials và bad password, xác minh `WWW-Authenticate` phù hợp.

**Bài tập B — Bearer:** Cấu hình Resource Server JWT, tạo test token hợp lệ không có scope `documents:read` và token không hợp lệ. Phân biệt 403 và 401/Bearer challenge.

**Bài tập C — JSON Problem Details:** Dùng RFC 9457 media type `application/problem+json`, trả `type`, `title`, `status` hợp lệ nhưng không phản chiếu message nội bộ. Test content type và schema.

**Bài tập D — Tenant:** Thêm `/api/tenants/{tenantId}/docs/{id}` và reactive policy. Anonymous nhận 401, user đúng tenant/đủ authority nhận 200, cùng authority nhưng sai tenant nhận 403 hoặc 404 theo quy định.

**Bài tập E — CSRF:** Giữ nguyên Cookie session, POST với và không có `csrf()`; bổ sung xác minh controller không được chạy ở đường thiếu token.

**Bài tập F — Hai security chains:** Phân biệt `/api/**` yêu cầu JSON 401 với `/web/**` redirect login; kiểm thử thứ tự `securityMatcher` và entry points.

**Bài tập G — Controller error:** Tạo route được phép nhưng ném `IllegalArgumentException`. Chứng minh error response thuộc application exception handling, không bị đánh dấu ngẫu nhiên thành 403.

**Bài tập H — Race:** Một DELETE được HTTP authorization cho phép, nhưng bản ghi bị chuyển sang APPROVED trước khi ghi. Dùng SQL conditional DELETE và xác nhận không có side effect.

## 13. Tổng kết

`ExceptionTranslationWebFilter` là thành phần **chuyển ngoại lệ bảo mật thành phản hồi HTTP phù hợp** trong Spring Security WebFlux:

- Thiếu authentication: xử lý qua **`ServerAuthenticationEntryPoint`**, thường 401/challenge hoặc redirect.
- Authenticated nhưng thiếu quyền: xử lý qua **`ServerAccessDeniedHandler`**, thường 403.
- CSRF hoặc authentication failure ở filter khác có thể cũng dẫn đến 401/403 nhưng **không nhất thiết đi qua custom handler này**.
- Business exceptions, validation, resource not found và server failure cần cơ chế xử lý lỗi thích hợp, **không quy hết về 403**.

Cấu hình bằng `ServerHttpSecurity.exceptionHandling(...)`, không tự đăng ký trùng WebFilter. Kiểm thử bằng `WebTestClient` để chứng minh **status đúng, JSON an toàn và controller không chạy khi bị từ chối**, đồng thời giữ phân quyền thực tế ở service/repository.

## Tài liệu tham khảo

- Spring Security 6.5 API — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Security 6.5 API — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.5 API — `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security 6.5 API — `HttpStatusServerEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/HttpStatusServerEntryPoint.html
- Spring Security 6.5 — WebFlux HTTP Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — WebFlux CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — WebFlux Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/index.html
- HTTP Semantics — 401, 403 (RFC 9110): https://www.rfc-editor.org/rfc/rfc9110
- HTTP Authentication — Basic (RFC 7617) và Bearer (RFC 6750): https://www.rfc-editor.org/rfc/rfc7617 ; https://www.rfc-editor.org/rfc/rfc6750
