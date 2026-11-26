# Kiểm tra header cùng redirect trên ứng dụng WebFlux

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Chủ đề:** Kiểm thử đồng thời **HTTP response headers** và **redirects** trong ứng dụng Spring Security WebFlux: các header mặc định, CSP, HSTS, cookie/session, redirect khi chưa xác thực, sau login/logout, từ controller và khi buộc HTTPS.  
> **Phạm vi:** Spring Security 6.5/7.x, Spring Framework WebFlux, Spring Boot 3.5/4.x, JUnit Jupiter và `WebTestClient`; ví dụ Java 17+. Chú ý sự khác biệt giữa mock WebTestClient, HTTP server thật và browser qua TLS/reverse proxy.

## 1. Vì sao cần kiểm tra header **cùng** redirect?

Một ứng dụng WebFlux có thể trả:

```http
HTTP/1.1 302 Found
Location: /login
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

Một test chỉ viết `expectStatus().is3xxRedirection()` chưa đủ. Response có thể redirect tới **sai địa chỉ**, tạo open redirect, rò host nội bộ, chuyển từ HTTPS xuống HTTP hoặc thiếu header cần thiết. Ngược lại, test chỉ assert `nosniff`/CSP trên HTTP 200 có thể bỏ sót **response 302/401/403** được client và browser nhận trong luồng authentication.

Tình huống sản xuất điển hình:

1. Người dùng truy cập `GET /account/home` khi chưa login.
2. Spring Security redirect đến `/login` (hoặc API dùng Bearer trả 401, không redirect).
3. Sau login thành công, server đưa người dùng về URL phù hợp theo request-cache/success strategy.
4. Người dùng POST tạo đơn, handler trả 303 để client tải trang xác nhận bằng GET.
5. Ứng dụng chạy sau ingress HTTPS, nhưng Spring nhìn thấy HTTP nội bộ và tạo `Location: http://...` hoặc vòng lặp redirect.
6. Một số trang HTML do CDN/frontend khác phục vụ có CSP/HSTS khác với response JSON từ WebFlux.

Muốn khẳng định đúng chính sách, phải kiểm tra **status + Location + response headers + cookie/session + selected security chain + hành vi qua browser**. Bài này tổ chức các kiểm thử đó theo mức độ tin cậy.

### 1.1. Kết quả học tập

Người học sẽ:

1. Phân biệt redirect từ controller với redirect do `ServerAuthenticationEntryPoint`, authentication success/failure, logout và `redirectToHttps`.
2. Hiểu security headers mặc định của Spring Security và những header cần chủ động cấu hình, đặc biệt CSP, HSTS, `Referrer-Policy`.
3. Dùng `WebTestClient` kiểm tra `Location`, 301/302/303/307/308, `Cache-Control`, `X-Content-Type-Options`, `X-Frame-Options` và CSP.
4. Kiểm chứng **HSTS chỉ có trên response HTTPS**, không nhầm với redirect HTTP → HTTPS.
5. Viết tests cho đăng nhập chưa xác thực, POST có/thiếu CSRF, login/logout và API trả 401 thay vì redirect.
6. Chống open redirect, protocol downgrade, rò host/port nội bộ, redirect loops, cache/headers sai trên 3xx.
7. Đối chiếu mock context, live `RANDOM_PORT`, ingress/CDN và browser HTTPS; tách CORS/cookie/CSP issues.
8. Xây ma trận hồi quy và runbook chẩn đoán có thể đưa vào CI.

## 2. Response headers và redirects có quan hệ thế nào?

Redirect là **một response HTTP** có status 3xx và thường có `Location` cho client đi tới URL khác; security headers cũng là các field trên response ấy. Nhưng hiệu lực của chúng có phạm vi khác nhau:

| Thành phần | Vai trò | Kiểm thử cần làm |
| --- | --- | --- |
| `Location` | Đích client có thể đi tới | Scheme, host, port, path, query, allowlist và encoding |
| `Cache-Control` | Kiểm soát lưu response | Trang nhạy cảm/redirect login không bị cache tùy tiện |
| `X-Content-Type-Options: nosniff` | Hạn chế MIME sniffing | Có trên response qua Security chain |
| `X-Frame-Options` / CSP `frame-ancestors` | Chống framing/clickjacking | Header trên **HTML document** cần bảo vệ |
| `Content-Security-Policy` | Hạn chế script, frame, connect, resource loads | **Chủ động cấu hình** cho HTML; không giả định default |
| `Strict-Transport-Security` | Chính sách HTTPS của **hostname** mà browser nhớ | Chỉ assert trên HTTPS và qua public host |
| `Referrer-Policy` | Điều khiển dữ liệu Referer ra ngoài | Assert theo policy/version thực tế |
| `Set-Cookie` | Session/security cookie | `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, rotation/logout |
| `Access-Control-Allow-*` | Browser cross-origin response access | Origin, method, headers; không thay authentication/CSRF |

### 2.1. Các loại redirect cần phân biệt

| Nguồn redirect | Ví dụ | Điểm dễ kiểm thử sai |
| --- | --- | --- |
| Controller `ResponseEntity` | `GET /public/go` → `/public/landing` | Chỉ kiểm status, không check Location |
| Spring Security form login entry point | Anonymous `/account/home` → `/login` | API cũng bị 302 thay vì trả 401 |
| Login success/failure handler | Đăng nhập thành công → saved request/home; sai password → error page | Request cache/session sai, redirect tới URL ngoài |
| Logout success handler | POST `/logout` → logout success | Cookie/session cũ vẫn dùng được |
| `redirectToHttps` | `http://...` → `https://...` | Redirect loop sau TLS termination |
| Reverse proxy/CDN | HTTP → HTTPS hoặc canonical host | Location bị đổi host, mất path/query |

### 2.2. Các mã trạng thái redirect không hoàn toàn tương đương

| HTTP status | Ý nghĩa | Phương thức cho request kế tiếp |
| --- | --- | --- |
| 301 Moved Permanently | Đích mới có tính dài hạn | User agent lịch sử có thể chuyển POST thành GET |
| 302 Found | Redirect tạm | User agent lịch sử có thể chuyển POST thành GET |
| 303 See Other | Sau POST, client **nên** truy cập Location bằng GET | Phù hợp Post/Redirect/Get |
| 307 Temporary Redirect | Redirect tạm và **giữ method/body** | Cẩn trọng khi redirect POST và auth credentials |
| 308 Permanent Redirect | Redirect lâu dài và **giữ method/body** | Không dùng bừa cho flow login |

Không hard-code “mọi redirect phải là 302”. Hãy xác định semantics từng endpoint: sau POST thành công thường chọn **303**; redirect HTTPS có status tùy framework/proxy và policy đã thiết kế. Mã 3xx cùng `Location` không tự chứng minh browser đã tới đích.

### 2.3. Đừng tự động theo redirect trong kiểm thử đầu tiên

Trình duyệt có thể tự follow redirect, nhưng kiểm thử **response trung gian** cần nhìn được:

```text
GET /account/home
  |
  +-- 302 Location: /login
          |
          +-- GET /login -> 200 HTML login
```

Hai HTTP responses có thể do **hai chains/servers khác nhau** tạo ra và mang headers khác nhau. Đầu tiên assert riêng 302 + Location + security headers; sau đó GET đích ở một bước khác. Nếu client/tool tự follow, bạn có thể chỉ thấy status cuối 200 và mất bằng chứng redirect đúng.

## 3. Security headers mặc định và những điều không nên mặc định

Spring Security cung cấp headers an toàn mặc định khi request đi qua chain có header writers. Theo tài liệu chính thức về HTTP Response Headers, các giá trị phổ biến gồm:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
```

**HSTS chỉ được thêm vào HTTPS responses**, không coi nó là header mặc định cho HTTP plaintext. `X-XSS-Protection` là header legacy, giá trị `0` nhằm tắt các XSS Auditor cũ; nó **không** thay thế CSP hay output encoding.

### 3.1. Trạng thái mặc định cần kiểm tra theo phiên bản

| Header | Mặc định phổ biến | Khi nào viết test? |
| --- | --- | --- |
| `Cache-Control`/`Pragma`/`Expires` | Chống cache nội dung nhạy cảm | HTML login, account API, redirect auth |
| `X-Content-Type-Options` | `nosniff` | HTML, JSON, JS và 3xx thuộc chain |
| `X-Frame-Options` | `DENY` | HTML/iframe policy |
| `Strict-Transport-Security` | HTTPS-only, thời hạn tùy config | Trên URL HTTPS thật, proxy và redirects |
| `X-XSS-Protection` | Thường `0` ở các dòng hỗ trợ | Không coi là lớp chống XSS chính |
| `Content-Security-Policy` | **Không được tự thêm một CSP ứng dụng hoàn chỉnh** | Phải cấu hình và test trên HTML |
| `Referrer-Policy` | Tài liệu WebFlux theo dòng có thể đặt mặc định `no-referrer`; cần kiểm chứng resolved version | Assert policy dự án, không suy từ Servlet docs |
| `Permissions-Policy` | Không giả định có sẵn | Chỉ assert khi chủ động cấu hình |
| `Clear-Site-Data` | Không mặc định cho mọi response | Test logout flow nếu đã thiết kế |

**Ghi chú phiên bản:** tài liệu Reactive hiện hành mô tả `Referrer-Policy: no-referrer` là default, trong khi tài liệu Servlet mô tả khác. Vì vậy hãy kiểm tra **WebFlux và version đang chạy**, không copy nguyên assertions của Servlet/MockMvc sang Reactive. Các ví dụ test dưới đây dùng những header cố ý cấu hình hoặc có hành vi mặc định được nêu rõ.

### 3.2. Header writer có thể nhường chỗ cho response cache policy

Default cache writer của Spring Security thường không ghi đè `Cache-Control` đã được ứng dụng đặt. Vì thế với asset public (JS/CSS/hash-file) bạn có thể chủ động trả:

```http
Cache-Control: public, max-age=3600
```

và giữ `nosniff`/các lớp khác. Test cần phân biệt **private account page** với **immutable static asset**; không assert toàn bộ responses luôn `no-store`, điều đó khiến caching hợp pháp bị phá.

### 3.3. Header hiệu lực phụ thuộc owner của response

`SecurityWebFilterChain` chỉ ghi headers cho response nằm trong pipeline của nó. Nếu:

- CDN phục vụ trực tiếp HTML,
- Nginx/Ingress trả 301/302 trước khi tới app,
- gateway tự xử lý OPTIONS preflight,
- request bị server/parser từ chối trước WebFlux,

thì không được suy những response đó tự nhận mọi Spring Security headers. Cần xác định **owner** của từng response rồi test đúng lớp, nhất là CSP trên HTML và HSTS tại public HTTPS host.

## 4. WebFlux và Servlet: import nhầm dễ khiến bài test sai

| Servlet security/test | Reactive WebFlux security/test |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpServletResponse`, `OncePerRequestFilter` | `ServerHttpResponse`, `WebFilter` |
| `MockMvc` | `WebTestClient` |
| `SecurityMockMvcRequestPostProcessors.csrf()` | `SecurityMockServerConfigurers.csrf()` |
| `HeaderWriterFilter` Servlet | `HttpHeaderWriterWebFilter` Reactive |
| `RedirectStrategy` Servlet | `ServerRedirectStrategy`/Reactive authentication entry point |

