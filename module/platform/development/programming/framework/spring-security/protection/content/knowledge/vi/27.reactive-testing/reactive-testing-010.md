# Đối chiếu filter giả lập với HTTP server thực

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Mục tiêu:** So sánh đường đi request qua **WebFlux WebFilters/Spring Security** trong `WebTestClient` mock với đường đi qua **HTTP server thật**. Xác minh CSRF, CORS preflight, HTTP firewall, security headers, session cookie, authentication, redirect và ranh giới reverse proxy mà không đánh đồng “test xanh trên mock” với “trình duyệt ngoài Internet đã được bảo vệ”.  
> **Ngữ cảnh phiên bản:** Spring Framework 6.2/7.x, Spring Security 6.5/7.x, Spring Boot 3.5/4.x, Java 17+, JUnit Jupiter. Ví dụ chọn **Spring Boot 3.5 imports** khi nhắc tới test annotations; Boot 4 có package tương ứng. Cần dùng các artifacts tương thích theo BOM.

## 1. Tình huống: mock trả 200 nhưng browser thật bị 401/403

Một nhóm phát triển có test sau:

```java
client.mutateWith(mockUser("alice"))
    .mutateWith(csrf())
    .post().uri("/secure/orders")
    .exchange()
    .expectStatus().isCreated();
```

Test xanh và controller tạo đơn. Nhưng SPA ngoài đời gửi `POST /secure/orders` nhận 403, hoặc login thật vẫn nhận 401. Hai kết quả **không nhất thiết mâu thuẫn**:

- `mockUser("alice")` đặt một authentication **giả lập** vào mock exchange, không gửi Basic password, form cookie hay chữ ký JWT qua mạng.
- `csrf()` từ `spring-security-test` cho mock request có điều kiện CSRF hợp lệ, **không** chứng minh browser đã bootstrap token, lưu `SESSION` cookie và gửi token thật.
- `WebTestClient.bindToApplicationContext` dựng WebFlux handler chain với mock request/response, **không mở socket TCP**. Vì thế nó không tự kiểm HTTP parser, TLS termination, ingress rewrite, cookie browser restrictions hoặc network timeout.
- Khi chạy `@SpringBootTest(webEnvironment = RANDOM_PORT)`, client gọi HTTP server bằng credentials/cookie/header **thật**. Thất bại lúc đó có thể chỉ ra đúng đường biên integration còn thiếu test.

**Bài học trọng tâm:** test mock trả lời “Security WebFilters và handler phản ứng thế nào với một `ServerWebExchange` có đầu vào đã dựng?”, còn test live trả lời “một HTTP request đi qua socket/server adapter rồi vào filters có đúng kết quả không?”. Trình duyệt HTTPS sau CDN/proxy là tầng kiểm chứng thứ ba.

### 1.1. Mục tiêu đạt được

Sau bài này, người học có thể:

1. Mô tả `WebTestClient.bindToController`, `bindToApplicationContext`, `bindToServer`, `@WebFluxTest`, `@SpringBootTest(MOCK/RANDOM_PORT)` và khi nào chọn từng loại.
2. Dựng cùng một fixture gồm global `WebFilter`, `SecurityWebFilterChain`, controller và side-effect counter; chạy bộ test **mock** và **HTTP thật** với cùng policy.
3. Kiểm thử positive/negative cho authentication, authorization, CSRF, CORS preflight và response headers; hiểu vì sao mock mutators không thay credentials thật.
4. Bootstrap `Mono<CsrfToken>`/`WebSession` và tự gửi cookie/token qua HTTP thật, không dùng `csrf()` bypass.
5. Phân biệt HTTP firewall, URL normalization, HTTP method/parser và proxy rejection với kết quả từ business controller.
6. Kiểm HTTP 3xx `Location`/headers và HTTPS/HSTS mà không tự nhận mock HTTPS là TLS handshake.
7. Đối chiếu dữ liệu bất biến nên giống nhau giữa hai tầng với những yếu tố **không nên** assert bằng nhau (port, session ID, `Date`, timing).
8. Tổ chức test isolation, CI test matrix và runbook chẩn đoán các sai lệch mock/live.

## 2. Hai đường đi request khác nhau từ đầu đến đâu?

### 2.1. Mock `bindToApplicationContext`

```text
JUnit
  |
  v
WebTestClient.bindToApplicationContext(context)
  |
  v
MockServerHttpRequest / MockServerHttpResponse
  |
  v
WebHttpHandlerBuilder / HttpWebHandlerAdapter
  |
  +--> Global WebFilter(s)
  |      +--> Spring Security WebFilterChainProxy
  |              +--> ServerWebExchangeFirewall
  |              +--> SecurityWebFilterChain
  |                       +--> CSRF / authentication / authorization
  |                       +--> security response headers
  +--> DispatcherHandler / annotated controller
  |
  v
WebTestClient response assertions

Không có HTTP listener/TCP connection/TLS handshake/edge proxy.
```

`bindToApplicationContext` lấy Spring WebFlux configuration, WebFilter beans và controller declarations từ **cùng ApplicationContext**. Khi áp dụng `springSecurity()` theo Spring Security Test docs, các mock security configurers như `mockUser()`/`csrf()` có hiệu lực.

Tuy vậy, **test context không tự giống production** nếu:

- `@WebFluxTest` slice bỏ custom `SecurityWebFilterChain`/CORS/global filter khỏi context.
- Test profile nạp cấu hình khác production.
- Bạn tự viết `bindToController(new Controller(...))` nhưng không cung cấp Security WebFilters.
- Một `@MockitoBean` đã thay auth repository/CSRF repo/decoder thật bằng mock.

### 2.2. HTTP server thật với `RANDOM_PORT`

```text
WebTestClient.bindToServer / @AutoConfigureWebTestClient
  |
  v
HTTP client connector (TCP, HTTP headers, body, connection)
  |
  v
localhost:<random-port> (Reactor Netty trong Boot WebFlux mặc định)
  |
  v
HTTP parser / server adapter -> ServerHttpRequest
  |
  v
HttpWebHandlerAdapter -> Global WebFilters
  |
  +--> CorsWebFilter (nếu được đặt trước Security)
  +--> WebFilterChainProxy / reactive firewall / SecurityWebFilterChain
  +--> DispatcherHandler / controller
  |
  v
HTTP response bytes qua socket -> client assertions
```

`RANDOM_PORT` là **server HTTP thật**, thường không có TLS ở local test trừ khi cấu hình HTTPS server. Nó vẫn không đồng nghĩa đi qua **production CDN/WAF/ingress**, và cũng chưa chứng minh trình duyệt thực thi SameSite, CSP hay HSTS.

### 2.3. Tầng thứ ba: browser HTTPS qua public entry point

```text
Browser (Fetch/SOP/CORS/SameSite/CSP/HSTS)
   |
   +--> HTTPS/TLS to CDN/WAF
              |
              +--> optional HTTP -> HTTPS redirect
              +--> optional CORS preflight handling
              +--> path/host/header rewriting
              |
              v
          Gateway/Ingress
              |
              v
          WebFlux app HTTP or HTTPS
```

Khi nói “HTTP server thực”, hãy ghi rõ **thực đến đâu**: `RANDOM_PORT` nội bộ, app staging trực tiếp, hay hostname public sau edge. Những mức ấy có câu trả lời khác nhau về CSP trên HTML, HSTS và cookie flags.

## 3. Bảng so sánh các kiểu setup

| Kiểu test | Có full Spring WebFilters? | Có server socket? | Mock principal/CSRF mutators? | Mục đích |
| --- | --- | --- | --- | --- |
| `bindToController` | Không tự có global app filters | Không | Chỉ khi dựng Security test setup phù hợp | Unit controller và route/body mapping |
| `bindToRouterFunction` | Không tự có full app context | Không | Tùy setup | Functional endpoint riêng |
| `bindToApplicationContext` + `springSecurity()` | **Có** với WebFlux/Security beans trong context | Không | **Có** | Filter/Security integration nhanh |
| `@WebFluxTest` | **Slice**, tùy bean được nạp/import | Không mặc định | Có khi setup phù hợp | Web layer isolation |
| `@SpringBootTest(MOCK)` + WebTestClient | Full test context (theo profile) | Không | Có với mock binding/setup phù hợp | Full wiring nhưng mock request |
| `@SpringBootTest(RANDOM_PORT)` | Full test context (theo profile) | **Có** | **Không dùng** mock mutators qua TCP | HTTP adapter/auth/cookies/filters thật |
| `WebTestClient.bindToServer()` | Không nạp context trong client; gọi server đã chạy | **Có** | Không | Test endpoint server bất kỳ |
| Browser E2E HTTPS | Theo topology public | Có + TLS + browser policy | Không | Xác nhận end-user CORS/CSP/cookie/HSTS |

> **Cần hiểu đúng “full WebFilters”:** `bindToApplicationContext` chạy **các filter beans trong context đã nạp**, không bảo đảm context ấy đã chứa mọi custom bean của ứng dụng thật. `bindToController` không phải phép thử đại diện cho security filter chain production nếu không chủ động lắp đặt nó.

## 4. Những gì thường giống và khác giữa mock và live

| Thuộc tính | Nên giống khi cùng Security config | Có thể khác hợp lệ |
| --- | --- | --- |
| Protected path yêu cầu authentication | Có | Entry point/status khác nếu test profile/chain khác — **cần điều tra** |
| POST thiếu CSRF bị từ chối | Có | Response body/timing/headers từ adapter khác |
| CORS origin/method/header allowlist | Có | Edge/proxy có thể thêm, sửa, chặn preflight |
| Header `X-Content-Type-Options`, CSP đã cấu hình | Có trên response do cùng chain tạo | HTTP parser/edge response không chạy Spring writer |
| HSTS trên HTTPS | Có khi request được nhận là secure | HTTP local **không** nên có HSTS |
| Side-effect counter nếu request bị chặn | Không tăng | Timing/race khi app fire-and-forget có thể khác; đó là bug cần sửa |
| Session cookie & CSRF token **giá trị** | Chỉ đúng semantics | IDs/tokens random, không so byte-by-byte |
| `Date`, `Server`, `Connection`, `Transfer-Encoding` | Không cần giống | Server adapter/gateway sở hữu hoặc thay đổi |
| `Location` redirect | Public contract về đích/method | Absolute/relative representation, port/proxy tùy cấu hình |
| URL encoded bytes, invalid HTTP headers | Không chắc giống | HTTP client/server parser và proxy có thể reject trước filters |
| Latency, backpressure, connection pooling | Không | Chỉ live HTTP mới bộc lộ network/transport behavior |

**Không ép các test cho ra toàn bộ raw HTTP response giống hệt nhau.** So sánh **invariants của policy** và ghi rõ những khác biệt do transport/lớp sở hữu response.

## 5. Chọn dependencies và xác nhận WebFlux chứ không phải MVC

### 5.1. Gradle theo Spring Boot BOM

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu dùng Maven, cần `spring-boot-starter-webflux` và `spring-boot-starter-security` runtime, `spring-boot-starter-test` và `spring-security-test` với scope test. Đừng tự pin Spring Security 7 lên một Spring Boot/Framework version không tương thích.

### 5.2. Tên classes cần đúng stack

| Servlet MVC | Reactive WebFlux |
| --- | --- |
| `HttpSecurity`, `SecurityFilterChain` | `ServerHttpSecurity`, `SecurityWebFilterChain` |
| `OncePerRequestFilter` | `WebFilter` |
| `HttpServletRequest`/`HttpServletResponse` | `ServerWebExchange`, `ServerHttpRequest` |
| `MockMvc` | `WebTestClient` |
| `SecurityMockMvcRequestPostProcessors.csrf()` | `SecurityMockServerConfigurers.csrf()` |
| `StrictHttpFirewall` | `StrictServerWebExchangeFirewall` (Security 6.4+) |
| `org.springframework.web.filter.CorsFilter` | `org.springframework.web.cors.reactive.CorsWebFilter` |

Nếu dự án tình cờ mang cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn MVC theo classpath rules trừ khi ép `spring.main.web-application-type=reactive`. Kiểm tra application type và actual server; **không** mặc định dùng WebFlux WebFilter trong một app đang chạy MVC.

### 5.3. Spring Boot version của test annotations

```java
// Spring Boot 3.5:
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;

// Spring Boot 4:
// import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
```

Các examples dưới đây dùng **Boot 3.5 package**. Boot 4 có module/test starter tách theo stack và import trên là tương ứng; không đưa cả hai imports vào một class. `@SpringBootTest` nằm ở `org.springframework.boot.test.context.SpringBootTest` trong cả hai dòng.

### 5.4. Không gọi build/tests tại STEP 4

Đây là bài viết Knowledge theo quy trình biên soạn. Người học có thể thực hành:

```bash
./gradlew test --tests '*MockTransportSecurityTest'
./gradlew test --tests '*LiveTransportSecurityTest'
./mvnw test
```

