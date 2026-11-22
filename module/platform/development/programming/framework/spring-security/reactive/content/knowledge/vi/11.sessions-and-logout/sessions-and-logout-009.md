# Phối hợp xóa cookie, hủy phiên và xử lý yêu cầu CSRF khi đăng xuất

## 1. Mục tiêu học tập

Trong Spring Security **reactive/WebFlux**, đăng xuất không đơn giản là xóa một cookie trong browser. Một ứng dụng dùng **form login và WebSession** thường có ba nhóm trạng thái liên quan:

- `SecurityContext` / `Authentication` đã lưu trong `ServerSecurityContextRepository`;
- `WebSession` ở server, bao gồm session ID, dữ liệu người dùng, CSRF token và các trạng thái nghiệp vụ;
- cookies phía client, bao gồm cookie ID phiên và những cookie riêng mà ứng dụng đặt.

Bên cạnh đó, **CSRF protection** kiểm soát việc ai có thể kích hoạt thao tác logout. Nếu ứng dụng cho phép một trang web khác ép trình duyệt gửi logout bằng GET, người dùng có thể bị đăng xuất ngoài ý muốn. Với Spring Security WebFlux, **POST /logout** và CSRF token là cơ chế mặc định quan trọng.

Bài học này giúp bạn:

1. Phân biệt xóa SecurityContext, invalidate WebSession và hết hạn cookie; biết vì sao các bước cần phối hợp.
2. Nắm rõ `LogoutWebFilter`, `SecurityContextServerLogoutHandler`, `WebSessionServerLogoutHandler`, `CsrfServerLogoutHandler` và `DelegatingServerLogoutHandler`.
3. Dùng `ServerHttpSecurity.logout(...)` cấu hình POST logout, cleanup và kết quả HTTP 204.
4. Gửi cookie hết hạn với cùng name/Path/Domain và `Max-Age=0`.
5. Hiểu cách trình duyệt lấy/gửi CSRF token, token cũ bị vô hiệu hóa và vấn đề session timeout.
6. Chạy một dự án Java 17+ Spring Boot WebFlux, thực hành với browser và kiểm tra `WebTestClient`.
7. Phân biệt logout session cục bộ với thu hồi JWT, refresh token hoặc logout mọi thiết bị.

**Phạm vi:** đăng xuất khi ứng dụng **dùng cookie và phiên ở server**. HTTP Basic không có phiên, OIDC SSO và JWT stateless có những yêu cầu thu hồi riêng, không thể giải quyết hoàn toàn bằng `WebSession.invalidate()`.

## 2. Vì sao “xóa cookie” không đồng nghĩa “đăng xuất”?

Mô hình thường gặp:

```text
Browser                                        Spring WebFlux
  |                                                 |
  | Cookie: SESSION=<id>                            |
  +------------------------------------------------>|
  |                                                 |
  |                           WebSession có id đó? --+
  |                                    |
  |                                    v
  |                           SecurityContext
  |                                    |
  |                                    v
  |                           Principal/Authorities
  |<------------------------------------------------+
  |                    response                      |
```

Cookie `SESSION` chủ yếu là **khóa tham chiếu**, không chứa toàn bộ dữ liệu session. Server dựa vào ID đó để tìm `WebSession`, sau đó tìm `SecurityContext` hoặc state khác.

**Tình huống A — chỉ xóa cookie:** browser không còn gửi cookie ở request mới, nhưng session ID vẫn có thể còn trong kho phiên của server. Nếu attacker có bản sao của ID, attacker có thể dùng nó đến khi session hết hạn.

**Tình huống B — chỉ invalidate server session:** session ID cũ không còn được server chấp nhận, đây là yếu tố bảo vệ chính. Nhưng trình duyệt có thể còn cookie cũ hoặc các cookie phụ trợ; giao diện SPA vẫn có thể hiển thị dữ liệu của người dùng từ memory.

**Tình huống C — chỉ xóa SecurityContext:** request mới không còn dùng authentication context đã lưu; nhưng một số thuộc tính nghiệp vụ trong WebSession có thể vẫn tồn tại. Nếu yêu cầu logout là hủy toàn bộ session, phải invalidate.

Do đó, logout cần đạt **hai mục tiêu độc lập**: (1) server không công nhận phiên cũ, (2) client không giữ hoặc gửi lại trạng thái cũ. Với form login, CSRF token cũng phải được quản lý phù hợp.

### Các thành phần

