# Đăng nhập bằng biểu mẫu và luồng chuyển hướng của trình duyệt trong Spring Security

Khi một người chưa đăng nhập mở trang `/dashboard`, Spring Security thường **chuyển trình duyệt đến trang đăng nhập**, nhận thông tin từ biểu mẫu, xác thực danh tính rồi chuyển lại trang ban đầu. Tuy nhiên, đó không phải một request duy nhất: trình duyệt và server thực hiện nhiều lượt HTTP riêng biệt, mỗi lượt có phương thức, URL, cookie và nhiệm vụ khác nhau.

Bài này thuộc **Đăng nhập và đăng xuất** của **Spring Security - fundamentals**. Mục tiêu là hiểu đúng **GET login page, POST login processing, HTTP redirect, saved request, session, CSRF, xử lý thành công/thất bại và logout**; biết triển khai, kiểm thử và gỡ lỗi luồng form login. Ví dụ chính sử dụng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x trên Spring MVC/Servlet**. Với ứng dụng WebFlux, lớp cấu hình và cách quản lý ngữ cảnh khác; không sao chép nguyên mẫu `HttpSecurity` sang `ServerHttpSecurity`.

## 1. Mô hình tư duy: những HTTP request nào thực sự xảy ra?

Giả sử người dùng gõ `http://localhost:8080/dashboard` khi chưa đăng nhập:

~~~text
Trình duyệt                                   Ứng dụng Spring Security
    |                                                   |
    |  GET /dashboard                                   |
    |-------------------------------------------------->|
    |                                                   | Chưa xác thực
    |  302 Location: /login                             | Có thể lưu request
    |<--------------------------------------------------|
    |                                                   |
    |  GET /login                                       |
    |-------------------------------------------------->|
    |  200 HTML chứa biểu mẫu                           |
    |<--------------------------------------------------|
    |                                                   |
    |  POST /login                                      |
    |  username=lan&password=...&_csrf=...              |
    |-------------------------------------------------->|
    |                                                   | Kiểm tra CSRF,
    |                                                   | xác thực mật khẩu,
    |                                                   | lưu SecurityContext
    |  302 Location: /dashboard                         |
    |<--------------------------------------------------|
    |                                                   |
    |  GET /dashboard + cookie phiên                    |
    |-------------------------------------------------->|
    |  200 Nội dung dashboard                           |
    |<--------------------------------------------------|
~~~

Ở đây **redirect (chuyển hướng)** nghĩa là server trả mã HTTP 3xx kèm header `Location`, sau đó **trình duyệt tạo request mới**. Redirect không tự gọi một Controller trong cùng request như một lệnh gọi Java nội bộ.

Ví dụ này mô tả luồng Servlet với form login mặc định. URL, status, việc lưu URL cũ, thành công và thời gian sống của phiên có thể được tùy chỉnh. Đừng coi mọi redirect 302 là đăng nhập thành công: **thất bại đăng nhập cũng thường trả 302**, nhưng với đích khác.

Ba pha cần nhớ:

1. **Trước xác thực:** một request cần quyền được yêu cầu, Spring Security từ chối truy cập khi người dùng chưa đăng nhập và khởi động luồng login.
2. **Thực thi xác thực:** form gửi POST có username/password và CSRF; bộ lọc xác thực giao tiếp với `AuthenticationManager`.
3. **Sau xác thực:** khi thành công, ngữ cảnh xác thực được lưu, chiến lược thành công chọn URL đích và trình duyệt gửi GET tiếp theo với cookie phiên.

## 2. GET /login khác POST /login

Spring Security Servlet với `formLogin(Customizer.withDefaults())` có quy ước:

| HTTP request | Vai trò | Thành phần thường xử lý | Kết quả phổ biến |
| --- | --- | --- | --- |
| `GET /login` | Hiện biểu mẫu HTML | Trang login Spring Security tự sinh khi chưa cấu hình trang khác | 200 |
| `POST /login` | Kiểm tra thông tin đăng nhập | `UsernamePasswordAuthenticationFilter` | 302 tới trang đích hoặc login lỗi |
| `GET /login?error` | Hiện thông báo đăng nhập sai | Trang login | 200 |
| `GET /login?logout` | Hiện thông báo đăng xuất | Trang login | 200 |
| `GET /dashboard` khi anonymous | Yêu cầu tài nguyên cần login | Authorization + entry point | Thường 302 tới `/login` |
| `GET /dashboard` sau login | Xem nội dung được bảo vệ | Filter chain cho qua, rồi tới Controller | Thường 200 |

