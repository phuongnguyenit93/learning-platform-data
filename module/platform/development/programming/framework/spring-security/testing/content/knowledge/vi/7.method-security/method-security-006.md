# @Secured và @RolesAllowed khi được cấu hình hỗ trợ

## 1. Khi nào dùng hai annotation này?

Trong chương **Bảo mật phương thức** của module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive. Trong Spring Security, ngoài các biểu thức linh hoạt như @PreAuthorize, ứng dụng còn có thể dùng hai kiểu annotation gọn hơn để biểu diễn quyền theo vai trò:

- **@Secured** là annotation riêng của Spring Security, nhận các authority cần có để gọi method.
- **@RolesAllowed** thuộc chuẩn JSR-250/Jakarta Annotations, mô tả danh sách role được phép gọi method.

Hai annotation phù hợp khi chính sách đơn giản, chẳng hạn “chỉ ADMIN được duyệt” hoặc “ADMIN hay AUDITOR được xem báo cáo”. Chúng không có khả năng biểu đạt đầy đủ các điều kiện phức tạp theo tham số, chủ sở hữu hoặc kết quả trả về như SpEL của @PreAuthorize/@PostAuthorize.

Sau bài học, bạn có thể:

- Bật riêng hỗ trợ @Secured và JSR-250 trong method security.
- Phân biệt cách ghi authority của @Secured với role name của @RolesAllowed.
- Dùng @PermitAll và @DenyAll như các annotation JSR-250 đi kèm.
- Viết test được phép/bị từ chối bằng @WithMockUser và gọi Spring bean thật.
- Kiểm chứng kết quả qua MockMvc, phân biệt 401, 403 và 200 theo cấu hình HTTP.
- Nhận biết khác biệt namespace javax/jakarta và giới hạn khi chuyển cấu hình sang WebFlux.

> **Phạm vi phiên bản:** Ví dụ Servlet chính dùng Spring Security 6.x, Spring Boot 3.x và Jakarta Annotations. Spring Security 7.x tiếp tục hỗ trợ các annotation này. Với Spring Security 5.x, kiểm tra API đã resolve; dự án cũ thường dùng @EnableGlobalMethodSecurity. Cấu hình Servlet và Reactive là hai cơ chế khác nhau, không dùng lẫn annotation bật bảo mật.

## 2. So sánh @Secured, @RolesAllowed và @PreAuthorize

| Annotation | Thuộc hệ sinh thái | Cách khai báo quyền | Bật hỗ trợ trong Servlet |
|---|---|---|---|
| @Secured | Spring Security | Chuỗi authority so khớp trực tiếp, thường có tiền tố ROLE_ | @EnableMethodSecurity(securedEnabled = true) |
| @RolesAllowed | JSR-250/Jakarta | Tên role; Spring Security mặc định thêm ROLE_ khi kiểm tra | @EnableMethodSecurity(jsr250Enabled = true) |
| @PreAuthorize | Spring Security SpEL | Biểu thức role, authority, tham số, bean policy... | Bật mặc định bởi @EnableMethodSecurity |

Spring Security mô tả @Secured là lựa chọn legacy cho authorization. @PreAuthorize được khuyến nghị khi cần biểu đạt chính sách mới hoặc phức tạp hơn. JSR-250 là chuẩn annotation độc lập với Spring, hữu ích khi codebase cần annotation vai trò quen thuộc trong hệ sinh thái Jakarta.

Ví dụ cùng một ý định “chỉ admin được duyệt”:

~~~java
@Secured("ROLE_ADMIN")
public void approveWithSecured(String id) {
    // ...
}
~~~

~~~java
@RolesAllowed("ADMIN")
public void approveWithRolesAllowed(String id) {
    // ...
}
~~~

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void approveWithExpression(String id) {
    // ...
}
~~~

Các cách viết trên tương ứng với cấu hình role prefix mặc định. Tuy nhiên, cơ chế kiểm tra và cấu hình bật annotation khác nhau; không thay một annotation bằng annotation khác rồi giữ nguyên chuỗi quyền mà chưa kiểm tra.

## 3. Bật hỗ trợ annotation trong Servlet

Một điểm dễ bỏ sót: @EnableMethodSecurity mặc định bật nhóm annotation pre/post, nhưng **không tự bật @Secured hoặc JSR-250**. Hãy cấu hình rõ ràng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
~~~

