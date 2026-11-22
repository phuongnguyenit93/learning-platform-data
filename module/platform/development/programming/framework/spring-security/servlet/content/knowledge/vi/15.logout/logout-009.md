# Kiểm thử yêu cầu sau đăng xuất và những phiên còn hoạt động trong Spring Security Servlet

> **Chủ đề:** Spring Security - servlet. **Nhóm:** Đăng xuất (Logout). Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC và Spring Security Test.

## 1. Sau khi logout, chính xác điều gì cần được kiểm thử?

Người dùng nhấn **Đăng xuất**. Trình duyệt nhận HTTP 302 về trang login. Ta có thể kết luận việc đăng xuất đã hoàn tất chưa?

**Chưa đủ.** Redirect chỉ cho biết endpoint logout đã tạo phản hồi. Cần kiểm tra trạng thái **trong server**, **các request sau đó** và **những phiên/token khác** còn có quyền truy cập hay không.

Có ít nhất ba câu hỏi riêng biệt:

1. **Phiên hiện tại**: request đăng xuất có thực sự hủy `HttpSession` hiện tại, xóa `SecurityContext` và không còn coi cookie session cũ là bằng chứng xác thực?
2. **Request kế tiếp**: nếu client cố mở lại một URL bảo vệ sau khi logout, server trả về kết quả phù hợp (ví dụ redirect tới `/login` hoặc HTTP 401) chứ không tiếp tục phục vụ dữ liệu của principal trước đó?
3. **Các phiên khác**: nếu cùng một tài khoản đang đăng nhập tại trình duyệt B, máy C hoặc thiết bị khác, việc logout từ A **có chủ ý** giữ hay thu hồi những phiên đó? Nếu sản phẩm hứa hẹn "Đăng xuất khỏi mọi thiết bị" thì đã có cơ chế và test chứng minh thu hồi toàn bộ chưa?

Bài học này phân biệt:

- **Logout phiên hiện tại**: tác động cục bộ lên context/session của request đang logout.
- **Logout khỏi mọi phiên**: yêu cầu quản lý các session khác của cùng account, thường vượt khả năng mặc định của một request `/logout`.
- **Thu hồi remember-me/refresh token/JWT**: vòng đời credential khác với `JSESSIONID`, không tự hoàn tất chỉ nhờ xóa session.
- **Kiểm thử controller/Servlet filter** với `MockMvc` và **kiểm thử browser/HTTP thực tế** với cookie jar và session store.
- **Nhìn thấy trang cũ qua nút Back** và **server vẫn cấp dữ liệu sau logout** là hai hiện tượng khác nhau.

**Nguyên tắc:** một bài test tốt phải chứng minh **trạng thái bảo mật sau logout**, không chỉ kiểm tra có `302 Found`.

## 2. Logout ở đâu trong chuỗi Servlet security filters?

Trong Spring Security Servlet, các request đi qua `FilterChainProxy` và một `SecurityFilterChain` được chọn bằng matcher. Với form login session-based, `LogoutFilter` là thành phần xử lý request khớp logout URL trước khi tới MVC controller. Nó sử dụng một chuỗi `LogoutHandler` và `LogoutSuccessHandler` để thực hiện các công việc khác nhau.

```text
Browser                         Spring Security Servlet
   | POST /logout
   | cookie phiên + CSRF token hợp lệ
   +------------------------------------>
                                    CsrfFilter
                                      |
                           LogoutFilter (matcher đúng)
                                      |
                         SecurityContextLogoutHandler
                           - clear SecurityContext
                           - invalidate HttpSession
                             nếu được cấu hình
                                      |
                         LogoutHandler khác (nếu có)
                           - RememberMeServices
                           - cleanup theo ứng dụng
                                      |
                         LogoutSuccessHandler
                           - redirect /login?logout
                             hoặc response tùy biến
                                      |
   <----------------------------------+
   | 302 Location: /login?logout
   |
   | GET /account, không có phiên hợp lệ
   +------------------------------------>
                          Authorization trên /account
                                      |
                          AuthenticationEntryPoint
                                      |
   <----------------------------------+
   | 302 Location: /login (web form)
```

Sơ đồ mô tả logic chính; thứ tự từng logout handler, repository và các filter có thể tùy config/version. **CSRF validation có thể chặn `POST /logout` trước khi LogoutFilter hoạt động.**

Điểm cần hiểu:

- `LogoutFilter` nhận request theo `logoutRequestMatcher`/URL được cấu hình.
- `SecurityContextLogoutHandler` thường xóa `Authentication` trong context và invalidate HTTP session theo cấu hình. Với DSL logout thông thường, `invalidateHttpSession(true)` và `clearAuthentication(true)` là những lựa chọn chủ chốt.
- `LogoutSuccessHandler` chỉ tạo **kết quả HTTP** sau cleanup. Một 302 thành công không tự chứng minh server đã xóa tất cả session ở mọi thiết bị.
- Với CSRF bật, Spring Security thường yêu cầu **POST** (hoặc phương thức được cấu hình) để thực hiện logout; GET `/logout` có thể hiển thị trang xác nhận thay vì thực sự đăng xuất.
- `SecurityContextRepository` và session management quyết định cách authentication được lưu/khôi phục ở các request khác nhau.

## 3. Ma trận kết quả cần có trước khi viết test

Giả sử:

- `GET /account` chỉ cho người đã xác thực.
- `POST /logout` thực hiện logout với CSRF.
- Người dùng `learner` đăng nhập tại session A.
- Một session B độc lập (có thể của cùng user hoặc user khác) cũng đã login.

