# Tùy chỉnh đích chuyển hướng sau đăng nhập thành công hoặc thất bại

> **Bài học:** Đăng nhập biểu mẫu (*form login*) trong **Spring Security reactive / Spring WebFlux**. Nội dung dùng Spring Boot 3.x, Spring Security 6.x và Java 17+. Ta cấu hình `SecurityWebFilterChain` để sau khi người dùng gửi form đăng nhập, **đăng nhập đúng** được chuyển tới `/app/home` và **đăng nhập sai** được chuyển tới `/auth/failed`. Bài giải thích thêm cơ chế *saved request*, CSRF, WebSession, phân quyền và các bẫy *open redirect*.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **đích khi chưa đăng nhập**, **đích sau đăng nhập thành công** và **đích sau đăng nhập thất bại**.
2. Cấu hình `ServerHttpSecurity.formLogin(...)` với `ServerAuthenticationSuccessHandler` và `ServerAuthenticationFailureHandler`.
3. Dùng `RedirectServerAuthenticationSuccessHandler` và `RedirectServerAuthenticationFailureHandler` thay vì viết logic chuyển hướng trong controller xử lý mật khẩu.
4. Hiểu vì sao `RedirectServerAuthenticationSuccessHandler("/app/home")` có thể **ưu tiên saved request hơn đích /app/home**, và biết cách chọn đích cố định khi cần.
5. Hoàn thiện một ứng dụng WebFlux chạy được với trang login do Spring Security tạo, user store reactive và trang thông báo lỗi công khai.
6. Test đúng HTTP `302` và `Location` bằng `WebTestClient` với CSRF token, không vô tình tắt CSRF chỉ để test qua.
7. Tránh vòng lặp redirect, lộ thông tin xác thực, chuyển hướng ra website ngoài ý muốn và nhầm lẫn giữa xác thực với phân quyền.

## 2. Ba tình huống redirect không giống nhau

Trong một ứng dụng web dùng form login, những sự kiện sau xảy ra tại những thời điểm khác nhau:

| Sự kiện | Thành phần xử lý chính | Đích thường gặp |
| --- | --- | --- |
| Người chưa xác thực mở trang được bảo vệ | `ServerAuthenticationEntryPoint` / exception handling | `/login` |
| Người dùng gửi `POST /login` và password đúng | `ServerAuthenticationSuccessHandler` | Saved request hoặc trang mặc định, ví dụ `/` |
| Người dùng gửi `POST /login` và password sai | `ServerAuthenticationFailureHandler` | `/login?error` |
| Người đã xác thực nhưng không có quyền | Authorization / access-denied handling | Thường **403 Forbidden**, không phải “login failed” |
| Form POST thiếu CSRF token | CSRF WebFilter | Thường **403 Forbidden**; failure handler của password chưa chắc được gọi |

**Nhầm lẫn phổ biến:** `.formLogin(form -> form.loginPage("/login"))` **không đặt đích sau đăng nhập thành công**. `loginPage(...)` khai báo trang nhận diện cho flow đăng nhập (và đường xử lý form theo mặc định của FormLoginSpec). Để đổi đích success/failure, hãy cấu hình **`authenticationSuccessHandler(...)`** và **`authenticationFailureHandler(...)`**.

### 2.1 Luồng request trong WebFlux

```text
Browser: GET /app/home (chưa login)
   |
   v
WebFlux SecurityWebFilterChain: chưa xác thực
   |
   +--> entry point điều hướng đến GET /login
                     |
                     v
              Spring Security hiển thị form
              có username, password, CSRF token
                     |
                     v
              Browser: POST /login
                     |
                     v
              AuthenticationWebFilter
                     |
             ReactiveAuthenticationManager
                 /             \
         xác thực đúng       xác thực sai
              |                  |
              v                  v
   ServerAuthentication  ServerAuthentication
      SuccessHandler        FailureHandler
              |                  |
              v                  v
   HTTP 302 Location:   HTTP 302 Location:
       /app/home             /auth/failed
```

Đây là sơ đồ **logic**. WebFilter thật có thứ tự riêng; CSRF có thể dừng POST trước khi xử lý credential, còn authorization cho URL đích được kiểm tra khi browser gửi **GET tiếp theo**. Handler redirect không thể tự đảm bảo người vừa đăng nhập có quyền truy cập trang đích.

## 3. Những API cần nhớ trong Spring Security reactive

| API / lớp | Vai trò |
| --- | --- |
| `ServerHttpSecurity` | DSL cấu hình bảo mật HTTP WebFlux |
| `SecurityWebFilterChain` | Chuỗi WebFilter bảo mật của WebFlux |
| `ServerHttpSecurity.FormLoginSpec` | Cấu hình form authentication trong `.formLogin(form -> ...)` |
| `ServerAuthenticationSuccessHandler` | Contract reactive `onAuthenticationSuccess(WebFilterExchange, Authentication)` trả `Mono<Void>` |
| `ServerAuthenticationFailureHandler` | Contract reactive `onAuthenticationFailure(WebFilterExchange, AuthenticationException)` trả `Mono<Void>` |
| `RedirectServerAuthenticationSuccessHandler` | Handler chuyển hướng sau success; mặc định xét saved request trước fallback location |
| `RedirectServerAuthenticationFailureHandler` | Handler chuyển hướng cố định sau authentication failure |
| `ServerRequestCache` | Lưu request bị gián đoạn do cần login, để có thể quay lại sau đăng nhập |
| `NoOpServerRequestCache` | Cache không lưu/khôi phục request; dùng khi chủ động muốn đích cố định |
| `DefaultServerRedirectStrategy` | Thực hiện HTTP redirect theo một `URI` trong WebFlux |
| `ReactiveUserDetailsService` / `ReactiveAuthenticationManager` | Kiểm tra username/password và tạo kết quả xác thực |

