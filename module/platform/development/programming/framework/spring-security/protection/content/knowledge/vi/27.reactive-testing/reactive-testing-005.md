# Kiểm tra CSRF repository dùng WebSession hoặc cookie

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Mục tiêu:** Kiểm tra nơi Spring Security WebFlux lưu và đọc *expected CSRF token*: `WebSessionServerCsrfTokenRepository` (mặc định) hoặc `CookieServerCsrfTokenRepository` (khi chọn cookie cho SPA). Bài sử dụng `WebTestClient` để xác minh token được cấp, ghi lại, nạp lại, so khớp, bị từ chối khi thiếu/sai và xử lý đúng vòng đời authentication.  
> **Phạm vi:** Spring Security 6.5 và 7.x, Spring WebFlux, JUnit 5, Spring Test, Spring Boot 3.5/4.x. Chọn API theo phiên bản thực tế đã resolve; ví dụ dùng Java 17+ và Lambda DSL.

## 1. Bài toán: test POST được 200 chưa chứng minh repository đúng

Một SPA quản lý đơn hàng gửi `POST /orders`. Trong một kiểm thử đơn giản, lập trình viên viết:

```java
client.mutateWith(mockUser("alice").roles("USER"))
    .mutateWith(csrf())
    .post().uri("/orders")
    .exchange()
    .expectStatus().isOk();
```

Test này hữu ích: request thử nghiệm được coi là đáp ứng điều kiện CSRF và tiếp tục đến authorization/handler. **Nhưng nó không chứng minh** server đã tạo token, lưu token trong WebSession/cookie hoặc đọc lại token từ request tiếp theo. `SecurityMockServerConfigurers.csrf()` là một **test mutator** dành cho mock `WebTestClient`; nó không phải browser tự thực hiện token round-trip.

Hai tình huống production dễ xảy ra dù test trên xanh:

- App dự kiến token lưu trong **WebSession**, nhưng client không gửi `SESSION` cookie của request cấp token. Server nạp session khác, expected token khác và POST bị 403.
- App chuyển sang **cookie repository**, frontend đọc `XSRF-TOKEN` rồi gửi raw token trong `X-XSRF-TOKEN`; trong khi request handler đang chờ **XOR-masked token**. Cookie và header trông giống nhau nhưng server vẫn trả 403.

Do vậy, chủ đề này không chỉ là chọn một bean repository. Mục đích là **chứng minh hợp đồng lưu–nạp–so khớp CSRF token** trên các request thực tế và hiểu giới hạn của từng cách lưu.

### 1.1. Bạn sẽ học được gì?

1. Phân biệt `ServerCsrfTokenRepository`, `CsrfWebFilter`, `ServerCsrfTokenRequestHandler` và browser session cookie.
2. Chọn đúng repository `WebSessionServerCsrfTokenRepository` hoặc `CookieServerCsrfTokenRepository` cho từng kiến trúc.
3. Viết fixture Spring Security Reactive và endpoint `GET /csrf` để **consume** token do framework cung cấp.
4. Viết tests WebSession: thiếu session, cùng session đúng token, token sai, token từ session khác, token sau logout.
5. Viết tests cookie: `Set-Cookie: XSRF-TOKEN`, `HttpOnly`/`Secure`/`SameSite`/`Path`, cookie thiếu/sai, header thiếu/sai/đúng.
6. Phân biệt token **raw** với token **XOR-masked**, giữ BREACH protection khi thiết kế SPA.
7. Kiểm thử repository độc lập ở cấp `MockServerWebExchange` và tích hợp qua `WebTestClient`.
8. Phân biệt CORS, authentication, authorization, session, headers/CSP/HSTS và HTTP firewall khi debug 400/401/403.
9. Tạo ma trận regression tests và tiêu chí release cho browser session, cookie SPA và nhiều security chains.

## 2. Repository giữ vai trò gì trong CSRF protection?

`ServerCsrfTokenRepository` định nghĩa ba thao tác Reactive:

```java
Mono<CsrfToken> generateToken(ServerWebExchange exchange);
Mono<Void> saveToken(ServerWebExchange exchange, CsrfToken token);
Mono<CsrfToken> loadToken(ServerWebExchange exchange);
```

`saveToken(exchange, null)` có ngữ nghĩa **xóa token** khỏi repository. Mỗi implementation chọn cách liên kết expected token với `ServerWebExchange`: WebSession hoặc cookie trong request/response.

```text
                GET /csrf (safe request)
                         |
                         v
                   CsrfWebFilter
                         |
               ServerCsrfTokenRepository
                /                     \
               /                       \
     WebSession repository      Cookie repository
        (default)                (opt-in)
               |                       |
     WebSession attributes        Set-Cookie: XSRF-TOKEN=R
      Cookie: SESSION=S           Request Cookie: XSRF-TOKEN=R
               |                       |
               +----------+------------+
                          |
                ServerCsrfTokenRequestHandler
                 expose Mono<CsrfToken> và
                 resolve token gửi lại
                          |
               POST /orders + CSRF header
                          |
                 CsrfWebFilter so sánh
                      /       \
                 đúng         thiếu/sai
                   |               |
            authorization        thường 403
                /handler
```

**Phân biệt ba giá trị:**

- **Expected token**: giá trị repository lưu/nạp, ví dụ raw token `R`.
- **Exposed token**: giá trị handler đưa ra cho view/`GET /csrf`, có thể đã XOR-mask thành `M` để chống BREACH.
- **Actual token**: giá trị client gửi trong header/form; handler giải mã (nếu cần) trước khi so với expected token.

Cookie ở đây không tự động là actual token. Với cơ chế *double-submit* kiểu SPA, JavaScript phải **chủ động đưa** token vào HTTP header/form; browser tự gửi cookie không phải bằng chứng yêu cầu đó. CSRF không thay XSS defense, origin validation, session protection hoặc quyền truy cập.

### 2.1. Hai repository đều cùng interface nhưng có thuộc tính khác nhau

| Tiêu chí | `WebSessionServerCsrfTokenRepository` | `CookieServerCsrfTokenRepository` |
| --- | --- | --- |
| Vai trò | Repository mặc định của WebFlux | Repository tùy chọn phù hợp một số SPA |
| Expected token nằm ở | **WebSession attribute** trên server | **Cookie `XSRF-TOKEN`** do client giữ |
| Cookie liên quan | `SESSION` (thường), chứa session ID, không chứa token CSRF thô | `XSRF-TOKEN` mang token CSRF thô |
| Token được gửi về POST | Thường `X-CSRF-TOKEN` hoặc `_csrf` | Thường `X-XSRF-TOKEN` hoặc `_csrf` |
| JavaScript phải đọc cookie? | Không; có thể dùng HTML/form/meta/`GET /csrf` | Chỉ khi chọn SPA đọc cookie trực tiếp |
| `HttpOnly` mặc định/khuyến nghị | Session authentication cookie nên `HttpOnly` | CSRF cookie có thể `HttpOnly=false` khi JS cần đọc |
| Quan hệ với session | Expected token gắn với WebSession đang gửi | Token cookie tự mang expected token; không tự khẳng định gắn với WebSession |
| Thử negative quan trọng | Token S1 không hợp lệ với S2 | Cookie thiếu/sai hoặc header thiếu/sai |
| Rủi ro triển khai | Session loss, wrong cookie, clustering/session store | Cross-subdomain cookie injection, raw-vs-XOR, cookie flags |
| Phù hợp | Form login/SSR/BFF/browser session | SPA muốn đọc cookie CSRF, sau khi xem threat model |

Spring Security Javadoc `CsrfWebFilter` ưu tiên lưu trong WebSession thay vì cookie vì cookie có thể bị ứng dụng client sửa. Điều này **không có nghĩa** cookie repository bị cấm; nó đặt thêm trách nhiệm cho thiết kế origin, subdomain trust, request handler và regression tests.

### 2.2. Cùng một token name không có nghĩa cùng Java class

| Servlet | Reactive WebFlux |
| --- | --- |
| `org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository` | `org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository` |
| `org.springframework.security.web.csrf.CookieCsrfTokenRepository` | `org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository` |
| `CsrfTokenRepository` / `HttpServletRequest` | `ServerCsrfTokenRepository` / `ServerWebExchange` |
| `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| `MockMvc` / `SecurityMockMvcRequestPostProcessors.csrf()` | `WebTestClient` / `SecurityMockServerConfigurers.csrf()` |

Không import Servlet `CookieCsrfTokenRepository` vào `ServerHttpSecurity.csrf(...)`. Hai class cùng ý tưởng nhưng nằm trong stack, request type và test infrastructure khác nhau.

## 3. Deferred token và XOR/BREACH: lớp nào thực sự làm gì?

Trong Spring Security 6.0+, `CsrfWebFilter` sử dụng mặc định `XorServerCsrfTokenRequestAttributeHandler` để giảm nguy cơ BREACH khi token xuất hiện trong response có nén. Trong 5.8, mặc định là `ServerCsrfTokenRequestAttributeHandler` (không masking). Phân biệt phiên bản rất quan trọng khi nâng Spring Security và khi test SPA raw token.

### 3.1. Request handler khác repository

```text
Repository:
    generateToken() -> expected raw token R
    saveToken()     -> lưu R vào WebSession hoặc Cookie
    loadToken()     -> nạp R theo request

Request handler (mặc định 6.x/7.x):
    handle()        -> expose Mono<CsrfToken> dưới exchange attribute,
                       token.getToken() ở view có thể là masked M
    resolveCsrfTokenValue() -> đọc actual token từ header/form,
                               giải mã masked M khi cần, trả raw R

CsrfWebFilter:
    compare raw expected R với actual R
```

**Không nhầm** `CookieServerCsrfTokenRepository` “có token” với việc request handler đã chấp nhận raw header. Repository có thể tạo cookie đúng, nhưng actual token vẫn 403 nếu browser gửi dạng không đúng.

### 3.2. Phần “deferred” trong Reactive

`CsrfWebFilter` đưa một `Mono<CsrfToken>` vào exchange attributes. Nếu controller/view không subscribe/consume publisher, token có thể **chưa được sinh/lưu** theo lazy/deferred processing. Do đó test “GET /public/ping luôn phải có `XSRF-TOKEN`” là sai nếu không có code thực sự consume token.

Khi cần bootstrap:

```text
GET /csrf
   -> consume Mono<CsrfToken>
   -> repository generate/save nếu chưa có expected token
   -> response mang session cookie hoặc XSRF-TOKEN cookie
   -> response body/meta/form có exposed token để gửi ở POST
