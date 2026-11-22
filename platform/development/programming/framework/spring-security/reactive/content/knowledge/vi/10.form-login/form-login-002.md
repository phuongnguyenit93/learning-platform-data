# Cấu hình formLogin và trang đăng nhập mặc định trong Spring Security WebFlux

## Mục tiêu

Bài học giúp bạn hiểu:

1. `ServerHttpSecurity.formLogin(...)` bật luồng đăng nhập bằng biểu mẫu HTML cho **WebFlux**, khác cơ chế Servlet `HttpSecurity.formLogin(...)`.
2. Trang đăng nhập mặc định được Spring Security tạo ở `GET /login`, trong khi `POST /login` được WebFilter của Spring Security dùng để xác thực.
3. Cách username/password, CSRF token, `ReactiveAuthenticationManager`, `WebSession` và `SecurityContext` phối hợp.
4. Cách cấu hình `SecurityWebFilterChain` bằng Java 17+ mà không tự viết controller xử lý mật khẩu.
5. Cách kiểm thử trang mặc định, redirect, credential đúng/sai, CSRF và phân quyền bằng `WebTestClient`.
6. Cách thay trang mặc định bằng một trang Thymeleaf tùy chỉnh, đồng thời giữ nguyên yêu cầu CSRF và quản lý phiên an toàn.

> Phạm vi: Spring Boot 3.x, Spring Security 6.x, Java 17+ và **Spring WebFlux reactive**. `SecurityFilterChain`, `UsernamePasswordAuthenticationFilter` và `HttpSecurity` thường xuất hiện trong tài liệu Servlet/MVC; ví dụ ở đây sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và các reactive WebFilter.

## 1. formLogin là gì?

Đăng nhập bằng biểu mẫu (form login) cho phép người dùng mở một trang HTML, điền username/password và submit bằng HTTP POST. Spring Security nhận credential, xác minh chúng, tạo `Authentication`, rồi quản lý trạng thái đăng nhập và redirect. Controller nghiệp vụ nhận request đã xác thực mà không cần tự kiểm tra password.

Trong Spring Security WebFlux, form login gồm:

- **Login page**: HTML được framework tạo mặc định; hoặc ứng dụng cung cấp HTML riêng.
- **Authentication WebFilter**: xử lý POST form tại đường dẫn được cấu hình.
- **ReactiveAuthenticationManager**: xác thực credential.
- **ReactiveUserDetailsService/PasswordEncoder**: tải user và kiểm tra hash khi dùng username/password authentication.
- **Security context persistence**: lưu/khôi phục xác thực theo session hoặc repository được chọn.
- **Authorization**: quyết định user sau khi login có được phép tới URL tương ứng hay không.
- **CSRF protection**: bảo vệ những request thay đổi trạng thái, gồm login và logout.

Không nhầm "mở trang login" với "đăng nhập thành công". GET trang login thường cho anonymous, còn POST login mới tạo hoặc thay đổi Authentication.

| Cơ chế | Thông tin phía client | Phù hợp với | Lưu ý |
| --- | --- | --- | --- |
| Form login | Body form-encoded username/password và CSRF token; sau đó browser gửi session cookie | Web app có giao diện trình duyệt | Thường **stateful**, phải xử lý session và CSRF |
| HTTP Basic | Header `Authorization: Basic ...` trên request | API client hoặc ví dụ đơn giản | Base64 không phải mã hóa; cần HTTPS |
| JWT resource server | Header Bearer token | API/SPA theo kiến trúc token | Không có nghĩa tự sinh login HTML |
| OIDC/OAuth2 login | Redirect sang identity provider | SSO, đăng nhập tập trung | Có state/nonce/callback và chính sách IdP |

Bạn có thể kết hợp nhiều cơ chế, nhưng behavior của anonymous request có thể phụ thuộc entry point, `Accept` và cách chọn security chain. Demo bên dưới **tắt HTTP Basic** để trình duyệt sử dụng duy nhất form login.

## 2. Trang đăng nhập mặc định hoạt động thế nào?

Khi cấu hình:

```java
.formLogin(Customizer.withDefaults())
```

