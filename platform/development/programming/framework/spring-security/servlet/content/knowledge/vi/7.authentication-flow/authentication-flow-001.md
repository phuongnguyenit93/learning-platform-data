# Chuỗi xử lý từ thông tin đăng nhập đến Authentication đã xác thực

> **Phạm vi:** Spring Security trên **Servlet stack**, Java 17+, ứng dụng Spring Boot 3.x / Spring Security 6.x. Chủ đề là **luồng xác thực**: từ credentials do client gửi, qua filter, token chưa xác thực, `AuthenticationManager`, `AuthenticationProvider`, đến một `Authentication` đã được xác minh và cách đưa kết quả vào `SecurityContext`. Cần phân biệt xác thực (*authentication*) với kiểm tra quyền (*authorization*), cũng như khác biệt giữa form login, HTTP Basic và bearer token.

## 1. Bức tranh tổng thể: ai làm gì?

Trong một ứng dụng Servlet dùng Spring Security, HTTP request đi qua container filter chain. `DelegatingFilterProxy` thường chuyển việc thực thi sang `FilterChainProxy`; đối tượng này tìm một `SecurityFilterChain` có `RequestMatcher` khớp URL. Filter xác thực chỉ chạy nếu nó nằm trong chain đã chọn và nếu request đáp ứng điều kiện mà filter đó xử lý.

~~~text
Client
  |  POST /login với username/password (ví dụ form login)
  v
Servlet container
  -> DelegatingFilterProxy -> FilterChainProxy
     -> SecurityFilterChain khớp request
       -> bộ lọc nạp SecurityContext cho request
       -> [CSRF filter khi áp dụng]
       -> UsernamePasswordAuthenticationFilter
          (1) trích xuất username/password
          (2) tạo Authentication chưa xác thực
          (3) gọi AuthenticationManager.authenticate(...)
                -> ProviderManager
                    -> chọn AuthenticationProvider hỗ trợ token
                        -> lấy dữ liệu người dùng/khóa/tokens cần kiểm tra
                        -> xác minh credentials + trạng thái tài khoản
                        -> trả Authentication đã xác thực
          (4) đặt Authentication vào SecurityContext
          (5) lưu context vào repository nếu cần, xử lý session/success
       -> nhánh response hoặc các filter/controller tiếp theo
       -> cuối phạm vi filter: dọn SecurityContextHolder trên thread
~~~

Sơ đồ thể hiện **form login thành công điển hình**. Không phải mọi cơ chế đều có cùng endpoint, loại token hoặc response. Với HTTP Basic hoặc bearer token, credentials thường xuất hiện ở header và request có thể tiếp tục vào controller sau khi được xác thực. Với form login mặc định, thành công thường dẫn đến redirect và kết thúc nhánh xử lý đăng nhập.

| Thành phần | Trách nhiệm chính | Không nên gán nhầm trách nhiệm |
| --- | --- | --- |
| `SecurityFilterChain` / `FilterChainProxy` | Chọn và chạy các servlet security filter phù hợp request. | Không trực tiếp so mật khẩu. |
| Authentication filter | Lấy dữ liệu do client gửi, tạo token chưa xác thực, gọi manager, xử lý kết quả. | Không nên tự đánh dấu token đã xác thực khi chưa kiểm chứng. |
| `AuthenticationManager` | Đầu mối hợp đồng `authenticate(authentication)`. | Không nhất thiết tự hiểu mọi loại thông tin đăng nhập. |
| `ProviderManager` | Một triển khai `AuthenticationManager`, điều phối các provider. | Không đồng nghĩa luôn phải có một provider duy nhất. |
| `AuthenticationProvider` | Kiểm tra loại Authentication mà nó hỗ trợ và tạo kết quả đã xác thực hoặc báo lỗi. | Không quyết định toàn bộ HTTP redirect / session cookie. |
| `UserDetailsService` | Tải `UserDetails` theo username trong mô hình username/password. | Không phải nơi so mật khẩu với request. |
| `PasswordEncoder` | So mật khẩu thô với hash đã lưu bằng `matches(raw, encoded)`. | Không được lưu mật khẩu dạng plaintext trong production. |
| `SecurityContextHolder` | Cho code trên thread hiện tại truy cập `SecurityContext`. | Không phải kho lưu session lâu dài. |
| `SecurityContextRepository` | Nạp/lưu context giữa dispatch/request theo chính sách. | Không phải tự động lưu mọi thay đổi trong mọi cấu hình. |

Trong ứng dụng thực, một số filter có thể không hiện diện, thay đổi thứ tự hoặc được thay bằng filter khác tùy cấu hình. Sơ đồ là mô hình để hiểu luồng xử lý, không phải danh sách thứ tự đầy đủ cố định cho mọi phiên bản.

