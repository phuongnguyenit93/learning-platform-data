# Gửi header hoặc cookie thực khi cần kiểm thử HTTP qua mạng

Một bài kiểm thử Spring Security có thể trả về **200 OK** vì test đã gắn sẵn người dùng vào `SecurityContext`. Kết quả đó không chứng minh trình duyệt hoặc ứng dụng khách đã gửi đúng header `Authorization`, máy chủ nhận được cookie, hay luồng xác thực HTTP thực sự xử lý request.

Trong chương **Thiết lập WebTestClient** của module `SPRING_SECURITY_TESTING`, chủ đề này giải quyết trường hợp cần xác minh **HTTP request đi qua mạng**: client gửi header hoặc cookie đến một server đang lắng nghe trên cổng thật; Spring Security trên server kiểm tra request, tạo authentication và quyết định cho phép hoặc từ chối.

`WebTestClient` làm được cả kiểm thử không mở cổng và kiểm thử qua HTTP. Sự khác biệt nằm ở **cách bind client**:

- `bindToController(...)` và `bindToApplicationContext(...)`: kiểm thử phía server trong bộ nhớ, không thực hiện một kết nối mạng TCP đến server đang chạy.
- `bindToServer()`: gửi HTTP tới URL của server đang lắng nghe; có thể là ứng dụng Spring Boot khởi chạy ở cổng ngẫu nhiên trong test hoặc một server ở môi trường kiểm thử.

Bài học tập trung vào việc chọn đúng cơ chế để kiểm chứng header/cookie, dùng các assertion tương ứng và tránh nhầm `mockUser()`, `mockJwt()` hoặc `@WithMockUser` với thông tin xác thực đã được truyền qua mạng.

## 1. Vì sao phải quan sát HTTP request thật?

Hãy xét API `GET /api/me` chỉ cho người đã đăng nhập truy cập. Trong kiểm thử WebFlux chạy trong bộ nhớ, một lời gọi như sau có thể đủ để kiểm tra phân quyền:

~~~java
webTestClient
    .mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

`mockUser("alice")` thuộc `SecurityMockServerConfigurers` của `spring-security-test`. Configurer cấp sẵn danh tính cho **test security context**, phù hợp khi chỉ muốn biết endpoint xử lý người dùng có role `USER` như thế nào.

Nhưng nó không chứng minh có header HTTP Basic, token Bearer hoặc cookie đăng nhập trong request. Với client thật, những dữ liệu này phải được gửi theo HTTP và được filter chain phân tích.

Ví dụ gửi Basic header qua mạng:

~~~http
GET /api/me HTTP/1.1
Host: localhost:54321
Accept: application/json
Authorization: Basic YWxpY2U6Y29ycmVjdA==
~~~

Header ở ví dụ là Base64 của `alice:correct`, không phải mật khẩu đã được mã hóa an toàn. Với request qua Internet, HTTP Basic cần được bảo vệ bằng HTTPS. Trong test cục bộ, ta dùng header này để kiểm chứng cơ chế xác thực của ứng dụng.

Ví dụ gửi một cookie do server cấp:

~~~http
GET /demo/read-cookie HTTP/1.1
Host: localhost:54321
Cookie: demo-pref=dark
~~~

Điểm cần xác nhận không chỉ là mã trạng thái cuối cùng, mà còn là **server nhận đúng giá trị** và xử lý đúng các giới hạn bảo mật của request đó.

### So sánh nhanh các kiểu WebTestClient

| Cách dựng WebTestClient | Có mở kết nối HTTP tới server thật? | Có thể dùng `mockUser()` trực tiếp? | Phù hợp để kiểm tra |
| --- | --- | --- | --- |
| `bindToController(controller)` | Không | Chỉ khi setup WebFlux Security test thích hợp | Controller/handler và phản hồi |
| `bindToApplicationContext(context)` | Không | Có, khi cấu hình Spring Security test cho WebFlux | WebFilter chain, phân quyền, logic ứng dụng trong bộ nhớ |
| `bindToServer().baseUrl(...)` | **Có** | Không dùng test configurer như cơ chế xác thực từ client qua mạng | Header, cookie, redirect, session và HTTP filters trên server thật |

