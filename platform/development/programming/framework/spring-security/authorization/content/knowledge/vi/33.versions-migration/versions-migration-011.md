# Kiểm chứng hierarchy, tiền tố role và annotation mặc định sau nâng phiên bản

> **Phạm vi:** Spring Security Authorization — **Phiên bản và chuyển đổi**. Bài này tập trung vào nguy cơ thay đổi kết quả phân quyền khi nâng Spring Security hoặc chuyển cấu hình cũ sang `@EnableMethodSecurity`: kế thừa role (`RoleHierarchy`), tiền tố role (`ROLE_` hoặc prefix riêng), và những annotation thực sự được bật mặc định. Mục tiêu cuối cùng là có **ma trận quyết định ALLOW/DENY tự động** trước và sau upgrade; không kết luận rằng chỉ cần ứng dụng khởi động và compile thành công là chính sách còn nguyên.

## 1. Vì sao một lần nâng phiên bản có thể gây lộ quyền?

Một ứng dụng có thể vẫn khởi động, controller vẫn trả JSON, nhưng kết quả authorization đổi:

- `ROLE_ADMIN` trước đây tự kế thừa `ROLE_MANAGER` và `ROLE_USER`; sau nâng version, custom `RoleHierarchy` không còn được nối vào một authorization manager, khiến admin bị từ chối (mất quyền hợp lệ).
- Ứng dụng dùng authority `APP_ADMIN`, nhưng `hasRole('ADMIN')` ở một đường code mới mặc định tìm `ROLE_ADMIN`, dẫn tới `403`; hoặc sửa prefix không đồng bộ làm mở quyền ngoài ý muốn.
- Cấu hình cũ chỉ bật `@Secured`; chuyển sang `@EnableMethodSecurity` mà không tắt pre/post khiến những `@PreAuthorize` tồn tại nhưng trước đây chưa chạy bắt đầu có hiệu lực.
- Ngược lại, chuyển sang `@EnableMethodSecurity` mà quên `securedEnabled=true` hoặc `jsr250Enabled=true` sẽ làm `@Secured`/`@RolesAllowed` không được enforcement ở method security.
- Một class có hai annotation khác nhau được đánh giá nối tiếp; hoặc method-level annotation ghi đè class-level annotation cùng loại. Nếu migration đổi vị trí/loại annotation, kết quả kiểm tra có thể khác dự kiến.
- Bean chứa method không đi qua proxy Spring (self-invocation, gọi `new`, cấu hình proxy khác), nên annotation hoàn toàn không được đánh giá, dù unit test gọi Java method vẫn PASS.

**Không suy ra mọi bản phát hành có cùng API và mặc định.** Ghi rõ tuple `Spring Boot version + Spring Security version + Java version`, đọc migration guide đúng dải version rồi dùng test chạy trên **classpath thực sự** của build đang nâng cấp.

## 2. Khái niệm phải tách biệt: role, authority, prefix, hierarchy

**Authority** là chuỗi trong `Authentication.getAuthorities()`, ví dụ:

~~~text
ROLE_ADMIN
ROLE_MANAGER
ROLE_USER
invoice:read
APP_ADMIN
~~~

**Role** là một quy ước thường được dùng trong authorization expression. Theo cấu hình mặc định phổ biến của Spring Security, `hasRole('ADMIN')` kiểm tra authority `ROLE_ADMIN`; `hasAuthority('ROLE_ADMIN')` kiểm tra đúng chuỗi `ROLE_ADMIN`. Phần `hasAuthority` không tự thêm prefix.

| Biểu thức / dữ liệu | Với prefix mặc định `ROLE_` | Kết quả |
| --- | --- | --- |
| `hasRole('ADMIN')` | Authority `ROLE_ADMIN` | ALLOW |
| `hasRole('ADMIN')` | Chỉ có authority `ADMIN` | DENY |
| `hasAuthority('ADMIN')` | Chỉ có authority `ROLE_ADMIN` | DENY |
| `hasAuthority('ROLE_ADMIN')` | Authority `ROLE_ADMIN` | ALLOW |
| `hasAuthority('invoice:read')` | Authority `invoice:read` | ALLOW |
| `hasRole('USER')` | Chỉ có `ROLE_ADMIN`, **không cấu hình hierarchy** | DENY |
| `hasRole('USER')` | Có `ROLE_ADMIN` và hierarchy `ADMIN > USER` đã được gắn đúng | ALLOW |

Quyền `invoice:read` không mặc nhiên là role, và một người có role `ADMIN` không tự động có mọi permission: chỉ được suy ra khi **policy hoặc hierarchy thực sự định nghĩa** điều đó. Không viết test theo phỏng đoán “ADMIN chắc chắn có mọi quyền”.

### RoleHierarchy nghĩa là gì?

Ví dụ một cây quyền:

~~~text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_USER
~~~

