# Giới hạn của mock Authentication so với kiểm thử toàn bộ chuỗi xác thực

> **Ngữ cảnh:** Spring Security trên Servlet stack, kiểm thử HTTP bằng Spring MVC MockMvc. Trọng tâm là phân biệt kiểm thử **quyền truy cập sau khi đã có danh tính** với kiểm thử **cách hệ thống xác thực danh tính từ HTTP request**. Các ví dụ Java dùng Java 17+, Spring Boot 3.x và Spring Security 6.x; nguyên tắc cũng áp dụng cho các phiên bản tương ứng mới hơn.

## 1. Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Giải thích chính xác `Authentication`, `SecurityContext`, *authentication* (xác thực) và *authorization* (phân quyền).
2. Chỉ ra phần nào được thực thi, phần nào bị đi tắt khi dùng `@WithMockUser`, `user(...)`, `authentication(...)` hoặc `jwt()`.
3. Chọn bài kiểm thử phù hợp để phát hiện lỗi mật khẩu, cấu hình filter, JWT, vai trò/quyền, CSRF và phản hồi 401/403.
4. Viết ít nhất một bài test gửi credential thật qua HTTP request mô phỏng, thay vì chỉ cấp sẵn một principal đã xác thực.

## 2. "Mock Authentication" thực sự làm gì?

Trong Spring Security, interface `Authentication` mô tả một chủ thể và thông tin bảo mật: `principal`, `credentials`, `authorities` và trạng thái `isAuthenticated()`. Một `SecurityContext` thường chứa `Authentication` của request hiện tại.

- **Authentication (quá trình xác thực):** Kiểm tra bằng chứng danh tính, ví dụ username/password, HTTP Basic hoặc Bearer JWT. Thành công mới tạo/xác lập một `Authentication` được tin cậy theo cấu hình.
- **Authorization (phân quyền):** Sau khi đã biết danh tính và quyền, quyết định chủ thể có thể truy cập endpoint hay thực thi hành động không, ví dụ `hasRole("ADMIN")` hay `hasAuthority("SCOPE_reports.read")`.
- **Mock Authentication trong test:** Test dựng sẵn một `Authentication` hoặc `SecurityContext` và đưa nó vào quá trình xử lý. Đây là cách **giả định danh tính đã được xác thực** để tập trung kiểm tra hành vi phía sau.

Một flow HTTP Basic thực tế thường có dạng (các filter cụ thể thay đổi theo cấu hình):

~~~text
HTTP request (Authorization: Basic ...)
    ↓
SecurityFilterChain
    ↓
Filter đọc credential
    ↓
AuthenticationManager / AuthenticationProvider
    ↓
UserDetailsService + PasswordEncoder (ví dụ username/password)
    ↓
SecurityContext chứa Authentication đã xác thực
    ↓
AuthorizationFilter / kiểm tra method security
    ↓
Controller / service
~~~

Khi dùng `@WithMockUser` hoặc `with(user("alice"))`, test **chuẩn bị sẵn** `Authentication` trong ngữ cảnh bảo mật để đoạn xử lý phía sau nhìn thấy user có quyền tương ứng. Nó không chứng minh HTTP header được parse đúng, không tìm user từ kho dữ liệu, không so mật khẩu, không chạy chuỗi đăng nhập thực tế.

**Phân biệt quan trọng:** Giả lập người dùng **không có nghĩa là toàn bộ filter chain bị tắt**. Nếu MockMvc được tích hợp Spring Security đúng cách, các filter và các luật authorization vẫn có thể chạy. Cái bị bỏ qua là **con đường tạo/xác minh danh tính thực**; mức độ bỏ qua cụ thể tùy kỹ thuật mock và cấu hình test.

## 3. Các cách mock và phạm vi chứng minh

