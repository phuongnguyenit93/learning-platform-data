# CSRF, CORS và cookie khi client trình duyệt gọi endpoint đăng nhập JSON

## 1. Phạm vi: JSON login dùng HTTP session trong Spring Security Servlet

Một ứng dụng web có thể cho JavaScript gọi `POST /api/login` bằng body JSON thay vì gửi form HTML. Khi yêu cầu đăng nhập thành công, backend xác thực username/password, lưu `SecurityContext` vào HTTP session và gửi cookie phiên (thường là `JSESSIONID`). Những lần gọi API tiếp theo không cần gửi lại mật khẩu: browser gửi cookie để backend tìm phiên đã xác thực.

Ba cơ chế khác nhau tác động đồng thời:

| Cơ chế | Quyết định điều gì? | Dấu hiệu thường thấy |
| --- | --- | --- |
| **CSRF** | Request có thao tác thay đổi dữ liệu và dựa vào credential mà browser tự đính kèm có kèm bằng chứng chống giả mạo hợp lệ không? | Token trong header `X-CSRF-TOKEN`; thiếu/sai thường 403. |
| **CORS** | JavaScript chạy ở một **origin** khác có được phép gửi/đọc request và response theo chính sách browser không? | `Origin`, preflight `OPTIONS`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`. |
| **Cookie phiên** | Browser có lưu và gửi ID phiên sang backend không; backend có phục hồi được danh tính từ ID đó không? | `Set-Cookie: JSESSIONID=...` và `Cookie: JSESSIONID=...`. |

**JSON không tự làm request miễn nhiễm CSRF.** Nếu xác thực dựa vào cookie phiên, browser thường tự gắn cookie vào request phù hợp; đó là điều khiến CSRF trở thành vấn đề. Ngược lại, CORS chỉ là chính sách kiểm soát truy cập response của JavaScript trong browser; không phải cơ chế xác thực, cũng không bảo đảm chống CSRF.

Bài dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring MVC/Servlet**. Giả định endpoint JSON login duy trì phiên đăng nhập. Một API dùng Bearer token được client chủ động đặt trong header `Authorization` có mô hình rủi ro khác, cần đánh giá riêng; không suy luận cứ là JSON thì có hoặc không có CSRF.

## 2. Phân biệt origin và site trước khi cấu hình

**Origin** là bộ ba `scheme + host + port`. Vì vậy:

- `http://localhost:5173` và `http://localhost:8080`: **khác origin** (khác port) nhưng thường **cùng site**.
- `https://app.example.com` và `https://api.example.com`: **khác origin** (khác subdomain) nhưng cùng site nếu cùng scheme và cùng registrable domain.
- `https://frontend.example.net` và `https://api.example.com`: khác origin **và** khác site.

Browser áp dụng **CORS theo origin**, còn thuộc tính cookie `SameSite` xét quan hệ **site** (ngày nay thường xét cả scheme, gọi là *schemeful same-site*). Từ đó rút ra hai hệ quả:

1. Client ở `localhost:5173` gọi backend `localhost:8080` vẫn cần cấu hình CORS, dù `SameSite=Lax` có thể không ngăn cookie vì đây là same-site.
2. Frontend ở một domain hoàn toàn khác backend thường cần cookie `SameSite=None; Secure` để gửi qua cross-site `fetch`, nhưng vẫn có thể bị chính sách chặn third-party cookies của browser; chỉ bật CORS không giải quyết được.

`Domain` và `Path` của cookie quyết định host/path mà cookie được gửi đến. Cookie host-only do `api.example.com` đặt vẫn được gửi tới `api.example.com` khi frontend ở `app.example.com` gọi API, nếu các điều kiện khác cho phép; không cần tự đặt `Domain=.example.com`. Đặt cookie cho toàn bộ domain có thể mở rộng phạm vi ngoài nhu cầu.

## 3. Luồng JSON login bằng cookie session và CSRF

Ví dụ frontend chạy trên `http://localhost:5173`, backend trên `http://localhost:8080`.