Ý nghĩa `ROLE_ADMIN > ROLE_MANAGER` là quyền có `ROLE_ADMIN` có thể được coi là có `ROLE_MANAGER` trong **những authorization component đã cấu hình sử dụng hierarchy**. Mối quan hệ là bắc cầu: `ADMIN` bao gồm `MANAGER` và `USER`. Nó **không sửa vĩnh viễn** danh sách gốc `Authentication.getAuthorities()`; các evaluator dùng các *reachable authorities* khi quyết định. Vì vậy xem raw authorities trong log mà không thấy `ROLE_USER` không tự chứng minh hierarchy hỏng.

Phân biệt:

- **Nguồn gốc:** token/session/`UserDetailsService` cung cấp authority nào?
- **Chuyển đổi:** claim `roles`/`scope` được map sang `GrantedAuthority` thế nào?
- **Mở rộng hierarchy:** `RoleHierarchy` có diễn giải đúng prefix và quan hệ không?
- **Điểm thực thi:** HTTP rule, `@PreAuthorize`, `@Secured` và `@RolesAllowed` có thực sự sử dụng hierarchy không?

Đừng kết luận từ một test duy nhất. Một cấu hình có thể hoạt động với `@PreAuthorize` nhưng chưa được áp dụng nhất quán ở HTTP matcher hoặc custom `AuthorizationManager`.

## 3. Mặc định của method security và bẫy khi migration

### 3.1. Cấu hình cũ và mới khác nhau ở những điểm quan trọng

`@EnableGlobalMethodSecurity` là cách cấu hình cũ; `@EnableMethodSecurity` là hướng hiện đại sử dụng `AuthorizationManager`. Spring Boot Starter Security **không tự bật method security** chỉ vì đã thêm dependency.

Ở cách cấu hình hiện đại:

~~~java
@EnableMethodSecurity
class SecurityConfiguration {
}
~~~

- `prePostEnabled` mặc định **true**: bật `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`.
- `securedEnabled` mặc định **false**: `@Secured` không được xử lý trừ khi bật tường minh.
- `jsr250Enabled` mặc định **false**: `@RolesAllowed`, `@PermitAll`, `@DenyAll` không được xử lý theo JSR-250 trừ khi bật.
- **Method không có annotation** không tự được bảo vệ bằng method security. Cần HTTP deny-by-default hoặc quy tắc bảo vệ khác ở boundary.
- Khi một method có **nhiều annotation khác loại được bật**, các kiểm tra được thực hiện nối tiếp; về mặt cho phép truy cập, tất cả đều phải cho phép (logic AND).
- Annotation cùng loại trên method có thể **override** annotation tương ứng ở class; không suy ra mặc định class và method cùng loại luôn là AND.

| Cấu hình | `@PreAuthorize` | `@Secured` | `@RolesAllowed` |
| --- | --- | --- | --- |
| `@EnableMethodSecurity` | Bật | Tắt | Tắt |
| `@EnableMethodSecurity(securedEnabled=true)` | Bật | Bật | Tắt |
| `@EnableMethodSecurity(jsr250Enabled=true)` | Bật | Tắt | Bật |
| `@EnableMethodSecurity(securedEnabled=true, jsr250Enabled=true)` | Bật | Bật | Bật |
| `@EnableMethodSecurity(securedEnabled=true, prePostEnabled=false)` | Tắt | Bật | Tắt |

**Ví dụ migration phải giữ ý định cũ:** nếu trước đây dùng:

~~~java
@EnableGlobalMethodSecurity(securedEnabled = true)
class LegacyConfig {
}
~~~

và muốn giữ **chỉ** nhóm `@Secured`, không bất ngờ bật pre/post, cấu hình mới là:

~~~java
@EnableMethodSecurity(securedEnabled = true, prePostEnabled = false)
class NewConfig {
}
~~~

Đừng thay máy móc thành `@EnableMethodSecurity(securedEnabled=true)` rồi cho rằng mọi annotation sẽ giữ nguyên trạng thái. Ngược lại, nếu migration chủ đích bật pre/post, hãy ghi rõ thay đổi và kiểm thử tác động đến các phương thức có annotation cũ chưa từng được enforcement.

### 3.2. Phân biệt cú pháp và thời điểm kiểm tra

- `@PreAuthorize("hasRole('USER')")` kiểm **trước** khi method được thực thi; cũng hỗ trợ SpEL trên tham số.
- `@PostAuthorize(...)` kiểm **sau** khi method trả kết quả; không dùng làm chốt quyền duy nhất cho thao tác đã ghi dữ liệu DB.
- `@Secured("ROLE_USER")` nhận tên authority/role theo định dạng annotation; trong cấu hình mặc định thường ghi đầy đủ `ROLE_USER`, khác cú pháp `hasRole('USER')`.
- `@RolesAllowed("USER")` là JSR-250; dùng `jakarta.annotation.security.RolesAllowed` trong dòng Spring Boot 3/Spring Security 6, không bê nguyên import `javax.annotation.security.RolesAllowed` từ ứng dụng Java EE cũ.
- `@PermitAll` và `@DenyAll` thuộc cơ chế JSR-250 khi được bật; `@PermitAll` trên method có thể không có nghĩa là bỏ qua một **@PreAuthorize khác đang chạy** hay bỏ qua HTTP filter chain. Không dùng annotation riêng lẻ để phỏng đoán tổng kết quả.
- Với custom meta-annotation, annotation ở interface/class/method, hãy test từng endpoint/service được bảo vệ. Spring AOP có giới hạn self-invocation; conflict annotations từ nhiều interface có thể gây lỗi khởi động.