| Kỹ thuật | Điều test cung cấp sẵn | Có thể kiểm tra tốt | Không chứng minh được |
| --- | --- | --- | --- |
| `@WithMockUser(username="alice", roles="READER")` | User/authority giả được đặt trong `SecurityContext` của test | Endpoint hay method có cho/khước từ `ROLE_READER` không; code đọc principal thế nào | User alice tồn tại, mật khẩu đúng, request header đăng nhập đúng |
| `mockMvc.perform(get(...).with(user("alice").roles("READER")))` | User giả cho request đó | Phân quyền theo user/role khi chạy MockMvc | `UserDetailsService`, `PasswordEncoder`, đăng nhập HTTP Basic/form |
| `with(authentication(customAuth))` | Đối tượng `Authentication` do test dựng | Logic dựa vào loại principal/authority tùy biến | Hệ thống production thực sự tạo ra đối tượng đó được hay không |
| `@WithUserDetails("alice")` | Tải `UserDetails` qua service rồi dựng ngữ cảnh | Khả năng tải người dùng, ánh xạ quyền từ `UserDetailsService` được dùng trong test | Đăng nhập bằng password thật, HTTP credential parsing, `PasswordEncoder.matches(...)` |
| `with(jwt())` / `with(oauth2Login())` | JWT/principal OAuth2 giả | Kiểm tra phần xử lý đã có JWT/OAuth2 principal và authorities | Kiểm chữ ký, hạn token, issuer, audience, tương tác login/authorization server thực |
| `with(httpBasic("alice","secret"))` | Header HTTP Basic chứa username/password; không cấp sẵn principal | Đường xác thực HTTP Basic, provider, user lookup, password check **nếu dùng bean thật** | TLS/container/network thực; không bao quát JWT hay form login |
| `formLogin()` | Gửi request đăng nhập form mô phỏng, có CSRF hợp lệ theo helper | Form-login filter, credential và xử lý login theo cấu hình | Browser thật, session/cookie qua hạ tầng ngoài tiến trình |

Các helper này thuộc `spring-security-test`. Kết quả phụ thuộc **điều kiện dựng test**: nếu mock `UserDetailsService`, `AuthenticationProvider` hoặc `JwtDecoder` thì phần tương ứng vẫn chưa được kiểm tra thật, dù request có header.

### Một kết quả 200 có thể che lấp lỗi nghiêm trọng

Giả sử cơ sở dữ liệu không có user `ghost`:

~~~java
@Test
@WithMockUser(username = "ghost", roles = "READER")
void readerCanOpenPage() throws Exception {
    mockMvc.perform(get("/me"))
        .andExpect(status().isOk());
}
~~~

Bài test có thể **PASS** vì user `ghost` và quyền `ROLE_READER` đã được cấp sẵn. Nó không hề truy vấn kho user. Vì vậy, kết luận "đăng nhập thành công với ghost" là **sai**. Kết luận hợp lệ là: "nếu request được xử lý dưới ngữ cảnh một user đã xác thực, có ROLE_READER, thì endpoint chấp nhận".

## 4. Ví dụ kiểm thử đối chiếu: mock principal và credential HTTP Basic thực

Ví dụ tối thiểu sau sử dụng Servlet MVC, Spring Boot test và một `InMemoryUserDetailsManager` thực cho môi trường test. Cùng một endpoint `GET /me` có thể nhận principal giả, nhưng khi request gửi HTTP Basic thì password phải khớp dữ liệu đã lưu.