Nhưng nội dung đang ở STEP 4 **chưa có xác nhận thực thi** trên một dự án hoàn chỉnh. QA học thuật, bản build và integration CI sẽ được kiểm riêng theo quy trình sau.

## 6. Fixture chung: cùng một ứng dụng cho cả mock và HTTP server

Ta dựng một ứng dụng nhỏ với những thành phần sau:

```text
SideBySideDemoApplication (Spring Boot WebFlux)
 |
 +-- CorsWebFilter (global, order sớm nhất)
 |     +-- allowed Origin: https://spa.example.test
 |     +-- /secure/**, /csrf
 |
 +-- DiagnosticWebFilter (chỉ profile security-test)
 |     +-- X-Demo-Filter: visited
 |
 +-- SecurityWebFilterChain
 |     +-- /public/**, /csrf permitAll
 |     +-- /secure/** authenticated
 |     +-- CSRF enabled (WebSession repository)
 |     +-- HTTP Basic cho test credential thật
 |     +-- CSP explicit + default security headers
 |
 +-- DemoController
       +-- GET /public/ping
       +-- GET /public/redirect
       +-- GET /csrf (consume Mono<CsrfToken>)
       +-- GET /secure/whoami
       +-- POST /secure/orders (side effect count)
```

**Điều kiện quan trọng:** Không dùng một Security config cho mock rồi một Security config khác cho live. Cả hai phải lấy **cùng app classes, profile và policy**, nếu không bạn sẽ so hai hệ thống khác nhau và kết luận thiếu cơ sở.

### 6.1. Điểm khởi động Spring Boot

```java
package com.example.transport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SideBySideDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SideBySideDemoApplication.class, args);
    }
}
```

Đặt config, filter, controller bên dưới cùng package `com.example.transport` hoặc package con để component scan tìm thấy chúng.

### 6.2. Store đếm nghiệp vụ để phát hiện request bị chặn vẫn gây side effect

```java
package com.example.transport;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class OrderLedger {
    private final AtomicInteger created = new AtomicInteger();

    public int count() {
        return created.get();
    }

    public void record() {
        created.incrementAndGet();
    }

    public void resetForTests() {
        created.set(0);
    }
}
```

`OrderLedger` là **singleton test fixture**. Các test methods dùng `@BeforeEach` để reset và **không chạy song song** khi chia sẻ cùng instance. Trong production, kiểm side effect ở repository/database hoặc outbox bằng namespace riêng; `AtomicInteger` không phải cơ chế persistence thực.

### 6.3. Global `WebFilter` có dấu hiệu kiểm tra rõ ràng

```java
package com.example.transport;

import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Profile("security-test")
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class DiagnosticWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        exchange.getResponse().getHeaders()
            .set("X-Demo-Filter", "visited");
        return chain.filter(exchange);
    }
}
```

**Đây là filter chẩn đoán chỉ cho test**, không phải security header cho production. Marker `X-Demo-Filter` cho biết **request đã đi qua global filter này**, chứ không tự chứng minh tất cả Security WebFilters/authorization đã chạy. Vì filter được đặt trước Spring Security, cả HTTP 401/403 do Security tạo có thể vẫn mang marker.

Nếu request bị parser/gateway từ chối **trước** WebFlux, marker sẽ không xuất hiện. Nhưng **marker không xuất hiện không đủ kết luận parser gây lỗi**: một CORS preflight có thể được filter CORS sớm hơn xử lý và short-circuit.

### 6.4. Global CORS filter được đặt trước marker và Security

```java
package com.example.transport;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class BrowserCorsConfig {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    CorsWebFilter corsWebFilter() {
        CorsConfiguration policy = new CorsConfiguration();
        policy.setAllowedOrigins(
            List.of("https://spa.example.test"));
        policy.setAllowedMethods(
            List.of("GET", "POST", "OPTIONS"));
        policy.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "Authorization"));
        policy.setAllowCredentials(true);
        policy.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/secure/**", policy);
        source.registerCorsConfiguration("/csrf", policy);
        return new CorsWebFilter(source);
    }
}
```

Đúng WebFlux package là `org.springframework.web.cors.reactive.CorsWebFilter`, **không** phải Servlet `org.springframework.web.filter.CorsFilter`. Chỉ cấp phép cụ thể origin/method/header cần thiết. `allowCredentials(true)` không được kết hợp với wildcard `allowedOrigins("*")`.

`Authorization` được allowlist để browser SPA **có thể xin phép gửi** HTTP Basic/Bearer header khi flow thật cần; việc cho phép tên header qua CORS **không** xác thực nội dung hoặc cấp quyền của credential. Các tests preflight bên dưới chỉ yêu cầu `content-type,x-csrf-token` để tập trung vào CSRF, nhưng khi SPA gửi Authorization, bổ sung testcase `Access-Control-Request-Headers: authorization,content-type,x-csrf-token`.

Với cấu hình này:

- Preflight OPTIONS `/secure/orders` từ `https://spa.example.test` được **CorsWebFilter** xử lý trước Security, không cần Basic/cookie.
- Một actual GET/POST có Origin hợp lệ đi qua filter CORS, rồi mới đến `DiagnosticWebFilter` và Spring Security.
- CORS preflight bị short-circuit **không chạy marker filter**; đây là kết quả được thiết kế chứ không phải test thiếu Security.
- `/public/ping` không có CORS mapping. GET same-origin vẫn hoạt động; JavaScript cross-origin không tự được đọc response.

### 6.5. Spring Security chain: giữ CSRF, dùng HTTP Basic test-only

```java
package com.example.transport;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class DemoSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/csrf").permitAll()
                .pathMatchers("/secure/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults())
            // Global CorsWebFilter đã sở hữu CORS.
            .cors(cors -> cors.disable())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; "
                    + "object-src 'none'; "
                    + "frame-ancestors 'none'"
                ))
            )
            .build();
    }

    @Bean
    @Profile("security-test")
    MapReactiveUserDetailsService testUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password("{noop}test-password")
                .roles("USER").build(),
            User.withUsername("bob")
                .password("{noop}test-password")
                .roles("USER").build()
        );
    }
}
```

`{noop}` chỉ dành cho test profile. Trong ứng dụng production không được dùng plaintext password/noop encoder và phải cấu hình authentication phù hợp (hash password, OIDC, JWT...). Cấu hình `formLogin.disable()` giúp những test anonymous protected route trong ví dụ nhận 401 HTTP Basic, không bị redirect đến login page.

**Vì sao `.cors(cors -> cors.disable())` ở đây hợp lý?** Chúng ta đã đăng ký một global `CorsWebFilter` chạy **trước** Spring Security và muốn tránh hai CORS processors cùng tạo `Access-Control-Allow-Origin`. Trong một app **không có global filter**, disabling Security CORS sẽ khiến SPA cross-origin hoạt động sai. Phương án thay thế là **bỏ global filter** và bật `ServerHttpSecurity.cors(...)` với Reactive `CorsConfigurationSource`, nhưng phải dùng **một** chính sách được kiểm thử nhất quán.

### 6.6. Controller để so từng kết quả

```java
package com.example.transport;

import java.net.URI;
import java.security.Principal;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record CreateOrder(String sku) {}
    public record OrderReceipt(String owner, String sku) {}
    public record CsrfPayload(String headerName, String token) {}

    private final OrderLedger ledger;

    public DemoController(OrderLedger ledger) {
        this.ledger = ledger;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/public/redirect")
    public Mono<ResponseEntity<Void>> redirect() {
        return Mono.just(ResponseEntity
            .status(HttpStatus.SEE_OTHER)
            .location(URI.create("/public/ping"))
            .build());
    }

    @GetMapping("/secure/whoami")
    public Mono<String> whoami(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }

    @PostMapping("/secure/orders")
    public Mono<ResponseEntity<OrderReceipt>> createOrder(
            Mono<Principal> principal,
            @RequestBody Mono<CreateOrder> body) {
        return Mono.zip(principal, body).map(tuple -> {
            ledger.record();
            return ResponseEntity.status(HttpStatus.CREATED)
                .body(new OrderReceipt(
                    tuple.getT1().getName(),
                    tuple.getT2().sku()));
        });
    }

    @GetMapping("/csrf")
    public Mono<ResponseEntity<CsrfPayload>> csrf(
            ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());
        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CsrfWebFilter was not applied"));
        }
        return token.map(t -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(
                t.getHeaderName(), t.getToken())));
    }
}
```

`GET /csrf` **consume `Mono<CsrfToken>`** khi trả response, tạo điều kiện để WebSession repository sinh/lưu expected token và cấp cookie phiên phù hợp. Lấy attribute `Mono` rồi không subscribe là một test khác, không chứng minh CSRF bootstrap thành công.

Trong Spring Security WebFlux 6.x/7.x, token expose có thể dùng XOR masking chống BREACH; vì thế **không tự thay bằng raw token**. Client lấy `CsrfPayload.token()` trả về và gửi cùng cookie phiên; mock `csrf()` helper chỉ phục vụ các test khác.

### 6.7. Quy tắc fixture khi triển khai

- Tạo tất cả classes trong cùng package root để `@SpringBootApplication` scan được.
- Bật profile `security-test` **cho cả mock và live classes**, để cùng test user store và marker filter được nạp.
- Không chạy các tests dùng `OrderLedger.resetForTests()` song song trên cùng cached context.
- Controller không ghi log password, session ID, CSRF token hay authorization header.
- Endpoint `GET /csrf` phải `no-store`, không để CDN cache token cá nhân hóa.
- Không đưa marker `X-Demo-Filter` hoặc test user store vào production profile.

## 7. Lớp A: mock HTTP qua `bindToApplicationContext`

Mục tiêu của lớp mock là **xác nhận behavior của WebFilters/Security/controller**, không kiểm password hay session cookie qua TCP.

### 7.1. Setup toàn application context, không chỉ controller

```java
package com.example.transport;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringBootTest(
    classes = SideBySideDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@ActiveProfiles("security-test")
class MockTransportSecurityTest {

    @Autowired ApplicationContext context;
    @Autowired OrderLedger ledger;

    WebTestClient mock;

    @BeforeEach
    void setup() {
        // Giả định suite dùng ledger singleton chạy tuần tự.
        ledger.resetForTests();
        mock = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .baseUrl("http://localhost")
            .build();
    }

    // Các @Test mục 7–9 nằm trong lớp này.
}
```

`@SpringBootTest(MOCK)` **không mở socket**. `bindToApplicationContext` gắn vào Spring WebFlux `ApplicationContext`, `apply(springSecurity())` cung cấp test integration để áp dụng `mockUser()`/`csrf()`. Khi lớp trên dùng cùng application class/profile với live class ở mục 10, đối chiếu behavior có ý nghĩa.

Nếu `@SpringBootTest` chưa biết web application là reactive do dự án lẫn MVC, cần chỉnh dependencies hoặc chỉ định `spring.main.web-application-type=reactive` đúng theo yêu cầu ứng dụng. Không ép property rồi giả vờ production cũng dùng Reactive nếu server thực vẫn MVC.

### 7.2. Test marker của global WebFilter trên public GET

```java
@Test
void mockPublicGetPassesDiagnosticWebFilter() {
    mock.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff")
        .expectBody(String.class).isEqualTo("pong");
}
```

Test này chứng minh **marker filter và Security header writer đều có mặt** trong mock application context. Nó **không** chứng minh server socket đã chạy — đó là mục đích của lớp live.

### 7.3. Anonymous request không được đi tới protected handler

```java
@Test
void mockAnonymousGetIsDeniedBySecurity() {
    mock.get().uri("/secure/whoami")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited");
}
```

Vì fixture bật HTTP Basic và tắt form login, anonymous protected request trả 401. Nếu app dùng form login, anonymous có thể nhận 302 `/login`; test phải so với **entry point của chain được chọn**, không gán cố định 401 cho tất cả ứng dụng.

### 7.4. `mockUser()` cho test authorization, không gọi password provider

```java
@Test
void mockUserCanReachHandlerWithoutHttpCredentials() {
    mock.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/secure/whoami")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");

    // Baseline anonymous KHÔNG bị mutate bởi request Alice.
    mock.get().uri("/secure/whoami")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Hai assertions cùng test giúp phát hiện tình huống vô tình lưu client đã `mockUser` vào field `mock`, khiến anonymous test sau hưởng principal Alice.

### 7.5. POST mock thiếu CSRF phải bị chặn, không có side effect

```java
@Test
void mockPostWithUserButWithoutCsrfIsForbidden() {
    mock.mutateWith(mockUser("alice"))
        .post().uri("/secure/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new DemoController.CreateOrder("BOOK-01"))
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, ledger.count());
}
```

Nếu test trên nhận 201, cần kiểm `SecurityWebFilterChain` có thật sự bật CSRF không, request có đi đúng chain không, và `WebTestClient` có được cấu hình `csrf()` ở baseline khiến token hợp lệ được gửi từ trước hay không.

### 7.6. POST mock `csrf()` chỉ là positive control

```java
@Test
void mockPostCanPassWhenCsrfConditionIsSimulated() {
    mock.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/secure/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new DemoController.CreateOrder("BOOK-02"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited")
        .expectBody(DemoController.OrderReceipt.class)
        .value(body -> {
            assertEquals("alice", body.owner());
            assertEquals("BOOK-02", body.sku());
        });

    assertEquals(1, ledger.count());
}
```

Test này chứng minh Security/handler chạy đúng **khi test infrastructure giả lập điều kiện CSRF hợp lệ**. Nó **không** kiểm `GET /csrf`, WebSession repository, HSTS cookie flags, Basic authentication password hoặc browser fetch.

### 7.7. Kiểm header và redirect trên mock response

```java
@Test
void mockRedirectHasSafeLocationAndSecurityHeaders() {
    mock.get().uri("/public/redirect")
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.SEE_OTHER)
        .expectHeader().valueEquals(
            "Location", "/public/ping")
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");
}

