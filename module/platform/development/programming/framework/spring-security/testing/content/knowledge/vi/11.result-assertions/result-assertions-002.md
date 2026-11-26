# `authenticated()` để kiểm tra sự hiện diện của người dùng đã xác thực

## 1. Mục tiêu: chứng minh request có danh tính hợp lệ

Một endpoint trả HTTP `200 OK` chưa đủ để kết luận Spring Security đã xác thực người gọi. Endpoint có thể được cấu hình `permitAll()`, bộ lọc bảo mật có thể chưa tham gia vào phép thử, hoặc controller trả dữ liệu thành công mà không cần thông tin đăng nhập. Ngược lại, một endpoint trả `403 Forbidden` vẫn có thể đang xử lý người dùng **đã xác thực** nhưng thiếu quyền.

Trong module **SPRING_SECURITY_TESTING**, chúng ta dùng `spring-security-test` để kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên ứng dụng Servlet và Reactive. Bài này đi sâu vào một công cụ dành cho **Servlet + MockMvc**: `SecurityMockMvcResultMatchers.authenticated()`. Matcher giúp trả lời câu hỏi:

> **Sau khi MockMvc xử lý request này, Spring Security có ghi nhận một người dùng đã xác thực trong kết quả kiểm thử hay không?**

Đây là câu hỏi khác với “HTTP trả mã gì?”, “người dùng có role nào?” và “mật khẩu/JWT đã được xác minh thật chưa?”. Các câu hỏi đó cần những phép kiểm tra bổ sung.

Sau bài học, người đọc có thể:

- Sử dụng `authenticated()` và `unauthenticated()` trong `MockMvc.andExpect(...)`.
- Phân biệt người dùng đã xác thực, người dùng anonymous và người dùng có danh tính nhưng thiếu quyền.
- Kết hợp matcher với mã HTTP, username/role và nội dung response để mô tả đầy đủ kết quả bảo mật.
- Chọn đúng giữa `httpBasic()`, `@WithMockUser`, `user()` và `jwt()` cho mục tiêu của test.
- Hiểu vì sao không nên đọc `SecurityContextHolder` của luồng kiểm thử sau khi request kết thúc, cũng như ranh giới giữa MockMvc và WebTestClient.

## 2. `authenticated()` thực sự kiểm tra điều gì?

`authenticated()` là một static factory method của lớp:

```java
org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers
```

Nó tạo `ResultMatcher` để kiểm tra trạng thái xác thực được Spring Security lưu lại cho request mà `MockMvc` vừa chạy. Ví dụ đơn giản nhất:

```java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;

mockMvc.perform(get("/api/me").with(user("linh")))
       .andExpect(status().isOk())
       .andExpect(authenticated());
```

Ý nghĩa từng bước:

1. `perform(...)` thực hiện request giả lập qua `MockMvc`.
2. `with(user("linh"))` tạo một `Authentication` đã xác thực phục vụ kiểm thử và gắn vào request.
3. `status().isOk()` xác minh HTTP response có status `200`.
4. `authenticated()` xác minh request có trạng thái người dùng **đã xác thực** theo Spring Security Test.

Matcher này kiểm tra trạng thái xác thực, không đòi hỏi một username cụ thể. Nếu cần khẳng định danh tính, có thể kết hợp:

```java
.andExpect(authenticated().withUsername("linh"))
```

Nếu cần thêm role:

```java
.andExpect(authenticated().withUsername("linh").withRoles("USER"))
```

### Xác thực khác với anonymous authentication

Trong Spring Security, một request ẩn danh có thể được đại diện bởi `AnonymousAuthenticationToken`. Dù token này có thể báo `isAuthenticated() == true` ở mức phương thức Java, Spring Security vẫn xem nó là **anonymous** trong quyết định bảo mật. Matcher `authenticated()` phân biệt được trường hợp này và không coi anonymous là người dùng thực sự đã xác thực.

Đối ứng của `authenticated()` là `unauthenticated()`:

```java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;

mockMvc.perform(get("/api/me"))
       .andExpect(status().isUnauthorized())
       .andExpect(unauthenticated());
```

`unauthenticated()` phù hợp với các request không có thông tin đăng nhập hoặc có thông tin đăng nhập không hợp lệ. Nó cũng phù hợp với endpoint công khai được truy cập ẩn danh, ngay cả khi endpoint đó trả `200`.

