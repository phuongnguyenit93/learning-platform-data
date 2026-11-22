# Vô hiệu hóa HttpSession và xóa cookie liên quan khi đăng xuất

> **Spring Security - authentication → Đăng xuất.** Bài dùng **Spring Boot 3.x, Spring Security 6.x, Servlet, Java 17+**. Trọng tâm là hai việc phải được phân biệt nhưng phối hợp: **vô hiệu hóa trạng thái đăng nhập phía server (`HttpSession` và `SecurityContext`)**, đồng thời **yêu cầu trình duyệt xóa cookie liên quan** (`JSESSIONID`, remember-me, cookie bổ sung của ứng dụng). Ví dụ dùng form login stateful; phần cuối nêu điểm khác với JWT stateless, OAuth2 và đăng xuất khỏi nhiều thiết bị.

## 1. Logout thành công phải làm gì?

Trong ứng dụng Spring MVC dùng session, sau khi người dùng nhập username/password thành công, Spring Security thường lưu `Authentication` trong `SecurityContext` và lưu context đó qua `SecurityContextRepository`, phổ biến là `HttpSessionSecurityContextRepository`. Trình duyệt giữ một cookie như `JSESSIONID` để tham chiếu session phía server.

Khi nhấn **Đăng xuất**, yêu cầu bảo mật không chỉ là chuyển trình duyệt về `/login`. Một logout đúng cần bảo đảm:

1. Session hiện tại trên server không còn được dùng để lấy lại authentication cũ.
2. `SecurityContextHolder` của request/thread hiện tại và `SecurityContextRepository` tương ứng được làm sạch.
3. Cookie chỉ dẫn tới session cũ được hết hạn hoặc xóa trên browser khi có thể; cookie remember-me và cookie ứng dụng liên quan cần xử lý theo chính sách.
4. Các token/credential **không nằm trong HttpSession** được xử lý riêng: remember-me có thể cần thu hồi, JWT/refresh token có thể có lifecycle khác.
5. Trình duyệt nhận response logout phù hợp; lần truy cập sau tới tài nguyên bảo vệ phải được yêu cầu đăng nhập lại, **trừ khi có credential độc lập còn hợp lệ** được gửi lại.

Bốn đối tượng không phải một:

| Đối tượng | Nằm ở đâu? | Tác động khi logout đúng |
| --- | --- | --- |
| `SecurityContextHolder` | Trong cơ chế giữ context của request/thread | Bỏ authentication hiện tại; tránh còn principal sau logout trong cùng luồng |
| `HttpSession` | Trên servlet container hoặc session store phía server | `invalidate()` làm session hiện tại không thể dùng lại |
| `JSESSIONID` | Trong cookie phía browser | Browser được yêu cầu quên ID (cookie hết hạn); bản thân cookie **không phải** dữ liệu authentication |
| `remember-me` | Cookie nhớ đăng nhập (và có thể token record ở server) | Logout handler xóa cookie; khả năng revoke token đã bị sao chép tùy cơ chế |
| JWT/refresh token | Ở client và/hoặc authorization server | **Không tự bị vô hiệu hóa** bởi `HttpSession.invalidate()` |

**Điểm cốt lõi:** xóa cookie trong browser không phải là hủy trạng thái session phía server; ngược lại, invalidate session phía server không tự bảo đảm mọi cookie đã biến mất khỏi mọi thiết bị hoặc bản sao. Với authentication bảo mật, phía server phải là nơi quyết định session cũ còn hợp lệ hay không.

## 2. Luồng logout chuẩn của Spring Security Servlet

Khi bật Spring Security cho Servlet, `LogoutFilter` xử lý endpoint logout trong filter chain. Với CSRF mặc định đang bật, **`POST /logout` có CSRF token hợp lệ** là yêu cầu thực hiện logout. `GET /logout` thường hiển thị **trang xác nhận** với form POST và CSRF token; GET không phải thao tác xóa session.

```text
Đã login: Browser                         Server
      |                                     |
      | Cookie: JSESSIONID=SESSION_A        |
      | GET /me                             |
      |------------------------------------>|
      |                   SecurityContext từ HttpSession A
      |<------------------------------------| 200 "alice"
      |                                     |
      | POST /logout + CSRF                 |
      | Cookie: JSESSIONID=SESSION_A        |
      |------------------------------------>|
      |                 CsrfFilter xác minh CSRF
      |                 LogoutFilter khớp logout request
      |                   + SecurityContextLogoutHandler
      |                     - invalidate HttpSession A
      |                     - clear SecurityContextHolder
      |                     - clear SecurityContextRepository
      |                   + RememberMeServices LogoutHandler
      |                     - hủy cookie nhớ đăng nhập của browser
      |                   + CsrfLogoutHandler
      |                     - xóa CSRF token đã lưu
      |                   + CookieClearingLogoutHandler (nếu thêm)
      |                     - Set-Cookie cho cookie cần hết hạn
      |                   + LogoutSuccessHandler
      |<------------------------------------| 302 /signed-out
      |                     Set-Cookie: JSESSIONID=; Max-Age=0...
      |                     Set-Cookie: remember-me=; Max-Age=0...
      |
      | GET /me (không có session/cookie hợp lệ)
      |------------------------------------>|
      |<------------------------------------| 302 /login
```

