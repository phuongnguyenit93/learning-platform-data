# WebTestClient và tích hợp Spring Security trong ứng dụng reactive

## 1. Kiểm thử điều gì trong ứng dụng Spring WebFlux?

Với ứng dụng **Spring WebFlux**, việc một controller trả về đúng dữ liệu chưa đủ để khẳng định API an toàn. Cần chứng minh rằng request đi qua **chuỗi lọc bảo mật reactive**, được xác thực và phân quyền đúng, rồi mới đến handler. Một endpoint có thể trả kết quả đúng trong test controller đơn lẻ nhưng lại bị chặn hoặc bị mở sai quyền khi chạy cùng cấu hình Spring Security thật.

`WebTestClient` là công cụ của Spring Test dành cho kiểm thử HTTP theo phong cách fluent, dùng được với WebFlux **không cần khởi động HTTP server** hoặc với server thực. Khi kết hợp `spring-security-test`, nó còn cho phép tạo danh tính kiểm thử, gắn quyền, cung cấp CSRF token và quan sát phản hồi từ các `WebFilter` của Spring Security.

Một bộ test tối thiểu cần trả lời:

1. Endpoint công khai có truy cập được khi **anonymous** không?
2. Endpoint yêu cầu đăng nhập có trả **401** hoặc chuyển hướng xác thực đúng như cấu hình không?
3. Người dùng đã xác thực nhưng thiếu role/scope có nhận **403** không?
4. Người dùng đủ quyền có nhận **200** cùng dữ liệu đúng không?
5. Thao tác ghi có bị **CSRF protection** chặn khi thiếu token và được phép khi đủ token/quyền không?
6. Danh tính trong controller/service có lấy từ **reactive SecurityContext** của request đang được kiểm thử hay không?
7. Kiểm thử có thực sự chạy với **SecurityWebFilterChain của ứng dụng**, thay vì một cấu hình bảo mật mặc định hoặc một handler không đi qua filter?

Bài này dùng **Java 17+, Spring Boot 3.x và Spring Security 6.x** làm ví dụ. Đối với Spring Boot 4.x / Spring Security 7.x, tên package của một số annotation cấu hình test đã thay đổi; cần đối chiếu đúng tài liệu phiên bản dự án. Các khái niệm về `WebTestClient`, `SecurityWebFilterChain` và test mutator vẫn giữ vai trò tương ứng.

## 2. Kiến trúc: từ WebTestClient tới SecurityWebFilterChain

Luồng xử lý của một request WebFlux có bảo mật:

```text
JUnit test
    |
    v
WebTestClient
    |
    v
WebFlux HttpHandler / WebHandler
    |
    v
Spring Security WebFilterChainProxy
    |
    +--> CSRF / authentication / authorization WebFilter
    |
    v
DispatcherHandler
    |
    v
@RestController hoặc RouterFunction
    |
    v
Mono / Flux / ResponseEntity
    |
    v
HTTP status + headers + body -> expectStatus / expectHeader / expectBody
```

**Điểm cần nhớ:** WebFlux dùng `WebFilter` và `SecurityWebFilterChain`. Ứng dụng Servlet thường dùng `Filter`, `SecurityFilterChain`, `HttpSecurity` và `MockMvc`. Hai nhóm này có tên tương tự nhưng **không thể thay thế kiểu trực tiếp cho nhau**.

Trong reactive stack:

- `ServerHttpSecurity` khai báo chính sách bảo mật cho HTTP request.
- `SecurityWebFilterChain` mô tả chuỗi WebFilter được áp dụng cho request.
- `authorizeExchange(...)` thiết lập phân quyền theo đường dẫn và method.
- `ReactiveAuthenticationManager` và các thành phần liên quan xử lý xác thực theo kiểu reactive.
- Thông tin security được truyền qua **Reactor Context**; không nên dựa vào giả định ThreadLocal luôn giữ đúng principal khi luồng reactive chuyển thread.
- `WebTestClient` có thể gắn vào `ApplicationContext` để thực thi các WebFilter thật của ứng dụng khi test, hoặc gắn với server chạy trên cổng mạng.

### Ba cách dựng WebTestClient

| Cách dựng | Có mở HTTP port? | Phù hợp khi | Giới hạn đáng lưu ý |
| --- | --- | --- | --- |
| `bindToApplicationContext(context)` | Không | Kiểm thử kết hợp router/controller + toàn bộ WebFilter cấu hình trong context | Không kiểm chứng TLS, proxy, cổng thật và các vấn đề ngoài HTTP handler |
| `bindToController(controller)` | Không | Kiểm thử nhanh controller đơn lẻ | Không tự động chứng minh `SecurityWebFilterChain` production đang hoạt động; phải cấu hình test security riêng |
| `bindToServer().baseUrl(...)` | Có server thực | Kiểm thử đầu cuối qua HTTP, session/cookie, network behavior | Phải tự gửi credentials/token thật của môi trường test; `mockUser()` không biến server từ xa thành người dùng giả |

