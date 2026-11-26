# Đăng nhập thành công khác với đăng nhập thất bại nhưng vẫn có phiên cũ

Trong ứng dụng Spring Security dùng đăng nhập bằng biểu mẫu HTTP, một yêu cầu đăng nhập **thất bại** không nhất thiết khiến mọi yêu cầu tiếp theo trở thành **chưa xác thực**. Nếu trình duyệt đang giữ phiên HTTP đã đăng nhập trước đó, lần nhập sai mật khẩu có thể bị từ chối trong khi quyền truy cập từ phiên cũ vẫn còn hiệu lực. Kiểm thử cần phân biệt kết quả của **lần thử đăng nhập mới** với trạng thái xác thực **được lưu từ trước trong phiên**.

Bài này tập trung vào Spring Security trên **Servlet stack**, kiểm thử bằng **MockMvc** và **spring-security-test**. Đây là một trường hợp điển hình trong chương **Đăng nhập qua HTTP** của module **SPRING_SECURITY_TESTING**: kiểm chứng thực tế việc xác thực, bảo vệ endpoint và hành vi phiên bằng những yêu cầu HTTP đi qua chuỗi bộ lọc bảo mật.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt đăng nhập thành công, đăng nhập sai trên phiên mới và đăng nhập sai trên phiên đã xác thực.
- Giải thích vai trò khác nhau của phản hồi HTTP, SecurityContext của yêu cầu hiện tại và SecurityContext lưu trong HttpSession.
- Dùng MockMvc để gửi POST /login với CSRF hợp lệ, giữ và tái sử dụng MockHttpSession, rồi truy cập tài nguyên được bảo vệ.
- Viết assertion đúng với **chính sách phiên** của ứng dụng: giữ phiên cũ hay chủ động hủy phiên khi đăng nhập thất bại.
- Nhận ra các phép kiểm tra có thể cho kết quả đánh lừa, như chỉ kiểm tra mã 302 hoặc dùng @WithMockUser để thay thế luồng đăng nhập thật.

## 2. Ba tình huống cần kiểm thử riêng

Giả sử Alice có tài khoản hợp lệ, endpoint /private yêu cầu đăng nhập, và ứng dụng dùng form login mặc định của Spring Security.

| Tình huống | Yêu cầu gửi đi | Kết quả lần thử đăng nhập | Truy cập /private sau đó |
| --- | --- | --- | --- |
| A. Đăng nhập đúng | POST /login với mật khẩu đúng | Thành công; có Authentication của Alice | Cho phép với phiên đã xác thực |
| B. Đăng nhập sai, phiên ban đầu chưa xác thực | POST /login với mật khẩu sai | Thất bại; không tạo phiên đăng nhập hợp lệ | Bị chuyển tới trang đăng nhập theo cấu hình form login |
| C. Đăng nhập sai **trên phiên Alice đã xác thực** | POST /login với mật khẩu sai và mang lại cookie phiên cũ | Lần thử mới thất bại | **Phụ thuộc chính sách phiên**; cấu hình minh họa bên dưới vẫn cho phép |

Trường hợp C là trọng tâm. Một yêu cầu POST bị chuyển hướng tới /login?error không chứng minh rằng người dùng đã mất quyền của phiên trước. Ngược lại, GET /private thành công sau POST sai **không chứng minh** lần nhập mật khẩu sai đã được chấp nhận: quyền truy cập có thể đến từ lần xác thực đúng trước đó.

### Trạng thái xác thực được lưu ở đâu?

Với cơ chế lưu SecurityContext trong HttpSession thường dùng ở Servlet:

1. Trước khi xử lý yêu cầu, Spring Security có thể nạp SecurityContext đã lưu trong phiên vào ngữ cảnh của yêu cầu.
2. Khi POST /login xác thực **thành công**, bộ lọc đăng nhập thiết lập Authentication mới; thành phần lưu SecurityContext duy trì trạng thái xác thực để những yêu cầu sau sử dụng. Chiến lược chống session fixation có thể đổi session ID.
3. Khi POST /login xác thực **thất bại**, bộ lọc xóa SecurityContext đang gắn với lần thử hiện tại và gọi failure handler. Việc này **không đồng nghĩa** với xóa SecurityContext đã lưu trong HttpSession hay vô hiệu hóa toàn bộ phiên cũ.
4. Ở GET /private tiếp theo, nếu HttpSession vẫn chứa SecurityContext cũ và ứng dụng chưa hủy nó, Spring Security có thể nạp lại Authentication hợp lệ từ phiên đó.

~~~text
Phiên S đã đăng nhập Alice
    |
    +-- GET /private ----------------------> 200 OK (Alice)
    |
    +-- POST /login (mật khẩu sai) --------> 302 /login?error
    |                                        lần thử mới bị từ chối
    |
    +-- GET /private, vẫn dùng phiên S ----> 200 OK (Alice)
                                             nếu phiên cũ được giữ
~~~

Lưu ý: đây là hành vi có thể quan sát với **cấu hình mẫu** của bài. Một ứng dụng có failure handler riêng, chính sách vô hiệu hóa phiên, hoặc cơ chế lưu SecurityContext khác có thể cho kết quả khác; kiểm thử phải thể hiện quy tắc mong muốn của chính ứng dụng.

## 3. Chuẩn bị ứng dụng Servlet tối thiểu

Với dự án Spring Boot Servlet, cần các dependency tương ứng:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Giả sử ứng dụng đã có lớp khởi động Spring Boot và quét được hai lớp sau. Cấu hình dùng trang đăng nhập và URL xử lý POST /login mặc định; /private yêu cầu xác thực.

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/private").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}correct-horse")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class PrivateController {

    @GetMapping("/private")
    String privatePage() {
        return "secret";
    }
}
~~~

Các import chính cho cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
~~~

Mã hóa mật khẩu dạng {noop} chỉ phục vụ ví dụ kiểm thử có dữ liệu cố định. Trong ứng dụng thật, hãy sử dụng PasswordEncoder phù hợp, chẳng hạn BCrypt.

## 4. Bộ kiểm thử MockMvc theo ba tình huống

