# Đăng xuất cục bộ không tự thu hồi mọi token hoặc phiên tại hệ thống danh tính ngoài

> **Module:** Spring Security - fundamentals  
> **Nhóm:** Đăng nhập và đăng xuất  
> **Thông điệp cốt lõi:** `POST /logout` của ứng dụng có thể xóa trạng thái đăng nhập **tại ứng dụng đó**, nhưng không mặc nhiên thu hồi access token, refresh token, ID token, session SSO ở Identity Provider (IdP) hay phiên của các ứng dụng khác.

## 1. Mục tiêu của bài học

Sau bài này bạn cần hiểu và giải thích được:

- Tại sao đã đăng xuất khỏi một Spring Boot application nhưng lần đăng nhập lại có thể diễn ra rất nhanh, không yêu cầu nhập mật khẩu khi IdP còn phiên SSO.
- `SecurityContext`, `HttpSession`, cookie phiên ứng dụng, cookie của IdP, access token và refresh token **không phải một đối tượng**.
- `LogoutFilter` của Spring Security xử lý những gì và đâu là giới hạn trách nhiệm của nó.
- Sự khác biệt giữa **local logout**, **OpenID Connect RP-Initiated Logout**, **OAuth 2.0 token revocation** và **logout liên ứng dụng** (front-channel/back-channel).
- Vì sao một JWT access token đã cấp vẫn có thể được Resource Server chấp nhận sau khi phiên browser tại ứng dụng bị xóa.
- Cách xây dựng ứng dụng Java 17+/Spring Security và bài test minh họa việc local logout **không tự gọi** hệ thống token bên ngoài.
- Cách thiết kế chính sách đăng xuất và kiểm thử đúng với yêu cầu “chỉ thiết bị này”, “ứng dụng này”, “mọi ứng dụng” hoặc “mọi thiết bị”.

## 2. Một người dùng có thể có nhiều trạng thái đăng nhập khác nhau

Hãy xem kiến trúc phổ biến:

~~~text
                     Trình duyệt
               /                    \
              v                      v
     Spring Boot App (RP)     Identity Provider (OP/IdP)
        Cookie app             Cookie đăng nhập SSO
        HttpSession            Phiên tại IdP
        SecurityContext        OAuth2/OIDC Authorization Server
              |                      |
              |     cấp token        |
              +<---------------------+
              |
              v
         Resource Server
       Kiểm tra access token

Các trạng thái/credential có vòng đời riêng.
~~~

Trong cùng một phiên sử dụng, các thành phần sau có thể cùng tồn tại:

| Thành phần | Ai thường quản lý? | Dùng để làm gì? |
| --- | --- | --- |
| Cookie session của ứng dụng, chẳng hạn `JSESSIONID` hoặc `SESSION` | Ứng dụng / Spring Session | Mang ID để tìm `HttpSession` của **ứng dụng** |
| `HttpSession` và `SecurityContext` | Spring Security + Servlet/Spring Session | Nhớ `Authentication` của người dùng giữa các request tới ứng dụng |
| Cookie đăng nhập của IdP | Hệ thống danh tính ngoài | Nhớ rằng user đã xác thực ở IdP, phục vụ SSO |
| **ID token** (OIDC) | IdP cấp, OIDC client tiêu thụ | Chứng thực thông tin đăng nhập/identity cho client theo OIDC |
| **Access token** (OAuth 2.0) | Authorization Server cấp | Cho phép client gọi API/Resource Server trong scope/thời hạn được cấp |
| **Refresh token** | Authorization Server cấp | Cho phép client lấy access token mới theo chính sách |
| Phiên của ứng dụng B | Ứng dụng B | Có thể độc lập với phiên ứng dụng A dù cùng IdP |

Đây là lý do cụm từ “đăng xuất” **không đủ rõ** để thiết kế bảo mật. Cần trả lời: đăng xuất **khỏi đâu**, **khỏi thiết bị nào**, **thu hồi credential nào** và **mức độ lan truyền sang các hệ thống khác** ra sao?

## 3. `POST /logout` mặc định của Spring Security Servlet làm những gì?

Với ứng dụng dùng form login và session, Spring Security cung cấp `LogoutFilter`. Khi CSRF protection đang bật, mặc định logout có ý nghĩa thay đổi trạng thái được xử lý bằng **HTTP POST** tới `/logout` với CSRF token hợp lệ. `GET /logout` có thể hiển thị trang xác nhận hỗ trợ POST.

Ví dụ cấu hình phổ biến:

~~~java
// Đoạn DSL ở bên trong cấu hình SecurityFilterChain.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults())
    .logout(Customizer.withDefaults());
~~~

Khi logout được thực hiện theo cấu hình mặc định phù hợp, các `LogoutHandler` có thể:

1. Vô hiệu hóa `HttpSession` của ứng dụng (`SecurityContextLogoutHandler`).
2. Làm sạch `SecurityContextHolderStrategy` và security context persistence của ứng dụng.
3. Xóa remember-me authentication/token liên quan nếu đã cấu hình.
4. Dọn CSRF token tương ứng (`CsrfLogoutHandler`).
5. Phát `LogoutSuccessEvent` và thực hiện `LogoutSuccessHandler`, thường redirect tới `/login?logout`.

**Những thao tác trên không có nghĩa:**

- Xóa cookie đăng nhập của IdP trên miền khác.
- Gửi revocation request tới OAuth 2.0 Authorization Server.
- Hủy mọi refresh token hoặc access token đã phát cho cùng tài khoản.
- Đăng xuất một ứng dụng khác vốn có session riêng.
- Xóa token trên thiết bị khác hoặc trong app mobile khác.
- Khiến một Resource Server tự động ngừng chấp nhận mọi JWT chưa hết hạn.

`LogoutFilter` chạy trong **security filter chain của ứng dụng hiện tại**. Nó không có quyền điều khiển cookie trên tất cả domain và không tự có thông tin của mọi token được phát hành ở hệ thống khác.

### CSRF của logout không nên bị bỏ qua

~~~html
<!-- Form minh họa cho ứng dụng server-rendered. Giá trị CSRF cần
     được template engine điền từ request thực; không hardcode. -->
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <button type="submit">Đăng xuất</button>
</form>
~~~

HTML trên là mẫu diễn giải, **không phải form production hoàn chỉnh**: token và tên tham số có thể được framework render khác nhau. Đừng biến logout thành GET tùy tiện hoặc tắt CSRF toàn ứng dụng chỉ để một nút bấm hoạt động. Trình duyệt cũng có thể bị tấn công *logout CSRF* nếu endpoint không được bảo vệ phù hợp.

## 4. Ba tình huống phải phân biệt rõ

### Tình huống A — Spring Boot form login thuần, chỉ có session của ứng dụng

~~~text
Browser -> App /login -> App session authenticated
Browser -> POST /logout -> App invalidate session
Browser -> /private -> yêu cầu đăng nhập lại
~~~

Nếu không có IdP, local logout có thể là đủ cho yêu cầu “đăng xuất khỏi ứng dụng này”. Nhưng nếu còn remember-me cookie, token ở một API khác hoặc session trên thiết bị khác, mỗi phần vẫn cần chính sách riêng.

### Tình huống B — Ứng dụng dùng OAuth2/OIDC Login với IdP SSO

~~~text
1. Browser vào App A -> chưa có local session.
2. App A chuyển hướng sang IdP.
3. User nhập mật khẩu ở IdP; IdP tạo SSO session cookie.
4. App A nhận kết quả OIDC, tạo local session.
5. User POST /logout ở App A.
6. App A xóa local session. Cookie phiên của IdP vẫn có thể còn.
7. User vào lại App A -> chuyển tới IdP -> IdP còn phiên SSO.
8. IdP có thể xác thực ngay mà không hỏi lại password.
9. App A tạo local session mới.
~~~

Người dùng nói “Tôi vừa đăng xuất mà bấm login lại không phải nhập password”. Điều này **không chứng minh** `LogoutFilter` thất bại. Có thể local logout đã thành công, nhưng **phiên tại IdP vẫn sống**; SSO nhanh là hành vi được thiết kế.

### Tình huống C — API sử dụng Bearer access token

~~~text
Client giữ access token (JWT hoặc opaque)
    |
    +-- Gọi API X: Authorization: Bearer <token>
    |
    +-- Xóa local app session / cookie
    |
    +-- Token cũ có thể còn nguyên hạn sử dụng
    |
    +-- Gọi API X lần nữa với chính token cũ
          |
          v
      Resource Server kiểm tra token theo policy riêng
~~~

Một Resource Server kiểu JWT thường xác minh chữ ký, issuer, thời hạn `exp`/`nbf` và các validation được cấu hình. Việc xóa session browser ở một OAuth2 client **không tự phát tín hiệu thu hồi token** tới tất cả Resource Server.

**Lưu ý:** Nếu Resource Server dùng token introspection hay một denylist có cập nhật revocation, kết quả có thể khác. Chính sách token revocation phụ thuộc kiến trúc thật, không suy đoán chỉ từ chuỗi “JWT” hoặc “logout thành công”.

## 5. Bảng ranh giới: hành động nào ảnh hưởng tới credential nào?

