# logoutUrl, HTTP method và yêu cầu CSRF của thao tác đăng xuất

> **Phạm vi học:** Spring Security **Servlet stack**, Java 17+, Spring Boot 3.x và Spring Security 6.x. Trọng tâm là cấu hình `logoutUrl`, HTTP method thực sự được phép tạo sự kiện đăng xuất, vai trò của `CsrfFilter` và cách kiểm thử để **GET không làm thay đổi trạng thái xác thực**, **POST không có CSRF token hợp lệ không được phép logout**, còn **POST đúng token thì xóa phiên/ngữ cảnh bảo mật theo chính sách**. Ví dụ Spring cần một dự án Boot với đúng dependencies; có một chương trình Java 17 độc lập ở cuối để luyện tập quy tắc.

## 1. Vì sao một nút “Đăng xuất” lại là vấn đề bảo mật?

Trong ứng dụng Servlet sử dụng form login và `HttpSession`, một lần đăng nhập thành công thường lưu `SecurityContext` để các request tiếp theo đi kèm cookie phiên có thể được nhận diện là đã xác thực. Đăng xuất là thao tác **thay đổi trạng thái**: làm mất authentication, có thể hủy phiên, dọn cookie/token và dẫn người dùng về trang phù hợp.

Nếu ứng dụng cho phép đăng xuất chỉ bằng `GET /logout`, một website bên ngoài có thể khiến trình duyệt của người dùng đang đăng nhập tự tải URL đó (qua link, ảnh, chuyển hướng hoặc nội dung nhúng, tùy chính sách trình duyệt). Người dùng bị buộc đăng xuất mà không chủ động yêu cầu. Đây là một dạng **logout CSRF**; thường tác động tới tính sẵn sàng/trải nghiệm và có thể trở nên nghiêm trọng hơn trong các flow có thay đổi tài khoản hoặc gây nhầm lẫn xác thực.

Ví dụ rủi ro:

~~~html
<!-- Ví dụ hành vi cần NGĂN, không phải cách triển khai logout -->
<img src="https://app.example.test/logout" alt="">
~~~

`GET` nên mang ý nghĩa **đọc tài nguyên**; một GET chỉ để xem trang xác nhận đăng xuất không nên tự hủy phiên. Với website dựa vào cookie, nguyên tắc an toàn phổ biến là **logout bằng POST có CSRF token hợp lệ**.

Lưu ý: CSRF không phải biện pháp chống mọi vấn đề về session. Nó không thay HTTPS, cookie `Secure`/`HttpOnly`, phòng chống XSS, session fixation, giới hạn phiên, quản lý token ngoài hệ thống hay xử lý refresh token của nhà cung cấp danh tính.

## 2. Ba cấu hình cần phân biệt

Trong `HttpSecurity.logout(...)` của Spring Security:

- `logoutUrl("/signout")`: xác định **đường dẫn mà LogoutFilter xử lý để thực hiện đăng xuất**, không phải đường dẫn chuyển đến sau đăng xuất.
- `logoutSuccessUrl("/login?logout")`: xác định **đích điều hướng sau một logout thành công**; thuộc response, không kích hoạt logout.
- `logoutRequestMatcher(...)`: thay cơ chế nhận diện logout request, bao gồm method/đường dẫn; đây là cấu hình nâng cao cần cực kỳ cẩn thận để không nhận thêm HTTP method không mong muốn.

Ví dụ cơ bản:

~~~java
http.logout(logout -> logout
    .logoutUrl("/signout")
    .logoutSuccessUrl("/login?logout")
    .permitAll());
~~~

Với một ứng dụng dùng session và **CSRF đang bật** theo cấu hình tiêu chuẩn, `POST /signout` với token hợp lệ là hành động logout; chỉ truy cập `GET /signout` **không** có nghĩa đã logout. Không đánh đồng `logoutUrl` với `logoutSuccessUrl`.

| Tùy chọn | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| `logoutUrl` | Request nào kích hoạt logout? | `POST /signout` khi CSRF bật và matcher mặc định tương ứng. |
| `logoutSuccessUrl` | Thành công thì trình duyệt đi đâu? | `/login?logout`. |
| `logoutSuccessHandler` | Muốn custom response sau logout? | Trả 204 cho một SPA/API thay vì 302. |
| `logoutRequestMatcher` | Muốn kiểm soát matching theo path/method đặc biệt? | Chỉ match `POST /signout`. |
| `invalidateHttpSession` | Có hủy `HttpSession` hiện tại? | Thường bật cho stateful form login. |
| `clearAuthentication` | Có xóa `Authentication` trong context? | Thường bật. |
| `deleteCookies` | Có phát yêu cầu xóa cookie được chỉ định? | Chỉ là một phần cookie cleanup; path/domain phải phù hợp. |

**Chú ý:** method và hành vi matching của `logoutUrl` phụ thuộc cấu hình CSRF và phiên bản Spring Security. Trong Spring Security 6 Servlet, khi CSRF được bật, matcher logout do configurer tạo thường yêu cầu `POST`; khi CSRF bị tắt, cấu hình mặc định có thể chấp nhận nhiều HTTP method, bao gồm GET. Không coi việc chỉ đổi đường dẫn thành một biện pháp an ninh. Hãy **kiểm thử method thực tế** trên chính security chain đang deploy.

## 3. LogoutFilter nằm ở đâu trong filter chain?