**Không cần tự khai báo `@PostMapping("/login")`** nếu ứng dụng sử dụng `UsernamePasswordAuthenticationFilter` mặc định. Filter xử lý URL POST login của nó trước khi request được chuyển tới Controller.

Trong form mặc định, trường người dùng tên `username`, mật khẩu tên `password`. Nếu tự viết form với `name="email"` nhưng không đặt `usernameParameter("email")` thì filter không tự đọc tên trường mới.

Khi gọi `.loginPage("/signin")`, Spring Security **không còn tự sinh HTML trang signin tùy chỉnh**. Ứng dụng phải cung cấp route GET và view/HTML tương ứng; URL POST để xác thực có thể giữ mặc định hoặc đổi qua `loginProcessingUrl(...)`.

## 3. Ai đưa người chưa xác thực đến trang login?

Trong một chain Servlet, ý nghĩa của các thành phần quan trọng:

- **`AuthorizationFilter`**: áp dụng quy tắc phân quyền như `.requestMatchers("/dashboard").authenticated()`.
- **`ExceptionTranslationFilter`**: chuyển lỗi bảo mật thành một hướng xử lý phù hợp. Với người chưa xác thực, nó có thể khởi động quá trình đăng nhập; với người đã xác thực nhưng thiếu quyền, có thể xử lý từ chối truy cập.
- **`LoginUrlAuthenticationEntryPoint`**: trong form login, thường tạo redirect tới đường dẫn trang đăng nhập.
- **`RequestCache`**: có thể giữ URL yêu cầu trước khi redirect để người dùng quay lại sau login.
- **`UsernamePasswordAuthenticationFilter`**: nhận POST ở URL xử lý login và gọi cơ chế xác thực.
- **`AuthenticationManager`/`AuthenticationProvider`**: kiểm tra danh tính và mật khẩu với nguồn dữ liệu người dùng.
- **`AuthenticationSuccessHandler`**: chọn phản hồi/đích sau khi xác thực thành công.
- **`AuthenticationFailureHandler`**: xử lý lần xác thực thất bại, thường redirect về trang login với trạng thái lỗi.
- **`SecurityContextRepository`**: hỗ trợ lưu và đọc thông tin bảo mật giữa các request.

Dòng thời gian khái niệm:

~~~text
GET /dashboard
    |
    +--> Chưa được xác thực
    +--> AuthorizationFilter từ chối
    +--> ExceptionTranslationFilter / AuthenticationEntryPoint
    +--> (có thể) lưu SavedRequest
    +--> 302 Location: /login

GET /login
    +--> Form HTML, trong đó có CSRF token

POST /login
    +--> CsrfFilter kiểm tra nếu CSRF áp dụng
    +--> UsernamePasswordAuthenticationFilter
    +--> AuthenticationManager
           +--> thành công -> lưu SecurityContext
           |                  -> success handler
           |                  -> 302 Location: saved URL hoặc default URL
           |
           +--> thất bại   -> failure handler
                              -> 302 Location: /login?error

GET saved URL
    +--> Cookie phiên, SecurityContext được khôi phục
    +--> Kiểm tra phân quyền lại
    +--> Controller trả nội dung
~~~

Thứ tự chi tiết và các lớp có mặt phụ thuộc cấu hình chain. Bài này dùng chúng để giải thích **trách nhiệm**, không khẳng định sơ đồ là dump thứ tự mọi filter của mọi phiên bản.

### 3.1. Chưa đăng nhập khác sai mật khẩu

Một người lần đầu truy cập `/dashboard` chưa gửi mật khẩu. Spring Security chuyển về login vì **chưa có danh tính hợp lệ**, không phải vì password sai. Chỉ khi submit POST login mới có một nỗ lực xác thực có thể đúng hoặc sai.

