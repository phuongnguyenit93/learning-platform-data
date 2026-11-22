# Remember-me, anonymous và fullyAuthenticated trong chính sách truy cập

> Phạm vi: **Spring Security - authentication → Ghi nhớ đăng nhập**, **Spring Boot 3.x / Spring Security 6.x / Servlet / Java 17+**. Bài tập trung vào **mức độ tin cậy của phiên đăng nhập** khi ra quyết định truy cập: khách chưa đăng nhập (anonymous), người được nhận diện lại bằng remember-me cookie, và người đã xác thực tương tác đầy đủ (fully authenticated). Đây là các mức khác nhau; cùng một username và cùng quyền `ROLE_USER` không có nghĩa mọi thao tác đều nên được cho phép.

## 1. Ba trạng thái không giống nhau

Một website có chức năng “Ghi nhớ đăng nhập” thường để người dùng đánh dấu checkbox trong form login. Sau khi xác thực mật khẩu thành công, server có thể cấp một cookie remember-me tồn tại lâu hơn session đăng nhập thông thường. Khi session hết hoặc trình duyệt không gửi session cũ, cookie đó giúp **khôi phục danh tính với mức tin cậy remember-me**, chứ không phải chứng minh người dùng vừa nhập lại mật khẩu.

| Trạng thái | Cách hình thành | Authentication thường gặp | Có thể đọc hồ sơ? | Có nên đổi mật khẩu/chuyển tiền? |
| --- | --- | --- | --- | --- |
| **Anonymous** | Chưa có authentication hợp lệ; Spring Security tạo anonymous token cho request | `AnonymousAuthenticationToken` | Không, trừ khi route công khai | Không |
| **Remember-me** | Cookie nhớ đăng nhập được xác minh khi chưa có authentication từ session | `RememberMeAuthenticationToken` | Có thể, nếu policy dùng `authenticated()` | Không nên; yêu cầu `fullyAuthenticated()`, có thể cần MFA |
| **Fully authenticated** | Đăng nhập tương tác qua form/mật khẩu (hoặc cơ chế được framework coi là full) | `UsernamePasswordAuthenticationToken` xác thực thành công | Có | Có thể sau khi kiểm tra cả quyền nghiệp vụ và mức xác thực |

**Điểm cốt lõi:** Spring Security không tự xem remember-me là “chưa đăng nhập”; nó là một authentication hợp lệ nhưng được nhận diện là **mức tin cậy thấp hơn** đối với các hành động nhạy cảm. Vì vậy, `authenticated()` **cho phép** cả remember-me lẫn full login, còn `fullyAuthenticated()` chỉ nhận full login, loại trừ anonymous và remember-me.

### 1.1. authenticated(), fullyAuthenticated(), rememberMe(), anonymous()

Spring Security 6.x cung cấp các quy tắc trong `authorizeHttpRequests`:

- `.authenticated()`: yêu cầu một danh tính đã xác thực, **bao gồm** người được nhận diện bằng remember-me, **không bao gồm anonymous**.
- `.fullyAuthenticated()`: yêu cầu danh tính đã xác thực **không qua remember-me** và không phải anonymous; thường dùng với thay đổi email, mật khẩu, payout, thay đổi bảo mật.
- `.rememberMe()`: yêu cầu request đang được xác thực ở **trạng thái remember-me**; người đang full login không tự khớp quy tắc này. Ít dùng cho nghiệp vụ, hữu ích khi muốn làm trang chuyên biệt “chào mừng bạn quay lại”.
- `.anonymous()`: chỉ cho đối tượng được framework coi là anonymous; không nhận remember-me hoặc full login.
- `.permitAll()`: mọi trạng thái đều có thể đi qua; không đồng nghĩa là request phải có `AnonymousAuthenticationToken`.
- `.hasRole("USER")` hoặc `.hasAuthority("...")`: kiểm tra **quyền**, không tự yêu cầu `fullyAuthenticated()`. Người remember-me có quyền `ROLE_USER` vẫn có thể vượt qua một rule chỉ kiểm tra role.

### 1.2. Ma trận chính sách truy cập

| Policy | Anonymous | Remember-me | Fully authenticated |
| --- | :---: | :---: | :---: |
| `permitAll()` | ✅ | ✅ | ✅ |
| `anonymous()` | ✅ | ❌ | ❌ |
| `rememberMe()` | ❌ | ✅ | ❌ |
| `authenticated()` | ❌ | ✅ | ✅ |
| `fullyAuthenticated()` | ❌ | ❌ | ✅ |
| `hasRole("USER")` (nếu có role) | ❌ | ✅ | ✅ |
| `fullyAuthenticated()` **và** `hasRole("ADMIN")` | ❌ | ❌ | Chỉ admin |