Một request đi qua `FilterChainProxy` và `SecurityFilterChain` tương ứng. Khi request match logout endpoint, `LogoutFilter` là thành phần trung tâm nhận diện và chạy các `LogoutHandler`, sau đó chạy `LogoutSuccessHandler`.

Sơ đồ logic:

~~~text
Trình duyệt giữ cookie JSESSIONID
  |
  | POST /signout + CSRF token hợp lệ
  v
SecurityFilterChain
  |
  | CsrfFilter
  |  -> token missing/sai? 403; KHÔNG đi đến LogoutFilter
  |  -> token đúng? tiếp tục
  |
  v
LogoutFilter
  | match logout URL + HTTP method
  |
  +-- Không match:
  |      chuyển tiếp request trong filter chain
  |
  +-- Match:
         1. Các LogoutHandler dọn state (SecurityContext,
            authentication, HttpSession, CSRF token, ...)
         2. LogoutSuccessHandler tạo response
            ví dụ 302 Location: /login?logout
  |
  v
Trình duyệt nhận redirect / kết quả logout
~~~

**Thứ tự quan trọng:** `LogoutFilter` trong chain tiêu chuẩn xử lý logout trước khi authorization dành cho các controller được xét, vì vậy trang logout không nên phụ thuộc vào một `@PostMapping` trong MVC controller như thể nó là login business logic. Nếu bạn tự làm endpoint logout ở controller mà bỏ qua `LogoutFilter`, bạn phải tự bảo đảm các handler và cơ chế dọn state; cách này dễ thiếu sót.

`CsrfFilter` phải chặn các request không hợp lệ trước khi chúng gây side effect. Đối với `POST /signout`, điều quan trọng là request **đi vào đúng chain có CSRF bật** và không bị `ignoringRequestMatchers(...)` miễn trừ ngoài ý muốn.

### LogoutHandler và LogoutSuccessHandler khác nhau

`LogoutHandler` thực hiện công việc trước response: ví dụ `SecurityContextLogoutHandler` xóa context/authentication, có thể invalidate `HttpSession`, cùng các handler liên quan CSRF/remember-me đã được cấu hình. Handler nên xử lý an toàn, không quăng lỗi bừa bãi làm lộ trạng thái một phần.

`LogoutSuccessHandler` chỉ quyết định HTTP response **sau** chuỗi handler: redirect về `/login?logout`, trả `204 No Content` hoặc một response theo hợp đồng frontend. Không dùng success handler để thay thế dọn session, cũng không lấy `returnUrl`/`next` tùy ý làm redirect để tránh open redirect.

### LogoutFilter không có nghĩa mọi token đều bị thu hồi

Đăng xuất phiên HTTP có thể invalidate session cookie, nhưng một **JWT access token tự chứa** đã phát hành vẫn có thể hợp lệ đến khi hết hạn nếu resource server khác tiếp tục chấp nhận nó và không có cơ chế revocation. Với OAuth2/OIDC, refresh token, SSO session và provider logout, phải thiết kế quy trình riêng nếu cần logout trên nhiều thành phần. Không khẳng định `http.logout(...)` tự thu hồi mọi token ở mọi dịch vụ.

## 4. GET, POST và CSRF: ma trận hành vi

Giả sử:

- Ứng dụng stateful dùng cookie session.
- CSRF bật, không có matcher miễn trừ logout.
- Đăng xuất tùy chỉnh theo `logoutUrl("/signout")` và success URL `/login?logout`.
- Không có MVC controller khác cố tình xử lý `GET /signout`.

| Request | Có CSRF token hợp lệ? | Kỳ vọng bảo mật |
| --- | --- | --- |
| `GET /signout` | Không cần token cho safe GET | **Không đăng xuất**. Có thể 404, trang xác nhận hoặc response theo định tuyến cụ thể. |
| `POST /signout` | Không có | **403** do CSRF, phiên đăng nhập còn hiệu lực. |
| `POST /signout` | Token không hợp lệ | **403**, không chạy logout handlers. |
| `POST /signout` | Token hợp lệ | Chạy logout handlers, thường **302** về `/login?logout` trong cấu hình ví dụ. |
| `PUT /signout` | Không có | Thường bị CSRF chặn nếu không được miễn trừ; không được logout. |
| `DELETE /signout` | Token hợp lệ | Không match method POST mặc định của `logoutUrl` khi CSRF bật; không được logout. |
| `POST /wrong-path` | Token hợp lệ | Không match logout URL; xử lý theo route/authorization khác. |
| `POST /signout` với session không authenticated | Token hợp lệ | Logout handler có thể vẫn hoàn tất và success response; không chứng minh đã có tài khoản đăng nhập trước đó. |

Đây là **ma trận chính sách** cho ví dụ, không phải cam kết status giống hệt ở mọi ứng dụng. Status cho những request **không match logout** phụ thuộc route, dispatcher, entry point và authorization còn lại. Test nên kiểm tra quan trọng nhất: **session chưa bị hủy và context không bị xóa do một GET**.

### GET /logout “trang xác nhận” trong cấu hình mặc định

Khi dùng cấu hình đăng nhập/đăng xuất mặc định và Spring Security có thể sinh trang giao diện mặc định, **`GET /logout` có thể hiển thị trang xác nhận** chứa form POST cùng CSRF token, thay vì thực thi logout ngay. Trường hợp có trang logout tự thiết kế, đã đổi URL, dùng nhiều security chains hoặc tắt thành phần sinh trang mặc định, hành vi GET có thể khác hoặc là 404. Không dựa vào việc mọi app Spring Security đều tự có trang xác nhận GET.

