# Đổi mật khẩu, xác thực lại và vô hiệu hóa những phiên liên quan trong Spring Security Servlet

**Phạm vi:** Java 17+, Spring Security 6.x / Spring Boot 3.x trên Jakarta Servlet. Bài thuộc nhóm **Mật khẩu**. Mục tiêu là thiết kế luồng đổi mật khẩu an toàn; xác minh lại người dùng trước thao tác nhạy cảm; cập nhật password hash đúng cách; thu hồi những phiên đã xác thực và credential liên quan; kiểm thử được kết quả.

Tình huống: một tài khoản đang đăng nhập trên trình duyệt A, B và điện thoại C. Tại A, người dùng đổi mật khẩu. Mật khẩu cũ không còn dùng được để **đăng nhập mới**, nhưng B và C có thể tiếp tục hoạt động nếu server chỉ đổi hash trong database. Lý do: mỗi phiên có thể đã giữ một <code>Authentication</code> hợp lệ trong <code>SecurityContext</code> và không tự kiểm tra lại password ở mỗi request.

## 1. Ba công việc phải hoàn thành độc lập

1. **Re-authentication / step-up:** chứng minh lại người yêu cầu là chủ tài khoản hoặc người có quyền đổi credential. Với mật khẩu nội bộ, thường phải kiểm tra current password; với SSO/IdP dùng cơ chế xác thực lại/MFA thích hợp.
2. **Cập nhật credential:** kiểm tra mật khẩu mới, băm bằng <code>PasswordEncoder</code>, ghi bền vững và nhất quán, không lưu plaintext; đồng thời tăng phiên bản credential hoặc ghi thời điểm đổi khi hệ thống cần thu hồi.
3. **Vô hiệu hóa quyền truy cập đang tồn tại:** hủy phiên hiện tại, đánh dấu/xóa các phiên khác, thu hồi remember-me token, refresh token, hoặc thiết lập chính sách token đã phát hành nếu ứng dụng dùng chúng.

Không được xem các thao tác sau là tương đương:

| Thao tác | Tác dụng | Không tự thực hiện |
| --- | --- | --- |
| <code>PasswordEncoder.encode(newPassword)</code> | Sinh password hash mới | Không hủy session hoặc JWT |
| Cập nhật <code>password_hash</code> trong database | Đổi credential cho lần xác thực tiếp theo | Không xóa SecurityContext đã lưu |
| <code>SecurityContextHolder.clearContext()</code> | Xóa authentication ở context hiện tại | Không tìm và hủy session trên thiết bị khác |
| <code>request.getSession(false).invalidate()</code> | Hủy một HttpSession của request hiện tại | Không duyệt tất cả session của account |
| <code>SessionInformation.expireNow()</code> | Đánh dấu phiên do SessionRegistry theo dõi là expired | Không xóa cookie trên thiết bị từ xa hay đồng bộ nhiều node |
| Xóa cookie <code>JSESSIONID</code> ở browser A | Browser A không gửi lại cookie đó | Không hủy session trên server hoặc ở browser B |

**Mục tiêu an toàn:** người dùng phải đăng nhập lại bằng credential mới sau khi đổi; mọi phiên cũ nằm trong phạm vi chính sách thu hồi không còn có thể thực hiện các hành động được bảo vệ. “Hủy session” có thể được thực thi tức thời ở kho session hoặc bị phát hiện ở **request tiếp theo**; phải mô tả chính xác semantics của kiến trúc.

## 2. Đổi mật khẩu, quên mật khẩu và admin reset không phải một luồng

| Loại thao tác | Bằng chứng danh tính | Quy tắc quan trọng |
| --- | --- | --- |
| Người đang đăng nhập tự đổi mật khẩu | Session đã xác thực **và** current password/step-up phù hợp | Chỉ đổi mật khẩu của chính tài khoản server đã xác thực |
| Quên mật khẩu (password reset) | Token recovery dùng một lần, TTL ngắn, gắn tài khoản và mục đích | Không đòi current password; token bị vô hiệu sau sử dụng |
| Admin hỗ trợ reset | Authentication và authorization riêng của admin, audit | Không để client tự đặt <code>userId</code> nhằm vượt quyền; cân nhắc buộc đặt mật khẩu mới |
| Đổi mật khẩu tại Identity Provider | Re-authentication/MFA theo IdP | Ứng dụng không sở hữu hash thì không tự xử lý password nội bộ |

Reset token cần được lưu dưới dạng hash hoặc được bảo vệ tương đương, ngẫu nhiên khó đoán, một lần dùng và bị thu hồi nếu hết hạn/đã sử dụng. Không gửi password mới hoặc token vĩnh viễn qua email. Nếu hỗ trợ SSO, cần kiểm tra chính sách revocation của Identity Provider, ứng dụng và mọi refresh token riêng.

