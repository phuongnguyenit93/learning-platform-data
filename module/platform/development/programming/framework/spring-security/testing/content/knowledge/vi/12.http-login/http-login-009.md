# Remember-me và phạm vi cần kiểm tra bằng cookie thật

## 1. Tình huống và mục tiêu

Một ứng dụng có màn hình đăng nhập bằng username/password và ô **Remember me**. Người dùng đăng nhập, đóng trình duyệt hoặc để phiên HTTP hết hạn, rồi mở lại một trang yêu cầu xác thực. Ứng dụng có thể nhận diện người dùng nhờ cookie remember-me đã cấp trước đó. Chức năng này tạo ra một luồng xác thực riêng, vì vậy kiểm thử chỉ gọi `@WithMockUser` hoặc `with(user(...))` sẽ bỏ sót phần quan trọng nhất.

Sau bài học, người học có thể:

1. Phân biệt session cookie, remember-me cookie và thông tin xác thực gắn trực tiếp vào request kiểm thử.
2. Dùng **MockMvc và spring-security-test** để thực hiện form login thật qua chuỗi filter, lấy cookie của response rồi gửi chính cookie đó trong request mới.
3. Kiểm tra điều kiện phát hành cookie, các thuộc tính HTTP, khả năng khôi phục xác thực, phân quyền cho remember-me và cơ chế từ chối cookie lỗi.
4. Xác định ca nào MockMvc kiểm chứng được và ca nào cần HTTP client hoặc trình duyệt thực.
5. Thiết kế bộ kiểm thử cho cả remember-me dựa trên chữ ký và remember-me dùng persistent token.

Phạm vi ví dụ chính là **Spring Security trên Servlet stack** với `SecurityFilterChain`, `formLogin`, `RememberMeAuthenticationFilter` và `MockMvc`. Cơ chế bảo mật trên WebFlux/Reactive có bộ lọc và API khác; không lấy nguyên cấu hình Servlet này áp dụng cho `SecurityWebFilterChain`.

## 2. Remember-me thực sự hoạt động như thế nào?

Remember-me không phải là cách kéo dài `JSESSIONID`. Nó là một cơ chế cho phép máy chủ xác thực lại người dùng từ một cookie dài hạn khi request mới không có phiên đăng nhập hợp lệ.

```mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant F as Spring Security filters
    participant R as RememberMeServices
    participant P as Nguồn người dùng/token
    U->>F: POST /login + username/password + remember-me
    F->>R: Đăng nhập tương tác thành công
    R-->>U: Set-Cookie: remember-me=...; Max-Age=...
    Note over U: Không còn phiên đăng nhập cũ
    U->>F: GET /me với Cookie: remember-me=...
    F->>R: Kiểm tra cookie vì chưa có Authentication
    R->>P: Tải UserDetails hoặc xác minh persistent token
    P-->>R: Thông tin hợp lệ
    R-->>F: RememberMeAuthenticationToken
    F-->>U: Trang được phép truy cập theo chính sách
```

Đối với Servlet, hai chiến lược phổ biến là:

| Chiến lược | Dữ liệu cookie | Xác minh ở máy chủ | Hệ quả kiểm thử |
| --- | --- | --- | --- |
| `TokenBasedRememberMeServices` | Thông tin người dùng, thời hạn và chữ ký có dùng khóa bí mật | Kiểm tra chữ ký, thời hạn và `UserDetails` hiện hành | Đổi mật khẩu/khóa có thể làm cookie cũ mất hiệu lực; chỉ xóa cookie ở trình duyệt không thu hồi được bản cookie đã bị sao chép |
| `PersistentTokenBasedRememberMeServices` | `series` và token ngẫu nhiên | Đối chiếu `PersistentTokenRepository`; thông thường xoay token sau mỗi lần dùng | Phải kiểm tra cả kho token, việc xoay token, logout/thu hồi và việc phát lại token cũ |

Cả hai triển khai chuẩn cần `UserDetailsService` để lấy lại người dùng khi khôi phục xác thực. Nếu hệ thống chỉ có JWT/OAuth2 hoặc một authentication provider không dựa trên `UserDetailsService`, cần cấu hình dịch vụ phù hợp; bật `rememberMe()` một cách máy móc không đủ để bảo đảm luồng này chạy.

