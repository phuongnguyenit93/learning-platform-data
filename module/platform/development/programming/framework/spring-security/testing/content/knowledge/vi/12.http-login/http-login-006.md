# Kiểm thử tài khoản bị khóa, hết hạn hoặc bị vô hiệu hóa

Một hệ thống có thể nhận đúng tên đăng nhập và mật khẩu nhưng vẫn phải từ chối truy cập: tài khoản đã bị quản trị viên khóa, người dùng đã hết hạn sử dụng, mật khẩu cần đổi hoặc tài khoản đã bị vô hiệu hóa. Trong Spring Security, đây là các **lỗi xác thực (authentication)**, khác với trường hợp người dùng đã đăng nhập nhưng **không đủ quyền (authorization)**.

Bài học này sử dụng `spring-security-test` để kiểm chứng hành vi HTTP thực tế trên hai mô hình: **Servlet với MockMvc** và **Reactive với WebTestClient**. Mục tiêu là kiểm tra yêu cầu có thực sự đi qua bộ lọc bảo mật và cơ chế xác thực hay không; đồng thời nhận biết lúc nào `@WithMockUser`, `mockUser()` hoặc JWT/OAuth2 giả lập chỉ phù hợp để kiểm tra phân quyền.

## 1. Bốn trạng thái tài khoản trong `UserDetails`

Đối với xác thực tên đăng nhập/mật khẩu dựa trên `UserDetailsService` và `DaoAuthenticationProvider`, Spring Security xét bốn điều kiện sau:

| Phương thức trong `UserDetails` | Ý nghĩa khi trả về `false` | Ngoại lệ xác thực thường gặp |
| --- | --- | --- |
| `isAccountNonLocked()` | Tài khoản **bị khóa**; ví dụ khóa do nhập sai nhiều lần hoặc quyết định của quản trị viên | `LockedException` |
| `isEnabled()` | Tài khoản **bị vô hiệu hóa**; ví dụ chưa kích hoạt hoặc đã ngừng cung cấp dịch vụ | `DisabledException` |
| `isAccountNonExpired()` | **Tài khoản hết hạn**; thời hạn của chính tài khoản đã kết thúc | `AccountExpiredException` |
| `isCredentialsNonExpired()` | **Thông tin đăng nhập hết hạn**; thường là mật khẩu cần được thay đổi | `CredentialsExpiredException` |

Tên phương thức dùng dạng phủ định: `isAccountNonLocked() == true` nghĩa là tài khoản *không bị khóa*. Vì vậy, khi dùng bộ dựng `User` trong ví dụ, `accountLocked(true)` sẽ tạo ra đối tượng có `isAccountNonLocked() == false`.

Trong luồng chuẩn của `DaoAuthenticationProvider`, bộ kiểm tra *trước khi so khớp mật khẩu* xem xét trạng thái khóa, vô hiệu hóa và hết hạn tài khoản; sau khi mật khẩu hợp lệ, bộ kiểm tra tiếp theo xem xét thời hạn thông tin đăng nhập. Nếu một tài khoản đồng thời vi phạm nhiều điều kiện, ngoại lệ đầu tiên theo thứ tự kiểm tra có thể che các điều kiện còn lại. Vì vậy hãy tạo **một trạng thái lỗi độc lập cho mỗi ca kiểm thử**.

Một tài khoản bị khóa không đồng nghĩa với một tài khoản bị vô hiệu hóa. Hai trạng thái có thể được quản lý và mở lại theo quy trình nghiệp vụ khác nhau. Tương tự, **hết hạn tài khoản** không giống **hết hạn mật khẩu**.

## 2. Kỳ vọng ở lớp HTTP: phân biệt 401, 403 và chuyển hướng

Kết quả HTTP phụ thuộc vào kiểu xác thực và `AuthenticationEntryPoint` / `AccessDeniedHandler` được cấu hình:

| Tình huống | HTTP Basic hoặc REST API thông thường | Form Login mặc định | Giải thích |
| --- | --- | --- | --- |
| Tài khoản hợp lệ, có quyền | `200 OK` | Đăng nhập thành công rồi chuyển hướng | Đã xác thực và được cấp quyền |
| Tài khoản bị khóa, vô hiệu hóa, hết hạn | `401 Unauthorized` | Chuyển hướng tới `/login?error` | Không tạo phiên đăng nhập hợp lệ |
| Sai mật khẩu hoặc không có thông tin xác thực | Thường là `401` | Thất bại đăng nhập hoặc chuyển tới trang đăng nhập | Không xác thực thành công |
| Đã xác thực nhưng thiếu vai trò được yêu cầu | `403 Forbidden` | Thường là `403` | Xác thực thành công, phân quyền thất bại |
| Yêu cầu thay đổi dữ liệu thiếu CSRF token khi CSRF được bật | Có thể là `403` | Có thể là `403` | Bộ lọc CSRF từ chối yêu cầu, không chứng minh tài khoản bị khóa |

