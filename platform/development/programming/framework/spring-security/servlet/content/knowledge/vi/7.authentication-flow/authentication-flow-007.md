# AuthenticationSuccessHandler và AuthenticationFailureHandler trong Spring Security Servlet

## 1. Hai handler này giải quyết vấn đề gì?

Trong Spring Security chạy trên **Servlet stack** (Spring MVC, Tomcat và các Servlet container tương đương), việc gửi username/password chỉ là **đầu vào** cho quá trình xác thực. Sau khi một authentication filter xử lý credential, ứng dụng còn cần quyết định **HTTP response cho tình huống thành công hoặc thất bại**: chuyển về trang người dùng đã yêu cầu, mở dashboard, hiển thị thông báo lỗi, trả JSON, hay ghi audit.

Hai extension point thường dùng với **form login** là:

- **`AuthenticationSuccessHandler`**: tạo phản hồi sau khi bước xác thực do authentication filter điều phối **thành công**. Ví dụ redirect tới request đã lưu trước khi đăng nhập hoặc `/dashboard`.
- **`AuthenticationFailureHandler`**: tạo phản hồi khi chính bước xác thực đó **thất bại** với `AuthenticationException`. Ví dụ redirect tới `/login?error` hoặc trả HTTP 401 cho API.

**Chúng không phải** cơ chế kiểm tra password, không phải bộ phân quyền URL, và không thay thế việc xử lý CSRF/session. Handler quyết định phản hồi ở *điểm kết thúc một lần thử xác thực*, không tự làm cho principal hợp lệ.

Mục tiêu học tập:

1. Xác định chính xác handler được gọi khi nào trong luồng Servlet authentication.
2. Phân biệt form login failure với request chưa đăng nhập vào tài nguyên protected, và với request đã đăng nhập nhưng thiếu quyền.
3. Biết dùng `SavedRequestAwareAuthenticationSuccessHandler` và `SimpleUrlAuthenticationFailureHandler` thay vì tự viết redirect không an toàn.
4. Tạo cấu hình Spring Boot 3.x/Spring Security 6.x, Java 17+ có thể chạy và kiểm thử bằng MockMvc, không vô hiệu hóa CSRF cho tiện.
5. Thiết kế response/redirect phù hợp với web dùng cookie/session và API dùng JSON, đồng thời tránh lộ thông tin nhạy cảm.

## 2. Vị trí handler trong luồng `SecurityFilterChain`

Với form login tiêu chuẩn, `UsernamePasswordAuthenticationFilter` xử lý request đăng nhập (mặc định là **POST `/login`**) và gọi `AuthenticationManager`/các `AuthenticationProvider` được cấu hình để xác minh credential.

Luồng tổng quát:

```text
Browser                          Servlet / Spring Security
   |                                      |
   | POST /login + username/password     |
   |   + CSRF token + cookie session     |
   +------------------------------------->|
                                          |
                             FilterChainProxy chọn SecurityFilterChain
                                          |
                                    CsrfFilter (nếu áp dụng)
                                          |
                              UsernamePasswordAuthenticationFilter
                                          |
                              AuthenticationManager / Provider
                                          |
                              +-----------+------------+
                              |                        |
                       thành công                  thất bại
                              |                        |
                   session strategy /         clear SecurityContext,
                   SecurityContext được       thông báo remember-me
                   thiết lập/lưu phù hợp      thất bại (nếu dùng)
                              |                        |
                   AuthenticationSuccessHandler   AuthenticationFailureHandler
                              |                        |
                        302 /dashboard               302 /login?error
                        hoặc saved URL               hoặc HTTP 401 JSON
```

Sơ đồ trình bày **ý nghĩa các bước**, không liệt kê mọi filter theo thứ tự tuyệt đối cho tất cả phiên bản hoặc cơ chế authentication. Những filter trước authentication filter (đặc biệt CSRF) có thể chặn request **trước khi** success/failure handler có cơ hội chạy.

### Các interface có phương thức chính nào?

```java
// Chữ ký minh họa các phương thức của API Spring Security Servlet:
void onAuthenticationSuccess(
    jakarta.servlet.http.HttpServletRequest request,
    jakarta.servlet.http.HttpServletResponse response,
    org.springframework.security.core.Authentication authentication
) throws java.io.IOException, jakarta.servlet.ServletException;

void onAuthenticationFailure(
    jakarta.servlet.http.HttpServletRequest request,
    jakarta.servlet.http.HttpServletResponse response,
    org.springframework.security.core.AuthenticationException exception
) throws java.io.IOException, jakarta.servlet.ServletException;
```

