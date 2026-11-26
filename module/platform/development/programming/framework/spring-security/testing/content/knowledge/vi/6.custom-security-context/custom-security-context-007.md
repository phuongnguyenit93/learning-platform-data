# Tham số hóa annotation cho nhiều vai trò hoặc tenant

## 1. Vì sao cần annotation kiểm thử có tham số?

Một hệ thống thường có nhiều nhóm người dùng và nhiều phạm vi dữ liệu. Ví dụ, `FINANCE` có thể xem hóa đơn, `AUDITOR` cũng được xem nhưng không được phát hành; một người dùng có thể thao tác trong `tenant-a` nhưng không có quyền đọc `tenant-b`. Nếu mỗi kịch bản lại viết một annotation riêng như `@WithFinanceUser`, `@WithAuditorUser`, `@WithTenantAUser`, số lượng fixture sẽ tăng nhanh và khó bảo trì.

Ta có thể định nghĩa **một annotation kiểm thử có tham số** để mô tả danh tính, tenant đang hoạt động, nhiều role và các permission cụ thể. Factory đọc những thuộc tính này rồi tạo `Authentication` với danh sách `GrantedAuthority` tương ứng. Mỗi test chỉ cần khai báo dữ liệu của kịch bản:

```java
@WithTenantUser(
    userId = "u-42",
    tenantId = "tenant-a",
    roles = { "FINANCE", "AUDITOR" },
    permissions = { "invoice:read" }
)
```

Trong module **SPRING_SECURITY_TESTING**, cách làm này hỗ trợ kiểm chứng xác thực và phân quyền trên Servlet/Reactive bằng `spring-security-test`, `MockMvc`, `WebTestClient` và các authentication giả lập. Bài học tập trung vào việc biểu diễn nhiều role và tenant bằng một fixture linh hoạt, đồng thời kiểm tra cả trường hợp được phép lẫn bị từ chối.

Sau bài này, bạn có thể:

- Thiết kế annotation nhận `userId`, `tenantId`, nhiều role và nhiều permission.
- Ánh xạ role thành authority có tiền tố `ROLE_` và giữ permission theo chuỗi nguyên văn.
- Dùng `hasRole`, `hasAnyRole`, `hasAuthority` và `hasAnyAuthority` đúng với chính sách.
- Viết các test cho nhiều role, thiếu role, thiếu permission và tenant không khớp.
- Tái sử dụng annotation ở cấp lớp/phương thức mà vẫn giữ mỗi kịch bản độc lập.
- Nhận biết khi nào một `tenantId` đại diện tenant đang hoạt động và khi nào cần kiểm tra membership nhiều tenant.

## 2. Phân biệt role, permission và tenant

Role và permission thường được dùng cùng nhau nhưng biểu diễn hai chiều khác nhau của chính sách:

| Thuộc tính | Ý nghĩa | Ví dụ | Ánh xạ trong Spring Security |
| --- | --- | --- | --- |
| Role | Nhóm trách nhiệm của người dùng | `FINANCE`, `AUDITOR` | `ROLE_FINANCE`, `ROLE_AUDITOR` |
| Permission | Hành động cụ thể được phép thực hiện | `invoice:read`, `invoice:issue` | `invoice:read`, `invoice:issue` |
| Tenant | Phạm vi dữ liệu mà danh tính hiện tại được phép thao tác | `tenant-a` | Thường là thuộc tính principal/claim và được policy kiểm tra riêng |

Theo quy ước mặc định, `hasRole('FINANCE')` kiểm tra authority `ROLE_FINANCE`; đối số của `hasRole` không cần viết tiền tố. `hasAuthority('invoice:read')` so sánh chuỗi chính xác và không tự thêm tiền tố. Vì vậy, factory phải quy định rõ cách chuyển role và permission:

- Giá trị `roles = { "FINANCE" }` sinh `ROLE_FINANCE`.
- Giá trị `permissions = { "invoice:read" }` sinh `invoice:read`.
- `tenantId = "tenant-a"` được đưa vào principal; nó không tự trở thành role hay permission.

