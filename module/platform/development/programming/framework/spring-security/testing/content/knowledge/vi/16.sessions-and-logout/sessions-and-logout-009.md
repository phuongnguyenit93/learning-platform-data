# Gọi lại tài nguyên sau đăng xuất để xác minh bị từ chối

## 1. Logout xong phải kiểm tra request tiếp theo

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, kiểm thử logout chỉ có ý nghĩa khi chứng minh người dùng không còn truy cập được tài nguyên cần xác thực sau khi đăng xuất. Một response thành công từ **POST /logout** chưa đủ: ứng dụng có thể trả redirect nhưng vẫn giữ SecurityContext trong session, hoặc request tiếp theo vô tình dùng lại danh tính giả lập trong test.

Bài này tập trung vào hành trình **đăng nhập → truy cập tài nguyên → logout → gọi lại tài nguyên** bằng **MockMvc** và **spring-security-test** trong ứng dụng Servlet. Ta sẽ xác minh request sau logout không còn Authentication hợp lệ và không thể đọc tài nguyên bảo vệ.

Sau bài học, bạn có thể:

- Viết test đăng nhập bằng credentials thật trong application context, không dựa vào Authentication dựng sẵn.
- Dùng cùng MockHttpSession trước logout để truy cập tài nguyên, sau logout xác minh session đã invalid.
- Gọi lại endpoint bằng request mới hoặc session mới và xác minh bị từ chối.
- Phân biệt redirect đến form login, **401 Unauthorized** và **403 Forbidden**.
- Tránh dùng lại session đã invalid hoặc @WithMockUser theo cách làm sai lệch kết quả.
- Hiểu giới hạn của MockMvc khi mô phỏng cookie cũ và session của Servlet container.

## 2. Luồng kiểm thử sau logout

Với ứng dụng form login dùng HTTP session, luồng cần kiểm tra:

1. Gửi **POST /login** với username/password và CSRF token.
2. Lấy MockHttpSession do request đăng nhập tạo ra.
3. Gọi **GET /profile** với session đó và xác nhận endpoint trả dữ liệu của người dùng.
4. Gửi **POST /logout** với cùng session và CSRF token.
5. Xác nhận session đã bị vô hiệu hóa.
6. Gửi một request mới không mang session đăng nhập cũ; endpoint phải yêu cầu xác thực lại.

~~~mermaid
sequenceDiagram
    autonumber
    participant T as MockMvc test
    participant F as Spring Security
    participant S as HttpSession
    participant P as GET /profile
    T->>F: POST /login + credentials + CSRF
    F->>S: Lưu SecurityContext của alice
    F-->>T: Login thành công, trả session
    T->>P: GET /profile + session
    P-->>T: 200 OK, alice
    T->>F: POST /logout + cùng session + CSRF
    F->>S: Xóa context và invalidate session
    F-->>T: Logout success
    T->>P: GET /profile, không có session đăng nhập
    F-->>T: Redirect đến /login
~~~

**Điểm cần chứng minh:** cùng một phiên cho phép truy cập trước logout; sau logout, một request độc lập không còn kế thừa Authentication. Với form login mặc định, request chưa xác thực thường được chuyển hướng đến trang đăng nhập. Nếu API dùng HTTP Basic hoặc bearer token, response thường là 401 thay vì redirect.

## 3. Ứng dụng mẫu

Ví dụ dùng **Spring Boot 3.x**, **Spring Security 6.x**, Spring MVC, JUnit 5 và MockMvc. Cấu hình form login lưu trạng thái trong session:

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
            .logout(Customizer.withDefaults())
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

Controller chỉ trả tên người dùng hiện tại:

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

Trong ví dụ, **/profile** yêu cầu đã xác thực. Form login mặc định tiếp nhận POST /login, còn logout mặc định dùng POST /logout khi CSRF đang bật. Cấu hình **IF_REQUIRED** cho phép Spring Security tạo session khi cần lưu SecurityContext.

## 4. Bộ test đầy đủ với MockMvc

Bộ test sau xác minh quyền truy cập trước và sau logout. Helper **loginAsAlice()** thực hiện login qua filter chain và lấy session thực tế từ request, nhờ đó test không vô tình dùng một Authentication giả lập.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
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
class AccessAfterLogoutTest {

    @Autowired
    MockMvc mockMvc;

    private MockHttpSession loginAsAlice() throws Exception {
        MvcResult login = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertThat(saved).isInstanceOf(SecurityContext.class);

        SecurityContext context = (SecurityContext) saved;
        assertThat(context.getAuthentication()).isNotNull();
        assertThat(context.getAuthentication().getName()).isEqualTo("alice");

        return session;
    }

    private void logout(MockHttpSession session) throws Exception {
        mockMvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertThat(session.isInvalid()).isTrue();
    }