Đừng dùng snippets Servlet `HttpSecurity.headers(...).cacheControl(...)` để thay WebFlux APIs: Reactive DSL dùng `.headers(headers -> headers.cache(cache -> ...))` và các spec tương ứng. Không dùng `MockMvc` để kết luận một WebFlux `SecurityWebFilterChain` đã ghi headers.

## 5. Cách tổ chức tests có độ tin cậy tăng dần

| Cấp | Cách chạy | Chứng minh được | Chưa chứng minh |
| --- | --- | --- | --- |
| Unit controller | Gọi method trực tiếp hoặc bind controller đơn giản | Controller tạo `ResponseEntity.status/location` | Security headers/auth redirect |
| Mock app context | `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` | Headers/redirect trong Security WebFilters, status và Location | TLS thật, gateway, browser HSTS |
| Full context | `@SpringBootTest` + bind to context | Wiring và Security chains gần runtime | Không tự mở TCP |
| Live HTTP | `@SpringBootTest(RANDOM_PORT)` / `bindToServer()` | Server adapter, real auth/cookies, redirect status | HTTPS public/edge nếu chạy HTTP local |
| Browser HTTPS staging | Playwright/Selenium/browser DevTools | Redirect chain, cookie rules, CSP/HSTS, CORS và gateway | Không thay kiểm tra multi-region production |

Các tests mock là nền tảng ổn định để phát hiện regressions nhanh, nhưng HSTS và cookie `Secure/SameSite` phải được xác nhận qua **browser HTTPS** khi phát hành.

## 6. Dependencies cho fixture kiểm thử WebFlux

### 6.1. Gradle với Spring Boot quản lý BOM

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

### 6.2. Maven test dependencies

```xml
<dependencies>
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
```

Spring Boot 4 có thể dùng những test starters được tách theo web stack, ví dụ WebFlux test starter. Dùng dependency và test annotation **đúng dòng đang chạy**; không tự pin Spring Security version khác với BOM. Để xác minh version resolved:

```bash
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Trên Windows dùng wrapper `gradlew.bat`/`mvnw.cmd`. Các snippets là tài liệu thực hành; bài viết ở STEP 4 chưa chạy build hoặc QA chuyên môn STEP 6.

## 7. Controller fixture: HTML, assets, business redirect và POST/303

Controller dưới đây tách rõ response từ **controller** và redirect do Spring Security. Nó dùng những đích cố định; không echo URL tự do từ query string vào `Location`.

### 7.1. Bộ đếm side effect

```java
package com.example.protection.redirects;

import java.util.concurrent.atomic.AtomicInteger;

final class OrderCounter {
    private final AtomicInteger created = new AtomicInteger();

    int value() {
        return created.get();
    }

    void reset() {
        created.set(0);
    }

    void record() {
        created.incrementAndGet();
    }
}
```

Đây là counter **test-only** để chứng minh request bị chặn không thực thi nghiệp vụ; với hệ thống thực, verify service/repository hoặc test database isolation.

### 7.2. Controller trả response và Location

```java
package com.example.protection.redirects;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class HeaderRedirectController {

    public record CsrfEnvelope(String headerName, String token) {}

    private static final Map<String, String> REDIRECTS = Map.of(
        "landing", "/public/landing",
        "account", "/account/home"
    );

    private final OrderCounter counter;

    public HeaderRedirectController(OrderCounter counter) {
        this.counter = counter;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/public/document",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> htmlDocument() {
        return Mono.just(
            "<!doctype html><html><head><title>Demo</title></head>"
            + "<body><h1>Safe demo</h1></body></html>"
        );
    }

    @GetMapping("/public/landing")
    public Mono<String> landing() {
        return Mono.just("landing");
    }

    @GetMapping("/account/home")
    public Mono<String> accountHome() {
        return Mono.just("account-home");
    }

    @GetMapping("/public/cacheable")
    public Mono<ResponseEntity<String>> cacheableAsset() {
        return Mono.just(ResponseEntity.ok()
            .cacheControl(
                CacheControl.maxAge(Duration.ofHours(1)).cachePublic()
            )
            .body("public-static-content"));
    }

    @GetMapping("/public/go")
    public Mono<ResponseEntity<Void>> redirectToLanding() {
        return Mono.just(ResponseEntity.status(HttpStatus.FOUND)
            .location(URI.create("/public/landing"))
            .build());
    }

    @GetMapping("/public/keep-method")
    public Mono<ResponseEntity<Void>> temporaryRedirect() {
        return Mono.just(ResponseEntity
            .status(HttpStatus.TEMPORARY_REDIRECT)
            .location(URI.create("/public/landing"))
            .build());
    }

    @GetMapping("/public/choose")
    public Mono<ResponseEntity<Void>> allowedRedirect(
            @RequestParam(defaultValue = "landing") String next) {
        String target = REDIRECTS.getOrDefault(
            next, "/public/landing");
        return Mono.just(ResponseEntity.status(HttpStatus.SEE_OTHER)
            .location(URI.create(target))
            .build());
    }

    @PostMapping("/account/orders")
    public Mono<ResponseEntity<Void>> createOrder() {
        return Mono.fromSupplier(() -> {
            counter.record();
            return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create("/account/home"))
                .build();
        });
    }

    @GetMapping("/public/csrf")
    public Mono<ResponseEntity<CsrfEnvelope>> csrf(
            ServerWebExchange exchange) {
        Mono<CsrfToken> source =
            exchange.getAttribute(CsrfToken.class.getName());

        if (source == null) {
            return Mono.error(new IllegalStateException(
                "CsrfWebFilter is not active"));
        }
        return source.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfEnvelope(
                token.getHeaderName(), token.getToken())));
    }
}
```

**Đọc code đúng mục đích:**

- `/public/go` trả **302** với Location nội bộ cố định.
- `/public/keep-method` trả **307** để minh họa redirect giữ method; route này là GET và không tạo dữ liệu, nên không có chuyện vô ý retry POST.
- `/public/choose?next=...` chỉ chấp nhận **key** trong map `REDIRECTS`, không chấp nhận URL do user đưa vào. Input lạ sẽ đưa về landing nội bộ.
- `POST /account/orders` chỉ chạy khi **được xác thực và có CSRF hợp lệ**, trả **303** để client tiếp tục GET. Side effect được thực thi một lần trước response 303.
- `GET /public/csrf` tiêu thụ `Mono<CsrfToken>` của WebFlux để bootstrap token/session thật. Endpoint chỉ dùng cho fixture; nếu làm production, cần CORS, cache và exposure policy rõ ràng.
- `/public/document` là HTML do chính WebFlux tạo. Nếu HTML thực của SPA nằm ở CDN, phải test headers trên **CDN response** thay vì nghĩ Security chain của API luôn sở hữu CSP.

## 8. Security fixture: form login, CSRF và CSP tường minh

### 8.1. Cấu hình WebFlux và user store test-only

```java
package com.example.protection.redirects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class RedirectWebConfig {
    @Bean
    OrderCounter orderCounter() {
        return new OrderCounter();
    }

    @Bean
    HeaderRedirectController headerRedirectController(
            OrderCounter counter) {
        return new HeaderRedirectController(counter);
    }
}
```

`@EnableWebFlux` thích hợp với **Spring Test context thuần**, còn Spring Boot app đã tự cấu hình WebFlux thì không nên thêm tùy tiện vì có thể thay đổi Boot auto-config.

### 8.2. Security chain chuyên thử redirect login và headers

```java
package com.example.protection.redirects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class HeaderRedirectSecurityConfig {

    @Bean
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/login").permitAll()
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(policy -> policy
                    .policyDirectives(
                        "default-src 'self'; "
                        + "object-src 'none'; "
                        + "base-uri 'self'; "
                        + "frame-ancestors 'none'"
                    )
                )
            )
            .build();
    }

    @Bean
    MapReactiveUserDetailsService testUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password("{noop}test-only-password")
                .roles("USER")
                .build()
        );
    }
}
```

Ta bật **form login** và chủ động tắt HTTP Basic ở browser chain để yêu cầu anonymous `GET /account/home` được redirect sang trang login, không bị nhiễu bởi một Basic entry point trả 401. Nếu triển khai API JSON Bearer-only, test **401 thay cho 302** ở chain riêng (mục sau).

**CSP được cấu hình rõ ràng**, vì Spring Security không thể tự tạo CSP đáp ứng mọi website. Policy trên được áp cho responses qua chain, nhưng ý nghĩa browser đặc biệt quan trọng với **HTML document**; nó chỉ là điểm khởi đầu của một policy thật. Nếu trang có scripts, styles, fonts, API calls, WebSocket hoặc third-party resources, phải review `script-src/style-src/connect-src/frame-src` và nguồn tin cậy.

`frame-ancestors 'none'` ngăn framing theo CSP; `X-Frame-Options: DENY` của default header writers hỗ trợ defense in depth. Không sửa cả hai thành allow-all vì một iframe integration chưa được review.

**Password `{noop}` chỉ cho test**, tuyệt đối không đưa vào môi trường production.

### 8.3. Test context và WebTestClient

```java
package com.example.protection.redirects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    RedirectWebConfig.class,
    HeaderRedirectSecurityConfig.class
})
class HeaderAndRedirectWebFluxTest {

    @Autowired ApplicationContext context;
    @Autowired OrderCounter counter;

    WebTestClient client;

    @BeforeEach
    void setup() {
        counter.reset();
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .baseUrl("http://local.test")
            .build();
    }

    // Các @Test ở các mục 9–17 bên dưới nằm trong class này.
}
```

`bindToApplicationContext` dựng **WebFlux handler chain cùng Spring Security**, không mở TCP port. `apply(springSecurity())` tích hợp security test support cho `mockUser`/`csrf`. Test class dùng HTTP scheme mặc định cho hầu hết assertions; khi cần mô phỏng HTTPS, tạo client bằng `client.mutate().baseUrl("https://local.test").build()`. Mô phỏng scheme **không thay thử TLS thật**.

Counter được reset ở `@BeforeEach`; do Spring test context có bean dùng chung, các tests này giả định chạy tuần tự. Nếu bật parallel JUnit, cô lập counter/session state theo test instance.

### 8.4. Không dùng `bindToController` để kết luận header writer đang chạy

```java
WebTestClient controllerOnly =
    WebTestClient.bindToController(
        new HeaderRedirectController(new OrderCounter()))
    .build();