Đối với mục tiêu **kiểm thử tích hợp Spring Security trong reactive application**, cách đầu tiên là trọng tâm. Chính cấu hình `springSecurity()` của `spring-security-test` giúp thêm hỗ trợ test security cho client gắn với application context.

## 3. Phụ thuộc dự án

Tạo dự án Spring Boot 3.x bằng Spring Initializr, chọn **Spring Reactive Web** và **Spring Security**. Với Gradle Groovy DSL, các dependency cốt lõi là:

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

Đây là đoạn **dependencies/test task** cần đặt vào `build.gradle` của dự án Spring Boot đã có plugin/version từ Initializr, không phải toàn bộ nội dung build script. Lý do cần từng dependency:

- `spring-boot-starter-webflux` cung cấp Spring WebFlux, Reactor, bộ codec và WebTestClient khi kết hợp Spring Test.
- `spring-boot-starter-security` cung cấp reactive security và DSL `ServerHttpSecurity`.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Boot Test, Spring Test và các công cụ xác minh.
- `spring-security-test` cung cấp `springSecurity()`, `mockUser()`, `csrf()`, các annotation/mock authentication chuyên dụng.
- `reactor-test` cần cho những bài test thao tác trực tiếp với `Mono`/`Flux` bằng `StepVerifier`; trong ví dụ HTTP bên dưới, phần này có thể được dùng cho bài thực hành mở rộng.

**Không thêm `spring-boot-starter-web` chỉ để chạy ví dụ.** Nếu cả Web MVC và WebFlux cùng có trên classpath, Spring Boot 3.x thường ưu tiên chế độ Servlet/MVC. Với dự án hỗn hợp cần kiểm thử reactive, xác định rõ `spring.main.web-application-type=reactive` và kiểm tra bean `SecurityWebFilterChain` thực sự được dùng.

## 4. Ứng dụng reactive mẫu có phân quyền và CSRF

Dự án ví dụ đặt Java source tại:

```text
src/main/java/demo/reactivetest/ReactiveSecurityLabApplication.java
```

Tạo **đúng một tệp** chứa chương trình đầy đủ sau:

```java
package demo.reactivetest;

import java.security.Principal;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityLabApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            // API HTTP Basic: không dùng chuyển hướng HTML form login.
            .formLogin(form -> form.disable())
            // Không tắt CSRF: POST phải có token CSRF hợp lệ.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor123"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    public record NoteRequest(String text) {}

    @RestController
    public static class ApiController {

        @GetMapping("/api/public")
        public Mono<String> publicEndpoint() {
            return Mono.just("public-ok");
        }

        @GetMapping("/api/admin")
        public Mono<String> adminEndpoint() {
            return Mono.just("admin-ok");
        }

        // WebFlux lấy Principal của request đã xác thực.
        @GetMapping("/api/me")
        public Mono<String> currentUser(Mono<Principal> principal) {
            return principal.map(Principal::getName);
        }

        @PostMapping("/api/notes")
        public Mono<Map<String, String>> createNote(
                @RequestBody Mono<NoteRequest> body) {

            return body.map(note ->
                Map.of("saved", note.text())
            );
        }
    }
}
```

### Vì sao dùng đúng các thành phần này?

**`@EnableWebFluxSecurity`** kích hoạt WebFlux security; `SecurityWebFilterChain` khai báo quy tắc cho các request reactive. `ServerHttpSecurity` khác với `HttpSecurity` trong Servlet. Mã này **không** dùng `SecurityFilterChain` hoặc `@EnableWebSecurity` của Spring MVC.

**`authorizeExchange(...)`** xét đường dẫn theo thứ tự:

1. `/api/public` mở cho anonymous.
2. `POST /api/notes` chỉ cho role `EDITOR`.
3. `/api/admin` chỉ cho role `ADMIN`.
4. Mọi request còn lại cần xác thực.

`hasRole("ADMIN")` kiểm tra authority mang tiền tố `ROLE_ADMIN` theo quy ước mặc định. Người có `ROLE_USER` được xác thực nhưng vẫn bị 403 khi vào `/api/admin`.

**`httpBasic(...)`** giúp kiểm thử cả trạng thái thiếu credentials hoặc credentials sai và trạng thái credentials hợp lệ. `formLogin(form -> form.disable())` tránh đường redirect tới trang login HTML trong API minh họa. Vì vậy GET `/api/admin` khi anonymous sẽ nhận **401** thay vì 302 theo cấu hình ví dụ.