**Chọn đúng stack:** Spring MVC Servlet dùng `HttpSecurity`, `SecurityFilterChain`, `AuthenticationSuccessHandler` của Servlet và `HttpServletResponse.sendRedirect(...)`. **Không dùng các API Servlet đó** bên trong WebFlux `ServerHttpSecurity`. Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng xuất hiện, Spring Boot mặc định thường ưu tiên MVC; cần kiểm tra ứng dụng thực sự chạy WebFlux trước khi áp dụng ví dụ reactive.

## 4. Quy tắc mặc định và lý do phải quan tâm saved request

Giả sử người dùng ban đầu mở `/reports/monthly` khi chưa login. Security redirect họ tới `/login`, đồng thời request cache có thể lưu `/reports/monthly`. Sau khi xác thực thành công:

1. `RedirectServerAuthenticationSuccessHandler` kiểm tra có URL/request cần tiếp tục trong request cache hay không.
2. **Nếu có saved request**, nó có thể redirect tới URL được lưu.
3. **Nếu không có**, nó redirect tới fallback location, mặc định là `/` hoặc đường dẫn bạn cấu hình trong constructor.

Vì vậy:

```java
new RedirectServerAuthenticationSuccessHandler("/app/home");
```

**không nhất thiết ép mọi phiên đăng nhập về `/app/home`**. Constructor này đặt **fallback location**; Javadoc của handler xác nhận saved request được ưu tiên. Đây là điểm thường khiến test khi “đăng nhập trực tiếp từ /login” pass nhưng trình duyệt sau khi truy cập một protected link lại đi sang trang khác.

### 4.1 Ba chính sách lựa chọn

| Mong muốn sản phẩm | Giải pháp phù hợp |
| --- | --- |
| Cho người dùng tiếp tục trang họ muốn mở trước khi login | Giữ `ServerRequestCache` và success handler có xử lý saved request |
| **Luôn** đi đến `/app/home` khi login thành công | Cấu hình `NoOpServerRequestCache` cho cả chain và success handler, hoặc custom success handler trực tiếp redirect tới URL cố định |
| Đích phụ thuộc role, tenant hoặc quy tắc nghiệp vụ | Custom `ServerAuthenticationSuccessHandler` hoặc routing đã kiểm chứng; chỉ redirect tới các đích **được server cho phép** |

Đừng chọn “return URL” trực tiếp từ query param mà không kiểm tra. Nếu chuyển hướng theo dữ liệu user cung cấp, cần whitelist path nội bộ, tránh URL tuyệt đối đến domain lạ hoặc path dạng `//attacker.example`, và không cho người dùng đưa quyền truy cập khác vào redirect logic.

## 5. Chuẩn bị project thực hành

Tạo ứng dụng Spring Boot **3.x**, Java **17+**, Gradle Groovy, chọn:

- **Spring Reactive Web** — `spring-boot-starter-webflux`;
- **Spring Security** — `spring-boot-starter-security`;
- **Spring Boot Test** — `spring-boot-starter-test`;
- **Spring Security Test** — `spring-security-test`, dùng cho kiểm thử CSRF.

Phần dependencies của `build.gradle` trong project đã cấu hình Spring Boot plugin và dependency management:

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

**Không thêm `spring-boot-starter-web` cho ví dụ này.** Dự án dùng WebFlux server và WebFilter chain, không dùng Spring MVC.

Cấu trúc file:

```text
src/main/java/com/example/redirectlogin/
  RedirectLoginApplication.java
  LoginSecurityConfig.java
  PageController.java
src/test/java/com/example/redirectlogin/
  FormRedirectTest.java
```

Các class là **file Java riêng** trong cùng package `com.example.redirectlogin`. Không ghép nhiều `public class` trong một file. Với Gradle, chạy `./gradlew bootRun` hoặc `./gradlew test`. Trên Windows PowerShell, dùng `.\gradlew.bat` thay vì `./gradlew`.

### 5.1 Class khởi động

`src/main/java/com/example/redirectlogin/RedirectLoginApplication.java`:

```java
package com.example.redirectlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedirectLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedirectLoginApplication.class, args);
    }
}
```

`@SpringBootApplication` quét `LoginSecurityConfig` và `PageController` trong cùng package. Ví dụ không cần template engine vì **Spring Security sẽ tạo trang login mặc định** khi bạn cấu hình form login và không thay `loginPage(...)`.

## 6. Cấu hình chuyển hướng success và failure trong SecurityWebFilterChain

`src/main/java/com/example/redirectlogin/LoginSecurityConfig.java`:

```java
package com.example.redirectlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class LoginSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("READER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ReactiveAuthenticationManager passwordAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain webSecurity(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager passwordAuthenticationManager) {

        // Đích CỐ ĐỊNH khi login thành công.
        var success = new RedirectServerAuthenticationSuccessHandler(
            "/app/home"
        );

        // Không dùng saved request để ghi đè "/app/home".
        var noSavedRequest = NoOpServerRequestCache.getInstance();
        success.setRequestCache(noSavedRequest);

        // Đích CỐ ĐỊNH khi xác thực username/password thất bại.
        var failure = new RedirectServerAuthenticationFailureHandler(
            "/auth/failed"
        );

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/auth/failed", "/public/**")
                    .permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .requestCache(cache -> cache.requestCache(noSavedRequest))
            .formLogin(form -> form
                .authenticationManager(passwordAuthenticationManager)
                .authenticationSuccessHandler(success)
                .authenticationFailureHandler(failure)
            )
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .build();
    }
}
```

**Những điểm quan trọng trong cấu hình trên:**

