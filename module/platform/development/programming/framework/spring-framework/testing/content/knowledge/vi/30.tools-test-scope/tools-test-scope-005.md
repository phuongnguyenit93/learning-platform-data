# Spring Security Test là tích hợp riêng khi cần xác nhận xác thực và phân quyền

Spring MVC và WebFlux có thể xử lý request mà không cần bật Spring Security. Khi ứng dụng có xác thực hoặc phân quyền, test cần đưa security filter chain và `SecurityContext` vào đúng luồng request. Module `spring-security-test` cung cấp các công cụ riêng để chuẩn bị danh tính người dùng, token, CSRF token và tích hợp Spring Security với MockMvc hoặc WebTestClient.

Đây là dependency test riêng. `spring-boot-starter-test` cung cấp nền tảng kiểm thử phổ biến, nhưng không tự động thay thế việc khai báo `spring-security-test`. Chỉ cần thêm module này khi test cần xác nhận hành vi bảo mật của ứng dụng.

## 1. Spring Security Test giải quyết vấn đề gì?

Một test controller thông thường có thể chỉ kiểm tra dữ liệu trả về. Nhưng khi ứng dụng có security, kết quả của request còn phụ thuộc vào danh tính đã xác thực, authorities, CSRF token và các quy tắc truy cập.

Spring Security Test giúp test mô phỏng hoặc cung cấp những thông tin đó một cách có kiểm soát:

- Tạo người dùng đã xác thực với username, role hoặc authority cụ thể.
- Dùng `UserDetailsService` thật của test context để nạp một user.
- Chuẩn bị anonymous user, JWT hoặc OAuth2 authentication trong phạm vi test.
- Gửi CSRF token hợp lệ hoặc không hợp lệ.
- Đưa Spring Security filter chain vào MockMvc hoặc WebTestClient.
- Đặt `SecurityContext` cho test method để kiểm tra method security như `@PreAuthorize`.

Các công cụ này cho phép kiểm tra những quyết định bảo mật mà ứng dụng đưa ra. Cần phân biệt test dùng danh tính giả lập với test xác nhận quy trình đăng nhập hoặc xác minh token thực tế; mỗi cách trả lời một câu hỏi khác nhau.

## 2. Thêm dependency riêng

Với Gradle:

```groovy
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Quản lý version `spring-security-test` đồng bộ với Spring Security đang dùng trong ứng dụng. Nếu dự án dùng Spring Boot dependency management hoặc Spring Security BOM, nên để BOM quản lý version để tránh lệch API giữa các module.

`spring-security-test` là dependency phục vụ test. Không cần đưa nó vào runtime classpath của ứng dụng production.

## 3. Tích hợp Spring Security với MockMvc

Với ứng dụng Spring MVC, MockMvc phải chạy qua security filter chain nếu muốn xác nhận authentication và authorization ở tầng HTTP. Khi dựng MockMvc thủ công từ `WebApplicationContext`, áp dụng configurer `springSecurity()`:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

`springSecurity()` kết nối MockMvc với các thành phần Spring Security được cấu hình trong application context, bao gồm filter chain và cơ chế lưu/khôi phục security context thích hợp cho test.

Với Spring Boot, `@AutoConfigureMockMvc` thường đăng ký các filter từ application context vào MockMvc theo mặc định:

```java
@SpringBootTest
@AutoConfigureMockMvc
class AccountControllerSecurityTests {

