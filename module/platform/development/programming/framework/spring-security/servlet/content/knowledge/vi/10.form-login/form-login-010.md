# Chống chuyển hướng tới địa chỉ không tin cậy và kiểm thử luồng đăng nhập

> **Bối cảnh:** Spring Security **Servlet**, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài tập trung vào **đăng nhập biểu mẫu (form login)** và hành vi trả `Location`/chuyển hướng sau đăng nhập hoặc thất bại, nhất là khi client tự gửi `next`, `returnUrl`, `redirect`, `destination`. Mục tiêu là ngăn **open redirect** nhưng không phá vỡ luồng đăng nhập, CSRF, session, kiểm tra quyền và điều hướng hợp lệ. Ví dụ Spring dưới đây thuộc một dự án Boot đã có Maven/Gradle và dependencies phù hợp; ví dụ Java 17 cuối bài chạy độc lập.

## 1. Open redirect là gì và vì sao liên quan đến đăng nhập?

**Open redirect** xảy ra khi ứng dụng tạo phản hồi chuyển hướng sang địa chỉ do người dùng không đáng tin điều khiển, mà không giới hạn đích đến bằng chính sách đáng tin. Trình duyệt vẫn đi qua URL của website thật trước khi bị chuyển sang website khác, nên kẻ tấn công có thể mượn uy tín miền của bạn để phục vụ phishing, lừa người dùng hoặc kết hợp các luồng xác thực/ủy quyền khác.

Ví dụ một ứng dụng có endpoint đáng tin:

~~~text
GET https://app.example.test/login?next=https://fake-login.example/collect
                              |
                              v
                    Người dùng đăng nhập đúng
                              |
                              v
HTTP/1.1 302 Found
Location: https://fake-login.example/collect
~~~

Nếu ứng dụng lấy nguyên `next` để làm `Location` thì URL đầu tiên trông thuộc website thật, nhưng đích sau lại nằm ngoài vùng tin cậy. Đây là **ví dụ luồng lỗi**, không phải cách triển khai an toàn.

**Lưu ý bảo mật:** Một open redirect không có nghĩa session cookie của website gốc tự động được gửi tới mọi domain khác. Cookie còn tuân theo domain/path/SameSite và các quy tắc trình duyệt. Rủi ro xác thực nằm ở sự nhầm lẫn nguồn gốc, phishing, chaining với lỗ hổng khác và những thông tin có thể xuất hiện trong URL tùy ứng dụng; không nên khẳng định cứ redirect là tự lộ mọi token.

### Ranh giới tin cậy

- **Tin cậy:** một đường dẫn đã được code ứng dụng định nghĩa, hoặc một khóa điều hướng được **server** ánh xạ tới đường dẫn cho phép.
- **Không tin cậy:** query parameter, form field, cookie do client sửa được, `Referer`, `Host` chưa chuẩn hóa, `X-Forwarded-Host` từ hop chưa được tin cậy, và bất kỳ URL nào đến từ request dù được đặt tên `safeUrl`.
- **Điều kiện cần:** URL trông “cùng domain” hoặc “bắt đầu bằng /” **chưa đủ** để chứng minh an toàn, vì trình duyệt/proxy có thể diễn giải `//host`, dấu gạch chéo ngược, ký tự mã hóa, dấu điều khiển và URL có userinfo khác nhau.

## 2. Bốn kiểu URL thường gặp trong đăng nhập

| Kiểu | Ví dụ | Điều cần cảnh giác |
| --- | --- | --- |
| Đích cố định do server quyết định | `/app` | Tốt nếu ứng dụng kiểm soát route, không sinh nó từ input tùy ý. |
| Đích tương đối cùng ứng dụng | `/orders` | Hợp lý khi nằm trong allowlist; cần xét context path. |
| URL tuyệt đối ngoài site | `https://evil.example/collect` | Không dùng trực tiếp làm redirect sau login. |
| URL scheme-relative | `//evil.example/collect` | Trình duyệt diễn giải là một host ngoài site, **không phải** đường dẫn nội bộ. |

Các ví dụ nguy hiểm không chỉ là `https://evil.example`. Một số giá trị phải bị loại nếu chúng được dùng làm đầu vào đích redirect:

~~~text
//evil.example/path
https://trusted.example.evil.example/path
https://trusted.example@evil.example/path
javascript:alert(1)
/\evil.example
%2F%2Fevil.example
%252F%252Fevil.example
../admin
/orders?next=https://evil.example
\r\nLocation: https://evil.example
~~~

Danh sách trên mô tả **các payload cần thử khi kiểm tra policy**, không khẳng định tất cả web server/trình duyệt sẽ xử lý mọi chuỗi giống nhau. Với ký hiệu `\r\n`, ý là ký tự CR/LF có thể được khai thác nếu code tự nối header; framework HTTP hiện đại thường có cơ chế chặn header injection nhưng không được phụ thuộc vào nó để chấp nhận URL thiếu kiểm soát.

Với tên miền, so chuỗi bằng `startsWith("https://trusted.example")` là sai vì còn khớp `https://trusted.example.evil.example`. So host bằng `endsWith("example.com")` cũng có thể nhận nhầm `notexample.com`. Nếu phải cho phép external origins vì nghiệp vụ, hãy chuẩn hóa URI và kiểm tra **scheme + host chính xác + port + userinfo + redirect policy** theo danh sách phê duyệt; không dùng mẹo nối chuỗi.

## 3. Spring Security quyết định redirect sau form login ở đâu?

Một lần đăng nhập form điển hình:

~~~text
Trình duyệt
    |
    |  POST /login, username/password, CSRF token
    v
FilterChainProxy -> SecurityFilterChain
    |
    v
UsernamePasswordAuthenticationFilter
    |    tạo UsernamePasswordAuthenticationToken chưa xác thực
    |    -> AuthenticationManager / AuthenticationProvider
    |
    +-- thất bại: failure handler, thường /login?error
    |
    +-- thành công:
         cập nhật SecurityContext + session strategy/repository theo cấu hình
         AuthenticationSuccessHandler quyết định response
             -> 302 Location: <đích được phép>
~~~

**AuthenticationSuccessHandler** là điểm mở rộng phù hợp khi ứng dụng muốn định nghĩa chính sách chuyển hướng sau đăng nhập. Nó nhận request, response và `Authentication` đã xác thực; việc xác thực mật khẩu **đã được provider thực hiện** trước khi success handler chạy. Không tự đánh dấu authenticated chỉ để thực hiện redirect.

Các API đáng phân biệt:

- `formLogin(login -> login.defaultSuccessUrl("/app", true))`: đặt **đích cố định** và bật `alwaysUse`, nên không ưu tiên SavedRequest để chọn đích. Phù hợp khi mọi user cần về `/app`.
- `defaultSuccessUrl("/app")` (không truyền `true`): mặc định vẫn có cơ chế **khôi phục request trước đăng nhập** thông qua `SavedRequestAwareAuthenticationSuccessHandler`; đây không phải luôn luôn redirect đúng `/app`.
- `successHandler(customHandler)`: toàn quyền quyết định thành công; khi tự viết phải tự quy định xử lý `RequestCache`, đích đến và response. Đừng mặc định handler tùy biến còn giữ hành vi SavedRequest giống handler cũ.
- `targetUrlParameter`: cơ chế cho phép đọc tên parameter chỉ đích ở một số handler; nếu cấu hình bất cẩn, đây là cổng nhận URL do client điều khiển. Không bật rồi tin nguyên giá trị request.
- `useReferer`: `Referer` có thể không có hoặc không đáng tin. Không sử dụng nó làm nguồn URL redirect không kiểm chứng.
- `failureUrl("/login?error")` và `logoutSuccessUrl("/login?logout")`: nên dùng route cố định hoặc whitelist tương tự. Chính sách redirect không chỉ xuất hiện ở nhánh thành công.

Thư viện Spring Security có nhiều bảo vệ mặc định, nhưng **không được suy ra mọi success handler tùy biến đều an toàn**. Đặc biệt nếu code tự gọi `response.sendRedirect(request.getParameter("next"))`, bạn đang đưa input client thẳng vào quyết định điều hướng.

### SavedRequest là gì?

Nếu user chưa đăng nhập và truy cập `GET /orders`, security entry point có thể lưu một `SavedRequest` trong `RequestCache` rồi dẫn user đến trang login. Sau thành công, handler mặc định dạng `SavedRequestAwareAuthenticationSuccessHandler` có thể điều hướng về request đã lưu.

~~~text
GET /orders (chưa đăng nhập)
  -> /login
  -> POST /login (thành công)
  -> /orders (khôi phục request, nếu policy/handler sử dụng SavedRequest)
~~~

Hành vi khôi phục hữu ích cho UX, nhưng phải nhớ request ban đầu cũng là đầu vào đến từ client. Các ứng dụng dùng reverse proxy, forwarded headers hoặc nhiều host cần tránh tin `Host`/`X-Forwarded-*` chưa được xác thực khi reconstruct URL. Nếu nghiệp vụ cần **chỉ** một vài đích sau login, có thể **bỏ qua SavedRequest** và chuyển hướng đến allowlist nội bộ, như ví dụ ở mục 5.

## 4. Ba chiến lược an toàn theo độ phức tạp

### Cách A — Một đích cố định, ít nhánh nhất

Nếu mọi user được đưa về màn hình chính:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(form -> form
            .defaultSuccessUrl("/app", true)
            .permitAll());
    return http.build();
}
~~~

Đây là **mảnh mã** dành cho class `@Configuration`, cần import `HttpSecurity`, `SecurityFilterChain` và `@Bean`. Vì `true` yêu cầu luôn dùng đích mặc định, handler không tự dùng một parameter `next` để quyết định đích. Ứng dụng cần có handler/controller cho `GET /app`. Thao tác này vẫn giữ **xác thực** và **authorization**; nó chỉ giới hạn **nơi trình duyệt đến sau khi login thành công**.

Khi dùng ứng dụng trong một context path (không phải root), kiểm tra URL cuối cùng và cấu hình `RedirectStrategy`/reverse proxy để tránh gắn prefix sai. Đừng tự nối protocol/host từ header client.

### Cách B — Tùy chọn có giới hạn bằng **khóa điều hướng**

Khi user có thể đến `/app`, `/orders` hoặc `/profile`, hãy nhận một **khóa** như `home`, `orders`, `profile` rồi để code server ánh xạ. Không nhận URL trần:

~~~text
Client: destination=orders
Server: "orders" -> "/orders"

Client: destination=https://evil.example/
Server: không có key này -> "/app"
~~~

Cách này an toàn hơn so với phân tích một chuỗi URL tự do vì quyết định đích được định nghĩa sẵn. Cần chọn key theo yêu cầu ứng dụng, không tạo quá nhiều key khiến whitelist thực tế mất kiểm soát.

### Cách C — URL nội bộ động nhưng có validation mạnh

Chỉ dùng khi thật sự cần. Chẳng hạn app muốn trả user về từng trang đơn hàng, có thể nhận **ID đơn hàng** đã kiểm tra quyền và xây đường dẫn **trên server**:

~~~text
Client: orderId=12345
Server: kiểm tra ID, authenticated user và quyền thấy order 12345
Server: tạo path "/orders/12345" bằng URL builder/escaping chuẩn
~~~

Đừng cho client gửi `returnUrl=/orders/12345?redirect=https://evil.example` rồi chuyển nguyên chuỗi. Kiểm tra authorization với resource ID cũng quan trọng: URL có thể cùng site nhưng trỏ tới tài nguyên user không được phép xem. Nếu dùng opaque state để bảo toàn điểm đến qua nhiều bước login/SSO, state phải được server ký hoặc ràng buộc phiên, thời hạn, nonce và chính sách cho phép; mã hóa Base64 một URL không biến nó thành đáng tin.

**Khuyến nghị cho form login nội bộ:** ưu tiên A khi có một điểm đến, B khi có một số điểm đến được phê duyệt; C cần có lý do nghiệp vụ và bộ kiểm thử/giám sát bổ sung.

## 5. Ví dụ Spring Boot hoàn chỉnh theo cách B: chỉ nhận destination key

Ví dụ dùng **một security chain**, in-memory user dành cho test và hai route nội bộ. Trong production, thay user demo bằng user store và secret policy thực tế; **không** hard-code password. Dependencies: `spring-boot-starter-web`, `spring-boot-starter-security`; kiểm thử dùng `spring-boot-starter-test` và `spring-security-test`.

Giả sử package `com.example.safeformlogin`, Java 17+, các class bên dưới nằm trong package được `@SpringBootApplication` scan. Demo sử dụng form-login mặc định của Spring Security ở `GET /login`. Form tự sinh **không có field destination**; vì vậy trình duyệt bình thường sẽ về `/app`. Để gửi destination từ UI tự tạo, form tùy chỉnh có thể thêm hidden field `destination=orders`, nhưng giá trị ấy vẫn được xem là **không đáng tin** vì client có thể sửa.

### 5.1. `AllowlistedLoginSuccessHandler.java`

~~~java
package com.example.safeformlogin;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.DefaultRedirectStrategy;
import org.springframework.security.web.RedirectStrategy;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;

public final class AllowlistedLoginSuccessHandler
        implements AuthenticationSuccessHandler {

    private static final String DEFAULT_PATH = "/app";

    private static final Map<String, String> ROUTES = Map.of(
            "home", "/app",
            "orders", "/orders",
            "profile", "/profile"
    );

    private final RequestCache requestCache;
    private final RedirectStrategy redirectStrategy =
            new DefaultRedirectStrategy();

    public AllowlistedLoginSuccessHandler(RequestCache requestCache) {
        this.requestCache = requestCache;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) throws IOException {

        String suppliedKey = request.getParameter("destination");

        // Map.of không nhận khóa null: kiểm tra trước.
        String target = suppliedKey == null
                ? DEFAULT_PATH
                : ROUTES.getOrDefault(suppliedKey, DEFAULT_PATH);

        // Chính sách ví dụ: không khôi phục URL SavedRequest.
        // Xóa saved request cũ để không bị dùng trong lần khác.
        requestCache.removeRequest(request, response);

        // Chỉ có các literal path trong ROUTES/DEFAULT_PATH đi đến đây.
        redirectStrategy.sendRedirect(request, response, target);
    }
}
~~~

**Vì sao handler này không open redirect với `destination`?**

- Input từ request được dùng **chỉ** để tra cứu `Map` của server; không được gửi thẳng vào `Location`.
- Những giá trị như `https://evil.example`, `//evil.example`, `%2F%2Fevil.example`, `javascript:...` hoặc chuỗi lạ **không** trùng key hợp lệ ⇒ về `/app`.
- Những giá trị cho phép ánh xạ tới các **path cố định** bắt đầu bằng một dấu `/`, không mang scheme/host của client, không chứa query ngoài ý muốn.
- `RequestCache.removeRequest(...)` thể hiện rõ thiết kế: **không** khôi phục saved URL chưa được duyệt. Nếu ứng dụng muốn khôi phục SavedRequest thì phải xây một policy khác, không bỏ lệnh này rồi mặc nhiên cho rằng đã an toàn.
- `DefaultRedirectStrategy` giúp xử lý redirect của framework; nó không tự biến bất kỳ URL client nào thành an toàn. Đầu vào `target` vẫn phải là đích đã phê duyệt.

**Tính chất đáng chú ý:** Nếu attacker gửi `destination=admin`, nó về `/app` vì `admin` không phải key hợp lệ. Nếu một ngày bạn thêm `"admin" -> "/admin"`, việc thêm route không tự cấp quyền admin: authorization cho `GET /admin` vẫn phải thực hiện ở filter/controller. Hai tầng **redirect policy** và **authorization policy** bổ trợ nhau nhưng không thay thế nhau.

### 5.2. `SecurityConfig.java`

~~~java
package com.example.safeformlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Chỉ cho học tập/test. Không đặt credential thực trong source.
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("training-only"))
                .roles("LEARNER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    RequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    AuthenticationSuccessHandler safeLoginSuccessHandler(
            RequestCache requestCache) {
        return new AllowlistedLoginSuccessHandler(requestCache);
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            AuthenticationSuccessHandler safeLoginSuccessHandler,
            RequestCache requestCache) throws Exception {

        http
            .requestCache(cache -> cache.requestCache(requestCache))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .successHandler(safeLoginSuccessHandler)
                .failureUrl("/login?error")
                .permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"));

        return http.build();
    }
}
~~~

Ở ví dụ này:

1. `formLogin(...)` dùng các filter/login page mặc định, nhưng nhánh **thành công** được giao cho `AllowlistedLoginSuccessHandler`.
2. `.failureUrl("/login?error")` là một đích server cố định cho login sai; không lấy `destination` khi thất bại.
3. `.requestCache(...)` sử dụng cùng một `RequestCache` mà success handler có thể xóa. Mẫu này chủ động không giữ SavedRequest để quyết định đích sau login.
4. `@Bean` cho `UserDetailsService` và `PasswordEncoder` là cơ chế username/password minh họa, không phải bộ phận của chính sách redirect.
5. Endpoint `/admin` có rule `hasRole("ADMIN")` để minh họa **redirect đến một path không đồng nghĩa được quyền truy cập path đó**.
6. POST logout khi bật CSRF phải đáp ứng CSRF token; cấu hình redirect sau logout không thay đổi trách nhiệm bảo vệ CSRF.

Trong ứng dụng thật, có thể còn nhiều `SecurityFilterChain`, login handlers hay reverse proxy; phải kiểm tra đúng chain xử lý `POST /login`. Nếu chain API token match nhầm `/login`, success handler này có thể không chạy.

### 5.3. `PageController.java`

~~~java
package com.example.safeformlogin;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/app")
    public String app() {
        return "app";
    }

    @GetMapping("/orders")
    public String orders() {
        return "orders";
    }

    @GetMapping("/profile")
    public String profile() {
        return "profile";
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
~~~

Nếu cần main class cho dự án demo, tạo:

~~~java
package com.example.safeformlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeFormLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeFormLoginApplication.class, args);
    }
}
~~~

`GET /public` không yêu cầu đăng nhập; `GET /app`, `/orders`, `/profile` yêu cầu authenticated user; `/admin` cần `ROLE_ADMIN` nhưng user demo chỉ có `ROLE_LEARNER`.

### 5.4. Đọc đúng flow

~~~text
GET /orders khi chưa đăng nhập
   -> security yêu cầu authenticated
   -> request có thể được RequestCache lưu
   -> browser chuyển tới /login

POST /login (username=learner, password=training-only, CSRF hợp lệ)
   -> Spring Security xác minh credentials
   -> result đã xác thực, lưu session theo cấu hình
   -> AllowlistedLoginSuccessHandler chạy
   -> destination=orders -> Location: /orders
      destination=https://evil.example -> Location: /app
      không có destination -> Location: /app
   -> xóa SavedRequest vì chính sách này không dùng nó

GET /orders sau login với cookie session hợp lệ
   -> HTTP 200, body "orders"

POST /login password sai
   -> failure handler -> Location: /login?error
   -> KHÔNG gọi success handler cho lần thử sai đó
~~~

Ở form-login mặc định, trang HTML được framework sinh không gửi `destination`, nên đường đi thông thường vẫn là `/app`. Muốn “điểm đến tùy chọn” xuất hiện trong giao diện, phải tự tạo form (với CSRF token đúng) hoặc dùng một entry flow server kiểm soát. Dù UI ẩn field đó, attacker vẫn sửa được form field nên allowlist phải nằm trên server.

**Không cần thay Spring Security để test redirect policy:** `MockMvc` có thể gửi một tham số `destination` bất kỳ trong test. Đây chính là cách mô phỏng client gửi input không đáng tin.

## 6. Kiểm thử HTTP thật với Spring Security Test

Tạo `src/test/java/com/example/safeformlogin/LoginRedirectSecurityTest.java`. Dependencies test: `spring-boot-starter-test`, `spring-security-test`.

~~~java
package com.example.safeformlogin;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class LoginRedirectSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validKeyRedirectsToApprovedOrdersPage() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "training-only")
                    .param("destination", "orders"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/orders"))
                .andExpect(authenticated().withUsername("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/orders").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("orders"));
    }

    @Test
    void missingKeyUsesSafeDefault() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "training-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/app"))
                .andExpect(authenticated().withUsername("learner"));
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "https://evil.example/path",
            "//evil.example/path",
            "https://trusted.example.evil.example/",
            "https://trusted.example@evil.example/",
            "javascript:alert(1)",
            "%2F%2Fevil.example",
            "%252F%252Fevil.example",
            "/\\evil.example",
            "../admin",
            "orders?next=//evil.example",
            "orders/",
            ""
    })
    void unapprovedValueCannotInfluenceRedirect(String supplied)
            throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "training-only")
                    .param("destination", supplied))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/app"))
                .andExpect(authenticated().withUsername("learner"));
    }

    @Test
    void badCredentialsDoNotUseSuccessRedirect() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "learner")
                    .param("password", "incorrect")
                    .param("destination", "orders"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void formLoginRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "learner")
                    .param("password", "training-only")
                    .param("destination", "orders"))
                .andExpect(status().isForbidden());
    }
}
~~~

Các test dùng `post("/login")` thật qua servlet security filter chain, `.with(csrf())` để mô phỏng POST form hợp lệ, thay vì vô hiệu hóa CSRF trong cấu hình. Sau khi xác thực, `redirectedUrl(...)` kiểm tra **đích trả về**, còn `authenticated()` đảm bảo nhánh thành công thực sự có principal được Spring Security xác thực.

Test cuối kiểm tra rằng POST login **không có CSRF token** bị chặn trong cấu hình demo; đây là kiểm tra một lớp bảo vệ khác, độc lập với redirect policy.

**Vì sao test với input xấu vẫn có thể có `authenticated()`?** Vì username/password trong test là đúng. Điều cần bác bỏ là **quyền điều khiển địa chỉ chuyển hướng**, không phải bắt buộc từ chối một người dùng hợp lệ chỉ vì họ gửi field destination không được chấp nhận. Policy ví dụ chọn fallback `/app`. Với nghiệp vụ muốn fail toàn bộ request khi key sai, có thể chọn chính sách báo lỗi rõ ràng, nhưng phải định nghĩa và kiểm thử nhất quán.

**Kiểm tra cả `Location` khi HTTPS/reverse proxy:** ở test root context, `redirectedUrl("/orders")` biểu diễn route nội bộ. Trong deployment có context path, forwarded headers và reverse proxy, assert URL cuối cùng theo cấu hình thực, bao gồm việc chỉ chấp nhận host được tin cậy.

Chạy trong project đã cài dependency test:

~~~bash
./mvnw test
~~~

Windows PowerShell thường chạy `.\mvnw.cmd test`. Output build phụ thuộc tool và môi trường; không gán stdout cố định. Để chạy server demo:

~~~bash
./mvnw spring-boot:run
~~~

Lưu ý trong production không dùng in-memory user `learner/training-only`; mật khẩu trong bài chỉ là dữ liệu test.

## 7. Java 17 độc lập: kiểm tra tính đúng của quyết định điều hướng

Phần logic server-side allowlist có thể được hiểu mà không cần thư viện Spring. Tạo `RedirectPolicyDemo.java`:

~~~java
import java.util.Map;

public final class RedirectPolicyDemo {

    private static final String SAFE_DEFAULT = "/app";

    private static final Map<String, String> DESTINATIONS = Map.of(
            "home", "/app",
            "orders", "/orders",
            "profile", "/profile"
    );

    static String resolve(String key) {
        if (key == null) {
            return SAFE_DEFAULT;
        }
        return DESTINATIONS.getOrDefault(key, SAFE_DEFAULT);
    }

    static void print(String supplied) {
        String display = supplied == null ? "<missing>" : supplied;
        System.out.println(display + " -> " + resolve(supplied));
    }

