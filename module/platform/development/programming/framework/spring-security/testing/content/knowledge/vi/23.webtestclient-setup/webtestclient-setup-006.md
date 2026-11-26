# `@SpringBootTest` kết hợp `WebTestClient` theo phạm vi mục tiêu

## 1. Mục tiêu: chọn đúng phạm vi kiểm thử bảo mật HTTP

Trong Spring Security, cùng một phép thử “người chưa đăng nhập không được truy cập API” có thể chạy ở nhiều mức độ:

- **Chỉ một controller và một phần cấu hình WebFlux**: chạy slice test để phản hồi nhanh.
- **Toàn bộ ứng dụng Reactive nhưng không mở cổng HTTP**: dùng `@SpringBootTest` với `WebTestClient` gắn vào `ApplicationContext`.
- **Toàn bộ ứng dụng qua HTTP thật**: dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `WebTestClient` kết nối bằng URL cổng đang chạy.
- **Ứng dụng Servlet/Spring MVC**: dùng `MockMvc` cho mock HTTP, hoặc dùng `WebTestClient.bindToServer()` nếu muốn kiểm tra qua một server Servlet thật.

Chọn phạm vi có chủ đích rất quan trọng trong module `SPRING_SECURITY_TESTING`. Người học cần kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng Spring Security Test trên cả Servlet và Reactive, với `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và những request được phép hoặc bị từ chối.

Ví dụ một request nhận `200 OK` nhờ `mockUser()` chứng minh ứng dụng xử lý một principal giả như mong đợi. Nó **không** chứng minh trình duyệt hoặc HTTP client bên ngoài đã xác thực mật khẩu, chữ ký JWT hay login OAuth2 thực sự. Ngược lại, request đi qua cổng HTTP thật có thể kiểm tra cookie, headers và entry point từ phía client, nhưng sẽ tốn thời gian khởi động server.

**Sau bài này**, bạn sẽ biết chọn giữa `@WebFluxTest`, `@SpringBootTest` ở chế độ mock và `@SpringBootTest` với cổng thật, đồng thời đặt các assertion `401`, `403`, `200` và CSRF đúng ngữ cảnh.

## 2. Bảng quyết định theo mục tiêu

| Mục tiêu | Thiết lập khuyến nghị | Đường request | Điều kiểm tra được |
| --- | --- | --- | --- |
| Một controller WebFlux và một số bean liên quan | `@WebFluxTest(YourController.class)`, import cấu hình bảo mật cần thiết | Mock WebFlux | Routing, binding, xử lý controller và những security filters có trong test context |
| Toàn ứng dụng WebFlux, không mở HTTP port | `@SpringBootTest(webEnvironment = MOCK)` + `@AutoConfigureWebTestClient` | Gắn WebTestClient vào WebFlux application context | Tích hợp toàn bộ bean, WebFlux handlers và web filters trong mô phỏng server |
| Cần chắc chắn client mock hỗ trợ `mockUser()`, `csrf()` | `@SpringBootTest(MOCK)` + `bindToApplicationContext(context).apply(springSecurity())` | Mock WebFlux với Spring Security Test | SecurityContext và request post-processors giả trong vòng đời request |
| WebFlux qua socket thực, kiểm tra headers/cookies | `@SpringBootTest(RANDOM_PORT)` + `bindToServer()` | TCP/HTTP thật | Embedded server, filters, codecs, HTTP status, headers và session |
| Spring MVC/Servlet, cần mock HTTP | `@SpringBootTest` + `@AutoConfigureMockMvc` | MockMvc qua Servlet filter chain | Form login, security filters, servlet session, CSRF, phân quyền |
| Spring MVC/Servlet, muốn dùng API `WebTestClient` | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient.bindToServer()` | TCP/HTTP thật | HTTP behavior của server Servlet; không có reactive mock server |
| Chỉ kiểm tra một hàm nghiệp vụ | JUnit/Mockito thông thường | Không qua HTTP | Hành vi hàm, không chứng minh HTTP security |

`@SpringBootTest` tải application context đầy đủ, còn `@WebFluxTest` chỉ tải một lát cắt của WebFlux. Một slice test có thể cần `@Import` security config và mock các dependency không thuộc slice. Nếu bỏ cấu hình bảo mật khỏi slice, kết quả test không đại diện cho policy mà ứng dụng thực tế đang sử dụng.

