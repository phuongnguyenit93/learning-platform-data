# SAML2 với Authentication tùy chỉnh cho ca phân quyền sau đăng nhập

Một ứng dụng doanh nghiệp dùng SAML 2.0 có thể xác thực người dùng tại Identity Provider (IdP), rồi cho phép họ xem báo cáo theo vai trò và tenant. Khi IdP gửi một SAML Response hợp lệ, Spring Security xây dựng `Authentication` và đặt nó vào `SecurityContext`. Nhưng **đăng nhập thành công không đồng nghĩa mọi quyền truy cập tài nguyên đều hợp lệ**: Alice thuộc tenant A không được đọc báo cáo tenant B; một nhân viên thiếu nhóm quản trị cũng không được gọi API admin.

Trong chương **Cơ chế chuyên biệt** của **SPRING_SECURITY_TESTING**, chúng ta học cách kiểm chứng hành vi này bằng `spring-security-test` và `MockMvc` trên **Servlet stack**. Trọng tâm là dựng **`Saml2Authentication` với principal và authorities tùy chỉnh** để kiểm thử phân quyền **sau khi đăng nhập**; sau đó phân định rõ những gì phải kiểm chứng bằng luồng SAML thật. Khi ứng dụng có thành phần Reactive, `WebTestClient` có thể kiểm tra tầng API sau khi danh tính đã được chuyển đổi, nhưng không được mặc định dùng nó như một bản sao của SAML2 Servlet login.

## 1. Phân biệt xác thực SAML và phân quyền nghiệp vụ

Trong mô hình SAML Web Browser SSO, ứng dụng là **Service Provider (SP, hay relying party)** và IdP là **asserting party**. Một luồng SP-initiated thông dụng:

~~~mermaid
sequenceDiagram
    participant User as Browser
    participant SP as Spring Security SP
    participant IdP as Identity Provider
    participant App as Report service
    User->>SP: Yêu cầu /api/reports/report-a
    SP-->>User: Redirect để bắt đầu SAML login
    User->>SP: Truy cập /saml2/authenticate/corp
    SP-->>User: Redirect với SAML AuthnRequest
    User->>IdP: Đăng nhập tại IdP
    IdP-->>User: SAML Response
    User->>SP: POST /login/saml2/sso/corp
    SP->>SP: Kiểm tra chữ ký, issuer, audience, thời gian và response
    SP->>SP: Tạo Saml2Authentication + authorities
    SP-->>User: Session xác thực / redirect
    User->>SP: GET /api/reports/report-a
    SP->>App: Kiểm tra vai trò và tenant
    App-->>User: 200 hoặc 403 theo chính sách
~~~

Các URL trong sơ đồ là mẫu đường dẫn phổ biến của Spring Security Servlet; đường xử lý thực tế tùy `RelyingPartyRegistration` và cấu hình `saml2Login()` của ứng dụng.

| Lớp | Trách nhiệm | Dạng test phù hợp |
| --- | --- | --- |
| **SAML protocol/authentication** | Tiếp nhận response, tìm relying party, xác minh chữ ký, issuer, audience, thời hạn, recipient, correlation và các điều kiện | Integration test dùng response đã ký hợp lệ/không hợp lệ từ IdP kiểm thử |
| **Authentication conversion** | Biến danh tính/attributes đã xác minh thành principal nội bộ và `GrantedAuthority` | Unit test mapper và test tích hợp provider/converter |
| **HTTP authorization** | Áp dụng `SecurityFilterChain`, URL, HTTP method và authority | `MockMvc` với `authentication(...)` hoặc `securityContext(...)` |
| **Method/domain authorization** | Kiểm tra quyền trên tenant, tài liệu, nghiệp vụ ở service | `@PreAuthorize`/policy test với principal tùy chỉnh |

**Quan trọng:** một test `MockMvc` dùng `.with(authentication(customSamlAuthentication))` **bỏ qua việc phân tích và xác minh XML SAML**. Nó rất phù hợp để kiểm tra quyền sau đăng nhập, nhưng không chứng minh IdP hay SP đã hoàn tất quy trình SAML một cách an toàn.

## 2. Những thông tin của SAML có ý nghĩa với phân quyền

Sau khi IdP xác thực, ứng dụng có thể cần ánh xạ các dữ liệu đã được xác minh:

| Giá trị | Ví dụ test | Cách sử dụng |
| --- | --- | --- |
| `NameID` hoặc external subject | `alice@corp.example` | Liên kết định danh người dùng |
| `tenant_id` | `tenant-a` | Giới hạn dữ liệu theo tổ chức |
| `groups` | `reports.read`, `reports.admin` | Ánh xạ sang authority nội bộ |
| `department` | `finance` | Thông tin nghiệp vụ phụ trợ nếu được policy cho phép |
| `RelyingPartyRegistration` | `corp` | Xác định IdP/relying party đáng tin của phiên |

Các tên attributes như `tenant_id` và `groups` là **quy ước ứng dụng mẫu**, không phải thuộc tính SAML bắt buộc của mọi IdP. Dự án thật cần xác nhận tên attribute, format, tính ổn định của subject và hợp đồng với IdP.

Không sử dụng input `tenant_id` từ query parameter hoặc một HTTP header tự gửi để quyết định quyền. Nó phải xuất phát từ **assertion đã được SP xác minh và ánh xạ theo chính sách tin cậy**, hoặc từ cơ sở dữ liệu nội bộ được quản trị.

## 3. Tại sao cần Authentication tùy chỉnh?

Một `Saml2Authentication` thông thường có principal và collection `GrantedAuthority`. Khi ứng dụng muốn kiểm tra tenant, nhóm nghiệp vụ hoặc subject ổn định, ta có thể dùng một **custom principal** hoặc một kiểu Authentication riêng theo nhu cầu. Nhiều trường hợp **không cần kế thừa `AbstractAuthenticationToken`**: chỉ cần xây `Saml2Authentication` với một principal thực hiện `AuthenticatedPrincipal` và authorities do mapper nội bộ cấp.

Ví dụ một principal chuyên dùng cho ứng dụng báo cáo:

~~~java
import java.util.Set;
import org.springframework.security.core.AuthenticatedPrincipal;

public record AppSamlPrincipal(
        String name,
        String tenantId,
        Set<String> groups
) implements AuthenticatedPrincipal {

    public AppSamlPrincipal {
        groups = Set.copyOf(groups);
    }

    @Override
    public String getName() {
        return name;
    }
}
~~~