**Không vô hiệu hóa CSRF.** Cơ chế CSRF mặc định của Spring Security WebFlux bảo vệ các HTTP method thay đổi trạng thái. Do đó một request POST có role `EDITOR` nhưng thiếu CSRF token có thể bị **403 trước khi controller chạy**. Trong bài kiểm thử, `csrf()` là công cụ tạo token **giả lập hợp lệ cho test**, không phải cách tắt bảo vệ trong sản phẩm.

**`MapReactiveUserDetailsService`** là dịch vụ tài khoản dạng reactive, thích hợp ví dụ thử nghiệm. Mật khẩu được mã hóa bằng `DelegatingPasswordEncoder`; dữ liệu tài khoản ở đây chỉ là fixture cục bộ. Hệ thống thực tế cần provider/user store phù hợp, HTTPS và quản lý secrets.

**`Mono<Principal>`** của endpoint `/api/me` cho phép lấy danh tính từ request đang xử lý theo cơ chế reactive. Nó không lấy tên người dùng từ query parameter. Việc sử dụng tham số này cho phép kiểm tra trực tiếp rằng authentication trong bài test thực sự được truyền qua pipeline reactive đến handler.

**`Mono` trong controller không có `block()`**. Với WebFlux, tránh chặn thread I/O trong request handler; khi dùng kho dữ liệu thật, chọn thư viện reactive hoặc tách các thao tác blocking một cách có chủ đích.

## 5. Bài test tích hợp dùng WebTestClient và spring-security-test

Đặt tệp test tại:

```text
src/test/java/demo/reactivetest/ReactiveSecurityLabApplicationTests.java
```

Đây là **tệp Java test hoàn chỉnh** trong dự án vừa tạo:

```java
package demo.reactivetest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveSecurityLabApplicationTests {

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
    void publicEndpointAllowsAnonymous() {
        client.get()
            .uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void adminEndpointRequiresAuthentication() {
        client.get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void userWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanAccessAdminEndpoint() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void principalReachesReactiveController() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void editorWithoutCsrfTokenIsForbidden() {
        client.mutateWith(mockUser("editor").roles("EDITOR"))
            .post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void editorWithCsrfTokenCanCreateNote() {
        client.mutateWith(mockUser("editor").roles("EDITOR"))
            .mutateWith(csrf())
            .post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.saved").isEqualTo("hello");
    }

    @Test
    void userWithCsrfButWithoutEditorRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void realBasicCredentialsAreCheckedByReactiveAuthentication() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("alice", "alice123")
            )
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void wrongBasicPasswordIsUnauthorized() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("alice", "wrong-password")
            )
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Cú pháp import static dài:** Java cho phép đặt xuống dòng sau tên package chứa class, trước dấu chấm, nhưng để tránh người đọc hiểu nhầm trong IDE hoặc copy từng dòng riêng, ba import trên có thể viết thành **một dòng cho mỗi static import**:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Khi tạo tệp thực tế, **dùng ba import một dòng này thay cho ba import đã ngắt dòng ở trên**, không lặp import. Các tên static nằm trong `SecurityMockServerConfigurers` thuộc dependency `spring-security-test`.

### Điều xảy ra ở @BeforeEach

Lệnh:

```java
client = WebTestClient.bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
```

tạo client gọi HTTP handler **trong ApplicationContext của Spring Boot**, không mở server ở cổng 8080. Bước `.apply(springSecurity())` cung cấp tích hợp test với Spring Security, cho phép các mock mutator như `mockUser()` và `csrf()` đi qua pipeline phù hợp. Cấu hình `SecurityWebFilterChain` được nạp từ ứng dụng, nên test không chỉ kiểm tra phương thức controller tách rời.

Với `@SpringBootTest`, context chứa bean ứng dụng và cấu hình bảo mật thật ở phạm vi test. `@SpringBootTest` mặc định dùng mock web environment; khác với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, vốn khởi động HTTP server trên cổng thực. Đối với test ở đây, không cần `@AutoConfigureWebTestClient` bởi `WebTestClient` được khởi tạo thủ công trong `setUp()`.

### Ý nghĩa của các test

| Test | Request | Kết quả kỳ vọng |
| --- | --- | --- |
| `publicEndpointAllowsAnonymous` | GET `/api/public`, không xác thực | 200 + `public-ok` |
| `adminEndpointRequiresAuthentication` | GET `/api/admin`, anonymous | 401 + Basic challenge |
| `userWithoutAdminRoleIsForbidden` | GET `/api/admin`, mock USER | 403 |
| `adminRoleCanAccessAdminEndpoint` | GET `/api/admin`, mock ADMIN | 200 + `admin-ok` |
| `principalReachesReactiveController` | GET `/api/me`, mock Alice | 200 + `alice` |
| `editorWithoutCsrfTokenIsForbidden` | POST `/api/notes`, mock EDITOR, không CSRF | 403 |
| `editorWithCsrfTokenCanCreateNote` | POST, mock EDITOR, CSRF hợp lệ | 200 + `{"saved":"hello"}` |
| `userWithCsrfButWithoutEditorRoleIsForbidden` | POST, mock USER, CSRF hợp lệ | 403 |
| `realBasicCredentialsAreCheckedByReactiveAuthentication` | GET `/api/me`, Basic Alice đúng | 200 + `alice` |
| `wrongBasicPasswordIsUnauthorized` | GET `/api/me`, Basic Alice sai | 401 |

Đoạn test phân biệt rõ **hai tầng được kiểm chứng**: `mockUser()` bỏ qua bước xác thực bằng mật khẩu để tập trung vào phân quyền; phép thử Basic credentials thực tế đi qua cơ chế xác thực của ứng dụng. Nếu chỉ có mockUser tests, ta **chưa chứng minh** password encoder, ReactiveUserDetailsService hoặc thông tin Basic được xử lý đúng.

### Chạy test

Trong thư mục dự án Gradle có Wrapper:

```bash
./gradlew test
# Windows PowerShell:
# .\gradlew.bat test
```

Nếu chỉ chạy lớp test (dùng tên lớp đúng như ở trên):

```bash
./gradlew test --tests "demo.reactivetest.ReactiveSecurityLabApplicationTests"
```

**Kết quả kỳ vọng:** 10 phương thức test PASS, Gradle task `test` thành công. Đây là **kỳ vọng từ cấu hình và assertions**, không phải stdout đã được đo từ một lần chạy trong tài liệu này. Khi test fail, hãy xem status thực tế, thông điệp assertion và cấu hình `SecurityWebFilterChain` đang được nạp, rồi đối chiếu phiên bản Spring Boot/Security cụ thể.

## 6. Các test mutator thực hiện điều gì?

### 6.1. mockUser(): tạo danh tính trong request kiểm thử

Ví dụ:

```java
client.mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("alice");
```

`mockUser("alice").roles("USER")` cung cấp một `Authentication` giả lập có tên Alice và authority `ROLE_USER` cho **request của client test**. Nó thích hợp để xác minh `authorizeExchange(...)`, `@PreAuthorize` khi có method security và việc truy cập principal trong handler.

Không nên suy rằng `mockUser()`:

- Đã thực sự kiểm tra password Alice trong kho người dùng.
- Đã xác minh chữ ký hoặc thời hạn của một JWT.
- Đã chạy quy trình đăng nhập form, callback OIDC hoặc cấp refresh token.
- Đã kiểm tra tenant, quyền sở hữu tài nguyên hay nghiệp vụ ngoài những rule mà test thực sự gọi.
- Có thể thay đổi danh tính của một server đã chạy ở nơi khác qua kết nối HTTP thật.

Đây là công cụ **tập trung vào authorization behavior**. Muốn kiểm tra authentication provider, cần thử credentials thật trong môi trường test hoặc kiểm thử riêng provider.

**Lưu ý về role và authority:** `roles("ADMIN")` tạo authority `ROLE_ADMIN`. Nếu rule dùng `hasAuthority("SCOPE_notes.read")`, hãy cung cấp authority phù hợp thay vì giả định role ADMIN tương đương scope đó.

### 6.2. csrf(): tạo CSRF token hợp lệ cho kiểm thử

Ví dụ:

```java
client.mutateWith(mockUser("editor").roles("EDITOR"))
    .mutateWith(csrf())
    .post()
    .uri("/api/notes")
    .bodyValue("{\"text\":\"hello\"}")
    .header("Content-Type", "application/json")
    .exchange()
    .expectStatus().isOk();