Ví dụ form an toàn về semantics:

~~~html
<form action="/logout" method="post">
  <!-- CSRF hidden field cần được framework/template đưa vào -->
  <button type="submit">Đăng xuất</button>
</form>
~~~

Đoạn HTML trên **chưa đầy đủ cho app CSRF-enabled** nếu không có hidden input chứa CSRF token thực tế. Phần ví dụ Spring Boot bên dưới dùng Thymeleaf để render form token đúng cách.

### Vì sao không chọn GET cho logout?

GET có thể bị prefetch, được trình duyệt tải khi user chỉ xem một liên kết, được nhúng từ website khác hoặc bị crawler chạm tới. Dù ứng dụng có `SameSite` và hạn chế cookie, những biện pháp đó không biến GET thay đổi trạng thái thành một thiết kế đáng tin. Dùng POST + CSRF token vẫn là đường cơ bản cho browser session.

### Có nên cho DELETE logout?

Trong một số REST API, `DELETE /session/current` có thể mang ý nghĩa xóa session. Nhưng đối với giao diện browser dùng **cookie authentication**, DELETE cũng là unsafe method và cần chính sách CSRF tương đương; hơn nữa HTML form không gửi DELETE trực tiếp nếu không có method override. Nếu nghiệp vụ chỉ cần logout, một POST đơn giản nhất quán với Spring Security mặc định thường dễ dùng và dễ kiểm thử hơn.

## 5. CSRF token đến từ đâu?

**CSRF** lợi dụng việc trình duyệt có thể tự gửi cookie/credentials của site đến request do một origin khác khởi xướng. Khi một thao tác **thay đổi trạng thái** chỉ dựa vào cookie, server cần cách xác định request được khởi tạo qua luồng được site cho phép. Một CSRF token không thể đoán trước, ràng buộc đúng với session/request policy, là một biện pháp phổ biến.

Trong Spring Security Servlet:

- `CsrfFilter` quyết định request có cần kiểm tra token hay không, rồi so token từ request với token được repository cung cấp.
- `CsrfTokenRepository` lưu/đọc token theo chính sách; `HttpSessionCsrfTokenRepository` và `CookieCsrfTokenRepository` có đặc điểm khác nhau.
- Form thường gửi token trong hidden field có tên tương ứng `CsrfToken.getParameterName()`, phổ biến là `_csrf`.
- JS frontend thường gửi token trong header có tên theo repository, ví dụ `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN`, **không** tự đoán chung cho mọi ứng dụng.
- Trong Spring Security 6, cơ chế xử lý token có thể liên quan đến **deferred token** và cách mã hóa/che token để hỗ trợ chống BREACH. Khi xây SPA, phải theo đúng hướng dẫn token-request handler và repository cho phiên bản Spring Security đang sử dụng.

Ví dụ HTTP (giá trị chỉ mang tính minh họa; token thật được framework tạo):

~~~http
POST /signout HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=opaque-session-id
Content-Type: application/x-www-form-urlencoded

_csrf=generated-csrf-token
~~~

CSRF token **không phải mật khẩu** và không phải access token. Không ghi token/session cookie vào log, URL query string, email hay referrer. Token có thể được rotate/clear sau authentication/logout; form lấy token cũ từ cache có thể cần refresh trước lần thao tác kế tiếp.

### Token trong hidden form

Một form server-rendered có thể tạo input từ request attribute `_csrf`. Với Thymeleaf được tích hợp Spring MVC, dùng `th:action` trên form POST thường giúp framework thêm hidden CSRF field qua `RequestDataValueProcessor`, tùy cấu hình template/request handler. Khi tự render HTML hoặc dùng frontend không hỗ trợ, phải lấy token do server cấp và thêm đúng parameter/header.

Không hard-code token và không dùng `csrf().disable()` để “sửa” POST bị 403. Lỗi 403 cần kiểm tra: có token không, tên parameter/header có đúng không, token có thuộc session hiện tại không, form đã được render sau login/logout hay chưa, browser có gửi đúng cookie không, và endpoint có đi qua đúng `SecurityFilterChain` không.

## 6. Ví dụ Spring Boot đầy đủ: POST /signout có CSRF

Ví dụ dùng user trong memory **chỉ để học**, mặc định form login, logout URL tùy chỉnh, success URL cố định và một trang Thymeleaf có nút đăng xuất. Cấu trúc dự án:

~~~text
src/main/java/com/example/logoutlesson/
  LogoutLessonApplication.java
  SecurityConfig.java
  PagesController.java
src/main/resources/templates/
  signout-form.html
src/test/java/com/example/logoutlesson/
  LogoutFlowIntegrationTest.java
~~~

