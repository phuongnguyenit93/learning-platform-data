# Tách nhiều cơ chế đăng nhập theo SecurityFilterChain trong Spring Security

## 1. Bài toán thực hành tổng hợp

Một ứng dụng Spring Boot có thể phục vụ nhiều nhóm client với những quy trình xác thực khác nhau: người dùng trình duyệt đăng nhập bằng biểu mẫu và giữ session; CLI/service gọi API qua HTTP Basic hoặc Bearer; nhân viên nội bộ dùng SSO/OIDC; quản trị viên yêu cầu mức xác thực cao. Nếu để mọi cơ chế trên cùng một cấu hình mà không có ranh giới rõ, API dễ bị redirect sang trang HTML login, browser session có thể đi nhầm vào API, hoặc một endpoint không thuộc bất kỳ filter chain nào bị bỏ bảo vệ.

Mục tiêu là triển khai **nhiều `SecurityFilterChain` trong cùng ứng dụng**, tách biệt về URL, authentication entry point, session và CSRF policy. Bài thực hành chính gồm:

1. Vùng **`/api/**`**: HTTP Basic, **stateless**, chỉ cung cấp GET, trả **401** khi chưa có credentials.
2. Vùng **`/web/**`**: form login, **HttpSession**, CSRF, trả **302** tới trang đăng nhập khi chưa authenticated.
3. **Fallback chain** không có `securityMatcher`: từ chối mọi path còn lại bằng `denyAll()`.

Hai vùng dùng cùng `UserDetailsService` mẫu cho dễ quan sát; chúng ta sẽ chứng minh **form session không thay HTTP Basic**, và **HTTP Basic không tạo web login session**. Phần sau mở rộng kiến trúc sang OAuth2 Resource Server JWT, OIDC/SSO và tách identity stores.

### Kết quả cần đạt

- Giải thích `FilterChainProxy` chọn **SecurityFilterChain khớp đầu tiên**, không trộn các chain.
- Phân biệt `securityMatcher` (chọn toàn bộ chain) với `requestMatchers` trong `authorizeHttpRequests` (chọn rule bên trong chain).
- Dùng `@Order` với matcher hẹp trước, fallback cuối.
- Đặt `loginPage`, `loginProcessingUrl`, logout và OAuth2 callback trong matcher thích hợp.
- Phân biệt HTTP **401 Basic challenge**, HTTP **302 form redirect**, HTTP **403 authorization/CSRF**.
- Giữ CSRF trên browser và không tắt CSRF toàn cục chỉ vì ứng dụng có API.
- Viết Java 17 / Spring Security 6.x / JUnit 5 / MockMvc integration tests cho các đường đi, ranh giới session và negative cases.

**Giới hạn quan trọng:** HTTP Basic là lựa chọn **minh họa** cho API GET trong localhost, không phải đề xuất mặc định cho mobile hoặc public API production. Basic gửi password trong header chỉ được mã hóa Base64, vì vậy **HTTPS là bắt buộc** ngoài localhost. Browser có thể tự gửi lại Basic credentials trong một số ngữ cảnh; nếu API Basic có mutation thì cần đánh giá CSRF, không tự mặc định an toàn chỉ vì `STATELESS`.

## 2. FilterChainProxy chọn chain như thế nào?

~~~text
HTTP request
   |
   v
DelegatingFilterProxy
   |
   v