```

Client trên chỉ nạp controller và WebFlux infrastructure tối thiểu; **không tự dùng `HeaderRedirectSecurityConfig` hay toàn bộ Security WebFilters**. Nếu thiếu `nosniff`/`HSTS` trong controller-only test, chưa thể kết luận production Security config sai. Với header/redirect do Security tạo, phải bind full application context hoặc HTTP server thật.

## 9. Test security headers trên HTTP 200

### 9.1. `nosniff`, `X-Frame-Options` và cache-control

Thêm tests vào `HeaderAndRedirectWebFluxTest`:

```java
@Test
void publicHtmlGetsSecurityHeaders() {
    client.get().uri("/public/document")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
            org.springframework.http.MediaType.TEXT_HTML)
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff")
        .expectHeader().valueEquals(
            "X-Frame-Options", "DENY")
        .expectHeader().valueMatches(
            "Cache-Control", "(?i).*no-store.*");
}
```

Những assertions được viết dựa trên **chain cụ thể đang dùng**: Security headers mặc định còn bật và HTML đi qua chain. Không kết luận rằng mọi HTTP 200 từ *CDN hoặc proxy* đều có các header này.

### 9.2. CSP được chủ động cấu hình: assert cả tên và directives

```java
@Test
void htmlGetsExplicitCspPolicy() {
    client.get().uri("/public/document")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().value("Content-Security-Policy", value -> {
            assertTrue(value.contains("default-src 'self'"));
            assertTrue(value.contains("object-src 'none'"));
            assertTrue(value.contains("base-uri 'self'"));
            assertTrue(value.contains("frame-ancestors 'none'"));
        });
}
```

`Content-Security-Policy` **không được Spring Security tạo sẵn một policy hoàn chỉnh mặc định**; test này pass vì `HeaderRedirectSecurityConfig` đã gọi `headers.contentSecurityPolicy(...).policyDirectives(...)`. Nếu CSP được cấu hình ở CDN nhưng HTML không đi qua WebFlux, test phải chạy qua CDN public entrypoint.

### 9.3. Không phụ thuộc vào thứ tự CSP directives

Browser xử lý CSP theo cấu trúc directives, không yêu cầu thứ tự hard-code:

```text
default-src 'self'; object-src 'none'; base-uri 'self'
```

và

```text
base-uri 'self'; object-src 'none'; default-src 'self'
```

có thể tương đương với một số policy. Khi kiểm thử, assert directives cần thiết và kiểm tra CSP bằng browser, không dùng một chuỗi equals duy nhất nếu framework/CDN có thể sắp xếp lại. Nhưng đừng chỉ assert header “tồn tại”: policy `default-src *; script-src * 'unsafe-inline'` có thể vẫn nguy hiểm.

### 9.4. HTML phải là đúng response owner

`CSP frame-ancestors` và `X-Frame-Options` có ý nghĩa với **document mà browser cố render trong iframe**. Nếu application thực tế trả React SPA HTML từ Nginx nhưng Spring Security chỉ trả JSON, việc JSON có CSP không bảo vệ tài liệu HTML do Nginx tạo. Xác định owner của `index.html`/login page và test từ hostname/cổng mà người dùng thật truy cập.

## 10. Cache header trên static asset khác trang nhạy cảm

Trong fixture, `GET /public/cacheable` đặt explicit `Cache-Control: public, max-age=3600`.

```java
@Test
void explicitPublicCachePolicyIsNotSilentlyOverwritten() {
    client.get().uri("/public/cacheable")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().value("Cache-Control", value -> {
            assertTrue(value.contains("public"));
            assertTrue(value.contains("max-age=3600"));
        })
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");
}
```

Đừng áp `Cache-Control: public` cho nội dung cá nhân hóa, CSRF bootstrap token hoặc trang login chỉ để tăng hiệu năng. Với hashed JS/CSS assets, cache public có thể là hợp lý nếu URL/version immutable và hệ thống xử lý invalidation đúng.

### 10.1. Ma trận cache

| Response | Cache policy nên kiểm tra | Lý do |
| --- | --- | --- |
| `GET /account/home` | Thường `no-store` khi mang thông tin nhạy cảm | Không lưu nội dung sau logout |
| `GET /login` | Không cache tùy tiện token/form cá nhân hóa | Tránh form/token cũ |
| `GET /public/csrf` | `no-store` do endpoint đặt | Token gắn session/request handler |
| `GET /public/cacheable` | `public, max-age=3600` trong fixture | Nội dung công khai không cá nhân |
| `GET /public/go` 302 | Theo redirect policy, tránh cache không mong muốn | Không giữ redirect stale |
| `POST /account/orders` 303 | Không cache private operation | Redirect không được làm lộ dữ liệu |

**Lưu ý:** Security cache writer có thể không ghi đè header do controller đặt. Để chứng minh *policy an toàn*, test cả nội dung và cache policy thay vì khẳng định mọi response phải có một header giống hệt.

## 11. Test controller redirect: status và Location phải đi cùng nhau

### 11.1. Redirect 302 hợp lệ

```java
@Test
void controllerRedirectHasExpectedLocationAndHeaders() {
    client.get().uri("/public/go")
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.FOUND)
        .expectHeader().valueEquals(
            "Location", "/public/landing")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff")
        .expectHeader().valueEquals(
            "X-Frame-Options", "DENY");
}
```

Status 302 là **kết quả chủ động của controller**. Nó không phải authentication redirect vì URL công khai, cũng không phải HTTPS redirect vì fixture chưa bật `redirectToHttps`. Điều này giúp test tách nguyên nhân.

### 11.2. Redirect 307 giữ method trên lần truy cập tiếp theo

```java
@Test
void temporaryRedirectUses307Not302() {
    client.get().uri("/public/keep-method")
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.TEMPORARY_REDIRECT)
        .expectHeader().valueEquals(
            "Location", "/public/landing");
}
```

Không dùng 307/308 cho mọi POST form login hoặc thanh toán nếu không chủ định bảo toàn method/body: user agent có thể phát lại cùng request chứa credential/body sang đích redirect. Với Post/Redirect/Get hãy dùng 303 có chủ đích.

### 11.3. Test từng hop để tránh che mất response 302

```java
@Test
void redirectedTargetRespondsSuccessfullyWhenFetchedSeparately() {
    client.get().uri("/public/go")
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.FOUND)
        .expectHeader().valueEquals(
            "Location", "/public/landing");

    client.get().uri("/public/landing")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("landing");
}
```

Đây là **hai requests độc lập**. Chúng chứng minh destination exists; chúng không kiểm tra browser thực hiện auto-follow, cookie transfer giữa hosts, hoặc full redirect chain do proxy tạo. Thêm E2E cho các hành vi đó.

### 11.4. Redirect không được đưa người dùng ra host do input điều khiển

Controller `/public/choose` dùng map **keys** cho phép, không lấy trực tiếp `next` làm Location:

```java
@Test
void untrustedNextParameterCannotCreateOpenRedirect() {
    client.get()
        .uri(uri -> uri.path("/public/choose")
            .queryParam("next", "https://attacker.example/phish")
            .build())
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.SEE_OTHER)
        .expectHeader().valueEquals(
            "Location", "/public/landing");
}

@Test
void knownRedirectKeyCanTargetAccountPage() {
    client.get().uri("/public/choose?next=account")
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.SEE_OTHER)
        .expectHeader().valueEquals(
            "Location", "/account/home");
}
```

Test thứ hai **không tự xác thực** người dùng: redirect tới `/account/home` là một response 303 công khai; khi browser GET `/account/home`, Security vẫn có thể chuyển tiếp tới `/login`. Đó là behavior đúng vì redirect destination không thay authorization.

### 11.5. Các payload open redirect nên có negative tests

Nếu ứng dụng phải nhận tham số `returnTo`/`next`, cần chống nhiều biến thể đầu vào:

| Input | Rủi ro | Kỳ vọng ở fixture |
| --- | --- | --- |
| `https://attacker.example` | External phishing | Fallback path nội bộ |
| `//attacker.example/path` | Scheme-relative external host | Fallback path nội bộ |
| `http://localhost:8080/admin` | Rò internal/local address | Fallback path nội bộ |
| `%2f%2fattacker.example` | Encoded scheme-relative | Fallback sau decode/validation |
| `\\attacker.example` | Browser normalization khác nhau | Fallback |
| `javascript:...` | Unsafe scheme | Fallback |
| `landing` | Key hợp lệ | `/public/landing` |
| `account` | Key hợp lệ | `/account/home` |

Không tự ghép `Location` bằng concatenation với input chưa normalize/validate. Cách dễ kiểm toán là map key → **fixed path**; nếu cần URL ngoài, dùng allowlist **scheme, host, port, path** với redirect service riêng.

## 12. POST/Redirect/GET: kiểm tra 303 và side effect

POST `/account/orders` được auth + CSRF bảo vệ. Khi thành công, controller thực thi side effect rồi trả 303 sang `/account/home`.

### 12.1. POST thiếu CSRF phải bị từ chối

```java
@Test
void unsafePostWithoutCsrfIsRejectedBeforeRedirectHandler() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/account/orders")
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, counter.value());
}
```

Không thấy `Location` trong response 403 là điều bình thường; flow CSRF phải chặn **trước** khi handler tạo đơn và trả 303. Nếu test POST luôn nhận 303 dù thiếu token trong browser chain, kiểm tra CSRF có bị disable/ignored hoặc `csrf()` test mutator đã gắn nhầm trên client dùng chung chưa.

### 12.2. POST authenticated + CSRF mock positive control trả 303

```java
@Test
void successfulPostReturns303SeeOtherWithSafeLocation() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/account/orders")
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.SEE_OTHER)
        .expectHeader().valueEquals(
            "Location", "/account/home")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");

    assertEquals(1, counter.value());
}
```

`csrf()` ở đây chỉ là **mock test hỗ trợ request qua CSRF**; nó không chứng minh token repository/session cookie hoạt động thật. Viết round-trip GET `/public/csrf` → POST cùng session/header nếu muốn kiểm tra token thật, hoặc dùng HTTP server test.

### 12.3. GET destination không tạo order lần nữa

```java
@Test
void getAfter303DoesNotRepeatPostSideEffect() {
    client.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/account/orders")
        .exchange()
        .expectStatus().isEqualTo(
            org.springframework.http.HttpStatus.SEE_OTHER);

    assertEquals(1, counter.value());

    client.mutateWith(mockUser("alice"))
        .get().uri("/account/home")
        .exchange()
        .expectStatus().isOk();

    assertEquals(1, counter.value());
}
```

Đây là kiểm tra **business idempotency qua PRG ở mức demo**. 303 không tự chống double-submit khi browser gửi **hai POST độc lập**; để đảm bảo thanh toán/đặt hàng không trùng, cần idempotency key/deduplication ở domain/API.

## 13. Kiểm tra redirect khi chưa xác thực: `/account/home` → `/login`

Form login của Reactive Spring Security thường dùng `RedirectServerAuthenticationEntryPoint` để đưa browser đến login page. Điều này **khác** API Resource Server trả 401 JSON/WWW-Authenticate.

### 13.1. Anonymous request phải có Location hợp lệ

```java
@Test
void anonymousBrowserRequestRedirectsToLogin() {
    client.get().uri("/account/home")
        .accept(org.springframework.http.MediaType.TEXT_HTML)
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectHeader().valueMatches(
            "Location", ".*/login(?:[?].*)?$")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");
}
```