~~~text
Frontend browser                 Spring Security / Backend
       |                                    |
       | GET /api/csrf                     |
       | credentials: include              |
       |----------------------------------->|
       |        tạo/đọc CSRF token          |
       |<-----------------------------------|
       | JSON: headerName + token           |
       | Set-Cookie: JSESSIONID=...         |
       |                                    |
       | OPTIONS /api/login (preflight)     |
       | Origin, Content-Type, X-CSRF-TOKEN |
       |----------------------------------->|
       |<-----------------------------------|
       | CORS cho phép origin/header/method |
       |                                    |
       | POST /api/login                    |
       | Cookie: JSESSIONID=...             |
       | X-CSRF-TOKEN: <token>              |
       | Body: {"username":"alice",...}     |
       |----------------------------------->|
       | CSRF filter kiểm tra token         |
       | AuthenticationManager xác thực     |
       | đổi session id, lưu SecurityContext|
       |<-----------------------------------|
       | 200 JSON + cookie phiên mới (nếu cần)
       |                                    |
       | GET /api/csrf (token mới)          |
       |----------------------------------->|
       |<-----------------------------------|
       |                                    |
       | GET /api/me + cookie phiên         |
       |----------------------------------->|
       |<-----------------------------------|
       | 200 {"username":"alice"}           |
~~~

**Vì sao lấy CSRF token trước login?** Spring Security bảo vệ các HTTP method thay đổi trạng thái như POST. Login cũng là thao tác nhạy cảm: yêu cầu đăng nhập giả mạo (*login CSRF*) có thể buộc nạn nhân đăng nhập vào tài khoản do kẻ tấn công kiểm soát, rồi vô tình nhập dữ liệu vào tài khoản đó. Việc endpoint `/api/login` được cấu hình `permitAll()` chỉ nói rằng **chưa cần đăng nhập**; nó **không bỏ qua `CsrfFilter`**.

**Vì sao lấy CSRF token lại sau login?** Theo cơ chế CSRF của Spring Security, `CsrfAuthenticationStrategy` có thể xóa token cũ sau khi xác thực thành công; `CsrfLogoutHandler` xóa token sau logout. Client nên xin token mới trước lần POST tiếp theo. Spring Security 6 còn có deferred token và cơ chế bảo vệ BREACH, nên đừng giả định giá trị token luôn cố định hoặc chỉ cần lấy đúng một lần cho cả đời ứng dụng.

## 4. CSRF là gì và xảy ra lúc nào?

Giả sử user đã đăng nhập `https://api.example.com` bằng cookie phiên. Người đó mở trang độc hại ở origin khác. Trang độc hại có thể dụ browser gửi một request gây thay đổi trạng thái tới API; trong hoàn cảnh cookie được browser tự đính kèm, backend có thể nhận request dưới danh nghĩa user hiện tại.

CSRF không đòi kẻ tấn công biết mật khẩu hoặc đọc được cookie `HttpOnly`. Đặc trưng của CSRF là **lạm dụng credential được browser tự gắn**.

Ví dụ logic:

~~~text
Nạn nhân có cookie phiên hợp lệ → mở trang của kẻ tấn công
→ trang đó tìm cách gửi thao tác tới website mục tiêu
→ browser tự đính kèm cookie nếu chính sách cookie cho phép
→ nếu server chỉ kiểm tra cookie, thao tác có thể bị thực hiện
→ CSRF token / kiểm tra Origin phù hợp có thể chặn giả mạo
~~~

Cần phân biệt thêm: request JSON với `Content-Type: application/json` thường gây **CORS preflight** khi đi cross-origin. Điều này giúp một số kiểu request từ JavaScript bị chặn trước khi gửi, nhưng **không thay thế CSRF protection**. Vẫn phải xét HTML form, endpoint chấp nhận simple content type, cấu hình proxy, cùng-site subdomain không tin cậy và các thay đổi hành vi sau này. Trên hệ thống session-cookie, hãy giữ CSRF protection cho các thao tác thay đổi trạng thái.

### 4.1. Token được kiểm tra ra sao?

Trong cấu hình Spring Security Servlet thường gặp:

1. Server tạo hoặc tải token từ `CsrfTokenRepository`; mặc định thường là `HttpSessionCsrfTokenRepository`.
2. Client lấy token bằng trang HTML hoặc một endpoint GET được thiết kế để cung cấp token.
3. Với POST/PUT/PATCH/DELETE, JavaScript đặt token trong header, thường là `X-CSRF-TOKEN`.
4. `CsrfFilter` kiểm tra token phía request với token server mong đợi, **trước khi controller login được gọi**.
5. Thiếu, sai hoặc hết hạn token thường nhận `403 Forbidden`, kể cả khi username/password đúng.

Đừng gửi token chống CSRF qua URL query string: URL có thể vào history, Referer hoặc log. Trong JSON API, một request header riêng là lựa chọn phổ biến.

### 4.2. HttpSessionCsrfTokenRepository và CookieCsrfTokenRepository

Hai hướng phân phối token thường gặp:

| | `HttpSessionCsrfTokenRepository` | `CookieCsrfTokenRepository` |
| --- | --- | --- |
| Nơi lưu token mong đợi | HTTP session trên server | Cookie phía browser |
| Cách SPA lấy token | GET `/api/csrf` trả JSON hoặc server-rendered meta tag | SPA có thể đọc cookie `XSRF-TOKEN` nếu được cấu hình không `HttpOnly` |
| Header gửi lại | Thường `X-CSRF-TOKEN` | Thường `X-XSRF-TOKEN` |
| Lưu ý Spring Security 6 | Token có thể deferred và được biểu diễn dạng đã mask để chống BREACH | Nếu JS gửi giá trị cookie chưa mask, cần cấu hình request handler SPA phù hợp với BREACH |
| Ưu tiên trong ví dụ | **Dùng để tránh lộ token qua cookie JS đọc được** | Phù hợp khi framework SPA cần cơ chế cookie XSRF; phải cấu hình đúng |

**`JSESSIONID` không phải CSRF token.** Cookie phiên thường phải `HttpOnly`; JavaScript không cần đọc ID phiên. Endpoint `GET /api/csrf` có thể trả CSRF token qua JSON cho JavaScript cùng quyền truy cập hợp lệ; response không nên bị shared cache lưu lại và cần hạn chế origin được phép đọc.

## 5. CORS làm gì với browser fetch?

CORS được browser thực thi khi JavaScript ở **origin A** gọi URL ở **origin B**. Server biểu đạt origin/method/header được phép; browser quyết định có cho JavaScript đọc response hay tiếp tục request có preflight hay không.

Với request:

~~~http
OPTIONS /api/login HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Backend có thể trả (minh họa):

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
~~~

`OPTIONS` là **preflight**: browser hỏi chính sách trước khi gửi POST. Preflight thường **không mang cookie phiên**, nên Spring Security cần xử lý CORS trước lớp yêu cầu xác thực; nếu chặn OPTIONS vì “chưa đăng nhập”, browser sẽ báo lỗi CORS ngay cả khi POST hợp lệ.

Điều cần nhớ:

- `Access-Control-Allow-Origin` phải phù hợp **origin chính xác** khi dùng credential. Không ghép `Access-Control-Allow-Credentials: true` với `Access-Control-Allow-Origin: *`.
- `Access-Control-Allow-Credentials: true` cho phép browser xử lý credentialed CORS response theo chính sách; nó **không tạo cookie** và không thay `credentials: "include"` của fetch.
- `Access-Control-Allow-Headers` cần cho phép `Content-Type` và `X-CSRF-TOKEN` khi client dùng chúng.
- CORS không bảo vệ request từ cURL hoặc ứng dụng server-to-server: các client ngoài browser không bị cơ chế chặn CORS của browser ràng buộc.
- Không bật CORS toàn cầu cho mọi origin chỉ vì phát triển local. Giới hạn cụ thể origin, method, header và endpoint cần thiết.
- Nếu JavaScript không thể đọc response do CORS, request đơn giản đã được gửi vẫn có thể gây thay đổi trên server. **CORS không phải tường lửa chống CSRF.**

## 6. Cookie: `HttpOnly`, `Secure`, `SameSite` và chính sách browser

Session cookie nên mang ID ngẫu nhiên, khó đoán; trạng thái xác thực nằm ở backend. Sau login, server có thể cập nhật `JSESSIONID` để chống session fixation. Ví dụ header được đơn giản hóa:

~~~http
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

| Thuộc tính | Ý nghĩa thực tế |
| --- | --- |
| `HttpOnly` | Không cho JavaScript đọc cookie bằng `document.cookie`, giảm nguy cơ lấy ID phiên qua XSS. Browser vẫn có thể gửi cookie trong HTTP request. |
| `Secure` | Chỉ gửi cookie qua HTTPS (một số browser có ngoại lệ cho `localhost`). Production phải dùng HTTPS. |
| `SameSite=Strict` | Hạn chế cookie ở request cross-site mạnh hơn, nhưng có thể ảnh hưởng luồng điều hướng. |
| `SameSite=Lax` | Giảm gửi cookie trong nhiều ngữ cảnh cross-site; thường phù hợp frontend/backend **cùng site**. Không thay CSRF token. |
| `SameSite=None; Secure` | Cho phép gửi cookie ở ngữ cảnh cross-site nếu browser/chính sách third-party cookie cho phép; cần HTTPS. |
| `Path` / `Domain` | Giới hạn các đường dẫn và host có thể nhận cookie; ưu tiên phạm vi hẹp phù hợp. |
| `Max-Age` / `Expires` | Quyết định vòng đời cookie; **không bảo đảm phiên server vẫn còn**. |

