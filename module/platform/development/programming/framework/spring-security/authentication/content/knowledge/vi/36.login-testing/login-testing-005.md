# Kiểm thử đăng nhập: CSRF token, cookie phiên và phản hồi chuyển hướng

## 1. Mục tiêu và phạm vi

Trong một ứng dụng **Spring Security Servlet** dùng form login, kiểm tra “đăng nhập đúng username/password nhận HTTP 302” **chưa đủ**. Một luồng đăng nhập đáng tin phải kiểm đồng thời:

1. **CSRF token:** POST login, logout và các request thay đổi trạng thái phải có token hợp lệ theo chính sách CSRF; request giả mạo từ trang khác không được dựa vào cookie của người dùng để vượt kiểm soát.
2. **Cookie phiên:** browser giữ identifier như `JSESSIONID`, server khôi phục `SecurityContext` theo phiên; session fixation protection đổi identifier khi xác thực.
3. **Redirect:** HTTP 302 cùng header `Location` có thể là yêu cầu tới trang login, báo password sai, đích thành công hoặc quay lại tài nguyên được yêu cầu trước khi login.

**Ba cơ chế không thay thế nhau.** CSRF token không phải password hay session identifier; cookie phiên tự được browser gửi không chứng minh request hợp lệ; 302 không có nghĩa user đã login thành công.

Bài học tập trung vào **Kiểm thử đăng nhập** bằng **Java 17+ / Spring Boot 3.5.x / Spring Security 6.5.x / Spring MVC / JUnit 5 / MockMvc**, có Maven project đầy đủ, 14 test cases và các bước kiểm cookie/redirect bằng HTTP thật. Với OAuth Bearer Resource Server stateless hoặc WebFlux cần dùng phương pháp phù hợp riêng, không áp mặc định toàn bộ kỳ vọng JSESSIONID và redirect của Servlet form login.

## 2. Luồng request/response cần hiểu

~~~text
Browser                         Spring Security                      Ứng dụng
   |                                  |                                 |
   | GET /dashboard                   |                                 |
   |--------------------------------->| chưa authenticated              |
   |                                  | lưu GET vào RequestCache        |
   |<---------------------------------| 302 Location: /login            |
   | GET /login                       |                                 |
   |--------------------------------->| render form có CSRF token       |
   |<---------------------------------| 200 HTML + _csrf                |
   |                                  | session tùy repository          |
   | POST /login                      |                                 |
   | Cookie: JSESSIONID=...           |                                 |
   | username/password/_csrf          |                                 |
   |--------------------------------->| CsrfFilter kiểm token           |
   |                                  | UsernamePasswordAuthentication  |
   |                                  | AuthenticationManager           |
   |                                  | SessionAuthenticationStrategy   |
   |                                  | lưu SecurityContext             |
   |<---------------------------------| 302 Location: /dashboard        |
   |                                  | đổi session ID chống fixation   |
   | GET /dashboard + cookie phiên    |                                 |
   |--------------------------------->| load SecurityContext           |
   |                                  |-------------------------------> |
   |<---------------------------------| 200 dashboard                   |
~~~

Nếu user mở trực tiếp trang login mà **không có saved request**, thành công thường redirect tới default target (ví dụ `/home`). Nếu trước đó đã vào tài nguyên bị chặn, `SavedRequestAwareAuthenticationSuccessHandler` có thể redirect về tài nguyên ban đầu.

### 2.1. Các thành phần liên quan

| Thành phần | Vai trò | Điều cần test |
| --- | --- | --- |
| `CsrfFilter` | Chặn request unsafe thiếu/sai CSRF | 403 khi thiếu/sai; cho qua khi token hợp lệ |
| `CsrfTokenRepository` | Lưu expected token | Session hoặc cookie đúng theo cấu hình |
| `CsrfTokenRequestHandler` | Resolve token trong parameter/header | Hidden field, header, XOR/BREACH |
| `UsernamePasswordAuthenticationFilter` | Nhận POST /login | Đúng parameter name và login URL |
| `AuthenticationManager` | Kiểm username/password | Đúng và sai credential |
| `SecurityContextRepository` | Lưu/khôi phục authentication | Request sau login vẫn authenticated |
| `SessionAuthenticationStrategy` | Chống session fixation | Identifier thay khi login |
| `ExceptionTranslationFilter` | Kích hoạt login entry point | 302 tới /login |
| `RequestCache` | Lưu URL muốn tới trước login | Saved request thắng default target |
| `AuthenticationSuccessHandler` | Quyết định redirect khi thành công | 302 đúng Location |
| `AuthenticationFailureHandler` | Quyết định redirect khi sai password | 302 /login?error |
| `LogoutFilter` | Logout và xóa session/context | POST logout có CSRF, redirect và invalidation |

