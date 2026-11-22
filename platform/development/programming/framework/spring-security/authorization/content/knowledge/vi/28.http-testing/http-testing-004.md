# Kiểm thử người chưa xác thực, đúng quyền và thiếu quyền

Trong Spring Security (Servlet), một endpoint được bảo vệ đúng phải xử lý **ít nhất ba trạng thái khác nhau**: người gọi **chưa xác thực**, người gọi **đã xác thực và có đủ quyền**, và người gọi **đã xác thực nhưng thiếu quyền**. Kiểm thử HTTP cần chứng minh cả ba qua đường đi request thực tế, bao gồm security filter chain, cơ chế xác thực, quy tắc authorization và phản hồi HTTP. Kiểm tra duy nhất một lần gọi thành công không đủ để kết luận endpoint an toàn.

Bài này thuộc nhóm **Kiểm thử HTTP** của module **Spring Security - authorization**. Ví dụ sử dụng **Spring Boot 3.x, Spring Security 6.x, Java 17+**, JUnit 5 và MockMvc, với một SecurityFilterChain sử dụng HTTP Basic để kết quả 401/403 dễ quan sát. Khi chuyển sang form login, OAuth2 Bearer hoặc một custom entry point, cần giữ nguyên mục tiêu kiểm thử nhưng điều chỉnh kỳ vọng HTTP theo cấu hình thực tế.

## 1. Ba trạng thái và câu hỏi cần kiểm chứng

| Trạng thái của request | Ví dụ | Điều cần chứng minh | HTTP thường thấy trong ví dụ Basic |
| --- | --- | --- | --- |
| **Chưa xác thực** | Không gửi `Authorization` khi đọc báo cáo cần role | Tài nguyên được bảo vệ không bị trả ra, hệ thống yêu cầu xác thực | `401 Unauthorized`, có `WWW-Authenticate: Basic ...` |
| **Đã xác thực, đủ quyền** | `analyst` có `ROLE_ANALYST` đọc báo cáo | Request đi qua authentication và authorization, nhận đúng dữ liệu được phép | `200 OK` cùng nội dung đúng |
| **Đã xác thực, thiếu quyền** | `viewer` có `ROLE_VIEWER` đọc báo cáo đòi `ANALYST` | Bị từ chối, không gọi hành động được bảo vệ hoặc lộ nội dung nhạy cảm | `403 Forbidden` |
| **Credentials không hợp lệ** | Username đúng, password sai | Xác thực thất bại, không được xem như người dùng đã đăng nhập | `401 Unauthorized` |
| **Có quyền nhưng thiếu CSRF token** | `admin` POST lên endpoint thay đổi trạng thái mà không có token | Lớp chống CSRF chặn request trước khi thực thi hành động | `403 Forbidden` trong cấu hình mặc định |

Phân biệt hai khái niệm:

- **Authentication** (xác thực) trả lời *principal là ai, credential có hợp lệ không?*; ví dụ `BasicAuthenticationFilter` và `AuthenticationManager` xác thực tên đăng nhập/mật khẩu.
- **Authorization** (phân quyền) trả lời *principal này được thực hiện hành động gì trên tài nguyên nào?*; ví dụ `AuthorizationFilter` áp dụng `authorizeHttpRequests` hoặc method security kiểm tra `@PreAuthorize`.

Một 403 không luôn có nghĩa là *thiếu role*: nó cũng có thể do CSRF, rule khác, method security hay kiểm tra quyền ở mức đối tượng. Tương tự, trong ứng dụng dùng `formLogin`, anonymous có thể được chuyển hướng `302` đến trang đăng nhập; với Bearer token, yêu cầu có thể dùng `WWW-Authenticate: Bearer ...`. Vì vậy bài kiểm thử phải kiểm tra **quy tắc dự kiến**, sau đó mới xác nhận status/header tương ứng.

## 2. Mục tiêu của một HTTP security test đáng tin

Một kiểm thử đủ tốt xác nhận đồng thời:

