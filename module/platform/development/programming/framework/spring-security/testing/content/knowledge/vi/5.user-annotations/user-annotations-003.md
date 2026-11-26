# `roles` và tiền tố `ROLE_` được bổ sung theo quy ước

## 1. Mục tiêu của bài học

Trong ứng dụng Spring Security, một người dùng có thể đã đăng nhập thành công nhưng vẫn không được thực hiện một thao tác vì thiếu quyền. Chẳng hạn, nhân viên được xem báo cáo nhưng chỉ quản trị viên mới được phê duyệt báo cáo. Khi viết test bằng **`spring-security-test`**, `@WithMockUser` cho phép dựng sẵn một người dùng đã xác thực cùng các vai trò (*roles*) để kiểm chứng kết quả phân quyền.

Một điểm rất dễ nhầm là **`roles = "ADMIN"` không tạo authority `"ADMIN"`**. Theo quy ước mặc định của Spring Security, nó tạo **`"ROLE_ADMIN"`**. Việc hiểu chính xác phép chuyển đổi này giúp tránh các ca test nhận `403 Forbidden` dù tưởng rằng đã cung cấp đúng quyền.

Bài thuộc chương **Annotation người dùng** của module **SPRING_SECURITY_TESTING**. Kiến thức sẽ được áp dụng vào kiểm thử HTTP bằng `MockMvc` cho ứng dụng Servlet và `WebTestClient` cho ứng dụng Reactive, đồng thời đặt nền tảng để giả lập `SecurityContext`, JWT/OAuth2/OIDC và các ca được phép hoặc bị từ chối.

Sau khi học xong, bạn có thể:

- Giải thích sự khác nhau giữa *role* và *granted authority* trong Spring Security.
- Dự đoán danh sách authority được tạo bởi `@WithMockUser(roles = ...)`.
- Chọn đúng `hasRole`, `hasAnyRole`, `hasAuthority` và `hasAnyAuthority` trong quy tắc bảo mật.
- Tạo các bài test HTTP xác minh `200`/`204`, `401` và `403`, có xét đến CSRF.
- Phát hiện các trường hợp cấu hình tiền tố role tùy biến hoặc chuyển đổi claim JWT khiến test không khớp với hệ thống thật.

## 2. Role và authority là gì?

Trong mô hình Spring Security, một `Authentication` đã xác thực thường mang theo tập hợp các `GrantedAuthority`. Mỗi `GrantedAuthority` biểu diễn một quyền dưới dạng chuỗi, chẳng hạn `"ROLE_ADMIN"`, `"report:read"` hoặc `"SCOPE_reports.read"`.

**Role** là một cách tổ chức quyền ở mức nghiệp vụ, ví dụ `ADMIN`, `READER`, `AUDITOR`. Mặc định, Spring Security diễn đạt role này trong tập authority bằng tiền tố `ROLE_`:

```text
Role nghiệp vụ:         ADMIN
Authority tương ứng:    ROLE_ADMIN

Role nghiệp vụ:         READER
Authority tương ứng:    ROLE_READER

Quyền chi tiết:         report:approve
Authority tương ứng:    report:approve
```

Tiền tố `ROLE_` là **quy ước biểu diễn role thành authority**, không phải một trường quyền đặc biệt nằm riêng trong `Authentication`. Khi kiểm tra truy cập, Spring Security đối chiếu các `GrantedAuthority` trong đối tượng xác thực với authority mà quy tắc đang yêu cầu.

