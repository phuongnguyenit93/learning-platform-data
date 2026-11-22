# csrf() và các trường hợp token thiếu, sai hoặc hợp lệ

## 1. Bối cảnh và mục tiêu

**Đề bài:** csrf() và các trường hợp token thiếu, sai hoặc hợp lệ.  
**Nhóm kiến thức:** Kiểm thử HTTP.  
**Module:** Spring Security - reactive.  
**Môi trường ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring WebFlux, WebTestClient, JUnit 5.

CSRF (*Cross-Site Request Forgery*) là nguy cơ một trang không đáng tin khiến browser của người dùng đã đăng nhập gửi request thay đổi trạng thái đến ứng dụng. Khi browser tự đính kèm cookie session hoặc credential có tính ambient, server có thể nhầm request giả mạo thành ý định của người dùng.

Cơ chế CSRF token yêu cầu request thay đổi trạng thái phải mang một giá trị mà browser không tự gửi hộ như cookie. Trên Spring WebFlux, `CsrfWebFilter` kiểm tra token theo `ServerCsrfTokenRepository` và `ServerCsrfTokenRequestHandler` trước khi request được cho phép thực hiện hành động.

Bài này tập trung **kiểm thử HTTP có đối chứng**. Một test tốt phải kiểm đồng thời:

1. **HTTP status**: thiếu/sai CSRF token thường dẫn tới 403; hợp lệ cộng với authentication/authorization đúng dẫn đến status nghiệp vụ.
2. **Không có side effects** khi request bị chặn: không tăng counter, không ghi DB hoặc phát event.
3. **Khả năng cô lập nguyên nhân**: 401 do chưa authenticated, 403 do token CSRF hoặc thiếu quyền role/scope có thể trông giống nhau nếu test không chuẩn bị các điều kiện khác.

### Sau bài bạn sẽ biết

- Phân biệt `ServerHttpSecurity.csrf(...)` của ứng dụng và `SecurityMockServerConfigurers.csrf()` của **Spring Security Test**.
- Cấu hình `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` rồi dùng `mutateWith(csrf())` đúng WebFlux.
- Kiểm GET, POST, PUT, PATCH, DELETE với token missing/invalid/valid.
- Kiểm authentication và authorization độc lập với CSRF.
- Dùng `WebSessionServerCsrfTokenRepository` mặc định, đọc CSRF token qua GET và gửi lại **cùng SESSION cookie** để test gần browser thật.
- Hiểu `XorServerCsrfTokenRequestAttributeHandler` (masked token chống BREACH), `CookieServerCsrfTokenRepository` và lưu ý SPA.
- Test đổi token giữa hai sessions, token bị sửa hoặc token không có cookie/session.
- Nhận biết những thứ test mutator **chưa** mô phỏng: cookie flags, SameSite, CORS, login/logout rotation và proxy.
- Tạo dự án WebFlux Java 17+, 19 HTTP tests mẫu, checklist lỗi thường gặp và bài tập.

Không cần tắt CSRF để test chạy. Nội dung mã được rà soát tĩnh; kết quả chạy Gradle chỉ có thể xác nhận sau khi thực thi trong project thật.

## 2. CSRF là gì, tại sao browser session gặp rủi ro?

Ví dụ một trang attacker tạo form:

~~~html
<form method="post" action="https://bank.example.invalid/transfer">
  <input type="hidden" name="amount" value="500">
  <input type="hidden" name="destination" value="attacker">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Khi người dùng truy cập trang này, browser có thể gửi credential cookie đến `bank.example.invalid` theo cookie/SameSite policy. Server chỉ kiểm session mà không yêu cầu CSRF token sẽ có nguy cơ thực hiện giao dịch không do người dùng chủ ý.

Phòng vệ bằng CSRF token dựa trên hai yếu tố khác nhau:
- **Session cookie** cho biết ngữ cảnh đăng nhập, có thể tự được browser đính kèm.
- **CSRF token** phải được client đọc từ trang/response tin cậy rồi chủ động gửi trong form field hoặc header.

CSRF token **không phải mật khẩu** và không tự xác thực user. Token hợp lệ nhưng user chưa đăng nhập vẫn không được phép truy cập endpoint cần authentication.

**CORS khác CSRF:** Browser có thể bị giới hạn đọc cross-origin response nhưng vẫn có thể gửi một số form requests. Chỉ cấu hình CORS không thay CSRF protection. SameSite cookie và kiểm Origin/Referer là các lớp bổ sung; không nên coi một mình chúng là bảo vệ đầy đủ trong mọi luồng session.

### 2.1. Các phương thức được bảo vệ theo mặc định

| HTTP method | Có cần CSRF mặc định? | Ghi chú |
|---|---|---|
| GET | Không | Chỉ nên đọc, không tạo side effect |
| HEAD | Không | Không dùng để thay đổi dữ liệu |
| OPTIONS | Không | CORS/preflight vẫn có policy riêng |
| TRACE | Không theo default matcher | Thường nên hạn chế TRACE ở hạ tầng |
| POST | Có | Create, login, logout, submit |
| PUT | Có | Replace |
| PATCH | Có | Partial update |
| DELETE | Có | Remove |

