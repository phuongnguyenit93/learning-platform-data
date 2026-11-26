# Kiểm tra yêu cầu thiếu token hoặc giá trị không đúng

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Trọng tâm:** Kiểm thử **request thiếu CSRF token**, có token không hợp lệ, token thuộc session khác, token đã hết hiệu lực, hoặc token đặt sai chỗ trong **Spring Security WebFlux**. Bài cũng phân biệt các lỗi này với **thiếu/sai Bearer token**, CORS, authorization, HTTP firewall và session.  
> **Nền tảng ví dụ:** Spring Security 6.5/7.x, Spring WebFlux, JUnit 5, `spring-security-test` và `WebTestClient`. Các API thực tế phải được kiểm tra theo phiên bản đã resolve; ví dụ dùng Java 17+ và Lambda DSL.

## 1. Đặt đúng câu hỏi trước khi viết negative test

Giả sử một người dùng đã đăng nhập vào hệ thống bán hàng qua session cookie. Browser gửi một request tạo đơn:

```http
POST /orders HTTP/1.1
Host: shop.example.com
Cookie: SESSION=some-session-id
Content-Type: application/json

{"sku":"BOOK-01","quantity":1}
```

Request mang cookie xác thực nhưng **không** mang CSRF token. Nếu ứng dụng dùng cookie/browser session và bật CSRF, request này phải bị chặn **trước khi ghi order**. Khi một request khác mang `X-CSRF-TOKEN: sai-token`, nó cũng phải bị chặn: sự hiện diện của header không đồng nghĩa token khớp giá trị mà server đang kỳ vọng cho session.

Trong `SPRING_SECURITY_HTTP_PROTECTION`, việc kiểm thử hai tình huống này là một phần của phòng vệ trình duyệt. CSRF giúp chống việc browser bị lợi dụng gửi lệnh bằng credential tự đính kèm; nó **không** thay authentication, quyền truy cập, CORS, CSP, HSTS, HTTP firewall hoặc thiết lập session.

### 1.1. Phân biệt ba kiểu “token” trong ứng dụng

| Token hoặc credential | Mục đích | Nơi thường gửi | Thiếu/sai gây ra gì? |
| --- | --- | --- | --- |
| **CSRF token** | Chứng minh client chủ động gửi secret đúng với token kỳ vọng | Header `X-CSRF-TOKEN` / `X-XSRF-TOKEN` hoặc form parameter `_csrf` | Thường **403** ở `CsrfWebFilter` trên unsafe methods |
| **Bearer JWT/opaque access token** | Xác thực API client và cung cấp scopes/authorities | `Authorization: Bearer ...` | Thường **401** nếu thiếu/sai token; 403 nếu đủ auth nhưng thiếu quyền |
| **WebSession cookie** | Liên kết browser với WebSession và SecurityContext | `Cookie: SESSION=...` hoặc cookie tên custom | Không có session, auth có thể bị coi là anonymous; CSRF repository có thể tạo expected token mới |

Một test POST thiếu CSRF **không thể thay thế** test JWT không hợp lệ. Ngược lại, một request thiếu `Authorization: Bearer` nhận 401 chưa chứng minh CSRF được bật trên browser chain.

### 1.2. Mục tiêu kiểm thử của bài

Sau bài, bạn có thể:

1. Tạo một WebFlux `SecurityWebFilterChain` có CSRF và authorization thật trong mock application context.
2. Viết cặp kiểm thử **negative/positive** cho cùng principal, URL và HTTP method.
3. Hiểu vì sao `SecurityMockServerConfigurers.csrf()` chỉ hỗ trợ **trường hợp hợp lệ trong mock test**, không thích hợp để kiểm thử token sai.
4. Lấy token thật từ `CsrfWebFilter` qua `GET /csrf`, giữ WebSession cookie rồi gửi POST thiếu/sai/đúng token **không dùng `csrf()`**.
5. Kiểm tra token của session khác, token cũ sau logout hoặc session hết hạn, token sai header, token dạng raw/masked không tương thích.
6. Phân biệt 400/401/403/404/405 và xác định lớp bảo vệ nào từ chối request.
7. Tổ chức regression tests ở các tầng mock `WebTestClient`, HTTP server thật và browser/HTTPS ingress.

## 2. Mô hình xử lý khi WebFlux kiểm tra CSRF

`CsrfWebFilter` trong Spring Security WebFlux dùng mô hình *synchronizer token*: có một **expected token** do `ServerCsrfTokenRepository` lưu, và một **actual token** mà client gửi. Với request cần CSRF, filter resolve actual token rồi so sánh với expected.

```text
Browser / WebTestClient
   |
   +-- HTTP method + URI
   +-- Cookie: SESSION=S1
   +-- X-CSRF-TOKEN: T?  (có thể thiếu hoặc sai)
   |
   v
WebFilterChainProxy / SecurityWebFilterChain
   |
   +--> HTTP firewall (từ Security 6.4+)
   |
   +--> CsrfWebFilter
           |
           +-- CSRF matcher: method có cần bảo vệ?
           |       |
           |       +-- Không (GET/HEAD/OPTIONS/TRACE mặc định)
           |       |      -> tiếp tục chain
           |       |
           |       +-- Có (POST/PUT/PATCH/DELETE thông thường)
           |              |
           |              +-- ServerCsrfTokenRepository
           |              |      expected token của session S1
           |              |
           |              +-- ServerCsrfTokenRequestHandler
           |                     resolve actual token từ header/form
           |              |
           |              +-- thiếu/sai -> từ chối (thường 403)
           |              +-- trùng -> tiếp tục authentication/authorization/handler
           |
           v
      Controller/RouterFunction (chỉ đến khi mọi lớp cho phép)
```

### 2.1. Token “thiếu” không đồng nghĩa expected token chưa tồn tại

Ta cần tách:

- **Missing actual token:** client không gửi giá trị được handler nhận ra, dù repository có thể có expected token.
- **Invalid actual token:** client gửi một giá trị nhưng nó không trùng expected token (hoặc không giải mã được vì sai định dạng).
- **Missing/changed expected token:** WebSession mới/hết hạn, repository không tải được dữ liệu cũ, hoặc login/logout đã xóa token.

Đa số trường hợp đều thể hiện thành **403** ở HTTP, nhưng nguyên nhân cụ thể chỉ xác định được qua request, session/repository và cấu hình handler. Trong WebFlux, lớp ngoại lệ chung là `org.springframework.security.web.server.csrf.CsrfException`; **không import nhầm** `org.springframework.security.web.csrf.MissingCsrfTokenException` của Servlet rồi mong WebFlux phát nó.

### 2.2. Default methods và HTTP semantics

| Method | CSRF mặc định | Kiểm thử có ý nghĩa |
| --- | --- | --- |
| GET, HEAD | Không yêu cầu | Đọc dữ liệu; tuyệt đối không thực hiện side effect |
| OPTIONS | Không yêu cầu | CORS preflight theo chính sách riêng |
| TRACE | Không yêu cầu bởi CSRF matcher | Firewall/server thường chặn TRACE |
| POST | Yêu cầu | Missing/invalid token trên browser form/API |
| PUT, PATCH, DELETE | Yêu cầu | Negative tests cho cập nhật/xóa |

Một GET thiếu token trả 200 **không** chứng minh CSRF đã tắt. Một POST sai token trả 403 **không** tự chứng minh quyền user được bảo vệ: vẫn phải test authorization độc lập.

### 2.3. Token repository và handler theo phiên bản

| Vai trò | WebFlux API | Hành vi cần nhớ |
| --- | --- | --- |
| Lưu expected token | `ServerCsrfTokenRepository` | Mặc định `WebSessionServerCsrfTokenRepository` |
| Lưu token trong cookie (tùy chọn) | `CookieServerCsrfTokenRepository` | Cookie `XSRF-TOKEN`, header `X-XSRF-TOKEN` theo convention |
| Expose/resolve token | `ServerCsrfTokenRequestHandler` | 6.x/7.x mặc định XOR để giảm nguy cơ BREACH |
| Chặn unsafe request | `CsrfWebFilter` | Dùng matcher, repository và request handler |
| Test condition hợp lệ | `SecurityMockServerConfigurers.csrf()` | Dùng trong **mock WebTestClient**, không phải actual token round-trip |

Từ Spring Security 6, `XorServerCsrfTokenRequestAttributeHandler` giúp che token khi expose cho view, nên **token đã masking** lấy từ GET có thể khác nhau giữa các lần lấy. Đừng dùng giá trị raw trong cookie rồi giả định handler mặc định luôn xử lý nó như masked form token.

## 3. Dependency và phạm vi API

`WebTestClient` thuộc Spring Test/WebFlux; `SecurityMockServerConfigurers` thuộc `spring-security-test`. Cần để Spring Boot BOM quản lý tổ hợp dependency tương thích.

### 3.1. Gradle Groovy DSL

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

### 3.2. Maven test dependencies

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