| Trạng thái request | Matcher thường cần dùng | Kết quả HTTP minh họa |
| --- | --- | --- |
| Chưa đăng nhập, gọi API yêu cầu xác thực | `unauthenticated()` | `401` nếu dùng HTTP Basic |
| Gửi HTTP Basic với mật khẩu sai | `unauthenticated()` | `401` |
| Đã xác thực và đủ quyền | `authenticated()` | `200` |
| Đã xác thực nhưng thiếu role | `authenticated()` | `403` |
| Truy cập endpoint `permitAll()` mà không đăng nhập | `unauthenticated()` | `200` |
| Gửi request đã đăng nhập nhưng thiếu CSRF token | Có thể dùng `authenticated()` khi danh tính đã được thiết lập trong request | `403` |

Các mã HTTP là ví dụ, không phải quy luật của matcher. Form login thường chuyển hướng `302`; API Bearer token và các handler tùy chỉnh có thể trả kết quả khác. Trạng thái xác thực phải được kiểm tra theo cấu hình đang chạy.

## 3. Chuẩn bị `spring-security-test` và `MockMvc`

Với dự án Spring Boot Servlet có `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-boot-starter-test`, thêm dependency kiểm thử sau nếu chưa có:

```xml
<!-- Maven; phiên bản thường do Spring Boot BOM quản lý -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Hoặc với Gradle:

```groovy
testImplementation 'org.springframework.security:spring-security-test'
```

Khi dùng Spring Boot integration test, cấu hình cơ bản:

```java
@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationResultTest {
    @Autowired MockMvc mockMvc;
}
```

`@AutoConfigureMockMvc` mặc định đăng ký filter của ứng dụng, bao gồm Spring Security nếu ứng dụng đã khai báo. Nếu tự dựng `MockMvc` dựa trên `WebApplicationContext`, cần áp dụng hỗ trợ bảo mật:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

`springSecurity()` đến từ `SecurityMockMvcConfigurers.springSecurity`. Nó giúp gắn Spring Security filter chain và hỗ trợ việc chuyển ngữ cảnh kiểm thử vào request.

**Lỗi thiết lập cần tránh:** xây `MockMvcBuilders.standaloneSetup(controller)` mà không tích hợp cơ chế bảo mật tương ứng, rồi dựa vào status thành công để kết luận endpoint đã được bảo vệ. Với test xác minh hành vi bảo mật HTTP, hãy chắc chắn request thực sự đi qua filter chain ứng dụng.

## 4. Ví dụ đầy đủ: một API, nhiều trạng thái xác thực

Giả sử hệ thống có API `/api/me` yêu cầu đăng nhập, `/api/public` cho phép tất cả, và `/api/admin` chỉ dành cho role `ADMIN`.

### 4.1. Controller và chính sách truy cập mẫu

```java
@RestController
@RequestMapping("/api")
class AccountController {

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-data";
    }
}
```

```java
@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/public").permitAll()
                    .requestMatchers("/api/admin").hasRole("ADMIN")
                    .requestMatchers("/api/**").authenticated()
                    .anyRequest().permitAll()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("linh")
                    .password("{noop}secret")
                    .roles("USER")
                    .build()
        );
    }
}
```

Các lớp này cần nằm trong vùng quét component của ứng dụng Spring Boot; import Java/Spring thông thường được lược bớt để tập trung vào logic. Mật khẩu `{noop}` chỉ phục vụ ví dụ kiểm thử; hệ thống thật cần một `PasswordEncoder` thích hợp. Cấu hình trên dùng HTTP Basic để các trường hợp `401`/`403` có thể dự đoán được.

### 4.2. Kiểm tra sự hiện diện của người dùng đã xác thực

Test dưới đây gửi HTTP Basic đúng. Spring Security xử lý header và nạp thông tin người dùng từ `UserDetailsService`:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationResultTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void validCredentialsProduceAuthenticatedRequest() throws Exception {
        mockMvc.perform(get("/api/me").with(httpBasic("linh", "secret")))
               .andExpect(status().isOk())
               .andExpect(authenticated())
               .andExpect(authenticated().withUsername("linh"))
               .andExpect(jsonPath("$.username").value("linh"));
    }

    @Test
    void missingCredentialsAreNotAuthenticated() throws Exception {
        mockMvc.perform(get("/api/me"))
               .andExpect(status().isUnauthorized())
               .andExpect(unauthenticated());
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mockMvc.perform(get("/api/me").with(httpBasic("linh", "wrong")))
               .andExpect(status().isUnauthorized())
               .andExpect(unauthenticated());
    }

    @Test
    void anonymousVisitorCanAccessPublicResource() throws Exception {
        mockMvc.perform(get("/api/public"))
               .andExpect(status().isOk())
               .andExpect(unauthenticated())
               .andExpect(content().string("public"));
    }

    @Test
    void authenticatedUserCanStillBeDeniedAuthorization() throws Exception {
        mockMvc.perform(get("/api/admin")
                    .with(user("linh").roles("USER")))
               .andExpect(status().isForbidden())
               .andExpect(authenticated().withUsername("linh")
                                         .withRoles("USER"));
    }
}
```

