# formLogin, httpBasic và logout trong kiểm thử Servlet

Trong ứng dụng **Spring Security Servlet**, kiểm thử đăng nhập không chỉ là đặt một `Authentication` giả vào test rồi mong endpoint trả HTTP 200. Để chứng minh đúng cơ chế đăng nhập, bài test phải thực sự chạy **Spring Security Filter Chain**, đưa đúng **HTTP request** qua filter tương ứng, xác minh **kết quả xác thực và quyền truy cập**, đồng thời kiểm tra được **CSRF, session và logout**.

Bộ công cụ `spring-security-test` cung cấp ba helper rất hữu ích cho `MockMvc`:

- **`formLogin()`**: tạo **POST** đăng nhập qua form, kèm CSRF token hợp lệ, cho phép đặt username/password hoặc đổi URL và tên tham số.
- **`httpBasic(username, password)`**: là `RequestPostProcessor` thêm header `Authorization: Basic ...` vào một request; nó **không** tạo phiên đăng nhập qua form.
- **`logout()`**: tạo **POST** logout có CSRF token; dùng để kiểm tra `LogoutFilter` và cấu hình URL/logout handler.

Bài học thuộc nhóm **Kiểm thử đăng nhập**, sử dụng **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x**, JUnit Jupiter và `MockMvc`. Nội dung gồm giải thích luồng xử lý, ví dụ Spring Boot hoàn chỉnh, các ca kiểm thử hợp lệ và lỗi, cách dùng session qua nhiều request, phân biệt HTTP 401/403/302, kiểm thử CSRF, logout thật và những sai lầm thường gặp khi chỉ mock user.

## 1. Mục tiêu kiểm thử: đang test filter hay chỉ test authorization?

Câu hỏi đầu tiên trước khi viết test là **mình muốn kiểm điều gì?**

| Mục đích | Công cụ phù hợp | Tầng nào được kiểm tra? |
| --- | --- | --- |
| Controller có trả đúng dữ liệu cho user mang role `USER`? | `@WithMockUser` hoặc `with(user("..."))` | Chủ yếu authorization và controller; **bỏ qua việc kiểm tra password thực** |
| Form login xác minh username/password đúng, sai? | `mvc.perform(formLogin().user(...).password(...))` | `UsernamePasswordAuthenticationFilter` → `AuthenticationManager` → provider, CSRF và handler |
| API chấp nhận Basic Auth thực? | `mvc.perform(get(...).with(httpBasic(...)))` | `BasicAuthenticationFilter`/provider, HTTP status và quyền |
| Logout bằng POST có CSRF có xử lý đúng? | `mvc.perform(logout())` | `LogoutFilter`, logout handlers và redirect theo cấu hình |
| Logout có **xóa session đã đăng nhập** không? | Tạo session qua `formLogin()`, sau đó `post("/logout").session(session).with(csrf())` | Cơ chế vô hiệu hóa session/context và request tiếp theo |
| Bảo vệ CSRF có làm việc? | `post("/login")`/`post("/logout")` **không** `with(csrf())` | `CsrfFilter` từ chối unsafe request |
| Browser có nhận cookie, redirect và lưu session trong nhiều replica? | E2E/browser hoặc HTTP integration test thực | Vượt phạm vi `MockMvc`, cần hạ tầng gần production |

**Không đánh đồng** `with(user("student"))` với `formLogin().user("student")`. Ở cách thứ nhất, Spring Security Test **đặt sẵn một principal đã được xác thực**; ở cách thứ hai, hệ thống phải **xác minh password thật** theo `UserDetailsService`/`PasswordEncoder` đang cấu hình.

Tương tự, `httpBasic(...)` chỉ tạo header cho một request; HTTP Basic thường là cơ chế xác thực **mỗi request**, không có nghĩa nó đã tạo ra session đăng nhập như form login. Muốn thử password hash hoặc Basic Authentication Entry Point, phải chạy request thực qua filter chain.

## 2. Các thành phần và request trong Servlet

~~~text
Browser/HTTP test
       │
       ▼
MockMvc + Spring Security FilterChainProxy
       │
       ├── POST /login + CSRF, username/password
       │       │
       │       ▼
       │   UsernamePasswordAuthenticationFilter
       │       │
       │       ▼
       │   AuthenticationManager → AuthenticationProvider
       │       ├─ thành công → SecurityContext/session → success handler
       │       │                              └─ redirect (thường 302)
       │       └─ thất bại  → failure handler (thường /login?error)
       │
       ├── GET /api/me + Authorization: Basic <Base64>
       │       │
       │       ▼
       │   BasicAuthenticationFilter
       │       ├─ đúng  → Authentication cho request → controller/authorization
       │       └─ sai   → AuthenticationEntryPoint (thường HTTP 401)
       │
       └── POST /logout + CSRF
               │
               ▼
           LogoutFilter
               ├─ clear SecurityContext, invalidate session
               ├─ cleanup remember-me/CSRF (tùy config)
               └─ logout success handler (thường /login?logout)
~~~

**Thứ tự thực tế** của các filter và điểm xử lý error phụ thuộc `SecurityFilterChain`, cơ chế authentication đang bật và Spring Security version. Trong ví dụ, cả form login và HTTP Basic dùng **cùng `UserDetailsService` và `PasswordEncoder`**, nhưng chúng là hai cửa vào HTTP khác nhau.

