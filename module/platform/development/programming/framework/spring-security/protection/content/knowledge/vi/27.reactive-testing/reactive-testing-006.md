# Kiểm tra việc lấy `Mono<CsrfToken>` và vòng đời session

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Định hướng:** Áp dụng và kiểm thử các lớp phòng vệ HTTP/trình duyệt của Spring Security, từ CSRF và session đến CORS, headers, CSP, HSTS, firewall trên Servlet và Reactive; **bài này tập trung riêng vào WebFlux**.  
> **Mục tiêu:** Hiểu cách `CsrfWebFilter` expose `Mono<CsrfToken>` qua `ServerWebExchange`, khi nào token được sinh/lưu do subscription, cách `WebSession` được bắt đầu, đổi ID, hết hạn hoặc bị vô hiệu hóa, và cách chứng minh các hành vi bằng `WebTestClient`.  
> **Phiên bản tham chiếu:** Spring Security 6.5/7.x, Spring Framework WebFlux, Spring Boot 3.5/4.x, Java 17+, JUnit 5 và `spring-security-test`. Những APIs chỉ dành cho Servlet được phân biệt rõ.

## 1. Vấn đề thực tế: vì sao GET có token nhưng POST vẫn 403?

Một SPA hoặc form-based application đăng nhập bằng cookie session. Lần đầu tải giao diện, nó gọi `GET /csrf` lấy một token rồi POST tạo đơn:

```text
Browser / WebTestClient
    |
    | GET /csrf
    v
CsrfWebFilter exposes Mono<CsrfToken>
    |
    | Controller tiêu thụ Mono
    v
WebSessionServerCsrfTokenRepository
    |-- tạo expected token T1 (nếu chưa có)
    |-- lưu vào WebSession S1
    |
    +--> Response body: token đã được handler expose M1
    +--> Set-Cookie: SESSION=<session-id-S1>
                       |
                       v
Browser gửi POST /orders:
  Cookie: SESSION=<session-id-S1>
  X-CSRF-TOKEN: <token-M1>
                       |
                       v
CsrfWebFilter nạp expected T1, resolve actual M1
    |-- hợp lệ: request đến authorization/handler
    +-- thiếu/sai/cookie khác: thường 403
```

Trong thực tế, có ba lỗi khác nhau thường bị gộp thành “CSRF không hoạt động”:

1. **Token publisher không được tiêu thụ:** controller/view đọc attribute nhưng không subscribe `Mono<CsrfToken>`; token có thể chưa được generate/save, nên GET không tạo session cookie như kỳ vọng.
2. **Session không được duy trì:** GET tạo session S1, nhưng POST không gửi `SESSION` cookie hoặc cookie bị browser/proxy từ chối; repository không thể nạp expected token của S1.
3. **Token bị thay đổi hoặc hết hiệu lực:** login/logout, session invalidation, timeout hoặc request handler XOR làm exposed token khác raw expected token.

Chỉ có `client.mutateWith(csrf()).post(...).expectStatus().isOk()` **không chứng minh** ba điểm trên: đây là helper của mock Security test, không phải browser token lifecycle. Bài này tập trung vào việc kiểm thử **Mono → WebSession → cookie → request tiếp theo** một cách tường minh.

### 1.1. Sau bài này, người học có thể

1. Truy xuất `Mono<CsrfToken>` bằng đúng key từ `ServerWebExchange`, không dùng nhầm Servlet `HttpServletRequest`.
2. Tiêu thụ publisher trong controller, `@ControllerAdvice` hoặc view mà không gọi `block()` trên event loop.
3. Phân biệt hành vi `getSession()`, `WebSession.start()`, `getAttributes().put(...)`, `save()`, `changeSessionId()` và `invalidate()`.
4. Viết kiểm thử GET bootstrap thực sự làm phát token và session cookie; dùng lại cookie/token trên POST.
5. Viết negative tests: không session, session khác, sai token, token cũ sau invalidation, cookie hết hạn, logout.
6. Tách kiểm thử `csrf()` mutator khỏi việc xác minh token thật, đồng thời giữ authentication/authorization không gây nhiễu.
7. Hiểu `XorServerCsrfTokenRequestAttributeHandler`, giá trị raw/masked, deferred loading, session fixation và cookie repository khác WebSession.
8. Lập ma trận hồi quy trong mock WebTestClient, HTTP server thật và browser/HTTPS staging.

## 2. Bốn đối tượng chính, bốn nhiệm vụ riêng

| Đối tượng | API | Trách nhiệm | Khi nào phải test riêng? |
| --- | --- | --- | --- |
| CSRF filter | `org.springframework.security.web.server.csrf.CsrfWebFilter` | Đặt token publisher vào exchange; kiểm tra unsafe requests | Có CSRF chain không, POST thiếu token có bị chặn không |
| Repository | `ServerCsrfTokenRepository` | `generateToken`, `saveToken`, `loadToken` expected token | Token được lưu vào đúng WebSession, nạp lại request sau |
| Request handler | `ServerCsrfTokenRequestHandler` | Expose token cho view/controller và resolve actual token từ header/form | Token raw hay XOR-masked, header/parameter được chấp nhận |
| Web session | `org.springframework.web.server.WebSession` | Quản lý id, attributes, max idle, started/expired/invalidate | Cookie `SESSION`, session continuity và lifetime |

### 2.1. Request attribute chứa **Mono**, không phải luôn chứa `CsrfToken` trực tiếp

Javadoc chính thức ghi:

```java
Mono<CsrfToken> csrfToken =
    exchange.getAttribute(CsrfToken.class.getName());
```

Khóa attribute là tên đầy đủ của class `org.springframework.security.web.server.csrf.CsrfToken`, không phải chuỗi `"_csrf"` và không phải Servlet `CsrfToken.class.getName()` dưới package `org.springframework.security.web.csrf`. View có thể dùng model attribute `_csrf` qua integration, nhưng đó là **tên được expose cho template**, không phải cùng key bắt buộc trong `ServerWebExchange.getAttributes()`.

Trong Reactive, không làm:

```java
// Sai: getAttribute trả Mono<CsrfToken>, không phải CsrfToken trực tiếp.
CsrfToken wrong = exchange.getAttribute(CsrfToken.class.getName());

// Sai cho request handler WebFlux: block() trên event-loop.
CsrfToken blocking = csrfMono.block();
```

Thay vào đó, **return publisher** hoặc compose bằng `map`/`flatMap` và để WebFlux subscribe ở ranh giới HTTP.

### 2.2. `ServerCsrfTokenRepository` và `WebSession` không phải một

Repository mặc định trong WebFlux là `WebSessionServerCsrfTokenRepository`. Nó lưu expected token vào **session attributes**; cookie `SESSION` chỉ mang **session ID**, không phải expected token raw. Chính request browser phải gửi session cookie cùng actual token trong header/form.

```text
WebSession S1: { ... , expected-CsrfToken: raw-T1 }
       ^
       | lookup bằng SESSION cookie
       |
Request Cookie: SESSION=opaque-S1-id
Request Header: X-CSRF-TOKEN=exposed-token-M1
```

Giữa hai requests, nếu client **không** trả cookie S1, WebSession repository không có expected token T1 để so. Không dùng một global variable/static token để giả lập storage rồi coi là integration test.

### 2.3. Session cookie khác CSRF cookie

`CookieServerCsrfTokenRepository` là cấu hình **tùy chọn** khi SPA muốn JavaScript đọc cookie `XSRF-TOKEN`. Nó không sử dụng WebSession làm chỗ lưu expected CSRF token giống repository mặc định.

| Tiêu chí | WebSession repository | Cookie repository |
| --- | --- | --- |
| Expected CSRF token | Server-side WebSession attributes | Cookie `XSRF-TOKEN` từ client |
| Cookie cần giữ | `SESSION`, mặc định phổ biến | `XSRF-TOKEN`; có thể còn `SESSION` cho authentication |
| Token từ browser gửi lại | Header `X-CSRF-TOKEN` hoặc form parameter `_csrf` | Header `X-XSRF-TOKEN` hoặc `_csrf` |
| Session-binding | Token gắn với đúng WebSession | Không tự có đặc tính token gắn server-side WebSession |
| SPA JS đọc cookie? | Không bắt buộc; GET token endpoint là lựa chọn | Có thể phải đọc `XSRF-TOKEN` nếu chọn flow raw-cookie |

Bài này dùng repository **WebSession mặc định** để kiểm tra vòng đời session, rồi đối chiếu cookie repository nhằm tránh kết luận sai từ một trường hợp khác kiến trúc.

## 3. Ngữ nghĩa Reactive: deferred, lazy và subscription

### 3.1. Gọi `getAttribute` không làm token được subscribe

Hãy phân biệt “đã có đối tượng publisher” và “đã thực sự tiêu thụ nó”:

```java
@GetMapping("/wrong")
public Mono<String> wrong(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
        exchange.getAttribute(CsrfToken.class.getName());

    // Chỉ lấy reference, không compose/subcribe token.
    return Mono.just("ok");
}

@GetMapping("/csrf")
public Mono<CsrfToken> right(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
        exchange.getAttribute(CsrfToken.class.getName());

    if (token == null) {
        return Mono.error(
            new IllegalStateException("CSRF filter not active"));
    }

    // Framework subscribe vào publisher được return.
    return token;
}
```

Đoạn `right` minh họa nguyên lý, **không** nên expose trực tiếp token object như API production tùy tiện. Ở phần fixture, ta trả một JSON envelope tối thiểu và áp `Cache-Control: no-store`. Đừng log token, đừng nhét nó vào URL query string hoặc analytics/tracing.

### 3.2. `doOnNext` chỉ chạy khi có subscription

```java
Mono<CsrfToken> tokenMono =
    exchange.getAttribute(CsrfToken.class.getName());

if (tokenMono != null) {
    Mono<CsrfToken> withTrace = tokenMono.doOnNext(token -> {
        // Chỉ ghi thông tin sự kiện, KHÔNG ghi token.getToken().
        incrementCsrfBootstrapMetric();
    });

    // withTrace cũng chưa chạy cho đến khi được subscribe.
}
```

`incrementCsrfBootstrapMetric` là pseudocode đo số lần bootstrap, không phải API Spring. **Không gọi `subscribe()` thủ công** trong handler để “ép token được tạo”: điều đó tạo side effect ngoài luồng response, khó quản lý lỗi và thời điểm save. Hãy compose publisher và return nó.

### 3.3. Token mới được save khi Mono thực sự được tiêu thụ

Spring Security ghi nhận trong Javadoc `CsrfWebFilter` rằng nếu token mới được tạo, nó được tự lưu khi `Mono<CsrfToken>` được subscribe. Điều này giúp giảm việc tạo session cho những GET không render token.

```text
GET /public/ping:
  CsrfWebFilter đặt Mono<CsrfToken> vào exchange
  controller không tiêu thụ Mono
  -> không nên giả định session được tạo chỉ do CSRF

GET /csrf:
  controller tiêu thụ Mono<CsrfToken>
  -> repository load hoặc generate + save
  -> WebSession attributes có expected token
  -> WebSession có thể bắt đầu và phát session cookie
```