Điểm dễ nhầm: **CSRF kiểm trước credential** trong flow thông thường. POST login thiếu CSRF nhận 403 không có nghĩa password sai. Spring Security form login cũng có thể trả redirect khi authentication failure; đó không phải 401 như HTTP Basic hoặc Bearer.

## 3. CSRF token là gì, khác cookie phiên thế nào?

Cookie session thường được browser tự đính kèm vào request theo domain/path/SameSite policy. Điều đó tạo nguy cơ **Cross-Site Request Forgery (CSRF)**: một trang độc hại kích hoạt request tới trang đang đăng nhập và lợi dụng cookie được gửi tự động. Ví dụ: gửi POST đổi địa chỉ liên hệ, logout hoặc **login CSRF** làm nạn nhân sử dụng account do attacker kiểm soát.

Spring Security phát CSRF token khó đoán, lưu expected value phía server hoặc qua repository đã cấu hình, và đòi client trình token ở request thay đổi trạng thái.

**Không đánh đồng:**

- `JSESSIONID`: identifier của session. Nó liên kết request với session state, bao gồm `SecurityContext`, nhưng bản thân cookie không chứa username/password khi dùng HttpSession mặc định.
- `_csrf`: hidden form parameter chứa CSRF token được render trong form.
- `X-CSRF-TOKEN` / `X-XSRF-TOKEN`: request headers có thể dùng để trình token theo repository/config.
- `XSRF-TOKEN`: tên cookie của `CookieCsrfTokenRepository`, khác session cookie.
- Password/OTP: credential để authenticate người dùng; CSRF token **không phải authentication**.

### 3.1. Phương thức nào yêu cầu CSRF?

Spring Security mặc định bảo vệ HTTP methods không an toàn. GET, HEAD, OPTIONS, TRACE là những method không bắt buộc CSRF theo matcher mặc định; POST, PUT, PATCH, DELETE thường bắt buộc.

| Request | CSRF mặc định | Lưu ý |
| --- | --- | --- |
| GET /login | Không | Render token trong form |
| POST /login | Có | Đăng nhập cũng có nguy cơ login CSRF |
| GET /dashboard | Không | Chỉ đọc dữ liệu |
| POST /profile | Có | Thay đổi state |
| POST /logout | Có | Ngăn logout CSRF |
| DELETE /profile | Có | Không phải GET |
| GET /dangerous-delete | Không theo matcher | **Thiết kế sai** nếu GET thay đổi state |

Không chuyển tác vụ nhạy cảm sang GET chỉ để khỏi gửi CSRF token.

### 3.2. Thiếu, sai và đúng CSRF

Với POST login:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_ID

username=learner&password=lab-password
~~~

**Thiếu CSRF**: thường HTTP 403. Dù password đúng, token vẫn thiếu nên `CsrfFilter` chặn trước authentication.

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_ID

username=learner&password=lab-password&_csrf=INVALID
~~~

**CSRF sai**: thường HTTP 403. Với token thực của đúng repository/phiên và credentials đúng, login mới có thể thành công và trả redirect 302.

Các chuỗi SESSION_ID/INVALID chỉ minh họa, không phải credential thật.

## 4. Deferred CSRF, XOR và CookieCsrfTokenRepository ở Spring Security 6

### 4.1. HttpSessionCsrfTokenRepository mặc định

Spring Security Servlet thường dùng `HttpSessionCsrfTokenRepository`: expected token nằm trong HTTP session phía server. Khi view cần hiển thị hidden input, Spring đưa token vào request attribute. Form gửi lại token và session cookie, server so sánh với expected token.

Từ Spring Security 6, CSRF token **deferred** theo mặc định: GET không cần token không nhất thiết load/create session chỉ vì Spring Security. Khi render form hoặc xử lý unsafe method, token được dùng và có thể tạo session.

`XorCsrfTokenRequestAttributeHandler` là handler mặc định chống rủi ro BREACH bằng cách biểu diễn token có randomness. Vì vậy:

- Không hard-code giá trị token trong unit/integration test.
- Giá trị token render ra form ở các lần khác nhau có thể khác biểu diễn.
- Không nhất thiết token HTML bằng một chuỗi đọc trực tiếp từ session attribute.
- Kiểm request **thực sự được chấp nhận** thay vì chỉ so chuỗi token.
- Login/logout có thể khiến CSRF token cũ bị clear/rotate, đặc biệt quan trọng với SPA.

