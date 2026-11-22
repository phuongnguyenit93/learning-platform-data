# Kiểm thử phương thức với `@WithSecurityContext`: principal và bộ quyền tùy chỉnh

## 1. Khi nào cần `@WithSecurityContext`?

Trong kiểm thử method security của Spring Security, `@WithMockUser` giúp giả lập một người dùng đơn giản với username, roles hoặc authorities. Tuy nhiên, ứng dụng thực tế thường có **principal riêng** mang thêm `tenantId`, `organizationId`, loại tài khoản hoặc các thuộc tính mà biểu thức `@PreAuthorize` phải kiểm tra. Khi đó, một test chỉ cấp username/role không mô phỏng đủ dữ liệu bảo mật.

Ví dụ nghiệp vụ: người dùng chỉ được xem tài liệu khi **đồng thời** có authority `document:read` và thuộc đúng tenant của tài liệu. Người duyệt phải có role `APPROVER` và cũng thuộc đúng tenant.

`@WithSecurityContext` cho phép tạo một **test annotation riêng**. Annotation này chỉ định một `WithSecurityContextFactory`, nơi bạn tự xây dựng `SecurityContext` chứa `Authentication`, principal và bộ `GrantedAuthority` tương ứng với từng test.

| Công cụ | Principal được tạo | Khi phù hợp |
| --- | --- | --- |
| `@WithMockUser` | Principal mặc định của Spring Security Test, thường là `User` | Chỉ cần username, role hoặc authority đơn giản |
| `@WithUserDetails` | Đối tượng từ `UserDetailsService` | Cần principal thật và người dùng có sẵn trong nguồn dữ liệu/bean |
| **`@WithSecurityContext`** | **Do factory của bạn quyết định** | Cần principal riêng, danh sách quyền linh hoạt, hoặc `Authentication` tùy chỉnh |

**Mục tiêu:** viết một annotation `@WithMockTenantUser` để mỗi test khai báo được `username`, `tenantId`, `authorities` và `roles`; xác minh chính xác quyền truy cập tại Spring bean.

## 2. Cơ chế hoạt động và các thành phần

Luồng thiết lập và sử dụng dữ liệu bảo mật:

```text
@Test + @WithMockTenantUser(...)
           |
           v
WithSecurityContextTestExecutionListener
           |
           v
WithMockTenantUserSecurityContextFactory
  1. tạo TenantPrincipal(username, tenantId)
  2. tạo GrantedAuthority từ authorities + roles
  3. tạo Authentication đã xác thực cho bài test
  4. đặt Authentication vào SecurityContext mới
           |
           v
SecurityContextHolder (luồng kiểm thử)
           |
           v
Spring-managed DocumentService proxy
           |
           v
@PreAuthorize kiểm tra quyền + tenant
           |
           +-- đủ điều kiện --> thực thi phương thức
           |
           +-- thiếu điều kiện --> AccessDeniedException
```

Phân biệt các kiểu dữ liệu:

- `SecurityContext` lưu `Authentication` hiện tại; `SecurityContextHolder` là điểm truy cập context theo chiến lược lưu trữ (mặc định gắn với thread).
- `Authentication.getPrincipal()` đại diện người dùng. Nó có thể là `UserDetails`, `Principal`, một object riêng, hoặc một kiểu principal khác tùy authentication mechanism.
- `Authentication.getAuthorities()` trả tập `GrantedAuthority`; Spring Security so sánh chuỗi authority khi đánh giá `hasAuthority` và `hasRole`.
- `hasAuthority('document:read')` cần đúng authority `document:read`.
- Với quy ước mặc định, `hasRole('APPROVER')` cần authority `ROLE_APPROVER`, không phải `APPROVER`.
- `@WithSecurityContext` thuộc **Spring Security Test**, dùng để tạo fixture kiểm thử; nó không phải annotation bảo vệ phương thức sản phẩm. Quy tắc truy cập nằm ở `@PreAuthorize` (hoặc cơ chế phân quyền khác) trên bean.

Factory **trả về một `SecurityContext` mới**. Test execution listener đưa context đó vào quá trình thực thi test và dọn dẹp sau test. Không cần trực tiếp gọi `SecurityContextHolder.setContext(...)` trong mỗi test.