Một số application có filter/controller khác tự tạo session (authentication, `WebSession.start()`), nên test “GET public không có `SESSION`” chỉ đúng nếu fixture đã loại bỏ các thành phần tạo session khác.

### 3.4. WebSession được tạo khác với WebSession **started**

Javadoc `WebSession` nêu rõ: việc tạo một instance `WebSession` không tự bắt đầu session và không bảo đảm gửi session id cho client. Session bắt đầu khi:

- Gọi `session.start()` một cách tường minh; hoặc
- Có session attribute được thêm, ví dụ `session.getAttributes().put("key", value)`.

Để session được lưu/gửi cookie, WebFlux session manager/store còn phải thực hiện `save()` tại giai đoạn phù hợp, thường khi response commit. **Đừng giả định chỉ gọi `exchange.getSession()` là đủ**:

```java
// GET session object, chưa chắc started:
Mono<WebSession> access = exchange.getSession();

// Explicitly start, nếu thực sự cần một session:
Mono<Void> started = exchange.getSession()
    .doOnNext(WebSession::start)
    .then();
```

Trong ví dụ này, `access`/`started` cũng là publishers. Nếu không return/compose và không được subscribe, vẫn không có hiệu ứng. Không tạo session trên mọi GET chỉ để chữa một test CSRF; chỉ bootstrap khi client thực sự cần token.

### 3.5. Token raw và token expose khác nhau do XOR masking

Spring Security 5.8 dùng `ServerCsrfTokenRequestAttributeHandler` mặc định; từ 6.0, WebFlux dùng `XorServerCsrfTokenRequestAttributeHandler` để giảm nguy cơ BREACH. Token mà controller trả về từ `CsrfToken.getToken()` có thể đã masked:

```text
WebSession expected raw token = R1
   |
   +--> GET /csrf #1: exposed masked M1
   +--> GET /csrf #2: exposed masked M2

M1 có thể khác M2 ngay cả khi R1 chưa rotate.
POST cùng session S1, header chứa M1 hoặc M2:
  handler giải mã -> raw R1 -> có thể hợp lệ
```

Không assert hai chuỗi token JSON bằng nhau để chứng minh repository lưu đúng. Hãy dùng **round-trip qua request handler** hoặc test `ServerCsrfTokenRepository.loadToken` trực tiếp để kiểm tra raw expected token.

## 4. Thiết lập một WebFlux test fixture có thể tái sử dụng

Mỗi test cần đi qua cùng Security WebFilters và endpoint thực. Fixture dưới đây không phụ thuộc database hoặc identity provider: nó có controller, một bộ đếm side effect, Security chain và user store **chỉ dùng cho tests**. Nó dùng WebSession repository mặc định.

### 4.1. Gradle và Maven

Với Spring Boot quản lý versions:

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

Maven:

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

Spring Boot 4 có test starters tách theo web stack; chọn dependency/annotation package đúng BOM hiện tại. Không tự ép Spring Security 7 lên một Boot/Framework không tương thích. Trong bài này chúng ta **không chạy build**; người học có thể xác nhận resolved versions trên dự án:

```bash
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Trên Windows dùng `gradlew.bat`/`mvnw.cmd`. Các dependency/runtime starters đã có trong dự án thì không cần khai báo trùng.

### 4.2. Controller có endpoint **không tiêu thụ token** và endpoint **có tiêu thụ token**

```java
package com.example.reactivelifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

final class OrderCounter {
    private final AtomicInteger value = new AtomicInteger();

    int get() { return value.get(); }
    void reset() { value.set(0); }
    void record() { value.incrementAndGet(); }
}

@RestController
public class SessionCsrfController {

    public record CsrfEnvelope(
        String headerName, String parameterName, String token
    ) {}

    private final OrderCounter counter;

    public SessionCsrfController(OrderCounter counter) {
        this.counter = counter;
    }

    // Không đọc CSRF token; GET này phải giữ semantics read-only.
    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    // Cố ý lấy reference nhưng KHÔNG subscribe token.
    @GetMapping("/public/unused-token")
    public Mono<String> unusedToken(ServerWebExchange exchange) {
        Mono<CsrfToken> unused =
            exchange.getAttribute(CsrfToken.class.getName());
        return Mono.just("read-only");
    }