và không gọi `loginPage(...)`, Spring Security WebFlux sinh trang đăng nhập mặc định.

| HTTP | Đường dẫn | Hành vi khi dùng mặc định |
| --- | --- | --- |
| GET | `/login` | Trả HTML chứa ô username/password và form login |
| POST | `/login` | Filter nhận form và gọi authentication manager |
| GET | `/login?error` | Hiển thị trang login ở trạng thái lỗi sau khi xác thực thất bại |
| GET | `/logout` | Có thể hiển thị trang xác nhận đăng xuất mặc định |
| POST | `/logout` | Xử lý logout khi có CSRF hợp lệ |

**Không viết `@PostMapping("/login")` để xác thực password** trong trường hợp dùng default form login; authentication filter đã phụ trách URL đó. Không cần tự tạo file `login.html` hay `@GetMapping("/login")` khi vẫn dùng trang được framework tạo.

Form mặc định gửi tối thiểu các tham số:

- `username`: tên người dùng, trừ khi cơ chế chuyển đổi credential được tùy chỉnh.
- `password`: password người dùng nhập.
- `_csrf`: token CSRF hợp lệ dành cho session/request hiện tại.

Mẫu HTML sau chỉ **giải thích cấu trúc**, không phải một form chạy được khi giá trị CSRF còn là placeholder:

```html
<form action="/login" method="post">
  <label for="username">Tài khoản</label>
  <input id="username" name="username" autocomplete="username">

  <label for="password">Mật khẩu</label>
  <input id="password" name="password" type="password"
         autocomplete="current-password">

  <input type="hidden" name="_csrf" value="SERVER_GENERATED_TOKEN">
  <button type="submit">Đăng nhập</button>
</form>
```

Đường dẫn `/login` là **đường dẫn mặc định**, không phải yêu cầu mọi ứng dụng dùng đúng URL này: gọi `loginPage("/signin")` sẽ thay đổi behavior. Giá trị `SERVER_GENERATED_TOKEN` không được hardcode vào code thật; nó cần được Spring Security phát và xác nhận.

### Request đi qua filter nào?

```text
Browser: GET /private (chưa đăng nhập)
             |
             v
SecurityWebFilterChain: authorization yêu cầu authenticated()
             |
             v
Authentication entry point -> HTTP redirect /login
             |
             v
Browser: GET /login -> nhận trang form + CSRF token
             |
             v
Browser: POST /login (username, password, _csrf)
             |
             +--> CsrfWebFilter kiểm tra token
             |
             +--> AuthenticationWebFilter của form login
             |        |
             |        v
             |     ReactiveAuthenticationManager
             |        |
             |        +--> Xác minh user/password, trạng thái tài khoản
             |        |
             |        +--> Thành công -> Authentication
             |
             +--> SecurityContext được ghi vào repository/phiên
             |
             +--> Success handler -> redirect đến trang đích
             |
             +--> Nếu thất bại -> failure handler -> /login?error
```

Đây là sơ đồ **khái niệm**. Mỗi filter có thể kết thúc sớm, nên một POST thiếu CSRF thường bị từ chối **trước khi** kiểm chứng password. Nếu app bật nhiều chain, request chỉ đi qua chain được chọn theo matcher/order. Đích redirect thành công do success handler/request cache quyết định; không khẳng định cố định một URL cho mọi cấu hình.

### Vì sao phải giữ thông tin qua session?

Form login thường phục vụ browser: nếu server không giữ trạng thái, người dùng phải gửi password lại ở mỗi request. Spring Security WebFlux mặc định có thể sử dụng `WebSessionServerSecurityContextRepository` để lưu `SecurityContext`; cookie phiên giúp browser liên kết các request sau đó với session. WebSession trong WebFlux thường dùng cookie tên `SESSION` (có thể cấu hình), không mặc nhiên dùng `JSESSIONID` như Servlet.

**WebSession khác Reactor Context**:

| Khái niệm | Phạm vi | Vai trò |
| --- | --- | --- |
| `WebSession` | Qua nhiều HTTP request có cookie phù hợp | Lưu trạng thái server-side |
| `ServerSecurityContextRepository` | Lưu/khôi phục security context theo cơ chế cấu hình | Giữ Authentication giữa request |
| `Reactor Context` | Theo subscription hiện tại | Truyền SecurityContext trong chuỗi WebFlux |
| `PasswordEncoder` | Trong thao tác kiểm chứng credential | Đối chiếu password thô với hash được lưu |

Không lưu raw password trong session, local storage hay log. Không tự tạo session bằng global variable hoặc `ThreadLocal` khi làm reactive.

## 3. Dựng ứng dụng demo với trang mặc định

Dưới đây là **ví dụ Java 17+ đầy đủ về mã nguồn**, chạy trong project Spring Boot 3.x đã có plugin Gradle hoặc Maven phù hợp. Chỉ dùng các tài khoản mẫu cục bộ, không đưa credential này lên môi trường thật.

### 3.1. Dependency

**`build.gradle`** — phần dependencies của project có Spring Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Dự án demo này không thêm `spring-boot-starter-web`: khi cả MVC và WebFlux có trên classpath, Spring Boot thường mặc định chọn Servlet.

Cấu trúc các file:

```text
src/main/java/example/formlogin/
    FormLoginDemoApplication.java
    SecurityConfiguration.java
    ExampleController.java
src/test/java/example/formlogin/
    FormLoginWebTest.java
```

### 3.2. Main class

**`src/main/java/example/formlogin/FormLoginDemoApplication.java`**:

```java
package example.formlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormLoginDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormLoginDemoApplication.class, args);
    }
}
```

### 3.3. SecurityWebFilterChain và người dùng demo

**`src/main/java/example/formlogin/SecurityConfiguration.java`**:

```java
package example.formlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("local-learner-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("local-admin-pass"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(learner, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/favicon.ico").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .httpBasic(basic -> basic.disable())
                .logout(Customizer.withDefaults())
                .build();
    }
}
```

Giải thích:

1. `@EnableWebFluxSecurity` cùng bean `SecurityWebFilterChain` tạo cấu hình bảo mật **reactive**. Không dùng `HttpSecurity` của Servlet.
2. `pathMatchers("/", "/favicon.ico").permitAll()` mở trang chủ; `/admin` cần `ROLE_ADMIN`; mọi URL còn lại cần authentication. Filter tạo trang login mặc định có thể phục vụ `GET /login` trước khi authorization chặn.
3. `formLogin(Customizer.withDefaults())` kích hoạt generated login page và form authentication. Không khai báo `loginPage(...)` nên chưa phải cung cấp template riêng.
4. `httpBasic(basic -> basic.disable())` chỉ tắt HTTP Basic để demo nhất quán với trình duyệt. Không tắt bảo vệ authorization, session hoặc CSRF.
5. `logout(Customizer.withDefaults())` bật xử lý logout. Không biến logout thành GET làm thay đổi trạng thái.
6. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo hash có prefix thuật toán, thường là `{bcrypt}`. Không sử dụng `User.withDefaultPasswordEncoder()` cho mật khẩu production.
7. Hai tài khoản có mật khẩu mẫu hardcode để **thực hành local/test**. Ứng dụng thật dùng source user/secret an toàn, hash thích hợp, quản lý tài khoản và rate limiting.
8. Không có `.csrf(csrf -> csrf.disable())`: **CSRF vẫn được bật mặc định**, đặc biệt cần thiết cho browser session-based login.

### 3.4. Controller demo

**`src/main/java/example/formlogin/ExampleController.java`**:

```java
package example.formlogin;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ExampleController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("Home is public");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "Hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/admin")
    public Mono<String> adminPage() {
        return Mono.just("Admin only");
    }
}
```

Controller không có `@GetMapping("/login")` hay `@PostMapping("/login")`, bởi WebFlux security filter quản lý trang và form mặc định. `ReactiveSecurityContextHolder` lấy principal từ Reactor Context của request; không đọc `SecurityContextHolder.getContext()` đồng bộ như Servlet.

### 3.5. Chạy bằng Gradle

