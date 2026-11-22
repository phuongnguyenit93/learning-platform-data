# Session fixation, token replay và ranh giới của từng biện pháp giảm thiểu trong Spring Security

## 1. Hai kiểu tấn công có tên gần nhau nhưng khác điểm xuất phát

**Session fixation** (cố định phiên) xảy ra khi kẻ tấn công **biết hoặc áp đặt một session ID trước lúc nạn nhân đăng nhập**, rồi hy vọng ứng dụng giữ nguyên định danh phiên ấy sau khi nâng mức tin cậy từ anonymous lên authenticated. Kẻ tấn công không nhất thiết phải trộm cookie **sau** đăng nhập: họ có thể tạo một phiên anonymous do server cấp, tìm cách đặt ID đó vào browser nạn nhân, chờ nạn nhân login, sau đó thử sử dụng ID đã biết.

**Token replay** (phát lại token) xảy ra khi một bên dùng lại **giá trị credential/bằng chứng đã quan sát hoặc đánh cắp**, thường ở thời điểm khác hoặc từ tác nhân khác, để tiếp tục truy cập hoặc xác thực. Token có thể là session cookie, OAuth access token dạng Bearer, refresh token, remember-me cookie, authorization code, OTT/magic link hoặc challenge response. Mỗi loại có vòng đời khác nhau: có token **được thiết kế dùng nhiều lần** cho đến khi hết hạn (session cookie và đa số access tokens), trong khi có loại **phải tiêu thụ một lần** (authorization code, OTP/OTT theo chính sách, refresh token khi rotation).

**Kết luận cốt lõi:** thay session ID khi login giải quyết rủi ro **biết trước ID của phiên sẽ được nâng quyền**; nó không tự vô hiệu hóa cookie phiên hiện tại nếu cookie đó **bị đánh cắp sau khi login**. Ngược lại, PKCE ở OAuth hoặc cơ chế anti-replay của refresh token không tự thay cho session fixation protection của HTTP session.

| Câu hỏi | Session fixation | Replay cookie/token |
| --- | --- | --- |
| Kẻ tấn công cần gì? | Một ID đã biết/có thể gắn vào browser **trước login** | Bản sao cookie/token đang hoặc từng có hiệu lực |
| Thời điểm quan trọng | Chuyển mức tin cậy **trước → sau authentication**, nâng quyền, switch principal | **Sau khi** token được cấp hoặc đã được thấy |
| Điều kiện để khai thác | Phiên sau login tiếp tục chấp nhận **ID cũ** | Verifier vẫn tin credential đó hoặc thiếu kiểm tra single-use |
| Hàng rào trực tiếp | **Rotate/change session ID** ở boundary login/privilege change | Bảo vệ token khỏi lộ, TTL, revoke, replay detection, sender-constraining hoặc one-time consume tùy loại |
| Điều không tự giải quyết | Cookie phiên **mới** bị đánh cắp | Session đã bị cố định trước login; bỏ sót issuer/audience/CSRF/authorization |
| Kiểm thử bắt buộc | ID cũ không được truy cập phiên authenticated sau login | Dùng lại chính token/credential ở phiên hoặc tác nhân khác theo policy phải thất bại hay được xử lý đúng |

Không nên đánh đồng replay với “gửi lại HTTP GET”: người dùng bấm refresh trang trong cùng session thường là hợp lệ. Replay là **lạm dụng lại credential/bằng chứng** trái với mục tiêu bảo mật. Một Bearer token thông thường **có thể được gửi nhiều lần hợp lệ** cho các API cho đến hết hạn. Bài toán là **ngăn người khác dùng token bị trộm**, không phải mặc định “mỗi access token dùng một lần”.

## 2. Vẽ ranh giới: anonymous session, authenticated session, Bearer token

### 2.1. Session fixation từ trước lúc đăng nhập

```text
Attacker                   Browser nạn nhân                Ứng dụng Spring MVC
   |                            |                              |
   |-- mở trang -> nhận SID=X -------------------------------->|
   |<---------------------- Cookie SID=X ----------------------|
   |
   | (bằng lỗ hổng khác, cố đặt SID=X vào browser nạn nhân)
   |--------------------------->|                              |
   |                            | GET /login; cookie SID=X     |
   |                            |----------------------------->|
   |                            | POST /login; password đúng   |
   |                            |----------------------------->|
   |                            |                         authenticated
   |                            |                         rotate X -> Y
   |                            |<--- Set-Cookie SID=Y --------|
   |                            |                              |
   |-- GET /account; SID=X ----------------------------------->|
   |<------------ KHÔNG authenticated --------------------------|
   |                            |                              |
   |                            | GET /account; SID=Y         |
   |                            |----------------------------->|
   |                            |<----- authenticated ---------|
```

**Tính chất cần đạt:** authentication của nạn nhân gắn với **Y**, không với ID **X** đã biết trước. Session ID cũ không được dùng để lấy principal của nạn nhân. Nếu người dùng tự làm chủ session Y mà Y sau đó bị kẻ tấn công đánh cắp, session fixation protection **không còn là biện pháp đủ**.

Với Servlet hiện đại, Spring Security mặc định bật session fixation protection; chiến lược phổ biến là `HttpServletRequest.changeSessionId()`. Nó đổi ID của **cùng session**, nên **không có nghĩa xóa sạch mọi session attribute**. Ứng dụng cần kiểm soát riêng các thuộc tính pre-authentication như checkout data, redirect target, pending MFA, cờ “verified” do code tự tạo.

### 2.2. Phát lại cookie sau đăng nhập là kịch bản khác

```text
Browser A đăng nhập thành công: cookie SID=Y
    |
    | (XSS, malware, proxy/log leak, browser extension độc hại,
    |  session store compromise hoặc lỗ hổng khác làm lộ Y)
    v
Attacker gửi Cookie: SID=Y tới /account

Nếu server vẫn còn session Y và không có binding/ràng buộc khác:
    -> RỦI RO session hijacking / replay Y
    -> Rotate lúc login trước đó KHÔNG làm Y vô hiệu ngay
```

Cookie session trên thực tế là một **bearer credential**: server tin người sở hữu ID còn hợp lệ. Các cờ `HttpOnly`, `Secure`, `SameSite`, HTTPS và kiểm soát XSS giảm một số **đường lộ/sử dụng** cookie, nhưng không biến cookie thành token ràng buộc mật mã với thiết bị. Với XSS, `HttpOnly` ngăn JavaScript đọc cookie, nhưng script độc hại vẫn có thể gửi **request cùng origin** bằng cookie đang được browser tự gửi.

### 2.3. JWT access token không đồng nghĩa session ID