## 3. Ví dụ đầy đủ: principal có tenant và quyền theo từng test

Ví dụ dùng **Java 17, Spring Boot 3.5.7, Spring Security 6.5.x, Maven, JUnit Jupiter**. Ứng dụng không có HTTP endpoint; kiểm thử gọi trực tiếp service do Spring quản lý, để đi qua method security proxy.

Cấu trúc dự án:

```text
custom-security-context-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/securitydemo/
    │   ├── SecurityDemoApplication.java
    │   ├── TenantPrincipal.java
    │   └── DocumentService.java
    └── test/java/com/example/securitydemo/
        ├── WithMockTenantUser.java
        ├── WithMockTenantUserSecurityContextFactory.java
        └── DocumentServiceSecurityTest.java
```

### 3.1. Maven dependencies

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>custom-security-context-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-security-test` mang đến `@WithSecurityContext`, `WithSecurityContextFactory`, `@WithAnonymousUser` và các test listeners. Chỉ thêm dependency production của Spring Security không đủ để sử dụng các annotation kiểm thử này.

### 3.2. Bật method security trong ứng dụng

Tệp `src/main/java/com/example/securitydemo/SecurityDemoApplication.java`:

```java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

`@EnableMethodSecurity` đăng ký interceptor xử lý `@PreAuthorize`. Nếu thiếu annotation này trong cấu hình mặc định, các lời gọi service có thể thực thi mà không bị kiểm tra phân quyền, khiến test sai mục đích.

### 3.3. Định nghĩa principal ứng dụng

Tệp `src/main/java/com/example/securitydemo/TenantPrincipal.java`:

```java
package com.example.securitydemo;

import java.security.Principal;
import java.util.Objects;

public final class TenantPrincipal implements Principal {

    private final String username;
    private final String tenantId;

    public TenantPrincipal(String username, String tenantId) {
        this.username = Objects.requireNonNull(username, "username");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
    }

    @Override
    public String getName() {
        return username;
    }

    public String getUsername() {
        return username;
    }

    public String getTenantId() {
        return tenantId;
    }
}
```

Đây là POJO bất biến và đồng thời triển khai `java.security.Principal`. Vì có `getName()`, `Authentication.getName()` của token mẫu có thể trả đúng username. Vì có `getTenantId()`, Spring Expression Language (SpEL) có thể truy cập thuộc tính `principal.tenantId` trong điều kiện bảo mật.

Trong production, principal có thể triển khai `UserDetails` hoặc là một kiểu khác. **Không bắt buộc** triển khai `UserDetails` để dùng `@WithSecurityContext`: factory có thể tạo một `Authentication` với bất kỳ principal thích hợp nào.

### 3.4. Service được bảo vệ bởi authority và tenant

Tệp `src/main/java/com/example/securitydemo/DocumentService.java`:

```java
package com.example.securitydemo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasAuthority('document:read') and principal.tenantId == #tenantId"
    )
    public String readDocument(@P("tenantId") String tenantId) {
        return "document:" + tenantId;
    }

    @PreAuthorize(
        "hasRole('APPROVER') and principal.tenantId == #tenantId"
    )
    public String approveDocument(@P("tenantId") String tenantId) {
        return "approved:" + tenantId;
    }
}
```

Hai điều kiện trong mỗi `@PreAuthorize` phải cùng đúng:

1. Có authority tương ứng (`document:read` hoặc `ROLE_APPROVER`).
2. `tenantId` trong principal đúng bằng tham số `tenantId` của phương thức.

`@P("tenantId")` (đúng import: `org.springframework.security.access.method.P`) công khai tên tham số cho method-security SpEL, kể cả khi không dựa vào metadata `-parameters` của trình biên dịch. Chuỗi `#tenantId` tham chiếu tham số lời gọi; `principal.tenantId` tham chiếu thuộc tính của principal đang xác thực.

**Quan trọng:** giá trị `tenantId` do caller gửi vào chỉ là tham số nghiệp vụ. Phân quyền so sánh nó với tenant đáng tin cậy trong `Authentication`, rồi mới cho phép thực thi. Ở hệ thống thật, vẫn cần kiểm tra tenant/ownership trong truy vấn dữ liệu phù hợp để tránh lộ dữ liệu qua những đường truy cập khác.

