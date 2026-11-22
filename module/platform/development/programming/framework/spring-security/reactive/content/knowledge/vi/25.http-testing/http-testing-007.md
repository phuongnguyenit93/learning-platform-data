# Kiểm thử biểu mẫu đăng nhập, cookie phiên và đăng xuất

## 1. Vì sao phải kiểm thử **cả hành trình** login → session → logout?

Một ứng dụng Spring WebFlux sử dụng Spring Security form login có thể vượt qua kiểm thử `@WithMockUser` nhưng vẫn gặp lỗi thật khi chạy trên trình duyệt: form POST thiếu CSRF, response không phát cookie phiên, cookie không quay lại request sau, session không chứa `SecurityContext`, hoặc `POST /logout` chuyển hướng thành công nhưng phiên cũ vẫn truy cập tài nguyên được.

Bài thuộc nhóm **Kiểm thử HTTP** trong module **Spring Security - reactive**. Trọng tâm không chỉ là assert một request đã authenticated, mà là xác minh **chuỗi HTTP requests nối tiếp nhau**:

~~~text
Browser / WebTestClient           Spring WebFlux + Spring Security
          |                                   |
          | GET /login                        |
          |---------------------------------->|
          | 200 HTML login form + CSRF        |
          |<----------------------------------|
          |                                   |
          | POST /login (username,password)   |
          | + SESSION cookie + CSRF token     |
          |---------------------------------->|
          | Password verification, save       |
          | SecurityContext in WebSession     |
          |<----------------------------------|
          | 302 redirect + Set-Cookie SESSION |
          |                                   |
          | GET /me + SESSION                 |
          |---------------------------------->|
          | 200 authenticated principal       |
          |<----------------------------------|
          |                                   |
          | POST /notes + SESSION + CSRF      |
          |---------------------------------->|
          | 200 if authorized                 |
          |<----------------------------------|
          |                                   |
          | POST /logout + SESSION + CSRF     |
          |---------------------------------->|
          | Clear context / invalidate        |
          | WebSession per logout policy      |
          |<----------------------------------|
          | 302 redirect, cookie retired      |
          |                                   |
          | GET /me + OLD SESSION            |
          |---------------------------------->|
          | 302 to /login (no auth)           |
          |<----------------------------------|
~~~

Phải chứng minh ít nhất:
1. Người chưa login không thể truy cập protected route.
2. `GET /login` hiển thị form (trong cấu hình mặc định).
3. `POST /login` thiếu hoặc sai CSRF bị 403.
4. Sai username/password không tạo authenticated session.
5. Đúng credentials + đúng CSRF tạo authentication và phát/duy trì cookie phiên.
6. **Request sau** mang cookie cũ/đã được cập nhật nhận đúng principal.
7. Request không có cookie hoặc cookie giả không mượn được authentication của request trước.
8. User đăng nhập nhưng thiếu role vẫn 403 ở protected admin endpoint.
9. Unsafe request khi đã login vẫn phải có CSRF.
10. `GET /logout` không tự đăng xuất; `POST /logout` thiếu CSRF bị chặn.
11. `POST /logout` hợp lệ hủy/clear state đúng policy.
12. **Ngay cả khi client cố tình gửi lại session ID cũ**, backend không chấp nhận nó như một login đang hoạt động.

**Một test chỉ `mockUser()` rồi GET protected route trả 200 không kiểm được form, cookie, password, session fixation hay logout.** Phải dùng WebTestClient với trình tự cookie/CSRF thật, và phân biệt điều nào đang được giả lập.

## 2. Các thành phần Spring Security Reactive cần hiểu

| Thành phần | Vai trò trong form login/session/logout |
| --- | --- |
| `ServerHttpSecurity` | Reactive Security DSL |
| `SecurityWebFilterChain` | Chuỗi WebFilters cho HTTP requests |
| `AuthenticationWebFilter` | Xử lý authentication request, ví dụ username/password |
| `ReactiveAuthenticationManager` | Kiểm credentials bằng provider phù hợp |
| `ReactiveUserDetailsService` | Tải user và password hash/authorities |
| `PasswordEncoder` | Kiểm mật khẩu an toàn |
| `WebSession` | Phiên WebFlux, có ID và trạng thái server-side |
| `WebSessionServerSecurityContextRepository` | Lưu/đọc `SecurityContext` từ WebSession |
| `ReactorContextWebFilter` | Đọc SecurityContext cho Reactor Context |
| `WebSessionServerCsrfTokenRepository` | Mặc định lưu CSRF token kỳ vọng trong WebSession |
| `XorServerCsrfTokenRequestAttributeHandler` | Mặc định Spring Security 6.x xử lý CSRF token dạng masked, giảm BREACH risk |
| `CsrfWebFilter` | Kiểm CSRF trên unsafe HTTP methods |
| `LogoutWebFilter` | Phát hiện request đăng xuất theo matcher |
| `SecurityContextServerLogoutHandler` | Xóa authentication context đã lưu |
| `WebSessionServerLogoutHandler` | Invalidate WebSession nếu được cấu hình |
| `WebTestClient` | Client test cho Reactive HTTP handlers/filters |
| `SecurityMockServerConfigurers.springSecurity()` | Gắn hỗ trợ Spring Security vào WebTestClient |
| `SecurityMockServerConfigurers.csrf()` | Test mutator cung cấp CSRF token hợp lệ |
| `SecurityMockServerConfigurers.mockUser()` | Test mutator đặt mock principal, bỏ qua login thật |

**Không trộn Servlet và WebFlux.** Trong bài này dùng `WebSession` / cookie `SESSION` thay vì suy luận từ `HttpSession`/`JSESSIONID` của Servlet. Ứng dụng có thể tùy biến cookie name và dùng Spring Session với backend Redis; luôn kiểm tên cookie trong config thực tế.

## 3. Form login: đường đi, phương thức, redirect và password

Cấu hình WebFlux tối thiểu:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Đây là **snippet**, chưa có `ReactiveUserDetailsService` và imports; project độc lập đầy đủ ở phần 9. Khi form login mặc định được bật:
- Chưa authenticated mà GET protected resource → thông thường redirect đến `/login`, **không tự mặc định trả 401 JSON** như API Bearer.
- `GET /login` tạo trang HTML login mặc định (khi không cấu hình custom loginPage).
- `POST /login` gửi `application/x-www-form-urlencoded` với `username` và `password`.
- Trước authentication, `CsrfWebFilter` kiểm token của form POST.
- Credentials đúng → Authentication thành công; security context được lưu vào repository; success handler redirect về URL hợp lý như saved request hoặc default target.
- Credentials sai → redirect tới đường dẫn lỗi, thường `/login?error`, không được lưu authenticated principal.
- `GET /logout` có thể hiển thị trang xác nhận; `POST /logout` thực hiện logout khi CSRF hợp lệ.

### 3.1. Vì sao không assert cứng mọi Location là "/"?

Spring Security có thể lưu requested URL trước khi redirect login. Nếu người dùng truy cập `GET /me` khi chưa đăng nhập, sau khi login thành công họ có thể được đưa về URL trước đó. Nếu không có request cache liên quan, success target có thể là `/`.

**Kiểm thử tốt**: xác nhận response 3xx, không phải redirect error khi credentials đúng, và GET protected route bằng cookie của session trả **principal đúng**. Chỉ assert Location tuyệt đối nếu ứng dụng đã định nghĩa chính xác success handler contract.

### 3.2. 401 và 302 không tương đương

