# Remember-me sau đăng xuất hoặc sau khi phiên hết hạn

## 1. Remember-me duy trì đăng nhập khi session không còn

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, người dùng có thể chọn **Remember me** khi đăng nhập để tiếp tục được nhận diện sau khi HTTP session hết hạn hoặc trình duyệt mở lại. Đây là cơ chế xác thực bổ sung dựa trên cookie, không phải kéo dài vô hạn session hiện tại.

Khi session bị hết hạn, cookie remember-me còn hợp lệ có thể được Spring Security dùng để xác thực người dùng lại. Ngược lại, sau khi người dùng chủ động logout, ứng dụng cần xóa cookie và xử lý token remember-me theo loại dịch vụ đang dùng. Kiểm thử phải phân biệt hai tình huống: **session hết hạn nhưng người dùng muốn được nhớ**, và **người dùng đã logout nên không được tự đăng nhập lại**.

Bài này tập trung vào cách kiểm chứng hành vi đó bằng **MockMvc** và **spring-security-test** trong ứng dụng Servlet. Sau bài học, bạn có thể:

- Cấu hình remember-me với form login và thời hạn cookie.
- Kiểm tra cookie remember-me được phát hành khi người dùng chọn checkbox.
- Xác minh cookie hợp lệ có thể khôi phục Authentication sau khi session hết hạn.
- Xác minh người dùng không chọn remember-me phải đăng nhập lại khi session hết hạn.
- Kiểm tra logout xóa cookie và thu hồi persistent remember-me token.
- Phân biệt token-based remember-me với persistent-token remember-me, đặc biệt khi cookie đã bị sao chép.

## 2. Remember-me hoạt động như thế nào?

Trong form login, người dùng gửi thêm tham số **remember-me** khi chọn checkbox. Spring Security xác thực credentials như bình thường, sau đó RememberMeServices phát hành cookie. Ở request sau, nếu SecurityContext chưa có Authentication, **RememberMeAuthenticationFilter** có thể đọc cookie và khôi phục Authentication.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant F as Spring Security
    participant S as HttpSession
    participant R as Remember-me service
    B->>F: POST /login + credentials + remember-me
    F->>F: Xác thực username/password
    F->>S: Lưu SecurityContext
    F->>R: Phát hành remember-me cookie
    R-->>B: Set-Cookie: remember-me
    Note over B,S: Session hết hạn hoặc bị mất
    B->>F: GET /profile + remember-me cookie
    F->>R: Kiểm tra cookie
    R-->>F: Authentication được khôi phục
    F-->>B: 200 OK
~~~

Remember-me thường được kích hoạt khi request không có Authentication đã xác thực trong SecurityContext. Nếu session vẫn còn hợp lệ, Spring Security có thể nạp Authentication từ session mà không cần dùng cookie remember-me. Vì thế, để kiểm thử đúng tình huống sau khi session hết hạn, test cần bỏ session cũ khỏi request và chỉ gửi cookie remember-me.

**Remember-me không phải session.** Cookie remember-me có thời hạn và dữ liệu xác thực riêng. Session có thể hết hạn trong khi cookie remember-me vẫn còn hợp lệ; khi đó một request mới có thể tạo Authentication mới và có thể tạo session mới tùy cấu hình.

## 3. Hai loại RememberMeServices và khác biệt khi logout

Spring Security có hai cách triển khai thường gặp:

| Cơ chế | Dữ liệu cookie | Kiểm tra phía server | Khả năng thu hồi cookie đã bị sao chép |
| --- | --- | --- | --- |
| **TokenBasedRememberMeServices** | Username, thời hạn và chữ ký được tạo bằng key | Xác minh chữ ký, thời hạn và dữ liệu người dùng | Không có bản ghi token riêng để thu hồi; cookie bị sao chép có thể còn hợp lệ đến khi hết hạn hoặc chữ ký không còn hợp lệ |
| **PersistentTokenBasedRememberMeServices** | Series và token ngẫu nhiên | Tra cứu token trong PersistentTokenRepository; token được xoay khi sử dụng | Có thể thu hồi token phía server; logout khi có Authentication sẽ xóa các token persistent của người dùng theo repository |

