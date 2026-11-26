# `withUsername`, `withRoles` và kiểm tra authorities theo API phù hợp

## 1. Mục tiêu của bài học

Khi viết kiểm thử bảo mật, việc xác nhận một request đã được xác thực mới là bước đầu. Người dùng có thể đăng nhập thành công nhưng hệ thống lại gắn sai tên tài khoản, cấp nhầm role `ADMIN` hoặc thiếu authority `SCOPE_report:read`. Những sai sót này có thể khiến endpoint trả về kết quả ngoài chính sách dự kiến.

Trong module **SPRING_SECURITY_TESTING**, chúng ta kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Chương **Khẳng định kết quả** tập trung vào cách kiểm tra kết quả sau request. Riêng bài này hướng dẫn ba nhóm khẳng định trên **Spring MVC/Servlet với `MockMvc`**:

- `authenticated().withUsername(...)`: kiểm tra danh tính của người dùng.
- `authenticated().withRoles(...)`: kiểm tra danh sách role theo tiền tố chuẩn `ROLE_`.
- `authenticated().withAuthorities(...)`: kiểm tra authority đầy đủ, bao gồm role, permission hoặc scope OAuth2.

Điểm quan trọng: các overload của `withAuthorities` **khác nhau theo phiên bản Spring Security**. Cần chọn đúng chữ ký API trước khi sao chép ví dụ vào dự án.

Kết thúc bài, bạn có thể phân biệt username, role và authority; viết phép kiểm tra trên một request thành công hoặc bị từ chối; và lựa chọn cách khẳng định phù hợp cho `@WithMockUser`, HTTP Basic và JWT/OAuth2/OIDC giả lập.

## 2. Ba khái niệm liên quan nhưng không đồng nghĩa

Một `Authentication` thường chứa principal, tên danh tính và tập hợp `GrantedAuthority`:

```mermaid
flowchart TD
    A["Authentication của request"] --> B["Principal / tên danh tính"]
    A --> C["Collection<GrantedAuthority>"]
    B --> D["withUsername(\"mai\")"]
    C --> E["ROLE_USER"]
    C --> F["SCOPE_report:read"]
    C --> G["document:approve"]
    E --> H["withRoles(\"USER\")"]
    E --> I["withAuthorities(...)"]
    F --> I
    G --> I
```

| Khía cạnh | Dữ liệu thường gặp | Matcher thích hợp | Cần lưu ý |
| --- | --- | --- | --- |
| Tên tài khoản | `mai`, `quantri`, `account-42` | `withUsername("mai")` | Không phải tên hiển thị của người dùng |
| Role | `USER`, `ADMIN` | `withRoles("USER")` | Matcher gắn tiền tố `ROLE_` theo quy ước mặc định |
| Authority của role | `ROLE_USER`, `ROLE_ADMIN` | `withAuthorities(...)` | Phải dùng giá trị đầy đủ |
| Scope của OAuth2/JWT | `SCOPE_report:read` | `withAuthorities(...)` | Scope không tự trở thành role |
| Quyền chi tiết của ứng dụng | `document:approve` | `withAuthorities(...)` | Không cần tiền tố `ROLE_` nếu policy dùng `hasAuthority` |

Theo quy ước phổ biến của Spring Security, `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN`; `hasAuthority("SCOPE_report:read")` kiểm tra đúng chuỗi `SCOPE_report:read`. Các so sánh này phân biệt hoa/thường. Một tên authority tùy biến có thể dùng tiền tố khác, nhưng cần khớp với cách ứng dụng cấu hình và tạo quyền.

Sự phân biệt này rất quan trọng khi một người dùng có nhiều quyền. Ví dụ:

```text
username: mai
authorities:
  - ROLE_USER
  - SCOPE_report:read
  - document:approve
```

Người dùng này có role `USER`, đồng thời có thêm một scope và một permission. Việc kiểm tra riêng `withRoles("USER")` không đủ để chứng minh cả hai quyền còn lại đã được cấp đúng.

