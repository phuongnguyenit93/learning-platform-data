# Spring Security Test là gì và giải quyết vấn đề nào?

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một API chạy đúng nghiệp vụ vẫn có thể có lỗ hổng xác thực hoặc phân quyền.
- Phân biệt kiểm thử bảo mật ở lớp HTTP với kiểm thử phương thức, kiểm thử token thật và kiểm thử toàn hệ thống.
- Sử dụng `spring-security-test` cùng `MockMvc` (Servlet) hoặc `WebTestClient` (Reactive) để giả lập người dùng, quyền và các tình huống truy cập.
- Nhận biết vai trò của `@WithMockUser`, `SecurityContext`, `csrf()`, `jwt()`, OAuth2/OIDC mock và ý nghĩa của các trạng thái `200`, `401`, `403`.
- Thiết kế ma trận kiểm thử thể hiện được cả truy cập **được phép** lẫn truy cập **phải bị từ chối**.

## 1. Vấn đề: nghiệp vụ đúng chưa chắc bảo mật đúng

Giả sử ứng dụng có ba API:

| API | Quy tắc cần bảo vệ |
| --- | --- |
| `GET /api/me` | Chỉ người dùng đã đăng nhập được xem thông tin của mình. |
| `GET /api/admin/report` | Chỉ người có vai trò `ADMIN` được xem báo cáo quản trị. |
| `POST /api/transfers` | Phải được xác thực; với cấu hình CSRF mặc định, yêu cầu thay đổi trạng thái cần có CSRF token hợp lệ. |

Một unit test gọi thẳng `controller.adminReport()` có thể trả về dữ liệu chính xác, dù ứng dụng thực tế đang cho phép người dùng thường truy cập báo cáo quản trị. Nguyên nhân là lời gọi trực tiếp có thể đi vòng qua **chuỗi bộ lọc bảo mật** (security filter chain), nơi Spring Security xử lý xác thực, CSRF và quy tắc phân quyền theo URL.

Ngược lại, một bài kiểm thử chỉ chứng minh `GET /api/admin/report` trả `200 OK` khi có quản trị viên cũng chưa đủ: nếu người dùng thường vẫn nhận `200` thì chính sách bảo mật đã thất bại. Vì vậy, kiểm thử Spring Security phải bao gồm **ca tích cực** (người có quyền được truy cập) và **ca tiêu cực** (người thiếu quyền hoặc chưa xác thực bị từ chối).

**Spring Security Test** là tập hợp tiện ích trong thư viện `spring-security-test` để thiết lập ngữ cảnh bảo mật và kiểm tra hành vi của Spring Security trong các bài kiểm thử. Nó hỗ trợ cả ứng dụng **Servlet** lẫn **Reactive**, cũng như các trường hợp đăng nhập bằng tài khoản thông thường, JWT, OAuth2 và OpenID Connect (OIDC).

## 2. Spring Security Test tham gia vào luồng xử lý ở đâu?

### 2.1. Hai câu hỏi bảo mật căn bản

- **Authentication – xác thực:** *Yêu cầu này đại diện cho ai?* Ví dụ: chưa đăng nhập, `linh`, hoặc một JWT đại diện cho dịch vụ.
- **Authorization – phân quyền:** *Danh tính đó được làm gì?* Ví dụ: `ROLE_ADMIN` được xem báo cáo, còn `ROLE_USER` không được.

Trong Spring Security, kết quả xác thực thường được biểu diễn bằng một đối tượng `Authentication` chứa principal, trạng thái xác thực và danh sách `GrantedAuthority`. Những thông tin này được dùng để ra quyết định phân quyền.

Với mô hình **Servlet**, ngữ cảnh bảo mật được truy cập thông qua `SecurityContextHolder` trong quá trình xử lý request. Với **Reactive/WebFlux**, Spring Security truyền ngữ cảnh theo chuỗi Reactor thông qua `ReactiveSecurityContextHolder`; không nên coi `ThreadLocal` của Servlet là cơ chế lưu ngữ cảnh cho luồng Reactive.

