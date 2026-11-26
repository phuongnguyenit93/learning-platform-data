# Authentication.isAuthenticated khác với quyền thực hiện một hành động

Một đối tượng `Authentication` có thể trả về `isAuthenticated() == true` nhưng vẫn không được phép đọc báo cáo, xuất dữ liệu hoặc gọi một phương thức nghiệp vụ. Điều này không mâu thuẫn: `isAuthenticated()` trên Java interface mô tả trạng thái tin cậy của **token xác thực**, còn quyền thực hiện hành động được quyết định bởi **authorization** dựa trên chính sách và authorities.

Sự nhầm lẫn này thường xuất hiện trong bài kiểm thử Spring Security. Người học thấy `@WithMockUser` tạo một authentication có `isAuthenticated()` là `true` rồi kết luận người dùng phải được truy cập. Nhưng một người dùng đã xác thực vẫn có thể thiếu `ROLE_ADMIN` hoặc `report:export` và bị từ chối. Ngược lại, `AnonymousAuthenticationToken` cũng thường trả `true` ở Java API, nhưng được Spring Security nhận diện là anonymous.

Bài học thuộc chương **Ngữ cảnh và vòng đời** của module **SPRING_SECURITY_TESTING**, tập trung vào cách đọc trạng thái authentication, phân biệt nó với quyết định authorization và viết kiểm thử được phép/bị từ chối bằng `@WithMockUser`, method security, `MockMvc` và `WebTestClient`.

## 1. Authentication biểu diễn điều gì?

`Authentication` là một đối tượng bảo mật chứa thông tin về principal, credentials, authorities và trạng thái xác thực. Một cách nhìn khái quát:

| Thành phần | Ý nghĩa |
| --- | --- |
| `getPrincipal()` | Danh tính hoặc đối tượng đại diện cho người dùng/chủ thể |
| `getCredentials()` | Thông tin chứng minh danh tính, ví dụ password hoặc credential khác; có thể được xóa sau xác thực |
| `getAuthorities()` | Các quyền/nhãn quyền mà chủ thể được cấp |
| `getDetails()` | Thông tin bổ sung của request hoặc quá trình xác thực |
| `isAuthenticated()` | Token hiện được đánh dấu là đã xác thực/được tin cậy trong mô hình Authentication |

`Authentication` không tự mô tả toàn bộ chính sách của ứng dụng. Nó không tự biết endpoint nào yêu cầu `ROLE_ADMIN`, báo cáo nào chỉ cho phép người sở hữu, hay thao tác xuất file có bị cấm trong tenant hiện tại hay không. Những quyết định đó thuộc authorization.

Một `SecurityContext` có thể chứa authentication:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();

if (authentication == null) {
    // Chưa có Authentication trong context hiện tại.
} else {
    String principalName = authentication.getName();
    Collection<? extends GrantedAuthority> authorities =
            authentication.getAuthorities();
    boolean tokenTrusted = authentication.isAuthenticated();
}
~~~

Giá trị boolean ở đây chỉ là một thuộc tính của đối tượng token. Không nên đổi tên nó thành `hasPermission` hoặc dùng nó như kết luận cuối cùng về quyền truy cập.

## 2. isAuthenticated() trên Java Authentication là trạng thái của token

Một ví dụ dễ quan sát là `UsernamePasswordAuthenticationToken`. Lớp này có constructor dành cho trạng thái chưa xác thực và constructor dành cho trạng thái đã xác thực:

~~~java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

Authentication unauthenticated =
        new UsernamePasswordAuthenticationToken("lan", "secret");

assertThat(unauthenticated.isAuthenticated()).isFalse();

Authentication authenticated =
        new UsernamePasswordAuthenticationToken(
                "lan",
                "N/A",
                AuthorityUtils.createAuthorityList("ROLE_READER"));

assertThat(authenticated.isAuthenticated()).isTrue();
assertThat(authenticated.getAuthorities())
        .extracting("authority")
        .contains("ROLE_READER");
~~~

Constructor hai tham số tạo token chưa được xác thực. Constructor có danh sách authorities tạo token ở trạng thái đã xác thực. Đây là cách biểu diễn hai trạng thái khác nhau của cùng loại token, không phải hai mức quyền truy cập.

Trong luồng đăng nhập thật, một `AuthenticationManager` nhận authentication chưa xác thực, chuyển tới provider phù hợp để kiểm tra credential, rồi trả về authentication đã được xác thực cùng authorities. Ứng dụng không nên tự tạo token “đã xác thực” từ dữ liệu người dùng nhập vào để thay thế bước kiểm tra password, chữ ký token hoặc cơ chế credential tương ứng.