Các dependency cần có trong project Spring Boot 3.x (version do Spring Boot BOM quản lý):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo file `src/test/java/example/AuthenticationBoundaryTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthenticationBoundaryTest.App.class)
@AutoConfigureMockMvc
class AuthenticationBoundaryTest {

    @Autowired
    MockMvc mockMvc;

    // Chỉ chứng minh phân quyền sau khi có Authentication.
    // "ghost" không nằm trong UserDetailsService.
    @Test
    @WithMockUser(username = "ghost", roles = "READER")
    void mockedReaderCanAccessWithoutExistingAccount() throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:ghost"));
    }

    // Credential được chuyển thành HTTP Basic header và xử lý bởi filter.
    @Test
    void basicAuthenticationChecksStoredPassword() throws Exception {
        mockMvc.perform(get("/me").with(httpBasic("reader", "s3cr3t")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:reader"));

        mockMvc.perform(get("/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/me").with(httpBasic("ghost", "whatever")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCredentialsYield401ButMissingAuthorityYields403()
            throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/me").with(user("reader").roles("VIEWER")))
            .andExpect(status().isForbidden());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableWebSecurity
    static class App {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            return http
                .authorizeHttpRequests(registry -> registry
                    .requestMatchers("/me").hasRole("READER")
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        }

        @Bean
        PasswordEncoder passwordEncoder() {
            return new BCryptPasswordEncoder();
        }

        @Bean
        UserDetailsService users(PasswordEncoder encoder) {
            return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                    .password(encoder.encode("s3cr3t"))
                    .roles("READER")
                    .build()
            );
        }

        @Bean
        GreetingController greetingController() {
            return new GreetingController();
        }
    }

    @RestController
    static class GreetingController {
        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello:" + authentication.getName();
        }
    }
}
~~~

Chạy từ project Gradle đã cấu hình Spring Boot:

~~~bash
./gradlew test --tests example.AuthenticationBoundaryTest
~~~

**Kết quả kỳ vọng:** Cả ba phương thức JUnit pass; không có stdout nghiệp vụ bắt buộc. Các assertion xác nhận lần lượt: `ghost` giả → HTTP 200; `reader/s3cr3t` → 200; sai password/user không tồn tại → 401; thiếu header → 401; có principal nhưng thiếu role → 403.

Tại sao ví dụ này có giá trị?

- `@WithMockUser` vượt qua bước xác minh user và password; test đầu có thể pass ngay cả khi `ghost` không tồn tại.
- `httpBasic(...)` tạo header request; với filter chain, `InMemoryUserDetailsManager` và `BCryptPasswordEncoder` thực, test thứ hai kiểm tra được lookup và so khớp mật khẩu.
- `with(user(...))` cho test quyền bị từ chối mà không cần tạo user thật. Vì request **đã xác thực nhưng không đủ quyền**, `403 Forbidden` là đúng trong cấu hình ví dụ.
- `401 Unauthorized` trong test Basic thể hiện không có xác thực hợp lệ. Trong ứng dụng thật, status còn phụ thuộc `AuthenticationEntryPoint`, redirect login, exception handling và loại cơ chế đăng nhập đang bật.

**Ranh giới còn lại:** MockMvc xử lý Servlet MVC bằng mock request/response trong JVM; nó không khởi chạy HTTP socket hay chứng minh reverse proxy, TLS, cookie trên trình duyệt, container và hệ thống nhận dạng bên ngoài hoạt động. Khi cần xác thực cả đường truyền và triển khai, thêm integration/e2e test gửi HTTP thật đến server chạy trên cổng ngẫu nhiên.

## 5. Cần bao nhiêu lớp test cho chuỗi xác thực?

Không có một kỹ thuật đơn lẻ đủ chứng minh mọi khía cạnh. Nên ghép các lớp theo rủi ro:

| Cấp | Ví dụ | Mục tiêu | Giới hạn |
| --- | --- | --- | --- |
| Test logic/authorization | Gọi service với `@WithMockUser`; MockMvc `with(user(...))` | Kiểm soát truy cập, `@PreAuthorize`, xử lý principal, role/authority | Bỏ qua quy trình chứng thực credential |
| MockMvc + Spring Security filter chain | `@SpringBootTest` + `@AutoConfigureMockMvc`; `httpBasic(...)`, `formLogin()` hoặc `Authorization` header thật | Kiểm tra request mapping, filter, provider, status, exception handling | Chỉ chạy trong JVM; còn phụ thuộc các bean bị mock |
| Tích hợp với kho user/decoder thật | Cùng MockMvc hoặc HTTP test với repository DB test, `PasswordEncoder` và `JwtDecoder` cấu hình thật | Bắt lỗi mapping user, hash password, JWT signature/claim validation | Có thể vẫn stub IdP hoặc phần ngoài phạm vi |
| E2E HTTP với server đang chạy | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client, gửi cookie/header/token thật | Gần lưu lượng production hơn: HTTP, chain, session, redirect, cấu hình chạy | Chậm hơn, cần kiểm soát dependency; vẫn chưa tự chứng minh dịch vụ IdP production |

Một test `@WebMvcTest` + `@WithMockUser` rất hữu ích cho **quy tắc authorization ở lớp web**, nhưng chỉ kiểm tra những bean/filter thật sự được nạp vào slice. `@AutoConfigureMockMvc(addFilters = false)` cố ý bỏ các filter đăng ký trong MockMvc: không được dùng kết quả của nó làm bằng chứng SecurityFilterChain/CSRF đang hoạt động.

### Trường hợp JWT Resource Server

Với API dùng Bearer JWT, các test này trả lời những câu hỏi khác nhau:

1. `mockMvc.perform(get("/api/reports").with(jwt().authorities(...)))`: Nếu đã có JWT principal mang authority nhất định, endpoint có chấp nhận không? Helper `jwt()` có thể đi qua các API authentication ở mức mock, nhưng **không chứng minh** `JwtDecoder` production đã giải mã hoặc kiểm chữ ký.
2. Gửi `Authorization: Bearer <signed-token>` đến chain có `JwtDecoder` thật: hệ thống có trích token, kiểm chữ ký, `exp`/`nbf`, issuer/audience (khi validator đã cấu hình), rồi ánh xạ claim → authority không?
3. Gửi token lỗi, hết hạn, sai issuer/audience, sai chữ ký, thiếu scope: có từ chối theo kỳ vọng không, và có vô tình chấp nhận token giả mạo không?

Ví dụ **chỉ là đoạn minh họa, yêu cầu sẵn controller `/api/reports`, security config JWT và import phù hợp**:

~~~java
mockMvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Đoạn trên gán `SCOPE_reports.read` trực tiếp. Nó **không kiểm tra** converter ánh xạ `scope`/`scp` thành authority. Để kiểm tra mapping thật, cần đi qua `JwtAuthenticationConverter` được cấu hình hoặc tập test riêng của converter, không ép authority bằng tay rồi kết luận converter đúng.

Tương tự, `with(oauth2Login())`/`with(oidcLogin())` thuận tiện để test controller sau login, nhưng không thực hiện trọn redirect, authorization code exchange, token validation hay tương tác IdP thực. HTTP integration/E2E hoặc test thành phần liên quan mới bao quát những bước đó.

## 6. Các ca âm tính không được thiếu

Chỉ có happy path trả 200 thường chưa đủ để phát hiện cấu hình security bị hở. Bộ kiểm thử nên chọn các ca có ý nghĩa với cơ chế thực tế:

| Tình huống | Điều cần chứng minh | Kỳ vọng thường gặp |
| --- | --- | --- |
| Không credential đến API yêu cầu xác thực | Endpoint không mở ẩn danh | 401 với HTTP Basic/Bearer; có thể redirect khi cấu hình form login |
| Username không tồn tại hoặc password sai | Provider thực sự kiểm credential | Không được trả 200; thường 401 với HTTP Basic |
| User hợp lệ nhưng thiếu authority | Authorization chạy sau authentication | 403 trong ví dụ HTTP Basic |
| Role/authority đúng | Quy tắc cho phép đúng chủ thể | 200/2xx tương ứng nghiệp vụ |
| Token giả chữ ký, hết hạn, sai issuer hoặc audience | Decoder + validator có hiệu lực | Reject; thường 401 với Bearer |
| Token thật nhưng thiếu scope | Không nhầm lỗi xác thực với thiếu quyền | Thường 403 |
| POST/PUT/DELETE với CSRF bật | Chính sách CSRF có hiệu lực | Thiếu hoặc sai token bị 403; hợp lệ được xử lý theo quyền |
| Request vào URL khác, phương thức khác hoặc thứ tự filter khác | `SecurityFilterChain` match đúng endpoint và thứ tự | Chặn/cho phép đúng theo cấu hình |

**CSRF:** Trong ứng dụng Servlet có CSRF enabled, request POST/PUT/PATCH/DELETE có thể nhận 403 **dù Authentication và role đều đúng**. Khi kiểm thử nghiệp vụ đã xác thực, dùng `with(csrf())` nếu cần token hợp lệ; để xác nhận bảo vệ CSRF, viết ca thiếu token hoặc `with(csrf().useInvalidToken())` riêng. Đừng hiểu mọi 403 là thiếu role.

**Kiểm tra lỗi đúng tầng:** Nếu controller nhận `@AuthenticationPrincipal CustomUser` nhưng test dùng `@WithMockUser` (principal mặc định kiểu Spring Security `User`), lỗi kiểu principal trong production có thể bị che hoặc làm test sai hướng. Dùng `@WithSecurityContext`/`authentication(...)` với principal đúng kiểu cho test nghiệp vụ, và test đường tạo principal thực cho authentication.

## 7. Các sai lầm thường gặp và cách sửa

**Sai lầm 1 — Dùng `@WithMockUser` để xác nhận "đăng nhập đúng mật khẩu".** Annotation không gửi username/password đến `UsernamePasswordAuthenticationFilter`/`BasicAuthenticationFilter` và không gọi `PasswordEncoder.matches(...)`. Muốn kiểm mật khẩu, gửi credential qua `httpBasic(...)` hoặc `formLogin()`; dùng `UserDetailsService`/provider thật và xác nhận cả ca sai.

**Sai lầm 2 — Có MockMvc là cho rằng SecurityFilterChain đã chạy.** Với `MockMvcBuilders.standaloneSetup(...)` hoặc cấu hình bỏ filter, authentication/authorization có thể không được tích hợp. Với `MockMvcBuilders.webAppContextSetup(context)`, tích hợp `springSecurity()`; với Boot, cấu hình `@AutoConfigureMockMvc` và kiểm tra filter chain thực sự hiện diện. Không dùng `addFilters = false` làm test bảo mật.

**Sai lầm 3 — Nhầm `roles("ADMIN")` với `authorities("ADMIN")`.** Trong các helper Spring Security, `roles("ADMIN")` tạo authority `ROLE_ADMIN`; `hasRole("ADMIN")` cũng kiểm `ROLE_ADMIN` theo mặc định. `authorities("ADMIN")` tạo đúng chuỗi `ADMIN`, thường không khớp `hasRole("ADMIN")`. Với OAuth2 scope, authority thường mang tiền tố `SCOPE_`, tùy converter cấu hình.

**Sai lầm 4 — Dùng `@WithUserDetails` rồi kết luận password/OTP/MFA đã được kiểm.** Annotation có thể nạp user thật từ service, nhưng không trình diễn chứng thực credential hay second factor. Tách test xác thực đa bước và test quyền sau khi đăng nhập.

**Sai lầm 5 — Mock `JwtDecoder` rồi khẳng định JWT có chữ ký hợp lệ.** Nếu decoder trả sẵn `Jwt`, bài test chỉ chứng minh đường đi sau decoder; cần test riêng với decoder/validator thật và token ký với khóa test khi muốn bắt lỗi mật mã và claim validation.

**Sai lầm 6 — Dùng annotation mock ở test gửi HTTP đến server thật.** `@WithMockUser` nạp `SecurityContext` của luồng chạy test, không tự được truyền qua socket đến request server. Với test `RANDOM_PORT` phải tự đưa credential/token/cookie vào HTTP client.

**Sai lầm 7 — Chỉ assert 200.** Nếu bảo vệ bị tắt, nhiều happy-path vẫn 200. Luôn bổ sung ca không login, sai credential, thiếu quyền và các cơ chế như CSRF phù hợp ứng dụng.

## 8. Quy trình thiết kế test cho một endpoint bảo vệ

Trước khi thêm test, trả lời tuần tự:

1. **Đường vào của danh tính là gì?** HTTP Basic, form login, session, opaque token, JWT, SSO/OIDC hay cơ chế khác?
2. **Đang kiểm bước nào?** Tạo/xác minh `Authentication`, ánh xạ principal → authority, hay quyết định authorization sau khi xác thực?
3. **Bean nào là thật?** `SecurityFilterChain`, provider, `UserDetailsService`, `PasswordEncoder`, `JwtDecoder`, converter, repository hay IdP có bị mock/stub không?
4. **Tiêu chuẩn pass/fail là gì?** Cặp request hợp lệ và sai credential; đã xác thực nhưng thiếu quyền; anonymous; trạng thái 401/403/redirect; body/side effect.
5. **Có ít nhất một test "không thể pass nếu vô hiệu hóa xác thực" không?** Ví dụ sai password bị 401, token giả chữ ký bị reject, không header bị chặn. Đây là bằng chứng mạnh hơn một test mock-user 200.
6. **Có nhất quán Servlet stack không?** Bài này nói về `MockMvc` và Servlet. Ứng dụng Spring WebFlux cần `WebTestClient` cùng các tiện ích test reactive riêng.

### Bài tự kiểm tra ngắn

- Test `@WithMockUser(roles="ADMIN")` truy cập `/admin` được 200. Có chứng minh admin tồn tại trong database? **Không.** Chỉ chứng minh luật cho phép principal giả có `ROLE_ADMIN`.
- Test `httpBasic("admin","wrong")` trả 401 khi dùng provider và encoder thật. Có kiểm tra bước xác thực password? **Có**, trong phạm vi cấu hình HTTP Basic và các bean thật của test.
- Test `with(jwt().authorities(...))` trả 200. Có chứng minh JWT ký đúng và chưa hết hạn? **Không.** Phải gửi token thực qua Bearer và dùng decoder/validator thật nếu muốn xác minh những thuộc tính đó.

## 9. Ghi nhớ khi review test

**Mock Authentication là công cụ cô lập authorization, không phải bằng chứng cho toàn bộ authentication pipeline.** Cách kiểm thử vững chắc là giữ test mock gọn và nhiều tình huống quyền, sau đó bổ sung test credential/token đi qua filter chain với bean bảo mật thật, negative cases và HTTP end-to-end khi rủi ro triển khai yêu cầu.

### Tài liệu chính thức để tra cứu

- Spring Security — Testing / Spring MVC: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Running as a User in Spring MVC Test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Setting Up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Testing OAuth 2.0 (JWT, OAuth2 login): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Framework — MockMvc vs HTTP end-to-end: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html