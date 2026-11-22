# UsernamePasswordAuthenticationFilter và cách tiếp nhận thông tin đăng nhập

> **Chủ đề:** Spring Security — Servlet stack. **Nhóm:** Đăng nhập biểu mẫu. Ví dụ sử dụng Java 17+, Spring Boot 3.x và Spring Security 6.x.

## 1. Bức tranh tổng thể: nhận credential khác với xác thực credential

Khi người dùng gửi form đăng nhập gồm username và password, Spring Security Servlet cần một thành phần **nhận request HTTP**, lấy dữ liệu theo quy ước, tạo yêu cầu xác thực và chuyển đến hệ thống xác thực. Thành phần thường đảm nhiệm công việc đó trong form login là **`UsernamePasswordAuthenticationFilter`**.

Filter này không tự tra database rồi so sánh password. Nó đóng vai trò "cửa tiếp nhận" (authentication processing filter):

1. Xác định request có phải một lần **thử đăng nhập** mà filter phụ trách hay không.
2. Lấy giá trị username và password từ tham số request; mặc định là `username` và `password`.
3. Tạo đối tượng `UsernamePasswordAuthenticationToken` ở trạng thái **chưa xác thực**.
4. Gửi token vào `AuthenticationManager.authenticate(...)`.
5. Nhận kết quả thành công hoặc `AuthenticationException`, rồi thực hiện nhánh success/failure theo pipeline mà nó kế thừa từ `AbstractAuthenticationProcessingFilter`.

Còn những việc quan trọng khác thuộc thành phần khác:

- `AuthenticationManager` và `AuthenticationProvider`: kiểm tra credential, account status, cấu hình xác thực phù hợp.
- `PasswordEncoder`: so khớp mật khẩu nhận được với mật khẩu **đã băm** trong kho dữ liệu.
- `SecurityContextHolder`/`SecurityContextRepository`: quản lý kết quả xác thực trong request và các request tiếp theo, tùy session policy.
- `AuthenticationSuccessHandler`/`AuthenticationFailureHandler`: tạo redirect hoặc HTTP response sau một lần thử đăng nhập.
- `AuthorizationFilter`: quyết định một request đã tới tài nguyên có được phép truy cập hay không theo quyền và rule.
- `CsrfFilter`: kiểm tra token chống CSRF cho request thuộc diện bảo vệ; có thể chặn POST login **trước** khi filter đăng nhập xử lý.

**Kết luận ngắn:** `UsernamePasswordAuthenticationFilter` đọc *đầu vào của nỗ lực đăng nhập*, không phải một "controller xử lý password" và không phải nơi quy định `ROLE_ADMIN` được phép vào endpoint nào.

## 2. Vị trí trong `SecurityFilterChain` Servlet

Một luồng form login điển hình:

```text
Browser / client
  |
  | POST /login
  | Content-Type: application/x-www-form-urlencoded
  | username=alice&password=(giá trị do người dùng nhập)
  | CSRF token + session cookie (khi áp dụng)
  v
Servlet container
  |
DelegatingFilterProxy ("springSecurityFilterChain")
  |
FilterChainProxy chọn SecurityFilterChain đầu tiên phù hợp
  |
  +--> SecurityContext / CSRF / các filter trước login
  |       |
  |       +--> CSRF không hợp lệ: có thể 403, không chạy login filter
  |
  +--> UsernamePasswordAuthenticationFilter
          |
          +--> RequestMatcher có khớp login-processing URL + method?
          |       | Không -> cho request đi tiếp theo filter chain
          |       | Có
          |       v
          |   Lấy username/password từ request parameters
          |       |
          |   UsernamePasswordAuthenticationToken (unauthenticated)
          |       |
          |   AuthenticationManager
          |       |
          |       +--> AuthenticationProvider (ví dụ DaoAuthenticationProvider)
          |               |
          |               +--> UserDetailsService + PasswordEncoder
          |               +--> kiểm tra credential / account status
          |       |
          |       +--> OK: Authentication đã được xác thực
          |       |         |
          |       |         +--> xử lý session/context/remember-me
          |       |         +--> AuthenticationSuccessHandler
          |       |                  |
          |       |                  +--> redirect hoặc response thành công
          |       |
          |       +--> AuthenticationException
          |                 |
          |                 +--> AuthenticationFailureHandler
          |                          |
          |                          +--> redirect trang login lỗi
          |
          v
    Không nhất thiết đi tới controller POST /login
```

Đây là sơ đồ khái niệm; filter thực tế còn có nhiều thành phần bảo mật khác và thứ tự có thể thay đổi theo cấu hình. Điểm cốt lõi là **request đăng nhập có thể được một Servlet filter xử lý trực tiếp**, hoàn toàn không cần controller `@PostMapping("/login")`.

### Hai lớp matcher phải phân biệt

- `HttpSecurity.securityMatcher(...)` quyết định **cả `SecurityFilterChain`** có được dùng cho request không. Nếu login POST nằm **ngoài** scope chain có `UsernamePasswordAuthenticationFilter`, filter này không thể tiếp nhận request.
- Matcher riêng của `AbstractAuthenticationProcessingFilter` quyết định **request nào trong chain** sẽ kích hoạt nỗ lực xác thực. Với form login mặc định, đó là `POST /login`.
- Quy tắc `authorizeHttpRequests(...requestMatchers(...))` kiểm soát **authorization** khi request đi qua bước đó; nó không thay thế matcher kích hoạt login processing.