| Thành phần | Trách nhiệm | Ghi chú |
| --- | --- | --- |
| `SecurityContext` | Giữ `Authentication` và danh tính đã xác thực | Trong WebFlux được truyền theo Reactor Context |
| `ServerSecurityContextRepository` | Lưu/đọc security context giữa các request | Có thể dùng `WebSessionServerSecurityContextRepository` |
| `WebSession` | Lưu phiên và attributes phía server | Invalidate để session ID không còn hợp lệ |
| `WebSessionIdResolver` | Liên kết session ID với request/response | Default cookie name thường là `SESSION` |
| `ServerCsrfTokenRepository` | Sinh/lưu/đọc/xóa CSRF token | Default thường dùng WebSession |
| `LogoutWebFilter` | Nhận request logout đúng matcher | Default logout là POST |
| `ServerLogoutHandler` | Thực hiện cleanup lúc logout | Trả `Mono<Void>` |
| `ServerLogoutSuccessHandler` | Quyết định response sau logout | Redirect hoặc trả 200/204 tùy cấu hình |

Đừng sao chép nguyên mẫu logout Servlet (`HttpSession`, `SecurityContextLogoutHandler`) vào WebFlux: reactive dùng `WebSession` và `ServerLogoutHandler`.

## 3. Request logout đi qua pipeline như thế nào?

Với browser đang có cookie session:

```text
POST /logout
Cookie: SESSION=...
X-CSRF-TOKEN: <token của session hiện tại>
             |
             v
      CsrfWebFilter
      - method cần CSRF?
      - có token hợp lệ?
             |
       +-----+------+
       |            |
     không         đúng
       |            |
       v            v
   403 Forbidden  LogoutWebFilter
                    |
                    v
                ServerLogoutHandler
                    |
        +-----------+----------+-----------+
        |           |          |           |
   xóa context  xóa CSRF  invalidate   expire app
                           WebSession    cookies
        |           |          |           |
        +-----------+----------+-----------+
                    |
                    v
            LogoutSuccessHandler
                    |
                    v
               204 / redirect
                    |
                    v
          Client xóa trạng thái UI
```

Sơ đồ mô tả **logic**, không cam kết thứ tự tất cả WebFilter nội bộ của mọi phiên bản. Ở phần thực hành, chúng ta chủ động khai báo các logout handlers cần thiết để biết bước nào được thực hiện.

### Vì sao phải là POST?

Logout thay đổi trạng thái. GET nên dùng để đọc; browser, crawler, link preview hoặc trang khác có thể phát sinh GET ngoài ý muốn. Một endpoint GET gây logout tạo nguy cơ **logout CSRF**.

Theo hướng dẫn Spring Security WebFlux, `LogoutWebFilter` mặc định xử lý **HTTP POST /logout** để kết hợp với kiểm tra CSRF. GET /logout có thể hiển thị trang xác nhận cho người dùng, nhưng không phải cách thực hiện logout.

Không đổi sang GET hay tắt `csrf` chỉ vì thấy **403** khi POST: 403 thường là tín hiệu **thiếu, sai hoặc hết hạn token**, không phải bằng chứng rằng logout framework bị lỗi.

## 4. Các logout handler cần phối hợp

### 4.1. `SecurityContextServerLogoutHandler`

Class `org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler` xóa `SecurityContext` đã lưu thông qua `ServerSecurityContextRepository`. Đây là bước để security context cũ không được nạp lại ở request sau.

Nếu ứng dụng sử dụng một `ServerSecurityContextRepository` tùy chỉnh, logout phải làm sạch **đúng repository đó**. Không dùng `SecurityContextHolder.clearContext()` của Servlet như giải pháp chính trong WebFlux: pipeline reactive không cố định trên một thread duy nhất.

### 4.2. `WebSessionServerLogoutHandler`

Class `org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler` invalidate `WebSession` hiện tại. Nó loại bỏ server-side session state, chứ không chỉ xóa thuộc tính `Authentication`.

Tài liệu Spring Security reactive lưu ý thường phải cấu hình thêm handler này nếu muốn **invalidate toàn bộ WebSession** khi logout; không nên suy đoán handler mặc định luôn xử lý hết mọi thuộc tính session.

### 4.3. `CsrfServerLogoutHandler`

Class `org.springframework.security.web.server.csrf.CsrfServerLogoutHandler` dùng `ServerCsrfTokenRepository` để xóa CSRF token cũ. Khi tự định nghĩa một logout handler tổng hợp, hãy bảo đảm bước này không bị vô tình bỏ qua.

Quan trọng: nếu app cấu hình repository A để kiểm tra CSRF nhưng handler logout lại xóa repository B, bạn có thể không xóa đúng token. Hãy dùng **cùng một bean repository** cho cả hai.

### 4.4. `DelegatingServerLogoutHandler`