| Request | Kết quả thường gặp | Giải thích |
| --- | --- | --- |
| GET /me khi anonymous, Form Login | 302 tới /login | Chưa authenticated, entry point dạng login |
| GET /login | 200 HTML | Form mặc định hiển thị |
| POST /login sai password nhưng CSRF đúng | 302 tới /login?error | Authentication failure |
| POST /login thiếu CSRF | 403 | CSRF chặn trước xác thực mật khẩu |
| GET /admin với session USER | 403 | Đã authenticated nhưng thiếu ADMIN |
| GET /me sau login và cookie hợp lệ | 200 | SecurityContext được phục hồi |
| POST /logout thiếu CSRF | 403 | Logout không xảy ra |
| POST /logout hợp lệ | Thường 302 về login page | Context/session được cleanup |
| GET /me với old invalidated cookie | 302 tới /login | Không còn authenticated state |

Các mã redirect/status là hành vi **theo cấu hình demo**, không phải một hằng số cho mọi custom success/failure handler hay API trả JSON.

## 4. Cookie phiên: cookie không phải toàn bộ Authentication

Với WebFlux session-based login, trình duyệt thường lưu cookie `SESSION` mang **session ID**. Server dùng ID để tìm `WebSession` và `SecurityContext`.

~~~text
Cookie: SESSION=<opaque-session-id>
              |
              v
WebSessionManager -> session store
              |
              v
WebSessionServerSecurityContextRepository
              |
              v
SecurityContext -> Authentication -> principal/roles
              |
              v
authorizeExchange -> handler
~~~

**Session cookie không phải JWT access token.** Một cookie ID không tự chứa role hoặc mật khẩu (trong mô hình WebSession thông thường); backend quyết định user từ session store. Đừng decode cookie như JWT hoặc tin `Cookie: SESSION=admin` thành role.

### 4.1. Không test mỗi request bằng một WebTestClient hoàn toàn vô trạng thái

`WebTestClient` không mặc nhiên bảo đảm lưu cookie jar qua mọi test/request như browser. Trong các tests dưới đây, chúng ta **chủ động trích `Set-Cookie: SESSION` từ response**, rồi gửi lại `Cookie: SESSION=...` ở request sau. Nếu sau login session ID thay đổi, phải lấy ID **mới nhất**, không cố dùng ID trước login.

Giao thức kiểm thử:
1. GET `/csrf` để lấy CSRF token và khởi tạo WebSession.
2. Lấy `SESSION` response cookie từ GET /csrf.
3. POST `/login` với cùng SESSION + CSRF token + form credentials.
4. Lấy SESSION mới từ response login nếu được phát; nếu không có Set-Cookie mới, giữ ID hiện tại.
5. GET `/me` với SESSION hiện hành.
6. Lấy CSRF token mới trong cùng session sau login trước unsafe request/logout.
7. POST `/logout` với session hiện hành + CSRF token.
8. Dùng **ID trước logout** GET /me để chứng minh server-side invalidation.

### 4.2. Session fixation

`WebSessionServerSecurityContextRepository` mặc định đổi session ID khi lưu SecurityContext sau authentication để giảm nguy cơ session fixation. Tuy nhiên một test không nên cố giữ cookie trước login như session ID vĩnh viễn. **Giữ cookie mới nhất trả về**, rồi test old/new IDs với version cụ thể nếu session fixation rotation là một acceptance criterion.

Không chỉ khẳng định “login trả 200” là session fixation đã an toàn. Kiểm Set-Cookie, WebSession ID rotation, cookie domain/path và behavior ở proxy/sticky sessions/Redis.

### 4.3. Cookie security flags

- **HttpOnly:** JavaScript không thể đọc cookie qua document.cookie, giảm một số rủi ro bị đánh cắp bởi XSS; không tự chống XSS/CSRF.
- **Secure:** browser chỉ gửi cookie qua HTTPS, phải bật ở production; local demo chạy HTTP nên chưa bật.
- **SameSite:** Lax/Strict/None tùy SSO/cross-site flows; **không thay CSRF token** khi có ambient cookies.
- **Path:** chỉ giới hạn nơi browser gửi cookie, không phải quyền ứng dụng.
- **Domain:** tránh đặt quá rộng cho toàn bộ subdomains nếu không cần.
- **Session timeout:** kiểm server-side expiry, không chỉ cookie expiry.
- **Rotation/invalidation:** login và logout phải xử lý session lifecycle chứ không chỉ ẩn UI.

Spring Boot 3.5 có các properties `server.reactive.session.cookie.*` và `server.reactive.session.timeout` cho WebFlux; không dùng nhầm `server.servlet.session.*` trong Reactive stack.

## 5. CSRF với biểu mẫu login và logout

Một browser có thể tự gửi cookie SESSION trong request đến site. Attacker không nhất thiết cần đọc cookie để dụ browser gửi POST cross-site tới ứng dụng. Vì vậy Spring Security WebFlux bật CSRF mặc định; đặc biệt **đăng nhập và đăng xuất đều phải được bảo vệ**.

Với mặc định WebFlux:
- `WebSessionServerCsrfTokenRepository` lưu **expected CSRF token** trong WebSession.
- `CsrfWebFilter` yêu cầu token với unsafe methods như POST.
- Token được expose trong request attribute dạng `Mono<CsrfToken>`.
- `XorServerCsrfTokenRequestAttributeHandler` cung cấp **masked token** cho browser/template ở Spring Security 6.x nhằm hạn chế BREACH.
- Client gửi token ở form parameter `_csrf` hoặc header do `CsrfToken.getHeaderName()` cung cấp, thường là `X-CSRF-TOKEN`.
- Expected token gắn session; nếu SESSION cookie bị thiếu hoặc khác session, CSRF value tương ứng sẽ không hợp lệ.

### 5.1. Form HTML điển hình

~~~html
<form action="/login" method="post">
  <input type="text" name="username" autocomplete="username" />
  <input type="password" name="password" autocomplete="current-password" />
  <input type="hidden" name="_csrf" value="masked-csrf-token-from-server" />
  <button type="submit">Đăng nhập</button>
</form>
~~~

Giá trị masked ở đây là **placeholder giải thích**, không có token thật. Ứng dụng có thể dùng trang đăng nhập mặc định hoặc Thymeleaf (hỗ trợ tự chèn CSRF) thay vì form HTML viết tay.

### 5.2. Vì sao bài demo có GET /csrf?

Để học rõ cookie + CSRF ở tầng HTTP, bài tạo một endpoint **GET /csrf** trả tên header và token hiện hành trong JSON. Việc subscribe `Mono<CsrfToken>` làm token được phát sinh/lưu theo repository, cho phép WebTestClient quan sát SESSION cookie và gửi lại token vào POST.

**Đây là endpoint học tập**, không bắt buộc cho mọi app. Với SSR + Thymeleaf, biểu mẫu có thể tự nhúng token; với SPA cần contract cung cấp token an toàn, hạn chế CORS, không cache response và đánh giá XSS. Đừng expose endpoint này cross-origin tùy ý.

### 5.3. Mã 403 khi thiếu CSRF không chứng minh password sai

Nếu POST `/login` trả 403, điều đầu tiên nên kiểm là session cookie và CSRF token. Một sai mật khẩu **khi CSRF đã hợp lệ** thường đi qua AuthenticationManager rồi redirect trang lỗi.

Tránh “fix” login 403 bằng `csrf(disable)` cho ứng dụng dùng session cookies. CSRF và password verification là hai bước khác nhau, cả hai cần test.

### 5.4. Login thành công có thể làm token CSRF trước đó không còn dùng được

Authentication hoặc logout có thể clear/rotate CSRF token theo cấu hình. Vì vậy test **lấy CSRF token mới sau khi login** trước khi POST `/notes` hoặc `/logout`, thay vì mặc định token từ pre-login luôn còn đúng.