```

Test chính xác phải đi qua endpoint/view thực sự đọc token, thay vì kiểm tra cookie trên một endpoint không dùng token.

### 3.3. Token thay đổi qua GET không nhất thiết repository đã rotate

```text
Expected raw R trong WebSession hoặc cookie
   |
   +-- GET /csrf #1 -> exposed masked M1
   +-- GET /csrf #2 -> exposed masked M2

M1 có thể khác M2 dù raw R vẫn như cũ.
```

Không assert hai token JSON luôn bằng nhau để “chứng minh lưu token”, vì XOR có randomness. Thay vào đó, gửi M1/M2 đúng session/cookie và xác nhận cả hai được handler giải mã hợp lệ, hoặc test repository raw ở cấp unit.

## 4. Chuẩn bị dependencies và test context

### 4.1. Gradle (Spring Boot quản lý BOM)

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

Spring Boot 4 có thể sử dụng test starters chia theo web stack (như `spring-boot-starter-webflux-test`) theo đúng BOM; không trộn các starter/test annotation từ Boot 3 và Boot 4. Mục tiêu ở đây là `spring-webflux`, `spring-test`, `spring-security-test` và Security runtime cùng dòng tương thích.

### 4.2. Maven

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

Với Spring Boot BOM hoặc parent phù hợp, không tự gắn version độc lập vào `spring-security-test`. Các ví dụ trong bài **không phải kết quả đã chạy**; STEP 4 chỉ soạn nội dung. Người học có thể xác minh resolved dependency qua:

```bash
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./mvnw dependency:tree -Dincludes=org.springframework.security
```

### 4.3. Quy tắc thiết lập `WebTestClient`

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

`bindToApplicationContext` dựng mock WebFlux handler pipeline từ context; `springSecurity()` gắn phần test support của Spring Security. **Quan trọng hơn cả:** context phải chứa chính xác `SecurityWebFilterChain` và controller/repository của biến thể đang test.

Không dùng `bindToController(new MyController())` rồi kết luận CSRF đang bị tắt: mock handler đơn giản **không tự nạp** application Security WebFilters. Không dùng `csrf()` trong các tests muốn chứng minh repository đã ghi/nạp **actual token**; helper đó khiến request được coi là đáp ứng điều kiện CSRF theo cơ chế mock test, không mô phỏng đầy đủ token HTTP.

## 5. Tạo fixture chung cho cả hai repository

Ta dùng hai test contexts độc lập, mỗi context có **đúng một** `SecurityWebFilterChain`, nhưng dùng chung controller và counter. Mục tiêu: test repository thực sự được cấu hình, không phải một mock bean trả token cố định.

### 5.1. Handler public, protected và ghi đơn hàng

```java
package com.example.reactivecsrf;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class OrderRecorder {
    private final AtomicInteger count = new AtomicInteger();

    void reset() { this.count.set(0); }
    void record() { this.count.incrementAndGet(); }
    int count() { return this.count.get(); }
}

@RestController
public class TestOrdersController {

    public record CsrfEnvelope(
        String headerName, String parameterName, String token
    ) {}

    private final OrderRecorder recorder;

    public TestOrdersController(OrderRecorder recorder) {
        this.recorder = recorder;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("admin-report");
    }

    @PostMapping("/orders")
    public Mono<String> createOrder() {
        return Mono.fromSupplier(() -> {
            recorder.record();
            return "created";
        });
    }