Không dùng `roles = { "ROLE_FINANCE" }` nếu factory tự thêm tiền tố `ROLE_`, vì kết quả sẽ thành `ROLE_ROLE_FINANCE`. Cũng không biến tenant thành authority nếu policy của ứng dụng yêu cầu so sánh tenant với tài nguyên. Role/permission trả lời *người dùng được làm gì*; tenant trả lời *người dùng được làm trên phạm vi nào*.

## 3. Thiết kế annotation có nhiều tham số

Ví dụ xuyên suốt là API đọc hóa đơn trong ứng dụng đa tenant. Principal tối giản đặt ở `src/main/java/com/example/security/TenantPrincipal.java`:

```java
package com.example.security;

import java.security.Principal;

public record TenantPrincipal(String userId, String tenantId)
        implements Principal {

    public TenantPrincipal {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId không được rỗng");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId không được rỗng");
        }
    }

    @Override
    public String getName() {
        return userId;
    }
}
```

Annotation kiểm thử đặt ở `src/test/java/com/example/security/WithTenantUser.java`:

```java
package com.example.security;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Target({ ElementType.METHOD, ElementType.TYPE })
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@Documented
@WithSecurityContext(factory = WithTenantUserFactory.class)
public @interface WithTenantUser {

    String userId() default "u-42";

    String tenantId() default "tenant-a";

    // Giá trị role không kèm ROLE_; factory chịu trách nhiệm thêm tiền tố.
    String[] roles() default {};

    // Permission được giữ nguyên chuỗi.
    String[] permissions() default {};
}
```

Annotation dùng `String[]` để một test có thể cấp nhiều role hoặc permission. Mặc định cả hai danh sách đều rỗng, giúp fixture tuân theo nguyên tắc quyền tối thiểu: test phải khai báo rõ những gì nó cần. `@Retention(RUNTIME)` cho phép Spring Security Test đọc tham số khi chạy; `@WithSecurityContext` kết nối annotation với factory.

## 4. Factory ánh xạ role và permission thành authorities

Đặt `WithTenantUserFactory.java` trong `src/test/java/com/example/security`:

```java
package com.example.security;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithTenantUserFactory
        implements WithSecurityContextFactory<WithTenantUser> {

    @Override
    public SecurityContext createSecurityContext(WithTenantUser marker) {
        TenantPrincipal principal =
                new TenantPrincipal(marker.userId(), marker.tenantId());

        Set<GrantedAuthority> authorities = new LinkedHashSet<>();

        for (String role : marker.roles()) {
            String normalizedRole = requireValue(role, "role");
            if (normalizedRole.startsWith("ROLE_")) {
                throw new IllegalArgumentException(
                        "Khai báo role không kèm tiền tố ROLE_: " + normalizedRole);
            }
            authorities.add(new SimpleGrantedAuthority("ROLE_" + normalizedRole));
        }

        for (String permission : marker.permissions()) {
            authorities.add(new SimpleGrantedAuthority(
                    requireValue(permission, "permission")));
        }

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, null, authorities);

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }

    private static String requireValue(String value, String field) {
        if (value == null || value.isBlank() || !value.equals(value.trim())) {
            throw new IllegalArgumentException(
                    field + " không được rỗng hoặc có khoảng trắng thừa");
        }
        return value;
    }
}
```

Factory thực hiện ba việc tách biệt:

1. Tạo `TenantPrincipal` từ `userId` và `tenantId` của annotation.
2. Chuyển từng role thành `ROLE_` cộng tên role; permission được giữ nguyên.
3. Tạo `Authentication` và `SecurityContext` mới cho lần chạy test này.

`LinkedHashSet` loại bỏ authority trùng lặp mà vẫn giữ thứ tự khai báo ổn định, giúp assertion dễ đọc. Hàm `requireValue` khiến cấu hình fixture sai (chuỗi rỗng hoặc khoảng trắng thừa) thất bại ngay lúc chuẩn bị context. Factory không truy vấn membership thật; vì vậy, nếu ứng dụng có nhiều tenant, test phải khai báo tenant đã được xác minh trong kịch bản hoặc dùng một factory khác có service kiểm tra membership.

`UsernamePasswordAuthenticationToken.authenticated(...)` chỉ mô phỏng authentication đã hoàn tất để kiểm thử authorization. Nó không chạy password authentication. Nếu controller/service production yêu cầu một subtype `Authentication` khác, factory phải tạo đúng loại đó theo hợp đồng ứng dụng.

