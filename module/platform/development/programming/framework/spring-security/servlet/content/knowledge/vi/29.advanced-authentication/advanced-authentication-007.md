# Yêu cầu xác thực lại trước thao tác nhạy cảm hoặc sau một khoảng thời gian

## 1. Tình huống và mục tiêu bảo mật

Một người dùng đã đăng nhập vào ứng dụng Spring MVC có thể làm những việc ít rủi ro như xem hồ sơ, đọc thông báo hay tìm kiếm. Nhưng những thao tác sau có mức độ rủi ro khác:

- Thay đổi mật khẩu, địa chỉ email khôi phục, số điện thoại hoặc phương thức MFA.
- Xóa tài khoản, tải dữ liệu nhạy cảm hoặc xem thông tin thanh toán.
- Thêm tài khoản nhận tiền, thay đổi hạn mức, thực hiện chuyển tiền.
- Cấp quyền quản trị hoặc thay đổi cấu hình bảo mật của tổ chức.

Nếu chỉ kiểm tra **SecurityContext chứa một Authentication đã đăng nhập**, phiên đăng nhập được tạo nhiều giờ trước vẫn có thể thực hiện thao tác nhạy cảm. Người khác có thể đã sử dụng máy tính khi chủ tài khoản rời đi, session cookie có thể bị đánh cắp, hoặc người dùng đăng nhập bằng remember-me thay vì vừa chứng minh danh tính.

**Reauthentication (xác thực lại)** yêu cầu người dùng chứng minh danh tính thêm lần nữa, trước khi thực hiện hành động nhạy cảm hoặc sau một khoảng thời gian kể từ lần kiểm tra đủ tin cậy gần nhất. **Step-up authentication** là khái niệm rộng hơn: nâng mức đảm bảo xác thực, ví dụ xác nhận lại mật khẩu rồi thực hiện WebAuthn/passkey, MFA hoặc xác thực qua IdP với mức assurance phù hợp.

Ví dụ chính sách:

- Truy cập **GET /account**: chỉ cần phiên đăng nhập bình thường.
- Thực hiện **POST /account/security-settings**: phải vừa xác thực lại trong **5 phút** gần nhất.
- Khi đã quá 5 phút, phiên đăng nhập có thể tiếp tục được dùng cho trang thường nhưng endpoint nhạy cảm từ chối đến khi reauthentication thành công.
- Nếu nhập sai mật khẩu khi reauthentication, không tạo quyền tạm thời; tùy chính sách có thể hủy bằng chứng xác thực lại cũ.
- Với thao tác rủi ro rất cao, có thể cần **một lần xác nhận cho một giao dịch cụ thể** hoặc MFA chống phishing, thay vì dùng chung cửa sổ 5 phút.

Bài học dùng **Spring Boot 3.x, Spring Security 6.x, Servlet stack, Java 17+**, mô phỏng đăng nhập bằng **formLogin** và xác thực lại mật khẩu. OAuth2 Login/SSO, passkey và MFA cần cách kiểm chứng khác, được phân biệt rõ ở phần sau.

## 2. Những khái niệm dễ bị nhầm

| Cơ chế | Nó trả lời câu hỏi gì? | Có thay thế reauthentication không? |
| --- | --- | --- |
| **Authentication** | Ai đang gửi request? | Không: biết người dùng đã đăng nhập không cho biết lúc nào họ xác thực gần nhất |
| **Authorization** | Người này có quyền thực hiện thao tác không? | Không: phải kiểm tra quyền **và** độ mới của xác thực |
| **Session idle timeout** | Bao lâu không hoạt động thì session hết hạn? | Không: hoạt động liên tục có thể giữ session sống nhưng lần xác thực đầu đã rất cũ |
| **Session absolute timeout** | Session tối đa sống bao lâu từ lúc phát hành? | Không: giới hạn tuổi session, không tạo bằng chứng mới cho thao tác nhạy cảm |
| **Remember-me** | Có thể khôi phục đăng nhập từ cookie dài hạn không? | Không: remember-me thường không đạt yêu cầu “vừa chứng minh danh tính” |
| **CSRF protection** | Request thay đổi trạng thái có thực sự xuất phát từ luồng được phép của người dùng không? | Không: CSRF token không chứng minh người dùng vừa xác thực lại |
| **Reauthentication freshness** | Lần xác thực lại gần nhất diễn ra lúc nào, do ai thực hiện, bằng cách gì? | Đây là một thành phần của yêu cầu bảo mật |
| **MFA / step-up** | Lần xác thực có đạt mức đảm bảo cần thiết không? | Có thể bổ sung freshness, nhưng cần kiểm tra đủ yếu tố/assurance, không chỉ timestamp |