Khi framework nâng cấp, có thể thay đổi cách phát hiện annotation, proxy, method interface, expression evaluation hoặc cách kết hợp nhiều interceptor. **Chỉ một test method có quyền** không đủ để phát hiện permission bị mở rộng.

## 4. Tiền tố role: phải nhất quán từ nguồn Authentication tới evaluator

Prefix thường là `ROLE_`. Các thành phần dùng prefix có thể bao gồm:

1. Mapping từ IdP/JWT/group vào `GrantedAuthority`, ví dụ claim `admin` -> `ROLE_ADMIN`.
2. `@WithMockUser(roles = "ADMIN")` trong test mặc định tạo authority `ROLE_ADMIN`.
3. Expression `hasRole('ADMIN')` / `hasAnyRole(...)`.
4. Annotation `@Secured` hoặc `@RolesAllowed`.
5. `RoleHierarchy` và custom `AuthorizationManager`.

**Lỗi migration hay gặp:**

~~~text
Token/Authentication authority: APP_ADMIN
Code after upgrade:           hasRole("ADMIN")
Default role prefix:          ROLE_
Authority it seeks:          ROLE_ADMIN
Result:                      DENY (403)
~~~

Hoặc khi nhân viên sửa mapping token thành `ROLE_ADMIN` nhưng policy cũ vẫn dùng `APP_ADMIN`, một số API hoạt động còn API khác bị chặn.

Trong Spring Security 6.5, `GrantedAuthorityDefaults` hỗ trợ công bố prefix tùy chỉnh. Khai báo bean **static** sớm để method-security configuration nhìn thấy:

~~~java
// Snippet minh họa cấu hình prefix riêng; không đặt cạnh
// cấu hình ROLE_ mặc định ở ví dụ chạy thực tế bên dưới.
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_");
}
~~~

Khi chọn `APP_`, phải điều chỉnh đồng bộ mapper, hierarchy và các expression/annotation tương ứng. Với test, nên dùng:

~~~java
@WithMockUser(authorities = "APP_ADMIN")
~~~

Không nhầm `@WithMockUser(roles="ADMIN")` là tự tuân theo custom `GrantedAuthorityDefaults`: annotation test thường tạo `ROLE_ADMIN` theo quy ước riêng của nó. **Kiểm tra raw authority thực tế** thay vì suy đoán.

Một minh họa cho cấu hình custom-prefix và hierarchy **riêng** trên nhánh Spring Security 6.5:

~~~java
// Snippet đặt trong @Configuration của ứng dụng sử dụng APP_.
// Các import Spring tương ứng được cung cấp trong project.
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_");
}

@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy(
            "APP_ADMIN > APP_MANAGER\nAPP_MANAGER > APP_USER");
}

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy roleHierarchy) {
    var handler = new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(roleHierarchy);
    handler.setDefaultRolePrefix("APP_"); // API dành cho cấu hình nhánh 6.5
    return handler;
}
~~~

Lưu ý khi chuyển sang Spring Security 7.x: `setDefaultRolePrefix` trên expression handler được đánh dấu deprecated từ 7.0; tài liệu 7.x hướng tới `AuthorizationManagerFactory`. **Không sao chép cấu hình 6.5 nguyên xi rồi mặc định nó vẫn là đường tùy biến khuyến nghị.** Chốt mã tương thích với version cụ thể, kiểm thử `hasRole`, `@Secured`, JSR-250 và request authorization độc lập. Tên/lớp API cũ có thể vẫn tồn tại nhưng đã bị deprecate.

`hasAuthority("APP_ADMIN")` là chuỗi cụ thể, không tự chuyển thành `ROLE_ADMIN` hay `APP_APP_ADMIN`. Đừng thay `hasAuthority` thành `hasRole` trong một commit cơ khí mà không rà soát semantics.

## 5. Checklist thu thập baseline trước khi nâng

Trước khi sửa dependency, ghi **bằng chứng** từ ứng dụng hiện tại. Một baseline tốt gồm:

- Spring Boot/Spring Security version chính xác (xem Maven dependency tree hoặc Gradle dependencies), Java runtime và phiên bản annotation API.
- Danh sách `SecurityFilterChain`, `@EnableGlobalMethodSecurity`/`@EnableMethodSecurity`, `@EnableReactiveMethodSecurity` nếu có WebFlux.
- Các bean cấu hình `RoleHierarchy`, `GrantedAuthorityDefaults`, `MethodSecurityExpressionHandler`, custom `AuthorizationManager`, legacy voters/`AccessDecisionManager`.
- Tất cả `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter`, `@Secured`, `@RolesAllowed`, `@PermitAll`/`@DenyAll`, custom meta-annotation và nơi đặt chúng ở class/interface/method.
- Mapping authority từ JWT/IdP/LDAP/DB. Xác định chuỗi thô thực sự trong `Authentication.getAuthorities()`, kể cả prefix, chữ hoa/thường.
- Ma trận ai được làm gì theo chức năng và object, có role kế thừa, role không kế thừa, người thiếu quyền, anonymous và tenant khác.
- Các đặc tính proxy/transaction: bean thực sự do Spring tạo; self-invocation có thể bypass kiểm tra; method không được gắn annotation.
- Test HTTP và test service (bao gồm negative tests) phải chạy trên version cũ để có baseline so sánh.