Dependencies Maven/Gradle tương ứng: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-thymeleaf`; cho test có `spring-boot-starter-test` và `spring-security-test`. Các đoạn source phải nằm cùng package hoặc được scan đúng.

### 6.1. SecurityConfig.java

~~~java
package com.example.logoutlesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("student")
                .password(encoder.encode("training-only"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(demo);
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/signout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .permitAll());

        // Không gọi csrf(AbstractHttpConfigurer::disable):
        // CSRF mặc định vẫn áp dụng cho POST đăng xuất.
        return http.build();
    }
}
~~~

Đây là cấu hình tiêu biểu cho **stateful browser login**:

1. `formLogin(...)` bật đường đăng nhập với session; không dùng API Bearer JWT stateless ở đây.
2. `logoutUrl("/signout")` thay request path gây logout, không đổi method POST an toàn khi CSRF đang bật.
3. `logoutSuccessUrl("/login?logout")` dùng một relative URL cố định phía server, không nhận external URL từ client.
4. `invalidateHttpSession(true)` yêu cầu hủy HTTP session; điều này có thể ảnh hưởng dữ liệu khác nằm trong session, nên cần hiểu phạm vi nghiệp vụ.
5. `clearAuthentication(true)` dọn authentication. Security context và token liên quan còn được xử lý bởi những logout handlers theo cấu hình của framework.
6. `permitAll()` tiện cho logout endpoint và success URL trong mô hình có authorization chặt; không có nghĩa bỏ qua CSRF.
7. Cấu hình **không** tắt CSRF. Nếu gặp 403 sau khi submit nút logout, phải điều tra token/session, không mặc định bỏ CSRF.

**Không dùng credential demo trong production.** Khi triển khai thực tế, dùng user store, password hashing/secret management và policy phù hợp. Các strings `student`/`training-only` chỉ giúp test dễ hiểu.

### 6.2. PagesController.java

~~~java
package com.example.logoutlesson;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PagesController {

    @GetMapping("/public")
    @ResponseBody
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    @ResponseBody
    public String privatePage(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/signout-form")
    public String signoutForm() {
        return "signout-form";
    }
}
~~~

`GET /signout-form` chỉ **hiển thị form**, không thực thi logout. Nó cần authentication vì `anyRequest().authenticated()`. `GET /private` cũng cần login và trả username; test có thể dùng nó để chứng minh context còn hay mất sau các request.

Không tạo `@PostMapping("/signout")` trong controller: URL POST này thuộc `LogoutFilter` của Spring Security. Controller không chịu trách nhiệm xóa session hay context.

### 6.3. templates/signout-form.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng xuất an toàn</title>
</head>
<body>
  <h1>Đăng xuất</h1>
  <p>Bấm nút để kết thúc phiên đăng nhập hiện tại.</p>
  <form th:action="@{/signout}" method="post">
    <button type="submit">Đăng xuất</button>
  </form>
</body>
</html>
~~~

**Điểm quan trọng:** Với Thymeleaf tích hợp Spring MVC/Spring Security theo cấu hình Boot thông thường, `th:action` của form POST tương tác với request-data-value processor để thêm hidden field CSRF thích hợp. Khi dùng template engine khác hoặc HTML static, tính năng này có thể **không tồn tại**; bạn phải tự render hidden field có token do server cấp. Hãy **kiểm tra HTML thực tế** (phải xuất hiện đúng field token) thay vì giả định chỉ có `method="post"` là đủ.

Một cách render form thủ công trong môi trường khác (đây là **mảnh minh họa**, không chứa token thật và chưa chạy được nếu không có phía server cấp token):

~~~html
<form action="/signout" method="post">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Trong code thật không sử dụng literal `TOKEN_FROM_SERVER`. Tên field `_csrf` là cấu hình thường gặp, nhưng ứng dụng có thể đổi tên/header/repository; phải lấy từ `CsrfToken`/template renderer. Nếu dùng Thymeleaf `th:action`, tránh tự chèn thêm một hidden token thứ hai không cần thiết.

### 6.4. LogoutLessonApplication.java

~~~java
package com.example.logoutlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutLessonApplication.class, args);
    }
}
~~~

Với một dự án có Maven Wrapper, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Mở `http://localhost:8080/private` khi chưa login sẽ được đưa về luồng login. Sau khi login bằng user demo `student`, mở `http://localhost:8080/signout-form` và bấm nút. Kết quả mong đợi là form POST đi tới `/signout` với CSRF token hợp lệ, session bị invalidated và response chuyển tới `/login?logout`.

Trong ứng dụng gắn context path hoặc reverse proxy, sử dụng URL builder template và kiểm tra cookie path, route thực tế; không tự nối raw host do request cung cấp.

## 7. Kiểm thử MockMvc: đừng chỉ assert 302

`MockMvc` cùng `spring-security-test` cho phép chạy request qua `SecurityFilterChain` thay vì chỉ gọi controller, và kiểm tra CSRF/session. Đặc biệt với logout, **một phản hồi 302 không đủ chứng minh session thực sự đã bị hủy**, còn 403 do thiếu CSRF không nói gì về logout handler nếu request chưa đi tới nó.

Tạo `src/test/java/com/example/logoutlesson/LogoutFlowIntegrationTest.java`:

~~~java
package com.example.logoutlesson;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
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
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutFlowIntegrationTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "training-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void postWithCsrfLogsOutAndInvalidatesSession()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/signout")
                    .session(session)
                    .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"))
            .andExpect(unauthenticated());

        assertTrue(session.isInvalid());

        // Không mang phiên cũ vào request tiếp theo.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void postWithoutCsrfDoesNotLogOut() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/signout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void invalidCsrfDoesNotLogOut() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/signout")
                    .session(session)
                    .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
    }

    @Test
    void getCannotPerformLogout() throws Exception {
        MockHttpSession session = login();

        MvcResult result = mvc.perform(
                    get("/signout").session(session))
                .andReturn();

        // Không ràng buộc GET phải 200 hay 404 vì tùy
        // trang/route được ứng dụng cấu hình.
        assertNotEquals("/login?logout",
                result.getResponse().getRedirectedUrl());
        assertFalse(session.isInvalid());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }
}
~~~