### 4.2. CookieCsrfTokenRepository và SPA

Một số SPA đọc CSRF token ở cookie `XSRF-TOKEN` và gửi header `X-XSRF-TOKEN`. Cấu hình có thể dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` để JavaScript đọc **cookie CSRF**.

~~~text
Cookie: XSRF-TOKEN=<csrf-token>
X-XSRF-TOKEN: <csrf-token>
~~~

**Không áp `HttpOnly=false` cho `JSESSIONID`** chỉ vì JS cần CSRF. Cookie phiên là session credential và nên HttpOnly.

Spring Security 6 có xử lý riêng cho **raw token trong cookie**, **XOR encoded token trong HTML** và deferred loading; SPA thường cần `CsrfTokenRequestHandler` tùy chỉnh như tài liệu chính thức để resolver header đúng, đồng thời lấy cookie CSRF mới sau login/logout. Chỉ đổi sang CookieCsrfTokenRepository rồi bỏ qua phần này có thể dẫn đến POST 403.

CORS không tự chống CSRF: cross-origin form submissions có thể diễn ra mà attacker không cần đọc response; SameSite và Origin checks là các biện pháp bổ sung, không thay thế chính sách CSRF theo threat model.

## 5. Session cookie và các thuộc tính cần kiểm

Trong Spring Boot Servlet/Tomcat thường gặp:

~~~http
Set-Cookie: JSESSIONID=REDACTED; Path=/; HttpOnly
Cookie: JSESSIONID=REDACTED
~~~

Giá trị session ID là một chuỗi opaque; server dùng để tra session, không phải JWT chứa thông tin người dùng.

| Thuộc tính | Ý nghĩa | Kiểm chứng |
| --- | --- | --- |
| `HttpOnly` | JavaScript không được đọc cookie phiên | Xem Set-Cookie thực tế |
| `Secure` | Chỉ gửi qua HTTPS | Test public HTTPS ingress |
| `SameSite` | Điều chỉnh cross-site cookie behavior | Kiểm policy Lax/Strict/None phù hợp |
| `Path` | Cookie gửi trong path nào | Không scope quá rộng |
| `Domain` | Domain cookie hợp lệ | Không tự mở rộng mọi subdomain |
| `Expires`/`Max-Age` | Session hoặc persistent lifetime | Không mặc định session cookie có Max-Age |
| ID rotation | Chống session fixation | So session ID trước/sau authentication |

Các flag cuối cùng có thể do embedded container, Spring Session hoặc reverse proxy định hình; **đọc Set-Cookie ở HTTP thật**, không chỉ MockMvc.

### 5.1. Session fixation

Attacker cố ép user sử dụng session ID đã biết trước, chờ user đăng nhập rồi tái sử dụng ID đó. Spring Security mặc định chống fixation bằng thay session ID khi authentication thành công; trên Servlet 3.1+ sử dụng `changeSessionId()`.

Test nên tạo một session trước login (có thể do saved request/CSRF), ghi nhận ID; thực hiện login hợp lệ và xác nhận ID mới **khác ID cũ**, trong khi request kế tiếp với session mới vẫn authenticated.

Cookie tồn tại **trước login** không có nghĩa user đã authenticated. Dấu hiệu cần kiểm là GET protected sau login thành công và session fixation protection, không chỉ có header Set-Cookie.

### 5.2. MockMvc session khác trình duyệt thật

`MockMvc` dùng `MockHttpSession`, giả lập Servlet request/filter/response mà không cung cấp nguyên vẹn cookie jar và network/container behavior. Vì vậy:

- MockMvc **không tự follow** redirect; mỗi request phải được test tự gửi.
- MockMvc không tự giữ cookie như trình duyệt; muốn mô phỏng cùng session cần truyền `.session(session)`.
- Không coi việc không thấy `Set-Cookie: JSESSIONID` trong MockMvc là lỗi Spring Security.
- Không kết luận flags Secure/HttpOnly/SameSite production chỉ từ MockMvc.
- Với test Set-Cookie, cần embedded Tomcat/HTTP client hoặc browser E2E qua HTTPS proxy.

## 6. HTTP 302: điều gì cần kiểm ngoài status?

| Request | Điều kiện | Response thường gặp |
| --- | --- | --- |
| GET /dashboard | Chưa login | 302 Location: /login |
| GET /login | Chưa login | 200 HTML chứa _csrf |
| POST /login | CSRF thiếu hoặc sai | 403 |
| POST /login | CSRF đúng, password sai | 302 Location: /login?error |
| POST /login | CSRF đúng, password đúng, login trực tiếp | 302 Location: /home (ví dụ này) |
| POST /login | Password đúng, có saved request | 302 về saved path |
| GET /dashboard | Session đã authenticated | 200 |
| POST /logout | CSRF đúng | 302 Location: /login?logout |
| POST /logout | CSRF thiếu/sai | 403 |

**302 không tự chứng minh đăng nhập thành công:** redirect cũng dùng khi chưa login hoặc sai password. Luôn assert **Location, session và request tiếp theo**.

### 6.1. RequestCache và saved request

Một request GET tới tài nguyên bảo vệ khi chưa authenticated có thể được `ExceptionTranslationFilter` lưu trong `HttpSessionRequestCache`. Sau khi xác thực thành công, `SavedRequestAwareAuthenticationSuccessHandler` thường đưa user trở lại URL đó thay vì default success target.

~~~text
GET /dashboard       -> 302 /login  (lưu saved request)
GET /login           -> 200
POST /login          -> 302 /dashboard (saved request)
GET /dashboard       -> 200
~~~

Nếu user mở trang login trực tiếp:

~~~text
GET /login           -> 200
POST /login          -> 302 /home (default target)
~~~

Cùng là login đúng nhưng **hai Location khác nhau**. URL redirect có thể là absolute URL hoặc có marker/query tùy Spring version/config, nên test saved request nên kiểm đích một cách hợp lý, không quá phụ thuộc biểu diễn relative/absolute.

### 6.2. Open redirect, proxy và entry point

- Không lấy `returnUrl` hay `next` của client rồi đưa thẳng vào `sendRedirect`; attacker có thể dùng open redirect tới domain lạ.
- Nếu hỗ trợ redirect tùy biến, dùng allowlist exact trusted URL/origin hoặc relative internal paths, xử lý protocol-relative URL và encoding.
- Khi app sau ingress TLS, kiểm `Location` dùng public HTTPS host, không trả http://internal-host:8080; trusted forwarded headers chỉ nhận từ proxy tin cậy.
- Nếu có nhiều `SecurityFilterChain`, web form thường trả 302 login, còn API Bearer có thể trả 401; kiểm chain order và matcher.

## 7. Project Maven Spring Boot (Java 17+) kiểm thử đăng nhập

Ta tạo ứng dụng học tập:

- Tài khoản `learner` / `lab-password`, role USER.
- GET `/health` public.
- GET `/home`, `/dashboard` protected.
- POST `/profile` protected và CSRF enabled.
- Form login mặc định, direct login success redirect `/home` (nếu không có saved request).
- POST /logout mặc định có CSRF và redirect `/login?logout`.

Dùng Spring Boot **3.5.x** với Spring Security **6.5.x** do Boot BOM quản lý. Mật khẩu `{noop}` chỉ cho lab; production dùng PasswordEncoder hash và credential store phù hợp.

### 7.1. Cấu trúc tệp

~~~text
login-flow-lab/
├── pom.xml
└── src/
    ├── main/java/demo/login/LoginFlowApplication.java
    └── test/java/demo/login/LoginFlowTests.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>login-flow-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 7.3. LoginFlowApplication.java

~~~java
package demo.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginFlowApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        var user = User.withUsername("learner")
            .password("{noop}lab-password")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/home", "/dashboard", "/profile")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form.defaultSuccessUrl("/home", false))
            .logout(Customizer.withDefaults());

        // CSRF vẫn bật mặc định. Không gọi csrf.disable().
        return http.build();
    }

    @RestController
    static class AppApi {
        @GetMapping("/health")
        String health() {
            return "ready";
        }

        @GetMapping("/home")
        String home(Authentication auth) {
            return "home:" + auth.getName();
        }

        @GetMapping("/dashboard")
        String dashboard(Authentication auth) {
            return "dashboard:" + auth.getName();
        }

        @PostMapping("/profile")
        String changeProfile(Authentication auth) {
            // Chỉ minh họa: không thay database thật.
            return "updated:" + auth.getName();
        }
    }
}
~~~

Vì có `SecurityFilterChain` tùy chỉnh, phải gọi `.formLogin(...)` tường minh. Generated login page của Spring xử lý `GET /login` và `POST /login`. CSRF mặc định được giữ nguyên. Route `/profile` chỉ có POST và cần authentication + token CSRF.

## 8. JUnit 5 và MockMvc: 14 ca kiểm thử

Tệp `src/test/java/demo/login/LoginFlowTests.java`:

~~~java
package demo.login;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFlowTests {

    @Autowired
    MockMvc mvc;

    private static final String USER = "learner";
    private static final String PASS = "lab-password";

    private MvcResult login() throws Exception {
        return mvc.perform(post("/login")
                .param("username", USER)
                .param("password", PASS)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void anonymousProtectedGetRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void loginFormContainsCsrfField() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void correctPasswordWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", USER)
                .param("password", PASS))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", USER)
                .param("password", PASS)
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidPasswordWithCsrfRedirectsToError() throws Exception {
        mvc.perform(post("/login")
                .param("username", USER)
                .param("password", "wrong-password")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void directLoginRedirectsHomeAndPersistsSession()
            throws Exception {
        MvcResult result = login();
        assertEquals("/home", result.getResponse().getRedirectedUrl());

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);
        mvc.perform(get("/dashboard")
                .session((MockHttpSession) session))
            .andExpect(status().isOk())
            .andExpect(content().string("dashboard:learner"));
    }

    @Test
    void savedRequestIsRestoredAndSessionIdChanges()
            throws Exception {
        MvcResult first = mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(session);
        String oldId = session.getId();

        MvcResult signedIn = mvc.perform(post("/login")
                .session(session)
                .param("username", USER)
                .param("password", PASS)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = signedIn.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.contains("/dashboard"));
        HttpSession after = signedIn.getRequest().getSession(false);
        assertNotNull(after);
        assertNotEquals(oldId, after.getId());
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/profile").with(user(USER)))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithInvalidCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/profile")
                .with(user(USER))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithHeaderCsrfSucceeds()
            throws Exception {
        mvc.perform(post("/profile")
                .with(user(USER))
                .with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(content().string("updated:learner"));
    }

    @Test
    void validCsrfAloneDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/profile").with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void logoutWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/logout").with(user(USER)))
            .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithCsrfRedirectsAndInvalidatesSession()
            throws Exception {
        MvcResult loggedIn = login();
        MockHttpSession session =
            (MockHttpSession) loggedIn.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());
    }
}
~~~

### 8.1. Ý nghĩa cụ thể của 14 ca test

| Test | Chứng minh |
| --- | --- |
| Public /health | Đường dẫn public không cần login |
| GET /dashboard anonymous | Login entry point redirect tới /login |
| GET /login | Generated form có CSRF hidden input |
| POST /login đúng password thiếu CSRF | CSRF chặn trước khi credentials được chấp nhận |
| POST /login token sai | Invalid token bị từ chối |
| POST /login valid CSRF, password sai | Failure handler redirect /login?error |
| Direct login valid | Redirect /home và session giữ authenticated context |
| Saved request login | Quay về dashboard và đổi session ID |
| Authenticated POST thiếu CSRF | Bị 403 |
| Authenticated POST sai CSRF | Bị 403 |
| Authenticated POST có CSRF header | Controller chạy, status 200 |
| Anonymous POST có CSRF | Vẫn cần login, CSRF không thay authentication |
| Logout POST thiếu CSRF | Bị 403 |
| Logout POST đúng CSRF | Redirect logout và session invalidated |

Các test có `.with(user(USER))` **cố ý chỉ giả lập authenticated principal** để cô lập CSRF behavior của endpoint, không chứng minh password provider đã chạy. Hai test direct login và saved request mới thật sự gửi POST /login với credentials qua Spring Security filter.

### 8.2. Chạy và kết quả kỳ vọng

Trong thư mục Maven project:

~~~bash
mvn test
~~~

Với Java 17+ và dependencies tải thành công, bộ suite có **14 test**. Tóm tắt đầu ra mong đợi (Maven sẽ in thêm thông tin khác):

~~~text
Tests run: 14, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kết quả dự kiến** từ cấu hình ví dụ, không phải log chạy đã được thu thập. Khi ứng dụng thực có custom login URL, custom handlers hoặc multi-chain, cần điều chỉnh assertions cho policy thật, không tắt CSRF chỉ để test pass.

### 8.3. Các helper Spring Security Test

Trong MockMvc:

~~~java
// CSRF parameter:
mvc.perform(post("/profile").with(csrf()));

// CSRF header:
mvc.perform(post("/profile").with(csrf().asHeader()));

// CSRF sai:
mvc.perform(post("/profile").with(csrf().useInvalidToken()));
~~~

Spring Security Test còn có `formLogin()` để tạo một POST login kèm **CSRF hợp lệ**:

~~~java
// Fragment test, cần import formLogin từ SecurityMockMvcRequestBuilders:
mvc.perform(formLogin().user("learner").password("lab-password"));
~~~

**Không dùng `formLogin()` để test thiếu CSRF**, vì helper tự thêm token. Khi cần missing-CSRF, dùng `post("/login")` với username/password mà **không** dùng `.with(csrf())`.

## 9. Kiểm JSESSIONID và Set-Cookie với HTTP thật

Để test cookie đúng mức HTTP, khởi động ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Mở DevTools → Network trong browser và chọn **Preserve log**. Tiếp đó:

1. GET `http://localhost:8080/dashboard` khi anonymous: kiểm 302 `Location: /login`.
2. Browser tự GET `/login`: kiểm 200 và trường `_csrf`.
3. Quan sát cookie session trước login, nếu có. Có thể được tạo do saved request hoặc token cần lưu; **có cookie không nghĩa đã authenticated**.
4. Submit username `learner`, password `lab-password`: request POST cần cookie và CSRF token hợp lệ.
5. Quan sát 302 thành công; nếu có saved request /dashboard, `Location` quay về /dashboard, không nhất thiết /home.
6. Kiểm session ID thay sau login và browser gửi ID mới ở request tiếp theo.
7. GET /dashboard phải 200. Sau logout đúng CSRF, cookie/session cũ không được truy cập được endpoint bảo vệ.