Nếu không cấu hình PersistentTokenRepository, Spring Security thường sử dụng cơ chế token-based. Logout sẽ gửi cookie hết hạn về trình duyệt. Điều này giúp browser bình thường ngừng gửi cookie, nhưng **không thể thu hồi một bản cookie mà kẻ khác đã sao chép trước đó**.

Với persistent remember-me, token được lưu phía server. Khi logout có Authentication tương ứng, PersistentTokenBasedRememberMeServices có thể xóa token của người dùng khỏi repository. Khi cookie cũ được gửi lại, token không còn tồn tại nên không thể khôi phục Authentication.

Vì vậy, nếu yêu cầu bảo mật là **logout phải vô hiệu hóa cả bản cookie remember-me đã bị sao chép**, cần chọn cơ chế có trạng thái phía server và kiểm thử việc thu hồi token. Chỉ kiểm tra Set-Cookie hết hạn là chưa đủ để chứng minh token bị thu hồi.

## 4. Cấu hình ứng dụng mẫu với persistent remember-me

Ví dụ dùng **Spring Boot 3.x**, **Spring Security 6.x**, Spring MVC, form login và một PersistentTokenRepository. Trong test có thể dùng **InMemoryTokenRepositoryImpl**; ứng dụng thực tế thường dùng **JdbcTokenRepositoryImpl** hoặc repository bền vững phù hợp.

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
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
class SecurityConfig {

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

    @Bean
    PersistentTokenRepository persistentTokenRepository() {
        // Chỉ dùng in-memory cho test hoặc ví dụ đơn giản.
        // Production nên dùng repository bền vững như JDBC.
        return new InMemoryTokenRepositoryImpl();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users,
            PersistentTokenRepository tokenRepository) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/profile").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key("test-only-remember-me-key")
                .rememberMeParameter("remember-me")
                .rememberMeCookieName("remember-me")
                .tokenValiditySeconds(14 * 24 * 60 * 60)
                .userDetailsService(users)
                .tokenRepository(tokenRepository)
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .deleteCookies("JSESSIONID", "remember-me")
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            );

        return http.build();
    }
}
~~~

**Key trong ví dụ chỉ dành cho test.** Ứng dụng thực tế phải lấy key từ cấu hình bí mật phù hợp và không commit key vào repository. Với JDBC repository, cần tạo bảng persistent token theo schema Spring Security hoặc migration do dự án quản lý; không bật tự tạo bảng khi chạy production nếu schema đã được quản lý riêng.

Endpoint bảo vệ:

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

Form login mặc định sử dụng tham số **remember-me**. Khi người dùng gửi giá trị checkbox, RememberMeServices tạo cookie có tên **remember-me** theo cấu hình. Logout tiêu chuẩn cũng gọi RememberMeServices như một LogoutHandler để hủy cookie và xử lý token tương ứng.

## 5. Kiểm thử remember-me sau khi session hết hạn