**Điểm phân biệt cốt lõi:** `WebTestClient` là **API của client kiểm thử**, không mặc định có nghĩa application là Reactive. Khi client gắn vào `ApplicationContext` WebFlux, nó không sử dụng socket. Khi client gắn với `bindToServer()`, nó gửi HTTP thật và có thể kiểm thử cả WebFlux lẫn Servlet.

## 3. Cấu trúc test và những phụ thuộc cần thiết

Với ví dụ WebFlux, một cấu hình Gradle cơ bản:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Các thư viện cần cho WebTestClient và các annotation kiểm thử thông thường đã được starter test cung cấp qua dependency phù hợp. Khi viết test security với `mockUser()`, `mockJwt()` hoặc `csrf()`, cần có `spring-security-test` trên test classpath.

Trong **Spring Boot 3.x**, annotation `@AutoConfigureWebTestClient` nằm ở package `org.springframework.boot.test.autoconfigure.web.reactive`, còn `@LocalServerPort` nằm ở `org.springframework.boot.test.web.server`. Đường dẫn import có thể khác ở dòng Spring Boot lớn hơn; ưu tiên version và auto-import từ dependency thực tế của dự án.

Đừng đưa cả `spring-boot-starter-web` và `spring-boot-starter-webflux` vào ứng dụng rồi mặc định coi application là Reactive. Khi cả hai có mặt, Spring Boot thường ưu tiên **Servlet MVC** nếu không cấu hình loại ứng dụng khác. Trong trường hợp đó, `@AutoConfigureWebTestClient` cho mô phỏng WebFlux không tự biến Servlet application thành WebFlux.

### 3.1. Một API WebFlux nhỏ làm ví dụ

Giả sử ta có bốn endpoint:

| Method/path | Chính sách | Kết quả dự kiến |
| --- | --- | --- |
| `GET /api/public` | `permitAll()` | `200` cho khách |
| `GET /api/private` | `authenticated()` | `401` khi không có authentication; `200` khi đã xác thực |
| `GET /api/admin` | Role `ADMIN` | `403` cho `USER`; `200` cho `ADMIN` |
| `POST /api/notes` | Đã xác thực; CSRF mặc định bật | `403` nếu thiếu CSRF, thành công khi đủ authentication/CSRF |

Controller WebFlux:

~~~java
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
    Mono<String> privateInfo() {
        return Mono.just("private");
    }

    @GetMapping("/api/admin")
    Mono<String> adminInfo() {
        return Mono.just("admin");
    }

    @PostMapping("/api/notes")
    Mono<String> createNote() {
        return Mono.just("created");
    }
}
~~~

Cấu hình Spring Security cho WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyExchange().authenticated())
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

Các mật khẩu `{noop}` trong ví dụ chỉ dùng với tài khoản giả của test. Ứng dụng thực cần password encoder phù hợp và quản lý secrets an toàn. Với `httpBasic`, request không có credentials đến endpoint cần xác thực thường nhận `401 Unauthorized`; principal có quyền không đủ nhận `403 Forbidden`.

CSRF vẫn đang bật theo mặc định. Không tắt CSRF chỉ để test `POST` trở nên xanh; cần quyết định chính sách CSRF theo kiến trúc xác thực và viết test tương ứng.

## 4. `@SpringBootTest(MOCK)` + `@AutoConfigureWebTestClient` cho WebFlux