Biểu thức `[?]` trong regex Java khớp dấu hỏi literal của query string; `Location` có thể tương đối (`/login`) hoặc do redirect strategy tạo absolute URL tùy cấu hình. Nếu app chủ động cam kết `Location: /login` chính xác, có thể dùng `valueEquals("Location", "/login")`. Không hard-code hostname local nếu chạy qua proxy.

### 13.2. Logged-in mock principal không bị redirect

```java
@Test
void authenticatedBrowserCanReadAccountWithoutRedirect() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/account/home")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("account-home");
}
```

Cặp tests này giúp xác nhận response 302 là **authentication entry point**, không phải controller `/account/home` tự trả redirect, vì handler chỉ trả `"account-home"`.

### 13.3. Default login page có thể được Spring Security render

```java
@Test
void generatedLoginPageIsReachableAndHasHeaders() {
    client.get().uri("/login")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff")
        .expectHeader().valueMatches(
            "Cache-Control", "(?i).*no-store.*");
}
```

Trong fixture dùng `formLogin(Customizer.withDefaults())`, Spring Security có thể tạo trang login mặc định. Nếu app thay `formLogin(form -> form.loginPage("/signin"))`, application phải thực sự render trang `/signin`, xử lý error page và permission đúng; **không tự suy Spring còn tạo default login page tại `/login`**.

### 13.4. Saved request và cookie có thể ảnh hưởng đích sau login

`RedirectServerAuthenticationEntryPoint` có thể hợp tác với `ServerRequestCache` để ghi nhớ tài nguyên user muốn mở; authentication success handler có thể redirect về saved request hoặc default target tùy cấu hình/phiên bản. Khi test:

```text
1. GET /account/home (anonymous)
   -> 302 Location: /login
   -> có thể tạo session/request cache cookie

2. GET /login với cookie mới nhất
   -> login form + token CSRF

3. POST /login với username/password và CSRF từ form
   -> 3xx Location: saved target hoặc default target

4. GET Location với authenticated session cookie
   -> 200 khi có quyền
```

**Không kết luận “login success phải luôn tới `/`”** nếu request cache đã lưu `/account/home`. Test phải bắt chính xác chiến lược mà dự án dùng và xác nhận session cookie mới nhất được giữ qua các requests.

## 14. Kiểm tra login failure và logout redirect

### 14.1. Đăng nhập sai password sẽ redirect tới error page

Trong fixture test-only user `alice` có password `test-only-password`:

```java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;

@Test
void invalidFormCredentialsRedirectToErrorPage() {
    client.mutateWith(csrf())
        .post().uri("/login")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(BodyInserters.fromFormData(
            "username", "alice")
            .with("password", "incorrect-password"))
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectHeader().valueMatches(
            "Location", ".*/login[?]error(?:$|&.*)");
}
```

`csrf()` là mock helper cho mục đích cô lập authentication failure. Nếu không có token CSRF, request POST `/login` có thể bị từ chối **trước khi password được kiểm tra**, khiến test không còn đo failure redirect. Test form login HTTP thật phải lấy token từ `/login` hoặc `/public/csrf` và gửi đúng WebSession cookie/form parameter.

### 14.2. Logout cũng là unsafe request và cần CSRF

```java
@Test
void logoutPostWithoutCsrfIsRejected() {
    client.mutateWith(mockUser("alice"))
        .post().uri("/logout")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void logoutPostWithMockCsrfRedirectsToLogin() {
    client.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/logout")
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectHeader().valueMatches(
            "Location", ".*/login[?]logout(?:$|&.*)");
}
```

Reactive Spring Security cung cấp logout support theo `LogoutWebFilter`. Mặc định, POST logout có CSRF hợp lệ có thể redirect về `/login?logout`. **Đừng chuyển logout thành GET state-changing** chỉ để “chữa” một POST 403.

### 14.3. Redirect logout thành công ≠ WebSession đã bị hủy

Tài liệu Reactive logout chỉ ra các trách nhiệm xóa SecurityContext/CSRF và chuyển đến login; ứng dụng **có thể cần cấu hình thêm `WebSessionServerLogoutHandler`** để invalidate toàn bộ WebSession. Một phương án cụ thể:

```java
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

var logoutHandler = new DelegatingServerLogoutHandler(
    new SecurityContextServerLogoutHandler(),
    new WebSessionServerLogoutHandler()
);

http.logout(logout -> logout.logoutHandler(logoutHandler));
```

Đây là **đoạn cấu hình thay thế/tùy chỉnh trong một Security chain**, không phải code để thêm vào class JUnit ở trên. Hãy kiểm thử sau logout rằng **request với cookie cũ không còn truy cập được tài nguyên được bảo vệ**, token CSRF cũ không được tái sử dụng trái policy, và session ID/cookie clearing đúng ứng dụng. Một 302 success page đơn lẻ không chứng minh toàn bộ post-logout invariants.

### 14.4. Không dùng `mockUser` để kết luận logout session thật

`mockUser` tạo principal cho mock exchange; nó **không** thực hiện authentication login thật hoặc lưu WebSession SecurityContext giống form login. Để kiểm tra saved request, session rotation, login success và logout invalidation, cần HTTP round-trip **cookie + CSRF + form credential thật** trong test profile.

### 14.5. Header trên 302/303 phải kiểm đúng response

```java
@Test
void loginRedirectIsStillPartOfSecurityHeaderPolicy() {
    client.get().uri("/account/home")
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectHeader().exists("Location")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");
}
```

Đây là test header viết lên **redirect response từ Security pipeline**. Nếu không thấy header, kiểm tra header writers và thứ tự commit response; nhưng nếu redirect được tạo bởi **edge proxy trước Spring**, hãy sửa/test header policy tại edge, không kỳ vọng Spring có thể ghi header lên một response nó không sở hữu.

## 15. Kiểm thử HSTS chỉ trên HTTPS

Spring Security mặc định bật hỗ trợ HSTS cho HTTPS. Header HSTS là **cam kết của hostname** rằng browser nên dùng HTTPS trong những lần truy cập sau; nó không tự làm request HTTP hiện tại đổi sang HTTPS, và browser không tin HSTS được phát qua HTTP plaintext.

### 15.1. So sánh mock request HTTP và HTTPS

Trong `HeaderAndRedirectWebFluxTest`, request HTTP:

```java
@Test
void hstsIsNotWrittenOnPlainHttpResponse() {
    client.get().uri("/public/document")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .doesNotExist("Strict-Transport-Security");
}
```

Và mock request có HTTPS scheme:

```java
@Test
void hstsIsWrittenForMockSecureRequest() {
    WebTestClient httpsClient = client.mutate()
        .baseUrl("https://local.test")
        .build();

    httpsClient.get().uri("/public/document")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().value(
            "Strict-Transport-Security",
            value -> assertTrue(value.contains("max-age=")));
}
```

Mục đích là chứng minh **header writer quyết định theo request scheme** trong mock context. Nếu mock request chưa mang scheme đúng do custom builder, kiểm tra `ServerHttpRequest.getURI()` hoặc baseUrl. Test này **không** tạo TLS handshake, không xác nhận browser tin chứng chỉ và không kiểm tra ingress/CDN đã phát header.

### 15.2. HSTS không đồng nghĩa HTTP → HTTPS redirect

| Tính năng | Kích hoạt bởi | Response/hành vi |
| --- | --- | --- |
| `Strict-Transport-Security` | Header writer trên HTTPS | Browser nhớ HTTPS policy cho hostname |
| `redirectToHttps` | Rule Security được cấu hình | HTTP request nhận 3xx Location HTTPS |
| Ingress `http→https` | Proxy/load balancer | Edge trả 301/302/307/308, app có thể không nhận HTTP |
| Browser HSTS preloaded | Danh sách preload/đã lưu | Browser có thể tự nâng cấp request trước khi gửi HTTP |

Một site có thể có HTTPS HSTS đúng nhưng HTTP endpoint **không redirect** nếu HTTP traffic bị chặn ở network/edge theo thiết kế. Ngược lại, có HTTP → HTTPS 301 nhưng response HTTPS không có HSTS. Test riêng cả hai chính sách khi yêu cầu vận hành.

### 15.3. Tùy biến HSTS cần cân nhắc toàn hostname

Spring Security Reactive hỗ trợ:

```java
import java.time.Duration;

http.headers(headers -> headers.hsts(hsts -> hsts
    .includeSubdomains(true)
    .maxAge(Duration.ofDays(365))
    .preload(true)
));
```

Đây là **mẫu thay đổi cấu hình có chủ đích**, không nên copy vào staging domain có subdomains chạy HTTP. `preload` directive **không tự đăng ký hostname vào browser preload list**; nó báo ý định, còn việc preload có yêu cầu và quy trình riêng. Cần kiểm tra toàn bộ subdomains, redirect HTTPS, TLS certificate hợp lệ trước khi áp.

## 16. `redirectToHttps`: kiểm thử 3xx Location theo scheme

Nếu yêu cầu app tự redirect HTTP sang HTTPS (không giao hoàn toàn cho ingress), `ServerHttpSecurity.redirectToHttps` cung cấp WebFlux-specific filter. Spring Security docs minh họa:

```java
http.redirectToHttps(Customizer.withDefaults());
```

Để test **redirect HTTPS riêng**, không thêm tùy tiện filter này vào fixture trước rồi khiến mọi HTTP tests đều chuyển thành 3xx. Tạo một config/test context **thay thế**.

### 16.1. Security config chuyên thử HTTPS redirect

```java
package com.example.protection.redirects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class HttpsRedirectSecurityConfig {
    @Bean
    SecurityWebFilterChain https(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth.anyExchange().permitAll())
            .redirectToHttps(Customizer.withDefaults())
            .build();
    }
}
```

**Không nạp cùng `HeaderRedirectSecurityConfig`** trong context này, trừ khi bạn chủ động thiết kế nhiều chains và order. Đây là fixture riêng để cô lập HTTPS redirect.

### 16.2. HTTP request được chuyển sang HTTPS

```java
@SpringJUnitConfig(classes = {
    RedirectWebConfig.class,
    HttpsRedirectSecurityConfig.class
})
class HttpsRedirectTest {

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .baseUrl("http://public.example.test")
            .build();
    }

    @Test
    void httpRequestGetsHttpsLocation() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value("Location", location -> {
                java.net.URI target = java.net.URI.create(location);
                assertEquals("https", target.getScheme());
                assertEquals("public.example.test", target.getHost());
                assertEquals("/public/ping", target.getPath());
            });
    }

    @Test
    void alreadyHttpsRequestIsNotRedirected() {
        WebTestClient httpsClient = client.mutate()
            .baseUrl("https://public.example.test")
            .build();

        httpsClient.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectHeader().exists("Strict-Transport-Security");
    }
}
```

Đoạn test dùng imports JUnit/`@SpringJUnitConfig`, `@Autowired ApplicationContext`, `WebTestClient` và `springSecurity()` như mục 8.3. Nó dùng **scheme trong mock request URI** để đo filter logic, không thử TLS certificate hay actual network port. Status redirect có thể thay đổi theo HTTP redirect strategy; test kiểm tra 3xx và **Location scheme/host/path** là điều kiện chính.