1. **Đúng đường dẫn và phương thức**: `GET /api/reports/summary` khác `POST /api/admin/publish`, và khác `GET /api/admin/audit`.
2. **Đúng cơ chế xác thực**: anonymous, Basic credentials đúng/sai, hoặc token/session hợp lệ theo ứng dụng.
3. **Đúng vai trò/authority**: phân biệt `ROLE_ANALYST`, `ROLE_VIEWER`, `ROLE_ADMIN`, không đồng nhất có đăng nhập với có quyền.
4. **Đúng mã HTTP và header**: phản hồi 401 có challenge thích hợp; phản hồi 403 không giả vờ thành 200; 302 chỉ là mong đợi khi có redirect login.
5. **Đúng nội dung thành công**: không chỉ `status().isOk()`; kiểm tra dữ liệu/DTO chứa thông tin được phép.
6. **Không lộ dữ liệu khi bị từ chối**: kiểm tra body/header không chứa nội dung nghiệp vụ được bảo vệ.
7. **Không gây side effect khi bị từ chối**: POST/DELETE phải chứng minh dữ liệu không đổi hoặc service không được gọi nếu quyền/CSRF không hợp lệ.
8. **Tính ổn định của test**: cấu hình security thực được nạp, filter chain tham gia, không vô tình tắt filter khi dựng MockMvc.

**Bề mặt kiểm thử:** MockMvc mô phỏng request Servlet trong tiến trình, có thể chạy qua `FilterChainProxy` và Spring MVC mà **không mở cổng HTTP thật**. Nó hữu ích để kiểm tra authentication, authorization và response contract; nhưng không thay thế kiểm thử HTTPS, reverse proxy, cookie domain, CORS, load balancer hoặc hệ thống IAM thật trên môi trường tích hợp.

## 3. Xác định ma trận quyền trước khi viết test

Giả sử ứng dụng có ba tài khoản in-memory để học:

- `analyst/pw` với role `ANALYST`: đọc báo cáo.
- `viewer/pw` với role `VIEWER`: đăng nhập được nhưng không đọc được báo cáo hoặc chức năng admin.
- `admin/pw` với role `ADMIN`: đọc báo cáo, đọc audit và xuất bản tài liệu quản trị.

Quy tắc trong ví dụ:

| Endpoint | Anonymous | ANALYST | VIEWER | ADMIN |
| --- | --- | --- | --- | --- |
| `GET /api/public` | 200 | 200 | 200 | 200 |
| `GET /api/reports/summary` | 401 | 200 | 403 | 200 |
| `GET /api/admin/audit` | 401 | 403 | 403 | 200 |
| `POST /api/admin/publish` (CSRF hợp lệ) | 401 | 403 | 403 | 200 |
| `POST /api/admin/publish` (thiếu CSRF) | 403 | 403 | 403 | 403 |

Đây là **ma trận của cấu hình mẫu**, không phải quy tắc chung cho mọi ứng dụng. Thứ tự Spring Security filter khiến một POST thiếu CSRF token bị chặn 403 ngay cả khi chưa có thông tin xác thực. Nếu truyền token CSRF hợp lệ vào POST, authorization mới thể hiện rõ nhánh anonymous 401 hoặc thiếu quyền 403.

Mỗi hàng cần ít nhất một test đại diện, và mọi endpoint có quyền cao cần cả kiểm thử **positive** (được phép) lẫn **negative** (bị chặn). Với quyền đa tenant hoặc object-level, ma trận cần thêm **owner, non-owner, khác tenant, trạng thái tài nguyên và thời hạn quyền**.

## 4. Chuẩn bị ứng dụng Spring Boot 3.x để chạy thử

Sử dụng dự án Spring Boot Servlet đã có plugin Gradle và Java 17+. Các dependency trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter và Spring Boot Test/MockMvc; `spring-security-test` cung cấp `httpBasic()`, `csrf()`, `user()`, `@WithMockUser` cùng nhiều tiện ích kiểm thử bảo mật. Trong Gradle, dự án cần chạy JUnit Platform; Spring Boot plugin/starter template thường thiết lập như sau:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 4.1. Ứng dụng và SecurityFilterChain đầy đủ

Tạo file `src/main/java/com/example/authorization/HttpAuthorizationApplication.java`:

~~~java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class HttpAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpAuthorizationApplication.class, args);
    }

    @GetMapping("/api/public")
    public String publicData() {
        return "public";
    }

    @GetMapping("/api/reports/summary")
    public String reportSummary() {
        return "report:ready";
    }

    @GetMapping("/api/admin/audit")
    public String auditSummary() {
        return "admin:audit";
    }

    @PostMapping("/api/admin/publish")
    public String publish() {
        return "published";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports/summary")
                            .hasAnyRole("ANALYST", "ADMIN")
                        .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                            .hasRole("ADMIN")
                        .requestMatchers(HttpMethod.POST, "/api/admin/publish")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("analyst")
                        .password("{noop}pw").roles("ANALYST").build(),
                User.withUsername("viewer")
                        .password("{noop}pw").roles("VIEWER").build(),
                User.withUsername("admin")
                        .password("{noop}pw").roles("ADMIN").build()
        );
    }
}
~~~