Một Resource Server sử dụng `oauth2ResourceServer().jwt()` sẽ xác minh Bearer JWT trên từng request. Nó **không mặc định sử dụng HTTP session** để biết JWT đã được dùng trước đó hay chưa. JWT hợp lệ về chữ ký, `iss`, `aud`, `exp` và scope có thể tiếp tục được dùng nhiều lần. Muốn chống **trộm + phát lại access token**, cần các lớp khác như sender-constrained token (DPoP/mTLS, nếu cả issuer/client/resource server đều hỗ trợ), kiểm soát vòng đời và ngăn rò token. Tạo session mới khi login web không làm một access token JWT độc lập hết hiệu lực.

## 3. Session fixation: nguồn gốc, các tình huống và điều kiện khai thác

### 3.1. Một ID có thể được “ấn định” thế nào?

Attacker cần khiến browser nạn nhân sử dụng session ID mà attacker đã biết hoặc kiểm soát. Những đường thường được phân tích trong threat model:

- Ứng dụng chấp nhận session ID trên URL hoặc tham số query (URL rewriting/`;jsessionid=...`), khiến link được chia sẻ mang session identity hoặc ID do attacker chuẩn bị.
- Lỗi cookie scope/domain/path hoặc subdomain chưa tin cậy làm browser nhận cookie với session ID do nguồn khác thiết lập (**cookie tossing/cookie injection**).
- HTTP không có TLS, proxy/edge cấu hình sai hoặc mixed content cho phép ảnh hưởng cookie/token trong quá trình trao đổi.
- Session ID do ứng dụng tự tạo có entropy thấp, predictable hoặc còn chấp nhận một giá trị chưa từng được server phát.
- Ứng dụng giữ nguyên pre-login session ID sau khi authentication/role elevation, làm một ID đã biết từ trước trở thành ID của authenticated user.

Không phải bất kỳ `JSESSIONID` attacker tự gõ cũng thành một session server chấp nhận. Servlet container/framework thường quản lý ID ngẫu nhiên và chỉ tin ID thuộc session đã cấp. Tấn công fixation phụ thuộc một **đường chèn/đồng bộ ID thực tế**; kiểm thử nên chỉ rõ cơ chế thử nghiệm, không khẳng định mọi ứng dụng dễ bị fixation chỉ vì dùng session cookie.

### 3.2. Biện pháp trọng tâm: rotate tại boundary

Theo OWASP Session Management Cheat Sheet, khi **mức đặc quyền thay đổi**, ứng dụng cần **renew session ID**, đặc biệt khi anonymous → authenticated, user role tăng hoặc switch principal. Trong Spring Security, cấu hình session fixation protection chủ yếu áp dụng tại luồng **authentication interactive thành công**. Nếu dự án tự nâng quyền bằng controller hoặc có custom login filter, phải đảm bảo chiến lược áp dụng đúng đường đi đó; không giả định bất kỳ request nào sửa `SecurityContext` cũng tự trigger mọi session strategy.

Dòng thời gian:

| Mốc | Browser giữ cookie | Server biết session | Kỳ vọng |
| --- | --- | --- | --- |
| Trước login | SID_A | Anonymous session SID_A | Chỉ quyền công khai |
| Login thành công | SID_B mới | Authenticated session SID_B | SID_B gắn principal; SID_A không còn quyền |
| Attacker thử SID_A | SID_A | Không truy xuất phiên authenticated SID_B | Bị chặn/anonymous |
| Nạn nhân dùng SID_B | SID_B | Phiên hợp lệ | Được vào route phù hợp role |
| Sau logout | Cookie bị xóa/expired; session invalidated | SID_B mất hiệu lực server-side | SID_B không được truy cập lại |
| Login lại | SID_C mới | Session mới | Không tái sử dụng SID_B |

Chuyển principal Alice → Bob trong cùng browser cần chính sách reset **những bằng chứng và quyền gắn với Alice**, không chỉ đổi `Authentication.getName()` mà giữ nguyên cache quyền/MFA state của Alice. Session ID rotation là một phần lifecycle; còn authorization, pending factors và account binding phải được re-check.

## 4. Spring Security 6.x Servlet: ba chiến lược fixation protection

Spring Security có DSL `http.sessionManagement(session -> session.sessionFixation(...))`. Các chiến lược thông dụng được mô tả trong tài liệu chính thức:

| Strategy | Hành vi | Khi dùng / giới hạn |
| --- | --- | --- |
| `changeSessionId()` | Gọi `HttpServletRequest.changeSessionId()` từ Servlet container; **đổi ID nhưng giữ session object/attributes** | **Mặc định** trên Servlet 3.1+; phương án phổ biến với Spring Boot 3 / Tomcat hiện đại |
| `migrateSession()` | Tạo session mới và **copy tất cả session attributes** sang session mới | Mặc định của container Servlet cũ 3.0 trở xuống; không “dọn sạch” dữ liệu pre-auth |
| `newSession()` | Tạo session mới “sạch”, nhưng Spring Security vẫn chuyển một số thuộc tính liên quan đến security | Dùng khi muốn hạn chế carry-over, vẫn phải test flash messages/CSRF/shopping cart và integration |
| `none()` | Tắt session fixation protection | **Không nên dùng** cho cookie-based interactive login, tăng rủi ro fixation |

**Phạm vi của `changeSessionId()`:** đây là thay đổi ID của session, không phải **invalidate mọi session khác**, không đồng nghĩa “rotate tất cả remember-me tokens”, không có chức năng revoke OAuth/JWT access tokens. Việc Java Servlet API gọi `changeSessionId()` có thể phát `HttpSessionIdListener`; Spring Security còn có `SessionFixationProtectionEvent`. Nếu bạn nghe cả hai loại sự kiện, tránh đếm đôi.

### Cấu hình tối thiểu, rõ mục tiêu

Trong ứng dụng Spring Boot 3.x, Java 17+, Servlet/Spring MVC, tạo `SecurityConfig.java`:

```java
package com.example.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fix -> fix.changeSessionId()))
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));
        // Không tắt CSRF trong ứng dụng web dùng cookie.
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
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build());
    }
}
```

Ví dụ chỉ có account demo Alice và password `demo-password` được băm BCrypt khi khởi động. **Không dùng password tĩnh và InMemoryUserDetailsManager cho hệ thống thật**: dùng database, password hash, chính sách account lock/MFA/rate-limit phù hợp.

Với cấu hình Spring Security/Servlet hiện đại, `changeSessionId()` là mặc định nên đoạn DSL này **làm rõ ý định**, không phải bản vá bổ sung độc lập. Nếu ứng dụng đã tắt session fixation protection hoặc tự thực hiện login/upgrade, cần xem lại chính xác đường authentication và test.

### Controller tạo anonymous session và xem danh tính

