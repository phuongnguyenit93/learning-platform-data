# Lưu ngữ cảnh sau đăng nhập và xác nhận bằng yêu cầu tiếp theo trong Spring Security WebFlux

## 1. Bài toán và kết quả cần quan sát

Xây dựng ứng dụng Spring Boot dùng **Spring WebFlux + Spring Security**: người dùng đăng nhập thành công bằng biểu mẫu, sau đó gọi **một HTTP request mới** tới tài nguyên cần xác thực. Request thứ hai vẫn nhận diện đúng người dùng mà không gửi lại username/password. Đây là kiểm chứng việc lưu và khôi phục ngữ cảnh xác thực giữa hai request, không chỉ là kiểm tra danh tính trong chính request đăng nhập.

Kết quả mong đợi:

1. Chưa đăng nhập: truy cập `GET /api/me` bị chặn và được hướng tới trang đăng nhập (với cơ chế form login).
2. Đăng nhập thành công bằng `POST /login`, có CSRF token hợp lệ: Spring Security lưu `SecurityContext` trong `WebSession` và trả session cookie cho client.
3. Gửi request hoàn toàn mới tới `GET /api/me` với **cookie của phiên vừa đăng nhập**, không kèm Basic Auth hoặc password: response `200 OK`, body `alice`.
4. Gửi chính request đó **không có cookie hợp lệ**: trở lại trạng thái chưa xác thực. Như vậy kết quả không đến từ biến toàn cục hay một authentication giả lập áp dụng cho tất cả request.

Phạm vi ở đây là **đăng nhập có trạng thái (session-based) trong ứng dụng reactive**. Với REST API dùng Bearer JWT stateless, mỗi request phải gửi token riêng và cơ chế khôi phục `Authentication` sẽ khác.

## 2. Phân biệt Reactor Context với dữ liệu tồn tại qua nhiều request

Trong Spring Security WebFlux:

| Thành phần | Vai trò | Tuổi thọ cần hiểu |
| --- | --- | --- |
| `Authentication` | Principal, authorities, trạng thái xác thực | Là thông tin danh tính, chưa tự quyết định cách lưu |
| `SecurityContext` | Bao bọc `Authentication` | Có thể được lưu hoặc chỉ tồn tại trong chuỗi xử lý hiện tại |
| `ReactiveSecurityContextHolder` | Đọc/đặt `Mono<SecurityContext>` trong **Reactor Context** | Phục vụ luồng reactive được subscribe, không phải bộ nhớ phiên HTTP |
| `ServerSecurityContextRepository` | Hợp đồng `save(exchange, context)` và `load(exchange)` | Kết nối ngữ cảnh với nguồn lưu có thể dùng ở request khác |
| `WebSessionServerSecurityContextRepository` | Lưu `SecurityContext` trong `WebSession` | Tồn tại qua nhiều request nếu client gửi session ID hợp lệ |
| `ReactorContextWebFilter` | Nạp ngữ cảnh từ repository vào Reactor Context | Cho handler và bộ lọc đọc danh tính ở mỗi request |

**Điểm cốt lõi:** `ReactiveSecurityContextHolder.withAuthentication(authentication)` chỉ thêm authentication vào **Reactor Context của một chuỗi publisher**. Nó không tự ghi vào phiên HTTP; một HTTP request mới khởi tạo chuỗi Reactor Context mới. Muốn duy trì đăng nhập kiểu session phải thực hiện cả **save** khi xác thực thành công lẫn **load** ở request kế tiếp.

Đừng dùng cách suy luận của Servlet như gọi `SecurityContextHolder.getContext()` rồi trông chờ một `ThreadLocal` được bảo toàn khi WebFlux chuyển thread. Trong reactive code hãy đọc qua `ReactiveSecurityContextHolder.getContext()` hoặc dùng principal được WebFlux cung cấp.

### Chuỗi xử lý

1. Client gửi `POST /login` gồm credentials và CSRF token.
2. Bộ lọc xác thực của Spring Security kiểm tra credentials qua cơ chế authentication đã cấu hình.
3. Khi thành công, form-login `AuthenticationWebFilter` ghi `SecurityContext` bằng repository của **form login**.
4. Với `WebSessionServerSecurityContextRepository`, dữ liệu nằm trong `WebSession` phía server; client chỉ giữ session ID, thông thường qua cookie `SESSION`. Repository này thay đổi session ID khi lưu context nhằm hạn chế session fixation.
5. Client lưu cookie vừa nhận và gửi cookie đó trên `GET /api/me` mới.
6. `ReactorContextWebFilter` dùng repository được cấu hình ở `ServerHttpSecurity` để tải lại context vào Reactor Context. Quy tắc `authenticated()` cho phép request và controller đọc được `alice`.
7. Nếu cookie không được gửi, hết hạn hoặc phiên đã bị vô hiệu hóa, ngữ cảnh cũ không được khôi phục.

