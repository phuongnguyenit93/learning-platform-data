# Mã trạng thái, chuyển hướng và kết quả `Authentication` sau đăng nhập HTTP

Một phép thử đăng nhập thành công không kết thúc ở việc máy chủ trả về `302 Found`. Với ứng dụng dùng Spring Security, cần phân biệt ba câu hỏi: yêu cầu HTTP nhận **mã trạng thái và header gì**, trình duyệt/client **được hướng đến đâu**, và **người dùng nào đã được xác thực với những quyền nào**. Ba lớp kết quả này liên quan nhưng không thay thế cho nhau.

Bài này tập trung vào kiểm thử luồng đăng nhập HTTP thực tế của Spring Security bằng **`spring-security-test`**, **MockMvc** trên Servlet và **WebTestClient** trên WebFlux/Reactive. Các ví dụ dùng tài khoản thử nghiệm; không gọi dịch vụ nhận dạng bên ngoài.

## 1. Đọc đúng kết quả của một lượt đăng nhập

Với form login mặc định, một lượt vào trang được bảo vệ rồi đăng nhập thành công thường diễn ra như sau:

```text
Client                               Spring Security (Servlet)
  | GET /private                             |
  |----------------------------------------->|
  |<------------- 302 Location: /login ------|  Chưa xác thực
  | GET /login                               |
  |----------------------------------------->|
  |<------------- 200 trang đăng nhập -------|
  | POST /login                              |
  |   username=alice&password=secret         |  Có CSRF token hợp lệ
  |----------------------------------------->|
  |                    AuthenticationManager |  Kiểm tra thông tin đăng nhập
  |                    SecurityContext       |  Lưu Authentication
  |<------------- 302 Location: /private ----|  Phục hồi SavedRequest
  | GET /private + cookie phiên              |
  |----------------------------------------->|
  |<------------- 200 nội dung bảo vệ -------|
```

Đây là hành vi thường gặp khi bật `formLogin()` và giữ cơ chế `SavedRequestAwareAuthenticationSuccessHandler`. Đích chuyển hướng phụ thuộc vào cấu hình, lịch sử request và success handler; không được mặc định mọi lần đăng nhập sẽ quay về `/private`.

| Tình huống | HTTP thường thấy | `Location` / nội dung | Kết quả bảo mật cần kiểm tra |
| --- | --- | --- | --- |
| GET tài nguyên cần đăng nhập, chưa có phiên | `302 Found` | `/login` | Chưa có người dùng đăng nhập |
| GET trang login mặc định | `200 OK` | HTML form | Chưa đăng nhập |
| POST `/login`, mật khẩu đúng, CSRF hợp lệ | `302 Found` | URL đích sau thành công | `Authentication` đã xác thực, có principal/quyền đúng |
| POST `/login`, mật khẩu sai, CSRF hợp lệ | `302 Found` | `/login?error` theo mặc định | Không tạo phiên đăng nhập hợp lệ |
| POST `/login`, thiếu hoặc sai CSRF | `403 Forbidden` | Bị chặn trước xác thực | Chưa thể kết luận mật khẩu đúng/sai |
| GET tài nguyên chỉ dành cho ADMIN với USER đã đăng nhập | `403 Forbidden` | Trang/lỗi truy cập bị từ chối | Đã xác thực nhưng thiếu quyền |
| Gọi API chưa xác thực, cấu hình Basic/Bearer hoặc entry point trả 401 | `401 Unauthorized` | Có thể kèm `WWW-Authenticate` | Chưa có chứng thực hợp lệ |

