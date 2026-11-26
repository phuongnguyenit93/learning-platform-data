# HTTP 401, 403 và chuyển hướng đăng nhập theo cấu hình ứng dụng

## 1. Mục tiêu: kiểm tra đúng lý do request bị từ chối

Khi kiểm thử Spring Security, một request bị từ chối có thể kết thúc bằng nhiều phản hồi khác nhau. API dùng HTTP Basic hoặc Bearer token thường trả **401 Unauthorized** khi request chưa có thông tin xác thực hợp lệ. Người dùng đã đăng nhập nhưng thiếu quyền thường nhận **403 Forbidden**. Ứng dụng web dùng form login có thể chuyển hướng người chưa đăng nhập tới trang đăng nhập bằng HTTP **302 Found**.

Những phản hồi này thể hiện các giai đoạn khác nhau trong chuỗi bảo mật. Nếu test chỉ khẳng định “request không thành công”, nó có thể bỏ sót việc ứng dụng đang từ chối đúng hay sai lý do. Ví dụ, endpoint chỉ dành cho quản trị viên phải trả 403 với tài khoản thường đã xác thực; nếu lại trả 401, có thể cơ chế xác thực hoặc cách cấu hình exception đang không như mong đợi.

Trong module **SPRING_SECURITY_TESTING**, người học dùng spring-security-test để kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế trên Servlet và Reactive. Bài thuộc chương **Khẳng định kết quả** này tập trung vào MockMvc và cách kết hợp matcher HTTP với matcher trạng thái bảo mật để xác minh:

- 401 khi request chưa xác thực hoặc thông tin xác thực không hợp lệ.
- 403 khi danh tính đã được xác thực nhưng không đáp ứng chính sách truy cập, hoặc request bị chặn bởi một cơ chế bảo vệ như CSRF.
- 302 hoặc một phản hồi chuyển hướng khác khi ứng dụng web đưa người dùng tới trang đăng nhập.
- Sự khác nhau giữa kết quả mặc định và kết quả do AuthenticationEntryPoint, AccessDeniedHandler hoặc cấu hình login tùy chỉnh quyết định.

## 2. Phân biệt 401, 403 và redirect

### 2.1. HTTP 401: cần xác thực

401 Unauthorized thường xuất hiện khi request truy cập tài nguyên được bảo vệ nhưng chưa cung cấp credentials hợp lệ. Trong Spring Security, ExceptionTranslationFilter chuyển tình huống cần bắt đầu xác thực tới AuthenticationEntryPoint.

Ví dụ:

- API HTTP Basic nhận request không có header Authorization.
- API HTTP Basic nhận username/password không hợp lệ.
- Resource server nhận request không có Bearer token.
- Resource server không chấp nhận token vì token hết hạn, sai chữ ký hoặc không hợp lệ theo decoder/validator.

Với HTTP Basic, entry point mặc định thường trả 401 và header WWW-Authenticate: Basic ... . Với resource server Bearer token, entry point thường trả 401 và challenge bắt đầu bằng Bearer. Nội dung header cụ thể phụ thuộc cơ chế và lỗi xác thực; không nên đóng đinh toàn bộ chuỗi challenge nếu ứng dụng có cấu hình riêng.

### 2.2. HTTP 403: đã xác thực nhưng không được phép

403 Forbidden thường có nghĩa request không được phép truy cập tài nguyên. Trường hợp điển hình là Authentication đã hợp lệ nhưng authority không đáp ứng rule:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Nếu người dùng có ROLE_USER gọi /api/admin/report, Spring Security từ chối truy cập. Với request có danh tính đã xác thực, ExceptionTranslationFilter chuyển AccessDeniedException tới AccessDeniedHandler. Handler mặc định cho Servlet thường gửi status 403.

Tuy nhiên, không thể kết luận mọi phản hồi 403 đều là “người dùng đã đăng nhập nhưng thiếu role”. Một request thiếu CSRF token cũng có thể bị CsrfFilter chặn bằng 403 trước khi kiểm tra quyền URL. Một số filter tùy chỉnh cũng có thể gửi 403 trực tiếp. Vì vậy cần kiểm tra cả trạng thái xác thực và chính sách liên quan trong từng test.

### 2.3. Redirect đăng nhập: cách phản hồi của ứng dụng web

