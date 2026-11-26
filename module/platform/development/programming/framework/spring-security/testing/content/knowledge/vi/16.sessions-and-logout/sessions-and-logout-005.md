# Session fixation và thay đổi mã phiên theo chiến lược đã chọn

## 1. Vì sao phải đổi mã phiên sau khi đăng nhập?

Trong chương **Phiên và đăng xuất** của module **SPRING_SECURITY_TESTING**, ta cần kiểm chứng không chỉ việc người dùng đăng nhập thành công và tiếp tục sử dụng session, mà cả việc session đó có được bảo vệ khi quyền truy cập thay đổi hay không.

**Session fixation** là kiểu tấn công trong đó kẻ xấu khiến nạn nhân sử dụng một session ID mà kẻ xấu đã biết hoặc có thể dự đoán. Nếu nạn nhân đăng nhập mà ứng dụng vẫn giữ nguyên ID đó, kẻ xấu có thể dùng cùng ID để truy cập phiên đã xác thực. Vì vậy, sau khi xác thực thành công, ứng dụng cần thay đổi mã phiên hoặc tạo một session mới theo chiến lược phù hợp.

Bài này tập trung vào **kiểm thử sự thay đổi session ID khi đăng nhập bằng MockMvc** và cách xác minh các chiến lược session fixation của Spring Security. Sau bài học, bạn có thể:

- Giải thích session fixation và phân biệt nó với session hijacking.
- Cấu hình chiến lược **changeSessionId**, **migrateSession**, **newSession** và **none**.
- Ghi lại session ID trước khi xác thực, sau đó xác minh session ID đã đổi sau đăng nhập.
- Kiểm tra dữ liệu ứng dụng trong session được giữ lại hay bị loại bỏ theo chiến lược.
- Nhận biết giới hạn của MockHttpSession và những gì cần kiểm chứng thêm trên Servlet container thực tế.

## 2. Hiểu đúng về session fixation

Giả sử một ứng dụng tạo session cho khách truy cập chưa đăng nhập. Session có ID là **S1**. Kẻ xấu biết hoặc ép nạn nhân sử dụng ID **S1**. Nạn nhân đăng nhập thành công, nhưng ứng dụng vẫn dùng S1. Khi đó, kẻ xấu có thể thử gửi request với ID S1 và thừa hưởng phiên đã xác thực.

Luồng dễ bị tấn công:

~~~mermaid
sequenceDiagram
    participant A as Attacker
    participant V as Victim
    participant App as Application
    A->>App: Tạo session, nhận ID S1
    A->>V: Dụ nạn nhân dùng session ID S1
    V->>App: Đăng nhập với session S1
    App-->>V: Xác thực thành công, vẫn giữ S1
    A->>App: Gửi request bằng S1
    App-->>A: Có thể nhận diện là phiên đã đăng nhập
~~~

Cách bảo vệ là **đổi session ID sau khi xác thực thành công**. Nếu ID ban đầu là S1, ứng dụng chuyển sang ID S2. Kẻ xấu chỉ biết S1 sẽ không thể dùng ID cũ để truy cập phiên mới.

~~~mermaid
sequenceDiagram
    participant V as Victim
    participant App as Application
    participant A as Attacker
    V->>App: Đăng nhập bằng session ID S1
    App->>App: Xác thực thành công
    App->>App: Thay session ID S1 thành S2
    App-->>V: Trả response với session ID S2
    A->>App: Gửi request bằng ID S1
    App-->>A: Không còn là phiên đã xác thực
~~~

**Session fixation khác session hijacking.** Fixation bắt đầu từ việc kẻ tấn công biết trước hoặc áp đặt ID cho nạn nhân trước khi đăng nhập. Hijacking thường là việc kẻ tấn công chiếm được một session ID đang có hiệu lực sau khi người dùng đã đăng nhập. Đổi ID khi xác thực giúp chống fixation; nó không thay thế các biện pháp bảo vệ cookie, HTTPS, XSS hay phát hiện session bị đánh cắp.