    @Test
    void protectedResourceIsAvailableBeforeLogoutAndDeniedAfterwards()
            throws Exception {
        MockHttpSession authenticatedSession = loginAsAlice();

        // Trước logout: cùng phiên đã đăng nhập đọc được tài nguyên.
        mockMvc.perform(get("/profile").session(authenticatedSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        logout(authenticatedSession);

        // Sau logout: request mới không mang session cũ.
        mockMvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location", endsWith("/login")));
    }

    @Test
    void aFreshSessionDoesNotInheritAuthenticationAfterLogout()
            throws Exception {
        MockHttpSession authenticatedSession = loginAsAlice();

        mockMvc.perform(get("/profile").session(authenticatedSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        logout(authenticatedSession);

        MockHttpSession freshSession = new MockHttpSession();
        mockMvc.perform(get("/profile").session(freshSession))
                .andExpect(status().is3xxRedirection());

        // Request cache có thể thêm thuộc tính riêng, nhưng không có
        // SecurityContext xác thực của alice trong session mới.
        assertThat(freshSession.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY))
                .isNull();
    }

    @Test
    void userCanLoginAgainAndReceiveANewAuthenticatedSession()
            throws Exception {
        MockHttpSession firstSession = loginAsAlice();
        logout(firstSession);

        MockHttpSession secondSession = loginAsAlice();

        assertThat(secondSession).isNotSameAs(firstSession);
        mockMvc.perform(get("/profile").session(secondSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void unauthenticatedRequestCannotReadProtectedResponse()
            throws Exception {
        mockMvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location", endsWith("/login")));
    }
}
~~~

### 4.1. Vì sao không truyền session cũ sau logout?

Sau khi logout, session đã bị invalid. Không nên gọi:

~~~java
mockMvc.perform(get("/profile").session(authenticatedSession));
~~~

với chính đối tượng MockHttpSession đã invalid. Tùy cách MockHttpSession được truy cập, thao tác này có thể phát sinh IllegalStateException và không mô phỏng đúng request từ browser.

Trình duyệt thật có thể vẫn còn cookie JSESSIONID cũ cho đến khi nhận được chỉ thị xóa cookie hoặc cookie hết hạn. Khi server đã invalidate session, cookie cũ không thể khôi phục SecurityContext đã bị xóa. Trong MockMvc, cách kiểm tra luồng ứng dụng sau logout là gửi request mới không gắn session cũ, hoặc dùng một MockHttpSession mới chưa xác thực.

### 4.2. Vì sao cần kiểm tra trước và sau logout?

Nếu chỉ kiểm tra request sau logout bị redirect, test chưa chứng minh rằng người dùng từng đăng nhập thành công. Có thể cấu hình login sai, credentials sai hoặc filter chain chưa được nối.

Vì vậy, test trước hết gọi /profile bằng session sau login và khẳng định **200 OK** cùng body **alice**. Sau logout, cùng tài nguyên phải chuyển sang trạng thái yêu cầu xác thực. Cặp assertion này chứng minh thay đổi quyền truy cập thực sự xảy ra do logout.

### 4.3. Request cache có thể tạo session mới

Khi người dùng chưa xác thực gọi tài nguyên được bảo vệ, form login entry point có thể lưu request ban đầu để chuyển hướng trở lại sau login. Request cache có thể tạo session mới để lưu saved request. Vì thế, không nên khẳng định rằng request sau logout luôn không tạo session.

Điều cần khẳng định là **session mới không chứa Authentication đã đăng nhập của alice** và endpoint bảo vệ vẫn yêu cầu đăng nhập. Test ở trên kiểm tra SecurityContext key, không yêu cầu toàn bộ session phải rỗng.

## 5. Phân biệt 302, 401 và 403

Kết quả sau logout phụ thuộc cơ chế xác thực và quy tắc phân quyền:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **302 / 3xx redirect** | Chưa xác thực và được chuyển đến trang login | Form login mặc định khi GET /profile |
| **401 Unauthorized** | Request chưa có thông tin xác thực hợp lệ | REST API dùng HTTP Basic hoặc bearer token |
| **403 Forbidden** | Đã xác thực nhưng không đủ quyền, hoặc bị chặn bởi chính sách khác như CSRF | Alice có ROLE_USER gọi endpoint yêu cầu ROLE_ADMIN |

**Không dùng 403 để khẳng định logout thành công.** Nếu request sau logout trả 403, hãy kiểm tra xem request có bị CSRF chặn hay không, hoặc có một Authentication khác còn tồn tại nhưng thiếu quyền. Với form login mặc định, request chưa đăng nhập thường được redirect tới login.

Nếu ứng dụng có custom AuthenticationEntryPoint, AccessDeniedHandler hoặc response JSON, hãy viết assertion theo hợp đồng của ứng dụng thay vì sao chép status của ví dụ.

## 6. Các lỗi làm test sau logout cho kết quả sai

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request sau logout vẫn trả 200 | Request vô tình dùng Authentication mock, session khác vẫn đăng nhập, hoặc logout không khớp matcher | Dùng login thật, kiểm tra URL/method logout và session |
| Request sau logout trả 302 nhưng test vẫn không đáng tin | Chưa chứng minh login trước đó thành công | Khẳng định GET tài nguyên trả 200 trước logout |
| Dùng lại MockHttpSession sau invalidate gây lỗi | Session object đã invalid | Gửi request mới không gắn session cũ |
| Request sau logout tạo session mới | Request cache, CSRF hoặc code ứng dụng tạo session | Kiểm tra SecurityContext vắng mặt thay vì yêu cầu không có session |
| Test luôn trả 200 dù không có login | @WithMockUser, .with(user(...)) hoặc filter chain bị tắt | Bỏ danh tính mock, bảo đảm Spring Security filters hoạt động |
| POST logout trả 403 | Thiếu CSRF token | Thêm .with(csrf()) vào request logout |
| Request trả 401 thay vì redirect | API dùng HTTP Basic/bearer token hoặc entry point tùy chỉnh | Khẳng định status theo cấu hình API |
| Logout session nhưng JWT vẫn dùng được | JWT stateless không phụ thuộc session | Dùng cơ chế thu hồi token nếu yêu cầu |

### Tránh @WithMockUser trong bài test này

@WithMockUser hữu ích để kiểm tra authorization khi đã có principal giả lập. Tuy nhiên, nó có thể khiến request /profile trả 200 ngay cả khi test chưa thực hiện login và chưa lưu SecurityContext vào session.

Đối với mục tiêu xác minh **logout rồi gọi lại tài nguyên**, hãy dùng POST /login qua filter chain, lấy session từ request login và dùng session đó cho request trước logout. Như vậy, test chứng minh được luồng xác thực thực tế trong phạm vi application context.

## 7. Kiểm thử API stateless sau logout

Đối với API dùng JWT, khái niệm logout session không giống form login. Nếu client gửi bearer token hợp lệ ở mỗi request, việc invalidate HttpSession không làm token đó hết hiệu lực.

Một test resource server có thể dùng **jwt()** để giả lập Authentication:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void apiRequiresBearerAuthenticationOnEveryRequest() throws Exception {
    mockMvc.perform(get("/api/orders")
                .with(jwt().jwt(token -> token.subject("alice"))))
            .andExpect(status().isOk());

    // Request mới không mang JWT phải bị từ chối.
    mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
}
~~~

Đây là phép kiểm thử hai request độc lập, chứng minh Authentication không tự tiếp nối giữa các request trong cấu hình stateless. jwt() tạo JwtAuthenticationToken giả lập để kiểm thử filter/authorization phía sau; nó không xác minh chữ ký, issuer, audience hoặc thời hạn của JWT thực.

Nếu sản phẩm yêu cầu logout thu hồi JWT trước thời điểm hết hạn, cần kiểm thử cơ chế revocation, denylist hoặc introspection tương ứng. Xóa session cookie không thu hồi bearer token tự chứa.

## 8. Giới hạn của MockMvc và kiểm thử tích hợp

MockMvc chạy request trong ứng dụng Servlet mà không mở HTTP server thực. Nó phù hợp để kiểm tra filter chain, session, SecurityContext và response logic. Tuy nhiên, nó không tự kiểm chứng:

- Browser có lưu cookie JSESSIONID mới hay xóa cookie cũ hay không.
- Cookie Path, Domain, Secure, HttpOnly và SameSite có được browser áp dụng đúng không.
- Servlet container thực xử lý session ID cũ sau invalidate như thế nào.
- Reverse proxy hoặc session store phân tán có đồng bộ trạng thái session hay không.

Nếu cần kiểm chứng cookie cũ thực sự không truy cập được, hãy bổ sung test tích hợp chạy ứng dụng qua embedded Servlet container hoặc môi trường triển khai thử nghiệm. Client cần giữ cookie từ login, gửi cookie đó sau logout và xác minh tài nguyên bị từ chối. Đây là bước kiểm tra ở cấp HTTP/browser, khác với việc truyền MockHttpSession trong MockMvc.

## 9. Bài tập thực hành

1. Chạy protectedResourceIsAvailableBeforeLogoutAndDeniedAfterwards. Xác minh response trước logout là 200, sau logout là redirect login.
2. Bỏ .session(authenticatedSession) ở request trước logout. Quan sát vì sao test không còn chứng minh trạng thái đăng nhập.
3. Sau logout, thử dùng một MockHttpSession mới. Xác minh SecurityContext của alice không được kế thừa.
4. Dùng @WithMockUser cho test riêng, so sánh với test đăng nhập thực. Giải thích vì sao test mock không chứng minh session đã bị logout.
5. Thay form login bằng HTTP Basic và xác minh request sau logout không credentials trả 401.
6. Với API JWT, mô phỏng request có jwt() rồi gọi request độc lập không có token; kiểm tra API từ chối request thứ hai.
7. Bổ sung test tích hợp dùng HTTP client giữ cookie để xác minh cookie/session cũ sau logout không truy cập được tài nguyên.

Một bài kiểm thử logout có giá trị phải chứng minh được **người dùng đã truy cập được tài nguyên trước logout và bị từ chối khi gọi lại sau logout**. Khi kết hợp việc kiểm tra session invalid, request mới và response theo đúng cơ chế xác thực, test giúp phát hiện trường hợp logout chỉ trả thành công trên giao diện nhưng trạng thái đăng nhập vẫn còn hiệu lực.