### 16.3. Ngăn redirect loop sau TLS termination

```text
Browser --> HTTPS public.example.com
            |
            v
       Ingress terminates TLS
            |
            +--> HTTP internal service
                      |
                      v
              Spring WebFlux sees http?
                      |
                      +--> redirect https://public.example.com
                               |
                               +--> Browser HTTPS again -> LOOP
```

Nếu application chỉ nhìn scheme `http` mà không xử lý trusted forwarded metadata đúng, `redirectToHttps` có thể liên tục redirect dù user đã ở HTTPS. Mô hình khắc phục:

- Ingress sở hữu HTTPS redirect, Spring không bật redirect trùng, **hoặc**
- Spring tin `Forwarded`/`X-Forwarded-Proto` **chỉ từ reverse proxy đáng tin**, hoặc
- `httpsRedirectWhen` matcher được thiết kế rõ theo topology nếu cần.

Spring Boot có `server.forward-headers-strategy` theo phiên bản; việc cấu hình phải dựa trên network/trust boundaries. **Đừng tin client-supplied `X-Forwarded-*` tùy ý từ Internet**; attacker có thể thao túng scheme/host nếu trust sai.

### 16.4. Tránh rò hostname/port nội bộ trong Location

Đích HTTPS phải là hostname/cổng public hợp lệ. Một redirect:

```http
Location: https://service.default.svc.cluster.local:8080/account/home
```

có thể làm browser đi sai đích và tiết lộ cấu trúc nội bộ. Đừng chỉ assert `Location` bắt đầu bằng `https://`; test `target.getHost()`, `getPort()`, path và query theo public contract. Nếu có multi-tenant domains, allowlist những hosts đã xác minh, không lấy host tùy ý từ untrusted `Host` header.

## 17. Header tùy chỉnh: CSP, Referrer-Policy và frame control

### 17.1. Referrer-Policy phải được test theo hành vi dự án

Theo tài liệu Reactive hiện hành, `Referrer-Policy` mặc định có thể là `no-referrer`. Nếu sản phẩm muốn policy khác như `same-origin` hoặc `strict-origin-when-cross-origin`, cấu hình explicit và viết test phù hợp:

```java
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy;

http.headers(headers -> headers
    .referrerPolicy(referrer -> referrer
        .policy(ReferrerPolicy.SAME_ORIGIN)
    )
);
```

Test cho **biến thể có cấu hình explicit**:

```java
@Test
void configuredReferrerPolicyIsExposedOnDocument() {
    client.get().uri("/public/document")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Referrer-Policy", "same-origin");
}
```

Đoạn test **không** thuộc fixture chính ở mục 8 trừ khi bạn đã thêm cấu hình referrer policy tương ứng; nếu không, assert theo default của version resolved hoặc bỏ assertion này.

### 17.2. Frame policy phải thống nhất với CSP

```java
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter.Mode;

http.headers(headers -> headers
    .frameOptions(frame -> frame.mode(Mode.SAMEORIGIN))
);
```

Nếu sản phẩm muốn embed vào iframe **cùng origin**, test `X-Frame-Options: SAMEORIGIN` và review CSP `frame-ancestors 'self'` tương ứng. Nếu CSP vẫn là `frame-ancestors 'none'`, browser hỗ trợ CSP sẽ **không cho iframe**, dù X-Frame-Options đã thành SAMEORIGIN. Không sửa một header mà quên header kia.

### 17.3. CSP report-only khác enforcement

Spring Security Reactive hỗ trợ:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(policy -> policy
        .policyDirectives(
            "default-src 'self'; object-src 'none'")
        .reportOnly()
    )
);
```

Khi test biến thể này, assert `Content-Security-Policy-Report-Only` **thay vì** nhầm là `Content-Security-Policy` enforcing. Report-only dùng để thu thập vi phạm/tuning policy, không thay enforcement. Với CSP reporting endpoint, kiểm tra sampling/rate-limits, privacy, retention và không để báo cáo lộ dữ liệu nhạy cảm.

### 17.4. `Permissions-Policy` và các headers hiện đại

Nếu ứng dụng cần hạn chế camera/microphone/geolocation, cấu hình và test `Permissions-Policy` theo browser compatibility hiện tại. Header này khác CSP; không suy rằng `nosniff` và `frame-ancestors` tự cấm quyền thiết bị. Cross-Origin-Opener/Embedder/Resource Policies (COOP/COEP/CORP) cũng cần lựa chọn phù hợp với frontend/third-party integrations; không bật hàng loạt mà thiếu browser tests.

### 17.5. Không vô hiệu hóa toàn bộ header writers để sửa một rule

Ví dụ nguy hiểm:

```java
// Không khuyến nghị khi chỉ muốn thay CSP/frame policy:
http.headers(headers -> headers.disable());
```

Cách này có thể loại `nosniff`, cache-control, frame protection, HSTS và các headers khác của Security chain. Thay vì tắt tất cả, hãy cấu hình **đúng spec cần sửa** và viết regression tests cho defaults còn lại.

## 18. Multi-chain: header và redirect thuộc chain được chọn

Một ứng dụng có thể có browser session chain và Bearer-only API chain. Hai loại client cần **khác authentication entry point**.

### 18.1. Cấu hình minh họa có hai chains

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        // Chỉ miễn CSRF nếu API thực sự Bearer-only, không nhận
        // browser credentials tự đính kèm: threat-model review.
        .csrf(csrf -> csrf.disable())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browser(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public/**", "/login").permitAll()
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
```

Đây là **cấu hình thay thế** `HeaderRedirectSecurityConfig` trong một context/ứng dụng khác, không đăng ký cả hai fallback chains tùy tiện. API chain cần OAuth2 Resource Server dependencies và `ReactiveJwtDecoder`/issuer config thực; chưa phải demo có thể xác thực JWT thật ngay.

### 18.2. Tests phân biệt 302 browser và 401 API

```java
@Test
void anonymousBrowserGetsLoginRedirect() {
    // Dành cho context hai chain có /account/home handler:
    client.get().uri("/account/home")
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectHeader().exists("Location");
}

@Test
void anonymousBearerApiGetsUnauthorizedNotLoginRedirect() {
    // Dành cho context hai chain, handler protected /api/profile:
    client.get().uri("/api/profile")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().doesNotExist("Location");
}
```

Đoạn này là **test template cho cấu hình hai chain**, không chạy y nguyên trong fixture chính vì nó không có `ReactiveJwtDecoder` và handler `/api/profile`. 401 có thể được resource-server entry point thêm `WWW-Authenticate: Bearer`; test HTTP thực cần kiểm JWT decoder/issuer thay vì `mockJwt()` nếu mục tiêu là token invalid/expired.

### 18.3. Header policy khác nhau theo chain nhưng HSTS có hiệu lực theo host

`headers(...)` được cấu hình trong từng `SecurityWebFilterChain`. Nếu browser chain thêm CSP nhưng API chain không, response API không nhất thiết có CSP như HTML; đây có thể là chủ đích. Tuy nhiên HSTS có **hiệu lực browser theo hostname**, dù được ghi vào response do chain nào tạo. Vì vậy:

- Test headers trên từng nhóm path/chain.
- Bảo đảm HTML frontend nhận CSP từ đúng response owner.
- Kiểm tra HSTS ở public HTTPS hostname, không chỉ một API path.
- Không bỏ toàn bộ headers ở API chain rồi giả định browser chain đã “bảo vệ hộ” tất cả responses.

### 18.4. Matcher và response owner ảnh hưởng redirect

`/api/**` không bao phủ `/api-v2/**`. Nếu API mới lọt sang browser fallback, một anonymous JSON client có thể thấy **302 /login** thay vì **401**. Đây là regression thường gặp khi tách chains: cần test route mẫu của từng nhóm API, management context (nếu có) và các rewritten paths sau ingress.

## 19. `@WebFluxTest` slice, full context và test dependency wiring

### 19.1. Slice test phải import custom Security configuration

Spring Boot `@WebFluxTest` chỉ nạp web slice; **custom `SecurityWebFilterChain`, header writers hoặc controller dependencies không được đảm bảo nạp giống full app**. Nếu test không import `HeaderRedirectSecurityConfig`, bạn có thể đang chạy default Spring Security khác production.

Ví dụ **Spring Boot 3.5 package**:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(HeaderRedirectController.class)
@Import({
    HeaderRedirectSecurityConfig.class,
    HeaderRedirectSliceTest.TestBeans.class
})
class HeaderRedirectSliceTest {

    @TestConfiguration
    static class TestBeans {
        @Bean
        OrderCounter counter() {
            return new OrderCounter();
        }
    }

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void htmlHasConfiguredCspInSlice() {
        client.get().uri("/public/document")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Content-Security-Policy");
    }
}
```

Đây là **khung slice test**: tùy Boot version và project component scan, cần kiểm tra số lượng/loại `SecurityWebFilterChain` beans thực sự được import, test user store, codecs, `@ControllerAdvice` và filter order. Nếu setup quá khác production, dùng full-context `@SpringBootTest` thay cho việc tự mock hết Security.

### 19.2. Boot 4 dùng package khác cho WebFlux test annotations

```java
// Boot 4:
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;

// Boot 3.5:
// org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest
// org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient
```

Đừng trộn hai bộ imports. Chọn test starter/version phù hợp BOM, nhất là nếu lên Spring Framework 7 hoặc Security 7. Mock WebTestClient dùng cùng principles nhưng boot annotations đã đổi package ở các dòng.

### 19.3. Full context vẫn có thể dùng mock HTTP

```java
@SpringBootTest
class FullHeaderRedirectTest {
    @Autowired ApplicationContext context;

    @Test
    void configuredPolicyAppliesInFullContext() {
        WebTestClient client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();

        client.get().uri("/public/document")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Content-Security-Policy")
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff");
    }
}
```

`@SpringBootTest` với default web environment không tự nghĩa là có server TCP. Trên đây vẫn là mock request/response chạy qua handler chain được nạp từ full Spring context; tốt cho bean wiring, chưa kiểm HTTPS public.

## 20. Live HTTP và browser E2E: điều gì mock không chứng minh?

### 20.1. `RANDOM_PORT`: kiểm tra headers và redirect qua network

Trong một Spring Boot WebFlux test application có bean Security/controller fixture tương ứng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveHeaderRedirectTest {

    @Autowired WebTestClient http;

    @Test
    void publicHtmlHasHeadersOverRealHttp() {
        http.get().uri("/public/document")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Content-Security-Policy")
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff");
    }

    @Test
    void anonymousProtectedPageRedirectsOverRealHttp() {
        http.get().uri("/account/home")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().exists("Location");
    }
}
```

`@AutoConfigureWebTestClient` import ở trên là Boot 3.5; Boot 4 dùng `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient`. Test `RANDOM_PORT` thường chạy HTTP plaintext local, vì vậy không assert HSTS hiện diện trừ khi server thật đã TLS-enabled.

### 20.2. Live login POST phải mang CSRF token **thật**