Ngược lại, một người đã đăng nhập nhưng không có `ROLE_ADMIN` bị chặn ở `/admin` theo `hasRole("ADMIN")`. Với cơ chế Servlet mặc định, kết quả thường là 403, vì **đã biết danh tính nhưng thiếu quyền**. Cách chuyển đổi thành 401/403/redirect phụ thuộc entry point và access denied handler.

### 3.2. Redirect không chứng minh trang đích được phép truy cập

Sau login, browser có thể nhận `Location: /dashboard`; request GET sau đó **vẫn phải đi qua security filter chain**. Nếu tài khoản thiếu quyền truy cập trang đã lưu, server vẫn có thể từ chối. Authentication success không tự cấp mọi quyền của ứng dụng.

## 4. Saved request: quay về trang người dùng định mở

Tình huống:

~~~text
GET /orders/42                  chưa đăng nhập
  → lưu request nếu phù hợp
  → 302 /login
POST /login                     đúng username/password
  → 302 /orders/42
GET /orders/42                  có session xác thực
  → tài nguyên được xem nếu có quyền
~~~

`HttpSessionRequestCache` thường giữ `SavedRequest` trong session. Một bộ xử lý thành công như `SavedRequestAwareAuthenticationSuccessHandler` có thể ưu tiên URL này.

Những giới hạn cần hiểu:

- Việc lưu request phụ thuộc matcher, chính sách session, RequestCache và cấu hình phiên bản.
- Với nhiều tab hoặc khi saved request đã bị thay thế/không còn hợp lệ, URL được chọn có thể khác dự đoán.
- **Đừng trông chờ POST có body được tự động gửi lại sau login.** Hướng quay lại hợp lý nhất thường là một trang GET, nơi người dùng có thể tự xác nhận hành động ghi.
- Nếu không có saved request phù hợp, handler thường dùng URL mặc định.
- Một số cấu hình có thể yêu cầu URL mặc định được ưu tiên trong mọi trường hợp.

Ví dụ điều khiển URL mặc định:

~~~java
.formLogin(form -> form
    .defaultSuccessUrl("/home", false)
)
~~~

Ý nghĩa `false`: không cưỡng bức dùng URL mặc định nếu có saved request được ưu tiên. Với:

~~~java
.formLogin(form -> form
    .defaultSuccessUrl("/home", true)
)
~~~

ý nghĩa `true`: luôn điều hướng tới `/home` theo bộ xử lý này, thay vì ưu tiên saved request.

Nếu tự cho phép query string như `returnUrl` làm nơi redirect, phải giới hạn URL hợp lệ trong ứng dụng. **Không chuyển hướng trực tiếp tới đích bất kỳ do client nhập**, vì có thể tạo lỗ hổng open redirect.

## 5. Mật khẩu đi qua AuthenticationManager như thế nào?

Form mặc định gửi dữ liệu kiểu `application/x-www-form-urlencoded`:

~~~http
POST /login HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

username=lan&password=demo123&_csrf=VALID_CSRF_VALUE
~~~

Ở đây `VALID_CSRF_VALUE` chỉ là mô tả, không phải một token dùng được. CSRF token thật được server cấp trong ngữ cảnh phù hợp.

`UsernamePasswordAuthenticationFilter` đọc các tham số và tạo một đối tượng xác thực **chưa được tin cậy**, sau đó gọi `AuthenticationManager.authenticate(...)`. Với ứng dụng lưu người dùng ở database, `DaoAuthenticationProvider` thường phối hợp `UserDetailsService` và `PasswordEncoder`.

~~~text
username/password từ form
           |
           v
UsernamePasswordAuthenticationToken chưa xác thực
           |
           v
AuthenticationManager
           |
           v
AuthenticationProvider phù hợp
     - tải thông tin người dùng
     - so khớp mật khẩu bằng PasswordEncoder
           |
           +--> đúng: Authentication đã xác thực
           |
           +--> sai: AuthenticationException
~~~

Không so sánh chuỗi mật khẩu thô bằng `equals` rồi lưu database plaintext. Trong sản phẩm, dùng bộ mã hóa mật khẩu phù hợp (BCrypt/Argon2 tùy hệ thống) và quy trình thay đổi/khôi phục mật khẩu an toàn.

## 6. Ứng dụng Spring Boot mẫu: trang login mặc định