Với endpoint phục vụ trình duyệt và API trong cùng một ứng dụng, `Accept: text/html` có thể dẫn tới chuyển hướng đăng nhập, còn yêu cầu API thường nhận `401`. Không khẳng định mọi ứng dụng đều dùng đúng một mã trạng thái: cấu hình entry point, bộ xử lý lỗi và cơ chế xác thực của dự án mới quyết định hành vi cuối cùng.

`spring-security-test` giúp viết các kiểm thử có ý nghĩa ở hai cấp:

1. **Kiểm thử xác thực thật:** gửi username/password qua HTTP Basic hoặc form login để `AuthenticationManager` và `UserDetailsService` được sử dụng.
2. **Kiểm thử phân quyền:** đặt sẵn một `Authentication` giả lập bằng `@WithMockUser` hoặc `mockUser()` rồi kiểm tra endpoint được phép hay bị chặn.

Hai cấp này bổ sung cho nhau nhưng không thay thế lẫn nhau.

## 3. Ví dụ Servlet: thiết lập tài khoản và endpoint

Trong ứng dụng Spring Boot dùng Spring MVC, cần có dependency kiểm thử:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Ví dụ cấu hình dưới đây sử dụng `{noop}` chỉ để minh họa trong môi trường kiểm thử. Ứng dụng thật phải dùng bộ mã hóa mật khẩu thích hợp, chẳng hạn BCrypt, và lưu trữ trạng thái tài khoản từ nguồn dữ liệu đáng tin cậy.

~~~java
@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/profile").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("active")
                .password("{noop}secret").roles("USER").build(),
            User.withUsername("locked")
                .password("{noop}secret").roles("USER")
                .accountLocked(true).build(),
            User.withUsername("disabled")
                .password("{noop}secret").roles("USER")
                .disabled(true).build(),
            User.withUsername("expired")
                .password("{noop}secret").roles("USER")
                .accountExpired(true).build(),
            User.withUsername("credentialsExpired")
                .password("{noop}secret").roles("USER")
                .credentialsExpired(true).build()
        );
    }
}

@RestController
class ProfileController {

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "ADMIN";
    }
}
~~~

Các lớp trên sử dụng những import tương ứng thuộc `org.springframework.security.*`, `org.springframework.context.annotation.*` và `org.springframework.web.bind.annotation.*`. Trong ứng dụng thật, tích hợp `ServletSecurityConfig` và `ProfileController` vào component scan trước khi chạy kiểm thử.

Endpoint `/profile` yêu cầu đăng nhập. Endpoint `/admin` yêu cầu authority `ROLE_ADMIN`. Mọi tài khoản thử nghiệm đều có `ROLE_USER`, nhờ đó ta phân biệt được trường hợp **xác thực bị từ chối** với trường hợp **đã xác thực nhưng thiếu quyền**.

## 4. MockMvc: kiểm tra trạng thái thông qua bộ lọc xác thực thật