**Lưu ý:** `bindToApplicationContext(...)` vẫn có thể chạy Spring Security web filters thực của ứng dụng trong bộ nhớ nếu được cấu hình đúng. “Không qua mạng” không có nghĩa “bỏ qua bảo mật”; nó chỉ không đo transport, địa chỉ host, cookie trên HTTP và cách client nói chuyện với server bên ngoài.

## 2. Tạo server thật bằng SpringBootTest RANDOM_PORT

Với Spring Boot, cách thuận tiện là khởi động ứng dụng trên cổng ngẫu nhiên và tạo `WebTestClient` kết nối đến cổng đó.

Ví dụ Gradle cho ứng dụng **WebFlux**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Trong ứng dụng Servlet/Spring MVC, vẫn có thể dùng `WebTestClient.bindToServer()` để gửi HTTP tới server đang chạy. Khi đó ứng dụng dùng `spring-boot-starter-web`, và test cần thư viện WebTestClient (thuộc Spring WebFlux) trên classpath. Không nên chuyển cả ứng dụng sang Reactive chỉ vì muốn dùng client HTTP cho test.

### 2.1. Dựng WebTestClient nối tới cổng được cấp

~~~java
import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class LiveHttpSecurityTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void configureClient() {
        client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }
}
~~~

Ở Spring Boot 3.x, `@LocalServerPort` thường nằm trong package `org.springframework.boot.test.web.server`. Nếu dự án dùng phiên bản Spring Boot có package test khác, hãy dùng annotation tương ứng. Ví dụ ở bài này dựa trên API của Spring Boot 3.x và Spring Security 6.x; các tên class/annotation thuộc Spring Boot thế hệ sau có thể cần cập nhật import.

Những điều cần hiểu:

- `RANDOM_PORT` khởi động server thực; Spring Boot cấp một cổng còn trống, giúp giảm xung đột trên máy phát triển và CI.
- `bindToServer()` tạo **HTTP client** kết nối tới `localhost:port`. Nó không tự tạo mock principal cho server.
- `responseTimeout(...)` giới hạn thời gian chờ, giúp test không treo mãi khi server không phản hồi.
- `localhost` với HTTP là lựa chọn phù hợp cho test cục bộ. Muốn kiểm tra TLS/HTTPS, reverse proxy hoặc cookie `Secure`, phải sử dụng môi trường HTTPS tương ứng.

Sơ đồ hai kiểu request:

~~~mermaid
flowchart LR
    A["WebTestClient bindToApplicationContext"] --> B["WebFlux filters trong bộ nhớ"]
    C["WebTestClient bindToServer"] --> D["HTTP qua localhost:port"]
    D --> E["Server Spring Boot đang chạy"]
    E --> F["Spring Security filter chain"]
    B --> G["Controller"]
    F --> G
~~~

Nếu mục tiêu là kiểm thử HTTP qua mạng, hãy xác nhận **server đang chạy** và client được tạo bằng `bindToServer()` hoặc cơ chế HTTP client tương đương.

## 3. Ứng dụng WebFlux mẫu để kiểm tra authentication thật

Các ví dụ tiếp theo dùng một ứng dụng Reactive nhỏ, chỉ để thấy rõ hiệu ứng của header và cookie. Cấu hình có hai người dùng test với mật khẩu được mã hóa, bật HTTP Basic và form login, đồng thời bảo vệ các endpoint `/api/**`.