`SecurityMockServerConfigurers.csrf()`/`mockUser()` chỉ hoạt động với mock WebFlux handler builder; chúng không tự thêm principal/CSRF token qua TCP. Để test form login thực:

1. GET `/public/csrf` để nhận `CsrfEnvelope` và cookie session.
2. POST `/login` với form credentials + token field/header đúng, mang cookie session cũ.
3. Assert status 3xx, Location đúng chiến lược (default/home/saved request), và lấy cookie session **mới nhất** nếu auth strategy đổi.
4. GET `/account/home` với cookie authenticated session mới nhất, assert 200 + security headers.
5. POST `/logout` với CSRF hợp lệ của trạng thái đang login; assert redirect và state bị xóa theo logout config.
6. GET `/account/home` bằng cookie cũ phải bị từ chối/redirect, không được lộ dữ liệu.

Fragment minh họa POST login thực:

```java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;

http.post().uri("/login")
    .cookie("SESSION", sessionIdFromBootstrap)
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters
        .fromFormData("username", "alice")
        .with("password", "test-only-password")
        .with("_csrf", tokenFromBootstrap))
    .exchange()
    .expectStatus().is3xxRedirection()
    .expectHeader().exists("Location");
```

`sessionIdFromBootstrap` và `tokenFromBootstrap` là dữ liệu thực từ GET cùng HTTP client; không hard-code. Với custom CSRF parameter name hoặc XOR handler, lấy đúng `parameterName`/exposed token và giữ cookie. Chỉ dùng **test credentials** và không ghi chúng/token vào shell history, CI log, screenshots.

### 20.3. Test TLS/public host bằng curl

Trên staging HTTPS:

```bash
curl -sSI 'https://app.example.com/public/document'
```

Kiểm tra `Strict-Transport-Security`, `Content-Security-Policy` (nếu owner HTML này có), `X-Frame-Options`, `X-Content-Type-Options` và cache headers.

Kiểm tra HTTPS redirect **không tự follow**:

```bash
curl -sSI 'http://app.example.com/account/home'
```

Kiểm tra status 3xx + `Location` có scheme/host/path đúng. `-I` gửi HEAD nên behavior có thể khác GET/POST; nếu policy phụ thuộc method, dùng:

```bash
curl -sS -D - -o /dev/null 'http://app.example.com/account/home'
```

Chỉ ở bước riêng có thể dùng `curl -L` để xem toàn redirect chain. Nếu dùng `-L` ngay từ đầu, dễ chỉ thấy response cuối và bỏ qua headers tại hop 301/302 trung gian.

### 20.4. Dùng browser để kiểm CSP và HSTS có hiệu lực

`WebTestClient` không thực thi browser Content Security Policy, sandbox iframe, HSTS preload, mixed-content upgrade hoặc cross-site cookie policies. Kiểm tra qua browser automation/DevTools trên **public HTTPS origin**:

- CSP có chặn inline script/external script không được phép không?
- `frame-ancestors` và `X-Frame-Options` có ngăn framing đúng mục tiêu?
- HSTS được browser nhận trên hostname với certificate tin cậy?
- Cookie `Secure/SameSite/HttpOnly` có bị browser từ chối hoặc gửi sai domain?
- Redirect chain có giữ đúng scheme/host/path, không lặp, không downgrade?
- SPA fetch có bị `connect-src`/CORS chặn, khiến frontend báo lỗi dù API 200?

Browser E2E phải lấy dữ liệu test đã redacted; không công khai session cookie, auth token, raw CSRF token hoặc thông tin tài khoản thật trong artifacts.

### 20.5. Test ở edge không được suy từ app response

```text
Browser
  |
  +-- HTTP :80 --> CDN/Ingress 301 Location: https://...
  |                  (Response do edge sở hữu)
  |
  +-- HTTPS :443 --> CDN (serve index.html + CSP/HSTS?)
                       |
                       +--> WebFlux API (JSON, auth, CSP?)
```

Nếu HTTP redirect được tạo hoàn toàn bởi edge, Spring Security **không bao giờ chạy** cho request HTTP đó. Nếu HTML được CDN phục vụ, Security headers của WebFlux JSON API không bảo vệ HTML. Test cần phân chia **CSP owner**, **HSTS owner**, **redirect owner** và **cookie owner** cụ thể thay vì assert mọi headers trên một URI ngẫu nhiên.

## 21. Runbook chẩn đoán lỗi headers và redirects WebFlux

### Lỗi A — Anonymous `GET /account/home` trả 401 thay vì 302

**Có thể do:** chain đang bật HTTP Basic/Bearer entry point, Content Negotiation/`Accept` chọn entry point khác, route thuộc API chain, hoặc formLogin chưa được cấu hình. Một JSON API **có thể đúng** khi trả 401; một browser form-login chain **thường cần** 302.

**Chẩn đoán:** kiểm tra `securityMatcher`/`@Order`, `formLogin(...)`/`httpBasic(...)`/`oauth2ResourceServer(...)` và response `WWW-Authenticate`. Dùng test cùng request với `Accept: text/html` để cô lập browser case, nhưng đừng mặc định thêm redirect cho mọi API client.

### Lỗi B — Redirect login trả 302 nhưng `Location` sai

**Có thể do:** custom `loginPage` đã chuyển `/login` sang `/signin`, context path/prefix rewrite khác nhau, saved request được tạo hoặc redirect strategy ghi absolute URL thay vì relative. Test phải kiểm Location theo **policy đã chọn**, không dựa hoàn toàn vào browser cuối cùng tới một trang login nào đó.

### Lỗi C — Login redirect thành công nhưng tài nguyên vẫn 401/302

**Có thể do:** cookie session `SESSION` không được giữ, SecurityContext không được lưu/nạp, session ID đổi sau login, cookie `Path/SameSite/Secure` sai hoặc proxy rewrite đường dẫn. Một HTTP status login success 3xx **không chứng minh** user đã authenticated trong request tiếp theo.

**Cách kiểm tra:** theo dõi `Set-Cookie` của các bước, dùng cookie mới nhất và GET protected route, assert 200. Test riêng WebSession store và logout/invalidation.

### Lỗi D — POST `/login` trả 403 thay vì redirect `/login?error`

**Có thể do:** CSRF token thiếu/sai hoặc client không trả session cookie được dùng khi tạo token, nên request bị CsrfWebFilter từ chối **trước authentication failure handler**.

**Cách sửa:** trong mock test dùng `mutateWith(csrf())` nếu đang kiểm credential failure; trong live HTTP test lấy token qua form/`GET /public/csrf`, gửi đúng cookie và form field. Không disable CSRF của login để sửa test.

### Lỗi E — Logout redirect 302 nhưng session vẫn dùng được

**Có thể do:** logout chỉ clear SecurityContext/CSRF token theo config nhưng chưa invalidate toàn WebSession, client còn giữ cookie/remember-me, hoặc test dùng `mockUser` nên không có session auth thật để xóa.

**Cách kiểm tra:** chạy authentication thật, POST logout có CSRF, sau đó GET protected resource bằng cookie cũ và assert bị chặn; nếu yêu cầu invalidation toàn session, cấu hình `WebSessionServerLogoutHandler` và kiểm tra store/cookie.

### Lỗi F — Header `X-Content-Type-Options` không xuất hiện trên 302

**Có thể do:** redirect được tạo tại gateway trước khi request tới WebFlux; header writers bị disable trên selected chain; response custom filter commit sớm/không chạy như dự kiến. Phân biệt **owner** của redirect và đối chiếu header trên 200 trong cùng chain.

**Cách kiểm tra:** test cả redirect do controller **và** redirect do Security, sau đó test public edge. Đừng yêu cầu Spring ghi header lên response của CDN.

### Lỗi G — Không thấy `Strict-Transport-Security` trên HTTP local

**Giải thích:** HSTS không được gửi trên plain HTTP theo chuẩn. Một mock/local `http://localhost:...` thiếu HSTS là **bình thường**.

**Cách kiểm tra:** dùng mock request HTTPS scheme để kiểm writer logic và public HTTPS URL với certificate hợp lệ để kiểm hành vi deployment. Không thêm HSTS vào HTTP plaintext để làm test xanh.

### Lỗi H — HTTPS public bị redirect lặp vô hạn

**Có thể do:** TLS termination ở ingress nhưng backend vẫn nghĩ request là HTTP, cả ingress và Spring cùng redirect hoặc trusted forwarded scheme bị xử lý sai.

**Cách kiểm tra:** ghi lại từng `Location`/status của redirect chain (không tự follow ban đầu), xác nhận `Forwarded`/`X-Forwarded-Proto` từ **trusted proxy** và trách nhiệm redirect của mỗi lớp. Không bật trust forwarded headers từ Internet tùy ý.

### Lỗi I — `Location` chứa `service:8080` hoặc host nội bộ

**Có thể do:** app xây absolute URL từ request host/scheme nội bộ, reverse proxy chưa truyền/khôi phục public host, hoặc redirect strategy dùng absolute URL từ unsafe input.

**Cách kiểm tra:** parse `Location` thành `URI`, assert scheme=https, host public, port/path/query hợp lệ; không chỉ assert 3xx.

### Lỗi J — `Content-Security-Policy` không xuất hiện trên trang SPA

**Có thể do:** CSP chỉ được cấu hình trong Spring WebFlux API, nhưng `index.html` do CDN/Nginx tạo; hoặc Security chain khác không cấu hình CSP.

**Cách sửa:** xác định owner của **HTML document**, cấu hình CSP ở owner đó và test qua public URL. JSON API có CSP không tự bảo vệ HTML của origin khác.

### Lỗi K — CSP có nhưng script hoặc fetch bị browser chặn

**Có thể do:** `script-src` thiếu nguồn script hợp lệ/nonce/hash, `connect-src` không cho API/WebSocket, inline script không được phép, hoặc resource được tải từ external host.

**Cách kiểm tra:** browser DevTools Console/CSP reports, tập trung đúng directive; điều chỉnh allowlist tối thiểu. Không chuyển `default-src *; script-src * 'unsafe-inline'` chỉ để hết lỗi.

### Lỗi L — `X-Frame-Options: SAMEORIGIN` nhưng iframe vẫn bị chặn

**Có thể do:** CSP `frame-ancestors 'none'` đang áp dụng hoặc iframe dùng một origin khác. Browser thường ưu tiên CSP `frame-ancestors` khi có. Kiểm tra **cả hai policies** trên HTML document và iframe origin.

### Lỗi M — Security cache-control bị thay bằng public

**Có thể do:** controller/CDN chủ động đặt `Cache-Control: public`, default Security header writer không override header có sẵn; hoặc headers được CDN sửa sau app.

**Cách kiểm tra:** xác định URL có chứa thông tin cá nhân hoặc CSRF token không. Với private content, `public` là regression; với hashed public assets, đó có thể là chính sách caching đúng.

### Lỗi N — CSP test xanh ở 200 nhưng login 302 vẫn thiếu header

**Có thể do:** test chỉ gọi controller HTML, chưa gọi Security authentication entry point; filter ordering/selected chain khác; hoặc 302 do proxy. Bổ sung test trực tiếp **anonymous protected GET** và assert response 302/Location/headers.