### 9.1. Curl giữ cookie và xem redirect trung gian

Ví dụ chạy **trong môi trường lab**, không dùng credentials thật:

~~~bash
curl -i -c jar.txt http://localhost:8080/dashboard
curl -i -b jar.txt -c jar.txt http://localhost:8080/login
~~~

Đọc giá trị `_csrf` **thực** trong HTML của GET /login (không dùng chuỗi hard-code), sau đó POST với cùng cookie jar:

~~~bash
curl -i -b jar.txt -c jar.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=lab-password" \
  --data-urlencode "_csrf=TOKEN_LAY_TU_FORM" \
  http://localhost:8080/login
~~~

`TOKEN_LAY_TU_FORM` là chú thích thay bằng token thật lấy từ response, không phải token hợp lệ. Cuối cùng:

~~~bash
curl -i -b jar.txt http://localhost:8080/dashboard
~~~

Nếu login/CSRF/session đúng, response thường 200 với body:

~~~text
dashboard:learner
~~~

Lệnh `-c` lưu cookie và `-b` gửi lại cookie. **Không dùng `-L` trong test quan sát Location** vì nó follow redirect và có thể khiến chỉ thấy status cuối. Trên Windows PowerShell có thể dùng `curl.exe`. File `jar.txt` chứa credential phiên: không đưa vào Git, không chia sẻ và xóa an toàn sau bài lab.

