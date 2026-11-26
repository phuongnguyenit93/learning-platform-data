# AuthorizationManager với yêu cầu được phép và bị từ chối

## 1. Đặt vấn đề: đăng nhập đúng vẫn có thể bị từ chối

Giả sử ứng dụng có API đọc báo cáo `GET /api/reports/42` và API tạo báo cáo `POST /api/reports/new`. Tài khoản `lan` đăng nhập thành công nhưng chỉ được phép đọc báo cáo; tài khoản `minh` có quyền tạo báo cáo. Một yêu cầu đã **xác thực** (authentication) chưa chắc đã được **phân quyền** (authorization) để thực hiện mọi thao tác.

Trong Spring Security, `AuthorizationManager` là hợp đồng dùng để đưa ra quyết định cho phép hoặc từ chối truy cập đối với một đối tượng được bảo vệ: một HTTP request, một lời gọi phương thức hoặc một ngữ cảnh khác. Khi viết kiểm thử, cần xác minh cả nhánh **được phép** lẫn **bị từ chối**, đồng thời phân biệt lỗi thiếu thông tin đăng nhập với lỗi thiếu quyền.

Bài học nằm trong chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun hướng tới kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` cho cả Servlet và Reactive. Vì vậy, bên cạnh kiểm thử trực tiếp `AuthorizationManager`, bài sẽ dùng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và giải thích phạm vi của các tiện ích giả lập JWT/OAuth2/OIDC.

Sau khi học, bạn có thể:

- Phân biệt kết quả xác thực danh tính và quyết định phân quyền.
- Hiểu cách `AuthorizationManager` nhận `Authentication`, đối tượng được bảo vệ và trả quyết định.
- Viết JUnit test cho các quyền `GrantedAuthority` và vai trò `ROLE_ADMIN`, kể cả trường hợp thiếu quyền.
- Kiểm thử luật HTTP được khai báo bằng `authorizeHttpRequests(...)` qua `MockMvc`, bao gồm `401`, `403` và CSRF.
- Nhận biết khi nào `@WithMockUser` là công cụ đúng, khi nào cần kiểm tra xác thực thật bằng HTTP Basic/JWT.
- Phân biệt kiểm thử phân quyền ở Servlet, Reactive và method security.

## 2. Authentication và authorization là hai bước khác nhau

`AuthenticationManager`/`AuthenticationProvider` kiểm tra **người dùng là ai** và các bằng chứng xác thực có hợp lệ không. `AuthorizationManager` dùng thông tin đã có về người dùng, quyền và đối tượng truy cập để quyết định **hành động có được phép hay không**.

Ví dụ:

| Danh tính và quyền | Yêu cầu | Kết quả kỳ vọng |
| --- | --- | --- |
| Chưa xác thực | `GET /api/reports/42` yêu cầu đăng nhập | Bị từ chối; với HTTP Basic thông thường trả `401 Unauthorized` |
| `lan` có `REPORT_READ` | `GET /api/reports/42` | Được phép, thường trả `200 OK` nếu controller xử lý thành công |
| `lan` chỉ có `REPORT_READ` | `POST /api/reports/new` yêu cầu `REPORT_WRITE` | Bị từ chối, thường trả `403 Forbidden` khi đã xác thực |
| `minh` có `REPORT_WRITE` | `POST /api/reports/new` kèm CSRF hợp lệ nếu cần | Được phép, ví dụ trả `201 Created` |
| `lan` có `REPORT_READ` | `GET /api/admin/status` yêu cầu role `ADMIN` | Bị từ chối, thường trả `403 Forbidden` |

`AuthorizationManager` chỉ quyết định cho phép/từ chối; **nó không tự trả mã HTTP**. Mã HTTP hình thành khi các filter, `ExceptionTranslationFilter` và `AuthenticationEntryPoint`/`AccessDeniedHandler` xử lý kết quả bảo mật. Mã cuối cùng còn phụ thuộc cơ chế đăng nhập và cấu hình ứng dụng: form login có thể chuyển hướng thay vì trả `401`.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Security filters lấy hoặc xác minh Authentication"]
    B --> C{"Đã có Authentication phù hợp?"}
    C --> D["AuthorizationManager nhận Authentication và request"]
    D --> E{"Quy tắc truy cập cho phép?"}
    E -- "Có" --> F["Chuyển đến controller"]
    E -- "Không" --> G["Ném / xử lý AccessDeniedException"]
    G --> H{"Người gọi chưa xác thực đầy đủ?"}
    H -- "Có" --> I["AuthenticationEntryPoint: thường 401 với Basic"]
    H -- "Không" --> J["AccessDeniedHandler: thường 403"]
    F --> K["HTTP response của controller"]
~~~

Sơ đồ minh họa luồng HTTP thông thường. Thực tế, các filter xác thực/ủy quyền, CSRF và các xử lý ngoại lệ có thứ tự riêng. Một request có thể bị chặn trước khi tới `AuthorizationManager`, ví dụ `POST` thiếu CSRF khi CSRF đang bật.

## 3. Hợp đồng của AuthorizationManager

`org.springframework.security.authorization.AuthorizationManager<T>` nhận hai loại thông tin:

- `Supplier<Authentication>`: cung cấp `Authentication` của người gọi; thường chỉ được lấy khi cần.
- `T object`: đối tượng cần phân quyền, ví dụ `RequestAuthorizationContext` của Servlet hoặc lời gọi phương thức.

Trong API Spring Security hiện đại, phương thức trả quyết định có dạng:

~~~java
AuthorizationResult authorize(
        Supplier<Authentication> authentication, T object);
~~~

Kết quả có thể biểu thị `isGranted() == true` (cho phép) hoặc `false` (từ chối). Một số phiên bản Spring Security còn có `check(...)` trả `AuthorizationDecision`; ở các phiên bản mới, `check(...)` là API cũ và `authorize(...)` được ưu tiên. Nếu sử dụng phiên bản dự án khác, hãy đối chiếu API tương ứng khi biên dịch ví dụ.

Một số manager cũng có thể trả `null` để không đưa ra quyết định (*abstain*). Khi kết hợp nhiều manager hoặc triển khai manager tùy chỉnh, cần quy định rõ cách xử lý trường hợp này; đừng đánh đồng `null` với cho phép.

Phương thức `verify(...)` trên `AuthorizationManager` dùng để thực thi quyết định và ném `AccessDeniedException` khi bị từ chối. Vì vậy có thể kiểm thử theo hai cách:

1. Gọi `authorize(...)` rồi khẳng định `isGranted()`.
2. Gọi `verify(...)` rồi khẳng định có hoặc không có ngoại lệ tương ứng.

| Thành phần | Vai trò | Điều nên kiểm thử |
| --- | --- | --- |
| `Authentication` | Principal và tập `GrantedAuthority` | Test sử dụng đúng danh tính, trạng thái xác thực và authorities |
| `AuthorizationManager<T>` | Quyết định truy cập cho đối tượng loại `T` | Quyết định đúng cho dữ liệu được phép và bị từ chối |
| `AuthorityAuthorizationManager<T>` | So khớp authority/role yêu cầu | Đúng authority; thiếu quyền bị từ chối |
| `RequestAuthorizationContext` | Bao request Servlet và biến đường dẫn nếu có | Test cung cấp đúng ngữ cảnh request |
| `SecurityFilterChain` | Áp dụng quy tắc vào HTTP request | Đường dẫn, HTTP method, thứ tự matcher, trạng thái phản hồi |
| Method security | Bảo vệ lời gọi đến phương thức Spring bean | Proxy/interceptor áp dụng đúng quy tắc khi gọi bean |

### Role khác authority ra sao?

Spring Security lưu quyền dưới dạng `GrantedAuthority.getAuthority()`. Quy tắc `hasAuthority("REPORT_READ")` so khớp chính xác chuỗi `REPORT_READ`. Trong cấu hình mặc định, `hasRole("ADMIN")` tìm authority `ROLE_ADMIN`, còn `@WithMockUser(roles = "ADMIN")` cũng tạo `ROLE_ADMIN`.

Không giả định `hasAuthority("ADMIN")` tương đương `hasRole("ADMIN")`. Các ứng dụng có thể cấu hình role prefix riêng; khi đó test cần theo đúng chính sách đã cấu hình.

## 4. Kiểm thử component với AuthorityAuthorizationManager

Để kiểm thử riêng quyết định phân quyền, chưa cần khởi động Spring Boot hoặc server HTTP. Ví dụ sau dùng JUnit Jupiter, AssertJ và các lớp Spring Security. `MockHttpServletRequest` đến từ Spring Test.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ReportAuthorizationManagerComponentTest {

    private final AuthorityAuthorizationManager<RequestAuthorizationContext>
            reportRead = AuthorityAuthorizationManager.hasAuthority(
                    "REPORT_READ");

    private final AuthorityAuthorizationManager<RequestAuthorizationContext>
            adminOnly = AuthorityAuthorizationManager.hasRole("ADMIN");

    private static Authentication user(String username, String... authorities) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username,
                null,
                AuthorityUtils.createAuthorityList(authorities));
    }

    private static RequestAuthorizationContext request(String path) {
        return new RequestAuthorizationContext(
                new MockHttpServletRequest("GET", path));
    }

    @Test
    void readAuthorityGrantsReportAccess() {
        Authentication reader = user("lan", "REPORT_READ");

        AuthorizationResult result = reportRead.authorize(
                () -> reader, request("/api/reports/42"));

        assertThat(result).isNotNull();
        assertThat(result.isGranted()).isTrue();
    }

    @Test
    void missingReadAuthorityDeniesReportAccess() {
        Authentication writer = user("minh", "REPORT_WRITE");

        AuthorizationResult result = reportRead.authorize(
                () -> writer, request("/api/reports/42"));

        assertThat(result).isNotNull();
        assertThat(result.isGranted()).isFalse();
    }

    @Test
    void verifyRejectsUserWithoutRequiredAuthority() {
        Authentication writer = user("minh", "REPORT_WRITE");

        assertThatThrownBy(() -> reportRead.verify(
                () -> writer, request("/api/reports/42")))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void verifyAllowsUserWithRequiredAuthority() {
        Authentication reader = user("lan", "REPORT_READ");

        assertThatCode(() -> reportRead.verify(
                () -> reader, request("/api/reports/42")))
                .doesNotThrowAnyException();
    }

    @Test
    void hasRoleAdminAcceptsRoleAdminAuthority() {
        Authentication admin = user("admin", "ROLE_ADMIN");

        AuthorizationResult result = adminOnly.authorize(
                () -> admin, request("/api/admin/status"));

        assertThat(result).isNotNull();
        assertThat(result.isGranted()).isTrue();
    }

    @Test
    void hasRoleAdminDoesNotAcceptUnprefixedAdminAuthority() {
        Authentication wrongAuthority = user("lan", "ADMIN");

        AuthorizationResult result = adminOnly.authorize(
                () -> wrongAuthority, request("/api/admin/status"));

        assertThat(result).isNotNull();
        assertThat(result.isGranted()).isFalse();
    }
}
~~~

Các test này chỉ kiểm tra **quyết định của manager đối với ngữ cảnh đã cung cấp**. `AuthorityAuthorizationManager` trong ví dụ chỉ xét authorities, nên nó không kiểm tra đường dẫn cụ thể; `request("/api/reports/42")` cung cấp một ngữ cảnh giống yêu cầu HTTP, nhưng việc **chọn quy tắc theo URL và HTTP method** là trách nhiệm của cấu hình matcher. Cần kiểm thử tầng HTTP riêng để biết yêu cầu nào được gắn với quy tắc nào.

Khi có nhiều role, nên bổ sung trường hợp người dùng vừa có `REPORT_READ` vừa có `REPORT_WRITE`. Đồng thời kiểm tra người dùng với authority gần giống như `REPORT_READER` vẫn bị từ chối nếu quy tắc yêu cầu chính xác `REPORT_READ`.

### Manager tùy chỉnh dựa trên biến đường dẫn

Không phải quy tắc nào cũng chỉ dựa vào role. Giả sử người dùng được phép đọc tài nguyên của chính mình tại `/api/users/{owner}/reports`. Một manager có thể lấy thông tin `owner` từ `RequestAuthorizationContext`:

~~~java
import java.util.function.Supplier;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

final class OwnerAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        String owner = context.getVariables().get("owner");

        boolean allowed = current != null
                && current.isAuthenticated()
                && owner != null
                && current.getName().equals(owner);

        return new AuthorizationDecision(allowed);
    }
}
~~~

Test trực tiếp cần cung cấp map biến đường dẫn trong context:

~~~java
OwnerAuthorizationManager manager = new OwnerAuthorizationManager();
Authentication lan = UsernamePasswordAuthenticationToken.authenticated(
        "lan", null, AuthorityUtils.createAuthorityList("ROLE_USER"));

RequestAuthorizationContext owned = new RequestAuthorizationContext(
        new MockHttpServletRequest("GET", "/api/users/lan/reports"),
        java.util.Map.of("owner", "lan"));

RequestAuthorizationContext other = new RequestAuthorizationContext(
        new MockHttpServletRequest("GET", "/api/users/minh/reports"),
        java.util.Map.of("owner", "minh"));

assertThat(manager.authorize(() -> lan, owned).isGranted()).isTrue();
assertThat(manager.authorize(() -> lan, other).isGranted()).isFalse();
~~~

Đây là ví dụ minh họa, với biến `owner` được matcher của ứng dụng cung cấp. Khi tích hợp với HTTP thật, phải kiểm tra matcher có chuyển biến đường dẫn đúng hay không. Trong hệ thống có tenant, quyền sở hữu không nên chỉ dựa vào username trong URL nếu dữ liệu nguồn có quy tắc sở hữu khác; cần xác minh quyền từ nguồn dữ liệu tin cậy.

## 5. Khai báo luật HTTP bằng authorizeHttpRequests

Một `SecurityFilterChain` có thể gắn manager vào từng nhóm request qua DSL `authorizeHttpRequests(...)`. Ví dụ sau dành cho ứng dụng **Servlet** sử dụng HTTP Basic; CSRF giữ mặc định để minh họa việc kiểm thử các request thay đổi trạng thái.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ReportSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("REPORT_WRITE")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Thứ tự matcher quan trọng.** Quy tắc phù hợp đầu tiên được áp dụng. Các matcher cụ thể nên nằm trước quy tắc bao quát. Với `anyRequest().denyAll()` ở cuối, các đường dẫn chưa được khai báo sẽ không vô tình trở thành public. Quy tắc `permitAll()` dành cho endpoint công khai; rule còn lại phụ thuộc role/authority.

Để các ví dụ HTTP phía dưới có thể chạy, ứng dụng cần có endpoint tương ứng. Đây là controller tối giản:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/api/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/reports/{id}")
    String report(@PathVariable String id) {
        return "report " + id;
    }

    @PostMapping("/api/reports/new")
    ResponseEntity<Void> createReport() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    @GetMapping("/api/admin/status")
    String adminStatus() {
        return "ok";
    }
}
~~~

Các lớp `ReportSecurityConfig` và `ReportController` cần nằm trong phạm vi quét bean của ứng dụng Spring Boot. Mã nguồn minh họa chỉ phục vụ quy tắc truy cập; một hệ thống thực phải bổ sung kiểm tra dữ liệu, business authorization và các biện pháp bảo vệ khác.

## 6. Kiểm thử request được phép và bị từ chối bằng MockMvc

Để kiểm thử **authorization**, không nhất thiết phải thử mật khẩu ở mọi test. `spring-security-test` cung cấp `@WithMockUser` để đặt `Authentication` giả lập vào `SecurityContext`, giúp mỗi ca chỉ tập trung vào quyền của người dùng. Với `@SpringBootTest` và `@AutoConfigureMockMvc`, request sẽ chạy qua Spring Security filter chain được cấu hình cho test.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportHttpAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointDoesNotRequireLogin() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());
    }

    @Test
    void anonymousUserCannotReadProtectedReport() throws Exception {
        mockMvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "REPORT_READ")
    void readerCanReadReport() throws Exception {
        mockMvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "minh", authorities = "REPORT_WRITE")
    void writerWithoutReadAuthorityCannotReadReport() throws Exception {
        mockMvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "minh", authorities = "REPORT_WRITE")
    void writerCanCreateReportWithValidCsrf() throws Exception {
        mockMvc.perform(post("/api/reports/new").with(csrf()))
                .andExpect(status().isCreated());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "REPORT_READ")
    void readerCannotCreateReportEvenWithValidCsrf() throws Exception {
        mockMvc.perform(post("/api/reports/new").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "minh", authorities = "REPORT_WRITE")
    void postWithoutCsrfIsRejectedBeforeReportPermission() throws Exception {
        mockMvc.perform(post("/api/reports/new"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanAccessAdminStatus() throws Exception {
        mockMvc.perform(get("/api/admin/status"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "REPORT_READ")
    void nonAdminCannotAccessAdminStatus() throws Exception {
        mockMvc.perform(get("/api/admin/status"))
                .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ giả định ứng dụng Spring Boot có `ReportSecurityConfig` và `ReportController` ở mục 5, cũng như các dependency kiểm thử Spring Boot, Spring Security Test và JUnit Jupiter. Nếu ứng dụng có thêm một `SecurityFilterChain` khác, custom entry point hoặc cấu hình CSRF khác, kết quả có thể thay đổi; khi đó cần áp dụng đúng hợp đồng bảo mật của ứng dụng thực.

### Vì sao phải kiểm tra CSRF?

Trong ứng dụng Servlet, bảo vệ CSRF thường áp dụng cho request thay đổi trạng thái như `POST`. Nếu CSRF bật, một request `POST` thiếu CSRF token có thể trả `403` **trước khi** kiểm tra `REPORT_WRITE`. Vì vậy:

- Để chứng minh người dùng **được phép tạo báo cáo**, gửi `.with(csrf())` và kỳ vọng `201` theo controller.
- Để chứng minh người dùng **thiếu quyền tạo báo cáo**, vẫn gửi `.with(csrf())`, rồi kỳ vọng `403` do authorization.
- Để kiểm tra **CSRF**, cố ý bỏ token và kỳ vọng `403`, nhưng không diễn giải kết quả đó là bằng chứng rule `hasAuthority("REPORT_WRITE")` hoạt động đúng.

`@WithMockUser` không kiểm tra password, `UserDetailsService` hay `AuthenticationProvider`. Nó tạo sẵn danh tính/quyền cho test và giúp cô lập logic truy cập. Khi cần xác minh **thông tin đăng nhập thật** đi qua filter, viết test riêng với `httpBasic(...)` hoặc cơ chế đăng nhập mà ứng dụng thực dùng.

## 7. Khi nào cần kiểm chứng kết hợp authentication và authorization?

Giả sử tài khoản `lan` thực sự được lưu với `REPORT_READ`. Một bài test dùng `@WithMockUser(authorities = "REPORT_READ")` sẽ xanh ngay cả khi hệ thống đăng nhập thực lấy sai authorities từ CSDL hoặc `PasswordEncoder` bị cấu hình lỗi. Vì vậy nên giữ ít nhất một đường kiểm thử HTTP thực:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;

// Bên trong bài test dùng MockMvc, với UserDetailsService và provider thật:
mockMvc.perform(get("/api/reports/42")
                .with(httpBasic("lan", "correct-password")))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/admin/status")
                .with(httpBasic("lan", "correct-password")))
        .andExpect(status().isForbidden());

mockMvc.perform(get("/api/reports/42")
                .with(httpBasic("lan", "wrong-password")))
        .andExpect(status().isUnauthorized());
~~~

Đây là đoạn minh họa bổ sung, chỉ chạy khi ứng dụng cấu hình HTTP Basic, tài khoản `lan` và các quyền tương ứng. Bộ kiểm thử kết hợp giúp chứng minh kết quả phân quyền xuất phát từ `Authentication` thật; nó có chi phí chạy cao hơn test component nên không nhất thiết lặp lại mọi tổ hợp quyền.

Khi debug một test thất bại, phân tách rõ:

1. Request có đi qua đúng `SecurityFilterChain` không?
2. Người gọi có được xác thực và có authorities dự kiến không?
3. Matcher nào đã được chọn cho URL và HTTP method?
4. `AuthorizationManager` được chọn trả quyết định gì?
5. Có lớp bảo vệ trước/sau authorization (ví dụ CSRF, method security) thay đổi kết quả không?

## 8. Phân quyền tại phương thức và biểu thức

Rule HTTP thường bảo vệ URL; nhưng dữ liệu nghiệp vụ có thể được truy cập từ nhiều endpoint hoặc qua lời gọi nội bộ. Với method security, Spring Security có thể dùng một `AuthorizationManager` để quyết định việc gọi phương thức được đánh dấu `@PreAuthorize` hoặc `@PostAuthorize`.

Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String findReport(String id) {
        return "report " + id;
    }
}
~~~

Để annotation có hiệu lực, ứng dụng phải bật method security (ví dụ `@EnableMethodSecurity`) và lời gọi phải đi qua Spring proxy/interceptor của bean. Một test chỉ tạo `new ReportService()` rồi gọi `findReport(...)` sẽ **bỏ qua** proxy và không chứng minh được rule hoạt động.

Khi test method security, hãy lấy bean từ Spring context, thiết lập `SecurityContext` bằng `@WithMockUser` và kiểm tra trường hợp có `REPORT_READ` được phép, còn thiếu quyền thì bị từ chối bằng `AccessDeniedException`. Nếu cùng request HTTP đi qua cả URL authorization và method security, kết quả HTTP cuối cùng phụ thuộc vào **cả hai** lớp kiểm tra.

## 9. Với Spring WebFlux và WebTestClient

Spring WebFlux sử dụng chuỗi filter Reactive và các hợp đồng `ReactiveAuthorizationManager`. Kiểm thử component của `AuthorizationManager<RequestAuthorizationContext>` trong Servlet **không thay thế** được kiểm thử `ReactiveAuthorizationManager` với ngữ cảnh Reactive.

Trong WebFlux, `WebTestClient` có thể gắn vào Spring application context, áp dụng `springSecurity()` rồi giả lập người dùng qua `mockUser(...)`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveReportAuthorizationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void readerCanReadReport() {
        WebTestClient client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .build();

        client.mutateWith(
                    mockUser("lan").authorities(
                            new SimpleGrantedAuthority("REPORT_READ")))
                .get()
                .uri("/api/reports/42")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void readerCannotAccessAdmin() {
        WebTestClient client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .build();

        client.mutateWith(
                    mockUser("lan").authorities(
                            new SimpleGrantedAuthority("REPORT_READ")))
                .get()
                .uri("/api/admin/status")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Ví dụ chỉ áp dụng khi test context thực sự là **ứng dụng WebFlux** với các endpoint và rule tương đương được cấu hình trong `SecurityWebFilterChain`. Không áp dụng trực tiếp `SecurityFilterChain` của Servlet ở mục 5 cho Reactive rồi kỳ vọng kết quả tương tự. Một request `POST` Reactive có bật CSRF phải sử dụng cơ chế CSRF test tương ứng, chẳng hạn `SecurityMockServerConfigurers.csrf()`.

`mockUser(...)` trong WebFlux và `@WithMockUser` trong Servlet đều rất hữu ích để kiểm tra **authorization trên ngữ cảnh đã xác thực**. Cả hai không có nghĩa mật khẩu thật đã được kiểm tra hoặc token thật đã được xác minh.

## 10. JWT, OAuth2 và OIDC: phân quyền giả lập khác xác minh token

Với resource server sử dụng JWT, quyền truy cập thường dựa trên authorities/claims được ánh xạ từ token. `spring-security-test` cung cấp `jwt()` cho `MockMvc` và cơ chế tương ứng cho `WebTestClient` để dựng ngữ cảnh JWT phù hợp với test. Các phép kiểm thử này có thể khẳng định:

- Người dùng có authority `SCOPE_reports.read` truy cập được tài nguyên đọc báo cáo.
- Người dùng thiếu scope đó nhận `403` khi đã được coi là xác thực.
- Rule HTTP hoặc method security sử dụng đúng danh sách authorities nhận từ ngữ cảnh giả lập.

Chúng **không** chứng minh JWT đã được giải mã hoặc xác minh chữ ký, issuer, audience, thời hạn hay mapping claims thật từ `JwtDecoder`. Để kiểm chứng các điểm đó, cần kiểm thử resource server với decoder/validator thực hoặc test riêng phần mapping.

Tương tự, `oauth2Login()` và `oidcLogin()` có thể tạo người dùng OAuth2/OIDC giả lập để kiểm tra rule sau đăng nhập. Các tiện ích này không xác nhận luồng authorization code, redirect, callback hoặc phiên giao tiếp với nhà cung cấp định danh thực sự hoạt động.

## 11. Các lỗi kiểm thử phổ biến

**Chỉ kiểm tra ca được phép.** Nếu một tài khoản có `REPORT_READ` truy cập được báo cáo, vẫn cần ca thiếu `REPORT_READ` bị từ chối. Nếu không, rule có thể vô tình thành `permitAll()` mà test vẫn xanh.

**Nhầm 401 và 403.** Trong HTTP Basic thông thường, chưa xác thực thường trả `401`; đã xác thực nhưng thiếu quyền thường trả `403`. Với form login, entry point tùy chỉnh hoặc API gateway, phản hồi có thể khác. Test nên bám hợp đồng HTTP của ứng dụng.

**Nhầm lỗi CSRF với thiếu role.** `POST` có thể bị `403` do thiếu CSRF token dù người dùng có quyền ghi. Với test role, cung cấp token CSRF hợp lệ khi chính sách yêu cầu.

**Nhầm hasRole với hasAuthority.** `hasRole("ADMIN")` mặc định yêu cầu `ROLE_ADMIN`; `hasAuthority("ADMIN")` kiểm tra chính xác `ADMIN`. Đừng sửa kết quả bằng cách gán đại nhiều authority cho user giả lập.

**Chỉ kiểm thử AuthorizationManager trực tiếp.** Điều đó không kiểm tra matcher URL, HTTP method, filter hoặc method proxy. Bổ sung test tầng HTTP hoặc method security khi rule được gắn vào ngữ cảnh thật.

**Chỉ dùng @WithMockUser để khẳng định toàn bộ bảo mật đăng nhập hoạt động.** Annotation tạo sẵn `Authentication`. Muốn kiểm tra password/provider, JWT signature hoặc luồng OIDC thật, cần các test phù hợp với cơ chế xác thực.

**Bỏ qua thứ tự requestMatchers.** Matcher bao quát đặt trước matcher cụ thể có thể nuốt các quy tắc hạn chế hơn. Kiểm thử từng HTTP method, đường dẫn biên và URL ngoài danh sách cho phép.

**Tin tuyệt đối vào dữ liệu đầu vào khi phân quyền theo chủ sở hữu.** Quy tắc kiểu `owner == username` chỉ an toàn khi owner được xác định từ nguồn đáng tin cậy và danh tính được xác thực. Trong ứng dụng nhiều tenant hoặc có quyền chia sẻ, test cần kiểm tra tenant, quan hệ sở hữu và vai trò phù hợp.

**Không kiểm tra SecurityContext đúng với request.** Nếu request dùng người dùng giả lập khác với user được cấu hình trong test context, kết quả có thể xanh ở tầng authorization nhưng thất bại khi gọi HTTP thực. Tách test chính sách quyền và test tích hợp xác thực giúp nhận diện chỗ sai.

## 12. Bài thực hành

1. Mở rộng `ReportAuthorizationManagerComponentTest` bằng tài khoản có cả `REPORT_READ` và `REPORT_WRITE`. Kiểm tra một manager đọc và một manager ghi đều cho phép tài khoản đó.
2. Với `ReportHttpAuthorizationTest`, thêm ca `GET /api/reports/42` bằng `@WithMockUser(authorities = "REPORT_READER")` và khẳng định `403` để chứng minh không so khớp gần đúng.
3. Đổi thứ tự matcher để một rule quá rộng đứng trước `GET /api/reports/**`, chạy lại bài test và xác định ca nào báo lỗi. Sau đó khôi phục thứ tự hạn chế đúng.
4. Viết thêm kiểm thử method security cho `ReportService.findReport(...)` với bean được Spring quản lý. Giải thích vì sao `new ReportService()` bỏ qua bảo vệ của annotation.
5. So sánh một test `@WithMockUser` với test `httpBasic(...)` dùng `UserDetailsService` và `AuthenticationProvider` thật. Chỉ ra bằng chứng nào về xác thực danh tính mà test đầu không cung cấp.
6. Với ứng dụng Reactive, tạo hai ca `WebTestClient` cùng endpoint: một người dùng có authority yêu cầu nhận `200`, người dùng thiếu quyền nhận `403`.

Một bài kiểm thử phân quyền có giá trị khi nó xác minh được **cả yêu cầu phải được cho phép lẫn yêu cầu bắt buộc bị từ chối**, trong đúng ngữ cảnh request hoặc lời gọi phương thức. Kết hợp kiểm thử component của `AuthorizationManager` với kiểm thử HTTP bằng `spring-security-test` giúp phát hiện sai quyền, sai matcher và sai cách xử lý `401/403` trước khi những lỗi này ảnh hưởng người dùng thực.