### 2.2. Kiểm thử ở lớp HTTP

~~~mermaid
flowchart LR
    T["JUnit / Test"] --> R["MockMvc hoặc WebTestClient"]
    R --> F["Security Filter Chain (Servlet) hoặc WebFilter Chain (Reactive)"]
    F --> C["Controller / Handler"]
    C --> M["Service có kiểm tra quyền (nếu có)"]
    M --> O["HTTP response"]
    O --> A["Assert: 200 / 401 / 403 / nội dung"]
~~~

Các công cụ kiểm thử cho phép gửi request mô phỏng qua cơ chế xử lý web của Spring mà thường không cần mở một cổng HTTP thật. Khi chuỗi bảo mật được tích hợp đúng, test có thể xác minh quy tắc truy cập mà ứng dụng áp dụng cho request.

**Điều cần phân biệt:** giả lập một người dùng hoặc JWT giúp thử *quyết định phân quyền* rất nhanh, nhưng không tự động chứng minh mật khẩu được kiểm tra đúng, JWT được xác minh chữ ký, hoặc toàn bộ quá trình chuyển hướng OAuth2/OIDC hoạt động với nhà cung cấp danh tính thật.

## 3. Thư viện và các thành phần thường dùng

Với dự án Spring Boot sử dụng Gradle, có thể khai báo các phụ thuộc kiểm thử sau (phiên bản thư viện thường do Spring Boot quản lý):

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Ứng dụng cần có các starter chạy thực tế phù hợp, chẳng hạn Spring Security và Spring MVC hoặc WebFlux. Không nên thêm cả hai web stack chỉ vì muốn chạy một ví dụ kiểm thử.

| Công cụ | Mục đích |
| --- | --- |
| `MockMvc` | Gửi và kiểm tra request HTTP mô phỏng trong ứng dụng **Servlet/Spring MVC**. |
| `WebTestClient` | Gửi và kiểm tra request trong **Reactive/WebFlux**; cũng có thể dùng trong các chế độ kiểm thử HTTP khác, nhưng cách gắn mock security khác nhau. |
| `@WithMockUser` | Đặt sẵn người dùng giả lập cho một phương thức hoặc lớp kiểm thử. |
| `@WithUserDetails` / `@WithSecurityContext` | Dùng tài khoản từ `UserDetailsService` hoặc tạo ngữ cảnh xác thực tùy biến. |
| `user()`, `httpBasic()`, `csrf()` | Gắn danh tính, header HTTP Basic hoặc CSRF token vào request `MockMvc`. |
| `jwt()`, `opaqueToken()` | Giả lập xác thực bearer token cho kiểm thử phân quyền tại ứng dụng. |
| `oauth2Login()`, `oidcLogin()` | Giả lập principal đăng nhập OAuth2 hoặc OIDC trong bài kiểm thử Servlet. |

Trong ví dụ bên dưới, các API là một **hợp đồng bảo mật minh họa**. Khi đưa vào dự án thực tế, hãy thay đường dẫn và điều kiện phân quyền theo ứng dụng của bạn.

## 4. Ví dụ Servlet: kiểm thử với MockMvc

### 4.1. Tạo chính sách bảo mật tối thiểu

Ví dụ sau dùng cú pháp DSL quen thuộc của Spring Security 6.x; trong dự án phiên bản khác, hãy đối chiếu API cấu hình tương ứng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Configuration
class DemoSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
        // CSRF vẫn được bật theo mặc định.
    }
}

@RestController
@RequestMapping("/api")
class DemoController {

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin/report")
    Map<String, String> adminReport() {
        return Map.of("status", "ready");
    }

    @GetMapping("/reports/daily")
    Map<String, String> dailyReport() {
        return Map.of("report", "daily");
    }

    @PostMapping("/transfers")
    ResponseEntity<Void> transfer() {
        return ResponseEntity.ok().build();
    }
}
~~~

