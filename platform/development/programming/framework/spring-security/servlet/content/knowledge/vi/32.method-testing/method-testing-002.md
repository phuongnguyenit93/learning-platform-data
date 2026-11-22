# @WithMockUser và giới hạn của principal giả lập trong kiểm thử phương thức Spring Security

> **Phạm vi:** Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet stack (Spring MVC). Trọng tâm là kiểm thử `@PreAuthorize`/`@PostAuthorize` và các Spring-managed service có bảo vệ phương thức bằng `@WithMockUser`. Bài giải thích chính xác cái gì được **giả lập**, cái gì được **kiểm chứng**, những giới hạn của principal giả và khi nào cần `@WithUserDetails`, `@WithSecurityContext`, kiểm thử HTTP/login thực tế. Không dùng kết quả test giả principal để khẳng định xác thực ngoài đời đã an toàn.

## 1. Vấn đề: muốn test phân quyền, không phải lúc nào cũng cần đăng nhập thật

Trong một ứng dụng Spring MVC, quyền có thể được kiểm tra ở nhiều tầng:

- Servlet filter chain: `authorizeHttpRequests` quyết định request nào được vào một URL dựa trên authentication.
- Method security: `@PreAuthorize`, `@PostAuthorize`, `@Secured` hoặc các authorization interceptors quyết định **một lời gọi method** được cho phép hay từ chối.
- Domain authorization: quyền trên **chính bản ghi, tenant, owner** hoặc điều kiện nghiệp vụ cụ thể.

Khi chỉ muốn kiểm chứng một method chỉ cho phép người có quyền `DOC_READ` xem tài liệu, việc phải chạy login form, kết nối LDAP/IdP hoặc tạo JWT thật trong từng test có thể làm test chậm và khó tập trung. `@WithMockUser` của **spring-security-test** giúp cung cấp sẵn một `Authentication` giả trong Spring Security context của test.

**Nhưng:** một test `@WithMockUser(roles = "ADMIN")` thành công **chỉ chứng minh rule của method có thể nhận một Authentication đã mang quyền ADMIN**. Nó không chứng minh người dùng đã vượt qua login thật, không chứng minh role được lấy đúng từ database/IdP/JWT, không chứng minh tài khoản bị khóa bị từ chối và không chứng minh API HTTP không có đường bypass.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Hiểu cách `@WithMockUser` tạo `SecurityContext`, principal và authorities, cũng như cách nó được dọn dẹp giữa các test.
2. Cấu hình một method service `@PreAuthorize` và viết test **được phép/bị từ chối** bằng Spring Boot Test.
3. Phân biệt `roles` với `authorities`, user name với principal object thật, và `@WithMockUser` với `@WithUserDetails`.
4. Nhận biết các trường hợp `@WithMockUser` tạo **false confidence**, đặc biệt custom principal, token/JWT claims, tenant/ownership, database account state, filter chain và self-invocation.
5. Chọn integration tests bổ sung cho HTTP authentication, mapping authorities, CSRF và quyền theo tài nguyên.

## 2. Cách @WithMockUser hoạt động

`@WithMockUser` nằm trong package:

~~~java
import org.springframework.security.test.context.support.WithMockUser;
~~~

Nó được hỗ trợ bởi **Spring Security Test** qua `WithSecurityContextTestExecutionListener` trong Spring TestContext. Listener tạo một `SecurityContext` test, đặt `Authentication` do annotation quy định vào context, rồi dọn dẹp context sau test.

Một annotation tiêu biểu:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void canUseAServiceAsAlice() {
    // Lời gọi tới Spring bean có method security.
}
~~~

Trong test này, `Authentication` có các đặc tính đại diện:

| Thuộc tính | Giá trị/ý nghĩa |
| --- | --- |
| `Authentication.getName()` | `alice`. |
| `Authentication.isAuthenticated()` | `true`: token test được tạo ở trạng thái đã xác thực. |
| `Authentication.getPrincipal()` | Thường là `org.springframework.security.core.userdetails.User` từ Spring Security Test, **không phải** entity `AppUser` hoặc principal của IdP. |
| `Authentication.getAuthorities()` | Từ role `USER` thành `ROLE_USER` theo quy ước mặc định. |
| `Authentication.getCredentials()` | Thông tin giả dùng trong token; không có quy trình kiểm tra password như login thật. |
| `SecurityContextHolder.getContext()` | Chứa authentication test trong thread/context mà test listener thiết lập. |

**Mặc định** khi chỉ viết `@WithMockUser`, test user có username `user`, password giả mặc định `password`, và role `USER` (authority `ROLE_USER`). Nó **không** đại diện cho anonymous user.

Chú ý hai từ thường bị hiểu sai:

- **Mock** ở đây là *mô phỏng trạng thái bảo mật*; principal thường là một đối tượng `User` cụ thể chứ không phải Mockito mock tùy ý.
- **Authenticated** ở đây là cờ trong `Authentication` test. Không có password encoder, xác minh mật khẩu, MFA, JWT signature hay HTTP login flow nào tự động diễn ra chỉ nhờ annotation.

Ví dụ kiểm tra context trong một test có Spring TestContext:

~~~java
@Test
@WithMockUser(username = "alice", roles = {"USER", "EDITOR"})
void showsWhatIsStoredInContext() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("alice", auth.getName());
    assertTrue(auth.isAuthenticated());
    assertTrue(auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_EDITOR")));
    assertInstanceOf(
            org.springframework.security.core.userdetails.User.class,
            auth.getPrincipal());
}
~~~