Class `org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler` thực thi nhiều `ServerLogoutHandler` qua một interface chung.

```java
ServerLogoutHandler coordinated =
        new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler());
```

Đây là đoạn **minh họa trong class cấu hình**, cần import các kiểu. Ví dụ chạy được phía dưới bổ sung `CsrfServerLogoutHandler` và một handler xóa cookie riêng. Các handler reactive trả `Mono<Void>`; không gọi `block()` trong WebFilter.

### 4.5. Logout success

`ServerLogoutSuccessHandler` trả phản hồi sau cleanup. Với browser thông thường có thể redirect về login; với SPA/API có thể trả `204 No Content`. Class `HttpStatusReturningServerLogoutSuccessHandler` nhận `HttpStatus.NO_CONTENT` để thực hiện điều này.

**HTTP 204 chỉ xác nhận success handler đã trả response.** Để chứng minh logout an toàn, vẫn phải thử request tiếp theo với session ID cũ.

## 5. Cookie: expire đúng name, Path và Domain

Một cookie được browser nhận diện theo scope bao gồm name và phạm vi domain/path. Muốn xóa cookie, server thường gửi `Set-Cookie` hết hạn với **cùng name, Path và Domain tương ứng**, đặt `Max-Age=0` hoặc `Expires` quá khứ.

Ví dụ:

```http
Set-Cookie: demo-pref=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax
```

Đây là ví dụ dễ đọc; thứ tự thuộc tính trong response có thể khác. Trong WebFlux, có thể làm:

```java
ResponseCookie expired = ResponseCookie.from("demo-pref", "")
        .path("/")
        .maxAge(Duration.ZERO)
        .httpOnly(true)
        .sameSite("Lax")
        .build();

exchange.getResponse().addCookie(expired);
```

Đoạn này là **fragment**, cần biến `ServerWebExchange exchange` và imports `ResponseCookie`, `Duration`.

Nếu cookie ban đầu dùng `Path=/app` nhưng logout dùng `Path=/`, browser có thể giữ cookie cũ; tương tự, host-only cookie và cookie có `Domain=example.com` có thể đòi hỏi cách expire khác nhau. Hai cookie cùng tên nhưng khác Path/Domain không phải cùng một cookie.

- `HttpOnly` giúp JavaScript không đọc session cookie; không bảo vệ khỏi mọi kiểu tấn công.
- `Secure` yêu cầu truyền cookie qua HTTPS; nên bật cho session/auth cookie production. Local demo HTTP cần cấu hình phù hợp để thử.
- `SameSite` giảm một số tình huống cross-site request; không thay thế CSRF token trong mọi kiến trúc.
- `Max-Age=0` yêu cầu browser xóa cookie, **không thu hồi** access token hoặc server-side session còn hiệu lực.

### Cookie session WebFlux khác `JSESSIONID`

`CookieWebSessionIdResolver` mặc định dùng tên **`SESSION`**. Đây là khác biệt đáng nhớ với ví dụ Servlet thường dùng `JSESSIONID`. Với Spring Session hoặc custom `WebSessionIdResolver`, tên/Path/SameSite có thể được thay đổi.

Để xóa session cookie, ưu tiên để **session infrastructure** xử lý khi invalidate rồi kiểm chứng response thực tế. Không mặc định hardcode `Set-Cookie: JSESSIONID=...` trong một ứng dụng WebFlux dùng `SESSION`. Nếu cần expire cookie tùy chỉnh do app tạo, dùng handler riêng và đúng scope.

### Có nên xóa toàn bộ cookie?

Không nhất thiết. Cookie consent, theme, locale hoặc cookie của identity provider có quyền sở hữu và chính sách khác. Xóa tất cả browser cookies có thể phá user preferences hoặc không thực hiện được do khác Domain. Hãy lập inventory, chỉ xóa những cookie thực sự cần dọn khi logout.

Nếu cân nhắc `Clear-Site-Data`, cần xác minh hỗ trợ browser, scope và tác động tới cache/offline storage. Header này không thay thế server-side invalidation.

## 6. CSRF token trước, trong và sau khi logout

### 6.1. Token đi cùng phiên

Spring Security WebFlux mặc định bật CSRF; `WebSessionServerCsrfTokenRepository` là lựa chọn thông thường để lưu expected token trong `WebSession`. `CsrfWebFilter` expose `Mono<CsrfToken>` trong `ServerWebExchange` attribute có key `CsrfToken.class.getName()`.

Với form, token được đưa vào hidden input `_csrf`. Với AJAX/fetch, client có thể gửi header, ví dụ `X-CSRF-TOKEN` theo repository mặc định. Token phải thuộc **session hiện hành**, không phải token của lần login trước.