Browser có thể chặn third-party cookies, partition cookie, hoặc kiểm soát quyền riêng tư khác; do đó **`SameSite=None` không bảo đảm đăng nhập cross-site hoạt động trên mọi thiết bị**. Nếu sản phẩm cho phép, triển khai SPA và API dưới cùng site hoặc dùng backend-for-frontend/reverse proxy cùng origin thường giúp đơn giản hóa.

**Lưu ý `HttpOnly`:** không dùng `document.cookie` để đọc `JSESSIONID`. JavaScript chỉ cần:

~~~js
fetch("http://localhost:8080/api/me", {
  credentials: "include"
});
~~~

Browser quyết định có đính kèm cookie hay không. Ở request cross-origin, `fetch` mặc định `credentials: "same-origin"`, nên nếu frontend ở port khác, phải đặt `"include"`. Ngay cả khi đã đặt, cookie vẫn có thể bị chặn bởi `SameSite`, `Secure`, `Domain`, `Path`, third-party cookie policy hoặc browser settings.

Không thể đọc `Set-Cookie` từ `response.headers.get("set-cookie")` trong JavaScript: đây là response header bị browser bảo vệ. Quan sát cookie qua DevTools Network/Application hoặc kiểm thử HTTP client; không cố tự đặt header `Cookie` trong `fetch`.

## 7. Ví dụ Spring Boot 3.x: JSON login, session cookie, CSRF và CORS

Ví dụ **chạy thử được** bằng Spring Boot 3.x / Spring Security 6.x, Java 17+. Backend lắng nghe mặc định `localhost:8080`; frontend development server ở `localhost:5173`. Tài khoản và password chỉ là dữ liệu giả phục vụ demo.

### 7.1. Dependency và cấu trúc file

Trong dự án đã cấu hình Gradle Spring Boot plugin, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Ba file Java (cùng package `com.example.jsonlogin`):

~~~text
src/main/java/com/example/jsonlogin/
├── JsonLoginApplication.java
├── SecurityConfig.java
└── AuthController.java
~~~

Tạo `JsonLoginApplication.java`:

~~~java
package com.example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
~~~

### 7.2. SecurityConfig.java

~~~java
package com.example.jsonlogin;

import java.util.List;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            SecurityContextRepository contexts,
            CsrfTokenRepository tokens,
            CorsConfigurationSource corsSource) throws Exception {
        http
            .cors(cors -> cors.configurationSource(corsSource))
            .csrf(csrf -> csrf.csrfTokenRepository(tokens))
            .securityContext(sc -> sc.securityContextRepository(contexts))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((req, res, ex) ->
                    res.sendError(HttpServletResponse.SC_UNAUTHORIZED)))
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((req, res, auth) ->
                    res.setStatus(HttpServletResponse.SC_NO_CONTENT)));

        return http.build();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository tokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
            new ChangeSessionIdAuthenticationStrategy(),
            new CsrfAuthenticationStrategy(tokens)
        ));
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);
        return new ProviderManager(dao);
    }
}
~~~

Giải thích các điểm ảnh hưởng đến bảo mật:

1. `csrf(csrf -> csrf.csrfTokenRepository(tokens))` giữ CSRF protection, dùng `HttpSessionCsrfTokenRepository`. `POST /api/login` được `permitAll` nhưng vẫn phải có token.
2. `cors(...configurationSource(...))` làm CORS được xử lý qua Spring Security; origin `localhost:5173` được cho phép rõ ràng cùng credential. Khi deploy, đổi thành **origin HTTPS frontend thật** (không thêm dấu `/` cuối).
3. `securityContextRepository(contexts)` thiết lập nơi Spring Security khôi phục và lưu ngữ cảnh xác thực, để controller login có thể dùng cùng repository khi ghi session.
4. `IF_REQUIRED` cho phép session khi cần. **Không dùng `STATELESS`** cho ví dụ đăng nhập dựa vào session.
5. `formLogin` và `httpBasic` được tắt vì endpoint này tự xử lý login bằng body JSON, không dùng filter login form/Basic. `POST /api/logout` vẫn được `LogoutFilter` xử lý.
6. `SessionAuthenticationStrategy` kết hợp đổi session ID (`ChangeSessionIdAuthenticationStrategy`) với xóa CSRF token cũ sau authentication (`CsrfAuthenticationStrategy`). Vì **controller tự xác thực**, ta phải gọi strategy này; trong cơ chế login filter chuẩn, các bước tương ứng do Spring Security quản lý.
7. `AuthenticationManager` dùng `DaoAuthenticationProvider`, `UserDetailsService` và BCrypt. API constructor/setter của provider thay đổi/deprecate theo nhánh Spring Security 6; dạng setter ở đây tương thích dòng 6.3 của Spring Boot 3.3. Không copy password demo vào môi trường thật.

