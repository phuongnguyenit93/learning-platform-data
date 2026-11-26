# Chuyển ma trận kiểm thử từ MockMvc sang WebTestClient đúng API

## 1. Bài thực hành tổng hợp: giữ nguyên mục tiêu, thay đúng công cụ

Một nhóm phát triển đang chuyển một API từ Spring MVC (Servlet) sang Spring WebFlux (Reactive). Trước khi chuyển, bộ test `MockMvc` đã kiểm tra:

- Khách chưa đăng nhập không xem được dữ liệu riêng.
- Người dùng `USER` được xem dữ liệu riêng nhưng không truy cập vùng quản trị.
- Người dùng `ADMIN` được vào vùng quản trị.
- Request `POST` có thay đổi trạng thái phải đi qua CSRF protection.
- Password sai phải bị từ chối; password đúng phải được xác thực.

Yêu cầu không phải chỉ “đổi `MockMvc` thành `WebTestClient` sao cho compile”. Ta phải **giữ nguyên hợp đồng bảo mật** và **chuyển đúng API theo stack**; đồng thời xác nhận rằng test vẫn chạy qua security filters, có assertion trên kết quả, và không vô tình biến kiểm thử authentication thành kiểm thử một principal giả lập.

Trong module `SPRING_SECURITY_TESTING`, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên Servlet và Reactive, sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và cả các ca cho phép lẫn từ chối. Bài thuộc chương **Thực hành tổng hợp**: tự xây dựng và chuyển đổi một ma trận kiểm thử thực tế.

Sau bài này, bạn sẽ:

1. Viết ma trận yêu cầu **độc lập với framework** trước khi sửa test.
2. Đối chiếu đúng `RequestPostProcessor` của Servlet với mock-server mutator của Reactive.
3. Thiết lập `MockMvc` và `WebTestClient` có tích hợp đúng Spring Security.
4. Chuyển assertions cho status, body, CSRF và roles mà không đổi ý nghĩa.
5. Viết test gửi HTTP Basic credentials thật cho cả Servlet và Reactive.
6. Phân biệt `jwt()` với `mockJwt()`, `oidcLogin()` với `mockOidcLogin()` và các hạn chế của mock.
7. Xây checklist chạy lại test suite/CI, phát hiện ca bị mất hoặc “test xanh giả” sau migration.

## 2. Bắt đầu bằng ma trận hành vi, không bắt đầu bằng tên method

Giả định một ứng dụng có bốn endpoint:

| Endpoint | Chính sách | Trạng thái thành công |
| --- | --- | --- |
| `GET /api/public` | `permitAll()` | `200 OK`, body `public` |
| `GET /api/private` | `authenticated()` | `200 OK`, body JSON chứa username |
| `GET /api/admin` | `hasRole("ADMIN")` | `200 OK`, body `admin` |
| `POST /api/notes` | `authenticated()`, CSRF bật | `201 Created`, body `created` |

Ta chọn **HTTP Basic** làm authentication entry point trong bài thực hành chính, để request thiếu hoặc sai credentials nhận `401 Unauthorized`. Nếu hệ thống đích dùng form login, anonymous request có thể nhận redirect `302`; lúc đó cần điều chỉnh assertion theo hợp đồng, **không ép framework trả `401` chỉ để giống ví dụ**.

<table>
<tr><th>Ca</th><th>Request</th><th>Danh tính/CSRF</th><th>Kỳ vọng</th><th>Nhánh được chứng minh</th></tr>
<tr><td>M01</td><td>GET public</td><td>Guest</td><td>200</td><td>Đường công khai</td></tr>
<tr><td>M02</td><td>GET private</td><td>Guest</td><td>401</td><td>Yêu cầu xác thực</td></tr>
<tr><td>M03</td><td>GET private</td><td>Mock USER</td><td>200</td><td>Đã authenticated thì được xem</td></tr>
<tr><td>M04</td><td>GET admin</td><td>Mock USER</td><td>403</td><td>Thiếu ROLE_ADMIN bị chặn</td></tr>
<tr><td>M05</td><td>GET admin</td><td>Mock ADMIN</td><td>200</td><td>Đủ ROLE_ADMIN được vào</td></tr>
<tr><td>M06</td><td>POST notes</td><td>Mock USER, không CSRF</td><td>403</td><td>CSRF từ chối</td></tr>
<tr><td>M07</td><td>POST notes</td><td>Mock USER, CSRF hợp lệ</td><td>201</td><td>CSRF + authentication được phép</td></tr>
<tr><td>M08</td><td>GET private</td><td>Basic password sai</td><td>401</td><td>Authentication manager từ chối</td></tr>
<tr><td>M09</td><td>GET private</td><td>Basic password đúng</td><td>200</td><td>Authentication manager chấp nhận</td></tr>
<tr><td>M10</td><td>GET admin</td><td>Basic USER password đúng</td><td>403</td><td>Phân quyền sau authentication thật</td></tr>
<tr><td>M11</td><td>GET admin</td><td>Basic ADMIN password đúng</td><td>200</td><td>Authentication và authorization đều qua</td></tr>
</table>

Ma trận trên là **hợp đồng chung**. Dù chuyển từ Servlet sang Reactive, các ca M01–M11 vẫn phải tồn tại, trừ khi nhóm chủ động thay đổi yêu cầu và ghi rõ lý do. Chỉ đổi syntax của một ca `200` nhưng bỏ ba ca từ chối không phải là một migration hoàn chỉnh.

### 2.1. Hai trục cần ghi lên từng test

| Trục | Lựa chọn A | Lựa chọn B |
| --- | --- | --- |
| Nguồn danh tính | Principal đã được test giả lập | Credentials thật trong HTTP request, server tự tạo Authentication |
| Đường vận chuyển | Mock Servlet/WebFlux exchange trong tiến trình | HTTP request qua socket tới embedded server |

