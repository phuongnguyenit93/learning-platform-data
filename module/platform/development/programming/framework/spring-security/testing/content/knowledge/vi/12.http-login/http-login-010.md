# Kiểm tra bằng header hoặc form thực thay vì đưa sẵn người dùng vào context

Trong kiểm thử Spring Security, một request có thể được xem là đã đăng nhập theo hai con đường rất khác nhau: **gắn sẵn một đối tượng xác thực vào `SecurityContext`**, hoặc **gửi thông tin đăng nhập qua request HTTP để bộ lọc bảo mật xử lý**. Cả hai cách đều hữu ích, nhưng chúng trả lời những câu hỏi khác nhau.

Với chủ đề **Đăng nhập qua HTTP**, mục tiêu là kiểm tra chính luồng đăng nhập của ứng dụng Servlet: client gửi header `Authorization` hoặc gửi biểu mẫu gồm tên đăng nhập và mật khẩu; Spring Security đọc request, chọn cơ chế xác thực, kiểm tra thông tin đăng nhập rồi quyết định cho phép, từ chối hoặc chuyển hướng. Đây là điểm khác biệt cốt lõi so với `@WithMockUser` hoặc `with(user(...))`, vốn tạo sẵn danh tính để kiểm thử các quy tắc phân quyền.

Sau bài này, bạn có thể:

- Tạo bài kiểm thử `MockMvc` gửi HTTP Basic header và form login qua bộ lọc bảo mật thực của ứng dụng.
- Phân biệt lỗi **401 Unauthorized** (chưa xác thực hoặc sai thông tin đăng nhập), **403 Forbidden** (đã xác thực nhưng thiếu quyền, hoặc request vi phạm CSRF) và **302 Found** (chuyển hướng thường gặp của form login).
- Kiểm chứng mật khẩu sai, tham số đăng nhập, CSRF, session và yêu cầu tiếp theo sau khi đăng nhập.
- Nhận biết trường hợp kiểm thử "xanh" vì đã đặt sẵn `SecurityContext` nhưng chưa hề kiểm tra cơ chế đăng nhập.

## 1. Hai đường đi của request khác nhau ở đâu?

Giả sử endpoint `GET /api/private` chỉ cho người đã đăng nhập truy cập.

**Cách A — cấp sẵn danh tính cho bài test:**

~~~java
mockMvc.perform(get("/api/private").with(user("alice")))
    .andExpect(status().isOk());
~~~

Lệnh `user("alice")` của `spring-security-test` thiết lập một danh tính kiểm thử. Request được xử lý trong bối cảnh Alice đã được xác thực; bài test có thể kiểm tra việc bảo vệ URL hoặc phân quyền, nhưng không chứng minh hệ thống đã đọc username/password hay kiểm tra mật khẩu.

**Cách B — gửi thông tin xác thực qua giao thức HTTP:**

~~~java
mockMvc.perform(get("/api/private")
        .with(httpBasic("alice", "secret")))
    .andExpect(status().isOk());
~~~

`httpBasic("alice", "secret")` tạo header HTTP Basic cho request. `BasicAuthenticationFilter` (khi được cấu hình) đọc header, chuyển thông tin đăng nhập cho `AuthenticationManager`/`AuthenticationProvider`, kiểm tra tài khoản và mật khẩu qua `UserDetailsService`/`PasswordEncoder` rồi mới đặt kết quả xác thực vào `SecurityContext`.