## 3. Luồng HTTP của thao tác tự đổi mật khẩu

~~~text
Browser A                         Spring Security / ứng dụng
  | POST /password/change                    |
  | Cookie: JSESSIONID=... + CSRF token       |
  | currentPassword, newPassword             |
  |----------------------------------------->|
  |                             CSRF được kiểm tra
  |                             Đã authentication?
  |                             Load account theo principal server
  |                             matches(currentPassword, hash)?
  |                             Validate chính sách mật khẩu mới
  |                             Encode và cập nhật hash/phiên bản
  |                             Thu hồi các phiên/token cũ
  |                             Logout + hủy session hiện tại
  |<-----------------------------------------|
  | 200 + yêu cầu đăng nhập lại               |
  |                                           |
Browser B gửi request với session trước đó
  |----------------------------------------->|
  |                             Session bị expire/revoke?
  |<-----------------------------------------|
  | Redirect login hoặc response từ chối      |
~~~

Một phiên đã đăng nhập không phải bằng chứng đủ mạnh cho **mọi** thao tác nhạy cảm: nó có thể bị chiếm quyền hoặc một request có thể bị CSRF. Kiểm tra current password (hoặc step-up đã được IdP xác nhận gần đây), bật CSRF với ứng dụng dựa vào cookie/session, và yêu cầu HTTPS.

Dữ liệu password chỉ được gửi trong body qua kênh an toàn. Không để trong query string, log HTTP, analytics, message queue không được bảo vệ hoặc email. Không lộ lý do quá chi tiết cho người không đủ quyền; vẫn ghi audit ở server theo quy tắc bảo vệ dữ liệu.

**Re-authentication khác authentication thông thường:** yêu cầu có session hiện tại cho phép bắt đầu flow, còn bước kiểm tra current password hoặc MFA chứng minh lại người dùng trước khi thay credential. Không chấp nhận flag tự khai như <code>confirmed=true</code> từ trình duyệt.

## 4. Băm mật khẩu và chính sách thay đổi

Spring Security dùng <code>PasswordEncoder</code>:

~~~java
// Trích đoạn logic trong service, không phải chương trình độc lập.
if (!passwordEncoder.matches(currentPassword, currentHash)) {
    throw new IllegalArgumentException("Current password not accepted");
}
if (passwordEncoder.matches(newPassword, currentHash)) {
    throw new IllegalArgumentException("Choose a different password");
}
String newHash = passwordEncoder.encode(newPassword);
repository.updatePasswordHash(accountId, newHash);
~~~

Các điểm quan trọng:
- <code>matches(raw, encoded)</code> xác minh raw password bằng hash, không giải mã hash. Password hash đúng chuẩn là một chiều.
- Hash password nên được tạo bởi thuật toán dành cho password như BCrypt/Argon2/PBKDF2 với cấu hình chi phí thích hợp; không dùng SHA-256 đơn thuần để lưu password.
- <code>PasswordEncoderFactories.createDelegatingPasswordEncoder()</code> giúp lưu định danh thuật toán như <code>{bcrypt}</code>; đừng làm mất prefix khi lưu database.
- Hash có salt nên hai lần <code>encode</code> cùng mật khẩu có thể khác nhau; không so sánh hash cũ với hash mới để kết luận password trùng.
- Policy có thể bao gồm độ dài, passphrase, kiểm tra mật khẩu dễ đoán/bị lộ, lịch sử mật khẩu và hỗ trợ password manager; demo chỉ dùng độ dài tối thiểu để tập trung vào session.
- Không dùng client-side validation làm lớp kiểm tra duy nhất; server phải kiểm tra. Rate limit cho bước nhập sai current password, phát hiện thay đổi bất thường và cơ chế thông báo an toàn là những yêu cầu sản phẩm thường có.

**Đồng thời và transaction:** hai yêu cầu thay mật khẩu gần như cùng lúc có thể cùng so khớp hash cũ rồi lần lượt ghi đè nhau. Production nên dùng giao dịch database, khóa bản ghi hoặc optimistic version; chỉ phát sự kiện/ghi trạng thái thu hồi sau khi commit credential thành công. Nếu bước thu hồi session gặp lỗi sau khi hash đã đổi, cần có chiến lược retry đáng tin hoặc cơ chế từ chối session dựa vào credential version.

## 5. Vòng đời session và những giới hạn của Servlet

Session cookie <code>JSESSIONID</code> thường chỉ mang session ID; <code>HttpSession</code> và <code>SecurityContext</code> được server quản lý. Cần phân biệt:

- <code>logout</code> trong request hiện tại thường gọi <code>SecurityContextLogoutHandler</code>, xóa SecurityContext và invalidate HttpSession hiện tại theo cấu hình mặc định.
- <code>SessionRegistry</code> có thể liệt kê session theo principal nếu session được đăng ký đúng. <code>SessionInformation.expireNow()</code> đánh dấu expired; <code>ConcurrentSessionFilter</code> kiểm tra trong request kế tiếp.
- <code>HttpSessionEventPublisher</code> chuyển sự kiện session lifecycle từ container để registry cập nhật trạng thái đăng ký.
- Một <code>SessionRegistryImpl</code> chỉ giữ dữ liệu **trong một JVM** và không tự thu hồi phiên của các replica khác, một session chưa đăng ký, hay JWT stateless.

Ví dụ trích đoạn:

~~~java
for (SessionInformation info
        : sessionRegistry.getAllSessions(authentication.getPrincipal(), false)) {
    info.expireNow();
}
// Sau đó logout/invalidate session hiện tại.
~~~

Đoạn trên chỉ có ý nghĩa khi cấu hình session concurrency/tracking phù hợp. Spring Security không “mặc định” cung cấp một hệ thống logout everywhere cho mọi loại xác thực.

Nếu muốn giữ session hiện tại, cần thiết kế một luồng riêng và chứng minh session này đã được step-up đủ mạnh, rotate session ID khi cần; **không** được giả định chỉ vì thao tác chạy ở máy A thì phiên A an toàn hơn mọi phiên khác. Ví dụ bên dưới chọn **logout tất cả, bao gồm máy đổi mật khẩu**.

## 6. Ví dụ đầy đủ chạy trong một JVM: form login + SessionRegistry

Demo sử dụng **Java 17+, Maven, Spring Boot 3.3.5, Spring Security 6.x**. Mật khẩu được lưu trong <code>InMemoryUserDetailsManager</code> để chạy độc lập. Form login tạo session; concurrency support đăng ký session; khi đổi mật khẩu, server đánh dấu toàn bộ session của người dùng đã expired rồi hủy session hiện tại. Khi session khác gửi request tiếp theo, nó được redirect về login.

**Hạn chế có chủ đích:** đây là ví dụ học tập trong một tiến trình, không phải giải pháp production với database/Redis, SSO hoặc JWT. Mật khẩu mẫu chỉ dùng để chạy localhost.

Cấu trúc dự án:

~~~text
password-sessions-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/passwordsessions/
    │   ├── PasswordSessionsApplication.java
    │   ├── SecurityConfiguration.java
    │   └── PasswordController.java
    └── test/java/com/example/passwordsessions/
        └── PasswordChangeTest.java
~~~

### 6.1. Maven

Tệp <code>pom.xml</code>:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>password-sessions-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. Entry point và endpoint kiểm tra session

Tạo <code>src/main/java/com/example/passwordsessions/PasswordSessionsApplication.java</code>:

~~~java
package com.example.passwordsessions;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PasswordSessionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordSessionsApplication.class, args);
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }
}
~~~

<code>/me</code> chỉ trả tên người dùng hiện tại, không hiển thị session ID, password hash hay dữ liệu nhạy cảm. Request anonymous vào endpoint này phải được chuyển sang login.

### 6.3. Cấu hình authentication và session tracking

Tạo <code>src/main/java/com/example/passwordsessions/SecurityConfiguration.java</code>:

~~~java
package com.example.passwordsessions;

import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("Old-password-1234"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
        return new ServletListenerRegistrationBean<>(
            new HttpSessionEventPublisher());
    }

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http,
                                    SessionRegistry registry) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(sessions -> sessions
                .maximumSessions(5)
                    .expiredUrl("/login?expired")
                    .sessionRegistry(registry))
            .build();
    }
}
~~~

Cách cấu hình hoạt động:
- <code>InMemoryUserDetailsManager</code> vừa cung cấp <code>UserDetailsService</code> khi login, vừa cung cấp <code>updateUser(...)</code> cho demo đổi mật khẩu.
- <code>maximumSessions(5)</code> bật cơ chế theo dõi session đồng thời và đăng ký session với <code>SessionRegistry</code>. Giới hạn 5 chỉ giúp mô phỏng nhiều session; nó không có nghĩa lệnh đổi mật khẩu chỉ tìm tối đa 5 session một cách tổng quát.
- <code>expiredUrl("/login?expired")</code> cho biết session bị đánh dấu expired sẽ được redirect về login khi nó gửi request tiếp theo. Trạng thái expired không có nghĩa cookie trên thiết bị khác đã biến mất tức thì.
- <code>HttpSessionEventPublisher</code> giúp registry nhận sự kiện hủy session.
- CSRF vẫn bật mặc định đối với POST. Form login mặc định xử lý <code>POST /login</code>, yêu cầu authentication cho <code>/me</code> và <code>/password/change</code>.
- Session fixation protection được Spring Security hỗ trợ khi login; nếu thay authentication strategy/custom filters, cần kiểm tra cấu hình này còn hiệu lực hay không.