    public static void main(String[] args) {
        print("orders");
        print("home");
        print("https://evil.example/path");
        print("//evil.example");
        print("%2F%2Fevil.example");
        print(null);
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac RedirectPolicyDemo.java
java RedirectPolicyDemo
~~~

Stdout **chính xác**:

~~~text
orders -> /orders
home -> /app
https://evil.example/path -> /app
//evil.example -> /app
%2F%2Fevil.example -> /app
<missing> -> /app
~~~

Chương trình này **chỉ quyết định path**, không thực hiện HTTP redirect, không cung cấp session, không xác thực mật khẩu và không dùng Spring Security API. Nó minh họa nguyên tắc: client được chọn **một key trong tập server quy định**, chứ không được chọn URL tùy ý. Cùng một bộ mapping có thể test unit độc lập rồi tái sử dụng trong success handler.

## 8. Khi nào cần tự kiểm tra URL nội bộ?

Thỉnh thoảng ứng dụng phải giữ lại một đường dẫn động như `/orders/123?tab=history`. Nếu không dùng khóa điều hướng hoặc ID tạo path từ server, một redirect policy nghiêm ngặt cần kiểm tra **toàn bộ phép diễn giải URL**.

Các điều kiện phổ biến để chỉ cho phép *local path*:

1. Giá trị bắt đầu bằng **một** dấu `/`, không phải `//`.
2. Không có scheme, host, userinfo hoặc port.
3. Không chứa `\`, CR/LF, NUL hay ASCII control.
4. Không chứa path traversal `..` hoặc những biến thể mã hóa có thể tạo ra traversal sau normalize/decode.
5. Xử lý percent encoding nhất quán qua mọi tầng; không kiểm tra một lần rồi để tầng khác decode lần thứ hai dẫn tới `//` hoặc `../`.
6. Bắt buộc route nằm trong danh sách path prefix/route pattern **được định nghĩa chặt**. Đừng dùng `startsWith("/admin")` hay `startsWith("/orders")` thiếu ranh giới segment khi khác nhau về ý nghĩa; `/orders-admin` không phải nhánh `/orders/`.
7. Xử lý query parameter theo schema cho phép. Không tự động cho phép nested `returnUrl` hoặc `redirect` đi tiếp đến một handler khác.
8. Nếu route cần tài nguyên cụ thể, kiểm tra quyền truy cập; redirect policy **không** thay authorization.

Với `java.net.URI`, một bước parse có thể giúp tìm scheme, authority, path và query, nhưng **chỉ parse URI chưa chứng minh an toàn**. Browser và reverse proxy có thể chuẩn hóa input khác nhau, đặc biệt với backslash, percent decoding và Unicode. Vì vậy, các ứng dụng không có yêu cầu URL động nên chọn allowlist *key → literal path*, tránh đưa vào một parser URL tự chế rộng và khó kiểm chứng.

Nếu bắt buộc hỗ trợ external origin đã phê duyệt (ví dụ một số miền của doanh nghiệp), hãy đặt origin chính xác trong cấu hình server, xác minh HTTPS, hostname theo IDNA/canonical form, port, userinfo rỗng, không scheme lạ, path/query cho phép; dùng công cụ/framework chuyên dụng và kiểm thử riêng. Không so string prefix hay tin `Referer`.

### Redirect với query parameter hoặc ID: cách xây an toàn

Thay vì nhận `/orders/123?returnTo=https://evil.example`, hãy nhận `orderId=123`, parse kiểu số/UUID được hỗ trợ, kiểm tra user có quyền xem đơn hàng này, rồi xây:

~~~java
String safePath = "/orders/" + orderId;
redirectStrategy.sendRedirect(request, response, safePath);
~~~

Đây là **mảnh mã minh họa**, không đủ độc lập: `orderId` phải là giá trị đã kiểm tra định dạng và quyền; `redirectStrategy` là thành phần Spring Security có sẵn trong handler. Nếu ID có thể chứa ký tự đặc biệt, phải URL-encode đúng *path segment* bằng URI builder thay vì nối chuỗi raw. Với ID là số nguyên được parse chặt, việc tạo path từ số đã kiểm tra đơn giản hơn và tránh đưa URL client tùy ý vào redirect.

## 9. Cẩn thận với RequestCache, Host header và reverse proxy

Nếu vẫn muốn tính năng “sau login quay lại trang user định mở”:

- `SavedRequestAwareAuthenticationSuccessHandler` và `HttpSessionRequestCache` là các thành phần chuẩn hỗ trợ luồng này.
- Chỉ dùng với URL đã qua chính sách local/same-origin phù hợp deployment, không bất kỳ request URL nào có thể bị kẻ tấn công điều khiển qua proxy/Host headers.
- Một ứng dụng chạy sau proxy cần danh sách host hợp lệ và **trusted proxies** được cấu hình chính xác. Không tin toàn bộ `X-Forwarded-Host`, `Forwarded` do client Internet gửi.
- Nếu app nhận nhiều hostname (admin/internal/public) hoặc context path khác nhau, cần kiểm tra cả authority và nơi URL sẽ được chuyển ở trình duyệt.
- Nếu app có nhiều security chain, phải xác định chain nào lưu/đọc request cache và chain nào xử lý login.
- Nếu policy muốn luôn vào dashboard, dùng `defaultSuccessUrl("/app", true)` hoặc success handler an toàn có `removeRequest` rõ ràng. Đừng vô tình lưu lại `SavedRequest` cũ rồi dùng nó sau này.

**Một test nên bổ sung:** bắt đầu bằng một request chưa xác thực tới `/orders` để tạo saved request, rồi login với một `destination` không hợp lệ. Với chính sách trong mục 5, đích vẫn phải là `/app`; nếu lại chuyển theo một `SavedRequest` chưa được duyệt thì handler hoặc request cache đang sai kỳ vọng. Tình huống này cũng cần test sau session expiration, login retry và nhiều tab.

### Open redirect qua login failure/logout/OAuth2

Không chỉ test `successHandler`:

- Nếu handler thất bại tự nhận `errorRedirect` từ client, hãy áp dụng whitelist tương tự; mặc định dùng URL cố định.
- Nếu logout thành công được cấu hình nhận `postLogoutRedirect`, không để client tự chuyển đến host bất kỳ.
- Với OAuth2/OIDC, `redirect_uri` và post-logout redirect URI thường có quy tắc chặt riêng từ nhà cung cấp danh tính; không biến cơ chế `state`/URL hồi đáp thành open redirect bằng cách nhận URL tùy ý ở app. Đây là chủ đề khác form-login, nhưng cùng một nguyên tắc về nguồn đích đáng tin.
- Nếu app có thư viện router phía frontend tự đọc query `next` để chuyển trang, kiểm tra cả **client-side redirect**, không chỉ header `Location` của Spring Security.

## 10. Những phản ví dụ cần nhận diện trong code review

### Sai: gửi `next` trực tiếp sang Location

~~~java
String next = request.getParameter("next");
response.sendRedirect(next);
~~~

Đây là **phản ví dụ không an toàn**. Nó có thể cho phép URL tuyệt đối ngoài site, network-path reference hoặc biến thể parser khác; không đưa vào code production.

### Sai: chỉ kiểm tra bắt đầu bằng một dấu slash

~~~java
if (next.startsWith("/")) {
    response.sendRedirect(next);
}
~~~

`//evil.example` cũng bắt đầu bằng `/` và có thể được browser coi là URL tới host khác. Đây chỉ là **phản ví dụ**, không phải validation đủ an toàn.

### Sai: chấp nhận bất kỳ chuỗi chứa domain tin cậy

~~~java
if (next.contains("trusted.example")) {
    response.sendRedirect(next);
}
~~~

Một URL có `trusted.example` trong path, userinfo hoặc subdomain giả không có nghĩa host thật được phép. Nên tránh xét domain theo chuỗi; với app chỉ cần nội bộ thì không cần external URL ngay từ đầu.

### Sai: tin header `Referer` để trở lại trang trước

`Referer` có thể bị lược bỏ vì policy, có thể do user agent gửi hoặc do flow/phần mềm khác ảnh hưởng, và bản thân nó có thể trỏ ra ngoài site. Không lấy nguyên `request.getHeader("Referer")` làm `Location` trong handler login.

### Sai: kiểm tra rồi decode lần nữa

Nếu validation nhìn thấy `%2F%2Fevil.example` và cho qua, sau đó code hoặc tầng khác decode thành `//evil.example` rồi redirect, policy bị bypass. Thiết kế có nhiều lần decode/normalize dễ sai; dùng allowlist key tránh lớp lỗi này.

### Sai: bỏ các lớp bảo vệ vì test redirect

Không tắt CSRF chỉ để POST `/login` test chạy. Không chuyển `/admin` sang `permitAll` chỉ để kiểm tra redirect đến đó. Không cho phép password/plaintext trong test production. Một HTTP 302 hợp lệ không chứng minh principal đã được xác thực; test phải assert cả authentication và behavior của endpoint sau đó.

## 11. Kế hoạch kiểm thử đầy đủ trước khi phát hành

| Nhóm test | Dữ liệu vào / kịch bản | Kỳ vọng |
| --- | --- | --- |
| Đích hợp lệ | `destination=orders` | Login đúng, `302 Location: /orders`. |
| Đích còn lại | `home` / `profile` | Chỉ các path đã khai báo. |
| Không có đích | Không có `destination` | Redirect `/app`. |
| URL tuyệt đối ngoài site | `https://evil.example` | Không đi ra site; fallback `/app`. |
| Scheme-relative | `//evil.example` | Không chuyển host ngoài. |
| Userinfo/domain giả | `https://trusted.example@evil.example` | Không được chấp nhận. |
| Mã hóa | `%2F%2F...`, double-encoded, backslash | Không được xem là route hợp lệ. |
| Phân biệt hoa/thường, khoảng trắng | `Orders`, ` orders ` | Không tự mở rộng whitelist nếu chưa định nghĩa policy. |
| Destination rất dài | Chuỗi hàng nghìn ký tự | Không đưa vào Location hoặc log; server có request-size limit thích hợp. |
| Credentials sai | Password sai + `destination=orders` | Nhánh failure cố định, không success redirect. |
| CSRF sai/thiếu | POST login không có CSRF token | Bị chặn theo CSRF policy. |
| Session đăng nhập | Login đúng, rồi GET path đã cho phép | Có principal đúng; GET thành công. |
| Quyền không đủ | Redirect đến path nội bộ cần role khác | Authorization vẫn từ chối, không nhầm redirect với cấp quyền. |
| SavedRequest có sẵn | GET path bảo vệ → login | Hành vi đúng theo policy: hoặc cho khôi phục đã kiểm chứng, hoặc cố định. |
| Logout | Logout thành công | Chỉ dùng route logout-success được cho phép. |
| Proxy/Host | Host/forwarded headers khác giá trị tin cậy | Không để client đổi đích Location sang host bất ngờ. |
| Nhiều security chain | Form chain + API chain | POST login qua đúng chain, không bị handler khác vượt chính sách. |

Một kiểm thử tốt xác nhận **cả** đầu ra HTTP lẫn ý nghĩa security. Ví dụ, response `302` có thể vẫn là open redirect nếu `Location` sai. Ngược lại, `403` không chứng minh redirect policy đúng vì request có thể bị CSRF chặn trước khi chạm tới handler. Kiểm thử nên chủ động xác thực đúng password **và** CSRF để vào success path.

Khi viết thêm property-based/fuzz tests, có thể sinh các chuỗi Unicode, percent encoding, dấu slash, đường dẫn rất dài và dấu điều khiển; tuy vậy phải giới hạn tài nguyên test, tránh ghi input độc hại vào log. Với map key policy, kết quả kỳ vọng rất đơn giản: **mọi key ngoài tập cho phép đều về `/app`**.

## 12. Vấn đề UX và yêu cầu nghiệp vụ

Ngăn open redirect không nhất thiết phải khiến người dùng khó sử dụng:

- Nếu đa số user về một dashboard, dùng URL cố định là đủ và dễ kiểm thử.
- Nếu cần chọn giữa vài màn hình, dùng key server-side như `orders`/`profile`.
- Nếu cần nhớ một route bị chặn trước login, quyết định rõ chính sách SavedRequest: cho phép những route thuộc app, kiểm tra proxy/host đúng, bảo vệ khỏi lưu URL độc hại và test theo deployment thực.
- Nếu có thông báo lỗi, giữ `/login?error` hoặc route lỗi cố định, tránh tiết lộ username có tồn tại hay password sai.
- Nếu web frontend SPA cần điều hướng sau login, server có thể trả **một enum route/key** để frontend map tới route nội bộ; không trả URL client tùy ý.

Có thể dùng UI thân thiện như “Sau đăng nhập, tiếp tục đến trang Đơn hàng” nhưng **nội dung UI không phải biện pháp bảo mật**. Cần enforcement phía server cho mọi request, kể cả curl, browser DevTools hoặc một client tùy chỉnh.

## 13. Checklist rà soát nhanh

- [ ] Tìm mọi nơi sử dụng `sendRedirect(...)`, `RedirectStrategy`, `Location`, `targetUrlParameter`, `SavedRequestAwareAuthenticationSuccessHandler`, `Referer` và các tham số `next/returnUrl/redirect`.
- [ ] Không dùng URL/host từ request trực tiếp làm đích chuyển hướng sau login, failure, logout.
- [ ] Nếu chỉ có một đích, cấu hình `defaultSuccessUrl("/app", true)` hoặc handler tĩnh.
- [ ] Nếu nhiều đích, dùng allowlist **key → literal internal path** phía server.
- [ ] RequestCache được giữ và kiểm chứng theo policy, hoặc được xóa khi không dùng.
- [ ] CSRF vẫn được bật với form login dùng session/cookie khi threat model yêu cầu.
- [ ] Điều kiện authn/authz vẫn được kiểm tra; login success không tự cấp quyền vào mọi trang.
- [ ] Kiểm thử mọi biến thể URL ngoài site, mã hóa, missing/unknown destination, wrong password, CSRF.
- [ ] Kiểm thử context path, forwarded headers và host allowlist khi deploy qua proxy.
- [ ] Không đưa session ID, access token, raw password, hash hoặc dữ liệu nhạy cảm vào redirect URL/log.
- [ ] Có test regression cho mọi handler mới/route mới được thêm sau này.

## 14. Câu hỏi tự ôn tập

**Q1. Vì sao `next=//evil.example` nguy hiểm dù bắt đầu bằng `/`?** Vì `//host/path` là dạng URL có authority (scheme-relative) ở nhiều ngữ cảnh trình duyệt, có thể điều hướng đến host khác. Kiểm tra `startsWith("/")` không đủ.

**Q2. `defaultSuccessUrl("/app", true)` khác phiên bản thiếu `true` như thế nào?** Tham số `true` yêu cầu dùng đích cố định, không ưu tiên SavedRequest. Khi thiếu `true`, handler mặc định có thể khôi phục URL được lưu trước login.

**Q3. Vì sao trong `AuthenticationSuccessHandler` dùng `Map` key tốt hơn gửi nguyên URL?** Vì server quyết định tập đích cuối cùng; input không khớp không tạo host/scheme/path mới.

**Q4. `SavedRequest` có đáng tin hoàn toàn vì Spring Security tạo ra không?** Không. Nó bắt nguồn từ request client và có thể chịu ảnh hưởng của proxy/host/path. Cần chính sách và deployment trust boundary rõ.

**Q5. Login sai nhưng `destination=orders` có nên chuyển user đến `/orders` không?** Không. Nhánh thất bại phải dùng failure handler; ví dụ trả về `/login?error` cố định.

**Q6. Nếu policy redirect chỉ cho `/orders`, user không có quyền xem `/orders` sẽ ra sao?** Redirect có thể vẫn xảy ra, nhưng request `GET /orders` sau đó chịu authorization; whitelist redirect không thay thế kiểm tra quyền.

**Q7. Vì sao test cần `.with(csrf())`?** Để POST form đi qua lớp CSRF hợp lệ và thực sự kiểm tra success handler. Nếu thiếu CSRF, `403` chỉ phản ánh CSRF filter chặn request.

**Q8. `response.sendRedirect(request.getParameter("next"))` có an toàn khi app chỉ chạy HTTPS không?** Không. HTTPS bảo vệ kết nối, không biến URL do client cung cấp thành đích được phép.

**Ghi nhớ:** **Đích chuyển hướng sau đăng nhập là một quyết định bảo mật phía server.** Ưu tiên **URL cố định** hoặc **khóa điều hướng có allowlist**, phân biệt rõ SavedRequest với success handler, giữ CSRF và authorization, rồi kiểm tra cả đầu ra `Location` lẫn trạng thái authenticated trong test tích hợp.
