# Giả lập người dùng khác với chạy quy trình đăng nhập thật

## Mục tiêu học tập

Trong kiểm thử Spring Security, bạn thường thấy hai cách chuẩn bị danh tính: gắn sẵn một người dùng giả lập vào `SecurityContext`, hoặc gửi credential/token để ứng dụng thực hiện quy trình xác thực. Hai cách đều hữu ích, nhưng chúng chứng minh những điều khác nhau.

Sau bài này, bạn có thể:

- Phân biệt `@WithMockUser`, `user()`, `jwt()`, `oauth2Login()` và `oidcLogin()` với việc gửi mật khẩu, session cookie hoặc bearer token thật qua request.
- Giải thích `SecurityContext` giả lập bỏ qua những bước nào của quy trình đăng nhập.
- Viết kiểm thử HTTP Basic, form login và session bằng `MockMvc`.
- Kiểm tra bearer token qua resource server và hiểu giới hạn của JWT mock.
- Phân biệt OAuth2/OIDC principal giả lập với authorization code flow thực tế.
- Áp dụng cùng nguyên tắc cho Servlet và Reactive bằng `MockMvc` và `WebTestClient`.
- Chọn đúng loại test cho câu hỏi cần trả lời: “người này có quyền không?” hay “server có xác minh đúng bằng chứng đăng nhập không?”.

Module **SPRING_SECURITY_TESTING** dùng `spring-security-test` để kiểm chứng xác thực, phân quyền và bảo vệ HTTP trong ứng dụng Servlet và Reactive. Bài này tập trung vào một ranh giới rất quan trọng: **danh tính được tạo sẵn trong test** và **danh tính được server xác minh từ credential/token**.

## 1. Hai cách tạo trạng thái đăng nhập

Giả sử ứng dụng có endpoint `GET /api/me`. Endpoint chỉ trả thông tin khi người gọi đã xác thực.

Một test có thể đặt sẵn người dùng:

~~~java
mvc.perform(get("/api/me")
        .with(user("linh").roles("USER")))
    .andExpect(status().isOk());
~~~

Hoặc gửi username/password:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("linh", "mat-khau-test")))
    .andExpect(status().isOk());
~~~

Cả hai request có thể nhận `200 OK`, nhưng đường đi khác nhau:

- `user("linh").roles("USER")` gắn một `Authentication` đã xác thực vào ngữ cảnh của request. Nó giúp thử các quy tắc phân quyền phía sau.
- `httpBasic("linh", "mat-khau-test")` tạo header `Authorization: Basic ...`. Request đi qua filter xác thực HTTP Basic, `AuthenticationManager` và provider để kiểm tra thông tin đăng nhập theo cấu hình ứng dụng.

Ở cách thứ nhất, bài test **không chứng minh** mật khẩu của `linh` đúng. Ở cách thứ hai, nếu test context dùng cấu hình xác thực thật và kho người dùng được cấu hình đúng, nó có thể chứng minh mật khẩu đúng/sai được xử lý như mong đợi.

### 1.1. Sơ đồ hai đường đi

~~~mermaid
flowchart TD
    A["Test với user() / @WithMockUser"] --> B["Tạo Authentication giả lập"]
    B --> C["SecurityContext"]
    C --> D["Authorization / Controller / Service"]

    E["Test gửi username + password"] --> F["HTTP Authorization hoặc POST /login"]
    F --> G["Authentication Filter"]
    G --> H["AuthenticationManager / Provider"]
    H --> I{"Credential hợp lệ?"}
    I -->|Không| J["Authentication failure"]
    I -->|Có| K["Authentication từ provider"]
    K --> L["SecurityContext / Session"]
    L --> D
~~~

Sơ đồ cho thấy mock user bắt đầu từ trạng thái đã xác thực. Đường đăng nhập thật phải đi qua bước xác minh credential trước khi ứng dụng có thể tin cậy danh tính.

## 2. Các tiện ích giả lập của spring-security-test làm gì?

`spring-security-test` cung cấp các công cụ giúp test nhanh và có thể kiểm soát danh tính. Chúng đặc biệt hữu ích khi mục tiêu là kiểm tra **phân quyền** hoặc logic ứng dụng sau đăng nhập.

| Tiện ích | Cách sử dụng điển hình | Điều được giả lập | Điều không tự kiểm tra |
| --- | --- | --- | --- |
| `@WithMockUser` | Gắn vào test method/class | User, username, roles/authorities đã xác thực | Mật khẩu, login form, session fixation, token signature |
| `user()` | `.with(user("linh").roles("USER"))` trong MockMvc | Principal và authorities cho request | `UserDetailsService` có tìm user không, password có đúng không |
| `@WithUserDetails` | Gắn vào test method | User được tải từ `UserDetailsService` trong test context | Request login và xác minh mật khẩu |
| `@WithSecurityContext` | Annotation tùy chỉnh | `SecurityContext` theo factory riêng | Quy trình xác thực credential thực tế |
| `jwt()` | `.with(jwt())` trong MockMvc | JWT authentication và claims/authorities giả lập | Chữ ký, issuer, audience, thời hạn của token gửi từ client |
| `opaqueToken()` | MockMvc request post-processor | Authentication từ opaque token giả lập | Gọi introspection endpoint thật |
| `oauth2Login()` | MockMvc request post-processor | OAuth2 principal đã đăng nhập | Redirect, state, code exchange với Identity Provider |
| `oidcLogin()` | MockMvc request post-processor | OIDC principal và ID token giả lập | Nonce, callback, ID token signature và provider thật |
| `mockUser()`, `mockJwt()` | `WebTestClient.mutateWith(...)` | Principal đã xác thực trong Reactive test | Credential/token thật đi qua WebFilter và decoder |

`@WithMockUser` được thiết lập cho phạm vi test method hoặc class bởi cơ chế hỗ trợ test của Spring Security và được dọn dẹp sau test. `user()` thường gắn principal vào một request cụ thể trong MockMvc. Cả hai đều hữu ích để tạo các trường hợp quyền khác nhau mà không cần chạy màn hình đăng nhập.

### 2.1. Ví dụ với @WithMockUser

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AdminAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void adminCanReadAudit() throws Exception {
        mvc.perform(get("/api/admin/audit"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "linh", roles = "USER")
    void regularUserIsDenied() throws Exception {
        mvc.perform(get("/api/admin/audit"))
            .andExpect(status().isForbidden());
    }
}
~~~

Hai test này chứng minh quy tắc truy cập theo role, với điều kiện `SecurityFilterChain` thực sự được nạp vào test context. Chúng không chứng minh `mai` hoặc `linh` có thể đăng nhập bằng mật khẩu nào.

`roles = "ADMIN"` tạo authority `ROLE_ADMIN`. Nếu chính sách dùng `hasAuthority("orders:approve")`, hãy cung cấp đúng authority:

~~~java
@Test
@WithMockUser(authorities = "orders:approve")
void approverCanApprove() throws Exception {
    mvc.perform(post("/api/orders/approve").with(csrf()))
        .andExpect(status().isOk());
}
~~~

### 2.2. Ví dụ với user() theo từng request

~~~java
@Test
void compareTwoRolesForSameEndpoint() throws Exception {
    mvc.perform(get("/api/admin/audit")
            .with(user("linh").roles("USER")))
        .andExpect(status().isForbidden());

    mvc.perform(get("/api/admin/audit")
            .with(user("mai").roles("ADMIN")))
        .andExpect(status().isOk());
}
~~~

Cùng một test method có thể thử nhiều danh tính mà không phải tạo nhiều tài khoản thật. Mỗi request nhận principal được chỉ định bởi post-processor. Cách này rất phù hợp với ma trận role/authority và các ca được phép/bị từ chối.

### 2.3. @WithUserDetails vẫn không phải đăng nhập thật

`@WithUserDetails("linh")` yêu cầu Spring tải user từ `UserDetailsService` trong test context. Nó giúp kiểm tra ứng dụng tạo principal từ dữ liệu người dùng ra sao, bao gồm authorities và thuộc tính tùy biến do `UserDetails` cung cấp.

Tuy vậy, annotation này không gửi username/password đến login endpoint và không gọi `PasswordEncoder.matches(...)` như một quy trình đăng nhập thông thường. Test có thể chứng minh user được tải đúng, nhưng không chứng minh mật khẩu người dùng nhập vào đã được xác minh.

## 3. Kiểm thử HTTP Basic với credential thực qua MockMvc

HTTP Basic là ví dụ đơn giản để thấy rõ khác biệt giữa mock principal và credential thực.

### 3.1. Cấu hình ứng dụng minh họa

Ví dụ dùng Spring Boot 3.x/Spring Security 6.x, Servlet MVC, một kho user trong bộ nhớ và mật khẩu đã mã hóa. Đây là cấu hình dành cho test/demo; ứng dụng thật có thể dùng database hoặc identity service.

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
class BasicAuthTestConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("linh")
                .password(encoder.encode("correct-password"))
                .roles("USER")
                .build(),
            User.withUsername("mai")
                .password(encoder.encode("admin-password"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Controller có thể trả về tên người dùng đã được xác thực:

~~~java
@RestController
class ProfileController {

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

### 3.2. Gửi credential và xác minh kết quả

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthenticationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validPasswordIsAccepted() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("linh", "correct-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("linh"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("linh", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUsernameIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("unknown", "any-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousRequestIsRejected() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Trong các test này, `httpBasic()` chuẩn bị header HTTP Basic. Request đi qua cơ chế xác thực được cấu hình trong ứng dụng. Test có thể phát hiện:

- User không tồn tại nhưng vẫn bị chấp nhận.
- Password sai vẫn được chấp nhận.
- `PasswordEncoder` hoặc provider được cấu hình sai.
- Ứng dụng trả kết quả thành công cho anonymous request.

Để test thực sự có giá trị, phải chắc chắn test context sử dụng `SecurityFilterChain`, `UserDetailsService` và `PasswordEncoder` đang cần kiểm tra. Nếu test thay provider bằng mock luôn trả về thành công, nó chỉ chứng minh cách ứng dụng xử lý kết quả từ mock provider.

**Giới hạn:** HTTP Basic thường gửi credential theo từng request; test ở trên không chứng minh một phiên đăng nhập có session tồn tại qua nhiều request. Nếu ứng dụng sử dụng form login/session, cần kiểm tra luồng đó riêng.

## 4. Kiểm thử form login và session

Khác HTTP Basic, form login thường nhận username/password qua một POST đến endpoint đăng nhập. Khi xác thực thành công, ứng dụng có thể lưu `SecurityContext` trong HTTP session và trình duyệt gửi session cookie ở các request tiếp theo.

### 4.1. Cấu hình form login

Có thể bổ sung form login vào cấu hình Servlet:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Với cấu hình mặc định, Spring Security cung cấp trang đăng nhập và xử lý POST tại `/login`. Ứng dụng có thể tùy biến login page, username parameter, password parameter, success handler và failure handler.

### 4.2. Đăng nhập bằng username/password và dùng lại session

~~~java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginCreatesAuthenticatedSession() throws Exception {
        MvcResult loginResult = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "linh")
                .param("password", "correct-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("linh"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) loginResult.getRequest().getSession(false);

        assertThat(session).isNotNull();

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("linh"));
    }

    @Test
    void invalidPasswordDoesNotAuthenticateUser() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "linh")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(unauthenticated());
    }
}
~~~

Các static import thường dùng cho ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
~~~

Test đầu tiên xác minh ba việc liên tiếp:

1. POST `/login` gửi credential và CSRF token.
2. Spring Security xác minh credential rồi trả về trạng thái đăng nhập thành công.
3. Session được sử dụng cho request tiếp theo đến `/api/me`.

Đây là bằng chứng mạnh hơn `@WithMockUser` khi bạn cần kiểm tra form login và session. Dù vậy, `MockMvc` vẫn chạy trong môi trường mô phỏng Servlet; nó không kiểm tra đầy đủ hành vi của trình duyệt thật, cookie trên mạng, reverse proxy hay HTTPS ở môi trường triển khai.

### 4.3. CSRF trong login test

Với CSRF được bật, POST `/login` cũng là request thay đổi trạng thái và thường cần token hợp lệ. `.with(csrf())` cung cấp token hợp lệ cho request kiểm thử.

Cần phân biệt:

- Test form login với CSRF hợp lệ kiểm tra xác thực và tạo session.
- Test form login thiếu token kiểm tra cơ chế CSRF chặn request.
- `.with(csrf())` là token được tạo cho test, không tự chứng minh trình duyệt thực tế lấy và gửi token từ trang login đúng cách.

Nếu muốn kiểm tra cả quá trình render trang login, lấy CSRF token, gửi lại token qua form và xử lý cookie như trình duyệt, hãy bổ sung kiểm thử end-to-end hoặc browser test theo phạm vi ứng dụng.

### 4.4. Kiểm thử logout và vòng đời session

Đăng xuất là một phần của quy trình đăng nhập thật. Với ứng dụng form login, cần xác minh:

- Request logout đúng phương thức và có CSRF token nếu CSRF bật.
- Session hoặc security context được xóa theo chính sách.
- Request tiếp theo dùng session cũ không còn được coi là đã đăng nhập.
- Cookie/session được xử lý đúng với cấu hình logout handler.

Không nên dùng một `@WithMockUser` test để kết luận logout đã hủy session. Annotation chỉ tạo ngữ cảnh cho test method; nó không tạo vòng đời session như trình duyệt.

## 5. Bearer token: jwt() mock và JWT được xác minh thực tế

Ứng dụng Resource Server nhận header:

~~~http
Authorization: Bearer <access-token>
~~~

Spring Security có thể trích token, xác minh token và tạo `JwtAuthenticationToken`. Trong kiểm thử, có hai con đường cần phân biệt.

### 5.1. Dùng jwt() để kiểm tra phân quyền

~~~java
@Test
void jwtWithRequiredScopeCanReadReports() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isOk());
}

@Test
void jwtWithoutRequiredScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile.read"))))
        .andExpect(status().isForbidden());
}
~~~

Các test này giả lập một JWT authentication đã được chấp nhận, với authorities chỉ định. Chúng rất phù hợp để kiểm tra `hasAuthority`, `hasRole`, method security hoặc logic sử dụng claims.

Chúng **không** gửi một chuỗi bearer token qua `BearerTokenAuthenticationFilter`, không gọi `JwtDecoder` để xác minh chữ ký và không kiểm tra issuer/audience/expiration của token bên ngoài.

### 5.2. Gửi bearer token qua pipeline xác thực thật

Để kiểm tra xác thực JWT thực tế, test phải gửi header:

~~~java
mvc.perform(get("/api/reports")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + signedAccessToken))
    .andExpect(status().isOk());
~~~

`signedAccessToken` phải là JWT được tạo theo đúng thuật toán/khóa và claim mà decoder của test context chấp nhận. Cấu hình resource server phải dùng `JwtDecoder` và validators thực sự cần kiểm tra.

Một bộ test tích hợp có thể chuẩn bị các token:

| Token gửi qua HTTP | Kỳ vọng thường gặp | Điều được kiểm tra |
| --- | --- | --- |
| Chữ ký hợp lệ, issuer/audience đúng, chưa hết hạn | Request được xác thực; sau đó xét quyền | Token hợp lệ được chấp nhận. |
| Chữ ký sai hoặc token bị sửa payload | `401` | Decoder từ chối tính toàn vẹn. |
| `exp` đã qua | `401` | Validator từ chối token hết hạn. |
| `iss` không được tin cậy | `401` | Issuer validator hoạt động. |
| `aud` không dành cho API này | Tùy validator; thường `401` | Audience validation hoạt động nếu được cấu hình. |
| Token hợp lệ nhưng thiếu scope | `403` | Xác thực thành công nhưng phân quyền thất bại. |

Đừng gộp mọi ca vào một assertion. Token hết hạn bị `401` là vấn đề xác thực; token hợp lệ thiếu scope bị `403` là vấn đề phân quyền.

Để test không phụ thuộc Identity Provider bên ngoài, có thể dùng cặp khóa kiểm thử riêng, ký token trong test và cấu hình decoder dùng public key tương ứng. Điều đó vẫn kiểm tra chữ ký qua decoder, dù không kiểm tra việc cấp token của nhà cung cấp thật. Không dùng khóa production hoặc token người dùng thật trong bộ test.

### 5.3. Opaque token cũng có ranh giới tương tự

`opaqueToken()` dựng một authentication giả lập với principal/authorities cho test. Nó không gọi introspection endpoint thật.

Nếu muốn kiểm tra token opaque được xác minh bởi authorization server, cần gửi bearer token qua request và cho `OpaqueTokenIntrospector` thực sự xử lý nó. Có thể dùng một introspector test server hoặc mock có kiểm soát để kiểm tra giao tiếp; nhưng nếu introspector được mock trả về trạng thái active cho mọi token, bạn chỉ kiểm tra tích hợp với mock đó.

## 6. OAuth2 Login và OIDC: principal giả lập không phải authorization code flow

OAuth2 Login và OpenID Connect thường liên quan đến một Identity Provider (IdP). Trình duyệt được chuyển hướng đến provider, người dùng xác thực, provider chuyển hướng về ứng dụng cùng authorization code, sau đó ứng dụng đổi code lấy token và hoàn tất đăng nhập.

### 6.1. Điều oauth2Login() và oidcLogin() giúp kiểm tra

~~~java
@Test
void oauth2UserCanOpenProfile() throws Exception {
    mvc.perform(get("/api/me")
            .with(oauth2Login()
                .attributes(attrs -> attrs.put("name", "Linh"))))
        .andExpect(status().isOk());
}

@Test
void oidcUserCanOpenProfile() throws Exception {
    mvc.perform(get("/api/me")
            .with(oidcLogin()
                .idToken(token -> token
                    .claim("sub", "linh-123")
                    .claim("email", "linh@example.test"))))
        .andExpect(status().isOk());
}
~~~

Ví dụ giả định endpoint đọc thuộc tính tương ứng từ principal và test context đã có cấu hình phù hợp. `oauth2Login()` và `oidcLogin()` hữu ích để kiểm tra:

- Controller/service đọc đúng thuộc tính principal.
- Quyền được ánh xạ hoặc xử lý đúng sau khi người dùng đã đăng nhập.
- Ứng dụng phản hồi đúng với các claims, authorities hoặc thông tin user khác nhau.

Chúng **không** tự thực hiện redirect đến IdP, xác minh state/nonce, trao đổi authorization code, kiểm tra chữ ký ID token hoặc gọi UserInfo endpoint thật.

### 6.2. Muốn kiểm tra quy trình OAuth2/OIDC thật thì cần gì?

Một bài tích hợp hoặc end-to-end có thể dùng IdP thử nghiệm, authorization server cục bộ hoặc môi trường provider dành riêng cho test. Cần kiểm tra những bước thuộc phạm vi ứng dụng:

1. Ứng dụng tạo authorization request với client ID, redirect URI và scope phù hợp.
2. `state` được sinh và đối chiếu để chống request giả mạo.
3. Với OIDC, `nonce` được kiểm tra theo ID token.
4. Callback nhận authorization code và xử lý đúng.
5. Ứng dụng đổi code lấy token theo cấu hình client.
6. ID token/access token được xác minh theo issuer, chữ ký, thời hạn và các điều kiện liên quan.
7. Principal được tạo với thuộc tính và authority đúng.
8. Session hoặc trạng thái đăng nhập được duy trì và kết thúc đúng.

Không phải bài test nào cũng cần dựng provider thật. Dùng `oidcLogin()` cho logic sau đăng nhập thường nhanh, ổn định và dễ kiểm soát hơn. Chỉ chạy bài tích hợp flow thật cho những rủi ro mà mock principal không thể chứng minh.

### 6.3. OAuth2 Client khác OAuth2 Login

`oauth2Client()` có thể thiết lập một authorized client giả lập để kiểm tra thành phần ứng dụng gọi API bên ngoài bằng OAuth2. Nó không tự chứng minh ứng dụng đã lấy access token từ token endpoint thật, refresh token đúng hoặc xử lý lỗi provider thực tế.

Hãy xác định vai trò ứng dụng:

- **OAuth2 Login/OIDC Login:** ứng dụng đăng nhập người dùng thông qua provider.
- **OAuth2 Resource Server:** ứng dụng nhận và xác minh bearer token trên API.
- **OAuth2 Client:** ứng dụng lấy/đính kèm token khi gọi dịch vụ khác.

Mỗi vai trò có luồng xác thực và loại test riêng. Không nên dùng một test `oauth2Login()` để kết luận cả ba vai trò đều hoạt động.

## 7. Servlet và Reactive: gửi credential thật trong từng mô hình

Các tiện ích mock khác nhau theo web stack, nhưng nguyên tắc không đổi: mock principal tạo sẵn trạng thái xác thực; credential gửi qua HTTP phải được xử lý bởi cơ chế xác thực của ứng dụng.

### 7.1. Servlet với MockMvc

| Mục tiêu | Cách thử |
| --- | --- |
| Mock user để thử quyền | `.with(user("linh").roles("USER"))` |
| Mock JWT để thử scope | `.with(jwt().authorities(...))` |
| Gửi HTTP Basic thật qua filter | `.with(httpBasic("linh", "password"))` |
| Gửi form login | POST `/login` với username/password và CSRF token |
| Dùng session sau login | Lấy `MockHttpSession` từ kết quả login và gửi ở request tiếp theo |
| Gửi JWT thực tế | Header `Authorization: Bearer ...` và decoder hoạt động |
| Mock OAuth2/OIDC principal | `.with(oauth2Login())`, `.with(oidcLogin())` |
| Kiểm tra OAuth2/OIDC flow | Tích hợp với provider thử nghiệm hoặc browser/E2E test |

Khi tự tạo `MockMvc` bằng `MockMvcBuilders.webAppContextSetup(context)`, hãy tích hợp Spring Security bằng `.apply(springSecurity())`. Với `@SpringBootTest` và `@AutoConfigureMockMvc`, cấu hình web của application context thường được tự động đưa vào.

### 7.2. Reactive với WebTestClient

Với WebFlux, `SecurityMockServerConfigurers` cung cấp các cách tạo danh tính giả lập:

~~~java
client.mutateWith(mockUser("linh").roles("USER"))
    .get().uri("/api/me")
    .exchange()
    .expectStatus().isOk();

client.mutateWith(mockJwt())
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là principal mock cho test client gắn với mock server/application context. Để gửi HTTP Basic qua cơ chế xác thực thật, client cần gửi header:

~~~java
client.get()
    .uri("/api/me")
    .headers(headers -> headers.setBasicAuth("linh", "correct-password"))
    .exchange()
    .expectStatus().isOk();
~~~

Để gửi bearer token thật:

~~~java
client.get()
    .uri("/api/reports")
    .headers(headers -> headers.setBearerAuth(signedAccessToken))
    .exchange()
    .expectStatus().isOk();
~~~

Các ví dụ credential thật yêu cầu `SecurityWebFilterChain` và `ReactiveAuthenticationManager`/resource server được cấu hình trong application context. Nếu `WebTestClient` gọi một server thật qua mạng, hãy gửi credential/token trong HTTP request; không thể dùng `mutateWith(mockUser(...))` ở test process để đăng nhập hộ server từ xa.

### 7.3. Reactive form login và session cookie

Với WebFlux, form login cũng có thể kiểm thử bằng POST đến login endpoint, sau đó sử dụng cookie session trong request tiếp theo. Test phải gửi đúng content type/form fields, CSRF token theo cấu hình, rồi lấy cookie từ response để gửi lại.

Điểm cần quan sát:

- Login thành công tạo trạng thái xác thực và session/cookie theo cấu hình.
- Password sai không tạo trạng thái đăng nhập.
- Request tiếp theo có cookie hợp lệ được nhận diện là người dùng đã đăng nhập.
- Logout hoặc session hết hạn làm request tiếp theo trở thành anonymous.

`WebTestClient` không nên được coi như trình duyệt hoàn chỉnh tự động xử lý mọi tương tác cookie/redirect trong mọi kiểu test. Khi cần xác minh hành vi cookie qua nhiều request, hãy chủ động chuyển cookie từ response sang request tiếp theo; khi cần kiểm tra JavaScript, trình duyệt và IdP thật, dùng browser/E2E test.

## 8. Chọn test theo câu hỏi cần trả lời

| Câu hỏi | Nên dùng | Không đủ nếu chỉ dùng |
| --- | --- | --- |
| Người có `ROLE_ADMIN` được truy cập route quản trị không? | `@WithMockUser`/`user()` + MockMvc | Test mật khẩu đăng nhập |
| Người thiếu `orders:approve` bị chặn ở service không? | `@WithMockUser` + bean Spring có method security | Unit test gọi `new Service()` |
| Password sai có bị từ chối không? | HTTP Basic hoặc form login gửi credential qua filter | `@WithMockUser` |
| Session được tạo và dùng lại sau login không? | Form login + session/cookie test | `user()` cho từng request |
| JWT thiếu scope có bị từ chối không? | `jwt()`/`mockJwt()` cho phân quyền | Chỉ test decoder |
| JWT chữ ký sai hoặc hết hạn có bị từ chối không? | Bearer token gửi qua resource server với decoder/validator hoạt động | `jwt()`/`mockJwt()` |
| OIDC principal có claims cần thiết không? | `oidcLogin()`/mock OIDC principal | Test authorization code flow |
| `state`, `nonce`, callback và token exchange có đúng không? | Tích hợp/E2E với IdP thử nghiệm | `oidcLogin()` |
| Basic auth hoạt động trong WebFlux không? | `WebTestClient` gửi Basic header | `mockUser()` |
| Reactive method security có từ chối publisher không? | Bean Spring + reactive context + `StepVerifier` | Chỉ tạo `Mono` nhưng không subscribe |

Một chiến lược cân bằng thường dùng mock principal cho phần lớn tổ hợp phân quyền, một số test credential thật cho đường xác thực, và một số bài tích hợp cho session/token/IdP quan trọng. Cách này giữ test nhanh nhưng vẫn có bằng chứng cho các bước xác thực thực tế.

## 9. Các lỗi thường gặp

### 9.1. Dùng @WithMockUser để test mật khẩu

Annotation tạo principal đã xác thực. Test vẫn có thể xanh dù `PasswordEncoder` sai hoặc login filter không được cấu hình. Hãy gửi credential qua HTTP Basic hoặc form login khi mục tiêu là mật khẩu.

### 9.2. Gửi Basic header nhưng test context không có provider thật

Header có thể đi qua filter nhưng nếu `AuthenticationManager`/provider bị mock hoặc thay thế, test chỉ kiểm tra cấu hình giả. Kiểm tra bean và profile của test context để biết ai thực sự xác minh password.

### 9.3. Nhầm jwt() với kiểm tra chữ ký

`jwt()` cung cấp một JWT authentication đã được dựng sẵn. Token value giả lập không chứng minh decoder có thể xác minh chữ ký. Muốn kiểm tra chữ ký, hãy gửi token đã ký qua header và dùng decoder thật trong phạm vi test.

### 9.4. Test form login nhưng không giữ session

Nếu mỗi request đều gắn `.with(user(...))`, bạn không kiểm tra session được tạo và tái sử dụng. Hãy thực hiện POST login, lấy session/cookie từ response rồi dùng lại trong request tiếp theo.

### 9.5. Bỏ qua CSRF trong test POST login

Một request đăng nhập có thể bị CSRF filter từ chối trước khi username/password được xử lý. Dùng token hợp lệ khi mục tiêu là kiểm tra credential; bỏ token khi mục tiêu chính là kiểm tra CSRF.

### 9.6. Dùng oauth2Login() để kết luận IdP thật hoạt động

Mock OAuth2/OIDC principal không chạy redirect, callback, code exchange hay token validation. Dùng provider thử nghiệm cho các bước đó.

### 9.7. Dùng mock principal với server đang chạy ở cổng thật

Mock principal nằm trong tiến trình test và không tự được truyền sang server qua mạng. Gửi credential hoặc token thật trong request HTTP khi kiểm tra server thật.

### 9.8. Chỉ kiểm tra status mà không kiểm tra danh tính

Một endpoint trả `200` chưa chứng minh đúng người dùng đã đăng nhập. Hãy kiểm tra principal/username/claims cần thiết, dữ liệu trả về và tác động nghiệp vụ.

## 10. Ma trận thực hành

Giả sử ứng dụng có:

- `GET /api/me`: yêu cầu xác thực.
- `GET /api/admin/audit`: yêu cầu `ROLE_ADMIN`.
- `POST /api/orders`: yêu cầu xác thực và CSRF.
- `GET /api/reports`: yêu cầu `SCOPE_reports.read`.
- Form login tại `/login`.

Ma trận gợi ý:

| Bài test | Cách thiết lập | Kết quả kỳ vọng | Loại bằng chứng |
| --- | --- | --- | --- |
| Anonymous đọc profile | Không gắn user, không credential | `401` hoặc redirect theo entry point | Anonymous bị chặn |
| User thường đọc audit | `user("linh").roles("USER")` | `403` | Phân quyền URL |
| Admin đọc audit | `user("mai").roles("ADMIN")` | `200` | Phân quyền URL cho phép |
| Password đúng | HTTP Basic/form login với credential hợp lệ | Xác thực thành công | Credential được kiểm tra |
| Password sai | HTTP Basic/form login với password sai | `401` hoặc failure redirect | Credential sai bị từ chối |
| Form login tạo session | POST `/login`, lấy session, gọi `/api/me` | Request tiếp theo nhận diện user | Session được tạo và dùng lại |
| JWT mock có scope | `jwt()` với `SCOPE_reports.read` | `200` | Phân quyền sau xác thực giả lập |
| JWT mock thiếu scope | `jwt()` với authority khác | `403` | Phân quyền từ chối |
| JWT thật hết hạn | Bearer token qua decoder/validator | Thường `401` | Token validation |
| OAuth2/OIDC principal | `oauth2Login()`/`oidcLogin()` | Theo quyền/logic ứng dụng | Logic sau đăng nhập |
| OAuth2/OIDC flow | Provider thử nghiệm và callback | Hoàn tất hoặc từ chối đúng | Quy trình đăng nhập liên hệ IdP |

Với mỗi hàng, hãy ghi rõ test có đi qua filter/provider/decoder thật hay không. Đó là thông tin quan trọng nhất khi đánh giá độ bao phủ.

## 11. Bài tập

1. Viết hai test cho cùng endpoint quản trị: một dùng `@WithMockUser(roles = "USER")`, một dùng `@WithMockUser(roles = "ADMIN")`. Giải thích vì sao chúng không kiểm tra password.
2. Cấu hình HTTP Basic với một user trong `UserDetailsService`. Viết test password đúng, password sai và username không tồn tại bằng `.with(httpBasic(...))`.
3. Cấu hình form login. Gửi POST `/login` với credential và CSRF token; lấy session từ kết quả login rồi dùng session để gọi endpoint cần xác thực.
4. Viết một test JWT mock có scope hợp lệ và một test thiếu scope. Sau đó thiết kế test gửi bearer token đã ký qua resource server để kiểm tra decoder.
5. Dùng `oidcLogin()` để thử logic đọc claim `email`. Liệt kê các bước của authorization code flow mà test này chưa kiểm chứng.
6. Tạo ứng dụng WebFlux nhỏ; so sánh `.mutateWith(mockUser(...))` với request gửi Basic header thật qua `WebTestClient`.
7. Viết tên test thể hiện rõ mục tiêu, ví dụ `wrongPasswordIsRejected`, `regularUserCannotReadAudit`, `expiredBearerTokenIsRejected` và `formLoginSessionCanAccessProfile`.

**Tiêu chí hoàn thành:** bạn có thể chỉ ra test nào tạo sẵn danh tính, test nào thực sự gửi credential/token, thành phần nào xác minh bằng chứng, và test cần bổ sung để kiểm tra session hoặc giao tiếp với Identity Provider.

## 12. Ghi nhớ

`@WithMockUser`, `user()`, `jwt()`, `oauth2Login()` và `oidcLogin()` giúp kiểm tra nhanh chính sách phân quyền và logic ứng dụng sau khi đã có một principal. Chúng giảm phụ thuộc vào hạ tầng đăng nhập và cho phép thử nhiều vai trò, authority, claim một cách có kiểm soát.

Khi cần kiểm chứng quy trình xác thực, hãy gửi thông tin qua đường xử lý thực tế: HTTP Basic hoặc form login với username/password, session cookie cho các request tiếp theo, bearer token qua resource server, hoặc OAuth2/OIDC flow với provider thử nghiệm. Trong Servlet, dùng `MockMvc`; trong Reactive, dùng `WebTestClient` và cấu hình bảo mật tương ứng.

Một bài test tốt phải nói rõ nó chứng minh **quyền của một danh tính đã được giả lập** hay **server đã xác minh đúng bằng chứng đăng nhập**. Phân biệt được hai kết quả đó giúp bộ kiểm thử Spring Security có giá trị và tránh những test xanh nhưng bỏ sót lỗi xác thực.
