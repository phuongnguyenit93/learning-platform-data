# CSRF token trong biểu mẫu đăng nhập — Spring Security Servlet

Trong ứng dụng Spring MVC dùng Spring Security, người dùng thường mở trang `GET /login` rồi gửi biểu mẫu `POST /login` với username và password. Một lỗi hiểu nhầm phổ biến là **chưa đăng nhập thì không cần CSRF token**. Trên thực tế, thao tác login thay đổi danh tính gắn với phiên trình duyệt. Nếu bỏ qua CSRF protection, kẻ tấn công có thể tìm cách khiến trình duyệt nạn nhân đăng nhập vào tài khoản do kẻ tấn công kiểm soát — đây là **login CSRF**.

Với **Spring Security 6.x trên Servlet stack**, CSRF protection mặc định áp dụng cho các HTTP method có thể thay đổi trạng thái, bao gồm POST xử lý đăng nhập, trừ khi ứng dụng thay đổi chính sách. Vì vậy, trang login phải phát token hợp lệ và biểu mẫu phải gửi lại token cùng ngữ cảnh trình duyệt; chỉ cung cấp password đúng là chưa đủ.

Bài này dùng Java 17+, Spring Boot 3.3.5, Spring MVC, Spring Security và Thymeleaf. Các API và đường đi được nêu cho trường hợp **login bằng form + HTTP session**. Những ứng dụng SPA, bearer token hoặc nhiều security chain cần đánh giá mô hình chứng thực riêng; không sao chép cấu hình bỏ CSRF chỉ để hết lỗi 403.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **CSRF thông thường**, **login CSRF** và lỗi sai credentials.
2. Giải thích vì sao `permitAll()` ở trang login không hề vô hiệu `CsrfFilter`.
3. Mô tả chu trình `GET form → CSRF token → POST form + session cookie → CsrfFilter → authentication filter`.
4. Nhận biết `CsrfToken`, `CsrfTokenRepository`, `HttpSessionCsrfTokenRepository`, `CsrfTokenRequestHandler` và cơ chế token masking/deferred token của Spring Security 6.
5. Đưa CSRF token vào biểu mẫu bằng Thymeleaf; kiểm tra **HTML kết xuất**, không chỉ mã nguồn template.
6. Viết kiểm thử MockMvc cho các trường hợp không có token, token sai, token đúng nhưng password sai và login thành công.
7. Phân tích session timeout, refresh login, logout, nhiều tab, SPA/cookie và những lỗi 403 thường gặp.

## 2. CSRF thực chất tấn công vào đâu?

**Cross-Site Request Forgery (CSRF)** là tình huống website không đáng tin cố làm trình duyệt gửi một request tới website đích ngoài ý muốn người dùng. Trình duyệt có thể tự gắn thông tin nhận diện/đăng nhập như session cookie cho request đích, tùy cấu hình cookie, SameSite và bối cảnh request.

~~~text
Người dùng đang duyệt trang độc hại
            |
            v
Trang đó tạo/sắp xếp một request POST sang site thật
            |
            v
Browser có thể tự gắn cookie của site thật
            |
            v
Nếu site thật chỉ tin vào cookie và thiếu kiểm soát chống CSRF:
  request thay đổi trạng thái có thể được thực thi trái ý người dùng
~~~

Kẻ tấn công **không nhất thiết đọc được** cookie, password hay response của site thật. Mấu chốt là khả năng làm browser gửi một request không xuất phát từ hành động có chủ đích ở origin đáng tin.

CSRF khác với:

- **XSS:** thực thi JavaScript độc hại trong origin của ứng dụng; XSS có thể làm suy yếu cả CSRF defense nếu script đọc được token hoặc thực hiện request cùng origin.
- **Đoán mật khẩu/credential stuffing:** thử thông tin đăng nhập bị lộ; phòng vệ chính gồm xác thực, rate limiting, MFA, passkeys và phát hiện bất thường.
- **Session fixation:** cố giữ/ấn định một session id trước khi nạn nhân đăng nhập; session fixation protection không thay thế việc chặn CSRF.
- **SQL injection:** nhập dữ liệu để can thiệp câu truy vấn; không liên quan trực tiếp đến việc browser tự đính kèm cookie.

### 2.1. Login CSRF dù nạn nhân chưa đăng nhập

Giả sử attacker sở hữu tài khoản `attacker-user` trên một ứng dụng lưu ghi chú. Attacker cố làm trình duyệt nạn nhân gửi:

~~~text
POST https://notes.example/login
username=attacker-user
password=<mật khẩu của chính attacker>
~~~