    @Autowired
    MockMvc mockMvc;
}
```

Nếu đặt `@AutoConfigureMockMvc(addFilters = false)`, các servlet filter trong context sẽ không tham gia request MockMvc. Cấu hình đó có thể hữu ích cho test MVC không xét filter, nhưng sẽ làm test mất khả năng xác nhận hành vi của Spring Security filter chain. Không tắt filter trong test đang kiểm tra bảo mật.

Với `@WebMvcTest`, kiểm tra xem security configuration có nằm trong slice hay chưa. Có thể cần import cấu hình bảo mật của ứng dụng bằng `@Import(SecurityConfig.class)` để test chạy đúng các rule thực tế.

## 4. Tạo người dùng giả lập bằng @WithMockUser

`@WithMockUser` đặt một `Authentication` giả lập vào `SecurityContext` trước khi test method chạy. Đây là cách ngắn gọn để kiểm tra authorization mà không cần thực hiện quy trình đăng nhập.

```java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanReadReports() throws Exception {
    mockMvc.perform(get("/admin/reports"))
            .andExpect(status().isOk());
}
```

Trong ví dụ, Spring Security Test tạo người dùng `alice` với authority `ROLE_ADMIN`. Thuộc tính `roles` tự thêm tiền tố `ROLE_`. Vì vậy `roles = "ADMIN"` tương ứng với `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")`.

Có thể khai báo nhiều role:

```java
@WithMockUser(username = "alice", roles = {"ADMIN", "AUDITOR"})
```

Hoặc khai báo authority chính xác:

```java
@Test
@WithMockUser(username = "report-reader",
        roles = {},
        authorities = {"reports:read", "orders:view"})
void userWithReportAuthorityCanReadReports() throws Exception {
    mockMvc.perform(get("/reports"))
            .andExpect(status().isOk());
}
```

`roles` và `authorities` là hai cách khai báo authority khác nhau; không dùng đồng thời trong cùng annotation. `authorities` giữ nguyên tên được cung cấp và không tự thêm `ROLE_`.

Nếu không khai báo username, Spring Security Test dùng tên mặc định `user`; role mặc định là `USER`. Nên khai báo rõ danh tính và quyền trong test để ý định của test dễ đọc.

## 5. Kiểm tra cả trường hợp được phép và bị từ chối

Một test authorization tốt thường có cả trường hợp có quyền và không có quyền. Ví dụ endpoint chỉ cho phép ADMIN:

```java
@Test
@WithMockUser(roles = "ADMIN")
void adminCanOpenAdminPage() throws Exception {
    mockMvc.perform(get("/admin"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(roles = "USER")
void regularUserCannotOpenAdminPage() throws Exception {
    mockMvc.perform(get("/admin"))
            .andExpect(status().isForbidden());
}
```

Kết quả 403 cho biết người dùng đã được xác thực nhưng không đủ quyền. Nếu request không có danh tính xác thực và endpoint yêu cầu login, kết quả thường là 401 hoặc redirect đến trang đăng nhập tùy cơ chế authentication và cấu hình ứng dụng.

Phân biệt hai tình huống này giúp test mô tả đúng rule:

| Trạng thái | Ý nghĩa thường gặp | Kết quả thường thấy |
|---|---|---|
| Chưa xác thực | Chưa có Authentication hợp lệ | 401 hoặc redirect tới login |
| Đã xác thực, thiếu quyền | Authentication có nhưng authorities không đáp ứng rule | 403 Forbidden |
| Đã xác thực, đủ quyền | Authentication và authority đáp ứng rule | Endpoint xử lý bình thường |

Không nên chỉ kiểm tra status của một trường hợp thành công. Một rule phân quyền cần chứng minh rằng user đúng được phép và user không đủ quyền bị từ chối.

## 6. Dùng @WithUserDetails khi cần user từ UserDetailsService

`@WithMockUser` tạo `User` giả lập trực tiếp. Nếu test cần sử dụng user được nạp từ `UserDetailsService` của ứng dụng, dùng `@WithUserDetails`:

```java
@Test
@WithUserDetails("alice")
void usesUserLoadedByUserDetailsService() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isOk());
}
```

Test context phải có `UserDetailsService` và user `alice` tồn tại trong nguồn dữ liệu mà service đó sử dụng. Điều này hữu ích khi authorities được gán động theo dữ liệu test hoặc ứng dụng có custom `UserDetails`.

Có thể chỉ định bean name nếu context có nhiều `UserDetailsService`:

```java
@WithUserDetails(value = "alice", userDetailsServiceBeanName = "accountUserDetailsService")
```