### 7.3. AuthController.java

~~~java
package com.example.jsonlogin;

import java.security.Principal;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {

    private final AuthenticationManager manager;
    private final SecurityContextRepository contexts;
    private final SessionAuthenticationStrategy sessionStrategy;

    public AuthController(
            AuthenticationManager manager,
            SecurityContextRepository contexts,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.contexts = contexts;
        this.sessionStrategy = sessionStrategy;
    }

    public record LoginRequest(String username, String password) {}

    @GetMapping("/api/csrf")
    public CsrfToken csrf(CsrfToken token) {
        // Truy cập token để cấp cho client; GET không cần đăng nhập.
        return token;
    }

    @PostMapping("/api/login")
    public ResponseEntity<Map<String, String>> login(
            @RequestBody LoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {
        try {
            Authentication authentication = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    input.username(), input.password()));

            sessionStrategy.onAuthentication(authentication, request, response);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);
            contexts.saveContext(context, request, response);

            return ResponseEntity.ok(Map.of(
                "username", authentication.getName()));
        } catch (AuthenticationException ex) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_credentials"));
        }
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

**Vì sao phải `saveContext`?** Từ Spring Security 6, khi tự xác thực trong controller, đặt `Authentication` vào `SecurityContextHolder` chỉ giúp request hiện tại. Muốn request sau có danh tính qua session, phải lưu `SecurityContext` bằng `SecurityContextRepository`. Nếu bỏ bước này, `POST /api/login` có thể báo thành công nhưng `GET /api/me` tiếp theo lại trả 401.

**Vì sao không tự trả `JSESSIONID` trong JSON?** Backend gửi session cookie bằng `Set-Cookie`. JavaScript không cần nhận hoặc lưu ID phiên vào `localStorage`. Đặt ID phiên vào JSON rồi tự gắn header có thể phá mô hình bảo vệ HttpOnly và làm tăng rủi ro lộ session.

**Vì sao không tự xử lý POST logout trong controller?** Cấu hình `logoutUrl("/api/logout")` đưa logout qua `LogoutFilter`, nơi đã có các handler chuẩn để xóa ngữ cảnh và vô hiệu session. Controller chỉ nhận `/api/login` và `/api/csrf`; không tạo endpoint logout thứ hai.

**Giới hạn demo:** Bất cứ hệ thống login thật nào cũng cần policy cho mật khẩu, session, quản lý user, rate limiting, khóa/giãn thử sai, logging an toàn, timeout và exception handling. Ví dụ này minh họa chính xác **CSRF–CORS–cookie**, không phải hệ thống quản lý tài khoản hoàn chỉnh. Mã nguồn Java phụ thuộc Spring Boot/Security nên chạy bằng Gradle, không dùng `javac` thiếu classpath.

### 7.4. Cấu hình cookie cho development và production

Dùng defaults của Spring Boot để thử `localhost`. Khi deploy HTTPS, có thể cấu hình `src/main/resources/application-prod.properties`:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

`lax` phù hợp khi SPA và API **cùng site** (ví dụ `https://app.example.com` → `https://api.example.com`), dù khác origin và vẫn cần CORS. Nếu hai bên **khác site thực sự** và dựa vào cookie cross-site, cần cân nhắc `same-site=none` cùng `secure=true`, kiểm thử browser privacy restrictions và khả năng đặt frontend/backend cùng site. Không dùng cấu hình production cookie `Secure=true` trên HTTP tùy tiện rồi kết luận API không tạo session; browser có thể từ chối/gửi cookie khác nhau theo môi trường.

Trong môi trường reverse proxy, bảo đảm ứng dụng nhận biết HTTPS public đúng cách và proxy không loại bỏ `Set-Cookie`. Không mở rộng `Domain` của session cookie khi chưa có lý do.

## 8. JavaScript fetch: khởi tạo CSRF, đăng nhập, gọi API và logout

Ví dụ chạy từ trang frontend ở `http://localhost:5173`. `fetch` sẽ không tự đưa cookie vào request cross-origin nếu thiếu `credentials: "include"`.

~~~js
const API = "http://localhost:8080";