Bảng mô tả quyết định **authorization** của framework, không phải mã HTTP cố định. Với form login, khi anonymous hoặc remember-me yêu cầu trang phải full login, `ExceptionTranslationFilter` thường **redirect tới trang login** (`302`). Người đã full login nhưng thiếu role thường nhận `403 Forbidden`. Nếu API dùng authentication entry point khác, mã phản hồi có thể là `401`/`403` tùy cấu hình.

**Không nhầm:** “remember-me đã khôi phục principal và authorities” không đồng nghĩa người đó đã xác thực lại trong phiên hiện tại. `fullyAuthenticated()` là kiểm tra dạng authentication theo `AuthenticationTrustResolver`, **không** chứng minh MFA vừa được thực hiện, không phải freshness window và không thay thế các yêu cầu step-up riêng.

## 2. Vì sao AnonymousAuthenticationToken có thể gây nhầm?

Khi chưa có session hoặc remember-me hợp lệ, `AnonymousAuthenticationFilter` có thể đưa một `AnonymousAuthenticationToken` vào `SecurityContextHolder`. Token này có thể trả `authentication.isAuthenticated() == true` vì nó đã được framework tạo, nhưng nó **vẫn biểu thị người dùng vô danh**, không được coi là authentication của một người dùng thật.

Vì vậy, kiểm tra ngây thơ sau là **không đủ** để bảo vệ endpoint:

```java
Authentication a = SecurityContextHolder.getContext().getAuthentication();
if (a != null && a.isAuthenticated()) {
    // Sai nếu coi đây là bằng chứng đã đăng nhập thật:
    // AnonymousAuthenticationToken cũng có thể trả true.
}
```

Spring Security dùng `AuthenticationTrustResolver` để phân loại nguồn authentication:

```java
AuthenticationTrustResolver trust = new AuthenticationTrustResolverImpl();
Authentication a = SecurityContextHolder.getContext().getAuthentication();

boolean guest = trust.isAnonymous(a);
boolean remembered = trust.isRememberMe(a);
boolean knownUser = trust.isAuthenticated(a);
boolean fullLogin = trust.isFullyAuthenticated(a);
```

`isAuthenticated(a)` của **trust resolver** (khác với `a.isAuthenticated()` thô) trả false với anonymous. `isFullyAuthenticated(a)` trả false với anonymous/remember-me, true với authentication đầy đủ được nhận diện theo chuẩn resolver.

**Khuyến nghị:** trong cấu hình URL, dùng `authorizeHttpRequests(...).authenticated()/fullyAuthenticated()`; không tự viết bộ lọc rồi dựa vào `Authentication.isAuthenticated()`. Với business method, kết hợp `@PreAuthorize`/authorization manager phù hợp hoặc kiểm tra lại trạng thái qua trust resolver nếu có lý do rõ ràng.

## 3. Vòng đời remember-me: từ checkbox tới request sau

```text
Lần truy cập đầu tiên:
  Browser (không session)
     | GET /profile
     v
  Authorization: chưa authenticated
     '-- chuyển tới /login (form)

Đăng nhập tương tác:
  Browser
     | POST /login
     | username=alice, password=study-pass
     | remember-me=on + CSRF
     v
  UsernamePasswordAuthenticationFilter
     | AuthenticationManager xác minh username/password
     | SecurityContext được lưu trong HttpSession
     | RememberMeServices.loginSuccess()
     '-- response chứa cookie JSESSIONID và remember-me

Trong lúc session còn tồn tại:
  GET /auth-state + JSESSIONID
     '-- Authentication từ HttpSession -> fully-authenticated:alice

Sau khi session không được gửi/đã hết:
  GET /auth-state + remember-me cookie, KHÔNG có JSESSIONID cũ
     |
     v
  RememberMeAuthenticationFilter
     | RememberMeServices.autoLogin() kiểm tra cookie
     | tải UserDetails từ nguồn server
     | tạo RememberMeAuthenticationToken
     '-- AuthenticationTrustResolver.isRememberMe() == true

  /profile dùng authenticated()  -> được phép
  /security-settings dùng fullyAuthenticated() -> yêu cầu đăng nhập lại
```

Remember-me **chỉ hoạt động nếu token còn hợp lệ** và request không có Authentication đã được chấp nhận ở context. Nếu cả session đang full login và remember-me cookie đều tồn tại, full authentication từ session thường được dùng; remember-me không tự hạ mức tin cậy.

### 3.1. Hai cách cấp remember-me token