### Lỗi O — Post/Redirect/Get tạo đơn hai lần

**Có thể do:** client gửi hai POST, retry do timeout/redirect, user double-click, hoặc ứng dụng chọn 307/308 giữ method rồi chuyển POST sang endpoint khác. **303 không tự bảo đảm idempotency**.

**Cách kiểm tra:** test counter/DB unique constraints/idempotency key, mô phỏng retry và xác minh business state. Chọn 303 cho PRG đúng nghĩa, không chỉ thay status để che double-submit.

### Lỗi P — POST có `csrf()` pass nhưng HTTP real request 403

**Giải thích:** mock helper đáp ứng CSRF condition trong test builder nhưng không bootstrap WebSession/repository/cookie thật qua TCP.

**Cách sửa:** GET `/public/csrf`, giữ `SESSION` cookie và exposed token, POST actual header/form trong live test. Không coi redirect test mock là bằng chứng CSRF toàn hệ thống.

### Lỗi Q — Không nhìn thấy security headers khi thử bare OPTIONS

**Có thể do:** `CorsWebFilter` xử lý preflight trước Spring Security hoặc OPTIONS bị ingress xử lý; hoặc request không đúng preflight vì thiếu `Origin`/`Access-Control-Request-Method`.

**Cách kiểm tra:** kiểm tra CORS response semantics riêng; **không bắt buộc** preflight response sở hữu cùng header writers như HTML/JSON từ Security chain.

### Lỗi R — Browser bị CORS khi API redirect đến login

**Có thể do:** SPA fetch cross-origin `/api/**` anonymous nhận 302 đến login page, browser theo redirect và gặp CORS/HTML thay JSON; API nên có **401/WWW-Authenticate** để client biết cần login, thay vì browser redirect xuyên origin.

**Cách sửa:** tách browser form-login chain và API Bearer/JSON chain; test `/api/**` anonymous 401, `/account/**` anonymous 302, không dùng một catch-all `formLogin` cho mọi API path khi behavior mong muốn khác.

### Lỗi S — Thêm CORS hoặc CSRF config làm mất HSTS

**Có thể do:** khi chỉnh chain đã gọi `headers(headers -> headers.disable())`, chuyển request sang chain khác hoặc header writer không còn được áp dụng. Kiểm tra regression matrix trên từng chain/HTTPS.

### Lỗi T — `@WebFluxTest` xanh, public HTTPS staging đỏ

**Có thể do:** test slice không nạp đúng Security chain, hostname/proxy policies khác, CDN tạo HTML/redirect, headers bị override hoặc cookie scheme mismatch. Test full-context `RANDOM_PORT` và public endpoint để định vị tầng.

### Lỗi U — Browser vẫn dùng redirect cũ dù server đã đổi

**Có thể do:** 301/308 hoặc CDN cache được giữ, HSTS được browser nhớ, service worker intercept navigation, hoặc cache của redirect response. Kiểm tra profile sạch và cache headers, không vội đổi Security rule liên tục.

### Lỗi V — Open redirect qua `next`/`returnUrl`

**Có thể do:** server echo input vào `Location`, chấp nhận URL bắt đầu `//`, mixed-encoded slash/backslash hoặc dựa vào untrusted Host/X-Forwarded-Host.

**Cách sửa:** dùng map keys → fixed internal path hoặc server-side allowlist URI sau normalization; test malicious inputs và assert Location không rời origin/trust boundary.

## 22. Ma trận hồi quy headers + redirect

| ID | Request/kịch bản | Kỳ vọng chính |
| --- | --- | --- |
| H01 | GET `/public/document` | 200, `nosniff` |
| H02 | HTML qua Security chain | `X-Frame-Options: DENY` |
| H03 | HTML qua configured chain | CSP có `default-src`/`frame-ancestors` |
| H04 | HTML qua HTTP | Không có HSTS |
| H05 | HTML mock HTTPS | Có HSTS với `max-age` |
| H06 | GET `/public/cacheable` | Cache public 3600s, `nosniff` vẫn có |
| H07 | GET `/public/csrf` | `no-store`, token envelope/session theo repo |
| H08 | GET `/public/go` | 302, Location `/public/landing` |
| H09 | GET `/public/keep-method` | 307, Location đúng |
| H10 | GET `/public/choose?next=landing` | 303, Location nội bộ |
| H11 | `next=https://attacker.example` | Không open redirect |
| H12 | `next=//attacker.example` | Không open redirect |
| H13 | GET `/account/home` anonymous | 3xx về `/login` |
| H14 | GET `/account/home` mock authenticated | 200, không redirect |
| H15 | GET `/login` | Trang login, cache/header policy đúng |
| H16 | POST `/login` sai password + CSRF | Redirect error, không phải CSRF 403 |
| H17 | POST `/login` thiếu CSRF | Từ chối (theo CSRF policy) |
| H18 | POST `/logout` thiếu CSRF | 403 |
| H19 | POST `/logout` có CSRF | Redirect logout success |
| H20 | Cookie/session cũ sau logout thật | Không được phép đọc private content |
| H21 | POST `/account/orders` thiếu CSRF | 403, counter 0 |
| H22 | POST `/account/orders` auth + CSRF | 303, Location `/account/home`, counter 1 |
| H23 | GET sau 303 | 200, không tạo thêm order |
| H24 | Security-created 302 | Header `nosniff` theo chain policy |
| H25 | HTTP request với `redirectToHttps` | 3xx, Location HTTPS public host |
| H26 | HTTPS request với `redirectToHttps` | Không loop, route xử lý bình thường |
| H27 | Form-login browser chain anonymous | 302 |
| H28 | Bearer-only API chain anonymous | 401, không login Location |
| H29 | Browser/CSP `frame-ancestors` | Chống iframe theo policy |
| H30 | SPA CSP `connect-src` | Cho phép/chặn API theo policy |
| H31 | Public HTTPS HSTS qua ingress | HSTS trên hostname/chứng chỉ tin cậy |
| H32 | HTTP → HTTPS ở proxy | Status/Location/canonical host đúng |
| H33 | CDN HTML và JSON WebFlux | CSP/HSTS từ đúng response owner |
| H34 | `@WebFluxTest` slice | Security config có nạp đúng không |
| H35 | `@SpringBootTest(RANDOM_PORT)` | Live HTTP headers/redirect |
| H36 | Saved-request login flow | Không open redirect, cookie/session đúng |
| H37 | Browser cookie `Secure/SameSite/HttpOnly` | Đúng với HTTPS và login/logout |
| H38 | Origin không tin cậy/CORS | Không cấp permission trái policy |
| H39 | Response từ HTTP firewall/edge | Xác minh status/headers tại đúng owner |
| H40 | Staging canary/rolling deployment | Không redirect loop, headers ổn định |

### 22.1. Đừng bỏ negative controls

Một bộ test chỉ kiểm tra 200 HTML có CSP và một 302 có Location không đủ. Ít nhất cần:

1. **Anonymous browser redirect** đúng `/login`, authenticated browser không redirect.
2. **API 401** khi thiếu Bearer trên chain riêng, không redirect đến HTML login.
3. **POST không CSRF** bị chặn và **POST có CSRF** trả 303 khi hợp lệ.
4. **Location allowlist** chống external URL/scheme-relative URLs.
5. **HSTS HTTPS-only** và redirect HTTPS ở đúng deployment layer.
6. **CSP on HTML document** và no-store cho nội dung nhạy cảm.
7. **Logout/session old-cookie replay** bị từ chối bằng auth flow thật.
8. **Public HTTPS redirect chain** có host/scheme/cookie headers không bị proxy làm sai.

### 22.2. Điều kiện nên chặn phát hành

Đánh dấu regression bảo mật nghiêm trọng nếu redirect đưa user đến attacker-controlled domain từ tham số không tin cậy, Location HTTPS chứa host nội bộ, browser POST thiếu CSRF vẫn thực thi nghiệp vụ, logout không làm mất quyền truy cập của session cũ trái contract, hoặc CSP/HSTS cần thiết bị mất trên **HTML/public HTTPS response owner**. Đừng “fix test” bằng cách tắt header writers hoặc nới authorization toàn ứng dụng.

## 23. Bài tập thực hành

### Bài 1 — Assert headers trên HTML công khai

Tạo `GET /public/document` trả HTML và cấu hình `SecurityWebFilterChain` có CSP explicit. Viết `WebTestClient` test `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Cache-Control` chống cache và CSP `default-src`/`frame-ancestors`. Sau đó chủ động disable header writers trên **test variant riêng** và kiểm tra regression; giải thích vì sao không nên dùng `headers.disable()` làm giải pháp production.

### Bài 2 — Static asset và cache-control

Viết `GET /public/cacheable` trả `Cache-Control: public, max-age=3600`. Xác nhận Security default writer **không xóa** cache policy đã đặt, nhưng `nosniff` vẫn có. So sánh với private account response `no-store`. Vì sao bắt mọi response `no-store` có thể phá hiệu năng static assets?

### Bài 3 — Controller 302 và follow redirect

Viết GET `/public/go` → 302 `Location: /public/landing`. Test status + exact Location + headers trên response 302. Sau đó GET destination độc lập và assert 200. Vì sao một test tự follow redirect chỉ assert status cuối 200 có thể che sai Location ở hop đầu?

### Bài 4 — POST/Redirect/GET 303 và CSRF

Tạo POST `/account/orders` có side effect counter. Anonymous hoặc authenticated thiếu CSRF bị chặn; authenticated + CSRF mock hợp lệ nhận 303 sang `/account/home`, counter tăng 1. GET trang đích không làm counter tăng nữa. Giải thích sự khác biệt 303 và 307, và vì sao 303 **không** thay idempotency key khi có hai POST.

### Bài 5 — Anonymous browser redirect khác API 401

Cấu hình hai `SecurityWebFilterChain`: browser form login fallback và Bearer-only API hẹp `/api/**`. Viết test anonymous `GET /account/home` nhận 302 `/login`; anonymous `GET /api/profile` nhận 401 không có `Location` login. Bổ sung test `/api-v2/profile` để phát hiện matcher chưa bao phủ route mới.

### Bài 6 — Form login failure redirect

Gửi POST `/login` với username đúng, password sai và CSRF mock condition hợp lệ, kiểm Location `/login?error`. Lặp lại nhưng bỏ CSRF, giải thích tại sao response 403 không phải bằng chứng authentication failure handler sai. Sau đó thay bằng HTTP live GET token/cookie và POST form thật.

### Bài 7 — Logout và WebSession invalidation

Đăng nhập bằng HTTP form thật trong test profile, lấy session cookie. POST logout với CSRF hợp lệ, assert 3xx, rồi GET private resource bằng cookie cũ và assert không được phép. Thêm `WebSessionServerLogoutHandler` nếu policy yêu cầu invalidate toàn session, test session store không còn attributes/authentication. Vì sao `mockUser()` không đủ cho phần kiểm chứng này?

### Bài 8 — HTTP và HTTPS HSTS