## 3. Các chiến lược session fixation trong Spring Security

Spring Security cung cấp các chiến lược xử lý session fixation thông qua cấu hình **sessionManagement**. Với Servlet 3.1 trở lên, chiến lược mặc định thường là **changeSessionId**; ở môi trường Servlet cũ hơn, Spring Security có thể dùng **migrateSession**. Có thể cấu hình tường minh để hành vi rõ ràng và dễ kiểm thử.

| Chiến lược | Hành vi | Thuộc tính session ứng dụng |
| --- | --- | --- |
| **changeSessionId** | Gọi Servlet API `HttpServletRequest.changeSessionId()` để đổi ID của session hiện tại | Giữ nguyên session và các thuộc tính |
| **migrateSession** | Hủy session cũ, tạo session mới và sao chép các thuộc tính từ session cũ | Thuộc tính ứng dụng được chuyển sang session mới |
| **newSession** | Tạo session mới sạch, không sao chép các thuộc tính ứng dụng cũ | Các thuộc tính ứng dụng cũ bị loại bỏ; thuộc tính cần thiết của Spring Security được xử lý riêng |
| **none** | Không thực hiện bảo vệ session fixation | Giữ session ID cũ |

### 3.1. changeSessionId

Đây là lựa chọn phù hợp với Servlet API hiện đại. Container đổi ID của session hiện tại bằng **changeSessionId()**. Đối tượng session và các thuộc tính vẫn được giữ; chỉ định danh session thay đổi.

Ví dụ: trước đăng nhập, session có ID S1 và thuộc tính `cartId`. Sau đăng nhập, session có ID S2, nhưng `cartId` vẫn còn. Đây là hành vi mong đợi khi ứng dụng cần giữ giỏ hàng hoặc dữ liệu điều hướng của khách trước đăng nhập.

### 3.2. migrateSession

Chiến lược này tạo một session mới sau khi đăng nhập, đồng thời sao chép các thuộc tính hiện có từ session cũ sang session mới. Session cũ bị vô hiệu hóa. Nó hữu ích khi cần chuyển trạng thái ứng dụng trước đăng nhập sang phiên đã xác thực và muốn hành vi tương thích với Servlet container không hỗ trợ đổi ID trực tiếp.

### 3.3. newSession

Chiến lược này tạo một session mới mà không chuyển các thuộc tính ứng dụng thông thường từ session cũ. Các thuộc tính cần thiết của Spring Security được xử lý theo cơ chế riêng. Chọn chiến lược này khi ứng dụng muốn loại bỏ trạng thái session do client chưa xác thực tạo ra, chấp nhận việc các dữ liệu như giỏ hàng tạm thời không được giữ.

### 3.4. none

Chiến lược này giữ nguyên session ID và không thực hiện biện pháp chống fixation. Đây thường không phải lựa chọn phù hợp cho ứng dụng đăng nhập bằng session. Chỉ dùng khi có yêu cầu kiến trúc đặc biệt và đã đánh giá đầy đủ rủi ro.

## 4. Cấu hình ứng dụng mẫu

Ví dụ sử dụng **Spring Boot 3.x**, **Spring Security 6.x**, ứng dụng **Spring MVC (Servlet)** và form login. Người dùng alice có quyền USER; endpoint profile chỉ yêu cầu đã xác thực.

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
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
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
                .build()
        );
    }
}
~~~