Những hàng trên mô tả **cấu hình phổ biến**, không phải bảng mã cố định cho mọi ứng dụng. Custom `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, content negotiation hoặc cơ chế đăng nhập khác có thể thay đổi status/header/body.

### Tại sao đăng nhập thành công lại trả 302?

Form login truyền thống dùng mẫu **POST → Redirect → GET** để trình duyệt không gửi lại mật khẩu nếu người dùng tải lại trang. `302` chỉ báo client cần điều hướng; bản thân status này **không chứng minh** việc đăng nhập đã thành công, bởi đăng nhập thất bại cũng có thể redirect. Để kết luận, phải kiểm tra đồng thời đích `Location` và `Authentication`, sau đó thực hiện thêm yêu cầu được bảo vệ với phiên đã được tạo.

`303 See Other` cũng có thể được ứng dụng lựa chọn để diễn đạt POST → GET rõ ràng hơn, nhưng không phải status mặc định cần áp đặt cho Spring Security form login. `307`/`308` bảo toàn HTTP method khi redirect và không nên được tự suy diễn là kết quả của form login thông thường.

## 2. Ai quyết định redirect và tạo `Authentication`?

Với Servlet, chuỗi xử lý cốt lõi gồm:

1. `ExceptionTranslationFilter` chuyển tình huống chưa xác thực thành lời gọi `AuthenticationEntryPoint`; entry point của form login thường dẫn đến trang đăng nhập.
2. `UsernamePasswordAuthenticationFilter` nhận POST tại `loginProcessingUrl` (mặc định `/login`), lấy `username`/`password` và yêu cầu `AuthenticationManager` kiểm tra.
3. Nếu hợp lệ, security context chứa một `Authentication` đã xác thực, thường có principal dạng `UserDetails` và các `GrantedAuthority`. `SecurityContextRepository` lưu context để request sau có thể dùng lại.
4. Success handler chọn URL đích, ưu tiên saved request khi cấu hình mặc định cho phép; failure handler thường redirect về `/login?error` khi xác thực thất bại.
5. `SessionAuthenticationStrategy` có thể đổi session ID khi đăng nhập để chống session fixation. Test nên lấy **session sau login**, không so sánh cứng ID trước và sau.

Các thông tin quan trọng có thể kiểm tra từ `Authentication`:

| Thuộc tính | Ý nghĩa | Cách kiểm chứng |
| --- | --- | --- |
| `isAuthenticated()` | Token đã được xác thực hay chưa | `authenticated()` trong MockMvc |
| `getName()` / `getPrincipal()` | Người dùng đang được đại diện | `withUsername("alice")` hoặc đọc principal ở endpoint |
| `getAuthorities()` | Các quyền hiện có, ví dụ `ROLE_USER` | `withRoles("USER")` |
| `getDetails()` | Chi tiết gắn với request, phụ thuộc cấu hình | Chỉ kiểm tra khi thật sự là hợp đồng của ứng dụng |
| `getCredentials()` | Dữ liệu chứng thực; có thể đã bị xóa sau xác thực | **Không** kiểm thử bằng cách mong mật khẩu được giữ lại |

Lưu ý: `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true` theo đặc tính token. Khi xác nhận người dùng **thực sự đăng nhập**, nên dùng matcher của Spring Security hoặc kiểm tra loại token, principal và quyền phù hợp, thay vì chỉ gọi một boolean.

## 3. Ví dụ cấu hình Servlet có thể kiểm thử

Giả sử ứng dụng Spring Boot Servlet có `spring-boot-starter-security`, `spring-boot-starter-web` và test dependency `spring-security-test` tương thích với phiên bản Spring Security đang dùng.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class HttpLoginSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
        ).formLogin(withDefaults());
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
                        .build()
        );
    }
}

@RestController
class HttpLoginDemoController {
    @GetMapping({"/", "/private"})
    String privatePage(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "Admin only";
    }
}
```

`formLogin(withDefaults())` sử dụng trang login mặc định của Spring Security khi không đăng ký trang login riêng. Vì `/private` và `/` yêu cầu xác thực, client chưa đăng nhập sẽ nhận redirect; sau khi đăng nhập thành công mà không có saved request, đích mặc định thường là `/`.

Khi viết ứng dụng thật, nên dùng người dùng từ kho định danh phù hợp và quản lý mật khẩu an toàn. `InMemoryUserDetailsManager` ở đây chỉ giúp ví dụ có thể lặp lại và không phụ thuộc dữ liệu ngoài.