Theo tài liệu Spring Security, chuỗi logout mặc định có `SecurityContextLogoutHandler`, handler của remember-me nếu cấu hình, `CsrfLogoutHandler`, event và `LogoutSuccessHandler`. `SecurityContextLogoutHandler` mặc định **invalidate HttpSession** và làm sạch context. Những hành động cleanup là trách nhiệm của các `LogoutHandler`; redirect hoặc trả mã HTTP do **`LogoutSuccessHandler`** thực hiện sau đó.

### 2.1. Tại sao GET /logout không nên trực tiếp hủy session?

GET thường được xem là safe method và có thể được browser, prefetch, crawler hoặc liên kết bên ngoài kích hoạt. Nếu một GET tự động logout, ứng dụng có nguy cơ **logout CSRF** và trải nghiệm khó đoán. Bật CSRF giúp Spring Security yêu cầu **POST /logout kèm token**; khi gửi `GET /logout`, framework có thể hiển thị form xác nhận để người dùng chủ động thực hiện POST.

Không tắt CSRF toàn cục chỉ vì muốn tạo link `<a href="/logout">Đăng xuất</a>`. Dùng form POST có token, hoặc JavaScript gửi POST có token từ nguồn an toàn. Một request logout bị từ chối do thiếu CSRF không được hủy session.

### 2.2. LogoutFilter và controller khác nhau

`LogoutFilter` nằm trước `AuthorizationFilter` trong chuỗi filter; endpoint logout do DSL cấu hình thường không cần controller MVC riêng. Chỉ cần:

```java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/signed-out")
    .permitAll()
);
```

Nếu cần trang `/signed-out` được render bằng MVC sau redirect, endpoint đó phải được cho phép truy cập công khai. `logout.permitAll()` hỗ trợ đưa các logout URL vào danh sách permit; ví dụ vẫn khai báo `/signed-out` rõ ràng để dễ đọc.

**Không** viết một `@PostMapping("/logout")` tự làm `request.getSession().invalidate()` rồi kết luận đã logout hoàn chỉnh. Một controller có thể bỏ sót context repository, CSRF token, remember-me và cleanup handler. Ưu tiên dùng `logout(...)` để tích hợp với cơ chế framework. Khi thật sự cần custom logout MVC, phải gọi các `LogoutHandler` thích hợp, tối thiểu `SecurityContextLogoutHandler`, và đảm bảo endpoint được phép truy cập. Không tạo session mới chỉ để hủy nó.

## 3. HttpSession.invalidate(), SecurityContext và Session ID

### 3.1. Trạng thái nằm ở server, cookie chỉ tham chiếu

Sau login, giả sử Spring Security lưu context trong session A. Khi browser gửi cookie `JSESSIONID=A`, servlet container dùng ID để tìm session. Tại thời điểm logout:

```java
// Đây là ý tưởng Servlet cơ bản, không phải thay thế toàn bộ
// LogoutFilter/LogoutHandlers của Spring Security.
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
```

`getSession(false)` quan trọng: khi không có session, nó trả `null` thay vì tạo session mới. `invalidate()` làm session không còn hợp lệ; các thuộc tính của session không thể dùng lại sau đó. Spring Security `SecurityContextLogoutHandler` làm điều tương tự (kèm dọn SecurityContext) trong luồng logout.

**Không nhầm với `session.setMaxInactiveInterval(0)`**: đây không phải API chính để kết thúc login hiện tại tức thời theo contract logout. Hãy dùng invalidate/handler chuẩn, không chỉ đổi timeout hoặc ghi đè một thuộc tính session bằng `null`.

### 3.2. Vì sao phải xóa SecurityContext nữa?

Trong Servlet, `SecurityContextHolder` giúp các filter và application code truy xuất `Authentication` cho request hiện tại. Nếu bạn chỉ invalidate session nhưng vẫn giữ một `Authentication` trong holder hoặc một `SecurityContextRepository` tùy biến có trạng thái khác, một request hoặc xử lý nội bộ có thể vẫn nhìn thấy principal đã xác thực.