| Hành động | Local app session | Phiên SSO tại IdP | Access token đã cấp | Refresh token | App B có phiên riêng |
| --- | --- | --- | --- | --- | --- |
| `POST /logout` mặc định của App A | Thường bị vô hiệu hóa | Không tự động | Không tự động | Không tự động | Không tự động |
| Xóa cookie phiên App A trong browser | Browser mất ID App A; server session chưa chắc bị hủy | Không | Không | Không | Không |
| OIDC RP-Initiated Logout từ App A | Có thể kết hợp local logout | Yêu cầu IdP xử lý logout | Không bảo đảm thu hồi tất cả | Không bảo đảm thu hồi tất cả | Tùy IdP và cơ chế propagation |
| OAuth2 token revocation | Không mặc nhiên đổi local session | Không mặc nhiên xóa SSO cookie | Tùy token, server policy và cơ chế kiểm tra | Token được revoke có thể mất khả năng refresh | Không mặc nhiên |
| Global logout / “log out all devices” | Phải định nghĩa phạm vi | Phải phối hợp IdP | Cần chính sách token riêng | Cần chính sách token riêng | Cần phối hợp các RP |

**Đọc bảng theo nghĩa “không có bảo đảm tự động”**, không phải kết luận các sản phẩm IdP cụ thể không hỗ trợ chức năng nào. Một nhà cung cấp có thể cung cấp logout, session-management, token-revocation và global-sign-out API riêng; cách chúng ảnh hưởng tới từng token cần kiểm chứng theo tài liệu chính thức của nhà cung cấp đó.

## 6. Demo Java 17+ chạy được: local logout không xóa token ở kho bên ngoài

Để nhìn thấy **phạm vi tác dụng**, ví dụ Spring Boot sau có hai thành phần:

- Local form login/`HttpSession` do Spring Security quản lý thật.
- Một bean `ExternalTokenRegistry` **mô phỏng hệ thống token ở ngoài** để test có thể kiểm chứng nó không bị thay đổi khi local logout. Đây chỉ là *test double*; không phải IdP, không tự xác thực JWT và không phải một token store có thể dùng cho production.

Mục đích: kiểm thử local logout sạch local session, nhưng không tự gọi `revoke(...)` trên một hệ thống độc lập. Đối với hệ thống IdP thật, thay simulator bằng cơ chế giao tiếp chuẩn được kiểm soát.

**Phiên bản ví dụ:** JDK 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.x.

### 6.1. Cấu trúc project

~~~text
logout-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/logoutboundary/
    │   ├── LogoutBoundaryApplication.java
    │   ├── SecurityConfig.java
    │   ├── DemoController.java
    │   └── ExternalTokenRegistry.java
    └── test/java/demo/logoutboundary/
        └── LocalLogoutTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'logout-boundary-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot BOM quản lý phiên bản của các Spring dependencies. Không cần OAuth2 client dependency trong demo **form login thuần**; phần OIDC sau là cách mở rộng độc lập.

### 6.2. Main application

File `src/main/java/demo/logoutboundary/LogoutBoundaryApplication.java`:

~~~java
package demo.logoutboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutBoundaryApplication.class, args);
    }
}
~~~

### 6.3. Cấu hình Spring Security

File `src/main/java/demo/logoutboundary/SecurityConfig.java`:

~~~java
package demo.logoutboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

Cấu hình giữ CSRF mặc định. `POST /logout` với CSRF token hợp lệ làm việc với **local session của ứng dụng**. Không có dòng nào gửi HTTP request tới Authorization Server hoặc thu hồi remote token.

### 6.4. Endpoint yêu cầu local authentication

File `src/main/java/demo/logoutboundary/DemoController.java`:

~~~java
package demo.logoutboundary;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
~~~

### 6.5. Simulator cho trạng thái token bên ngoài

File `src/main/java/demo/logoutboundary/ExternalTokenRegistry.java`:

~~~java
package demo.logoutboundary;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class ExternalTokenRegistry {

    private final Set<String> activeTokens =
        ConcurrentHashMap.newKeySet();

    public ExternalTokenRegistry() {
        // Token giả, chỉ dùng trong test.
        activeTokens.add("demo-external-token");
    }

    public boolean isActive(String token) {
        return activeTokens.contains(token);
    }

    public void revoke(String token) {
        activeTokens.remove(token);
    }
}
~~~

Đây **không phải** một OAuth2 Authorization Server thực. Nó mô phỏng việc có một kho credential độc lập với session ứng dụng. Spring Security local logout không biết đến bean này và cũng không tự gọi `revoke()`.

### 6.6. MockMvc test bảo vệ đúng ranh giới

File `src/test/java/demo/logoutboundary/LocalLogoutTest.java`:

~~~java
package demo.logoutboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LocalLogoutTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ExternalTokenRegistry external;

    @Test
    void localLogoutDoesNotRevokeExternalToken() throws Exception {
        // Đăng nhập bằng form login thật của Spring Security.
        MvcResult login = mvc.perform(
                post("/login").with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);

        // Session đang authenticated và cho phép vào /private.
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));

        // Kho token "bên ngoài" vẫn có token giả.
        assertTrue(external.isActive("demo-external-token"));

        // Logout hợp lệ làm mất local session.
        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

        assertTrue(session.isInvalid());

        // Request mới không có local session phải đăng nhập lại.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());

        // Token ở registry độc lập KHÔNG bị revoke tự động.
        assertTrue(external.isActive("demo-external-token"));

        // Chỉ khi có hành động revoke riêng, registry mới đổi.
        external.revoke("demo-external-token");
        assertFalse(external.isActive("demo-external-token"));
    }
}
~~~

