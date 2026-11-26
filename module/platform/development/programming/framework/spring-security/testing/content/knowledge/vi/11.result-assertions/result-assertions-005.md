# Kiểm chứng `unauthenticated()` sau đăng nhập sai hoặc đăng xuất

## 1. Mục tiêu và ý nghĩa bảo mật

Trong ứng dụng dùng Spring Security, một lần đăng nhập thất bại không được tạo danh tính đã xác thực; một lần đăng xuất thành công phải làm mất khả năng sử dụng phiên đăng nhập đã kết thúc. Đây là hai tình huống cần kiểm thử **trạng thái bảo mật** bên cạnh mã HTTP hay trang đích.

Trong phạm vi kiểm thử Spring Security:

- **Đăng nhập sai:** gửi thông tin đăng nhập không hợp lệ và xác nhận yêu cầu không nhận được người dùng đã xác thực.
- **Đăng xuất:** tạo một phiên đã đăng nhập thật, gọi endpoint đăng xuất, xác nhận authentication được xóa, phiên cũ bị vô hiệu hóa theo cấu hình, rồi thử truy cập lại tài nguyên được bảo vệ.
- **Servlet:** dùng `MockMvc` và `SecurityMockMvcResultMatchers.unauthenticated()` để khẳng định trạng thái xác thực của kết quả một yêu cầu.
- **Reactive:** dùng `WebTestClient` và yêu cầu tiếp theo đến endpoint bảo vệ để kiểm tra trạng thái không có quyền truy cập; không lấy matcher dành riêng cho MockMvc áp dụng sang WebFlux.

Hai thao tác cần phân biệt: *authentication* xác định người dùng là ai, còn *authorization* quyết định người dùng được làm gì. Một người đã đăng nhập nhưng thiếu vai trò thường nhận **403 Forbidden**; người chưa được xác thực có thể nhận **401 Unauthorized** với API, hoặc **302 Redirect** đến trang login với ứng dụng web dùng form. Do đó, không thể coi riêng mã `401`, `403` hoặc `302` là bằng chứng đầy đủ cho trạng thái `unauthenticated`.

## 2. Đọc đúng kết quả `unauthenticated()`

`spring-security-test` cung cấp matcher:

~~~java
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
~~~

Matcher này kiểm tra **không có người dùng được xác thực trong kết quả `MockMvc`**. Nó phù hợp để khẳng định login thất bại và logout đã xóa authentication. Nó không phải hàm để đăng xuất, không tự hủy session, không thu hồi JWT và không kiểm tra mọi lần truy cập tương lai.

Ví dụ cốt lõi theo tài liệu Spring Security:

~~~java
mockMvc.perform(formLogin().user("learner").password("wrong"))
       .andExpect(unauthenticated());
~~~

Trong thực tế nên ghép các loại khẳng định:

| Khẳng định | Chứng minh | Không tự chứng minh |
| --- | --- | --- |
| `unauthenticated()` | Kết quả yêu cầu MockMvc không gắn với người dùng đã xác thực | Session cũ đã bị hủy; token đã bị thu hồi |
| `status().is3xxRedirection()` | Máy chủ yêu cầu trình duyệt chuyển hướng | Đã login/logout đúng |
| `status().isUnauthorized()` | Yêu cầu HTTP bị từ chối bằng 401 | Logout của một session cũ đã diễn ra |
| `status().isForbidden()` | Yêu cầu bị từ chối bằng 403 | Người dùng là anonymous; có thể đang đăng nhập nhưng thiếu quyền hoặc thiếu CSRF |
| Truy cập lại endpoint bảo vệ | Quy tắc bảo vệ vẫn được thực thi ở yêu cầu sau | Phiên đã bị xóa khỏi mọi kho lưu trữ, nếu không kiểm tra thêm |

**Lưu ý về anonymous authentication:** Spring Security có thể tạo `AnonymousAuthenticationToken` để đại diện người truy cập vô danh. Vì thế không nên suy luận đơn giản từ `Authentication#isAuthenticated()` hay từ việc đối tượng `Authentication` khác `null` rằng đó là người dùng đã đăng nhập thật. Hãy dùng matcher của Spring Security hoặc `AuthenticationTrustResolver` theo ngữ cảnh.

## 3. Bối cảnh chạy ví dụ Servlet với form login

Giả sử ứng dụng Servlet có:

- Tài khoản thử nghiệm `learner` / `correct-password` với vai trò `USER`.
- Endpoint `GET /private` yêu cầu đã xác thực.
- Form login mặc định xử lý `POST /login`; login sai chuyển đến `/login?error`.
- Logout mặc định xử lý `POST /logout` khi CSRF được bật; thành công chuyển đến `/login?logout`.

Một cấu hình minh họa bằng Spring Security hiện đại:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("correct-password"))
                .roles("USER")
                .build());
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}

@RestController
class PrivateController {
    @GetMapping("/private")
    String privateContent(Authentication authentication) {
        return "Hello " + authentication.getName();
    }
}
~~~

Các import chính nằm trong `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.annotation.web.configuration.EnableWebSecurity`, `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.core.userdetails.*`, `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder` và Spring Web MVC. Ví dụ sử dụng `Customizer.withDefaults()` từ `org.springframework.security.config.Customizer`.

Trong dự án Spring Boot, khai báo starter web, starter security và dependency kiểm thử Spring Security:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Các đoạn kiểm thử sau chạy trong test tích hợp với security filter chain thật của ứng dụng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationStateTests {
    @Autowired
    MockMvc mockMvc;

    // Các phương thức @Test ở các mục tiếp theo.
}
~~~

Khi dùng `MockMvcBuilders.webAppContextSetup(...)` thủ công thay cho `@AutoConfigureMockMvc`, cần tích hợp `springSecurity()`. Nếu bỏ security filter chain, phép thử có thể không đi qua cơ chế bảo mật cần kiểm tra.

## 4. Đăng nhập sai: yêu cầu phải không xác thực

### 4.1. Kiểm thử login thất bại

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@Test
void wrongPasswordShouldLeaveRequestUnauthenticated() throws Exception {
    mockMvc.perform(formLogin()
                    .user("learner")
                    .password("wrong-password"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/login?error"))
           .andExpect(unauthenticated());
}
~~~

**Diễn giải từng phép kiểm tra:**

1. `formLogin()` dựng yêu cầu `POST /login` với tham số `username`, `password` và CSRF token hợp lệ cho test.
2. Mật khẩu sai phải đi qua nhánh xác thực thất bại. Với cấu hình form login mặc định, failure handler trả redirect đến `/login?error`.
3. `unauthenticated()` khẳng định không có danh tính đã xác thực trong kết quả yêu cầu; riêng redirect chưa nói được điều đó.

Test có thể đi kèm ca đối chứng thành công:

~~~java
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;

@Test
void correctPasswordShouldAuthenticate() throws Exception {
    mockMvc.perform(formLogin()
                    .user("learner")
                    .password("correct-password"))
           .andExpect(status().is3xxRedirection())
           .andExpect(authenticated().withUsername("learner"));
}
~~~

Đối chứng giúp phát hiện test đăng nhập sai “đậu” chỉ vì endpoint `/login` chưa được cấu hình hoặc mọi lần đăng nhập đều thất bại. Trong tình huống đó, ca xác thực đúng sẽ thất bại và chỉ rõ lỗi hệ thống.

### 4.2. Kiểm tra truy cập ở yêu cầu kế tiếp

~~~java
@Test
void anonymousClientCannotAccessPrivateEndpoint() throws Exception {
    mockMvc.perform(get("/private"))
           .andExpect(status().is3xxRedirection());
}
~~~

Đây là một yêu cầu mới, không có session đã đăng nhập. Với **form login** mặc định, client được chuyển đến trang đăng nhập; với API cấu hình HTTP Basic hoặc Bearer Token, kết quả dự kiến thường là `401`. Cần khớp assertion với `AuthenticationEntryPoint` thực tế.

**Giới hạn cần nhớ:** đăng nhập sai trong một request không mặc nhiên có nghĩa *mọi session đăng nhập trước đó của cùng tài khoản* đều mất hiệu lực. Test ở mục này bắt đầu không có session đã xác thực; nếu yêu cầu nghiệp vụ là khóa phiên sau một lần nhập sai, phải thiết kế chính sách riêng và viết test cho chính sách ấy.

## 5. Đăng xuất: chứng minh phiên đăng nhập không còn hiệu lực

Để kiểm thử logout thực sự, phải đi theo chuỗi **login thành công → dùng session vừa tạo để logout → kiểm tra session và quyền truy cập sau logout**. Chỉ gọi `logout()` khi chưa đăng nhập là kiểm tra tuyến logout có thể được gọi, chưa chứng minh phiên đăng nhập đã bị thu hồi.

### 5.1. Logout cùng session đã xác thực

~~~java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.*;

@Test
void logoutShouldInvalidateAuthenticatedSession() throws Exception {
    // Bước 1: tạo phiên thật qua luồng form login.
    MvcResult login = mockMvc.perform(formLogin()
                    .user("learner")
                    .password("correct-password"))
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

    MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
    assertNotNull(session, "Form login thành công phải tạo session");

    // Bước 2: xác nhận session hiện truy cập được tài nguyên bảo vệ.
    mockMvc.perform(get("/private").session(session))
           .andExpect(status().isOk())
           .andExpect(content().string("Hello learner"));

    // Bước 3: POST logout với CÙNG session và CSRF hợp lệ.
    mockMvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/login?logout"))
           .andExpect(unauthenticated());

    // Bước 4: phiên cũ đã bị vô hiệu hóa.
    assertTrue(session.isInvalid());

    // Bước 5: client không có phiên đăng nhập không còn truy cập được.
    mockMvc.perform(get("/private"))
           .andExpect(status().is3xxRedirection());
}
~~~

Ở đây dùng `post("/logout").session(session).with(csrf())` vì cần gắn đúng `MockHttpSession` đã lấy từ login. Helper `logout()` của Spring Security Test rất hữu ích để tạo POST logout kèm CSRF, nhưng helper đó không có phương thức `session(...)`. Khi logout được cấu hình mặc định, `SecurityContextLogoutHandler` xóa authentication và vô hiệu hóa HTTP session; `MockHttpSession#isInvalid()` kiểm chứng việc vô hiệu hóa đó.

Với ứng dụng thay đổi `logoutSuccessUrl`, endpoint logout hoặc cơ chế session, hãy điều chỉnh chính xác URL/assertion. Với hệ thống có khả năng truy xuất session ở nhiều node, kiểm thử tích hợp còn phải kiểm tra kho session thực tế hoặc phiên được tái gửi theo cơ chế client/server tương ứng.

### 5.2. Phép thử âm: thiếu CSRF thì không được logout

~~~java
@Test
void logoutWithoutCsrfShouldNotDestroySession() throws Exception {
    MvcResult login = mockMvc.perform(formLogin()
                    .user("learner")
                    .password("correct-password"))
            .andExpect(authenticated())
            .andReturn();

    MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
    assertNotNull(session);

    mockMvc.perform(post("/logout").session(session)) // không gửi CSRF
           .andExpect(status().isForbidden());

    assertFalse(session.isInvalid());
    mockMvc.perform(get("/private").session(session))
           .andExpect(status().isOk());
}
~~~

Test này xác nhận CSRF filter chặn yêu cầu trước khi logout handler chạy. **403 ở đây không có nghĩa người dùng đã bị đăng xuất**; thực tế session vẫn còn đăng nhập. Nếu ứng dụng đã tắt CSRF có chủ đích, ca này cần được viết lại theo hợp đồng bảo mật đang áp dụng.

### 5.3. Helper logout ngắn gọn

Khi chỉ cần xác minh matcher trên một yêu cầu, Spring Security Test cung cấp:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.logout;

mockMvc.perform(logout())
       .andExpect(status().is3xxRedirection())
       .andExpect(unauthenticated());
~~~

`logout()` mặc định tạo POST `/logout` với CSRF hợp lệ. Nó hữu ích cho một test tuyến logout, nhưng bài toán “phiên từng đăng nhập bị vô hiệu hóa” vẫn cần chuỗi kiểm thử có session thật như mục 5.1.

## 6. Môi trường Reactive: kiểm thử bằng `WebTestClient`

WebFlux sử dụng `WebFilterChainProxy`, `ReactiveSecurityContextHolder` và thường là `WebSession`. Không dùng `MockMvc` hoặc `unauthenticated()` của Servlet để kiểm tra trực tiếp WebFlux. Tương ứng, có thể kiểm tra request bị từ chối và request tiếp theo không nhận được authentication từ session/token đã hết hiệu lực.

### 6.1. Một ca Reactive API dùng HTTP Basic

Với `SecurityWebFilterChain` cho endpoint `/private` yêu cầu xác thực và bật `httpBasic`, kiểm tra thông tin đăng nhập sai như sau:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveAuthenticationTests {
    @Autowired
    WebTestClient client;

    @Test
    void invalidBasicCredentialsAreRejected() {
        client.get()
              .uri("/private")
              .headers(h -> h.setBasicAuth("learner", "wrong-password"))
              .exchange()
              .expectStatus().isUnauthorized();

        client.get()
              .uri("/private")
              .exchange()
              .expectStatus().isUnauthorized();
    }
}
~~~

HTTP Basic xác thực **mỗi yêu cầu**. Vì vậy không có phiên form login được tạo để logout ở ví dụ này. Hai phép kiểm tra xác nhận credentials sai và request không có credentials đều không được truy cập. Hãy thay `401` nếu security chain dùng entry point khác.

Nếu tự tạo client gắn vào `ApplicationContext`, nhớ áp dụng hỗ trợ Spring Security:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
~~~

### 6.2. Reactive form login/logout theo phiên

Với WebFlux form login, các bước phải kiểm tra là:

1. Gửi `POST /login` với username/password đúng và CSRF token hợp lệ; lưu cookie session trả về (thường tên `SESSION`, có thể được tùy biến).
2. Dùng cookie ấy để gọi endpoint bảo vệ, phải được truy cập.
3. Gửi `POST /logout` với **cùng cookie** và CSRF hợp lệ.
4. Dùng lại thông tin phiên phía client theo hành vi ứng dụng; endpoint bảo vệ phải yêu cầu đăng nhập trở lại. Kiểm tra cookie/session server nếu hợp đồng logout yêu cầu invalidation, và xác nhận logout sai CSRF không thành công.

Để tạo CSRF token trong kiểm thử client gắn với mock server, Spring Security Test hỗ trợ:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
      .post()
      .uri("/logout")
      // Bổ sung cookie session đã lấy từ lần login thành công.
      .exchange()
      .expectStatus().is3xxRedirection();
~~~

Đoạn trên chỉ minh họa cách thêm CSRF; để chứng minh logout, **phải gửi cookie phiên đã đăng nhập** và gọi tiếp endpoint bảo vệ. Không áp đặt kết quả `401` nếu ứng dụng Reactive form login trả `302` đến trang đăng nhập. Cũng không mặc định WebFlux luôn hủy toàn bộ `WebSession`: kết quả phụ thuộc logout handler và security-context repository đã cấu hình.

`mockUser()`, `mockJwt()` hay `@WithMockUser` có thể tạo danh tính giả cho **một lượt kiểm thử**, nhưng chúng không xác nhận cookie đăng nhập thật đã hết giá trị sau logout.

## 7. JWT, OAuth2 và OIDC: điều gì thay đổi?

Spring Security Test hỗ trợ `jwt()`, `oauth2Login()`, `oidcLogin()` (Servlet) và các mutator tương ứng cho Reactive. Chúng thuận tiện để kiểm tra quyền trên endpoint khi đã giả lập authentication, nhưng khác với kiểm thử xử lý login/logout thực tế.

| Cơ chế | Đối tượng cần kiểm tra sau đăng nhập sai / logout | Cần thận trọng |
| --- | --- | --- |
| Form login + HTTP session | SecurityContext, session ID, endpoint bảo vệ sau logout | Dùng đúng session của lần login trước |
| HTTP Basic | Yêu cầu thiếu/sai Authorization bị từ chối | Không có phiên logout phía server theo mặc định |
| JWT Bearer stateless | Yêu cầu không token/sai token/hết hạn bị từ chối | Endpoint `/logout` không tự vô hiệu hóa JWT đã ký và còn hạn |
| OAuth2/OIDC login | Phiên đăng nhập local, OIDC/OAuth2 session và logout flow đã cấu hình | Local logout không mặc nhiên đăng xuất tại Identity Provider |

Ví dụ kiểm tra **API Bearer** qua MockMvc:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

@Test
void missingBearerTokenCannotAccessProtectedApi() throws Exception {
    mockMvc.perform(get("/api/private").with(jwt()))
           .andExpect(status().isOk())
           .andExpect(authenticated());

    mockMvc.perform(get("/api/private"))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated());
}
~~~

Đoạn này giả định `/api/private` được bảo vệ bằng resource-server JWT và không cần thêm quyền ngoài việc đã xác thực. `jwt()` chèn `JwtAuthenticationToken` giả cho test, **không gọi decoder hoặc kiểm tra chữ ký**. Để kiểm chứng token sai chữ ký, token hết hạn hoặc token bị thu hồi, cần gửi Bearer token thực qua filter chain có decoder/validator/revocation strategy phù hợp. Với OIDC, muốn xác thực đăng xuất một lần trên nhiều hệ thống thì phải kiểm thử cả giao thức logout với nhà cung cấp danh tính.

## 8. Lỗi thường gặp và cách tránh

| Lỗi | Vì sao nguy hiểm | Cách kiểm thử đúng |
| --- | --- | --- |
| Chỉ `andExpect(status().is3xxRedirection())` sau login sai | 302 cũng có thể đến từ trang lỗi hay điều hướng khác | Thêm URL đích và `unauthenticated()` |
| Chỉ gọi `logout()` khi chưa login | Không có session trước đó để chứng minh đã bị hủy | Login thành công, lưu session, logout bằng chính session ấy |
| Logout không có CSRF và nhầm 403 là logout thành công | Logout handler chưa chạy | Dùng `with(csrf())` cho ca logout thành công; viết ca 403 riêng |
| Dùng `@WithMockUser` trên test cần kiểm chứng guest | Authentication mock có thể che lỗi bảo vệ endpoint | Gửi yêu cầu không gắn principal giả |
| Gọi `SecurityContextHolder.getContext()` sau `mockMvc.perform(...)` | Context thường được dọn ở cuối request, nên không đại diện đầy đủ cho phản hồi trước đó | Dùng matcher trên `MvcResult` và thêm test session/endpoint |
| Kiểm tra quyền với `with(user(...))` rồi kết luận form login hoạt động | `user(...)` bỏ qua xác minh mật khẩu thật | Dùng `formLogin()` để đi qua authentication flow |
| Dùng `jwt()` rồi kết luận token được ký hợp lệ hoặc đã bị thu hồi | `jwt()` giả lập JWT authentication | Test decoder/validator và API với Bearer token thật |
| Ép mọi unauthorized thành `401` | Form login thường redirect; thiếu quyền và thiếu CSRF thường là 403 | Đối chiếu entry point và cấu hình từng security filter chain |
| Dùng lại `MockHttpSession` đã bị invalidate cho request mới | Có thể phát sinh lỗi từ mock session thay vì phản ánh đúng client | Khẳng định `isInvalid()` rồi kiểm tra request guest mới hoặc dùng client tích hợp cookie |

## 9. Bộ ca kiểm thử khuyến nghị

| Tình huống | Điều kiện đầu | Kết quả mong đợi |
| --- | --- | --- |
| Mật khẩu sai | Chưa đăng nhập, username tồn tại | Login thất bại, `unauthenticated()`, không truy cập tài nguyên riêng tư |
| Username không tồn tại | Chưa đăng nhập | Thất bại như mật khẩu sai, không rò rỉ thông tin tài khoản |
| Mật khẩu đúng | Tài khoản hợp lệ | `authenticated().withUsername(...)`, truy cập endpoint bảo vệ |
| Logout hợp lệ | Đang có session đã login | Authentication bị xóa, session bị invalidate theo hợp đồng, tài nguyên bảo vệ không còn truy cập |
| Logout thiếu CSRF | Đang login, CSRF bật | 403; session còn hoạt động |
| API không gửi Bearer | Resource server bảo vệ endpoint | 401 và không được truy cập |
| JWT hết hạn/không hợp lệ | Resource server có validator | 401 qua đường đi xác thực token thật |
| Người đã đăng nhập nhưng thiếu vai trò | Principal hợp lệ, authority không đủ | 403 (phân quyền), không được hiểu là guest |

Một test bảo mật đáng tin cần gắn kết **nguyên nhân** (thông tin login sai hoặc logout đúng), **trạng thái** (`unauthenticated` hoặc session không còn hiệu lực) và **hậu quả** (tài nguyên được bảo vệ không thể truy cập). Các phép kiểm tra này bổ sung cho nhau.

## 10. Tài liệu tham khảo chính thức

- [Spring Security — SecurityMockMvcResultMatchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): `authenticated()` và `unauthenticated()`.
- [Spring Security — SecurityMockMvcRequestBuilders](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestBuilders.html): `formLogin()` và `logout()`.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout handler, SecurityContext và session.
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): gắn security vào WebTestClient.
- [Spring Security — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): test yêu cầu không có principal.
- [Spring Security — Reactive Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): CSRF cho `WebTestClient`.