    // Token bootstrap: framework subscribe khi write JSON response.
    @GetMapping("/csrf")
    public Mono<ResponseEntity<CsrfEnvelope>> csrf(
            ServerWebExchange exchange) {
        Mono<CsrfToken> source =
            exchange.getAttribute(CsrfToken.class.getName());

        if (source == null) {
            return Mono.error(new IllegalStateException(
                "CsrfWebFilter did not expose token"
            ));
        }

        return source.map(token ->
            ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new CsrfEnvelope(
                    token.getHeaderName(),
                    token.getParameterName(),
                    token.getToken()
                ))
        );
    }

    @PostMapping("/orders")
    public Mono<String> order() {
        return Mono.fromSupplier(() -> {
            counter.record();
            return "created";
        });
    }

    // TEST-ONLY route: minh họa explicit session.start()
    @GetMapping("/test/session/start")
    public Mono<String> startSession(ServerWebExchange exchange) {
        return exchange.getSession()
            .doOnNext(WebSession::start)
            .thenReturn("started");
    }

    // TEST-ONLY route: invalidation thuộc cùng session request.
    @PostMapping("/test/session/invalidate")
    public Mono<String> invalidateSession(ServerWebExchange exchange) {
        return exchange.getSession()
            .flatMap(WebSession::invalidate)
            .thenReturn("invalidated");
    }
}
```

Mặc dù dùng từ “test”, hai route `/test/session/**` vẫn **làm thay đổi trạng thái session**. Chỉ đăng ký chúng trong fixture/test profile, không expose trong production. Trong một ứng dụng thật, invalidation thường xảy ra qua logout handler với authentication, không nên tạo endpoint công khai chỉ để test.

`/public/unused-token` cố tình không sử dụng biến `unused` để thể hiện **không có subscription**. Trình biên dịch Java có thể cảnh báo unused local, nhưng đây là mẫu giảng dạy. Việc handler trả `Mono.just(...)` không subscribe `unused`, nên không suy token sẽ được lưu bởi endpoint này.

### 4.3. Security chain giữ CSRF bật

```java
package com.example.reactivelifecycle;

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
public class TestSecurityConfig {

    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/csrf").permitAll()
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password("{noop}testing-only")
                .roles("USER")
                .build()
        );
    }
}
```

`WebSessionServerCsrfTokenRepository` là default; không cần khai báo `csrfTokenRepository(...)` để dùng nó. Nếu muốn hiển thị lựa chọn tường minh:

```java
http.csrf(csrf -> csrf.csrfTokenRepository(
    new WebSessionServerCsrfTokenRepository()
));
```

Đây là **thay thế** `.csrf(Customizer.withDefaults())` trong chain, không đăng ký một chain khác. Password `{noop}` **chỉ dùng trong test fixture**, không bao giờ dùng production.

### 4.4. WebFlux infrastructure thuần Spring Test

```java
package com.example.reactivelifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class TestWebConfig {

    @Bean OrderCounter counter() {
        return new OrderCounter();
    }

    @Bean SessionCsrfController sessionCsrfController(
            OrderCounter counter) {
        return new SessionCsrfController(counter);
    }
}
```

`@EnableWebFlux` cung cấp WebFlux infrastructure cho context thuần Spring Test. Trong Spring Boot app đã auto-config WebFlux, không tự thêm annotation này một cách máy móc vì nó có thể thay đổi Boot WebFlux auto-config defaults.

### 4.5. Tạo `WebTestClient` tích hợp Security

```java
package com.example.reactivelifecycle;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    TestWebConfig.class,
    TestSecurityConfig.class
})
class WebSessionCsrfLifecycleTest {

    @Autowired ApplicationContext context;
    @Autowired OrderCounter counter;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        counter.reset();
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Các @Test và helpers ở những mục sau đặt trong class này.
}
```

Chúng ta sử dụng `bindToApplicationContext`, **không phải `bindToController`**, để mock WebFlux pipeline nạp Security WebFilters thật. `apply(springSecurity())` cho phép mutators `mockUser()/csrf()` hoạt động trong mock context. Mỗi request dùng `client.mutateWith(...)` để tránh rò principal giữa tests. `OrderCounter` là bean shared trong context, nên các tests này giả định chạy tuần tự; khi chạy JUnit song song cần cô lập counter/session fixtures.

## 5. Kiểm thử “token chưa được dùng” và “token đã được dùng”

### 5.1. GET không consume token không tự khởi động WebSession vì CSRF

Với fixture không có WebFilter/handler khác tạo session:

```java
@Test
void unusedCsrfPublisherDoesNotRequireSessionCookie() {
    client.get().uri("/public/unused-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().doesNotExist("Set-Cookie")
        .expectBody(String.class).isEqualTo("read-only");
}
```

**Điều test này chứng minh:** trong fixture đã chọn, chỉ lấy `Mono<CsrfToken>` từ exchange mà không consume không đủ để sinh/lưu token và phát session cookie. Nếu một Security/WebFilter component khác tạo session, `Set-Cookie` vẫn có thể xuất hiện và test cần điều chỉnh phạm vi kết luận.

### 5.2. GET bootstrap phải tiêu thụ `Mono<CsrfToken>`

```java
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

@Test
void consumingCsrfMonoCreatesExpectedSessionCookie() {
    EntityExchangeResult<SessionCsrfController.CsrfEnvelope> result =
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueMatches(
                "Cache-Control", ".*no-store.*")
            .expectBody(SessionCsrfController.CsrfEnvelope.class)
            .returnResult();

    var body = result.getResponseBody();
    assertNotNull(body);
    assertNotNull(body.headerName());
    assertNotNull(body.token());

    ResponseCookie session =
        result.getResponseCookies().getFirst("SESSION");
    assertNotNull(session, "Expected WebSession cookie");
    org.junit.jupiter.api.Assertions.assertFalse(
        session.getValue().isBlank());
}
```

Ở `WebSessionServerCsrfTokenRepository` default, khi token mới được sinh và lưu vào WebSession attributes, WebSession bắt đầu; ở WebFlux default cookie name phổ biến là `SESSION`. Test ứng dụng sử dụng Spring Session/custom `WebSessionIdResolver` có thể phải kiểm tra tên cookie khác.

### 5.3. So sánh `GET /public/ping` và `GET /csrf`

| Request | Có access `Mono<CsrfToken>`? | Có subscribe token? | Expectation trong fixture |
| --- | --- | --- | --- |
| `GET /public/ping` | CsrfWebFilter có thể expose | Controller không dùng | Không yêu cầu session mới chỉ vì CSRF |
| `GET /public/unused-token` | Controller lấy publisher | **Không** | Không yêu cầu session mới chỉ vì CSRF |
| `GET /csrf` | Controller lấy publisher | **Có**, qua response publisher | Token được generate/load, WebSession được lưu khi cần |
| `POST /orders` thiếu token | Filter phải resolve/validate | Có xử lý CSRF | Thường 403 trước controller |

Token cũng có thể được tiêu thụ bởi template, filter bổ sung hoặc `@ControllerAdvice`, vì vậy “không consume ở controller” chỉ đủ khi toàn pipeline không có subscriber khác. Hãy test trên đúng application context, không suy kết quả toàn hệ thống từ một handler lẻ.

## 6. Viết helper bootstrap và giữ session cookie đúng cách

Để kiểm tra session lifecycle, ta phải lấy token từ một HTTP exchange, rồi dùng **đúng cookie** của exchange ấy trong request tiếp theo. Không dựa vào một WebTestClient dùng `mutateWith(csrf())` chung cho mọi request.

### 6.1. Một record biểu diễn cặp session/token

Thêm vào `WebSessionCsrfLifecycleTest`:

```java
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

record SessionToken(
    String cookieName,
    String sessionId,
    String headerName,
    String parameterName,
    String exposedToken
) {}

SessionToken bootstrap() {
    EntityExchangeResult<SessionCsrfController.CsrfEnvelope> result =
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(SessionCsrfController.CsrfEnvelope.class)
            .returnResult();

    SessionCsrfController.CsrfEnvelope body =
        result.getResponseBody();
    assertNotNull(body);
    assertNotNull(body.token());
    assertNotNull(body.headerName());

    ResponseCookie sessionCookie =
        result.getResponseCookies().getFirst("SESSION");
    assertNotNull(sessionCookie);

    return new SessionToken(
        sessionCookie.getName(),
        sessionCookie.getValue(),
        body.headerName(),
        body.parameterName(),
        body.token()
    );
}
```

Session ID và CSRF token là hai **secret-bearing values**: không ghi chúng vào logs, reports hoặc error messages trong CI. Không gọi `System.out.println(token.exposedToken())`. Trong response HTTP thật, `Set-Cookie` phải có flags thích hợp (`Secure`/`HttpOnly`/`SameSite`), được xác minh ở browser staging.

### 6.2. Cookie jar có thể thay đổi kết quả nếu bạn không quản lý nó

`WebTestClient` mock ở các đoạn ví dụ **không cấu hình cookie jar tự động**. Vì thế:

- `bootstrap()` mới không nhận cookie từ lần trước, thường tạo session mới.
- `.cookie(token.cookieName(), token.sessionId())` giúp gửi lại S1 theo yêu cầu test.
- Nếu dự án tự cấu hình một HTTP client có cookie store hoặc `defaultCookie`, hãy tách state giữa tests để hai bootstrap requests thực sự độc lập.

Trong một app có reverse proxy, cookie `Path`/`Domain` có thể quyết định browser có tự gửi cookie ở route khác không; mock `.cookie(...)` bỏ qua logic browser này. Đó là lý do vẫn cần test E2E qua HTTPS.

## 7. Bộ ba POST thiếu, sai và đúng token với **cùng session**

Các tests sau sử dụng helper `bootstrap()` và `OrderCounter`. **Không gọi `mutateWith(csrf())` trong POST**, vì mục tiêu là kiểm tra actual HTTP token cùng WebSession.

### 7.1. Có session nhưng không có actual CSRF token

```java
@Test
void authenticatedPostWithoutTokenIsForbidden() {
    SessionToken token = bootstrap();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.sessionId())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, counter.get());
}
```

Có authentication không đồng nghĩa có CSRF. Browser tự gửi session cookie, nhưng không tự gửi giá trị bí mật vào header/form. Đây chính là điều kiện kẻ tấn công CSRF thường cố khai thác.

### 7.2. Có đúng session và header name, nhưng token value sai

```java
@Test
void postWithIncorrectTokenIsForbidden() {
    SessionToken token = bootstrap();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.sessionId())
        .header(token.headerName(), "intentionally-wrong-token")
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, counter.get());
}
```

Một chuỗi sai về giá trị hoặc không có format XOR hợp lệ phải bị từ chối. Tùy custom error handler, status có thể được cấu hình khác, nhưng mặc định thường 403; test nên assert contract cụ thể của ứng dụng.

### 7.3. Đúng session và token do handler expose

```java
@Test
void postWithCorrectSessionAndCsrfTokenReachesHandler() {
    SessionToken token = bootstrap();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.sessionId())
        .header(token.headerName(), token.exposedToken())
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("created");

    assertEquals(1, counter.get());
}
```

Đây là positive control quan trọng: nếu cả request sai và đúng đều trả 403, **chưa thể kết luận** WebSession repository đã phát hiện token sai; có thể authorization hoặc một filter khác luôn chặn.

### 7.4. Token đúng nhưng không có cookie session gốc

```java
@Test
void tokenFromPreviousSessionWithoutCookieIsRejected() {
    SessionToken token = bootstrap();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        // Chủ đích KHÔNG gửi SESSION cookie.
        .header(token.headerName(), token.exposedToken())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, counter.get());
}
```

CSRF expected token nằm trong WebSession S1, không nằm trong header mà server có thể tin khi thiếu S1. Nếu handler vẫn vào controller, kiểm tra chain có CSRF không, matcher có bỏ qua URL không, hoặc test mutator `csrf()` có vô tình gắn vào client dùng chung không.

### 7.5. Token của session khác không được dùng chéo

```java
import static org.junit.jupiter.api.Assertions.assertNotEquals;

@Test
void tokenFromDifferentSessionIsRejected() {
    SessionToken first = bootstrap();
    SessionToken second = bootstrap();

    assertNotEquals(first.sessionId(), second.sessionId());

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(second.cookieName(), second.sessionId())
        .header(second.headerName(), first.exposedToken())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, counter.get());
}
```

Nếu hai bootstrap requests đều dùng cùng session cookie do một custom cookie jar, hãy thay helper tạo **hai isolated clients**. Khi sử dụng default WebSession repository, expected token liên kết với session, không phải một token singleton cho toàn ứng dụng.

### 7.6. Token đúng của session thứ hai phải thành công

```java
@Test
void secondSessionUsesItsOwnToken() {
    SessionToken first = bootstrap();
    SessionToken second = bootstrap();

    assertNotEquals(first.sessionId(), second.sessionId());

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(second.cookieName(), second.sessionId())
        .header(second.headerName(), second.exposedToken())
        .exchange()
        .expectStatus().isOk();
}
```

Đây là positive control đi kèm negative test S2/T1: nếu S2/T2 cũng bị chặn, có thể session cookie không được giữ hoặc handler nhận sai format, chứ không thể kết luận token S1 bị từ chối vì khác session.

### 7.7. Gửi actual token đúng form field cũng là một phương án

Với form URL encoded, dùng `CsrfToken.getParameterName()` (thường `_csrf`), không tự đặt một tên tùy ý:

```java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;

@Test
void formSubmissionCanUseCsrfParameter() {
    SessionToken token = bootstrap();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(token.cookieName(), token.sessionId())
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(BodyInserters.fromFormData(
            token.parameterName(), token.exposedToken()
        ))
        .exchange()
        .expectStatus().isOk();
}
```

Fixture `POST /orders` không yêu cầu JSON request body. Với production controller chỉ nhận `application/json`, dùng CSRF HTTP header cùng JSON body thay vì đổi content type chỉ để làm test pass.

### 7.8. So sánh với `csrf()` helper — trường hợp hợp lệ giả lập

```java
@Test
void csrfMockMutatorIsNotARepositoryRoundTripTest() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

`SecurityMockServerConfigurers.csrf()` **dùng cho mock WebTestClient** để coi request được đáp ứng CSRF, tiện test handler/authorization. Nó không kiểm chứng repository thực sự đã lưu T1 trong S1; các tests ở 7.1–7.7 mới kiểm tra luồng storage và actual token.

## 8. Vòng đời WebSession: tạo, bắt đầu, thay ID, hết hạn, vô hiệu hóa

### 8.1. Các phương thức quan trọng của `WebSession`

| API | Tác dụng | Có tự tạo token CSRF mới không? |
| --- | --- | --- |
| `exchange.getSession()` | Trả `Mono<WebSession>` ứng với request | Không mặc nhiên |
| `session.start()` | Bắt đầu session (khi được lưu, tạo cookie ID) | Không mặc nhiên |
| `session.getAttributes().put(k,v)` | Thêm attribute, gián tiếp bắt đầu session | Không, trừ khi repo ghi token |
| `session.changeSessionId()` | Tạo session id mới, giữ session state theo contract | Không mặc nhiên rotate CSRF raw token |
| `session.setMaxIdleTime(Duration)` | Giới hạn idle timeout | Không |
| `session.isExpired()` | Kiểm tra trạng thái hết hạn dựa vào idle time | Không |
| `session.invalidate()` | Vô hiệu hóa, xóa session storage | Token cũ không còn expected trong session |
| `session.save()` | Lưu session qua store | Không nên gọi tùy tiện trong mỗi handler |

`WebSession.changeSessionId()` là **session fixation defense** khi được authentication strategy gọi lúc đăng nhập. Nó không đồng nghĩa raw CSRF token luôn rotate. Nếu app có logout strategy xóa token, token lifecycle có thể thay đổi độc lập với việc đổi session ID.

### 8.2. Tại sao `start()` không đồng nghĩa `generateToken()`?

```text
GET /test/session/start:
  exchange.getSession() -> WebSession.start()
  response có thể phát SESSION cookie
  không cần có CsrfToken trong session

GET /csrf:
  CsrfWebFilter exposes Mono<CsrfToken>
  controller consume -> repo generate/save expected token
  WebSession attributes có CSRF token
  response có thể phát SESSION cookie
```

Vì vậy **một cookie `SESSION` xuất hiện không chứng minh CSRF token đã được tạo**. Ngược lại, mặc định repository tạo token trong session thường kéo theo session được bắt đầu. Muốn biết token thực sự có, test `GET /csrf` bootstrap và POST same session/actual token.

### 8.3. Unit test tối giản cho `WebSession.start()` và attributes

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.server.MockWebSession;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void creatingSessionObjectDoesNotStartIt() {
    MockWebSession session = new MockWebSession();
    assertFalse(session.isStarted());

    session.start();
    assertTrue(session.isStarted());
}

@Test
void addingAnAttributeStartsSession() {
    MockWebSession session = new MockWebSession();
    assertFalse(session.isStarted());

    session.getAttributes().put("test-state", "value");
    assertTrue(session.isStarted());
}
```

`MockWebSession` là test double của Spring Framework. Không suy rằng test này xác minh browser đã nhận cookie — cookie thuộc WebSession manager/HTTP response, không phải cùng `WebSession` object.

### 8.4. Kiểm thử `start()` bằng HTTP response trong fixture

Route `/test/session/start` đã khai báo ở mục 4.2 và được authentication bảo vệ. Với mock user:

```java
@Test
void startingSessionExplicitlyIssuesSessionCookie() {
    var result = client.mutateWith(mockUser("alice"))
        .get().uri("/test/session/start")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("started")
        .returnResult();

    assertNotNull(
        result.getResponseCookies().getFirst("SESSION")
    );
}
```

Test này chỉ cho biết **session started** và cookie được phát trong fixture default. Nó không kiểm tra token CSRF, vì endpoint không consume `Mono<CsrfToken>`.

## 9. Invalidate session: token cũ có còn sử dụng được?

Trong session-based CSRF, một token đã được server lưu trước đó có thể **không còn hợp lệ** khi WebSession bị vô hiệu hóa. Việc invalidation xóa session storage nghĩa là repository không thể nạp expected token thuộc session đã mất.

### 9.1. Kiểm thử luồng GET → POST invalidate → POST old token

Route test-only `POST /test/session/invalidate` trong fixture có CSRF bật. Do đó bản thân request **invalidate session** cũng phải gửi token hợp lệ:

```java
@Test
void sessionInvalidationRejectsOldCsrfToken() {
    SessionToken before = bootstrap();

    // 1. Vô hiệu hóa session bằng request state-changing hợp lệ.
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/test/session/invalidate")
        .cookie(before.cookieName(), before.sessionId())
        .header(before.headerName(), before.exposedToken())
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("invalidated");

    // 2. Thử lại với session ID/token cũ, nhưng không gọi csrf().
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie(before.cookieName(), before.sessionId())
        .header(before.headerName(), before.exposedToken())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, counter.get(),
        "Session/token invalidated must not create an order");
}
```

`mockUser()` vẫn cung cấp principal trong request thứ hai để **cô lập CSRF**; ở production, sau logout user cũng mất authentication, nên HTTP status có thể là 401/redirect thay vì 403. Để test đầy đủ logout, dùng **authentication thật và cookie jar**, không chỉ mock principal.

### 9.2. Bootstrap token mới sau invalidation

```java
@Test
void newSessionCanBootstrapFreshCsrfToken() {
    SessionToken old = bootstrap();

    client.mutateWith(mockUser("alice"))
        .post().uri("/test/session/invalidate")
        .cookie(old.cookieName(), old.sessionId())
        .header(old.headerName(), old.exposedToken())
        .exchange()
        .expectStatus().isOk();

    // Một GET mới không mang cookie từ session đã bị hủy.
    SessionToken fresh = bootstrap();
    org.junit.jupiter.api.Assertions.assertNotEquals(
        old.sessionId(), fresh.sessionId());

    client.mutateWith(mockUser("alice"))
        .post().uri("/orders")
        .cookie(fresh.cookieName(), fresh.sessionId())
        .header(fresh.headerName(), fresh.exposedToken())
        .exchange()
        .expectStatus().isOk();
}
```

Không assert exposed token `old.exposedToken()` khác `fresh.exposedToken()` như **bằng chứng duy nhất**: XOR masking có randomness ngay cả khi expected raw token không rotate. Kiểm tra session ID, repository state và request token mới hợp lệ quan trọng hơn.

### 9.3. Test unit cho invalidation không phải HTTP test

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.server.MockWebSession;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void invalidationClearsSessionState() {
    MockWebSession session = new MockWebSession();
    session.getAttributes().put("demo-csrf-state", "present");
    assertTrue(session.isStarted());

    StepVerifier.create(session.invalidate())
        .verifyComplete();

    assertFalse(session.getAttributes()
        .containsKey("demo-csrf-state"));
}
```

Test unit này chỉ xác nhận `WebSession.invalidate()` có hiệu lực với một session test double, **chưa** chứng minh `CsrfWebFilter` nạp đúng token sau invalidation. Test HTTP ở mục 9.1 mới kiểm tra integration behavior.

### 9.4. Không để test-only invalidation endpoint ở production

Endpoint `POST /test/session/invalidate` minh họa vòng đời thấp, không phải cách khuyến nghị xây chức năng logout của ứng dụng. Với production, Spring Security `LogoutWebFilter`, logout handler, session invalidation và cookie clearing phải được cấu hình đúng. Nếu app cho phép anonymous gọi một endpoint tùy ý hủy session của user, đó có thể tạo rủi ro logout CSRF hoặc denial-of-service.

## 10. Đổi session ID không tự xoay vòng CSRF token

`WebSession.changeSessionId()` có thể giúp ngăn session fixation sau authentication. Nó yêu cầu session store/manager đổi ID mà vẫn giữ các session attributes theo contract. Điều này **khác** với `ServerCsrfTokenRepository.saveToken(exchange, null)` dùng để xóa token.

### 10.1. Unit test `changeSessionId()`

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.server.MockWebSession;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

@Test
void changingSessionIdPreservesAttributes() {
    MockWebSession session = new MockWebSession();
    session.getAttributes().put("test-role", "viewer");
    String oldId = session.getId();

    StepVerifier.create(session.changeSessionId())
        .verifyComplete();

    assertNotEquals(oldId, session.getId());
    assertEquals("viewer",
        session.getAttribute("test-role"));
}
```

Test này là minh họa **ID rotation giữ session state**. Nó không đảm bảo CSRF token còn nguyên trong mọi login flow, vì authentication success strategy có thể xóa/rotate CSRF token độc lập.

### 10.2. Ba chuyển động cần tách

| Thay đổi | Session ID | CSRF expected token | SecurityContext |
| --- | --- | --- | --- |
| `changeSessionId()` | Mới | Có thể giữ nếu attribute chưa xóa | Có thể giữ |
| `saveToken(exchange, null)` | Không bắt buộc đổi | Token bị xóa | Không bắt buộc thay |
| `invalidate()` | Session cũ mất hiệu lực | Token cũ không còn trong session | Authentication session bị mất theo store/handler |

Không viết một test “session id khác → token raw bắt buộc khác” khi chính sách không yêu cầu. Thay vào đó, mô tả rõ app dùng chiến lược **rotate ID, clear CSRF token, invalidate session hoặc kết hợp** vào từng thời điểm.

### 10.3. Đọc Session ID trong HTTP test mà không lộ bí mật

Trong mock test bạn có thể `assertNotEquals(oldId,newId)`, nhưng không ghi các ID này vào CI logs hoặc test failure message. Với HTTP server thật, kiểm tra `Set-Cookie`/cookie jar thay đổi hợp lý, không đặt ID vào query string. Ngoài ra, `CookieWebSessionIdResolver` và `Spring Session` có thể thay cookie name và behavior theo cấu hình.

## 11. Session timeout: phải test **hết hạn thực** chứ không chỉ bỏ cookie

### 11.1. WebSession có idle timeout

`WebSession.getMaxIdleTime()` và `setMaxIdleTime(Duration)` mô tả khoảng bất hoạt cho phép, tính từ `getLastAccessTime()`. `isExpired()` phản ánh thời hạn theo implementation/store. Với session đã hết hạn, session manager/store thường trả một session mới khi request có session ID cũ.

```java
import java.time.Duration;

// Trong fixture hoặc configuration test thích hợp:
session.setMaxIdleTime(Duration.ofMinutes(15));
```

Đoạn trên là Java fragment minh họa cho object `WebSession session`; không cấu hình timeout bằng cách gọi method trên một bean không được inject. Các session managers và stores có cơ chế riêng để đặt timeout mặc định cho toàn ứng dụng.

### 11.2. Ba loại test có độ tin cậy khác nhau

| Kịch bản | Cách thực hiện | Kết luận |
| --- | --- | --- |
| Bỏ session cookie | POST T1 không mang S1 | Token cũ không hợp lệ **khi session gốc không được gửi** |
| Gọi `session.invalidate()` | POST invalidate, replay S1/T1 | Token cũ không hợp lệ sau **explicit invalidation** |
| Chờ/giả lập hết idle time | Fake clock/test session store hoặc session timeout thấp trên staging | **Expiration semantics** của store đang chạy |

Không dùng một POST thiếu cookie làm bằng chứng bạn đã kiểm tra idle timeout. Nếu muốn test timeout chính xác, dùng clock/fake session store có thể kiểm soát, hoặc môi trường staging có timeout được cấu hình và xác nhận; không dùng `Thread.sleep` dài trong bộ unit tests.

### 11.3. Kịch bản E2E sau timeout

```text
t0:    GET /csrf -> S1, M1; login hoặc có auth session
t0+:   POST /orders với S1/M1 -> thành công
tIdle: Không có HTTP request refresh lastAccessTime
tExp:  Session store xác định S1 hết hạn
tExp+: POST /orders với S1/M1 -> phải bị từ chối
       (CSRF 403 hoặc auth 401/redirect tùy chain/order)
tNew:  GET /csrf -> S2, M2
tNew+: POST /orders với S2/M2 và auth hợp lệ -> thành công
```

**Lưu ý:** Trong hệ thống thật, JS polling, assets requests hoặc keepalive có thể làm `lastAccessTime` thay đổi. Khi test timeout, phải biết request nào thực sự chạm session store; một test tưởng “không có activity” nhưng frontend vẫn poll có thể không bao giờ thấy session expire.

### 11.4. Hiển thị lỗi cho người dùng khi session đã hết

Đối với SPA, một POST sau timeout có thể trả 403 vì CSRF expected token mất; nhưng nếu session auth cũng mất, có thể nhận 401 hoặc login redirect. Client nên nhận biết session hết hạn và **đưa người dùng về luồng đăng nhập/khởi tạo session phù hợp**, tránh retry vô hạn POST side-effect. Không tắt CSRF hoặc tự động resubmit thanh toán chỉ vì token cũ bị từ chối.

### 11.5. Unit test riêng cho `WebSession` timeout configuration

```java
import java.time.Duration;
import org.springframework.mock.web.server.MockWebSession;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void sessionCanBeConfiguredWithIdleTimeout() {
    MockWebSession session = new MockWebSession();
    session.setMaxIdleTime(Duration.ofMinutes(15));

    assertEquals(Duration.ofMinutes(15),
        session.getMaxIdleTime());
}
```

Test này kiểm tra **cấu hình property**, không buộc đồng hồ tiến 15 phút và không xác minh store expiration. Muốn kết luận S1 hết hạn, cần kịch bản 11.3 hoặc test store được kiểm soát thời gian.

## 12. Repository raw token: test riêng để không nhầm XOR

`ServerCsrfTokenRepository` cung cấp `generateToken`, `saveToken`, `loadToken`. Trong WebSession repository, ba thao tác này cho phép xác minh **raw expected token** được lưu trong session, khác với exposed token có thể được XOR-mask ở `GET /csrf`.

### 12.1. Kiểm thử tạo/lưu/nạp token

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Test
void repositorySavesExpectedTokenInWebSession() {
    var repository = new WebSessionServerCsrfTokenRepository();
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/csrf"));

    var generated = repository.generateToken(exchange).block();
    assertNotNull(generated);

    StepVerifier.create(
        repository.saveToken(exchange, generated)
            .then(repository.loadToken(exchange))
    )
        .assertNext(loaded ->
            org.junit.jupiter.api.Assertions.assertEquals(
                generated.getToken(), loaded.getToken()))
        .verifyComplete();
}
```

Ở đây `block()` chỉ nằm **trong JUnit test setup**, không nằm trong handler/event loop. Đây là unit-ish test một `MockServerWebExchange`: nó không chứng minh cookie được gửi qua hai HTTP requests, XOR handler hoạt động hay logout thực sự clear session.

### 12.2. Thử `saveToken(exchange, null)`

Theo repository contract, truyền `null` cho `saveToken` nhằm xóa expected token:

```java
@Test
void clearingStoredTokenMakesLoadEmpty() {
    var repo = new WebSessionServerCsrfTokenRepository();
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/csrf"));

    var initial = repo.generateToken(exchange).block();
    assertNotNull(initial);

    StepVerifier.create(
        repo.saveToken(exchange, initial)
            .then(repo.saveToken(exchange, null))
            .then(repo.loadToken(exchange))
    )
        .verifyComplete();
}
```

`verifyComplete()` trên publisher `Mono<CsrfToken>` sau khi clear chứng minh **không phát ra token**; vì các publisher được nối bằng `then`, chúng được subscribe đúng thứ tự. Đây là một khác biệt quan trọng với việc gọi `repo.saveToken(exchange, initial);` nhưng quên subscribe: khi đó lệnh lưu có thể chưa chạy.

### 12.3. Tránh double subscription không chủ đích

`Mono` trong Reactor có thể là cold, hot, cached hoặc deferred tùy cách xây publisher. Đừng giả định “subscribe hai lần luôn sinh hai token” hoặc “subscribe hai lần luôn cùng instance” nếu chưa kiểm tra implementation của phiên bản.

Trong application, **chỉ compose token publisher cần thiết cho response**; nếu nhiều thành phần cùng đọc token, đảm bảo request handler/framework duy trì contract đúng, và viết regression test dựa trên hành vi **POST cùng session được chấp nhận**, không dựa vào con số subscription nội bộ của một phiên bản.

## 13. `Mono<CsrfToken>` trong Thymeleaf, form và `@ControllerAdvice`

Ứng dụng Reactive trả HTML có thể không dùng JSON endpoint `GET /csrf` mà render CSRF token vào hidden input. Khi đó view engine phải **subscribe `Mono<CsrfToken>`** và expose `CsrfToken` dưới tên mà tích hợp Spring Security nhận biết.

### 13.1. `@ControllerAdvice` để expose token cho view

Ví dụ theo Spring Security Reactive CSRF Reference:

```java
package com.example.reactivelifecycle;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.reactive.result.view.CsrfRequestDataValueProcessor;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@ControllerAdvice
public class ReactiveCsrfModelAdvice {

    @ModelAttribute
    public Mono<CsrfToken> csrfToken(ServerWebExchange exchange) {
        Mono<CsrfToken> source =
            exchange.getAttribute(CsrfToken.class.getName());

        if (source == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter is not active for this request"));
        }

        return source.doOnNext(token ->
            exchange.getAttributes().put(
                CsrfRequestDataValueProcessor.DEFAULT_CSRF_ATTR_NAME,
                token
            )
        );
    }
}
```

`CsrfRequestDataValueProcessor.DEFAULT_CSRF_ATTR_NAME` tương ứng `_csrf`. Đoạn `@ControllerAdvice` dùng cho view integration: chỉ khi **view rendering infrastructure thực sự subscribe returned publisher** thì token được load và đưa vào request attribute. Không tự động đăng ký advice này cho mọi JSON API nếu không cần CSRF model attribute.

**Lưu ý cú pháp:** dùng `exchange.getAttributes().put(...)` để đặt attribute; `CsrfToken` không có `getAttributes()`. Với blog/tutorial cũ, kiểm tra đúng biến và Spring Security version.

### 13.2. Form phải gửi hidden field đúng tên và giá trị

Ví dụ HTML **sau khi render**, không hard-code `MASKED_TOKEN_FROM_SERVER` trong production:

```html
<form method="post" action="/orders">
  <input type="hidden"
         name="_csrf"
         value="MASKED_TOKEN_FROM_SERVER"/>
  <button type="submit">Tạo đơn</button>
</form>
```

Với Thymeleaf và `_csrf` model attribute đã expose, form có thể dùng:

```html
<form th:action="@{/orders}" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}" />
  <button type="submit">Tạo đơn</button>
</form>
```

`${_csrf...}` là biểu thức của **Thymeleaf** trong template HTML, không phải Java string. Thymeleaf WebFlux integration có thể hỗ trợ chèn token tự động; tránh nhân đôi hidden input khi cả framework và template đã làm.

### 13.3. Kiểm thử HTML thật ngoài kiểm thử JSON bootstrap

```text
GET /orders/new
  -> view subscribe Mono<CsrfToken>
  -> render <input name="_csrf" value="...">
  -> WebSession repository lưu expected token
  -> Set-Cookie: SESSION=S1

POST /orders
  -> Cookie: SESSION=S1
  -> body: _csrf=<token-from-rendered-form>
  -> CSRF pass -> authorization -> handler
```

Muốn xác nhận Thymeleaf tự chèn CSRF field, test cần **HTML page thật** và parser/browser E2E. Fixture `GET /csrf` JSON trước đó chỉ chứng minh publisher/token round-trip, không chứng minh Thymeleaf integration.

### 13.4. Không gọi `block()` trong `@ModelAttribute`

```java
// SAI trong Reactive request processing:
@ModelAttribute("_csrf")
public CsrfToken blocking(ServerWebExchange exchange) {
    Mono<CsrfToken> source =
        exchange.getAttribute(CsrfToken.class.getName());
    return source.block();
}
```

Block trong WebFlux event-loop có thể gây nghẽn hoặc lỗi; dùng `Mono<CsrfToken>` và return/composition để framework subscribe.

## 14. Đối chiếu WebSession repository và cookie repository cho SPA

Nếu frontend Angular-style cần đọc cookie `XSRF-TOKEN` và tự gửi `X-XSRF-TOKEN`, có thể dùng:

```java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()
));
```

Đây là **cấu hình thay thế** WebSession repository của fixture, không đăng ký cả hai tùy tiện trên cùng chain. `withHttpOnlyFalse()` chỉ có lý do khi JavaScript cần đọc **CSRF cookie**; không tắt `HttpOnly` của authentication session cookie.

### 14.1. Raw cookie không luôn tương thích XOR handler

Trong WebFlux Security 6/7, default `XorServerCsrfTokenRequestAttributeHandler` có thể expect **masked token** trong header/form. Cookie repository lại đặt **raw expected token** vào `XSRF-TOKEN`:

```text
CookieServerCsrfTokenRepository -> XSRF-TOKEN=R (raw)
    |
    +-- SPA JS đọc cookie -> header X-XSRF-TOKEN=R
    |                        -> default XOR handler có thể 403
    |
    +-- GET /csrf -> exposed masked token M
         header X-XSRF-TOKEN=M + cookie XSRF-TOKEN=R
         -> handler decode M thành R -> pass
```

Một mock `mutateWith(csrf())` pass không chứng minh SPA gửi đúng format. Cần test cookie/header thực và request handler phù hợp. Nếu cần raw-header SPA flow, thiết kế handler tương thích và **review tác động BREACH**, không tắt CSRF.

### 14.2. Cookie repository không mặc nhiên ràng buộc token với WebSession

`CookieServerCsrfTokenRepository` thông thường đọc expected token từ cookie của client. Không áp dụng test “T1/S1 nhất thiết khác T1/S2” của WebSession repository rồi kết luận cookie repo lỗi. Nếu threat model đòi token gắn mật mã với session, cần signed/session-bound scheme được thiết kế riêng.

### 14.3. CORS, cookie scope và security headers là các lớp riêng

Khi SPA/API khác origin, OPTIONS preflight thường không mang session cookie. CSRF matcher mặc định không yêu cầu token cho OPTIONS, nhưng CORS phải được xử lý đúng `Origin`/method/headers trước authentication.

Kiểm tra allowed origins chính xác, CSRF header trong `Access-Control-Allow-Headers`, cookie `Secure`/`SameSite`/`Domain`/`Path` và response `GET /csrf` không bị CDN cache. Với SPA ở `https://app.example.com` và API ở `https://api.example.com`, JavaScript của SPA không thể đọc cookie host-only của API bằng `document.cookie`, dù CORS cho phép đọc HTTP response. Cân nhắc JSON `GET /csrf` với CORS allowlist hoặc same-origin BFF.

`Content-Security-Policy` trên HTML frontend, HSTS trên HTTPS hostname và HTTP firewall phải được test **riêng**; một CSRF token round-trip không chứng minh các lớp đó hoạt động.

## 15. Authentication và logout: session/token thay đổi độc lập

### 15.1. `mockUser()` không thực hiện login thật

`mockUser("alice")` tạo principal trong mock exchange. Nó không gửi username/password qua authentication flow thật, không nhất thiết lưu SecurityContext vào WebSession hoặc gọi login success/logout strategy. Vì vậy `mockUser()` + `csrf()` pass không chứng minh token/session lifecycle sau authentication.

### 15.2. Luồng login/logout cần HTTP round-trip thật

```text
GET /csrf -> S0, M0

POST /login:
  cookie S0 + username/password + _csrf=M0
  -> auth success có thể đổi session ID, clear token, ghi SecurityContext

GET /csrf sau login:
  dùng cookie session mới nhất, lấy M1 hợp lệ

POST /orders:
  authenticated session + M1 -> success khi đủ quyền

POST /logout:
  session cookie + CSRF token phù hợp
  -> logout handler invalidates/clears theo config

POST /orders bằng session/token cũ:
  -> không được phép thực hiện side effect
```

WebFlux mặc định yêu cầu CSRF cho login/logout state-changing requests; `LogoutWebFilter` thường xử lý POST. Không chuyển login/logout sang GET để né CSRF. Fixture `HTTP Basic` ở mục 4 không tự có form login `/login`.

### 15.3. Form login fixture **thay thế** HTTP Basic-only

```java
@Bean
SecurityWebFilterChain formLogin(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/login", "/csrf", "/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .csrf(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
}
```

Đây là **replacement** cho `TestSecurityConfig.web`, không thêm hai fallback chains không có `@Order`/`securityMatcher`. Để test login/logout lifecycle, gửi credential/form thật với CSRF token, theo dõi cookie sau từng response, assert protected GET sau login được phép và sau logout bị chặn.

### 15.4. Không đồng nhất session fixation và CSRF token rotation

Session ID rotation và CSRF token clearing không bắt buộc xảy ra cùng lúc hoặc theo một thứ tự cố định trong mọi version/config. Test rõ chính sách được chọn: session cũ không được tự authenticated, session mới có quyền phù hợp và token cũ có/không được chấp nhận theo CSRF repository/strategy.

## 16. Nhiều security chains và đường dẫn sau proxy rewrite

Ứng dụng có thể dùng Bearer-only API chain và browser fallback:

```java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        // Chỉ miễn CSRF khi threat model chứng minh Bearer-only:
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browser(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/csrf", "/public/**").permitAll()
            .anyExchange().authenticated())
        .csrf(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Ví dụ là **hai chains thay thế** fixture một chain trước đó. Cần imports `@Bean`/`@Order`, `ServerWebExchangeMatchers`, `SecurityWebFilterChain`, `ServerHttpSecurity`, `Customizer` và Resource Server dependencies + `ReactiveJwtDecoder` thực tế. Không nạp nhiều fallback chains vào một test không có order.

### 16.1. Test chain cùng repository/token scope

| Request | Chain | Điều cần kiểm tra |
| --- | --- | --- |
| GET `/csrf` | Browser | `Mono<CsrfToken>` được expose, WebSession lưu token |
| POST `/orders` với cookie | Browser | Thiếu token 403; đúng token/auth được phép |
| GET `/api/orders` Bearer | API | Thiếu JWT 401; scope sai 403 nếu rule scope được khai báo |
| POST `/api/orders` | API | Authentication và CSRF đúng threat model |
| GET `/unknown` | Browser fallback | Không lọt khỏi tất cả Security chains |

Không lấy token ở browser chain rồi dùng nó để đánh giá một API chain có repository/CSRF policy khác. Nếu ingress rewrite `/gateway/**` sang `/api/**`, xác minh security matcher theo canonical path mà Spring nhìn thấy; một 403 do chọn sai chain không tự là lỗi session token.

## 17. `@WebFluxTest` và `@SpringBootTest`: test context nào có `CsrfWebFilter`?

### 17.1. `@WebFluxTest` chỉ là slice

Trong Spring Boot, `@WebFluxTest` tập trung vào web components; custom `SecurityWebFilterChain` và CSRF repository/handler **không nhất thiết được nạp**. Nếu test chỉ bind controller, nó không chứng minh token được Spring Security expose hay WebSession tạo. Hãy import config cần thiết và viết negative POST test.

Ví dụ **package Spring Boot 3.5**:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@WebFluxTest(SessionCsrfController.class)
@Import({TestSecurityConfig.class, SliceTestDependencies.class})
class SessionCsrfSliceTest {

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void sessionBasedCsrfIsNotDisabledInSlice() {
        client.mutateWith(mockUser("alice"))
            .post().uri("/orders")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`SliceTestDependencies` là **test configuration mà người học tự tạo** để cung cấp `OrderCounter` và các dependencies của controller, không phải class Spring có sẵn. Với một fixture hoàn chỉnh không phụ thuộc Boot, dùng `@SpringJUnitConfig` ở mục 4.5 thay cho snippet slice.

Spring Boot 4 có packages tương ứng:

```java
// Boot 4.x:
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
```

Không kết hợp import Boot 3.5 và Boot 4 trong cùng test class. Kiểm tra đúng version của test starter/Security. Nếu slice thiếu custom `ServerCsrfTokenRequestHandler`, test JSON token bootstrap có thể vẫn xanh với default handler trong khi frontend thật lỗi; cần full-context test bổ sung.

### 17.2. Full context nhưng vẫn mock HTTP

```java
@SpringBootTest
class FullContextSessionCsrfTest {
    @Autowired ApplicationContext context;

    @Test
    void policyRejectsUnsafeRequestWithoutToken() {
        WebTestClient client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();

        client.mutateWith(mockUser("alice"))
            .post().uri("/orders")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`@SpringBootTest` với webEnvironment mặc định **không có nghĩa mở TCP server**. Ở đây WebTestClient bind vào application context và dùng mock exchange. Nó nạp gần toàn bộ bean wiring hơn slice, nhưng không tự mô phỏng browser cookie restrictions hoặc TLS proxy.

### 17.3. Không dùng test client filter để giả lập server Security

`WebTestClient.configureClient().filter(ExchangeFilterFunction)` là filter **phía client** (ví dụ thêm Basic auth header/logging). Nó không phải `WebFilter` của Spring Security server, không làm `Mono<CsrfToken>` tự xuất hiện trong server exchange. Khi cần test server Security, phải bind đúng application context/web server.

## 18. Live HTTP: kiểm chứng session và token qua cổng thật

### 18.1. `RANDOM_PORT` kiểm tra Basic authentication thật

Đối với Spring Boot WebFlux app/test profile có controller, CSRF repository và test user store phù hợp:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveHttpCsrfLifecycleTest {

    @Autowired WebTestClient http;

    @Test
    void realSessionCookieAndCsrfHeaderAreRequired() {
        EntityExchangeResult<SessionCsrfController.CsrfEnvelope> bootstrap =
            http.get().uri("/csrf")
                .exchange()
                .expectStatus().isOk()
                .expectBody(SessionCsrfController.CsrfEnvelope.class)
                .returnResult();

        var csrf = bootstrap.getResponseBody();
        ResponseCookie cookie =
            bootstrap.getResponseCookies().getFirst("SESSION");
        assertNotNull(csrf);
        assertNotNull(cookie);

        // Authentication thật qua Basic; session/token đúng.
        http.post().uri("/orders")
            .headers(h -> h.setBasicAuth(
                "alice", "testing-only"))
            .cookie("SESSION", cookie.getValue())
            .header(csrf.headerName(), csrf.token())
            .exchange()
            .expectStatus().isOk();

        // Cùng Basic/session, nhưng thiếu actual token -> 403.
        http.post().uri("/orders")
            .headers(h -> h.setBasicAuth(
                "alice", "testing-only"))
            .cookie("SESSION", cookie.getValue())
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`@AutoConfigureWebTestClient` import ở trên là **Boot 3.5**; Boot 4 dùng `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient`. Tên password là fixture test-only; không dùng trong production. Nếu application không dùng HTTP Basic, gửi credential/token thực của auth mechanism đã chọn.

### 18.2. Vì sao `csrf()`/`mockUser()` không áp dụng như vậy qua TCP?

Trong mock context:

```text
client.mutateWith(mockUser(...)).mutateWith(csrf())
  -> mock ServerWebExchange + test Security context/configurer
  -> không cần Basic password / token ký thật
```

Trong HTTP server thật:

```text
WebTestClient.bindToServer hoặc @SpringBootTest(RANDOM_PORT)
  -> HTTP request đi qua TCP
  -> server authentication provider/decoder thật
  -> CsrfWebFilter nạp expected từ WebSession thật
  -> client phải gửi cookie + header/form token thật
```

`@WithMockUser` nằm trong test thread cũng không tự truyền principal qua network tới server. `SecurityMockServerConfigurers.csrf()` cần mock `WebHttpHandlerBuilder` và không thay thế HTTP token round-trip trên live client.

### 18.3. Khi dùng `bindToServer()`

```java
WebTestClient live = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080")
    .build();

live.get().uri("/public/ping")
    .exchange()
    .expectStatus().isOk();
```

Chỉ dùng cổng 8080 nếu server độc lập đang chạy ở cổng đó. Với `RANDOM_PORT`, ưu tiên WebTestClient do Boot cấu hình tự động; không hard-code port. Test Basic/cookie như mục 18.1 vẫn phải dùng HTTP requests thực.

### 18.4. HTTPS staging vẫn cần thiết

RANDOM_PORT kiểm thử parser/server/auth/CSRF thật, nhưng thường **chưa** đi qua:

- TLS termination và trusted `Forwarded`/`X-Forwarded-Proto`.
- CORS policy tại gateway và header duplication.
- CDN caching `GET /csrf` hoặc HTML có CSRF form field.
- Cookie `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path` theo browser.
- Session store dùng Redis/Spring Session trên nhiều replicas.
- HSTS/CSP của frontend HTML khi khác owner với JSON API.
- URL path normalization, HTTP firewall và reverse proxy prefix rewrite.

Vì vậy có một nhóm smoke tests qua **public staging HTTPS** và browser engine là cần thiết khi thay token/session design.

## 19. Triển khai session store nhiều replicas

### 19.1. Vấn đề khi request đổi pod

`WebSessionServerCsrfTokenRepository` lưu expected token trong WebSession. Nếu hệ thống có các pods A/B nhưng chỉ dùng in-memory session store độc lập:

```text
GET /csrf ở pod A:
  WebSession S1 trên A chứa raw token R1
  browser nhận cookie SESSION=S1 và exposed token M1

POST /orders tới pod B:
  B không có S1 trong store của B
  -> B không nạp được expected R1
  -> POST với M1 có thể bị 403
```

Giải pháp có thể gồm **Spring Session backed by Redis** hoặc sticky sessions có tính toán, nhưng việc dùng sticky sessions không tự xử lý failover/rolling deployment. Test staging nên đưa GET và POST qua khác replica một cách có kiểm soát.

### 19.2. Lưu ý serializer và security context

Khi rolling deployment giữa Spring Boot/Security versions, cần kiểm tra tương thích serialization của **WebSession attributes và SecurityContext**, không chỉ expected CSRF token. Nếu session store không deserialize được một attribute, lỗi có thể được nhìn thấy như 401/403, session mới hoặc HTTP 500 tùy failure path.

Không đưa session ID/token thật vào metrics/logs; có thể dùng một correlation id không nhạy cảm và các counter như “session-load-failed”, “csrf-rejected”, “auth-failed” tách biệt.

### 19.3. Cookie repo không tự giải quyết mọi vấn đề session

`CookieServerCsrfTokenRepository` giúp token expected đi theo cookie từ client, nhưng nếu ứng dụng vẫn sử dụng **session authentication**, SecurityContext và logout state cần session store nhất quán. Không chuyển CSRF repository sang cookie chỉ để che lỗi shared session mà không kiểm tra toàn authentication architecture.

## 20. Chẩn đoán lỗi `Mono<CsrfToken>` và WebSession lifecycle

### Lỗi A — `GET /csrf` báo “CsrfWebFilter did not expose token”

**Nguyên nhân thường gặp:** `SecurityWebFilterChain` không được nạp trong test, request không đi qua chain có CSRF, chain đã `csrf.disable()` hoặc test dùng `bindToController` thay vì `bindToApplicationContext`.

**Cách khắc phục:** xác minh bean `SecurityWebFilterChain` và `WebFilterChainProxy`, `securityMatcher` đúng URL, test context import config, client có `apply(springSecurity())`. Không tự tạo một token hard-code để che lỗi missing filter.

### Lỗi B — `GET /csrf` có `Mono<CsrfToken>` nhưng không phát cookie

**Khả năng:** controller chỉ lấy reference `Mono` rồi return publisher khác, không có subscriber; WebSession không được start; repository được đổi sang cookie/handler khác; cookie name khác `SESSION` hoặc proxy loại bỏ `Set-Cookie`.

**Cách khắc phục:** return `csrfMono.map(...)` trong response, bảo đảm HTTP pipeline subscribe; kiểm tra repo và session manager. Không gọi `csrfMono.subscribe()` thủ công như một side effect race.

### Lỗi C — `exchange.getSession()` trả object nhưng response không có `SESSION`

**Giải thích:** `getSession()` không tự bắt đầu WebSession. Session bắt đầu khi thêm attribute hoặc `start()` rồi được lưu đúng lúc. Test `/test/session/start` sẽ minh họa khác biệt này.

### Lỗi D — `@ControllerAdvice` trả `Mono<CsrfToken>` nhưng form vẫn không có hidden CSRF field

**Kiểm tra:** view/template có thực sự resolve/subcribe model attribute không? `CsrfRequestDataValueProcessor` có được tích hợp vào Thymeleaf/WebFlux renderer không? `_csrf` được expose đúng name chưa?

**Cách khắc phục:** test HTML thực đã render, không chỉ test controller trả 200; dùng `exchange.getAttributes().put("_csrf", token)` khi publisher được consume và bảo đảm template dùng `_csrf.parameterName`/`_csrf.token`.

### Lỗi E — GET hai lần token string khác nhau, kết luận token bị rotate

**Giải thích:** `XorServerCsrfTokenRequestAttributeHandler` 6.x/7.x có thể tạo giá trị masked khác mỗi lần expose raw expected token. Test **cùng session gửi M1/M2 qua POST** hoặc repo unit test raw token. Không assert equality của masked strings.

### Lỗi F — POST dùng token từ GET nhưng vẫn 403

**Kiểm tra theo thứ tự:** cookie `SESSION` từ GET có được gửi lại không; đúng HTTP header name/parameter name không; CSRF handler raw/masked ra sao; POST rơi vào đúng chain không; user có đủ quyền không; có CORS/proxy làm mất cookie/header không?

**Cách khắc phục:** giữ principal, method và URL cố định, so missing/invalid/valid token. Dùng đúng token trả từ server cho **same session**, không tạo token giả.

### Lỗi G — POST không có cookie nhưng có token vẫn 200

**Cảnh báo:** với default WebSession repository, expected token từ S1 không nên được chấp nhận khi client không gửi S1. Kiểm tra `csrf()` có gắn trên mock client, CSRF bị disable, repo thực là CookieServerCsrfTokenRepository hay WebSession repo, hoặc test có default cookies vô hình.

### Lỗi H — POST từ session khác được chấp nhận

Nếu repo là WebSession, trước tiên bảo đảm S1/S2 **thực sự khác ID** và không có cookie jar trộn state. Nếu repo là Cookie, không gán sai semantics server-side session binding cho nó. Nếu app cần signed/session-bound token, yêu cầu thiết kế repository riêng.

### Lỗi I — Test invalidation báo 401/redirect thay vì 403

Khi request sau logout không có authentication, authentication entry point có thể phản hồi 401/redirect. Trong mock CSRF-isolation test, dùng `mockUser()` để giữ principal và kiểm tra CSRF riêng; trong live logout test, xác nhận **request bị từ chối** theo policy, không bắt buộc luôn 403.

### Lỗi J — POST invalidate session không hoạt động

Route `POST /test/session/invalidate` cũng là unsafe method và cần **actual CSRF token hợp lệ**, chưa kể user authenticated. Nếu thiếu token, nó có thể bị từ chối trước khi controller gọi `WebSession.invalidate()`. Giữ cookie/token đúng, assert response và replay token cũ.

### Lỗi K — Đổi session ID, expected token không đổi

`WebSession.changeSessionId()` chủ yếu đổi ID và giữ state; nó không có contract tự xóa raw `CsrfToken`. Nếu app cần clear token khi authentication success, phải xem CSRF/authentication strategy chứ không tự coi ID rotation là token rotation.

### Lỗi L — Token cũ sau timeout vẫn được server chấp nhận

Kiểm tra session **thực sự** hết hạn chưa. Polling/keepalive có thể gia hạn `lastAccessTime`; store timeout config khác với app config; sticky session hoặc session cluster có TTL khác. Kiểm tra expired-session test environment và response session-state, không suy từ một `Thread.sleep` ngắn.

### Lỗi M — `csrf()` helper làm test pass trong khi token flow thật fail

`SecurityMockServerConfigurers.csrf()` là test mutator cho mock condition hợp lệ, không thay GET token bootstrap/WebSession cookie. Giữ helper để test business logic sau CSRF, nhưng thêm negative tests và actual cookie/header round-trip.

### Lỗi N — Test live HTTP không nhận `mockUser()` hoặc `csrf()`

`mockUser()` là mock exchange mutator, không chuyển credentials qua TCP; `csrf()` cần mock handler builder. Với `RANDOM_PORT`/`bindToServer`, dùng HTTP authentication thật (Basic/Bearer/form) và GET bootstrap token rồi POST cookie/header như browser.

### Lỗi O — SPA đọc raw cookie nhưng default XOR handler từ chối

`CookieServerCsrfTokenRepository` cấp raw token qua `XSRF-TOKEN`, nhưng default XOR handler có thể cần masked actual token. Thiết kế request handler hỗ trợ raw header theo đúng Spring Security WebFlux version hoặc dùng `GET /csrf` exposed masked token. Không tắt BREACH masking chỉ vì frontend mới lỗi 403.

### Lỗi P — CORS OPTIONS trả 401/403

OPTIONS preflight thường không có cookie; default CSRF matcher không yêu cầu CSRF cho OPTIONS. Kiểm tra `CorsConfigurationSource` **Reactive**, allowed origins/methods/headers và chain matcher. `permitAll()` OPTIONS không tự sinh `Access-Control-Allow-*` headers; `csrf()` cũng không sửa CORS.

### Lỗi Q — HSTS/CSP không thấy trong mock HTTP

HSTS phụ thuộc HTTPS/trusted forwarding, CSP phải cấu hình chủ động và đặt trên **HTML document** nếu muốn bảo vệ frontend. Một CSRF session test không tự kiểm tra cả hai; thêm staging HTTPS/browser E2E và test response owner.

### Lỗi R — GET URL bất thường trả 400, tưởng token bị từ chối

`StrictServerWebExchangeFirewall` (Security 6.4+) hoặc proxy/parser có thể reject semicolon, encoded slash hoặc invalid method trước `CsrfWebFilter`. Dùng URL canonical cho CSRF tests; giữ firewall tests độc lập với test token.

### Lỗi S — Sau rolling deploy, một số POST 403 ngẫu nhiên

GET có thể ở pod A và POST vào pod B mà session store không chia sẻ. Kiểm tra Spring Session/Redis, serialization, session affinity, rolling version compatibility, proxy cookie scope và token handler. Nếu chỉ tăng retries có thể lặp side effect; sửa nhất quán session store thay vì disable CSRF.

### Lỗi T — Test song song gây rò counter/session cookie

Shared `ApplicationContext` có `OrderCounter` chung; test `@BeforeEach` reset nhưng chạy song song có thể tranh chấp. Cô lập fixture/test instance hoặc không chạy song song suite này, không dùng static mutable counter và không chia sẻ session cookies giữa các test độc lập.

## 21. Ma trận hồi quy vòng đời session và CSRF token

| ID | Kịch bản | Cookie/session | Token | Kỳ vọng theo fixture |
| --- | --- | --- | --- | --- |
| M01 | GET `/public/ping` | Chưa có | Không dùng | 200; không cần tạo session chỉ vì CSRF |
| M02 | GET `/public/unused-token` | Chưa có | Chỉ lấy reference Mono | 200; không yêu cầu `Set-Cookie` do CSRF |
| M03 | GET `/csrf` | Chưa có | Consume Mono | 200, token envelope + `SESSION` |
| M04 | GET `/test/session/start` | Mock user | Không consume token | 200, session được start |
| M05 | POST `/orders`, user authenticated | S1 | Thiếu token | 403; counter 0 |
| M06 | POST `/orders`, user authenticated | S1 | Sai token | 403; counter 0 |
| M07 | POST `/orders`, user authenticated | S1 | Token M1 từ S1 | 200; counter 1 |
| M08 | POST `/orders`, mock user | Không gửi S1 | M1 từ S1 | 403 |
| M09 | POST `/orders` | S2 | M1 từ S1 | 403 |
| M10 | POST `/orders` | S2 | M2 từ S2 | 200 |
| M11 | POST form `/orders` | S1 | Parameter `_csrf` đúng | 200 |
| M12 | POST form `/orders` | S1 | Parameter sai | 403 |
| M13 | POST `/test/session/invalidate` | S1 | M1 hợp lệ | Invalidate thành công |
| M14 | POST `/orders` sau invalidate | S1 cũ | M1 cũ | Không được xử lý |
| M15 | GET `/csrf` sau invalidate | Session mới | Bootstrap token mới | 200, session/token mới hợp lệ |
| M16 | `WebSession.changeSessionId()` | Session mock | Không bắt buộc rotate CSRF | ID đổi, attribute giữ |
| M17 | `WebSession.setMaxIdleTime` | Session mock | Không áp | Config duration được lưu |
| M18 | Sau idle timeout thật | Cookie session cũ | Token cũ | Không được xử lý |
| M19 | Sau login thật | Session cookie mới nhất | Token mới hợp lệ | Authenticated + CSRF pass |
| M20 | Sau logout thật | Cookie cũ | Token cũ | Không được xử lý |
| M21 | API Bearer-only GET không token | Không session | Không liên quan CSRF | 401 |
| M22 | OPTIONS preflight origin allowlisted | Không cookie | Không cần CSRF | CORS headers đúng |
| M23 | Cookie repo SPA raw header | XSRF cookie | Header raw | Kết quả theo handler tùy chỉnh |
| M24 | HTTPS public HTML | Cookie flags đúng | Form/meta token | CSP/HSTS và browser policy riêng |
| M25 | GET ở pod A, POST ở pod B | S1 shared | M1 | Pass nếu session store consistent |

### 21.1. Độ tin cậy của từng lớp test

| Cấp kiểm thử | Chứng minh được | Không tự chứng minh |
| --- | --- | --- |
| Unit `MockWebSession` | Session started/attributes/ID/invalidate APIs | Cookie HTTP/CSRF filter |
| Unit `ServerCsrfTokenRepository` | Raw token generate/save/load/delete | Request handler XOR và session cookie |
| Mock `WebTestClient` `csrf()` | Handler/authorization khi điều kiện CSRF giả lập hợp lệ | Token thật và session persistence |
| Mock WebTestClient GET/POST | `Mono<CsrfToken>` subscribe, session cookie, actual token validation | HTTP parser/TLS/browser cookie behavior |
| `RANDOM_PORT` | Server thật, authentication credential, cookies, CSRF filter | CDN/gateway/browser SameSite |
| Browser E2E HTTPS staging | Full cookie/CORS/CSP/HSTS/client flow | Không tự chứng minh các site/replica ngoài môi trường staging |

### 21.2. Điều kiện dừng release

Một browser POST có session cookie nhưng **thiếu/nhầm CSRF token** mà vẫn tạo đơn là regression bảo mật cần dừng release để điều tra. Một token session S1 bị chấp nhận ở session S2 **với WebSession repository** cũng cần xem xét; trước hết chắc chắn tests không dùng `csrf()` bypass và sessions thực sự độc lập.

## 22. Bài tập thực hành

### Bài 1 — Chứng minh `Mono<CsrfToken>` thực sự được subscribe

Dùng fixture ở mục 4 và viết ba GET tests: `/public/ping`, `/public/unused-token`, `/csrf`. So sánh có hay không có session cookie. Giải thích vì sao chỉ lấy `exchange.getAttribute(CsrfToken.class.getName())` chưa đồng nghĩa repository đã tạo token.

### Bài 2 — Ghi và nạp token trong đúng WebSession

Gọi `GET /csrf` để lấy S1/M1, rồi POST `/orders` với `Cookie: SESSION=S1` và `X-CSRF-TOKEN=M1`. Viết negative test cùng session nhưng thiếu header và header sai. Dùng `OrderCounter` chứng minh request bị chặn không thực hiện nghiệp vụ.

### Bài 3 — Đổi session không được dùng token cũ

Bootstrap S1/M1 và S2/M2 độc lập. Thử POST S2/M1 (phải bị từ chối) và S2/M2 (được đi tiếp). Giải thích vì sao **không được tự gửi cookie S1** trong request bootstrap S2 nếu muốn test hai sessions khác nhau.

### Bài 4 — Kiểm tra explicit session start

Tạo một route test-only chỉ gọi `exchange.getSession().doOnNext(WebSession::start)` và một route chỉ lấy `exchange.getSession()`. So sánh response cookies khi không có component khác tự tạo session. Vì sao `WebSession` instance được tạo chưa chắc đã được persisted?

### Bài 5 — Test session invalidation

Từ S1/M1, gọi `POST /test/session/invalidate` với cookie/token hợp lệ. Sau đó gửi POST `/orders` dùng S1/M1 cũ, kỳ vọng không tạo order. Bootstrap session mới và kiểm tra token mới hợp lệ. Phân biệt “session invalidated” với “session expired sau idle timeout”.

### Bài 6 — `changeSessionId()` khác CSRF rotation

Trong unit test `MockWebSession`, thêm attribute, gọi `changeSessionId()` và assert ID đổi trong khi attribute vẫn được giữ. Giải thích vì sao test này **không thể khẳng định** CSRF token tự rotate khi authentication success. Thiết kế thêm test auth flow thật nếu yêu cầu session fixation protection.

### Bài 7 — Session timeout có kiểm soát

Cấu hình một session store/time source cho test môi trường phù hợp. Tạo S1/M1, xác nhận POST hợp lệ, cho session thực sự expire theo TTL, rồi thử POST S1/M1. Đảm bảo frontend không poll/keepalive làm reset idle timer. Không dùng `Thread.sleep` dài trong unit tests.

### Bài 8 — Thymeleaf hidden input

Thêm form page `GET /orders/new` bằng Thymeleaf WebFlux. Expose token qua `@ControllerAdvice` hoặc integration đã có, xác nhận HTML chứa field `_csrf` và session cookie. POST form với field đúng/sai và cùng S1, so kết quả. Tại sao JSON `GET /csrf` test pass **không đủ** để chứng minh Thymeleaf render field?

### Bài 9 — Cookie repository và XOR handler

Thay WebSession repository bằng `CookieServerCsrfTokenRepository.withHttpOnlyFalse()`. So sánh `XSRF-TOKEN` raw cookie và token handler expose qua `GET /csrf`. Test raw-header POST theo handler mặc định vs một handler được thiết kế hỗ trợ raw value. Đánh giá tradeoff BREACH và token binding; không cho rằng cookie repo tự gắn với WebSession.

### Bài 10 — CORS và cross-origin SPA

Frontend `https://app.example.com` gọi API `https://api.example.com`. Viết OPTIONS preflight tests cho origin hợp lệ và không hợp lệ, không thêm `csrf()` vào OPTIONS. Kiểm tra cookie host-only của API có được JS của SPA đọc bằng `document.cookie` hay không; thiết kế JSON token bootstrap hoặc BFF same-origin phù hợp.

### Bài 11 — HTTP Basic thật trên cổng ngẫu nhiên

Với `@SpringBootTest(RANDOM_PORT)` và user store test-only, gọi `GET /csrf` qua network, giữ session cookie, rồi POST `/orders` bằng Basic credentials và actual header token. Thử thiếu cookie, sai token, sai password để xác định 401/403. Không dùng `mockUser()` hoặc `csrf()` để thay HTTP credential và token.

### Bài 12 — Multi-node session store

Chạy hai replicas với shared Spring Session/Redis test setup. Gọi GET token qua pod A, POST qua pod B và ngược lại, sau đó thử invalidation/logout và rolling deployment. Đo session load errors, authentication failures, CSRF rejections theo metrics tách biệt; tuyệt đối không log session ID/CSRF token.

### Bài 13 — Có lỗi 403 sau proxy rewrite

Ingress chuyển `/portal/api/orders` thành `/orders`. Thiết kế test kiểm tra canonical URL trong Spring Security matcher, session cookie `Path`, CORS origin và CSRF header sau rewrite. Giải thích tại sao một 403 có thể do chọn sai security chain thay vì mất token.

## 23. Checklist review trước khi đưa CSRF session flow vào production

- [ ] Xác nhận ứng dụng là **Reactive WebFlux**, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`, không nhầm `HttpSecurity` Servlet.
- [ ] `spring-security-test`, Spring Framework và Boot artifacts cùng dòng tương thích.
- [ ] `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` được cấu hình đúng trong mock tests.
- [ ] Test context nạp đúng `CsrfWebFilter`/`WebSessionServerCsrfTokenRepository` và handler đã được cấu hình.
- [ ] `Mono<CsrfToken>` được lấy bằng `exchange.getAttribute(CsrfToken.class.getName())`, đúng Reactive package.
- [ ] Endpoint/view thực sự **consume publisher**; không chỉ lấy reference Mono rồi trả publisher khác.
- [ ] Không gọi `block()` hoặc `subscribe()` thủ công trên WebFlux request event loop để ép token creation.
- [ ] `GET /csrf` dùng `Cache-Control: no-store` và không ghi token ra log/query string/analytics.
- [ ] Có test GET không consume Mono không tạo session **chỉ vì CSRF** trong fixture đã cô lập.
- [ ] Có test GET bootstrap phát token và `SESSION` cookie tương ứng, đúng session manager/cookie name.
- [ ] Có test `POST /orders` **không** token bị 403 và side effect không xảy ra.
- [ ] Có test POST với session đúng/token đúng được xử lý; các negative tests có positive control.
- [ ] Có test token của S1 không được chấp nhận với S2 khi dùng **WebSession repository**.
- [ ] Actual token tests **không** dùng `mutateWith(csrf())` để tránh bypass cơ chế cần kiểm tra.
- [ ] Không assert exposed token strings luôn bằng nhau trên hai GET khi dùng XOR/BREACH.
- [ ] Có test repository raw `generateToken`/`saveToken`/`loadToken` và `saveToken(null)` ở cấp unit khi cần.
- [ ] Đã phân biệt `WebSession.start()` với `getSession()` và thời điểm store save/cookie issuance.
- [ ] Có test `WebSession.changeSessionId()`/session fixation theo threat model, không đồng nhất với token rotation.
- [ ] Có test `WebSession.invalidate()` và replay token cũ bị từ chối, không lộ test-only invalidation route ra production.
- [ ] Session timeout test xác minh **TTL hết thật**, không chỉ bỏ cookie hoặc ngủ tùy ý.
- [ ] Login/logout thật được test bằng authentication flow và cookie jar, không suy từ `mockUser()`.
- [ ] Có chính sách xử lý lỗi session expired cho SPA, không tự resubmit POST side-effect vô hạn.
- [ ] Cookie authentication bảo vệ `HttpOnly/Secure/SameSite/Path/Domain` theo public HTTPS origin.
- [ ] Nếu dùng cookie CSRF repository, raw-vs-XOR handler được test và đánh giá BREACH/cookie injection.
- [ ] CORS preflight OPTIONS được test riêng, không nhầm với CSRF và không cấp credentialed CORS cho origin lạ.
- [ ] CSP trên HTML frontend, HSTS trên HTTPS hostname, HTTP firewall và session cookies có regression tests riêng.
- [ ] Có fallback chain và matcher đúng nếu app có API Bearer-only + browser session chains.
- [ ] `@WebFluxTest` slice import custom Security config; `@SpringBootTest` full context bảo đảm wiring giống runtime.
- [ ] Live HTTP test dùng Basic/Bearer/form credential và actual CSRF cookie/header, không dùng mock mutators qua TCP.
- [ ] Multi-pod session store/serialization được xác minh trong rolling deployment.
- [ ] Metrics/logs redacted: không ghi session ID, token CSRF, JWT, passwords hoặc raw cookies.

## 24. Nguồn tài liệu chính thức

1. [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — `CsrfWebFilter`, `Mono<CsrfToken>` exchange attribute, request handler, BREACH, WebSession repository, form và session timeout.
2. [Spring Security 7.0 — Reactive CSRF (pinned)](https://docs.spring.io/spring-security/reference/7.0/reactive/exploits/csrf.html) — ví dụ cụ thể `@ControllerAdvice`/`@ModelAttribute`, session timeout và logout.
3. [Spring Security API — CsrfWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html) — CSRF synchronizer token filter, request attribute `CsrfToken.class.getName()` và subscription/save behavior.
4. [Spring Security API — ServerCsrfTokenRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html) — `generateToken`, `saveToken`, `loadToken` và delete semantics.
5. [Spring Security API — WebSessionServerCsrfTokenRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html) — WebSession attribute storage, header/parameter/session attribute customization.
6. [Spring Security API — ServerCsrfTokenRequestHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestHandler.html) — expose token và resolve actual token.
7. [Spring Security API — XorServerCsrfTokenRequestAttributeHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html) — BREACH masking từ dòng 6.
8. [Spring Security API — CookieServerCsrfTokenRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html) — cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN`.
9. [Spring Framework API — WebSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html) — `start`, `getAttributes`, `changeSessionId`, `invalidate`, `save`, `isExpired`, idle timeout.
10. [Spring Framework API — MockWebSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mock/web/server/MockWebSession.html) — unit testing WebSession lifecycle.
11. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — mock application context/client vs live HTTP.
12. [Spring Security — Reactive Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) và [WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — `csrf()` test mutator, `apply(springSecurity())`.
13. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`/`ServerHttpSecurity` và multi-chain matcher.
14. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html), [Reactive Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html), [Reactive Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — các lớp phòng vệ khác với CSRF.
15. [Spring Session — Common Configurations](https://docs.spring.io/spring-session/reference/configuration/common.html) — WebFlux session id resolver/cookie và khả năng tùy chỉnh.
16. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`/`@SpringBootTest`/`RANDOM_PORT` và test setup theo version.
17. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — synchronizer token, session/cookie properties, signed double-submit và defense in depth.

**Câu hỏi tự đánh giá:** Tại sao `CsrfWebFilter` expose `Mono<CsrfToken>` chứ không nhất thiết một token đã được tạo? Điều gì xảy ra nếu controller chỉ lấy Mono rồi bỏ không dùng? `exchange.getSession()` đã chắc làm phát `SESSION` cookie chưa? Khi nào WebSession bắt đầu và lưu attributes? Làm sao kiểm tra cùng token với session S1 được phép nhưng với S2 bị từ chối? Vì sao `changeSessionId()` không chứng minh CSRF token đã rotate? Một POST dùng token cũ sau logout trả 401 thay vì 403 có nhất thiết là lỗi không? Giá trị masked từ hai GET khác nhau nói gì về raw expected token? Nếu GET ở pod A, POST ở pod B thất bại, bạn sẽ kiểm tra những thành phần nào? Và cần thêm những phép kiểm thử nào ngoài mock WebTestClient để chắc chắn cookie, CORS, CSP/HSTS và TLS/proxy hoạt động đúng?