### 2.1. POST login khác GET trang đăng nhập

- `GET /login`: thường là trang nhập thông tin và có form chứa CSRF token. Nó **không tự thực hiện authentication**.
- `POST /login`: mặc định là URL do `UsernamePasswordAuthenticationFilter` nhận, đọc tham số `username` và `password`.
- Khi password đúng: Spring Security form login thường tạo redirect, không nhất thiết trả HTTP 200 trực tiếp tại POST.
- Khi sai: thường redirect sang `/login?error`, **không phải HTTP 401**, trừ khi ứng dụng tùy chỉnh failure handler.
- Nếu thiếu CSRF: `CsrfFilter` thường trả HTTP 403 **trước khi** user/password được xác minh.

### 2.2. HTTP Basic khác session login

Với HTTP Basic, request gửi:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
Accept: application/json
Authorization: Basic <base64-of-username-colon-password>
~~~

Base64 chỉ là **encoding**, không phải mã hóa bảo mật. **Bắt buộc HTTPS trong production**. Basic header phải được tạo từ dữ liệu thử nghiệm, không ghi raw credentials/header vào log. Một request Basic hợp lệ có thể trả 200 nếu user được authorize; request sau **không có header Basic** không nhất thiết có authentication tương ứng. Đừng mặc định HTTP Basic tạo session.

### 2.3. Logout khác “xóa cookie ở client”

Logout của Spring Security Servlet thường gồm `LogoutFilter`, `SecurityContextLogoutHandler` và các logout handlers khác. Khi CSRF đang bật, **POST /logout với CSRF token** mới là hành động logout thực; `GET /logout` mặc định thường hiển thị trang xác nhận thay vì logout ngay.

Kết quả server redirect sang `/login?logout` chỉ là một bằng chứng. Phải xác minh **session bị invalidated**, `SecurityContext` được xóa và **request tiếp theo** không còn được xem là đã đăng nhập. Nếu Basic credentials lại được gửi trong request tiếp theo, hệ thống có thể xác thực mới bình thường; logout không xóa password trên client.

## 3. Bộ dependency và các static imports cần biết

### 3.1. Gradle dependencies

Đoạn đặt vào `build.gradle` Groovy DSL của một project Spring Boot **đã khai báo plugin và Java 17+**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Nếu dùng Maven, tương ứng cần `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` (scope test) và `spring-security-test` (scope test), để Spring Boot BOM quản lý phiên bản. Không trộn Spring Security test 6.5 với runtime security 6.3 rồi kỳ vọng API cùng hoạt động.

Trong Spring Boot 3.5, `@AutoConfigureMockMvc` cấu hình `MockMvc` cho integration test và thường đăng ký filter chain từ ứng dụng nếu có dependency security; cần kiểm tra project có đang **tắt filters** bằng `addFilters=false` hoặc dùng standalone setup không có Security không.

### 3.2. Static imports chuẩn

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

**Lưu ý Java:** cách xuống dòng với dấu chấm **ở đầu dòng** trong import như minh họa là hợp lệ về mặt cú pháp Java (whitespace giữa token); nhưng để dễ copy và đọc nên viết thành từng import **một dòng** trong file test hoàn chỉnh bên dưới.

Những static imports trên không cùng package:
- `formLogin` và `logout` thuộc **`SecurityMockMvcRequestBuilders`**.
- `httpBasic` và `csrf` thuộc **`SecurityMockMvcRequestPostProcessors`**.
- `authenticated` và `unauthenticated` thuộc **`SecurityMockMvcResultMatchers`**.

Đây là lỗi import thường gặp. Đừng tìm `SecurityMockMvcRequestBuilders.httpBasic`; helper `httpBasic` dùng cùng `with(...)` trên một request builder thông thường.

## 4. Dựng ứng dụng mẫu Spring Boot chạy được

Ví dụ dùng một ứng dụng Spring MVC nhỏ, hai tài khoản **chỉ dành cho lab**:

| User | Password thử nghiệm | Authorities |
| --- | --- | --- |
| `student` | `student-lab-pass` | `ROLE_USER` |
| `admin` | `admin-lab-pass` | `ROLE_ADMIN` |

Không dùng mật khẩu này cho bất cứ tài khoản thật nào. Chúng được cố định **chỉ để test có tính xác định**; production phải dùng secret quản lý đúng cách, tài khoản trong database/IdP, HTTPS và chính sách mật khẩu theo chuẩn của tổ chức. Password lưu trong `InMemoryUserDetailsManager` đã qua BCrypt, không phải plaintext trong kho user.

### 4.1. File ứng dụng

Tạo `src/main/java/example/servlettest/ServletAuthDemoApplication.java`:

~~~java
package example.servlettest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletAuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAuthDemoApplication.class, args);
    }
}
~~~

### 4.2. SecurityFilterChain, user store và endpoints

Tạo `src/main/java/example/servlettest/DemoSecurityConfig.java`:

~~~java
package example.servlettest;

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

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("student-lab-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-lab-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(student, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll());

        http.httpBasic(Customizer.withDefaults());
        http.logout(Customizer.withDefaults());

        // CSRF giữ mặc định: POST /login và POST /logout cần token.
        return http.build();
    }
}
~~~

