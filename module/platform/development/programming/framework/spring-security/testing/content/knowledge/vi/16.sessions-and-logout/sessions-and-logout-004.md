# Tách hai phiên hoặc hai người dùng trong cùng ca kiểm thử

## 1. Vì sao cần kiểm tra tính độc lập của phiên?

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, ứng dụng Servlet thường phục vụ nhiều người dùng cùng lúc. Mỗi người có một phiên đăng nhập riêng; trạng thái xác thực và quyền của người này không được rò sang request của người khác.

Một lỗi quản lý session có thể khiến ứng dụng dùng nhầm danh tính, trả dữ liệu của người dùng A cho người dùng B, hoặc làm thao tác đăng xuất của A ảnh hưởng đến phiên của B. Vì vậy, kiểm thử một người dùng đăng nhập rồi truy cập tài nguyên bằng cùng session mới chỉ chứng minh khả năng tiếp nối phiên. Ta còn cần chứng minh **hai session khác nhau giữ hai danh tính độc lập**, ngay cả khi được kiểm thử xen kẽ trong cùng một phương thức test.

Bài này sử dụng **MockMvc**, **MockHttpSession** và **spring-security-test** để kiểm chứng:

- Hai lần đăng nhập tạo ra hai session riêng.
- Request mang session A luôn nhận danh tính A; request mang session B nhận danh tính B.
- Một session mới hoặc không có session không tự thừa hưởng Authentication.
- Quyền truy cập được đánh giá riêng cho từng người dùng.
- Logout session A không hủy phiên đang đăng nhập của B.

Đây là bài kiểm thử cho ứng dụng **Spring MVC (Servlet)**. Với ứng dụng Reactive, cần dùng WebTestClient và WebSession tương ứng.

## 2. Mô hình hai người dùng, hai phiên

Giả sử hệ thống có hai tài khoản:

| Người dùng | Mật khẩu dành cho test | Role | Tài nguyên được phép |
| --- | --- | --- | --- |
| alice | secret | USER | /api/me |
| bob | bob-secret | ADMIN | /api/me và /api/admin |

Sau khi đăng nhập, server lưu SecurityContext chứa Authentication của mỗi người trong session tương ứng. Trong test, ta giữ hai đối tượng **MockHttpSession**:

~~~text
MockMvc test
  |
  +-- POST /login (alice) --> sessionAlice
  |                             |
  |                             +-- GET /api/me --> "alice"
  |
  +-- POST /login (bob) ----> sessionBob
                                |
                                +-- GET /api/me --> "bob"
                                +-- GET /api/admin --> 200 OK
~~~

Khi gửi request, ta chọn session rõ ràng:

~~~java
mockMvc.perform(get("/api/me").session(sessionAlice));
mockMvc.perform(get("/api/me").session(sessionBob));
~~~

Mỗi request dùng đúng session mà test chỉ định. **MockMvc không tự đóng vai trò một trình duyệt duy trì cookie chung giữa các lần gọi perform**. Nếu không truyền session, request mới không tự biết người dùng nào đã đăng nhập ở request trước.

## 3. Cấu hình ứng dụng mẫu

Ví dụ dùng Spring Boot 3.x, Spring Security 6.x, JUnit 5, MockMvc và AssertJ. Các dependency chính:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Nếu dùng Maven, thêm artifact **org.springframework.security:spring-security-test** với scope **test**. Nên dùng phiên bản được Spring Boot quản lý trong dự án.

### 3.1. Khai báo hai người dùng với quyền khác nhau

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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-secret"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Quy tắc **hasRole("ADMIN")** kiểm tra authority **ROLE_ADMIN**. Alice chỉ có ROLE_USER, còn Bob có ROLE_ADMIN. Cả hai đều được xác thực để gọi /api/me.

**IF_REQUIRED** cho phép tạo HTTP session khi cần. Cấu hình form login mặc định sử dụng cơ chế lưu SecurityContext tương thích với session, vì vậy request tiếp theo có thể khôi phục Authentication nếu client gửi lại đúng session.

Tài khoản và mật khẩu trong ví dụ chỉ dành cho test. Không dùng thông tin này làm tài khoản thực tế.

### 3.2. Tài nguyên trả về danh tính hiện tại

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    @GetMapping("/api/me")
    String currentUser(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
~~~

Endpoint /api/me trả tên principal đã được Spring Security xác thực. Endpoint /api/admin chỉ đến được khi người dùng có role ADMIN. Các assertion về response body giúp phát hiện trường hợp request vô tình dùng nhầm session của người còn lại.

## 4. Viết helper đăng nhập và lấy session riêng

Một helper dùng chung giúp mỗi người đăng nhập bằng một request riêng và trả về session được tạo sau khi xác thực:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MvcResult;

private MockHttpSession loginAs(String username, String password)
        throws Exception {
    MvcResult result = mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andReturn();

    // Lấy session sau khi login hoàn tất.
    MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

    assertThat(session).isNotNull();

    Object savedContext = session.getAttribute(
            HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
    assertThat(savedContext).isInstanceOf(SecurityContext.class);

    SecurityContext context = (SecurityContext) savedContext;
    assertThat(context.getAuthentication()).isNotNull();
    assertThat(context.getAuthentication().getName()).isEqualTo(username);

    return session;
}
~~~

Helper kiểm tra cả SecurityContext đã được lưu trong session. Điều này phù hợp với cấu hình mẫu sử dụng **HttpSessionSecurityContextRepository**. Nếu ứng dụng dùng repository tùy biến, có thể thay assertion về key nội bộ bằng kiểm tra hành vi request tiếp theo.

Lấy session sau login rất quan trọng vì Spring Security có thể thay đổi session ID để bảo vệ khỏi session fixation. Không giả định session ID trước và sau xác thực luôn giống nhau.

## 5. Hai session trong cùng một test

Test quan trọng nhất là đăng nhập cả Alice và Bob trong cùng phương thức, sau đó gửi request xen kẽ với từng session:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MultipleServletSessionsTest {

    @Autowired
    MockMvc mockMvc;

    // Đặt helper loginAs(...) ở đây.

    @Test
    void twoUsersKeepIndependentIdentityInOneTest() throws Exception {
        MockHttpSession aliceSession = loginAs("alice", "secret");
        MockHttpSession bobSession = loginAs("bob", "bob-secret");

        assertThat(aliceSession).isNotSameAs(bobSession);
        assertThat(aliceSession.getId()).isNotEqualTo(bobSession.getId());

        mockMvc.perform(get("/api/me").session(aliceSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        mockMvc.perform(get("/api/me").session(bobSession))
                .andExpect(status().isOk())
                .andExpect(content().string("bob"));

        // Gọi lại A sau B để phát hiện rò rỉ SecurityContext giữa request.
        mockMvc.perform(get("/api/me").session(aliceSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        mockMvc.perform(get("/api/me").session(bobSession))
                .andExpect(status().isOk())
                .andExpect(content().string("bob"));
    }
}
~~~

Các assertion có ý nghĩa riêng:

1. **Hai object session khác nhau:** test không vô tình truyền cùng một đối tượng MockHttpSession cho cả hai người.
2. **Session ID khác nhau:** hai phiên được tạo độc lập trong cấu hình Servlet mẫu.
3. **Alice → Bob → Alice → Bob:** việc xen kẽ request giúp phát hiện trường hợp Authentication bị giữ nhầm trong trạng thái dùng chung thay vì được khôi phục từ session tương ứng.

Không nên chỉ kiểm tra hai lần đăng nhập đều redirect. Cần đọc tài nguyên được bảo vệ bằng từng session và xác minh đúng principal ở response.

## 6. Kiểm tra phân quyền độc lập theo từng session

Sau khi đã có hai session, ta kiểm tra cùng một endpoint quản trị với từng danh tính:

~~~java
@Test
void authorizationIsEvaluatedForEachSession() throws Exception {
    MockHttpSession aliceSession = loginAs("alice", "secret");
    MockHttpSession bobSession = loginAs("bob", "bob-secret");

    mockMvc.perform(get("/api/admin").session(aliceSession))
            .andExpect(status().isForbidden());

    mockMvc.perform(get("/api/admin").session(bobSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:bob"));
}
~~~

Kết quả **403** của Alice cho thấy phiên đã được xác thực nhưng không đủ quyền. Bob có ROLE_ADMIN nên được phép. Nếu cả hai request đều trả 200, cần kiểm tra quy tắc authorization hoặc xem test có vô tình bỏ qua Spring Security filter hay không.

Nếu cả hai cùng trả 403, hãy kiểm tra role được cấp trong UserDetailsService, quy tắc hasRole và authority thực tế. **hasRole("ADMIN")** tương ứng với **ROLE_ADMIN**, không phải authority tên ADMIN.

## 7. Logout một phiên không làm mất phiên còn lại

Một thuộc tính quan trọng của việc tách phiên là thao tác logout của Alice chỉ tác động đến session Alice. Bob vẫn phải truy cập được tài nguyên bằng session riêng của mình.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// Trong cùng test class, sử dụng logout endpoint mặc định:
@Test
void loggingOutAliceDoesNotInvalidateBobSession() throws Exception {
    MockHttpSession aliceSession = loginAs("alice", "secret");
    MockHttpSession bobSession = loginAs("bob", "bob-secret");

    mockMvc.perform(post("/logout")
                .session(aliceSession)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

    assertThat(aliceSession.isInvalid()).isTrue();
    assertThat(bobSession.isInvalid()).isFalse();

    mockMvc.perform(get("/api/me").session(bobSession))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"));
}
~~~

Logout request phải truyền đúng **aliceSession** và có CSRF token. Sau logout, kiểm tra Bob vẫn sử dụng được phiên của mình.

Không tái sử dụng Alice session sau khi đã bị invalidate. Để kiểm tra người dùng truy cập lại sau logout, gửi request mới không có session cũ hoặc với session mới chưa xác thực.

## 8. Bài kiểm thử hoàn chỉnh trong một lớp

Các phương thức dưới đây có thể đặt chung trong một lớp test, cùng helper loginAs ở mục 4. Mỗi phương thức tạo session riêng, tránh chia sẻ trạng thái giữa các test:

~~~java
@Test
void newSessionDoesNotInheritEitherIdentity() throws Exception {
    MockHttpSession aliceSession = loginAs("alice", "secret");
    MockHttpSession bobSession = loginAs("bob", "bob-secret");
    MockHttpSession freshSession = new MockHttpSession();

    assertThat(aliceSession.getId()).isNotEqualTo(bobSession.getId());

    mockMvc.perform(get("/api/me").session(freshSession))
            .andExpect(status().is3xxRedirection());

    mockMvc.perform(get("/api/me").session(aliceSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

    mockMvc.perform(get("/api/me").session(bobSession))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"));
}
~~~

Test này phân biệt ba trường hợp: session Alice, session Bob và một session mới không có Authentication. Session mới có thể tồn tại nhưng vẫn chưa được xác thực; **có HttpSession không đồng nghĩa với đã đăng nhập**.

### Ma trận kết quả mong đợi

| Request | Session gửi kèm | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| GET /api/me | Alice session | **200**, alice | Khôi phục danh tính Alice |
| GET /api/me | Bob session | **200**, bob | Khôi phục danh tính Bob |
| GET /api/me | Session mới | **302** tới login | Không có Authentication |
| GET /api/admin | Alice session | **403** | Đã xác thực nhưng thiếu quyền |
| GET /api/admin | Bob session | **200**, admin:bob | Đủ ROLE_ADMIN |
| POST /logout | Alice session | **3xx**, session invalid | Chỉ kết thúc phiên Alice |
| GET /api/me sau logout Bob session | Bob session | **200**, bob | Phiên Bob còn hoạt động |

Mã redirect 302 áp dụng cho form login mặc định. Nếu ứng dụng dùng HTTP Basic, REST entry point hoặc xử lý lỗi tùy chỉnh, request chưa xác thực có thể nhận 401 hoặc response khác. Luôn viết assertion theo chính sách thật của SecurityFilterChain.

## 9. Các lỗi thường gặp khi tách phiên

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Alice và Bob đều trả về cùng một tên | Dùng nhầm session object, truyền nhầm biến hoặc test đang mock một Authentication dùng chung | Kiểm tra session ID và truyền đúng .session(...) |
| Request không session vẫn trả 200 | Có @WithMockUser, .with(user(...)) hoặc filter bị tắt | Bỏ danh tính mock ở test luồng login và bật Spring Security filter |
| Logout Alice làm Bob cũng mất phiên | Hai biến cùng tham chiếu một session hoặc ứng dụng có logic logout tùy chỉnh tác động rộng | Assert hai object/ID khác nhau và kiểm tra handler logout |
| Cả Alice và Bob đều vào được admin | Cấu hình role quá rộng hoặc endpoint không được bảo vệ | Kiểm tra hasRole/hasAuthority và filter chain |
| Test chạy riêng qua nhưng chạy song song bị nhiễu | Chia sẻ MockHttpSession hoặc trạng thái mutable ở field/static | Tạo session trong từng test method, không dùng session static |
| Không thấy SecurityContext trong session | Dùng repository tùy chỉnh hoặc cấu hình stateless | Kiểm tra hợp đồng repository và hành vi request tiếp theo |

### Đừng dùng SecurityContextHolder như nơi giữ danh tính của cả bài test

SecurityContextHolder cung cấp ngữ cảnh cho request đang xử lý. Spring Security thiết lập và dọn ngữ cảnh theo vòng đời filter. Nếu test tự gán một SecurityContext vào holder rồi dùng chung cho nhiều request, nó có thể bỏ qua chính cơ chế cần kiểm thử và gây rò trạng thái giữa các lần thực thi.

Để xác minh session isolation, hãy để mỗi request đi qua SecurityFilterChain và cung cấp đúng session. Nếu cần mock một danh tính cho từng request riêng lẻ, **.with(user(...))** là tiện ích phù hợp cho test authorization đơn giản, nhưng nó không chứng minh hai phiên đăng nhập được lưu độc lập.

### Không chia sẻ session qua biến static

Không giữ Alice session hoặc Bob session trong static field, vì test khác có thể dùng lại đối tượng mutable này. Hãy tạo session bên trong từng test method hoặc helper được gọi trong test. Cách này làm rõ dữ liệu đầu vào và giúp các test độc lập, kể cả khi suite được cấu hình chạy song song.

## 10. Bài tập thực hành

1. Chạy test hai người dùng trong cùng một phương thức. Thay đổi thứ tự request Alice/Bob và xác minh body vẫn đúng theo session.
2. Cố tình truyền aliceSession cho request mà bạn nghĩ là của Bob. Quan sát test phát hiện sai danh tính như thế nào.
3. Thêm tài khoản thứ ba có role USER và kiểm tra người dùng này cũng bị từ chối ở /api/admin.
4. Logout Alice trong khi Bob vẫn đăng nhập. Xác minh session Bob không bị invalid và vẫn truy cập /api/me được.
5. Tạo một MockHttpSession mới, thêm thuộc tính ứng dụng bất kỳ, rồi kiểm tra nó vẫn không có Authentication. Giải thích sự khác nhau giữa dữ liệu session và SecurityContext.
6. Thử thay login helper bằng @WithMockUser hoặc .with(user(...)). Chỉ ra phần nào của hành trình đăng nhập và lưu session không còn được kiểm thử.

Khi nhiều người dùng được xử lý trong cùng một ca kiểm thử, bằng chứng quan trọng là **mỗi request khôi phục đúng danh tính từ session được chỉ định**, quyền được đánh giá theo principal đó và thao tác trên một phiên không làm thay đổi phiên còn lại. Đó là cơ sở để kiểm tra tính cô lập của phiên trong ứng dụng Servlet.