Spring Security phân loại “unsafe” dựa trên HTTP method, **không dựa trên tên endpoint**. Ví dụ `POST /health` nếu được route cho phép vẫn chịu CSRF protection theo mặc định; `GET /deleteAccount` không cần CSRF theo default matcher dù hành vi là không an toàn — lỗi nằm ở thiết kế sử dụng GET.

### 2.2. Những trạng thái HTTP cần phân biệt

Giả sử endpoint `POST /api/mutations` yêu cầu user có role EDITOR:

| Điều kiện | Kết quả mong đợi | Controller được chạy? |
|---|---|---|
| EDITOR + không CSRF token | 403 Forbidden | Không |
| EDITOR + token sai | 403 Forbidden | Không |
| EDITOR + token hợp lệ | 201 Created | Có |
| Không authentication + token hợp lệ | 401 Unauthorized | Không |
| VIEWER đã authenticated + token hợp lệ | 403 Forbidden | Không |
| GET public /health không auth, không token | 200 OK | GET chỉ đọc |
| GET protected /api/mutations không auth | 401 Unauthorized | Không |
| GET protected /api/mutations + EDITOR, không CSRF | 200 OK | GET chỉ đọc |

Nếu cùng thiếu authentication và CSRF, filter order có thể làm kết quả đầu tiên là 403 thay vì 401. **Để test CSRF, luôn cung cấp Authentication đúng**; để test 401, hãy cung cấp CSRF hợp lệ và cố tình bỏ credentials. Đây là cách tránh test pass vì sai nguyên nhân.

## 3. Phân biệt hai lời gọi csrf()

### 3.1. ServerHttpSecurity.csrf(...) — ứng dụng thật

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/health").permitAll()
            .anyExchange().authenticated())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

Đoạn trên là **snippet**, cần imports và những config xác thực phù hợp. `ServerHttpSecurity.csrf(...)` cấu hình `CsrfWebFilter`. Trong Spring Security WebFlux, CSRF được **bật theo mặc định**; khai báo tường minh giúp người học biết test đang bảo vệ điều gì.

Cấu hình sau **bỏ qua** CSRF, không phải cách tạo token hợp lệ:

~~~java
// Anti-pattern nếu mục đích là kiểm thử CSRF:
.csrf(csrf -> csrf.disable())
~~~

Một negative test POST thiếu token mà vẫn trả 201 khi CSRF disabled là dấu hiệu lỗ hổng/thay đổi chính sách, không phải test thành công.

### 3.2. SecurityMockServerConfigurers.csrf() — test-only

Trong `spring-security-test` cho reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
    .post().uri("/api/mutations")
    .exchange()
    .expectStatus().isCreated();
~~~

Đây là **snippet**, chỉ pass khi authentication/authorization, request body và controller đều đúng. `mutateWith(csrf())` thêm **valid CSRF test context** cho request trong mock WebFlux. Nó không yêu cầu bạn hardcode token, không xác thực user hộ và không cấp role.

**Sai import phổ biến:** `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf` dùng cho Servlet/MockMvc, không phải WebTestClient. Ví dụ Servlet có thể có `csrf().useInvalidToken()`; không bê nguyên helper đó sang WebFlux. Reactive negative test gửi raw header token sai cùng expected token repository/session hoặc đơn giản gửi một raw invalid header mà không gọi valid `csrf()` mutator.

### 3.3. Setup WebTestClient phải đúng

Tài liệu Spring Security hướng dẫn:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Đây là **snippet** dùng trong test đã inject `ApplicationContext`. `apply(springSecurity())` đăng ký Spring Security reactive test support cho mock server. Nếu tạo client sai bằng `bindToController(...)` mà không gắn security chain, negative CSRF test có thể pass/fail sai lý do. Nếu dùng HTTP server thật với `@SpringBootTest(RANDOM_PORT)`, đừng giả định test mutator hoạt động y hệt browser; hãy dùng **token/cookie được server thật phát**.

## 4. Token repositories và request handlers

### 4.1. CSRF WebFlux pipeline

~~~text
POST /api/mutations
    |
    v
CsrfWebFilter:
    - method có cần CSRF?
    - load/generate expected token từ ServerCsrfTokenRepository
    - resolve token client gửi qua header/form
    - so sánh token sau request handler
    |
    +--- missing/mismatch -> 403 -> không gọi business
    |
    +--- match -> Authentication/Authorization
                        |
                        +--- no user -> 401
                        +--- insufficient role -> 403
                        +--- valid -> controller/service -> 201
~~~

Default `WebSessionServerCsrfTokenRepository` lưu expected token trong `WebSession`. Khi session hết hạn hoặc bị rotate/invalidated, token cũ thường không còn dùng được. Một CSRF token lấy từ session A không được sử dụng cùng session B.

### 4.2. Deferred token và exchange attribute

`CsrfWebFilter` đưa `Mono<CsrfToken>` vào `ServerWebExchange` dưới key:

~~~java
CsrfToken.class.getName()
~~~

Token có thể được tạo/lưu **lazily**, nghĩa là nếu bạn mở GET mà không render/subscribe token, chưa chắc đã có SESSION cookie và expected token để dùng trong POST tiếp theo. Vì vậy demo dùng một `GET /csrf-token` endpoint subscribe vào Mono và trả token đã expose.

### 4.3. XOR/BREACH masking

