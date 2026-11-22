# user(), anonymous() và cấu hình role, authority cho request trong kiểm thử HTTP

> Bối cảnh: **Spring Security authorization**, kiểm thử **Servlet HTTP** bằng **Spring MVC Test (MockMvc)** với **Spring Security Test**. Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x. API WebFlux dùng WebTestClient và bộ công cụ kiểm thử khác.

## 1. Mục tiêu của bài

Khi viết test HTTP cho endpoint đã bảo vệ bằng Spring Security, chỉ gọi `mockMvc.perform(get("/api/report"))` là chưa đủ để kiểm tra mọi nhánh quyền. Cần chủ động tạo **danh tính gắn với từng request** và xác nhận policy trả kết quả đúng.

Sau bài này bạn có thể:

1. Sử dụng `user("alice")` để tạo mock authenticated user trên **một request MockMvc**, và `anonymous()` để mô phỏng truy cập anonymous.
2. Phân biệt `roles("ADMIN")` với `authorities(new SimpleGrantedAuthority("..."))` và hiểu tiền tố `ROLE_`.
3. Phối hợp `@SpringBootTest`/`@AutoConfigureMockMvc` hoặc `springSecurity()` để Spring Security thật sự chạy trong MockMvc.
4. Viết các bài kiểm thử `permitAll()`, `authenticated()`, `hasRole()`, `hasAuthority()` với user khác quyền; kiểm tra HTTP 200, 401 và 403 theo cấu hình API.
5. Tránh nhầm lỗi thiếu CSRF token với lỗi thiếu role/authority khi kiểm thử POST/PUT/PATCH/DELETE.
6. Phân biệt **mô phỏng authentication cho authorization test** với **kiểm thử luồng đăng nhập, giải mã JWT hoặc tải UserDetails thật**.

## 2. Hai RequestPostProcessor cốt lõi

Spring Security Test cung cấp các hàm tĩnh trong `SecurityMockMvcRequestPostProcessors`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
~~~

Các request mẫu:

~~~java
// Alice được coi là authenticated, mặc định có authority ROLE_USER.
mockMvc.perform(get("/api/me").with(user("alice")));

// Bob có hai role -> ROLE_USER và ROLE_ADMIN.
mockMvc.perform(get("/api/admin")
    .with(user("bob").roles("USER", "ADMIN")));

// Request mô phỏng anonymous, không phải authenticated user bình thường.
mockMvc.perform(get("/api/public").with(anonymous()));
~~~

Các đoạn trên chỉ là **lệnh bên trong test method**, không phải class Java độc lập. Chúng không đòi hỏi account `alice`/`bob` tồn tại trong database và không thực hiện kiểm tra password. Có thể sử dụng `user(userDetails)` khi cần chủ động cung cấp một `UserDetails` đã tạo cho test.

**Ý nghĩa quan trọng:** `user()` thiết lập mock `Authentication` trên request để **bộ lọc và quyết định phân quyền của ứng dụng** có thể đánh giá như có người dùng đã đăng nhập. Đây không phải bằng chứng luồng login ngoài đời thật đang hoạt động.

### 2.1 user("name") cho request

Với `.with(user("alice"))`, Spring Security Test tạo user tên `alice`. Mặc định có password thử nghiệm và role `USER`, tương ứng GrantedAuthority `ROLE_USER`. Có thể thay đổi:

~~~java
mockMvc.perform(get("/api/admin")
    .with(user("alice")
        .password("unused-password")
        .roles("ADMIN")));
~~~

Giá trị `password("unused-password")` ở đây chỉ là **thuộc tính của mock principal**, không được đưa qua AuthenticationProvider để kiểm tra mật khẩu. Đừng viết test xác thực mật khẩu bằng `user().password(...)`.

Hàm `roles("ADMIN")` tự tạo `ROLE_ADMIN`; không truyền `roles("ROLE_ADMIN")` vì giá trị `roles(...)` đã có tiền tố sẽ bị từ chối trong builder mặc định.

### 2.2 anonymous() cho request