Test quan trọng nhất là đăng nhập với checkbox remember-me, lấy cookie, vô hiệu hóa session và gửi request mới **chỉ với cookie remember-me**.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeSessionTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    PersistentTokenRepository tokenRepository;

    record LoginState(MockHttpSession session, Cookie rememberMeCookie) {}

    @BeforeEach
    void clearAliceTokens() {
        tokenRepository.removeUserTokens("alice");
    }

    private LoginState login(boolean rememberMe) throws Exception {
        var request = post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "secret");

        if (rememberMe) {
            request.param("remember-me", "true");
        }

        MvcResult result = mockMvc.perform(request)
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        Cookie cookie = result.getResponse().getCookie("remember-me");
        if (rememberMe) {
            assertThat(cookie).isNotNull();
            assertThat(cookie.getMaxAge()).isPositive();
        } else {
            assertThat(cookie).isNull();
        }

        return new LoginState(session, cookie);
    }

    @Test
    void rememberMeCookieRestoresAuthenticationAfterSessionExpires()
            throws Exception {
        LoginState state = login(true);

        // Mô phỏng session hết hạn; giữ cookie remember-me ở client.
        state.session().invalidate();

        mockMvc.perform(get("/profile").cookie(state.rememberMeCookie()))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void withoutRememberMeUserMustLoginAgainAfterSessionExpires()
            throws Exception {
        LoginState state = login(false);

        state.session().invalidate();

        mockMvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

Test đầu kiểm chứng cookie remember-me có thể khôi phục Authentication sau khi session không còn. Test thứ hai cho thấy nếu không chọn remember-me thì sau khi session hết hạn, request mới không có cookie xác thực phải quay về trang login.

**Không truyền session đã invalid vào request mới.** Hãy bỏ session cũ khỏi request và chỉ gửi cookie cần kiểm tra. MockMvc không tự giữ cookie giữa các lần gọi perform; **.cookie(...)** mô phỏng browser gửi cookie ở request mới.

### 5.1. Phân biệt session hết hạn với logout

Session hết hạn là trạng thái tự nhiên của vòng đời session. Nếu cookie remember-me vẫn hợp lệ, người dùng có thể được xác thực lại. Logout là hành động chủ động kết thúc trạng thái đăng nhập; với persistent remember-me, token phía server cũng cần được thu hồi.

Không dùng **session.invalidate()** để thay thế test logout. Nó chỉ mô phỏng session hết hạn hoặc bị hủy, không gọi LogoutHandler và không gửi chỉ thị xóa cookie remember-me.

## 6. Kiểm thử logout xóa cookie và thu hồi persistent token

Với cấu hình persistent repository ở mục 4, ta kiểm tra cả cookie hết hạn và việc cookie cũ không thể khôi phục Authentication sau logout.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

@Test
void logoutExpiresRememberMeCookieAndRevokesPersistentToken()
        throws Exception {
    LoginState state = login(true);

    // Xác minh cookie còn dùng được trước logout.
    mockMvc.perform(get("/profile").session(state.session()))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

    MvcResult logout = mockMvc.perform(post("/logout")
                .session(state.session())
                .cookie(state.rememberMeCookie())
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

    assertThat(state.session().isInvalid()).isTrue();

    Cookie expiredCookie = logout.getResponse().getCookie("remember-me");
    assertThat(expiredCookie).isNotNull();
    assertThat(expiredCookie.getMaxAge()).isZero();

    // Mô phỏng client đã giữ bản cookie cũ và gửi lại sau logout.
    // PersistentTokenRepository đã thu hồi token nên cookie cũ bị từ chối.
    mockMvc.perform(get("/profile").cookie(state.rememberMeCookie()))
            .andExpect(status().is3xxRedirection());
}
~~~

Đoạn test này đặt trong cùng class có helper **login(true)** và cấu hình PersistentTokenRepository ở mục 4. Khi logout, session đang có Authentication nên RememberMeServices có thể xác định người dùng và xóa token persistent của họ khỏi repository. Request sau logout gửi lại cookie cũ sẽ không thể khôi phục Authentication.

Nếu chỉ dùng TokenBasedRememberMeServices, assertion replay cookie cũ bị từ chối **không đúng**: cookie đã sao chép có thể còn hợp lệ cho đến khi hết hạn hoặc key/password thay đổi. Với cơ chế token-based, test nên kiểm tra response logout gửi cookie hết hạn và request không có cookie bị từ chối; không khẳng định server đã thu hồi một bản cookie đã bị sao chép.

## 7. Kiểm thử logout thiếu CSRF không làm mất remember-me

Với form login và CSRF bật, POST /logout không có token hợp lệ phải bị từ chối trước khi LogoutHandler thực hiện xóa session hoặc remember-me token.

~~~java
@Test
void missingCsrfDoesNotRevokeRememberMeOrInvalidateSession()
        throws Exception {
    LoginState state = login(true);

    mockMvc.perform(post("/logout")
                .session(state.session())
                .cookie(state.rememberMeCookie()))
            .andExpect(status().isForbidden());

    assertThat(state.session().isInvalid()).isFalse();

    mockMvc.perform(get("/profile").session(state.session()))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

    // Nếu session hết hạn, cookie remember-me vẫn có thể xác thực lại.
    state.session().invalidate();

    mockMvc.perform(get("/profile").cookie(state.rememberMeCookie()))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
}
~~~

Test này phân biệt request logout bị từ chối với logout thành công. Nếu thiếu CSRF mà session/token vẫn bị xóa, cần kiểm tra filter chain, CSRF matcher và các handler tùy chỉnh.

## 8. Token rotation và phát hiện cookie bị dùng lại

Với **PersistentTokenBasedRememberMeServices**, token được xoay sau khi cookie được sử dụng thành công. Cookie mới chứa token mới; token cũ không còn là token hiện hành cho series đó. Cơ chế này giúp phát hiện tình huống token cũ bị dùng lại, có thể xảy ra khi cookie bị sao chép.

Vì vậy, khi request sau session expiry được xác thực bằng persistent remember-me, response có thể gửi một cookie remember-me mới. Client cần dùng cookie mới cho request tiếp theo.

| Tình huống | Hành vi kỳ vọng với persistent remember-me |
| --- | --- |
| Session hết hạn, cookie hiện hành còn hợp lệ | Authentication được khôi phục |
| Cookie hợp lệ được sử dụng | Token được xoay và cookie mới được gửi |
| Cookie cũ đã được sử dụng trước đó bị replay | Token không khớp; có thể kích hoạt xử lý phát hiện reuse |
| Logout khi Authentication còn trong session | Token persistent của user được xóa |
| Replay cookie sau logout | Không khôi phục được Authentication |

Không nên dùng một cookie persistent cũ nhiều lần trong các test mà không cập nhật cookie mới từ response. Với repository in-memory dùng chung trong test suite, nên dọn token của user ở **@BeforeEach** hoặc tạo repository riêng cho mỗi test context để tránh trạng thái test này ảnh hưởng test khác.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Session hết hạn nhưng request vẫn redirect login | Không gửi remember-me cookie, cookie hết hạn hoặc remember-me chưa được cấu hình | Kiểm tra checkbox, cookie response, key, UserDetailsService và token repository |
| Chọn remember-me nhưng không có cookie | Tham số checkbox sai hoặc RememberMeServices không được bật | Kiểm tra rememberMeParameter và cấu hình rememberMe |
| Cookie có nhưng không khôi phục Authentication | Chữ ký/token không hợp lệ, user bị xóa hoặc token persistent không còn trong repository | Kiểm tra key, user, thời hạn và repository |
| Logout xóa cookie nhưng cookie sao chép vẫn dùng được | Đang dùng TokenBasedRememberMeServices không có trạng thái thu hồi server-side | Chọn persistent token repository nếu cần thu hồi bản cookie đã sao chép |
| Logout xong session vẫn hợp lệ | Request không khớp logout URL/method, thiếu CSRF hoặc dùng sai session trong test | Kiểm tra POST /logout, CSRF và MockHttpSession |
| Cookie mới không được browser lưu | Path, Domain, Secure, SameSite hoặc Max-Age không phù hợp | Kiểm tra toàn bộ Set-Cookie qua HTTP client/browser |
| Test lúc chạy riêng qua, chạy suite lỗi | PersistentTokenRepository dùng chung dữ liệu giữa test | Dọn token hoặc cô lập repository mỗi test |
| Test replay cookie cũ sai kết quả | Đang kỳ vọng token-based bị thu hồi như persistent token | Xác định implementation RememberMeServices đang dùng |

## 10. Bài tập thực hành

1. Đăng nhập với và không có tham số remember-me; so sánh cookie được phát hành.
2. Vô hiệu hóa session nhưng giữ cookie remember-me; xác minh request mới có cookie được xác thực lại.
3. Lặp lại với tài khoản không chọn remember-me; xác minh request sau session expiry bị redirect login.
4. Logout bằng POST và CSRF token; kiểm tra cookie remember-me hết hạn, session invalid và request replay cookie bị từ chối với persistent repository.
5. Bỏ CSRF token khỏi request logout; xác minh session và remember-me token vẫn có thể dùng.
6. Thử TokenBasedRememberMeServices trong test riêng. Phân biệt việc browser nhận cookie hết hạn với khả năng thu hồi một bản cookie đã bị sao chép.
7. Với JDBC token repository, kiểm tra bản ghi persistent token được tạo, cập nhật khi rotation và xóa khi logout.

Remember-me cần được kiểm thử theo cả hai vòng đời: **session hết hạn nhưng cookie còn hợp lệ thì người dùng được nhận diện lại**, còn **logout phải xóa cookie ở client và thu hồi token phía server nếu ứng dụng dùng persistent remember-me**. Phân biệt rõ hai hành vi này giúp test không nhầm một session timeout bình thường với việc người dùng đã chủ động đăng xuất.
