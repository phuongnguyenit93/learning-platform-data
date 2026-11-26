# SecurityMockServerConfigurers.csrf() và token hợp lệ

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Trọng tâm:** Sử dụng `SecurityMockServerConfigurers.csrf()` với `WebTestClient` để viết kiểm thử CSRF cho Spring Security **WebFlux/Reactive**, đồng thời phân biệt một *request thử nghiệm được coi là hợp lệ* với việc truyền **CSRF token thật** qua WebSession, cookie, header hoặc form.  
> **Phạm vi:** Spring Security 6.5/7.x, Spring WebFlux, `spring-security-test`, Spring Boot 3.5/4.x. Các ví dụ giả định ứng dụng HTTP dùng session/cookie hoặc credential có thể được browser tự gửi; chính sách cho API Bearer-only phải được quyết định riêng theo threat model.

## 1. Vì sao cần bài kiểm thử CSRF riêng trong WebFlux?

Một trình duyệt đăng nhập vào `https://shop.example.com` có thể tự đính kèm session cookie khi gửi request tới website này. Nếu ứng dụng có endpoint `POST /orders` thay đổi trạng thái, một website không đáng tin có thể cố lừa browser thực hiện POST khi người dùng vẫn đang đăng nhập. Kiểm tra authentication chỉ biết người gửi **có session hợp lệ**, chưa chứng minh request xuất phát từ một thao tác hợp lệ của ứng dụng.

CSRF (*Cross-Site Request Forgery*) giải quyết một phần vấn đề đó bằng token bí mật gắn với client/session. Với unsafe HTTP methods, server yêu cầu client chủ động gửi token qua một vị trí như header hoặc form field, **không phải một giá trị mà browser tự đính kèm như cookie session**.

```text
Browser bình thường                     Website độc hại
       |                                      |
 Cookie session tự gửi               Có thể làm browser gửi cookie
       |                                      |
 X-CSRF-TOKEN: token đã lấy hợp lệ     Không tự biết token cần gửi
       |                                      |
       +----------------------+---------------+
                              |
                              v
               Spring WebFlux: CsrfWebFilter
                   Token hợp lệ?      Quyết định CSRF
                     /    \
                  Có       Không
                  |           |
            Tiếp tục authz   Thường 403
            và controller
```

Ở test, nếu chỉ thử `GET /orders` trả 200 hoặc user hợp lệ POST thành công bằng một helper mà không có test âm, ta có thể bỏ sót lỗi **CSRF đã vô tình bị tắt trong chain**. Bài này xây bộ kiểm thử chứng minh cả hành vi bị cấm và hành vi được phép.

### Kết quả học tập

Sau bài, bạn có thể:

1. Import `SecurityMockServerConfigurers.csrf()` đúng Reactive package và tích hợp với `WebTestClient`.
2. Dùng `mutateWith(csrf())` cho một request POST/PUT/PATCH/DELETE hợp lệ trong mock test mà không nhầm với `csrf()` Servlet của MockMvc.
3. Phân biệt xác thực (`mockUser`/`mockJwt`) với xác minh CSRF; đọc đúng ý nghĩa HTTP 401/403.
4. Thiết lập `bindToApplicationContext(...).apply(springSecurity())` và đảm bảo custom `SecurityWebFilterChain` thực sự nằm trong test context.
5. Viết test âm không token, test dương với `csrf()`, và test độc lập gửi token thật/tokens sai qua WebSession.
6. Hiểu `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerCsrfTokenRequestHandler` và BREACH masking trên WebFlux 6/7.
7. Không nhầm test helper với bảo vệ thực trong browser, token bootstrap, CORS, session rotation hay các lớp CSP/HSTS/firewall.

## 2. `csrf()` là API nào?

`csrf()` được sử dụng trong bài là static method của:

```java
org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers
```

Nó trả về một `SecurityMockServerConfigurers.CsrfMutator` có thể áp dụng trong cấu hình `WebTestClient`. Spring Security Reference Guide minh họa:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
    .post()
    .uri("/login")
    .exchange();
```

Ý nghĩa chính thức: **cung cấp điều kiện CSRF hợp lệ cho request test**. Điều này có ích khi mục đích chính là kiểm thử authorization, controller hoặc form-login trong một ứng dụng **vẫn bật CSRF**. Nó không thay `csrf.disable()` trên server và không tắt chính sách CSRF production.

### 2.1. Cần phân biệt ba tên gần giống nhau

| Tên | API | Phạm vi |
| --- | --- | --- |
| `SecurityMockServerConfigurers.csrf()` | WebFlux **test** support | Dùng với `WebTestClient.mutateWith(...)` |
| `ServerHttpSecurity.csrf(...)` | WebFlux **runtime** security DSL | Cấu hình CSRF trong `SecurityWebFilterChain` |
| `SecurityMockMvcRequestPostProcessors.csrf()` | Servlet **test** support | Dùng với `MockMvc` và `.with(csrf())` |

Ví dụ **không hợp lệ trong WebFlux**:

```java
// SAI: MockMvc post processor không phải WebTestClient configurer.
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

client.mutateWith(csrf());  // Sai kiểu API
```

Ví dụ **đúng**:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
    .post().uri("/orders")
    .exchange();
```

### 2.2. Tính khả dụng theo phiên bản

`SecurityMockServerConfigurers` có mặt từ Spring Security **5.0** trong API test Reactive. `csrf()` xuất hiện trong các Javadoc 5.8, 6.5 và 7.x; không phải một method mới riêng của 7.0. Tuy nhiên, **cách framework xử lý CSRF token ở runtime** đã thay đổi, chẳng hạn request handler XOR/BREACH từ 6.0, nên test token thật cần được đối chiếu theo version.

| Phần | 5.8 | 6.5 | 7.x |
| --- | --- | --- | --- |
| WebTestClient `csrf()` test mutator | Có | Có | Có |
| `CsrfWebFilter` trong WebFlux | Có | Có | Có |
| Runtime token handler mặc định | `ServerCsrfTokenRequestAttributeHandler` | `XorServerCsrfTokenRequestAttributeHandler` | `XorServerCsrfTokenRequestAttributeHandler` theo dòng |
| Repository mặc định | `WebSessionServerCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Servlet `csrf.spa()` | Không có | Không có | Có từ 7.0, **chỉ Servlet** |

Không suy API `csrf()` của test từ `CsrfConfigurer.spa()`: một bên dành cho **test mock exchange**, một bên là **cấu hình CSRF ứng dụng Servlet**.

## 3. Cần những dependency nào?

`WebTestClient` nằm trong Spring Test/WebFlux; `SecurityMockServerConfigurers` nằm trong `org.springframework.security:spring-security-test`. Với dự án dùng Spring Boot BOM, không chỉ định version riêng cho từng module khi không có nhu cầu đã kiểm chứng.

### 3.1. Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 3.2. Maven

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

Spring Boot 4 có các test starters chia nhỏ theo web stack; đối chiếu dependency và annotation package theo đúng Boot version. Không trộn Spring Security 7 artifact với một tổ hợp Boot/Framework không tương thích chỉ vì IDE thiếu import.

Để kiểm tra bản dependency đã resolve (chạy trong repo thực tế của người học):

```bash
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Ví dụ chỉ minh họa; Gradle và Maven dùng **một trong hai** tùy project. Trên Windows wrapper có thể là `gradlew.bat` hoặc `mvnw.cmd`. Bài này không chạy build/Gradle mà tập trung vào kiến thức và kỹ thuật kiểm thử.

### 3.3. Import cho WebFlux tests

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Không lấy các `...web.servlet...` imports của `spring-security-test` khi đang dùng `SecurityWebFilterChain`.

## 4. Mô hình test: token hợp lệ về mặt chính sách khác token thật qua HTTP

Hãy tách các câu hỏi kiểm thử:

| Kiểm thử cần trả lời | Công cụ phù hợp | Không nên suy |
| --- | --- | --- |
| “POST của user hợp lệ, với điều kiện CSRF hợp lệ, có qua authorization và controller?” | `mutateWith(mockUser(...)).mutateWith(csrf())` | Không chứng minh cookie/header token thật tồn tại |
| “Không đưa CSRF condition, POST có bị từ chối?” | Mock WebTestClient **không gọi `csrf()`** | 403 có thể đến từ quyền, phải có positive control |
| “Repository phát token và lưu ở session đúng không?” | GET token endpoint + WebSession cookie, không dùng `csrf()` | Không chứng minh bằng helper |
| “Header sai token có bị reject?” | Gửi raw HTTP header sai cùng session/token repository | Không suy từ `csrf()` |
| “Token cũ sau logout còn hợp lệ?” | Đăng nhập/logout thật và giữ cookie jar | Mock user không chạy login handler |
| “CORS origin được phép và preflight hợp lệ?” | OPTIONS với Origin/ACR headers | CORS không thay CSRF |
| “JWT thiếu scope bị 403 hay token sai chữ ký bị 401?” | Mock JWT cho authority, decoder/test issuer thật cho chữ ký | CSRF helper không giả lập crypto |

### 4.1. Chi tiết về chính `CsrfMutator`: đừng suy nó gửi một cookie/header thật

Javadoc ghi `csrf()` trả `CsrfMutator`. Reference Guide diễn đạt ngắn gọn rằng helper “provide a valid CSRF token”. Tuy nhiên, đây là **cơ chế hỗ trợ kiểm thử mock**, không phải thao tác của một trình duyệt: implementation của một số phiên bản sử dụng một `CsrfWebFilter` dành riêng cho test với matcher được cấu hình không yêu cầu xác minh để yêu cầu đi qua điều kiện CSRF. Như vậy, **không được xây test dựa trên giả định `csrf()` luôn viết một header `X-CSRF-TOKEN` hay phát một `Set-Cookie` có thể quan sát**.

```text
WebTestClient (mock context)
    |
    +-- mutateWith(mockUser()) -> cung cấp principal test
    |
    +-- mutateWith(csrf()) -> coi request đáp ứng điều kiện CSRF test
    |                       (theo cơ chế test support của version)
    |
    v
CsrfWebFilter / SecurityWebFilterChain trong test context
    |
    v
Authorization -> Handler

Không đồng nghĩa:
    GET /csrf -> Set-Cookie -> browser lưu cookie ->
    browser gửi X-CSRF-TOKEN với cùng WebSession.
```

**Quy tắc sử dụng:** dùng `csrf()` để kiểm tra *luồng request khi CSRF không còn là trở ngại*, và dùng **HTTP round-trip tests riêng** nếu mục tiêu là chứng minh token request được tạo/lưu/đọc/so khớp thật. Không khẳng định một chi tiết implementation bất biến giữa các phiên bản; coi Javadoc và test helper là contract có chủ đích, còn code source là đối chiếu lúc debug.

## 5. Fixture WebFlux hoàn chỉnh để kiểm thử

Để kết quả có nghĩa, ta cần controller thực sự đổi trạng thái, `SecurityWebFilterChain` bật CSRF và `WebTestClient` gắn Security. Các class sau dùng cho một **ứng dụng WebFlux test độc lập**, không trộn với `HttpSecurity`/`MockMvc` Servlet.

### 5.1. Controller tối giản

```java
package com.example.reactivecsrf;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

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
        return Mono.just("order-created");
    }
}
```

Đây là handler mô phỏng, không thực sự ghi order vào database. Test thực tế nên kiểm tra **side effect không xảy ra** khi request bị CSRF chặn, chẳng hạn repository không được gọi, nhưng không nên làm điều đó bằng một mock filter bỏ qua security pipeline.

### 5.2. WebFlux Security chain