Hai thuộc tính có ý nghĩa riêng:

- **securedEnabled = true** đăng ký interceptor cho @Secured.
- **jsr250Enabled = true** đăng ký interceptor cho @RolesAllowed, @PermitAll và @DenyAll.

Nếu chỉ dùng @Secured thì chỉ cần bật securedEnabled. Nếu chỉ dùng @RolesAllowed hoặc annotation JSR-250 khác thì chỉ cần bật jsr250Enabled. Có thể bật cả hai trong cùng application context nếu dự án thực sự dùng cả hai họ annotation.

Spring Boot Starter Security không tự bật method-level authorization. Class cấu hình phải được nạp vào application context, service phải là Spring bean và lời gọi cần đi qua proxy/interceptor. Nếu test tự tạo service bằng new, annotation không được áp dụng theo proxy mode thông thường.

### Cấu hình cũ trong Spring Security 5.x

Trong một số dự án Spring Security 5.x, bạn sẽ thấy:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

@Configuration
@EnableGlobalMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class LegacyMethodSecurityConfig {
}
~~~

@EnableMethodSecurity đã có từ Spring Security 5.6 và là cấu hình hiện đại. Với Spring Security 6/7, dùng @EnableMethodSecurity; tránh mang ví dụ cũ sang phiên bản mới mà không kiểm tra khả năng tương thích.

## 4. Khác biệt quan trọng: authority literal và role prefix

Đây là chỗ dễ viết sai nhất trong test.

### 4.1. @Secured so khớp authority

@Secured nhận chuỗi authority cần có. Nếu khai báo:

~~~java
@Secured("ROLE_ADMIN")
public String adminDashboard() {
    return "ADMIN-DASHBOARD";
}
~~~

Authentication cần có GrantedAuthority chính xác là ROLE_ADMIN. Vì vậy:

- @WithMockUser(roles = "ADMIN") tạo authority ROLE_ADMIN và phù hợp.
- @WithMockUser(authorities = "ROLE_ADMIN") cũng phù hợp vì cấp đúng chuỗi.
- @WithMockUser(authorities = "ADMIN") không phù hợp vì chuỗi thiếu ROLE_.

@Secured cũng có thể kiểm tra authority nghiệp vụ không phải role:

~~~java
@Secured("invoice:approve")
public String approveInvoice(String id) {
    return "APPROVED-" + id;
}
~~~

Trong trường hợp này, principal phải có authority invoice:approve. Annotation có tên Secured nhưng không bắt buộc giá trị phải là role; nó kiểm tra các authority được khai báo.

Nhiều giá trị trong @Secured được hiểu là các lựa chọn được phép: người gọi có một trong các authority phù hợp là đủ. Ví dụ:

~~~java
@Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})
public String auditReport() {
    return "AUDIT-REPORT";
}
~~~

### 4.2. @RolesAllowed nhận tên role

Với JSR-250, viết tên role không kèm tiền tố mặc định:

~~~java
import jakarta.annotation.security.RolesAllowed;

@RolesAllowed("ADMIN")
public String adminDashboard() {
    return "ADMIN-DASHBOARD";
}
~~~

Spring Security mặc định ánh xạ tên ADMIN thành authority ROLE_ADMIN. Do đó @WithMockUser(roles = "ADMIN") phù hợp với @RolesAllowed("ADMIN").

Không viết @RolesAllowed("ROLE_ADMIN") trong cấu hình mặc định, vì Spring Security sẽ thêm role prefix ROLE_ và khi đó chuỗi được kiểm tra có thể thành ROLE_ROLE_ADMIN. Chỉ dùng cách ghi khác khi bạn đã chủ động tùy biến role prefix và hiểu chính xác manager đang sử dụng.

Nhiều tên role trong @RolesAllowed cũng biểu thị danh sách role được phép:

~~~java
@RolesAllowed({"ADMIN", "AUDITOR"})
public String auditReport() {
    return "AUDIT-REPORT";
}
~~~

Người có một trong các role được khai báo có thể gọi method. @RolesAllowed mô tả role, nên với quyền kiểu document:read hoặc invoice:approve không có dạng role, hãy cân nhắc @Secured hoặc @PreAuthorize.