Đây là lựa chọn khi muốn tải toàn bộ ứng dụng và chạy HTTP test kiểu mô phỏng, không khởi động cổng mạng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveFullContextMockTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publicEndpointAllowsAnonymousClient() {
        webTestClient.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void privateEndpointRejectsAnonymousClient() {
        webTestClient.get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

**Giải thích từng phần:**

1. `@SpringBootTest(webEnvironment = MOCK)` tải toàn bộ Spring application context và dùng môi trường web mô phỏng. Với WebFlux, không có cổng HTTP thật được cấp cho test.
2. `@AutoConfigureWebTestClient` yêu cầu Spring Boot cấu hình một `WebTestClient` để test có thể inject.
3. `.exchange()` thực thi một request qua đường đi đã bind và trả về đối tượng assertions.
4. `.expectStatus().isUnauthorized()` kiểm tra đầu ra của security entry point; nó không tự kiểm tra mật khẩu, JWT hoặc OAuth2 token.
5. `.expectBody(String.class).isEqualTo(...)` kiểm tra payload như một phần hợp đồng HTTP.

Ví dụ phù hợp để kiểm tra cấu hình filter, routing, controller và serialization chung trong ứng dụng WebFlux. Tuy nhiên, tất cả nằm trong tiến trình kiểm thử: nó chưa kiểm tra cổng TCP, proxy hoặc TLS.

**Điều kiện:** `@AutoConfigureWebTestClient` hoạt động trong ngữ cảnh WebFlux và phải có các dependency WebFlux test cần thiết. Nếu application là Spring MVC/Servlet, dùng `MockMvc` cho chế độ mock hoặc `WebTestClient` gắn server thật theo mục 8.

## 5. Khi cần `mockUser()` và `csrf()`: áp dụng `springSecurity()` tường minh

Với test security có principal giả, có thể dựng client trực tiếp từ `ApplicationContext` và áp dụng cấu hình kiểm thử Spring Security. Cách này minh bạch về việc filter chain và các mutator được tích hợp:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveSecurityMockTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void bindSecurityAwareClient() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void readerCanAccessPrivateEndpoint() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .get()
              .uri("/api/private")
              .exchange()
              .expectStatus().isOk()
              .expectBody(String.class).isEqualTo("private");
    }

    @Test
    void readerCannotAccessAdminEndpoint() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminEndpoint() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isOk();
    }

    @Test
    void missingCsrfIsRejectedForPost() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .post()
              .uri("/api/notes")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void csrfAllowsAuthenticatedPost() {
        client.mutateWith(mockUser("reader").roles("USER"))
              .mutateWith(csrf())
              .post()
              .uri("/api/notes")
              .exchange()
              .expectStatus().isOk()
              .expectBody(String.class).isEqualTo("created");
    }
}
~~~

`mockUser("reader").roles("USER")` đưa principal thử nghiệm vào request. Điều này cho phép kiểm chứng phân quyền của `SecurityWebFilterChain` mà không phải đi qua HTTP Basic hoặc một Identity Provider bên ngoài. `csrf()` thêm dữ liệu CSRF phù hợp cho request mô phỏng. Đây là **test cấu hình bảo mật ứng dụng**, không phải test người dùng đã nhập mật khẩu thật.

### 5.1. Cách đọc kết quả

| Ca kiểm thử | Principal | CSRF | Mong đợi | Kết luận hợp lệ |
| --- | --- | --- | --- | --- |
| `GET /api/private` | Anonymous | Không áp dụng | `401` | Entry point bảo vệ endpoint |
| `GET /api/private` | Mock USER | Không áp dụng | `200` | Chính sách cho phép user đã xác thực |
| `GET /api/admin` | Mock USER | Không áp dụng | `403` | Thiếu quyền ADMIN |
| `GET /api/admin` | Mock ADMIN | Không áp dụng | `200` | Chính sách cho phép role ADMIN |
| `POST /api/notes` | Mock USER | Thiếu | `403` | CSRF filter chặn thao tác ghi |
| `POST /api/notes` | Mock USER | Có | `200` | Request đáp ứng authentication và CSRF policy trong demo |

**Cẩn thận:** nếu request chưa đăng nhập gọi `POST` thiếu CSRF, nó có thể bị từ chối bằng `403` bởi CSRF filter trước khi đến bước yêu cầu authentication. Để xác minh chính xác chính sách đăng nhập, dùng `GET` hoặc cung cấp CSRF hợp lệ trước khi đánh giá kết quả của authorization.

### 5.2. Dùng `@WithMockUser` trong WebFlux

Spring Security Test hỗ trợ `@WithMockUser` để thiết lập authentication giả trong test context. Với WebFlux, test execution listeners và cơ chế reactive security context phải được tích hợp đúng. Đó là lý do ví dụ ở trên dùng `mutateWith(mockUser(...))` trên từng request: ngữ cảnh mà test cung cấp được thể hiện ngay tại request cụ thể, tránh nhầm với HTTP client gửi request qua server ngoài tiến trình.

Nếu test có nhiều request dùng người dùng khác nhau, mutator trên từng request cũng giúp đọc lại case dễ hơn. Không dùng `@WithMockUser` hoặc `mockUser()` để kết luận HTTP Basic đã kiểm tra password hoặc JWT đã được decode.

### 5.3. Ngữ cảnh Reactor khác với ThreadLocal Servlet