```java
package com.example.reactivecsrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveCsrfSecurityConfig {

    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/csrf").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            // WebFlux CSRF mặc định được giữ rõ ràng để tiện học:
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Ở đây `POST /orders` có hai điều kiện **độc lập**: principal phải authenticated và token CSRF phải hợp lệ. `hasRole("ADMIN")` chỉ áp với `/admin/**`. `GET /csrf` ở phần sau được permit anonymous để bootstrap token nhưng **không phải** một endpoint “miễn CSRF cho mọi method”.

### 5.3. Khởi tạo WebFlux infrastructure và test user store

```java
package com.example.reactivecsrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class ReactiveTestAppConfig {

    @Bean OrdersController ordersController() {
        return new OrdersController();
    }

    @Bean
    MapReactiveUserDetailsService testUsers() {
        UserDetails user = User.withUsername("alice")
            .password("{noop}testing-only")
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}testing-admin-only")
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(user, admin);
    }
}
```

`@EnableWebFlux` phù hợp một context test thuần Spring; nếu dùng Boot auto-configuration, không nên tự thêm `@EnableWebFlux` chỉ để “làm test chạy” mà không xét ảnh hưởng tới WebFlux auto-configuration. `{noop}` là mật khẩu giả **chỉ cho fixture**, tuyệt đối không dùng production.

## 6. Bài test chuẩn: `springSecurity()` + `mutateWith(csrf())`

### 6.1. Gắn đúng application context

Ví dụ dùng JUnit 5/Spring Test trực tiếp, không cần khởi động web server trên cổng TCP:

```java
package com.example.reactivecsrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    ReactiveTestAppConfig.class,
    ReactiveCsrfSecurityConfig.class
})
class ReactiveCsrfWebTestClientTest {

    @Autowired ApplicationContext applicationContext;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicGetWithoutTokenIsAccepted() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void userPostWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .post().uri("/orders")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void userPostWithValidCsrfTestSupportIsAccepted() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .post().uri("/orders")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("order-created");
    }
}
```

Đây là mẫu cốt lõi của bài: hai request POST giữ **cùng principal, URL và method**; khác biệt duy nhất về mục tiêu là có hay không có `csrf()`. Nếu test không token nhận 403 nhưng test với token có body đúng, ta có bằng chứng phù hợp rằng việc áp điều kiện CSRF là yếu tố khiến request trước bị từ chối trong fixture này. Tham khảo [Spring Security — Reactive Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html).

### 6.2. Vì sao cần `.apply(springSecurity())`?

`bindToApplicationContext` dựng mock WebFlux handler pipeline từ Spring context; `springSecurity()` gắn **test support** cần thiết để các request mutators như `mockUser()` và `csrf()` tương tác đúng. Còn context phải thực sự có `SecurityWebFilterChain`/`WebFilterChainProxy` của ứng dụng; helper không tự tạo toàn bộ authorization rules thay cho bạn.

```text
ApplicationContext:
  ReactiveTestAppConfig + ReactiveCsrfSecurityConfig
            |
            v
WebTestClient.bindToApplicationContext(...)
            |
       apply(springSecurity())
            |
            v
mutateWith(mockUser("alice").roles("USER"))
mutateWith(csrf())
            |
            v
POST /orders -> CSRF test condition -> authorization -> controller
```

Nếu bạn chỉ dùng:

```java
WebTestClient noSecurity = WebTestClient
    .bindToController(new OrdersController())
    .build();

// Đây không phải regression test cho Spring Security:
noSecurity.post().uri("/orders")
    .exchange()
    .expectStatus().isOk();
```

thì request có thể trả 200 vì **chưa đưa Security WebFilters vào mock pipeline**. Không dùng kết quả ấy để kết luận CSRF của ứng dụng đã bị vô hiệu hóa hay hoạt động bình thường.

### 6.3. Các assertion phải phân biệt rõ

| Test | Authentication | `csrf()` | Expected nếu fixture đúng |
| --- | --- | --- | --- |
| GET `/public/ping` | Anonymous | Không | 200 |
| GET `/admin/report` | USER | Không | 403 — thiếu quyền |
| GET `/admin/report` | ADMIN | Không | 200 — đúng role |
| POST `/orders` | USER | **Không** | 403 — không đáp ứng CSRF |
| POST `/orders` | USER | **Có** | 200 — qua CSRF và authz |

Request POST anonymous không token có thể bị **CSRF từ chối trước** khi logic authentication chọn 401/redirect. Vì thế **không dùng một POST anonymous để “kiểm tra CSRF”** rồi ngạc nhiên khi nhận 403 thay vì 401. Dùng `mockUser` để giữ authentication ổn định khi cô lập CSRF.

## 7. `csrf()` và `mockUser()` là hai thao tác độc lập

### 7.1. Một thao tác cung cấp user, thao tác còn lại cung cấp điều kiện CSRF

```java
// Có user nhưng thiếu CSRF:
client.mutateWith(mockUser("alice").roles("USER"))
    .post().uri("/orders")
    .exchange()
    .expectStatus().isForbidden();

// Có CSRF nhưng không mock user cho private endpoint:
client.mutateWith(csrf())
    .post().uri("/orders")
    .exchange();
// Status là của authentication entry point, không tự động 200.

// Có cả user và điều kiện CSRF hợp lệ:
client.mutateWith(mockUser("alice").roles("USER"))
    .mutateWith(csrf())
    .post().uri("/orders")
    .exchange()
    .expectStatus().isOk();
```

Không dùng `csrf()` để “đăng nhập”, không dùng `mockUser()` để tự động có token CSRF và không trộn `@WithMockUser` vào test HTTP server qua cổng thật rồi kỳ vọng nó mang credential qua mạng.

### 7.2. Vai trò vs authority cũng là một lớp độc lập

```java
client.mutateWith(mockUser("alice").roles("USER"))
    .get().uri("/admin/report")
    .exchange()
    .expectStatus().isForbidden();

client.mutateWith(mockUser("admin").roles("ADMIN"))
    .get().uri("/admin/report")
    .exchange()
    .expectStatus().isOk();
```

`hasRole("ADMIN")` tìm authority `ROLE_ADMIN`. Nếu một endpoint cần `hasAuthority("SCOPE_orders:write")`, token CSRF hợp lệ **không cấp scope đó**. Hãy kiểm tra authorization bằng các test riêng, đặc biệt ở API JWT.

### 7.3. Có cần `csrf()` với GET, HEAD, OPTIONS và TRACE?

Theo CSRF matcher mặc định của Spring Security, các **safe methods** thường là GET, HEAD, OPTIONS, TRACE; CSRF được yêu cầu cho các phương thức còn lại như POST, PUT, PATCH và DELETE. Safe methods chỉ an toàn khi **application không thay đổi trạng thái bằng chúng**.

| HTTP method | CSRF theo default matcher | Lưu ý |
| --- | --- | --- |
| GET | Không | Không được thực hiện chuyển tiền/xóa tài nguyên ở GET |
| HEAD | Không | Chỉ đọc metadata |
| OPTIONS | Không | CORS preflight còn phụ thuộc cấu hình CORS |
| TRACE | Không theo default CSRF matcher | HTTP firewall có thể **chặn TRACE** trước |
| POST | Có | Login/logout và thao tác nghiệp vụ có side effect |
| PUT | Có | Thay tài nguyên |
| PATCH | Có | Sửa một phần tài nguyên |
| DELETE | Có | Xóa tài nguyên |

Không viết một test `csrf()` trên GET rồi kết luận filter chống CSRF đang hoạt động. Cần ít nhất một unsafe request âm và một request dương. Nếu API yêu cầu idempotency hoặc chỉ hỗ trợ method subset, test method thực tế theo hợp đồng nghiệp vụ.

## 8. Chẩn đoán 401, 403, 404 khi viết test CSRF

Một status không tự cho biết filter nào ra quyết định. Với WebFlux Security, quan sát security chain, CSRF matcher, authentication và authorization.

| Kết quả | Tầng có thể gây ra | Cách xác nhận |
| --- | --- | --- |
| 200 | CSRF qua, authz qua, handler chạy; **hoặc** Security bị bỏ qua | Có negative control không token? Có chain không? |
| 302/303 | Form login entry point/redirect | Request có authenticated principal không? |
| 400 | HTTP parser, firewall, input validation | URL có semicolon/encoded slash? |
| 401 | Authentication entry point (như HTTP Basic/JWT) | Test user/token có thật hoặc mock đúng không? |
| 403 | CSRF hoặc authorization hoặc CORS | Giữ principal, so POST có/không có `csrf()`; thử GET role |
| 404 | Không có handler hoặc request bị proxy/handler tùy chỉnh từ chối | URL có đúng path/matcher không? |
| 405 | Handler không hỗ trợ method | Có controller POST/PUT tương ứng không? |

**Một POST trả 403 dù đã thêm `csrf()`** có thể cho thấy user thiếu quyền, endpoint thuộc chain khác, custom CSRF handler/repository hoặc CORS bị từ chối. Đừng sửa bằng `csrf.disable()`. **Một POST không có token trả 200** là tín hiệu cần điều tra: chain bị bỏ qua, CSRF bị disable hoặc matcher miễn trừ endpoint.

## 9. Tại sao token thật cần repository và request handler?

Trong WebFlux, `CsrfWebFilter` phối hợp với hai thành phần:

| Thành phần | Vai trò | Default trong Spring Security 6/7 |
| --- | --- | --- |
| `ServerCsrfTokenRepository` | Sinh, lưu, tải expected token | `WebSessionServerCsrfTokenRepository` |
| `ServerCsrfTokenRequestHandler` | Expose token cho view/controller, resolve token từ request | `XorServerCsrfTokenRequestAttributeHandler` |
| `CsrfWebFilter` | Quyết định HTTP method có cần CSRF; so sánh token | Có trong chain bật CSRF |

Ở request GET, `CsrfWebFilter` có thể expose `Mono<CsrfToken>` trên `ServerWebExchange` attribute với key `CsrfToken.class.getName()`. Để **lấy token thật** cho SPA hay integration test, app phải subscribe/consume token này; chỉ gọi GET bất kỳ rồi đòi có một `Set-Cookie: XSRF-TOKEN` là không đúng với repository WebSession mặc định.

```text
CsrfWebFilter
   |
   v
ServerCsrfTokenRepository        ServerCsrfTokenRequestHandler
  (expected token)                 (exposed / resolved token)
   |                                   |
   +-- WebSession (default)            +-- ServerWebExchange attribute
   |                                   +-- masked value for view (XOR)
   |
   +-----------------------------------+
                 |
         Request header / form field
                 |
          Token hợp lệ hay không?
```

### 9.1. BREACH masking từ Spring Security 6

Từ Spring Security 6, WebFlux dùng `XorServerCsrfTokenRequestAttributeHandler` mặc định để che token khi trình bày cho view, giảm nguy cơ BREACH. Giá trị token view nhận được có thể thay đổi giữa các request ngay cả khi token nền tảng vẫn được lưu trong cùng một session. Không so sánh chuỗi token masked ở hai GET rồi tự kết luận repository đã rotate token.

**Token thô (raw) và token đã masking không luôn cùng dạng.** Nếu bạn lấy token từ GET endpoint expose bằng handler mặc định, frontend nên gửi **đúng giá trị mà handler expose** trong header/parameter tương ứng; không tự decode/encode khi không có thiết kế riêng.

### 9.2. Cookie repository không có nghĩa `csrf()` sẽ tạo cookie

`CookieServerCsrfTokenRepository` có thể được dùng nếu SPA cần cookie `XSRF-TOKEN`/header `X-XSRF-TOKEN`. Khi thay repository:

```java
// WebFlux ServerHttpSecurity, không phải Servlet HttpSecurity:
http.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()
));
```

Đây chỉ là cấu hình **repository**; default XOR handler vẫn cần được hiểu khi một SPA gửi raw token từ cookie. Không suy rằng một repository cookie tự động làm cho raw header tương thích với mọi request handler. `csrf()` test mutator không kiểm chứng những ranh giới này.

## 10. Cấp token thật qua `GET /csrf` trong WebFlux

Khi muốn xác minh **token được server sinh, được WebSession lưu và được gửi lại đúng dạng**, có thể dùng một endpoint GET an toàn để ứng dụng test nhận token thực của request handler.

### 10.1. Controller bootstrap

```java
package com.example.reactivecsrf;

import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class CsrfBootstrapController {

    @GetMapping("/csrf")
    public Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        // CsrfWebFilter expose Mono<CsrfToken> theo class name.
        Mono<CsrfToken> csrfMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (csrfMono == null) {
            return Mono.error(new IllegalStateException(
                "CsrfWebFilter did not expose token"));
        }

        return csrfMono.map(token ->
            ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "headerName", token.getHeaderName(),
                    "parameterName", token.getParameterName(),
                    "token", token.getToken()
                ))
        );
    }
}
```

Ở đây controller lấy **Mono** từ exchange và trả một publisher tiếp tục xử lý, **không gọi `block()` trong WebFlux event loop**. `token.getToken()` làm token thực sự được consume; một GET không cần dùng token thường có thể không tạo/lưu token ngay. Việc controller trả token qua JSON là quyết định kiến trúc; trong production cần CORS allowlist, cache policy và XSS protection tương ứng, không để response chứa token bị CDN cache nhầm.

### 10.2. Bổ sung controller vào test fixture

Đối với context thuần Spring ở mục 5.3, khai báo thêm đúng một bean:

```java
// Thêm vào ReactiveTestAppConfig:
@Bean CsrfBootstrapController csrfBootstrapController() {
    return new CsrfBootstrapController();
}
```

`GET /csrf` được `permitAll` trong `ReactiveCsrfSecurityConfig` ở mục 5.2, còn `POST /orders` vẫn có CSRF. Nếu dùng Spring Boot component scan trong application thật, controller `@RestController` có thể tự được đăng ký; **không** đồng thời thêm một bean trùng mapping từ `@Bean` và scan.

### 10.3. WebSession mặc định, không có cookie `XSRF-TOKEN` theo mặc định

Ở WebFlux, repository mặc định là `WebSessionServerCsrfTokenRepository`, vì vậy token kỳ vọng được gắn vào WebSession. Một session cookie có thể được phát dưới tên `SESSION` bởi `DefaultWebSessionManager` (tùy cấu hình session manager/cookie policy). **Không** đòi response `GET /csrf` tự xuất `XSRF-TOKEN` nếu bạn chưa cấu hình `CookieServerCsrfTokenRepository`.

```text
GET /csrf
   |
   v
CsrfWebFilter exposes Mono<CsrfToken>
   |
   v
CsrfBootstrapController consumes token Mono
   |
   +-- WebSessionServerCsrfTokenRepository lưu expected token
   |            |
   |            v
   |         WebSession
   |         cookie SESSION (thường)
   |
   +-- JSON body:
        {
          "headerName": "X-CSRF-TOKEN",
          "parameterName": "_csrf",
          "token": "<giá trị được handler expose>"
        }
```

Token trong response là dữ liệu nhạy cảm. Không log giá trị thực, không lưu trong test report công khai và không đưa vào URL query string. Ví dụ biểu diễn token bằng placeholder, không phải một JWT hay credential xác thực.

## 11. Kiểm thử HTTP round-trip **không** dùng `csrf()`

Mục tiêu phần này là thực sự thử repository và request handler. Khác với `mutateWith(csrf())`, test sẽ lấy token tại `GET /csrf`, giữ cookie session và đưa giá trị token vào header của POST.

### 11.1. Đọc CSRF envelope và cookie trong WebTestClient

Đoạn dưới dùng `client` bind vào application context **chứa `CsrfBootstrapController`**. Ngoài imports của mục 6 cần:

```java
import java.util.Map;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import static org.junit.jupiter.api.Assertions.assertNotNull;
```

Test minh họa:

```java
@Test
void realWebSessionTokenMustMatchSubmittedHeader() {
    // 1. Server cấp token bằng cơ chế WebFlux thật.
    EntityExchangeResult<Map> bootstrap = client.get()
        .uri("/csrf")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Map.class)
        .returnResult();

    Map<?, ?> body = bootstrap.getResponseBody();
    assertNotNull(body, "GET /csrf must return token envelope");
    String headerName = (String) body.get("headerName");
    String tokenValue = (String) body.get("token");
    assertNotNull(headerName);
    assertNotNull(tokenValue);

    // 2. Giữ session mà repository đã lưu expected token vào.
    ResponseCookie webSession =
        bootstrap.getResponseCookies().getFirst("SESSION");
    assertNotNull(webSession, "Expected WebSession cookie");

    // 3. Cùng WebSession nhưng không gửi token -> bị chặn.
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", webSession.getValue())
        .exchange()
        .expectStatus().isForbidden();

    // 4. Cùng WebSession và token SAI -> bị chặn.
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", webSession.getValue())
        .header(headerName, "deliberately-invalid")
        .exchange()
        .expectStatus().isForbidden();

    // 5. Cùng WebSession, token server đã expose -> hợp lệ.
    client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/orders")
        .cookie("SESSION", webSession.getValue())
        .header(headerName, tokenValue)
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("order-created");
}
```

**Phân biệt quan trọng:** test này **không gọi `mutateWith(csrf())` ở bất kỳ request POST nào**. Do đó, nếu test pass, ta đã thử một luồng CSRF token cụ thể của repository/handler chứ không chỉ helper giả lập điều kiện hợp lệ.

### 11.2. Điều kiện để test round-trip có ý nghĩa

| Điều kiện | Nếu thiếu, chuyện gì xảy ra? |
| --- | --- |
| App context có `CsrfWebFilter` đúng chain | `GET /csrf` không có exchange attribute token |
| Controller consume `Mono<CsrfToken>` | Token chưa chắc được tạo/lưu theo deferred-loading |
| Repository/handler giống lúc POST | Token dạng khác, server resolve không khớp |
| Giữ WebSession cookie từ GET sang POST | Server xem POST như session mới |
| Mock user chỉ dùng cho authorization | Test vẫn kiểm tra token thật vì **không** gọi `csrf()` |
| Header name/value lấy từ endpoint | Không hard-code sai header trong custom repository |
| Controller POST có handler đúng | Tránh hiểu 404/405 là lỗi CSRF |

Tên cookie `SESSION` là default trong nhiều cấu hình WebFlux; nếu dự án đổi cookie name/path hoặc dùng Spring Session hay proxy, **cập nhật test theo cookie contract của ứng dụng**. Không xem thiếu `SESSION` là bằng chứng chắc chắn CSRF tắt: có thể session chưa được start, repository khác, hoặc test client không giữ trạng thái.

### 11.3. Điều gì xảy ra với token XOR/masked?

Trong WebFlux 6/7, `XorServerCsrfTokenRequestAttributeHandler` có thể expose **masked token** cho endpoint GET. Vì test lấy token từ chính request handler và gửi lại không sửa đổi ở request header, handler giải mã/resolve theo cơ chế runtime của nó. Không hard-code so sánh token đã masked với một raw token xuất hiện trong database hoặc một cookie repo khác.

Khi ứng dụng tùy chỉnh handler, test round-trip **phải đi qua handler mới**, còn `csrf()` có thể vẫn tạo cảm giác “mọi thứ ổn” dù frontend thật chưa thể gửi đúng định dạng.

## 12. Viết test invalid/stale token đúng cách

### 12.1. WebFlux `csrf()` không phải Servlet `csrf().useInvalidToken()`

Javadoc `SecurityMockServerConfigurers.CsrfMutator` công bố các hook của `WebTestClientConfigurer`/`MockServerConfigurer`, không cung cấp một builder API `useInvalidToken()` tương tự Servlet `SecurityMockMvcRequestPostProcessors.csrf()`. Vì vậy **đừng copy**:

```java
// SAI khi sử dụng WebFlux SecurityMockServerConfigurers.csrf():
client.mutateWith(csrf().useInvalidToken())
    .post().uri("/orders")
    .exchange();
```

Hãy dùng HTTP token thật nhưng sai trong cùng WebSession như ở mục 11. Dùng input xấu có kiểm soát, không tự tạo “token rỗng” rồi mong server báo đúng exception nếu repository chưa từng có expected token.

### 12.2. Khi nào 403 là Missing và khi nào là Invalid?

Ở lớp CSRF, thiếu token hoặc token không khớp có thể dẫn đến access-denied/403. Với repository và handler cụ thể:

- Request không gửi header/parameter token có thể bị xem là **missing**.
- Request gửi token không trùng expected token có thể bị xem là **invalid**.
- Request đang ở WebSession mới có thể khiến expected token mới được tạo và token cũ không hợp lệ.
- Custom `ServerAccessDeniedHandler` có thể đổi HTTP status/message; status không phải toàn bộ nguồn sự thật.

Khi debug, có thể bật mức log Spring Security ở môi trường test để xác định filter/exception, nhưng **không ghi token, session cookie, Authorization header hoặc raw request body nhạy cảm** vào CI logs.

### 12.3. Hết phiên và CSRF token rotation

Token thuộc vòng đời authentication/session. Với browser app thực:

```text
Chưa đăng nhập:
  GET /csrf -> token T1, WebSession S1

Đăng nhập:
  POST /login (T1 + session S1 + credentials)
  authentication/session strategy có thể xóa hoặc đổi token/session

Sau đăng nhập:
  GET /csrf -> token T2 tương ứng trạng thái mới
  POST /orders (T2 + cookie session mới) -> hợp lệ

Đăng xuất:
  POST /logout với token hợp lệ
  session/authentication bị xóa

Lần POST tiếp theo:
  Phải lấy token hợp lệ theo session mới, không dùng mù T2
```

Mô hình trên cần được thực hiện với **form-login/OAuth login thật** để xác minh rotation. `mockUser()` cấp principal mock mà **không chạy authentication success handler**, nên nó không kiểm chứng tự động việc token bị xóa sau login/logout. Nếu một fixture chỉ bật HTTP Basic mà không có form login, đừng chạy POST `/login` theo ví dụ rồi tưởng đang test authentication lifecycle.

## 13. Kiểm thử form login và logout bằng `csrf()`

Spring Security Reactive CSRF documentation chọn `POST /login` làm ví dụ cho test helper vì login form là một state-changing operation. Đây là **một ví dụ về test support**, không có nghĩa `POST /login` trong mọi ứng dụng được cấu hình giống nhau.

### 13.1. Một cấu hình WebFlux có form login

Ở một fixture **khác** với HTTP Basic-only chain của mục 5, có thể bật:

```java
@Bean
SecurityWebFilterChain formLoginChain(ServerHttpSecurity http) {
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

Với form login do Spring Security cung cấp, POST yêu cầu username/password theo hợp đồng cấu hình, đồng thời CSRF vẫn bật. Không thêm chain này vào ứng dụng đang có chain fallback khác mà không xác định `@Order` và `securityMatcher`.

### 13.2. Test form POST với helper khi chỉ cần cô lập bước CSRF

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@Test
void loginFormWithCsrfTestConditionIsProcessed() {
    client.mutateWith(csrf())
        .post().uri("/login")
        .bodyValue("username=alice&password=testing-only")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .exchange()
        .expectStatus().is3xxRedirection();
}
```

Ví dụ chỉ phù hợp khi test context thực sự bật `formLogin` và có test user store đúng. Redirect success/failure phụ thuộc `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` và URL đích trong dự án; test một form login thành công nên **còn xác nhận authenticated session và truy cập route protected ở request tiếp theo**, không chỉ redirect.

### 13.3. Test login thiếu CSRF

```java
@Test
void loginFormWithoutCsrfIsRejected() {
    client.post().uri("/login")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .bodyValue("username=alice&password=testing-only")
        .exchange()
        .expectStatus().isForbidden();
}
```

Đối chiếu hai test trong cùng fixture có `formLogin` là hữu ích để tách lỗi CSRF khỏi lỗi password. Nhưng helper vẫn không tái hiện lifecycle token thật; để thử rotation/logout phải dùng WebSession cookie và thực hiện login/logout có cùng client state.

### 13.4. Vì sao không chuyển login/logout sang GET?

GET/HEAD được coi là safe trong CSRF matcher mặc định, vì vậy dùng GET để thay đổi trạng thái có thể tạo kẽ hở. Không làm `GET /logout` hoặc `GET /confirm-payment` chỉ để né CSRF. Giữ HTTP verbs có side effect, thêm token hợp lệ và test negative tương ứng.

## 14. CORS preflight khác CSRF: OPTIONS không cần `csrf()`

Giả sử SPA ở `https://app.example.com` gọi API WebFlux `https://api.example.com`. Browser có thể gửi một OPTIONS preflight trước POST JSON có header `X-CSRF-TOKEN`.

```http
OPTIONS /orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Theo Spring Security CORS guide, preflight thường **không chứa cookie xác thực**. CORS phải được xử lý trước authentication phù hợp; tự thêm `csrf()` vào OPTIONS không giúp nó được cấp quyền CORS và có thể che một lỗi cấu hình thực.

### 14.1. CORS config đúng Reactive package

```java
package com.example.reactivecsrf;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfig {

    @Bean
    CorsConfigurationSource csrfCorsSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
        ));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
```

Và trong `SecurityWebFilterChain`:

```java
// Inject tham số CorsConfigurationSource có kiểu Reactive:
http.cors(cors -> cors.configurationSource(csrfCorsSource));
```

`org.springframework.web.cors.reactive.CorsConfigurationSource` **khác kiểu** với interface cùng tên ở Servlet. Ở test thuần Spring, thêm `ReactiveCorsConfig.class` vào `@SpringJUnitConfig(classes=...)` nếu cần test CORS như runtime. Với CORS có credentials, không dùng allowed origin wildcard `*`.

### 14.2. Positive/negative CORS tests không dùng csrf mutator

```java
@Test
void allowedPreflightSucceedsWithoutAuthenticationOrCsrf() {
    client.options().uri("/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type,x-csrf-token")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin", "https://app.example.com")
        .expectHeader().valueEquals(
            "Access-Control-Allow-Credentials", "true");
}

@Test
void unknownOriginIsNotGrantedCorsPermission() {
    client.options().uri("/orders")
        .header("Origin", "https://untrusted.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectHeader()
        .doesNotExist("Access-Control-Allow-Origin");
}
```

Test assume CORS source mục 14.1 được gắn vào chain. Một origin bị từ chối có thể trả 403 hoặc status khác, nhưng phải **không có `Access-Control-Allow-Origin` cho origin không tin cậy**. `csrf()` không thể sửa allowlist, preflight headers hay browser credential mode.

### 14.3. Sau preflight, POST thật vẫn phải có token

```text
OPTIONS /orders
  -> CORS: origin/method/headers được phép
  -> Không phải thao tác tạo order
  -> Không có CSRF validation như POST

POST /orders
  -> Cookie/session có thể đi kèm theo browser policy
  -> Authentication, CSRF, authorization cùng áp dụng
  -> CSRF token hợp lệ vẫn bắt buộc khi dùng cookie
```

Một OPTIONS 200/204 không chứng minh POST CSRF thành công. CORS giới hạn khả năng một script cross-origin đọc response; nó **không** là biện pháp thay thế CSRF. Test cả CORS và CSRF riêng.

## 15. SPA, cookie, header và sự khác biệt same-origin/cross-origin

### 15.1. SPA và API cùng origin

Ví dụ browser tải HTML tại `https://app.example.com` và fetch `/csrf`/`/orders` cùng host qua reverse proxy. Nếu app dùng WebSession/token endpoint:

```javascript
async function fetchCsrf() {
  const response = await fetch("/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot bootstrap CSRF");
  return response.json();
}

async function submitOrder(order) {
  const csrf = await fetchCsrf();
  const response = await fetch("/orders", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(order)
  });
  if (!response.ok) throw new Error("Order rejected");
  return response;
}
```

Đây là phương án **token JSON qua GET**; nó không yêu cầu JavaScript đọc `XSRF-TOKEN` cookie và có thể giữ repository mặc định WebSession. Khi dùng handler XOR mặc định, client gửi lại đúng token trả về trong `csrf.token`. Phải bảo vệ endpoint HTML khỏi XSS; script đã chạy trong trusted origin thường có khả năng lấy token từ API same-origin.

### 15.2. SPA và API khác origin

```text
SPA: https://app.example.com
API: https://api.example.com

Cùng site trong nhiều ngữ cảnh, nhưng KHÁC origin.
Cookie host-only của api.example.com:
  Browser có thể gửi nó tới API nếu policy cho phép,
  nhưng JavaScript app.example.com KHÔNG đọc nó qua document.cookie.
```

CORS `Access-Control-Allow-Origin: https://app.example.com` có thể cho phép frontend **đọc response JSON `GET /csrf`** khi server đã duyệt origin. Nó không cấp quyền đọc cookie host-only của API bằng `document.cookie`. Nếu cần cookie cross-origin, browser `fetch` phải dùng `credentials: "include"`, API phải trả allow-credentials hợp lệ và cookie policy `SameSite`/`Secure`/`Domain`/`Path` phải tương thích.

Ưu tiên reverse proxy/BFF same-origin hoặc token endpoint có CORS allowlist được đánh giá. Không mở rộng cookie Domain cho mọi subdomain chỉ để chữa 403 và không tắt `HttpOnly` của **session authentication cookie**.

### 15.3. `CookieServerCsrfTokenRepository` và raw header

`CookieServerCsrfTokenRepository.withHttpOnlyFalse()` cho JavaScript đọc cookie CSRF. Cookie này **khác session cookie xác thực**. Nhưng khi handler dùng XOR masking, raw token trong cookie có thể không cùng định dạng với token đã được handler expose ở form; cần chọn request handler tương thích thay vì chỉ cấu hình repository.

```text
Cookie XSRF-TOKEN: raw T
    |
    +-- JavaScript đọc T, gửi X-XSRF-TOKEN: T
    |
    +-- Nhưng handler mặc định có thể chờ token XOR-masked
    |
    +-- Custom handler/SPA strategy phải được thiết kế cho raw header
```

Đừng coi một test `mutateWith(csrf())` pass là bằng chứng một SPA thực tế đã xử lý raw vs masked token đúng. Đó là lý do có test HTTP round-trip và browser E2E.

## 16. Nhiều SecurityWebFilterChain: `csrf()` chỉ hỗ trợ request, không chọn chain

Một WebFlux application có thể chia:

```text
@Order(1) /api/** -> Bearer-only Resource Server
@Order(2) fallback -> Browser session/form login
```

`securityMatcher` chọn chain; `authorizeExchange().pathMatchers` chọn quyền **bên trong chain**. Khi dùng `mutateWith(csrf())`, helper không chuyển request từ API chain sang browser chain và không tự bật CSRF ở chain đã disable.

### 16.1. Ví dụ cấu hình khung

```java
@Bean
@Order(1)
SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
            .anyExchange().authenticated()
        )
        // CHỈ cân nhắc nếu API thật sự Bearer-only, không chấp nhận
        // session cookie hoặc credential do browser tự gửi.
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
            .pathMatchers("/public/**", "/csrf").permitAll()
            .anyExchange().authenticated()
        )
        .csrf(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Ví dụ chỉ minh họa **chain isolation**; khi vận hành API cần `ReactiveJwtDecoder`/issuer và dependencies phù hợp. Không dùng hai chain này cùng lúc với `ReactiveCsrfSecurityConfig.web` fixture ở mục 5 nếu không xác định rõ order/matcher. Backend dùng Basic hoặc cookie authentication không được tự suy là Bearer-only để tắt CSRF.

### 16.2. Regression matrix cho các chain

| Request | Chain mong đợi | Phòng vệ quan trọng |
| --- | --- | --- |
| POST `/orders` qua browser cookie | Fallback browser | CSRF bật, test có/không có `csrf()` |
| POST `/api/orders` với Bearer thật | API | JWT auth/authority, CSRF theo threat model |
| POST `/api/orders` không auth | API | 401 hoặc entry point phù hợp |
| GET `/api/admin/report` với scope không đủ | API | 403 authorization |
| GET `/admin/report` | Fallback | Role, session/authentication |
| GET `/unknown` | Fallback | Không được lọt ngoài toàn bộ Security |

**Test rất quan trọng:** POST `/orders` với user nhưng **không `csrf()`** phải bị chặn. Nếu nó thành công sau khi thêm chain API, có thể matcher `/**` của API chain đã bắt nhầm route browser hoặc fallback không còn hoạt động.

## 17. `@WebFluxTest`, `@SpringBootTest` và HTTP server thật

### 17.1. Test slice không tự nạp toàn bộ security configuration

`@WebFluxTest` của Spring Boot tập trung vào một phần web layer, không bảo đảm mọi custom `SecurityWebFilterChain`, `ServerCsrfTokenRepository`, request handler hoặc authentication bean của application đều được nạp. Để test CSRF có nghĩa, phải import security configuration của ứng dụng cùng dependencies cần thiết.

Ví dụ package Spring Boot 3.5:

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
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@WebFluxTest(OrdersController.class)
@Import(ReactiveCsrfSecurityConfig.class)
class OrdersSecuritySliceTest {

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
    void sliceStillRequiresCsrf() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .post().uri("/orders")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .post().uri("/orders")
            .exchange()
            .expectStatus().isOk();
    }
}
```

Nếu security config cần một `ReactiveUserDetailsService` hoặc `ReactiveAuthenticationManager` mà slice không cung cấp, phải thêm test bean hợp lệ (ví dụ `@Import` configuration của test user store), không giải quyết bằng cách tắt Security. Đây là một ví dụ test slice tập trung chính sách; với tất cả Security WebFilters thật, `@SpringBootTest` full context có ích hơn.

### 17.2. Spring Boot 4 đổi package test annotations

```java
// Boot 4.x:
import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;

// Boot 3.5:
// org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest
// org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient
```

Đọc đúng migration guide của Boot phiên bản đã resolve. Không trộn các package hoặc starter test đời khác trong cùng module.

### 17.3. Full context khác HTTP server thật

```java
@SpringBootTest
class FullContextReactiveCsrfTest {
    @Autowired ApplicationContext context;

    @Test
    void csrfPolicyIsActive() {
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

`@SpringBootTest` mặc định sử dụng mock web environment, không tự mở TCP port. Test có thể chạy toàn bộ Security bean wiring mà không kết nối HTTP network.

Ngược lại, `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `WebTestClient.bindToServer()` gửi HTTP tới server thật. Ở đó, `csrf()` test mutator **không được dùng như trên mock builder**, vì implementation cần mock `WebHttpHandlerBuilder`; client thực phải lấy và gửi cookie/header token theo protocol. Trong Spring Security source có thông báo khi áp mutator cho HTTP builder không phù hợp: `Cannot apply Csrf because WebHttpHandlerBuilder is null. You must use mock clients.`

```java
// HTTP server thật: thay token/cookie bằng giá trị bootstrap từ /csrf.
http.post().uri("/orders")
    .cookie("SESSION", sessionCookie)
    .header(headerName, tokenValue)
    .headers(h -> h.setBasicAuth("alice", "testing-only"))
    .exchange();
```

Đây là fragment request, không phải standalone method: `http` là WebTestClient đã bind vào server, còn `sessionCookie`/`headerName`/`tokenValue` phải được lấy qua `GET /csrf`. `@WithMockUser` trong test thread không tự đưa principal qua HTTP network.

## 18. Bảo vệ HTTP khác vẫn cần được kiểm thử riêng

`csrf()` hỗ trợ kiểm thử một điều kiện CSRF, nhưng không thay thế các lớp phòng vệ thuộc `SPRING_SECURITY_HTTP_PROTECTION`.

| Lớp | Negative test | Positive test |
| --- | --- | --- |
| Authentication | Private GET không credential | HTTP Basic/JWT hợp lệ hoặc `mockUser` |
| Authorization | USER truy cập `/admin/**` bị 403 | ADMIN truy cập đúng route |
| CSRF | POST user có cookie nhưng thiếu token bị 403 | POST với `csrf()` hoặc token thật |
| CORS | OPTIONS origin lạ không có allow-origin | OPTIONS allowed origin có headers |
| CSP | HTML thiếu/sai directives phát hiện ở E2E | CSP đúng trên **document HTML** |
| HSTS | HTTPS public thiếu HSTS policy | HSTS xuất hiện trên TLS hostname phù hợp |
| HTTP firewall | Semicolon/encoded slash/method bất thường bị chặn | URL canonical được xử lý |
| Session | Token/cookie cũ sau logout không còn hợp lệ | Login/refresh tạo session/token hợp lệ |
| Multi-chain | Browser URL không lọt vào API chain | Fallback bảo vệ URL ngoài matcher |

### 18.1. Security headers

`Content-Security-Policy` cần được cấu hình chủ động; `X-Content-Type-Options: nosniff` thường có mặc định ở security header writer. `Strict-Transport-Security` chỉ có ý nghĩa khi browser nhận qua HTTPS public. Một test `csrf()` pass không chứng minh CSP, HSTS, cookie flags hay TLS proxy đang đúng.

Nếu frontend HTML do CDN phục vụ còn Spring chỉ trả JSON, CSP trên API response **không thay thế** CSP của trang HTML. Hãy xác định response owner trước khi assert.

### 18.2. HTTP firewall Reactive

Từ Spring Security 6.4, `StrictServerWebExchangeFirewall` có thể từ chối HTTP URI/method/header nguy hiểm trước khi request vào controller. Một request `/admin;mode=1/report` bị HTTP 400 (hoặc bị proxy từ chối) **không** cho biết CSRF token có đúng hay không. Test firewall bằng `MockServerWebExchange`/`StepVerifier` riêng và HTTP staging tests để xác minh proxy normalization.

### 18.3. Session lifecycle

`mockUser()` không tự lưu đăng nhập thực vào WebSession, cũng không kích hoạt toàn bộ authentication success/logout strategies. Muốn kiểm tra token cũ sau logout, phải thử authentication/session lifecycle bằng client duy trì cookie qua requests. Nếu dùng cluster Redis/WebSession, kiểm tra cả failover/multi-replica theo cấu hình thật.

## 19. Chẩn đoán lỗi khi dùng `SecurityMockServerConfigurers.csrf()`

### A. `csrf()` không compile hoặc import có kiểu sai

**Nguyên nhân thường gặp:** import từ `org.springframework.security.test.web.servlet...` dành cho MockMvc, chưa thêm `spring-security-test` hoặc dependency bị resolve về version không tương thích. Kiểm tra đúng import:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Đừng lấy `SecurityMockMvcRequestPostProcessors.csrf()` của Servlet rồi chuyển nguyên sang `WebTestClient.mutateWith`.

### B. POST không token vẫn trả 200

**Cần điều tra trước khi go-live.** Những khả năng:

- Test dùng `bindToController`/`bindToRouterFunction` mà không có security filters.
- `SecurityWebFilterChain` nhận request đã gọi `csrf.disable()`.
- CSRF matcher/`ignoringExchangeMatchers` bỏ qua URL.
- Client test đã được mutate để luôn đáp ứng CSRF, nên negative test vô tình có `csrf()`.
- Request thực ra vào chain khác không bật CSRF.

Hãy tạo request mới **không `csrf()`**, dùng authenticated principal, kiểm tra selected chain và CSRF config. Một test chỉ chứng minh 200 khi có `csrf()` sẽ không phát hiện được CSRF bị tắt.

### C. `mutateWith(csrf())` rồi vẫn nhận 403

Đây không nhất thiết là lỗi helper. Có thể authenticated user thiếu quyền, CORS chặn origin, API method security bị từ chối, custom CSRF/filter stack, hoặc test context không nạp chain đúng. Dùng một GET admin role test, giữ principal và URL cố định, rồi so request có/không có mutator. Nếu response đến từ custom `ServerAccessDeniedHandler`, kiểm tra logs/exception loại phù hợp, không log token.

### D. POST anonymous trả 403, mong đợi 401

CSRF có thể kiểm tra request unsafe trước authentication entry point. Muốn test 401 của HTTP Basic/JWT, dùng GET private không credential hoặc POST có `csrf()` khi đang ở mock context. Không dùng một POST anonymous thiếu token để xác nhận authentication behavior.

### E. `csrf().useInvalidToken()` không tồn tại

Đây là API của Servlet MockMvc, không phải contract của WebFlux `CsrfMutator`. Để test invalid token, giữ WebSession cookie từ GET `/csrf` và gửi một giá trị sai trong header thực, **không gọi `csrf()`**.

### F. Test `csrf()` pass nhưng frontend SPA production vẫn 403

Khả năng: token không được expose/consume, CSRF repository khác, WebSession cookie thiếu, header name sai, default XOR handler và raw cookie khác format, token cũ sau login/logout, CORS/SameSite/cross-origin khác. Viết lại test WebSession round-trip mục 11 và browser E2E qua public HTTPS; đừng tắt CSRF để giải quyết.

### G. Token nhận từ hai GET khác nhau dù không logout

Khi handler XOR/BREACH mặc định được dùng, giá trị **masked/exposed** có randomness nên có thể khác giữa các GET dù expected token ở WebSession chưa đổi. Test nên gửi token lấy từ GET tương ứng chứ không so token strings rồi khẳng định rotation.

### H. GET `/csrf` không tạo cookie `XSRF-TOKEN`

Với `WebSessionServerCsrfTokenRepository` mặc định, expected token lưu trong `WebSession` chứ không tự ghi `XSRF-TOKEN`. Nếu cần JavaScript đọc cookie CSRF thì phải cấu hình repository/handler theo kiến trúc SPA; hoặc dùng JSON token endpoint như bài minh họa. Không coi thiếu cookie XSRF mặc định là lỗi.

### I. Không thấy cookie `SESSION` sau bootstrap

Có thể token `Mono` chưa được subscribe, WebSession chưa được start, repo không dùng WebSession, cookie manager đã đổi tên hoặc test có custom session store. Kiểm tra exchange attribute, repository đã resolve, response `Set-Cookie` và session manager. Đừng đoán cookie tên `SESSION` là bất biến của mọi WebFlux deployment.

### J. HTTP server thật báo không thể áp CsrfMutator

`CsrfMutator` cần mock server WebHttpHandlerBuilder. Với `bindToServer` hoặc RANDOM_PORT TCP request, gửi header/cookie/token theo flow thực; không dùng mock exchange configurer thay cho HTTP protocol.

### K. OPTIONS preflight 401

Đừng thêm `csrf()` vào OPTIONS. Kiểm tra Reactive `CorsConfigurationSource`, `Origin`, `Access-Control-Request-Method`, allowed headers, chain matcher và ingress. OPTIONS có thể không có cookie; xử lý CORS phải xảy ra trước yêu cầu login.

### L. 403 biến mất sau khi thêm JWT API chain

Kiểm tra `@Order` và `securityMatcher`. Một API chain với matcher quá rộng có thể bắt request browser có cookie nhưng CSRF đã bị tắt. Test POST browser không token, GET admin và URL ngoài matcher hẹp; bảo đảm fallback chain vẫn bảo vệ.

### M. `@WebFluxTest` pass còn `@SpringBootTest` fail

Test slice có thể không nạp custom `SecurityWebFilterChain`, repository/handler, CORS source hoặc custom filter. Import cấu hình đúng hoặc dùng full context cho policy test. Không “làm đồng bộ kết quả” bằng cách tắt CSRF trong full context.

### N. POST có `csrf()` trả 404 hoặc 405

CSRF có thể đã cho request đi tiếp, nhưng controller không có handler cho URL/method. Kiểm tra mapping/router, base path, URL rewrite và application context. 404/405 không phải bằng chứng CSRF sai.

### O. Test login/logout bằng `mockUser()` không thấy rotation

`mockUser()` không chạy login success handler. Test vòng đời token cần HTTP authentication/logout thực, giữ cookie jar và quan sát CSRF token session qua GET bootstrap. Nếu app chưa cấu hình form login, `POST /login` sẽ không tự xuất hiện chỉ vì bạn bật HTTP Basic.

## 20. Ma trận hồi quy CSRF tối thiểu và mở rộng

| Test | User/session | CSRF | Kết quả được kỳ vọng |
| --- | --- | --- | --- |
| GET `/public/ping` | Anonymous | Không | 200, không cần token |
| GET `/admin/report` | USER | Không | 403 thiếu ADMIN, **không phải CSRF** |
| GET `/admin/report` | ADMIN | Không | 200 |
| POST `/orders` | USER mock | Không có `csrf()` | 403 nếu CSRF bật |
| POST `/orders` | USER mock | Có `csrf()` | 200 qua CSRF/authz |
| POST `/orders` | Anonymous mock | Có `csrf()` | Không mặc định 200: còn authentication |
| GET `/csrf` | Anonymous WebSession | Không | Token envelope nếu endpoint được cấu hình |
| POST `/orders` | USER + WebSession | Header thiếu | 403 |
| POST `/orders` | USER + WebSession | Header sai | 403 |
| POST `/orders` | USER + WebSession | Header server cấp | 200 (handler tồn tại) |
| POST `/orders` | Session đã logout | Token cũ | Không được chấp nhận theo policy |
| OPTIONS `/orders` | Không session | Không | CORS preflight được xử lý theo Origin |
| GET URL có semicolon | Phụ thuộc | Không | HTTP firewall/parser xử lý, **không phải CSRF test** |
| HTTPS public GET | Phụ thuộc | Không | CSP/HSTS/cookie policies kiểm tra riêng |

**Điểm quan trọng:** test với `csrf()` là một mảnh ghép trong ma trận, không phải toàn bộ bằng chứng chống CSRF. Muốn chứng minh implementation chính xác, còn phải xác nhận session, header và token lifecycle.

## 21. Bài tập thực hành

### Bài 1 — Viết cặp test âm/dương chuẩn

Tạo WebFlux controller `POST /orders`, chain `csrf(Customizer.withDefaults())` và WebTestClient `bindToApplicationContext(...).apply(springSecurity())`. Viết hai tests: cùng `mockUser("alice").roles("USER")`, POST không `csrf()` bị 403, POST có `csrf()` trả kết quả thành công. Giải thích vì sao chỉ test positive là chưa đủ.

### Bài 2 — Phân biệt CSRF và authorization

Đặt `GET /admin/report` yêu cầu `hasRole("ADMIN")`. Viết test USER bị 403, ADMIN được 200 mà không cần `csrf()`. Sau đó thêm một POST admin route cần cả ROLE_ADMIN và token CSRF; thử thiếu một trong hai điều kiện. Phân biệt nguyên nhân mỗi response.

### Bài 3 — Token endpoint trong WebFlux

Tạo `GET /csrf` lấy `Mono<CsrfToken>` từ `ServerWebExchange` và trả envelope `headerName`/`token`, không log token. Viết test dùng WebSession cookie giữa GET và POST mà **không gọi `csrf()`** trong POST.

### Bài 4 — Token sai và BREACH

Trong cùng WebSession, gửi một POST với header `X-CSRF-TOKEN: invalid` và một POST với token từ endpoint bootstrap. Test 403 vs 200. Quan sát token ở hai GET; giải thích vì sao XOR-masked value có thể đổi ngay cả khi expected token ở session chưa rotate.

### Bài 5 — Form login và logout

Tạo một fixture bật `formLogin` và `logout`, user store test-only. Thử POST `/login` thiếu CSRF, POST có `csrf()`. Sau đó thử login/logout **không dùng helper** bằng token thật và WebSession cookie, kiểm tra token cũ không được giữ nguyên một cách vô điều kiện.

### Bài 6 — CORS preflight

Frontend `https://app.example.com` gửi POST JSON có `X-CSRF-TOKEN`. Cấu hình `CorsConfigurationSource` Reactive và kiểm thử OPTIONS từ origin đúng/sai không có `csrf()`. Tại sao preflight thành công không chứng minh POST session-cookie sẽ được CSRF cho qua?

### Bài 7 — Multiple security chains

Thiết kế API Bearer-only chain `/api/**` và browser fallback chain. Tắt CSRF chỉ ở API chain **sau threat-model review**; test POST `/orders` browser không token vẫn bị 403, và `/api/orders` cần Bearer authentication/scope. Điều gì xảy ra nếu API matcher trở thành `/**`?

### Bài 8 — Test slice so với server thật

Trên Spring Boot 3.5 hoặc 4.x, viết `@WebFluxTest` có import security config đúng. So sánh với `@SpringBootTest(RANDOM_PORT)`: test mock được phép dùng `csrf()` nhưng HTTP client thật phải gửi WebSession cookie/header token từ GET bootstrap. Xác minh lỗi nếu cố áp mock mutator lên client bind-to-server.

### Bài 9 — Các lớp bảo vệ không thay thế nhau

Giữ `csrf()` positive test xanh nhưng cố tình bỏ CSP trên HTML, cấu hình CORS origin quá rộng hoặc thiếu fallback chain. Viết tests riêng để phát hiện mỗi regression; giải thích tại sao CSRF test không thể phát hiện chúng.

## 22. Checklist trước khi merge một test liên quan `csrf()`

- [ ] Xác định chính xác WebFlux Reactive, không dùng `SecurityMockMvcRequestPostProcessors` Servlet.
- [ ] `spring-security-test` cùng dòng tương thích với runtime Security/Framework/Boot.
- [ ] `WebTestClient` mock bind vào đúng `ApplicationContext` và có `.apply(springSecurity())`.
- [ ] Application context của test chứa đúng `SecurityWebFilterChain`, `CsrfWebFilter` và CSRF repository/handler cần kiểm tra.
- [ ] Có ít nhất **một POST không `csrf()` bị 403** và **một POST cùng principal với `csrf()` được xử lý**.
- [ ] Có test authorization riêng, không coi mọi 403 đều là CSRF.
- [ ] Không gọi `csrf().useInvalidToken()` như Servlet; dùng token sai qua WebSession/header test.
- [ ] `GET /csrf` trả token do request handler expose và `Cache-Control: no-store` nếu dùng token endpoint.
- [ ] Token round-trip test giữ cookie session và **không gọi `csrf()` ở request POST**.
- [ ] Không hard-code token masked bằng raw token; test đúng handler/repository của version thực tế.
- [ ] Kiểm tra token cũ sau login/logout bằng luồng authentication thực, không suy từ `mockUser()`.
- [ ] OPTIONS preflight kiểm tra CORS origin/method/headers riêng, không dùng `csrf()` để “sửa” CORS.
- [ ] Bearer-only API và browser session chain được test độc lập; không miễn CSRF ở browser chỉ vì API có JWT.
- [ ] Test slice có custom security config và không bỏ Security filters vì thiếu bean.
- [ ] Không kỳ vọng `csrf()` gửi header/cookie thật hay dùng được trên `bindToServer()`.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` và CORS behavior được thử trên browser/HTTPS public khi cần.
- [ ] CSP/HSTS/HTTP firewall/session có regression tests riêng.
- [ ] Không log CSRF token, session ID, JWT, password hoặc dữ liệu sensitive trong logs/artifacts của CI.

## 23. Tài liệu tham khảo chính thức

1. [Spring Security — Reactive Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — cú pháp `mutateWith(csrf())` và mục đích cung cấp điều kiện CSRF hợp lệ cho test.
2. [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — `bindToApplicationContext`, `apply(springSecurity())`.
3. [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html) — method `csrf()`, `mockUser()` và `springSecurity()`.
4. [Spring Security API — CsrfMutator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.CsrfMutator.html) — giao diện `WebTestClientConfigurer`/`MockServerConfigurer` và phạm vi mock handler.
5. [Spring Security source — SecurityMockServerConfigurers](https://github.com/spring-projects/spring-security/blob/main/test/src/main/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.java) — code tham khảo **theo branch/version**, không coi implementation hiện tại là contract vĩnh viễn.
6. [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — `CsrfWebFilter`, WebSession/cookie repository, `ServerCsrfTokenRequestHandler`, BREACH, token trong form/header.
7. [Spring Security API — CsrfWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html) — filter, default request matcher, token repository, request handler.
8. [Spring Security — Reactive Authentication Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html) và [OAuth2 Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html) — `mockUser()`/`mockJwt()` và vai trò.
9. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`, `SecurityWebFilterChain`, matcher và multi-chain.
10. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html), [Reactive Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html), [Reactive Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — các lớp bảo vệ HTTP độc lập với CSRF.
11. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — mock controller/router/context, live server setup.
12. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`/`@SpringBootTest` và test configuration theo version.
13. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — threat model, synchronizer token, SameSite và lớp bảo vệ bổ sung.

**Tự đánh giá:** `SecurityMockServerConfigurers.csrf()` thuộc package nào và dùng với loại test client nào? Vì sao test POST có `csrf()` thành công chưa chứng minh server đã lưu và so khớp một token HTTP thật? Trong cùng một WebSession, làm sao viết test thiếu token, token sai và token đúng mà **không** dùng helper? Vì sao masked token ở hai request GET có thể khác nhau? Khi nào OPTIONS không cần CSRF nhưng CORS vẫn từ chối? Và tại sao cần kiểm tra riêng authentication, authorization, headers, firewall, session và chain matcher dù bộ test CSRF đã xanh?
