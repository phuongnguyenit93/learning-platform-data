# Kiểm thử đăng xuất, hết phiên và truy cập lại bằng thông tin cũ

## 1. Bài toán: “Đã đăng xuất” thực sự có nghĩa là gì?

Người dùng đăng nhập vào ứng dụng, xem trang tài khoản, rồi nhấn **Đăng xuất**. Giao diện chuyển về trang đăng nhập và không còn hiển thị tên tài khoản. Điều đó **chưa đủ để chứng minh phiên đã bị vô hiệu hóa**. Nếu máy chủ vẫn chấp nhận cookie phiên cũ, yêu cầu HTTP trực tiếp có thể tiếp tục truy cập dữ liệu đã được bảo vệ.

Tương tự, một phiên hết hạn vì không hoạt động phải bị từ chối khi người dùng truy cập lại. Không nên chỉ kiểm tra rằng trình duyệt đã hiển thị thông báo “Phiên hết hạn”. Điều cần kiểm tra là **máy chủ không còn chấp nhận thông tin phiên cũ**.

Bài học thuộc chủ đề **Kiểm thử** của **Spring Security – fundamentals**. Các ví dụ chính dùng **Spring Security Servlet**, **Spring Boot 3.x / Spring Security 6.x** và **Java 17+**, với đăng nhập bằng form và phiên `HttpSession`. Phần sau phân biệt rõ kết quả này với HTTP Basic, remember-me, OAuth/OIDC, bearer token và JWT, vì mỗi cách xác thực có quy tắc thu hồi khác nhau.

Có năm câu hỏi cần trả lời:

1. Request có phiên hợp lệ **trước khi logout** có truy cập được tài nguyên đúng quyền không?
2. `POST /logout` có đúng phương thức, CSRF token và phản hồi dự kiến không?
3. Sau logout, máy chủ có từ chối **cookie/session ID cũ** không, kể cả khi client cố tình gửi lại?
4. Sau khi **hết thời gian không hoạt động** (idle timeout), session ID cũ có bị từ chối không?
5. Sau khi có phiên mới, phiên mới hoạt động bình thường còn **phiên cũ vẫn vô hiệu** không?

Hãy kiểm thử cả trường hợp thành công và trường hợp bị từ chối. Một bài kiểm thử chỉ xác nhận trang đăng nhập hiện lên sau logout không đủ chứng minh an toàn.

## 2. Phân biệt đăng xuất, hết phiên và hủy quyền truy cập

| Tình huống | Điều xảy ra ở phía máy chủ | Điều phải kiểm thử |
| --- | --- | --- |
| **Logout chủ động** | Với đăng nhập bằng `HttpSession`, Spring Security thường invalidate session, xóa security context, dọn CSRF token và trạng thái remember-me được tích hợp. | `POST /logout` hợp lệ thành công; cookie phiên trước logout không được phép truy cập tài nguyên bảo vệ. |
| **Idle timeout** | Servlet container hoặc session repository đánh dấu session hết hiệu lực khi vượt khoảng không hoạt động. | Sau thời gian cấu hình, gửi lại session ID cũ phải bị từ chối. |
| **Absolute lifetime** | Session chỉ sống tối đa một khoảng từ lúc cấp, kể cả khi người dùng đang hoạt động, nếu ứng dụng có chính sách này. | Hết thời hạn tuyệt đối thì yêu cầu với phiên cũ bị từ chối; chính sách này thường cần triển khai bổ sung. |
| **Session fixation protection** | Khi xác thực thành công, Spring Security thông thường đổi session ID của phiên servlet. | Session ID trước login không trở thành phiên đã đăng nhập; session ID sau login khác nếu cơ chế được bật. |
| **Đăng nhập lại** | Sau login thành công, ứng dụng cấp trạng thái xác thực mới. | Session mới được phép truy cập; session cũ sau logout/hết hạn vẫn không được chấp nhận. |
| **Cookie còn tồn tại ở trình duyệt** | Cookie là dữ liệu do browser giữ; server có thể đã hủy session tương ứng. | Dù cố gửi lại cookie cũ bằng công cụ HTTP, server vẫn từ chối. |
| **Đăng xuất toàn bộ thiết bị** | Cần quản lý nhiều session hoặc token và cơ chế thu hồi toàn bộ theo chính sách. | Mọi session/token thuộc phạm vi thu hồi đều không dùng lại được; logout một session không mặc định đồng nghĩa logout tất cả. |
| **Bearer/JWT** | Token đã cấp có thể tiếp tục được chấp nhận tới khi hết hạn nếu không có cơ chế thu hồi. | Kiểm thử riêng chính sách revoke/denylist/introspection, refresh-token rotation và giới hạn thời gian sống. |

**Một khái niệm quan trọng:** `JSESSIONID` chỉ là **mã nhận diện** session phía máy chủ. Sau khi session bị hủy, việc browser còn giữ cookie hoặc người dùng sao chép nó vào công cụ HTTP **không làm session sống lại**. Vì vậy, kiểm thử phải thử **replay giá trị cũ**, không chỉ kiểm tra header `Set-Cookie` xóa cookie.

## 3. Thứ tự các bước trong một kịch bản kiểm thử đúng

Giả sử có ba endpoint:

- `GET /api/public/csrf`: lấy CSRF token để gửi form login/logout trong ví dụ.
- `GET /api/private/me`: chỉ cho người đã xác thực vào.
- `POST /logout`: logout bằng Spring Security; yêu cầu CSRF token khi CSRF đang bật.

Một luồng kiểm thử điển hình:

```text
1. Client GET /api/public/csrf
   -> Server cấp anonymous HttpSession và CSRF token
   -> Client ghi nhớ JSESSIONID trước khi đăng nhập

2. Client POST /login với form + CSRF + cookie
   -> Server xác thực thành công
   -> Session ID được đổi khi login (cấu hình mặc định thông dụng)
   -> Client ghi nhớ JSESSIONID sau login

3. Client GET /api/private/me với cookie sau login
   -> 200 OK

4. Client lấy CSRF token MỚI của phiên đã đăng nhập
   -> Token trước login đã bị xóa khi xác thực thành công

5. Client POST /logout với cookie + CSRF token mới
   -> 204 No Content trong cấu hình minh họa

6. Client CỐ TÌNH dùng lại JSESSIONID cũ:
   GET /api/private/me
   -> 401 Unauthorized

7. Client login lần nữa để tạo phiên mới
   -> Cookie mới truy cập được (200)
   -> Cookie đã logout vẫn bị từ chối (401)
```

Không nên dựa vào chuỗi cookie mới nhất mà browser tự gửi để kết luận phiên cũ vô hiệu. Khi kiểm thử replay, hãy **lưu bản sao cookie trước logout** và gửi **đúng giá trị cũ** sau logout.

### 3.1. Những kết quả nào là đúng?

- Với một **API JSON** sử dụng status-based entry point như ví dụ dưới đây, request chưa xác thực trả **401**.
- Với **ứng dụng web form login mặc định**, cùng tình huống có thể trả **302 redirect tới trang đăng nhập**. Đây là hợp đồng khác, không nhất thiết sai.
- **403** thường dành cho request đã xác thực nhưng thiếu quyền, hoặc POST thiếu/sai CSRF token. Vì vậy, đừng gộp mọi lỗi bảo mật thành “403”.
- Sau logout, nếu client vẫn gửi một **username/password hợp lệ tới endpoint đăng nhập mới**, ứng dụng có thể xác thực lại. Logout không tự đổi mật khẩu.
- Nếu client vẫn gửi **Authorization: Basic** trên mỗi request, server có thể xác thực lại từng lần. Kiểm thử cookie phiên không thể được dùng để kết luận mọi phương thức xác thực đều bị thu hồi.

## 4. Logout mặc định của Spring Security Servlet

Khi bật cơ chế logout của Spring Security Servlet và giữ CSRF:

- `GET /logout` thường hiển thị trang xác nhận logout được Spring Security tạo; **GET không trực tiếp hủy session**.
- `POST /logout` với CSRF token hợp lệ kích hoạt `LogoutFilter`.
- Các logout handler mặc định xử lý `HttpSession`, `SecurityContextHolder`/repository, CSRF token và remember-me khi tính năng đó được tích hợp.
- Sau xử lý, mặc định trình duyệt có thể được redirect tới `/login?logout`. Ví dụ sau thay đổi **chỉ phản hồi thành công** thành `204 No Content` để test API dễ quan sát.

Lưu ý không gọi `GET /logout` bằng JavaScript hay gắn href với kỳ vọng luôn logout. Việc chấp nhận GET để thực hiện logout làm tăng nguy cơ một trang ngoài kích hoạt logout ngoài ý muốn. Đối với form/browser, dùng `POST` với CSRF token; với API, dùng hợp đồng logout phù hợp với cơ chế xác thực.

### 4.1. Logout tác động đến những gì?

Trong trường hợp đăng nhập bằng `HttpSession` thông thường:

- Phiên đang dùng bị vô hiệu hóa bằng `HttpSession.invalidate()`.
- `SecurityContext` được xóa khỏi ngữ cảnh và repository theo đường logout đã cấu hình.
- CSRF token liên quan bị xóa; client phải lấy token mới khi bắt đầu phiên mới.
- Cookie session có thể được yêu cầu xóa ở phía browser. Nhưng **bằng chứng quan trọng vẫn là server từ chối session cũ**.
- Nếu có remember-me và đã cấu hình đúng `RememberMeServices`, logout có thêm bước dọn remember-me.
- Nếu ứng dụng có WebSocket, OAuth2 client session, nhiều subdomain hoặc token ngoài hệ thống session, cần cơ chế thu hồi riêng; logout servlet không tự làm thay toàn bộ.

Không đánh đồng **xóa cookie** và **vô hiệu hóa session**. Xóa cookie ở client khiến trình duyệt không gửi tiếp, nhưng một kẻ đã sao chép session ID trước đó vẫn có thể dùng nếu server chưa thu hồi.

## 5. Những lớp kiểm thử phải có

| Nhóm | Case kiểm thử | Mục tiêu |
| --- | --- | --- |
| Trước login | Gọi endpoint private không có cookie | Bị chặn theo hợp đồng (ví dụ 401). |
| Login thành công | Dùng credentials đúng và CSRF hợp lệ | Session mới có quyền, private endpoint trả 200. |
| Session fixation | So sánh session ID trước và sau khi login | Xác thực không giữ nguyên ID do anonymous session có trước. |
| POST logout có CSRF | Gửi cookie hợp lệ và CSRF token hợp lệ | Logout thành công; server hủy session. |
| POST logout **không có CSRF** | Gửi cookie hợp lệ nhưng bỏ token | Trả 403 và **không logout ngoài ý muốn**. |
| GET logout | Mở trang xác nhận bằng GET | Không mất phiên chỉ vì GET. |
| Replay session cũ | Dùng chính cookie đã lưu trước logout | Endpoint private từ chối. |
| Replay CSRF cũ | Sau logout dùng cookie/token cũ gửi POST ghi dữ liệu | Request không được chấp nhận. |
| Hết hạn do inactivity | Đặt session timeout ngắn ở môi trường test, không truy cập tới khi hết hạn | Sau timeout, cookie cũ không truy cập được. |
| Login lại | Sau logout thực hiện login mới | Cookie mới truy cập được; cookie cũ vẫn bị chặn. |
| Browser back/cache | Logout rồi nhấn Back, Reload và dùng tab cũ | Không tải lại được nội dung nhạy cảm từ server; không hiển thị dữ liệu từ cache ngoài chính sách. |
| Nhiều thiết bị/session | Hai browser đăng nhập cùng tài khoản, logout một phiên hoặc logout all | Hành vi đúng phạm vi thu hồi đã công bố. |