Tạo `src/main/java/example/servlettest/DemoEndpoints.java`:

~~~java
package example.servlettest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoEndpoints {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "private:" + authentication.getName();
    }

    @GetMapping("/api/me")
    String currentUser(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-only";
    }
}
~~~

**Giải thích cấu hình:**

1. `/public` dành cho cả anonymous user; `/private` và `/api/me` yêu cầu authenticated; `/admin` yêu cầu `ROLE_ADMIN`.
2. `formLogin` có default login page và xử lý POST `/login`; `defaultSuccessUrl("/private", true)` buộc redirect đến `/private` sau login thành công, tạo kỳ vọng rõ cho bài test.
3. `httpBasic` cho phép cùng một account đăng nhập bằng header Basic trên request thích hợp. Nếu một request HTTP Basic sai password, `BasicAuthenticationFilter` thường trả 401.
4. `logout` sử dụng cấu hình mặc định, gồm POST `/logout` có CSRF, invalidates session, clears `SecurityContext` và redirect `/login?logout`.
5. Không disable CSRF, không dùng `SessionCreationPolicy.STATELESS`, vì bài cần kiểm tra form session thật.
6. Code không khai báo controller xử lý `POST /login` hay `POST /logout`: các URL này do **Spring Security filters** nhận trước controller.
7. Trong production, cấu hình cơ chế HTTP Basic và form login trên cùng toàn bộ URL cần được đánh giá kỹ về chấp nhận scheme/Accept header; demo bật cả hai để so sánh.
8. Form login/HTTP Basic đều dùng `DaoAuthenticationProvider`/`PasswordEncoder` trong cấu hình thông thường. Vì mã này là sample, không có password reset, MFA, account lock, rate limit hoặc JDBC identity storage.

Khi chạy với JDK 17 và Gradle wrapper, dùng:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Browser có thể mở `http://localhost:8080/login` để xem form demo, nhưng **không truyền password thật qua HTTP ngoài localhost**; hệ production phải dùng HTTPS.

## 5. File kiểm thử tích hợp: formLogin + httpBasic + logout

Tạo `src/test/java/example/servlettest/ServletAuthenticationFlowTest.java`. Toàn bộ file bên dưới là một **JUnit Jupiter + Spring Boot + MockMvc** test class, chạy ứng dụng `ServletAuthDemoApplication` đã khai báo ở trên và dùng dữ liệu lab.