**Điểm bảo mật then chốt:** Xác thực từ remember-me thường tạo `RememberMeAuthenticationToken`. Với `authenticated()`, request này được xem là đã xác thực; với `fullyAuthenticated()`, nó không đủ mức tin cậy như lần đăng nhập tương tác. Đây là khác biệt cần kiểm tra bằng endpoint thật.

## 3. Cookie nào cần theo dõi?

Đừng chỉ kiểm tra rằng response có *một* cookie. Một ứng dụng có thể phát hành `JSESSIONID`, cookie CSRF, cookie tùy chỉnh và cookie remember-me cùng lúc.

| Dấu hiệu | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| Tên, ví dụ `remember-me` | Phải khớp tên mà `RememberMeServices` cấu hình | Tìm đúng cookie trong response; không nhầm với `JSESSIONID` |
| Giá trị không rỗng | Token đã được phát hành | Kiểm tra tồn tại, tránh in token thật ra log |
| `Max-Age` hoặc `Expires` | Chính sách lưu cookie phía trình duyệt | Đối chiếu chính sách dự kiến; không coi đây là bằng chứng máy chủ chắc chắn sẽ từ chối token hết hạn |
| `HttpOnly` | JavaScript trình duyệt không đọc trực tiếp cookie | Xem `Set-Cookie` và kiểm tra trong môi trường HTTP thực |
| `Secure` | Trình duyệt chỉ gửi trên kết nối bảo mật theo quy tắc cookie | Kiểm thử trên HTTPS hoặc cấu hình proxy đáng tin cậy |
| `SameSite` | Hạn chế gửi cookie trong một số ngữ cảnh cross-site | Kiểm tra header; kiểm chứng hành vi thực trong trình duyệt |
| `Path`, `Domain` | Giới hạn URL/host nhận cookie | Kiểm tra phạm vi dự kiến; test request sai path hoặc host khi cần |

Một cookie có `HttpOnly` và `Secure` vẫn có thể bị lạm dụng nếu token bị đánh cắp bằng cách khác. `SameSite` không thay cho CSRF protection. Thuộc tính cookie do ứng dụng, phiên bản framework và lớp Servlet/container cấu hình quyết định; **chỉ assert một giá trị cụ thể khi chính sách của ứng dụng có yêu cầu đó**.

## 4. Chuẩn bị ứng dụng Servlet mẫu

Ví dụ mã bên dưới dùng cấu trúc dependency và import của **Spring Boot 3.x / Spring Security 6.x**, với `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test`. Ở dự án dùng Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Nếu dùng Spring Boot 4.x:** bổ sung dependency test `org.springframework.boot:spring-boot-starter-webmvc-test` và thay import `AutoConfigureMockMvc` thành `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc`. Spring Boot 4 đã tách gói kiểm thử MVC; ví dụ import của Boot 3 sẽ không biên dịch trực tiếp trên Boot 4. Phần ý tưởng kiểm thử cookie và các API của Spring Security bên dưới vẫn tương ứng.

Đặt chính sách truy cập có chủ đích: `/me` chấp nhận mọi Authentication hợp lệ; `/step-up` yêu cầu người dùng đăng nhập tương tác. Tên người dùng, mật khẩu và khóa bên dưới **chỉ dành cho môi trường kiểm thử minh họa**.

```java
@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, UserDetailsService users) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/step-up").fullyAuthenticated()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .userDetailsService(users)
                .key("example-test-key-not-for-production")
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60));
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}secret") // Chỉ dùng trong ví dụ test.
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class SessionProbeController {
    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/step-up")
    String stepUp() {
        return "sensitive action permitted";
    }
}
```

Các import tương ứng nằm trong `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.core.userdetails.*`, `org.springframework.security.provisioning.InMemoryUserDetailsManager`, `org.springframework.context.annotation.*`, `org.springframework.security.config.Customizer` và `org.springframework.web.bind.annotation.*`.

Mẫu này dùng remember-me dựa trên chữ ký. Trong sản phẩm thực tế, khóa phải là bí mật ổn định được bảo vệ, mật khẩu phải mã hóa phù hợp và cấu hình cookie cần khớp môi trường HTTPS. Cấu hình `alwaysRemember(true)` sẽ làm thay đổi kỳ vọng về trường hợp người dùng không đánh dấu ô Remember me; ví dụ này giữ mặc định **chỉ nhớ khi yêu cầu**.