### 9.2. Kiểm cookie flags ở public HTTPS ingress

Header HTTP minh họa:

~~~http
HTTP/1.1 302 Found
Location: /home
Set-Cookie: JSESSIONID=REDACTED; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Không khẳng định** demo HTTP localhost tự phát đủ Secure/SameSite ở mọi môi trường. Trong production kiểm qua public HTTPS URL và reverse proxy:

- `HttpOnly` và `Secure` cho session cookie.
- `SameSite` theo nhu cầu đăng nhập/SSO; `SameSite=None` phải kết hợp `Secure`.
- `Path` và `Domain` chỉ bao phủ phạm vi cần thiết.
- Không tồn tại nhiều session cookies cùng tên nhưng khác Path/Domain ngoài dự kiến.
- Redirect `Location` không rò internal scheme/hostname của server.
- Trusted proxy chain xử lý `Forwarded`/`X-Forwarded-*`, không tin header do client Internet tùy ý gửi.

## 10. Kiểm thử SavedRequest, Location và HTTP codes

### 10.1. Direct login khác saved-request login

~~~text
A. Direct login
GET /login   -> 200 + CSRF
POST /login  -> 302 /home

B. Truy cập protected trước
GET /dashboard -> 302 /login; saved /dashboard
POST /login    -> 302 /dashboard
~~~