Một số IDE/tooling yêu cầu static import `redirectedUrlPattern` khi dùng matcher này; trong tệp trên cần bổ sung import sau bên cạnh `redirectedUrl`:

~~~java
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrlPattern;
~~~

**Tại sao test này có giá trị?**

1. Test `POST /signout` với `.with(csrf())` xác nhận route logout hoạt động **sau** khi token đã được kiểm tra.
2. `session.isInvalid()` xác nhận mock session bị invalidated; không chỉ nhìn URL redirect.
3. `POST` thiếu token hoặc token sai phải trả **403** và session **vẫn hợp lệ**.
4. `GET /signout` không làm logout; không buộc status 404 vì ứng dụng có thể thêm trang xác nhận, nhưng **không được invalidate session**.
5. `GET /private` sau POST bị chặn vẫn cho kết quả **200** với session cũ, chứng minh người dùng chưa bị đăng xuất trái ý muốn.
6. Sau POST logout thành công, một request **không có session** bị chuyển tới login; để kiểm tra cookie/session ID cũ không thể tái sử dụng trên server thực, cần thêm HTTP integration test qua trình duyệt/container.

**Chú ý kỹ thuật:** `MockMvc` dùng `MockHttpSession` và `SecurityMockMvcRequestPostProcessors.csrf()` để dựng request; đây là kiểm thử servlet-filter-level, không mô phỏng hoàn hảo cookie của browser/proxy. Trong ứng dụng có session fixation/concurrent sessions và CSRF token riêng, có thể cần fixture đồng bộ token với repository/session thực tế. Các assert logic của ví dụ giả định cấu hình mặc định như mục 6.

Chạy test trong dự án Maven Boot đã có dependencies:

~~~bash
./mvnw test
~~~

Không khẳng định stdout Maven hoặc các ID session cụ thể: chúng khác nhau theo môi trường. Test cần chạy cùng phiên bản Spring Security/Boot mà bạn deploy.

### 7.1. Kiểm thử với request cache và form login

Logout không chỉ được test ở màn hình đã login. Xem thêm chuỗi thao tác:

~~~text
GET /private (anonymous)
  -> redirect login
POST /login + CSRF + credential đúng
  -> SecurityContext lưu vào session
GET /signout-form
  -> HTML chứa form POST /signout + hidden CSRF token hợp lệ
POST /signout + cookie session + CSRF
  -> session invalidated, context cleared
GET /private
  -> lại yêu cầu login
~~~

Nếu ứng dụng có custom `AuthenticationSuccessHandler`, `SavedRequest` hay nhiều `SecurityFilterChain`, những thành phần đó có thể ảnh hưởng URL đích của login/logout; hãy kiểm thử đúng chain và route, không suy từ những tên mặc định.

### 7.2. Test không được “vô hiệu hóa để qua bài”

Sai lầm phổ biến: `POST /signout` bị 403, lập trình viên xóa `csrf()` khỏi security chain để test xanh. Khi đó test mất ý nghĩa bảo mật của web session.

Thay vào đó:
- Dùng `csrf()` request post-processor trong MockMvc hoặc gửi token do site tạo khi test browser.
- Kiểm tra form có hidden token, cookie session đúng, token chưa hết hạn/rotate, path đúng.
- Kiểm tra `CsrfTokenRepository` của security chain cụ thể, kể cả cấu hình SPA/CSRF token trong cookie.
- Không thêm `csrf.ignoringRequestMatchers("/signout")` nếu mục tiêu là logout chống CSRF.

## 8. Custom method matching: thay matcher thì có gì thay đổi?

Trong Spring Security 6, muốn policy hiển nhiên rằng **chỉ POST** được thực hiện logout, có thể định nghĩa request matcher riêng. Ví dụ dưới đây là **mảnh cấu hình thay thế** cho phần `.logout(...)` ở mục 6, không dùng đồng thời cả hai:

~~~java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

// ...

.logout(logout -> logout
    .logoutRequestMatcher(
        new AntPathRequestMatcher("/signout", "POST"))
    .logoutSuccessUrl("/login?logout")
    .permitAll())
~~~

`AntPathRequestMatcher` có thể bị deprecate trong các bản Spring Security 6.x mới và được thay bằng cách matching khác ở các phiên bản lớn về sau; điều cần giữ là **request matcher ràng buộc cả path và POST method**. Khi dùng matcher riêng, nên viết test phương thức GET/PUT/DELETE rõ ràng.

**Quan trọng:** ràng buộc method POST **không thay thế CSRF token**. Một form ở website độc hại vẫn có thể gửi POST tới origin mục tiêu trong những điều kiện nhất định. Nếu ứng dụng dựa trên cookie, CSRF protection vẫn cần thiết dù matcher chỉ chấp nhận POST.

### Nếu tắt CSRF thì sao?

Ví dụ:

~~~java
// PHẢN VÍ DỤ với ứng dụng form login dùng session:
// Không copy nguyên cấu hình này vào production.
http.csrf(csrf -> csrf.disable());
~~~

Khi CSRF bị tắt, một `LogoutConfigurer` mặc định theo URL có thể match nhiều method, làm GET logout trở lại (hành vi cụ thể phụ thuộc phiên bản/cấu hình). Ngay cả khi bạn ép matcher chỉ POST, request POST từ origin khác vẫn có thể gây logout vì không còn CSRF token. Vì vậy, trong **browser session authentication**, đừng tắt CSRF chỉ để sửa lỗi AJAX/form.

