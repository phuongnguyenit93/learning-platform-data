# Số phiên đồng thời và phiên bị hết hiệu lực khi ứng dụng dùng chức năng này

## 1. Vì sao cần giới hạn số phiên đăng nhập?

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, ứng dụng có thể cần giới hạn số phiên đăng nhập đồng thời cho mỗi tài khoản. Ví dụ, tài khoản nhân viên chỉ được đăng nhập trên một trình duyệt tại một thời điểm. Khi người dùng đăng nhập ở thiết bị thứ hai, ứng dụng có thể đánh dấu phiên cũ hết hiệu lực hoặc từ chối lần đăng nhập mới.

Spring Security hỗ trợ kiểm soát số phiên trong ứng dụng Servlet thông qua cấu hình **maximumSessions**, **SessionRegistry** và **ConcurrentSessionFilter**. Bài học này tập trung vào cách kiểm thử hành vi khi người dùng đăng nhập nhiều lần bằng cùng một tài khoản.

Sau bài này, bạn có thể:

- Cấu hình giới hạn số phiên hoạt động cho một principal.
- Phân biệt chính sách **hết hiệu lực phiên cũ** và **từ chối phiên đăng nhập mới**.
- Dùng SessionRegistry để kiểm tra phiên nào đang hoạt động hoặc đã bị đánh dấu hết hiệu lực.
- Dùng MockMvc kiểm thử hai lần đăng nhập của cùng người dùng.
- Xác minh request tiếp theo của phiên cũ bị ConcurrentSessionFilter từ chối.
- Nhận biết yêu cầu dọn dẹp SessionRegistry và giới hạn của kiểm soát phiên với API stateless.

## 2. Các thành phần quản lý phiên đồng thời

Spring Security phối hợp một số thành phần để theo dõi phiên đăng nhập:

| Thành phần | Vai trò |
| --- | --- |
| **SessionManagementConfigurer** | Nhận cấu hình giới hạn phiên trong SecurityFilterChain |
| **ConcurrentSessionControlAuthenticationStrategy** | Kiểm tra số phiên hiện có khi Authentication thành công; đánh dấu phiên cũ hết hiệu lực hoặc từ chối đăng nhập mới |
| **SessionRegistry** | Theo dõi principal, session ID, thời điểm truy cập và trạng thái hết hiệu lực |
| **RegisterSessionAuthenticationStrategy** | Đăng ký session mới sau khi xác thực thành công |
| **ConcurrentSessionFilter** | Kiểm tra phiên hiện tại có bị đánh dấu hết hiệu lực không ở request tiếp theo |
| **HttpSessionEventPublisher** | Phát sự kiện khi HTTP session được tạo hoặc hủy để SessionRegistry có thể dọn dữ liệu tương ứng |

Luồng khi giới hạn một phiên và chọn hết hiệu lực phiên cũ:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Browser A
    participant B as Browser B
    participant S as Spring Security
    participant R as SessionRegistry
    A->>S: Login alice
    S->>R: Đăng ký session S1
    S-->>A: Login thành công
    B->>S: Login alice lần hai
    S->>R: Tìm các session của alice
    S->>R: Đánh dấu S1 expired
    S->>R: Đăng ký session S2
    S-->>B: Login thành công
    A->>S: GET /profile với S1
    S->>R: Kiểm tra SessionInformation S1
    S-->>A: Logout phiên cũ và redirect expired URL
    B->>S: GET /profile với S2
    S->>R: S2 vẫn hợp lệ
    S-->>B: 200 OK
~~~

**Đánh dấu hết hiệu lực và invalidate session là hai thời điểm khác nhau.** Khi phiên mới được đăng nhập, SessionRegistry có thể đánh dấu phiên cũ là expired. Phiên cũ thường bị ConcurrentSessionFilter xử lý ở request tiếp theo: filter gọi logout handlers, vô hiệu hóa session và chuyển hướng theo expired URL.

## 3. Hai chính sách khi vượt giới hạn phiên

Với cấu hình tối đa một phiên, Spring Security có hai hành vi chính:

### 3.1. Hết hiệu lực phiên cũ để chấp nhận phiên mới

Đây là hành vi mặc định khi không bật **maxSessionsPreventsLogin(true)**. Khi alice đăng nhập lần hai:

- Phiên cũ được đánh dấu hết hiệu lực trong SessionRegistry.
- Phiên mới được đăng ký và có thể truy cập tài nguyên.
- Khi phiên cũ gửi request tiếp theo, ConcurrentSessionFilter phát hiện trạng thái expired và kết thúc phiên đó.
- Request của phiên cũ được chuyển đến URL hết hiệu lực đã cấu hình.

Cách này phù hợp khi muốn lần đăng nhập mới nhất có hiệu lực và phiên trước bị đẩy ra.

### 3.2. Từ chối lần đăng nhập mới

Khi bật **maxSessionsPreventsLogin(true)**, nếu người dùng đã đạt giới hạn phiên, lần xác thực mới bị từ chối bằng SessionAuthenticationException. Phiên cũ vẫn được giữ.

Cách này phù hợp khi muốn phiên đang hoạt động được ưu tiên và không cho đăng nhập ở thiết bị khác cho đến khi phiên hiện tại kết thúc.

| Tùy chọn | Phiên cũ | Phiên mới | Kết quả lần đăng nhập thứ hai |
| --- | --- | --- | --- |
| Mặc định, không bật maxSessionsPreventsLogin | Được đánh dấu expired | Được chấp nhận | Thành công; phiên cũ bị chặn ở request tiếp theo |
| **maxSessionsPreventsLogin(true)** | Vẫn hoạt động | Không được đăng ký thành phiên hợp lệ | Xác thực mới bị từ chối |

Giới hạn phiên được tính theo **principal** trong Authentication. Principal tùy chỉnh nên có equals() và hashCode() ổn định theo định danh người dùng; nếu mỗi lần xác thực tạo principal không có quy tắc so sánh nhất quán, SessionRegistry có thể coi cùng một tài khoản là nhiều principal khác nhau.

## 4. Cấu hình ứng dụng Servlet

Ví dụ dùng **Spring Boot 3.x**, **Spring Security 6.x**, Spring MVC và form login. Tài khoản alice chỉ được duy trì tối đa một phiên đăng nhập. Khi có đăng nhập mới, phiên cũ bị đánh dấu hết hiệu lực.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
class SecurityConfig {

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SessionRegistry sessionRegistry) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/profile").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .sessionManagement(session -> session
                .maximumSessions(1)
                .maxSessionsPreventsLogin(false)
                .expiredUrl("/login?expired")
                .sessionRegistry(sessionRegistry)
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

Controller dùng để kiểm tra principal:

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

Các điểm cần chú ý:

- **maximumSessions(1)** đặt giới hạn một phiên hoạt động cho mỗi principal.
- **maxSessionsPreventsLogin(false)** cho phép phiên mới được đăng nhập và đánh dấu phiên cũ hết hiệu lực.
- **expiredUrl("/login?expired")** xác định nơi chuyển hướng khi ConcurrentSessionFilter phát hiện phiên đã hết hiệu lực.
- **sessionRegistry(sessionRegistry)** dùng registry được quản lý bởi ứng dụng và có thể inject vào test.
- **HttpSessionEventPublisher** phát sự kiện vòng đời session để SessionRegistry loại bỏ thông tin session khi session bị hủy.

Trong ứng dụng thực tế, nếu dùng principal tùy chỉnh, hãy bảo đảm equals() và hashCode() dựa trên định danh ổn định. SessionRegistryImpl lưu principal làm khóa để tìm các session của cùng một người dùng.

## 5. Kiểm thử hai lần đăng nhập bằng MockMvc

