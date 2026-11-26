# Giới hạn của danh tính giả lập đối với cơ chế xác thực thực tế

## 1. Bối cảnh: một bài kiểm thử xanh đang chứng minh điều gì?

Trong ứng dụng Reactive dùng Spring WebFlux và Spring Security, `WebTestClient` có thể gửi yêu cầu giả lập người dùng đã đăng nhập bằng `spring-security-test`:

~~~java
client.mutateWith(mockUser("learner").roles("USER"))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

Đây là phép kiểm thử hữu ích: với một principal mang quyền `ROLE_USER` đã được cung cấp, ứng dụng cho phép truy cập tài nguyên bảo vệ. Nhưng kết quả `200 OK` **không chứng minh** rằng password của `learner` đã được kiểm tra, JWT đã được giải mã và xác minh chữ ký, OAuth2/OIDC login đã gọi Identity Provider hay session cookie đã đi qua quá trình xác thực thật.

Trong module `SPRING_SECURITY_TESTING`, người học cần phân biệt **kiểm thử phân quyền với danh tính giả lập** và **kiểm thử cơ chế tạo danh tính từ một yêu cầu HTTP thực**. Cả hai đều cần thiết, nhưng trả lời những câu hỏi khác nhau.

Sau bài học, bạn sẽ:

1. Hiểu `SecurityContext` trong Reactive và cách `ReactiveSecurityContextHolder` mang authentication qua Reactor Context.
2. Dùng đúng `mockUser()`, `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()` và `@WithMockUser` để kiểm tra policy.
3. Nhận diện những đường xác thực đã bị bỏ qua khi dùng các danh tính giả lập.
4. Viết test xác nhận mật khẩu sai hoặc Bearer token không hợp lệ bị từ chối bởi authentication mechanism thực tế.
5. Chọn `WebTestClient` gắn mock application context hoặc gắn HTTP server thật theo phạm vi mục tiêu.
6. Đọc đúng `401`, `403`, `200` và tránh nhầm lỗi CSRF với lỗi xác thực.

## 2. Mô hình danh tính Reactive

Trong Spring MVC/Servlet, `SecurityContextHolder` thường gắn context với thread xử lý request. WebFlux có thể chuyển việc xử lý giữa nhiều thread trong cùng một luồng Reactive, nên không thể dựa vào một `ThreadLocal` duy nhất để đại diện danh tính xuyên suốt request.

Spring Security Reactive cung cấp `ReactiveSecurityContextHolder`, nơi `SecurityContext` được truyền trong **Reactor Context** của chuỗi `Mono`/`Flux`. Khi authorization filter cần biết ai đang gửi request, nó truy cập security context tương ứng với chuỗi đang chạy.

~~~mermaid
flowchart TD
    A["HTTP request đi vào WebFlux"] --> B["SecurityWebFilterChain"]
    B --> C["Authentication web filter hoặc test configurer"]
    C --> D["Reactor Context chứa SecurityContext"]
    D --> E["Authentication: principal + authorities"]
    E --> F{"Luật phân quyền?"}
    F -- "Đủ quyền" --> G["Controller / service reactive"]
    F -- "Thiếu quyền" --> H["403 Forbidden"]
    C -- "Không xác thực được" --> I["401 hoặc redirect tùy entry point"]
~~~

| Thành phần | Vai trò |
| --- | --- |
| `Authentication` | Đối tượng biểu diễn principal, credentials và authorities |
| `SecurityContext` | Bao chứa authentication của ngữ cảnh bảo mật |
| `ReactiveSecurityContextHolder` | Truy cập security context trong Reactor Context |
| `SecurityWebFilterChain` | Các web filter chịu trách nhiệm xác thực, CSRF, authorization và xử lý ngoại lệ |
| `ReactiveAuthenticationManager` | Kiểm tra credentials/token và trả authentication hoặc lỗi |
| `ServerSecurityContextRepository` | Lưu/đọc security context khi sử dụng session hoặc chiến lược lưu phù hợp |
| `SecurityMockServerConfigurers` | Tạo danh tính/ngữ cảnh giả để kiểm thử các nhánh đã có authentication |