### 6.4. Controller kiểm tra lại mật khẩu và thu hồi session

Tạo <code>src/main/java/com/example/passwordsessions/PasswordController.java</code>:

~~~java
package com.example.passwordsessions;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PasswordController {

    private final InMemoryUserDetailsManager users;
    private final PasswordEncoder encoder;
    private final SessionRegistry sessions;
    private final SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

    public PasswordController(InMemoryUserDetailsManager users,
                              PasswordEncoder encoder,
                              SessionRegistry sessions) {
        this.users = users;
        this.encoder = encoder;
        this.sessions = sessions;
    }

    @PostMapping("/password/change")
    public ResponseEntity<String> change(
            @RequestParam String currentPassword,
            @RequestParam String newPassword,
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        // Lấy danh tính từ authentication của server.
        UserDetails stored = users.loadUserByUsername(authentication.getName());

        // Session hiện tại không thay cho xác thực lại.
        if (!encoder.matches(currentPassword, stored.getPassword())) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body("Current password was not accepted");
        }

        // Chính sách tối thiểu cho demo, chưa đủ cho production.
        if (newPassword.length() < 12
                || encoder.matches(newPassword, stored.getPassword())) {
            return ResponseEntity.badRequest()
                .body("Choose a different password with 12+ characters");
        }

        UserDetails updated = User.withUserDetails(stored)
            .password(encoder.encode(newPassword))
            .build();
        users.updateUser(updated);

        // Những phiên đang được registry theo dõi của cùng principal.
        for (SessionInformation info
                : sessions.getAllSessions(authentication.getPrincipal(), false)) {
            info.expireNow();
        }

        // Session hiện tại bị hủy và SecurityContext được xóa.
        logout.logout(request, response, authentication);
        return ResponseEntity.ok("Password changed; sign in again");
    }
}
~~~

Các quyết định thiết kế ở đây:
- Endpoint không nhận tên tài khoản cần đổi từ client. Chỉ dùng <code>authentication.getName()</code> do Spring Security xác định để tránh thao tác chéo tài khoản.
- <code>encoder.matches</code> kiểm tra current password; điều kiện mật khẩu mới được xác minh **trước khi ghi**.
- <code>User.withUserDetails(stored)</code> sao chép trạng thái/tập quyền của user demo, chỉ đổi hash mới; <code>users.updateUser</code> làm cập nhật trong kho in-memory.
- <code>getAllSessions(principal, false)</code> lấy những phiên chưa expired trong registry; <code>expireNow()</code> đánh dấu toàn bộ, gồm phiên hiện tại nếu có trong registry.
- <code>SecurityContextLogoutHandler.logout</code> hủy ngay HttpSession của request hiện tại và dọn context. Session khác bị từ chối ở request tiếp theo nhờ <code>ConcurrentSessionFilter</code>.
- Vì đây là in-memory store/registry, code không có transaction xuyên nhiều node và không thu hồi JWT/remember-me token. Đoạn này là **mô hình một JVM để học**, không phải lời hứa global logout production.

## 7. Kiểm thử hai phiên đăng nhập và thay đổi credential bằng MockMvc

Thêm <code>src/test/java/com/example/passwordsessions/PasswordChangeTest.java</code>:

~~~java
package com.example.passwordsessions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.result.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.result.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordChangeTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry sessions;

    private MockHttpSession login(String password) throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", password))
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void changeRequiresReauthenticationAndRevokesBothSessions()
            throws Exception {
        MockHttpSession browserA = login("Old-password-1234");
        MockHttpSession browserB = login("Old-password-1234");

        mvc.perform(get("/me").session(browserA))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
        mvc.perform(get("/me").session(browserB))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        // CSRF thiếu: request đổi mật khẩu bị chặn.
        mvc.perform(post("/password/change")
                .session(browserA)
                .param("currentPassword", "Old-password-1234")
                .param("newPassword", "New-password-5678"))
            .andExpect(status().isForbidden());

        // Current password sai: chưa được đổi credential.
        mvc.perform(post("/password/change")
                .session(browserA).with(csrf())
                .param("currentPassword", "incorrect")
                .param("newPassword", "New-password-5678"))
            .andExpect(status().isForbidden());

        // Đổi thành công: cần nhập current password đúng và CSRF.
        mvc.perform(post("/password/change")
                .session(browserA).with(csrf())
                .param("currentPassword", "Old-password-1234")
                .param("newPassword", "New-password-5678"))
            .andExpect(status().isOk())
            .andExpect(content().string("Password changed; sign in again"));

        assertThat(browserA.isInvalid()).isTrue();

        SessionInformation other =
            sessions.getSessionInformation(browserB.getId());
        assertThat(other).isNotNull();
        assertThat(other.isExpired()).isTrue();

        // Request tiếp theo bằng phiên B bị chuyển tới login.
        mvc.perform(get("/me").session(browserB))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        // Mật khẩu cũ không còn xác thực cho lần đăng nhập mới.
        mvc.perform(post("/login").with(csrf())
                .param("username", "alice")
                .param("password", "Old-password-1234"))
            .andExpect(unauthenticated());

        // Credential mới tạo được phiên mới hợp lệ.
        MockHttpSession newSession = login("New-password-5678");
        mvc.perform(get("/me").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }
}
~~~