Đây là năm ca kiểm tra độc lập. Test đầu tiên chứng minh danh tính hiện diện **và** endpoint cho phép truy cập. Hai test tiếp theo kiểm tra trường hợp không có danh tính hợp lệ. Test thứ tư chứng minh `200` không đồng nghĩa với đã xác thực. Test cuối cùng chứng minh `403` không đồng nghĩa với chưa xác thực: người dùng `linh` được nhận diện nhưng không có `ROLE_ADMIN`.

Chính sách ví dụ dùng `hasRole("ADMIN")`. Vì thế `.roles("USER")` tương đương gán authority `ROLE_USER`; phương thức `withRoles("USER")` cũng nhận tên role **không có** tiền tố `ROLE_`.

### 4.3. `@WithMockUser`: kiểm tra logic khi đã có người dùng

Khi cần kiểm tra endpoint đã có sẵn danh tính, annotation có thể giúp test ngắn hơn:

```java
@Test
@WithMockUser(username = "linh", roles = "USER")
void mockUserIsVisibleToRequest() throws Exception {
    mockMvc.perform(get("/api/me"))
           .andExpect(status().isOk())
           .andExpect(authenticated().withUsername("linh"));
}
```

Trong ví dụ này, Spring Security Test chuẩn bị `SecurityContext` với người dùng giả lập trước khi chạy test. Do đó `authenticated()` xác nhận hệ thống **nhìn thấy danh tính giả lập** trong request, chứ không kiểm tra quá trình xác minh mật khẩu thật. `@WithMockUser` hữu ích khi tập trung vào điều kiện `authenticated()` hoặc chính sách quyền; dùng `httpBasic()` như mục 4.2 nếu mục tiêu là chạy qua quá trình kiểm tra thông tin đăng nhập HTTP Basic.

## 5. Lựa chọn nguồn `Authentication` phù hợp với mục tiêu test

| Cách cung cấp danh tính | Điều gì diễn ra? | Có thể kết luận gì khi `authenticated()` pass? |
| --- | --- | --- |
| `@WithMockUser` | Test framework tạo sẵn `SecurityContext` với người dùng giả lập | Request xử lý với danh tính được tạo sẵn |
| `.with(user("linh"))` | Request post-processor gắn principal giả lập vào request | Danh tính giả lập có mặt trong ngữ cảnh request |
| `.with(httpBasic("linh", "secret"))` | Gửi header Basic để filter thực tế xác minh credentials | Cơ chế Basic đã nhận diện danh tính theo cấu hình hiện tại |
| `.with(jwt())` | Gắn `JwtAuthenticationToken` giả lập cho request | Request có danh tính JWT giả lập |
| `.with(oauth2Login())` hoặc `.with(oidcLogin())` | Tạo thông tin OAuth2/OIDC đã đăng nhập cho kiểm thử | Request nhìn thấy principal OAuth2/OIDC giả lập |

Ví dụ JWT khi resource server có endpoint và quy tắc riêng:

```java
mockMvc.perform(get("/api/profile")
            .with(jwt().jwt(token -> token.subject("user-42"))))
       .andExpect(status().isOk())
       .andExpect(authenticated());
```

Đoạn trên **giả định** `/api/profile` có tồn tại, cho phép danh tính JWT đã xác thực và `MockMvc` đã gắn Spring Security. `jwt()` đặt authentication giả lập vào request, không tự chứng minh bộ giải mã của ứng dụng đã kiểm tra chữ ký, issuer, audience hay thời hạn token. Kiểm thử đường đi Bearer token thật cần gửi header `Authorization: Bearer ...` qua cơ chế `JwtDecoder`/resource server đã cấu hình và kiểm tra riêng các trường hợp token không hợp lệ.