Lưu ý rằng **repository dùng để ghi và repository dùng để đọc phải tương thích**. Chỉ gọi `http.securityContextRepository(repo)` là định cấu hình phần tải context cho `ReactorContextWebFilter`; phần lưu lúc form login phải dùng repository tương ứng. Ví dụ bên dưới cấu hình rõ cả hai để hành vi dễ kiểm chứng. Khi dùng cấu hình form login chuẩn, Spring Security vốn sử dụng `WebSessionServerSecurityContextRepository` làm mặc định cho bước lưu.

## 3. Ví dụ Spring Boot WebFlux chạy được

Môi trường: **Java 17+**, một dự án Spring Boot 3.x tạo bằng Spring Initializr, dùng **Spring Reactive Web** và **Spring Security**. Không đồng thời thêm `spring-boot-starter-web` để tránh vô tình chạy ứng dụng Servlet. Thêm dependency test nếu muốn chạy kiểm chứng tự động ở mục 5.

Trong `build.gradle` của dự án Spring Boot/Gradle đã được cấu hình plugin và dependency management, khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 3.1. Cấu hình xác thực và cùng một repository cho save/load

Tạo `src/main/java/com/example/demo/SecurityConfig.java`:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/me").authenticated()
                        .anyExchange().permitAll())
                // Repository được ReactorContextWebFilter dùng để load.
                .securityContextRepository(repository)
                // Repository được form-login dùng để save khi login thành công.
                .formLogin(form -> form.securityContextRepository(repository))
                // Tắt Basic Auth để phép thử chỉ chứng minh session cookie.
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                // CSRF vẫn bật: không disable để làm cho POST /login dễ qua.
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

Ở ví dụ học tập, người dùng được giữ trong bộ nhớ và mật khẩu `demo-pass` là dữ liệu mẫu. BCrypt chỉ bảo vệ chuỗi mật khẩu được lưu; sản phẩm thực tế cần kho người dùng, quản lý secret và chính sách đăng nhập phù hợp.

Cấu hình trên sử dụng `SecurityWebFilterChain` và `ServerHttpSecurity` của **WebFlux**, không phải `SecurityFilterChain` / `HttpSecurity` của Servlet. `.formLogin(...)` cấp sẵn trang đăng nhập tại `GET /login` và xử lý `POST /login`. Mã của ta không tự viết lại xác thực username/password hoặc tự quản lý HTTP session. Cấu hình `.httpBasic(...disable)` làm cho việc truy cập `/api/me` thành công ở request thứ hai thể hiện **session persistence**, chứ không phải browser ngầm gửi Basic credentials.

### 3.2. Đọc ngữ cảnh trong một handler reactive

Tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class MeController {

    @GetMapping("/api/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }
}
```

`ReactiveSecurityContextHolder.getContext()` lấy context cho request đang xử lý. Trước khi controller chạy, quy tắc `authenticated()` đã yêu cầu xác thực; khi có session hợp lệ, response body là username `alice`. `Mono<String>` được WebFlux subscribe khi tạo HTTP response; không gọi `block()` và không tạo thread riêng để lấy principal.

## 4. Kiểm tra thủ công bằng **hai HTTP request khác nhau**

Khởi động từ thư mục dự án: `./gradlew bootRun` (trên Windows dùng `gradlew.bat bootRun`). Sau khi ứng dụng chạy tại `http://localhost:8080`, thực hiện bằng trình duyệt:

1. Trong cửa sổ riêng tư mới, mở `http://localhost:8080/api/me`. Khi chưa có session đăng nhập, bạn được chuyển tới trang login (kỳ vọng redirect HTTP 3xx với form login). Không có body `alice`.
2. Đăng nhập trên biểu mẫu mặc định bằng `alice` / `demo-pass`. Biểu mẫu do framework sinh ra đi kèm CSRF token cần thiết. Kiểm tra bằng Developer Tools → Network: có request `POST /login`, response thành công thường là redirect và có cookie session hợp lệ.
3. **Sau khi trang login hoàn thành, gõ lại trực tiếp** `http://localhost:8080/api/me` (hoặc refresh ở endpoint). Đây là một request GET mới, không kèm username/password trong URL, body hay header Authorization. Kỳ vọng: `HTTP 200` và nội dung response chính xác là `alice`.
4. Mở cửa sổ riêng tư khác **không chia sẻ cookie**, truy cập cùng URL. Kỳ vọng lại bị yêu cầu đăng nhập. Nếu xóa cookie `SESSION` trong cửa sổ đầu và gọi lại, kết quả tương tự.
5. Đăng xuất đúng cách (sử dụng form `POST /logout` với CSRF token) hoặc đợi session hết hạn; sau đó thử request mới để xác nhận context cũ không còn được chấp nhận.

Một trace HTTP khái quát (headers/cookie/token thật có giá trị khác nhau):

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=<id-truoc-login-neu-co>

username=alice&password=demo-pass&_csrf=<token-hop-le>

HTTP/1.1 302 Found
Set-Cookie: SESSION=<id-phien-sau-login>; Path=/; HttpOnly

GET /api/me HTTP/1.1
Cookie: SESSION=<id-phien-sau-login>

HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

alice
```

Đây là **mô tả trao đổi**, không phải lệnh có thể copy y nguyên: phải lấy CSRF token và cookie do server cấp. Header `Set-Cookie` có thể mang thuộc tính bổ sung; không nên cố định giá trị session ID, trạng thái chuyển hướng hay thuộc tính cookie vào mã ứng dụng.

## 5. Kiểm thử tự động: login thật, mang cookie sang request thứ hai

Cách sau kiểm thử hành vi của form login và repository. Nó **không** dùng `mockUser()` hay `@WithMockUser` để đưa sẵn danh tính vào request thứ hai, vì làm như vậy sẽ không chứng minh context đã được lưu. Dùng `WebTestClient` mock-server, cấu hình Spring Security test support và cung cấp CSRF hợp lệ cho request đăng nhập.

Tạo `src/test/java/com/example/demo/SessionPersistenceTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionPersistenceTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void authenticatedSessionIsRestoredOnNextRequest() {
        // Request 1: gửi form login thật, không đặt principal giả.
        EntityExchangeResult<byte[]> login = client.mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "alice")
                        .with("password", "demo-pass"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody()
                .returnResult();

        ResponseCookie cookie = login.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie, "Login phải tạo session cookie");

        // Request 2: client chỉ gửi session cookie, không gửi credentials.
        client.get()
                .uri("/api/me")
                .cookie("SESSION", cookie.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("alice");

        // Request 3: không mang cookie nên không có quyền truy cập.
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().is3xxRedirection();
    }
}
```

Chạy `./gradlew test --tests com.example.demo.SessionPersistenceTest` (Windows: `gradlew.bat test --tests com.example.demo.SessionPersistenceTest`). Khi test pass, hai quan sát quan trọng nhất là: **request GET thứ hai nhận 200 + `alice`** và **request GET không cookie bị chặn**. `csrf()` là tiện ích dành cho WebTestClient mock-server; ứng dụng thật vẫn phải nhận CSRF token hợp lệ. Nếu project dùng cấu trúc build hoặc tên package khác, điều chỉnh đường dẫn/package/test task tương ứng.

Nếu muốn kiểm tra môi trường production gần thực tế hơn, chạy một HTTP client có cookie jar (hoặc trình duyệt) qua server thật, đăng nhập và **gửi request tiếp theo** với chính session cookie nhận được. Một test chỉ gọi `ReactiveSecurityContextHolder.withAuthentication(...)` hoặc `mockUser()` ở mỗi request không thay thế được bước kiểm chứng này.

## 6. Nếu tự viết endpoint đăng nhập thì lưu thế nào?

Ví dụ trên dùng `formLogin`, nơi Spring Security tự save sau khi xác thực thành công. Nếu thay bằng controller JSON hoặc `AuthenticationWebFilter` tự cấu hình, bạn phải xem **đường nào đang thực sự gọi save**. Không đủ khi chỉ tạo `Authentication`, set `SecurityContext` trong một publisher hoặc trả `200 OK`.

Với một controller đã có `ReactiveAuthenticationManager manager`, `ServerSecurityContextRepository repository` (chung với cấu hình chain), và `ServerWebExchange exchange`, ý tưởng save là:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(username, password);

return manager.authenticate(request)
        .switchIfEmpty(Mono.error(new BadCredentialsException("Invalid credentials")))
        .flatMap(authenticated -> {
            SecurityContext context = new SecurityContextImpl(authenticated);
            return repository.save(exchange, context)
                    .thenReturn(authenticated.getName());
        });
```

**Đây là đoạn logic minh họa bên trong một controller đã có dependencies**, không phải chương trình độc lập hay API đăng nhập hoàn chỉnh. Các class cần import tương ứng: `Authentication`, `UsernamePasswordAuthenticationToken`, `BadCredentialsException`, `SecurityContext`, `SecurityContextImpl` và `Mono`. Khi triển khai thực tế, vẫn phải bảo vệ CSRF, xử lý lỗi xác thực thành HTTP status phù hợp và xác định response contract.

