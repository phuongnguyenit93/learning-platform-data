# failureUrl, failureHandler và thông báo đăng nhập không tiết lộ tài khoản

Trong ứng dụng **Spring Security dùng Servlet và đăng nhập biểu mẫu (form login)**, khi người dùng gửi thông tin đăng nhập sai, việc xác thực có thể thất bại ở `AuthenticationManager` hoặc `AuthenticationProvider`. Spring Security không nên trả thẳng nguyên nhân nội bộ như “không tồn tại username”, “mật khẩu sai”, “tài khoản bị vô hiệu hóa” hoặc chi tiết ngoại lệ cho trình duyệt: làm như vậy có thể giúp kẻ tấn công **liệt kê tài khoản có thật (account/username enumeration)** và tối ưu chiến dịch dò mật khẩu.

Hai điểm mở rộng liên quan trực tiếp tới trải nghiệm khi đăng nhập thất bại là:

- **`failureUrl("/login?error")`**: cách cấu hình ngắn gọn, thường chuyển hướng về một URL cố định để giao diện hiển thị **thông báo chung**.
- **`failureHandler(AuthenticationFailureHandler)`**: cung cấp toàn quyền kiểm soát phản hồi sau một lần xác thực thất bại ở authentication filter, chẳng hạn redirect có kiểm soát, trả JSON `401` cho client hoặc ghi audit nội bộ với dữ liệu được lọc.

Bài thuộc nhóm **Đăng nhập biểu mẫu**, trình bày luồng lỗi trong `UsernamePasswordAuthenticationFilter`, tương quan giữa `failureUrl` và `failureHandler`, cách tránh lộ account qua body/status/redirect/thời gian, cấu hình trang login, xử lý CSRF, session, user experience, kiểm thử bảo mật và ví dụ **Java 17 chạy độc lập** mô phỏng response bằng API Spring Security thật.

**Nguyên tắc nền tảng:** Cho người dùng biết **“Đăng nhập không thành công; hãy kiểm tra thông tin hoặc dùng phương thức khôi phục”** là đủ trong phần lớn tình huống. Hệ thống vận hành có thể phân biệt nguyên nhân sâu hơn **ở kênh nội bộ có bảo vệ**, nhưng không dùng thông điệp công khai để xác nhận rằng một tên tài khoản đã tồn tại.

## 1. Form login thất bại ở bước nào?

Luồng điển hình với Spring Security 6, Java Servlet:

~~~text
Browser
  |
  |  POST /login
  |  username=...&password=...&CSRF=...
  v
SecurityFilterChain
  |
  +--> CsrfFilter (nếu CSRF được bật)
  |      |-- thiếu/không hợp lệ -> 403 trước khi form auth filter
  |
  '--> UsernamePasswordAuthenticationFilter
          |
          +--> Đọc username/password theo parameter names
          +--> Tạo Authentication CHƯA được tin cậy
          +--> AuthenticationManager.authenticate(...)
          |      |
          |      +--> DaoAuthenticationProvider
          |             +--> UserDetailsService.loadUserByUsername
          |             +--> PasswordEncoder.matches
          |             +--> Kiểm tra account/credential status
          |
          +-- THÀNH CÔNG -> SecurityContext, session strategy,
          |                 successHandler theo cấu hình
          |
          '-- THẤT BẠI -> AuthenticationException
                           |
                           +--> Không để auth thất bại thành trusted principal
                           +--> remember-me failure hook nếu có
                           '--> AuthenticationFailureHandler
                                    |
                                    +--> Redirect /login?error
                                    '--> Hoặc response 401 JSON cố định
~~~

Sơ đồ **khái niệm**, không phải source code của framework. Các bước/lifecycle thực tế còn phụ thuộc security chain, session, authentication filter, remember-me và phiên bản Spring Security. Quan trọng: **authentication failure handler không phải nơi xác minh raw password**; việc đó thuộc `AuthenticationManager`/provider và `PasswordEncoder`.

### 1.1. AuthenticationException là nhóm lỗi nào?

Một số subclass thường gặp:

| Ngoại lệ | Ý nghĩa nội bộ | Có nên hiển thị nguyên văn? |
|---|---|---|
| `BadCredentialsException` | Bằng chứng xác thực không hợp lệ | **Không** |
| `UsernameNotFoundException` | `UserDetailsService` không tìm thấy account | **Không** |
| `DisabledException` | Account chưa được cho phép đăng nhập | **Không xác nhận account tồn tại** |
| `LockedException` | Account đang bị khóa | **Không xác nhận account tồn tại** |
| `AccountExpiredException` | Thời hạn account đã hết | Không lộ ở bước login công khai |
| `CredentialsExpiredException` | Credential đã hết hạn theo policy | Dùng luồng đổi/reset phù hợp sau khi chứng minh danh tính |
| `AuthenticationServiceException` | Lỗi xử lý xác thực/hạ tầng, tùy provider | Không in stacktrace; cảnh báo vận hành |

Những subclass không có cùng nguyên nhân: `LockedException` khác password sai, sự cố database khác account không tồn tại. **Thông điệp trả cho người dùng có thể giống nhau**, nhưng metrics/audit/runbook nội bộ phải phân biệt để khắc phục đúng và không bỏ qua lỗi hệ thống.

### 1.2. Đừng nhầm lỗi CSRF với lỗi mật khẩu

Nếu browser gửi `POST /login` mà thiếu/không hợp lệ CSRF token khi cơ chế CSRF được bật, `CsrfFilter` có thể từ chối request **trước khi `UsernamePasswordAuthenticationFilter` gọi provider**. Vì vậy `failureHandler` dành cho form authentication **có thể không chạy**, và kết quả thường là `403`.

Cách xử lý là cấu hình form cung cấp CSRF token hợp lệ và test đúng policy, **không tắt CSRF toàn ứng dụng** chỉ để redirect về trang login đẹp hơn. Với ứng dụng dùng cookie/session trên browser, bỏ CSRF protection có thể là lỗ hổng nghiêm trọng.

## 2. failureUrl là gì và mặc định hoạt động ra sao?

Trong cấu hình `formLogin`, bạn có thể viết:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .loginPage("/login")
            .loginProcessingUrl("/login")
            .failureUrl("/login?error")
            .permitAll());
    return http.build();
}
~~~

Đây là **mảnh cấu hình Spring Boot/Spring Security Servlet**, cần imports, beans, user store/provider, Spring MVC và trang login tương ứng; không phải chương trình độc lập. `failureUrl` được cung cấp bởi `AbstractAuthenticationFilterConfigurer`. Nó cấu hình một handler mặc định dựa trên **`SimpleUrlAuthenticationFailureHandler`** để chuyển hướng đến URL được chỉ định khi form authentication thất bại.

Với cách dùng này, trình duyệt thường thấy luồng:

~~~text
POST /login -> xác thực thất bại
HTTP 302 Location: /login?error
GET /login?error -> hiển thị lại form và thông báo CHUNG
~~~

HTTP status redirect ví dụ là hành vi phổ biến, còn method/status chi tiết còn phụ thuộc redirect strategy, proxy và cấu hình. Sau redirect, URL chỉ cho biết **lần đăng nhập trước đã thất bại**, **không cho biết username có thật hoặc account đang bị khóa**.