Cần thêm cả trường hợp **request đã bắt đầu trước logout**: logout không nhất thiết hủy request đang xử lý dở hoặc tác vụ đã xếp hàng. Với nghiệp vụ nhạy cảm, kiểm tra quyền và trạng thái phiên tại đúng điểm thực hiện thay đổi, kết hợp chính sách chống race khi cần.

## 6. Ví dụ Spring Boot 3.x / Java 17+: form login, session và logout thật

Để quan sát đầy đủ cookie và thời gian hết hạn, phần kiểm thử sử dụng **HTTP thật tới embedded Servlet container chạy trên random port**, thay vì chỉ mô phỏng request bằng MockMvc. Điều này giúp kiểm chứng cả việc cấp session cookie, thay session ID, thu hồi session và session timeout.

Một dự án Spring Boot 3.x có plugin Gradle, Java toolchain 17+ và các dependency:

```groovy
// Trích đoạn trong build.gradle (Groovy DSL).
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **trích đoạn dependencies** của dự án Spring Boot đã có build script, không phải một file `build.gradle` đầy đủ có thể thực thi độc lập. Các lớp Java dưới đây đặt trong package `demo.sessiontest`. Mã được xây dựng cho Spring Boot 3.x / Spring Security 6.x dùng Servlet và embedded Tomcat do `spring-boot-starter-web` cung cấp.

### 6.1. Main class

Tệp `src/main/java/demo/sessiontest/SessionTestApplication.java`:

```java
package demo.sessiontest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionTestApplication.class, args);
    }
}
```

### 6.2. Cấu hình xác thực, entry point cho API và logout

Tệp `src/main/java/demo/sessiontest/SecurityConfig.java`:

```java
package demo.sessiontest;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        AuthenticationEntryPoint apiUnauthorized =
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            // Form login của Spring Security:
            // GET /login hiển thị form, POST /login kiểm tra credentials.
            .formLogin(Customizer.withDefaults())
            // Chỉ với /api/**: thay redirect sang login bằng HTTP 401.
            .exceptionHandling(ex -> ex
                .defaultAuthenticationEntryPointFor(
                    apiUnauthorized,
                    new AntPathRequestMatcher("/api/**")
                )
            )
            // Giữ CSRF mặc định; logout phải là POST có CSRF token.
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
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
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

**Tại sao cấu hình này phù hợp để học kiểm thử?**

- Có form login và `HttpSession` thật, nên có thể lưu **cookie trước và sau login**.
- `.csrf(Customizer.withDefaults())` giữ token cho cả POST login và POST logout; không đơn giản hóa kiểm thử bằng `csrf.disable()`.
- Entry point dùng status **401** cho `/api/**` thay vì redirect, giúp xác nhận request thiếu xác thực một cách rõ ràng. Phần `/login` vẫn hoạt động theo form login của Spring Security.
- Logout invalidate session, xóa security context và gửi yêu cầu xóa cookie `JSESSIONID`. Test vẫn **tái sử dụng bản sao cookie cũ** để chứng minh phía server từ chối.
- `204 No Content` là hợp đồng logout tùy chỉnh cho bài học. Nếu ứng dụng dùng logout mặc định redirect, test phải kiểm tra status/Location phù hợp thay vì luôn chờ 204.
- Không bật remember-me, JWT hay HTTP Basic; các cơ chế đó có quy tắc thu hồi khác và cần test riêng.

Tên người dùng và mật khẩu cố định trong ví dụ **chỉ cho môi trường học/test**. Hệ thống thật dùng quản lý danh tính/credentials an toàn, HTTPS và chính sách cookie phù hợp. Không đưa tài khoản demo này vào production.

### 6.3. Controller: CSRF token và tài nguyên private

Tệp `src/main/java/demo/sessiontest/DemoController.java`:

```java
package demo.sessiontest;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        // Đọc token để HttpSessionCsrfTokenRepository sinh/lưu token.
        // Spring Security 6 mặc định còn xử lý token chống BREACH.
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }

    @GetMapping("/api/private/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/api/private/update")
    public Map<String, Boolean> update() {
        // Chỉ là thao tác minh họa đã vượt qua CSRF và xác thực.
        return Map.of("updated", true);
    }
}
```

Endpoint `GET /api/public/csrf` giúp bài test lấy token hợp lệ qua HTTP mà không phải phân tích HTML login mặc định. Nó trả masked CSRF token theo cơ chế mặc định tương ứng của Spring Security 6; client gửi token đó trong header được chỉ định. Sau khi xác thực hoặc logout, token CSRF cũ bị xóa, nên ví dụ **lấy token mới** khi cần POST tiếp.

Đây là endpoint phục vụ ví dụ học. Với SPA ngoài thực tế, thiết kế endpoint lấy token, CORS, cookie, BREACH masking, phương thức truyền token và thời điểm refresh phải phù hợp kiến trúc frontend; không suy ra chỉ cần công khai token là mọi luồng SPA đều an toàn. Token CSRF không phải token xác thực và không được đưa vào URL.

### 6.4. Endpoint điều chỉnh idle timeout — chỉ đặt trong test source

Để kiểm thử hết phiên **thật** mà không phải chờ mặc định 30 phút, thêm một controller vào **classpath kiểm thử**. File này ở `src/test/java`, không nằm trong artifact production.

Tệp `src/test/java/demo/sessiontest/SessionExpiryProbe.java`:

```java
package demo.sessiontest;

import jakarta.servlet.http.HttpSession;
import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("test")
public class SessionExpiryProbe {

    @PostMapping("/__test/expire-soon")
    public ResponseEntity<Void> expireSoon(HttpSession session) {
        // Chỉ phiên đang đăng nhập trong bài test này bị giảm timeout.
        session.setMaxInactiveInterval(1);
        return ResponseEntity.noContent().build();
    }
}
```