```

Spring Security WebFlux bảo vệ CSRF mặc định đối với nhiều thao tác thay đổi trạng thái. Test `editorWithoutCsrfTokenIsForbidden` cho thấy **role đúng vẫn chưa đủ**. Test có `csrf()` xác minh chính sách phân quyền **sau khi** điều kiện CSRF đã được đáp ứng.

Đừng tắt CSRF toàn bộ bằng `.csrf(csrf -> csrf.disable())` chỉ vì test POST nhận 403. Ứng dụng dùng cookie/session, form login hoặc HTTP Basic do browser tự đính kèm credentials có thể chịu rủi ro CSRF. Với Bearer token chỉ được gửi chủ động trong header ở API stateless, quyết định cấu hình CSRF cần dựa trên mô hình xác thực và nguy cơ thực tế.

### 6.3. @WithMockUser: dùng annotation thay cho mutateWith

`spring-security-test` còn hỗ trợ `@WithMockUser`. Ví dụ **minh họa một phương thức trong lớp test đã cấu hình `springSecurity()`**, không phải class độc lập:

```java
@Test
@WithMockUser(username = "admin", roles = "ADMIN")
void annotationProvidesMockAdmin() {
    client.get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
}
```

Import thêm `org.springframework.security.test.context.support.WithMockUser` khi dùng snippet này. Với request riêng cần nhiều principal khác nhau trong một test hoặc muốn thể hiện rõ trạng thái bảo mật ngay tại chỗ gọi, `mutateWith(mockUser(...))` thường dễ đọc hơn. Luôn kiểm tra annotation/mutator có thực sự đi qua security test support của client, thay vì chỉ đặt annotation lên test mà không ghép Spring Security vào HTTP handler.

### 6.4. Không để trạng thái giả lọt qua test khác

Trong lớp ví dụ, mỗi `@BeforeEach` dựng lại client gốc, và mỗi lần `mutateWith(mockUser(...))` tạo bản client cấu hình cho tình huống đó. Điều này giúp hạn chế việc một test dùng principal của test khác. Tránh đặt `mockUser("admin")` mặc định cho mọi bài test rồi tuyên bố rằng endpoint chắc chắn đã bảo vệ anonymous, vì lúc đó bạn chưa thực sự thử người chưa xác thực.

## 7. Kiểm thử JWT/Bearer trong WebFlux: sử dụng đúng tầng

Nếu ứng dụng là **OAuth2 Resource Server** thay vì HTTP Basic, có thể dùng `mockJwt()` của Spring Security Test. Tuy nhiên, phải cài Spring Security OAuth2 Resource Server tương ứng và cấu hình `oauth2ResourceServer(...jwt...)` trong `SecurityWebFilterChain`; **đừng chép test JWT này vào chương trình HTTP Basic ở mục 4 rồi kỳ vọng nó tự kiểm tra scope**.

Ví dụ minh họa dành cho resource server đã cấu hình:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Trong test của ứng dụng reactive resource server:
client.mutateWith(
        mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")
        )
    )
    .get()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Nếu endpoint `/api/reports` dùng `hasAuthority("SCOPE_reports.read")` thì test trên kiểm tra đường phân quyền theo authority giả lập. `mockJwt()` **không chứng minh** JWT do IdP phát hành có chữ ký đúng, issuer/audience hợp lệ hoặc thực sự đi qua `ReactiveJwtDecoder`. Cần thêm test riêng cho token validation hoặc chạy kiểm thử tích hợp với cấu hình resource server và token test có thể xác minh.

Tương tự, `mockOpaqueToken()` hỗ trợ test principal từ opaque token ở môi trường giả lập; không tự động chứng minh introspection endpoint hoạt động. Đối với cookie/session OAuth login, phải test đúng flow đăng nhập, lưu phiên và cách client gửi cookie khi cần.

## 8. Phân biệt mock HTTP handler và server thực

`WebTestClient.bindToApplicationContext(...)` là lựa chọn lý tưởng cho test bảo mật ứng dụng reactive vì nhanh và nạp security filter trong cùng context. Tuy nhiên, test in-memory không kiểm tra được tất cả hành vi production:

- Reverse proxy có truyền/xóa header danh tính đúng không?
- Cookie `Secure`/`SameSite`/domain/path có hoạt động đúng qua trình duyệt không?
- TLS, CORS với origin thực và đường redirect ngoài server có đúng không?
- HTTP server thật có giới hạn header/body, compression và timeout phù hợp không?
- Session, load balancer, nhiều instance và mạng giữa dịch vụ có hoạt động theo cấu hình không?

Để kiểm chứng network thật, dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` cùng `@AutoConfigureWebTestClient` phù hợp phiên bản Boot 3.x, hoặc tạo client `WebTestClient.bindToServer().baseUrl("http://localhost:<port>")`. Bài test phải gửi Basic credentials hoặc Bearer token **thực sự được môi trường test chấp nhận**. Không nên dùng `mockUser()` như cơ chế giả mạo danh tính của một server độc lập.

Ví dụ khung kiểm thử server thật (minh họa trong ứng dụng Boot 3.x có server test khởi động):