Với OAuth2/OIDC cũng vậy: matcher có thể chứng minh principal giả lập hiện diện, nhưng không kiểm tra authorization code flow, trao đổi token hoặc xác minh token với nhà cung cấp danh tính.

## 6. Đọc `authenticated()` cùng kết quả HTTP để tránh kết luận sai

### `authenticated()` không tự chứng minh được cấp quyền

Ví dụ:

```java
mockMvc.perform(get("/api/admin").with(user("linh").roles("USER")))
       .andExpect(status().isForbidden())
       .andExpect(authenticated());
```

Hai assertion không hề mâu thuẫn nhau. `authenticated()` nói rằng request có người dùng đã xác thực; `isForbidden()` nói rằng request không được phép truy cập tài nguyên. Để mô tả đầy đủ lý do, nên thêm `.withRoles("USER")` hoặc matcher authority phù hợp với chính sách được kiểm tra.

### `status().isOk()` không tự chứng minh được xác thực

Ví dụ:

```java
mockMvc.perform(get("/api/public"))
       .andExpect(status().isOk())
       .andExpect(unauthenticated());
```

Endpoint `permitAll()` cho phép truy cập ẩn danh nên không cần principal đã xác thực. Trường hợp này đặc biệt quan trọng khi kiểm thử cấu hình endpoint công khai.

### `authenticated()` không tự chứng minh phiên đăng nhập còn hiệu lực

Matcher quan sát trạng thái của **request đang kiểm thử**. Một request đăng nhập thành công có thể có `Authentication`, nhưng để kiểm tra phiên tiếp tục tồn tại ở request sau, cần tái sử dụng session/cookie hoặc kiểm tra token phản hồi theo cơ chế của ứng dụng.

Nếu ứng dụng dùng form login, một phép kiểm tra có thể viết như sau (với filter chain đã bật `formLogin()` và tài khoản thử nghiệm tương ứng):

```java
mockMvc.perform(formLogin().user("linh").password("secret"))
       .andExpect(status().is3xxRedirection())
       .andExpect(authenticated().withUsername("linh"));
```

Việc form login thành công ở request này chưa thay thế cho test tiếp theo sử dụng phiên đã được tạo. Với cấu hình form login, redirect mặc định hoặc handler tùy chỉnh cũng có thể ảnh hưởng status và location kỳ vọng.

### `authenticated()` không thay thế kiểm tra thuộc tính danh tính

Một test chỉ có `.andExpect(authenticated())` vẫn pass nếu request có một tài khoản hợp lệ khác với mong đợi. Với endpoint cần đúng người, hãy viết:

```java
.andExpect(authenticated().withUsername("linh").withRoles("USER"))
```

Nếu cần kiểm tra loại `Authentication`, principal hoặc authority phức tạp, có thể dùng `authenticated().withAuthentication(auth -> { ... })`. Chỉ thêm các khẳng định này khi chúng gắn với yêu cầu của API; mục tiêu chính của `authenticated()` vẫn là kiểm tra **sự hiện diện của danh tính đã xác thực**.

## 7. `SecurityContext` trong và sau request

Spring Security gắn `Authentication` vào `SecurityContext` trong vòng đời xử lý request, đồng thời thường xóa ngữ cảnh khỏi thread sau khi filter chain hoàn tất. Vì vậy không nên xác minh kết quả bằng cách đọc `SecurityContextHolder` ngay sau `perform()`:

```java
mockMvc.perform(get("/api/me").with(user("linh")));

// Không dùng kết quả này làm khẳng định danh tính của request vừa chạy:
Authentication auth = SecurityContextHolder.getContext().getAuthentication();
```

Cách phù hợp với MockMvc là kiểm tra ngay trên `MvcResult`:

```java
mockMvc.perform(get("/api/me").with(user("linh")))
       .andExpect(authenticated());
```

Điều này cũng tránh tình trạng test vô tình đọc trạng thái còn sót lại từ quá trình thiết lập `SecurityContext` trước đó. Nếu cần kiểm tra code chạy trong controller/service, hãy viết test phù hợp cho tầng đó hoặc kiểm tra response phản ánh danh tính mà endpoint trả về.