~~~java
package example.servlettest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ServletAuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserIsRedirectedToLoginPage() throws Exception {
        mvc.perform(get("/private").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void formLoginAcceptsCorrectPasswordAndPersistsSession()
            throws Exception {

        MvcResult loginResult = mvc.perform(formLogin()
                .user("student")
                .password("student-lab-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("student"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                loginResult.getRequest().getSession(false);
        assertNotNull(session);

        // Đây là request khác, không có username/password.
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(content().string("private:student"));
    }

    @Test
    void formLoginRejectsWrongPassword() throws Exception {
        mvc.perform(formLogin()
                .user("student")
                .password("incorrect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void rawFormPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "student-lab-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void httpBasicAcceptsCorrectCredentialsPerRequest()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "student-lab-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(content().string("me:student"));
    }

    @Test
    void httpBasicRejectsIncorrectPassword() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "incorrect"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(unauthenticated());
    }

    @Test
    void authenticatedStudentCannotAccessAdminPage()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("student", "student-lab-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanAccessAdminPage() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-lab-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void logoutHelperBuildsPostWithValidCsrf()
            throws Exception {
        // logout() tự thêm CSRF, dù không có user đăng nhập.
        mvc.perform(logout())
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));
    }

    @Test
    void logoutInvalidatesActualLoggedInSession()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("student")
                .password("student-lab-pass"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);
        assertFalse(session.isInvalid());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("private:student"));

        // Ở đây dùng post(...).session(...).with(csrf())
        // để gắn CHÍNH session đã được login vào logout.
        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"))
            .andExpect(unauthenticated());

        // Xác minh server đã vô hiệu hóa đúng session đó.
        assertTrue(session.isInvalid());

        // Không tái sử dụng một MockHttpSession đã invalidated trong
        // RequestBuilder; với browser cần phát request mới không có
        // cookie/phiên hợp lệ rồi kiểm tra bị yêu cầu login.
        mvc.perform(get("/private").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfDoesNotInvalidateSession()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("student")
                .password("student-lab-pass"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk());
    }
}
~~~

Đây là một ví dụ **tích hợp Security Filter Chain** (không phải chỉ unit test controller), với **12 phương thức `@Test`** có các kịch bản chính: anonymous, form login thành công/thất bại, CSRF, Basic thành công/thất bại, phân quyền 403, logout và session invalidation.

Chạy bằng Gradle (khi project đã có Gradle wrapper):

~~~bash
./gradlew test --tests example.servlettest.ServletAuthenticationFlowTest
~~~

Nếu đúng các dependencies và cấu hình trên, kỳ vọng **12 tests pass**. Tên logger, timestamp hay output Gradle có thể khác tùy dự án; không khẳng định build thành công khi chưa thực sự chạy trong một project tương ứng. Bộ test không đòi Internet, database, email, JWT issuer hay browser thật.

## 6. formLogin(): hiểu chính xác helper này làm gì

`formLogin()` của `SecurityMockMvcRequestBuilders`:

- Sinh `POST /login` mặc định.
- Đặt param `username` và `password` (mặc định của helper là `user/password` nếu không đổi).
- Thêm CSRF token hợp lệ để request không bị `CsrfFilter` từ chối ở bước đầu.
- Cho phép tùy chỉnh login processing URL và tên tham số.

Ví dụ mặc định:

~~~java
mvc.perform(formLogin()
        .user("student")
        .password("student-lab-pass"))
    .andExpect(authenticated().withUsername("student"));
~~~

Lệnh trên **khác**:

~~~java
mvc.perform(get("/private")
        .with(user("student").roles("USER")))
    .andExpect(status().isOk());
~~~

Đoạn thứ hai cần import `SecurityMockMvcRequestPostProcessors.user`. Nó tạo sẵn authenticated test principal và **không** xác minh password, không tạo `POST /login`, không nhất thiết chạy handler/session strategy như login thật. Chỉ dùng để test authorization khi không cần kiểm thuật toán xác thực.

### 6.1. Đổi login URL và tên tham số

Nếu ứng dụng cấu hình:

~~~java
http.formLogin(form -> form
        .loginProcessingUrl("/session/login")
        .usernameParameter("loginName")
        .passwordParameter("secretValue")
        .defaultSuccessUrl("/private", true)
        .permitAll());
~~~

Thì test cũng phải đổi đúng:

~~~java
mvc.perform(formLogin("/session/login")
        .user("loginName", "student")
        .password("secretValue", "student-lab-pass"))
    .andExpect(authenticated().withUsername("student"));
~~~

Đây là **hai snippets ở các vị trí khác nhau**: đoạn config nằm trong bean `SecurityFilterChain`, đoạn test nằm trong test method có `MockMvc mvc`. **Không ghép vào file demo mục 4 mà quên sửa các test mặc định**, vì mỗi URL/parameter khác nhau sẽ làm filter không nhận đúng.

### 6.2. CSRF và các kết quả gây nhầm

| Request test | CSRF | Kết quả điển hình |
| --- | --- | --- |
| `mvc.perform(formLogin())` | **Được helper thêm** | Đi tiếp vào authentication; đúng/sai tùy credentials |
| `mvc.perform(post("/login"))` | **Thiếu** | 403 do CSRF trước khi kiểm password |
| `mvc.perform(post("/login").with(csrf()))` | Hợp lệ | Đi tiếp vào username/password filter |
| `mvc.perform(post("/login").with(csrf().useInvalidToken()))` | Không hợp lệ | 403 |
| `GET /login` | Không cần token để *đọc trang*, nhưng form phải gửi CSRF ở POST | Trả trang login/redirect tùy config |

Thấy HTTP 403 khi gửi POST login không có CSRF **không có nghĩa** password đã bị xác minh là sai. Thấy redirect `/login?error` với CSRF hợp lệ thường là login failure handler; phải phân biệt hai nhóm trong test.

### 6.3. Chú ý cú pháp của builder

`SecurityMockMvcRequestBuilders.FormLoginRequestBuilder` thực thi `RequestBuilder` và có `.user(...)`, `.password(...)`, `.acceptMediaType(...)`; nó **không** phải `MockHttpServletRequestBuilder` có đầy đủ `.session(...)` và `.with(...)` như `get(...)`/`post(...)`.

Nếu muốn điều khiển session hoặc thêm `RequestPostProcessor` tùy biến, có thể dùng `post("/login").session(session).with(csrf()).param(...)`, nhưng nhớ rằng request này đi vào cùng filter chain và chịu các chính sách session/CSRF thực. **Đừng tự gọi `formLogin().session(...)` nếu API builder của version bạn dùng không có phương thức đó.**

## 7. httpBasic(): Basic Auth là một header cho từng request

Helper đúng là:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("student", "student-lab-pass")))
    .andExpect(status().isOk())
    .andExpect(content().string("me:student"));
~~~

Nó tạo header `Authorization: Basic ...` tương ứng với cặp username/password đã nhập và Base64-encode theo format Basic Auth. Mục đích là **đỡ viết tay header và giảm lỗi format**, không phải tự mock authentication.

### 7.1. Kỳ vọng 401, 403, 200

| Tình huống | Kết quả thông thường | Vì sao |
| --- | --- | --- |
| Basic username/password đúng, endpoint yêu cầu authenticated | **200** | Provider xác thực, controller chạy |
| Basic password sai | **401**; thường có `WWW-Authenticate: Basic ...` | Authentication failure, Basic entry point |
| Basic đúng nhưng thiếu role cho endpoint | **403** | Authentication thành công nhưng authorization từ chối |
| Không gửi Basic header | Có thể **401 hoặc redirect /login** | Phụ thuộc entry point của chain, Accept header và form login cũng đang bật |
| Gửi header Basic nhưng chưa cấu hình `httpBasic` ở chain được chọn | Không đảm bảo Basic được xử lý | Header không tự bật filter |
| Basic đúng, request sau không có header | Không tự có session mới | Default Basic thường xác thực mỗi request |