Lý do chọn cách này:

- `HttpSession.setMaxInactiveInterval(1)` đặt **một giây** không hoạt động cho chính phiên đang dùng. Session sẽ bị xem là hết hạn khi container kiểm tra thời gian idle, thay vì test tự gọi `invalidate()` rồi nhầm đó là timeout.
- Route probe yêu cầu xác thực do `anyRequest().authenticated()` và CSRF vì dùng POST.
- `@Profile("test")` khiến controller chỉ hoạt động khi active profile `test`. Vì đặt trong `src/test/java`, nó không được đưa vào ứng dụng đóng gói production.
- Đừng tạo endpoint đặt lại timeout tùy ý của người dùng trong môi trường production chỉ để dễ viết test. Đây là **công cụ riêng của bộ test**.

Khi cần kiểm thử session timeout chính xác hơn, xác định `server.servlet.session.timeout`, cơ chế session repository (ví dụ Spring Session/Redis), behavior của Servlet container và chiến lược làm mới thời điểm truy cập. Session timeout **không phải** timeout của access token OAuth2.

## 7. Kiểm thử tích hợp qua HTTP thật và cookie cố tình dùng lại

Tệp `src/test/java/demo/sessiontest/LogoutAndExpiryIntegrationTests.java`:

```java
package demo.sessiontest;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class LogoutAndExpiryIntegrationTests {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    // Cố tình không dùng CookieManager tự động:
    // test cần gửi lại chính xác cookie cũ, kể cả sau khi server yêu cầu xóa.
    private final HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Test
    void privateResourceRequiresAuthentication() throws Exception {
        HttpResponse<String> response = get("/api/private/me", null);
        assertEquals(401, response.statusCode());
    }

    @Test
    void loginRotatesSessionIdAndOldAnonymousIdIsNotAuthenticated()
            throws Exception {
        HttpResponse<String> csrfResponse = get("/api/public/csrf", null);
        assertEquals(200, csrfResponse.statusCode());

        String beforeLogin = sessionCookie(csrfResponse);
        String csrf = csrfToken(csrfResponse);

        HttpResponse<String> login = post(
            "/login", beforeLogin, csrf,
            "username=reader&password=demo-password"
        );

        assertEquals(302, login.statusCode());
        String afterLogin = sessionCookie(login);

        // Cấu hình Spring Security Servlet thông dụng chống session fixation.
        assertNotEquals(beforeLogin, afterLogin);
        assertEquals(200, get("/api/private/me", afterLogin).statusCode());
        assertEquals(401, get("/api/private/me", beforeLogin).statusCode());
    }

    @Test
    void logoutWithValidCsrfInvalidatesOldSession() throws Exception {
        String signedInCookie = loginAndReturnCookie();
        assertEquals(200, get("/api/private/me", signedInCookie).statusCode());

        String freshCsrf = csrfToken(
            get("/api/public/csrf", signedInCookie)
        );

        HttpResponse<String> logout = post(
            "/logout", signedInCookie, freshCsrf, ""
        );
        assertEquals(204, logout.statusCode());

        // Replay đúng giá trị JSESSIONID trước logout.
        assertEquals(401, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndSessionRemainsValid()
            throws Exception {
        String signedInCookie = loginAndReturnCookie();

        HttpResponse<String> rejected = post(
            "/logout", signedInCookie, null, ""
        );
        assertEquals(403, rejected.statusCode());

        // POST không hợp lệ không được vô tình đăng xuất người dùng.
        assertEquals(200, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void getLogoutPageDoesNotPerformLogout() throws Exception {
        String signedInCookie = loginAndReturnCookie();

        // Với CSRF bật, GET /logout là trang xác nhận, không thực hiện logout.
        get("/logout", signedInCookie);
        assertEquals(200, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void previousCsrfTokenCannotUpdateStateAfterLogout()
            throws Exception {
        String signedInCookie = loginAndReturnCookie();
        String oldCsrf = csrfToken(get("/api/public/csrf", signedInCookie));

        assertEquals(204,
            post("/logout", signedInCookie, oldCsrf, "").statusCode());

        HttpResponse<String> replay = post(
            "/api/private/update", signedInCookie, oldCsrf, ""
        );

        // Session đã mất; CSRF token cũ không còn được chấp nhận.
        assertEquals(403, replay.statusCode());
        assertFalse(replay.body().contains("updated"));
    }

    @Test
    void idleTimeoutRejectsOldSessionId() throws Exception {
        String signedInCookie = loginAndReturnCookie();
        String csrf = csrfToken(get("/api/public/csrf", signedInCookie));

        HttpResponse<String> shortened = post(
            "/__test/expire-soon", signedInCookie, csrf, ""
        );
        assertEquals(204, shortened.statusCode());

        // Giữ im lặng trên phiên > 1 giây để container đánh dấu hết hạn.
        Thread.sleep(1600);

        // Client cố tình gửi lại cookie từng hợp lệ.
        assertEquals(401, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void newLoginWorksButLoggedOutSessionNeverWorksAgain()
            throws Exception {
        String oldCookie = loginAndReturnCookie();
        String csrf = csrfToken(get("/api/public/csrf", oldCookie));

        assertEquals(204, post("/logout", oldCookie, csrf, "").statusCode());

        String newCookie = loginAndReturnCookie();
        assertNotEquals(oldCookie, newCookie);
        assertEquals(200, get("/api/private/me", newCookie).statusCode());
        assertEquals(401, get("/api/private/me", oldCookie).statusCode());
    }

    @Test
    void protectedResponseShouldNotBeStoredInSharedCache()
            throws Exception {
        String cookie = loginAndReturnCookie();
        HttpResponse<String> response = get("/api/private/me", cookie);

        assertEquals(200, response.statusCode());
        assertTrue(
            response.headers().firstValue("Cache-Control")
                .orElse("").contains("no-store")
        );
    }

    private String loginAndReturnCookie() throws Exception {
        HttpResponse<String> issued = get("/api/public/csrf", null);
        assertEquals(200, issued.statusCode());
        String anonymousCookie = sessionCookie(issued);
        String token = csrfToken(issued);

        HttpResponse<String> login = post(
            "/login", anonymousCookie, token,
            "username=reader&password=demo-password"
        );
        assertEquals(302, login.statusCode());

        return sessionCookie(login);
    }

    private String csrfToken(HttpResponse<String> response) throws Exception {
        assertEquals(200, response.statusCode());
        JsonNode json = mapper.readTree(response.body());
        String token = json.path("token").asText();
        assertFalse(token.isBlank());
        return token;
    }

    private String sessionCookie(HttpResponse<String> response) {
        return response.headers().allValues("Set-Cookie").stream()
            .map(value -> value.split(";", 2)[0])
            .filter(value ->
                value.startsWith("JSESSIONID=")
                && value.length() > "JSESSIONID=".length()
            )
            .findFirst()
            .orElseThrow(() ->
                new AssertionError("Server did not issue JSESSIONID cookie")
            );
    }

    private HttpResponse<String> get(String path, String cookie)
            throws Exception {
        return send("GET", path, cookie, null, "");
    }

    private HttpResponse<String> post(
            String path, String cookie, String csrf, String body
    ) throws Exception {
        return send("POST", path, cookie, csrf, body);
    }

    private HttpResponse<String> send(
            String method, String path, String cookie,
            String csrf, String body
    ) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(
            URI.create("http://127.0.0.1:" + port + path)
        ).timeout(Duration.ofSeconds(10));

        if (cookie != null) {
            request.header("Cookie", cookie);
        }
        if (csrf != null) {
            request.header("X-CSRF-TOKEN", csrf);
        }

        if ("POST".equals(method)) {
            request.header(
                "Content-Type", "application/x-www-form-urlencoded"
            );
            request.POST(HttpRequest.BodyPublishers.ofString(
                body, StandardCharsets.UTF_8
            ));
        } else {
            request.GET();
        }

        return client.send(
            request.build(),
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );
    }
}
```