### 4.3. Bảng đối chiếu dữ liệu test

| Cấu hình method | Authentication trong test | Kết quả |
|---|---|---|
| @Secured("ROLE_ADMIN") | @WithMockUser(roles = "ADMIN") | Cho phép |
| @Secured("ROLE_ADMIN") | @WithMockUser(authorities = "ADMIN") | Từ chối |
| @Secured("invoice:approve") | @WithMockUser(authorities = "invoice:approve") | Cho phép |
| @RolesAllowed("ADMIN") | @WithMockUser(roles = "ADMIN") | Cho phép |
| @RolesAllowed("ADMIN") | @WithMockUser(authorities = "ROLE_ADMIN") | Cho phép |
| @RolesAllowed("ADMIN") | @WithMockUser(authorities = "ADMIN") | Từ chối với role prefix mặc định |
| @RolesAllowed({"ADMIN", "AUDITOR"}) | @WithMockUser(roles = "AUDITOR") | Cho phép |

Thuộc tính roles và authorities của @WithMockUser phục vụ hai cách tạo GrantedAuthority khác nhau. Khi dùng roles, Spring Test tự thêm ROLE_. Khi dùng authorities, chuỗi được giữ nguyên. Không khai báo cả hai với các giá trị khác rỗng trong cùng một @WithMockUser.

## 5. Annotation JSR-250 bổ sung: @PermitAll và @DenyAll

Khi đã bật jsr250Enabled, Spring Security cũng hỗ trợ hai annotation JSR-250:

- **@PermitAll** cho phép mọi caller gọi method theo chính sách method security.
- **@DenyAll** từ chối mọi caller, kể cả principal có role quản trị.

Ví dụ:

~~~java
import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.stereotype.Service;

@Service
public class Jsr250Operations {

    @RolesAllowed("ADMIN")
    public String approve() {
        return "APPROVED";
    }

    @RolesAllowed({"ADMIN", "AUDITOR"})
    public String readAuditReport() {
        return "AUDIT-REPORT";
    }

    @PermitAll
    public String publicStatus() {
        return "SERVICE-AVAILABLE";
    }

    @DenyAll
    public String disabledOperation() {
        return "UNAVAILABLE";
    }
}
~~~

@PermitAll chỉ mô tả quyết định ở tầng method. Nếu request HTTP vẫn bị URL rule, authentication entry point hoặc filter khác chặn, caller không nhất thiết truy cập được endpoint. Ngược lại, @DenyAll có thể hữu ích khi method cần bị khóa có chủ đích trong khi vẫn giữ lại implementation để tham chiếu hoặc phục vụ một luồng khác.

Không nhầm @PermitAll với @PreAuthorize("permitAll") trong mọi khía cạnh cấu hình; chúng thuộc các annotation/interceptor khác nhau. Nếu dùng nhiều loại method-security annotation trong một ứng dụng, hãy quy định rõ convention và tránh đặt nhiều họ annotation lên cùng một method để tạo các điều kiện khó hiểu.

## 6. Namespace javax và jakarta của @RolesAllowed

Tên annotation vẫn là RolesAllowed, nhưng package phụ thuộc thế hệ Jakarta/Java EE mà ứng dụng dùng:

| Nền tảng thường gặp | Import |
|---|---|
| Spring Boot 3.x / Spring Framework 6.x / Spring Security 6.x | jakarta.annotation.security.RolesAllowed |
| Dự án Spring Boot 2.x / Spring Security 5.x còn dùng Java EE namespace | javax.annotation.security.RolesAllowed |

Ví dụ import hiện đại:

~~~java
import jakarta.annotation.security.RolesAllowed;
~~~

Ví dụ import cũ:

~~~java
import javax.annotation.security.RolesAllowed;
~~~

Không trộn hai package trong cùng một application context. Đây là hai class khác nhau dù cùng tên annotation. Nếu compiler không tìm thấy jakarta.annotation.security.RolesAllowed, kiểm tra dependency Jakarta Annotations; tùy dependency management của ứng dụng, có thể cần khai báo jakarta.annotation:jakarta.annotation-api. Với dự án Spring Security 5.x dùng javax, hãy giữ namespace tương ứng và đối chiếu phiên bản API.

@Secured không thay đổi package theo chuyển đổi javax/jakarta:

~~~java
import org.springframework.security.access.annotation.Secured;
~~~

## 7. Tổ chức service để kiểm thử

Tách ví dụ thành hai service để mỗi họ annotation có cấu hình và test rõ ràng.

~~~java
// LegacyAuthorityService.java
import org.springframework.security.access.annotation.Secured;
import org.springframework.stereotype.Service;

@Service
public class LegacyAuthorityService {

    @Secured("ROLE_ADMIN")
    public String adminTask() {
        return "ADMIN-TASK";
    }

    @Secured({"ROLE_ADMIN", "ROLE_EDITOR"})
    public String editContent() {
        return "CONTENT-EDITED";
    }

    @Secured("invoice:approve")
    public String approveInvoice() {
        return "INVOICE-APPROVED";
    }
}
~~~

~~~java
// Jsr250Service.java
import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.stereotype.Service;

@Service
public class Jsr250Service {

    @RolesAllowed("ADMIN")
    public String adminTask() {
        return "ADMIN-TASK";
    }

    @RolesAllowed({"ADMIN", "AUDITOR"})
    public String auditTask() {
        return "AUDIT-TASK";
    }

    @PermitAll
    public String publicTask() {
        return "PUBLIC-TASK";
    }

    @DenyAll
    public String closedTask() {
        return "CLOSED";
    }
}
~~~

Các method được gọi thông qua bean do Spring inject. Không dùng new LegacyAuthorityService() hoặc new Jsr250Service() trong test để kết luận annotation có hiệu lực, vì như vậy bỏ qua method-security proxy.

## 8. Kiểm thử trực tiếp bằng @WithMockUser