1. `.formLogin(form -> ...)` bật form authentication trong WebFlux. Khi không gọi `form.loginPage(...)`, Spring Security có thể tạo trang login mặc định tại **`GET /login`** và xử lý credential tại **`POST /login`**. Login form dùng các trường `username`, `password`; CSRF token cần được gửi với POST.
2. `.authenticationSuccessHandler(success)` quyết định phản hồi **sau khi credentials đã được xác thực**. Ở đây `RedirectServerAuthenticationSuccessHandler` đưa client tới `/app/home`.
3. `.authenticationFailureHandler(failure)` áp dụng khi form authentication **đã được thử và thất bại**, ví dụ sai password. Response redirect tới `/auth/failed` — route này phải tồn tại và được phép truy cập không cần login.
4. `NoOpServerRequestCache` được dùng trong cả success handler **và** cấu hình `requestCache` của chain. Nhờ vậy request đến URL protected trước login không làm redirect thành công ưu tiên URL đã lưu; đây là **chính sách đích cố định**, không phải cách duy nhất để thiết kế form login.
5. `.httpBasic(...disable)` tắt HTTP Basic trong **chain của demo** nhằm giảm các cơ chế authentication cạnh tranh. Nó **không làm mất** form login hay authorization.
6. `passwordAuthenticationManager` là `UserDetailsRepositoryReactiveAuthenticationManager` sử dụng `MapReactiveUserDetailsService` và `PasswordEncoder`. Ta cấu hình tường minh để tránh nhầm việc handler redirect chịu trách nhiệm kiểm tra mật khẩu: **không**, manager mới xác thực.
7. `.pathMatchers("/admin/**").hasRole("ADMIN")` là policy authorization sau login. `reader` có thể đăng nhập thành công nhưng vẫn **403** khi mở trang admin. Success redirect không thay thế kiểm tra quyền của URL đích.
8. `.pathMatchers("/login", "/auth/failed", "/public/**").permitAll()` tránh redirect vòng lặp cho trang login và trang thông báo lỗi. `POST /login` cũng phải được phép đi tới authentication filter phù hợp; không tạo rule chặn login POST.
9. **CSRF protection được giữ nguyên**, không có `csrf(...disable)`. Đây là điều quan trọng cho browser form login. Việc bỏ CSRF sẽ làm demo ngắn đi nhưng **không phải** một phương án an toàn để dạy form login.

**Giới hạn ví dụ:** Password demo được viết trực tiếp trong mã để người học chạy local. Production nên dùng kho người dùng/IdP đáng tin, password hash phù hợp và quản lý bí mật; tuyệt đối không hardcode tài khoản thật. Form login phải dùng HTTPS/TLS và cookie session bảo mật.

### 6.1 Vì sao cấu hình manager tường minh?

`MapReactiveUserDetailsService` đáp ứng hợp đồng `ReactiveUserDetailsService`, nhưng manager cụ thể mới xử lý credential, kiểm `PasswordEncoder.matches(...)`, tình trạng user và tạo `Authentication` đã được xác thực. `UserDetailsRepositoryReactiveAuthenticationManager` là manager tích hợp của Spring Security dành cho user details reactive.

Ta khai báo bean `ReactiveAuthenticationManager` và truyền vào `form.authenticationManager(...)` để ví dụ độc lập với những mặc định auto-config khác có thể xuất hiện trong dự án thật. Với OAuth2 login hay JWT Resource Server, cơ chế authentication khác; không dùng form redirect handler như cách tự xác thực token.

## 7. Các endpoint minh họa

`src/main/java/com/example/redirectlogin/PageController.java`:

```java
package com.example.redirectlogin;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/app/home",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> home() {
        return username().map(name -> "Welcome " + name);
    }

    @GetMapping(
        value = "/admin/home",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> adminHome() {
        return username().map(name -> "Admin area: " + name);
    }

    @GetMapping(
        value = "/auth/failed",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> loginFailed() {
        return Mono.just("Login failed. Return to /login and try again.");
    }

    private Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

**Tại sao `/auth/failed` là endpoint công khai?** Nếu một user vừa nhập password sai, họ **chưa có session authenticated hợp lệ**. Nếu `/auth/failed` bị bảo vệ, request sau redirect lại bị đưa về `/login` hoặc lỗi access, người dùng không nhìn thấy thông báo thất bại. Bởi vậy route này được `permitAll` và hiển thị thông điệp chung, không tiết lộ username có tồn tại hay không.

**Tại sao `/app/home` vẫn cần bảo vệ?** Nếu không có `anyExchange().authenticated()`, một người không login vẫn có thể tự nhập URL đó. Redirect sau login chỉ là **điều hướng UX**, không tạo access policy.

## 8. Chạy và quan sát redirect bằng trình duyệt hoặc curl

Từ thư mục project:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Với cấu hình mặc định, ứng dụng thường nghe tại `http://localhost:8080`. Dùng HTTP local chỉ cho thực hành với password giả; production bắt buộc HTTPS/TLS.

### 8.1 Truy cập protected endpoint trước login

```bash
curl -i http://localhost:8080/app/home
```

Kỳ vọng tương ứng với form entry point:

```text
HTTP 302 Found
Location: /login
```

Nội dung trên chỉ minh họa **status và Location** quan trọng; phiên bản framework có thể thêm headers/cookies khác. HTTP 3xx ở đây **không phải success redirect**, mà là **entry point redirect** vì request chưa được xác thực.

### 8.2 Mở trang login

```bash
curl -i http://localhost:8080/login
```

Khi chưa thay `loginPage`, Spring Security tạo trang HTML mặc định với form username/password. Trang này có cơ chế chèn CSRF token cần thiết vào POST trong cấu hình chuẩn. Thay vì tự copy token từ một response rồi post từ session khác, hãy mở **`/login` trên browser**, nhập:

- Username `reader`; password `reader-demo-password` → đăng nhập thành công.
- Nhập password sai → chuyển sang `/auth/failed`.

Để test thủ công bằng curl mà vẫn giữ CSRF, phải **lưu cookie session** từ GET trang login, lấy đúng `_csrf` hidden field rồi gửi POST với cùng cookie:

```text
1. GET /login
   <- Set-Cookie: SESSION=... (nếu session được tạo)
   <- HTML form: hidden input name="_csrf", value="..."
2. POST /login
   Cookie: SESSION=...
   Content-Type: application/x-www-form-urlencoded

   username=reader&password=reader-demo-password&_csrf=<token>
3. <- HTTP 302 Location: /app/home
4. GET /app/home cùng cookie session đã được cập nhật
   <- HTTP 200 body "Welcome reader"
```

Đây là **sơ đồ thao tác**, không phải raw HTTP đã đo được hoặc công thức shell hoàn chỉnh. Token và cookie được tạo theo session, nên thay chúng bằng dữ liệu thực từ cùng một client. Sau đăng nhập, server có thể đổi session identifier vì bảo vệ session fixation; client phải nhận cookie mới nếu có.

### 8.3 Luồng thất bại

Nếu gửi POST `/login` với mật khẩu sai nhưng **CSRF hợp lệ**:

```text
POST /login (username=reader, password=wrong, CSRF hợp lệ)
      -> authentication manager từ chối
      -> RedirectServerAuthenticationFailureHandler
      -> HTTP 302 Location: /auth/failed
GET /auth/failed
      -> HTTP 200
      -> Login failed. Return to /login and try again.
```

Vì failure handler đã chuyển hướng, **phản hồi POST có thể là 302 chứ không phải 401**. Lỗi 401/403 thường xuất hiện trong API, Basic/Bearer hoặc authentication/authorization policy khác; **đừng cố ép form login phải trả 401 khi sai password**.

CSRF không hợp lệ là câu chuyện khác: request có thể nhận **403** ngay tại CSRF WebFilter, trước khi password manager được gọi. Trường hợp ấy **không phải** “failure redirect sang /auth/failed”, vì đây không phải sai password trong form authentication.

## 9. Kiểm thử bằng WebTestClient và CSRF mutator

Với `spring-security-test`, có thể kiểm thử form login qua **mock WebFlux application context**, không cần mở cổng mạng. `SecurityMockServerConfigurers.springSecurity()` gắn hỗ trợ Spring Security cho `WebTestClient`. `SecurityMockServerConfigurers.csrf()` cấp CSRF token hợp lệ để test một POST vốn phải đi qua CSRF protection.

Tạo `src/test/java/com/example/redirectlogin/FormRedirectTest.java`:

```java
package com.example.redirectlogin;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class FormRedirectTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousProtectedPageRedirectsToLogin() {
        client.get()
            .uri("/app/home")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login");
    }

    @Test
    void generatedLoginPageIsPublic() {
        client.get()
            .uri("/login")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validCredentialsRedirectToFixedHome() {
        client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "reader"
            ).with(
                "password", "reader-demo-password"
            ))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/app/home");
    }

    @Test
    void invalidCredentialsRedirectToFailurePage() {
        client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "reader"
            ).with(
                "password", "wrong-password"
            ))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/auth/failed");
    }

    @Test
    void missingCsrfIsForbiddenNotPasswordRedirect() {
        client.post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "reader"
            ).with(
                "password", "reader-demo-password"
            ))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void failurePageIsPublic() {
        client.get()
            .uri("/auth/failed")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo(
                "Login failed. Return to /login and try again.");
    }

    @Test
    void publicPingDoesNotRequireLogin() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("pong");
    }
}
```

**Giải thích kỹ test:**

- `@SpringBootTest(webEnvironment = MOCK)` dựng application context thực về bean/config nhưng không cần real HTTP socket. `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` áp dụng security của context trong test.
- `mutateWith(csrf())` của `spring-security-test` chuẩn bị một request có CSRF token hợp lệ cho **mock exchange**. Nó **không thay thế** kiểm thử cookie/session/CSRF qua trình duyệt hoặc live HTTP server nếu cần kiểm chứng end-to-end.
- POST form dùng `Content-Type: application/x-www-form-urlencoded`, field `username` và `password`. Nếu gửi JSON body mà không đổi converter, login form mặc định không đọc dữ liệu theo cách bạn nghĩ.
- `expectStatus().is3xxRedirection()` không giả định chính xác một status 302/303/307 ở mọi custom strategy; `expectHeader().valueEquals(Location, ...)` xác minh **đích chuyển hướng**, trọng tâm bài.
- Test invalid credential có CSRF **hợp lệ** nên mới đi đến authentication failure handler. Test thiếu CSRF kiểm tra phản hồi **403**, không được đánh đồng với password sai.
- Các test này **không chứng minh session được lưu và được dùng qua nhiều request thật**. Muốn chứng minh điều đó, viết thêm live server test giữ cookie/session sau POST hoặc thử bằng browser.
- Nếu sử dụng nhiều `SecurityWebFilterChain` trong ứng dụng thật, mock context phải chứa đúng chain và matcher; một test slice chỉ import Controller có thể bỏ qua security config.

Chạy bằng Gradle:

```bash
./gradlew test --tests '*FormRedirectTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*FormRedirectTest'
```

Các kết quả 3xx/403/200 trong test là **kỳ vọng từ cấu hình ví dụ**. Nếu dự án đã thay thế login page, request matcher, csrf repository, session management hoặc success handler, hãy dùng các giá trị tương ứng; không copy test rồi bỏ mọi tính năng bảo mật để làm xanh kiểm thử.

## 10. Giữ saved request hay chuyển hướng cố định?

Hai chính sách có trải nghiệm khác nhau và đều có trường hợp phù hợp.

### 10.1 Chính sách A: quay về URL người dùng muốn mở trước login

Nếu bạn muốn người dùng mở `/reports/monthly`, bị yêu cầu đăng nhập, rồi quay lại đúng trang đó, hãy giữ `WebSessionServerRequestCache` và success handler có hỗ trợ saved request.

Ví dụ **mảnh cấu hình thay thế**:

```java
var success = new RedirectServerAuthenticationSuccessHandler(
    "/app/home"
);

// KHÔNG success.setRequestCache(NoOpServerRequestCache.getInstance()).
// Giữ request cache và request-cache filter tương thích.
return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/login", "/auth/failed").permitAll()
        .anyExchange().authenticated())
    .formLogin(form -> form
        .authenticationSuccessHandler(success)
        .authenticationFailureHandler(
            new RedirectServerAuthenticationFailureHandler(
                "/auth/failed")))
    .build();
```

Đoạn này chỉ **minh họa phần return của bean security**, cần import và manager/user store tương ứng như ví dụ chính. Khi đã có request được lưu, saved URL có thể được ưu tiên hơn `/app/home`; nếu login trực tiếp, fallback vẫn là `/app/home`. Cần quyết định điều gì xảy ra với URL GET ban đầu, query params nhạy cảm, role thiếu quyền và nhiều tab của cùng session.

**Khuyến nghị:** Chỉ khôi phục URL thuộc phạm vi ứng dụng tin cậy, không nhận URL bên ngoài từ client một cách mù quáng. Nếu ứng dụng qua proxy, phải kiểm soát forwarded headers và host để tránh redirect tới host bị giả mạo.

### 10.2 Chính sách B: luôn chuyển tới dashboard

Ví dụ chính ở mục 6 thực hiện chính sách này bằng hai chỗ:

```java
var cache = NoOpServerRequestCache.getInstance();
var success = new RedirectServerAuthenticationSuccessHandler(
    "/app/home"
);
success.setRequestCache(cache);

http.requestCache(requestCache -> requestCache.requestCache(cache));
```

Đây là **snippet** nằm trong method cấu hình. Tác dụng:

- Security không lưu request mục tiêu bằng request cache của flow này.
- Success handler không chọn saved request để ghi đè `/app/home`.
- Người dùng nhập đúng credential sẽ nhận redirect tới đích cố định.
- Quyền truy cập `/app/home` vẫn phải do `authorizeExchange` kiểm soát.

**Quan trọng:** “Không lưu saved request” **không đồng nghĩa “không dùng WebSession”**. Form login vẫn có thể lưu SecurityContext vào `WebSessionServerSecurityContextRepository` để người dùng không phải gửi lại password ở mỗi request. Đừng thay `ServerSecurityContextRepository` bằng NoOp chỉ vì muốn đích redirect cố định: thao tác đó có thể làm login thành công nhưng request tiếp theo lại không còn danh tính.

## 11. Đích redirect phụ thuộc role: ví dụ nâng cao

Khi người dùng có `ROLE_ADMIN` nên tới `/admin/home`, còn người dùng thông thường tới `/app/home`, có thể viết một `ServerAuthenticationSuccessHandler` tự chọn **đường dẫn nội bộ đã được kiểm soát**.

Mã sau là **đoạn thay thế success handler** trong `LoginSecurityConfig`, không phải class hoàn chỉnh đứng một mình:

```java
import java.net.URI;

import org.springframework.security.web.server.DefaultServerRedirectStrategy;
import org.springframework.security.web.server.ServerRedirectStrategy;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

ServerRedirectStrategy redirects = new DefaultServerRedirectStrategy();

ServerAuthenticationSuccessHandler successByRole =
    (webFilterExchange, authentication) -> {
        boolean admin = authentication.getAuthorities().stream()
            .anyMatch(authority ->
                "ROLE_ADMIN".equals(authority.getAuthority()));

        URI destination = URI.create(
            admin ? "/admin/home" : "/app/home"
        );

        return redirects.sendRedirect(
            webFilterExchange.getExchange(), destination
        );
    };

// Trong formLogin(...) của bean SecurityWebFilterChain:
.formLogin(form -> form
    .authenticationManager(passwordAuthenticationManager)
    .authenticationSuccessHandler(successByRole)
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler(
            "/auth/failed")))
```

**Không dán cả đoạn trên sau `http.build()`.** Để biên dịch, đưa các import lên đầu file Java, đặt biến `redirects` và `successByRole` **bên trong method cấu hình**, rồi thay phần `formLogin(...)` của ví dụ chính. Mẫu này dùng đúng API reactive `ServerRedirectStrategy.sendRedirect(ServerWebExchange, URI)`, **không phải** Servlet `RedirectStrategy.sendRedirect(HttpServletRequest, HttpServletResponse, String)`.

Các lưu ý:

1. `Authentication` đi vào success handler phải là **kết quả của authentication manager đã xác thực**; không lấy role từ query parameter `role=admin`.
2. Chỉ dùng danh sách path do server đặt ra. Không nối chuỗi kiểu `"/" + request.getQueryParams().getFirst("next")` để redirect vì có thể gây open redirect, path traversal hoặc điều hướng tới vùng không mong muốn.
3. `/admin/home` phải có rule `hasRole("ADMIN")`. Redirect chọn admin page **không phải** cơ chế cấp role. Nếu server chọn nhầm path, authorization vẫn phải chặn.
4. Việc custom success handler như trên **không tự xử lý saved request**. Nó chủ động redirect trực tiếp; nếu cần behavior quay về saved request, phải thiết kế rõ thứ tự ưu tiên và dùng đúng `ServerRequestCache`.
5. Không viết logic blocking I/O trong reactive handler; nếu cần tra role/tenant từ repository reactive, kết hợp `Mono.flatMap(...)` rồi trả `Mono<Void>`, không `block()`.
6. Trong Spring Security 6.3+, `FormLoginSpec.authenticationSuccessHandler(Consumer<List<ServerAuthenticationSuccessHandler>>)` có thể phối hợp danh sách handlers; khi sử dụng nó phải hiểu thứ tự và semantics. Bài đơn giản này dùng overload **một handler** để tránh hành vi chồng chéo.

## 12. Đổi trang login và đổi đích redirect là hai thao tác độc lập

Nếu cần giao diện riêng tại `GET /sign-in`, bạn có thể viết:

```java
.formLogin(form -> form
    .loginPage("/sign-in")
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/app/home"))
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler(
            "/sign-in?error")))
```

Đây là **mảnh cấu hình để giải thích API**, chưa đủ là ứng dụng hoàn chỉnh. Sau khi dùng `.loginPage("/sign-in")`:

- Spring Security **không tự tạo trang login mặc định** cho đường dẫn mới.
- Ứng dụng phải thực sự cung cấp `GET /sign-in` và trang/response HTML thích hợp.
- Theo `FormLoginSpec` của Spring Security 6.x, POST xử lý credential mặc định sẽ đi tới **`/sign-in`** khi custom login page như vậy.
- Form phải gửi `username`, `password` và CSRF token hợp lệ; thêm thông báo khi query `error` xuất hiện.
- Đưa `/sign-in` và trang liên quan vào danh sách public routes; nếu không, có thể redirect loop.
- Nếu vẫn muốn fixed success path, cần lưu ý saved request như mục 10. Chỉ đổi `loginPage` không đổi saved-request policy.

Nếu dùng Thymeleaf làm template, thư viện có tích hợp CSRF thuận tiện. Nếu dựng HTML thuần/SPA, phải lấy CSRF token đúng từ WebFlux `ServerWebExchange` hoặc repository được cấu hình, thêm hidden input hay header hợp lệ; không copy token cố định vào HTML. Spring Security 6.x dùng CSRF request handling có bảo vệ BREACH, vì thế cách expose raw/masked token cần tương thích với handler hiện hành.

## 13. Phân biệt các failure ngoài password sai

Không phải mọi trạng thái 3xx/401/403 đều chạy `ServerAuthenticationFailureHandler`:

| Tình huống | Thành phần chịu trách nhiệm | Kết quả thường gặp trong bài |
| --- | --- | --- |
| GET protected khi chưa login | Authentication entry point | 302 tới `/login` |
| POST `/login` thiếu CSRF | CSRF protection | 403, **không** redirect tới `/auth/failed` |
| POST `/login` sai password | Authentication manager → failure handler | 302 tới `/auth/failed` |
| POST `/login` đúng password | Authentication manager → success handler | 302 tới `/app/home` |
| Reader sau login truy cập `/admin/home` | Authorization | 403 |
| GET `/auth/failed` khi chưa login | Rule `permitAll` | 200 |
| Truy cập `/app/home` sau session hết hạn | Authentication entry point | Thường redirect tới `/login` |
| GET URL không có handler, không bị security chặn | WebFlux routing | 404 |

Nếu mục tiêu là **REST API** gọi bằng `fetch`/`WebClient` muốn JSON lỗi, cách redirect kiểu browser có thể không phù hợp: client có thể tự follow 302 rồi nhận HTML thay vì phản hồi 401/403 JSON. Với API nên dùng `ServerAuthenticationEntryPoint`/failure handler phù hợp loại request, hoặc một security chain riêng cho API; với browser dùng form login và redirect.

### 13.1 CSRF không phải password failure

Khi thiếu CSRF, request POST bị chặn ở lớp CSRF, vì vậy không có cơ sở để gọi `RedirectServerAuthenticationFailureHandler` chuyên xử lý authentication failure. Đừng thêm `csrf(csrf -> csrf.disable())` chỉ để test POST trả 302. Trong kiểm thử mock, dùng `mutateWith(csrf())`; trong browser, dùng token mà framework cung cấp.

### 13.2 Access denied không phải login failure

Khi đã authenticated nhưng không có quyền admin, server nên trả 403 (hoặc response tùy access denied handler), không chuyển người dùng về “sai mật khẩu” vì như vậy vừa gây nhầm lẫn vừa khiến điều tra security khó hơn. Tùy biến 403 dùng cấu hình exception handling/access denied riêng, không sửa authenticationFailureHandler.

### 13.3 URL lỗi nên che nguyên nhân nhạy cảm

Đừng đặt `?username=alice&reason=user-not-found`, `?password=...` hay exception message trong `Location`. URL bị lưu trong browser history, proxy logs, referrer, analytics và screenshot. Trang lỗi chỉ nên đưa thông báo chung: “Không thể đăng nhập. Hãy kiểm tra thông tin hoặc thử lại.” Đồng thời ghi log bảo mật có cấu trúc ở backend **không chứa mật khẩu/token**; phân biệt account lock, rate limit và bad credentials theo chính sách.

## 14. Bảo mật redirect và WebSession trong sản phẩm thật

### 14.1 Ngăn open redirect

Một ví dụ **không an toàn**:

```java
String next = exchange.getRequest().getQueryParams().getFirst("next");
return redirects.sendRedirect(exchange, URI.create(next));
```

Đây là **snippet cảnh báo**, không nên đưa vào ứng dụng. Nếu `next` đến từ user, giá trị có thể là `https://attacker.example` hoặc `//attacker.example`. Client vừa đăng nhập có thể bị đưa ra trang giả mạo giống ứng dụng thật. Nếu phải có `returnUrl`, áp dụng một **allowlist có cấu trúc**:

- Chỉ chấp nhận các path nội bộ được phép (ví dụ một set `/app/home`, `/reports`, `/settings`); không chấp nhận URL scheme/host tùy ý.
- Chuẩn hóa path, từ chối backslash/double-slash/control characters và xử lý percent-encoding theo router thực tế.
- Không dùng role/tenant từ query param làm nguồn quyết định quyền.
- Kiểm tra authorization ở **URL đích**, không chỉ khi chọn redirect.
- Xem xét proxy headers đáng tin cậy, HTTPS và host validation.
- Không đưa token/password/PII vào Location URL.

### 14.2 Phân biệt session với request cache

`WebSessionServerSecurityContextRepository` có thể lưu `SecurityContext` sau login để request tiếp theo nhận diện người dùng bằng cookie session. `WebSessionServerRequestCache` là một cơ chế **khác**, dùng lưu URL từng muốn truy cập để redirect sau login. Việc chọn `NoOpServerRequestCache` **không xóa session đăng nhập**.