Nếu project có Gradle Wrapper, mở terminal tại root:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Với cổng mặc định 8080 còn trống, mở trình duyệt và quan sát:

1. `http://localhost:8080/` trả `Home is public` dù chưa đăng nhập.
2. `http://localhost:8080/private` chuyển đến `/login` vì yêu cầu authentication.
3. Trang mặc định có trường username/password và CSRF. Nhập `learner` / `local-learner-pass`.
4. Xác thực thành công khiến browser nhận redirect và phiên đăng nhập; `/private` trả `Hello learner`.
5. `/admin` vẫn bị từ chối với learner vì không có `ROLE_ADMIN`.
6. Đăng xuất bằng form/luồng logout rồi đăng nhập `admin` / `local-admin-pass`: truy cập `/admin` nhận `Admin only`.

Tránh chia sẻ screenshot/trace chứa cookie phiên, mật khẩu, token CSRF hoặc header Authorization. Chỉ chạy demo password trên localhost, không deploy nguyên tài khoản mẫu lên server public.

## 4. Các trạng thái HTTP cần phân biệt

| Tình huống | Kết quả điển hình trong demo | Điểm cần hiểu |
| --- | --- | --- |
| GET `/login` | 200 và HTML | Trang do Spring Security tạo |
| GET `/private` chưa đăng nhập | 3xx đến `/login` | Entry point yêu cầu form login |
| POST `/login` không kèm CSRF | Thường 403 | CSRF filter chặn trước khi xét password |
| POST `/login` có CSRF, password sai | 3xx đến `/login?error` | Authentication failure handler |
| POST `/login` có CSRF, password đúng | 3xx đến đích success handler | Đã xác thực và thiết lập session/context |
| GET `/admin` bằng learner đã login | Thường 403 | Đã xác thực, không có vai trò ADMIN |
| GET `/admin` bằng admin đã login | 200 và `Admin only` | Có `ROLE_ADMIN` |
| POST `/logout` hợp lệ | Redirect/hoàn tất logout | Session/security context được xử lý theo cấu hình |

**Form login dùng redirect để yêu cầu browser đăng nhập; không kỳ vọng HTTP 401 cho mọi anonymous browser request** như khi chỉ dùng HTTP Basic. HTTP status/Location có thể đổi với custom entry point, handler, request cache hoặc matcher; hãy kiểm tra behavior thực của ứng dụng.

### "Đăng nhập thành công" khác "được quyền truy cập"

Authentication trả lời **ai là người dùng**. Authorization kiểm tra người dùng được làm gì. `roles("USER")` tạo authority `ROLE_USER`; `roles("ADMIN")` tạo `ROLE_ADMIN`. Spring Security `hasRole("ADMIN")` sẽ tìm authority `ROLE_ADMIN`. Người dùng USER có thể đăng nhập thành công nhưng vẫn nhận 403 trên `/admin`.

### Lưu và khôi phục session

Ở form login mặc định, Spring Security WebFlux thường dùng `WebSessionServerSecurityContextRepository` để lưu Authentication. Browser gửi session cookie trong request sau; Spring Security nạp context vào luồng xử lý khi cần. Đối với deployment nhiều instance, nếu mỗi instance giữ WebSession nội bộ mà không chia sẻ, request sau có thể sang instance khác và bị coi là anonymous. Cần thiết kế session store chia sẻ (ví dụ Spring Session với backend phù hợp) hoặc cơ chế định tuyến được quản trị; không giả định WebFlux không có session chỉ vì nó reactive.

## 5. CSRF: phần không thể bỏ qua khi dùng form

CSRF bảo vệ các hành động thay đổi trạng thái khi browser tự đính cookie của user. Nếu website độc hại khiến trình duyệt nạn nhân gửi POST đến trang của bạn, cookie đăng nhập vẫn có thể được gửi; CSRF token giúp chứng minh request dùng dữ liệu được server phát cho phiên.

Spring Security WebFlux **bật CSRF mặc định**, dùng `CsrfWebFilter`. Khi dùng WebSession, token dự kiến thường được giữ bởi `WebSessionServerCsrfTokenRepository`. Từ Spring Security 6.x, `XorServerCsrfTokenRequestAttributeHandler` có thể che token đầu ra để giảm rủi ro BREACH; không cố so khớp token theo cách tự viết khi framework đã có handler.