Kể từ Spring Security 6.0, default WebFlux `XorServerCsrfTokenRequestAttributeHandler` giúp chống rủi ro BREACH khi token được in vào compressed response. Nó expose **masked token** có thành phần random; khi request gửi lại token, handler giải mã và so với expected secret trong repository.

Hệ quả trong test:

- Đừng hardcode token toàn hệ thống.
- Đừng assert string của exposed token phải bằng nhau qua mọi GET.
- Gửi **đúng token value được GET trả** với **đúng session**.
- Một raw random header như `X-CSRF-TOKEN: wrong` không tự hợp lệ chỉ vì header có mặt.
- Nếu đổi request handler/repository, phải kiểm cả masked-vs-raw protocol.
- Không tắt XOR/masking chỉ vì negative test khó viết.

### 4.4. CookieServerCsrfTokenRepository cho SPA

Spring WebFlux còn có `CookieServerCsrfTokenRepository`. Default cookie name `XSRF-TOKEN`, header name `X-XSRF-TOKEN` và form parameter `_csrf`. Trường hợp frontend thật cần đọc CSRF cookie từ JavaScript, snippet:

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

Đây là snippet, **không** có nghĩa mọi cookie đều nên mở HttpOnly. Cookie đăng nhập/session vẫn cần HttpOnly, Secure, SameSite phù hợp.

**Quan trọng:** Ở Spring Security 6.x, cookie có thể lưu **raw token**, trong khi XOR request handler mặc định mong masked token qua header/form. SPA trực tiếp copy raw cookie sang header có thể cần custom `ServerCsrfTokenRequestHandler` phù hợp. Không suy ra chỉ cần `withHttpOnlyFalse()` là mọi setup AJAX hoạt động; test real browser flow và những lần login/logout refresh CSRF token.

## 5. Demo WebFlux Java 17+ và Gradle

Tạo project Spring Initializr (Gradle Groovy, Java 17+, Boot 3.5.x, Reactive Web, Security, Test). Phần `dependencies` trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

Đây chỉ là **dependencies block**, giữ plugins, Java toolchain, repositories, Gradle wrapper do Initializr tạo. Không thêm `spring-boot-starter-web` nếu inbound cần WebFlux; MVC và WebFlux cùng có mặt trong Boot 3.x có thể khiến Servlet được ưu tiên.

Cấu trúc:

~~~text
src/main/java/demo/csrf/
  CsrfLearningApplication.java
  SecurityConfig.java
  MutationStore.java
  MutationController.java
  CsrfTokenController.java
src/test/java/demo/csrf/
  CsrfHttpTests.java
~~~

### 5.1. CsrfLearningApplication.java

~~~java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfLearningApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfLearningApplication.class, args);
    }
}
~~~

### 5.2. SecurityConfig.java

~~~java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails editor = User.withUsername("learner")
            .password(encoder.encode("study-pass"))
            .roles("EDITOR")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-pass"))
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(editor, viewer);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/csrf-token").permitAll()
                .pathMatchers("/api/mutations", "/api/mutations/**")
                    .hasRole("EDITOR")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Giải thích:
- `httpBasic` là cơ chế test/non-browser demo cho credentials hợp lệ; browser production thường dùng session cookie/form login hoặc token workflow riêng.
- Password được hash bằng delegating encoder, không dùng `{noop}` trong test application.
- Role EDITOR yêu cầu `ROLE_EDITOR`, VIEWER không có.
- CSRF bật rõ ràng, cả POST/PUT/PATCH/DELETE chịu bảo vệ.
- `GET /csrf-token` public chỉ để phát CSRF token theo session; **không cấp authentication**. Nếu production expose endpoint tương tự, phải áp CORS, cache, SameSite và privacy policy đúng.
- Không tắt CSRF hoặc permitAll mutation routes.
- HTTP Basic credential demo chỉ dùng trên localhost; production phải dùng TLS và secret management.

### 5.3. MutationStore.java: assert zero side effect

~~~java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MutationStore {

    public record Receipt(String operation, int totalMutations) {
    }

    private final AtomicInteger counter = new AtomicInteger();

    public int count() {
        return counter.get();
    }

    public void resetForTest() {
        counter.set(0);
    }

    public Mono<Receipt> mutate(String operation) {
        return Mono.fromSupplier(() ->
            new Receipt(operation, counter.incrementAndGet()));
    }
}
~~~

Store chỉ là bộ đếm thay cho database. Khi security filter từ chối request, business Mono không được subscribe, counter phải giữ **0**. Nếu production có DB, event bus hoặc email, thêm assertions đảm bảo transaction/event side effects thực sự không xảy ra.

### 5.4. MutationController.java: các HTTP methods cần test