Tạo `SessionController.java` cùng package. Chỉ trả một thông báo, **không trả session ID ra response**:

```java
package com.example.session;

import java.security.Principal;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/public/session")
    public String createPreLoginSession(HttpServletRequest request) {
        request.getSession(true); // phục vụ test ID trước login
        return "anonymous session initialized";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return "Hello " + principal.getName();
    }
}
```

Ví dụ này là một cấu hình ứng dụng Spring, không chạy độc lập bằng `javac` nếu thiếu dependency và class `@SpringBootApplication`. Để thử end-to-end, tạo project Boot 3 từ Spring Initializr với `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test`, `spring-security-test`, đặt các class cùng package được scan, chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) rồi test browser trên HTTPS/test local.

## 5. Test session fixation: không nhầm rotation với logout

### 5.1. Chuỗi kiểm thử thực tế

1. Browser A tải `GET /public/session`, ghi nhận cookie `JSESSIONID=SID_A` **chỉ trong môi trường test**, chưa đăng nhập.
2. Browser A gửi `POST /login` với mật khẩu đúng và CSRF hợp lệ. Quan sát browser có `JSESSIONID=SID_B`, **SID_B khác SID_A**.
3. Browser A gửi `GET /me` với SID_B, nhận `Hello alice`.
4. Browser B/curl cookie jar độc lập chỉ mang **SID_A** gọi `GET /me`. Kỳ vọng: không vào được tài nguyên đã authenticated, thường redirect login hoặc HTTP 401 tùy entry point.
5. Browser B thử gửi SID_B đã được lộ trong **test fixture** và có thể được nhận nếu không có binding bổ sung. Đây là test **giới hạn bảo vệ**: session rotation không ngăn replay của cookie hiện hành.
6. Browser A logout theo HTTP method/CSRF của ứng dụng; trong server phải invalidate SID_B. Kiểm SID_B cũ không truy cập được, không chỉ kiểm `Set-Cookie: JSESSIONID=;...` ở browser.

**Đừng đặt session ID thật của môi trường production vào log, request inspector công khai hoặc ticket.** Trong automated test nội bộ có thể so ID trong bộ nhớ; chỉ in boolean rotated, không dump cookie.

### 5.2. Test MockMvc kiểm rotate ID khi login

Tạo `src/test/java/com/example/session/SessionFixationTest.java` trong Spring Boot project ở mục 4:

```java
package com.example.session;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rotatesSessionIdWhenUserLogsIn() throws Exception {
        MvcResult initialized = mvc.perform(get("/public/session"))
                .andExpect(status().isOk())
                .andReturn();
        MockHttpSession beforeSession =
                (MockHttpSession) initialized.getRequest().getSession(false);

        assertThat(beforeSession).isNotNull();
        String oldId = beforeSession.getId();

        MvcResult login = mvc.perform(post("/login")
                    .session(beforeSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession afterSession =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(afterSession).isNotNull();
        assertThat(afterSession.getId()).isNotEqualTo(oldId);

        mvc.perform(get("/me").session(afterSession))
                .andExpect(status().isOk());
    }
}
```

Điểm cần lưu ý:

- Kiểm tra ID **trước** khi POST; nếu chỉ giữ reference tới cùng `MockHttpSession` và so `beforeSession.getId()` sau login, có thể bạn đang so chính cùng object đã đổi ID, làm test sai.
- `MockMvc` kiểm filter/session trong môi trường test, nhưng **không chứng minh servlet container + cookie jar + reverse proxy ở production** đã thật sự loại mọi đường chấp nhận ID cũ. Bổ sung browser/E2E test với **hai cookie jars** và HTTPS.
- Nếu test thông qua `@WithMockUser` hoặc `.with(user("alice"))`, user đã được giả lập authenticated và có thể **không chạy login authentication success/session fixation strategy**. Phải submit form login thật như trên.
- Khi login bị sai password nhưng response vẫn redirect về trang lỗi, test chỉ dùng status 302 chưa đủ. Assert thêm `GET /me` trả đúng principal và cookie/session thay đổi như mong muốn.
- Nếu cấu hình custom `AuthenticationFilter` hoặc custom controller làm login, cần gọi `SessionAuthenticationStrategy` đúng lúc và lưu `SecurityContext` qua `SecurityContextRepository`; việc chỉ set `SecurityContextHolder` không đảm bảo persistence/correct rotation trong Spring Security 6+.

## 6. Token replay: phải xác định **loại token** trước khi chọn biện pháp

“Token replay” không phải một tấn công có duy nhất một cách chặn. Cần hỏi bốn câu: token này được sinh để **dùng một lần hay nhiều lần**, ai được nhận, cách ràng buộc với người gửi, và điều kiện nào làm token hết hiệu lực?