Ghi lại expected ALLOW/DENY **theo yêu cầu nghiệp vụ**, không chỉ copy kết quả hiện tại. Nếu hệ cũ có lỗ hổng, “giữ nguyên hành vi cũ” không được phép biến thành mục tiêu bảo mật. Mọi delta sau upgrade cần được phân loại: **cố ý sửa policy**, **vô tình nới quyền**, **vô tình siết quyền**.

## 6. Cấu hình mẫu Spring Security 6.5 với hierarchy và ba kiểu annotation

Ví dụ chạy trong một **Spring Boot 3.x / Spring Security 6.5.x / Java 17** project; không áp dụng nguyên các import/API này cho nhánh 7.x mà chưa xác minh migration guide. Nó chủ ý dùng prefix mặc định `ROLE_` để có baseline rõ ràng trước khi thử custom prefix.

### 6.1. Maven dependencies

Dự án đã có Spring Boot parent/BOM quản lý version:

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
    <dependency>
        <groupId>jakarta.annotation</groupId>
        <artifactId>jakarta.annotation-api</artifactId>
    </dependency>
</dependencies>
~~~

Không cần controller HTTP cho method-security test. Nếu ứng dụng thật có web API thì phải test riêng `SecurityFilterChain` và HTTP status. `spring-security-test` cung cấp `@WithMockUser`; Spring Boot starter test cung cấp JUnit Jupiter/Spring Test.

### 6.2. Cấu hình đầy đủ

File `src/main/java/com/example/authupgrade/UpgradeSecurityConfig.java`:

~~~java
package com.example.authupgrade;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)
public class UpgradeSecurityConfig {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
                "ROLE_ADMIN > ROLE_MANAGER\n"
                + "ROLE_MANAGER > ROLE_USER");
    }

    // Spring Security 6.5: nối hierarchy vào pre/post expression handler.
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }

    @Bean
    PermissionService permissionService() {
        return new PermissionService();
    }
}
~~~

`ROLE_ADMIN > ROLE_MANAGER` và `ROLE_MANAGER > ROLE_USER` là hai cạnh có hướng, cho phép kế thừa **bắc cầu**. Việc publish một `RoleHierarchy` bean chưa phải lý do để bỏ qua kiểm tra từng authorization manager; ví dụ đã cấu hình rõ expression handler cho `@PreAuthorize` và test sẽ xác nhận kết quả thật. `@EnableMethodSecurity(securedEnabled=true,jsr250Enabled=true)` bật **cả ba** nhóm annotation, tránh test “PASS” vì cơ chế đang bị tắt.

### 6.3. Service được bảo vệ

File `src/main/java/com/example/authupgrade/PermissionService.java`:

~~~java
package com.example.authupgrade;

import jakarta.annotation.security.RolesAllowed;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;

public class PermissionService {

    @PreAuthorize("hasRole('USER')")
    public String read() {
        return "read";
    }

    @PreAuthorize("hasRole('MANAGER')")
    public String manage() {
        return "manage";
    }

    @PreAuthorize("hasAuthority('ROLE_USER')")
    public String readByLiteralAuthority() {
        return "literal";
    }

    @Secured("ROLE_USER")
    public String readBySecured() {
        return "secured";
    }

    @RolesAllowed("USER")
    public String readByJsr250() {
        return "jsr250";
    }

    @PreAuthorize("hasAuthority('invoice:export')")
    public String exportInvoice() {
        return "export";
    }

    public String notAnnotated() {
        return "unguarded";
    }
}
~~~

`PermissionService` được tạo qua `@Bean` trong `UpgradeSecurityConfig` nên Spring có thể tạo method-security proxy. `notAnnotated()` cố ý cho thấy **không có annotation nghĩa là không có method-security rule tự động**; ứng dụng thực không nên coi đây là một endpoint public an toàn chỉ vì có `@EnableMethodSecurity`.

### 6.4. Kiểm thử phân quyền trước/sau upgrade bằng JUnit

File `src/test/java/com/example/authupgrade/UpgradeMethodSecurityTest.java`:

~~~java
package com.example.authupgrade;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(classes = UpgradeSecurityConfig.class)
class UpgradeMethodSecurityTest {