### 6.7. Chạy và giải thích kết quả

Từ project root, với JDK 17+ và Gradle 8.x:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng:** bài test duy nhất `localLogoutDoesNotRevokeExternalToken` thành công. Đây là **kỳ vọng từ mã ví dụ**, không phải kết quả đã thực thi trong bài viết.

Bằng chứng của test gồm ba mệnh đề độc lập:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Đăng nhập form rồi gọi `/private` bằng session đó | HTTP 200, body `hello alice` |
| `POST /logout`, rồi gọi `/private` bằng request mới | Redirect tới login; session cũ invalid |
| `external.isActive("demo-external-token")` ngay sau local logout | Vẫn `true` |
| Chỉ khi gọi `external.revoke(...)` | Chuyển thành `false` |

**Giới hạn quan trọng:** Token giả trong test không được gắn vào HTTP auth filter. Test chứng minh **ranh giới trách nhiệm** chứ không kiểm chứng thực tế một IdP cụ thể sẽ làm gì. Để chứng minh end-to-end trong production, phải kiểm tra access/refresh token và phiên IdP thật trước/sau logout bằng phương thức nhà cung cấp hỗ trợ.

## 7. OIDC RP-Initiated Logout: yêu cầu IdP đăng xuất qua browser

Khi ứng dụng sử dụng **OpenID Connect Login** và IdP hỗ trợ [RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html), ứng dụng (*Relying Party / RP*) có thể chuyển hướng trình duyệt tới endpoint logout của IdP (*OpenID Provider / OP*).

~~~text
Browser đã login cả App A và IdP
           |
           v
POST /logout tại App A
           |
           v
Local session App A bị invalidate
           |
           v
LogoutSuccessHandler chuyển hướng browser
  đến IdP end_session_endpoint
  với id_token_hint / post_logout_redirect_uri khi phù hợp
           |
           v
IdP xử lý yêu cầu logout theo chính sách
           |
           v
Browser có thể quay lại URL đã đăng ký
~~~

Đây là **một yêu cầu tới IdP**, không phải quyền lực tuyệt đối khiến tất cả ứng dụng hoặc token lập tức mất hiệu lực. Hệ thống IdP có thể yêu cầu xác nhận, có giới hạn liên ứng dụng, còn token đã cấp có vòng đời riêng.

### Spring Security hỗ trợ `OidcClientInitiatedLogoutSuccessHandler`

Đoạn cấu hình minh họa *thay thế* cho `SecurityConfig` ở demo phần 6, dành cho app đã có OAuth2/OIDC client registration và dùng `oauth2Login()`:

~~~java
// Đoạn tích hợp, không phải một class Java độc lập.
@Bean
SecurityFilterChain oidcSecurityFilterChain(
        HttpSecurity http,
        ClientRegistrationRepository clients) throws Exception {

    OidcClientInitiatedLogoutSuccessHandler oidcLogout =
        new OidcClientInitiatedLogoutSuccessHandler(clients);

    oidcLogout.setPostLogoutRedirectUri("{baseUrl}/logged-out");

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/logged-out").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout.logoutSuccessHandler(oidcLogout))
        .build();
}
~~~

Các type chính:

- `OidcClientInitiatedLogoutSuccessHandler` thuộc `org.springframework.security.oauth2.client.oidc.web.logout`.
- `ClientRegistrationRepository` thuộc `org.springframework.security.oauth2.client.registration`.
- `SecurityFilterChain`, `HttpSecurity`, `Customizer` và `@Bean` dùng các package Spring Security/Spring quen thuộc.

Để dùng đoạn này cần thêm `spring-boot-starter-oauth2-client`, đăng ký OIDC client và cấu hình issuer/client ID/secret phù hợp; IdP cần hỗ trợ `end_session_endpoint` hoặc metadata tương đương. **Đừng ghép hai bean SecurityFilterChain cho cùng các request mà không thiết kế thứ tự/scope.** Đây là một cấu hình thay thế, không phải phần thêm vào demo form login thuần.

`{baseUrl}/logged-out` là URI mẫu do Spring Security xây dựng từ request; URL post-logout phải được IdP cho phép/đăng ký trước. Đừng lấy một URL redirect tùy ý do client gửi để dùng làm post-logout destination.

### Các tham số của chuẩn OIDC