**Điểm cần nhớ:** `Authentication.isAuthenticated() == true` có thể do test tự cung cấp, không nhất thiết do một `ReactiveAuthenticationManager` xác minh thành công. Ngược lại, người dùng anonymous không phải luôn tương ứng với một `Authentication` bằng `null`: Spring Security có thể đại diện người dùng chưa đăng nhập bằng anonymous authentication.

## 3. Hai đường tạo danh tính: giả lập và xác thực thật

### 3.1. Đường giả lập

Với `client.mutateWith(mockUser("learner"))`, Spring Security Test thiết lập principal được coi là đã đăng nhập cho request mô phỏng. Các web filter/authorization rules vẫn có thể thực thi, nhưng request **không cần gửi username/password thực** và không phải đi qua phần xác thực HTTP Basic hay form login để tạo principal ấy.

`mockJwt()` tạo authentication JWT giả với claims/authorities để kiểm tra logic ứng dụng. `mockOAuth2Login()`, `mockOidcLogin()` tạo người dùng OAuth2/OIDC giả sau login. Chúng không gọi decoder hoặc Identity Provider chỉ vì đã được dùng.

### 3.2. Đường xác thực thực tế

Với `WebTestClient.bindToServer()` gửi:

~~~http
GET /api/private HTTP/1.1
Authorization: Basic <base64-of-real-test-credentials>
~~~

Ứng dụng nhận HTTP request, chạy security web filters, gọi authentication manager và user-details service (hoặc cơ chế authentication thực được cấu hình), rồi mới cấp quyền nếu credentials hợp lệ. Với Bearer JWT, request phải đi qua bearer authentication filter và `ReactiveJwtDecoder` đã cấu hình; với OAuth2/OIDC login cần kiểm tra riêng giao thức redirect/callback/token validation.

| Tác vụ kiểm thử | Principal giả qua `mockUser()` | Client thật gửi HTTP credentials |
| --- | --- | --- |
| Có thể kiểm tra role/authority? | Có | Có, sau khi xác thực |
| Kiểm tra tài nguyên trả `200`/`403`? | Có | Có |
| Kiểm tra mật khẩu có đúng không? | **Không** | Có, nếu gọi authentication manager thật |
| Kiểm tra Bearer JWT có chữ ký đúng không? | Không | Có, nếu dùng decoder/validator thật |
| Kiểm tra token hết hạn? | Không | Có, nếu token chạy qua timestamp validator thật |
| Kiểm tra OAuth2/OIDC authorization-code exchange? | Không | Cần integration test flow với IdP/authorization server thử nghiệm |
| Kiểm tra TCP, HTTP cookies/headers qua server? | Không khi mock bind | Có khi `bindToServer()` |

**Không đồng nhất “security filter chain đã được gọi” với “authentication provider đã xác thực credentials thật”.** Một request chứa authentication giả có thể được phép đi tiếp dù phần xác thực password hoặc JWT đang cấu hình sai.

## 4. Ứng dụng WebFlux mẫu dùng xuyên suốt

Tạo một API Reactive có bốn endpoint:

| Endpoint | Chính sách | Kết quả cần quan sát |
| --- | --- | --- |
| `GET /api/public` | `permitAll()` | Guest được `200` |
| `GET /api/private` | `authenticated()` | Guest `401` khi dùng HTTP Basic; người đã xác thực `200` |
| `GET /api/admin` | `hasRole("ADMIN")` | USER nhận `403`; ADMIN nhận `200` |
| `POST /api/notes` | Người đã xác thực, CSRF bật | Thiếu CSRF `403`; có CSRF và auth hợp lệ `200` |

Gradle dependencies minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Controller trả một phần dữ liệu định danh để test có thể quan sát:

~~~java
import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class IdentityDemoController {
    @GetMapping("/api/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    Mono<Map<String, String>> privateEndpoint(Mono<Principal> principal) {
        return principal.map(value -> Map.of("user", value.getName()));
    }

    @GetMapping("/api/admin")
    Mono<String> adminEndpoint() {
        return Mono.just("admin");
    }

    @PostMapping("/api/notes")
    Mono<String> createNote() {
        return Mono.just("created");
    }
}
~~~