| Cách kiểm thử | Dữ liệu đầu vào | Có thực thi cơ chế kiểm tra mật khẩu? | Mục đích chính |
| --- | --- | --- | --- |
| `@WithMockUser` | Annotation tạo danh tính cho test | Không | Kiểm thử phân quyền theo người dùng/vai trò |
| `with(user("alice"))` | Danh tính giả lập gắn với request | Không | Kiểm thử URL, quyền truy cập hoặc method security |
| `with(httpBasic("alice", "secret"))` | Header `Authorization: Basic ...` | Có, nếu filter chain và provider được nối đúng | Kiểm thử HTTP Basic login |
| `formLogin().user(...).password(...)` | `POST /login` với form parameters | Có, nếu form login được bật | Kiểm thử đăng nhập biểu mẫu |
| `post("/login").param(...).with(csrf())` | HTTP POST tự dựng | Có, nếu xử lý bởi login filter | Kiểm tra request thực và CSRF ở mức chi tiết |

Luồng HTTP Basic điển hình:

~~~mermaid
sequenceDiagram
    participant C as MockMvc / Client
    participant F as SecurityFilterChain
    participant P as AuthenticationProvider
    participant A as API
    C->>F: GET /api/private + Authorization: Basic ...
    F->>P: Xác thực username + password
    alt Thông tin hợp lệ
        P-->>F: Authentication đã xác thực
        F->>A: Tiếp tục với SecurityContext
        A-->>C: 200 OK
    else Thông tin không hợp lệ
        P-->>F: AuthenticationException
        F-->>C: 401 Unauthorized
    end
~~~

**Giới hạn cần hiểu:** `MockMvc` chạy pipeline Spring MVC và Servlet security filters trong tiến trình kiểm thử, không mở một kết nối TCP/TLS thật. Vì vậy, từ “thực” ở đây nghĩa là **request đi qua cơ chế xác thực HTTP đã cấu hình**, chứ không đồng nghĩa với kiểm thử end-to-end qua mạng, reverse proxy hoặc nhà cung cấp định danh bên ngoài.

## 2. Dựng ứng dụng Servlet tối thiểu để quan sát hành vi

Ví dụ giả định một ứng dụng Spring Boot Servlet có `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test` trong test classpath. `spring-security-test` cung cấp `httpBasic()`, `formLogin()` và các matcher `authenticated()`/`unauthenticated()`. Không cần máy chủ thật hay tài khoản bên ngoài.

Ta bật đồng thời HTTP Basic và form login trên một `SecurityFilterChain` để minh họa hai kiểu request. Đối với hệ thống thực tế, có thể dùng nhiều filter chain và chính sách riêng cho API/browser.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**", "/web/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults());

        // Giữ CSRF mặc định bật, đặc biệt để kiểm tra POST /login.
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
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Ở đây:

- `alice` có vai trò `ROLE_USER`, đăng nhập bằng mật khẩu `secret`; `admin` có vai trò `ROLE_ADMIN`.
- Spring Security kiểm tra mật khẩu đã mã hóa bằng `BCryptPasswordEncoder`. Tài khoản in-memory chỉ là fixture của bài kiểm thử; nó vẫn đi qua luồng xác thực của ứng dụng.
- `/api/admin` đòi `ADMIN`, còn `/api/private` và `/web/profile` chỉ đòi người dùng đã xác thực.
- CSRF vẫn được bật. HTTP GET không cần CSRF token; `POST /login` tự dựng sẽ cần token hợp lệ theo cấu hình mặc định.

Các endpoint được bảo vệ có thể là:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProtectedEndpoints {

    @GetMapping("/api/private")
    String privateApi(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    String adminApi() {
        return "admin-area";
    }

    @GetMapping("/web/profile")
    String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }
}
~~~

Đặt cấu hình và controller trong package được ứng dụng Spring Boot quét. Ví dụ này cố ý dùng endpoint đơn giản để kết quả HTTP phản ánh rõ hành vi bảo mật, tránh phụ thuộc logic nghiệp vụ.

## 3. Gửi HTTP Basic header để kiểm tra xác thực

HTTP Basic dùng header có dạng:

~~~http
GET /api/private HTTP/1.1
Accept: application/json
Authorization: Basic YWxpY2U6c2VjcmV0
~~~

Chuỗi phía sau `Basic` là Base64 của `alice:secret`; **Base64 là encoding, không phải mã hóa bảo mật**. Mật khẩu trong Basic cần được bảo vệ bằng HTTPS khi chạy ngoài môi trường kiểm thử. Trong `MockMvc`, `httpBasic()` là cách gọn và ít lỗi để tạo header.

Ví dụ test dưới đây chạy với Spring Boot, JUnit Jupiter và `MockMvc` đã được tự động cấu hình. Các import quan trọng được viết đầy đủ để phân biệt request post-processor, request builder và result matcher:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HttpBasicAuthenticationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void correctCredentialsAreAuthenticatedByBasicFilter() throws Exception {
        mockMvc.perform(get("/api/private")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("alice", "secret")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:alice"))
            .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/api/private")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized())
            .andExpect(unauthenticated());
    }

    @Test
    void missingHeaderIsRejected() throws Exception {
        mockMvc.perform(get("/api/private")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(unauthenticated());
    }

    @Test
    void authenticatedUserWithoutAdminRoleGetsForbidden() throws Exception {
        mockMvc.perform(get("/api/admin")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("alice", "secret")))
            .andExpect(status().isForbidden())
            .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void adminMayAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin")
                .accept(MediaType.APPLICATION_JSON)
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-area"))
            .andExpect(authenticated().withUsername("admin"));
    }
}
~~~

`Accept: application/json` giúp ví dụ dùng HTTP Basic entry point trong cấu hình có cả form login: client API thường nhận **401** khi chưa xác thực thay vì chuyển hướng tới trang đăng nhập. Nếu ứng dụng có nhiều `SecurityFilterChain`, hãy xác minh request thực sự khớp chain chứa `httpBasic()`. Không nên mặc định rằng mọi endpoint bảo vệ đều trả về cùng một kiểu lỗi khi có form login.

### 3.1. Header thật và helper `httpBasic()` có khác nhau không?

Hai request sau truyền cùng một loại thông tin đến authentication filter:

~~~java
// Cách dễ đọc: spring-security-test tạo Authorization header.
mockMvc.perform(get("/api/private")
    .with(httpBasic("alice", "secret")));

// Cách kiểm tra wire format: tự tạo đúng header Basic.
String credentials = java.util.Base64.getEncoder().encodeToString(
    "alice:secret".getBytes(java.nio.charset.StandardCharsets.ISO_8859_1)
);

mockMvc.perform(get("/api/private")
    .header(org.springframework.http.HttpHeaders.AUTHORIZATION,
            "Basic " + credentials));
~~~

Trong cả hai trường hợp, `MockMvc` nhận request chứa header HTTP; không có lời gọi `with(user("alice"))`. Cách dựng tay hữu ích khi cần kiểm thử header thiếu prefix, Base64 sai định dạng, username/password chứa ký tự đặc biệt hoặc proxy đã chuyển tiếp header không đúng. Với luồng phổ biến, dùng `httpBasic()` để tránh lỗi tự mã hóa và giữ test dễ hiểu.

**Chú ý phân biệt 401 và 403:** Người dùng sai mật khẩu chưa tạo được danh tính hợp lệ nên thông thường nhận 401 qua Basic entry point. Người dùng đúng mật khẩu nhưng thiếu role cần thiết đã xác thực thành công, nên kiểm tra quyền có thể trả về 403. Nếu cả hai ca đều được thiết lập bằng `@WithMockUser`, bạn sẽ bỏ sót nhánh mật khẩu sai.

## 4. Gửi biểu mẫu đăng nhập qua `POST /login`

Form login khác HTTP Basic ở một số điểm quan trọng. Browser gửi username/password dưới dạng tham số HTTP POST tới `loginProcessingUrl`; `UsernamePasswordAuthenticationFilter` đọc tham số, yêu cầu xác thực và xử lý thành công/thất bại. Với cấu hình mặc định, thành công thường chuyển hướng tới trang đích, thất bại chuyển hướng về `/login?error`; trạng thái đăng nhập được duy trì qua session.

`spring-security-test` cung cấp request builder `formLogin()`:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;

mockMvc.perform(formLogin()
        .user("alice")
        .password("secret"))
    .andExpect(authenticated().withUsername("alice"));
~~~

Builder này tạo request đăng nhập tới `/login` với các parameter mặc định `username` và `password`, đồng thời chuẩn bị CSRF token hợp lệ cho request đăng nhập trong cấu hình mặc định. Việc kiểm thử đi qua Spring Security filter chain, tương tự browser gửi form.

### 4.1. Kiểm tra thành công, sai mật khẩu và session

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class FormAuthenticationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void successfulLoginIsPreservedAcrossSessionRequests() throws Exception {
        MvcResult login = mockMvc.perform(formLogin()
                .user("alice")
                .password("secret"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        // Request mới dùng session từ request login, không gắn mock user.
        mockMvc.perform(get("/web/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"))
            .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void incorrectFormPasswordRedirectsToLoginError() throws Exception {
        mockMvc.perform(formLogin()
                .user("alice")
                .password("wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }
}
~~~

Bài test thành công kiểm tra **hai giai đoạn độc lập**: request đầu tiên xác thực từ form parameters; request tiếp theo không gửi mật khẩu nữa nhưng vẫn truy cập được nhờ session. Lấy session từ `MvcResult` giúp tránh nhầm với một request MockMvc khác vốn không tự động mang cookie/session của request trước.

Chỉ kiểm tra `302` là chưa đủ: form thất bại cũng thường trả về `302`. Hãy kiểm tra thêm `authenticated()` hoặc `unauthenticated()`, nơi redirect và nội dung endpoint kế tiếp. Nếu ứng dụng cấu hình `defaultSuccessUrl`, `successHandler`, `failureUrl` hay `failureHandler` khác, kỳ vọng redirect phải khớp cấu hình thật.

### 4.2. POST tự dựng và CSRF

Một biểu mẫu được gửi bởi browser không tự nhiên có quyền vượt qua CSRF. Với CSRF mặc định của Spring Security, HTTP POST thay đổi trạng thái cần token hợp lệ. Ta nên có bài test xác nhận request thiếu token bị từ chối:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

@Test
void rawLoginPostRequiresCsrfToken() throws Exception {
    mockMvc.perform(post("/login")
            .param("username", "alice")
            .param("password", "secret"))
        .andExpect(status().isForbidden());

    mockMvc.perform(post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "secret"))
        .andExpect(authenticated().withUsername("alice"));
}
~~~

Lệnh `with(csrf())` tạo token CSRF hợp lệ cho request kiểm thử. Nó **không tạo người dùng**, không xác thực hộ và không thay thế mật khẩu. Nếu muốn kiểm thử CSRF âm tính rõ ràng hơn, có thể dùng `with(csrf().useInvalidToken())` rồi mong đợi 403.

Không nên thêm `.csrf(csrf -> csrf.disable())` vào cấu hình chỉ để giúp bài test login chạy xanh. Khi CSRF là yêu cầu của ứng dụng, tắt nó sẽ làm mất chính hành vi cần kiểm chứng. Ngược lại, nếu ứng dụng đã chủ đích bỏ qua CSRF cho những API stateless cụ thể, kỳ vọng trong test phải theo cấu hình đó, không áp 403 một cách máy móc.

## 5. Kiểm thử endpoint tùy biến thay cho `/login` mặc định

Trong ứng dụng thật, URL nhận form, tên trường và trang đăng nhập có thể khác mặc định. Chẳng hạn:

~~~java
http.formLogin(form -> form
    .loginPage("/signin")
    .loginProcessingUrl("/signin")
    .usernameParameter("email")
    .passwordParameter("passcode")
    .permitAll()
);
~~~

Khi đó, request kiểm thử phải gửi tới đúng URL và đúng parameter name:

~~~java
mockMvc.perform(formLogin("/signin")
        .user("email", "alice")
        .password("passcode", "secret"))
    .andExpect(authenticated().withUsername("alice"));
~~~

`loginProcessingUrl` mới là URL mà login filter xử lý khi gửi thông tin đăng nhập. `loginPage` chỉ quy định trang GET hiển thị form; nếu tự cấu hình trang này, ứng dụng cũng phải cung cấp trang hoặc controller tương ứng. Đừng nhầm kiểm tra `GET /signin` trả HTML với kiểm tra `POST /signin` có xác thực đúng hay không.

Khi thay đổi cấu hình, hãy kiểm tra cả lỗi phổ biến:

- POST đến URL cũ `/login` không còn đi qua đúng login filter.
- Tên trường không khớp (`email` và `passcode` thay cho `username`/`password`), dẫn tới xác thực thất bại dù giá trị mật khẩu đúng.
- Login thành công nhưng `successHandler` hoặc cookie/session strategy làm request sau không giữ được danh tính.
- Cấu hình request matcher đặt trước khiến endpoint login bị chặn hoặc lọt sang filter chain khác.

## 6. Đọc đúng tín hiệu từ phản hồi HTTP

Một test đáng tin cần quan sát cả **trạng thái xác thực** lẫn **trạng thái HTTP**. Hai thứ không phải lúc nào tương đương một-một: 403 còn có thể đến từ CSRF; 302 có thể là cả login thành công lẫn thất bại.

| Request trong cấu hình ví dụ | Kỳ vọng | Giải thích |
| --- | --- | --- |
| `GET /api/private`, không có header, `Accept: application/json` | **401** | Chưa có thông tin xác thực |
| `GET /api/private`, Basic `alice:wrong` | **401** | Sai mật khẩu, chưa xác thực |
| `GET /api/private`, Basic `alice:secret` | **200** | Xác thực đúng và đủ điều kiện |
| `GET /api/admin`, Basic `alice:secret` | **403** | Alice đã đăng nhập nhưng thiếu `ROLE_ADMIN` |
| `GET /api/admin`, Basic `admin:admin-pass` | **200** | Đủ quyền `ADMIN` |
| `POST /login`, sai mật khẩu nhưng CSRF hợp lệ | **302** tới `/login?error` | Form login dùng failure handler chuyển hướng |
| `POST /login`, đúng mật khẩu và CSRF hợp lệ | **302** tới đích thành công | Đăng nhập xong, session có thể được lưu |
| `POST /login` tự dựng, thiếu CSRF | **403** | CSRF filter từ chối trước khi xử lý đăng nhập |
| `GET /web/profile` dùng session từ login thành công | **200** | Xác thực được duy trì qua request tiếp theo |

Những kết quả này phụ thuộc vào **cấu hình mẫu**. Ví dụ, một REST API dùng JSON failure handler có thể trả 401 thay cho 302 khi sai form password; ứng dụng bật `oauth2ResourceServer()` có thể trả `WWW-Authenticate: Bearer ...`; hệ thống dùng `exceptionHandling()` tùy biến có thể chuyển hướng theo cách khác. Hãy lấy hành vi mà ứng dụng cam kết làm assertion.

Đối với HTTP Basic, cũng có thể kiểm tra challenge header:

~~~java
mockMvc.perform(get("/api/private")
        .accept(org.springframework.http.MediaType.APPLICATION_JSON))
    .andExpect(status().isUnauthorized())
    .andExpect(header().exists(
        org.springframework.http.HttpHeaders.WWW_AUTHENTICATE
    ));
~~~

Assertion này đặc biệt hữu ích khi kiểm tra API có yêu cầu client cung cấp credentials, nhưng giá trị/realm cụ thể của `WWW-Authenticate` phải dựa trên cấu hình entry point của ứng dụng.

## 7. Vì sao test với `@WithMockUser` vẫn cần được giữ lại?

Không nên loại bỏ toàn bộ test dùng mock principal. Chúng phục vụ một tầng khác trong chiến lược kiểm thử:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void userCannotOpenAdminPage() throws Exception {
    mockMvc.perform(get("/api/admin"))
        .andExpect(status().isForbidden());
}
~~~

Test này đặt câu hỏi: “Một người dùng có `ROLE_USER` có bị chặn khỏi tài nguyên của `ADMIN` không?” Nó không cần phụ thuộc mật khẩu, login form, header hay cấu hình UserDetailsService. Vì vậy, nó chạy nhanh và tập trung cho các phép thử quyền truy cập.

Trong khi đó:

~~~java
@Test
void wrongPasswordDoesNotCreateAuthenticatedUser() throws Exception {
    mockMvc.perform(get("/api/private")
            .accept(MediaType.APPLICATION_JSON)
            .with(httpBasic("alice", "incorrect")))
        .andExpect(status().isUnauthorized())
        .andExpect(unauthenticated());
}
~~~

Test thứ hai trả lời một câu hỏi khác: “Spring Security có thực sự từ chối thông tin đăng nhập không hợp lệ khi client gửi nó qua giao thức HTTP?” Đây là điều `@WithMockUser` không thể chứng minh.

Một bộ kiểm thử hợp lý thường kết hợp:

1. **Unit/service tests:** kiểm tra logic riêng của `UserDetailsService`, cấu hình dữ liệu người dùng hoặc quy tắc nghiệp vụ.
2. **Authorization tests:** dùng `@WithMockUser`, `with(user(...))`, `with(jwt())` để kiểm tra quyền nhanh, tường minh và độc lập với cơ chế đăng nhập.
3. **HTTP authentication tests:** dùng `httpBasic()`, `formLogin()` hoặc header Bearer thật để kiểm tra lọc request, xử lý thông tin đăng nhập, kết quả thành công/thất bại và session.
4. **End-to-end tests (nếu cần):** chạy server và tích hợp thực với cookie, proxy, TLS hoặc IdP để xác nhận những yếu tố ngoài phạm vi `MockMvc`.

## 8. Những lỗi khiến bài test trông đúng nhưng bỏ qua Security

### 8.1. Chưa gắn Spring Security filter chain vào `MockMvc`

Trong ứng dụng Boot thông thường, `@SpringBootTest` + `@AutoConfigureMockMvc` sẽ đăng ký các Servlet filters phù hợp. Nếu dựng `MockMvc` thủ công, cần tích hợp Spring Security:

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
~~~

Chỉ gọi `MockMvcBuilders.standaloneSetup(controller)` mà không thêm bộ lọc tương ứng có thể khiến controller được gọi trực tiếp, bỏ qua xác thực HTTP. Tương tự, `@AutoConfigureMockMvc(addFilters = false)` làm mất giá trị của test filter-based authentication. Một phép kiểm tra an toàn tối thiểu là: cùng endpoint đó phải **từ chối request không có thông tin đăng nhập**.

### 8.2. Trộn danh tính giả lập với phép thử mật khẩu

Ví dụ dưới đây không kiểm tra sai mật khẩu:

~~~java
mockMvc.perform(get("/api/private")
        .with(user("alice"))
        .header("Authorization", "Basic credentials-sai"))
    .andExpect(status().isOk()); // Không có giá trị chứng minh cơ chế xác thực
~~~

Danh tính do `user("alice")` tạo làm kết quả khó diễn giải. Khi kiểm thử Basic/form thật, hãy để header hoặc form là nguồn xác thực duy nhất trong request; khi kiểm thử authorization, dùng principal giả lập có chủ đích.

### 8.3. Nhầm đăng nhập thành công với HTTP 200

`POST /login` thành công theo mặc định thường trả **302 redirect**, không trả 200. Test cố đòi 200 dễ dẫn đến việc thay đổi handler hoặc cấu hình sai mục đích. Thay vào đó, xác minh kết quả xác thực và đường redirect/response như hợp đồng của ứng dụng.

### 8.4. Giả định session tự đi theo nhiều lệnh `perform()`

Hai lần gọi `mockMvc.perform(...)` là hai request; chúng không tự động là cùng một browser session. Với form login, hãy lấy `MockHttpSession` từ response login rồi truyền nó vào request tiếp theo. Với HTTP Basic, thông thường client gửi lại header ở mỗi request; đừng suy diễn thành cơ chế đăng nhập giữ session giống hệt form login.

### 8.5. Cấu hình sai filter chain hoặc tắt security trong test

Với nhiều `SecurityFilterChain`, thứ tự matcher quyết định request được xử lý bởi chain nào. Nếu test `/api/private` dùng chain chỉ cấu hình form login, một request không có header có thể nhận 302 thay vì 401. Nếu môi trường test dùng cấu hình khác production, kiểm tra đúng các bean và profile thực sự được khởi tạo. Không nên “sửa” assertion bằng cách thay ngẫu nhiên mã trạng thái để test xanh.

### 8.6. Nhầm “header Bearer” với “JWT đã được giải mã thật”

`with(jwt())` hoặc `with(oauth2Login())` của `spring-security-test` giúp giả lập authentication cho phép thử quyền, tương tự `with(user())`. Nếu bài test cần xác nhận `BearerTokenAuthenticationFilter` đọc header thật và `JwtDecoder` xử lý token, phải gửi header `Authorization: Bearer ...` và cấu hình decoder/resource server phù hợp. Không nên tuyên bố đã kiểm tra chữ ký JWT chỉ vì test `with(jwt())` thành công. Đây là cùng nguyên tắc phân lớp như HTTP Basic và form login.

## 9. Thiết kế bộ ca kiểm thử có ý nghĩa

Thay vì chỉ có một “happy path”, có thể chọn các ca dựa vào rủi ro của từng cơ chế:

| Phạm vi | Ca tích cực | Ca tiêu cực | Bằng chứng nên assert |
| --- | --- | --- | --- |
| HTTP Basic | Đúng user/password | Sai password, thiếu header, header hỏng | 200/401, `authenticated()`, challenge header |
| Phân quyền sau Basic | Người có `ADMIN` truy cập `/api/admin` | Người chỉ có `USER` | 200/403, role/danh tính |
| Form login | Đúng username/password + CSRF | Sai password, sai parameter name | Authenticated/unauthenticated, redirect |
| CSRF | POST hợp lệ có token | POST thiếu hoặc sai token | Thành công/403 |
| Session | Request tiếp theo dùng session đăng nhập | Request không mang session | 200 hoặc bị yêu cầu đăng nhập |
| Cấu hình nhiều chain | Request vào đúng chain Basic/form | Sai URL hoặc chain matcher | Entry point và trạng thái đúng |

Thực hiện các ca với tài khoản kiểm thử ổn định, mật khẩu được mã hóa theo cấu hình thật và dữ liệu không phụ thuộc thứ tự chạy test. Khi có custom authentication provider, có thể dùng provider hoặc fixture kiểm thử có kiểm soát, nhưng phải đảm bảo phép thử vẫn gọi qua cơ chế xác thực đã chọn.

**Tiêu chí hoàn thành cho bài thực hành:** Một request không có thông tin đăng nhập bị chặn; Basic header đúng được chấp nhận và sai bị từ chối; form login thành công có thể duy trì session; mật khẩu sai không tạo người dùng đã xác thực; thiếu CSRF của POST theo mặc định bị chặn; và người đăng nhập thành công vẫn bị 403 khi thiếu quyền. Đó là các bằng chứng cụ thể cho việc ứng dụng thực sự kiểm tra thông tin xác thực HTTP, thay vì nhận sẵn một người dùng trong `SecurityContext`.