async function csrfToken() {
  const response = await fetch(API + "/api/csrf", {
    method: "GET",
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot obtain CSRF token");
  return response.json(); // { headerName, parameterName, token }
}

async function login(username, password) {
  const csrf = await csrfToken();
  const response = await fetch(API + "/api/login", {
    method: "POST",
    mode: "cors",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ username, password })
  });
  if (!response.ok) {
    throw new Error("Login failed: HTTP " + response.status);
  }

  const user = await response.json();
  // Authentication đã thay đổi phiên/token; xin token mới cho POST sau.
  await csrfToken();
  return user;
}

async function currentUser() {
  const response = await fetch(API + "/api/me", {
    method: "GET",
    credentials: "include"
  });
  if (!response.ok) {
    throw new Error("Not authenticated: HTTP " + response.status);
  }
  return response.json();
}

async function logout() {
  const csrf = await csrfToken();
  const response = await fetch(API + "/api/logout", {
    method: "POST",
    credentials: "include",
    headers: { [csrf.headerName]: csrf.token }
  });
  if (!response.ok) {
    throw new Error("Logout failed: HTTP " + response.status);
  }
  // Có thể cấp CSRF token mới cho người dùng chưa đăng nhập.
  await csrfToken();
}

// Ví dụ từ UI action thật; không log password vào console.
// const user = await login("alice", "demo-pass");
// const profile = await currentUser();
// await logout();
~~~

Điểm đặc biệt quan trọng:

- `credentials: "include"` phải áp dụng **cả** `GET /api/csrf`, `POST /api/login`, `GET /api/me` và `POST /api/logout` nếu các request qua origin khác nhau; riêng POST có include mà GET /csrf không lưu cookie phiên thì token dễ bị lệch session.
- `Content-Type: application/json` và `X-CSRF-TOKEN` là non-simple request headers, thường kích hoạt preflight; backend phải cho phép chúng.
- `CsrfToken` trả về có `headerName` và `token`; dùng đúng tên/value thay vì hardcode và vô tình mismatch.
- `Set-Cookie` có thể hiện trong DevTools, nhưng JS không đọc được session cookie nếu `HttpOnly`. Việc không đọc được cookie bằng JavaScript là **hành vi bảo vệ**, không chứng cứ login thất bại.
- Không ghi token CSRF, password hay session cookie vào console/log. CSRF token là dữ liệu bảo vệ request; nó không phải password, nhưng không nên để lộ không cần thiết.
- Khi CSRF token hết hạn hoặc session bị hủy, lấy lại token bằng GET và yêu cầu người dùng đăng nhập lại nếu cần. Không tự retry vô hạn POST nhạy cảm.

## 9. Xử lý 401, 403 và “CORS error” đúng nguyên nhân

| Hiện tượng | Nguyên nhân cần kiểm tra | Hành động |
| --- | --- | --- |
| `POST /api/login` trả **403** dù credential đúng | Thiếu/sai CSRF token, token gắn với session khác hoặc đã hết hạn | GET `/api/csrf` với cookie cùng session, gửi lại header đúng; kiểm tra session và CSRF. |
| `POST /api/login` trả **401** | Username/password bị từ chối bởi `AuthenticationManager` | Kiểm tra credential demo, encoder, user status; không lộ chi tiết tài khoản. |
| Login **200** nhưng `GET /api/me` **401** | Cookie không được lưu/gửi, session ID thay đổi, hoặc `SecurityContext` chưa save | Kiểm tra `Set-Cookie`, request `Cookie`, `credentials`, SameSite/Secure, `saveContext`. |
| Browser báo **CORS blocked** | Origin không được phép, thiếu Allow-Headers/Methods/Credentials, preflight bị 401/403 | Xem **Network → OPTIONS** và response headers; xử lý CORS trước auth. |
| `POST /api/logout` trả **403** | Thiếu/CSRF token cũ, hoặc đã logout/session hết hạn | Gọi GET CSRF mới, gửi POST đúng; kiểm tra cookie và phiên. |
| Browser thấy `JSESSIONID` nhưng JS không đọc được | Cookie có `HttpOnly` | Đây là thiết kế đúng; dùng `credentials: "include"`. |
| Localhost chạy, domain production không giữ session | HTTPS, SameSite, third-party cookies, proxy, cookie Domain/Path | Kiểm tra theo origin/site thật trên trình duyệt mục tiêu. |
| `OPTIONS` thành công nhưng POST thất bại | CORS cho phép request, nhưng CSRF/authentication/backend lỗi | Đọc status và log server của **POST**, không coi đây là CORS lỗi. |

