# formLogin, httpBasic và logout trong kiểm thử luồng xác thực — Spring Security Servlet

> **Phạm vi:** Kiểm thử HTTP trên **Spring Security 6.x / Servlet / Spring MVC**, dùng Spring Boot 3.x, Java 17+, JUnit 5 và `spring-security-test` với `MockMvc`. Bài tập trung vào **đăng nhập thật bằng form, xác thực HTTP Basic, duy trì phiên giữa các HTTP request và logout**, khác với chỉ giả lập người dùng qua `@WithMockUser` hoặc `user()`. Cấu hình minh họa dùng một security chain có cả form login lẫn HTTP Basic để so sánh dễ dàng; ứng dụng sản xuất cần lựa chọn/sắp xếp authentication mechanisms phù hợp threat model.

## 1. Mục tiêu: phải kiểm tra luồng xác thực, không chỉ “endpoint trả 200”

Ba tình huống phổ biến:

1. Người dùng gửi **POST /login** với `username` và `password`. Spring Security phải kiểm tra credential, tạo `Authentication`, lưu security context vào phiên theo cấu hình, rồi chuyển hướng đúng.
2. Client gửi `Authorization: Basic …` trên HTTP request. Spring Security phải giải mã Basic credential, kiểm tra username/password rồi thực thi authorization; request sai credential phải bị từ chối.
3. Người đã đăng nhập gửi **POST /logout** đúng cách (kể cả CSRF khi bật). Spring Security phải hủy trạng thái xác thực phía server và áp dụng logout success behavior.

Các test yếu thường chỉ viết:

~~~java
mvc.perform(get("/web/me").with(user("alice")))
   .andExpect(status().isOk());
~~~

Đây là **fragment** dùng Spring Security test post-processor `user()`. Nó có giá trị khi kiểm tra **authorization** với một người dùng giả định đã xác thực, nhưng **không chứng minh** password được kiểm tra, HTTP Basic header được xử lý, login session được tạo, hoặc logout đã invalidate phiên.

Để kiểm tra **authentication flow**, ta cần gọi **đúng endpoint/đúng mechanism** thông qua test filter chain, rồi kiểm tra kết quả và trạng thái sau hành động.

### Tiêu chí đạt bài

- Biết `formLogin()` test helper gửi yêu cầu gì tới `UsernamePasswordAuthenticationFilter`.
- Biết `httpBasic()` test post-processor thực sự tạo Basic header; phân biệt nó với `user()`.
- Kiểm chứng login thành công/thất bại, request không có credential, credential sai, trạng thái phiên và authorization.
- Hiểu sự khác nhau giữa **logout thực tế** với chỉ “xóa SecurityContextHolder trong test”.
- Kiểm tra **CSRF** cho login, logout và POST nghiệp vụ có session.
- Không viết test phụ thuộc cứng vào redirect URL, session hoặc status của một cấu hình khác cấu hình đang chạy.

## 2. Ba cơ chế trong Servlet filter chain

~~~text
HTTP request
    |
    v
Servlet FilterChainProxy / SecurityFilterChain
    |
    +-- UsernamePasswordAuthenticationFilter
    |       POST /login
    |       username + password (+ CSRF nếu được yêu cầu)
    |       -> AuthenticationManager
    |       -> AuthenticationProvider / UserDetailsService
    |       -> thành công: SecurityContext + session/redirect
    |       -> thất bại: redirect hoặc failure handler
    |
    +-- BasicAuthenticationFilter
    |       Authorization: Basic base64(username:password)
    |       -> AuthenticationManager
    |       -> đúng: Authentication cho request
    |       -> sai: thường 401 + WWW-Authenticate
    |
    +-- LogoutFilter
    |       mặc định POST /logout khi CSRF bật
    |       -> LogoutHandler(s), ví dụ invalidation/session/context
    |       -> LogoutSuccessHandler / redirect
    |
    +-- AuthorizationFilter
            -> có quyền: Controller
            -> thiếu Authentication: entry point / 401 hoặc redirect
            -> thiếu quyền: AccessDeniedHandler / thường 403
~~~

Đây là sơ đồ khái niệm, **không phải thứ tự đầy đủ của mọi filter**. Trong thực tế, `CsrfFilter`, `SecurityContextHolderFilter`/repository, `ExceptionTranslationFilter`, `RequestCacheAwareFilter` và nhiều filter khác cũng tham gia.

**Điểm quan trọng:** `formLogin` và `httpBasic` là **hai cách xác thực** khác nhau; `logout` tác động chủ yếu tới **state/session/cookie** và các logout handlers, chứ không thể vô hiệu hóa vô điều kiện một Basic credential đúng mà client lại gửi ở request kế tiếp.

### So sánh nhanh

| Tiêu chí | Form login | HTTP Basic | Logout |
| --- | --- | --- | --- |
| Thông tin client gửi | Username/password ở form POST. | Header `Authorization: Basic …` trên từng request. | Request tới logout endpoint, thường POST và CSRF token. |
| Spring Security component | `UsernamePasswordAuthenticationFilter`. | `BasicAuthenticationFilter`. | `LogoutFilter`. |
| Kết quả chính | SecurityContext, thường phiên đăng nhập và redirect. | Authentication cho request. | Xóa authentication/session và redirect/response. |
| Mô hình client | Browser/web application. | API client/tool, đôi khi browser. | Browser/session-based logout. |
| Test helper | `formLogin()`. | `httpBasic("u","p")`. | `logout()` hoặc POST với `csrf()`. |
| Kỹ thuật kiểm chứng | `authenticated()`, redirect, session, request sau login. | HTTP 200/401, principal, `WWW-Authenticate`. | Phiên cũ invalid, logout success, request sau logout. |

HTTP Basic chỉ **Base64 encode**, không mã hóa bảo mật mật khẩu; dùng HTTPS cho credential thật. Browser có thể cache/đính kèm Basic credentials ở request sau, vì vậy không được kết luận “đã logout là Basic sẽ không bao giờ xác thực lại”.

