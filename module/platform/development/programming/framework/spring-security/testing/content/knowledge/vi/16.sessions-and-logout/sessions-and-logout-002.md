# Dùng MockHttpSession để kiểm tra tiếp nối phiên Servlet

## 1. Bài toán: đăng nhập ở request đầu, truy cập ở request sau

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, một bài kiểm thử quan trọng là xác nhận người dùng đã đăng nhập có thể tiếp tục truy cập tài nguyên ở những request sau. Đây là phần thực hành của mục tiêu kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng **spring-security-test** trên ứng dụng Servlet.

Giả sử người dùng **alice** đăng nhập bằng form login. Request đăng nhập trả về redirect và server lưu trạng thái xác thực trong HTTP session. Tiếp theo, client gửi **GET /api/me** với cùng session. Endpoint phải nhận ra alice mà không yêu cầu gửi lại mật khẩu.

Khi kiểm thử với **MockMvc**, ta không có trình duyệt thật tự quản lý cookie. Ta cần lấy **MockHttpSession** sau khi đăng nhập và truyền nó vào request tiếp theo bằng **.session(session)**. Nếu bỏ bước này, request thứ hai có thể bị coi là chưa đăng nhập, dù request đầu đã thành công.

Sau bài học, bạn có thể:

- Tạo, lấy và tái sử dụng **MockHttpSession** trong nhiều lời gọi MockMvc.
- Kiểm tra SecurityContext thực sự được gắn với session sau form login.
- Viết test cho ba tình huống: **cùng session**, **session khác** và **đã logout**.
- Phân biệt việc kiểm thử tiếp nối phiên với kiểm thử phân quyền bằng **@WithMockUser**.
- Nhận biết các giới hạn của MockHttpSession với hệ thống stateless, ứng dụng Reactive và triển khai HTTP thực tế.

## 2. MockHttpSession mô phỏng điều gì?

**HttpSession** là nơi ứng dụng Servlet lưu trạng thái phía server. Trình duyệt thông thường giữ cookie như **JSESSIONID** và gửi lại cookie trong các request sau, giúp server tra cứu đúng session.

**MockHttpSession** là implementation dùng cho test trong thư viện **spring-test**. Nó mô phỏng các thao tác của HttpSession, chẳng hạn **getAttribute**, **setAttribute**, **getId**, **invalidate**, **isInvalid**. Cùng một đối tượng MockHttpSession được đưa vào nhiều request MockMvc giúp các request đó chia sẻ trạng thái phiên trong môi trường kiểm thử.

Các thao tác thường dùng:

| Thao tác | Ý nghĩa khi kiểm thử |
| --- | --- |
| **new MockHttpSession()** | Tạo một phiên giả lập độc lập |
| **result.getRequest().getSession(false)** | Lấy session hiện có sau khi một request chạy; không tạo session chỉ để đọc |
| **.session(session)** | Đưa session vào request MockMvc mới |
| **session.getAttribute(name)** | Kiểm tra dữ liệu server lưu trong session |
| **session.setAttribute(name, value)** | Chuẩn bị thuộc tính session cho một tình huống test |
| **session.invalidate()** | Vô hiệu hóa session giả lập |
| **session.isInvalid()** | Kiểm tra session đã bị vô hiệu hóa |

Ví dụ ngắn để thấy cách truyền trạng thái:

~~~java
MockHttpSession session = new MockHttpSession();
session.setAttribute("cartId", "CART-123");

mockMvc.perform(get("/api/me").session(session));
~~~

Đoạn này mới minh họa việc chuyển session vào request. **Thêm một thuộc tính cartId không khiến người dùng được xác thực**. Để kiểm thử tiếp nối đăng nhập, ta cần một bước login thật đi qua Spring Security và tạo SecurityContext hợp lệ.

### SecurityContext được lưu trong session thế nào?

Trong cấu hình dùng HTTP session, Spring Security có thể lưu một **SecurityContext** chứa **Authentication** dưới key do **HttpSessionSecurityContextRepository** định nghĩa, thường là **SPRING_SECURITY_CONTEXT**. Request sau sử dụng lại session thì cơ chế bảo mật có thể đọc SecurityContext ấy để khôi phục danh tính.