`MockMvc.with(httpBasic(...))` có thể kiểm tra password thật **không cần socket**. `WebTestClient.bindToServer()` dùng socket thật, nhưng nếu client không gửi credentials thì `@WithMockUser` ở thread JUnit **không tự cấp danh tính** cho server. Không trộn hai trục này thành khái niệm “real test” duy nhất.

## 3. Bản đồ API: Servlet ↔ Reactive

Đây là bảng tra trước khi sửa Java imports:

| Mục tiêu | MockMvc / Servlet | WebTestClient / Reactive mock |
| --- | --- | --- |
| Tạo request | `mockMvc.perform(get("/x"))` | `client.get().uri("/x").exchange()` |
| Giả lập username | `.with(user("alice"))` | `client.mutateWith(mockUser("alice"))` |
| Giả lập role | `user("alice").roles("USER")` | `mockUser("alice").roles("USER")` |
| Giả lập authority | `user("alice").authorities(...)` | `mockUser("alice").authorities(...)` |
| Gắn CSRF hợp lệ | `.with(csrf())` | `client.mutateWith(csrf())` |
| Mock JWT | `.with(jwt())` | `client.mutateWith(mockJwt())` |
| Mock opaque token | `.with(opaqueToken())` | `client.mutateWith(mockOpaqueToken())` |
| Mock OAuth2 login | `.with(oauth2Login())` | `client.mutateWith(mockOAuth2Login())` |
| Mock OIDC login | `.with(oidcLogin())` | `client.mutateWith(mockOidcLogin())` |
| Mock authorized OAuth2 client | `.with(oauth2Client("client-id"))` | `client.mutateWith(mockOAuth2Client("client-id"))` |
| HTTP Basic credentials | `.with(httpBasic("u", "p"))` | `.headers(h -> h.setBasicAuth("u", "p"))` |
| Bearer token thật | `.header("Authorization", "Bearer " + token)` | `.headers(h -> h.setBearerAuth(token))` |
| Assert status | `.andExpect(status().isForbidden())` | `.expectStatus().isForbidden()` |
| Assert chuỗi body | `.andExpect(content().string("x"))` | `.expectBody(String.class).isEqualTo("x")` |
| Assert JSON path | `.andExpect(jsonPath("$.user").value("alice"))` | `.expectBody().jsonPath("$.user").isEqualTo("alice")` |
| Assert header | `.andExpect(header().exists("X-Id"))` | `.expectHeader().exists("X-Id")` |

**Lưu ý:** đây là đối chiếu theo **ý định kiểm thử**, không phải mỗi helper có cùng mọi overload và hành vi nội bộ. Khi đổi Spring Security major/minor, tra Javadoc **đúng phiên bản đã resolve** của `spring-security-test`, nhất là với các mutator JWT/OAuth2/OIDC.

### 3.1. Hai class được dùng nhiều nhất

Servlet:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
~~~

Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
~~~

Hai `csrf()` cùng tên nhưng thuộc **hai package khác nhau**. Hai `springSecurity()` setup helper cũng có class sở hữu khác nhau:

- MockMvc: `org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity()`.
- WebFlux WebTestClient: `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity()`.

Nếu một file import đồng thời hai static method cùng tên, sử dụng tên class đầy đủ hoặc tách test class theo stack. Không sửa lỗi ambiguous import bằng cách bỏ Security Test configurer.

## 4. Fixture Servlet: endpoint và SecurityFilterChain

Ví dụ dưới dành cho **một ứng dụng Spring MVC Servlet**. Nếu dự án đang dùng WebFlux, đây là phần **nguồn để chuyển đổi**, không phải các bean được khởi tạo đồng thời cùng cấu hình Reactive ở mục 5.

### 4.1. Controller Servlet

~~~java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletDemoApi {

    @GetMapping("/api/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/api/private")
    Map<String, String> privateInfo(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }

    @PostMapping("/api/notes")
    ResponseEntity<String> createNote() {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body("created");
    }
}
~~~

### 4.2. Cấu hình Servlet security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ServletDemoSecurity {

    @Bean
    SecurityFilterChain servletChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/private", "/api/notes")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService servletUsers() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader-password")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}admin-password")
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

`{noop}` chỉ để fixture ngắn gọn trong bài học. Trong môi trường thật, dùng password encoder phù hợp, secret an toàn và TLS. Không tắt CSRF: bài thực hành cần phân biệt `POST` có/không có token.

Dependencies thường có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

## 5. Fixture Reactive: endpoint và SecurityWebFilterChain

Khi chuyển sang WebFlux, controller có thể trả `Mono` hoặc `Flux`; security chain phải đổi đúng loại. **Không dùng `SecurityFilterChain(HttpSecurity)` của Servlet để bảo vệ WebFlux.**

### 5.1. Controller WebFlux

~~~java
import java.security.Principal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReactiveDemoApi {

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
    Mono<ResponseEntity<String>> createNote() {
        return Mono.just(
            ResponseEntity.status(HttpStatus.CREATED).body("created"));
    }
}
~~~

Controller Reactive dùng `Mono<Principal>` để lấy principal trong publisher. Cấu hình Servlet ở mục 4 dùng `Authentication` làm tham số trực tiếp. Hợp đồng trả status/body vẫn giống nhau, nhưng cách thực thi có khác biệt.