Nếu tùy chỉnh `.securityContextRepository(...)` của form login, hãy đảm bảo thành phần nạp context ở các request tiếp theo dùng repository tương thích. Thay bằng NoOp repository trong luồng browser session có thể khiến POST login thành công, redirect đúng, nhưng GET trang đích lại bị đẩy về login.

### 14.3 Session fixation, cookie và logout

Ứng dụng production cần kiểm tra cơ chế bảo vệ session fixation, giới hạn thời gian sống, cookie `Secure`/`HttpOnly`/`SameSite`, TLS termination ở reverse proxy và logout. Redirect 302 **không chứng minh** session cookie an toàn hoặc đăng nhập còn hiệu lực sau reload. Test thực qua browser/lưu cookie là phần cần có khi tích hợp với proxy và domain thực.

Nếu dùng OAuth2/OIDC login, success/failure handler cho flow OAuth2 có thể được cấu hình ở `oauth2Login(...)` hoặc lớp tương ứng; sửa `formLogin(...)` **không tự động** đổi callback/redirect OAuth2. Cần phân biệt form username/password với đăng nhập qua Identity Provider bên ngoài.

## 15. Chẩn đoán sự cố thực tế

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Login thành công nhưng redirect về trang cũ thay vì `/app/home` | Saved request được ưu tiên | Kiểm tra `RedirectServerAuthenticationSuccessHandler.setRequestCache` và `http.requestCache(...)` |
| Login thành công nhưng GET `/app/home` lại về `/login` | Session/security context không được lưu hoặc cookie mất | Kiểm tra `ServerSecurityContextRepository`, cookie, session, proxy, nhiều instances |
| Password sai nhưng nhận 403 thay vì redirect `/auth/failed` | Thiếu CSRF token hoặc POST bị chặn trước authentication | Kiểm tra field `_csrf`, cùng session và CSRF config |
| GET `/auth/failed` lại redirect login | Failure route không `permitAll` | Thêm rule public cho failure route và test riêng |
| Có 404 sau 302 tới đích | Target controller/route chưa tồn tại | Tạo `GET` handler đúng URL, kiểm tra mappings |
| Sau khi đổi `loginPage("/sign-in")` form không login được | App chưa render page hoặc form action vẫn `/login` | Kiểm tra GET + POST path, CSRF và form field names |
| Trình duyệt bị redirect loop | `/login` hoặc trang error bị bảo vệ, session lỗi | Kiểm tra authorization rule, session cookie, matcher |
| API JavaScript nhận HTML không mong đợi | Form login redirect phù hợp browser, không phù hợp API | Tách security chain cho API với JSON 401/403 |
| Reader vào admin page được | Rule `anyExchange().authenticated()` che rule admin | Rule admin phải đặt trước matcher rộng |
| Khi login sai lỗi lý do nhạy cảm nằm trong URL | Failure handler tự chèn exception message | Redirect URL cố định, thông báo chung |
| Đăng nhập đúng trong test mock nhưng browser vẫn fail | Mock CSRF/session khác flow HTTP thật | Kiểm tra cookie, HTTPS, reverse proxy, real browser flow |
| Handler redirect không chạy dù POST có password | Form login filter không match path, auth lỗi trước filter | Kiểm tra `requiresAuthenticationMatcher`, form action, CSRF, active security chain |

**Quy trình chẩn đoán gọn:** Xác định request nào tạo 302/403 → xem `Location`/response headers → kiểm tra security matcher đang active → phân biệt entry point, authentication success/failure và access-denied → kiểm tra CSRF/session → mới rà controller. Không bắt đầu bằng sửa bừa các URL và tắt security.

## 16. Bài thực hành mở rộng

### Bài A: Bỏ request cache no-op

Bỏ hai cấu hình `NoOpServerRequestCache` và giữ `new RedirectServerAuthenticationSuccessHandler("/app/home")`. Mở `/admin/home` khi chưa login, sau đó đăng nhập bằng `reader`. Suy nghĩ: nếu saved request quay về `/admin/home`, user sẽ bị **403** vì không có role ADMIN. Đây là kết quả hợp lý: **redirect không cấp quyền**. Sau đó đăng nhập bằng `admin` sẽ được phép vào trang admin.

Khi làm bài này, test mock độc lập không mô phỏng đầy đủ saved request giữa nhiều browser requests. Hãy chạy bằng browser thật hoặc test lưu cookie/session và so sánh hai chính sách.

### Bài B: Thay failure page

Chuyển failure redirect từ `/auth/failed` thành `/login?error`:

```java
new RedirectServerAuthenticationFailureHandler("/login?error");
```

Với trang login mặc định, query `error` thường kích hoạt thông báo thất bại. Đảm bảo failure route vẫn accessible và test lại `Location`. Nếu thay bằng `/sign-in?error`, bạn cần tự render trang login custom như mục 12.

### Bài C: Đích theo role

Thay success handler cố định bằng `successByRole` ở mục 11. Dùng reader và admin đăng nhập riêng, kiểm tra redirect đích tương ứng. Thêm test rằng `GET /admin/home` chỉ trả 200 khi session có `ROLE_ADMIN`; user thiếu quyền phải bị từ chối dù tự nhập URL.

### Bài D: Xử lý app qua reverse proxy

Giả sử ứng dụng ở ngoài tại `https://example.invalid/portal` nhưng server nội bộ hiểu path khác. Kiểm tra context path/base path, forwarded headers tin cậy và cách strategy xử lý redirect relative. Không tự lấy `Host`/`X-Forwarded-Host` từ client chưa qua proxy được tin cậy để tạo absolute redirect. Nếu cần redirect cross-domain để tích hợp SSO, dùng flow OAuth2/OIDC chuẩn và danh sách redirect URI đã đăng ký.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao cấu hình `.formLogin(form -> form.loginPage("/sign-in"))` chưa đủ để đưa user đến dashboard sau khi xác thực thành công?