### Kiểm thử trực tiếp bằng MockMvc

`@SpringBootTest` kết hợp `@AutoConfigureMockMvc` khởi tạo filter chain thật của ứng dụng. Dùng test helpers từ `spring-security-test` để sinh request form và đối chiếu `Authentication` sau request.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HttpLoginFlowTest {
    @Autowired
    MockMvc mvc;

    @Test
    void correctPassword_redirectsAndPersistsAuthentication() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("secret"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/"))
                .andExpect(authenticated()
                        .withUsername("alice")
                        .withRoles("USER"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("alice"))
                .andExpect(content().string("Hello alice"));
    }

    @Test
    void wrongPassword_redirectsToErrorWithoutAuthentication()
            throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("wrong"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void savedRequest_isUsedAfterSuccessfulLogin() throws Exception {
        MvcResult first = mvc.perform(get("/private"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrlPattern("**/login"))
                .andReturn();

        MockHttpSession beforeLogin =
                (MockHttpSession) first.getRequest().getSession(false);
        assertThat(beforeLogin).isNotNull();

        MvcResult login = mvc.perform(post("/login")
                        .session(beforeLogin)
                        .param("username", "alice")
                        .param("password", "secret")
                        .with(csrf()))
                .andExpect(status().isFound())
                .andExpect(header().string("Location", endsWith("/private")))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession afterLogin =
                (MockHttpSession) login.getRequest().getSession(false);
        mvc.perform(get("/private").session(afterLogin))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello alice"));
    }

    @Test
    void missingCsrf_blocksLoginBeforeCredentialCheck() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "secret"))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUserWithoutAdminRole_isForbidden() throws Exception {
        mvc.perform(get("/admin").with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }
}
```

**Điểm cần đọc trong kết quả test:**

- `status().isFound()` kiểm tra HTTP `302`; `redirectedUrl(...)` và header `Location` kiểm tra nơi chuyển hướng. Hai assertion này trả lời hai câu hỏi khác nhau.
- `authenticated().withUsername(...).withRoles(...)` kiểm tra trạng thái bảo mật sau request; thành công ở lớp HTTP thôi chưa đủ.
- `formLogin()` từ `spring-security-test` dựng request đăng nhập thích hợp với cấu hình mặc định, bao gồm CSRF hợp lệ cho luồng kiểm thử form login. Khi tự dựng `post("/login")`, cần thêm `.with(csrf())` nếu CSRF đang bật.
- Test saved request lấy **session từ GET bị chặn** đưa vào POST login. Nếu bỏ session này, request cache không tìm được URL trước đăng nhập và có thể redirect sang URL mặc định.
- Khi kiểm tra request tiếp theo, truyền **session sau login**; `MockMvc` không tự đóng vai trình duyệt để theo mọi redirect và mang cookie qua các request riêng.

Trong test saved request, Spring có thể sinh URL tuyệt đối như `http://localhost/private`. Matcher `endsWith("/private")` tập trung vào đường dẫn mong đợi mà vẫn cho phép kiểm tra chính xác hơn host/scheme trong một test cấu hình redirect riêng. Với ứng dụng có context path hoặc tham số query, cần cập nhật assertion theo URL đích thực tế.

### Nếu đổi URL xử lý đăng nhập hoặc tham số

`loginPage("/sign-in")` là URL hiển thị form; `loginProcessingUrl("/authenticate")` là URL nhận POST để lọc xác thực xử lý. Nếu dùng trang login tùy chỉnh, ứng dụng phải phục vụ GET cho trang đó và bảo đảm client có thể truy cập.

```java
http.formLogin(form -> form
        .loginPage("/sign-in")
        .loginProcessingUrl("/authenticate")
        .usernameParameter("email")
        .passwordParameter("password")
        .defaultSuccessUrl("/dashboard", true)
        .failureUrl("/sign-in?error")
        .permitAll()
);
```

Test phải gửi đúng form và kiểm tra đúng đích cấu hình:

```java
mvc.perform(formLogin("/authenticate")
                .user("email", "alice")
                .password("password", "secret"))
        .andExpect(status().isFound())
        .andExpect(redirectedUrl("/dashboard"))
        .andExpect(authenticated().withUsername("alice"));
```

Đối số `true` của `defaultSuccessUrl("/dashboard", true)` có nghĩa là **luôn chuyển về `/dashboard`**, kể cả khi có saved request. Nếu không bật chế độ đó, saved request có thể được ưu tiên. Cần xây assertion theo hợp đồng redirect đã chọn thay vì sao chép mặc định.

## 4. Phân biệt 302, 401 và 403 trong cùng một ứng dụng

Ba status thường bị nhầm khi kiểm thử authentication/authorization:

- **302 Redirect:** entry point dành cho browser chuyển người chưa xác thực đến trang login; success/failure handler cũng có thể trả 302. Phải đọc `Location` mới hiểu kết quả.
- **401 Unauthorized:** client chưa đưa chứng thực hợp lệ cho tài nguyên. Thường xuất hiện trong HTTP Basic hoặc Bearer API. Header `WWW-Authenticate` mô tả cơ chế xác thực/challenge khi được áp dụng.
- **403 Forbidden:** client đã xác thực nhưng không có quyền, **hoặc** request bị bảo vệ CSRF chặn. Trong ca CSRF, không thể kết luận từ 403 rằng user thiếu role.

Ví dụ yêu cầu vào `/admin`:

```text
GET /admin, browser chưa đăng nhập, form login bật
  -> 302 Location: /login

GET /admin, user alice đã đăng nhập, chỉ có ROLE_USER
  -> 403 Forbidden

GET /admin, API yêu cầu Bearer, không có token
  -> 401 Unauthorized
     WWW-Authenticate: Bearer ...
```

Không nên viết test `GET /admin` phải trả `401` nếu đang dùng default form-login entry point; điều đó thường sai với luồng browser. Muốn API trả 401 cần kiểm tra cấu hình `SecurityFilterChain` và entry point dành cho API. Nếu đồng thời có web form và API, hãy kiểm tra từng vùng URL theo đúng filter chain đang áp dụng.

**CSRF là một nhánh độc lập:** POST `/login` đúng mật khẩu nhưng thiếu CSRF có thể trả 403 trước khi `UsernamePasswordAuthenticationFilter` xác thực. Đây là lỗi thiết lập request test, không phải bằng chứng mật khẩu sai. Dùng `csrf()` để test đăng nhập hợp lệ; viết thêm ca thiếu CSRF riêng để chứng minh bảo vệ HTTP còn hoạt động.

## 5. Kiểm tra trạng thái đăng nhập ở nhiều thời điểm

Một ca test hoàn chỉnh nên tách ba thời điểm quan sát:

| Thời điểm | Assertion phù hợp | Điều cần tránh |
| --- | --- | --- |
| Trước login: vào route được bảo vệ | Redirect đến trang login hoặc 401 theo entry point | Giả định mọi app đều trả 401 |
| Ngay sau POST login | Status, `Location`, `authenticated()` và authorities | Xem một redirect 302 là đủ |
| Request mới với session/cookie vừa cấp | HTTP 200 và principal được nhận diện đúng | Chỉ xác minh principal giả lập trên một request |

Trong Servlet, bạn cũng có thể dùng `@WithMockUser(username = "alice", roles = "USER")` hoặc `.with(user("alice").roles("USER"))` để kiểm thử riêng quyền truy cập. Hai cách này **cấp sẵn danh tính cho request test**; chúng không gửi form, không kiểm tra mật khẩu, không thực thi success/failure handler và không chứng minh login flow.

Đối với bài toán bảo đảm **kết quả Authentication sau đăng nhập**, nên giữ ít nhất một ca gửi POST `/login` thực sự, kiểm tra redirect/authentication và lặp lại request bằng session sau login. `@WithMockUser` chỉ bổ sung những phép thử phân quyền nhanh, độc lập với đăng nhập.

## 6. Kiểm thử hướng Reactive với WebTestClient

Với Spring WebFlux, filter chain là `SecurityWebFilterChain` và cơ chế lưu security context thường đi qua `ServerSecurityContextRepository` / `WebSession`. Tư tưởng kiểm thử vẫn giống Servlet: quan sát HTTP result, redirect, rồi tính liên tục của trạng thái đăng nhập. Tuy nhiên không dùng `MockHttpSession`, `MockMvc` hay `SecurityContextHolder` kiểu ThreadLocal như đường đi chính của WebFlux.

Ví dụ cấu hình dành **riêng cho ứng dụng WebFlux**:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveHttpLoginSecurityConfig {
    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/login").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("secret"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

Đoạn trên giả định ứng dụng WebFlux đã có bean `PasswordEncoder` phù hợp và endpoint `/private` do controller/handler cung cấp. Các import thường dùng là `EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveUserDetailsService` và `MapReactiveUserDetailsService` của Spring Security.

Khi bind `WebTestClient` vào reactive application context, cần áp dụng tích hợp `springSecurity()` để các mock security mutator thực sự có hiệu lực:

```java
// Trong test ứng dụng WebFlux, context là ApplicationContext được inject.
WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();

// Thực sự POST vào endpoint form-login, kèm CSRF hợp lệ.
client.mutateWith(SecurityMockServerConfigurers.csrf())
        .post()
        .uri("/login")
        .body(BodyInserters.fromFormData("username", "alice")
                .with("password", "secret"))
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectHeader().exists("Location");

// Test riêng authorization: mock danh tính cho một request.
client.mutateWith(SecurityMockServerConfigurers.mockUser("alice")
                .roles("USER"))
        .get()
        .uri("/admin")
        .exchange()
        .expectStatus().isForbidden();
```

Khi muốn chứng minh đăng nhập **được duy trì sau redirect** trong WebFlux, phải lấy cookie phiên (tên cookie phụ thuộc cấu hình session resolver) từ phản hồi login rồi gửi nó ở request kế tiếp, hoặc dùng cơ chế quản lý cookie của client test phù hợp. Dùng `mockUser()` ở request kế tiếp sẽ bỏ qua việc kiểm chứng session persistence nên không thay thế được phép thử đó. Nếu endpoint trả principal, có thể assert body theo `Principal#getName()` hoặc `ReactiveSecurityContextHolder`/`Authentication` theo hợp đồng của handler.

Test reactive cũng cần phân biệt redirect do `formLogin()` với 401/403 của resource server hoặc entry point tùy chỉnh. `WebTestClient` kiểm tra mã HTTP bằng `expectStatus()`, header bằng `expectHeader()`, body bằng `expectBody()`; các lệnh này quan sát phản hồi HTTP, **không tự chứng minh** tất cả thuộc tính `Authentication` đã được lưu.

## 7. Ranh giới với JWT, OAuth2 và OIDC

Không phải mọi cách xác thực đều có POST form login:

| Cơ chế | Điểm cần quan sát | Cách kiểm thử phù hợp |
| --- | --- | --- |
| Servlet/Reactive form login | POST thông tin đăng nhập; 302 success/failure; phiên sau login | MockMvc/WebTestClient gửi form thật trong test |
| HTTP Basic | `401` challenge khi thiếu/sai thông tin; `200` khi hợp lệ | Gửi header Basic; assert HTTP + principal |
| OAuth2 Resource Server JWT | `401` token thiếu/hỏng; `403` scope/authority thiếu | `jwt()`/`mockJwt()` để kiểm thử phân quyền; ca token thực cho kiểm thử decoder/validation |
| `oauth2Login()` / OIDC | Redirect sang authorization endpoint, callback, OAuth2/OIDC principal và phiên | Test luồng redirect/callback bằng cấu hình test thích hợp; mock OAuth2/OIDC chỉ để test route đã xác thực |

`jwt()` của MockMvc và `mockJwt()` của WebTestClient tạo chứng thực thử nghiệm, có ích khi kiểm tra endpoint yêu cầu `scope`, `role` hoặc `audience` đã được map. Chúng **không xác minh chữ ký JWT**, không gọi Identity Provider và không đại diện cho success handler của `formLogin()`.

Tương tự, `oauth2Login()`/`oidcLogin()` trong `spring-security-test` giúp dựng principal đã đăng nhập để kiểm thử route bảo vệ; muốn kiểm chứng vòng redirect OAuth2/OIDC phải kiểm tra authorization request, callback, state, token exchange theo phạm vi bài test tích hợp. Tên lớp `Authentication` và các authority có thể khác form login: ví dụ `JwtAuthenticationToken` hoặc `OAuth2AuthenticationToken`. Đừng cố assert một loại token cho mọi cơ chế.

## 8. Các lỗi khiến assertion đúng cú pháp nhưng sai ý nghĩa

**Chỉ assert status 302.** Mật khẩu đúng và sai đều có thể redirect. Thêm kiểm tra `Location`, `authenticated()/unauthenticated()` và request tiếp theo có session.

**Tự POST thiếu CSRF.** POST `/login` trả 403 khiến người viết test tưởng login thất bại. Thêm `.with(csrf())` (Servlet) hoặc `mutateWith(csrf())` (Reactive) cho ca login hợp lệ; kiểm thử CSRF ở ca riêng.

**Dùng mock principal để tuyên bố login thành công.** `@WithMockUser`, `user()`, `mockUser()` và `mockJwt()` bỏ qua một phần hoặc toàn bộ quy trình nhận và kiểm tra credential. Chúng rất hữu ích cho authorization, nhưng phải có test login flow riêng.

**Kiểm tra sai redirect khi có saved request.** Nếu user trước đó đi đến `/private`, thành công có thể quay lại `/private` thay vì `/`. `defaultSuccessUrl(..., true)` có thể thay đổi kết quả. Ghi rõ setup của từng test.

**Không truyền session/cookie sang request mới.** Kiểm tra `authenticated()` ngay sau login chưa chứng minh request mới vẫn đăng nhập. Servlet dùng session sau login; Reactive truyền cookie phiên theo cơ chế thực tế.

**Nhầm 401 với 403.** Trước khi sửa assertion, xem request bị chặn ở bước authentication, authorization hay CSRF; xác định entry point và filter chain của URL.

**Khẳng định tất cả redirect đều tương đối.** `Location` có thể là URL tuyệt đối, phụ thuộc redirect strategy, proxy, host, context path. Khi hành vi yêu cầu cố định URL hoàn chỉnh, hãy assert cả scheme, host, path theo cấu hình.

## 9. Checklist kiểm thử cho một tính năng HTTP login

- Có ca GET tài nguyên bảo vệ khi chưa đăng nhập, xác nhận đúng entry point và đích chuyển hướng.
- Có ca login thành công, xác nhận status, `Location`, principal/authorities và truy cập được tài nguyên trong request mới với session/cookie.
- Có ca mật khẩu sai, xác nhận failure redirect/status, không tồn tại `Authentication` hợp lệ.
- Có ca POST thiếu CSRF và có CSRF hợp lệ để tránh nhầm authentication với request protection.
- Có ca user đã đăng nhập nhưng thiếu quyền, xác nhận 403 hoặc hành vi AccessDeniedHandler đã cấu hình.
- Nếu app dùng tùy biến login URL, username parameter, success/failure handler hoặc saved request, mọi assertion phải theo cấu hình đó.
- Nếu app dùng Servlet và Reactive song song ở các service khác nhau, kiểm chứng bằng đúng công cụ của mỗi stack.

**Kết quả mong đợi:** bài kiểm thử chỉ được coi là bao phủ đăng nhập khi nó chứng minh đồng thời **HTTP response đúng**, **redirect đúng** và **`Authentication` có hiệu lực trên request phù hợp**. Kết hợp ba bằng chứng này giúp phân biệt lỗi nhập mật khẩu, lỗi phân quyền, cấu hình CSRF, redirect và lưu phiên khi kiểm thử Spring Security.