## 3. Chuẩn bị `MockMvc` với Spring Security

Trong ứng dụng Spring Boot Servlet sử dụng `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-boot-starter-test`, cần thêm `spring-security-test` vào phạm vi test:

```xml
<!-- Maven: version được quản lý bởi Spring Boot BOM khi có -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Hoặc Gradle:

```groovy
testImplementation 'org.springframework.security:spring-security-test'
```

Cấu hình kiểm thử tích hợp phổ biến:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityResultTest {
    @Autowired MockMvc mockMvc;
}
```

Nếu tự dựng `MockMvc` bằng `MockMvcBuilders.webAppContextSetup(context)`, hãy dùng `.apply(springSecurity())` để gắn chuỗi filter bảo mật cùng cơ chế hỗ trợ `SecurityContext` thử nghiệm. Những `ResultMatcher` trong bài dành cho `MockMvc`; không gọi trực tiếp chúng trên `WebTestClient` của WebFlux.

Các import tĩnh cần thiết:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

### Một ứng dụng ví dụ

Giả sử có ba endpoint: xem thông tin chính mình, xem bảng quản trị và xem báo cáo. Controller dùng `Authentication` để trả về tên người dùng ở endpoint đầu tiên:

```java
@RestController
@RequestMapping("/api")
class ExampleController {

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin/dashboard")
    String dashboard() {
        return "admin-dashboard";
    }

    @GetMapping("/reports")
    String reports() {
        return "reports-ready";
    }
}
```

Áp dụng chính sách URL theo hai kiểu khác nhau: role và authority:

```java
@Configuration
class ExampleSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/admin/**").hasRole("ADMIN")
                    .requestMatchers("/api/reports").hasAuthority("SCOPE_report:read")
                    .requestMatchers("/api/**").authenticated()
                    .anyRequest().permitAll()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("mai")
                    .password("{noop}secret")
                    .authorities("ROLE_USER", "SCOPE_report:read")
                    .build()
        );
    }
}
```

Các lớp ví dụ cần nằm trong vùng quét component của ứng dụng Spring Boot. Để tập trung vào matcher, các import Java/Spring thông thường được lược bớt. `{noop}` chỉ dành cho dữ liệu demo; ứng dụng thực tế phải dùng phương pháp mã hóa mật khẩu phù hợp. HTTP Basic giúp phân biệt test dùng thông tin đăng nhập đi qua filter với test giả lập danh tính bằng `user()`.

## 4. `withUsername`: đúng tài khoản đã được nhận diện

`authenticated()` chỉ cho biết request có danh tính đã xác thực. `withUsername` bổ sung yêu cầu **danh tính đó phải đúng tên**:

```java
@Test
void basicAuthShouldIdentifyMai() throws Exception {
    mockMvc.perform(get("/api/me")
                .with(httpBasic("mai", "secret")))
           .andExpect(status().isOk())
           .andExpect(authenticated().withUsername("mai"))
           .andExpect(jsonPath("$.username").value("mai"));
}
```

Nếu hệ thống nhận nhầm một principal khác, phép kiểm tra username sẽ phát hiện lỗi ngay cả khi response vẫn trả `200`. Phép kiểm tra `jsonPath` giúp đối chiếu thêm dữ liệu JSON mà controller gửi về client.

Khi username được tạo sẵn bằng `@WithMockUser`, ý nghĩa sẽ khác:

```java
@Test
@WithMockUser(username = "mai", roles = "USER")
void mockIdentityShouldMatchUsername() throws Exception {
    mockMvc.perform(get("/api/me"))
           .andExpect(status().isOk())
           .andExpect(authenticated().withUsername("mai"));
}
```

Test này chứng minh endpoint xử lý đúng **danh tính giả lập** được Spring Security Test cung cấp; nó không kiểm tra quá trình xác minh mật khẩu. Khi cần xác minh đường đi thật của HTTP Basic, dùng `httpBasic(...)` như ví dụ trước.

Phân biệt thêm:

- `withUsername("mai")` kiểm tra username gắn với principal trong kết quả test.
- `withAuthenticationName("mai")` kiểm tra `Principal.getName()` của `Authentication` theo API matcher. Nó có ích khi cần làm rõ trường name được xác định bởi loại authentication cụ thể.
- Không đánh đồng username với tên đầy đủ, email hoặc mã nhân viên nếu principal của ứng dụng dùng một trường khác làm tên định danh.

Đối với JWT/OIDC, tên của `Authentication` có thể dựa trên `sub` hoặc một claim được cấu hình. Khi cần chắc chắn một claim cụ thể đúng, hãy kiểm tra trực tiếp principal/token thay vì mặc định claim `email` chính là username.

## 5. `withRoles`: xác minh role và tiền tố `ROLE_`

Một role được mô hình hóa bằng `GrantedAuthority`. Mặc định Spring Security sử dụng tiền tố `ROLE_`; phương thức `withRoles` **tự thêm** tiền tố này vào role được truyền vào.

```java
@Test
void adminRoleShouldAllowDashboard() throws Exception {
    mockMvc.perform(get("/api/admin/dashboard")
                .with(user("quantri").roles("ADMIN")))
           .andExpect(status().isOk())
           .andExpect(authenticated()
                   .withUsername("quantri")
                   .withRoles("ADMIN"))
           .andExpect(content().string("admin-dashboard"));
}
```

Ở đây `user("quantri").roles("ADMIN")` tạo authority `ROLE_ADMIN`. Bởi vậy matcher đúng là `withRoles("ADMIN")`, không phải `withRoles("ROLE_ADMIN")`. Việc viết thêm tiền tố thủ công dễ dẫn tới so khớp sai (ví dụ kỳ vọng `ROLE_ROLE_ADMIN`).

Nếu một người dùng có nhiều role:

```java
mockMvc.perform(get("/api/me")
            .with(user("linh").roles("USER", "AUDITOR")))
       .andExpect(status().isOk())
       .andExpect(authenticated()
               .withUsername("linh")
               .withRoles("USER", "AUDITOR"));
```

Với role ít nhất một quyền khác nhau, dùng bộ giá trị role mong đợi phù hợp, đừng dùng `withRoles("ADMIN")` chỉ vì một phần quyền trong hệ thống có chữ `ADMIN`.

**Hạn chế cần biết:** `withRoles` không phải công cụ kiểm kê mọi quyền. Ở dòng Spring Security 7.x, tài liệu API mô tả matcher này chỉ xác minh những authority bắt đầu bằng `ROLE_` và bỏ qua authority không phải role. Với dự án có hỗn hợp `ROLE_USER`, `SCOPE_report:read` và permission tùy biến, hãy dùng `withAuthorities(...)` hoặc assertion riêng trên `Authentication` để kiểm tra toàn bộ quyền. Không mặc định hành vi xử lý tập authority hỗn hợp của các phiên bản là giống hệt nhau.

## 6. `withAuthorities`: chọn đúng overload theo phiên bản

Authority là chuỗi mà `GrantedAuthority.getAuthority()` biểu diễn, chẳng hạn `ROLE_USER`, `SCOPE_report:read` hay `document:approve`. Khác `withRoles`, việc kiểm tra authority cần truyền **giá trị đầy đủ**, gồm tiền tố nếu có.

### 6.1. Ví dụ tương thích Spring Security 6.x và 7.x

Trong Spring Security **6.5.x**, `AuthenticatedMatcher` công khai overload:

```java
withAuthorities(Collection<? extends GrantedAuthority> expected)
```

Spring Security **7.x** vẫn có overload này. Vì vậy ví dụ sử dụng `List.of(new SimpleGrantedAuthority(...))` là lựa chọn dùng được ở cả hai dòng:

```java
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void reportAccessShouldHaveExactAuthorities() throws Exception {
    mockMvc.perform(get("/api/reports")
                .with(user("mai").authorities(
                        new SimpleGrantedAuthority("ROLE_USER"),
                        new SimpleGrantedAuthority("SCOPE_report:read"))))
           .andExpect(status().isOk())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withAuthorities(List.of(
                           new SimpleGrantedAuthority("ROLE_USER"),
                           new SimpleGrantedAuthority("SCOPE_report:read"))))
           .andExpect(content().string("reports-ready"));
}
```

`withAuthorities(Collection<? extends GrantedAuthority>)` dùng collection để đối chiếu `Authentication.getAuthorities()`. Khi muốn khẳng định **toàn bộ tập quyền dự kiến**, hãy liệt kê tất cả authority áp dụng cho request đó. Nếu trong chính sách có cả role và scope, đừng chỉ đưa role mà bỏ quên scope.

Đây cũng là cách tránh một lỗi biên dịch phổ biến trên Spring Security 6.x:

```java
// Sai trên Spring Security 6.5.x: chưa có overload với String...
// .andExpect(authenticated().withAuthorities("SCOPE_report:read"));

// Đúng trên 6.5.x và 7.x:
.andExpect(authenticated().withAuthorities(
        List.of(new SimpleGrantedAuthority("SCOPE_report:read"))));
```

Ví dụ thứ hai chỉ phù hợp với request có **duy nhất** authority `SCOPE_report:read`; nếu request còn `ROLE_USER` hoặc authority khác thì phải đưa chúng vào collection mong đợi hoặc chọn chiến lược kiểm tra một phần như mục 6.3.

### 6.2. Overload mới trên Spring Security 7.x

Ở Spring Security 7.x, API có thêm:

```java
withAuthorities(String... authorities)
```

Khi dự án đã dùng phiên bản hỗ trợ overload này, có thể viết gọn:

```java
mockMvc.perform(get("/api/reports")
            .with(user("mai").authorities(
                    new SimpleGrantedAuthority("ROLE_USER"),
                    new SimpleGrantedAuthority("SCOPE_report:read"))))
       .andExpect(status().isOk())
       .andExpect(authenticated().withAuthorities(
               "ROLE_USER", "SCOPE_report:read"));
```

Nếu IDE báo không có `withAuthorities(String...)`, hãy kiểm tra phiên bản **`spring-security-test`** thực tế trong classpath, vì bạn có thể đang dùng dòng 6.x. Đừng đoán phiên bản từ tài liệu đang mở trên web; hãy dùng Javadoc đúng phiên bản ứng dụng hoặc phiên bản do Spring Boot BOM quản lý.

Một overload khác `withRoles(String rolePrefix, String[] roles)` xuất hiện từ Spring Security 7.0, dành cho tiền tố role tùy biến. Không áp dụng ví dụ overload này cho Spring Security 6.x; với 6.x, khi hệ thống dùng authority khác tiền tố `ROLE_`, có thể kiểm tra bằng `withAuthorities`.

### 6.3. Chỉ cần kiểm tra một authority trong nhiều quyền

Đôi khi không cần khẳng định **toàn bộ collection** mà chỉ muốn chứng minh tài khoản có một scope nhất định, không có role nguy hiểm, hoặc các authority đến từ nhiều nguồn. Khi đó sử dụng `withAuthentication(Consumer<Authentication>)`:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.springframework.security.core.GrantedAuthority;

mockMvc.perform(get("/api/reports")
            .with(user("mai").authorities(
                    new SimpleGrantedAuthority("ROLE_USER"),
                    new SimpleGrantedAuthority("SCOPE_report:read"))))
       .andExpect(status().isOk())
       .andExpect(authenticated().withAuthentication(auth -> {
           assertThat(auth.getAuthorities())
               .extracting(GrantedAuthority::getAuthority)
               .contains("SCOPE_report:read")
               .doesNotContain("ROLE_ADMIN");
       }));