| Tình huống | Kết quả mong muốn | Điểm cần quan sát |
| --- | --- | --- |
| A gọi GET /account trước logout | HTTP 200 | A còn authentication |
| A gọi POST /logout và CSRF hợp lệ | 302 tới trang login/logout result | Logout request khớp filter và handler chạy |
| A sau logout gọi GET /account **không còn session auth** | Redirect login hoặc HTTP 401 theo chain | Không lộ nội dung protected |
| Browser cố gửi lại cookie session A cũ | Server không khôi phục authentication đã bị hủy | Cookie cũ không còn đại diện session hợp lệ |
| B gọi GET /account sau khi A logout | HTTP 200 **nếu policy chỉ logout A** | Không vô tình hủy session khác |
| B sau "logout all devices" | Không còn được coi là authenticated sau SLA revoke | Cơ chế revoke toàn bộ thực sự hoạt động |
| POST /logout thiếu CSRF | Thường HTTP 403 | Session A chưa bị logout bởi request đó |
| GET /logout với CSRF mặc định | Không tự hủy session nếu chỉ là trang xác nhận | GET không gây thay đổi trạng thái ngoài ý muốn |
| Nhấn Back sau logout | Có thể thấy UI cache; server không được cấp mới dữ liệu protected | Kiểm tra network/reload và cache policy |
| Cookie remember-me vẫn còn | Có thể khôi phục auth nếu chưa revoke | Cần test remember-me riêng |
| JWT đã phát hành trước logout | Có thể còn hợp lệ nếu chưa revoke/hết hạn | Không xem xóa session là revoke JWT |

**Chỉ chọn một policy** cho session B là chưa đủ: phải ghi rõ phạm vi sản phẩm ("đăng xuất trên thiết bị này" hay "tất cả thiết bị") rồi thiết kế tests đúng với lời hứa đó.

## 4. Authentication, SecurityContext, HttpSession và browser cookie không phải một đối tượng

Nắm rõ bốn lớp giúp tránh những test sai:

| Lớp | Được giữ ở đâu? | Logout bình thường tác động gì? |
| --- | --- | --- |
| `Authentication` | Trong `SecurityContext` | `clearAuthentication` dọn danh tính của context |
| `SecurityContext` | Theo request và `SecurityContextRepository` | Clear/remove theo logout handling |
| `HttpSession` | Servlet container hoặc shared session store | `invalidateHttpSession` hủy phiên hiện tại |
| Cookie `JSESSIONID` | Browser client | Có thể bị xóa qua Set-Cookie, nhưng **hủy server session mới là điều quyết định** |
| Remember-me cookie | Browser; có thể đối chiếu server token store | Logout services phải xử lý riêng |
| Access/refresh tokens | Browser/mobile/SDK, token store hoặc issuer | Logout local không tự thu hồi mọi token |

Một cookie session có thể còn hiện diện trong browser storage, hoặc client cố tình gửi ID cũ, nhưng server **không được** xem nó là phiên hợp lệ sau khi session đã invalidated. Ngược lại, xóa cookie phía browser mà không invalidating server session có thể chưa ngăn một người đã sao chép session ID sử dụng tiếp.

**Không test bằng cách nhìn thấy dòng `Set-Cookie: JSESSIONID=...; Max-Age=0` rồi kết luận server-side revoke đã hoàn tất.** Cookie deletion hữu ích nhưng không thay kiểm tra session server-side.

## 5. Logout mặc định khác logout-all

Khi một browser gọi `POST /logout` trong cấu hình form login thông thường, Spring Security tập trung vào **current security context/session**. Nó không tự duyệt tất cả `HttpSession` còn hoạt động của cùng username trên mọi JVM và vô hiệu hóa chúng.

Ví dụ:

```text
t0: learner đăng nhập trên Chrome -> session A
t1: learner đăng nhập trên Firefox -> session B
t2: Chrome gửi POST /logout kèm session A + CSRF hợp lệ
t3: session A bị invalidated
t4: Firefox còn session B -> vẫn xem /account được
```

Đây thường là **hành vi đúng** với nút "Đăng xuất" theo phiên. Nếu UI ghi "Đăng xuất khỏi tất cả thiết bị", cần một chức năng khác: theo dõi phiên theo tài khoản, đánh dấu/expire/invalidate các session liên quan qua store/registry phù hợp, thu hồi remember-me, refresh tokens và định nghĩa việc JWT đang còn hạn được xử lý thế nào.

Với Spring Security, có các cơ chế hỗ trợ như `SessionRegistry`, concurrent session control, `SessionInformation.expireNow()`, Spring Session và các session stores tập trung. Tuy nhiên, **`expireNow()` chủ yếu đánh dấu session để cơ chế tương ứng phát hiện**, không mặc nhiên xóa tức thì mọi server-side session trên mọi node. Với session storage phân tán, cần chính sách thu hồi và test theo kiến trúc triển khai.

### Đừng nhầm concurrent sessions với forced logout toàn bộ

`.maximumSessions(1)` là chính sách hạn chế số lượng phiên đăng nhập đồng thời (và cách xử lý phiên cũ/phát sinh) theo session registry. Nó **không** đồng nghĩa có một API chuẩn `logoutAllDevices()` tự hoàn tất mọi cơ chế credentials. Registry phải thực sự theo dõi sessions, event/session store hoạt động đúng và các request kế tiếp phải đi qua cơ chế xử lý expiration.