## 3. spring-security-test cung cấp những gì?

Dependency `spring-security-test` đưa vào MockMvc các công cụ:

| API | Loại | Dùng để |
| --- | --- | --- |
| `formLogin()` | `RequestBuilder` | Giả lập POST tới form login processing URL với username/password và CSRF phù hợp. |
| `httpBasic("user","pass")` | `RequestPostProcessor` | Tạo header Basic phù hợp cho một request. |
| `logout()` | `RequestBuilder` | Tạo yêu cầu logout theo quy ước và CSRF mặc định của helper. |
| `csrf()` | `RequestPostProcessor` | Gắn CSRF token hợp lệ khi test endpoint cần CSRF. |
| `csrf().useInvalidToken()` | `RequestPostProcessor` | Test token không hợp lệ. |
| `authenticated()` | `ResultMatcher` | Kiểm tra trạng thái authentication trong kết quả MockMvc. |
| `authenticated().withUsername("alice")` | `ResultMatcher` | Kiểm chứng user đã authenticated với tên mong đợi. |
| `unauthenticated()` | `ResultMatcher` | Kiểm tra không có authentication của người dùng đã xác thực. |
| `user("alice")` | `RequestPostProcessor` | Chèn test principal, **không test credential validation**. |
| `@WithMockUser` | Test annotation | Đặt mock Authentication vào test context, thích hợp kiểm authorization. |

Các import static thường gặp:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
~~~

**Lưu ý:** `formLogin()` và `logout()` trả về **request builder**, trong khi `httpBasic()` và `csrf()` là **post-processors** dùng với `.with(…)` trên `MockHttpServletRequestBuilder`:

~~~java
mvc.perform(formLogin().user("alice").password("demo-pass"));
mvc.perform(get("/api/me").with(httpBasic("alice", "demo-pass")));
mvc.perform(post("/web/action").with(csrf()));
mvc.perform(logout());
~~~

Đây là các fragment trong lớp test đã khởi tạo `mvc`. Không dùng cú pháp `.with(httpBasic(...))` trên kết quả `formLogin()` nếu API builder đó không hỗ trợ `with`.

### Cần có Spring Security filters trong MockMvc

Trong Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {
    @Autowired MockMvc mvc;
}
~~~

Thiết lập này nạp Spring context và tích hợp security filters thông thường. Với MockMvc tự dựng bằng `MockMvcBuilders.webAppContextSetup(context)`, cần `.apply(springSecurity())` hoặc tích hợp FilterChainProxy đúng cách.

**Không dùng `@AutoConfigureMockMvc(addFilters = false)`** rồi kiểm chứng login/CSRF/logout: khi tắt filters, bạn có thể đang kiểm một controller hoàn toàn khác luồng bảo mật sản xuất. Tương tự, standalone MockMvc thiếu filter chain có thể khiến một số test “pass” mà không thực sự chạy Spring Security.

## 4. Một project Java 17+ đầy đủ để chạy test

Chúng ta xây một ứng dụng Spring Boot MVC tối giản:

- `GET /public`: không cần đăng nhập.
- `GET /api/me`: hiển thị người gọi, dùng để test Basic.
- `GET /web/me`: hiển thị người gọi qua session sau form login.
- `POST /web/action`: một endpoint thay đổi trạng thái **giả lập**, dùng để chứng minh CSRF. Không ghi dữ liệu, không chuyển tiền thật.
- `POST /login`: Spring Security filter xử lý, không viết Controller handler riêng.
- `POST /logout`: Spring Security filter xử lý, không viết Controller handler riêng.

### Cấu trúc thư mục

~~~text
security-http-tests/
  pom.xml
  src/
    main/
      java/com/example/securityhttptests/
        SecurityHttpTestsApplication.java
        SecurityConfig.java
        DemoController.java
    test/
      java/com/example/securityhttptests/
        AuthenticationFlowTest.java
~~~

Bài dùng **Spring Boot 3.3.5** làm phiên bản tham chiếu cùng Java 17; đây là một phiên bản cụ thể để ví dụ có thể tái lập, **không phải khẳng định là bản mới nhất**.

### 4.1. Maven pom.xml

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>security-http-tests</artifactId>
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

Maven parent quản lý phiên bản thư viện tương thích. Test framework dùng JUnit Jupiter và Spring Test. Không cần thư viện OAuth2/JWT trong bài này; `formLogin` và Basic dùng `UserDetailsService`/`PasswordEncoder`.

### 4.2. Main application

**`src/main/java/com/example/securityhttptests/SecurityHttpTestsApplication.java`:**

~~~java
package com.example.securityhttptests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityHttpTestsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityHttpTestsApplication.class, args);
    }
}
~~~

### 4.3. Cấu hình xác thực và bảo vệ endpoint

**`src/main/java/com/example/securityhttptests/SecurityConfig.java`:**

~~~java
package com.example.securityhttptests;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            // Không disable CSRF: bảo vệ POST /login, /logout
            // và POST /web/action theo cấu hình mặc định.
            .build();
    }
}
~~~

**Giải thích:**