~~~mermaid
sequenceDiagram
    participant T as MockMvc test
    participant L as POST /login
    participant S as MockHttpSession
    participant G as GET /api/me
    T->>L: username + password + CSRF
    L->>S: Lưu SecurityContext của alice
    L-->>T: Redirect, request có session
    T->>S: Lấy getSession(false)
    T->>G: .session(session)
    G->>S: Đọc SecurityContext
    G-->>T: 200 OK, body alice
~~~

**Điểm cốt lõi:** SecurityContextHolder chỉ cung cấp ngữ cảnh cho request hiện tại. Việc request sau tiếp tục đăng nhập phụ thuộc vào cơ chế lưu và khôi phục SecurityContext. Với Spring Security 6, những luồng xác thực tự viết thường phải lưu ngữ cảnh rõ ràng qua SecurityContextRepository; form login chuẩn đã được tích hợp cơ chế này.

## 3. Ứng dụng Servlet mẫu để kiểm thử

Ví dụ sau dùng **Spring Boot 3.x**, **Spring Security 6.x**, **JUnit 5**, **MockMvc**, **AssertJ** và **spring-security-test**. Những dependency thường cần có:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Nếu dự án dùng Maven, thêm artifact **org.springframework.security:spring-security-test** với scope **test**. Nên để dependency management của Spring Boot thống nhất phiên bản phụ thuộc.

### 3.1. Cấu hình login, session và logout

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
                .requestMatchers("/api/me").authenticated()
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-secret"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Trong cấu hình này:

- **POST /login** được Spring Security xử lý theo form login mặc định, với hai tham số **username** và **password**.
- **GET /api/me** cần người dùng đã xác thực.
- **POST /logout** xử lý đăng xuất; mặc định Spring Security có thể vô hiệu hóa HTTP session và xóa SecurityContext.
- **SessionCreationPolicy.IF_REQUIRED** cho phép Spring Security tạo session khi cần.
- CSRF protection vẫn được bật theo mặc định, nên các request POST trong bài sẽ dùng **.with(csrf())**.

Hai tài khoản trên chỉ dùng cho ví dụ. Không đưa mật khẩu mẫu vào môi trường triển khai thực tế.