Nếu server chấp nhận login POST mà không cần token phòng vệ, nạn nhân có thể bị đăng nhập vào **tài khoản của attacker**. Nạn nhân tiếp tục viết ghi chú mà tưởng chúng được lưu vào tài khoản riêng, trong khi attacker có thể xem dữ liệu thuộc tài khoản do họ sở hữu.

Vì vậy, tác hại của login CSRF **không nhất thiết là attacker chiếm tài khoản của nạn nhân**; nó có thể khiến nạn nhân sử dụng nhầm tài khoản của attacker, dẫn tới rò rỉ hoặc liên kết dữ liệu sai. Ảnh hưởng thực tế phụ thuộc chức năng sản phẩm.

Một form tấn công minh họa về mặt cấu trúc:

~~~html
<!-- Chỉ minh họa threat model, không phải chức năng cần triển khai -->
<form action="https://notes.example/login" method="post">
  <input name="username" value="attacker-user">
  <input name="password" value="attacker-password">
</form>
~~~

Form này **không có CSRF token hợp lệ**. Với policy session-based CSRF đúng, request bị từ chối trước khi server hoàn tất đăng nhập.

### 2.2. Token giải quyết mối đe dọa như thế nào?

Trong mô hình synchronizer token, server tạo token ngẫu nhiên khó đoán và ràng buộc token với trạng thái phiên/client thích hợp. Khi render form, website hợp lệ đưa token vào một hidden field. Website độc hại thuộc origin khác không thể tự ý đọc form/token nếu same-origin policy được thực thi đúng và không có lỗ hổng khác.

Khi browser submit biểu mẫu, server kiểm tra token trong request có khớp dữ liệu tin cậy mà repository lưu không. Token khác phiên, thiếu, bị sửa hoặc không thể phân giải sẽ bị từ chối khi CSRF protection áp dụng.

Token chỉ là một lớp phòng vệ; cần tiếp tục dùng HTTPS, cookie attributes thích hợp, chống XSS, bảo mật session, bảo vệ thông tin xác thực và các lớp xác thực/phân quyền khác.

## 3. Chuỗi request GET /login và POST /login

~~~text
[1] Browser -> GET /login
      |
[2] Server tạo/lấy CsrfToken từ repository khi cần
      |
[3] Spring MVC + Thymeleaf render form có hidden CSRF field
    Browser nhận HTML + session cookie phù hợp
      |
[4] User điền username/password và submit
      |
      v
    POST /login
    Cookie: JSESSIONID=...  (khi app dùng session)
    Content-Type: application/x-www-form-urlencoded
    username=learner&password=...&_csrf=...
      |
      v
[5] CsrfFilter kiểm tra token
      |
      +--- thiếu/sai token -----------------> 403 Forbidden
      |
      +--- token hợp lệ
              |
              v
[6] Form-login authentication filter nhận username/password
              |
              +--- credentials sai --------> failure handler
              |                              (thường 302 /login?error)
              |
              +--- credentials đúng --------> Authentication thành công
                                              -> lưu SecurityContext theo flow
                                              -> success handler (thường redirect)
~~~

Đây là **sơ đồ logic**, không phải bản sao log chính xác của mọi phiên bản. Một số deployment dùng custom entry point, API response JSON hoặc filter khác nên status có thể khác. Nhưng cần giữ rõ hai bước: **CSRF kiểm tra request** và **AuthenticationManager/Provider kiểm tra password**.

### 3.1. Vì sao GET thường không cần token trong request?

Với mặc định của Spring Security, các method được coi là safe (như GET, HEAD, OPTIONS, TRACE) thông thường không cần CSRF token **khi gửi tới server**. Tuy nhiên response của GET /login phải cung cấp token để client **gửi lại trong POST tiếp theo**.

Hai điều này không mâu thuẫn:

- `GET /login` có thể được gọi khi browser chưa có session.
- Trong lúc render trang login, việc truy cập token có thể khiến session được tạo để lưu token theo repository sử dụng session.

Không nên thiết kế thao tác thay đổi phiên, xóa dữ liệu hoặc chuyển trạng thái nghiệp vụ chỉ bằng GET, vì CSRF policy mặc định coi GET là safe.

### 3.2. Vì sao POST /login cần token trước khi người dùng được xác thực?

Trình duyệt có thể có session **trước khi login** chỉ để mang CSRF token. `CsrfFilter` không yêu cầu người dùng đã đăng nhập mới kiểm tra token: nó xét HTTP method/request theo chính sách.

Trong cùng một form, ba trường có bản chất khác nhau:

| Field | Mục đích | Có chứng minh danh tính hay nguồn gốc request không? |
| --- | --- | --- |
| `username` | Danh tính người dùng tự khai | Chưa chứng minh |
| `password` | Credentials mà authentication provider cần kiểm tra | Chỉ được xác nhận sau khi provider kiểm chứng |
| `_csrf` | Token để server kiểm tra request có phù hợp ngữ cảnh CSRF không | Không chứng minh user là ai |

CSRF token **không phải password, access token, JWT hoặc role**. Có token đúng không có nghĩa password đúng. Có password đúng cũng không đủ để một POST vi phạm CSRF policy đi qua.

### 3.3. PermitAll không bỏ qua CsrfFilter

Cấu hình:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login").permitAll()
    .anyRequest().authenticated())
~~~

là đoạn **authorization**, trả lời “request có được phép truy cập URL theo quyền không?”. Nó không nói “bỏ qua tất cả security filters”.

Nếu request POST /login thiếu token, `CsrfFilter` vẫn có thể từ chối **trước** khi authorization đến lượt đánh giá. Khi debug, không chỉ nhìn `permitAll` rồi kết luận CSRF đã bị tắt.

## 4. Các thành phần Spring Security liên quan

| API/Class | Vai trò |
| --- | --- |
| `CsrfFilter` | Kiểm tra token trên các request cần CSRF protection |
| `CsrfToken` | Cung cấp parameter name, header name và token value |
| `CsrfTokenRepository` | Tạo, lưu và tìm token trong trạng thái được chọn |
| `HttpSessionCsrfTokenRepository` | Lưu/lấy CSRF token trong HTTP session |
| `CookieCsrfTokenRepository` | Sử dụng cookie làm nơi mang token theo mô hình thích hợp, thường bàn trong SPA |
| `CsrfTokenRequestHandler` | Quyết định cách expose/resolve token trên request |
| `XorCsrfTokenRequestAttributeHandler` | Request handler có masking để giảm rủi ro liên quan BREACH |
| `CsrfAuthenticationStrategy` | Hỗ trợ làm mới trạng thái CSRF sau sự kiện xác thực theo cơ chế được tích hợp |
| `CsrfLogoutHandler` | Xử lý làm sạch token trong logout flow |
| `UsernamePasswordAuthenticationFilter` | Xử lý username/password khi form login request tới được bước xác thực |
| `SecurityFilterChain` | Tập các filter được framework xây dựng cho request phù hợp |

**Không nên tự tạo một CSRF token cố định rồi gắn vào HTML.** Token cần được sinh và xác minh thông qua repository/handler thống nhất giữa GET form và POST submit.

### 4.1. HttpSessionCsrfTokenRepository

Với server-rendered form login dùng session cookie, repository dựa trên HTTP session là lựa chọn phổ biến. Token được gắn với session thích hợp, browser lưu cookie session và gửi lại khi submit.

Điều kiện thường cần đồng thời:

1. HTML form chứa token server đã render.
2. POST gửi token dưới đúng parameter/header name.
3. Browser gửi cookie phù hợp với session chứa token.
4. Server có thể đọc session nhất quán (quan trọng trong hệ thống nhiều node).

Copy token từ browser A rồi gửi bằng cookie session browser B không được coi là hợp lệ. Tương tự, copy token nhưng bỏ cookie jar trong curl sẽ khiến server không tìm được cùng trạng thái.

### 4.2. Deferred CSRF token trong Spring Security 6.x

Trong các phiên bản Spring Security hiện đại, token có thể được **trì hoãn tạo/lấy** cho đến khi thực sự cần, tránh tạo session vô ích cho các request không dùng CSRF token. Khi HTML form tham chiếu token để render, việc truy cập đó có thể kích hoạt việc tạo/lưu token.

Vì vậy đừng dùng quy tắc “mọi GET đều tạo session”. Hãy quan sát đúng request nào render token và repository nào đang được dùng.

### 4.3. Masking và BREACH

`XorCsrfTokenRequestAttributeHandler` có thể che (mask) giá trị token khi expose ra response, giúp giảm rủi ro lộ token lặp lại trong dữ liệu nén (một phần mô hình phòng vệ BREACH).

Hệ quả:

- Hidden token trong HTML có thể khác với raw token repository đang lưu.
- Token xuất hiện ở hai lần render HTML có thể khác nhau dù underlying token chưa đổi.
- Không kiểm thử rotation bằng cách so hai hidden value rồi kết luận token đã thực sự được tạo mới.
- Với SPA đọc token từ cookie và gửi header, cần cấu hình handler tương thích theo đúng phiên bản; không mặc định giá trị raw luôn được chấp nhận ở mọi chế độ.