Spring Security expression **isFullyAuthenticated()** chỉ giúp phân biệt tình trạng anonymous/remember-me với xác thực đầy đủ theo ngữ nghĩa framework; **nó không tự áp đặt ngưỡng 5 phút**. Tương tự, **Authentication.isAuthenticated()** không cho biết thời điểm người dùng nhập lại mật khẩu.

Không tự suy luận thời gian xác thực từ **session.getCreationTime()**, lần truy cập gần nhất, hoặc thời điểm bearer JWT được tạo (**iat**). Những giá trị đó có ý nghĩa khác với **thời điểm hoàn tất một thử thách reauthentication**.

## 3. Thiết kế chính sách: bảo vệ tại security boundary

Mục tiêu là áp dụng reauthentication cho **mọi đường vào của thao tác nhạy cảm**, thay vì chỉ kiểm tra ở trang HTML. Với Spring Security Servlet, có thể đặt điều kiện trong **authorizeHttpRequests(...)**, dùng **AuthorizationManager<RequestAuthorizationContext>**. Khi điều kiện không đạt, request sẽ không đến controller.

~~~text
Người dùng đã có HttpSession + SecurityContext
                │
                ├── GET /account
                │       → authenticated → xem trang
                │
                ├── POST /account/security-settings
                │       → CSRF check
                │       → AuthorizationManager:
                │          - current authentication hợp lệ?
                │          - có bằng chứng reauth trong session?
                │          - bằng chứng thuộc chính username này?
                │          - timestamp chưa quá 5 phút?
                │       → đủ điều kiện → controller nhạy cảm
                │       → thiếu/quá hạn → 403 + yêu cầu xác thực lại
                │
                └── POST /account/reauth
                        → phải đang đăng nhập đầy đủ và có CSRF token
                        → kiểm tra lại mật khẩu qua AuthenticationManager
                        → thành công: ghi bằng chứng reauth ở phía server
                        → thất bại: không cấp bằng chứng
~~~

**Hai điều kiện độc lập cần đồng thời đúng:** (1) tài khoản có **quyền** thực hiện nghiệp vụ, và (2) người đang dùng session có bằng chứng xác thực **đủ mới và đủ mạnh**. Một người không có quyền admin không được phép sửa thiết lập admin dù vừa nhập đúng mật khẩu.

### Bằng chứng xác thực lại phải được quản lý thế nào?

Một giá trị như **RecentProof(username, verifiedAt)** đặt **trong HttpSession phía server** là đủ cho bài demo một nút reauthentication bằng mật khẩu:

- Lưu **username hoặc subject ổn định** để không cho tài khoản B sử dụng marker của tài khoản A.
- Lưu **Instant verifiedAt** do server tạo sau khi reauthentication thành công, không lấy timestamp từ form/browser.
- Khi kiểm tra, dùng đồng hồ phía server và khoảng **Duration.ofMinutes(5)**; không tin client gửi **reauth=true** hay **lastAuthenticatedAt**.
- Không ghi **mật khẩu, OTP, access token hoặc dữ liệu bí mật** vào session marker.
- Khi đăng xuất, invalidation session phải làm marker biến mất; khi đổi account, phải xóa marker và đối chiếu principal.
- Nếu ứng dụng chạy nhiều instance, session store/replication phải chia sẻ marker cùng security context. Nếu dùng stateless JWT hoặc không có HttpSession, phải thiết kế bằng chứng step-up riêng thay vì copy cách này.
- Nếu security incident đánh dấu một session đã bị chiếm đoạt, không chỉ chờ hết TTL; cần cơ chế hủy session/bằng chứng.