```

Điểm khác biệt: `contains(...)` ở đây chỉ kiểm tra quyền bắt buộc có mặt; `doesNotContain(...)` xác nhận quyền không được xuất hiện. Kiểu khẳng định này hữu ích khi tập quyền được bổ sung động hoặc khi muốn kiểm tra chính xác rủi ro leo thang đặc quyền, nhưng không thay thế được kiểm tra toàn bộ authority nếu hợp đồng bảo mật yêu cầu một tập quyền cố định.

### 6.4. Vai trò của `GrantedAuthority` phức tạp

`SimpleGrantedAuthority` phù hợp với role, scope và quyền được biểu diễn bằng chuỗi. Nếu ứng dụng tự xây một implementation `GrantedAuthority` chứa dữ liệu phức tạp, `getAuthority()` có thể trả về `null`. Khi đó không thể dựa vào phép so sánh chuỗi để hiểu toàn bộ chính sách; nên kiểm tra đối tượng authority thực tế bằng `withAuthentication(...)` và một assertion phù hợp với cấu trúc dữ liệu đó.

## 7. Các ca bị từ chối cũng cần kiểm tra danh tính và quyền

Trong nhiều hệ thống, hai request có cùng status `403` nhưng nguyên nhân khác nhau. Nếu `ROLE_USER` yêu cầu endpoint admin, người dùng có thể **đã được xác thực** nhưng không có `ROLE_ADMIN`:

```java
@Test
void ordinaryUserCannotOpenAdminDashboard() throws Exception {
    mockMvc.perform(get("/api/admin/dashboard")
                .with(user("mai").roles("USER")))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withRoles("USER"));
}
```

Nếu `/api/reports` yêu cầu scope `SCOPE_report:read`, người dùng chỉ có `SCOPE_report:write` bị từ chối:

```java
@Test
void userWithoutReadScopeCannotViewReports() throws Exception {
    mockMvc.perform(get("/api/reports")
                .with(user("mai").authorities(
                        new SimpleGrantedAuthority("SCOPE_report:write"))))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withAuthorities(List.of(
                           new SimpleGrantedAuthority("SCOPE_report:write"))));
}
```

Hai test kiểm chứng đồng thời status của policy và **quyền thực tế của request bị chặn**. Nếu chỉ kiểm tra `isForbidden()`, test không cho biết request thất bại do sai role, sai scope, CSRF hay filter khác.

Ngược lại, với request anonymous:

```java
mockMvc.perform(get("/api/admin/dashboard"))
       .andExpect(status().isUnauthorized())
       .andExpect(unauthenticated());
```

Với `httpBasic()` như cấu hình ví dụ, status anonymous là `401`. Trong ứng dụng dùng form login, request không đăng nhập thường bị chuyển hướng tới trang login; không mặc định `401` là kết quả của mọi cơ chế xác thực.

## 8. JWT, OAuth2/OIDC: kiểm tra đúng trường và loại quyền

Trong resource server, Spring Security thường ánh xạ scope thành authority có tiền tố `SCOPE_`. Chẳng hạn scope `report:read` có thể trở thành authority `SCOPE_report:read`. Request post-processor `jwt()` giúp mô phỏng principal JWT đã được xác thực:

```java
mockMvc.perform(get("/api/reports")
            .with(jwt()
                .jwt(token -> token.subject("account-42"))
                .authorities(new SimpleGrantedAuthority("SCOPE_report:read"))))
       .andExpect(status().isOk())
       .andExpect(authenticated()
               .withAuthorities(List.of(
                       new SimpleGrantedAuthority("SCOPE_report:read"))))
       .andExpect(authenticated().withAuthentication(auth -> {
           assertThat(auth).isInstanceOf(JwtAuthenticationToken.class);
           JwtAuthenticationToken jwtAuth = (JwtAuthenticationToken) auth;
           assertThat(jwtAuth.getToken().getSubject()).isEqualTo("account-42");
       }));