Mỗi nhánh cần test riêng. `SavedRequestAwareAuthenticationSuccessHandler` có thể trả absolute URL, query marker hoặc relative URL tùy cấu hình; assertion nên kiểm destination có ý nghĩa, không tùy tiện pin cứng toàn bộ chuỗi khi policy không đòi.

### 10.2. Redirect 302 khi sai password không có nghĩa success

~~~text
POST login, CSRF đúng, password sai  -> 302 /login?error
POST login, CSRF đúng, password đúng -> 302 /home
GET dashboard, no authentication     -> 302 /login
~~~

Nếu chỉ `andExpect(status().is3xxRedirection())` cả ba trường hợp đều pass. Cần kiểm `redirectedUrl(...)` và **follow-up session access**.

### 10.3. Session timeout và stale CSRF

Khi session hết hạn, expected CSRF token trong session không còn. Browser đang mở form cũ có thể gửi token cũ và nhận 403. UX có thể cung cấp trang thông báo hết hạn và cách làm mới session/CSRF. Không xử lý bằng cách vô hiệu CSRF.

### 10.4. Open redirect và external host

Nếu ứng dụng tự lấy query `returnUrl` rồi redirect không kiểm soát, attacker có thể lợi dụng redirect sau login để đưa người dùng ra domain độc hại. Dùng `RequestCache` có kiểm soát hoặc allowlist relative paths/trusted origins. Test các giá trị bên ngoài, protocol-relative URL và encoding lạ, không cho redirect tùy ý.