Tốt nhất để form login server-rendered học tập là dùng tích hợp chính thức của Spring MVC/Thymeleaf, không tự xử lý raw/masked token.

## 5. Thymeleaf đưa token vào form ra sao?

Một biểu mẫu cơ bản:

~~~html
<form th:action="@{/login}" method="post">
    <label>
        Tài khoản
        <input type="text" name="username" required>
    </label>
    <label>
        Mật khẩu
        <input type="password" name="password" required>
    </label>
    <button type="submit">Đăng nhập</button>
</form>
~~~

Khi template được xử lý bởi **Thymeleaf tích hợp Spring MVC/Spring Security**, cơ chế `RequestDataValueProcessor` thường thêm hidden CSRF input cho form method POST có `th:action`. HTML kết xuất có input về mặt ý nghĩa như:

~~~html
<input type="hidden" name="_csrf" value="server-generated-token">
~~~

`server-generated-token` là ký hiệu mô tả, **không phải token thật**. Người học cần mở Network/Elements hoặc MockMvc để xác nhận HTML cuối cùng có input đó. File template không nhất thiết có sẵn trường hidden trong source.

Nếu template chỉ được phát như **tệp HTML tĩnh** mà không đi qua processor, CSRF input sẽ không tự xuất hiện. Khi đó POST login có thể trả 403. Sửa view integration/form rendering, không tắt CSRF.

### 5.1. Thêm field tường minh khi thật sự cần

Một template đã có request attribute `_csrf` có thể biểu diễn field thủ công:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

Đây là **mảnh code minh họa** cho template có sẵn attribute; không phải HTML thuần chạy độc lập. Không thêm mảnh này bên trong một form đã được `th:action` auto-inject token mà không kiểm tra, vì bạn có thể tạo hai trường trùng `_csrf` gây khó debug.

Các template engine khác, JSP hoặc JavaScript cần truyền token theo cơ chế tương thích với repository và request handler thực tế. Chú ý field name có thể cấu hình; không phải mọi hệ thống đều bắt buộc dùng chuỗi `_csrf`.

### 5.2. Đổi đường dẫn login

Nếu bạn cấu hình:

~~~java
.formLogin(form -> form
    .loginPage("/signin")
    .loginProcessingUrl("/session/login")
    .permitAll())
~~~

thì GET `/signin` render trang, nhưng POST xử lý credentials là `/session/login`. CSRF token phải hiện diện ở **POST xử lý login**, bất kể bạn đặt URL nào. Đừng đồng nhất login page URL với login processing URL khi đã custom.

## 6. Ví dụ chạy được: Java 17 + Spring Boot 3.3.5

Ứng dụng gồm trang đăng nhập, trang profile và form đăng xuất. Spring Security xử lý POST /login và POST /logout; controller chỉ render GET pages. Ví dụ dùng user in-memory `learner / demo-pass` để thử cục bộ.

**Không dùng password hardcoded trong sản phẩm thực.** Ở môi trường production cần nguồn user/secret management, HTTPS, rate limiting, logging an toàn và những biện pháp bảo mật bổ sung.

### 6.1. Cấu trúc tệp

~~~text
login-csrf-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/logincsrf/
    │   │   ├── LoginCsrfApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PageController.java
    │   └── resources/templates/
    │       ├── login.html
    │       └── profile.html
    └── test/java/example/logincsrf/
        └── LoginCsrfTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'login-csrf-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

BOM của Spring Boot lựa chọn các phiên bản Spring Security tương thích. Đừng ép riêng version của một security module nếu các module khác đang được Boot quản lý.

### 6.2. Application

Tệp `src/main/java/example/logincsrf/LoginCsrfApplication.java`:

~~~java
package example.logincsrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginCsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginCsrfApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfiguration

Tệp `src/main/java/example/logincsrf/SecurityConfiguration.java`:

~~~java
package example.logincsrf;

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

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .anyRequest().authenticated())

            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/profile", true)
                .permitAll())

            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"))

            // Giữ CSRF protection mặc định: không gọi disable().
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

Giải thích:

- `requestMatchers("/login").permitAll()` cho phép người chưa đăng nhập xem form. Đây **chỉ** là authorization.
- `formLogin().loginPage("/login")` cấu hình form page, còn POST /login do login filter xử lý.
- `defaultSuccessUrl("/profile", true)` chuyển hướng sau login thành công.
- `logoutSuccessUrl("/login?logout")` chuyển hướng sau logout.
- Không gọi `csrf(csrf -> csrf.disable())`, nên POST /login và POST /logout vẫn phải thỏa CSRF protection mặc định.
- Password encoder chịu trách nhiệm xác thực secret sau khi CSRF đã cho POST đi qua; nó không thay thế token.