Trong Spring Security 6.x, token được expose có thể được mask để chống BREACH, nên chuỗi token khác nhau giữa các lần render không nhất thiết là lỗi.

### 6.2. Thứ tự đúng

1. Browser đã có cookie session từ login.
2. Browser lấy CSRF token gắn với session đó qua form hoặc same-origin endpoint.
3. Browser gửi **POST /logout**, session cookie và CSRF token.
4. CSRF filter kiểm tra token; nếu sai hoặc thiếu, request bị chặn trước logout thành công.
5. Logout handlers xóa context/token, hủy session và expire cookies cần thiết.
6. Server trả 204 hoặc redirect theo giao diện.
7. Frontend xóa UI state và cache chứa dữ liệu đã xác thực.
8. Nếu user login lại, cần session và CSRF token mới.

**Không tái sử dụng CSRF token cũ** cho session mới. Sau login hoặc logout, token có thể được làm mới theo security configuration; SPA nên tải lại token trước POST tiếp theo.

### 6.3. Session đã timeout trước logout

Khi session hết hạn, CSRF token cũ không còn trong repository. Browser vẫn có thể giữ dữ liệu cũ trong memory và gửi POST /logout với token đã hết hạn; kết quả có thể là `403 Forbidden`. Đây không phải lý do hợp lệ để chuyển sang GET logout hoặc vô hiệu hóa CSRF.

Ứng dụng nên báo phiên hết hạn, dọn UI state phía client và yêu cầu lấy token/session mới nếu cần. Điều này khác logout thành công của một session đang hoạt động.

### 6.4. `CookieServerCsrfTokenRepository`

Nếu app dùng CSRF cookie riêng, thường là `XSRF-TOKEN` với header `X-XSRF-TOKEN`, hành vi lưu/xóa khác với WebSession repository. Logout phải xóa token ở repository đang dùng, đồng thời xem xét xóa cookie token đúng Path/Domain. `withHttpOnlyFalse()` cho phép JS đọc **CSRF token cookie**, không có nghĩa là nên cho JS đọc **session ID cookie**.

CSRF, cookie SameSite và CORS là các cơ chế bổ sung; không cơ chế nào thay việc xác thực/ủy quyền thực tế.

## 7. Dự án chạy được: Spring Boot 3.3.5 + WebFlux + form login

Ví dụ dành cho **Java 17+** và Gradle tương thích (chẳng hạn 8.5). Spring Security 6.x được quản lý qua Spring Boot BOM.

Cấu trúc:

```text
reactive-logout-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/logout/
    │   ├── LogoutApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/logout/
        └── LogoutSecurityTests.java
```

### 7.1. Build files

`settings.gradle`:

```groovy
rootProject.name = 'reactive-logout-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
```

Đừng thêm `spring-boot-starter-web` khi mục tiêu là WebFlux thuần: Spring Boot thường ưu tiên Servlet nếu cả hai starter được khai báo.

### 7.2. Lớp khởi động

`src/main/java/dev/example/logout/LogoutApplication.java`:

```java
package dev.example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutApplication.class, args);
    }
}
```

### 7.3. Spring Security với logout phối hợp

`src/main/java/dev/example/logout/SecurityConfig.java`:

```java
package dev.example.logout;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.HttpStatusReturningServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfServerLogoutHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    ServerCsrfTokenRepository csrfTokenRepository() {
        return new WebSessionServerCsrfTokenRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerCsrfTokenRepository csrfRepository) {

        ServerLogoutHandler expireAppCookie = (filterExchange, auth) -> {
            ResponseCookie expired = ResponseCookie.from("demo-pref", "")
                    .path("/")
                    .maxAge(Duration.ZERO)
                    .httpOnly(true)
                    .sameSite("Lax")
                    .build();
            filterExchange.getExchange()
                    .getResponse().addCookie(expired);
            return Mono.empty();
        };

        ServerLogoutHandler coordinated =
                new DelegatingServerLogoutHandler(
                        new SecurityContextServerLogoutHandler(),
                        new CsrfServerLogoutHandler(csrfRepository),
                        new WebSessionServerLogoutHandler(),
                        expireAppCookie);

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/public", "/login", "/csrf")
                            .permitAll()
                        .anyExchange().authenticated())
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .formLogin(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutHandler(coordinated)
                        .logoutSuccessHandler(
                                new HttpStatusReturningServerLogoutSuccessHandler(
                                        HttpStatus.NO_CONTENT)))
                .build();
    }
}
```

**Ý nghĩa từng phần:**