    @GetMapping("/csrf")
    public Mono<ResponseEntity<CsrfEnvelope>> csrf(
            ServerWebExchange exchange) {
        Mono<CsrfToken> csrfToken =
            exchange.getAttribute(CsrfToken.class.getName());

        if (csrfToken == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter did not expose a token"));
        }

        return csrfToken.map(token ->
            ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new CsrfEnvelope(
                    token.getHeaderName(),
                    token.getParameterName(),
                    token.getToken()
                ))
        );
    }
}
```

`/csrf` là endpoint bootstrap dùng chung cho cả hai repository. Nó **subscribe/consume `Mono<CsrfToken>`** gián tiếp qua return publisher, vì vậy có thể buộc deferred token được generate/load/save. `Cache-Control: no-store` giảm nguy cơ proxy lưu token, nhưng còn cần CORS và origin policies phù hợp. Không đưa token vào application logs hoặc query strings.

`OrderRecorder` chỉ là test-only counter chứng minh request bị CSRF từ chối **không chạy side effect**. Ở production, thay bằng mock service/test database có isolation. Các class/package trong snippet có thể được tách thành các file Java thích hợp; không đăng ký controller hai lần bằng component scan và `@Bean`.

### 5.2. Spring WebFlux infrastructure và test users

```java
package com.example.reactivecsrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class TestReactiveWebConfig {

    @Bean
    OrderRecorder orderRecorder() {
        return new OrderRecorder();
    }

    @Bean
    TestOrdersController testOrdersController(OrderRecorder recorder) {
        return new TestOrdersController(recorder);
    }

    @Bean
    MapReactiveUserDetailsService testUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password("{noop}only-for-tests")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}only-for-tests-admin")
                .roles("ADMIN")
                .build()
        );
    }
}
```

`@EnableWebFlux` hữu ích ở **Spring Test context thuần**; trong Spring Boot application đã có auto-configuration, không tùy tiện thêm nó vì có thể thay đổi web auto-configuration. User store và password `{noop}` **chỉ cho test**, không được dùng production.

### 5.3. Chính sách URL cơ sở

Mỗi test security configuration sẽ dùng rule:

```java
.authorizeExchange(auth -> auth
    .pathMatchers("/public/**", "/csrf").permitAll()
    .pathMatchers("/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
.csrf(Customizer.withDefaults())
.httpBasic(Customizer.withDefaults())
```

`POST /orders` cần **user authenticated và CSRF token đúng**; `GET /csrf` có thể permit anonymous để bootstrap, còn `GET /admin/report` cho phép test authorization riêng. HTTP Basic giúp dùng HTTP credential thật ở live tests; trên mock context, `mockUser()` cho phép cô lập kiểm thử CSRF.

## 6. Cấu hình A — WebSession repository (mặc định)

### 6.1. Bean Security độc lập

```java
package com.example.reactivecsrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class WebSessionSecurityConfig {

    @Bean
    SecurityWebFilterChain webSessionChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/csrf").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository()
                )
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Khai báo repo tường minh ở đây để nhìn thấy đối tượng đang test. Nếu không override `csrfTokenRepository`, default WebFlux tương ứng cũng là `WebSessionServerCsrfTokenRepository`. Lưu ý không nhầm `WebSessionServerCsrfTokenRepository` với Servlet `HttpSessionCsrfTokenRepository`.

### 6.2. Test client cho cấu hình WebSession

```java
package com.example.reactivecsrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    TestReactiveWebConfig.class,
    WebSessionSecurityConfig.class
})
class WebSessionRepositoryIntegrationTest {

    @Autowired ApplicationContext context;
    @Autowired OrderRecorder recorder;

    WebTestClient client;

    @BeforeEach
    void setup() {
        recorder.reset();
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Các @Test và helper ở mục 7 được đặt trong class này.
}
```

Nếu test suite chạy **song song**, `OrderRecorder` shared trong Spring context cần isolation per test/request. Các ví dụ assume test tuần tự. Dùng `@SpringJUnitConfig` để không tự động cần TCP port; một test HTTP thật được bổ sung về sau.

## 7. Kiểm thử WebSession repository qua nhiều requests

### 7.1. Helper lấy token và session cookie

Trong `WebSessionRepositoryIntegrationTest`, thêm record và method:

```java
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

record SessionCsrf(
    String cookieName,
    String sessionId,
    String headerName,
    String exposedToken
) {}

SessionCsrf bootstrapSessionToken() {
    EntityExchangeResult<TestOrdersController.CsrfEnvelope> result =
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(TestOrdersController.CsrfEnvelope.class)
            .returnResult();

    var csrf = result.getResponseBody();
    assertNotNull(csrf);
    assertNotNull(csrf.token());

    // Tên SESSION là mặc định phổ biến; khi custom WebSessionManager
    // hoặc Spring Session đặt tên khác, dùng tên đã cấu hình.
    ResponseCookie sessionCookie =
        result.getResponseCookies().getFirst("SESSION");
    assertNotNull(sessionCookie, "Bootstrap must start a WebSession");

    return new SessionCsrf(
        sessionCookie.getName(),
        sessionCookie.getValue(),
        csrf.headerName(),
        csrf.token()
    );
}
```

`SESSION` là WebFlux session ID cookie, **không phải token CSRF**. Repository giữ expected token trong server-side WebSession attributes; cookie này chỉ giúp tìm WebSession đúng. Đặt một header `X-CSRF-TOKEN` mà không có cookie S1 không được xem là request hợp lệ với expected token từ S1.

### 7.2. Bộ ba âm/dương cho WebSession

```java
@Test
void missingCsrfHeaderIsRejectedWithSession() {
    SessionCsrf token = bootstrapSessionToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.sessionId())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}

@Test
void invalidCsrfHeaderIsRejectedWithSession() {
    SessionCsrf token = bootstrapSessionToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.sessionId())
        .header(token.headerName(), "wrong-token")
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}

@Test
void exposedTokenIsAcceptedWithSameSession() {
    SessionCsrf token = bootstrapSessionToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.sessionId())
        .header(token.headerName(), token.exposedToken())
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("created");

    assertEquals(1, recorder.count());
}
```

Các request POST ở trên **không gọi `mutateWith(csrf())`**. Vì vậy chúng kiểm tra đúng repository/handler của WebFlux đang dùng, thay vì sử dụng test mutator hợp lệ. Cùng user và URL giúp cô lập CSRF; counter đảm bảo request bị chặn không thực hiện side effect.

### 7.3. Token từ WebSession khác không hợp lệ

```java
@Test
void tokenFromAnotherWebSessionIsRejected() {
    SessionCsrf first = bootstrapSessionToken();
    SessionCsrf second = bootstrapSessionToken();

    assertNotEquals(first.sessionId(), second.sessionId());

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(second.cookieName(), second.sessionId())
        .header(second.headerName(), first.exposedToken())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Hai bootstrap requests cần thật sự tạo **hai sessions khác nhau**; `WebTestClient` không được cấu hình tự tái sử dụng cookie trước đó trong test này. Nếu bạn dùng cookie jar tự động, hãy tách client/session có chủ đích. Đây là điểm khác biệt then chốt của WebSession repo: token S1 không được dùng thay token S2.

### 7.4. Token đúng nhưng thiếu session cookie

```java
@Test
void validTokenWithoutItsSessionIsRejected() {
    SessionCsrf token = bootstrapSessionToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        // Cố ý KHÔNG gửi Cookie: SESSION
        .header(token.headerName(), token.exposedToken())
        .exchange()
        .expectStatus().isForbidden();
}
```

Test này chứng minh token đúng của **session khác hoặc session đã không được gửi** không đủ. Đừng coi đây là test “session timeout thật”: để kiểm tra timeout cần test expiration của session manager/store.

### 7.5. Test dương với mock mutator không thay round-trip

```java
@Test
void mockCsrfMutatorIsOnlyAPositiveControl() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

Đây là test khẳng định controller được xử lý **khi điều kiện CSRF test được đáp ứng**. Nó không kiểm tra WebSession attribute, cookie name hay XOR format; các test ở mục 7.2–7.4 mới làm việc đó.

## 8. Cấu hình B — Cookie repository cho SPA

Trong một SPA, frontend thường đọc cookie `XSRF-TOKEN` và gửi giá trị ở header `X-XSRF-TOKEN`. `CookieServerCsrfTokenRepository` hỗ trợ convention này; nhưng **cookie repository không tự quyết định** request handler giải mã actual token là raw hay XOR-masked.

### 8.1. Security config riêng, không trộn hai repositories

```java
package com.example.reactivecsrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class CookieSecurityConfig {

    @Bean
    SecurityWebFilterChain cookieChain(ServerHttpSecurity http) {
        // CSRF cookie đọc được bởi JavaScript; không phải session auth cookie.
        CookieServerCsrfTokenRepository repo =
            CookieServerCsrfTokenRepository.withHttpOnlyFalse();

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/csrf").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .csrf(csrf -> csrf.csrfTokenRepository(repo))
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Giữ mặc định `XorServerCsrfTokenRequestAttributeHandler` của Spring Security 6/7. Test context của cookie repository chỉ dùng `TestReactiveWebConfig.class` và `CookieSecurityConfig.class`; **không nạp cùng `WebSessionSecurityConfig.class`**, vì nhiều fallback chains sẽ làm mơ hồ chính sách.

`withHttpOnlyFalse()` cho phép JavaScript đọc **CSRF cookie**; điều này không phải lý do để hạ `HttpOnly` của cookie xác thực `SESSION`. Nếu frontend chỉ nhận token từ JSON/meta và không đọc cookie, dùng `new CookieServerCsrfTokenRepository()` để giữ `HttpOnly` cho cookie CSRF cũng là một lựa chọn.

### 8.2. Cookie flags ở version mới

Từ Spring Security 6.1, `CookieServerCsrfTokenRepository.setCookieCustomizer(...)` cho phép tùy chỉnh `ResponseCookieBuilder`. Ví dụ **cấu hình minh họa cho HTTPS staging/production**:

```java
CookieServerCsrfTokenRepository repo =
    CookieServerCsrfTokenRepository.withHttpOnlyFalse();

repo.setCookieCustomizer(cookie -> cookie
    .secure(true)
    .sameSite("Lax")
    .path("/")
);
```

Đây là cấu hình **tùy mục tiêu**, không phải một bộ giá trị dùng được cho mọi môi trường: `Secure=true` yêu cầu HTTPS; `SameSite=None` cần `Secure` và có thể bị browser chặn third-party cookies; `Path="/"` có thể vượt phạm vi cần thiết nếu app nằm dưới prefix. Đừng đặt `Domain=.example.com` tùy tiện vì subdomain ít tin cậy có thể tác động đến cookie scope.

Ở Spring Security trước 6.1, `setCookieCustomizer` chưa có; đọc Javadoc đúng phiên bản thay vì thêm dependency sai dòng chỉ để dùng method mới.

### 8.3. Cookie repository và double-submit cần threat-model review

`XSRF-TOKEN` cookie chứa một **expected token mà client có khả năng sở hữu và sửa**; do đó nó không có đúng đặc tính server-side/session binding của `WebSessionServerCsrfTokenRepository`. Chính sách origin, cookie Domain/Path, sibling-subdomain trust, signed/bound token strategy và XSS protection cần được cân nhắc.

Với form login hoặc BFF, ưu tiên WebSession repository khi có thể. Nếu cần SPA cookie, phải kiểm tra cookie injection/cross-subdomain assumptions; **không** coi việc JavaScript tự đọc được cookie CSRF là một lỗi bảo mật độc lập, vì đó là mục đích của `withHttpOnlyFalse()`, nhưng xác thực session cookie vẫn phải được bảo vệ bằng `HttpOnly`.

## 9. Kiểm thử cookie repository với **XOR handler mặc định**

### 9.1. Fixture test riêng

```java
package com.example.reactivecsrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseCookie;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@SpringJUnitConfig(classes = {
    TestReactiveWebConfig.class,
    CookieSecurityConfig.class
})
class CookieRepositoryIntegrationTest {

    @Autowired ApplicationContext context;
    @Autowired OrderRecorder recorder;

    WebTestClient client;

    @BeforeEach
    void setup() {
        recorder.reset();
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Thêm helper và các tests ở các mục tiếp theo vào class này.
}
```

Không dùng `@SpringJUnitConfig` chứa cả `CookieSecurityConfig` và `WebSessionSecurityConfig`. Test repo phải biết chính xác filter chain và repo đang dùng.

### 9.2. Lấy cả raw cookie token và exposed masked token

```java
record CookieCsrf(
    String cookieName,
    String rawCookieToken,
    String headerName,
    String exposedToken,
    ResponseCookie cookieMetadata
) {}

CookieCsrf bootstrapCookieToken() {
    EntityExchangeResult<TestOrdersController.CsrfEnvelope> result =
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(TestOrdersController.CsrfEnvelope.class)
            .returnResult();

    TestOrdersController.CsrfEnvelope body = result.getResponseBody();
    assertNotNull(body);
    assertNotNull(body.token());

    ResponseCookie tokenCookie =
        result.getResponseCookies().getFirst("XSRF-TOKEN");
    assertNotNull(tokenCookie, "Cookie repository must issue a token cookie");
    assertFalse(tokenCookie.getValue().isBlank());

    return new CookieCsrf(
        tokenCookie.getName(),
        tokenCookie.getValue(),
        body.headerName(),
        body.token(),
        tokenCookie
    );
}
```

Hai giá trị **khác vai trò**: `rawCookieToken()` là raw expected token mà repository đã phát; `exposedToken()` là token do request handler đưa cho view/endpoint, ở 6/7 mặc định thường là XOR-masked. Không assert `rawCookieToken().equals(exposedToken())`. Với version/handler khác, quan hệ có thể đổi.

### 9.3. Test cookie được phát và có thuộc tính dự kiến

```java
@Test
void cookieRepositoryIssuesReadableCsrfCookie() {
    CookieCsrf cookie = bootstrapCookieToken();

    assertEquals("XSRF-TOKEN", cookie.cookieName());
    assertFalse(cookie.cookieMetadata().isHttpOnly(),
        "Only CSRF cookie is intentionally readable by JavaScript");

    // Nếu production config dùng setCookieCustomizer(secure/sameSite/path),
    // bổ sung assertions isSecure(), getSameSite(), getPath() tương ứng.
}
```

Không cần assert `SESSION` tồn tại cho cookie repository, trừ khi app còn một **authentication session** thực sự. `CookieServerCsrfTokenRepository` có thể hoạt động độc lập với server-side CSRF session; việc `mockUser()` tạo auth ở mock exchange không bắt buộc sinh `SESSION` cookie.

### 9.4. Cookie có mặt nhưng không gửi header vẫn phải bị chặn

```java
@Test
void cookieAloneDoesNotSatisfyCsrfValidation() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.rawCookieToken())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Đây là **negative test quan trọng nhất** cho cookie repo: browser tự gửi cookie `XSRF-TOKEN` là không đủ; JavaScript phải chủ động gửi token trong header/form theo handler.

### 9.5. Header có nhưng không gửi CSRF cookie

```java
@Test
void headerWithoutExpectedCookieIsRejected() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        // Không gửi cookie XSRF-TOKEN của bootstrap.
        .header(token.headerName(), token.exposedToken())
        .exchange()
        .expectStatus().isForbidden();
}
```

Không có CSRF cookie, repository sẽ không nạp được expected raw token của request trước. Một token masked đúng lấy từ bootstrap cũ **không** trở thành hợp lệ nếu cookie expected bị bỏ.

### 9.6. Cookie raw token đúng + exposed token đúng ở header

```java
@Test
void cookieAndExposedMaskedTokenPassRoundTrip() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.rawCookieToken())
        .header(token.headerName(), token.exposedToken())
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("created");

    assertEquals(1, recorder.count());
}
```

Lưu ý **gửi lại exposed token chứ không mặc định gửi raw cookie value**. Với handler XOR mặc định, exposed token masked được giải mã trước khi so với raw expected token mà cookie repo nạp.

### 9.7. Cookie sai hoặc header sai

```java
@Test
void incorrectCookieValueIsRejected() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), "incorrect-expected-value")
        .header(token.headerName(), token.exposedToken())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}

@Test
void incorrectHeaderValueIsRejected() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.rawCookieToken())
        .header(token.headerName(), "incorrect-actual-value")
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Trong mỗi test, chỉ một phần thay đổi. Nếu header đúng nhưng cookie sai bị 403, repository vẫn chịu trách nhiệm expected token; nếu cookie đúng nhưng header sai bị 403, request handler/CSRF comparison không chấp nhận actual token.

### 9.8. Thử gửi raw cookie làm header với handler XOR

```java
@Test
void rawCookieValueIsNotAssumedValidForXorHandler() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.rawCookieToken())
        .header(token.headerName(), token.rawCookieToken())
        .exchange()
        .expectStatus().isForbidden();
}
```

Với **default XOR handler** của Security 6/7, raw token do cookie repo tạo không có định dạng masked mà handler đang resolve, nên test trên có thể/phải bị từ chối theo cấu hình minh họa. Khi app sử dụng `ServerCsrfTokenRequestAttributeHandler` thay XOR hoặc handler custom hỗ trợ raw header, **expected status thay đổi**; không sao chép test 403 này như bất biến cho mọi version/handler.

## 10. SPA muốn gửi raw `X-XSRF-TOKEN`: thiết kế request handler có chủ đích

Khi frontend JavaScript đọc cookie `XSRF-TOKEN`, nó thường gửi lại **raw token** trong `X-XSRF-TOKEN`. Đó là flow khác với việc frontend đọc `GET /csrf` rồi gửi **masked token**. Nếu dự án sử dụng Spring Security 6/7 và vẫn giữ default XOR handler, raw header có thể không được giải mã.

**Repository không sửa được lỗi request handler.** Thay `WebSessionServerCsrfTokenRepository` thành `CookieServerCsrfTokenRepository` mà không nghĩ đến `ServerCsrfTokenRequestHandler` là nguyên nhân phổ biến khiến một SPA vừa nâng phiên bản bị 403.

### 10.1. Phương án đơn giản nhưng có đánh đổi: handler không mask

Spring Security cho phép:

```java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()
    )
    .csrfTokenRequestHandler(
        new ServerCsrfTokenRequestAttributeHandler()
    )
);
```

`ServerCsrfTokenRequestAttributeHandler` resolve raw header/form value, nên cookie/header raw cùng giá trị có thể đi qua CSRF. **Nhưng cấu hình này tắt lớp XOR/BREACH masking** khi expose token. Nếu ứng dụng render token vào HTML/nội dung nén, phải đánh giá rủi ro; đừng tắt BREACH protection chỉ để một negative/positive test xanh.

### 10.2. Phương án nâng cao: giữ XOR khi expose, chấp nhận raw header từ SPA

Một cách thiết kế là **dùng XOR handler để expose token** cho HTML/form, nhưng dùng raw resolver khi request đến với header CSRF được đặt tường minh bởi JavaScript. Cần viết và review custom handler theo API từng version; ví dụ WebFlux 6.5/7.x:

```java
package com.example.reactivecsrf;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class SpaRawHeaderCsrfRequestHandler
        implements ServerCsrfTokenRequestHandler {

    private final ServerCsrfTokenRequestHandler xor =
        new XorServerCsrfTokenRequestAttributeHandler();

    private final ServerCsrfTokenRequestHandler plain =
        new ServerCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(ServerWebExchange exchange, Mono<CsrfToken> csrfToken) {
        // Giữ masking cho token expose vào view hoặc /csrf.
        xor.handle(exchange, csrfToken);
    }

    @Override
    public Mono<String> resolveCsrfTokenValue(
            ServerWebExchange exchange, CsrfToken expected) {

        // JavaScript SPA gửi raw token bằng CSRF header.
        String actualHeader = exchange.getRequest().getHeaders()
            .getFirst(expected.getHeaderName());

        if (actualHeader != null) {
            // Resolve raw header; CsrfWebFilter vẫn so với expected token.
            return plain.resolveCsrfTokenValue(exchange, expected);
        }

        // Form HTML vẫn gửi masked token, giữ bảo vệ BREACH.
        return xor.resolveCsrfTokenValue(exchange, expected);
    }
}
```

Đây là **mẫu tùy biến cần security review**, không phải bean mặc định hay một API `csrf.spa()` của Reactive. Khi header hiện diện nhưng sai, bộ lọc vẫn phải từ chối; không fallback sang token form/cookie như cách né validation. Header custom thường gây CORS preflight nếu khác origin; chỉ allowlist những origin đáng tin, không đặt `Access-Control-Allow-Origin: *` cho credentialed SPA.

### 10.3. Config cho SPA raw-header variant

```java
@Configuration
@EnableWebFluxSecurity
public class RawCookieSpaSecurityConfig {