`SecurityContextLogoutHandler` xử lý làm sạch các nơi này. Ví dụ Spring Security DSL:

```java
.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
);
```

- `invalidateHttpSession(true)`: yêu cầu hủy session hiện tại nếu có. Đây là default của handler chuẩn trong logout.
- `clearAuthentication(true)`: làm sạch authentication/context theo handler. Đây cũng là default trong cấu hình thông thường.
- Handler còn tương tác với `SecurityContextRepository` theo hành vi phiên bản framework. Vì vậy logout không nên bị thay bằng `SecurityContextHolder.clearContext()` đơn lẻ: chỉ xóa thread-local không đồng nghĩa session phía server hết hiệu lực.

Nếu sử dụng repository đặc biệt như Redis-backed session hoặc custom `SecurityContextRepository`, phải kiểm chứng việc xóa/invalidating vẫn tác động đúng backend. Khác biệt thực tế có thể đến từ cách container, session store hoặc filter chain được cấu hình.

### 3.3. Session fixation, rotation và logout

Khi đăng nhập, Spring Security có thể đổi session ID (ví dụ `changeSessionId`) để chống session fixation. Sau logout, ID nào đang thuộc session **hiện tại** phải bị invalidated. Không cố gắng hardcode một ID cũ để xóa cookie.

Ví dụ:

```text
Trước login:       JSESSIONID=GUEST_ID
Sau login:         JSESSIONID=LOGIN_ID   (có thể được rotate)
POST /logout:      invalidates session LOGIN_ID
Lần truy cập sau:  không thể dùng LOGIN_ID để lấy Authentication cũ
```

Việc trả lại trang login hoặc xóa cookie hiển thị trên DevTools **không phải bằng chứng duy nhất**; nên test cả trạng thái `HttpSession` và quyền truy cập sau logout.

### 3.4. Logout một phiên khác logout mọi phiên

`invalidateHttpSession(true)` áp dụng cho **phiên HTTP hiện tại**. Nếu cùng account còn session B trên thiết bị khác, logout session A **không tự hủy B**. Tính năng “đăng xuất tất cả thiết bị” phải được thiết kế riêng: session registry/store phân tán, cơ chế thu hồi phiên, nhớ đăng nhập, access/refresh tokens và các kết nối lâu dài. Không tự suy rằng logout A làm mất mọi phiên khác.

## 4. Xóa cookie: tên cookie thôi chưa đủ

Browser lưu cookie theo các thuộc tính như **Name, Domain và Path**; muốn nó xóa một cookie, response phải đặt cookie có tên/phạm vi tương ứng, với thời hạn đã hết hoặc `Max-Age=0`. Ví dụ minh họa:

```http
HTTP/1.1 302 Found
Location: /signed-out
Set-Cookie: JSESSIONID=; Max-Age=0; Path=/; HttpOnly
Set-Cookie: ui-hint=; Max-Age=0; Path=/
Set-Cookie: remember-me=; Max-Age=0; Path=/; HttpOnly
```

Đây chỉ là **response minh họa**: Servlet container, Spring Security, reverse proxy và cookie config có thể thay đổi số lượng, thứ tự hoặc giá trị thuộc tính `Set-Cookie`.

Một cookie tên `JSESSIONID` được phát với `Path=/app` sẽ **không** bị xóa chỉ bởi lệnh đặt cookie cùng tên với `Path=/`. Nếu cookie có `Domain=.example.com`, việc xóa với cookie host-only khác Domain có thể không đánh trúng bản gốc. Vì thế, kiểm tra **Name/Path/Domain thực tế trên DevTools** và cấu hình xóa sao cho khớp; đặc biệt với nhiều ứng dụng cùng domain, proxy rewrite hoặc deployment dưới context path.

### 4.1. Spring Security hỗ trợ deleteCookies

```java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID", "ui-hint")
);
```

`deleteCookies(...)` thêm `CookieClearingLogoutHandler`, đưa các cookie được nêu vào response với expiry. Trong ví dụ, `ui-hint` là cookie trạng thái UI do **chính ứng dụng** quản lý, cần xóa cùng lúc logout. Không sử dụng wildcard để xóa mọi cookie của domain bằng API này.

**Lưu ý:** tài liệu Spring Security cho biết thường không cần nêu `JSESSIONID`, vì việc invalidate session làm container xử lý nó; tuy nhiên xóa `JSESSIONID` bằng `deleteCookies` cũng **không được đảm bảo tuyệt đối trên mọi Servlet container**. Chỉ cấu hình cookie deletion theo tên không thay thế cho `invalidateHttpSession(true)`. Khi cần bảo đảm hành vi browser, test với target container/proxy, context path và thuộc tính cookie cụ thể.

### 4.2. Cookie remember-me có handler riêng

Nếu bật `rememberMe(...)`, implementation chuẩn `TokenBasedRememberMeServices` hoặc `PersistentTokenBasedRememberMeServices` tích hợp `LogoutHandler` để **xóa remember-me cookie** khi logout. Vì thế trong ví dụ runnable, ta không cần thêm `"remember-me"` vào `deleteCookies(...)` một lần nữa; nếu tự đổi tên/Path/Domain hoặc dùng RememberMeServices custom, phải kiểm tra handler thực sự xóa cookie đang dùng.

Cần phân biệt:

- **Xóa remember-me cookie trên browser:** người dùng bình thường không gửi nó nữa sau logout.
- **Thu hồi một token ở server:** chỉ có nếu cơ chế có trạng thái/lưu token phù hợp và thực hiện revoke. Với remember-me hash-based đơn giản, một **bản cookie đã bị sao chép trước logout có thể vẫn được dùng lại** tới khi hết hạn hoặc mật khẩu/secret thay đổi. `clear cookie` không xóa bản sao ở thiết bị kẻ tấn công.
- **Persistent remember-me:** có token series/token ở repository, hỗ trợ kiểm soát và dọn thông tin theo policy, cần kiểm tra logout/rotation/revoke theo implementation.
- **Remember-me có thể tự đăng nhập lại:** nếu browser vẫn gửi một cookie hợp lệ sau khi session bị xóa, `RememberMeAuthenticationFilter` có thể tạo `RememberMeAuthenticationToken` cho request tiếp theo. Chính vì vậy chỉ xóa `JSESSIONID` thường **không đủ** cho trải nghiệm “đăng xuất hoàn toàn”.

### 4.3. Clear-Site-Data: cách thay thế có tác động rộng

Spring Security hỗ trợ `HeaderWriterLogoutHandler` với `ClearSiteDataHeaderWriter`:

```java
import org.springframework.security.web.authentication.logout.HeaderWriterLogoutHandler;
import org.springframework.security.web.header.writers.ClearSiteDataHeaderWriter;

HeaderWriterLogoutHandler clearCookies =
    new HeaderWriterLogoutHandler(
        new ClearSiteDataHeaderWriter(
            ClearSiteDataHeaderWriter.Directive.COOKIES));

http.logout(logout -> logout
    .addLogoutHandler(clearCookies)
);
```

Header `Clear-Site-Data: "cookies"` hướng dẫn browser xóa cookies thuộc phạm vi site theo quy tắc trình duyệt, phù hợp khi cần xử lý nhiều cookie và giảm sự phụ thuộc vào path cụ thể. Tuy nhiên nó có thể ảnh hưởng **cả ứng dụng khác trên cùng site/domain**, và mức hỗ trợ browser, HTTPS/secure context, proxy cũng cần kiểm tra. Không tự bật `Directive.ALL` (có thể xóa thêm cache/storage) chỉ để giải quyết một cookie, vì tác động UX có thể lớn.

Thực hành nên chọn **đúng phạm vi**: cookie của ứng dụng thì xóa đúng name/path/domain; nếu muốn xóa rộng hơn, ghi rõ lý do, kiểm thử trên các browser mục tiêu và đánh giá ảnh hưởng cross-app. Đừng tưởng `Clear-Site-Data` là phương pháp thu hồi mọi bearer token được lưu trên máy hoặc server của bên thứ ba.

## 5. Ví dụ Spring Boot 3 / Spring Security 6 / Java 17+

Ví dụ gồm login form mặc định, một tài khoản demo, nhớ đăng nhập có opt-in và logout hủy session + dọn cookie. `/me` là endpoint bảo vệ; `/signed-out` là trang công khai xác nhận đã logout. Trong ứng dụng production, thay user store in-memory, remember-me key và chính sách cookie bằng cấu hình an toàn.

### 5.1. Dependencies

Trong ứng dụng có Spring Boot Gradle plugin và Java 17:

```groovy
// build.gradle (phần dependencies)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 5.2. Main

**`src/main/java/example/logoutdemo/LogoutDemoApplication.java`**

```java
package example.logoutdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
```

### 5.3. SecurityConfig

**`src/main/java/example/logoutdemo/SecurityConfig.java`**

```java
package example.logoutdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("study-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            Environment environment) throws Exception {

        String rememberKey =
            environment.getRequiredProperty("app.remember-me.key");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/signed-out").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll())
            .rememberMe(remember -> remember
                .key(rememberKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID", "ui-hint")
                .permitAll());

        // CSRF mặc định BẬT, nên POST /logout cần CSRF token.
        // RememberMeServices được đăng ký như một LogoutHandler.
        return http.build();
    }
}
```

**Giải thích từng dòng liên quan logout:**

1. `.logoutUrl("/logout")` đăng ký endpoint do `LogoutFilter` xử lý. Không cần viết MVC controller POST `/logout`.
2. `.logoutSuccessUrl("/signed-out")` chỉ quyết định redirect sau cleanup. Nó **không** thực hiện cleanup thay `LogoutHandler`.
3. `.invalidateHttpSession(true)` yêu cầu hủy session đang tồn tại. Đây là chính sách stateful, không xóa các session ở thiết bị khác.
4. `.clearAuthentication(true)` cùng handler giúp context hiện tại không còn authentication. Giữ default này để không xảy ra việc cookie đã bị xóa nhưng `SecurityContext` còn được nạp lại.
5. `.deleteCookies("JSESSIONID", "ui-hint")` phát expiry cookies; `JSESSIONID` vẫn cần được server invalidate trước. `ui-hint` minh họa cookie ứng dụng có thể xóa cùng logout, dù nó không chứa credential.
6. `.rememberMe(...)` bật cookie `remember-me` khi login có `remember-me=on`; cơ chế remember-me chuẩn tham gia logout để clear cookie đó. Ví dụ dùng hash-based token cho demo, không có per-token revoke ở server.
7. `.permitAll()` đảm bảo các URL phục vụ logout có thể truy cập theo policy. `/signed-out` được khai báo permit rõ ràng.
8. Không có `.csrf(AbstractHttpConfigurer::disable)`: form login/logout sử dụng cookie nên phải được CSRF bảo vệ.
9. Khóa remember-me không nên nằm trong source production; với nhiều instance phải dùng key nhất quán cho cùng ứng dụng hoặc design token store phù hợp.

### 5.4. Controller

**`src/main/java/example/logoutdemo/AccountController.java`**

```java
package example.logoutdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/signed-out")
    String signedOut() {
        return "signed-out";
    }
}
```

Khi đã login, `GET /me` trả body:

```text
alice
```

Sau logout, `GET /signed-out` trả:

```text
signed-out
```

Đó là **body kỳ vọng** của các endpoint, không phải stdout do tài liệu đã chạy. `GET /me` mà không còn authentication hợp lệ sẽ chuyển về trang login mặc định.

### 5.5. application.yml

**`src/main/resources/application.yml`**

```yaml
app:
  remember-me:
    # Chuỗi chỉ phục vụ local demo; thay bằng secret thật từ môi trường.
    key: local-demo-key-not-for-real-deployments-2026

server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        same-site: lax
```

Đây là cấu hình cho local learning, không phải production secret. Với production HTTPS, bật cookie `Secure`; quản lý Path/Domain của session cookie và remember-me cookie, xác định proxy có rewrite cookie hay không. Nếu dùng `server.servlet.context-path` hoặc một reverse proxy mount app dưới một path khác, kiểm thử cả cookie issuance và deletion thực tế.

## 6. Kiểm thử với MockMvc

Mục tiêu kiểm tra **hai phía**: (A) server đã invalidate session và request sau không còn full authentication; (B) response yêu cầu browser xóa cookie. Test mặc định không thể mô phỏng trọn vẹn cookie jar/Servlet container thật, nên có thêm hướng dẫn browser ở phần 7.

**`src/test/java/example/logoutdemo/LogoutFlowTest.java`**

```java
package example.logoutdemo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutFlowTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        var request = post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "study-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andReturn();
    }

    private MockHttpSession sessionOf(MvcResult result) {
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void successfulLoginCreatesAuthenticatedSession() throws Exception {
        MockHttpSession session = sessionOf(login(false));

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void postLogoutInvalidatesSessionAndExpiresNamedCookies()
            throws Exception {
        MockHttpSession session = sessionOf(login(false));
        assertFalse(session.isInvalid());

        MvcResult result = mvc.perform(post("/logout")
                .with(csrf())
                .session(session)
                .cookie(new Cookie("ui-hint", "expanded")))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"))
            .andReturn();

        assertTrue(session.isInvalid(), "HttpSession A phải bị hủy");

        Cookie jsessionid = result.getResponse().getCookie("JSESSIONID");
        Cookie uiHint = result.getResponse().getCookie("ui-hint");
        assertNotNull(jsessionid);
        assertNotNull(uiHint);
        assertEquals(0, jsessionid.getMaxAge());
        assertEquals(0, uiHint.getMaxAge());

        mvc.perform(get("/signed-out"))
            .andExpect(status().isOk())
            .andExpect(content().string("signed-out"));

        // Request mới không có session/cookie hợp lệ cần login lại.
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void missingCsrfCannotInvalidateSession() throws Exception {
        MockHttpSession session = sessionOf(login(false));

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void getLogoutIsConfirmationNotTheLogoutAction()
            throws Exception {
        MockHttpSession session = sessionOf(login(false));

        mvc.perform(get("/logout").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("form")));

        assertFalse(session.isInvalid());
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void rememberMeCookieIsClearedByItsLogoutHandler()
            throws Exception {
        MvcResult login = login(true);
        MockHttpSession session = sessionOf(login);
        Cookie originallyIssued =
            login.getResponse().getCookie("remember-me");
        assertNotNull(originallyIssued);

        MvcResult logout = mvc.perform(post("/logout")
                .with(csrf())
                .session(session)
                .cookie(originallyIssued))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"))
            .andReturn();

        assertTrue(session.isInvalid());

        Cookie expired =
            logout.getResponse().getCookie("remember-me");
        assertNotNull(expired);
        assertEquals(0, expired.getMaxAge());
    }

    @Test
    void copiedHashBasedRememberCookieCanOutliveBrowserLogout()
            throws Exception {
        MvcResult loggedIn = login(true);
        MockHttpSession session = sessionOf(loggedIn);
        Cookie stolenCopy =
            loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(stolenCopy);

        mvc.perform(post("/logout")
                .with(csrf())
                .session(session))
            .andExpect(status().is3xxRedirection());
        assertTrue(session.isInvalid());

        // Mô phỏng bản copy cookie tồn tại ở client khác.
        // Hash-based remember-me không có per-token server revoke.
        mvc.perform(get("/me").cookie(stolenCopy))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void logoutOneSessionDoesNotInvalidateAnotherSession()
            throws Exception {
        MockHttpSession first = sessionOf(login(false));
        MockHttpSession second = sessionOf(login(false));
        assertNotEquals(first.getId(), second.getId());

        mvc.perform(post("/logout")
                .with(csrf())
                .session(first))
            .andExpect(status().is3xxRedirection());

        assertTrue(first.isInvalid());
        assertFalse(second.isInvalid());

        mvc.perform(get("/me").session(second))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void postLogoutWithoutPriorLoginRemainsSafe()
            throws Exception {
        mvc.perform(post("/logout").with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"));

        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }
}
```

Bộ test có **8 phương thức `@Test`**. Kết quả kỳ vọng:

- Login tạo session đủ để `GET /me` trả `alice`.
- POST logout với CSRF làm `MockHttpSession.isInvalid() == true` và trả cookie `JSESSIONID`/`ui-hint` với `Max-Age=0`.
- POST logout **không** có CSRF bị từ chối, session đã xác thực không bị hủy.
- GET logout tạo trang xác nhận (với CSRF đang bật), không làm mất session.
- Remember-me handler chuẩn làm cookie nhớ đăng nhập hết hạn trong response.
- **Bản sao hash-based remember-me cookie còn hợp lệ có thể được replay** sau logout của trình duyệt ban đầu; đó là lý do phải phân biệt cookie clearing với token revocation.
- Logout một session không mặc định logout session khác của cùng account.
- Logout khi chưa có authentication vẫn hoàn tất an toàn và không tạo user đăng nhập.

Chạy trong root project đã có Gradle wrapper:

```bash
./gradlew test --tests example.logoutdemo.LogoutFlowTest
./gradlew bootRun
```

Với Windows dùng `gradlew.bat`. Đây là mã và các assertion **dự kiến chạy được** trong cấu hình Spring Boot 3.x / Spring Security 6.x, không phải kết quả đã thực thi trong tài liệu. MockMvc là giả lập server-side; nó không mô phỏng toàn bộ cookie jar của browser hoặc sự kiện session timeout thực.

### 6.1. Vì sao test phải kiểm tra session và cookie riêng?

Giả sử app chỉ gửi `Set-Cookie: JSESSIONID=; Max-Age=0` nhưng không `invalidate()`, kẻ có bản sao session ID có thể tiếp tục truy cập cho tới khi session timeout. Ngược lại, nếu session đã bị hủy nhưng browser vẫn giữ cookie cũ, request sau có thể gửi cookie không còn hiệu lực, dẫn tới invalid-session UX hoặc cookie cleanup không nhất quán. Với remember-me còn hợp lệ, người dùng thậm chí có thể tự được đăng nhập lại sau khi session đã bị hủy.

Do đó, test chỉ kiểm tra HTTP 302 sang trang logout **không đủ**. Cần đọc trạng thái session, cookie expiry và request bảo vệ sau logout. Trong end-to-end test, nên gửi lại session ID cũ với cookie jar độc lập tới **container thực** để xác nhận server thật sự từ chối nó; MockMvc không giả lập hoàn toàn ánh xạ cookie ID → session trong container.

## 7. Kiểm thử bằng browser và DevTools

Khi chạy `bootRun`, dùng trình duyệt trên localhost, vào `/login` và đăng nhập `alice` / `study-pass`.

1. **Trước logout:** vào `/me` và xác nhận body `alice`. Trong DevTools → Application/Storage → Cookies, xem tên cookie và thuộc tính Path/Domain, `Secure`, `HttpOnly` và `SameSite`. Không chép giá trị cookie vào ảnh báo lỗi.
2. **Bật remember-me nếu cần test:** đánh dấu remember-me khi đăng nhập. Browser có thể giữ cả `JSESSIONID` và `remember-me`. Quan sát giá trị `Set-Cookie` *ở mức thuộc tính*, không chia sẻ secret.
3. **Thực hiện logout đúng:** truy cập `GET /logout` để xem trang xác nhận rồi gửi POST bằng form. Hoặc dùng form của ứng dụng có trường CSRF và action `/logout`.
4. **Network response logout:** xác minh `302 Location: /signed-out`, các `Set-Cookie` expiry với name/path/domain đúng; `remember-me` bị hủy bởi handler của remember-me nếu được phát.
5. **Sau logout:** `GET /me` phải chuyển đến `/login`, không dùng lại session cũ. Browser Back có thể hiển thị nội dung cache; cần refresh/gọi server để xác nhận authorization, đồng thời cấu hình cache cho dữ liệu nhạy cảm.
6. **Thử CSRF âm tính:** trong môi trường test, gửi POST /logout thiếu token; xác minh `403` và session không bị vô tình hủy. Không vô hiệu hóa CSRF để “sửa”.
7. **Thử cookie path khác:** nếu deploy dưới `/app` hoặc có reverse proxy, đối chiếu `Path` và `Domain` trên cookie phát ra và cookie xóa. Một mismatch có thể để lại cookie; test trên target container thực.
8. **Thử hai session khác nhau:** đăng nhập cùng account trên hai browser profile; logout profile A không nên hủy B nếu ứng dụng chưa có tính năng logout-all. Không dùng hai tab cùng profile để mô phỏng hai session.

Trên môi trường production, cookie session nên là `HttpOnly`/`Secure`, có `SameSite` và Path/Domain phù hợp, website dùng HTTPS. Với ngữ cảnh API khác nguồn (cross-site), chính sách cookie và CSRF cần được thiết kế theo request thực tế, không sao chép nguyên cookie config mẫu.

## 8. Những sai lầm phổ biến

| Sai lầm | Rủi ro/hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ redirect `/login` khi nhấn Logout | Context và session có thể vẫn còn; truy cập `/me` vẫn được | Dùng `LogoutFilter` + `SecurityContextLogoutHandler` |
| Chỉ xóa `JSESSIONID` trong browser | Server vẫn có thể còn session, bản copy ID có thể tái sử dụng | Invalidate session phía server |
| Chỉ gọi `SecurityContextHolder.clearContext()` | Context của session/repository có thể được nạp lại | Dùng logout handler chuẩn và invalidate HttpSession |
| Chỉ gọi `session.invalidate()` trong MVC controller | Có thể bỏ sót context/remember-me/CSRF/logout event | Dùng Spring Security logout DSL hoặc gọi đủ handlers |
| Dùng GET làm thao tác logout | Dễ xảy ra logout CSRF hoặc browser prefetch kích hoạt | POST + CSRF, GET chỉ là trang xác nhận |
| Nghĩ `deleteCookies("JSESSIONID")` luôn hoạt động | Cookie Path/Domain khác, container/proxy khác | Kiểm tra cookie thực; server invalidation vẫn bắt buộc |
| Bỏ xử lý remember-me | Session hết nhưng cookie nhớ đăng nhập tự phục hồi danh tính | Đăng ký logout handler remember-me, kiểm tra replay/revoke |
| Nghĩ xóa remember-me cookie là thu hồi mọi bản sao | Hash-based token copy có thể vẫn hợp lệ tới hạn | Chọn persistent token/revoke policy khi cần |
| Nghĩ logout phiên A sẽ logout mọi thiết bị | Phiên B độc lập không tự bị hủy | Thiết kế session revocation/logout-all riêng |
| Cho rằng invalidate HttpSession sẽ revoke JWT | JWT stateless không dựa vào session đó | Thu hồi refresh token, blacklist/introspection/token TTL theo thiết kế |
| Dùng `Clear-Site-Data: "cookies"` không đánh giá tác động | Có thể xóa cookie của ứng dụng khác cùng site | Kiểm tra scope, browser support, hành vi thật |
| Ghi JSESSIONID hoặc remember-me token vào log | Tạo cơ hội chiếm phiên hoặc replay token | Redact và chỉ audit metadata tối thiểu |
| Test chỉ kiểm tra 302 logout | Không chứng minh server invalidation hay cookie deletion | Assert session invalid + Set-Cookie expiry + request sau |
| Tắt CSRF để test logout bằng Postman | Mở lỗ hổng với browser cookie auth | Giữ CSRF và dùng token hợp lệ trong test |

## 9. Trường hợp đặc biệt: OAuth2, JWT và logout nhiều hệ thống

**JWT stateless Resource Server:** nếu request dùng bearer access token không có `HttpSession`, gọi `invalidateHttpSession(true)` tại ứng dụng **không tự hủy access token** ở mọi nơi. JWT đã ký có thể tiếp tục hợp lệ tới `exp` trừ khi có introspection/revocation/denylist hoặc chính sách của authorization server. Cần phân biệt logout khỏi browser session với OAuth2 token revocation/refresh-token rotation.

**OIDC login:** logout session của ứng dụng chỉ là *local logout*. Nếu muốn logout ở Identity Provider và các ứng dụng khác, dùng cơ chế OIDC logout thích hợp (RP-initiated logout, front/back-channel tùy hỗ trợ) với kiểm tra redirect URI và state. Xóa `JSESSIONID` của app không xóa SSO session cookie ở IdP thuộc domain khác; IdP có thể cho login lại mà không yêu cầu password.

**SAML/CAS:** tương tự, local invalidation không luôn đồng nghĩa single logout. Cần tích hợp giao thức và session mapping đúng. Không gửi cookie của domain khác qua `Set-Cookie` để cố xóa cookie IdP không thuộc quyền sở hữu của ứng dụng.

**Concurrent sessions:** để logout-all, phải biết các session khác của account và invalidating chúng trên session store/registry tương ứng; đồng thời xử lý remember-me và token. Nếu dùng Spring Session Redis/JDBC, kiểm tra propagation tới các node và race conditions, không tuyên bố “đã đăng xuất mọi thiết bị” chỉ dựa trên một POST /logout.

**WebSocket/SSE:** kết nối dài hạn có thể sống lâu hơn request logout. Ứng dụng cần cơ chế đóng/ủy quyền lại các kết nối theo session hoặc user identity, tránh để thông tin nhạy cảm tiếp tục đi qua connection đã mở.

## 10. Checklist QA cuối bài

- [ ] `POST /logout` có CSRF hợp lệ đi vào `LogoutFilter`; `GET /logout` không tự làm mất phiên khi CSRF bật.
- [ ] `SecurityContextLogoutHandler` làm sạch context và invalidate `HttpSession` hiện tại; không tạo session mới chỉ để hủy.
- [ ] `LogoutSuccessHandler` chỉ điều hướng/trả status sau cleanup, không bị coi là thay thế logout handler.
- [ ] Response có `Set-Cookie` expiry cho cookie cần xóa; đã đối chiếu Name/Path/Domain thực tế.
- [ ] `JSESSIONID` bị hủy ở server ngay cả khi browser/proxy không xóa cookie như mong đợi.
- [ ] Remember-me cookie được xóa bởi handler; hiểu rằng một bản sao hash-based token có thể vẫn replay.
- [ ] Test POST không có CSRF bị từ chối và không hủy phiên đang xác thực.
- [ ] Test phiên đã logout không thể truy cập endpoint bảo vệ với session cũ trên Servlet container thật.
- [ ] Logout một session không tự đồng nghĩa logout các session còn lại của account.
- [ ] Mọi secret/cookie/token được bảo vệ, không ghi giá trị vào audit/log hay chia sẻ ảnh chụp.
- [ ] Có test end-to-end với browser/container/proxy và cookie Path/Domain/Secure/SameSite.
- [ ] Nếu dùng JWT, OAuth2/OIDC hoặc SAML, có thiết kế revoke/SSO logout riêng theo giao thức.
- [ ] Dữ liệu nhạy cảm trên browser/back cache và kết nối lâu dài được đánh giá trong quy trình logout.

### Tài liệu chính thức

- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — SecurityContextLogoutHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html)
- [Spring Security 6.5 — CookieClearingLogoutHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/CookieClearingLogoutHandler.html)
- [Spring Security 6.5 — ClearSiteDataHeaderWriter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/header/writers/ClearSiteDataHeaderWriter.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — MockMvc Security Tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