Hai chữ ký trên chỉ là **trích dẫn phương thức** để giải thích, không phải khai báo `class` có thể biên dịch độc lập. Một `AuthenticationSuccessHandler` nhận `Authentication` đã được xác thực; một `AuthenticationFailureHandler` nhận lỗi xác thực. Không cố dùng failure handler để bắt mọi `AccessDeniedException` của request nghiệp vụ.

### Phân biệt bốn tình huống rất thường bị nhầm

| Tình huống | Thành phần xử lý thường gặp | Phản hồi web thông dụng |
| --- | --- | --- |
| POST `/login` với credential hợp lệ | Authentication filter → success handler | 302 tới saved request hoặc trang mặc định |
| POST `/login` với password sai | Authentication filter → failure handler | 302 tới `/login?error` |
| GET `/account` của người chưa đăng nhập | Authorization → `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | Redirect đến login page hoặc HTTP 401 |
| GET `/admin` của người đã đăng nhập nhưng thiếu quyền | Authorization → `AccessDeniedHandler` | Thường HTTP 403 |

Lỗi CSRF trên POST thường bị `CsrfFilter` từ chối, phổ biến là 403; nó **không** phải "mật khẩu sai" và thường không được chuyển tới `AuthenticationFailureHandler`.

**Nhận diện lỗi chính xác trước khi sửa:** `AuthenticationFailureHandler` xử lý lỗi **trong quá trình authentication mà filter đó phụ trách**. `AuthenticationEntryPoint` mở đầu quá trình authentication khi tài nguyên yêu cầu đăng nhập. `AccessDeniedHandler` xử lý quyền truy cập bị từ chối với caller đã xác thực. Ba loại callback phục vụ ba mục đích riêng.

## 3. Handler mặc định của form login

Khi bật form login bằng `http.formLogin(Customizer.withDefaults())` trong Spring Security Servlet, các hành vi mặc định đáng biết gồm:

- Nếu chưa có login page riêng, Spring Security thường tạo **trang GET `/login`** để tương tác trong trình duyệt.
- Form gửi credential lên **POST `/login`** với các tham số mặc định `username` và `password` (cùng CSRF token khi CSRF protection áp dụng).
- Thành công thường sử dụng **`SavedRequestAwareAuthenticationSuccessHandler`**: ưu tiên trả người dùng về URL được lưu trước lúc phải đăng nhập, hoặc dùng trang mặc định.
- Thất bại thường sử dụng **`SimpleUrlAuthenticationFailureHandler`**: redirect đến `/login?error` trong kiểu cấu hình form login mặc định (hành vi cụ thể có thể được tùy biến).

Đừng coi `failureUrl` và `failureHandler` là hai bước luôn chạy liên tiếp. `failureUrl(...)` là một cách cấu hình behavior redirect; khi tự đặt `failureHandler(...)`, handler ấy sẽ chịu trách nhiệm thực hiện response tương ứng. Tương tự, `defaultSuccessUrl(...)` và `successHandler(...)` cùng liên quan đến nhánh thành công, nhưng handler do bạn đăng ký quyết định luồng cuối.

### Success handler và "saved request"

Một người dùng chưa đăng nhập cố mở `GET /account`. Khi cấu hình session/request cache hỗ trợ, `ExceptionTranslationFilter` có thể lưu request này trước khi chuyển tới login page. Sau khi đăng nhập thành công:

```text
GET /account (anonymous)
        |
        v
RequestCache lưu request gốc
        |
        v
302 /login  ->  GET /login
        |
        v
POST /login + thông tin hợp lệ
        |
        v
SavedRequestAwareAuthenticationSuccessHandler
        |
        +--> redirect về /account (nếu có saved request phù hợp)
        |
        +--> redirect về defaultTargetUrl (nếu không có saved request)