Trong hệ thống **stateless API** mà credential chỉ được gửi bằng Bearer token trong header do client chủ động đặt (không tự động gửi qua cookie), threat model CSRF khác. Có thể cấu hình CSRF riêng cho API chain sau khi đánh giá đầy đủ, nhưng không nên sao chép chính sách stateless sang form-login chain.

### Có thể hỗ trợ nhiều URL logout không?

Có thể cấu hình matcher phức tạp kết hợp nhiều path/method, nhưng phải giới hạn các đường thực sự cần và test từng endpoint. Nếu app có nhiều frontend, nên thống nhất một endpoint server và để mỗi frontend dùng cùng hợp đồng thay vì tạo alias GET nguy hiểm.

Nếu dùng `/api/logout` và `/signout` ở hai security chains khác nhau, cần xác định rõ chain match order, session policy, CSRF repository và logout handlers tương ứng. Một POST có thể bị xử lý bởi chain API trước khi đến chain web; kết quả sẽ khác nếu matcher thuộc chain không được chọn.

## 9. SPA hoặc fetch() dùng cookie session

Một trang SPA có thể không dùng HTML form truyền thống mà gọi `fetch`. Nếu browser vẫn dùng cookie session để xác thực, **CSRF vẫn là vấn đề phải xử lý**. Ví dụ nguyên lý JavaScript:

~~~javascript
async function signOut(csrfToken, csrfHeaderName) {
  const response = await fetch("/signout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      [csrfHeaderName]: csrfToken
    },
    redirect: "follow"
  });

  if (!response.ok) {
    throw new Error("Logout failed");
  }
}
~~~

Đây là **mã phía client**, không phải ví dụ đầy đủ về cách lấy token. `csrfToken` và `csrfHeaderName` phải lấy từ server theo cơ chế được phê duyệt, tương thích với repository và CSRF request handler của Spring Security 6 (kể cả deferred/BREACH token behavior). Đừng tự lưu secret/session token vào localStorage nếu ứng dụng không yêu cầu và chưa phân tích XSS/threat model.

Với `fetch` mặc định có redirect handling, kết quả `response.ok` có thể thuộc response cuối cùng sau 302; ứng dụng cần định nghĩa UI navigation khi logout thành công. Đối với SPA/API chỉ muốn status không redirect, có thể dùng success handler trả `204`:

~~~java
import jakarta.servlet.http.HttpServletResponse;

// Thay cho logoutSuccessUrl(...) trong cấu hình phù hợp:
.logout(logout -> logout
    .logoutUrl("/signout")
    .logoutSuccessHandler((request, response, authentication) ->
        response.setStatus(HttpServletResponse.SC_NO_CONTENT))
    .permitAll())
~~~

Lưu ý đây là **mảnh cấu hình thay thế**; không được kết hợp với `logoutSuccessUrl("/login?logout")` cùng lúc nếu hai semantics mâu thuẫn. Với `204`, client nên xóa trạng thái UI đang giữ và chuyển tới màn hình chưa đăng nhập theo logic của app; server vẫn phải invalidate session/context và xử lý CSRF.

### CookieCsrfTokenRepository và SPA

Một số ứng dụng dùng `CookieCsrfTokenRepository` để frontend đọc token từ cookie, thường sử dụng header `X-XSRF-TOKEN`. Với Spring Security 6, cần đặc biệt chú ý cách unmask token khi kết hợp CSRF request handler, vì token được render trong HTML và token raw trong cookie có thể được xử lý khác nhau. Đừng chỉ copy đoạn `CookieCsrfTokenRepository.withHttpOnlyFalse()` từ một bài hướng dẫn cũ rồi mặc định app an toàn; phải cấu hình chính sách và kiểm thử theo phiên bản, xét XSS và phạm vi cookie.

## 10. Logout thành công cần xóa những gì?

Các công việc thường liên quan:

| Tài nguyên | Cơ chế thường gặp | Lưu ý |
| --- | --- | --- |
| `SecurityContext` trong request | `SecurityContextLogoutHandler` và context holder/repository. | Không giữ authenticated context trong thread/dispatch tiếp theo. |
| `HttpSession` | `invalidateHttpSession(true)`. | Có thể hủy các session attributes khác; không nhầm với xóa DB user. |
| Cookie session | Phản hồi invalidation/container và `deleteCookies(...)` nếu cần. | Cookie domain/path/Secure/SameSite quyết định browser thực sự xóa cái nào. |
| CSRF token | `CsrfLogoutHandler`/repository tương ứng. | Token cũ không dùng tiếp; form tiếp theo lấy token mới. |
| Remember-me cookie | Remember-me logout handler nếu remember-me được bật. | Không mặc định cookie remember-me bị xóa nếu config khác. |
| Concurrent-session registry | Session lifecycle/events và registry integration. | Kiểm tra session cleanup, nhất là khi maxSessions đang áp dụng. |
| Refresh token/OAuth2/OIDC session | Thành phần identity/provider riêng. | Không tự bị thu hồi chỉ do HTTP session invalidated. |
| Frontend memory state | Client clear user state/cache và điều hướng. | Không thay cho server invalidation. |

**Không dùng `deleteCookies("JSESSIONID")` thay cho invalidate session.** Việc yêu cầu trình duyệt xóa cookie không tự đảm bảo session phía server bị kết thúc; một session ID cũ có thể còn giá trị nếu server chưa invalidate. Ngược lại, session đã invalidate sẽ vô hiệu về phía server ngay cả khi cookie cũ còn ở browser. Cookie có path khác có thể không bị xóa bởi một `Set-Cookie` không khớp, nên luôn test trong browser thực.

