# @WithSecurityContext để tạo danh tính kiểm thử riêng trong Spring Security Servlet

## 1. Vì sao @WithMockUser không phải lúc nào cũng đủ?

Khi kiểm thử Spring Security, ta thường muốn chạy một `@PreAuthorize` hoặc gửi request `MockMvc` với người dùng đã đăng nhập. `@WithMockUser` rất thuận tiện:

~~~java
@Test
@WithMockUser(username = "alice", roles = "READER")
void readerCanRead() {
    // Kiểm thử logic được bảo vệ bằng hasRole("READER").
}
~~~

Tuy nhiên, trong ứng dụng thực tế, principal có thể không chỉ là một username:

- **Local account ID**: `user-100`, ổn định ngay cả khi username/email thay đổi.
- **Tenant / workspace ID**: `tenant-a`, cần để chặn đọc chéo dữ liệu.
- **Roles và permissions**: `ROLE_READER`, `ROLE_MANAGER`, `PROJECT_EXPORT`.
- **Trạng thái và ngữ cảnh nghiệp vụ**: thông tin gắn với session/identity sau khi xác thực.
- **Principal class riêng**: ví dụ `TenantPrincipal` được ứng dụng dùng trong `@PreAuthorize`, service hoặc `@AuthenticationPrincipal`.

`@WithMockUser` mặc định tạo principal kiểu `org.springframework.security.core.userdetails.User`. Nếu policy của ứng dụng đòi hỏi một principal tùy biến có `tenantId`, tên và role thôi không đủ. Việc ép kiểu principal sai có thể dẫn tới `ClassCastException`; hoặc một policy viết đúng sẽ từ chối vì principal không có dữ liệu cần thiết.

`@WithSecurityContext` của **spring-security-test** cho phép ta khai báo một annotation **chỉ dùng trong test** và một `WithSecurityContextFactory` để xây chính xác `SecurityContext`, `Authentication`, principal và authorities phục vụ kịch bản kiểm thử.

Mục tiêu bài này: tạo `@WithMockTenantUser`, kiểm thử trực tiếp service có `@PreAuthorize` và kiểm thử `MockMvc`; hiểu cách listener gắn/xóa context, thời điểm thiết lập context, ranh giới của test giả lập và các lỗi bảo mật thường gặp.

**Phạm vi:** Spring Security 6, Spring Boot 3.3.5, Java 17, **Servlet** và JUnit 5. Đây là cơ chế **test fixture**, không phải authentication provider trong production.

## 2. Tách đúng ba thứ: SecurityContext, Authentication và principal

Spring Security phân biệt:

| Thành phần | Vai trò | API thường gặp |
| --- | --- | --- |
| `SecurityContextHolder` | Cung cấp context cho thread/strategy hiện tại | `SecurityContextHolder.getContext()` |
| `SecurityContext` | Giữ `Authentication` của security context | `getAuthentication()`, `setAuthentication()` |
| `Authentication` | Đại diện danh tính, trạng thái authenticated, authorities và credentials | `getPrincipal()`, `getAuthorities()`, `isAuthenticated()` |
| Principal | Mô hình người dùng đã xác thực theo ứng dụng | `getName()`, `tenantId()`, `accountId()` |
| `GrantedAuthority` | Quyền mà Spring Security dùng cho `hasRole`, `hasAuthority` | `getAuthority()` |

Trong ứng dụng thật, authentication filter và `AuthenticationManager` tạo `Authentication` sau khi xác minh mật khẩu, session hoặc token. Với test `@WithSecurityContext`, ta **khởi tạo sẵn một `Authentication` đáng tin trong phạm vi test**, bỏ qua phần xác minh credential để chỉ tập trung vào authorization/business behavior.

Luồng kiểm thử:

~~~text
JUnit 5 + Spring TestContext
        |
        v
WithSecurityContextTestExecutionListener
        |
        v
Phát hiện @WithMockTenantUser trên method/class
        |
        v
WithMockTenantUserFactory.createSecurityContext(annotation)
        |
        +--> Tạo TenantPrincipal(username, accountId, tenantId)
        +--> Tạo ROLE_READER hoặc các authorities phù hợp
        +--> Tạo Authentication đã authenticated
        +--> Đặt Authentication vào SecurityContext rỗng
        |
        v
SecurityContextHolder cho luồng test hiện tại
        |
        +--> Gọi trực tiếp service proxy có @PreAuthorize
        |
        +--> MockMvc đã tích hợp Spring Security filter chain
        |
        v
Spring Test listener dọn context sau test
~~~

**Không gọi `SecurityContextHolder.setContext(...)` trong factory nếu không cần**: hợp đồng factory là **trả về** một `SecurityContext` mới; test listener sẽ xử lý cài đặt và dọn dẹp. Điều này giảm nguy cơ context bị rò sang test khác.

Test annotation không làm một JWT hợp lệ xuất hiện, không chạy OAuth2 authorization code exchange, không kiểm password và không tự mở session production. Nó chỉ tạo **điều kiện đầu vào có kiểm soát** để kiểm policy.

## 3. @WithSecurityContext và factory hoạt động như thế nào?

Các API thuộc test dependency:

~~~java
import org.springframework.security.test.context.support.WithSecurityContext;
import org.springframework.security.test.context.support.WithSecurityContextFactory;
import org.springframework.security.test.context.support.TestExecutionEvent;
~~~