Các bước chuẩn:

1. GET `/login` để nhận form và cookie/session liên quan.
2. Spring Security phát CSRF token cho form.
3. Browser POST `username`, `password` và `_csrf` với cookie phù hợp.
4. CSRF filter kiểm tra token trước khi authentication filter xử lý credential.
5. Nếu token sai/thiếu, response có thể 403 ngay cả khi password đúng.
6. Logout bằng POST cũng cần token. Đừng biến `GET /logout` thành thao tác logout tự động nếu không có thiết kế và đánh giá rủi ro.

**Sai lầm thường gặp:** dùng curl POST username/password nhưng không GET trang trước và không giữ cookie/token, sau đó kết luận mật khẩu không đúng vì server trả 403. Đó là lỗi CSRF, khác với xác thực sai password (thường redirect `/login?error` nếu CSRF hợp lệ).

Với frontend SPA dùng cookies và API khác origin, cần thiết kế phù hợp giữa CORS, SameSite cookie và CSRF repository. CORS giới hạn JavaScript của origin khác đọc response; **nó không thay CSRF**. Không tắt CSRF toàn cục chỉ để request thử chạy được.

## 6. Kiểm thử với WebTestClient và spring-security-test

Spring Security Test cung cấp `springSecurity()` để tích hợp security filter vào `WebTestClient`, cùng `csrf()` để gửi token hợp lệ trong test. Ví dụ sau kiểm chứng phân biệt **CSRF**, **authentication**, **authorization**, nhưng không giả vờ rằng mock user chứng minh toàn bộ quá trình login.

**`src/test/java/example/formlogin/FormLoginWebTest.java`**:

```java
package example.formlogin;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormLoginWebTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void defaultLoginPageIsAvailable() {
        client.get().uri("/login")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> assertTrue(html.contains("username")));
    }

    @Test
    void protectedPageRedirectsToLogin() {
        client.get().uri("/private")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueMatches("Location", ".*login.*");
    }

    @Test
    void loginWithoutCsrfIsForbidden() {
        client.post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "learner")
                        .with("password", "local-learner-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordRedirectsToErrorPage() {
        client.mutateWith(csrf())
                .post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "learner")
                        .with("password", "wrong-password"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueMatches(
                        "Location", ".*login\\?error.*");
    }

    @Test
    void correctPasswordProducesSuccessRedirect() {
        client.mutateWith(csrf())
                .post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "learner")
                        .with("password", "local-learner-pass"))
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("learner").roles("USER"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Lệnh chạy:

```bash
./gradlew test --tests example.formlogin.FormLoginWebTest
```

Windows:

```powershell
.\gradlew.bat test --tests example.formlogin.FormLoginWebTest
```

**Kỳ vọng:** sáu test PASS khi project đã đặt đúng các file và dependency. Đây là kết quả dự kiến từ mã mẫu, **không phải log một lần kiểm thử đã chạy**.

Giới hạn cần phân biệt:

- `bindToApplicationContext(context)` dựng mock server gắn với Spring ApplicationContext và security filter; không bắt buộc mở cổng mạng thật.
- `mutateWith(csrf())` cung cấp token test hợp lệ; test wrong-password nhờ đó đánh giá **authentication**, không nhầm lỗi CSRF.
- `mockUser(...)` giả lập authentication cho phép test **authorization**; nó không chứng minh user đã đăng nhập bằng form.
- Test success chỉ kiểm chứng redirect sau POST, chưa chứng minh browser giữ được session cookie qua nhiều request.
- Muốn test end-to-end session thật, thực hiện POST login với token/cookie thật, nhận `Set-Cookie`, rồi gửi cookie đó khi GET `/private`. Dùng browser/HTTP client có cookie jar hoặc test integration bổ sung.

### Quan sát trong Browser Network

Với demo chạy thực, mở DevTools → Network rồi thử login:

| Request | Cần quan sát |
| --- | --- |
| GET `/login` | Response HTML, form action, hidden CSRF, cookie session nếu được cấp |
| POST `/login` | Content-Type form-encoded; username/password/CSRF nằm đúng chỗ |
| Response login | Status 3xx và `Location`; cookie session/headers liên quan |
| GET `/private` sau login | Browser gửi cookie, response trả đúng username |
| GET `/admin` sau login USER | 403 do thiếu authority |
| POST `/logout` | CSRF đúng và session không còn quyền truy cập sau logout |

Không chia sẻ raw Network HAR chứa password, session cookie, token hoặc Authorization header cho nơi không được phép; khi cần đưa log vào issue, phải xóa thông tin nhạy cảm.

## 7. Thay trang login mặc định bằng Thymeleaf

Trong sản phẩm thật, bạn có thể cần giao diện riêng: logo, liên kết khôi phục mật khẩu, hỗ trợ bàn phím, khả năng truy cập và thông báo lỗi theo ngôn ngữ. **Gọi `loginPage("/signin")` chỉ cấu hình đường dẫn; nó không tự sinh HTML của bạn.**

Theo `ServerHttpSecurity.FormLoginSpec.loginPage(String)` trong Spring Security WebFlux 6.x:

- Nếu cấu hình trang mới, trang login/logout mặc định không còn được tự tạo như trước.
- Ứng dụng phải phục vụ GET của trang đó, ví dụ `GET /signin`.
- Khi authentication sai, trang với `?error` cần được render, ví dụ `GET /signin?error`.
- Mặc định form authentication POST đến chính URL mới, ở đây là `POST /signin`.

### 7.1. Dependency bổ sung

Thêm vào dependencies:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
```