~~~java
mockMvc.perform(get("/api/public")
        .with(anonymous()))
    .andExpect(status().isOk());
~~~

`anonymous()` mô phỏng security context của anonymous user. Về kỹ thuật Spring Security có thể dùng `AnonymousAuthenticationToken` với authority như `ROLE_ANONYMOUS`, nhưng rule `authenticated()` **không coi anonymous là authenticated thật**. Đây không phải thao tác “đăng xuất” của trình duyệt; nó thiết lập bối cảnh cho **request được kiểm thử**.

`anonymous()` đặc biệt hữu ích nếu test class đang có `@WithMockUser` hoặc MockMvc được cấu hình defaultRequest có mock user: bạn vẫn có thể kiểm tra nhánh không đăng nhập cho một request cụ thể.

### 2.3 RequestPostProcessor thuộc về request, không phải session đăng nhập thật

Một lời gọi `perform(...)` được dựng lại riêng. Khi muốn so sánh nhiều identity, truyền `.with(user(...))` ở **mỗi request cần kiểm thử**. Đừng giả định lệnh trước đã đăng nhập cho tất cả request tiếp theo.

Nếu muốn test user được duy trì bằng cookie/session giữa nhiều request, hoặc test Basic/Bearer authentication thực, cần tạo và truyền state tương ứng trong test. `user()` không thay thế việc kiểm tra session persistence, JWT signature/claim conversion hoặc authentication provider.

## 3. Roles và authorities: cú pháp giống nhau nhưng ý nghĩa khác

Spring Security cuối cùng đánh giá các phần tử `GrantedAuthority` trên `Authentication`. “Role” là một **quy ước đặt tên authority** (mặc định bắt đầu bằng `ROLE_`).