### 5.2. Cấu hình WebFlux security

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

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class ReactiveDemoSecurity {

    @Bean
    SecurityWebFilterChain reactiveChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/private", "/api/notes")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
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

Dependencies Reactive thay `spring-boot-starter-web` bằng `spring-boot-starter-webflux`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

**Điều kiện tiền đề:** các ví dụ giả định một Spring Boot application có `@SpringBootApplication` và controller/security configuration tương ứng được nạp. Trong một dự án chứa cả Spring MVC và WebFlux starters, Spring Boot có thể ưu tiên Servlet; phải xác nhận web application type trước khi kết luận test Reactive đang chạy.

## 6. Bộ test gốc MockMvc: thực thi ma trận M01–M07

Ở Servlet, `MockMvc` dùng `RequestPostProcessor` để gắn principal và CSRF. `@AutoConfigureMockMvc` cấu hình test client qua Spring Boot; security filters phải **được bật**. Đừng dùng `addFilters = false` trong test nhằm kiểm tra security chain.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletSecurityMatrixTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void m01_publicIsAvailable() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void m02_guestCannotReadPrivate() throws Exception {
        mockMvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void m03_mockUserCanReadPrivate() throws Exception {
        mockMvc.perform(get("/api/private")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void m04_mockUserCannotReadAdmin() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void m05_mockAdminCanReadAdmin() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(user("bob").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void m06_postWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/api/notes")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void m07_postWithCsrfIsCreated() throws Exception {
        mockMvc.perform(post("/api/notes")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }
}
~~~

**Đọc kết quả:** M03–M07 kiểm tra authorization và CSRF với **authentication giả**. M03 dùng username `alice` dù user store chỉ chứa `reader` và `admin`; test vẫn có thể xanh. Không ghi kết luận “password của alice đã được xác minh” từ kết quả này.

### 6.1. M06 phải có M07

Nếu chỉ có M06 nhận `403`, test có thể xanh dù endpoint bị chặn do một lỗi khác như security chain `denyAll`. M07 nhận `201` chứng minh cùng endpoint hoạt động **khi authentication và CSRF hợp lệ**. Một cặp âm/dương luôn giúp khoanh vùng nguyên nhân.

## 7. Bộ test WebTestClient: chuyển tương đương M01–M07

Ở WebFlux, dùng `WebTestClient.bindToApplicationContext(...)` với `SecurityMockServerConfigurers.springSecurity()`. Không thay `.with(...)` bằng một method tưởng tượng cùng tên; dùng `.mutateWith(...)` trên test client đã được gắn security.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveSecurityMatrixTests {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void connect() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void m01_publicIsAvailable() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void m02_guestCannotReadPrivate() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void m03_mockUserCanReadPrivate() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/api/private")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("alice");
    }

    @Test
    void m04_mockUserCannotReadAdmin() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void m05_mockAdminCanReadAdmin() {
        client.mutateWith(mockUser("bob").roles("ADMIN"))
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }

    @Test
    void m06_postWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .post().uri("/api/notes")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void m07_postWithCsrfIsCreated() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .post().uri("/api/notes")
            .exchange()
            .expectStatus().isCreated()
            .expectBody(String.class).isEqualTo("created");
    }
}
~~~

Mỗi test tự tạo một request với danh tính mong muốn. `client.mutateWith(...)` trả về một client đã được điều chỉnh; đừng dùng chung client đã gắn ADMIN cho toàn bộ lớp rồi vô tình khiến các ca guest/USER không còn thực sự độc lập.

### 7.1. Những chỗ đổi API không thể bỏ qua

| Chỗ trong M03 | Servlet | Reactive |
| --- | --- | --- |
| Tạo request | `perform(get("/api/private"))` | `get().uri("/api/private").exchange()` |
| Cấp principal | `with(user("alice").roles("USER"))` | `mutateWith(mockUser("alice").roles("USER"))` |
| Xác nhận status | `andExpect(status().isOk())` | `expectStatus().isOk()` |
| Kiểm tra JSON path | `jsonPath("$.user").value("alice")` | `expectBody().jsonPath("$.user").isEqualTo("alice")` |
| Tạo CSRF | `with(csrf())` | `mutateWith(csrf())` |
| Test server | Servlet mock pipeline | WebFlux mock exchange với `springSecurity()` |

Nếu `client.mutateWith(mockUser(...))` không hoạt động, trước tiên kiểm tra **binding và application context**. Nó cần WebFlux mock request được tích hợp Spring Security Test; đổi tên static import mà quên `apply(springSecurity())` có thể khiến test không gắn được context đúng cách.

## 8. M08–M11: chuyển authentication thật, không dùng mockUser

Để chứng minh user store và password authentication hoạt động, **không dùng** `@WithMockUser` hoặc `mockUser()` cho các ca này. Gửi username/password dưới dạng HTTP Basic credentials của request để filters/provider trên server xử lý.

### 8.1. MockMvc: `httpBasic()` tạo Authorization header

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletBasicCredentialsTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void m08_wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/api/private")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void m09_correctPasswordIsAccepted() throws Exception {
        mockMvc.perform(get("/api/private")
                .with(httpBasic("reader", "reader-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("reader"));
    }

    @Test
    void m10_readerCannotReadAdmin() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void m11_adminCanReadAdmin() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-password")))
            .andExpect(status().isOk());
    }
}
~~~

`httpBasic(...)` là `RequestPostProcessor` tạo header `Authorization: Basic ...`, **không phải** helper cấp `Authentication` đã xác thực. Với security filters và manager thật của test context, password sai bị từ chối, đúng được cấp identity và authorities từ `UserDetailsService`.

### 8.2. WebTestClient: `headers.setBasicAuth(...)`

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveBasicCredentialsTests {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void bind() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void m08_wrongPasswordIsRejected() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth(
                "reader", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void m09_correctPasswordIsAccepted() {
        client.get().uri("/api/private")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void m10_readerCannotReadAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void m11_adminCanReadAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "admin", "admin-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }
}
~~~

Tại đây, `MapReactiveUserDetailsService` và `ReactiveAuthenticationManager` (hoặc provider được cấu hình trong WebFlux test context) thực sự tham gia khi có Basic header. Nhưng `bindToApplicationContext` vẫn là **mock WebFlux HTTP**, không có kết nối TCP.

### 8.3. Cả hai ca đúng/sai đều quan trọng

| Nếu hệ thống bị lỗi | Chỉ test sai password | Chỉ test đúng password | Test cả hai |
| --- | --- | --- | --- |
| “Deny all” hoặc provider luôn từ chối | Có thể vẫn xanh | Đỏ | Đỏ |
| “Allow all” hoặc endpoint bị `permitAll` | Đỏ | Có thể vẫn xanh | Đỏ |
| User store trả sai authorities | Có thể không thấy | Private vẫn xanh | Phải thêm admin USER `403` và ADMIN `200` |

**M08–M11 không phải bản dịch của `mockUser()`.** Đây là nhóm kiểm thử **authentication từ HTTP credentials**, bổ sung cho nhóm policy với principal giả. Khi chuyển framework, phải giữ cả hai nhóm, không thay toàn bộ policy tests bằng login thật hoặc ngược lại.

## 9. Chuyển authorization theo authorities thay vì chỉ roles

Ví dụ business endpoint `GET /api/reports` yêu cầu authority `SCOPE_reports.read`. `roles` và `authorities` không đồng nghĩa:

| Rule | Authority cần có | Cách test mock đúng |
| --- | --- | --- |
| `hasRole('ADMIN')` | `ROLE_ADMIN` | `roles("ADMIN")` |
| `hasAuthority('SCOPE_reports.read')` | `SCOPE_reports.read` | `authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))` |
| `hasAuthority('REPORT_EXPORT')` | `REPORT_EXPORT` | `authorities(new SimpleGrantedAuthority("REPORT_EXPORT"))` |

Servlet:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/api/reports")
        .with(user("analyst").authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("analyst").authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")))
      .get().uri("/api/reports")
      .exchange()
      .expectStatus().isOk();
~~~

**Tiền đề:** hai đoạn này thuộc các test context đã khai báo `/api/reports` với rule `hasAuthority("SCOPE_reports.read")`. Không thêm test vào demo M01–M11 rồi cho rằng endpoint đã tồn tại: trong demo gốc, `anyRequest().denyAll()` sẽ từ chối một route chưa được khai báo.

Cũng cần ca thiếu scope tương ứng:

~~~java
// Servlet: principal có PROFILE_READ, không có reports.read.
mockMvc.perform(get("/api/reports")
        .with(user("analyst").authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read"))))
    .andExpect(status().isForbidden());

// Reactive: cùng ý nghĩa.
client.mutateWith(mockUser("analyst").authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read")))
      .get().uri("/api/reports")
      .exchange()
      .expectStatus().isForbidden();
~~~

**Đừng viết `roles("SCOPE_reports.read")`.** Với quy tắc mặc định, `roles(...)` thêm tiền tố `ROLE_`, làm authority khác với `SCOPE_reports.read` mà policy đang yêu cầu.

## 10. JWT: không biến `jwt()` thành header Bearer giả

Khi chuyển một Resource Server từ Servlet sang Reactive, test thường có mục tiêu **policy** và mục tiêu **token validation**. Phải tách hai loại.

### 10.1. Policy test — principal JWT giả

Servlet:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")))
      .get().uri("/api/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Nên thêm ca `SCOPE_profile.read` nhưng không có `SCOPE_reports.read`, kỳ vọng `403`.

**Tiền đề:** các test chạy trên Servlet Resource Server hoặc WebFlux Resource Server configuration tương ứng, có endpoint và authorization policy `SCOPE_reports.read`. Không chỉ thêm một test JWT vào context HTTP Basic của demo rồi suy luận decoder đã chạy.

Các helper `jwt()` và `mockJwt()` có thể cung cấp một `JwtAuthenticationToken` đã được test chuẩn bị. Chúng **không gửi JWS qua JWT decoder**; ngay cả khi bạn đặt claim `exp` trong quá khứ, helper không tự xác minh hạn và chữ ký.

### 10.2. Validation test — Bearer JWS ký thật

Khi yêu cầu là “token sai chữ ký bị từ chối”, dùng request chứa **JWS thật**:

~~~java
// Servlet / MockMvc:
mockMvc.perform(get("/api/reports")
        .header("Authorization", "Bearer " + signedJws))
    .andExpect(status().isOk());
~~~

~~~java
// Reactive / WebTestClient:
client.get().uri("/api/reports")
      .headers(headers -> headers.setBearerAuth(signedJws))
      .exchange()
      .expectStatus().isOk();
~~~

Trong các đoạn trên, `signedJws` phải được ký bằng private key test tương ứng public key được `JwtDecoder` / `ReactiveJwtDecoder` thực tế tin cậy. Không thay bằng `"fake-jwt"`. Cần ít nhất ma trận:

| Token / claim | Mục tiêu | Kỳ vọng thường gặp |
| --- | --- | --- |
| JWS hợp lệ, đủ scope | Decode + authorize | `200` |
| JWS sai chữ ký | Decoder từ chối | `401` |
| JWS hết hạn (vượt clock skew) | Timestamp validator từ chối | `401` |
| JWS sai issuer/audience theo policy | Claim validators từ chối | `401` |
| JWS hợp lệ, thiếu scope | Authentication qua, authorization từ chối | `403` |

Để test converter ánh xạ claims thành authorities, có thể kiểm thử converter riêng. Nếu `mockJwt().authorities(...)` trực tiếp cung cấp authority, nó **bỏ qua converter**, nên không chứng minh mapping `scope` từ token thật đúng.

## 11. OAuth2, OIDC và authorized client: cùng ý định, khác helper

Khi API cần principal của người dùng đã đăng nhập OAuth2:

~~~java
// Servlet:
mockMvc.perform(get("/api/me").with(oauth2Login()))
    .andExpect(status().isOk());

// Reactive:
client.mutateWith(mockOAuth2Login())
      .get().uri("/api/me").exchange()
      .expectStatus().isOk();
~~~

Khi code cần `OidcUser`:

~~~java
// Servlet:
mockMvc.perform(get("/api/me").with(oidcLogin()))
    .andExpect(status().isOk());

// Reactive:
client.mutateWith(mockOidcLogin())
      .get().uri("/api/me").exchange()
      .expectStatus().isOk();
~~~

Khi code cần một OAuth2 authorized client:

~~~java
// Servlet:
mockMvc.perform(get("/api/client-info")
        .with(oauth2Client("reports-client")))
    .andExpect(status().isOk());

// Reactive:
client.mutateWith(mockOAuth2Client("reports-client"))
      .get().uri("/api/client-info").exchange()
      .expectStatus().isOk();
~~~

**Điều kiện:** những snippet này dùng ở context **riêng**, nơi application có `/api/me` hoặc `/api/client-info` phù hợp và Spring Security OAuth2 dependencies/beans cần thiết; các endpoints ấy không thuộc demo cơ bản. Nên assert thêm username, attributes hoặc response body theo hợp đồng — `200` đơn độc thường chưa đủ để xác nhận mapping.

| Ý nghĩa | Servlet | Reactive |
| --- | --- | --- |
| OAuth2 principal sau login | `oauth2Login()` | `mockOAuth2Login()` |
| OIDC principal sau login | `oidcLogin()` | `mockOidcLogin()` |
| Authorized OAuth2 client có sẵn | `oauth2Client(...)` | `mockOAuth2Client(...)` |
| Truy cập SecurityContext | Servlet `SecurityContextHolder` | `ReactiveSecurityContextHolder` / Reactor Context |

**Giới hạn chung:** các helper trên không tự thực hiện authorization redirect, state/PKCE validation, `authorization_code` exchange, ID token signature/nonce validation hoặc HTTP token grant. Một migration chỉ chuyển `oauth2Login()` sang `mockOAuth2Login()` mới giữ được **test principal giả**, chưa chứng minh luồng OAuth2/OIDC thực vẫn chạy.

Với protocol tests, cần authorization server/IdP thử nghiệm, HTTP callback/token endpoint, cookie/session và các assertions cụ thể. Không dựng một `OAuth2AuthorizedClient` sẵn rồi coi đó là bằng chứng token endpoint đã nhận request.

## 12. Method security và sự khác biệt giữa thread-bound và Reactor Context

Khi migration còn liên quan `@PreAuthorize`, chỉ đổi HTTP helper là chưa đủ. Các annotation bảo mật phương thức phải được Spring kích hoạt trên đúng stack:

- Servlet: thường `@EnableMethodSecurity` và bean Spring được proxy.
- Reactive: `@EnableReactiveMethodSecurity`, service trả publisher được hỗ trợ như `Mono`/`Flux` và context đi theo Reactor pipeline.

Ví dụ Reactive:

~~~java
@PreAuthorize("hasAuthority('REPORT_READ')")
public Mono<String> readReport() {
    return Mono.just("report");
}
~~~

Một test cần thực sự **subscribe**:

~~~java
@Test
@WithMockUser(authorities = "REPORT_READ")
void authorizedCanReadReport() {
    StepVerifier.create(reportService.readReport())
            .expectNext("report")
            .verifyComplete();
}

@Test
@WithMockUser(authorities = "PROFILE_READ")
void unauthorizedCannotReadReport() {
    StepVerifier.create(reportService.readReport())
            .expectError(AccessDeniedException.class)
            .verify();
}
~~~

Test này yêu cầu `reportService` là Spring bean đã được proxy, Spring Security Test listener hoạt động và project có `reactor-test`. `assertNotNull(reportService.readReport())` không có giá trị tương đương: publisher có thể chưa được subscribe và authorization chưa được quan sát.

Trong WebFlux, `ReactiveSecurityContextHolder` dùng Reactor Context. Đừng kiểm tra `SecurityContextHolder.getContext()` ở thread JUnit sau `exchange()` rồi suy ra principal của server Reactive. Một `@WithMockUser` ở thread test cũng **không tự đi qua HTTP socket**.

## 13. Migrate sang HTTP server thật: không dùng mock-server mutators

Để kiểm chứng network boundary, dùng `RANDOM_PORT` và `bindToServer()`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveRealHttpTests {

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
    void basicCredentialsGoThroughHttpServer() {
        http.get().uri("/api/private")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void missingCredentialsAreUnauthorized() {
        http.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

**Sai phạm vi:**

~~~java
// Không dùng mock-server authentication configurer
// làm cơ chế truyền identity sang real HTTP server.
http.mutateWith(mockUser("reader").roles("USER"))
    .get().uri("/api/private").exchange();
~~~

Tùy version/configurer, code có thể lỗi lúc áp dụng mutator hoặc request không tạo ra authentication mà server đọc được. Không mong nó tự gửi username/password. `WebTestClient.bindToServer()` có thể gọi **Servlet server** lẫn WebFlux server, nhưng muốn xác thực phải gửi credentials/token/cookies qua HTTP.

### 13.1. CSRF ở real HTTP là luồng nhận và gửi lại token

Trong mock WebFlux, `.mutateWith(csrf())` có thể thiết lập token cho request test. Qua real HTTP, client phải:

1. Lấy CSRF token theo cơ chế ứng dụng phát hành (HTML/form, cookie hoặc endpoint ứng dụng cung cấp).
2. Giữ session cookie hoặc CSRF cookie tương ứng.
3. Gửi token trong header/form field được request handler của ứng dụng chấp nhận.
4. Gửi lại cookie/session đúng và kiểm tra response.

Không giả định Spring Security tự cung cấp `GET /csrf`. Nếu ứng dụng dùng form login, cần thêm login/cookie/redirect flow; nếu dùng JWT stateless, phải đánh giá CSRF theo threat model thay vì tắt tùy tiện.

### 13.2. Transaction và test data

Khi test qua `RANDOM_PORT`, server HTTP xử lý ở thread/transaction khác. Dữ liệu user vừa tạo trong một test-managed transaction chưa commit có thể **không xuất hiện** trong server's user store. Chuẩn bị fixture đã commit và cleanup rõ ràng, đặc biệt khi test chạy song song.

## 14. Tự động hóa ma trận mà không che giấu sự khác biệt API

Có thể lưu ma trận hành vi dưới dạng bảng testcase hoặc một lớp kịch bản thuần:

~~~java
record SecurityScenario(
        String id,
        String method,
        String path,
        String identity,
        int expectedStatus) { }
~~~

Ví dụ dữ liệu:

~~~java
List<SecurityScenario> scenarios = List.of(
    new SecurityScenario("M01", "GET", "/api/public", "guest", 200),
    new SecurityScenario("M02", "GET", "/api/private", "guest", 401),
    new SecurityScenario("M03", "GET", "/api/private", "USER", 200),
    new SecurityScenario("M04", "GET", "/api/admin", "USER", 403),
    new SecurityScenario("M05", "GET", "/api/admin", "ADMIN", 200)
);
~~~

Đây là **dữ liệu kịch bản**, không phải một test runner hoàn chỉnh. Cách thực thi khác nhau theo stack:

- Servlet adapter chuyển `identity="USER"` thành `RequestPostProcessor user(...).roles("USER")`, gọi `MockMvc.perform(...)`, assert bằng `andExpect(...)`.
- Reactive adapter chuyển thành `mockUser(...).roles("USER")`, gọi `WebTestClient.mutateWith(...)`, assert bằng `expectStatus(...)`.

Không ép hai adapters cùng nhận một kiểu `RequestPostProcessor`: WebTestClient mutators và MockMvc request post-processors không có chung type contract. Với security tests nhạy cảm, viết các phương thức test rõ ràng như M01–M11 thường dễ review hơn một abstraction dài chứa nhiều `if/else` và khó biết request đã dùng principal giả hay credentials thật.

### 14.1. Hai cột dùng để review migration

Khi review PR, có thể duy trì bảng:

| ID | Servlet test | Reactive test | Cùng observation? |
| --- | --- | --- | --- |
| M01 | `m01_publicIsAvailable` | `m01_publicIsAvailable` | `200`, body `public` |
| M02 | `m02_guestCannotReadPrivate` | `m02_guestCannotReadPrivate` | `401` |
| M03 | `m03_mockUserCanReadPrivate` | `m03_mockUserCanReadPrivate` | `200`, username |
| M04 | `m04_mockUserCannotReadAdmin` | `m04_mockUserCannotReadAdmin` | `403` |
| M05 | `m05_mockAdminCanReadAdmin` | `m05_mockAdminCanReadAdmin` | `200`, body `admin` |
| M06 | `m06_postWithoutCsrfIsForbidden` | `m06_postWithoutCsrfIsForbidden` | `403` |
| M07 | `m07_postWithCsrfIsCreated` | `m07_postWithCsrfIsCreated` | `201`, body `created` |
| M08–M11 | Basic credentials tests | Reactive Basic credentials tests | `401/200/403/200` |

Nếu chỉ có `M05 ADMIN 200` mà thiếu `M04 USER 403`, một lỗi thay `hasRole("ADMIN")` bằng `permitAll()` có thể không bị phát hiện. Nếu chỉ có `M04 USER 403` mà thiếu `M05 ADMIN 200`, một policy `denyAll()` có thể làm test xanh sai mục đích.

## 15. Bảng chẩn đoán lỗi sau khi chuyển sang WebTestClient

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `.with(user(...))` không compile | Servlet `RequestPostProcessor` không dùng với WebTestClient | Dùng `.mutateWith(mockUser(...))` |
| `.mutateWith(jwt())` không compile | `jwt()` là helper Servlet | Dùng Reactive `mockJwt()` |
| `springSecurity()` bị ambiguous | Import cả Servlet và Reactive setup helper | Chọn đúng class hoặc dùng fully qualified call |
| `mockUser()` không tạo identity | Chưa áp dụng `springSecurity()` hoặc client không bind WebFlux mock | Kiểm tra `bindToApplicationContext` và `SecurityWebFilterChain` |
| `@WithMockUser` không vào real HTTP | Test context không đi qua socket | Gửi Basic/Bearer/cookie thực |
| `@SpringBootTest(MOCK)` tạo Servlet context | Có `spring-boot-starter-web`, Boot chọn MVC | Kiểm tra web application type và dependencies |
| Không có `MockMvcResultMatchers` trong WebFlux test | Assertions thuộc Servlet | Dùng `expectStatus`, `expectBody`, `expectHeader` |
| USER nhận `200` ở admin | Rule `hasRole` bị thay đổi/không chạy | Xem security chain, test USER 403 + ADMIN 200 |
| ADMIN `POST` nhận `403` | Thiếu CSRF | Cấp token CSRF cho mock request, thêm ca đối chứng |
| Guest nhận `302` thay vì `401` | Form login entry point | Kiểm tra security config/`Location` |
| Basic đúng vẫn `401` | User store/encoder/credentials sai | Thử đúng/sai mật khẩu, xem server-side authentication |
| JWT mock `200`, Bearer thật `401` | Decoder/chữ ký/issuer/hạn không được mock test kiểm tra | Dùng JWS ký đúng/sai với decoder thật |
| OIDC principal bị cast lỗi | Dùng `mockUser` thay `mockOidcLogin` | Mock đúng loại authentication/principal |
| Test Reactive service xanh dù thiếu quyền | Không subscribe, bean không proxy hoặc method security chưa bật | Dùng `StepVerifier`, kiểm tra `@EnableReactiveMethodSecurity` |
| Test bị sai thứ tự | Dùng chung WebTestClient đã mutate, session/cookie hoặc fixture | Client/fixture riêng theo test |
| Test HTTP thật không thấy user mới tạo | Chưa commit transaction fixture | Seed và commit trước HTTP request |

Đừng sửa nhanh bằng `.anyExchange().permitAll()`, tắt filter chain hoặc tắt CSRF. Cách đó có thể “chữa” test nhưng làm mất chính chính sách mà bộ test cần bảo vệ.

## 16. Những lỗi phổ biến làm migration có vẻ xanh nhưng mất độ bao phủ

### 16.1. Chỉ chuyển ca dương

Nếu chỉ giữ test ADMIN `200`, không có ca USER `403` và guest `401`, bộ test không bảo vệ được ranh giới authorization. Một thay đổi mở route `permitAll()` có thể không làm test thất bại.

### 16.2. Nhầm `403` do CSRF với `403` do role

Ví dụ một test `POST` với USER thiếu role nhưng **cũng thiếu CSRF**. `403` có thể đến từ CSRF filter trước khi rule role chạy. Muốn chứng minh thiếu role, cung cấp CSRF hợp lệ trong cả ca ROLE_USER và ROLE_ADMIN, rồi so sánh.

### 16.3. Thay JWS ký thật bằng `mockJwt()`

Sau migration, `mockJwt()` cho `200` không chứng minh `ReactiveJwtDecoder` chấp nhận token thật hoặc chặn token ký sai. Hãy giữ test decoder/validator bằng Bearer JWS thật ở tầng integration.

### 16.4. Đổi hết test sang `RANDOM_PORT`

Không cần biến mọi mock authorization test thành test qua HTTP server thật. Việc đó làm suite chậm và có thể khiến người viết bỏ qua các ca âm. Giữ nhiều test policy nhanh trên mock WebFlux, kết hợp số lượng đủ của integration tests qua Basic/Bearer và HTTP thật khi cần kiểm tra network boundary.

### 16.5. Chỉ assert `exchange()` đã chạy

~~~java
@Test
void weakTest() {
    client.get().uri("/api/admin").exchange();
}
~~~

Test này không khẳng định status/body. `exchange()` tự chạy request, **không thay thế** `expectStatus()`. Cần assertion cụ thể để phát hiện policy bị mở hoặc bị khóa.

### 16.6. Chỉ kiểm tra dữ liệu do test tạo

~~~java
@Test
void meaninglessTest() {
    var roles = List.of("ROLE_ADMIN");
    assertTrue(roles.contains("ROLE_ADMIN"));
}
~~~

Đoạn trên không đi qua security chain. Một test có `mockUser().roles("ADMIN")` cũng chỉ kiểm tra principal giả nếu không gọi endpoint/service được bảo vệ và assert hành vi quan sát được.

## 17. CI checklist cho bài thực hành

Một pipeline sau khi chuyển stack cần kiểm tra:

1. **Dependency alignment:** `spring-security-test` đúng phiên bản Spring Security của ứng dụng.
2. **Application type:** Reactive tests chạy trên WebFlux context; không chỉ có WebTestClient trên classpath.
3. **Test discovery:** JUnit Jupiter tìm đủ M01–M11; không bị skip hoặc vô hiệu hóa.
4. **Filter chain:** WebFlux setup nạp `SecurityWebFilterChain`; Servlet baseline nạp `SecurityFilterChain`.
5. **Assertions:** mọi test đều kiểm tra status, body/headers hoặc side effects có liên quan.
6. **Negative cases:** guest, USER thiếu quyền, thiếu CSRF, password sai và token không hợp lệ (nếu dùng).
7. **Positive cases:** đủ quyền, CSRF đúng, password đúng và token hợp lệ.
8. **Principal type:** user, JWT, OAuth2/OIDC được mô phỏng bằng đúng helper và đúng loại principal.
9. **Transport:** integration tests qua socket gửi credentials/cookies thật thay vì mock configurer.
10. **Data isolation:** không dùng chung user fixture mutable, session/cookies hoặc clock khiến test phụ thuộc thứ tự.
11. **Không vô hiệu hóa bảo mật:** không tắt filters, CSRF hoặc chuyển `denyAll` thành `permitAll` chỉ để build xanh.
12. **Failure demonstration:** nếu đổi `hasRole("ADMIN")` thành `permitAll()`, test M04 phải thất bại; nếu đổi thành `denyAll()`, M05 phải thất bại.

Ví dụ chạy test bằng Gradle trong một dự án thật:

~~~bash
./gradlew test
~~~

Lệnh này chỉ mang tính hướng dẫn; trong bước viết Markdown hiện tại **không chạy Gradle/Python**. CI nên lưu report số test chạy/bị bỏ qua, failures và artifacts cần thiết. “BUILD SUCCESSFUL” mà không có test security được chạy không chứng minh migration thành công.

## 18. Bài tập mở rộng

### Bài 1 — Chuyển đúng bảy ca mock

Viết lại M01–M07 từ `MockMvc` sang `WebTestClient`. Giữ nguyên status và body assertions. Với mỗi ca, chỉ ra request post-processor Servlet nào đổi thành Reactive mutator nào; đánh dấu các ca không dùng identity giả.

### Bài 2 — Chứng minh không kiểm tra password bằng `mockUser()`

Chạy một test `mockUser("ghost")` vào `/api/private` và giải thích tại sao vẫn có thể `200` dù user store không có `ghost`. Gửi Basic `ghost` với password bất kỳ và assert `401`. Viết kết luận riêng cho policy test và authentication test.

### Bài 3 — Bảo vệ authorization bằng cả hai hướng

Ở `/api/admin`, viết test USER `403` và ADMIN `200` cho cả hai stack. Tạm thay `hasRole("ADMIN")` bằng `permitAll()` trong nhánh thực hành cô lập, quan sát ca nào thất bại; khôi phục rule.

### Bài 4 — Chẩn đoán `403` khi POST

Viết ca USER có CSRF nhưng thiếu quyền với một endpoint chỉ dành cho ADMIN; viết ca ADMIN có CSRF được phép; viết ca ADMIN thiếu CSRF bị từ chối. Giải thích nguyên nhân độc lập của hai response `403`.

### Bài 5 — JWT và scopes

Với endpoint `/api/reports` yêu cầu `SCOPE_reports.read`, viết policy tests dùng `jwt()`/`mockJwt()` với scope đúng và sai. Sau đó thiết kế test Bearer JWS ký thật qua decoder, gồm token hợp lệ, sai chữ ký và hết hạn.

### Bài 6 — OIDC principal và OAuth2 token exchange

Viết test Servlet `oidcLogin()` và Reactive `mockOidcLogin()` để assert body từ `OidcUser`, thay vì chỉ assert status. Với OAuth2 Client, chỉ ra vì sao `oauth2Client()`/`mockOAuth2Client()` không chứng minh token endpoint đã nhận POST, rồi thiết kế một integration test quan sát request ấy.

### Bài 7 — Mock HTTP và HTTP thật

Chạy M08/M09 với `WebTestClient.bindToApplicationContext(...)` và sau đó `bindToServer()` với `RANDOM_PORT`. Giải thích hai test giống nhau về authentication mechanism nhưng khác nhau về network boundary. Không dùng `mockUser()` làm credentials qua socket.

### Bài 8 — Tự thiết kế cổng chất lượng CI

Tạo bảng theo dõi M01–M11 với cột Servlet test, Reactive test, status, assertions và ghi chú mục tiêu. Định nghĩa điều kiện CI fail nếu có ca M04/M05 bị skip, test không có assertion hoặc authentication integration test bị thay bằng mock decoder.

## 19. Checklist tự đánh giá

- [ ] Có ma trận yêu cầu độc lập framework trước khi đổi mã.
- [ ] Đã phân biệt `SecurityMockMvcRequestPostProcessors` và `SecurityMockServerConfigurers`.
- [ ] WebFlux test dùng `WebTestClient` gắn đúng mock application context và `springSecurity()`.
- [ ] Đã xác minh security chain đúng stack được nạp, không tắt filter.
- [ ] Mọi ca M01–M11 được bảo toàn hoặc thay đổi theo quyết định có ghi rõ.
- [ ] Không mất ca guest, USER thiếu quyền, ADMIN đủ quyền, thiếu/đủ CSRF.
- [ ] `roles("ADMIN")` và `authorities("SCOPE_...")` không bị nhầm.
- [ ] Các ca Basic credentials dùng header thật, không dùng `mockUser()` thay cho password.
- [ ] Mỗi `200` có assertion body hoặc bằng chứng hành vi hữu ích khi cần.
- [ ] Các ca JWT mock được phân loại là policy tests, không ghi thành token validation tests.
- [ ] Nếu dùng OAuth2/OIDC, loại principal và giới hạn của helper được diễn giải đúng.
- [ ] Reactive method security có subscriber/`StepVerifier` để kiểm tra kết quả.
- [ ] Test `RANDOM_PORT` gửi credentials/token/cookies qua HTTP thật, không chuyển test SecurityContext qua socket.
- [ ] Fixture, cookies và transactions được cô lập khi chạy CI/song song.
- [ ] CI có test discovery, report skipped/failures và một cặp âm/dương cho policy quan trọng.

## 20. Kết luận

Chuyển một ma trận Spring Security Test từ `MockMvc` sang `WebTestClient` thành công nghĩa là **giữ nguyên hành vi bảo mật được chứng minh**, không chỉ chuyển tên hàm. Ở Servlet, request post-processors như `user()` và `csrf()` được gắn bằng `with(...)`. Ở Reactive mock WebFlux, dùng `mockUser()`, `csrf()` và `mutateWith(...)` cùng setup `springSecurity()` phù hợp.

Test principal giả kiểm tra **policy sau khi có authentication**; test HTTP Basic/Bearer kiểm tra **cơ chế tạo authentication**; `bindToServer()` kiểm tra thêm **HTTP network boundary**. Ba kết luận này bổ trợ nhau nhưng không thể thay thế lẫn nhau.

Bộ kiểm thử chuyển đổi đáng tin phải giữ cả **ca chấp nhận và ca từ chối**: guest `401`, USER `403`, ADMIN `200`, POST thiếu/đủ CSRF `403/201`, password sai/đúng `401/200`. Sau đó mới bổ sung JWT/OAuth2/OIDC và method-security scenarios theo cơ chế thật của dự án.

## 21. Tài liệu tham khảo

- [Spring Security — Servlet MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): cấu hình Spring Security cho MockMvc.
- [Spring Security — Servlet MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user()`, `httpBasic()` và context giả.
- [Spring Security — Servlet MockMvc OAuth2](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, `oauth2Login()`, `oidcLogin()`, `oauth2Client()`.
- [Spring Security — Reactive Web Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `WebTestClient` và `springSecurity()`.
- [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()` và các helper authentication.
- [Spring Security — Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `csrf()` trên mock WebFlux.
- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOAuth2Login()` và `mockOidcLogin()`.
- [Spring Security — Reactive Method Testing](https://docs.spring.io/spring-security/reference/reactive/test/method.html): method security và `StepVerifier`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToApplicationContext()`, `bindToServer()` và assertions.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc` và `RANDOM_PORT`.
