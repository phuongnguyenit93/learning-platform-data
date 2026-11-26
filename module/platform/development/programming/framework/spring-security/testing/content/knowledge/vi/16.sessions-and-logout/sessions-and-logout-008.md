# Kiểm tra xóa Authentication, vô hiệu phiên và xử lý cookie

## 1. Logout phải dọn ba lớp trạng thái

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, kiểm thử đăng xuất cần xác minh ba việc liên quan nhưng độc lập:

1. **Xóa Authentication khỏi SecurityContext** đang được sử dụng trong request.
2. **Vô hiệu hóa HTTP session** phía server để session cũ không còn được dùng để khôi phục trạng thái đăng nhập.
3. **Xóa cookie session ở client** bằng response Set-Cookie có thời hạn hết hiệu lực.

Nếu chỉ xóa cookie mà session phía server vẫn còn hiệu lực, một client còn giữ session ID có thể tiếp tục gửi ID đó. Nếu chỉ invalidate session mà response không xóa cookie, trình duyệt vẫn có thể gửi cookie cũ ở request sau, dù server không còn session tương ứng. Nếu chỉ xóa Authentication trong SecurityContextHolder nhưng không dọn session/repository, trạng thái cũ có thể được khôi phục ở request khác tùy cấu hình.

Bài này hướng dẫn cấu hình và kiểm chứng ba hành vi trên bằng **Spring Security**, **spring-security-test** và **MockMvc** trong ứng dụng Servlet. Sau bài học, bạn có thể:

- Phân biệt xóa Authentication, xóa SecurityContext, invalidate session và xóa cookie.
- Cấu hình LogoutHandler và LogoutSuccessHandler.
- Kiểm tra Authentication đã được xóa, session đã invalid và cookie đã được yêu cầu xóa.
- Kiểm tra request logout thiếu CSRF bị từ chối mà không làm mất phiên đăng nhập.
- Nhận biết giới hạn của MockMvc khi kiểm thử cookie và hành vi trình duyệt thực tế.

## 2. Ba lớp trạng thái có vai trò khác nhau

### 2.1. Authentication và SecurityContext

**Authentication** biểu diễn danh tính và quyền của người dùng đã được xác thực. **SecurityContext** chứa Authentication đó. Trong một request Servlet, **SecurityContextHolder** cung cấp SecurityContext cho phần xử lý hiện tại.

Khi logout, Spring Security cần xóa Authentication khỏi SecurityContext và dọn SecurityContextHolder để thread xử lý không giữ lại danh tính đã đăng nhập. Việc dọn holder là quan trọng vì thread có thể được tái sử dụng cho request khác.

### 2.2. HTTP session và SecurityContextRepository

Trong ứng dụng stateful, **HttpSessionSecurityContextRepository** có thể lưu SecurityContext vào HttpSession. Request tiếp theo dùng cùng session sẽ tải lại SecurityContext và Authentication.

Vì vậy, chỉ gọi thao tác xóa context trong một request mà không xử lý nơi lưu trữ có thể chưa đủ để kết thúc phiên đăng nhập. Logout mặc định của Spring Security sử dụng handler quản lý SecurityContext và session để dọn trạng thái theo cấu hình.

### 2.3. Cookie session ở trình duyệt

Cookie như **JSESSIONID** thường chỉ mang mã định danh session. Cookie không chứa trực tiếp SecurityContext hoặc mật khẩu người dùng. Trình duyệt gửi cookie để server tra cứu session tương ứng.

Khi logout, response có thể gửi một header **Set-Cookie** với cùng tên cookie, giá trị rỗng và thời hạn hết hiệu lực. Đây là yêu cầu để client xóa cookie. Nó không thay thế việc invalidate session phía server.

| Hành động | Nơi tác động | Bằng chứng kiểm thử phù hợp |
| --- | --- | --- |
| Xóa Authentication | SecurityContext / SecurityContextHolder | Authentication trong context đã được xóa; holder không còn Authentication |
| Invalidate session | HttpSession phía server | MockHttpSession báo invalid; request sau không khôi phục được đăng nhập |
| Xóa cookie | Response gửi về client | Set-Cookie cho cookie cùng tên có Max-Age=0 hoặc Expires trong quá khứ |
| Xác minh logout hoàn chỉnh | Kết hợp các lớp trên | Session invalid, Authentication đã xóa, cookie có chỉ thị xóa và request sau bị yêu cầu đăng nhập |

## 3. LogoutHandler xử lý việc dọn trạng thái

Khi request khớp LogoutFilter, Spring Security gọi các **LogoutHandler** rồi mới gọi **LogoutSuccessHandler**.

Một số thành phần quan trọng:

- **SecurityContextLogoutHandler**: xóa Authentication khỏi SecurityContext, dọn SecurityContextHolder và invalidate HttpSession theo cấu hình.
- **CookieClearingLogoutHandler**: gửi cookie hết hiệu lực về client.
- **CsrfLogoutHandler**: xóa CSRF token gắn với phiên hoặc repository tương ứng.
- **LogoutSuccessHandler**: tạo response sau khi các LogoutHandler đã chạy, ví dụ redirect hoặc trả HTTP 204.

Luồng xử lý tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Browser / Client
    participant L as LogoutFilter
    participant H as LogoutHandler
    participant S as HttpSession
    participant R as Response
    C->>L: POST /logout + session + CSRF
    L->>H: Gọi các logout handlers
    H->>H: Xóa Authentication khỏi SecurityContext
    H->>S: Invalidate session
    H->>R: Thêm Set-Cookie hết hạn
    H-->>L: Hoàn tất dọn trạng thái
    L->>R: LogoutSuccessHandler tạo response
    R-->>C: 204 hoặc redirect + Set-Cookie
~~~

Cấu hình logout tiêu chuẩn thường đã bật xóa Authentication và invalidate session. Ta có thể khai báo rõ hai hành vi này để chính sách dễ đọc và kiểm thử. Cookie cần được xóa riêng nếu ứng dụng muốn gửi chỉ thị xóa cookie về client.

## 4. Cấu hình ứng dụng mẫu

Ví dụ sử dụng **Spring Boot 3.x**, **Spring Security 6.x**, Spring MVC và form login. Ứng dụng có tài khoản alice và endpoint profile yêu cầu Authentication.

~~~java
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
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
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request, response, authentication) -> {
                    boolean contextCleared =
                        SecurityContextHolder.getContext().getAuthentication() == null;
                    response.setHeader(
                        "X-Security-Context-Cleared",
                        Boolean.toString(contextCleared)
                    );
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT);
                })
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

LogoutSuccessHandler trong ví dụ trả **204 No Content** để phù hợp với API hoặc test muốn kiểm tra response rõ ràng. Header **X-Security-Context-Cleared** chỉ là tín hiệu chẩn đoán dành cho ví dụ kiểm thử: nó ghi nhận SecurityContextHolder không còn Authentication tại thời điểm success handler chạy. Không cần expose header nội bộ này trong ứng dụng production.

Endpoint mẫu:

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

Trong cấu hình:

- **invalidateHttpSession(true)** yêu cầu vô hiệu hóa session hiện tại.
- **clearAuthentication(true)** yêu cầu xóa Authentication khỏi SecurityContext.
- **deleteCookies("JSESSIONID")** thêm chỉ thị xóa cookie session vào response.
- LogoutSuccessHandler chạy sau các LogoutHandler, nên có thể kiểm tra SecurityContextHolder đã được dọn trước khi trả response.

Nếu ứng dụng dùng tên cookie session tùy chỉnh, hãy truyền đúng tên thay vì mặc định JSESSIONID.

## 5. Kiểm thử đăng nhập và logout bằng MockMvc

Test cần đăng nhập trước để tạo session có Authentication, sau đó gửi request logout bằng **cùng session**. Sau logout, ta kiểm tra cả Authentication, session và cookie.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;

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
class LogoutStateCleanupTest {

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

        SecurityContext context = (SecurityContext) saved;
        assertThat(context.getAuthentication()).isNotNull();
        assertThat(context.getAuthentication().getName()).isEqualTo("alice");