```java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveHttpSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousAdminIsUnauthorized() {
        client.get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Trong Boot 3.x, import `@AutoConfigureWebTestClient` từ `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`. Với Boot 4.x, tên package/nhóm starter test khác, vì vậy phải theo đúng phiên bản. Đoạn trên chỉ là **khung minh họa** của một lớp test riêng trong dự án có application class và security config như mục 4; không phải tệp độc lập có đầy đủ imports.

Trong test server thật, các lỗi còn liên quan tới trạng thái dữ liệu và thời điểm giao dịch commit. Nếu test dùng cơ sở dữ liệu, cần tạo fixture độc lập và dọn dẹp phù hợp; không mặc định rằng rollback của transaction phía test sẽ hoàn tác transaction chạy ở server trên thread/connection khác.

## 9. Test slice @WebFluxTest và lý do dễ bỏ sót security config

`@WebFluxTest(SomeController.class)` nạp một phần nhỏ các bean web để test controller nhanh hơn `@SpringBootTest`. Tuy nhiên, **các bean application service, repository và cấu hình `SecurityWebFilterChain` tùy chỉnh có thể không được nạp tự động**. Vì vậy:

1. Nếu muốn test **controller behavior** độc lập, `@WebFluxTest` có thể phù hợp; dùng mock collaborator và nạp cấu hình cần thiết.
2. Nếu muốn khẳng định **chuỗi phân quyền của ứng dụng**, dùng `@SpringBootTest` (như ví dụ) hoặc `@Import(SecurityConfig.class)` đúng cấu hình vào slice test.
3. Đừng thấy test `@WebFluxTest` trả 401/403 rồi kết luận matcher tùy chỉnh của production đã được kiểm thử; có thể đó là security mặc định khác.
4. Nếu dự án dùng `RouterFunction` thay cho `@RestController`, slice test cần import các route/bean phù hợp hoặc dùng full context.

Sự khác biệt giữa **mock ứng dụng** và **mock danh tính** cũng cần rõ:

- `bindToApplicationContext` giữ lại ứng dụng thật trong test context nhưng không mở network server.
- `mockUser` thay thế bước cung cấp identity, không thay toàn bộ ứng dụng.
- `@WebFluxTest` thu hẹp các bean trong application context.
- `bindToController` chỉ gắn một hay vài controller được cung cấp, dễ thiếu WebFilter production.

Khi một test luôn 200 dù endpoint đáng lẽ yêu cầu role, hãy xác minh security chain có được nạp, `springSecurity()` có được apply và rule có khớp URL không.

## 10. Method security và truyền SecurityContext trong chuỗi reactive

Trong một hệ thống lớn, phân quyền không chỉ nằm ở `authorizeExchange`. Dịch vụ có thể dùng `@EnableReactiveMethodSecurity` và `@PreAuthorize` để kiểm tra quyền ngay tại method nghiệp vụ, ví dụ role/scope hoặc điều kiện trên tài nguyên. Khi đó cần kiểm thử **lời gọi đi qua Spring proxy** và Reactor Context, không chỉ gọi thẳng một method mới bằng `new Service()`.

Ví dụ **minh họa trên một service reactive có bật reactive method security**:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> privilegedAction() {
    return Mono.just("approved");
}
```

Đoạn trên là method minh họa, cần nằm trong Spring-managed service và dùng annotation/import tương ứng. Nếu gọi qua controller dùng service, WebTestClient có thể xác minh người dùng thường nhận 403 còn admin nhận 200. Nếu tự gọi method trên đối tượng không phải Spring proxy, annotation không được thực thi.

Trong Reactor, các thao tác như `publishOn(...)`, `flatMap(...)` và xử lý bất đồng bộ có thể làm việc trên thread khác; đừng dựa vào `SecurityContextHolder.getContext()` của mô hình Servlet để suy rằng principal sẽ tự đi theo ThreadLocal. Reactive security dùng `ReactiveSecurityContextHolder` và Reactor Context. Để lấy danh tính trong reactive service, có thể dùng API dành cho reactive context, ví dụ:

```java
Mono<String> currentAuthenticatedName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
```

Đây là **method minh họa**; import `org.springframework.security.core.context.ReactiveSecurityContextHolder` và `reactor.core.publisher.Mono`. Khi chưa có reactive security context, publisher có thể rỗng; đừng coi chuỗi rỗng là danh tính đã xác thực. Mô hình kiểm thử bằng `mockUser()` cần chứng minh danh tính đi đúng context đến method được test.

## 11. Kiểm thử Flux, SSE và endpoint phát dữ liệu liên tục

`WebTestClient` có thể xác minh cả response reactive trả một giá trị (`Mono`) và response nhiều phần tử (`Flux`). Với `Mono` trong ví dụ, `expectBody(String.class)` hoặc `expectBody().jsonPath(...)` là đủ. Với endpoint streaming hoặc Server-Sent Events, response không nhất thiết kết thúc nhanh, nên việc gọi `expectBody()` để đợi toàn bộ stream có thể bị treo đến timeout.