1. `formLogin(Customizer.withDefaults())` bật default login page và default processing URL `POST /login`. Form fields mặc định là `username` và `password`. Login thành công thường **302 redirect** tới saved request hoặc default target; thất bại thường redirect `/login?error`.
2. `httpBasic(Customizer.withDefaults())` cho phép HTTP Basic credential trên request; nếu sai, thông thường trả 401 và challenge Basic. Nếu không gửi credential, entry point có thể là Basic challenge hoặc form login redirect **tùy request matcher/content negotiation**.
3. `logout(Customizer.withDefaults())` bật logout endpoint và mặc định invalidation session, clear security context; khi CSRF đang bật, logout action mặc định cần `POST /logout`. Response thành công thường redirect `/login?logout`.
4. `requestMatchers("/public").permitAll()` là policy URL, không phải bypass mọi filter. `anyRequest().authenticated()` yêu cầu authentication cho những endpoint còn lại.
5. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo password hash tương thích với password authentication. Mật khẩu `demo-pass` hardcoded **chỉ dùng trong bài học**; trong production không dùng tài khoản mặc định có mật khẩu trong source.
6. Chúng ta **không** dùng `SessionCreationPolicy.STATELESS` ở đây: mục tiêu test là quan sát phiên form login. Nếu đặt stateless, bài test session có thể không còn đúng. HTTP Basic và form login được đặt chung **chỉ vì demo**; production API và UI thường nên có chains/policies khác nhau.
7. Không đặt `.csrf(csrf -> csrf.disable())` chỉ để làm test POST pass. Khi có browser và session cookie, CSRF là một phần của threat model cần được kiểm chứng.

**Cần phân biệt thành phần:** `UserDetailsService` tìm account, `PasswordEncoder` giúp kiểm tra password qua provider; controller không tự giải mật khẩu. Test helper `formLogin()` gửi đúng request cho security filter, không gọi thẳng `SecurityContextHolder.setAuthentication(...)`.

### 4.4. Controller

**`src/main/java/com/example/securityhttptests/DemoController.java`:**