**Giải thích các điểm quyết định:**

- `permitAll()` cho phép truy cập công khai; nó không bắt client phải đăng nhập. Đừng mặc định mọi endpoint đều cần 401 khi anonymous.
- `hasAnyRole("ANALYST", "ADMIN")` yêu cầu một trong các authority `ROLE_ANALYST` hoặc `ROLE_ADMIN`. `User.roles("ADMIN")` thêm prefix `ROLE_`; đừng khai báo `roles("ROLE_ADMIN")` nếu đang dùng API tạo role theo tên ngắn.
- `hasRole("ADMIN")` chặn các principal đã xác thực nhưng không có `ROLE_ADMIN`. `.anyRequest().denyAll()` khóa các route/method chưa có rule được công bố.
- `httpBasic(Customizer.withDefaults())` giúp kiểm tra credentials bằng header `Authorization: Basic ...`; hệ thống dùng Basic phải truyền qua HTTPS trong môi trường thật.
- Không gọi `csrf.disable()`: cơ chế CSRF mặc định còn hiệu lực đối với các phương thức không an toàn như POST. Điều này cho phép viết test phân biệt **thiếu quyền** với **thiếu CSRF token**.
- Mật khẩu `{noop}pw` chỉ phục vụ demo local/test; production cần password hashing thích hợp, credential từ nguồn xác thực thực và không nhúng tài khoản cố định trong mã.

Các controller trả chuỗi cố định để test có thể đối chiếu **nội dung chính xác** thay vì phụ thuộc dữ liệu bên ngoài. Ứng dụng không kết nối database; khi chuyển sang nghiệp vụ thật, cần test thêm quyền đọc theo từng bản ghi và việc từ chối không gây side effect.

## 5. Bộ test MockMvc chạy cùng Spring Security

