# UsernamePasswordAuthenticationFilter và tham số username, password

**Module:** Spring Security – authentication. **Chủ đề cha:** Đăng nhập biểu mẫu.  
**Phiên bản tham chiếu:** Spring Security Servlet 6.5.11, Java 17+. Nội dung tập trung vào tên trường HTTP của form login, cách filter trích credential, tùy chỉnh và kiểm thử.

## 1. Bắt đầu từ request thật

Một biểu mẫu đăng nhập Spring Security mặc định gửi:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan%40example.test&password=secret-123
~~~

`UsernamePasswordAuthenticationFilter` đọc hai HTTP request parameters có tên **`username`** và **`password`**. Nó chuyển các giá trị thành `UsernamePasswordAuthenticationToken` chưa xác thực, rồi giao cho `AuthenticationManager`. Nếu provider xác minh thành công, framework xử lý `SecurityContext`/session và gọi success handler; nếu thất bại, gọi failure handler.

**Phân biệt:** Filter này **không** có nhiệm vụ so sánh raw password với hash database. `DaoAuthenticationProvider` và `PasswordEncoder` kiểm chứng mật khẩu, `UserDetailsService` đọc account; `AuthenticationSuccessHandler` và `AuthenticationFailureHandler` quyết định HTTP response.

Với cấu hình mặc định, URL xử lý là `POST /login`. Một trang có thể được render bằng `GET /login`. GET để **hiển thị form**, POST để **gửi credential**; hai công việc khác nhau dù cùng đường dẫn.

## 2. Sơ đồ tích hợp trong Servlet filter chain

~~~text
Browser GET /private (anonymous)
          |
          v
AuthorizationFilter -> ExceptionTranslationFilter
          |
          v
AuthenticationEntryPoint -> redirect GET /login
          |
          v
HTML form: input name="username"
           input name="password"
           CSRF token
          |
          v
POST /login (form-urlencoded)
          |
          v
SecurityFilterChain
          |
          +-- CsrfFilter: kiểm tra token khi yêu cầu bảo vệ
          |
          v
UsernamePasswordAuthenticationFilter
          |
          +-- matcher POST /login?
          +-- obtainUsername(request)
          +-- obtainPassword(request)
          +-- UsernamePasswordAuthenticationToken.unauthenticated(...)
          |
          v
AuthenticationManager / ProviderManager
          |
          +-- DaoAuthenticationProvider
          |      +-- UserDetailsService.loadUserByUsername
          |      +-- PasswordEncoder.matches(raw, storedHash)
          |      +-- account status / authorities
          |
          +-- THÀNH CÔNG -> SessionAuthenticationStrategy
          |                  SecurityContextRepository
          |                  AuthenticationSuccessHandler
          |                  redirect saved request / trang đích
          |
          +-- THẤT BẠI -> clear SecurityContextHolder
                             AuthenticationFailureHandler
                             /login?error / generic 401
~~~

Sơ đồ rút gọn theo Spring Security Servlet 6.5.11. Không mặc nhiên giả định một request JSON, bearer token hay OAuth2 callback chạy qua filter form login này.

## 3. API trọng tâm của UsernamePasswordAuthenticationFilter

Class đầy đủ:

~~~java
org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter
~~~

Nó kế thừa `AbstractAuthenticationProcessingFilter`. Những method và thuộc tính thường dùng:

| Thành phần | Chữ ký/tên | Công dụng |
| --- | --- | --- |
| Attempt | `attemptAuthentication(HttpServletRequest,HttpServletResponse)` | Đọc credential và gọi AuthenticationManager |
| Username | `obtainUsername(HttpServletRequest)` | Protected hook lấy parameter username |
| Password | `obtainPassword(HttpServletRequest)` | Protected hook lấy parameter password |
| Đổi tên username | `setUsernameParameter(String)` | Đổi tên request parameter từ `username` |
| Đổi tên password | `setPasswordParameter(String)` | Đổi tên request parameter từ `password` |
| Đọc tên hiện tại | `getUsernameParameter()`, `getPasswordParameter()` | Hữu ích cho tests/debug |
| Chỉ nhận POST | `setPostOnly(boolean)` | Mặc định `true`; không nên mở GET login |
| Gắn details | `setDetails(request,authRequest)` | Chèn WebAuthenticationDetails theo config |
| URL/matcher | `setFilterProcessesUrl`/`setRequiresAuthenticationRequestMatcher` | Kế thừa base class; DSL quản lý thuận tiện hơn |
| Managers/handlers | `setAuthenticationManager`, `setAuthenticationSuccessHandler`, `setAuthenticationFailureHandler` | Kế thừa base class |

**Thông thường dùng `http.formLogin(...)`**, không tự tạo thêm một instance filter trong chain. Chỉ tự cấu hình filter khi có yêu cầu framework-level cụ thể và hiểu đầy đủ ordering, matcher, CSRF, context persistence cùng session policy.

### Default parameter names

~~~java
UsernamePasswordAuthenticationFilter.SPRING_SECURITY_FORM_USERNAME_KEY;
UsernamePasswordAuthenticationFilter.SPRING_SECURITY_FORM_PASSWORD_KEY;
~~~

Hai constant đại diện tên mặc định `username`/`password`. Đây là **tên khóa HTTP**, không khẳng định mọi ứng dụng đều dùng username thay email làm định danh.

## 4. Tại sao HTML name quan trọng hơn id?

