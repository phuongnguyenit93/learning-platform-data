# logout với URL, HTTP method và CSRF đúng cấu hình

## 1. Đăng xuất là một request được bảo vệ

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, kiểm thử logout cần xác nhận đúng request mới thực hiện việc kết thúc phiên đăng nhập. Một request sai URL, sai HTTP method hoặc thiếu CSRF token không được vô tình đăng xuất người dùng.

Với ứng dụng Servlet dùng form login, Spring Security cung cấp **LogoutFilter** để nhận diện request logout, gọi các handler xóa trạng thái bảo mật và chuyển tiếp đến trang hoặc handler thông báo thành công. Request logout phải khớp với **URL và HTTP method** đã cấu hình. Khi CSRF được bật (mặc định), logout tiêu chuẩn dùng **POST** và cần token hợp lệ.

Sau bài này, bạn có thể:

- Hiểu URL và HTTP method mặc định của logout trong Spring Security.
- Phân biệt trang xác nhận logout qua GET với request thực sự thực hiện logout qua POST.
- Cấu hình URL logout, success URL và xóa cookie.
- Kiểm thử POST logout hợp lệ, thiếu CSRF, sai method và sai URL bằng MockMvc.
- Xác minh session bị vô hiệu hóa và request tiếp theo cần đăng nhập lại.
- Phân biệt logout dựa trên HTTP session với việc thu hồi bearer token trong API stateless.

## 2. LogoutFilter khớp URL và HTTP method

Trong cấu hình form login mặc định, Spring Security sử dụng đường dẫn **/logout** cho logout. Khi CSRF protection được bật, request thực hiện logout mặc định là:

~~~http
POST /logout
Content-Type: application/x-www-form-urlencoded

_csrf=<valid-token>
~~~

**GET /logout không phải request thực hiện logout** trong cấu hình mặc định có CSRF. Nếu trang logout mặc định được bật, GET /logout có thể hiển thị trang xác nhận chứa form gửi POST và CSRF token. Khi dùng trang logout tùy chỉnh hoặc không bật trang mặc định, phản hồi GET có thể khác; điều quan trọng là GET không khớp với matcher POST của LogoutFilter.

~~~mermaid
flowchart TD
    A["Request đến ứng dụng"] --> B{"URL có khớp /logout?"}
    B -->|Không| C["Tiếp tục filter chain bình thường"]
    B -->|Có| D{"HTTP method là POST?"}
    D -->|Không| E["Không thực hiện logout"]
    D -->|Có| F{"CSRF token hợp lệ?"}
    F -->|Không| G["403 Forbidden"]
    F -->|Có| H["LogoutFilter gọi LogoutHandler"]
    H --> I["Xóa Authentication / invalidate session"]
    I --> J["LogoutSuccessHandler"]
    J --> K["Redirect hoặc response thành công"]
~~~

Nếu CSRF bị tắt, matcher logout mặc định có thể chấp nhận các HTTP method khác nhau. Điều đó không có nghĩa nên dùng GET để logout. GET được kỳ vọng là thao tác an toàn, không làm thay đổi trạng thái server; để tránh logout ngoài ý muốn do link, crawler hoặc prefetch, hãy giữ logout bằng POST có CSRF cho ứng dụng trình duyệt dùng session.

## 3. Cấu hình logout trong ứng dụng Servlet

Ví dụ sử dụng **Spring Boot 3.x**, **Spring Security 6.x**, Spring MVC, form login và session. Ứng dụng có người dùng alice và endpoint profile cần xác thực.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/profile").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("secret"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Endpoint minh họa:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Trong cấu hình trên:

- **logoutUrl("/logout")** xác định đường dẫn logout. Khi CSRF đang bật, request mặc định phải là POST.
- **logoutSuccessUrl("/login?logout")** chuyển hướng sau khi logout thành công. URL đích nên được phép truy cập công khai.
- **invalidateHttpSession(true)** yêu cầu vô hiệu hóa HTTP session hiện tại.
- **clearAuthentication(true)** xóa Authentication khỏi SecurityContext.
- **deleteCookies("JSESSIONID")** yêu cầu response xóa cookie session phía client bằng cookie cùng tên.