Việc gọi `mutateWith(csrf())` giúp test đơn request, nhưng không kiểm CSRF lifecycle giữa nhiều requests và session cookie thực. Trong bài này, **test chính** dùng token được controller trả về, không giả lập CSRF filter bằng mutator.

## 6. Logout không chỉ là xóa cookie ở client

Theo tài liệu Spring Security Reactive:
- Logout mặc định có `GET /logout` cho confirmation và `POST /logout` để thực hiện hành động.
- Khi POST hợp lệ, logout handlers có thể clear `ServerSecurityContextRepository` và CSRF repository, rồi redirect.
- Nếu cần **invalidate WebSession**, có thể cấu hình `WebSessionServerLogoutHandler` kết hợp `SecurityContextServerLogoutHandler`.

Trong demo, chúng ta chủ động cấu hình:

~~~java
.logout(logout -> logout.logoutHandler(
    new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler()
    )
))
~~~

Đây là snippet; import đầy đủ ở `SecurityConfig.java`.

**Tại sao cần kiểm old cookie?** Một response logout 302 hoặc xóa cookie trên browser chưa đủ để chứng minh server-side session không còn được tin. Test phải cố tình gửi lại **ID cũ** vào protected request; nó phải không còn authenticated.

### 6.1. GET /logout không phải logout action

Một test đúng:
1. Login thành công, lưu SESSION.
2. GET `/logout` (trang xác nhận mặc định).
3. GET `/me` **vẫn** trả 200 cùng session.
4. POST `/logout` + CSRF mới thật sự kết thúc phiên.
5. GET `/me` với old cookie không được 200.

Không đổi logout thành GET chỉ để dễ viết link; GET có thể bị prefetch/crawler và tạo logout CSRF.

### 6.2. Logout không bảo đảm thu hồi mọi token/chỗ đăng nhập

Nếu ứng dụng còn remember-me, JWT Bearer, OAuth2 Login, SSO IdP session, Spring Session Redis hoặc nhiều services, “logout local WebSession” không mặc nhiên revoke access tokens/refresh tokens hoặc đăng xuất toàn hệ thống. Phải có thiết kế riêng: IdP logout, token revocation, client logout, clearing cookies, invalidating distributed sessions theo security contract.

## 7. Ma trận kiểm thử HTTP nên có

| Test case | Method/path | Cookie | CSRF | Credentials/role | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| Public home | GET / | Không | Không | Anonymous | 200 |
| Login page | GET /login | Không | Không | Anonymous | 200 HTML |
| Protected anonymous | GET /me | Không | Không | Anonymous | 302 login |
| Login thiếu CSRF | POST /login | Bất kỳ | Thiếu | Alice đúng | 403 |
| Login sai CSRF | POST /login | SESSION hợp lệ | Sai | Alice đúng | 403 |
| CSRF không có session khớp | POST /login | Thiếu SESSION | CSRF của session khác | Alice đúng | 403 |
| Login sai mật khẩu | POST /login | SESSION + token | Đúng | Alice sai password | 302 error |
| Login user không tồn tại | POST /login | SESSION + token | Đúng | Username lạ | 302 error |
| Login thành công | POST /login | SESSION + token | Đúng | Alice đúng | 302, session được lưu |
| Request kế tiếp | GET /me | SESSION hiện hành | Không cần | Alice | 200, name=alice |
| Không gửi cookie | GET /me | Không | Không cần | Anonymous | 302 login |
| Session cookie giả | GET /me | Unknown | Không cần | Không | 302 login |
| User thiếu quyền admin | GET /admin | Alice SESSION | Không | ROLE_USER | 403 |
| Admin thật | GET /admin | Bob SESSION | Không | ROLE_ADMIN | 200 |
| Unsafe thiếu CSRF | POST /notes | Alice SESSION | Thiếu | ROLE_USER | 403 |
| Unsafe có CSRF | POST /notes | Alice SESSION | Đúng | ROLE_USER | 200 |
| CSRF của session A với session B | POST /notes | Bob SESSION | Token Alice | Bob | 403 |
| GET logout | GET /logout | Alice SESSION | Không | Alice | Không logout |
| POST logout thiếu CSRF | POST /logout | Alice SESSION | Thiếu | Alice | 403, session còn |
| POST logout có CSRF | POST /logout | Alice SESSION | Đúng | Alice | Redirect, session hết |
| Dùng old cookie sau logout | GET /me | OLD SESSION | Không | Chưa authentication | 302 login |

Mục tiêu là kiểm **cả security decisions lẫn state transitions**. Chỉ kiểm status của POST login/logout mà không kiểm request tiếp theo là kiểm thử chưa hoàn chỉnh.

## 8. Project đầy đủ: Java 17 + Spring Boot WebFlux

Dùng Spring Boot 3.5.7 + Java 17 cho ví dụ học tập. Các phiên bản sản phẩm phải được cập nhật security patch trong môi trường triển khai. Có thể dùng Gradle Wrapper của project; ví dụ bên dưới không tạo wrapper binary sẵn.

Cấu trúc:

~~~text
webflux-form-session-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── FormSessionFlowTest.java
        └── SecurityTestHelpersTest.java
~~~

### 8.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-form-session-test'
~~~

### 8.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm `spring-boot-starter-web` vì đó là Servlet MVC stack; bài chỉ dùng Reactive WebFlux. Cũng không cần OAuth2 Resource Server starter: form login ở đây dùng username/password và WebSession.

### 8.3. application.yml

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        same-site: lax
        path: /
        # Để HTTP localhost chạy được, không ép Secure ở demo này.
        # Ở production HTTPS: server.reactive.session.cookie.secure=true

spring:
  application:
    name: webflux-form-session-test
~~~

Bộ cookie này chỉ là cấu hình local; **production bắt buộc HTTPS + Secure**, review Domain/Path/SameSite, proxy TLS termination, HSTS và session store. `SameSite=Lax` giúp giảm một số kịch bản nhưng **không thay CSRF**. `HttpOnly` giảm đọc cookie bằng JavaScript nhưng XSS vẫn có thể gửi requests dưới ngữ cảnh user.

### 8.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

## 9. SecurityConfig.java — form login, CSRF mặc định và session invalidation

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // {bcrypt} encoded password; không lưu raw password thực tế.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER", "ADMIN")
                .build();

        // Chỉ tài khoản DEMO; production dùng user store/IdP an toàn.
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/", "/login", "/logout", "/csrf")
                                .permitAll()
                        .pathMatchers(HttpMethod.POST,
                                "/login", "/logout")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/admin")
                                .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/me")
                                .authenticated()
                        .pathMatchers(HttpMethod.POST, "/notes")
                                .authenticated()
                        .anyExchange().denyAll())
                // Bật form login. Trang login mặc định tại /login.
                .formLogin(Customizer.withDefaults())
                // Không cần HTTP Basic trong bài kiểm thử form.
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                // CSRF mặc định ENABLED; không gọi .csrf(disable).
                .logout(logout -> logout.logoutHandler(
                        new DelegatingServerLogoutHandler(
                                new SecurityContextServerLogoutHandler(),
                                new WebSessionServerLogoutHandler())))
                .build();
    }
}
~~~

### 9.1. Vai trò của các lựa chọn