### 7.1. Vì sao test dùng Java `HttpClient` thay vì chỉ MockMvc?

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động **Servlet container thật** trên cổng ngẫu nhiên.
- `HttpClient` của Java 17 gửi request HTTP thật. Đoạn test **không bật CookieManager** và **không tự follow redirect**, cho phép ghi lại cookie trước logout rồi cố tình replay.
- `sessionCookie(...)` đọc giá trị `JSESSIONID=...` từ `Set-Cookie` mà server cấp; nó không tự xóa bản sao cookie cũ khi response logout gửi cookie hủy.
- `loginAndReturnCookie()` thực hiện đúng chu trình `GET CSRF → POST login → nhận session ID mới`, tránh tự chế session đã đăng nhập.
- `@ActiveProfiles("test")` bật controller test-only để đặt timeout một giây cho một phiên. `Thread.sleep(1600)` tạo khoảng không hoạt động lớn hơn cấu hình. Thời gian ngắn này dành cho test tích hợp; không đem timeout một giây vào hệ thống thực.
- Mỗi test tạo session riêng; vì vậy logout ở test này không làm thay đổi phiên của test khác.
- Đối với môi trường CI có timing bất ổn, có thể tăng khoảng chờ hoặc dùng cơ chế polling có giới hạn và kiểm tra cuối cùng sau khi idle thực sự vượt ngưỡng. Tránh gọi endpoint bảo vệ trong khoảng chờ vì mỗi request có thể làm mới thời gian truy cập của session.

### 7.2. Kết quả mong đợi

Nếu các class được tạo đúng đường dẫn, ứng dụng dùng container và dependency phù hợp, các bài kiểm thử trên **được thiết kế để PASS**. Lệnh chạy:

```bash
./gradlew test --tests demo.sessiontest.LogoutAndExpiryIntegrationTests
```

Test class có **9 ca** kiểm tra độc lập:

| Ca | Status/trạng thái mong đợi | Ý nghĩa |
| --- | --- | --- |
| Không có cookie | 401 | Endpoint private được bảo vệ. |
| Login / session fixation | 302 khi login; 200 với cookie mới; 401 với cookie anonymous cũ | Không cố định ID session trước và sau xác thực. |
| Logout có CSRF | 204 logout; dùng cookie cũ nhận 401 | Session bị vô hiệu hóa ở phía server. |
| Logout thiếu CSRF | 403 logout; cookie cũ vẫn truy cập 200 | Không thể ép logout bằng POST giả mạo. |
| GET logout | Session vẫn truy cập 200 | GET không tự thực hiện logout. |
| Replay CSRF cũ | POST ghi dữ liệu 403 | Token/session cũ không còn đủ điều kiện. |
| Idle timeout thật | Sau 1,6 giây idle, cookie cũ nhận 401 | Container từ chối session hết hạn. |
| Login mới | Cookie mới 200, cookie đã logout 401 | Không làm sống lại phiên trước đó. |
| Header cache cho private | Có `Cache-Control` chứa `no-store` | Giảm nguy cơ response nhạy cảm bị lưu ngoài dự kiến. |

**Đây là kỳ vọng của mã ví dụ, không phải kết quả test đã chạy trong tài liệu.** Phụ thuộc vào phiên bản Boot/Servlet container và hệ thống CI, có thể cần điều chỉnh test timeout/đường dẫn hoặc hợp đồng redirect của ứng dụng thật. Không nên sử dụng phép ngủ ngắn làm “bằng chứng” duy nhất cho tất cả loại session repository phân tán.

## 8. Khi kiểm thử bằng MockMvc: điều gì được và chưa được chứng minh?

Spring Security cung cấp test helper cho MockMvc như `formLogin()`, `logout()` và `csrf()`:

```java
import static org.springframework.security.test.web.servlet
        .request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet
        .request.SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet
        .request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;

// Các dòng minh họa sử dụng trong một test đã có MockMvc mvc:
mvc.perform(formLogin().user("reader").password("demo-password"));
mvc.perform(logout()); // Helper tạo POST logout với CSRF hợp lệ.
mvc.perform(post("/logout")); // Không có CSRF: thường bị 403.
mvc.perform(post("/api/private/update").with(csrf()));
```

Các dòng này là **trích đoạn trong test**, không phải chương trình độc lập; phải có `MockMvc`, security filter chain, assertion và trạng thái session được xây dựng đúng. `formLogin()` helper chuẩn bị form request, còn `logout()` helper tạo POST logout có CSRF token.

**Cảnh báo kiểm thử sai phổ biến:** gửi `MockHttpSession` đã `invalidate()` rồi gắn trực tiếp vào request mới không đồng nghĩa với việc một trình duyệt gửi lại `JSESSIONID` qua mạng và container kiểm tra session store. Mô phỏng quá trình timeout bằng `mockSession.invalidate()` chỉ kiểm tra **hủy phiên chủ động**, không chứng minh **idle timeout** của Servlet container.

Dùng MockMvc để kiểm tra nhanh quy tắc filter, status, CSRF, handler và controller. Muốn xác nhận **Set-Cookie, session ID rotation, cookie replay, idle timeout, browser redirect và container**, cần bổ sung kiểm thử tích hợp HTTP thật như phần 7.

## 9. Đánh giá đúng trường hợp “truy cập lại bằng thông tin cũ”

“Thông tin cũ” có nhiều nghĩa và kết quả mong đợi **khác nhau**:

### 9.1. Session ID hoặc cookie cũ

Sau logout hoặc session timeout, cookie cũ phải **không** tạo ra quyền truy cập với phiên đó. Test dùng lại đúng giá trị đã lưu là cách kiểm tra trực tiếp. Nếu server vẫn trả 200 cho private endpoint, đây là dấu hiệu cần điều tra session invalidation, session store, cache hoặc cơ chế xác thực phụ.

### 9.2. CSRF token cũ

Spring Security logout thường xóa CSRF token hiện hành, và xác thực thành công cũng làm token trước login bị xóa. Trên yêu cầu ghi cần CSRF, việc replay token cũ kèm cookie cũ phải bị từ chối. Nhưng CSRF token **không phải credential đăng nhập**: ngay cả token hợp lệ cũng không cấp quyền nếu thiếu xác thực. Hãy kiểm thử CSRF và authentication như **hai điều kiện độc lập**.

### 9.3. Username/password cũ

Nếu người dùng chỉ logout mà chưa đổi mật khẩu, credentials hợp lệ **vẫn có thể dùng để login lại**. Điều này không chứng minh logout lỗi. Nếu chính sách là khóa tài khoản, reset mật khẩu hoặc thu hồi tất cả quyền, cần test riêng việc vô hiệu hóa credentials và các session hiện hành.

### 9.4. Remember-me cookie

Khi nhớ đăng nhập được bật, một request không có `JSESSIONID` vẫn có thể được xác thực qua remember-me cookie nếu cookie và server-side token còn hợp lệ. Spring Security tích hợp remember-me logout handler khi được cấu hình, nhưng **phải kiểm thử thực tế**:

- Trước logout, remember-me cookie có thể khôi phục xác thực theo chính sách.
- Sau logout, gửi lại cookie remember-me cũ phải không khôi phục được xác thực nếu yêu cầu là hủy remember-me.
- Với persistent remember-me, xác minh token trong repository bị thu hồi hoặc xoay vòng đúng cách.
- Không chỉ dựa vào response `Set-Cookie` xóa cookie; cố tình replay bản sao cũ.

### 9.5. JWT/access token và refresh token

JWT dạng self-contained còn hạn dùng có thể được resource server chấp nhận sau khi ứng dụng web logout nếu **không** có denylist, token versioning, introspection, thu hồi key hoặc một cơ chế kiểm tra trạng thái khác. Logout một `HttpSession` không tự hủy JWT đã phát hành.

Với OAuth/OIDC phải phân biệt:

- **Logout tại ứng dụng**: xóa local session.
- **Logout tại Identity Provider**: kết thúc phiên đăng nhập tại nhà cung cấp khi giao thức/luồng được hỗ trợ.
- **Revocation của refresh token**: chặn việc xin access token mới theo chính sách cấp token.
- **Access token còn hạn**: có thể cần sống ngắn hoặc cơ chế thu hồi phù hợp.

Các ca chấp nhận cần được viết theo **chính sách thực tế**; không khẳng định “logout xong mọi token ở mọi hệ thống lập tức vô hiệu” nếu kiến trúc không hỗ trợ. Nếu ứng dụng cho phép login lại nhờ SSO còn hiệu lực, một lượt GET sau logout có thể tạo phiên mới qua redirect. Test phải phân biệt điều đó với việc session ID cũ vẫn có quyền.

### 9.6. Nhiều tab và nhiều thiết bị

Các tab cùng browser profile thường chia sẻ cookie session. Logout ở tab A khiến request mới của tab B dùng session ID cũ phải bị từ chối; nhưng nội dung đã render trong bộ nhớ UI của tab B có thể vẫn hiển thị cho đến khi reload hoặc ứng dụng nhận sự kiện thay đổi. Cần kiểm thử trạng thái UI và cấm thao tác tiếp theo ở server.

Hai trình duyệt/thiết bị có thể có hai session độc lập. Logout thiết bị A thường **chỉ hủy session A**, trừ khi chính sách yêu cầu logout all. Muốn logout all phải có quản lý session/token tập trung và kiểm thử trên từng thiết bị.

## 10. Những yếu tố làm test logout/timeout “xanh giả”

### 10.1. Client tự bỏ cookie rồi gọi API