Trong mock context, GET `http://local.test/public/document` không có HSTS; GET `https://local.test/public/document` có HSTS. Sau đó gọi public staging HTTPS bằng curl/browser, kiểm HSTS thực và certificate. Nếu mock HTTPS xanh nhưng browser không có HSTS, những lớp nào có thể là nguyên nhân?

### Bài 9 — `redirectToHttps` và redirect loop

Dùng fixture `HttpsRedirectSecurityConfig`. Test HTTP response 3xx với `Location` scheme=https, hostname public và path giữ nguyên; test HTTPS response 200 không redirect. Triển khai sau TLS-terminating ingress và cố tình cấu hình forwarded headers sai trên staging để phân tích redirect loop. Không mở quyền tin `X-Forwarded-*` cho mọi client.

### Bài 10 — Open redirect và normalization

Cho endpoint `/public/choose?next=...` và map key → fixed path. Thử input `https://attacker.example`, `//attacker.example`, encoded slash, backslash, `javascript:`, hostname nội bộ và key hợp lệ. Assert Location **không** rời allowlist, không chứa scheme nguy hiểm. Giải thích vì sao kiểm `startsWith("/")` đơn lẻ có thể vẫn chấp nhận `//attacker.example`.

### Bài 11 — CSP và iframe

Cấu hình `frame-ancestors 'none'` và `X-Frame-Options: DENY`, dùng browser staging để thử render HTML trong iframe từ origin khác. Chuyển cả hai chính sách thành một phương án `SAMEORIGIN`/`frame-ancestors 'self'` được review rồi thử iframe cùng/khác origin. Vì sao chỉ sửa X-Frame-Options có thể không tạo hiệu ứng mong muốn?

### Bài 12 — CSP `connect-src` và redirect login API

SPA phục vụ ở origin A gọi WebFlux API origin B. Khi anonymous API trả 302 `/login`, browser fetch có thể báo CORS hoặc nhận HTML thay JSON. Tách API trả 401 phù hợp, cập nhật CSP `connect-src`/CORS allowlist nếu cần, rồi test qua browser. Không mở CORS `*` với credentialed sessions.

### Bài 13 — Owner của header sau CDN/Ingress

Lập sơ đồ request path: CDN phục vụ `/index.html`, ingress redirect HTTP → HTTPS, WebFlux phục vụ `/api/**`. Đối với mỗi response 200/301/302/401, ghi owner và expected `CSP/HSTS/nosniff/Location`. Thử HTTP public path, HTTPS HTML và API bằng curl **không tự follow redirect**, sau đó browser E2E.

### Bài 14 — Saved request qua đăng nhập

Gọi anonymous `GET /account/home`, lưu cookie từ response redirect nếu có, GET login page lấy CSRF, POST credentials+token, kiểm Location theo saved request strategy, GET đích bằng authenticated cookie. Tại sao không thể assert login success luôn redirect tới `/` trên mọi phiên bản/cấu hình?

### Bài 15 — Audit rollout Spring Security/Boot

Sau khi nâng dependency theo BOM, chạy các tests H01–H40 ở mock context, HTTP live và HTTPS staging. Kiểm tra sự thay đổi default headers (`Referrer-Policy`, cache headers), Location format, login/logout redirect, HSTS, CSP và cookie. Giải thích vì sao không sửa expected test value mà không phân tích lý do behavior đổi.

## 24. Checklist review khi kiểm tra header và redirect WebFlux

- [ ] Application là **WebFlux Reactive**; code dùng `ServerHttpSecurity`/`SecurityWebFilterChain` và `WebTestClient`, không lẫn Servlet `HttpSecurity`/`MockMvc`.
- [ ] Dependencies Framework/Security/Boot/test nằm cùng dòng BOM, version-specific APIs đã đối chiếu.
- [ ] Mock test dùng `bindToApplicationContext(...).apply(springSecurity())` với chain/header policy đúng.
- [ ] Nếu dùng `@WebFluxTest` slice, custom Security config và controller dependencies được import rõ; có full-context coverage.
- [ ] Có test HTTP 200 HTML trả `X-Content-Type-Options: nosniff` và `X-Frame-Options` theo policy.
- [ ] Có test `Cache-Control`/`Pragma`/`Expires` cho private content; không cache công khai dữ liệu cá nhân/CSRF.
- [ ] Explicit public cache policy cho hashed static assets được test riêng, không xóa `nosniff`.
- [ ] CSP được **chủ động cấu hình**, test directives quan trọng trên **HTML response owner** chứ không chỉ JSON API.
- [ ] CSP `Content-Security-Policy-Report-Only` không bị hiểu là enforcing CSP.
- [ ] CSP `frame-ancestors` và `X-Frame-Options` không mâu thuẫn theo yêu cầu iframe.
- [ ] `Referrer-Policy`/`Permissions-Policy` được assert theo version và configuration, không suy từ Servlet defaults.
- [ ] Không dùng `headers.disable()` để sửa một directive nhỏ.
- [ ] Response controller 302/303/307 được test **status + Location + security headers**.
- [ ] 303 được dùng đúng cho Post/Redirect/Get khi phù hợp, không nhầm là đảm bảo idempotency.
- [ ] Không chỉ assert status cuối sau auto-follow; kiểm từng hop redirect trung gian.
- [ ] `Location` được validate/normalize, chống external/scheme-relative/encoded open redirects.
- [ ] `Location` không lộ service hostname/port nội bộ hoặc chuyển HTTPS xuống HTTP trái chính sách.
- [ ] Anonymous browser chain đúng redirect `/login`; authenticated request không bị redirect sai.
- [ ] Bearer/JSON API anonymous trả 401 theo policy, không tự redirect đến HTML login page.
- [ ] Form login sai password + CSRF valid được kiểm authentication failure redirect.
- [ ] POST login/logout thiếu CSRF bị từ chối; không disable CSRF để làm flow pass.
- [ ] Login success/saved request strategy, session cookie mới nhất và protected GET sau login được test qua auth thật.
- [ ] Logout redirect được kiểm riêng với việc xóa SecurityContext, CSRF token và invalidation WebSession khi cần.
- [ ] HSTS **chỉ** được assert trên HTTPS responses; mock scheme khác TLS thật.
- [ ] `redirectToHttps` hoặc redirect tại ingress có owner và policy rõ, không gây redirect loop.
- [ ] Nếu `includeSubDomains`/`preload` được bật, toàn bộ host/subdomain/TLS prerequisites được review.
- [ ] Trusted forwarded headers cấu hình đúng topology, không tin untrusted `Host`/`X-Forwarded-*`.
- [ ] CSP/HSTS được kiểm trên public HTML hostname; CDN/Ingress và API owner không bị nhầm.
- [ ] Redirect 301/308 caching, browser HSTS memory và service worker được xét trong debugging.
- [ ] Browser E2E kiểm CSP violation, iframe, cookie `SameSite/Secure/HttpOnly`, CORS và full redirect chain.
- [ ] Response preflight/HTTP firewall/edge được test tại đúng owner; không bắt mọi security headers trên response Spring không sở hữu.
- [ ] Multi-chain có route regression: browser 302, API 401, fallback và URL rewrite.
- [ ] HTTP live test dùng credentials, CSRF token và cookies thực; mock `csrf()`/`mockUser()` không thay thế request TCP.
- [ ] Side effects không xảy ra khi request CSRF/authorization bị từ chối; domain idempotency được test nếu cần.
- [ ] Không ghi session ID, password, JWT hoặc raw CSRF token vào tests/logs/screenshots/redirect query.

## 25. Nguồn chính thức và đọc thêm

1. [Spring Security — Reactive HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — default headers, cache-control, nosniff, X-Frame-Options, HSTS, CSP, Referrer-Policy và header customizations.
2. [Spring Security 6.5 — Reactive HTTP Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html) và [Spring Security 7.0 — Reactive Headers](https://docs.spring.io/spring-security/reference/7.0/reactive/exploits/headers.html) — đối chiếu version đang dùng thay vì dựa trên Servlet examples.
3. [Spring Security — Reactive HTTPS Redirect / HTTP](https://docs.spring.io/spring-security/reference/reactive/exploits/http.html) — `redirectToHttps`, `httpsRedirectWhen`, HSTS và proxy considerations.
4. [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html) — mục đích và default HTTP security headers.
5. [Spring Security — Getting Started with WebFlux](https://docs.spring.io/spring-security/reference/reactive/getting-started.html) — generated login page, anonymous browser redirect và Spring Boot security flow.
6. [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html) — `LogoutWebFilter`, CSRF/security-context clearing, `WebSessionServerLogoutHandler`.
7. [Spring Security API — ServerHttpSecurity.FormLoginSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html) — `loginPage`, authentication entry point, success/failure handlers.
8. [Spring Security API — RedirectServerAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationEntryPoint.html) — Location, redirect strategy và request cache.
9. [Spring Security API — RedirectServerLogoutSuccessHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/RedirectServerLogoutSuccessHandler.html) — logout redirect URL và custom success handler.
10. [Spring Security API — HttpHeaderWriterWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/header/HttpHeaderWriterWebFilter.html) — Reactive response security header writers.
11. [Spring Security API — StrictTransportSecurityServerHttpHeadersWriter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/header/StrictTransportSecurityServerHttpHeadersWriter.html) — secure scheme, max-age/includeSubDomains.
12. [Spring Security API — ContentSecurityPolicyServerHttpHeadersWriter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/header/ContentSecurityPolicyServerHttpHeadersWriter.html) — CSP directives/report-only.
13. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, chain selection/order.
14. [Spring Security — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) và [Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — mock security support và giới hạn `csrf()` mutator.
15. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — `expectStatus`, `expectHeader`, mock context vs real HTTP.
16. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`, `@SpringBootTest`, `RANDOM_PORT` theo phiên bản.
17. [MDN — HTTP Redirections](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Redirections) — các mã 3xx, `Location` và method semantics.
18. [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security) — HSTS HTTPS-only, subdomains, preload.
19. [MDN — Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy) — browser CSP enforcement/directives và report-only.
20. [OWASP — HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) và [Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html) — chọn headers đúng threat model và chống open redirect.

**Tự đánh giá:** Vì sao test một 302 chỉ assert status là chưa đủ? Headers nào Spring Security WebFlux thêm mặc định, headers nào phải chủ động cấu hình? Vì sao HSTS không xuất hiện trên HTTP mock response? Sự khác biệt giữa HTTP → HTTPS redirect và HSTS browser policy là gì? Khi nào `/account/home` anonymous nên trả 302, nhưng `/api/profile` nên trả 401? Vì sao login failure POST có thể bị CSRF chặn trước khi authentication handler chạy? Vì sao một logout 302 không chứng minh WebSession đã bị hủy? Khi nào 303 thích hợp hơn 307? Một `Location: //attacker.example` có rủi ro gì? Nếu HTML nằm ở CDN còn JSON ở WebFlux, bạn sẽ đặt và test CSP/HSTS ở đâu? Cuối cùng, bộ test nào cần chạy thêm sau mock WebTestClient để xác minh TLS, cookies, redirect loops và chính sách browser thật?