- User mẫu `reader / reader-pass` phục vụ local demo, password được BCrypt encode khi tạo `UserDetails`. Không dùng mật khẩu demo trên server công khai.
- CSRF filter và `CsrfServerLogoutHandler` cùng sử dụng bean `csrfTokenRepository`.
- `formLogin` bật cơ chế đăng nhập lưu security context vào WebSession, khác HTTP Basic thuần gửi credentials mỗi request.
- `SecurityContextServerLogoutHandler` xóa authentication đã lưu; `CsrfServerLogoutHandler` xóa token CSRF; `WebSessionServerLogoutHandler` invalidate session; lambda cuối expire cookie `demo-pref`.
- `logoutUrl("/logout")` giữ quy trình **POST**; không mở logout bằng GET hoặc disable CSRF.
- `HttpStatusReturningServerLogoutSuccessHandler(NO_CONTENT)` trả `204` thay vì chuyển hướng trang login.
- `anyExchange().authenticated()` bảo vệ endpoint ngoài danh sách public. Logout filter xử lý request logout theo matcher riêng.
- Nếu bạn tự đổi `ServerSecurityContextRepository` hay `ServerCsrfTokenRepository` trong dự án, phải đồng bộ handler với repository đang dùng.

**Về duplicate cleanup:** khi tự thay `logoutHandler`, cần biết handler nào được giữ lại trong phiên bản framework và không bỏ qua bước dọn CSRF/session. Ví dụ trên khai báo rõ các thành phần muốn thực hiện. Không mặc định mọi custom handler được cộng dồn tự động với các handler mặc định.

### 7.4. Controller WebFlux

`src/main/java/dev/example/logout/DemoController.java`:

```java
package dev.example.logout;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.ResponseCookie;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(
            Principal principal, ServerHttpResponse response) {

        response.addCookie(ResponseCookie.from("demo-pref", "seen")
                .path("/")
                .httpOnly(true)
                .sameSite("Lax")
                .build());

        return Mono.just(Map.of("user", principal.getName()));
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF filter did not expose a token"));
        }

        return tokenPublisher.map(token -> Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()));
    }
}
```

`/csrf` trả token dành cho thử nghiệm, gắn với session khi client nhận và gửi cookie. Spring Security 6.x expose `Mono<CsrfToken>` trong exchange attribute, có thể được subscribe theo cách này mà không cần gọi `block()`. Khi chuyển thành ứng dụng production, xem lại same-origin policy, CORS, HTTP caching, token response và logging để không làm lộ token.

`/me` tạo cookie không nhạy cảm `demo-pref=seen` với `Path=/` chỉ để có một cookie tùy chỉnh mà logout có thể xóa. Cấu hình production nên bật `Secure` khi dùng HTTPS; demo chạy `http://localhost` nên không bật ở đây.

## 8. Thực hành logout từ trình duyệt

Khởi động:

```bash
gradle bootRun
```

Nếu có wrapper, dùng `./gradlew bootRun` hoặc `gradlew.bat bootRun`. Giả sử server đang ở `http://localhost:8080`.

**Bước 1 — đăng nhập:** mở `http://localhost:8080/login`, đăng nhập với `reader` và mật khẩu demo `reader-pass`. Spring Security có thể sinh trang login mặc định có token CSRF cho POST login.

**Bước 2 — kiểm tra phiên:** mở `http://localhost:8080/me`. Body dự kiến:

```json
{"user":"reader"}
```

Trong DevTools Application/Cookies, bạn thường thấy cookie `SESSION` do WebFlux và `demo-pref` do controller tạo. Có thể điều chỉnh tên cookie session qua resolver, nên kiểm tra thực tế.

**Bước 3 — lấy CSRF hiện tại:** mở `http://localhost:8080/csrf` (hoặc dùng same-origin `fetch`). JSON chứa `token`, `headerName`, `parameterName`. Token có thể được làm mới sau login; đừng dùng token đã lấy trước khi đăng nhập.

**Bước 4 — gửi POST logout hợp lệ:** trong DevTools Console cùng origin:

```javascript
const csrf = await fetch("/csrf", {
  credentials: "same-origin"
}).then(response => response.json());

const response = await fetch("/logout", {
  method: "POST",
  credentials: "same-origin",
  headers: { [csrf.headerName]: csrf.token }
});

console.log(response.status); // Dự kiến 204
```

Đây là request POST kèm session cookie và CSRF token. Kết quả 204 nghĩa là success handler trả status thành công; hãy kiểm tra cả việc expire cookie `demo-pref` và kết quả của request dùng session cũ.