```

Điều này tạo trải nghiệm tốt hơn so với luôn đưa người dùng về `/`. Request cache không phải là cơ sở để tin mọi URL do client tự khai; redirect vẫn phải tuân theo chính sách URL/host an toàn của ứng dụng. Các deployment stateless có thể không có session/saved request giống web browser.

`SimpleUrlAuthenticationSuccessHandler` phù hợp khi muốn chuyển hướng tới một URL mục tiêu cố định hoặc tùy biến đơn giản. `SavedRequestAwareAuthenticationSuccessHandler` mở rộng behavior đó để xử lý saved request. **Không tự nối `request.getParameter("next")` vào `sendRedirect`** nếu chưa xác thực target để tránh open redirect.

## 4. Điều gì xảy ra trước khi success handler chạy?

Authentication handler thường là **phần cuối về phản hồi HTTP** của một lần thử xác thực. Trong luồng `AbstractAuthenticationProcessingFilter` (cơ sở của nhiều filter form login), khi authentication thành công, Spring Security đã có cơ hội thực hiện các công việc như:

1. `AuthenticationManager` xác minh credential và tạo `Authentication` thành công.
2. Session authentication strategy xử lý các chính sách liên quan phiên, chẳng hạn chống **session fixation** khi sử dụng phiên.
3. `SecurityContext` được thiết lập và được lưu theo cơ chế `SecurityContextRepository` phù hợp.
4. Remember-me services, nếu được cấu hình, nhận thông báo success; authentication success event có thể được publish.
5. Sau đó success handler tạo redirect hoặc response.

Thứ tự/chi tiết có thể khác nhau giữa các loại authentication filter và tùy chỉnh ứng dụng. **Không dùng success handler để tự đặt `isAuthenticated=true`, lưu mật khẩu trong session hay tự ghi đè security context** khi filter đã làm đúng phần việc đó.

Trong nhánh thất bại, các bước thường bao gồm xóa `SecurityContext` của lần thử đó, thông báo remember-me services nếu có, rồi gọi failure handler. Không giả định rằng thất bại luôn có session tồn tại; tùy cơ chế login và cấu hình, session có thể chưa được tạo.

### Vì sao không nên tự xử lý session trong handler?

Việc tự `request.getSession().setAttribute("USER", username)` không thay thế mô hình security context và dễ xung đột session fixation protection. Một session attribute tùy biến cũng không làm cho request tiếp theo được Spring Security xác thực. Nếu cần ghi thông tin hiển thị sau login, nên dùng đối tượng `Authentication` được framework cung cấp hoặc một service nghiệp vụ riêng, không chép password/token nhạy cảm vào session.

## 5. Ví dụ đầy đủ Spring Boot 3.x / Java 17+: delegate tới handler chuẩn

Dự án Spring Boot Servlet (Spring Security 6.x) đã được cấu hình plugin build và dependency management cần hai dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Tạo tệp **`src/main/java/example/loginhandlers/LoginHandlersApplication.java`**:

```java
package example.loginhandlers;

import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginHandlersApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginHandlersApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    private static final Logger LOG =
        LoggerFactory.getLogger(SecurityConfiguration.class);

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationSuccessHandler loginSuccessHandler,
            AuthenticationFailureHandler loginFailureHandler
    ) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/dashboard").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler(loginSuccessHandler)
                .failureHandler(loginFailureHandler)
                .permitAll()
            )
            .build();
    }

    @Bean
    AuthenticationSuccessHandler loginSuccessHandler() {
        SavedRequestAwareAuthenticationSuccessHandler delegate =
            new SavedRequestAwareAuthenticationSuccessHandler();

        delegate.setDefaultTargetUrl("/dashboard");
        delegate.setAlwaysUseDefaultTargetUrl(false);

        return (request, response, authentication) -> {
            // Chỉ ghi sự kiện tối thiểu; không log password/cookie/token.
            LOG.info("Form login success for principal type={}",
                authentication.getPrincipal().getClass().getSimpleName());

            // Delegate giữ lại logic chuyển tới saved request an toàn theo cấu hình.
            delegate.onAuthenticationSuccess(request, response, authentication);
        };
    }

    @Bean
    AuthenticationFailureHandler loginFailureHandler() {
        SimpleUrlAuthenticationFailureHandler delegate =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, exception) -> {
            // Không gửi message từ AuthenticationException ra trình duyệt.
            LOG.warn("Form login rejected; exception type={}",
                exception.getClass().getSimpleName());

            delegate.onAuthenticationFailure(request, response, exception);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }
}

