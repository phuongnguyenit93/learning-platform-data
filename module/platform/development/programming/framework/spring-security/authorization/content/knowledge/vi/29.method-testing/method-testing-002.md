# @WithMockUser và khác biệt giữa roles với authorities khi kiểm thử phương thức

> **Bối cảnh:** Spring Security trên Servlet, kiểm thử **method security** (`@PreAuthorize`) bằng JUnit 5 và `spring-security-test`. Bài tập trung vào việc tạo người dùng giả lập, kiểm tra authority thực sự có trong `Authentication`, và chứng minh phương thức chỉ chạy khi đúng quyền. Các ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x, với quy ước prefix vai trò mặc định `ROLE_`.

## 1. Cần phân biệt ba khái niệm

**Authentication (xác thực)** trả lời “ai đang thực hiện lời gọi?”. Trong Spring Security, câu trả lời nằm ở `SecurityContextHolder.getContext().getAuthentication()`.

**GrantedAuthority (quyền được cấp)** là một giá trị quyền của `Authentication`, thường biểu diễn bằng `SimpleGrantedAuthority` và một chuỗi chính xác như `ROLE_ADMIN`, `invoice:read` hoặc `SCOPE_invoices.read`. Spring Security không tự biến một chuỗi `ADMIN` thành `ROLE_ADMIN` khi kiểm tra `hasAuthority`.

**Role (vai trò)** là cách đặt tên và kiểm tra một nhóm authority theo quy ước. Với prefix mặc định `ROLE_`:

- `hasRole('ADMIN')` kiểm tra quyền thực tế `ROLE_ADMIN`.
- `hasAuthority('ROLE_ADMIN')` kiểm tra đúng `ROLE_ADMIN` nên thường cho kết quả giống `hasRole('ADMIN')`.
- `hasAuthority('ADMIN')` kiểm tra đúng `ADMIN`; nó khác hai cách trên.
- `hasAuthority('invoice:read')` kiểm tra một permission cụ thể; không cần thêm `ROLE_`.

`@WithMockUser` là **công cụ chuẩn bị SecurityContext cho test**. Nó không tự gọi dịch vụ đăng nhập, không kiểm tra mật khẩu và không tra cứu tài khoản thật. Vì thế, kiểm thử bằng `@WithMockUser` chứng minh các quy tắc **phân quyền** với principal/authority đã cấp, chứ chưa chứng minh dữ liệu đăng nhập hoặc token ngoài đời được chuyển thành đúng authority.

### Mục tiêu thực hành

Khi hoàn thành bài, bạn phải có khả năng:

1. Đọc chính xác quyền được tạo ra từ `@WithMockUser` mặc định, `roles` và `authorities`.
2. Viết cặp test **được phép / bị từ chối** cho `hasRole` và `hasAuthority`.
3. Hiểu vì sao `@WithMockUser(roles = "ADMIN")` và `@WithMockUser(authorities = "ADMIN")` không tương đương.
4. Kiểm thử rule yêu cầu **đồng thời** role và permission.
5. Biết lúc nào nên dùng `@WithUserDetails`, `@WithSecurityContext` hoặc gửi credentials qua HTTP thay vì dùng mock user.

## 2. @WithMockUser thực sự tạo ra đối tượng gì?

`@WithMockUser` làm việc cùng `WithSecurityContextTestExecutionListener` trong Spring Test. Nó tạo một `SecurityContext` cho test thread, bên trong có `UsernamePasswordAuthenticationToken` đã xác thực. Principal mặc định là một `org.springframework.security.core.userdetails.User` giả lập. User này **không cần có trong database hoặc `UserDetailsService`**.

Giá trị mặc định của annotation:

```java
@WithMockUser
// Tương đương về mặt dữ liệu người dùng mặc định với:
// username = "user"
// password = "password"
// roles = {"USER"}  --> authority thật: "ROLE_USER"
```

Những cấu hình thường gặp:

| Annotation | `Authentication.getName()` | `GrantedAuthority.getAuthority()` được cấp |
| --- | --- | --- |
| `@WithMockUser` | `user` | `ROLE_USER` |
| `@WithMockUser("mai")` | `mai` | `ROLE_USER` |
| `@WithMockUser(username = "mai", roles = "ADMIN")` | `mai` | `ROLE_ADMIN` |
| `@WithMockUser(roles = {"USER", "ADMIN"})` | `user` | `ROLE_USER`, `ROLE_ADMIN` |
| `@WithMockUser(authorities = "ADMIN")` | `user` | `ADMIN` |
| `@WithMockUser(authorities = "ROLE_ADMIN")` | `user` | `ROLE_ADMIN` |
| `@WithMockUser(authorities = {"invoice:read", "invoice:write"})` | `user` | Hai chuỗi nguyên văn `invoice:read`, `invoice:write` |
| `@WithMockUser(authorities = "SCOPE_invoices.read")` | `user` | `SCOPE_invoices.read` |

Điểm dễ nhầm: khi chỉ truyền `authorities`, thuộc tính `roles` ở giá trị mặc định `{"USER"}` **không sinh thêm `ROLE_USER`**. `authorities` thay vai trò mặc định bằng danh sách authority chính xác do bạn đưa vào. Khi muốn cả `ROLE_ADMIN` lẫn `invoice:read`, hãy viết:

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})
```

Trong annotation `@WithMockUser`, không đặt `roles` khác mặc định cùng với `authorities`: Spring Security Test không cho kết hợp hai thuộc tính theo cách đó. Hai ví dụ sau là **cấu hình sai, chỉ dùng để nhận biết lỗi**, không đưa vào test đang chạy:

```java
// SAI: roles tự thêm ROLE_, không được truyền giá trị đã có prefix.
@WithMockUser(roles = "ROLE_ADMIN")