    @Bean
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/csrf", "/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieServerCsrfTokenRepository.withHttpOnlyFalse()
                )
                .csrfTokenRequestHandler(
                    new SpaRawHeaderCsrfRequestHandler()
                )
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Ví dụ là **biến thể thay thế** `CookieSecurityConfig` ở mục 8. Chỉ nạp một config tương ứng trong mỗi test; nếu cần import các class Java, dùng `org.springframework.context.annotation.Configuration/Bean`, `org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity` và các imports như mục 8.1.

### 10.4. Regression tests bắt buộc cho handler tùy chỉnh

Đặt test trong context chứa `TestReactiveWebConfig` và `RawCookieSpaSecurityConfig`, dùng `CookieCsrf bootstrapCookieToken()` tương tự mục 9:

```java
@Test
void spaRawHeaderMatchesRawCookieWhenCustomHandlerIsEnabled() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.rawCookieToken())
        .header(token.headerName(), token.rawCookieToken())
        .exchange()
        .expectStatus().isOk();
}

@Test
void spaStillRejectsMissingOrIncorrectRawHeader() {
    CookieCsrf token = bootstrapCookieToken();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.rawCookieToken())
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.rawCookieToken())
        .header(token.headerName(), "wrong")
        .exchange()
        .expectStatus().isForbidden();
}
```

Mục tiêu ở đây là so sánh **hai biến thể được khai báo rõ**:

| Repository + handler | Actual header | Expected |
| --- | --- | --- |
| Cookie + default XOR | Masked token từ `GET /csrf` | 200 khi cùng raw cookie |
| Cookie + default XOR | Raw value từ `XSRF-TOKEN` cookie | 403 theo fixture |
| Cookie + raw-only `ServerCsrfTokenRequestAttributeHandler` | Raw value từ cookie | 200, nhưng mất XOR masking |
| Cookie + custom hybrid ở trên | Raw value trong `X-XSRF-TOKEN` | 200 |
| Cookie + custom hybrid ở trên | Masked form parameter hợp lệ | 200, với form handler phù hợp |
| Bất kỳ handler nào | Cookie đúng nhưng header/parameter thiếu hoặc sai | 403 |

Nếu dự án quyết định **chỉ dùng JSON `GET /csrf`** cho SPA, không nhất thiết cần cookie đọc bằng JS: có thể chọn WebSession repository và giữ XOR mặc định, giảm bớt các rủi ro cookie-injection/cross-domain.

## 11. Kiểm tra repository ở cấp đơn vị, không qua SecurityWebFilterChain

`WebTestClient` integration quan trọng, nhưng đôi khi cần cô lập một câu hỏi thấp hơn: `generateToken`, `saveToken`, `loadToken` có hoạt động theo đúng backing store không? Dùng `MockServerWebExchange` + `StepVerifier` để test **repository instance** độc lập với request handler/auth.

### 11.1. WebSession repo: save và load trong cùng exchange

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Test
void webSessionRepositoryPersistsRawToken() {
    var repo = new WebSessionServerCsrfTokenRepository();
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/csrf")
    );

    var generated = repo.generateToken(exchange).block();
    assertNotNull(generated);

    StepVerifier.create(
        repo.saveToken(exchange, generated)
            .then(repo.loadToken(exchange))
    )
        .assertNext(loaded ->
            org.junit.jupiter.api.Assertions.assertEquals(
                generated.getToken(), loaded.getToken()
            )
        )
        .verifyComplete();
}
```

`block()` dùng **trong JUnit test setup**, không dùng trong WebFlux request handler. Test này chỉ chứng minh save/load trên **một `MockServerWebExchange`**. Nó không kiểm tra WebSession cookie qua hai HTTP requests, session store cluster, raw-vs-masked token hoặc login/logout; các tests ở mục 7 giải quyết phần đó.

### 11.2. Cookie repo: save sinh `Set-Cookie`, load đọc `Cookie`

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpCookie;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Test
void cookieRepositoryStoresAndReloadsRawToken() {
    var repo = CookieServerCsrfTokenRepository.withHttpOnlyFalse();
    var first = MockServerWebExchange.from(
        MockServerHttpRequest.get("/csrf")
    );

    var generated = repo.generateToken(first).block();
    assertNotNull(generated);
    StepVerifier.create(repo.saveToken(first, generated))
        .verifyComplete();

    var responseCookie = first.getResponse()
        .getCookies().getFirst("XSRF-TOKEN");
    assertNotNull(responseCookie);

    var next = MockServerWebExchange.from(
        MockServerHttpRequest.post("/orders")
            .cookie(new HttpCookie(
                "XSRF-TOKEN", responseCookie.getValue()))
    );

    StepVerifier.create(repo.loadToken(next))
        .assertNext(loaded ->
            org.junit.jupiter.api.Assertions.assertEquals(
                generated.getToken(), loaded.getToken()
            )
        )
        .verifyComplete();
}
```

Test này **không** assert CSRF filter sẽ cho POST đi qua: nó kiểm tra raw repository persistence. Nếu XOR handler đang chờ masked actual token, một raw `X-XSRF-TOKEN` header vẫn có thể bị từ chối; cần integration test ở mục 9/10.

### 11.3. Token deletion là một contract riêng

`saveToken(exchange, null)` được interface quy định để **xóa expected token**. Trong WebSession repo, hành vi này xóa attribute; cookie repo phát cookie delete/expired. Nếu viết unit test deletion, kiểm tra:

- Sau `saveToken(..., null)`, `loadToken` trên cùng session không còn trả token cũ.
- Cookie repo phát response cookie xóa token với scope `Path`/`Domain` phù hợp.
- Request sau logout/bootstrap mới không thể dùng mù token trước đó.

Đừng dựa vào **một status POST 403** để kết luận token đã bị xóa; 403 cũng có thể do user không được phép hoặc authentication đã hết hiệu lực.

## 12. Cookie attributes: kiểm tra điều browser thực sự nhận

Khi chuyển từ WebSession repository sang cookie repository, test không chỉ cần có `XSRF-TOKEN`, mà phải kiểm tra cookie có **scope** và thuộc tính phù hợp với origin, HTTPS và thiết kế frontend. Lỗi `Path`/`Domain` làm browser không gửi cookie, còn `HttpOnly=true` ngăn JavaScript đọc cookie dù server đã phát token.

### 12.1. Bảng thuộc tính và hệ quả

| Thuộc tính | Cookie CSRF `XSRF-TOKEN` | Session auth cookie `SESSION` |
| --- | --- | --- |
| `HttpOnly` | False **chỉ khi** SPA phải đọc token bằng JS; nếu không thì nên True | Nên True, tránh JS đọc credential |
| `Secure` | Nên True khi triển khai HTTPS; bắt buộc với `SameSite=None` | Nên True với HTTPS |
| `SameSite` | Chọn Lax/Strict/None theo flow browser thực | Phù hợp login, redirects, cross-site requirements |
| `Domain` | Ưu tiên **host-only** khi có thể | Ưu tiên host-only để giảm phạm vi |
| `Path` | Phải bao phủ path nơi client gửi CSRF token | Phải phù hợp app context/path login |
| `Max-Age` | Gắn với vòng đời token; không giữ token vô hạn | Gắn với session timeout/remember-me policy |

**Không áp `withHttpOnlyFalse()` lên session authentication cookie**. Nó chỉ nên được sử dụng cho cookie **CSRF** mà SPA thực sự cần đọc. Trong WebFlux, session cookie có thể mang tên `SESSION`, nhưng Spring Session/custom WebSessionManager có thể thay tên.

### 12.2. Test cookie customizer trong HTTPS profile

Ví dụ trong `CookieSecurityConfig` thay repository:

```java
CookieServerCsrfTokenRepository repo =
    CookieServerCsrfTokenRepository.withHttpOnlyFalse();

repo.setCookieCustomizer(cookie -> cookie
    .secure(true)
    .sameSite("Lax")
    .path("/")
);
```