**Bước 5 — kiểm tra sau logout:** mở lại `/me`. Với form login, request không còn authenticated và thường được redirect về `/login`. Cookie `demo-pref` đã được yêu cầu hết hạn. Từ browser network tab, kiểm tra `Set-Cookie` có `Max-Age=0` đúng Path và session cookie được xử lý ra sao.

### Thử cố ý thiếu CSRF

Khi **vẫn còn đang đăng nhập**, thử:

```javascript
const response = await fetch("/logout", {
  method: "POST",
  credentials: "same-origin"
});

console.log(response.status); // Dự kiến 403
```

Không có CSRF token thì request bị chặn, và không nên coi là đã logout. Sau đó gửi lại bằng token đúng. Nếu session đã timeout, token cũ có thể không còn hợp lệ; cần quy trình UX riêng cho session expired.

### Tại sao không dùng GET logout?

`fetch("/logout")` không chỉ định method sẽ gửi **GET**. GET không phải một thao tác logout đã được CSRF bảo vệ; Spring Security có thể trả trang xác nhận. Đừng tạo menu “Đăng xuất” như một link GET làm thay đổi trạng thái.

## 9. Kiểm thử với `WebTestClient`

Tệp `src/test/java/dev/example/logout/LogoutSecurityTests.java`:

```java
package dev.example.logout;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class LogoutSecurityTests {

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
    void csrfEndpointReturnsToken() {
        client.get().uri("/csrf")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.token").exists()
                .jsonPath("$.headerName").exists();
    }

    @Test
    void authenticatedMeReturnsIdentity() {
        client.mutateWith(mockUser("reader"))
                .get().uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void postLogoutWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("reader"))
                .post().uri("/logout")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postLogoutWithCsrfExpiresCookieAndReturns204() {
        client.mutateWith(mockUser("reader"))
                .mutateWith(csrf())
                .post().uri("/logout")
                .exchange()
                .expectStatus().isNoContent()
                .expectHeader()
                .values(HttpHeaders.SET_COOKIE, values ->
                        assertTrue(values.stream().anyMatch(cookie ->
                                cookie.startsWith("demo-pref=")
                                        && cookie.contains("Max-Age=0"))));
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả dự kiến:** 4 test thành công với dự án/dependencies như trên. Đây là kỳ vọng từ cấu hình ví dụ, **không phải tuyên bố đã chạy Gradle trong repository của bạn**.

Các test kiểm tra CSRF gate, response logout, user mock và cookie expire. **Giới hạn:** `mockUser` chỉ tạo security context cho mock exchange, không thay một chuỗi **login thật → browser session ID → logout → thử lại ID cũ**. Vì vậy phải có bài kiểm thử E2E riêng để chứng minh session thực sự bị invalidate ở server.

### Ma trận kiểm thử logout

| Trường hợp | Kết quả mong đợi | Điều cần xác minh |
| --- | --- | --- |
| POST thiếu token | 403 | Handler logout không được coi là thành công |
| POST với token sai | 403 | Không chấp nhận token tự chế |
| POST với token đúng | 204 trong demo | Logout success handler |
| Cookie `demo-pref` | `Set-Cookie` hết hạn cùng Path/Domain | Browser xóa cookie thật |
| Gửi lại SESSION ID cũ | Không còn truy cập được `/me` như user trước | Server session invalidated |
| GET /logout | Không thực hiện logout trực tiếp | Tránh logout CSRF |
| Logout sau timeout | Có thể 403/redirect tùy flow | UX của session đã hết hạn |
| Login lại sau logout | Session và token mới | Không dùng lại CSRF cũ |
| Hai tab cùng session | Tab kia không còn authenticated | UI đồng bộ trạng thái |
| Hai thiết bị khác session | Phạm vi theo chính sách | Không nhầm session hiện tại với global logout |

Kiểm thử session invalidation thực bằng HTTP client có cookie jar hoặc browser E2E: login thật, giữ một bản ID thử nghiệm, logout có CSRF, sau đó gửi lại ID cũ. Nếu server vẫn nhận user đã đăng nhập, phần server cleanup có lỗi, dù response logout đã 204.

## 10. Những ranh giới cần phân biệt

### 10.1. Session ID cũ và browser cookie cũ

Nếu server đã invalidate nhưng browser vẫn gửi ID cũ, request tiếp theo phải không còn authenticated. Lúc này phần server-side bảo mật đã đạt, nhưng client state vẫn có thể cần dọn.

Ngược lại, xóa cookie client mà không xóa session server vẫn để lại nguy cơ nếu session ID bị đánh cắp. Phải kiểm tra **khả năng dùng lại session ID cũ**, không chỉ kiểm tra cookie đã biến mất.

### 10.2. Nhiều tab cùng browser

Các tab cùng origin thường chia sẻ session cookie nhưng có state UI riêng. Logout ở tab A khiến tab B không còn authenticated, song tab B vẫn có thể hiển thị tên user cũ. Frontend nên xóa state/cache và, khi cần, dùng cơ chế đồng bộ tab như `BroadcastChannel`. Đây là UX cleanup, không phải server invalidation.

### 10.3. Logout mọi thiết bị

`WebSessionServerLogoutHandler` hủy **session hiện tại**. Nó không tự tìm các session cùng user trên những thiết bị khác. Chức năng “đăng xuất ở mọi thiết bị” cần session index/registry hoặc token revocation cơ sở dữ liệu phù hợp.

### 10.4. Spring Session / Redis

Khi sử dụng session store phân tán, cần chắc rằng invalidate đi tới backend chung để instance khác từ chối session ID cũ. Cookie name/Path có thể được custom và không còn mặc định. Test trên nhiều instance, đừng chỉ test một node local.

### 10.5. HTTP Basic và JWT

Nếu client tiếp tục gửi `Authorization: Basic username:password` trong mỗi request, session logout không ngăn được việc **xác thực lại bằng credential đó**. Tương tự, xóa cookie không thu hồi JWT vẫn còn hạn. Các loại token stateless cần expiry, refresh-token revocation, token denylist hoặc cơ chế khác nếu threat model đòi hỏi.

### 10.6. OIDC/SSO

Xóa session cục bộ không mặc định logout khỏi Identity Provider. Với OIDC, có thể cần `OidcClientInitiatedServerLogoutSuccessHandler` hoặc luồng logout federation được IdP hỗ trợ. Đừng tuyên bố logout toàn bộ hệ thống khi mới xóa session của ứng dụng.

### 10.7. HTTPS và cookie production

Production nên dùng HTTPS với cookie phiên có `Secure`, `HttpOnly` và `SameSite` theo threat model. Với proxy terminate TLS, chỉ tin forwarded headers từ proxy được kiểm soát; đừng tin giá trị `X-Forwarded-Proto` do client tự đặt. CSRF và TLS giải quyết hai nguy cơ khác nhau.

## 11. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Bấm “logout” nhưng không đăng xuất | UI chỉ gửi GET hoặc xóa state frontend | Gửi POST có token, kiểm tra server handlers |
| POST logout 403 | Token thiếu, sai, session khác hoặc đã hết hạn | Lấy CSRF hiện hành, đừng disable CSRF |
| POST trả 204 nhưng ID cũ vẫn truy cập được | Chưa invalidate session hoặc repo không khớp | Kiểm tra `WebSessionServerLogoutHandler` và session store |
| Cookie không mất | Path/Domain của expire cookie không đúng | So sánh `Set-Cookie` lúc tạo và lúc xóa |
| Xóa nhầm `JSESSIONID` | WebFlux đang dùng `SESSION` | Đọc cấu hình `WebSessionIdResolver` |
| CSRF cũ vẫn xuất hiện trong SPA | Client cache token qua login/logout | Xóa cache, lấy token mới cho session mới |
| Đăng xuất một tab nhưng tab khác còn tên user | UI chưa cập nhật | Đồng bộ client state, để server từ chối phiên cũ |
| Logout một thiết bị, thiết bị khác vẫn đăng nhập | Mặc định hủy một session | Thiết kế logout mọi session riêng |
| JWT còn hoạt động sau logout | Không revoke JWT | Thiết kế token lifecycle |
| Cookie bị xóa nhưng server session vẫn sống | Chỉ expire cookie | Invalidate ở server và test ID cũ |
| Spring app dùng `SecurityContextHolder` Servlet | Nhầm reactive Context với ThreadLocal | Dùng reactive logout handlers/repository |
| Test `mockUser` xanh nhưng E2E sai | Test không tạo real session | Test login thật, cookie jar và ID reuse |
| Tắt CSRF để chữa 403 | Tạo nguy cơ logout CSRF | Duy trì POST và token |
| Custom handler làm mất cleanup mặc định | Thay handler nhưng bỏ context/token/session | Dùng delegating handler có đầy đủ trách nhiệm |

### Các anti-pattern nên tránh

**Chỉ expire cookie:**

```java
// Chỉ minh họa: chưa invalidate server-side WebSession.
response.addCookie(ResponseCookie.from("SESSION", "")
        .path("/").maxAge(Duration.ZERO).build());