Vì thế, chỉ viết `requestMatchers("/login").permitAll()` không có nghĩa đã tạo một cơ chế kiểm tra password. Ngược lại, chỉ cấu hình form login cũng không tự bảo vệ tất cả các URL nếu bạn tạo nhiều filter chain hoặc cố tình bỏ rơi một số đường dẫn.

## 3. Mặc định: HTTP method, URL và tên tham số

Trong cấu hình thông thường bật `formLogin`, bộ lọc `UsernamePasswordAuthenticationFilter` sử dụng các quy ước sau:

| Thành phần | Mặc định/đặc điểm | Vì sao quan trọng |
| --- | --- | --- |
| Login processing URL | `/login` | Đích HTTP để filter thử xác thực |
| HTTP method | `POST` | `GET /login` là xem trang login, **không** phải gửi password để xác thực |
| Username parameter | `username` | Tên field mà `request.getParameter(...)` đọc |
| Password parameter | `password` | Tên field chứa credential |
| Request body web form | Thường là `application/x-www-form-urlencoded` | Servlet container ánh xạ form fields thành request parameters |
| Trang login | Có thể là GET `/login` do Spring Security tự tạo nếu chưa khai báo trang riêng | Không nên nhầm trang HTML với POST handler |
| Success response | Thường redirect tới saved request hoặc trang mặc định | Tùy `AuthenticationSuccessHandler` |
| Failure response | Thường redirect tới `/login?error` | Tùy `AuthenticationFailureHandler` |
| CSRF | Bật mặc định trong cấu hình Servlet web thông dụng | Form POST cần CSRF token hợp lệ khi CSRF áp dụng |

Ví dụ HTTP request dạng form:

```http
POST /login HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

username=alice&password=correct-horse-battery-staple
```

Ví dụ chỉ minh họa **nội dung form**, không phải request hoàn chỉnh để dùng trên một ứng dụng bật CSRF; request thực tế thường phải mang **CSRF token hợp lệ** và cookie/session liên quan. Không sử dụng password ví dụ làm credential thật.

### Vì sao GET /login không được xem là lần xác thực?

GET thường hiển thị HTML form. Filter mặc định chỉ coi POST tới login processing URL là yêu cầu xử lý credential. Nếu đặt username và password trong URL `/login?username=...&password=...`, không những không đúng giao thức form login mặc định mà còn có nguy cơ lộ mật khẩu qua URL, access logs, browser history và referrer.

Không đổi filter sang nhận GET chỉ để "test nhanh". Luôn dùng POST qua HTTPS và cơ chế token/chính sách CSRF phù hợp.

### `/login` là login page và login processing URL khác nhau về vai trò

Trong cấu hình mặc định, GET và POST có thể dùng chung path `/login` nhưng khác method:

```text
GET  /login -> DefaultLoginPageGeneratingFilter có thể tạo HTML login
POST /login -> UsernamePasswordAuthenticationFilter thử authentication
```

Nếu tự làm trang đăng nhập, GET sẽ do MVC/controller/template phục vụ, còn POST có thể tiếp tục do `UsernamePasswordAuthenticationFilter` nhận. **Không cần** tự tạo một `@PostMapping` gọi `AuthenticationManager` nếu `formLogin` đã được cấu hình đúng.

## 4. `attemptAuthentication`: filter thật sự làm gì với tham số?

`UsernamePasswordAuthenticationFilter` kế thừa `AbstractAuthenticationProcessingFilter`. Khi request phù hợp matcher, nó gọi `attemptAuthentication(request, response)` để tạo nỗ lực xác thực.

Đoạn pseudocode Java dưới đây mô tả hành vi chính thường thấy; **đây không phải mã nguồn nguyên văn của tất cả phiên bản Spring Security và không biên dịch độc lập**:

```java
// Pseudocode bên trong UsernamePasswordAuthenticationFilter.
String username = obtainUsername(request);  // request parameter
String password = obtainPassword(request);  // request parameter

if (username == null) {
    username = "";
}
if (password == null) {
    password = "";
}

username = username.trim();                  // chỉ username

UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

setDetails(request, attempt);                // authentication details
return getAuthenticationManager().authenticate(attempt);
```

Một số chi tiết rất đáng nhớ:

- `obtainUsername(...)` đọc tên tham số đã cấu hình qua `getUsernameParameter()`; `obtainPassword(...)` đọc `getPasswordParameter()`.
- Theo hành vi thông dụng, filter **trim username** sau khi đọc; không chủ động trim password. Password là dữ liệu bí mật có thể chứa khoảng trắng có ý nghĩa, không được tự sửa làm người dùng đăng nhập sai.
- Nếu tham số bị thiếu, filter dùng chuỗi rỗng cho nỗ lực xác thực thay vì làm phát sinh một "user session" đặc biệt.
- Token được tạo **chưa được xác thực**. Chỉ `AuthenticationManager` và provider thích hợp mới xác thực credential và trả đối tượng kết quả.
- `setDetails` thường lấy metadata request (ví dụ thông tin kết nối/session thông qua `WebAuthenticationDetailsSource`), **không phải** bước phán quyết username/password hợp lệ.
- Lỗi mật khẩu sai, tài khoản bị khóa, disabled... thuộc authentication provider/account checks; việc gửi message trả người dùng nằm ở failure handler.