Tạo file `src/test/java/com/example/authorization/HttpAuthorizationTests.java`:

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAvailableWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadProtectedReport() throws Exception {
        mvc.perform(get("/api/reports/summary"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic ")));
    }

    @Test
    void analystCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("analyst", "pw")))
                .andExpect(status().isOk())
                .andExpect(content().string("report:ready"));
    }

    @Test
    void viewerHasLoginButNotReportPermission() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("viewer", "pw")))
                .andExpect(status().isForbidden());
    }

    @Test
    void analystCannotReadAdminAudit() throws Exception {
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("analyst", "pw")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminAudit() throws Exception {
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("admin", "pw")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin:audit"));
    }

    @Test
    void adminCanAlsoReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("admin", "pw")))
                .andExpect(status().isOk())
                .andExpect(content().string("report:ready"));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("analyst", "wrong")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic ")));
    }

    @Test
    void adminPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("admin", "pw")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithValidCsrfIsAllowed() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("admin", "pw"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("published"));
    }

    @Test
    void viewerPostWithValidCsrfStillHasNoPermission() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("viewer", "pw"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPostWithValidCsrfMustAuthenticate() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(csrf()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminPostWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("admin", "pw"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }
}
~~~

### 5.1. Vì sao phải giữ `@AutoConfigureMockMvc` và bộ lọc bảo mật?

`@SpringBootTest` tải application context với `SecurityFilterChain`, controller và `UserDetailsService` đã cấu hình. `@AutoConfigureMockMvc` tạo MockMvc tích hợp filter chain của ứng dụng; mặc định `addFilters=true`. Vì vậy các request sử dụng `httpBasic("analyst", "pw")` đi qua quá trình xác thực Basic, còn `AuthorizationFilter` kiểm tra authorities trước khi gọi controller.

Nếu tự dựng `MockMvcBuilders.standaloneSetup(controller)` mà không gắn Spring Security, test có thể trả 200 cho request anonymous dù production chặn 401. Với cấu hình MockMvc thủ công sử dụng `webAppContextSetup`, áp dụng `SecurityMockMvcConfigurers.springSecurity()` để thêm security filters cùng test post-processors. Với `@WebMvcTest`, cần kiểm tra rõ security configuration nào được nạp và import/mocks phù hợp; nó không tự thay thế test tích hợp toàn bộ chuỗi.

### 5.2. Vì sao dùng `httpBasic()` thay vì gán sẵn user cho cả ba nhánh?

`SecurityMockMvcRequestPostProcessors.httpBasic(...)` tạo HTTP `Authorization` header đúng định dạng Basic, để bộ lọc xác thực xử lý user/password thật trong test application context. Nhờ đó có thể kiểm chứng **mật khẩu sai trả 401**.

`@WithMockUser` hoặc `.with(user("analyst").roles("ANALYST"))` rất hữu ích khi chỉ cần giả lập principal để test **authorization** nhanh; chúng không chứng minh password được xác thực, token signature hợp lệ hay authentication filter đang chạy đúng. Đừng dùng `@WithMockUser` trên cả test anonymous hoặc wrong password rồi tưởng đã kiểm tra đường đi HTTP Basic. Với JWT/OAuth2, có các hỗ trợ `jwt()`/`oauth2Login()` nhưng mock principal/claims vẫn không thay thế test với token thật và resource server decoder thực tế.

## 6. Chạy test và hiểu kết quả

Tại gốc dự án Spring Boot có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.authorization.HttpAuthorizationTests
~~~

Trên Windows dùng:

~~~powershell
.\gradlew.bat test --tests com.example.authorization.HttpAuthorizationTests
~~~

Khi các test đúng cấu hình đều vượt qua, Gradle kết thúc task test thành công. Phần trên định nghĩa **13 test methods**, kiểm tra các trạng thái sau:

| Test | Kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| `publicEndpointIsAvailableWithoutLogin` | 200 và `public` | Tài nguyên công khai |
| `anonymousCannotReadProtectedReport` | 401 và Basic challenge | Anonymous bị chặn |
| `analystCanReadReport` | 200 và `report:ready` | Đủ quyền |
| `viewerHasLoginButNotReportPermission` | 403 | Đã đăng nhập, thiếu quyền |
| `analystCannotReadAdminAudit` | 403 | Quyền ANALYST không tự trở thành ADMIN |
| `adminCanReadAdminAudit` | 200 và `admin:audit` | Quyền ADMIN hợp lệ |
| `adminCanAlsoReadReport` | 200 và `report:ready` | Route cho phép nhiều role |
| `wrongPasswordIsAuthenticationFailure` | 401 và challenge | Sai credential |
| `adminPostWithoutCsrfIsForbidden` | 403 | CSRF chặn dù ADMIN có role |
| `adminPostWithValidCsrfIsAllowed` | 200 và `published` | Đủ quyền và có CSRF |
| `viewerPostWithValidCsrfStillHasNoPermission` | 403 | Có CSRF vẫn thiếu quyền |
| `anonymousPostWithValidCsrfMustAuthenticate` | 401 | Có CSRF không thay cho đăng nhập |
| `adminPostWithInvalidCsrfIsForbidden` | 403 | Invalid token cũng bị chặn |

Ví dụ test failed khi ai đó vô tình đổi `.requestMatchers(HttpMethod.GET, "/api/reports/summary").hasAnyRole(...)` thành `.permitAll()`: test anonymous từ 401 có thể thành 200, còn test viewer từ 403 thành 200. Đó là **regression bảo mật**, không nên sửa test cho khớp 200. Khi hợp đồng phân quyền thực sự thay đổi theo yêu cầu được phê duyệt, cập nhật ma trận và cả test positive/negative tương ứng.

Nếu muốn thử HTTP thủ công sau khi chạy `./gradlew bootRun`:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports/summary
curl -i -u analyst:pw http://localhost:8080/api/reports/summary
curl -i -u viewer:pw http://localhost:8080/api/reports/summary
curl -i -u admin:pw http://localhost:8080/api/admin/audit
curl -i -u analyst:wrong http://localhost:8080/api/reports/summary
~~~

Các lần GET ở đây cho kết quả lần lượt **200, 401, 200, 403, 200, 401**; với endpoint 401, quan sát `WWW-Authenticate`. POST thay đổi trạng thái cần CSRF token hợp lệ theo session và cấu hình thực; tiện ích `.with(csrf())` trong MockMvc tạo token kiểm thử, không phải token production dùng trực tiếp bằng curl.

## 7. Giải thích 401, 403 và 302 đúng ngữ cảnh

### 7.1. Anonymous và thông tin xác thực sai

Với cấu hình Basic của ví dụ, khi người gọi không có authentication hợp lệ mà endpoint yêu cầu role, phần xử lý bảo mật có thể chuyển `AccessDeniedException` của principal anonymous qua `ExceptionTranslationFilter` tới `AuthenticationEntryPoint`. Entry point cho Basic trả **401** cùng HTTP challenge. Còn credential sai thường bị `BasicAuthenticationFilter` xử lý ngay ở bước xác thực; kết quả cũng **401** nhưng đường đi khác nhau.

Đừng dựa vào câu “`AuthenticationException` luôn là 401, `AccessDeniedException` luôn là 403”. Status thực tế còn tùy entry point, handler, loại principal (anonymous/remember-me/full), chain và bước xử lý xảy ra trước.

### 7.2. Đã xác thực nhưng thiếu quyền

`viewer` đăng nhập Basic thành công và có authority `ROLE_VIEWER`. Rule `hasAnyRole("ANALYST", "ADMIN")` không khớp, nên permission check chặn và trả 403. Kiểm thử cần chứng minh **viewer thực sự đã xác thực**, nếu không một test 401 chỉ nói về thiếu credentials, chưa chứng minh rằng rule phân quyền từ chối một tài khoản hợp lệ thiếu quyền.

### 7.3. Có đủ quyền nhưng request bị chặn bởi cơ chế khác

`admin` có đủ role cho POST nhưng thiếu CSRF token, nên nhận 403. Điều này không mâu thuẫn với test admin đủ quyền. Muốn kiểm tra authorization cho POST, trước hết tạo request đáp ứng các điều kiện an toàn khác: đúng HTTP method, content type, CSRF nếu cần, và dữ liệu hợp lệ. Sau đó mới đánh giá khác biệt giữa role đủ và thiếu.

### 7.4. 302 trong website login

Khi SecurityFilterChain sử dụng `formLogin`, unauthenticated request có thể được chuyển tới `/login` bằng 302/303 thay vì 401. Test website nên kiểm tra mã redirect cùng header `Location` thích hợp; API tiêu thụ JSON có thể cần cấu hình entry point riêng để trả 401. Đừng ép tất cả ứng dụng dùng form login phải trả 401 khi thiết kế thực tế quy định redirect.

### 7.5. Bearer token

Với OAuth2 Resource Server, token thiếu, không hợp lệ, hết hạn hay scope không đủ có thể tạo phản hồi theo Bearer challenge: 401 hoặc 403 tùy lỗi và policy, có thể kèm `WWW-Authenticate: Bearer ...`. Để kiểm tra authorization theo claims/scopes, có thể dùng request post-processors `jwt()` hoặc `opaqueToken()`; để kiểm tra cryptographic validation, decoder/introspection và các failure path thật, cần integration test có thành phần xác thực token phù hợp. Không sao chép kỳ vọng `Basic realm` sang API Bearer.

## 8. Kiểm tra cả nội dung, header và việc không thực hiện nghiệp vụ

**Chỉ status chưa đủ.** Ví dụ endpoint đọc báo cáo trả 200 cùng nội dung mặc định sai hoặc dữ liệu của tenant khác vẫn có thể vượt qua `status().isOk()`. Với REST JSON, dùng `jsonPath` để so khớp id, chủ sở hữu, field được phép, và để khẳng định field nhạy cảm **không tồn tại** trong response. Với tài nguyên bị từ chối, kiểm tra body không chứa PII hoặc nội dung nội bộ. Lưu ý 403 có thể trả một error document tùy cấu hình; không nên khóa test vào body rỗng nếu hợp đồng không yêu cầu như vậy.

Đối với endpoint có side effect, cần test rằng request bị từ chối **không gọi thao tác nguy hiểm**. Chẳng hạn trong service test:

~~~java
// Minh họa: service được thay bằng @MockitoBean hoặc @MockBean
// phù hợp phiên bản Spring Boot; snippet không độc lập.
mvc.perform(post("/api/admin/publish")
        .with(httpBasic("viewer", "pw"))
        .with(csrf()))
    .andExpect(status().isForbidden());

verify(publishService, never()).publish(any());
~~~

Đoạn trên dùng Mockito và giả định controller gọi `publishService.publish(...)`. Với ứng dụng thật, có thể kiểm tra database vẫn giữ nguyên trạng thái sau request bị chặn; điều đó mạnh hơn giả lập về việc không gọi service khi side effect còn có đường khác.

Các assertion hữu ích bổ sung:

- **Challenge header:** dùng `header().string(HttpHeaders.WWW_AUTHENTICATE, startsWith("Basic "))` cho Basic 401. Tránh hardcode realm khi sản phẩm cho phép cấu hình.
- **Content-Type:** nếu API quy định `application/problem+json` hoặc `application/json`, test response của 401/403 theo đúng hợp đồng.
- **Body rò rỉ:** không được chứa token, exception stacktrace, object dữ liệu, password, roles nội bộ hoặc full SQL error.
- **Redirect:** nếu dùng form login, test mã 302 và `Location`, không coi mọi redirect là lỗi.
- **Idempotency và mutation:** request bị từ chối không thêm/sửa/xóa bản ghi, không phát event nghiệp vụ thành công.
- **Cache:** response phụ thuộc principal không bị tái sử dụng cho người ít quyền; phù hợp `Cache-Control` hoặc cache key.
- **Auth context:** principal/tenant từ nguồn được xác thực, không lấy role từ query parameter/header tự khai báo.

## 9. Bổ sung kiểm thử quyền ở mức đối tượng

Rule route `hasRole("ANALYST")` chỉ kiểm tra quyền của role ở endpoint. Nếu URL là `GET /api/reports/{id}` và người đọc chỉ được xem báo cáo **của tenant mình**, cần thêm kiểm tra record-level authorization. Hai user cùng có `ROLE_ANALYST` vẫn có thể có quyền khác nhau trên một `reportId`.

Ma trận mở rộng:

| Principal | Tài nguyên | Kỳ vọng |
| --- | --- | --- |
| Alice (ANALYST của tenant-A) | Báo cáo thuộc tenant-A, được cấp phép | 200, chỉ dữ liệu tenant-A |
| Alice | Báo cáo thuộc tenant-B | 403 hoặc 404 theo chính sách che tồn tại |
| Bob (ANALYST của tenant-B) | Báo cáo thuộc tenant-B | 200 |
| Viewer tenant-A | Báo cáo của tenant-A nhưng thiếu role cần thiết | 403 |
| Anonymous | Bất kỳ báo cáo bảo vệ nào | 401 với Basic |
| Admin | Báo cáo tenant khác | Phụ thuộc quyền cross-tenant **được định nghĩa rõ**, không mặc định global admin có mọi quyền |

Kiểm thử cần tạo các fixture có owner/tenant rõ ràng, gọi cùng endpoint với các user khác nhau, assert dữ liệu thật hoặc không lộ thông tin bị cấm. Cấu hình `@PreAuthorize`, custom `AuthorizationManager` hay kiểm tra trong service đều có thể bảo vệ object-level, miễn mọi đường gọi dùng chung chính sách và kiểm thử đúng vị trí ra quyết định. Nếu cần 404 cho đối tượng người dùng không được biết tồn tại, hãy kiểm tra quy tắc này nhất quán, kể cả search/list/export, lỗi và timing. Không được coi một `200` có body đã mask là thay thế hợp lệ cho việc **từ chối toàn bộ đối tượng**.

## 10. Cẩn thận khi dùng @WithMockUser, user() và test slice

| Công cụ | Tạo gì? | Phù hợp để kiểm tra | Giới hạn |
| --- | --- | --- | --- |
| `.with(httpBasic("u", "p"))` | Header HTTP Basic | Credentials đi qua Basic authentication filter + rules | Không kiểm tra HTTPS/proxy/network |
| `@WithMockUser(roles = "ANALYST")` | SecurityContext giả với role | Quy tắc authorization ở method/HTTP | Không chứng minh password/token được xác thực |
| `.with(user("u").roles("ANALYST"))` | Principal giả trên request | Từng kịch bản role tại một request | Không xác thực credential thực |
| `.with(anonymous())` | Principal anonymous giả | Test anonymous khi suite có default user | Không phải request không có mọi header thực |
| `.with(csrf())` | CSRF token hợp lệ trong test | POST/PUT/PATCH/DELETE có CSRF | Không thực hiện quy trình phát token/cookie của trình duyệt |
| `.with(csrf().useInvalidToken())` | CSRF token không hợp lệ | Nhánh từ chối CSRF | Không chứng minh browser thực thi bảo vệ same-site |

`@WithMockUser` có thể là lựa chọn tốt cho test method security:

~~~java
// Snippet minh họa, yêu cầu @EnableMethodSecurity,
// bean được Spring quản lý và @PreAuthorize trong ứng dụng.
@WithMockUser(roles = "ANALYST")
@Test
void analystCanCallSecuredService() {
    assertEquals("ok", securedService.readReport());
}
~~~

Nhưng nếu hệ thống dùng LDAP, SSO, Bearer JWT hay password encoder riêng, cần thêm một số test đi qua cơ chế authentication thật. Một unit test với `user()` không phát hiện bug cấu hình filter, decoder hoặc credential store.

Đối với `@WebMvcTest`: chỉ test một lát cắt MVC, thường nhanh nhưng phải đảm bảo import chain và cấu hình/bean cần thiết. Nếu test trả 403 bất ngờ vì SecurityFilterChain mặc định khác production, đừng vội sửa expected status; hãy xác định chain thật đang được nạp. Bộ `@SpringBootTest + @AutoConfigureMockMvc` trong ví dụ được chọn để giữ cấu hình xác thực/phân quyền sát ứng dụng hơn.

## 11. Kiểm thử theo HTTP method, matcher và filter chain

**Matcher order:** `authorizeHttpRequests` xử lý các quy tắc theo thứ tự, thông thường rule khớp đầu tiên quyết định. Nếu đặt `anyRequest().permitAll()` trước `hasRole`, ứng dụng hoặc sẽ lỗi cấu hình hoặc bỏ qua mục tiêu bảo vệ dự kiến. Test phải gọi URL và method thật, bao gồm các path động, URL encoding và đường dẫn gần giống nhau.

**GET/POST không tương đương:** `GET /api/admin/publish` và `POST /api/admin/publish` khác hẳn, vì security rule của ví dụ dùng `HttpMethod.POST`. Đừng cho rằng một test GET đã chứng minh endpoint POST được bảo vệ. Với ứng dụng có `PATCH`, `PUT`, `DELETE`, tạo test tương ứng và kiểm tra CSRF theo cơ chế client.

**Nhiều SecurityFilterChain:** request thuộc chain nào được lựa chọn theo `securityMatcher` và thứ tự chain. API dùng HTTP Basic hoặc Bearer có thể cần 401; trang web dùng `formLogin` thường có 302. Phải test cả URI đúng chain lẫn boundary `/api/**`, `/admin/**`, đường public và các phương thức không khớp. Nếu một route rơi vào chain rộng hơn, kỳ vọng bảo mật có thể khác hoàn toàn.

**Method security:** `@PreAuthorize` cần `@EnableMethodSecurity` và method được gọi qua proxy phù hợp. HTTP filter cho phép request chưa đảm bảo method tương ứng cũng cho phép; test phải quan sát kết quả thực tế và exception translation. Nếu controller gọi service qua self-invocation làm bypass proxy, test chỉ dựa vào annotation có thể bỏ sót.

**CSRF:** mặc định cho unsafe methods trong Servlet; test role phải kèm token hợp lệ nếu sản phẩm dùng CSRF. Không vô hiệu hóa CSRF chỉ để một test POST dễ chạy, trừ khi kiến trúc và threat model của ứng dụng đã quyết định rõ không cần CSRF cho client/cơ chế xác thực ấy.

**Dispatcher và errors:** `FORWARD`/`ERROR` dispatch, static resources và error controller có thể chịu rule riêng. Lỗi 403 thứ cấp có thể che giấu lỗi gốc. Với error handling chuyên biệt, thêm test cho đường lỗi và bảo đảm route cho lỗi không làm lộ dữ liệu hoặc vô tình mở quyền.

## 12. Cách xác định nguyên nhân khi test thất bại

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Anonymous nhận 200 ở endpoint bảo vệ | Filter chain có được bật cho MockMvc không? Route có `permitAll` hay matcher sai không? |
| Anonymous nhận 302 thay vì 401 | Có `formLogin`/redirect entry point không? Test có đi vào chain của trang web không? |
| User đúng password nhưng nhận 401 | Credential store, password encoder, username, header Basic, session/token, SecurityContext |
| User có quyền nhưng nhận 403 với GET | Authority có prefix `ROLE_`? Matcher đúng HTTP method/path? Rule áp dụng ở method/object-level? |
| Admin POST nhận 403 | CSRF token, auth role, HTTP method, content type, AccessDeniedHandler |
| Viewer nhận 401 thay vì 403 | Credential có hợp lệ không? Authentication có bị mất? User có đang anonymous? |
| `@WithMockUser` pass nhưng HTTP Basic fail | Test giả lập user đã bỏ qua xác thực thật; kiểm tra Basic filter và UserDetailsService |
| `@WebMvcTest` không load rule mong muốn | Kiểm tra `@Import` SecurityFilterChain, test slice, bean dependencies, auto configuration |
| 403 nhưng nghiệp vụ vẫn bị thực hiện | Kiểm tra side effect trước authorization, async task, thứ tự filter, method proxy và transaction |
| Test pass nhưng production khác | Proxy/CORS, session cookies, chain order, forwarded headers, tenant context, external identity provider |

Cần tránh “sửa” bằng cách đổi `401` thành `403` hoặc thêm `@WithMockUser` mà chưa hiểu nguyên nhân. Hãy đọc log Spring Security ở mức DEBUG trong môi trường phát triển để biết filter chain nào đang xử lý, principal đã xác thực ra sao và decision point nào trả về denial. Không bật logging credentials hoặc token thô vào môi trường vận hành.

Nếu test chỉ thất bại khi chạy cả suite, xem xét test isolation: `SecurityContextHolder` hoặc static state bị rò giữa test, random order, mutable in-memory grants, cache hoặc mock bean dùng lại. Mỗi test nên tự thiết lập principal, dữ liệu và CSRF; không dựa vào một test khác đã chạy trước.

## 13. Kế hoạch kiểm thử cho API có quyền quan trọng

Một ma trận nhỏ và có ý nghĩa thường đủ hơn một tập test lớn chỉ khẳng định 200:

1. **Public**: anonymous truy cập được đúng những route công khai, không đi vòng qua route nhạy cảm.
2. **Protected + anonymous**: không được thấy dữ liệu; response theo cơ chế xác thực (401/challenge hoặc redirect đúng).
3. **Protected + đủ quyền**: response đúng status, body, tenant/resource; side effect chỉ xảy ra khi được phép.
4. **Protected + thiếu quyền**: credentials hợp lệ nhưng role/scope/owner không đủ; status 403/404 theo policy và không lộ thông tin.
5. **Credential lỗi**: wrong password, expired/revoked token hoặc invalid signature được xử lý ở authentication boundary.
6. **HTTP mutation**: CSRF valid/invalid/missing theo cơ chế đang dùng; thiếu quyền không gây side effect.
7. **Thay đổi permission**: thu hồi quyền có hiệu lực đúng theo phiên bản quyền/token cache, test không giả định claims cập nhật ngay nếu token cũ còn sống.
8. **Error/data leak**: error response không trả dữ liệu nhạy cảm hoặc stack trace; authn/authz audit ghi đúng event khi cần.
9. **Boundary**: route ít quyền và nhiều quyền, GET/POST, nhiều filter chain, path mismatch, parameter/object/tenant.
10. **Regression**: test fail khi thay rule từ `hasRole` thành `permitAll` hoặc đổi thứ tự matcher, nhờ có cả positive và negative cases.

### Checklist trước khi kết thúc bài

- [ ] Phân biệt được **chưa xác thực**, **xác thực đúng và đủ quyền**, **xác thực đúng nhưng thiếu quyền**.
- [ ] Viết được test MockMvc đi qua SecurityFilterChain thực và khẳng định response status.
- [ ] Kiểm chứng Basic challenge cho 401 trong cấu hình Basic; hiểu 302/401/403 phụ thuộc entry point và handler.
- [ ] Kiểm tra đúng username/password cho nhánh authentication và đúng roles/authorities cho authorization.
- [ ] Khẳng định cả dữ liệu thành công và absence/không side effect trong nhánh bị từ chối.
- [ ] Với POST, phân biệt từ chối do CSRF với từ chối do thiếu role bằng cách tạo token hợp lệ trong test quyền.
- [ ] Không lấy `@WithMockUser` làm bằng chứng mật khẩu hoặc token đã được xác thực thật.
- [ ] Mở rộng ma trận cho owner, tenant, method-level, nhiều chain và các đường export/error khi sản phẩm cần.
- [ ] Đảm bảo test độc lập, không ghi lộ password/token ra log, và không đổi chính sách bảo mật chỉ để test pass.

### Tài liệu tham khảo chính thức

- Spring Security — Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Security — MockMvc Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