### 7.2. Vì sao Basic không thể thay formLogin?

- `formLogin()` kiểm tra luồng POST, CSRF, form success/failure handler, session fixation và lưu SecurityContext.
- `httpBasic(...)` kiểm tra HTTP header, trạng thái 401/challenge và authorization cho request đó.
- Một endpoint có thể bật **cả hai**, nhưng client negotiation/entry point được chọn theo request.
- Logout của form session không ngăn một Basic header hợp lệ **tiếp tục xác thực ở request sau**; để thu hồi Basic cần đổi credential, khóa tài khoản hoặc thay policy xác thực.
- Không log hoặc test snapshot nguyên Basic header: Base64 username/password có thể bị giải mã ngay.

### 7.3. Thử với curl chỉ trên localhost

Với app demo chạy local:

~~~bash
curl -i -u student:student-lab-pass \
  -H "Accept: application/json" \
  http://localhost:8080/api/me
~~~

Kỳ vọng body:

~~~text
me:student
~~~

Tham số `-u` khiến curl gửi Basic credentials. Khi thao tác với credentials thật, tránh đặt trực tiếp vào shell history/process arguments; dùng phương pháp quản lý secrets phù hợp. Không gửi Basic Auth qua HTTP công khai, chỉ dùng HTTPS trên môi trường thực.

### 7.4. User mocking không phải chứng minh Basic hoạt động

Hai test sau kiểm khác nhau:

~~~java
// Test Authorization của controller; không verify Basic password.
mvc.perform(get("/api/me").with(user("student").roles("USER")))
    .andExpect(status().isOk());

// Test thực sự nhập Basic header vào Security filter.
mvc.perform(get("/api/me")
        .with(httpBasic("student", "student-lab-pass")))
    .andExpect(status().isOk());
~~~

Có thể test mock user pass ngay cả khi `httpBasic` chưa được bật. Vì vậy khi yêu cầu chứng minh Basic Authentication hoạt động, hãy test bằng `httpBasic(...)` và có **negative case** cho password sai.

## 8. logout(): helper, session, CSRF và ý nghĩa của kết quả

Spring Security mặc định bật `LogoutFilter` trong servlet security chain. Với CSRF bật:

- `GET /logout` thường hiển thị trang xác nhận, **không** tự thực hiện hành động logout.
- `POST /logout` với token CSRF hợp lệ là lệnh logout.
- `logout()` helper tạo đúng request cơ bản.
- Logout mặc định invalidates `HttpSession`, clears `SecurityContext`, xử lý remember-me/CSRF liên quan và redirect `/login?logout`.

### 8.1. Test logout helper

~~~java
mvc.perform(logout())
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/login?logout"));
~~~

**Giới hạn:** nếu gọi như trên khi chưa gắn session đã đăng nhập, test chủ yếu chứng minh **endpoint nhận request và tạo redirect**. Nó không khẳng định session của một user trước đó đã bị hủy. Cần ca tích hợp như `logoutInvalidatesActualLoggedInSession()` trong file test ở mục 5.

### 8.2. Test logout của đúng session

Quy trình:

1. `formLogin()` password đúng.
2. Lấy `MockHttpSession` từ `MvcResult`.
3. Gọi một endpoint protected với `.session(session)`, bảo đảm thực sự dùng được.
4. `post("/logout").session(session).with(csrf())`.
5. Assert redirect và `session.isInvalid() == true`.
6. Gọi endpoint protected bằng một **request mới không còn phiên hợp lệ**; nó phải yêu cầu authentication.

Mã trọng tâm trong method test:

~~~java
MockHttpSession session = (MockHttpSession)
        loginResult.getRequest().getSession(false);

mvc.perform(post("/logout").session(session).with(csrf()))
    .andExpect(redirectedUrl("/login?logout"));

assertTrue(session.isInvalid());
~~~

Lưu ý `loginResult` được lấy từ một request form login thành công trước đó; đoạn trên **không phải test method độc lập**. Với browser thật, cookie invalidation/expiration có hành vi riêng theo container. Với `MockMvc`, object `MockHttpSession` đã invalidated không nên dùng lại làm một session hợp lệ.

### 8.3. CSRF với logout

~~~java
mvc.perform(post("/logout"))
    .andExpect(status().isForbidden());

mvc.perform(post("/logout").with(csrf()))
    .andExpect(redirectedUrl("/login?logout"));
~~~

Hai request trên đều chưa gắn session authenticated, dùng để kiểm việc router/filter xử lý CSRF và endpoint logout. Khi cần test session, **gắn đúng session** và kiểm invalidation; tránh suy từ redirect đơn lẻ.

**Không tắt CSRF toàn ứng dụng** chỉ để cho POST logout chạy. CSRF protection chống lại việc một trang bên ngoài ép browser nạn nhân logout hoặc thực hiện state-changing requests khác.

### 8.4. Custom URL

Khi ứng dụng dùng:

~~~java
http.logout(logout -> logout
        .logoutUrl("/session/logout")
        .logoutSuccessUrl("/goodbye"));
~~~

Test helper có thể dùng:

~~~java
mvc.perform(logout("/session/logout"))
    .andExpect(redirectedUrl("/goodbye"));
~~~

Điều kiện: `/goodbye` phải được cho phép truy cập cho anonymous nếu browser được redirect sau logout; có thể dùng `logout.permitAll()` hoặc rule phù hợp. Hai snippet là **cấu hình thay thế** cho demo mặc định, không được ghép vào mà không cập nhật kỳ vọng các test.

### 8.5. Logout session khác thu hồi các loại token

| Credential/trạng thái | Sau `LogoutFilter` mặc định |
| --- | --- |
| HTTP session hiện tại | Thường invalidated, Spring Security context được xóa |
| CSRF token gắn với session | Có thể bị xóa/đổi theo logout handlers |
| Remember-me cookie | Cleanup nếu tính năng này được bật và handler được cấu hình |
| **HTTP Basic password** | Không bị đổi hoặc thu hồi bởi logout |
| **JWT Bearer access token** | Không bị vô hiệu hóa chỉ bằng logout servlet session |
| Refresh token/OAuth2 grant bên IdP | Có thể cần revocation/logout riêng |
| Session ở hệ khác (SSO) | Có thể cần federated/OIDC logout riêng |

Khi test “logout hoàn chỉnh”, phải định nghĩa **đang kiểm logout cục bộ hay toàn hệ thống**. Một 302 `/login?logout` không chứng minh JWT bên ngoài đã bị thu hồi.

## 9. Vì sao MockMvc test có thể cho kết quả sai?

### 9.1. Không chạy Security filters

Với `MockMvcBuilders.standaloneSetup(controller)` mặc định, bạn có thể không có `FilterChainProxy`. Kết quả: controller được gọi dù không authenticated, hoặc `formLogin()` gửi POST nhưng không có filter xử lý như project thật.

Khi dựng `MockMvc` thủ công cho WebApplicationContext:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

Đoạn này cần imports `MockMvcBuilders` và static import `springSecurity` từ `SecurityMockMvcConfigurers`, đặt trong setup method có `WebApplicationContext context`. Trong ví dụ `@SpringBootTest + @AutoConfigureMockMvc`, Boot cấu hình `MockMvc`, nên không cần viết setup thủ công.

### 9.2. Dùng @WithMockUser để kiểm password

~~~java
@Test
@WithMockUser(username = "student", roles = "USER")
void mockUserCanSeeProtectedPage() throws Exception {
    mvc.perform(get("/private"))
        .andExpect(status().isOk());
}
~~~

Test có giá trị khi kiểm authorization; **không chứng minh password thật được validate**. Có thể pass dù `PasswordEncoder` sai hoặc `UserDetailsService` trả lỗi. Muốn test login hãy tạo POST đúng bằng `formLogin()`; muốn test Basic hãy dùng `httpBasic(...)`.

### 9.3. Nhầm HTTP status và authentication result

Một test chỉ `.andExpect(status().isOk())` không đủ. Endpoint `/public` luôn 200 và không chứng minh authentication.

Gợi ý dùng cả:

~~~java
mvc.perform(formLogin().user("student").password("student-lab-pass"))
    .andExpect(authenticated().withUsername("student"))
    .andExpect(redirectedUrl("/private"));
~~~

Với Basic cũng kiểm body/principal hoặc role. Với logout phải kiểm **invalidation/session**. Cần biết rằng controller response 403 sau Basic có thể là **authorization failure** chứ không phải credential failure.

### 9.4. Dùng cookie của session không đúng

Một lỗi phổ biến là lấy `MockHttpSession` từ một request **khác** hoặc tạo mới bằng `new MockHttpSession()` trước khi follow-up, rồi kết luận session không được lưu. Hãy lấy session từ chính `MvcResult` của POST login, sau đó truyền vào request thứ hai bằng `.session(session)`.

Ngược lại, **không giữ cùng session trong mọi test** khi muốn các test độc lập. Các ví dụ trên tạo session mới cho từng method, không lưu global static session, tránh ảnh hưởng lẫn nhau.

### 9.5. Nhầm CSRF lỗi 403 với authorization lỗi 403

Có ít nhất hai nguyên nhân 403:

- `CsrfFilter` từ chối `POST /login` hoặc `POST /logout` không có CSRF.
- `AuthorizationFilter` từ chối user đã authenticated nhưng thiếu `ROLE_ADMIN`.

Nếu test ghi đơn giản “được 403 nên security tốt” thì không chứng minh **rule tương ứng** có đúng không. Cần gửi CSRF hợp lệ trong test authorization của unsafe method và phân biệt response path/event.

### 9.6. HTTP Basic và Accept header

Khi bật cả `formLogin` lẫn `httpBasic`, Spring Security chọn authentication entry point phù hợp với loại request và cấu hình. Với request thiếu credentials, HTML browser thường redirect login, còn API nhận JSON/Basic có thể được 401 challenge. Đây là lý do test phải mô tả **Accept header** và expected result theo chain. Đừng khẳng định mọi anonymous GET luôn 401 hoặc mọi API GET luôn redirect.

### 9.7. Password hash và mock user store