## 2. HTTP request mang “thông tin đăng nhập” là gì?

Credentials là bằng chứng client cung cấp để chứng minh danh tính, chẳng hạn mật khẩu, HTTP Basic credentials, bearer token hoặc một assertion từ hệ thống danh tính. **Username/email đơn lẻ chỉ là định danh được khai báo, không phải bằng chứng đủ để xác thực.**

Với form login mặc định Spring Security:

- Trình duyệt gửi `POST /login` kèm form parameter `username` và `password`.
- Mẫu Spring Security cấu hình form login thường có `UsernamePasswordAuthenticationFilter` xử lý URL này.
- Nếu bật bảo vệ CSRF (mặc định phù hợp cho ứng dụng web dựa trên cookie), form POST phải có CSRF token hợp lệ; request có thể bị chặn trước khi tới filter xác thực nếu token sai.
- Dữ liệu phải truyền trên **HTTPS** trong môi trường thực. Không đưa mật khẩu vào query string vì dễ lọt vào URL/log/history.

Với Basic authentication:

~~~http
GET /private HTTP/1.1
Host: example.test
Authorization: Basic <base64-credentials>
~~~

Đây là **mô tả dạng HTTP**, không phải một request có thể dùng trực tiếp vì phần `<base64-credentials>` là ký hiệu minh họa. HTTP Basic dùng Base64 để biểu diễn `username:password`, **không phải mã hóa bảo mật**; HTTPS vẫn bắt buộc. `BasicAuthenticationFilter` có thể chuyển dữ liệu thành một authentication request để `AuthenticationManager` xử lý.

Với bearer token:

~~~http
GET /api/orders HTTP/1.1
Host: example.test
Authorization: Bearer <access-token>
~~~

`BearerTokenAuthenticationFilter` xử lý bearer token trong một resource server được cấu hình tương ứng. Token được kiểm tra chữ ký/claims hoặc introspection tùy loại token và cấu hình; **không** đi qua `DaoAuthenticationProvider` chỉ vì nó cũng là một lần xác thực. Đừng gửi token thật vào log hoặc ví dụ chia sẻ công khai.

## 3. Token *chưa xác thực*: đối tượng `Authentication` đầu vào

`Authentication` là interface trung tâm của Spring Security, bao gồm các ý niệm:

- `getPrincipal()`: đối tượng biểu thị danh tính; đầu vào có thể chỉ là username, đầu ra có thể là `UserDetails` hoặc principal chuyên biệt.
- `getCredentials()`: bằng chứng cần xác minh, ví dụ password/token; sau xác thực credentials có thể bị xóa.
- `getAuthorities()`: danh sách quyền (`GrantedAuthority`) áp dụng cho principal.
- `getDetails()`: thông tin phụ theo cơ chế, chẳng hạn metadata request; không dùng nó làm bằng chứng tin cậy nếu chưa kiểm chứng.
- `isAuthenticated()`: trạng thái token đã được cơ chế xác thực chấp nhận; chỉ trạng thái này **không tự chứng minh có quyền đối với mọi tài nguyên**.

Ở luồng username/password, filter có thể tạo:

~~~java
Authentication request = UsernamePasswordAuthenticationToken.unauthenticated(
    username, password
);
Authentication result = authenticationManager.authenticate(request);
~~~