`@WithAnonymousUser` có thể dùng để chạy một method với anonymous authentication, ví dụ khi class có `@WithMockUser` nhưng một test cần xác nhận truy cập ẩn danh:

```java
@Test
@WithAnonymousUser
void anonymousUserCannotOpenProfile() throws Exception {
    mockMvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
}
```

Status cụ thể còn phụ thuộc vào entry point của ứng dụng; nếu ứng dụng chuyển hướng tới trang login, hãy assertion theo redirect contract đó.

## 7. Đặt user trực tiếp trên từng request bằng user(...)

Thay vì annotation trên test method, có thể dùng `RequestPostProcessor` để gắn danh tính cho một request cụ thể:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/admin").with(user("alice").roles("ADMIN")))
        .andExpect(status().isOk());
```

Cách này hữu ích khi một test gửi nhiều request với các danh tính khác nhau:

```java
@Test
void comparesTwoUsers() throws Exception {
    mockMvc.perform(get("/reports").with(user("alice").roles("ADMIN")))
            .andExpect(status().isOk());

    mockMvc.perform(get("/reports").with(user("bob").roles("USER")))
            .andExpect(status().isForbidden());
}
```

Có thể truyền một `UserDetails` đã tạo sẵn:

```java
UserDetails account = User.withUsername("alice")
        .password("unused")
        .authorities("reports:read")
        .build();

mockMvc.perform(get("/reports").with(user(account)))
        .andExpect(status().isOk());
```

`user(...)` chuẩn bị một authentication cho test. Nó không chạy password encoder, không xác minh mật khẩu và không kiểm tra form login hoặc HTTP Basic authentication mechanism. Dùng nó để tập trung vào authorization rules phía sau khi danh tính đã được thiết lập.

## 8. Kiểm tra CSRF token

Khi CSRF protection được bật, request thay đổi trạng thái như POST, PUT, PATCH hoặc DELETE thường phải mang CSRF token hợp lệ. Spring Security Test cung cấp `csrf()` để thêm token vào request MockMvc:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

mockMvc.perform(post("/profile")
        .with(user("alice"))
        .with(csrf())
        .param("displayName", "Alice"))
        .andExpect(status().is3xxRedirection());
```

Có thể đặt token trong header thay vì request parameter:

```java
mockMvc.perform(post("/profile")
        .with(user("alice"))
        .with(csrf().asHeader())
        .param("displayName", "Alice"))
        .andExpect(status().is3xxRedirection());
```

Kiểm tra request thiếu token hoặc có token không hợp lệ:

```java
mockMvc.perform(post("/profile")
        .with(user("alice"))
        .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
```

Khi test POST nhận 403, hãy xác định nguyên nhân là CSRF hay authorization. Nếu mục tiêu test là quyền truy cập endpoint và CSRF đang bật, cung cấp token hợp lệ bằng `csrf()` để request đi qua bước CSRF rồi mới kiểm tra rule phân quyền. Tạo một test riêng cho trường hợp thiếu hoặc sai CSRF token.

## 9. Kiểm tra HTTP Basic và cơ chế xác thực thật

Nếu mục tiêu là xác nhận HTTP Basic authentication filter xử lý credential, dùng processor `httpBasic(...)` thay cho `user(...)`:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;

mockMvc.perform(get("/account").with(httpBasic("alice", "correct-password")))
        .andExpect(status().isOk());