Một ứng dụng dùng formLogin() thường muốn trình duyệt hiển thị trang đăng nhập thay vì JSON lỗi. Khi anonymous user truy cập trang cần xác thực, LoginUrlAuthenticationEntryPoint thường chuyển hướng tới /login bằng 302.

Spring Security có thể lưu request ban đầu vào request cache. Sau khi đăng nhập thành công, ứng dụng thường chuyển người dùng về URL đã yêu cầu trước đó. Nếu không có request đã lưu, đích chuyển hướng mặc định thường là /. Login page, success handler, failure handler và request cache đều có thể thay đổi hành vi này.

| Tình huống | Kết quả thường gặp | Thành phần liên quan |
| --- | --- | --- |
| Anonymous gọi API HTTP Basic được bảo vệ | 401 | BasicAuthenticationEntryPoint |
| Anonymous gọi API Bearer được bảo vệ | 401 | BearerTokenAuthenticationEntryPoint |
| Anonymous gọi trang web được bảo vệ với form login | 302 tới login page | LoginUrlAuthenticationEntryPoint |
| Credentials HTTP Basic sai | 401 | Cơ chế xác thực Basic và entry point |
| Đã xác thực nhưng thiếu role | 403 | AccessDeniedHandler |
| Đã xác thực nhưng thiếu scope JWT | 403 | Authorization rule và access denied handler |
| Request thiếu CSRF token khi CSRF bật | Thường 403 | CsrfFilter và access denied handling |
| Đăng nhập form thành công | Thường 302 | AuthenticationSuccessHandler |
| Đăng nhập form thất bại | Thường 302 về login page có error | AuthenticationFailureHandler |

Đây là hành vi thường gặp với cấu hình mặc định. Mã HTTP cuối cùng phải được xác định theo filter chain và handler mà ứng dụng đang sử dụng.

## 3. Chuẩn bị MockMvc và các matcher

Với ứng dụng Spring Boot Servlet, thêm dependency test:

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
class SecurityHttpResultTest {

    @Autowired
    MockMvc mockMvc;
}
```

@AutoConfigureMockMvc tích hợp các servlet filter của ứng dụng. Nếu tự tạo MockMvc từ WebApplicationContext, hãy dùng .apply(springSecurity()) để request chạy qua Spring Security filter chain.

Các matcher HTTP được cung cấp bởi MockMvcResultMatchers:

| Matcher | Công dụng |
| --- | --- |
| status().isUnauthorized() | Xác nhận HTTP 401 |
| status().isForbidden() | Xác nhận HTTP 403 |
| status().is3xxRedirection() | Xác nhận một status thuộc nhóm chuyển hướng 3xx |
| redirectedUrl("/login") | Xác nhận header Location trỏ đúng URL |
| redirectedUrlPattern("/login*") | Xác nhận URL chuyển hướng khớp pattern |
| header().string(HttpHeaders.WWW_AUTHENTICATE, ...) | Kiểm tra challenge xác thực |
| content().contentTypeCompatibleWith(...) | Kiểm tra kiểu nội dung trả về |

Khi cần xác nhận trạng thái bảo mật trong kết quả request, dùng thêm SecurityMockMvcResultMatchers:

- unauthenticated() xác nhận request không có người dùng đã xác thực.
- authenticated().withUsername(...) xác nhận danh tính đã được nhận diện.
- authenticated().withRoles(...) hoặc withAuthorities(...) xác nhận quyền.
- authenticated().withAuthentication(...) kiểm tra loại token hoặc principal cụ thể.

Một phép kiểm tra đầy đủ thường có dạng:

```java
mockMvc.perform(get("/api/admin/report")
            .with(user("mai").roles("USER")))
       .andExpect(status().isForbidden())
       .andExpect(authenticated().withUsername("mai").withRoles("USER"));
```

Status khẳng định request bị từ chối; matcher bảo mật khẳng định request vẫn có danh tính mai và role USER. Hai kết quả này bổ sung cho nhau.

## 4. API dùng HTTP Basic: kiểm tra 401 và 403

### 4.1. Cấu hình ví dụ

Giả sử API có endpoint hồ sơ và endpoint quản trị:

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/admin/**").hasRole("ADMIN")
                    .requestMatchers("/api/**").authenticated()
                    .anyRequest().permitAll()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

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
}
```

Controller minh họa:

```java
@RestController
@RequestMapping("/api")
class ApiController {

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin/report")
    String report() {
        return "admin-report";
    }
}
```