Test quan trọng là đăng nhập alice hai lần bằng hai request độc lập, giữ lại hai MockHttpSession và kiểm tra trạng thái của từng phiên.

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
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ConcurrentSessionTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    SessionRegistry sessionRegistry;

    private MockHttpSession loginAsAlice() throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void secondLoginExpiresFirstSession() throws Exception {
        MockHttpSession firstSession = loginAsAlice();

        mockMvc.perform(get("/profile").session(firstSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        MockHttpSession secondSession = loginAsAlice();

        assertThat(secondSession.getId()).isNotEqualTo(firstSession.getId());

        SessionInformation firstInfo =
                sessionRegistry.getSessionInformation(firstSession.getId());
        SessionInformation secondInfo =
                sessionRegistry.getSessionInformation(secondSession.getId());

        assertThat(firstInfo).isNotNull();
        assertThat(firstInfo.isExpired()).isTrue();
        assertThat(secondInfo).isNotNull();
        assertThat(secondInfo.isExpired()).isFalse();

        // Phiên cũ bị ConcurrentSessionFilter xử lý ở request kế tiếp.
        mockMvc.perform(get("/profile").session(firstSession))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?expired"));

        assertThat(firstSession.isInvalid()).isTrue();

        // Phiên mới vẫn được phép truy cập.
        mockMvc.perform(get("/profile").session(secondSession))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

### 5.1. Vì sao phải giữ cả hai session?

MockMvc không tự lưu cookie giữa các lần gọi perform(). Mỗi lần login trong helper tạo một request độc lập và trả về MockHttpSession riêng. Nếu test không giữ hai session, ta không thể chứng minh rằng phiên cũ và phiên mới có trạng thái khác nhau.

### 5.2. Vì sao kiểm tra SessionInformation trước request của phiên cũ?

Ngay sau lần đăng nhập thứ hai, phiên cũ có thể mới chỉ được **đánh dấu expired** trong SessionRegistry. ConcurrentSessionFilter thường thực hiện logout và invalidate khi phiên cũ gửi request tiếp theo. Vì vậy, kiểm tra SessionInformation trước rồi mới gửi request cũ giúp phân biệt hai bước:

1. Chính sách concurrency phát hiện vượt giới hạn và đánh dấu phiên cũ.
2. Filter từ chối request tiếp theo, kết thúc session cũ và chuyển hướng đến expired URL.

### 5.3. Request của phiên mới phải vẫn thành công

Sau khi phiên cũ bị từ chối, session mới cần tiếp tục truy cập tài nguyên. Assertion 200 và body alice xác nhận rằng việc hết hiệu lực phiên cũ không làm mất trạng thái đăng nhập của phiên mới.

## 6. Từ chối đăng nhập mới bằng maxSessionsPreventsLogin

Nếu sản phẩm yêu cầu chỉ một thiết bị được đăng nhập và không cho phép lần đăng nhập mới đẩy phiên cũ ra, đổi cấu hình thành:

~~~java
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
    .expiredUrl("/login?expired")
    .sessionRegistry(sessionRegistry)
)
~~~

Khi alice đã có một phiên hoạt động, lần đăng nhập thứ hai bị từ chối bởi chiến lược kiểm soát phiên. Form login mặc định thường chuyển hướng về **/login?error** do SessionAuthenticationException được xử lý như một lỗi đăng nhập.

Test minh họa cho context có cấu hình **maxSessionsPreventsLogin(true)**:

~~~java
@Test
void secondLoginIsRejectedAndFirstSessionRemainsActive()
        throws Exception {
    MockHttpSession firstSession = loginAsAlice();

    mockMvc.perform(get("/profile").session(firstSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

    mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "secret"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

    // Phiên đầu tiên không bị đánh dấu hết hiệu lực.
    SessionInformation firstInfo =
            sessionRegistry.getSessionInformation(firstSession.getId());
    assertThat(firstInfo).isNotNull();
    assertThat(firstInfo.isExpired()).isFalse();

    mockMvc.perform(get("/profile").session(firstSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
}
~~~

Test này cần chạy với SecurityFilterChain có **maxSessionsPreventsLogin(true)**, không phải cấu hình hết hiệu lực phiên cũ ở mục 4. Nếu ứng dụng có AuthenticationFailureHandler tùy chỉnh, hãy điều chỉnh assertion redirect theo response thực tế.

## 7. Dọn dẹp SessionRegistry và giới hạn của test

SessionRegistry cần nhận được sự kiện khi session bị hủy để loại bỏ bản ghi tương ứng. Với Servlet container, đăng ký **HttpSessionEventPublisher** như bean trong cấu hình giúp phát SessionDestroyedEvent khi session kết thúc.

Nếu thiếu publisher hoặc session store không phát sự kiện vòng đời tương ứng, SessionRegistry có thể giữ thông tin session đã không còn tồn tại. Điều này có thể làm bộ đếm phiên hoạt động sai, nhất là khi giới hạn số phiên chặt.

Một số lưu ý khi kiểm thử:

- **Session timeout:** container sẽ hủy session khi hết thời hạn; cần có sự kiện để registry dọn thông tin.
- **Logout:** logout handler invalidate session; registry cần được cập nhật qua sự kiện session destroyed.
- **MockMvc:** phù hợp để kiểm tra SessionRegistry, trạng thái expired và ConcurrentSessionFilter, nhưng không mô phỏng đầy đủ mọi chi tiết timeout của container.
- **Nhiều instance:** nếu ứng dụng chạy nhiều node, SessionRegistry trong bộ nhớ của từng node không tự chia sẻ trạng thái. Cần thiết kế registry hoặc cơ chế quản lý session dùng chung phù hợp.
- **Principal tùy chỉnh:** equals() và hashCode() phải ổn định để cùng người dùng được nhận diện là một principal.
- **JWT stateless:** SessionRegistry không giới hạn số bearer token đang có hiệu lực. Muốn giới hạn phiên/token stateless cần cơ chế riêng như token registry, refresh-token rotation hoặc revocation.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đăng nhập hai lần nhưng phiên cũ vẫn truy cập được | Chưa cấu hình maximumSessions, filter chain không chạy hoặc test không dùng đúng session | Kiểm tra cấu hình concurrency và truyền session vào request |
| SessionRegistry không tìm thấy session | Chưa đăng ký session strategy, registry khác instance hoặc lấy ID trước khi session fixation đổi ID | Inject cùng SessionRegistry và lấy session ID sau login |
| Phiên cũ chỉ bị đánh dấu expired, chưa invalid ngay | ConcurrentSessionFilter xử lý ở request kế tiếp | Gửi request tiếp theo bằng session cũ rồi kiểm tra expired URL |
| Người dùng bị từ chối ngay ở lần login thứ hai | Đã bật maxSessionsPreventsLogin(true) | Kiểm tra chính sách mong muốn và assertion login failure |
| Registry còn bản ghi session đã hủy | Thiếu HttpSessionEventPublisher hoặc session store không phát sự kiện | Đăng ký publisher và kiểm tra vòng đời session |
| Hai principal cùng username nhưng không được tính chung | Principal tùy chỉnh thiếu equals/hashCode ổn định | Dùng định danh người dùng ổn định làm cơ sở so sánh |
| Nhiều node cho phép vượt giới hạn | SessionRegistry chỉ lưu trong bộ nhớ từng node | Dùng giải pháp quản lý session đồng bộ giữa các node |
| JWT vẫn dùng được dù đã logout session | JWT stateless không thuộc SessionRegistry | Dùng cơ chế quản lý và thu hồi token riêng |

## 9. Bài tập thực hành

1. Chạy test hai lần đăng nhập với cấu hình mặc định. Kiểm tra phiên đầu tiên bị đánh dấu expired và phiên thứ hai vẫn truy cập được.
2. Thêm assertion đọc SessionInformation trước và sau request cũ để quan sát thời điểm session bị invalidate.
3. Đổi maxSessionsPreventsLogin thành true. Xác minh lần đăng nhập thứ hai bị từ chối và phiên đầu tiên tiếp tục hoạt động.
4. Tạm bỏ HttpSessionEventPublisher trong môi trường test riêng, quan sát cách registry giữ thông tin session sau khi session bị hủy.
5. Tạo principal tùy chỉnh không có equals/hashCode ổn định, quan sát kết quả đếm phiên rồi sửa theo user ID.
6. Mở rộng ứng dụng có nhiều node và đánh giá cách chia sẻ session registry.
7. Với API JWT stateless, thiết kế test giới hạn refresh token hoặc token đang hoạt động thay vì dùng SessionRegistry.

Khi kiểm thử giới hạn phiên, hãy chứng minh rõ **cùng một principal có bao nhiêu session hoạt động, chính sách chọn phiên nào bị hết hiệu lực hoặc từ chối, và request tiếp theo của phiên bị ảnh hưởng được xử lý ra sao**. Chỉ kiểm tra response đăng nhập thành công chưa đủ để xác nhận concurrency control đang hoạt động.