## 5. Chính sách ứng dụng sử dụng role, permission và tenant

Tạo component kiểm tra tenant trong `src/main/java/com/example/security/TenantPolicy.java`:

```java
package com.example.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantPolicy")
public class TenantPolicy {

    public boolean matches(Authentication authentication, String requestedTenant) {
        return authentication != null
                && authentication.isAuthenticated()
                && authentication.getPrincipal() instanceof TenantPrincipal principal
                && principal.tenantId().equals(requestedTenant);
    }
}
```

Controller yêu cầu người dùng có một trong hai role `FINANCE` hoặc `AUDITOR`, đồng thời có permission `invoice:read` và tenant khớp:

```java
package com.example.security;

import java.util.Map;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.parameters.P;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants")
public class InvoiceController {

    @GetMapping("/{tenantId}/invoices")
    @PreAuthorize("hasAnyRole('FINANCE', 'AUDITOR') "
            + "and hasAuthority('invoice:read') "
            + "and @tenantPolicy.matches(authentication, #tenantId)")
    public Map<String, String> readInvoices(
            @PathVariable("tenantId") @P("tenantId") String tenantId,
            @AuthenticationPrincipal(errorOnInvalidType = true)
            TenantPrincipal principal) {
        return Map.of("tenantId", tenantId, "userId", principal.userId());
    }
}
```

`hasAnyRole('FINANCE', 'AUDITOR')` có nghĩa là người dùng có ít nhất một role trong danh sách. Nếu factory cấp cả hai role, người dùng vẫn thỏa điều kiện; nếu chỉ cấp `AUDITOR`, người dùng cũng được phép khi có permission và tenant phù hợp. `hasAuthority('invoice:read')` là điều kiện riêng, nên role không tự thay thế permission. `@P("tenantId")` giúp biểu thức SpEL tham chiếu tham số method ổn định ngay cả khi tên tham số không được giữ bởi compiler.

Ứng dụng cần bật `@EnableMethodSecurity` và cấu hình `SecurityFilterChain` yêu cầu authentication. Với HTTP Basic entry point mặc định, request anonymous thường trả `401`; người dùng đã xác thực nhưng thiếu role/permission hoặc sai tenant trả `403`.

## 6. Tham số hóa nhiều vai trò

Các test sau dùng cùng một annotation nhưng mô tả những tổ hợp quyền khác nhau:

```java
@Test
@WithTenantUser(roles = { "FINANCE" },
        permissions = { "invoice:read" })
void financeCanRead() {
    // ...
}

@Test
@WithTenantUser(roles = { "AUDITOR" },
        permissions = { "invoice:read" })
void auditorCanRead() {
    // ...
}

@Test
@WithTenantUser(roles = { "FINANCE", "AUDITOR" },
        permissions = { "invoice:read" })
void userCanHoldMultipleRoles() {
    // ...
}

@Test
@WithTenantUser(roles = { "SUPPORT" },
        permissions = { "invoice:read" })
void unrelatedRoleIsDenied() {
    // ...
}
```

Với policy `hasAnyRole('FINANCE', 'AUDITOR')`, ba trường hợp đầu được phép khi các điều kiện còn lại thỏa; `SUPPORT` không thỏa. Nếu policy dùng `hasRole('FINANCE') and hasRole('AUDITOR')`, người dùng phải có **cả hai** role. Chọn biểu thức theo yêu cầu nghiệp vụ, không suy luận rằng danh sách role trong annotation tự động có nghĩa AND hoặc OR; quan hệ được quyết định bởi policy.

### Role và permission không tự kế thừa lẫn nhau

Nếu người dùng có `ROLE_FINANCE`, họ không mặc nhiên có `invoice:read`. Muốn một role cấp nhiều permission, ứng dụng phải cấu hình `RoleHierarchy`, `GrantedAuthoritiesMapper` hoặc một policy chuyển đổi rõ ràng. Test cần đi qua cơ chế đó nếu mục tiêu là kiểm chứng mapping. Không thêm permission thủ công vào annotation chỉ để làm test pass khi production dự kiến suy ra permission từ role.

## 7. Tham số hóa nhiều tenant

Vì `tenantId` là thuộc tính của principal, cùng một role/permission có thể được kiểm tra trên các tenant khác nhau:

```java
@Test
@WithTenantUser(userId = "reader-a", tenantId = "tenant-a",
        roles = { "AUDITOR" }, permissions = { "invoice:read" })
void auditorReadsTenantA() {
    // Request tới /api/tenants/tenant-a/invoices được phép.
}

@Test
@WithTenantUser(userId = "reader-b", tenantId = "tenant-b",
        roles = { "AUDITOR" }, permissions = { "invoice:read" })
void auditorCannotReadTenantAWhenActiveInTenantB() {
    // Request tới /api/tenants/tenant-a/invoices bị từ chối.
}
```

Hai test có cùng role và permission, chỉ khác tenant trong principal. Đây là cách cô lập biến số để chứng minh quyết định authorization thực sự xét tenant.

**Một người dùng thuộc nhiều tenant:** annotation hiện tại mô tả một tenant đang hoạt động tại một thời điểm. Nếu người dùng có membership ở `tenant-a` và `tenant-b`, một test cho mỗi tenant có thể dùng cùng `userId` nhưng thay `tenantId`. Trong ứng dụng thật, server phải xác minh membership của user trước khi tạo principal hoặc chuyển tenant hoạt động; không lấy tenant từ URL rồi mặc định người dùng có quyền ở đó. Nếu policy cần biết *tất cả* tenant mà người dùng thuộc về, hãy thiết kế principal có tập membership đã xác minh hoặc inject membership service vào factory và tạo context theo dữ liệu service trả về.

## 8. Kiểm thử bằng `MockMvc`

Với Spring Boot, các dependency test thường gồm:

```gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Test tích hợp dưới đây giả định có `InvoiceController`, `TenantPolicy`, `SecurityFilterChain`, method security và các annotation/factory đã khai báo:

```java
package com.example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantRoleParameterizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    @WithTenantUser(userId = "u-finance", tenantId = "tenant-a",
            roles = { "FINANCE" }, permissions = { "invoice:read" })
    void financeRoleCanReadOwnTenant() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("u-finance"));
    }

    @Test
    @WithTenantUser(userId = "u-auditor", tenantId = "tenant-a",
            roles = { "AUDITOR" }, permissions = { "invoice:read" })
    void auditorRoleCanReadOwnTenant() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices"))
                .andExpect(status().isOk());
    }

    @Test
    @WithTenantUser(roles = { "FINANCE", "AUDITOR" },
            permissions = { "invoice:read" })
    void multipleRolesAreMapped() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices"))
                .andExpect(status().isOk());
    }

    @Test
    @WithTenantUser(roles = { "SUPPORT" },
            permissions = { "invoice:read" })
    void unrelatedRoleIsDenied() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithTenantUser(roles = { "FINANCE" }, permissions = {})
    void missingPermissionIsDenied() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithTenantUser(tenantId = "tenant-b", roles = { "AUDITOR" },
            permissions = { "invoice:read" })
    void sameRoleButWrongTenantIsDenied() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices"))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousIsRejected() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices"))
                .andExpect(status().isUnauthorized());
    }
}
```

Ma trận kết quả kỳ vọng:

| Roles | Permissions | Tenant trong principal | Tenant trên request | Kết quả |
| --- | --- | --- | --- | --- |
| `FINANCE` | `invoice:read` | `tenant-a` | `tenant-a` | `200` |
| `AUDITOR` | `invoice:read` | `tenant-a` | `tenant-a` | `200` |
| `FINANCE`, `AUDITOR` | `invoice:read` | `tenant-a` | `tenant-a` | `200` |
| `SUPPORT` | `invoice:read` | `tenant-a` | `tenant-a` | `403` |
| `FINANCE` | Rỗng | `tenant-a` | `tenant-a` | `403` |
| `AUDITOR` | `invoice:read` | `tenant-b` | `tenant-a` | `403` |
| Anonymous | Không có | Không có | `tenant-a` | `401` theo HTTP Basic entry point |

Nếu test thiếu role vẫn trả `200`, kiểm tra method security và policy có thực sự được áp dụng. Nếu anonymous trả redirect thay vì `401`, đó có thể là hành vi đúng của form login. Khi tự dựng `MockMvc` bằng `MockMvcBuilders`, nhớ áp dụng `.apply(springSecurity())`; `@AutoConfigureMockMvc` thường tích hợp filter chain trong Spring Boot.

## 9. Dùng annotation ở cấp lớp và cấp phương thức

`@WithSecurityContext` có thể được sử dụng thông qua annotation tùy biến ở cấp lớp test hoặc phương thức test. Cấp lớp hữu ích khi nhiều test cùng dùng một danh tính mặc định; cấp phương thức hữu ích khi mỗi test cần thay đổi role, permission hoặc tenant.

Ví dụ đặt mặc định ở lớp:

```java
@SpringBootTest
@AutoConfigureMockMvc
@WithTenantUser(userId = "u-default", tenantId = "tenant-a",
        roles = { "AUDITOR" }, permissions = { "invoice:read" })
