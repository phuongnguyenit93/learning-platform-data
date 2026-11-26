# Annotation tổng hợp để dùng lại một danh tính kiểm thử

## 1. Vì sao nên tạo annotation tổng hợp?

Trong một module có nhiều bài kiểm thử bảo mật, cùng một số danh tính thường xuất hiện lặp đi lặp lại: người đọc báo cáo, quản trị viên, nhân viên hỗ trợ hoặc khách chưa đăng nhập. Nếu mỗi phương thức đều khai báo lại `@WithMockUser(username = "...", roles = "...")`, test sẽ dài và dễ lệch nhau khi tên quyền hoặc quy ước dữ liệu thay đổi.

Spring Security Test cho phép **tổng hợp annotation** bằng cách đặt `@WithMockUser` trên một annotation do dự án định nghĩa. Annotation mới trở thành một cách đặt tên cho persona kiểm thử, ví dụ `@WithReportReader` hoặc `@WithReportAdmin`. Khi cần, có thể dùng `@AliasFor` để mở một vài thuộc tính như username cho người viết test thay đổi.

Bài học thuộc chương **Annotation người dùng** của module **SPRING_SECURITY_TESTING**. Module tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive; người học sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và các ca được phép hoặc bị từ chối.

Sau bài này, bạn có thể:

- Tạo annotation tổng hợp từ `@WithMockUser` để dùng lại một danh tính kiểm thử.
- Dùng `@AliasFor` để cho phép tùy chỉnh username mà vẫn giữ role mặc định.
- Đặt annotation tổng hợp ở cấp lớp hoặc phương thức và hiểu quy tắc ghi đè.
- Kết hợp persona dùng chung với `@WithAnonymousUser` hoặc persona khác.
- Phân biệt annotation tổng hợp với `@WithUserDetails`, request post-processor và `@WithSecurityContext`.
- Dùng cùng một persona trong các test Servlet và Reactive khi context test được cấu hình phù hợp.

## 2. Annotation tổng hợp là gì?

Trong Spring, một annotation có thể được đặt trên một annotation khác để tạo thành **meta-annotation**. Spring Test tìm annotation bảo mật thông qua cơ chế hợp nhất annotation, vì vậy annotation tự định nghĩa có thể mang theo `@WithMockUser` và được xử lý như một nguồn cấu hình security context.

Ví dụ tối giản:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithMockUser(username = "report-reader", roles = "READER")
public @interface WithReportReader {
}
```

Sau khi tạo annotation, test có thể viết:

```java
@Test
@WithReportReader
void readerCanOpenReport() {
    // Có danh tính report-reader và authority ROLE_READER.
}
```

So với việc khai báo lặp lại `@WithMockUser`, tên `@WithReportReader` diễn đạt trực tiếp vai trò nghiệp vụ của test. Nếu quy ước username hoặc role của persona thay đổi, có thể cập nhật ở một nơi.

### Những metadata cần có

| Annotation | Vai trò |
| --- | --- |
| `@Retention(RetentionPolicy.RUNTIME)` | Giữ annotation ở runtime để Spring Test có thể đọc |
| `@Target({METHOD, TYPE})` | Cho phép đặt ở phương thức và lớp kiểm thử |
| `@WithMockUser(...)` | Cấu hình danh tính và authorities được tổng hợp |
| `@Documented` | Cho annotation xuất hiện trong tài liệu API |
| `@Inherited` | Có thể cho phép annotation cấp lớp được kế thừa theo cơ chế Java annotation |

`@Documented` và `@Inherited` không phải điều kiện bắt buộc để meta-annotation hoạt động. Thêm `@Inherited` khi dự án muốn biểu đạt rõ việc annotation trên lớp cha có thể được kế thừa; vẫn cần kiểm tra cách Spring Test tìm annotation trên hệ thống lớp test thực tế.

## 3. Tạo persona dùng chung cho người đọc báo cáo

Một annotation tổng hợp có thể cố định username và role:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.test.context.support.WithMockUser;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithMockUser(
    username = "report-reader",
    roles = "READER"
)
public @interface WithReportReader {
}
```

Với annotation này:

```java
@Test
@WithReportReader
void readerHasExpectedAuthority() {
    Authentication authentication = SecurityContextHolder.getContext()
            .getAuthentication();

    assertThat(authentication.getName()).isEqualTo("report-reader");
    assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactly("ROLE_READER");
}
```

`roles = "READER"` tạo authority `ROLE_READER` theo quy ước mặc định của `@WithMockUser`. Annotation tổng hợp không tạo một kiểu principal mới; principal vẫn là `org.springframework.security.core.userdetails.User` của Spring Security.