### 3.1. SecurityWebFilterChain và test accounts

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class DemoReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService testUsers(
            PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("correct"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-secret"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Đây là các tài khoản fixture cục bộ. Không sao chép mật khẩu trong ví dụ vào hệ thống thực. `httpBasic()` khiến server xử lý header Basic trong request; `formLogin()` hỗ trợ trường hợp login bằng form và session ở phần sau. CSRF mặc định không bị tắt.

Khi vừa bật form login vừa bật Basic, một client không được xác thực có thể nhận **401** hoặc **redirect tới trang login** tùy content negotiation, entry point và cấu hình. Đối với các test Basic, ta gửi `Accept: application/json` và kiểm tra hành vi API. Nếu ứng dụng phân chia nhiều `SecurityWebFilterChain`, hãy bảo đảm URL test khớp chain có Basic authentication.

### 3.2. Controller cho header và cookie

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.http.ResponseCookie;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class HttpRequestDemoController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(user ->
            Map.of("name", user.getName()));
    }

    @GetMapping("/api/admin")
    Mono<String> admin() {
        return Mono.just("admin-only");
    }

    @GetMapping("/demo/request-id")
    String requestId(@RequestHeader("X-Request-ID")
                     String requestId) {
        return requestId;
    }

    @GetMapping("/demo/issue-cookie")
    String issueCookie(ServerHttpResponse response) {
        response.addCookie(
            ResponseCookie.from("demo-pref", "dark")
                .httpOnly(true)
                .path("/")
                .sameSite("Lax")
                .build()
        );
        return "created";
    }

    @GetMapping("/demo/read-cookie")
    String readCookie(
        @CookieValue(name = "demo-pref", defaultValue = "unset")
        String preference
    ) {
        return preference;
    }

    // Endpoint dành riêng cho fixture kiểm thử form login/CSRF.
    @GetMapping("/csrf")
    Mono<CsrfToken> csrf(ServerWebExchange exchange) {
        return exchange.getAttributeOrDefault(
            CsrfToken.class.getName(),
            Mono.empty()
        );
    }
}
~~~

Các endpoint `/demo/**` và `/csrf` được cho phép bởi `anyExchange().permitAll()`, để ta thấy header và cookie một cách độc lập với quyền truy cập. Endpoint `/api/me` vẫn yêu cầu authentication; nó sẽ chứng minh HTTP Basic hoặc session login có thật sự được server chấp nhận.

Endpoint `/csrf` chỉ minh họa cách lấy token từ Reactive security filter chain cho **bộ test**. Một ứng dụng production cần thiết kế việc cung cấp CSRF token phù hợp với kiến trúc giao diện và chính sách bảo mật, đồng thời tránh lộ token qua log hoặc cache không thích hợp.

## 4. Gửi Basic Authorization header thật

Dùng `HttpHeaders.setBasicAuth(...)` để tạo header đúng cấu trúc, thay vì tự nối chuỗi Base64:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

