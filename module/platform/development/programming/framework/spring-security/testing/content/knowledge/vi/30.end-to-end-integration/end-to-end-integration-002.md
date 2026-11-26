# Gửi thông tin xác thực thật qua HTTP thay vì chỉ đặt `SecurityContext` của test

## 1. Vấn đề cốt lõi: test xanh chưa chắc đã kiểm tra đăng nhập

Giả sử API `GET /api/private` chỉ cho phép người dùng đã xác thực truy cập. Một test dùng Spring Security Test:

~~~java
mockMvc.perform(get("/api/private")
        .with(user("reader").roles("USER")))
    .andExpect(status().isOk());
~~~

Kết quả `200 OK` cho biết hệ thống **cho phép một authentication giả mang role `USER`**. Nó chưa chứng minh mật khẩu đã được kiểm tra, authentication manager thật đã chạy, JWT đã được giải mã hay trình duyệt đã hoàn tất OAuth2/OIDC login.

Tương tự, với WebFlux:

~~~java
webTestClient
    .mutateWith(mockUser("reader").roles("USER"))
    .get()
    .uri("/api/private")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là bài test phân quyền hợp lệ, nhưng principal đã được **đặt sẵn**. Nếu cấu hình `PasswordEncoder` hoặc `ReactiveJwtDecoder` đang sai, ca này vẫn có thể xanh.

Chủ đề **Tích hợp đầu cuối** trong module `SPRING_SECURITY_TESTING` đòi hỏi người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng Spring Security Test trên Servlet và Reactive. Bài này giải thích cách **gửi credentials thật trong HTTP request của test** và quan sát kết quả từ các thành phần authentication thực, thay vì chỉ đặt `SecurityContext`.

Kết thúc bài, bạn có thể:

1. Phân biệt test dùng `@WithMockUser`/`user()`/`mockJwt()` với test truyền `Authorization` header hoặc login form.
2. Phân biệt request **HTTP mô phỏng** trong `MockMvc` với request **qua TCP/HTTP thật** trong `@SpringBootTest(RANDOM_PORT)`.
3. Dùng HTTP Basic kiểm chứng cả password đúng, password sai, không có credentials và người dùng thiếu quyền.
4. Kiểm tra JWT Bearer được ký thật bằng decoder/validator thật, thay vì sử dụng `jwt()` hoặc `mockJwt()`.
5. Xác định khi nào phải tích hợp OAuth2/OIDC provider, cookie/session và CSRF.
6. Đọc đúng ý nghĩa của `200`, `401`, `403` và redirect `302` theo cấu hình bảo mật.

## 2. Hai trục độc lập: nguồn danh tính và đường vận chuyển request

Có **hai câu hỏi riêng** mà mỗi bài kiểm thử cần trả lời.

**Trục A — Authentication đến từ đâu?**

- **Được đặt sẵn**: `@WithMockUser`, `SecurityMockMvcRequestPostProcessors.user()`, `jwt()` hoặc `WebTestClient.mutateWith(mockUser()/mockJwt())`.
- **Được hệ thống xác thực từ credentials**: gửi HTTP Basic username/password, form login, cookie phiên đã được tạo bởi login thật, hoặc Bearer JWS qua decoder.

**Trục B — Request đi qua đâu?**