```

**Tắt CSRF để POST logout trả 2xx:**

```java
// Không phù hợp với app browser dùng cookie/session.
http.csrf(csrf -> csrf.disable());
```

**Logout qua GET:**

```http
GET /logout HTTP/1.1
Cookie: SESSION=...
```

Cả ba trường hợp trên có thể dẫn tới rủi ro bảo mật hoặc trạng thái client/server không đồng bộ.

## 12. Câu hỏi tự kiểm tra

**1.** `SecurityContextServerLogoutHandler` khác `WebSessionServerLogoutHandler` thế nào?  
**Đáp án:** Một bên xóa authentication context đã lưu; bên còn lại invalidate toàn bộ WebSession.

**2.** Vì sao xóa cookie chưa đủ?  
**Đáp án:** Session ID cũ có thể vẫn hợp lệ phía server và bị tái sử dụng nếu lộ.

**3.** Vì sao server invalidate vẫn cần quan tâm cookie?  
**Đáp án:** Browser có thể còn state/cookie cũ và ứng dụng còn cookie khác cần dọn.

**4.** Phương thức nào dùng để logout trong WebFlux mặc định?  
**Đáp án:** POST /logout, có CSRF protection khi được bật.

**5.** POST /logout không có token sẽ thế nào?  
**Đáp án:** Thường nhận 403, không thực hiện logout thành công.

**6.** GET /logout có được dùng để logout trực tiếp không?  
**Đáp án:** Không nên; có thể là trang xác nhận và không được thiết kế như state-changing logout.

**7.** Xóa cookie cần khớp những thuộc tính quan trọng nào?  
**Đáp án:** Name cùng Path và Domain scope; gửi `Max-Age=0` hoặc Expires quá khứ.

**8.** WebFlux mặc định thường đặt cookie phiên tên gì?  
**Đáp án:** `SESSION` với `CookieWebSessionIdResolver`; cần xác minh nếu có custom config.

**9.** Vì sao phải lấy token mới sau logout?  
**Đáp án:** Token cũ thuộc ngữ cảnh session trước; request state-changing trong session mới cần token hợp lệ mới.

**10.** `mockUser` + `csrf()` có chứng minh server session ID bị vô hiệu hóa không?  
**Đáp án:** Chưa; cần kiểm tra real login/logout và tái sử dụng ID cũ.

**11.** Logout cục bộ có kết thúc mọi session cùng user ở máy khác không?  
**Đáp án:** Không mặc định.

**12.** Logout session có thu hồi JWT không?  
**Đáp án:** Không. Session và token lifecycle là cơ chế khác nhau.

### Bài tập thực hành

1. Chạy demo, login, mở `/me`, POST logout với CSRF hợp lệ; kiểm tra `Set-Cookie` expire và request `/me` không còn authenticated.
2. Thử gửi POST thiếu CSRF khi đang có phiên, quan sát 403; không tắt CSRF.
3. Tạo cookie với `Path=/account`, thử expire với `Path=/` và `Path=/account`, so sánh kết quả trong DevTools.
4. Thử thay `HttpStatusReturningServerLogoutSuccessHandler` bằng redirect success handler phù hợp cho browser, giữ nguyên các bước cleanup.
5. Tạo E2E test dùng cookie jar: login thật, lưu ID, logout, thử gửi ID cũ từ client khác.
6. Tìm nguyên nhân một user bị đăng xuất ở tab A nhưng tab B vẫn hiển thị nội dung cũ; mô tả ranh giới UX/client/server.
7. Nếu dùng Redis session store, kiểm tra request đến instance khác sau logout.
8. Lập bản thiết kế “logout all devices” nêu rõ session registry, refresh tokens, identity provider và phạm vi thu hồi.

## 13. Tài liệu chính thức

- [Spring Security — Logout cho WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html): phối hợp context/session handlers.
- [Spring Security — CSRF cho WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html): logout POST, token và session timeout.
- [Spring Security API — ServerHttpSecurity.LogoutSpec](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.LogoutSpec.html): logout URL và handlers.
- [Spring Security API — CsrfServerLogoutHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfServerLogoutHandler.html): xóa token.
- [Spring Security — Test CSRF với WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `mutateWith(csrf())`.
- [Spring Framework — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html): cookie `SESSION` và resolver.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Path, Domain, Max-Age và cookie security.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): bảo vệ request thay đổi trạng thái.

**Ghi nhớ:** Logout trong Spring Security reactive là quy trình **POST có CSRF hợp lệ → clear SecurityContext → clear CSRF token → invalidate WebSession → expire đúng cookies → cập nhật UI**. Không được nhầm việc xóa cookie phía client với việc thu hồi session/tokens trên server.