@Test
void correctBasicHeaderAuthenticatesOnLiveServer() {
    client.get()
        .uri("/api/me")
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers ->
            headers.setBasicAuth("alice", "correct"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.name").isEqualTo("alice");
}
~~~

Request được gửi **qua socket HTTP** đến server ở `localhost:port`. Server nhận `Authorization: Basic ...`, kiểm tra username/password bằng `ReactiveUserDetailsService` và `PasswordEncoder`, tạo authentication rồi cho phép handler trả tên người dùng.

Test âm tính:

~~~java
@Test
void wrongPasswordIsRejected() {
    client.get()
        .uri("/api/me")
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers ->
            headers.setBasicAuth("alice", "wrong"))
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void authenticatedUserWithoutAdminRoleIsForbidden() {
    client.get()
        .uri("/api/admin")
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers ->
            headers.setBasicAuth("alice", "correct"))
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void correctAdminMayAccessAdminEndpoint() {
    client.get()
        .uri("/api/admin")
        .accept(MediaType.APPLICATION_JSON)
        .headers(headers ->
            headers.setBasicAuth("admin", "admin-secret"))
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("admin-only");
}
~~~

Trong cấu hình ví dụ, sai mật khẩu dẫn đến **401 Unauthorized**; người đã đăng nhập nhưng không có `ROLE_ADMIN` dẫn đến **403 Forbidden**. Đây là hai nhánh khác nhau: authentication và authorization.

**Đừng dùng `mutateWith(mockUser("alice"))` để thay Basic header** trong test này. Mục tiêu đang là chứng minh server nhận và xử lý credentials từ giao thức HTTP. Mock user chỉ đưa sẵn principal vào test setup.

### 4.1. Header tùy biến, trace ID và nội dung Accept

Với header không liên quan xác thực, dùng `header(...)` hoặc `headers(...)` để gửi yêu cầu thật:

~~~java
@Test
void customHeaderIsVisibleToServer() {
    client.get()
        .uri("/demo/request-id")
        .header("X-Request-ID", "trace-123")
        .accept(MediaType.TEXT_PLAIN)
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("trace-123");
}
~~~

Test này đo dữ liệu do server nhận. Nếu header bị mất hoặc đổi bởi reverse proxy/API gateway, cần chạy client qua chính proxy đó, không chỉ nối `localhost` vào Spring Boot server.

Có thể dùng `defaultHeader(...)` khi một header cần được gửi trên nhiều request, hoặc `mutate()` để tạo client có default headers mới. Tuy nhiên, đối với các ca cần so sánh request có/không có header xác thực, khai báo tường minh ở từng request sẽ dễ kiểm tra hơn.

### 4.2. Khi dùng Bearer JWT hoặc opaque token

Với ứng dụng thật có cấu hình Resource Server, header Bearer phải được gửi như HTTP request:

~~~java
client.get()
    .uri("/api/resource")
    .headers(headers -> headers.setBearerAuth(rawAccessToken))
    .exchange()
    .expectStatus().isOk();
~~~

Điều kiện là endpoint `/api/resource` phải được bảo vệ bởi `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` phù hợp, và `rawAccessToken` là token được môi trường test chấp nhận. Ví dụ này **không chạy với Basic-only resource server** khi chưa cấu hình JWT/opaque token.

Trong WebFlux security tests, `mockJwt()` hoặc `mockOpaqueToken()` có thể thiết lập principal để test authorization trong bộ nhớ. Chúng không thay thế việc gửi Bearer header tới server khi cần kiểm chứng decoder/introspector thực. Kết quả HTTP 200 từ `mockJwt()` không chứng minh chữ ký JWT đã được xác minh.

## 5. Gửi cookie thực qua mạng

Cookie thường có hai giai đoạn:

1. Server trả header `Set-Cookie` trong response.
2. Client gửi lại giá trị trong header `Cookie` của request sau.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: demo-pref=dark; Path=/; HttpOnly; SameSite=Lax
~~~

Sau đó client gửi:

~~~http
GET /demo/read-cookie HTTP/1.1
Cookie: demo-pref=dark
~~~

Với `WebTestClient` bind tới server, bạn có thể đọc cookie từ response và tự chuyển nó vào request tiếp theo.

### 5.1. Test một vòng Set-Cookie → Cookie

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void serverIssuedCookieCanBeSentBackOverHttp() {
    EntityExchangeResult<byte[]> issued = client.get()
        .uri("/demo/issue-cookie")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .returnResult();

    ResponseCookie cookie = issued.getResponseCookies()
        .getFirst("demo-pref");

    assertThat(cookie).isNotNull();
    assertThat(cookie.getValue()).isEqualTo("dark");
    assertThat(cookie.isHttpOnly()).isTrue();

    client.get()
        .uri("/demo/read-cookie")
        .cookie(cookie.getName(), cookie.getValue())
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("dark");
}
~~~

Test này kiểm chứng **server phát hành cookie** và **server đọc đúng cookie do client gửi lại** qua HTTP. Việc gọi `cookie(name, value)` sẽ đặt cookie vào request; không cần tự viết chuỗi `Cookie: ...`.

Đừng hiểu rằng `WebTestClient.bindToServer()` tự động hoạt động như một browser có cookie jar đầy đủ cho mọi request. Trong code test, nên **truyền lại cookie một cách rõ ràng** hoặc thiết lập một HTTP client/cookie management phù hợp với mục tiêu. Không tự giả định rằng `Set-Cookie` từ lần `exchange()` trước sẽ được giữ và gửi ở lần sau.

### 5.2. Cookie không đồng nghĩa với authentication

Cookie `demo-pref=dark` ở ví dụ chỉ lưu sở thích giao diện. Nó **không xác thực người dùng**. Không nên viết test `/api/me` với cookie này rồi kết luận đã đăng nhập.

Authentication cookie của một ứng dụng có thể là `SESSION` (thường gặp với WebFlux/WebSession), `JSESSIONID` (Servlet session), hoặc tên cookie tùy biến. Giá trị đó phải do server tạo sau luồng đăng nhập hợp lệ hoặc do fixture tích hợp phù hợp. Một cookie tự gán như `SESSION=alice` không chứng minh có session đã xác thực trên server.

Nếu ứng dụng dùng cookie để mang JWT hoặc opaque token, cần kiểm tra cơ chế đọc cookie tương ứng đã được cấu hình; resource server mặc định thường tìm Bearer token trong **Authorization header**, không tự lấy JWT từ cookie tùy ý.

## 6. Kiểm thử session login thực với form và CSRF

Trong ứng dụng WebFlux mẫu, `formLogin()` cho phép người dùng đăng nhập bằng HTTP POST và lưu authentication theo session. Mục tiêu ở phần này là:

1. Client lấy CSRF token hợp lệ và cookie session từ server.
2. Client gửi `POST /login` với username/password, CSRF token và cookie của **cùng session**.
3. Client dùng cookie session sau login để gọi `GET /api/me` mà không gửi lại Basic header.

Với cấu hình mặc định WebFlux dùng session và CSRF, một endpoint trả `CsrfToken` như `GET /csrf` trong controller ở trên giúp dựng test có thể quan sát token. Thông thường Spring Security giữ thông tin CSRF trong `WebSession`; nếu ứng dụng dùng repository tùy biến, cách lấy token/cookie cần theo cấu hình đó.

### 6.1. Test form login và truyền session cookie

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.web.reactive.function.BodyInserters;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void formLoginCreatesSessionUsedOnNextHttpRequest() {
    // 1. Lấy CSRF token từ server cùng session hiện tại.
    EntityExchangeResult<Map> csrfResult = client.get()
        .uri("/csrf")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Map.class)
        .returnResult();

    Map csrf = csrfResult.getResponseBody();
    assertThat(csrf).isNotNull();

    String csrfHeader = (String) csrf.get("headerName");
    String csrfValue = (String) csrf.get("token");
    assertThat(csrfHeader).isNotBlank();
    assertThat(csrfValue).isNotBlank();

    ResponseCookie initialSession =
        csrfResult.getResponseCookies().getFirst("SESSION");
    assertThat(initialSession).isNotNull();

    // 2. Gửi form và CSRF qua HTTP, mang cùng SESSION cookie.
    EntityExchangeResult<byte[]> loginResult = client.post()
        .uri("/login")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .cookie(initialSession.getName(), initialSession.getValue())
        .header(csrfHeader, csrfValue)
        .body(BodyInserters.fromFormData("username", "alice")
            .with("password", "correct"))
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectBody()
        .returnResult();

    // Server có thể đổi session ID sau đăng nhập.
    ResponseCookie renewedSession =
        loginResult.getResponseCookies().getFirst("SESSION");

    ResponseCookie activeSession =
        renewedSession != null ? renewedSession : initialSession;

    // 3. Không dùng mockUser() hoặc Basic header ở request tiếp theo.
    client.get()
        .uri("/api/me")
        .cookie(activeSession.getName(), activeSession.getValue())
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.name").isEqualTo("alice");
}
~~~

