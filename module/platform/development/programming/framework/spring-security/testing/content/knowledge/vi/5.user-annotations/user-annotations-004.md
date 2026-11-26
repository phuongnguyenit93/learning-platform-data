# `authorities` và tên quyền tường minh trong `@WithMockUser`

## 1. Vấn đề cần giải quyết

Trong một ứng dụng bảo vệ bằng Spring Security, việc **đã xác thực** chưa đủ để truy cập mọi tài nguyên. Người dùng có thể được xem báo cáo nhưng không được phê duyệt báo cáo; một nhân viên hỗ trợ có thể đọc hồ sơ nhưng không được xóa hồ sơ. Các quyền như `report:read`, `report:approve` hoặc `customer:delete` thường được biểu diễn bằng **authority**.

Khi viết kiểm thử với thư viện `spring-security-test`, `@WithMockUser(authorities = ...)` cho phép gán trực tiếp những authority này cho danh tính giả lập. Không cần tạo tài khoản thật, đăng nhập bằng mật khẩu, cấp JWT hay gọi máy chủ OAuth2/OIDC để kiểm chứng riêng quy tắc phân quyền.

Bài học thuộc chương **Annotation người dùng** của module **SPRING_SECURITY_TESTING**. Mục tiêu là hiểu chính xác giá trị mà `authorities` đưa vào `SecurityContext` và cách so khớp giá trị đó qua `MockMvc` trên Servlet hoặc `WebTestClient` trên Reactive. Qua đó, người học kiểm chứng được cả HTTP request **được phép** lẫn **bị từ chối** và nhận ra khi nào cần mô phỏng JWT/OAuth2/OIDC thay cho `@WithMockUser`.

Sau bài này, bạn có thể:

- Dùng `authorities` để cấp một hoặc nhiều quyền cụ thể cho người dùng giả lập.
- Phân biệt phép so khớp chính xác của `hasAuthority`/`hasAnyAuthority` với quy ước `ROLE_` của `roles`/`hasRole`.
- Giải thích vì sao tên quyền sai chữ hoa, dấu phân cách hoặc tiền tố có thể dẫn đến `403 Forbidden`.
- Kiểm tra authority trong `Authentication`, principal mặc định và cả kết quả của HTTP request.
- Viết ca dương tính, âm tính, ẩn danh và kiểm thử POST có CSRF trong một ngữ cảnh Spring Security thật.

## 2. Authority nằm ở đâu?

Trong Spring Security, `Authentication` chứa danh tính đã xác thực và tập hợp `GrantedAuthority`. Mỗi `GrantedAuthority` thường mang một chuỗi quyền:

```text
SecurityContext
  └── Authentication (đã xác thực)
        ├── principal: User(username = "mai")
        └── authorities:
              ├── SimpleGrantedAuthority("report:read")
              └── SimpleGrantedAuthority("report:approve")
```

`@WithMockUser` tạo `SecurityContext` cho test nhờ hạ tầng Spring Test. Principal mặc định là `org.springframework.security.core.userdetails.User` và `Authentication` thường là `UsernamePasswordAuthenticationToken`. Dữ liệu này được đặt sẵn ở trạng thái **đã xác thực**, tức annotation không kiểm tra mật khẩu, chữ ký JWT hoặc phiên đăng nhập thật.

Một authority có thể có nhiều dạng tên khác nhau:

| Ví dụ authority | Ý nghĩa minh họa | Quy ước tạo tên |
| --- | --- | --- |
| `report:read` | Được đọc báo cáo | Quyền chi tiết do ứng dụng định nghĩa |
| `report:approve` | Được phê duyệt báo cáo | Quyền chi tiết do ứng dụng định nghĩa |
| `customer:delete` | Được xóa hồ sơ khách hàng | Quyền chi tiết do ứng dụng định nghĩa |
| `ROLE_ADMIN` | Mang vai trò `ADMIN` | Quy ước role mặc định của Spring Security |
| `SCOPE_reports.read` | Scope `reports.read` được ánh xạ thành authority | Quy ước mặc định thường gặp trong JWT Resource Server |

Không có định dạng `object:action` bắt buộc cho mọi ứng dụng. Spring Security đối chiếu **chuỗi authority đang được cấp** với **chuỗi mà quy tắc phân quyền yêu cầu**; cách đặt tên thuộc về thiết kế chính sách của hệ thống.