~~~java
package demo.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MutationController {

    public record MutationCommand(String value) {
    }

    public record CounterView(int mutations) {
    }

    private final MutationStore store;

    public MutationController(MutationStore store) {
        this.store = store;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/mutations")
    public Mono<CounterView> list() {
        return Mono.just(new CounterView(store.count()));
    }

    @PostMapping("/api/mutations")
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<MutationStore.Receipt> create(
            @RequestBody Mono<MutationCommand> command) {
        return command.flatMap(c -> store.mutate("POST"));
    }

    @PutMapping("/api/mutations/{id}")
    public Mono<MutationStore.Receipt> put(
            @PathVariable int id,
            @RequestBody Mono<MutationCommand> command) {
        return command.flatMap(c -> store.mutate("PUT"));
    }

    @PatchMapping("/api/mutations/{id}")
    public Mono<MutationStore.Receipt> patch(
            @PathVariable int id,
            @RequestBody Mono<MutationCommand> command) {
        return command.flatMap(c -> store.mutate("PATCH"));
    }

    @DeleteMapping("/api/mutations/{id}")
    public Mono<MutationStore.Receipt> delete(
            @PathVariable int id) {
        return store.mutate("DELETE");
    }
}
~~~

Các path variables và body ở demo được nhận để mô phỏng HTTP, không lưu record thật. Sản phẩm cần validation/ACL và xử lý lỗi nghiệp vụ riêng. `GET /api/mutations` chỉ đọc counter; unsafe methods ghi counter đúng một lần nếu pass.

### 5.5. CsrfTokenController.java: GET token thực từ WebSession

~~~java
package demo.csrf;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class CsrfTokenController {

    public record CsrfResponse(String headerName, String token) {
    }

    @GetMapping("/csrf-token")
    public Mono<CsrfResponse> issue(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter is not active"));
        }

        return token.map(t ->
            new CsrfResponse(t.getHeaderName(), t.getToken()));
    }
}
~~~

Spring Security WebFlux đặt token Mono vào request attribute. Việc trả `Mono<CsrfResponse>` từ controller làm token được load/subscribe trong response, nhờ đó session repository có thể phát/lưu CSRF token. Default `WebSessionServerCsrfTokenRepository` lưu expected token trong WebSession, client nhận `SESSION` cookie khi session start.

Trong Spring 6.x, `t.getToken()` đã qua request handler và có thể là **masked token**. Gửi lại chính value được expose qua header `t.getHeaderName()`, **cùng session**.

**Không** đưa CSRF token vào shared public cache hoặc log token, không cho hostile origin CORS-read credentialed `/csrf-token`. Token không phải bearer credential, nhưng rò token có thể làm giảm hiệu quả CSRF defense nếu kẻ xấu cũng điều khiển session context.

## 6. WebTestClient tests: 19 tình huống rõ nghĩa

Sử dụng `@SpringBootTest(webEnvironment=MOCK)` và WebTestClient bind tới ApplicationContext, có `springSecurity()`. Phương thức `csrf()` dùng cho positive paths; raw header/session dùng cho negative và gần-browser cases.

File `src/test/java/demo/csrf/CsrfHttpTests.java`:

~~~java
package demo.csrf;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.MOCK)
class CsrfHttpTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    MutationStore store;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        store.resetForTest();
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private void editor(HttpHeaders headers) {
        headers.setBasicAuth("learner", "study-pass");
    }

    private void viewer(HttpHeaders headers) {
        headers.setBasicAuth("viewer", "viewer-pass");
    }

    private WebTestClient.ResponseSpec post(
            WebTestClient web, boolean withAuth) {

        var request = web.post()
            .uri("/api/mutations")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"));

        if (withAuth) {
            request.headers(this::editor);
        }
        return request.exchange();
    }

    @Test
    void healthGetDoesNotRequireCsrf() {
        client.get().uri("/health")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
        assertEquals(0, store.count());
    }

    @Test
    void authenticatedGetWorksWithoutCsrf() {
        client.get().uri("/api/mutations")
            .headers(this::editor)
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.mutations").isEqualTo(0);
        assertEquals(0, store.count());
    }

    @Test
    void unauthenticatedGetIsUnauthorized() {
        client.get().uri("/api/mutations")
            .exchange().expectStatus().isUnauthorized();
        assertEquals(0, store.count());
    }

    @Test
    void postMissingCsrfIsForbidden() {
        post(client, true)
            .expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void postInvalidCsrfHeaderIsForbidden() {
        client.post().uri("/api/mutations")
            .headers(this::editor)
            .header("X-CSRF-TOKEN", "not-valid-token")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void postValidCsrfIsCreated() {
        post(client.mutateWith(csrf()), true)
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.operation").isEqualTo("POST")
            .jsonPath("$.totalMutations").isEqualTo(1);
        assertEquals(1, store.count());
    }

    @Test
    void csrfDoesNotReplaceAuthentication() {
        post(client.mutateWith(csrf()), false)
            .expectStatus().isUnauthorized();
        assertEquals(0, store.count());
    }

    @Test
    void csrfDoesNotReplaceAuthorization() {
        client.mutateWith(csrf())
            .post().uri("/api/mutations")
            .headers(this::viewer)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void putMissingCsrfIsForbidden() {
        client.put().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void patchMissingCsrfIsForbidden() {
        client.patch().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void deleteMissingCsrfIsForbidden() {
        client.delete().uri("/api/mutations/1")
            .headers(this::editor)
            .exchange().expectStatus().isForbidden();
        assertEquals(0, store.count());
    }

    @Test
    void putValidCsrfWorks() {
        client.mutateWith(csrf())
            .put().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isOk();
        assertEquals(1, store.count());
    }

    @Test
    void patchValidCsrfWorks() {
        client.mutateWith(csrf())
            .patch().uri("/api/mutations/1")
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "changed"))
            .exchange().expectStatus().isOk();
        assertEquals(1, store.count());
    }

    @Test
    void deleteValidCsrfWorks() {
        client.mutateWith(csrf())
            .delete().uri("/api/mutations/1")
            .headers(this::editor)
            .exchange().expectStatus().isOk();
        assertEquals(1, store.count());
    }

    private record Issued(
            String session, CsrfTokenController.CsrfResponse token) {
    }

    private Issued issue() {
        EntityExchangeResult<CsrfTokenController.CsrfResponse> reply =
            client.get().uri("/csrf-token")
                .exchange().expectStatus().isOk()
                .expectBody(CsrfTokenController.CsrfResponse.class)
                .returnResult();

        ResponseCookie cookie = reply.getResponseCookies()
            .getFirst("SESSION");

        assertNotNull(cookie);
        assertNotNull(reply.getResponseBody());
        assertNotNull(reply.getResponseBody().token());
        assertNotNull(reply.getResponseBody().headerName());

        return new Issued(
            cookie.getValue(), reply.getResponseBody());
    }

    private WebTestClient.ResponseSpec postWithSession(
            String cookie, String header, String token) {

        return client.post().uri("/api/mutations")
            .cookie("SESSION", cookie)
            .header(header, token)
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange();
    }

    @Test
    void issuedTokenAndMatchingSessionAreAccepted() {
        Issued issued = issue();

        postWithSession(
            issued.session(),
            issued.token().headerName(),
            issued.token().token())
            .expectStatus().isCreated();

        assertEquals(1, store.count());
    }

    @Test
    void missingTokenWithExistingSessionIsForbidden() {
        Issued issued = issue();

        client.post().uri("/api/mutations")
            .cookie("SESSION", issued.session())
            .headers(this::editor)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();

        assertEquals(0, store.count());
    }

    @Test
    void tamperedTokenWithExistingSessionIsForbidden() {
        Issued issued = issue();

        postWithSession(
            issued.session(),
            issued.token().headerName(),
            issued.token().token() + "-tampered")
            .expectStatus().isForbidden();

        assertEquals(0, store.count());
    }

    @Test
    void tokenOfSessionADoesNotMatchSessionB() {
        Issued a = issue();
        Issued b = issue();

        assertNotEquals(a.session(), b.session());

        postWithSession(
            b.session(),
            a.token().headerName(),
            a.token().token())
            .expectStatus().isForbidden();

        assertEquals(0, store.count());
    }

    @Test
    void issuedTokenWithoutSessionIsForbidden() {
        Issued issued = issue();

        client.post().uri("/api/mutations")
            .headers(this::editor)
            .header(
                issued.token().headerName(),
                issued.token().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "demo"))
            .exchange().expectStatus().isForbidden();

        assertEquals(0, store.count());
    }
}
~~~

### 6.1. Vì sao có 19 test methods?

**Nhóm safe methods + authentication (3):** GET public không cần token; GET protected với authentication không cần token; GET protected thiếu auth trả 401.

**Nhóm POST missing/invalid/valid (5):** Basic EDITOR nhưng không CSRF → 403; raw header sai → 403; `mutateWith(csrf())` → 201; valid CSRF thiếu authentication → 401; valid CSRF nhưng role VIEWER → 403.

**Nhóm PUT/PATCH/DELETE (6):** ba method thiếu token đều 403 và không mutate; khi valid CSRF thì 200, counter tăng một lần.

**Nhóm repository/session (5):** GET lấy expected token và SESSION; POST cùng session valid → 201; missing token → 403; tampered token → 403; token từ session A kèm cookie B → 403; token có mặt nhưng không gửi session cookie → 403.

Tổng **3 + 5 + 6 + 5 = 19**. Mọi negative test chốt `store.count()==0`, mọi successful mutation chốt `store.count()==1`.

**Test helper `csrf()` không chứng minh browser:** Nó cung cấp token hợp lệ nhờ test-only hook. Chính phần `issue()` và `postWithSession()` cho thấy session-backed expected token và exposed header thực sự khớp. Dù vậy WebTestClient mock vẫn không áp cookie SameSite/CORS/browser policy như Chrome/Firefox; cần test browser E2E khi tích hợp frontend.

### 6.2. Hạn chế của shared store

`MutationStore` là singleton trong Spring context, test reset `AtomicInteger` trước mỗi test. JUnit 5 mặc định không chạy parallel nếu chưa kích hoạt. Khi CI bật parallel tests, cần isolate context/store theo test hoặc chạy suite này sequential để không gây race và false failures.

### 6.3. Không dùng mockUser để “giả” mọi thứ

Reactive Spring Security Test còn có `mockUser()`:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("learner").roles("EDITOR"))
    .mutateWith(csrf())
    .post().uri("/api/mutations")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("value", "demo"))
    .exchange().expectStatus().isCreated();
~~~

Đây là snippet trong test class đã có imports. `mockUser()` giả Authentication; `csrf()` giả valid token. Chúng độc lập:
- `mockUser()` không tự cung cấp CSRF token.
- `csrf()` không tạo user hoặc role.
- Nếu chỉ test cả hai mock mutators, có thể bỏ sót lỗi password encoder/session cookie/browser integration.
- Bài thực hành còn dùng HTTP Basic thật trong mock server và GET CSRF/session để tăng độ tin cậy.

## 7. Chạy project và test nhanh

Trong project root:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Public health:

~~~bash
curl -i http://localhost:8080/health
~~~