## 6. Ví dụ hoàn chỉnh: Spring Boot 3.x và Spring Security 6.x

Ta tạo một ứng dụng Servlet nhỏ dùng form login, session và endpoint `/account`. Hai user `learner` và `reviewer` giúp test hai session độc lập. Ví dụ giữ **CSRF bật** và dùng default logout process để thấy rõ sự khác biệt giữa request logout và các request kế tiếp.

### 6.1. Gradle dependencies

Trong dự án Spring Boot 3.x có Gradle plugin và dependency management phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 6.2. Tệp `src/main/java/example/logouttests/LogoutTestsApplication.java`

```java
package example.logouttests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LogoutTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutTestsApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/account").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            )
            // CSRF protection vẫn bật theo mặc định.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails reviewer = User.withUsername("reviewer")
            .password(encoder.encode("reviewer-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner, reviewer);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "Public";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "Hello " + authentication.getName();
    }
}
```

Chỉ `LogoutTestsApplication` là public top-level class; các class còn lại package-private nên một tệp Java 17 như trên là hợp lệ. `@SpringBootApplication` quét package `example.logouttests` và nhận security config cùng MVC controller.

**Điểm cần hiểu trong code:**

- `.formLogin(form -> form.permitAll())` bật form login Servlet; POST `/login` được authentication filter xử lý, không cần controller riêng.
- `.logout(...)` cấu hình URL và kết quả đăng xuất. `invalidateHttpSession(true)` hủy session hiện tại; `clearAuthentication(true)` dọn authentication khỏi security context.
- `logoutSuccessUrl("/login?logout")` chỉ điều hướng UI. Bài test vẫn phải xác minh session invalidation và request sau đó.
- CSRF được giữ mặc định: POST logout cần CSRF token hợp lệ. `GET /logout` có thể là trang xác nhận trong cấu hình chuẩn, không phải cách nên dùng để tạo side effect logout.
- `anyRequest().denyAll()` không mở thêm route ngoài nhu cầu demo; các URL cần cho `formLogin`/logout được cơ chế security config xử lý trước MVC authorization phù hợp.
- Password được encode trước khi đưa vào `InMemoryUserDetailsManager`. Tài khoản/password chỉ dành cho demo local; production cần identity store thật và HTTPS.

### 6.3. Chạy ứng dụng

Nếu project có Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell dùng `./gradlew.bat bootRun`. Sau khi server khởi động local, mở `http://localhost:8080/account`, đăng nhập với `learner` / `learner-pass`. Kết quả dự kiến:

```text
Hello learner
```

Nhấn logout theo form POST có CSRF token hợp lệ; sau đó mở lại `/account`. Kỳ vọng browser bị chuyển tới login page, chứ không tiếp tục nhận `Hello learner` từ server.

Đây là **hành vi dự kiến của cấu hình**, không phải output đã chạy thật. Browser URL, response Location và cookie flags có thể thay đổi bởi context path, reverse proxy, HTTPS và session store.

## 7. Viết integration test đúng: sử dụng `MockMvc` và `MockHttpSession`

`MockMvc` rất phù hợp để kiểm thử Servlet filter chain mà không cần mở cổng HTTP thật. Trong Spring Security Test:

- `.with(csrf())` tạo/sử dụng CSRF token hợp lệ cho các POST test.
- `.session(session)` gắn một `MockHttpSession` cụ thể vào request, giúp kiểm tra authenticated session giữa các lần gọi.
- `MockHttpSession.isInvalid()` cho biết phiên mock đã bị hủy qua `invalidate()`.
- `MockMvcResultMatchers` kiểm tra status/body/Location.
- `MockMvc` **không hoàn toàn mô phỏng browser cookie jar hoặc lookup session ID cũ qua một request cookie**; cần browser/HTTP integration test cho câu hỏi đó.

### 7.1. Tạo tệp `src/test/java/example/logouttests/LogoutFlowTest.java`

```java
package example.logouttests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutFlowTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session, "Form login should have a session");
        assertFalse(session.isInvalid());
        return session;
    }

    @Test
    void logoutInvalidatesCurrentSessionAndNextAnonymousRequestIsBlocked()
            throws Exception {

        MockHttpSession session = login("learner", "learner-pass");

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello learner"));

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login?logout")));

        // Kiểm tra server-side invalidation, không chỉ HTTP redirect.
        assertTrue(session.isInvalid());

        // Sau logout, request mới không có authenticated session.
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void anotherActiveSessionIsNotInvalidatedByLocalLogout()
            throws Exception {

        MockHttpSession sessionA =
            login("learner", "learner-pass");

        MockHttpSession sessionB =
            login("reviewer", "reviewer-pass");

        mvc.perform(get("/account").session(sessionA))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello learner"));

        mvc.perform(get("/account").session(sessionB))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello reviewer"));

        mvc.perform(post("/logout")
                .session(sessionA)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

        assertTrue(sessionA.isInvalid());
        assertFalse(sessionB.isInvalid());

        // Local logout của A không tự thu hồi session B.
        mvc.perform(get("/account").session(sessionB))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello reviewer"));
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndSessionRemainsAuthenticated()
            throws Exception {

        MockHttpSession session = login("learner", "learner-pass");

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello learner"));
    }

    @Test
    void anonymousAccessBeforeLoginRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void publicPageIsAccessibleAfterLogout()
            throws Exception {
        MockHttpSession session = login("learner", "learner-pass");

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("Public"));
    }
}
```