## 5. Kiểm thử bằng MockMvc: phát hành cookie rồi tái sử dụng

Ở tầng này cần dùng `@SpringBootTest` và `@AutoConfigureMockMvc` (hoặc xây `MockMvc` từ `WebApplicationContext` rồi `apply(springSecurity())`) để request đi qua Spring Security filter chain. Nếu chỉ gọi trực tiếp controller hoặc gắn `@WithMockUser`, bài test không đi qua quá trình form login cấp cookie.

Ví dụ dưới đây giả định các bean ở mục 4 có trong context:

```java
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.security.authentication.RememberMeAuthenticationToken;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeCookieTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        MockHttpServletRequestBuilder request = post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "secret");

        if (remember) {
            request.param("remember-me", "true");
        }
        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    @Test
    void checkedRememberMeIssuesCookie() throws Exception {
        MvcResult loginResult = login(true);
        Cookie cookie = loginResult.getResponse().getCookie("remember-me");

        assertThat(cookie).isNotNull();
        assertThat(cookie.getValue()).isNotBlank();
        assertThat(cookie.getMaxAge()).isPositive();
        assertThat(cookie.isHttpOnly()).isTrue();
    }

    @Test
    void uncheckedRememberMeDoesNotIssueCookie() throws Exception {
        MvcResult loginResult = login(false);
        assertThat(loginResult.getResponse().getCookie("remember-me"))
            .isNull();
    }

    @Test
    void actualCookieRestoresIdentityWithoutOldSession() throws Exception {
        Cookie remember = login(true).getResponse().getCookie("remember-me");
        assertThat(remember).isNotNull();

        // Không mang MockHttpSession của lần login sang request mới.
        mvc.perform(get("/me").cookie(remember))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"))
            .andExpect(authenticated().withAuthentication(authentication ->
                assertThat(authentication)
                    .isInstanceOf(RememberMeAuthenticationToken.class)));
    }

    @Test
    void rememberMeDoesNotPassFullyAuthenticatedRule() throws Exception {
        Cookie remember = login(true).getResponse().getCookie("remember-me");
        assertThat(remember).isNotNull();

        mvc.perform(get("/step-up").cookie(remember))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void interactiveLoginSessionPassesFullyAuthenticatedRule()
            throws Exception {
        MvcResult loginResult = login(true);
        MockHttpSession session =
            (MockHttpSession) loginResult.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/step-up").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void invalidCookieCannotRestoreIdentity() throws Exception {
        Cookie forged = new Cookie("remember-me", "not-a-valid-token");

        mvc.perform(get("/me").cookie(forged))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutClearsRememberMeCookieInBrowserResponse()
            throws Exception {
        MvcResult loginResult = login(true);
        Cookie remember = loginResult.getResponse().getCookie("remember-me");
        MockHttpSession session =
            (MockHttpSession) loginResult.getRequest().getSession(false);
        assertThat(remember).isNotNull();
        assertThat(session).isNotNull();

        mvc.perform(post("/logout")
                .session(session)
                .cookie(remember)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(cookie().maxAge("remember-me", 0));
    }
}
```

**Vì sao phải lấy cookie từ response?** Nếu tự tạo `new Cookie("remember-me", "abc")` để kiểm thử trường hợp thành công, ta không chứng minh ứng dụng đã ký/phát hành một token có thể dùng được. Chỉ dùng cookie tự tạo để kiểm thử trường hợp **bị từ chối**. Tương tự, `@WithMockUser`, `with(user("alice"))` hoặc đặt thủ công `SecurityContext` chỉ chứng minh quyết định phân quyền trong một request giả lập; chúng không kích hoạt đầy đủ luồng Remember-me.

Ở `actualCookieRestoresIdentityWithoutOldSession`, chi tiết quan trọng nhất là **không truyền session** từ lần login sang lần GET. Nếu truyền session cũ, request có thể thành công bằng session authentication dù remember-me hoàn toàn hỏng. Assertion về `RememberMeAuthenticationToken` giúp phát hiện lỗi kiểm thử kiểu này.