**Khoảng 5 phút là ví dụ chính sách**, không phải quy tắc có sẵn của Spring Security. Với chuyển tiền lớn hoặc đổi credential, một cửa sổ rộng có thể không đủ; cần ràng buộc proof với giao dịch, xác nhận lại mỗi lần, giới hạn số lần thử và dùng MFA thích hợp.

## 4. Ví dụ Spring Boot 3.x / Spring Security 6.x

Ví dụ có hai endpoint: **POST /account/reauth** kiểm tra lại mật khẩu và **POST /account/security-settings** là một thao tác nhạy cảm giả lập. Mặc định Spring Security tạo form login tại **/login** và bảo vệ POST bằng CSRF token. Mọi đường dẫn ví dụ đều thuộc cùng ứng dụng Servlet.

Tại một dự án Spring Boot 3.x đã có Gradle wrapper:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tệp **src/main/java/com/example/reauth/ReauthApplication.java**:

~~~java
package com.example.reauth;

import java.io.Serial;
import java.io.Serializable;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.authentication.AuthenticationException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ReauthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReauthApplication.class, args);
    }
}

// Bằng chứng do server phát hành. Không chứa mật khẩu hay OTP.
record RecentProof(String username, Instant verifiedAt)
        implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;
}

final class ReauthPolicy {
    private ReauthPolicy() {}

    static final String SESSION_KEY =
            ReauthPolicy.class.getName() + ".RECENT_PROOF";
    static final Duration FRESH_FOR = Duration.ofMinutes(5);

    static boolean isFresh(
            HttpServletRequest request,
            Authentication current,
            Clock clock) {

        if (current == null ||
                !current.isAuthenticated() ||
                current instanceof AnonymousAuthenticationToken ||
                current instanceof RememberMeAuthenticationToken) {
            return false;
        }

        HttpSession session = request.getSession(false);
        if (session == null) {
            return false;
        }

        Object value = session.getAttribute(SESSION_KEY);
        if (!(value instanceof RecentProof proof)) {
            return false;
        }

        Instant now = clock.instant();
        return proof.username().equals(current.getName()) &&
                !proof.verifiedAt().isAfter(now) &&
                now.isBefore(proof.verifiedAt().plus(FRESH_FOR));
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Demo local only; không dùng username/password này ở production.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-only-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("another-demo-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration configuration) throws Exception {
        return configuration.getAuthenticationManager();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> recentPasswordCheck(
            Clock clock) {
        return (authentication, context) ->
                new AuthorizationDecision(
                        ReauthPolicy.isFresh(
                                context.getRequest(),
                                authentication.get(),
                                clock));
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext>
                    recentPasswordCheck) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        // Một lớp authorization độc lập trước controller:
                        .requestMatchers(HttpMethod.POST,
                                "/account/security-settings")
                                .access(recentPasswordCheck)
                        .requestMatchers(HttpMethod.POST,
                                "/account/reauth")
                                .fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}

@RestController
class AccountController {
    private final AuthenticationManager authenticationManager;
    private final Clock clock;

    AccountController(
            AuthenticationManager authenticationManager,
            Clock clock) {
        this.authenticationManager = authenticationManager;
        this.clock = clock;
    }

    @GetMapping("/")
    String home() {
        return "Sign in, then POST /account/reauth before sensitive POST";
    }

    @GetMapping("/account")
    String account(Authentication current) {
        return "account=" + current.getName();
    }

    @PostMapping("/account/reauth")
    ResponseEntity<Void> reauthenticate(
            @RequestParam("password") String password,
            Authentication current,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        // Mỗi lần thử lại đều xóa proof cũ; thất bại không được kế thừa.
        session.removeAttribute(ReauthPolicy.SESSION_KEY);

        try {
            Authentication verified =
                    authenticationManager.authenticate(
                            UsernamePasswordAuthenticationToken
                                    .unauthenticated(
                                            current.getName(), password));

            if (!verified.isAuthenticated() ||
                    !verified.getName().equals(current.getName())) {
                throw new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED,
                        "Reauthentication failed");
            }

            session.setAttribute(
                    ReauthPolicy.SESSION_KEY,
                    new RecentProof(current.getName(), clock.instant()));

            return ResponseEntity.noContent().build();
        } catch (AuthenticationException exception) {
            // Không trả về chi tiết "username không tồn tại" hay "sai mật khẩu".
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "Reauthentication failed");
        }
    }

    @PostMapping("/account/security-settings")
    String updateSensitiveSettings() {
        // Demo: nơi triển khai thật phải kiểm tra thêm quyền nghiệp vụ,
        // validate dữ liệu, audit và lưu thay đổi bằng service.
        return "sensitive action accepted";
    }
}
~~~

### Cơ chế trong mã

1. **AuthorizationManager** kiểm tra marker trong server-side session trước khi controller của thao tác nhạy cảm được gọi. Nếu marker không có, thuộc user khác hoặc quá **5 phút**, **AuthorizationDecision(false)**. Người dùng vẫn có thể truy cập tài nguyên thông thường.
2. **POST /account/reauth** chỉ được gọi từ phiên **fullyAuthenticated**, nên remember-me đơn thuần không đủ. Password được kiểm tra bằng **AuthenticationManager**, đi qua cơ chế mật khẩu/provider đã cấu hình, thay vì so sánh chuỗi hoặc kiểm tra một giá trị do trình duyệt gửi.
3. Chỉ sau khi password chính xác và username khớp session đang sử dụng, server mới ghi **RecentProof(username, Instant.now(...))**. Không cập nhật marker ở một request GET, khi refresh trang, hay khi người dùng chỉ bấm nút “Tôi xác nhận”.
4. Từ chối reauthentication xóa proof cũ. Đây là lựa chọn *fail closed* của demo; một ứng dụng thực có thể yêu cầu reauthentication lại hoặc khóa thử tạm thời sau quá nhiều lần sai.
5. **CSRF vẫn bật.** POST nhập mật khẩu và POST thay đổi thiết lập đều cần CSRF token hợp lệ. Nếu có form HTML, sử dụng cách tích hợp token của Spring Security/Thymeleaf hoặc đọc token được cung cấp an toàn; **không** tắt CSRF để khiến form hoạt động.
6. **Logout** làm session không còn hợp lệ; marker không còn giá trị. **Username được ràng buộc với marker** để tránh dùng proof của tài khoản khác trong cùng session. Với ứng dụng nhiều instance, cần bảo đảm session replication đúng nếu sử dụng session store.
7. Endpoint nhạy cảm trong demo chỉ trả body minh họa, **không thực sự sửa dữ liệu**. Trong ứng dụng thật, service phải áp dụng kiểm tra quyền đối tượng (object-level authorization), audit, giao dịch và idempotency phù hợp.

**Quan trọng:** Cơ chế này là **reauthentication bằng mật khẩu**, không phải MFA. Nó chưa đáp ứng các yêu cầu như phishing-resistant MFA, xác nhận chữ ký giao dịch hoặc risk-based authentication. Một phiên vừa được reauthentication vẫn có thể bị chiếm đoạt; proof thời gian chỉ giới hạn cửa sổ, không loại bỏ hoàn toàn rủi ro.

### Thay đổi vai trò, account và session

- **Không dùng marker chỉ có boolean true.** Boolean có thể sống không giới hạn, không gắn account và không biểu thị mức độ assurance.
- **Đăng nhập một tài khoản khác:** ứng dụng phải xóa trạng thái step-up trên login/switch-user thành công, không chỉ dựa vào username. Việc ràng buộc username là lớp bảo vệ bổ sung, không thay cho vòng đời session.
- **Session fixation:** Spring Security thường thay session identifier khi đăng nhập bằng formLogin. Không vô hiệu hóa các biện pháp session fixation mặc định vì muốn giữ marker.
- **Đổi mật khẩu hoặc thiết lập MFA:** sau khi đổi, có thể yêu cầu logout các session khác, thu hồi refresh token, hủy các proof step-up đã cấp. Việc xóa marker trong một session không tự thu hồi phiên ở thiết bị khác.
- **Kiểm tra quyền:** ví dụ chỉ có ROLE_USER, nhưng một endpoint thực tế dành cho admin còn cần kiểm tra **hasRole("ADMIN")** hoặc policy tương ứng cùng freshness, không thay role check bằng timestamp.

## 5. Kiểm thử bằng MockMvc