### 6.4. Controller

Tệp `src/main/java/example/logincsrf/PageController.java`:

~~~java
package example.logincsrf;

import java.security.Principal;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/profile")
    public String profile(Principal principal, Model model) {
        model.addAttribute("username", principal.getName());
        return "profile";
    }
}
~~~

Không thêm `@PostMapping("/login")` để tự so sánh password. Form-login filter của Spring Security chặn request và xử lý trước controller theo cấu hình đang dùng.

### 6.5. login.html

Tệp `src/main/resources/templates/login.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>
    <p th:if="${param.error}">Tài khoản hoặc mật khẩu sai.</p>
    <p th:if="${param.logout}">Đã đăng xuất.</p>
    <form th:action="@{/login}" method="post">
        <label>Tài khoản
            <input type="text" name="username"
                   autocomplete="username" required>
        </label>
        <label>Mật khẩu
            <input type="password" name="password"
                   autocomplete="current-password" required>
        </label>
        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
~~~

Thymeleaf xử lý `th:action` và thường tự thêm hidden CSRF field nhờ tích hợp Spring MVC. Đừng chỉnh template chỉ để tạo token có giá trị cố định.

### 6.6. profile.html

Tệp `src/main/resources/templates/profile.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang cá nhân</title>
</head>
<body>
    <h1>Trang cá nhân</h1>
    <p>Xin chào, <span th:text="${username}">người dùng</span></p>
    <form th:action="@{/logout}" method="post">
        <button type="submit">Đăng xuất</button>
    </form>
</body>
</html>
~~~

Logout thay đổi trạng thái phiên, nên form POST /logout cũng cần token. Trong cấu hình mặc định có CSRF, không tự làm logout qua GET chỉ để đơn giản.

## 7. Kiểm thử CSRF và đăng nhập bằng MockMvc

Tệp `src/test/java/example/logincsrf/LoginCsrfTests.java`:

~~~java
package example.logincsrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginCsrfTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginPageRendersHiddenCsrfField() throws Exception {
        mockMvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("name=\"_csrf\"")));
    }

    @Test
    void loginWithoutTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginWithInvalidTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/login")
                .with(csrf().useInvalidToken())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validTokenButWrongPasswordUsesFailureRedirect()
            throws Exception {
        mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void validTokenAndPasswordRedirectToProfile()
            throws Exception {
        mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profile"));
    }

    @Test
    void protectedProfileRedirectsAnonymousBrowserToLogin()
            throws Exception {
        mockMvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void authenticatedSessionCanViewProfile() throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mockMvc.perform(get("/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("Xin chào")));
    }

    @Test
    void logoutWithoutTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các test đi qua Spring Security filters vì dùng `@SpringBootTest` và `@AutoConfigureMockMvc`. Nếu tự dựng MockMvc mà không áp dụng security, test có thể bỏ qua `CsrfFilter` và cho kết quả sai lệch.

**Hai điểm quan trọng khi đọc test:**

- `.with(csrf())` tạo token hợp lệ trong request test. Nó **không chứng minh** template đã render token; vì vậy cần test HTML ở đầu.
- `.with(csrf().useInvalidToken())` mô phỏng token sai; tách riêng với trường hợp token hoàn toàn vắng mặt.

Bảng kỳ vọng:

| Request | CSRF | Credentials | Kết quả điển hình |
| --- | --- | --- | --- |
| GET /login | Không gửi | Chưa có | 200, HTML có hidden input |
| POST /login | Thiếu | Đúng | 403 trước bước đăng nhập |
| POST /login | Sai | Đúng | 403 |
| POST /login | Đúng | Sai | 302 về /login?error |
| POST /login | Đúng | Đúng | 302 đến /profile |
| GET /profile khi chưa login | Không cần | Chưa xác thực | Redirect /login |
| GET /profile khi có session đã xác thực | Không cần | Đã xác thực | 200 |
| POST /logout | Thiếu | Không cần xét | 403 |

Khi đổi authentication success/failure handler hoặc security entry point, mã trạng thái có thể khác. Những kỳ vọng trên gắn với **cấu hình mẫu**, không phải contract cho mọi project.

### 7.1. Chạy chương trình

Trong thư mục có Gradle và Java 17:

~~~bash
gradle test
gradle bootRun
~~~

Nếu project có wrapper, dùng:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat test` và `gradlew.bat bootRun`. Vì đây là project dùng Spring Boot dependencies, chỉ chạy `javac`/`java` trần sẽ thiếu classpath; không đưa stdout Gradle cố định vì môi trường thực tế có thể khác nhau.

## 8. Dùng browser và curl để quan sát

### 8.1. Browser

1. Mở `http://localhost:8080/login`.
2. Trong DevTools → Elements hoặc Network, kiểm tra HTML response có hidden input `_csrf` và form POST đúng URL.
3. Nhập `learner / demo-pass`, submit; quan sát POST có cookie phiên và token hợp lệ, sau đó redirect đến /profile.
4. Tạm sửa token trong DevTools để quan sát 403.
5. Từ trang profile, submit logout bằng POST và quan sát chuyển lại trang login.

Token và session cookie là dữ liệu nhạy cảm theo ngữ cảnh. Khi chụp ảnh gửi hỗ trợ, hãy che giá trị thực; đừng bật request body logging chứa password.

### 8.2. curl: phải mang cả token và cookie cùng session

Lấy trang và ghi cookie jar:

~~~bash
curl -s -c cookie-jar.txt \
  http://localhost:8080/login \
  -o login-page.html
~~~

Mở `login-page.html` trong môi trường học để lấy **value thực** của input `_csrf`. Sau đó POST với cùng cookie:

~~~bash
curl -i -b cookie-jar.txt -c cookie-jar.txt \
  -X POST http://localhost:8080/login \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo-pass" \
  --data-urlencode "_csrf=TOKEN_FROM_SAME_FORM"
~~~

`TOKEN_FROM_SAME_FORM` chỉ là **ký hiệu để thay bằng token thực**; giữ nguyên chữ đó không thể tạo request hợp lệ. Khi không có cookie cùng session hoặc dùng token từ browser khác, request có thể 403. Không đặt token/password thật trong script chia sẻ hay application logs.

Curl command với `-d` hoặc `--data-urlencode` thường gửi `application/x-www-form-urlencoded`; converter/form login đọc các parameter name do framework quy định. Nếu chuyển sang JSON, bạn không thể dựa vào hidden form field mà không thiết kế client/header CSRF integration riêng.

## 9. Token lifecycle: login, logout, timeout, nhiều tab

Spring Security có cơ chế clear/rotate CSRF token khi authentication/logout diễn ra trong flow phù hợp. Nếu user mở tab đăng nhập rồi thay đổi trạng thái phiên ở tab khác, form còn mở có thể giữ token không còn hiệu lực.

~~~text
Tab A: GET /login -> form chứa token A
Tab B: GET /login -> form chứa token hiện hành (có thể masked khác)
Tab A: POST /login -> authentication thành công
       -> session/auth state có thể đổi, token cũ có thể bị clear
Tab B: POST với token từ trước -> có thể 403
~~~

Không nên suy luận chỉ từ việc hidden string khác nhau rằng token đã rotation: Spring Security 6 có thể mask token trong từng response. Khi phân tích, cần phân biệt **raw token trong repository**, **token đã mask đưa vào HTML**, **session id**, và **token clear sau authentication/logout**.

### 9.1. Session fixation khác CSRF

Một số cấu hình session-based login sử dụng session fixation protection như đổi session id sau khi đăng nhập. Điều đó nhằm bảo vệ phiên khỏi bị tái sử dụng với session id cũ. CSRF token lại nhằm kiểm tra request có phù hợp trạng thái trình duyệt hay không. Cần cả hai khi threat model yêu cầu.

### 9.2. Xử lý stale token

Khi form đã cũ trả 403:

- Kiểm tra session timeout, cookie, application restart và token đã bị clear/rotate chưa.
- Cân nhắc hướng dẫn user tải lại form để lấy token mới; tránh tự động submit lại mật khẩu nhiều lần.
- Nếu có form dài, cân nhắc giữ dữ liệu không nhạy cảm để UX tốt hơn; **không giữ password trong localStorage**.
- Test với hai tab và nhiều node backend; nếu session store không dùng chung, POST có thể bị backend khác từ chối.
- Không tắt CSRF để giải quyết lỗi stale form.

## 10. CookieCsrfTokenRepository, SPA và hệ thống stateless

CSRF liên quan mạnh đến **ambient credentials** mà browser có thể tự gửi, không phụ thuộc đơn giản vào tên công nghệ.

| Loại ứng dụng | Nhận định cần kiểm tra |
| --- | --- |
| Server-rendered form login + session cookie | Thường cần CSRF token cho login, logout và unsafe methods |
| SPA dùng session cookie | Vẫn có CSRF risk; có thể cần token header và cookie repository/request handler tương thích |
| HTTP Basic trong browser | Browser có thể tự gửi credentials; không mặc định miễn CSRF |
| JWT nằm trong cookie tự gửi | Vẫn cần đánh giá CSRF, dù JWT được gọi là token |
| API dùng Authorization bearer header do client chủ động thêm, không có cookie ambient | Threat model CSRF khác; điều chỉnh CSRF cần xác minh toàn bộ auth flow |
| Stateless service nhưng có login endpoint cấp cookie | Cần đánh giá riêng endpoint tạo/đổi browser auth state |

`CookieCsrfTokenRepository` là một lựa chọn khi client cần đọc token từ cookie, chẳng hạn một SPA. Các tên như `XSRF-TOKEN` và `X-XSRF-TOKEN` thường được dùng. Tuy nhiên, khi muốn JavaScript đọc cookie, có thể cần thay đổi HttpOnly theo chính sách phù hợp; điều này có trade-off bảo mật vì XSS có thể đọc token.

Trong Spring Security 6, deferred token và XOR masking có thể yêu cầu **SPA request handler** thích hợp: đọc raw cookie rồi gửi header không phải công thức đúng cho mọi cấu hình. Hãy thiết kế theo version framework và kiểm tra request thực. Không đổi sang CookieCsrfTokenRepository chỉ để làm một Thymeleaf form login thông thường chạy được.

### SameSite và CORS

SameSite cookie có thể giúp giảm một số cross-site requests mang cookies, nhưng browser/flow SSO/subdomain có những khác biệt và giới hạn. CORS giúp kiểm soát JavaScript đọc/gửi một số request cross-origin, nhưng **không** nên được coi là cơ chế thay thế CSRF token một cách chung chung. Kẻ tấn công có thể tạo HTML form cross-site mà không cần quyền đọc response. Kiểm soát XSS vẫn bắt buộc.

### Bao giờ mới cân nhắc ignore CSRF cho một endpoint?

`csrf(csrf -> csrf.ignoringRequestMatchers(...))` là công cụ có thể dùng với endpoint rất cụ thể **sau khi** threat model chứng minh nó không phụ thuộc vào ambient browser credentials, chẳng hạn một webhook có chữ ký riêng. Đừng áp dụng cho form login cookie-session chỉ vì password đúng mà POST trả 403.

## 11. Quy trình chẩn đoán lỗi 403 trên login form

Khi `POST /login` bị 403, kiểm tra theo đúng thứ tự thay vì lập tức sửa UserDetailsService:

1. **Method và endpoint:** POST có đúng loginProcessingUrl của filter không?
2. **HTML đã render:** có field token thực không? `th:action` đã qua Thymeleaf/Spring MVC integration chưa?
3. **Tên field/header:** có đúng `CsrfToken.parameterName` hoặc header name đang dùng không?
4. **Cookie phiên:** request POST có gửi cookie từ lần GET form không? Có bị ảnh hưởng Secure/SameSite/Path/Domain?
5. **Repository:** token có được lưu và đọc đúng backend/session không?
6. **Handler:** token raw/masked có được xử lý như expected không, đặc biệt với SPA?
7. **Lifecycle:** phiên bị timeout, login/logout ở tab khác, token đã clear chưa?
8. **Filter order:** request bị `CsrfFilter` từ chối trước hay đã vào login authentication filter?
9. **Authentication:** nếu CSRF pass, password sai thường dẫn đến login failure redirect; phân biệt với 403.
10. **Multiple chains:** có `securityMatcher`, `@Order` hay filter cấu hình khác khiến POST /login vào chain không mong đợi không?

Môi trường học có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Không kỳ vọng mọi release log cùng một chuỗi. Không log token raw, JSESSIONID, password, header Authorization hoặc response chứa dữ liệu nhạy cảm vào môi trường công khai.

| “Sửa nhanh” | Vì sao nguy hiểm hoặc sai hướng |
| --- | --- |
| `csrf(csrf -> csrf.disable())` cho toàn bộ ứng dụng | Vô hiệu hóa phòng vệ login CSRF và các state-changing requests khác |
| `permitAll("/login")` rồi bỏ hidden field | Authorization không xóa yêu cầu CSRF |
| Chuyển login thành GET | Làm GET thay đổi auth state, gây rủi ro |
| Gán token cố định vào template | Không còn ràng buộc đúng phiên và lifecycle |
| Gửi token từ session khác | Token không khớp context của request |
| Tắt session mà không đổi kiến trúc login | Context/CSRF/session persistence có thể hỏng |
| Gửi token trong query string | Nguy cơ lộ qua history, logs, referer |
| Cho mọi POST trong `/api/**` bỏ CSRF | Có thể bỏ qua cookie-backed endpoints |
| Chỉ dùng SameSite rồi bỏ token | Không bao quát mọi flow/threat model |
| Test dùng `with(csrf())` nhưng không test view HTML | Integration test có thể pass trong khi template không gửi token |

## 12. Bài tập tự kiểm tra

1. Vì sao login CSRF có thể xảy ra khi nạn nhân **chưa** đăng nhập? Nêu kịch bản ép đăng nhập vào tài khoản do attacker sở hữu.
2. Cùng một user/password đúng, tại sao `POST /login` không có CSRF token lại có thể trả 403?
3. Phân biệt tác dụng của `permitAll()`, `CsrfFilter` và form authentication filter.
4. Với GET /login, vì sao request không cần gửi token nhưng HTML response cần chứa token?
5. Trình bày cách một token bị mask ở response có thể khác string qua hai lần render mà không nhất thiết là hai raw token khác nhau.
6. Dùng MockMvc viết test: thiếu token → 403; sai token → 403; token đúng/password sai → redirect lỗi; token đúng/password đúng → redirect thành công.
7. Tìm hidden input `_csrf` trong HTML đã render dù source Thymeleaf không có dòng input đó.
8. Dùng curl GET login + cookie jar, rồi POST chỉ có token mà không có cookie; phân tích lỗi.
9. Mở hai tab form login; đăng nhập một tab rồi submit tab cũ. Những điều kiện nào có thể khiến token cũ bị từ chối?
10. Vì sao POST /logout cũng cần CSRF protection, và điều gì sai khi logout qua GET?
11. Một SPA dùng cookie session, nhưng API trả 403 khi dùng raw XSRF cookie làm header. Những gì cần kiểm tra về request handler/deferred/masked token?
12. Với JWT trong cookie và JWT trong Authorization header được client chủ động gắn, threat model CSRF giống và khác nhau thế nào?
13. Nếu custom loginProcessingUrl là `/session/login`, điều gì phải đổi ở form action, matcher và test?
14. Liệt kê các thông tin có thể log an toàn hơn thay vì log raw token hoặc session id khi debug.
15. Trong một hệ thống nhiều node, vì sao thiếu session stickiness/distributed session nhất quán có thể gây lỗi CSRF sau GET form?

## 13. Checklist triển khai form login an toàn

- [ ] Có phân tích **login CSRF**, không chỉ chống CSRF sau đăng nhập.
- [ ] POST xử lý login vẫn nằm trong phạm vi `CsrfFilter` phù hợp.
- [ ] GET trang login công khai nhưng form chứa CSRF token được server tạo.
- [ ] Kiểm tra HTML **kết xuất thực** và tên hidden field/header đúng với cấu hình.
- [ ] Cookie phiên và token thuộc cùng CSRF context; cookie attributes phù hợp HTTPS, SameSite và reverse proxy.
- [ ] Có test thiếu token, sai token, đúng token + sai password, đúng token + đúng password.
- [ ] Logout dùng phương thức/CSRF policy đúng, tránh GET thay đổi phiên tùy tiện.
- [ ] Có test stale token, nhiều tab, session timeout, đổi session sau login.
- [ ] Không truyền token qua query string và không log token, session cookie hoặc raw password.
- [ ] Có biện pháp phòng vệ bổ sung: HTTPS, XSS prevention, rate limiting, MFA khi cần.
- [ ] Nếu dùng SPA, config cookie repository/request handler tương thích với Spring Security version.
- [ ] Không tắt CSRF rộng chỉ để tránh 403; mọi ngoại lệ matcher đều có threat model rõ.
- [ ] SecurityContext, session persistence và logout đã được kiểm thử, không suy luận từ một HTTP status.
- [ ] Test MVC/Thymeleaf rendering thực tế cùng Spring Security filters.
- [ ] Không hardcode credentials trong hệ thống triển khai thực tế.

## 14. Kết luận

**CSRF token trong form login bảo vệ hành động chuyển đổi danh tính của phiên trình duyệt**, không thay thế việc kiểm tra password. Luồng chuẩn: **GET /login render token → browser POST form cùng session cookie + token → CsrfFilter kiểm tra → authentication provider mới xác thực credentials → success/failure handler chuyển hướng**.

Nếu POST login trả 403, cần xem token, cookie, session, view rendering và request handler trước khi đụng vào password encoder. Với Spring MVC và Thymeleaf dùng đúng tích hợp, CSRF protection có thể được áp dụng mà không cần tự viết logic sinh token — nhưng luôn cần kiểm thử HTML kết xuất và request thực để chắc chắn hệ thống vận hành đúng.