**Token hash-based** (`TokenBasedRememberMeServices`): chữ ký phụ thuộc username, expiry, password (giá trị hiện do `UserDetailsService` cung cấp) và secret key của ứng dụng. Spring Security 6.x mặc định có triển khai SHA-256 cho signature. Server xác minh cookie bằng thông tin account + key. Ưu điểm là đơn giản, không cần bảng token; nhược điểm là nếu cookie bị đánh cắp, nó có thể bị **replay** tới khi hết hạn hoặc khi key/password thay đổi. Logout trình duyệt thường xóa cookie **trên client**; điều đó không thể thu hồi một bản cookie đã bị đánh cắp ở nơi khác chỉ bằng thao tác xóa local cookie.

**Persistent token** (`PersistentTokenBasedRememberMeServices`): dùng token series/random token lưu trên server (`PersistentTokenRepository`; ví dụ JDBC). Thường hỗ trợ rotation và cơ chế quản trị token có trạng thái. Hệ thống thật cần thiết kế chiến lược revoke, xử lý token bị dùng lại, dọn token cũ và chính sách multi-device. Nó vẫn là **bearer cookie có giá trị bảo mật**, không tự biến remember-me thành full login.

Cả hai cơ chế thông thường đều cần `UserDetailsService` để tải lại danh tính và quyền. Nếu authentication chính dùng provider ngoài (như LDAP/custom) mà không có `UserDetailsService` phù hợp, phải cấu hình nguồn lookup rõ ràng; không giả định bật `rememberMe()` là tự khôi phục được mọi loại principal.

### 3.2. Remember-me cookie không giống session cookie

| Thuộc tính | Session cookie | Remember-me cookie |
| --- | --- | --- |
| Mục đích | Tham chiếu trạng thái `HttpSession` | Chứng cứ để tái tạo authentication khi session không còn |
| Tên thường gặp | `JSESSIONID` | `remember-me` (có thể đổi) |
| Phạm vi tồn tại | Session/browser/container policy | Theo token validity và cookie policy |
| Xóa session | Mất phiên full login | Cookie nhớ đăng nhập có thể vẫn hợp lệ |
| Độ tin cậy authorization | Full login nếu context chứa kết quả login tương tác | Mức remember-me, không phải full login |
| Khả năng bị đánh cắp | Có thể chiếm session | Có thể tái đăng nhập dưới mức remember-me |

Không đặt remember-me key trong source code production hoặc gửi cookie vào log/analytics. Cấu hình cookie `Secure`/`HttpOnly`/`SameSite`, HTTPS và domain/path phù hợp; chính sách CSRF vẫn quan trọng vì browser tự gửi cookies.

## 4. Ví dụ Spring Boot 3.x / Spring Security 6.x / Java 17+

Ví dụ dùng form login chuẩn, mã hóa BCrypt cho user demo, remember-me opt-in và một policy phân biệt bốn trạng thái. Trang login `GET /login` do Spring Security tạo mặc định; không viết custom login page để tránh làm phân tán trọng tâm.

### 4.1. Phụ thuộc

Trong project Spring Boot 3.x có Gradle plugin và Java 17:

```groovy
// build.gradle (phần dependencies)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không cần Spring Session hay database để chạy demo một node này. Khi triển khai thật, thay account in-memory bằng user store và token store có chính sách quản lý tương ứng.

### 4.2. Application class

**`src/main/java/example/rememberpolicy/RememberPolicyApplication.java`**

```java
package example.rememberpolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberPolicyApplication.class, args);
    }
}
```

### 4.3. Cấu hình SecurityFilterChain

**`src/main/java/example/rememberpolicy/SecurityConfig.java`**

```java
package example.rememberpolicy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("study-pass"))
                .roles("USER")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            Environment environment) throws Exception {

        String signingKey = environment.getRequiredProperty(
            "app.remember-me.key");

        http
            .authorizeHttpRequests(auth -> auth
                // Ai cũng có thể vào tài nguyên công khai.
                .requestMatchers("/public", "/auth-state").permitAll()

                // Route riêng cho khách vô danh.
                .requestMatchers("/guest-only").anonymous()

                // Route chỉ dành cho request được khôi phục qua remember-me.
                .requestMatchers("/remembered-only").rememberMe()

                // Có thể xem hồ sơ bằng full login hoặc remember-me.
                .requestMatchers("/profile").authenticated()

                // Thao tác nhạy cảm: nhớ đăng nhập là chưa đủ.
                .requestMatchers("/security-settings").fullyAuthenticated()

                // Ví dụ nhạy cảm cần cả full login VÀ ROLE_ADMIN.
                .requestMatchers("/admin/critical").access(
                    AuthorizationManagers.allOf(
                        AuthenticatedAuthorizationManager
                            .<RequestAuthorizationContext>fullyAuthenticated(),
                        AuthorityAuthorizationManager
                            .<RequestAuthorizationContext>hasRole("ADMIN")
                    )
                )

                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/profile", true)
                .permitAll()
            )
            .rememberMe(remember -> remember
                .key(signingKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
            );

        // CSRF mặc định vẫn bật cho POST /login và POST /logout.
        return http.build();
    }
}
```

**Điều quan trọng trong cấu hình:**

1. Thứ tự matcher có ý nghĩa; Spring Security chọn rule đầu tiên phù hợp URL. `/security-settings` dùng `fullyAuthenticated()` chứ không chỉ `hasRole("USER")`.
2. `/admin/critical` dùng `AuthorizationManagers.allOf(...)` để yêu cầu **đồng thời** full login và `ROLE_ADMIN`. Chỉ yêu cầu `hasRole("ADMIN")` sẽ không loại trừ remember-me của một admin nếu quyền `ROLE_ADMIN` được tải lại từ server.
3. `/remembered-only` là route minh họa cho trạng thái remember-me **đúng nghĩa**. Nó không thay thế `/profile`. Trong ứng dụng thật, ít khi cần endpoint chỉ cho remember-me mà từ chối full login; trang “chào mừng quay lại” là một trường hợp có thể cân nhắc.
4. `/guest-only` dùng `anonymous()` để minh họa route chỉ dành cho khách. `/login` do Spring Security tạo được phép truy cập qua `formLogin(...permitAll())`, không đặt login page vào rule `anonymous()` vì full user/remembered user có thể cần đăng nhập lại để nâng mức tin cậy.
5. `.rememberMe(...)` thiết lập dịch vụ remember-me với secret key, `UserDetailsService` và thời hạn 7 ngày. Checkbox phải gửi parameter `remember-me=on` khi đăng nhập; nếu không chọn, không tự cấp cookie. Thời hạn 7 ngày chỉ là demo, không phải khuyến nghị mặc định cho mọi sản phẩm.
6. `.formLogin(...)` dùng `UsernamePasswordAuthenticationFilter` và success handler chuẩn. Remember-me service được gọi ở login thành công, còn `RememberMeAuthenticationFilter` có thể phục hồi authentication ở request sau **khi không có context đã đăng nhập**.
7. `.anyRequest().denyAll()` chặn route chưa khai báo. Khi thêm endpoint mới, phải lựa chọn đúng policy thay vì để mặc định nới lỏng.
8. Không tắt CSRF cho form login dùng cookie; request POST từ browser vẫn cần token. `MockMvc` dùng `csrf()` cho POST.
9. `.key(signingKey)` dùng secret riêng của server. **Không** dùng khóa ví dụ của môi trường dev cho deployment thật; phải nạp qua secret manager/environment và quản lý rotation.

### 4.4. Cấu hình demo

**`src/main/resources/application.yml`**

```yaml
app:
  remember-me:
    # Chỉ dùng khi học trên máy cá nhân; triển khai thật dùng secret riêng.
    key: local-demo-key-only-do-not-use-in-production-2026