- **Mock server trong tiến trình test**: `MockMvc` cho Servlet hoặc `WebTestClient.bindToApplicationContext(...)` cho WebFlux.
- **Embedded HTTP server thật**: `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `TestRestTemplate`/`WebTestClient.bindToServer()`.

Hai trục tạo ra ma trận:

| Authentication | Request transport | Công cụ | Kết luận hợp lệ |
| --- | --- | --- | --- |
| Principal giả | Mock Servlet | `MockMvc.with(user())`, `@WithMockUser` | Policy chấp nhận/từ chối principal giả |
| Credentials trong request | Mock Servlet | `MockMvc.with(httpBasic(...))` hoặc header `Authorization` | Servlet security filters và authentication provider thật được thử; **không có socket** |
| Principal giả | Mock WebFlux | `mockUser()`, `mockJwt()` | Reactive policy với context giả |
| Credentials trong request | Mock WebFlux | WebTestClient gửi Basic/Bearer header và không dùng mock principal | Reactive filters, manager/decoder được thử trong application context |
| Credentials trong request | HTTP server thật | `RANDOM_PORT` + HTTP client | Authentication path cùng network HTTP boundary trong phạm vi test |
| Principal giả ở thread test | HTTP server thật | `@WithMockUser` + `bindToServer()` | **Không tự truyền** principal qua socket; không thay thế credentials |

**Nhận định quan trọng:** không bắt buộc phải mở cổng mạng để kiểm tra password hoặc JWT decoder. `MockMvc` gửi một request HTTP **mô phỏng** qua Servlet filter chain có thể kiểm tra authentication thật. Ngược lại, mở HTTP server nhưng chỉ kiểm tra endpoint công khai chưa chứng minh cơ chế xác thực.

~~~mermaid
flowchart TD
    A["Bắt đầu kiểm thử endpoint bảo vệ"] --> B{"Test có đặt sẵn Authentication?"}
    B -- "Có" --> C["SecurityContext giả"]
    C --> D["Authorization: role/scope/policy"]
    B -- "Không" --> E["HTTP request chứa credentials"]
    E --> F["Security filters"]
    F --> G["AuthenticationManager / ReactiveAuthenticationManager / JwtDecoder"]
    G -- "Không hợp lệ" --> H["401 hoặc login failure"]
    G -- "Hợp lệ" --> I["SecurityContext từ authentication thật"]
    I --> D
    D -- "Thiếu quyền" --> J["403"]
    D -- "Đủ quyền" --> K["200"]
    L["MockMvc / WebTestClient mock"] -. "Không mở socket" .-> E
    M["RANDOM_PORT / HTTP client"] -. "Có socket" .-> E
~~~

## 3. Ứng dụng Servlet nhỏ dùng làm mẫu

Ví dụ dùng Spring Boot Servlet, HTTP Basic và hai người dùng fixture. Chúng ta cố tình dùng những đường `GET` để tách kiểm tra authentication/authorization khỏi CSRF trên các phương thức ghi dữ liệu.

### 3.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ ứng với Spring Boot 3.x / Spring Security 6.x, Java 17+. API và package có thể thay đổi theo major version; dùng phiên bản dependency do dự án quản lý thay vì sao chép phiên bản ngẫu nhiên.

### 3.2. Endpoint công khai và endpoint cần quyền

~~~java
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class DemoController {

    @GetMapping("/api/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/api/private")
    Map<String, String> privateInfo(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }
}
~~~

### 3.3. Security filter chain và user store

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class DemoHttpSecurity {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/public").permitAll()
                    .requestMatchers("/api/admin").hasRole("ADMIN")
                    .requestMatchers("/api/private").authenticated()
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("correct-password"))
                .roles("USER")
                .build(),
            User.withUsername("administrator")
                .password(encoder.encode("admin-password"))
                .roles("ADMIN")
                .build());
    }
}
~~~

Giả sử các lớp ở trên thuộc ứng dụng Spring Boot có `@SpringBootApplication` và được nạp trong test context. Đây là user store dùng **chỉ cho môi trường ví dụ**, không sử dụng usernames/passwords mẫu trong production.

Khi gửi Basic credentials, Spring Security chuyển thông tin từ header vào authentication request, sau đó provider kiểm tra người dùng và mật khẩu bằng `UserDetailsService` và `PasswordEncoder`. Người dùng `reader` được xác thực nhưng không có `ROLE_ADMIN`; vì thế kết quả của `/api/admin` phải là `403`.

Không cần tắt CSRF để kiểm tra các đường `GET`. Nếu bổ sung `POST`/`PUT`/`DELETE`, phải đánh giá CSRF theo phương thức xác thực của ứng dụng; xem mục 10.

## 4. Test giả lập: hữu ích nhưng không kiểm tra password

Một ca test trong ứng dụng mẫu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MockPrincipalAuthorizationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void inventedUserCanReachPrivateEndpoint() throws Exception {
        mockMvc.perform(get("/api/private")
                    .with(user("does-not-exist").roles("USER")))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.username")
                       .value("does-not-exist"));
    }
}
~~~

`does-not-exist` **không có trong `UserDetailsService`**. Test vẫn có thể cho `200`, bởi `user(...)` đặt sẵn test authentication cho request. Điều này chứng minh rất rõ rằng ca test không cần tra cứu username hay xác minh password.

Các helper có ý nghĩa tương tự:

- `@WithMockUser(username = "reader", roles = "USER")`: thiết lập authentication giả qua Spring Test security context.
- `SecurityMockMvcRequestPostProcessors.user(...)`: thêm người dùng giả cho request MockMvc cụ thể.
- `SecurityMockMvcRequestPostProcessors.jwt()`: giả lập JWT authentication, không xác minh JWS signature.
- `SecurityMockMvcRequestPostProcessors.oauth2Login()/oidcLogin()`: giả lập trạng thái sau login, không chạy authorization-code callback.
- Reactive `mockUser()/mockJwt()/mockOidcLogin()`: đưa authentication giả vào Reactive test security context.

Các helper này **không xấu**. Chúng rất phù hợp cho test authorization nhanh và ổn định, nhưng kết luận phải giới hạn ở **quy tắc của ứng dụng khi đã có danh tính**.

## 5. Cũng dùng `MockMvc` nhưng gửi HTTP Basic credentials thật

Để test authentication provider, thay `with(user(...))` bằng `with(httpBasic(...))`. Post-processor `httpBasic` **tạo header HTTP Basic**; nó không tự công nhận người dùng đã xác thực. Với security filters được bật, request phải đi qua authentication path thật:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;

@SpringBootTest
@AutoConfigureMockMvc
class MockMvcBasicAuthenticationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rightPasswordAuthenticates() throws Exception {
        mockMvc.perform(get("/api/private")
                    .with(httpBasic("reader", "correct-password")))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/api/private")
                    .with(httpBasic("reader", "wrong-password")))
               .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCredentialsAreRejected() throws Exception {
        mockMvc.perform(get("/api/private"))
               .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsForbidden()
            throws Exception {
        mockMvc.perform(get("/api/admin")
                    .with(httpBasic("reader", "correct-password")))
               .andExpect(status().isForbidden());
    }

    @Test
    void adminPasswordAndAuthorityBothWork()
            throws Exception {
        mockMvc.perform(get("/api/admin")
                    .with(httpBasic(
                        "administrator", "admin-password")))
               .andExpect(status().isOk());
    }
}
~~~

Cần các imports của JUnit, `@SpringBootTest`, `@AutoConfigureMockMvc`, `@Autowired`, `MockMvc` cùng `get` và `MockMvcResultMatchers` như mục 4.

### 5.1. Bằng chứng thu được

| Request | Authentication | Authorization | Kỳ vọng |
| --- | --- | --- | --- |
| Không header Basic | Chưa có user | Endpoint đòi authentication | `401` |
| Basic username đúng, password sai | Authentication manager từ chối | Chưa có principal hợp lệ | `401` |
| Basic `reader`, password đúng | Tra user và so sánh password thành công | `authenticated()` | `200` |
| Basic `reader`, password đúng | Xác thực thành công | Thiếu `ROLE_ADMIN` | `403` |
| Basic `administrator`, password đúng | Xác thực thành công | Có `ROLE_ADMIN` | `200` |

Test kiểu này mạnh hơn `with(user(...))` ở ranh giới **xác minh password và tải user**. Tuy nhiên, `MockMvc` vẫn xử lý HTTP mô phỏng trong tiến trình, **chưa chứng minh kết nối TCP, embedded server, reverse proxy hay TLS hoạt động**.

**Điều kiện quan trọng:** `@AutoConfigureMockMvc` phải giữ security filters, và application context phải nạp `SecurityFilterChain` cùng `UserDetailsService` thật mà test đang muốn kiểm tra. Đừng vô tình dùng `@AutoConfigureMockMvc(addFilters = false)`, mock `AuthenticationManager` thành luôn chấp nhận hoặc gắn thêm `@WithMockUser` trong ca kiểm tra password.

## 6. Servlet integration qua HTTP server thật với `RANDOM_PORT`

Khi mục tiêu gồm HTTP transport ngoài tiến trình xử lý mock, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`. Với Spring Boot Servlet, `TestRestTemplate` tiện cho các ca status/headers vì mặc định nó không ném exception chỉ vì HTTP trả `4xx`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletRealHttpBasicTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void missingCredentialsReturn401() {
        ResponseEntity<String> result =
                http.getForEntity("/api/private", String.class);
        assertEquals(HttpStatus.UNAUTHORIZED, result.getStatusCode());
    }

    @Test
    void wrongPasswordReturns401() {
        ResponseEntity<String> result =
                http.withBasicAuth("reader", "wrong-password")
                    .getForEntity("/api/private", String.class);
        assertEquals(HttpStatus.UNAUTHORIZED, result.getStatusCode());
    }

    @Test
    void validPasswordReturns200() {
        ResponseEntity<String> result =
                http.withBasicAuth("reader", "correct-password")
                    .getForEntity("/api/private", String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
    }

    @Test
    void validUserWithoutRoleReturns403() {
        ResponseEntity<String> result =
                http.withBasicAuth("reader", "correct-password")
                    .getForEntity("/api/admin", String.class);
        assertEquals(HttpStatus.FORBIDDEN, result.getStatusCode());
    }

    @Test
    void validAdminCanAccessAdminEndpoint() {
        ResponseEntity<String> result =
                http.withBasicAuth("administrator", "admin-password")
                    .getForEntity("/api/admin", String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
    }
}
~~~

`RANDOM_PORT` khởi động embedded Servlet server trên cổng được cấp động. `TestRestTemplate` được Spring Boot test cấu hình để gửi request đến server ấy. Username/password ở đây **thực sự đi qua HTTP header**, được server kiểm tra rồi mới trả kết quả. Các fixture vẫn nằm trong ứng dụng test; không có cơ sở để suy ra password của tài khoản production hoặc hạ tầng bên ngoài đã được kiểm tra.

### 6.1. Tại sao không dùng `@WithMockUser` trên test HTTP thật?

`@WithMockUser` thiết lập security context cho **môi trường thực thi test**, không phải một protocol để truyền principal từ client tới server qua socket. Một test kiểu:

~~~java
@Test
@WithMockUser(username = "reader", roles = "USER")
void mockUserDoesNotTravelThroughHttp() {
    ResponseEntity<String> result =
            http.getForEntity("/api/private", String.class);
    assertEquals(HttpStatus.UNAUTHORIZED, result.getStatusCode());
}
~~~

vẫn mong đợi `401` vì request của `TestRestTemplate` **không gửi credentials**. Nếu test chỉ xanh nhờ một session/cookie được tái sử dụng từ trước, cần cô lập client state và kiểm tra lại.

**Lưu ý:** server chạy trong cùng ứng dụng test nhưng ở HTTP request thread/connection riêng. “HTTP thật” không đồng nghĩa hạ tầng sản xuất hoàn chỉnh; nó có nghĩa đã kiểm tra network boundary tới embedded server đang chạy.

## 7. Dùng `WebTestClient.bindToServer()` cho Servlet hoặc WebFlux

`WebTestClient` là HTTP client kiểm thử; khi dùng `bindToServer()` nó có thể gọi cả **Servlet server** lẫn **Reactive server** qua socket. Để sử dụng `WebTestClient` trong một dự án Servlet, cần có Spring WebFlux test client trên test classpath (ví dụ thêm `spring-boot-starter-webflux` với scope `testImplementation` theo version Boot phù hợp).

~~~groovy
// Chỉ cần khi test(Servlet) muốn dùng WebTestClient
// và project chưa có đủ các dependency cho client này.
testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
~~~

Ví dụ cho HTTP Basic:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpWebTestClientTests {

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
    void basicAuthenticationReallyRuns() {
        http.get()
            .uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "correct-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void wrongPasswordIsRejected() {
        http.get()
            .uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingAdminRoleIsForbidden() {
        http.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "correct-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

`WebTestClient.bindToServer()` **không phải** `WebTestClient.bindToApplicationContext(...)`. Ở chế độ server thật, các mutators như `mockUser()` hoặc `mockJwt()` dành cho mock server không phải cách truyền credentials sang embedded server; phải gửi Basic, Bearer, cookie hoặc form data bằng HTTP.

Điều tương tự áp dụng với ứng dụng WebFlux. Thay `DemoHttpSecurity` của Servlet bằng `SecurityWebFilterChain` và `MapReactiveUserDetailsService` tương ứng, rồi chạy `@SpringBootTest(RANDOM_PORT)` với `bindToServer()`. Với HTTP Basic, các headers/expectations ở ví dụ trên vẫn dùng được.

## 8. Đối chứng trong WebFlux: gửi Basic header qua mock WebTestClient

Để kiểm tra Reactive authentication manager mà không mở socket, dùng `WebTestClient` gắn vào WebFlux application context và gửi header thật:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();

client.get()
      .uri("/api/private")
      .headers(h -> h.setBasicAuth("reader", "correct-password"))
      .exchange()
      .expectStatus().isOk();

client.get()
      .uri("/api/private")
      .headers(h -> h.setBasicAuth("reader", "wrong-password"))
      .exchange()
      .expectStatus().isUnauthorized();
~~~

Đoạn này giả định `applicationContext` là **WebFlux context**, có `SecurityWebFilterChain` bật HTTP Basic và `ReactiveAuthenticationManager`/`ReactiveUserDetailsService` thật, cùng endpoint `/api/private`. Nó không thể dùng nguyên xi `SecurityFilterChain` Servlet ở mục 3.

Nếu thay bằng:

~~~java
client.mutateWith(mockUser("reader").roles("USER"))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

thì ca đó quay về **kiểm thử authorization với identity giả**, không xác minh password. Tên class `WebTestClient` không quyết định nội dung kiểm thử: **cách cung cấp authentication** mới là điểm khác biệt.

## 9. JWT Bearer: cần JWS thật, decoder thật và cả ca âm

Khi ứng dụng dùng OAuth2 Resource Server, không thể lấy `mockJwt()` hoặc `SecurityMockMvcRequestPostProcessors.jwt()` làm bằng chứng xác minh signature/hạn token. Để kiểm tra đường đi thật:

1. Cấu hình `JwtDecoder` hoặc `ReactiveJwtDecoder` cùng bộ khóa/validator test đáng tin cậy.
2. Tạo JWT **được ký thật** bằng khóa test; đặt claims `sub`, `iss`, `exp` và `scope`.
3. Gửi `Authorization: Bearer <signed-jws>` qua HTTP client, **không gắn `mockJwt()`/`jwt()`** vào cùng request.
4. Kiểm tra token hợp lệ được chấp nhận, token sai chữ ký hoặc đã hết hạn bị từ chối; token hợp lệ nhưng thiếu scope dẫn đến `403` nếu rule yêu cầu scope.

### 9.1. Cấu hình Resource Server Servlet cho endpoint báo cáo

Ví dụ cấu hình riêng **thay thế** HTTP Basic configuration ở mục 3 trong một test context chuyên cho JWT:

~~~java
@Bean
SecurityFilterChain reportJwtChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/reports")
                .hasAuthority("SCOPE_reports.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Ứng dụng cần thêm `spring-boot-starter-oauth2-resource-server`. Trong test context phải có `JwtDecoder` thật và endpoint `GET /api/reports`; dùng controller tối giản trả `200` và body theo nhu cầu. Không đăng ký đồng thời hai security chains trùng path mà không kiểm soát `@Order`/`securityMatcher`.

### 9.2. Khóa RSA thử nghiệm, encoder và decoder

Ví dụ sử dụng một cặp RSA 2048-bit chỉ tạo trong test; decoder chỉ tin khóa công khai của cặp này:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@TestConfiguration(proxyBeanMethods = false)
class JwtTestKeys {
    private static final KeyPair PAIR = generateKeyPair();

    private static KeyPair generateKeyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (Exception e) {
            throw new IllegalStateException("Cannot create test key", e);
        }
    }

    @Bean
    JwtEncoder jwtEncoder() {
        RSAKey signingKey = new RSAKey.Builder(
                (RSAPublicKey) PAIR.getPublic())
            .privateKey((RSAPrivateKey) PAIR.getPrivate())
            .keyID("integration-key")
            .build();
        return new NimbusJwtEncoder(
                new ImmutableJWKSet<>(new JWKSet(signingKey)));
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey((RSAPublicKey) PAIR.getPublic())
                .build();
        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer(
                    "https://issuer.example.test"));
        return decoder;
    }
}
~~~

Lớp `JwtTestKeys` cần được import vào test context, ví dụ `@Import(JwtTestKeys.class)`. Key được tạo lúc test chạy, không lưu private key vào repository. Các package Nimbus và Spring OAuth2 trong ví dụ đến từ dependency resource server/JOSE tương ứng.

### 9.3. Ký một token và gửi qua HTTP

~~~java
import java.time.Instant;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;

static String signedToken(
        JwtEncoder encoder, Instant expiresAt, String scope) {
    Instant now = Instant.now();

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer("https://issuer.example.test")
        .subject("reader")
        .issuedAt(now.minusSeconds(3600))
        .expiresAt(expiresAt)
        .claim("scope", scope)
        .build();

    JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("integration-key")
        .build();

    return encoder.encode(JwtEncoderParameters.from(header, claims))
            .getTokenValue();
}
~~~

Ở một `@SpringBootTest(RANDOM_PORT)` đã import `JwtTestKeys` và dùng **resource-server chain**, test có thể làm:

~~~java
@Autowired
JwtEncoder encoder;

@Test
void signedJwtWithReadScopeIsAccepted() {
    String jwt = signedToken(
        encoder, Instant.now().plusSeconds(600), "reports.read");

    http.get()
        .uri("/api/reports")
        .headers(h -> h.setBearerAuth(jwt))
        .exchange()
        .expectStatus().isOk();
}

@Test
void expiredSignedJwtIsRejected() {
    String jwt = signedToken(
        encoder, Instant.now().minusSeconds(600), "reports.read");

    http.get()
        .uri("/api/reports")
        .headers(h -> h.setBearerAuth(jwt))
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void signedJwtWithoutReadScopeIsForbidden() {
    String jwt = signedToken(
        encoder, Instant.now().plusSeconds(600), "profile");

    http.get()
        .uri("/api/reports")
        .headers(h -> h.setBearerAuth(jwt))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Ở đây `http` là `WebTestClient.bindToServer()` được cấu hình như mục 7. Test hết hạn đặt `exp` lùi 600 giây để vượt qua khoảng clock skew thông thường; issuer đúng để ca hết hạn chỉ thất bại vì thời gian. Với token sai chữ ký, tạo token từ **một cặp khóa RSA khác** nhưng vẫn gửi tới decoder chỉ tin khóa `PAIR` ở trên; kỳ vọng `401`.

**Lưu ý phạm vi:** encoder tạo token và decoder xác minh token là **implementation thực**, nhưng khóa/issuer là fixture của môi trường test. Điều này chứng minh validation chạy trong test context, không chứng minh authorization server sản xuất thực sự cấp token hoặc cấu hình production trust store/JWKS đúng.

## 10. Form login, cookie/session và CSRF qua HTTP thật

Nếu ứng dụng dùng form login, HTTP Basic không mô phỏng đầy đủ giao thức của ứng dụng. Cần test các bước đúng:

1. `GET /login` để nhận trang login và (nếu CSRF bật) token CSRF theo cấu hình.
2. Lưu session cookie từ response; lấy token CSRF hợp lệ từ HTML, cookie hoặc endpoint do ứng dụng thiết kế.
3. `POST /login` gửi username/password, CSRF token và session cookie như browser thật.
4. Kiểm tra response success/failure, redirect, cookie session mới nếu cấu hình tương ứng.
5. Dùng cookie được cấp truy cập endpoint cần đăng nhập; thử không có cookie và cookie sau logout.
6. `POST /logout` với CSRF hợp lệ theo policy; dùng lại session cũ và xác nhận bị từ chối.

Mã HTTP khác theo configuration. Form login thường trả **`302`** hướng đến trang login khi chưa xác thực, không nhất thiết `401`. Khi sai password, có thể redirect về `/login?error`; khi thiếu CSRF, có thể nhận `403` **trước khi kiểm tra username/password**.

### 10.1. `with(csrf())` là helper mô phỏng, không phải token đã được browser lấy

~~~java
mockMvc.perform(post("/api/notes")
        .with(user("reader"))
        .with(csrf()))
    .andExpect(status().isOk());
~~~

Đây là một ca **mock request** có authentication giả và CSRF token hợp lệ do Spring Security Test cung cấp. Nó kiểm tra CSRF/authorization phía server khi request có đủ input, nhưng không chứng minh browser đã lấy được CSRF token và gửi lại cùng cookie/session.

Đối với `RANDOM_PORT`, cần truyền **cookie và token thật từ response trước**. Không áp dụng `csrf()` mock mutator rồi cho rằng nó sẽ tự biến thành trình duyệt đang tương tác qua socket.

### 10.2. Khi nào được tắt CSRF?

Không mặc định API là stateless thì tắt CSRF là an toàn. Cần xét liệu trình duyệt có **tự động gắn** credentials (session cookie, Basic authentication đã cache hoặc cơ chế tương đương) khi một trang khác kích hoạt request hay không. API chỉ nhận Bearer header do ứng dụng client chủ động gắn và không dựa trên credentials tự động của browser có threat model khác, nhưng vẫn phải đánh giá cụ thể.

Một test `POST` thiếu CSRF trả `403` không chứng minh password sai; hãy có ca đối chứng cung cấp CSRF hợp lệ rồi mới diễn giải lỗi authentication.

## 11. OAuth2/OIDC Login cần IdP thử nghiệm, không chỉ `oidcLogin()`

`oauth2Login()` và `oidcLogin()` trong `spring-security-test` tạo trạng thái đã đăng nhập giả để test controller và authorization. Để chứng minh **login protocol** hoạt động, cần integration test với authorization server/Identity Provider thử nghiệm hoặc môi trường tích hợp được kiểm soát:

| Bước | Dấu hiệu cần kiểm chứng |
| --- | --- |
| Bắt đầu OAuth2 login | HTTP redirect đến đúng authorization endpoint, `client_id`, `redirect_uri`, `scope`, `state` |
| Nhận callback | `state` khớp request đã lưu, code được xử lý đúng |
| Token exchange | Có HTTP POST thật đến token endpoint với `grant_type=authorization_code`, `code`, `redirect_uri`, client authentication/PKCE thích hợp |
| Xác minh OIDC | ID token signature, issuer, audience, `exp`, `nonce` và các ràng buộc cần thiết |
| Dựng principal | UserInfo/claims được ánh xạ chính xác; chỉ cấp authorities đáng tin |
| Session/lifecycle | Cookie, session, logout và các trường hợp thất bại đúng hợp đồng |

Một test chỉ có:

~~~java
mockMvc.perform(get("/api/me").with(oidcLogin()))
    .andExpect(status().isOk());
~~~

**chưa chạy** các bước trên. Nó rất hữu ích để kiểm tra endpoint xử lý `OidcUser` giả ra sao, nhưng không phải bằng chứng ID token đã được ký hoặc nonce đã khớp.

Với OAuth2 Client cấp access token cho API downstream, cần kiểm tra HTTP token endpoint thật của test server và Bearer header gửi đi; một `OAuth2AuthorizedClient` giả được đặt trước cũng không chứng minh token đã được trao đổi đúng.

## 12. Vấn đề dữ liệu và cô lập trong test HTTP thật

Test tích hợp HTTP khác test gọi bean trực tiếp ở chỗ request được server xử lý trong **ngữ cảnh và transaction riêng**. Những lỗi thường gặp:

- **Fixture chưa commit:** test `@Transactional` tạo user trong transaction của JUnit rồi gọi server qua `RANDOM_PORT`. Server không thấy user chưa commit theo isolation thông thường → test sai mật khẩu `401` dù dữ liệu trông đã có trong test.
- **Session/cookie rò rỉ:** một HTTP client dùng lại cookie giữa các tests khiến request không credentials vẫn có authentication.
- **Dùng chung username mutable:** test A thay quyền `reader` trong khi test B đang thực thi, gây lỗi không ổn định.
- **Mock thay thành phần cần test:** `@MockBean AuthenticationManager` hoặc `JwtDecoder` trả sẵn authentication/token có thể làm test xanh mà không kiểm tra password hoặc signature.
- **Test vô tình chạm IdP bên ngoài:** OAuth2/JWT config trỏ tới môi trường thật thay vì fixture ổn định, khiến test chập chờn và có nguy cơ tác động hệ thống.

Hướng thực hành:

1. Tạo user, authority và key fixtures **trước HTTP request**, đã commit nếu server dùng transaction khác.
2. Dùng test database, ID/username riêng và cleanup theo cơ chế phù hợp. Tránh dùng secrets hoặc tài khoản production.
3. Tách test authentication provider, authorization policy và token validation để chỉ rõ lỗi nằm ở đâu.
4. Dùng `RANDOM_PORT` để tránh xung đột cổng khi chạy CI.
5. Không ghi password, API key, JWT, cookie session hoặc client secret vào logs/test report.
6. Với test phụ thuộc đồng hồ, dùng clock cố định hoặc timestamps cách xa boundary/clock skew.
7. Với form/session, chủ động giữ hoặc bỏ cookie thay vì giả định client có cookie jar mặc định.
8. Với JSON response, assert thêm nội dung/ngữ cảnh người dùng để tránh false positive do endpoint khác cũng trả `200`.

**Đặc biệt:** `@WithUserDetails` trong test thread tạo `SecurityContext` từ `UserDetailsService`; nó cũng không tự truyền identity qua HTTP socket của `RANDOM_PORT`. Khi muốn kiểm chứng login thật, gửi credentials qua client.

## 13. Hiểu `200`, `401`, `403`, `302` theo đúng security chain

| Kết quả | Giải thích thường gặp | Cần xác minh thêm |
| --- | --- | --- |
| `200 OK` | Request qua authentication và authorization hoặc endpoint `permitAll` | Có thật sự đi qua auth mechanism muốn test? Principal có đúng không? |
| `401 Unauthorized` | Basic/Bearer cần xác thực; credentials thiếu/sai hoặc JWT invalid | `WWW-Authenticate`, loại entry point, lỗi decoder/provider |
| `403 Forbidden` | Đã xác thực nhưng thiếu quyền; **hoặc** CSRF bị từ chối | Phân biệt principal/authorities và CSRF |
| `302 Found` | Form login/OAuth2 bắt đầu redirect hoặc login failure redirect | Kiểm tra `Location` và cookie/session |
| `5xx` | Lỗi application hoặc hạ tầng | Không coi là kết quả authentication/authorization thành công |

Không viết test “mọi guest phải nhận 401” mà không xét entry point. Ứng dụng dùng form login có thể trả redirect `302`; ứng dụng dùng nhiều security chains có thể cho những path khác nhau hành vi khác nhau.

## 14. Những ngộ nhận dễ làm bộ test bảo mật mất giá trị

| Ngộ nhận | Vấn đề | Cách kiểm chứng |
| --- | --- | --- |
| `@WithMockUser` nhận `200` nên password đúng | Không có password authentication | Gửi Basic/form credentials đúng và sai |
| `MockMvc` không mở port nên không kiểm tra được authentication thật | Nhầm transport và nguồn identity | Gửi `httpBasic()` qua Servlet filters |
| `RANDOM_PORT` tự bảo đảm mọi cơ chế xác thực đúng | Có socket nhưng chưa chắc chạy decoder/provider cần kiểm tra | Gửi credentials/token thật và kiểm tra ca âm |
| `jwt()`/`mockJwt()` có claim `exp` nên đã kiểm tra hết hạn | Helper giả authentication | Gửi JWS thật qua decoder/validator |
| `oidcLogin()` chứng minh ID token được xác minh | Không có IdP/callback | Test OIDC flow, chữ ký, issuer, audience, nonce |
| Có `200` với token hợp lệ là đủ | Decoder có thể luôn chấp nhận | Thêm token sai chữ ký/hết hạn và thiếu scope |
| Password sai nhận `401` là đủ | Provider có thể chặn mọi request | Thêm password đúng nhận `200` |
| `403` luôn do thiếu role | Có thể thiếu CSRF | Test CSRF riêng bằng token hợp lệ |
| `@WithMockUser` sang được HTTP server thật | SecurityContext local không qua socket | Gửi Basic/Bearer/cookie thật |
| Test context thay JwtDecoder bằng Mockito rồi kiểm tra signature | Mock decoder bỏ qua signature | Sử dụng implementation decoder thật |
| Gửi Basic credentials trong header là an toàn trên HTTP thường | Basic chỉ mã hóa Base64, không mã hóa truyền tải | Chỉ dùng HTTP local test, TLS cho môi trường thật |
| Test luôn dùng token/user từ production | Rủi ro dữ liệu, bí mật và độ ổn định | Fixture tự tạo hoặc môi trường tích hợp được kiểm soát |

## 15. Ma trận kiểm thử tối thiểu cho một endpoint bảo vệ

Với `GET /api/private` và `GET /api/admin` trong demo:

| Mục tiêu | Request | Kỳ vọng |
| --- | --- | --- |
| Kiểm tra policy bằng mock | `with(user("reader").roles("USER"))` | `200` ở private |
| Chứng minh mock không tải user | `with(user("does-not-exist"))` | Vẫn có thể `200` ở private |
| Thiếu credentials | HTTP request không `Authorization` | `401` |
| Password sai | Basic `reader / wrong-password` | `401` |
| Password đúng | Basic `reader / correct-password` | `200` |
| Thiếu quyền admin | Basic `reader / correct-password` vào admin | `403` |
| Đủ quyền admin | Basic `administrator / admin-password` | `200` |
| Token JWT hợp lệ | Bearer JWS đúng chữ ký, issuer, hạn, scope | `200` ở reports |
| JWT sai chữ ký | Bearer JWS ký bằng khóa lạ | `401` |
| JWT hết hạn | Bearer JWS `exp` trong quá khứ | `401` |
| JWT thiếu scope | Bearer JWS hợp lệ nhưng thiếu `reports.read` | `403` |
| HTTP transport | `RANDOM_PORT` + `TestRestTemplate`/`bindToServer()` | Status, headers, body qua socket thật |

Chạy đủ **ca được chấp nhận** và **ca bị từ chối**. Ca âm giúp phát hiện hệ thống đang “cho phép tất cả”; ca dương giúp phát hiện hệ thống đang “chặn tất cả”. Nếu chỉ có một phía, bộ kiểm thử có thể xanh mà vẫn bỏ sót lỗi nghiêm trọng.

## 16. Bài tập thực hành

### Bài 1 — Chuyển mock principal thành Basic credentials

Cho test `MockMvc.with(user("reader").roles("USER"))` nhận `200`, hãy viết lại bằng `with(httpBasic("reader", "correct-password"))`. Thêm ca mật khẩu sai nhận `401` và giải thích sự khác biệt về thành phần authentication được chạy.

### Bài 2 — Phân biệt MockMvc với HTTP thật

Chạy lại ba ca `401`, `403`, `200` của HTTP Basic bằng `@SpringBootTest(RANDOM_PORT)` cùng `TestRestTemplate` hoặc `WebTestClient.bindToServer()`. Liệt kê những gì kiểm tra thêm được về embedded server và những gì vẫn chưa kiểm tra được về proxy/TLS production.

### Bài 3 — Một principal giả không tồn tại

Trong test `@WithMockUser(username = "ghost")` hoặc `with(user("ghost"))`, endpoint private vẫn nhận `200`. Gửi Basic `ghost` với password bất kỳ và xác nhận `401`. Trình bày tại sao hai kết quả không mâu thuẫn.

### Bài 4 — JWT thật so với mock JWT

Sử dụng cặp RSA test ở mục 9. Viết bốn test: token hợp lệ, hết hạn, sai chữ ký, thiếu scope. Kiểm tra `200`/`401`/`401`/`403` tương ứng; giải thích tại sao `mockJwt()` không thể thay thế nhóm test validation này.

### Bài 5 — CSRF và session

Một ứng dụng form login có `POST /login` và `POST /logout`. Thiết kế test HTTP thật đi qua `GET /login` → CSRF token/cookie → login → endpoint bảo vệ → logout → truy cập lại. Thêm ca thiếu CSRF để phân biệt `403` với sai password.

### Bài 6 — WebFlux

Dựng `SecurityWebFilterChain` với HTTP Basic và `MapReactiveUserDetailsService`. So sánh `mockUser()`, Basic header qua `bindToApplicationContext(...).apply(springSecurity())` và Basic header qua `bindToServer()`. Nêu rõ phần authorization, authentication và network transport đã được bao phủ ở mỗi test.

## 17. Checklist trước khi nói “đã kiểm thử tích hợp đầu cuối”

- [ ] Đã xác định test dùng principal giả hay credentials từ request.
- [ ] Đã chỉ rõ request đi qua MockMvc/mock WebFlux hay socket HTTP thật.
- [ ] Security filter chain cùng authentication manager/decoder mục tiêu thực sự được chạy, không bị mock hoặc vô hiệu hóa.
- [ ] Có ca credentials/token **hợp lệ** cho kết quả đúng.
- [ ] Có ca credentials/token **sai hoặc thiếu** bị từ chối.
- [ ] Có ca user/token hợp lệ nhưng **thiếu quyền** nhận `403` theo policy.
- [ ] Với JWT, chữ ký, issuer, hạn và scopes được validator/converter thật kiểm tra nếu thuộc mục tiêu.
- [ ] Với OAuth2/OIDC, token endpoint/callback/ID token validation đã được kiểm tra riêng nếu kết luận về protocol.
- [ ] Với session/browser login, cookie và CSRF token được gửi qua đúng HTTP flow.
- [ ] Fixture, transactions, key test và cookie state được cô lập giữa các test.
- [ ] Logs/test report không chứa secrets, private key, session cookie hoặc bearer token thật.
- [ ] Kết luận ghi rõ giới hạn: embedded server không đồng nghĩa toàn bộ mạng/IdP production.

## 18. Kết luận

Một test dùng `@WithMockUser`, `user()`, `jwt()` hoặc `mockJwt()` chủ yếu kiểm tra **ứng dụng làm gì khi đã có authentication**. Khi mục tiêu là **cơ chế tạo authentication**, hãy gửi username/password, Bearer JWS, cookie hoặc thông điệp OAuth2/OIDC qua request và cho security filters, manager/decoder cùng validator thật xử lý.

**Không nhầm xác thực thật với HTTP transport thật:** `MockMvc.with(httpBasic(...))` có thể kiểm tra password đúng/sai mà không mở socket. `@SpringBootTest(RANDOM_PORT)` kết hợp HTTP client kiểm tra thêm embedded server và đường truyền HTTP, nhưng vẫn cần credential hợp lệ và ca âm rõ ràng.

Một bộ test mạnh dùng cả hai lớp: test mock principal để phủ nhiều tổ hợp quyền nhanh, và integration tests có chủ đích để chứng minh authentication provider, decoder, login flow và network boundary làm việc đúng.

## 19. Tài liệu tham khảo

- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): áp dụng Spring Security filters trong MockMvc.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user()`, `httpBasic()` và test authentication.
- [Spring Security — MockMvc OAuth2 Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, `oauth2Login()`, `oidcLogin()` và giới hạn mock.
- [Spring Security — Reactive Web Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `WebTestClient` gắn security và Reactor Context.
- [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()` và kiểm thử principal Reactive.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, JWT validation và authority mapping.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `RANDOM_PORT` và test clients.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToApplicationContext` và `bindToServer`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF policy cho browser, session và các loại credentials.