Trong Boot 4, các test starters được chia nhỏ theo stack; xem documentation/BOM của dự án khi chọn artifacts và packages `@WebFluxTest`/`@AutoConfigureWebTestClient`. Không trộn Security 6/7 modules thủ công để “fix import”.

### 3.3. Kiểm tra versions thật

```bash
# Dùng trong dự án của người học; không bắt buộc chạy khi đọc bài.
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath

# Hoặc với Maven:
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Windows dùng `gradlew.bat`/`mvnw.cmd`. Mọi ví dụ trong bài là mẫu kiến thức, không hàm ý đã chạy chúng trên repo cụ thể.

### 3.4. Đúng import cho Reactive test

```java
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

**Không** dùng `SecurityMockMvcRequestPostProcessors.csrf().useInvalidToken()` trong `WebTestClient`. Đó là Servlet `MockMvc` API, không phải WebFlux.

## 4. Điều gì thật sự xảy ra khi dùng `mutateWith(csrf())`?

Spring Security Reference Guide mô tả `csrf()` như một cách “provide a valid CSRF token” cho mock WebTestClient:

```java
client.mutateWith(csrf())
    .post().uri("/orders")
    .exchange();
```

Đó là **ý nghĩa kiểm thử ở mức contract**: yêu cầu đi qua điều kiện CSRF để bạn kiểm tra các bước khác. Trong source của Spring Security, `CsrfMutator` dựng một `CsrfWebFilter` test-only với matcher không yêu cầu CSRF, rồi thêm vào mock `WebHttpHandlerBuilder`. **Không nên khẳng định helper luôn thực sự tạo `Set-Cookie`/`X-CSRF-TOKEN` và so khớp expected token từ WebSession**.

### 4.1. Hai bài kiểm thử khác nhau

| Câu hỏi | Công cụ phù hợp | Kết luận hợp lệ |
| --- | --- | --- |
| “Request POST sẽ thế nào khi **được xem là đáp ứng CSRF**?” | `mutateWith(csrf())` | Handler/authorization hoạt động sau bước CSRF |
| “CSRF filter có chặn POST **thiếu token** không?” | POST **không** dùng `csrf()` | 403 khi user/authz cố định |
| “Token giá trị sai có bị từ chối không?” | Bootstrap token thật, gửi header sai với đúng session | Repository + handler thực sự từ chối |
| “Token thuộc session khác có bị từ chối không?” | Hai session/cookie khác nhau, token T1/S2 | Token không hợp lệ ngoài session gốc |
| “JWT signature sai có bị 401 không?” | HTTP bearer token với decoder thật | Authentication từ chối; **không phải** CSRF helper |

### 4.2. Ba lỗi kiểm thử cần tránh

1. **Đưa `csrf()` vào negative test** rồi kỳ vọng 403 do thiếu token: helper làm mất chính điều kiện đang muốn thử.
2. **Dùng mỗi test POST có `csrf()` trả 200** rồi kết luận CSRF đã bật: nếu chain vô tình `csrf.disable()`, test này vẫn có thể 200.
3. **Copy `csrf().useInvalidToken()` từ MockMvc**: `SecurityMockServerConfigurers.CsrfMutator` Reactive không công bố phương thức này.

Kết hợp một negative POST thiếu token và một positive POST có `csrf()`, sau đó bổ sung test token thật nếu mục tiêu là bảo đảm định dạng/giá trị.

## 5. Tạo fixture WebFlux có CSRF hoạt động thật

Để test âm có ý nghĩa, ứng dụng phải **có Spring Security filters**, controller POST thật và một user hợp lệ. Ta dùng ví dụ cửa hàng: `GET /public/ping`, `GET /csrf`, `GET /admin/report` và `POST /orders`.

### 5.1. Controller, endpoint token và nghiệp vụ thử nghiệm

Ví dụ sử dụng một bean ghi số lần handler `POST /orders` chạy. Đây là counter **test-only**, không phải database hay hệ thống chống double-submit.

```java
package com.example.protection.reactivetest;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class WebTestFixtureConfig {

    @Bean
    OrderRecorder orderRecorder() {
        return new OrderRecorder();
    }

    @Bean
    OrdersController ordersController(OrderRecorder recorder) {
        return new OrdersController(recorder);
    }

    @Bean
    CsrfBootstrapController csrfBootstrapController() {
        return new CsrfBootstrapController();
    }
}

final class OrderRecorder {
    private final AtomicInteger accepted = new AtomicInteger();

    int count() {
        return this.accepted.get();
    }

    void record() {
        this.accepted.incrementAndGet();
    }

    void reset() {
        this.accepted.set(0);
    }
}
```

Controller:

```java
package com.example.protection.reactivetest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    private final OrderRecorder recorder;

    public OrdersController(OrderRecorder recorder) {
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
            this.recorder.record();
            return "created";
        });
    }
}
```

Lưu ý: `Mono.fromSupplier` trì hoãn side effect cho đến khi publisher được subscribe, phù hợp mục tiêu kiểm tra request có thực sự đến handler. Test ứng dụng lớn hơn nên mock service hoặc dùng một kho dữ liệu test riêng để xác nhận **không có order nào được tạo** sau request bị chặn.

### 5.2. Cấu hình `SecurityWebFilterChain`

```java
package com.example.protection.reactivetest;

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
public class SecurityTestFixtureConfig {

    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public/**", "/csrf").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService testUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password("{noop}test-only")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}test-only-admin")
                .roles("ADMIN")
                .build()
        );
    }
}
```

Các password với `{noop}` chỉ dùng trong test fixture, tuyệt đối không dùng production. Spring Security WebFlux dùng `ServerHttpSecurity` và `SecurityWebFilterChain`; **không** thay bằng Servlet `HttpSecurity`/`SecurityFilterChain`.

**Lưu ý bảo mật:** `/csrf` được phép GET anonymous để minh họa bootstrap token, nhưng nên có `Cache-Control: no-store`, origin policy rõ ràng và không ghi token vào log. Nếu production không cho client chưa xác thực tải token, dùng chính sách khác có kiểm thử tương ứng.

### 5.3. Endpoint cấp token thật, không tự chế token

`CsrfWebFilter` expose một `Mono<CsrfToken>` qua `ServerWebExchange` attribute. Để lấy được token kỳ vọng thuộc WebSession, controller phải **consume publisher** mà filter cung cấp:

```java
package com.example.protection.reactivetest;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class CsrfBootstrapController {

    public record TokenEnvelope(
        String token,
        String headerName,
        String parameterName
    ) {}

    @GetMapping("/csrf")
    public Mono<ResponseEntity<TokenEnvelope>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenPublisher =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                "CsrfWebFilter is not active for this exchange"
            ));
        }

        return tokenPublisher.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new TokenEnvelope(
                token.getToken(),
                token.getHeaderName(),
                token.getParameterName()
            ))
        );
    }
}
```

Đoạn này trả **giá trị mà request handler expose**, có thể là token đã XOR-mask chứ không phải raw token trong storage. Điều quan trọng là client gửi lại đúng giá trị mà server đã trả về cho session tương ứng; không hard-code `X-CSRF-TOKEN` nếu repository/handler đã thay.

### 5.4. Test client và context đầy đủ

```java
package com.example.protection.reactivetest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    WebTestFixtureConfig.class,
    SecurityTestFixtureConfig.class
})
class ReactiveNegativeCsrfTest {

    @Autowired ApplicationContext applicationContext;
    @Autowired OrderRecorder recorder;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        recorder.reset();
        this.client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Các @Test bên dưới được thêm lần lượt trong bài.
}
```

Đây là mock application context, **không mở TCP port**. `springSecurity()` gắn hỗ trợ security testing, còn `@SpringJUnitConfig` nạp các beans Security thật. Test counter có reset giữa các phương thức; không chạy những test cùng chia sẻ counter này song song nếu chưa cô lập bean/context.

## 6. Kiểm thử thiếu token: phải có positive control

### 6.1. Negative test: user được xác thực nhưng không gửi CSRF

```java
@Test
void postWithoutCsrfTokenIsForbidden() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count(),
        "Orders handler must not execute for a CSRF-rejected request");
}
```

Ta dùng user có role `USER` đã authenticated. Nhờ đó test không bị nhiễu bởi 401 do thiếu authentication; request thiếu CSRF phải bị từ chối và handler không chạy.

### 6.2. Positive control: đúng user, đúng URL, có điều kiện CSRF hợp lệ

```java
@Test
void postWithCsrfTestMutatorReachesHandler() {
    client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("created");

    assertEquals(1, recorder.count());
}
```

Nếu negative POST trả 403 và positive POST trả 200, có thể suy ra trong fixture này request bị chặn khi chưa đáp ứng CSRF. Nhưng positive test **không** xác nhận expected token được lưu đúng, vì `csrf()` là mutator dành riêng cho mock testing.

### 6.3. Không dùng GET để thử CSRF