### Không tự gắn `authenticated=true` cho client input

Đoạn sau là **sai về ranh giới tin cậy** nếu code tự nhận dữ liệu từ request:

```java
// Không dùng input chưa xác minh để tự khẳng định đã đăng nhập.
String username = request.getParameter("username");
Authentication forged =
    new UsernamePasswordAuthenticationToken(
        username, null, java.util.List.of());
SecurityContextHolder.getContext().setAuthentication(forged);
```

Constructor có danh sách authorities tạo một `UsernamePasswordAuthenticationToken` đánh dấu đã authenticated; đoạn này có thể khiến Spring Security tin một danh tính **chưa từng kiểm tra password**. Cần đưa token chưa xác thực qua `AuthenticationManager` thay vì tự cấy vào `SecurityContext`.

## 5. Khác biệt giữa `UsernamePasswordAuthenticationToken` và `UsernamePasswordAuthenticationFilter`

Hai tên gần giống nhau nhưng đối tượng thực hiện công việc khác:

| Thành phần | Bản chất | Trách nhiệm |
| --- | --- | --- |
| `UsernamePasswordAuthenticationFilter` | Servlet `Filter` chuyên xử lý nỗ lực đăng nhập | Match URL/method, đọc request params, tạo authentication attempt, gọi manager, điều phối kết quả qua parent filter |
| `UsernamePasswordAuthenticationToken` | Implementation của interface `Authentication` | Mang principal/credentials (và authorities khi đã được xác thực) |
| `AuthenticationManager` | API xác thực | Phân phối `authenticate(...)` tới provider |
| `DaoAuthenticationProvider` | Provider cho user/password với `UserDetailsService` | Tải user, kiểm tra account status, so sánh password bằng encoder |
| `UserDetailsService` | API truy xuất thông tin user | Cung cấp `UserDetails`; không tự mã hóa hay so password theo hợp đồng interface |
| `AuthenticationSuccessHandler` | Callback phản hồi thành công | Redirect, saved-request handling hoặc response khác |
| `AuthenticationFailureHandler` | Callback phản hồi thất bại | Redirect/error payload khi authentication attempt thất bại |

Khi debug, ghi rõ bạn đang nói tới **filter nhận request** hay **token mang credential**. Một `UsernamePasswordAuthenticationToken` chưa xác thực không đồng nghĩa với người dùng đăng nhập thành công.

## 6. Thành công và thất bại: lifecycle của parent filter

`AbstractAuthenticationProcessingFilter` quản lý các nhánh sau khi `attemptAuthentication` trả về:

**Thành công (khái quát):**

1. Provider kiểm tra credential và trả một `Authentication` hợp lệ.
2. Session authentication strategy được áp dụng theo cấu hình (ví dụ session fixation protection cho form/session-based login).
3. Framework cập nhật `SecurityContext` và có thể lưu qua `SecurityContextRepository` tương ứng.
4. Remember-me services và authentication event handling được thông báo nếu cấu hình.
5. `AuthenticationSuccessHandler` quyết định redirect hoặc response HTTP.

**Thất bại (khái quát):**

1. Lần thử xác thực phát sinh `AuthenticationException`.
2. Framework làm sạch context thuộc lần xác thực thất bại theo luồng thích hợp.
3. Remember-me service, nếu có, được thông báo lỗi.
4. `AuthenticationFailureHandler` quyết định response/redirect.

Tùy filter/version, các công việc phụ trợ có chi tiết khác; đừng dùng thứ tự minh họa này để tự thay thế toàn bộ cơ chế context/session.

Một biến thể quan trọng: `attemptAuthentication(...)` có thể trả `null` khi cơ chế xác thực cần **tiếp tục qua một bước khác**; khi đó parent filter hiểu rằng quá trình chưa hoàn tất và không chạy nhánh success/failure như trường hợp trả authentication hoặc ném exception. Với form username/password mặc định, nhánh thông thường là được xử lý trong cùng nỗ lực xác thực.

### Khi nào handler không được gọi?

Nếu POST bị `CsrfFilter` chặn vì thiếu token, request **có thể chưa đến** `UsernamePasswordAuthenticationFilter`, nên không có success/failure callback. Nếu gọi sai URL hoặc sai method, matcher của login filter không khớp; request có thể chuyển sang authorization/controller khác và nhận redirect, 403 hoặc 404 tùy cấu hình.

Do đó, status 403 không nhất thiết đồng nghĩa password sai; tương tự status 302 tới `/login` chưa chứng minh đã có một authentication attempt thất bại.

## 7. Cấu hình mặc định và tùy biến bằng `formLogin`

Cách thường dùng là cấu hình DSL trên `HttpSecurity`, **không cần tự đăng ký `UsernamePasswordAuthenticationFilter` bằng tay**:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/account").authenticated()
            .anyRequest().denyAll()
        )
        .formLogin(form -> form.permitAll())
        .build();
}
```

Đây là fragment `SecurityFilterChain`, cần import và bean/configuration thích hợp. Nếu ứng dụng chưa có trang login riêng, Spring Security có thể tạo một trang login mặc định. Khi người dùng submit form, filter xử lý POST theo cấu hình.

### Đổi URL/field names đúng cách

Bạn có thể đổi login processing path và tên field mà filter đọc:

```java
.formLogin(form -> form
    .loginProcessingUrl("/auth/signin")
    .usernameParameter("email")
    .passwordParameter("passcode")
    .defaultSuccessUrl("/profile", false)
    .failureUrl("/login?error")
    .permitAll()
)
```

Đoạn cấu hình trên có ý nghĩa:

- `loginProcessingUrl("/auth/signin")`: filter **xử lý POST `/auth/signin`**; không tự tạo controller business `/auth/signin`.
- `usernameParameter("email")`: filter đọc `request.getParameter("email")`; có thể nhập email làm định danh đăng nhập, nhưng `UserDetailsService` phải tra đúng định danh đó.
- `passwordParameter("passcode")`: filter đọc `request.getParameter("passcode")`; không thay đổi thuật toán `PasswordEncoder`.
- `defaultSuccessUrl("/profile", false)`: dùng `/profile` khi không có saved request ưu tiên; không buộc bỏ saved request.
- `failureUrl("/login?error")`: chuyển về login page với tín hiệu lỗi chung.
- `permitAll()`: cho phép các URL cần thiết cho form login theo cấu hình; không làm toàn bộ ứng dụng public.

Nếu front-end vẫn submit hai field `username`/`password` tới `/auth/signin`, trong khi server đã cấu hình `email`/`passcode`, filter sẽ không nhận được credential theo kỳ vọng, và authentication thường thất bại. Cần kiểm tra **đồng thời 3 thứ: URL, method, tên field**.

### `loginPage` không phải `loginProcessingUrl`

`loginPage("/signin")` chỉ ra URL trang HTML mà browser tới bằng GET (và khi dùng trang tùy biến, bạn phải tự phục vụ trang đó). `loginProcessingUrl("/auth/signin")` chỉ ra URL POST để filter xử lý thông tin đăng nhập. Chúng có thể giống hoặc khác, nhưng không tự thay thế chức năng của nhau.

Khi tự cấu hình `loginPage(...)`, Spring Security **không còn tự tạo trang login đó**. Cần controller/template và bảo đảm route GET trang login, URL submit cùng CSRF đều hợp lệ.

## 8. Ví dụ hoàn chỉnh: Spring Boot 3.x, Java 17+, POST đăng nhập tùy biến

Ví dụ dưới đây tạo một ứng dụng Spring MVC Servlet chạy được với Spring Boot 3.x/Spring Security 6.x. Mục đích là chứng minh:

- Spring Security filter tiếp nhận **POST `/auth/signin`**.
- Hai tham số bắt buộc theo cấu hình là `email` và `passcode`, không phải `username` và `password`.
- `AuthenticationManager` và `UserDetailsService` xác minh account.
- Thành công redirect tới `/profile` khi không có saved request.
- Password sai quay về `/login?error`; GET `/profile` khi anonymous mở đầu luồng login.

Trong Gradle project Spring Boot đã cấu hình plugins và dependency management, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo đúng tệp `src/main/java/example/formfilter/FormFilterApplication.java`:

```java
package example.formfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FormFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormFilterApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/profile")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                // URL kích hoạt UsernamePasswordAuthenticationFilter.
                .loginProcessingUrl("/auth/signin")
                // Tên tham số request mà filter lấy.
                .usernameParameter("email")
                .passwordParameter("passcode")
                // Nếu không có saved request, đi tới /profile.
                .defaultSuccessUrl("/profile", false)
                .failureUrl("/login?error")
                .permitAll()
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }
}

@RestController
class DemoController {

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "Admin only";
    }
}
```

**Giải thích khả năng chạy:** chỉ `FormFilterApplication` là public class; hai top-level class còn lại là package-private, hợp lệ khi cùng nằm trong một tệp Java 17. `@SpringBootApplication` quét package `example.formfilter`, tìm thấy cấu hình security và controller. Ví dụ không viết `@PostMapping("/auth/signin")` vì chính `UsernamePasswordAuthenticationFilter` trong form login xử lý request đó.

**Về username "email":** đổi `usernameParameter("email")` chỉ đổi **tên request field**, không tự áp đặt validation rằng chuỗi phải đúng dạng địa chỉ email. Trong demo, `learner` và `admin` là username được ánh xạ vào field tên `email`. Nếu sản phẩm thật đăng nhập bằng email, `UserDetailsService`/identity directory cần hỗ trợ tra tài khoản theo email, chuẩn hóa và bảo vệ tenant boundary phù hợp.

**Về generated login page:** vì không dùng `.loginPage(...)`, Spring Security có thể tự sinh GET `/login` cho form login trong cấu hình chuẩn. Nếu thay các tên parameter hoặc login processing URL, cần kiểm tra HTML form thực tế để xác nhận action/field names phản ánh cấu hình của bạn. Khi tự tạo giao diện, phải render đúng tên và action.

### Chạy ứng dụng

Trong dự án Gradle Spring Boot với wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell: `./gradlew.bat bootRun`.

Sau khi server chạy local ở `http://localhost:8080`, vào `/profile` bằng browser khi chưa đăng nhập. Kết quả mong đợi là browser được chuyển tới trang đăng nhập. Submit form hợp lệ với field `email=learner` và `passcode=demo-pass`: nếu không có saved request khác, ứng dụng chuyển về `/profile`, controller trả:

```text
Hello learner
```

Nếu trình duyệt trước đó đã cố mở `/admin`, `SavedRequestAwareAuthenticationSuccessHandler` có thể ưu tiên saved request và điều hướng tới `/admin`. Với user thường `learner`, request đó vẫn bị từ chối bởi `hasRole("ADMIN")`. **Đăng nhập thành công không đồng nghĩa có quyền admin**.

Đây là kết quả **dự kiến theo code**, không phải output thu được từ lần chạy thực tế; HTTP `Location` có thể là URL tương đối hoặc tuyệt đối tùy container/proxy/context path.

## 9. Định dạng HTTP thật: form-urlencoded, JSON và các field không khớp

### 9.1. Form-urlencoded là con đường mặc định

Trình duyệt submit `<form method="post">` thông thường theo `application/x-www-form-urlencoded`; Servlet container chuyển từng field thành request parameter và filter sử dụng `request.getParameter(...)`.

Một form minh họa khi bạn tự phục vụ trang HTML:

```html
<form method="post" action="/auth/signin">
  <label for="email">Tài khoản</label>
  <input id="email" name="email" autocomplete="username" required>

  <label for="passcode">Mật khẩu</label>
  <input id="passcode" type="password" name="passcode"
         autocomplete="current-password" required>

  <button type="submit">Đăng nhập</button>
</form>
```

**Cảnh báo:** fragment HTML trên chỉ minh họa `action`/`method`/`name`; **chưa đủ để gửi vào một ứng dụng bật CSRF**. Trang thực phải thêm CSRF hidden input (với parameter name/token do framework cung cấp, kèm session/cookie cần thiết). Nếu dùng Thymeleaf hoặc template engine có tích hợp Spring MVC CSRF, hãy dùng cơ chế render CSRF của framework thay vì tự tạo token từ client. Cũng cần escape đúng dữ liệu khi render các giá trị từ server để ngăn XSS.

Nếu ứng dụng dùng context path khác `/`, không hardcode action dễ làm lệch prefix; dùng URL generation của template/framework tương ứng.

### 9.2. Gửi JSON không tự chuyển thành form login

Request sau có vẻ hợp lý với một JSON API nhưng **không được `UsernamePasswordAuthenticationFilter` mặc định parse như JSON**:

```http
POST /auth/signin HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"email":"learner","passcode":"demo-pass"}
```

Filter mặc định đọc request parameters, không gọi Jackson để deserialize JSON body. Đổi tên field bằng `.usernameParameter(...)` không giải quyết việc parse JSON. Nếu bạn thực sự cần login JSON, hãy thiết kế authentication filter/converter hoặc authentication endpoint chuyên dụng nối đúng với `AuthenticationManager`/security context/session policy, cùng cơ chế chống CSRF và xử lý response tương ứng. Không đọc raw JSON trong controller rồi tự đặt `SecurityContextHolder` thành authenticated mà bỏ qua authentication manager.

### 9.3. Đừng gửi credentials qua query string

Với Servlet `request.getParameter(...)`, tham số có thể được lấy từ query string hoặc form body tùy request/container. **Hãy thiết kế client chỉ gửi credentials trong POST body**; không coi việc filter đọc được parameter là bảo đảm password chỉ đến từ body. URL có credential có thể bị ghi vào logs, reverse proxy, monitoring, browser history và referrer.

Do đó, để đáp ứng chính sách nghiêm ngặt, cần thiết kế request validation, logging/redaction và (nếu cần) kiểm tra Content-Type tại boundary phù hợp. Không tin dữ liệu do client tự tuyên bố (headers, Content-Type, Origin) như bằng chứng đã xác thực.

## 10. CSRF và form login: tại sao thiếu token có thể trả 403?

Form login thường được dùng với browser cookie/session. Browser tự gửi cookie, vì vậy endpoint POST login phải được xem xét trong **CSRF threat model**. Trong Spring Security Servlet chuẩn, CSRF protection được bật mặc định và `CsrfFilter` có thể xử lý trước `UsernamePasswordAuthenticationFilter`.

So sánh:

```text
POST /auth/signin
  method/path/field đều đúng
  password sai
  CSRF hợp lệ
    -> authentication attempt diễn ra
    -> provider ném AuthenticationException
    -> failure handler redirect /login?error

POST /auth/signin
  method/path/field đều đúng
  password đúng
  CSRF thiếu hoặc không hợp lệ
    -> CsrfFilter từ chối (thường HTTP 403)
    -> không tới filter đăng nhập
    -> không gọi failure handler của form login
```

**Vì thế, đừng xóa `http.csrf(...disable...)` chỉ để bài test POST login chạy được.** Với `MockMvc`, Spring Security Test có helper `.with(csrf())`. Với browser, form nên được server render CSRF token và cookie/session nhất quán. Với API dùng bearer token và không dùng credential tự động gắn từ browser, CSRF có thể được thiết kế khác, nhưng phải phân tích cơ chế và khách hàng thực tế trước khi vô hiệu.

Các điểm liên quan nhưng độc lập:

- **HTTPS/TLS:** password phải được truyền qua kênh bảo mật khi triển khai thật; TLS termination ở reverse proxy cần được cấu hình đúng.
- **SameSite/HttpOnly/Secure cookies:** giảm một số rủi ro cho session, nhưng không thay thế toàn bộ CSRF protection.
- **Session fixation:** khi xác thực thành công, session strategy phù hợp có thể đổi session ID; không tự copy session ID vào log/response business.
- **Rate limiting:** bảo vệ trước brute-force, password spraying, credential stuffing ở tầng identity service/filter/gateway.
- **Không ghi password:** không log `request.getParameter("passcode")`, raw form body, `Authentication` hoặc headers chứa credential.

## 11. Kiểm thử thực tế bằng MockMvc

Với ứng dụng ví dụ ở trên, thêm dependency:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo tệp `src/test/java/example/formfilter/FormLoginFilterTest.java`:

```java
package example.formfilter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginFilterTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousOpeningProfileStartsLogin() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void customFieldNamesAreAcceptedByLoginFilter() throws Exception {
        mvc.perform(post("/auth/signin")
                .with(csrf())
                .param("email", "learner")
                .param("passcode", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/profile")));
    }

    @Test
    void wrongPasswordUsesAuthenticationFailureHandler() throws Exception {
        mvc.perform(post("/auth/signin")
                .with(csrf())
                .param("email", "learner")
                .param("passcode", "wrong-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login?error")));
    }

    @Test
    void defaultNamesNoLongerMatchCustomFieldNames() throws Exception {
        mvc.perform(post("/auth/signin")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login?error")));
    }

    @Test
    void missingCsrfTokenIsRejectedBeforePasswordCheck()
            throws Exception {
        mvc.perform(post("/auth/signin")
                .param("email", "learner")
                .param("passcode", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void regularUserCannotUseAdminRole() throws Exception {
        mvc.perform(get("/admin")
                .with(org.springframework.security.test.web.servlet
                    .request.SecurityMockMvcRequestPostProcessors
                    .user("learner").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
```

Chạy test bằng Gradle wrapper:

```bash
./gradlew test
```

Các test là **mã dự kiến** cho project có dependency/version đã nêu, chưa được thực thi trong bài viết này. `MockMvc` cho phép truyền đúng CSRF token để tập trung vào login filter. Test cuối dùng một authenticated principal giả lập với `ROLE_USER` để chứng minh **authorization không đồng nghĩa authentication**; nó không phải thử lại password qua `UsernamePasswordAuthenticationFilter`.

Có thể bổ sung test lưu session sau login, then GET `/profile` bằng cùng cookie/session, và test session fixation riêng. Tránh suy kết luận một lần POST redirect thành công đã chứng minh mọi request sau đó đều còn đăng nhập; session và `SecurityContextRepository` có lifecycle riêng.

## 12. Phân biệt những loại lỗi thường bị đánh đồng

Một tập tình huống giúp chẩn đoán nhanh:

| Request | Filter login có thử xác thực? | Hành vi/điểm kiểm tra |
| --- | --- | --- |
| GET `/login` | Không | Trang login được trả về (mặc định hoặc custom) |
| POST `/auth/signin`, CSRF hợp lệ, field đúng, password đúng | Có | AuthenticationManager → success handler |
| POST `/auth/signin`, CSRF hợp lệ, password sai | Có | AuthenticationException → failure handler |
| POST `/auth/signin`, CSRF không hợp lệ | Thường không | CsrfFilter có thể trả 403 trước |
| POST `/auth/signin`, field tên sai | Có thể có attempt nhưng credential rỗng | Authentication thất bại với cấu hình provider thông thường |
| GET `/auth/signin` | Không theo matcher POST mặc định | Tiếp tục chain; authorization hoặc handler khác quyết định status |
| POST `/other-login` | Không nếu processing URL là `/auth/signin` | Request đi theo filter/authorization khác |
| GET `/profile` khi anonymous | Không | Authorization kích hoạt AuthenticationEntryPoint, thường redirect login |
| GET `/admin` của user đã login nhưng thiếu role | Không | Authorization → access-denied handling, thường 403 |
| POST login JSON body, CSRF hợp lệ | Matcher URL/method có thể khớp, nhưng tham số không được đọc từ JSON | Provider nhận missing/empty fields; không tự parse JSON |

Sự phân biệt này đặc biệt cần thiết khi frontend báo "đăng nhập lỗi" nhưng backend trả 403 hoặc 404: nguyên nhân có thể là **CSRF**, **sai URL**, **sai HTTP method**, **sai tên field**, **sai Content-Type**, **vấn đề chain selection** hoặc **credential thực sự không hợp lệ**.

## 13. Những tùy biến nâng cao và giới hạn cần biết

### 13.1. Khi nào cấu hình `UsernamePasswordAuthenticationFilter` trực tiếp?

Các method của filter như `setUsernameParameter(...)`, `setPasswordParameter(...)`, `setRequiresAuthenticationRequestMatcher(...)`, `setAuthenticationDetailsSource(...)` có thể dùng khi bạn **thực sự quản lý filter instance và vị trí trong chain**. Nhưng với form login Servlet thông thường, DSL `.formLogin(...)` là cách ít rủi ro hơn: Spring Security tự thiết lập manager, handlers, security context và những thành phần liên quan theo configuration.

Nếu tự tạo filter:

- Phải xác định rõ nó được thêm **vào chain nào**, trước/sau filter nào và matcher nào.
- Phải gắn đúng `AuthenticationManager` và cấu hình success/failure behavior.
- Phải bảo đảm xử lý context/session phù hợp Spring Security 6 và cấu hình repository của ứng dụng.
- Không vô tình có **hai login filters** cùng xử lý một URL hoặc che lấp nhau.
- Kiểm tra request method, CSRF, session, logout, logging và test đầy đủ.

Đặc biệt, tự `new UsernamePasswordAuthenticationFilter()` trong một `@Bean` không có nghĩa Servlet `FilterChainProxy` sẽ tự chọn và chạy bean đó theo thứ tự chính xác; phải đăng ký và cấu hình đúng chain.

### 13.2. Login JSON hoặc nhiều cách đăng nhập

Nếu form login truyền thống không phù hợp, có thể dùng một authentication filter có `AuthenticationConverter` riêng hoặc một controller được thiết kế cẩn thận gọi `AuthenticationManager`, rồi quản lý security context, session strategy, CSRF và response theo security contract. Cách chọn phụ thuộc phiên bản Spring Security, kiểu client và nguy cơ bảo mật.

Không nên tùy tiện override `attemptAuthentication` chỉ để lấy JSON rồi copy mã xác thực cũ không còn tương thích. Bất kể chọn filter hay endpoint, ranh giới quan trọng vẫn là **input chưa đáng tin → authentication manager xác minh → auth state được thiết lập đúng chuẩn**.

### 13.3. Nhiều `SecurityFilterChain`

Khi có một chain cho `/api/**` và một chain cho web UI, URL `POST /auth/signin` phải thuộc chain chứa cấu hình `formLogin` tương ứng. Nếu chain chỉ có `securityMatcher("/web/**")` nhưng processing URL đặt ngoài `/web/**`, request sẽ **không đi qua filter login của chain đó**.

Một chain match-all có `@Order` cao hơn chain chuyên biệt cũng có thể che filter login mong muốn. Khi thấy request không vào filter, kiểm tra lựa chọn chain **trước** khi debug username/password.

### 13.4. Forwarded headers và reverse proxy

Nếu ứng dụng sau reverse proxy, URL redirect sau login có thể sai scheme/host/port (ví dụ redirect HTTP dù public request là HTTPS). Đây thường là vấn đề cấu hình trusted forwarded headers, TLS termination và server base URL, **không phải lỗi parser username/password**. Chỉ chấp nhận forwarded headers từ proxy đáng tin, không dùng `X-Forwarded-Host` do client tự tạo để dựng redirect.

### 13.5. Sessionless và form login

Form login truyền thống thường gắn với phiên browser. Nếu cấu hình `SessionCreationPolicy.STATELESS`, request sau login không tự được coi là authenticated từ session như trước; phải thiết kế cơ chế mang credential ở request tiếp theo. Đừng áp cấu hình stateless của resource server vào form login rồi mong server vẫn ghi nhớ trạng thái đăng nhập.

## 14. Checklist chẩn đoán khi "filter không nhận username/password"

Nếu credential không được xử lý đúng, kiểm tra theo thứ tự:

1. **Chain:** request URL có vào đúng `SecurityFilterChain` chứa `formLogin` không?
2. **Method:** request gửi POST, không phải GET?
3. **Processing URL:** action của form đúng với `.loginProcessingUrl(...)` không? Có context path/prefix gateway nào thay đổi URL không?
4. **Input:** tên field đúng với `.usernameParameter(...)` và `.passwordParameter(...)` không? Có gửi body theo form URL encoding không?
5. **CSRF:** token được gửi đúng và có tương ứng cookie/session không? Nếu trả 403, filter nào phát sinh?
6. **Authentication manager/provider:** có provider phù hợp với `UsernamePasswordAuthenticationToken` không?
7. **UserDetailsService:** tra đúng username/email, đúng tenant, trạng thái account và authorities không?
8. **PasswordEncoder:** hash lưu trong database có đúng định dạng/encoder? Không dùng so sánh raw password?
9. **Handlers:** lỗi credential được failure handler xử lý đúng chưa; success handler có redirect tới URL mà user được phép truy cập không?
10. **Session/context:** request sau login có giữ cookie và security context đúng cấu hình? Không lẫn lỗi login với lỗi session persistence?
11. **Logging:** bật debug có kiểm soát để xem filter chain và lý do tổng quát; không dump password/request body/token.
12. **Rate limit/TLS:** bảo vệ endpoint khỏi brute force và bảo đảm credential không đi qua HTTP công khai.

Để tạm bật log trong môi trường development:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Tắt hoặc hạ log level sau khi xử lý xong. Không gửi log chứa thông tin nhạy cảm ra kênh chia sẻ công khai.

## 15. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Tưởng `UsernamePasswordAuthenticationFilter` tự xác minh password | Filter chỉ tiếp nhận request và gọi manager/provider | Phân biệt filter, token, manager, provider, encoder |
| Viết `@PostMapping("/login")` đồng thời bật form login mặc định mà không có chủ đích | Request có thể bị filter giữ trước controller | Chọn một luồng xử lý authentication rõ ràng |
| Dùng GET để gửi password | Credentials có thể lọt vào URL/log; matcher mặc định chỉ POST | Dùng POST body qua HTTPS |
| Đổi UI field thành `email` nhưng server vẫn đòi `username` | `getParameter("username")` không nhận field mới | Đồng bộ `usernameParameter(...)` |
| Đổi `loginProcessingUrl` nhưng form action vẫn là `/login` | Request không khớp filter login đã cấu hình | Đồng bộ action URL và test |
| Gửi JSON nhưng nghĩ filter mặc định parse JSON | `getParameter(...)` không phải JSON parser | Dùng form-urlencoded hoặc authentication converter/filter thích hợp |
| POST login trả 403 mà đổ lỗi password | CSRF filter có thể chặn trước authentication | Kiểm tra CSRF/session, dùng `.with(csrf())` trong MockMvc |
| Đặt trực tiếp `Authentication` authenticated vào context từ form input | Bỏ qua kiểm tra credential, có thể tạo lỗ hổng | Gọi `AuthenticationManager` |
| Nghĩ login success đồng nghĩa có mọi quyền | Authentication và authorization là hai quyết định riêng | Dùng `hasRole`/domain authorization |
| Không có fallback chain cho login path | Filter login không chạy nếu path ngoài chain scope | Thiết kế matcher/chain order đúng |
| Tắt CSRF hoặc session protection cho dễ demo | Có thể làm suy yếu bảo mật browser login | Cấu hình theo threat model và test đúng |
| In raw request parameters để debug | Gây lộ password, cookie, token | Log loại lỗi/status/correlation ID, redact bí mật |
| Gửi exception cụ thể cho người dùng | Có thể tiết lộ account tồn tại/bị khóa | Dùng thông báo lỗi chung và audit nội bộ phù hợp |

## 16. Bài tập thực hành

**Bài 1.** Ứng dụng đặt `loginProcessingUrl("/auth/signin")`, `usernameParameter("email")`, `passwordParameter("passcode")`. Request là POST tới `/auth/signin`, CSRF hợp lệ, nhưng body chứa `username=alice&password=123`. Filter xử lý được credential đúng ý định không?

**Đáp án:** URL/method khớp nên filter có thể thực hiện authentication attempt, nhưng `email` và `passcode` không có trong request parameters; username/password nhận về rỗng. Với provider thông thường, authentication thất bại. Phải sửa frontend fields hoặc cấu hình parameter names.

**Bài 2.** Người dùng gửi POST `/auth/signin` với password chính xác, nhưng không có CSRF token trong một ứng dụng form login cookie/session. Tại sao response có thể là 403 thay vì redirect thành công?

**Đáp án:** `CsrfFilter` kiểm tra CSRF trước, nên request bị từ chối trước khi `UsernamePasswordAuthenticationFilter` gọi authentication manager. Mật khẩu chưa chắc đã được kiểm tra.

**Bài 3.** Tại sao `@PostMapping("/login")` trong controller không được gọi khi form login mặc định đã xử lý cùng POST URL?

**Đáp án:** Authentication filter trong Servlet `FilterChainProxy` nhận request trước Spring MVC dispatcher/controller, thường kết thúc request bằng success/failure redirect.

**Bài 4.** Khi client gửi `Content-Type: application/json` cùng body `{"email":"alice","passcode":"secret"}`, đổi `.usernameParameter("email")` có đủ để filter hiểu JSON không?

**Đáp án:** Không. Filter mặc định đọc servlet request parameters, không deserialize JSON. Cần format form-urlencoded hoặc thiết kế authentication conversion riêng.

**Bài 5.** Sau một lần login thành công, user thường truy cập `GET /admin` nhận 403. Đây là lỗi của `UsernamePasswordAuthenticationFilter` không?

**Đáp án:** Không nhất thiết. Authentication đã thành công, nhưng authorization ở `/admin` cần `ROLE_ADMIN`. Phải kiểm tra rule/authorities thay vì sửa password filter.

**Bài 6.** Trong môi trường có hai chain: web chain scope `/ui/**`, login processing URL là `/auth/signin`, không có chain nào khác bật form login cho URL này. Vì sao request POST không được xác thực?

**Đáp án:** URL login processing nằm **ngoài** scope của web chain nên filter đăng nhập của chain đó không được chạy. Phải chọn URL/chain scope nhất quán hoặc có chain phù hợp cho login.

**Bài 7.** Có nên `trim()` password trong custom filter vì người dùng hay nhập dư dấu cách?

**Đáp án:** Không được mặc nhiên sửa password. Dấu cách có thể là một phần của password hợp lệ. Có thể trim/normalize username theo chính sách thống nhất; password phải được xử lý như chuỗi bí mật mà người dùng đã cung cấp.

## Kết luận

`UsernamePasswordAuthenticationFilter` là thành phần **tiếp nhận nỗ lực đăng nhập form** trong Spring Security Servlet: match request, đọc username/password theo parameter names, tạo `UsernamePasswordAuthenticationToken` chưa xác thực và chuyển tới `AuthenticationManager`. Kết quả được điều phối qua security context/session và success/failure handlers.

Để cấu hình đúng, luôn kiểm tra **chain → POST URL → form field names → CSRF → provider/encoder → handler → session/authorization**. Phần lớn ứng dụng nên dùng `.formLogin(...)` thay vì tự tạo filter; chỉ tùy biến sâu khi đã hiểu lifecycle và có kiểm thử bảo mật tương ứng.