Với `UsernamePasswordAuthenticationToken`, việc gọi `setAuthenticated(true)` trực tiếp không phải cách để hoàn tất đăng nhập; API bảo vệ việc chuyển token chưa tin cậy sang tin cậy. Hãy để provider/authentication manager tạo token thành công, hoặc trong test chủ động dùng cơ chế mock đã được thiết kế cho việc đó.

## 3. Vì sao token isAuthenticated=true vẫn có thể bị từ chối?

Authorization kiểm tra xem chủ thể có đủ quyền để thực hiện **hành động cụ thể trên tài nguyên cụ thể** hay không. Spring Security thường dùng các thành phần như `AuthorizationManager` cho request authorization và method authorization. Chính sách có thể dựa trên:

- Authorities trong `Authentication`, ví dụ `ROLE_READER` hoặc `report:export`.
- Vai trò được ánh xạ qua `hasRole(...)`.
- Điều kiện trên principal, tham số phương thức hoặc dữ liệu nghiệp vụ.
- Quan hệ sở hữu tài nguyên, tenant, trạng thái bản ghi hoặc quy tắc do ứng dụng định nghĩa.

Ví dụ, `lan` có token đã xác thực nhưng chỉ có `ROLE_READER`:

~~~java
Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "lan",
                "N/A",
                AuthorityUtils.createAuthorityList("ROLE_READER"));

assertThat(authentication.isAuthenticated()).isTrue();
assertThat(authentication.getAuthorities())
        .extracting("authority")
        .doesNotContain("ROLE_ADMIN");
~~~

Nếu endpoint yêu cầu `hasRole("ADMIN")`, người dùng này bị từ chối. Điều đó hoàn toàn hợp lý: danh tính đã được xác nhận, nhưng quyền thực hiện thao tác quản trị không được cấp.

Một ma trận ngắn:

| Authentication | Chính sách | Kết quả |
| --- | --- | --- |
| Đã xác thực, có `ROLE_READER` | `hasRole("READER")` | Cho phép |
| Đã xác thực, có `ROLE_READER` | `hasRole("ADMIN")` | Từ chối |
| Đã xác thực, có `report:read` | `hasAuthority("report:read")` | Cho phép |
| Đã xác thực, chỉ có `report:read` | `hasAuthority("report:export")` | Từ chối |
| Anonymous token | `authenticated()` | Không được xem là người dùng đã đăng nhập đầy đủ |
| Authentication chưa xác thực | Quy tắc yêu cầu người dùng đã đăng nhập | Không đáp ứng |

## 4. Phân biệt Java authentication.isAuthenticated() với biểu thức SpEL isAuthenticated()

Đây là điểm rất dễ nhầm vì tên gọi giống nhau.

**Java API:**

~~~java
authentication.isAuthenticated()
~~~

Đọc cờ trạng thái trên đối tượng `Authentication` cụ thể. Anonymous token và remember-me token cũng có thể có cờ này là `true`.

**Biểu thức authorization của Spring Security:**

~~~java
@PreAuthorize("isAuthenticated()")
~~~

Hoặc:

~~~java
.requestMatchers("/api/private/**").authenticated()
~~~

Đây là biểu thức/quy tắc bảo mật. Với expression-based authorization, `isAuthenticated()` được đánh giá theo cơ chế trust resolver của Spring Security, để phân biệt người dùng anonymous với người dùng được xác thực. Nó không chỉ gọi trực tiếp Java boolean rồi coi anonymous token là người đăng nhập.

Một số biểu thức thường gặp:

| Biểu thức bảo mật | Ý nghĩa |
| --- | --- |
| `permitAll()` | Không yêu cầu người dùng đăng nhập |
| `denyAll()` | Từ chối mọi người dùng |
| `isAnonymous()` | Chủ thể hiện tại được nhận diện là anonymous |
| `isAuthenticated()` | Chủ thể được xác thực, không phải anonymous |
| `isRememberMe()` | Chủ thể đăng nhập bằng remember-me |
| `isFullyAuthenticated()` | Không phải anonymous và cũng không phải remember-me |
| `hasAuthority("report:read")` | Có authority chính xác `report:read` |
| `hasRole("ADMIN")` | Có role `ROLE_ADMIN` theo role prefix mặc định |

`isAuthenticated()` trong SpEL và `Authentication.isAuthenticated()` trong Java là hai phép kiểm tra khác nhau. Khi viết code nghiệp vụ hoặc test, hãy nêu rõ đang kiểm tra trạng thái token hay đang đánh giá biểu thức authorization.

Có thể thấy rõ khác biệt với anonymous token:

~~~java
Authentication anonymous =
        new AnonymousAuthenticationToken(
                "test-key",
                "anonymousUser",
                AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS"));

AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

assertThat(anonymous.isAuthenticated()).isTrue();
assertThat(trustResolver.isAnonymous(anonymous)).isTrue();
~~~

Java token báo trạng thái của nó là authenticated, nhưng trust resolver vẫn phân loại chủ thể là anonymous. Đây là lý do biểu thức authorization không nên được thay bằng một phép đọc boolean thô.

## 5. Authorities không tự động đồng nghĩa với quyền trên mọi tài nguyên

Một authority là dữ liệu quyền gắn với authentication. Quy tắc authorization mới xác định authority nào cần có và trong hoàn cảnh nào.

Ví dụ:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}

@Service
class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public Report readReport(String reportId) {
        // Đọc báo cáo.
        return loadReport(reportId);
    }

    @PreAuthorize("hasAuthority('report:export')")
    public byte[] exportReport(String reportId) {
        // Xuất báo cáo.
        return createExport(reportId);
    }
}
~~~

Người có `report:read` có thể đọc nhưng không nhất thiết được xuất. Nếu chỉ kiểm tra `authentication.isAuthenticated()`, code sẽ bỏ qua sự khác biệt giữa hai hành động.

Role cũng là một quy ước ánh xạ. Với prefix mặc định, `hasRole("ADMIN")` tương đương kiểm tra authority `ROLE_ADMIN`. `hasAuthority("ROLE_ADMIN")` kiểm tra chuỗi authority trực tiếp. Nếu ứng dụng dùng permission theo hành động như `report:read`, `report:export`, hãy dùng `hasAuthority` để diễn đạt đúng chính sách.

Trong nhiều hệ thống, quyền truy cập còn phụ thuộc dữ liệu:

~~~java
@PreAuthorize("@reportPolicy.canRead(authentication, #reportId)")
public Report readReport(String reportId) {
    return repository.findById(reportId).orElseThrow();
}
~~~

`reportPolicy` có thể kiểm tra người dùng có phải chủ sở hữu, có thuộc tenant phù hợp hoặc báo cáo có được chia sẻ cho người đó không. Một authentication đã xác thực và có role phù hợp vẫn có thể bị từ chối nếu điều kiện dữ liệu không thỏa mãn.

## 6. Kiểm thử method security: cùng trạng thái token, quyền khác nhau