### 3.2. Endpoint đọc tên người dùng

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    String currentUser(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Khi SecurityContext được nạp đúng từ session, controller trả về **alice** hoặc **bob**. Nếu request chưa được xác thực, Spring Security sẽ chặn truy cập trước khi controller chạy. Với **formLogin** mặc định, kết quả thường là redirect đến trang login, thay vì mã **401** của HTTP Basic.

## 4. Bài test hoàn chỉnh: giữ session qua nhiều request

Bộ kiểm thử sau đặt trong nguồn test của ứng dụng Spring Boot có cấu hình và controller ở mục 3:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
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
class ServletSessionContinuationTest {

    @Autowired
    MockMvc mockMvc;

    private MockHttpSession loginAs(String username, String password)
            throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", username)
                    .param("password", password))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        // Lấy session SAU đăng nhập, vì Spring Security có thể đổi session ID.
        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertThat(saved).isInstanceOf(SecurityContext.class);

        SecurityContext context = (SecurityContext) saved;
        assertThat(context.getAuthentication()).isNotNull();
        assertThat(context.getAuthentication().getName()).isEqualTo(username);
        return session;
    }

    @Test
    void sameSession_preservesAuthenticatedUser() throws Exception {
        MockHttpSession aliceSession = loginAs("alice", "secret");

        mockMvc.perform(get("/api/me").session(aliceSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        // Có thể tái sử dụng cùng session ở request tiếp theo nữa.
        mockMvc.perform(get("/api/me").session(aliceSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void withoutSession_cannotReusePreviousLogin() throws Exception {
        loginAs("alice", "secret");

        // MockMvc không tự nhớ session của perform() trước đó.
        mockMvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void anotherSession_doesNotInheritAliceIdentity() throws Exception {
        MockHttpSession aliceSession = loginAs("alice", "secret");
        MockHttpSession freshSession = new MockHttpSession();

        mockMvc.perform(get("/api/me").session(freshSession))
                .andExpect(status().is3xxRedirection());

        mockMvc.perform(get("/api/me").session(aliceSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void sessionsOfTwoUsersRemainIndependent() throws Exception {
        MockHttpSession aliceSession = loginAs("alice", "secret");
        MockHttpSession bobSession = loginAs("bob", "bob-secret");

        mockMvc.perform(get("/api/me").session(aliceSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        mockMvc.perform(get("/api/me").session(bobSession))
                .andExpect(status().isOk())
                .andExpect(content().string("bob"));
    }

    @Test
    void logout_invalidatesTheSession() throws Exception {
        MockHttpSession aliceSession = loginAs("alice", "secret");

        mockMvc.perform(post("/logout")
                    .session(aliceSession)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertThat(aliceSession.isInvalid()).isTrue();

        // Request độc lập sau logout phải xác thực lại.
        mockMvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

### Giải thích từng bước quan trọng

**Bước 1 – Đăng nhập qua SecurityFilterChain.** **post("/login")** cùng tham số username/password gửi request qua bộ lọc xác thực thực. Khi thành công, cơ chế form login có thể lưu Authentication vào SecurityContext và gắn SecurityContext với session.

**Bước 2 – Lấy session bằng getSession(false).** Giá trị **false** rất có ý nghĩa: phép đọc không tạo một session rỗng để che giấu lỗi. Nếu kết quả là **null** trong cấu hình mẫu, có thể login chưa thành công, không có cơ chế lưu session hoặc cấu hình không giống giả định.

**Bước 3 – Kiểm tra SecurityContext trong session.** Test đọc key **SPRING_SECURITY_CONTEXT_KEY** để xác minh đối tượng đã lưu chứa đúng principal. Assertion này phù hợp với cấu hình mẫu dùng repository dựa trên HttpSession. Nếu ứng dụng dùng repository tùy biến hoặc Spring Session với cơ chế lưu riêng, có thể cần khẳng định qua hành vi request kế tiếp thay vì kiểm tra key nội bộ.

**Bước 4 – Truyền session sang request tiếp theo.** **get("/api/me").session(aliceSession)** sử dụng chính session sau đăng nhập. Đây là điểm làm cho bài test chứng minh sự tiếp nối của cùng một phiên Servlet.

**Bước 5 – Kiểm tra tách biệt phiên.** Request không có session và request dùng **new MockHttpSession()** không được nhận danh tính alice; ngược lại, hai session alice/bob phải trả đúng tên của chủ phiên.

**Bước 6 – Đăng xuất.** Request logout sử dụng session đang đăng nhập và CSRF token. Ta kiểm tra session đã vô hiệu hóa. Không tái sử dụng một MockHttpSession đã bị vô hiệu hóa trong request mới: một đối tượng session invalid không tương đương với một phiên client mới hợp lệ.

## 5. Ma trận tình huống và kỳ vọng

| Tiền điều kiện | Request tiếp theo | Kỳ vọng với cấu hình mẫu | Ý nghĩa |
| --- | --- | --- | --- |
| Alice login thành công, session A | GET /api/me + session A | **200**, body **alice** | Danh tính được tiếp nối |
| Alice login thành công, session A | GET /api/me, không truyền session | **3xx** về login | MockMvc không tự giữ session |
| Alice login thành công, session A | GET /api/me + session B mới | **3xx** về login | Session khác không thừa hưởng danh tính |
| Alice login session A; Bob login session B | GET /api/me + A, rồi + B | Lần lượt **alice**, **bob** | Ngữ cảnh của mỗi session độc lập |
| Alice login session A rồi POST /logout | Kiểm tra A.isInvalid() | **true** | Phiên đăng nhập đã bị hủy |

Mã trạng thái **3xx** áp dụng cho luồng form login mặc định trong ví dụ. Nếu ứng dụng cấu hình HTTP Basic, API JSON, custom authentication entry point hoặc access-denied handler, kỳ vọng có thể là **401/403** hay một response khác. Test phải đối chiếu với chính sách của ứng dụng.

## 6. Kiểm thử session bị hết hạn hoặc bị vô hiệu hóa

Có thể dùng **MockHttpSession.invalidate()** để mô phỏng trạng thái session đã bị vô hiệu hóa phía server. Tuy nhiên, không nên cố gán chính object đã invalid cho request mới rồi khẳng định response HTTP theo cơ chế của container thật. Thay vào đó, ta xác minh hành vi của một request sử dụng **session mới, chưa xác thực**:

~~~java
@Test
void afterSessionInvalidation_newSessionMustLogInAgain() throws Exception {
    MockHttpSession expired = loginAs("alice", "secret");
    expired.invalidate();
    assertThat(expired.isInvalid()).isTrue();

    MockHttpSession fresh = new MockHttpSession();
    mockMvc.perform(get("/api/me").session(fresh))
            .andExpect(status().is3xxRedirection());
}
~~~

Phép kiểm thử trên xác nhận rằng trạng thái xác thực từ session cũ không tự xuất hiện trong session mới. Nó **không chứng minh toàn bộ** cách servlet container xử lý cookie JSESSIONID hết hạn, thời gian timeout thực, hay cơ chế session fixation ở tầng HTTP. Các hành vi đó cần kiểm thử tích hợp phù hợp với container và cấu hình triển khai nếu là yêu cầu sản phẩm.

### Đừng giả định session ID trước và sau login luôn giống nhau

Spring Security có các biện pháp chống **session fixation**. Tùy cấu hình và servlet container, ID của session có thể đổi trong quá trình đăng nhập. Vì vậy, cách ổn định là **lấy session sau khi request login hoàn tất**, như helper **loginAs(...)**, rồi dùng session đó cho request tiếp theo. Không tự tạo một session trước login và mặc định rằng mọi thuộc tính hoặc ID vẫn nguyên vẹn trong mọi cấu hình.

### Thuộc tính ứng dụng và ngữ cảnh bảo mật là hai chuyện khác nhau

Một session có thể chứa thuộc tính ứng dụng như giỏ hàng, locale hoặc thông tin điều hướng, đồng thời chứa SecurityContext do Spring Security lưu. Test tiếp nối đăng nhập cần xác minh **Authentication được khôi phục và phân quyền đúng**. Chỉ kiểm tra một thuộc tính tùy ý còn tồn tại không đủ để chứng minh bảo mật hoạt động.

## 7. Các cách kiểm thử dễ gây nhầm lẫn

### 7.1. @WithMockUser không thay thế bước login và lưu session

Ví dụ sau hữu ích khi muốn kiểm tra một endpoint có chấp nhận người dùng mang role USER hay không:

~~~java
@WithMockUser(username = "alice", roles = "USER")
@Test
void authorizedMockUser_canReadProfile() throws Exception {
    mockMvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
}
~~~

Annotation cần import **org.springframework.security.test.context.support.WithMockUser**. Đây là phép kiểm tra với danh tính được mock cho test. Nó **không tự chứng minh** rằng form login đã xác thực mật khẩu, SecurityContext được lưu trong HttpSession rồi được nạp lại ở một request độc lập.

Tương tự, **.with(user("alice"))** đặt một danh tính test trên request. Nếu mục tiêu là kiểm chứng phiên Servlet sau đăng nhập, hãy dùng luồng **POST /login → lấy MockHttpSession → GET cùng session**.

### 7.2. Bỏ qua Spring Security filters gây kết quả giả

Với **@SpringBootTest** và **@AutoConfigureMockMvc** mặc định, MockMvc được cấu hình để chạy các filter của application context. Nếu đặt **@AutoConfigureMockMvc(addFilters = false)** hoặc tự dựng MockMvc mà không áp dụng security filter chain, request có thể đi vào controller dù chưa đăng nhập. Một bài test trả **200** khi đó không chứng minh tính đúng đắn của session security.

Nếu tự dựng MockMvc từ **WebApplicationContext**, cách tích hợp Spring Security thường dùng là:

~~~java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

Trong đó cần import **MockMvcBuilders** từ Spring Test và static import **springSecurity** từ **SecurityMockMvcConfigurers**.

### 7.3. POST login hoặc logout trả 403 vì thiếu CSRF

Trong mẫu cấu hình này, Spring Security bật CSRF protection. Request POST thiếu token hợp lệ có thể bị chặn trước khi xử lý login hoặc logout. Cần **.with(csrf())** ở request POST trong test. Không nên mặc định rằng **403** tại login có nghĩa là mật khẩu sai.

### 7.4. Một phiên HTTP Basic hoặc JWT không có nghĩa sẽ tiếp nối bằng session

Với API stateless, client gửi HTTP Basic credentials, bearer token hoặc JWT trên **mỗi request**. Khi Spring Security được cấu hình **STATELESS** và không lưu Authentication vào HttpSession, request thứ hai không có credentials vẫn phải bị từ chối. Trong tình huống đó, dùng MockHttpSession để mong Authentication tự xuất hiện là sai mục tiêu kiểm thử.

Đối với stack **Reactive**, ứng dụng dùng WebFlux, **WebTestClient**, **WebSession** và SecurityContextRepository tương ứng của Reactive; **MockHttpSession** là công cụ thuộc stack **Servlet**. Một module bao quát Servlet và Reactive cần lựa chọn đúng tiện ích theo stack.

## 8. Bảng chẩn đoán lỗi

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Login redirect nhưng session không có SecurityContext | Login có thật sự thành công? Session policy và repository có lưu ngữ cảnh không? |
| Request thứ hai luôn redirect về login | Có truyền đúng **.session(session)** được lấy từ request login không? |
| Request không có session vẫn trả 200 | Có **@WithMockUser** hoặc mock identity gắn sẵn? Bộ lọc Spring Security có đang chạy? |
| Hai user trả cùng principal | Có tái sử dụng nhầm cùng MockHttpSession hoặc danh tính mock trong test? |
| POST /logout trả 403 | Có CSRF token không? Method và đường dẫn logout có đúng cấu hình? |
| Lỗi khi dùng lại session sau logout | MockHttpSession đã bị invalid; cần mô phỏng request mới bằng session mới |
| Session attribute không có trong hệ thống tùy biến | Ứng dụng đang dùng repository khác hoặc stateless; kiểm tra hành vi thực tế thay cho key mặc định |
| Test pass với MockMvc nhưng lỗi trên trình duyệt | Cookie, SameSite, HTTPS, reverse proxy hoặc session store thật chưa được kiểm thử ở tầng mạng |

## 9. Bài tập mở rộng

1. Chạy bộ test ở mục 4 với đầy đủ filter. Xác minh rằng **sameSession_preservesAuthenticatedUser** đạt và **withoutSession_cannotReusePreviousLogin** bị chuyển hướng.
2. Bỏ **.session(aliceSession)** khỏi request GET thứ hai. Giải thích vì sao login trước đó không giúp request này được xác thực.
3. Đổi helper **loginAs(...)** để cố tình nhập sai mật khẩu. Sau đó kiểm tra redirect đăng nhập thất bại, không giả định có SecurityContext hợp lệ trong session.
4. Thêm endpoint **GET /api/admin** yêu cầu **ROLE_ADMIN**. Kiểm tra rằng session của alice đã xác thực nhưng thiếu role vẫn bị **403**, qua đó tách xác thực khỏi phân quyền.
5. Sửa ứng dụng thành stateless rồi so sánh kết quả. Xác định vì sao tiếp nối qua session không còn là hành vi mong đợi.
6. Thêm thuộc tính giỏ hàng vào session và đọc lại qua request sau. Phân biệt phép kiểm tra thuộc tính ứng dụng với việc Spring Security khôi phục Authentication.

Khi kiểm thử tiếp nối phiên Servlet, bằng chứng quan trọng là **cùng một session từ request đăng nhập được sử dụng trong request cần bảo vệ**, trong khi request dùng session khác không được thừa hưởng danh tính. **MockHttpSession** giúp mô phỏng chính xác sự chia sẻ trạng thái ấy trong phạm vi MockMvc, còn các hành vi của browser, cookie và container thực cần được xác minh ở cấp kiểm thử thích hợp.