```java
@Test
void safeGetDoesNotNeedCsrfToken() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("pong");
}
```

GET/HEAD/OPTIONS/TRACE không yêu cầu CSRF theo default matcher; không có token trong GET là hành vi bình thường. Nếu code nghiệp vụ sửa dữ liệu bằng GET, phải **sửa HTTP semantics**, không nên xem việc thiếu CSRF trên GET là chủ đích an toàn.

### 6.4. Bắt cả PUT, PATCH và DELETE

Nếu ứng dụng có endpoints hỗ trợ thay đổi tài nguyên bằng `PUT /orders/42`, `PATCH /orders/42` hoặc `DELETE /orders/42`, hãy thêm test âm cho **đúng method và URL thật**:

```java
@Test
void unsafeMethodsRequireCsrfWhenHandlersExist() {
    // Giả định ứng dụng có endpoint PUT /orders/42
    // và user đã có quyền gọi khi CSRF hợp lệ.
    client.mutateWith(mockUser("alice").roles("USER"))
        .put().uri("/orders/42")
        .exchange()
        .expectStatus().isForbidden();
}
```

Ở fixture demo hiện tại **chưa có PUT handler**; đây là mẫu mở rộng, không phải test có thể chạy y nguyên trên demo `OrdersController`. Nếu request có lỗi CSRF, security filter có thể chặn trước khi router xét method và vẫn trả 403; muốn test dương phải thêm handler PUT tương ứng.

## 7. Lấy CSRF token thật từ WebSession

Để thực sự kiểm tra giá trị sai, ta phải biết token server **kỳ vọng** và phân biệt nó với giá trị client **gửi vào**. Với default `WebSessionServerCsrfTokenRepository`, expected token gắn với WebSession; nếu mỗi request dùng một session khác nhau thì token đúng của session cũ có thể bị xem là sai.

### 7.1. Điều kiện của một test token thật

```text
GET /csrf
  |
  +--> CsrfWebFilter exposes Mono<CsrfToken>
  +--> Controller consumes Mono
  +--> WebSession repository lưu expected token
  +--> Response JSON có exposed token T
  +--> Response Set-Cookie có Session S

POST /orders
  Cookie: SESSION=S
  X-CSRF-TOKEN: <actual token>
  |
  +--> Repo lấy expected token từ S
  +--> Handler resolve actual token từ request
  +--> Sai/thiếu: 403; đúng: đi tiếp
```

Không kỳ vọng default WebSession repository tự phát cookie `XSRF-TOKEN`. Cookie token repo là lựa chọn tùy biến khác; default WebFlux session thường dùng cookie `SESSION` (có thể được đổi tên).

### 7.2. Tạo helper lấy token cùng session

Đặt record và method sau vào class `ReactiveNegativeCsrfTest` ở mục 5.4; cần thêm imports:

```java
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import static org.junit.jupiter.api.Assertions.assertNotNull;

record CsrfSession(
    String sessionCookie,
    String headerName,
    String token,
    String parameterName
) {}

CsrfSession bootstrapCsrf() {
    EntityExchangeResult<CsrfBootstrapController.TokenEnvelope> response =
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(CsrfBootstrapController.TokenEnvelope.class)
            .returnResult();

    var body = response.getResponseBody();
    assertNotNull(body, "/csrf must return a token");
    assertNotNull(body.headerName());
    assertNotNull(body.token());

    ResponseCookie cookie = response
        .getResponseCookies()
        .getFirst("SESSION");
    assertNotNull(cookie,
        "WebSession token repository should start a session");

    return new CsrfSession(
        cookie.getValue(),
        body.headerName(),
        body.token(),
        body.parameterName()
    );
}
```

Ở ví dụ này, `ResponseCookie cookie` mang session ID từ bootstrap, và `TokenEnvelope.token()` mang token **được request handler expose**. Không so sánh token string với dữ liệu trong Redis/database để chứng minh XOR masking vì đây có thể là hai dạng khác nhau.

**Lưu ý phiên bản và session policy:** khi app đặt tên cookie khác `SESSION`, cấu hình custom WebSessionManager, hoặc sử dụng `CookieServerCsrfTokenRepository`, hãy điều chỉnh helper theo cookie/repository đã thực sự cấu hình. Nếu thiếu cookie, trước hết kiểm tra token Mono có được consume và session có được lưu không.

### 7.3. Tại sao không lấy token từ một constant?

Sai lầm thường gặp:

```java
// SAI: test đang dùng một token tự chế, không gắn với repository.
String token = "csrf-valid-token";

client.post().uri("/orders")
    .header("X-CSRF-TOKEN", token)
    .exchange()
    .expectStatus().isOk();
```

Giá trị hard-code đó không tự trở thành expected token. Nếu test này trả 200 mà không có custom token repository nào chấp nhận nó, hãy kiểm tra xem Security/CSRF đã bị bỏ qua hoặc test đang dùng `csrf()` mặc định nào khác.

## 8. Negative test đầy đủ: thiếu token, sai token và token đúng

Đặt các method tiếp theo trong cùng `ReactiveNegativeCsrfTest`, dùng helper `bootstrapCsrf()` ở mục 7.2. **Tuyệt đối không gọi `mutateWith(csrf())` trong các test gửi actual HTTP token** — nếu thêm helper, bạn đang thay đổi lớp kiểm tra mà chính bạn muốn thử.

### 8.1. Thiếu header và parameter