Ta xây ứng dụng có `/` và `/public` công khai, `/dashboard` yêu cầu đăng nhập, `/admin` yêu cầu role ADMIN, một tài khoản `lan` chỉ có USER. Ứng dụng dùng **Java 17+**, Spring Boot **3.3.x** và Spring Security **6.3.x**. Đây là ví dụ học tập với tài khoản in-memory.

### 6.1. Dependency trong build.gradle

Với dự án Spring Boot đã cấu hình plugin và version:

~~~groovy
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

Đây là phần **phụ thuộc để ghép vào build.gradle hiện có**, không phải toàn bộ build độc lập. Ví dụ không cần Thymeleaf khi dùng trang đăng nhập tự sinh.

### 6.2. FormLoginDemoApplication.java

Tệp `src/main/java/example/formlogin/FormLoginDemoApplication.java`:

~~~java
package example.formlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormLoginDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormLoginDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

Tệp `src/main/java/example/formlogin/SecurityConfig.java`:

~~~java
package example.formlogin;

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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .requestMatchers("/dashboard").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(lan);
    }
}
~~~

Cấu hình nêu trên:

- `permitAll()` cho phép khách xem URL công khai.
- `authenticated()` yêu cầu có danh tính hợp lệ tại `/dashboard`.
- `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo quy ước mặc định, nên tài khoản `lan` không vào được `/admin`.
- `anyRequest().denyAll()` từ chối các URL không khai báo.
- `formLogin(Customizer.withDefaults())` bật trang login mặc định và POST processing; `logout(...)` bật cơ chế logout.
- Tài khoản thử nghiệm có mật khẩu được BCrypt mã hóa lúc khởi động. Không dùng tài khoản demo trong sản phẩm.
- CSRF giữ nguyên cấu hình bật mặc định. Vì vậy request POST login/logout phải có CSRF token hợp lệ.
- Spring Security tạo trang `GET /login` trong cấu hình mặc định; **không cần tạo Controller cho GET/POST login**.

### 6.4. PagesController.java

Tệp `src/main/java/example/formlogin/PagesController.java`:

~~~java
package example.formlogin;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/")
    public String index() {
        return "Home (public)";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "Public page";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "Dashboard (authenticated)";
    }

    @GetMapping("/admin")
    public String admin() {
        return "Admin area";
    }
}
~~~

Controller trả văn bản cho dễ quan sát. Khi khởi động ứng dụng, truy cập `http://localhost:8080/dashboard` trong trình duyệt chưa có session: dự kiến nhận redirect tới login; đăng nhập bằng `lan/demo123` sẽ điều hướng trở lại dashboard; `/admin` vẫn bị chặn vì thiếu ROLE_ADMIN.

Lệnh chạy từ dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Đây là **kịch bản dự kiến**, không phải bản ghi từ một lần chạy thực tế. Khi vận hành, nhớ dùng HTTPS, kho người dùng thật, phiên/cookie và chính sách đăng nhập phù hợp.

## 7. Kiểm thử cả redirect và phiên sau login bằng MockMvc

Một kiểm thử chỉ gửi POST login rồi nhận 302 chưa chứng minh người dùng có thể mở tài nguyên bảo vệ. Cần giữ **cùng session** qua chuỗi request:

1. `GET /dashboard` với khách chưa đăng nhập để tạo saved request.
2. `POST /login` trong session đó với CSRF và thông tin đúng.
3. `GET /dashboard` trong session đã đăng nhập để xác nhận SecurityContext được khôi phục.

Tệp `src/test/java/example/formlogin/FormLoginFlowTest.java`:

~~~java
package example.formlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public page"));
    }

    @Test
    void protectedPageRedirectsAnonymousUser() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void generatedLoginFormIsVisible() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("username")));
    }

    @Test
    void badPasswordRedirectsBackToLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "incorrect")
                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void postingWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void successfulLoginReturnsToSavedPageAndPersistsSession()
            throws Exception {

        MvcResult first = mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(session);

        MvcResult loggedIn = mvc.perform(post("/login")
                .session(session)
                .param("username", "lan")
                .param("password", "demo123")
                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/dashboard"))
                .andExpect(authenticated().withUsername("lan"))
                .andReturn();

        MockHttpSession loggedInSession =
                (MockHttpSession) loggedIn.getRequest().getSession(false);
        assertNotNull(loggedInSession);

        mvc.perform(get("/dashboard").session(loggedInSession))
                .andExpect(status().isOk())
                .andExpect(content().string("Dashboard (authenticated)"));
    }

    @Test
    void directLoginWithoutSavedRequestUsesDefaultTarget() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123")
                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/"));
    }

    @Test
    void ordinaryUserStillCannotEnterAdminPage() throws Exception {
        mvc.perform(get("/admin").with(user("lan").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithCsrfRedirectsToNotice() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123")
                .with(csrf()))
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

Lệnh kiểm thử:

~~~bash
./gradlew test --tests '*FormLoginFlowTest'
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests "*FormLoginFlowTest"
~~~

**Kết quả kỳ vọng:** 9 phép thử đều đạt trong môi trường có đúng dependencies và cấu hình nêu trên. Đây là kết quả suy ra theo API, **chưa phải báo cáo kiểm thử đã thực thi**. Test dùng Spring Security MockMvc request post-processors để cung cấp CSRF và danh tính giả. Browser thực vẫn cần kiểm tra thuộc tính cookie, HTTPS, session fixation và hành vi nhiều tab.

## 8. Trang login tùy chỉnh với Thymeleaf

Để có giao diện đăng nhập riêng, dùng một URL **hiển thị trang** và một URL **nhận dữ liệu POST**:

~~~java
// Đoạn thay thế phần formLogin của SecurityFilterChain.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/public", "/signin", "/css/**").permitAll()
        .requestMatchers("/dashboard").authenticated()
        .anyRequest().denyAll()
    )
    .formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/perform-login")
        .failureUrl("/signin?error")
        .defaultSuccessUrl("/dashboard", false)
        .permitAll()
    );
~~~

Giải thích:

- `loginPage("/signin")` đặt URL GET để browser tải HTML. Khi dùng trang tùy chỉnh, bạn cần tự định nghĩa route và view.
- `loginProcessingUrl("/perform-login")` là URL POST mà **filter xác thực** xử lý. Không tạo thêm POST Controller cùng URL này nếu vẫn dùng filter chuẩn.
- `failureUrl("/signin?error")` đặt redirect khi sai thông tin đăng nhập.
- `defaultSuccessUrl("/dashboard", false)` dùng dashboard khi không có saved request được ưu tiên.
- `.permitAll()` cho phép các URL cần dùng cho login; đồng thời công khai trang và tài nguyên tĩnh cần thiết.

Thêm `spring-boot-starter-thymeleaf` vào dependency, rồi tạo Controller:

~~~java
package example.formlogin;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class SignInController {

    @GetMapping("/signin")
    public String signin() {
        return "signin";
    }
}
~~~