Trong ví dụ `InMemoryUserDetailsManager`, mật khẩu được encode bằng BCrypt trước khi lưu. Nếu test dùng raw password khác, `DaoAuthenticationProvider` phải từ chối. Nếu bạn cố dùng `{noop}` để “test tiện hơn”, test có thể không giống production, bỏ sót lỗi tương tác `PasswordEncoder` và tạo thói quen nguy hiểm khi copy cấu hình.

Dùng dữ liệu lab cố định trong source test là có thể chấp nhận **nếu** đó không phải credential thật và không được dùng lại ở môi trường khác. Không log cả password thất bại hay Basic header trong CI.

## 10. Test phân quyền, session fixation và concurrency nâng cao

### 10.1. Đăng nhập không có nghĩa có mọi quyền

Form login và Basic chỉ xác minh danh tính. User `student` có `ROLE_USER` vẫn bị từ chối ở `/admin`. Bộ test nên có:

- Credential đúng + quyền đúng → 200.
- Credential đúng + thiếu quyền → 403.
- Credential sai → thất bại authentication.
- Không có credential → login redirect/401 tùy entry point.

Như vậy phân biệt được **authentication** và **authorization** một cách chắc chắn.

### 10.2. Session fixation

Spring Security mặc định bảo vệ session fixation bằng cách đổi session ID hoặc tạo session mới theo servlet container/version. Có thể test:

1. Tạo `MockHttpSession` trước login, lưu một thuộc tính bình thường.
2. `post("/login").session(preSession).with(csrf())` và param username/password.
3. Xem `MockHttpSession#getId()` trước/sau (có thể cùng Java object nhưng ID được đổi).
4. Xác minh security context đã được lưu đúng và không tái sử dụng ID trước login theo policy.

**Không dùng `formLogin().session(...)` một cách mù quáng**; builder `formLogin` không có API `session(MockHttpSession)` như `MockHttpServletRequestBuilder`. Để test session fixation, dùng raw `post` + `with(csrf())`. Trường hợp này cần đối chiếu `changeSessionId` của mock container và strategy cụ thể.

### 10.3. Concurrent session control

Nếu cấu hình `maximumSessions(1)`, cần kiểm:

- Login lần đầu thành công; session A truy cập được.
- Login lần hai của cùng user từ session khác; nếu policy cho phép đăng nhập mới thì session A trở nên không hợp lệ, còn B hợp lệ.
- Nếu `maxSessionsPreventsLogin(true)` thì login lần hai bị chặn, session A vẫn hoạt động.
- Các event/response và cookie phải khớp chính sách.

Với session registry hoặc Spring Session phân tán, test integration cần môi trường/bean thật. Không kết luận tính đúng đắn của concurrent sessions chỉ từ một test MockMvc không có registry.

### 10.4. LogoutSuccessEvent và audit

Spring Security có thể phát `LogoutSuccessEvent` trong quá trình logout. Nếu ứng dụng nghe event để audit, không xem event là bằng chứng **mọi hệ thống bên ngoài** đã hết phiên. Chỉ log event code, actor/ref nội bộ đã được duyệt và thời gian; không ghi password, Basic header, session ID, CSRF token hoặc raw request.

Không thực hiện các side effects không idempotent chỉ dựa vào một event listener không bền vững. Nếu logout toàn SSO, cần flow federated logout riêng theo chuẩn của IdP.

## 11. Checklist nghiệm thu và ma trận lỗi

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| M01 | `GET /public` anonymous | 200 |
| M02 | `GET /private` anonymous, Accept HTML | Redirect login |
| M03 | `formLogin` đúng username/password + CSRF | Authentication success, redirect `/private` |
| M04 | Sau form login, GET protected bằng cùng session | 200 với principal đúng |
| M05 | `formLogin` sai password | Redirect `/login?error`, unauthenticated |
| M06 | Raw POST `/login` thiếu CSRF | 403 do CSRF, không coi là password failure |
| M07 | Raw POST `/login` có invalid CSRF | 403 |
| M08 | Basic đúng password, endpoint authenticated | 200 với principal đúng |
| M09 | Basic sai password | 401, không authenticated |
| M10 | Basic đúng nhưng thiếu role | 403 authorization |
| M11 | Basic admin đủ role | 200 `/admin` |
| M12 | Basic request tiếp theo không có Authorization header | Không tự coi đã đăng nhập form session |
| M13 | `logout()` helper mặc định | POST với CSRF, redirect `/login?logout` |
| M14 | Logout đúng session đã login | Session invalidated, context xóa |
| M15 | POST logout không có CSRF | 403, session cũ vẫn hợp lệ |
| M16 | GET logout với CSRF bật | Không tự logout; thường hiện confirmation |
| M17 | Custom URL login/logout | Builders dùng đúng URL và params |
| M18 | `@WithMockUser` pass nhưng real form login fail | Phát hiện test giả không kiểm password |
| M19 | MockMvc không có Security filters | Bị phát hiện, không coi kết quả là auth test hợp lệ |
| M20 | Logout local rồi gửi Basic credentials hợp lệ | Request mới vẫn có thể xác thực |
| M21 | Session hết hạn hoặc bị logout | Không truy cập protected bằng phiên cũ |
| M22 | User bị disabled/locked | Login phải bị từ chối theo account policy |
| M23 | 401/403/302 dưới nhiều Accept headers | Đúng entry point/security chain |
| M24 | Browser thật nhận/sử dụng cookie ở production | Cần E2E, không chỉ MockMvc |
| M25 | Có nhiều `SecurityFilterChain` | Test đúng endpoint/chain được chọn |