FilterChainProxy
   |
   +-- thử chain @Order(1), matcher=/api/**
   |        khớp → dùng filter list API và DỪNG chọn
   |
   +-- thử chain @Order(2), matcher=/web/**
   |        khớp → dùng filter list WEB và DỪNG chọn
   |
   +-- chain @Order(3), không giới hạn matcher
            luôn khớp → denyAll()
~~~

**Chỉ chain đầu tiên khớp được áp dụng cho một request.** Spring Security không thực thi lần lượt API chain rồi WEB chain để cộng dồn các filters.

| Khái niệm | Vai trò | Hệ quả |
|---|---|---|
| `http.securityMatcher("/api/**")` | Quyết định chain nào nhận request | Phạm vi filter chain |
| `http.authorizeHttpRequests(...)` | Cấu hình quyền cho request đã vào chain | Không mở rộng matcher |
| `requestMatchers("/api/admin")` | Áp dụng rule của endpoint nằm trong chain | Không bảo vệ URL bên ngoài chain |
| `anyRequest()` | Phần còn lại *trong chain* | Không thay thế catch-all chain |
| `@Order(1)` | Ưu tiên cao | Có thể che chain sau nếu matcher quá rộng |
| Fallback không gọi `securityMatcher` | Match mọi path còn lại | Chống URL bị bỏ lọt |

Ví dụ một lỗi phổ biến:

~~~java
// Sai: /web/login không nằm trong phạm vi /api/**.
// requestMatchers().permitAll() ở đây không bao giờ áp dụng cho /web/login.
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/web/login").permitAll()
        .anyRequest().authenticated());
~~~

**Nếu không chain nào khớp**, request có thể đi tiếp tới Servlet/MVC mà **không được Spring Security bảo vệ**. Đó là lý do ví dụ chủ động thêm fallback.

## 3. Route matrix và hành vi kỳ vọng

| Method + URL | Chain | Xác thực | Kết quả chủ đích |
|---|---|---|---|
| GET /api/whoami | API | Basic | 200 khi đúng, 401 khi thiếu/sai |
| GET /api/admin | API | Basic + ROLE_ADMIN | 200 với admin, 403 với USER |
| POST /api/whoami | API | Không được cấp phép | Bị chặn |
| GET /web/login | WEB | Anonymous | 200, HTML form có CSRF |
| POST /web/login | WEB | Username/password + CSRF | Login success hoặc failure |
| GET /web/home | WEB | Session | 200 khi đã login, 302 nếu anonymous |
| GET /web/admin | WEB | Session + ROLE_ADMIN | 200 admin, 403 USER |
| POST /web/logout | WEB | Session + CSRF | Logout và redirect |
| GET /unmapped | Fallback | Không có login | 403 trong cấu hình demo |

Chúng ta chủ ý **không công bố POST/PUT/PATCH/DELETE trên API Basic**. Khi triển khai API thay đổi trạng thái, cần quyết định credential và CSRF policy phù hợp với browser, proxy và client thực tế.

### Ranh giới giữa API và WEB

~~~text
CLI/API client                              Browser
    |                                         |
    | Authorization: Basic ...                | cookie JSESSIONID
    v                                         v
/api/**                                    /web/**
    |                                         |
API chain                                 WEB chain
    |                                         |
httpBasic                                  formLogin
STATELESS                                  HttpSession
401 challenge                              302 /web/login
    |                                         |
    +----------------+------------------------+
                     |
            UserDetailsService
            PasswordEncoder
            Authorization rules
~~~

Việc chia chain **không tự chia danh tính**: nếu hai cơ chế dùng cùng user store, cùng tài khoản vẫn có thể dùng password ở cả hai, nhưng cách tạo và giữ `Authentication` khác nhau. Nếu policy đòi service-account identity không thể đăng nhập WEB, cần tách provider/manager/store.

## 4. Tạo project Java 17 và Spring Boot 3.5.7

Cấu trúc dự án:

~~~text
multiple-login-chains/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/multichain/
    │   │   ├── MultiChainApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── LoginPageController.java
    │   │   └── DemoController.java
    │   └── resources/
    │       ├── application.yml
    │       └── templates/login.html
    └── test/
        └── java/com/example/multichain/
            └── MultipleSecurityChainsTest.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>multiple-login-chains</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

Spring Boot BOM quản lý các dependency Spring Security tương thích. `spring-security-test` là test scope; không sử dụng test identity helpers trong production.

### 4.2. application.yml

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  password: ${DEMO_PASSWORD}
~~~

Đặt `DEMO_PASSWORD` qua environment ở local. JUnit sẽ override `demo.password` bằng một giá trị riêng trong `@SpringBootTest(properties=...)`.

### 4.3. MultiChainApplication.java

~~~java
package com.example.multichain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }
}
~~~

## 5. Cấu hình SecurityFilterChain theo đúng phạm vi

File `src/main/java/com/example/multichain/SecurityConfiguration.java`:

~~~java
package com.example.multichain;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.password}") String password) {

        var alice = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();

        var admin = User.withUsername("admin")
                .password(encoder.encode(password))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/api/whoami")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .requestCache(cache -> cache.disable())
                // CSRF mặc định vẫn bật; demo API chỉ có GET.
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/web/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/web/login")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/web/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/web/home")
                            .authenticated()
                        .anyRequest().denyAll())
                .formLogin(form -> form
                        .loginPage("/web/login")
                        .loginProcessingUrl("/web/login")
                        .defaultSuccessUrl("/web/home", true)
                        .failureUrl("/web/login?error")
                        .permitAll())
                .logout(logout -> logout
                        .logoutUrl("/web/logout")
                        .logoutSuccessUrl("/web/login?logout"))
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackSecurity(HttpSecurity http)
            throws Exception {

        // Không đặt securityMatcher: chain cuối match mọi URL.
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .build();
    }
}
~~~

### 5.1. Tại sao cấu hình này quan trọng?

**API chain:**
- Chỉ path `/api/**`.
- Chỉ hai GET URLs được cho phép có điều kiện; các request khác bị `denyAll`.
- Không `.formLogin()`; `httpBasic()` cung cấp Basic authentication challenge.
- `STATELESS` khiến Spring Security không dùng HttpSession để lấy SecurityContext.
- `requestCache.disable()` tránh saved request/redirect theo mô hình browser.
- CSRF không bị tắt toàn cục.

**WEB chain:**
- Chỉ path `/web/**`.
- GET/POST `/web/login` là login route.
- `formLogin` xác thực bằng username/password; trang GET được MVC render.
- `/web/logout` là logout processing URL.
- Dựa trên session và CSRF mặc định.
- Basic không được bật trong WEB chain.

**Fallback chain:**
- Không có `securityMatcher`, vì vậy các URL chưa khớp chain nào cũng bị Spring Security kiểm tra.
- Không có một login method để tự động cấp quyền cho những path không được dự kiến.
- `denyAll()` từ chối, không trông đợi việc controller không tồn tại mới bảo vệ hệ thống.

### 5.2. Vì sao @Order không thể bỏ qua?

Một chain `@Order(1)` với `securityMatcher("/**")` sẽ chiếm mọi URL và khiến các chain sau không được xét. Nếu đặt fallback lên đầu, toàn bộ ứng dụng bị chặn. Nếu bỏ fallback, một controller mới ở `/debug` hoặc `/reports` có thể không được Spring Security bảo vệ.

`@Order` cần được xem như một phần cấu hình bảo mật có regression test, không chỉ là thông tin thẩm mỹ.

## 6. Trang đăng nhập tùy biến và CSRF

Do đã cấu hình `.loginPage("/web/login")`, Spring Security không tự render HTML tùy chỉnh. Ta cần một MVC controller cho **GET** và một template; **POST** được `UsernamePasswordAuthenticationFilter` xử lý.

### 6.1. LoginPageController.java

~~~java
package com.example.multichain;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginPageController {

    @GetMapping("/web/login")
    public String login() {
        return "login";
    }
}
~~~

Không tạo `@PostMapping("/web/login")` tự so sánh password. Làm như vậy dễ bỏ qua `AuthenticationManager`, `PasswordEncoder`, CSRF/session fixation protection và authentication events.

### 6.2. templates/login.html

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="utf-8">
  <title>WEB login</title>
</head>
<body>
  <h1>Đăng nhập WEB</h1>
  <p th:if="${param.error}">
    Thông tin đăng nhập không hợp lệ.
  </p>
  <p th:if="${param.logout}">
    Bạn đã đăng xuất.
  </p>
  <form th:action="@{/web/login}" method="post">
    <label for="username">Tài khoản</label>
    <input id="username" name="username"
           autocomplete="username" required>

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>

    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
~~~

Thymeleaf tích hợp `RequestDataValueProcessor` của Spring MVC nên có thể **tự chèn hidden CSRF token** vào POST form có `th:action`. Kiểm tra HTML đã render ở trình duyệt để xác nhận input `name="_csrf"` thực sự có mặt.

Đừng thêm một hidden CSRF field thứ hai nếu view engine đã tạo field; duplicate parameters có thể gây sai lệch token. Với template engine khác, render CSRF token đúng từ request attribute/server-side repository. Không copy token của người dùng này sang phiên khác.

### 6.3. Vì sao permitAll vẫn yêu cầu CSRF?

`requestMatchers("/web/login").permitAll()` chỉ cho phép anonymous truy cập endpoint theo **authorization**. `CsrfFilter` vẫn kiểm tra POST và có thể trả 403 **trước khi password tới AuthenticationProvider**.

Nếu thấy 403 từ POST login, hãy kiểm tra CSRF parameter/session, không tắt CSRF toàn cục hoặc sửa password encoder trước khi xác định provider đã được gọi.

## 7. API và WEB controllers

File `src/main/java/com/example/multichain/DemoController.java`:

~~~java
package com.example.multichain;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/whoami")
    public Map<String, String> apiWhoami(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "channel", "api-basic");
    }

    @GetMapping("/api/admin")
    public Map<String, String> apiAdmin(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "resource", "api-admin");
    }

    @GetMapping("/web/home")
    public Map<String, String> webHome(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "channel", "web-form");
    }

    @GetMapping("/web/admin")
    public Map<String, String> webAdmin(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "resource", "web-admin");
    }
}
~~~

Dù cả hai loại endpoint trả JSON, chain được chọn vẫn dựa trên **request matcher của HTTP path**, không dựa vào content type trả về.

`ROLE_ADMIN` được kiểm tra bằng `hasRole("ADMIN")` (tương ứng authority `ROLE_ADMIN`). Basic `alice` có `ROLE_USER` nên bị từ chối tại `/api/admin`; WEB session của `alice` cũng bị từ chối ở `/web/admin`.

## 8. Chạy demo với Maven, curl và browser

Trong thư mục dự án, dùng JDK 17+ và Maven.

Linux/macOS:

~~~bash
export DEMO_PASSWORD='local-training-password-only'
mvn spring-boot:run
~~~

PowerShell:

~~~powershell
$env:DEMO_PASSWORD = "local-training-password-only"
mvn spring-boot:run
~~~

Đây là password ví dụ cho **localhost**. Không dùng nó cho tài khoản production hoặc đưa môi trường demo mở ra Internet.

### 8.1. API anonymous

~~~bash
curl -i http://localhost:8080/api/whoami
~~~

Kỳ vọng **401 Unauthorized** với `WWW-Authenticate: Basic ...` (header chi tiết tùy cấu hình). **Không** bị redirect tới `/web/login`.

### 8.2. API Basic đúng

~~~bash
curl -i -u "alice:local-training-password-only"   http://localhost:8080/api/whoami
~~~

Kỳ vọng status 200 và JSON tương đương:

~~~json
{"principal":"alice","channel":"api-basic"}
~~~

Trên PowerShell, dùng executable `curl.exe` nếu alias `curl` khác nhau:

~~~powershell
curl.exe -i -u "alice:local-training-password-only" "http://localhost:8080/api/whoami"
~~~

**Cảnh báo:** `curl -u` trên command line có thể lưu credential vào shell history hoặc hiển thị qua process inspection. Ví dụ chỉ dành cho local; trong môi trường thật dùng secret management và hạn chế ghi credential vào log/history.

### 8.3. API Basic sai

~~~bash
curl -i -u "alice:wrong"   http://localhost:8080/api/whoami
~~~

Kỳ vọng 401, không tạo web session.

### 8.4. WEB anonymous

~~~bash
curl -i http://localhost:8080/web/home
~~~

Kỳ vọng 302 redirect về `/web/login`. Truy cập `http://localhost:8080/web/login` bằng browser, nhập `alice` và password demo; sau thành công, GET `/web/home` trả JSON tương đương:

~~~json
{"principal":"alice","channel":"web-form"}
~~~

Không dùng một request POST form trần không có CSRF token để kết luận password sai. Browser cần gửi form token và cookie thuộc **cùng session**.

### 8.5. Fallback

~~~bash
curl -i http://localhost:8080/unmapped
~~~

Kỳ vọng bị từ chối (thường 403 với handler mặc định demo) thay vì được Spring MVC cho truy cập công khai.

## 9. JUnit 5 + MockMvc: chứng minh hai chain độc lập

Các bài test dưới đây sử dụng **SecurityFilterChain thật trong ApplicationContext** cùng `spring-security-test`. Chúng kiểm tra không chỉ happy path mà cả status, role, CSRF, session isolation và fallback.

File `src/test/java/com/example/multichain/MultipleSecurityChainsTest.java`:

~~~java
package com.example.multichain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.logout;
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
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(properties =
        "demo.password=local-only-test-password")
@AutoConfigureMockMvc
class MultipleSecurityChainsTest {

    @Autowired
    MockMvc mvc;

    private static final String PASSWORD =
            "local-only-test-password";

    private MockHttpSession webLogin(String username)
            throws Exception {
        MvcResult result = mvc.perform(
                formLogin("/web/login")
                    .user(username)
                    .password(PASSWORD))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername(username))
            .andReturn();

        MockHttpSession session =
                (MockHttpSession)
                    result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void apiAnonymousGets401() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiBasicCorrectPasswordGets200() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"))
            .andExpect(jsonPath("$.channel").value("api-basic"));
    }

    @Test
    void apiBasicWrongPasswordGets401() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiRoleUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", PASSWORD)))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiRoleAdminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("api-admin"));
    }

    @Test
    void apiPostIsDeniedEvenWithCredentialsAndCsrf()
            throws Exception {
        mvc.perform(post("/api/whoami")
                .with(httpBasic("alice", PASSWORD))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void webAnonymousRedirectsToFormLogin()
            throws Exception {
        mvc.perform(get("/web/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/login"));
    }

    @Test
    void webLoginPageRendersCsrf() throws Exception {
        mvc.perform(get("/web/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    containsString("name=\"_csrf\"")));
    }

    @Test
    void webSessionAllowsHome() throws Exception {
        MockHttpSession session = webLogin("alice");

        mvc.perform(get("/web/home").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"))
            .andExpect(jsonPath("$.channel").value("web-form"));
    }

    @Test
    void webWrongPasswordRedirectsToError()
            throws Exception {
        mvc.perform(formLogin("/web/login")
                .user("alice")
                .password("wrong"))
            .andExpect(unauthenticated())
            .andExpect(redirectedUrl("/web/login?error"));
    }

    @Test
    void webLoginWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/web/login")
                .param("username", "alice")
                .param("password", PASSWORD))
            .andExpect(status().isForbidden());
    }

    @Test
    void webSessionDoesNotAuthenticateStatelessApi()
            throws Exception {
        MockHttpSession session = webLogin("alice");

        mvc.perform(get("/api/whoami").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiBasicHeaderDoesNotAuthenticateWeb()
            throws Exception {
        mvc.perform(get("/web/home")
                .with(httpBasic("alice", PASSWORD)))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/login"));
    }

    @Test
    void webAdminRequiresAdminRole() throws Exception {
        MockHttpSession alice = webLogin("alice");
        mvc.perform(get("/web/admin").session(alice))
            .andExpect(status().isForbidden());

        MockHttpSession admin = webLogin("admin");
        mvc.perform(get("/web/admin").session(admin))
            .andExpect(status().isOk());
    }

    @Test
    void webLogoutUsesWebChain() throws Exception {
        MockHttpSession session = webLogin("alice");
        mvc.perform(logout("/web/logout").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/login?logout"));
    }

    @Test
    void unmatchedPathIsDeniedByFallback()
            throws Exception {
        mvc.perform(get("/unmapped"))
            .andExpect(status().isForbidden());
    }
}
~~~

### 9.1. Chạy tests

~~~bash
mvn clean test
~~~

**Kỳ vọng:** **16 bài test** pass với Java 17+, Maven và dependencies tương thích; report Maven Surefire nằm dưới `target/surefire-reports/`. Output thời gian/chỉ số Maven thay đổi theo máy, không khẳng định stdout byte-for-byte.

**Ranh giới kết luận:** đây là MockMvc integration tests dùng real security filters và password encoder, nhưng vẫn là in-process ApplicationContext; chưa chứng minh HTTPS termination, Redis session store, IAM/IdP ngoài ứng dụng hay token signature verification.

### 9.2. Hai tests quan trọng nhất

~~~java
// Session từ WEB không đủ để xác thực API Basic stateless.
mvc.perform(get("/api/whoami").session(webSession))
    .andExpect(status().isUnauthorized());

// Header Basic hợp lệ không tự tạo WEB form session.
mvc.perform(get("/web/home")
        .with(httpBasic("alice", PASSWORD)))
    .andExpect(redirectedUrl("/web/login"));
~~~

Đây là bằng chứng request/response cho phân tách cơ chế, không chỉ là việc Java class `SecurityFilterChain` có nhiều @Bean.

### 9.3. Các helper có chủ đích

- `formLogin("/web/login")` gửi POST đúng custom processing URL và tự gắn CSRF token cho test.
- `formLogin()` không tham số mặc định gọi **POST /login**, có thể nằm ngoài WEB matcher.
- `httpBasic("alice", password)` tạo Authorization header phù hợp cho API test, không tạo session form login.
- `logout("/web/logout")` tạo request logout đúng URL và có CSRF token.
- `.with(csrf())` dùng khi POST test cần hợp lệ; muốn test **thiếu** CSRF phải dùng raw POST không gắn helper.
- `@AutoConfigureMockMvc` phải giữ các security filters hoạt động; không dùng `addFilters=false` chỉ để tránh lỗi 401/403.

## 10. Java 17 độc lập: mô phỏng first matching chain

Mẫu chỉ thể hiện **ý tưởng** chọn chain theo đường dẫn, không dùng Spring Security, không thay thế `RequestMatcher` thật. Java file: **FirstMatchDemo.java**.

~~~java
public final class FirstMatchDemo {

    static String choose(String path) {
        if (path.startsWith("/api/")) return "API_BASIC";
        if (path.startsWith("/web/")) return "WEB_FORM";
        return "DENY_FALLBACK";
    }

    static void show(String path) {
        System.out.println(path + " -> " + choose(path));
    }

    public static void main(String[] args) {
        show("/api/whoami");
        show("/web/login");
        show("/web/home");
        show("/oauth2/authorization/demo");
        show("/unmapped");
    }
}
~~~

Lệnh:

~~~bash
javac FirstMatchDemo.java
java FirstMatchDemo
~~~

**Stdout chính xác:**

~~~text
/api/whoami -> API_BASIC
/web/login -> WEB_FORM
/web/home -> WEB_FORM
/oauth2/authorization/demo -> DENY_FALLBACK
/unmapped -> DENY_FALLBACK
~~~

Spring Security thực tế dùng matcher theo request servlet/MVC context; mô phỏng trên không xác định edge cases như encoded path, trailing slash hoặc path rewrite. Trong production, dùng `securityMatcher` và test HTTP thực.

## 11. CSRF, session và logout không được lẫn giữa các chain

### 11.1. WEB form login

~~~text
GET /web/home (anonymous)
   → WEB chain
   → 302 /web/login

GET /web/login
   → MVC render login.html + CSRF input

POST /web/login với CSRF hợp lệ
   → CsrfFilter
   → UsernamePasswordAuthenticationFilter
   → AuthenticationManager / Provider
   → lưu SecurityContext vào HttpSession
   → 302 /web/home

POST /web/logout với CSRF hợp lệ
   → LogoutFilter thuộc WEB chain
   → invalidate session + clear security context
   → redirect /web/login?logout
~~~

Nếu `POST /web/login` thiếu CSRF, `CsrfFilter` có thể trả 403 trước provider. Không nên sửa bằng cách disable CSRF rộng.

### 11.2. API Basic

~~~text
GET /api/whoami
   → API chain
   → BasicAuthenticationFilter
   → Authorization: Basic ... ?
      KHÔNG → 401 challenge
      CÓ   → AuthenticationManager / PasswordEncoder
   → GET endpoint được phép nếu authenticated
~~~

`SessionCreationPolicy.STATELESS` khiến Spring Security **không sử dụng HttpSession làm SecurityContext repository của API chain**. Mỗi Basic request cần gửi credentials riêng; web session cookie không làm request trở thành authenticated.

### 11.3. CSRF trong Basic API có mutation

Không suy diễn “HTTP Basic stateless” thành “browser không thể bị CSRF”. Browser có thể lưu và gửi lại Basic credentials tự động. Vì vậy demo giới hạn GET; nếu thêm POST/PUT/DELETE phải:
- xác định client có phải browser không;
- xác định loại credentials được tự đính kèm;
- giữ CSRF/token control khi phù hợp;
- cân nhắc chuyển sang Bearer-only Resource Server hoặc mTLS;
- test negative cases cho cross-origin/CSRF.

### 11.4. CORS không thay CSRF

CORS trả lời origin nào được đọc một response hoặc gửi một số cross-origin JS requests; CSRF bảo vệ state-changing requests có ambient credentials. API client cần CORS không đồng nghĩa browser session routes được phép tắt CSRF. Cả hai phải được cấu hình theo threat model và ở đúng filter chain.

## 12. Login URL, callback URL và logout URL phải thuộc đúng chain

Đối với form login, chuỗi URL cần được bao phủ:
- GET login page: `/web/login`;
- POST login-processing URL: `/web/login`;
- redirect success: `/web/home`;
- redirect error: `/web/login?error`;
- POST logout: `/web/logout`;
- logout success: `/web/login?logout`.

Nếu viết:

~~~java
http.securityMatcher("/web/**")
    .formLogin(form -> form
        .loginPage("/login")
        .loginProcessingUrl("/login"));
~~~

thì `/login` **nằm ngoài** `/web/**`: trang, processing endpoint có thể bị fallback chiếm hoặc không được filter xử lý. Chọn URL dưới cùng prefix hoặc mở rộng matcher cụ thể.

Tương tự, SSO/OIDC thường dùng:
- `/oauth2/authorization/{registrationId}`;
- `/login/oauth2/code/{registrationId}` cho callback.

Nếu browser chain chỉ match `/web/**`, các endpoint OIDC mặc định nằm ngoài nó. Điều chỉnh matcher hoặc endpoint base URI + cấu hình redirect URI ở IdP, không disable fallback để cho callback “đi qua tự do”.

## 13. Mở rộng API sang Bearer JWT Resource Server

Trong production, HTTP Basic API có thể được thay bằng Bearer access token từ OAuth2 Authorization Server. Việc thay thế cần có **một** API chain được xác định rõ, không thêm nhiều `@Order(1)` với cùng matcher rồi đoán chain nào sẽ thắng.

### 13.1. Dependency mới

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 13.2. Mẫu API JWT chain thay thế

~~~java
@Bean
@Order(1)
SecurityFilterChain jwtApi(HttpSecurity http)
        throws Exception {

    return http
            .securityMatcher("/api/**")
            .sessionManagement(s -> s
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(a -> a
                .requestMatchers(
                    HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_api.admin")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
}
~~~

Đây là **mảnh thay thế minh họa**, chưa runnable độc lập. Cần khai báo `JwtDecoder`, trusted issuer và key source, ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
~~~

Địa chỉ trên **chỉ là ví dụ cấu hình**. Production kiểm tra signature, issuer, token expiry, `nbf`, audience, scopes/roles/tenant mapping và quy trình key rotation/revocation. **Mặc định không đồng nghĩa đã kiểm tra audience riêng của API** nếu chưa bổ sung validator phù hợp.

Việc disable CSRF trong mảnh JWT chỉ có thể cân nhắc khi API thật sự **Bearer-only, không chấp nhận cookie/HTTP Basic hoặc ambient browser credentials**. Không áp dụng mảnh này lên WEB form chain.

### 13.3. JWT test mock không phải signature test

Trong MockMvc, `jwt()` postprocessor có thể tạo authentication giả để kiểm tra rule `SCOPE_api.admin`:

~~~java
mvc.perform(get("/api/admin")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_api.admin"))))
    .andExpect(status().isOk());
~~~

Cần import `jwt`, `SimpleGrantedAuthority` và các MockMvc helpers. Nhưng helper này **không chứng minh JWT signature/issuer/audience thật đã được xác minh**. Để test cryptographic path, phải gửi signed test token qua decoder được cấu hình, dùng JWK/issuer fixture đáng tin.

## 14. Mở rộng browser sang OIDC/SSO

Nếu thay `formLogin` bằng `oauth2Login`, Spring Security có:
- endpoint khởi tạo authorization request;
- redirect đến Identity Provider;
- callback/authorization-code exchange;
- xử lý state/nonce/ID token, UserInfo và principal mapping;
- session browser.

Các URL mặc định `/oauth2/authorization/**` và `/login/oauth2/code/**` có thể **không** nằm trong matcher `/web/**`.

Một ý tưởng mở rộng matcher:

~~~java
http.securityMatcher(
        "/web/**",
        "/oauth2/authorization/**",
        "/login/oauth2/code/**")
    .oauth2Login(Customizer.withDefaults());
~~~

Mảnh trên chưa có `spring-boot-starter-oauth2-client`, `ClientRegistration`, IdP issuer, client credentials và redirect URI. Nó chỉ minh họa **phạm vi matcher**, không phải OIDC application đã chạy hoàn chỉnh.

Test OAuth2 cần phân biệt:
- Mock principal từ `oauth2Login()` / `oidcLogin()`: authorization layer sau authentication.
- Integration flow thật với IdP/test Authorization Server: redirects, state, nonce, token signature, issuer/audience và user mapping.

**Không bỏ fallback denyAll để callback tự do đi qua.** Hãy đặt callback vào đúng chain và tiếp tục bảo vệ nó theo protocol.

## 15. Tách identity stores, provider và AuthenticationManager

Hai chain trong demo dùng cùng `UserDetailsService`. Đây là **mechanism isolation**, không phải **identity isolation**. Nếu yêu cầu nghiệp vụ là:
- web user chỉ được vào browser bằng OIDC/MFA;
- service account chỉ được vào API bằng mTLS hoặc Client Credentials;
- admin chỉ được vào route có step-up;

thì cần AuthenticationManager/AuthenticationProvider và user/token stores riêng theo chain.

Ví dụ khung:

~~~java
// Mảnh minh họa trong cấu hình của service API.
// apiManager phải được tạo từ provider phục vụ service identity.
@Bean
@Order(1)
SecurityFilterChain apiSecurity(
        HttpSecurity http, AuthenticationManager apiManager)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .authenticationManager(apiManager)
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .sessionManagement(s -> s
            .sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
        .build();
}
~~~

**Không phải chương trình runnable độc lập:** cần khai báo `apiManager`, providers và CSRF/method policies phù hợp. `http.authenticationManager(...)` cho phép chỉ định manager theo chain thay vì mặc định dùng global provider.

Phân quyền ở tầng HTTP không thay thế object-level authorization: một `ROLE_ADMIN` được xác thực hợp lệ chưa chắc được sửa tài nguyên của tenant khác. Cần kiểm tra quyền hiện hành tại service/DB, account status và resource ownership.

## 16. Thử nghiệm lỗi matcher và chain ordering

### Case A — API matcher rộng hơn dự định

~~~java
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http.securityMatcher("/**")
        .httpBasic(Customizer.withDefaults())
        .authorizeHttpRequests(a ->
            a.anyRequest().authenticated())
        .build();
}
~~~

Vì chain đầu match mọi URL, WEB chain phía sau không có cơ hội chạy. Anonymous `/web/home` có thể nhận Basic challenge thay vì redirect form login.

### Case B — requestMatchers đặt ngoài securityMatcher

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/web/login").permitAll()
        .anyRequest().authenticated());
~~~

Rule `/web/login` không có tác dụng vì request đó không bao giờ vào API chain.

### Case C — thiếu fallback

~~~text
@Order(1): /api/**
@Order(2): /web/**
(no catch-all chain)
~~~

Một URL mới `/debug`, `/actuator` hoặc `/internal` có thể không match bất kỳ chain nào. Không suy luận “vì anyRequest trong API chain nên mọi URL đều được bảo vệ”. Muốn bảo vệ toàn bộ ứng dụng, thêm fallback không hạn chế matcher.

### Case D — login/callback ngoài chain

Form login `/login` nằm ngoài `/web/**`, hoặc callback `/login/oauth2/code/**` bị fallback deny. Sửa matcher/processing URL, không tự disable security ở callback.

### Case E — đường dẫn biến thể

Path như `/api` (không có slash cuối), trailing slash, encoded characters, context path và proxy rewrite có thể ảnh hưởng matcher. Không tự xây `startsWith` security logic bên ngoài Spring để “fix” path. Kiểm tra với RequestMatcher, HttpFirewall và URL được expose ở ingress.

### Case F — API Basic POST thiếu CSRF

Một POST có thể bị `CsrfFilter` trả 403 **trước** khi authorization rule xử lý. Với POST có valid CSRF, `denyAll()` vẫn từ chối. Đây là hai cơ chế khác nhau, không coi kết quả 403 đủ để nói rule nào chặn.

## 17. Giám sát và kiểm thử hồi quy

Gợi ý kiểm tra ở mỗi deploy:
1. Log startup liệt kê đúng số SecurityFilterChains và filter list.
2. `/api/**` thiếu credentials → 401, không 302.
3. `/web/**` anonymous → 302 tới đúng login page, không 401 Basic.
4. WEB form POST có CSRF hợp lệ đến AuthenticationManager.
5. API Basic không tạo web session.
6. Web session không xác thực API stateless.
7. Role USER bị chặn ở cả hai admin endpoints.
8. Fallback chặn URL không thuộc dự án.
9. Logout URL và session invalidation đúng.
10. OAuth2 callback/refresh/token endpoints không nằm ngoài chain nếu dùng SSO.
11. CSRF/CORS/session cookie hoạt động khi qua reverse proxy và multi-replica.
12. Tests giữ security filters hoạt động: không dùng `@AutoConfigureMockMvc(addFilters=false)`.

Bật log ở mức DEBUG trong môi trường chẩn đoán:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Theo dõi `DefaultSecurityFilterChain` startup log và behavior request. Không log `Authorization`, `Cookie`, password, raw token hoặc session ID; dùng correlation ID, route template, chain type và HTTP status để quan sát.

Có thể kiểm tra filter list qua `FilterChainProxy.getFilters("/api/whoami")` và `getFilters("/web/home")` trong integration test chuyên biệt; nhưng **request→response tests** vẫn cần để chứng minh entry point, provider, session và authorization thực thi đúng.

## 18. Ma trận QA tổng hợp

| Case | Mong đợi |
|---|---|
| GET /api/whoami anonymous | 401 |
| GET /api/whoami Basic đúng | 200 |
| GET /api/whoami Basic sai | 401 |
| GET /api/admin Basic alice USER | 403 |
| GET /api/admin Basic admin | 200 |
| POST /api/whoami Basic + CSRF | 403 do denyAll |
| GET /web/login | 200, có form CSRF |
| GET /web/home anonymous | 302 /web/login |
| POST /web/login đúng + CSRF | Tạo authenticated session |
| POST /web/login sai + CSRF | Redirect /web/login?error |
| POST /web/login thiếu CSRF | 403 |
| GET /web/home với session alice | 200 |
| GET /web/admin với session alice | 403 |
| GET /web/admin với session admin | 200 |
| Web session nhưng không Basic, GET /api/whoami | 401 |
| Basic header nhưng không web session, GET /web/home | 302 |
| POST /web/logout với CSRF | Logout và redirect |
| GET /unmapped | 403 nhờ fallback |
| Path API bị match vào WEB | Regression fail |
| Form endpoint ngoài WEB matcher | Regression fail |
| OAuth2 callback ngoài chain | Bị fallback deny, cần sửa matcher |
| JWT mock principal | Chỉ authorization test |
| JWT thật sai issuer/audience/signature | Token verification phải từ chối |
| Reverse proxy rewrite path | Matcher vẫn đúng public route |
| New controller ngoài prefix | Không thành public endpoint |

Kiểm thử nên bao phủ **các request thật qua Spring Security filters**, không chỉ controller unit tests. Một controller trả 200 trong unit test không chứng minh nó có authentication đúng khi request đi qua ingress.

## 19. Sai lầm cần tránh

1. Chỉ khai báo API + WEB chains, không có fallback.
2. Đặt catch-all chain ở `@Order(1)`.
3. Dùng `securityMatcher("/**")` cho API chain.
4. Nhầm `requestMatchers` với `securityMatcher`.
5. Để `/web/login` hoặc `/web/logout` ngoài WEB matcher.
6. Bật nhiều login mechanisms chung mà không chọn entry point phù hợp.
7. Cho API trả 302 HTML thay 401 status.
8. Tưởng Basic header tạo web session.
9. Tưởng web session làm API stateless authenticated.
10. Disable CSRF toàn ứng dụng vì muốn dùng API.
11. Dùng HTTP Basic cho state-changing browser-accessible API mà không đánh giá CSRF.
12. Dùng Basic qua HTTP công khai không TLS.
13. Tạo custom POST login controller tự so sánh raw password.
14. Chạy `formLogin()` MockMvc mặc định khi actual path là `/web/login`.
15. Không test password sai, quyền sai và fallback.
16. Tắt MockMvc filters để có test 200.
17. Thêm JWT chain trùng `/api/**` mà không xóa Basic chain cũ.
18. Gán `ROLE_ADMIN` từ thông tin client tự gửi.
19. Tin `jwt()` mock test đã chứng minh signature validation.
20. Không kiểm tra SSO callback path và redirect URI.
21. Không phân biệt mechanism isolation với identity segregation.
22. Không bảo vệ actuator, health, metrics và endpoints ngoài prefix.
23. Không kiểm tra object-level/tenant authorization sau authentication.
24. Không có policy session/token revocation và account disable.
25. Không kiểm thử path normalization, trailing slash và reverse proxy.
26. Không ghi nhận chain/status trong monitoring, dẫn tới chẩn đoán 401/302/403 sai tầng.

## 20. Checklist production

- [ ] Toàn bộ URL authentication, authorization, callback, logout, health và admin được inventory.
- [ ] Mỗi SecurityFilterChain có securityMatcher hẹp hoặc fallback rõ ràng.
- [ ] @Order được kiểm thử, không có chain che chain khác ngoài chủ đích.
- [ ] Có fallback không matcher bảo vệ các URL còn lại.
- [ ] API trả đúng 401 challenge hoặc Bearer error semantics, không redirect HTML.
- [ ] WEB form login/session dùng CSRF, session fixation protection và cookie bảo mật.
- [ ] Credentials API không tự trở thành session, session WEB không bypass API.
- [ ] Chỉ dùng Basic với HTTPS và chính sách CSRF/HTTP methods được đánh giá.
- [ ] Production API Bearer kiểm tra JWT signature, issuer, audience, expiry và scope mapping.
- [ ] OIDC authorization/callback endpoints nằm trong chain đúng và state/nonce được xác minh.
- [ ] Identity provider/authentication manager tách nếu policy đòi tách user và service accounts.
- [ ] Request authorization và service/resource-level authorization đều có test.
- [ ] Logout, session expiry, revoke, disable account được test.
- [ ] MockMvc tests cover anonymous, wrong password, wrong role, CSRF, mixed session, fallback.
- [ ] Reverse proxy/trusted forwarded headers/CORS/cookie routing đã được kiểm thử.
- [ ] Logs không chứa raw Basic credentials, session cookies, JWT hoặc password.
- [ ] Có regression tests trước khi đổi login path, @Order, securityMatcher hoặc policy.

## 21. Tổng kết

Tách nhiều cơ chế xác thực trong Spring Security phải đồng thời tách **phạm vi URL**, **filter mechanism**, **entry point**, **session strategy** và **security policy**:

~~~text
/api/** → HTTP Basic + STATELESS + 401
/web/** → formLogin + HttpSession + CSRF + 302
other   → fallback denyAll
~~~

**Quy tắc quyết định:** `FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp**. `authorizeHttpRequests().requestMatchers` chỉ kiểm tra quyền bên trong chain đã chọn. Mọi login-processing URL, logout URL và OIDC callback phải nằm trong matcher phù hợp; URL còn lại cần được fallback bảo vệ.

Một lần HTTP Basic thành công không tạo web session, và một web session hợp lệ không thay credentials mà API stateless yêu cầu. Đây là hai kiểm chứng rất quan trọng khi ứng dụng kết hợp nhiều kiểu authentication.

## 22. Tài liệu tham khảo

1. [Spring Security 6.5 — Java Configuration và Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): SecurityFilterChain, securityMatcher, @Order và fallback.
2. [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): FilterChainProxy, first matching chain và filter order.
3. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): custom login page, POST processing URL và CSRF.
4. [Spring Security 6.5 — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): BasicAuthenticationFilter và Basic entry point.
5. [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SessionCreationPolicy.STATELESS, SecurityContextRepository.
6. [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF cho browser login, tokens và logout.
7. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): authorization rules và denyAll.
8. [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): formLogin custom URL có CSRF.
9. [Spring Security 6.5 — MockMvc Security Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html): csrf(), httpBasic(), authentication assertions.
10. [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): Bearer/JWT validation, issuer, authority mapping.
11. [Spring Security 6.5 — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): OAuth2 endpoints, callback và ClientRegistration.
12. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): bảo vệ login và error handling.
13. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): token defense, SameSite và ranh giới credential.