Tạo tệp `src/main/resources/templates/signin.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>
    <form th:action="@{/perform-login}" method="post">
        <label for="username">Tên đăng nhập</label>
        <input id="username" name="username" autocomplete="username">

        <label for="password">Mật khẩu</label>
        <input id="password" type="password" name="password"
               autocomplete="current-password">

        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
~~~

Trong tích hợp Spring MVC/Thymeleaf, xử lý form `th:action` thường tự thêm trường CSRF ẩn qua cơ chế của Spring. Phải xem HTML sinh ra để chắc token được gửi. Nếu dùng HTML tĩnh hoặc template engine không hỗ trợ, cần lấy CSRF token do server cung cấp rồi đưa vào field phù hợp. Không sửa 403 bằng cách tắt CSRF toàn bộ.

`@Controller` trả `"signin"` để view resolver nạp template. `@RestController` trả nguyên văn `signin` vào response body và không thay thế vai trò render template của `@Controller`.

### Vòng lặp redirect nếu trang login không công khai

Nếu `GET /signin` cũng yêu cầu xác thực:

~~~text
GET /dashboard → 302 /signin
GET /signin    → 302 /signin
GET /signin    → 302 /signin
...
~~~

Hãy bảo đảm đường dẫn trang login và asset bắt buộc được phép truy cập khi chưa đăng nhập, đồng thời handler GET signin tồn tại. Vòng lặp cũng có thể xuất hiện khi cookie/session không được giữ sau login.

## 9. CSRF: tại sao POST /login có thể nhận 403?

Form login truyền thống hoạt động trong trình duyệt và thường sử dụng cookie phiên. Spring Security mặc định bảo vệ request có khả năng thay đổi trạng thái bằng CSRF:

| Request | Điều kiện | Kết quả thường gặp |
| --- | --- | --- |
| `GET /login` | Không cần submit username/password | Hiển thị trang login |
| `POST /login` | Đúng tên/mật khẩu, CSRF hợp lệ | Xác thực thành công, redirect |
| `POST /login` | Sai mật khẩu, CSRF hợp lệ | Redirect tới trang lỗi |
| `POST /login` | Thiếu/sai CSRF | 403 trước khi bước xác thực hoàn tất |
| `POST /logout` | CSRF hợp lệ | Đăng xuất và redirect |
| `POST /logout` | Thiếu/sai CSRF | 403 |

Thông báo 403 **không chứng minh người dùng nhập sai mật khẩu**. Nó có thể đến từ `CsrfFilter` trước khi form login được xử lý. Trong test MockMvc, `.with(csrf())` cho phép kiểm tra đúng nhánh xác thực. Trong browser, token được lấy từ trang do server render; đừng hardcode token vào HTML sản phẩm.

Bật HTTPS, cấu hình cookie và session phù hợp, duy trì chống CSRF đối với browser dùng cookie. Với API không dựa trên cookie phiên, cách bảo vệ có thể khác, nhưng phải dựa trên kiến trúc xác thực thực tế.

## 10. Cookie phiên, SecurityContext và session fixation

Form login truyền thống thường lưu trạng thái xác thực trong một session phía server. Browser mang cookie nhận diện phiên ở request tiếp theo, thường là `JSESSIONID` trong môi trường Servlet.

~~~http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=example-session-id; Path=/; HttpOnly
Location: /dashboard
~~~

Đây là **minh họa giao thức**, không phải một cookie thực. Browser sau đó gửi cookie ở lần GET tiếp theo:

~~~http
GET /dashboard HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=example-session-id
~~~

Trên server, `SecurityContextRepository` hỗ trợ lưu/đọc `SecurityContext`, trong đó có thông tin `Authentication`. Spring Security 6 có cơ chế yêu cầu lưu rõ ràng khi tự tạo authentication qua custom filter hoặc Controller; **chỉ đặt Authentication vào `SecurityContextHolder` của một request không bảo đảm request sau đã đăng nhập**. Bộ lọc form login chuẩn có bước quản lý/persist ngữ cảnh của riêng nó.

Để chống *session fixation* (kẻ tấn công gài trước session ID rồi dụ người dùng đăng nhập), Spring Security hỗ trợ thay đổi session ID khi login thành công. Trên Servlet container hiện đại, chiến lược thường là `changeSessionId`. Do đó, đừng coi việc session ID đổi sau đăng nhập là lỗi.

Với sản phẩm thực tế cần kiểm tra `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, HTTPS và thiết lập reverse proxy. Nếu browser không gửi cookie của phiên sau login, có thể bị redirect về login dù mật khẩu đã đúng.

## 11. Logout và redirect sau đăng xuất

Với `.logout(Customizer.withDefaults())`, thao tác logout hợp lệ thực hiện hủy/giải phóng trạng thái đăng nhập theo cấu hình (xóa ngữ cảnh, xử lý session...) rồi thường trả:

~~~http
HTTP/1.1 302 Found
Location: /login?logout
~~~

Đối với browser có CSRF đang bật, gửi POST logout với token hợp lệ; một liên kết GET tùy tiện không thay thế được form POST an toàn:

~~~html
<form th:action="@{/logout}" method="post">
    <button type="submit">Đăng xuất</button>
</form>
~~~

Đoạn trên dành cho Thymeleaf có tích hợp CSRF phù hợp. Trong ứng dụng có SSO/OIDC/remember-me, logout còn có những vấn đề khác như phiên ở Identity Provider và token ghi nhớ; ví dụ này chỉ mô tả form login Servlet cơ bản.

