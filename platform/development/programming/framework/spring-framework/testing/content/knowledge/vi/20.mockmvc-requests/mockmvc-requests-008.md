# Principal và ngữ cảnh xác thực của yêu cầu

Khi kiểm thử endpoint Spring MVC bằng `MockMvc`, một request có thể mang thông tin về người gọi. Controller có thể đọc tên người dùng qua `Principal`, nhận đối tượng `Authentication`, hoặc lấy principal đã xác thực bằng `@AuthenticationPrincipal`. Spring Security còn dùng `SecurityContext` để lưu trạng thái xác thực trong quá trình xử lý request.

Các khái niệm này có liên quan nhưng không đồng nhất. `Principal` là khái niệm của Java và Servlet API, thường đại diện cho danh tính của người gửi request. `Authentication` là đối tượng của Spring Security, chứa principal, trạng thái xác thực và authorities. `SecurityContext` giữ `Authentication` hiện tại. Khi Spring Security filter chain được cấu hình, nó kết nối ngữ cảnh bảo mật với Servlet request để controller có thể truy cập danh tính theo các API phù hợp.

Trong MockMvc test, cần tạo đúng loại ngữ cảnh mà hành vi đang kiểm tra sử dụng. Chỉ gắn một `Principal` vào request có thể đủ cho controller gọi `request.getUserPrincipal()`, nhưng chưa chắc đã tạo `Authentication` trong `SecurityContextHolder` để Spring Security kiểm tra quyền hoặc để `@AuthenticationPrincipal` hoạt động.

## 1. Principal trong Servlet request

`java.security.Principal` là một interface đơn giản mô tả danh tính. Nó cung cấp phương thức `getName()` để trả về tên định danh. Trong Servlet API, `HttpServletRequest` có các phương thức liên quan:

- `getUserPrincipal()` trả về principal gắn với request, hoặc `null` nếu request chưa có principal.
- `getRemoteUser()` trả về tên người dùng được xác định cho request, hoặc `null` nếu chưa xác thực.
- `isUserInRole(String role)` kiểm tra người gọi có thuộc role được chỉ định hay không theo cơ chế bảo mật của Servlet.

Controller có thể nhận `Principal` trực tiếp làm tham số handler:

```java
@RestController
public class ProfileController {

    @GetMapping("/request-principal")
    public String requestPrincipal(Principal principal) {
        return principal == null ? "anonymous" : principal.getName();
    }
}
```

Spring MVC hỗ trợ resolve tham số `Principal` từ request hiện tại. Đây là cách đọc danh tính ở tầng Servlet/MVC. Nếu controller chỉ cần tên principal, nó không cần phụ thuộc trực tiếp vào kiểu `Authentication` của Spring Security.

### Gắn Principal trực tiếp trong MockMvc

Spring MVC Test cho phép đặt principal trên request builder bằng `.principal(...)`:

```java
@WebMvcTest(ProfileController.class)
@AutoConfigureMockMvc(addFilters = false)
class ProfileControllerPrincipalTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void exposesPrincipalNameToController() throws Exception {
        Principal principal = () -> "alice";

        mockMvc.perform(get("/request-principal").principal(principal))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
```

Trong ví dụ này, test đặt một đối tượng triển khai `Principal` trực tiếp vào `MockHttpServletRequest`. Nó phù hợp để kiểm tra controller hoặc thành phần Servlet đọc `request.getUserPrincipal()` hay tham số `Principal`.

`addFilters = false` tắt các filter đã đăng ký cho MockMvc trong test này để tập trung vào Servlet request principal. Nếu mục tiêu là kiểm tra cách Spring Security chuyển Authentication thành request principal, hãy giữ filter chain hoạt động và thiết lập Authentication bằng các cách ở phần sau.

Tuy nhiên, `.principal(...)` chỉ thiết lập principal trên request mock. Nó không tự tạo một `Authentication` đã xác thực trong `SecurityContextHolder`. Vì vậy, cách này không đủ để kiểm tra quy tắc `hasRole`, `hasAuthority`, method security hoặc tham số `@AuthenticationPrincipal` dựa trên Spring Security.

## 2. Authentication và SecurityContext của Spring Security

Spring Security biểu diễn trạng thái xác thực bằng interface `Authentication`, interface này cũng mở rộng `Principal`. Một `Authentication` thường chứa:

- `getPrincipal()`: đối tượng đại diện cho người dùng hoặc danh tính. Nó có thể là username dạng chuỗi, một `UserDetails`, hoặc một kiểu principal tùy chỉnh.
- `getCredentials()`: thông tin chứng thực được dùng trong quá trình xác thực, ví dụ password trước khi xác thực hoàn tất. Ứng dụng không nên ghi log hoặc trả credentials ra response.
- `getAuthorities()`: tập quyền được cấp, thường là `GrantedAuthority` như `ROLE_ADMIN` hoặc `SCOPE_read`.
- `isAuthenticated()`: cho biết đối tượng đang được xem là đã xác thực hay chưa.
- `getDetails()`: thông tin bổ sung về quá trình xác thực, tùy cơ chế được dùng.

`SecurityContext` chứa `Authentication` hiện tại. `SecurityContextHolder` là nơi Spring Security cung cấp context cho code đang xử lý. Cấu hình mặc định thường lưu context theo thread thông qua `ThreadLocal`, nhờ đó các thành phần bảo mật có thể đọc cùng trạng thái trong một luồng xử lý.

Quan hệ khái quát:

```text
MockMvc request
      |
      v
Spring Security filter chain
      |
      +--> SecurityContextHolder
      |        |
      |        v
      |    SecurityContext
      |        |
      |        v
      |    Authentication
      |        +--> principal
      |        +--> authorities
      |        +--> authenticated state
      |
      v
DispatcherServlet --> controller
                         |
                         +--> Principal / Authentication
                         +--> @AuthenticationPrincipal
```

Sơ đồ mô tả luồng điển hình khi test đã tích hợp Spring Security filter chain. Cấu hình thực tế có thể có thêm các filter xác thực, lưu context, xử lý exception và kiểm tra quyền.

### Principal và Authentication khác nhau như thế nào?

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| `Principal` | Đại diện danh tính và cung cấp tên | `principal.getName()` trả về `alice` |
| `Authentication` | Trạng thái xác thực trong Spring Security | Chứa principal `alice` và authorities `ROLE_USER` |
| `SecurityContext` | Giữ Authentication hiện tại | `context.getAuthentication()` |
| `SecurityContextHolder` | Cung cấp SecurityContext cho code đang xử lý | `SecurityContextHolder.getContext()` |
| `GrantedAuthority` | Một quyền được cấp | `ROLE_ADMIN`, `invoice:read` |

`Authentication` là một loại `Principal`, nhưng một `Principal` bất kỳ không nhất thiết là `Authentication`. Đây là lý do hai cách thiết lập request principal và security context trong test có ý nghĩa khác nhau.

## 3. Spring Security kết nối Servlet request với SecurityContext ra sao?

Khi ứng dụng sử dụng Spring Security, filter chain đọc hoặc tạo `SecurityContext`, thực hiện xác thực theo cấu hình và đặt `Authentication` vào context hiện tại. Một filter tích hợp với Servlet API còn giúp các phương thức như `getUserPrincipal()`, `getRemoteUser()` và `isUserInRole()` phản ánh danh tính và quyền theo ngữ cảnh bảo mật.

Trong controller, có thể nhận `Authentication` trực tiếp:

```java
@RestController
public class AccountController {

    @GetMapping("/account/name")
    public String accountName(Authentication authentication) {
        return authentication.getName();
    }
}
```

Hoặc dùng `@AuthenticationPrincipal` để nhận principal bên trong Authentication:

```java
@RestController
public class AccountController {

    @GetMapping("/account/principal")
    public String principalName(
            @AuthenticationPrincipal UserDetails userDetails) {
        return userDetails.getUsername();
    }
}
```

`@AuthenticationPrincipal` được Spring Security cung cấp trong package `org.springframework.security.core.annotation`. Argument resolver lấy principal từ Authentication hiện tại. Nếu không có Authentication phù hợp hoặc principal không tương thích với kiểu tham số, kết quả có thể là `null` hoặc không bind được theo cấu hình resolver.

Nếu code dùng `@AuthenticationPrincipal` hoặc đọc `SecurityContextHolder`, hãy thiết lập Authentication trong test. Chỉ gọi `.principal(...)` trên request builder không đáp ứng mục tiêu đó.

## 4. Dùng user() để tạo người dùng đã xác thực trong MockMvc

Spring Security Test cung cấp request postprocessor `user(...)`. Nó là cách thuận tiện để tạo một request có người dùng xác thực giả lập mà không cần chạy quy trình đăng nhập thật.

Ví dụ endpoint yêu cầu xác thực:

```java
@RestController
public class CurrentUserController {

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin area";
    }
}
```

Giả sử cấu hình bảo mật yêu cầu người dùng đăng nhập để vào `/profile` và yêu cầu role ADMIN để vào `/admin`:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .requestMatchers("/profile").authenticated()
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Test có thể tạo user cho từng request:

```java
@WebMvcTest(CurrentUserController.class)
@Import(SecurityConfig.class)
class CurrentUserControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void authenticatedUserCanReadProfile() throws Exception {
        mockMvc.perform(get("/profile").with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void userWithoutAdminRoleCannotOpenAdminPage() throws Exception {
        mockMvc.perform(get("/admin").with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdminPage() throws Exception {
        mockMvc.perform(get("/admin").with(user("root").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin area"));
    }
}
```

`user("alice")` tạo người dùng test với tên `alice`. `roles("USER")` thêm authority `ROLE_USER`; Spring tự thêm tiền tố `ROLE_`. Vì vậy, khi cấu hình dùng `hasRole("ADMIN")`, test cần `roles("ADMIN")`, không cần truyền chuỗi `ROLE_ADMIN` vào `roles`.

Nếu ứng dụng kiểm tra authority tùy chỉnh thay vì role, dùng `.authorities(...)`:

```java
mockMvc.perform(get("/reports")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("report:read"))))
        .andExpect(status().isOk());
```

`authorities(...)` dùng nguyên tên quyền được cung cấp, không tự thêm `ROLE_`. Phân biệt `hasRole("ADMIN")` và `hasAuthority("ROLE_ADMIN")` hoặc `hasAuthority("report:read")` để tránh test tạo sai authority.

`user(...)` là cơ chế tạo Authentication cho test. Nó không kiểm tra password encoder, user lookup, LDAP, OAuth login hay quy trình xác thực production. Nếu mục tiêu là kiểm tra các bước đăng nhập thật, cần test riêng filter hoặc authentication provider với thông tin đăng nhập tương ứng.

## 5. Dùng UserDetails hoặc principal tùy chỉnh

Nếu ứng dụng dùng một kiểu principal có thêm thông tin như account ID, tenant hoặc mã nhân viên, có thể truyền `UserDetails` vào `user(...)`:

```java
public class AppUser implements UserDetails {

    private final Long accountId;
    private final String username;
    private final Collection<? extends GrantedAuthority> authorities;

    public AppUser(Long accountId, String username,
                   Collection<? extends GrantedAuthority> authorities) {
        this.accountId = accountId;
        this.username = username;
        this.authorities = authorities;
    }

    public Long getAccountId() {
        return accountId;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return "unused-in-this-test";
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
```

Controller nhận đúng kiểu principal:

```java
@GetMapping("/account/id")
public Long accountId(@AuthenticationPrincipal AppUser user) {
    return user.getAccountId();
}
```

Test tạo principal:

```java
AppUser appUser = new AppUser(
        42L,
        "alice",
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

mockMvc.perform(get("/account/id").with(user(appUser)))
        .andExpect(status().isOk())
        .andExpect(content().string("42"));
```

Như vậy test có thể xác nhận controller dùng đúng dữ liệu trong principal của ứng dụng. Nếu principal tùy chỉnh không triển khai `UserDetails`, có thể tạo `Authentication` phù hợp và dùng `authentication(...)` hoặc `securityContext(...)` như phần tiếp theo.

## 6. Thiết lập Authentication hoặc SecurityContext trực tiếp

Khi cần kiểm soát chính xác loại `Authentication`, authorities, details hoặc principal, dùng các postprocessor tương ứng của Spring Security Test.

### Dùng authentication(...)

Ví dụ tạo `UsernamePasswordAuthenticationToken` đã xác thực:

```java
Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "alice",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

mockMvc.perform(get("/profile").with(authentication(authentication)))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
```

Constructor nhận authorities tạo token ở trạng thái authenticated. Constructor chỉ nhận principal và credentials không authorities thường tạo token chưa xác thực; không dùng nhầm constructor nếu mục tiêu test là request đã đăng nhập.

### Dùng securityContext(...)

Khi test cần kiểm soát toàn bộ `SecurityContext`, có thể tạo context và gắn Authentication vào đó:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);

mockMvc.perform(get("/profile").with(securityContext(context)))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
```

Hai cách này hữu ích khi `user(...)` không đủ biểu đạt cấu trúc principal hoặc Authentication mà ứng dụng sử dụng. Với trường hợp phổ biến chỉ cần username và roles, `user(...)` thường ngắn gọn hơn.

## 7. Dùng @WithMockUser cho test method hoặc test class

Ngoài request postprocessor, Spring Security Test hỗ trợ annotation `@WithMockUser`. Annotation này thiết lập SecurityContext cho test method hoặc toàn bộ test class.

```java
@WebMvcTest(CurrentUserController.class)
@Import(SecurityConfig.class)
class CurrentUserWithMockUserTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void exposesCurrentUser() throws Exception {
        mockMvc.perform(get("/profile"))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void allowsAdmin() throws Exception {
        mockMvc.perform(get("/admin"))
                .andExpect(status().isOk());
    }
}
```

Có thể đặt `@WithMockUser` trên class nếu mọi test trong class dùng cùng người dùng mặc định. Đặt trên method khi từng test cần danh tính hoặc quyền khác nhau.

`@WithMockUser` tạo người dùng mô phỏng với principal kiểu `UserDetails` mặc định của Spring Security. Nếu ứng dụng yêu cầu principal tùy chỉnh, hãy dùng `user(customUserDetails)`, `authentication(...)`, hoặc cơ chế `@WithSecurityContext` tự định nghĩa.

Annotation này không thực hiện đăng nhập qua form, không gọi `UserDetailsService` production và không kiểm tra password. Nó thiết lập trạng thái xác thực cho mục tiêu kiểm thử.

## 8. Cấu hình Spring Security cho MockMvc

Các ví dụ `user(...)`, `authentication(...)` và `@WithMockUser` có ý nghĩa khi test thực sự chạy với cấu hình Spring Security cần kiểm tra. Cần đưa filter chain vào MockMvc.

Với Spring Boot và `@AutoConfigureMockMvc` hoặc các test slice như `@WebMvcTest`, cấu hình MockMvc thường được Boot tích hợp với Spring Security khi các dependency và bean security phù hợp có mặt. Nếu tự xây dựng MockMvc bằng `MockMvcBuilders`, hãy thêm security configurer:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` đến từ `SecurityMockMvcConfigurers` trong Spring Security Test. Nó tích hợp `FilterChainProxy` và các thành phần cần thiết để request mock đi qua Spring Security filter chain.

Nếu không thêm filter chain, test có thể không kiểm tra được quy tắc authorization của ứng dụng. Một endpoint có thể trả 200 trong test vì filter bảo vệ không chạy, dù khi deploy nó yêu cầu đăng nhập hoặc role cụ thể.

Để kiểm tra một request được bảo vệ, cần bảo đảm đồng thời:

1. Security configuration được nạp vào context test.
2. Filter chain của Spring Security được gắn vào MockMvc.
3. Test cung cấp trạng thái xác thực phù hợp hoặc cố ý không cung cấp để kiểm tra anonymous.
4. Assertion kiểm tra đúng status và kết quả mà quy tắc bảo mật quy định.

## 9. Kiểm tra request anonymous, authenticated và quyền truy cập

Một nhóm test authorization nên mô tả ít nhất các trạng thái khác nhau mà endpoint hỗ trợ.

| Trạng thái | Thiết lập trong test | Kết quả thường mong đợi với endpoint được bảo vệ |
| --- | --- | --- |
| Chưa xác thực | Không dùng `user(...)` hoặc `@WithMockUser` | 401 hoặc chuyển hướng đăng nhập, tùy cấu hình |
| Đã xác thực, thiếu quyền | `.with(user("alice").roles("USER"))` | 403 nếu người dùng đã đăng nhập nhưng không đủ quyền |
| Đã xác thực, đủ quyền | `.with(user("root").roles("ADMIN"))` | Request được cho phép |
| Authority tùy chỉnh | `.with(user("alice").authorities(...))` | Phụ thuộc authority được cấu hình |

Ví dụ anonymous:

```java
@Test
void anonymousUserCannotReadProfile() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
}
```

Assertion 401 chỉ phù hợp nếu ứng dụng cấu hình authentication entry point trả 401, ví dụ API stateless. Một ứng dụng web dùng form login có thể trả redirect 302 đến trang đăng nhập. Hãy viết assertion theo chính sách xử lý anonymous của ứng dụng.

403 thường biểu thị người dùng đã xác thực nhưng không có quyền. Nếu request chưa được xác thực, Spring Security thường gọi authentication entry point trước; kết quả cụ thể phụ thuộc cấu hình.

## 10. Các cơ chế xác thực chuyên biệt trong MockMvc

`user(...)` là cách tạo người dùng mô phỏng tổng quát. Nếu ứng dụng dùng loại Authentication chuyên biệt, Spring Security Test có các postprocessor tương ứng trong module test của từng tính năng.

### HTTP Basic

Với endpoint dùng HTTP Basic, `httpBasic(username, password)` tạo header Basic Authorization:

```java
mockMvc.perform(get("/profile").with(httpBasic("alice", "password")))
        .andExpect(status().isOk());
```

Cách này hữu ích khi muốn kiểm tra filter và authentication provider xử lý HTTP Basic. Khác với `user(...)`, nó gửi thông tin đăng nhập vào request để cơ chế xác thực cấu hình trong filter chain xử lý. Test cần có user store hoặc authentication provider tương ứng.

### JWT cho OAuth 2.0 Resource Server

Nếu endpoint được bảo vệ bằng JWT bearer token và ứng dụng dùng Spring Security OAuth2 Resource Server, có thể dùng `jwt()` để tạo JWT Authentication mô phỏng:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("scope", "orders.read"))))
        .andExpect(status().isOk());
```

Postprocessor `jwt()` giúp kiểm tra authorization dựa trên claims và authorities đã ánh xạ trong test. Nó không kiểm tra chữ ký token, issuer, audience, thời hạn hoặc quá trình lấy khóa từ authorization server. Muốn xác nhận việc xác minh JWT thật, cần test riêng cấu hình decoder và kiểm tra token hợp lệ/không hợp lệ với cơ chế phù hợp.

### CSRF là một khía cạnh riêng

Nếu ứng dụng bật CSRF protection, request thay đổi trạng thái như POST, PUT, PATCH hoặc DELETE có thể cần token CSRF:

```java
mockMvc.perform(post("/profile/email")
        .with(user("alice"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"email\":\"alice@example.test\"}"))
        .andExpect(status().isOk());
```

CSRF token kiểm tra tính hợp lệ của request theo cơ chế chống CSRF; nó không thay thế Authentication. Một request có thể đã đăng nhập nhưng vẫn bị từ chối nếu thiếu CSRF token theo cấu hình.

## 11. Các lỗi thường gặp khi thiết lập Principal và Authentication

### Dùng principal(...) nhưng mong đợi @AuthenticationPrincipal có dữ liệu

`.principal(...)` thiết lập `HttpServletRequest.getUserPrincipal()`. `@AuthenticationPrincipal` đọc principal từ `Authentication` trong Spring Security context. Hai nguồn này có thể được liên kết khi filter chain chạy, nhưng một request mock đơn thuần chỉ có principal không tự tạo SecurityContext. Hãy dùng `user(...)`, `authentication(...)` hoặc `securityContext(...)` cho trường hợp thứ hai.

### Dùng user(...) nhưng filter chain không chạy

Postprocessor có thể thiết lập thông tin người dùng cho request, nhưng nếu MockMvc không tích hợp Spring Security filter chain, test không mô phỏng đầy đủ đường đi authorization của ứng dụng. Hãy dùng `@AutoConfigureMockMvc` theo cấu hình Boot phù hợp hoặc `.apply(springSecurity())` khi tự build.

### Nhầm role với authority

`roles("ADMIN")` thêm tiền tố `ROLE_`, tạo `ROLE_ADMIN`. `authorities("ADMIN")` hoặc `hasAuthority("ADMIN")` làm việc với tên authority nguyên văn. Nếu ứng dụng dùng `hasRole("ADMIN")`, test nên tạo `ROLE_ADMIN` qua `roles("ADMIN")` hoặc authority chính xác tương đương.

### Dùng sai kiểu principal

Một endpoint nhận `@AuthenticationPrincipal AppUser` cần Authentication có principal là `AppUser`. Dùng `user("alice")` tạo principal mặc định kiểu `UserDetails`, không phải `AppUser`. Hãy truyền đúng đối tượng `UserDetails` tùy chỉnh hoặc tạo Authentication phù hợp.

### Dùng một người dùng cho mọi test

Một test class có thể cần anonymous, USER và ADMIN. Hãy thiết lập danh tính rõ ràng trên từng test để mỗi trường hợp độc lập, dễ đọc và không phụ thuộc trạng thái còn lại. Khi dùng `@WithMockUser` ở cấp class, có thể ghi đè ở cấp method hoặc chọn request postprocessor riêng cho test cần tình huống khác.

### Giả định status code giống nhau ở mọi cấu hình

Anonymous có thể nhận 401 hoặc 302 tùy entry point. Người dùng đã xác thực nhưng thiếu quyền thường nhận 403. Hãy căn cứ vào cấu hình API hoặc web login của ứng dụng khi xác định assertion.

### Trả thông tin xác thực ra response hoặc log

Principal và authorities thường có thể dùng để kiểm tra quyền, nhưng credentials không nên được hiển thị. Test nên chỉ kiểm tra thông tin cần thiết như username, account ID hoặc quyền; không serialize toàn bộ Authentication hay SecurityContext vào response production.

## 12. Chọn cách thiết lập theo mục tiêu test

| Mục tiêu | Cách thiết lập phù hợp |
| --- | --- |
| Controller chỉ cần tên từ Servlet request principal | `.principal(principal)` |
| Controller đọc `Authentication` hoặc `@AuthenticationPrincipal` | `.with(user(...))` hoặc `@WithMockUser` |
| Cần principal kiểu `UserDetails` tùy chỉnh | `.with(user(customUserDetails))` |
| Cần Authentication tùy chỉnh | `.with(authentication(authentication))` |
| Cần kiểm soát toàn bộ SecurityContext | `.with(securityContext(context))` |
| Muốn kiểm tra HTTP Basic filter và provider | `.with(httpBasic(username, password))` |
| Muốn kiểm tra authorization theo JWT claims/authorities mô phỏng | `.with(jwt())` |
| Muốn kiểm tra anonymous | Không thiết lập user hoặc Authentication; assertion theo entry point |
| Muốn kiểm tra authorization thực của ứng dụng | Nạp security config và tích hợp filter chain vào MockMvc |

Quy trình thực hiện một bài test xác thực:

1. Xác định code đang đọc `Principal`, `Authentication`, `SecurityContextHolder` hay `@AuthenticationPrincipal`.
2. Xác định quyền mà endpoint yêu cầu: authenticated, role hay authority cụ thể.
3. Nạp security configuration cần kiểm tra.
4. Bảo đảm Spring Security filter chain tham gia MockMvc.
5. Chọn postprocessor hoặc annotation phù hợp với loại principal và Authentication.
6. Kiểm tra response cho trường hợp anonymous, thiếu quyền và đủ quyền khi các trường hợp đó có ý nghĩa.

## 13. Kết luận

`Principal` đại diện danh tính ở tầng Java/Servlet; `Authentication` của Spring Security chứa principal cùng trạng thái xác thực và authorities; `SecurityContext` lưu Authentication hiện tại. Trong MockMvc, `.principal(...)` phù hợp khi test chỉ cần đặt Servlet request principal. `user(...)`, `authentication(...)`, `securityContext(...)` và `@WithMockUser` phù hợp khi test cần trạng thái xác thực của Spring Security.

Để kiểm tra authorization có ý nghĩa, cần nạp cấu hình Spring Security và cho request đi qua filter chain trong MockMvc. Chọn đúng nguồn principal, đúng kiểu Authentication và đúng quyền giúp test phản ánh chính xác hành vi endpoint mà ứng dụng cần bảo vệ.