class InvoiceReadTests {

    @Test
    void defaultAuditorReadsTenantA() {
        // Dùng bối cảnh được khai báo trên lớp.
    }

    @Test
    @WithTenantUser(userId = "u-finance", tenantId = "tenant-b",
            roles = { "FINANCE" }, permissions = { "invoice:read" })
    void financeUserUsesAnotherTenant() {
        // Dùng bối cảnh được khai báo cho kịch bản này.
    }
}
```

Khi cần một bối cảnh khác, khai báo annotation trực tiếp trên phương thức để kịch bản được đọc rõ ràng. Tránh chồng nhiều annotation security tùy biến trên cùng một phần tử và dựa vào thứ tự không được định nghĩa. Nếu một lớp test có quá nhiều kịch bản với danh tính rất khác nhau, tách thành các lớp nhỏ có thể làm policy dễ đọc hơn.

## 10. Cấp authentication theo từng request và WebFlux

### 10.1. Nhiều danh tính trong một test Servlet

Nếu một phương thức cần gửi nhiều request với các tenant khác nhau, dùng request post-processor `authentication(...)` thay vì thay đổi một context dùng chung:

```java
Authentication tenantA = UsernamePasswordAuthenticationToken.authenticated(
        new TenantPrincipal("u-42", "tenant-a"), null,
        List.of(new SimpleGrantedAuthority("ROLE_AUDITOR"),
                new SimpleGrantedAuthority("invoice:read")));

Authentication tenantB = UsernamePasswordAuthenticationToken.authenticated(
        new TenantPrincipal("u-42", "tenant-b"), null,
        List.of(new SimpleGrantedAuthority("ROLE_AUDITOR"),
                new SimpleGrantedAuthority("invoice:read")));

mvc.perform(get("/api/tenants/tenant-a/invoices")
        .with(authentication(tenantA)))
    .andExpect(status().isOk());

mvc.perform(get("/api/tenants/tenant-a/invoices")
        .with(authentication(tenantB)))
    .andExpect(status().isForbidden());
```

Ví dụ cần static import `SecurityMockMvcRequestPostProcessors.authentication` và các matcher/request builder tương ứng. Mỗi request nhận authentication riêng. Cách này phù hợp để so sánh hai danh tính trong cùng một test mà không sửa principal/token đang được request trước sử dụng.

### 10.2. Reactive với `WebTestClient`

Trong WebFlux, security context được truyền qua Reactor Context. `WebTestClient` cung cấp `mockAuthentication(...)` để cấp một authentication có principal và authorities cụ thể:

```java
Authentication auditor = UsernamePasswordAuthenticationToken.authenticated(
        new TenantPrincipal("u-auditor", "tenant-a"), null,
        List.of(new SimpleGrantedAuthority("ROLE_AUDITOR"),
                new SimpleGrantedAuthority("invoice:read")));

webTestClient.mutateWith(mockAuthentication(auditor))
        .get().uri("/api/reactive/tenants/tenant-a/invoices")
        .exchange()
        .expectStatus().isOk();