Đây là **một test tích hợp có đủ cả cấu hình, authentication filters, session registry và controller**. Nó làm rõ các invariant:
- Khi thiếu CSRF hoặc current password sai, không được đổi credential.
- Hai login độc lập tạo hai HttpSession cùng principal.
- Sau thay password, session hiện tại bị invalidate; session khác bị đánh dấu expired và bị redirect khi gọi tiếp.
- Mật khẩu cũ không thể đăng nhập lại; mật khẩu mới hoạt động.

Chạy với JDK 17+ và Maven ở thư mục <code>password-sessions-demo</code>:

~~~bash
mvn test
mvn spring-boot:run
~~~

<code>mvn test</code> chạy test tự động, **không** bảo đảm ngay lập tức tất cả session trong Redis/cluster đều bị thu hồi vì demo chỉ sử dụng một JVM. Trong bài này không có stdout cố định: log Maven/Tomcat có thể khác theo môi trường. Kết quả quan trọng là bộ test thành công hoặc nêu rõ assertion thất bại.

Nếu thử qua browser thủ công, mở <code>/login</code> và đăng nhập bằng <code>alice / Old-password-1234</code>, sau đó gọi endpoint đổi mật khẩu bằng một form có CSRF token do Spring Security cung cấp. Gửi <code>POST /password/change</code> trần bằng curl mà không có CSRF token **dự kiến bị 403**. Đây là bảo vệ có chủ đích; không tắt CSRF toàn app chỉ để tiện thử.

## 8. Các loại session và token cần được rà soát ngoài HttpSession

| Loại trạng thái | Điểm cần xử lý khi password đổi |
| --- | --- |
| HttpSession hiện tại | Logout, clear SecurityContext, invalidate session |
| HttpSession ở browser/thiết bị khác | Liệt kê/xóa hoặc đánh dấu expired ở kho session được chia sẻ |
| Remember-me cookie dạng persistent token | Thu hồi series/token trong persistent token repository; xóa cookie phù hợp |
| Remember-me dựa trên hash password | Thay đổi password có thể khiến cookie cũ không còn xác thực nếu implementation sử dụng hash; vẫn phải kiểm chứng cơ chế thực tế |
| Refresh token | Thu hồi refresh token/grant thuộc user, ngăn cấp access token mới |
| Access token JWT tự chứa | Đổi password không thể tự xóa JWT khỏi client; cần expiry ngắn, token version, blacklist hoặc introspection/nguồn kiểm tra phù hợp |
| OAuth2/OIDC session tại IdP | Xem chức năng logout/revocation/back-channel logout của IdP và contract với ứng dụng |
| WebSocket/connection sống lâu | Có thể cần đóng kết nối hoặc kiểm tra quyền lại trên thông điệp nhạy cảm |
| Session ở node khác | Cần kho session chung hoặc cơ chế revocation được chia sẻ giữa các node |

**Không gộp các khái niệm:** <code>JSESSIONID</code> là session identifier của Servlet, còn JWT access token/refresh token/remember-me cookie có lifecycle riêng. Spring Security không tự thu hồi tất cả chúng chỉ vì controller gọi <code>invalidate()</code> trên một HttpSession.

### Stateless JWT thường gặp

Ví dụ JWT được phát hành lúc tài khoản có <code>credentialVersion=4</code>. Khi đổi mật khẩu, server tăng version lên 5. Nếu mỗi request có xác minh token signature/issuer/audience/expiry và **kiểm tra version của token so với account version hiện tại** (từ nguồn đáng tin), token version 4 có thể bị từ chối.