### 7.2. Thay bean SecurityWebFilterChain

**Thay thế** method security chain ở mục 3 bằng phiên bản bên dưới. Giữ main class và các bean user/password encoder. Đừng tạo một chain thứ hai match mọi request mà không định nghĩa matcher/order rõ:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/", "/signin", "/css/**").permitAll()
                    .pathMatchers("/admin").hasRole("ADMIN")
                    .anyExchange().authenticated()
            )
            .formLogin(form -> form.loginPage("/signin"))
            .httpBasic(basic -> basic.disable())
            .logout(Customizer.withDefaults())
            .build();
}
```

Dù GET trang login public, các quy tắc Authorization cho `/private` và `/admin` vẫn hoạt động như cũ. Nếu template dùng CSS/ảnh/script cục bộ, bảo đảm tài nguyên tĩnh cần thiết có thể truy cập anonymous nhưng không vô tình mở cả API.

### 7.3. Trang custom và CSRF token

Dùng `@Controller` (không dùng `@RestController`) để trả một view Thymeleaf. CSRF filter có thể cung cấp `Mono<CsrfToken>` qua `ServerWebExchange`; ta để Spring WebFlux subscribe và cung cấp giá trị token cho template.

**`src/main/java/example/formlogin/SignInPageController.java`**:

```java
package example.formlogin;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.reactive.result.view.Rendering;
import reactor.core.publisher.Mono;

@Controller
public class SignInPageController {

    @GetMapping("/signin")
    public Mono<Rendering> signin(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
                exchange.getAttribute(CsrfToken.class.getName());

        return csrf.map(token -> Rendering.view("signin")
                .modelAttribute("_csrf", token)
                .modelAttribute("hasError",
                        exchange.getRequest().getQueryParams()
                                .containsKey("error"))
                .build());
    }
}
```

Với CSRF được bật trong chain này, attribute được kỳ vọng tồn tại. Nếu bạn tùy chỉnh CSRF repository/request handler, phải kiểm tra cách expose token. Không thay bằng chuỗi token cố định hoặc tự gọi `block()` trong controller.

**`src/main/resources/templates/signin.html`**:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
<main>
    <h1>Đăng nhập</h1>
    <p th:if="${hasError}">
        Đăng nhập không thành công. Hãy kiểm tra thông tin.
    </p>

    <form method="post" th:action="@{/signin}">
        <label for="username">Tài khoản</label>
        <input id="username" name="username" type="text"
               autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password" type="password"
               autocomplete="current-password" required>

        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <button type="submit">Đăng nhập</button>
    </form>
</main>
</body>
</html>
```

Spring/Thymeleaf còn tích hợp `CsrfRequestDataValueProcessor` để đưa token vào form method unsafe khi sử dụng `th:action`. Nếu template engine của bạn đã tự sinh hidden CSRF, **không cố tạo thêm input trùng tên**: giữ một đường đưa token phù hợp và kiểm tra HTML render thật. Mã trên cho thấy cách expose token qua model; khi dùng cơ chế tự chèn, bạn có thể bỏ phần input ẩn thủ công. Không gửi token CSRF qua URL nếu không có lý do và đánh giá nguy cơ rò rỉ.

### 7.4. Luồng custom so với mặc định

| Hạng mục | Mặc định | Tùy chỉnh `/signin` |
| --- | --- | --- |
| Trang HTML | Filter tự tạo GET `/login` | Ứng dụng phải render GET `/signin` |
| Submit | POST `/login` | POST `/signin` theo `loginPage("/signin")` |
| Lỗi xác thực | `/login?error` | `/signin?error` cần được view xử lý |
| CSRF | Form mặc định tích hợp sẵn | Controller/template cần tích hợp đúng token |
| Cơ chế password | Authentication manager | Vẫn manager; controller không tự so password |
| Trang logout mặc định | Có thể do framework tạo | Khi custom login phải chủ động thiết kế UI logout |
| Bảo vệ URL | `authorizeExchange` | Vẫn `authorizeExchange` |
| Redirect sau login | Success handler | Có thể tùy biến success handler |

Nếu cần trang GET `/signin` nhưng POST đến URL khác, phải cấu hình đúng `requiresAuthenticationMatcher(...)` và các handler, sửa `form action` đồng thời. Đừng chỉ đổi HTML `action` rồi kỳ vọng filter nhận request ở đường dẫn mới.

### 7.5. Điều hướng khi đăng nhập thành công/thất bại

`ServerHttpSecurity.FormLoginSpec` cho phép gắn `authenticationSuccessHandler(...)` và `authenticationFailureHandler(...)`; cách cấu hình cụ thể phụ thuộc phiên bản. Ví dụ minh họa một success handler redirect đến trang cố định:

```java
.formLogin(form -> form
        .authenticationSuccessHandler(
                new RedirectServerAuthenticationSuccessHandler("/dashboard"))
)
```

Khi sử dụng đoạn trên, cần import class `RedirectServerAuthenticationSuccessHandler` trong package `org.springframework.security.web.server.authentication` và tạo endpoint `/dashboard`. Đây là **một đoạn cấu hình**, không phải lớp Java độc lập. Nếu ứng dụng có request cache/saved request, custom success handler có thể đổi cách quay lại URL mà người dùng mở ban đầu. Không nhận URL redirect tùy ý từ tham số request mà không có allowlist/kiểm tra tránh open redirect.

## 8. Các lỗi thường gặp và cách tìm nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| GET `/login` trả 404 | Form login bị tắt, đã đổi `loginPage` hoặc chain khác được chọn | Kiểm tra bean `SecurityWebFilterChain` và URL login đang dùng |
| GET `/private` không redirect tới login | HTTP Basic/custom entry point, Accept hoặc matcher khác | Kiểm tra HTTP Basic/form login và request headers |
| POST login trả 403 dù password đúng | CSRF thiếu/sai, token và cookie session không khớp | Mở trang login lấy token thật, giữ cookie; không tắt CSRF |
| Sai password nhưng response là redirect `?error` | Form-login failure handler hoạt động bình thường | Đối chiếu user source và encoder; không log raw password |
| Login thành công rồi GET khác vẫn anonymous | Browser không giữ cookie, session store không chia sẻ, SameSite/HTTPS/proxy sai | Kiểm tra session cookie, redirect, proxy và persistence |
| User login được nhưng không vào /admin | Thiếu `ROLE_ADMIN` | Kiểm tra rule `hasRole` và authorities |
| Custom login redirect loop | Route trang login cũng đòi authenticated | Cho phép `/signin` và resources cần thiết |
| Custom POST nhận 404 | Form action khác `loginPage`/matcher | Đồng bộ POST URI với Security form authentication |
| Template không có CSRF input | CSRF Mono chưa được đưa vào model/view | Inspect HTML render và dùng Thymeleaf CSRF integration |
| Ứng dụng có hai chain trùng matcher | Chain ưu tiên khác bắt request | Xác định `@Order` và `securityMatcher(...)` rõ ràng |
| Log/password xuất hiện trong HAR/trace | Logging quá chi tiết | Redact, không ghi password/token/session cookie |
| Dùng `SecurityContextHolder` của Servlet | Không phản ánh Reactor Context khi đổi thread | Dùng `ReactiveSecurityContextHolder` |
| Test dùng `mockUser` rồi kết luận login hoạt động | Chỉ test authorization, bỏ qua password/CSRF/redirect | Thêm test POST form với `csrf()` và password |
| Dùng `.csrf(csrf -> csrf.disable())` để sửa lỗi login | Có thể mở lỗ hổng với browser cookies | Giữ CSRF, sửa token/session đúng cách |

### Thực hành an toàn

- Chỉ gửi credential qua **HTTPS**; áp dụng `Secure`, `HttpOnly`, `SameSite` cho cookie theo mô hình client, và kiểm tra xử lý forwarded headers từ proxy tin cậy.
- Password phải được lưu bằng hàm băm chuyên dụng có work factor, ví dụ BCrypt/Argon2 theo chính sách; không lưu plaintext, không dùng hash nhanh đơn lẻ hoặc `{noop}` cho production.
- Thiết lập session timeout, hạn chế phiên đồng thời khi cần, invalidation lúc logout và sau những thay đổi account quan trọng.
- Giới hạn tốc độ đăng nhập, giám sát lỗi bảo mật và tránh tiết lộ account có tồn tại qua thông báo lỗi.
- Với hệ thống nhiều instance, thiết kế WebSession store/chia sẻ hoặc session affinity phù hợp.
- Kiểm thử cả đăng nhập thành công, không thành công, CSRF, thiếu role, logout và session hết hạn. Test trình duyệt thật bổ sung cho mock WebTestClient.

## 9. Bài tập củng cố

1. Chạy app và quan sát GET `/private` chuyển GET `/login` như thế nào; ghi nhận status và `Location` trong DevTools.
2. So sánh POST `/login` không có CSRF với POST có CSRF nhưng password sai. Giải thích vì sao một request trả 403 còn request kia redirect `/login?error`.
3. Thêm trang `/reports` yêu cầu `ROLE_ADMIN`, thử learner/admin. Phân biệt authentication thành công và authorization thành công.
4. Dùng `loginPage("/signin")`, thêm controller Thymeleaf và kiểm chứng `GET /signin?error` cùng `POST /signin` hoạt động.
5. Tạo success handler redirect tới `/dashboard`, sau đó so sánh với behavior saved request khi mở URL bảo vệ trước login.
6. Viết test end-to-end giữ cùng session cookie qua POST login và GET `/private`, rồi logout và chứng minh request sau bị yêu cầu login.
7. Thay `MapReactiveUserDetailsService` bằng service đọc user từ cơ sở dữ liệu reactive; chứng minh thay nguồn user không đòi tự viết POST controller.
8. Thử cấu hình chạy sau reverse proxy có TLS và cookie SameSite; kiểm tra không lặp redirect, không lộ password và không làm mất CSRF token.

**Ghi nhớ:** Với WebFlux, `formLogin(Customizer.withDefaults())` tạo form login mặc định, Spring Security xử lý POST credential qua filter và bảo vệ bằng CSRF. Việc tùy chỉnh giao diện chỉ thay cách trình bày, không thay trách nhiệm xác thực/password/session/authorization. Giữ một luồng reactive nhất quán, có test bảo mật và không hardcode dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — FormLoginSpec Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security 6.5 — CSRF dành cho WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — Testing CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
- [Spring Framework — WebFlux Rendering API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html)