    @Autowired
    PermissionService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminInheritsManagerAndUser() {
        assertEquals("read", service.read());
        assertEquals("manage", service.manage());
        assertEquals("literal", service.readByLiteralAuthority());
        assertEquals("secured", service.readBySecured());
        assertEquals("jsr250", service.readByJsr250());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userMayReadButCannotManage() {
        assertEquals("read", service.read());
        assertEquals("secured", service.readBySecured());
        assertEquals("jsr250", service.readByJsr250());
        assertThrows(AccessDeniedException.class, service::manage);
    }

    @Test
    @WithMockUser(roles = "MANAGER")
    void managerInheritsUserButNotAdminOnlyRights() {
        assertEquals("read", service.read());
        assertEquals("manage", service.manage());
        assertThrows(AccessDeniedException.class, service::exportInvoice);
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void rawAdminIsNotRoleAdminWithDefaultPrefix() {
        assertThrows(AccessDeniedException.class, service::read);
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void explicitAuthorityRoleAdminWorks() {
        assertEquals("read", service.read());
        assertEquals("manage", service.manage());
    }

    @Test
    @WithMockUser(authorities = "invoice:export")
    void granularPermissionIsNotImplicitRole() {
        assertEquals("export", service.exportInvoice());
        assertThrows(AccessDeniedException.class, service::read);
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void roleAdminDoesNotAutomaticallyHaveAllPermissions() {
        assertThrows(AccessDeniedException.class, service::exportInvoice);
    }

    @Test
    @WithMockUser(roles = "USER")
    void methodWithoutAnnotationHasNoMethodGate() {
        // Phát hiện hành vi thực; không coi đó là authorization an toàn.
        assertEquals("unguarded", service.notAnnotated());
    }
}
~~~

Chạy từ thư mục Maven project có cấu hình Spring Boot 3 tương ứng:

~~~bash
./mvnw -Dtest=UpgradeMethodSecurityTest test
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd -Dtest=UpgradeMethodSecurityTest test
~~~

**Kỳ vọng khi đúng cấu hình 6.5:** tám test PASS; khi chạy trên version mới, một test FAIL cho biết hành vi phân quyền cần được kiểm tra. Không có `System.out.println` nên không có stdout chương trình ổn định; Maven hiển thị trạng thái test/build theo phiên bản plugin. Ví dụ này xác minh **method security trong Spring context thật**, không mock chính authorization evaluator.

Nếu test `@Secured`/JSR-250 bất ngờ từ chối `ROLE_ADMIN` khi `@PreAuthorize` cho phép, hãy kiểm tra **hierarchy có được dùng bởi từng interceptor** của version đang chạy hay không. Đừng “sửa test cho PASS” bằng cách gán thêm `ROLE_USER` vào user ADMIN rồi che mất regression; trong test nâng phiên bản cần giữ đầu vào chỉ có `ROLE_ADMIN` để hierarchy thật sự bị thử.

### 6.5. Ma trận expected cho cấu hình mẫu

| Principal với authorities thực tế | `read()`/`hasRole(USER)` | `manage()`/`hasRole(MANAGER)` | `exportInvoice()` |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | ALLOW qua hierarchy | ALLOW qua hierarchy | DENY |
| `ROLE_MANAGER` | ALLOW qua hierarchy | ALLOW | DENY |
| `ROLE_USER` | ALLOW | DENY | DENY |
| `ADMIN` (không prefix) | DENY | DENY | DENY |
| `invoice:export` | DENY | DENY | ALLOW |
| Không có Authentication phù hợp | DENY | DENY | DENY |

Đây là **baseline nghiệp vụ giả định** của ví dụ, không phải chính sách mặc định cho mọi doanh nghiệp. Role ADMIN có quyền gì ngoài hierarchy phải được định nghĩa rõ, không áp dụng `permitAll()` vì tên role.

## 7. Chương trình Java 17 độc lập minh họa prefix và transitive hierarchy

Để có thể xác minh trực tiếp bằng `javac`/`java` mà không cần Spring, đoạn sau mô phỏng **khái niệm** reachable authorities và prefix. Nó **không phải bản sao triển khai nội bộ Spring Security**; bài test `@SpringJUnitConfig` phía trên mới kiểm framework thực.

Tạo một file **`RoleContractDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class RoleContractDemo {

    private static Set<String> reachable(
            Set<String> granted, Map<String, Set<String>> implies) {
        Set<String> result = new HashSet<>(granted);

        boolean changed;
        do {
            changed = false;
            for (String authority : Set.copyOf(result)) {
                changed |= result.addAll(
                        implies.getOrDefault(authority, Set.of()));
            }
        } while (changed);

        return result;
    }

    private static boolean hasRole(
            Set<String> authorities, String prefix, String role) {
        String required = prefix.isEmpty() || role.startsWith(prefix)
                ? role
                : prefix + role;
        return authorities.contains(required);
    }

    public static void main(String[] args) {
        Map<String, Set<String>> hierarchy = Map.of(
                "ROLE_ADMIN", Set.of("ROLE_MANAGER"),
                "ROLE_MANAGER", Set.of("ROLE_USER"));

        Set<String> rawAdmin = Set.of("ROLE_ADMIN");
        Set<String> expanded = reachable(rawAdmin, hierarchy);

        System.out.println("ADMIN inherited USER: "
                + hasRole(expanded, "ROLE_", "USER"));
        System.out.println("Without hierarchy USER: "
                + hasRole(rawAdmin, "ROLE_", "USER"));
        System.out.println("Raw ADMIN equals ROLE_ADMIN: "
                + Set.of("ADMIN").contains("ROLE_ADMIN"));
        System.out.println("APP_ADMIN with APP_ prefix: "
                + hasRole(Set.of("APP_ADMIN"), "APP_", "ADMIN"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RoleContractDemo.java
java RoleContractDemo
~~~

**Stdout chính xác:**

~~~text
ADMIN inherited USER: true
Without hierarchy USER: false
Raw ADMIN equals ROLE_ADMIN: false
APP_ADMIN with APP_ prefix: true
~~~

Hàm `reachable` mở rộng bắc cầu đến khi không còn thay đổi, kể cả hierarchy dài nhiều tầng. Nó không sửa `rawAdmin`, giống ý tưởng rằng quyền thực trong Authentication và quyền suy ra cho phép đánh giá là hai khái niệm khác nhau. Nhưng **không dùng hàm này để thay Spring authorization manager** trong production; các quy tắc về anonymous, expression, method proxy, JSR-250 và lỗi framework cần test tích hợp.

## 8. Kiểm chứng annotation mặc định khi thay cấu hình

### Bật đúng nhóm annotation

Nếu codebase dùng cả ba nhóm, phải ghi rõ:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Nếu chỉ dùng nhóm `@Secured` cũ và muốn giữ chính xác behavior trước upgrade:

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true,
    jsr250Enabled = false
)
~~~

Với `@PreAuthorize`, cấu hình `prePostEnabled=false` khiến annotation đó **không được intercept** bởi nhóm pre/post mặc định; nếu cần pre/post thì phải bật. Với `@Secured` và `@RolesAllowed`, không bật tương ứng thì chúng **không tạo ra method gate qua cơ chế đó**. Điều này đặc biệt nguy hiểm khi test chỉ khẳng định “user có quyền gọi thành công” mà không test “user thiếu quyền phải bị chặn”.

### Thứ tự kiểm tra và annotation trên class

~~~java
@PreAuthorize("hasRole('USER')")
public class ExampleService {

    // Cùng loại @PreAuthorize ở method có thể override
    // @PreAuthorize trên class, không tự động AND.
    @PreAuthorize("hasRole('ADMIN')")
    public String adminAction() {
        return "ok";
    }
}
~~~

Đây là snippet minh họa, không phải class thuộc project mẫu. Nếu business rule yêu cầu vừa `USER` vừa `ADMIN`, hãy mô tả tường minh trong một expression, hoặc kiểm tra theo chính sách nghiệp vụ thay vì kỳ vọng inheritance tự tạo AND.

Ngược lại, khi một method đồng thời mang `@Secured("ROLE_USER")` và `@PreAuthorize("hasAuthority('invoice:export')")`, và **cả hai nhóm được bật**, các kiểm tra áp dụng nối tiếp (cần đáp ứng cả hai). Thứ tự interceptor có thể ảnh hưởng exception hoặc giao dịch, nhưng không được dựa vào thứ tự để lách quyền.

### JSR-250 và Jakarta namespace

Ở Spring Boot 3, import nên là:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Nếu migration từ Java EE/Boot 2 còn import `javax.annotation.security.RolesAllowed`, cần chuyển sang `jakarta.annotation.security.RolesAllowed` theo dependency đã hỗ trợ. Không cho rằng compile thành công của một thư viện legacy đảm bảo annotation đó được Spring Security phiên bản mới nhận diện.

### Reactive/Servlet khác nhau

Ứng dụng WebFlux dùng `@EnableReactiveMethodSecurity`, `Mono`/`Flux` và Reactor Context; ứng dụng Servlet dùng `@EnableMethodSecurity` và proxy method thông thường. Không bê nguyên ví dụ `@SpringJUnitConfig` với method đồng bộ sang reactive và coi như đã kiểm chứng authorization thực hiện khi subscribe. Với reactive, thêm `StepVerifier` và test propagation của `ReactiveSecurityContextHolder`.

## 9. Ma trận regression cần chạy trên codebase thật

Ma trận nên được viết thành test và chạy cùng một bộ fixture trên **version trước** lẫn **version sau**:

| Ca | Authority gốc | Rule cần kiểm | Kỳ vọng |
| --- | --- | --- | --- |
| 1. Role trực tiếp | `ROLE_USER` | `hasRole('USER')` | ALLOW |
| 2. Kế thừa một cấp | `ROLE_MANAGER` | `hasRole('USER')` | ALLOW nếu đã cấu hình hierarchy |
| 3. Kế thừa bắc cầu | `ROLE_ADMIN` | `hasRole('USER')` | ALLOW nếu hierarchy đầy đủ |
| 4. Không suy ngược | `ROLE_USER` | `hasRole('ADMIN')` | DENY |
| 5. Sai prefix | `ADMIN` | `hasRole('ADMIN')` với prefix `ROLE_` | DENY |
| 6. Prefix riêng | `APP_ADMIN` | `hasRole('ADMIN')` với `APP_` | ALLOW |
| 7. Literal authority | `invoice:read` | `hasAuthority('invoice:read')` | ALLOW |
| 8. Role không tự có permission | `ROLE_ADMIN` | `hasAuthority('invoice:read')` | DENY nếu hierarchy/policy không cấp |
| 9. `@Secured` | `ROLE_USER` | `@Secured("ROLE_USER")` | ALLOW nếu enabled |
| 10. `@Secured` âm tính | Không có `ROLE_USER` | Cùng method | DENY nếu enabled |
| 11. JSR-250 | `ROLE_USER` | `@RolesAllowed("USER")` | ALLOW nếu enabled và prefix đúng |
| 12. JSR-250 âm tính | Không có `ROLE_USER` | Cùng method | DENY nếu enabled |
| 13. Pre/post mặc định | User không có quyền | `@PreAuthorize(...)` | DENY nếu `prePostEnabled` |
| 14. Method không annotation | User bất kỳ | Không có method gate | Phải có boundary guard khác nếu nhạy cảm |
| 15. Class/method khác nhau | Role khác nhau | Annotation trên class và method | Kiểm precedence theo rule dự kiến |
| 16. Proxy bypass | Caller qua `this.method()` | Protected method nội bộ | Phải phát hiện rủi ro và sửa call path |
| 17. API HTTP | User thiếu quyền | `SecurityFilterChain` | `401`/`403` phù hợp, không phát dữ liệu |
| 18. Object/tenant | User có role nhưng sai owner | Service/domain policy | DENY độc lập với hierarchy |

Các expected phụ thuộc **chính sách doanh nghiệp** và cấu hình. Bảng đặt ra những câu hỏi cần test; không được auto-convert tất cả thành ALLOW để đạt số lượng test xanh.

Ngoài các case thông thường, cần kiểm:

- `@WithMockUser(roles="ADMIN")` vs `@WithMockUser(authorities="ROLE_ADMIN")` vs `@WithMockUser(authorities="ADMIN")`.
- Prefix là một chuỗi chính xác, phân biệt chữ hoa/thường, không tự sửa token.
- Hai annotation áp dụng ở class/interface có bị xung đột, startup có lỗi không?
- Method final/private, self-invocation, interface proxy vs class proxy; test gọi **bean thực** thay vì `new`.
- Tham số Spring Expression Language (`#p0`, `#id`) có còn resolve đúng khi đổi compiler flag hoặc version?
- Các rule HTTP và method có nhất quán không? Role hierarchy ở HTTP không nên bị mặc định giống method nếu chưa test.
- Cache quyền, JWT authority mapping, custom authentication converter, groups từ IdP và OAuth2 scope mapping (thường mang `SCOPE_`) có bị ảnh hưởng không?

## 10. Quy trình nâng phiên bản có kiểm soát

**Bước 1 — Chụp baseline:** khóa Maven/Gradle dependencies và build hiện tại; xuất báo cáo version, cấu hình, nhóm annotations, hierarchy và raw authorities từ fixture kiểm thử. Lưu baseline decision matrix.

**Bước 2 — Khai báo semantic diff:** trước khi sửa, mô tả chính xác những rule dự kiến thay đổi. Ví dụ “`@PreAuthorize` trước chưa bật, sau bật” là thay đổi policy cần người sở hữu nghiệp vụ phê duyệt. Không gộp thay đổi security policy ngoài ý muốn vào một PR chỉ ghi “upgrade dependency”.

**Bước 3 — Cập nhật API có chủ đích:** chuyển `@EnableGlobalMethodSecurity` sang `@EnableMethodSecurity` và tường minh các flags. Chuyển JSR import sang Jakarta nếu nâng Boot 3. Kiểm tra role hierarchy bean/handler/factory đúng version. Với Spring Security 7.x, rà soát `AuthorizationManagerFactory` và các API tùy biến prefix đã deprecate; không dùng một snippet 6.5 như đáp án mặc định của 7.x.

**Bước 4 — Chạy test ở method và HTTP:** bảo vệ bản ghi và service thật, test allow lẫn deny, có trường hợp ADMIN chỉ mang `ROLE_ADMIN` để chứng minh hierarchy. Nếu JUnit pass chỉ vì đã gán sẵn `ROLE_USER` thì test chưa chứng minh inheritance.

**Bước 5 — So sánh quyết định:** ghi tập request/fixture (không chứa bí mật), chạy old và new trong môi trường kiểm thử, xuất `before/after` theo principal/action/resource. Với mọi `DENY -> ALLOW`, kiểm tra nguy cơ mở quyền; với `ALLOW -> DENY`, xác nhận không chặn nghiệp vụ hợp lệ.

**Bước 6 — Canary và quan sát:** triển khai theo cohort ổn định, giám sát `403` theo route/role/cohort, lỗi nghiệp vụ, latency của authorization, event `AuthorizationDeniedEvent` khi phù hợp và policy/config version thực thi. Không log raw JWT hoặc dữ liệu nhạy cảm.

**Bước 7 — Rollback nếu lệch:** quay lại artifact/config build tương thích đã được phê duyệt. Không chỉ revert dependency rồi để lại prefix/hierarchy mapping của bản mới. Xác minh toàn cụm và chạy lại ma trận; nếu bản cũ chứa lỗ hổng đã phát hiện thì chọn hotfix/deny-safe policy thay vì tự động mở lại quyền nguy hiểm.

### “Definition of Done” cho nâng cấp authorization

- Có phiên bản target chính xác, dependency lock/BOM và migration notes.
- Đã ghi rõ annotation nào mặc định bật/tắt **trước và sau**.
- RoleHierarchy hoạt động bắc cầu với authority gốc duy nhất, kể cả HTTP/method nếu dùng cả hai.
- Prefix role nhất quán giữa IdP/JWT mapper, `@WithMockUser`, `hasRole`, `@Secured`, `@RolesAllowed` và custom managers.
- Negative tests bằng Spring proxy thực đều PASS, cả owner/tenant và anonymous.
- Không xuất hiện `DENY -> ALLOW` ngoài thay đổi đã duyệt; lỗi 403 hợp lệ được phân biệt với regression.
- Đã lưu kết quả canary và có rollback plan được kiểm chứng.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng sau nâng | Nguyên nhân có thể | Hướng tìm và sửa |
| --- | --- | --- |
| Admin bị 403 ở `hasRole('USER')` | Không nối hierarchy vào handler/manager | Test `ROLE_ADMIN` thuần, kiểm `RoleHierarchy` và evaluator đúng version |
| `hasRole('ADMIN')` từ chối `ADMIN` | Prefix mặc định `ROLE_` | Kiểm raw authorities và thống nhất mapper/prefix |
| Custom prefix hoạt động ở method nhưng lỗi ở HTTP | HTTP authorization manager cấu hình khác | Test riêng request-level, dùng factory/custom manager đúng version |
| `@Secured` đột nhiên không còn chặn | Quên `securedEnabled=true` | Bật tường minh và có test thiếu quyền phải bị deny |
| `@RolesAllowed` không còn chặn | Quên `jsr250Enabled=true` hoặc import namespace cũ | Bật JSR-250 và dùng Jakarta đúng Boot version |
| `@PreAuthorize` bất ngờ chặn request | `@EnableMethodSecurity` bật pre/post mặc định | Xác nhận đây là thay đổi policy cố ý; nếu giữ behavior cũ, `prePostEnabled=false` |
| Có nhiều annotation và quyền bị siết | Nhiều interceptor nối tiếp | Kiểm AND semantics và annotation class/method/interface |
| Test pass dù annotation bị tắt | Chỉ kiểm user đủ quyền | Thêm test negative với user thiếu quyền |
| Method có annotation nhưng không bị chặn | Gọi `new`, self-invocation, proxy/final method | Test Spring bean injected qua proxy, tách service nếu cần |
| Prefix custom làm `@WithMockUser(roles=...)` thất bại | `roles` giả lập thường tạo `ROLE_*` | Dùng `authorities` tương ứng actual prefix |
| Nâng major version code compile lỗi | API/package thay đổi, deprecations | Đọc migration guide chính xác; sửa nguồn cấu hình theo target |
| User có role hợp lệ đọc được object người khác | Chỉ kiểm role, thiếu object policy | Giữ owner/tenant checks độc lập với hierarchy |

## 12. Checklist đánh giá cuối bài

- [ ] Biết role trong expression khác chuỗi authority trong `Authentication`.
- [ ] Phân biệt `hasRole`/`hasAuthority` và hiểu mặc định `ROLE_`.
- [ ] Biết `ROLE_ADMIN > ROLE_MANAGER > ROLE_USER` là quan hệ bắc cầu, không phải sửa authorities gốc.
- [ ] Đã kiểm tra role hierarchy trên **từng loại interceptor thực sự dùng**.
- [ ] Nắm `prePostEnabled=true`, `securedEnabled=false`, `jsr250Enabled=false` của `@EnableMethodSecurity`.
- [ ] Biết migration từ `@EnableGlobalMethodSecurity` có thể làm thay đổi group annotation được bật.
- [ ] Biết nhập `jakarta.annotation.security.RolesAllowed` cho Boot 3, không bê nguyên `javax`.
- [ ] Đã test `@WithMockUser(roles=...)` và `authorities=...` riêng, có cả negative test.
- [ ] Tất cả test bảo vệ method gọi bean qua Spring proxy.
- [ ] Đã chạy comparison matrix trước/sau nâng version, gồm HTTP, service, owner/tenant.
- [ ] Mọi thay đổi ALLOW/DENY được review và có plan canary/rollback.

## Tài liệu chính thức

- [Spring Security 6.5 — Authorization Architecture: Role Prefix & Hierarchy](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 7.x — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 7.x — Method Security & migration](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — API GrantedAuthorityDefaults](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/core/GrantedAuthorityDefaults.html)

**Bài tập mở rộng:** chuyển project mẫu sang policy `APP_ADMIN > APP_MANAGER > APP_USER` với prefix `APP_` và test cùng một ma trận trên phiên bản Spring Security đang dùng. Sau đó chủ động thử một cấu hình thiếu `jsr250Enabled` và một cấu hình thiếu hierarchy handler để thấy test âm tính hoặc kế thừa thất bại. Báo cáo chính xác những ALLOW/DENY thay đổi, chỉ rõ nguyên nhân thuộc authority mapping, prefix, hierarchy hay annotation enablement.