Nếu chỉ xóa cookie trong test client, GET private trả 401 là điều đương nhiên. Bạn chưa chứng minh máy chủ đã hủy phiên. Phải **lưu và tái gửi lại cookie cũ sau logout**.

### 10.2. Test gửi Basic/Bearer credentials ngoài ý muốn

Một HTTP client có cấu hình `Authorization` mặc định hoặc tự refresh token có thể truy cập lại thành công bằng **một cơ chế mới**, khiến bạn tưởng session chưa bị vô hiệu. Tắt tự động thêm credentials/refresh trong test replay, sau đó kiểm thử từng cơ chế riêng.

### 10.3. Auto-follow redirect che mất status

Nếu client tự theo `302 /login` rồi nhận 200 từ trang đăng nhập, assertion nhìn thấy 200 dễ dẫn đến kết luận sai. Với API status contract, cố định expected status; với web contract, tắt follow redirect khi đo status và `Location`.

### 10.4. Chỉ kiểm tra cookie bị xóa

`deleteCookies("JSESSIONID")` gửi lệnh cho browser xóa cookie. Cookie bị mất ở client không có nghĩa bản sao cũ đã bị server thu hồi. Test phải tái gửi chính ID cũ.

### 10.5. Chỉ gọi `invalidate()` rồi gọi đó là “hết phiên”

Invalidate là thao tác chủ động. Idle timeout cần kiểm tra **thời gian không hoạt động**, container hoặc session repository. Với Spring Session/Redis, còn phải xét thời gian lưu trữ, TTL, đồng bộ và việc dọn session.

### 10.6. Có request nền làm mới session

Một request định kỳ như polling, heartbeat hoặc endpoint load dữ liệu có thể làm mới thời gian truy cập của session và khiến test timeout không thể hết hạn. Khi đo idle timeout, đảm bảo không có request nào khác sử dụng chính session đó.

### 10.7. Nhầm 401 với 403

Ở ví dụ, GET private không có xác thực trả 401. POST thiếu CSRF có thể trả 403 **ngay trước khi kiểm tra quyền**. Test phải dựa vào đường đi cụ thể thay vì suy luận rằng mọi 403 đều là “đã đăng nhập nhưng thiếu quyền”.

### 10.8. Browser back hiển thị trang đã cache

Sau logout, nhấn Back có thể hiển thị snapshot đã render, kể cả khi server đã hủy phiên. Điều đó không tự chứng minh session còn hiệu lực, nhưng có thể là rủi ro lộ dữ liệu trên máy dùng chung. Cần kết hợp `Cache-Control: no-store`, reload và kiểm thử hành vi UI thực tế.

### 10.9. Nhầm session timeout với JWT expiry

Servlet session timeout không làm JWT hết hạn. Một backend dùng bearer token độc lập với session phải test thời hạn/thu hồi token theo cơ chế riêng.

### 10.10. Không thử session fixation và login lại

Nếu chỉ test một logout đơn lẻ, bạn có thể bỏ sót chuyện session ID trước login được giữ nguyên hoặc session cũ vô tình có quyền lại khi login mới. Cần so sánh ID trước/sau login và xác minh old ID sau logout không bao giờ được tái kích hoạt.

## 11. Kiểm thử browser thực tế và bảo mật dữ liệu sau logout

Các bài test HTTP chứng minh trạng thái xác thực ở server, nhưng người dùng còn nhìn thấy giao diện. Hãy kiểm thử thủ công hoặc qua Playwright/Selenium với tài khoản thử nghiệm:

1. Đăng nhập, mở trang có dữ liệu cá nhân rồi mở cùng trang ở tab thứ hai.
2. Logout tại tab đầu tiên bằng luồng giao diện thật.
3. Quay lại tab thứ hai; thử tải thêm dữ liệu, thực hiện một thao tác ghi và reload. Request mới phải bị từ chối hoặc yêu cầu đăng nhập.
4. Dùng Back/Forward: kiểm tra có dữ liệu nhạy cảm bị hiển thị từ cache hay state giữ trong bộ nhớ. Nếu có, cần thiết kế dọn state frontend, header cache và chính sách cho thiết bị dùng chung.
5. Kiểm tra mục Network: logout là POST có CSRF khi ứng dụng dùng cookie, status/redirect đúng, không có token/session ID trong URL.
6. Thử giữ một request đang mở khi logout xảy ra; ghi nhận khả năng request đã được chấp nhận trước đó vẫn hoàn thành.
7. Thử logout ở một tab rồi đăng nhập user khác: nội dung/tài nguyên của user trước không được tái sử dụng từ cache hoặc state cũ.
8. Kiểm tra response private có chính sách cache phù hợp và client không lưu dữ liệu nhạy cảm lâu hơn cần thiết.

**Lưu ý:** `Cache-Control: no-store` giúp giảm nguy cơ browser/proxy lưu response, nhưng không tự xóa toàn bộ DOM hiện tại, localStorage, IndexedDB hoặc dữ liệu SPA đã giữ trong RAM. Nếu ứng dụng lưu dữ liệu nhạy cảm ngoài session, quy trình logout frontend phải dọn chúng một cách có chủ đích.

## 12. Session ở nhiều máy chủ và Spring Session

Trong môi trường có load balancer và nhiều instance:

- Nếu session chỉ nằm trong bộ nhớ từng node, cơ chế routing/sticky session ảnh hưởng request nào tìm được session. Đây có thể gây “đăng nhập lúc được lúc mất”, không nên nhầm với logout đúng.
- Nếu dùng **Spring Session** với Redis/JDBC, cần kiểm thử rằng session bị xóa/expire ở repository dùng chung và request đi qua **node khác** vẫn bị từ chối.
- Việc TTL trong Redis và cơ chế session expiration có thể có độ trễ vận hành; tiêu chí chấp nhận nên dựa trên hành vi xác thực request thực tế, không chỉ quan sát key biến mất tức thì.
- Với session fixation, kiểm tra session ID mới tại login trên chính hệ thống deployment; đừng giả định cùng hành vi cho mọi loại repository và container tùy chỉnh.
- Nếu có “logout tất cả thiết bị”, hệ thống phải liệt kê và thu hồi đúng **mọi phiên** thuộc tài khoản; logout mặc định của một browser không tự làm việc này.