### 2.1. Vì sao dùng ?error thay vì ?reason=USER_NOT_FOUND?

`/login?error` là một cờ chung, đủ để giao diện hiển thị một nội dung cố định. Những URL sau **không nên dùng** cho login public:

~~~text
/login?error=USERNAME_NOT_FOUND
/login?error=PASSWORD_WRONG
/login?error=ACCOUNT_DISABLED
/login?reason=locked&username=linh
/login?message=Invalid%20password%20for%20linh
~~~

Dù giao diện có thể che chữ, khác biệt query string có thể bị browser history, log của reverse proxy, analytics, referer hoặc automation quan sát. Nó còn tiết lộ thông tin cho người đang thử hàng triệu username.

Một URL redirect chung không tự chứng minh an toàn: nếu HTML body, cookie, HTTP status, latency hoặc endpoint khôi phục thay đổi có hệ thống theo việc account tồn tại, **username enumeration vẫn xảy ra**.

### 2.2. failureUrl không phải trang tự sinh tùy ý

Khi gọi `loginPage("/login")`, **ứng dụng thường chịu trách nhiệm cung cấp GET /login** (ví dụ qua controller + Thymeleaf). `loginProcessingUrl("/login")` lại chỉ định URL **POST** mà authentication filter xử lý. Hai endpoint có thể cùng path nhưng khác method và chức năng.

Nếu một `SecurityFilterChain` chỉ áp dụng `securityMatcher("/secured/**")` mà login page/processing URL là `/login` nằm ngoài matcher, Spring Security filter xử lý form có thể **không áp dụng cho POST /login**. Kết quả thường là 404/405 hoặc flow sai, không phải do `failureUrl`. Test URL thực cùng đúng chain.

### 2.3. failureUrl khác successUrl

`failureUrl` dành cho lần **xác thực thất bại**. `defaultSuccessUrl` và `successHandler` dành cho **xác thực thành công**. Không dùng failure URL để “cho user tiếp tục login” khi provider đã từ chối.

Nếu muốn đưa người dùng trở về trang họ định truy cập, Spring Security có request-cache và success handlers thích hợp. **Đường dẫn redirect từ client** phải được xác minh trước khi sử dụng, tránh open redirect hoặc rò dữ liệu qua URL ngoài miền.

## 3. AuthenticationFailureHandler: quyền kiểm soát phản hồi sau thất bại

Giao diện quan trọng:

~~~java
public interface AuthenticationFailureHandler {
    void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException;
}
~~~

Đây là chữ ký API **được rút gọn để học**, không phải interface bạn tự viết. Handler được authentication filter gọi sau khi phát hiện lỗi thuộc phạm vi xử lý của nó. Các tham số:

- `request`: HTTP request thất bại, có thể chứa raw username/password, headers, session; **không dump/log cả object**.
- `response`: nơi chọn status/header/body/redirect. Handler phải bảo đảm response đúng định dạng client mong đợi và không commit hai lần.
- `exception`: chứa loại lỗi và thông điệp **nội bộ**; có thể hữu ích cho audit/logging có kiểm soát, **không đưa nguyên `getMessage()` hay stacktrace ra client**.

### 3.1. failureUrl và failureHandler liên hệ ra sao?

| Cấu hình | Mục đích | Kết quả thường thấy |
|---|---|---|
| `.failureUrl("/login?error")` | Browser form login đơn giản | Redirect về URL cố định |
| `.failureHandler(handler)` | Tự quyết định redirect/forward/JSON/metric | Theo handler |
| `SimpleUrlAuthenticationFailureHandler` | Implementation sẵn có cho URL redirect/forward | Redirect hoặc forward đến URL đã cấu hình |
| `ExceptionMappingAuthenticationFailureHandler` | Có thể map exception type sang URL | **Cần thận trọng**: map public URL khác nhau theo account status sẽ làm lộ trạng thái |
| Handler tự viết trả `401` | Một số client AJAX/API | Status/body chung, không có redirect |

`failureUrl` về cơ bản là **shortcut cấu hình một `AuthenticationFailureHandler`**. Không nên gọi `failureUrl(...)` và `failureHandler(...)` liên tiếp rồi giả định cả hai kết quả luôn cùng chạy; cấu hình sau có thể thay thế hiệu lực của handler trước. **Chọn một policy rõ ràng** cho từng security chain và kiểm thử response thực tế.

### 3.2. Khi nào nên chọn failureHandler?

- Login được thực hiện bởi **fetch/AJAX** và client mong `401` JSON, không mong HTML redirect.
- Cần ghi **audit event** hoặc số liệu thất bại được lọc theo policy, không tiết lộ account.
- Cần response header `Cache-Control`/content type hoặc status code thống nhất.
- Ứng dụng nhiều tenant có trang login được chọn theo **mapping đã xác minh**, nhưng không redirect tùy ý theo input client.
- Muốn bỏ qua việc cache `AuthenticationException` vào session cho login lỗi, dùng một custom handler không gọi `saveException` và không xuất stacktrace.

Không nhất thiết phải viết custom handler chỉ vì muốn đổi câu tiếng Việt trên trang login: với `failureUrl` cố định và template hiển thị thông báo chung, **cấu hình mặc định có thể đơn giản và an toàn hơn**.

### 3.3. Đừng để exception message quyết định thông điệp public

**Sai:**

~~~java
response.sendError(401, exception.getMessage());
~~~

Hoặc:

~~~java
return "redirect:/login?error=" +
        URLEncoder.encode(exception.getMessage(), UTF_8);
~~~

Đây là **phản ví dụ**. `exception.getMessage()` có thể chứa nội dung quá chi tiết, bị tùy biến bởi provider hoặc chứa dữ liệu gắn với account. Gắn exception vào URL còn khiến nội dung đi vào log/browser history.

**Đúng về nguyên tắc:**

~~~java
response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
response.setContentType("application/json;charset=UTF-8");
response.getWriter().write(
        "{\"error\":\"Không thể đăng nhập với thông tin vừa cung cấp.\"}");
~~~

Đây là **mảnh code trong handler**, không phải class độc lập. Nếu response là JSON, cần xem xét escaping khi giá trị động; ví dụ trên sử dụng **literal cố định**, không nối exception hay username.

## 4. SimpleUrlAuthenticationFailureHandler: redirect, forward và session

Handler có sẵn của Spring Security thường được dùng khi cấu hình `failureUrl`.

### 4.1. Khi có defaultFailureUrl

~~~java
SimpleUrlAuthenticationFailureHandler failure =
        new SimpleUrlAuthenticationFailureHandler("/login?error");
~~~

Với `onAuthenticationFailure(...)`, handler sẽ chuyển hướng đến `defaultFailureUrl` đã đặt. Nếu cấu hình `useForward=true`, nó gọi `RequestDispatcher.forward` thay vì redirect; điều này có semantics khác về HTTP method, request attributes, container dispatcher và rendering.

**Không dùng forward chỉ để tránh redirect rồi giả định form sẽ có một GET mới.** Forward giữ trong cùng request/dispatch, có thể khiến controller/template nhận method và request body khác dự kiến; cần integration test.

### 4.2. Khi KHÔNG có defaultFailureUrl