Ví dụ, với cấu hình HTTP:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
```

quy tắc `hasRole("ADMIN")` theo mặc định yêu cầu authority `ROLE_ADMIN`. Nếu người dùng chỉ có authority `ADMIN`, phép kiểm tra này sẽ không khớp.

## 3. `@WithMockUser(roles = ...)` thêm `ROLE_` như thế nào?

`@WithMockUser` thuộc `org.springframework.security.test.context.support`. Khi được xử lý bởi hạ tầng Spring Test, annotation tạo một `SecurityContext` với `UsernamePasswordAuthenticationToken` đã xác thực. Principal mặc định là `org.springframework.security.core.userdetails.User`; các quyền nằm trong `authentication.getAuthorities()`.

Ví dụ cơ bản:

```java
@Test
@WithMockUser(username = "minh", roles = "ADMIN")
void adminHasPrefixedAuthority() {
    Authentication authentication = SecurityContextHolder
            .getContext()
            .getAuthentication();

    assertThat(authentication.isAuthenticated()).isTrue();
    assertThat(authentication.getName()).isEqualTo("minh");
    assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactly("ROLE_ADMIN");
}
```

Ở đoạn trên, `Authentication`, `GrantedAuthority` và `SecurityContextHolder` đến từ Spring Security; `assertThat` là phép khẳng định của AssertJ. Cần chạy test dưới `SpringExtension` hoặc test slice của Spring Boot để annotation được xử lý.

Hãy đọc thuộc tính `roles` theo công thức:

```text
@WithMockUser(roles = "ADMIN")
                   |
                   v
            "ROLE_" + "ADMIN"
                   |
                   v
       GrantedAuthority("ROLE_ADMIN")
```

| Cấu hình trong test | Danh sách authority được tạo |
| --- | --- |
| `@WithMockUser` | `ROLE_USER` |
| `@WithMockUser(roles = "USER")` | `ROLE_USER` |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` |
| `@WithMockUser(roles = {"READER", "EDITOR"})` | `ROLE_READER`, `ROLE_EDITOR` |
| `@WithMockUser(roles = {"ADMIN", "AUDITOR"})` | `ROLE_ADMIN`, `ROLE_AUDITOR` |

Các vai trò được đặt trong `roles` **không tự động kế thừa** lẫn nhau. Ví dụ, người có `ROLE_ADMIN` không đương nhiên có `ROLE_READER` nếu ứng dụng chưa định nghĩa chính sách cho phép admin truy cập hoặc cấu hình role hierarchy tương ứng.

### Không ghi sẵn `ROLE_` vào `roles`

**Sai:**

```java
@WithMockUser(roles = "ROLE_ADMIN")
```

Nhà máy tạo security context của `@WithMockUser` yêu cầu tên role trong `roles` **không bắt đầu bằng `ROLE_`**, bởi chính annotation sẽ thêm tiền tố này. Với cách khai báo trên, việc dựng context sẽ thất bại, thay vì tạo một người dùng có `ROLE_ADMIN` như mong muốn.

**Đúng:**

```java
@WithMockUser(roles = "ADMIN")
```

Hoặc, nếu muốn khai báo chính xác authority đã có tiền tố, dùng:

```java
@WithMockUser(authorities = "ROLE_ADMIN")
```

## 4. Phân biệt `roles` và `authorities`

Hai thuộc tính đều ảnh hưởng đến danh sách `GrantedAuthority` nhưng có quy tắc khác nhau:

- **`roles`**: nhận tên role không có tiền tố, Spring Security Test thêm `ROLE_` khi dựng authority.
- **`authorities`**: nhận trực tiếp các chuỗi authority, giữ nguyên giá trị đã khai báo.

Ví dụ:

```java
@WithMockUser(username = "lan", roles = "ADMIN")
// authorities: ["ROLE_ADMIN"]

@WithMockUser(username = "lan", authorities = "ADMIN")
// authorities: ["ADMIN"]

@WithMockUser(username = "lan", authorities = "ROLE_ADMIN")
// authorities: ["ROLE_ADMIN"]

@WithMockUser(
    username = "lan",
    authorities = {"ROLE_ADMIN", "report:approve"}
)
// authorities: ["ROLE_ADMIN", "report:approve"]
```

Nếu khai báo **`authorities` không rỗng**, `@WithMockUser` sử dụng các authority tường minh đó và **bỏ qua `roles`**. Vì vậy, đoạn sau **không** tự cộng thêm `ROLE_ADMIN`:

```java
@WithMockUser(
    roles = "ADMIN",
    authorities = "report:approve"
)
// authority có hiệu lực: report:approve
// không tự có ROLE_ADMIN
```

Muốn một người có cả quyền theo role và quyền chi tiết, hãy khai báo đầy đủ:

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "report:approve"})
```

Điều này đặc biệt hữu ích khi API có các quy tắc kết hợp `hasRole("ADMIN")` và `hasAuthority("report:approve")`.

## 5. Liên hệ với `hasRole`, `hasAuthority` và các biến thể

Các phương thức cấu hình phân quyền thường gặp:

| Quy tắc | Chuỗi authority cần có, theo mặc định |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAnyRole("READER", "ADMIN")` | Ít nhất một trong `ROLE_READER`, `ROLE_ADMIN` |
| `hasAuthority("ADMIN")` | Chính xác `ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | Chính xác `ROLE_ADMIN` |
| `hasAuthority("report:approve")` | Chính xác `report:approve` |
| `hasAnyAuthority("report:read", "report:approve")` | Ít nhất một trong hai chuỗi đã nêu |

Bảng dưới đây minh họa kết quả khi các quy tắc sử dụng tiền tố role mặc định:

| Annotation người dùng giả | Authority hiệu lực | `hasRole("ADMIN")` | `hasAuthority("ADMIN")` | `hasAuthority("ROLE_ADMIN")` |
| --- | --- | --- | --- | --- |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` | Đạt | Không đạt | Đạt |
| `@WithMockUser(authorities = "ADMIN")` | `ADMIN` | Không đạt | Đạt | Không đạt |
| `@WithMockUser(authorities = "ROLE_ADMIN")` | `ROLE_ADMIN` | Đạt | Không đạt | Đạt |
| `@WithMockUser(roles = "READER")` | `ROLE_READER` | Không đạt | Không đạt | Không đạt |
| `@WithMockUser` | `ROLE_USER` | Không đạt | Không đạt | Không đạt |

Trong method security, các biểu thức tương tự có thể xuất hiện ở `@PreAuthorize`:

```java
@PreAuthorize("hasRole('ADMIN')")
public void approveReport(long reportId) {
    // ...
}

@PreAuthorize("hasAuthority('report:approve')")
public void approveReportWithPermission(long reportId) {
    // ...
}
```

Với cách sử dụng mặc định, biểu thức đầu yêu cầu `ROLE_ADMIN`; biểu thức thứ hai chỉ yêu cầu `report:approve`. Nếu ứng dụng tùy biến cách ánh xạ role, cần kiểm tra cấu hình tương ứng trước khi kết luận về authority chính xác.

## 6. Ví dụ hoàn chỉnh với `MockMvc`: được phép và bị từ chối

Giả sử hệ thống quản lý báo cáo có hai endpoint:

- `GET /reports/{id}`: người có role `READER` hoặc `ADMIN` được đọc.
- `POST /reports/{id}/approve`: chỉ người có role `ADMIN` được phê duyệt.

Trong dự án Spring Boot có Spring MVC và Spring Security, bộ phụ thuộc kiểm thử cốt lõi gồm:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Ví dụ sau sử dụng Java 17+, Spring Security 6+ và JUnit 5. Đặt các lớp Java cùng package trong dự án; những import của từng lớp được thể hiện bên dưới.

### 6.1. Controller

```java
// ReportController.java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
class ReportController {

    @GetMapping("/{id}")
    String getReport(@PathVariable long id) {
        return "report-" + id;
    }

    @PostMapping("/{id}/approve")
    ResponseEntity<Void> approveReport(@PathVariable long id) {
        return ResponseEntity.noContent().build();
    }
}
```