| Token/credential | Thiết kế sử dụng | Replay có nghĩa gì? | Biện pháp trực tiếp | Giới hạn |
| --- | --- | --- | --- | --- |
| **JSESSIONID cookie** | Có thể dùng nhiều HTTP requests trong một session | Người khác dùng cookie hiện hành đã trộm | HttpOnly/Secure/SameSite, TLS, XSS defense, rotate login, server-side invalidate/timeout, reauth | Rotate lúc login không ngăn cookie mới bị trộm; cookie không tự là proof-of-possession |
| **Simple remember-me cookie** | Có thể tự đăng nhập lại giữa các session | Cookie bị chụp có thể auto-login từ user agent khác | Hạn dùng, secret key, password change, cookie protection; đánh giá không bật ở route nhạy cảm | Spring docs lưu ý hash-based remember-me cookie bị chụp có thể sử dụng từ user agent khác tới expiry |
| **Persistent remember-me series/token** | Chuỗi token theo persistent store, có rotation khi sử dụng | Cookie cũ xuất hiện sau rotation hoặc token bị đánh cắp | Rotate token trong persistent repository, detect mismatch, revoke series/credential, bảo vệ storage | Rủi ro race/false positive cần test; không đồng nghĩa session fixation protection |
| **OAuth Bearer access token** | Dùng nhiều lần tới expiry/scope/resource | Token bị trộm dùng ở API bởi actor khác | HTTPS, short TTL, audience/scope, hạn rò, sender constraint DPoP/mTLS nếu hỗ trợ | JWT chữ ký đúng không chứng minh người gửi là chủ hợp pháp; `jti` một mình không làm replay bị từ chối |
| **Refresh token** | Dùng để xin access token mới | Attacker và client đều dùng lại một refresh token | **Rotation + reuse detection + revoke family** hoặc sender-constrained token | Một implementation chỉ đổi refresh token mà không phát hiện reuse/khóa family vẫn có rủi ro; concurrency phải được xử lý |
| **Authorization code** | Dùng **một lần** tại token endpoint | Kẻ trộm đổi code lấy token hoặc gửi lại code | Code one-time, short TTL, client/redirect binding, **PKCE S256** | PKCE bảo vệ exchange khi attacker không có verifier; không bảo vệ access token đã được cấp |
| **OAuth state / OIDC nonce** | Gắn request/response hoặc ID Token với login transaction | Callback/ID Token cũ đưa vào flow khác | Random, transaction/session binding, compare, one-time lifecycle | Không thay TLS/PKCE, không ngăn API Bearer access token replay |
| **OTT/magic link** | Phát hành một lần, tiêu thụ đúng một lần | Gửi lại link/mã sau khi đã sử dụng | TTL, **atomic consume**, binding với account, tránh email scanner consume GET | Link bị trộm **trước khi dùng** vẫn có thể bị attacker dùng trước |
| **TOTP/HOTP** | Mã theo time window/counter, không tự một lần nếu server không lưu state | Gửi lại mã trong window hoặc sử dụng counter cũ | Chống reuse bằng last-used step/counter, atomic update, rate limits | Clock skew/retry policy ảnh hưởng, không dùng lại cơ chế OTT DB mà thiếu thiết kế |
| **WebAuthn response** | Assertion ký cho challenge/request cụ thể | Submit assertion cho challenge đã dùng hoặc sai origin/RP | Challenge random, TTL, one-use, origin/RP ID, chữ ký, credential binding | Sign counter không phải chỉ số tuyệt đối trên mọi authenticator |
| **CSRF token** | Chứng minh request form nằm trong security context/browser đã phát | Reuse token form có thể hợp lệ theo policy | Check CSRF trên state-changing requests, SameSite bổ trợ | CSRF token của Spring **không mặc nhiên là one-time token**; không chống trộm access token |
| **Business idempotency key** | Định danh operation để tránh ghi thanh toán lặp | Submit lại cùng payment request | Dedupe/idempotency ở DB/payment layer | Không chứng minh identity/token ownership, không thay authentication |

**Một access token Bearer hợp lệ có thể được dùng 100 lần hợp lệ** trong một phiên làm việc, nên một replay detector “cứ thấy JWT lần hai là reject” thường làm vỡ protocol. Đối với access token, anti-replay đúng nghĩa cần sender-constraint hoặc thiết kế stateful riêng với điều kiện chi phí/hành vi rõ ràng.

## 7. JWT và Bearer access token: chữ ký đúng không chống token theft

### 7.1. Mô hình Resource Server

Khi API được cấu hình Spring Security:

```java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt());
```

thư viện sẽ xác minh JWT signature theo trust/key config và validator của bạn. Muốn bảo vệ API đúng cách, phải giới hạn `issuer-uri` (issuer đáng tin), `aud` (API nhận token), `exp`/`nbf`, thuật toán phù hợp và scope/roles/tenant. Một token JWT đã ký đúng nhưng cấp cho **API khác** không được xem là đủ.

**Tuy nhiên:** các kiểm tra chữ ký, issuer, audience, expiry **không phân biệt** chủ sở hữu thật với attacker có cùng chuỗi Bearer token. Với API chấp nhận `Authorization: Bearer T`, attacker biết T và T còn hạn có thể dùng T nếu không có ràng buộc/deny bổ sung. `jti` là định danh token; nếu server không lưu/truy vấn trạng thái đã dùng/revoked, `jti` **không tự tạo replay detection**.

Đối với OAuth2 JWT access token, session fixation setting ở form-login web chain cũng **không hủy JWT đã phát**; hai hệ thống token có trust store/lifecycle khác nhau.

### 7.2. Short-lived access token và revoke

TTL ngắn giới hạn **thời gian** một token bị trộm có thể tiếp tục hoạt động, nhưng không ngăn replay **trong cửa sổ còn hiệu lực**. Đối với JWT self-contained, logout phía browser không mặc nhiên invalidate token ở mọi Resource Server nếu server chỉ validate chữ ký/expiry. Để revoke trước expiry cần một cách kiểm tra trạng thái: denylist `jti`, introspection/opaque tokens, event-driven revocation, sender-constraint hoặc chiến lược xác thực phù hợp.

**Denylist** có chi phí cache/database, đồng bộ nhiều node, TTL cleanup và rủi ro fail-open khi kho trạng thái bị lỗi. **Introspection** mang lại kiểm soát trạng thái tập trung nhưng tăng network dependency. Không có “một dòng code logout” biến mọi JWT ở mọi service thành invalid ngay.

### 7.3. Sender-constrained access tokens: DPoP và mTLS

Theo **OAuth 2.0 Security BCP RFC 9700**, Authorization Server/Resource Server nên cân nhắc sender-constrained access tokens, như:

- **Mutual TLS (mTLS, RFC 8705):** token bị ràng buộc với chứng chỉ/key của client; Resource Server cần kiểm proof ở kết nối phù hợp.
- **DPoP (RFC 9449):** client giữ private key, tạo proof JWT riêng cho mỗi HTTP request có method `htm`, target URI `htu`, thời gian `iat`, ID duy nhất `jti` và hash access token `ath` khi dùng token. Server xác minh chữ ký và proof binding cùng anti-replay window. Bearer token lấy trộm **mà không có private key** không đủ.

**Giới hạn:** sender-constraint không cứu được nếu attacker lấy cả access token **lẫn private key** hoặc thực thi request trong browser/process đang giữ key (ví dụ XSS). DPoP chỉ giúp khi Authorization Server **cấp token ràng buộc** và Resource Server **thực sự kiểm tra proof**, không phải chỉ thêm header `DPoP` vào request. Cần quản lý nonce, TTL, replay cache/`jti`, canonical target URI/reverse proxy và key lifecycle. Spring Security resource server có thể cần custom/config phù hợp để thực thi DPoP; **không khẳng định bật `.jwt()` mặc định sẽ kiểm DPoP**.

## 8. Refresh token rotation: cơ chế replay detection khác session ID rotation

Refresh token dùng để đổi lấy access token mới, vì vậy vòng đời thường dài hơn access token. Với OAuth public client, RFC 9700 yêu cầu refresh token **được sender-constrain hoặc dùng refresh token rotation**.

Một refresh token family:

```text
Client được cấp RT1
    |
    | POST /token grant_type=refresh_token, refresh_token=RT1
    v
Authorization Server (atomic)
    -> invalidates RT1
    -> issues RT2 + new access token
    -> remembers RT1 belongs to RT-family-F

Client dùng RT2 -> issues RT3, RT2 becomes invalid

Attacker gửi lại RT1:
    -> RT1 đã invalid => detect potential reuse/compromise
    -> revoke active token/family hoặc thực hiện response theo policy
    -> buộc client đăng nhập lại khi cần
```