Dùng @SpringBootTest để Spring nạp cấu hình method security và hai service thật. Các test dương tính và âm tính:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class LegacyMethodAnnotationsTest {

    @Autowired
    LegacyAuthorityService legacy;

    @Autowired
    Jsr250Service jsr250;

    @Test
    @WithMockUser(roles = "ADMIN")
    void securedAllowsAdminRole() {
        assertEquals("ADMIN-TASK", legacy.adminTask());
    }

    @Test
    @WithMockUser(roles = "USER")
    void securedDeniesOrdinaryUser() {
        assertThrows(AccessDeniedException.class,
            () -> legacy.adminTask());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void securedRequiresExactAuthority() {
        assertThrows(AccessDeniedException.class,
            () -> legacy.adminTask());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void securedAllowsOneOfDeclaredAuthorities() {
        assertEquals("CONTENT-EDITED", legacy.editContent());
    }

    @Test
    @WithMockUser(authorities = "invoice:approve")
    void securedSupportsBusinessAuthority() {
        assertEquals("INVOICE-APPROVED", legacy.approveInvoice());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void rolesAllowedMapsRoleNameToDefaultRoleAuthority() {
        assertEquals("ADMIN-TASK", jsr250.adminTask());
    }

    @Test
    @WithMockUser(roles = "AUDITOR")
    void rolesAllowedAcceptsAnotherDeclaredRole() {
        assertEquals("AUDIT-TASK", jsr250.auditTask());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void rolesAllowedUsesRolePrefixByDefault() {
        assertThrows(AccessDeniedException.class,
            () -> jsr250.adminTask());
    }

    @Test
    @WithAnonymousUser
    void permitAllAllowsAnonymousMethodInvocation() {
        assertEquals("PUBLIC-TASK", jsr250.publicTask());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void denyAllRejectsEvenAdministrator() {
        assertThrows(AccessDeniedException.class,
            () -> jsr250.closedTask());
    }
}
~~~

Các test này chứng minh từng quy tắc độc lập:

- Test roles = ADMIN xác nhận @Secured("ROLE_ADMIN") và @RolesAllowed("ADMIN") có thể nhận cùng authority ROLE_ADMIN, dù hai annotation dùng cách khai báo khác nhau.
- Test authorities = ADMIN cố ý tạo chuỗi không có ROLE_ để chứng minh sự khác biệt.
- Test invoice:approve chứng minh @Secured có thể dùng custom authority, không chỉ role.
- Test @PermitAll và @DenyAll chứng minh hai annotation JSR-250 có hiệu lực khi jsr250Enabled được bật.

Nếu bỏ securedEnabled hoặc jsr250Enabled trong cấu hình, các test tương ứng không còn chứng minh đúng chính sách; một method có thể được gọi như method bình thường vì interceptor chưa được đăng ký. Vì vậy, **test bị từ chối** là phần bắt buộc, không chỉ test admin thành công.

## 9. Kiểm thử qua HTTP Servlet bằng MockMvc

Service test chứng minh method interceptor. MockMvc bổ sung kiểm tra controller, filter chain và cách lỗi authorization được ánh xạ sang HTTP.

Controller gọi service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/legacy")
public class LegacyAuthorizationController {

    private final LegacyAuthorityService legacy;
    private final Jsr250Service jsr250;

    public LegacyAuthorizationController(
            LegacyAuthorityService legacy,
            Jsr250Service jsr250) {
        this.legacy = legacy;
        this.jsr250 = jsr250;
    }

    @GetMapping("/secured")
    public String secured() {
        return legacy.adminTask();
    }

    @GetMapping("/roles-allowed")
    public String rolesAllowed() {
        return jsr250.adminTask();
    }

    @GetMapping("/public")
    public String publicStatus() {
        return jsr250.publicTask();
    }
}
~~~

Để cô lập method authorization trong bài thực hành, cấu hình HTTP Basic và cho phép request tới controller:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DemoHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình permitAll() toàn cục chỉ nhằm làm rõ lớp method security trong bài học. Ứng dụng thực tế vẫn cần quy tắc URL, xác thực, CSRF và xử lý lỗi phù hợp.

Test MockMvc với Spring Boot 3.x:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LegacyMethodAnnotationsHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void adminCanCallSecuredEndpoint() throws Exception {
        mvc.perform(get("/legacy/secured")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN-TASK"));
    }

    @Test
    void ordinaryUserGetsForbiddenFromSecuredEndpoint() throws Exception {
        mvc.perform(get("/legacy/secured")
                .with(user("lan").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanCallRolesAllowedEndpoint() throws Exception {
        mvc.perform(get("/legacy/roles-allowed")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN-TASK"));
    }

    @Test
    void userWithoutRoleGetsForbiddenFromRolesAllowedEndpoint()
            throws Exception {
        mvc.perform(get("/legacy/roles-allowed")
                .with(user("lan").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCallerGets401WithHttpBasicEntryPoint() throws Exception {
        mvc.perform(get("/legacy/secured"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Các status trong ví dụ phụ thuộc HTTP Basic và cấu hình filter chain đã nêu:

- **200 OK**: principal có authority phù hợp, method được gọi.
- **403 Forbidden**: principal đã được xác thực nhưng thiếu authority/role.
- **401 Unauthorized**: caller chưa xác thực; HTTP Basic entry point yêu cầu xác thực khi method security từ chối anonymous.

Nếu ứng dụng dùng form login, entry point có thể redirect thay vì trả 401. Nếu URL rule chặn request trước controller, 403 có thể đến từ filter chain chứ không phải @Secured/@RolesAllowed. Vì vậy hãy kết hợp test trực tiếp service thật với test HTTP. Khi dùng @WebMvcTest và thay service bằng mock, test controller không còn chứng minh annotation trên service thật.

## 10. JWT, OAuth2 và OIDC: annotation kiểm tra authorities đã được cấp

@Secured và @RolesAllowed không đọc trực tiếp claim JWT. Chúng kiểm tra GrantedAuthority trong Authentication. Vì thế, khi dùng resource server, cần bảo đảm converter tạo đúng authority mà annotation đòi hỏi.

Ví dụ method:

~~~java
@Secured("ROLE_ADMIN")
public String approve() {
    return "APPROVED";
}
~~~

Nếu converter JWT tạo authority ROLE_ADMIN, có thể kiểm tra qua MockMvc:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

mvc.perform(get("/legacy/secured")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ADMIN"))))
    .andExpect(status().isOk());
~~~

Đoạn trên cần endpoint thực sự gọi method có @Secured("ROLE_ADMIN"). jwt() tạo Authentication giả lập để kiểm tra authorization; nó không xác minh chữ ký token, issuer, audience hoặc việc gọi identity provider. OAuth2 Login/OIDC Login có helper riêng như oauth2Login() và oidcLogin(); các test đó cũng cần cấp authority phù hợp với annotation.

Một JWT có scope documents.read thường được chuyển thành SCOPE_documents.read, không tự động trở thành ROLE_ADMIN. Nếu endpoint dùng @RolesAllowed("ADMIN"), converter phải cấp ROLE_ADMIN (hoặc role prefix được tùy chỉnh). Hãy kiểm tra authority sau chuyển đổi thay vì giả định tên scope và tên role là một.

## 11. WebFlux/Reactive: cấu hình riêng và giới hạn annotation

Reactive method security sử dụng Reactor Context và cần phương thức trả về Publisher như Mono hoặc Flux để tích hợp với context. Cấu hình cơ bản:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {
}
~~~

Trong Spring Security 6.x, Reactive AuthorizationManager mode được bật mặc định; với Spring Security 5.8 có thể gặp cấu hình tường minh useAuthorizationManager = true. Reactive method security có API và interceptor riêng, không dùng @EnableMethodSecurity(securedEnabled = true) như Servlet.

Tài liệu Reactive 6.5 mô tả AuthorizationManager mode là tương thích JSR-250, nhưng ví dụ Reactive chủ yếu trình bày @PreAuthorize và không cung cấp cờ securedEnabled tương đương của Servlet. Vì vậy, đừng sao chép cấu hình bật @Secured của Servlet sang Reactive hoặc suy luận từ một test Servlet rằng annotation đã được kích hoạt trên WebFlux. Nếu reactive service cần policy role có thể dùng nhất quán, @PreAuthorize("hasRole('ADMIN')") là lựa chọn biểu thức được tài liệu Reactive trình bày trực tiếp; nếu dự án muốn dùng @RolesAllowed, hãy xác minh với đúng phiên bản bằng integration test WebFlux.

Ví dụ reactive service dùng policy biểu thức:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveAdminService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminTask() {
        return Mono.just("REACTIVE-ADMIN-TASK");
    }
}
~~~

WebTestClient kiểm chứng đường đi HTTP với reactive mock user:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class ReactiveAdminSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void adminCanInvokeReactiveMethod() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/reactive/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("REACTIVE-ADMIN-TASK");
    }

    @Test
    void ordinaryUserIsDenied() {
        client.mutateWith(mockUser("lan").roles("USER"))
            .get().uri("/reactive/admin")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Ví dụ cần một controller WebFlux GET /reactive/admin gọi ReactiveAdminService.adminTask() và một SecurityWebFilterChain phù hợp. Test cần nạp đúng ReactiveSecurityConfig và Spring WebFlux application context. WebTestClient gửi request và subscribe Mono, vì vậy có thể quan sát quyết định authorization. Nếu gọi service trực tiếp, dùng StepVerifier trong reactive security context phù hợp.

**Phạm vi quan trọng:** đoạn WebFlux trên kiểm thử @PreAuthorize, không khẳng định @Secured đã được bật trong Reactive. Với bài toán cụ thể của @Secured và @RolesAllowed, phần kiểm thử đầy đủ và cấu hình cờ bật ở các mục trước là dành cho Servlet method security; Reactive cần xác nhận hỗ trợ annotation theo release và API riêng.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách kiểm tra |
|---|---|---|
| @Secured có mặt nhưng user sai quyền vẫn gọi được. | Chưa bật securedEnabled hoặc bean không qua Spring proxy. | Kiểm tra @EnableMethodSecurity(securedEnabled = true), inject bean thật và thêm negative test. |
| @RolesAllowed không có tác dụng. | Chưa bật jsr250Enabled hoặc import sai namespace. | Bật jsr250Enabled, kiểm tra jakarta/javax và dependency. |
| @Secured("ROLE_ADMIN") từ chối @WithMockUser(roles = "ADMIN"). | Có thể test không gọi bean đã được proxy hoặc quyền thực tế bị thay đổi. | Kiểm tra authorities của Authentication và test trực tiếp service thật. |
| @Secured("ADMIN") bị từ chối. | @Secured so khớp authority literal; test cấp ROLE_ADMIN. | Dùng @Secured("ROLE_ADMIN") hoặc cấp authority ADMIN có chủ đích. |
| @RolesAllowed("ROLE_ADMIN") bị từ chối. | Role prefix mặc định thêm ROLE_ thành ROLE_ROLE_ADMIN. | Dùng @RolesAllowed("ADMIN") trong cấu hình mặc định. |
| Test roles và authorities cho kết quả khác nhau. | roles tự thêm ROLE_; authorities giữ nguyên chuỗi. | Dùng đúng thuộc tính @WithMockUser cho annotation đang kiểm tra. |
| @PermitAll không truy cập được qua HTTP. | HTTP filter chain vẫn yêu cầu authentication hoặc URL policy khác chặn. | Phân biệt quyết định method với quyết định request-level. |
| @DenyAll không từ chối trong test. | JSR-250 interceptor chưa được bật hoặc test gọi đối tượng không qua proxy. | Bật jsr250Enabled và gọi bean thật. |
| Test MockMvc nhận 302 thay vì 401. | Ứng dụng dùng form-login entry point. | Kiểm tra authentication entry point thay vì giả định HTTP Basic. |
| Test MockMvc nhận 403 nhưng method annotation không chạy. | URL rule/CSRF chặn request trước khi vào service. | Kết hợp test service trực tiếp với test HTTP. |
| JWT scope không qua @RolesAllowed. | Scope được ánh xạ thành SCOPE_..., không phải ROLE_ADMIN. | Kiểm tra JWT converter và GrantedAuthority thực tế. |
| Chạy trên WebFlux nhưng annotation Servlet không hoạt động. | Reactive method security dùng cấu hình và interceptor riêng. | Kiểm tra API Reactive của phiên bản; dùng @PreAuthorize nếu cần policy portable. |

Không gắn @Secured và @RolesAllowed cùng lúc lên một method để mong hai điều kiện tự động kết hợp theo AND. Hai annotation thuộc hai interceptor khác nhau và có thể tạo cấu hình khó dự đoán hoặc xung đột. Nếu cần nhiều điều kiện cùng lúc, hãy biểu đạt rõ bằng một @PreAuthorize, ví dụ hasRole('ADMIN') and hasAuthority('invoice:approve').

## 13. Bài thực hành và tiêu chí hoàn thành

1. Bật @EnableMethodSecurity(securedEnabled = true) và tạo một service có @Secured("ROLE_ADMIN"). Dùng @WithMockUser(roles = "ADMIN") để chứng minh được phép, roles = "USER" để chứng minh bị từ chối.
2. Thêm @Secured("invoice:approve") và kiểm thử bằng authorities = "invoice:approve". Giải thích vì sao roles = "ADMIN" không tự cấp quyền nghiệp vụ này.
3. Bật jsr250Enabled = true, tạo @RolesAllowed("ADMIN") và @RolesAllowed({"ADMIN", "AUDITOR"}). Kiểm tra role prefix mặc định qua roles và authorities.
4. Thêm @PermitAll và @DenyAll. Kiểm tra anonymous được gọi method công khai và cả admin vẫn bị từ chối method đóng.
5. Tạo MockMvc controller gọi service thật, kiểm tra 200/403/401 với HTTP Basic. Thử thay entry point và giải thích thay đổi phản hồi.
6. Tạo JWT mock có ROLE_ADMIN rồi kiểm thử endpoint; đổi authority thành SCOPE_documents.read và quan sát kết quả khi policy vẫn đòi role.
7. Với WebFlux, bật @EnableReactiveMethodSecurity, tạo method trả Mono có @PreAuthorize và dùng WebTestClient kiểm thử role admin/user. Nếu cần @RolesAllowed trên Reactive, xác minh hỗ trợ của release cụ thể thay vì dùng cấu hình Servlet.
8. So sánh một policy đơn giản bằng @Secured/@RolesAllowed với biểu thức tương đương bằng @PreAuthorize; nêu trường hợp cần tham số hoặc nhiều điều kiện thì biểu thức có lợi hơn.

**Tiêu chí hoàn thành:** Người học bật đúng interceptor cho từng annotation, phân biệt chính xác authority literal với role name có tiền tố, và chứng minh được cả ca được phép lẫn bị từ chối bằng bean Spring thật. Test HTTP cần phản ánh filter chain đang cấu hình; test Reactive phải dùng reactive context và WebTestClient đúng stack.

## Tài liệu tham khảo

- [Spring Security 6.5 — Servlet Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — EnableMethodSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Security 6.5 — Jsr250AuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/Jsr250AuthorizationManager.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)