Kỳ vọng HTTP 200, body `ok`. Với endpoint protected:

~~~bash
curl -i \
  -u learner:study-pass \
  -H "Content-Type: application/json" \
  -d '{"value":"demo"}' \
  http://localhost:8080/api/mutations
~~~

Kỳ vọng **403 Forbidden** vì không có CSRF token, dù Basic credentials đúng. Chỉ dùng credential demo trên localhost; HTTP Basic trên public network phải đi qua TLS và secrets management.

Để gọi thành công bằng CSRF thật:
1. GET `/csrf-token`, lưu response JSON token/headerName.
2. Lưu cookie `SESSION` từ response đó.
3. POST `/api/mutations` kèm **cùng cookie**, headerName=token value và Basic credentials hợp lệ.
4. Kỳ vọng 201, counter tăng một lần.

Chạy tests:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

**Lưu ý:** Dự kiến các tests PASS với stack được mô tả, nhưng mã mới được kiểm tra tĩnh về cấu trúc và API; bài không tuyên bố đã thực thi Gradle.

## 8. Vì sao test thiếu/sai token đôi khi trả status bất ngờ?

### 8.1. 401 vs 403 do thứ tự filters

Nếu gửi POST **vừa thiếu Authorization vừa thiếu CSRF**, `CsrfWebFilter` có thể từ chối trước Basic authentication. Khi đó response là 403. Điều này không chứng minh endpoint không yêu cầu authentication.

Cách viết test tách yếu tố:
- Để test CSRF, gửi Basic EDITOR hợp lệ, chỉ bỏ/sửa token.
- Để test 401, cung cấp valid token bằng `mutateWith(csrf())` và bỏ Authorization.
- Để test role, gửi Basic VIEWER hợp lệ và valid CSRF.
- Để test success, đủ cả Basic EDITOR + valid CSRF.

### 8.2. Mock client không đi qua đúng security chain

Lỗi:

~~~java
// Chỉ bind controller, không tích hợp security:
WebTestClient.bindToController(new MutationController(store))
    .build();
~~~

Nếu controller không có `SecurityWebFilterChain`, request POST có thể pass dù thiếu CSRF. Đừng viết test và kết luận ứng dụng được bảo vệ. Bài dùng `bindToApplicationContext(context).apply(springSecurity())` để gắn WebFlux security thật.

### 8.3. Token missing và wrong đều 403 nhưng nguyên nhân khác

CSRF missing: request không có header/form token.  
CSRF wrong: có token nhưng không match expected token/không decode đúng XOR.  
Cả hai thường cùng 403, nhưng security policy phải chặn cả hai. Dùng tests riêng, tránh chỉ assert một trường hợp.

### 8.4. Session cookie thiếu hoặc token khác session

Trong WebSession repository, token có thể đã được phát ở session A. Nếu request mới không gửi `SESSION` hoặc gửi session B, expected token server load khác; token A không hợp lệ. Test positive path bắt buộc lưu cookie từ GET và gửi lại đúng.

### 8.5. Login/logout và token rotation

Spring Security login/logout có thể tạo mới/clear token repository hoặc thay session state. Khi frontend vẫn dùng token trước login/logout, unsafe request có thể 403. Test nên gồm:
- Login POST phải có CSRF token theo cookie-based policy.
- Sau authentication success, lấy token mới trước mutation.
- Logout POST thiếu/sai CSRF bị từ chối.
- Logout/expiry khiến token cũ không thể tiếp tục dùng nếu session được invalidate.
- Multi-tab và session timeout có UX reload token hợp lý.
- Không tắt CSRF ở login/logout chỉ vì frontend gặp lỗi 403.

### 8.6. Masked token và cookie SPA

Với Spring Security 6.x mặc định `XorServerCsrfTokenRequestAttributeHandler`, token exposed thay đổi theo masking; nếu SPA đọc raw cookie `XSRF-TOKEN` và gửi ngay `X-XSRF-TOKEN`, request handler phải xử lý đúng representation. Một cấu hình custom handler cho raw header/ masked form cần test chính xác theo version. Đừng nhầm Servlet `CsrfTokenRequestHandler` với reactive `ServerCsrfTokenRequestHandler`.

## 9. Form và JSON: hai cách gửi token hợp lệ

HTML form:

~~~html
<form action="/profile" method="post">
  <input type="text" name="displayName" value="Alice">
  <input type="hidden" name="_csrf"
         value="<server-exposed-token-for-current-session>">
  <button type="submit">Save</button>
</form>
~~~

`_csrf` chỉ có giá trị khi token được render đúng vào response (ví dụ Thymeleaf/Spring Security form integration); hardcode literal như trên không phải production.

JSON/AJAX:

~~~http
POST /api/mutations HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: <token-from-trusted-response>
Cookie: SESSION=<same-session>

{"value":"demo"}
~~~

Với JSON nên đặt token trong header. Không chuyển token vào URL query vì URLs có thể lọt logs, traces, cache, analytics và history. Với multipart form, việc đọc body để lấy token có trade-off resource consumption; WebFlux có cấu hình riêng `tokenFromMultipartDataEnabled(true)`, không bật nếu không cần.

**Tên header thực:** Session repository thường trả `X-CSRF-TOKEN`; CookieServerCsrfTokenRepository thường dùng `X-XSRF-TOKEN`. Dùng `CsrfToken.getHeaderName()` hoặc contract thực thay vì đoán.