## 8. Trên ứng dụng Reactive dùng gì?

`SecurityMockMvcResultMatchers.authenticated()` thuộc `spring-security-test` dành cho **Spring MVC/Servlet**; không gọi matcher này trên `WebTestClient`. Với WebFlux, sử dụng `WebTestClient` được cấu hình Spring Security Reactive, kết hợp `mockUser()`, `mockJwt()` hoặc `@WithMockUser` theo kiểu kiểm thử.

Ví dụ với endpoint Reactive `/api/me` được bảo vệ:

```java
// static import SecurityMockServerConfigurers.mockUser
webTestClient.mutateWith(mockUser("linh").roles("USER"))
             .get().uri("/api/me")
             .exchange()
             .expectStatus().isOk()
             .expectBody()
             .jsonPath("$.username").isEqualTo("linh");
```

Ở đây WebTestClient khẳng định kết quả HTTP và dữ liệu trả về; danh tính được cấp bởi `mockUser()`. Nếu cần chứng minh cơ chế xác thực Reactive thật sự xử lý token hoặc credentials, hãy gửi request đi qua filter và authentication manager/decoder tương ứng, thay vì chỉ dùng `mockUser()`.

## 9. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Endpoint trả `200` nhưng `authenticated()` fail | Endpoint công khai, request anonymous hoặc filter chain không được áp dụng | Xác định policy; nếu endpoint công khai thì dùng `unauthenticated()`, nếu yêu cầu login thì kiểm tra thiết lập MockMvc |
| `authenticated()` pass nhưng request trả `403` | Đã có danh tính nhưng không có quyền hoặc bị chặn bởi cơ chế khác | Kiểm tra rule `hasRole`/`hasAuthority`, CSRF và handler; assert thêm role/authority |
| Test dùng `@WithMockUser` pass nhưng đăng nhập thật thất bại | Test đã bỏ qua quá trình kiểm chứng credential | Bổ sung test `httpBasic()`, form login hoặc HTTP Bearer token thật tùy cơ chế |
| Kiểm tra username/role không khớp | Giả lập danh tính khác kỳ vọng hoặc nhầm `ROLE_` | So sánh `withUsername`, `withRoles` và `withAuthorities` đúng ngữ nghĩa |
| `SecurityContextHolder` sau request rỗng | Filter chain dọn trạng thái cuối request | Khẳng định bằng `andExpect(authenticated())` trên kết quả request |
| Thử dùng `authenticated()` với `WebTestClient` | API kiểm thử thuộc Servlet, không thuộc Reactive | Dùng `expectStatus()`, `expectBody()` và hỗ trợ bảo mật dành cho WebFlux |

Khi một test fail, hãy đọc đồng thời request, response, matcher bảo mật và cấu hình filter chain. Mã HTTP riêng lẻ hiếm khi đủ để xác định lỗi thuộc xác thực, phân quyền hay điều kiện bảo vệ như CSRF.

## 10. Bài tập thực hành

Mở rộng ví dụ ở mục 4 theo ba yêu cầu:

1. Thêm tài khoản `admin` với role `ADMIN`. Viết test cho `GET /api/admin` có `status().isOk()`, `authenticated()` và `withRoles("ADMIN")`. Sau đó thay thành tài khoản `linh` và giải thích vì sao cùng `authenticated()` pass nhưng status trở thành `403`.
2. Thêm một endpoint `GET /api/health` có `permitAll()`. So sánh hai request: request anonymous và request `.with(user("linh"))`. Cả hai có thể nhận `200`, nhưng matcher bảo mật phải khác nhau.
3. Thêm test sử dụng `@WithMockUser(username = "khach")` và test dùng `httpBasic("khach", "wrong")`. Phân tích sự khác nhau giữa **danh tính giả lập** và **kết quả xác thực credentials qua filter**.

**Tiêu chí đạt:** Người học chỉ ra được kết quả `authenticated()`/`unauthenticated()` cho từng request, giải thích đúng vì sao status và trạng thái xác thực không đồng nhất, đồng thời chọn cách cung cấp danh tính phù hợp mục tiêu kiểm thử.

## Tài liệu tham khảo

- [Spring Security Reference — Testing Spring MVC Applications](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security Reference — Security Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security Reference — Setting Up MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security Reference — Running a Test as a User](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security Reference — Testing OAuth2](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security Reference — Testing WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