Các lớp phải được Spring Boot component scan. {noop} chỉ dùng cho dữ liệu demo; ứng dụng thật cần PasswordEncoder phù hợp.

### 4.2. Không có credentials: 401

```java
@Test
void missingBasicCredentialsReturns401() throws Exception {
    mockMvc.perform(get("/api/me"))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   startsWith("Basic")));
}
```

Test kiểm tra ba điều: server yêu cầu xác thực, kết quả không có danh tính đã xác thực và response gửi challenge Basic. Dùng startsWith("Basic") giúp test ít phụ thuộc hơn vào realm hoặc các chi tiết header có thể thay đổi theo cấu hình.

### 4.3. Credentials sai: cũng phải từ chối xác thực

```java
@Test
void invalidBasicCredentialsReturns401() throws Exception {
    mockMvc.perform(get("/api/me")
                .with(httpBasic("mai", "wrong")))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   startsWith("Basic")));
}
```

Đây là kiểm thử đường đi xác thực Basic: request có header credentials nhưng tài khoản/mật khẩu không hợp lệ. unauthenticated() giúp xác nhận hệ thống không để lại danh tính đã xác thực sau khi quá trình xác thực thất bại.

### 4.4. Đã xác thực nhưng thiếu role: 403

```java
@Test
void basicUserWithoutAdminRoleReturns403() throws Exception {
    mockMvc.perform(get("/api/admin/report")
                .with(httpBasic("mai", "secret")))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withRoles("USER"));
}
```

Request dùng mật khẩu đúng nên Spring Security xác thực được mai. Tuy nhiên, endpoint yêu cầu ROLE_ADMIN; người dùng chỉ có ROLE_USER, vì thế kết quả là 403. Nếu test chỉ khẳng định status, nó chưa chứng minh người dùng đã được xác thực đúng trước khi bị từ chối.

### 4.5. Tài khoản có quyền được phép truy cập

```java
@Test
void adminCanReadReport() throws Exception {
    mockMvc.perform(get("/api/admin/report")
                .with(httpBasic("quantri", "secret")))
           .andExpect(status().isOk())
           .andExpect(authenticated()
                   .withUsername("quantri")
                   .withRoles("ADMIN"))
           .andExpect(content().string("admin-report"));
}
```

Ca thành công nên xác nhận cả status, danh tính, role và nội dung. Như vậy test chứng minh được endpoint không chỉ cho phép truy cập mà còn phản hồi theo đúng hợp đồng dự kiến.

## 5. Form login: kiểm tra redirect theo login page

### 5.1. Request chưa đăng nhập được chuyển tới trang login

Với ứng dụng web có cấu hình:

```java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/account/**").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Request anonymous truy cập trang tài khoản thường được chuyển hướng tới trang login mặc định:

```java
@Test
void anonymousIsRedirectedToLoginPage() throws Exception {
    mockMvc.perform(get("/account/profile"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/login"))
           .andExpect(unauthenticated());
}
```

redirectedUrl("/login") kiểm tra đích chuyển hướng; unauthenticated() xác nhận request ban đầu không có người dùng đã xác thực. Nếu ứng dụng dùng login page riêng, thay giá trị mong đợi bằng URL đã cấu hình.

### 5.2. Login page tùy chỉnh

Ví dụ:

```java
.formLogin(form -> form
    .loginPage("/signin")
    .permitAll()
)
```

Khi đó test request cần xác nhận redirect tới /signin:

```java
mockMvc.perform(get("/account/profile"))
       .andExpect(status().is3xxRedirection())
       .andExpect(redirectedUrl("/signin"))
       .andExpect(unauthenticated());
```

Đừng dùng URL /login mặc định nếu ứng dụng đã đổi loginPage, hoặc cấu hình AuthenticationEntryPoint theo content negotiation để API trả 401 còn trình duyệt nhận redirect.

### 5.3. Đăng nhập thành công và thất bại

Với formLogin() mặc định và tài khoản mai/secret, formLogin() của Spring Security Test tạo request đăng nhập, bao gồm CSRF token hợp lệ:

```java
@Test
void successfulFormLoginAuthenticatesUser() throws Exception {
    mockMvc.perform(formLogin().user("mai").password("secret"))
           .andExpect(status().is3xxRedirection())
           .andExpect(authenticated().withUsername("mai"));
}

@Test
void failedFormLoginLeavesUserUnauthenticated() throws Exception {
    mockMvc.perform(formLogin().user("mai").password("wrong"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/login?error"))
           .andExpect(unauthenticated());
}
```

Với success handler mặc định, đăng nhập thành công thường chuyển tới request đã được lưu trước đó hoặc / nếu không có request lưu. Vì vậy không nên luôn kỳ vọng redirectedUrl("/") nếu test đã thực hiện request được bảo vệ trước đó trong cùng session. Failure handler mặc định thường chuyển tới /login?error, nhưng handler tùy chỉnh có thể trả JSON, status hoặc URL khác.

Nếu mục tiêu chỉ là xác nhận đăng nhập thành công, status().is3xxRedirection() kết hợp authenticated().withUsername("mai") thường ổn định hơn việc khẳng định một URL redirect không thuộc hợp đồng của ứng dụng.

## 6. Resource server Bearer token: phân biệt 401 và 403

API resource server thường dùng Bearer token. Hai tình huống phải được kiểm tra riêng:

- Chưa có token hoặc token không hợp lệ: không thiết lập được danh tính hợp lệ, thường là 401.
- Token hợp lệ nhưng thiếu scope/authority cần thiết: đã xác thực, nhưng không được phép, thường là 403.

Giả sử cấu hình resource server có rule:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports").hasAuthority("SCOPE_report:read")
    .anyRequest().authenticated()
)
.oauth2ResourceServer(resourceServer -> resourceServer
    .jwt(Customizer.withDefaults())
)
```

### 6.1. Không gửi Bearer token: 401

```java
@Test
void missingBearerTokenReturns401() throws Exception {
    mockMvc.perform(get("/api/reports"))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   startsWith("Bearer")));
}
```

### 6.2. JWT hợp lệ nhưng thiếu scope: 403

jwt() tạo danh tính JWT giả lập cho kiểm thử. Ví dụ này giả định resource server và endpoint /api/reports đã được cấu hình:

```java
@Test
void jwtWithoutRequiredScopeReturns403() throws Exception {
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

Đây là ví dụ điển hình cho 403 sau khi xác thực: matcher xác nhận token type và scope thực tế, trong khi status xác nhận policy đã từ chối request.

### 6.3. Phân biệt thiếu token với token không hợp lệ

Token hết hạn, chữ ký sai, issuer/audience không được chấp nhận hoặc token sai định dạng thường khiến authentication thất bại và trả 401 theo Bearer entry point. Token hợp lệ nhưng thiếu scope lại thường trả 403. Với default BearerTokenAccessDeniedHandler, header challenge có thể mang error="insufficient_scope"; nội dung chính xác phụ thuộc handler và phiên bản/cấu hình.

jwt() không kiểm tra chữ ký hay validator của decoder. Muốn kiểm tra các trường hợp token sai chữ ký/hết hạn, phải gửi Bearer token qua filter chain với JwtDecoder và validator thực tế hoặc một decoder test được cấu hình để mô phỏng đúng các kết quả đó.

## 7. CSRF: một nguyên nhân khác tạo 403

CSRF là ví dụ cho thấy 403 không phải lúc nào cũng do thiếu role. Với cấu hình mặc định, Spring Security bật CSRF protection cho các request thay đổi trạng thái. Một request POST thiếu CSRF token có thể bị CsrfFilter chặn trước khi controller thực thi.

Giả sử endpoint POST /api/items yêu cầu người dùng đã xác thực:

```java
@PostMapping("/api/items")
ResponseEntity<Void> createItem() {
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

Kiểm tra request đã đăng nhập nhưng thiếu CSRF token:

```java
@Test
void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/api/items")
                .with(user("mai").roles("USER")))
           .andExpect(status().isForbidden())
           .andExpect(authenticated().withUsername("mai"));
}
```

Sau đó thêm token hợp lệ:

```java
@Test
void authenticatedPostWithCsrfCanReachController() throws Exception {
    mockMvc.perform(post("/api/items")
                .with(user("mai").roles("USER"))
                .with(csrf()))
           .andExpect(status().isCreated())
           .andExpect(authenticated().withUsername("mai"));
}
```

Test đầu chứng minh danh tính đã có nhưng request bị CSRF protection chặn. Test sau chứng minh khi cung cấp CSRF token hợp lệ, request có thể đi tới controller và nhận 201 Created.

Đối với API stateless dùng Bearer token trong header, chính sách CSRF thường được cấu hình khác với ứng dụng dùng cookie/session. Không mặc định tắt CSRF chỉ vì endpoint trả JSON; hãy dựa trên cách credentials được trình duyệt tự động gửi và threat model của ứng dụng.

## 8. Cấu hình handler làm thay đổi kết quả

### 8.1. Vai trò của AuthenticationEntryPoint và AccessDeniedHandler

Hai thành phần có nhiệm vụ khác nhau:

- AuthenticationEntryPoint: bắt đầu quy trình xác thực khi request chưa có danh tính hợp lệ. Ví dụ: trả 401, thêm WWW-Authenticate hoặc redirect tới login page.
- AccessDeniedHandler: xử lý request đã được xác thực nhưng không có quyền, hoặc các trường hợp AccessDeniedException được chuyển tới handler. Handler mặc định của Servlet thường trả 403.

ExceptionTranslationFilter kết nối exception trong chuỗi filter với các thành phần xử lý phù hợp. Filter khác như CsrfFilter cũng có thể gọi access denied handling khi request vi phạm CSRF.

### 8.2. Cấu hình handler cho API

Ví dụ một API muốn trả status thay vì trang HTML:

```java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED))
    .accessDeniedHandler((request, response, exception) ->
        response.sendError(HttpServletResponse.SC_FORBIDDEN))
);
```

Khi handler được tùy chỉnh, status và body có thể khác mặc định. Hãy viết test theo hợp đồng API mà handler tạo ra: status, content type, JSON error code, correlation id hoặc header challenge nếu có.

### 8.3. Một ứng dụng có thể phục vụ cả HTML và API

Nếu cùng một ứng dụng phục vụ trình duyệt và REST API, có thể cần login redirect cho HTML nhưng trả 401 cho API. Điều này có thể được triển khai bằng nhiều SecurityFilterChain, các AuthenticationEntryPoint khác nhau hoặc request matcher/content negotiation.

Ví dụ ý tưởng:

- Request Accept: text/html vào /account/**: redirect tới /signin.
- Request Accept: application/json vào /api/**: trả 401 với JSON error.
- Người dùng đã xác thực nhưng thiếu quyền: trả 403 theo chính sách API/web đã chọn.

Khi test, gửi đúng header và URL như client thật. Không kiểm tra redirect khi request đang được cấu hình đi qua API entry point; cũng không mong JSON 401 nếu request HTML được chuyển tới login page.

## 9. Thiết kế assertion ổn định cho status và redirect

### 9.1. Kiểm tra redirect

Dùng status().is3xxRedirection() khi mọi redirect hợp lệ theo hợp đồng. Nếu cần đích cụ thể, thêm redirectedUrl(...):

```java
mockMvc.perform(get("/account/profile")
            .accept(MediaType.TEXT_HTML))
       .andExpect(status().is3xxRedirection())
       .andExpect(redirectedUrl("/signin"));
```

Nếu ứng dụng thêm query string hoặc dùng nhiều đích hợp lệ, có thể dùng redirectedUrlPattern(...) hoặc kiểm tra header Location với matcher phù hợp. Tránh khẳng định URL tuyệt đối chứa host/port nếu chúng không phải một phần hợp đồng.

### 9.2. Kiểm tra WWW-Authenticate

Header challenge là một phần quan trọng của giao thức xác thực:

```java
mockMvc.perform(get("/api/me"))
       .andExpect(status().isUnauthorized())
       .andExpect(header().exists(HttpHeaders.WWW_AUTHENTICATE));
```

Nếu API cam kết dùng HTTP Basic hoặc Bearer, có thể xác nhận scheme bắt đầu bằng Basic hoặc Bearer. Chỉ kiểm tra toàn bộ challenge string khi realm, error code và tham số đã được cố định trong cấu hình ứng dụng.

### 9.3. Kiểm tra content type và body

API thường có error response theo hợp đồng riêng:

```java
mockMvc.perform(get("/api/me")
            .accept(MediaType.APPLICATION_JSON))
       .andExpect(status().isUnauthorized())
       .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
       .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
```

Đoạn này giả định AuthenticationEntryPoint tùy chỉnh của ứng dụng tạo JSON với trường code. Entry point mặc định của Basic không nhất thiết trả body JSON đó. Chỉ thêm assertion về body khi ứng dụng đã định nghĩa response contract tương ứng.

## 10. Ma trận chọn kết quả kỳ vọng

| Cơ chế / tình huống | Status thường gặp | Matcher bảo mật | Assertion bổ sung hữu ích |
| --- | --- | --- | --- |
| HTTP Basic, không có credentials | 401 | unauthenticated() | Header WWW-Authenticate: Basic |
| HTTP Basic, credentials sai | 401 | unauthenticated() | Challenge Basic |
| HTTP Basic, đúng credentials và đủ quyền | 200 | authenticated().withUsername(...) | Role/authority và response body |
| HTTP Basic, đúng credentials nhưng thiếu role | 403 | authenticated() | Username và role hiện có |
| Form login, anonymous truy cập trang bảo vệ | 302 | unauthenticated() | Redirect URL login |
| Form login thành công | Thường 302 | authenticated() | Username và request đích sau login nếu cần |
| Bearer token thiếu/không hợp lệ | 401 | unauthenticated() | Challenge Bearer |
| JWT hợp lệ nhưng thiếu scope | 403 | authenticated() | JwtAuthenticationToken và scope hiện có |
| POST thiếu CSRF token | Thường 403 | Có thể authenticated() nếu request có danh tính | Thử lại với .with(csrf()) |
| Endpoint permitAll() | Có thể 200 | Có thể unauthenticated() | Body/status theo endpoint |

Các status trong bảng là cấu hình thường gặp. AuthenticationEntryPoint, AccessDeniedHandler, login handlers, request cache và filter tùy chỉnh có thể thay đổi kết quả. Điều quan trọng là test phải thể hiện đúng chính sách đã chọn.

## 11. Lỗi thường gặp khi kiểm thử

| Biểu hiện | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Anonymous nhận redirect nhưng test mong 401 | Endpoint thuộc web/form-login chain | Kiểm tra formLogin, entry point và request matcher |
| API trả 302 ngoài mong đợi | Request bị áp dụng login entry point hoặc chain web | Kiểm tra filter chain, Accept header và entry point |
| User thường trả 403 nhưng matcher unauthenticated() fail | Request đã xác thực, chỉ thiếu authority | Dùng authenticated() và kiểm tra role/scope |
| Request thiếu CSRF trả 403 dù có user | CsrfFilter chặn request trước controller | Thêm .with(csrf()) cho ca business flow; giữ test thiếu token để xác nhận bảo vệ |
| Header challenge không khớp chuỗi cố định | Realm, error parameters hoặc handler khác nhau | Chỉ kiểm tra scheme/field thuộc hợp đồng |
| Test form login redirect sai URL | Request cache, login page hoặc success/failure handler tùy chỉnh | Xác nhận handler và request session thực tế |
| Mock JWT trả 403, token thật lại trả 401 | Mock bỏ qua decoder/validator | Viết test Bearer token đi qua resource server thực tế |
| Status đúng nhưng response body sai | Entry point/handler tạo payload khác hợp đồng | Assert content type và error code riêng |

Một test tốt không chỉ kiểm tra con số status. Nó phải làm rõ **request đang ở trạng thái xác thực nào, bị chặn tại giai đoạn nào, và client nhận được phản hồi gì**.

## 12. Bài tập thực hành

Dùng ví dụ HTTP Basic và form login ở trên để thực hiện:

1. Viết test anonymous gọi /api/me bằng HTTP Basic, xác nhận 401, unauthenticated() và header WWW-Authenticate bắt đầu bằng Basic.
2. Viết test user mai có role USER gọi /api/admin/report, xác nhận 403 và authenticated().withUsername("mai").withRoles("USER").
3. Tạo một SecurityFilterChain form login với login page /signin. Viết test truy cập /account/profile khi anonymous và xác nhận redirect tới /signin.
4. Viết test form login thành công và thất bại. Kiểm tra trạng thái xác thực và URL redirect theo success/failure handler đã cấu hình.
5. Với resource server, phân biệt request thiếu Bearer token (401) và JWT giả lập có SCOPE_report:write nhưng thiếu SCOPE_report:read (403).
6. Với POST /api/items, kiểm tra danh tính đã đăng nhập nhưng thiếu CSRF token, sau đó thêm .with(csrf()) và xác nhận request tới được controller.

**Tiêu chí hoàn thành:** Người học giải thích được vai trò của AuthenticationEntryPoint và AccessDeniedHandler, chọn đúng giữa 401, 403 và redirect theo cấu hình, đồng thời viết assertion kết hợp status, authentication, header/location và response body khi cần.

## Tài liệu tham khảo chính thức

- [Spring Security — Exception Translation](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Authentication Entry Point](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