`save(...)` trả về `Mono<Void>`: phải **nối nó vào chuỗi được trả về** như `.flatMap(...).thenReturn(...)` để việc ghi thực sự hoàn thành. Gọi `repository.save(...)` mà không subscribe, hoặc tự `subscribe()` rồi trả response trước khi save xong, dễ khiến request kế tiếp vẫn anonymous. Nếu bạn tự tạo `AuthenticationWebFilter`, phương thức `setSecurityContextRepository(repository)` thiết lập chỗ lưu; theo API, repository mặc định của filter tự tạo là `NoOpServerSecurityContextRepository`, nên phải cấu hình rõ khi cần session persistence.

Ngược lại, nếu thiết kế chủ đích stateless (Bearer token), chọn repository không lưu session là hợp lý; client phải gửi token trên **mỗi** request. Không biến API stateless thành session-based chỉ để làm cho bài kiểm tra thứ hai qua.

## 7. Lỗi phổ biến, cách chẩn đoán và ranh giới bảo mật

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Login báo thành công nhưng GET tiếp theo lại yêu cầu login | Context chỉ nằm trong Reactor Context hiện tại, chưa save, hoặc save vào repository khác repository dùng để load | Kiểm tra save của form login/filter và `ServerHttpSecurity.securityContextRepository(...)` |
| GET sau login không thấy session | Cookie không được client giữ/gửi, sai domain/path, chính sách SameSite/Secure, cross-origin request thiếu credentials | Xem `Set-Cookie` ở response login và `Cookie` ở request GET kế tiếp |
| POST /login trả 403 | Thiếu/sai CSRF token, hoặc session chứa CSRF token đã thay đổi/hết hạn | Lấy token từ trang login, gửi đúng token; đừng tắt CSRF theo phản xạ |
| GET vẫn trả 200 dù không có cookie | Request còn Basic/Bearer credentials, test gắn mock principal, hoặc endpoint vô tình `permitAll()` | Xem Authorization header, bỏ `mockUser()` và giữ `/api/me` trong nhóm authenticated |
| Có context trong `map()` nhưng mất sau khi tạo publisher/thread riêng | Reactor Context không được truyền theo cách thực thi đó | Duy trì một chuỗi reactive và dùng `ReactiveSecurityContextHolder`; tránh dựa vào ThreadLocal |
| Một instance nhận session, instance khác không nhận | Session store chỉ nằm cục bộ từng instance | Dùng shared reactive session store (ví dụ Spring Session + Redis) theo kiến trúc triển khai |
| Trước đăng xuất chạy được, sau đăng xuất vẫn chạy | Cookie cũ/phiên chưa bị vô hiệu hóa hoặc GET thực sự được xác thực bằng cơ chế khác | Kiểm tra logout handler, session invalidation và credential khác gửi kèm |

**Các lưu ý bảo mật có liên quan trực tiếp:**

- Session cookie là thông tin truy cập nhạy cảm: bật HTTPS, dùng `Secure`/`HttpOnly` và `SameSite` phù hợp với luồng web; không log giá trị cookie hoặc session ID.
- Không lưu plaintext password, access token tùy tiện hay cả request body vào `SecurityContext`; chỉ giữ authentication information cần thiết.
- Giữ CSRF protection cho đăng nhập và thao tác thay đổi dữ liệu khi dựa vào cookie tự động gửi từ browser.
- Thiết kế TTL, logout/invalidation, session fixation protection và chiến lược chia sẻ session giữa các instance. `WebSessionServerSecurityContextRepository` hỗ trợ đổi session ID khi lưu context.
- Khi đánh giá bug, phân biệt **đăng nhập thành công trong một request** với **ngữ cảnh được khôi phục ở request mới**: chỉ trường hợp thứ hai mới chứng minh yêu cầu của bài.

## 8. Tiêu chí hoàn thành

Bài thực hành đạt yêu cầu khi bạn có bằng chứng cho đủ chuỗi **login hợp lệ → session cookie được cấp → GET mới chỉ mang cookie → 200/`alice` → GET không cookie bị chặn**. Có thể giải thích rõ vì sao `ReactiveSecurityContextHolder` phục vụ chuỗi reactive hiện tại, còn `WebSessionServerSecurityContextRepository` và `ReactorContextWebFilter` là cặp ghi/đọc giúp xác thực tồn tại qua nhiều HTTP request.

### Tài liệu chính thức để đối chiếu

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security API — FormLoginSpec và securityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security API — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — WebFlux CSRF testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