Đối với stream có số phần tử hữu hạn, có thể dùng `returnResult(...)` để lấy body như `Flux` rồi dùng `StepVerifier` kiểm tra số item và completion. Đối với stream không kết thúc, kiểm tra số event đầu tiên, sau đó **hủy subscription** thay vì đợi completion. Ví dụ khái niệm với một endpoint stream đã có:

```java
FluxExchangeResult<String> result = client
    .mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/events")
    .exchange()
    .expectStatus().isOk()
    .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(2)
    .thenCancel()
    .verify();
```

Đoạn này là **minh họa thêm**, đòi hỏi endpoint `/api/events` có thật và phát ít nhất hai phần tử có thể decode thành String. Cần import `org.springframework.test.web.reactive.server.FluxExchangeResult` và `reactor.test.StepVerifier`. Đối với SSE, cần kiểm tra media type và kiểu event/decoder thực sự. Không thêm snippet này vào test hoàn chỉnh mục 5 vì ứng dụng mẫu không khai báo endpoint `/api/events`.

Lưu ý rằng security có thể kiểm tra quyền khi thiết lập subscription/request, nhưng nếu các phần tử stream chứa dữ liệu thuộc nhiều người dùng, **điều kiện lọc quyền trên từng tài nguyên vẫn cần thực thi trong pipeline nghiệp vụ**. Test “kết nối stream thành công” không chứng minh mọi sự kiện trong stream đều được phép công bố.

## 12. Cách chẩn đoán test 401, 403 hoặc redirect sai

### Trường hợp 1: mong đợi 401 nhưng nhận 302

Nguyên nhân thường là form login đang bật hoặc có `AuthenticationEntryPoint` chọn redirect cho request. Với API JSON, cấu hình HTTP Basic/Bearer cùng entry point phù hợp. Trong ứng dụng mẫu, `formLogin(form -> form.disable())` khiến test anonymous GET `/api/admin` dự kiến nhận 401. Đừng sửa assertion thành 302 mà chưa hiểu hợp đồng API.

### Trường hợp 2: mock admin vẫn nhận 403

Kiểm tra lần lượt:

- Có thật đang áp dụng `springSecurity()` cho WebTestClient gắn với context?
- Matcher `/api/admin` có khớp đường dẫn test?
- Test sử dụng `roles("ADMIN")` hay một authority khác? Rule `hasRole("ADMIN")` cần `ROLE_ADMIN`.
- Nếu là POST/PUT/DELETE, có thiếu CSRF token, CORS hoặc một rule khác chặn trước quyền?
- Controller/service có `@PreAuthorize` hoặc kiểm tra quyền nghiệp vụ bổ sung?

Đừng suy rằng mọi 403 có nghĩa tài khoản thiếu role; CSRF, policy engine hoặc các lớp kiểm soát khác có thể tạo 403.

### Trường hợp 3: test không có principal vẫn trả 200 cho endpoint riêng tư

Xem test đang dùng `mockUser` mặc định, `@WithMockUser` trên cả class hay filter security chưa được nạp. Một controller-only client không tự động mang cấu hình production. Hãy thử lại từ client sạch, không mutator, và đối chiếu rule `.anyExchange().authenticated()`.

### Trường hợp 4: Basic credentials đúng nhưng 401

Kiểm tra `MapReactiveUserDetailsService` được nạp, username/password trong test có khớp, password encoder/format có hợp lệ và server đang dùng HTTP Basic. `mockUser` thành công không chứng minh Basic login thành công; cần giữ ít nhất một bài test credentials thật để phân biệt hai tầng.

### Trường hợp 5: POST đúng role nhưng 403

Tách thành hai test:

1. Editor **không** CSRF token → 403.
2. Editor **có** `csrf()` → 200.

Sau đó thử USER **có** `csrf()` → 403. Ba kịch bản này giúp phân biệt lỗi CSRF với lỗi role. Nếu thay cả auth và CSRF trong một lần thử, khó biết điều kiện nào bị từ chối.

### Trường hợp 6: 404 thay vì 401/403

Có thể endpoint không được component-scan, tên URL sai, controller thiếu annotation hoặc test context không nạp RouterFunction. Khi request đi qua security với quyền hợp lệ nhưng không có handler, HTTP 404 là kết quả hợp lý; nó không tự chứng minh bảo mật sai. Kiểm tra test khớp đường dẫn thật và bean controller hiện diện.

### Trường hợp 7: test có kết quả khác production