Các test trên giả định `formLogin` điều hướng người dùng chưa đăng nhập tới trang login (thường HTTP 302). Khi ứng dụng dùng entry point dành cho REST API, trường hợp bị từ chối có thể trả 401 hoặc 403 theo cấu hình. Hãy kiểm tra **mã HTTP theo security policy của ứng dụng**, không ép mọi ứng dụng phải redirect.

## 6. Assert cookie ở đúng tầng HTTP

`MockHttpServletResponse.getCookie(...)` tiện để xác nhận Servlet đã phát hành cookie qua `addCookie`. Để kiểm tra các thuộc tính trình duyệt nhận được, cần quan sát trực tiếp các header `Set-Cookie`:

```java
MvcResult result = mvc.perform(
        post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "secret")
            .param("remember-me", "true"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

var setCookieHeaders = result.getResponse().getHeaders("Set-Cookie");
assertThat(setCookieHeaders)
    .anySatisfy(header ->
        assertThat(header).contains("remember-me="));
```

Nếu hệ thống có yêu cầu `SameSite=Lax` hoặc `SameSite=Strict`, hãy assert trên **header chứa đúng cookie remember-me**, đồng thời kiểm tra ứng dụng/container thực sự phát hành thuộc tính ấy. `getCookie(...)` có thể không biểu diễn đầy đủ các thuộc tính mở rộng như `SameSite`. Không nối tất cả header rồi kiểm tra từ khóa một cách mù quáng: thuộc tính mong muốn có thể thuộc cookie khác.

Một số lỗi cần tránh:

- `Set-Cookie` là **response header** từ server; `Cookie` là **request header** browser gửi lại. Hai header này có định dạng và mục đích khác nhau.
- `MockMvc` không tự vận hành cookie jar hay các quy tắc trình duyệt. Trong lần GET, phải dùng `.cookie(remember)` hoặc đặt request cookie rõ ràng.
- Nếu ứng dụng cấp lại cookie remember-me sau một request (đặc biệt khi xoay persistent token), request tiếp theo phải mang **giá trị mới nhất**.
- Cần phân biệt xác thực nhờ remember-me và xác thực nhờ `HttpSession`: không reuse session khi đang kiểm thử khả năng khôi phục.
- Đừng ghi nguyên giá trị remember-me token, `Set-Cookie` hay mật khẩu vào log CI; các giá trị này có thể là credential.

### Kiểm thử `Secure` và phạm vi cookie

Nếu chính sách yêu cầu remember-me cookie chỉ được gửi trên HTTPS, hãy dùng request mô phỏng kết nối HTTPS trong MockMvc hoặc chạy test với server HTTPS thực:

```java
MvcResult result = mvc.perform(
        post("/login")
            .secure(true)
            .with(csrf())
            .param("username", "alice")
            .param("password", "secret")
            .param("remember-me", "true"))
    .andReturn();

Cookie remember = result.getResponse().getCookie("remember-me");
assertThat(remember).isNotNull();
assertThat(remember.getSecure()).isTrue();
```

Ví dụ phụ thuộc cấu hình remember-me theo trạng thái HTTPS của request. Nếu ứng dụng chủ động đặt thuộc tính `Secure` hoặc chạy sau reverse proxy, hãy so sánh với chính cấu hình đó. Một test MockMvc thành công **chưa chứng minh** trình duyệt sẽ từ chối gửi cookie qua HTTP, hoặc `Path`/`Domain`/`SameSite` hoạt động đúng trong tình huống cross-site. Các hành vi ấy cần kiểm tra bằng client thực hoặc trình duyệt.

## 7. Ma trận ca kiểm thử nên có