Điều này cần thiết kế hệ thống riêng: JWT mặc định không tự có trường version và Spring Security không tự đối chiếu version database. Lấy version từ cache cũng cần chính sách nhất quán/TTL phù hợp với yêu cầu thu hồi; không nên tin một claim version nếu bỏ qua kiểm tra chữ ký hoặc nguồn cấp token. Với token chỉ được validate offline, không truy vấn server, token cũ có thể tiếp tục tồn tại cho tới khi hết hạn.

## 9. Nhiều server: SessionRegistryImpl không đủ để logout everywhere

Giả sử cùng ứng dụng đang chạy sau load balancer:

~~~text
Browser A -> App node A -> SessionRegistryImpl của node A
Browser B -> App node B -> SessionRegistryImpl của node B
Browser C -> App node C -> SessionRegistryImpl của node C
                    |
             Database tài khoản dùng chung
~~~

Khi đổi mật khẩu trên node A:
- Database có thể nhận hash mới.
- Registry của A đánh dấu session nó biết.
- Registry của B/C **không tự nhận** việc A vừa đánh dấu expired.
- Các session cũ có thể còn sống trên B/C cho tới khi có cơ chế chia sẻ hoặc kiểm tra lại.

Các cách thiết kế production thường dùng (có thể kết hợp):
1. **Kho session dùng chung**, ví dụ Spring Session + Redis/JDBC với chỉ mục principal được cấu hình đúng. Sau thay đổi thành công, tìm session thuộc account và xóa/đánh dấu ở kho tập trung. Dựa vào cách repository/index hoạt động thực tế và quyền được phép xóa.
2. **Credential/security version** trong account: lưu <code>version</code> lúc tạo Authentication; kiểm tra lại trước các request cần bảo vệ và từ chối/invalidate session nếu version không còn khớp. Cần xác định chi phí và freshness của tra cứu.
3. **Revocation event đáng tin:** sau commit password, phát sự kiện tới các node để dọn cache/session, có retry, idempotency và quan sát lỗi. Event chỉ là tăng tốc nếu hệ thống đòi hỏi độ chắc chắn cao; vẫn nên có kiểm tra nguồn chung.
4. **Rút ngắn vòng đời token + revoke refresh token:** với stateless access token, nên xác định khoảng thời gian token cũ còn sống và cơ chế thu hồi thích hợp cho mức rủi ro.

Ví dụ **mã minh họa, không độc lập** khi sử dụng một Spring Session repository đã có chỉ mục principal:

~~~java
// Cần cấu hình Spring Session / repository / principal index trước.
var sessions = indexedSessionRepository.findByPrincipalName(username);
for (String sessionId : sessions.keySet()) {
    indexedSessionRepository.deleteById(sessionId);
}
~~~

Ở đây <code>indexedSessionRepository</code> phải là một <code>FindByIndexNameSessionRepository</code> được cấu hình đúng và <code>username</code> lấy từ server, không phải giá trị tùy ý do client nhập. Chỉ xóa khi principal index đầy đủ; cần kiểm tra mọi loại session, race condition, failure handling và cách tách current session. **Đây không phải API thay thế trực tiếp vào demo SessionRegistryImpl.**

### Khi cần chính sách thu hồi mạnh

Một mô hình bền vững có thể lưu <code>credentialsChangedAt</code> hoặc <code>credentialVersion</code> trong database, và lưu phiên bản tương ứng trong Authentication/session lúc xác thực. Mỗi request hoặc nhóm request nhạy cảm sẽ đối chiếu với version hiện tại; phiên mang version cũ không còn được chấp nhận. Nó xử lý cả trường hợp một session không có trong registry, miễn request đi qua bộ lọc/check được thiết kế đúng. Cơ chế này phải được kiểm thử trên multi-node, cache và quyền truy cập tài nguyên.

## 10. Transaction, race condition và phục hồi khi có lỗi

Trình tự “update hash -> thu hồi session” có các cửa sổ lỗi:

| Điểm lỗi | Hậu quả | Cách xử lý ở hệ thống thật |
| --- | --- | --- |
| Current password không đúng | Người gọi không được đổi hash | Từ chối, rate limit và audit an toàn |
| Hai yêu cầu đổi đồng thời | Request ghi sau có thể ghi đè password mới | Transaction, optimistic version / row lock |
| Hash update thành công, revoke session thất bại | Session cũ có thể còn hợp lệ | Credential version bắt buộc, retry/outbox, giám sát |
| Revoke session trước nhưng hash update thất bại | Người dùng bị logout dù credential chưa đổi | Sắp xếp hành động theo ranh giới transaction |
| Session khác vừa được tạo trong lúc revoke | Session mới có thể lọt giữa các bước | Đồng bộ version/cutoff trong nguồn đáng tin |
| Một node mất kết nối message bus | Cache/session của node đó chưa biết đổi password | So khớp trạng thái với kho chung khi nhận request |
| Remember-me/refresh token không được xử lý | Credential phụ vẫn tạo session mới được | Revoke token trong cùng workflow, test riêng |