**Ranh giới:** rotation giúp **phát hiện** một token cũ được dùng lại, nhưng không cho biết chắc actor nào là attacker. Server không thể quyết định “client hay attacker” chỉ qua token RT1 cũ. Nếu bị reuse, cần phản ứng bảo mật như thu hồi active refresh token/family. Điều kiện atomic ở token endpoint rất quan trọng: hai refresh requests đồng thời với cùng RT1 **không được cùng thành công**. Cần quy định/grace policy cho network retry và tránh false positive, nhưng grace phải có giới hạn và không biến token cũ thành vô hạn lần dùng.

**Đừng nhầm:**

- `sessionFixation().changeSessionId()` đổi **HTTP session ID** sau interactive login.
- **Refresh token rotation** đổi **OAuth refresh credential** khi client xin token mới.
- **Signing-key rotation** đổi khóa ký JWT và ảnh hưởng việc verify signature, không tự revoke JWT còn hạn khi cả khóa cũ vẫn được tin cậy.
- **CSRF token rotation** (nếu chính sách làm như vậy) bảo vệ browser request context, không thay cho ba loại trên.

## 9. Browser/cookie: thuộc tính bảo vệ và giới hạn thực tế

### 9.1. Secure, HttpOnly và SameSite

Đối với session cookie:

| Thuộc tính | Giảm nguy cơ | Không tự giải quyết |
| --- | --- | --- |
| `Secure` | Browser chỉ gửi cookie trong kết nối HTTPS, tránh lộ ở HTTP | XSS, malware, các nguồn trộm token khác |
| `HttpOnly` | JavaScript thông thường không đọc được cookie qua `document.cookie` | XSS vẫn có thể phát request same-origin dùng cookie |
| `SameSite=Lax/Strict` | Giảm cross-site cookie inclusion trong nhiều tình huống CSRF | XSS, same-site cross-origin attack và các luồng cross-site đặc biệt |
| `Path` và `Domain` hẹp | Giảm nơi cookie được gửi/nhận; tránh chia sẻ tràn sang subdomain không tin | Cookie theft ở đúng scope |
| Prefix `__Host-` khi phù hợp | Ràng buộc cookie Secure, Path=/ và không có Domain theo browser rule | Không biến cookie thành proof-of-possession |
| TTL/idle/absolute timeout phía server | Giới hạn thời gian session còn được chấp nhận | Replay trong thời hạn còn hiệu lực |

Với Spring Boot 3 web app, có thể cấu hình các thuộc tính cookie từ server và Spring Session nếu dùng; kiểm tra `Set-Cookie` tại browser/proxy thật vì behavior phụ thuộc deployment:

```yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
      timeout: 30m
```

Đây là **cấu hình minh họa** cho HTTPS production; trên localhost HTTP, cookie `Secure` có thể không được browser gửi, khiến bạn thấy đăng nhập “mất phiên”. Khi ứng dụng sử dụng IdP/OIDC callback qua cross-site, `SameSite=Strict` hoặc cấu hình Lax không phù hợp với flow redirect/POST binding có thể gây lỗi; phải thiết kế/test chính sách cookie theo luồng thật và cơ chế CSRF, không mặc định một giá trị phù hợp tất cả.

**Timeout 30m** thường là idle timeout của servlet session; OWASP còn khuyên xem xét **absolute timeout** độc lập. Không kết luận `server.servlet.session.timeout: 30m` tự tạo hạn tối đa 30 phút kể từ lúc login, vì hoạt động có thể gia hạn idle session.

### 9.2. HTTPS và HSTS

HTTPS chống đọc/sửa lưu lượng trên đường truyền khi TLS kết thúc ở đúng endpoint đáng tin. HSTS giúp browser giảm nguy cơ downgrade sang HTTP cho domain đã nhận chính sách. Nhưng reverse proxy TLS termination, log header, client JS, database session store, email magic link và phần mềm độc hại vẫn là các đường lộ credential khả dĩ. TLS **không** thay session rotation hoặc replay detection.

### 9.3. CSRF không phải replay của Bearer token

- **CSRF:** browser nạn nhân tự gửi cookie đăng nhập tới website thật khi bị dụ tương tác từ website khác. Attacker thường **không cần biết cookie**. Spring Security CSRF token kiểm **nguồn/ngữ cảnh request state-changing**.
- **Session hijack/replay:** attacker có bản sao cookie và gửi trực tiếp. CSRF token của nạn nhân có thể không giúp nếu attacker đã chiếm browser hoặc lấy được cookie/token cùng dữ liệu khác.
- **JWT Bearer dùng trong Authorization header:** browser không tự thêm header `Authorization: Bearer ...` cho trang web khác giống cookie session. Rủi ro CSRF phụ thuộc cách client lưu/gửi token. Nếu dùng cookie để mang token hoặc auto-authenticated request, vẫn cần phân tích CSRF.

Spring Security mặc định bật CSRF cho web app sử dụng cookie và form login. **Đừng tắt CSRF chỉ để test POST /login hoặc /logout nhanh**. Test phải gửi form hidden CSRF token/cookie đúng.

## 10. Remember-me và logout: cookie phiên không phải cookie persistent login

Spring Security có hai kiểu remember-me chính:

1. `TokenBasedRememberMeServices` tạo cookie dạng hash/signature từ username, expiry, password và key. Tài liệu Spring cảnh báo cookie bị trộm có thể dùng từ **user agent khác** cho đến khi hết hạn (hoặc password/key thay đổi).
2. `PersistentTokenBasedRememberMeServices` dùng `PersistentTokenRepository` chứa series/token, chẳng hạn JDBC. Cơ chế này có thể rotate token trên auto-login và phát hiện một số mismatch. Cần test đồng thời, persistence, logout/revocation và token theft; không xem persistent remember-me là một trong những session IDs.

Logout điển hình:

- Invalidate **HTTP session** phía server và xóa cookie `JSESSIONID` ở client; xóa cookie riêng không đủ nếu session server vẫn sống.
- Khi đã bật remember-me, cần gọi đúng logout handlers/revoke persistent remember-me state, không chỉ xóa JSESSIONID.
- Nếu web app còn phát **OAuth access/refresh tokens**, logout session MVC không mặc nhiên revoke token ở Authorization Server/Resource Server.
- Thay password hoặc khóa account có thể đòi invalidate các sessions và remember-me credentials hiện có, tùy chính sách; đừng chỉ rotate ID của một session rồi coi mọi phiên khác đều an toàn.

Một ví dụ phân biệt: người dùng logout A, nhưng B có access token JWT độc lập còn hạn. Nếu API chỉ verify JWT, B có thể tiếp tục dùng token cho tới expiry hoặc khi hệ thống áp dụng revoke mechanism. Thất bại ở đây là **thiết kế revocation**, không phải lỗi session fixation.