| Ca | Kích thích | Kết quả cần chứng minh |
| --- | --- | --- |
| Login + tick remember-me | Form login hợp lệ kèm `remember-me=true` | Response phát cookie remember-me hợp lệ |
| Login không tick | Form login hợp lệ, thiếu tham số nhớ đăng nhập | Không cấp cookie remember-me trong cấu hình opt-in |
| Login thất bại | Sai mật khẩu kèm remember-me | Không cấp credential remember-me hợp lệ |
| Cookie hợp lệ, không có session | GET protected endpoint chỉ với cookie đã nhận | Tạo `RememberMeAuthenticationToken` và truy cập đúng chính sách |
| Không có cookie và session | GET protected endpoint | Chuyển tới login hoặc trả 401 theo entry point |
| Cookie sai/chỉnh sửa | Đổi một phần giá trị cookie | Không được xác thực; không trả 500 hoặc lộ thông tin token |
| Cookie hết hạn | Token hết hạn theo xác minh server | Từ chối khôi phục xác thực, xử lý response an toàn |
| Cookie của tài khoản bị khóa/xóa | Thay trạng thái `UserDetails` sau khi phát hành | Không tiếp tục xác thực tài khoản không còn hợp lệ |
| Endpoint cần `authenticated()` | GET chỉ với remember-me | Được phép nếu role/authority cũng đáp ứng |
| Endpoint cần `fullyAuthenticated()` | GET chỉ với remember-me | Bị yêu cầu đăng nhập lại hoặc bị từ chối theo chính sách |
| Logout | POST logout hợp lệ với CSRF | Trả cookie xóa phía client; nếu dùng persistent token, xác minh cơ chế thu hồi phía server |
| Persistent token rotation | Dùng token một lần rồi gửi request mới | Lần sử dụng tạo token mới; client dùng token mới nhất |
| Persistent token replay | Dùng lại giá trị cũ sau rotation | Bị từ chối theo cơ chế phát hiện token không khớp và chính sách xử lý |
| Cookie flags | Login trên môi trường HTTPS | `Secure`, `HttpOnly`, `SameSite`, `Path`, `Max-Age` khớp hợp đồng |
| Session không che lỗi | Request GET khôi phục không mang session login | Bảo đảm bài test thực sự đi qua remember-me |

Không nhất thiết mỗi hàng là một test độc lập; có thể gộp những assertion cùng một kịch bản. Tuy vậy, nên có **một test tái sử dụng cookie được cấp thật và một test xác nhận loại Authentication**, vì đó là bằng chứng chính của luồng remember-me.

## 8. Trường hợp persistent token cần chú ý hơn

Với `PersistentTokenBasedRememberMeServices`, repository phổ biến là `JdbcTokenRepositoryImpl` và bảng mặc định có các cột:

```sql
CREATE TABLE persistent_logins (
    username  VARCHAR(64) NOT NULL,
    series    VARCHAR(64) PRIMARY KEY,
    token     VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Để chuyển từ token theo chữ ký sang persistent token, ứng dụng cần cấu hình `PersistentTokenRepository` phù hợp (ví dụ datasource test) và tích hợp nó vào remember-me services. Đây là một thành phần trạng thái, nên kiểm thử chỉ dựa vào HTTP response là chưa đủ. Với database dùng cho test, cần xác minh vòng đời:

1. Form login có remember-me tạo bản ghi token tương ứng.
2. Truy cập với cookie không kèm session khôi phục người dùng và cập nhật token theo chính sách rotation.
3. Cookie từ **response mới** phải được đưa vào request tiếp theo; cookie cũ có thể bị xem là replay.
4. Logout được thực hiện trong ngữ cảnh có `Authentication` phù hợp phải thu hồi token thuộc người dùng theo cơ chế tích hợp.
5. Tài khoản bị xóa, bị khóa hoặc token không còn trong kho không được tiếp tục truy cập.

Một test có giá trị là lưu `oldCookie`, gọi GET với `oldCookie` để lấy `rotatedCookie`, sau đó kiểm tra repository và dùng `rotatedCookie` cho lần GET kế tiếp. Không dùng cùng một cookie cũ cho nhiều request rồi kết luận "remember-me ngẫu nhiên lỗi": với persistent token, hành vi rotation là có chủ đích.

Không dùng chung repository chứa token của các test khi chạy song song nếu chúng có thể thao tác lên cùng người dùng hoặc `series`. Dùng dữ liệu cách ly, transaction/cleanup thích hợp hoặc test database riêng. Chỉ assert chi tiết SQL theo contract cụ thể, tránh buộc mọi triển khai persistent token phải trùng một thuật toán nội bộ.

**Giới hạn thu hồi cần hiểu rõ:** Với triển khai remember-me dựa trên chữ ký, logout thông thường có thể chỉ phát cookie hết hạn để trình duyệt xóa cookie. Một bản sao token cũ đã bị lấy trước đó có thể tiếp tục được xác minh cho tới khi hết hạn hoặc khi yếu tố ký/xác minh thay đổi. Vì vậy không viết test yêu cầu "logout làm mọi bản sao cookie chữ ký cũ lập tức vô hiệu" nếu ứng dụng chưa thiết kế một cơ chế thu hồi phía server.

## 9. Khi nào cần HTTP client hoặc trình duyệt thật?

MockMvc đi qua xử lý Spring MVC và các security filter, nhưng request/response là Servlet mock và không có server network thực. Nó xác minh rất tốt logic xác thực, authorization và cookie ứng dụng tạo ra; nó không mô phỏng đầy đủ browser cookie jar, TLS, proxy hay chính sách cross-site.

| Tầng kiểm thử | Công cụ gợi ý | Có thể chứng minh | Chưa chứng minh |
| --- | --- | --- | --- |
| Security unit test | `@WithMockUser`, `with(user(...))` | Quy tắc phân quyền theo principal/role | Login, cấp cookie, khôi phục remember-me |
| Servlet integration | `MockMvc` + `spring-security-test` | Form login qua filter; lấy và tái gửi cookie; phân biệt remember-me/full authentication | Cookie jar, trình duyệt và kết nối mạng thật |
| HTTP integration | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client có cookie store | Server thực phát `Set-Cookie`, client gửi `Cookie`, HTTP status và redirect thật | Một số chính sách trình duyệt như `SameSite` |
| Browser E2E | Playwright/Selenium qua HTTPS | Browser lưu/xóa cookie, `Secure`, `SameSite`, path/domain, reload và phiên mới | Không thay thế được test repository/token trên server |

Một kịch bản HTTP/browser chuẩn:

1. Khởi động server trong môi trường test tách biệt; truy cập form login để lấy CSRF token nếu ứng dụng yêu cầu.
2. Gửi POST login hợp lệ với checkbox Remember me, xác nhận response có `Set-Cookie` cho remember-me.
3. Để client lưu remember-me; **xóa hoặc loại bỏ session cookie riêng biệt** để mô phỏng phiên cũ không còn, nhưng giữ remember-me cookie.
4. Tạo request GET mới đến endpoint yêu cầu xác thực; kiểm tra trạng thái và danh tính trả về.
5. Dùng endpoint nhạy cảm yêu cầu xác thực đầy đủ; xác nhận bị từ chối hoặc yêu cầu login lại.
6. Logout rồi kiểm tra browser xóa cookie, đồng thời đối chiếu chính sách thu hồi phía server.

Ví dụ với `java.net.http.HttpClient` có `CookieManager`, người học có thể tạo client như sau (phần thu thập và gửi CSRF token phụ thuộc form thực tế):

```java
CookieManager jar = new CookieManager();
jar.setCookiePolicy(CookiePolicy.ACCEPT_ALL);

HttpClient client = HttpClient.newBuilder()
    .cookieHandler(jar)
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