- `formLogin` bật form POST username/password; Spring Security cấu hình login page/entry point mặc định khi không custom page.
- `ReactiveUserDetailsService` tải user; `PasswordEncoder` xác minh password hash theo thuật toán được cấu hình.
- `permitAll` cho `POST /login` **không bỏ CSRF**: CsrfWebFilter vẫn áp dụng.
- `GET /admin` đòi ROLE_ADMIN, Alice chỉ USER phải bị 403.
- `POST /notes` được bảo vệ cả authentication và CSRF.
- `anyExchange().denyAll()` ngăn các URL/method không được review.
- `SecurityContext` được lưu/khôi phục bằng WebSession repository mặc định trong form login path; **không** cấu hình `NoOpServerSecurityContextRepository` như Bearer-only API.
- `SecurityContextServerLogoutHandler` clear stored authentication; `WebSessionServerLogoutHandler` làm phiên không còn sử dụng được sau logout.
- **Không sử dụng** `.csrf(ServerHttpSecurity.CsrfSpec::disable)` vì đây là app dùng session cookie.

### 9.2. Đăng nhập thành công không cần tự viết controller POST /login

Spring Security xử lý `POST /login` qua filters. Controller chỉ khai báo protected routes và endpoint trả CSRF token phục vụ bài kiểm thử. Tự viết `@PostMapping("/login")` rồi gọi `ReactiveUserDetailsService.findByUsername` và tự gán session context dễ làm hỏng session fixation, exception/failure handlers và CSRF.

### 9.3. Sai lầm với User.withDefaultPasswordEncoder hoặc {noop}