Đăng xuất không phải xóa toàn bộ dữ liệu người dùng hay mọi hệ thống liên kết. Với SSO/multiple-device, “đăng xuất phiên này” và “đăng xuất mọi thiết bị” là hai sản phẩm khác nhau và cần quyết định nghiệp vụ riêng.

## 11. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Click link `GET /logout` mà chưa logout | GET chỉ mở trang xác nhận hoặc không match matcher POST. | Dùng form POST có token, không đổi sang GET cho tiện. |
| POST logout trả 403 | Thiếu/sai CSRF token, cookie session không khớp, token bị rotate. | Xem form render và repository; dùng `csrf()` trong MockMvc. |
| POST đúng nhưng luôn 404 | URL cấu hình khác URL form, hoặc request vào security chain khác. | So `logoutUrl`, method, context path và chain order. |
| GET làm logout dù CSRF bật ở chain khác | Request match chain CSRF-disabled hoặc matcher tùy biến nhận GET. | Kiểm tra securityMatcher, csrf config và logoutRequestMatcher. |
| POST logout trả 302 nhưng GET protected vẫn được phép | Session/context chưa invalidate, request dùng credential khác (remember-me/JWT), hoặc test dùng session không đúng. | Assert session state, context repository và credential của request sau. |
| Redirect sau logout tới website lạ | Success handler lấy `returnUrl` tùy ý. | Dùng relative URL cố định hoặc allowlist đích bên server. |
| CSRF token cũ gây 403 sau login/logout | Token đã xóa/rotate; frontend cache token cũ. | Lấy token mới từ trang/endpoint hợp lệ. |
| Xóa cookie nhưng session vẫn dùng được | Chỉ xóa browser cookie, chưa invalidate server session. | Kiểm tra `SecurityContextLogoutHandler` và session store. |
| Logout của form web làm API JWT mất hoặc không mất đúng kỳ vọng | Khác threat model/token store, nhầm local session logout với JWT revocation. | Thiết kế riêng token invalidation/logout flow. |
| Không thể logout khi session hết hạn | UI gửi CSRF token cũ, session/cookie đã thay đổi. | Định nghĩa UX/re-login/recovery; không bypass CSRF bừa bãi. |
| POST bị redirect bởi proxy trước logout | HTTP→HTTPS/path canonicalization làm browser đổi method hoặc mất body. | Kiểm tra reverse proxy, TLS redirect và request route. |
| `GET /signout-form` có hidden CSRF trống | Template engine không tích hợp Spring MVC token processor hoặc view sai. | Kiểm tra HTML thực tế; xác nhận CSRF repository và token request attribute. |

### Sai: viết logout bằng @GetMapping

~~~java
// PHẢN VÍ DỤ: gây side effect qua GET, không đưa vào production.
@GetMapping("/unsafe-logout")
public String unsafeLogout(HttpSession session) {
    session.invalidate();
    return "redirect:/login";
}
~~~

Đây là đoạn minh họa lỗi, cần import/cấu hình MVC nếu cố biên dịch. Việc invalidate session **trực tiếp trên GET** bỏ qua cơ chế logout handler/CSRF chuẩn và dễ tạo logout CSRF. Không nên sửa bằng cách “chuyển GET sang PUT” khi browser còn tự đính cookie nhưng không có CSRF policy.

### Sai: bỏ toàn bộ CSRF chỉ vì logout 403

~~~java
// PHẢN VÍ DỤ với browser form/session:
http.csrf(csrf -> csrf.disable());
~~~

Nếu app phụ thuộc cookie, việc này có thể mở rộng CSRF cho những thao tác nguy hiểm hơn logout (chuyển tiền, thay email, đổi mật khẩu, ...). Bảo vệ đăng xuất không nên được xử lý bằng cách làm yếu bảo vệ toàn bộ web chain.

### Sai: chỉ kiểm tra request có Method POST

~~~java
// PHẢN VÍ DỤ: POST không có CSRF vẫn có thể được origin khác tạo.
if ("POST".equals(request.getMethod())) {
    session.invalidate();
}
~~~

Phương thức POST là **điều kiện cần cho thiết kế logout theo semantic**, không phải biện pháp chứng minh ý định người dùng trong ứng dụng cookie-based.

### Sai: redirect tới returnUrl không được kiểm soát

~~~java
// PHẢN VÍ DỤ open redirect sau logout:
response.sendRedirect(request.getParameter("returnUrl"));
~~~

Nếu ứng dụng muốn chuyển đến trang cụ thể sau logout, phải dùng đích server cố định hoặc ánh xạ key → path được phê duyệt. Đừng tin `Referer` hoặc prefix string của external domain.

## 12. Java 17 độc lập: mô phỏng hợp đồng method + CSRF

Chương trình nhỏ này **không phải Spring Security**, không gửi HTTP và không hủy session; nó mô tả quyết định logic của một endpoint logout POST-only. Tạo tệp `LogoutRequestPolicyDemo.java`:

~~~java
public final class LogoutRequestPolicyDemo {

    record Request(String path, String method, boolean validCsrf) {}

    static String evaluate(Request request) {
        if (!"/signout".equals(request.path())
                || !"POST".equals(request.method())) {
            return "NOT_LOGOUT";
        }

        if (!request.validCsrf()) {
            return "CSRF_REJECTED";
        }

        return "LOGOUT_ALLOWED";
    }