```java
@Test
void missingActualCsrfTokenIsRejected() {
    CsrfSession csrfSession = bootstrapCsrf();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", csrfSession.sessionCookie())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Đây là bài test trực tiếp cho **missing actual token**: repository đã được tạo token trong WebSession; POST giữ session nhưng không có header hoặc form parameter token. Nếu thiếu token vẫn được 200, cần kiểm tra `CsrfWebFilter` và chain matcher.

### 8.2. Header có mặt nhưng sai giá trị

```java
@Test
void incorrectCsrfTokenValueIsRejected() {
    CsrfSession csrfSession = bootstrapCsrf();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", csrfSession.sessionCookie())
        .header(csrfSession.headerName(), "invalid-test-token")
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Test này chứng minh chỉ **có mặt một header tên đúng** không đủ: giá trị phải khớp expected token và định dạng mà handler chấp nhận. Nếu dùng XOR request handler mặc định, chuỗi `invalid-test-token` có thể không decode được và phải bị từ chối.

### 8.3. Token hợp lệ lấy từ server phải được chấp nhận

```java
@Test
void correctCsrfTokenAndSessionAreAccepted() {
    CsrfSession csrfSession = bootstrapCsrf();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", csrfSession.sessionCookie())
        .header(csrfSession.headerName(), csrfSession.token())
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("created");

    assertEquals(1, recorder.count());
}
```

Cả expected token và actual token đi theo **cùng WebSession**. Trong mô hình default, đây mới là bằng chứng rằng repository và request handler có thể trao đổi token thành công qua HTTP mock exchange. So với test `mutateWith(csrf())`, nó kiểm tra thêm cả **bootstrap, lưu session, cookie và header resolution**.

### 8.4. Sai header name: token đúng nhưng đặt ở chỗ server không đọc

```java
@Test
void tokenInUnrecognizedHeaderIsRejected() {
    CsrfSession csrfSession = bootstrapCsrf();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", csrfSession.sessionCookie())
        // Không phải header mà CsrfToken.getHeaderName() chỉ định.
        .header("X-Unrecognized-CSRF", csrfSession.token())
        .exchange()
        .expectStatus().isForbidden();
}
```

Vì token không nằm trong vị trí handler nhận biết, đây tương đương **missing actual token** với cấu hình fixture. Đừng gửi token qua `Authorization` header hay query string để “giải quyết” chuyện đặt sai header; token cần đúng kênh của CSRF handler.

### 8.5. Trường hợp header trống, whitespace và token bị cắt

Một test table có thể bao gồm:

| Actual token trong request | Đánh giá kỳ vọng |
| --- | --- |
| Không có header/parameter | 403 |
| `""` (chuỗi rỗng) | 403 |
| `" "` hoặc whitespace | 403 nếu parser nhận và giữ header |
| Một phần token bị cắt | 403 |
| Random string có độ dài tương tự | 403 |
| Token hợp lệ từ đúng session | Qua CSRF |
| Token hợp lệ nhưng đặt trong header không được nhận biết | 403 |

Một số HTTP server/proxy có thể loại header trống hoặc từ chối ký tự bất thường **trước** khi tới `CsrfWebFilter`. Để cô lập so sánh token, ưu tiên test bằng HTTP strings hợp lệ và xác minh token được WebFlux nhận như dự kiến. Các biến thể malformed raw HTTP cần integration test ở network layer riêng.

### 8.6. Kiểm tra side effect không xảy ra

Chỉ assert 403 đôi khi chưa đủ. Trong fixture, `OrderRecorder.count()` bằng 0 chứng minh controller chưa thực hiện side effect; trong dự án thật, ta có thể:

- Verify service/repository không được gọi.
- Đếm số record của test database trước và sau request.
- Kiểm tra không có event/message nào được publish.
- Sử dụng transaction rollback và test fixture tách dữ liệu.

Không dựa vào việc không thấy response body `"created"` làm bằng chứng đủ mạnh nếu controller có side effect rồi mới trả lỗi. Security filter lý tưởng chặn **trước** khi tới domain handler.

## 9. Token đúng nhưng thuộc **WebSession khác**

Một synchronizer token phải liên kết với session/identity context mà server dùng để lưu expected token. Token T1 từ session S1 không được dùng thay token của session S2.

### 9.1. Tạo hai session độc lập

```java
@Test
void csrfTokenFromAnotherSessionIsRejected() {
    // Hai lần GET /csrf không mang cookie từ lần trước:
    CsrfSession first = bootstrapCsrf();
    CsrfSession second = bootstrapCsrf();

    // Không dùng mutateWith(csrf()) ở request POST.
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", second.sessionCookie())
        .header(second.headerName(), first.token())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Hai bootstrap requests phải tạo **hai WebSession khác nhau**. Client ở đây không có cookie jar tự động dùng lại `SESSION` giữa requests; nếu test framework hoặc custom client đã tự giữ cookie, cần bảo đảm mỗi bootstrap thực sự tạo session độc lập. Có thể assert hai session IDs khác nhau trong fixture test, nhưng **đừng log session IDs** lên CI.

### 9.2. Kết quả có ý nghĩa gì?

- Nếu T1/S2 bị 403: token không hợp lệ khi dùng với expected token của S2.
- Nếu T1/S2 được 200: cần xem repo có thực sự gắn token với session hay không, CORS/CSRF matcher, skipExchange test helper, hoặc test session isolation.
- Nếu không có handler POST và server trả 404: không thể kết luận token đúng; phải có positive control T2/S2 với handler thực.

Sự khác biệt giữa session giúp phân biệt cấu hình đúng với một mock token **dùng chung toàn ứng dụng** không có tính ràng buộc.

## 10. Form parameter `_csrf` và JSON header: hai đường truyền khác nhau

CSRF token phải đi trong phần request mà browser **không tự đính kèm**. Form truyền hidden input trong body; fetch JSON thường truyền HTTP header. Test cần dùng đúng cách app thực sự nhận token.

### 10.1. Truyền token trong form URL encoded

Với `ServerCsrfTokenRequestAttributeHandler` và `XorServerCsrfTokenRequestAttributeHandler` hỗ trợ form parameter, có thể thử token qua `_csrf` theo `parameterName` của token server cấp:

```java
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.http.MediaType;

@Test
void formPostWithCorrectParameterIsAccepted() {
    CsrfSession csrfSession = bootstrapCsrf();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", csrfSession.sessionCookie())
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(BodyInserters.fromFormData(
            csrfSession.parameterName(), csrfSession.token()
        ))
        .exchange()
        .expectStatus().isOk();

    assertEquals(1, recorder.count());
}
```

Fixture `OrdersController` không yêu cầu JSON body nên ví dụ chạy bằng form data được; nếu controller production chỉ nhận `application/json`, dùng **HTTP header** cùng JSON body thay vì cố đổi content type để kiểm tra CSRF.

### 10.2. Sai form parameter name

```java
@Test
void tokenUnderWrongFormParameterIsRejected() {
    CsrfSession csrfSession = bootstrapCsrf();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", csrfSession.sessionCookie())
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(BodyInserters.fromFormData(
            "not_the_csrf_parameter", csrfSession.token()
        ))
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Tên parameter không được request handler công nhận nên actual token được xem như thiếu; giá trị đúng nhưng gửi sai nơi **không** phải điều kiện hợp lệ.

### 10.3. Không đặt token trong URL query

```http
POST /orders?_csrf=secret-value HTTP/1.1
```

Không khuyến khích đưa token qua URL query string: URL dễ bị lưu trong browser history, server/access logs, analytics, Referer hoặc tracing. Chọn header hoặc hidden form field trong body, rồi test các vị trí đó. Không dùng `Authorization: Bearer <csrf-token>` vì nó **không** phải access token.

### 10.4. Header name và token value phải là một cặp đúng

| Repository/handler | Header thông thường | Vấn đề kiểm thử |
| --- | --- | --- |
| WebSession repo mặc định | `X-CSRF-TOKEN` (theo token object) | Header phải mang exposed token đúng dạng |
| CookieServerCsrfTokenRepository | `X-XSRF-TOKEN` theo convention | Cookie raw token và XOR handler có thể cần custom resolution |
| Custom token handler | Theo `CsrfToken.getHeaderName()` hoặc contract đã cấu hình | Không hard-code nếu ứng dụng chủ động đổi header |

Trong test integration, nên lấy `headerName` từ bootstrap endpoint của server. Nhưng thêm một test **hợp đồng frontend** vẫn cần thiết: frontend đã gửi đúng tên header công khai được tài liệu API cam kết chưa?

## 11. Token “đúng nhìn bằng mắt” nhưng không hợp lệ do XOR/BREACH

Spring Security 6+ WebFlux mặc định sử dụng `XorServerCsrfTokenRequestAttributeHandler` để mask token khi expose qua request attribute. Giải pháp này làm giảm nguy cơ khai thác BREACH khi token xuất hiện trong response được nén cùng nội dung do attacker kiểm soát.

### 11.1. Phân biệt raw expected token và exposed token

```text
WebSession expected token (raw): R
        |
        v
XorServerCsrfTokenRequestAttributeHandler
        |
        +-- GET /csrf #1 -> masked token M1
        |
        +-- GET /csrf #2 -> masked token M2
        |                     M1 có thể khác M2
        |
        v
POST header/form: token mà handler có thể resolve
        |
        +-- M1 hoặc M2 đúng session -> có thể hợp lệ
        +-- raw R đưa trực tiếp vào handler chờ masked -> có thể 403
```

**Đừng kết luận** token đã bị rotate chỉ vì JSON token khác giữa hai GET; nếu dùng handler XOR mặc định, thay đổi exposed token do masking là bình thường. Test nên kiểm chứng round-trip, không so string equality của masked token như một định nghĩa token lifetime.

### 11.2. Vì sao `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` chưa đủ?

Trong ứng dụng SPA, có thể cấu hình:

```java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()
));
```

Cookie `XSRF-TOKEN` được JavaScript đọc, sau đó gửi raw token trong `X-XSRF-TOKEN`. Nhưng repository chỉ nói **expected token được lưu và đọc ra ở đâu**; request handler còn quyết định **actual token được giải mã như thế nào**. Nếu handler đang chờ masked token, request raw header có thể 403 dù hai chuỗi raw cookie/header giống hệt.

| Tình huống | Cookie `XSRF-TOKEN` | Header `X-XSRF-TOKEN` | Phân tích |
| --- | --- | --- | --- |
| SPA không gửi header | Có | Không | Chống CSRF phải chặn |
| Header bị frontend gửi sai | Có | Raw token khác | Phải chặn |
| Header raw trùng cookie nhưng handler chờ masked | Có | Raw token trùng | Có thể bị chặn do **handler incompatibility** |
| Handler được thiết kế nhận raw cookie header | Có | Raw token trùng | Có thể hợp lệ nếu các chính sách khác cho phép |

**Cách xử lý:** đọc Reference Guide đúng WebFlux version và thiết kế `ServerCsrfTokenRequestHandler` phù hợp với SPA. Một tùy chọn là thay handler bằng `ServerCsrfTokenRequestAttributeHandler` nhưng điều này **loại bỏ lớp BREACH masking**; nên đánh giá rủi ro thay vì tắt vì một test lỗi. Với yêu cầu cao hơn, có thể có handler tùy chỉnh hỗ trợ raw header từ SPA nhưng vẫn mask token expose trong HTML, kèm regression tests.

### 11.3. Xây test cho đúng contract của SPA

Một test cần xác minh **ít nhất**:

1. GET bootstrap khởi tạo token cho client đúng origin/session.
2. Token được expose theo contract (JSON/header/cookie) và không bị cache công khai.
3. JavaScript gửi **đúng header name và token format**.
4. POST không header bị 403.
5. POST header raw sai bị 403.
6. POST header hợp lệ được server chấp nhận.
7. Login/logout làm token/session thay đổi theo lifecycle dự kiến.

`mutateWith(csrf())` có thể pass ở cùng thời điểm frontend đang 403 do khác dạng token. Vì vậy phải có **HTTP round-trip và browser E2E**.

## 12. Token hết hạn hoặc bị xóa sau login/logout

Token được kỳ vọng theo repository/session lifecycle. Một token từng hợp lệ **không bảo đảm** tiếp tục hợp lệ sau logout, session timeout, đổi session ID hoặc thay đổi auth strategy.

### 12.1. Dùng token cũ nhưng không có session cookie

Trong mock context, ta có thể thử **token cũ ở một request không có cookie session**; đây là test *session mismatch*, không phải giả lập thời gian timeout thực:

```java
@Test
void tokenWithoutOriginalSessionIsRejected() {
    CsrfSession old = bootstrapCsrf();

    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        // Cố tình KHÔNG gửi Cookie: SESSION=old.sessionCookie()
        .header(old.headerName(), old.token())
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, recorder.count());
}
```

Để khẳng định session **đã hết hạn theo thời gian**, phải sử dụng test session manager/clock hoặc live session store với expiration có kiểm soát, chứ không coi việc bỏ cookie là bằng chứng timeout.

### 12.2. Sau logout

```text
GET /csrf -> (S1, T1)
POST /login  (credential, S1, T1)
GET /csrf -> (S2, T2)  [nếu strategy thay token/session]
POST /orders với S2,T2 -> được phép
POST /logout với S2,T2 -> xóa authentication/session/token
POST /orders với session/token cũ -> không được xử lý
GET /csrf -> bootstrap token mới trước unsafe request tiếp theo
```

Chuỗi này phải được **kiểm thử bằng form login/logout hoặc auth mechanism thật**, không phải `mockUser()`: mock principal không tự chạy `CsrfAuthenticationStrategy`, `CsrfServerLogoutHandler` hoặc session rotation. Để test logout endpoint có CSRF, phải gửi đúng token trước khi session bị hủy.

### 12.3. Yêu cầu kỹ thuật của một test logout/session

| Bước | Dữ liệu giữ lại | Điều kiểm tra |
| --- | --- | --- |
| Bootstrap ban đầu | Cookie session + token | Token được lưu và có thể gửi lại |
| Login | Username/password + CSRF token | Authenticated session mới/same theo strategy |
| Request sau login | Cookie mới nhất + token mới | User có quyền; token cũ không được dùng mù |
| Logout | Cookie + CSRF token hợp lệ | Logout success và context/session bị xóa |
| Request sau logout | Cookie/token cũ | Không được phép thực hiện side effect |

Nếu logout trả 200/302 nhưng user vẫn có thể gọi protected API với cookie cũ, đó là lỗi vòng đời authentication/session; không được đánh dấu PASS chỉ vì response logout không lỗi.

### 12.4. Session fixation và token reuse

Ngay cả khi token còn đúng raw bytes, server có thể đổi session ID hoặc token repository scope sau authentication. Để tránh test giả:

- Không giữ cứng cookie trước login cho mọi request.
- Lấy `Set-Cookie` mới sau login/logout nếu có.
- Không giả định token luôn rotate ở cùng thời điểm trong mọi phiên bản/config.
- Test điều kiện **bảo mật mong muốn**: token của trạng thái cũ không được dùng để thực hiện request trái policy.
- Với rollout nhiều replica, xác minh Spring Session/Redis serialization và session store shared behavior.

## 13. Bearer JWT thiếu/sai token: khác CSRF như thế nào?

Đối với **Bearer-only API** (không chấp nhận browser credential tự đính kèm), threat model có thể cho phép miễn CSRF cho API chain cụ thể. Nhưng một `Authorization: Bearer ...` thiếu/sai là bài toán **authentication**, không phải `CsrfWebFilter`.

### 13.1. Ma trận để tránh nhầm 401 và 403

| Trạng thái Bearer token | CSRF theo chain | Kỳ vọng điển hình |
| --- | --- | --- |
| Không có Bearer token, GET protected API | Không liên quan tới GET | 401 |
| Bearer có chữ ký sai/hết hạn, GET API | Không liên quan tới GET | 401 |
| Bearer hợp lệ nhưng thiếu `SCOPE_orders:write`, GET/POST API | Tùy chain | 403 authorization khi auth hợp lệ |
| Bearer hợp lệ, browser chain POST thiếu CSRF | Bật | 403 CSRF |
| Bearer hợp lệ, API chain *được phép miễn CSRF theo threat model* | Đã miễn riêng | Đi tiếp tới authorization/handler |

Nếu chưa xác định chain và CSRF matcher, đừng đoán rằng POST thiếu Bearer nhất thiết trả 401: `CsrfWebFilter` có thể chặn trước bằng 403. Dùng **GET protected API** để kiểm chứng authentication 401 mà không có nhiễu CSRF.

### 13.2. Mẫu hai security chains

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
@Order(1)
SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders:write")
            .anyExchange().authenticated()
        )
        // Chỉ khi client/API không nhận cookie hay credential
        // browser tự gửi; policy phải được đánh giá và review.
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(resource -> resource
            .jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browser(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public/**", "/csrf").permitAll()
            .anyExchange().authenticated()
        )
        .csrf(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đây là **cấu hình thay thế** cho fixture một chain ở mục 5, không thêm đồng thời không kiểm soát. Cần cấu hình Resource Server decoder/issuer, CORS và headers phù hợp khi triển khai. `csrf.disable()` chỉ ở API chain được đánh giá Bearer-only; nó **không** được áp lên browser chain.

### 13.3. Mock JWT dùng để test quyền, không test chữ ký

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@Test
void jwtWithoutRequiredScopeIsForbidden() {
    // Test chỉ có ý nghĩa với API chain và handler /api/orders/42.
    client.mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get().uri("/api/orders/42")
        .exchange()
        .expectStatus().isForbidden();
}
```

`mockJwt()` tạo authentication trong mock exchange, **không verify signature/issuer/expiry**. Để test Bearer token sai, dùng test decoder/issuer và HTTP request thật tới Resource Server, bảo đảm token ký sai/hết hạn trả 401; tách khỏi negative CSRF tests.

## 14. CORS preflight: OPTIONS không có token không phải lỗi CSRF

Một SPA ở `https://app.example.com` gọi API tại `https://api.example.com` với JSON và custom header `X-CSRF-TOKEN` có thể khiến browser gửi một OPTIONS preflight:

```http
OPTIONS /orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Preflight thường **không gửi session cookie**, và CSRF matcher mặc định không yêu cầu token cho OPTIONS. Vậy nếu OPTIONS trả 401/403, hãy kiểm tra **CORS source, authentication filter ordering hoặc proxy**, không thêm `csrf()` để giả lập một token không cần thiết.

### 14.1. Tạo cấu hình CORS Reactive

Trong một biến thể của test fixture, thêm cấu hình:

```java
package com.example.protection.reactivetest;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveTestCorsConfig {

    @Bean
    CorsConfigurationSource allowedOrigins() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
```

Chỉnh **bean chain của biến thể test**, thay cho method ở mục 5.2:

```java
// Thay chữ ký method để inject Reactive CorsConfigurationSource.
SecurityWebFilterChain web(
        ServerHttpSecurity http,
        CorsConfigurationSource allowedOrigins) {

    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public/**", "/csrf").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .cors(cors -> cors.configurationSource(allowedOrigins))
        .csrf(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Snippet là **replacement method**, không tự định nghĩa bean thứ hai. Nạp `ReactiveTestCorsConfig.class` vào test context. Chú ý `org.springframework.web.cors.reactive.CorsConfigurationSource` **khác** interface Servlet `org.springframework.web.cors.CorsConfigurationSource`.

### 14.2. Test preflight origin hợp lệ/không hợp lệ

```java
@Test
void allowedOriginPreflightDoesNotNeedCsrf() {
    client.options().uri("/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin",
            "https://app.example.com");
}

@Test
void untrustedOriginDoesNotGetCorsPermission() {
    client.options().uri("/orders")
        .header("Origin", "https://untrusted.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");
}
```

Các tests này dành cho fixture có CORS source ở mục 14.1. Không dùng `mutateWith(csrf())` cho OPTIONS. Origin không được cấp quyền có thể nhận 403 hoặc status khác tùy handler/gateway, nhưng không được nhận allow-origin cho credentialed cross-origin.

### 14.3. POST sau preflight vẫn cần CSRF

```text
OPTIONS /orders -> CORS source kiểm tra Origin/Method/Headers
                -> có thể trả 200/204

POST /orders    -> Browser gửi cookie/session theo chính sách
                -> CSRF matcher thấy unsafe method
                -> actual token cần có và khớp
                -> authorization/handler tiếp tục
```

Nếu preflight pass nhưng POST 403, debug **token source, WebSession, request handler và authorization**. `Access-Control-Allow-Origin` không thay đồng bộ CSRF token với session.

## 15. HTTP firewall, URL routing và lỗi input có thể che lỗi token

Từ Spring Security 6.4, Reactive `WebFilterChainProxy` hỗ trợ `StrictServerWebExchangeFirewall`. Một URL `/admin;mode=1/report` hoặc method bất thường có thể bị chặn **trước** `CsrfWebFilter`. Một request HTTP 400 không phải bằng chứng token sai.

| Request | Tầng cần điều tra đầu tiên | Status thường gặp |
| --- | --- | --- |
| POST `/orders` thiếu token, user hợp lệ | CSRF | 403 |
| POST `/orders` token sai, session đúng | CSRF | 403 |
| POST `/orders` có token đúng nhưng USER bị cấm | Authorization | 403 |
| GET `/admin/report` không auth | Authentication | 401 hoặc redirect |
| GET `/admin;v=1/report` | Firewall / HTTP parser | 400 hoặc status ở edge |
| POST `/unknown` có token đúng | Router / authorization | 404/401/403 tùy chain |
| PUT `/orders` nhưng handler không hỗ trợ | Router, sau security checks | 405 khi qua filters |

### 15.1. Unit test firewall riêng

Nếu muốn xác minh firewall, dùng `MockServerWebExchange` và `StepVerifier`, không sửa CSRF fixture:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall;
import org.springframework.security.web.server.firewall.ServerExchangeRejectedException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void strictFirewallRejectsSemicolonPath() {
    var firewall = new StrictServerWebExchangeFirewall();
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/admin;role=1/report")
    );

    StepVerifier.create(
        Mono.defer(() -> firewall.getFirewalledExchange(exchange))
    )
        .expectError(ServerExchangeRejectedException.class)
        .verify();
}
```

Đây là test **firewall riêng**, yêu cầu Spring Security 6.4+. Nó chưa chứng minh WebFlux runtime dùng instance firewall ấy. Test qua `WebTestClient` và staging HTTP public khi cần kiểm tra bean wiring hoặc proxy rewrite.

### 15.2. Proxy có thể rewrite request trước khi Spring nhìn thấy

```text
Client: GET /portal/admin%2Freports
        |
        v
Ingress/proxy: strip prefix, decode/normalize? reject?
        |
        v
Reactor Netty: parse request URI
        |
        v
StrictServerWebExchangeFirewall
        |
        v
SecurityWebFilterChain matcher + CsrfWebFilter + handler
```

Khi làm negative CSRF test, hãy chọn **canonical URL**, ví dụ `/orders`; nếu cố tình gửi path bất thường cùng token sai, server có thể dừng ở HTTP firewall và test không còn cô lập CSRF. Raw URL tests nên nằm trong suite riêng có kiểm tra request qua ingress.

## 16. Test slice, full context và HTTP server thật

### 16.1. `@WebFluxTest` có thể bỏ sót custom Security chain

`@WebFluxTest` của Spring Boot tập trung vào WebFlux slice; nó **không bảo đảm** tự nạp mọi custom `SecurityWebFilterChain`, custom token repository hoặc request handler. Nếu thiếu config, test có thể chạy dưới default chain khác production.

Ví dụ Spring Boot 3.5:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(OrdersController.class)
@Import({SecurityTestFixtureConfig.class, SliceBeans.class})
class OrdersCsrfSliceTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

`SliceBeans` là **test configuration do dự án phải cung cấp** chứa `OrderRecorder`, user store hoặc dependencies cần thiết, không phải class Spring có sẵn; đoạn này chỉ là bộ khung test slice. Với một fixture tự chứa để chạy ngay mà không phụ thuộc Boot, dùng `@SpringJUnitConfig` ở mục 5.4.

Spring Boot 4 đổi package test annotations:

```java
// Boot 4:
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
```

Không copy import Boot 3.5 và Boot 4 vào cùng file. Nếu cần test **toàn application context**, dùng `@SpringBootTest` với WebFlux Security beans thật.

### 16.2. `@SpringBootTest` mặc định không mở TCP server

```java
@SpringBootTest
class FullContextCsrfPolicyTest {
    @Autowired ApplicationContext context;

    @Test
    void unsafeRequestWithoutTokenIsRejected() {
        WebTestClient c = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();

        c.mutateWith(mockUser("alice").roles("USER"))
            .post().uri("/orders")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Trong `@SpringBootTest` với webEnvironment mặc định, client ở đây vẫn là **mock WebTestClient**, không tự đi qua HTTP server/ingress. Full context có thể cho bạn Security beans giống production hơn slice, nhưng cần profile/test services phù hợp.

### 16.3. HTTP server thật: không dùng `csrf()` mock mutator

`@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `WebTestClient.bindToServer()` gửi HTTP request qua network. `SecurityMockServerConfigurers.CsrfMutator` được thiết kế cho **mock `WebHttpHandlerBuilder`**, không áp dụng như vậy cho HTTP connector thật.

Với `WebTestClient` đã bind vào cổng thật, gửi cookie/header token được lấy từ `GET /csrf`:

```java
// Fragment trong live HTTP test, giả định các biến lấy từ bootstrap:
http.post().uri("/orders")
    .cookie("SESSION", sessionCookieValue)
    .header(headerName, csrfToken)
    .headers(headers -> headers.setBasicAuth(
        "alice", "test-only"))
    .exchange()
    .expectStatus().isOk();
```

`http` phải là WebTestClient được cấu hình tới server thật; `sessionCookieValue`, `headerName` và `csrfToken` là dữ liệu bootstrap hợp lệ. `mockUser()` hoặc `@WithMockUser` trên test thread **không** xác thực request TCP. Test âm live HTTP cũng cần Basic/Bearer credential thật để cô lập CSRF khỏi authentication.

### 16.4. Cookie và browser rules không được mô phỏng đầy đủ

Mock `WebTestClient` không phải Chrome: nó không thực thi đầy đủ SameSite, third-party cookie policies, browser Fetch credentials mode hay CSP. `WebTestClient.bindToServer` thử server thật nhưng vẫn không phải browser engine. Vì vậy:

- Mock context: policy CSRF/authorization nhanh và ổn định.
- Live HTTP: token repository/handler, HTTP parser và authentication thật.
- Browser E2E qua HTTPS ingress: cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path`, CORS preflight, CSP/HSTS, redirect và proxy rewrite.

Nếu browser không gửi cookie WebSession ở môi trường cross-origin, một test mock token đúng vẫn có thể pass trong khi ứng dụng thực trả 403 hoặc 401. Đây là lý do phải kiểm tra cả đường public.

## 17. Chẩn đoán lỗi token thiếu hoặc giá trị không đúng

### Lỗi A — POST **không có CSRF token** nhưng trả 200

Đây là tín hiệu quan trọng cần điều tra:

- Test đã gọi `mutateWith(csrf())` trên một client dùng chung mà bạn quên?
- WebTestClient chỉ `bindToController` nên thiếu Security WebFilters?
- `SecurityWebFilterChain` nhận request có `csrf.disable()`?
- `csrf.ignoringExchangeMatchers(...)` đã miễn URL đó?
- API chain `@Order(1)` với matcher quá rộng đang bắt cả browser POST?
- Một global test WebFilter hoặc custom handler đã gọi `CsrfWebFilter.skipExchange`?

**Khắc phục:** tạo request test hoàn toàn mới, giữ principal và URL hợp lệ, không có `csrf()`, kiểm tra chain và negative assertion. Không sửa expected status thành 200 chỉ vì suite đang đỏ.

### Lỗi B — POST thiếu token trả 401, tưởng CSRF không chạy

401 có thể do authentication entry point. Hãy test `mockUser("alice")` với POST thiếu token để kiểm tra CSRF độc lập; nếu test cũng bị 401, xác minh mock security support và chain đúng. Một API Bearer-only đã miễn CSRF theo threat model có thể phản hồi 401 khi không có access token — không phải lỗ hổng CSRF của browser chain.

### Lỗi C — POST token sai trả 403, nhưng chưa biết filter nào chặn

403 cũng xuất hiện do authorization và CORS. Dùng ba đối chứng:

1. GET private với user thiếu quyền để kiểm tra authorization.
2. POST với user đủ quyền và token **đúng từ bootstrap** để kiểm tra positive.
3. POST cùng user/session nhưng token **sai** để cô lập CSRF.

Nếu positive POST vẫn 403, chưa thể quy nguyên nhân cho token sai. Kiểm tra `CsrfWebFilter`, request handler, repository, chain matcher và logs/metrics đã làm sạch.

### Lỗi D — `csrf().useInvalidToken()` không compile

Đây là nhầm lẫn với API Servlet `SecurityMockMvcRequestPostProcessors.csrf()`. WebFlux `SecurityMockServerConfigurers.CsrfMutator` **không cung cấp** method này. Dùng actual HTTP header sai từ mục 8 với WebSession đã bootstrap, **không `mutateWith(csrf())`**.

### Lỗi E — `csrf()` pass nhưng token JSON/header thật bị 403

Helper kiểm thử mock condition hợp lệ; nó không tự chứng minh format raw/XOR, repository hoặc cookie session. Kiểm tra:

- `GET /csrf` có consume `Mono<CsrfToken>`?
- Repository thực là `WebSessionServerCsrfTokenRepository` hay cookie/custom?
- Request handler có yêu cầu XOR-masked token không?
- Header name có trùng `CsrfToken.getHeaderName()`?
- Cookie `SESSION` từ GET được gửi lại POST chưa?
- User có đủ quyền để handler xử lý sau khi qua CSRF chưa?

### Lỗi F — `GET /csrf` không trả token hoặc lỗi 500

Có thể `CsrfWebFilter` không hoạt động trên chain, endpoint đã bị Security matcher loại khỏi chain, hoặc controller đọc exchange attribute trước khi filter expose token. Kiểm tra `@Order`/`securityMatcher` và request handler. Không thay null token bằng một chuỗi hard-code; làm như vậy chỉ che việc Security không được gắn.

### Lỗi G — Không có `Set-Cookie: SESSION`

Token repository mặc định cần WebSession được tạo và lưu. Hãy kiểm tra GET có consume token publisher, response đã commit, session manager, cookie name, Spring Session configuration và thuộc tính cookie. Nếu app dùng `CookieServerCsrfTokenRepository` thì contract khác, đừng cưỡng ép assertion phải có `SESSION`.

### Lỗi H — Token đúng ở cùng session nhưng sai khi gửi từ SPA

Frontend có thể gửi raw cookie `XSRF-TOKEN` trong khi handler chờ token XOR-masked; hoặc gửi `X-CSRF-TOKEN` khi backend chờ `X-XSRF-TOKEN`. Test raw HTTP exchange theo format public contract của API, rồi chạy browser E2E qua đúng origin. Không vô hiệu CSRF để chữa lỗi.

### Lỗi I — Token cũ sau login/logout bất ngờ bị reject

Đây có thể là **hành vi an toàn mong muốn** nếu authentication/logout strategy đã xóa token. SPA phải bootstrap token mới và dùng cookie session mới nhất. Đừng lấy một token từ lúc chưa login rồi tái dùng mãi cho mọi POST.

### Lỗi J — Token của session S1 dùng cho S2 vẫn được chấp nhận

Điều tra ngay: client đã thật sự tạo hai sessions độc lập chưa? Repo có phải singleton token cố định? Filter có bị skip bởi test helper? Chain có bật CSRF không? Một test S1/S2 còn cần **positive T2/S2** để biết endpoint và quyền vẫn hoạt động.

### Lỗi K — OPTIONS preflight trả 401/403

OPTIONS không cần CSRF theo default matcher. Kiểm tra `CorsConfigurationSource` **Reactive**, allowed origins/methods/headers, filter ordering và proxy. `permitAll()` cho OPTIONS không tự sinh CORS headers; `csrf()` cũng không sửa CORS.

### Lỗi L — POST sai token trả 404/405 thay vì 403

Nếu request rơi ngoài Spring Security chain hoặc CSRF matcher miễn URL, router có thể xử lý và trả 404/405. Nhưng cũng có thể custom rejection handler đổi status. Test endpoint tồn tại, request method đúng, fallback chain hoạt động, rồi xác nhận filter đã chạy. Không kết luận “token được chấp nhận” chỉ vì không thấy 403.

### Lỗi M — Test JWT không hợp lệ luôn 403 thay vì 401

Nếu request POST qua browser chain còn bật CSRF và thiếu token, CSRF có thể chặn trước JWT authentication. Để kiểm chứng **JWT decoder** và 401, gửi GET protected API với Bearer sai qua chain Resource Server thật; nếu cần POST, đảm bảo policy CSRF cho chain đã được xác định độc lập.

### Lỗi N — Khi chạy song song, test token/session thỉnh thoảng thất bại

Các test sử dụng shared `ApplicationContext`, một `OrderRecorder` hoặc cookie jar có thể làm rò trạng thái. Trong fixture bài này reset counter ở `@BeforeEach` và giả định tests không chạy song song. Nếu project bật parallel tests, cô lập state theo request/test instance hoặc tạo fixture/session riêng, không chia sẻ cookie/token giữa tests.

### Lỗi O — HTTP test thật không cho dùng `csrf()` mutator

`CsrfMutator` cần mock `WebHttpHandlerBuilder`; nó không đưa token qua TCP như một HTTP client thực. Với `RANDOM_PORT`/`bindToServer` hãy bootstrap token, giữ cookie và gửi header/form như browser thực. `@WithMockUser` trong test thread cũng không thể tự authenticated request network.

## 18. Ma trận hồi quy được đề xuất

| ID | Request | Session/authentication | Actual CSRF token | Kỳ vọng |
| --- | --- | --- | --- | --- |
| R01 | GET `/public/ping` | Anonymous | Không | 200 |
| R02 | GET `/admin/report` | USER | Không | 403 authorization |
| R03 | GET `/admin/report` | ADMIN | Không | 200 |
| R04 | POST `/orders` | USER mock | Không `csrf()` | **403**, handler chưa chạy |
| R05 | POST `/orders` | USER mock | `mutateWith(csrf())` | 200, handler chạy |
| R06 | GET `/csrf` | Anonymous | N/A | Token response, session được lưu |
| R07 | POST `/orders` | USER + S1 | Header thiếu | **403**, handler không chạy |
| R08 | POST `/orders` | USER + S1 | `"invalid-test-token"` | **403** |
| R09 | POST `/orders` | USER + S1 | Token T1 từ S1 | **200** |
| R10 | POST `/orders` | USER + S1 | T1 nhưng header không nhận biết | **403** |
| R11 | POST `/orders` | USER + S2 | Token T1 từ S1 | **403** |
| R12 | POST `/orders` | USER, không gửi S1 | Token T1 | **403** |
| R13 | POST form `/orders` | USER + S1 | `_csrf` đúng | 200 |
| R14 | POST form `/orders` | USER + S1 | Parameter sai tên | **403** |
| R15 | POST `/orders` sau logout | Session cũ | Token cũ | Không được xử lý |
| R16 | OPTIONS `/orders` | Không cookie | Không | CORS quyết định; không yêu cầu CSRF |
| R17 | GET `/api/private` | Không Bearer | N/A | 401 trên Bearer-only API |
| R18 | GET `/api/private` | JWT sai chữ ký | N/A | 401 với decoder thật |
| R19 | GET `/api/admin` | JWT thiếu scope | N/A | 403 authorization |
| R20 | GET URL có semicolon | Bất kỳ | N/A | Firewall/parser reject theo policy |

Đặt **negative và positive controls trong cùng fixture có Security thực**. Nếu chỉ có các test 403 mà không có 200 đối ứng, có thể suite xanh vì app luôn reject request, handler không được map hoặc authentication luôn thất bại.

### 18.1. Mục tiêu về mức tin cậy

| Cấp kiểm thử | Độ tin cậy cho CSRF | Giới hạn |
| --- | --- | --- |
| `mutateWith(csrf())` mock test | Chứng minh flow sau điều kiện CSRF hợp lệ | Không chứng minh so khớp actual token |
| Mock WebTestClient với `GET /csrf` + cookie/header | Repository/handler + session trong mock context | Không kiểm tra TLS/proxy/browser rules |
| Live TCP `WebTestClient` | HTTP parser, Basic/JWT provider, cookies và filter thật | Chưa chắc qua CDN/ingress production |
| Browser E2E qua HTTPS staging | Browser cookie, CORS, CSP, HSTS, redirects, token bootstrap | Cần môi trường tương tự production |

### 18.2. Điều kiện release quan trọng

**Dừng release** nếu browser session POST thiếu token vẫn thực thi nghiệp vụ, hoặc token từ một session khác có thể được dùng để làm thay đổi trạng thái trái chính sách. Không nới CSRF matcher vì một frontend chưa gửi token đúng; sửa token bootstrap/handler/cookie, sau đó chạy lại negative tests.

## 19. Quy trình viết test thiếu/sai CSRF token có thể bảo trì

1. **Xác định stack và phiên bản:** Spring WebFlux, `ServerHttpSecurity`, `spring-security-test` và Spring Boot BOM.
2. **Xác định loại request:** unsafe method, browser credential tự gửi hay Bearer-only API?
3. **Chọn chain đúng:** `@Order`, `securityMatcher`, fallback và `authorizeExchange`.
4. **Giữ CSRF enabled:** đừng disable để vượt lỗi 403 khi chưa xác định nguyên nhân.
5. **Gắn test security:** `bindToApplicationContext(...).apply(springSecurity())` cùng custom security beans.
6. **Viết negative missing token:** authenticated USER, POST canonical path, không `csrf()`, assert 403 và side effect không xảy ra.
7. **Viết positive mock control:** cùng USER/POST nhưng có `mutateWith(csrf())`, assert handler được xử lý.
8. **Tạo token bootstrap:** consume `Mono<CsrfToken>` và trả token envelope bằng endpoint GET an toàn.
9. **Kiểm tra repository round-trip:** cùng WebSession, thử header thiếu, sai, đúng, sai vị trí và token của S1 trong S2.
10. **Kiểm tra token lifecycle:** login/logout/session timeout và cookie rotation bằng auth thật.
11. **Kiểm tra cùng CORS/SPA:** Origin allowlist, CSRF token ở header đúng dạng, SameSite/Secure và XSS/CSP.
12. **Kiểm tra HTTP public:** staging qua HTTPS reverse proxy, không coi status của edge là bằng chứng filter nào chạy.
13. **Đưa vào CI:** chạy tests độc lập state; log lý do lỗi đã làm sạch, không lộ token/session.

## 20. Bài tập thực hành

### Bài 1 — Tạo cặp âm/dương

Dùng fixture WebFlux ở mục 5. Viết `POST /orders` authenticated USER nhưng không có `csrf()`, assert 403 và counter bằng 0. Viết request thứ hai cùng principal với `csrf()`, assert 200 và counter bằng 1. Giải thích tại sao chỉ test thứ hai là chưa đủ.

### Bài 2 — Token sai với session đúng

Tạo `GET /csrf` trả `TokenEnvelope` và session cookie. Không dùng `csrf()`, gửi POST với `"invalid-test-token"` rồi gửi POST với token thực. Assert 403 và 200. Kiểm tra handler không được gọi ở request sai token.

### Bài 3 — Token đúng nhưng đặt sai vị trí

Gửi token thật trong `X-Unrecognized-CSRF` rồi đổi sang đúng `headerName` từ endpoint. Vì sao token string giống nhau nhưng một request 403, request kia được xử lý?

### Bài 4 — Hai WebSession

Bootstrap hai sessions độc lập S1/T1 và S2/T2. Gửi POST với S2/T1, kỳ vọng 403; sau đó S2/T2 kỳ vọng được phép. Không sử dụng test helper bypass CSRF. Giải thích vì sao phải kiểm tra sessions độc lập.

### Bài 5 — Form parameter

Dùng `BodyInserters.fromFormData` gửi hidden parameter `_csrf` theo `parameterName` từ server. Thử thiếu, sai tên và đúng giá trị. Giải thích vì sao production controller chỉ nhận JSON cần test bằng header thay vì form body.

### Bài 6 — Token raw so với XOR-masked

Chạy cùng một endpoint token với default `WebSessionServerCsrfTokenRepository`/`XorServerCsrfTokenRequestAttributeHandler`. Lấy token hai lần trong cùng session và đánh giá khác biệt. Sau đó cân nhắc `CookieServerCsrfTokenRepository` raw cookie và thiết kế handler tương thích; không tự tắt BREACH masking vì một test đỏ.

### Bài 7 — Login/logout và token cũ

Tạo form-login fixture với test user store. Bootstrap S1/T1, đăng nhập thật, lấy token/sessions mới nếu có, thử POST rồi logout. Viết negative request sau logout dùng cookie/token cũ. Giải thích vì sao `mockUser()` không test được login-success token rotation.

### Bài 8 — JWT và CSRF là hai token khác nhau

Tạo API Resource Server Bearer-only và browser fallback chain. Viết GET protected API thiếu JWT → 401, JWT có scope sai → 403; browser POST thiếu CSRF → 403. Đừng dùng `csrf()` làm JWT hợp lệ hoặc dùng `mockJwt()` để xác nhận signature decoder.

### Bài 9 — CORS preflight

Frontend khác origin gửi POST JSON với `X-CSRF-TOKEN`. Viết OPTIONS test allowed origin và denied origin, **không thêm csrf mutator**. Sau đó thực hiện POST thiếu token để xác nhận 403 riêng. Tại sao CORS 200 không làm POST tự động qua CSRF?

### Bài 10 — Browser và ingress

Viết một browser E2E chạy trên HTTPS staging: lấy CSRF envelope, lưu session cookie, gửi đúng header, thử thiếu/sai token. Kiểm tra cookie `Secure`/`SameSite`, CSP và HSTS trên HTML public. Đánh giá request path sau proxy rewrite; không log giá trị token/session vào test report.

## 21. Checklist trước khi merge kiểm thử token âm

- [ ] Đã xác định đây là **CSRF token** hay **Bearer access token**; hai loại có threat model và error semantics khác nhau.
- [ ] WebFlux test dùng `SecurityMockServerConfigurers` đúng Reactive package, không dùng Servlet `MockMvc` post processors.
- [ ] Dependency `spring-security-test` đồng bộ với Security/Framework/Boot đã resolve.
- [ ] Test client mock có `bindToApplicationContext(...).apply(springSecurity())` và context chứa chain thật.
- [ ] Test dùng đúng URL, HTTP method và handler có tồn tại; không nhầm 404/405 với 403 CSRF.
- [ ] Có negative POST **không** `mutateWith(csrf())` và có user đủ quyền; expected 403.
- [ ] Có positive POST cùng principal với `mutateWith(csrf())`; handler thành công.
- [ ] Nếu muốn test actual token, `GET /csrf` phải consume `Mono<CsrfToken>` và trả token đúng handler.
- [ ] Test WebSession/cookie giữ dữ liệu từ bootstrap sang POST và không gọi `csrf()` trong POST round-trip.
- [ ] Token sai, thiếu, sai header, sai parameter và token từ session khác đều bị từ chối.
- [ ] Có positive control **token đúng/same session** khi test token S1/S2.
- [ ] Không giả định `csrf().useInvalidToken()` tồn tại trên WebFlux.
- [ ] Phân biệt raw token/cookie `XSRF-TOKEN` với giá trị XOR-masked do request handler expose.
- [ ] Token cũ sau login/logout/session expiry được test bằng auth/session flow thật khi thuộc contract.
- [ ] OPTIONS preflight không bị coi là CSRF failure; CORS source đúng Reactive stack.
- [ ] Browser session chain vẫn bật CSRF dù API Bearer-only chain có policy miễn CSRF riêng.
- [ ] CSP/HSTS, HTTP firewall, session cookie flags và authorization có regression tests riêng.
- [ ] `@WebFluxTest` không bỏ sót custom chain, repository, handler và test dependencies.
- [ ] HTTP server thật không dùng `csrf()` mock mutator; request mang Basic/JWT credential và CSRF cookie/header thực.
- [ ] Browser/HTTPS staging đã kiểm chứng cookie SameSite/Secure/Domain/Path và CORS khi có cross-origin.
- [ ] Handler/repository/negative tests không log, hard-code hoặc xuất lộ token, session ID, JWT hay password thật.
- [ ] Bộ kiểm thử có side-effect assertion: request không hợp lệ **không** tạo dữ liệu/trigger event.

## 22. Nguồn tham khảo chính thức

1. [Spring Security — Testing with CSRF (Reactive WebTestClient)](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — cú pháp `mutateWith(csrf())` và phạm vi hỗ trợ test.
2. [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — `bindToApplicationContext`, `apply(springSecurity())`.
3. [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — default WebSession repository, cookie repository, token request handler, BREACH/XOR, form/header.
4. [Spring Security API — CsrfWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html) — default matcher, WebFilter contract, request handler và `skipExchange`.
5. [Spring Security API — WebFlux CSRF package](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/package-summary.html) — `CsrfException`, `CsrfToken`, `ServerCsrfTokenRepository`, request handlers.
6. [Spring Security API — XorServerCsrfTokenRequestAttributeHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html) — masking và raw-token resolution.
7. [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html) — test mutators `csrf`, `mockUser`, `springSecurity`.
8. [Spring Security source — SecurityMockServerConfigurers](https://github.com/spring-projects/spring-security/blob/main/test/src/main/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.java) — kiểm tra implementation `CsrfMutator`, đặc biệt mock `WebHttpHandlerBuilder`; khi debug hãy chọn tag/branch **khớp dependency version**, không coi branch main là contract vĩnh viễn.
9. [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — `authorizeExchange`, roles/authorities và chain semantics.
10. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — xử lý preflight trước authentication, origin/method/header allowlist.
11. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`, `SecurityWebFilterChain` và multi-chain.
12. [Spring Security — Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html), [Reactive HTTP Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — các lớp phòng vệ độc lập với CSRF.
13. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — mock context vs server TCP binding.
14. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`, `@SpringBootTest` và web test setup theo phiên bản.
15. [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — threat model, synchronizer token, defense in depth và cookie controls.

**Tự đánh giá:** Vì sao POST thiếu CSRF token cần được kiểm tra với một user đã authenticated? Nếu cả negative và positive test đều trả 403 thì có thể kết luận gì? Tại sao không dùng `csrf()` để thử token sai trong WebFlux? Khi lấy token thật từ `GET /csrf`, những dữ liệu nào phải được giữ qua POST? Vì sao token T1 của S1 không được gửi cùng S2, và tại sao token XOR-masked có thể khác giữa hai GET? Vì sao GET thiếu token hoặc OPTIONS preflight thiếu cookie không đồng nghĩa CSRF bị bỏ qua? Phân biệt CSRF 403, authorization 403 và JWT 401 bằng cách nào? Cuối cùng, khi nào test mock xanh nhưng vẫn cần test qua HTTP server thật hoặc browser HTTPS?