Có thể định nghĩa persona quản trị tương tự:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithMockUser(
    username = "report-admin",
    roles = "ADMIN"
)
public @interface WithReportAdmin {
}
```

Như vậy, các test dùng `@WithReportReader` hoặc `@WithReportAdmin` thể hiện rõ danh tính nghiệp vụ và không phải lặp lại tên người dùng hay role.

## 4. Mở thuộc tính username bằng @AliasFor

Đôi khi muốn dùng chung role nhưng mỗi test cần một username khác. `@AliasFor` cho phép một thuộc tính của annotation tổng hợp ánh xạ tới thuộc tính của meta-annotation.

```java
import org.springframework.core.annotation.AliasFor;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithMockUser(roles = "READER")
public @interface WithReportReader {

    @AliasFor(annotation = WithMockUser.class, attribute = "username")
    String username() default "";
}
```

Ở đây `username` của annotation tổng hợp là alias cho `username` của `@WithMockUser`. Giá trị mặc định rỗng khớp với mặc định của thuộc tính meta-annotation; nếu không truyền username, `@WithMockUser` vẫn áp dụng cơ chế mặc định của nó. Khi cần tên riêng:

```java
@Test
@WithReportReader(username = "mai")
void maiCanReadReport() {
    // username = mai, authority ROLE_READER.
}
```

Một lưu ý quan trọng: `@AliasFor` cần khai báo đúng annotation đích và tên thuộc tính; các alias và giá trị mặc định phải nhất quán với meta-annotation. Nếu không cần tùy chỉnh thuộc tính, hãy dùng annotation cố định đơn giản ở phần trước để giảm độ phức tạp.

### Không tự tạo alias cho mọi thuộc tính

Chỉ mở các thuộc tính có ý nghĩa với người viết test. Ví dụ, một persona `WithReportReader` nên giữ role `READER` cố định để không biến nó thành một annotation tổng quát khó hiểu. Nếu cần role khác, tạo persona riêng hoặc dùng annotation tổng hợp khác.

Nếu annotation tổng hợp đặt `roles = "READER"` trên `@WithMockUser`, không nên đồng thời mở `authorities` tùy ý mà không quy định rõ quan hệ giữa chúng. Khi `authorities` không rỗng, thuộc tính này được ưu tiên thay cho `roles`; người đọc có thể tưởng annotation vẫn mang `ROLE_READER` trong khi test đã thay bằng authority khác.

## 5. Đặt annotation tổng hợp ở cấp lớp và phương thức

Annotation tổng hợp có thể đặt trên lớp để làm persona mặc định cho cả nhóm test:

```java
@WebMvcTest(ReportController.class)
@Import(ReportSecurityConfig.class)
@WithReportReader
class ReportControllerSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readerCanRead() throws Exception {
        mockMvc.perform(get("/reports"))
                .andExpect(status().isOk());
    }

    @Test
    @WithReportAdmin
    void adminCanApprove() throws Exception {
        mockMvc.perform(post("/reports/approve").with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    @WithAnonymousUser
    void guestCannotReadPrivateReport() throws Exception {
        mockMvc.perform(get("/reports"))
                .andExpect(status().isUnauthorized());
    }
}
```

Quy tắc giống annotation bảo mật thông thường:

- Phương thức không có annotation bảo mật riêng sử dụng persona ở cấp lớp.
- Annotation ở phương thức ghi đè persona ở cấp lớp.
- `@WithReportAdmin` tạo người dùng admin cho đúng phương thức.
- `@WithAnonymousUser` thay thế người đọc mặc định bằng anonymous authentication.
- Các danh tính không cộng dồn. Phương thức admin không tự mang `ROLE_READER` từ lớp.

| Annotation trên lớp | Annotation trên phương thức | Danh tính có hiệu lực |
| --- | --- | --- |
| `@WithReportReader` | Không có | Người đọc báo cáo |
| `@WithReportReader` | `@WithReportAdmin` | Quản trị viên |
| `@WithReportReader` | `@WithAnonymousUser` | Khách ẩn danh |
| `@WithReportReader` | `@WithReportReader(username = "mai")` | Người đọc có username `mai` |

Nếu một phương thức có nhiều annotation tổng hợp cùng thiết lập security context, không nên giả định Spring sẽ kết hợp chúng theo cách mong muốn. Hãy chọn một persona rõ ràng cho mỗi test method.

## 6. Ví dụ hoàn chỉnh với MockMvc

Ta kiểm tra hai endpoint:

- `GET /reports`: yêu cầu `ROLE_READER`.
- `POST /reports/approve`: yêu cầu `ROLE_ADMIN` và CSRF hợp lệ.

### 6.1. Controller

```java
import org.springframework.security.core.Authentication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/reports")
    String readReports() {
        return "reports";
    }

    @GetMapping("/reports/me")
    String currentUser(Authentication authentication) {
        return authentication.getName();
    }

    @PostMapping("/reports/approve")
    ResponseEntity<Void> approve() {
        return ResponseEntity.noContent().build();
    }
}
```

### 6.2. SecurityFilterChain

```java
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
                .requestMatchers(HttpMethod.GET, "/reports/me")
                    .hasRole("READER")
                .requestMatchers(HttpMethod.GET, "/reports")
                    .hasRole("READER")
                .requestMatchers(HttpMethod.POST, "/reports/approve")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