WebFlux dùng `ReactiveSecurityContextHolder`, mang `SecurityContext` qua Reactor Context. Servlet thường truy cập `SecurityContextHolder` với chiến lược gắn ThreadLocal trong chu kỳ xử lý request. Trong ứng dụng Reactive, đừng tự đọc `SecurityContextHolder.getContext()` ở thread kiểm thử sau `exchange()` rồi cho rằng nó đại diện cho request WebFlux đã kết thúc.

Nếu cần kiểm tra principal ngay trong handler hoặc service reactive, có thể dùng `ReactiveSecurityContextHolder.getContext()` trong reactive chain hoặc injection `Mono<Principal>`/`Authentication` phù hợp. Với kiểm thử HTTP, ưu tiên khẳng định status và response quan sát được; với method security, thêm phép thử dịch vụ chuyên biệt.

## 6. `@WebFluxTest`: khi chỉ kiểm tra một lát cắt

`@SpringBootTest` toàn context có thể tốn chi phí khởi động không cần thiết nếu mục tiêu chỉ là mapping, validation, lỗi controller hoặc một rule của WebFlux. Khi đó:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = DemoApi.class)
@Import(DemoSecurity.class)
class DemoApiSliceTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksInSlice() {
        client.get()
              .uri("/api/public")
              .exchange()
              .expectStatus().isOk();
    }
}
~~~

Phần `@Import(DemoSecurity.class)` bảo đảm test mang đúng cấu hình security mong muốn. Tùy cách khai báo security và auto configuration, một số bean security có thể đã được slice test nạp sẵn; việc import nên được quyết định theo project thật để tránh duplicate beans. Nếu controller phụ thuộc service, cung cấp mock bean/test fixture thích hợp theo version Spring Boot đang sử dụng.

Một test slice không tự chứng minh các filter hoặc beans **bị lược bỏ** hoạt động đúng trong toàn ứng dụng. Vì vậy, khi bảo mật phụ thuộc nhiều security chains, custom authentication manager, OIDC hoặc filter riêng, nên có ít nhất một `@SpringBootTest` cho đường đi quan trọng.

### 6.1. Không lấy độ rộng context làm thước đo duy nhất

Toàn context chưa chắc là bài test đúng nếu bạn vô hiệu hóa security filters, mock mọi authentication provider hoặc đặt sẵn principal cho tất cả request. Ngược lại, slice test đủ cấu hình có thể bắt được bug phân quyền rất hữu ích. Điều quan trọng là **danh sách component được chạy thực** phải khớp mục tiêu.

## 7. `@SpringBootTest(RANDOM_PORT)`: kiểm tra HTTP thật