Giao dịch database không thể tự rollback việc xóa session ở một Redis hoặc revoke token tại IdP theo cách nguyên tử nếu không có kiến trúc phù hợp. Có thể dùng transactional outbox, trạng thái revocation bền vững và retry idempotent. Thiết kế cần chọn rõ mức bảo đảm và phản hồi khi một bước thất bại: không trả “đã logout mọi thiết bị” nếu thực tế chưa xác minh được.

## 11. CSRF, XSS, cookie và cấu hình browser

Với form login và cookie session, browser tự gắn cookie vào request đủ điều kiện; attacker có thể tìm cách tạo request thay đổi trạng thái qua trình duyệt nạn nhân. Do vậy:
- Bật và kiểm thử CSRF cho <code>POST /password/change</code>.
- Chỉ chấp nhận password trong request body, qua HTTPS; không dùng URL GET.
- Cookie session production nên dùng <code>Secure</code>, <code>HttpOnly</code> và SameSite phù hợp với luồng thực tế, cùng timeout hợp lý.
- HttpOnly giảm khả năng JavaScript đọc cookie nhưng **không** ngăn mọi XSS thực hiện request; phải bảo vệ XSS.
- Sau thay đổi credential, có thể xóa cookie session ở browser bằng response có cùng Path/Domain, nhưng invalidation **phía server** mới là trọng tâm. Xóa cookie không thể đảm bảo session các browser khác đã bị hủy.
- Nếu frontend gọi API cross-origin, cần CORS và <code>credentials</code> được cấu hình rõ, không dùng CORS như biện pháp thay thế authentication/authorization.

Không hiển thị mật khẩu hiện tại hoặc mới trở lại trong HTML/log; không gửi mật khẩu mới qua email. Có thể gửi thông báo “mật khẩu đã thay đổi” kèm thời điểm, kênh báo cáo bất thường, nhưng không kèm secret.

## 12. Kiểm tra UX và hành vi bảo mật sau khi đổi password

Một luồng người dùng hợp lý:
1. Trang settings yêu cầu mật khẩu hiện tại và mật khẩu mới; với account có MFA, có thể yêu cầu xác thực lại theo chính sách.
2. Request sử dụng HTTPS và token CSRF. Server xác định tài khoản từ authentication, kiểm tra bằng nguồn đáng tin, rồi cập nhật hash.
3. Server thu hồi session/token theo chính sách “đăng xuất tất cả thiết bị”. Response không tiết lộ thông tin nhạy cảm.
4. Giao diện xóa trạng thái hiển thị cũ và điều hướng người dùng sang login; không dựa vào thao tác frontend để quyết định session server đã hết hiệu lực.
5. Người dùng đăng nhập lại bằng credential mới. Mọi thiết bị còn session cũ được yêu cầu xác thực khi gọi API tiếp.
6. Hệ thống audit sự kiện theo account ID, thời điểm, loại thao tác và kết quả; không log current/new password hay token.

**Lưu ý về status:** với form login, session cũ có thể redirect 302 sang login; API có thể trả 401 hoặc 403 theo entry point/configuration. Không khẳng định mọi ứng dụng sẽ trả cùng một status. Trong demo, <code>expiredUrl</code> được đặt rõ để test redirect.

## 13. Những lỗi thường gặp

| Sai lầm | Kết quả | Hướng sửa |
| --- | --- | --- |
| Chỉ đổi hash trong DB | Session đang đăng nhập vẫn có authentication cũ | Thu hồi session/token hoặc kiểm tra credential version |
| Chỉ logout tab hiện tại | Thiết bị khác không bị ảnh hưởng | Kho session theo principal và chính sách multi-node |
| Gọi <code>expireNow()</code> nhưng không có tracking/filter | Session không được đăng ký hoặc không được kiểm tra expired | Bật concurrency management, listener và test request kế |
| Dùng SessionRegistryImpl trên nhiều node | Mỗi node chỉ biết session của mình | Spring Session/kho chung hoặc version guard |
| Không yêu cầu current password/step-up | Session bị đánh cắp có thể đổi credential | Re-authentication phù hợp |
| Tắt CSRF để POST hoạt động | Browser cookie app tăng nguy cơ CSRF | Giữ CSRF và gửi token đúng |
| Dùng BCrypt encode rồi so sánh hai hash để biết password giống | Có thể so sánh sai do salt | Dùng <code>matches</code> |
| Nhận <code>username</code> từ form để chọn account | Có nguy cơ đổi mật khẩu người khác | Lấy account ID từ principal server |
| Quên refresh/remember-me token | Người dùng đã logout nhưng token phụ vẫn cấp quyền | Liệt kê mọi loại credential và revoke |
| Tin rằng JWT tự mất hiệu lực khi đổi password | JWT cũ còn chữ ký và chưa hết hạn | Token version, revoke/introspection hoặc TTL phù hợp |
| Gửi thông báo thành công trước khi revoke chắc chắn | Sai trạng thái bảo mật thực tế | Giao dịch + retry/monitoring + message đúng |
| Chỉ test một session | Không phát hiện phiên khác vẫn có thể dùng | Test hai browser và hệ thống nhiều node |
| Lưu plaintext hoặc log password | Rò rỉ credential | PasswordEncoder, TLS, không log dữ liệu nhạy cảm |