Chạy bằng Gradle:

```bash
./gradlew test
```

**Mức độ xác minh:** các kết quả trên là **assertion dự kiến theo ứng dụng mẫu**, chưa có lần compile/test nào được thực thi khi viết tài liệu này. `MockMvc` kiểm tra filter chain ở mock Servlet environment; muốn chứng minh việc trình duyệt gửi cookie ID cũ không được chấp nhận, phải kiểm tra thêm tại HTTP server/session store thật.

### 7.2. Vì sao test không gắn lại một `MockHttpSession` đã invalidated?

Sau `session.invalidate()`, đối tượng `MockHttpSession` đã bị đánh dấu invalid. Cố tiếp tục gọi:

```java
// Không dùng kiểu kiểm thử này làm bằng chứng browser có cookie cũ:
mvc.perform(get("/account").session(invalidatedSession));
```

có thể gây lỗi ở mô hình mock hoặc trộn khái niệm: một Java object session đã invalidated **khác** với HTTP request mang cookie `JSESSIONID` cũ. Trong browser thật, client chỉ gửi một chuỗi cookie; Servlet container hoặc session store phải xác định session ID đó đã hết hiệu lực và tạo/không tạo session mới theo policy.

Test đúng chia làm hai tầng:

1. **MockMvc**: chứng minh `MockHttpSession.isInvalid()==true` và request mới không có authentication không được truy cập.
2. **HTTP integration**: giữ lại raw session cookie cũ, gửi nó trong request sau logout và kiểm tra server không phục hồi user đã logout.

Tránh khẳng định test `MockMvc` không mang session tự nó chứng minh "stolen JSESSIONID đã bị revoke". Nó chỉ là một phần của chuỗi bằng chứng.

## 8. Kiểm thử độc lập nhiều phiên của **cùng một tài khoản**

Test session A = `learner`, session B = `reviewer` chứng minh isolation giữa hai phiên khác user. Nhưng yêu cầu thường gặp là **cùng một account đăng nhập ở nhiều thiết bị**. Cần thêm test rõ ràng cho trường hợp đó.

Đổi test dưới đây vào class `LogoutFlowTest` ở trên:

```java
@Test
void logoutOfOneOfTwoSessionsForSameUserKeepsOtherSession()
        throws Exception {

    MockHttpSession chrome =
        login("learner", "learner-pass");

    MockHttpSession firefox =
        login("learner", "learner-pass");

    mvc.perform(get("/account").session(chrome))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello learner"));

    mvc.perform(get("/account").session(firefox))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello learner"));

    mvc.perform(post("/logout").session(chrome).with(csrf()))
        .andExpect(status().is3xxRedirection());

    assertTrue(chrome.isInvalid());
    assertFalse(firefox.isInvalid());

    mvc.perform(get("/account").session(firefox))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello learner"));
}
```

Đoạn trên là **method bổ sung**, dùng `login`, `mvc` và static imports từ class test trước; không phải file độc lập. Với mặc định không giới hạn concurrency trong demo, hai sessions của cùng user có thể tồn tại song song.

Khi policy sản phẩm thay đổi thành "mỗi user chỉ một session" hoặc "logout all devices", **kỳ vọng của test phải đổi**. Không coi việc session B còn sống là lỗi nếu logout A được định nghĩa là local logout.

### Chú ý định danh session khác nhau

Trong kiểm thử session độc lập, không dùng lại cùng `MockHttpSession` để login hai lần, vì đó là **một client context**. Hai HTTP sessions cần xuất phát từ hai login requests không chia sẻ session, hoặc hai browser contexts/cookie jars độc lập. Trong deployment thật, dùng hai browser profiles hoặc hai cookie jars để tránh cookie session mới ghi đè cookie cũ.

## 9. Kiểm thử cookie cũ bằng HTTP server thực sự

Muốn trả lời "Client cố gửi lại JSESSIONID từ trước logout có được nhận không?", nên có một end-to-end test với Servlet container/HTTP session store thật.

Đề xuất quy trình:

```text
1. Client A (cookie jar A) GET /account -> nhận 302 tới /login.
2. Client A GET /login -> nhận HTML form và CSRF token.
3. Client A POST /login với username/password + CSRF token hợp lệ.
4. Lưu bản sao Cookie: JSESSIONID=<old-value> từ cookie jar A.
5. Client A GET /account -> HTTP 200, đúng principal.
6. Client A POST /logout với CSRF token hợp lệ.
7. Dùng client riêng (không được tái sử dụng authenticated session hiện tại)
   cố gửi Cookie: JSESSIONID=<old-value> trong GET /account.
8. Kỳ vọng không nhận dữ liệu protected:
   form login thường redirect /login;
   REST API có thể trả HTTP 401.
9. Client B với cookie jar B đăng nhập trước đó được kiểm tra theo
   chính sách "local logout" hay "logout all sessions".
```

Đây là **kịch bản kiểm thử**, không phải một script shell hoàn chỉnh: client phải lấy/giữ đúng CSRF token, session cookie, redirect và proxy context. Tránh một `curl -X POST /logout` thiếu CSRF token rồi kết luận logout đã thành công.

### Có thể sử dụng curl không?

Có, nhưng cần quản lý cookie jar và CSRF token đúng format của ứng dụng. Nếu chỉ dùng:

```bash
curl -i -X POST http://localhost:8080/logout
```