```

Ví dụ giả định route Reactive và policy tương ứng đã được cấu hình; dùng static import `SecurityMockServerConfigurers.mockAuthentication`. Nếu client được dựng từ application context, tích hợp `springSecurity()` khi build `WebTestClient`. Để kiểm tra tenant khác, tạo một authentication mới với `tenant-b` rồi gọi cùng URI và kỳ vọng `403`. Không dùng `SecurityContextHolder` ThreadLocal để truyền context qua reactive pipeline.

## 11. Lỗi thường gặp khi tham số hóa annotation

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `hasRole('FINANCE')` không khớp | Factory không thêm `ROLE_` hoặc annotation đã chứa sẵn tiền tố | Quy định role không kèm prefix; chỉ factory thêm prefix |
| `hasAuthority('invoice:read')` không khớp | Permission bị thêm `ROLE_` hoặc bị đổi chuỗi | Giữ permission nguyên văn và kiểm tra authorities thực tế |
| Có một trong nhiều role nhưng vẫn bị từ chối | Policy dùng `hasRole(A) and hasRole(B)` trong khi test chỉ cấp một role | Dùng `hasAnyRole` nếu chính sách là OR; dùng `hasRole` kết hợp AND nếu bắt buộc cả hai |
| Người dùng sai tenant vẫn đọc được dữ liệu | Policy chỉ kiểm tra role/permission mà không kiểm tra tenant | Kiểm tra tenant từ principal đã xác minh với tenant của tài nguyên |
| Test mặc định có quá nhiều quyền | Annotation cấp role/permission mặc định | Để mảng rỗng và khai báo quyền tường minh từng test |
| Role được kỳ vọng kéo theo permission nhưng test fail | Chưa cấu hình role hierarchy/mapper hoặc test không đi qua mapper | Kiểm thử mapping thực tế, không tự thêm quyền trong fixture |
| Factory báo giá trị role không hợp lệ | Tên role có prefix hoặc khoảng trắng | Truyền `FINANCE`, `AUDITOR`; không truyền `ROLE_FINANCE` |
| Test Reactive không thấy authentication | Context chưa được đặt qua Reactor Context | Dùng `WebTestClient.mutateWith(...)` và reactive security configurer |

## 12. Bài thực hành

Mở rộng annotation `@WithTenantUser` để hỗ trợ endpoint phát hành hóa đơn:

1. `GET /api/tenants/{tenantId}/invoices` yêu cầu một trong hai role `FINANCE` hoặc `AUDITOR`, permission `invoice:read` và tenant khớp.
2. `POST /api/tenants/{tenantId}/invoices` yêu cầu role `FINANCE`, permission `invoice:issue`, tenant khớp và CSRF hợp lệ nếu CSRF đang bật.
3. Viết test cho người có cả `FINANCE` và `AUDITOR`, người chỉ có `AUDITOR`, người chỉ có `SUPPORT`, và người có role đúng nhưng thiếu permission.
4. Dùng cùng `userId` với hai tenant khác nhau để chứng minh policy kiểm tra tenant hoạt động.
5. Viết test xác nhận factory tạo đúng các chuỗi `ROLE_FINANCE`, `ROLE_AUDITOR`, `invoice:read` và không tạo `ROLE_ROLE_FINANCE`.
6. Lặp lại một ca được phép và một ca sai tenant trên endpoint Reactive bằng `WebTestClient`.

### Câu hỏi tự đánh giá

- Vì sao `roles = { "FINANCE", "AUDITOR" }` không tự xác định policy là AND hay OR?
- Factory nên thêm tiền tố `ROLE_` ở đâu và vì sao annotation không nên bắt người viết test tự thêm?
- Tại sao tenant phải được kiểm tra riêng với role và permission?
- Khi nào một người dùng có nhiều tenant cần principal chứa tenant đang hoạt động, khi nào cần danh sách membership đã xác minh?
- Sự khác nhau giữa `@WithTenantUser` và request post-processor `authentication(...)` là gì?
- Khi chuyển test sang WebFlux, cơ chế nào đưa authentication vào request pipeline?

## Tài liệu tham khảo

- [Spring Security — Testing Method Security and `@WithSecurityContext`](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — `hasRole` and `hasAuthority` Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html)
- [Spring Security — Reactive Web Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)

Một annotation tham số hóa tốt giúp cùng một factory mô tả được nhiều vai trò, permission và tenant mà vẫn làm rõ quyền nào được cấp cho từng test. Hãy để factory chuyển role và permission theo quy ước nhất quán, giữ tenant trong principal và kiểm tra tenant ở policy. Khi đó, các ca được phép và bị từ chối thể hiện đúng ma trận phân quyền của ứng dụng.