### 3.5. Tạo annotation riêng cho fixture kiểm thử

Tệp `src/test/java/com/example/securitydemo/WithMockTenantUser.java`:

```java
package com.example.securitydemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@WithSecurityContext(factory = WithMockTenantUserSecurityContextFactory.class)
public @interface WithMockTenantUser {

    String username() default "demo";

    String tenantId() default "tenant-a";

    String[] authorities() default {};

    String[] roles() default {};
}
```

Giải thích từng phần:

- `@Target({METHOD, TYPE})` cho phép dùng annotation trên **một test method** hoặc **cả test class**.
- `@Retention(RUNTIME)` giữ metadata để test listener đọc được tại runtime.
- `@Inherited` cho phép annotation ở class được kế thừa khi kế thừa class test.
- `@WithSecurityContext(factory = ...)` liên kết annotation với code tạo context.
- `username` và `tenantId` cấu hình principal; `authorities` và `roles` cấu hình tập quyền. Mỗi test có thể chỉ định các trường cần dùng; trường còn lại lấy giá trị mặc định.

Annotation này nằm dưới `src/test/java` vì chỉ phục vụ kiểm thử. Việc khai báo một test annotation **không thay thế** annotation phân quyền trên service.

### 3.6. Factory tạo principal, authorities và SecurityContext

Tệp `src/test/java/com/example/securitydemo/WithMockTenantUserSecurityContextFactory.java`:

```java
package com.example.securitydemo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithMockTenantUserSecurityContextFactory
        implements WithSecurityContextFactory<WithMockTenantUser> {

    @Override
    public SecurityContext createSecurityContext(WithMockTenantUser user) {
        TenantPrincipal principal =
                new TenantPrincipal(user.username(), user.tenantId());

        List<GrantedAuthority> permissions = new ArrayList<>();

        for (String authority : user.authorities()) {
            permissions.add(new SimpleGrantedAuthority(authority));
        }

        for (String role : user.roles()) {
            permissions.add(new SimpleGrantedAuthority("ROLE_" + role));
        }

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, "N/A", permissions);

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
```

Từng bước có tác dụng:

1. Dựng `TenantPrincipal` với dữ liệu annotation của **test hiện tại**.
2. Chuyển mỗi chuỗi `authorities` thành `SimpleGrantedAuthority`, giữ nguyên tên.
3. Chuyển mỗi phần tử `roles` thành authority có tiền tố `ROLE_` theo quy ước mặc định. Ví dụ `roles = {"APPROVER"}` tạo `ROLE_APPROVER`.
4. Dựng `UsernamePasswordAuthenticationToken.authenticated(...)` để có đối tượng `Authentication` đã xác thực cho bài test; credential `"N/A"` chỉ là giá trị giả, không được dùng để đăng nhập.
5. Tạo `SecurityContext` mới rồi trả cho listener. Không tái sử dụng một context tĩnh giữa các test.

Nếu truyền `authorities = {"APPROVER"}`, factory tạo authority `APPROVER`, nên `hasRole('APPROVER')` **không** khớp. Để khớp, dùng `roles = {"APPROVER"}` hoặc `authorities = {"ROLE_APPROVER"}`. Không đưa chuỗi đã có `ROLE_` vào `roles`, nếu không sẽ thành `ROLE_ROLE_APPROVER`.

### 3.7. Kiểm thử principal, bộ quyền, điều kiện cho phép và từ chối

Tệp `src/test/java/com/example/securitydemo/DocumentServiceSecurityTest.java`:

```java
package com.example.securitydemo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(classes = SecurityDemoApplication.class)
@WithMockTenantUser(
    username = "lan",
    tenantId = "tenant-a",
    authorities = {"document:read"}
)
class DocumentServiceSecurityTest {

    @Autowired
    private DocumentService documentService;

    @Test
    void springInjectsProxiedService() {
        assertThat(AopUtils.isAopProxy(documentService)).isTrue();
    }

    @Test
    void customPrincipalAndAuthoritiesArePresent() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication.isAuthenticated()).isTrue();
        assertThat(authentication.getName()).isEqualTo("lan");
        assertThat(authentication.getPrincipal())
                .isInstanceOf(TenantPrincipal.class);

        TenantPrincipal principal =
                (TenantPrincipal) authentication.getPrincipal();
        assertThat(principal.getTenantId()).isEqualTo("tenant-a");

        assertThat(authentication.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("document:read");
    }

    @Test
    void readerCanReadDocumentInOwnTenant() {
        assertThat(documentService.readDocument("tenant-a"))
                .isEqualTo("document:tenant-a");
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-a",
        authorities = {"document:write"}
    )
    void userWithoutReadAuthorityIsDenied() {
        assertThatThrownBy(() -> documentService.readDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-b",
        authorities = {"document:read"}
    )
    void readerFromDifferentTenantIsDenied() {
        assertThatThrownBy(() -> documentService.readDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-a",
        roles = {"APPROVER"}
    )
    void approverCanApproveOwnTenantDocument() {
        assertThat(documentService.approveDocument("tenant-a"))
                .isEqualTo("approved:tenant-a");
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-a",
        authorities = {"APPROVER"}
    )
    void authorityWithoutRolePrefixDoesNotMatchHasRole() {
        assertThatThrownBy(() -> documentService.approveDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadDocument() {
        assertThatThrownBy(() -> documentService.readDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

Có **8 test**:

1. **Proxy:** xác minh `DocumentService` lấy từ Spring là AOP proxy. Kiểm tra này có ích, nhưng bản thân nó chưa chứng minh authorization hoạt động.
2. **Principal + authorities:** xác minh factory thực sự đưa `TenantPrincipal("lan", "tenant-a")` và quyền `document:read` vào context; kiểm tra thêm `Authentication.getName()`.
3. **Cho phép đúng tenant:** quyền và tenant đều đúng, service trả `document:tenant-a`.
4. **Thiếu quyền:** cùng tenant nhưng chỉ có `document:write`, truy cập bị từ chối.
5. **Sai tenant:** có `document:read` nhưng principal thuộc tenant khác, truy cập bị từ chối.
6. **Đúng role:** `roles = {"APPROVER"}` được chuyển thành `ROLE_APPROVER`, duyệt thành công.
7. **Sai định dạng quyền:** authority `APPROVER` không thỏa `hasRole('APPROVER')`.
8. **Ẩn danh:** `@WithAnonymousUser` đặt trạng thái anonymous thay cho annotation cấp class; truy cập bị từ chối.

Annotation trên test class áp dụng mặc định cho các test không khai báo authentication riêng. **Annotation ở test method thay thế** cấu hình authentication của class cho phương thức đó; các thuộc tính không truyền ở annotation method sử dụng default của chính annotation, không tự động cộng quyền với cấu hình class.

Các trường hợp bị từ chối sử dụng `assertThatThrownBy(...).isInstanceOf(AccessDeniedException.class)` để kiểm tra hành vi mà annotation bảo mật thực sự chặn lời gọi. Tùy phiên bản, exception cụ thể có thể là một lớp con của `AccessDeniedException`.

### 3.8. Chạy thử và đối chiếu kết quả

Từ thư mục chứa `pom.xml`, dùng JDK 17+ cùng Maven:

```bash
java -version
mvn test
```

Kỳ vọng bộ test thành công có tổng kết tương đương:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **kết quả kỳ vọng**, không phải log của một lần chạy đã thực hiện. Maven có thể in nhiều dòng khởi tạo Spring context, nhưng điều cần kiểm tra là tổng số test và các assertion.

Một phép kiểm tra độ nhạy rất hữu ích: tạm bỏ `@EnableMethodSecurity` trong bản thử nghiệm và chạy lại. Các test `userWithoutReadAuthorityIsDenied`, `readerFromDifferentTenantIsDenied`, `authorityWithoutRolePrefixDoesNotMatchHasRole` và `anonymousCannotReadDocument` phải không còn chứng minh được từ chối; test proxy cũng có thể thất bại. Sau phép kiểm tra, khôi phục cấu hình. Nếu bộ test vẫn hoàn toàn xanh khi vô hiệu hóa security, nhiều khả năng bạn đang gọi nhầm mock/target object hoặc chưa kiểm tra nhánh từ chối.

## 4. Kiểm soát vòng đời của security context

### 4.1. Listener thiết lập context vào lúc nào?

Với Spring Test integration, `WithSecurityContextTestExecutionListener` xử lý `@WithSecurityContext` và các meta-annotation của nó. Mặc định, context được thiết lập trong sự kiện `beforeTestMethod`, tức là **trước `@BeforeEach` của JUnit Jupiter**. Có thể chọn `TestExecutionEvent.TEST_EXECUTION` để thiết lập context sau `@BeforeEach` nhưng trước chính phương thức `@Test`.

Ví dụ **minh họa riêng**, không thay thế annotation trong project hoàn chỉnh:

```java
// Đặt trên khai báo annotation tùy chỉnh nếu thật sự cần đổi thời điểm.
@WithSecurityContext(
    factory = WithMockTenantUserSecurityContextFactory.class,
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
```

Với lựa chọn này, đừng kỳ vọng principal tùy chỉnh đã được thiết lập khi `@BeforeEach` chạy. Import enum đúng là `org.springframework.security.test.context.support.TestExecutionEvent`.

Các test cần isolation: mỗi factory invocation nên sinh context mới, không dùng `static SecurityContext` có thể gây rò rỉ principal giữa test. Khi sử dụng Spring Test listeners chuẩn, không phải tự viết `@AfterEach` chỉ để xóa security context.

### 4.2. Context của test không tự xác thực request HTTP

`@WithSecurityContext` cấu hình context cho **luồng chạy test**. Khi dùng một HTTP server thực chạy ở luồng khác (ví dụ `@SpringBootTest(webEnvironment = RANDOM_PORT)` rồi gửi HTTP request), server không tự nhận principal từ thread test. Với kiểm thử HTTP, cần gắn thông tin xác thực vào request (MockMvc `with(user(...))`, bearer token, HTTP Basic, v.v.) phù hợp với mục tiêu test.

Bài này kiểm thử **method security trực tiếp** qua Spring-managed service. Nó không thay thế kiểm thử token validation, filter chain hay quyền ở endpoint.

## 5. Các biến thể khi thiết kế factory

### 5.1. Principal kiểu `UserDetails`

Nếu ứng dụng có `CustomUserDetails`, factory có thể khởi tạo hoặc lấy đối tượng đó rồi đặt vào `Authentication`, miễn là kiểu và authorities khớp với logic mà method-security expression cần đọc. Khi muốn sử dụng dữ liệu thực từ `UserDetailsService`, `@WithUserDetails` thường đơn giản hơn. Chọn `@WithSecurityContext` khi cần thêm trường hoặc authentication semantics mà test annotation có sẵn không diễn tả được.

### 5.2. Cần JWT/OAuth2AuthenticationToken thật trong unit/integration test?

Có thể tạo một `Authentication` thuộc kiểu khác trong factory, thay vì `UsernamePasswordAuthenticationToken`, nhưng phải hiểu loại token mà production code thực sự kiểm tra. Nếu production expression dùng `authentication.tokenAttributes` hoặc kiểm tra kiểu `JwtAuthenticationToken`, factory tạo username-password token sẽ **không tương đương**. Hãy tạo token phù hợp và kiểm tra claims, authorities cùng principal đúng nhu cầu; nếu bài kiểm thử đi qua HTTP filter thì dùng công cụ test riêng cho HTTP hoặc gửi request xác thực.

### 5.3. Factory cần Spring bean?

`WithSecurityContextFactory` hỗ trợ dependency injection của Spring Test. Có thể dùng `@Autowired` để đưa một builder hoặc dịch vụ tạo principal vào factory khi cần logic dựng fixture phức tạp. Tuy nhiên, ưu tiên fixture nhỏ, rõ dữ liệu; tránh để test phải gọi cơ sở dữ liệu hoặc hệ thống ngoài chỉ nhằm tạo một principal đơn giản.

## 6. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Test không nhận annotation tùy chỉnh | Thiếu `@Retention(RUNTIME)`, thiếu `@WithSecurityContext` hoặc thiếu dependency `spring-security-test` | Kiểm tra annotation + factory và Spring Test integration |
| `Authentication.getPrincipal()` sai kiểu | Factory vẫn tạo `User` mặc định hoặc service yêu cầu một kiểu khác | Assert `instanceof TenantPrincipal` ngay trong test |
| `principal.tenantId` không đọc được | Principal không có getter property phù hợp | Cung cấp `getTenantId()` hoặc truy cập đúng cấu trúc principal |
| `#tenantId` không resolve | Tên tham số Java không được lưu hoặc không khai báo alias | Dùng `@P("tenantId")` với đúng import, hoặc build với `-parameters` |
| `hasRole('APPROVER')` luôn từ chối | Đã cấp `APPROVER` thay vì `ROLE_APPROVER` | Dùng `roles = {"APPROVER"}` trong custom annotation |
| Quyền bị cộng dồn ngoài ý muốn | Hiểu nhầm annotation method sẽ kế thừa toàn bộ authorities của annotation class | Kiểm tra từng fixture; factory tạo quyền từ annotation hiệu lực của test |
| Mọi cuộc gọi đều thành công | Chưa bật `@EnableMethodSecurity`, gọi object qua `new` hoặc mock, hoặc self-invocation bỏ qua proxy | Inject bean Spring; assert denied và kiểm tra proxy |
| `@BeforeEach` chưa thấy principal | Đặt `setupBefore = TEST_EXECUTION` | Dùng mặc định hoặc di chuyển assertion vào `@Test` |
| Test HTTP qua server thật luôn anonymous | Security context của thread test không chuyển sang thread HTTP | Cung cấp credentials/token ở request và test filter chain riêng |
| Test thay đổi khi chạy song song | Factory chia sẻ context mutable hoặc state tĩnh | Luôn tạo `SecurityContext` mới và tránh giữ trạng thái chung |

Đặc biệt, **không dùng `@MockBean`/`@MockitoBean` để thay thế chính `DocumentService`** rồi coi lời gọi mock là bằng chứng annotation bảo mật hoạt động. Mockito thuần giúp kiểm thử logic, nhưng phép kiểm tra authorization cần method invocation đi qua đối tượng mà Spring Security có thể intercept.

Với Spring AOP proxy, lời gọi nội bộ kiểu `this.securedMethod()` thường không đi qua proxy nên có thể bỏ qua method-security advice trên phương thức đích. Phép test qua bean được inject cần bao phủ đúng đường gọi mà production sử dụng.

## 7. Tiêu chí của một bộ test đáng tin

Một bộ kiểm thử `@WithSecurityContext` chất lượng nên bảo đảm:

1. **Đúng identity:** principal có đúng kiểu, username và các thuộc tính được policy sử dụng.
2. **Đúng quyền:** `GrantedAuthority` trong `Authentication` khớp chính xác với ý nghĩa của `hasAuthority`/`hasRole`; có test cho role prefix nếu liên quan.
3. **Đúng ranh giới:** chạy test với Spring context có `@EnableMethodSecurity` và gọi bean qua Spring proxy.
4. **Có positive + negative tests:** đồng thời kiểm tra đủ quyền, thiếu quyền, sai thuộc tính nghiệp vụ và anonymous khi cần.
5. **Không phụ thuộc thứ tự chạy:** không lưu `Authentication` hoặc `SecurityContext` tĩnh; dữ liệu fixture của mỗi test dễ đọc.
6. **Phát hiện được lỗi phân quyền:** vô hiệu hóa policy trong một phép thử đối chứng phải làm ít nhất một negative test thất bại.

Ví dụ bài tập nâng cao: thêm `departmentId` vào `TenantPrincipal` và annotation, rồi bổ sung điều kiện `principal.departmentId == #departmentId` trong một phương thức khác. Viết ba test độc lập: đúng tenant/phòng ban/quyền; sai phòng ban dù đúng tenant; đủ thông tin tổ chức nhưng thiếu authority. Nếu cả ba kiểm chứng đúng, bạn đã vận dụng `@WithSecurityContext` để mô phỏng một principal và bộ quyền phù hợp với policy cụ thể của ứng dụng.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security: `@WithSecurityContext`](https://docs.spring.io/spring-security/reference/servlet/test/method.html): cách tạo custom annotation, `WithSecurityContextFactory`, lifecycle của test context.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, role/authority, principal và tham số phương thức.
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): giới hạn của proxy và self-invocation.