`@SpringBootTest` kết hợp `@AutoConfigureMockMvc` tải ứng dụng và tích hợp Spring Security filter chain. `httpBasic(username, password)` tạo header `Authorization: Basic ...` để bộ lọc xác thực xử lý yêu cầu.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
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

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AccountStatusMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void activeAccountCanAccessProfile() throws Exception {
        mvc.perform(get("/profile")
                .with(httpBasic("active", "secret"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello active"))
            .andExpect(authenticated().withUsername("active"));
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "locked", "disabled", "expired", "credentialsExpired"
    })
    void nonActiveAccountCannotAuthenticate(String username) throws Exception {
        mvc.perform(get("/profile")
                .with(httpBasic(username, "secret"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(unauthenticated());
    }

    @Test
    void lockedAccountCannotLogInWithForm() throws Exception {
        mvc.perform(formLogin()
                .user("locked")
                .password("secret"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsForbidden() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("active", "secret"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "locked", roles = "USER")
    void mockUserBypassesRealAccountStatusChecks() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("locked"));
    }
}
~~~

Trong bài kiểm thử `nonActiveAccountCannotAuthenticate`, cả bốn tài khoản đều dùng **đúng mật khẩu** nhưng vẫn bị từ chối. Đây là bằng chứng HTTP cho việc xác thực không thành công do trạng thái tài khoản, khi được kết hợp với dữ liệu `UserDetails` đã thiết lập. Kiểm thử `activeAccountCanAccessProfile` là đối chứng dương, giúp phát hiện cấu hình sai khiến tất cả tài khoản đều bị từ chối.

Ca `lockedAccountCannotLogInWithForm` sử dụng `formLogin()` của `spring-security-test`, vốn tạo yêu cầu form đăng nhập phù hợp với cấu hình mặc định. Nếu ứng dụng đổi `loginProcessingUrl`, tham số username/password hoặc URL thất bại, phải sửa request builder và kỳ vọng cho đúng cấu hình thực tế.

**Điểm rất dễ nhầm:** `@WithMockUser(username = "locked")` tự đặt một người dùng đã được xác thực vào `SecurityContext` của bài kiểm thử. Nó không hỏi `UserDetailsService` liệu username `locked` có bị khóa hay không và không chạy bước kiểm tra trạng thái của `DaoAuthenticationProvider`. Vì vậy bài kiểm thử cuối **cố ý trả về `200`**. Đây là cách kiểm tra phân quyền, không phải cách chứng minh rằng tài khoản bị khóa vẫn đăng nhập được.

Tương tự, `user("locked")` của MockMvc hoặc `@WithUserDetails("locked")` cũng đặt ngữ cảnh xác thực phục vụ test; riêng `@WithUserDetails` có đọc `UserDetailsService` nhưng không biến thao tác đó thành một lần đăng nhập qua `AuthenticationManager`.

## 5. Muốn khẳng định đúng loại ngoại lệ thì kiểm tra ở tầng xác thực

Mã HTTP `401` không cho biết nguyên nhân là `LockedException`, `DisabledException` hay sai mật khẩu, vì ứng dụng thường cố tình trả về thông báo lỗi chung để tránh tiết lộ trạng thái tài khoản. Nếu yêu cầu nghiệp vụ phải phân biệt nội bộ từng nguyên nhân, có thể kiểm thử trực tiếp `DaoAuthenticationProvider`:

~~~java
@Test
void providerRejectsLockedAccount() {
    UserDetailsService users = username ->
        User.withUsername("locked")
            .password("{noop}secret")
            .roles("USER")
            .accountLocked(true)
            .build();

    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(
        PasswordEncoderFactories.createDelegatingPasswordEncoder());

    assertThatThrownBy(() -> provider.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "locked", "secret")))
        .isInstanceOf(LockedException.class);
}
~~~

Đoạn ví dụ dùng `assertThatThrownBy` của AssertJ và các lớp tương ứng trong `org.springframework.security.authentication.*`, `org.springframework.security.core.userdetails.*`, `org.springframework.security.crypto.factory.*`. Có thể viết các test tương tự cho `DisabledException`, `AccountExpiredException` và `CredentialsExpiredException`.

Kiểm thử provider giúp tìm đúng nguyên nhân ở lớp xác thực; kiểm thử MockMvc chứng minh hành vi mà client nhận được sau khi yêu cầu đi qua filter chain. Hai loại kiểm thử trả lời hai câu hỏi khác nhau.

## 6. Reactive: xác thực HTTP Basic với WebTestClient

Với Spring WebFlux, chuỗi lọc bảo mật là `SecurityWebFilterChain` và nguồn tài khoản có thể là `MapReactiveUserDetailsService`. Ví dụ sau dùng một **ứng dụng Reactive riêng** với endpoint `/profile`, không cấu hình đồng thời chuỗi Servlet trong cùng bài thử.

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/profile").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("active")
                .password("{noop}secret").roles("USER").build(),
            User.withUsername("locked")
                .password("{noop}secret").roles("USER")
                .accountLocked(true).build(),
            User.withUsername("disabled")
                .password("{noop}secret").roles("USER")
                .disabled(true).build(),
            User.withUsername("expired")
                .password("{noop}secret").roles("USER")
                .accountExpired(true).build(),
            User.withUsername("credentialsExpired")
                .password("{noop}secret").roles("USER")
                .credentialsExpired(true).build()
        );
    }
}

@RestController
class ReactiveProfileController {

    @GetMapping("/profile")
    Mono<String> profile(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }
}
~~~

`Mono` thuộc Reactor, `Principal` thuộc `java.security`; các lớp security reactive thuộc `org.springframework.security.config.web.server.*`, `org.springframework.security.web.server.*` và `org.springframework.security.core.userdetails.*`.