## 10. Khi nào có thể không cần CSRF?

CSRF chủ yếu là rủi ro khi browser **tự gửi** credentials như session cookies. Nếu API thực sự chỉ nhận Bearer token đặt thủ công trong Authorization header, không lưu token trong cookie và browser không auto-attach credential, CSRF threat model có thể khác. Nhưng:
- JWT lưu trong cookie vẫn có rủi ro CSRF.
- HTTP Basic trong browser có thể có credential ambient.
- Có cookies/session login trong cùng app thì cần tách `SecurityWebFilterChain` cho API và browser routes cẩn thận.
- Tắt CSRF cho toàn app chỉ vì một machine API là quyết định quá rộng.
- CORS, XSS, access token theft, same-origin protections và authorization cần được phân tích riêng.

Nếu security architecture quyết định không cần CSRF ở Bearer-only endpoint, cấu hình matcher/chain có phạm vi phù hợp sau review, đồng thời giữ negative tests cho authentication/audience/scope và bảo vệ CSRF ở cookie routes. Không quyết định dựa trên tên “REST” hay “stateless” một cách cơ học.

## 11. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Khắc phục |
|---|---|---|
| POST missing CSRF vẫn 201 | `csrf.disable()`, chain sai, test không gắn security | Negative test + bindToApplicationContext + springSecurity |
| POST valid `csrf()` vẫn 403 | Role thiếu, route khác, test setup sai | Cô lập authn/authorization; check SecurityWebFilterChain |
| POST thiếu auth và token trả 403 | CSRF filter chặn trước authn | Test authn với valid CSRF |
| GET protected trả 401 không có CSRF | Authentication required, không phải CSRF | Gửi Basic/mockUser cho GET |
| POST có `X-CSRF-TOKEN: abc` vẫn 403 | Header value không match repo/handler | Gửi đúng token và đúng session |
| CSRF token trong GET không có SESSION cookie | Token Mono chưa được subscribe/save | Expose token và kiểm WebSession |
| Token A với SESSION B trả 403 | Expected token khác | Đúng bảo vệ, test mismatch |
| Token giữa hai GET khác nhau | XOR/BREACH masked token random | Không assert string equality |
| SPA cookie raw nhưng header bị reject | XOR handler mong masked token | Thiết kế custom reactive handler phù hợp |
| Login/logout làm POST 403 | Token cũ bị clear/rotate | Fetch fresh token |
| POST sau session timeout bị reject | Expected token/session đã hết | Refresh token/login, xử lý idempotency |
| Test using mockUser pass, prod Basic login fail | MockUser bypass credential verification | Thêm real-auth tests |
| Test GET xóa data mà không cần CSRF | Sai HTTP method | Dùng POST/DELETE cho mutation |
| Token sai nhưng counter vẫn tăng | Side effect xảy ra trước security hoặc fire-and-forget | Đặt action sau authz, không subscribe thủ công |
| Test CI không ổn định | Shared counter với parallel tests | Test isolation, reset và serialize |
| CORS failure bị coi là CSRF | Browser preflight/cookie flags sai | Kiểm CORS/SameSite/credentials độc lập |
| CSRF token lộ trong query/logs | Token truyền sai kênh | Header/form body, redact |
| WebTestClient `csrf()` copy từ Servlet | Sai import | Dùng SecurityMockServerConfigurers.csrf |
| Một route mới không đòi CSRF | Multi-chain matcher/ordering sai | Test từng path và HTTP verb |
| Authenticated VIEWER + valid CSRF trả 403 | Thiếu role EDITOR | Đúng authorization layer |

## 12. Bài tập có đáp án

### Bài 1 — Hai csrf() khác nhau thế nào?
**Đáp án:** `ServerHttpSecurity.csrf(...)` bật/cấu hình filter bảo vệ trong ứng dụng; `SecurityMockServerConfigurers.csrf()` tạo valid CSRF test context cho WebTestClient.

### Bài 2 — POST với valid Basic nhưng không CSRF?
**Đáp án:** Thường 403, service không được chạy. Authentication hợp lệ không tự thay CSRF token.

### Bài 3 — POST với invalid header?
**Đáp án:** 403. Header có mặt chưa đủ; phải match expected token theo repository và handler.

### Bài 4 — POST với valid `csrf()` nhưng không auth?
**Đáp án:** Thường 401 trong demo Basic auth. Token CSRF không xác định identity.

### Bài 5 — POST với valid csrf nhưng role VIEWER?
**Đáp án:** 403 do authorization. Kiểm status cùng zero side effects.

### Bài 6 — GET protected không CSRF?
**Đáp án:** Default không đòi token vì GET là safe method, nhưng vẫn cần Authentication/Role.

### Bài 7 — DELETE có yêu cầu CSRF không?
**Đáp án:** Có theo default CSRF matcher, như POST/PUT/PATCH. Không xem DELETE tự an toàn chỉ vì REST semantics.

### Bài 8 — Vì sao assert counter==0 sau 403?
**Đáp án:** Đảm bảo request không chạy side effect nghiệp vụ, không chỉ response status.

### Bài 9 — Token session A gửi kèm cookie session B?
**Đáp án:** Với WebSession repository, expected token session B khác A, phải từ chối.