với CSRF protection đang bật thì request thường bị chặn (403). Điều đó **không** chứng minh session được invalidated. Trong automated HTTP tests có thể dùng `TestRestTemplate`, WebTestClient trên server chạy thật hoặc Java HTTP client, miễn thực hiện đúng token/cookie lifecycle. Với browser thực tế, DevTools Network giúp xem status/Location nhưng không nên log hoặc chia sẻ raw session IDs.

### Quan sát cookie ID cũ qua API gateway hoặc reverse proxy

Nếu hệ thống chạy sau gateway hoặc nhiều service nodes, phải kiểm tra request mang cookie cũ qua **đúng public URL và cùng session backend**. Một kết quả thành công trên node A không đủ chứng minh node B cũng biết session đã bị hủy nếu dùng local session stores hoặc replication trễ.

## 10. Trạng thái sau logout trong hệ thống nhiều node

Ví dụ server chạy sau load balancer:

```text
Browser A + JSESSIONID=S1
           |
     Load balancer
       /       \
      v         v
   Node A     Node B
     |           |
     +------ shared Spring Session store (ví dụ Redis)
                 |
             Session S1
```

Khi POST logout tới node A, nếu session state được lưu trong shared store và invalidation được thực thi đồng nhất, node B không được tiếp tục phục hồi authentication từ S1 cho request sau. Với local `HttpSession` không được chia sẻ, sticky sessions và node failover có thể gây behavior khác nhau; một test chỉ trên node A có thể bỏ sót lỗ hổng nhất quán.

Đối với Spring Session (ví dụ Redis-backed sessions), hãy thiết kế test:

- Tạo session trên node A, truy cập protected URL qua node B (theo routing test).
- Logout tại node A.
- Gửi lại cookie session cũ qua node B sau khi logout.
- Xác nhận backend không trả authenticated principal.
- Kiểm tra race giữa request protected đang xử lý và việc logout; định nghĩa thời điểm mà chính sách revoke được bảo đảm.
- Đo thời gian session invalidation có hiệu lực qua mọi node và session store.

**Đừng tự tuyên bố "logout có hiệu lực tức thì toàn cluster" nếu hệ thống dùng cache phiên bất đồng bộ**. Hãy xác định SLA và test qua public load-balancer path.

## 11. `SessionRegistry`, concurrent sessions và "logout all devices"

Một hệ thống muốn quản lý nhiều phiên phải có **bản đồ user → các sessions đang hoạt động**. Spring Security có cơ chế `SessionRegistry` và session-concurrency support, nhưng việc tìm/expire phiên còn phụ thuộc cấu hình session tracking.

Về mặt ý tưởng:

```java
// Pseudocode: cần SessionRegistry thực sự tracking sessions.
for (SessionInformation session :
        sessionRegistry.getAllSessions(principal, false)) {
    session.expireNow();
}
```

Đây là **fragment minh họa**, cần import `SessionRegistry`, `SessionInformation`, xác định cùng principal và đúng tracking strategy. Nó **không phải** một triển khai đầy đủ của logout-all.

Cần hiểu `expireNow()` trong cơ chế concurrent sessions thường đánh dấu phiên là expired; nó có thể được phát hiện và xử lý khi request tiếp theo đi qua `ConcurrentSessionFilter` hoặc cơ chế tương ứng. Điều này **khác với** xóa tức thì mọi key khỏi distributed session store. Nếu muốn chính sách revoke tức thì ở mọi node, có thể cần xóa trực tiếp sessions trong session repository hoặc một security-version check request-time, tùy Spring Session và kiến trúc.

### Đăng xuất tất cả thiết bị còn liên quan token khác

Nếu browser B có cả một `remember-me` cookie còn hợp lệ, việc hủy session B thôi có thể khiến remember-me filter **tái tạo authentication** cho request tiếp theo. Logout-all phải xem xét remember-me token revocation (persistent token repository phù hợp, key/version strategy đối với token-based), và phân biệt logout một thiết bị với tất cả.

Nếu mobile app C đang giữ JWT access token 15 phút, session registry ở Servlet web chain **không tự làm JWT hết hiệu lực**. Cần chính sách access-token expiry, refresh-token revocation, introspection, `jti` denylist hoặc token/account version check. Một SSO/OIDC IdP cũng có lifecycle riêng: local logout chưa chắc là IdP single logout.

## 12. Remember-me có thể làm xuất hiện "đăng nhập lại sau logout"

Một lỗi sản phẩm phổ biến là xóa HTTP session, nhưng **không thu hồi remember-me cookie**. Người dùng tưởng đã logout, sau đó GET `/account` không có session authentication sẽ đi qua `RememberMeAuthenticationFilter`, cookie nhớ đăng nhập hợp lệ và user lại được xác thực.

Vì thế, khi ứng dụng bật remember-me, thêm kiểm thử:

| Request/điều kiện | Kỳ vọng |
| --- | --- |
| Login có chọn checkbox remember-me | Server phát remember-me cookie hợp lệ |
| Session mất nhưng cookie còn hợp lệ | App có thể khôi phục remember-me theo policy |
| POST logout thành công | Xóa cookie remember-me tại browser và revoke server token theo implementation/policy |
| Browser gửi lại **bản sao cookie cũ** sau logout | Kỳ vọng phụ thuộc token-based/persistent strategy; phải test đúng threat model |
| Account bị khóa hoặc password bị thay | Cookie cũ bị chặn theo yêu cầu thời gian hiệu lực |
| Logout-all | Không còn active sessions hoặc remember-me/refresh tokens được phép sử dụng ngoài policy |