Có thể dùng `WebTestClient` để thực sự gửi yêu cầu HTTP tới ứng dụng WebFlux đang chạy trong kiểm thử Spring Boot:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AccountStatusWebFluxTest {

    @Autowired
    WebTestClient client;

    @Test
    void activeUserCanAccessProfile() {
        client.get()
            .uri("/profile")
            .headers(headers -> headers.setBasicAuth("active", "secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("active");
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "locked", "disabled", "expired", "credentialsExpired"
    })
    void nonActiveUserIsRejected(String username) {
        client.get()
            .uri("/profile")
            .headers(headers -> headers.setBasicAuth(username, "secret"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Lớp kiểm thử này cần các import JUnit Jupiter, `@SpringBootTest`, `@AutoConfigureWebTestClient`, `@Autowired` và `org.springframework.test.web.reactive.server.WebTestClient`. Một ứng dụng WebFlux cần các dependency WebFlux, Security và Security Test phù hợp. Khi dùng server thật (`RANDOM_PORT`), header Basic được gửi qua HTTP và cơ chế xác thực Reactive sẽ xử lý nó.

`mockUser()` và `mockAuthentication()` của `SecurityMockServerConfigurers` dùng khi `WebTestClient` được gắn với ứng dụng hoặc controller mock có áp dụng `springSecurity()`. Chúng tạo danh tính trong test, tương tự `@WithMockUser` trên Servlet, nên **không xác minh** tài khoản trong `MapReactiveUserDetailsService` có bị khóa hay không. Với mục tiêu kiểm tra khóa tài khoản, hãy dùng đường xác thực thật như ví dụ Basic ở trên.

## 7. JWT, OAuth2 và OIDC: trạng thái tài khoản không tự suy ra từ token giả

Spring Security Test có các công cụ như `jwt()`, `oauth2Login()` và `oidcLogin()`. Chúng hữu ích để kiểm thử request đã có danh tính, claims hoặc authorities mong muốn. Tuy nhiên:

- `jwt()` trong MockMvc tạo trạng thái `JwtAuthenticationToken` giả lập; nó không tự kiểm tra người dùng đang bị vô hiệu hóa trong database.
- `oauth2Login()` và `oidcLogin()` giả lập phiên đăng nhập OAuth2/OIDC thành công; chúng không chứng minh quá trình gọi nhà cung cấp danh tính đã từ chối một tài khoản bị khóa.
- Token JWT hết hạn (`exp`) là vấn đề **hiệu lực token**, không đồng nhất với `isAccountNonExpired()` hoặc `isCredentialsNonExpired()` của tài khoản nội bộ.
- Nếu API cần chặn ngay một tài khoản đã bị khóa trong lúc access token còn hạn, ứng dụng phải có chính sách thực thi riêng, chẳng hạn tra trạng thái user lúc xử lý yêu cầu, hủy phiên, thu hồi token hoặc kiểm tra trạng thái qua authorization logic. Chỉ tạo `jwt()` với một claim tự đặt không kiểm thử được chính sách đó.

Để kiểm thử việc từ chối JWT **thật sự không hợp lệ**, cần cho request đi qua Resource Server với decoder và các validator thực tế hoặc được cấu hình cho test; `jwt()` là công cụ bỏ qua khâu decode. Để kiểm thử trạng thái tài khoản trong hệ thống OIDC, cần kiểm tra hành vi của integration thực tế hoặc quy tắc ánh xạ/truy vấn trạng thái mà ứng dụng triển khai. Không suy luận hành vi này chỉ từ một request có identity giả lập.

## 8. Bộ ca kiểm thử nên có

| Ca | Cách kích hoạt phù hợp | Điều cần xác nhận |
| --- | --- | --- |
| Đăng nhập thành công | Basic hoặc Form với tài khoản `active` | Được phép vào endpoint cần xác thực |
| Bị khóa | Basic/Form với `accountLocked(true)` | Xác thực thất bại, không truy cập endpoint bảo vệ |
| Bị vô hiệu hóa | Basic/Form với `disabled(true)` | Xác thực thất bại |
| Hết hạn tài khoản | Basic/Form với `accountExpired(true)` | Xác thực thất bại |
| Hết hạn thông tin đăng nhập | Basic/Form với `credentialsExpired(true)` | Xác thực thất bại |
| Sai mật khẩu | Basic/Form với `active` nhưng sai password | Xác thực thất bại, tránh nhầm nguyên nhân |
| Có danh tính nhưng thiếu quyền | Xác thực user thường rồi GET `/admin` | `403`, tách biệt lỗi authorization |
| Mock user trùng tên tài khoản bị khóa | `@WithMockUser` hoặc `mockUser()` | Endpoint có thể trả `200` vì đã bỏ qua provider |
| Đổi trạng thái khi đã có session/token | Giữ phiên/token cũ rồi khóa user | Hành vi đúng với chính sách thu hồi phiên/token của ứng dụng |

Với trường hợp cuối, thay đổi `UserDetails` trong kho dữ liệu **không mặc nhiên** khiến mọi session đã đăng nhập hoặc mọi JWT còn hạn bị từ chối ở request tiếp theo. Nếu yêu cầu bảo mật đòi hỏi có hiệu lực ngay, cần kiểm thử riêng cơ chế vô hiệu hóa session, tra cứu trạng thái hoặc thu hồi token.

## 9. Những lỗi phổ biến làm bài kiểm thử đánh lừa người viết

**Dùng `@WithMockUser` để thử tài khoản bị khóa.** Annotation đặt sẵn danh tính hợp lệ, nên test `200` không phải là bằng chứng hệ thống đã bỏ qua chính sách khóa tài khoản ở lần đăng nhập thật.

**Chỉ kiểm tra `403` cho mọi trường hợp bị từ chối.** Với HTTP Basic, không thể xác thực thường là `401`; đã xác thực nhưng thiếu quyền mới thường là `403`. Với Form Login, lỗi đăng nhập thường là chuyển hướng chứ không nhất thiết là `401`.

**Quên security filter chain trong test.** Nếu tự dựng `MockMvc` bằng `standaloneSetup` mà không gắn Spring Security, yêu cầu có thể đi thẳng vào controller. Hãy dùng `@AutoConfigureMockMvc` trong kiểm thử tích hợp hoặc áp dụng `springSecurity()` khi tự `webAppContextSetup`.

**Vô hiệu hóa CSRF chỉ để test đăng nhập chạy qua.** Khi kiểm thử form login, nên dùng `formLogin()` hoặc gửi đúng CSRF token bằng `csrf()` nếu request được dựng thủ công. Đừng biến lỗi `403` do thiếu CSRF thành kết luận về trạng thái tài khoản.

**Khẳng định nội dung lỗi quá chi tiết.** Một API có thể chủ động trả thông báo chung cho mọi thất bại đăng nhập để tránh tiết lộ rằng username nào đang tồn tại, bị khóa hay bị vô hiệu hóa. Kiểm tra chi tiết ngoại lệ tại tầng provider, còn ở HTTP kiểm tra hợp đồng phản hồi công khai của ứng dụng.

**Dùng cùng một user vi phạm nhiều cờ trạng thái.** Bài test lúc đó chỉ quan sát được ngoại lệ được ném đầu tiên. Hãy tạo các tài khoản thử riêng với đúng một điều kiện bất hợp lệ.

## 10. Bài tập thực hành

1. Bổ sung tài khoản `wrongPassword` còn hiệu lực và viết test Basic dùng mật khẩu sai. So sánh kết quả HTTP với `locked` để thấy rằng cùng `401` không đồng nghĩa cùng nguyên nhân nội bộ.
2. Viết test riêng với `DaoAuthenticationProvider` để xác nhận `DisabledException`, `AccountExpiredException` và `CredentialsExpiredException`. Dùng mỗi lần đúng một cờ trạng thái sai.
3. Thêm endpoint `/admin` có `hasRole("ADMIN")`. Đối chiếu hai ca: tài khoản `active` với `ROLE_USER` nhận `403`, còn user giả lập có `ROLE_ADMIN` được phép truy cập.
4. Với WebFlux, lặp lại bảng kiểm thử HTTP Basic bằng `WebTestClient` rồi thử `mockUser("locked")` trong client gắn với application context. Giải thích vì sao hai cách cho kết quả khác nhau.
5. Nếu hệ thống đang dùng session hoặc JWT, xác định yêu cầu nghiệp vụ khi quản trị viên khóa một tài khoản đã đăng nhập, rồi viết kiểm thử tích hợp cho chính cơ chế hủy hoặc từ chối session/token đó.

Khi hoàn thành, người học phải phân biệt được **trạng thái tài khoản trong nguồn dữ liệu**, **kết quả xác thực của provider**, **phản hồi HTTP của chuỗi lọc bảo mật** và **danh tính giả lập phục vụ kiểm thử phân quyền**. Đây là bốn lớp quan sát khác nhau và cần các phép kiểm thử phù hợp với từng lớp.