Khi mục tiêu bao gồm embedded server, routing qua socket, headers, cookies, login redirect hoặc cách client bên ngoài nhận response, chạy ứng dụng thật trên một cổng được chọn tự động:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveRealHttpTests {

    @LocalServerPort
    int port;

    WebTestClient http;

    @BeforeEach
    void buildHttpClient() {
        http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void anonymousClientGets401() {
        http.get()
            .uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void realBasicCredentialsAreChecked() {
        http.get()
            .uri("/api/private")
            .headers(h -> h.setBasicAuth(
                    "reader", "reader-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private");
    }

    @Test
    void validUserWithoutAdminRoleGets403() {
        http.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                    "reader", "reader-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Ở đây `bindToServer()` tạo client gửi HTTP thực, không có cơ chế tự gắn `Authentication` từ `mockUser()`. Request kiểm tra HTTP Basic thông qua `Authorization: Basic ...`, nên nếu password sai thì authentication manager phải từ chối. Đây là kết luận mạnh hơn một ca `mutateWith(mockUser())` khi mục tiêu là kiểm tra HTTP Basic.

### 7.1. Lưu ý về ngữ cảnh client và server

Với `RANDOM_PORT`, ứng dụng chạy trên embedded server trong process test nhưng có kết nối HTTP riêng. `@WithMockUser` là phương tiện thiết lập test security context trong process test; nó không tự truyền một principal qua mạng vào request HTTP bên ngoài. `mockUser()`, `mockJwt()` và `csrf()` của mock-server test cũng không thay thế được headers/cookies thật khi dùng `bindToServer()`.

Khi test form login qua HTTP thật, cần gửi form data và CSRF token theo cách trình duyệt gửi, giữ session cookie qua các request và xác nhận redirect hoặc access denied. Khi test Bearer JWT, phải gửi token ký hợp lệ qua header và cấu hình decoder/validator thực; mock JWT không chứng minh chữ ký đã được xác minh.

### 7.2. Không ép mọi request chưa đăng nhập phải nhận 401

Demo ở trên bật HTTP Basic nên kết quả mặc định cho `GET /api/private` thiếu credentials là `401`. Nếu ứng dụng bật form login và dùng `LoginUrlAuthenticationEntryPoint`, request có thể nhận `302` đến trang đăng nhập. Nếu người dùng đã xác thực nhưng thiếu authority, kết quả có thể là `403`. Thiếu CSRF trên POST cũng thường cho `403`.

Hãy dựa trên **security filter chain và entry point thực tế** để chọn assertions. Một status đơn lẻ không đủ để chứng minh authentication/authorization đúng trong mọi cấu hình.

## 8. Dùng `WebTestClient` với ứng dụng Servlet/Spring MVC

`WebTestClient` có thể test một ứng dụng Servlet **qua HTTP server thật**, bởi nó là HTTP client. Ví dụ:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletWithWebTestClientTests {

    @LocalServerPort
    int port;

    @Test
    void protectedServletEndpointRejectsAnonymous() {
        WebTestClient http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        http.get()
            .uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Ví dụ giả định Spring MVC application đã cấu hình endpoint `/api/private`, `SecurityFilterChain` và một authentication entry point trả `401`. Cần có dependency test cho `WebTestClient` và các thành phần `WebFlux` test client theo Spring Boot version tương ứng; dùng API giống nhau không có nghĩa server đang chạy WebFlux.

Nếu bạn muốn test **Servlet mà không mở cổng**, nên dùng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ServletMockSecurityTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousIsRejected() throws Exception {
        mockMvc.perform(get("/api/private"))
               .andExpect(status().isUnauthorized());
    }
}
~~~

Trong ví dụ MockMvc, import static `MockMvcRequestBuilders.get` và `MockMvcResultMatchers.status`. Spring Framework cũng có adapter `MockMvcWebTestClient` cho phép dùng API WebTestClient trên backend MockMvc, nhưng nó là cơ chế **MockMvc adapter**, không phải WebFlux application context hay một cổng HTTP thật. Hãy chọn `MockMvc` khi kiểm tra các matcher dành riêng cho Servlet như `SecurityMockMvcResultMatchers.authenticated()` hoặc HTTP session.

## 9. JWT/OAuth2/OIDC giả lập trong WebTestClient: giới hạn cần ghi rõ

Trong mock WebFlux test đã áp dụng `springSecurity()`, Spring Security Test có các mutators:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;

// Giả lập một principal JWT có scope "reports.read".
client.mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("reader")
            .claim("scope", "reports.read")))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

Ví dụ trên chỉ phù hợp khi application context đang kiểm thử có một chính sách tương thích với principal JWT giả. Nó **không kiểm tra `ReactiveJwtDecoder`**, chữ ký JWS, issuer hoặc hạn token. `mockOidcLogin()` tương tự cho phép tạo OIDC principal giả để kiểm tra logic sau login; nó không tự thực thi authorization-code flow hay xác minh ID token thật.

| Mục tiêu | Mock WebFlux | HTTP thật |
| --- | --- | --- |
| Kiểm tra policy với role | `mockUser(...)` | Gửi credentials/token/cookie hợp lệ |
| Kiểm tra policy với JWT claims | `mockJwt(...)` | Gửi Bearer token qua HTTP header |
| Kiểm tra OAuth2/OIDC principal | `mockOAuth2Login(...)` / `mockOidcLogin(...)` | Chạy login flow tích hợp hoặc dùng IdP test |
| Kiểm tra CSRF policy | `csrf()` mutator | Lấy và gửi CSRF token/cookie như client thật |
| Kiểm tra chữ ký/hạn JWT | Chỉ khi gửi Bearer thật qua decoder trong test context | Gửi Bearer thật qua decoder |
| Kiểm tra HTTP Basic password | Không dùng `mockUser()` để suy luận | Gửi `Authorization: Basic ...` và kiểm tra status |

Các phương pháp này bổ sung nhau. Dùng mock để kiểm tra nhiều tổ hợp quyền nhanh; dùng HTTP thật khi mục tiêu liên quan trực tiếp đến network-boundary behavior hoặc hợp đồng với hệ thống nhận request.

## 10. Cấu hình, timeout và khả năng tái hiện

### 10.1. Dùng cổng động

`RANDOM_PORT` giúp các test song song tránh cạnh tranh một port cố định. Không hardcode `localhost:8080` rồi hy vọng server tình cờ đang chạy. `@LocalServerPort` lấy đúng port được ứng dụng test sử dụng.

### 10.2. Dùng một base URL rõ ràng

Với client thật, cấu hình `baseUrl("http://localhost:" + port)` giúp các request `.uri("/...")` không bị gửi nhầm máy chủ. Với mock binding, request được điều phối trong application context, không cần network base URL.

### 10.3. Timeout không nên che lỗi xác thực

`WebTestClient` có thể tùy chỉnh thời gian chờ response, ví dụ:

~~~java
WebTestClient http = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .responseTimeout(Duration.ofSeconds(5))
        .build();
~~~

Thêm import `java.time.Duration`. Với stream phản hồi dài hoặc SSE, cần test timeout và cách tiêu thụ body phù hợp; đừng tăng timeout vô hạn để che việc endpoint bị treo. Khi kiểm tra security, hãy ưu tiên xác định đã nhận một status rõ ràng, không chỉ xem request có hoàn thành hay không.

### 10.4. Tránh chia sẻ session hoặc state không có chủ đích

Nếu test nhiều authentication paths, hãy đảm bảo cookies, security context và token fixtures không bị rò rỉ giữa các ca. Một `WebTestClient` được reuse không nhất thiết mô phỏng đầy đủ cookie jar của trình duyệt; với login/session HTTP thật, cần chủ động lưu và truyền cookies từ response khi cần.

Đối với `mockUser()`, cấu hình principal trên mỗi request giúp cô lập ca USER và ADMIN. Đối với mutable database, `@SpringBootTest` toàn context có thể cần dọn fixture sau mỗi test hoặc transaction/test data setup phù hợp; không phải cứ dùng mock HTTP là toàn bộ dữ liệu tự rollback.

## 11. Sự cố thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không inject được `WebTestClient` với `@SpringBootTest(MOCK)` | Ứng dụng là Servlet, thiếu WebFlux test auto configuration hoặc dependency | Xác nhận web application type; dùng `@AutoConfigureWebTestClient` cho WebFlux |
| Test có `mockUser()` nhưng bị `401` | Client mock chưa tích hợp `springSecurity()`, filter không đúng hoặc rule không khớp | Dùng binding tường minh ở mục 5, kiểm tra chain thực |
| POST nhận `403` dù đã mock user | Thiếu CSRF | Dùng `csrf()` nếu CSRF bật; viết ca thiếu CSRF riêng |
| Anonymous POST nhận `403` thay vì `401` | CSRF filter từ chối trước authentication entry point | Kiểm tra login policy bằng GET hoặc gửi CSRF hợp lệ |
| `@WithMockUser` không tác dụng trong `RANDOM_PORT` | Test principal không tự đi qua socket | Gửi Basic/Bearer/cookie thật qua client |
| `mockJwt()` cho `200` với JWT tưởng như hết hạn | Helper giả authentication, không gọi decoder | Gửi JWS thật đến `ReactiveJwtDecoder` |
| Test slice xanh nhưng full test thất bại | Slice thiếu filter/config/service ở context thật | Import đúng bean cho slice và thêm full-context test |
| Test full context xanh nhưng production sai | Authentication provider đã bị mock, filters tắt, hoặc chưa thử HTTP thật | Xác minh thành phần được thực thi, thêm real-HTTP test khi cần |
| Test Servlet không dùng được WebFlux mock binding | Servlet và WebFlux có server adapters khác nhau | Dùng `MockMvc` hoặc `WebTestClient.bindToServer()` |
| Test lỗi ngẫu nhiên khi chạy song song | Port cố định, dữ liệu chia sẻ hoặc thời gian token | `RANDOM_PORT`, fixture cô lập và clock ổn định |
| Kiểm tra 302 thành 401 | Ứng dụng dùng form login, không dùng HTTP Basic/Bearer entry point | Điều chỉnh assertion theo chain và redirect thực tế |

## 12. Thực hành theo mục tiêu

### Bài tập A: chọn mức test

Một API WebFlux mới cần kiểm tra quyền `ROLE_ADMIN` trên `GET /api/admin`, nhưng không cần kiểm tra cổng mạng. Hãy dùng `@WebFluxTest` có import security config hoặc `@SpringBootTest(MOCK)` nếu policy phụ thuộc nhiều bean. Viết hai ca: mock USER nhận `403` và mock ADMIN nhận `200`. Giải thích security components đã được nạp.

### Bài tập B: xác minh HTTP Basic thật

Sử dụng `@SpringBootTest(RANDOM_PORT)` và `WebTestClient.bindToServer()`. Gửi `GET /api/private` lần lượt không header, Basic sai mật khẩu, Basic đúng mật khẩu. Mong đợi `401`, `401` và `200` theo demo. Nêu lý do kết quả mạnh hơn test `mockUser()` nếu yêu cầu của bài là “mật khẩu có được xác minh không”.

### Bài tập C: phân biệt authorization và CSRF

Với `POST /api/notes` và CSRF đang bật, viết ba ca: (1) mock USER thiếu CSRF nhận `403`, (2) mock USER có CSRF nhận `200`, (3) mock ADMIN có CSRF cũng nhận `200` nếu policy chỉ yêu cầu authentication. Giải thích vì sao 403 ở trường hợp 1 không nhất thiết có nghĩa người dùng thiếu role.

### Bài tập D: JWT giả so với JWT thật

Chạy `mockJwt()` có scope hợp lệ để xác nhận phân quyền. Sau đó thiết lập `ReactiveJwtDecoder` thật với token được ký bằng khóa test và gửi Bearer header qua HTTP. Thử token hết hạn hoặc sai chữ ký; giải thích vì sao chỉ ca thứ hai chứng minh decoder đã kiểm tra token.

### Bài tập E: dùng WebTestClient cho Spring MVC

Một dự án Servlet đã có `@SpringBootTest(RANDOM_PORT)`. Viết test `WebTestClient.bindToServer()` kiểm tra `GET /api/private`. Sau đó viết cùng case bằng `@AutoConfigureMockMvc`. So sánh phạm vi: một request đi qua HTTP server thật và một request đi qua mock Servlet filter chain.

## 13. Ma trận chấp nhận trước khi kết luận test đã đủ phạm vi

| Câu hỏi | Nếu câu trả lời là “có” | Cần bổ sung khi “chưa” |
| --- | --- | --- |
| Cần xác nhận filter chain thực thi? | Giữ security filter trong mock/full context | Không tắt filters hoặc chỉ chạy controller standalone |
| Cần xác nhận tất cả bean ứng dụng tương tác? | `@SpringBootTest` | Slice test chưa đại diện toàn context |
| Cần xác nhận status/headers từ socket thật? | `RANDOM_PORT` + `bindToServer()` | Mock binding chưa kiểm tra HTTP port |
| Cần xác minh mật khẩu Basic? | Gửi header Basic thực qua server/security chain | `mockUser()` không kiểm tra mật khẩu |
| Cần xác minh chữ ký JWT hoặc ID token? | Token thật và decoder/validator thật | `mockJwt()` / `mockOidcLogin()` chỉ giả lập |
| Cần kiểm tra quyền nhiều tổ hợp nhanh? | Mock principal với đúng authorities | HTTP thật có thể không cần cho mọi tổ hợp |
| Cần kiểm tra CSRF? | Ca có token và thiếu token | `200` trên GET không cho biết CSRF POST đúng |
| Cần kiểm tra user/session nhiều request? | Lưu cookie và chạy flow tuần tự | Một request mock không chứng minh session lifecycle |

Khi một test ghi nhận `200`, `401` hoặc `403`, trước tiên cần biết **request đang đi qua mock WebFlux, qua MockMvc hay qua embedded HTTP server**. Từ đó mới kết luận được test đã xác minh phần nào của security stack.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, web environment và test client.
- [Spring Boot — Testing Spring WebFlux](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.with-mock-environment): auto configuration của WebTestClient trong môi trường mock.
- [Spring Security — WebFlux Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `WebTestClient.bindToApplicationContext` và `springSecurity()`.
- [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()` và security context.
- [Spring Security — Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `csrf()` cho WebTestClient.
- [Spring Framework — Testing WebFlux Applications](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): các kiểu binding, `bindToServer()` và WebTestClient.
- [Spring Framework — MockMvcWebTestClient](https://docs.spring.io/spring-framework/reference/testing/mockmvc/webtestclient.html): adapter WebTestClient cho ứng dụng Spring MVC.