Để kiểm tra việc tiếp tục sử dụng phiên sau đăng nhập, controller có thể trả về tên người dùng hiện tại:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    String profile(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Điểm cần chú ý trong cấu hình là:

- **IF_REQUIRED** cho phép tạo session khi cần.
- **changeSessionId()** chỉ rõ chiến lược đổi ID khi xác thực thành công.
- **formLogin()** kích hoạt luồng xác thực form chuẩn của Spring Security.
- **/api/profile** yêu cầu Authentication hợp lệ.

Trong ứng dụng thật, hãy chọn một chiến lược theo yêu cầu lưu trạng thái của sản phẩm và khả năng của Servlet container. Không nên chọn **none** chỉ để giữ ID hoặc thuộc tính cũ cho tiện.

## 5. Kiểm thử đổi session ID bằng MockMvc

Mục tiêu của test là tạo một session **trước đăng nhập**, lưu lại ID ban đầu, sau đó gửi request đăng nhập bằng session đó. Khi đăng nhập thành công, test lấy session từ request login và so sánh ID.

Cần các dependency test như **spring-boot-starter-test** và **spring-security-test**. Ví dụ dưới đây dùng JUnit 5, AssertJ và MockMvc.

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
class SessionFixationMockMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginChangesSessionIdAndPreservesApplicationAttributes()
            throws Exception {
        // Session tồn tại trước khi người dùng xác thực.
        MockHttpSession beforeLogin = new MockHttpSession();
        beforeLogin.setAttribute("cartId", "CART-42");
        String originalId = beforeLogin.getId();

        MvcResult loginResult = mockMvc.perform(post("/login")
                    .session(beforeLogin)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "secret"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        // Lấy session sau xác thực, không dùng ID cũ để giả định kết quả.
        MockHttpSession afterLogin = (MockHttpSession)
                loginResult.getRequest().getSession(false);

        assertThat(afterLogin).isNotNull();
        assertThat(afterLogin.getId()).isNotEqualTo(originalId);

        // changeSessionId đổi ID của cùng session, không thay object.
        assertThat(afterLogin).isSameAs(beforeLogin);
        assertThat(afterLogin.getAttribute("cartId")).isEqualTo("CART-42");

        Object savedContext = afterLogin.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertThat(savedContext).isInstanceOf(SecurityContext.class);

        SecurityContext context = (SecurityContext) savedContext;
        assertThat(context.getAuthentication().getName()).isEqualTo("alice");

        // Phiên mới sau xác thực tiếp tục được dùng để gọi tài nguyên bảo vệ.
        mockMvc.perform(get("/api/profile").session(afterLogin))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

### 5.1. Vì sao phải tạo session trước đăng nhập?

Nếu test chỉ gửi POST login mà không có session trước đó, Spring Security có thể tạo session sau khi xác thực để lưu SecurityContext. Test khi đó không có **ID cũ** để so sánh. Một response thành công không tự chứng minh biện pháp chống fixation đã đổi ID.

Bằng cách tạo **MockHttpSession** trước, lưu `originalId`, rồi gửi session đó vào POST login, test mô phỏng chính xác tiền điều kiện của session fixation: có một phiên chưa xác thực tồn tại trước khi người dùng đăng nhập.

### 5.2. Vì sao lấy session sau request login?

Spring Security có thể thay đổi session ID hoặc thay session cũ bằng một session mới tùy chiến lược. Vì thế, luôn lấy session hiện hành từ request đã xử lý:

~~~java
MockHttpSession afterLogin = (MockHttpSession)
        loginResult.getRequest().getSession(false);
~~~

Không tiếp tục dựa vào ID cũ hoặc tự giả định session trước và sau login là cùng một đối tượng. Việc so sánh object có ý nghĩa khác nhau theo chiến lược: **changeSessionId** giữ object, còn **migrateSession** và **newSession** tạo object session mới.

## 6. Kiểm thử các chiến lược khác

Có thể thay cấu hình trong SecurityFilterChain để kiểm chứng hành vi từng chiến lược. Mỗi lần chạy, chỉ bật một chiến lược trong context test.

### 6.1. migrateSession: session mới, thuộc tính được chuyển

Thay cấu hình bằng:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
    .sessionFixation(fixation -> fixation.migrateSession())
)
~~~

Các assertion trọng tâm sau login:

~~~java
assertThat(afterLogin).isNotNull();
assertThat(afterLogin).isNotSameAs(beforeLogin);
assertThat(afterLogin.getId()).isNotEqualTo(originalId);
assertThat(beforeLogin.isInvalid()).isTrue();
assertThat(afterLogin.getAttribute("cartId")).isEqualTo("CART-42");
~~~

Ở đây, session mới mang ID mới và giữ thuộc tính `cartId` do chiến lược migrate sao chép. Session cũ bị invalid. Sau đó, có thể gọi `GET /api/profile` bằng `afterLogin` để xác nhận Authentication vẫn được lưu và khôi phục.

### 6.2. newSession: session mới, không giữ thuộc tính ứng dụng cũ

Cấu hình:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
    .sessionFixation(fixation -> fixation.newSession())
)
~~~

Assertion tập trung:

~~~java
assertThat(afterLogin).isNotNull();
assertThat(afterLogin).isNotSameAs(beforeLogin);
assertThat(afterLogin.getId()).isNotEqualTo(originalId);
assertThat(beforeLogin.isInvalid()).isTrue();
assertThat(afterLogin.getAttribute("cartId")).isNull();
~~~

Không kiểm tra rằng mọi thuộc tính của session mới đều rỗng: Spring Security có thể lưu các thuộc tính bảo mật cần thiết vào session mới. Điều cần xác nhận ở đây là thuộc tính ứng dụng cũ như `cartId` không được chuyển tiếp. Vẫn cần kiểm tra request sau đăng nhập truy cập được endpoint bảo vệ.

### 6.3. none: session ID không đổi

Cấu hình minh họa:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
    .sessionFixation(fixation -> fixation.none())
)
~~~