Các imports `Authentication`, `SecurityContextHolder` và static assertions của JUnit 5 cần được thêm theo dự án. Đoạn trên là **method test minh họa**, không phải file Java độc lập. Nó cố ý kiểm tra principal giả để nhắc rằng test **không đọc một user entity thật**.

## 3. Roles và authorities: đặt sai có thể test sai

Spring Security phân biệt **role** (quy ước có prefix) và **authority** (tên chính xác).

~~~java
@WithMockUser(username = "alice", roles = "ADMIN")
// GrantedAuthority tương ứng thường là "ROLE_ADMIN".

@WithMockUser(username = "alice", authorities = "DOC_READ")
// GrantedAuthority có tên chính xác "DOC_READ".
~~~

Hai annotation trên là **ví dụ khai báo thay thế** cho một method/class, không đặt cả hai liên tiếp để tạo hai người dùng cùng lúc.

| Cấu hình test | GrantedAuthority chính | Phù hợp với |
| --- | --- | --- |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` | `hasRole('ADMIN')` hoặc `hasAuthority('ROLE_ADMIN')`. |
| `@WithMockUser(roles = "USER")` | `ROLE_USER` | `hasRole('USER')`. |
| `@WithMockUser(authorities = "DOC_READ")` | `DOC_READ` | `hasAuthority('DOC_READ')`. |
| `@WithMockUser(authorities = {"DOC_READ", "DOC_WRITE"})` | Hai authority chính xác. | Rule cần một hoặc cả hai permission. |
| `@WithMockUser` | `ROLE_USER` | Test hành vi default user. |

**Không** khai báo `roles = "ROLE_ADMIN"` nếu đang dùng convention mặc định: prefix `ROLE_` được framework áp dụng cho role. Dùng `roles = "ADMIN"`. Nếu ứng dụng đổi role prefix hoặc có custom authority mapper, test phải phản ánh đúng chính sách thực tế và không mặc định mọi authority đều bắt đầu bằng ROLE.

`roles` và `authorities` cùng có trong annotation, nhưng khi đặt `authorities` tường minh, quyền được xác định theo danh sách authorities đó; không nên trộn hai thuộc tính rồi kỳ vọng Spring tự hợp nhất mọi role. Muốn test nhiều quyền, biểu diễn rõ trong `authorities`.

### Chọn điều kiện cho đúng use case

- Quyền khái quát: `@PreAuthorize("hasRole('ADMIN')")`.
- Permission chính xác: `@PreAuthorize("hasAuthority('DOC_READ')")`.
- Quyền kết hợp resource ownership: `@PreAuthorize("hasAuthority('DOC_READ') and #p0 == authentication.name")`.
- Multi-tenant: cần policy server-side biết tenant của principal và tenant của resource; chỉ role USER chưa đủ.

Test nên có cả ca **đúng role nhưng sai owner**, **đúng owner nhưng thiếu permission** để tránh tình trạng chỉ một chiều dương tính.

## 4. Dự án Spring Boot mẫu: bảo vệ method thật

Các ví dụ sau kết hợp thành một dự án Spring Boot 3.x (Java 17+), package `com.example.methodauth`. Test chạy trong **Spring ApplicationContext**, không phải Java SE độc lập: hãy dùng Maven/Gradle và dependencies tương ứng.

### 4.1 Dependencies cần có

Trong `pom.xml` của một Spring Boot project sử dụng Boot parent/BOM, phần `dependencies` cần ít nhất:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu app cũng dùng MVC endpoints, thêm `spring-boot-starter-web`. Không cần network/IdP để chạy test chỉ gọi service method và dùng `@WithMockUser`.

### 4.2 Bật method security

File `src/main/java/com/example/methodauth/MethodAuthApplication.java`:

~~~java
package com.example.methodauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodAuthApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` kích hoạt cơ chế xử lý authorization annotations cho các Spring-managed beans. Trong Spring Security 6, không phải cứ thêm `@PreAuthorize` vào Java method là nó tự chạy trong một object tạo bằng `new`.

Với service proxies, **lời gọi phải đi qua Spring bean/proxy**. Một lỗi hay gặp:

~~~java
// Không phải cách chứng minh method security đang hoạt động:
DocumentService service = new DocumentService();
service.readForOwner("alice");
~~~

Nếu tự `new` như trên, đối tượng không được container xử lý method authorization; test có thể chạy qua rule mà không phát hiện lỗi. Phần dưới sử dụng `@Autowired` để gọi bean từ ApplicationContext.

### 4.3 Service chứa policy kiểm tra permission và chủ sở hữu

File `src/main/java/com/example/methodauth/DocumentService.java`:

~~~java
package com.example.methodauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasAuthority('DOC_READ') and #p0 == authentication.name")
    public String readForOwner(String ownerUsername) {
        return "document for " + ownerUsername;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String deleteForAdministration(long documentId) {
        return "deleted " + documentId;
    }
}
~~~

Đây là code **độc lập trong ngữ cảnh Spring bean**: phương thức chỉ trả chuỗi để test được cả authorization lẫn kết quả. Nó không truy vấn database hoặc thực sự xóa tài liệu.