## 12. Những trường hợp khiến redirect và login hoạt động sai

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| GET /dashboard trả 302 /login | Chưa xác thực, đây có thể là luồng bình thường |
| GET /login trả 404 | Trang tùy chỉnh chưa có handler/view; URL login sai |
| GET /signin cứ redirect /signin | Trang login bị bảo vệ, chưa `permitAll()` |
| POST /login nhận 403 | CSRF sai hoặc thiếu |
| POST /login redirect /login?error | Sai credentials hoặc authentication failure |
| POST /perform-login trả 404 | Form action không khớp `loginProcessingUrl` |
| Đăng nhập đúng nhưng trở về URL khác | SavedRequest không có/không còn hoặc success URL cấu hình ưu tiên |
| Login thành công rồi lại chuyển tới login | Cookie/session/SecurityContext không duy trì giữa request |
| Đã login nhưng /admin trả 403 | Người dùng thiếu `ROLE_ADMIN`, khác lỗi đăng nhập |
| POST /logout trả 403 | Thiếu CSRF |
| SPA API nhận HTML login | Cơ chế redirect trang không phù hợp với hợp đồng API JSON |

Một request 302 có thể thuộc bước chưa login, login thành công hoặc login thất bại. Hãy xem **URL đích trong Location** rồi xác minh chuỗi request tiếp theo.

### Phân biệt website nhiều trang với API JSON

Form login và redirect phù hợp với browser điều hướng HTML. Với SPA/mobile gửi `fetch` và kỳ vọng JSON, một redirect tới trang login HTML có thể khiến client xử lý sai dữ liệu. Ứng dụng nên định nghĩa `AuthenticationEntryPoint`/phản hồi 401 phù hợp cho API hoặc tách `SecurityFilterChain` cho web và API theo thiết kế rõ ràng. Nếu API vẫn dùng cookie, vẫn cần đánh giá CSRF.

### Phân biệt redirect và forward

- **Redirect**: server trả 3xx và `Location`; browser tạo request mới, URL có thể thay đổi.
- **Forward**: Servlet chuyển xử lý nội bộ trong cùng request, browser không tự gửi request thứ hai.
- `defaultSuccessUrl` thường điều khiển redirect. Các lựa chọn forward của form login có ngữ nghĩa khác; không thay chúng tùy tiện.

## 13. Lỗi bảo mật hay gặp

1. **Viết form dùng GET để gửi mật khẩu.** Mật khẩu có thể lộ trong URL, history và log; dùng POST qua HTTPS.
2. **Quên bật formLogin sau khi tự định nghĩa SecurityFilterChain.** Không suy ra trang login mặc định luôn tồn tại.
3. **Nhầm GET /login với POST /login.** Một cái trả HTML, một cái nhận thông tin xác thực.
4. **Không công khai login page tùy chỉnh.** Gây redirect loop hoặc không tải được CSS/JS.
5. **Sai tên field form.** `name="email"` cần cấu hình tương ứng `usernameParameter("email")` nếu không dùng username mặc định.
6. **Không gửi CSRF.** POST login/logout có thể bị chặn trước khi credentials được kiểm tra.
7. **Lưu mật khẩu plaintext hoặc tự so sánh mật khẩu thô.** Dùng `PasswordEncoder` phù hợp.
8. **Tắt session fixation protection.** Làm tăng nguy cơ kẻ tấn công biết trước session ID được dùng sau login.
9. **Không lưu SecurityContext trong cơ chế xác thực tự viết.** Request sau có thể quay lại trạng thái anonymous.
10. **Nhận redirect URL không kiểm soát từ client.** Có thể tạo open redirect.
11. **Tin rằng sau login mọi tài nguyên đều được phép.** User vẫn cần role/authority cụ thể.
12. **Tự động phát lại POST nghiệp vụ sau login.** Không dựa vào saved request như cơ chế tự động gửi lại body hay xác nhận giao dịch.
13. **Chỉ kiểm thử POST /login một lần.** Cần kiểm tra chuỗi GET protected → POST login → GET protected trong cùng session.
14. **Đánh đồng cookie xuất hiện với đã xác thực.** Cookie có thể không hợp lệ, hết hạn hoặc không mang được SecurityContext.
15. **Chỉ theo dõi status cuối cùng.** Browser tự theo redirect; bật Preserve log để nhìn từng response trung gian.