### 6.2. Chính sách HTTP

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
    SecurityFilterChain reportFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/reports/*")
                    .hasAnyRole("READER", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/reports/*/approve")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        // Giữ CSRF mặc định: mọi POST hợp lệ cần token CSRF.
        return http.build();
    }
}
```

Ở đây `hasAnyRole("READER", "ADMIN")` yêu cầu `ROLE_READER` hoặc `ROLE_ADMIN`; `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`. `httpBasic()` giúp khách chưa đăng nhập nhận `401 Unauthorized` khi truy cập endpoint được bảo vệ. Các ứng dụng cấu hình form login có thể trả mã chuyển hướng, vì thế kỳ vọng HTTP phải phù hợp với cơ chế xác thực được sử dụng.

### 6.3. Kiểm thử annotation trên lớp và phương thức

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
@WithMockUser(username = "reader01", roles = "READER")
class ReportControllerSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readerHasRoleReaderAuthority() {
        Authentication authentication = SecurityContextHolder
                .getContext().getAuthentication();

        assertThat(authentication.getName()).isEqualTo("reader01");
        assertThat(authentication.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("ROLE_READER");
    }

    @Test
    void readerCanReadReport() throws Exception {
        mockMvc.perform(get("/reports/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("report-42"));
    }

    @Test
    void readerCannotApproveReport() throws Exception {
        mockMvc.perform(post("/reports/42/approve").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin01", roles = "ADMIN")
    void adminCanApproveReport() throws Exception {
        mockMvc.perform(post("/reports/42/approve").with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(username = "wrongAuthority", authorities = "ADMIN")
    void unprefixedAuthorityDoesNotMatchHasRole() throws Exception {
        mockMvc.perform(post("/reports/42/approve").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "explicitAuthority", authorities = "ROLE_ADMIN")
    void explicitlyPrefixedAuthorityMatchesHasRole() throws Exception {
        mockMvc.perform(post("/reports/42/approve").with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    @WithAnonymousUser
    void guestCannotReadReport() throws Exception {
        mockMvc.perform(get("/reports/42"))
                .andExpect(status().isUnauthorized());
    }
}
```

Annotation `@WithMockUser(roles = "READER")` trên lớp làm danh tính mặc định cho các ca không khai báo annotation khác. Ở ca `adminCanApproveReport`, annotation trên phương thức **ghi đè** annotation trên lớp; nó tạo `ROLE_ADMIN` và không cộng dồn `ROLE_READER`. Hai ca `wrongAuthority` và `explicitAuthority` giúp kiểm chứng trực tiếp việc có hay không có tiền tố `ROLE_`.

### 6.4. Bảng kết quả cần quan sát

| Trường hợp | Authority của người gọi | Request | Kỳ vọng |
| --- | --- | --- | --- |
| Reader đọc báo cáo | `ROLE_READER` | `GET /reports/42` | `200 OK` |
| Reader phê duyệt | `ROLE_READER` | `POST /reports/42/approve` + CSRF | `403 Forbidden` |
| Admin phê duyệt | `ROLE_ADMIN` | `POST /reports/42/approve` + CSRF | `204 No Content` |
| Có authority `ADMIN` | `ADMIN` | `POST /reports/42/approve` + CSRF | `403 Forbidden` |
| Có authority `ROLE_ADMIN` | `ROLE_ADMIN` | `POST /reports/42/approve` + CSRF | `204 No Content` |
| Khách ẩn danh | Không có danh tính đã xác thực | `GET /reports/42` | `401 Unauthorized` với HTTP Basic |

**Tại sao các ca POST đều gọi `.with(csrf())`?** Khi CSRF còn bật, request POST thiếu CSRF token có thể nhận `403` **ngay cả khi** người dùng có `ROLE_ADMIN`. Để chứng minh reader bị từ chối vì **thiếu role**, cần gửi CSRF token hợp lệ. `@WithMockUser` tự tạo danh tính nhưng **không tự cung cấp CSRF token cho request**.

Nếu bài test được cấu hình bỏ qua security filters hoặc không nạp chính sách HTTP của ứng dụng, những kỳ vọng trên có thể không còn ý nghĩa. Hãy xác nhận `SecurityFilterChain` đang được áp dụng cho `MockMvc`.

## 7. Đặt nhiều role và kiểm tra khi kết hợp

Một người dùng có thể mang nhiều role bằng cú pháp mảng:

```java
@Test
@WithMockUser(
    username = "linh",
    roles = {"READER", "APPROVER"}
)
void userHasBothRoleAuthorities() {
    Authentication auth = SecurityContextHolder.getContext()
            .getAuthentication();

    assertThat(auth.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder("ROLE_READER", "ROLE_APPROVER");
}
```

Quy tắc `hasAnyRole("READER", "APPROVER")` chấp nhận một trong hai role, trong khi yêu cầu **cả hai quyền** phải được diễn đạt thành điều kiện kết hợp rõ ràng, ví dụ `hasRole('READER') and hasRole('APPROVER')` ở method security. Không nên suy luận rằng `hasAnyRole` yêu cầu tất cả.

Đừng gộp nhiều ý nghĩa vào role chỉ để làm test đỗ. Nếu hệ thống cấp quyền nghiệp vụ chi tiết như `report:read`, `report:approve`, hãy dùng `authorities` và `hasAuthority` để bài test phản ánh đúng cơ chế cấp quyền đã thiết kế.

## 8. Tiền tố role khi cấu hình ứng dụng khác mặc định

Phần lớn dự án sử dụng tiền tố `ROLE_`. Tuy nhiên, một số ứng dụng có thể thay đổi cách diễn giải role ở từng cơ chế phân quyền, ví dụ cấu hình `GrantedAuthorityDefaults` cho phần method security hoặc dùng biểu thức tùy biến.

Điểm cần nhớ là **`@WithMockUser(roles = "ADMIN")` theo cơ chế chuẩn vẫn tạo `ROLE_ADMIN`**; annotation này không tự suy ra một tiền tố khác từ quy tắc phân quyền của ứng dụng. Nếu ứng dụng kiểm tra authority `ADMIN` hoặc `APP_ADMIN`, một test chỉ sử dụng `roles = "ADMIN"` có thể không phù hợp.

Khi đó nên khai báo authority theo giá trị thực sự mà cơ chế phân quyền yêu cầu:

```java
@WithMockUser(authorities = "ADMIN")
// Khi chính sách được cấu hình yêu cầu chuỗi "ADMIN".

@WithMockUser(authorities = "APP_ADMIN")
// Khi chính sách được cấu hình yêu cầu chuỗi "APP_ADMIN".
```

Các API cấu hình role prefix không nhất thiết ảnh hưởng giống nhau tới mọi dạng `hasRole` và biểu thức method security ở mọi phiên bản Spring Security. Vì vậy, thay vì đoán tên authority từ một chỗ cấu hình, hãy kiểm tra **chính quy tắc authorization đang được test** và danh sách authority sau khi bộ chuyển đổi danh tính chạy.

Nếu ứng dụng dùng **role hierarchy** (ví dụ `ADMIN` kế thừa `READER`), hạ tầng phân quyền có thể mở rộng quyền hiệu lực khi đánh giá. `@WithMockUser(roles = "ADMIN")` vẫn tạo authority gốc `ROLE_ADMIN`; việc được phép dùng endpoint `READER` khi chỉ có `ROLE_ADMIN` phụ thuộc vào role hierarchy được cấu hình và áp dụng trong cơ chế authorization tương ứng.

## 9. Ứng dụng Reactive với `WebTestClient`

Trong Spring WebFlux, ý nghĩa của `roles` và tiền tố `ROLE_` không đổi. `@WithMockUser(roles = "READER")` vẫn chuẩn bị một danh tính có authority `ROLE_READER`. Khác biệt chính là Spring Security Reactive truyền ngữ cảnh bảo mật qua **Reactor Context** thay vì chỉ dùng `SecurityContextHolder` trên luồng hiện tại.