server:
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax
```

Ở production cần bí mật ngẫu nhiên đủ mạnh, không commit vào git; cấu hình HTTPS/cookie `Secure` và `SameSite` theo threat model. Với nhiều instance, key phải nhất quán giữa các node phục vụ cùng domain. Thay key sẽ khiến các cookie hash-based đã cấp trước đó không còn xác minh được; thay password cũng có thể làm điều tương tự.

### 4.5. Controller hiển thị trạng thái trust resolver

**`src/main/java/example/rememberpolicy/AccessController.java`**

```java
package example.rememberpolicy;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccessController {
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/guest-only")
    String guestOnly() {
        return "guest";
    }

    @GetMapping("/remembered-only")
    String rememberedOnly() {
        return "welcome-back";
    }

    @GetMapping("/profile")
    String profile(Authentication user) {
        return "profile:" + user.getName();
    }

    @GetMapping("/security-settings")
    String securitySettings(Authentication user) {
        return "security:" + user.getName();
    }

    @GetMapping("/admin/critical")
    String adminCritical(Authentication user) {
        return "admin:" + user.getName();
    }

    @GetMapping("/auth-state")
    String authState() {
        Authentication a =
            SecurityContextHolder.getContext().getAuthentication();

        if (a == null || trust.isAnonymous(a)) {
            return "anonymous";
        }
        if (trust.isRememberMe(a)) {
            return "remember-me:" + a.getName();
        }
        if (trust.isFullyAuthenticated(a)) {
            return "fully-authenticated:" + a.getName();
        }
        return "unrecognized";
    }
}
```

`/auth-state` được mở công khai **chỉ để quan sát trong demo**, đọc context qua `SecurityContextHolder` và phân loại bằng `AuthenticationTrustResolver`. Không trả nguyên token, authorities, session ID, cookie value hoặc dữ liệu bí mật cho client. Trong ứng dụng thực, chỉ cung cấp những thông tin trạng thái mà UI thực sự cần và kiểm soát chúng bằng policy phù hợp.

Ví dụ body **mong đợi** từ endpoint (không phải stdout đã chạy):

```text
GET /auth-state khi chưa đăng nhập          -> anonymous
GET /auth-state với JSESSIONID đã login     -> fully-authenticated:alice
GET /auth-state chỉ với remember-me cookie  -> remember-me:alice
GET /profile với remember-me cookie         -> profile:alice
```

Lưu ý dùng remember-me cookie **không kèm session full login** trong phép thử thứ ba. Nếu vẫn gửi JSESSIONID có authentication đầy đủ, request tiếp tục được phân loại full login.

## 5. Kiểm thử MockMvc theo ba mức xác thực

Test chạy `SecurityFilterChain` thật và gọi `POST /login` với password + CSRF, lấy cookie từ response rồi thử request mới. Điểm này khác test dùng `@WithMockUser`, vì `@WithMockUser` gắn một authentication giả lập mà **không chứng minh** luồng phát và khôi phục remember-me cookie.

**`src/test/java/example/rememberpolicy/RememberPolicyTest.java`**

```java
package example.rememberpolicy;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RememberPolicyTest {
    @Autowired
    MockMvc mvc;

    private MvcResult login(
            String username, String password, boolean remember) throws Exception {
        var request = post("/login")
            .with(csrf())
            .param("username", username)
            .param("password", password);

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profile"))
            .andReturn();
    }

    private Cookie rememberCookie(String username, String password)
            throws Exception {
        MvcResult response = login(username, password, true);
        Cookie cookie = response.getResponse().getCookie("remember-me");
        assertNotNull(cookie, "Phải phát remember-me cookie khi opt-in");
        assertNotNull(cookie.getValue());
        assertFalse(cookie.getValue().isBlank());
        return cookie;
    }

    @Test
    void anonymousCanReadPublicAndGuestButNotProfile() throws Exception {
        mvc.perform(get("/auth-state"))
            .andExpect(status().isOk())
            .andExpect(content().string("anonymous"));

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/guest-only"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest"));

        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void interactiveLoginIsFullyAuthenticated() throws Exception {
        MvcResult response = login("alice", "study-pass", false);
        MockHttpSession session =
            (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/auth-state").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("fully-authenticated:alice"));

        mvc.perform(get("/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        mvc.perform(get("/security-settings").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("security:alice"));
    }

    @Test
    void fullLoginDoesNotMatchRememberMeOnlyOrAnonymousOnly()
            throws Exception {
        MvcResult response = login("alice", "study-pass", false);
        MockHttpSession session =
            (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/remembered-only").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/guest-only").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberCookieRestoresIdentityWithoutOriginalSession()
            throws Exception {
        Cookie cookie = rememberCookie("alice", "study-pass");

        // KHÔNG .session(...) -> không dùng Authentication từ session cũ.
        mvc.perform(get("/auth-state").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("remember-me:alice"));

        mvc.perform(get("/profile").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        mvc.perform(get("/remembered-only").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("welcome-back"));
    }

    @Test
    void rememberMeCannotReachFullyAuthenticatedResource()
            throws Exception {
        Cookie cookie = rememberCookie("alice", "study-pass");

        mvc.perform(get("/security-settings").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void sensitiveAdminEndpointRequiresFullLoginAndRole()
            throws Exception {
        // Alice full login nhưng thiếu ROLE_ADMIN.
        MvcResult aliceLogin = login("alice", "study-pass", false);
        MockHttpSession aliceSession =
            (MockHttpSession) aliceLogin.getRequest().getSession(false);
        assertNotNull(aliceSession);

        mvc.perform(get("/admin/critical").session(aliceSession))
            .andExpect(status().isForbidden());

        // Operator có ROLE_ADMIN, nhưng cookie remember-me chưa đủ.
        MvcResult adminLogin = login("operator", "admin-pass", true);
        Cookie adminRemember =
            adminLogin.getResponse().getCookie("remember-me");
        assertNotNull(adminRemember);

        mvc.perform(get("/admin/critical").cookie(adminRemember))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));

        // Cùng operator nhưng session full login được phép.
        MockHttpSession adminSession =
            (MockHttpSession) adminLogin.getRequest().getSession(false);
        assertNotNull(adminSession);

        mvc.perform(get("/admin/critical").session(adminSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:operator"));
    }

    @Test
    void rememberMeCookieIsOnlyIssuedWithOptIn() throws Exception {
        MvcResult response = login("alice", "study-pass", false);
        assertNull(response.getResponse().getCookie("remember-me"));
    }

    @Test
    void tamperedRememberCookieDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/auth-state")
                .cookie(new Cookie("remember-me", "invalid-cookie")))
            .andExpect(status().isOk())
            .andExpect(content().string("anonymous"));

        mvc.perform(get("/profile")
                .cookie(new Cookie("remember-me", "invalid-cookie")))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void csrfStillProtectsLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "study-pass")
                .param("remember-me", "on"))
            .andExpect(status().isForbidden());
    }
}
```

Bộ test trên có **9 phương thức `@Test`**. Mỗi helper login tạo một HTTP request độc lập; khi kiểm tra remember-me, test **chỉ gửi cookie remember-me**, không chuyển session đã được login. Ngược lại, kiểm tra full authentication dùng `MockHttpSession` trả về từ form login.

Chạy trong root project Spring Boot đã có Gradle wrapper:

```bash
./gradlew test --tests example.rememberpolicy.RememberPolicyTest
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat`. Các chuỗi response và status trong test là **kỳ vọng có thể xác minh**, không phải khẳng định đã chạy Gradle ở môi trường hiện tại.

### 5.1. Đọc các test đúng ý nghĩa

1. **Anonymous** được vào `/public` và `/guest-only`, không vào `/profile`. Khi chưa login, form authentication entry point redirect về `/login`.
2. **Full login** truy cập `/profile` và `/security-settings`; không khớp route riêng `.rememberMe()` hoặc `.anonymous()`.
3. **Remember-me auto login** chỉ cần cookie hợp lệ khi không có full session; `/auth-state` cho thấy `remember-me:alice`, trong khi `/profile` vẫn hoạt động vì `authenticated()` chấp nhận mức này.
4. **Fully authenticated resource** vẫn chặn remember-me: thường redirect về `/login` để người dùng xác thực lại.
5. **Phân quyền admin** minh họa hai điều kiện độc lập: user full login nhưng thiếu `ROLE_ADMIN` nhận `403`; admin nhớ đăng nhập nhưng chưa full login bị yêu cầu xác thực lại; admin full login mới vào được.
6. **Checkbox và cookie**: nếu không gửi parameter `remember-me`, login vẫn thành công nhưng response không cấp cookie remember-me.
7. **Cookie hỏng**: không khôi phục authentication; request bị phân loại anonymous và endpoint bảo vệ redirect tới login.
8. **CSRF** vẫn bảo vệ POST form login; remember-me không phải lý do tắt CSRF.

**Giới hạn MockMvc:** bài test giả lập HTTP và bộ lọc trên server, không mô phỏng đầy đủ hành vi browser về cookie expiry, SameSite, domain, Secure flag, private browsing hoặc proxy. Đối với production, cần kiểm thử end-to-end trên HTTPS với trình duyệt thật, TLS/cookie settings và chính sách timeout/revocation của hệ thống.

## 6. Kiểm thử thủ công với browser

Chạy ứng dụng tại `http://localhost:8080` trong môi trường học local. Từ trình duyệt profile riêng, vào `/login`. Form mặc định của Spring Security sẽ có tùy chọn remember-me khi tính năng đã bật.

**Lượt A — không đánh dấu Remember me:**

1. Login `alice` / `study-pass` mà không tích checkbox. `/auth-state` trả `fully-authenticated:alice` khi `JSESSIONID` vẫn hợp lệ.
2. Mở DevTools → Application/Storage → Cookies và kiểm tra không có cookie `remember-me` được cấp trong response này.
3. Khi session thật sự không còn, `GET /profile` chuyển về `/login`. Đừng chỉ mở tab thứ hai cùng browser rồi cho rằng đã xóa session.

**Lượt B — tích Remember me:**

1. Logout bằng POST với CSRF token rồi login lại, lần này chọn checkbox. Khi thành công, browser có thể có cả `JSESSIONID` và cookie `remember-me`.
2. Trong lúc `JSESSIONID` còn hiệu lực, `/auth-state` **vẫn là full login**, không phải remember-me.
3. Trong môi trường demo riêng biệt, loại bỏ **chỉ** cookie `JSESSIONID`/session browser, giữ cookie remember-me; gọi `/auth-state` lần nữa. Kết quả mong đợi là `remember-me:alice`.
4. `GET /profile` tiếp tục hoạt động; `GET /security-settings` chuyển về `/login` để yêu cầu nhập lại credential.
5. Sau khi nhập lại credential qua login form, request mới có full authentication. `fullyAuthenticated()` cho phép quyền truy cập tương ứng nếu policy nghiệp vụ cũng cho phép.

**Không sao chép cookie thật vào bug report hoặc log.** Với session cookie hoặc remember-me cookie bị đánh cắp, người khác có thể sử dụng nó như một loại bearer credential trong điều kiện nhất định. Đổi mật khẩu, thu hồi persistent token và vòng đời cookie phải được thiết kế theo rủi ro của sản phẩm.

## 7. Thiết kế chính sách truy cập theo mức độ nhạy cảm

| Loại chức năng | Quy tắc gợi ý | Lý do |
| --- | --- | --- |
| Trang giới thiệu, điều khoản, trang login | `permitAll()` | Không cần danh tính; login page có thể cần mở cho người đã nhớ đăng nhập |
| Welcome cho khách chưa có account | `anonymous()` (nếu thực sự cần) | Chỉ hiển thị cho guest, không phải route đăng nhập bắt buộc |
| Trang nhận diện nhớ đăng nhập | `rememberMe()` (ít dùng) | Chỉ phản ánh trạng thái được phục hồi bằng cookie |
| Xem profile, danh sách đơn hàng ít nhạy cảm | `authenticated()` nếu threat model cho phép | Remember-me có thể đủ cho trải nghiệm đọc; vẫn kiểm tra quyền tài nguyên |
| Đổi password/email hoặc thiết lập bảo mật | `fullyAuthenticated()` | Cookie dài hạn bị lộ không đủ để thay đổi trạng thái nhạy cảm |
| Duyệt thanh toán, xuất dữ liệu bí mật, cấp quyền admin | `fullyAuthenticated()` **và** role/permission/MFA/step-up thích hợp | Full login là điều kiện cần nhưng chưa đủ cho high-risk operation |

**Role không thay freshness.** Một `RememberMeAuthenticationToken` được phục hồi có thể tải lại `ROLE_ADMIN` từ user store. Chỉ `hasRole("ADMIN")` không ngăn được trường hợp này. Dùng composite `AuthorizationManagers.allOf(fullyAuthenticated(), hasRole(...))` hoặc policy tương đương. Với hành động cực nhạy cảm, full auth trong Spring Security vẫn chưa chắc là “vừa xác minh mật khẩu trong 5 phút” hoặc “đã MFA”: cần chứng cứ thời điểm/mức xác thực bổ sung, challenge riêng hoặc step-up.

**Lưu ý về API:** Browser dùng cookie có CSRF risk; `rememberMe()` phù hợp với form login/session browser. Stateless bearer JWT/OAuth2 resource server có trust model khác; không lấy `fullyAuthenticated()` làm proxy cho mức xác minh MFA hoặc tuổi token trong một API JWT mà chưa định nghĩa policy riêng.

## 8. Những sai lầm điển hình

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `if (authentication.isAuthenticated())` và coi là user thực | `AnonymousAuthenticationToken` cũng có thể mang flag true | Dùng `AuthenticationTrustResolver` hoặc Spring Security authorization DSL |
| Cho `authenticated()` bảo vệ đổi mật khẩu | Remember-me cũng có thể vượt qua | Dùng `fullyAuthenticated()` và thêm step-up nếu cần |
| Dùng `hasRole("ADMIN")` làm điều kiện duy nhất cho thao tác cực nhạy cảm | Admin nhớ đăng nhập vẫn có authority được tải lại | Kết hợp full login và role; bổ sung MFA/freshness policy |
| Cho rằng có cookie remember-me là full login | Cookie chỉ chứng minh nhận diện lại theo cơ chế remember-me | Phân biệt `RememberMeAuthenticationToken` và full token |
| Xem `.rememberMe()` là “ít nhất remember-me” | Rule này chỉ match trạng thái remember-me, không tự nhận full login | Dùng `.authenticated()` khi muốn nhận cả hai |
| Xem `.anonymous()` giống `permitAll()` | Full/remembered bị từ chối ở route anonymous-only | Dùng `permitAll()` cho trang công khai cần mở cho mọi người |
| Tắt CSRF do có remember-me cookie | Browser tự gửi cookie, có thể gây request giả mạo | Giữ CSRF cho tác vụ dùng cookie/session |
| Logout chỉ xóa cookie và kết luận token bị đánh cắp đã bị revoke | Hash-based remember-me token copy vẫn có thể hợp lệ | Đặt TTL ngắn, đổi password/key khi cần; persistent token store để quản lý revoke |
| Đặt secret key remember-me trong repository công khai | Kẻ tấn công có cơ hội giả mạo/kiểm tra token | Secret manager/env, rotation và quyền truy cập tối thiểu |
| Dùng `@WithMockUser` để “test remember-me” | Bỏ qua filter phát cookie và autoLogin | Login thật qua MockMvc rồi dùng cookie không session |
| Dùng chung `JSESSIONID` trong test và khẳng định remember-me đã được kích hoạt | Authentication vẫn đọc từ session full | Test request mới không gắn session, chỉ gửi remember-me cookie |
| Mất session nhưng vẫn giữ remember-me cookie không được giải thích UX | User tưởng đã logout hoàn toàn dù còn được nhận diện lại | Thống nhất logout/revoke, giải thích rõ trạng thái nhớ đăng nhập |

## 9. Bảo mật cookie và vòng đời đăng nhập

1. **HTTPS và cookie flags:** Dùng `Secure` trên production, `HttpOnly` để hạn chế JavaScript đọc cookie, `SameSite` theo luồng cross-site hợp lệ; thiết lập domain/path càng hẹp càng tốt. Các flag giúp giảm rủi ro nhưng không thay thế chống XSS/CSRF.
2. **Thời hạn hợp lý:** remember-me thường tồn tại lâu hơn session; phải có TTL, giám sát, cookie expiration và chính sách hủy khi đổi mật khẩu, khóa account hoặc rút quyền. Không để remember-me tồn tại vĩnh viễn.
3. **Khả năng thu hồi:** simple hash-based token phù hợp demo hoặc trường hợp rủi ro thấp nhưng không hỗ trợ server-side per-token revoke như persistent store. Nếu sản phẩm cần quản lý danh sách thiết bị/thu hồi một thiết bị, cần lưu trạng thái token phù hợp.
4. **Login/re-authentication:** chỉ dựa vào remember-me cho những nội dung được phép. Với `fullyAuthenticated()`, form login cần thực hiện lại xác thực tương tác; đừng dùng một redirect giả hoặc đổi kiểu token bằng cách tự set cờ authenticated.
5. **MFA/step-up:** với giao dịch rủi ro cao, thực hiện xác minh bổ sung (mật khẩu mới nhập, passkey, OTP/phishing-resistant MFA theo policy), và ghi nhận proof/freshness chính xác. `fullyAuthenticated()` chỉ phân biệt anonymous/remember-me/full trong Spring Security, không chứa toàn bộ bằng chứng assurance.
6. **Session fixation:** nếu remember-me tự tạo session mới trong quá trình autoLogin, các vấn đề session fixation/lifecycle vẫn cần được quản lý đúng cơ chế Spring Security. Không cho một cookie nhớ đăng nhập mở thẳng endpoint admin nhạy cảm.
7. **Đổi quyền account:** việc tải lại `UserDetails` có thể cập nhật authorities khi remember-me được dùng, nhưng chính sách quyền ở request vẫn phải kiểm tra lại bằng dữ liệu đã xác minh và policy đúng. Không tin role từ client gửi.
8. **Xử lý lỗi:** cookie hết hạn, lỗi chữ ký, user không tồn tại hoặc user bị disabled phải dẫn tới không khôi phục authentication; UI không nên bật thông báo tiết lộ quá nhiều về account hoặc token.

## 10. Checklist QA

- [ ] Phân biệt đúng anonymous, remember-me và full login; không dựa độc lập vào `Authentication.isAuthenticated()`.
- [ ] Hiểu `authenticated()` nhận remember-me + full, còn `fullyAuthenticated()` chỉ nhận full.
- [ ] Hiểu `anonymous()` và `rememberMe()` là chính sách **trạng thái cụ thể**, không phải alias cho `permitAll()` hoặc `authenticated()`.
- [ ] Remember-me cookie chỉ được cấp khi người dùng chọn opt-in (trừ khi policy chủ ý bật alwaysRemember).
- [ ] Khi session full login còn, request vẫn được nhận diện full; khi chỉ có cookie hợp lệ, request được nhận diện remember-me.
- [ ] Endpoint xem thông tin phù hợp có thể dùng `authenticated()`; endpoint đổi thông tin bảo mật yêu cầu `fullyAuthenticated()`.
- [ ] Endpoint admin nhạy cảm phải kiểm tra **cả** full login và role/permission; với rủi ro cao còn cần MFA/step-up.
- [ ] Test cookie thiếu/hỏng không biến thành account đã đăng nhập.
- [ ] CSRF vẫn bảo vệ form POST, logout và thao tác nhạy cảm dùng cookie.
- [ ] Remember-me secret được quản lý an toàn, cookie có flags và TTL phù hợp, có quy trình revoke và audit.
- [ ] Test MockMvc xác minh phát cookie, phục hồi authentication **không kèm session cũ**, và 302/403 theo policy.
- [ ] Thử thêm trên trình duyệt thật với HTTPS, session expiry, logout và cookie attributes.
- [ ] Không nhầm Remember-me Spring Security với token JWT stateless hay chứng cứ MFA đã hoàn thành.

### Tài liệu tham khảo

- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — AuthenticationTrustResolver](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html)
- [Spring Security 6.5 — AuthenticatedAuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthenticatedAuthorizationManager.html)
- [Spring Security 6.5 — RememberMeConfigurer](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/RememberMeConfigurer.html)
- [Spring Security 6.5 — MockMvc Security Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