| Tham số | Ý nghĩa |
| --- | --- |
| `end_session_endpoint` | URL logout được IdP công bố trong discovery metadata |
| `id_token_hint` | ID token đã cấp để IdP nhận biết login/session liên quan (khuyến nghị) |
| `post_logout_redirect_uri` | Nơi browser có thể quay lại sau khi IdP xử lý, cần được đăng ký/cho phép |
| `state` | Giá trị opaque để RP đối chiếu khi quay lại, nếu luồng dùng tham số này |
| `client_id` | Có thể giúp xác định client trong một số trường hợp được chuẩn hỗ trợ |

Không xây dựng một “logout URL” bằng cách tự nối chuỗi token/URI mà bỏ qua validation state và redirect allowlist. Đặc biệt, ID token là dữ liệu nhạy cảm; cần xử lý qua cơ chế thư viện hỗ trợ, giảm log và lộ trong analytics/history.

### RP-Initiated Logout có đảm bảo global logout không?

Không. RP-Initiated Logout thông báo cho OP về yêu cầu logout từ RP. Để các ứng dụng B/C đồng bộ logout có thể cần **OIDC Front-Channel Logout** hoặc **Back-Channel Logout**, và từng RP phải hỗ trợ xử lý tín hiệu. Các token đã phát có thể còn hiệu lực theo chính sách access/refresh token và resource-server validation. Tách bạch **logout phiên SSO** với **token revocation**.

## 8. OAuth 2.0 Token Revocation: một cơ chế riêng