Ví dụ khung kiểm thử trên WebFlux:

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
    @WithMockUser(roles = "READER")
    void readerCanFetchReport() {
        webTestClient.get()
                .uri("/reports/42")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    @WithMockUser(roles = "READER")
    void readerCannotApproveReport() {
        webTestClient.post()
                .uri("/reports/42/approve")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Đây là **khung minh họa**, với `ReactiveReportController` và `ReactiveReportSecurityConfig` là các lớp do ứng dụng cung cấp. Phải nạp `SecurityWebFilterChain` với chính sách tương ứng, áp dụng tích hợp Spring Security cho `WebTestClient`, và kiểm soát CSRF nếu muốn kết luận rằng ca POST trả `403` vì thiếu role. Với request đặc biệt, Spring Security Test cũng hỗ trợ `mutateWith(mockUser("lan").roles("ADMIN"))`; muốn kiểm chứng một request POST hợp lệ về CSRF có thể dùng `mutateWith(csrf())` khi client được tích hợp `springSecurity()`.

Ví dụ minh họa kết hợp ở mức request:

```java
webTestClient
    .mutateWith(mockUser("admin01").roles("ADMIN"))
    .mutateWith(csrf())
    .post()
    .uri("/reports/42/approve")
    .exchange()
    .expectStatus().isNoContent();
```

Hai hàm `mockUser` và `csrf` cho `WebTestClient` có trong `SecurityMockServerConfigurers`, và cấu trúc này giả định client đã được cấu hình đúng với Spring Security. Không nhầm các request post-processor của `MockMvc` với configurer của `WebTestClient`.

## 10. Khi quyền đến từ JWT, OAuth2 hoặc OIDC

Trong các hệ thống dùng Resource Server JWT, quyền có thể đến từ `scope`, `scp`, `roles` hoặc claim riêng. Spring Security có bộ chuyển đổi `JwtGrantedAuthoritiesConverter`; theo cấu hình mặc định thường gặp, scope được chuyển thành authority có tiền tố **`SCOPE_`**, ví dụ `SCOPE_reports.read`.

Do đó, `@WithMockUser(roles = "ADMIN")` tạo `ROLE_ADMIN` không chứng minh rằng một JWT ngoài thực tế cũng được ánh xạ thành `ROLE_ADMIN`. Người dùng trong test này có principal kiểu `User`, trong khi một `JwtAuthenticationToken` thường có principal kiểu `Jwt`.

Ví dụ khi ứng dụng dùng `hasAuthority("SCOPE_reports.read")`:

```java
@WithMockUser(authorities = "SCOPE_reports.read")
// Phù hợp để cô lập kiểm tra authorization theo authority.
```

Để kiểm chứng HTTP theo kiểu principal/token JWT, nên dùng mock JWT tương ứng:

```java
mockMvc.perform(get("/reports/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")
        )))
    .andExpect(status().isOk());
```

Đoạn này dùng `jwt()` từ `SecurityMockMvcRequestPostProcessors` và `SimpleGrantedAuthority` của Spring Security; cần cấu hình endpoint và Resource Server phù hợp. Mô phỏng JWT/OAuth2/OIDC cũng không thay thế cho bài test kiểm tra chữ ký, issuer, audience hoặc luồng trao đổi token thực tế.

## 11. Sai sót thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| `@WithMockUser(roles = "ROLE_ADMIN")` làm test lỗi từ lúc thiết lập context | Đã đưa tiền tố vào `roles` | Dùng `roles = "ADMIN"`, hoặc `authorities = "ROLE_ADMIN"` |
| Test có `authorities = "ADMIN"` nhưng `hasRole("ADMIN")` từ chối | Thiếu tiền tố `ROLE_` | Dùng `roles = "ADMIN"` hoặc `authorities = "ROLE_ADMIN"` |
| Test có `roles = "ADMIN"` nhưng `hasAuthority("ADMIN")` từ chối | Test có `ROLE_ADMIN`, policy tìm `ADMIN` | Dùng `authorities = "ADMIN"` hoặc sửa policy nếu quy ước role đã xác định |
| Trộn `roles` và `authorities` nhưng bị mất role | Khi `authorities` không rỗng, `roles` bị bỏ qua | Liệt kê đầy đủ trong `authorities` |
| `ADMIN` không được gọi endpoint của `READER` | Không có role hierarchy hoặc policy cho phép cả hai | Cấu hình `hasAnyRole`, hierarchy hoặc cấp cả hai role theo yêu cầu |
| POST thiếu quyền trả `403` ngay cả với `ADMIN` | Có thể thiếu CSRF token | Cung cấp CSRF hợp lệ trước khi kiểm chứng role |
| Không nhận được `401` như kỳ vọng khi chưa đăng nhập | Cơ chế xác thực đang chuyển hướng tới login | Kiểm tra cấu hình HTTP Basic, form login hoặc entry point |
| Test JWT đỗ với `@WithMockUser` nhưng production không có quyền | Danh tính giả không đi qua bộ chuyển đổi claim JWT | Viết test riêng với `jwt()`, `mockJwt()` hoặc test tích hợp phù hợp |
| `@WithMockUser` không có hiệu lực trong test thuần JUnit | Thiếu hạ tầng Spring Test/listener | Dùng test slice Spring Boot hoặc `SpringExtension` với cấu hình cần thiết |

Khi gặp lỗi `403`, đừng chỉ thử đổi role ngẫu nhiên. Hãy truy nguyên ba dữ kiện: **authority thực tế của người gọi**, **authority mà chính sách yêu cầu**, và **bộ lọc có chặn request vì CSRF hay lý do khác không**. Ba dữ kiện này thường chỉ ra đúng nguyên nhân.

## 12. Bài tập vận dụng

Giả sử ứng dụng có chính sách:

- `GET /invoices/{id}`: cho `ACCOUNTANT` hoặc `ADMIN`.
- `POST /invoices/{id}/close`: chỉ cho `ADMIN`, yêu cầu CSRF.
- `GET /invoices/audit`: yêu cầu authority `invoice:audit`, không kiểm tra role.

Hãy hoàn thành các nhiệm vụ sau:

1. Viết test với `@WithMockUser(roles = "ACCOUNTANT")` và kiểm tra authority thật trong `SecurityContext`, sau đó gọi `GET /invoices/7` và `POST /invoices/7/close`.
2. Viết test với `@WithMockUser(roles = "ADMIN")`. Giải thích tại sao yêu cầu `hasRole("ADMIN")` khớp với authority đã được tạo.
3. Viết một test với `@WithMockUser(authorities = "ADMIN")`. Dự đoán kết quả khi gọi endpoint yêu cầu `hasRole("ADMIN")` và giải thích trước khi chạy.
4. Viết một test cho `GET /invoices/audit` với `@WithMockUser(authorities = "invoice:audit")`; kiểm chứng rằng quyền này không cần tiền tố `ROLE_`.
5. Gộp `ROLE_ADMIN` và `invoice:audit` vào **một** người dùng giả bằng `authorities`, rồi xác minh cả hai loại endpoint.
6. Tạo ca chưa đăng nhập với `@WithAnonymousUser`; kiểm tra phản hồi theo cơ chế xác thực của ứng dụng.

**Gợi ý đáp án quan trọng:** ở câu 3, `authorities = "ADMIN"` chỉ tạo authority `ADMIN`, vì vậy không khớp với `hasRole("ADMIN")` theo quy ước mặc định. Ở câu 5, dùng `@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:audit"})` để khai báo chính xác cả hai.

## 13. Ghi nhớ

`@WithMockUser(roles = "ADMIN")` tạo **`ROLE_ADMIN`**, vì Spring Security Test tự thêm tiền tố `ROLE_`. Trong khi đó, `@WithMockUser(authorities = "ADMIN")` giữ nguyên authority `ADMIN`. `hasRole("ADMIN")` mặc định kiểm tra `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` kiểm tra đúng chuỗi `ADMIN`. Khi kiểm thử bằng `MockMvc` hoặc `WebTestClient`, phải bảo đảm security chain thực sự chạy, cung cấp CSRF cho các request cần token, và phân biệt authority do người dùng giả tạo ra với authority được ánh xạ từ JWT/OAuth2/OIDC trong hệ thống thật.