Các hành vi invalidate session và clear Authentication cũng là mặc định của cấu hình logout tiêu chuẩn; khai báo tường minh trong ví dụ giúp người đọc thấy rõ ý định và làm cho chính sách dễ rà soát. Xóa cookie ở trình duyệt là bước riêng: **cookie bị xóa không tự thay thế việc vô hiệu hóa session phía server**, và vô hiệu hóa session phía server cũng không tự bảo đảm mọi cookie liên quan được xóa khỏi client.

Nếu ứng dụng dùng tên cookie session tùy chỉnh, hãy xóa đúng tên cookie đã cấu hình. Nếu có nhiều cookie hoặc nhiều cơ chế xác thực, cần xác định rõ cookie/token nào thuộc phiên cần kết thúc.

## 4. Đổi URL logout hoặc định nghĩa matcher riêng

Nếu ứng dụng muốn dùng **/signout**, hãy thay logout URL:

~~~java
.logout(logout -> logout
    .logoutUrl("/signout")
    .logoutSuccessUrl("/login?logout")
)
~~~

Với CSRF protection đang bật, Spring Security tiếp tục yêu cầu POST cho URL logout mới. Request **POST /logout** cũ không còn là URL logout được cấu hình; request **POST /signout** mới thực hiện logout.

Nếu cần kiểm soát rõ cả path lẫn method, có thể đặt matcher tường minh:

~~~java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

.logout(logout -> logout
    .logoutRequestMatcher(
        new AntPathRequestMatcher("/signout", "POST")
    )
    .logoutSuccessUrl("/login?logout")
)
~~~

Matcher trên chỉ khớp **POST /signout**. Hãy giữ CSRF protection và gửi token hợp lệ cho request này. Với ứng dụng đang dùng phiên bản Spring Security mới hơn, hãy kiểm tra API matcher phù hợp với phiên bản của dự án; mục tiêu vẫn là giới hạn chính xác path và HTTP method.

Không nên cấu hình logout bằng GET chỉ để tiện đặt một liên kết. Nếu người dùng nhấn một đường dẫn GET, trình duyệt, crawler hoặc cơ chế prefetch có thể kích hoạt thao tác thay đổi trạng thái ngoài ý muốn. Với ứng dụng dùng cookie session, hãy dùng form POST có CSRF token.

## 5. Kiểm thử logout bằng MockMvc