```

Request được gửi với HTTP Basic credentials để security filter chain thực hiện authentication theo cấu hình của ứng dụng. Test cần có `AuthenticationManager` và `UserDetailsService` hoặc provider phù hợp trong context.

So sánh:

| Cách chuẩn bị | Điều được thiết lập | Điều test có thể xác nhận |
|---|---|---|
| `user("alice")` | Authentication giả lập trong request | Authorization rules với danh tính và quyền đã cho |
| `@WithMockUser` | SecurityContext giả lập quanh test method | Method security hoặc logic cần SecurityContext |
| `httpBasic("alice", "...")` | HTTP Basic credentials trên request | Basic authentication filter và bước xác thực credential trong chain |
| `@WithUserDetails("alice")` | User được nạp qua UserDetailsService | Authorities và custom user details từ nguồn user test |

Kể cả `httpBasic(...)`, test MockMvc vẫn không mở cổng HTTP thật. Nó kiểm tra filter chain và authentication provider trong test context. Nếu cần kiểm tra TLS, reverse proxy hoặc hành vi mạng, cần integration test qua server thật.

## 10. Kiểm thử JWT và OAuth2

Với Resource Server dùng JWT, Spring Security Test cung cấp `jwt()` để tạo một JWT authentication giả lập cho request:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

Có thể tùy chỉnh claim hoặc subject:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().jwt(token -> token
                .subject("alice")
                .claim("tenant", "tenant-42"))
                .authorities(new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

Đối với OAuth2 Login, có các processor như `oauth2Login()`; với opaque token resource server, có `opaqueToken()`. Chúng chuẩn bị authentication tương ứng để kiểm tra phần authorization của request.

JWT được tạo bởi test processor không chứng minh ứng dụng xác minh chữ ký, issuer, audience hoặc gọi đúng `JwtDecoder`. Nếu mục tiêu là kiểm tra xác minh token thực, cần test `JwtDecoder`/authentication converter hoặc gửi token ký bằng test key qua cấu hình resource server thật.

## 11. Tích hợp với WebTestClient cho WebFlux

Ứng dụng WebFlux dùng `WebTestClient` có bộ configurer riêng của Spring Security Test. Khi dựng client từ application context, áp dụng `springSecurity()`:

```java
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .build();
```

Có thể gắn mock user cho một request:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser().roles("ADMIN"))
        .get()
        .uri("/admin")
        .exchange()
        .expectStatus().isOk();
```

Với test WebFlux, dùng `mutateWith(...)` để áp dụng configurer của WebTestClient. Không dùng `RequestPostProcessor` của MockMvc cho WebTestClient vì hai API thuộc hai stack khác nhau.

Nếu dùng Spring Boot test với server reactive, có thể inject WebTestClient đã được cấu hình bởi Boot. Khi cần kiểm tra security filter chain, bảo đảm test thực sự đi qua cấu hình security của ứng dụng; test bind trực tiếp vào một controller mà không thêm security config sẽ không xác nhận các rule đó.

## 12. Kiểm tra method security

Spring Security Test cũng hữu ích khi ứng dụng bảo vệ service method bằng `@PreAuthorize` hoặc `@PostAuthorize`. Test cần bật method security trong cấu hình Spring:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Service:

```java
@Service
class ReportService {

    @PreAuthorize("hasAuthority('reports:read')")
    public Report loadReport(String id) {
        return new Report(id);
    }
}
```

Test dùng `@WithMockUser` để thiết lập SecurityContext trước khi gọi service:

```java
@SpringJUnitConfig(classes = {MethodSecurityConfig.class, ReportService.class})
class ReportServiceSecurityTests {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(roles = {}, authorities = "reports:read")
    void userWithAuthorityCanLoadReport() {
        assertThat(reportService.loadReport("R-42").id()).isEqualTo("R-42");
    }

    @Test
    @WithMockUser(roles = {}, authorities = "profile:read")
    void userWithoutAuthorityIsDenied() {
        assertThatThrownBy(() -> reportService.loadReport("R-42"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

Test này xác nhận method security interceptor thực thi rule trên service. Nó không cần MockMvc vì không kiểm tra HTTP request; nếu cần kiểm tra cả endpoint lẫn method security, có thể kết hợp context web và MockMvc.

## 13. Tạo annotation bảo mật riêng cho test

Nếu nhiều test dùng cùng một nhóm quyền, có thể tạo meta-annotation để giảm lặp:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@WithMockUser(username = "report-admin", roles = {}, authorities = "reports:admin")
public @interface WithReportAdmin {}
```

Sử dụng:

```java
@Test
@WithReportAdmin
void reportAdminCanManageReports() throws Exception {
    mockMvc.perform(delete("/reports/42"))
            .andExpect(status().isNoContent());
}
```