## 3. Khai báo một authority tường minh

Ví dụ một test cần người có quyền đọc báo cáo:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(username = "mai", authorities = "report:read")
void readerCanAccessReports() {
    // Người dùng "mai" có authority chính xác "report:read".
}
```

Thuộc tính `authorities` nhận một mảng chuỗi, vì vậy viết một giá trị trực tiếp hoặc viết mảng đều hợp lệ:

```java
@WithMockUser(authorities = "report:read")
// Tương đương:
@WithMockUser(authorities = {"report:read"})
```

Với `authorities`, Spring Security Test **giữ nguyên giá trị được khai báo**. Nó không tự động thêm `ROLE_`, `SCOPE_`, đổi chữ hoa/thường hoặc đổi dấu phân cách.

```text
@WithMockUser(authorities = "report:read")
                 │
                 ▼
GrantedAuthority("report:read")
                 │
                 ▼
hasAuthority("report:read")  → khớp
hasAuthority("REPORT_READ")  → không khớp
hasAuthority("ROLE_report:read") → không khớp
```

Chẳng hạn:

```java
@WithMockUser(username = "mai", authorities = "Report:Read")
```

không thỏa mãn một quy tắc yêu cầu `hasAuthority("report:read")`, vì **`Report:Read` khác `report:read`**. Giá trị authority cũng không tự được chuẩn hóa khi tạo test; nếu quy tắc của dự án dùng `report.read`, hãy khai báo đúng chuỗi đó.

## 4. Nhiều authority và dữ liệu trong `SecurityContext`

Một danh tính có thể mang nhiều quyền:

```java
@Test
@WithMockUser(
    username = "linh",
    authorities = {"report:read", "report:approve", "audit:view"}
)
void principalHasExplicitPermissions() {
    Authentication authentication = SecurityContextHolder.getContext()
            .getAuthentication();

    assertThat(authentication.isAuthenticated()).isTrue();
    assertThat(authentication.getName()).isEqualTo("linh");
    assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder(
                    "report:read",
                    "report:approve",
                    "audit:view"
            );
}
```

Các kiểu được dùng ở trên:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.assertj.core.api.Assertions.assertThat;
```

Đây là test dựa trên Spring Test, chẳng hạn `@SpringBootTest`, `@WebMvcTest` hoặc `@ExtendWith(SpringExtension.class)` cùng ngữ cảnh phù hợp. `WithSecurityContextTestExecutionListener` xử lý annotation để thiết lập `SecurityContext` trước khi phương thức test chạy.

Để kiểm tra sự tồn tại của từng quyền, nên dùng `contains` hoặc `containsExactlyInAnyOrder` thay vì dựa vào thứ tự danh sách, trừ khi thứ tự đó là một phần của hợp đồng mà ứng dụng thật sự cần.

### Đừng nhầm principal với authority

`@WithMockUser(username = "linh", authorities = "report:read")` vẫn tạo principal dạng `User` của Spring Security. Thuộc tính `authorities` chỉ điều khiển danh sách `GrantedAuthority`, **không biến principal thành** entity người dùng của dự án, `Jwt`, `OAuth2User` hay `OidcUser`.

Nếu mã ứng dụng yêu cầu một principal tùy biến có `tenantId`, `userId` hoặc claim của token, bạn cần cơ chế test khác như `@WithUserDetails`, `@WithSecurityContext` hoặc bộ giả lập JWT/OAuth2/OIDC. Việc cấp đúng authority không thay thế được yêu cầu về **kiểu principal**.

## 5. `authorities` khác `roles` như thế nào?

Đây là khác biệt cốt lõi:

| Annotation | Authority thực tế | Quy tắc tương ứng |
| --- | --- | --- |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` |
| `@WithMockUser(authorities = "ADMIN")` | `ADMIN` | `hasAuthority("ADMIN")` |
| `@WithMockUser(authorities = "ROLE_ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| `@WithMockUser(authorities = "report:read")` | `report:read` | `hasAuthority("report:read")` |
| `@WithMockUser(authorities = "SCOPE_reports.read")` | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` |

`roles = "ADMIN"` tự sinh `ROLE_ADMIN`, vì Spring Security Test áp dụng tiền tố `ROLE_` theo quy ước. Ngược lại, `authorities = "ADMIN"` **không** tự thêm tiền tố.

Vì thế, các tổ hợp sau có kết quả khác nhau theo quy tắc role mặc định:

```java
// Đạt yêu cầu hasRole("ADMIN"):
@WithMockUser(roles = "ADMIN")

// Cũng đạt yêu cầu hasRole("ADMIN"):
@WithMockUser(authorities = "ROLE_ADMIN")

// Không đạt yêu cầu hasRole("ADMIN"):
@WithMockUser(authorities = "ADMIN")
```

### Trường hợp khai báo cả `roles` lẫn `authorities`

Khi `authorities` **không rỗng**, danh sách quyền tường minh được ưu tiên và `roles` không được dùng để sinh thêm authority:

```java
@WithMockUser(
    username = "linh",
    roles = "ADMIN",
    authorities = "report:read"
)
// Authority thực tế: report:read
// Không có ROLE_ADMIN được tự động thêm vào.
```

Muốn kết hợp một role và một quyền chi tiết, hãy liệt kê trực tiếp:

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "report:read"})
```

Một hệ quả thường gặp là việc dùng `@WithMockUser(roles = "ADMIN", authorities = "report:read")` rồi kỳ vọng test truy cập endpoint `hasRole("ADMIN")` phải thành công. Nếu không có `ROLE_ADMIN` trong danh sách authority, quy tắc trên sẽ từ chối.

> **Nguyên tắc lựa chọn:** `roles` phù hợp khi chính sách dùng role theo tiền tố mặc định; `authorities` phù hợp khi cần kiểm soát chính xác từng chuỗi quyền hoặc cần kết hợp role với quyền chi tiết.

## 6. So khớp quyền bằng `hasAuthority` và `hasAnyAuthority`

Spring Security cung cấp các quy tắc phổ biến:

```java
.hasAuthority("report:read")
.hasAnyAuthority("report:read", "report:approve")
.hasRole("ADMIN")
.hasAnyRole("READER", "ADMIN")
```

Giả sử người dùng có đúng hai authority `report:read` và `audit:view`. Khi đó:

| Quy tắc cần kiểm chứng | Kết quả | Giải thích |
| --- | --- | --- |
| `hasAuthority("report:read")` | Cho phép | Có chuỗi trùng chính xác |
| `hasAuthority("report:approve")` | Từ chối | Thiếu authority cần thiết |
| `hasAnyAuthority("audit:view", "report:approve")` | Cho phép | Có `audit:view`, chỉ cần một quyền |
| `hasAnyAuthority("report:approve", "customer:delete")` | Từ chối | Không có quyền nào phù hợp |
| `hasRole("ADMIN")` | Từ chối theo mặc định | Thiếu `ROLE_ADMIN` |

`hasAnyAuthority` là điều kiện **OR**: người dùng chỉ cần một trong các authority được liệt kê, không bắt buộc sở hữu tất cả. Nếu nghiệp vụ yêu cầu cả hai quyền, cần xây dựng điều kiện AND tường minh.

Với method security, có thể dùng:

```java
@PreAuthorize("hasAuthority('report:approve')")
public void approveReport(long reportId) {
    // ...
}

@PreAuthorize("hasAuthority('report:read') and hasAuthority('audit:view')")
public void readSensitiveAudit(long reportId) {
    // ...
}
```

Các annotation `@PreAuthorize` chỉ được thực thi khi ứng dụng đã bật method security tương ứng, ví dụ `@EnableMethodSecurity`. Nếu method security chưa bật, một test trả thành công không chứng minh rằng biểu thức đã được kiểm tra.

## 7. Ví dụ chạy xuyên suốt: kiểm chứng HTTP bằng `MockMvc`

Ví dụ sau mô tả một hệ thống báo cáo với ba hành động:

- `GET /reports/{id}` yêu cầu `report:read`.
- `POST /reports/{id}/approve` yêu cầu `report:approve`.
- `GET /admin/reports` yêu cầu role `ADMIN`, tương ứng authority `ROLE_ADMIN` theo quy ước.

Mục tiêu là kiểm tra **đúng chuỗi authority**, phân biệt `200 OK`, `204 No Content`, `401 Unauthorized` và `403 Forbidden`, đồng thời loại trừ lỗi CSRF khi đánh giá phân quyền POST.

### 7.1. Phụ thuộc trong dự án

Một dự án Spring Boot Servlet dùng Gradle cần Spring MVC, Spring Security, JUnit 5 và Spring Security Test:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Ví dụ hướng tới Spring Boot 3 / Spring Security 6 và Java 17 trở lên. Trong dự án Spring Boot thuộc thế hệ khác, tên starter hoặc package của annotation test có thể thay đổi; hãy đối chiếu với phiên bản thực tế. Các lớp Java dưới đây được giả định cùng package để việc import lớp ứng dụng không làm loãng ví dụ.

### 7.2. Controller mẫu

```java
// ReportController.java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/reports/{id}")
    String getReport(@PathVariable long id) {
        return "report-" + id;
    }

    @PostMapping("/reports/{id}/approve")
    ResponseEntity<Void> approveReport(@PathVariable long id) {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/admin/reports")
    String adminReports() {
        return "admin-ok";
    }
}
```

Các endpoint cố ý đơn giản để bài test tập trung vào bảo vệ HTTP, thay vì logic cơ sở dữ liệu hay nghiệp vụ.

### 7.3. `SecurityFilterChain` sử dụng quyền tường minh

```java
// ReportSecurityConfig.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ReportSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/admin/reports")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/reports/*")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.POST, "/reports/*/approve")
                    .hasAuthority("report:approve")
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        // CSRF vẫn được bật cho POST.
        return http.build();
    }
}
```

Đoạn cấu hình này không tự tạo quyền `report:read` cho người dùng. Nó chỉ nói rằng một request đến endpoint đó **cần** authority có chuỗi tương ứng. Việc cung cấp authority thuộc về lớp xác thực hoặc, trong test, thuộc về `@WithMockUser`.

### 7.4. Lớp test đầy đủ

```java
// ReportControllerSecurityTest.java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReportController.class)
@Import(ReportSecurityConfig.class)
class ReportControllerSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "mai", authorities = "report:read")
    void readerCanGetReport() throws Exception {
        Authentication authentication = SecurityContextHolder.getContext()
                .getAuthentication();

        assertThat(authentication.getName()).isEqualTo("mai");
        assertThat(authentication.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("report:read");

        mockMvc.perform(get("/reports/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("report-42"));
    }

    @Test
    @WithMockUser(authorities = "Report:Read")
    void permissionNameIsCaseSensitive() throws Exception {
        mockMvc.perform(get("/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCannotApproveWithoutPermission() throws Exception {
        mockMvc.perform(post("/reports/42/approve").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:approve")
    void approverCanApproveWithCsrf() throws Exception {
        mockMvc.perform(post("/reports/42/approve").with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(
            authorities = {"report:read", "report:approve", "ROLE_ADMIN"}
    )
    void multipleExplicitAuthoritiesPermitSeveralActions() throws Exception {
        mockMvc.perform(get("/reports/42"))
                .andExpect(status().isOk());
        mockMvc.perform(post("/reports/42/approve").with(csrf()))
                .andExpect(status().isNoContent());
        mockMvc.perform(get("/admin/reports"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void bareAdminAuthorityDoesNotMatchHasRoleAdmin() throws Exception {
        mockMvc.perform(get("/admin/reports"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN", authorities = "report:read")
    void explicitAuthoritiesTakePriorityOverRoles() throws Exception {
        Authentication authentication = SecurityContextHolder.getContext()
                .getAuthentication();
        assertThat(authentication.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("report:read");

        mockMvc.perform(get("/admin/reports"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadReport() throws Exception {
        mockMvc.perform(get("/reports/42"))
                .andExpect(status().isUnauthorized());
    }
}
```

### 7.5. Vì sao mỗi ca có kết quả đó?

| Danh tính / authority | Request | Kết quả mong đợi | Nguyên nhân |
| --- | --- | --- | --- |
| `report:read` | `GET /reports/42` | `200` | Khớp chính xác `hasAuthority("report:read")` |
| `Report:Read` | `GET /reports/42` | `403` | Sai chữ hoa/thường |
| `report:read` | `POST /reports/42/approve` + CSRF | `403` | Thiếu `report:approve` |
| `report:approve` | `POST /reports/42/approve` + CSRF | `204` | Đủ quyền và có CSRF hợp lệ |
| `report:read`, `report:approve`, `ROLE_ADMIN` | Cả ba endpoint | `200`, `204`, `200` | Có đủ từng loại quyền |
| `ADMIN` | `GET /admin/reports` | `403` | `hasRole("ADMIN")` cần `ROLE_ADMIN` mặc định |
| `roles = "ADMIN"` kèm `authorities = "report:read"` | `GET /admin/reports` | `403` | Authority tường minh được ưu tiên |
| Ẩn danh | `GET /reports/42` | `401` | HTTP Basic từ chối request chưa xác thực |

**Phân biệt lỗi phân quyền với lỗi CSRF:** khi CSRF bật, `POST`, `PUT`, `PATCH` và `DELETE` thường cần token CSRF hợp lệ. Nếu request POST không có token, Spring Security có thể trả `403` trước khi kiểm tra authority. Do vậy, trong ca `readerCannotApproveWithoutPermission`, `.with(csrf())` giúp cô lập nguyên nhân bị từ chối là **thiếu quyền `report:approve`**. `@WithMockUser` không tự tạo CSRF token.

**Phân biệt `401` với `403`:** trong cấu hình HTTP Basic trên, khách chưa xác thực nhận `401`; người đã xác thực nhưng thiếu authority nhận `403`. Nếu ứng dụng dùng form login, khách chưa đăng nhập có thể bị chuyển hướng đến trang đăng nhập. Vì vậy HTTP status cho khách ẩn danh phải được suy ra từ cấu hình bảo mật cụ thể.

## 8. Đặt `authorities` trên lớp hay trên phương thức?

Nếu nhiều ca test sử dụng một quyền chung, đặt annotation trên lớp:

```java
@WithMockUser(username = "doc-gia", authorities = "report:read")
class ReportAccessTest {

    @Test
    void defaultReaderCanOpenReport() {
        // Dùng report:read từ annotation của lớp.
    }

    @Test
    @WithMockUser(
        username = "nguoi-duyet",
        authorities = {"report:read", "report:approve"}
    )
    void approverHasBothPermissions() {
        // Annotation trên phương thức thay thế cấu hình của lớp.
    }

    @Test
    @WithAnonymousUser
    void guestCannotOpenReport() {
        // Ngữ cảnh ẩn danh thay thế ngữ cảnh có report:read.
    }
}
```

Annotation tại phương thức **ghi đè**, không cộng dồn, annotation tại lớp. Nếu trên lớp có `report:read` mà trên phương thức chỉ khai báo `report:approve`, phương thức đó **không tự được thêm** `report:read`. Hãy liệt kê đầy đủ tất cả quyền mà ca test cần.

Spring Test thiết lập và dọn `SecurityContext` theo vòng đời test; không viết ca test dựa trên giả định rằng authority của phương thức trước sẽ còn lại cho phương thức kế tiếp.

## 9. `WebTestClient` trong ứng dụng Reactive

Trên WebFlux, `@WithMockUser(authorities = "report:read")` cũng biểu diễn một người dùng giả có authority `report:read`. Phần khác biệt là Spring Security Reactive gắn thông tin bảo mật với **Reactor Context**, không dựa riêng vào `ThreadLocal` của `SecurityContextHolder` kiểu Servlet.

Ví dụ cấu trúc test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(ReactiveReportController.class)
@Import(ReactiveReportSecurityConfig.class)
class ReactiveReportSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanGetReport() {
        webTestClient.get().uri("/reports/42")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Đây là **khung minh họa**: ứng dụng phải cung cấp `ReactiveReportController`, `ReactiveReportSecurityConfig` và `SecurityWebFilterChain` có chính sách tương ứng. Hạ tầng Spring Security Test dành cho Reactor cần được tích hợp để danh tính từ annotation có hiệu lực trong luồng reactive.

Nếu cần thay authority **theo từng request**, thay vì dùng annotation cho cả phương thức, có thể sử dụng `SecurityMockServerConfigurers.mockUser`:

```java
// static imports từ SecurityMockServerConfigurers: mockUser, csrf
webTestClient
    .mutateWith(mockUser("mai").authorities(
            new SimpleGrantedAuthority("report:approve")
    ))
    .mutateWith(csrf())
    .post()
    .uri("/reports/42/approve")
    .exchange()
    .expectStatus().isNoContent();
```

Đoạn này giả định `WebTestClient` đã được cấu hình với hỗ trợ Spring Security; `SimpleGrantedAuthority` đến từ `org.springframework.security.core.authority`. Với POST, `csrf()` giúp xác nhận kết quả là do **authority đúng** và request hợp lệ về CSRF. Không dùng nhầm request post-processor dành cho `MockMvc` trong `WebTestClient`.

## 10. Khi authority được tạo từ JWT, OAuth2 hoặc OIDC

Trong ứng dụng Resource Server, dữ liệu quyền có thể bắt nguồn từ claim token, ví dụ:

```json
{
  "sub": "mai",
  "scope": "reports.read reports.approve"
}
```

Với bộ chuyển đổi JWT mặc định thường gặp của Spring Security, các scope được ánh xạ thành `SCOPE_reports.read` và `SCOPE_reports.approve`. Nếu API kiểm tra `hasAuthority("SCOPE_reports.read")`, test phân quyền đơn thuần có thể viết:

```java
@WithMockUser(authorities = "SCOPE_reports.read")
```

Nhưng ca test này chỉ chứng minh **kết quả phân quyền khi authority đó đã tồn tại**. Nó không chứng minh Resource Server đọc đúng claim, xác minh chữ ký JWT, kiểm tra issuer/audience, hay chuyển claim thành authority đúng trong thực tế. Principal của `@WithMockUser` vẫn là một `User` giả chứ không phải `Jwt`.

Để mô phỏng request JWT trong `MockMvc`, dùng `jwt()` của Spring Security Test:

```java
mockMvc.perform(get("/reports/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("report:read")
        )))
    .andExpect(status().isOk());
```

Đây là mẫu cách dùng, yêu cầu endpoint và cấu hình Resource Server phù hợp. Với `WebTestClient` có thể dùng `mockJwt()`; với ứng dụng OAuth2 Login hoặc OIDC có các công cụ như `oauth2Login()` và `oidcLogin()` ở những ngữ cảnh tương ứng. Kiểm thử bộ chuyển đổi claim và kiểm thử quá trình xác thực token thực phải được thiết kế riêng để bao phủ đúng hành vi mong muốn.

### Authority tùy biến và nhiều tenant

Trong hệ thống đa tenant, tên authority có thể không đủ để quyết định truy cập. Chẳng hạn, hai người đều có `report:read` nhưng chỉ được đọc báo cáo thuộc tổ chức của họ. `@WithMockUser(authorities = "report:read")` chỉ kiểm chứng phần **quyền truy cập chung**, chưa tự tạo `tenantId`, quan hệ sở hữu hoặc dữ liệu người dùng riêng.

Nếu logic còn yêu cầu claim JWT, thông tin principal tùy biến hay quyền theo đối tượng (object-level authorization), hãy tạo fixture phản ánh các điều kiện ấy và viết thêm ca được phép/bị từ chối ở đúng tầng xử lý.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `authorities = "ADMIN"` nhưng `hasRole("ADMIN")` trả `403` | Chính sách mặc định yêu cầu `ROLE_ADMIN` | Dùng `roles = "ADMIN"` hoặc `authorities = "ROLE_ADMIN"` |
| `authorities = "Report:Read"` không qua `hasAuthority("report:read")` | Sai chữ hoa/thường | Khớp chính xác tên quyền từ chính sách |
| `authorities = "report_read"` không qua `hasAuthority("report:read")` | Sai dấu phân cách | Dùng một quy ước đặt tên thống nhất |
| Khai báo `roles` và `authorities` nhưng role biến mất | `authorities` không rỗng được ưu tiên | Liệt kê cả `ROLE_ADMIN` và quyền chi tiết trong `authorities` |
| `@WithMockUser` có quyền đúng nhưng controller không nhận `Jwt` | Principal mặc định là `User` | Dùng mock JWT/OAuth2/OIDC hoặc custom security context |
| Người được phép gọi POST vẫn nhận `403` | Có thể thiếu CSRF token | Bổ sung CSRF hợp lệ và kiểm tra security chain |
| Khách ẩn danh không nhận `401` như test mong đợi | Ứng dụng dùng entry point khác, ví dụ form login | Kiểm tra chính sách phản hồi khi chưa xác thực |
| Test luôn trả `200` dù sửa authority | Security filter hoặc chính sách thực tế có thể chưa được áp dụng | Kiểm tra `MockMvc`/`WebTestClient` và cấu hình security test |
| `@PreAuthorize` không chặn dù thiếu authority | Method security chưa được bật hoặc method không đi qua proxy | Kiểm tra `@EnableMethodSecurity` và cách gọi method |
| Test dùng `SCOPE_...` nhưng token thật không có quyền tương ứng | Bộ chuyển đổi scope/claim chưa được kiểm chứng | Test thêm `JwtGrantedAuthoritiesConverter` và cấu hình Resource Server |

Khi gặp `403 Forbidden`, nên kiểm tra theo thứ tự: **request có vượt qua CSRF hay không**, **`Authentication` thực tế có những `GrantedAuthority` nào**, và **chính sách đang yêu cầu chuỗi chính xác nào**. Cách này giúp phân biệt lỗi quyền với lỗi do cách dựng request.

## 12. Bài tập thực hành

Giả sử API có ba hành động:

| Endpoint | Quy tắc bảo mật |
| --- | --- |
| `GET /invoices/{id}` | `hasAuthority("invoice:read")` |
| `POST /invoices/{id}/pay` | `hasAuthority("invoice:pay")` và CSRF hợp lệ |
| `GET /admin/invoices` | `hasRole("ADMIN")` |

Hãy viết một lớp test đáp ứng các tình huống sau:

1. Với `@WithMockUser(authorities = "invoice:read")`, khẳng định trong `SecurityContext` có đúng `invoice:read` rồi gọi `GET /invoices/7`; kỳ vọng được phép.
2. Với cùng danh tính, gửi `POST /invoices/7/pay` có CSRF và kiểm tra bị từ chối do thiếu `invoice:pay`.
3. Thử `@WithMockUser(authorities = "invoice:pay")`; kỳ vọng `POST /invoices/7/pay` với CSRF thành công nhưng `GET /invoices/7` bị từ chối nếu chỉ yêu cầu quyền đọc.
4. Tạo một danh tính mang `invoice:read`, `invoice:pay` và `ROLE_ADMIN` trong cùng mảng `authorities`; kiểm tra ba hành động đều được phép.
5. Dùng `@WithMockUser(authorities = "ADMIN")` và giải thích tại sao không qua `hasRole("ADMIN")` trong cấu hình mặc định.
6. Khai báo `@WithMockUser(roles = "ADMIN", authorities = "invoice:read")`; quan sát authority thực tế và giải thích vì sao `ROLE_ADMIN` không được cộng thêm.
7. Tạo ca khách ẩn danh bằng `@WithAnonymousUser`; so sánh phản hồi thực tế với yêu cầu của cơ chế HTTP Basic hoặc form login trong ứng dụng.

**Gợi ý câu 4:** dùng `@WithMockUser(authorities = {"invoice:read", "invoice:pay", "ROLE_ADMIN"})`. Với câu 5, `ADMIN` khác `ROLE_ADMIN`; với câu 6, `authorities` có giá trị nên nó được ưu tiên hơn `roles`.

## 13. Ghi nhớ

`@WithMockUser(authorities = "...")` gán **đúng chuỗi quyền đã khai báo** vào `Authentication`; không tự thêm `ROLE_` hay chuẩn hóa tên. `hasAuthority` yêu cầu chuỗi tương ứng, còn `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`. Nếu `authorities` không rỗng, nó được ưu tiên thay cho `roles`; muốn cấp nhiều loại quyền, hãy liệt kê đầy đủ trong mảng `authorities`.

Khi kiểm chứng HTTP bằng `MockMvc` hoặc `WebTestClient`, luôn xét cả ca được phép và bị từ chối, bảo đảm các security filter hoạt động và phân biệt lỗi phân quyền với CSRF. Đối với JWT/OAuth2/OIDC, hãy nhớ rằng **đặt authority giả lập** là một bước kiểm thử phân quyền; quá trình tạo, chuyển đổi và xác minh danh tính thật cần các bài test phù hợp khác.