## 14. Bài tập tự kiểm tra

**Câu 1:** Người chưa đăng nhập gọi `GET /dashboard` và nhận `302 Location: /login`. Ai gửi `GET /login` tiếp theo?

**Đáp án:** Trình duyệt, theo header Location. Đây là HTTP request mới.

**Câu 2:** Cấu hình form login mặc định có cần tự viết `@PostMapping("/login")` không?

**Đáp án:** Không. `UsernamePasswordAuthenticationFilter` nhận POST đúng URL xử lý login.

**Câu 3:** Login bằng đúng mật khẩu nhưng thiếu CSRF, nhận 403. Có kết luận mật khẩu sai được không?

**Đáp án:** Không. CSRF có thể chặn trước khi xác thực.

**Câu 4:** Người dùng mở `/dashboard` trước khi đăng nhập, đăng nhập xong quay lại dashboard. Thành phần nào thường giúp ghi nhớ đích?

**Đáp án:** `RequestCache`/`SavedRequest` và bộ xử lý đăng nhập thành công ưu tiên saved request.

**Câu 5:** Người đã xác thực có `ROLE_USER` truy cập `/admin` bảo vệ bằng `hasRole("ADMIN")` sẽ ra sao?

**Đáp án:** Không đạt điều kiện quyền, thường bị từ chối 403. Đăng nhập thành công không tạo role ADMIN.

**Câu 6:** Nếu muốn luôn chuyển tới `/home` sau login dù có saved request, cấu hình gì?

**Đáp án:** `defaultSuccessUrl("/home", true)` và đảm bảo người dùng được phép truy cập `/home`.

**Câu 7:** Trang login tùy chỉnh bị redirect lại chính nó vô hạn. Kiểm tra gì?

**Đáp án:** Route login có tồn tại, có công khai quyền `permitAll()`, có cấu hình loginPage/loginProcessingUrl đúng và cookie/session không bị mất không.

**Câu 8:** Vì sao cùng browser sau POST login đúng vẫn bị yêu cầu đăng nhập khi GET trang khác?

**Đáp án:** Cookie phiên không được gửi hoặc SecurityContext không được lưu/đọc đúng, hay ứng dụng dùng chế độ stateless không phù hợp với giả định.

## 15. Checklist trước khi triển khai sản phẩm

- Đã tách rõ URL hiển thị login, URL nhận POST và URL sau login chưa?
- Trang login và asset thiết yếu có thể tải khi anonymous chưa?
- Tên field username/password và URL form action đã khớp filter chưa?
- Đã có CSRF token hợp lệ cho các form login/logout chưa?
- PasswordEncoder, lưu trữ tài khoản, quản lý mật khẩu và chính sách lỗi đã đáp ứng yêu cầu chưa?
- Session fixation protection, timeout và logout được kiểm thử chưa?
- Cookie phiên có Secure, HttpOnly, SameSite, Path và Domain phù hợp khi dùng HTTPS chưa?
- Saved request và URL mặc định có hành vi đúng với nhiều tab, đường dẫn không tồn tại và URL không được phép chưa?
- Redirect đích có được giới hạn để tránh open redirect chưa?
- Đã kiểm thử nhánh chưa đăng nhập, sai mật khẩu, thiếu CSRF, đúng mật khẩu, thiếu role và logout chưa?
- Nếu có API JSON hoặc WebFlux, đã thiết kế authentication entry point và cơ chế ngữ cảnh đúng loại ứng dụng chưa?

**Điểm phải nhớ:** form login Servlet có **ba bước khác nhau**: redirect tới trang đăng nhập, POST xác thực rồi redirect/tiếp tục request đã lưu. Quan sát từng method, URL, status, Location và cookie trong trình duyệt sẽ giúp biết chính xác lỗi xảy ra ở bước nào.

## Tài liệu tham khảo

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/form.html): biểu mẫu mặc định và tùy chỉnh.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): ngữ cảnh bảo mật qua request.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/session-management.html): session và session fixation.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.3/servlet/exploits/csrf.html): CSRF cho form.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/logout.html): logout và chuyển hướng.
- [Spring Security — MockMvc Integration](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/index.html): kiểm thử với chuỗi bảo mật.