Với **token-based remember-me**, xóa cookie trong browser không tự hủy một bản sao đã bị đánh cắp; cookie có chữ ký hợp lệ có thể tiếp tục dùng tới expiry hoặc khi key/signature inputs thay đổi. Với **persistent tokens**, repository hỗ trợ thu hồi, nhưng phải xác nhận chính sách logout thực tế và xử lý concurrency.

Đừng viết test `assertNull(response.getCookie("remember-me"))` sau logout rồi cho rằng token đã bị thu hồi: response có thể chứa cookie với giá trị rỗng và Max-Age=0 để xóa cookie; việc cần kiểm tra là nội dung/thuộc tính Set-Cookie và server-side revocation.

## 13. Xóa cookie không đồng nghĩa hủy session

Có lúc developer thêm vào logout config:

```java
.logout(logout -> logout
    .deleteCookies("JSESSIONID")
)
```

Đây là **fragment DSL**, yêu cầu lớp/config phù hợp. Nó có thể gửi Set-Cookie để browser xóa cookie session, nhưng hiệu quả phụ thuộc cookie Path/Domain/Secure và reverse proxy. Trong nhiều trường hợp, default session invalidation đã là cơ sở quan trọng nhất; `deleteCookies` chỉ là lớp điều chỉnh browser cookie UX hoặc bổ sung vệ sinh cookie.

Để test mạnh, hãy kiểm tra:

1. `HttpSession` bị invalidated ở server.
2. Request mới không thể phục hồi `Authentication` cũ.
3. Nếu yêu cầu, browser nhận cookie deletion đúng `Path` và `Domain`.
4. Bản sao session cookie cũ bị server từ chối.
5. Các sessions khác vẫn/không còn hợp lệ đúng policy.

Tránh hai kiểu "false green":

- Test chỉ nhìn thấy Set-Cookie xóa cookie nhưng server vẫn giữ session.
- Test chỉ nhìn browser không có cookie nữa, rồi không bao giờ thử gửi lại session ID cũ để xác nhận server đã invalidated.

## 14. CSRF: không bỏ qua trong bài test logout

Một trong những lỗi phổ biến khi viết test:

```java
mvc.perform(post("/logout").session(session))
    .andExpect(status().is3xxRedirection());
```

Nếu CSRF bảo vệ POST, request này có thể trả **403** thay vì redirect. Đó không phải là lỗi logout handler. Spring Security Test giúp cung cấp CSRF token:

```java
mvc.perform(post("/logout")
        .session(session)
        .with(csrf()))
    .andExpect(status().is3xxRedirection());
```

Đây là fragment khi đã có `MockMvc mvc` và `MockHttpSession session`, không phải test độc lập.

**Không disable CSRF chỉ để đạt kết quả 302**. Với browser sử dụng session hoặc remember-me cookie tự động, CSRF mitigation vẫn có vai trò. Đừng dùng GET làm logout side effect chỉ để "tránh CSRF token": cross-site navigation có thể kích hoạt GET và gây forced logout của user.

Một test từ chối POST thiếu CSRF phải kiểm tra **session không bị hủy**. Nếu chỉ `status().isForbidden()` mà không kiểm tra session thì có thể bỏ sót một handler chạy quá sớm.

## 15. Sau logout bị đưa tới login nhưng frontend vẫn hiện dữ liệu cũ

Browser Back/Forward Cache (bfcache), HTTP cache, SPA state và service worker có thể giữ lại DOM/dữ liệu được render trước khi logout. Khi nhấn nút Back, user có thể thấy một trang cũ mà **không có request mới tới server**. Điều đó khác với việc GET protected resource sau logout được server phục vụ thành công.

Phương pháp kiểm tra:

1. Logout và bấm Back để quan sát UI.
2. Dùng DevTools Network kiểm tra có network request thực hay không.
3. Bật reload/navigate trực tiếp protected URL sau logout.
4. Xác minh server trả redirect login/401, không trả dữ liệu private mới.
5. Kiểm tra response headers `Cache-Control` của tài nguyên nhạy cảm; `no-store` có thể cần cho dữ liệu không được lưu.
6. Với SPA, xóa client-side auth state/cache, reset query stores và tránh render stale user data; nhưng không thay thế server authorization.
7. Với service worker, kiểm tra caching strategy để không cache private authenticated responses ngoài chủ đích.

Spring Security thường thiết lập các security headers và cache-control defaults phù hợp, nhưng **không nên coi chúng là bằng chứng tự động rằng mọi CDN, reverse proxy, browser cache và service worker đều tuân theo policy dữ liệu nhạy cảm**. Test thực tế cho đường đi triển khai mới đủ.

### Ví dụ request phải được kiểm tra

```http
GET /account HTTP/1.1
Host: app.example
Cookie: JSESSIONID=<old-session-id>
```

Kỳ vọng sau logout là **server không chấp nhận session ID cũ như authentication hợp lệ**. Mã HTTP có thể là 302 tới login (form-based), 401 với API entry point, hoặc một kết quả tùy biến đã được thiết kế. Không coi một status cố định là bằng chứng nếu frontend/proxy có thể trả trang login như 200.

## 16. Logout và request đang chạy đồng thời

Giả sử một request thay đổi trạng thái đã được server xác thực lúc t0, sau đó người dùng logout ở t1, rồi request cũ hoàn tất ở t2. Logout ở t1 **không tự rollback** một transaction đã bắt đầu trước đó và không hủy mọi thread đang xử lý.