Bài dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()` và password được encode (thường dạng `{bcrypt}...`). Tài khoản/password là **dữ liệu demo trong mã học tập**; không được dùng credential này ở production.

Tránh `{noop}productionPassword` hoặc lưu raw password trong config. Với production, dùng bcrypt/argon2/pbkdf2 theo chính sách, salt/rehash và secure user store/IdP, không phụ thuộc MapReactiveUserDetailsService tĩnh.

## 10. DemoController.java — CSRF endpoint và các protected routes

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record CsrfView(
            String headerName,
            String parameterName,
            String token) {
    }

    public record NoteRequest(String text) {
    }

    public record NoteResult(String owner, String text) {
    }

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping(path = "/csrf",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        // CsrfWebFilter exposes Mono<CsrfToken> as exchange attribute.
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        // Subscribing triggers lazy token generation/saving in WebSession.
        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF filter/token attribute is missing"));
        }

        return token.map(value -> new CsrfView(
                value.getHeaderName(),
                value.getParameterName(),
                value.getToken()));
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> currentUser(Principal principal) {
        return Mono.just(Map.of("username", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<String> admin(Principal principal) {
        return Mono.just("admin:" + principal.getName());
    }

    @PostMapping(path = "/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<NoteResult> note(
            Principal principal,
            @RequestBody Mono<NoteRequest> body) {
        return body.map(value ->
                new NoteResult(principal.getName(), value.text()));
    }
}
~~~

**Lưu ý về phản hồi:** endpoint `/notes` chỉ echo dữ liệu kiểm thử, không lưu database. Trong sản phẩm thật, cần validation, quota, ownership checks và audit; không đưa thông tin nhạy cảm vào response.

### 10.1. CSRF token ở đây là masked token

Trong cấu hình mặc định Spring Security Reactive 6.x, `CsrfToken.getToken()` được expose dưới cơ chế XOR/masking. Client gửi **đúng token được nhận từ `/csrf`** trong header `CsrfView.headerName` (thường `X-CSRF-TOKEN`). Không tự decode, bỏ masking hay so giá trị token từ nhiều GET một cách ngây thơ.

Với server-side Thymeleaf login form, template engine có integration cho CSRF; API JSON `/csrf` không phải bắt buộc cho toàn bộ ứng dụng WebFlux.

### 10.2. Có nên để /csrf public?

Nếu một frontend cần lấy token trước login, endpoint có thể permitAll như ví dụ, nhưng phải:
- Giữ **same-origin policy** và CORS allowlist chặt.
- Bảo đảm response không bị shared CDN caching; có thể thêm `Cache-Control: no-store`.
- Không phản chiếu token vào logs, tracing hoặc analytics.
- Không cho trang của attacker tùy ý đọc token qua permissive CORS.
- Bảo vệ XSS, vì script chạy trong chính origin có thể dùng token để gửi request.
- Thay đổi token/session lifecycle theo contract khi authentication/logout.

## 11. FormSessionFlowTest.java — kiểm thử cookie và CSRF THẬT qua nhiều HTTP requests

Phần này dùng:
- `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`.
- **Không** `@WithMockUser`, **không** `mockUser()`, **không** `mutateWith(csrf())` trong test chính.
- CSRF token được đọc từ controller `GET /csrf` trong server pipeline thật.
- Cookie `SESSION` được trích từ `Set-Cookie` trong test response, gửi lại ở request khác.
- Username/password đi qua form authentication filter và `PasswordEncoder` thật.

Đó là khác biệt giữa **session-flow integration test** và **mock authorization-only test**.

### 11.1. Đoạn mã đầy đủ

`src/test/java/demo/FormSessionFlowTest.java`:

~~~java
package demo;

import java.util.Objects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormSessionFlowTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    private record CsrfTicket(
            String sessionId, String headerName, String token) {
    }

    private record LoginResult(
            String sessionId, String redirect) {
    }

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    // Cookie SESSION có thể được thay/rotate trên mỗi transition.
    private static String latestSession(
            MultiValueMap<String, ResponseCookie> responseCookies,
            String previous) {
        ResponseCookie cookie = responseCookies.getFirst("SESSION");
        if (cookie != null && !cookie.getValue().isEmpty()) {
            return cookie.getValue();
        }
        return previous;
    }

    // Lấy CSRF token thực từ server và giữ session cookie.
    private CsrfTicket csrf(String existingSessionId) {
        var request = client.get().uri("/csrf");
        if (existingSessionId != null) {
            request.cookie("SESSION", existingSessionId);
        }

        var response = request.exchange()
                .expectStatus().isOk()
                .expectBody(DemoController.CsrfView.class)
                .returnResult();

        DemoController.CsrfView body =
                Objects.requireNonNull(response.getResponseBody());
        String sessionId = latestSession(
                response.getResponseCookies(), existingSessionId);

        assertNotNull(sessionId,
                "Expected SESSION cookie for WebSession CSRF token");
        assertNotNull(body.token());
        return new CsrfTicket(
                sessionId, body.headerName(), body.token());
    }

    // Đăng nhập bằng form + CSRF + SESSION thực; không mockUser().
    private LoginResult login(String username, String password) {
        CsrfTicket preLogin = csrf(null);

        var response = client.post().uri("/login")
                .cookie("SESSION", preLogin.sessionId())
                .header(preLogin.headerName(), preLogin.token())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", username)
                        .with("password", password))
                .exchange()
                .expectStatus().is3xxRedirection()
                .returnResult(Void.class);

        String activeSession = latestSession(
                response.getResponseCookies(),
                preLogin.sessionId());
        assertNotNull(activeSession);

        return new LoginResult(
                activeSession,
                String.valueOf(response.getResponseHeaders()
                        .getLocation()));
    }

    @Test
    void homeIsPublic() {
        client.get().uri("/")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("home");
    }

    @Test
    void loginPageCanBeLoaded() {
        client.get().uri("/login")
                .exchange().expectStatus().isOk();
    }

    @Test
    void anonymousProtectedRequestRedirectsToLogin() {
        client.get().uri("/me")
                .exchange().expectStatus().is3xxRedirection()
                .expectHeader().valueMatches(
                        "Location", ".*\\/login.*");
    }

    @Test
    void loginWithoutCsrfIs403() {
        client.post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "alice-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void loginWithBadCsrfIs403() {
        CsrfTicket ticket = csrf(null);

        client.post().uri("/login")
                .cookie("SESSION", ticket.sessionId())
                .header(ticket.headerName(), "incorrect-csrf")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "alice-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void csrfTokenWithoutItsSessionIs403() {
        CsrfTicket ticket = csrf(null);

        client.post().uri("/login")
                // Không gửi session cookie của CSRF token.
                .header(ticket.headerName(), ticket.token())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "alice-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void badPasswordRedirectsToErrorAndDoesNotAuthenticate() {
        LoginResult result = login("alice", "wrong-password");
        assertTrue(result.redirect().contains("error"));

        client.get().uri("/me")
                .cookie("SESSION", result.sessionId())
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void unknownUsernameDoesNotCreateAuthentication() {
        LoginResult result = login("nonexistent", "whatever");
        assertTrue(result.redirect().contains("error"));

        client.get().uri("/me")
                .cookie("SESSION", result.sessionId())
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void correctFormLoginCreatesAuthenticatedSession() {
        LoginResult result = login("alice", "alice-pass");
        assertTrue(!result.redirect().contains("error"));

        client.get().uri("/me")
                .cookie("SESSION", result.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void sameSessionCookieRestoresPrincipalOnNextRequest() {
        LoginResult login = login("alice", "alice-pass");

        for (int i = 0; i < 2; i++) {
            client.get().uri("/me")
                    .cookie("SESSION", login.sessionId())
                    .exchange().expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.username").isEqualTo("alice");
        }
    }

    @Test
    void withoutSessionCookiePreviousLoginDoesNotCarryOver() {
        LoginResult loggedIn = login("alice", "alice-pass");
        assertNotNull(loggedIn.sessionId());

        client.get().uri("/me")
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void fabricatedSessionCookieCannotImpersonateUser() {
        client.get().uri("/me")
                .cookie("SESSION", "not-a-session-created-by-server")
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void userRoleCannotReadAdminPage() {
        LoginResult login = login("alice", "alice-pass");
        client.get().uri("/admin")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanReadAdminPage() {
        LoginResult login = login("bob", "bob-pass");
        client.get().uri("/admin")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:bob");
    }

    @Test
    void authenticatedPostWithoutCsrfStillGets403() {
        LoginResult login = login("alice", "alice-pass");

        client.post().uri("/notes")
                .cookie("SESSION", login.sessionId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("hello"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void authenticatedPostWithFreshSessionCsrfSucceeds() {
        LoginResult login = login("alice", "alice-pass");
        CsrfTicket ticket = csrf(login.sessionId());

        client.post().uri("/notes")
                .cookie("SESSION", ticket.sessionId())
                .header(ticket.headerName(), ticket.token())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("hello"))
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice")
                .jsonPath("$.text").isEqualTo("hello");
    }

    @Test
    void csrfFromOneSessionCannotAuthorizeAnotherSessionPost() {
        LoginResult alice = login("alice", "alice-pass");
        LoginResult bob = login("bob", "bob-pass");
        CsrfTicket aliceTicket = csrf(alice.sessionId());
        CsrfTicket bobTicket = csrf(bob.sessionId());

        client.post().uri("/notes")
                .cookie("SESSION", bobTicket.sessionId())
                .header(aliceTicket.headerName(), aliceTicket.token())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("cross-session"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void getLogoutDoesNotActuallyEndSession() {
        LoginResult login = login("alice", "alice-pass");
        client.get().uri("/logout")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk();

        client.get().uri("/me")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void postLogoutWithoutCsrfDoesNotEndSession() {
        LoginResult login = login("alice", "alice-pass");

        client.post().uri("/logout")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isForbidden();

        client.get().uri("/me")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void validPostLogoutInvalidatesOldSession() {
        LoginResult login = login("alice", "alice-pass");
        CsrfTicket ticket = csrf(login.sessionId());

        client.post().uri("/logout")
                .cookie("SESSION", ticket.sessionId())
                .header(ticket.headerName(), ticket.token())
                .exchange().expectStatus().is3xxRedirection();

        // Dù cố tình dùng lại ID cũ, server không coi là logged-in.
        client.get().uri("/me")
                .cookie("SESSION", ticket.sessionId())
                .exchange().expectStatus().is3xxRedirection()
                .expectHeader().valueMatches(
                        "Location", ".*\\/login.*");
    }
}
~~~

### 11.2. Giải thích chi tiết các hàm trợ giúp

`csrf(existingSessionId)`:
- GET `/csrf`, có hoặc không gửi session cũ.
- Đọc `CsrfView` từ JSON response.
- Đọc `SESSION` từ `response.getResponseCookies()`.
- Trả token + headerName + sessionId **cùng một đối tượng**, tránh trộn token của phiên A với cookie phiên B.
- Nếu không có SESSION cookie khi khởi tạo CSRF token, test fail với thông báo có nghĩa; không giả định session tự được lưu bởi client.

`login(username, password)`:
- Lấy CSRF token trước login.
- Gửi **form URL encoded** như browser, không gửi JSON tới POST /login mặc định.
- Gửi cùng `SESSION` cookie và CSRF token.
- Kiểm redirect response.
- Nếu login phản hồi Set-Cookie SESSION mới, lấy ID mới; nếu không, giữ ID hiện tại.
- Trả session ID và Location để assertions kiểm sau login hoặc failure redirect.

**Lưu ý:** helper `login()` dùng chung cho cả thành công và thất bại vì cả hai có thể trả 3xx. Test quyết định bằng redirect target và GET /me ở request sau, không chỉ vì POST trả 3xx.

### 11.3. Vì sao cần assert user sau khi GET /me?

Nếu test chỉ check POST /login trả redirect, một server bị lỗi vẫn có thể redirect nhưng không lưu `SecurityContext`. `GET /me` với cookie mới là bằng chứng framework đã load lại authentication từ session store ở **request khác**.

### 11.4. Vì sao logout phải test cả hai chiều?

- **Thiếu CSRF**: POST logout bị 403, **session vẫn truy cập /me thành công**.
- **Có CSRF**: POST logout redirect, **old cookie bị từ chối** ở request sau.

Như vậy test chứng minh **không bị logout CSRF** và **không còn session authenticated sau logout**, thay vì chỉ check một 302.

## 12. SecurityTestHelpersTest.java — phân biệt mockUser() và csrf() với login thật

Spring Security Test có những mutators rất tiện để kiểm policy của controller mà không cần đi qua form login/password:
- `mockUser()` cung cấp authentication giả lập trong WebTestClient request.
- `csrf()` cung cấp valid CSRF trong test request.
- `@WithMockUser` tương đương về mục đích authorization test ở trường hợp phù hợp.

**Điều không được phép suy ra:** vì `mockUser("alice")` GET /me trả 200 thì form POST/PasswordEncoder/WebSession cookie đã chạy đúng. Và vì `mutateWith(csrf())` POST thành công thì CSRF token thực có cùng session ID hoặc rotate đúng sau login.

`src/test/java/demo/SecurityTestHelpersTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SecurityTestHelpersTest {

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
    void mockUserCanTestAuthorizationWithoutFormLogin() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/me")
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void mockUserWithoutCsrfCannotPost() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .post().uri("/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("note"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void mockUserAndCsrfCanTestPostAuthorization() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("note"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.owner")
                .isEqualTo("alice");
    }

    @Test
    void mockAdminRoleCanAccessAdminEndpoint() {
        client.mutateWith(mockUser("bob").roles("ADMIN"))
                .get().uri("/admin")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:bob");
    }
}
~~~

Các tests này hữu ích để cô lập **authorization policy** và CSRF request validation. Chúng **không tạo login session thật**, không chứng minh cookie `SESSION`/logout invalidation, và không xác minh BCrypt password. Hai lớp test bổ sung cho nhau, không thay thế nhau.

## 13. Chạy Gradle và kết quả mong đợi

Từ project root:

~~~bash
gradle test
~~~

Nếu đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Trong dự án mẫu:
- `FormSessionFlowTest` có **20 phương thức @Test** đi qua login/logout/cookie/CSRF HTTP thật trong WebTestClient application context.
- `SecurityTestHelpersTest` có **4 phương thức @Test** dùng mockUser()/csrf().
- Tổng là **24 test methods** theo source.

**Đây là số lượng/mục tiêu được thiết kế trong mã**, không phải kết quả test thực thi trên môi trường soạn bài. Để tuyên bố BUILD SUCCESSFUL phải thực sự chạy Gradle bằng Java 17, dependencies đã tải về, và xác nhận kết quả trong project.

### 13.1. Test nào chứng minh được điều gì?

| Tầng | Test | Kiểm chứng | Không chứng minh |
| --- | --- | --- | --- |
| Form/CSRF | POST /login thiếu token | CsrfWebFilter chặn | Password encoder hoặc cookie sống |
| Credentials | Login sai mật khẩu nhưng CSRF đúng | Authentication failure | Logout |
| Session flow | POST /login + GET /me cùng cookie | Credentials, SecurityContext persistence | Reverse proxy TLS hoặc distributed session |
| Session isolation | Bỏ cookie/fake cookie/cross-session CSRF | Không tái sử dụng auth ngoài phiên | Session fixation attack chuyên biệt mọi case |
| Authorization | Alice USER vs Bob ADMIN | Route authority | Ownership dữ liệu thật |
| Logout | POST /logout và old-cookie GET /me | Server-side session invalidation theo config | Global IdP logout/revoke token |
| mockUser | mutateWith(mockUser()) | Controller/authority logic | Form login/password/cookie |
| csrf mutator | mutateWith(csrf()) | CSRF chấp nhận một test request | Session CSRF lifecycle thật |

### 13.2. Khi nào test actual HTTP server thay vì bindToApplicationContext?

`bindToApplicationContext` tạo mock server pipeline trong process; rất hữu ích cho WebFilters, cookies và sessions. Nhưng nó **không thể** thay các integration tests mạng thật cho:
- HTTPS và TLS termination tại Gateway.
- `Set-Cookie` Secure/Domain/Path qua reverse proxy.
- Browser SameSite/third-party cookie policies.
- Redis/Spring Session across pods và failover.
- Load balancer sticky sessions.
- Host/forwarded headers, CORS origins và session fixation qua ingress.
- Browser navigation, HTML login form rendering, redirects và history.
- Proxy cookie rewriting, SameSite=None;Secure, HSTS.

Để kiểm đầy đủ, bổ sung `@SpringBootTest(webEnvironment = RANDOM_PORT)` với WebTestClient kết nối real port và E2E browser tests hoặc staging Gateway tests.

## 14. Kiểm thử bằng curl với cookie jar

Khởi chạy:

~~~bash
gradle bootRun
~~~

GET public:

~~~bash
curl -i http://localhost:8080/
~~~

Kỳ vọng 200 với body `home`.

### 14.1. Lấy session cookie và CSRF token

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
~~~

Response JSON mẫu:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "masked-csrf-value-from-server"
}
~~~

Đây là **chuỗi minh họa**, không phải token thật. Lưu trữ token nhận được trong biến của shell hoặc copy thủ công vào lệnh sau. `cookies.txt` là dữ liệu phiên nhạy cảm, không commit/log/chia sẻ.

### 14.2. Form POST /login

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-CSRF-TOKEN: <token-from-get-csrf>' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'password=alice-pass' \
  http://localhost:8080/login
~~~

Kỳ vọng redirect. `-c` phải được dùng để lưu Set-Cookie SESSION có thể thay đổi khi login. Không chỉ dùng `-b` và bỏ Set-Cookie mới.

### 14.3. GET protected với session đã đăng nhập

~~~bash
curl -i -b cookies.txt \
  http://localhost:8080/me
~~~

Kỳ vọng 200 JSON:

~~~json
{"username":"alice"}
~~~

Nếu bỏ `-b cookies.txt`, request không có session, thường redirect `/login`.

### 14.4. POST logout với CSRF mới

Sau login, lấy CSRF token lại:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
~~~

Dùng token mới vừa nhận:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  -H 'X-CSRF-TOKEN: <new-token-from-get-csrf>' \
  http://localhost:8080/logout
~~~

Kỳ vọng redirect về login page. Request kế tiếp với cookie jar phải không còn authenticated. Để test cứng server-side invalidation, lưu bản **session ID cũ** trước logout và thử lại GET `/me` sau đó; nó phải không còn cho 200. Cẩn trọng không lưu session ID thật trong CI logs.

### 14.5. Không thể dùng csrf() mutator trong curl

`mutateWith(csrf())` thuộc Spring Security Test, không phải HTTP endpoint/cookie hay một lệnh curl. Browser/curl thật phải lấy token từ server và gửi cùng session tương ứng.

## 15. Các phản ví dụ thường làm test “xanh giả”

### 15.1. Chỉ @WithMockUser mà không POST form login

~~~java
// Chỉ test authorization, KHÔNG chứng minh đăng nhập.
@Test
@WithMockUser(username = "alice", roles = "USER")
void wrongConclusion() {
    client.get().uri("/me")
            .exchange().expectStatus().isOk();
}
~~~

Nếu client chưa tích hợp hỗ trợ mock authentication đúng thì snippet còn có thể cần cấu hình; điểm chính là **mock principal bỏ qua password**. Để test form thật, gửi POST /login với URL-encoded credentials + CSRF, rồi GET /me bằng SESSION cookie.

### 15.2. Disable CSRF để login test pass

~~~java
// SAI cho ứng dụng dùng cookie form login:
http.csrf(ServerHttpSecurity.CsrfSpec::disable);
~~~

Nếu form POST /login trước đó trả 403, cần xác nhận CSRF token và session cookie của request, không tắt security control cho cả app.

### 15.3. Test “logout thành công” chỉ vì 302

~~~java
// TEST THIẾU: chưa chứng minh session thực sự hết.
client.post().uri("/logout")
        .exchange().expectStatus().is3xxRedirection();
~~~

Với CSRF enabled, lệnh trên có thể còn trả 403; kể cả đã thêm CSRF, một 302 cũng chưa chứng minh old session không còn được tin. Thêm GET /me với **old SESSION** sau logout.

### 15.4. Nhầm JSESSIONID với SESSION

Spring WebFlux mặc định thường dùng cookie `SESSION` của `CookieWebSessionIdResolver`. Servlet containers thường dùng `JSESSIONID`. Nhưng project có thể tùy biến tên cookie qua `server.reactive.session.cookie.name` hoặc Spring Session WebSessionIdResolver. Test nên đọc response cookies thực và dùng tên đã được cấu hình, không hardcode tên Servlet khi dùng Reactive.

### 15.5. Cookie tồn tại không chứng minh đã authenticated

Một anonymous session có thể được tạo chỉ để lưu CSRF token, **trước login**. Test “response có SESSION cookie” chỉ chứng minh có WebSession, **không** chứng minh SecurityContext chứa authenticated principal. Phải GET /me trong request mới và assert principal.

### 15.6. Login redirect đúng không chứng minh role đúng

User có thể authenticated nhưng thiếu ROLE_ADMIN. Test phải kiểm access control trên /admin: Alice 403, Bob 200. Domain permissions còn cần data ownership tests.

### 15.7. Logout frontend-only

Chỉ xóa cookie phía browser hoặc xóa state trong SPA không đảm bảo session cũ trên server invalidated. Một attacker giữ ID cũ có thể dùng lại nó nếu session store còn hợp lệ. Test old-cookie request để bảo đảm invalidation.