Cấu hình trên yêu cầu mọi request phải được xác thực. Riêng đường dẫn `/api/admin/**` cần vai trò quản trị; đường dẫn `/api/reports/**` cần quyền `SCOPE_reports.read`. Với `httpBasic()`, request chưa có thông tin xác thực tới API được bảo vệ thường nhận `401 Unauthorized`. Người dùng đã xác thực nhưng thiếu quyền sẽ nhận `403 Forbidden`.

### 4.2. Kiểm tra người dùng chưa đăng nhập, người dùng thường và quản trị viên

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class DemoSecurityMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void regularUserCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("linh").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("mai").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ready"));
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/transfers")
                .with(user("linh").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/api/transfers")
                .with(user("linh").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk());
    }

    @Test
    void bearerPrincipalWithRequiredScopeCanReadReport()
            throws Exception {
        mvc.perform(get("/api/reports/daily")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("daily"));
    }
}
~~~

Trong mẫu này:

1. `@SpringBootTest` khởi tạo application context; `@AutoConfigureMockMvc` cung cấp `MockMvc` đã tích hợp các filter của ứng dụng. Với `MockMvc` tự tạo bằng builder, cần gắn cấu hình bảo mật phù hợp, thường qua `.apply(springSecurity())`.
2. `user("linh").roles("USER")` chỉ đặt danh tính giả lập cho **request hiện tại**. `roles("USER")` tạo authority `ROLE_USER`; `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`.
3. `csrf()` sinh token kiểm thử hợp lệ để đi qua kiểm tra CSRF. Cặp test có/không có token phản ánh rõ nguyên nhân `403` của yêu cầu `POST`.
4. `jwt()` dựng thông tin xác thực JWT giả lập để thử quyền truy cập. Test cuối kiểm tra `SCOPE_reports.read`, **không** kiểm tra chữ ký JWT hay hoạt động của `JwtDecoder`.

Đừng dùng `.with(user(...))` hoặc `@WithMockUser` để kết luận rằng cơ chế kiểm tra mật khẩu đã hoạt động. Muốn thử đường đi HTTP Basic thực tế, có thể gửi `.with(httpBasic("linh", "password"))` và cấu hình `UserDetailsService`/mật khẩu dùng trong môi trường test.

### 4.3. Dùng @WithMockUser cho những ca không cần tùy biến từng request

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AnnotatedSecurityMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "linh", roles = "USER")
    void regularUserIsDenied() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }
}
~~~

`@WithMockUser` được Spring Security Test thiết lập trước khi chạy phương thức kiểm thử và dọn dẹp theo vòng đời test, giúp các ca kiểm thử độc lập nhau. Không truyền tham số thì annotation mặc định tạo người dùng `user` có vai trò `USER`.

Để kiểm tra quyền theo tên chính xác, dùng `@WithMockUser(authorities = "SCOPE_reports.read")`. Khi cần principal tùy biến hoặc dữ liệu có trong database, cân nhắc `@WithUserDetails` hoặc annotation xây dựng bằng `@WithSecurityContext`.

## 5. Kiểm thử CSRF: vì sao đã đăng nhập vẫn có thể nhận 403?

**Cross-Site Request Forgery (CSRF)** là tình huống trình duyệt của người dùng đang đăng nhập bị dẫn dụ gửi một yêu cầu thay đổi dữ liệu tới ứng dụng. Khi ứng dụng sử dụng phương thức xác thực tự động đi kèm request, chẳng hạn cookie phiên, Spring Security có thể yêu cầu token CSRF cho các HTTP method làm thay đổi trạng thái.

Với cấu hình mặc định ở ví dụ Servlet:

- `GET /api/me` là phương thức đọc, thông thường không yêu cầu CSRF token.
- `POST /api/transfers` cần CSRF token; dù `linh` đã được xác thực, thiếu token vẫn có thể nhận `403`.
- `.with(csrf())` cung cấp token hợp lệ cho request test; `.with(csrf().useInvalidToken())` giúp thử trường hợp token sai.