Với security context phức tạp hơn, có thể tạo annotation dùng `@WithSecurityContext` và một `WithSecurityContextFactory` để dựng principal hoặc authentication domain-specific. Đây là cách phù hợp khi ứng dụng có custom principal chứa tenant, organization hoặc dữ liệu người dùng.

## 14. Spring Security Test không tự kiểm tra mọi thứ

Chọn test helper theo câu hỏi cần xác nhận:

| Câu hỏi | Công cụ phù hợp |
|---|---|
| User có authority A truy cập endpoint được không? | `@WithMockUser`, `user(...)` hoặc `mockUser()` |
| User không có authority có bị từ chối không? | Mock user với quyền thiếu và assertion 403/AccessDenied |
| User được nạp từ UserDetailsService có quyền gì? | `@WithUserDetails` |
| HTTP Basic filter xác thực credential ra sao? | `httpBasic(...)` với security chain và provider thật trong test context |
| Request có bị từ chối khi thiếu CSRF token không? | `csrf()` và `csrf().useInvalidToken()` |
| JWT authentication có authority nào? | `jwt()` cho authorization; test riêng decoder khi cần xác minh token |
| Service method có được bảo vệ bởi @PreAuthorize không? | `@WithMockUser` cùng `@EnableMethodSecurity` |

`@WithMockUser`, `user(...)`, `jwt()` và `mockUser()` thường tạo authentication giả lập. Chúng rất hữu ích để kiểm tra rule phân quyền, nhưng không chứng minh mật khẩu, chữ ký token, quy trình OAuth2 redirect hoặc việc lấy user từ hệ thống thật hoạt động đúng.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Request luôn bị 401/redirect dù có @WithMockUser | MockMvc không chạy qua Spring Security integration hoặc test context thiếu security configuration | Dùng `.apply(springSecurity())` hoặc cấu hình Boot với filter registration được bật |
| Request bị 403 dù user có role | Nhầm `roles` với `authorities`, hoặc role cần tiền tố `ROLE_` | Kiểm tra `hasRole`/`hasAuthority` và tên authority thực tế |
| POST bị 403 trong test | CSRF protection đang bật và request thiếu token | Thêm `.with(csrf())`; tạo test riêng cho token sai/thiếu |
| @WithUserDetails không tìm thấy user | User không có trong UserDetailsService của test context | Seed user hoặc dùng `@WithMockUser` nếu chỉ cần test authorization |
| `httpBasic(...)` vẫn không xác thực | Basic authentication chưa được bật hoặc provider không chấp nhận credentials | Kiểm tra filter chain, AuthenticationManager, password encoder và test user |
| JWT test pass dù token chữ ký sai | `jwt()` tạo authentication giả lập, bỏ qua bước decode/xác minh chữ ký | Viết test decoder hoặc integration test với JWT ký bằng test key |
| WebTestClient không nhận mock user | Dùng processor dành cho MockMvc hoặc chưa apply reactive security configurer | Dùng `springSecurity()` và `mutateWith(mockUser())` |
| Method security không chặn lời gọi | Chưa bật `@EnableMethodSecurity` hoặc gọi method không qua proxy | Bật method security và gọi bean được Spring quản lý |

## 16. Ghi nhớ

`spring-security-test` là module riêng dùng khi test cần xác nhận authentication, authorization, CSRF hoặc method security. Với MockMvc, tích hợp filter chain bằng `springSecurity()` và chuẩn bị user bằng `@WithMockUser`, `@WithUserDetails`, `user(...)`, `httpBasic(...)` hoặc `jwt()`. Với WebFlux, áp dụng reactive `springSecurity()` configurer và dùng `mutateWith(mockUser())`. Các danh tính giả lập giúp kiểm tra authorization nhanh, còn quy trình xác thực thật như password, JWT signature hoặc OAuth2 login cần test riêng. Luôn kiểm tra cả trường hợp được phép và bị từ chối để bảo đảm security rule hoạt động đúng.