**Đây là mảnh Java sử dụng Spring Security**, không phải chương trình Java SE độc lập. Cần import `org.springframework.security.core.Authentication`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.springframework.security.authentication.AuthenticationManager` và các biến `username`, `password` đã được lấy từ request hợp lệ.

Lúc tạo bằng factory `unauthenticated(...)`, token chỉ đại diện **lời khai của client**. Đừng tạo `UsernamePasswordAuthenticationToken.authenticated(...)` với danh sách authority tự chọn để “bỏ qua” bước kiểm tra: làm thế có thể trao quyền cho một danh tính chưa được xác minh. Một đối tượng được set là authenticated do code tự tạo không thay thế quy trình tin cậy của `AuthenticationProvider`.

### Dữ liệu đi vào và đi ra

| Giai đoạn | Principal | Credentials | Authenticated | Authorities |
| --- | --- | --- | --- | --- |
| Form vừa gửi, trước kiểm tra | Username do client cung cấp | Raw password | `false` | Thường chưa có |
| Provider xác thực thành công | Danh tính đã được xác minh, ví dụ `UserDetails` | Có thể vẫn tồn tại trong quá trình xử lý, sau đó bị xóa | `true` | Được lấy từ nguồn đáng tin cậy/chính sách |
| Provider xác thực thất bại | Không có kết quả đáng tin | Không được duy trì/log | Không phát sinh result thành công | Không được cấp |
| Authorization về sau | Principal từ context tương ứng | Thường không cần password | Có thể true, nhưng vẫn phải xét loại token và policy | Được kiểm tra với yêu cầu truy cập cụ thể |

`AnonymousAuthenticationToken` là trường hợp cần lưu ý: đối tượng này có thể có `isAuthenticated() == true` nhưng thể hiện **người dùng ẩn danh**, không phải người dùng đăng nhập. Vì vậy mã nghiệp vụ không nên viết `if (auth != null && auth.isAuthenticated())` rồi mặc nhiên hiểu là authenticated login. Hãy dùng các rule authorization như `authenticated()`, `hasAuthority(...)`, `hasRole(...)` hoặc `AuthorizationManager` theo yêu cầu.

## 4. `AuthenticationManager` và `ProviderManager` điều phối ra sao?

Hợp đồng của `AuthenticationManager` có thể hình dung bằng:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

Đây là **chữ ký minh họa** từ API của Spring Security; `AuthenticationException` là lỗi xác thực thuộc Spring Security, không phải exception Java SE. Thành công trả một `Authentication` đã xác thực; thất bại ném exception, thay vì trả `false`.

Một triển khai phổ biến, `ProviderManager`, có danh sách `AuthenticationProvider`. Mỗi provider cho biết có hỗ trợ kiểu token qua `supports(Class<?>)` hay không. `supports(...)` thể hiện khả năng xử lý kiểu token; nó **không bảo đảm** provider sẽ xác thực thành công một token cụ thể.

Ví dụ conceptual:

~~~text
AuthenticationManager.authenticate(
    UsernamePasswordAuthenticationToken{authenticated=false}
)
    |
    v
ProviderManager
    | -> DaoAuthenticationProvider.supports(...) = true
    |    -> đọc UserDetails
    |    -> kiểm tra password, account status
    |    -> Authentication{authenticated=true} hoặc AuthenticationException
    |
    | -> provider cho token khác: chỉ được xét nếu có thể xử lý kiểu token
    v
result hoặc AuthenticationException
~~~

Nếu có nhiều provider, cách phối hợp còn phụ thuộc kiểu exception và provider nào trả kết quả: provider có thể trả `null` để một provider khác có cơ hội xử lý, hoặc ném exception; một số lỗi trạng thái tài khoản có thể dừng luồng ngay. Đừng nghĩ mọi provider đều “OR” với nhau vô điều kiện. `ProviderManager` có thể có parent manager, có thể phát sự kiện xác thực qua publisher và mặc định có thể xóa thông tin credential nhạy cảm trong result bằng cơ chế `eraseCredentialsAfterAuthentication`.

Những nhóm lỗi thường gặp:

| Kết quả | Ý nghĩa tổng quát |
| --- | --- |
| `BadCredentialsException` | Credentials bị từ chối. |
| `UsernameNotFoundException` | Không tìm thấy user trong tầng tra cứu (thường được che thành lỗi credentials chung để giảm dò username). |
| `DisabledException`, `LockedException`, `AccountExpiredException` | Tài khoản không ở trạng thái được phép xác thực. |
| `CredentialsExpiredException` | Thông tin đăng nhập đã hết hiệu lực theo policy. |
| `ProviderNotFoundException` | Không có provider phù hợp để xử lý token. |

Không công khai thông điệp “username không tồn tại” và “password sai” theo cách giúp kẻ tấn công dò tài khoản. Nên có rate limiting, giám sát brute-force, chính sách khóa tài khoản và MFA theo mức rủi ro thực tế.

## 5. Bên trong `DaoAuthenticationProvider`: kiểm tra username/password

Trường hợp điển hình với username/password dùng database:

1. Provider nhận `UsernamePasswordAuthenticationToken` chưa xác thực.
2. `UserDetailsService.loadUserByUsername(...)` tìm `UserDetails`. Nguồn dữ liệu có thể là database, LDAP adapter hoặc dịch vụ khác.
3. Thông tin tài khoản như enabled/locked/expired được kiểm tra theo chính sách/provider.
4. `PasswordEncoder.matches(rawPassword, storedEncodedPassword)` kiểm tra mật khẩu đã gửi so với hash lưu trữ.
5. Nếu hợp lệ, provider trả `Authentication` đã xác thực có principal và authorities phù hợp. Những thành phần xử lý sau đó có thể xóa credentials khỏi object kết quả.

### Lưu password đúng cách

Ví dụ dùng `BCryptPasswordEncoder`:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String encoded = encoder.encode("demo-only-password");

boolean accepted = encoder.matches("demo-only-password", encoded);
boolean rejected = encoder.matches("wrong-password", encoded);
~~~

Đây là **mảnh mã Spring Security**, import `org.springframework.security.crypto.password.PasswordEncoder` và `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`. Giá trị `encoded` có salt ngẫu nhiên nên **không thể ghi trước một chuỗi output hash cố định**; kết quả Boolean theo ví dụ là `accepted == true`, `rejected == false`. Không lưu literal password trong code production, không dùng hàm hash thường như SHA-256 trần làm password encoder thay BCrypt/Argon2/PBKDF2 có cấu hình phù hợp.

`UserDetailsService` **chỉ cung cấp dữ liệu user**, không tự xác thực password của request. `PasswordEncoder` thực hiện phép so sánh hash, còn provider quản lý quá trình xác thực và kết quả. Đây là ranh giới quan trọng để thiết kế module đăng nhập có thể thay nguồn dữ liệu mà không phải viết lại servlet filter.

## 6. Một ví dụ Spring Boot 3: từ form login tới Authentication

Tạo một ứng dụng Spring Boot 3.x có Java 17+, các dependencies phù hợp:

- `spring-boot-starter-web` (Servlet/Spring MVC).
- `spring-boot-starter-security`.
- Với bài kiểm thử bên dưới: `spring-boot-starter-test` và `spring-security-test` ở scope test.

Đoạn cấu hình dưới dùng **in-memory user dành riêng cho môi trường học tập**. Với production, dùng nguồn user thật và đưa secrets vào hệ thống cấu hình bảo mật; không hard-code credentials trong repository.

### 6.1. `SecurityConfig.java`

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("training-only"))
            .roles("LEARNER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

Khi ứng dụng khởi động, Spring tạo bean `SecurityFilterChain`, `PasswordEncoder` và `UserDetailsService`. Trong cấu hình form login tiêu chuẩn, cơ chế username/password dùng `DaoAuthenticationProvider` và `AuthenticationManager` phù hợp. Đối với yêu cầu đăng nhập, provider lấy `UserDetails` tương ứng, kiểm tra mật khẩu qua encoder, rồi trả kết quả đã xác thực nếu hợp lệ.

`.roles("LEARNER")` tạo authority `ROLE_LEARNER`; lưu ý `hasRole("LEARNER")` tự dùng tiền tố `ROLE_` theo convention, còn `hasAuthority("ROLE_LEARNER")` so sánh tên authority đầy đủ.

### 6.2. `DemoController.java`

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String currentUser(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

`Authentication` được Spring MVC cung cấp cho controller sau khi request đã qua security chain. Endpoint `/me` cần người dùng đã được xác thực vì `anyRequest().authenticated()` trong chain. Controller chỉ minh họa đọc principal, không có code tự kiểm tra password.

### 6.3. Diễn tiến trên browser

~~~text
GET /me không có session đăng nhập
  -> authorization yêu cầu authenticated user
  -> Spring Security chuyển tới trang đăng nhập (thường redirect /login)

GET /login
  -> trang login do Spring Security sinh nếu chưa tùy chỉnh

POST /login (username=learner, password=training-only, CSRF hợp lệ)
  -> UsernamePasswordAuthenticationFilter tạo request Authentication
  -> AuthenticationManager -> DaoAuthenticationProvider
  -> UserDetailsService lấy learner + password hash
  -> PasswordEncoder.matches(...) => true
  -> result Authentication(authenticated=true, ROLE_LEARNER)
  -> SecurityContext được cập nhật và lưu theo login flow/repository
  -> success handler redirect theo yêu cầu đã lưu hoặc URL mặc định

GET /me với session hợp lệ
  -> security context được nạp cho request mới
  -> Authentication.getName() == "learner"
  -> HTTP 200, body "learner"
~~~

Chuỗi trên là luồng **thường gặp của form login stateful**. URL redirect chính xác tùy request cache, success handler, Spring Security config và browser; không nên khẳng định mọi lần đăng nhập đều chuyển đến cùng một path. Client cần gửi lại cookie session hợp lệ trong request sau.

### 6.4. Thử bằng `curl` và CSRF

Có thể chạy ứng dụng qua Maven Wrapper (`./mvnw spring-boot:run` trên Unix hoặc `mvnw.cmd spring-boot:run` trên Windows) khi dự án đã có build file và Spring Boot main class. Lệnh sau:

~~~bash
curl -i http://localhost:8080/me
~~~

sẽ thường nhận redirect tới `/login` khi chưa xác thực. Để thử đăng nhập bằng `curl` với CSRF đang bật, phải giữ cookie jar, lấy CSRF token từ trang login, rồi gửi token cùng POST và cookie. **Không** chỉ POST username/password không có CSRF rồi coi phản hồi `403` là lỗi mật khẩu.

Để kiểm tra tự động chính xác hơn, nên dùng Spring Security Test (mục tiếp theo). Trong môi trường browser, DevTools có thể giúp xem status/redirect/cookie, nhưng không sao chép giá trị session cookie, password hoặc token ra log/công cụ công khai.

## 7. Test luồng xác thực thật bằng Spring Security Test

Giả sử các class ở mục 6 nằm trong cùng ứng dụng Boot có `@SpringBootApplication`, tạo `SecurityFlowTest.java`:

~~~java
package com.example.demo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validCredentialsProduceAuthenticatedPrincipal() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                    .user("learner").password("training-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void badCredentialsDoNotAuthenticate() throws Exception {
        mvc.perform(formLogin()
                    .user("learner").password("wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(unauthenticated());
    }
}
~~~

`formLogin()` ở đây là **request builder của thư viện spring-security-test**, khác với configurer `http.formLogin(...)`. Builder test tạo login request theo form login mặc định và xử lý CSRF phù hợp để kiểm tra nhánh xác thực. `authenticated()` và `unauthenticated()` là **assertion của Spring Security Test**; test không tự gọi `AuthenticationManager`, nên kiểm tra được sự tích hợp của filter, manager, provider và security context.

Test thành công dùng lại session từ HTTP request đăng nhập để xác nhận kết quả **còn tồn tại sang request mới**. Nếu ứng dụng của bạn cấu hình stateless, thay repo, thay success handler hoặc login URL, bài test này phải điều chỉnh theo chính sách thực. Tránh dùng status `302` hay cookie session làm hợp đồng cứng cho mọi kiểu authentication.

Chạy bằng Maven Wrapper trong dự án đã thiết lập:

~~~bash
./mvnw test
~~~

Lệnh này chạy test thật và in log/build output phụ thuộc môi trường, vì vậy không đưa “stdout chính xác” giả định. Nếu một `SecurityFilterChain` khác match `/login` hoặc `/me`, bạn phải xét lại thứ tự chain trước khi diễn giải kết quả.

## 8. Minh họa độc lập Java 17: chuyển trạng thái, không xác thực thật

Để nhìn rõ khác biệt giữa **request token chưa xác thực** và **result token đã xác thực** mà không phụ thuộc Spring, ví dụ Java SE dưới đây mô phỏng bước chuyển do provider quyết định. Biến `credentialsWereVerified` là **kết quả giả lập của một bước xác minh bên ngoài**, không phải cách kiểm tra password. Ứng dụng thật phải dùng password encoder hoặc token verifier.

Tạo tệp `AuthenticationTransitionDemo.java`:

~~~java
import java.util.Set;

public final class AuthenticationTransitionDemo {

    record Token(String principal, boolean authenticated,
                 Set<String> authorities) {}

    static Token provider(Token submitted, boolean credentialsWereVerified) {
        if (!credentialsWereVerified) {
            throw new IllegalArgumentException("Bad credentials");
        }

        return new Token(
                submitted.principal(),
                true,
                Set.of("ROLE_LEARNER")
        );
    }

    static void attempt(String username, boolean credentialsWereVerified) {
        Token incoming = new Token(username, false, Set.of());
        System.out.println("Submitted: " + incoming.authenticated());

        try {
            Token result = provider(incoming, credentialsWereVerified);
            System.out.println("Accepted: " + result.principal()
                    + ", authenticated=" + result.authenticated()
                    + ", authority=" + result.authorities().iterator().next());
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        attempt("learner", true);
        attempt("learner", false);
    }
}
~~~

Chạy:

~~~bash
javac AuthenticationTransitionDemo.java
java AuthenticationTransitionDemo
~~~

Stdout chính xác:

~~~text
Submitted: false
Accepted: learner, authenticated=true, authority=ROLE_LEARNER
Submitted: false
Rejected: Bad credentials
~~~

Giá trị `credentialsWereVerified` được truyền thủ công chỉ để mô phỏng kết quả của provider. Nó **không nhận password**, không có quy trình quản lý session, không dùng Spring Security API và **không được dùng làm cơ chế đăng nhập**. Điểm cần quan sát là token đầu vào không được coi là đã xác thực; chỉ khi provider cho kết quả thành công mới tạo một token kết quả chứa danh tính/authority đáng tin.

## 9. Sau khi thành công: SecurityContext, session và vòng đời thread

`AuthenticationManager.authenticate(...)` trả một `Authentication` thành công **chưa tự động** nói rằng mọi request tiếp theo đã đăng nhập. Còn các bước bên ngoài manager:

1. Authentication filter nhận result từ manager.
2. Một `SecurityContext` phù hợp được tạo/cập nhật để chứa result.
3. `SecurityContextHolder` gắn context vào **thread xử lý hiện tại**.
4. Theo cơ chế, authentication filter có thể thực thi `SessionAuthenticationStrategy` để xử lý session fixation, concurrent sessions hoặc chính sách khác.
5. Nếu đăng nhập stateful, context phải được lưu bởi cơ chế xác thực vào `SecurityContextRepository` phù hợp theo cấu hình; response có thể mang session cookie.
6. Success handler quyết định response (redirect, status, cookie...) theo kiểu authentication.
7. Khi security filter chain kết thúc, holder trên thread được dọn, nhưng context đã lưu trong session/repository có thể được nạp lại ở request sau.

Trong Spring Security Servlet hiện đại, `SecurityContextHolderFilter` cung cấp cơ chế nạp context (có thể trì hoãn) và **dọn holder** khi rời filter. Với mô hình **explicit-save**, filter này **không tự save context khi request kết thúc**; các thành phần authentication cần lưu vào repository khi muốn duy trì login. Form login do Spring Security cung cấp đã tích hợp quy trình lưu phù hợp; nếu tự viết authentication filter, phải kiểm soát cả bước save theo cấu hình hiện tại.

Một mảnh mã minh họa cho **authentication filter tùy chỉnh**, sau khi đã xác minh request:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Đây **chưa phải filter hoàn chỉnh**. Cần import `org.springframework.security.core.Authentication`, `org.springframework.security.core.context.SecurityContext`, `org.springframework.security.core.context.SecurityContextHolder` và các kiểu manager/repository; còn phải xử lý lỗi, session strategy, success/failure handler, CSRF, cookies và phương thức/URL đăng nhập. **Không bê nguyên đoạn này vào controller** để tạo một login mới thiếu những thành phần chuẩn. Nếu dùng filter có sẵn, ưu tiên cấu hình nó thay vì tự chép logic lõi.

**Dọn holder khác đăng xuất:** `SecurityContextHolder.clearContext()` chỉ gỡ context của thread; nó không vô hiệu hóa session hoặc xóa giá trị đã lưu. Đăng xuất phải dùng cơ chế logout của Spring Security và những thao tác cleanup repository/session phù hợp.

## 10. Xác thực thất bại đi theo nhánh nào?

Nếu credentials sai hoặc bị từ chối:

~~~text
Authentication filter
  -> AuthenticationManager.authenticate(...)
      -> AuthenticationException
  -> failure path:
       không tạo result đáng tin
       xóa/ngừng sử dụng context không hợp lệ của lần thử
       xử lý remember-me failure / session theo cấu hình
       failure handler hoặc AuthenticationEntryPoint tạo response
  -> không có authenticated principal mới được cấp bởi lần thử này
~~~

Với form login mặc định, thất bại thường dẫn đến redirect kiểu `/login?error`; với HTTP Basic thiếu/sai credentials, response thường là `401 Unauthorized` và có `WWW-Authenticate`; với bearer token không hợp lệ, thường là `401` theo cơ chế bearer token. Các status/header cụ thể phụ thuộc authentication entry point, failure handler và security chain của ứng dụng.

Không nên coi `ExceptionTranslationFilter` là nơi trực tiếp giải quyết **mọi** lỗi login: những authentication filter dựa trên `AbstractAuthenticationProcessingFilter` có luồng success/failure riêng. `ExceptionTranslationFilter` có vai trò chuyển `AuthenticationException` hoặc `AccessDeniedException` từ phần xử lý downstream thành hành vi HTTP phù hợp khi chúng lan tới nó.

Cần phân biệt:

| Trường hợp | Kết quả logic |
| --- | --- |
| Không có credentials, truy cập endpoint yêu cầu đăng nhập | Kích hoạt điểm vào xác thực phù hợp (redirect/401). |
| Có credentials nhưng sai | Authentication thất bại, không cấp principal xác thực mới. |
| Đã xác thực nhưng thiếu authority cho tài nguyên | Authorization thất bại; thường là `403 Forbidden`, có thể khác tùy ngữ cảnh. |
| Login thành công nhưng request sau vẫn anonymous | Kiểm tra session cookie, repository, explicit save, stateless policy và chain match. |

Các trường hợp trên có thể cùng dẫn tới một màn hình “không truy cập được”, nhưng cách sửa hoàn toàn khác: thiếu đăng nhập cần authentication; thiếu quyền cần authorization; mất đăng nhập giữa requests liên quan tới persistence và client cookie/session.

## 11. Các biến thể authentication không dùng password trong form

Cùng mô hình chung nhưng token và provider khác nhau:

| Cơ chế | Credentials đầu vào | Filter / provider điển hình | Có session mặc định? |
| --- | --- | --- | --- |
| Form login | Username + password form | `UsernamePasswordAuthenticationFilter` → `DaoAuthenticationProvider` | Thường dùng session cho trạng thái login ở web stateful. |
| HTTP Basic | `Authorization: Basic ...` | `BasicAuthenticationFilter` → provider username/password tương ứng | Không đòi hỏi phải tạo session chỉ để kiểm tra mỗi request; phụ thuộc policy chung. |
| OAuth2 Resource Server JWT | `Authorization: Bearer token` | `BearerTokenAuthenticationFilter` → `JwtAuthenticationProvider` / `JwtDecoder` | Thường stateless, xác thực token trên request hiện tại. |
| OAuth2 Resource Server opaque token | Bearer token | Bearer filter → `OpaqueTokenAuthenticationProvider` / introspector | Thường stateless, xác minh qua introspection. |
| SSO/OIDC login | Authorization code và các tham số phản hồi | Các filter/login handler của `oauth2Login`, client và provider phù hợp | Thường là login web có session, tùy cấu hình. |

Một ứng dụng có thể có nhiều `SecurityFilterChain`: ví dụ `/api/**` dùng bearer token và phần giao diện web dùng form login. Khi debug, phải xác nhận request **được chain nào chọn**. Không thể sửa authentication bằng cách thêm `DaoAuthenticationProvider` nếu request thực ra mang JWT và được resource-server chain xử lý.

Trong hệ thống REST, không nhất thiết phải lưu result vào HTTP session: khi bearer token được gửi ở mỗi request, provider xác minh lại hoặc dùng cache/kiểm tra phù hợp; `SecurityContext` của mỗi request vẫn tồn tại trong phạm vi cần authorize. `SessionCreationPolicy.STATELESS` không có nghĩa “bỏ SecurityContextHolder”.

## 12. Các sai lầm phổ biến

### Sai lầm A: “Có username nghĩa là đã đăng nhập”

Username là dữ liệu client gửi và có thể giả mạo. Chỉ provider hoặc cơ chế xác thực tin cậy mới cấp kết quả đã xác thực. Nếu code tự viết:

~~~java
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, authorityList
        );
~~~

thì code đã **tự khẳng định xác thực thành công** mà chưa kiểm chứng. Đây là **phản ví dụ bảo mật, tuyệt đối không áp dụng với input chưa tin cậy**. Nó cho thấy vì sao ứng dụng cần đi qua manager/provider, không trực tiếp tạo authenticated result từ user input.

### Sai lầm B: “UserDetailsService sẽ so password”

`UserDetailsService` chỉ nạp thông tin user; provider kết hợp dữ liệu với `PasswordEncoder.matches(...)` để quyết định. Nếu muốn đổi database, hãy thay adapter/service/repository thích hợp; đừng nhét password checking vào controller rồi gán flag.

### Sai lầm C: “Authenticated đồng nghĩa có mọi quyền”

Không. `Authentication` biểu thị xác thực, còn `AuthorizationFilter`, `AuthorizationManager`, method security và policy khác kiểm tra yêu cầu cụ thể. `ROLE_LEARNER` không tự được phép truy cập endpoint admin. Anonymous token và authority đặc biệt càng cho thấy cần dùng rule đúng nghĩa.

### Sai lầm D: “Mất context trong task async là login thất bại”

`SecurityContextHolder` theo mặc định gắn với thread hiện tại. Task chạy bởi `@Async`, `CompletableFuture` hoặc executor tự tạo không mặc nhiên có context của request. Cần truyền dữ liệu tối thiểu hoặc dùng cơ chế context propagation như các wrapper `DelegatingSecurityContext...` phù hợp; đảm bảo cleanup sau task. Không dùng `InheritableThreadLocal` làm giải pháp chung cho thread pool.

### Sai lầm E: “Đăng nhập thành công rồi là chắc chắn lưu session”

Với explicit-save và custom authentication flow, quên `SecurityContextRepository.saveContext(...)` có thể khiến request sau trở lại anonymous. Ngược lại, stateless token authentication hợp lệ có thể chủ động **không lưu** giữa requests. Hai mô hình khác nhau, không phải mô hình nào cũng cần session.

### Sai lầm F: “Phải tắt CSRF để test POST /login”

CSRF bảo vệ những request thay đổi trạng thái của browser sử dụng cookie. Test phải cung cấp CSRF token hợp lệ; tắt CSRF mà không đánh giá mô hình xác thực thực tế có thể tạo lỗ hổng. Spring Security Test cung cấp request builder phù hợp để kiểm tra form login.

### Sai lầm G: “Có bao nhiêu filter cũng giống nhau”

`UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter` và `BearerTokenAuthenticationFilter` có kiểu input, cách trigger, response và cơ chế xác thực khác nhau. `securityMatcher(...)` quyết định chain phù hợp; `requestMatchers(...)` trong `authorizeHttpRequests(...)` chỉ quyết định rule quyền bên trong chain. Đừng nhầm đường dẫn không chạy đúng chain với lỗi password.

### Sai lầm H: “Đổi isAuthenticated thành true để qua bước kiểm tra”

Chỉ authenticated flag không làm request đáng tin. Nếu ứng dụng tự đánh dấu token đã xác thực, nó có thể tạo lỗ hổng privilege escalation. Với mật khẩu, luôn dựa vào provider và encoder; với token, dựa vào verifier/decoder + policy đầy đủ.

## 13. Checklist triển khai và chẩn đoán theo thứ tự

1. **Xác định request thực tế:** endpoint, method, body/header và HTTPS; credentials đã tới server đúng định dạng chưa?
2. **Kiểm tra chain match:** `FilterChainProxy` có chọn đúng `SecurityFilterChain` không? Filter xác thực tương ứng có nằm trong chain không?
3. **Đối chiếu điều kiện filter:** form login nhận đúng `POST /login` và tên parameter chưa? CSRF token có hợp lệ? Basic/Bearer header đúng chuẩn?
4. **Kiểm tra token đầu vào:** kiểu `Authentication` có phù hợp manager/provider không, và `isAuthenticated()` ban đầu có là false?
5. **Kiểm tra provider:** có provider `supports(...)` token? `UserDetailsService` có tìm đúng user? account locked/disabled/expired không?
6. **Kiểm tra credentials:** `PasswordEncoder.matches(...)` có so với hash đúng định dạng không? BCrypt salted hash không nên được so bằng phép `equals` trực tiếp với raw password.
7. **Kiểm tra kết quả:** result authentication đã xác minh có principal và authorities đáng tin, không tự set flag từ client input?
8. **Kiểm tra SecurityContext:** filter có đặt result đúng vào holder trong lần thực thi hiện tại? Có cleanup ở cuối chain?
9. **Kiểm tra lưu login:** auth flow có lưu context vào repository khi cần? Client có giữ đúng session cookie? Có session fixation protection?
10. **Phân biệt authn/authz:** login hợp lệ nhưng bị `403` có thể là thiếu quyền; không nên tự sửa bằng cách bỏ authorization.
11. **Kiểm tra exception path:** sai password có bị xử lý như lỗi credentials an toàn, không tiết lộ user tồn tại hay password, không log secrets?
12. **Kiểm thử nhiều request/async:** user A và B không bị lẫn thread-local; request tiếp theo stateful có context đúng; task background được truyền context đúng theo thiết kế.

**Không log** raw password, Bearer access token, Basic header, session ID đầy đủ hoặc `Authentication.credentials`. Chỉ ghi thông tin chẩn đoán tối thiểu như correlation ID, loại cơ chế xác thực, request path và loại lỗi (đã được giảm nhạy cảm).

## 14. Câu hỏi tự kiểm tra

**Q1. Tại sao filter phải tạo một token chưa xác thực?** Vì credentials vừa tới từ client là dữ liệu chưa đáng tin. Provider phải kiểm chứng rồi mới tạo kết quả đã xác thực.

**Q2. `ProviderManager` khác `DaoAuthenticationProvider` như thế nào?** `ProviderManager` chọn/điều phối các provider theo loại token; `DaoAuthenticationProvider` là một cách xác thực username/password với `UserDetailsService` và `PasswordEncoder`.

**Q3. `UserDetailsService` có kiểm tra password không?** Không. Nó tải `UserDetails`; password match do provider/encoder và policy xác thực đảm trách.

**Q4. Kết quả `Authentication` thành công có tự lưu session không?** Không. Authentication filter/session strategy/repository thực hiện việc đưa vào context và lưu theo cấu hình. Resource server stateless có thể không lưu giữa requests.

**Q5. Login thành công nhưng không truy cập được tài nguyên admin nghĩa là password sai?** Không nhất thiết. Authentication có thể thành công, còn authorization từ chối do thiếu quyền.

**Q6. Form login sai password trả HTTP 401 hay redirect?** Mặc định với form login có thể redirect về `/login?error`; Basic/Bearer thường trả `401`. Cần nhìn cơ chế và handler thật thay vì gán một status cố định.

**Q7. Vì sao trong Spring Security không nên chỉ dựa vào `authentication.isAuthenticated()` để xem có người đăng nhập?** Vì token anonymous cũng có thể báo true, và quyết định truy cập cần xem loại authentication, authority và chính sách authorization.

**Ghi nhớ:** `credentials chưa tin cậy → authentication request chưa xác thực → AuthenticationManager/Provider kiểm chứng → Authentication result đã xác thực → SecurityContext → authorization và lưu trạng thái (nếu cần)`. Mỗi mũi tên là một ranh giới trách nhiệm riêng cần giữ đúng trong thiết kế bảo mật.