~~~java
package com.example.securityhttptests;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> basicIdentity(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @GetMapping("/web/me")
    public Map<String, String> sessionIdentity(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @PostMapping("/web/action")
    public Map<String, String> fakeAction(Authentication auth) {
        // Endpoint thay đổi trạng thái giả lập để kiểm CSRF.
        // Không có side effect nghiệp vụ thực tế.
        return Map.of(
            "result", "accepted",
            "user", auth.getName()
        );
    }
}
~~~

Dù hai endpoint `/api/me` và `/web/me` trả cùng một trường `user`, **phương thức xác thực** khác nhau: test đầu gửi Basic header trên request, test sau tái sử dụng session sau khi đăng nhập form.

Không tự tạo `@PostMapping("/login")` hoặc `@PostMapping("/logout")` trong Controller: theo cấu hình này, hai URL được Spring Security filters bắt và xử lý trước MVC. Việc viết handler có cùng path không thay thế authentication/logout chain.

## 5. Bộ kiểm thử MockMvc hoàn chỉnh

**`src/test/java/com/example/securityhttptests/AuthenticationFlowTest.java`:**

~~~java
package com.example.securityhttptests;

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
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicPageWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void correctBasicCredentialsAuthenticateUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("alice"))
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void incorrectBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void formLoginSucceedsAndSessionAuthenticatesNextRequest()
            throws Exception {

        MockHttpSession session = loggedInSession();

        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void incorrectFormLoginRedirectsToError() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void rawLoginPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void sessionPostNeedsCsrfToken() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/web/action").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(post("/web/action")
                .session(session)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("accepted"))
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void logoutWithoutCsrfDoesNotInvalidateSession()
            throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void postLogoutWithCsrfInvalidatesFormSession()
            throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());
    }

    private MockHttpSession loggedInSession() throws Exception {
        MvcResult result = mvc.perform(formLogin()
                .user("alice")
                .password("demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }
}
~~~

**Tại sao ví dụ kiểm đúng luồng?**

- `httpBasic("alice", "demo-pass")` tạo header Basic, để `BasicAuthenticationFilter` kiểm tra credential thật qua configured provider.
- `formLogin().user(...).password(...)` gửi request đăng nhập và **bao gồm CSRF hợp lệ theo helper test**. Vì vậy nó kiểm thử phần **username/password authentication**, không chỉ chèn user giả.
- `loggedInSession()` lấy session của chính request form login thành công, dùng `.session(session)` trong request tiếp theo. Đó là kiểm thử **security context được duy trì giữa các request**, không chỉ trạng thái “authenticated” ngay trong request POST.
- `post("/login").param(...)` **không** có CSRF token nên bị 403 bởi `CsrfFilter`, cho thấy raw POST khác `formLogin()` helper.
- `post("/web/action").session(session)` phải bị từ chối dù người dùng đã đăng nhập, vì không có CSRF. Thêm `.with(csrf())` giúp POST đi tiếp đến controller.
- `post("/logout").session(session).with(csrf())` thực sự dùng **session đang authenticated** và xác nhận nó bị invalidate. Kết quả redirect `/login?logout` dựa vào cấu hình logout mặc định của project demo.

`MockHttpSession.isInvalid()` dùng được với `org.springframework.mock.web.MockHttpSession` trong các Spring Test versions tương ứng. Không dùng lại **session đã invalid** cho request tiếp theo: servlet session không còn hợp lệ và MockHttpSession có thể ném lỗi khi truy cập sau invalidation. Nếu muốn kiểm hậu logout bằng HTTP request mới, tạo session/client state mới không có authentication và kiểm endpoint được bảo vệ vẫn chặn.

### Chạy bộ test

Tại thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

Kỳ vọng là các test xác thực, Basic, CSRF và logout đều pass khi chạy đúng với Spring Boot 3.x/Spring Security 6.x mà project chọn. **Không có stdout Maven cố định** vì log, cache dependency, Java version và test reporter có thể khác giữa máy. Nếu test fail, đọc **assertion cụ thể** và security filter configuration, không sửa policy thành `permitAll`/`csrf.disable()` để “cho xanh”.

Để chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

HTTP Basic trong môi trường local:

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/me
~~~

Body JSON kỳ vọng:

~~~json
{"user":"alice"}
~~~

Sử dụng HTTPS khi test credential thật; URL HTTP localhost chỉ dành cho demo. Không dùng password production trong shell history, mã nguồn hoặc tài liệu test công khai.

## 6. Đi sâu vào formLogin(): nó kiểm tra điều gì?

### 6.1. Luồng request và trạng thái

~~~text
MockMvc
  |
  | formLogin().user("alice").password("demo-pass")
  | POST /login, username, password, CSRF
  v
CsrfFilter (valid)
  |
  v
UsernamePasswordAuthenticationFilter
  |
  v
AuthenticationManager
  |
  v
Provider kiểm PasswordEncoder và UserDetailsService
  |
  +-- Đúng -> Authentication thành công
  |          -> SecurityContext được lưu theo session/repository
  |          -> success handler, thường 302 redirect
  |
  +-- Sai -> authentication failure
             -> failure handler, thường 302 /login?error
~~~

Test `authenticated().withUsername("alice")` đặt sau request login nói rằng **kết quả request đã authenticated theo test matcher**. Nó không tự kiểm tra trạng thái phiên của request kế tiếp, vì thế ta lấy `MockHttpSession` rồi thực hiện `GET /web/me` trong một lượt riêng.

### 6.2. Login success không có nghĩa luôn redirect cùng URL

Khi user truy cập một URL được bảo vệ trước khi login, Spring Security có thể lưu `SavedRequest` qua `RequestCache`. Đăng nhập thành công có thể redirect về URL ban đầu. Nếu user đăng nhập trực tiếp, có thể redirect về default target (thường `/`).

Vì vậy trong test **login success tổng quát**, nên assert `status().is3xxRedirection()` và `authenticated()` trước; chỉ assert exact redirect khi bạn đã **cố ý cấu hình success URL/handler** hoặc test cụ thể saved request.

**Ví dụ không nên copy cứng cho mọi app:** `redirectedUrl("/")`. Nếu dự án có `defaultSuccessUrl("/dashboard", true)`, URL mong đợi là `/dashboard`; nếu dùng saved request thì URL có thể là trang từng yêu cầu.

### 6.3. Test sai mật khẩu phải qua provider thật

~~~java
mvc.perform(formLogin()
        .user("alice")
        .password("wrong-password"))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/login?error"))
    .andExpect(unauthenticated());
~~~

Trong demo, Spring Security dùng `UserDetailsService` và `PasswordEncoder`, nên test này phát hiện lỗi credential. Nếu chỉ dùng `@WithMockUser("alice")`, test **không chứng minh** mật khẩu “wrong-password” bị từ chối.

Login failure handler có thể được dự án tùy biến trả JSON 401 thay vì redirect. Khi đó test cần kỳ vọng theo **contract thật** thay vì mặc định của form login.

### 6.4. Custom login URL và parameter names

Nếu production cấu hình:

~~~java
.formLogin(form -> form
    .loginPage("/signin")
    .loginProcessingUrl("/auth/signin")
    .usernameParameter("email")
    .passwordParameter("secret")
    .permitAll())
~~~

thì POST login phải gửi tới `/auth/signin` với fields `email` và `secret`. Có thể test bằng raw POST:

~~~java
mvc.perform(post("/auth/signin")
        .param("email", "alice@example.test")
        .param("secret", "example-password")
        .with(csrf()));
~~~

Đây là fragment minh họa; nó **không tương thích trực tiếp** với account `alice`/`demo-pass` của project demo nếu không thay UserDetailsService và login config. Mục tiêu là nắm **processing URL và parameter contract**, không lặp lại test đăng nhập mặc định cho URL khác.

**Phân biệt:**
- `loginPage("/signin")`: URL GET hiển thị form login (cần controller/view nếu custom).
- `loginProcessingUrl("/auth/signin")`: URL POST filter chặn để xác thực.
- `usernameParameter` và `passwordParameter`: tên field mà filter đọc.
- `defaultSuccessUrl` và `failureUrl`: quyết định response/redirect sau authentication.

Nếu custom login URL mà quên `permitAll`/authorization rule thích hợp, người chưa đăng nhập có thể bị chặn ngay tại đường login hoặc rơi vào vòng redirect.

## 7. HTTP Basic: điều gì cần assert?

### 7.1. Header Basic được tạo thế nào?

HTTP Basic chuẩn gửi:

~~~http
Authorization: Basic <base64(username:password)>
~~~

`httpBasic("alice", "demo-pass")` tạo header cho request test:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("alice", "demo-pass")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.user").value("alice"));
~~~

Framework kiểm thông tin đăng nhập qua `BasicAuthenticationFilter`/provider được cấu hình. Không tự ghép `"Basic alice:demo-pass"` vì đó **không phải Base64 hợp lệ**. Cũng không coi Basic encoding là cơ chế bảo mật trên mạng; phải dùng HTTPS.

### 7.2. Lỗi credential thường là 401

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("alice", "wrong-password")))
    .andExpect(status().isUnauthorized());
~~~

Trong cơ chế Basic mặc định, response khi yêu cầu xác thực thất bại thường kèm `WWW-Authenticate: Basic realm="Realm"` hoặc realm do ứng dụng cấu hình, nhưng **đừng assert cứng chuỗi realm** nếu không có contract cụ thể.

Nếu không có Authorization header, một ứng dụng bật **cả form login và Basic** có thể lựa chọn **302 redirect** hoặc **401 Basic challenge** dựa trên content negotiation/request matcher. Do đó test “GET /api/me không header luôn 401” có thể không chính xác với mọi chain. Trong ví dụ, kiểm **sai Basic credential** sẽ ổn định hơn để khẳng định lỗi cơ chế Basic, còn việc chọn entry point cho request thiếu credential cần test theo Accept header và security config thực.

### 7.3. Authenticated Basic không tự đồng nghĩa stateless

Vì demo sử dụng một security chain có cả form login và Basic, session/repository vẫn có thể tham gia request. HTTP Basic tự nó không đòi hỏi lưu session, nhưng **cấu hình SecurityFilterChain** quyết định liệu security context có được lưu, session có được tạo, request cache có hoạt động hay không.