### Troubleshooting

| Triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| `formLogin()` nhận 404 | Filter chain không chạy, sai `loginProcessingUrl` | Bảo đảm Boot MockMvc có filters, URL đúng |
| `formLogin()` nhận 403 | CSRF config, builder không được dùng hoặc filter chain khác | Kiểm CSRF và filter chain |
| `formLogin()` login sai dù password đúng | PasswordEncoder mismatch hoặc user store khác | Test `UserDetailsService`/`PasswordEncoder.matches` |
| Form login đúng nhưng trang đích vẫn về login | Không giữ session, cookie sai, context không lưu | Kiểm `SecurityContextRepository` và session |
| Basic test 200 dù password sai | Dùng `with(user(...))` nên bypass Basic | Bỏ mock principal khi test Basic |
| Basic test 302 thay vì 401 | Request không có Basic header hoặc entry point phù hợp HTML | Kiểm header, Accept và config `httpBasic` |
| Basic test 401 dù user đúng | Password/hash mismatch hoặc filter chain sai | Kiểm provider, key, password encoder |
| Logout test 302 nhưng session không hết | Test logout khác session hoặc custom handler bỏ cleanup | Gắn đúng session, kiểm `SecurityContextLogoutHandler` |
| POST logout bị 403 | Thiếu CSRF | Dùng `logout()` hoặc `post(...).with(csrf())` |
| GET logout bị 200 nhưng vẫn authenticated | GET hiển thị confirm, chưa thực hiện POST | Submit POST logout có CSRF |
| Sau logout vẫn vào bằng Basic | Client lại gửi Basic credentials | Phân biệt logout session với thu hồi password |
| 403 ở `/admin` khiến test gọi là “login fail” | User đã authenticated nhưng thiếu role | Tách negative authorization khỏi login |
| Test độc lập pass nhưng chạy cùng suite fail | Dùng static/global session, cấu hình test context bị bẩn | Cô lập session và fixtures giữa tests |
| `MockMvc` trả code đúng nhưng browser thật lỗi | Cookie/HTTPS/proxy/SameSite/distributed session | Dùng E2E tests |

## 12. Câu hỏi tự kiểm tra

1. `formLogin()` có khác `with(user("student"))` không? Bước xác minh mật khẩu chạy ở cách nào?
2. Vì sao `formLogin()` tự thêm CSRF, còn raw `post("/login")` có thể 403?
3. Khi form login thành công, tại sao kỳ vọng 302 redirect hơn là luôn 200?
4. HTTP Basic header được tạo bởi helper nào? Helper này thuộc class nào?
5. Tại sao `httpBasic("student","pass")` không có nghĩa người dùng đã có phiên?
6. Nếu user đúng password nhưng không có `ROLE_ADMIN`, endpoint `/admin` nên có status nào?
7. Vì sao `logout()` redirect 302 vẫn chưa đủ để chứng minh session thực sự bị hủy?
8. Khi muốn logout session có sẵn, vì sao dùng `post("/logout").session(session).with(csrf())`?
9. Với CSRF bật, GET `/logout` có tự logout không?
10. Sau logout form session, tại sao Basic Auth với cùng username/password vẫn có thể gọi API?
11. Nếu dùng `@WebMvcTest` hoặc `standaloneSetup`, cần bảo đảm điều gì để kết luận test có chạy Security?
12. `SecurityMockMvcResultMatchers.authenticated()` và `MockMvcResultMatchers.status()` kiểm tra các khía cạnh khác nhau thế nào?
13. Kịch bản kiểm thử nào chứng minh SecurityContext thực sự được lưu và dùng qua request?
14. Nếu app đổi `usernameParameter` thành `loginName`, cần đổi test gì?
15. Test này đã chứng minh cookie thực tế ở browser và reverse proxy an toàn chưa?

**Đáp án ngắn:** (1) khác, `formLogin` đi qua auth provider; (2) CSRF cần cho unsafe POST; (3) form success handler thường redirect; (4) `SecurityMockMvcRequestPostProcessors.httpBasic`; (5) Basic gắn header mỗi request; (6) 403; (7) chưa gắn session hoặc chỉ test redirect; (8) builder raw POST hỗ trợ `.session` và `.with(csrf())`; (9) thường chỉ hiện confirm page; (10) Basic xác thực request mới; (11) có `FilterChainProxy`/`springSecurity()`; (12) authentication state so với HTTP status; (13) gửi protected GET bằng cùng `MockHttpSession`; (14) đổi tên param trong `formLogin(...).user("loginName", "...")`; (15) chưa, cần E2E.

## 13. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Testing Form Based Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Testing Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/logout.html)
- [Spring Security 6.5 — SecurityMockMvcRequestBuilders API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestBuilders.html)
- [Spring Security 6.5 — SecurityMockMvcRequestPostProcessors API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Security 6.5 — SecurityMockMvcResultMatchers API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/response/SecurityMockMvcResultMatchers.html)
- [Spring Security 6.5 — Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