~~~html
<form action="/login" method="post">
  <label for="login-identifier">Tên đăng nhập</label>
  <input id="login-identifier" name="username" type="text"
         autocomplete="username" required>

  <label for="login-secret">Mật khẩu</label>
  <input id="login-secret" name="password" type="password"
         autocomplete="current-password" required>

  <!-- Với CSRF bật, server/template phải chèn CSRF token hợp lệ. -->
  <button type="submit">Đăng nhập</button>
</form>
~~~

- `id="login-identifier"` dùng cho label/DOM; filter **không** tìm theo HTML id.
- `name="username"` quyết định browser tạo parameter `username`.
- `name="password"` quyết định parameter chứa raw password.
- `type="password"` giúp che chữ trên giao diện, **không mã hóa password trên mạng**.
- `method="post"` tránh gửi password trong query URL.
- `required` là UX client-side validation, không thay server validation.
- `autocomplete` giúp password manager và accessibility.

Form dưới đây sẽ bị filter mặc định đọc thiếu parameters:

~~~html
<!-- SAI nếu backend vẫn đang chờ username/password. -->
<input id="account" name="emailAddress" type="text">
<input id="secret" name="pwd" type="password">
~~~

Dù người dùng điền đúng thông tin, `getParameter("username")` và `getParameter("password")` không lấy được hai trường trên.

**Tên request parameters có phân biệt chữ hoa/chữ thường.** `username` khác `userName`, `password` khác `passWord`.

## 5. Logic obtainUsername/obtainPassword và normalization

Hai protected methods theo mặc định dùng Servlet API:

~~~java
// Mô tả logic cơ bản; không phải class độc lập.
String username = request.getParameter(usernameParameter);
String password = request.getParameter(passwordParameter);
~~~

Trong `attemptAuthentication` của Spring Security 6.5, giá trị được chuẩn hóa tiếp:

~~~java
// Rút gọn logic để học.
String username = obtainUsername(request);
username = (username != null) ? username.trim() : "";

String password = obtainPassword(request);
password = (password != null) ? password : "";
~~~

**Điểm rất quan trọng:**

1. Username được `trim()` ở hai đầu trước khi tạo token. Ví dụ `"  lan@example.test  "` trở thành `"lan@example.test"`.
2. **Password không được trim.** `"  secret  "` và `"secret"` là hai raw passwords khác nhau.
3. Nếu parameter không tồn tại, filter dùng `""`. Không có nghĩa thiếu field được chấp nhận hoặc tự có HTTP 400; provider thường từ chối authentication.
4. `String.trim()` không đồng nghĩa canonicalization Unicode, case-insensitive email hay identity-linking policy. Những vấn đề đó phải thống nhất giữa registration, DB lookup, login, recovery và unique constraints.

**Không tự viết** `request.getParameter("password").trim()` trong filter/controller: nếu người dùng cố tình chọn password chứa dấu cách đầu/cuối, việc sửa raw credential sẽ khiến đăng nhập sai.

Không bao giờ `toLowerCase` password. Tên account/email có cho phép case-insensitive hay không là quyết định nghiệp vụ có kiểm soát, không áp đặt từ tên tham số.

## 6. Request parameter khác JSON request body

`request.getParameter("username")` không phải JSON parser. Một form browser tiêu chuẩn gửi `application/x-www-form-urlencoded`, servlet container parse thành các HTTP parameters.

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&password=secret
~~~

Khác với:

~~~http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"lan","password":"secret"}
~~~

Với JSON body, filter form login mặc định **không tự đọc** hai JSON properties. Nó thường nhận null/chuỗi rỗng từ `getParameter`, dẫn đến thất bại. **Chỉ đổi `AuthenticationSuccessHandler` sang JSON response không biến request thành JSON login.**

Nếu sản phẩm thực sự cần JSON login, chọn authentication filter/converter hoặc controller phù hợp, parse body có giới hạn, tạo unauthenticated token, gọi `AuthenticationManager`, quản lý session strategy/SecurityContext, CSRF/cookie/CORS và handlers đầy đủ. Không tự tạo authenticated token từ client JSON để “bỏ qua provider”.

### Query string vẫn có thể là nguồn parameter

Servlet request parameters có thể đến từ query string hoặc body tùy cách parse. Vì vậy không giả định `getParameter("password")` **chỉ đọc POST body**, và tuyệt đối không đặt password vào URL:

~~~text
/login?username=lan&password=secret     <-- KHÔNG AN TOÀN
~~~

URL có thể đi vào proxy logs, browser history, analytics và Referer. Luôn dùng HTTPS POST, tránh logging toàn bộ form body hoặc credentials.

## 7. Token chưa xác thực và ranh giới tin cậy

Filter tạo một token như sau:

~~~java
UsernamePasswordAuthenticationToken token =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
~~~

Token này:

- Có `principal` ban đầu thường là chuỗi username;
- Có `credentials` là raw password của request;
- Mang `isAuthenticated() == false`;
- Được giao `AuthenticationManager.authenticate(token)`.

`DaoAuthenticationProvider` có thể đọc `UserDetails`, gọi `PasswordEncoder.matches(raw,stored)`, kiểm tra account locked/disabled/expired rồi trả result đã được xác minh, với authorities từ nguồn tin cậy.

**Sai và nguy hiểm:**