Và assert trên response cookie:

```java
@Test
void csrfCookieAttributesMatchApprovedPolicy() {
    CookieCsrf token = bootstrapCookieToken();
    ResponseCookie cookie = token.cookieMetadata();

    assertFalse(cookie.isHttpOnly());          // SPA JS sẽ đọc token
    org.junit.jupiter.api.Assertions.assertTrue(cookie.isSecure());
    assertEquals("Lax", cookie.getSameSite());
    assertEquals("/", cookie.getPath());
}
```

Test này **chỉ hợp lệ** khi đã bật `setCookieCustomizer` như đoạn trên. Nếu fixture ở mục 8.1 không custom `Secure`/`SameSite`, đừng hard-code test expecting chúng. Mock WebTestClient cũng **không mô phỏng việc browser từ chối cookie `Secure` trên HTTP**; phải có browser/HTTPS staging tests.

### 12.3. Host-only cookie và frontend ở một origin khác

Giả sử:

```text
HTML SPA: https://app.example.com
Reactive API: https://api.example.com

Set-Cookie từ api.example.com:
  XSRF-TOKEN=R; Path=/; Secure; SameSite=Lax

Browser có thể lưu/gửi cookie tới api.example.com theo policy,
nhưng JavaScript chạy trên app.example.com
KHÔNG đọc cookie host-only của api.example.com qua document.cookie.
```

CORS `Access-Control-Allow-Origin` đúng cho phép JS **đọc response** của API khi credential policy cho phép, **không** cho phép `document.cookie` đọc cookie host-only của origin khác. Những hướng xử lý có thể xem xét:

- Dùng **BFF/reverse proxy cùng origin**: SPA fetch `/api/**` cùng host.
- Trả exposed CSRF token qua **JSON `GET /csrf`** với CORS allowlist thích hợp, để SPA lấy token mà không đọc cookie của API.
- Thiết kế cookie Domain chung **chỉ sau đánh giá subdomain trust/cookie injection**, không mở rộng mặc định.
- Sử dụng WebSession repository + JSON token endpoint, nếu không cần JS đọc raw CSRF cookie.

Đừng tắt `HttpOnly` của authentication cookie để giải quyết lỗi CSRF. CORS, CSRF, SameSite và CSP xử lý các mối đe dọa **khác nhau**.

### 12.4. Test cookie scope bằng HTTP thực

`WebTestClient` mock có thể xem `ResponseCookie.getPath()`, `getSameSite()`, `isSecure()` và `isHttpOnly()`, nhưng không tự áp các browser cookie-matching rules như Chrome. Với staging HTTPS, dùng browser devtools/automation:

1. Mở HTML ở origin thực.
2. Gọi `GET /csrf` hoặc endpoint phát token.
3. Quan sát `Set-Cookie` và cookie jar ở đúng host.
4. Gửi POST đúng path và kiểm tra Request Cookies + `X-XSRF-TOKEN`.
5. Lặp lại sau login/logout và khi path/hostname thay đổi.
6. Thử origin không tin cậy và verify CORS không cho truy cập dữ liệu.

Không in raw token, session ID hoặc cookie value vào build logs.

## 13. CORS, credentialed SPA và preflight khi dùng cookie repository

CSRF token được gửi qua custom HTTP header thường khiến browser gửi `OPTIONS` preflight khi frontend/API **khác origin**. Preflight thường **không có cookie authentication**, vì thế CORS cần được xử lý trước khi Spring Security đòi authentication.

### 13.1. Reactive CORS source

```java
package com.example.reactivecsrf;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class TestCorsConfig {

    @Bean
    CorsConfigurationSource csrfCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-XSRF-TOKEN", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
```

Import `org.springframework.web.cors.reactive.CorsConfigurationSource` là **bắt buộc** ở WebFlux; Servlet có interface cùng tên khác package. Đừng đăng ký một CORS source trùng và không nhất quán ở gateway + Security + HandlerMapping.

Để dùng trong `CookieSecurityConfig` hoặc `WebSessionSecurityConfig`, inject `CorsConfigurationSource csrfCorsSource` và thêm:

```java
.cors(cors -> cors.configurationSource(csrfCorsSource))
```

Đây là thay đổi trên **chain hiện có**, không thêm một security chain khác. Test context của variant này phải nạp `TestCorsConfig.class`.

### 13.2. Preflight tests không dùng `csrf()`

```java
@Test
void allowedPreflightSucceedsBeforeLogin() {
    client.options().uri("/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-xsrf-token"
        )
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin", "https://app.example.com")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true");
}

@Test
void untrustedOriginCannotReadCredentialedResponse() {
    client.options().uri("/orders")
        .header("Origin", "https://untrusted.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectHeader().doesNotExist(
            "Access-Control-Allow-Origin");
}
```

Test assume CORS đã được gắn vào chain đúng. OPTIONS là safe method trong CSRF matcher mặc định; không thêm `csrf()` vào preflight để chữa 401. Negative origin có thể trả 403 hoặc status khác, nhưng **không được cấp `Access-Control-Allow-Origin` cho untrusted origin**.

### 13.3. CORS không thay CSRF

```text
OPTIONS /orders
  -> CORS kiểm tra Origin, method, header
  -> được phép: response preflight
  -> không tự xác thực user hoặc kiểm tra CSRF token

POST /orders
  -> browser có thể tự gửi session cookie
  -> CsrfWebFilter vẫn yêu cầu header/form token hợp lệ
  -> authorization kiểm tra role/scope trước xử lý nghiệp vụ
```

Một OPTIONS pass không chứng minh frontend gửi đúng raw/masked token. Khi thấy POST 403 sau OPTIONS 200, kiểm tra repository, handler, cookie, session, body/header và authorization, **không mở `Access-Control-Allow-Origin: *`** để che lỗi.

## 14. Login, logout, session timeout và token rotation

### 14.1. WebSession repo: token gắn với session

`WebSessionServerCsrfTokenRepository` ràng buộc expected token với WebSession. Khi session hết hạn hoặc bị xóa, token cũ không thể tự xác nhận request mới. Nếu session store bị mất giữa replicas do cấu hình sai, frontend có thể thấy hàng loạt 403 sau deploy.

```text
GET /csrf -> session S1, token T1
POST /login (S1,T1,credentials)
  -> authentication/session strategies có thể đổi session/token
GET /csrf -> nhận cookie/session/token cần thiết cho trạng thái mới
POST /orders -> user hợp lệ + CSRF mới hợp lệ
POST /logout -> CSRF + auth session được xóa theo strategy
POST bằng cookie/token trước logout -> không được phép xử lý
```

**Không khẳng định mặc định mỗi lần login sẽ luôn rotate token theo một cách/phiên bản cố định**. Test contract thực tế là session/token cũ không được cho phép side effect trái policy, còn client phải biết bootstrap token hợp lệ sau authentication.

### 14.2. Cookie repo: đừng mặc định token gắn với login session

Với `CookieServerCsrfTokenRepository`, expected CSRF token lấy từ `XSRF-TOKEN` cookie. Nó không có cùng semantics **server-side WebSession attribute**. Vì vậy không viết test “CSRF token của browser A chắc chắn không hợp lệ nếu browser B đã copy cả raw cookie token và gửi actual header khớp” rồi coi đó là bất biến của repository cookie.

Thay vào đó:

- Kiểm tra cookie và actual header **khớp chính xác** theo handler.
- Kiểm tra cookie/header thiếu hoặc sai bị chặn.
- Kiểm tra flow login/logout xóa hoặc cấp lại CSRF cookie theo strategy mà app thực sự dùng.
- Nếu threat model cần token **gắn mật mã với user/session**, thiết kế signed/session-bound token repository riêng và test property ấy; `CookieServerCsrfTokenRepository` mặc định không tự bảo đảm điều đó.

### 14.3. Tại sao `mockUser()` không thay login/logout thật?

`mockUser()` tạo authentication trong **mock exchange**. Nó không chạy form login success handler, session fixation strategy, logout handler hay token clearing giống luồng authentication thực. Do đó một test dùng `mockUser()` + `csrf()` pass **không** chứng minh token rotation sau login/logout.

Để kiểm tra lifecycle, dùng form login hoặc OAuth2 login thực với test identity provider, giữ session/cookie qua nhiều HTTP requests. Với API Bearer-only, session login flow có thể không tồn tại; đừng áp script login/logout của browser lên resource server.

### 14.4. Token hết hạn khi cookie còn tồn tại

Cookie repo có token tồn tại theo browser cookie expiry. Nếu `XSRF-TOKEN` còn nhưng session auth đã hết hạn, request có header đúng vẫn có thể bị 401/redirect do authentication. Ngược lại WebSession repo có thể trả 403 vì expected token đã mất sau timeout. Cần test cả **CSRF** lẫn **authentication**; không coi cùng một status 403 là lỗi của repository nếu user đã mất quyền.

### 14.5. Triển khai đa replica và rolling deployment

| Tình huống | WebSession repository | Cookie repository |
| --- | --- | --- |
| Request từ pod A rồi pod B | Cần shared/persisted WebSession (ví dụ Spring Session), hoặc sticky-session theo thiết kế | CSRF expected token đến từ request cookie, nhưng **authentication session** vẫn có thể cần shared store |
| Logout ở pod A, request tới B | Cần đồng bộ trạng thái session/logout | Cần cookie clearing và authentication invalidation trên mọi pod |
| Nâng version Serialization/SessionContext | Kiểm tra dữ liệu WebSession tương thích | Cookie CSRF đơn giản hơn nhưng auth session vẫn có thể ảnh hưởng |
| Proxy đổi scheme/host/path | Session cookie mất/không gửi gây 403 | CSRF cookie mất/không gửi gây 403 |

Test staging phải phản ánh số replicas và session store topology; `MockWebTestClient` một JVM không bắt được mọi lỗi multi-node.

## 15. Nhiều `SecurityWebFilterChain`: repo nào có hiệu lực?

Spring Security Reactive có thể có nhiều `SecurityWebFilterChain` được chọn theo `securityMatcher` và `@Order`. Repository CSRF được cấu hình **trên chain**; request chỉ chịu chính sách CSRF của chain được chọn. Vì vậy test WebSession repository cho browser không chứng minh cookie repository của SPA API đang hoạt động nếu hai chain khác nhau.

### 15.1. Ví dụ hai browser chains có nhu cầu khác nhau

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