`Set.copyOf(...)` tạo tập nhóm không sửa được sau khi dựng, giảm khả năng một test hoặc request khác thay đổi quyền bằng cách sửa cùng một collection. Trong hệ thống thật, nếu principal có dữ liệu lồng nhau khả biến, phải defensive-copy ở những cấp tương ứng. Cũng cần quyết định rõ `name` là NameID hay internal user ID; không tự lấy email làm khóa vĩnh viễn nếu IdP có thể đổi email.

**Điều quan trọng là nguồn gốc các giá trị**, không phải tên lớp `AppSamlPrincipal`. Trong ứng dụng thật, converter phải nhận identity/attributes qua đường xác minh SAML đáng tin. Trong bài test hậu đăng nhập, ta được phép dựng principal giả lập với giá trị xác định nhằm kiểm tra rule.

## 4. Ánh xạ nhóm SAML sang quyền có danh sách cho phép

Một sai lầm dễ gặp là nhận mọi chuỗi trong `groups` rồi ghép tiền tố `ROLE_` để cấp quyền. Nếu IdP thay đổi tên group, mapping không nhất quán; nguy hiểm hơn, nếu có nguồn attribute không đáng tin được đưa vào mapper, ứng dụng có thể cấp quyền vượt dự kiến.

Thay vì cấp authority tùy ý, định nghĩa bảng ánh xạ rõ:

| Group đã được xác minh | Authority ứng dụng |
| --- | --- |
| `reports.read` | `ROLE_REPORT_READER` |
| `reports.admin` | `ROLE_REPORT_ADMIN` |
| Group khác hoặc không có group | Không cấp quyền báo cáo |

Một mapper đơn giản và thuần (pure function):

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

final class ReportAuthorityMapper {
    private ReportAuthorityMapper() {}

    static Collection<GrantedAuthority> map(Set<String> verifiedGroups) {
        List<GrantedAuthority> result = new ArrayList<>();
        result.add(new SimpleGrantedAuthority("ROLE_USER"));

        if (verifiedGroups.contains("reports.read")) {
            result.add(new SimpleGrantedAuthority("ROLE_REPORT_READER"));
        }
        if (verifiedGroups.contains("reports.admin")) {
            result.add(new SimpleGrantedAuthority("ROLE_REPORT_ADMIN"));
        }
        return List.copyOf(result);
    }
}
~~~

Trong fixture bên dưới, `verifiedGroups` chỉ là **tên biến mô tả dữ liệu giả lập**. Nó không làm dữ liệu test có chữ ký thật. Ở production, chỉ gọi mapper sau khi response đã qua bước xác minh của SAML provider; nếu còn yêu cầu quản lý quyền nội bộ, hãy đối chiếu group với trạng thái người dùng/tenant trong hệ thống.

## 5. Tạo Saml2Authentication giả lập cho test hậu đăng nhập

Trong bộ test, hãy có factory tạo **mới hoàn toàn** principal và Authentication mỗi lần:

~~~java
import java.util.Set;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;

final class SamlFixtures {
    private SamlFixtures() {}

    static Saml2Authentication authenticated(
            String username, String tenantId, Set<String> groups) {
        AppSamlPrincipal principal =
            new AppSamlPrincipal(username, tenantId, groups);

        // Chỉ là marker fixture, KHÔNG phải SAML XML có chữ ký hợp lệ.
        String fakeSamlResponse = "<not-a-real-saml-response/>";

        return new Saml2Authentication(
            principal,
            fakeSamlResponse,
            ReportAuthorityMapper.map(principal.groups()));
    }
}
~~~

Ví dụ:

~~~java
Saml2Authentication alice = SamlFixtures.authenticated(
    "alice@corp.example",
    "tenant-a",
    Set.of("reports.read"));

Saml2Authentication bob = SamlFixtures.authenticated(
    "bob@corp.example",
    "tenant-b",
    Set.of("reports.admin"));

assertThat(alice.getName()).isEqualTo("alice@corp.example");
assertThat(alice.getAuthorities())
    .extracting(GrantedAuthority::getAuthority)
    .contains("ROLE_REPORT_READER")
    .doesNotContain("ROLE_REPORT_ADMIN");
~~~

`Saml2Authentication` đại diện cho kết quả **đã xác thực** của SAML login. Constructor ở ví dụ chỉ dùng trong test downstream; truyền chuỗi XML giả vào object **không khiến XML được validate hoặc signed**. Không gửi `fakeSamlResponse` tới `/login/saml2/sso/{registrationId}` và không dùng fixture làm bằng chứng chữ ký, `InResponseTo`, audience hay thời gian hiệu lực đúng.

Với một ca kiểm thử phân quyền sau đăng nhập, điều cần làm rõ là: “Giả sử người dùng Alice đã được SAML xác thực và được ánh xạ thành các authorities này, API có cho phép đúng tài nguyên không?”. Để chứng minh câu hỏi “Assertion của IdP có thật sự hợp lệ không?”, phải viết một lớp test khác.

## 6. Tạo policy theo tenant và authority tại service

Giả sử có hai báo cáo:

~~~text
report-a -> tenant-a
report-b -> tenant-b
~~~

Một policy cần cả quyền báo cáo và tenant khớp với tài nguyên. Chúng ta kiểm tra loại principal cụ thể để chắc chắn rule đang dùng **identity nghiệp vụ đã được mapping sau SAML**, chứ không vô tình tin một principal thông thường:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportAccessPolicy")
public class ReportAccessPolicy {
    private final Map<String, String> reportTenants = Map.of(
        "report-a", "tenant-a",
        "report-b", "tenant-b");

    public boolean canRead(Authentication authentication, String reportId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        if (!(authentication instanceof Saml2Authentication)) {
            return false;
        }
        if (!(authentication.getPrincipal() instanceof AppSamlPrincipal p)) {
            return false;
        }

        String resourceTenant = reportTenants.get(reportId);
        if (resourceTenant == null
                || !resourceTenant.equals(p.tenantId())) {
            return false;
        }

        return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(authority ->
                authority.equals("ROLE_REPORT_READER")
                    || authority.equals("ROLE_REPORT_ADMIN"));
    }
}
~~~

Các import còn lại gồm `Saml2Authentication` và `GrantedAuthority`. Bản đồ dữ liệu chỉ là fixture để ví dụ độc lập với database. Ở ứng dụng thật, policy phải tra tenant của resource từ repository tin cậy, xử lý tài nguyên không tồn tại, và cân nhắc transaction/race condition nếu quyền sở hữu có thể đổi trong lúc ghi.