CSRF vẫn được bật mặc định; request POST cần token hợp lệ.

### 6.3. Persona tổng hợp

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.core.annotation.AliasFor;
import org.springframework.security.test.context.support.WithMockUser;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithMockUser(roles = "READER")
public @interface WithReportReader {

    @AliasFor(annotation = WithMockUser.class, attribute = "username")
    String username() default "";
}
```

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithMockUser(username = "report-admin", roles = "ADMIN")
public @interface WithReportAdmin {
}
```

### 6.4. Test

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.security.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReportController.class)
@Import(ReportSecurityConfig.class)
@WithReportReader(username = "mai")
class ReportControllerSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void classPersonaCanReadReport() throws Exception {
        Authentication authentication = SecurityContextHolder.getContext()
                .getAuthentication();
        assertThat(authentication.getName()).isEqualTo("mai");
        assertThat(authentication.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("ROLE_READER");

        mockMvc.perform(get("/reports"))
                .andExpect(status().isOk())
                .andExpect(content().string("reports"));
    }

    @Test
    void aliasCanSupplyDifferentUsername() throws Exception {
        mockMvc.perform(get("/reports/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("mai"));
    }

    @Test
    @WithReportAdmin
    void methodPersonaOverridesClassReader() throws Exception {
        mockMvc.perform(post("/reports/approve").with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    @WithAnonymousUser
    void anonymousPersonaOverridesClassReader() throws Exception {
        mockMvc.perform(get("/reports"))
                .andExpect(status().isUnauthorized());
    }
}
```

Trong test trên, `@WithReportReader(username = "mai")` trên lớp tạo danh tính mặc định. Test `methodPersonaOverridesClassReader` sử dụng `@WithReportAdmin` nên nhận `ROLE_ADMIN`, còn test anonymous sử dụng `AnonymousAuthenticationToken`. Request POST có `.with(csrf())` để kết quả thành công hoặc bị từ chối phản ánh chính sách role thay vì thiếu CSRF.

### 6.5. Kết quả mong đợi

| Test | Persona hiệu lực | Request | Kết quả |
| --- | --- | --- | --- |
| `classPersonaCanReadReport` | `mai / ROLE_READER` | `GET /reports` | `200 OK` |
| `aliasCanSupplyDifferentUsername` | `mai / ROLE_READER` | `GET /reports/me` | `200 OK` |
| `methodPersonaOverridesClassReader` | `report-admin / ROLE_ADMIN` | `POST /reports/approve` + CSRF | `204 No Content` |
| `anonymousPersonaOverridesClassReader` | Anonymous | `GET /reports` | `401 Unauthorized` với HTTP Basic |

Nếu ứng dụng dùng form login thay cho HTTP Basic, khách chưa xác thực có thể nhận `302` chuyển hướng. Hãy đặt kỳ vọng theo entry point của cấu hình thực tế.

## 7. Tạo persona dựa trên UserDetailsService

Annotation tổng hợp không bắt buộc phải dùng `@WithMockUser`. Có thể meta-annotate `@WithUserDetails` để dùng lại một người dùng do service tải:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithUserDetails(
    value = "report-reader",
    userDetailsServiceBeanName = "accountDetailsService"
)
public @interface WithStoredReportReader {
}
```

Khi dùng `@WithStoredReportReader`, Spring Test vẫn gọi `UserDetailsService.loadUserByUsername("report-reader")`. Do đó:

- Bean `accountDetailsService` phải có trong ApplicationContext.
- Username phải tồn tại trước thời điểm annotation được xử lý.
- Principal và authorities là những gì service trả về.
- Nếu fixture được tạo trong `@BeforeEach`, cân nhắc `setupBefore = TestExecutionEvent.TEST_EXECUTION` trên `@WithUserDetails` được tổng hợp.

Đây là cách tạo persona dùng chung khi cần principal tùy chỉnh hoặc dữ liệu người dùng được quản lý bởi ứng dụng. Nó không kiểm tra mật khẩu qua `AuthenticationManager`.

## 8. Khi nào cần @WithSecurityContext thay vì meta-annotation?

Meta-annotate `@WithMockUser` hoặc `@WithUserDetails` là đủ cho phần lớn persona kiểm thử. Nếu danh tính cần dữ liệu hoặc cách tạo phức tạp hơn, dùng `@WithSecurityContext`:

| Nhu cầu | Lựa chọn |
| --- | --- |
| Persona cố định, chỉ có username và role | Annotation tổng hợp từ `@WithMockUser` |
| Persona cùng role nhưng username có thể đổi | Meta-annotation + `@AliasFor` |
| Principal do service của ứng dụng tải | Annotation tổng hợp từ `@WithUserDetails` |
| Principal chứa `tenantId`, `accountId` và dữ liệu tùy biến | `@WithSecurityContext` và factory riêng, hoặc `UserDetails` tùy chỉnh |
| Principal JWT | `jwt()`/`mockJwt()` hoặc context factory thích hợp |
| OAuth2/OIDC user | `oauth2Login()`/`oidcLogin()` hoặc factory phù hợp |
| Danh tính khác nhau trên từng request trong cùng test | Request post-processor như `user(...)` hoặc configurer của `WebTestClient` |

Không nên viết factory riêng nếu một meta-annotation đơn giản đã mô tả đủ persona. Factory có ích khi phải tạo nhiều trường, authentication token đặc biệt, hoặc kết hợp dữ liệu từ nhiều thuộc tính.

## 9. Tái sử dụng persona trong WebTestClient

Trong WebFlux, các annotation tổng hợp dựa trên `@WithMockUser` vẫn có thể được sử dụng trong test khi Spring Security Test và Reactor context được tích hợp đúng. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@WebFluxTest(ReactiveReportController.class)
@Import(ReactiveReportSecurityConfig.class)
@WithReportReader
class ReactiveReportSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readerCanFetchReport() {
        webTestClient.get()
                .uri("/reports")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    @WithReportAdmin
    void adminPersonaOverridesReader() {
        webTestClient
                .mutateWith(csrf())
                .post()
                .uri("/reports/approve")
                .exchange()
                .expectStatus().isNoContent();
    }
}
```

Đây là khung minh họa: `ReactiveReportController` và `ReactiveReportSecurityConfig` phải do ứng dụng cung cấp, và client cần tích hợp Spring Security. Request POST thêm CSRF hợp lệ để kết quả thành công phản ánh quyền ADMIN thay vì chỉ phản ánh việc vượt qua bộ lọc CSRF. Hàm `csrf()` được cung cấp bởi `SecurityMockServerConfigurers`.

Persona tổng hợp chỉ thiết lập security context; nó không tự cấu hình `SecurityWebFilterChain` hoặc biến ứng dụng Servlet thành Reactive. Khi endpoint cần JWT, dùng `mockJwt()`; khi cần OAuth2/OIDC, chọn configurer tương ứng.

## 10. Tổ chức annotation tổng hợp trong dự án

Khi số lượng persona tăng, nên đặt chúng trong package test dùng chung, ví dụ:

```text
src/test/java/com/example/security/testsupport/
    WithReportReader.java
    WithReportAdmin.java
    WithSupportAgent.java
    WithStoredReportReader.java
```

Quy ước tổ chức:

- Tên annotation bắt đầu bằng `With` để thể hiện đây là danh tính/context cho test.
- Tên mô tả nghiệp vụ, ví dụ `WithReportReader`, không dùng tên chung chung như `WithUser1`.
- Role và authority của persona phải ổn định, dễ nhận biết.
- Chỉ expose thuộc tính qua `@AliasFor` khi test thực sự cần tùy chỉnh.
- Dùng package test support chung nếu nhiều module test cần tái sử dụng; tránh đưa annotation chỉ dành cho test vào mã production.
- Nếu persona phụ thuộc service hoặc fixture, ghi rõ yêu cầu về ApplicationContext và dữ liệu.

Annotation tổng hợp không phải nơi để giấu chính sách phức tạp. Khi tên persona không còn phản ánh rõ quyền thực tế, hãy tách persona hoặc viết test diễn đạt trực tiếp điều kiện.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Spring Test không nhận annotation tổng hợp | Thiếu `@Retention(RUNTIME)` hoặc meta-annotation không được đặt đúng | Kiểm tra retention, target và `@WithMockUser` |
| `@AliasFor` báo lỗi khi tạo merged annotation | Sai annotation đích, tên thuộc tính hoặc default không nhất quán | Kiểm tra alias với thuộc tính meta-annotation tương ứng |
| Persona có username mặc định ngoài dự kiến | Không cấu hình username hoặc alias không được ánh xạ | Kiểm tra `value`/`username` của `@WithMockUser` |
| Authority không đúng | Meta-annotation đặt role khác hoặc khai báo `authorities` ghi đè `roles` | Assert danh sách `GrantedAuthority` |
| Method test vẫn dùng persona cấp lớp | Annotation phương thức chưa được nhận diện hoặc không phải annotation security | Kiểm tra meta-annotation và target |
| Phương thức admin vẫn bị từ chối | Persona admin thiếu role/authority cần thiết hoặc thiếu CSRF | Kiểm tra context và request token |
| Test anonymous vẫn nhận quyền người đọc | Không đặt `@WithAnonymousUser` trên phương thức | Thêm annotation ghi đè |
| Annotation tổng hợp không có principal tùy chỉnh | `@WithMockUser` vẫn tạo principal `User` mặc định | Dùng `@WithUserDetails` hoặc `@WithSecurityContext` |
| Test WebFlux không thấy context | Thiếu tích hợp Reactive Security Test | Cấu hình `WebTestClient` và Reactor Context |

Khi test thất bại, kiểm tra theo thứ tự: annotation tổng hợp có được phát hiện không, thuộc tính alias đã hợp nhất đúng chưa, danh sách authority thực tế là gì, và request có đi qua security chain/CSRF cần thiết không.

## 12. Bài tập vận dụng

Ứng dụng báo cáo có ba persona:

- Người đọc: `ROLE_READER`.
- Người phê duyệt: `ROLE_APPROVER`.
- Quản trị viên: `ROLE_ADMIN`.

Các endpoint:

- `GET /reports` yêu cầu `ROLE_READER`.
- `POST /reports/approve` yêu cầu `ROLE_APPROVER` và CSRF.
- `GET /admin/reports` yêu cầu `ROLE_ADMIN`.

Hãy thực hiện:

1. Tạo ba annotation tổng hợp `@WithReportReader`, `@WithReportApprover`, `@WithReportAdmin`.
2. Tạo `@WithReportReader(username = "mai")` bằng `@AliasFor); xác nhận username đổi nhưng role vẫn là `READER`.
3. Đặt `@WithReportReader` ở cấp lớp, sau đó ghi đè một phương thức bằng `@WithReportApprover`.
4. Thêm `@WithAnonymousUser` cho một phương thức và xác nhận danh tính ẩn danh thay thế persona cấp lớp.
5. Kiểm tra authorities trong `SecurityContext` trước khi gửi request.
6. Cung cấp CSRF hợp lệ cho POST để phân biệt lỗi CSRF với lỗi thiếu role.
7. Tạo annotation tổng hợp từ `@WithUserDetails` nếu ứng dụng cần principal do service tải.
8. Giải thích khi nào cần chuyển sang `@WithSecurityContext` thay vì tiếp tục thêm thuộc tính vào annotation tổng hợp.

**Câu hỏi tự kiểm tra:** Nếu lớp có `@WithReportReader` và phương thức có `@WithReportAdmin`, phương thức đó có cả `ROLE_READER` lẫn `ROLE_ADMIN` không? **Không.** Annotation bảo mật ở phương thức ghi đè danh tính ở lớp; nếu cần cả hai authority, hãy khai báo rõ cả hai trong một persona hoặc một annotation tổng hợp thích hợp.

## 13. Ghi nhớ

Annotation tổng hợp giúp đặt tên và tái sử dụng persona kiểm thử bằng cách meta-annotate `@WithMockUser` hoặc `@WithUserDetails`. Dùng `@AliasFor` khi cần mở một thuộc tính như username; giữ các giá trị mặc định nhất quán với meta-annotation. Có thể đặt persona ở cấp lớp và ghi đè bằng persona khác hoặc `@WithAnonymousUser` ở cấp phương thức. Khi cần principal hoặc authentication phức tạp, dùng `@WithSecurityContext` và factory riêng. Dù dùng annotation tổng hợp nào, hãy kiểm tra authority thực tế và bảo đảm request đi qua security chain phù hợp trên `MockMvc` hoặc `WebTestClient`.