// SAI: roles được đặt khác mặc định cùng lúc với authorities.
@WithMockUser(roles = "ADMIN", authorities = "invoice:read")
```

Nếu cần các quyền trộn nhiều kiểu tên, dùng `authorities = {...}` và ghi rõ mọi giá trị; không dựa vào việc `roles` và `authorities` sẽ hợp nhất.

## 3. Quy tắc đối chiếu: roles và authorities

Hãy coi `Authentication.getAuthorities()` là **dữ liệu đầu vào thực** của phép kiểm tra, còn `hasRole` và `hasAuthority` là **điều kiện**. Với prefix mặc định:

| Người dùng giả lập | Rule trên phương thức | Kết quả | Giải thích |
| --- | --- | --- | --- |
| `roles = "ADMIN"` | `hasRole('ADMIN')` | Cho phép | `roles` tạo `ROLE_ADMIN` |
| `roles = "ADMIN"` | `hasAuthority('ROLE_ADMIN')` | Cho phép | So khớp authority `ROLE_ADMIN` |
| `roles = "ADMIN"` | `hasAuthority('ADMIN')` | Từ chối | Không có chuỗi `ADMIN` |
| `authorities = "ADMIN"` | `hasRole('ADMIN')` | Từ chối | Không có `ROLE_ADMIN` |
| `authorities = "ADMIN"` | `hasAuthority('ADMIN')` | Cho phép | So khớp đúng chuỗi `ADMIN` |
| `authorities = "ROLE_ADMIN"` | `hasRole('ADMIN')` | Cho phép | Rule `hasRole` yêu cầu `ROLE_ADMIN` |
| `authorities = "invoice:read"` | `hasAuthority('invoice:read')` | Cho phép | Permission khớp nguyên văn |
| `roles = "ADMIN"` | `hasAuthority('invoice:read')` | Từ chối | Vai trò `ADMIN` không tự sinh permission |
| `authorities = "SCOPE_invoices.read"` | `hasAuthority('invoice:read')` | Từ chối | `SCOPE_invoices.read` và `invoice:read` là hai chuỗi khác nhau |

**Không có quy tắc “ADMIN mạnh hơn mọi permission” mặc định.** Nếu chính sách muốn admin đọc mọi hóa đơn, hãy diễn tả rõ trong expression (`hasRole('ADMIN') or hasAuthority('invoice:read')`), hoặc định nghĩa và kiểm thử `RoleHierarchy` hay `AuthorizationManager` của ứng dụng. Ví dụ trong bài **không** khai báo role hierarchy.

Tên authority phân biệt chuỗi, bao gồm chữ hoa/thường và dấu hai chấm; `report:read`, `REPORT:READ` và `SCOPE_report:read` khác nhau. `@WithMockUser(roles = "USER")` không tự cấp `ROLE_ADMIN` hoặc quyền đọc một tài nguyên.

### Quy tắc prefix tùy chỉnh

Spring Security cho phép cấu hình prefix vai trò thông qua `GrantedAuthorityDefaults` hoặc cơ chế authorization tương ứng của phiên bản. Nếu ứng dụng đổi prefix từ `ROLE_` thành `PRIV_`, biểu thức `hasRole('ADMIN')` có thể kỳ vọng `PRIV_ADMIN`, trong khi `@WithMockUser(roles = "ADMIN")` **vẫn tự sinh `ROLE_ADMIN`** theo hợp đồng của annotation. Khi đó nên xây mock principal có `authorities = "PRIV_ADMIN"` hoặc dùng fixture thực tế tương ứng, và xác nhận quy tắc đang sử dụng đúng prefix. Đừng thay đổi prefix chỉ để một test thành công.

## 4. Ví dụ chạy được: method security và kiểm thử bằng JUnit 5

### 4.1. Chuẩn bị dependencies

Ví dụ dựa trên **một ứng dụng Spring Boot 3.x dùng Java 17 trở lên**, với plugin Spring Boot/Dependency Management và repository Maven Central đã được cấu hình. Trong `build.gradle` (Groovy), bổ sung:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn khai báo bổ sung cho dự án Spring Boot hiện có**, không phải toàn bộ `build.gradle`. `spring-security-test` cung cấp `@WithMockUser`, `@WithAnonymousUser` và các listener liên quan. `spring-boot-starter-test` cung cấp JUnit 5 và cơ chế chạy test với Spring Context.

### 4.2. Bật method security

Tệp **`src/main/java/demo/roles/MethodRoleDemoApplication.java`**:

```java
package demo.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodRoleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodRoleDemoApplication.class, args);
    }
}
```

`@EnableMethodSecurity` cho phép Spring Security chặn lời gọi đến các Spring bean có `@PreAuthorize`. Nếu thiếu annotation này và không có cấu hình method security tương đương, việc đặt `@PreAuthorize` lên phương thức chưa đủ để thực thi rule. Trong ví dụ, test luôn gọi **bean được Spring inject**, để đi qua proxy/AOP bảo vệ; không dùng `new InvoiceService()` rồi kết luận về bảo mật.

### 4.3. Tạo service với các quy tắc độc lập

Tệp **`src/main/java/demo/roles/InvoiceService.java`**:

```java
package demo.roles;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    @PreAuthorize("hasRole('ADMIN')")
    public String approveInvoice() {
        return "APPROVED";
    }

    @PreAuthorize("hasAuthority('ROLE_ADMIN')")
    public String checkExplicitRoleAuthority() {
        return "ROLE_ADMIN_OK";
    }

    @PreAuthorize("hasAuthority('ADMIN')")
    public String checkBareAdminAuthority() {
        return "ADMIN_OK";
    }

    @PreAuthorize("hasAuthority('invoice:read')")
    public String readInvoice() {
        return "INVOICE_READ";
    }

    @PreAuthorize("hasAuthority('invoice:write')")
    public String writeInvoice() {
        return "INVOICE_WRITE";
    }

    @PreAuthorize("hasAuthority('SCOPE_invoices.read')")
    public String readWithScopeAuthority() {
        return "SCOPE_READ";
    }

    @PreAuthorize("hasRole('ADMIN') and hasAuthority('invoice:read')")
    public String auditInvoice() {
        return "AUDITED";
    }

    @PreAuthorize("isAuthenticated()")
    public String currentUsername() {
        return SecurityContextHolder.getContext()
                .getAuthentication().getName();
    }
}
```

Tám phương thức tạo ra những điều kiện khác nhau: role `ADMIN`, authority có sẵn prefix `ROLE_ADMIN`, authority không prefix `ADMIN`, permission `invoice:read`/`invoice:write`, scope kiểu OAuth2, tổ hợp **AND**, và điều kiện đã xác thực. Chúng trả về chuỗi đơn giản để kiểm thử quy tắc phân quyền mà không cần database hay HTTP controller.

### 4.4. Bộ test có cả ca được phép và bị từ chối

Tệp **`src/test/java/demo/roles/InvoiceServiceSecurityTest.java`**:

```java
package demo.roles;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class InvoiceServiceSecurityTest {
    @Autowired
    private InvoiceService service;

    private static Set<String> currentAuthorities() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        return auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    @WithMockUser
    void defaultUserHasOnlyRoleUser() {
        assertEquals("user", service.currentUsername());
        assertEquals(Set.of("ROLE_USER"), currentAuthorities());
        assertThrows(AccessDeniedException.class, service::approveInvoice);
    }

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void customUsernameAndAdminRoleAreAvailable() {
        assertEquals("mai", service.currentUsername());
        assertEquals(Set.of("ROLE_ADMIN"), currentAuthorities());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void rolesAutomaticallyAddRolePrefix() {
        assertTrue(currentAuthorities().contains("ROLE_ADMIN"));
        assertEquals("ROLE_ADMIN_OK",
                service.checkExplicitRoleAuthority());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void rolesDoNotAlsoGrantBareAdminAuthority() {
        assertThrows(AccessDeniedException.class,
                service::checkBareAdminAuthority);
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void exactRoleAuthorityAlsoSatisfiesHasRole() {
        assertEquals(Set.of("ROLE_ADMIN"), currentAuthorities());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void bareAuthoritySatisfiesHasAuthorityButNotHasRole() {
        assertEquals(Set.of("ADMIN"), currentAuthorities());
        assertEquals("ADMIN_OK", service.checkBareAdminAuthority());
        assertThrows(AccessDeniedException.class,
                service::approveInvoice);
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readPermissionDoesNotNeedRolePrefix() {
        assertEquals(Set.of("invoice:read"), currentAuthorities());
        assertEquals("INVOICE_READ", service.readInvoice());
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readPermissionDoesNotImplyWritePermission() {
        assertThrows(AccessDeniedException.class, service::writeInvoice);
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotAutomaticallyGrantReadPermission() {
        assertThrows(AccessDeniedException.class, service::readInvoice);
    }

    @Test
    @WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})
    void mixedAuthoritiesCanSatisfyCombinedRule() {
        assertEquals(Set.of("ROLE_ADMIN", "invoice:read"),
                currentAuthorities());
        assertEquals("AUDITED", service.auditInvoice());
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void combinedRuleRejectsMissingReadPermission() {
        assertThrows(AccessDeniedException.class, service::auditInvoice);
    }

    @Test
    @WithMockUser(roles = {"ADMIN", "EDITOR"})
    void multipleRolesBecomeMultiplePrefixedAuthorities() {
        assertEquals(Set.of("ROLE_ADMIN", "ROLE_EDITOR"),
                currentAuthorities());
        assertEquals("APPROVED", service.approveInvoice());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_invoices.read")
    void scopeNamedAuthorityIsComparedLiterally() {
        assertEquals("SCOPE_READ", service.readWithScopeAuthority());
        assertThrows(AccessDeniedException.class, service::readInvoice);
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotCallAuthenticatedMethod() {
        assertThrows(AccessDeniedException.class, service::currentUsername);
    }
}
```

**Chạy test** từ thư mục gốc của dự án:

```bash
./gradlew test --tests 'demo.roles.InvoiceServiceSecurityTest'
```

Trên Windows PowerShell dùng `.\gradlew.bat test --tests "demo.roles.InvoiceServiceSecurityTest"`. **Kỳ vọng:** cả 14 test đều pass khi chạy trên cấu hình mẫu với prefix `ROLE_` mặc định. Câu trả lời của các phương thức như `APPROVED`, `INVOICE_READ` hay `AUDITED` là các giá trị được assert trong test, không phải các dòng sẽ tự in ra stdout. Dòng tóm tắt Gradle phụ thuộc cấu hình build, vì vậy không giả định một transcript console cố định.

### Vì sao test này có ý nghĩa?

- `@SpringBootTest` tạo Spring application context; service được inject qua Spring nên interceptor của `@EnableMethodSecurity` có cơ hội áp dụng `@PreAuthorize`.
- Test khẳng định **authority thực tế** qua `currentAuthorities()`. Nếu chỉ assert kết quả cho phép, dễ bỏ qua một test đang vô tình được cấp nhiều quyền hơn dự định.
- `assertThrows(AccessDeniedException.class, ...)` kiểm tra lời gọi trực tiếp đến service bị chặn khi thiếu quyền. Với method security, không nên kỳ vọng đối tượng `MockMvc` hoặc HTTP status xuất hiện nếu test không gửi HTTP request.
- Cặp `roles = "ADMIN"` ↔ `authorities = "ADMIN"` chứng minh chúng tạo ra authority khác nhau; cặp `roles = "ADMIN"` ↔ `authorities = "ROLE_ADMIN"` chứng minh hai cách có thể cùng thỏa `hasRole('ADMIN')`.
- Test kết hợp dùng `authorities = {"ROLE_ADMIN", "invoice:read"}` thay vì cố gắng truyền đồng thời `roles` và `authorities` vào annotation.

Nếu sửa `@PreAuthorize("hasRole('ADMIN')")` thành `hasAuthority('ADMIN')` nhưng không đổi test, các ca cho phép/bị từ chối tương ứng sẽ đổi kết quả. Đó là regression signal hữu ích: **policy thực tế** đã thay đổi.

## 5. Điều gì xảy ra nếu dùng @WithMockUser sai cách?

### 5.1. Trộn roles và authorities

Không viết:

```java
@WithMockUser(roles = {"ADMIN"}, authorities = {"invoice:read"})
```

Spring Security Test không hợp nhất hai danh sách theo cách này: nếu `authorities` được chỉ định, `roles` không được đổi khỏi giá trị mặc định. Test có thể thất bại **ngay ở bước dựng SecurityContext**, trước khi method security được kiểm tra. Dùng:

```java
@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})
```

để cấp chính xác cả hai authority.

### 5.2. Đưa ROLE_ vào roles

Không viết `@WithMockUser(roles = "ROLE_ADMIN")`. `roles` nhận **tên role không có prefix**, bởi factory tự thêm `ROLE_` và kiểm tra giá trị đầu vào. Viết `roles = "ADMIN"` hoặc `authorities = "ROLE_ADMIN"`.

### 5.3. Cứ thấy 403 là nghĩ rule method đã chạy

Nếu gọi qua HTTP, `403 Forbidden` có thể đến từ HTTP authorization, CSRF, method security hoặc handler khác. Khi gọi trực tiếp bean bằng JUnit, thường kiểm tra `AccessDeniedException`/kiểu con; khi đi qua `MockMvc`, thêm phép kiểm tra status **và** body của ca được phép để xác nhận controller và service thực sự được gọi. Cần xác định tầng đang được test, không suy luận ngược từ một mã HTTP.

### 5.4. Không bật method security hoặc bỏ qua proxy

Ví dụ sau **không kiểm tra đúng interceptor**:

```java
var service = new InvoiceService(); // Đối tượng do new tạo, không qua Spring proxy.
service.approveInvoice();           // Không có proxy để áp dụng @PreAuthorize.
```

Tương tự, gọi phương thức có `@PreAuthorize` từ một phương thức khác **trong cùng object** có thể là self-invocation, không đi qua AOP proxy; annotation ở phương thức đích khi ấy có thể không chạy theo proxy mode. Test qua Spring bean, giữ các điểm gọi liên quan đi qua proxy; với yêu cầu đặc biệt cần chọn thiết kế bảo mật phù hợp và test luồng thực tế.

## 6. Class-level, method-level và thời điểm tạo SecurityContext

Annotation có thể đặt ở **lớp test** để tất cả test kế thừa cùng người dùng, rồi thay ở phương thức cụ thể. Ví dụ minh họa (không phải phần bổ sung vào bộ test ở trên):

```java
@WithMockUser(roles = "USER")
class ExampleTests {
    @Test
    void normalUserCase() {
        // ROLE_USER.
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminOverrideCase() {
        // ROLE_ADMIN của method; không cộng dồn ROLE_USER từ class.
    }

    @Test
    @WithAnonymousUser
    void anonymousOverrideCase() {
        // Không dùng mock user ROLE_USER của class.
    }
}
```

Trong Spring Test, mặc định `@WithMockUser` dựng context ở sự kiện `TEST_METHOD`, trước `@BeforeEach`. Nếu cần để `@BeforeEach` chạy **trước** khi mock security context được thiết lập, có thể dùng:

```java
@WithMockUser(
    username = "mai",
    roles = "ADMIN",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
```

Tệp test dùng tùy chọn trên cần import `org.springframework.security.test.context.support.TestExecutionEvent`. Lúc này context được dựng sau `@BeforeEach` nhưng trước thân `@Test`. Chỉ dùng tùy chọn này khi thứ tự khởi tạo thực sự quan trọng; một `@BeforeEach` gọi service cần quyền sẽ không thấy mock user nếu context chưa được dựng.

SecurityContext thường gắn với luồng test hiện tại. Nếu code chạy trên thread khác như `@Async` hoặc test gửi request HTTP đến server thật với `webEnvironment = RANDOM_PORT`, context trong test thread **không tự động trở thành authentication của luồng server**. Với end-to-end test, phải xác thực request bằng cookie/session, HTTP Basic, bearer token hoặc cách phù hợp.

## 7. Khi nào dùng @WithMockUser, @WithUserDetails, @WithSecurityContext?

| Công cụ | Phù hợp | Không tự chứng minh |
| --- | --- | --- |
| `@WithMockUser` | Kiểm tra rule method/MockMvc với username và các role/authority chủ động khai báo | Tài khoản thật tồn tại, password đúng, JWT chứa claim phù hợp |
| `@WithUserDetails("mai")` | Test cần principal thực tế do một bean `UserDetailsService` tải lên | Toàn bộ quá trình đăng nhập ngoài HTTP |
| `@WithSecurityContext` | Custom principal, kiểu `Authentication` riêng hoặc fixture bảo mật phức tạp | Tính đúng của protocol/token bên ngoài nếu không test |
| `MockMvc` với `user(...)` hoặc `jwt(...)` | Gắn principal/claims/authorities cho **một request** để kiểm tra lớp HTTP | Authentication thật nếu vẫn dùng request giả lập |
| HTTP integration test gửi credentials/token thật | Kiểm thử cả bộ lọc, parser token, chuyển claim thành authority và ứng dụng | Mọi trường hợp quyền ở từng object nếu không tạo test riêng |

Nếu ứng dụng ép kiểu `authentication.getPrincipal()` sang một lớp `CustomUserDetails`, principal chuẩn của `@WithMockUser` là `User` có thể gây lỗi ép kiểu dù logic quyền đúng. Dùng `@WithUserDetails` với fixture thực hoặc `@WithSecurityContext` tùy biến để test đúng kiểu principal của ứng dụng.

Trong OAuth2 Resource Server, quyền `SCOPE_invoices.read` thường được sinh từ scope của bearer token qua bộ chuyển đổi phù hợp. Việc gán `@WithMockUser(authorities = "SCOPE_invoices.read")` chỉ kiểm tra rằng **method chấp nhận authority đó**; nó chưa kiểm tra JWT hợp lệ hoặc converter ánh xạ scope đúng. Cần test thêm phần converter/filter bằng `jwt()` hoặc request bearer token thực tùy mục tiêu.

## 8. Ma trận QA cho một phương thức được bảo vệ

Giả sử hệ thống có:

```java
@PreAuthorize("hasRole('ADMIN') and hasAuthority('invoice:read')")
public Invoice detailForAudit(String id) { /* business logic */ }
```

Đây là **chữ ký và rule minh họa**, chưa phải một chương trình độc lập; `Invoice` và phần xử lý nghiệp vụ phải do ứng dụng định nghĩa.

| Principal giả lập | Authority có thật | Kỳ vọng | Vì sao |
| --- | --- | --- | --- |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` | Từ chối | Thiếu `invoice:read` |
| `@WithMockUser(authorities = "invoice:read")` | `invoice:read` | Từ chối | Thiếu `ROLE_ADMIN` |
| `@WithMockUser(authorities = "ADMIN")` | `ADMIN` | Từ chối | Thiếu cả hai |
| `@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:read"})` | Cả hai | Cho phép | Đúng hai điều kiện |
| `@WithMockUser(authorities = {"ROLE_ADMIN", "invoice:write"})` | `ROLE_ADMIN` + `invoice:write` | Từ chối | Write không thay read |
| `@WithAnonymousUser` | Authority anonymous, nếu có | Từ chối | Không thỏa role và permission |

Test đủ sáu ca giúp tránh lỗi chuyển từ `and` sang `or`, lỗi cấp nhầm role theo prefix, lỗi đồng nhất read/write và lỗi mock user có nhiều quyền ngoài ý muốn. Với phương thức truy cập hóa đơn theo `id`, cần thêm rule kiểm tra **ownership/tenant/resource** nếu đó là hợp đồng của nghiệp vụ: `@WithMockUser` chỉ cấp authority, không tự giới hạn tài nguyên cụ thể.

### Checklist khi kiểm thử một method mới

1. Xác định trước **phương thức cần bảo vệ** và expression `@PreAuthorize`; ghi rõ bạn muốn kiểm chứng role, permission hay cả hai.
2. Viết bảng authority **nguyên văn** sẽ có trong `Authentication`, gồm prefix và chữ hoa/thường.
3. Tạo ít nhất một ca cho phép, một ca thiếu role, một ca thiếu permission và một ca không xác thực, khi những trường hợp đó có ý nghĩa.
4. Gọi method trên bean do Spring quản lý, bảo đảm `@EnableMethodSecurity` đang bật.
5. Assert **kết quả thực** ở ca thành công và `AccessDeniedException` ở ca bị chặn; đừng chỉ xem test có chạy mà không exception hay không.
6. Bổ sung kiểm thử principal thật hoặc JWT/HTTP khi nghiệp vụ phụ thuộc user repository, claim, scope, tenant hoặc login.
7. Nếu ứng dụng có `RoleHierarchy` hay đổi prefix `ROLE_`, thiết lập fixture đúng cấu hình rồi chạy lại test matrix.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Phương thức có `@PreAuthorize("hasRole('ADMIN')")`. Hai annotation sau có cùng kết quả không?

```java
@WithMockUser(roles = "ADMIN")
@WithMockUser(authorities = "ROLE_ADMIN")
```

**Giải thích:** trong hai test độc lập, cả hai cấp authority thật `ROLE_ADMIN` với prefix mặc định, nên đều thỏa rule. Không đặt hai annotation lên cùng một test; đây là hai phương án giả lập khác nhau.

**Câu 2.** Tại sao `@WithMockUser(authorities = "ADMIN")` không qua `hasRole('ADMIN')`?

Vì `hasRole('ADMIN')` mặc định tìm `ROLE_ADMIN` còn `authorities = "ADMIN"` cấp đúng chuỗi `ADMIN`. Muốn giữ rule role, dùng `roles = "ADMIN"` hoặc `authorities = "ROLE_ADMIN"`.

**Câu 3.** Vì sao một test có `@WithMockUser(roles = "ADMIN")` không chứng minh admin đọc được `invoice:read`?

Vì role và permission là hai authority độc lập, trừ khi chính sách ứng dụng có thêm role hierarchy hoặc logic ánh xạ. Cần khai báo rule cho admin, hoặc cấp đúng permission mà method yêu cầu.

**Câu 4.** Vì sao test `@WithMockUser` pass nhưng request JWT thực bị 403?

Các nguyên nhân có thể là JWT không được chuyển thành `ROLE_ADMIN`/`invoice:read` như fixture đã giả định, rule HTTP khác rule method, hoặc principal/tenant khác. Test method riêng và test converter/filter/HTTP riêng để tìm đúng nguyên nhân.

## 10. Bài tập thực hành

1. Đổi `approveInvoice()` từ `hasRole('ADMIN')` thành `hasAuthority('ADMIN')`. Dự đoán các test nào thất bại; chạy test và giải thích bằng authority thực, rồi khôi phục policy.
2. Thêm `@PreAuthorize("hasAnyRole('ADMIN', 'AUDITOR')")` cho một phương thức mới. Test `roles = "AUDITOR"`, `authorities = "AUDITOR"` và `authorities = "ROLE_AUDITOR"`.
3. Thay `auditInvoice()` từ `and` thành `or` trong một bản thử nghiệm. Xác nhận ma trận ở mục 8 phát hiện việc nới quyền.
4. Tạo meta-annotation `@WithMockInvoiceReader` dùng `@WithMockUser(authorities = "invoice:read")`, rồi áp dụng cho các test liên quan; bảo đảm vẫn có test thiếu quyền.
5. Nếu dự án dùng custom `UserDetailsService`, viết một test bằng `@WithUserDetails` và so sánh kiểu principal/authority với `@WithMockUser`. Không giả định tài khoản có sẵn; tạo fixture thực trong môi trường test.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext` và thời điểm dựng context.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `hasRole` và `hasAuthority`.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority` và prefix mặc định `ROLE_`.
- [Spring Security — @WithMockUser API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithMockUser.html): định nghĩa chính xác của `roles`, `authorities`, `username` và `setupBefore`.
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): khi cần chuyển từ kiểm thử trực tiếp service sang kiểm thử request HTTP.