JavaDoc cho biết `SimpleUrlAuthenticationFailureHandler` nếu không có URL sẽ gửi phản hồi lỗi **`401`**, kèm message từ `AuthenticationException` theo behavior của implementation. Với yêu cầu **không lộ chi tiết tài khoản**, **không dùng nhánh đó để public một cách mặc định** mà không kiểm tra message/status/body thực.

Đặt một `failureUrl` cố định hoặc dùng handler trả body cố định nếu client API cần 401. Kết quả mong đợi phải được kiểm thử theo version/framework container đang chạy.

### 4.3. Ngoại lệ có thể được giữ trong session/request

Một điểm dễ bị bỏ sót: `SimpleUrlAuthenticationFailureHandler` gọi `saveException` khi redirect/forward tới URL thất bại.

- **Redirect:** thường lưu `AuthenticationException` trong `HttpSession` để view có thể sử dụng; nếu chưa có session, có thể tạo mới theo `allowSessionCreation`.
- **Forward:** exception thường được đặt trong **request attribute** vì vẫn ở request hiện tại.
- Attribute được Spring Security dùng thường là `WebAttributes.AUTHENTICATION_EXCEPTION`.

**Dữ liệu có trong session không đồng nghĩa nó được phép đưa lên giao diện.** Template đừng đọc message exception rồi render, dù người dùng tự xem được trang `/login?error`. Nếu viết custom handler chỉ dùng redirect cố định và không muốn giữ exception, có thể tránh gọi `saveException`, hoặc quản lý session attribute cũ theo policy.

### 4.4. Session exception khác Authentication của user

`WebAttributes.AUTHENTICATION_EXCEPTION` chỉ lưu **lý do thất bại**, không phải principal đã được xác thực. Đừng coi session có attribute đó là đã login. Nếu form login thất bại sau khi một session khác từng tồn tại, phải kiểm tra chính sách SecurityContext/session liên quan; không tự tuyên bố logout toàn bộ phiên chỉ vì failure handler được gọi.

Logout, session invalidation, session fixation, remember-me cleanup, CSRF và forced reauthentication là những lớp lifecycle khác nhau.

## 5. Tạo trang login chỉ hiển thị thông báo chung

Một cách phổ biến trong Spring MVC + Thymeleaf là cấu hình:

~~~java
@Controller
class LoginPageController {
    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

Đoạn trên cần imports Spring MVC. Tạo template `src/main/resources/templates/login.html`:

~~~html
<!DOCTYPE html>
<html lang="vi"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}" role="alert">
        Không thể đăng nhập với thông tin vừa cung cấp.
        Vui lòng thử lại hoặc sử dụng chức năng khôi phục tài khoản.
    </p>

    <form th:action="@{/login}" method="post">
        <label>
            Tên đăng nhập
            <input type="text" name="username" autocomplete="username">
        </label>
        <label>
            Mật khẩu
            <input type="password" name="password"
                   autocomplete="current-password">
        </label>
        <button type="submit">Đăng nhập</button>
    </form>

    <a th:href="@{/forgot-password}">Quên mật khẩu?</a>
</body>
</html>
~~~

Thymeleaf tích hợp Spring MVC/Spring Security thường thêm **CSRF hidden field** cho form POST qua `RequestDataValueProcessor`; hãy xác minh output HTML thực trong app. Nếu không dùng Thymeleaf hoặc không có tích hợp tương ứng, phải truyền CSRF token hợp lệ vào form bằng cách phù hợp. **Không hardcode một token CSRF cố định** và không tắt CSRF chỉ để form chạy.

Nút “Quên mật khẩu?” cần được phục vụ bởi một recovery flow thực đã bảo vệ chống enumeration. Đường dẫn chỉ là ví dụ UI; controller cho `/forgot-password` cần được cấu hình nếu muốn link hoạt động.

### 5.1. Điều kiện hiển thị thông báo

`th:if="${param.error}"` chỉ kiểm tra cờ xuất hiện trong request sau redirect. **Không lấy giá trị `param.error` làm message để hiển thị**: attacker có thể tự tạo `/login?error=<script...>` hoặc chuỗi tùy ý trong URL. Template phải render **một chuỗi cố định do server kiểm soát**, tránh XSS và tránh lộ exception.

Vì query string `?error` có thể được truy cập trực tiếp, giao diện nói “đăng nhập không thành công” khi có cờ này **không phải chứng cứ một lần login thật vừa xảy ra**. Mọi audit/lockout/rate limit phải dựa trên sự kiện server-side của authentication, không dựa vào việc trang `GET /login?error` được xem.

### 5.2. Những trường không nên hiển thị

Không in:

~~~text
"Không tìm thấy user linh"
"User linh có thật nhưng mật khẩu chưa đúng"
"Tài khoản đang bị khóa cho đến 15:30"
"Email này đã đăng ký và chưa xác minh"
"SQL timeout ở bảng account_credentials"
"BadCredentialsException: ..."
~~~

Các thông tin này hoặc tiết lộ sự tồn tại/trạng thái account, hoặc tiết lộ hạ tầng. Sau khi người dùng đã chứng minh quyền sở hữu bằng recovery/MFA hoặc một phiên đáng tin, hệ thống có thể có **luồng hướng dẫn riêng**, nhưng không tự đưa các chi tiết đó vào màn hình đăng nhập công khai.

### 5.3. Thông điệp an toàn nhưng vẫn hữu ích

Một câu gợi ý:

> Không thể đăng nhập với thông tin vừa cung cấp. Vui lòng kiểm tra thông tin và thử lại hoặc sử dụng chức năng khôi phục tài khoản.

Nó không xác nhận tài khoản có tồn tại, không nói sai chắc chắn mật khẩu, và cung cấp hành động tiếp theo. Tránh viết “username này không tồn tại, hãy đăng ký” trước khi có bằng chứng sở hữu. Thông điệp support hoặc thử lại sau khi dịch vụ lỗi cũng nên giữ mức tiết lộ phù hợp.

## 6. Giấu sự tồn tại của tài khoản ở tầng provider và tầng UI

Một handler chỉ chặn hiển thị exception là **cần nhưng chưa đủ**. Phải kiểm tra từ database lookup đến response ngoài.

### 6.1. DaoAuthenticationProvider và UsernameNotFoundException

`AbstractUserDetailsAuthenticationProvider` có cấu hình `hideUserNotFoundExceptions` mặc định **`true`**. Trong luồng mặc định, account không tồn tại và password sai thường đều dẫn đến **`BadCredentialsException`** ở tầng authentication provider.

~~~java
// KHÔNG nên tắt cờ này chỉ để hiện "không tồn tại username":
provider.setHideUserNotFoundExceptions(false);
~~~

Đây là **phản ví dụ**, không phải lời khuyên. Khi đặt `false`, `UsernameNotFoundException` có thể được báo ra cho phần gọi, làm tăng nguy cơ phân biệt account có/không nếu các thành phần phía trên xử lý khác nhau.

Vẫn cần test với provider/custom `UserDetailsService` thật: một custom handler hoặc controller có thể lộ account dù provider mặc định đã che tên exception.

### 6.2. Ba tình huống nên có public outcome tương đương