**401 và 403 không thay thế nhau.** Với ví dụ, invalid credential trả 401, thiếu CSRF trả 403 từ filter trước controller, và `GET /api/me` chưa đăng nhập trả 401 qua entry point. CORS failure có thể hiện trong console bằng thông báo network mà JS không đọc được response thật; quan sát Network sẽ giúp phân biệt với HTTP 403.

## 10. Tự kiểm thử bằng browser và curl

### 10.1. Chạy backend

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Đảm bảo frontend đang chạy ở `http://localhost:5173` hoặc sửa `setAllowedOrigins(...)` cho đúng origin thực tế.

Mở DevTools → Network, thực hiện login theo thứ tự `/api/csrf` → preflight `OPTIONS` (nếu có) → `POST /api/login` → `/api/csrf` → `GET /api/me`. Kiểm tra:

1. **GET /api/csrf:** trả JSON chứa `token` và có thể tạo `JSESSIONID`. Trong Network/Application, browser thực sự chấp nhận cookie?
2. **OPTIONS /api/login:** preflight được cho phép trước authentication; có `Access-Control-Allow-Origin` chính xác, `Allow-Headers` phù hợp và `Allow-Credentials: true`?
3. **POST /api/login:** có `Origin`, `Content-Type: application/json`, header CSRF và request cookie cần thiết? Response 200 và session sau auth được duy trì?
4. **GET /api/me:** request gửi cookie phiên và trả `{"username":"alice"}`?
5. **POST /api/logout:** token hợp lệ, response 204; sau đó `GET /api/me` với cookie cũ không còn đại diện cho user → 401?

Để phân biệt **CORS** với **CSRF**, thử từ frontend gọi POST mà cố ý bỏ header CSRF: preflight/credential có thể vẫn hợp lệ, nhưng Spring Security sẽ chặn POST bằng 403. Thử sửa `allowedOrigins` sai origin: JavaScript sẽ bị CORS, có thể chặn trước POST. Không dùng cấu hình cố ý sai cho production.

### 10.2. cURL chứng minh CSRF không phải CORS

cURL không bị browser CORS enforcement, nhưng vẫn chịu server-side CSRF. Dùng cookie jar và nội dung token thật:

~~~bash
# Lấy CSRF JSON và lưu cookie vào jar (chỉ dùng tài khoản demo).
curl -i -c cookies.txt http://localhost:8080/api/csrf

# Login với JSON nhưng KHÔNG gửi CSRF token: dự kiến HTTP 403.
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"demo-pass"}' \
  http://localhost:8080/api/login
~~~

Lưu ý lệnh thứ nhất hiển thị token; để login thành công, lấy giá trị trường `token` từ JSON vừa nhận và gắn header `X-CSRF-TOKEN` cùng cookie jar:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: <token-from-previous-json>" \
  -d '{"username":"alice","password":"demo-pass"}' \
  http://localhost:8080/api/login
~~~

Dòng `<token-from-previous-json>` là ký hiệu thay thế, không chạy nguyên xi: hãy thay bằng token thực tế đã nhận. Đây là một lệnh **minh họa thao tác thủ công**, không có output cố định vì token ngẫu nhiên. Khi chạy bằng PowerShell, có thể dùng `curl.exe`; ký tự quote cần đúng theo shell. Không lưu cookie/token/password thật vào file hoặc lịch sử lệnh ngoài môi trường kiểm soát.

Lần GET CSRF sau login sẽ trả token mới nếu token trước đó bị xóa. Muốn kiểm tra phiên, tiếp tục gọi `GET /api/me` với `-b cookies.txt`. Nếu trả 401, kiểm tra cookie jar, session ID, thời hạn phiên và bước `saveContext`.

### 10.3. Ma trận QA tối thiểu

| Case | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| CSRF-01 | POST login không header CSRF | 403, controller login không được gọi. |
| CSRF-02 | Header CSRF đúng nhưng cookie thuộc session khác | 403. |
| LOGIN-01 | POST login có CSRF đúng, password sai | 401, không tạo danh tính đăng nhập. |
| LOGIN-02 | POST login có CSRF đúng, credential demo đúng | 200; session lưu `SecurityContext`. |
| SESSION-01 | GET `/api/me` sau login, gửi cookie phiên | 200, trả user. |
| SESSION-02 | GET `/api/me` không cookie sau login | 401. |
| CORS-01 | Origin `http://localhost:5173` | Preflight/response cho phép origin và credentials. |
| CORS-02 | Origin không có trong allowedOrigins | Browser bị từ chối bởi CORS. |
| LOGOUT-01 | POST logout thiếu CSRF | 403. |
| LOGOUT-02 | POST logout đúng CSRF | 204; session đăng nhập bị vô hiệu. |
| LOGOUT-03 | GET `/api/me` sau logout | 401. |
| COOKIE-01 | Cookie `HttpOnly` | Không đọc ID session qua JavaScript; browser vẫn tự gửi khi được phép. |
| DEPLOY-01 | Frontend/backend production HTTPS | `Secure` và `SameSite` đúng với quan hệ site, login duy trì session. |