~~~java
// Không được lấy role từ payload chưa xác minh rồi tự cấp quyền.
UsernamePasswordAuthenticationToken.authenticated(
        request.getParameter("username"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

Factory `authenticated(...)` không tự chứng minh password. Đó là API dùng trong code trusted với bằng chứng hợp lệ, không phải cơ chế login thay `AuthenticationManager`.

`Authentication` result thành công có thể chứa `UserDetails` và authorities. Đừng lấy request parameter `username` làm bằng chứng người gửi đang sở hữu account có tên đó.

## 8. Authentication details: metadata khác credential

`setDetails(HttpServletRequest,UsernamePasswordAuthenticationToken)` gắn dữ liệu do `AuthenticationDetailsSource` cung cấp, mặc định có thể là `WebAuthenticationDetails` như remote address và session ID.

- IP có thể là tín hiệu risk scoring/rate limit, **không phải proof of identity**.
- Không mù quáng tin `X-Forwarded-For` từ client nếu reverse proxy chưa được cấu hình trusted.
- Session ID và authentication details là thông tin nhạy cảm; không trả trong JSON public.
- Không gắn raw password vào details rồi log toàn bộ token.
- Không đặt role/tenant lấy từ client vào details để provider tự coi là trusted.

Nếu yêu cầu đăng nhập bằng OTP/MFA, nên dùng flow xác minh nhiều bước đúng chính sách, không nối OTP vào raw password bằng một override `obtainPassword` tùy tiện.

## 9. Đổi tên parameters qua HttpSecurity.formLogin

Đây là hướng tùy biến được khuyến nghị trong ứng dụng Servlet:

~~~java
// Trong cấu hình HttpSecurity; snippet không standalone.
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/auth/login")
        .usernameParameter("email")
        .passwordParameter("passcode")
        .defaultSuccessUrl("/home", false)
        .failureUrl("/signin?error")
        .permitAll());
~~~

Khi đó:

| Thành phần | Giá trị mới |
| --- | --- |
| Trang hiển thị form | `GET /signin` |
| URL filter xử lý credential | `POST /auth/login` |
| Request key cho username | `email` |
| Request key cho password | `passcode` |
| Thành công | Saved request phù hợp hoặc `/home` |
| Thất bại | Thường redirect `/signin?error` với message chung |

`usernameParameter("email")` **không tự đổi `UserDetailsService` thành “lookup by email”**. Đây chỉ là tên HTTP key. Nếu account lookup thực dùng email, `UserDetailsService`/repository phải nhận diện chuỗi đó nhất quán.

Không thêm một `@PostMapping("/auth/login")` chỉ vì có `loginProcessingUrl("/auth/login")`: filter của Spring Security thường tiêu thụ request trước Spring MVC. Controller riêng chỉ cần thiết nếu **chủ ý thiết kế authentication mechanism custom**.

### Khi cấu hình trang tùy biến

`loginPage("/signin")` khiến ứng dụng phải render được `GET /signin`. Nếu URL này vẫn yêu cầu authenticated, user có thể bị redirect vòng lặp. `permitAll()` trên form login và request matcher authorization tương ứng phải hợp lệ.

## 10. Tên tham số phía HTML phải đổi đồng bộ

Với cấu hình `email`/`passcode`, form phải dùng đúng keys:

~~~html
<form th:action="@{/auth/login}" method="post">
  <label for="email">Email</label>
  <input id="email" name="email" type="text"
         autocomplete="username" required>

  <label for="passcode">Mật khẩu</label>
  <input id="passcode" name="passcode" type="password"
         autocomplete="current-password" required>

  <button type="submit">Đăng nhập</button>
</form>
~~~

Đây là **mẫu Thymeleaf form tích hợp**, không phải file HTML chạy độc lập với CSRF policy. Với Spring MVC + Thymeleaf có `RequestDataValueProcessor` phù hợp, `th:action` giúp chèn CSRF hidden input cho form POST. Hãy **inspect HTML render thực tế** để chắc chắn có token, nhất là sau khi đổi template engine hoặc security config.

Không chỉ đổi `placeholder="Email"` hoặc `id="email"`, mà quên đổi `name`. Không hard-code action URL theo domain khác nếu ứng dụng chạy dưới servlet context path; `th:action` hỗ trợ tạo URL theo context của ứng dụng.

## 11. Đổi tên trực tiếp trên filter khi thật sự cần

Nếu đang tự xây filter theo use case đặc biệt:

~~~java
UsernamePasswordAuthenticationFilter filter =
        new UsernamePasswordAuthenticationFilter(authenticationManager);

filter.setUsernameParameter("email");
filter.setPasswordParameter("passcode");
~~~

Các setters chỉ đổi **instance đó**. Nếu formLogin DSL đã tạo filter khác trong `SecurityFilterChain`, thay đổi trên một bean rời có thể không có hiệu lực.

Một filter tự tạo còn cần:

- URL/HTTP matcher;
- AuthenticationManager đúng;
- SecurityContextRepository nếu cần session;
- SessionAuthenticationStrategy (fixation/concurrent sessions);
- Success/Failure handlers;
- Remember-me policy, event publisher;
- CSRF và filter ordering;
- Tests đi qua filter chain thật.

Chỉ muốn tên field khác thì dùng DSL thay vì tự subclass/filter thứ hai.

### Protected obtainUsername/obtainPassword

Hai methods này có thể override khi yêu cầu protocol đặc biệt. Nhưng parsing JSON, thêm tenant/multifactor, hoặc normalize password bằng subclass là thay đổi **giao thức xác thực**, không phải chỉ là UI customization. Cần đánh giá threat model và tests rõ ràng.

## 12. postOnly và RequestMatcher: hai tầng khác nhau

Có hai câu hỏi riêng:

1. `requiresAuthentication(request,response)` của `AbstractAuthenticationProcessingFilter`: request có khớp URL/method matcher không?
2. `UsernamePasswordAuthenticationFilter.attemptAuthentication(...)`: `postOnly=true` có từ chối method khác POST không?

Trong thiết lập mặc định, matcher nhắm `POST /login`. Vì thế `GET /login` thường hiển thị form và **không đi vào `attemptAuthentication`**. Nếu gọi trực tiếp `attemptAuthentication` với GET trong unit test thì `postOnly=true` ném `AuthenticationServiceException`; không nên nhầm điều đó với behavior của GET form trong chain thật.

~~~java
// KHÔNG khuyến nghị cho form login public:
filter.setPostOnly(false);
~~~

Thay flag này **không tự thay matcher POST /login thành GET/POST mọi URL**. Và cho phép password qua GET là rủi ro URL leaks; không “sửa lỗi form” bằng cách tắt POST-only.

Nếu form POST `/login` trong khi DSL xử lý `/auth/login`, matcher không khớp. Lúc đó request có thể đi vào filter khác hoặc controller, trả 404/405/403, không nhất thiết `BadCredentialsException`.

## 13. Demo Java 17: chạy filter thật và thử tên trường

Demo gọi **`UsernamePasswordAuthenticationFilter.attemptAuthentication(...)` trực tiếp** trên mock Servlet request, đồng thời dùng **`ProviderManager` + `DaoAuthenticationProvider` + `PasswordEncoderFactories`** để có kiểm chứng password thực sự. Đây là chương trình Java 17 độc lập với Spring Boot/web server/DB; nó không thử matcher/CSRF/session/redirect vì những phần đó thuộc integration tests.

Demo thể hiện:

1. Default keys `username,password`;
2. Username được trim nhưng password **giữ khoảng trắng**;
3. Custom keys `email,passcode`;
4. Form gửi sai keys hoặc thiếu password phải thất bại;
5. GET truyền trực tiếp vào `attemptAuthentication` bị từ chối.

**Để tránh credential erasure ảnh hưởng object lưu trong bộ nhớ**, loader trả một `UserDetails` copy cho mỗi lần auth. Production cũng nên tránh dùng chung mutable `UserDetails` giữa cache/store và authentication principal.

### 13.1. Cấu trúc

~~~text
form-parameters-demo/
├── build.gradle
└── src/main/java/example/FormParametersDemo.java
~~~

**File build.gradle:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
    implementation 'org.springframework:spring-web:6.2.19'
    implementation 'org.springframework:spring-test:6.2.19'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.FormParametersDemo'
}
~~~

