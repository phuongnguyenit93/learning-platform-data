# Phân biệt người dùng vẫn xác thực nhưng bị cấm truy cập

## 1. Ý nghĩa của một request đã xác thực nhưng nhận 403

Trong Spring Security, **xác thực (authentication)** trả lời câu hỏi “request này là ai?”, còn **phân quyền (authorization)** trả lời câu hỏi “danh tính này có được phép thực hiện hành động đang yêu cầu không?”. Hai giai đoạn có liên quan nhưng không đồng nhất.

Một người dùng có thể đăng nhập thành công, được Spring Security nhận diện đầy đủ, nhưng vẫn không được phép mở tài nguyên quản trị. Ví dụ, tài khoản `mai` có `ROLE_USER` gọi `/api/admin/report`, trong khi endpoint yêu cầu `ROLE_ADMIN`. Kết quả điển hình là:

- HTTP status: `403 Forbidden`.
- Trạng thái bảo mật: request vẫn có `Authentication` đã xác thực.
- Danh tính: username vẫn là `mai`.
- Quyền hiện có: `ROLE_USER`, không có `ROLE_ADMIN`.

Đây là trường hợp quan trọng cần kiểm thử trong module **SPRING_SECURITY_TESTING**. Người học dùng `spring-security-test` để xác minh xác thực, phân quyền và bảo vệ HTTP trên ứng dụng Servlet và Reactive, với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập.

Bài thuộc chương **Khẳng định kết quả** tập trung vào cách chứng minh một request bị từ chối **sau khi danh tính đã được xác thực**. Ta sẽ kết hợp status `403` với `authenticated()`, username, role/authority và các kiểm tra response phù hợp.

## 2. Phân biệt authentication failure và access denied

### 2.1. Hai loại lỗi đi qua hai nhánh xử lý khác nhau

Ở tầng Servlet, Spring Security dùng `ExceptionTranslationFilter` để chuyển các exception bảo mật thành HTTP response. Hai nhóm tình huống chính:

| Tình huống | Trạng thái danh tính | Thành phần xử lý thường gặp | Phản hồi thường gặp |
| --- | --- | --- | --- |
| Không có credentials để vào tài nguyên được bảo vệ | Anonymous | `AuthenticationEntryPoint` | `401` hoặc redirect login |
| Credentials sai hoặc token không hợp lệ | Không tạo được Authentication hợp lệ | Authentication mechanism và entry point | Thường `401` |
| Đã xác thực nhưng thiếu role/authority | Authenticated | `AccessDeniedHandler` | Thường `403` |
| Đã xác thực nhưng thiếu scope JWT | Authenticated | Authorization và access-denied handling | Thường `403` |
| Đã xác thực nhưng thiếu CSRF token | Có thể đã Authenticated | `CsrfFilter` và access-denied handling | Thường `403` |
| Remember-me không đáp ứng yêu cầu fully authenticated | Remember-me | Entry point có thể yêu cầu xác thực mạnh hơn | `401`, redirect hoặc phản hồi tùy cấu hình |

`AuthenticationEntryPoint` bắt đầu một cơ chế xác thực khi request chưa có danh tính đủ điều kiện. `AccessDeniedHandler` xử lý trường hợp truy cập bị từ chối. Với người dùng đã xác thực đầy đủ, thiếu quyền thường dẫn đến `403`.

### 2.2. Vì sao 403 chưa đủ chứng minh người dùng đã đăng nhập?

HTTP `403` chỉ nói rằng server từ chối request. Nó không tự chứng minh nguyên nhân là thiếu role. Ví dụ:

- `CsrfFilter` có thể từ chối request POST thiếu CSRF token.
- Một filter tùy chỉnh có thể gửi 403 trước khi authorization URL được đánh giá.
- Ứng dụng có thể cấu hình handler riêng cho anonymous request.
- Một số cấu hình phân quyền có thể chủ động che giấu tài nguyên bằng 403.

Do đó, nếu mục tiêu là kiểm tra “người dùng đã xác thực nhưng thiếu quyền”, hãy kết hợp:

```java
.andExpect(status().isForbidden())
.andExpect(authenticated().withUsername("mai"))
```

Nếu chính sách liên quan đến role, thêm `withRoles(...)`; nếu liên quan đến scope hoặc permission, thêm `withAuthorities(...)` hoặc kiểm tra tập authority bằng `withAuthentication(...)`.

### 2.3. So sánh 401, 403 và anonymous

| Request | Assertion HTTP | Assertion bảo mật | Kết luận |
| --- | --- | --- | --- |
| Không có credentials gọi API yêu cầu đăng nhập | `isUnauthorized()` trong API Basic/Bearer | `unauthenticated()` | Chưa có danh tính hợp lệ |
| User thường gọi endpoint admin | `isForbidden()` | `authenticated().withRoles("USER")` | Đã xác thực nhưng thiếu role |
| JWT hợp lệ thiếu scope | `isForbidden()` | `authenticated()` và kiểm tra scope hiện có | Đã xác thực nhưng thiếu authority |
| User có quyền phù hợp | `isOk()` | `authenticated().withRoles("ADMIN")` | Đã xác thực và được phép |
| Anonymous gọi endpoint `permitAll()` | Có thể `isOk()` | `unauthenticated()` | Endpoint công khai, không cần đăng nhập |

Với form login, anonymous request có thể nhận redirect `302` thay vì `401`. Hãy xác định response theo `SecurityFilterChain` và `AuthenticationEntryPoint` của ứng dụng.

## 3. Chuẩn bị ví dụ Servlet với MockMvc

### 3.1. Dependency và cấu hình kiểm thử

Ứng dụng Spring Boot Servlet cần `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` và dependency kiểm thử bảo mật:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Cấu hình test tích hợp:

```java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationDenialTest {

    @Autowired
    MockMvc mockMvc;
}
```

`@AutoConfigureMockMvc` tích hợp servlet filter chain của ứng dụng. Nếu tự dựng MockMvc bằng `MockMvcBuilders.webAppContextSetup(context)`, hãy áp dụng `.apply(springSecurity())`. Nếu filter chain không tham gia, test có thể trả kết quả không phản ánh chính sách bảo mật thực tế.

Các static import thường dùng:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

Các ví dụ lược bớt import thông thường. Tùy đoạn mã, cần thêm `Authentication`, `GrantedAuthority`, `SimpleGrantedAuthority`, `HttpStatus`, `HttpServletResponse`, `MediaType`, `JwtAuthenticationToken` và các lớp Spring/JUnit tương ứng.


### 3.2. Controller và policy

Giả sử API có một endpoint hồ sơ và một endpoint quản trị:

```java
@RestController
@RequestMapping("/api")
class ReportController {

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin/report")
    String adminReport() {
        return "admin-report";
    }
}
```

Chính sách:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Tài khoản demo:

```java
@Bean
UserDetailsService users() {
    return new InMemoryUserDetailsManager(
        User.withUsername("mai")
            .password("{noop}secret")
            .roles("USER")
            .build(),
        User.withUsername("quantri")
            .password("{noop}secret")
            .roles("ADMIN")
            .build()
    );
}
```

`{noop}` chỉ dành cho dữ liệu demo. Ứng dụng thực tế cần `PasswordEncoder` phù hợp. Quy tắc `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`.

## 4. Kiểm tra người dùng đã xác thực nhưng thiếu role

### 4.1. Dùng request post-processor user()

`user("mai").roles("USER")` tạo một danh tính thử nghiệm đã xác thực. Khi gọi endpoint yêu cầu ADMIN, request bị từ chối:

```java
@Test
void ordinaryUserIsAuthenticatedButCannotReadAdminReport() throws Exception {
    mockMvc.perform(get("/api/admin/report")
                .with(user("mai").roles("USER")))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withRoles("USER"));
}
```

Test này xác minh ba điều độc lập:

1. Endpoint từ chối request bằng HTTP 403.
2. Spring Security vẫn nhận diện người dùng `mai`.
3. Người dùng có role `USER`, không phải role `ADMIN` mà policy yêu cầu.

Đây là một test phân quyền; nó không xác minh mật khẩu vì `user()` đưa danh tính giả lập vào request.

### 4.2. Dùng @WithMockUser

Khi một phương thức test có nhiều request cần cùng một người dùng, `@WithMockUser` có thể làm setup gọn hơn:

```java
@Test
@WithMockUser(username = "mai", roles = "USER")
void mockUserRemainsAuthenticatedWhenAuthorizationFails() throws Exception {
    mockMvc.perform(get("/api/admin/report"))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withRoles("USER"));
}
```

`@WithMockUser` tạo `SecurityContext` thử nghiệm trước khi test chạy. Matcher trên kết quả request chứng minh danh tính giả lập đã được dùng trong lần gọi MockMvc. Nó không kiểm tra quá trình đăng nhập thực tế hoặc xác minh credentials.

### 4.3. So sánh với người có quyền

```java
@Test
void adminCanReadAdminReport() throws Exception {
    mockMvc.perform(get("/api/admin/report")
                .with(user("quantri").roles("ADMIN")))
           .andExpect(status().isOk())
           .andExpect(authenticated()
                   .withUsername("quantri")
                   .withRoles("ADMIN"))
           .andExpect(content().string("admin-report"));
}
```

Test thành công là đối chứng cho test bị từ chối. Nếu test user thường và admin đều trả 403, có thể cấu hình role, filter chain hoặc matcher đang sai.

## 5. Kiểm tra authority và scope thay vì chỉ role

Không phải mọi chính sách đều dùng role. Resource server thường dùng scope như `SCOPE_report:read`; ứng dụng nghiệp vụ có thể dùng permission `document:approve`.

Giả sử endpoint yêu cầu:

```java
.requestMatchers("/api/reports").hasAuthority("SCOPE_report:read")
```

JWT giả lập chỉ có scope ghi:

```java
@Test
void authenticatedJwtWithoutReadScopeIsForbidden() throws Exception {
    mockMvc.perform(get("/api/reports")
                .with(jwt()
                    .jwt(token -> token.subject("account-42"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_report:write"))))
           .andExpect(status().isForbidden())
           .andExpect(authenticated().withAuthentication(authentication -> {
               assertThat(authentication)
                       .isInstanceOf(JwtAuthenticationToken.class);
               assertThat(authentication.getAuthorities())
                       .extracting(GrantedAuthority::getAuthority)
                       .contains("SCOPE_report:write")
                       .doesNotContain("SCOPE_report:read");
           }));
}
```

Ở đây `jwt()` tạo một `JwtAuthenticationToken` giả lập. Test kiểm tra authorization sau khi danh tính JWT đã được thiết lập; nó không xác minh chữ ký, issuer, audience hoặc thời hạn của token. Nếu cần kiểm tra decoder/validator, phải có ca tích hợp gửi Bearer token qua resource server.

Nếu endpoint dùng permission tùy biến, kiểm tra authority đầy đủ:

```java
@Test
void authenticatedUserWithoutApprovePermissionIsForbidden() throws Exception {
    mockMvc.perform(post("/api/documents/42/approve")
                .with(user("mai").authorities(
                    new SimpleGrantedAuthority("document:read")))
                .with(csrf()))
           .andExpect(status().isForbidden())
           .andExpect(authenticated().withAuthentication(authentication -> {
               assertThat(authentication.getName()).isEqualTo("mai");
               assertThat(authentication.getAuthorities())
                       .extracting(GrantedAuthority::getAuthority)
                       .contains("document:read")
                       .doesNotContain("document:approve");
           }));
}
```

Ví dụ giả định endpoint POST có rule `hasAuthority("document:approve")`. CSRF token được thêm để test tập trung vào phân quyền; nếu cố ý kiểm tra CSRF thì bỏ `.with(csrf())` trong một test riêng.

## 6. Phân biệt Access Denied với CSRF rejection

Một request POST có thể bị chặn trước khi Spring Security đánh giá role/authority do thiếu CSRF token. Vì vậy, hai test có cùng status 403 nhưng mục tiêu khác nhau.

### 6.1. Thiếu role nhưng có CSRF token

```java
@Test
void userWithValidCsrfButWithoutAdminRoleGets403() throws Exception {
    mockMvc.perform(post("/api/admin/rebuild")
                .with(user("mai").roles("USER"))
                .with(csrf()))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withRoles("USER"));
}
```

Ở đây CSRF token hợp lệ, nên request có thể đi tiếp tới bước authorization. Policy yêu cầu ADMIN nhưng người dùng chỉ có USER.

### 6.2. Có role nhưng thiếu CSRF token

```java
@Test
void adminWithoutCsrfTokenIsRejected() throws Exception {
    mockMvc.perform(post("/api/admin/rebuild")
                .with(user("quantri").roles("ADMIN")))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("quantri")
                   .withRoles("ADMIN"));
}
```

Ở đây người dùng có role phù hợp, nhưng request vẫn có thể bị `CsrfFilter` từ chối vì thiếu token. Đây không phải bằng chứng rằng role ADMIN không đủ quyền; nó chứng minh lớp bảo vệ CSRF đang hoạt động.

Khi điều tra một test 403, hãy hỏi:

- Request có danh tính đã xác thực không?
- Rule URL hoặc method security yêu cầu authority nào?
- Request có bị CSRF filter hoặc filter tùy chỉnh chặn trước đó không?
- Có custom `AccessDeniedHandler` thay đổi status/body không?

## 7. Kiểm tra phân quyền ở method security

Phân quyền có thể được đặt ở URL hoặc trực tiếp trên method. Ví dụ service:

```java
@Service
class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String generateAdminReport() {
        return "admin-report";
    }
}
```

Ứng dụng cần bật method security:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Khi controller gọi service và người dùng không có role, exception từ method security thường được chuyển thành HTTP 403 qua Spring Security filter chain:

```java
@Test
@WithMockUser(username = "mai", roles = "USER")
void methodSecurityDeniesUserButKeepsAuthentication() throws Exception {
    mockMvc.perform(get("/api/admin/report"))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withRoles("USER"));
}
```

Test này cần controller thực sự gọi `ReportService.generateAdminReport()` và filter chain được tích hợp. Nếu test service trực tiếp thay vì MockMvc, hãy kiểm tra exception access-denied theo phiên bản Spring Security, thay vì mong có HTTP status.

Với Spring Security 6+, method security thường dùng `@EnableMethodSecurity`; cấu hình cũ `@EnableGlobalMethodSecurity` đã được thay thế. Hãy khớp API với phiên bản dự án.

## 8. Trường hợp remember-me và fully authenticated

Một sắc thái dễ bỏ sót: “đã xác thực” không phải lúc nào cũng đồng nghĩa “đã xác thực đầy đủ”. Spring Security phân biệt trạng thái anonymous, remember-me và fully authenticated thông qua `AuthenticationTrustResolver`.

- `authenticated()` trong result matcher xác nhận request có Authentication được xem là authenticated, không phải anonymous.
- Rule `fullyAuthenticated()` yêu cầu danh tính đã xác thực đầy đủ và loại trừ trạng thái remember-me.
- Một endpoint nhạy cảm có thể yêu cầu người dùng đăng nhập lại hoặc thực hiện xác thực mạnh hơn, dù phiên remember-me vẫn cho phép truy cập các endpoint thông thường.

Ví dụ policy:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/**").authenticated()
    .requestMatchers("/payments/confirm").fullyAuthenticated()
    .anyRequest().permitAll()
)
```

Không nên dùng một test `authenticated()` đơn lẻ để kết luận endpoint `fullyAuthenticated()` sẽ cho phép truy cập. Cần tạo test đúng loại Authentication/remember-me và khẳng định status theo policy. Khi request bị từ chối do chỉ có remember-me, framework có thể yêu cầu xác thực lại thông qua entry point thay vì xử lý giống một user thường thiếu role.

## 9. Kiểm tra AccessDeniedHandler và response lỗi

Khi request đã xác thực nhưng thiếu quyền, `AccessDeniedHandler` có thể trả 403 cùng error body riêng. Ví dụ handler API ghi JSON:

```java
http.exceptionHandling(exceptions -> exceptions
    .accessDeniedHandler((request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write("""
            {"code":"ACCESS_DENIED","message":"Insufficient permission"}
            """);
    })
);
```

Test có thể kiểm tra cả danh tính và hợp đồng response:

```java
@Test
@WithMockUser(username = "mai", roles = "USER")
void accessDeniedResponseIncludesStableErrorCode() throws Exception {
    mockMvc.perform(get("/api/admin/report")
                .accept(MediaType.APPLICATION_JSON))
           .andExpect(status().isForbidden())
           .andExpect(authenticated().withUsername("mai"))
           .andExpect(content().contentTypeCompatibleWith(
                   MediaType.APPLICATION_JSON))
           .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
}
```

Đoạn handler là ví dụ minh họa, cần điều chỉnh cho cách ghi response của ứng dụng. `AccessDeniedHandler` mặc định không bắt buộc tạo JSON có `code` như trên. Chỉ assert body sau khi custom handler đã được cấu hình.

## 10. JWT, OAuth2 và OIDC: danh tính có thể hợp lệ nhưng không đủ quyền

### 10.1. JWT hợp lệ nhưng thiếu scope

Trong resource server, scope thường được ánh xạ thành authority có tiền tố `SCOPE_`. Nếu endpoint yêu cầu `SCOPE_report:read`, token chỉ có `SCOPE_report:write` có thể được xác thực nhưng bị từ chối authorization.

Khi dùng `jwt()` trong MockMvc, test có thể khẳng định:

- Status là 403.
- `Authentication` là `JwtAuthenticationToken`.
- Subject đúng với token giả lập.
- Scope hiện có không chứa scope mà endpoint yêu cầu.

### 10.2. OAuth2/OIDC login thiếu role hoặc claim ánh xạ quyền

Với OAuth2 Login, principal có thể là `OAuth2User`; với OIDC Login, principal thường là `OidcUser`. Ứng dụng có thể ánh xạ group/claim từ provider thành authority. Nếu mapping thiếu group ADMIN, user vẫn đăng nhập thành công nhưng không được phép mở chức năng quản trị.

Test dùng `oauth2Login()` hoặc `oidcLogin()` có thể tạo principal và authorities giả lập để kiểm tra rule. Hãy khẳng định `OAuth2AuthenticationToken`/principal cùng authorities cần thiết khi đó là một phần yêu cầu. Các post-processor này không xác minh authorization code flow hoặc token thực từ provider.

## 11. Reactive: kiểm tra user bị từ chối với WebTestClient

`SecurityMockMvcResultMatchers` chỉ dành cho Servlet/MockMvc. Với WebFlux, dùng `WebTestClient` và `SecurityMockServerConfigurers`:

```java
webTestClient.mutateWith(mockUser("mai").roles("USER"))
             .get().uri("/api/admin/report")
             .exchange()
             .expectStatus().isForbidden();
```

Đoạn này giả định endpoint Reactive yêu cầu role ADMIN và WebTestClient đã được tích hợp Spring Security Reactive. `mockUser()` tạo danh tính thử nghiệm đã xác thực; status 403 cho thấy request không được phép.

WebTestClient không có matcher kết quả tương đương trực tiếp với `authenticated()` của MockMvc. Nếu cần kiểm tra danh tính/authority trong chính sách Reactive, có thể:

- Kiểm tra logic của `ReactiveAuthorizationManager` hoặc method security ở tầng phù hợp.
- Tạo một test-specific `ServerAccessDeniedHandler` để quan sát metadata cần thiết trong ngữ cảnh kiểm thử.
- Dùng endpoint chẩn đoán chỉ trong test để xác minh `ReactiveSecurityContextHolder`, không đưa endpoint nhạy cảm này vào production.

Với JWT Reactive, `mockJwt()` cũng tạo Authentication giả lập. Để xác minh decoder và token thực, cần test riêng đi qua resource server Reactive.

## 12. Ma trận assertion cho trường hợp bị từ chối

| Mục tiêu | Request post-processor / setup | Assertion chính |
| --- | --- | --- |
| Anonymous bị chặn khỏi API | Không thêm user/token | `status().isUnauthorized()` và `unauthenticated()` (với API Basic/Bearer) |
| User có role USER bị chặn khỏi admin | `user("mai").roles("USER")` | `isForbidden()` và `authenticated().withRoles("USER")` |
| User thiếu authority | `user(...).authorities(...)` | `isForbidden()` và `withAuthorities(...)`/`withAuthentication(...)` |
| JWT thiếu scope | `jwt()` với scope khác yêu cầu | `isForbidden()` và kiểm tra `JwtAuthenticationToken` |
| POST thiếu CSRF | Danh tính hợp lệ, không `.with(csrf())` | `isForbidden()` và matcher danh tính nếu có |
| POST đủ quyền, có CSRF | Danh tính có quyền và `.with(csrf())` | Status thành công và `authenticated()` |
| Remember-me không đạt fully authenticated | Authentication remember-me | Status/redirect theo entry point và policy |
| Method security từ chối | `@WithMockUser` không đủ role | `isForbidden()` và username/role |

Khi test một ca từ chối, hãy xác định **lớp nào từ chối request**. Cùng status 403 có thể đến từ URL authorization, method security, CSRF hoặc filter tùy chỉnh. Assertion danh tính và quyền hiện có giúp thu hẹp nguyên nhân.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `403` nhưng `unauthenticated()` fail | Request có danh tính đã xác thực | Dùng `authenticated()` và kiểm tra quyền |
| Chỉ assert `isForbidden()` | Chưa xác định danh tính hoặc lý do bị chặn | Thêm username, role/authority và response assertion |
| Dùng `withRoles("ROLE_USER")` | Nhầm role với authority đầy đủ | Dùng `withRoles("USER")`; `ROLE_USER` dành cho `withAuthorities(...)` |
| JWT mock bị từ chối dù token có scope | Authority được tạo không khớp policy | Kiểm tra prefix `SCOPE_` và mapping converter |
| POST trả 403 dù user có role | CSRF token thiếu hoặc sai | Thêm `.with(csrf())` khi muốn test business authorization |
| `@WithMockUser` không kiểm tra đăng nhập thực | Annotation tạo sẵn Authentication | Viết test credentials/HTTP token đi qua authentication filter |
| Method security không có tác dụng trong test | Chưa bật `@EnableMethodSecurity` hoặc controller không gọi bean được bảo vệ | Kiểm tra cấu hình và đường gọi thực tế |
| Test WebFlux dùng matcher MockMvc | Dùng nhầm API Servlet | Dùng WebTestClient và công cụ Reactive |

## 14. Bài tập thực hành

Dùng API quản trị và API báo cáo trong bài để thực hiện:

1. Tạo test user `mai` có `ROLE_USER` gọi `/api/admin/report`; xác nhận status 403, username `mai` và role USER.
2. Tạo test user `quantri` có `ROLE_ADMIN`; xác nhận request tới cùng endpoint trả 200.
3. Tạo endpoint yêu cầu `SCOPE_report:read`; gửi JWT giả lập chỉ có `SCOPE_report:write` và xác nhận 403 nhưng Authentication vẫn là `JwtAuthenticationToken`.
4. Tạo POST endpoint yêu cầu role ADMIN. So sánh test user ADMIN thiếu CSRF token với test user USER có CSRF token. Giải thích hai request bị từ chối ở hai lớp bảo vệ khác nhau.
5. Bật method security với `@PreAuthorize("hasRole('ADMIN')")`; kiểm tra service bị từ chối và controller chuyển kết quả thành HTTP 403.
6. Thử policy `fullyAuthenticated()` với trạng thái remember-me và giải thích vì sao `authenticated()` chưa đủ để mô tả chính sách đó.
7. Với WebFlux, dùng `mockUser("mai").roles("USER")` gọi endpoint yêu cầu ADMIN và xác nhận 403 bằng WebTestClient.

**Tiêu chí hoàn thành:** Người học chứng minh được request bị từ chối vẫn có thể mang danh tính đã xác thực; phân biệt được thiếu quyền với anonymous và CSRF; chọn đúng matcher cho role, authority hoặc token; và giải thích được sự khác nhau giữa Servlet và Reactive.

## Tài liệu tham khảo chính thức

- [Spring Security — Exception Translation](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Security MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