| Cách tạo mock user | GrantedAuthority trong request | Matcher điển hình | Kết quả |
| --- | --- | --- | --- |
| `user("a")` | `ROLE_USER` | `hasRole("USER")` | Cho phép |
| `user("a").roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho phép |
| `user("a").roles("ADMIN")` | `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Cho phép |
| `user("a").authorities(new SimpleGrantedAuthority("ADMIN"))` | `ADMIN` | `hasRole("ADMIN")` | Từ chối theo prefix mặc định |
| `user("a").authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho phép |
| `user("a").authorities(new SimpleGrantedAuthority("reports:export"))` | `reports:export` | `hasAuthority("reports:export")` | Cho phép |
| `user("a").roles("ADMIN")` | `ROLE_ADMIN` | `hasAuthority("reports:export")` | Từ chối nếu không có authority đó |

Quy tắc:

- `hasRole("ADMIN")` mặc định tìm authority `ROLE_ADMIN`; `roles("ADMIN")` trên test user tạo authority theo cùng quy ước.
- `hasAuthority("reports:export")` kiểm tra **chuỗi chính xác**; không thêm `ROLE_`.
- `hasAnyRole("ADMIN", "AUDITOR")` và `hasAnyAuthority("reports:read", "reports:export")` cũng tuân theo cơ chế tương ứng.
- `roles(...)` phù hợp role cấp cao; `authorities(...)` hữu ích cho permission/scope chi tiết hoặc khi muốn cung cấp authority đúng tên.
- `roles("ADMIN")` và `authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` có thể tạo cùng dữ liệu GrantedAuthority, nhưng cách biểu đạt trong test khác nhau.
- Chọn một trong `roles(...)` hoặc `authorities(...)` trên cùng builder theo ý định. Không tùy tiện chain cả hai và giả định chúng **cộng dồn**; kiểm tra overload/builder đang dùng nếu cần tập authority kết hợp.

Ví dụ đưa một authority cụ thể vào request:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/exports")
    .with(user("alice").authorities(
        new SimpleGrantedAuthority("reports:export")
    )));
~~~

Nếu có custom role prefix qua cấu hình security, role hierarchy, `GrantedAuthorityDefaults` hoặc converter JWT của ứng dụng, **test phải tái hiện chính xác các GrantedAuthority sau khi mapping**. Đặc biệt, một scope OAuth2/JWT có thể được map thành `SCOPE_reports.read`; test `hasAuthority("SCOPE_reports.read")` phải cấp đúng chuỗi đó. Dùng `roles("ADMIN")` để “thay” `SCOPE_reports.read` sẽ không chứng minh quyền tương đương.

## 4. Thiết lập MockMvc đúng cách để security được thực thi

Cần dependency kiểm thử của Spring Security. Với Gradle Groovy DSL trong ứng dụng Spring Boot 3.x:

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

Spring Boot dependency management/BOM nên quản lý phiên bản đồng bộ; không ghép `spring-security-test` khác major với `spring-security-core` của ứng dụng.

Hai cách thường gặp:

**Cách A — Integration test HTTP với Spring Boot:**

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityHttpTests {
    @Autowired MockMvc mockMvc;
    // @Test ...
}
~~~

Trong Spring Boot Test tiêu chuẩn, `@AutoConfigureMockMvc` tự cấu hình MockMvc và đăng ký các filter của application context theo mặc định. Từ đó `.with(user(...))`, `.with(anonymous())` và các rule ở `SecurityFilterChain` được xử lý trong request thực thi qua MockMvc.

**Cách B — Tự tạo MockMvc từ WebApplicationContext:**

~~~java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

`springSecurity()` thêm tích hợp Spring Security Test, các filter và cơ chế kết nối SecurityContext thích hợp với MockMvc. Nếu dùng `MockMvcBuilders.standaloneSetup(controller)` mà quên gắn filter/security config, test có thể trả `200` cho endpoint đáng lẽ bị chặn: nó chỉ đang kiểm tra controller, **chưa kiểm tra security thực sự**.

**Kiểm tra hữu ích:** luôn có ít nhất một negative test `anonymous()` với endpoint yêu cầu authentication và một test user thiếu authority. Nếu cả hai vẫn được `200`, kiểm tra `FilterChainProxy`, securityMatcher, test slice và rule.

## 5. Ví dụ hoàn chỉnh bằng Spring Boot: API và chính sách HTTP

Giả sử API có các route:

| Endpoint | Chính sách |
| --- | --- |
| `GET /api/public` | `permitAll()` |
| `GET /api/profile` | `authenticated()` |
| `GET /api/reports` | `hasRole("REPORTER")` |
| `POST /api/reports` | `hasRole("REPORTER")` **và** CSRF hợp lệ |
| `GET /api/exports` | `hasAuthority("reports:export")` |
| Mọi route khác | `denyAll()` |

Để chạy ví dụ, tạo project Spring Boot có dependency mục 4, package `example.requestsecurity` và các file tương ứng dưới `src/main/java/example/requestsecurity/`.

### 5.1 RequestSecurityApplication.java

~~~java
package example.requestsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestSecurityApplication.class, args);
    }
}
~~~

### 5.2 SecurityConfig.java

~~~java
package example.requestsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasRole("REPORTER")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("REPORTER")
                .requestMatchers(HttpMethod.GET, "/api/exports")
                    .hasAuthority("reports:export")
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

Các điểm cần hiểu:

- Rule được xét **theo thứ tự khớp đầu tiên**; luôn đặt rule cụ thể trước `anyRequest().denyAll()`.
- Cấu hình `httpBasic()` + tắt form login tạo hành vi REST HTTP rõ ràng: request anonymous vào route được bảo vệ thường nhận `401`, user mock đã xác thực nhưng thiếu quyền thường nhận `403`.
- `csrf(Customizer.withDefaults())` giữ bảo vệ POST. Một POST thiếu CSRF token có thể trả `403` **trước khi** chạm controller hoặc đánh giá rule về role.
- Đây là cấu hình **HTTP security**. Nó không mô phỏng database user store, JWT converter, role hierarchy hoặc authorization theo đối tượng trong service.
- Với endpoint public, `permitAll()` cho phép cả request anonymous; với `authenticated()`, mọi identity mock đã xác thực đủ đều qua, dù không có role cụ thể.

### 5.3 DemoApiController.java

~~~java
package example.requestsecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoApiController {

    @GetMapping("/api/public")
    public String publicPage() {
        return "public-ok";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "profile-ok";
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "reports-ok";
    }

    @PostMapping("/api/reports")
    public String createReport() {
        return "created-ok";
    }

    @GetMapping("/api/exports")
    public String exports() {
        return "exports-ok";
    }
}
~~~

Controller không tự đọc role trong body hay header. Quy tắc trên URL áp dụng trước khi controller chạy. Khi cần kiểm tra quyền sở hữu resource hoặc tenant, bổ sung policy service/method security thay vì suy từ `ROLE_REPORTER` rằng user được xem mọi báo cáo.

## 6. Bộ kiểm thử MockMvc đầy đủ: thay identity trên từng request

Tạo file `src/test/java/example/requestsecurity/RequestSecurityApplicationTests.java`:

~~~java
package example.requestsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestSecurityApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCanReadPublicEndpoint() throws Exception {
        mockMvc.perform(get("/api/public").with(anonymous()))
            .andExpect(status().isOk())
            .andExpect(content().string("public-ok"));
    }

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mockMvc.perform(get("/api/profile").with(anonymous()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void defaultUserIsAuthenticated() throws Exception {
        // user("alice") có ROLE_USER theo mặc định.
        mockMvc.perform(get("/api/profile").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile-ok"));
    }

    @Test
    void userWithDefaultRoleCannotReadReports() throws Exception {
        mockMvc.perform(get("/api/reports").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reporterRoleCanReadReports() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(user("alice").roles("REPORTER")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports-ok"));
    }

    @Test
    void bareReporterAuthorityIsNotRoleReporter() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORTER"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void prefixedAuthorityMatchesHasRole() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ROLE_REPORTER"))))
            .andExpect(status().isOk());
    }

    @Test
    void reporterRoleAloneCannotExport() throws Exception {
        mockMvc.perform(get("/api/exports")
                .with(user("alice").roles("REPORTER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void exactExportAuthorityAllowsExport() throws Exception {
        mockMvc.perform(get("/api/exports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("reports:export"))))
            .andExpect(status().isOk())
            .andExpect(content().string("exports-ok"));
    }

    @Test
    void reporterPostWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/api/reports")
                .with(user("alice").roles("REPORTER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reporterPostWithCsrfCanCreate() throws Exception {
        mockMvc.perform(post("/api/reports")
                .with(user("alice").roles("REPORTER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created-ok"));
    }

    @Test
    void anonymousPostWithCsrfStillRequiresLogin() throws Exception {
        mockMvc.perform(post("/api/reports")
                .with(anonymous())
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "mai", roles = "REPORTER")
    void annotationAlsoSuppliesAuthenticatedRole() throws Exception {
        mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
    }
}
~~~

Chạy trong root của **project Spring Boot demo vừa tạo**:

~~~bash
./gradlew test
~~~

Hoặc dùng `gradlew.bat test` trên Windows. Khi các file được tạo đúng package, có dependency và Gradle Java toolchain tương thích, các test trên được thiết kế để pass. Chúng dựa vào cấu hình `SecurityConfig` và endpoint cụ thể trong bài; không thể dùng `javac RequestSecurityApplicationTests.java` thuần vì cần Spring Boot, Spring Test và JUnit trên classpath.

### 6.1 Ma trận kết quả

| Identity thử nghiệm | Request | Expected status | Diễn giải |
| --- | --- | --- | --- |
| `anonymous()` | GET `/api/public` | `200` | `permitAll()` |
| `anonymous()` | GET `/api/profile` | `401` | Cần authentication; demo dùng HTTP Basic |
| `user("alice")` | GET `/api/profile` | `200` | Mặc định đã authenticated |
| `user("alice")` | GET `/api/reports` | `403` | Chỉ có `ROLE_USER` |
| `user("alice").roles("REPORTER")` | GET `/api/reports` | `200` | Có `ROLE_REPORTER` |
| Authority `REPORTER` | GET `/api/reports` | `403` | Thiếu tiền tố `ROLE_` |
| Authority `ROLE_REPORTER` | GET `/api/reports` | `200` | Khớp `hasRole("REPORTER")` |
| Chỉ có `ROLE_REPORTER` | GET `/api/exports` | `403` | Thiếu `reports:export` |
| Authority `reports:export` | GET `/api/exports` | `200` | Khớp chính xác `hasAuthority(...)` |
| `ROLE_REPORTER`, thiếu CSRF | POST `/api/reports` | `403` | CSRF filter từ chối |
| `ROLE_REPORTER`, CSRF hợp lệ | POST `/api/reports` | `200` | Vượt cả CSRF và role |
| `anonymous()`, CSRF hợp lệ | POST `/api/reports` | `401` | CSRF không thay thế đăng nhập |

Các HTTP status kỳ vọng phụ thuộc **chính xác SecurityFilterChain trong ví dụ**. Với ứng dụng có form login, entry point tùy chỉnh, JWT resource server hoặc redirect, anonymous có thể thấy kết quả khác. Hãy assert theo hợp đồng API thực tế.

### 6.2 Lý do cần cả positive và negative test

Test chỉ xác nhận user được phép vào route không bắt được lỗi policy vô tình chuyển thành `permitAll()`. Với mỗi rule, ít nhất cần:

- Trường hợp hợp lệ: user sở hữu đúng role/authority → được phép.
- Trường hợp thiếu quyền: authenticated user khác role/authority → bị từ chối.
- Trường hợp anonymous: không đăng nhập → bị từ chối nếu route cần authentication.
- Với unsafe HTTP method: CSRF token hợp lệ để cô lập quyết định authorization.

Riêng `authenticated()` không có nghĩa `hasRole("USER")`: một principal hợp lệ có authority `reports:export` nhưng không có `ROLE_USER` vẫn có thể thỏa `authenticated()`. Test phải khớp rule thực sự.

## 7. Cấu hình nhiều role, nhiều permission và custom UserDetails

### 7.1 Một user có nhiều roles

~~~java
mockMvc.perform(get("/api/reports")
        .with(user("mai").roles("REPORTER", "ADMIN")))
    .andExpect(status().isOk());
~~~

Danh sách role ở builder có nghĩa `ROLE_REPORTER` và `ROLE_ADMIN`. Nếu cần gán chính xác hỗn hợp `ROLE_REPORTER` **và** `reports:export`, dùng `authorities(...)`:

~~~java
mockMvc.perform(get("/api/exports")
    .with(user("mai").authorities(
        new SimpleGrantedAuthority("ROLE_REPORTER"),
        new SimpleGrantedAuthority("reports:export")
    )));
~~~

Với kiểm thử role-prefix, cần nhớ `authorities(...)` không tự thêm `ROLE_`. Đây là điểm test giả dễ sai nhất khi dữ liệu thực lấy từ roles DB, JWT scopes hoặc custom GrantedAuthoritiesMapper.

### 7.2 Gắn một UserDetails tự tạo

Nếu ứng dụng cần `UserDetails` custom có các thuộc tính khác username, dùng overload `user(userDetails)`. Ví dụ về mặt cấu trúc:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

UserDetails details = User.withUsername("test-user")
    .password("{noop}unused")
    .authorities("ROLE_REPORTER", "reports:export")
    .build();

mockMvc.perform(get("/api/exports").with(user(details)))
    .andExpect(status().isOk());
~~~

Đây là đoạn code **bên trong test method**; cần các import của test file tương ứng. Password đặt trong đối tượng test không được kiểm tra ở request này. `user(details)` sử dụng đối tượng do test đưa vào; nó **không xác minh UserDetailsService đã tải đúng tài khoản**. Để kiểm thử tải tài khoản từ DB và đăng nhập thật, thực hiện flow authentication riêng.

### 7.3 Phân biệt với @WithMockUser

Annotation `@WithMockUser` hữu ích nếu cả một method/class dùng cùng identity:

~~~java
@Test
@WithMockUser(username = "mai", roles = "REPORTER")
void reportIsAllowed() throws Exception {
    mockMvc.perform(get("/api/reports"))
        .andExpect(status().isOk());
}
~~~

Nó cung cấp SecurityContext cho phạm vi test tương ứng, còn `.with(user("..."))` rõ ràng hơn khi **mỗi request trong một test có identity khác nhau**. Với test class áp dụng `@WithMockUser` mặc định, dùng `.with(anonymous())` cho request muốn chủ động mô phỏng anonymous; hoặc dùng `@WithAnonymousUser` nếu cả method cần anonymous.

Không dùng `@WithMockUser` để chứng minh password đúng, xác thực OIDC login thành công, hoặc JWT signature/claim mapping. Cần integration test của authentication mechanism thật cho các mục tiêu đó.

## 8. Cài identity mặc định cho MockMvc và chủ động override

Khi nhiều test dùng cùng role, có thể dùng default request processor:

~~~java
// Đặt trong @BeforeEach hoặc phương thức thiết lập MockMvc.
mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .defaultRequest(get("/").with(user("tester").roles("REPORTER")))
    .apply(springSecurity())
    .build();
~~~

Test có thể gọi:

~~~java
// Từ defaultRequest: tester có ROLE_REPORTER.
mockMvc.perform(get("/api/reports"))
    .andExpect(status().isOk());

// Request này chủ động thay identity bằng anonymous.
mockMvc.perform(get("/api/reports").with(anonymous()))
    .andExpect(status().isUnauthorized());
~~~

Cần import `MockMvcBuilders`, `WebApplicationContext` và `SecurityMockMvcConfigurers.springSecurity` trong class thiết lập. Khi dùng `@AutoConfigureMockMvc` và `@Autowired MockMvc`, thường không cần tự dựng lại; lựa chọn defaultRequest là ví dụ thay thế cho trường hợp chủ đích cần fixture chung.

**Bẫy thường gặp:** cấu hình default user `ADMIN` rồi quên test negative path. Khi một testcase bất ngờ pass với 200, hãy kiểm tra danh tính mặc định của MockMvc, `@WithMockUser` trên class và `RequestPostProcessor` trên request.

## 9. Tương tác với CSRF: lý do POST dễ tạo kết luận sai

Trong Spring Security Servlet thông thường, CSRF bảo vệ các phương thức unsafe (như POST/PUT/PATCH/DELETE) nếu bật tính năng này. `user("reporter").roles("REPORTER")` **không tự gắn CSRF token**.

Ba request cùng route nhưng ý nghĩa khác nhau:

~~~java
// Có quyền REPORTER nhưng thiếu token: CSRF có thể chặn sớm (403).
mockMvc.perform(post("/api/reports")
        .with(user("reporter").roles("REPORTER")))
    .andExpect(status().isForbidden());

// Có quyền REPORTER và token hợp lệ: được thực hiện (200).
mockMvc.perform(post("/api/reports")
        .with(user("reporter").roles("REPORTER"))
        .with(csrf()))
    .andExpect(status().isOk());

// Không có quyền REPORTER nhưng có token hợp lệ: authorization từ chối (403).
mockMvc.perform(post("/api/reports")
        .with(user("reader").roles("USER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

Test `403` thứ nhất **không chứng minh rule hasRole đang hoạt động**: lỗi có thể hoàn toàn do `CsrfFilter`. Khi mục tiêu là kiểm tra authorization của POST, truyền `.with(csrf())` để qua lớp CSRF trước rồi mới xem kết quả role/authority.

Có thể dùng `csrf().asHeader()` hoặc `csrf().useInvalidToken()` khi muốn kiểm tra bảo vệ CSRF riêng. Không tắt toàn bộ CSRF chỉ để cho test POST chạy nếu ứng dụng thực sử dụng cookie/session và cần cơ chế bảo vệ đó. Nếu API thật sự dùng bearer token tự gửi và quyết định vô hiệu CSRF theo threat model đã xác minh, test phải phản ánh **đúng cấu hình production**, không suy đoán từ chữ “REST”.

## 10. Test user() có chứng minh authentication thật không?

**Không.** Có hai bài toán khác nhau:

| Mục tiêu kiểm thử | Công cụ phù hợp | Điều được kiểm chứng |
| --- | --- | --- |
| Authorization cho user đã xác thực | `.with(user("alice").roles(...))` | HTTP filter, rule role/authority, handler |
| Authorization khi anonymous | `.with(anonymous())` | Endpoint public/private, entry point |
| Kiểm thử HTTP Basic thật | Request có HTTP Basic credentials, UserDetailsService/AuthenticationProvider thật hoặc test-specific | Cơ chế xác thực, mật khẩu, dữ liệu account |
| Kiểm thử JWT Bearer | Request có token, decoder/converter và resource-server config | Signature/claims/expiry/authority mapping theo cấu hình test |
| Kiểm thử session login | POST login, cookie/session và request tiếp theo | Filter đăng nhập, session handling |
| Kiểm thử user có quyền trên object | Mock identity + permission/tenant policy trong service | Quyền trên tài nguyên cụ thể, không chỉ URL |

Ví dụ test HTTP Basic (chỉ minh họa, cần tài khoản test đã được cấu hình trong UserDetailsService):

~~~java
mockMvc.perform(get("/api/reports")
        .with(httpBasic("reporter", "actual-test-password")))
    .andExpect(status().isOk());
~~~

Cần static import `SecurityMockMvcRequestPostProcessors.httpBasic` và cấu hình `reporter`, password encoder, role tương ứng. Trong ví dụ hoàn chỉnh ở mục 5 không cung cấp UserDetailsService cho user `reporter`, nên **không được xem đoạn test Basic này là test runnable của demo trước**.

Ví dụ với JWT cũng phải phân biệt `jwt()` của Spring Security Test (mock token/authorities cho kiểm thử authorization) với HTTP request mang bearer JWT thật được decode và validate. Cả hai hữu ích, nhưng chúng xác minh các bước khác nhau.

## 11. Khi kiểm thử role hierarchy, scopes và authorization tùy biến

Các hệ thống thực thường nâng cao hơn `hasRole("ADMIN")` đơn lẻ:

- **Role hierarchy:** `ADMIN > MANAGER > USER` có thể cho phép `ADMIN` thỏa `hasRole("USER")`. Tính đúng phụ thuộc việc hierarchy đã được gắn vào authorization engine; test phải nạp cấu hình hierarchy thực, không tự cộng ROLE_USER vào principal rồi kết luận hierarchy chạy đúng.
- **Custom role prefix:** mặc định Spring Security so khớp `ROLE_`; một số tầng cấu hình có thể đổi cách diễn giải role. Kiểm tra authority string mà authorization manager thực sự nhìn thấy.
- **Scopes JWT:** nhiều resource server map `scope`/`scp` sang `SCOPE_x`. `user().authorities("SCOPE_x")` (với overload thích hợp) hoặc `new SimpleGrantedAuthority("SCOPE_x")` kiểm tra **matcher**, không kiểm tra JWT converter.
- **Permission theo tenant/object:** `hasAuthority("invoice:approve")` mới bảo đảm có permission tĩnh. User có thể có permission này nhưng không được duyệt invoice của tenant khác; cần kiểm thử domain policy/method security với dữ liệu resource.
- **Multiple SecurityFilterChain:** nếu test route khớp chain khác với dự kiến, bạn có thể thấy 401/403/200 ngoài ma trận. Kiểm tra `securityMatcher`, thứ tự chain và authorization rule.
- **Method security:** nếu handler/service có `@PreAuthorize`, cần bật `@EnableMethodSecurity` và test chạy qua Spring proxy. Việc gọi trực tiếp đối tượng tự `new` sẽ không chứng minh interceptor hoạt động.

Cách giảm false-positive: định nghĩa ma trận **route × method × principal × authorities × CSRF state** với cả positive/negative cases, sau đó assert kết quả và khi quan trọng, assert side-effect/service invocation tương ứng.

## 12. Checklist khắc phục lỗi MockMvc

| Triệu chứng | Khả năng thường gặp | Cách xác nhận/sửa |
| --- | --- | --- |
| Anonymous truy cập route protected vẫn 200 | Security filter chain chưa gắn vào MockMvc hoặc route bị `permitAll` | Kiểm tra `@AutoConfigureMockMvc`/`springSecurity()`, requestMatchers |
| `user("admin").roles("ADMIN")` vẫn 403 | Rule cần authority khác, CSRF thiếu, chain khác hoặc method security deny | Đọc chính xác rule và method, tách test GET/POST |
| `authorities("ADMIN")` bị 403 với `hasRole("ADMIN")` | Authority thiếu `ROLE_` | Dùng `roles("ADMIN")` hoặc authority `ROLE_ADMIN` |
| `roles("ROLE_ADMIN")` lỗi ngay khi tạo user | Builder đã thêm prefix tự động | Truyền `roles("ADMIN")` |
| POST có role đúng vẫn 403 | Thiếu/sai CSRF token | Thêm `.with(csrf())` khi test authorization, hoặc test CSRF riêng |
| Request anonymous trả 302 | Form login entry point | Assert redirect theo config thay vì mặc định kỳ vọng 401 |
| Mock user được 200 nhưng login thật bị từ chối | Test bỏ qua AuthenticationProvider/UserDetailsService/token decoder | Viết test luồng auth thật |
| User có scope trong token nhưng test matcher không khớp | Converter tạo authority `SCOPE_...` khác với dữ liệu mock | Kiểm tra authority mapping và dùng chuỗi thực |
| Một test dùng identity sai | `@WithMockUser` ở class hoặc `defaultRequest` có user khác | Override rõ trong từng request, test anonymous |
| Test `@PreAuthorize` không chặn | Không kích hoạt method security hoặc gọi ngoài Spring proxy | Dùng Spring context + `@EnableMethodSecurity`, gọi bean được proxy |

**Không viết test chỉ để làm xanh CI.** Cấu hình fixture role/authority phải phản ánh policy mong muốn; tránh nới rộng production rule hoặc tắt filter để khớp kết quả test.

## 13. Câu hỏi tự kiểm tra

1. `user("alex")` có `ROLE_USER` theo mặc định. Nó thỏa `authenticated()` không? Có. Nó thỏa `hasRole("ADMIN")` không? Không.
2. `roles("AUDITOR")` tạo authority gì? `ROLE_AUDITOR`, không phải `AUDITOR`.
3. Với `hasAuthority("document:delete")`, chỉ gán `ROLE_ADMIN` có chắc qua không? Không; phải có authority chính xác hoặc policy bổ sung.
4. Vì sao `anonymous()` vẫn cần khi test đã có default user? Để xác minh nhánh không đăng nhập ngay cả khi fixture mặc định có người dùng.
5. Vì sao POST với `.with(user("reporter").roles("REPORTER"))` có thể 403 dù role đúng? Thiếu CSRF token hoặc một tầng kiểm soát khác.
6. `user("alice")` có chứng minh Alice tồn tại trong database, password hợp lệ và JWT converter chạy đúng không? Không. Nó chủ động cung cấp mock principal để cô lập kiểm thử phân quyền.
7. Khi đổi test từ `roles("ADMIN")` sang `authorities(new SimpleGrantedAuthority("ADMIN"))`, vì sao `hasRole("ADMIN")` từ 200 thành 403? Do mất tiền tố `ROLE_` theo mặc định.
8. Một test chỉ `GET /api/reports` với `ROLE_REPORTER` trả 200 có đủ để kết luận endpoint an toàn không? Không: thêm negative cases (anonymous, thiếu role), unsafe method/CSRF và policy trên tài nguyên khi cần.

## 14. Tài liệu chính thức

Các URL dưới đây dùng nhánh Spring Security 6.5, phù hợp cơ chế API được minh họa. Nếu project đang dùng major khác, hãy đối chiếu reference tương ứng:

- Running as a User in Spring MVC Test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- Setting Up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security test integration overview: https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html