```

Ở đây `/api/reports` là endpoint trong ví dụ mục 3; để chạy riêng đoạn này, dự án cũng phải có các dependency JWT phù hợp. `jwt()` chỉ đưa token đã được giả lập vào `SecurityContext`, **không thực thi xác minh chữ ký, `iss`, `aud` hay `exp` như một request Bearer token thật**. Vì thế, dùng matcher để kiểm tra quyền sau ánh xạ và viết ca kiểm thử riêng cho quá trình xác minh JWT nếu đó là yêu cầu.

Với OAuth2/OIDC Login, `oauth2Login()` và `oidcLogin()` cũng tạo principal và authority phục vụ test. Tuy nhiên, `withUsername(...)` không nên bị dùng như cách mặc định để kiểm tra mọi claim của OIDC. Nếu yêu cầu là email, subject, issuer hoặc quyền riêng, hãy dùng `withAuthentication(...)` để lấy `OAuth2AuthenticationToken`/`OidcUser` và kiểm tra trực tiếp các giá trị đó.

Ví dụ minh họa khi endpoint `/api/oidc-profile` tồn tại và nhận OIDC principal:

```java
mockMvc.perform(get("/api/oidc-profile")
            .with(oidcLogin().idToken(id ->
                    id.claim("email", "mai@example.test"))))
       .andExpect(status().isOk())
       .andExpect(authenticated().withAuthentication(auth -> {
           assertThat(auth.getPrincipal()).isInstanceOf(OidcUser.class);
           OidcUser principal = (OidcUser) auth.getPrincipal();
           assertThat(principal.getEmail()).isEqualTo("mai@example.test");
       }));
```

Đây là tình huống mở rộng, không phải endpoint của controller mẫu; URL, các bộ lọc và cơ chế phân quyền phải phù hợp với ứng dụng cần kiểm thử. Kiểm thử giả lập OIDC không chứng minh toàn bộ authorization code flow hay xác minh ID Token của nhà cung cấp danh tính.

## 9. Khác biệt khi dùng WebTestClient trên Reactive

`authenticated().withUsername(...)`, `withRoles(...)` và `withAuthorities(...)` đang nói tới `SecurityMockMvcResultMatchers`, thuộc đường xử lý Servlet. **Không** chuyển nguyên các matcher này sang `WebTestClient` trong Spring WebFlux.

WebFlux sử dụng các cấu hình thử nghiệm như `SecurityMockServerConfigurers.mockUser()` và `mockJwt()`, kết hợp assertion HTTP và body của WebTestClient:

```java
// import static org.springframework.security.test.web.reactive.server
//     .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("mai").roles("USER"))
             .get().uri("/api/me")
             .exchange()
             .expectStatus().isOk()
             .expectBody()
             .jsonPath("$.username").isEqualTo("mai");