Một test phân tán tốt có thể đăng nhập qua node A, logout qua node B, rồi dùng cookie cũ gọi node A và B. Cả hai phải từ chối trong giới hạn nhất quán đã cam kết. Với ứng dụng dùng SSO, còn cần test trạng thái IdP và khả năng tự login lại.

## 13. Quy trình nghiệm thu logout/timeout có thể tái sử dụng

Khi xây bộ test cho ứng dụng của mình:

- **Định nghĩa cơ chế xác thực.** Session cookie, Basic, bearer JWT, remember-me, OAuth2 hay phối hợp? Kết quả thu hồi khác nhau.
- **Chốt hợp đồng HTTP.** Với API, định nghĩa 401/403/204; với browser, định nghĩa 302 và trang login/confirmation; giữ `WWW-Authenticate` nếu giao thức yêu cầu.
- **Xây fixture phiên hợp lệ.** Dùng login thật, lưu cookie trước và sau khi xác thực, lấy CSRF token ở thời điểm phù hợp.
- **Thử logout an toàn.** POST có CSRF thành công; POST thiếu token bị từ chối; GET không tự logout.
- **Replay dữ liệu cũ.** Gửi lại chính session ID và CSRF token từ phiên trước; server không cấp quyền.
- **Kiểm tra timeout thật.** Đặt timeout ngắn trên test server/session repository, để phiên idle rồi gửi lại ID cũ.
- **Chứng minh không chặn nhầm.** Login mới tạo phiên hợp lệ; request hợp lệ vẫn thành công.
- **Kiểm tra trình duyệt và hệ thống phân tán.** Cache/back button, tab khác, remember-me, IdP, Redis và multi-node khi có trong kiến trúc.
- **Quan sát đúng bằng chứng.** Status, `Set-Cookie`, `Location`, response body, session repository và log vận hành; không in cookie/token thật vào báo cáo lỗi.

### Checklist trước khi đưa lên production

| Tiêu chí | Kỳ vọng |
| --- | --- |
| Logout có CSRF và đúng method | Không thể bị một website ngoài kích hoạt tùy ý bằng GET/POST thiếu token. |
| Vô hiệu hóa session phía server | Cookie/session ID cũ bị từ chối dù client replay. |
| Session fixation | ID trước và sau đăng nhập khác nhau theo cơ chế đã chọn. |
| Hết phiên do inactivity | Thời gian hết hạn được đo bằng test có container/repository thật. |
| CSRF token lifecycle | Sau login/logout lấy token mới; không tái sử dụng token cũ để thay đổi trạng thái. |
| Login mới | Session mới hoạt động, session cũ không “sống lại”. |
| Nhớ đăng nhập/SSO/token | Chính sách thu hồi được kiểm thử riêng, không giả định theo logout servlet. |
| Cache/Back/đa tab | Không thể xem lại hoặc thao tác trên dữ liệu nhạy cảm trái chính sách. |
| Nhiều node | Thu hồi/expire nhất quán trên các instance thuộc phạm vi triển khai. |
| Test CI | Không dùng phiên production, credentials thật hoặc timeout cố định quá sát dẫn đến test không ổn định. |

## 14. Câu hỏi thực hành

**Tình huống A:** Sau logout, Chrome không gửi `JSESSIONID` nữa và `GET /api/private/me` trả 401. Đã chứng minh server invalidate session chưa?

**Chưa.** Cần lấy **giá trị cookie trước logout** rồi gửi lại thủ công. Nếu server vẫn trả 200, session phía server có thể chưa bị hủy hoặc có cơ chế xác thực khác đang tự phục hồi.

**Tình huống B:** Sau logout, dùng cùng username/password đăng nhập lại thành công. Có phải logout lỗi?

**Không.** Logout session không tự vô hiệu hóa thông tin đăng nhập hợp lệ. Muốn thay đổi mật khẩu/thu hồi credential cần quy trình và test riêng.

**Tình huống C:** Sau timeout một giây, test dùng `mockSession.invalidate()` rồi nhận 401. Có đủ khẳng định idle timeout hoạt động?

**Không.** Đây là test chủ động invalidate. Muốn kiểm thử hết hạn do idle cần container/repository thực sự áp dụng thời gian không hoạt động.

**Tình huống D:** API dùng JWT, logout session servlet thành công nhưng access token cũ vẫn đọc được dữ liệu. Có bắt buộc xem là lỗi?

**Tùy chính sách token của hệ thống.** Nếu hợp đồng cam kết revoke token ngay khi logout, đó là lỗi cần sửa. Nếu access token ngắn hạn không thu hồi tức thì theo thiết kế, phải công bố và kiểm thử đúng thời hạn/refresh-token revocation. Không dùng kết quả kiểm thử cookie session để suy ra tình trạng token tự chứa.

**Tình huống E:** Sau logout, nhấn Back vẫn thấy nội dung trang tài khoản, nhưng nhấn Reload nhận 401. Cần điều tra gì?

Máy chủ có vẻ không còn cho truy cập bằng session cũ, nhưng trình duyệt vẫn có thể hiển thị nội dung đã lưu. Kiểm tra `Cache-Control`, browser back-forward cache, state của SPA, dữ liệu ở storage và chính sách hiển thị trên thiết bị dùng chung.

## 15. Tài liệu tham khảo chính thức

- Spring Security — [Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html).
- Spring Security — [Testing Logout with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/logout.html).
- Spring Security — [Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html).
- Spring Security — [CSRF and logout](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/).
- Spring Boot — [Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html).
- Jakarta Servlet — [HttpSession API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession).