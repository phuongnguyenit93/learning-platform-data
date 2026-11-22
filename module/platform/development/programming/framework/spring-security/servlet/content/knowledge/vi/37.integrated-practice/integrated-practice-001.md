# Ứng dụng MVC dùng form login, phân vai và trang quản trị — Spring Security Servlet

## 1. Bài thực hành này xây dựng gì?

Một ứng dụng web **Spring MVC + Thymeleaf** có trang chủ công khai, trang đăng nhập, trang cá nhân và trang quản trị. Người chưa đăng nhập được điều hướng tới form login khi mở khu vực riêng. Người có quyền **USER** xem được trang cá nhân. Chỉ người có quyền **ADMIN** được truy cập **/admin**; người dùng bình thường tự gõ URL này vẫn bị Spring Security từ chối.

Công nghệ: **Java 17**, **Spring Boot 3.4.5**, **Spring Security 6**, Maven, Spring MVC Servlet, Thymeleaf, JUnit 5 và Spring Security Test. Cấu hình gồm **BCryptPasswordEncoder**, **InMemoryUserDetailsManager** dành cho demo, form authentication, **SecurityFilterChain**, session và **CSRF protection**. Có mã nguồn của các file, thao tác chạy và MockMvc tests.

**Kết quả cần đạt:** không chỉ đăng nhập được, mà còn chứng minh hệ thống từ chối **anonymous**, **password sai**, **CSRF token thiếu** và **ROLE_USER gọi trang quản trị**.

### Chức năng và ma trận truy cập

| URL | Chưa đăng nhập | USER | ADMIN |
| --- | --- | --- | --- |
| GET / | 200 | 200 | 200 |
| GET /login | 200 | Cho phép truy cập | Cho phép truy cập |
| POST /login | Xử lý username/password + CSRF | Xử lý tương tự | Xử lý tương tự |
| GET /account | 302 -> /login | 200 | 200 |
| GET /admin | 302 -> /login | **403** | **200** |
| POST /logout | Cần CSRF theo security chain | Logout + redirect | Logout + redirect |

Trong ví dụ:
- User **reader** có **ROLE_USER**.
- User **admin** có cả **ROLE_USER** và **ROLE_ADMIN**.
- Mật khẩu demo lần lượt là **reader-pass** và **admin-pass**, chỉ dùng trên localhost.

**Authentication** là xác minh danh tính; **authorization** là xác định quyền. Nhận 200 từ một route public không chứng minh caller đã login. Một người đã authenticated nhưng thiếu ROLE_ADMIN vẫn không được truy cập /admin.

## 2. Spring Security form login xử lý request như thế nào?

~~~text
Browser chưa đăng nhập
    |
    +-- GET /account
           |
           v
       Spring Security FilterChainProxy
           |
       AuthorizationFilter yêu cầu authenticated
           |
       AuthenticationEntryPoint
           |
       302 Location: /login
           |
    +-- GET /login
           |
       MVC controller -> Thymeleaf login.html
           |
       Form chứa username/password và CSRF token
           |
    +-- POST /login
           |
       CsrfFilter kiểm tra CSRF
           |
       UsernamePasswordAuthenticationFilter
           |
       AuthenticationManager / DaoAuthenticationProvider
           |
       UserDetailsService + PasswordEncoder.matches(...)
           |
       +---------+-----------+
       |                     |
    Thất bại             Thành công
       |                     |
    302 /login?error     Authentication đã xác minh
                             |
                         SecurityContext
                             |
                         HttpSession
                             |
                         302 /account
                             |
    +-- GET /account kèm session cookie
           |
       SecurityContext được khôi phục
           |
       AuthorizationFilter cho phép
           |
       PageController -> Thymeleaf account.html
~~~

**GET /login** do controller trả trang HTML. **POST /login** được **UsernamePasswordAuthenticationFilter** xử lý theo **loginProcessingUrl("/login")**, không cần và không nên viết controller tự so sánh password cho route đó.

Sau login, Spring Security lưu Authentication trong SecurityContext, và ở cơ chế form-session điển hình, context được liên kết với phiên để request sau dùng session cookie được nhận diện. Framework có các biện pháp về session fixation và session logout; không tự giữ SecurityContext trong singleton/static field.

**Trường hợp /admin:** AuthorizationFilter so sánh GrantedAuthority với rule **hasRole("ADMIN")**. User reader đã login nhưng chỉ có ROLE_USER nên bị 403; việc ẩn liên kết trên HTML không phải hàng rào bảo mật.

## 3. Tạo dự án và phụ thuộc

Cấu trúc file:

~~~text
mvc-role-portal/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/portal/
    │   │   ├── MvcRolePortalApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PortalController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── home.html
    │           ├── login.html
    │           ├── account.html
    │           └── admin.html
    └── test/java/demo/portal/
        └── PortalSecurityTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-role-portal</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

**starter-web** dùng Servlet MVC; **starter-thymeleaf** render HTML; **starter-security** cung cấp filters/providers/security context; **spring-security-test** cho phép dùng **user()**, **csrf()** và test authentication/authorization trong MockMvc. Parent quản lý versions phụ thuộc.

## 4. Java application và cấu hình bảo mật

### 4.1. MvcRolePortalApplication.java

**src/main/java/demo/portal/MvcRolePortalApplication.java**:

~~~java
package demo.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcRolePortalApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcRolePortalApplication.class, args);
    }
}
~~~

### 4.2. SecurityConfiguration.java

**src/main/java/demo/portal/SecurityConfiguration.java**:

~~~java
package demo.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                    .password(encoder.encode("reader-pass"))
                    .roles("USER")
                    .build(),
                User.withUsername("admin")
                    .password(encoder.encode("admin-pass"))
                    .roles("USER", "ADMIN")
                    .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                        "/", "/login", "/error", "/css/**")
                        .permitAll()
                    .requestMatchers("/admin", "/admin/**")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated()
                )
                .formLogin(form -> form
                    .loginPage("/login")
                    .loginProcessingUrl("/login")
                    .defaultSuccessUrl("/account", false)
                    .permitAll()
                )
                .logout(logout -> logout
                    .logoutUrl("/logout")
                    .logoutSuccessUrl("/login?logout")
                    .invalidateHttpSession(true)
                    .clearAuthentication(true)
                    .permitAll()
                )
                // CSRF protection giữ mặc định cho form web.
                .build();
    }
}
~~~

**Phân tích từng thành phần:**

1. **BCryptPasswordEncoder** thực hiện hashing mật khẩu với salt. Khác với lưu plaintext, encoder được dùng trong UserDetailsService và AuthenticationProvider phù hợp. Để thực hành, hai password vẫn xuất hiện trong source, nên **không đưa nguyên demo lên production**. Production cần lưu hash trong database/IdP, secret management, policy và rate limiting.
2. **InMemoryUserDetailsManager** tạo user mẫu. **.roles("USER")** sinh authority **ROLE_USER**; **.roles("USER", "ADMIN")** sinh **ROLE_USER** và **ROLE_ADMIN**.
3. **requestMatchers(...).permitAll()** chỉ mở những URL công khai. **/admin** và mọi nhánh **/admin/** được bảo vệ bằng hasRole trước fallback.
4. **hasRole("ADMIN")** mặc định yêu cầu **ROLE_ADMIN**. Không đặt chuỗi có prefix vào **.roles("ROLE_ADMIN")**; method roles tự thêm prefix.
5. **anyRequest().authenticated()** yêu cầu đăng nhập cho mọi URL còn lại, bao gồm **/account**.
6. **loginPage("/login")** chỉ nơi hiển thị form; **loginProcessingUrl("/login")** đặt endpoint xử lý POST form.
7. **defaultSuccessUrl("/account", false)** dùng /account khi không có saved request. Khi người dùng trước login đã yêu cầu một trang bảo vệ, SavedRequestAwareAuthenticationSuccessHandler có thể ưu tiên request được lưu; xem mục 10.
8. **logoutUrl("/logout")** dùng method POST khi CSRF đang bật; **invalidateHttpSession(true)** và **clearAuthentication(true)** để kết thúc phiên local.
9. **Không dùng csrf.disable()** trong web app dựa vào session cookie chỉ để test form. Dùng token đúng trong HTML và MockMvc.
10. Nếu thêm API Bearer/Resource Server, có thể cần **SecurityFilterChain riêng với securityMatcher và entry point phù hợp**; không mặc định trả 302 HTML login cho JSON API.

### 4.3. PortalController.java

**src/main/java/demo/portal/PortalController.java**:

~~~java
package demo.portal;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PortalController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/account")
    public String account(Model model,
                          Authentication authentication) {
        model.addAttribute("displayName", authentication.getName());

        boolean isAdmin = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_ADMIN"::equals);
        model.addAttribute("showAdminLink", isAdmin);

        return "account";
    }

    @GetMapping("/admin")
    public String admin(Model model,
                        Authentication authentication) {
        model.addAttribute("displayName", authentication.getName());
        return "admin";
    }
}
~~~

**@Controller** trả tên view **home/login/account/admin**, không trả tên template làm JSON. Spring MVC tìm HTML trong resources/templates.

Controller nhận **Authentication** đã được security infrastructure xác minh. **authentication.getName()** dùng cho demo hiển thị; nó không phải bằng chứng có quyền trên mọi tài nguyên. Khi ứng dụng có dữ liệu của nhiều tenants, service còn phải kiểm tra owner/ACL.

Biến **showAdminLink** chỉ điều khiển giao diện. Reader có thể tự gõ /admin; server vẫn phải trả **403** từ rule hasRole. Không thực hiện security bằng cách chỉ ẩn menu.

**GET /login** do controller render. **POST /login** do UsernamePasswordAuthenticationFilter xử lý; **không cần @PostMapping("/login")** để tự kiểm tra password.

## 5. Giao diện Thymeleaf HTML

Tạo bốn file trong **src/main/resources/templates/**, dùng cú pháp **th:** của Thymeleaf. Các biểu thức trong dấu ngoặc nhọn dưới đây được xử lý tại server khi template render.

### 5.1. home.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang chủ MVC Portal</title>
</head>
<body>
    <h1>Chào mừng đến MVC Portal</h1>
    <p>Thực hành Spring Security form login và phân vai.</p>
    <nav>
        <a th:href="@{/login}">Đăng nhập</a>
        <a th:href="@{/account}">Trang tài khoản</a>
    </nav>
</body>
</html>
~~~

Trang chủ được **permitAll()**, nên không cần Authentication. Link /account có thể hiển thị công khai; nếu chưa đăng nhập, security chain redirect khách về /login.

### 5.2. login.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <main>
        <h1>Đăng nhập</h1>

        <p th:if="${param.error}">
            Sai tên đăng nhập hoặc mật khẩu.
        </p>
        <p th:if="${param.logout}">
            Bạn đã đăng xuất.
        </p>

        <form th:action="@{/login}" method="post">
            <label for="username">Tên đăng nhập</label>
            <input id="username" name="username"
                   type="text" autocomplete="username" required>

            <label for="password">Mật khẩu</label>
            <input id="password" name="password"
                   type="password" autocomplete="current-password" required>

            <input type="hidden"
                   th:name="${_csrf.parameterName}"
                   th:value="${_csrf.token}">
            <button type="submit">Đăng nhập</button>
        </form>
        <a th:href="@{/}">Về trang chủ</a>
    </main>
</body>
</html>
~~~

**name="username"** và **name="password"** khớp mặc định của UsernamePasswordAuthenticationFilter. Đổi tên input mà quên cấu hình **usernameParameter/passwordParameter** sẽ khiến đăng nhập sai dù người dùng nhập đúng dữ liệu.

**_csrf** do Spring Security expose; hidden field gửi token được server kiểm tra ở POST. Với Thymeleaf Spring MVC, **th:action** có thể tự chèn CSRF hidden field theo RequestDataValueProcessor; ví dụ trình bày rõ hidden field để học cơ chế. Khi xem HTML thực tế, nếu đã có token do engine chèn tự động thì nên tránh render trùng một trường _csrf không cần thiết; một token hợp lệ là đủ.

**Thông báo lỗi:** khi password sai, form failure handler redirect về **/login?error**. Khi logout thành công, redirect về **/login?logout**. Template dùng **param.error/param.logout** để hiển thị trạng thái, không tự trả lỗi chi tiết làm lộ tài khoản nào tồn tại.

### 5.3. account.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang tài khoản</title>
</head>
<body>
    <main>
        <h1>Tài khoản</h1>
        <p>Xin chào, <strong th:text="${displayName}">
            Người dùng
        </strong></p>

        <a th:if="${showAdminLink}"
           th:href="@{/admin}">
            Trang quản trị
        </a>

        <form th:action="@{/logout}" method="post">
            <input type="hidden"
                   th:name="${_csrf.parameterName}"
                   th:value="${_csrf.token}">
            <button type="submit">Đăng xuất</button>
        </form>
    </main>
</body>
</html>
~~~

**th:text** escape HTML trong tên user; không thay bằng **th:utext** với dữ liệu không tin cậy. **th:if** chỉ ẩn link quản trị khi user thiếu ROLE_ADMIN; server-side **hasRole** vẫn cần và vẫn được kiểm thử độc lập.

### 5.4. admin.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang quản trị</title>
</head>
<body>
    <main>
        <h1>Bảng điều khiển quản trị</h1>
        <p>Quản trị viên:
            <strong th:text="${displayName}">admin</strong>
        </p>
        <p>Trang này yêu cầu ROLE_ADMIN.</p>
        <a th:href="@{/account}">Về tài khoản</a>

        <form th:action="@{/logout}" method="post">
            <input type="hidden"
                   th:name="${_csrf.parameterName}"
                   th:value="${_csrf.token}">
            <button type="submit">Đăng xuất</button>
        </form>
    </main>
</body>
</html>
~~~

Trang admin không tự thực hiện các thao tác nhạy cảm để bài tập tập trung vào phân quyền web. Nếu bổ sung POST tạo user, xóa tài khoản hoặc đổi role, phải có kiểm soát authorization/validation/CSRF/audit ở cả controller và service, không chỉ hiển thị nút trong HTML.

### 5.5. application.properties

**src/main/resources/application.properties**:

~~~properties
spring.application.name=mvc-role-portal
server.port=8080
spring.thymeleaf.cache=false
~~~

**spring.thymeleaf.cache=false** chỉ để dễ thay template khi học. Production nên cấu hình cache và security headers/session timeout/TLS phù hợp.

## 6. Khởi động và thử thủ công

Cần JDK 17+ và Maven. Từ thư mục có pom.xml:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Mở **http://localhost:8080/**. Thực hiện:

1. Chưa đăng nhập, nhấn **Trang tài khoản**; browser được chuyển hướng sang /login.
2. Đăng nhập **reader / reader-pass**. Trang /account hiển thị reader, không hiển thị link quản trị.
3. Tự gõ **http://localhost:8080/admin**. Spring Security trả **403**, không render admin.html.
4. Nhấn **Đăng xuất** bằng form POST, quay lại /login?logout.
5. Đăng nhập **admin / admin-pass**, từ trang /account mở /admin; trang quản trị hiển thị tên admin.
6. Nhập sai password khi login để thấy /login?error.
7. Trong test, thử POST login/logout thiếu CSRF để xác nhận 403.

Đây là **ứng dụng đào tạo cục bộ** với credentials demo, không triển khai trực tiếp lên Internet.

### 6.1. Kỳ vọng HTTP

| Request | HTTP status | Ý nghĩa |
| --- | --- | --- |
| Anonymous GET / | 200 | Trang công khai |
| Anonymous GET /login | 200 | Form login HTML |
| Anonymous GET /account | 302 | Location tới /login |
| Anonymous GET /admin | 302 | Location tới /login |
| Reader GET /account | 200 | Trang tài khoản |
| Reader GET /admin | 403 | Đủ authentication, thiếu authorization |
| Admin GET /admin | 200 | Đủ ROLE_ADMIN |
| POST /login thiếu CSRF | 403 | CsrfFilter từ chối |
| POST /login sai password, CSRF đúng | 302 | Location /login?error |
| POST /login đúng, không có saved request | 302 | Location /account |
| POST /logout, CSRF đúng | 302 | Location /login?logout |