## 11. Những sai lầm dễ tạo lỗ hổng hoặc lỗi khó debug

1. **Tắt CSRF bằng `csrf.disable()` chỉ vì request là JSON.** Với session cookie do browser tự gửi, hành vi này có thể mở cửa cho login CSRF, logout CSRF và giả mạo thao tác khác. Chỉ điều chỉnh theo mô hình credential thật đã đánh giá.
2. **Đưa `/api/login` vào `permitAll` rồi tưởng CSRF bị bỏ qua.** `permitAll` thuộc authorization, còn `CsrfFilter` xử lý POST riêng. 403 trước controller không nhất thiết là sai mật khẩu.
3. **Dùng `Access-Control-Allow-Origin: *` cùng credential.** Credentialed CORS cần origin rõ ràng; wildcard không hợp lệ khi `Access-Control-Allow-Credentials: true`.
4. **Không xử lý preflight vì OPTIONS không có cookie.** Preflight vốn không dùng phiên đăng nhập. CORS phải được xử lý trước security auth.
5. **Thiếu `credentials: "include"` ở một trong các request.** Lấy CSRF token bằng session A nhưng POST login tạo session B dễ gây 403; login 200 nhưng me 401 có thể do cookie không tiếp tục được gửi.
6. **Không thay CSRF token sau khi xác thực/logout.** Khi Spring Security xóa token cũ, request POST kế tiếp bị 403 cho tới khi client xin token mới.
7. **Dùng `SameSite=None` mà không `Secure`**, hoặc dùng cấu hình cross-site khi sản phẩm thực ra có thể triển khai cùng site. Browser hiện đại có thể từ chối cookie không phù hợp.
8. **Bật `HttpOnly=false` cho `JSESSIONID` để JavaScript tự đọc.** Không cần; làm tăng bề mặt lộ ID phiên qua XSS. Phân biệt cookie session và cookie CSRF.
9. **Tự nhận JSON login success nhưng quên `SecurityContextRepository.saveContext`.** Request login có thể thành công, request tiếp theo mất xác thực.
10. **Quên chống session fixation khi tự viết login controller.** Spring Security filter mặc định tích hợp xử lý session; tự auth trong controller phải gọi strategy tương ứng, như `ChangeSessionIdAuthenticationStrategy`.
11. **Tin rằng CORS bảo vệ server khỏi mọi nguồn khác.** cURL, server-to-server clients và HTML form đơn giản không chịu quy tắc đọc response của JavaScript CORS giống fetch.
12. **Log nhầm dữ liệu nhạy cảm.** Không ghi plaintext password, cookie session, full `Set-Cookie` hoặc token CSRF vào log/tracing. Bật HTTPS, cookie an toàn, giới hạn số lần login và thông điệp lỗi chung.

## 12. Tổng kết cách thiết kế

Với browser JSON login dựa trên session, hãy giữ chuỗi trách nhiệm rõ ràng:

~~~text
Browser fetch + credentials: include
           |
           +-- CORS kiểm tra nguồn JavaScript có được phép
           |
           +-- Cookie policy quyết định browser có gửi session ID
           |
           +-- CsrfFilter kiểm tra token cho phương thức nguy hiểm
           |
           +-- AuthenticationManager kiểm tra username/password ở login
           |
           +-- SessionAuthenticationStrategy chống session fixation,
           |                           xử lý CSRF token khi auth thành công
           |
           +-- SecurityContextRepository lưu/khôi phục Authentication
           |
           +-- AuthorizationFilter quyết định quyền endpoint
~~~

**Checklist khi thiết kế:** dùng HTTPS; cookie `HttpOnly` và `Secure` phù hợp; `SameSite` theo quan hệ site thực tế; CORS allowlist origin cụ thể, credentials đúng; CSRF bật cho POST login/logout và thao tác đổi dữ liệu; lấy/đổi token đúng vòng đời; lưu SecurityContext và đổi session ID sau login; logout hủy phiên; kiểm tra 401/403/preflight/session qua DevTools.

### Tài liệu tham khảo

- Spring Security Reference — CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security Reference — CORS (Servlet): https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security Reference — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security Reference — Logout: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- MDN — Fetch API credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN — Set-Cookie attributes: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