- `hasAuthority('DOC_READ')` kiểm tra permission đọc tài liệu.
- `#p0` là tham số đầu tiên của method (tên theo index) nên không lệ thuộc trình biên dịch có lưu parameter names hay không. So sánh nó với `authentication.name` giúp minh họa kiểm tra owner.
- `hasRole('ADMIN')` yêu cầu authority `ROLE_ADMIN`.
- Policy thật nên đọc owner/tenant từ **database/ACL được tin cậy** dựa trên ID tài nguyên, chứ **không tin ownerUsername mà client tự truyền**. Ví dụ sử dụng tham số owner chỉ để biểu diễn cơ chế SpEL; phần 8 làm rõ giới hạn.
- Method authorization chạy **trước khi vào thân method** theo `@PreAuthorize`. Nếu rule từ chối, nội dung `return` không được thực thi.

## 5. Kiểm thử cả đường được phép và bị từ chối

File `src/test/java/com/example/methodauth/DocumentServiceSecurityTest.java`:

~~~java
package com.example.methodauth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void permitsOwnerWithReadPermission() {
        assertEquals(
                "document for alice",
                documents.readForOwner("alice"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void deniesUserReadingDifferentOwner() {
        assertThrows(
                AccessDeniedException.class,
                () -> documents.readForOwner("bob"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void deniesOwnerWithoutReadPermission() {
        assertThrows(
                AccessDeniedException.class,
                () -> documents.readForOwner("alice"));
    }

    @Test
    @WithMockUser(username = "manager", roles = "ADMIN")
    void permitsAdministrator() {
        assertEquals(
                "deleted 99",
                documents.deleteForAdministration(99L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void deniesNormalUserAdministration() {
        assertThrows(
                AccessDeniedException.class,
                () -> documents.deleteForAdministration(99L));
    }
}
~~~

Bộ test này chạy qua **Spring-managed service** có method authorization. Kỳ vọng:

| Test | Authentication giả lập | Request method | Kỳ vọng |
| --- | --- | --- | --- |
| `permitsOwnerWithReadPermission` | alice, `DOC_READ` | `readForOwner("alice")` | Được phép, trả `document for alice`. |
| `deniesUserReadingDifferentOwner` | alice, `DOC_READ` | `readForOwner("bob")` | `AccessDeniedException`. |
| `deniesOwnerWithoutReadPermission` | alice, `ROLE_USER` | `readForOwner("alice")` | `AccessDeniedException` vì thiếu `DOC_READ`. |
| `permitsAdministrator` | manager, `ROLE_ADMIN` | `deleteForAdministration(99)` | Được phép, trả `deleted 99`. |
| `deniesNormalUserAdministration` | alice, `ROLE_USER` | `deleteForAdministration(99)` | `AccessDeniedException`. |

Chạy trong một Spring Boot Maven project đã đủ lớp/dependencies trên:

~~~bash
mvn test
~~~

Không tự gán stdout cố định cho Maven: kết quả in ra còn phụ thuộc phiên bản plugin và các test khác của project. Trong ví dụ này, năm test dự kiến pass nếu Spring context khởi tạo đúng và `@EnableMethodSecurity` có hiệu lực. Nếu **tất cả test từ chối đều không bị chặn**, xem lại: object có phải bean Spring? Có bật method security? Lời gọi có qua proxy? Annotation có được thực thi không?

### Vì sao phải test kết quả từ chối?

Test duy nhất user ADMIN được qua rule chưa chứng minh user USER bị chặn. Một cấu hình lỗi `permitAll` cũng có thể khiến test dương tính pass. Test âm tính buộc kiểm tra **đường từ chối**, phát hiện thiếu interceptor, sai annotation, thiếu authority hoặc sai logic ownership.

Ngược lại, nếu chỉ kiểm tra status 403 qua HTTP, test có thể **pass sai lý do** (ví dụ CSRF token thiếu) mà method security chưa bao giờ được gọi. Với unit/integration test ở service như trên, `assertThrows(AccessDeniedException.class, ...)` giúp cô lập policy method. Với HTTP test, phải tách CSRF và authentication/authorization rõ ràng.

## 6. @WithMockUser mặc định và các tùy chọn

### 6.1 Giá trị mặc định

~~~java
@Test
@WithMockUser
void testAsDefaultUser() {
    // Authentication.name = "user"
    // Granted authority thường = ROLE_USER
}
~~~

Một test không có `@WithMockUser` không tự động chạy với anonymous user; trong nhiều method test không có SecurityContext, `Authentication` có thể là `null` và gây `AuthenticationCredentialsNotFoundException` khi rule yêu cầu authentication. Để kiểm thử trạng thái anonymous một cách có chủ đích, dùng `@WithAnonymousUser` (kèm môi trường Spring TestContext phù hợp) hoặc một flow HTTP không mang credential.

### 6.2 username, password, roles, authorities

~~~java
@WithMockUser(
    username = "report-reader",
    authorities = {"DOC_READ", "REPORT_VIEW"}
)
~~~

`username` đặt tên test principal. `password` nếu được chỉ định chỉ là chuỗi giả gắn với user test; Spring Security Test **không gọi PasswordEncoder.matches(...)** hoặc xác nhận password với user store. `roles` biểu diễn roles không có tiền tố `ROLE_` trong annotation. `authorities` biểu diễn authority tên chính xác.

Vì vậy một test dùng:

~~~java
@WithMockUser(
    username = "account-does-not-exist",
    password = "wrong-password",
    roles = "ADMIN"
)
~~~

**vẫn có thể vượt qua** `@PreAuthorize("hasRole('ADMIN')")`. Đó là hành vi đúng của annotation: nó **cố tình bỏ qua login thực** để test authorization với quyền được chỉ định. Không dùng kết quả như vậy để khẳng định tài khoản tồn tại hoặc mật khẩu được bảo vệ.

### 6.3 Annotation ở mức class và method

`@WithMockUser` có thể gắn vào class để các test dùng cùng principal mặc định. Một method có annotation riêng có thể định nghĩa principal cho test đó. Tuy nhiên mỗi test cần **danh tính/quyền tường minh và đúng mục tiêu**; quá lạm dụng annotation class-level có thể che mất điều kiện bảo mật mà test tưởng đang kiểm tra.

### 6.4 Thời điểm thiết lập SecurityContext

`@WithMockUser` có tùy chọn:

~~~java
@WithMockUser(
    username = "alice",
    roles = "USER",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

Cần import `org.springframework.security.test.context.support.TestExecutionEvent`. Mặc định `setupBefore = TEST_METHOD`: context được tạo trước vòng callback `@BeforeEach` của JUnit/Spring test. Với `TEST_EXECUTION`, context được thiết lập muộn hơn, sau `@BeforeEach` và trước thân test. Tùy chọn này hữu ích khi setup cần chủ động không sử dụng Authentication giả cho tới khi test bắt đầu.

Test listener quản lý dọn context, tránh rò quyền giữa các test trong môi trường chuẩn. Tuy nhiên nếu tự tạo threads, chạy `@Async`, dùng executor hoặc lưu `Authentication` vào static/shared mutable state, context có thể **không tự truyền sang thread khác**; cần kiểm thử context propagation riêng, không dựa hoàn toàn vào `@WithMockUser`.

## 7. Giới hạn lớn nhất: principal là giả, không phải user của hệ thống

`@WithMockUser` tạo một `User` của Spring Security Test có username và authorities, không tạo entity domain. Nó không gọi:

- `UserDetailsService.loadUserByUsername(...)`;
- repository/database truy vấn user;
- kiểm tra password hash, trạng thái locked/disabled/expired;
- IdP/OIDC/SAML, JWT signature/issuer/audience/expiry;
- ánh xạ groups/claims từ một provider thành application authorities;
- account linking, tenant membership, profile enrichment của hệ thống;
- HTTP filter chain, session, CSRF, CORS hoặc custom authentication converters chỉ vì method annotation xuất hiện.

Điều này có thể khiến test xanh trong khi hệ thống thật lỗi: ví dụ JWT claim `roles=["admin"]` không được converter ánh xạ thành `ROLE_ADMIN`, hoặc IdP trả group khác tên. Test `@WithMockUser(roles="ADMIN")` **bỏ qua converter đó**, nên vẫn thành công.

### 7.1 Nguy cơ cast principal sai

Giả sử code production kỳ vọng:

~~~java
AppPrincipal principal =
        (AppPrincipal) authentication.getPrincipal();
String tenantId = principal.tenantId();
~~~

Đây là đoạn minh họa yêu cầu class `AppPrincipal` của ứng dụng và biến `authentication` hợp lệ; nó **không hoạt động** với principal `User` mặc định từ `@WithMockUser` vì không có type `AppPrincipal`. Có thể gặp `ClassCastException` hoặc rule SpEL thiếu thuộc tính khi gọi `principal.tenantId`.

Từ đó cần phân biệt **hai loại bài toán test**:

1. Chỉ kiểm tra rule dựa trên username + authorities tiêu chuẩn: `@WithMockUser` thường đủ để tạo context đơn giản.
2. Kiểm tra rule/coding path đòi claims, tenantId, userId, domain principal type, custom authorities: phải tạo principal đúng hình dạng bằng `@WithSecurityContext` hoặc một annotation test phù hợp, và vẫn cần integration test thật cho converter/IdP.

### 7.2 Principal giả không đảm bảo quyền theo dữ liệu thật

Ngay cả rule `#p0 == authentication.name` trong ví dụ `DocumentService` chỉ so một tham số method với username. Nếu controller truyền ownerUsername do client tự cung cấp, người dùng có thể đặt ownerUsername của chính mình để khiến rule pass, trong khi ID tài liệu thực tế lại thuộc người khác.

Đối với production, nên nhận `documentId`, rồi tra ownership/tenant từ dữ liệu đáng tin và kiểm tra cùng Authentication:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
public Document readById(long documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
~~~

Đoạn là **mẫu kiến trúc**, không chạy độc lập vì `Document`, `documentPolicy`, `documentRepository` là components nghiệp vụ cụ thể. Trong production cần ràng buộc query theo owner/tenant và xử lý race/TOCTOU phù hợp. Test `@WithMockUser` vẫn hữu ích cho role/authority, nhưng việc owner có thật trong DB, tenant tách biệt và resource scope đúng cần test có data fixture hoặc integration test tương ứng.

## 8. Khi dùng @WithUserDetails thay @WithMockUser

Spring Security Test cung cấp `@WithUserDetails`:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "userDetailsService"
)
void usesARealUserDetailsObjectFromService() {
    // Principal lấy từ UserDetailsService đã được cấu hình.
}
~~~

Ví dụ trên là **method test**, chỉ chạy khi Spring context có bean `UserDetailsService` mang tên `userDetailsService` và thực sự tìm được user `alice`.

Khác biệt:

| Đặc điểm | `@WithMockUser` | `@WithUserDetails` |
| --- | --- | --- |
| Nguồn username | Từ annotation. | Gọi `UserDetailsService` trong test context. |
| Principal | Spring Security `User` do test tạo. | `UserDetails` mà service trả; có thể là custom principal. |
| Cần tài khoản ở user store? | **Không**. | **Có** (theo service/test fixture). |
| Thực sự chạy login/password check? | Không. | **Không**: nó load `UserDetails`, không tự xác minh mật khẩu qua authentication provider. |
| Kiểm tra trạng thái account/tenant? | Không. | Có thể đọc dữ liệu thực từ user service, nhưng **chưa chứng minh** authentication provider đã từ chối locked/disabled. |
| Tốc độ và phạm vi | Nhẹ, tập trung rule. | Gắn với user service, DB fixtures hoặc bean wiring hơn. |

Dùng `@WithUserDetails` khi code cần custom `UserDetails` và bạn muốn test với dữ liệu do service cung cấp; nhưng phải phân biệt “service tìm thấy user” với “user đã login thành công”. Nếu muốn kiểm tra locked account bị chặn bởi real login, hãy thử login qua filter/provider, không gán sẵn authentication.

## 9. Tạo @WithSecurityContext cho principal riêng

Khi principal production mang tenantId hoặc userId đặc thù, có thể viết annotation chuyên dụng với `@WithSecurityContext`. Ví dụ sau tạo **AppPrincipal được kiểm soát trong test**. Nó vẫn giả lập authentication (không chứng minh login), nhưng **kiểu principal giống hợp đồng của code nghiệp vụ**.

### 9.1 Domain principal trong test

File `src/test/java/com/example/methodauth/AppPrincipal.java`:

~~~java
package com.example.methodauth;

import java.security.Principal;

public record AppPrincipal(String username, String tenantId)
        implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
~~~

Đây là Java record (Java 17+), có getter record `username()` và `tenantId()`. Implement `Principal` để `Authentication.getName()` trả đúng username khi dùng object này. Trong production, có thể sử dụng type/domain principal thật thay vì record dành riêng cho test.

### 9.2 Annotation test tùy chỉnh

File `src/test/java/com/example/methodauth/WithTenantUser.java`:

~~~java
package com.example.methodauth;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithTenantUserFactory.class)
public @interface WithTenantUser {

    String username() default "alice";

    String tenantId() default "team-a";
}
~~~

### 9.3 Factory đặt Authentication giả đúng kiểu

File `src/test/java/com/example/methodauth/WithTenantUserFactory.java`:

~~~java
package com.example.methodauth;

import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public class WithTenantUserFactory
        implements WithSecurityContextFactory<WithTenantUser> {

    @Override
    public SecurityContext createSecurityContext(WithTenantUser annotation) {

        AppPrincipal principal = new AppPrincipal(
                annotation.username(), annotation.tenantId());

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                    principal,
                    "not-a-real-credential",
                    List.of(new SimpleGrantedAuthority("DOC_READ")));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Factory có public no-arg constructor ngầm định, tạo Authentication **đã xác thực trong test** với principal dạng `AppPrincipal`. `"not-a-real-credential"` không được kiểm tra với user store; không lấy làm password hợp lệ. Factory chỉ tồn tại trong `src/test/java`, không phải hệ thống đăng nhập production.

### 9.4 Policy nhận Authentication và kiểm tra tenant

File `src/main/java/com/example/methodauth/TenantPolicy.java` (demo dùng `AppPrincipal` tương đương type production; trong dự án thật đặt domain principal ở `src/main/java`):

~~~java
package com.example.methodauth;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantPolicy")
public class TenantPolicy {

    public boolean canRead(
            Authentication authentication, String tenantId) {
        if (authentication == null ||
                !(authentication.getPrincipal() instanceof AppPrincipal p)) {
            return false;
        }

        boolean canReadDocs = authentication.getAuthorities().stream()
                .anyMatch(a -> "DOC_READ".equals(a.getAuthority()));

        return canReadDocs && p.tenantId().equals(tenantId);
    }
}
~~~

**Quan trọng về vị trí file:** `TenantPolicy` ở `src/main/java` phải tham chiếu type `AppPrincipal` cũng thuộc **`src/main/java`** trong một dự án thực. Nếu dùng ví dụ này cùng policy thật, hãy chuyển file `AppPrincipal.java` ở phần 9.1 sang `src/main/java/com/example/methodauth/` (và **không** giữ thêm bản trùng tên trong `src/test/java`). Factory và `@WithTenantUser` chỉ ở test sources. Sự tách lớp giúp code production không tham chiếu classes tồn tại chỉ khi chạy test.

File `src/main/java/com/example/methodauth/TenantDocumentService.java`:

~~~java
package com.example.methodauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class TenantDocumentService {

    @PreAuthorize("@tenantPolicy.canRead(authentication, #p0)")
    public String readFromTenant(String tenantId) {
        return "tenant " + tenantId;
    }
}
~~~

Trong ví dụ, policy so tenant của principal với tenantId được truyền. Trong hệ thống thật tenant của tài liệu phải lấy từ server-side database theo document ID chứ không tin tenantId do client tự truyền. Đây là policy minh họa cơ chế type/principal.

### 9.5 Test chứng minh sự khác biệt giữa principal mặc định và custom

File `src/test/java/com/example/methodauth/TenantDocumentServiceTest.java`:

~~~java
package com.example.methodauth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class TenantDocumentServiceTest {

    @Autowired
    TenantDocumentService service;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void plainMockUserHasWrongPrincipalType() {
        assertThrows(AccessDeniedException.class,
                () -> service.readFromTenant("team-a"));
    }

    @Test
    @WithTenantUser(username = "alice", tenantId = "team-a")
    void correctTenantPrincipalCanRead() {
        assertEquals("tenant team-a", service.readFromTenant("team-a"));
    }

    @Test
    @WithTenantUser(username = "alice", tenantId = "team-a")
    void cannotCrossTenantBoundary() {
        assertThrows(AccessDeniedException.class,
                () -> service.readFromTenant("team-b"));
    }
}
~~~

Những test này minh họa:

- `@WithMockUser` có đúng username và `DOC_READ` nhưng **không phải AppPrincipal**, nên policy từ chối.
- `@WithTenantUser` cung cấp type và tenantId mong muốn, giúp test logic của domain policy.
- User thuộc team-a không tự được đọc team-b.

**Vẫn chưa kiểm thử cách production tạo `AppPrincipal`** từ JWT/OIDC/SSO/database. Integration tests phải xác nhận mapping identity thật, đặc biệt issuer/tenant claim và quyền.

## 10. Với JWT, OAuth2, OIDC và SAML nên dùng gì?

Trong hệ thống nhận access token JWT tại Resource Server, principal thường là `Jwt` hoặc `JwtAuthenticationToken`, với claims/authorities được converter xử lý. `@WithMockUser` không kiểm tra:

- chữ ký JWT, issuer, audience, expiry, clock skew;
- converter từ scope/role claims sang `GrantedAuthority`;
- token revocation/introspection nếu dùng opaque token;
- mapping tenant/userId và principal object mong đợi.

Khi test method policy chỉ dựa vào `hasAuthority("SCOPE_docs.read")`, có thể dùng `@WithMockUser(authorities = "SCOPE_docs.read")` để cô lập policy. Nhưng nếu code cần `Jwt` claims hoặc logic đọc issuer/tenant, hãy dùng principal đúng kiểu, các Spring Security Test request post-processors như `jwt()`/`opaqueToken()` trong HTTP tests khi phù hợp, và test riêng converter/trust bằng JWT validation thật trong môi trường test.

Với OAuth2 Login/OIDC, principal có thể là `OAuth2User` hoặc `OidcUser`; với SAML2 Login, có thể là `Saml2AuthenticatedPrincipal`. `@WithMockUser` **không** có các attribute/claim như các principal đó. Spring Security Test cung cấp các cơ chế mock login cho các protocol tùy phiên bản; dùng test support phù hợp và luôn tách **policy test** với **integration test xác minh protocol response**.

### Tại sao cần cả mock và real-path tests?

Một hệ thống có thể có rule hoàn hảo:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void executeSensitiveOperation() {
    // ...
}
~~~

Nhưng nếu production SAML groups mapper bị sai và mọi user được gán `ROLE_ADMIN`, bộ `@WithMockUser` test role vẫn xanh. Cần thêm các test cho **authority mapping** và **real authentication path** để chứng minh user thường không thể có quyền ADMIN.

## 11. Method security test khác gì HTTP/MockMvc test?

| Loại test | Chủ thể giả lập | Phạm vi nó xác nhận | Không tự xác nhận |
| --- | --- | --- | --- |
| `@SpringBootTest` + `@WithMockUser` gọi Spring bean | SecurityContext test | `@PreAuthorize`/`@PostAuthorize`, SpEL, policy theo Authentication/args, behavior method. | Login thật, URL filter chain, CSRF, CORS, converter, HTTP status. |
| `@WebMvcTest` + MockMvc `@WithMockUser` | HTTP request trong test với security context giả | URL matcher, Spring MVC controller wiring, HTTP status, có thể method security nếu test slice bật/wire đúng. | IdP/DB thực tế và full production login. |
| MockMvc `.with(user(...))` | Test request-specific user | Gắn identity vào một request, cho phép nhiều principal trong một method test. | Xác thực thật qua password encoder. |
| MockMvc `.with(jwt())` | JWT/authentication giả gắn request | Request authorization theo JWT claims/authorities test. | Chữ ký/issuer/audience JWT thật trừ khi gọi đường decoder. |
| Integration test login/IdP test sandbox | Credential/token thực qua filter/provider | Authentication pipeline, mapping user/roles, session/redirect và chính sách API end-to-end. | Hành vi tất cả môi trường production nếu cấu hình khác. |

### Ví dụ ý tưởng test HTTP trực tiếp

Nếu muốn kiểm tra **một endpoint GET** chỉ cho admin truy cập, dùng MockMvc và Spring Security Test:

~~~java
mvc.perform(get("/admin/dashboard")
        .with(user("alice").roles("USER")))
   .andExpect(status().isForbidden());

mvc.perform(get("/admin/dashboard")
        .with(user("manager").roles("ADMIN")))
   .andExpect(status().isOk());
~~~

Đây là **đoạn minh họa** giả định đã có `MockMvc mvc`, các static imports, endpoint `/admin/dashboard` và `SecurityFilterChain` bảo vệ URL. Nó không chạy độc lập. Với POST, cần thêm `csrf()` khi ứng dụng bật CSRF, tránh pass nhờ 403 do thiếu token thay vì thiếu quyền.

`@WithMockUser` trong MockMvc test có thể cung cấp context cho request qua Spring Security test integration, nhưng muốn kiểm tra filter chain đúng phải bảo đảm MockMvc được cấu hình với Spring Security (ví dụ `@AutoConfigureMockMvc` trong `@SpringBootTest`). Tránh tắt filters hoặc dùng standalone MockMvc chưa gắn chain rồi kết luận server authorization đã được bảo vệ.

## 12. Phân biệt các dạng thất bại

Trong method test, lỗi và nguyên nhân có thể khác nhau:

| Hiện tượng | Khả năng nguyên nhân | Nên kiểm tra |
| --- | --- | --- |
| Test @WithMockUser vẫn `AccessDeniedException` | Authority thiếu, rule SpEL sai, tenant/owner không khớp hoặc custom principal type không đúng. | In/inspect authorities test và expression; xác minh bean policy. |
| Method đáng lẽ từ chối nhưng vẫn chạy | Chưa bật `@EnableMethodSecurity`, tự `new` service, self-invocation hoặc annotation không được intercept. | Kiểm tra Spring bean proxy, method access/public method, đường gọi thực tế. |
| Không có annotation, gặp `AuthenticationCredentialsNotFoundException` | Không có SecurityContext tại điểm method security cần authentication. | Dùng `@WithMockUser`/`@WithAnonymousUser` đúng mục đích hoặc cấu hình Spring TestContext. |
| `ClassCastException` từ principal | Code expect custom principal nhưng test có Spring Security `User`. | Dùng `@WithUserDetails` hoặc `@WithSecurityContext` với đúng type. |
| `@WithUserDetails` không load được user | Bean name/user not found hoặc DB fixture chưa được seed. | Kiểm tra UserDetailsService, test data, transaction lifecycle. |
| `@WithMockUser(roles = "ROLE_ADMIN")` lỗi | Role được khai báo với prefix trùng/không hợp lệ theo convention. | Dùng `roles = "ADMIN"` hoặc `authorities = "ROLE_ADMIN"`. |
| Test từ chối HTTP có 403 ngay cả khi method chưa chạy | CSRF chặn trước, hoặc URL authorization chặn trước. | Thêm `csrf()` và cấu hình request để tách từng cơ chế, test service riêng. |
| Test method pass nhưng production JWT/OIDC login fail | Bỏ qua login/validator/converter trong mock principal test. | Bổ sung tests cho filter, token verification, mapper và user provisioning. |
| Role thay đổi trong DB nhưng test không phản ánh | MockUser quyền hard-code không truy vấn DB. | Dùng test fixtures cho authority mapper/DB, xác minh role revocation. |
| Test @WithMockUser ảnh hưởng test khác | Shared thread/executor/security context thiết lập thủ công chưa được dọn, hoặc test harness custom. | Dùng Spring TestContext listener, reset state và tránh static security context. |

**Không coi “test xanh” là một kết luận chung chung.** Hãy ghi rõ kiểm chứng nào đã chạy: method authorization với identity giả; user store lookup; token/SSO integration; HTTP URL security; CSRF; hoặc quyền theo dữ liệu.

## 13. Quy tắc test tốt cho @PreAuthorize và @PostAuthorize

### Kiểm tra positive, negative và boundary

- **Có permission, đúng owner/tenant:** cho qua.
- **Có permission, sai owner/tenant:** từ chối.
- **Đúng owner, thiếu permission:** từ chối.
- **Role admin và non-admin:** test cả hai.
- **Anonymous/unauthenticated:** từ chối theo policy; phân biệt exception ở method với HTTP 401/403/redirect.
- **Null/missing claim:** không cấp quyền theo mặc định.
- **Tài nguyên không tồn tại, bị xóa, bị khóa:** chính sách phải fail-closed, không leak thông tin.
- **Multi-tenant và role mapping khác nhau:** test không có cross-tenant elevation.

### Post-authorization và dữ liệu trả về

`@PostAuthorize` kiểm tra **sau khi method thực thi**, thường thích hợp với điều kiện dựa trên kết quả trả về (`returnObject`). Nó **không phù hợp** để bảo vệ một thao tác gây side effect quan trọng nếu chỉ sau khi ghi/xóa mới từ chối — side effect có thể đã xảy ra trước khi bị chặn. Đặt `@PreAuthorize` hoặc policy trước lệnh thay đổi trạng thái. Test `@PostAuthorize` phải xác minh object-level condition và không chỉ test trường hợp role dương tính.

### Không bypass policy khi gọi trong cùng class

AOP proxy-based method security thường không intercept self-invocation (một method của bean gọi method được annotate trong chính bean đó qua `this.`). Một test gọi trực tiếp `service.securedMethod()` có thể pass, nhưng code production gọi qua `service.someOtherMethod()` trong cùng object có thể bypass. Test nên bao quát các entry points thực tế và thiết kế các method bảo vệ ở bean boundary rõ ràng.

### Context theo thread

Security context mặc định có lifecycle gắn thread trong nhiều tình huống; `@WithMockUser` không tự bảo đảm authentication được truyền tới `@Async`, scheduled tasks hoặc thread pools. Khi kiểm thử tác vụ chạy khác thread, hãy dùng cơ chế context propagation do Spring Security hỗ trợ hoặc mô hình service identity phù hợp và test riêng. Không tạo quyền ADMIN giả trong worker thread để “làm test qua”.

## 14. Checklist trước khi chấp nhận một bộ test bảo mật

1. Có `spring-security-test` phù hợp phiên bản Spring Security và Spring TestContext đang hoạt động.
2. Method security đã bật (`@EnableMethodSecurity`) và test gọi Spring-managed bean qua interceptor/proxy, không phải object mới tạo bằng `new`.
3. Test chỉ định **đúng username, roles, authorities**, không dùng mặc định USER nếu nghiệp vụ cần quyền khác.
4. Test dương tính và âm tính cùng một policy; không chỉ assert no exception.
5. Đã test sai owner/tenant, thiếu permission, tài nguyên không tồn tại khi liên quan.
6. Nếu code dùng custom principal, test dùng đúng type/cấu trúc qua `@WithUserDetails` hoặc `@WithSecurityContext`, không cast một `User` giả thành domain principal.
7. Không dùng `@WithMockUser` để chứng minh password checks, locked-account rejection, JWT validation, OAuth2/SAML handshake hoặc group mapper.
8. Có integration tests riêng cho đường xác thực thực (phù hợp kiến trúc), các authorities thực sự từ IdP/DB/claims và session/CSRF ở HTTP layer.
9. Với HTTP test 403, đã tách nguyên nhân CSRF, authorization URL và method authorization, không coi một 403 bất kỳ là bằng chứng policy đúng.
10. Đã đánh giá sự khác biệt test profile/prod profile, filter registration, role prefix và security configuration.
11. Không chia sẻ SecurityContext/token/test credentials giữa các test bằng static state hoặc executor chưa dọn.
12. Báo cáo kết quả theo **phạm vi test thực hiện**, tránh tuyên bố “đã kiểm thử bảo mật toàn hệ thống” từ vài test @WithMockUser.

## 15. Những hiểu lầm phổ biến

| Hiểu lầm | Thực tế |
| --- | --- |
| “@WithMockUser đăng nhập một user thật từ database.” | Không; nó trực tiếp dựng Spring Security Authentication giả theo annotation. |
| “Tạo role ADMIN trong annotation chứng minh user có thể được cấp quyền đúng.” | Chỉ chứng minh method nhận Authentication mang role đó; chưa kiểm tra authority mapper ngoài đời. |
| “@WithMockUser(password = 'wrong') sẽ bị từ chối login.” | Không có password verification trong annotation. |
| “Principal luôn là class AppPrincipal của dự án.” | Mặc định principal là Spring Security `User`; custom type cần setup riêng. |
| “Test method xanh chứng minh URL endpoint đã an toàn.” | Method test không tự chạy Servlet filter chain hoặc kiểm tra mọi URL. |
| “Kiểm tra 403 nghĩa là @PreAuthorize đã từ chối.” | 403 cũng có thể do CSRF hoặc URL authorization; phải cô lập cơ chế. |
| “roles và authorities là cùng một thứ.” | `roles` dùng prefix ROLE theo convention, `authorities` là chuỗi chính xác. |
| “@WithUserDetails xác nhận mật khẩu và MFA.” | Nó chỉ nạp UserDetails để tạo authentication test, không thực hiện login thật. |
| “Một user đã authenticated thì có thể đọc mọi resource.” | Cần quyền theo owner/tenant/ACL trên chính dữ liệu. |
| “Nếu @WithMockUser pass thì mọi code path production đều bị chặn đúng.” | AOP self-invocation, mapping principal, filters, converters và multi-entry point đều cần tests riêng. |

## 16. Tóm tắt

**`@WithMockUser` là công cụ mạnh để kiểm thử *method authorization* trên một `SecurityContext` có principal và authorities được tạo có chủ đích.** Nó phù hợp để viết test nhanh, rõ ràng về `@PreAuthorize`, quyền ADMIN/USER, custom permissions và các trường hợp owner/tenant cơ bản — miễn là test gọi Spring-managed bean và method security đã bật.

Nhưng **`@WithMockUser` không phải login thật và principal mặc định không phải user domain/SSO/JWT của ứng dụng**. Những điều chưa được kiểm chứng — password/MFA, IdP/JWT, authority mapping, account status, session/CSRF, HTTP filter chain, tài nguyên thực và những đường gọi bypass — cần test khác. Khi code đòi custom principal, dùng `@WithUserDetails` hoặc `@WithSecurityContext`; khi cần kiểm chứng nguồn danh tính và quyền ngoài đời, bổ sung integration tests theo chính cơ chế xác thực production.

**Quy tắc nhớ nhanh:** *Dùng @WithMockUser để hỏi “Nếu user có danh tính và quyền X thì method xử lý thế nào?”, không dùng nó để kết luận “Hệ thống đã xác minh user thực sự có quyền X”.*

## Tài liệu tham khảo

- Spring Security Reference — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security Reference — Running as a User in Spring Security Test: https://docs.spring.io/spring-security/reference/servlet/test/method.html#test-method-withmockuser
- Spring Security Reference — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security Reference — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