Trong thử nghiệm, **spring-security-test** có request post-processor **user(...)** để mô phỏng một request đã đăng nhập mà không phải thao tác giao diện form login. Tuy nhiên **POST /account/reauth** vẫn gọi **AuthenticationManager thật** và xác thực password của tài khoản demo. Cách test này kiểm tra được freshness và password recheck, nhưng **chưa phải integration test hoàn chỉnh** cho login form/remember-me/SSO của production.

Tệp **src/test/java/com/example/reauth/ReauthenticationTest.java**:

~~~java
package com.example.reauth;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReauthenticationTest {
    @Autowired
    MockMvc mvc;

    private static MockHttpSession session() {
        return new MockHttpSession();
    }

    @Test
    void sensitiveActionWithoutProofIsForbidden() throws Exception {
        mvc.perform(post("/account/security-settings")
                        .session(session())
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void correctPasswordCreatesFreshProof() throws Exception {
        MockHttpSession session = session();

        mvc.perform(post("/account/reauth")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("password", "demo-only-password"))
                .andExpect(status().isNoContent());

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("sensitive action accepted"));
    }

    @Test
    void wrongPasswordDoesNotCreateFreshProof() throws Exception {
        MockHttpSession session = session();

        mvc.perform(post("/account/reauth")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("password", "incorrect-password"))
                .andExpect(status().isUnauthorized());

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void expiredProofIsForbidden() throws Exception {
        MockHttpSession session = session();
        session.setAttribute(
                ReauthPolicy.SESSION_KEY,
                new RecentProof(
                        "alice", Instant.now().minus(Duration.ofMinutes(10))));

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void proofCannotBeReusedByAnotherAccount() throws Exception {
        MockHttpSession session = session();
        session.setAttribute(
                ReauthPolicy.SESSION_KEY,
                new RecentProof("alice", Instant.now()));

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("bob").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void failedRetryRemovesPreviousProof() throws Exception {
        MockHttpSession session = session();
        session.setAttribute(
                ReauthPolicy.SESSION_KEY,
                new RecentProof("alice", Instant.now()));

        mvc.perform(post("/account/reauth")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("password", "incorrect-password"))
                .andExpect(status().isUnauthorized());

        mvc.perform(post("/account/security-settings")
                        .session(session)
                        .with(user("alice").roles("USER"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void csrfIsStillRequiredForReauthentication() throws Exception {
        mvc.perform(post("/account/reauth")
                        .session(session())
                        .with(user("alice").roles("USER"))
                        .param("password", "demo-only-password"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy từ gốc dự án Spring Boot có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.reauth.ReauthenticationTest
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests com.example.reauth.ReauthenticationTest
~~~

Kết quả **dự kiến khi mã mẫu được đặt trong dự án Boot 3.x tương thích**: 7 test đạt. Thiếu proof, proof quá hạn, proof thuộc account khác hoặc thiếu CSRF nhận **403**; password sai nhận **401**; password đúng cho phép ghi proof và thực hiện request nhạy cảm (**204** rồi **200**). Đây là kỳ vọng của cấu hình demo, **không phải kết quả thực thi đã được xác nhận**.

**Không test bằng cách gửi trực tiếp một cookie giả hoặc một boolean** do client điều khiển. Trong bài test trên, thuộc tính HttpSession do server-side mock lưu, và controller reauthentication thật sự kiểm tra mật khẩu.

### Kiểm thử thêm trong hệ thống thật

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Tạo session bằng login form thật | Login đổi session ID theo chính sách và không vô tình giữ proof từ user cũ |
| Đăng xuất rồi sử dụng lại cookie | Marker không còn hiệu lực; nhạy cảm không thể tiếp tục được phép |
| Reauthenticate lúc t=0, thao tác lúc t=4 phút | Được phép nếu đủ quyền |
| Reauthenticate lúc t=0, thao tác lúc t=6 phút | Bị từ chối nhưng phiên dùng trang thường vẫn còn |
| Tài khoản không có quyền nghiệp vụ | Vẫn 403 dù proof còn mới |
| Session đã hết hạn/đổi phiên | Không dùng lại proof của session trước |
| Đồng thời nhiều tab và nhiều request | Không tạo race condition khiến quá hạn hoặc proof dùng một lần bị dùng nhiều lần |
| Cluster nhiều instance | Proof chỉ có hiệu lực đúng theo session chung, không sống trong biến static của một JVM |
| Brute-force mật khẩu trên endpoint reauth | Giới hạn thử, phát hiện bất thường, audit và chặn theo chính sách |
| Remember-me/SSO | Không gắn proof nếu chưa xác minh lại bằng phương thức thật |
| Thao tác nguy cơ cao | Bằng chứng có được gắn với đối tượng/giao dịch và chỉ được dùng đúng hành động không? |

Với bài test thời gian, dùng **Clock cố định hoặc Clock có thể điều khiển** để kiểm tra chính xác ngưỡng 4 phút 59 giây / 5 phút thay vì Thread.sleep hoặc test sát giờ thật. Ví dụ dùng Clock.systemUTC để chạy đơn giản, nên test quá hạn đã đặt dấu thời gian cách ngưỡng nhiều phút để tránh lỗi flakiness.

## 6. Dùng step-up với OAuth2 Login / OpenID Connect / MFA

Ứng dụng đăng nhập thông qua IdP không nhất thiết biết mật khẩu của người dùng. **Không yêu cầu lưu lại hoặc gửi mật khẩu IdP đến resource application để tự kiểm tra**. Thay vào đó, thực hiện flow xác thực lại tại IdP bằng các tham số và chính sách mà IdP hỗ trợ.

Các khái niệm cần phân biệt:

- **prompt=login** trong OIDC có thể yêu cầu IdP thực hiện đăng nhập tương tác lại, nhưng ứng dụng phải xác minh kết quả và chính sách assurance; không tự coi URL redirect là bằng chứng.
- **max_age** yêu cầu giới hạn tuổi xác thực ở IdP. Theo OIDC, khi max_age được yêu cầu, ID Token cần cung cấp **auth_time** để RP kiểm tra thời gian xác thực.
- **auth_time** phản ánh thời điểm xác thực người dùng theo tuyên bố của IdP; không đồng nghĩa với **iat** của ID Token, và không phải lúc ứng dụng vừa nhận callback.
- **acr** biểu thị Authentication Context Class Reference (mức assurance tùy profile IdP); **amr** mô tả các phương thức xác thực theo IdP. Ý nghĩa các giá trị phải nằm trong hợp đồng giữa ứng dụng và IdP, không tự gán rằng acr nào cũng là MFA.
- **WebAuthn/passkey**, TOTP, push challenge hoặc xác thực lại bằng mật khẩu có mức chống phishing và chống replay khác nhau. Với thao tác tài chính nhạy cảm, cân nhắc authenticator chống phishing và xác nhận nội dung giao dịch.
- **session freshness** ở app và **auth_time tại IdP** là hai tầng khác nhau. RP phải ràng buộc kết quả step-up với đúng user/session và tránh reuse ngoài thời hạn.

Luồng tham khảo:

~~~text
User đã login tại app
    │
    ├─ Yêu cầu sửa thông tin nhạy cảm
    ▼
App nhận thấy chưa có proof mới/đủ assurance
    │
    ▼
Redirect tới IdP với yêu cầu step-up được hỗ trợ
    │  (ví dụ max_age hoặc acr_values theo hợp đồng)
    ▼
IdP xác thực lại / thực hiện yếu tố bổ sung
    │
    ▼
Callback OAuth2/OIDC: app xác minh state/nonce, ID Token,
iss/aud/signature, auth_time và acr/amr thích hợp
    │
    ▼
App lưu server-side proof (subject, time, assurance, purpose)
    │
    ▼
Security authorization cho phép hành động đúng phạm vi
~~~

Với Spring Security OAuth2 Login trên Servlet, các yêu cầu OIDC bổ sung thường được tích hợp bằng cơ chế cấu hình hoặc tùy chỉnh **OAuth2AuthorizationRequestResolver** cùng xử lý kết quả login. Điều kiện tối quan trọng không phải nút “login lại” mà là **xác minh bằng chứng IdP trả về**; cơ chế cụ thể phụ thuộc Spring Security version và IdP.

**Không dùng session refresh của ứng dụng như bằng chứng step-up.** IdP có thể trả người dùng về ngay vì vẫn còn SSO session; nếu policy bắt buộc chứng minh danh tính gần đây, phải yêu cầu và xác minh đúng **auth_time**, assurance/method hoặc challenge bổ sung.

## 7. An toàn UX và vận hành

### 7.1. UX khi freshness đã hết hạn

Khi người dùng truy cập endpoint nhạy cảm lúc proof hết hạn:

1. **Không thực hiện nghiệp vụ** rồi mới yêu cầu nhập mật khẩu.
2. Với REST endpoint, trả **403** cùng mã lỗi nghiệp vụ như **reauthentication_required** theo hợp đồng API; với web MVC, có thể dẫn người dùng tới trang step-up nội bộ.
3. Không biến tất cả lỗi 403 thành “cần nhập lại mật khẩu”: có thể người dùng **không có quyền**, nên reauthentication cũng không giải quyết được.
4. Sau khi thành công, kiểm tra lại quyền và tính hợp lệ của request nhạy cảm, không “duyệt luôn” thao tác cũ mà không có xác nhận.
5. Nếu lưu địa chỉ quay lại, chỉ chấp nhận **relative path an toàn** hoặc allowlist đích; không dùng URL ngoài tùy ý gây **open redirect**.
6. Khi người dùng đổi tài khoản hoặc logout trong tab khác, xóa/không sử dụng proof cũ.

### 7.2. Các rủi ro còn lại

| Rủi ro | Biện pháp |
| --- | --- |
| Session bị lấy cắp **sau** khi reauthentication | TTL ngắn, session binding, detection, yêu cầu xác nhận cho giao dịch quan trọng |
| Password bị đoán qua endpoint reauth | Rate limit, throttle, audit, cảnh báo và MFA; không lộ lý do thất bại chi tiết |
| XSS làm phát request trong session đã step-up | CSP, encode output, kiểm soát scripts, giảm thời hạn và xác nhận giao dịch |
| CSRF khi người dùng đăng nhập bằng cookie | Giữ CSRF protection; step-up không loại bỏ CSRF |
| Proof tồn tại sau login/switch-account | Xóa proof trên login success, logout, đổi account và thay đổi credential |
| Thao tác admin thiếu kiểm tra role | Kết hợp authorization role/object với freshness |
| Cluster lưu session không nhất quán | Shared session store và kiểm thử request qua nhiều node |
| Đồng hồ lệch | Dùng UTC, NTP, Clock có thể test; không dùng giờ client |
| Người dùng nhập lại password vào trang phishing | HTTPS, UI đáng tin, passkey/WebAuthn hoặc step-up ở IdP khi phù hợp |
| Giao dịch yêu cầu “một lần duy nhất” | Proof ràng buộc purpose/transaction, nonce, TTL nhỏ, tiêu thụ atomically và idempotency |
| Lưu proof ở localStorage hoặc cookie client sửa được | Lưu trạng thái phía server hoặc dùng bằng chứng được ký/xác minh đúng; không tin boolean phía client |

### 7.3. Khi nào cần yêu cầu lại ngay cả trước 5 phút?

Khoảng thời gian là một yếu tố, không phải yếu tố duy nhất. Hệ thống có thể buộc reauthentication mới khi:

- Người dùng thực hiện thay đổi có ảnh hưởng trực tiếp tới khôi phục tài khoản hoặc phương thức MFA.
- Thiết bị, IP, vị trí hoặc hành vi bất thường được hệ thống đánh giá bằng risk engine đáng tin; tránh khóa nhầm chỉ vì một tín hiệu đơn lẻ.
- Tài khoản vừa bị thay đổi mật khẩu, thu hồi phiên, phát hiện credential compromise hoặc chuyển trạng thái rủi ro.
- Một giao dịch cần người dùng xác nhận **số tiền, người nhận hoặc đối tượng cụ thể**, không chỉ nhập mật khẩu trong cùng một cửa sổ ngắn.
- Chính sách tuân thủ yêu cầu loại authenticator hoặc mức đảm bảo cụ thể.

Lưu ý: IP hoặc user-agent không phải yếu tố xác thực độc lập đáng tin để “chứng minh” người dùng; chỉ dùng làm tín hiệu bổ sung có cân nhắc trải nghiệm và quyền riêng tư.

## 8. Những lỗi phổ biến cần tránh

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Chỉ gọi **authenticated()** ở URL nhạy cảm | Session đã login nhiều giờ trước vẫn được chấp nhận | Thêm kiểm tra thời điểm và mức xác thực |
| Chỉ dùng **isFullyAuthenticated()** | Không có giới hạn thời gian từ lần xác thực trước | Kết hợp freshness check |
| Tự nhận **lastLoginTime** từ trình duyệt | Người dùng có thể sửa request | Tạo proof phía server khi xác thực thật thành công |
| Đặt **boolean reauthenticated=true** trong session | Có thể tồn tại quá lâu và không gắn thời gian/user | Proof có principal, timestamp, assurance và TTL |
| Dùng mã PIN/OTP demo không có rate limit | Có thể brute-force hoặc replay | Giới hạn số lần thử, TTL, single-use và giám sát |
| Chỉ kiểm tra ở controller của web form | API khác có thể gọi nghiệp vụ trực tiếp | Dùng security boundary và service authorization ở mọi điểm vào |
| Tắt CSRF vì đã có reauth | Cookie session vẫn có nguy cơ CSRF | Giữ CSRF cho unsafe methods |
| Đăng nhập lại bằng IdP nhưng không xét **auth_time** | SSO có thể bỏ qua challenge và quay về tức thì | Yêu cầu/verifiy OIDC freshness và assurance |
| Dùng **iat** của JWT thay auth_time | Token mới không chứng minh người dùng vừa nhập credential | Sử dụng claim/tín hiệu reauth đáng tin |
| Cấp proof cho user A rồi dùng ở user B | Marker không ràng buộc danh tính | Ràng buộc proof với principal, session, mục đích |
| Coi proof mới là được mọi quyền | Freshness không thay thế RBAC/ABAC | Kiểm tra cả role, resource ownership và policy |
| Chỉ test happy path nhập đúng password | Không phát hiện thiếu CSRF, hết hạn hoặc replay | Test âm và test đúng thời gian/identity |

## 9. Checklist hoàn thiện trước production

- Định nghĩa cụ thể **đường dẫn/hành động** nào yêu cầu reauthentication, role nào được làm và mức rủi ro của từng hành động.
- Định nghĩa **freshness window** (ví dụ 5 phút) và liệu proof được dùng cho nhiều thao tác hay chỉ một giao dịch.
- Chọn **phương thức reauthentication** phù hợp: password qua provider, OIDC auth_time/acr, MFA, WebAuthn. Không cố xin password khi ứng dụng chỉ là OAuth2 Client của IdP.
- Ghi proof **chỉ sau kiểm chứng thành công**; lưu với session/user/time/purpose; xóa khi logout, chuyển account, thay đổi credential hoặc gặp sự cố bảo mật.
- Áp điều kiện ở **Spring Security authorization boundary** và kiểm tra quyền nghiệp vụ tại service. Không chỉ ẩn nút hay hiện popup ở frontend.
- Đảm bảo **CSRF**, session fixation protection, cookie HttpOnly/Secure/SameSite và session expiration vẫn hoạt động đúng.
- Kiểm thử timeout bằng **Clock có thể điều khiển**, wrong password, remember-me, user switch, session invalidation, concurrent requests, thiếu quyền và các endpoint khác cùng gọi nghiệp vụ.
- Giới hạn brute force, audit các sự kiện step-up thành công/thất bại và không ghi plaintext password/OTP trong log.
- Với giao dịch cực kỳ nhạy cảm, thêm confirmation gắn **transaction-specific nonce**, hạn dùng rất ngắn, one-time và chống replay.
- Khi triển khai nhiều node hoặc qua IdP, xác minh consistency của session/proof và đúng mức assurance từ authentication event, không dựa vào timestamp máy người dùng.

**Kết luận:** “Đã đăng nhập” và “vừa chứng minh danh tính đủ mạnh” là hai điều kiện khác nhau. Spring Security cho phép áp policy kiểm tra lại ngay tại **AuthorizationManager** và thực hiện password check qua **AuthenticationManager**; với OAuth2/OIDC phải dựa vào bằng chứng step-up đáng tin từ IdP. Cách thiết kế tốt là kiểm tra đúng người, đúng thời điểm, đúng mức assurance, đúng nghiệp vụ — đồng thời vẫn duy trì authorization, CSRF và bảo vệ session.