Trong production, API muốn stateless thường dùng một chain riêng `/api/**` với `SessionCreationPolicy.STATELESS`, policy CSRF/threat model riêng, và entry point trả 401 JSON/Basic challenge; browser UI dùng chain riêng với session/form login. Không đặt `STATELESS` cho toàn app nếu bạn muốn test login session.

### 7.4. Bảo vệ brute force và credential leakage

Bài test đúng password/sai password là tối thiểu. Production còn cần rate limiting, account lockout/chính sách chống credential stuffing, audit login failure, HTTPS, không log header Authorization, không lưu password vào test fixture chia sẻ công khai.

Một request Basic mới với credential đúng vẫn có thể tạo authentication dù một **session form login khác** đã logout. Vì Basic là credential được client gửi lại, **logout không thể xóa password mà client/browser đang nắm**.

## 8. logout(): kiểm điều gì ngoài redirect?

### 8.1. Logout flow mặc định khi CSRF bật

~~~text
Session đã authenticated
        |
        | POST /logout + valid CSRF token
        v
LogoutFilter
        |
        +-- LogoutHandler(s):
        |    clear SecurityContext
        |    invalidate HttpSession (theo cấu hình)
        |    xóa/điều chỉnh trạng thái có liên quan
        |
        v
LogoutSuccessHandler
        |
        v
302 /login?logout (default demo)
~~~

`logout()` từ `SecurityMockMvcRequestBuilders` là helper để tạo request logout, tương tự form login helper. Tuy nhiên khi muốn chứng minh **phiên cụ thể** đã bị xóa, dùng request POST tường minh có `session(session)` và `csrf()` như test mục 5; helper đơn giản nếu test default logout endpoint/status:

~~~java
mvc.perform(logout())
    .andExpect(unauthenticated());
~~~

Đây là fragment cần static imports phù hợp. Test này **không đủ để chứng minh** session mà một login thực tạo ra đã bị invalidate. Kết hợp session-driven test là cần thiết.

### 8.2. Vì sao POST /logout thiếu CSRF phải bị chặn?

CSRF bảo vệ một browser/session cookie khỏi việc website độc hại gây logout hoặc hành động không mong muốn bằng request phát sinh ngoài ý định. Trong cấu hình **CSRF enabled** của demo:

~~~java
mvc.perform(post("/logout").session(session))
    .andExpect(status().isForbidden());
~~~

`session` ở đây là biến của một test đã login, không phải đoạn độc lập. Sau request bị từ chối, phiên vẫn phải còn hợp lệ:

~~~java
assertFalse(session.isInvalid());
~~~

Khi thêm CSRF token hợp lệ:

~~~java
mvc.perform(post("/logout")
        .session(session)
        .with(csrf()))
    .andExpect(status().is3xxRedirection());
~~~

session phải bị invalidate theo cấu hình demo:

~~~java
assertTrue(session.isInvalid());
~~~

Nếu ứng dụng tùy biến logout success trả 204 thay vì 302, assert status tương ứng với contract. Nếu ứng dụng disable `invalidateHttpSession` hoặc có logout handler khác, không được sao chép máy móc assert `isInvalid`; hãy kiểm điều kiện mà security policy thực sự yêu cầu.

### 8.3. GET /logout có “đăng xuất” không?

Trong Spring Security Servlet với CSRF enabled, **GET /logout** thường hiển thị trang xác nhận logout do framework tạo, còn logout action yêu cầu POST có CSRF token. Vì vậy test:

~~~java
mvc.perform(get("/logout"));
~~~

không chứng minh user đã logout. Nếu hệ thống tùy biến để GET /logout trực tiếp sign out, cần đánh giá rủi ro CSRF/side effects vì GET không nên được dùng cho hành động thay đổi trạng thái. Đừng thay POST thành GET chỉ để tiện browser tự mở.

### 8.4. Session invalidation khác xóa mọi token

Logout mặc định của một Servlet app thường invalidates session và clear security context; nó **không mặc nhiên**:
- revoke access token JWT của OAuth2 Resource Server;
- revoke token đang lưu trên thiết bị khác;
- xóa mọi cookie tùy chỉnh ở domain khác;
- chặn client tiếp tục gửi Basic credentials;
- xóa distributed cache/remember-me tokens nếu chưa cấu hình handler phù hợp.

Nếu app có remember-me, OIDC logout, SSO, session registry hoặc custom cookies, phải test đúng các logout handlers và client-state/remote-state tương ứng. Logout thành công ở app A không tự đồng nghĩa IdP session của toàn SSO đã bị đóng.

## 9. CSRF: lớp bảo vệ không thể bỏ qua khi test login/logout

Trong demo, CSRF **mặc định bật**. Các request GET an toàn thường không cần CSRF token; các request POST/PUT/PATCH/DELETE thường phải có token hợp lệ khi thuộc phạm vi CSRF protection.

| HTTP request | Có authentication? | Có CSRF token? | Kỳ vọng với demo |
| --- | --- | --- | --- |
| GET /public | Không | Không | 200 |
| POST /login đúng credential | Chưa | Không | 403 |
| POST /login đúng credential qua `formLogin()` | Chưa | Helper thêm token | 302 login success |
| GET /web/me với session login | Có | Không | 200 |
| POST /web/action với session | Có | Không | 403 |
| POST /web/action với session | Có | Có, hợp lệ | 200 |
| POST /logout với session | Có | Không | 403, session còn |
| POST /logout với session | Có | Có, hợp lệ | 302, session invalid |
| GET /api/me với Basic đúng | Qua Basic | Không | 200 |
| GET /api/me với Basic sai | Thất bại | Không | 401 |

Đừng suy từ “API dùng Basic” rằng mọi POST được miễn CSRF. Browser có thể tự gửi Basic credentials/cookie tùy bối cảnh; cần phân tích credential có được **tự động đính kèm** trong cross-origin request hay không. Khi xây chain API chỉ nhận Bearer token được client chủ động đặt vào Authorization header, threat model CSRF có thể khác. Việc disable CSRF là **quyết định chính sách**, không phải mẹo để test pass.