Có thể tạo annotation meta-annotated bằng `@WithSecurityContext`:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = MyFactory.class)
public @interface WithMyIdentity {
    String userId() default "user-100";
}
~~~

Đây chỉ là **mảnh minh họa cú pháp**, vì `MyFactory` và các imports chưa được khai báo. Ví dụ hoàn chỉnh ở mục 7 có tên `WithMockTenantUser`.

`WithSecurityContextFactory<A>` có một phương thức cốt lõi:

~~~java
SecurityContext createSecurityContext(A annotation);
~~~

Factory nhận **instance annotation của test đang chạy**. Từ thuộc tính của annotation, factory có thể:

1. Kiểm tra những giá trị fixture hợp lệ.
2. Dựng principal và `GrantedAuthority` đúng như ứng dụng mong đợi.
3. Tạo `SecurityContext` mới.
4. Gán một `Authentication` đã authenticated.
5. Trả context cho Spring Security TestExecutionListener.

Ví dụ thiết lập authentication bằng constructor ba tham số:

~~~java
Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                principal,
                "N/A",
                authorities);

SecurityContext context =
        SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
return context;
~~~

`UsernamePasswordAuthenticationToken` với constructor **ba tham số** tạo authentication đã được đánh dấu authenticated, vì caller trong **test** đã xác định principal và quyền. Constructor hai tham số `(principal, credentials)` tạo token **chưa authenticated**, dùng cho luồng request xác thực ban đầu. Hai constructor không có cùng ngữ nghĩa.

Cụm `"N/A"` chỉ là placeholder của test, **không phải mật khẩu thật**. Không đưa credential production vào fixture hoặc log. Nếu ứng dụng sử dụng custom `Authentication` (ví dụ lớp đặc thù gắn claim), factory có thể tạo đúng kiểu đó thay vì `UsernamePasswordAuthenticationToken`; nhưng phải giữ các quy tắc `getPrincipal`, `getAuthorities`, `isAuthenticated` mà method security dựa vào.

## 4. Khi nào chọn @WithSecurityContext thay vì công cụ có sẵn?

| Cách kiểm thử | Danh tính được tạo | Nên dùng khi |
| --- | --- | --- |
| `@WithMockUser` | UserDetails mặc định và role/authority do test chỉ định | Policy chỉ phụ thuộc username, roles, authorities chuẩn |
| `@WithUserDetails` | Đọc UserDetails qua `UserDetailsService` của application context | Cần test principal như `UserDetailsService` trả về và muốn dữ liệu fixture từ service |
| `@WithSecurityContext` | **Bất kỳ SecurityContext/Authentication/principal** do factory tạo | Custom principal, tenant, account ID, permission claims, composite identity, nhiều biến thể cần tái sử dụng |
| `mockMvc.perform(...with(user(...)))` | Principal áp dụng cho **một request** | Cần biến thể danh tính khác nhau trong cùng test/request |
| `mockMvc.perform(...with(authentication(...)))` | Authentication áp dụng cho request cụ thể | Muốn kiểm request-level với authentication tùy biến |
| Full authentication integration test | Đăng nhập thật/mô phỏng IdP đủ bước, token/credential được xử lý | Xác thực mật khẩu, JWT validation, session, OAuth2/OIDC callback, failure paths |

`@WithSecurityContext` giúp test ngắn, dễ đọc và **không lặp code xây context ở mỗi phương thức**. Tuy nhiên nó không phù hợp khi mục tiêu test chính là chứng minh một login provider xác thực đúng: khi ấy cần integration test dành cho authentication.

Sự khác biệt quan trọng: `@WithUserDetails` phụ thuộc bean `UserDetailsService` và dữ liệu người dùng có sẵn; `@WithSecurityContext` có thể tạo principal thử nghiệm hoàn toàn **từ annotation**, không cần kết nối database hoặc directory bên ngoài.

Đối với **`@PreAuthorize`**, hãy kiểm trực tiếp method được Spring proxy quản lý. Với **MockMvc**, kiểm response/status của request qua security chain và MVC. Cả hai cấp kiểm thử bổ sung cho nhau.

## 5. Thiết kế fixture: chỉ mô tả điều cần test

Giả sử một `ProjectService` cho phép đọc project nếu:

- Người dùng đã authenticated.
- Có authority `ROLE_READER`.
- `tenantId` trong principal bằng `tenantId` của project được yêu cầu.

Một custom principal test sẽ có ba trường:

~~~java
public record TenantPrincipal(
        String username,
        String accountId,
        String tenantId
) implements Principal, Serializable {
    @Override
    public String getName() {
        return username;
    }
}
~~~

Đây là **mảnh mã**; ở mục 7 record này sẽ nằm trong class ứng dụng hoàn chỉnh, có imports và các bean cần thiết.

Vì Spring Security diễn giải `hasRole('READER')` thành so khớp authority **`ROLE_READER`**, annotation sẽ cho phép khai báo `roles = {"READER"}` và factory tự thêm prefix `ROLE_`. Không truyền `"ROLE_READER"` vào một API vốn đã tự thêm prefix.

Một annotation tốt nên có:

- Giá trị mặc định dễ hiểu cho test thông thường.
- `username`, `accountId`, `tenantId` riêng, không lấy email làm local ID.
- `roles` có thể là mảng rỗng để thử failure path.
- Factory chỉ cấp những quyền được ghi rõ trong fixture.
- Kiểm tra input của annotation để lỗi test xuất hiện **sớm** nếu một tenant hoặc role bị viết sai.