| Tình huống nội bộ | Điều người dùng nên thấy ở form login public | Điều vận hành có thể ghi nhận |
|---|---|---|
| Username không tồn tại | Một thông điệp thất bại chung | Sự kiện login failure, reason class được phân loại an toàn |
| Username tồn tại, password sai | **Cùng thông điệp**, cùng kiểu URL/status | Bad credentials, rate-limit signals |
| Username tồn tại nhưng disabled/locked | **Không xác nhận trạng thái account** | Account-state reason, compliance/security event |

Một số sản phẩm có cơ chế “tài khoản bị khóa” cần UX riêng. Nếu mức rủi ro cho phép, vẫn không nên xác nhận trạng thái account ở **unauthenticated response**; có thể hướng dẫn chung về recovery. Bước xác thực danh tính thứ hai/khôi phục đáng tin mới là nơi cung cấp hướng dẫn có mục tiêu theo policy.

### 6.3. Đừng để redirect/status khác nhau

Không có tác dụng nếu body chung nhưng:

~~~text
unknown user  -> HTTP 404
wrong pass    -> HTTP 401
locked user   -> HTTP 423

hoặc

unknown user  -> /register?user=linh
wrong pass    -> /login?retry
locked user   -> /support/locked-account
~~~

Kẻ tấn công vẫn có thể phân biệt bằng status, URL, response headers, cookies hoặc kích thước HTML. Với trình duyệt form login, một **failureUrl chung** giúp giảm rủi ro discrepancy factor. Với API 401, body và status chung cũng cần được kiểm tra cùng behavior của endpoint.

Không cố trả `200 OK` cho tất cả tình huống rồi gọi đó là bảo mật: một response 200 với nội dung khác, thời gian khác hoặc cookie khác cũng có thể rò thông tin. Lựa chọn status phải phù hợp giao thức và nhất quán giữa các tình huống muốn che.

### 6.4. Timing side-channel

Giả sử lookup không tìm thấy user thì server trả ngay, còn user có thật phải chạy bcrypt tốn chi phí. Dù URL/body giống nhau, kẻ tấn công có thể thu thập nhiều mẫu và đo latency khác biệt.

Cần kiểm soát **quick exit**, thời gian xác minh, fake password check phù hợp, caching, rate limiting và load variance. Spring Security có biện pháp giảm timing difference trong luồng provider mặc định, nhưng **không hứa timing đồng nhất tuyệt đối**: custom provider, database, tenant lookup, slow hash và policy lockout vẫn có thể tạo kênh phân biệt.

Không dùng `Thread.sleep(500)` tùy tiện cho mọi lỗi như một “giải pháp” đầy đủ: nó dễ gây DoS, không loại bỏ được các nguồn latency khác, và vẫn có thể tạo mẫu phân phối khác nhau. Cần kiểm thử thống kê trong môi trường có tải và phối hợp với phòng chống brute force/credential stuffing.

## 7. Custom failureHandler cho trình duyệt và client JSON

### 7.1. Redirect cố định không lưu exception vào session

Một browser app có thể muốn tự xử lý redirect thay vì dựa vào `SimpleUrlAuthenticationFailureHandler`:

~~~java
@Bean
AuthenticationFailureHandler safeBrowserFailureHandler() {
    return (request, response, exception) -> {
        // Không đưa exception.getMessage() vào URL hay body.
        response.sendRedirect(
                request.getContextPath() + "/login?error");
    };
}
~~~

Đây là **mảnh bean config**, chưa phải chương trình độc lập. Nó không gọi `saveException` nên không tự tạo session chỉ để lưu `AuthenticationException`. Với session đã tồn tại từ lần đăng nhập trước, tùy yêu cầu có thể dọn một error attribute cũ. Tuy nhiên nó không thay thế session/security lifecycle của authentication filter.

Đích redirect được xác định sẵn bởi server, không phải đường URL tùy ý do client gửi. Nếu dùng query `next`/`returnUrl`, cần validation nghiêm ngặt và kiểm tra open redirect.

Áp dụng:

~~~java
http.formLogin(form -> form
    .loginPage("/login")
    .failureHandler(safeBrowserFailureHandler())
    .permitAll());
~~~

Đây là mảnh cấu hình; chỉ dùng một handler policy. Nếu đã chọn `failureHandler` custom, không thêm `failureUrl` ở vị trí khác rồi mong hai cái chạy cộng dồn.

### 7.2. Trả JSON 401 cho login AJAX

Nếu client gửi form bằng JavaScript/fetch và mong một response API, có thể viết:

~~~java
@Bean
AuthenticationFailureHandler safeJsonFailureHandler() {
    return (request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json");

        response.getWriter().write(
            "{\"error\":\"Không thể đăng nhập với thông tin vừa cung cấp.\"}");
    };
}
~~~

Đây là mảnh bean Spring. Nó **không trả nội dung exception**, cùng response cho những loại lỗi authentication cần che. Nếu có request/response wrappers hoặc JSON schema chuẩn, dùng encoder serializer phù hợp thay vì ghép string từ dữ liệu động.

Với **SPA trên cùng origin dùng session cookie**, vẫn cần CSRF protection phù hợp cho request thay đổi trạng thái, kể cả endpoint login theo policy. CORS không thay thế CSRF, và 401 do handler không có nghĩa mọi lỗi 403 CSRF được chuyển thành 401.

### 7.3. Nên chọn redirect hay JSON?

| Client | Cách phản hồi thường hợp lý | Điểm cần test |
|---|---|---|
| Browser gửi HTML form truyền thống | Redirect `/login?error`, sau đó GET login page | CSRF hidden input, cờ error cố định, URL không lộ account |
| Client dùng fetch/XHR | `401` JSON có schema cố định | Content type/encoding, credentials/cookie, không nhận HTML redirect ngoài ý muốn |
| Mobile app dùng API riêng | JSON/status theo contract | Authentication mechanism có thể không phải form login |
| API resource server bearer JWT | Thường dùng entry point theo bearer protocol, **không phải formLogin failureHandler** | `WWW-Authenticate`, token error, bảo vệ chi tiết |
| IdP/OIDC login | OAuth2 failure handler/entry point theo flow phù hợp | State/nonce/callback và không nhầm form-login credentials |

Đừng bật cả form login và bearer auth chung một URL/chain mà không có design rõ. Các loại failure có thể đi qua **filter/handler khác nhau**; `formLogin().failureHandler(...)` không quản lý toàn bộ lỗi authentication trong ứng dụng.

## 8. Ví dụ Java 17 chạy được: hai loại failure handler, nhiều ngoại lệ, một thông điệp

Ví dụ dưới đây **không cần chạy Servlet container/Spring Boot**. Nó dùng chính `SimpleUrlAuthenticationFailureHandler` và `AuthenticationFailureHandler` của Spring Security, cùng `MockHttpServletRequest`/`MockHttpServletResponse` từ Spring Test để quan sát response.

Chúng ta mô phỏng:

1. Browser handler redirect `/login?error` khi gặp password sai, account không tồn tại hoặc account disabled.
2. Handler mặc định có `failureUrl` cố định có thể lưu `AuthenticationException` vào session (để trang view dùng), dù **URL công khai không tiết lộ nguyên nhân**.
3. Custom JSON handler trả `401` với body cố định, không đưa exception ra client.
4. Console chỉ in các nhãn tình huống **giúp học**; nhãn này không phải thông điệp gửi cho người dùng.

### 8.1. Cấu trúc project