### 10.5. Reverse proxy và nhiều filter chains

Khi backend HTTP nội bộ nằm sau TLS ingress, URL Location phải hướng tới **public HTTPS host**; trusted forwarded header policy không được nhận dữ liệu giả từ Internet.

Nếu web form login và REST API Bearer JWT cùng app, matcher cho mỗi `SecurityFilterChain` phải chuẩn: web anonymous thường 302 /login, API auth failure thường 401 JSON/Bearer challenge. Kiểm riêng path; đừng ép API về 302 hay cho web bypass CSRF bằng matcher quá rộng.

## 11. Các trường hợp thất bại cần test

| Test | Kỳ vọng | Ghi chú |
| --- | --- | --- |
| GET /dashboard anonymous | 302 /login | Entry point |
| GET /login | 200, form có CSRF | Không cố định token |
| POST /login thiếu CSRF | 403 | Kể cả password đúng |
| POST /login CSRF sai | 403 | Không authenticated |
| POST /login đúng CSRF/password sai | 302 /login?error | FailureHandler |
| POST /login đúng cả hai | 302 success target | Kiểm Location |
| Login sau GET protected | 302 saved URL | RequestCache |
| Request sau login cùng session | 200 | Context persisted |
| Session ID trước/sau login | Thay đổi | Session fixation |
| POST profile authenticated, thiếu CSRF | 403 | CsrfFilter |
| POST profile có CSRF nhưng anonymous | 302 /login | CSRF không phải auth |
| POST profile valid CSRF + authenticated | 200 | Authorization và CSRF |
| POST logout thiếu CSRF | 403 | Logout CSRF protection |
| POST logout hợp lệ | Redirect, invalid session | Kiểm request kế tiếp |
| Cookie ở public HTTPS | Secure/HttpOnly/SameSite đúng | Test container/gateway |
| Cookie sau logout | Không còn cấp quyền | E2E cookie jar |
| CSRF token từ session khác | Từ chối | Không chấp nhận cross-session |
| SPA dùng stale token sau login | Từ chối, lấy token mới | Rotation/deferred tokens |
| Redirect tới external domain | Từ chối | Chống open redirect |
| Reverse proxy | Location đúng public host | Không lộ internal host |

## 12. Lỗi triển khai phổ biến

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| POST login bị 403 dù password đúng | CSRF thiếu/sai | Include token, giữ đúng session |
| Dùng `formLogin()` để test thiếu token | Helper tự thêm CSRF | POST thô |
| Dùng `@WithMockUser` để kiểm login | Mock principal bỏ qua credentials | Gửi POST login thật |
| GET protected nhận 302 thay vì 401 | Form login entry point | Kiểm Location /login |
| Bad password nhận 302 thay vì 401 | FailureHandler redirect | Kiểm /login?error |
| MockMvc không có Set-Cookie | Mock container không tạo HTTP cookie thực | Test HTTP/embedded Tomcat |
| Session không giữ qua test requests | Quên truyền MockHttpSession | Dùng `.session(session)` |
| Login đúng nhưng không quay URL muốn tới | Saved request/default target khác | Test hai nhánh riêng |
| Token trong SPA cũ sau login bị 403 | CSRF rotation/XOR/deferred | Cập nhật token và handler |
| POST logout 403 | Thiếu CSRF | Gửi valid token |
| JS đọc được JSESSIONID | HttpOnly tắt | Bật HttpOnly cho session cookie |
| Cookie không Secure trên HTTPS | Proxy/config sai | Kiểm header public ingress |
| Cookie SameSite bất hợp lý | Không tương thích login/cross-site | Đặt policy theo threat model |
| Đúng cookie nhưng redirect login liên tục | Session store không nhất quán, cookie path sai | Kiểm persistence/HA |
| Redirect sang internal hostname | Forwarded headers chưa đúng | Trusted proxy headers |
| Tests xanh khi CSRF bị disable | Assertions không có negative test | Missing/invalid tests |