Không nên tạo annotation có hàng chục thuộc tính không liên quan, không tự gọi server hoặc DB trong factory nếu có thể dùng dữ liệu thuần. Với policy phức tạp, các fixture hướng domain cụ thể (`@WithMockTenantUser`, `@WithMockServiceAccount`) thường rõ hơn một annotation siêu tổng quát.

## 6. Cấu trúc demo Maven: Java 17 + Spring Boot 3.3.5

Ta tạo ứng dụng Spring MVC có một endpoint GET để đọc project và một endpoint POST minh họa CSRF. `ProjectService` được bảo vệ bởi method security:

~~~java
@PreAuthorize(
    "hasRole('READER') and " +
    "@tenantAccess.sameTenant(authentication, #p0)")
~~~

`#p0` là tham số đầu tiên của method, không phụ thuộc việc tên tham số Java có được giữ lại qua `-parameters` hay không. `@tenantAccess` tham chiếu một bean Spring có tên `tenantAccess`, không phải một biến Java trong controller.

Cấu trúc:

~~~text
tenant-security-test-demo/
├── pom.xml
├── src/main/java/example/securitytest/SecurityTestApplication.java
├── src/test/java/example/securitytest/WithMockTenantUser.java
├── src/test/java/example/securitytest/WithMockTenantUserFactory.java
└── src/test/java/example/securitytest/TenantSecurityTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>tenant-security-test-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chú ý `spring-security-test` có **`scope=test`**. Custom annotation và factory đặt ở `src/test/java` để chúng **không** trở thành thành phần authentication của hệ thống production.

## 7. Ví dụ mã đầy đủ: ứng dụng và danh tính mock riêng

### 7.1. Ứng dụng cần bảo vệ

**src/main/java/example/securitytest/SecurityTestApplication.java**:

~~~java
package example.securitytest;