**File src/main/java/example/FormParametersDemo.java:**

~~~java
package example;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

public final class FormParametersDemo {

    private static MockHttpServletRequest request(
            String method, String userKey, String username,
            String passKey, String password) {

        MockHttpServletRequest req =
                new MockHttpServletRequest(method, "/login");

        if (userKey != null && username != null) {
            req.addParameter(userKey, username);
        }
        if (passKey != null && password != null) {
            req.addParameter(passKey, password);
        }
        return req;
    }

    private static Authentication attempt(
            UsernamePasswordAuthenticationFilter filter,
            MockHttpServletRequest request) {
        return filter.attemptAuthentication(
                request, new MockHttpServletResponse());
    }

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        // Kho lưu một hash đã encode, không lưu raw password.
        String rawPassword = "  correct-123  ";
        UserDetails account = User.withUsername("lan@example.test")
                .password(encoder.encode(rawPassword))
                .roles("USER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(account);

        // Trả bản sao để ProviderManager.eraseCredentials không
        // xóa nhầm password hash khỏi đối tượng trong store/cache.
        UserDetailsService users = name ->
                User.withUserDetails(store.loadUserByUsername(name)).build();

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager =
                new ProviderManager(provider);

        UsernamePasswordAuthenticationFilter normal =
                new UsernamePasswordAuthenticationFilter(manager);

        System.out.println("default.keys="
                + normal.getUsernameParameter() + ","
                + normal.getPasswordParameter());

        Authentication first = attempt(normal, request(
                "POST", "username", "  lan@example.test  ",
                "password", rawPassword));

        System.out.println("default.name=" + first.getName());
        System.out.println("default.authenticated="
                + first.isAuthenticated());

        // Password mất khoảng trắng => khác raw password đã lưu.
        try {
            attempt(normal, request(
                    "POST", "username", "lan@example.test",
                    "password", "correct-123"));
            System.out.println("trimmedPassword=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println(
                    "trimmedPassword=BadCredentialsException");
        }

        UsernamePasswordAuthenticationFilter customized =
                new UsernamePasswordAuthenticationFilter(manager);
        customized.setUsernameParameter("email");
        customized.setPasswordParameter("passcode");

        System.out.println("custom.keys="
                + customized.getUsernameParameter() + ","
                + customized.getPasswordParameter());

        Authentication second = attempt(customized, request(
                "POST", "email", "lan@example.test",
                "passcode", rawPassword));

        System.out.println("custom.name=" + second.getName());
        System.out.println("custom.authenticated="
                + second.isAuthenticated());

        // Gửi keys cũ cho filter đang chờ email/passcode.
        try {
            attempt(customized, request(
                    "POST", "username", "lan@example.test",
                    "password", rawPassword));
            System.out.println("wrongKeys=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println("wrongKeys=BadCredentialsException");
        }

        // Thiếu password => provider phải từ chối.
        try {
            attempt(customized, request(
                    "POST", "email", "lan@example.test",
                    null, null));
            System.out.println("missingPassword=unexpected");
        } catch (BadCredentialsException expected) {
            System.out.println("missingPassword=BadCredentialsException");
        }

        // Gọi TRỰC TIẾP attemptAuthentication với GET:
        // postOnly=true từ chối trước khi xác thực credential.
        try {
            attempt(customized, request(
                    "GET", "email", "lan@example.test",
                    "passcode", rawPassword));
            System.out.println("getMethod=unexpected");
        } catch (AuthenticationServiceException expected) {
            System.out.println("getMethod=AuthenticationServiceException");
        }
    }
}
~~~

### 13.2. Chạy

Dùng **JDK 17+**, Gradle tương thích; từ thư mục `form-parameters-demo`:

~~~bash
gradle -q run
~~~

Hoặc `./gradlew -q run` nếu có wrapper; trên Windows `gradlew.bat -q run`. Cần tải dependencies từ Maven Central ở lần đầu.

**Stdout do chính chương trình in** (không kể log của Gradle/thư viện nếu có cấu hình thêm):

~~~text
default.keys=username,password
default.name=lan@example.test
default.authenticated=true
trimmedPassword=BadCredentialsException
custom.keys=email,passcode
custom.name=lan@example.test
custom.authenticated=true
wrongKeys=BadCredentialsException
missingPassword=BadCredentialsException
getMethod=AuthenticationServiceException
~~~

### 13.3. Giải thích kết quả

- `default.keys=username,password` chứng minh hai tên mặc định.
- `default.name=lan@example.test`: filter trim input username đầu/cuối, provider load user đúng.
- `default.authenticated=true`: raw password chứa khoảng trắng đúng, encoder kiểm chứng hash.
- `trimmedPassword=BadCredentialsException`: password không được normalize tự động; bỏ khoảng trắng tạo bí mật khác.
- `custom.keys=email,passcode`: hai setters thay tên parameters trên **đúng filter instance**.
- `custom.authenticated=true` với cùng account: đặt tên input không liên quan thuật toán băm.
- `wrongKeys` và `missingPassword`: provider từ chối khi filter nhận username/password rỗng hoặc thiếu.
- `getMethod=AuthenticationServiceException`: `postOnly` mặc định true **khi attemptAuthentication được gọi**.

**Giới hạn của demo:** Không đi qua `doFilter` nên **không kiểm tra RequestMatcher**, CSRF, session fixation, `SecurityContextRepository`, redirect và success/failure handlers. GET /login thực tế thường chỉ hiển thị form chứ không kích hoạt attempt. Cần tests toàn chain ở phần sau.

## 14. Tích hợp Spring Boot Servlet hoàn chỉnh về mặt cấu hình

Ví dụ dưới là **các snippet tích hợp, không phải một ứng dụng tự chạy độc lập**. Giả định project Spring Boot Servlet có Spring Security, Thymeleaf và đã cung cấp `UserDetailsService`/`PasswordEncoder` phù hợp.

### SecurityFilterChain

~~~java
@Configuration
@EnableWebSecurity
class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/signin", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/signin")
                .loginProcessingUrl("/auth/login")
                .usernameParameter("email")
                .passwordParameter("passcode")
                .defaultSuccessUrl("/home", false)
                .failureUrl("/signin?error")
                .permitAll());

        return http.build();
    }
}
~~~