Để bảo vệ service, sử dụng `@PreAuthorize`:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("@reportAccessPolicy.canRead(authentication, #p0)")
    public String read(String reportId) {
        return "report:" + reportId;
    }
}
~~~

`#p0` là tham số đầu tiên của phương thức, giúp tránh phụ thuộc việc trình biên dịch có giữ tên parameter `reportId` hay không. Điều kiện `@PreAuthorize` chỉ có hiệu lực khi `@EnableMethodSecurity` được bật và lời gọi đi qua Spring-managed bean/proxy. Một lời gọi `new ReportService()` không kiểm chứng method security.

## 7. SecurityFilterChain cho ứng dụng Servlet có SAML2 login

SAML2 login trong Spring Security hiện tập trung vào **Servlet SP**. Ứng dụng có thể cấu hình bộ lọc HTTP như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports/admin")
                    .hasAuthority("ROLE_REPORT_ADMIN")
                .requestMatchers("/api/reports/**").authenticated()
                .anyRequest().permitAll())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Để chạy cấu hình trên, Spring context còn cần `RelyingPartyRegistrationRepository` hợp lệ (hoặc cấu hình relying party của Spring Boot) với metadata/verification credentials dành cho IdP được phép. `saml2Login()` không tự tạo một IdP hay cấu hình relying party. **Test chỉ giả lập Authentication hậu đăng nhập** vẫn phải tải application context hợp lệ, nhưng không cần thực hiện SAML response exchange trong từng case.

Các request đọc báo cáo được HTTP filter kiểm tra `authenticated()`, rồi `ReportService.read` kiểm tra tenant + authority. `/api/reports/admin` được bảo vệ thêm bằng authority `ROLE_REPORT_ADMIN` ở filter. Khi unauthenticated request truy cập URL, SAML login entry point thường dẫn tới **redirect**; không mặc định assert `401` như với stateless JWT Resource Server.