### 12.1. Hai anti-pattern cần tránh

~~~java
// PHẢN VÍ DỤ: đừng tắt CSRF chỉ để POST /login hết 403.
http.csrf(csrf -> csrf.disable());

// PHẢN VÍ DỤ: đừng tắt session fixation protection
// chỉ để session ID "ổn định" trong một test.
http.sessionManagement(session ->
    session.sessionFixation(fixation -> fixation.none()));
~~~

Đây là hai fragment sai chủ đích, **không phải cấu hình đề xuất**. Với API thật sự stateless có thể có mô hình CSRF riêng tùy credential/cookie mechanism; không kết luận đơn giản “REST không cần CSRF”.

## 13. Checklist trước bàn giao

**CSRF**

- [ ] GET login form render token đúng, không lộ token qua log/URL.
- [ ] POST login thiếu/sai token bị 403; đúng token vẫn kiểm password.
- [ ] POST logout và thay đổi dữ liệu được CSRF bảo vệ.
- [ ] Deferred/XOR/BREACH handled đúng trong Spring Security 6.
- [ ] SPA/cookie token được refresh sau login/logout khi cần.

**Session**

- [ ] Login thành công tạo authenticated session và request tiếp theo truy cập được tài nguyên.
- [ ] Session fixation protection đổi ID; login sai không cấp context.
- [ ] Logout vô hiệu phiên; cookie cũ không cấp quyền.
- [ ] Session timeout, multi-instance store, cookie flags/paths được test.
- [ ] Cookie HttpOnly/Secure/SameSite đúng trên public HTTPS.

**Redirect**

- [ ] GET protected anonymous đi /login theo policy.
- [ ] Wrong password đi /login?error, không nhầm success.
- [ ] Direct success đi default target.
- [ ] Saved request success quay lại URL ban đầu.
- [ ] Không open redirect sang origin lạ.
- [ ] Public reverse-proxy redirect không lộ internal host.

**Chất lượng test**

- [ ] Unit/MockMvc và HTTP/browser tests được phân biệt.
- [ ] Test credentials thật đi qua filter, không chỉ @WithMockUser.
- [ ] Không đưa session cookie/password/token thật vào test reports.
- [ ] Có negative tests để chứng minh bảo mật, không chỉ happy path.

## 14. Câu hỏi tự kiểm tra

1. Vì sao POST /login cũng cần CSRF trong session-based form login?
2. JSESSIONID, XSRF-TOKEN và _csrf khác nhau như thế nào?
3. Vì sao login đúng password vẫn có thể nhận 403?
4. Vì sao password sai lại thường 302 /login?error thay vì 401?
5. MockMvc test phải truyền gì để dùng lại session?
6. Tại sao MockMvc không đủ để chứng minh Set-Cookie Secure/HttpOnly?
7. Session fixation protection làm gì với session ID?
8. SavedRequestAwareAuthenticationSuccessHandler chọn URL nào khi có saved request?
9. Dùng formLogin() helper có kiểm được thiếu CSRF không?
10. @WithMockUser có thực sự chạy DaoAuthenticationProvider không?
11. Vì sao chỉ assert HTTP 302 có thể bỏ sót lỗi login?
12. CSRF token có thể thay đổi sau login/logout vì sao?
13. SPA dùng CookieCsrfTokenRepository trong Security 6 cần lưu ý gì?
14. Vì sao HTTP GET thay đổi dữ liệu là lỗi thiết kế?
15. SameSite có thay thế mọi CSRF protection không?
16. Nếu sau logout cookie cũ vẫn xem được dashboard, test nào đã thiếu?
17. Nếu redirect sang internal-http hostname sau proxy, nên kiểm gì?
18. API Bearer và web form login nên có kỳ vọng 401/302 giống nhau không?

**Kết luận:** một bộ test đăng nhập đạt yêu cầu không dừng ở “POST login có 302”, mà phải chứng minh **token CSRF đúng**, **session được duy trì và chống fixation**, **redirect tới đúng đích theo saved request/success/failure policy**, rồi dùng **cookie/session ở request tiếp theo** để xác nhận authentication. MockMvc kiểm filter logic; HTTP/browser E2E kiểm Set-Cookie, cookie flags, redirect qua public ingress và hành vi thực tế của browser.

## 15. Tài liệu chính thức

- [Spring Security 6.5 — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security 6.5 — Testing Form-Based Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