Đặt lớp kiểm thử trong package được cấu hình bởi ứng dụng Spring Boot. Dùng @SpringBootTest và @AutoConfigureMockMvc để chạy SecurityFilterChain cùng các thành phần MVC thực tế. Mỗi phép kiểm tra dùng yêu cầu HTTP đi qua bộ lọc bảo mật; không gắn sẵn danh tính bằng @WithMockUser.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpLoginSessionTests {

    @Autowired
    MockMvc mvc;

    @Test
    void validCredentialsCreateAnAuthenticatedSession() throws Exception {
        MockHttpSession session = loginSuccessfully();

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("secret"));
    }

    @Test
    void wrongPasswordOnAnonymousSessionDoesNotGrantAccess()
            throws Exception {
        MockHttpSession anonymousSession = new MockHttpSession();

        mvc.perform(post("/login")
                .session(anonymousSession)
                .with(csrf())
                .param("username", "alice")
                .param("password", "incorrect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        mvc.perform(get("/private").session(anonymousSession))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void wrongPasswordDoesNotAutomaticallyDestroyOldLogin()
            throws Exception {
        MockHttpSession oldSession = loginSuccessfully();

        // Chứng minh phiên cũ đã được xác thực trước lần thử sai.
        mvc.perform(get("/private").session(oldSession))
            .andExpect(status().isOk());

        // Lần thử đăng nhập mới thất bại.
        mvc.perform(post("/login")
                .session(oldSession)
                .with(csrf())
                .param("username", "alice")
                .param("password", "incorrect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

        // Cấu hình mặc định minh họa vẫn nhận phiên đăng nhập cũ.
        mvc.perform(get("/private").session(oldSession))
            .andExpect(status().isOk())
            .andExpect(content().string("secret"));
    }

    private MockHttpSession loginSuccessfully() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "correct-horse"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }
}
~~~

**Vì sao phải tái sử dụng chính oldSession?** Với MockMvc, mỗi lần gọi perform là một yêu cầu độc lập. Nếu bỏ .session(oldSession), lần GET cuối có thể không mang trạng thái đã xác thực; phép thử lúc đó không còn kiểm tra tình huống phiên cũ. Hãy lấy phiên **sau khi đăng nhập thành công**, vì Spring Security có thể thay đổi session ID khi xác thực.

**Vì sao POST /login cần .with(csrf())?** Spring Security thường bật CSRF protection cho yêu cầu thay đổi trạng thái. Nếu thiếu token, POST có thể bị chặn với 403 trước khi UsernamePasswordAuthenticationFilter kiểm tra mật khẩu. Khi đó phép thử đang đo CSRF, không đo đăng nhập sai. Có thể dùng helper formLogin() của spring-security-test cho luồng đăng nhập; ví dụ chủ động dùng post() và csrf() để thấy rõ các tham số và phiên.

**Vì sao không chỉ khẳng định unauthenticated() sau lần thử sai có phiên cũ?** Trạng thái của một yêu cầu thất bại khác với trạng thái xác thực mà yêu cầu kế tiếp nạp lại từ phiên. Mục tiêu của ca thứ ba là kiểm chứng quyền truy cập **sau** sự kiện đăng nhập sai, nên phép đo rõ nhất là GET /private với cùng MockHttpSession.

## 5. Nếu yêu cầu nghiệp vụ là hủy phiên cũ khi nhập sai?

Có hai chính sách hợp lệ tùy sản phẩm:

| Chính sách | Hành vi mong muốn | Assertion quyết định |
| --- | --- | --- |
| Giữ phiên đã đăng nhập | Thử đăng nhập lại sai không tự đăng xuất Alice | Sau POST sai, GET /private với phiên cũ vẫn trả 200 |
| Hủy phiên khi đăng nhập sai | Thử đăng nhập lại sai làm mất quyền từ phiên trước | Phiên cũ bị invalidate; GET tiếp theo không còn quyền truy cập |

Nếu yêu cầu là chính sách thứ hai, ứng dụng phải **thực thi** nó trong cấu hình bảo mật. Chẳng hạn, với Servlet form login có thể khai báo failure handler chủ động vô hiệu hóa HttpSession:

~~~java
.formLogin(form -> form.failureHandler((request, response, error) -> {
    HttpSession session = request.getSession(false);
    if (session != null) {
        session.invalidate();
    }
    response.sendRedirect(request.getContextPath() + "/login?error");
}))
~~~

Trong đoạn này, HttpSession là kiểu jakarta.servlet.http.HttpSession. Đoạn failure handler thay thế cách xử lý thất bại mặc định; tùy sản phẩm có thể cần bổ sung hiển thị thông báo lỗi, ghi log hoặc chính sách điều hướng phù hợp. Không nên mặc định rằng Spring Security sẽ tự invalidate session trên mọi lần sai mật khẩu.

Với chính sách hủy phiên, một kiểm thử đặc trưng là:

~~~java
MockHttpSession oldSession = loginSuccessfully();

mvc.perform(post("/login")
        .session(oldSession)
        .with(csrf())
        .param("username", "alice")
        .param("password", "incorrect"))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/login?error"));

assertThat(oldSession.isInvalid()).isTrue();

// Yêu cầu mới không còn một phiên xác thực hợp lệ.
mvc.perform(get("/private"))
    .andExpect(status().is3xxRedirection());
~~~

Không tái sử dụng một đối tượng MockHttpSession đã bị invalidate để giả lập phiên hợp lệ. Trong hệ thống thật, cookie mang session ID cũ cũng không thể khôi phục phiên đã bị vô hiệu hóa ở phía server.

## 6. Những kết luận sai thường gặp

| Quan sát khi chạy test | Điều thực sự cần kiểm tra |
| --- | --- |
| POST /login trả 302 | Redirect tới đâu? Thành công hay /login?error? Có Authentication mới không? |
| POST /login trả 403 | Token CSRF hợp lệ chưa? Yêu cầu có đi đến bộ lọc đăng nhập không? |
| Sau nhập sai, GET /private vẫn 200 | Yêu cầu có mang session đã xác thực trước đó không? Chính sách có yêu cầu hủy nó không? |
| Đăng nhập đúng nhưng GET /admin trả 403 | Tài khoản đã xác thực có đủ authority/role để truy cập endpoint không? |
| Test dùng @WithMockUser vẫn truy cập được /private | Annotation đã tạo danh tính giả lập cho test; chưa hề kiểm chứng username, password và login filter |
| Mỗi perform() kiểm thử riêng đều đúng | Chưa chắc đã kiểm chứng dòng đời của **cùng một phiên** qua nhiều yêu cầu |

Cần tách các khái niệm HTTP status, authentication và authorization: 302 có thể là redirect đăng nhập hoặc redirect báo lỗi; 401 thường xuất hiện khi dùng cơ chế entry point khác như HTTP Basic/Bearer; 403 có thể đến từ CSRF hoặc thiếu quyền. Một mã phản hồi đơn lẻ không đủ để suy ra tình trạng của HttpSession.

## 7. Liên hệ Reactive và JWT/OAuth2

Đối với **Reactive**, sử dụng WebTestClient và cấu hình WebFlux Security tương ứng. Hãy giữ cookie/phiên WebSession giữa các yêu cầu khi kiểm thử luồng đăng nhập thật. Kỹ thuật mutateWith(mockUser(...)) hữu ích để giả lập một người dùng đã xác thực, nhưng cũng không thay thế kiểm thử POST login và hành vi phiên.

Đối với API **stateless** dùng JWT Bearer, một access token cũ có thể tiếp tục hợp lệ sau khi người dùng gửi sai thông tin đăng nhập lần khác, trừ khi có cơ chế thu hồi token hoặc trạng thái phiên riêng. Khi đó cần kiểm tra token được gửi trong Authorization header và chính sách thu hồi của hệ thống; không suy diễn kết quả từ HttpSession.

## 8. Tự luyện tập

1. Giữ nguyên cấu hình mẫu, thêm assert rằng /private chuyển hướng khi truy cập từ một MockHttpSession mới chưa xác thực. So sánh với cùng endpoint dùng session lấy từ login thành công.
2. Đổi mật khẩu trong POST thứ hai thành giá trị sai nhưng giữ nguyên oldSession. Giải thích vì sao redirect /login?error và GET /private = 200 có thể cùng đúng.
3. Thêm failure handler invalidate phiên. Thay assertion ca thứ ba để phản ánh chính sách mới và kiểm tra oldSession.isInvalid().
4. Thử bỏ .with(csrf()) khỏi POST. Quan sát response và giải thích tại sao kết quả 403 không chứng minh mật khẩu sai đã được xử lý.
5. Thêm endpoint chỉ cho ROLE_ADMIN. Kiểm chứng Alice có thể đã đăng nhập hợp lệ nhưng vẫn bị 403 do thiếu quyền; phân biệt kết luận này với lỗi xác thực.

**Điểm cần ghi nhớ:** Khi kiểm thử HTTP login, hãy hỏi đồng thời hai câu: **lần thử thông tin đăng nhập này thành công hay thất bại?** và **phiên nào sẽ được sử dụng ở yêu cầu tiếp theo?** Chỉ bằng cách kiểm thử cả hai, ta mới nhận ra đúng hành vi mà Spring Security và chính sách ứng dụng đang áp dụng.