@Bean
@Order(1)
SecurityWebFilterChain spa(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/spa/**"))
        .authorizeExchange(auth -> auth
            .pathMatchers("/spa/csrf").permitAll()
            .anyExchange().authenticated()
        )
        .csrf(csrf -> csrf
            .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse()
            )
            .csrfTokenRequestHandler(
                new SpaRawHeaderCsrfRequestHandler()
            )
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browserFallback(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public/**", "/csrf").permitAll()
            .anyExchange().authenticated()
        )
        .csrf(csrf -> csrf
            .csrfTokenRepository(
                new WebSessionServerCsrfTokenRepository()
            )
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đây là **một ví dụ minh họa thay thế** các fixture một chain ở trên. `SpaRawHeaderCsrfRequestHandler` là class custom ở mục 10; ứng dụng phải có handler/endpoint tương ứng cho `/spa/csrf`. Trong cùng ứng dụng có hai token repositories, không gọi `GET /csrf` (fallback) để bootstrap cho `POST /spa/orders` (SPA chain) rồi mong hợp lệ.

### 15.2. Kiểm thử selected chain trước khi test token

```text
GET /csrf       -> fallback (WebSession repo)
POST /orders    -> fallback (WebSession repo)

GET /spa/csrf   -> SPA chain (Cookie repo)
POST /spa/order -> SPA chain (Cookie repo)

GET /spa-v2/... -> fallback trừ khi matcher SPA đã mở rộng
```

`/spa/**` không nhất thiết bao phủ `/spa` không slash hoặc route sau proxy rewrite. Test URL tại public entrypoint và matcher đúng; một 403 do sai chain có thể bị chẩn đoán nhầm là token sai.

### 15.3. Nếu API dùng Bearer-only và tắt CSRF

Với API **thực sự** chỉ chấp nhận Bearer token được client thêm chủ động, không dùng cookie/auth credential browser tự đính kèm, có thể đánh giá miễn CSRF trên **đúng API chain**. Điều này không có nghĩa `WebSessionServerCsrfTokenRepository` hoặc `CookieServerCsrfTokenRepository` bị vô hiệu cho các browser chains khác.

Một regression test thiết yếu:

```java
@Test
void browserPostStillNeedsCsrfAfterApiChainWasAdded() {
    // Fixture có fallback browser chain và POST /orders.
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();
}
```

Nếu POST này bất ngờ thành công, kiểm tra API chain matcher có vô tình dùng `/**` hay không, fallback chain có tồn tại không và CSRF của browser chain có bị disable không. Đừng suy rằng `anyExchange()` của một chain hẹp bảo vệ URL ngoài `securityMatcher`.

## 16. `@WebFluxTest`, `@SpringBootTest` và HTTP server thật

### 16.1. Test slice: phải nạp đúng repo/handler

`@WebFluxTest` trong Spring Boot chỉ nạp một phần WebFlux beans; **custom `SecurityWebFilterChain` và custom repo/handler không nhất thiết có mặt**. Khi viết slice tests cho CSRF, dùng `@Import` đúng config và dependency, hoặc chuyển sang `@SpringBootTest` nếu cần full context.

Ví dụ **Spring Boot 3.5 package**:

```java
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;

@WebFluxTest(TestOrdersController.class)
@Import({WebSessionSecurityConfig.class, TestSliceBeans.class})
class WebSessionCsrfSliceTest {
    // @Autowired ApplicationContext và WebTestClient
    // được bindToApplicationContext(context).apply(springSecurity())
    // Viết negative/positive/round-trip tests tương ứng.
}
```

`TestSliceBeans` là config **do người học phải tự định nghĩa**, không phải Spring class có sẵn: nó có thể cung cấp `OrderRecorder` và test user store. Nếu muốn chạy fixture hoàn chỉnh mà không phụ thuộc Boot, dùng `@SpringJUnitConfig` ở mục 6/9.

Trong Spring Boot **4.x**, import test annotations chuyển theo tổ chức modules:

```java
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
```

Đọc migration guide và starter dependencies cho đúng dòng. Không copy cả import Boot 3 và Boot 4 vào cùng class.

### 16.2. `@SpringBootTest` full context vẫn có thể là mock

```java
@SpringBootTest
class FullContextRepositoryTest {

    @Autowired ApplicationContext context;

    @Test
    void webSessionPolicyIsActive() {
        WebTestClient client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();

        client.mutateWith(mockUser("alice").roles("USER"))
            .post().uri("/orders")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`@SpringBootTest` với web environment mặc định **không có nghĩa mở server TCP**. Ở đây `WebTestClient` vẫn bind in-memory. Full context có thể nạp cấu hình giống production hơn slice, nhưng vẫn không mô phỏng HTTPS ingress/cookie engine của browser.

### 16.3. `RANDOM_PORT` và `bindToServer`: gửi token thực qua HTTP

`@SpringBootTest(webEnvironment=RANDOM_PORT)` mở HTTP server trên cổng thật. Khi đó:

- Dùng `WebTestClient` được Boot auto-configured đúng port hoặc `WebTestClient.bindToServer()`.
- **Không** dùng `SecurityMockServerConfigurers.csrf()` để “gửi token” qua TCP; helper cần mock `WebHttpHandlerBuilder`.
- Bootstrap `GET /csrf` và giữ `Set-Cookie` phù hợp, rồi POST header/form token.
- Authentication phải dùng **HTTP credential thật** (Basic/JWT/form login), không dựa vào `mockUser()` test thread.

Ví dụ fragment cho WebSession repo:

```java
http.post().uri("/orders")
    .headers(headers -> headers.setBasicAuth(
        "alice", "only-for-tests"))
    .cookie("SESSION", sessionIdFromGetCsrf)
    .header(csrfHeaderName, exposedTokenFromGetCsrf)
    .exchange()
    .expectStatus().isOk();
```

Với cookie repo:

```java
http.post().uri("/orders")
    .headers(headers -> headers.setBasicAuth(
        "alice", "only-for-tests"))
    .cookie("XSRF-TOKEN", rawCookieValueFromGetCsrf)
    .header("X-XSRF-TOKEN", tokenValueAcceptedByHandler)
    .exchange()
    .expectStatus().isOk();
```

Các biến là dữ liệu do **GET bootstrap ở cùng test** cung cấp; đây là request fragments, không phải standalone test classes. Nếu login dùng session cookie, phải giữ **cả auth session cookie và CSRF cookie**. `WebTestClient` HTTP không tự áp mọi chính sách cookie của Chrome; cần browser E2E để kiểm tra `SameSite`, `Secure` và cross-origin behavior.

### 16.4. Triển khai sau reverse proxy

Kiểm thử qua `RANDOM_PORT` không nhất thiết bắt được:

- TLS termination, HSTS, `Forwarded`/`X-Forwarded-Proto` và redirect scheme.
- API ở `/backend/**` nhưng public URL ở `/api/**` sau prefix rewrite.
- CDN cache response `GET /csrf` trái `no-store` policy.
- CORS được xử lý ở gateway thay cho Spring, hoặc duplicate headers.
- Cookie `Domain`/`Path` bị ingress thay đổi.
- Session store phân tán và rolling deploy.

Do đó sau khi test repository ở mock context và local HTTP, chạy smoke tests trên **public HTTPS origin** với browser thật.

## 17. Cùng một 403 có thể đến từ nhiều lớp bảo vệ

### 17.1. Bảng phân biệt nguyên nhân

| Request/hành vi | Nguồn lỗi có thể | Status thường gặp |
| --- | --- | --- |
| POST user hợp lệ, không CSRF token | `CsrfWebFilter` | 403 |
| POST cookie raw và header masked sai | Repository + request handler | 403 |
| GET `/admin/report` với role USER | Authorization | 403 |
| GET private API thiếu Bearer | Authentication entry point | 401 |
| POST không user, không CSRF | CSRF **hoặc** authentication (tùy chain/order) | 403/401 |
| OPTIONS origin không hợp lệ | CORS source/proxy | Có thể 403/không cấp CORS headers |
| GET semicolon/encoded slash bất thường | HTTP firewall/server parser | Thường 400 |
| GET URL không có handler | Routing | 404 |
| POST method không được handler hỗ trợ | Routing, sau các filters phù hợp | 405 |

Vì CSRF thường kiểm tra unsafe method trước authorization, một POST thiếu token có thể trả 403 ngay cả khi user chưa login. Để kiểm tra **repository**, giữ principal/authentication đúng và dùng positive control cùng URL. Để kiểm tra **authentication**, dùng GET protected không bị CSRF matcher ảnh hưởng.

### 17.2. Security headers và HTTP firewall vẫn cần regression tests

`csrf()` hoặc test token round-trip xanh không chứng minh:

- `Content-Security-Policy` của **HTML frontend** đúng, nhất là khi CDN phục vụ HTML ngoài Spring.
- `Strict-Transport-Security` đang được browser nhận trên HTTPS public.
- `X-Content-Type-Options: nosniff` vẫn có trên response thuộc security chain.
- `StrictServerWebExchangeFirewall` (WebFlux từ Security 6.4+) đang chặn URL/method nguy hiểm.
- Cookie session có `HttpOnly/Secure/SameSite` phù hợp và được quản lý đúng.

Một test header đơn giản trong app có cấu hình CSP chủ động:

```java
@Test
void publicResponseStillGetsSecurityHeaders() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");

    // Chỉ assert Content-Security-Policy nếu app đã cấu hình explicit;
    // Spring Security không tự đặt một CSP phù hợp mọi website.
}
```

Đừng lấy một request URL bị HTTP firewall reject 400 làm bằng chứng CSRF hoạt động; đó là hai lớp khác nhau. Test URL canonical cho CSRF và URL bất thường ở suite firewall riêng.

## 18. Runbook chẩn đoán WebSession và Cookie CSRF repository

### Lỗi A — `GET /csrf` không trả token hoặc gặp 500

**Kiểm tra:** `CsrfWebFilter` có trong selected chain không? `/csrf` có đi qua đúng chain không? Controller có đọc exchange attribute `CsrfToken.class.getName()` và **subscribe/consume Mono** không? Có bị `web.ignoring()` (Servlet) hoặc bỏ qua toàn WebFlux security chain không?

**Cách sửa:** bind vào context có `SecurityWebFilterChain` và `springSecurity()`, dùng endpoint GET bootstrap tiêu thụ token, giữ CORS/cache policy an toàn. Không trả token constant từ controller để che lỗi cấu hình.

### Lỗi B — WebSession repository không có `SESSION` cookie

**Kiểm tra:** WebSession đã được tạo/lưu chưa? Token Mono đã được consume chưa? App có custom `WebSessionManager` hoặc Spring Session thay cookie name không? Response có bị gateway xóa `Set-Cookie` không?

**Cách sửa:** test repository `saveToken`/`loadToken` bằng `MockServerWebExchange` và xác minh session cookie qua HTTP thực. Không tự coi thiếu cookie `XSRF-TOKEN` là lỗi của **WebSession repo**, vì nó không dùng cookie đó mặc định.

### Lỗi C — Có cookie `XSRF-TOKEN` nhưng không có CSRF header

**Kết quả kỳ vọng:** POST state-changing phải bị chặn. Browser tự gửi cookie CSRF không đủ. Nếu vẫn thành công, kiểm tra CSRF có bị disable, selected chain sai hoặc test client đã áp `mutateWith(csrf())`.

### Lỗi D — Cookie và header raw giống nhau nhưng 403

**Thường do:** `CookieServerCsrfTokenRepository` đã phát raw cookie, nhưng request handler mặc định `XorServerCsrfTokenRequestAttributeHandler` đang chờ masked token. Test `GET /csrf` với exposed token để chứng minh masked flow hoạt động, sau đó chọn handler raw/hybrid có security review nếu SPA phải dùng raw header.

### Lỗi E — Cookie token bị mất trên route `/api/**`

**Kiểm tra:** `Path` của cookie có bao phủ route không? `Domain` host-only vs parent domain? Proxy có rewrite prefix hoặc chuyển host/scheme? Browser có chặn cookie `SameSite`/`Secure` theo context không?

**Cách sửa:** so sánh public `Set-Cookie` và HTTP Request Cookies trong browser DevTools; test HTTPS staging. Đừng tùy tiện mở `Domain=.example.com` cho mọi subdomain.

### Lỗi F — JS không đọc được cookie CSRF

**Khả năng:** `HttpOnly=true` trên cookie CSRF; frontend và API ở hai origins khác nhau; cookie là host-only cho api.example.com; hoặc browser đang chặn third-party access.

**Cách xử lý:** nếu thật sự phải đọc cookie same-origin, dùng `withHttpOnlyFalse()` **chỉ cho CSRF cookie**. Khi khác origin, cân nhắc `GET /csrf` JSON/CORS allowlist, BFF/proxy cùng origin hoặc thay kiến trúc. Không hạ `HttpOnly` của session authentication cookie.

### Lỗi G — Token S1 gửi cùng session S2 vẫn được chấp nhận

Đây là **vấn đề cần xác định loại repo trước khi kết luận**:

- **WebSession repo:** cần điều tra ngay: hai sessions có thực sự khác nhau? Test có dùng `csrf()` bỏ qua? Repo có lưu token chung ngoài ý định? Chain có CSRF?
- **Cookie repo:** expected token lấy từ cookie, **không ràng buộc server-side session như WebSession repo**. Nếu client copy nguyên cookie CSRF/token và gửi header hợp lệ, token match có thể được chấp nhận ở tầng CSRF; authentication/authorization vẫn phải kiểm tra riêng.

Nếu threat model yêu cầu CSRF token mật mã gắn với session, cần repo/handler thiết kế phù hợp, không suy tính chất ấy từ cookie repository mặc định.

### Lỗi H — `mutateWith(csrf())` pass nhưng test raw cookie/header fail

Helper hỗ trợ mock condition hợp lệ; nó không bảo đảm browser đã gửi cookie/header thật. Chạy bộ test 9.4–9.8, so repository raw vs handler masked, và xem `Set-Cookie`/Request Cookie ở public network. Không tắt `csrf` vì helper pass.

### Lỗi I — Token đổi giữa hai GET, tưởng repository bị lỗi

XOR handler có randomness nên **exposed masked token** có thể thay đổi giữa hai GET. Để kiểm tra repository có giữ expected raw token, dùng direct repo test hoặc gửi cả hai exposed tokens với cùng cookie/session. Không assert token JSON bằng nhau như thuộc tính bắt buộc.

### Lỗi J — Sau login/logout POST bị 403

Token/session có thể đã được xóa hoặc rotate, cookie mới chưa tới client hoặc SPA đang dùng token cũ. Test authentication và token bootstrap lại sau login/logout bằng HTTP client có cookie jar. `mockUser()` không mô phỏng toàn authentication success/logout lifecycle.

### Lỗi K — `@WebFluxTest` xanh nhưng `@SpringBootTest` đỏ

Test slice có thể thiếu custom chain, `ServerCsrfTokenRepository`, `ServerCsrfTokenRequestHandler`, CORS hoặc authentication beans. Import đúng config hoặc test full context; không sửa bằng cách disable CSRF toàn app.

### Lỗi L — `WebTestClient.bindToServer()` không nhận `csrf()`

`SecurityMockServerConfigurers.csrf()` là configurer cho **mock handler builder**, không tự chuyển token qua TCP. Với HTTP server thật, GET bootstrap và gửi cookie/header/form token như browser. `@WithMockUser` ở test thread cũng không tự xác thực request network.

### Lỗi M — 401/403 do JWT, authz hoặc CSRF?

Để chẩn đoán, dùng:

1. GET private không Bearer/session để kiểm tra authentication entry point (thường 401/redirect).
2. GET private có USER nhưng thiếu role để kiểm tra authorization (thường 403).
3. POST private có principal đủ quyền nhưng thiếu CSRF token để kiểm tra CsrfWebFilter (thường 403).
4. POST cùng principal với actual token đúng để làm positive control.

Đừng suy nguyên nhân chỉ từ HTTP status 403.

### Lỗi N — CORS OPTIONS bị 401 nhưng GET cùng origin OK

**Kiểm tra:** nguồn CORS Reactive có được xử lý trước authentication, đúng origin/method/header và chain matcher có match OPTIONS? Đừng thêm `csrf()` vào OPTIONS hoặc chỉ thêm `permitAll()` mà quên `Access-Control-Allow-*`.

### Lỗi O — Cookie CSRF tồn tại nhưng Browser không gửi ở HTTPS public

Kiểm tra `Secure`, `SameSite`, `Domain`, `Path`, host, scheme, redirect, proxy trust, third-party cookie restrictions. Mock WebTestClient không áp đầy đủ browser cookie rules; xác minh với Chrome/Firefox E2E ở public origin.

### Lỗi P — Production tạo được token nhưng không xóa được sau logout

Kiểm tra `saveToken(exchange, null)`/logout handlers và cookie delete scope. Một cookie delete dùng `Path`/`Domain` khác cookie gốc có thể không xóa đúng cookie của browser. Đo với cookie jar thật; không mặc định logout thành công chỉ vì response 302.

## 19. Ma trận regression tests để đối chiếu hai repositories

| ID | Tình huống | WebSession repository | Cookie repository |
| --- | --- | --- | --- |
| T01 | GET `/csrf` bootstrap | `SESSION` + exposed token | `XSRF-TOKEN` + exposed token |
| T02 | GET không consume token | Không đòi token mới được lưu | Không đòi XSRF cookie được phát |
| T03 | POST authenticated, không actual token | 403 | 403 |
| T04 | POST đúng token, cookie/session đúng | Được đi tiếp | Được đi tiếp |
| T05 | POST sai actual header | 403 | 403 |
| T06 | POST sai tên header | 403 | 403 |
| T07 | Expected state không được gửi | Không `SESSION` -> không nạp S1 | Không `XSRF-TOKEN` -> không nạp raw expected |
| T08 | Token T1 dùng với WebSession S2 | **Phải bị chặn** khi sessions độc lập | Không cùng semantics ràng buộc WebSession |
| T09 | Raw cookie value gửi vào default XOR handler | Không phải flow mặc định của repo | Thường 403 theo fixture XOR |
| T10 | Masked exposed token từ GET | Accepted với đúng WebSession | Accepted với đúng raw cookie |
| T11 | Raw cookie header với handler SPA hỗ trợ raw | Không cần nếu dùng JSON bootstrap | Accepted khi handler đã được cấu hình |
| T12 | Cookie CSRF `HttpOnly` | Không áp vì token nằm server-side | False nếu JS phải đọc, True nếu không |
| T13 | Cookie `Secure/SameSite/Path` | Session cookie manager/HTTP layer | Cookie repo/customizer/HTTP layer |
| T14 | Login/logout token lifecycle | Phụ thuộc session + strategies | Phụ thuộc cookie + strategies, không tự session-bound |
| T15 | CORS preflight OPTIONS | Theo CORS source | Theo CORS source |
| T16 | Raw JWT invalid | Authentication, không phải repo | Authentication, không phải repo |
| T17 | HTTPS public CSP/HSTS | Kiểm tra riêng | Kiểm tra riêng |
| T18 | Firewall reject URL bất thường | Kiểm tra riêng | Kiểm tra riêng |
| T19 | Multi-chain `/spa/**` và fallback | Đúng selected chain | Đúng selected chain |
| T20 | Request đổi replica/pod | Shared WebSession/token store | Cookie CSRF đi cùng client, auth session vẫn cần consistent store |

### 19.1. Bộ kiểm thử tối thiểu bắt buộc

Với **mỗi repo mà dự án dùng**, tối thiểu nên có:

1. Test bootstrap phát token theo contract.
2. Test POST thiếu token bị 403 và handler không chạy.
3. Test POST token sai bị 403.
4. Test POST token đúng với expected cookie/session được xử lý.
5. Test cookie/session expected state không có thì actual token cũ không đủ.
6. Test account/session lifecycle sau login/logout nếu application có browser authentication.

Với **cookie SPA**, bổ sung raw-vs-XOR test, cookie flags, browser same-origin/cross-origin và header CORS. Với **WebSession**, bổ sung S1/T1 vs S2/T2 và session store/replica tests.

### 19.2. Test nào không nên được gộp?

Không trộn:

- POST token sai + URL semicolon bất thường (firewall có thể chặn trước CSRF).
- POST token sai + user thiếu quyền (authorization cũng 403).
- OPTIONS preflight + `csrf()` (OPTIONS không cần CSRF theo default matcher).
- `mockJwt()` + assertion chữ ký JWT sai (mock bỏ qua decoder thực).
- Cookie flags in-memory + khẳng định Chrome đã gửi cookie (browser policy không được mô phỏng).
- Cookie repo token T1/S2 + kỳ vọng WebSession-binding không có trong contract.

Test dễ chẩn đoán nhất là test thay **một yếu tố** mỗi lần và có positive control tương ứng.

## 20. Bài tập thực hành

### Bài 1 — Xác định repository thực tế

Tạo WebFlux application có `SecurityWebFilterChain` bật CSRF và `GET /csrf` endpoint. Trong cấu hình thứ nhất không khai báo `csrfTokenRepository`; chạy bootstrap và xác định nơi expected token được lưu. Viết bảng phân biệt session cookie `SESSION` với CSRF cookie `XSRF-TOKEN`. Giải thích vì sao GET bất kỳ không consume token có thể chưa phát cookie.

### Bài 2 — WebSession repository: token gắn session

Với `WebSessionServerCsrfTokenRepository`, bootstrap hai sessions S1/T1 và S2/T2. Viết tests POST: S1/T1 được xử lý, S1/T2 bị chặn, S2/T1 bị chặn, S2/T2 được xử lý. Không sử dụng `mutateWith(csrf())` trong bốn requests này. Thêm assertion controller không tạo order khi request sai token.

### Bài 3 — Cookie repository: không có header thì không đủ

Bật `CookieServerCsrfTokenRepository.withHttpOnlyFalse()`. GET `/csrf` và lấy `XSRF-TOKEN`. Viết POST chỉ có cookie, không header, kỳ vọng 403. Sau đó POST cùng raw cookie nhưng header mang exposed masked token hợp lệ, kỳ vọng thành công. Giải thích vì sao cookie được tự đính kèm không tự chống CSRF.

### Bài 4 — Raw vs XOR-masked

Giữ default XOR handler, thử POST với `X-XSRF-TOKEN` mang raw value của cookie. Quan sát 403 trong fixture. Thêm `SpaRawHeaderCsrfRequestHandler` của mục 10, chạy lại và thử cả negative raw header sai. Vì sao không nên vô hiệu BREACH masking trên mọi response chỉ để SPA gửi raw token?

### Bài 5 — Kiểm tra trực tiếp `generateToken/saveToken/loadToken`

Viết hai JUnit tests dùng `MockServerWebExchange` và `StepVerifier`: một test repo WebSession save/load trong exchange, một test repo cookie phát `Set-Cookie` rồi load token từ cookie ở exchange khác. Viết rõ giới hạn: hai tests chỉ kiểm tra repository **raw persistence**, chưa xác nhận `CsrfWebFilter` hay request handler.

### Bài 6 — Cookie flags và HTML origin

Cấu hình cookie CSRF `HttpOnly=false`, `Secure=true`, `SameSite=Lax` và `Path=/`. Viết in-memory tests cho metadata, sau đó dùng browser staging HTTPS để kiểm tra cookie có được gửi trên path public không. So sánh với session authentication cookie (vẫn phải `HttpOnly=true`).

### Bài 7 — CORS và cross-origin cookie

SPA chạy tại `https://app.example.com`, API tại `https://api.example.com`. Dùng cookie repository phát host-only cookie cho API. Giải thích tại sao JS của SPA không đọc được cookie đó qua `document.cookie`, dù fetch/CORS đúng. Đề xuất JSON token bootstrap có CORS allowlist hoặc BFF cùng origin, rồi kiểm tra preflight OPTIONS và POST thật.

### Bài 8 — Login/logout và hai repositories

Với form login/session thực, viết kịch bản bootstrap token, login, bootstrap lại, logout và thử token cũ. So sánh:

- WebSession repo: expected token gắn với session store.
- Cookie repo: expected token lấy từ CSRF cookie; không tự giả định có session binding.

Định nghĩa tiêu chí sau logout: request cũ không được thực thi side effect, và session authentication phải mất hiệu lực.

### Bài 9 — Nhiều security chains

Tạo `/spa/**` chain dùng cookie repo + raw-header handler và fallback chain dùng WebSession repo. Lấy token ở `GET /csrf` (fallback) rồi cố dùng cho `POST /spa/orders`; dự kiến thất bại vì repository/chain khác. Viết test bootstrap tương ứng `GET /spa/csrf` rồi POST thành công.

### Bài 10 — Rolling deploy và session store

Hai pods chạy chung Redis/Spring Session. Login và cấp token từ pod A, gửi request protected từ pod B, sau đó đảo chiều. Nâng Spring Boot/Security theo canary, thử compatibility session serialization, logout và rollback. Cookie repo có giải quyết tất cả vấn đề shared session không? Giải thích vì sao authentication session vẫn cần lưu và đồng bộ.

### Bài 11 — Phân biệt các lỗi có cùng status

Tạo ba tests 403 riêng:

- USER gọi `GET /admin/report` thiếu `ROLE_ADMIN`.
- USER gọi `POST /orders` nhưng thiếu CSRF.
- CORS preflight origin không được phép.

Giải thích cách loại trừ từng nguyên nhân bằng positive control, method, origin headers và selected chain. Không coi mọi 403 là token repository failure.

### Bài 12 — E2E qua HTTPS/reverse proxy

Chạy kiểm thử được ủy quyền trên staging. Ghi lại public URL, cookies (không ghi giá trị nhạy cảm), `Set-Cookie` flags, `Origin`/`Access-Control-Allow-*`, CSP và HSTS, rồi kiểm tra POST không token/sai/đúng. So sánh với kết quả mock WebTestClient để phát hiện proxy rewrite, cookie Path hoặc TLS termination gây khác biệt.

## 21. Checklist review khi chọn hoặc đổi CSRF repository

- [ ] Xác định use case browser session, SSR/form login, SPA cookie hoặc Bearer-only API theo threat model.
- [ ] Đang dùng đúng **Reactive `ServerCsrfTokenRepository`**, không import Servlet `CsrfTokenRepository`.
- [ ] Xác nhận phiên bản Spring Security, Spring Framework, Boot và `spring-security-test` đã resolve; không trộn BOM.
- [ ] Có một `SecurityWebFilterChain` được chọn đúng cho endpoint bootstrap và unsafe POST.
- [ ] CSRF bật trong browser chain; nếu API khác miễn CSRF thì có matcher hẹp và fallback rõ ràng.
- [ ] Chỉ sử dụng **một** repo/handler được chủ đích cấu hình trên mỗi chain; tránh bean/matcher xung đột.
- [ ] `GET /csrf` hoặc view thực sự consume `Mono<CsrfToken>`, có `Cache-Control: no-store` và không log token.
- [ ] Test `csrf()` positive không được xem là bằng chứng repository lưu và so khớp actual token.
- [ ] WebSession repo: giữ `SESSION` cookie qua bootstrap/POST, assert token T1/S1 hợp lệ và T1/S2 không hợp lệ.
- [ ] Cookie repo: assert `Set-Cookie: XSRF-TOKEN` và POST thiếu cookie/header bị từ chối.
- [ ] Cookie repo: kiểm tra raw cookie + masked exposed header với default XOR handler.
- [ ] Nếu SPA gửi raw `X-XSRF-TOKEN`, có request handler tương thích được review và tests âm/dương.
- [ ] Không tắt XOR/BREACH masking chỉ vì một test raw header 403; hiểu rõ tradeoff.
- [ ] Repo unit tests kiểm tra generate/save/load và delete, nhưng vẫn có integration tests với `CsrfWebFilter` thật.
- [ ] `HttpOnly=false` chỉ dùng cho CSRF cookie khi JavaScript phải đọc; authentication cookie vẫn bảo vệ.
- [ ] Cookie `Secure`/`SameSite`/`Path`/`Domain` theo public origin và test browser/HTTPS thực.
- [ ] Host-only cookie ở API origin không được giả định JavaScript ở SPA origin khác có thể đọc.
- [ ] CORS preflight OPTIONS được kiểm tra riêng, không dùng `csrf()` để bypass và không cấp allow-origin cho origin lạ.
- [ ] `Content-Security-Policy` của HTML, HSTS qua HTTPS, nosniff và firewall có regression tests độc lập.
- [ ] Login/logout và token/session lifecycle được test với authentication thật, không chỉ `mockUser()`.
- [ ] Cookie repo không bị gán nhầm đặc tính mật mã ràng buộc session của WebSession repo.
- [ ] Có test POST không token/sai token **không chạy side effect** ở service/repository.
- [ ] `@WebFluxTest` đã import custom security config và test repo/handler; có full-context tests khi phù hợp.
- [ ] HTTP server thật dùng token/cookie/credential HTTP thật, không dùng mock `csrf()` hoặc `@WithMockUser` để thay authentication qua TCP.
- [ ] Multi-node/rolling deploy được kiểm tra với shared session store, cookie scope và compatibility.
- [ ] Không xuất CSRF token, session ID, JWT, password thật ra CI logs, tracing hoặc tài liệu.

## 22. Nguồn tham khảo và Javadoc chính thức

1. [Spring Security — Cross-Site Request Forgery for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — repo mặc định WebSession, cookie repo, request handler, BREACH và token trong header/form.
2. [Spring Security 7.0 — Reactive CSRF (pinned)](https://docs.spring.io/spring-security/reference/7.0/reactive/exploits/csrf.html) — tham chiếu phân biệt dòng 6/7, ví dụ cookie `withHttpOnlyFalse()` và XOR handler.
3. [Spring Security API — ServerCsrfTokenRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html) — contract `generateToken`, `saveToken`, `loadToken`, `saveToken(null)`.
4. [Spring Security API — WebSessionServerCsrfTokenRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html) — WebSession attribute, header/parameter customization.
5. [Spring Security API — CookieServerCsrfTokenRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html) — `XSRF-TOKEN`, `X-XSRF-TOKEN`, `withHttpOnlyFalse()`, `setCookieCustomizer` (6.1+).
6. [Spring Security API — CsrfWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html) — synchronizer token, default matcher, exchange attribute.
7. [Spring Security API — ServerCsrfTokenRequestHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestHandler.html) — `handle` và `resolveCsrfTokenValue`.
8. [Spring Security API — XorServerCsrfTokenRequestAttributeHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html) — masking và raw token resolution.
9. [Spring Security API — ServerCsrfTokenRequestAttributeHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html) — unmasked handler và form/header parsing.
10. [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) và [Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — `springSecurity()`, `csrf()` mutator và giới hạn mock tests.
11. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — preflight, origin và credentials.
12. [Spring Security — Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html), [Reactive HTTP Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — các lớp HTTP protection khác.
13. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`/`ServerHttpSecurity`, multi-chain matcher.
14. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — application context mock client, server binding và assertions.
15. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`, `@SpringBootTest` và version-specific test setup.
16. [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — synchronizer tokens, double-submit cookies, signed/session-bound tokens, SameSite và defense in depth.

**Câu hỏi tự đánh giá:** Repository lưu expected token, còn request handler giải mã actual token là khác nhau thế nào? Vì sao `csrf()` positive test không đủ để đánh giá repository? WebSession repository có ràng buộc token với session ra sao, và cookie repository có đặc tính ấy không? Trong cookie SPA, tại sao raw `XSRF-TOKEN` có thể không được default XOR handler chấp nhận? Làm thế nào test rằng cookie được phát nhưng header thiếu vẫn 403? Khi nào `HttpOnly=false` là lựa chọn có chủ đích và nó khác việc lộ authentication cookie ra sao? Nếu test qua mock context pass nhưng SPA khác origin vẫn 403, bạn sẽ xác minh cookie scope, CORS, SameSite và HTTPS theo thứ tự nào? Cuối cùng, khi nào một thay đổi repository cần dừng phát hành và review lại threat model?