```

Đoạn này giả định một endpoint Reactive `/api/me` trả JSON có trường `username`. Muốn kiểm tra authority trong logic Reactive, có thể kiểm tra response phản ánh quyền được phép hoặc kiểm tra thành phần `ReactiveSecurityContextHolder` tại tầng service/controller bằng phương pháp phù hợp. `mockUser()` và `mockJwt()` chỉ giả lập danh tính; chúng không thay thế ca kiểm tra pipeline xác thực thật.

## 10. Cách đọc lỗi và thiết kế assertion có ý nghĩa

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `authenticated()` pass nhưng `withUsername` fail | Đã đăng nhập nhưng nhận nhầm principal, hoặc test kỳ vọng tên không đúng | Kiểm tra `Authentication` của request và trường định danh thực tế |
| `withRoles("ROLE_ADMIN")` fail | Đưa tiền tố `ROLE_` vào giá trị role | Dùng `withRoles("ADMIN")`; kiểm tra đủ authority với `ROLE_ADMIN` nếu cần |
| `withRoles("USER")` pass nhưng thiếu `SCOPE_report:read` | Chỉ kiểm tra role, không kiểm tra scope/permission | Thêm `withAuthorities(...)` hoặc assertion riêng với `withAuthentication(...)` |
| `withAuthorities("SCOPE_x")` không biên dịch | Dùng Spring Security 6.x, thiếu overload `String...` | Dùng `withAuthorities(List.of(new SimpleGrantedAuthority("SCOPE_x")))` |
| Request `403` dù `authenticated()` pass | Người dùng đã xác thực nhưng thiếu quyền hoặc bị chặn bởi lớp bảo vệ khác | So sánh `hasRole`, `hasAuthority`, CSRF và các handler tùy chỉnh |
| Test giả lập `jwt()` pass nhưng token HTTP thật thất bại | Giả lập bỏ qua việc xác minh chữ ký/claim theo decoder | Viết thêm ca gửi Bearer token qua filter và `JwtDecoder` |
| Matcher đúng nhưng endpoint không có policy như dự kiến | `MockMvc` không gắn filter chain hoặc test dùng cấu hình khác | Tích hợp Spring Security với MockMvc và kiểm tra cấu hình test |

### Checklist khi viết một phép kiểm tra kết quả bảo mật

1. **Xác định danh tính kỳ vọng**: người dùng là ai (`withUsername`) hay đối tượng token/claim nào (`withAuthentication`).
2. **Xác định policy**: endpoint yêu cầu role qua `hasRole` hay authority qua `hasAuthority`.
3. **Chọn API khớp với chính sách**: `withRoles` cho role mặc định; `withAuthorities` cho authority đầy đủ; lambda khi cần kiểm tra một phần hoặc cấu trúc đặc biệt.
4. **Đối chiếu phiên bản**: với Spring Security 6.x, dùng overload collection của `withAuthorities`; overload chuỗi có ở 7.x.
5. **Kiểm tra status và payload riêng**: `authenticated()` không tự chứng minh được phép truy cập và `status().isOk()` không tự chứng minh danh tính.

Không nên so sánh toàn bộ `Authentication` khi mục tiêu chỉ là username hoặc một authority. Principal có thể chứa dữ liệu runtime như details, token, session; assertion quá rộng dễ trở nên giòn và không phản ánh yêu cầu nghiệp vụ.

## 11. Bài tập áp dụng

Từ controller ví dụ, thực hiện các yêu cầu sau:

1. Thêm tài khoản `quantri` với role `ADMIN`. Viết test được phép truy cập `/api/admin/dashboard`, kiểm tra đồng thời `status().isOk()`, `withUsername("quantri")` và `withRoles("ADMIN")`.
2. Tạo một người dùng có `ROLE_USER` và `SCOPE_report:read`. Viết test cho `/api/reports` bằng overload collection của `withAuthorities`; sau đó thêm `document:approve` vào tài khoản và điều chỉnh assertion để phản ánh đúng tập quyền.
3. Viết test `/api/reports` với chỉ `SCOPE_report:write`, kỳ vọng `403` và xác nhận rằng danh tính vẫn được xác thực. Giải thích tại sao kiểm tra `withRoles("USER")` sẽ không trả lời đủ câu hỏi về scope.
4. Viết hai đoạn assertion cùng ý nghĩa cho Spring Security 6.x và 7.x. Chỉ ra đoạn nào sử dụng `withAuthorities(Collection<? extends GrantedAuthority>)`, đoạn nào sử dụng `withAuthorities(String...)`.
5. Với JWT giả lập, kiểm tra `sub=account-42`, authority `SCOPE_report:read` và giải thích giới hạn của phép kiểm thử đối với chữ ký JWT.

**Tiêu chí hoàn thành:** Người học chọn đúng matcher cho từng loại dữ liệu, lý giải được tiền tố `ROLE_`, xử lý đúng sự khác biệt overload giữa Spring Security 6.x và 7.x, đồng thời kiểm tra cả kết quả HTTP và thông tin bảo mật của request.

## Tài liệu tham khảo chính thức

- [Spring Security — SecurityMockMvcResultMatchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security 6.5 — AuthenticatedMatcher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/response/SecurityMockMvcResultMatchers.AuthenticatedMatcher.html)
- [Spring Security 7.x — AuthenticatedMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/response/SecurityMockMvcResultMatchers.AuthenticatedMatcher.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing OAuth2/OIDC/JWT](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