### Test CSRF token sai

Một negative test bổ sung:

~~~java
mvc.perform(post("/web/action")
        .session(session)
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
~~~

Đây là fragment nằm trong test có `session` đã đăng nhập. Nó giúp phân biệt “có token field/header” với “token khớp repository/handler”. Khi dùng custom `CsrfTokenRepository` hoặc XOR token request handler, test cần tích hợp đúng vào security filter chain để không bỏ qua kiểm tra thực tế.

## 10. Test matcher: authenticated(), unauthenticated() và status khác nhau

`authenticated()` không giống `status().isOk()`:
- Authentication có thể thành công nhưng response lại là 302 redirect sau login.
- Một endpoint có thể trả 200 vì `permitAll`, dù người gọi chưa đăng nhập.
- Basic credential đúng nhưng user thiếu role có thể trả 403 dù đã authenticated.
- Một request có session và valid CSRF có thể vẫn 403 nếu thiếu authority hoặc business policy.

Bởi vậy mỗi test nên kiểm **hai chiều**:
1. **Authentication state**: có đúng user/authority đang được xác thực không?
2. **HTTP behavior**: status, redirect, headers, JSON, session, CSRF và quyền.

Ví dụ:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("alice", "demo-pass")))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("alice"))
    .andExpect(jsonPath("$.user").value("alice"));
~~~

Khi test request login success, response 302 không phải dấu hiệu “login thất bại”. Ngược lại, response 200 trên public endpoint **không chứng minh** credential từng được kiểm tra.

### Không đọc security context sai thời điểm

Trong Servlet, security context có thể được cleanup ở cuối request để tránh rò ThreadLocal sang request khác. Nếu test ngoài request gọi:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

và nhận null, không nhất thiết login trong request đã thất bại. Hãy kiểm bằng `authenticated()` matcher ở kết quả request, lấy session của login hoặc thực hiện request tiếp theo có cùng session. Không dùng một static `SecurityContext` làm “login state” cho nhiều test methods.

## 11. Session, Cookie và kiểm trạng thái qua nhiều HTTP request

MockMvc không phải trình duyệt thật có cookie jar tự động cho mọi call. Nếu cần mô phỏng người dùng tiếp tục request sau login, một cách rõ ràng là:

~~~java
MvcResult login = mvc.perform(formLogin()
        .user("alice")
        .password("demo-pass"))
    .andExpect(authenticated())
    .andReturn();

MockHttpSession session =
    (MockHttpSession) login.getRequest().getSession(false);

assertNotNull(session);

mvc.perform(get("/web/me").session(session))
    .andExpect(status().isOk());
~~~

Đây là fragment trong test đã có `mvc` và imports. Việc truyền **chính session** có ý nghĩa quan trọng: test chứng minh security context được Spring Security repository lưu/khôi phục giữa các request.

### Session fixation và session ID

Framework có thể đổi session ID sau login để giảm rủi ro session fixation. Đừng lấy ID từ session trước login rồi assert nó luôn bằng ID sau login. Nếu chính sách yêu cầu session fixation protection, nên test riêng qua cơ chế MockMvc/session semantics phù hợp, không suy từ “formLogin status 302”.

### Phân biệt authentication và session

Một request Basic đúng có thể authenticated **chỉ trong request đó**; không nhất thiết tạo/duy trì session. Một request form login thường tạo một phiên để browser dùng session cookie. Trong single-chain demo, cả hai chia một security config; không kết luận tất cả Basic requests đều stateless hoặc tất cả form login luôn dùng session trong mọi cấu hình.

### Logout và stale browser cookies

Khi server invalidates session, browser có thể vẫn gửi một cookie session ID cũ. Cookie cũ **không tự làm session đã invalidate sống lại**. Nhưng nếu client đồng thời gửi Basic header đúng hoặc OIDC login cookie với IdP còn phiên, hệ thống có thể xác thực lại theo mechanism khác. Vì vậy test logout nên nêu rõ: **logout cơ chế nào, xóa state nào, và credential nào còn tồn tại**.

## 12. Nhiều SecurityFilterChain: tránh test nhầm chain

Production thường tách UI và API:

~~~text
GET/POST /web/**  -> UI security chain:
   form login, session, CSRF, logout, redirects

/api/**           -> API security chain:
   HTTP Basic hoặc Bearer, policy status/CSRF/session riêng

other paths       -> fallback chain:
   deny/allow theo chính sách rõ ràng
~~~

Nếu khai báo nhiều `SecurityFilterChain` bằng `@Order` và `securityMatcher`, cần bảo đảm:

- Request `POST /login` thực sự match chain chứa `formLogin`.
- Request `POST /logout` match chain chứa `logout`.
- API challenge/entry point không bị UI form login redirect thay thế.
- Không có path nhạy cảm nằm ngoài mọi chain hoặc bị matcher quá rộng chọn nhầm.
- Session fixation, CSRF và request cache đúng theo từng chain.
- Test vừa gọi URL login/logout thực, vừa thực hiện request sau xác thực ở **chain mà nó bảo vệ**.

**Một lỗi điển hình:** chain UI chỉ `securityMatcher("/web/**")` nhưng login processing URL lại là `/login` nằm **ngoài** matcher, khiến request login được một chain khác xử lý hoặc không được form filter chặn. Có thể đặt `loginProcessingUrl("/web/login")` và logout URL trong chain UI hoặc mở rộng matcher đúng cách, rồi cập nhật test.

Không copy một fragment `formLogin()` test mặc định vào cấu hình có `loginProcessingUrl("/web/login")` mà không đổi URL. Test phải chứng minh **contract đang chạy**, không phải tên helper.

## 13. Một ma trận kiểm thử xác thực thực tế

Tổ chức kiểm thử thành nhiều nhóm thay vì chỉ một happy path.

| Nhóm | Kịch bản chính | Quan sát tối thiểu |
| --- | --- | --- |
| Public | GET /public không login | 200, đúng content |
| Form login success | Đúng username/password, valid CSRF | Authentication đúng, redirect, session được lưu |
| Form login failure | Sai password, unknown user | Không authenticated, failure handler phù hợp |
| Form login CSRF | POST /login thiếu/sai CSRF | Bị từ chối, không tạo session đăng nhập thành công |
| Basic success | Authorization Basic đúng | Authenticated đúng user, controller nhận đúng principal |
| Basic failure | Authorization Basic sai | 401/challenge phù hợp |
| Missing credentials | GET protected không credentials | Redirect login hoặc 401 theo chain/Accept |
| Session persistence | Login xong GET protected với cùng session | Thành công, đúng user |
| Authorization | Authenticated nhưng thiếu role | 403, không lộ data |
| Business CSRF | POST với session nhưng thiếu CSRF | 403; valid CSRF đến được controller |
| Logout protection | POST /logout thiếu CSRF | Bị từ chối, session chưa invalidate |
| Logout success | POST /logout valid CSRF | Handler chạy; session invalid, redirect/response đúng |
| Multi-chain | UI vs API vs fallback | Đúng security chain, status/redirect/CSRF theo policy |
| SSO/remember-me | Logout app và refresh/browser state | Session và token được xóa/giữ theo chính sách thực tế |

Các ca “missing credentials” cần tránh assert cứng một status nếu app bật đồng thời Basic/form và dựa trên content negotiation. Hãy **cấu hình entry point tường minh** nếu public API contract đòi hỏi status nhất định, rồi test nó.

### Bổ sung test quyền sau authentication

`formLogin`/`httpBasic` chỉ xác minh **ai** đăng nhập, không phải người đó được mọi quyền. Nếu route yêu cầu `hasRole("ADMIN")` mà `alice` chỉ có `ROLE_USER`, request phải bị 403. Viết test “correct credential but insufficient authority” giúp tránh lỗi vô tình gộp authentication với authorization.

## 14. Debug đúng tầng khi test thất bại

### Trường hợp A: formLogin trả 403

Kiểm tra `CsrfFilter`, URL login có match security chain không, helper `formLogin()` có đúng processing URL/parameters không và custom CSRF repository có chấp nhận token từ helper không. Khi dùng raw POST, phải thêm `.with(csrf())` nếu CSRF enabled.

**Đừng sửa bằng `csrf.disable()` nếu ứng dụng có browser session.**

### Trường hợp B: formLogin trả 302 nhưng GET /web/me vẫn redirect login

Thường do test không mang **session** sau login, session không được lưu/khôi phục theo repository, cấu hình `STATELESS`, hoặc request sau login đi qua chain khác. Kiểm `getSession(false)`, `MockHttpSession`, `.session(session)` và `SecurityContextRepository`.

### Trường hợp C: Basic đúng nhưng redirect login thay vì trả JSON

Kiểm BasicAuthenticationFilter có trong chain tương ứng không, path có match chain không, credential có đúng không và endpoint có bị policy khác chặn không. Nếu request **không có** Basic header thì entry point có thể redirect theo form login; nếu Basic header sai, thường nhận 401.

### Trường hợp D: Test logout pass nhưng user vẫn “đăng nhập”

Kiểm test có dùng **session trước login thật** hay chỉ mock authentication; logout URL, method, CSRF, handlers và state server-side nào bị xóa. Nếu client/browser vẫn gửi Basic credentials hoặc có remember-me/SSO session, request sau logout có thể được authenticated lại. **Logout session không xóa password ở client.**

### Trường hợp E: @WithMockUser pass, formLogin thất bại

Đây không mâu thuẫn. `@WithMockUser` đặt user giả vào security context; nó có thể bypass username/password provider. Form login kiểm tra **UserDetailsService, PasswordEncoder và login filter**. Hãy kiểm account tồn tại, hash format đúng và authentication manager được nối.

### Trường hợp F: Logout qua GET không làm gì

Nếu CSRF bật, mặc định GET /logout thường là trang xác nhận và POST mới thực thi. Dùng `post("/logout").with(csrf())` và session đã authenticated khi muốn test logout action. Đừng thay sang GET action tùy tiện.

### Trường hợp G: Test “không login” nhận status 302, mong 401

App bật form login, có thể chọn redirect đến login page khi `Accept: text/html`. API client thường mong 401. Nếu cần JSON API nhất quán, thiết kế một chain/entry point cho API và test tương ứng. Không coi mọi response 302 là bug.

### Trường hợp H: Test POST /web/action trả 403 dù login thành công

Đầu tiên phân biệt CSRF 403 và authorization 403. Trong demo, `CsrfFilter` chặn POST thiếu CSRF token **trước khi** controller chạy. Thêm `.with(csrf())` để kiểm flow sau CSRF, sau đó mới đánh giá authority/business rule.

## 15. Những hiểu nhầm cần tránh

**“formLogin() giống @WithMockUser.”** Sai. `formLogin()` gửi form credential qua Spring Security authentication flow; `@WithMockUser` chèn một Authentication giả cho test policy/controller.

**“httpBasic() chỉ gắn một username trong security context.”** Sai. `httpBasic()` tạo HTTP Basic header; provider vẫn kiểm username/password. `user()` mới là helper cài đặt principal giả vào request.

**“Đăng nhập thành công phải có status 200.”** Sai. Form login mặc định thường redirect 302; test cần kiểm authenticated, redirect và trạng thái phiên.

**“Một test login status 302 là đủ chứng minh session.”** Sai. Cần request sau với cùng MockHttpSession để chứng minh security context persisted.

**“Logout xóa cả mọi Basic/OAuth2 credential.”** Sai. Nó xóa state theo logout handlers; credential được client gửi lại hoặc remote IdP token còn hiệu lực cần policy riêng.

**“Logout mặc định qua GET.”** Không đúng khi CSRF enabled; GET /logout thường chỉ là confirmation page, POST mới trigger logout.

**“Tắt CSRF là cách sửa tốt khi test login/logout 403.”** Sai với app dùng browser/session. Test phải gửi token hợp lệ hoặc kiến trúc phải có lý do rõ để bỏ CSRF.

**“HTTP Basic an toàn vì có Base64.”** Sai. Base64 không phải encryption; dùng TLS/HTTPS và không log credentials.

**“Authenticated đồng nghĩa authorized.”** Sai. User đã đăng nhập vẫn có thể bị 403 bởi role, permission, CSRF hoặc policy nghiệp vụ.

**“Form login và HTTP Basic luôn trả cùng kiểu lỗi.”** Sai. Default form login hay redirect; Basic thường 401/challenge, tùy entry point và request.

**“Test dùng @AutoConfigureMockMvc(addFilters=false) vẫn xác thực thật.”** Sai. Khi security filters bị bỏ qua, test không đi qua login/basic/logout/CSRF chain như production.

## 16. Bài tập thực hành

### Bài 1 — Login thành công rồi truy cập

Tạo test `formLogin().user("alice").password("demo-pass")`, assert authenticated. Lấy `MockHttpSession` và thực hiện `GET /web/me` kèm session. **Kết quả mong đợi:** response 200 chứa `"user":"alice"`.

### Bài 2 — Sai password qua hai cơ chế

Thử `formLogin()` với password sai và `GET /api/me` với `httpBasic("alice","wrong-password")`. **Kết quả mong đợi:** form failure thường redirect `/login?error`; Basic failure thường 401; cả hai không được truy cập endpoint protected như alice.

### Bài 3 — So sánh POST raw và helper

Gửi raw `POST /login` đúng form fields nhưng không có CSRF. Sau đó dùng `formLogin()`. **Kết quả mong đợi:** request raw bị 403; helper thành công theo cấu hình demo. Giải thích sự khác nhau ở CSRF token.

### Bài 4 — Logout thật với session

Đăng nhập, lấy session; POST /logout thiếu CSRF, xác nhận chưa invalid; tiếp tục POST với CSRF, xác nhận `session.isInvalid()`. **Kết quả mong đợi:** request thứ nhất 403, thứ hai redirect logout success và invalidates session.

### Bài 5 — Thêm phân quyền ADMIN

Thêm `/admin` chỉ cho `hasRole("ADMIN")`, rồi test Basic với alice có ROLE_USER. **Kết quả mong đợi:** authenticated đúng user nhưng HTTP 403. Phân biệt bằng lời authentication với authorization.

### Bài 6 — API riêng và UI riêng

Tạo chain `/api/**` với Basic và chain `/web/**` với form login, xác định login/logout URLs thuộc UI chain. Viết test Basic wrong password nhận 401 và unauthenticated browser GET UI redirect tới login page. **Kết quả mong đợi:** không có endpoint/login handler nằm ngoài mọi chain; CSRF/session policies rõ ràng.

### Bài 7 — Form login custom parameters

Chuyển processing URL thành `/auth/signin` và field username thành `email`. Viết test raw POST đúng URL và `.with(csrf())`, cùng negative test POST nhầm `/login`. **Kết quả mong đợi:** chỉ URL và fields được cấu hình mới kích hoạt login thành công.

### Bài 8 — Sau logout không được tái dùng session

Đăng nhập, logout và xác minh session invalid. Thử truy cập protected endpoint bằng **request mới không có credentials/session hợp lệ**. **Kết quả mong đợi:** request không vào controller, nhận redirect/401 theo entry point. Không cố tái dùng `MockHttpSession` đã invalid vì nó có thể ném exception và không phản ánh HTTP client thực.

## 17. Checklist trước khi chấp nhận một bộ test authentication flow

- [ ] Test có bật Spring Security filter chain thật trong MockMvc.
- [ ] Có test form login **đúng và sai password** qua processing URL thực.
- [ ] Có test Basic **đúng và sai credential** qua Authorization header.
- [ ] Có test unauthenticated protected request theo đúng entry point contract.
- [ ] Có test **session persistence** sau form login bằng request kế tiếp.
- [ ] Có test CSRF cho raw login POST, endpoint state-changing và logout.
- [ ] Có test logout dùng **chính session được tạo sau login** và xác nhận invalidation.
- [ ] Có test authorization khi user đã authenticated nhưng thiếu quyền.
- [ ] Với custom login/logout path, mọi test được cập nhật theo URL/parameter thật.
- [ ] Với nhiều security chains, test xác nhận request chọn đúng chain.
- [ ] Không dùng `@WithMockUser`/`user()` làm bằng chứng kiểm tra password.
- [ ] Không disable filters/CSRF chỉ để “làm test xanh”.
- [ ] Không đưa password/token thật vào test fixtures hoặc logs.
- [ ] Không diễn giải HTTP Basic logout như khả năng revoke password phía client.
- [ ] Mọi kỳ vọng 200/302/401/403 dựa trên cấu hình đang chạy, không sao chép máy móc.

**Kết luận:** Trong Spring Security Servlet, `formLogin()` kiểm thử **authentication qua form POST**, `httpBasic()` kiểm thử **Basic header credential**, còn `logout()`/`POST /logout` kiểm thử **hủy trạng thái đăng nhập**. Một bộ test chất lượng phải chứng minh **credential được xác thực đúng, session được mang sang request kế tiếp, CSRF được thực thi và logout làm mất session theo policy**, rồi kiểm authorization tách biệt. Test matcher `authenticated()` rất hữu ích nhưng không thay thế kiểm tra HTTP status, redirect, session và endpoint được bảo vệ.