## 14. Checklist triển khai ở sản phẩm thật

1. Xác định cơ chế xác thực: form login, HTTP Basic, OAuth2/OIDC, remember-me, JWT, refresh token; liệt kê những trạng thái cần thu hồi.
2. Thiết kế re-authentication/step-up tương xứng rủi ro. Tài khoản SSO phải đi qua quy trình của IdP khi đổi mật khẩu tại IdP.
3. Xác định account từ principal đáng tin, không lấy userId tùy ý từ form; POST chỉ sau CSRF validation.
4. Kiểm tra current password bằng <code>PasswordEncoder.matches</code>, chính sách mật khẩu mới, chống reuse khi cần và xử lý lỗi an toàn.
5. Cập nhật hash và credential version qua transaction/lock hoặc optimistic concurrency.
6. Vô hiệu hóa session hiện tại và mọi session khác theo index principal hoặc version guard. Nếu có multi-node, bảo đảm trạng thái dùng chung.
7. Thu hồi remember-me/refresh tokens; quyết định rõ cách xử lý JWT/access token đã phát hành, cache và WebSocket connection.
8. Kiểm thử happy path và failure path: sai current password, thiếu CSRF, hai session, login bằng old/new password, session ở node khác, đổi đồng thời, revoke service lỗi.
9. Thông báo sự kiện đổi password theo kênh bảo mật phù hợp, audit không chứa secret, có quy trình báo cáo thao tác bất thường.
10. Xác minh rằng khi đã thông báo logout everywhere, mọi đường truy cập có thể sử dụng credential cũ đều đã bị chặn theo mức bảo đảm thiết kế.

## 15. Tự kiểm tra kiến thức

**Câu 1:** Sau khi update password hash, browser B đang đăng nhập có tự động bị logout không?  
**Trả lời:** Không. Authentication trong HttpSession hoặc token có thể còn hợp lệ; phải xử lý session/token revocation riêng.

**Câu 2:** <code>SessionInformation.expireNow()</code> đã ngay lập tức xóa cookie và HttpSession ở browser B chưa?  
**Trả lời:** Không. Nó đánh dấu session trong registry; khi browser B gửi request tiếp, filter cần nhận biết và xử lý phiên expired. Cookie của browser không tự bị xóa tức thì.

**Câu 3:** Vì sao phải kiểm tra mật khẩu hiện tại nếu người dùng đã có session?  
**Trả lời:** Đổi credential là thao tác nhạy cảm; session hiện tại có thể bị chiếm quyền. Re-authentication/step-up là một lớp bảo vệ bổ sung, cùng CSRF và biện pháp an toàn khác.

**Câu 4:** SessionRegistryImpl trên node A có chắc thu hồi session trên node B của cluster không?  
**Trả lời:** Không. RegistryImpl in-memory chỉ có thông tin của tiến trình của nó; cần kho chung/version guard/event có kiểm soát.

**Câu 5:** Đổi mật khẩu có làm JWT tự hết hạn không?  
**Trả lời:** Không. JWT thường có vòng đời độc lập; cần thiết kế TTL, revoke/introspection hoặc đối chiếu credential version.

**Câu 6:** Với quên mật khẩu, có cần nhập current password không?  
**Trả lời:** Không. Luồng khôi phục phải dùng bằng chứng thay thế như token dùng một lần, TTL ngắn và xác minh đủ mạnh, rồi thu hồi token đó.

**Ghi nhớ:** thao tác đổi mật khẩu chỉ hoàn chỉnh khi **đã xác thực lại**, **cập nhật credential đúng cách** và **vô hiệu hóa các session/token liên quan**. Spring Security cung cấp nhiều thành phần để thực hiện, nhưng bảo đảm logout everywhere phụ thuộc vào cách đăng ký session, kiến trúc nhiều node và chính sách token thực tế.