Nếu ứng dụng thật đã cấu hình bỏ qua hoặc tắt CSRF cho API stateless với mô hình đe dọa phù hợp, test phải phản ánh cấu hình đó. Không nên viết test luôn mong chờ `403` cho mọi `POST` rồi mặc nhiên coi đó là cơ chế bảo vệ đúng.

**Lưu ý về mã trạng thái:** `401` thường biểu thị chưa có xác thực hợp lệ; `403` thường biểu thị không được cấp quyền hoặc bị chặn bởi một cơ chế như CSRF. Tuy nhiên mã cụ thể phụ thuộc entry point và cấu hình: một ứng dụng form login có thể trả `302 Redirect` tới trang đăng nhập thay vì `401`.

## 6. Kiểm thử quyền ở tầng phương thức

Quy tắc theo URL chưa bao phủ hết bảo mật. Có ứng dụng cần kiểm tra quyền ngay khi service được gọi từ REST controller, job hoặc thành phần khác. Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String exportSensitiveReport() {
        return "private-report";
    }
}
~~~

Với ứng dụng Servlet, cấu hình `@EnableMethodSecurity` để Spring áp dụng kiểm tra quyền qua proxy phù hợp. Một bài kiểm thử gọi **bean do Spring quản lý** sẽ xác minh điều đó:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(roles = "USER")
    void userCannotExportSensitiveReport() {
        assertThatThrownBy(reportService::exportSensitiveReport)
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Nếu tự tạo service bằng `new ReportService()`, lời gọi có thể không đi qua proxy và `@PreAuthorize` sẽ không được thực thi; đó không phải bài kiểm thử phương thức bảo mật có ý nghĩa. Với ứng dụng Reactive, dùng cơ chế method security tương ứng như `@EnableReactiveMethodSecurity` và xác minh ngữ cảnh xác thực trên luồng Reactor.

Kiểm thử phân quyền theo **đối tượng** còn cần dữ liệu cụ thể: một người có quyền `read:invoice` có thể được đọc hóa đơn của mình nhưng không được đọc hóa đơn của người khác. Chỉ kiểm tra vai trò theo URL sẽ không tìm ra lỗi bỏ sót kiểm tra chủ sở hữu.

## 7. Ứng dụng Reactive: WebTestClient và mock security

Spring WebFlux không chạy theo Servlet FilterChain. Nó dùng WebFilter và ngữ cảnh trong Reactor, nên thông thường kiểm thử thông qua `WebTestClient` và các tiện ích từ `SecurityMockServerConfigurers`.

Ví dụ này giả định **một ứng dụng WebFlux riêng** với các endpoint và quy tắc truy cập tương tự mục 4. Cần có `SecurityWebFilterChain` trong context; có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveDemoSecurityConfig {

    @Bean
    SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Test dùng `WebTestClient` gắn vào **application context trong cùng tiến trình**, sau đó áp dụng Spring Security:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.*;

@SpringBootTest
class ReactiveSecurityTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousIsRejected() {
        client.get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void userIsDenied() {
        client.mutateWith(mockUser("linh").roles("USER"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminIsAllowed() {
        client.mutateWith(mockUser("mai").roles("ADMIN"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void csrfIsRequiredForPost() {
        client.mutateWith(mockUser("linh"))
            .post().uri("/api/transfers")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("linh"))
            .mutateWith(csrf())
            .post().uri("/api/transfers")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Trong ví dụ Reactive, `mockUser()` là cách gắn danh tính giả lập qua cơ chế kiểm thử của WebFlux. Để thử ứng dụng resource server JWT, có thể sử dụng `mockJwt()` và thiết lập claims/authorities phù hợp.

**Giới hạn quan trọng:** cơ chế `mutateWith(mockUser(...))` và `mockJwt()` dành cho client gắn trực tiếp vào mock server/application context của bài test. Nếu `WebTestClient` đang gọi một server **thật qua mạng** (ví dụ `RANDOM_PORT` hoặc môi trường triển khai), trạng thái bảo mật giả lập trong tiến trình test không tự truyền sang server đó. Khi ấy phải gửi credential hoặc bearer token thực tế qua HTTP.

## 8. JWT, OAuth2 và OIDC: đang giả lập phần nào?

Ứng dụng hiện đại thường tách việc phát hành danh tính khỏi quyết định phân quyền tại API. Vì thế cần phân biệt hai lớp kiểm tra:

1. **Token đã được xác minh hay chưa?** Chữ ký, thời hạn, issuer, audience, thuật toán và các quy tắc liên quan do bộ xác minh/decoder xử lý.
2. **Danh tính và authorities sau khi xác minh có được truy cập tài nguyên không?** Filter chain hoặc method security xử lý.

`spring-security-test` đặc biệt hữu ích để kiểm tra câu hỏi thứ hai mà không cần dựng toàn bộ Identity Provider.

| Tình huống | Servlet – tiện ích thử nghiệm | Điều thực sự được kiểm tra |
| --- | --- | --- |
| API dùng JWT bearer token | `jwt()` | Quyết định dựa trên `JwtAuthenticationToken`, claims và authorities giả lập. |
| API dùng opaque bearer token | `opaqueToken()` | Phân quyền theo principal và authorities đã được giả lập từ token. |
| Đăng nhập OAuth2 | `oauth2Login()` | Xử lý của ứng dụng sau khi đã có một OAuth2 principal. |
| Đăng nhập OpenID Connect | `oidcLogin()` | Xử lý dựa trên OIDC principal, thông tin định danh và quyền. |
| OAuth2 client gọi dịch vụ khác | `oauth2Client()` | Logic tích hợp với thông tin authorized client giả lập. |

Ví dụ thay đổi scope để kiểm tra *cho phép* và *từ chối* tại endpoint `/api/reports/daily`:

~~~java
@Test
void jwtWithoutRequiredScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/reports/daily")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile.read"))))
        .andExpect(status().isForbidden());
}

@Test
void jwtWithRequiredScopeIsAllowed() throws Exception {
    mvc.perform(get("/api/reports/daily")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isOk());
}
~~~

Các bài này kiểm tra quy tắc `hasAuthority("SCOPE_reports.read")`. Chúng **không đủ** để kết luận rằng ứng dụng sẽ từ chối token giả mạo, token hết hạn hay token sai issuer. Muốn kiểm tra phần đó, cần bài tích hợp thực sự đi qua `BearerTokenAuthenticationFilter`/bộ xác minh JWT (hoặc cơ chế tương ứng của Reactive), với decoder hoặc nguồn khóa kiểm thử được cấu hình có chủ đích.

Không nhầm **role** và **authority**:

- `hasRole("ADMIN")` thông thường so với authority `ROLE_ADMIN`.
- `hasAuthority("SCOPE_reports.read")` so với đúng chuỗi `SCOPE_reports.read`.
- Một scope trong token không tự động đồng nghĩa với một role. Quy tắc ánh xạ từ claims sang `GrantedAuthority` phải được kiểm tra riêng nếu ứng dụng tùy biến bộ chuyển đổi.

Đối với OIDC, `oidcLogin()` đặc biệt hữu ích khi ứng dụng sử dụng thông tin từ ID token/UserInfo để hiển thị hồ sơ hoặc cấp quyền. Tuy nhiên, nó không mô phỏng trọn vẹn authorization code flow, xử lý callback hay kiểm tra token của nhà cung cấp danh tính.

## 9. Chọn phạm vi kiểm thử hợp lý

Không phải mọi bài test đều cần khởi động toàn ứng dụng. Chọn cấp độ theo rủi ro muốn phát hiện:

| Cấp độ | Thiết lập thường gặp | Phát hiện được | Giới hạn |
| --- | --- | --- | --- |
| Unit test quy tắc nghiệp vụ | Gọi hàm với dữ liệu và principal mô phỏng | Sai điều kiện sở hữu, sai điều kiện nghiệp vụ | Không tự kiểm tra web filter hay method-security proxy. |
| MVC slice test | `@WebMvcTest` + cấu hình security/filter cần thiết | Quy tắc HTTP ở phần web được nạp | Có thể thiếu bean/cấu hình thực tế nếu slice chưa được dựng đủ. |
| HTTP integration test | `@SpringBootTest` + `@AutoConfigureMockMvc` | Filter chain, URL authorization, CSRF, controller | Mock authentication có thể bỏ qua phần xác minh credential. |
| Reactive integration test | `WebTestClient` gắn context + `springSecurity()` | WebFilter và xử lý Reactive | Mock principal không đại diện cho bearer token thật từ bên ngoài. |
| Kiểm thử xác thực thật/E2E | Gửi credential/token qua HTTP tới app đang chạy | Lỗi ở decoder, lưu phiên, redirect/callback, cấu hình triển khai theo phạm vi test | Chạy chậm hơn và cần hạ tầng kiểm thử. |

Với `@WebMvcTest`, phải đặc biệt kiểm tra xem cấu hình `SecurityFilterChain` thật có xuất hiện trong test context hay không. Một `403`/`200` từ cấu hình mặc định khác với production có thể khiến kết luận về bảo mật bị sai.

Đối với Spring MVC, nếu tự dựng `MockMvc` bằng `MockMvcBuilders.webAppContextSetup(context)`, hãy áp dụng `springSecurity()` để gắn chuỗi bảo mật và các hook kiểm thử. Với cấu hình `@AutoConfigureMockMvc` thông thường, bộ lọc của context đã được tích hợp theo cơ chế tự động của Spring Boot.

## 10. Ma trận kiểm thử tối thiểu cho một API có bảo mật

Trước khi viết test, chuyển chính sách thành bảng các tình huống có thể quan sát được. Ví dụ với ứng dụng ở mục 4:

| Người gọi | Request | Kỳ vọng | Lý do |
| --- | --- | --- | --- |
| Chưa đăng nhập | `GET /api/me` | `401` | Cần được xác thực; cấu hình dùng HTTP Basic. |
| `ROLE_USER` | `GET /api/admin/report` | `403` | Thiếu `ROLE_ADMIN`. |
| `ROLE_ADMIN` | `GET /api/admin/report` | `200` | Đúng vai trò. |
| `ROLE_USER` | `POST /api/transfers`, thiếu CSRF | `403` | CSRF đang bật. |
| `ROLE_USER` | `POST /api/transfers`, có CSRF | `200` | Đã xác thực và có token CSRF hợp lệ. |
| JWT mock có `SCOPE_profile.read` | `GET /api/reports/daily` | `403` | Thiếu scope được yêu cầu. |
| JWT mock có `SCOPE_reports.read` | `GET /api/reports/daily` | `200` | Có authority được yêu cầu. |

Ma trận cần mở rộng theo đặc thù ứng dụng: tài nguyên thuộc người khác, tài khoản bị khóa, token hết hạn, CORS, route công khai, route nội bộ, và từng phương thức HTTP có nguy cơ thay đổi dữ liệu.

Khi một test mong đợi `403`, hãy chắc chắn nó bị chặn vì **đúng quy tắc cần thử**. Ví dụ, test quyền `POST` nhưng quên CSRF có thể nhận `403` ngay từ `CsrfFilter`, khiến lỗi phân quyền bị che mất. Hãy thêm `csrf()` khi mục tiêu kiểm thử là role hoặc authority trên endpoint POST, trừ khi chính CSRF là đối tượng của test.

## 11. Các lỗi thường gặp và cách chẩn đoán

**Test vượt qua dù route bị mở công khai.** Có thể bạn chỉ kiểm tra trường hợp quản trị viên được `200` mà quên trường hợp người dùng thường phải `403`. Cần ít nhất một ca từ chối cho mỗi quy tắc phân quyền nhạy cảm.

**Tưởng `@WithMockUser` kiểm tra đăng nhập thực.** Annotation trực tiếp tạo security context đã xác thực; mật khẩu, session login, OAuth2 redirect và chữ ký token không đi qua đường xác thực thật. Hãy viết bài kiểm thử riêng cho đường xác thực khi cần.

**Sai `ROLE_` hoặc `SCOPE_`.** `roles("ADMIN")` tạo `ROLE_ADMIN`; `authorities("ADMIN")` chỉ tạo `ADMIN`. Kiểm tra cụ thể biểu thức `hasRole`/`hasAuthority` và lớp ánh xạ JWT claims sang authorities.

**Nhận 403 ngoài dự kiến khi POST.** Kiểm tra CSRF trước khi kết luận có lỗi phân quyền. Nếu API đã tắt CSRF theo cấu hình cụ thể, cần đọc lại hợp đồng bảo mật thay vì thêm `csrf()` một cách máy móc.

**MockMvc hoặc WebTestClient không chạy chuỗi bảo mật.** Kiểm tra filter/webfilter và configurer của Spring Security đã được gắn vào client hay chưa, đặc biệt khi tự tạo test client hoặc dùng test slice.

**Test method security nhưng gọi object tự tạo.** Spring cần quản lý bean và áp dụng proxy/interceptor thì `@PreAuthorize` mới được kiểm tra như trong ứng dụng.

**Test bị sai do kiểm tra quá ít.** Với ca được phép, nên xác minh thêm nội dung hoặc tác động mong đợi; với ca bị từ chối, khi phù hợp, xác minh rằng dữ liệu không bị thay đổi và thông tin nhạy cảm không lọt ra response.

Trong quá trình chẩn đoán lỗi MVC, có thể dùng `.andDo(print())` trên request MockMvc để xem request/response thử nghiệm; đồng thời xem cấu hình security của context đang chạy và nguồn authority thực tế của principal.

## 12. Bài thực hành đề xuất

1. Tạo một ứng dụng Spring MVC nhỏ với ba API `/api/me`, `/api/admin/report` và `/api/transfers`, dùng chính sách ở mục 4.
2. Viết trước hai test `ROLE_USER` bị từ chối và `ROLE_ADMIN` được phép ở `/api/admin/report`. Thử bỏ quy tắc `hasRole("ADMIN")` để quan sát test từ chối thất bại.
3. Thêm hai test cho `POST /api/transfers` có và không có CSRF token; nêu nguyên nhân status của từng test.
4. Thêm endpoint yêu cầu `SCOPE_reports.read` và hai test JWT mock với authorities khác nhau.
5. Chuyển một chính sách sang `@PreAuthorize` tại service và kiểm tra qua bean Spring.
6. Nếu đang học WebFlux, dựng ứng dụng Reactive tương đương và thử lại kịch bản người dùng thường/quản trị viên bằng `WebTestClient`.
7. Bổ sung một bài kiểm thử ngoài phạm vi mock security để chứng minh đường xác thực thật (ví dụ: mật khẩu sai bị từ chối, hoặc JWT có chữ ký/issuer không hợp lệ bị từ chối).

**Tiêu chí hoàn thành:** test mô tả chính sách rõ ràng, bao phủ cả trường hợp được phép lẫn bị từ chối, đi qua lớp bảo mật cần kiểm chứng và thất bại khi bạn cố ý làm yếu một quy tắc bảo vệ.

## 13. Ghi nhớ

Spring Security Test giải quyết khoảng trống giữa **kiểm tra logic nghiệp vụ** và **kiểm chứng chính sách bảo mật khi request được xử lý**. Với Servlet, sử dụng `MockMvc` cùng các tiện ích cho request và security context. Với Reactive, sử dụng `WebTestClient` cùng các tiện ích mock security phù hợp với WebFlux. Các công cụ này rất mạnh khi thử vai trò, authority, CSRF, quyền truy cập URL và method security; còn xác thực credential/token thực tế cần được kiểm chứng bổ sung ở phạm vi tích hợp thích hợp.

Một bài kiểm thử bảo mật tốt phải trả lời đồng thời: **ai được vào, ai phải bị chặn, cơ chế nào ra quyết định, và test có thực sự đi qua cơ chế đó hay không?**