~~~text
login-failure-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/LoginFailureDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'login-failure-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.3.8'
    implementation 'org.springframework:spring-test:6.1.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.LoginFailureDemo'
}
~~~

Ví dụ cố định một bộ thư viện Spring Security 6.3.8/Spring Framework 6.1.18 để dễ tái lập API của bài. **Không dùng các version ví dụ như khuyến nghị production hiện tại**: hãy theo Spring Boot BOM/phiên bản được hỗ trợ và cập nhật bản vá bảo mật.

### 8.2. Toàn bộ mã Java

Tạo `src/main/java/example/LoginFailureDemo.java`:

~~~java
package example;

import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.WebAttributes;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

public final class LoginFailureDemo {

    private static void browserAttempt(
            String caseName, AuthenticationException failure)
            throws IOException, ServletException {

        SimpleUrlAuthenticationFailureHandler handler =
                new SimpleUrlAuthenticationFailureHandler(
                        "/login?error");

        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/login");
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        handler.onAuthenticationFailure(request, response, failure);

        System.out.println(caseName + " redirect -> "
                + response.getRedirectedUrl());

        boolean exceptionCached =
                request.getSession(false) != null
                && request.getSession(false).getAttribute(
                        WebAttributes.AUTHENTICATION_EXCEPTION) != null;

        System.out.println(caseName + " session exception -> "
                + exceptionCached);
    }

    public static void main(String[] args) throws Exception {
        // Cùng một URL công khai cho ba lý do lỗi nội bộ.
        browserAttempt(
                "bad password",
                new BadCredentialsException("wrong password"));
        browserAttempt(
                "unknown account",
                new UsernameNotFoundException("unknown username"));
        browserAttempt(
                "disabled account",
                new DisabledException("account disabled"));

        // JSON response riêng, không lộ loại exception.
        AuthenticationFailureHandler genericJson =
                (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"error\":\"Đăng nhập không thành công\"}");
        };

        MockHttpServletRequest jsonRequest =
                new MockHttpServletRequest("POST", "/login");
        MockHttpServletResponse jsonResponse =
                new MockHttpServletResponse();

        genericJson.onAuthenticationFailure(
                jsonRequest, jsonResponse,
                new UsernameNotFoundException("user absent"));

        System.out.println("json status -> "
                + jsonResponse.getStatus());
        System.out.println("json content type -> "
                + jsonResponse.getContentType());
        System.out.println("json body -> "
                + jsonResponse.getContentAsString());
    }
}
~~~

### 8.3. Chạy và stdout

Nếu project đã có Gradle Wrapper tương thích:

~~~bash
./gradlew run
~~~

Nếu chỉ có Gradle cài sẵn, dùng `gradle run`; trên Windows PowerShell có wrapper, dùng `.\gradlew.bat run`.

Các dòng do `System.out.println` in ra (không gồm log Gradle):

~~~text
bad password redirect -> /login?error
bad password session exception -> true
unknown account redirect -> /login?error
unknown account session exception -> true
disabled account redirect -> /login?error
disabled account session exception -> true
json status -> 401
json content type -> application/json;charset=UTF-8
json body -> {"error":"Đăng nhập không thành công"}
~~~

### 8.4. Giải thích đầu ra

- Ba lần gọi `onAuthenticationFailure` với ba subclass exception khác nhau đều dùng **một `defaultFailureUrl` cố định**, nên `getRedirectedUrl()` trùng nhau. Console in `caseName` để phân biệt **trong demo**, nhưng browser chỉ nhận URL chung.
- `SimpleUrlAuthenticationFailureHandler` với redirect và mặc định cho phép tạo session sẽ lưu exception ở `WebAttributes.AUTHENTICATION_EXCEPTION`. Vì thế các dòng `session exception` là true. Đây là lý do không nên render trực tiếp exception message trong template.
- Custom JSON handler nhận `UsernameNotFoundException` nhưng **không đọc nó để sinh body**, nên status 401 và message luôn chung. Khi nhận `BadCredentialsException` hay `DisabledException` theo cùng handler, body cũng được tạo cố định.
- Không có password hash, `AuthenticationManager`, provider hoặc account database trong demo. Đây là **mô phỏng thất bại sau khi filter đã xác định lỗi**, không kiểm chứng mức độ an toàn của toàn bộ login flow.

**Lưu ý:** kết quả ví dụ dựa trên API/behavior của bộ thư viện đã pin; body/status thực tế khi chạy qua Servlet container thật còn chịu ảnh hưởng của filter chain, proxy, failure handler khác và exception mapping. Để kiểm tra hệ thống, phải có integration tests với form login thật.

## 9. Tích hợp đầy đủ vào Spring Boot: chọn một failure policy

### 9.1. Cấu hình Browser form login

~~~java
@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/forgot-password", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .failureUrl("/login?error")
                .permitAll());
        return http.build();
    }
}
~~~

Đây là **mảnh code trong ứng dụng Spring Boot Servlet**, không biên dịch độc lập. Cần `@Configuration`/`@Bean`, các imports, `UserDetailsService`/provider và controller/template GET /login. `/forgot-password` chỉ là đường dẫn dự kiến; nếu chưa có recovery controller, cần triển khai nó hoặc bỏ link khỏi UI.

### 9.2. Một SecurityFilterChain khác cho login qua AJAX

Nếu ứng dụng cần login dạng JSON, nên xác định ranh giới riêng:

~~~java
@Bean
SecurityFilterChain apiLoginSecurity(
        HttpSecurity http,
        AuthenticationFailureHandler safeJsonFailureHandler)
        throws Exception {

    http
        .securityMatcher("/api/login/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll())
        .formLogin(form -> form
            .loginProcessingUrl("/api/login/session")
            .failureHandler(safeJsonFailureHandler));

    return http.build();
}
~~~

Đoạn này **chỉ minh họa cách gắn failure handler vào một chain**, chưa xử lý JSON request body, CSRF strategy, session policy và thứ tự `@Order` của nhiều chain. `UsernamePasswordAuthenticationFilter` mặc định đọc **form parameters**, không tự parse arbitrary JSON payload; muốn gửi JSON phải dùng authentication converter/filter phù hợp. Đừng copy đoạn này làm “JSON login hoàn chỉnh” khi chưa triển khai cơ chế đọc credential.

**Cảnh báo:** nếu app có cả Web chain fallback và API chain hẹp, phải đặt `@Order` phù hợp và kiểm tra `POST /api/login/session` nằm trong API chain, nếu không failure handler API có thể không bao giờ được gọi.

### 9.3. Lựa chọn một handler rõ ràng

Trong một chain, nên chọn **một** trong các cách:

~~~java
form.failureUrl("/login?error");
~~~

hoặc:

~~~java
form.failureHandler(safeBrowserFailureHandler);
~~~

hoặc:

~~~java
form.failureHandler(safeJsonFailureHandler);
~~~

Ba câu là **alternatives**, không dùng như một chuỗi cấu hình tuần tự. Nếu yêu cầu thông điệp chung và redirect về trang login, `failureUrl` thường là lựa chọn đủ tốt. Viết custom handler khi cần policy response cụ thể có giá trị rõ ràng.

## 10. AuthenticationFailureHandler khác các handler lỗi khác như thế nào?

Không phải mọi lỗi được trả trong quá trình bảo vệ HTTP đều đi qua `formLogin().failureHandler`.

| Cơ chế / lỗi | Thành phần có thể xử lý | Vì sao khác form login failure? |
|---|---|---|
| `POST /login` credentials sai | `UsernamePasswordAuthenticationFilter` → `AuthenticationFailureHandler` | Đúng phạm vi form-login failure |
| `GET /private` chưa đăng nhập | `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | Đây là request vào URL được bảo vệ, không phải login attempt thất bại |
| Principal đã login nhưng thiếu quyền | `AccessDeniedHandler` | Authorization failure, không phải bad credentials |
| `POST /login` thiếu CSRF | `CsrfFilter`/access denied handling | Có thể bị chặn trước auth filter |
| HTTP Basic sai | `BasicAuthenticationFilter`/Basic auth entry point | Cơ chế auth khác, có protocol challenge |
| Bearer token sai/hết hạn | `BearerTokenAuthenticationFilter`/Bearer entry point | Theo OAuth2 Bearer protocol |
| OIDC/OAuth2 login callback thất bại | OAuth2 authentication filter failure handler | Khác filter/protocol form username/password |
| Spring MVC controller ném exception | `@ControllerAdvice` / Spring MVC error handling | Không tự rẽ về formLogin failureHandler |
| DB outage/JWK service outage | Hạ tầng/provider và exception mapping cụ thể | Cần xử lý fail-closed, alert; không để lỗi bị che mất vận hành |

Không áp dụng mặc định `ExceptionMappingAuthenticationFailureHandler` để redirect các account state tới trang khác nhau, vì `DisabledException`/`LockedException` có thể tạo discrepancy factor. Nếu cần recovery UX riêng, thiết kế bước chứng minh danh tính trước khi công khai chi tiết.

### 10.1. Đừng nhầm 401 và 403

- **401 Unauthorized** (tên HTTP hơi gây hiểu lầm): thông thường cần/vừa thất bại authentication, có thể kèm challenge.
- **403 Forbidden**: thường đã bị từ chối quyền hoặc bị protection filter như CSRF chặn; cũng phụ thuộc cách filter/entry point được cấu hình.
- **302 redirect** đến login page: dạng phổ biến với HTML browser flow.

Status một mình không nói chắc password sai, account tồn tại hay authorization thiếu; phải xem **filter/exception source** thực. Với UI chống enumeration, so sánh cả **status và redirect/body/headers/timing** giữa các tình huống account khác nhau.

## 11. Tránh account enumeration trên toàn bộ hành trình người dùng

Một trang login có thông điệp chung vẫn có thể bị lộ account ở endpoint lân cận:

### 11.1. Registration và forgot password

Ví dụ một ứng dụng trả:

~~~text
POST /register: "Email đã tồn tại"
POST /forgot: "Không tìm thấy tài khoản này"
POST /login: "Đăng nhập thất bại"
~~~

Kẻ tấn công chỉ cần gọi `/forgot` thay vì `/login` để liệt kê account. Cần một chính sách disclosure thống nhất theo threat model trên **login, reset, registration, recovery và MFA enrollment**, đồng thời tối ưu UX cho người dùng hợp lệ qua những kênh đã xác minh.

Với reset request, thông điệp chung như “Nếu tài khoản phù hợp tồn tại, chúng tôi sẽ gửi hướng dẫn” là phương án phổ biến. Nhưng phải bảo vệ cả thời gian phản hồi, rate limit, email sending/notification side effects và không tiết lộ reset token.

### 11.2. Rate limiting không được trở thành nguồn leak

Nếu account có thật bị khóa công khai sau N lần sai trong khi account không tồn tại chỉ nhận thông báo khác, lockout trở thành oracle xác nhận account. Dùng thông điệp chung, nội bộ vẫn áp dụng ngưỡng throttle/risk scoring theo username đã chuẩn hóa, network/IP, device/rate window phù hợp.

Cẩn trọng với việc cố định theo IP đơn thuần vì NAT/mobile users có thể bị ảnh hưởng; cũng tránh khóa account vĩnh viễn chỉ vì attacker biết username và chủ động gây denial-of-service. Rate limiting là **phòng vệ bổ sung**, không thay password hashing/MFA/monitoring.

### 11.3. MFA và trạng thái account nhạy cảm

Một câu “Bạn đã nhập đúng mật khẩu nhưng phải bật MFA” chỉ nên được cung cấp **sau khi bước password đã được xác minh đúng** và flow tương ứng được bảo vệ. Không xác nhận tài khoản nào có MFA ở bước username-only nếu không có cơ sở bảo mật. Hạn chế log nội dung challenge/token và tránh redirect chứa secret.

### 11.4. Timing khó kiểm soát hoàn toàn

Phép so sánh public response phải bao gồm tình huống:

- Username không tồn tại.
- Username tồn tại, password sai.
- Username tồn tại, disabled/locked.
- Có/không có cache hit.
- DB chậm hoặc không sẵn sàng.
- Tốc độ hash password khác nhau theo cost/algorithm.
- Rate limiting và email/notification async.

Mục tiêu là giảm khả năng phân biệt có ý nghĩa thống kê và tốc độ thu thập; không đặt yêu cầu phi thực tế “mọi request phải đúng 200 ms”. Bảo vệ nhiều lớp và đo trên môi trường gần production.

## 12. Logging, audit và dữ liệu nhạy cảm

### 12.1. Ghi thông tin gì cho vận hành?

Có thể ghi audit events được chuẩn hóa, chẳng hạn:

~~~json
{
  "event": "AUTH_LOGIN_FAILURE",
  "requestId": "opaque-correlation-id",
  "authMethod": "form",
  "result": "DENIED",
  "reasonCode": "BAD_CREDENTIALS_GENERIC",
  "clientBucket": "rate-limiter-key-redacted"
}
~~~

Đây là **ví dụ schema**, không phải output từ app cụ thể. Nếu vận hành cần phân loại `ACCOUNT_DISABLED` hoặc `SERVICE_UNAVAILABLE` để cảnh báo, chỉ đưa vào kênh **nội bộ bảo vệ**, hạn chế retention/quyền đọc và chống label cardinality. Không bắt buộc luôn ghi username/email nguyên văn, và không dùng raw username do client gửi làm log field chưa qua sanitization.

**Không log:** raw password, `Authorization` header, session cookie, CSRF token, reset token, bearer JWT, encoded password hash, nguyên nội dung `AuthenticationException` nếu có thể chứa dữ liệu nhạy cảm, hoặc object `Authentication` không được redaction.

### 12.2. Có thể gửi exception vào metrics không?

Tránh lấy `exception.getMessage()` làm metrics label: chuỗi có thể không ổn định, chứa dữ liệu nội bộ và tạo cardinality cao. Dùng **enum reason codes** theo danh sách cho phép, ví dụ `AUTH_BAD_CREDENTIALS`, `AUTH_ACCOUNT_STATE`, `AUTH_INFRASTRUCTURE_ERROR`.

Telemetry cần cho phép xem tỷ lệ thất bại login, spikes password spraying, error rate `AuthenticationServiceException`, latency và recovery requests, nhưng không trở thành công cụ dò danh tính cho người không được phép.

### 12.3. Quan hệ với HttpSession

Nếu handler redirect có lưu exception trong session, dữ liệu có vòng đời riêng với `SecurityContext`, remember-me hoặc CSRF token. Đừng đưa `WebAttributes.AUTHENTICATION_EXCEPTION.message` vào trang public, dù session được mã hóa hoặc cookie HttpOnly. Ngay cả khi người dùng không đọc được session server-side, **template của ứng dụng vẫn có thể tiết lộ nó**.

## 13. Ma trận kiểm thử chức năng và bảo mật

| Tình huống | Hành vi public cần kiểm tra | Kiểm tra nội bộ |
|---|---|---|
| Password sai cho account có thật | `/login?error`, thông điệp chung | Provider/encoder từ chối đúng |
| Username không tồn tại | **Cùng redirect/body/status** | Không leak `UsernameNotFoundException` |
| Account disabled | **Không tiết lộ trạng thái** | Account status được ghi nhận an toàn |
| Account locked | Public behavior chung | Lockout/rate limiting không mở enumeration |
| Account expired | Thông điệp chung | Chính sách recovery riêng |
| Password expired | Không lộ trước bước xác minh cần thiết | Flow đổi mật khẩu an toàn |
| DB outage/infra failure | Không stacktrace, không login thành công | Error/alert vận hành đủ rõ |
| `GET /login` không có error flag | Render form bình thường | Không tự ghi login failure event |
| `GET /login?error` truy cập trực tiếp | Hiện message cố định, không dùng giá trị query | Không coi nó là login attempt |
| `GET /login?error=USER_NOT_FOUND` | Vẫn message cố định | Không parse reason từ client |
| POST thiếu CSRF | Không được chấp nhận login | CSRF filter xử lý trước failure handler nếu cấu hình |
| POST đúng CSRF nhưng credentials sai | Form failure handler chạy | Session/exception handling đúng |
| GET error page trên mobile/JS | Không redirect loop | Client biết cách xử lý HTTP |
| Browser redirect mode | Location cùng URL giữa các loại lỗi | Không đưa username/exception vào query |
| JSON handler mode | `401` body/schema giống nhau | Content type/UTF-8 chuẩn |
| FailureUrl không được set | Không mặc định để exception message ra public | Kiểm tra SimpleUrl default response |
| Handler redirect có session | Không render `AUTHENTICATION_EXCEPTION` | Session attribute được quản lý đúng |
| Multiple `SecurityFilterChain` | POST /login vào đúng chain | `@Order` và matcher phù hợp |
| Custom form parameter names | Filter đọc đúng username/password | Mismatch không bị chẩn đoán sai thành account thiếu |
| CSRF/session cookie bị mất | Giao diện có hướng dẫn hợp lý | Secure/SameSite/Path/cookie proxy config |
| Login đúng | Không đi qua failure handler | Authentication vào context sau verify |
| Bypass thử username enumeration | Không phân biệt hữu ích qua status/body/redirect | Timing/rate limit/headers được đo |
| Forgot password/registration | Không rò account qua endpoint khác | Chính sách disclosure thống nhất |
| Thử open redirect với returnUrl | Không redirect ra domain attacker | URL chỉ từ allowlist/safe relative paths |
| BadCredentialsException có message nhạy cảm | Không xuất nguyên message | Logs/metrics được redaction |
| Retry/credential stuffing nhiều lần | Không gây brute-force vô hạn | Rate limiting, detection, MFA |
| Test qua proxy/container thật | Public behavior không khác local | Headers/redirect path đúng context |
| Thử ERROR/ASYNC dispatch | Không chạy handler nhiều lần ngoài thiết kế | Dispatcher/filter lifecycle đúng |

### 13.1. MockMvc integration tests minh họa

Trong một dự án Spring Boot đã có `spring-security-test`, có thể kiểm thử:

~~~java
mockMvc.perform(post("/login")
        .with(csrf())
        .param("username", "known-user")
        .param("password", "wrong-password"))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/login?error"));
~~~

Đây là **mảnh test**, không biên dịch độc lập. Cần có test fixture account hợp lệ nhưng password sai, imports `MockMvcRequestBuilders.post`, `SecurityMockMvcRequestPostProcessors.csrf`, status/redirect result matchers và app security chain.

Thêm một test với username không tồn tại, so sánh cùng redirect; thêm account disabled/locked nếu policy yêu cầu. Với custom JSON handler, test status 401 và body cố định. Để nhận diện timing leakage, cần một test/instrumentation có kiểm soát thống kê nhiều request, không dùng một lần `System.nanoTime()` để chứng minh an toàn.

### 13.2. Cần kiểm thử response từ phía trình duyệt

Integration test phải kiểm tra **cái client quan sát** chứ không chỉ method handler đã được gọi:

- HTTP status và `Location` header.
- HTML form có CSRF token đúng, password input không bị prefill với secret.
- Chỉ có một thông điệp cố định, không nhúng exception message.
- Content-Type và character encoding của JSON.
- Cache headers khi hiển thị thông tin nhạy cảm.
- Không có username/password/exception trong query, cookie, redirect hay response body.
- Có kiểm soát brute-force, credential stuffing và monitoring.

Đặc biệt, `MockMvc` không thay thế hoàn toàn HTTP test qua proxy, container, reverse proxy URL rewriting và cookie security thực tế.

## 14. Các lỗi triển khai phổ biến

**Lỗi 1 — Hiển thị nguyên `exception.getMessage()`.**  
Có thể tiết lộ username tồn tại, trạng thái account và chi tiết hạ tầng. Render message cố định.

**Lỗi 2 — Redirect khác nhau cho từng `AuthenticationException`.**  
Kẻ tấn công phân biệt `UsernameNotFoundException`, `LockedException` hay `BadCredentialsException` qua `Location`. Dùng public outcome chung hoặc một flow recovery đã xác minh.

**Lỗi 3 — Tưởng `failureUrl` và `failureHandler` sẽ chạy cộng dồn.**  
`failureUrl` là shortcut cho handler; chọn chính sách response rõ và test configuration cuối.

**Lỗi 4 — Cấu hình `failureUrl` nhưng không có GET /login.**  
Browser đi đến 404 hoặc custom error. Cần controller/template và permitAll.

**Lỗi 5 — `POST /login` nằm ngoài `securityMatcher`.**  
Authentication filter không xử lý POST. Kiểm tra selected chain và login processing URL.

**Lỗi 6 — Tắt CSRF vì login POST trả 403.**  
Đây có thể là thất bại của CSRF protection, không phải của password provider. Sửa form token.

**Lỗi 7 — Trả 200 với HTML khác nhau theo account state.**  
Status giống không che khác biệt body/size/cookie/timing.

**Lỗi 8 — Cho API dùng AJAX nhận redirect HTML bất ngờ.**  
Client không xử lý được, có thể tạo login loop. Chọn 401 JSON handler riêng nếu API contract yêu cầu.

**Lỗi 9 — Dùng `exception.getClass().getSimpleName()` làm reason công khai.**  
Dù không có message, tên exception vẫn có thể leak account state.

**Lỗi 10 — Giữ `setHideUserNotFoundExceptions(false)` vì “UX tốt hơn”.**  
Làm tăng khả năng phân biệt account, đặc biệt nếu handler/controller thay response.

**Lỗi 11 — Quên timing side-channel.**  
Quick exit khi user không tồn tại có thể rò account dù message chung. Thiết kế provider, KDF, rate limits và test phù hợp.

**Lỗi 12 — Lấy `/login?error` làm audit evidence.**  
Anyone có thể mở URL đó; event thất bại phải do server-side authentication attempt tạo.

**Lỗi 13 — Log raw credentials khi authentication fails.**  
Một log leak có thể dẫn đến account takeover. Chỉ log dữ liệu đã tối thiểu hóa và redaction.

**Lỗi 14 — Để custom failure handler tự tạo authenticated token để “giữ user”.**  
Authentication thất bại không được biến thành session tin cậy. Handler chỉ xử lý response/an toàn audit.

**Lỗi 15 — Dùng open redirect trong `failureHandler`.**  
Không tin đường `returnUrl`/`next` do client gửi, dùng target cố định hoặc whitelist relative URLs.

**Lỗi 16 — Coi `formLogin().failureHandler` xử lý cả Basic/JWT/OIDC.**  
Mỗi cơ chế có filter/entry point/handler khác; test riêng.

**Lỗi 17 — Không kiểm soát Session exception sau redirect.**  
Thường `SimpleUrlAuthenticationFailureHandler` lưu exception cho view; đừng render hoặc giữ dữ liệu không cần thiết.

**Lỗi 18 — Hễ login lỗi đều đưa về “đăng ký tài khoản mới”.**  
Nếu username có thật nhưng user nhập sai password, gợi ý này vừa không chính xác vừa có thể tạo các luồng xác nhận account. Dùng hướng dẫn chung về kiểm tra thông tin hoặc recovery.

## 15. Câu hỏi ôn tập và checklist production

### 15.1. Câu hỏi tự kiểm tra

**Câu 1.** `failureUrl("/login?error")` có phải code xác minh password không?  
**Trả lời:** Không. Nó cấu hình phản hồi sau khi authentication filter/provider đã báo thất bại.

**Câu 2.** `failureHandler` có thể trả JSON 401 thay redirect không?  
**Trả lời:** Có. Nó điều khiển `HttpServletResponse` của authentication failure event; phải tránh lộ exception detail.

**Câu 3.** Account không tồn tại và password sai có nên trả hai URL khác nhau không?  
**Trả lời:** Không trong login public cần chống account enumeration; cùng public outcome là an toàn hơn.

**Câu 4.** `SimpleUrlAuthenticationFailureHandler` có thể lưu exception trong session không?  
**Trả lời:** Có, khi redirect/forward theo cấu hình; redirect thường lưu vào session nếu có/được phép tạo. View không được đưa chi tiết đó ra public.

**Câu 5.** `POST /login` thiếu CSRF có chắc gọi failure handler không?  
**Trả lời:** Không. `CsrfFilter` có thể chặn trước filter form login, thường là 403.

**Câu 6.** `hideUserNotFoundExceptions` mặc định trong provider dạng DAO được dùng để làm gì?  
**Trả lời:** Giúp không phân biệt rõ unknown username với wrong password qua exception type mặc định; không loại bỏ mọi side-channel.

**Câu 7.** Có thể tránh enumeration chỉ bằng thông điệp HTML chung không?  
**Trả lời:** Không. Kiểm tra status, URL, headers, cookies, response length, timing, registration/reset flows và rate limits.

**Câu 8.** Người dùng thấy `/login?error` có nghĩa chắc chắn họ vừa nhập sai mật khẩu?  
**Trả lời:** Không. Cờ error có thể được tự thêm vào URL, và các loại failure nội bộ không phải lúc nào cũng là password sai.

**Câu 9.** Form login handler có nhận lỗi JWT signature không?  
**Trả lời:** Không mặc định. Bearer token được xử lý bởi resource server filter và entry point riêng.

**Câu 10.** Custom handler có nên ghi username và raw password vào log để debug không?  
**Trả lời:** Không. Chỉ log các security events có kiểm soát và tránh credential secrets.

### 15.2. Checklist áp dụng

- [ ] `UsernamePasswordAuthenticationFilter` nhận đúng `POST loginProcessingUrl` trong đúng `SecurityFilterChain`.
- [ ] Authentication được quyết định bởi `AuthenticationManager`/provider, không tạo trusted principal từ raw input.
- [ ] GET login page và POST login processing URL có mapping/permitAll phù hợp.
- [ ] Chọn **một** cách xử lý failure: `failureUrl` hoặc custom `failureHandler` theo client contract.
- [ ] Trang login dùng message **cố định**, không render `AuthenticationException.message` hay query value làm nội dung.
- [ ] Unknown username, wrong password, disabled/locked có public outcome không dễ phân biệt.
- [ ] Kiểm tra cả status, redirect URL, headers, cookies, body, length và timing.
- [ ] DaoAuthenticationProvider không tự nới lộ `UsernameNotFoundException` không cần thiết.
- [ ] Duy trì CSRF protection phù hợp với browser login; không gộp CSRF failure vào auth failure vô điều kiện.
- [ ] Với AJAX, trả JSON status/schema nhất quán; không redirect HTML ngoài ý muốn.
- [ ] Không dùng URL/exception detail từ client làm open redirect hoặc log uncontrolled.
- [ ] Có rate limiting, credential stuffing detection, MFA khi phù hợp và password hashing an toàn.
- [ ] Reset/registration/recovery cũng có chính sách chống account enumeration.
- [ ] Quản lý `WebAttributes.AUTHENTICATION_EXCEPTION` trong session và không hiển thị nó công khai.
- [ ] Quan sát lỗi thật qua metrics/audit nội bộ được phân quyền, không đưa account reasons ra public.
- [ ] Có MockMvc/integration/E2E tests với provider và security chain thực, kể cả user không tồn tại/disabled.
- [ ] Kiểm tra lỗi hạ tầng không vô tình trở thành “đăng nhập thành công” hoặc stacktrace public.
- [ ] Khi thay version Spring Security, đối chiếu JavaDoc của `AbstractAuthenticationFilterConfigurer` và `SimpleUrlAuthenticationFailureHandler`.

**Ghi nhớ:** `failureUrl` và `AuthenticationFailureHandler` quyết định **cách trả lời khi xác thực thất bại**, không quyết định account có thật hay password có đúng. Giao diện phải dùng thông báo chung và không tiết lộ `AuthenticationException`, đồng thời cả provider, timing, rate limits, recovery và các HTTP response khác cũng phải giữ được ranh giới chống **account enumeration**.

### Tài liệu chính thức

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): login page, form POST, CSRF token và tham số `error`.
- [Spring Security — AbstractAuthenticationFilterConfigurer JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): `failureUrl`, `failureHandler` và default redirect.
- [Spring Security — SimpleUrlAuthenticationFailureHandler JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html): redirect/forward, status khi thiếu URL và `saveException`.
- [Spring Security — AuthenticationFailureHandler JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): `onAuthenticationFailure`.
- [Spring Security — AbstractUserDetailsAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `hideUserNotFoundExceptions`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): provider, `UserDetailsService` và `PasswordEncoder`.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication error messages, discrepancy factors và timing.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): account enumeration và password reset an toàn.
- [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): rate limiting, threat signals và defenses.