**Đáp:** `loginPage` xác định trang đăng nhập. Thành công được xử lý bởi `ServerAuthenticationSuccessHandler`, không phải setting login page. Dùng `authenticationSuccessHandler(...)`.

**Câu 2.** Nếu đã tạo `new RedirectServerAuthenticationSuccessHandler("/app/home")`, mọi lần login đều tới `/app/home`?

**Đáp:** Không chắc. Handler có thể ưu tiên URL trong `ServerRequestCache`. Nếu yêu cầu đích cố định, cấu hình cache no-op phù hợp hoặc custom handler bỏ qua saved request.

**Câu 3.** Sai mật khẩu có nhất thiết trả 401 không?

**Đáp:** Không. Với form login kiểu browser, `ServerAuthenticationFailureHandler` thường trả redirect 3xx tới trang lỗi. HTTP Basic/Bearer API có cơ chế challenge/status khác.

**Câu 4.** Gửi POST `/login` đúng password nhưng thiếu `_csrf` và nhận 403. Failure handler có hỏng không?

**Đáp:** Chưa thể kết luận. CSRF filter có thể từ chối trước authentication. Cần cung cấp CSRF token hợp lệ từ cùng session rồi mới test success/failure handler.

**Câu 5.** Vì sao `/auth/failed` nên được `permitAll`?

**Đáp:** Người vừa xác thực thất bại chưa có principal được tin cậy. Nếu URL lỗi yêu cầu login, hệ thống có thể redirect về trang login hoặc tạo vòng lặp.

**Câu 6.** Success handler đưa user tới `/admin/home` có đồng nghĩa user được cấp role ADMIN không?

**Đáp:** Không. Authorization của URL đích quyết định quyền. Handler redirect chỉ tạo response HTTP; nó không thay authorities.

**Câu 7.** `NoOpServerRequestCache` có đồng nghĩa “xóa login session” không?

**Đáp:** Không. Request cache phục vụ URL quay lại; `ServerSecurityContextRepository` phục vụ SecurityContext/session. Đó là hai trách nhiệm khác nhau.

**Câu 8.** Có thể redirect tới `next` lấy từ query parameter bất kỳ không?

**Đáp:** Không an toàn vì có nguy cơ **open redirect**. Chỉ chấp nhận URL/path được server kiểm chứng bằng whitelist, kiểm tra host/path và quyền ở endpoint đích.

**Câu 9.** Nếu test POST success không có CSRF, cách đúng nhất là gì?

**Đáp:** Dùng CSRF token hợp lệ (`mutateWith(csrf())` khi dùng mock WebTestClient có Spring Security test support), không tắt CSRF toàn cục.

**Câu 10.** Làm sao kiểm tra trang đích thực sự hoạt động sau login?

**Đáp:** Ngoài assert POST trả 3xx và Location, cần thực hiện GET tiếp theo với cookie/session được bảo tồn trên browser hoặc live HTTP test, rồi xác nhận 200 và policy quyền tương ứng.

## 18. Checklist đưa vào dự án

- [ ] Server chạy **Spring WebFlux reactive**; dùng `ServerHttpSecurity` và `SecurityWebFilterChain` thay vì Servlet DSL.
- [ ] Đã tách rõ **entry point redirect**, **authentication success redirect**, **authentication failure redirect** và **access denied**.
- [ ] `.formLogin(...)` khai báo đúng `authenticationSuccessHandler` / `authenticationFailureHandler`.
- [ ] Đã quyết định giữ saved request hay cố định dashboard; không vô tình để saved URL ghi đè đích mong muốn.
- [ ] URL login và failure page công khai; các URL thực tế tồn tại và có controller/handler GET phù hợp.
- [ ] User/password được xác thực bằng `ReactiveAuthenticationManager` và encoder hợp lệ; không gắn thủ công authenticated principal từ input client.
- [ ] CSRF được giữ và form POST có CSRF token hợp lệ.
- [ ] URL đích protected vẫn có authorization; không dùng redirect để cấp quyền.
- [ ] Không tạo Location URL tùy ý từ `next`, `returnUrl`, `Host` hoặc claims chưa kiểm chứng.
- [ ] Failure message không làm lộ account existence, password, token hoặc chi tiết exception.
- [ ] Test status 3xx, `Location`, CSRF 403, failure page public và success path.
- [ ] Đã test riêng login session qua browser/cookie, proxy, TLS và logout khi deploy.
- [ ] Nếu có API và browser cùng hệ thống, đã tách rõ cơ chế phản hồi redirect HTML so với JSON 401/403 khi cần.

**Kết luận:** Trong Spring Security WebFlux, thay đổi nơi đi sau form login phải thực hiện ở `ServerAuthenticationSuccessHandler` và `ServerAuthenticationFailureHandler` của `ServerHttpSecurity.formLogin(...)`. `RedirectServerAuthenticationSuccessHandler` có thể ưu tiên **saved request** trước fallback URL; nếu cần đích cố định, hãy xử lý request cache có chủ đích. Đừng vô hiệu CSRF, bỏ session security context hoặc mở redirect ra ngoài chỉ để đạt một kết quả 302. Kiểm tra cả **Location**, **session** và **quyền ở URL đích**.

### Nguồn tham khảo chính thức

- [Spring Security 6.5 — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security 6.5 — RedirectServerAuthenticationSuccessHandler](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — RedirectServerAuthenticationFailureHandler](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html)
- [Spring Security 6.5 — RequestCacheSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.RequestCacheSpec.html)
- [Spring Security 6.5 — NoOpServerRequestCache](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/savedrequest/NoOpServerRequestCache.html)
- [Spring Security 6.5 — CSRF trong WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Thiết lập WebTestClient với Spring Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — Kiểm thử CSRF reactive](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