import java.io.Serializable;
import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Dữ liệu local demo cho HTTP Basic. Không dùng {noop} production.
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password("{noop}demo-pass")
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/projects/**")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean("tenantAccess")
    TenantAccess tenantAccess() {
        return new TenantAccess();
    }

    @Bean
    ProjectService projectService() {
        return new ProjectService();
    }

    // Domain principal mà ứng dụng thực tế có thể đưa vào Authentication.
    public record TenantPrincipal(
            String username,
            String accountId,
            String tenantId
    ) implements Principal, Serializable {
        @Override
        public String getName() {
            return username;
        }
    }

    public record Project(String tenantId, String title) {}

    public static class TenantAccess {

        public boolean sameTenant(
                Authentication authentication, String tenantId) {
            return authentication != null
                    && authentication.isAuthenticated()
                    && authentication.getPrincipal()
                            instanceof TenantPrincipal principal
                    && principal.tenantId().equals(tenantId);
        }
    }

    public static class ProjectService {

        @PreAuthorize(
                "hasRole('READER') and " +
                "@tenantAccess.sameTenant(authentication, #p0)")
        public Project readProject(String tenantId) {
            return new Project(tenantId, "Internal project");
        }
    }

    @RestController
    public static class ProjectController {
        private final ProjectService service;

        public ProjectController(ProjectService service) {
            this.service = service;
        }

        @GetMapping("/api/projects/{tenantId}")
        public Project getProject(@PathVariable String tenantId) {
            return service.readProject(tenantId);
        }

        @PostMapping("/api/projects/{tenantId}/confirm")
        public ResponseEntity<Void> confirmProject(
                @PathVariable String tenantId) {
            // Minh họa POST chịu CSRF và cùng policy dịch vụ.
            service.readProject(tenantId);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Các điều kiện bảo vệ quan trọng:**

1. `@EnableMethodSecurity` bật `@PreAuthorize` trên Spring-managed service; không được bỏ annotation này rồi nghĩ `@PreAuthorize` đã tự chạy.
2. `ProjectService` là bean do Spring quản lý, được gọi qua controller hoặc inject vào test. Gọi `new ProjectService()` ở ngoài Spring hoặc gọi `this.readProject(...)` từ một phương thức trong cùng instance có thể bỏ qua AOP proxy và **không** thực thi method security.
3. Rule URL yêu cầu `authenticated()`, còn method rule yêu cầu **role + tenant**. HTTP Basic user `demo` có role READER nhưng principal là `UserDetails` mặc định, **không** phải `TenantPrincipal`: policy cố ý từ chối vì thiếu ngữ cảnh tenant.
4. `TenantAccess.sameTenant` dùng `instanceof TenantPrincipal` để fail closed. **Không cast mù** hoặc bỏ tenant check chỉ vì request đã authenticated.
5. `#p0` bảo đảm biểu thức tham chiếu tới tenantId truyền cho service, kể cả khi metadata tên tham số bị lược bỏ. Các biểu thức `@PreAuthorize` cần được kiểm thử với quyền/tenant âm tính, không chỉ happy path.
6. POST trong ví dụ có URL `authenticated()` nhưng vẫn chịu **CsrfFilter** theo mặc định vì là unsafe HTTP method. Tạo principal bằng `@WithSecurityContext` **không** tự tạo CSRF token hợp lệ cho một request `MockMvc`.
7. `{noop}` chỉ dùng cho fixture HTTP Basic, không thích hợp lưu password production. Nguồn local identity trong thực tế phải qua authentication provider, không tin dữ liệu `tenantId` do client tự gửi trong form hoặc header.

### 7.2. Custom annotation @WithMockTenantUser

**src/test/java/example/securitytest/WithMockTenantUser.java**:

~~~java
package example.securitytest;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.test.context.support.TestExecutionEvent;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@Inherited
@WithSecurityContext(
        factory = WithMockTenantUserFactory.class,
        setupBefore = TestExecutionEvent.TEST_METHOD
)
public @interface WithMockTenantUser {

    String username() default "alice";

    String accountId() default "user-100";

    String tenantId() default "tenant-a";

    String[] roles() default {"READER"};
}
~~~

`@Retention(RUNTIME)` giúp test listener đọc annotation bằng reflection. `@Target(METHOD, TYPE)` cho phép dùng trên test method hoặc cả test class. `@Inherited` hỗ trợ một số trường hợp thừa kế annotation ở cấp class; nó **không** biến mọi annotation trên interface hoặc method của superclass thành tự động kế thừa theo mọi quy tắc Java.

`setupBefore = TEST_METHOD` là thời điểm mặc định: Spring Security TestExecutionListener chuẩn bị context **trước** các callback `@BeforeEach` của JUnit 5. Nếu muốn context được tạo sau `@BeforeEach`, cân nhắc `TestExecutionEvent.TEST_EXECUTION` (phần 10). Chọn theo mục đích test.

Trong ví dụ ta khai báo roles không có prefix `ROLE_`. Factory sẽ tạo `SimpleGrantedAuthority("ROLE_" + role)`. Nếu test muốn quyền không phải role, nên thêm thuộc tính `authorities()` riêng và ánh xạ chính xác; **không** đổi ý nghĩa `roles` một cách âm thầm.

### 7.3. WithSecurityContextFactory tạo principal và Authentication

**src/test/java/example/securitytest/WithMockTenantUserFactory.java**:

~~~java
package example.securitytest;

import java.util.Arrays;
import java.util.Collection;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithMockTenantUserFactory
        implements WithSecurityContextFactory<WithMockTenantUser> {

    @Override
    public SecurityContext createSecurityContext(
            WithMockTenantUser annotation) {

        if (annotation.username().isBlank()
                || annotation.accountId().isBlank()
                || annotation.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                    "Mock identity fields must not be blank");
        }

        Collection<GrantedAuthority> authorities = Arrays.stream(
                annotation.roles())
                .map(role -> {
                    if (role == null || role.isBlank()
                            || role.startsWith("ROLE_")) {
                        throw new IllegalArgumentException(
                                "roles must be names without ROLE_ prefix");
                    }
                    return (GrantedAuthority)
                            new SimpleGrantedAuthority("ROLE_" + role);
                })
                .toList();

        var principal =
                new SecurityTestApplication.TenantPrincipal(
                        annotation.username(),
                        annotation.accountId(),
                        annotation.tenantId());

        var authentication = new UsernamePasswordAuthenticationToken(
                principal, "N/A", authorities);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Ở đây `Collection<GrantedAuthority>` chấp nhận một tập quyền giả lập được tạo từ roles. `Arrays.stream(...).map(...).toList()` là cú pháp phù hợp Java 17.

Các điểm cần hiểu:

- `annotation.roles()` chính là input của mỗi test; không truy vấn dữ liệu production hay cấp quyền ngoài ý định của test.
- `TenantPrincipal` dùng **mô hình mà application code mong đợi**; `accountId` và `tenantId` là dữ liệu fixture độc lập với username.
- `UsernamePasswordAuthenticationToken(principal, "N/A", authorities)` tạo authenticated token trong phạm vi test.
- `SecurityContextHolder.createEmptyContext()` tạo context mới, không tái sử dụng context cũ. Factory **trả context**, không cần tự set global holder.
- `roles = {}` tạo tập authorities rỗng; test phải bị từ chối bởi `hasRole("READER")`.
- Factory chỉ kiểm dữ liệu fixture và tạo context; không gửi HTTP, không gọi password encoder, không tạo cookie hoặc session thực.

Nếu principal thực tế của dự án dùng một kiểu `Authentication` riêng (ví dụ chứa claims nội bộ đã được xác minh), có thể thay dòng tạo `UsernamePasswordAuthenticationToken` bằng đúng class đó. Trường hợp này vẫn phải đảm bảo `getAuthorities`, `isAuthenticated` và `getPrincipal` có ngữ nghĩa nhất quán.

**Đừng copy annotation/factory này vào `src/main/java` rồi để request production tự chọn role/tenant.** Trong test, annotation đáng tin vì người viết test kiểm soát nó. Trong runtime, identity và role phải đến từ authentication provider/identity service có validation.

### 7.4. Test trên MockMvc và method security

**src/test/java/example/securitytest/TenantSecurityTests.java**:

~~~java
package example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantSecurityTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    SecurityTestApplication.ProjectService projectService;

    @Test
    @WithMockTenantUser(
            username = "alice",
            accountId = "user-100",
            tenantId = "tenant-a",
            roles = {"READER"})
    void matchingTenantAndRoleCanRead() throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenantId").value("tenant-a"))
                .andExpect(jsonPath("$.title").value("Internal project"));
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a")
    void otherTenantIsForbiddenEvenWithReaderRole()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-b"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a", roles = {})
    void missingRoleIsForbiddenEvenWithMatchingTenant()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void defaultMockUserCannotPretendToHaveTenantContext()
            throws Exception {
        mvc.perform(get("/api/projects/tenant-a"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a", roles = {"READER"})
    void serviceProxyEnforcesTenantWithoutHttp() {
        var allowed = projectService.readProject("tenant-a");
        assertThat(allowed.tenantId()).isEqualTo("tenant-a");

        assertThatThrownBy(
                () -> projectService.readProject("tenant-b"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockTenantUser(tenantId = "tenant-a")
    void postRequiresCsrfIndependentlyOfMockIdentity()
            throws Exception {
        mvc.perform(post("/api/projects/tenant-a/confirm"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/projects/tenant-a/confirm")
                        .with(csrf()))
                .andExpect(status().isNoContent());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kết quả mong đợi** khi dùng nguyên cấu trúc ví dụ:

| Test | Mục tiêu | Kỳ vọng |
| --- | --- | --- |
| `matchingTenantAndRoleCanRead` | Principal riêng đúng tenant và role | HTTP 200, JSON đúng |
| `otherTenantIsForbiddenEvenWithReaderRole` | Đúng role nhưng khác tenant | HTTP 403 |
| `missingRoleIsForbiddenEvenWithMatchingTenant` | Đúng tenant nhưng thiếu `ROLE_READER` | HTTP 403 |
| `anonymousRequestRequiresAuthentication` | Không có principal | HTTP 401 do HTTP Basic |
| `defaultMockUserCannotPretendToHaveTenantContext` | Principal mặc định không chứa tenant | HTTP 403 |
| `serviceProxyEnforcesTenantWithoutHttp` | Method security chạy khi gọi bean Spring | Kết quả hợp lệ; gọi tenant khác ném `AccessDeniedException` |
| `postRequiresCsrfIndependentlyOfMockIdentity` | Authenticated không miễn trừ CSRF | POST thiếu CSRF 403; có CSRF 204 |

Các test này chứng minh **principal và quyền trong context ảnh hưởng đến authorization**. Chúng **không chứng minh** HTTP Basic password thực sự được xác minh trong kịch bản annotation, vì `@WithMockTenantUser` bỏ qua authentication entry point. Bổ sung integration tests đăng nhập thật khi cần kiểm password, JWT, OAuth2/OIDC hoặc session.

## 8. Cơ chế test listener, SpringExtension và thời gian tạo context

`@WithSecurityContext` chỉ hoạt động khi môi trường kiểm thử có hỗ trợ Spring TestContext và Spring Security TestExecutionListener. Với `@SpringBootTest`, Spring Boot tích hợp JUnit 5/SpringExtension và listener thích hợp. Nếu dùng unit test thuần `new ProjectService()` không có Spring context, không nên giả định method security hoặc `@WithSecurityContext` sẽ tự hoạt động.

### 8.1. TEST_METHOD và TEST_EXECUTION

Spring Security hỗ trợ `TestExecutionEvent` cho `@WithSecurityContext`:

| Giá trị | Thời điểm set SecurityContext | Khi nào hữu ích |
| --- | --- | --- |
| `TEST_METHOD` (mặc định) | Trước giai đoạn chuẩn bị phương thức test, bao gồm `@BeforeEach` của JUnit | Muốn `@BeforeEach` truy cập authentication |
| `TEST_EXECUTION` | Gần ngay trước khi chạy nội dung `@Test`, **sau** `@BeforeEach` | Muốn setup ở `@BeforeEach` không bị ảnh hưởng bởi identity mock |

Để sử dụng TEST_EXECUTION, đổi meta-annotation (mảnh minh họa, không thay file example khi chưa quyết định):

~~~java
@WithSecurityContext(
    factory = WithMockTenantUserFactory.class,
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

Nếu một `@BeforeEach` gọi service cần authentication, dùng `TEST_EXECUTION` có thể khiến `@BeforeEach` chưa có principal. Đây là lỗi timing, không phải lỗi `@PreAuthorize`.

### 8.2. Context nằm ở đâu và được dọn khi nào?

Theo mặc định, `SecurityContextHolder` dùng chiến lược gắn context với thread hiện tại. Spring Security TestExecutionListener cài context cho test và dọn sau test. Không cần tự `clearContext()` trong mỗi test khi đang dùng lifecycle chuẩn.

Tuy nhiên, `@Async`, threads tự tạo, scheduled jobs hoặc reactive boundaries **không mặc định kế thừa context của thread test**. Nếu cần kiểm propagation, phải dùng cơ chế propagation được Spring Security hỗ trợ (ví dụ `DelegatingSecurityContextRunnable` hoặc các wrapper executor thích hợp) và viết test riêng. Đừng bật `MODE_INHERITABLETHREADLOCAL` trên toàn JVM chỉ để một test qua, vì có nguy cơ rò context giữa tác vụ.

**Chạy test song song:** dùng context mặc định giúp hạn chế chia sẻ giữa thread nhưng không bảo đảm an toàn nếu fixture khác dùng singleton mutable state, static field, user cache hoặc session store toàn cục. Tách test data, tránh global `Authentication` mutable và dùng resource isolation khi cần.

### 8.3. Annotation ở cấp class và cấp method

Có thể đặt một identity mặc định trên test class:

~~~java
@WithMockTenantUser(
        username = "alice",
        tenantId = "tenant-a",
        roles = {"READER"})
class TenantPolicyTests {

    @Test
    void testWithDefaultIdentity() {
        // Sử dụng identity từ annotation cấp class.
    }

    @Test
    @WithMockTenantUser(
            username = "bob",
            tenantId = "tenant-b",
            roles = {"READER"})
    void testWithOtherIdentity() {
        // Annotation cấp method tùy chỉnh identity cho case này.
    }
}
~~~

Đây là **mảnh minh họa cấu trúc test**, không phải một lớp test đầy đủ có assertion. Khả năng đặt annotation ở class giúp giảm lặp, nhưng test quan trọng nên ghi rõ quyền và tenant để người đọc thấy **điều kiện bảo mật đang được kiểm**.

## 9. Tránh kiểm thử sai khi code phụ thuộc principal tùy biến

### 9.1. Không cast trực tiếp principal mặc định

Mã nguy hiểm:

~~~java
TenantPrincipal principal =
        (TenantPrincipal) authentication.getPrincipal();
~~~

Nếu nhận `UserDetails` mặc định hoặc `String` anonymous principal, phép cast gây `ClassCastException`, dễ biến tình huống từ chối quyền thành HTTP 500. Trừ khi contract ứng dụng luôn bảo đảm type, nên kiểm type trước và từ chối an toàn:

~~~java
if (!(authentication.getPrincipal()
        instanceof TenantPrincipal principal)) {
    throw new AccessDeniedException("Unsupported principal");
}
~~~

Trong ví dụ mục 7, `TenantAccess.sameTenant` kiểm `instanceof` và trả `false`, khiến `@PreAuthorize` từ chối thay vì ném lỗi kiểu dữ liệu. Một kết quả 403 từ test `@WithMockUser` là minh chứng fail closed.

### 9.2. Không tạo quyền vượt quá ý định test

Với test `@WithSecurityContext`, role trong annotation là **điều kiện đầu vào**. Nếu factory luôn gắn `ROLE_ADMIN` cho tiện, mọi test quyền thấp sẽ vô hiệu về mặt kiểm chứng. Nên test cả:

- Principal đúng type, đúng tenant, đủ role.
- Principal đúng type nhưng sai tenant.
- Principal đúng tenant nhưng thiếu role.
- Principal khác type với role tương tự.
- Anonymous.
- Trường hợp nhiều role, authority không có prefix `ROLE_`, tài khoản bị disabled hoặc tenant không tồn tại nếu domain có những khái niệm đó.

Không dùng cùng một test method để chứng minh nhiều quyết định bảo mật khác nhau mà không assert độc lập. Khi đổi role mapping, các test âm tính giúp phát hiện lỗi **privilege escalation**.

### 9.3. Không nhầm accountId với username

Trong một ứng dụng thực, `accountId` bền vững còn username/email có thể thay đổi. Nếu owner của resource là `accountId`, policy nên so sánh với `principal.accountId()`, không so sánh tùy tiện với `Authentication.getName()`. Với multi-tenant, ownership thường gồm **tenant ID + account ID + quyền với resource**. Ví dụ ở mục 7 chỉ kiểm tenant để cô lập một dạng policy; hệ thống thật có thể cần kiểm cả document/project owner và visibility.

### 9.4. Không test trực tiếp đối tượng không được Spring quản lý

Một phương thức có `@PreAuthorize` chỉ được kiểm nếu lời gọi đi qua cơ chế method-security interceptor/proxy thích hợp. Ví dụ:

~~~java
// SAI khi muốn kiểm AOP method security:
ProjectService service = new ProjectService();
service.readProject("tenant-b");

// ĐÚNG: nhận bean từ application context:
@Autowired ProjectService service;
~~~

Nếu code tự gọi nội bộ `this.readProject()` cùng đối tượng, có thể xảy ra **self-invocation**, không đi qua proxy. Viết test thực tế ở boundary nơi controller/bean khác gọi service đã được Spring quản lý.

## 10. Khác biệt giữa test danh tính, test HTTP và test đăng nhập thật

Cùng một endpoint có thể được kiểm thử theo ba mức:

### 10.1. Kiểm tra trực tiếp service

~~~java
@Autowired
SecurityTestApplication.ProjectService projectService;

@Test
@WithMockTenantUser(tenantId = "tenant-a")
void denyOtherTenantAtMethodBoundary() {
    assertThatThrownBy(() ->
            projectService.readProject("tenant-b"))
        .isInstanceOf(AccessDeniedException.class);
}
~~~

Đây là **mảnh minh họa** tương tự test hoàn chỉnh ở mục 7: method-security proxy chạy, không cần HTTP, Servlet dispatcher, filter URL hay CSRF.

### 10.2. Kiểm tra request MVC

~~~java
@Test
@WithMockTenantUser(tenantId = "tenant-a")
void mvcDeniesOtherTenant() throws Exception {
    mvc.perform(get("/api/projects/tenant-b"))
        .andExpect(status().isForbidden());
}
~~~

MockMvc chạy một request qua phần MVC/security filter mà test context cấu hình, trả HTTP response. Nó giúp kiểm cả URL rule, controller routing và method security. Khi Spring Security filter chain không được gắn vào MockMvc, các assertion có thể cho kết quả sai lệch; với `@AutoConfigureMockMvc` + `spring-security-test` theo cấu hình demo, filter được tích hợp. Nếu tự tạo MockMvc thủ công, cần `springSecurity()` configurer.

### 10.3. Kiểm xác thực thật

Muốn chứng minh user nhập password sai sẽ nhận 401 hoặc bearer token sai chữ ký bị từ chối, **không dùng `@WithSecurityContext`** để kết luận. Fixture đã tạo `Authentication` sẵn nên không chạy bước xác thực credential. Dùng integration tests có HTTP client, authentication provider, JWT decoder/IdP test, session/cookies và failure path phù hợp.

Một test MockMvc với `.with(httpBasic("demo", "demo-pass"))` là request gửi Basic credential tới chain, khác với `@WithMockTenantUser`. Trong demo, Basic user `demo` có role READER nhưng không có custom tenant principal nên bị **method security** từ chối; điều đó là một minh chứng rằng role alone không đủ cho chính sách tenant.

### 10.4. Kiểm POST và CSRF

`@WithMockTenantUser` tạo danh tính đã xác thực nhưng không tạo CSRF token. Khi `CsrfFilter` bật, với request thay đổi trạng thái, test cần chủ động cung cấp token:

~~~java
mvc.perform(post("/api/projects/tenant-a/confirm")
            .with(csrf()))
    .andExpect(status().isNoContent());
~~~

Nếu không gắn `with(csrf())`, POST có thể bị chặn 403 **trước** khi controller/method security chạy. Khi debug test bị 403, phải phân biệt lý do CSRF với role/tenant. Đừng tắt CSRF toàn ứng dụng chỉ để test business authorization qua POST.

## 11. Khi cần factory phức tạp hơn: dependency injection và custom Authentication

Một factory có thể phải lấy default tenant hoặc user profile fixture từ một bean. Spring Security Test có hỗ trợ làm việc với Spring test application context khi xây security context factory; tuy nhiên coupling factory với repository thật làm test chậm, khó lặp lại và dễ che các nhánh lỗi. Dùng dependency injection trong factory chỉ khi nó mang lại giá trị rõ rệt.

Ví dụ **mảnh mã** cho principal riêng có authorities tách khỏi roles:

~~~java
Collection<GrantedAuthority> authorities = List.of(
    new SimpleGrantedAuthority("ROLE_READER"),
    new SimpleGrantedAuthority("PROJECT_EXPORT")
);

Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        tenantPrincipal, "N/A", authorities);
~~~

Trong cấu hình `@PreAuthorize`:

~~~java
@PreAuthorize(
    "hasRole('READER') and hasAuthority('PROJECT_EXPORT')")
~~~

`hasRole` gắn tiền tố role theo mặc định; `hasAuthority` so khớp chính xác chuỗi authority. Nếu app dùng permission object phức tạp, có thể xây custom principal/authentication thích hợp, nhưng không vì thế mà gửi JWT giả chưa xác minh vào production handler.

Nếu cần kiểm `Authentication.getDetails()` hoặc request metadata, factory có thể tạo authentication với details phù hợp; nhớ phân biệt **client-provided request data** và **server-verified identity data**. Method-level authorization không nên tin tenantId từ request header mà chưa ràng buộc nó với danh tính đã xác thực.

Khi dùng OAuth2 Login hoặc OIDC, những test helper như `oauth2Login()`/`oidcLogin()` thường phù hợp để mô phỏng principal kiểu OAuth2/OIDC. Nếu mục tiêu là principal **đã được ứng dụng chuyển thành local identity có thêm tenant/roles**, annotation `@WithSecurityContext` vẫn hữu ích. Nhưng nó không kiểm thử việc gọi UserInfo endpoint hay xác minh chữ ký ID token thật.

## 12. Lỗi thường gặp và hướng sửa

| Lỗi | Dấu hiệu | Hướng khắc phục |
| --- | --- | --- |
| Thiếu `spring-security-test` | Không tìm thấy `@WithSecurityContext` hoặc `WithSecurityContextFactory` | Thêm dependency test scope |
| Không chạy Spring TestContext | Annotation không thiết lập authentication | Dùng `@SpringBootTest`, SpringExtension hoặc cấu hình test listener phù hợp |
| Dùng `@WithMockUser` khi policy cần `TenantPrincipal` | 403 hoặc `ClassCastException` | Custom factory tạo đúng principal type |
| Dùng constructor 2 tham số của UsernamePasswordAuthenticationToken | `isAuthenticated()` là false | Trong test fixture sử dụng constructor 3 tham số có authorities |
| Factory gọi `setContext` toàn cục rồi không clear | Test có thể ảnh hưởng lẫn nhau | Trả `SecurityContext` mới; để listener quản lý lifecycle |
| `roles={"ROLE_READER"}` khi factory thêm prefix | Tạo `ROLE_ROLE_READER` hoặc lỗi fixture | Quy ước roles không prefix; authorities dùng chuỗi chính xác |
| Thiếu `@EnableMethodSecurity` | `@PreAuthorize` không được thực thi | Bật method security và gọi Spring bean |
| Gọi `new ProjectService()` | Test quyền sai vẫn chạy thành công | Inject bean đã được Spring proxy quản lý |
| Test chỉ happy path | Không phát hiện lỗi tenant/role check | Viết test âm tính khác tenant, thiếu role, anonymous |
| Test POST chỉ nhận 403 | Không biết do CSRF hay policy | Gắn `with(csrf())` khi test authorization của POST |
| `@WithSecurityContext` bị dùng như test JWT | Test pass dù decoder sai | Viết integration test authentication thật riêng |
| `TEST_EXECUTION` nhưng `@BeforeEach` cần principal | Setup nhận null authentication | Dùng `TEST_METHOD` hoặc dời setup |
| Dữ liệu fixture để ở static mutable field | Test song song không ổn định | Context mới mỗi test, fixture bất biến, cô lập dữ liệu |
| Custom principal tạo quá nhiều quyền | Test che lỗi privilege escalation | Cấp ít quyền nhất, assert các case bị từ chối |
| App check tenant chỉ ở UI | HTTP trực tiếp có thể đọc chéo | Đưa kiểm tenant/ownership vào service/method-security layer |

Đặc biệt với `MockMvc`, nếu `@WithMockTenantUser` tạo đúng principal nhưng request vẫn 401, kiểm integration giữa MockMvc và security filter, security matcher, test listener và rule URL. Nếu request là POST 403, xét CSRF trước; nếu GET 403, xét role/tenant hoặc handler method security.

## 13. Bài tập tự kiểm tra

**Câu 1.** `@WithSecurityContext` khác `@WithMockUser` ở điểm cốt lõi nào?  
**Trả lời:** Có thể tạo **SecurityContext/Authentication/principal tùy biến hoàn toàn** qua factory thay vì sử dụng mock UserDetails mặc định.

**Câu 2.** `WithSecurityContextFactory` nên trả gì?  
**Trả lời:** Một `SecurityContext` mới đã chứa `Authentication` phù hợp với annotation test.

**Câu 3.** Đã khai `@WithMockTenantUser(roles={"READER"})` nhưng `hasRole('READER')` thất bại. Cần kiểm gì?  
**Trả lời:** Kiểm factory có tạo `ROLE_READER`, authentication có authenticated, method security được bật, và tenant policy có đang từ chối.

**Câu 4.** Hai tenant cùng có user tên `alice`. Có được dùng username một mình để kiểm ownership không?  
**Trả lời:** Không; cần tenant/account identity đã xác thực và quyền theo resource.

**Câu 5.** Test `@WithMockTenantUser` gọi GET thành công. Điều đó chứng minh Basic password hoặc JWT signature đúng chưa?  
**Trả lời:** Chưa; test đã dựng authentication sẵn và bỏ qua authentication provider.

**Câu 6.** `@PreAuthorize` hoạt động trên bean inject nhưng không hoạt động khi dùng `new ProjectService()`. Vì sao?  
**Trả lời:** Lời gọi ngoài Spring không đi qua method-security interceptor/proxy.

**Câu 7.** Với `TEST_METHOD`, `@BeforeEach` có thể đọc authentication không?  
**Trả lời:** Thường có, vì listener cài context trước callback `@BeforeEach` trong lifecycle chuẩn.

**Câu 8.** Với `TEST_EXECUTION`, `@BeforeEach` có sẵn mock identity không?  
**Trả lời:** Không theo timing được mô tả; context được thiết lập ngay trước test method, sau `@BeforeEach`.

**Câu 9.** `@WithSecurityContext` có tự gắn CSRF token cho POST MockMvc không?  
**Trả lời:** Không. Dùng `with(csrf())` hoặc client flow phù hợp nếu cần test POST qua CsrfFilter.

**Câu 10.** Muốn kiểm permission `PROJECT_EXPORT` nhưng không muốn cấp `ROLE_ADMIN`, nên làm gì?  
**Trả lời:** Cấu hình factory/annotation tạo chính xác `SimpleGrantedAuthority("PROJECT_EXPORT")`, dùng `hasAuthority('PROJECT_EXPORT')`, test cả thiếu permission.

## 14. Checklist trước khi áp dụng cho dự án

1. **Xác định principal thực tế**: class, field ID nội bộ, tenant, roles/permissions; không đồng nhất email/username với account ID.
2. **Định nghĩa test annotation**: tên theo domain, thuộc tính có default hợp lý, roles và authorities không nhập nhằng.
3. **Viết factory**: validate input, tạo principal và `GrantedAuthority`, tạo authenticated `Authentication`, trả một context mới; không mutate global holder tùy ý.
4. **Chọn test lifecycle**: `TEST_METHOD` hay `TEST_EXECUTION` tùy setup có cần authentication hay không.
5. **Đảm bảo method security**: `@EnableMethodSecurity`, đúng bean Spring proxy, tránh self-invocation.
6. **Kiểm lớp bảo mật độc lập**: URL authorization, `@PreAuthorize`, tenant/ownership policy, CSRF ở POST; không dùng 403 chung chung làm bằng chứng một lớp cụ thể.
7. **Viết test âm tính**: user không có role, sai tenant, anonymous, principal sai type, account disabled, permission không đủ, cross-tenant resource.
8. **Tách mock identity và login thật**: `@WithSecurityContext` kiểm hành vi sau xác thực; integration test riêng kiểm password/token/IdP.
9. **Cô lập dữ liệu và dọn context**: Spring Test listener, tránh static mutable state, test song song và threads có propagation phức tạp.
10. **Đặt annotation ở test source**: không đưa factory cung cấp role/tenant giả vào đường xử lý production.

**Ghi nhớ:** `@WithSecurityContext` giúp mô phỏng **danh tính đã được xác thực theo đúng cấu trúc domain** để kiểm logic phân quyền một cách có chủ đích. Factory tạo bối cảnh kiểm thử; nó **không** thay thế authentication provider hay integration test xác thực thật. Với Spring Security Servlet, kết hợp kiểm thử service proxy và `MockMvc` sẽ phát hiện cả lỗi method security lẫn lỗi định tuyến/CSRF của request.