Để chứng minh trạng thái authentication khác với quyền hành động, hãy viết hai test cho cùng một phương thức. Cả hai test đều có người dùng giả lập đã xác thực; một người có authority cần thiết, người còn lại thiếu authority.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class ReportServiceAuthorizationTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "lan", authorities = "report:read")
    void readerCanReadButDoesNotAutomaticallyGetExportPermission() {
        assertThat(reportService.readReport("r-1")).isNotNull();

        assertThatThrownBy(() -> reportService.exportReport("r-1"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "mai", authorities = "report:export")
    void exportPermissionDoesNotAutomaticallyGrantReadPermission() {
        assertThat(reportService.exportReport("r-1")).isNotEmpty();

        assertThatThrownBy(() -> reportService.readReport("r-1"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Ví dụ giả định ứng dụng đã bật method security, có bean `ReportService` như phần trước, và dữ liệu báo cáo `r-1` tồn tại. Các test dùng `@WithMockUser` để cung cấp authentication giả lập. Chúng kiểm chứng authorization theo authority, không chạy quy trình xác thực password.

Có thể bổ sung assertion về trạng thái token trong cùng test:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

assertThat(authentication.isAuthenticated()).isTrue();
assertThat(authentication.getAuthorities())
        .extracting("authority")
        .contains("report:read")
        .doesNotContain("report:export");
~~~

Kết hợp hai nhóm assertion giúp chứng minh rõ: token đã được thiết lập là authenticated, nhưng chỉ có một authority và hành động còn lại vẫn bị từ chối.

## 7. @WithMockUser tạo danh tính giả lập, không cấp mọi quyền

`@WithMockUser` là tiện ích của `spring-security-test` để chạy một test với authentication giả lập. Annotation này không tự động thêm tất cả role hoặc permission.

~~~java
@Test
@WithMockUser(username = "lan", roles = "READER")
void hasOnlyReaderRole() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertThat(authentication.isAuthenticated()).isTrue();
    assertThat(authentication.getAuthorities())
            .extracting("authority")
            .containsExactly("ROLE_READER");
}
~~~

`roles = "READER"` tạo authority `ROLE_READER`. Nếu dùng `authorities = "report:read"`, authority được giữ nguyên và không tự thêm tiền tố `ROLE_`.

~~~java
@Test
@WithMockUser(username = "mai", authorities = "report:read")
void authorityIsNotAnAdminRole() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertThat(authentication.getAuthorities())
            .extracting("authority")
            .containsExactly("report:read");
}
~~~

Không suy ra người dùng có quyền quản trị chỉ vì `authentication.isAuthenticated()` là `true`. Hãy thiết lập đúng role/authority mà ca kiểm thử cần, rồi kiểm tra kết quả authorization.

## 8. Kiểm thử HTTP với MockMvc: phân biệt 401 và 403

Với Servlet, `MockMvc` có thể gửi request qua `SecurityFilterChain`. Cần bảo đảm filter đã được tích hợp, ví dụ dùng `@SpringBootTest` với `@AutoConfigureMockMvc` hoặc dựng `MockMvc` qua `webAppContextSetup(...).apply(springSecurity())`.

Giả sử endpoint `GET /api/admin/reports` yêu cầu `ROLE_ADMIN` và ứng dụng dùng HTTP Basic:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AdminReportHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousIsNotAuthenticated() throws Exception {
        mockMvc.perform(get("/api/admin/reports").with(anonymous()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderIsForbidden() throws Exception {
        mockMvc.perform(get("/api/admin/reports")
                        .with(user("lan").roles("READER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedAdminIsAllowed() throws Exception {
        mockMvc.perform(get("/api/admin/reports")
                        .with(user("mai").roles("ADMIN")))
                .andExpect(status().isOk());
    }
}
~~~

Các kỳ vọng dựa trên giả định:

- `/api/admin/reports` tồn tại và yêu cầu `hasRole("ADMIN")`.
- Security filter chain đã được bật trong MockMvc.
- HTTP Basic entry point trả `401` cho request anonymous.
- Người dùng `READER` đã được xác thực nhưng không có quyền ADMIN nên nhận `403`.
- Người dùng `ADMIN` được phép và endpoint trả `200`.

`.with(user(...))` cung cấp authentication giả lập cho request; nó không xác minh password. Nếu ứng dụng dùng form login hoặc entry point tùy chỉnh, request anonymous có thể nhận redirect `302` thay vì `401`. Với request thay đổi trạng thái, CSRF cũng có thể gây `403` độc lập với role. Hãy giữ các giả định cấu hình rõ ràng khi viết assertion.

Một bảng quyết định:

| Trạng thái request | Có authentication được chấp nhận cho authorization? | Authority yêu cầu | Kết quả điển hình |
| --- | --- | --- | --- |
| Anonymous | Không phải người dùng đã đăng nhập | `ROLE_ADMIN` | `401` hoặc redirect tới entry point |
| Đã xác thực, chỉ có `ROLE_READER` | Có | `ROLE_ADMIN` | `403` |
| Đã xác thực, có `ROLE_ADMIN` | Có | `ROLE_ADMIN` | `200` |
| Đã xác thực, có `ROLE_ADMIN` | Có | `ROLE_READER` | Tùy authority/role thực tế; có thể bị từ chối nếu thiếu `ROLE_READER` |

`401` thường biểu thị cần xác thực hoặc không có credential hợp lệ; `403` thường biểu thị request đã được xác định nhưng không đủ quyền. Mã cuối cùng phụ thuộc exception handling và cấu hình của ứng dụng.

## 9. JWT, OAuth2 và OIDC giả lập: trạng thái token không chứng minh chữ ký thật

`spring-security-test` cung cấp request postprocessor/configurer để mô phỏng authentication dựa trên JWT, OAuth2 login hoặc OIDC login. Chúng giúp kiểm tra authorization theo claims và authorities, nhưng không tự chạy toàn bộ quy trình xác thực thật.

Ví dụ với MockMvc:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/reports")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_report:read"))))
        .andExpect(status().isOk());
~~~

Ví dụ giả định endpoint yêu cầu authority `SCOPE_report:read` và MockMvc đã tích hợp resource server security. `jwt()` tạo authentication giả lập cho request; nó không chứng minh JWT có chữ ký hợp lệ, issuer đúng hoặc chưa hết hạn.

Với OAuth2/OIDC login, `oauth2Login()` và `oidcLogin()` giúp tạo principal/claims và authorities để kiểm tra phân quyền. Nếu mục tiêu là xác minh authorization theo role/claim, các mock này phù hợp. Nếu mục tiêu là xác minh decoder, chữ ký, issuer, audience, thời hạn token hoặc callback của nhà cung cấp danh tính, phải chạy test qua thành phần xác thực thực tế.

Quy tắc tương tự áp dụng cho Reactive `WebTestClient`: mock user/JWT/OAuth2 có thể tạo authentication cho request, nhưng không chứng minh cơ chế xác minh token thật.

## 10. Kiểm thử Reactive với WebTestClient

Trong WebFlux, context bảo mật được truyền qua Reactor Context. `Authentication` vẫn chứa principal, credentials và authorities, và quyết định authorization vẫn dựa trên chính sách. Khác biệt là cách ngữ cảnh được truyền trong pipeline, không phải ý nghĩa của quyền.

Ví dụ:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("lan").roles("READER"))
        .get().uri("/api/admin/reports")
        .exchange()
        .expectStatus().isForbidden();
~~~

Đoạn này giả định endpoint yêu cầu `ROLE_ADMIN` và `WebTestClient` đã tích hợp Spring Security WebFlux. Người dùng `lan` được giả lập với `ROLE_READER`; request đã có danh tính nhưng không đủ quyền, vì vậy bị từ chối. Đây là bằng chứng authorization của endpoint hoạt động trong test, không phải bằng chứng mật khẩu hay token được xác minh.

Không dùng `SecurityContextHolder.getContext()` trên thread JUnit để kết luận danh tính trong toàn bộ reactive pipeline. Dùng `ReactiveSecurityContextHolder` khi cần đọc context trong pipeline, và dùng các configurer của `WebTestClient` khi cần cấp danh tính cho request.

## 11. Các bẫy thường gặp

| Bẫy | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `authentication.isAuthenticated()` để quyết định người dùng có role ADMIN | Cờ này không kiểm tra authority | Dùng `hasRole("ADMIN")` hoặc `hasAuthority(...)` |
| Thấy `isAuthenticated()` của anonymous token là `true` rồi coi đã đăng nhập | Anonymous token cũng có thể được đánh dấu authenticated | Dùng trust resolver hoặc authorization expression |
| Gán authorities rồi kết luận mọi hành động được phép | Mỗi hành động có thể yêu cầu authority khác nhau | Viết rule riêng cho từng hành động/tài nguyên |
| Dùng `@WithMockUser` để khẳng định password đúng | Annotation bỏ qua authentication flow | Gửi credentials qua cơ chế xác thực cần kiểm tra |
| Dùng `jwt()` để khẳng định chữ ký token hợp lệ | Mock JWT bỏ qua decoder/signature validation | Test resource server với decoder và token thật phù hợp |
| Chỉ kiểm tra service trả dữ liệu mà không có ca bị từ chối | Chưa chứng minh authorization ngăn người thiếu quyền | Viết ca allowed và denied cho cùng hành động |
| HTTP `403` được coi luôn là sai role | CSRF hoặc access handler cũng có thể trả 403 | Kiểm tra response, CSRF và policy đang được áp dụng |
| MockMvc thiếu security filter nhưng test vẫn `200` | Controller có thể được gọi mà không qua authorization filter | Tích hợp `springSecurity()` và xác minh ca anonymous/insufficient role |

## 12. Bài thực hành

Tạo hai hành động trong `ReportService`: `readReport()` yêu cầu `report:read` và `exportReport()` yêu cầu `report:export`. Bật method security rồi thực hiện:

1. Tạo một `UsernamePasswordAuthenticationToken` bằng constructor hai tham số và xác minh `isAuthenticated()` là `false`.
2. Tạo một token có authorities bằng constructor phù hợp và xác minh `isAuthenticated()` là `true`. Giải thích vì sao điều này không chứng minh credential đã được kiểm tra trong một luồng đăng nhập thật.
3. Dùng `@WithMockUser(authorities = "report:read")`, xác minh đọc thành công nhưng xuất bị từ chối.
4. Dùng `@WithMockUser(authorities = "report:export")`, xác minh xuất thành công nhưng đọc bị từ chối nếu chính sách yêu cầu riêng `report:read`.
5. Viết ba request MockMvc: anonymous, READER và ADMIN. Assert `401`/`403`/`200` theo entry point và policy đã cấu hình.
6. Viết một test JWT giả lập với scope `SCOPE_report:read`. Nêu rõ test đang kiểm tra authorization hay kiểm tra chữ ký token.
7. Viết một test WebTestClient với user thiếu role và xác minh request Reactive bị từ chối.

Sau khi thực hành, hãy tự trả lời: **Token đã được đánh dấu authenticated chưa? Người dùng có authority nào? Chính sách của hành động yêu cầu gì?** Chỉ khi tách ba câu hỏi này, bạn mới có thể kết luận đúng lý do một request được cho phép hoặc bị từ chối.

## Tài liệu tham khảo

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security API — Authentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