### Controller để quan sát kết quả phân quyền

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {
    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/{id}")
    public String read(@PathVariable String id) {
        return reports.read(id);
    }

    @GetMapping("/admin")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
~~~

`/admin` được HTTP filter yêu cầu quyền quản trị trước khi controller được gọi; `/{id}` gọi service có method security. Vì controller trả `String`, phép kiểm thử có thể assert response body đơn giản bằng `content().string(...)`.

**Giới hạn của mẫu:** đây là minh họa Servlet SP với một relying party đã được cấu hình trong test environment; chưa kèm private key, X.509 certificate hoặc IdP giả lập. Không được chép certificate hay private key sản xuất vào test. Nếu test context chưa có `RelyingPartyRegistrationRepository`, cần thiết lập cấu hình relying party của riêng môi trường test trước khi áp dụng ví dụ `@SpringBootTest` dưới đây.

## 8. MockMvc: phân quyền hậu SAML với Authentication tùy chỉnh

`SecurityMockMvcRequestPostProcessors.authentication(...)` gắn một `Authentication` cụ thể vào request test. Đây là kỹ thuật phù hợp khi muốn mô phỏng một phiên **đã qua SAML login** rồi kiểm tra URL, authority và tenant:

~~~java
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SamlPostLoginMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void aliceReadsReportInHerTenant() throws Exception {
        mvc.perform(get("/api/reports/report-a")
                .with(authentication(SamlFixtures.authenticated(
                    "alice@corp.example", "tenant-a",
                    Set.of("reports.read")))))
            .andExpect(status().isOk())
            .andExpect(content().string("report:report-a"));
    }

    @Test
    void aliceCannotReadReportOfAnotherTenant() throws Exception {
        mvc.perform(get("/api/reports/report-b")
                .with(authentication(SamlFixtures.authenticated(
                    "alice@corp.example", "tenant-a",
                    Set.of("reports.read")))))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobReadsReportInTenantB() throws Exception {
        mvc.perform(get("/api/reports/report-b")
                .with(authentication(SamlFixtures.authenticated(
                    "bob@corp.example", "tenant-b",
                    Set.of("reports.read")))))
            .andExpect(status().isOk());
    }

    @Test
    void loginWithoutReportGroupDoesNotGrantReadPermission()
            throws Exception {
        mvc.perform(get("/api/reports/report-a")
                .with(authentication(SamlFixtures.authenticated(
                    "charlie@corp.example", "tenant-a",
                    Set.of("unknown-idp-group")))))
            .andExpect(status().isForbidden());
    }

    @Test
    void reportAdminGroupCanVisitAdminEndpoint() throws Exception {
        mvc.perform(get("/api/reports/admin")
                .with(authentication(SamlFixtures.authenticated(
                    "bob@corp.example", "tenant-b",
                    Set.of("reports.admin")))))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:bob@corp.example"));
    }

    @Test
    void reportReaderCannotVisitAdminEndpoint() throws Exception {
        mvc.perform(get("/api/reports/admin")
                .with(authentication(SamlFixtures.authenticated(
                    "alice@corp.example", "tenant-a",
                    Set.of("reports.read")))))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/api/reports/report-a"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

`@AutoConfigureMockMvc` phải dùng Spring Security filter chain thật của test context; nếu tự tạo MockMvc thủ công, cần `.apply(springSecurity())` khi dựng builder. Nếu app thay `AuthenticationEntryPoint` bằng cơ chế API trả `401`, test anonymous phải sửa kỳ vọng theo cấu hình đó. Với mẫu SAML browser login, redirect là hành vi phổ biến hơn. Không hardcode `Location` tới một IdP cụ thể khi test chỉ kiểm tra “cần đăng nhập”.

### Ma trận ca phân quyền đã được bao phủ

| Người dùng | Tenant | Groups | Request | Kỳ vọng | Lý do |
| --- | --- | --- | --- | --- | --- |
| Alice | A | reports.read | GET report-a | `200` | Đủ authority và cùng tenant |
| Alice | A | reports.read | GET report-b | `403` | Sai tenant dù có quyền đọc |
| Bob | B | reports.read | GET report-b | `200` | Đối chứng dương thứ hai |
| Charlie | A | unknown group | GET report-a | `403` | Mapper không tự cấp quyền đọc |
| Bob | B | reports.admin | GET /admin | `200` | Có role admin hợp lệ |
| Alice | A | reports.read | GET /admin | `403` | Thiếu role admin |
| Anonymous | — | — | GET report-a | Thường `302` | Phải đi qua đăng nhập |

Nếu một test âm tính `403` nhưng không có test dương `200` tương ứng, lỗi cấu hình (ví dụ method security vô tình chặn mọi người) có thể không bị phát hiện. Cặp Alice đọc report-a và Alice bị từ chối report-b giúp chứng minh **chính sách tenant**, còn test admin/reader chứng minh **quy tắc authority**.

### @WithMockUser không thay thế Saml2Authentication

`@WithMockUser(username = "alice", roles = "REPORT_READER")` tạo một authentication kiểu mock user thông thường, không phải kết quả SAML được ánh xạ sang `AppSamlPrincipal`. Với policy có kiểm tra principal type như ở mục 6, một mock user thông thường **không được cấp quyền** dù tình cờ có authority tương tự.

~~~java
@Test
@WithMockUser(username = "alice", roles = "REPORT_READER")
void ordinaryMockUserIsNotACompleteSamlDomainIdentity()
        throws Exception {
    mvc.perform(get("/api/reports/report-a"))
        .andExpect(status().isForbidden());
}
~~~

Thêm import `org.springframework.security.test.context.support.WithMockUser` và đặt test trong lớp có `MockMvc mvc`. Điều này không có nghĩa `@WithMockUser` là công cụ sai: nó vẫn phù hợp với endpoint chỉ yêu cầu `authenticated()` hoặc authority phổ thông. Nhưng khi policy dựa vào tenant, groups, loại `Authentication` hoặc principal chuyên biệt, cần một fixture phản ánh đúng hợp đồng security của ứng dụng.

**Không giả định Spring Security Test có post processor chuyên biệt `saml2Login()` giống `oauth2Login()`.** Cách trực tiếp, có thể kiểm soát ở đây là `authentication(customSamlAuthentication)` hoặc `securityContext(context)`, và phải mô tả rõ chúng tạo sẵn trạng thái hậu đăng nhập.

## 9. Kiểm thử service trực tiếp: method security vẫn hoạt động

SecurityFilterChain bảo vệ **HTTP**, còn `@PreAuthorize` bảo vệ phương thức ở Spring bean. Vì thế có thể test domain policy độc lập:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest
class SamlReportMethodSecurityTest {
    @Autowired
    ReportService reports;

    @Test
    void serviceRejectsCrossTenantEvenWithoutHttp() {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(SamlFixtures.authenticated(
            "alice@corp.example", "tenant-a",
            Set.of("reports.read")));

        try {
            SecurityContextHolder.setContext(context);

            assertThat(reports.read("report-a"))
                .isEqualTo("report:report-a");

            assertThatThrownBy(() -> reports.read("report-b"))
                .isInstanceOf(AccessDeniedException.class);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Phép kiểm thử này gọi **bean được Spring quản lý**, không `new ReportService()`, nhờ vậy method-security interceptor được áp dụng. `SecurityContextHolder.clearContext()` ở `finally` rất quan trọng để tránh rò principal Alice sang test khác trên cùng test thread.

Lỗi `AccessDeniedException` trong unit/service test **không tự tạo một mã HTTP**. Khi truy cập qua Servlet filter chain, framework thường chuyển thành `403`. Đó là hai lớp bằng chứng khác nhau, nên nên duy trì cả service test lẫn MockMvc test.

## 10. Custom @WithSecurityContext cho nhiều test cùng nghiệp vụ

Nếu cần tạo identity SAML nội bộ trong nhiều lớp test, `@WithSecurityContext` cho phép dùng annotation thay vì lặp lại `SecurityContextHolder.setContext(...)`. Factory phải tạo **context mới trong mỗi lần chạy** và không chia sẻ một principal khả biến toàn suite.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithSamlIdentityFactory.class)
public @interface WithSamlIdentity {
    String username() default "alice@corp.example";
    String tenant() default "tenant-a";
    String[] groups() default {"reports.read"};
}
~~~

~~~java
import java.util.Arrays;
import java.util.Set;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithSamlIdentityFactory
        implements WithSecurityContextFactory<WithSamlIdentity> {

    @Override
    public SecurityContext createSecurityContext(WithSamlIdentity config) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(SamlFixtures.authenticated(
            config.username(),
            config.tenant(),
            Set.copyOf(Arrays.asList(config.groups()))));
        return context;
    }
}
~~~

Sử dụng:

~~~java
@Test
@WithSamlIdentity(
    username = "alice@corp.example",
    tenant = "tenant-a",
    groups = {"reports.read"})
void methodTestUsesSamlDomainPrincipal() {
    assertThat(reports.read("report-a")).isEqualTo("report:report-a");
}
~~~

Đặt annotation, factory và các fixture vào mã test của ứng dụng. `@WithSecurityContext` tạo identity **giả lập** trước test theo listener của Spring Security Test; nó không thực hiện SAML login. Không cache `SecurityContext` trong một biến `static`, không sửa danh sách group dùng chung và không dùng một annotation test để khẳng định chữ ký IdP được xác minh.

## 11. Ở production, Authentication tùy chỉnh được tạo tại đâu?

Các fixture trong bài mô phỏng **đầu ra** của quá trình xác thực. Để chúng phản ánh đúng hành vi production, ứng dụng phải có một bước ánh xạ thực tế giữa kết quả xác minh SAML của Spring Security và principal/authorities nội bộ.

Trong những phiên bản Spring Security dùng OpenSAML 5, một extension point là `OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter(...)`. Provider chịu trách nhiệm xác thực response/assertion; converter được áp dụng ở giai đoạn tạo Authentication từ dữ liệu đã qua đường xác minh của provider.

~~~text
SAMLResponse qua HTTP
      |
      v
Saml2WebSsoAuthenticationFilter
      |
      v
OpenSaml5AuthenticationProvider
  - chữ ký / issuer / destination
  - subject / audience / thời gian
  - những kiểm tra SAML khác theo config
      |
      v
Response authentication converter
  - lấy subject và trusted attributes
  - đối chiếu chính sách nội bộ
  - tạo principal và granted authorities
      |
      v
Saml2Authentication / SAML authentication phù hợp phiên bản
      |
      v
SecurityContext -> HTTP / method authorization
~~~

Một helper dễ unit-test có thể tiếp nhận **giá trị đã được xác minh**, kiểm tra dữ liệu bắt buộc và tạo authentication:

~~~java
import java.util.Set;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;

final class TrustedSamlIdentityFactory {

    static Saml2Authentication fromVerifiedAttributes(
            String externalSubject,
            String tenantId,
            Set<String> groups,
            String validatedSamlResponse) {

        if (externalSubject == null || externalSubject.isBlank()) {
            throw new IllegalArgumentException("Missing SAML subject");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant mapping");
        }
        if (groups == null) {
            throw new IllegalArgumentException("Missing groups collection");
        }

        AppSamlPrincipal principal =
            new AppSamlPrincipal(externalSubject, tenantId, groups);

        return new Saml2Authentication(
            principal,
            validatedSamlResponse,
            ReportAuthorityMapper.map(principal.groups()));
    }
}
~~~

Tên phương thức `fromVerifiedAttributes(...)` là một **hợp đồng**: caller production phải thực sự lấy dữ liệu từ kết quả đã xác minh của SAML provider hoặc một nguồn nội bộ đáng tin. Bản thân helper **không** kiểm tra chữ ký, issuer, audience, replay hoặc chất lượng của chuỗi `validatedSamlResponse`. Nếu test tự truyền XML chưa ký, chỉ chứng minh business mapping, không chứng minh SAML protocol.

Các test mapper nên bao phủ:

~~~java
@Test
void unknownSamlGroupDoesNotBecomeApplicationAdmin() {
    Saml2Authentication auth =
        TrustedSamlIdentityFactory.fromVerifiedAttributes(
            "charlie@corp.example",
            "tenant-a",
            Set.of("superusers", "ROLE_REPORT_ADMIN"),
            "<fixture-only/>");

    assertThat(auth.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .contains("ROLE_USER")
        .doesNotContain("ROLE_REPORT_ADMIN");
}

@Test
void missingTenantIsRejectedDuringIdentityMapping() {
    assertThatThrownBy(() ->
        TrustedSamlIdentityFactory.fromVerifiedAttributes(
            "alice@corp.example",
            "",
            Set.of("reports.read"),
            "<fixture-only/>"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("tenant");
}
~~~

`TrustedSamlIdentityFactory` cho phép test **chính sách cấp role** độc lập với một IdP đang chạy. Nhưng với tích hợp thật, cần bổ sung test xác nhận response converter đã gọi factory với **đúng attributes** được IdP phát hành và được SP tin cậy.

### Gắn converter vào provider theo phiên bản

Ở mức cấu hình, luồng ý tưởng với OpenSAML 5 là:

~~~java
// Minh họa điểm gắn extension, không phải một bean cấu hình thứ hai
// để đặt song song với SecurityFilterChain ở mục 7.
OpenSaml5AuthenticationProvider provider =
    new OpenSaml5AuthenticationProvider();

provider.setResponseAuthenticationConverter(customResponseConverter);

http.saml2Login(saml2 -> saml2.authenticationManager(
    new ProviderManager(provider)));
~~~

`customResponseConverter` ở đây là converter do ứng dụng triển khai theo **API của phiên bản Spring Security đang dùng**. Nó phải trích subject và các attribute từ response/assertion **sau khi provider kiểm tra**, gọi mapping/domain lookup phù hợp và tạo authentication không làm mất dữ liệu SAML cần thiết. Đây là **phác thảo phần tích hợp**; để có cấu hình hoàn chỉnh, dùng đúng import và converter contract theo Spring Security/OpenSAML của dự án.

Đừng thay provider thật bằng `AuthenticationManager` “luôn trả thành công” trong production để tiết kiệm thời gian viết converter. Làm vậy bỏ qua xác minh SAML ở ranh giới quan trọng nhất.

### Lưu ý phiên bản Spring Security 6.x và 7.x

SAML2 là vùng API có thay đổi theo phiên bản:

- Spring Security 6.x có `Saml2Authentication` và các API như `Saml2AuthenticatedPrincipal`, `DefaultSaml2AuthenticatedPrincipal`; một số bản 6.x dùng OpenSAML 4 hoặc hỗ trợ OpenSAML 5 tùy cấu hình/dependency.
- Spring Security 7.x định hướng dùng `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication` cho dữ liệu assertion; `Saml2AuthenticatedPrincipal` và một số API cũ đã được đánh dấu deprecated ở nhánh mới.
- Khi custom converter thay authentication mà bỏ mất assertion accessor hoặc registration information cần thiết, tính năng **SAML Single Logout** có thể bị ảnh hưởng.

Vì vậy ví dụ fixture hậu đăng nhập trong bài dùng `AuthenticatedPrincipal` riêng và `Saml2Authentication` để tập trung vào domain authorization. Với luồng SSO thực và SLO, cần kiểm tra hướng dẫn migration của **đúng phiên bản** và bảo toàn contract mà Spring Security sử dụng cho logout; không nên sao chép một converter giữa 6.x và 7.x mà không rà API.

## 12. Một test gắn Authentication vào request không tạo session SAML thật

`MockMvc.perform(...).with(authentication(samlAuth))` chỉ gắn identity **cho request đang kiểm thử**. Nó không thực hiện callback ACS, không tự chứng minh session đã được tạo qua SAML login, và không bảo đảm authentication sẽ tiếp tục tồn tại ở request thứ hai không gắn `authentication(...)`.

Nếu muốn kiểm tra việc một **session đã có SecurityContext** được dùng trên nhiều request, có thể tạo context và session giả phục vụ test của Servlet security context repository:

~~~java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Test
void sessionCanReuseAnAlreadyEstablishedSamlAuthentication()
        throws Exception {
    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(SamlFixtures.authenticated(
        "alice@corp.example", "tenant-a",
        Set.of("reports.read")));

    MockHttpSession session = new MockHttpSession();
    session.setAttribute(
        HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
        context);

    mvc.perform(get("/api/reports/report-a").session(session))
        .andExpect(status().isOk());

    mvc.perform(get("/api/reports/report-b").session(session))
        .andExpect(status().isForbidden());
}
~~~

Test trên **giả định** cấu hình security context repository của ứng dụng có đọc `SecurityContext` từ HttpSession theo khóa tương ứng. Nó kiểm chứng việc downstream authorization hoạt động khi session chứa authentication được chuẩn bị trước, **không chứng minh SP đã xác minh SAML Response để tạo ra session**. Nếu ứng dụng có custom `SecurityContextRepository` hoặc stateless policy, hãy kiểm tra đúng cơ chế lưu context thực tế thay vì dùng key mặc định.

Một test tích hợp login thật cần bảo toàn **cùng browser session/cookie** từ AuthnRequest đến callback ACS và request tiếp theo. Chỉ lặp lại `authentication(...)` ở mỗi request có thể che lỗi session persistence.

## 13. Kiểm thử SAML Response thật: một suite khác

Để xác nhận SP thực sự chấp nhận hoặc từ chối assertion của IdP, cần khởi tạo một **IdP kiểm thử** hoặc dùng những phản hồi SAML được tạo và ký bằng **private key riêng của môi trường test**. Có thể chạy một IdP local/container hoặc môi trường tích hợp đã kiểm soát metadata và certificate; không được dùng private key production trong test repository.

Một flow tích hợp SP-initiated tiêu biểu:

1. Đăng ký relying party `corp` với entity ID, ACS endpoint, IdP metadata và verification certificate test rõ ràng.
2. Gửi request khởi tạo SAML login tới `/saml2/authenticate/corp` hoặc luồng login tương ứng; lưu session, request ID và `RelayState` cần thiết.
3. IdP test xác thực người dùng giả rồi phát `SAMLResponse` phù hợp, đã ký, đúng issuer/audience/destination, subject và thời gian hiệu lực.
4. Browser/test client gửi **form POST** tới ACS `/login/saml2/sso/corp` với `SAMLResponse` đã được Base64-encoded, `RelayState` theo flow và **cùng session** nếu đang kiểm tra correlation của SP-initiated login.
5. SP thực thi `Saml2WebSsoAuthenticationFilter` và authentication provider; nếu thành công, chuyển/ghi SecurityContext vào session theo cấu hình.
6. Gửi request tiếp theo tới `/api/reports/report-a`, kiểm tra đúng principal, authorities, tenant và policy. Không dùng `.with(authentication(...))` tại bước này, nếu mục tiêu là kiểm tra dữ liệu đã được lưu bởi SAML login.
7. Lặp lại với response sai chữ ký, issuer, audience, destination, subject confirmation hoặc thời gian để kiểm tra **authentication failure** trước khi tới controller.

Ma trận test protocol:

| Tình huống | Điểm cần quan sát | Khác gì với test hậu đăng nhập? |
| --- | --- | --- |
| SAMLResponse ký hợp lệ, attributes đúng | SP chấp nhận callback và xây Authentication | Provider thực sự xác minh chữ ký |
| Chữ ký thiếu/sai hoặc certificate không tin cậy | Đăng nhập bị từ chối | Không thể mô phỏng bằng `Saml2Authentication` dựng sẵn |
| Sai issuer/audience/recipient/destination | Assertion không được chấp nhận | Kiểm tra ranh giới trust giữa SP và IdP |
| `NotBefore` hoặc `NotOnOrAfter` không hợp lệ | Bị từ chối theo validation/clock skew | Không chỉ kiểm tra business role |
| `InResponseTo` không tương ứng request đang chờ | Bị từ chối trong flow yêu cầu correlation | Cần giữ session/request ID đúng cách |
| Response dùng lại | Kiểm tra replay policy/thành phần lưu trạng thái được triển khai | Test hậu đăng nhập không phát hiện replay |
| Thiếu `tenant_id` sau xác minh | Domain mapping từ chối hoặc không cấp quyền | Tách identity hợp lệ và authorization thiếu dữ liệu |
| Nhóm SAML chưa được whitelist | Người dùng có thể đăng nhập nhưng không có `ROLE_REPORT_ADMIN` | Kiểm tra conversion và downstream authorization |

Không mặc định mọi SAML library/ứng dụng có sẵn cơ chế replay cache giống nhau; cần kiểm tra triển khai cụ thể và policy của sản phẩm. Một response từ IdP test cũng phải tuân theo các điều kiện assertion mà SP đang yêu cầu, không chỉ “có chữ ký” là đủ.

### Với MockMvc, phân biệt yêu cầu giả lập và yêu cầu vào ACS

~~~text
HTTP test hậu đăng nhập:
  GET /api/reports/report-a
  + authentication(customSamlAuthentication)
  -> chạy quy tắc phân quyền, KHÔNG parse SAML XML

HTTP test SAML thực:
  POST /login/saml2/sso/corp
  Content-Type: application/x-www-form-urlencoded
  SAMLResponse=<Base64 của XML đã ký>
  RelayState=<giá trị từ flow nếu có>
  -> chạy Saml2WebSsoAuthenticationFilter + provider/validator
~~~

Trong đoạn thứ hai, giá trị form chỉ là mô tả cấu trúc request. Bài này **không tạo một SAMLResponse có chữ ký**, vì điều đó đòi hỏi IdP/certificate và cấu hình relying party test. Không đưa placeholder `<not-a-real-saml-response/>` của fixture vào ACS rồi mong đợi login thành công.

## 14. Các lỗi phân quyền đặc thù sau SAML login

### Role không khớp quy tắc kiểm tra

Spring Security phân biệt `hasRole("REPORT_ADMIN")` và `hasAuthority("ROLE_REPORT_ADMIN")`: với prefix mặc định, chúng cùng tìm `ROLE_REPORT_ADMIN`. Nhưng `hasAuthority("REPORT_ADMIN")` là một chuỗi khác. Trong ví dụ, mapper cấp `ROLE_REPORT_ADMIN` nên security chain dùng `hasAuthority("ROLE_REPORT_ADMIN")`.

Test nên xác nhận đồng thời:

~~~java
Saml2Authentication reader = SamlFixtures.authenticated(
    "alice@corp.example", "tenant-a",
    Set.of("reports.read"));

assertThat(reader.getAuthorities())
    .extracting(GrantedAuthority::getAuthority)
    .contains("ROLE_REPORT_READER")
    .doesNotContain("ROLE_REPORT_ADMIN");
~~~

Không chỉ assert `Authentication.isAuthenticated() == true`: một user đã xác thực nhưng không có quyền nghiệp vụ phải bị `403` với endpoint tương ứng.

### Sai tenant dù nhóm đã đúng

Một principal có `reports.admin` không có nghĩa được đọc mọi tenant. Policy mục 6 cố tình yêu cầu:

~~~text
canRead =
    authenticatedSamlPrincipal
    AND hasAny(ROLE_REPORT_READER, ROLE_REPORT_ADMIN)
    AND principal.tenantId == report.tenantId
~~~

Thêm ca admin tenant B cố đọc báo cáo tenant A:

~~~java
@Test
void reportAdminCannotCrossTenantBoundary() throws Exception {
    mvc.perform(get("/api/reports/report-a")
            .with(authentication(SamlFixtures.authenticated(
                "bob@corp.example", "tenant-b",
                Set.of("reports.admin")))))
        .andExpect(status().isForbidden());
}
~~~

Nếu nghiệp vụ có **global admin** thực sự được đọc mọi tenant, cần chính sách và test riêng, không tự động biến `reports.admin` thành global superuser.

### NameID thay đổi hoặc không duy nhất giữa các IdP

Không mặc định `NameID` luôn là email hoặc luôn bất biến. Một IdP có thể phát hành transient/persistent NameID hoặc nhiều relying party/tenant có cùng chuỗi tên. Nếu hệ thống hỗ trợ nhiều IdP, nên gắn danh tính với **issuer/relying-party registration + subject bền vững** và mapping nội bộ; không chỉ khóa authorization bằng chuỗi `alice` mà thiếu nguồn phát hành.

Một test cần tạo hai principal có cùng display name nhưng khác tenant/IdP và chứng minh không thể truy cập tài nguyên của nhau. Để làm được đầy đủ, mô hình `AppSamlPrincipal` nên được mở rộng với external issuer hoặc internal user ID theo thiết kế thực.

### Thiếu attribute quan trọng

Một assertion có chữ ký đúng vẫn có thể thiếu `tenant_id` hoặc group mà ứng dụng cần. Không nên cấp tenant mặc định có nhiều quyền hoặc tự gán `ROLE_REPORT_ADMIN` khi attribute rỗng. Tách hai bước:

1. **SAML authentication**: SP xác minh response theo protocol.
2. **Domain authorization mapping**: dữ liệu không đủ thì từ chối mapping, từ chối login theo chính sách hoặc tạo principal không có quyền truy cập tài nguyên.

Ví dụ `TrustedSamlIdentityFactory` ở mục 11 từ chối tenant trống. Quyết định từ chối hẳn login hay chỉ thiếu quyền là chính sách nghiệp vụ, không phải một hành vi cố định của mọi ứng dụng SAML.

### Trạng thái nhóm thay đổi sau khi session được tạo

SAML thường xác thực người dùng tại thời điểm SSO. Nếu quyền trong IdP bị thu hồi sau đó, `Authentication` đang nằm trong session SP **không tự cập nhật mọi thay đổi group**. Nếu cần cập nhật quyền nhanh, ứng dụng phải có giải pháp rõ ràng: session TTL, logout, re-authentication, truy vấn quyền nội bộ, hoặc cơ chế đồng bộ/thu hồi session. Test hậu đăng nhập chỉ sử dụng fixture tĩnh không phát hiện trễ đồng bộ quyền.

### CSRF và ACS POST

SAML browser SSO thường dùng POST để gửi `SAMLResponse` tới ACS. Spring Security SAML login có xử lý đặc thù cho endpoint này; khi tùy biến CSRF, cần kiểm tra chính xác rule và endpoint ACS. **Không nên tắt CSRF cho toàn bộ ứng dụng chỉ để một test SAML login POST thành công**, đặc biệt nếu ứng dụng vẫn sử dụng cookie/session cho form hoặc API thay đổi dữ liệu.

Ở các API `PUT`/`DELETE` sau đăng nhập SAML dùng cookie session, hãy thêm test CSRF dương và âm theo `SecurityFilterChain` thật. Một `403` do thiếu CSRF không chứng minh policy tenant hay authority đang hoạt động.

## 15. Servlet SAML login và WebFlux/Resource Server không phải cùng một cơ chế

`saml2Login()` và `Saml2WebSsoAuthenticationFilter` trong các ví dụ thuộc **Spring Security Servlet**. Khi kiến trúc có gateway/identity broker dùng SAML để đăng nhập rồi gọi một ứng dụng Reactive, ứng dụng Reactive có thể nhìn thấy **một dạng authentication khác** (chẳng hạn JWT Bearer đã được ký), không nhất thiết là `Saml2Authentication`.

| Kiến trúc | Nơi kiểm tra SAML | Tầng downstream nên test |
| --- | --- | --- |
| Servlet SP trực tiếp phục vụ báo cáo | Tại `saml2Login()` trong Spring MVC | `MockMvc` với `Saml2Authentication` custom cho quyền sau login |
| Servlet SP xác thực rồi cấp session cho các request của chính ứng dụng | Tại Servlet filter và SAML provider | MockMvc session + method security |
| SAML broker chuyển sang JWT cho Reactive API | Tại broker/IdP gateway | `WebTestClient` với `mockJwt()` để kiểm tra role/tenant, thêm test Bearer token thật |
| Ứng dụng chỉ làm OAuth2/OIDC Client | Tại OAuth2/OIDC login provider | `oauth2Login()`, `oidcLogin()` hoặc test flow thật, không gọi đó là SAML |

`mockJwt()` và `@WithMockUser` có giá trị để kiểm tra authorization trên API Reactive, nhưng **không xác minh SAML Response**. Nếu trust boundary là “SAML → broker → JWT”, phải có ít nhất một bài integration test kiểm chứng broker không phát JWT chứa quyền mà nguồn SAML chưa được phép cấp. Với JWT Resource Server, cần kiểm tra `iss`, `aud`, chữ ký, thời hạn và converter claims riêng.

Không nên tìm cách đưa một `Saml2Authentication` từ Servlet `SecurityContextHolder` vào WebFlux chỉ bằng việc copy ThreadLocal; WebFlux sử dụng Reactor Context và các authentication mechanism riêng được cấu hình trong reactive security chain.

## 16. Checklist test có ý nghĩa và tránh xanh sai

| Câu hỏi | Phép thử nên có | Bằng chứng |
| --- | --- | --- |
| Identity hậu SAML được tạo đúng kiểu? | Fixture `Saml2Authentication` + custom principal | `getPrincipal()`/`getName()` đúng |
| Group `reports.read` có map đúng không? | Unit test `ReportAuthorityMapper` | Có `ROLE_REPORT_READER` |
| Group lạ có vô tình thành admin không? | Unknown group và chuỗi giả mạo role | Không có `ROLE_REPORT_ADMIN` |
| Tenant của principal có được dùng không? | Alice tenant A, report A và report B | `200`/`403` tương ứng |
| Admin role được áp dụng tại URL không? | Admin/reader gọi `/api/reports/admin` | `200`/`403` |
| Có thiếu xác thực không? | Request không có authentication | Redirect/login theo entry point |
| Method security có hoạt động không? | Gọi Spring service bean trực tiếp | `AccessDeniedException` khi sai tenant |
| `@WithMockUser` có giả lập đầy đủ SAML domain identity không? | Test dùng mock user thường | Không qua được policy yêu cầu principal SAML |
| Authentication được giữ giữa các request không? | Test session riêng, sau đó flow SAML thật | Có session đúng theo thiết kế, không dùng lại fixture request |
| Signature/issuer/audience được xác minh không? | Signed SAMLResponse thật và phản hồi sai | Provider chấp nhận/từ chối đúng |
| Assertion thiếu tenant có bị từ chối? | Converter mapping âm tính | Không mặc định cấp quyền |
| Quyền bị thu hồi có làm session cũ thay đổi không? | Integration test đổi quyền/expire session | Đúng policy quản lý vòng đời phiên |
| Test có dùng secret/certificate production không? | Rà cấu hình IdP test | Chỉ dùng fixture và key test |

### Dấu hiệu test không kiểm tra điều bạn nghĩ

**Mọi test đều 403.** Có thể security chain, CSRF hoặc method annotation sai. Cần test Alice đọc report-a `200`, Bob đọc report-b `200` để làm đối chứng.

**Test admin xanh khi dùng @WithMockUser, nhưng SAML user thật bị từ chối.** Có thể ứng dụng chưa ánh xạ đúng attribute group từ assertion sang `GrantedAuthority`. Test mock user chỉ tạo sẵn role, không kiểm chứng converter.

**Test sau đăng nhập xanh dù certificate IdP sai.** Test hậu đăng nhập đã tiêm sẵn `Saml2Authentication`, vì thế không chạy validator. Phải có integration test SAML Response thật.

**Nhóm tên gần giống nhau được cấp cùng quyền.** Mapping tùy ý bằng `contains("admin")` hoặc ghép role từ giá trị raw dễ sai. Nên dùng danh sách group cho phép và so sánh chính xác.

**Dùng chung principal hoặc Authentication có thể thay đổi.** Test A thêm group admin rồi test B hưởng trạng thái đó. Mỗi lần tạo fixture phải có object/collection riêng, không cache một principal mutable cho cả suite.

**Tên user trong response khác NameID mà vẫn 200.** Có thể custom mapper dùng email/display name và không chuẩn hóa/định danh đúng. Cần kiểm tra hợp đồng subject với IdP và khóa liên kết người dùng.

**Khi logout, request sau vẫn được phép dù session phải hết hiệu lực.** Một test luôn dùng `authentication(...)` sẽ tiếp tục tạo identity giả lập; nó không thể kiểm chứng SLO/session logout. Cần thử với cùng session đã login qua flow thực và không tiêm authentication mới.

## 17. Bài tập thực hành

1. Tạo `AppSamlPrincipal` có `name`, `tenantId` và `groups`, dùng `Set.copyOf` để tránh bị sửa sau khi xây. Viết assertion kiểm tra Authentication và principal khác nhau qua hai lần gọi fixture.
2. Viết `ReportAuthorityMapper` chỉ cấp `ROLE_REPORT_READER` từ `reports.read` và `ROLE_REPORT_ADMIN` từ `reports.admin`. Kiểm tra group không nằm trong allowlist không tự trở thành role admin.
3. Tạo `Saml2Authentication` giả cho Alice tenant A có quyền đọc; dùng `MockMvc.with(authentication(...))` để GET report-a `200` và report-b `403`.
4. Tạo Bob tenant B có quyền admin. Kiểm tra `/api/reports/admin` được `200` nhưng Bob vẫn không thể dùng quyền admin để đọc report-a nếu chính sách giới hạn tenant.
5. Dùng `@WithMockUser(roles="REPORT_READER")` thay fixture SAML và quan sát policy yêu cầu `AppSamlPrincipal` từ chối. Giải thích vì sao đây là khác biệt giữa mock identity chung và SAML domain identity.
6. Viết `@WithSamlIdentity` và `WithSecurityContextFactory` để tạo context mới cho mỗi test. Chạy các test theo thứ tự bất kỳ và bật parallel sau khi bảo đảm không có shared mutable state.
7. Gọi `ReportService.read` trực tiếp từ Spring-managed bean dưới context Alice. Kiểm tra `AccessDeniedException` khi đọc report-b, sau đó `clearContext()` ở `finally`.
8. Viết test session sử dụng `MockHttpSession` chứa `SecurityContext` giả, rồi giải thích tại sao nó vẫn chưa chứng minh login callback đã xác minh chữ ký.
9. Thực hiện SAML SP-initiated flow với IdP kiểm thử ký bằng test certificate, gửi form `SAMLResponse` tới ACS và giữ session qua redirect. Không dùng `authentication(...)` trong request sau login; kiểm tra role/tenant cuối cùng từ converter thực.
10. Tạo phản hồi sai chữ ký, sai audience, sai `InResponseTo` hoặc hết hạn. Xác minh chúng bị từ chối **trước** khi áp dụng method authorization. Ghi rõ nơi lỗi xảy ra.
11. Cho IdP phát hành assertion hợp lệ nhưng thiếu `tenant_id` hoặc chứa group lạ. Xác định rõ chính sách ứng dụng: từ chối login hay cho login với ít quyền; viết test cho chính sách đó.
12. Nếu ứng dụng có SAML Single Logout, kiểm tra thay đổi custom converter không làm mất thông tin assertion cần cho logout; thử request lại sau logout với **session cũ** và không tạo authentication giả lập mới.

### Kết quả cần đạt

Người học cần phân biệt được **xác minh SAML Response** với **phân quyền sau SAML login**. `Saml2Authentication` cùng custom principal/authorities tạo ra một fixture chính xác để kiểm thử chính sách URL và service bằng `MockMvc`, `@PreAuthorize` và `@WithSecurityContext`. Nhưng fixture không kiểm tra chữ ký, audience, thời gian, replay, session creation hay logout. Một bộ kiểm thử mạnh phải có cả **test downstream nhanh** cho `200`/`403` và **integration test IdP/SP** để bảo vệ ranh giới trust của SAML.

### Tài liệu tham khảo

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — MockMvc Authentication Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — SAML Migration Guide](https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html)
- [OASIS — SAML 2.0 Specifications](https://docs.oasis-open.org/security/saml/v2.0/)
