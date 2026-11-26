# Mutator WebTestClient không áp dụng cho request HTTP thật

## 1. Triệu chứng: có `mockUser()` mà server vẫn trả `401`

Trong Spring Security Test, bạn có thể đã viết thành công kiểm thử WebFlux như sau:

~~~java
client.mutateWith(mockUser("alice").roles("USER"))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

Sau đó nhóm chuyển sang `@SpringBootTest(webEnvironment = RANDOM_PORT)` và dùng `WebTestClient.bindToServer()` để kiểm thử qua cổng HTTP thật. Người viết giữ nguyên `mutateWith(mockUser(...))`, rồi ngạc nhiên khi request nhận `401 Unauthorized`, hoặc thấy lỗi liên quan tới mock server/security test configurer.

Vấn đề không nhất thiết nằm ở role `USER`, controller hoặc password. **`mockUser()` là một helper giả lập `Authentication` trong ngữ cảnh mock WebFlux; nó không tạo header HTTP để chuyển danh tính tới một server qua socket.**

Trong module `SPRING_SECURITY_TESTING`, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên cả Servlet và Reactive. Những công cụ như `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập giúp kiểm thử nhanh — nhưng phải phân biệt **danh tính do test gắn vào mock exchange** với **credentials được server nhận và xác minh từ HTTP request**.

Sau bài này, bạn sẽ có thể:

1. Nhận diện client đang gắn vào mock WebFlux context hay HTTP server thật.
2. Giải thích vì sao `mockUser()`, `mockJwt()`, `mockOidcLogin()` và `csrf()` không thay thế HTTP credentials, session hoặc CSRF token qua mạng.
3. Gửi HTTP Basic, Bearer JWS, form login và cookies đúng cách qua `bindToServer()`.
4. Thiết kế ca đối chứng `200`/`401`/`403` để phân biệt authentication, authorization và CSRF.
5. Khoanh vùng lỗi do security chain, entry point, dependency, sai web stack hoặc dữ liệu test chưa commit.
6. Ghi chính xác mức độ tích hợp mà một phép thử đã chứng minh.

## 2. Hai cơ chế thực thi của WebTestClient

`WebTestClient` là API xây dựng request và khẳng định HTTP response. **Cùng tên client không đồng nghĩa cùng kiểu backend.** Có hai nhóm setup quan trọng:

| Kiểu gắn client | Ví dụ | Có socket HTTP? | Có phù hợp với mock security mutator? |
| --- | --- | --- | --- |
| Gắn vào WebFlux application context | `bindToApplicationContext(context)` | Không | Có, khi tích hợp `springSecurity()` đúng |
| Gắn vào router/controller mô phỏng | `bindToRouterFunction(router)` hoặc `bindToController(controller)` | Không | Tùy setup mock server/security filters; không tự tải toàn bộ security chain |
| Gắn vào server thật | `bindToServer().baseUrl("http://localhost:" + port)` | **Có** | Không thể dùng mock principal mutator để truyền authentication qua socket |
| Client do Boot auto-configure | `@AutoConfigureWebTestClient` / test injection | **Phụ thuộc test environment** | Phải xác định nó đã được gắn vào đâu |

### 2.1. Gắn vào mock WebFlux application context

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
~~~

Với setup này, Spring Security Test tích hợp với mock server exchange trong tiến trình JUnit. Mutator `mockUser()` có thể tạo test authentication cho **request mô phỏng**.

### 2.2. Gắn vào cổng HTTP thật

~~~java
WebTestClient http = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .build();
~~~

Client này giao tiếp bằng HTTP với embedded server. Request cần mang **chứng cứ mà server có thể đọc được**: `Authorization` header, form fields, cookies, CSRF token hoặc bearer access token. `SecurityContext` ở phía JUnit không phải định dạng truyền dữ liệu của HTTP.

### 2.3. Hai trục đừng nhầm lẫn

| Nguồn danh tính | Đường request | Điều kiểm chứng |
| --- | --- | --- |
| `mockUser()` | Mock WebFlux | Phân quyền với principal giả |
| HTTP Basic header | Mock WebFlux | Filter/manager kiểm tra username/password của request mô phỏng |
| HTTP Basic header | Server thật | Filter/manager **và** đường HTTP qua socket |
| `mockJwt()` | Mock WebFlux | Phân quyền với JwtAuthenticationToken giả |
| Bearer JWS được ký thật | Mock WebFlux có decoder thật | JWT decoder/validators và policy, không kiểm tra TCP |
| Bearer JWS được ký thật | Server thật có decoder thật | JWT decoder/validators, policy và HTTP boundary |
| `@WithMockUser` ở thread JUnit | Server thật | Không tự cung cấp danh tính cho request mạng |

**Điểm tinh tế:** không phải mọi tính năng cấu hình WebTestClient đều bị vô hiệu khi dùng `bindToServer()`. Các tùy chọn bình thường như `baseUrl`, `defaultHeader`, timeout hoặc việc gửi HTTP Basic/Bearer headers **vẫn có tác dụng**. Giới hạn đang nói tới là **mock-server security mutators** của `spring-security-test`, không phải mọi cách thay đổi cấu hình HTTP client.

## 3. Request đi đến đâu? Sơ đồ xác định nguyên nhân

~~~mermaid
flowchart TD
    A["JUnit gọi WebTestClient"] --> B{"Client gắn vào đâu?"}
    B -- "ApplicationContext / mock WebFlux" --> C["MockServerWebExchange"]
    C --> D["springSecurity() test configurer"]
    D --> E["mockUser / mockJwt tạo Authentication giả"]
    E --> F["SecurityWebFilterChain và handler trong context"]
    B -- "bindToServer()" --> G["HTTP client encoder"]
    G --> H["TCP / embedded server"]
    H --> I["SecurityWebFilterChain của server"]
    I --> J{"Request có credentials thật?"}
    J -- "Không" --> K["Entry point: 401 hoặc redirect"]
    J -- "Có" --> L["Authentication manager / decoder"]
    L -- "Hợp lệ" --> M["Authorization và controller"]
    L -- "Không hợp lệ" --> N["401 / authentication failure"]
~~~

Khi sửa lỗi, hãy xác định **nút đầu tiên bị bỏ qua**. Nếu test dùng mock principal trên real HTTP, server có thể không nhận được bất kỳ authentication material nào. Nếu đã gửi Basic/JWT thật nhưng vẫn nhận `401`, mới điều tra authentication manager, decoder, user store hoặc token validator.

## 4. Ví dụ WebFlux hoàn chỉnh để tái hiện lỗi

Chúng ta chuẩn bị ứng dụng WebFlux có:

| Request | Quy tắc | Dự kiến |
| --- | --- | --- |
| `GET /api/public` | `permitAll()` | Khách nhận `200` |
| `GET /api/private` | `authenticated()` | Không credentials `401`; Basic đúng `200` |
| `GET /api/admin` | `hasRole('ADMIN')` | USER `403`; ADMIN `200` |
| `POST /api/notes` | `authenticated()` và CSRF mặc định | Thiếu CSRF thường `403` |

Gradle dependencies tối thiểu cho demo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tùy Spring Boot version, các package test auto-configuration có thể khác; trong ví dụ chủ động tạo `WebTestClient` để thấy rõ cách binding.

### 4.1. Controller

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoApi {

    @GetMapping("/api/public")
    Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    Mono<Map<String, String>> privateInfo(Mono<Principal> principal) {
        return principal.map(p -> Map.of("user", p.getName()));
    }

    @GetMapping("/api/admin")
    Mono<String> admin() {
        return Mono.just("admin");
    }

    @PostMapping("/api/notes")
    Mono<String> createNote() {
        return Mono.just("created");
    }
}
~~~

### 4.2. Security configuration dùng HTTP Basic

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class DemoSecurity {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(ex -> ex
                    .pathMatchers("/api/public").permitAll()
                    .pathMatchers("/api/admin").hasRole("ADMIN")
                    .pathMatchers("/api/private", "/api/notes")
                        .authenticated()
                    .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader-password")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin-password")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

`{noop}` chỉ dùng cho tài khoản cố định của **bài test**. Hệ thống thật cần password encoder mạnh, lưu secrets an toàn và HTTPS. Vì đã bật HTTP Basic, demo mong đợi request chưa xác thực đến endpoint bảo vệ nhận `401`; với form login, response có thể là `302` redirect.

## 5. Test A: mock WebFlux dùng `mockUser()` đúng mục đích

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class MockReactiveSecurityTests {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void guestIsRejected() {
        client.get()
              .uri("/api/private")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void mockReaderGetsPrivateContent() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .get()
              .uri("/api/private")
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void mockReaderCannotEnterAdminArea() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void mockAdminCanEnterAdminArea() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isOk();
    }

    @Test
    void postWithoutCsrfIsRejected() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .post()
              .uri("/api/notes")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfIsAccepted() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .mutateWith(csrf())
              .post()
              .uri("/api/notes")
              .exchange()
              .expectStatus().isOk();
    }
}
~~~

**Kết luận hợp lệ:** `SecurityWebFilterChain` và controller trong mock application context chấp nhận USER ở `/api/private`, từ chối USER ở `/api/admin`, chấp nhận ADMIN và áp dụng CSRF cho `POST`.

**Kết luận không hợp lệ:** “Password `reader-password` đã được kiểm tra” hoặc “một HTTP client ngoài process đã đăng nhập thành công”. `mockUser()` không gửi password để `ReactiveAuthenticationManager` so sánh.

### 5.1. Một phép đối chứng quan trọng

Bạn có thể đặt username **không tồn tại trong user store**:

~~~java
client.mutateWith(mockUser("ghost").roles("USER"))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.user").isEqualTo("ghost");
~~~

Ca này có thể cho `200`. Đó không phải lỗi của Spring Security: chính test đã tạo principal `ghost` và tuyên bố nó đã được xác thực trong mock exchange. Mục tiêu của test là authorization với principal giả, **không phải tra cứu account**.

## 6. Test B: `RANDOM_PORT` với `bindToServer()`

Giờ yêu cầu thay đổi: phải kiểm tra authentication từ request HTTP thật, cả khi password đúng và sai.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpReactiveSecurityTests {

    @LocalServerPort
    int port;

    WebTestClient http;

    @BeforeEach
    void connect() {
        http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void guestIsRejectedByServer() {
        http.get()
            .uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongPasswordIsRejectedByServer() {
        http.get()
            .uri("/api/private")
            .headers(h -> h.setBasicAuth(
                "reader", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void correctPasswordIsAuthenticatedByServer() {
        http.get()
            .uri("/api/private")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void readerCannotEnterAdminArea() {
        http.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanEnterAdminArea() {
        http.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-password"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void inventedAccountIsRejected() {
        http.get()
            .uri("/api/private")
            .headers(h -> h.setBasicAuth(
                "ghost", "any-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Các credentials **được truyền trên HTTP header**; server nhận request, chạy `SecurityWebFilterChain`, `ReactiveAuthenticationManager` và `MapReactiveUserDetailsService`, rồi mới cho phép truy cập.

### 6.1. Vì sao phải có cả test password đúng và password sai?

| Request | Mong đợi | Nếu có lỗi “allow all” | Nếu có lỗi “deny all” |
| --- | --- | --- | --- |
| Không credentials | `401` | Dễ phát hiện | Vẫn có thể xanh |
| Password sai | `401` | Dễ phát hiện | Vẫn có thể xanh |
| Password đúng | `200` | Vẫn có thể xanh | Dễ phát hiện |
| USER thiếu ADMIN | `403` | Dễ phát hiện | Không đủ bằng chứng |
| ADMIN đủ quyền | `200` | Vẫn có thể xanh | Dễ phát hiện |

Không chỉ kiểm tra `401` rồi kết luận authentication hoạt động: một server luôn từ chối mọi request cũng sẽ trả `401`. Cần ít nhất một ca **authentication thành công** và một ca **authentication thất bại**.

### 6.2. Cần HTTPS ở môi trường thật

`Authorization: Basic ...` chỉ mã hóa username/password bằng Base64, **không mã hóa đường truyền**. Sử dụng HTTP trên localhost trong fixture là tình huống kiểm thử có kiểm soát; môi trường thực phải có TLS và cấu hình phù hợp. Không log Basic/Bearer headers hoặc credentials vào test report.

## 7. Tái hiện lỗi: tại sao `mutateWith(mockUser())` không cứu được real HTTP?

Ví dụ **không phù hợp**:

~~~java
@Test
void incorrectAttemptToUseMockIdentityAcrossSocket() {
    WebTestClient http = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .build();

    http.mutateWith(mockUser("reader").roles("USER"))
        .get()
        .uri("/api/private")
        .exchange()
        .expectStatus().isOk();
}
~~~

Đây là **ví dụ về lỗi thiết kế test**, không phải đoạn nên dùng trong production test suite. Tùy bản Spring Security Test và connector được gắn, việc áp dụng mock-server configurer trên real HTTP client có thể bị từ chối ngay lúc cấu hình, hoặc không tạo ra authentication mà server có thể sử dụng. **Không dựa vào một thông báo lỗi cụ thể duy nhất** làm quy tắc cho mọi version.

Sửa thành:

~~~java
http.get()
    .uri("/api/private")
    .headers(h -> h.setBasicAuth("reader", "reader-password"))
    .exchange()
    .expectStatus().isOk();
~~~

Hoặc nếu ứng dụng dùng Bearer JWT, gửi:

~~~java
http.get()
    .uri("/api/private")
    .headers(h -> h.setBearerAuth(signedJws))
    .exchange()
    .expectStatus().isOk();
~~~

Ở ví dụ JWT, `signedJws` **phải là token có chữ ký hợp lệ đối với decoder thật mà server đã cấu hình**; chuỗi `"fake"` không phải JWT hợp lệ.

### 7.1. `@WithMockUser` trên test method cũng không đi qua socket

~~~java
@Test
@WithMockUser(username = "reader", roles = "USER")
void methodAnnotationDoesNotBecomeHttpCredentials() {
    http.get()
        .uri("/api/private")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

`@WithMockUser` tạo test security context phía JUnit. Khi `WebTestClient.bindToServer()` gửi request qua socket, nó **không tự thêm `Authorization` header hoặc session cookie**. Vì vậy guest request vẫn bị từ chối theo demo HTTP Basic.

Nếu test bất ngờ nhận `200` trong trường hợp này, hãy kiểm tra có default headers, cookie/session được reuse, endpoint `permitAll()` hoặc filter chain bị tắt hay không. Đừng vội suy luận rằng annotation đã “vượt qua mạng”.

### 7.2. `ReactiveSecurityContextHolder` không phải giao thức HTTP

Trong WebFlux, authentication được mang qua Reactor Context bằng `ReactiveSecurityContextHolder`. Context ấy thuộc pipeline của request server đang chạy, **không thể tự sao chép sang HTTP request mới ở process/client khác**.

Muốn server tạo authentication, cần cơ chế có đầu vào từ HTTP: Basic/form credentials, bearer token, session cookie hợp lệ, mTLS hoặc cơ chế khác mà server thực sự hỗ trợ. Bản thân Reactor Context phía test không phải một HTTP header.

## 8. Đừng nhầm `mutate()` cấu hình client với mutator bảo mật mock server

`WebTestClient` có những thao tác thay đổi **HTTP client** vẫn hợp lệ khi gọi server thật, ví dụ tạo base URL, default headers hoặc timeout:

~~~java
import java.time.Duration;

WebTestClient http = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .responseTimeout(Duration.ofSeconds(5))
        .defaultHeader("X-Test-Client", "security-suite")
        .build();
~~~

Request vẫn có thể gắn credentials:

~~~java
http.get()
    .uri("/api/private")
    .headers(headers -> headers.setBasicAuth(
        "reader", "reader-password"))
    .exchange()
    .expectStatus().isOk();
~~~

Điểm mấu chốt không phải “method nào có chữ *mutate* thì chỉ chạy mock”, mà là **configurer này thay đổi cái gì**. Các `SecurityMockServerConfigurers.mockUser`, `mockJwt`, `mockOAuth2Login` và `csrf` phụ thuộc hạ tầng mock WebFlux; chúng không tương đương với hành động gửi HTTP header/body/cookie.

## 9. JWT: chuyển từ `mockJwt()` sang Bearer JWS thực

Một policy test Reactive hợp lệ:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "reports.read")))
      .get()
      .uri("/api/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Test này chỉ có ý nghĩa với endpoint và policy tương ứng trong WebFlux context. `mockJwt()` cung cấp principal giả, có thể bỏ qua `ReactiveJwtDecoder` và token validators.

Khi chuyển qua `bindToServer()`:

~~~java
WebTestClient http = WebTestClient.bindToServer()
    .baseUrl("http://localhost:" + port)
    .build();

http.get()
    .uri("/api/reports")
    .headers(headers -> headers.setBearerAuth(validSignedJws))
    .exchange()
    .expectStatus().isOk();
~~~

Trong đó `validSignedJws` là token được ký bằng **private key của fixture**, decoder của server tin public key tương ứng, và claims đáp ứng chính sách `iss`, `aud`, `exp`, `nbf`, `scope` theo cấu hình. Bài học không cung cấp chuỗi JWT cố định vì một token không được ký bằng khóa mà decoder tin cậy sẽ không đạt test.

### 9.1. Các ca âm bắt buộc

| Bearer token | Điều test cần chạm đến | Kỳ vọng điển hình |
| --- | --- | --- |
| Không token | Authentication entry point | `401` |
| JWS đúng chữ ký, còn hạn, đủ scope | Decoder, validators, authorization | `200` |
| JWS sai chữ ký | Decoder từ chối | `401` |
| JWS hết hạn | Timestamp validator từ chối | `401` |
| JWS sai issuer/audience theo chính sách | Claim validator từ chối | `401` |
| JWS hợp lệ nhưng thiếu scope | Authentication thành công, authorization từ chối | `403` |

Không thay decoder bằng Mockito mock luôn trả `Jwt` khi mục tiêu là “ký sai phải bị từ chối”. Mock decoder có thể làm test `200` nhưng không cho biết hệ thống kiểm tra chữ ký.

### 9.2. Token có `exp` trong quá khứ chưa đủ chứng minh hết hạn bị chặn

~~~java
client.mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("alice")
            .expiresAt(Instant.now().minusSeconds(600))))
      .get()
      .uri("/api/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Nếu policy chỉ yêu cầu authentication, request dùng mock JWT vẫn có thể thành công, vì test đã đặt sẵn JWT authentication mà không gọi validator. Đây **không phải** bằng chứng hệ thống thật chấp nhận JWT hết hạn. Muốn kiểm tra expiration, gửi JWS thật qua `ReactiveJwtDecoder` và assert kết quả.

## 10. CSRF: vì sao `mutateWith(csrf())` không tạo token cho browser thật?

Mock WebFlux:

~~~java
client.mutateWith(mockUser("reader").roles("USER"))
      .mutateWith(csrf())
      .post()
      .uri("/api/notes")
      .exchange()
      .expectStatus().isOk();
~~~

`csrf()` thiết lập CSRF data phục vụ mock server exchange. Nó **không** tự thực hiện quy trình HTTP:

1. Client gọi một endpoint để server phát hành hoặc hiển thị CSRF token.
2. Client nhận token và, nếu cần, session cookie/CSRF cookie tương ứng.
3. Client lưu đúng cookie/token của response.
4. Client gửi lại token trong form field hoặc HTTP header theo repository/request handler thực tế.
5. Spring Security so sánh token của request với trạng thái đã lưu/xác minh.

Với `WebTestClient.bindToServer()`, thực hiện luồng HTTP đó như một client bên ngoài. Không áp dụng `csrf()` rồi coi như browser đã có token thật.

### 10.1. Cookie và header có phụ thuộc cấu hình

- Với session-based CSRF, token có thể gắn với `WebSession`; chỉ copy header token mà không giữ session cookie có thể bị `403`.
- Với `CookieServerCsrfTokenRepository`, ứng dụng có thể dùng cookie và header `X-XSRF-TOKEN` theo cấu hình; tuy nhiên cách encode/mask token còn phụ thuộc `ServerCsrfTokenRequestHandler` của phiên bản.
- Với frontend login, CSRF token có thể đến từ HTML/meta tag hoặc một endpoint `GET /csrf` do **ứng dụng tự cung cấp**.

Không giả định `GET /csrf` được Spring Security tự tạo trong mọi dự án. Nếu ứng dụng không có endpoint/cách phát token cho test client, cần thiết kế một phương pháp quan sát hợp lệ theo hợp đồng ứng dụng, không hardcode `"csrf-test-value"` rồi tự coi nó là hợp lệ.

### 10.2. Phân biệt `401` và `403` trong POST

Giả sử ứng dụng bật CSRF và yêu cầu authentication:

| Request | Kết quả thường gặp | Kết luận |
| --- | --- | --- |
| POST anonymous, thiếu CSRF | `403` | CSRF có thể chặn trước authentication |
| POST Basic đúng, thiếu CSRF | `403` | Có thể do CSRF, chưa chứng minh thiếu role |
| POST Basic đúng, CSRF hợp lệ | `2xx` theo API | Authentication/CSRF đã được đáp ứng |
| POST Basic sai, CSRF hợp lệ | `401` theo Basic entry point | Authentication thất bại |
| POST Basic đúng, CSRF hợp lệ, thiếu quyền | `403` | Authorization từ chối nếu rule đó được thực thi |

Đừng dùng một POST thiếu CSRF trả `403` để kết luận rule `hasRole('ADMIN')` đã hoạt động. Muốn kiểm tra authorization, bảo đảm request vượt qua điều kiện CSRF trước.

## 11. Form login và session: phải truyền cookie qua HTTP

Với ứng dụng dùng form login, authentication qua HTTP thường là một **chuỗi nhiều request**, không phải chỉ một request có user giả.

Một workflow kiểm thử thực tế:

1. `GET /login` để nhận HTML/form và CSRF token nếu có.
2. Lưu session cookie từ response, cùng token CSRF tương ứng.
3. `POST /login` với username/password, token CSRF và cookie cần thiết.
4. Kiểm tra redirect hoặc login success theo cấu hình và lấy session cookie mới nếu server thay đổi session.
5. `GET /api/private` với cookie đã được phát hành → được phép.
6. `GET /api/private` không có cookie → bị từ chối hoặc redirect.
7. `POST /logout` với cookie và CSRF hợp lệ, sau đó kiểm tra cookie cũ không còn cấp quyền.

### 11.1. Không giả định WebTestClient luôn tự giữ cookie như browser

Một client HTTP kiểm thử không nhất thiết có cookie jar theo cách bạn mong đợi. Hãy lưu rõ cookie từ HTTP response rồi gửi lại ở request tiếp theo; cùng lúc kiểm tra session ID có bị rotate khi login hay không.

Ví dụ thao tác gửi cookie trong request:

~~~java
http.get()
    .uri("/api/private")
    .cookie("SESSION", sessionCookieValue)
    .exchange()
    .expectStatus().isOk();
~~~

`sessionCookieValue` phải là giá trị nhận từ response login thật của test flow; `"SESSION"` là tên ví dụ thường gặp với WebFlux session và có thể khác theo cấu hình cookie. Tự tạo một chuỗi cookie không làm server công nhận user.

### 11.2. Có `@WithMockUser` mà không có cookie vẫn là guest đối với server thật

~~~java
@Test
@WithMockUser(username = "reader")
void fakeAuthenticationDoesNotPersistToHttpSession() {
    http.get()
        .uri("/api/private")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Assertion `401` phù hợp ví dụ HTTP Basic ở mục 4. Với form login, một client thiếu session có thể nhận `302`. **Một annotation trên phương thức test không thay thế login workflow.**

## 12. OAuth2/OIDC Login: helper giả không thay authorization code flow

Trong mock WebFlux:

~~~java
client.mutateWith(mockOidcLogin())
      .get()
      .uri("/api/me")
      .exchange()
      .expectStatus().isOk();
~~~

Đây là test xử lý `OidcUser` giả ở ứng dụng. Với `bindToServer()`, muốn xác minh OIDC login thực cần các bước:

1. Bắt đầu login và kiểm tra redirect đến authorization endpoint.
2. Giữ `state` và các thông tin được lưu trong session/cookies.
3. Tương tác authorization server/IdP thử nghiệm, nhận callback `code`.
4. Đổi code tại token endpoint, xác nhận `client_id`, client authentication, `redirect_uri`, `grant_type` và PKCE nếu áp dụng.
5. Xác minh ID token signature, issuer, audience, expiration, nonce và authorities mapping.
6. Dùng session/cookie sau login gọi endpoint được bảo vệ, rồi kiểm tra logout và các ca thất bại.

`mockOAuth2Login()`, `mockOidcLogin()` và `mockOAuth2Client()` cung cấp principal hoặc authorized client đã được giả lập. Chúng **không chứng minh** token endpoint đã nhận request hoặc Identity Provider đã xác minh danh tính.

**Không chuyển** một test `mockOidcLogin()` sang `bindToServer()` bằng cách chỉ đổi base URL rồi đòi `200`: để test login thật phải có IdP test phù hợp, callback/cookies và server config.

## 13. Ứng dụng Servlet có dùng WebTestClient được không?

Có. Khi `WebTestClient.bindToServer()` gửi HTTP qua socket, nó có thể kiểm thử một **Servlet server**. Nhưng mock-server WebFlux mutators không tự biến thành servlet `SecurityContext`.

| Nhu cầu | Servlet | Reactive |
| --- | --- | --- |
| Mock request với principal giả | `MockMvc.perform(...).with(user(...))` | `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` rồi `mutateWith(mockUser(...))` |
| HTTP thật, Basic | `TestRestTemplate` hoặc `WebTestClient.bindToServer()` gửi Basic header | `WebTestClient.bindToServer()` gửi Basic header |
| HTTP thật, Bearer | HTTP `Authorization: Bearer ...` đến Servlet resource server | HTTP `Authorization: Bearer ...` đến Reactive resource server |
| HTTP thật, session | Cookie servlet session qua HTTP | WebFlux session cookie qua HTTP |
| Chỉ cần test method policy | `@WithMockUser` với Spring test context | `@WithMockUser` và Reactive Security Test setup phù hợp |

Trong Servlet mock HTTP, helper:

~~~java
mockMvc.perform(get("/api/private")
        .with(user("reader").roles("USER")))
    .andExpect(status().isOk());
~~~

chỉ thiết lập principal giả cho request `MockMvc`. Để kiểm tra HTTP Basic password:

~~~java
mockMvc.perform(get("/api/private")
        .with(httpBasic("reader", "reader-password")))
    .andExpect(status().isOk());
~~~

`httpBasic(...)` là request post-processor **tạo HTTP Authorization header**, không phải helper gắn authentication đã được xác minh. Đây là lý do `MockMvc` có thể kiểm tra password thật **mà không mở socket**; nguồn authentication và network transport là hai trục độc lập.

## 14. Vì sao `RANDOM_PORT` + `@AutoConfigureWebTestClient` dễ gây nhầm?

Trong Spring Boot, `@SpringBootTest(webEnvironment = MOCK)` và `@SpringBootTest(webEnvironment = RANDOM_PORT)` tạo các môi trường khác nhau:

| Boot environment | Ý nghĩa | Cách dùng được đề xuất trong bài |
| --- | --- | --- |
| `MOCK` | Web server mô phỏng, không mở port | Bind vào WebFlux application context và `apply(springSecurity())` khi dùng mock mutators |
| `RANDOM_PORT` | Chạy embedded server với cổng ngẫu nhiên | Lấy `@LocalServerPort` rồi `bindToServer()`, gửi credentials thật |
| `DEFINED_PORT` | Chạy embedded server với port cấu hình | Chỉ dùng khi có lý do rõ, tránh xung đột CI |
| `NONE` | Không khởi tạo web environment | Không mặc định có HTTP client/server để test |

`@AutoConfigureWebTestClient` có thể cung cấp một client đã cấu hình trong các test context phù hợp, nhưng điều cần kiểm tra là **client ấy gắn vào mock exchange hay server thật**. Khi mục tiêu là chẩn đoán sự khác biệt này, việc tạo rõ client bằng `bindToApplicationContext(...)` hoặc `bindToServer()` làm phạm vi test dễ đọc hơn.

Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có mặt, Spring Boot có thể chọn **Servlet** nếu không chỉ định web application type. Việc có `WebTestClient` trên test classpath không chứng minh server đang chạy WebFlux.

## 15. Bảng tra sự cố: triệu chứng → nguyên nhân → phép kiểm tra

| Triệu chứng | Nguyên nhân khả dĩ | Bước chẩn đoán |
| --- | --- | --- |
| `mockUser()` chạy với mock context nhưng `bindToServer()` nhận `401` | Mock principal không được truyền qua socket | Gửi Basic/Bearer/session cookie thật |
| Gọi `mutateWith(mockJwt())` với real HTTP bị lỗi setup | Configurer chỉ hỗ trợ mock-server exchange | Bỏ mock mutator, gửi JWS qua header |
| `@WithMockUser` không ảnh hưởng request qua `RANDOM_PORT` | Authentication chỉ được tạo ở test execution context | Kiểm tra raw request headers/cookies |
| Basic đúng vẫn nhận `401` | Password sai, encoder/user store khác, filter chain không khớp | Có ca đúng/sai; xác minh cấu hình server |
| Basic sai lại nhận `200` | Endpoint công khai, filter chain bị bỏ qua hoặc test client reuse cookie | Thử guest, xóa cookie/default auth, kiểm tra policy |
| USER đã đăng nhập nhận `403` ở admin | Thiếu quyền `ROLE_ADMIN` | Kiểm tra authority thật; thêm ca ADMIN `200` |
| Anonymous nhận `302` thay vì `401` | Form login entry point | Assert `Location` và login redirect |
| POST có Basic đúng vẫn `403` | Thiếu CSRF | Gửi token CSRF hợp lệ kèm cookie/session |
| Gắn `csrf()` vào real HTTP mà không thấy tác dụng | Mutator dành cho mock exchange | Lấy token từ HTTP flow thực và gửi lại |
| GET private nhận `200` không credentials | Route `permitAll`, stale cookie/default header hoặc filter bị tắt | Tạo client mới, xem security matcher và request |
| JWT giả nhận `200` nhưng Bearer thật nhận `401` | Decoder/issuer/chữ ký/expiry khác mock | Test JWS ký đúng, sai chữ ký, issuer, scope |
| Signed JWT đúng nhưng nhận `403` | Authentication được nhưng scope/role thiếu | Kiểm tra converter và authority mapping |
| Cookie nhận từ login không dùng được | Không giữ session, cookie name/path sai, login chưa hoàn thành | Kiểm tra `Set-Cookie`, request `Cookie`, redirects |
| Test HTTP thật lúc xanh lúc đỏ | Port/fixture/DB state/transaction/cookie dùng chung | Dùng `RANDOM_PORT`, fixture đã commit và isolation |
| `@AutoConfigureWebTestClient` không inject client | Sai web application type/annotation/dependency theo version | Kiểm tra Boot version và chọn setup tường minh |
| MockMvc helper `user()` bị dùng ở WebTestClient | Nhầm Servlet `RequestPostProcessor` với Reactive mutator | Kiểm tra Javadoc/static import đúng stack |
| Test JWT validation xanh vì mock decoder | Decoder thật chưa chạy | Dùng `ReactiveJwtDecoder` implementation thật với test key |

Không chọn cách “sửa” bằng việc thêm `permitAll()`, tắt filters hoặc `csrf().disable()` chỉ để biến `401`/`403` thành `200`. Hành động đó có thể che mất chính lỗ hổng mà test cần phát hiện.

## 16. Chẩn đoán theo thứ tự để không sửa sai tầng

Khi một test thực hiện request HTTP thật không cho status mong đợi, thực hiện:

### Bước 1 — Xác định request có gửi tới server thật không

- Test có `@SpringBootTest(webEnvironment = RANDOM_PORT)` hay một server riêng?
- `baseUrl` có đúng host/port được cấp bởi `@LocalServerPort` không?
- `bindToApplicationContext` hay `bindToServer` đang được dùng?
- Nếu dùng client do auto-configure inject, hãy xác định phạm vi binding trước khi áp dụng mock mutator.

### Bước 2 — Kiểm tra HTTP request có chứng cứ xác thực không

- Header `Authorization` có thực sự được đặt chưa?
- Username/password của fixture có đúng với server-side user store?
- Bearer token có được **ký** và còn hạn hay chỉ là token giả `"fake"`?
- Có cookie session thật từ login trước đó không?
- Khi POST, đã có CSRF token hợp lệ gắn với session/cookie chưa?

Không log nguyên văn password, bearer token hoặc session cookie. Chỉ ghi những tín hiệu an toàn như **có/không có** header, authentication mechanism, issuer đã xác minh và mã status.

### Bước 3 — Phân biệt authentication với authorization

- `401`: với Basic/Bearer, thường chưa xác thực được; xem entry point/decoder/provider.
- `403`: có thể đã xác thực nhưng thiếu quyền, **hoặc** bị CSRF từ chối.
- `302`: có thể redirect đến login hoặc authorization endpoint theo cấu hình.
- `200`: chưa chắc authentication đã chạy nếu route là `permitAll`.

### Bước 4 — Kiểm tra security chain của server

- Server có đăng ký đúng `SecurityWebFilterChain` hoặc `SecurityFilterChain` không?
- Có nhiều chains với `securityMatcher`/`@Order`? Request đang match chain nào?
- Endpoint có thực sự gọi đúng controller/service được bảo vệ không?
- Có proxy, gateway hoặc custom filter thay đổi header?
- Client test có vô tình dùng default headers hoặc cookie cũ không?

### Bước 5 — Kiểm tra data và transaction

Với `RANDOM_PORT`, HTTP server xử lý request ở ngữ cảnh/transaction khác với test method. Nếu fixture user được insert trong `@Transactional` của JUnit nhưng chưa commit, server có thể không nhìn thấy nó. Cần tạo fixture đã commit theo isolation thích hợp, đồng thời dọn state sau test.

### Bước 6 — Thêm cặp đối chứng

Sau khi sửa, chạy:

- Guest → bị từ chối.
- Credentials sai → bị từ chối.
- Credentials đúng, đủ quyền → được phép.
- Credentials đúng, thiếu quyền → bị từ chối.

Nếu chỉ có một nhánh, test dễ xanh khi server luôn cho phép hoặc luôn từ chối.

## 17. Quan sát response đúng cách, không coi log là assertion

Ví dụ real HTTP test với Basic:

~~~java
http.get()
    .uri("/api/private")
    .headers(h -> h.setBasicAuth("reader", "wrong-password"))
    .exchange()
    .expectStatus().isUnauthorized()
    .expectHeader().exists("WWW-Authenticate");
~~~

`WWW-Authenticate` là header thường có trong HTTP Basic challenge; có thể assert thêm nếu demo security chain thực sự bật Basic entry point. Với form login redirect, kiểm tra `Location` thay vì ép có Basic challenge.

Đối với request thành công:

~~~java
http.get()
    .uri("/api/private")
    .headers(h -> h.setBasicAuth("reader", "reader-password"))
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.user").isEqualTo("reader");
~~~

Body assertion giúp xác minh request không chỉ được `200` từ một endpoint công khai hoặc response mặc định. Nhưng không nên chỉ kiểm tra chuỗi username mà client đã tự xây nếu server chưa thực hiện request; assertion phải đến từ **response của system under test**.

## 18. Bộ kiểm thử tối thiểu sau khi sửa lỗi

| Ca | Binding | Identity input | Mong đợi | Điều chứng minh |
| --- | --- | --- | --- | --- |
| A | Mock WebFlux | `mockUser("reader")` | `200` private | Rule cho mock principal |
| B | Mock WebFlux | `mockUser("reader")` | `403` admin | Rule thiếu quyền |
| C | HTTP thật | Không credentials | `401` private | Entry point bảo vệ route |
| D | HTTP thật | Basic sai password | `401` private | Authentication từ chối |
| E | HTTP thật | Basic đúng password | `200` private | Authentication chấp nhận |
| F | HTTP thật | Basic USER đúng | `403` admin | Authorization sau login |
| G | HTTP thật | Basic ADMIN đúng | `200` admin | Đủ quyền |
| H | Mock WebFlux | `mockJwt()` có scope | Theo policy | JWT principal giả được xử lý |
| I | HTTP thật | Bearer JWS ký sai | `401` | Decoder từ chối token |
| J | HTTP thật | Bearer JWS đúng, thiếu scope | `403` | Authorization theo scope |
| K | Mock WebFlux | Mock USER + `csrf()` | `2xx` POST | CSRF trên mock exchange |
| L | HTTP thật | Cookie/CSRF nhận từ server | `2xx` POST | HTTP CSRF/session flow |

Các ca JWT và CSRF ở cuối **chỉ áp dụng khi ứng dụng thật sự cấu hình các cơ chế đó**. Không nên cố chạy tất cả bằng một `SecurityWebFilterChain` HTTP Basic đơn giản nếu chưa thêm resource-server/CSRF/session flow phù hợp.

## 19. Bài tập thực hành

### Bài 1 — Từ test mock sang real HTTP

Cho test `client.mutateWith(mockUser("reader"))` trả `200` tại `/api/private`. Hãy viết test với `@SpringBootTest(RANDOM_PORT)` và `WebTestClient.bindToServer()`, gửi `Authorization: Basic` đúng password. Thêm ca password sai `401` và không có credentials `401`. Giải thích vì sao `mockUser()` không thay thế hai ca ấy.

### Bài 2 — Phân biệt lỗi API và lỗi test setup

Một test gọi `http.mutateWith(mockJwt())` khi `http` được tạo bằng `bindToServer()`. Xác định đối tượng mà mutator định thay đổi và ranh giới không thể truyền `SecurityContext`. Sửa bằng cách tạo JWS ký thật với test key, cấu hình `ReactiveJwtDecoder` và gửi Bearer header.

### Bài 3 — Vì sao POST vẫn `403`?

Server chấp nhận Basic đúng nhưng `POST /api/notes` bị `403`. Viết hai ca: POST Basic đúng thiếu CSRF bị từ chối, POST Basic đúng với CSRF token và session phù hợp được phép. Nêu lý do không kết luận user thiếu role chỉ từ `403` đầu tiên.

### Bài 4 — Cookie không tự mang theo

Thiết kế một form-login HTTP test ghi nhận `Set-Cookie` sau login, dùng cookie gọi `/api/private`, rồi gọi lại không cookie và sau logout. Giải thích tại sao test `@WithMockUser` không chứng minh session lifecycle.

### Bài 5 — Servlet cũng dùng được WebTestClient

Một dự án Spring MVC dùng `MockMvc.with(user())` để test role. Viết thêm test `WebTestClient.bindToServer()` gửi Basic credentials tới Servlet `RANDOM_PORT`. So sánh khi nào servlet filter chain chạy với principal giả và khi nào authentication provider xử lý credentials thực.

### Bài 6 — Xác định lỗi từ status

Cho các kết quả: GET private `401`, GET admin `403`, GET private `302` và POST `403`. Hãy mô tả ít nhất hai giả thuyết phù hợp cho từng status, cùng phép thử đối chứng giúp xác định lỗi đến từ Basic authentication, form login, role hay CSRF.

### Bài 7 — Không phụ thuộc cổng cố định

Viết `@BeforeEach` xây dựng WebTestClient từ `@LocalServerPort`; chứng minh test không cần hardcode `8080`. Thử chạy test song song với data độc lập và mô tả cách tránh dùng chung session, fixtures và token.

## 20. Checklist chẩn đoán cuối cùng

- [ ] Đã xác định rõ WebTestClient gắn vào mock context hay real HTTP server.
- [ ] Không dùng `mockUser()/mockJwt()/mockOidcLogin()/csrf()` làm phương tiện truyền credentials qua socket.
- [ ] `@WithMockUser` không được coi là một form login/Basic/Bearer request thực.
- [ ] HTTP Basic credentials đã nằm trong `Authorization` header và được server xử lý.
- [ ] Với JWT, token đã được ký thật và decoder/validator thực được chạy.
- [ ] Với form login, cookie/session được nhận từ response và gửi lại chính xác.
- [ ] Với CSRF, token được lấy từ HTTP flow phù hợp; không chỉ dùng mock `csrf()`.
- [ ] Đã xác nhận server security chain và entry point thực cho route đang kiểm tra.
- [ ] Đã phân biệt `401`, `403` và `302` theo nguyên nhân cụ thể.
- [ ] Có ca đúng credentials thành công và ca sai credentials thất bại.
- [ ] Có ca đủ quyền thành công và ca thiếu quyền thất bại.
- [ ] Test data đã tồn tại trước request và commit khi cần thiết.
- [ ] Test cô lập cookies, session, port, user data, JWT fixtures và clock.
- [ ] Không tắt security filters, CSRF hoặc mở `permitAll` chỉ để biến test thành công.
- [ ] Báo cáo test nêu rõ ranh giới: mock principal policy, authentication integration hay HTTP transport.

## 21. Kết luận

Khi `WebTestClient` dùng `bindToApplicationContext(...)` với `springSecurity()`, các mutator như `mockUser()`, `mockJwt()` và `csrf()` rất hữu ích để kiểm tra **security policy trong mock WebFlux exchange**. Khi `WebTestClient` dùng `bindToServer()`, nó gửi một **HTTP request thật**: danh tính phải được server tạo ra từ credentials, token hoặc session mà request thực sự mang theo.

**Không phải lỗi cứ nhận `401` là Spring Security đánh rơi principal.** Trước hết hãy xem principal ấy từng được truyền qua HTTP hay chưa. Sửa test bằng cách chọn đúng mục tiêu: mock mutators để kiểm tra policy; HTTP Basic, Bearer JWS, form login/cookie/CSRF thật để kiểm tra authentication và HTTP boundary.

Một bộ test đáng tin có cả nhánh **được phép** và **bị từ chối**, chỉ rõ thành phần nào đã thực thi và không vượt quá kết luận mà kết quả `200`/`401`/`403` thực sự hỗ trợ.

## 22. Tài liệu tham khảo

- [Spring Security — Reactive Test Web Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `bindToApplicationContext` và `springSecurity()`.
- [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()`, mock authentication.
- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()`.
- [Spring Security — Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `csrf()` cho mock WebFlux.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): mock binding và `bindToServer()`.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `MOCK`, `RANDOM_PORT` và test clients.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` và token validation.
- [Spring Security — Servlet MockMvc Test Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): test helper Servlet và cấu hình mock filters.