        return session;
    }

    @Test
    void logoutClearsAuthenticationInvalidatesSessionAndExpiresCookie()
            throws Exception {
        MockHttpSession session = loginAsAlice();

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        SecurityContext context = (SecurityContext) saved;
        assertThat(context.getAuthentication().getName()).isEqualTo("alice");

        MvcResult logout = mockMvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().isNoContent())
                .andExpect(header().string(
                    "X-Security-Context-Cleared", "true"))
                .andReturn();

        // SecurityContext đã được làm rỗng trước khi success handler chạy.
        assertThat(context.getAuthentication()).isNull();

        // Session phía server không còn hợp lệ.
        assertThat(session.isInvalid()).isTrue();

        // Response yêu cầu client xóa cookie session.
        Cookie[] cookies = logout.getResponse().getCookies();
        assertThat(cookies).anySatisfy(cookie -> {
            assertThat(cookie.getName()).isEqualTo("JSESSIONID");
            assertThat(cookie.getMaxAge()).isZero();
        });

        // Request mới không có session đăng nhập phải xác thực lại.
        mockMvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void missingCsrfDoesNotClearAuthenticationOrInvalidateSession()
            throws Exception {
        MockHttpSession session = loginAsAlice();

        mockMvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();

        mockMvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

### 5.1. Vì sao giữ tham chiếu SecurityContext trước logout?

Test lấy SecurityContext đã được lưu trong session trước khi logout. Sau khi LogoutHandler chạy, Authentication bên trong context được xóa. Việc kiểm tra tham chiếu này giúp xác nhận trạng thái Authentication đã được dọn, trong khi header do LogoutSuccessHandler tạo xác nhận holder không còn Authentication ở cuối chuỗi logout handler.

Trong ứng dụng tùy biến, repository có thể khác hoặc cách lưu context không dùng thuộc tính session mặc định. Khi đó, hãy kiểm tra hành vi theo hợp đồng của repository và endpoint thay vì phụ thuộc vào key nội bộ của HttpSessionSecurityContextRepository.

### 5.2. Vì sao kiểm tra session invalid riêng?

Xóa Authentication khỏi SecurityContext và invalidate session là hai hành động khác nhau. Nếu chỉ xóa Authentication nhưng session còn tồn tại, session có thể tiếp tục mang các dữ liệu ứng dụng khác hoặc được dùng lại theo chính sách. Nếu chỉ invalidate session mà không dọn context của thread hiện tại, code đang xử lý có thể còn giữ tham chiếu Authentication trong request.

Do đó, test xác minh riêng **context.getAuthentication() == null** và **session.isInvalid() == true**.

### 5.3. Vì sao CSRF thất bại không được xóa trạng thái?

Với CSRF protection mặc định, POST /logout không có token hợp lệ sẽ bị chặn trước khi LogoutFilter thực hiện logout. Test xác minh session vẫn hợp lệ và người dùng vẫn truy cập được profile. Điều này bảo đảm request không hợp lệ không vô tình kết thúc phiên.

## 6. Xử lý cookie session đúng cách

### 6.1. deleteCookies gửi chỉ thị xóa cookie

Cấu hình:

~~~java
.logout(logout -> logout
    .logoutUrl("/logout")
    .deleteCookies("JSESSIONID")
)
~~~

yêu cầu Spring Security gửi cookie cùng tên với thời hạn hết hiệu lực. Trong MockMvc, có thể kiểm tra cookie ở response:

~~~java
Cookie[] cookies = result.getResponse().getCookies();

assertThat(cookies).anySatisfy(cookie -> {
    assertThat(cookie.getName()).isEqualTo("JSESSIONID");
    assertThat(cookie.getMaxAge()).isZero();
});
~~~

Max-Age bằng 0 là chỉ thị cookie hết hiệu lực ngay. Một số response cũng có Expires trong quá khứ. Khi kiểm tra response thực, hãy xem toàn bộ Set-Cookie vì các thuộc tính Path, Domain, Secure, HttpOnly và SameSite ảnh hưởng việc browser áp dụng cookie.

### 6.2. Path và Domain phải khớp cookie ban đầu

Cookie được định danh bởi tên cùng phạm vi Path/Domain. Nếu ứng dụng tạo cookie JSESSIONID với Path riêng như /myapp hoặc Domain tùy chỉnh, chỉ gửi cookie xóa có tên đúng nhưng Path/Domain không khớp có thể không xóa được cookie mà browser đang giữ.

Trong trường hợp cookie tùy chỉnh, có thể tạo Cookie có thuộc tính tương ứng và dùng **CookieClearingLogoutHandler**:

~~~java
import jakarta.servlet.http.Cookie;
import org.springframework.security.web.authentication.logout.CookieClearingLogoutHandler;

Cookie sessionCookie = new Cookie("JSESSIONID", "");
sessionCookie.setPath("/myapp");
// Nếu cookie ban đầu có Domain, đặt đúng Domain đó.
// sessionCookie.setDomain("example.com");

CookieClearingLogoutHandler clearSessionCookie =
        new CookieClearingLogoutHandler(sessionCookie);

// Trong LogoutConfigurer:
.logout(logout -> logout
    .addLogoutHandler(clearSessionCookie)
)
~~~

Cookie clearing handler đặt thời hạn cookie về 0 khi logout. Hãy cấu hình Path/Domain khớp với cookie được phát hành. Tránh tạo nhiều handler xóa cùng cookie với các thuộc tính khác nhau vì browser có thể nhận các chỉ thị không nhất quán.

### 6.3. Xóa cookie không thay thế invalidate session

Giả sử response đã gửi JSESSIONID hết hạn nhưng session phía server vẫn hợp lệ. Một client đã sao chép cookie trước đó vẫn có thể thử gửi lại ID cũ. Vì vậy, ứng dụng phải invalidate session hoặc có cơ chế server-side tương đương.

Ngược lại, nếu server invalidate session nhưng không gửi chỉ thị xóa cookie, browser có thể tiếp tục gửi cookie cũ. Server không tìm thấy session hợp lệ, nhưng cookie vẫn còn ở client cho đến khi hết hạn hoặc bị thay thế. Đó là lý do cần kiểm thử cả hai phía.

## 7. Khi nào cần thêm LogoutHandler?

Ứng dụng có thể lưu nhiều loại trạng thái ngoài SecurityContext và session. Khi logout, cần xem xét handler bổ sung phù hợp:

| Trạng thái cần dọn | Cơ chế có thể dùng |
| --- | --- |
| SecurityContext và Authentication | SecurityContextLogoutHandler |
| Session HTTP hiện tại | SecurityContextLogoutHandler với invalidateHttpSession |
| Cookie session | CookieClearingLogoutHandler hoặc deleteCookies |
| CSRF token | CsrfLogoutHandler trong chuỗi logout tiêu chuẩn |
| Remember-me cookie/token | RememberMeServices.logout hoặc handler tương ứng |
| Trạng thái tùy chỉnh phía ứng dụng | LogoutHandler riêng |
| Token truy cập stateless | Cơ chế thu hồi token/introspection/denylist theo kiến trúc |

Không phải mọi hệ thống đều cần tất cả handler. Hãy liệt kê nơi ứng dụng lưu trạng thái xác thực, refresh token, remember-me và cookie rồi xác định hành động logout cần thực hiện.

### JWT không tự bị thu hồi khi xóa session

Với JWT tự chứa được xác minh độc lập ở mỗi request, logout một HTTP session không tự làm token hết hiệu lực. Nếu sản phẩm cần vô hiệu hóa token trước exp, phải có cơ chế như token revocation, denylist, introspection hoặc thời hạn token ngắn kết hợp refresh token có thể thu hồi.

Xóa cookie chứa JWT khỏi browser chỉ loại bỏ bản sao cookie ở client đó. Nó không vô hiệu hóa bản token mà người dùng đã sao chép ở nơi khác.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Session invalid nhưng Authentication trong code vẫn còn | Thread hoặc code tùy chỉnh giữ tham chiếu SecurityContext | Kiểm tra SecurityContextHolder và các tham chiếu context sau logout |
| Authentication đã xóa nhưng request sau vẫn đăng nhập | Repository/session chưa được dọn hoặc test vô tình dùng danh tính mock | Kiểm tra session, SecurityContextRepository và bỏ @WithMockUser |
| Cookie không biến mất trên browser | Path/Domain của cookie xóa không khớp cookie gốc | Kiểm tra Set-Cookie thực tế và thuộc tính cookie |
| Response có cookie hết hạn nhưng session vẫn truy cập được | Chỉ xóa cookie, chưa invalidate session phía server | Kiểm tra session invalid và thử gửi lại session ID cũ trong môi trường test phù hợp |
| POST logout trả 403 | Thiếu CSRF token hoặc token sai | Dùng .with(csrf()) và kiểm tra CSRF repository |
| Logout success handler thấy Authentication còn tồn tại | Handler thứ tự sai hoặc SecurityContextLogoutHandler không được gọi | Kiểm tra LogoutHandler được đăng ký và thứ tự xử lý |
| JWT vẫn dùng được sau logout | JWT stateless không phụ thuộc HTTP session | Thiết kế cơ chế thu hồi token nếu yêu cầu |

## 9. Bài tập thực hành

1. Chạy test logout thành công và xác minh cả ba assertion: Authentication đã xóa, session invalid và cookie JSESSIONID có Max-Age bằng 0.
2. Bỏ cấu hình deleteCookies rồi so sánh response cookie. Session vẫn invalid nhưng browser không nhận được chỉ thị xóa cookie từ handler này.
3. Đặt invalidateHttpSession(false) trong profile test riêng. Quan sát khác biệt giữa Authentication bị xóa và session vẫn còn hiệu lực; không dùng cấu hình này làm mặc định cho logout thông thường.
4. Gửi POST /logout thiếu CSRF token. Xác minh session và Authentication vẫn được giữ.
5. Thay Path cookie thành /myapp và cấu hình CookieClearingLogoutHandler với Path tương ứng. Kiểm tra Set-Cookie có đúng phạm vi.
6. Nếu ứng dụng dùng remember-me hoặc refresh token, bổ sung handler/revocation phù hợp và viết test cho trạng thái đó.
7. Với JWT stateless, kiểm tra vì sao xóa JSESSIONID không làm token đã phát hành hết hiệu lực.

Logout hoàn chỉnh cần có bằng chứng ở cả ba lớp: **Authentication không còn trong SecurityContext, session phía server đã bị vô hiệu hóa và response yêu cầu client xóa cookie**. Khi kiểm thử tách riêng từng hành động rồi kiểm tra request sau logout, ta có thể phát hiện trường hợp một lớp đã được dọn nhưng lớp khác vẫn giữ trạng thái đăng nhập.