## 11. Kiểm thử theo ma trận: hàng rào nào phải chặn?

| ID | Threat/test | Tiền điều kiện | Thao tác | Kỳ vọng đúng |
| --- | --- | --- | --- | --- |
| F01 | Session fixation trước login | Anonymous SID_A, login thành công | So ID trước/sau | SID_B khác SID_A |
| F02 | Dùng ID cũ | SID_A đã được thay | Browser thứ hai gửi SID_A tới /me | Không authenticated |
| F03 | Session mới | SID_B sau login | Browser thật dùng SID_B | Authenticated đúng user |
| F04 | Cookie theft sau login | SID_B bị lộ có kiểm soát trong test | Browser thứ hai dùng SID_B | Có thể còn vào nếu không ràng buộc bổ sung; chứng minh **giới hạn fixation protection** |
| F05 | Logout invalidate | SID_B còn hoạt động | POST /logout có CSRF, rồi thử SID_B | Không authenticated |
| F06 | Switch user | Alice session, chuyển Bob | Dùng lại pre-switch ID/attributes | Không lộ Alice factors/roles; rotate/recheck khi đổi đặc quyền |
| F07 | Missing CSRF | Browser cookie session | POST state-changing thiếu CSRF | Bị chặn bởi CSRF, không side effect |
| R01 | Access JWT hợp lệ | Token issued for API A | Gửi nhiều GET hợp lệ | Cho phép **dùng lặp** đúng design của Bearer token |
| R02 | Stolen Bearer | Token API A bị sao chép | Actor khác gửi lại token | Có thể được nhận nếu chỉ có Bearer; cần ngăn theft/sender constraint/revoke |
| R03 | Wrong audience | JWT đúng chữ ký, aud=API B | Gửi tới API A | 401 invalid_token |
| R04 | Expired JWT | JWT hết exp | Gửi tới API A | 401 |
| R05 | Revoked JWT | jti trong denylist đã sync | Gửi lại JWT dù còn exp | 401 nếu Resource Server thực thi denylist |
| R06 | Refresh replay | RT1 đã đổi thành RT2 | Gửi RT1 lần nữa | Detect reuse, revoke active family theo chính sách |
| R07 | Concurrent refresh | Hai calls RT1 cùng lúc | Race hai token exchanges | Tối đa một RT1 thành công |
| R08 | OTT replay | OTT T đã tiêu thụ | POST T trong session khác | Thất bại |
| R09 | Concurrent OTT | Hai POST cùng T từ hai sessions | Race trong DB | Tối đa một consume success |
| R10 | Authorization code replay | Code K đã đổi | POST K lần hai | Token endpoint từ chối |
| R11 | Code interception | Attacker có K, thiếu PKCE verifier V | Đổi K lấy token | Từ chối khi S256 enforced |
| R12 | Wrong OIDC nonce | ID Token thuộc login khác | Submit token | OIDC client từ chối |
| R13 | WebAuthn replay | Assertion cho challenge cũ | Submit lại | Fails challenge verification |
| R14 | Business duplicate payment | Idempotency key đã dùng | POST payment giống trước | Không tạo payment mới ngoài policy |

**Cách đọc kết quả:** Test F04/R02 có thể cho thấy credential vẫn được chấp nhận, **không phải khuyến nghị để mặc kẻ tấn công dùng**. Chúng là **negative demonstration** chứng minh giới hạn một lớp bảo vệ, nhờ đó lập yêu cầu bổ sung. Bài test không nên dump cookie/secret, chỉ dùng tài khoản test cô lập. Trên hệ thống thật, never replay credentials của người dùng khác.

**Khi test anti-replay phải có hai tác nhân/sessions.** Nếu cùng session đã authenticated, gửi lại GET /me 200 không phải proof token OTT bị replay; chỉ chứng tỏ session hoạt động đúng. Đặt mỗi credential trong đúng lifecycle và kiểm số lần backend thật cho phép tiêu thụ token.

## 12. Java 17 độc lập: mô hình trước/sau rotation và token một lần

File `SessionReplayLab.java` dưới đây chạy bằng **JDK 17+ thuần**, không cần Spring. Nó minh họa:

- Trước login session anonymous có ID A.
- Login đổi A thành B, ID A không còn được truy cập như Alice.
- Nếu ID B bị lộ **sau login**, mô hình bearer session vẫn chấp nhận B (giới hạn của anti-fixation).
- Ticket/OTT dùng một lần có TTL, owner binding, replay và concurrent consume.
- Token của Bob không được dùng để xác minh Alice.