Bộ kiểm thử dưới đây xác minh request logout thực sự đi qua filter chain. Test đăng nhập alice trước, lấy session từ request login, rồi gửi request logout bằng chính session đó.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutRequestTest {

    @Autowired
    MockMvc mockMvc;

    private MockHttpSession loginAsAlice() throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertThat(saved).isInstanceOf(SecurityContext.class);
        assertThat(((SecurityContext) saved).getAuthentication().getName())
                .isEqualTo("alice");

        return session;
    }

    @Test
    void postLogoutWithValidCsrfInvalidatesSession() throws Exception {
        MockHttpSession session = loginAsAlice();

        mockMvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));

        assertThat(session.isInvalid()).isTrue();

        mockMvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void postLogoutWithoutCsrfIsRejectedAndKeepsLogin() throws Exception {
        MockHttpSession session = loginAsAlice();

        mockMvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();

        mockMvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void getLogoutDoesNotPerformLogout() throws Exception {
        MockHttpSession session = loginAsAlice();

        // GET có thể hiển thị trang xác nhận hoặc response theo cấu hình.
        // Kiểm tra hành vi bảo mật thay vì phụ thuộc nội dung trang.
        mockMvc.perform(get("/logout").session(session));

        assertThat(session.isInvalid()).isFalse();

        mockMvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

### 5.1. Kiểm tra logout thành công

Ca test **postLogoutWithValidCsrfInvalidatesSession** kiểm tra ba kết quả:

1. POST /logout có session đã đăng nhập và CSRF token hợp lệ.
2. Response redirect tới /login?logout theo cấu hình.
3. Session cũ bị invalid và request tiếp theo không có session xác thực sẽ phải đăng nhập lại.

Đây là bằng chứng cho cả URL, method, CSRF và hành vi kết thúc session. Nếu ứng dụng dùng LogoutSuccessHandler tùy chỉnh, hãy thay assertion redirect bằng status/header/body mà handler thực tế trả về.

### 5.2. Thiếu CSRF token phải bị từ chối

Ca **postLogoutWithoutCsrfIsRejectedAndKeepsLogin** gửi POST logout mà không có token. Với CSRF bật, request bị chặn với **403 Forbidden** trước khi LogoutFilter hoàn tất thao tác. Session vẫn hợp lệ và người dùng vẫn truy cập được profile.

Điều này rất quan trọng: một request logout bị từ chối không được vô tình xóa phiên đăng nhập. Nếu test thấy session đã invalid dù request thiếu token, cần kiểm tra cấu hình filter chain, CSRF matcher và các logout handler tùy chỉnh.

### 5.3. GET /logout không được làm thay đổi trạng thái

Ca **getLogoutDoesNotPerformLogout** không cố định status của GET vì kết quả phụ thuộc việc ứng dụng có trang xác nhận logout mặc định hay không. Test chỉ xác minh session vẫn hợp lệ và người dùng vẫn đọc được profile sau GET.

Nếu ứng dụng tự cấu hình matcher để GET cũng thực hiện logout, test này sẽ phát hiện hành vi đó. Với ứng dụng dùng session và trình duyệt, nên giữ thao tác logout ở POST có CSRF.

## 6. Kiểm thử URL tùy chỉnh và method sai

Giả sử cấu hình logout đã đổi sang **/signout**. Một test riêng cần xác minh URL cũ không thực hiện logout, còn URL mới với POST và CSRF thì có.

~~~java
@Test
void oldLogoutUrlDoesNotMatchCustomLogoutEndpoint() throws Exception {
    MockHttpSession session = loginAsAlice();

    mockMvc.perform(post("/logout")
                .session(session)
                .with(csrf()));

    assertThat(session.isInvalid()).isFalse();

    mockMvc.perform(get("/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
}

@Test
void configuredLogoutUrlWithPostAndCsrfLogsOut() throws Exception {
    MockHttpSession session = loginAsAlice();

    mockMvc.perform(post("/signout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

    assertThat(session.isInvalid()).isTrue();
}
~~~

Hai test trên thuộc **context test có cấu hình .logoutUrl("/signout")**; không chạy chúng với cấu hình mặc định /logout. Để kiểm thử đúng matcher, bảo đảm application context test thực sự nạp cấu hình custom và filter chain đang bật.

Nếu dùng matcher tường minh **AntPathRequestMatcher("/signout", "POST")**, test nên có thêm request GET /signout và xác minh session không bị invalid. Tương tự, nếu đổi sang path khác, cần kiểm tra cả path cũ và path mới để tránh cấu hình trùng hoặc matcher rộng ngoài ý muốn.

## 7. Logout handler và LogoutSuccessHandler

Khi LogoutFilter nhận request khớp matcher, nó gọi các **LogoutHandler** rồi mới gọi **LogoutSuccessHandler**.

| Thành phần | Vai trò |
| --- | --- |
| **SecurityContextLogoutHandler** | Xóa Authentication, dọn SecurityContext và invalidate session theo cấu hình |
| **CookieClearingLogoutHandler** | Gửi response cookie hết hạn để client xóa cookie được chỉ định |
| **LogoutSuccessHandler** | Tạo response sau logout, thường redirect hoặc trả status cho API |

Cấu hình **invalidateHttpSession(true)**, **clearAuthentication(true)** và **deleteCookies("JSESSIONID")** minh họa ba mục tiêu khác nhau: hủy session phía server, xóa danh tính trong ngữ cảnh bảo mật và yêu cầu client xóa cookie. Không nên coi một trong ba hành động là thay thế hoàn toàn hai hành động còn lại.

### API muốn trả 204 No Content sau logout

Với API có session, có thể cấu hình LogoutSuccessHandler để trả status thay vì redirect:

~~~java
import jakarta.servlet.http.HttpServletResponse;

.logout(logout -> logout
    .logoutUrl("/api/logout")
    .logoutSuccessHandler((request, response, authentication) ->
        response.setStatus(HttpServletResponse.SC_NO_CONTENT)
    )
)
~~~

Nếu CSRF đang bật, request POST /api/logout vẫn cần token. Test tương ứng:

~~~java
mockMvc.perform(post("/api/logout")
        .session(session)
        .with(csrf()))
    .andExpect(status().isNoContent());
~~~

Nếu API stateless dùng JWT bearer token, logout session phía server không tự thu hồi một JWT tự chứa đã phát hành. Muốn vô hiệu hóa token trước thời hạn cần thiết kế như token revocation/denylist, introspection hoặc token ngắn hạn và cơ chế refresh phù hợp. Việc xóa cookie trên client cũng không làm chữ ký hoặc thời hạn JWT thay đổi.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| POST /logout trả 403 | Thiếu CSRF token hoặc token không khớp | Dùng **.with(csrf())**, kiểm tra CSRF repository và matcher |
| GET /logout không đăng xuất | Đúng với matcher POST mặc định khi CSRF bật | Kiểm tra session vẫn truy cập được tài nguyên bảo vệ |
| POST /logout trả 404 hoặc không xử lý | Sai URL hoặc filter chain không chứa logout matcher mong muốn | Kiểm tra **logoutUrl**, **logoutRequestMatcher** và chain được chọn |
| Logout thành công nhưng test vẫn thấy response redirect khác | LogoutSuccessHandler hoặc success URL tùy chỉnh | Kiểm tra handler thực tế và assertion response |
| Session không invalid sau logout | Đã tắt **invalidateHttpSession**, custom handler không invalidate hoặc test dùng session khác | Lấy đúng session từ login request và kiểm tra logout handlers |
| Cookie vẫn còn sau logout | Chưa cấu hình deleteCookies hoặc tên/path/domain cookie không khớp | Kiểm tra Set-Cookie trong response và cấu hình cookie |
| Logout bằng session nhưng JWT vẫn dùng được | JWT stateless không bị session logout thu hồi | Dùng cơ chế revocation/introspection nếu yêu cầu |
| GET link logout làm người dùng thoát ngoài ý muốn | Matcher tùy chỉnh chấp nhận GET hoặc CSRF bị tắt | Giới hạn matcher ở POST và giữ CSRF cho browser session |

## 9. Bài tập thực hành

1. Chạy ba test mặc định ở mục 5. Xác nhận POST có CSRF logout thành công, POST thiếu token bị 403 và GET không kết thúc phiên.
2. Đổi URL thành /signout, chạy test path cũ/path mới và kiểm tra chỉ endpoint mới thực hiện logout.
3. Thay logoutSuccessUrl bằng LogoutSuccessHandler trả 204; sửa assertion để kiểm tra response API.
4. Bỏ deleteCookies("JSESSIONID"), so sánh header Set-Cookie trong response logout. Giải thích vì sao cookie client và session server là hai trạng thái khác nhau.
5. Tắt CSRF trong một profile test riêng, quan sát matcher mặc định thay đổi ra sao; không dùng kết quả đó để mặc định thiết kế logout cho trình duyệt.
6. Với API JWT stateless, xác minh logout session không thu hồi JWT và đề xuất cơ chế thu hồi token nếu sản phẩm cần.

Một bài kiểm thử logout đầy đủ phải chứng minh **đúng URL, đúng HTTP method, CSRF hợp lệ và session được kết thúc**. Các ca sai method, sai URL hoặc thiếu token giúp bảo đảm người dùng chỉ bị đăng xuất khi gửi đúng request mà ứng dụng đã chủ động cấu hình.