### Bài 10 — Nếu không có SESSION cookie?
**Đáp án:** Với token lưu trong session, request không thể load expected token của session trước nên token cũ bị reject.

### Bài 11 — Vì sao exposed CSRF token có thể đổi giữa GET?
**Đáp án:** XOR masking thêm random để giảm rủi ro BREACH; không nên so string masked cố định.

### Bài 12 — CookieServerCsrfTokenRepository có nghĩa mọi request X-XSRF-TOKEN tự pass?
**Đáp án:** Không. Header phải đúng token và request handler phù hợp raw/masked representation, session/cookie policy và permissions.

### Bài 13 — CORS có thể thay CSRF?
**Đáp án:** Không; CORS hạn chế browser đọc cross-origin response, không chứng minh ý định mọi unsafe request.

### Bài 14 — App dùng JWT trong cookie có thể disable CSRF vì stateless?
**Đáp án:** Không tự động. Cookie vẫn được browser auto-send; cần CSRF theo threat model.

### Bài 15 — `@WithMockUser` có tự thêm CSRF không?
**Đáp án:** Không. Mock authentication và CSRF test mutator là hai việc khác nhau.

### Bài 16 — Login/logout có cần CSRF?
**Đáp án:** Có trong browser session flow. Login/logout POST cần CSRF, token thường cần refresh sau authentication/session changes.

### Bài 17 — Khi nào dùng real browser E2E?
**Đáp án:** Khi muốn xác minh SameSite/Secure/HttpOnly, CORS, cookie domain/path, SPA token refresh và behavior qua reverse proxy thật.

### Bài 18 — Có thể sửa test 403 bằng `csrf.disable()`?
**Đáp án:** Không nếu mục tiêu là xác minh CSRF. Nó loại bỏ security control và tạo false positive.

## 13. Checklist QA cho dự án

- [ ] Test dùng WebFlux `WebTestClient`, không import Servlet MockMvc csrf().
- [ ] Client in-memory bind ApplicationContext và apply(springSecurity()).
- [ ] CSRF filter vẫn bật, không disable để test pass.
- [ ] GET read-only không token vẫn hoạt động khi authenticated.
- [ ] POST thiếu token + EDITOR -> 403, counter=0.
- [ ] POST token sai + EDITOR -> 403, counter=0.
- [ ] POST `mutateWith(csrf())` + EDITOR -> 201, counter=1.
- [ ] Valid token + no auth -> 401.
- [ ] Valid token + VIEWER -> 403.
- [ ] PUT/PATCH/DELETE missing token -> 403.
- [ ] PUT/PATCH/DELETE valid token -> 200 và đúng side effect.
- [ ] Có test GET /csrf-token lấy SESSION và token, POST cùng session thành công.
- [ ] Có test tamper token, token từ session khác, thiếu cookie/session.
- [ ] Có kiểm tra default XOR handler và WebSession repository behavior.
- [ ] SPA cookie repository nếu dùng phải có test raw-vs-masked token.
- [ ] Login/logout/session expiry và CSRF refresh được test khi relevant.
- [ ] CORS/SameSite/HttpOnly/Secure không bị nhầm với mock WebTestClient.
- [ ] HTTP 401 khác 403 và CSRF reject khác role reject.
- [ ] Không log CSRF token, SESSION cookie, Authorization hoặc PII.
- [ ] Không thực thi state-changing action bằng GET.
- [ ] Không có async/fire-and-forget business side effects chạy sau khi bị reject.
- [ ] Test environment và production security chains không khác nhau trái chủ ý.
- [ ] Build/test trên Java 17+, Boot/Security phiên bản tương thích.

## 14. Tóm tắt

~~~text
APPLICATION:
  ServerHttpSecurity.csrf(...) -> bật CSRF checking
  CsrfWebFilter                -> reject missing/wrong token
  WebSessionServerCsrfTokenRepository -> expected token theo SESSION
  XorServerCsrfTokenRequestAttributeHandler -> masked value

WEBFLUX TEST:
  WebTestClient.bindToApplicationContext(ctx)
    .apply(springSecurity()).configureClient().build()

  POST + EDITOR + no csrf             -> 403, no side effect
  POST + EDITOR + wrong csrf          -> 403, no side effect
  POST + EDITOR + mutateWith(csrf())  -> 201, side effect once
  POST + valid csrf + no auth         -> 401
  POST + valid csrf + VIEWER          -> 403

REAL SESSION TEST:
  GET /csrf-token -> response token + SESSION cookie
  POST token + matching SESSION -> 201
  POST tampered/missing token -> 403
  POST token(A) + SESSION(B) -> 403
  POST token(A) without SESSION -> 403
~~~

**Thông điệp:** `csrf()` trong Spring Security Reactive Test cung cấp **CSRF token hợp lệ cho test**, không phải tắt bảo vệ. Một bộ kiểm thử đáng tin phải có đủ trường hợp **thiếu, sai và hợp lệ**, cô lập Authentication/Authorization, bảo đảm **không có side effect khi 403**, và kiểm tra một luồng thực dùng **CSRF token cùng session cookie**.

## 15. Tài liệu tham khảo

- [Spring Security 6.5 — Testing with CSRF in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [SecurityMockServerConfigurers API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [CsrfWebFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html)
- [WebSessionServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html)
- [CookieServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html)
- [XorServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