Test in-memory bỏ qua network, reverse proxy, OAuth identity provider, TLS, CORS preflight và một số session/cookie đặc thù. Bổ sung kiểm thử live server hoặc end-to-end phù hợp cho những điểm phụ thuộc vào network/hạ tầng. Đừng cố nhồi mọi loại kiểm thử vào `@SpringBootTest` không có port mạng.

## 13. Thiết kế ma trận kiểm thử bảo mật đủ mạnh

Thay vì chỉ ghi một test `200 OK`, lập bảng điều kiện:

| Đối tượng | Hành động | Anonymous | USER | EDITOR | ADMIN |
| --- | --- | --- | --- | --- | --- |
| `GET /api/public` | Đọc công khai | 200 | 200 | 200 | 200 |
| `GET /api/admin` | Xem quản trị | 401 | 403 | 403 | 200 |
| `GET /api/me` | Xem danh tính hiện tại | 401 | 200 | 200 | 200 |
| `POST /api/notes` có CSRF | Tạo ghi chú | Tùy thứ tự bộ lọc; không được 200 | 403 | 200 | 403 trong chính sách mẫu |
| `POST /api/notes` thiếu CSRF | Tạo ghi chú | Không được 200 | 403 | 403 | 403 |

Hàng cuối là **hành vi của ví dụ có CSRF mặc định**. Với API Bearer stateless được thiết kế không dùng cookie tự động, chiến lược CSRF có thể khác và cần test riêng.

Các loại test nên bổ sung khi phát triển sản phẩm:

- **Kiểm thử không xác thực:** request thiếu token/password, credential sai, session hết hạn.
- **Kiểm thử phân quyền âm tính:** đúng danh tính nhưng thiếu role/scope, sai tenant, sai owner, tài nguyên bị thu hồi quyền.
- **Kiểm thử CSRF/CORS:** phương thức ghi thiếu token, CORS preflight từ origin khác, header/credential hợp lệ.
- **Kiểm thử controller/business:** validation lỗi, bản ghi không tồn tại, phản hồi JSON đúng mã/trường.
- **Kiểm thử reactive:** truyền SecurityContext qua các operator, service policy chạy trong publisher và không chặn I/O.
- **Kiểm thử thật trên HTTP:** khả năng kết nối, redirect, cookie, TLS/proxy khi cần.
- **Kiểm thử stream:** không lộ event của người không có quyền, xử lý hủy subscription/timeout.

Một ma trận tốt phân biệt **kết quả HTTP** với **lý do phải đạt được**. Ví dụ test POST không CSRF trả 403 chưa chứng minh rằng role đã được kiểm tra đúng; test USER có CSRF mới kiểm tra nhánh role từ chối trong chính sách đó.

## 14. Checklist khi áp dụng vào dự án

1. Đảm bảo ứng dụng thực sự chạy WebFlux reactive; dùng `ServerHttpSecurity` và `SecurityWebFilterChain`.
2. Thêm `spring-security-test`; xác minh phụ thuộc `spring-boot-starter-test` và JUnit Platform.
3. Khởi tạo `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` khi muốn kiểm thử tích hợp WebFilter mà không mở server.
4. Dùng `mockUser()` / `@WithMockUser` để kiểm thử phân quyền; thêm test HTTP Basic/Bearer thật để kiểm thử xác thực và token validation.
5. Đối với request ghi, kiểm tra đủ **có và không có CSRF**, đồng thời đủ và thiếu role.
6. Kiểm tra response status, header và body; không chỉ khẳng định controller đã được gọi.
7. Không để test slice bỏ qua cấu hình security: nếu dùng `@WebFluxTest`, phải nạp đúng security configuration cần kiểm thử.
8. Không dùng `mockUser()` để kết luận về server chạy qua mạng; thêm bài test `RANDOM_PORT` hoặc môi trường tương ứng.
9. Đối với nghiệp vụ có dữ liệu nhạy cảm, kiểm tra quyền trên tài nguyên cụ thể ở service, không chỉ role tại URL.
10. Theo dõi version Spring Boot/Security; kiểm tra thay đổi package test annotation khi nâng major version.

**Điều quan trọng nhất:** `WebTestClient` chỉ thực sự kiểm thử Spring Security reactive khi bạn xác định rõ **context nào, security filter nào và danh tính kiểm thử nào** đang được sử dụng. Một bộ test tốt cần có cả request anonymous, user thiếu quyền, user đủ quyền, request thiếu CSRF và request có CSRF, đồng thời giữ một đường kiểm thử xác thực thực tế để tránh nhầm “mock principal hoạt động” với “đăng nhập production đã an toàn”.

### Tài liệu tham khảo

- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Authentication with WebTestClient](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security — Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security — Testing OAuth2 and mockJwt](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