Ví dụ dành cho **WebFlux với session cookie mặc định `SESSION`**. Nếu ứng dụng thay tên cookie, sử dụng cookie của chính cấu hình đó. Với Servlet, tên phổ biến là `JSESSIONID`, còn cách cung cấp CSRF token/session cũng có thể khác.

**Vì sao phải lấy session từ response login?** Một số chính sách bảo vệ session fixation có thể thay đổi session ID sau khi đăng nhập. Nếu server trả cookie mới, client cần dùng giá trị mới đó. Trong test có CSRF token dựa trên session, request POST phải mang cookie tạo ra lúc lấy CSRF token; dùng token của session A với cookie session B có thể bị 403.

### 6.2. Hai ca âm tính cần phân biệt

Nếu thiếu CSRF token ở `POST /login` mà ứng dụng giữ CSRF protection, request có thể bị chặn bằng **403 Forbidden** trước khi bộ lọc đăng nhập kiểm tra mật khẩu:

~~~java
@Test
void formLoginWithoutCsrfIsForbidden() {
    client.post()
        .uri("/login")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .body(BodyInserters.fromFormData("username", "alice")
            .with("password", "correct"))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Ngược lại, khi gửi CSRF và session hợp lệ nhưng mật khẩu sai, Spring Security form login thường chuyển hướng tới trang lỗi đăng nhập, chẳng hạn `/login?error`, không nhất thiết trả 401. Cần assert failure location và việc request tiếp theo không có authentication; **không chỉ assert 302**, bởi đăng nhập thành công cũng có thể trả redirect.

Nếu ứng dụng chủ đích thiết kế REST login trả JSON/401 hoặc dùng custom login endpoint, hãy kiểm tra hợp đồng HTTP thật của nó. Tránh thay đổi filter chain hoặc tắt CSRF chỉ để cho bài test chạy xanh.

### 6.3. Cookie HttpOnly, Secure, SameSite có ý nghĩa gì?

| Thuộc tính | Ý nghĩa thường gặp | Cách xác minh |
| --- | --- | --- |
| `HttpOnly` | JavaScript trên browser không đọc được cookie bằng `document.cookie` | Đọc `Set-Cookie` và kiểm tra flag trong response |
| `Secure` | Browser chỉ gửi cookie trong ngữ cảnh bảo mật phù hợp | Kiểm tra flag và thử HTTPS/browser nếu cần |
| `SameSite` | Giới hạn gửi cookie trong các tình huống cross-site | Kiểm tra flag, dùng browser test khi cần xác nhận hành vi thật |
| `Path`/`Domain` | Giới hạn URL/host áp dụng cookie | Kiểm tra thuộc tính và kiểm thử ở host/path tương ứng |
| `Max-Age`/`Expires` | Thời gian tồn tại cookie | Kiểm tra giá trị khi server cấp cookie |

Khi bạn gọi `WebTestClient.cookie("name", "value")`, test client có thể chủ động gửi cookie dù chính sách của **browser** sẽ không cho gửi trong một số ngữ cảnh (ví dụ `Secure` trên kết nối không phù hợp hoặc `SameSite` cross-site). Vì vậy, test HTTP server-side xác nhận giá trị cookie tới server, còn test chính sách browser cross-site/TLS cần công cụ hoặc môi trường phù hợp.

Không đưa mật khẩu, access token hoặc session ID thật vào log, screenshot kiểm thử hay assertion failure có chứa toàn bộ header nếu không cần thiết.

## 7. Những loại header khác cần kiểm thử qua mạng

Ngoài `Authorization`, có các trường hợp mà gửi header HTTP thật giúp phát hiện lỗi tích hợp:

| Header | Tình huống thử nghiệm | Lưu ý |
| --- | --- | --- |
| `X-Request-ID` | Request ID đi tới gateway, logging filter hoặc controller | Test server trực tiếp không kiểm chứng proxy bên ngoài |
| `Content-Type` | Server đọc body đúng định dạng | Gửi thực qua HTTP client thay vì tự tạo parsed body |
| `Accept` | Chọn JSON hay HTML; ảnh hưởng authentication entry point | Cùng endpoint có thể trả 401 hoặc redirect |
| `Origin` | CORS preflight hoặc CSRF/origin policy | Phải thử đúng method/header của request thực |
| `X-CSRF-TOKEN` hoặc header tùy biến | POST/PUT/PATCH/DELETE thay đổi trạng thái | CSRF token phải hợp lệ theo repository/session |
| `Authorization: Bearer ...` | JWT/opaque token resource server | Token phải được decoder/introspector tiếp nhận |
| `Forwarded`/`X-Forwarded-*` | Kiểm tra địa chỉ/scheme qua reverse proxy | Cần cấu hình xử lý forwarded headers và test qua proxy khi phù hợp |

Ví dụ kiểm tra request có header `Origin`:

~~~java
client.options()
    .uri("/api/me")
    .header("Origin", "https://ui.example.test")
    .header("Access-Control-Request-Method", "GET")
    .exchange();
~~~

Đây là một yêu cầu CORS preflight được mô phỏng qua HTTP. Kết quả phụ thuộc CORS configuration, Spring Security filter chain và endpoint thực tế; không mặc định rằng mọi application đều phải trả cùng một status hay headers. Hãy so sánh với chính sách CORS đã định của ứng dụng trước khi đặt assertion.

## 8. Reactive WebTestClient và Servlet MockMvc: chọn công cụ cho câu hỏi cần trả lời

`MockMvc` chạy mô phỏng request Servlet trong JVM, không mở socket mạng. Nó đặc biệt phù hợp khi muốn kiểm thử filter chain Servlet với `spring-security-test` như `user()`, `httpBasic()`, `jwt()` hay `formLogin()`.

`WebTestClient` có hai cách sử dụng chính:

1. **Mock server/WebFlux trong bộ nhớ:** nhanh, có thể dùng `mockUser()`, `mockJwt()`, `mockOAuth2Login()` để kiểm tra logic quyền và các WebFilter mà không mở port.
2. **Live server HTTP:** kết nối vào `localhost:randomPort` hoặc URL test, gửi `Authorization`, cookie, CSRF và body theo giao thức HTTP; kiểm tra phản hồi của server đang chạy.

Đối với ứng dụng Servlet, một live `WebTestClient.bindToServer()` vẫn có thể kiểm tra HTTP request tới embedded Tomcat/Jetty/Undertow. Tuy nhiên, configurer mock security của WebFlux không thay thế các công cụ `MockMvc` chuyên cho Servlet. Đối với ứng dụng Reactive, nên dùng WebTestClient với `SecurityWebFilterChain` và các Reactive test configurers khi không cần mạng.

### 8.1. Ba phép thử có kết quả giống nhau nhưng chứng cứ khác nhau

~~~java
// A: Giả lập user trong WebFlux mock-server test.
mockClient
    .mutateWith(mockUser("alice"))
    .get().uri("/api/me")
    .exchange()
    .expectStatus().isOk();

// B: Live server nhận Authorization header thật.
liveClient.get().uri("/api/me")
    .headers(h -> h.setBasicAuth("alice", "correct"))
    .exchange()
    .expectStatus().isOk();

// C: Live server nhận session cookie đã được cấp qua login.
liveClient.get().uri("/api/me")
    .cookie("SESSION", issuedSessionValue)
    .exchange()
    .expectStatus().isOk();
~~~

A có giá trị để kiểm tra hành vi ứng dụng với danh tính được cấp sẵn. B xác nhận HTTP Basic authentication. C xác nhận server phục hồi session từ cookie mà **server đã cấp**; nếu chỉ tự chế một giá trị `issuedSessionValue`, C không có giá trị chứng minh login. Ba kết quả 200 không đồng nghĩa cùng một cơ chế đã được thử.

## 9. Những lỗi thường khiến kiểm thử qua mạng không có ý nghĩa

### 9.1. Tưởng bindToApplicationContext đang gửi HTTP qua cổng thật

`bindToApplicationContext(context)` sử dụng mock request/response trong bộ nhớ. Nó kiểm tra WebFlux pipeline nhưng không đo kết nối TCP, proxy, cổng, TLS hoặc cookie transport. Khi yêu cầu nêu rõ “HTTP qua mạng”, cần `bindToServer()` hoặc client HTTP tương đương.

### 9.2. Dùng mockUser() hoặc mockJwt() thay vì header

Một test nhận `200 OK` với `mockUser("alice")` chưa chứng minh username/password hay token được server kiểm tra. Nếu mục tiêu là Basic authentication, gửi header Basic; nếu là JWT/opaque resource server, gửi Bearer token theo policy của server.

### 9.3. Gửi cookie giả và tưởng server đã đăng nhập

`.cookie("SESSION", "alice")` không phải session thực. Server thường lưu/mã hóa trạng thái session bằng cơ chế riêng; cookie chỉ mang ID hoặc token phiên. Phải lấy cookie từ response sau quy trình hợp lệ rồi gửi lại, hoặc tạo fixture phiên có kiểm soát nếu mục tiêu chỉ là authorization.

### 9.4. Bỏ qua CSRF trong form login

Khi `POST /login` bị 403, nguyên nhân có thể là CSRF token thiếu/sai hoặc cookie session không đúng; không nhất thiết sai mật khẩu. Hãy tách trường hợp CSRF khỏi trường hợp authentication failure.

### 9.5. Cho rằng WebTestClient giữ mọi cookie tự động

Một chuỗi `exchange()` không phải lúc nào cũng có cookie jar giống browser. Nếu request sau không có session cookie, server có thể coi đó là người dùng mới. Lấy `Set-Cookie`, kiểm tra tên/giá trị rồi truyền rõ ràng vào `cookie(...)`.

### 9.6. Dùng localhost để kết luận gateway hoặc HTTPS đã hoạt động

Kết nối trực tiếp tới embedded server không đi qua reverse proxy, TLS terminator, load balancer, WAF hoặc SSO gateway ở môi trường thật. Nếu mục tiêu là các thành phần đó, hãy đặt base URL tới môi trường kiểm thử chứa chúng.

### 9.7. Đọc nhầm 401, 403 và 302

- **401**: thường là chưa xác thực hoặc credentials/token bị từ chối với API entry point.
- **403**: có thể đã xác thực nhưng thiếu quyền, hoặc POST bị CSRF filter từ chối.
- **302/303**: có thể chuyển hướng đến trang login, login thành công hoặc thất bại.

Nên assert thêm response body, `Location`, `WWW-Authenticate` hoặc cookie/session tùy cơ chế. HTTP status một mình chưa luôn giải thích nguyên nhân.

### 9.8. Quên dọn các side effect giữa test

Test live server có thể ghi DB, đổi trạng thái session, tạo cookie hoặc ảnh hưởng nhau khi chạy song song. Dùng test fixture cô lập, dữ liệu hợp lệ cho từng case và cleanup thích hợp. Với request HTTP live, `@Transactional` ở test method không mặc nhiên rollback transaction được xử lý trong server thread giống trường hợp controller được gọi trong cùng transaction của test.

## 10. Ma trận tình huống đề xuất

| Mục tiêu | Client setup | Request test | Assertion chính |
| --- | --- | --- | --- |
| Quyền của role giả lập trong WebFlux | Mock server + Spring Security test | `mutateWith(mockUser("alice"))` | 200/403 theo role |
| Basic credentials đúng | Live `bindToServer()` | `Authorization: Basic ...` | 200, principal đúng |
| Basic password sai | Live `bindToServer()` | Basic header sai | 401 |
| Token Bearer thật | Live `bindToServer()` + resource server | Bearer header | 200/401/403 và claims/quyền tùy token |
| Header request ID | Live `bindToServer()` | `X-Request-ID` | Endpoint nhận đúng giá trị |
| Cookie thông thường | Live `bindToServer()` | Set-Cookie, rồi Cookie | Giá trị cookie round trip |
| Login bằng session | Live `bindToServer()` | GET CSRF, POST login, GET protected với session | Login thành công, request sau 200 |
| Thiếu CSRF | Live `bindToServer()` | POST login thiếu token | 403 nếu CSRF bật |
| Cookie `Secure/SameSite` trong browser | Browser test với đúng origin/scheme | Điều hướng cross-site/TLS thật | Browser có gửi cookie đúng policy |
| Proxy/TLS/gateway | Live client đến môi trường integration | Header/cookie qua gateway | Server, gateway và policy cùng hoạt động |

### Bài thực hành

Từ cấu hình WebFlux mẫu, hãy hoàn thành ba nhóm test:

1. **Headers:** chạy server ở random port, dùng WebTestClient `bindToServer()` gửi Basic header đúng và sai. Kiểm tra 200/401, thêm một request có Basic đúng nhưng thiếu role để nhận 403. Gửi `X-Request-ID` và xác nhận controller nhận cùng giá trị.
2. **Cookies:** gọi `/demo/issue-cookie`, đọc `Set-Cookie`, truyền cookie sang `/demo/read-cookie` và xác nhận giá trị. Thử bỏ cookie ở request sau để thấy server trả mặc định `unset`.
3. **Session:** lấy CSRF token và cookie `SESSION` từ server, POST login với credentials đúng, chuyển cookie mới (nếu được cấp) sang request `GET /api/me`. Xác nhận server trả `alice` ngay cả khi request sau không có header Basic. Thử request không mang cookie để xác nhận không còn authentication từ phiên login.

**Tiêu chí hoàn thành:** Bạn chỉ ra được request nào có **thông tin xác thực được gửi qua HTTP**, cookie nào **thực sự do server cấp**, trạng thái 401/403/redirect phản ánh nhánh bảo mật nào và vì sao một test chỉ dùng `mockUser()` hoặc `mockJwt()` chưa đủ khi yêu cầu là “gửi header hoặc cookie thực qua mạng”. Đây là ranh giới quan trọng giữa kiểm thử authorization trong bộ nhớ và integration test của HTTP authentication/session.