```text
t0: POST /transfer đi vào server với session S
t1: Server kiểm tra authorization, bắt đầu transaction
t2: Browser gửi POST /logout, session S bị invalidated
t3: Transaction /transfer hoàn thành theo dữ liệu/khóa đã kiểm tra
```

Yêu cầu "không có hành động nào sau logout" phải được định nghĩa chính xác theo **thời điểm bắt đầu**, **thời điểm authorization**, **thời điểm commit** và loại giao dịch. Với nghiệp vụ rủi ro cao, có thể cần revocation/version check ngay trước commit hoặc ràng buộc transaction theo policy, không chỉ dựa vào session invalidation.

Các trường hợp nên test:

- Logout đồng thời với request protected trên cùng session.
- Logout trong một node, request đang xử lý tại node khác.
- Request tới sau khi session đã bị invalidated nhưng mang cookie cũ.
- Token bị revoke giữa lúc request đã được xác thực và trước lúc hành động được commit.

Không tuyên bố một test tuần tự GET → logout → GET đã chứng minh hệ thống không có race condition.

## 17. HTTP status, handler và cách tránh chẩn đoán sai

| Kết quả | Một số nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| POST logout trả 302 | LogoutSuccessHandler redirect | Session thật sự invalidated chưa? |
| POST logout trả 403 | Thiếu/sai CSRF token, authorization khác | CSRF/LogoutFilter matcher, session có còn không? |
| GET /account sau logout trả 302 | AuthenticationEntryPoint mở lại login | Có đúng /login? Có leak private data không? |
| GET /account sau logout trả 401 | API/basic/bearer entry point thách thức xác thực | Contract của API và body/headers |
| GET /account sau logout vẫn trả 200 | Session/token khác còn hợp lệ, endpoint public hoặc cache response | Authentication type, cookie, remember-me, rules, proxy |
| GET /account trả 403 | Principal có thể authenticated nhưng thiếu quyền, hoặc custom handler | Không suy chỉ từ status rằng logout thất bại |
| GET /logout trả trang xác nhận | CSRF bật, default logout confirmation | GET có làm side effect không? |
| Node A từ chối, node B chấp nhận cookie cũ | Session store không đồng bộ, stale cache | Shared store/invalidation |
| Session A mất, session B vẫn hợp lệ | Local logout theo chính sách | Nếu muốn all-devices cần cơ chế khác |
| Browser Back vẫn hiện nội dung | bfcache/client state | Network reload và Cache-Control |

**Luôn ghi rõ** client, method, URL, security chain, loại authentication trước/sau, session ID được **ẩn/redact**, status và behavior của login entry point. Không gửi raw cookie hoặc token vào log/CI artifacts.

## 18. Kịch bản regression test cho môi trường sản xuất

Một bảng checklist nghiệm thu theo mức độ:

| Nhóm | Test case | Tiêu chí pass |
| --- | --- | --- |
| Happy path | Login form → GET protected → POST logout → GET protected | Trước 200, sau không được cấp dữ liệu private |
| Cleanup | Logout với valid CSRF | Current server session invalidated và context được clear |
| CSRF | Logout thiếu/sai CSRF | 403, session vẫn dùng được nếu policy CSRF chặn |
| Method | GET logout | Không tự logout nếu CSRF-enabled default confirmation |
| Isolation | A logout, B thuộc user khác vẫn login | B không bị ảnh hưởng |
| Same user | Session A và B của cùng user, chỉ logout A | B còn nếu policy local logout |
| All devices | A dùng chức năng logout-all | A/B/C bị revoke theo SLA |
| Replay | Dùng lại JSESSIONID cũ sau logout | Không khôi phục principal cũ |
| Remember me | Session bị hủy nhưng cookie nhớ đăng nhập còn | Theo policy, không tự tạo bypass sau logout |
| Tokens | JWT/refresh token đã phát hành | Revoke/expiry đúng security contract |
| Cluster | Logout ở node A, request cookie cũ tới node B | B không phục hồi auth đã bị hủy |
| Proxy | HTTPS, cookie Path/Domain/Secure | Browser nhận cookie cleanup phù hợp |
| UI | Back/reload sau logout | Không có dữ liệu nhạy cảm được server cấp mới |
| Concurrent | Request protected chạy cùng logout | Hành vi theo thời điểm commit/revoke đã định nghĩa |
| Audit | Logout event và revoke logs | Không in session ID/token/password |
| Accessibility | UI trạng thái logout | Người dùng hiểu mình đã logout phiên nào |

Các test mức "all devices", "cluster" hoặc "token revocation" cần **môi trường và implementation thực sự**; ví dụ Boot/MockMvc trong bài chỉ chứng minh local Servlet session behavior, không tự thỏa mọi mục trên.

## 19. Bài tập ôn tập có đáp án

**Câu 1.** Vì sao chỉ assert HTTP 302 của POST /logout chưa đủ?

**Đáp án:** 302 là phản hồi do success handler tạo. Cần xác nhận session/context bị xóa và các request protected tiếp theo không còn dùng identity cũ.

**Câu 2.** Một user đăng nhập ở hai browser A và B. A logout. B còn truy cập được `/account`. Đây có phải bug?

**Đáp án:** Không nếu chức năng là local logout. Nếu UI hứa "logout all devices" thì B còn hợp lệ là dấu hiệu cơ chế revoke-all chưa đạt yêu cầu.