// 1. GET login page, nhận CSRF token theo cơ chế của ứng dụng.
// 2. POST username/password/remember-me cùng CSRF token.
// 3. Kiểm tra CookieStore có remember-me.
// 4. Xóa session cookie trong CookieStore, giữ remember-me.
// 5. GET /me bằng chính client để kiểm tra xác thực được khôi phục.
```

Khi test qua HTTPS, client phải xác minh TLS đúng cách. Không vô hiệu CSRF, hostname verification hay certificate validation chỉ để làm cho bài test "xanh". Với browser E2E, kiểm tra cookie từ API của trình duyệt và quan sát network request để xác minh browser thực sự gửi cookie đến đúng domain/path.

## 10. Các bẫy thường gặp và cách chẩn đoán

**Test thành công dù remember-me đã bị tắt.** Nguyên nhân thường là request thứ hai tái sử dụng `MockHttpSession`, cấu hình `@WithMockUser` đang áp dụng, hoặc gọi endpoint công khai. Cách sửa: request GET chỉ có cookie remember-me, endpoint phải yêu cầu auth, kiểm tra `RememberMeAuthenticationToken`.

**Test luôn redirect dù cookie vừa được cấp.** Kiểm tra đúng tên cookie, request có đi qua Spring Security filter chain hay không, `UserDetailsService` có tra được người dùng, remember-me key có nhất quán giữa hai request, và cookie bị thay thế sau rotation hay chưa. Nếu dùng nhiều `SecurityFilterChain`, phải kiểm tra request thực sự khớp chain có remember-me.

**Form login nhận 403 trước khi cấp cookie.** Xác minh CSRF token của request POST login; `with(csrf())` của `spring-security-test` dùng cho MockMvc. Không tắt CSRF ở toàn ứng dụng chỉ để tránh cấu hình test.

**Assert `Secure` sai khi chạy qua proxy.** `request.isSecure()` phía Servlet có thể không phản ánh HTTPS phía client nếu cấu hình forwarded headers/proxy không đúng. Cần kiểm thử hạ tầng hoặc thiết lập cookie secure tường minh theo chính sách triển khai.

**Không thấy `SameSite` trong `Cookie` Java.** Đây là thuộc tính của `Set-Cookie`, không phải luôn có trong model cookie Servlet. Kiểm tra response header và một ca E2E trong browser nếu chính sách cross-site quan trọng.

**Cookie cũ tự nhiên ngừng hoạt động khi dùng persistent token.** Token mới có thể đã được phát hành sau lần khôi phục trước; sử dụng cookie mới nhất và quan sát repository. Không chạy nhiều request song song bằng cùng một cookie nếu sản phẩm không hỗ trợ tình huống đó.

**Logout "thành công" nhưng cookie sao chép vẫn xác thực.** Phân biệt xóa cookie tại client với thu hồi credential phía server. Chỉ yêu cầu thu hồi ngay lập tức khi chiến lược/token store thực sự hỗ trợ.

**Test hết hạn dựa vào `Thread.sleep` lâu.** Dễ chậm và thiếu ổn định. Ưu tiên clock điều khiển được, cấu hình TTL ngắn trong test có chủ đích, token fixture có thời hạn đã qua hoặc kiểm chứng trực tiếp service xác minh theo thiết kế. Không suy ra token đã hết hạn ở server chỉ từ `Max-Age` trên response.

## 11. Bài thực hành và tiêu chí đạt

**Bài 1 — Cookie opt-in:** Tạo hai test login với và không có `remember-me=true`. Chỉ lần tick checkbox mới được phát remember-me cookie trong cấu hình opt-in. Login sai mật khẩu không được cấp cookie hợp lệ.

**Bài 2 — Khôi phục sau session:** Dùng remember-me cookie của response login để GET `/me` trong một request không có session. Kiểm tra tên người dùng và kiểu `RememberMeAuthenticationToken`. Sau đó bỏ cookie khỏi request, xác nhận không còn truy cập được.

**Bài 3 — Phân biệt mức tin cậy:** Dùng cùng cookie truy cập endpoint `authenticated()` và `fullyAuthenticated()`. Giải thích tại sao kết quả khác nhau dù đều có danh tính.

**Bài 4 — Token giả và logout:** Sửa giá trị cookie, xác nhận server từ chối an toàn; gọi logout có CSRF token và kiểm tra cookie xóa trong response. Nếu ứng dụng dùng persistent token, kiểm tra trạng thái repository sau logout.

**Bài 5 — HTTP/browser thật:** Chạy app bằng server test, dùng HTTP client có cookie jar hoặc browser tự động; xác nhận cookie sống qua request không còn session và `Secure`/`SameSite`/`Path` được thực thi đúng với cấu hình môi trường.

Một bài làm đạt yêu cầu phải chứng minh được **đường đi của cookie từ `Set-Cookie` đến `Cookie` trong request mới**, loại Authentication sau khi khôi phục và kết quả phân quyền thực tế. Các test chỉ dùng principal giả lập vẫn hữu ích cho authorization, nhưng chưa đáp ứng mục tiêu remember-me của bài này.

## 12. Tài liệu tham khảo

- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html): hai mô hình token, `UserDetailsService` và repository.
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): tích hợp filter chain với MockMvc.
- [Spring Security — Testing Form Based Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): helper `formLogin` và luồng xác thực biểu mẫu.
- [Spring Security — SecurityMockMvcResultMatchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): assert trạng thái xác thực.
- [Spring Framework — MockMvc vs End-to-End Tests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/vs-end-to-end-integration-tests.html): giới hạn của Servlet mock so với HTTP server thực.