[OAuth 2.0 Token Revocation (RFC 7009)](https://www.rfc-editor.org/rfc/rfc7009) định nghĩa endpoint để client yêu cầu Authorization Server vô hiệu hóa token không còn cần thiết.

Ví dụ khái niệm về yêu cầu revoke refresh token:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=<refresh-token>&token_type_hint=refresh_token
~~~

**Đây là HTTP minh họa**, không phải endpoint cố định có ở mọi IdP và cũng không phải credentials thật. URL, client authentication, token type, rate limit, scopes và policy phải theo discovery/tài liệu của Authorization Server tương ứng.

### Revoke refresh token khác gì revoke access token?

- **Refresh token:** Nếu bị revoke thành công, client không còn được dùng chính refresh token đó để xin access token mới. Liên hệ với các access/refresh tokens khác phụ thuộc policy của Authorization Server.
- **Access token:** Một số server hỗ trợ revoke trực tiếp. Với opaque token và introspection, Resource Server có thể nhận biết token `active=false` sau revocation (có thể có cache/độ trễ).
- **Self-contained JWT access token:** Resource Server chỉ xác minh chữ ký/claims tại chỗ thường **không biết** rằng token đã bị revoke ở Authorization Server trước `exp`, trừ khi có denylist, introspection, sự kiện cập nhật trạng thái, key rotation hoặc cơ chế bổ sung.

RFC 7009 quy định hỗ trợ revoke refresh token; hỗ trợ access token được khuyến nghị tùy server. Chính sách thu hồi những token liên quan phụ thuộc Authorization Server. Ngay cả phản hồi HTTP 200 từ revocation endpoint cũng không phải bằng chứng một JWT cũ ở mọi Resource Server đã lập tức bị từ chối.

**Không nhầm hai mệnh đề:**

> “Không thể tiếp tục dùng refresh token để xin token mới.”  
> “Mọi access token đã cấp đều bị API từ chối ngay lập tức.”

Mệnh đề thứ nhất có thể đúng trong khi mệnh đề thứ hai còn sai cho tới khi access token hết hạn hoặc cơ chế từ chối sớm có hiệu lực.

### Client phải biết token nằm ở đâu

Một Spring OAuth2 Client có thể lưu `OAuth2AuthorizedClient` (access token, refresh token khi được cấp) trong một `OAuth2AuthorizedClientService` hoặc repository. Xóa local authorized client/token khỏi storage giúp ứng dụng không tiếp tục sử dụng chúng, nhưng **không mặc nhiên gửi revocation request** tới IdP. Ngược lại, gọi revocation endpoint là tương tác riêng với server đã phát token. Hai bước có trách nhiệm khác nhau.

Nếu ứng dụng không giữ refresh token, nó cũng không thể tùy tiện revoke một refresh token của thiết bị khác. “Logout mọi thiết bị” thường cần API và quyền quản trị/session-management riêng của IdP.

## 9. JWT Resource Server: vì sao token cũ còn dùng được?

Ví dụ client đã có JWT access token có thời hạn còn 10 phút. Khi client gửi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <jwt-access-token>
~~~

Resource Server có thể dùng Spring Security `oauth2ResourceServer().jwt()` và `JwtDecoder` để xác minh signature, issuer, expiry, not-before cùng các policy bổ sung được cấu hình.

~~~text
Tại t0: Authorization Server cấp JWT, exp = t0 + 10 phút
Tại t1: Người dùng logout khỏi Spring MVC client
Tại t2: Client cũ hoặc tác nhân giữ JWT gửi request đến API
Tại t2: Nếu JWT vẫn hợp lệ và API không kiểm tra revocation,
       Resource Server vẫn có thể chấp nhận request
Tại t3: JWT hết hạn -> bị từ chối theo exp validation
~~~

Để hỗ trợ yêu cầu thu hồi nhanh:

1. Dùng access token sống ngắn và refresh token rotation/revocation phù hợp.
2. Với opaque token, cân nhắc token introspection và chính sách cache phù hợp.
3. Với JWT, nếu cần từ chối tức thời, thiết kế denylist hoặc kiểm tra trạng thái cấp phát/phiên tại API, đánh đổi hiệu năng và tính sẵn sàng.
4. Khi bị lộ signing key hoặc sự cố nghiêm trọng, key rotation và incident response có vai trò riêng; không xem đổi key là thao tác logout thông thường.
5. Định nghĩa propagation/caching delay tối đa chấp nhận được, rồi kiểm thử token cũ sau từng loại logout.

**Không yêu cầu tắt JWT signature/expiry validation**, cũng không coi “xóa token khỏi localStorage” là revocation ở server: một bản sao token đã bị đánh cắp vẫn có thể được sử dụng tới khi không còn được chấp nhận.

## 10. Front-channel và back-channel logout cho hệ thống SSO nhiều RP

Khi cùng user đăng nhập App A, App B và App C qua một IdP, nhiều phiên tồn tại song song:

~~~text
                 Identity Provider
               /          |         \
              v           v          v
            App A        App B      App C
          session A    session B  session C
~~~

Nếu user logout ở App A:

- Local logout chỉ ảnh hưởng session A.
- RP-Initiated Logout có thể đề nghị IdP kết thúc SSO session.
- IdP có thể phát thông báo logout tới App B/C nếu hỗ trợ cơ chế liên ứng dụng và các RP đã tích hợp.
- Front-channel dựa vào trình duyệt và các điều kiện cookie/cross-site/browser behavior nên có thể không tin cậy tuyệt đối.
- Back-channel dùng thông báo server-to-server (logout token hoặc thông điệp theo chuẩn/hệ thống) để RP invalidates session tương ứng; cần xác thực thông điệp, replay protection và mapping session chính xác.

**Back-channel logout không đồng nghĩa tự revoke mọi access token:** nếu API chỉ dùng JWT tự kiểm tra, cần chính sách revocation/introspection riêng.

Nếu yêu cầu bảo mật là “rút toàn bộ quyền của tài khoản bị khóa trong vài giây”, chỉ đăng xuất browser không đủ. Cần tích hợp IdP, API và session/token state theo SLA đã định.

## 11. Xác định đúng phạm vi theo yêu cầu sản phẩm

Một chữ “Logout” trên nút bấm có thể ẩn bốn ý định khác nhau:

| Ý định | Phạm vi mong muốn | Điều kiện kỹ thuật |
| --- | --- | --- |
| Đăng xuất khỏi **ứng dụng A tại tab/browser này** | Xóa phiên A và credential local liên quan | Spring Security logout; clear cookie/session; test A |
| Đăng xuất khỏi **ứng dụng A trên mọi thiết bị** | Hủy tất cả session A của user | Session registry/index/store và API invalidate multiple sessions |
| Đăng xuất khỏi **SSO IdP** | Kết thúc phiên tại IdP theo chính sách provider | OIDC RP-Initiated Logout hoặc API vendor tương đương |
| Đăng xuất khỏi **mọi ứng dụng và thu hồi token** | Invalidate sessions A/B/C, refresh/access tokens trong phạm vi xác định | IdP propagation + token revocation + resource-server strategy + test |

Thiết kế phải trả lời:

- Có cần revoke **một refresh token**, một token family, tất cả tokens của account hay tất cả app sessions?
- Có thể mất bao lâu để propagation tới Resource Servers?
- Phải báo người dùng “đăng xuất cục bộ thành công nhưng không đăng xuất SSO” hay chặn kết quả logout khi IdP lỗi?
- Có thiết bị khác đang hoạt động, hoặc user có nhiều browser profiles không?
- IdP có hỗ trợ OIDC RP-Initiated Logout, front-/back-channel logout và token revocation cho loại client này không?
- “Logout all” có yêu cầu quyền cao hơn “Logout this session” không?

**Không tuyên bố “đã đăng xuất khỏi mọi nơi” khi ứng dụng mới chỉ invalidate local session.** Hãy dùng lời nhắn giao diện phù hợp đúng mức đảm bảo đã thực hiện.

## 12. Xử lý lỗi khi IdP hoặc revocation endpoint không sẵn sàng

Luồng logout có thể thất bại một phần:

~~~text
User bấm logout
    |
    v
Ứng dụng hủy local session thành công
    |
    v
Gửi logout/revoke request tới IdP
    |
    +-- Thành công -> cập nhật trạng thái theo bảo đảm thật
    |
    +-- Timeout / 5xx / network error
          |
          v
    Local session vẫn nên được xử lý an toàn
    Ghi trạng thái "remote logout chưa xác nhận"
    Retry hoặc quy trình xử lý theo chính sách
    Không báo sai "all devices signed out"
~~~

Tùy quy trình, bạn có thể thực hiện local cleanup trước hoặc phối hợp với bước remote. Tránh phụ thuộc IdP availability đến mức khi remote request timeout, ứng dụng để nguyên local session mà người dùng tưởng đã logout.

Nếu retry revocation, cần tôn trọng yêu cầu provider, thời hạn token, client authentication và idempotency semantics. Không log raw access/refresh tokens vào error messages. Một hệ thống theo dõi cần ghi correlation ID, user/session reference đã được ẩn danh hóa phù hợp, loại token, provider, thời điểm và quyết định mà không tiết lộ bí mật.

## 13. Test end-to-end: không chỉ nhìn thấy trang login

**Test local logout** chứng minh việc trong App A: session không còn authenticated, protected route bị chặn, remember-me xử lý đúng, CSRF và cookie settings hợp lệ.

**Test SSO logout** phải dùng IdP test realm/sandbox thật. Dùng lại cùng browser profile:

1. Login App A qua IdP.
2. Xác nhận cookie/session ở App A và SSO session ở IdP.
3. Logout App A bằng cơ chế local-only.
4. Thử login App A lại, ghi nhận có/không nhập credential. Nếu SSO session còn, login có thể nhanh mà không cần password.
5. Bật/tích hợp RP-Initiated Logout và thử lại; kiểm tra browser thực sự tới `end_session_endpoint`, IdP có xử lý và redirect về URI đã đăng ký.
6. Nếu có App B, kiểm tra session B có bị invalidate hay không theo cam kết của IdP và integration front-/back-channel.
7. Dùng access token đã cấp **trước logout** gọi Resource Server trong môi trường test; ghi nhận còn hợp lệ tới khi nào.
8. Thử refresh token cũ sau revocation; nó không được cấp access token mới khi chính token đó đã được revoke thành công và propagation hoàn tất.
9. Thử trường hợp IdP unavailable, timeout hoặc revocation 5xx; đo rõ local cleanup và thông báo cho user.

### Ma trận nghiệm thu

| Tình huống | Bước kiểm tra | Kết quả nên có theo chính sách |
| --- | --- | --- |
| Local logout App A | Gọi protected route bằng cookie A cũ | Không còn authenticated ở App A |
| IdP SSO chưa logout | Thử login lại App A qua browser đã login IdP | Có thể tái xác thực không cần password; **không được coi là lỗi local logout** |
| OIDC RP logout | Browser truy cập end-session endpoint và quay về RP | Đúng quy trình nhà cung cấp, không open redirect |
| Access token JWT cũ | Gửi lại token trước khi `exp` | Chấp nhận/từ chối theo chính sách revocation đã công bố |
| Refresh token cũ | Dùng sau khi revoke | Bị từ chối khi revocation có hiệu lực |
| App B có session độc lập | Vào App B sau App A logout | Theo thiết kế front-/back-channel hoặc session revocation, không suy đoán |
| Global logout | Thử thiết bị khác và API | Mọi thành phần trong phạm vi cam kết không còn cấp quyền |
| IdP/revoke timeout | Thực hiện logout khi IdP lỗi | Local state và thông báo phản ánh đúng kết quả, không báo thành công toàn cục giả |
| CSRF/logout | Thử POST không có CSRF token ở app dùng session | Request bị từ chối theo cấu hình CSRF |

**Test chỉ thấy redirect tới login là chưa đủ** để chứng minh SSO session, refresh token hoặc JWT cũ đã chết. Phải test đúng từng credential trên đúng hệ thống chấp nhận credential đó.

## 14. Các lỗi phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Coi `POST /logout` là global sign-out | Nó xử lý local security state theo mặc định | Phân loại local/IdP/token/session logout |
| Xóa cookie App A rồi tưởng cookie IdP cũng bị xóa | Cookie bị giới hạn bởi domain/path/security model | Dùng OIDC/logout API của IdP |
| Xóa refresh token chỉ trong database client | Server phát token có thể vẫn chấp nhận bản sao đã cấp | Dùng revocation endpoint với policy cụ thể |
| Revoke refresh token rồi tin JWT access token đã chết | JWT Resource Server offline có thể vẫn tin token tới `exp` | Ngắn hạn, introspection/denylist hoặc revocation strategy |
| Dùng `GET /logout` không CSRF | Dễ gây logout CSRF hoặc khác cơ chế mặc định | Dùng POST + CSRF token hợp lệ theo framework |
| Ghi raw token/session ID trong log | Credential có thể bị lộ và replay | Che/redact secrets, audit metadata tối thiểu |
| Chỉ test App A, không test App B | Không phát hiện sessions liên ứng dụng còn sống | Test multi-RP/browser/device |
| Báo “signed out everywhere” khi IdP đang timeout | Cam kết giao diện vượt khả năng thực tế | Trả kết quả trung thực và quy trình retry |
| Cho rằng `clearAuthentication(true)` xóa mọi token | Chỉ liên quan local security context | Tách token revocation và IdP session logout |
| Tự nối `post_logout_redirect_uri` từ tham số do user nhập | Nguy cơ redirect tới miền không đáng tin | Dùng redirect URI được đăng ký/allowlist |
| Thiếu chính sách khi tài khoản bị khóa hoặc quyền bị thu hồi | Phiên/token cũ có thể tiếp tục được chấp nhận | Session invalidation + token strategy + API enforcement |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng logout khỏi App A, bấm Login lại được vào ngay không cần mật khẩu. Có phải Spring Security không xóa session?

**Đáp án:** Chưa chắc. `LogoutFilter` có thể đã xóa local session; nhưng SSO session ở IdP còn hiệu lực nên IdP có thể xác thực lại và App A tạo session mới.

**Câu 2.** Xóa cookie `JSESSIONID` có thu hồi JWT mà client đã gửi vào `Authorization: Bearer` không?

**Đáp án:** Không tự động. Cookie và JWT access token là credential khác nhau, được kiểm tra tại những điểm khác nhau.

**Câu 3.** Revoke refresh token thành công có chứng minh access token JWT đã cấp không còn gọi API được không?

**Đáp án:** Không. Resource Server tự xác minh JWT có thể tiếp tục chấp nhận đến `exp` nếu không có cơ chế từ chối sớm.

**Câu 4.** `OidcClientInitiatedLogoutSuccessHandler` dùng làm gì?

**Đáp án:** Giúp Spring Security OAuth2/OIDC client chuyển hướng trình duyệt tới logout endpoint của OpenID Provider theo RP-Initiated Logout, khi provider/configuration hỗ trợ; không phải cơ chế auto-revoke mọi token.

**Câu 5.** Test local logout đã thấy `/private` redirect login. Có thể báo “all devices signed out” chưa?

**Đáp án:** Không. Phải kiểm chứng tất cả các phiên, thiết bị, RP và token trong phạm vi cam kết.

**Câu 6.** Khi IdP timeout trong lúc logout, điều gì nên được thể hiện với user?

**Đáp án:** Thông báo đúng trạng thái: local logout có thể đã hoàn tất nhưng remote/global logout chưa được xác nhận; không báo đã thu hồi mọi phiên/token nếu chưa có bằng chứng.

## 16. Checklist triển khai

- [ ] Sản phẩm phân biệt rõ **logout this app**, **logout IdP** và **logout all devices**.
- [ ] Local session bị invalidate; SecurityContext, remember-me, CSRF và cookie được xử lý đúng nhu cầu.
- [ ] Logout endpoint dùng POST/CSRF cho ứng dụng browser stateful khi cơ chế này áp dụng.
- [ ] OIDC RP-Initiated Logout chỉ được bật khi provider hỗ trợ và redirect URI được đăng ký.
- [ ] Access/refresh token revocation được tích hợp **riêng**, đúng endpoint/credential/token policy của IdP.
- [ ] Resource Servers có chính sách accept/reject token đã revoke rõ ràng; hiểu JWT local validation và propagation delay.
- [ ] Các ứng dụng liên quan hỗ trợ và kiểm tra front-/back-channel logout nếu cam kết SSO/global logout.
- [ ] Không lộ token, session ID, ID token hoặc client secret trong logs/URL không kiểm soát.
- [ ] Khi IdP hoặc revocation thất bại, UI/audit phản ánh đúng kết quả từng bước.
- [ ] Có integration test sau logout sử dụng lại **cookie cũ, refresh token cũ và access token cũ** trên các hệ thống tương ứng.

## 17. Tổng kết và tài liệu chính thức

**Đăng xuất cục bộ có phạm vi cục bộ.** Spring Security có thể vô hiệu hóa local session và SecurityContext, nhưng không mặc nhiên xóa cookie SSO tại IdP hoặc thu hồi mọi OAuth2/OIDC token. Muốn mở rộng phạm vi, phải tích hợp đúng cơ chế: OIDC RP-Initiated Logout cho phiên IdP, front-/back-channel logout cho các RP liên quan, OAuth2 Token Revocation cho token, và chiến lược Resource Server để từ chối credential cũ đúng SLA.

Tài liệu tham khảo:

- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — OAuth2 Login Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [OpenID Connect — RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