Trong browser, redirect được tự theo; URL cuối có thể là /login trả 200. Để kiểm tra **response ban đầu**, dùng MockMvc hoặc curl không bật chế độ follow redirect. Status 302 không đồng nghĩa login thành công; cũng có thể là redirect tới trang login vì chưa đăng nhập.

## 7. Bộ kiểm thử MockMvc

Tạo **src/test/java/demo/portal/PortalSecurityTests.java**.

~~~java
package demo.portal;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class PortalSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void homeIsPublic() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(view().name("home"))
                .andExpect(content().string(
                        containsString("MVC Portal")));
    }

    @Test
    void loginPageIsPublic() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(view().name("login"))
                .andExpect(content().string(
                        containsString("Đăng nhập")));
    }

    @Test
    void anonymousAccountRedirectsToLogin() throws Exception {
        mvc.perform(get("/account"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void anonymousAdminRedirectsToLogin() throws Exception {
        mvc.perform(get("/admin"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void readerSeesAccountButNotAdminLink() throws Exception {
        mvc.perform(get("/account")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(view().name("account"))
                .andExpect(model().attribute(
                        "displayName", "reader"))
                .andExpect(model().attribute(
                        "showAdminLink", false));
    }

    @Test
    void readerCannotOpenAdminPage() throws Exception {
        mvc.perform(get("/admin")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdminPage() throws Exception {
        mvc.perform(get("/admin")
                        .with(user("admin").roles("USER", "ADMIN")))
                .andExpect(status().isOk())
                .andExpect(view().name("admin"))
                .andExpect(model().attribute(
                        "displayName", "admin"));
    }

    @Test
    void formLoginWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "reader")
                        .param("password", "reader-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordRedirectsToLoginError() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "reader")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void successfulLoginCreatesSessionAndAllowsAccount()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "reader")
                        .param("password", "reader-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/account"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/account").session(session))
                .andExpect(status().isOk())
                .andExpect(view().name("account"))
                .andExpect(model().attribute(
                        "displayName", "reader"));
    }

    @Test
    void logoutWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/logout"))
                .andExpect(status().isForbidden());
    }

    @Test
    void successfulLogoutRedirectsToConfirmation()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "admin")
                        .param("password", "admin-pass"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }
}
~~~

**Có 12 phương thức @Test.** Nhóm tests này bao phủ public routes, anonymous redirect, role USER/ADMIN, CSRF, login failure/success và logout. **mvn test** được kỳ vọng chạy bộ tests thành công trên JDK/Maven với dependencies tương thích, nhưng cần chạy thật để xác nhận; code tại đây mới được kiểm tra tĩnh.

### 7.1. Vì sao cần cả mock user và form login thật?

**.with(user("admin").roles("ADMIN"))** cung cấp Authentication cho request MockMvc. Nó hữu ích khi chỉ muốn kiểm tra **hasRole** và render controller, nhưng **không kiểm tra password hoặc BCrypt**.

**POST /login** với **.with(csrf())** và **.param("username", ...).param("password", ...)** đi qua authentication filter/provider của test app, kiểm tra cấu hình UserDetailsService/PasswordEncoder và luồng login. Test request thứ hai với cùng MockHttpSession chứng minh session được dùng qua nhiều requests.

**Không nhầm MockMvc với embedded HTTP server thật:** TLS, cookie Secure/HttpOnly/SameSite trên mạng, proxy headers và các IdP bên ngoài cần thêm integration/E2E tests riêng.

### 7.2. Test view name khác test render HTML

**view().name("admin")** xác nhận handler chọn template đúng. **content().string(...)** xác minh HTML đã render có text kỳ vọng. Nếu cần test role-based menu, có thể assert HTML của reader không chứa link /admin, còn HTML của admin có. Tuy vậy **quan trọng nhất vẫn là request reader tới /admin trả 403**.

### 7.3. Test saved request và role sau login

Ví dụ: anonymous cố GET /admin, Spring Security chuyển 302 tới /login và lưu URL cần truy cập trong session theo RequestCache. Nếu sau đó reader login, success handler có thể redirect về /admin đã lưu; request tiếp theo **vẫn phải nhận 403** vì reader thiếu ROLE_ADMIN.

Đây là khác biệt giữa **defaultSuccessUrl("/account", false)** (có thể phục hồi saved request) với **true** (luôn dùng default target). Bài mẫu test case login thành công *không có saved request*, nên assert /account là hợp lệ.

Nếu thêm test saved request, hãy giữ cùng MockHttpSession giữa GET bị redirect và POST login, kiểm tra Location theo contract, rồi GET /admin bằng session để xác nhận 403. Không suy luận saved request tạo thêm quyền.

## 8. CSRF và session trong ứng dụng browser

### 8.1. Vì sao không tắt CSRF?

Browser gửi cookie phiên theo quy tắc cookie, và một trang bên ngoài có thể tìm cách khiến browser phát sinh POST. CSRF token giúp server xác minh request thay đổi trạng thái được tạo trong ngữ cảnh hợp lệ. Login CSRF cũng có thể tạo tác động khó nhận ra khi attacker cố ép browser đăng nhập vào tài khoản do họ kiểm soát.

Các request GET của bài không cần token khi chỉ đọc, trong khi **POST /login** và **POST /logout** cần token. Với HTML form, trường hidden dùng token do Spring Security cấp:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

Trong MockMvc, dùng **.with(csrf())**; muốn kiểm tra token sai, **.with(csrf().useInvalidToken())**. Đừng viết **csrf.disable()** hoặc đổi POST login thành GET chỉ để tránh 403.

### 8.2. Form login và session lifecycle

Spring Security có bảo vệ **session fixation**; khi user xác thực, session ID có thể được đổi hoặc session được migrate theo Servlet container và cấu hình. **JSESSIONID** là session identifier, không phải token được đưa vào business logs.

Trên production:
- Bắt buộc HTTPS, cấu hình cookie **Secure**, **HttpOnly**, **SameSite** theo môi trường.
- Cấu hình session timeout và cơ chế invalidation khi logout/password reset/offboarding.
- Với nhiều instances, cân nhắc Spring Session/distributed session repository.
- Không log raw password, Authorization header, cookie hoặc SecurityContext.
- Xác minh authorities trong session không còn stale sau khi đổi quyền nhạy cảm.
- Phân biệt local logout với logout ở IdP nếu sau này thêm OIDC.

### 8.3. POST logout và bảo mật cookie

Một liên kết **GET /logout** không thay thế form POST khi CSRF đang bật. Dùng POST và CSRF hợp lệ. **logoutSuccessUrl("/login?logout")** chỉ xác nhận browser được điều hướng tới trang thông báo; muốn chứng minh session bị vô hiệu thì phải kiểm tra request tiếp theo với cookie cũ hoặc trạng thái session trong integration test.

Ở MockMvc, MockHttpSession mô phỏng session nhưng không thể thay thế hoàn toàn hành vi Set-Cookie/Cookie qua HTTP/TLS thực, nên kiểm thử cookie flags nên dùng embedded server test.

## 9. Quyền UI và quyền thực sự ở server

**Ẩn link admin** bằng showAdminLink chỉ là thiết kế giao diện; không làm endpoint an toàn. Server phải giữ **hasRole("ADMIN")** cho /admin và các route con.

Đối với một trang quản trị thật, nên bảo vệ thêm **service layer**. Ví dụ trích đoạn (không standalone):

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void disableAccount(long accountId) {
    service.disableAccount(accountId);
}
~~~

Phải bật **@EnableMethodSecurity** khi sử dụng method authorization. Với thao tác cụ thể, còn cần kiểm tra tenant, ownership, separation of duties, audit và validation. Không tin role khai báo trong form JSON/hidden field.

Spring Security **hasRole("ADMIN")** thường đòi GrantedAuthority **ROLE_ADMIN**. Nếu dùng **.authorities("ADMIN")** nhưng lại yêu cầu hasRole("ADMIN"), request có thể bị 403. Kiểm tra đúng authority string, không bỏ authorization để sửa.

## 10. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| GET /account -> 302 | Chưa đăng nhập/không có session | Theo redirect /login, xác minh cookie |
| reader GET /admin -> 403 | Chính sách đúng | Không mở permitAll để “sửa” |
| admin GET /admin -> 403 | Sai username, roles, authority prefix | Kiểm tra ROLE_ADMIN và authenticated user |
| POST /login -> 403 | CSRF thiếu/sai | Kiểm tra _csrf, session, CsrfFilter |
| POST /login -> /login?error | Password/user không khớp | Kiểm tra input name, encoder, UserDetailsService |
| Controller POST /login không được gọi | Filter đã xử lý route | Không cần controller login POST |
| Trang login 404 | Thiếu controller hoặc template login.html | Kiểm tra @GetMapping("/login") và resources/templates |
| Template render exception | Sai Model attribute/Thymeleaf expression | Kiểm tra th:text và controller |
| Login thành công nhưng redirect khác /account | Saved request được ưu tiên | Kiểm tra defaultSuccessUrl(false), RequestCache |
| Logout button bị 403 | Thiếu CSRF | POST form chứa CSRF token |
| Link admin ẩn nhưng URL vẫn truy cập được | Chỉ ẩn UI, server rule thiếu | Thêm hasRole trong SecurityFilterChain |
| MockMvc with(user()) pass, login thật thất bại | Mock user không kiểm tra password | Test POST /login credentials đúng/sai |
| Phiên còn hoạt động sau logout SSO | Chỉ logout local app | Thiết kế IdP session/logout riêng |
| Admin vào trang nhưng xem sai tenant | Chỉ có role, chưa object ACL | Authorization theo tài nguyên ở service |
| Username thành HTML/script không mong muốn | Dùng th:utext hoặc render unsafe | Dùng th:text và output escaping |

**Quy trình debug:** URL/method → SecurityFilterChain match → CsrfFilter → UsernamePasswordAuthenticationFilter → AuthenticationManager/UserDetailsService/PasswordEncoder → Authentication authorities → AuthorizationFilter → MVC controller → Thymeleaf → session/Location. Lỗi 403 có thể là **CSRF** hoặc **thiếu quyền**, không được kết luận khi chưa xem tầng nào từ chối.

## 11. Nâng cấp an toàn trước khi đưa vào môi trường thật

- Thay InMemoryUserDetailsManager bằng một UserDetailsService với persistence phù hợp, quản lý password hash và quyền theo IAM/IdP.
- Không lưu username/password production trong source code, Git, build artifact hoặc log.
- Có password policy, lockout/rate-limiting, monitoring thử mật khẩu và MFA/step-up cho tài khoản admin.
- Dùng HTTPS/cookie Secure/HttpOnly/SameSite và chính sách session expiration.
- Dùng CSRF cho browser mutations; không dựa riêng vào SameSite.
- Thêm authorization ở service theo tenant/ACL/object, không chỉ URL roles.
- Audit login success/failure, logout và admin operations nhưng không log credentials.
- Xử lý user disabled/deleted và invalidate active sessions theo revocation policy.
- Có error page phù hợp cho 403 nhưng không tiết lộ cấu hình hoặc dữ liệu nhạy cảm.
- Với SPA/API, thiết kế riêng Bearer/JWT/Resource Server và 401/403 JSON theo contract, không ép API đi qua form-login HTML.
- Kiểm thử redirect target, open redirect và saved request; không cho client chọn URL ngoài allowlist một cách tự do.
- Không serialize nguyên Authentication hoặc SecurityContext xuống HTML/JSON.
- Chạy unit/integration tests trên môi trường thật, test trên nhiều browsers/nodes nếu dùng distributed sessions.

## 12. Bài tập mở rộng

**Bài A:** Thêm **GET /reports** cho mọi user đã login. Test anonymous 302, reader 200 và admin 200.

**Bài B:** Thêm POST **/admin/users/disable**. Bắt buộc có Role ADMIN, CSRF, validation, service-layer authorization, audit. Test reader 403, admin thiếu CSRF 403 và admin request hợp lệ được xử lý.

**Bài C:** Bật **@EnableMethodSecurity** và dùng **@PreAuthorize** trên service quản trị. Kiểm tra security ở service vẫn chặn nếu controller được refactor.

**Bài D:** Xây dựng test SavedRequest: anonymous yêu cầu /admin, browser login bằng reader, redirect trở lại /admin nhưng nhận 403. Làm tiếp với admin sẽ vào được /admin. Phân biệt URL đích và quyền.

**Bài E:** Thay lưu user in-memory bằng database, dùng BCrypt, account enabled/locked, gỡ role và thu hồi HttpSession cũ. Phân tích vì sao thay đổi user store không tự sửa mọi Authentication đang lưu trong session.

## 13. Checklist nghiệm thu

- [ ] Java 17 và Maven chạy được; file/package paths trùng code.
- [ ] GET / và GET /login trả trang HTML công khai.
- [ ] Anonymous GET /account, /admin được redirect tới /login.
- [ ] POST /login đi qua UsernamePasswordAuthenticationFilter.
- [ ] Password sai đưa về /login?error, không cấp quyền.
- [ ] Login đúng tạo session, GET /account tiếp theo hiển thị đúng user.
- [ ] reader chỉ có ROLE_USER, GET /admin bị 403.
- [ ] admin có ROLE_ADMIN, GET /admin thành công.
- [ ] UI chỉ hiện liên kết quản trị cho admin, nhưng server vẫn chặn URL trực tiếp.
- [ ] PasswordEncoder BCrypt và UserDetailsService cấu hình đúng.
- [ ] CSRF bảo vệ POST /login và POST /logout; không gọi csrf.disable().
- [ ] Logout dùng POST/CSRF, invalidates session và redirect /login?logout.
- [ ] MockMvc có đủ positive và negative tests, bao gồm session continuity.
- [ ] Không trả password, raw Authentication hoặc session cookie vào view/log.
- [ ] Có kế hoạch TLS, session management, account revoke, audit và service authorization cho production.

## 14. Câu hỏi tự kiểm tra

1. **GET /login khác POST /login ở đâu?** GET do MVC render; POST do authentication filter xử lý.
2. **ROLE_USER có vào /admin được không?** Không, vì rule hasRole ADMIN chặn.
3. **Ẩn link admin trên HTML đã đủ không?** Không; server phải kiểm tra quyền trên URL.
4. **Anonymous vào /account nhận gì?** Theo form-login contract, thường 302 tới /login.
5. **User đã login nhưng thiếu quyền vào /admin nhận gì?** Thường 403.
6. **.roles("ADMIN") tạo authority nào?** ROLE_ADMIN.
7. **Vì sao POST /login yêu cầu CSRF?** Ngăn request thay đổi trạng thái trái ý khi browser dùng cookie/session.
8. **.with(user("reader")) có kiểm tra password với BCrypt không?** Không; nó dựng user mock cho test authorization.
9. **Bài nào kiểm tra credential thật của demo?** POST /login với CSRF và username/password rồi kiểm tra session.
10. **defaultSuccessUrl("/account", false) có luôn trả /account?** Không, saved request có thể được ưu tiên.
11. **Logout local form-login có kết thúc session OIDC bên ngoài không?** Không áp dụng; OIDC là flow khác và cần logout riêng.
12. **Một admin có được xem mọi record mọi tenant không?** Không mặc định, phải kiểm tra quyền ở resource/service.
13. **Tại sao không tắt CSRF khi test bị 403?** Vì cần sửa form/token hoặc xác định nguyên nhân, không phá lớp bảo vệ.
14. **Project dùng InMemoryUserDetailsManager có sẵn sàng production không?** Không, nó chỉ giúp minh họa form login và phân vai.

**Kết luận:** Một ứng dụng MVC an toàn không chỉ có màn hình đăng nhập. Nó phải có **cơ chế xác thực Spring Security, SecurityFilterChain bảo vệ USER/ADMIN, session/CSRF đúng, controller MVC và template hiển thị có escape**, và những test chứng minh cả đường **được phép** lẫn **bị từ chối**. Chỉ khi anonymous, sai password, thiếu CSRF và thiếu ROLE_ADMIN đều không vượt qua được policy thì bài thực hành phân vai mới hoàn chỉnh.