### GET /signin controller

~~~java
@Controller
class LoginPageController {

    @GetMapping("/signin")
    String loginPage() {
        return "signin";
    }
}
~~~

### Thymeleaf template

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập</title>
</head>
<body>
  <p th:if="${param.error}">
    Đăng nhập không thành công. Vui lòng thử lại hoặc chọn hỗ trợ.
  </p>

  <form th:action="@{/auth/login}" method="post">
    <label for="email">Email</label>
    <input id="email" name="email" autocomplete="username" required>

    <label for="passcode">Mật khẩu</label>
    <input id="passcode" name="passcode" type="password"
           autocomplete="current-password" required>

    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
~~~

`th:if` là cú pháp Thymeleaf được diễn giải ở server; nội dung lỗi **không dùng exception.getMessage()**. Nếu user đã bị khóa, disabled hoặc username không tồn tại, public message vẫn nên chung theo threat model.

CSRF token: với integration Spring MVC + Thymeleaf phù hợp, `th:action` và `RequestDataValueProcessor` có thể thêm hidden input tự động. **Kiểm tra HTML được render thật**, không giả định mọi template engine đều tự chèn CSRF. Nếu viết HTML/JS thủ công, gửi token theo policy của `CsrfTokenRepository`.

**Không khai báo POST controller cạnh URL filter** trừ khi chủ ý thay authentication mechanism. Với `loginProcessingUrl("/auth/login")`, chính Spring Security filter xử lý request.

## 15. CSRF: trường hợp đúng password nhưng bị HTTP 403

Một browser form login dùng cookie/session thường cần CSRF protection. `CsrfFilter` có thể từ chối POST thiếu token **trước khi UsernamePasswordAuthenticationFilter chạy**:

~~~text
POST /auth/login
      |
      v
CsrfFilter
      +--> thiếu/sai CSRF token -> 403
      |
      v
UsernamePasswordAuthenticationFilter
      |
      v
AuthenticationManager
~~~

Do đó:

- `403` không tự có nghĩa mật khẩu sai.
- `AuthenticationFailureHandler` cho username/password không nhất thiết chạy.
- Không vô hiệu CSRF toàn cục chỉ để frontend đăng nhập được.
- Kiểm tra token ở template, session/cookie, hidden input/header và rotations.
- Với SPA cookie-auth, đảm bảo client gửi token và cookies theo chính sách SameSite/CORS.
- Stateless API với bearer header có threat model khác, không áp dụng kết luận cookie-auth máy móc.

CSRF token **không** thay thế password, và password không thay thế CSRF token.

## 16. Frontend AJAX với form-urlencoded

Một ứng dụng frontend dùng fetch có thể giữ nguyên filter form login, chỉ gửi body đúng định dạng:

~~~javascript
// Mã minh họa, không standalone: csrfToken phải lấy từ server an toàn.
const credentials = new URLSearchParams({
  email: "lan@example.test",
  passcode: "user-entered-password"
});

const response = await fetch("/auth/login", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded",
    "X-CSRF-TOKEN": csrfToken
  },
  body: credentials
});
~~~

Không hardcode password thật vào source frontend; ở UI thực giá trị đến từ input người dùng. Tên CSRF header tùy cấu hình server.

Với form login mặc định, server thường **redirect** khi thành công/thất bại. Fetch theo redirect có thể nhận HTML trang đích chứ không phải JSON. Nếu client đòi response JSON, cấu hình `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` trả JSON tương ứng; thay response handler **không** khiến filter parse JSON request body.

Cần bảo đảm session cookie được gửi trong request tiếp theo, CORS policy và SameSite/Secure/HttpOnly đúng. Khi xây JSON login custom, phải tổ chức lại toàn bộ authentication/session/context pipeline chứ không chỉ thay Content-Type.

## 17. Multiple SecurityFilterChain: vì sao filter không chạy?

Một app có thể có:

~~~text
/api/**  -> stateless bearer resource server
/web/**  -> form login + HTTP session
/**      -> fallback
~~~

Nếu request `POST /auth/login` thuộc chain thứ nhất không có `UsernamePasswordAuthenticationFilter`, cấu hình `formLogin` ở chain thứ hai không giúp gì. Cần kiểm tra:

1. `securityMatcher` nào khớp method/URL;
2. `@Order` của nhiều chains và fallback matcher;
3. `loginProcessingUrl` có nằm trong chain áp dụng không;
4. filter nào nhận POST; có duplicate filter không;
5. có CsrfFilter/authorization filter chặn trước không;
6. có custom login controller ở chain khác không;
7. providers được cấu hình trên AuthenticationManager nào.

Đừng chỉ thấy một bean `UsernamePasswordAuthenticationFilter` trong application context rồi kết luận endpoint thực sự dùng nó. Một bean/instance có thể không nằm trong chain đang chạy.

## 18. Success/Failure handlers, SecurityContext và session

Sau khi `AuthenticationManager` trả kết quả:

| Nhánh | Các tác vụ chính |
| --- | --- |
| Thành công | SessionAuthenticationStrategy, tạo/lưu SecurityContext, remember-me hook, success handler và redirect/response |
| Thất bại | Clear SecurityContextHolder, remember-me failure hook, failure handler trả thông điệp chung |
| Chưa đăng nhập vào tài nguyên protected | AuthenticationEntryPoint bắt đầu login/challenge |
| Đã đăng nhập nhưng thiếu quyền | Authorization/AccessDeniedHandler, thường HTTP 403 |

Trong Spring Security 6, `SecurityContextHolderFilter` dùng explicit-save style; built-in form login thực hiện context persistence khi đã cấu hình đúng. **Custom login controller tự gọi `authenticate(...)` và `setContext(...)` mà không `SecurityContextRepository.saveContext(...)` có thể thành công trong request hiện tại nhưng request sau lại 401.**

Đừng nhầm sự cố “request sau không giữ session” với sự cố “tên parameter sai”. Có hai bước xác minh: credential có thực được provider công nhận không; rồi session/token có được lưu, cấp và gửi đúng không.

## 19. Tránh rò tài khoản qua lỗi đăng nhập

Failure response không nên khác nhau tùy nguyên nhân như:

~~~text
Không có username -> 404 USER_NOT_FOUND
Sai password     -> 401 WRONG_PASSWORD
Account locked   -> 423 ACCOUNT_LOCKED
Account disabled -> 403 DISABLED
~~~

Kẻ tấn công có thể dùng status/body/redirect/header để dò account existence/state. Với endpoint chưa xác minh, cần phản hồi đủ nhất quán trong nhóm lỗi nhạy cảm:

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Đăng nhập không thành công. Vui lòng kiểm tra thông tin."
}
~~~

`AuthenticationFailureHandler` là nơi thích hợp chuẩn hóa response của **form authentication failure**, không phải nơi tự cấp quyền cho account đang bị khóa. Spring Security có `hideUserNotFoundExceptions` cho DAO provider, nhưng nó không tự giải quyết hết Locked/Disabled, timing oracle, rate limit hoặc signup/recovery leakage.

Audit phía server vẫn có thể phân biệt nguyên nhân nội bộ, nhưng phải hạn chế quyền truy cập và **không log password/hash/token**. Dùng rate limiting, monitoring, lockout có kiểm soát và hỗ trợ recovery để giảm credential stuffing/brute force.

## 20. Đầu vào bất thường: missing, duplicate và Unicode

### Missing parameters

Nếu request không có tên field đã cấu hình, `obtainUsername`/`obtainPassword` có thể trả null; filter chuẩn thay bằng `""` rồi gọi manager. Đừng mặc định điều đó có HTTP 400. Provider có thể ném `BadCredentialsException` và failure handler trả error chung.

### Duplicate parameters

~~~text
username=lan&username=admin&password=secret
~~~

`getParameter` trả một giá trị trong tập parameter values. Nếu reverse proxy/WAF và Servlet container parse khác nhau, có nguy cơ HTTP parameter pollution. Theo threat model, kiểm tra/reject duplicate username/password ở ingress/filter riêng và test cùng servlet container thực. Không cho client gửi thêm `role=ADMIN` để ảnh hưởng authenticated authorities.

### Unicode, length và canonicalization

Giới hạn kích thước request và parameter count/length để tránh DoS. Với username/email, định nghĩa normalization nhất quán giữa registration/login/recovery và unique DB constraint. **Không tự normalize raw password** thành chuỗi khác khi xác thực. Kiểm thử Unicode (kể cả ký tự ngoài ASCII) trên cùng encoding end-to-end.

Không dump request body và session ID ra log khi debug; chỉ log request ID, outcome và metadata đã kiểm soát.

## 21. Unit test và integration test phải tách vai trò

**Unit-level**: gọi `attemptAuthentication(...)` như Java demo để xác minh keys, trim và provider behavior. Test này **bỏ qua** URL matcher/CSRF/SessionAuthenticationStrategy.

**Integration-level**: gửi HTTP request qua `SecurityFilterChain` và kiểm tra:

| Kịch bản | Mong đợi |
| --- | --- |
| GET login page | Render được form cho anonymous |
| POST đúng URL, đúng names, đúng credential + CSRF | Thành công, session/redirect đúng |
| POST đúng credential nhưng keys cũ khi filter chờ keys mới | Thất bại |
| POST thiếu CSRF | Bị chặn theo CSRF policy, handler có thể chưa chạy |
| POST JSON vào filter mặc định | Không tự được parse như form params |
| POST sai URL/method | Không trúng matcher form login |
| Username có spaces | Trim theo behavior chuẩn |
| Password có spaces | Giữ nguyên raw credential |
| Unknown/locked/disabled account | Từ chối, không cấp authenticated session |
| Request thứ hai với session cookie | Nhận đúng Authentication nếu stateful |
| GET credential trong URL | Không được hỗ trợ như login an toàn |
| Nhiều filter chains | Đúng chain/matcher/provider/handlers |
| Logout | Session/context bị hủy theo policy |
| Rate limit/brute force | Giới hạn hoạt động, không lộ userExists qua 429 |

### Minh họa Spring Security Test (không standalone)

~~~java
// Cần MockMvc, Spring Security Test và config ứng dụng thật.
mvc.perform(post("/auth/login")
        .with(csrf())
        .param("email", "lan@example.test")
        .param("passcode", "correct-password"))
    .andExpect(authenticated());

mvc.perform(post("/auth/login")
        .with(csrf())
        .param("username", "lan@example.test")
        .param("password", "correct-password"))
    .andExpect(unauthenticated());
~~~

Response có thể là 302 redirect với formLogin HTML, hoặc 200/401 JSON nếu đã cấu hình handler JSON; assertion status phải đúng contract thực tế. Sau login thành công, nên kiểm tra tiếp request thứ hai sử dụng session cookie/id nhận được. Đừng test `ControllerAdvice` đơn lẻ rồi nghĩ đã kiểm tra authentication filter: `AuthenticationException` thường được filter bắt và chuyển cho failure handler.

## 22. Bảng lỗi phổ biến và cách tìm đúng nguyên nhân

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Form nhập đúng nhưng luôn sai | `name` HTML khác names backend | Đồng bộ `usernameParameter`/`passwordParameter` và form |
| GET /signin redirect vòng lặp | Trang custom login chưa permitAll | Mở đúng loginPage cho anonymous |
| POST trả 404/405 | `loginProcessingUrl` hoặc chain matcher sai | Kiểm tra method, action, context path |
| POST trả 403 dù password đúng | CSRF token thiếu/sai hoặc filter khác chặn | Xem CsrfFilter và rendered token |
| POST JSON không được xác thực | Default filter đọc request parameters | Dùng form-urlencoded hoặc JSON auth flow riêng |
| Mật khẩu có spaces luôn sai | Frontend/custom code trim password | Bỏ biến đổi raw password |
| Username trim rồi lại tìm nhầm account | DB/service normalization không nhất quán | Thống nhất identity lookup/unique key |
| Tạo filter trực tiếp nhưng handler không chạy | Filter instance không được gắn đúng chain | Ưu tiên formLogin DSL hoặc config đúng instance |
| Đã đổi keys nhưng frontend gửi keys cũ | Deploy frontend/backend không đồng bộ | Rolling deploy tương thích, integration tests |
| ControllerAdvice không bắt BadCredentials | Lỗi đã được filter xử lý | Cấu hình AuthenticationFailureHandler |
| Login 200 nhưng request sau 401 | Custom flow quên SecurityContextRepository/session | Explicit save và cookie/session strategy |
| Sai username và account locked trả status khác nhau | Enumeration oracle | Generic response, audit nội bộ |
| GET credentials đi vào query string | Form GET / JS sai | Chỉ POST TLS, không log URL chứa secret |
| Duplicate parameter làm behavior không ổn định | HTTP parameter pollution | Validation/rejection và test ingress |
| Login thành công nhưng redirect sai URL | RequestCache/defaultSuccessUrl/handler | Xác minh saved request và target |
| Filter xử lý nhầm endpoint API | Multiple chains/order/matcher | Tách web form và stateless API |
| Login chậm sau đổi BCrypt cost | Hashing CPU + brute-force | Benchmark/rate limit/capacity |
| User có role sai từ request | App tự cấp trusted token từ input | Chỉ dùng provider verified authorities |
| Browser có JSESSIONID trước login | RequestCache/failure handler/component khác tạo session | Truy nguồn tạo session thay vì kết luận auth thành công |

**Quy trình debug ít rủi ro:** quan sát method/URL/content-type/names trong DevTools (không chụp password thật); đối chiếu SecurityFilterChain; kiểm tra CSRF; rồi kiểm tra provider/encoder/account flags; cuối cùng xác minh cookie/session và redirect.

## 23. Checklist triển khai

1. Form method `POST` qua HTTPS.
2. `form action` đúng `loginProcessingUrl`.
3. HTML `name` trùng với `usernameParameter`/`passwordParameter`.
4. GET trang login mở cho anonymous, không redirect vòng lặp.
5. `UserDetailsService` hỗ trợ identity value đang gửi (username/email).
6. PasswordEncoder băm/xác minh đúng; password raw không bị trim/case-fold.
7. CSRF bảo vệ browser cookie-auth, token render và gửi đúng.
8. Không đặt credential vào query URL hoặc logs.
9. Không tự tạo authenticated token từ client payload.
10. Success/failure handler trả contract phù hợp UI, không lộ account state.
11. AuthenticationManager/provider đúng chain, không duplicate filters.
12. Built-in form flow xử lý session fixation/context persistence; custom flow phải bổ sung đủ.
13. Test password chứa khoảng trắng, username có spaces, Unicode/encoding.
14. Test missing/duplicate parameters và request quá lớn.
15. Test POST JSON không được hiểu nhầm như form.
16. Test logout, remember-me và request thứ hai với session.
17. Rate limiting/captcha không tạo account enumeration oracle.
18. Không coi `id`/`placeholder` là HTTP parameter names.
19. Dùng phiên bản đồng bộ Spring Security/Spring Framework qua BOM khi có thể.
20. Audit, monitoring, support không giữ raw passwords/tokens.

## 24. Câu hỏi tự kiểm tra

**1.** Filter mặc định nhận yêu cầu URL/method nào?  
**Đáp:** `POST /login` với `UsernamePasswordAuthenticationFilter` mặc định. GET /login thường là trang form.

**2.** Hai tham số mặc định là gì?  
**Đáp:** `username` và `password`, dựa trên HTTP parameter names.

**3.** HTML có `id="email"` nhưng `name="username"`, filter đọc key nào?  
**Đáp:** `username`; `id` không phải tên request parameter.

**4.** Đổi `usernameParameter("email")` có tự làm DB lookup theo email?  
**Đáp:** Không. Nó chỉ đổi request key; UserDetailsService phải hỗ trợ identity lookup đó.

**5.** Filter có tự kiểm tra BCrypt hash không?  
**Đáp:** Không. Nó chuyển unauthenticated token cho AuthenticationManager; provider/PasswordEncoder kiểm tra.

**6.** Username và password có bị trim giống nhau không?  
**Đáp:** Không. Username được trim ở filter chuẩn, password không được trim.

**7.** Gửi `application/json` có tự được obtainUsername đọc không?  
**Đáp:** Không mặc định; cần form-urlencoded hoặc JSON authentication integration riêng.

**8.** Tại sao password đúng nhưng POST trả 403?  
**Đáp:** CSRF có thể từ chối trước auth filter; kiểm tra CSRF token và filter chain.

**9.** `postOnly=true` nghĩa mọi GET /login đều ném AuthenticationServiceException?  
**Đáp:** Không. Matcher mặc định thường không đưa GET vào `attemptAuthentication`. Nếu gọi trực tiếp method bằng GET thì nó từ chối.

**10.** `UsernamePasswordAuthenticationToken.authenticated(...)` có tự xác minh username/password không?  
**Đáp:** Không. Không dùng với dữ liệu client chưa xác minh.

**11.** Đổi `loginPage` có đồng nghĩa đổi `loginProcessingUrl` không?  
**Đáp:** Hai khái niệm khác nhau; cấu hình rõ cả hai khi cần để không nhầm GET page với POST processing.

**12.** Unit test attemptAuthentication thành công có bảo đảm browser request sau vẫn logged-in?  
**Đáp:** Không. Cần test filter chain, session strategy, SecurityContextRepository, cookie và redirect.

**13.** Tại sao không đặt password trong query string dù dùng HTTPS?  
**Đáp:** URL có thể bị ghi vào browser history, logs, analytics và các nơi khác.

**14.** Khi request gửi đúng password nhưng tên field lệch, response nên tiết lộ “username không tồn tại” để debug không?  
**Đáp:** Không. Public response phải bảo vệ account existence/state; debug qua telemetry nội bộ an toàn.

**15.** Nếu một ứng dụng có bearer API và form login, form filter có tự xử lý mọi API request không?  
**Đáp:** Không. Mỗi SecurityFilterChain/RequestMatcher có phạm vi và authentication mechanism riêng.

## 25. Tham khảo chính thức

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): GET login page, POST form, `username`/`password`, CSRF và authentication filter flow.
- [UsernamePasswordAuthenticationFilter API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html): `attemptAuthentication`, `obtainUsername`, `obtainPassword`, parameter setters và `setPostOnly`.
- [FormLoginConfigurer API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html): `loginPage`, `loginProcessingUrl`, `usernameParameter` và `passwordParameter`.
- [AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): RequestMatcher, success/failure, context, session strategy.
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): đối chiếu raw password với hash, xử lý account state.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): AuthenticationManager, ProviderManager, Authentication tokens.
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF protection của form/cookie-auth.
- [Spring Security 6.5 – Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation, context persistence.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication failures, anti-enumeration, brute force mitigation.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): cách lưu password hash an toàn.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF token/headers cho browser flows.

**Kết luận:** `UsernamePasswordAuthenticationFilter` biến **HTTP parameters → unauthenticated token → AuthenticationManager**. Mặc định nó nhận **`POST /login`** và đọc **`username`/`password`** bằng Servlet `getParameter`; dùng `FormLoginConfigurer` để đổi tên đồng bộ với HTML. Username được trim, password giữ nguyên. Một login flow đúng còn cần CSRF, provider/encoder, filter matcher, handlers và session/context persistence, không chỉ hai ô input.