Cấu hình security đơn giản:

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
class IdentityDemoSecurity {
    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                    .pathMatchers("/api/public").permitAll()
                    .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                    .pathMatchers("/api/private", "/api/notes").authenticated()
                    .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}correct-password")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin-password")
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(learner, admin);
    }
}
~~~

Mật khẩu `{noop}` ở đây chỉ dành cho fixture học tập, không dùng trong môi trường thật. HTTP Basic là cơ chế xác thực minh họa để phân biệt principal giả và credentials được kiểm tra. Trong production hãy dùng password encoder và kho người dùng an toàn theo yêu cầu hệ thống.

Security chain giữ CSRF mặc định. Bất kỳ kiểm thử POST nào cũng cần xem xét CSRF cùng với authentication và authority.

## 5. Tạo WebTestClient cho mock WebFlux đúng cách

Để sử dụng các `SecurityMockServerConfigurers` cho Reactive, có thể bind client vào `ApplicationContext` và áp dụng `springSecurity()` tường minh:

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

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveIdentityMockTests {

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
    void anonymousCannotAccessPrivateEndpoint() {
        client.get()
              .uri("/api/private")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserCanAccessPrivateEndpoint() {
        client.mutateWith(mockUser("learner").roles("USER"))
              .get()
              .uri("/api/private")
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.user").isEqualTo("learner");
    }

    @Test
    void mockUserWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("learner").roles("USER"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void mockAdminIsAllowed() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isOk();
    }

    @Test
    void postWithoutCsrfIsForbiddenEvenWithMockUser() {
        client.mutateWith(mockUser("learner").roles("USER"))
              .post()
              .uri("/api/notes")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void csrfPlusMockUserAllowsPost() {
        client.mutateWith(mockUser("learner").roles("USER"))
              .mutateWith(csrf())
              .post()
              .uri("/api/notes")
              .exchange()
              .expectStatus().isOk();
    }
}
~~~

Để ý hai thành phần:

- `apply(springSecurity())` gắn cơ chế hỗ trợ Spring Security Test vào client mock; từ đó `mutateWith(mockUser(...))` và `mutateWith(csrf())` được xử lý trong request.
- `@SpringBootTest(webEnvironment = MOCK)` dùng WebFlux application context thực của ứng dụng, nhưng `WebTestClient.bindToApplicationContext(...)` không gửi packet HTTP qua socket.

Kết quả test xác nhận **policy đối với các principal giả** và cách filter CSRF hoạt động trong mock server. Nó không chứng minh user database đã được truy vấn, password đã được kiểm tra hay một bearer token đã được giải mã.

### 5.1. `@WithMockUser` và phạm vi của annotation

`@WithMockUser` cũng có thể thiết lập principal giả cho test Spring Security. Trong môi trường WebFlux, test cần được tích hợp đúng Spring Security Test execution listeners và reactive context. Ví dụ:

~~~java
@Test
@WithMockUser(username = "learner", roles = "USER")
void principalFromAnnotationIsAllowed() {
    client.get()
          .uri("/api/private")
          .exchange()
          .expectStatus().isOk();
}
~~~

Đoạn này giả định client WebFlux mock đã gắn `springSecurity()` như ở trên và `@WithMockUser` được Spring Test kích hoạt. Sử dụng `@WithMockUser` không có nghĩa password của `learner` được xác minh. Nếu mỗi request trong cùng test cần vai trò khác nhau, `mutateWith(mockUser(...))` thường rõ ràng hơn.

Đặc biệt, với `WebTestClient.bindToServer()` gửi HTTP qua cổng mạng, `@WithMockUser` trong thread kiểm thử **không tự đi qua socket** để trở thành principal của server. Hãy gửi credentials/token/cookie bằng HTTP thật.

## 6. Thử nghiệm đối chứng: Mock USER được chấp nhận nhưng mật khẩu sai bị từ chối

Đây là cách nhanh nhất để hiểu giới hạn của giả lập:

| Cùng endpoint | Cách thiết lập identity | Dự kiến |
| --- | --- | --- |
| `GET /api/private` | `mutateWith(mockUser("learner"))` | `200` |
| `GET /api/private` | Không credentials | `401` |
| `GET /api/private` | HTTP Basic, password sai | `401` |
| `GET /api/private` | HTTP Basic, password đúng | `200` |

Test với **cổng HTTP thật**:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveIdentityRealHttpTests {

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
    void wrongPasswordIsRejectedByRealAuthentication() {
        http.get()
            .uri("/api/private")
            .headers(headers -> headers.setBasicAuth(
                    "learner", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void correctPasswordAuthenticatesRealRequest() {
        http.get()
            .uri("/api/private")
            .headers(headers -> headers.setBasicAuth(
                    "learner", "correct-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("learner");
    }

    @Test
    void noCredentialsIsUnauthorized() {
        http.get()
            .uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validUserStillCannotEnterAdminEndpoint() {
        http.get()
            .uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                    "learner", "correct-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

So sánh hai nhóm test:

- `mockUser("learner")` đặt danh tính đã được xác thực cho request. Nó đánh giá liệu application có **cho phép principal được cấp quyền USER** truy cập đúng endpoint.
- HTTP Basic sai và đúng mật khẩu là các request đi qua web filters và authentication manager thật. Chúng đánh giá liệu hệ thống có **từ chối credentials không hợp lệ và cấp authentication cho credentials hợp lệ**.
- Ca user thật thiếu `ADMIN` trả `403` đánh giá phân quyền **sau khi đã xác thực**.

Kết quả một ca mock USER xanh có thể tiếp tục xanh ngay cả khi password encoder, user-details service hoặc authentication manager thực tế được cấu hình sai. Chỉ kiểm thử đường tạo danh tính thật mới phát hiện được nhóm lỗi này.

**Giới hạn của ví dụ HTTP Basic:** do đây là username/password được kiểm tra trong test context, nó không chứng minh mạng sản xuất, proxy, TLS hay kho danh tính sản xuất hoạt động; để xác nhận các thành phần đó cần môi trường tích hợp tương ứng.

## 7. Vì sao `ReactiveSecurityContextHolder` không phải `SecurityContextHolder`?

Một phương thức Reactive có thể đọc người dùng hiện tại mà không quan tâm request được xử lý trên thread nào:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
~~~

Để unit test logic đang dùng Reactor Context, có thể gắn authentication có chủ đích vào publisher:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

@Test
void userIdentityFlowsThroughReactorContext() {
    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                "learner",
                "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

    StepVerifier.create(currentUsername()
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(authentication)))
            .expectNext("learner")
            .verifyComplete();
}
~~~

Test này hữu ích để kiểm tra **truyền ngữ cảnh** qua chuỗi Reactive. Nó không chạy HTTP filter hay password validation: authentication được tạo trực tiếp trong test bằng constructor `UsernamePasswordAuthenticationToken` ba tham số.

Không nên thay bằng việc đọc `SecurityContextHolder.getContext().getAuthentication()` từ thread JUnit sau khi `client.exchange()` hoàn tất rồi kết luận user của request Reactive là ai. Reactor Context sống theo **subscriber chain**, không nhất thiết theo thread local của JUnit.

### 7.1. Context propagation qua thao tác bất đồng bộ

`Mono.deferContextual(...)` và `ReactiveSecurityContextHolder.getContext()` cho phép lấy dữ liệu từ Reactor Context khi subscription diễn ra. Nếu code tự mở một subscribe riêng, chuyển sang `CompletableFuture`, dùng thread pool thủ công hoặc làm mất context khi tích hợp thư viện không hỗ trợ propagation, dữ liệu bảo mật có thể không còn ở nơi cần dùng.

Một test đơn thuần gọi method với principal giả chưa chứng minh mọi boundary bất đồng bộ bảo toàn security context. Khi ứng dụng có đổi scheduler, gọi dịch vụ ngoài hoặc custom publisher, hãy thêm test đi qua chính boundary đó, kiểm tra đúng principal và không rò rỉ principal giữa các request.

## 8. JWT giả lập không chứng minh chữ ký, hạn hay decoder đã chạy

Trong WebFlux, Spring Security Test hỗ trợ `mockJwt()`:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("learner")
            .claim("scope", "reports.read")))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

Đây là một principal JWT **giả** có claims theo ý test, tương đương giả lập authentication đã tồn tại. Nó không gửi một JWS đến `ReactiveJwtDecoder` để xác minh.

Với test resource server WebFlux riêng, cấu hình phải sử dụng `oauth2ResourceServer(...).jwt(...)`, và application context cần một `ReactiveJwtDecoder` (thật hoặc test bean phù hợp). Đặt claims sai hạn trên `mockJwt()` vẫn không có nghĩa đã thực thi `JwtTimestampValidator`:

~~~java
import java.time.Instant;

Instant now = Instant.now();

client.mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("learner")
            .issuedAt(now.minusSeconds(3600))
            .expiresAt(now.minusSeconds(300))
            .claim("scope", "reports.read")))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

Hai trường `iat` và `exp` được đặt theo thứ tự hợp lệ nhưng đều trong quá khứ; đây là **ví dụ cho thấy test mock bỏ qua validator**, không phải lỗ hổng thực tế được chứng minh.

Để xác nhận hệ thống từ chối JWT sai chữ ký hoặc hết hạn:

1. Cấu hình WebFlux resource server có `ReactiveJwtDecoder` thực, bộ khóa đáng tin và validators (`exp`, `nbf`, `iss`, audience nếu hệ thống yêu cầu).
2. Tạo JWS ký thật cho test, trong đó có ít nhất một token hợp lệ, một token ký bằng khóa lạ và một token đã hết hạn vượt xa khoảng clock skew.
3. Gửi `Authorization: Bearer <signed-jws>` bằng `WebTestClient`, **không gắn `mockJwt()`** trong request đó.
4. Kiểm tra token hợp lệ nhận `200`, token sai chữ ký/hết hạn nhận `401`, token hợp lệ nhưng thiếu quyền nhận `403` nếu policy có scope/role yêu cầu.
5. Nếu cần kiểm tra HTTP thực, dùng `bindToServer()`; nếu mục tiêu chỉ cần filter/decoder trong application context thì cũng có thể gửi Bearer thật qua mock WebFlux client với decoder thật.

| Test | JWT signature | `exp`/`nbf` | Policy |
| --- | --- | --- | --- |
| `mockJwt()` có scope phù hợp | Không kiểm tra | Không kiểm tra | Có thể kiểm tra |
| `mockJwt()` với `exp` đã hết hạn | Không kiểm tra | Không kiểm tra | Có thể vẫn cho `200` |
| Bearer JWS thật + decoder thật | Kiểm tra theo khóa cấu hình | Kiểm tra theo validators cấu hình | Kiểm tra sau authentication thành công |
| Bearer JWS ký khóa lạ | Decoder từ chối | Có thể chưa tới bước claim validation | Thường `401` |
| Bearer JWS đúng chữ ký, thiếu scope | Chấp nhận token | Chấp nhận token | Thường `403` |

Đừng dùng `@MockBean ReactiveJwtDecoder`/Mockito trả sẵn một `Jwt` để kết luận chữ ký đã được kiểm tra: một mock decoder có thể bỏ qua chính phần cần chứng minh.

## 9. OAuth2 Login và OIDC Login giả lập: cùng giới hạn về giao thức

Spring Security Test Reactive còn cung cấp:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;

// Đã giả lập một người đăng nhập OAuth2.
client.mutateWith(mockOAuth2Login())
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();

// Đã giả lập một người đăng nhập OIDC.
client.mutateWith(mockOidcLogin())
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

Những helper này hữu ích khi controller/service cần `OAuth2User`, `OidcUser` hoặc authorities và claims của principal **sau login**. Test có thể thiết lập `sub`, `email`, authorities hoặc client registration tương ứng để kiểm tra mapping, nhưng không tự thực hiện:

- Redirect người dùng đến authorization endpoint.
- Lưu và so sánh tham số `state` trên callback.
- Đổi authorization code lấy token qua token endpoint.
- Kiểm tra PKCE `code_verifier`/`code_challenge`.
- Xác minh chữ ký, `iss`, `aud`, `exp` và `nonce` của OIDC ID token.
- Lưu session thực, token refresh hoặc logout với Identity Provider.

Một ca `mockOidcLogin()` trả `200` chỉ chứng minh application chấp nhận **principal OIDC do test tạo**. Nếu yêu cầu là “login OIDC thực phải từ chối ID token sai issuer hoặc nonce”, hãy viết integration test có authorization server/IdP thử nghiệm, đi qua callback và validator thực.

`mockOAuth2Client(...)` lại thường liên quan authorized client/token được cung cấp sẵn cho WebClient. Nó không chứng minh `ReactiveOAuth2AuthorizedClientManager` đã thực sự gửi POST đến token endpoint. Để chứng minh token exchange, cần quan sát request HTTP của client thật, grant parameters, client authentication và response hoặc lỗi từ token endpoint mô phỏng.

## 10. Session, logout và CSRF: điều mà một request mock không chứng minh

Với form login hoặc session based authentication, test `mockUser()` không tự tạo một phiên từng trải qua login thực tế. Vì vậy một test:

~~~java
client.mutateWith(mockUser("learner"))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk();
~~~

không xác nhận cookie `SESSION` đã được tạo, session được lưu trong repository, hay logout sẽ làm session đó mất hiệu lực.

Để kiểm tra session lifecycle:

1. Gửi login thật qua HTTP hoặc mock WebFlux filters với đúng credentials và CSRF token.
2. Giữ cookie session được server trả về.
3. Dùng cookie ấy gọi endpoint bảo vệ, bảo đảm được truy cập.
4. Gửi logout với cùng session và CSRF hợp lệ theo cấu hình.
5. Dùng lại cookie/session cũ để thử truy cập endpoint bảo vệ, phải bị từ chối theo hợp đồng logout; kiểm tra kho session nếu yêu cầu.

Khi CSRF được bật, `POST` thiếu CSRF thường nhận `403` **ngay cả khi user đã được mock là authenticated**. Đây là kiểm chứng CSRF, không phải bằng chứng xác thực thất bại. Hãy viết ca phân biệt: mock user + thiếu CSRF (`403`), mock user + `csrf()` (`200`), không có user nhưng có CSRF và endpoint yêu cầu authentication (thường `401` hoặc redirect tùy entry point).

Không mặc định mọi form login đều trả `401`; ứng dụng dùng `LoginUrlAuthenticationEntryPoint` thường trả redirect `302` đến trang login. Mã `403` cũng có thể xuất hiện khi principal đã xác thực nhưng không đủ role.

## 11. Cách chọn kiểu kiểm thử theo điều cần chứng minh

| Câu hỏi | Công cụ phù hợp | Bằng chứng cần có |
| --- | --- | --- |
| `ROLE_USER` có được đọc tài nguyên riêng? | Mock WebFlux + `mockUser()` | `200` với USER và `401`/`403` ở các trường hợp đối chứng |
| `ROLE_USER` có bị chặn tại `/api/admin`? | Mock WebFlux + `mockUser("learner").roles("USER")` | `403`; ADMIN được `200` |
| Password sai bị từ chối? | WebTestClient gửi HTTP Basic/form credentials thật | Password sai `401`/login failure; đúng được truy cập |
| Mật khẩu có được hash và so sánh đúng? | Integration test authentication manager với user store/encoder thật | Ca đúng/sai, không dùng principal giả |
| JWT ký sai/hết hạn bị từ chối? | Bearer JWS thật và `ReactiveJwtDecoder` thật | Token hợp lệ `200`, token lỗi `401` |
| Mapping claims/scopes thành quyền đúng? | Test converter/policy và bearer integration | Authorities tương ứng, thiếu scope `403` |
| OIDC principal được code ứng dụng xử lý đúng? | `mockOidcLogin()` | Principal/claims giả được đọc đúng |
| OIDC `nonce`/issuer/chữ ký được xác minh? | Integration test với OIDC Provider giả hoặc môi trường kiểm soát | Flow và token validator thực từ chối token sai |
| Session mất hiệu lực sau logout? | Chuỗi login → cookie → logout → truy cập lại | Session cũ không còn quyền truy cập |
| Reactor Context không rò rỉ qua request? | Test reactive pipeline và request song song | Mỗi request nhận đúng principal của nó |
| Network stack/proxy/TLS đúng? | Integration/end-to-end test qua HTTP thật tại môi trường thích hợp | Headers, cookies, TLS và routing đúng |

Một chiến lược kiểm thử hiệu quả gồm nhiều mock tests để bao phủ quyền nhanh, kết hợp số ít integration tests có chủ đích cho **những ranh giới xác thực không được fake**.

## 12. Phân biệt các kiểu setup WebTestClient

### 12.1. Mock WebFlux application context

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
~~~

Đây là môi trường phù hợp cho `mockUser()`, `mockJwt()`, `csrf()` và các test HTTP security không cần mở port. Nó cũng có thể kiểm tra bearer thật qua filter chain **nếu bạn cố ý gửi header và dùng decoder thật**, nhưng không kiểm tra network boundary.

### 12.2. Full context với auto configuration

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class WebFluxApplicationTests {
    @Autowired
    WebTestClient client;
}
~~~

`@AutoConfigureWebTestClient` giúp inject test client trong Spring Boot WebFlux phù hợp. Với test sử dụng Spring Security mutators, cần bảo đảm client đã được tích hợp `springSecurity()` theo cách test setup của dự án; dùng binding tường minh như mục 5 nếu cần kiểm soát chính xác.

### 12.3. HTTP server thật

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebFluxHttpTests {
    @LocalServerPort
    int port;

    @Test
    void realHttp() {
        WebTestClient http = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
        http.get().uri("/api/private")
            .exchange().expectStatus().isUnauthorized();
    }
}
~~~

Đây là cách kiểm thử những header/cookie/status mà một HTTP client thật nhìn thấy. Nó có thể áp dụng cho Servlet server nữa, nhưng **không thể đưa mock principal trực tiếp qua socket** bằng `mutateWith(mockUser())`.

Nếu ứng dụng dùng Spring MVC/Servlet và muốn mô phỏng request không mở cổng, dùng `MockMvc` cùng `spring-security-test` Servlet thay vì giả định `bindToApplicationContext` tạo được WebFlux security context cho Servlet.

## 13. Những lỗi kiểm thử dễ tạo cảm giác an toàn giả

| Hiện tượng | Ngộ nhận | Cách kiểm chứng đúng |
| --- | --- | --- |
| `mockUser()` nhận `200` | Người dùng thật đăng nhập thành công | Gửi credentials đúng/sai qua authentication manager |
| `mockJwt()` với `exp` quá khứ vẫn `200` | JWT hết hạn được production chấp nhận | Gửi Bearer JWS thật qua decoder/validator |
| `mockOidcLogin()` nhận `200` | Chữ ký ID token và `nonce` hợp lệ | Test flow OIDC và validator thật |
| Mock USER bị `403` trên POST | USER thiếu authority | Thêm CSRF vào request để phân biệt |
| Test có `@WithMockUser` mà server thật vẫn `401` | Spring Security mất principal | Authentication giả của test không đi qua HTTP socket |
| Test chỉ có ca credentials sai nhận `401` | Authentication đúng chắc chắn hoạt động | Thêm ca hợp lệ nhận `200` |
| Tắt WebFilter/SecurityWebFilterChain để test đơn giản | Endpoint đã được bảo vệ | Chạy filters thật và thử guest |
| Lấy `SecurityContextHolder` sau `exchange()` | Đã đọc danh tính request Reactive | Dùng Reactor Context hoặc phản hồi từ handler |
| Mock decoder luôn trả `Jwt` hợp lệ | Resource server xác minh chữ ký tốt | Sử dụng decoder thật với JWS ký đúng và ký sai |
| Chỉ kiểm tra role giả trong unit test | Không cần kiểm tra login/logout | Thêm integration test cho authentication boundaries |
| Gửi `Authorization: Bearer ...` giả nhưng không bật resource server | Token đã được phân tích | Xác nhận `ReactiveJwtDecoder`/filter thực và ca 401 |
| Nhận `403` rồi khẳng định guest bị chặn | Có thể là authenticated thiếu quyền hoặc thiếu CSRF | Thiết kế ca đối chứng riêng cho từng nguyên nhân |

## 14. Bài thực hành và tiêu chí đạt

### Bài tập 1: cùng một tên người dùng, hai cơ chế khác nhau

Trên API `GET /api/private`, viết một test `mockUser("learner")` nhận `200` và một test HTTP Basic với `learner` nhưng password sai nhận `401`. Giải thích vì sao hai kết quả không mâu thuẫn.

### Bài tập 2: chứng minh giới hạn mock JWT

Tạo `mockJwt()` với subject `learner`, claim `scope=reports.read`, `exp` đã ở quá khứ. Với policy cho phép authority tương ứng, chứng minh yêu cầu có thể nhận `200` vì không chạy `ReactiveJwtDecoder`. Sau đó viết kế hoạch test Bearer thật: token hợp lệ nhận `200` và token hết hạn nhận `401`.

### Bài tập 3: ngăn rò rỉ danh tính qua Reactor Context

Tạo hai publishers độc lập, mỗi publisher dùng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` với username khác nhau. Dùng `StepVerifier` xác nhận từng publisher trả đúng tên, không mượn danh tính từ publisher còn lại. Nếu ứng dụng dùng scheduler tùy chỉnh, thêm một ca đi qua scheduler đó.

### Bài tập 4: phân biệt thiếu quyền và thiếu CSRF

Test `GET /api/admin` bằng mock USER và ADMIN, rồi `POST /api/notes` với cùng mock USER có hoặc thiếu `csrf()`. Giải thích từng mã `403` dựa trên filter đang từ chối request.

### Bài tập 5: kiểm tra OAuth2/OIDC thực

Giả sử `mockOidcLogin()` nhận `200` từ endpoint hồ sơ. Liệt kê những bước chưa được chạy của OIDC login. Thiết kế một integration test gửi authorization code callback với `state`, token endpoint và ID token có issuer/nonce sai để xác minh application từ chối đúng.

**Tiêu chí đạt:** khi đọc một test có principal giả, người học có thể nói rõ thành phần nào đã chạy, thành phần xác thực nào bị bỏ qua, và cần test thực tế nào để kiểm chứng ràng buộc chưa được bao phủ.

## 15. Tổng hợp

Danh tính giả lập là công cụ để **cô lập và kiểm chứng chính sách sau khi có authentication**. Trong WebFlux, nó đi qua Reactor Context và các API như `mockUser()`, `mockJwt()`, `mockOAuth2Login()` hoặc `mockOidcLogin()`. Điều đó không tự kích hoạt xác minh mật khẩu, chữ ký JWT, token validation hoặc OAuth2/OIDC protocol.

Muốn kết luận cơ chế xác thực thực tế an toàn, hãy gửi **credentials/token/cookie qua đúng đường đi** và quan sát cả ca hợp lệ lẫn ca bị từ chối. Với Reactive, dùng `WebTestClient` và `ReactiveSecurityContextHolder` đúng ngữ cảnh; với Servlet, áp dụng `MockMvc` và các matcher tương ứng.

## 16. Tài liệu tham khảo chính thức

- [Spring Security — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()`, `@WithMockUser` và Reactive authentication tests.
- [Spring Security — Reactive Web Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `WebTestClient` và `springSecurity()`.
- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()`.
- [Spring Security — Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `csrf()` và test các HTTP method có state.
- [Spring Security — Security Context in WebFlux](https://docs.spring.io/spring-security/reference/reactive/authentication/architecture.html): security context và cơ chế xác thực Reactive.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToApplicationContext`, `bindToServer` và các kiểu binding.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` và web environment.