Với chiến lược này, session cũ được giữ lại:

~~~java
assertThat(afterLogin).isSameAs(beforeLogin);
assertThat(afterLogin.getId()).isEqualTo(originalId);
assertThat(afterLogin.getAttribute("cartId")).isEqualTo("CART-42");
~~~

Đây là test mô tả hành vi của cấu hình không bảo vệ session fixation. Nó giúp nhận ra sự khác biệt giữa các chiến lược, **không phải khuyến nghị cấu hình production**.

### 6.4. Bảng tổng hợp kết quả cần kiểm tra

| Chiến lược | ID sau login | Đối tượng session | Thuộc tính ứng dụng cũ | Session cũ |
| --- | --- | --- | --- | --- |
| **changeSessionId** | Khác ID trước login | Cùng object | Được giữ | Vẫn là session hiện tại với ID mới |
| **migrateSession** | Khác ID trước login | Object mới | Được sao chép | Bị invalid |
| **newSession** | Khác ID trước login | Object mới | Không được sao chép | Bị invalid |
| **none** | Giữ ID cũ | Cùng object | Được giữ | Vẫn có hiệu lực |

Khi kiểm thử các chiến lược, không nên chỉ khẳng định ID thay đổi. Hãy kiểm tra thêm **object session**, **thuộc tính ứng dụng**, **SecurityContext** và **request sau xác thực**. Những assertion này cho biết chính sách đang chạy có đúng với nhu cầu lưu trạng thái hay không.

## 7. Các lỗi thường gặp khi kiểm thử session fixation

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ID trước và sau login giống nhau | Đang dùng chiến lược **none**, authentication không đi qua session strategy, hoặc test không có session trước login | Kiểm tra SecurityFilterChain và tạo session trước khi xác thực |
| Không lấy được session sau login | Login thất bại, filter không chạy, hoặc ứng dụng không lưu context vào session | Kiểm tra redirect, credentials, filter chain và repository |
| Thuộc tính giỏ hàng biến mất | Đang dùng **newSession** hoặc custom strategy không migrate thuộc tính | Chọn **changeSessionId** hoặc **migrateSession** nếu cần giữ dữ liệu |
| Session cũ invalid trong khi mong cùng object | Đang dùng **migrateSession** hoặc **newSession** | Kiểm tra chiến lược đang cấu hình |
| Test trả 403 ở POST /login | Thiếu CSRF token | Thêm **.with(csrf())** |
| Test trả 200 dù chưa đăng nhập | Security filters bị tắt hoặc test dùng **@WithMockUser** | Bật filter chain và dùng luồng login thực |
| Không thấy session ID đổi trong môi trường test | Mock request không mô phỏng đúng hành vi container cần kiểm tra, hoặc authentication tùy chỉnh bỏ qua session strategy | Kiểm tra loại MockMvc setup; bổ sung test tích hợp trên Servlet container |