Đây là **mô hình học tập**, không phải servlet container hay production authentication server. ID thực được sinh bằng CSPRNG, nhưng demo không xây cookie browser, không xác minh mật khẩu, không có storage phân tán và không triển khai JWT.

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class SessionReplayLab {

    record Session(String principal) {}
    record Ticket(String owner, Instant expiresAt) {}

    private static final SecureRandom RANDOM = new SecureRandom();
    private final ConcurrentHashMap<String, Session> sessions =
            new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Ticket> tickets =
            new ConcurrentHashMap<>();

    static String randomSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    String createAnonymousSession() {
        String id = randomSecret();
        sessions.put(id, new Session(null));
        return id;
    }

    String loginAndRotate(String anonymousId, String principal) {
        // Mô phỏng password/interactive authentication đã thành công.
        Session old = sessions.remove(anonymousId);
        if (old == null || old.principal() != null) {
            return null;
        }
        String newId = randomSecret();
        sessions.put(newId, new Session(principal));
        return newId;
    }

    boolean canRead(String sessionId, String user) {
        Session s = sessions.get(sessionId);
        return s != null && Objects.equals(user, s.principal());
    }

    String issueTicket(String user, Instant expiry) {
        String code = randomSecret();
        tickets.put(code, new Ticket(user, expiry));
        return code;
    }

    boolean consumeTicket(String code, String expectedUser, Instant now) {
        Ticket t = tickets.get(code);
        if (t == null || !Objects.equals(t.owner(), expectedUser)) {
            return false;
        }
        if (!now.isBefore(t.expiresAt())) {
            tickets.remove(code, t);
            return false;
        }
        // remove(key, value) bảo đảm tại most one success trong một JVM.
        return tickets.remove(code, t);
    }

    public static void main(String[] args) throws InterruptedException {
        SessionReplayLab lab = new SessionReplayLab();
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String before = lab.createAnonymousSession();
        System.out.println("anonymousAsAlice=" +
                lab.canRead(before, "alice"));

        String after = lab.loginAndRotate(before, "alice");
        System.out.println("rotated=" + !before.equals(after));
        System.out.println("oldIdAsAlice=" +
                lab.canRead(before, "alice"));
        System.out.println("newIdAsAlice=" +
                lab.canRead(after, "alice"));

        // Kẻ tấn công biết ID MỚI có thể replay nếu không có lớp khác.
        System.out.println("stolenNewIdStillWorks=" +
                lab.canRead(after, "alice"));

        String ticket = lab.issueTicket("alice", now.plusSeconds(60));
        System.out.println("ticketFirst=" +
                lab.consumeTicket(ticket, "alice", now));
        System.out.println("ticketReplay=" +
                lab.consumeTicket(ticket, "alice", now));

        String expired = lab.issueTicket("alice", now.plusSeconds(5));
        System.out.println("ticketExpired=" +
                lab.consumeTicket(expired, "alice", now.plusSeconds(6)));

        String bobCode = lab.issueTicket("bob", now.plusSeconds(60));
        System.out.println("otherPrincipal=" +
                lab.consumeTicket(bobCode, "alice", now));

        String shared = lab.issueTicket("alice", now.plusSeconds(60));
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger accepted = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                gate.await();
                if (lab.consumeTicket(shared, "alice", now)) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };
        new Thread(attempt).start();
        new Thread(attempt).start();
        gate.countDown();
        done.await();
        System.out.println("concurrentTicketSuccess=" + accepted.get());
    }
}
```

Chạy trong thư mục chứa file:

```bash
javac SessionReplayLab.java
java SessionReplayLab
```

Stdout **xác định**:

```text
anonymousAsAlice=false
rotated=true
oldIdAsAlice=false
newIdAsAlice=true
stolenNewIdStillWorks=true
ticketFirst=true
ticketReplay=false
ticketExpired=false
otherPrincipal=false
concurrentTicketSuccess=1
```

Ý nghĩa: `rotated=true` và `oldIdAsAlice=false` minh họa session fixation protection. `stolenNewIdStillWorks=true` **không phải một lỗ hổng trong chương trình demo cần “sửa” bằng cách giữ ID cũ**: nó cho thấy một bearer session ID còn hợp lệ có thể bị lạm dụng nếu bị trộm. `ticketReplay=false` và `concurrentTicketSuccess=1` minh họa **atomic consume** cho credential được thiết kế dùng một lần. Chúng bảo vệ các đối tượng khác nhau.

**Giới hạn lab:** class `SessionReplayLab` không dùng `HttpServletRequest.changeSessionId()`, CSRF, HTTP cookie, TTL cho session hay multi-node DB. Mẫu session rotation trong lab là **delete/put** của map, chỉ để giải thích, không copy thành `SessionAuthenticationStrategy` production. Phải dùng cơ chế tích hợp của Spring Security.

## 13. Kiểm thử refresh token rotation với trạng thái server

Để triển khai OAuth refresh token rotation cần **Authorization Server** có khả năng lưu family và trạng thái token, không phải chỉ Resource Server giải mã JWT. Bất biến giao dịch:

```text
Initial:
  family=F, active=RT1, revoked=false

POST refresh RT1:
  atomic check RT1 is active and family F not revoked
  invalidate RT1, issue RT2, mark RT2 active
  response access_token + refresh_token RT2

POST refresh RT1 again:
  detect reuse of inactive RT1
  flag family F compromised, revoke active RT2 or apply
  documented incident policy; audit without raw token

POST refresh RT2 after family was revoked:
  reject