**Câu 3.** Vì sao không nên truyền lại một `MockHttpSession` đã bị invalidated vào `MockMvc.perform(...session(...))` để mô phỏng stolen cookie?

**Đáp án:** MockHttpSession là object server-side đã invalid; browser thực tế chỉ gửi cookie ID. Phải kiểm thử replay cookie tại HTTP server/session store thật.

**Câu 4.** POST logout thiếu CSRF trả 403. Session có nên bị hủy không?

**Đáp án:** Với cấu hình CSRF chặn trước LogoutFilter, session không nên bị hủy vì logout không được thực hiện. Test cả status và session validity.

**Câu 5.** Xóa cookie `JSESSIONID` bằng `deleteCookies` có ngăn người giữ bản sao ID cũ không?

**Đáp án:** Không chắc. Server phải invalidate session hoặc revoke ở session store; cookie deletion đơn thuần là client-side hygiene.

**Câu 6.** Sau logout, browser Back hiện nội dung cũ nhưng reload protected URL chuyển về login. Điều đó chứng minh điều gì?

**Đáp án:** Có thể là browser/client cache còn snapshot UI, trong khi server đã chặn request mới. Cần chính sách cache cho dữ liệu nhạy cảm và xử lý client state, không kết luận server session còn hoạt động chỉ từ Back.

**Câu 7.** Vì sao một cookie remember-me có thể khiến user trông như "chưa logout"?

**Đáp án:** Nếu remember-me chưa được thu hồi, request không có authenticated session có thể được filter nhớ đăng nhập khôi phục. Logout cần xử lý remember-me services/token policy riêng.

**Câu 8.** `SessionInformation.expireNow()` có lập tức xóa mọi session khỏi Redis hoặc database không?

**Đáp án:** Không được giả định như vậy. Trong nhiều cấu hình nó đánh dấu expired để filter xử lý ở request kế tiếp. Revoke tức thời qua cluster cần cơ chế tương ứng ở session store.

**Câu 9.** Mobile app giữ JWT còn hạn sau khi browser logout. Có phải lỗi của `SecurityContextLogoutHandler`?

**Đáp án:** Không. Local Servlet session logout không tự thu hồi JWT/refresh tokens. Nếu yêu cầu logout-all, phải bổ sung token revoke/expiry/version policy.

**Câu 10.** Một request thay đổi dữ liệu đã vượt qua authorization trước lúc logout rồi commit sau logout. Có thể tuyên bố đây luôn là lỗ hổng không?

**Đáp án:** Không thể kết luận chỉ từ thứ tự thời gian. Cần định nghĩa consistency/revocation policy cho request đang chạy, áp dụng version/recheck/transaction coordination nếu nghiệp vụ đòi chặn trước commit.

## 20. Checklist thực hiện và kiểm thử logout

- [ ] Xác định chính xác ý nghĩa sản phẩm: **logout phiên hiện tại** hay **logout tất cả phiên/thiết bị**.
- [ ] Xác nhận `LogoutFilter` có trong đúng `SecurityFilterChain` và request khớp method/path.
- [ ] Với form login cookie/session, giữ CSRF protection và test POST hợp lệ/thiếu token.
- [ ] Sau POST logout, assert session invalidated và authentication không còn ở request tiếp theo.
- [ ] Test client còn cố gửi raw session cookie cũ qua HTTP server thực tế.
- [ ] Test session B khác user và session B cùng user theo đúng policy.
- [ ] Nếu có logout-all, test registry/session store thu hồi qua mọi node sau SLA được công bố.
- [ ] Remember-me cookie/token bị dọn hoặc thu hồi phù hợp; không chỉ xóa `JSESSIONID`.
- [ ] Refresh tokens/JWT/OIDC logout có policy riêng; không tuyên bố tự mất hiệu lực.
- [ ] Không dùng `GET /logout` để gây thay đổi trạng thái chỉ vì tiện.
- [ ] Protected resources trả redirect/401/403 theo contract, **không trả private data** sau logout.
- [ ] Browser Back, bfcache, SPA cache, service worker và Cache-Control được kiểm thử.
- [ ] Reverse proxy/shared session store không giữ authentication đã bị revoked.
- [ ] Có test concurrent request/logout khi cần revoke có SLA nghiêm ngặt.
- [ ] Audit đủ để quan sát nhưng **không log raw cookie, session ID, token hoặc password**.
- [ ] Code test dùng `MockMvc` đúng với `.with(csrf())` và độc lập các `MockHttpSession`.
- [ ] Browser/integration tests bổ sung cho hạn chế của MockMvc.

## Kết luận

Một logout đáng tin không được chứng minh bằng **redirect duy nhất**. Trong Spring Security Servlet, cần kiểm chứng `LogoutFilter` thực thi cleanup, **phiên hiện tại** bị invalidated, và **request protected sau logout** không còn nhận authentication cũ. Đồng thời, các phiên khác phải được giữ hay thu hồi **đúng định nghĩa tính năng**.

Sử dụng `MockMvc` để test security filter chain, CSRF, `MockHttpSession.isInvalid()` và session isolation. Dùng HTTP/browser integration test để chứng minh cookie ID cũ thực sự bị server từ chối, cùng kiểm tra cluster, remember-me và token revocation nếu hệ thống có. **Phân biệt local logout, logout-all và token revoke** là điều kiện để tránh các bài test "xanh" nhưng trải nghiệm hoặc bảo mật thực tế vẫn sai.