### Custom authentication cần gọi session strategy

Các filter xác thực chuẩn của Spring Security đã tích hợp cơ chế quản lý session. Nhưng nếu ứng dụng tự viết controller hoặc service để gọi `AuthenticationManager.authenticate(...)`, sau đó tự gán Authentication vào SecurityContext, không nên mặc định rằng session fixation strategy sẽ tự chạy.

Luồng xác thực tùy chỉnh cần tích hợp đúng **SessionAuthenticationStrategy** theo cấu hình của ứng dụng, đồng thời lưu SecurityContext qua repository phù hợp. Nếu thiếu bước này, test login có thể trả thành công nhưng session ID không đổi hoặc request sau không nhận được Authentication. Thiết kế cụ thể phụ thuộc phiên bản Spring Security và cách ứng dụng tự quản lý quá trình xác thực.

## 8. Giới hạn của MockMvc và thực hành

**MockMvc** mô phỏng request/response trong ứng dụng Servlet, còn **MockHttpSession** mô phỏng session cho mục đích test. Nó giúp kiểm tra logic đổi ID và lưu thuộc tính theo chiến lược, nhưng không thay thế kiểm thử qua Servlet container thật.

Các hành vi cần xác minh bổ sung trong môi trường tích hợp nếu là yêu cầu của ứng dụng gồm:

- Cookie session mới được gửi về client trong response sau login.
- Client ngừng gửi cookie ID cũ và gửi cookie mới ở request kế tiếp.
- Container từ chối session ID cũ sau khi đã rotate hoặc invalidate.
- Session store phân tán, reverse proxy và cấu hình cookie hoạt động đúng khi triển khai nhiều instance.
- HTTPS, cookie **Secure**, **HttpOnly**, **SameSite** và chính sách thời gian sống được cấu hình phù hợp.

MockMvc với MockHttpSession không tự chứng minh các thuộc tính cookie hay hành vi mạng này. Để kiểm thử chúng, hãy chạy ứng dụng qua HTTP server thực và sử dụng client có khả năng lưu, gửi cookie.

Bài tập tự luyện:

1. Chạy test với **changeSessionId**. Ghi lại ID trước login và sau login; xác minh hai ID khác nhau nhưng thuộc tính `cartId` còn nguyên.
2. Chuyển sang **migrateSession**. Kiểm tra object session mới, session cũ invalid và `cartId` được sao chép.
3. Chuyển sang **newSession**. Kiểm tra `cartId` không còn, nhưng request sau login vẫn nhận được Authentication hợp lệ.
4. Thử **none** trong môi trường test riêng. Xác nhận ID giữ nguyên và giải thích rủi ro nếu dùng chiến lược này trong ứng dụng có xác thực bằng session.
5. Tự viết một luồng xác thực tùy chỉnh. Kiểm tra session fixation strategy có thực sự được gọi và SecurityContext có được lưu hay không.
6. Mở rộng test tích hợp để quan sát cookie session trong response login và cookie gửi lại trong request tiếp theo.

Một bài kiểm thử session fixation tốt phải tạo được **session trước xác thực**, chứng minh ID thay đổi sau đăng nhập theo chiến lược đã chọn, và kiểm tra trạng thái ứng dụng được giữ hoặc loại bỏ đúng chủ đích. Như vậy, test vừa xác minh khả năng chống fixation vừa bảo đảm trải nghiệm sử dụng session không bị phá vỡ ngoài ý muốn.