@Test
void mockCspMatchesConfiguredPolicy() {
    mock.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().value(
            "Content-Security-Policy",
            value -> assertTrue(
                value.contains("frame-ancestors 'none'")));
}
```

`Content-Security-Policy` trong fixture là **explicit**, không phải một CSP đầy đủ được Spring Security tự thêm mặc định. Trên production, nếu HTML được CDN phục vụ, CSP của JSON API **không** bảo vệ HTML bên CDN; cần test response owner thực.

## 8. Mock CORS preflight: filter trước Security có thực sự short-circuit?

### 8.1. Preflight đúng cấu trúc không có credentials

Theo Spring WebFlux `CorsUtils.isPreFlightRequest`, preflight có method OPTIONS, `Origin` và `Access-Control-Request-Method`. `Access-Control-Request-Headers` chỉ cần khi actual request có những headers browser phải xin phép, **không phải điều kiện bắt buộc để nhận diện preflight**.

```java
@Test
void mockAllowedPreflightSkipsSecurityAndDiagnosticFilter() {
    mock.options().uri("/secure/orders")
        .header("Origin", "https://spa.example.test")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://spa.example.test")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true")
        .expectHeader()
            .doesNotExist("X-Demo-Filter");

    assertEquals(0, ledger.count());
}
```

**Vì `CorsWebFilter` được đặt trước `DiagnosticWebFilter`**, preflight được xử lý trực tiếp tại CORS filter, nên không có marker. Đó là dấu hiệu **thứ tự đúng**; không phải “Security test bị bypass” theo nghĩa sai. Browser cũng không cần gửi cookie/session/CSRF token ở preflight.

### 8.2. Origin lạ bị từ chối trước handler

```java
@Test
void mockUntrustedOriginPreflightIsRejected() {
    mock.options().uri("/secure/orders")
        .header("Origin", "https://attacker.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader()
            .doesNotExist("Access-Control-Allow-Origin");
    assertEquals(0, ledger.count());
}
```

Trong fixture có policy match path nhưng origin không được phép, `DefaultCorsProcessor` thường trả 403. **Không** mặc định mọi CORS deny luôn trả 403: nếu source không có policy cho URL, filter có thể trả 200 **nhưng không có ACAO**, và browser vẫn không cho phép cross-origin.

### 8.3. OPTIONS thiếu preflight headers có thể đi tiếp Security

```java
@Test
void bareOptionsIsNotPreflight() {
    mock.options().uri("/secure/orders")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited");
}
```

Ở fixture này, OPTIONS không có Origin/`Access-Control-Request-Method` được chuyển tiếp tới Security; anonymous bị 401. Không viết test harness gửi một OPTIONS trống rồi dùng kết quả đó để kết luận **CORS preflight** đã bị auth filter chặn.

### 8.4. Actual request khác preflight

```java
@Test
void mockActualCorsGetStillNeedsAuthentication() {
    mock.get().uri("/secure/whoami")
        .header("Origin", "https://spa.example.test")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://spa.example.test")
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited");
}
```

Đây là cặp assertions quan trọng:

- CORS đã xác nhận origin được phép **đọc response** theo browser CORS protocol.
- Security vẫn yêu cầu **authentication** đối với protected resource.

CORS allow-origin không tương đương `permitAll()`. Preflight pass không có nghĩa actual POST được bỏ qua CSRF hoặc authorization.

## 9. Mock không nên dùng để “giả lập” mọi lỗi transport

### 9.1. Vì sao mock filters không kiểm HTTP parser?

`MockServerHttpRequest` cho phép tạo request object trực tiếp. Một HTTP client thật có thể:

- tự normalize URI trước khi gửi,
- từ chối header chứa CR/LF,
- thay `Transfer-Encoding` hoặc `Content-Length`,
- encode body theo charset,
- tái sử dụng connection, có timeout, buffer/compress response,
- gửi HTTP/2 hay HTTP/1.1 tùy server/cấu hình.

Vì vậy không dùng một mock `ServerWebExchange` có header/URI bất thường để suy chắc request bytes đó sẽ vượt qua parser Reactor Netty hoặc ingress. Ngược lại, khi parser đã reject HTTP bytes, filter/handler Spring **không có cơ hội xử lý**.

### 9.2. Thử HTTP firewall cần chính xác phạm vi

Spring Security **6.4+** hỗ trợ Reactive `ServerWebExchangeFirewall`; mặc định `StrictServerWebExchangeFirewall` trong `WebFilterChainProxy` từ chối các request bất thường như double slash, semicolon hoặc percent-encoding đáng ngờ theo policy. Nhưng:

```text
Raw HTTP request
   -> Client URL normalizer?
   -> Ingress HTTP parser/rewriter?
   -> Reactor Netty parser?
   -> Spring WebFlux HttpHandler adapter?
   -> StrictServerWebExchangeFirewall?
   -> SecurityWebFilterChain matcher?
   -> Controller?
```

Nếu mỗi tầng đã normalize/reject khác nhau, có thể có 400/403/404 khác nhau cho cùng **ý định tấn công**. Đừng assert rằng một URL bất thường phải cho raw response giống nhau ở mock và live; hãy assert security invariant: **không được chạy handler/side effect hoặc bypass authorization**.

### 9.3. Tests có thể khác mà vẫn đúng

| Request bất thường | Mock/Live có thể khác ở đâu? | Bất biến cần giữ |
| --- | --- | --- |
| `/secure//orders` | URL normalization/client/HTTP firewall | Không bypass protected route |
| `/secure/../public/ping` | Client path normalization, proxy rewrite | Không “đi lách” matcher/authorization |
| `/secure;v=1/orders` | Matrix variables, semicolon policy | Không bất ngờ permitAll |
| `%2F`, `%5C`, `%25` trong path | Percent decoding/encoded separators | Không rò dữ liệu hay bỏ qua firewall |
| Lowercase/unknown HTTP method | Parser, firewall method allowlist | Không được thực thi unsafe operation trái policy |
| Header chứa control chars | HTTP client/server parser có thể từ chối | Không header injection/response splitting |
| Duplicate `Host`/`Content-Length` | HTTP parser/proxy protocol checks | Không request smuggling/desync |

Không tự xây test attack payload để vượt qua firewall trong môi trường thật không được phép. Với staging do bạn sở hữu, test các mẫu malformed có kiểm soát và không tắt firewall chỉ để status đồng nhất.

## 10. Lớp B: Spring Boot `RANDOM_PORT` sử dụng HTTP thật

### 10.1. Cùng ứng dụng và profile, nhưng mở server socket

```java
package com.example.transport;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

@SpringBootTest(
    classes = SideBySideDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
@ActiveProfiles("security-test")
class LiveTransportSecurityTest {

    @Autowired WebTestClient live;
    @Autowired OrderLedger ledger;

    @BeforeEach
    void setup() {
        ledger.resetForTests();
    }

    // Các tests mục 10–12 được viết trong class này.
}
```

Spring Boot test context ở đây **khởi chạy HTTP server trên một port ngẫu nhiên**. `@AutoConfigureWebTestClient` cung cấp client đã bind đến live server khi môi trường là `RANDOM_PORT`; không cần hard-code `localhost:8080`. Đối với Boot 4, thay import bằng:

```java
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
```

**Không gọi `.apply(springSecurity())` hay `.mutateWith(mockUser())` trên live network client để thay Basic credentials.** Những mutators dùng mock builder/exchange; qua TCP, server chỉ thấy HTTP bytes thật.

### 10.2. HTTP thật vẫn nhận cùng marker và Security headers

```java
@Test
void livePublicGetHasSameFilterAndHeaderContract() {
    live.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff")
        .expectBody(String.class).isEqualTo("pong");
}
```

So với mục 7.2, các **invariants** giống nhau: controller trả `pong`, global marker xuất hiện, Security thêm `nosniff`. Nhưng test live còn xác minh network adapter có thể nhận và trả request. Nó không chứng minh SSL/TLS nếu server đang dùng HTTP plaintext.

### 10.3. Anonymous live HTTP trả 401 như mock

```java
@Test
void liveAnonymousGetIsUnauthorized() {
    live.get().uri("/secure/whoami")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited");
}
```

Không có `mockUser` trong test. HTTP request thật không mang Authorization/cookie nên HTTP Basic authentication entry point trả 401. Nếu client bên ngoài đang lưu Basic/SESSION mặc định, test anonymous có thể trở thành authenticated và đánh mất negative control.

### 10.4. HTTP Basic header thật cho Alice/Bob

```java
@Test
void liveBasicAuthenticationIsBoundToRequestHeaders() {
    live.get().uri("/secure/whoami")
        .headers(h -> h.setBasicAuth(
            "alice", "test-password"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");

    live.get().uri("/secure/whoami")
        .headers(h -> h.setBasicAuth(
            "bob", "test-password"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("bob");

    live.get().uri("/secure/whoami")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Khác mock `mockUser()`, live request phải đi qua HTTP Basic decoding, `ReactiveAuthenticationManager`/user store và SecurityContext được tạo từ **credentials trong request**.

**Đây không phải phép thử an toàn khi dùng production credential.** Tài khoản `alice`/`bob` và password `test-password` chỉ có ở `security-test` profile trên local test server. Không ghi Basic header/credential vào logs/CI artifacts.

### 10.5. Password sai không được chấp nhận

```java
@Test
void liveInvalidBasicPasswordIsRejected() {
    live.get().uri("/secure/whoami")
        .headers(h -> h.setBasicAuth(
            "alice", "wrong-password"))
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Mock `mockUser("alice")` **không thể phát hiện** user store sai password encoder, user disabled hoặc provider selection khác. Vì thế cần ít nhất một negative credential test ở live layer, nhất là khi thay identity provider hoặc Spring Security version.

### 10.6. POST live thiếu CSRF vẫn phải chặn side effect

```java
@Test
void liveAuthenticatedPostWithoutCsrfIsForbidden() {
    live.post().uri("/secure/orders")
        .headers(h -> h.setBasicAuth(
            "alice", "test-password"))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new DemoController.CreateOrder("BAD-ORDER"))
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, ledger.count());
}
```

Đây là phép đối chiếu trực tiếp với test mock mục 7.5, nhưng **auth thật** khác mock. Một 403 có thể do CSRF hoặc authorization; để chứng minh nguyên nhân, bổ sung **positive control cùng credentials/session nhưng có CSRF token thật** ở mục 11.

## 11. CSRF thực: bootstrap token và WebSession cookie qua TCP

### 11.1. Luồng phải kiểm

```text
HTTP client
  |
  +-- GET /csrf
  |     (không Basic cũng được do permitAll)
  |     -> 200 JSON {headerName, token}
  |     -> Set-Cookie: SESSION=S1
  |
  +-- POST /secure/orders
        Authorization: Basic <fixture credentials>
        Cookie: SESSION=S1
        X-CSRF-TOKEN: <exposed token from same session>
        Content-Type: application/json
        -> Security validates expected token in WebSession S1
        -> 201 Created only when authenticated and CSRF valid
```

Với `WebSessionServerCsrfTokenRepository` mặc định của WebFlux, **expected CSRF token nằm trong WebSession**. Spring Security 6.x/7.x có thể expose **XOR-masked token** chống BREACH, nên lấy đúng `token()` trả từ `GET /csrf`; đừng tự sinh raw `UUID` hoặc assert token exposed của hai GET phải giống nhau.

### 11.2. Bootstrap trả cookie và token thật

```java
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

record BrowserCsrf(
    String sessionCookieName,
    String sessionCookieValue,
    String headerName,
    String token
) {}

BrowserCsrf bootstrapCsrf(WebTestClient client) {
    EntityExchangeResult<DemoController.CsrfPayload> result =
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueMatches(
                "Cache-Control", "(?i).*no-store.*")
            .expectBody(DemoController.CsrfPayload.class)
            .returnResult();

    DemoController.CsrfPayload body = result.getResponseBody();
    assertNotNull(body);

    ResponseCookie cookie =
        result.getResponseCookies().getFirst("SESSION");
    assertNotNull(cookie);
    assertNotNull(body.token());

    return new BrowserCsrf(
        cookie.getName(), cookie.getValue(),
        body.headerName(), body.token()
    );
}
```

Mã `BrowserCsrf` và `bootstrapCsrf` là **helpers đặt bên trong `LiveTransportSecurityTest`**. Default cookie name trong WebFlux session phổ biến là `SESSION`; Spring Session/custom `WebSessionIdResolver` có thể đổi tên, khi đó cập nhật helper theo runtime config. Nếu response không có session cookie, kiểm CSRF repository thực sự là WebSession, `Mono<CsrfToken>` đã được consume và session đã được commit chưa.

### 11.3. Positive POST: credential + cookie + CSRF thật

```java
@Test
void liveRealSessionAndCsrfTokenAllowPost() {
    BrowserCsrf csrf = bootstrapCsrf(live);

    live.post().uri("/secure/orders")
        .headers(h -> h.setBasicAuth(
            "alice", "test-password"))
        .cookie(
            csrf.sessionCookieName(),
            csrf.sessionCookieValue())
        .header(csrf.headerName(), csrf.token())
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new DemoController.CreateOrder("BOOK-REAL"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().valueEquals(
            "X-Demo-Filter", "visited")
        .expectBody(DemoController.OrderReceipt.class)
        .value(receipt -> {
            assertEquals("alice", receipt.owner());
            assertEquals("BOOK-REAL", receipt.sku());
        });

    assertEquals(1, ledger.count());
}
```

Lúc này test đã đi qua **real HTTP Basic**, `CsrfWebFilter`, `WebSessionServerCsrfTokenRepository`, cookie parsing và JSON codecs của server. Đây là chứng cứ mạnh hơn `.mutateWith(csrf())` cho flow cookie-backed browser, dù vẫn chưa áp dụng Chrome/Safari SameSite/third-party-cookie restrictions.

### 11.4. Negative control: cùng session nhưng thiếu CSRF token

```java
@Test
void liveCookieAndAuthAloneDoNotBypassCsrf() {
    BrowserCsrf csrf = bootstrapCsrf(live);

    live.post().uri("/secure/orders")
        .headers(h -> h.setBasicAuth(
            "alice", "test-password"))
        .cookie(
            csrf.sessionCookieName(),
            csrf.sessionCookieValue())
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new DemoController.CreateOrder("NO-TOKEN"))
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, ledger.count());
}
```

Request này chứng minh `SESSION` cookie và Basic credentials **chưa đủ** để POST nếu CSRF policy đang bật cho unsafe methods.

### 11.5. Negative control: token của session A với cookie session B

```java
@Test
void csrfFromAnotherWebSessionIsRejected() {
    BrowserCsrf a = bootstrapCsrf(live);
    BrowserCsrf b = bootstrapCsrf(live);
    assertNotEquals(a.sessionCookieValue(), b.sessionCookieValue());

    live.post().uri("/secure/orders")
        .headers(h -> h.setBasicAuth(
            "alice", "test-password"))
        .cookie(b.sessionCookieName(), b.sessionCookieValue())
        .header(a.headerName(), a.token())
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new DemoController.CreateOrder("CROSS-SESSION"))
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, ledger.count());
}
```

Test này giả định `WebSessionServerCsrfTokenRepository` và hai bootstrap requests **không mang cookie của nhau**. Nếu bạn đã cấu hình custom cookie jar tự động, hãy tạo hai client/jars độc lập. Nếu ứng dụng dùng `CookieServerCsrfTokenRepository`, expected token có semantics khác; **đừng gán invariant WebSession binding** cho cookie repo mà không kiểm triển khai thực.

### 11.6. Khi HTTP Basic và WebSession cùng xuất hiện

HTTP Basic trong fixture giúp xác minh password/provider trực tiếp; cookie `SESSION` chủ yếu phục vụ CSRF expected token. **Không suy** rằng Basic authentication đã được lưu dưới session và sẽ tồn tại nếu bỏ Authorization ở POST sau: behavior phụ thuộc `ServerSecurityContextRepository`/authentication chain. Với form login, login success/session fixation/saved request cần suite riêng và cookie authentication thật.

## 12. CORS preflight live qua HTTP và quan hệ với Security

### 12.1. OPTIONS không cookie/auth vẫn phải qua global CORS trước Security

```java
@Test
void liveAllowedPreflightNeedsNoCredentials() {
    live.options().uri("/secure/orders")
        .header("Origin", "https://spa.example.test")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://spa.example.test")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true")
        .expectHeader()
            .doesNotExist("X-Demo-Filter");

    assertEquals(0, ledger.count());
}
```

Đối chiếu với mục 8.1: cả mock và live đều chứng minh **CORS filter short-circuit** trước marker/Security ở cùng app config. Đây cũng là test filter ordering thực sự ở server, không còn chỉ chạy trên mock handler builder.

Khi frontend chủ động gắn `Authorization: Basic ...` hoặc `Authorization: Bearer ...`, browser có thể đưa `authorization` vào `Access-Control-Request-Headers`. Vì fixture đã allowlist header này, bổ sung test:

```java
@Test
void livePreflightAllowsAuthorizationHeaderForBrowserClient() {
    live.options().uri("/secure/orders")
        .header("Origin", "https://spa.example.test")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "authorization,content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueMatches(
            "Access-Control-Allow-Headers",
            "(?i).*authorization.*");
}
```

`Access-Control-Allow-Headers` chỉ cho phép browser **gửi tên header**; request actual vẫn phải vượt xác thực Basic/Bearer và CSRF nếu thuộc cookie-backed chain. OPTIONS preflight không được yêu cầu credential.

### 12.2. Origin không được phép không nhận ACAO

```java
@Test
void liveUntrustedOriginIsDeniedByCors() {
    live.options().uri("/secure/orders")
        .header("Origin", "https://attacker.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectStatus().isForbidden()
        .expectHeader()
            .doesNotExist("Access-Control-Allow-Origin");
}
```

Nếu **mock 403 nhưng live 200/ACAO cho attacker**, kiểm version/profile, CORS beans order, reverse proxy/CORS headers và duplicate CORS owners. Nếu live OPTIONS bị 401 mà mock pass, xác minh request thực có đủ `Origin`/`Access-Control-Request-Method` và một proxy có yêu cầu auth trên OPTIONS hay không.

### 12.3. Preflight thành công chưa chứng minh actual POST hợp lệ

```text
OPTIONS /secure/orders -> 200 + ACAO
POST /secure/orders    -> 403 nếu thiếu CSRF
POST /secure/orders    -> 401 nếu Basic credentials sai
POST /secure/orders    -> 201 khi credentials + session + token hợp lệ
```

`WebTestClient` không tự tạo OPTIONS khi bạn gọi `.post()` như browser Fetch. Vì vậy test cả OPTIONS và actual POST **riêng**. Browser E2E mới chứng minh browser tự preflight trước request JSON/custom header và áp dụng CORS/cookie policies.

## 13. Đối chiếu headers, `Location` redirect và HSTS

### 13.1. Dùng cùng endpoint có redirect cố định

`GET /public/redirect` trong fixture trả `303 See Other` với `Location: /public/ping`. Cả mock lẫn live nên chứng minh:

```java
// Trong MockTransportSecurityTest:
mock.get().uri("/public/redirect")
    .exchange()
    .expectStatus().isEqualTo(
        org.springframework.http.HttpStatus.SEE_OTHER)
    .expectHeader().valueEquals("Location", "/public/ping")
    .expectHeader().valueEquals(
        "X-Content-Type-Options", "nosniff");

// Trong LiveTransportSecurityTest:
live.get().uri("/public/redirect")
    .exchange()
    .expectStatus().isEqualTo(
        org.springframework.http.HttpStatus.SEE_OTHER)
    .expectHeader().valueEquals("Location", "/public/ping")
    .expectHeader().valueEquals(
        "X-Content-Type-Options", "nosniff");
```

Chỉ vì `WebTestClient` nhận một `303` không chứng minh browser **đã theo redirect**. Để kiểm đích:

```java
live.get().uri("/public/ping")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("pong");
```

Nên test **từng hop** trước khi dùng client/browser auto-follow; nếu chỉ assert status cuối 200, có thể bỏ qua `Location` bị đổi sang host lạ hoặc URL không an toàn.

### 13.2. Kết quả của header writer cần nhìn trên 401/403/303

Trong fixture, `DiagnosticWebFilter` chạy trước Spring Security và `SecurityWebFilterChain` có các header writers. Vì thế trên request đi tới Security có thể có:

```http
HTTP/1.1 401 Unauthorized
X-Demo-Filter: visited
X-Content-Type-Options: nosniff
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'
```

Headers có thể được sắp xếp/gộp khác nhau bởi HTTP adapter; dùng `expectHeader().value(...)` kiểm **semantics**, không snapshot nguyên response bytes. Đối với preflight bị `CorsWebFilter` short-circuit **trước Security**, không bắt buộc có Security headers như trên: đó là response do layer khác tạo.

### 13.3. HSTS phụ thuộc HTTPS chứ không phụ thuộc tên lớp test

`Strict-Transport-Security` (HSTS) được browser dùng sau khi nhận qua **HTTPS**. Với `RANDOM_PORT` HTTP plaintext mặc định, thiếu HSTS thường là **đúng**:

```java
@Test
void liveHttpDoesNotEmitHstsOnPlaintext() {
    live.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .doesNotExist("Strict-Transport-Security");
}
```

Trong mock application context có thể dùng mock URI `https://localhost` để kiểm **logic header writer** theo scheme:

```java
@Test
void mockSecureUriCanExerciseHstsWriterLogic() {
    WebTestClient fakeHttps = mock.mutate()
        .baseUrl("https://localhost")
        .build();

    fakeHttps.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .exists("Strict-Transport-Security");
}
```

**Không tự gọi fakeHttps là TLS test.** Mock chỉ thay scheme của request object. Muốn chứng minh TLS handshake/certificate/HSTS từ public hostname, phải dùng server được cấu hình SSL hoặc gọi HTTPS staging qua gateway.

### 13.4. HSTS và HTTPS redirect là hai cơ chế riêng

| Khía cạnh | Kiểm thử | Không nên suy |
| --- | --- | --- |
| HSTS trên HTTPS | `GET https://public.example.test/...` có STS | HTTP response cũng phải có STS |
| HTTP → HTTPS | `GET http://...` trả 3xx `Location: https://...` | Có redirect nghĩa browser đã nhớ HSTS |
| TLS termination | CDN/ingress trả HTTPS response | Backend HTTP tự biết scheme HTTPS nếu không trusted forwarded headers |
| CSP on HTML | HTML origin/owner có enforcing CSP | JSON API có CSP sẽ bảo vệ HTML ở CDN |
| `X-Frame-Options`/`frame-ancestors` | Kiểm trên HTML document | OPTIONS preflight phải có đủ headers này |

**Test mock và live HTTP localhost có thể cùng xanh mà public HTTPS vẫn sai** nếu ingress chưa giữ HSTS hoặc redirect Location chứa internal host.

### 13.5. Redirects từ auth khác controller redirect

Fixture dùng HTTP Basic nên anonymous `/secure/whoami` trả **401**, không phải `302 /login`. Nếu app bật `formLogin`, endpoint browser protected có thể redirect tới login page; một `Bearer`-only API thường cần 401 với `WWW-Authenticate`, không HTML login redirect. Khi nâng cấp/migration:

```text
Anonymous browser:
  GET /account/home -> 302 Location: /login  (nếu form login)

Anonymous API:
  GET /api/profile  -> 401                    (nếu Bearer-only)

Controller PRG:
  POST /orders      -> 303 Location: /orders/{id}

HTTP gateway:
  GET http://...     -> 301/308 Location: https://...
```

Mỗi loại có **response owner và contract khác nhau**. Test ở mock và live phải chọn đúng Security chain; không đặt một assertion 302 chung cho mọi route.

## 14. URL encoding và `StrictServerWebExchangeFirewall`

### 14.1. Có ba nơi URL có thể biến đổi

Một request đường dẫn `/secure/../public/ping` có thể được:

1. HTTP client normalize trước khi gửi.
2. Proxy/ingress rewrite, decode, canonicalize hoặc reject.
3. Reactor Netty parser/WebFlux request adaptation xử lý.
4. `StrictServerWebExchangeFirewall` reject/wrap trước Security chain matching.
5. `DispatcherHandler` match endpoint nếu còn được đi tiếp.

Để test chính xác firewall, phải biết **dạng URL mà firewall thực sự nhìn thấy**. Một WebTestClient URI builder có thể encode/normalize khác với raw `curl --path-as-is`. Không dùng status khác nhau làm lý do tắt firewall.

### 14.2. Reactive firewall có từ phiên bản hỗ trợ

Spring Security 6.4+ cung cấp:

```java
org.springframework.security.web.server.firewall.ServerWebExchangeFirewall
org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall
org.springframework.security.web.server.firewall.ServerExchangeRejectedException
```

`WebFilterChainProxy` áp dụng firewall mặc định cho request đi qua Security. Theo reference, firewall strict kiểm HTTP methods, path patterns và header/parameter characters để giảm bypass qua path normalization/encoding. Nó **không** phải một filter servlet `StrictHttpFirewall`, và những apps Security 6.0–6.3 có thể chưa có API Reactive firewall tương ứng.

**Đọc đúng đích của test:** nếu request bị loại ngay tại parser, không nhất thiết Spring tạo `ServerExchangeRejectedException`; nếu firewall reject, handler nghiệp vụ cũng không chạy. Kết luận theo **chuỗi bằng chứng**, không theo riêng status code.

### 14.3. Test kiểm thử path chuẩn trước, rồi mới bất thường

```java
@Test
void canonicalPathHasExpectedAuthorization() {
    live.get().uri("/secure/whoami")
        .exchange()
        .expectStatus().isUnauthorized();

    live.get().uri("/secure/whoami")
        .headers(h -> h.setBasicAuth(
            "alice", "test-password"))
        .exchange()
        .expectStatus().isOk();
}
```

Sau đó kiểm URL bất thường có kiểm soát. Không nhất thiết assert **mọi variant phải 400**: proxy có thể trả 404, client có thể canonicalize thành URL khác, hoặc gateway 400 trước app. Điều phải giữ: không có request “lách” từ protected namespace sang public/side-effect route và không để unauthorized user tạo order.

### 14.4. Sử dụng `curl --path-as-is` khi muốn giữ path

```bash
# Với server local đang chạy ở một cổng thực:
curl -i --path-as-is \
  'http://localhost:8080/secure/../public/ping'

curl -i --path-as-is \
  'http://localhost:8080/secure//whoami'
```

Lệnh dùng cổng 8080 **chỉ khi app đã chạy cổng đó**; với `RANDOM_PORT` hãy lấy cổng bằng `@LocalServerPort`/test output. `curl --path-as-is` tránh một số normalization ở curl, nhưng proxy/server vẫn có thể xử lý khác. Chạy chỉ trên server bạn sở hữu và giữ payload benign khi kiểm tra parser/firewall.

Trên Windows PowerShell 5.1, `curl` có thể là alias của `Invoke-WebRequest`; dùng `curl.exe` nếu muốn đúng flags của curl.

### 14.5. Test nội bộ và public URL phải xét cả prefix rewrite

```text
Public:  https://api.example.test/gateway/secure/whoami
Ingress: strip /gateway
Backend: http://service:8080/secure/whoami
Security matcher: /secure/**
```

Nếu ingress không strip như dự kiến, ứng dụng có thể nhận `/gateway/secure/whoami` và fallback chain/HandlerMapping khác. Một test mock ở `/secure/whoami` không thấy lỗi edge mapping. Tạo smoke test **public staging URL** và check 401/200/headers theo đúng path canonical trong Spring.

### 14.6. Không bỏ qua method-security defense in depth

Path-based WebFlux authorization không đủ để chống mọi IDOR/tenant leak. Khi dữ liệu nhạy cảm gắn owner/tenant, dùng service-level `@PreAuthorize`/domain policy và tests “Bob gọi resource ID của Alice phải bị từ chối”. Firewall giúp canonicalize/reject đường dẫn bất thường, **không** quyết định quyền truy cập object-level.

## 15. HTTP parser, codecs và kết nối: tại sao mock chưa đủ?

### 15.1. `MockServerHttpRequest` không phải gói tin TCP

Trong mock mode, `WebTestClient` đưa dữ liệu từ request spec vào mock HTTP exchange. Đó là **mô hình request/response của Framework**, không phải những bytes thực sự đi qua socket. Các vấn đề transport cần live test:

| Nhóm vấn đề | Mock có thể kiểm | Live HTTP cần kiểm thêm |
| --- | --- | --- |
| JSON request/response | Jackson codec với test context | Headers `Content-Type/Length`, framing, HTTP charset qua adapter |
| Body size | Một số giới hạn codec `maxInMemorySize` | Giới hạn Netty, gateway/WAF, 413 vs codec 500 |
| Timeout | Reactor operator timeout, mock timeout config | Client connect/read timeout, slow server, connection reset |
| Response streaming | `Flux<DataBuffer>`/`Flux<T>` API | Flush/chunking/backpressure/connection lifecycle |
| Duplicate/malformed headers | Có thể tạo mock header map | Real HTTP parser có thể từ chối sớm |
| Redirect | `status + Location` ở Spring handler | Host/scheme/port/URI encoder và proxy rewrites |
| HTTPS | Giả lập request scheme | TLS handshake/certificate/SNI/HSTS theo hostname |
| HTTP/2 | Không chứng minh framing | Client/server negotiation, multiplexing, downgrade |

Không phải mọi API `WebFilter` bị ảnh hưởng; phần lớn business-level response có thể giống nhau. Nhưng chỉ test mock là thiếu chứng cứ cho request smuggling boundaries, header splitting, TLS hoặc reverse proxy behavior.

### 15.2. Content negotiation và body serialization

Một GET mock trả 200 với body Java object **không chứng minh** API gửi JSON đúng `Content-Type`/encoding đến client thật nếu test sử dụng decoder khác. Với live WebTestClient:

```java
@Test
void realHttpResponseUsesExpectedJsonContract() {
    BrowserCsrf csrf = bootstrapCsrf(live);

    live.post().uri("/secure/orders")
        .headers(h -> h.setBasicAuth(
            "alice", "test-password"))
        .cookie(
            csrf.sessionCookieName(),
            csrf.sessionCookieValue())
        .header(csrf.headerName(), csrf.token())
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new DemoController.CreateOrder("JSON-01"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(DemoController.OrderReceipt.class)
        .value(body -> assertEquals("JSON-01", body.sku()));
}
```

Tuy nhiên một live test đi thẳng tới localhost vẫn không tự kiểm gateway body-size rules hoặc CDN response transformations.

### 15.3. Streaming/chunked transfer cần route riêng

`WebFlux` có thể trả `Flux<T>` streaming hoặc Server-Sent Events. Trong mock, mọi `DataBuffer`/publisher có thể được test mà không có network; ở HTTP thật có thêm:

- Chunk flushing, client buffering và gateway `proxy_buffering`.
- Client disconnect và cancellation/`doFinally` handling.
- Response headers sau khi body đã bắt đầu commit.
- Connection pooling và idle timeout của Reactor Netty.
- Backpressure khi client đọc chậm.

Nên có một **streaming-specific test fixture** và live test đo chunk arrivals/cleanup. Không suy “Flux đã phát 3 phần tử trong StepVerifier” nghĩa browser đã nhận 3 chunks ngay theo đúng thời gian.

### 15.4. Các trường hợp 400/413/500 không nhất thiết cùng nguồn

`413 Payload Too Large` có thể do ingress giới hạn request trước WebFlux, hoặc custom handler trong app; `400 Bad Request` có thể do JSON parse/HTTP parser/firewall; `500` có thể do reactive pipeline exception sau khi filter đã chạy.

**Chẩn đoán:** xem response owner, có marker từ `DiagnosticWebFilter` không, loại error (HTTP status, exception class), rồi so mock/live. Tránh ép tất cả malformed request tests vào một status cố định không đúng với tầng xử lý.

## 16. Dùng `bindToServer()` tường minh khi cần điều khiển HTTP client

`@AutoConfigureWebTestClient` với `RANDOM_PORT` thuận tiện, nhưng bạn cũng có thể tự tạo client trỏ tới port đã chạy:

```java
import java.time.Duration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@LocalServerPort
int port;

WebTestClient rawHttpClient() {
    return WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .responseTimeout(Duration.ofSeconds(5))
        .build();
}
```

Đoạn code là **fragment trong một `@SpringBootTest(RANDOM_PORT)` class**. Không gán nó vào mock test class không có port. `@LocalServerPort` package trên phù hợp Boot 3.x; ở Boot 4 hãy đối chiếu API package theo BOM.

### 16.1. Vì sao không dùng cổng `8080` cố định?

- Một CI worker khác có thể đã dùng cổng đó.
- Build jobs song song có thể đụng cổng.
- Container/reverse proxy hoặc developer machine có cấu hình khác.
- Test có thể vô tình gọi một **server khác** đang chạy trên 8080 và cho kết quả sai.

`RANDOM_PORT` loại tranh chấp cổng phổ biến, nhưng **không tự cô lập** database/Redis; nhiều test servers vẫn có thể trỏ tới cùng store.

### 16.2. Test client customization không sửa server Security

`WebTestClient.bindToServer().filter(ExchangeFilterFunction)` hoặc `defaultHeader` thay **HTTP client request**, không thay Spring `WebFilter` của server. Ví dụ:

```java
WebTestClient aliceOnly = rawHttpClient().mutate()
    .defaultHeaders(h -> h.setBasicAuth(
        "alice", "test-password"))
    .build();
```

Client trên luôn thêm Basic header. Nếu lưu nó vào biến `live` dùng cho anonymous tests, negative control có thể fail do request không còn anonymous. **Giữ client baseline không credentials**, tạo local client riêng theo scenario.

### 16.3. Không dùng `mockUser()`/`csrf()` từ mock builder qua TCP

Sai về mặt ý nghĩa kiểm thử:

```java
// Không chứng minh real authentication/CSRF qua HTTP:
// rawHttpClient().mutateWith(mockUser("alice")).mutateWith(csrf())
```

Đúng trong live test:

```text
Authorization: Basic/Bearer thật
Cookie: SESSION=<id thật từ response GET>
X-CSRF-TOKEN: <giá trị exposed thật>
```

Nếu cần bypass authentication cho một **test-only integration fixture**, hãy giải thích rõ fixture đó kiểm logic nào, không báo rằng authentication password/JWT decoder đã được kiểm khi thực tế không.

### 16.4. Test timeout có giới hạn rõ

`responseTimeout(Duration.ofSeconds(5))` giới hạn thời gian chờ của test client; không đồng nghĩa server configured request timeout là 5 giây. Nếu test timeout:

- Có negative case để xác định request bị chặn ở client hay server.
- Không dùng thời gian quá chặt trên CI máy yếu nếu chỉ kiểm business behavior.
- Không dùng `Thread.sleep` dài để làm race/async state ổn định.
- Với Reactor timers unit tests, có thể dùng `StepVerifier.withVirtualTime`; với socket real cần kiểm network thời gian thật.

## 17. Một bộ “contract” dùng lại cho mock và live

Để thật sự **đối chiếu** thay vì copy hai bộ assertions rồi vô tình để chúng khác nhau, có thể gom những invariants chung thành helper:

```java
package com.example.transport;

import org.springframework.test.web.reactive.server.WebTestClient;

public final class SharedHttpContracts {
    private SharedHttpContracts() {}

    public static void assertPublicPing(
            WebTestClient client) {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Demo-Filter", "visited")
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectBody(String.class).isEqualTo("pong");
    }

    public static void assertAnonymousDenied(
            WebTestClient client) {
        client.get().uri("/secure/whoami")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Sử dụng:

```java
// Trong MockTransportSecurityTest:
@Test void sharedContractViaMock() {
    SharedHttpContracts.assertPublicPing(mock);
    SharedHttpContracts.assertAnonymousDenied(mock);
}

// Trong LiveTransportSecurityTest:
@Test void sharedContractViaHttp() {
    SharedHttpContracts.assertPublicPing(live);
    SharedHttpContracts.assertAnonymousDenied(live);
}
```

**Lợi ích:** Nếu ai đổi contract của `/public/ping` từ 200 thành redirect, cả hai test modes phản ánh cùng một expectation. Các khác biệt hợp lệ phải nằm ở helpers riêng (mockUser vs Basic, mock csrf vs real token, HSTS/HTTP vs HTTPS).

### 17.1. Không so token/cookie raw value giữa hai runs

Những giá trị không nên snapshot/equal:

- `SESSION` ID và CSRF token (random; XOR-masked values có thể đổi qua GET).
- `Date`, `Server`, `Connection`, `Transfer-Encoding`.
- Ephemeral port, generated correlation IDs/traces.
- Default error response body từ Netty vs mock hoặc edge (nếu không phải application contract).

Nên assert **tồn tại, scope, flags, semantics** và khả năng dùng token/session đúng chỗ, không assert string phải giống byte-for-byte.

### 17.2. Đừng đồng nhất “cùng status” với “cùng security”

`403` trên mock do CSRF; `403` trên live có thể do gateway CORS, authorization hoặc server CSRF. Vì vậy một security-sensitive test nên kiểm:

- request được gửi với/không có credential dự kiến,
- cookie/header token thực sự hiện diện như thiết kế,
- filter/service có được gọi hay không,
- response CORS/WWW-Authenticate/Location headers,
- **không có side effects** khi bị từ chối,
- cùng request có positive control hợp lệ pass.

Không log raw tokens/passwords để lấy bằng chứng; dùng test correlation IDs hoặc counters không nhạy cảm.

## 18. Các lớp filter và cách xác định “request bị chặn ở đâu”

### 18.1. Global WebFilters khác internal Security WebFilters

Trong WebFlux có ít nhất hai cơ chế thứ tự:

1. **Global `WebFilter` beans** theo `Ordered`/`@Order`, thuộc `HttpHandler/WebHandler` pipeline.
2. **Security filters bên trong `SecurityWebFilterChain`** được `ServerHttpSecurity` đặt theo `SecurityWebFiltersOrder` và một `WebFilterChainProxy` đại diện trong global chain.

```text
WebFlux global WebFilter order
  |
  +-- CorsWebFilter [HIGHEST_PRECEDENCE]
  |      +-- preflight -> short-circuit
  |
  +-- DiagnosticWebFilter [HIGHEST_PRECEDENCE + 10]
  |      +-- X-Demo-Filter = visited
  |
  +-- Spring Security WebFilterChainProxy
         +-- ServerWebExchangeFirewall
         +-- securityMatcher -> selected SecurityWebFilterChain
                +-- CSRF
                +-- Authentication
                +-- Authorization
                +-- Security headers
  |
  +-- DispatcherHandler -> route/controller
```

**`@Order` trên `SecurityWebFilterChain` không phải cách xếp một global `CorsWebFilter`.** Còn `SecurityWebFiltersOrder` chỉ có nghĩa bên trong Security pipeline, không trực tiếp sắp xếp bean `DiagnosticWebFilter` toàn cục.

### 18.2. Khi có nhiều SecurityWebFilterChain

```java
@Bean
@org.springframework.core.annotation.Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http.securityMatcher(
            org.springframework.security.web.server.util.matcher
                .ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(org.springframework.security.config
                .Customizer.withDefaults()))
        .csrf(csrf -> csrf.disable()) // Chỉ API thật sự Bearer-only.
        .build();
}
```

**Code trên là fragment của cấu hình thay thế**, không đăng ký cùng `DemoSecurityConfig` hiện tại. API JWT cần Resource Server dependencies và `ReactiveJwtDecoder`. Không miễn CSRF cho browser cookie chain chỉ vì một API Bearer-only đang tồn tại.

Khi mock và live trả response khác nhau, hãy xác định:

- Request có đi qua global CORS/diagnostic filters?
- Security proxy đã chọn chain nào theo path sau decode/rewrite?
- CSRF/authorization thuộc chain đó ra sao?
- Request bị từ chối trước hay sau controller?
- Response được tạo tại app hay gateway?

Một test `/api/**` 401 và một test `/account/**` 302 có thể đều đúng nếu hai chains có contract khác nhau. Điều quan trọng là **cùng URL/method/auth inputs** trên cùng config phải giữ nguyên policy.

### 18.3. Có marker nhưng status 403 không đủ xác định layer

Nếu `X-Demo-Filter: visited` xuất hiện, ta biết diagnostic filter đã chạy, nhưng 403 vẫn có thể do:

- CORS filter khác đứng sau marker (trong cấu hình khác),
- CSRF invalid/missing,
- authorization thiếu role/scope,
- custom `ServerAccessDeniedHandler`,
- controller tự trả 403,
- upstream response rewrite mà marker vẫn được giữ.

Muốn kết luận, cần **positive/negative controls** với một yếu tố thay đổi mỗi lần, hoặc diagnostics có correlation ID và counter theo layer. Không log full `Authentication`, password, JWT, session cookie và CSRF token.

### 18.4. Không có marker cũng chưa chứng minh controller/filters không chạy

Các trường hợp không có marker:

- Preflight được `CorsWebFilter` sớm hơn xử lý (đúng design).
- HTTP parser hoặc gateway reject (app không thấy request).
- Profile `security-test` không active nên DiagnosticWebFilter không tồn tại.
- Request được route tới server khác.
- Error handler/CDN strip header.

Vì thế một phép thử chẩn đoán nên ghi thêm **request id không nhạy cảm**, URL canonical, status/Location/allow-origin và server/app instance id. Marker là chỉ dấu có giới hạn, không phải nguồn sự thật duy nhất.

## 19. Triển khai thực: proxy, cookie, HTTPS và session store

### 19.1. Lớp thứ ba phải có public staging HTTPS tests

Một local `RANDOM_PORT` server thường chạy HTTP; production có thể:

```text
Browser https://app.example.com
  |
  | Fetch https://api.example.com/orders
  v
CDN/WAF TLS termination
  |
  +-- OPTIONS preflight may be answered here
  +-- CSP/HSTS/Cache-Control may be changed here
  +-- X-Forwarded-Proto / Host / prefix rewrite
  v
Ingress / load balancer
  |
  v
Reactive app pods + Redis session store
```

Muốn so mock/live có ý nghĩa, bổ sung **public URL smoke tests** cho đường đi thực:

- OPTIONS có `Origin`/`Access-Control-Request-Method` đúng.
- Actual POST có cookie/session/token, không bypass CSRF.
- HTML response owner có CSP, HSTS/HTTPS hostname đúng.
- Redirect không lặp hoặc rò internal host/port.
- HTTP parser/WAF không thay URL thành path lọt sai security matcher.
- Cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` được browser chấp nhận.

### 19.2. Forwarded headers phải có trust boundary

Khi TLS kết thúc ở reverse proxy, app có thể chỉ thấy kết nối HTTP nội bộ:

```text
Public: https://api.example.com/secure/whoami
Backend: http://service:8080/secure/whoami
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
```

Spring Boot cung cấp `server.forward-headers-strategy` theo version, nhưng cấu hình chính xác phụ thuộc topology và mức độ tin cậy proxy. **Không tin `Forwarded`/`X-Forwarded-*` do người dùng Internet tự gửi**; nếu sai, attacker có thể ảnh hưởng absolute redirects, secure cookie detection hoặc generated URLs.

Kiểm trên public HTTPS:

```http
HTTP/1.1 302 Found
Location: https://api.example.com/login
```

Đích không được vô tình trở thành `http://service:8080/login` hoặc redirect quay vòng vì backend nghĩ request vẫn là HTTP.

### 19.3. Browser cookie khác WebTestClient thủ công

WebTestClient cho phép bạn ghi:

```java
.cookie("SESSION", sessionId)
```

ngay cả khi browser thật **sẽ không gửi cookie đó** vì `Secure/SameSite/Domain/Path` hoặc third-party cookie restrictions. Một live HTTP test có thể xanh với cookie thủ công trong khi SPA thất bại.

Browser E2E cần tách **ít nhất hai browser contexts** với cookie jars riêng để thử Alice/Bob và xác minh cross-site restrictions. `Access-Control-Allow-Credentials: true` không bắt browser gửi cookie nếu frontend không đặt `credentials: "include"` hoặc browser policy cấm.

### 19.4. Multi-replica WebSession store không được giả định là shared

`GET /csrf` có thể tới pod A, trong khi `POST /secure/orders` tới pod B. Nếu `WebSessionServerCsrfTokenRepository` và authentication dựa vào **in-memory WebSession store riêng từng pod**, B có thể không tìm thấy session/token của A và trả 403.

```text
GET /csrf -> Pod A -> SESSION=S1, expected token T1 in A memory
POST /orders -> Pod B -> SESSION=S1 not found
                        -> CSRF validation fails
```

Giải pháp có thể là Spring Session/Redis shared store hoặc sticky sessions phù hợp topology; sticky sessions không thay thế xử lý failover. Cần staging tests bắt chéo replicas, rolling deployment và serialization compatibility, không chỉ chạy local `RANDOM_PORT` một instance.

### 19.5. CSP/HSTS/CORS owners khác nhau

| Response | Owner phổ biến | Cần test ở đâu? |
| --- | --- | --- |
| `GET /index.html` SPA | CDN/Nginx | Public HTML HTTPS origin, CSP/Cache-Control |
| `OPTIONS /api/**` | CDN/ingress hoặc CorsWebFilter | Public URL/browser preflight |
| `GET /secure/whoami` | WebFlux app | Mock + live app + public route |
| HTTP → HTTPS redirect | CDN/ingress hoặc Spring Security | Không follow ban đầu, kiểm từng `Location` |
| `GET /csrf` | WebFlux app | Cookie/token/no-store + session round-trip |
| Firewall rejection | WAF/parser/Security firewall | Xác định layer; kiểm không bypass |

Không bắt CSP/HSTS của JSON API “bảo vệ hộ” `index.html` từ CDN. Không đòi Spring Security thêm security headers lên response do ingress tạo trước khi request vào app.

## 20. Runbook chẩn đoán sai lệch mock/live

### Lỗi A — Mock GET anonymous 401 nhưng live GET 200

Kiểm tra live client có `defaultHeaders(Authorization)`/cookie jar từ test khác hay không, profile có `permitAll` khác, đúng cổng/app instance không, và Security chain matcher có bị proxy rewrite không. Gửi một live GET hoàn toàn không credentials và một GET Basic đúng để có negative/positive controls.

### Lỗi B — Mock `mockUser("alice")` trả 200 nhưng live Basic Alice trả 401

`mockUser` không kiểm password provider. Kiểm user store/password encoder, Basic header/credentials, Spring Security chain selected, password state, và authentication entry point. Không thêm `permitAll()` để chữa.

### Lỗi C — Mock `csrf()` POST 201 nhưng live POST 403

Live client có thể thiếu `SESSION` cookie hoặc actual exposed token, CSRF request handler raw/XOR mismatch, token stale sau login/logout, session store khác pod hoặc selected chain khác. Thử `GET /csrf`, gửi cùng cookie/header, giữ Basic credential, rồi so missing/invalid/valid token.

### Lỗi D — Live POST với session cookie và token vẫn 403

Kiểm `CsrfPayload.headerName` có gửi đúng, cookie `SESSION` có được gửi lại, XOR handler có nhận masked token, HTTP body/method đúng, authentication/authorization pass. Thêm positive GET protected route bằng cùng credentials để tách authentication khỏi CSRF.

### Lỗi E — Mock CORS OPTIONS 200, live OPTIONS 401

Kiểm real request có đủ `Origin` và `Access-Control-Request-Method`; global `CorsWebFilter` có chạy trước Security không, proxy có yêu cầu auth với OPTIONS hay route tới app khác không. Không sửa bằng cách tắt authentication của actual POST.

### Lỗi F — OPTIONS live 200 nhưng browser vẫn báo CORS

Response có thể không có ACAO, allowed method/header không phù hợp, `Access-Control-Allow-Credentials` sai, hoặc CDN phát hai ACAO headers. Test **header semantics**, không chỉ status. Browser còn có CSP `connect-src`, third-party cookies và redirects riêng.

### Lỗi G — Live CORS attacker Origin được chấp nhận nhưng mock từ chối

Kiểm double CORS processing ở edge/app, wildcard origin patterns, response rewrite của ingress, per-env allowlist và cache `Vary`. Không xem CORS là authentication; nhưng credentialed ACAO cho origin lạ là security regression.

### Lỗi H — Live redirect có host/port nội bộ

Kiểm trusted forwarded headers/proxy URL reconstruction, absolute redirect strategy, `Host` validation và baseUrl của test. Assert `Location` scheme/host/port/path theo public contract, không chỉ 3xx.

### Lỗi I — Mock HTTPS có HSTS, HTTP live localhost không có

Đây có thể là kết quả **đúng**: HSTS chỉ ghi trên HTTPS. Gọi public HTTPS hostname/certificate hợp lệ để kiểm HSTS thật; đừng ép HTTP plaintext phát STS.

### Lỗi J — Browser HTTPS redirect vòng lặp

Ingress TLS termination làm backend nhìn request là HTTP, Spring `redirectToHttps` và ingress cùng redirect hoặc forwarded strategy không đúng. Theo dõi từng hop không follow trước, xác định owner và trusted proxy scheme.

### Lỗi K — Mock URL `/secure//whoami` 400 nhưng live 404

HTTP client/server/parser/gateway có thể normalize/reject ở các tầng khác nhau. Kiểm URI raw trên wire (bằng `curl --path-as-is` với app test-owned), route matching và firewall logs không nhạy cảm. Bất biến là không bypass authorization và không gây side effect.

### Lỗi L — Status 400 live không có `X-Demo-Filter`

Có thể parser/gateway reject trước WebFlux, hoặc preflight CORS sớm short-circuit, hoặc test profile không active. Xem method/Origin/ACRM, server instance và marker behavior trên GET canonical; không tự suy 400 đều do firewall.

### Lỗi M — Body JSON khác nhau dù status đều 200/201

Kiểm codecs/`Content-Type`/Accept, Jackson configuration, mock vs full context/slice, API version media type, filters sửa body, timestamp serialization và gateway transformations. Đừng so object memory identity; kiểm JSON contract/fields.

### Lỗi N — POST tạo hai đơn khi network retry

Mock test có thể chỉ subscribe một lần, HTTP client/proxy có retry hoặc người dùng double-click POST. CSRF chỉ xác nhận tính hợp lệ request, **không bảo đảm idempotency**. Với nghiệp vụ quan trọng, dùng idempotency key/unique business constraints và test retries.

### Lỗi O — `@WebFluxTest` xanh, `RANDOM_PORT` lại dùng Security chain khác

Slice có thể không import `SecurityWebFilterChain`/CorsWebFilter/CSRF repository custom. Dùng `@SpringBootTest(MOCK)` hoặc context test nạp full wiring để so với live; không chỉ bind controller rồi coi như có filter thật.

### Lỗi P — `@SpringBootTest(MOCK)` xanh nhưng Netty body upload fail

Kiểm HTTP framing, max body size, content type, decoder, chunking, gateway 413, client timeout. Viết live streaming/upload tests, không kỳ vọng mock transport giải quyết giới hạn socket.

### Lỗi Q — Live test chỉ fail khi chạy cả suite

OrderLedger singleton hoặc Redis/WebSession/DB shared, client default headers/cookies, TestContext cache hoặc test song song gây data contamination. Dùng `@BeforeEach`/per-test namespace và không chia sẻ mutable client/cookie jar; đợi toàn bộ reactive publisher hoàn thành trước teardown.

### Lỗi R — JWT mock pass nhưng signed JWT bị 401

`mockJwt()` tạo SecurityContext/JwtAuthenticationToken giả, không test chữ ký, issuer/audience/expiry, JWKS/network. Live API tests phải gửi token signed bởi test issuer và kiểm decoder thật, không dùng mock như chứng cứ crypto verification.

### Lỗi S — CSRF test pass trực tiếp localhost nhưng fail qua CDN

CDN có thể cache `GET /csrf` trái `no-store`, strip `Set-Cookie`/CSRF header, rewrite cookie Path/Domain/SameSite hoặc requests tới nhiều pods không shared session. Test public HTTPS và multi-replica topology.

### Lỗi T — Security headers mất trên response do gateway tạo

Spring header writers không thể sửa response edge tạo trước khi tới app (ví dụ HTTP → HTTPS redirect hoặc WAF reject). Xác định response owner; đặt HSTS/CSP/nosniff/cache policy thích hợp ở edge/HTML server nếu cần.

### Lỗi U — Không thấy authentication của request trong async service

Reactive SecurityContext đi theo **Reactor Context/subscription**, không phải ThreadLocal Servlet. Nếu code fire-and-forget `subscribe()`, chuyển sang Thread tự tạo hoặc dùng static principal, có thể mất/rò context. Viết `StepVerifier`/`ReactiveSecurityContextHolder` unit tests và await composed publishers.

### Lỗi V — “HTTP thật” nhưng thử nhầm server

Test bind cổng 8080 cố định có thể gọi app từ phiên chạy trước, hoặc public DNS trỏ vào staging cluster khác. Dùng `RANDOM_PORT`/`@LocalServerPort` hoặc kiểm health/version marker không nhạy cảm. Đừng dùng kết quả 200 của một server không xác định để đánh dấu Security suite PASS.

## 21. Ma trận hồi quy: mock, HTTP local, HTTPS/browser

Bảng sau không bắt mọi test chạy ba lần. Nó chỉ ra **cấp tối thiểu** để chứng minh từng claim. Ký hiệu **M** = mock context, **H** = HTTP thật local/test server, **B** = browser/public HTTPS staging.

| ID | Kịch bản | M | H | B | Bất biến |
| --- | --- | --- | --- | --- | --- |
| P01 | GET `/public/ping` | ✓ | ✓ | Tùy | 200, body đúng |
| P02 | Global diagnostic filter marker | ✓ | ✓ | Tùy | Header marker trên actual request |
| P03 | Security `nosniff` on public GET | ✓ | ✓ | ✓ nếu HTML owner | Header policy đúng |
| P04 | CSP explicit | ✓ | ✓ | ✓ | Trên HTML document owner |
| P05 | Anonymous `/secure/whoami` | ✓ | ✓ | Tùy | 401 Basic chain |
| P06 | Mock Alice `mockUser()` | ✓ | — | — | Authorization logic |
| P07 | HTTP Basic Alice password đúng | — | ✓ | Tùy | 200, user Alice |
| P08 | HTTP Basic password sai | — | ✓ | Tùy | 401, không có user |
| P09 | HTTP Basic Bob | — | ✓ | Tùy | Principal Bob, không Alice |
| P10 | POST mock thiếu `csrf()` | ✓ | — | — | 403, side effect 0 |
| P11 | POST mock có `csrf()` | ✓ | — | — | 201, side effect 1 |
| P12 | POST live có Basic, thiếu CSRF | — | ✓ | ✓ nếu browser session | 403, side effect 0 |
| P13 | GET `/csrf` tạo token + session | ✓ nếu test thực | ✓ | ✓ | Exposed token + cookie/no-store |
| P14 | POST live cookie/token đúng | — | ✓ | ✓ | 201, đúng owner |
| P15 | POST live cookie, thiếu token | — | ✓ | ✓ | 403 |
| P16 | POST live session B/token A | — | ✓ | Tùy | 403 với WebSession repo |
| P17 | OPTIONS preflight allowlisted | ✓ | ✓ | ✓ | 2xx + ACAO/method/headers |
| P18 | OPTIONS không cookie/auth | ✓ | ✓ | ✓ | Không cần authenticated user |
| P19 | OPTIONS origin lạ | ✓ | ✓ | ✓ | Deny hoặc không ACAO theo policy |
| P20 | Bare OPTIONS không Origin/ACRM | ✓ | ✓ | Tùy | Không nhầm là preflight |
| P21 | Actual CORS GET không Basic | ✓ | ✓ | ✓ | CORS không bypass 401 |
| P22 | `Vary` Origin/ACRM/ACRH | ✓ | ✓ | ✓ qua CDN | Cache không lẫn origins |
| P23 | Controller redirect 303 | ✓ | ✓ | ✓ | Location safe |
| P24 | Redirect target GET | ✓ | ✓ | ✓ | Không sai host/loop |
| P25 | HTTP live thiếu HSTS | — | ✓ | — | HSTS chỉ trên HTTPS |
| P26 | Mock secure URI HSTS writer | ✓ | — | — | Header writer logic |
| P27 | Public HTTPS HSTS/certificate | — | — | ✓ | Browser nhận policy đáng tin |
| P28 | Public HTTP → HTTPS redirect | — | Tùy nếu app xử lý | ✓ | Location canonical/host |
| P29 | App proxy prefix rewrite | — | Tùy | ✓ | Chọn đúng chain/route |
| P30 | URL double slash/semicolon | ✓ nếu mock cho phép | ✓ | ✓ qua ingress | Không bypass auth |
| P31 | Encoded slash/backslash | ✓ nếu mock cho phép | ✓ | ✓ qua ingress | Không path matcher bypass |
| P32 | Invalid header control chars | Không đủ | ✓ | ✓ qua proxy | Parser/firewall không bị lách |
| P33 | Body JSON media type | ✓ | ✓ | Tùy | Contract JSON đúng |
| P34 | Large body/max size | ✓ codec | ✓ | ✓ qua ingress | Không chấp nhận payload trái limit |
| P35 | Streaming flush/disconnect | Một phần | ✓ | ✓ nếu browser | Cancellation/cleanup đúng |
| P36 | JWT mock principal/scopes | ✓ | — | — | Authorization đúng |
| P37 | Signed JWT expiry/signature | — | ✓ | Tùy | Decoder thật từ chối token sai |
| P38 | Session cookie SameSite/Secure | Một phần | Một phần | ✓ | Browser cookie policy đúng |
| P39 | Cross-pod session/CSRF | — | ✓ với multi-pod | ✓ | Token session không thất lạc |
| P40 | 401/403/no side effect trên retry | ✓ | ✓ | ✓ nếu cần | Không tạo đơn trái policy |
| P41 | Static shared test data isolation | ✓ | ✓ | Tùy | Test order không đổi kết quả |
| P42 | API vs browser multi-chain | ✓ | ✓ | ✓ nếu SPA | 401 API, 302 browser theo config |
| P43 | CDN/WAF tạo response trước app | — | — | ✓ | Header owner đúng |
| P44 | OAuth2 login/session/logout thật | Mock UI flow hạn chế | ✓ qua test IdP | ✓ | Cookie, state/nonce/CSRF đúng |

### 21.1. Các regression “red flags” nên chặn release

- Browser POST thiếu CSRF vẫn chạy nghiệp vụ ở cookie-authenticated route.
- Request anonymous thực được truy cập protected resource dù mock 401.
- API Bearer-only bị chuyển sang form-login fallback hoặc ngược lại một cách ngoài thiết kế.
- Credentialed CORS cấp ACAO cho origin không tin cậy.
- Redirect Location lấy từ URL không kiểm soát, chứa attacker host/internal host hoặc HTTPS downgrade.
- URL encoded/normalized bất thường bypass Security matcher hay object-level authorization.
- Public HTML mất CSP/HSTS policy theo threat model; browser nhận cookie không đúng security flags.
- Test live pass khi gọi nhầm app/port hoặc mock helper bị dùng như chứng cứ ký JWT/CSRF token thực.

### 21.2. Chọn test layer theo câu hỏi, không theo mức “mạnh nhất”

Không nhất thiết chạy toàn browser cho từng testcase: unit/mocked tests nhanh và cho thông báo lỗi rõ, dùng **một ít live HTTP tests chọn lọc** để chứng minh những assumptions của mock. Còn TLS/CDN/browser policy nằm ngoài localhost thì cần staging tests riêng. Cấu trúc phù hợp cho CI:

```text
Stage 1: unit + WebTestClient mock (nhanh)
Stage 2: @SpringBootTest(RANDOM_PORT) (HTTP/security/CSRF)
Stage 3: Testcontainers Redis/R2DBC/JWT issuer integration
Stage 4: HTTPS staging/browser/ingress smoke checks
```

Nếu Stage 2 khác Stage 1, đừng sửa expected một cách mù quáng: kiểm request inputs, profile, filter order và response owner. Nếu Stage 4 khác Stage 2, tập trung topology/cookie/CORS/CSP/redirect/TLS trước.

## 22. Bài tập thực hành đối chiếu mock và HTTP thực

### Bài 1 — Xác nhận đang dùng WebFlux

Tạo ứng dụng chỉ có `spring-boot-starter-webflux` và `spring-boot-starter-security`. Log application type một cách an toàn (không in secrets), dùng `ServerHttpSecurity`/`SecurityWebFilterChain`. Thêm `spring-boot-starter-web` vào **nhánh thí nghiệm** để quan sát thay đổi web application type nếu Boot chọn Servlet theo classpath. Giải thích vì sao test `MockMvc` không chứng minh WebFlux `WebFilter` đã chạy.

### Bài 2 — Một marker filter trong hai test modes

Dùng `DiagnosticWebFilter` từ mục 6.3. Viết một test `bindToApplicationContext` và một test `RANDOM_PORT` cùng GET `/public/ping`, assert status 200, body `pong`, `X-Demo-Filter: visited` và `nosniff`. Vì sao chỉ một lần assert marker trên mock chưa đủ để chứng minh filter được gắn vào HTTP server thật?

### Bài 3 — Authentication mock so với HTTP Basic thật

Mock: `mutateWith(mockUser("alice"))` GET `/secure/whoami` trả Alice; baseline anonymous 401. Live: HTTP Basic Alice/password đúng trả Alice, password sai trả 401, Bob/password đúng trả Bob. Ghi rõ case nào kiểm authorization, case nào kiểm authentication provider/credentials.

### Bài 4 — POST không CSRF không được có side effect

Mock: Alice `mockUser` POST không `csrf()` nhận 403 và ledger 0; thêm `csrf()` nhận 201. Live: POST Basic đúng nhưng không CSRF vẫn 403/ledger 0. Giải thích vì sao test mock positive chưa kiểm token repository.

### Bài 5 — WebSession token round-trip thật

Gọi GET `/csrf` qua `RANDOM_PORT`, lấy `SESSION` cookie và `CsrfPayload`, POST `/secure/orders` với Basic+cookie+header actual. Thử bỏ cookie, bỏ header và token của session khác; assert negative cases không tăng ledger. Đừng dùng `csrf()` helper trong suite này.

### Bài 6 — XOR/BREACH và token exposed

Thực hiện hai GET `/csrf` cùng một `SESSION` cookie, so exposed token qua version đang chạy. Không assert hai masked strings phải bằng nhau; thay vào đó dùng mỗi token trả về cho POST đúng session và kiểm hành vi. Giải thích sự khác biệt expected raw token trong repo với request handler exposed token.

### Bài 7 — Preflight đi trước marker/Security

Gửi OPTIONS `/secure/orders` với Origin allowlisted và `Access-Control-Request-Method: POST` qua mock/live. Assert 200 + ACAO, không Basic/session, không có `X-Demo-Filter`, ledger 0. Gửi bare OPTIONS thiếu Origin/ACRM và giải thích vì sao nó đi tiếp Security như request thường.

### Bài 8 — CORS origin trái policy

Gửi preflight từ `https://attacker.example`. Kiểm mock và live không cấp ACAO, thường 403 trong fixture. Sau đó test qua một staging ingress do bạn sở hữu để xác định CDN/WAF có thêm ACAO trùng hoặc vô tình mở wildcard credentials không. Không lấy CORS làm cơ chế authentication.

### Bài 9 — Actual POST sau preflight

Thử preflight 200 rồi actual POST thiếu CSRF nhận 403. Thêm Basic+SESSION+token đúng và nhận 201. Viết báo cáo ngắn phân biệt **permission của origin**, authentication và CSRF, vì sao cả ba cần kiểm độc lập.

### Bài 10 — Redirect controller và HTTPS

Kiểm `GET /public/redirect` trả 303 `Location: /public/ping` trên mock/live, sau đó GET đích riêng. Trên staging HTTPS, kiểm redirect HTTP → HTTPS do edge hoặc Security (nếu có), HSTS trên HTTPS và không chứa internal hostname. Không auto-follow ngay ở bước assert 3xx đầu.

### Bài 11 — Kiểm URL normalization nhưng không bypass Security

Chọn các URL benign nhưng bất thường như double slash và semicolon trên server test-owned. Dùng WebTestClient URI builder và `curl --path-as-is`, ghi status/marker/response owner. Đừng cố “sửa” Spring firewall để chúng có đúng một status; invariant quan trọng là anonymous không truy cập resource protected và không tạo side effect.

### Bài 12 — Handler không tồn tại vs parser/firewall reject

So một URL canonical không có controller, một HTTP request malformed do parser reject, một request bị CORS filter reject và một request bị CSRF từ chối. Xây bảng gồm status, `X-Demo-Filter`, `Content-Type`, ACAO và side effects. Giải thích vì sao “404” đơn độc không chỉ ra Security đã bị bypass.

### Bài 13 — Streaming/buffering

Tạo endpoint `Flux<String>` trả Server-Sent Events theo nhiều emissions. Test unit bằng `StepVerifier`, mock WebTestClient và HTTP thật qua Reactor Netty. Thử client cancellation/slow consumer trong môi trường test, xác minh cleanup và không làm lộ principal qua subscription độc lập. Phân biệt chunks trên wire với values của publisher.

### Bài 14 — Test client state isolation

Trong live suite, tạo một WebTestClient có default Basic header Alice và một baseline anonymous. Gọi cùng URL và kiểm Alice 200, anonymous 401. Thử một cookie jar chứa `SESSION` cũ và xác nhận negative CSRF tests không tự dùng session từ trước. Không chia sẻ client có credentials giữa test classes.

### Bài 15 — Reverse proxy rewrite ở staging

Ingress expose `/gateway/secure/whoami` nhưng app nhận `/secure/whoami`. So mock internal path, `RANDOM_PORT` internal path và public HTTPS path; kiểm security chain matcher/cookie Path/Location/HSTS. Tái hiện cấu hình strip-prefix sai trong dedicated test environment để xem vì sao status/route không giống mock.

### Bài 16 — Multi-pod session sharing

Chạy hai instance WebFlux dùng shared Spring Session/Redis test container; ép GET `/csrf` vào pod A và POST với S1/token vào pod B. So với hai pod dùng riêng memory store. Bổ sung logout/session invalidation và rolling deploy smoke test; không ghi raw session/token vào artifacts.

### Bài 17 — Contract helper chung

Áp dụng `SharedHttpContracts.assertPublicPing`/`assertAnonymousDenied` cho mock và live. Bổ sung một contract cho CORS preflight allowlisted và redirect. Ghi một test tách riêng cho auth mock và HTTP Basic thật; giải thích tại sao không nên cố chia sẻ code `mockUser()`/`csrf()` sang TCP client.

### Bài 18 — CI phân lớp

Xây pipeline chạy mock suite ở mọi push, `RANDOM_PORT` suite với Redis/R2DBC Testcontainers ở merge request, staging HTTPS browser smoke sau deploy. Đo tỉ lệ false positives, runtime, khả năng định vị lỗi và dữ liệu leak giữa test runs. Thử đảo thứ tự test, chạy nhiều workers song song khi đã có namespace isolation.

## 23. Checklist triển khai bộ test bảo vệ HTTP WebFlux

- [ ] Xác nhận runtime là **Reactive WebFlux**, không dùng nhầm Servlet `HttpSecurity`/`CorsFilter`/`MockMvc`.
- [ ] Spring Framework/Security/Boot/test dependencies tương thích theo BOM.
- [ ] Mock và live dùng cùng application classes, active profile và Security policy khi cần đối chiếu.
- [ ] Mock test sử dụng `bindToApplicationContext(context).apply(springSecurity())` để lấy WebFilters thật từ context.
- [ ] Không coi `bindToController`/`@WebFluxTest` slice tự có toàn bộ custom filter/security chain.
- [ ] Live test dùng `@SpringBootTest(RANDOM_PORT)` hoặc `bindToServer`, không gọi nhầm app cổng cũ.
- [ ] Boot 3.5/4 package của `@AutoConfigureWebTestClient` được chọn đúng.
- [ ] Global `WebFilter` order khác internal `SecurityWebFiltersOrder`/`SecurityWebFilterChain` order.
- [ ] Marker/instrumentation chỉ bật test profile, không để lộ nội bộ vào production.
- [ ] CORS filter owner được xác định: global trước Security **hoặc** Security-managed, không nhân đôi vô cớ.
- [ ] CORS preflight OPTIONS có `Origin`/`Access-Control-Request-Method`, không cookie/auth.
- [ ] Positive preflight assert **ACAO/method/header**, không chỉ status 200.
- [ ] Negative origin/method/header preflight không được cấp quyền ngoài allowlist.
- [ ] Không coi bare OPTIONS không ACRM là CORS preflight.
- [ ] Actual CORS GET/POST vẫn đi qua authentication, authorization và CSRF phù hợp.
- [ ] Anonymous protected route có negative control 401/302 theo chain.
- [ ] Mock `mockUser()` chỉ dùng kiểm authorization, không coi là password authentication.
- [ ] Live Basic/form/Bearer tests gửi credentials thực và có negative invalid-credential cases.
- [ ] `mockJwt()` không được dùng thay JWT signature/expiry/issuer verification thật.
- [ ] Mock `csrf()` có positive và negative controls, không nằm ở baseline client vô tình.
- [ ] Live POST dùng actual CSRF token và WebSession cookie từ GET bootstrap, không dùng mock mutator.
- [ ] CSRF cookie/token khác session không được lẫn khi dùng WebSession repository.
- [ ] Cookie CSRF repo được test theo semantics riêng, không gán sai WebSession binding.
- [ ] Side-effect counter/DB rows/events bằng 0 khi auth/CSRF bị chặn.
- [ ] Security header `nosniff`, CSP explicit và cache-control được kiểm trên đúng response owner.
- [ ] HSTS được kiểm ở **HTTPS**, không bắt HTTP plaintext phải có.
- [ ] `Location` redirect kiểm scheme/host/path/port theo public contract, không chỉ status 3xx.
- [ ] Public CDN/ingress redirects/CSP/HSTS được test ở edge, không suy từ localhost.
- [ ] Trusted forwarded headers được cấu hình theo proxy boundary, không tin untrusted Host/X-Forwarded.
- [ ] URL canonical/encoded/double slash/matrix variables có firewall/authorization tests riêng.
- [ ] Không assert status 400 tuyệt đối cho mọi malformed URL nếu parser/proxy có thể khác.
- [ ] HTTP parser/headers/body limits, streaming/timeout/connection behavior có live tests nếu threat model yêu cầu.
- [ ] Không snapshot `SESSION`/CSRF token/`Date`/ephemeral port hoặc header ordering.
- [ ] Test WebSession multi-replica nếu production có nhiều pods/shared session store.
- [ ] Browser E2E kiểm CORS/CSP/HSTS/`SameSite`/`Secure` và cookie credential mode.
- [ ] Test client credentials/default cookies không bị reuse ở anonymous tests.
- [ ] `OrderLedger` singleton test reset an toàn, suite không chạy song song nếu còn shared state.
- [ ] External Redis/DB cleanup chỉ trên namespace/test-owned data; không dọn production.
- [ ] Reactive side effects/cleanup được compose/await, không fire-and-forget `subscribe()`.
- [ ] Logs/CI artifacts không lộ raw CSRF/JWT/session cookies/Basic passwords.
- [ ] Mỗi security-sensitive path có positive control, negative control và side-effect assertion.
- [ ] CI chạy mock trước, HTTP server sau, public staging/browser theo topology.
- [ ] Khi test khác nhau, đã xác định request inputs, selected chain, response owner và transport boundary trước khi sửa security config.

## 24. Tài liệu chính thức và nguồn bổ sung

1. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — `bindToController`, `bindToApplicationContext`, `bindToServer`, mock/live server setups và response assertions.
2. [Spring Framework — Reactive Core / WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — `HttpHandler`, `WebHandler`, server adapters/Netty, filters và reactive contract.
3. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html) — `MOCK`/`RANDOM_PORT`, `@AutoConfigureWebTestClient`, server/client transaction boundaries.
4. [Spring Boot current — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — package mới của `@AutoConfigureWebTestClient` trong Boot 4, WebFlux slice/full tests.
5. [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — `apply(springSecurity())` và WebFlux test integration.
6. [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html) — `mockUser`, `@WithMockUser`, principal/authorities test scope.
7. [Spring Security — Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — `csrf()` test mutator và phạm vi positive controls.
8. [Spring Security — Reactive OAuth2/JWT Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html) — `mockJwt`/`mockOidcLogin`, giới hạn không test token decoder/issuer/signature.
9. [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — `Mono<CsrfToken>`, WebSession repository, XOR/BREACH request handler.
10. [Spring Security — WebFlux CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — preflight không có cookie và CORS phải được xử lý trước authentication.
11. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, matcher/order, Reactive Security DSL.
12. [Spring Security — Reactive HTTP Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — nosniff, cache, CSP, HSTS trên HTTPS.
13. [Spring Security — Reactive Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — `ServerWebExchangeFirewall`, `StrictServerWebExchangeFirewall` và Security 6.4+ behavior.
14. [Spring Security API — WebFilterChainProxy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/WebFilterChainProxy.html) — chọn SecurityWebFilterChain và request firewall.
15. [Spring Framework API — WebHttpHandlerBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html) — WebFlux chain dựng từ ApplicationContext.
16. [Spring Framework API — WebSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html) — session start/save/invalidate và session lifecycle.
17. [Spring Session — Common Configurations](https://docs.spring.io/spring-session/reference/configuration/common.html) — Reactive WebSession ID/cookie resolver, shared session store/config.
18. [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) — browser preflight, credentials, allow-origin/headers.
19. [MDN — HSTS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security) — HTTPS-only, browser policy theo hostname.
20. [OWASP — CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — cookie-bound credentials, token patterns và defense in depth.
21. [OWASP — HTTP Security Response Headers](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) — scope của security headers tại public HTTP entrypoint.
22. [OWASP — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — default-deny, object-level/tenant authorization ngoài URL firewall.

## 25. Tổng kết và tự đánh giá

**Ba tầng không thay thế nhau:**

1. **Mock WebFlux/WebTestClient**: kiểm filter chain, authorization, CSRF/CORS conditions, handler/header behavior trong context đã nạp; rất nhanh và xác định lỗi tốt, nhưng không có TCP/TLS/proxy.
2. **HTTP server thật qua `RANDOM_PORT`/`bindToServer`**: kiểm HTTP adapter, authentication credentials thật, WebSession cookie/token, serialization/headers/redirects, parser và network behavior; vẫn có thể chỉ là HTTP localhost.
3. **Browser HTTPS/public staging**: kiểm toàn đường đi CDN/ingress/TLS, CORS/CSP/HSTS/`SameSite` và redirect/cookie behavior của browser; đây là nơi những assumption của local test thường bị phá vỡ.

**Câu hỏi tự đánh giá:** Tại sao `bindToApplicationContext` được coi là integration test của WebFilters nhưng vẫn là mock HTTP? `bindToController` khác ở điểm nào? Vì sao `mockUser()` không kiểm Basic password, còn `csrf()` không kiểm token/session round-trip? Khi nào một 200 OPTIONS vẫn có thể bị browser từ chối? Nếu preflight không mang `X-Demo-Filter` nhưng GET actual có, có nhất thiết filter bị mất không? Vì sao một POST thiếu CSRF phải assert cả 403 lẫn không có side effect? Làm thế nào dùng một `CsrfPayload` từ server thật với cookie session đúng? Vì sao HSTS vắng ở HTTP localhost nhưng có ở HTTPS mock scheme hoặc HTTPS public? Nếu URL double slash bị live Netty trả 404 nhưng mock firewall trả 400, invariant nào cần kiểm thay vì ép status giống nhau? `@LocalServerPort` và `RANDOM_PORT` giảm rủi ro gì? Khi reverse proxy strip-prefix sai hoặc không tin `Forwarded` đúng cách, Authorization/Location/cookie có thể lệch ra sao? Và bạn sẽ chọn những test nào trong mock, live HTTP, Redis multi-node và browser để chứng minh ứng dụng Spring Security WebFlux thực sự được bảo vệ qua toàn bộ đường đi request?