    public static void main(String[] args) {
        System.out.println(evaluate(
            new Request("/signout", "GET", false)));
        System.out.println(evaluate(
            new Request("/signout", "POST", false)));
        System.out.println(evaluate(
            new Request("/signout", "POST", true)));
        System.out.println(evaluate(
            new Request("/private", "POST", true)));
    }
}
~~~

Chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac LogoutRequestPolicyDemo.java
java LogoutRequestPolicyDemo
~~~

Stdout **chính xác**:

~~~text
NOT_LOGOUT
CSRF_REJECTED
LOGOUT_ALLOWED
NOT_LOGOUT
~~~

Bài học: chỉ khi **đường dẫn đúng, HTTP method đúng và CSRF hợp lệ** thì mô hình cho phép chạy logout. Trong ứng dụng Spring thật, `CsrfFilter` và `LogoutFilter` thực hiện phần tương ứng ở các điểm khác nhau, HTTP status thực tế còn phụ thuộc authentication/authorization/route, và việc invalidate session phải được kiểm tra riêng.

## 13. Checklist trước khi phát hành

- [ ] Xác định rõ ứng dụng dùng browser cookie/session hay stateless token.
- [ ] `logoutUrl` là path chính xác mà form/client gọi; không nhầm với `logoutSuccessUrl`.
- [ ] Với cookie session: **POST-only logout và CSRF bật**, không để GET tự hủy session.
- [ ] Không miễn trừ CSRF cho logout chỉ để tránh 403.
- [ ] Form POST lấy token thực từ repository/framework, không hard-code token.
- [ ] Sau logout: authentication/context không còn trong request sau; session phía server được invalidated theo policy.
- [ ] Cookie `JSESSIONID` có Secure/HttpOnly/SameSite/path/domain phù hợp, được kiểm tra trên browser thật.
- [ ] Logout success destination cố định hoặc allowlist, không tạo open redirect.
- [ ] Nếu dùng nhiều chains, kiểm tra đúng chain match `/signout` và chính sách CSRF ở chain đó.
- [ ] Kiểm thử GET logout không gây side effect, POST thiếu/sai CSRF bị 403, POST đúng được logout, endpoint protected sau logout yêu cầu login.
- [ ] Tránh double-registration/custom controller logout bỏ qua `LogoutFilter`.
- [ ] Nếu dùng remember-me, concurrent sessions, Spring Session/cluster, xác nhận handlers và registry cleanup hoạt động.
- [ ] Với JWT/refresh token/SSO, có chính sách thu hồi token riêng nếu nghiệp vụ yêu cầu.
- [ ] Không log session cookie, CSRF token, mật khẩu hoặc authorization headers.
- [ ] Có test regression khi thay logoutUrl, request matcher, proxy/context path hoặc frontend form.

## 14. Câu hỏi ôn tập

**Q1. `logoutUrl("/signout")` có phải trang được hiển thị sau logout không?** Không. Đó là path để `LogoutFilter` nhận request logout. `logoutSuccessUrl(...)` mới xác định đích sau thành công.

**Q2. Vì sao đăng xuất qua GET không nên xảy ra?** GET có thể bị tải tự động/bị website khác kích hoạt và không nên làm thay đổi trạng thái; nguy cơ logout CSRF và vi phạm semantics.

**Q3. Nếu form dùng POST thì tự động chống CSRF chưa?** Chưa. Origin khác cũng có thể gửi POST; cần CSRF token hợp lệ hoặc biện pháp tương đương theo threat model.

**Q4. POST logout thiếu token trong app CSRF-enabled thường nhận gì?** 403 trước khi LogoutFilter xử lý; authentication/session hiện tại không nên bị xóa bởi request đó.

**Q5. Vì sao không dùng `csrf.disable()` để sửa 403?** Vì sẽ làm yếu bảo vệ cho toàn bộ unsafe requests thuộc chain và có thể vô tình cho GET logout hoặc POST giả mạo.

**Q6. `GET /logout` có phải lúc nào cũng là trang xác nhận?** Không. Nó có thể là trang xác nhận khi framework sinh giao diện mặc định phù hợp, hoặc là 404/custom route tùy config. Điều cốt lõi là GET không được logout.

**Q7. Vì sao sau 302 phải còn kiểm tra session?** 302 chỉ nói về response. Cần xác nhận logout handlers đã invalidate session/clear authentication, rồi endpoint protected không còn truy cập bằng credential cũ.

**Q8. Xóa cookie có đồng nghĩa với thu hồi JWT/refresh token không?** Không. Session logout và token revocation là những cơ chế khác nhau, nhất là khi có OAuth2/OIDC hoặc nhiều dịch vụ.

**Q9. Với SPA dùng fetch POST, lấy token ở đâu?** Từ một cơ chế phía server được thiết kế cho CSRF repository và request handler tương ứng; gửi trong header/field đúng tên với cookie session phù hợp. Không tự tạo giá trị hoặc đoán format.

**Q10. Khi đổi `logoutRequestMatcher`, cần test gì?** Test path và **HTTP method** thực sự match, GET không có side effect, các unsafe method khác không bypass policy, và CSRF vẫn được bảo vệ.

**Ghi nhớ:** **`logoutUrl` xác định điểm kích hoạt; HTTP method xác định thao tác; CSRF token xác minh yêu cầu đến từ luồng được phép; `LogoutHandler` dọn state; `LogoutSuccessHandler` quyết định response.** Với Servlet form login dùng cookie, thiết kế an toàn điển hình là **POST logout có CSRF**, không phải GET logout.