## 16. Session fixation, timeout và nhiều instance

### 16.1. Session fixation khi login

Kịch bản: attacker khiến browser dùng một session ID đã biết trước đăng nhập, rồi đợi nạn nhân login. Nếu ứng dụng giữ nguyên session ID, attacker có thể tận dụng. Với WebFlux, `WebSessionServerSecurityContextRepository` thay session ID khi lưu SecurityContext, giảm nguy cơ.

Test tăng cường:
1. GET /csrf để tạo pre-login SESSION.
2. POST /login đúng credentials với cookie cũ.
3. Quan sát Set-Cookie SESSION sau login.
4. Xác nhận response/login ID transition như policy/version.
5. Dùng **ID cũ** GET /me: nếu implementation bảo đảm rotation/invalidity, không được nhận user mới.
6. Dùng ID mới GET /me: 200.

**Không viết một test cố định về giá trị cụ thể hoặc hình thức UUID của session ID.** Session ID phải opaque; định dạng có thể đổi theo WebSessionManager/Spring Session.

### 16.2. Timeout không thể test bằng Thread.sleep dài trong CI

`server.reactive.session.timeout` điều khiển WebSession timeout. Một test integration thật có thể dùng session store/clock phù hợp hoặc cấu hình test timeout ngắn, nhưng cần:
- Kiểm không sử dụng phiên sau expiration.
- Kiểm cleanup session và CSRF token.
- Kiểm login lại tạo session mới.
- Không làm test suite ngủ hàng chục phút.
- Không suy luận từ cookie max-age: server-side expiry là tầng riêng.

### 16.3. Multi-instance và Spring Session

Spring WebFlux mặc định có thể dùng in-memory session store của một instance; khi scale:
- Pod A xử lý login, pod B xử lý GET /me.
- Nếu session không được share, B có thể không tìm thấy session ID -> redirect login.
- Sticky sessions là một chiến lược vận hành nhưng có điểm yếu failover.
- Spring Session hỗ trợ WebSession với `ReactiveSessionRepository` và Redis để chia sẻ state theo chính sách.
- Test phải đi qua Gateway/LB qua nhiều pods và mô phỏng failover.
- Redis TTL, serialization, cleanup, security, network ACL, namespace isolation quan trọng.

**Cookie SESSION là địa chỉ tra cứu phiên**, không phải bản sao toàn bộ Authentication có thể tự xác minh offline.

## 17. Browser, SameSite, Secure, CORS và reverse proxy

### 17.1. Secure cookie ở production

Local project chạy `http://localhost:8080` nên không ép Secure cookie. Production phải phục vụ HTTPS, đặt:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Kiểm Set-Cookie qua public HTTPS hostname. Sau TLS termination ở proxy, proxy forwarding/Spring Boot configuration có thể ảnh hưởng nhận biết scheme; test thực tế thay vì mặc định mọi proxy tự sửa cookie an toàn.

### 17.2. SameSite không thay CSRF

`SameSite=Lax` có thể giảm nhiều cross-site cookie sends nhưng không chặn mọi kịch bản CSRF (same-site subdomain, state-changing GET bug, browser behavior và cross-site flows). Các form POST /login, /logout và domain-changing actions cần token theo threat model.

Nếu SSO hoặc embedded app yêu cầu `SameSite=None`, thường phải có `Secure` và policy third-party cookies; không được tắt CSRF vì cookie cần cross-site.

### 17.3. CORS không phải authentication

CORS áp vào browser cross-origin reads/requests, không ngăn curl hoặc server-to-server. Với WebFlux form login:
- Avoid wildcard CORS có credentials.
- Xác định allowed origins rõ.
- Cho phép credentials chỉ đối với trusted origins.
- Kiểm preflight/actual request với SESSION và CSRF.
- Không expose `GET /csrf` qua CORS rộng.
- Kiểm Origin/Referer theo chính sách bổ sung khi phù hợp.

### 17.4. Logout từ browser có thể cần chăm sóc front-end state

Sau logout, redirect về login page không tự xóa mọi cache UI/service worker/local storage. Nên dùng Cache-Control phù hợp cho sensitive content, tránh lưu sensitive API response ở shared caches; cân nhắc Clear-Site-Data trong những kịch bản phù hợp nhưng không xem nó thay server session invalidation.

## 18. Troubleshooting theo HTTP response

### GET /me luôn redirect dù POST /login báo success

Kiểm:
1. Request POST /login thực sự có CSRF hợp lệ không?
2. Login response có Set-Cookie SESSION mới không?
3. Client có dùng **cookie ID mới nhất** ở GET /me không?
4. Cookie Path/Domain/SameSite/Secure có khiến browser không gửi lại?
5. Proxy có strip Set-Cookie hoặc Cookie?
6. App có `NoOpServerSecurityContextRepository` thay session repo không?
7. Login authentication manager có lưu SecurityContext thành công?
8. Session store có bị reset, TTL hết hoặc chia pods không share?
9. Login success handler có redirect về URL lạ khiến client bỏ cookie?
10. GET /me có vào đúng SecurityWebFilterChain và scope/role rule?

Không khẳng định lỗi credentials chỉ vì redirect sau login.

### POST /login trả 403

Kiểm SESSION cookie, token `_csrf` hoặc `X-CSRF-TOKEN`, form Content-Type, token đã refresh sau login/logout, Session ID có rotate, CSP/browser caching có cản hidden input hay không. 403 trước password verification khác failure redirect do sai mật khẩu.

### POST /logout trả 403

Kiểm đã lấy CSRF token mới gắn WebSession hiện hành và gửi đúng header/parameter chưa. Với CSRF mặc định, POST /logout thiếu token **phải bị chặn**. Không bật GET logout chỉ để test dễ hơn.

### POST /logout redirect nhưng GET /me bằng old cookie vẫn 200

Đây là lỗi nghiêm trọng của logout contract:
- Logout handler có thật invalidate WebSession không?
- `SecurityContextServerLogoutHandler` dùng đúng repository không?
- Session store có shared cache/replica với consistency issue?
- Request GET sau logout có mang cookie khác không?
- Proxy có session affinity/client cache sai?
- Có remember-me, bearer auth, Basic, gateway auth riêng vô tình đăng nhập lại?
- Test đã dùng **old SESSION** thật, không dùng `mockUser` xen vào?
- Client có giữ Authorization header khác ngoài SESSION không?

Không đánh dấu logout PASS cho đến khi old-session check đúng.

### WebTestClient test PASS nhưng browser không login được

Mock server có thể chưa mô phỏng TLS, cookie Secure/Domain/SameSite, reverse proxy, browser CSRF form generation hoặc cross-origin restrictions. Chạy E2E trên environment giống production, quan sát Set-Cookie/Cookie qua developer tools và gateway headers **mà không log token raw**.

## 19. Checklist bảo mật và coverage

### Form login và credentials
- [ ] Protected anonymous request đi đến login entry point, không thành 200.
- [ ] GET /login có form và CSRF hidden input trong UI thật.
- [ ] POST /login thiếu/sai CSRF bị từ chối.
- [ ] POST /login dùng application/x-www-form-urlencoded, không gửi JSON tùy ý nếu chưa custom filter.
- [ ] PasswordEncoder không noop cho production credentials.
- [ ] Login sai username/password không tạo authenticated session.
- [ ] Login success được xác thực bằng GET protected ở request **khác**.
- [ ] Role khác nhau dẫn đến 403/200 đúng policy.
- [ ] Không log password, CSRF tokens, session IDs trong CI logs.

### Session và cookie
- [ ] Test Set-Cookie SESSION từ response thật.
- [ ] Test cookie được gửi lại trong HTTP request sau.
- [ ] Test không cookie và cookie giả không được authenticated.
- [ ] Session ID rotation/fixation behavior được kiểm theo repository/version.
- [ ] Session TTL/idle timeout và expiry được test không flaky.
- [ ] HttpOnly, Secure, SameSite, Domain, Path, HSTS được kiểm qua HTTPS.
- [ ] Session store không mất state giữa pods hoặc sau failover nếu contract yêu cầu.
- [ ] Cookie SESSION không được nhầm với JWT/role.
- [ ] Không tin giá trị SESSION do client tự đặt nếu không tìm thấy trong server store.

### CSRF
- [ ] GET /csrf/token bootstrap được cùng-origin và không cache.
- [ ] Masked CSRF token của Spring 6.x được gửi nguyên vẹn qua header/form.
- [ ] Token gắn với SESSION tương ứng, không dùng token từ session khác.
- [ ] POST /notes, /login, /logout cần CSRF token.
- [ ] Không tắt CSRF toàn app dùng session cookie.
- [ ] Test `mockUser() + csrf()` chỉ được phân loại là policy test, không thay session flow.

### Logout
- [ ] GET /logout không thực hiện logout.
- [ ] POST /logout thiếu CSRF bị 403, session vẫn sống.
- [ ] POST /logout hợp lệ dùng ServerLogoutHandler đúng repository.
- [ ] Invalidate WebSession theo contract nếu yêu cầu logout hủy toàn phiên.
- [ ] GET protected bằng **old session ID** sau logout không còn authenticated.
- [ ] Global SSO/remember-me/refresh-token logout có kế hoạch riêng.
- [ ] Logout idempotency/replay/race conditions được xét trong thực tế.

### Gateway và vận hành
- [ ] HTTPS; proxy không strip Cookie/Set-Cookie.
- [ ] CORS with credentials chỉ cho trusted origins.
- [ ] WebFlux Reactive config, không copy Servlet HttpSession APIs.
- [ ] Spring Session/Redis TTL, encryption and access policy nếu scale ngang.
- [ ] Có monitoring login failures, logout results, CSRF 403 tổng hợp, không log secrets.
- [ ] E2E browser/Gateway test cho cookie flags, session fixation, logout persistence.
- [ ] Có test cho session timeout và multi-pod read-after-login.

## 20. Câu hỏi ôn tập

**1. @WithMockUser có kiểm được POST /login bằng mật khẩu thật không?**

> Không. Nó tạo mock Authentication để test authorization, không chạy form/password/session-flow thực.

**2. Vì sao anonymous GET /me có thể trả 302 chứ không phải 401?**

> Form login sử dụng redirect-to-login entry point cho browser, không phải Bearer API entry point.

**3. Cookie SESSION có chứa username và roles ở dạng JWT không?**

> Không trong WebSession mặc định. Cookie mang opaque session ID; server dùng nó để load SecurityContext.

**4. Lấy session cookie lúc nào?**

> Từ Set-Cookie của response và cập nhật khi login/session ID có thể rotate; dùng cookie mới nhất ở request kế tiếp.

**5. Vì sao có SESSION cookie trước login mà vẫn anonymous?**

> Một anonymous WebSession có thể được tạo để lưu CSRF token; không có authenticated principal.

**6. Vì sao POST /login cần CSRF?**

> Login CSRF có thể khiến browser đăng nhập tài khoản do attacker kiểm soát; Spring Security bảo vệ login request theo mặc định.

**7. CSRF token có thể dùng với session khác không?**

> Không. Expected token nằm trong WebSession tương ứng; session mismatch phải bị từ chối.

**8. Vì sao token GET /csrf có thể khác giữa các lần render dù session chưa đổi?**

> Spring Security 6.x có XOR/masking để giảm BREACH; không dựa trên so sánh raw masked token giữa các requests.

**9. POST /logout thiếu CSRF có nên được phép logout không?**

> Không, theo form/session default CSRF. Phải trả 403 và giữ session hiện hành.

**10. GET /logout có nên thực sự đăng xuất không?**

> Không theo cấu hình mặc định an toàn; GET dùng confirmation page, logout action dùng POST.

**11. Logout 302 chứng minh session đã invalidated chưa?**

> Chưa. Phải gửi GET /me với old cookie, xác nhận không còn authenticated.

**12. WebSessionServerLogoutHandler dùng để làm gì?**

> Invalidate active WebSession, bổ sung cho việc clear SecurityContext trong logout.

**13. Vì sao không dùng NoOpServerSecurityContextRepository cho form session login?**

> Nó không lưu Authentication qua requests, khiến login có thể không bền sang GET kế tiếp.

**14. Cookie HttpOnly/SameSite có thay CSRF token không?**

> Không. Chúng giảm rủi ro cụ thể nhưng không thay toàn bộ kiểm soát CSRF.

**15. Form login dùng HTTP body dạng gì mặc định?**

> application/x-www-form-urlencoded với username/password, kèm CSRF qua form parameter hoặc header.

**16. Vì sao test curl cần -c và -b?**

> -c ghi Set-Cookie mới, -b gửi cookie đã lưu ở request kế tiếp; có thể có session ID rotation.

**17. Session timeout nên test như thế nào?**

> Dùng test timeout/cấu hình store phù hợp và đo expiry, không Thread.sleep hàng chục phút trong CI.

**18. WebTestClient mock server có thay E2E browser/Gateway không?**

> Không. Nó kiểm WebFlux filters và session flow nhưng không đầy đủ TLS, proxy cookie rewrite, SameSite browser, Redis đa pod.

## 21. Tổng kết

Kiểm thử form login trong Spring Security WebFlux phải theo **đúng chuỗi HTTP stateful**:

~~~text
GET /csrf (+ Set-Cookie SESSION)
 -> POST /login (form username/password + SESSION + CSRF)
 -> 302 success (+ SESSION mới nếu rotation)
 -> GET /me (SESSION hiện hành) = 200, principal đúng
 -> POST /notes (SESSION + CSRF mới) = 200
 -> POST /logout (SESSION + CSRF mới)
 -> GET /me (OLD SESSION) = redirect login
~~~

Ba nguyên tắc:
1. **Không nhầm mock authorization với login thật.** Dùng `mockUser()`/`csrf()` cho request-level tests; dùng cookie jar và CSRF token thật để chứng minh login/session/logout.
2. **Kiểm cả trạng thái sau response.** Login 302 không đủ; GET protected trong request mới phải thành công. Logout 302 không đủ; old session cookie phải thất bại.
3. **Bảo vệ session lifecycle và CSRF.** Không disable CSRF để sửa test; kiểm cookie flags, session fixation, logout invalidation, distributed sessions và Gateway E2E trước production.

Project mẫu Java 17/Spring Boot 3.5 đưa ra **20 bài test HTTP session-flow + 4 test mock policy**, cùng mã chạy được về cấu trúc và lệnh Gradle/curl. Kết quả build/test chỉ được xác nhận sau khi thực thi tại môi trường phù hợp; không xem mô tả kỳ vọng là log build đã chạy.

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Getting Started WebFlux (login/logout): https://docs.spring.io/spring-security/reference/6.5/reactive/getting-started.html
- Spring Security 6.5 — Reactive Logout: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security 6.5 — Reactive CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security 6.5 — WebFlux Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — WebFlux Testing with CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Security API — WebSessionServerSecurityContextRepository: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security API — Reactive Logout Handlers: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/logout/package-summary.html
- Spring Boot 3.5 — server.reactive.session properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Session — Reactive WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session — WebFlux CookieWebSessionIdResolver: https://docs.spring.io/spring-session/reference/configuration/common.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html