```

Kiểm thử tối thiểu:

1. RT1 dùng lần đầu thành công và trả RT2; access token vẫn phải có issuer/audience/scope đúng.
2. RT1 dùng lại thất bại và gây phản ứng compromise/family revocation (theo chính sách).
3. Hai requests RT1 thực hiện đồng thời, chỉ một transaction được quyền chuyển active từ RT1 sang RT2. Tránh test chỉ chạy tuần tự rồi tuyên bố concurrency safe.
4. Request trễ hoặc retry có thể gây false-positive; chính sách xử lý collision/grace phải được đánh giá riêng, không cho RT1 dùng lại vô hạn.
5. Khi nghi token bị đánh cắp, revoke family có thể khiến client hợp pháp buộc login lại; cần thông điệp UX và audit.
6. Nếu token sender-constrained, verify proof key/certificate ở cả issuance và reuse path; đừng coi có token trong database là đủ.

Không lưu refresh token plaintext trong log hoặc instrumentation. Lưu hash/token family ID, expiry, client identity và revoke reason phù hợp; nguyên tắc atomicity phải được bảo đảm bởi DB transaction/locking hoặc conditional updates **trên tất cả node**.

## 14. Attack-mitigation matrix: chọn đúng lớp bảo vệ

| Biện pháp | Session fixation **trước login** | Cookie stolen **sau login** | Access JWT bị sao chép | Refresh token replay | One-time token replay |
| --- | --- | --- | --- | --- | --- |
| Rotate `JSESSIONID` khi login | **Trực tiếp chặn** ID pre-login bị nâng quyền | Không trực tiếp | Không | Không | Không |
| Cookie `HttpOnly` | Giảm đọc cookie bằng JS | Giảm một đường trộm | Chỉ khi JWT cất trong cookie và phù hợp | Tùy nơi lưu | Không trực tiếp |
| Cookie `Secure` + HTTPS | Giảm chiếm/chèn session trên mạng | Giảm network theft | Giảm token leak qua mạng | Giảm token leak qua mạng | Giảm link/mã bị nghe lén |
| `SameSite` + CSRF protection | Không thay rotation | Không bảo đảm nếu attacker đã có cookie | Phụ thuộc cách client gửi token | Không | Có thể giúp chặn CSRF ở form nhận |
| Idle/absolute session timeout | Rút ngắn cửa sổ tấn công | **Giới hạn thời gian** | Không | Không | Không |
| JWT signature + issuer + aud + exp | Không | Không với session cookie | **Bắt buộc validity** nhưng không phân biệt người gửi đã trộm | Không thay rotation | Không |
| Short-lived access JWT | Không | Không | Giảm cửa sổ replay | Không trực tiếp | Không |
| `jti` denylist / introspection | Không | Không | Có thể revoke/kiểm state nếu thực thi | Có thể áp dụng state | Tùy thiết kế |
| DPoP/mTLS sender constraint | Không | Không, trừ thiết kế đặc biệt | **Giảm replay bởi actor không có key** | Có thể giảm theo binding | Không mặc định |
| Refresh token rotation + reuse detect | Không | Không | Không trực tiếp | **Trực tiếp** | Không |
| Atomic consume + token expiry | Không | Không (session cần nhiều requests) | Không mặc định phù hợp Bearer JWT | Trực tiếp nếu rotating credential được thiết kế | **Trực tiếp** |
| PKCE S256 | Không | Không | Không với access token đã cấp | Không | Trực tiếp với code exchange (không phải magic link) |
| Business idempotency | Không | Không | Không | Không | Ngăn side effect trùng, không chứng minh identity |

**Sai lầm nghiêm trọng:** bật một biện pháp rồi tuyên bố “chống replay mọi loại token”. Mỗi lớp có **đối tượng, điểm kiểm và điều kiện** riêng. Một số lớp giảm *xác suất bị trộm*, một số giới hạn *thời gian bị lợi dụng*, một số *phát hiện reuse* và một số *ràng buộc với người gửi*. Hãy ghi rõ mục tiêu khi đánh giá security posture.

## 15. Lỗi thường gặp khi cấu hình Spring và kiểm thử

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Login xong SID vẫn giữ nguyên | Đã tắt fixation protection, custom login không gọi strategy, test đo sai object | Bật changeSessionId; test ID snapshot trước/sau |
| Dùng SID cũ vẫn vào như user | Server vẫn chấp nhận ID trước login, session store mapping lỗi, proxy/cookie scope | Kiểm tra Servlet session mapping và security chain |
| Test rotation fail dù cấu hình đúng | So reference `MockHttpSession` sau khi nó đã đổi ID | Lưu chuỗi oldId **trước** login |
| Logout xong SID cũ còn dùng được | Chỉ xóa cookie client, không invalidate session server-side | Logout handlers, server session invalidate, integration test |
| Cookie HttpOnly mà XSS vẫn thao tác được | HttpOnly chặn đọc, không chặn same-origin requests | Sửa XSS, CSP, CSRF và authorization |
| Tắt CSRF vì API dùng JWT | Cùng ứng dụng vẫn có cookie-based form login, CSRF còn áp dụng | Tách filter chains/API vs web, giữ CSRF nơi cần |
| JWT đúng chữ ký nhưng actor khác dùng được | Bearer token bị trộm, không sender-constrained/revoked | Giảm rò, TTL, DPoP/mTLS nếu khả thi, revoke |
| JWT có jti nhưng vẫn replay được | Không kiểm jti state | Dùng denylist/replay store khi đúng use case |
| Refresh RT1 vẫn dùng được nhiều lần | Không rotate/atomic hoặc reuse detection chưa bật | Implement rotate+family compromise hoặc sender constrain |
| SameSite=Strict làm OIDC callback mất session | Cookie không gửi trong cross-site flow phù hợp | Cân nhắc Lax/None+Secure và CSRF/OAuth state theo flow |
| Rotate signing key mà JWT cũ vẫn dùng | Public key cũ còn trong JWKS và JWT chưa hết exp | Đây là key rotation overlap, không phải token revocation |
| Persistent remember-me vẫn auto login sau logout | Token repository/cookie chưa được revoke đúng | Kiểm tra remember-me logout service và persistent tokens |
| Session attribute pre-auth được giữ | changeSessionId/migrateSession không xóa attributes | Clear/stamp pending state và quyền theo principal |
| Reuse OTT hai request đồng thời đều được | Store không đảm bảo atomic consume | DB transaction/conditional update, concurrency test |
| Hai Pod accept/deny khác nhau | Token/session cache hay revoke policy không đồng bộ | Shared store, atomic updates, refresh/invalidation strategy |
| HTTP 302 được coi là pass | Redirect sang login/challenge, không phải authenticated 200 | Assert principal, state change, side effect, eventual destination |
| JWT in log hoặc session ID trong URL | Sensitive logging/URL rewriting | Mask, HTTPS, cookie-only session transport |
| CSRF token được gửi lại mà vẫn pass | CSRF token không nhất thiết single-use | Đánh giá đúng mục tiêu CSRF, không dùng nó làm OTT |
| Browser A có thể access khi dùng cookie B | Sai ranh giới identity / account binding | Test two browser jars, principal, tenant, session ownership |

## 16. Checklist triển khai và kiểm thử âm tính

1. **Session:** session ID do Servlet container/Spring cung cấp, ngẫu nhiên; không nhận ID chưa từng tạo; tránh URL rewriting; cookie Secure/HttpOnly/SameSite/Domain/Path theo flow.
2. **Authentication:** session fixation protection đang bật ở mọi interactive login/privilege elevation cần thiết; tại boundary ID được đổi và ID cũ không thành authenticated.
3. **Attributes:** pre-auth state, pending MFA, session cart và caches được đánh giá/migrate/clear theo quyền hiện tại; switch user không mang theo role/factor cũ.
4. **Logout/revocation:** invalidate HTTP session server-side, xóa cookie đúng scope, xử lý remember-me và OAuth tokens **riêng**.
5. **CSRF:** giữ CSRF cho browser cookie-based state-changing endpoints, test bằng form/MockMvc có CSRF thật.
6. **Bearer JWT:** validate chữ ký, issuer, audience, expiry, scopes; chấp nhận việc Bearer token được dùng nhiều lần hợp lệ; giảm theft, TTL, sender constraint hoặc revoke khi cần.
7. **Refresh:** public client dùng sender-constrained refresh token hoặc rotation theo RFC 9700; reuse detection, family revoke, atomicity và concurrency tests.
8. **One-time credentials:** OTP/OTT/code/challenge chỉ tiêu thụ một lần theo đúng protocol, expiry, owner/transaction binding và atomic consume.
9. **Business:** payment/transfer có authorization riêng và idempotency riêng; MFA/CSRF/anti-replay không thay permission.
10. **Quan sát:** audit sự kiện session ID changed, logout/invalidate, invalid token/reuse/refresh family revoke; log hash/correlation ID phù hợp, **không log secrets**.
11. **Negative test:** cũ → mới, replay từ browser khác, replay sau logout, callback sai state, JWT sai audience, refresh reuse, concurrent consume và key theft.
12. **Giới hạn:** trong báo cáo test, ghi chính xác “lớp nào chặn cái gì” thay vì nói chung “đã bật chống replay”.

**Tóm tắt:** `changeSessionId()` ngăn một session ID đã biết từ **trước đăng nhập** trở thành ID của phiên có quyền sau đăng nhập. Nó không bảo vệ cookie phiên mới bị lấy trộm. Access JWT Bearer hợp lệ có thể được dùng nhiều lần nên phải giảm lộ và khi cần ràng buộc người gửi/thu hồi; refresh token rotation và one-time consumption phát hiện **reuse của credential vốn được thiết kế dùng một lần**. CSRF, PKCE, OAuth state/nonce, TTL, HTTPS và authorization đều hữu ích, nhưng **không hoán đổi vai trò**.

### Tài liệu gốc

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