@RestController
class SampleController {

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "Admin dashboard";
    }
}
```

Chỉ `LoginHandlersApplication` là public top-level class, nên ba class chung một tệp hợp lệ với Java 17. `@SpringBootApplication` quét package `example.loginhandlers` và phát hiện configuration/controller.

**Vì sao ví dụ này có ích?**

- Không tùy biến trang login: Spring Security cung cấp GET `/login` khi cấu hình phù hợp.
- `.formLogin(...permitAll())` cho phép truy cập các URL cần cho login page/login processing theo cơ chế form login; `anyRequest().denyAll()` vẫn chặn endpoint khác không khai báo.
- `SavedRequestAwareAuthenticationSuccessHandler` ưu tiên URL request được cache; nếu không có, chuyển tới `/dashboard`.
- `SimpleUrlAuthenticationFailureHandler` chuyển người dùng về `/login?error`, không tiết lộ user có tồn tại, password sai hay account bị khóa thông qua response message chi tiết.
- Logger chỉ ghi **loại principal** hoặc **loại exception** để minh họa. Vận hành thực tế nên thiết kế audit theo policy tổ chức, có correlation ID và tránh lưu thông tin định danh không cần thiết.
- Hai tài khoản chỉ dành cho demo, password được encoder tạo hash trước khi lưu trong memory. Không sao chép tài khoản/mật khẩu thử nghiệm sang production.
- Không tắt CSRF: trình duyệt sử dụng form login mặc định và CSRF token do Spring Security cấp. Không gửi username/password qua HTTP công khai ở production.

### Chạy ứng dụng

Với project Gradle Spring Boot đã có wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell dùng `./gradlew.bat bootRun`. Sau khi khởi động trên cổng local 8080, mở trình duyệt:

```text
http://localhost:8080/dashboard
```

Kỳ vọng: browser được chuyển tới trang login. Nhập `learner` / `demo-pass` vào form được Spring Security tạo; khi thành công, handler đưa browser về **`/dashboard` đã lưu**, và controller phản hồi:

```text
Hello learner
```

Nếu mở trực tiếp `http://localhost:8080/login` trước (không có saved request), sau đăng nhập thành công vẫn được chuyển tới `/dashboard` nhờ `setDefaultTargetUrl`. Nếu nhập password sai, failure handler chuyển tới `/login?error`, nơi trang login mặc định có thể hiển thị thông báo lỗi chung.

**Lưu ý**: đây là output và luồng **dự kiến theo cấu hình**, không phải stdout được thu từ một lần chạy thực tế. Redirect có thể dùng đường dẫn tương đối hoặc URL tuyệt đối theo Servlet container, context path và cách ứng dụng được triển khai sau proxy.

## 6. Kiểm thử với MockMvc: success, failure, saved request, CSRF

Chỉ nhìn thấy một redirect trong browser chưa đủ để xác nhận ranh giới. Test phải tách được: authentication thành công, authentication thất bại, CSRF thất bại và đã đăng nhập nhưng thiếu quyền.

Trong dự án Spring Boot đã cấu hình test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo tệp `src/test/java/example/loginhandlers/LoginHandlersSecurityTest.java`:

```java
package example.loginhandlers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginHandlersSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginRedirectsToDefaultWhenNoSavedRequest()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/dashboard")));
    }

    @Test
    void badPasswordUsesFailureHandlerRedirect() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "not-the-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login?error")));
    }

    @Test
    void anonymousProtectedRequestStartsLoginRatherThanFailureHandler()
            throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login")));
    }

    @Test
    void savedRequestIsRestoredAfterSuccessfulFormLogin() throws Exception {
        MvcResult first = mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) first.getRequest().getSession(false);

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/dashboard")));
    }

    @Test
    void csrfFilterRejectsLoginPostMissingToken() throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(org.springframework.security.test.web.servlet
                    .request.SecurityMockMvcRequestPostProcessors
                    .user("learner").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
```

Kiểm thử qua `MockMvc` giúp dùng `.with(csrf())` để gửi CSRF token hợp lệ cho POST login; không cần tắt tính năng bảo vệ này. Test saved request mang cùng `MockHttpSession` từ GET protected page sang POST login, nên kiểm tra được hành vi khôi phục URL. Sau khi session strategy xử lý login, ID session có thể thay đổi theo policy; test chỉ kiểm tra Location chứ không giả định ID không đổi.

Chạy:

```bash
./gradlew test
```

Các test trên là **ví dụ đề xuất**, chưa được thực thi trong tài liệu này. Khi viết test cho production, nên bổ sung assertion cụ thể về việc xác thực đã được lưu đúng context/session và kiểm tra `SecurityContextRepository` theo thiết kế (stateful/stateless).

## 7. Tùy chỉnh response thế nào cho đúng loại client?

Form login truyền thống hướng tới browser có điều hướng. Đối với một SPA/API có cơ chế login riêng, response mong muốn có thể khác. Không nên dùng **HTTP 302** cho mọi API authentication failure nếu client kỳ vọng mã 401 và payload JSON.

### 7.1. Success handler cho browser

Ưu tiên delegate đã được Spring Security hỗ trợ:

```java
SavedRequestAwareAuthenticationSuccessHandler success =
    new SavedRequestAwareAuthenticationSuccessHandler();

success.setDefaultTargetUrl("/dashboard");
success.setAlwaysUseDefaultTargetUrl(false);
```

Đoạn này minh họa cách tạo handler, cần đặt trong method/class thích hợp. `alwaysUseDefaultTargetUrl(false)` cho phép ưu tiên saved request nếu có. Ngược lại, đặt `true` khi chính sách thực sự muốn **luôn** đưa user tới một điểm duy nhất và bỏ qua saved request.

**Nếu ứng dụng đa tenant hoặc cần bước onboarding**, success handler có thể quyết định đích theo dữ liệu server-side đã được xác minh. Không tin trực tiếp `?returnUrl=https://evil.example`; chỉ cho redirect tới path nội bộ hợp lệ hoặc origin đã allowlist.

### 7.2. Failure handler cho browser

```java
SimpleUrlAuthenticationFailureHandler failure =
    new SimpleUrlAuthenticationFailureHandler("/login?error");
```

Handler chuẩn giúp thực hiện redirect sau login thất bại. `?error` chỉ là **tín hiệu UI**, không nhất thiết mô tả lý do cụ thể. Tránh hiển thị `BadCredentialsException.getMessage()` trực tiếp cho người dùng. Với các trường hợp account bị khóa, password sai, account không tồn tại, chính sách thông báo nên cân bằng UX và rủi ro username enumeration.

### 7.3. JSON response cho API login — fragment tùy biến

Nếu có **authentication filter xử lý POST login API** và đã cấu hình nó để sử dụng success/failure handlers, bạn có thể trả JSON thay vì redirect:

```java
AuthenticationSuccessHandler apiSuccess = (request, response, auth) -> {
    response.setStatus(HttpServletResponse.SC_OK);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write("{\"authenticated\":true}");
};

AuthenticationFailureHandler apiFailure = (request, response, exception) -> {
    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write("{\"error\":\"invalid_credentials\"}");
};
```

Đây là **fragment**, cần import `HttpServletResponse` và khai báo trong method/class thích hợp; ví dụ chỉ viết JSON cố định để tránh lỗi escape do đầu vào. Không phản ánh nguyên văn exception, token, principal hoặc submitted password trong payload.

**Quan trọng:** Khai báo một `AuthenticationSuccessHandler` bean không làm cho mọi request API tự được xác thực. Nó chỉ chạy khi **authentication filter cụ thể** nhận request và được nối với handler ấy. `httpBasic()`, OAuth2 login, bearer-token resource server và form login có các entry point/filter mặc định riêng; muốn thay đổi response của cơ chế nào phải cấu hình đúng extension point của cơ chế đó.

Đừng chuyển code browser cookie/session sang API stateless rồi vô điều kiện tắt CSRF. Cần xét nguồn credential (cookie được browser tự gửi, bearer token do client chủ động gắn, v.v.), CORS, SameSite, session policy và CSRF threat model trước khi thiết kế.

## 8. Những gì handler KHÔNG làm

### Không thay `AuthenticationProvider`

`AuthenticationSuccessHandler` không kiểm tra password; tại thời điểm nó chạy, authentication manager/provider đã quyết định thành công. Nếu muốn kiểm tra thêm tài khoản bị vô hiệu hóa hoặc yếu tố xác thực tiếp theo, chọn vị trí phù hợp trong authentication pipeline, không để success handler "cấp phép lại" bằng một chuỗi `if` tùy ý.

### Không thay authorization

Đăng nhập thành công chỉ tạo ra một `Authentication`; không có nghĩa người dùng được phép xem mọi URL. `hasRole("ADMIN")`, `hasAuthority(...)`, authorization theo ownership và các policy domain vẫn phải được thực hiện. Handler chỉ quyết định response khi login, không mở cửa admin.

### Không thay `AuthenticationEntryPoint`

Nếu anonymous truy cập `GET /dashboard`, Spring Security thường kích hoạt `AuthenticationEntryPoint` để chuyển tới `/login`. Đó không phải thất bại khi kiểm tra username/password. `AuthenticationFailureHandler` không được gọi chỉ vì user chưa đăng nhập.

### Không thay `AccessDeniedHandler`

User đã đăng nhập nhưng thiếu `ROLE_ADMIN` gọi `GET /admin` thường gặp 403 từ access-denied processing. Không đi qua login failure handler. Nếu muốn trang 403 tùy biến, cấu hình exception handling/access denied ở đúng vị trí.

### Không giải quyết mọi lỗi trước authentication filter

Request `POST /login` thiếu CSRF token có thể bị từ chối trước `UsernamePasswordAuthenticationFilter`. Một lỗi định dạng HTTP, request path không khớp login processing URL hoặc reverse proxy redirect loop cũng không phải trường hợp success/failure handler được gọi.

### Không tự động quản lý audit/lockout/rate limit

Ghi log "password sai" trong failure handler **không đủ** chống brute-force, password spraying, credential stuffing. Cần các biện pháp tương ứng ở authentication service, rate limiter, security monitoring hoặc gateway, với giới hạn tài nguyên hợp lý và tránh vô tình cho phép tấn công từ chối dịch vụ bằng cách khóa tài khoản hàng loạt.

## 9. Chọn giữa handler viết tay và handler chuẩn

| Nhu cầu | Giải pháp thông thường | Điểm cần cân nhắc |
| --- | --- | --- |
| Login thành công trở lại URL protected trước đó | `SavedRequestAwareAuthenticationSuccessHandler` | RequestCache và session phải phù hợp, URL public đáng tin |
| Login thành công luôn về dashboard | `SimpleUrlAuthenticationSuccessHandler` hoặc `defaultSuccessUrl(..., true)` | Không khôi phục saved request nếu luôn ép target |
| Login thành công cần audit nhẹ rồi redirect chuẩn | Handler riêng **delegate** tới saved-request handler | Không viết response trước khi delegate redirect |
| Login thất bại trở về login page | `SimpleUrlAuthenticationFailureHandler` hoặc `failureUrl(...)` | Giữ message chung, tránh username enumeration |
| Login API trả status và JSON | Handler gắn vào authentication filter tương ứng | Không gán mặc định tất cả cơ chế auth là form login |
| Caller anonymous truy cập tài nguyên protected | `AuthenticationEntryPoint` | Không dùng failure handler |
| Caller đã login nhưng thiếu quyền | `AccessDeniedHandler` và authorization rules | Không dùng failure handler |

Quy tắc thực dụng: **ưu tiên cấu hình sẵn có hoặc delegate; chỉ tự code phần chính sách thực sự cần**. Một handler tự viết vừa làm audit, cập nhật tài khoản, phát token, redirect, xóa cookie và gửi nhiều response thường khó test, dễ phát sinh trạng thái nửa thành công.

## 10. Các lỗi triển khai và cách gỡ

### 10.1. Browser bị redirect loop sau đăng nhập

Triệu chứng: POST login 302 nhưng browser liên tục quay lại `/login`. Nguyên nhân có thể là session/security context không được duy trì ở request tiếp theo, cookie thiếu/chặn, URL redirect không phù hợp, đường dẫn yêu cầu bị deny, hoặc proxy hiểu nhầm HTTPS.

Hướng chẩn đoán: theo dõi chuỗi HTTP status/Location trong Network tab, xác minh cookie session được gửi lại, security chain bao phủ URL đích và policy authorization cho URL đó. Không sửa bằng cách tùy tiện `permitAll()` cả ứng dụng.

### 10.2. Login thành công nhưng không tới `/dashboard`

Nếu có saved request, `SavedRequestAwareAuthenticationSuccessHandler` **ưu tiên saved request** theo cấu hình. Muốn luôn về dashboard, có thể dùng `setAlwaysUseDefaultTargetUrl(true)`, nhưng cần giải thích rõ trải nghiệm khi user vừa yêu cầu trang protected. Một `RequestCache` bị thay đổi/disabled cũng ảnh hưởng behavior.

### 10.3. Cấu hình handler nhưng không bao giờ chạy

Kiểm tra request có khớp **login processing URL** của authentication filter không; filter/chain có được chọn không; credential có đi đúng parameter names không; CSRF có chặn trước không; có config form login khác ghi đè handlers không. Tạo `@Bean AuthenticationFailureHandler` đơn lẻ chưa chắc khiến Spring Security tự dùng nó nếu không gắn vào `formLogin`.

### 10.4. Failure handler trả HTML/302 cho client API

Client gọi API có thể không tự xử lý redirect như browser; response là HTML login page thay vì JSON. Hãy phân biệt chain và authentication mechanism dành cho browser với API, định nghĩa mã lỗi và content type phù hợp. Không dùng `sendError(401)` sau khi đã `sendRedirect`: HTTP response có thể đã bị commit.

### 10.5. Log cả username/password hoặc exception message

Username có thể là dữ liệu cá nhân; password, OTP, session ID, CSRF token, bearer token là dữ liệu nhạy cảm. Không log `request.getParameter("password")`, raw `Authentication` hoặc `Authorization` header. Thông tin audit nên được thiết kế có phân quyền truy cập, thời gian lưu và giới hạn PII phù hợp.

### 10.6. Open redirect qua `?next=`

Ví dụ nguy hiểm:

```java
String next = request.getParameter("next");
response.sendRedirect(next); // KHÔNG dùng khi next chưa được kiểm soát.
```

Client có thể cung cấp một URL tới trang tấn công, khiến redirect sau login trỏ sang domain lạ. Nếu cần return URL, ưu tiên server-side saved request với ràng buộc host, hoặc chỉ cho path nội bộ khởi đầu bằng `/` với validation chặt (chặn `//`, encoding bất thường, ký tự điều khiển, scheme lạ, context path sai). Không chỉ kiểm tra `startsWith("/")` rồi kết luận an toàn.

### 10.7. Bỏ CSRF để test đăng nhập

Với form login sử dụng browser cookie/session, vô hiệu hóa CSRF vô điều kiện làm tăng rủi ro login CSRF và CSRF cho các hành động khác. Trong MockMvc, dùng `.with(csrf())`; trong browser, dùng login form và CSRF token do framework cấp. Một `POST /login` không có token thất bại không chứng minh failure handler cấu hình sai.

### 10.8. Lưu trạng thái đăng nhập bằng attribute tùy biến

Tự đặt `session.setAttribute("loggedIn", true)` trong success handler không thay thế `Authentication` trong `SecurityContext`. Những đoạn code kiểm tra session attribute còn dễ bất đồng bộ với logout, session expiration, authentication failure và concurrency control. Dùng Spring Security authentication/authorization đã được cấu hình.

## 11. Kiểm thử bảo mật ngoài happy path

Một bộ kiểm thử nghiệm thu nên có các tình huống sau:

| Test case | Kỳ vọng |
| --- | --- |
| POST login credential hợp lệ và CSRF hợp lệ | Success handler chạy, tạo response mong muốn, identity hợp lệ |
| POST login password sai và CSRF hợp lệ | Failure handler chạy, response không tiết lộ lý do nhạy cảm |
| POST login thiếu CSRF token | CSRF filter chặn (thường 403), không xem là lỗi password |
| GET trang protected khi anonymous | AuthenticationEntryPoint kích hoạt login challenge/redirect |
| GET admin khi user đã login thiếu quyền | AccessDeniedHandler xử lý, thường 403 |
| Login sau khi có saved protected request | Redirect về saved URL nếu chính sách cho phép |
| Login trực tiếp từ login page | Redirect về fallback `/dashboard` |
| URL mục tiêu chứa hostname không được phép | Không sinh redirect ra external host lạ |
| Login thành công rồi yêu cầu tiếp theo | SecurityContext/session được duy trì đúng lifecycle |
| Thay đổi session ID theo session-fixation policy | Không giữ session ID cũ trái chính sách |
| Request qua HTTPS reverse proxy | `Location`, scheme, host và cookie policy phản ánh origin public |
| Login API (nếu có) | Không bất ngờ trả HTML/302 khi contract yêu cầu 401 JSON |

Trong production, cần bổ sung kiểm thử chống brute-force, tài khoản khóa, password hết hạn, thông báo lỗi đồng nhất, logout và xử lý concurrent sessions theo yêu cầu nghiệp vụ. Handler không tự thực hiện những chính sách ấy.

## 12. Câu hỏi ôn tập (kèm đáp án)

**Câu 1.** Người dùng nhập mật khẩu sai ở POST `/login`. Handler nào được dùng trong form login chuẩn?

**Đáp án:** `AuthenticationFailureHandler` được cấu hình cho authentication filter xử lý POST login (với điều kiện request vượt qua các filter trước và có exception xác thực). Đây không phải `AccessDeniedHandler`.

**Câu 2.** Anonymous truy cập GET `/admin` và được chuyển tới `/login`. Có phải đã gọi failure handler chưa?

**Đáp án:** Chưa. Spring Security thường gọi `AuthenticationEntryPoint` do endpoint yêu cầu người dùng phải đăng nhập; không có lần xác thực password thất bại.

**Câu 3.** Tại sao success handler cần delegate `SavedRequestAwareAuthenticationSuccessHandler` thay vì luôn redirect cứng?

**Đáp án:** Delegate hỗ trợ trở lại tài nguyên mà người dùng đã yêu cầu trước login và có fallback khi không có saved request. Redirect cứng cũng có thể hợp lệ nếu sản phẩm cố ý bỏ qua saved request.

**Câu 4.** Một web app dùng session, POST login thiếu CSRF token và trả 403. Có nên kiểm tra password encoder hoặc failure handler đầu tiên không?

**Đáp án:** Nên kiểm tra `CsrfFilter`/CSRF token, vì request có thể bị từ chối **trước** khi tới authentication filter. MockMvc dùng `.with(csrf())` khi test đường login hợp lệ.

**Câu 5.** Một user đăng nhập thành công nhưng gọi GET `/admin` nhận 403. Có nên chuyển hướng bằng success handler không?

**Đáp án:** Không. Login thành công và quyền admin là hai quyết định khác nhau. Chính sách `hasRole("ADMIN")` và access-denied processing xử lý authorization.

**Câu 6.** Handler tự đọc `?next=https://other.example` rồi redirect tới URL đó. Nguy cơ là gì?

**Đáp án:** Open redirect sau login. Chỉ điều hướng tới đích được server kiểm soát hoặc đã validate/allowlist rõ ràng.

**Câu 7.** API client cần JSON lỗi `401` khi POST login không hợp lệ. Chỉ tạo một `@Bean AuthenticationFailureHandler` có đủ không?

**Đáp án:** Chưa đủ. Phải có authentication filter thực sự xử lý login API, gắn handler vào đúng filter/chain và xác nhận contract của client cũng như CSRF/session policy.

## 13. Tóm tắt kỹ thuật cần nhớ

- `AuthenticationSuccessHandler` nhận `Authentication` **đã thành công** và quyết định redirect/response cuối cho một lần xác thực.
- `AuthenticationFailureHandler` nhận `AuthenticationException` **từ bước xác thực** và quyết định thông báo/response thất bại.
- Với form login Servlet, **`SavedRequestAwareAuthenticationSuccessHandler`** hỗ trợ URL đã lưu; **`SimpleUrlAuthenticationFailureHandler`** hỗ trợ chuyển về trang lỗi.
- **`AuthenticationEntryPoint`** xử lý nhu cầu bắt đầu đăng nhập khi anonymous truy cập protected URL; **`AccessDeniedHandler`** xử lý authorization bị từ chối. Không trộn ba luồng.
- **CSRF, security context, session fixation, request cache và authorization** có vai trò riêng; handler không thay thế chúng.
- Ưu tiên delegate và kiểm thử status/`Location`/session theo từng tình huống. Không trả raw exception cho client, không log credential và không redirect tới URL client tự cung cấp mà chưa xác thực.

**Nguyên tắc chính:** Handler thành công/thất bại là **điểm tùy biến phản hồi sau nỗ lực xác thực**, không phải nơi định nghĩa liệu user có đúng mật khẩu hay được phép truy cập tài nguyên nào.
