# Áp dụng role hierarchy và đối chiếu quyền ở HTTP với service

## 1. Mục tiêu bài thực hành

Một hệ thống thường có các vai trò theo cấp bậc: **ADMIN** bao hàm quyền của **MANAGER**, MANAGER bao hàm quyền của **VIEWER**. Spring Security hỗ trợ **RoleHierarchy** để một người chỉ được cấp ROLE_ADMIN vẫn có thể vượt qua kiểm tra yêu cầu ROLE_MANAGER hoặc ROLE_VIEWER. Nhưng hệ thống có thể kiểm tra quyền ở **cả HTTP và service**. Nếu cấu hình hierarchy chỉ có ở một tầng, cùng một người dùng có thể được chấp nhận tại HTTP nhưng bị từ chối khi controller gọi service, hoặc ngược lại.

Bài thuộc phần **Thực hành tích hợp** của module **Spring Security – authorization**. Sau bài này, bạn có thể:

1. Khai báo role hierarchy **ROLE_ADMIN > ROLE_MANAGER > ROLE_VIEWER** và giải thích tính kế thừa bắc cầu.
2. Cấu hình **cùng một RoleHierarchy** cho authorization ở HTTP và cho **@PreAuthorize** trên service.
3. Kiểm thử user có **ROLE_ADMIN** (không cấp ROLE_MANAGER trực tiếp) vẫn được phép truy cập endpoint cần MANAGER và phương thức service cần MANAGER.
4. Kiểm thử **ROLE_MANAGER** được phép, **ROLE_VIEWER** bị từ chối và anonymous nhận challenge.
5. Xác minh **role hierarchy không tự vượt qua quyền theo tenant/owner**, kể cả với ADMIN.
6. So sánh HTTP **401/403/200** với kết quả của lời gọi Java trực tiếp (**AccessDeniedException** hoặc dữ liệu).
7. Chủ động phá một tầng cấu hình để chứng minh bộ test bắt được sự lệch quyền giữa HTTP và service.

Mã minh họa là dự án độc lập dùng **Java 17+, Spring Boot 3.5.7, Spring Security 6.x, Maven, JUnit 5, MockMvc**. Bài tập tập trung vào servlet security; không dùng WebFlux. Dữ liệu và membership được giả lập trong bộ nhớ để không cần database.

## 2. Cơ chế RoleHierarchy và điểm dễ nhầm

Ta định nghĩa:

~~~text
ROLE_ADMIN
   |
   v
ROLE_MANAGER
   |
   v
ROLE_VIEWER
~~~

Ý nghĩa của dấu **>** trong biểu thức Spring Security là **bao hàm**, không phải so sánh tên role theo thứ tự từ điển. Với các cấp trên:

| Authority được cấp trực tiếp | Authority đạt được khi xét hierarchy | Đạt yêu cầu hasRole('MANAGER')? |
| --- | --- | --- |
| ROLE_ADMIN | ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER | Có |
| ROLE_MANAGER | ROLE_MANAGER, ROLE_VIEWER | Có |
| ROLE_VIEWER | ROLE_VIEWER | Không |
| ROLE_AUDITOR (không thuộc hierarchy) | ROLE_AUDITOR | Không |

**Role hierarchy một chiều:** MANAGER có quyền VIEWER, nhưng VIEWER không có quyền MANAGER; hierarchy không tạo quyền ngược chiều. Quy tắc này chỉ mở rộng cách **so khớp authority** tại các điểm được cấu hình sử dụng hierarchy. Nó không cấp quyền tài liệu của người khác và không chứng minh user là thành viên của một tenant.

Với cấu hình prefix mặc định:

- **hasRole('MANAGER')** tương đương việc kiểm tra authority **ROLE_MANAGER** sau khi áp dụng RoleHierarchy tại điểm kiểm tra đó.
- **hasAuthority('SCOPE_reports.read')** xét tên authority cụ thể; role hierarchy ba cấp ở ví dụ này **không tạo** scope đó. Không nhầm role với OAuth scope.
- **RoleHierarchy#getReachableGrantedAuthorities(...)** cho biết những authority suy ra từ tập được cấp; không nhất thiết các authority suy ra đã được chèn vật lý vào Authentication hay JWT.

### 2.1. HTTP và service là hai điểm kiểm tra khác nhau

~~~text
MockMvc / HTTP request
         |
         v
SecurityFilterChain
  GET /api/tenants/*/reports/*
  -> AuthorityAuthorizationManager.hasRole("MANAGER")
  -> dùng RoleHierarchy
         |
         v
ReportController
         |
         v
ReportService.read(...) qua Spring proxy
  -> @PreAuthorize("hasRole('MANAGER') and domainPolicy")
  -> MethodSecurityExpressionHandler dùng RoleHierarchy
         |
         v
ReportRepository
~~~

Điều kiện thành công của endpoint trong ví dụ:

~~~text
ALLOW =
   authenticated
   AND httpHasRole("MANAGER")
   AND serviceHasRole("MANAGER")
   AND memberOf(principal, tenant)
   AND reportExists(tenant, reportId)
   AND reportOwner(tenant, reportId) == principal
~~~

HTTP **cho phép** chỉ có nghĩa đi tiếp đến controller; **@PreAuthorize vẫn kiểm**. Ngược lại, lời gọi Java trực tiếp vào service không đi qua security filter chain, nhưng method security vẫn kiểm tra khi bean được gọi qua Spring proxy. Ta dùng **cùng role threshold MANAGER** ở cả hai nơi để cố ý tạo hợp đồng nhất quán, còn tenant/owner được bảo vệ riêng tại service.

### 2.2. Vì sao cần cấu hình tường minh cả hai?

Trong Spring Security 6.x, **AuthorityAuthorizationManager** có phương thức **setRoleHierarchy**. Một bean RoleHierarchy không nên bị coi là bảo đảm mọi AuthorizationManager tùy biến đều áp dụng hierarchy; với manager được tạo thủ công, ví dụ này **gọi setRoleHierarchy rõ ràng**.

Đối với **@PreAuthorize**, **DefaultMethodSecurityExpressionHandler** phải nhận RoleHierarchy. Ta khai báo bean **static MethodSecurityExpressionHandler** để Spring công bố handler trước khi khởi tạo cấu hình method security. Cách này được tài liệu chính thức khuyến nghị.

Nếu bạn chỉ cấu hình HTTP manager, ADMIN có thể vượt qua URL nhưng bị @PreAuthorize từ chối vì không có ROLE_MANAGER trực tiếp. Nếu chỉ cấu hình method handler, ADMIN có thể hợp lệ ở service nhưng bị HTTP chặn. Bộ test sẽ phát hiện cả hai trường hợp.

## 3. Chuẩn bị project Maven

Cấu trúc thư mục:

~~~text
role-hierarchy-demo/
├── pom.xml
├── src/main/java/com/example/hierarchy/
│   ├── HierarchyApplication.java
│   ├── SecurityConfiguration.java
│   ├── Report.java
│   ├── ReportKey.java
│   ├── ReportRepository.java
│   ├── ReportPolicy.java
│   ├── ReportService.java
│   └── ReportController.java
└── src/test/java/com/example/hierarchy/
    └── RoleHierarchyIntegrationTest.java
~~~

**pom.xml**: starter web cho HTTP/JSON, starter security cho authorization, starter test + spring-security-test cho JUnit/MockMvc/@WithMockUser.

~~~xml
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
    <artifactId>role-hierarchy-demo</artifactId>
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

**HierarchyApplication.java**: @EnableMethodSecurity kích hoạt pre/post method security. Spring Boot không tự bật @PreAuthorize chỉ nhờ starter-security.

~~~java
package com.example.hierarchy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class HierarchyApplication {
    public static void main(String[] args) {
        SpringApplication.run(HierarchyApplication.class, args);
    }
}
~~~

## 4. Cấu hình chung cho HTTP và method security

**SecurityConfiguration.java** là file trọng tâm của bài:

~~~java
package com.example.hierarchy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class SecurityConfiguration {

    // Bản đồ quyền duy nhất: ADMIN bao hàm MANAGER; MANAGER bao hàm VIEWER.
    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
            "ROLE_ADMIN > ROLE_MANAGER\nROLE_MANAGER > ROLE_VIEWER"
        );
    }

    // Phải áp dụng hierarchy cho expression handler của @PreAuthorize.
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }

    // Manager dùng tại HTTP cũng phải được cấp cùng RoleHierarchy.
    @Bean
    AuthorizationManager<RequestAuthorizationContext> reportsHttpAccess(
            RoleHierarchy roleHierarchy) {
        var manager = AuthorityAuthorizationManager
            .<RequestAuthorizationContext>hasRole("MANAGER");
        manager.setRoleHierarchy(roleHierarchy);
        return manager;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> reportsHttpAccess
    ) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/tenants/*/reports/*"
                ).access(reportsHttpAccess)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đọc kỹ ba vị trí:**

1. **roleHierarchy()** trả về một bean RoleHierarchy với chuỗi quan hệ có prefix ROLE_. Không cần gán thẳng ROLE_MANAGER/ROLE_VIEWER vào test user ADMIN.
2. **methodSecurityExpressionHandler(...)** gắn hierarchy vào bộ giải biểu thức dùng cho @PreAuthorize. Cần static @Bean để bean được công bố sớm; nếu bỏ handler, lời gọi của ADMIN có thể bị service chặn mặc dù HTTP đã cho qua.
3. **reportsHttpAccess(...)** dùng **AuthorityAuthorizationManager.hasRole("MANAGER")** rồi gọi **setRoleHierarchy**. Nếu bỏ lời gọi này, ADMIN sẽ không tự khớp ROLE_MANAGER ở HTTP manager.
4. **securityFilterChain(...)** chỉ áp dụng reportsHttpAccess cho GET theo đường dẫn báo cáo; mọi URL còn lại mặc định bị từ chối. Matcher hẹp ở trên fallback denyAll.

**Lưu ý:** @Bean static khác với việc lời gọi protected method phải static; @PreAuthorize vẫn đặt trên **instance method** của Spring service proxy. Với nhiều SecurityFilterChain, nhớ rằng một request chỉ đi qua **chain đầu tiên khớp** (theo securityMatcher và @Order), không tự cộng các chain lại. Ví dụ này cố tình dùng một chain để loại bỏ nhầm lẫn thứ tự chain.

HTTP Basic được dùng để kiểm thử anonymous nhận HTTP 401. Kết quả 401/403 có thể khác khi bạn thay bằng resource server Bearer/JWT hoặc custom AuthenticationEntryPoint. Các endpoint chỉ đọc bằng GET nên không cần gửi CSRF token; khi bổ sung POST/PATCH/DELETE phải kiểm tra CSRF theo cơ chế xác thực áp dụng.

## 5. Dữ liệu và chính sách domain

Role hierarchy chỉ giải quyết **role threshold**; để đọc tài liệu, người dùng còn phải là member của tenant và là owner. Đây là phần **không thể suy ra chỉ từ ROLE_ADMIN**.

Dữ liệu thử nghiệm:

| Tenant | Report ID | Owner | Body |
| --- | --- | --- | --- |
| acme | q1 | alice | ACME Q1 for alice |
| acme | private | bob | ACME confidential for bob |
| beta | q1 | alice | BETA Q1 for alice |

Membership: **alice ∈ acme**, **bob ∈ acme, beta**. Report **beta/q1** có owner alice nhưng alice không thuộc beta, giúp phát hiện việc check owner mà bỏ tenant membership.

**Report.java**:

~~~java
package com.example.hierarchy;

public record Report(
    String tenantId, String reportId, String owner, String body
) {
}
~~~

**ReportKey.java**: dùng cả tenantId và reportId để không nhầm hai tenant có cùng ID.

~~~java
package com.example.hierarchy;

record ReportKey(String tenantId, String reportId) {
}
~~~

**ReportRepository.java**:

~~~java
package com.example.hierarchy;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class ReportRepository {
    private final Map<ReportKey, Report> reports = Map.of(
        new ReportKey("acme", "q1"),
            new Report("acme", "q1", "alice", "ACME Q1 for alice"),
        new ReportKey("acme", "private"),
            new Report("acme", "private", "bob", "ACME confidential for bob"),
        new ReportKey("beta", "q1"),
            new Report("beta", "q1", "alice", "BETA Q1 for alice")
    );

    public Optional<Report> find(String tenantId, String reportId) {
        return Optional.ofNullable(
            reports.get(new ReportKey(tenantId, reportId))
        );
    }
}
~~~

**ReportPolicy.java**: policy fail-closed nếu authentication thiếu, tenant không thuộc membership hoặc report không tồn tại/không thuộc owner. Hàm public để được gọi từ SpEL trong annotation.

~~~java
package com.example.hierarchy;

import java.util.Map;
import java.util.Set;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {
    private final ReportRepository repository;

    private final Map<String, Set<String>> memberships = Map.of(
        "alice", Set.of("acme"),
        "bob", Set.of("acme", "beta")
    );

    public ReportPolicy(ReportRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(
        Authentication authentication, String tenantId, String reportId
    ) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        String username = authentication.getName();
        if (!memberships.getOrDefault(username, Set.of()).contains(tenantId)) {
            return false;
        }

        return repository.find(tenantId, reportId)
            .map(report -> report.owner().equals(username))
            .orElse(false);
    }
}
~~~

**ReportService.java**: vừa yêu cầu role MANAGER (kể cả suy ra từ ADMIN) vừa yêu cầu domain policy. Bộ đếm giúp test phát hiện việc thân method chạy trước khi bị từ chối.

~~~java
package com.example.hierarchy;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportRepository repository;
    private final AtomicInteger invocations = new AtomicInteger();

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasRole('MANAGER') and @reportPolicy.canRead(authentication, #p0, #p1)"
    )
    public Report read(String tenantId, String reportId) {
        invocations.incrementAndGet();
        return repository.find(tenantId, reportId)
            .orElseThrow(() -> new IllegalStateException(
                "Report changed between authorization and read"
            ));
    }

    public int invocationCount() {
        return invocations.get();
    }

    public void resetInvocationCount() {
        invocations.set(0);
    }
}
~~~

Dùng **#p0/#p1** để truy cập tenantId/reportId theo vị trí, không phụ thuộc tên tham số có được compiler giữ hay không. Mọi lời gọi qua Spring-managed ReportService proxy đều được đánh giá @PreAuthorize trước thân read. Method **invocationCount** dùng minh họa; ở hệ thống thật có thể dùng spy/metric để theo dõi side effect.

**ReportController.java**:

~~~java
package com.example.hierarchy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/tenants/{tenantId}/reports/{reportId}")
    public Report read(
        @PathVariable String tenantId,
        @PathVariable String reportId
    ) {
        return service.read(tenantId, reportId);
    }
}
~~~

Controller inject Spring service, nên @PreAuthorize thực thi. Không tạo ReportService bằng **new** hoặc gọi protected method theo kiểu self-invocation. Nếu có background worker gọi trực tiếp service, domain policy vẫn bảo vệ vì được đặt tại service thay vì chỉ tại URL.

## 6. Ma trận kỳ vọng: đối chiếu hai lớp

Trong tất cả test dưới đây, **ROLE_ADMIN là authority được cấp trực tiếp duy nhất** cho test ADMIN, không cấp ROLE_MANAGER bổ sung. Như vậy test thật sự kiểm tra role hierarchy.

| Người dùng | Direct authorities | HTTP kiểm MANAGER | Service kiểm MANAGER + domain | Kết quả HTTP |
| --- | --- | --- | --- | --- |
| alice | ROLE_ADMIN | Allow nhờ hierarchy | Allow nhờ hierarchy + owner/tenant | 200 + body đúng |
| alice | ROLE_MANAGER | Allow | Allow | 200 + body đúng |
| alice | ROLE_VIEWER | Deny | Deny | 403 |
| anonymous | Không | Challenge | Không gọi | 401 |
| alice đọc acme/private | ROLE_ADMIN | Allow | Deny do owner=bob | 403 |
| alice đọc beta/q1 | ROLE_ADMIN | Allow | Deny do không thuộc beta | 403 |
| alice đọc acme/missing | ROLE_ADMIN | Allow | Deny do report không tồn tại | 403 |
| bob đọc acme/private | ROLE_MANAGER | Allow | Allow vì owner và tenant đúng | 200 |

Điểm quan trọng: một response HTTP 403 **không tự chứng minh** method security đang deny vì request có thể bị chặn từ filter chain. Vì vậy bộ test có cả **lời gọi service trực tiếp** và trường hợp ADMIN được HTTP chấp nhận nhưng domain policy ở service từ chối.

## 7. Bộ kiểm thử tích hợp HTTP và service

**RoleHierarchyIntegrationTest.java**: dùng @SpringBootTest + @AutoConfigureMockMvc để giữ filter chain, method proxy, RoleHierarchy và policy thật. @WithMockUser đặt đúng **một role/authority trực tiếp**, không tự thêm các role kế thừa. Các test dùng cùng Spring context và reset counter trước mỗi lần chạy.

~~~java
package com.example.hierarchy;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RoleHierarchyIntegrationTest {

    @Autowired private MockMvc mvc;
    @Autowired private ReportService service;
    @Autowired private RoleHierarchy hierarchy;

    @BeforeEach
    void reset() {
        service.resetInvocationCount();
    }

    @Test
    void hierarchyIsTransitive() {
        Set<String> reachable = hierarchy.getReachableGrantedAuthorities(
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")))
            .stream()
            .map(a -> a.getAuthority())
            .collect(Collectors.toSet());

        assertTrue(reachable.contains("ROLE_ADMIN"));
        assertTrue(reachable.contains("ROLE_MANAGER"));
        assertTrue(reachable.contains("ROLE_VIEWER"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_ADMIN"})
    void adminInheritsManagerAtHttpAndService() throws Exception {
        mvc.perform(get("/api/tenants/acme/reports/q1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("acme"))
            .andExpect(jsonPath("$.reportId").value("q1"))
            .andExpect(jsonPath("$.owner").value("alice"))
            .andExpect(jsonPath("$.body").value("ACME Q1 for alice"));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_ADMIN"})
    void adminInheritsManagerOnDirectServiceCall() {
        Report report = service.read("acme", "q1");

        assertEquals("ACME Q1 for alice", report.body());
        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_MANAGER"})
    void managerCanReadAtBothLayers() throws Exception {
        mvc.perform(get("/api/tenants/acme/reports/q1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.body").value("ACME Q1 for alice"));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_VIEWER"})
    void viewerCannotPassHttpManagerThreshold() throws Exception {
        mvc.perform(get("/api/tenants/acme/reports/q1"))
            .andExpect(status().isForbidden());

        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_VIEWER"})
    void viewerCannotPassDirectServiceManagerThreshold() {
        assertThrows(AccessDeniedException.class,
            () -> service.read("acme", "q1"));

        assertEquals(0, service.invocationCount());
    }

    @Test
    void anonymousIsChallengedAtHttpLayer() throws Exception {
        mvc.perform(get("/api/tenants/acme/reports/q1"))
            .andExpect(status().isUnauthorized());

        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_ADMIN"})
    void adminDoesNotBypassOwnership() throws Exception {
        mvc.perform(get("/api/tenants/acme/reports/private"))
            .andExpect(status().isForbidden());

        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_ADMIN"})
    void adminDoesNotBypassTenantMembership() throws Exception {
        // beta/q1 có owner=alice nhưng alice không phải thành viên beta.
        mvc.perform(get("/api/tenants/beta/reports/q1"))
            .andExpect(status().isForbidden());

        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_ADMIN"})
    void missingReportIsDeniedByDomainPolicy() throws Exception {
        mvc.perform(get("/api/tenants/acme/reports/missing"))
            .andExpect(status().isForbidden());

        assertEquals(0, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "bob", authorities = {"ROLE_MANAGER"})
    void managerCanReadOwnReportAsBob() throws Exception {
        mvc.perform(get("/api/tenants/acme/reports/private"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"))
            .andExpect(jsonPath("$.body").value("ACME confidential for bob"));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = {"ROLE_MANAGER"})
    void unknownRouteIsDeniedByDefault() throws Exception {
        mvc.perform(get("/outside"))
            .andExpect(status().isForbidden());

        assertEquals(0, service.invocationCount());
    }
}
~~~

### Giải thích kết quả

- **hierarchyIsTransitive** kiểm tra ADMIN suy ra MANAGER và VIEWER từ **bean thật**, không kiểm tra theo tên role trong code.
- **adminInheritsManagerAtHttpAndService** là test trọng tâm: user chỉ có ROLE_ADMIN nhưng vẫn nhận HTTP 200 và dữ liệu đúng, chứng minh **HTTP manager và method handler cùng nhận hierarchy**. Nếu thiếu một tầng, test này sẽ fail.
- **adminInheritsManagerOnDirectServiceCall** tách service khỏi URL, chứng minh @PreAuthorize áp dụng hierarchy.
- **managerCanReadAtBothLayers** chứng minh role được yêu cầu trực tiếp vẫn hoạt động, tránh cấu hình chỉ chấp nhận ADMIN.
- **viewerCannotPassHttpManagerThreshold** và **viewerCannotPassDirectServiceManagerThreshold** chứng minh cấp dưới không tự thừa kế cấp trên; HTTP deny phải xảy ra trước khi thân service chạy.
- **anonymousIsChallengedAtHttpLayer** xác nhận 401 của HTTP Basic.
- **adminDoesNotBypassOwnership**, **adminDoesNotBypassTenantMembership** và **missingReportIsDeniedByDomainPolicy** chứng minh role cao chỉ đáp ứng role threshold, không thể tự đọc tài nguyên bất kỳ.
- **managerCanReadOwnReportAsBob** kiểm tra policy hoạt động với principal khác và tài liệu thật của họ.
- **unknownRouteIsDeniedByDefault** xác nhận fallback denyAll.

Với các nhánh deny, **invocationCount() == 0** làm rõ method body chưa chạy. Đây là đặc tính của @PreAuthorize, không phải đảm bảo chung cho @PostAuthorize. Với nhánh allow, còn assert JSON body, tenant và owner, tránh việc chỉ test status 200 nhưng trả dữ liệu chéo tenant.

## 8. Chạy bài thực hành

Cần JDK 17 trở lên và Maven. Tại thư mục chứa pom.xml:

~~~bash
java -version
mvn -version
mvn test
~~~

Với cấu hình và code phù hợp, kỳ vọng **12 tests, 0 failures, 0 errors**. Số dòng log khởi tạo Spring context và thời gian thực thi phụ thuộc môi trường. Có thể chạy chỉ lớp test:

~~~bash
mvn -Dtest=RoleHierarchyIntegrationTest test
~~~

**Không cần chạy web server trên port thật**: MockMvc xử lý request bên trong Spring test context. @WithMockUser cung cấp Authentication cho test, không kiểm chứng đăng nhập, thông tin người dùng trong database hay token JWT thật.

Nếu cần nhìn riêng Spring method security trong debug, bật logging cho package liên quan trong cấu hình test; không dùng việc “có log” làm assertion chính vì log có thể đổi theo phiên bản.

## 9. Thử cố ý tạo xung đột và quan sát test đỏ

Sau khi chạy test thành công, chỉ thay **một lỗi mỗi lần**, chạy Maven lại, rồi khôi phục code. Các mutation dưới đây là ví dụ **sai có chủ ý**, không được giữ trong dự án ứng dụng.

### 9.1. Bỏ hierarchy ở HTTP

Trong **reportsHttpAccess**, tạm bỏ:

~~~java
manager.setRoleHierarchy(roleHierarchy);
~~~

Trường hợp **adminInheritsManagerAtHttpAndService** sẽ bị từ chối ở HTTP vì authentication chỉ có ROLE_ADMIN, manager yêu cầu ROLE_MANAGER mà không dùng hierarchy. Test **adminInheritsManagerOnDirectServiceCall** vẫn thành công vì method handler tiếp tục dùng hierarchy. Đây là bằng chứng cấu hình **lệch giữa hai tầng**.

### 9.2. Bỏ hierarchy ở method security

Giữ HTTP manager nhưng bỏ bean **methodSecurityExpressionHandler** hoặc bỏ dòng **handler.setRoleHierarchy(roleHierarchy)**. Khi đó HTTP có thể cho ADMIN đi qua, nhưng **@PreAuthorize hasRole('MANAGER')** không còn suy ra MANAGER từ ADMIN. Hai test ADMIN được phép sẽ fail, đặc biệt **adminInheritsManagerOnDirectServiceCall** xác định lỗi xảy ra ở service.

### 9.3. Thay ngưỡng HTTP hoặc service

Nếu HTTP yêu cầu MANAGER nhưng service đổi thành:

~~~java
@PreAuthorize(
    "hasRole('ADMIN') and @reportPolicy.canRead(authentication, #p0, #p1)"
)
~~~

User ROLE_MANAGER có thể vượt HTTP nhưng bị service từ chối. Test **managerCanReadAtBothLayers** sẽ fail. Nếu thay HTTP threshold thành VIEWER, test **viewerCannotPassHttpManagerThreshold** sẽ fail vì VIEWER vượt HTTP, và method vẫn chặn. Một test chỉ assert response 403 có thể bị xanh giả khi service chặn thay HTTP; cần kết hợp test trực tiếp từng layer, hoặc test riêng AuthorizationManager ở HTTP để xác định nguyên nhân.

### 9.4. Bỏ kiểm tra owner hoặc tenant

Nếu ReportPolicy trả true cho mọi role ADMIN mà không kiểm membership/owner, các test **adminDoesNotBypassOwnership** và **adminDoesNotBypassTenantMembership** phải fail. Role hierarchy không phải cơ chế admin bypass. Nếu nghiệp vụ muốn quyền override riêng, hãy khai báo rõ policy đó và tạo test của cả allow lẫn deny.

### 9.5. Bỏ @EnableMethodSecurity hoặc gọi service bằng new

Nếu xóa @EnableMethodSecurity hoặc tạo ReportService ngoài Spring, @PreAuthorize không được áp dụng. Test **viewerCannotPassDirectServiceManagerThreshold** và các deny do domain sẽ phát hiện lỗi. Đừng dùng @MockBean/@MockitoBean thay **chính service chứa annotation** trong bài test này, vì khi đó có thể không còn security proxy thật.

## 10. Đối chiếu nâng cao trong hệ thống thực tế

### 10.1. Bảng chủ sở hữu chính sách

| Lớp | Nội dung policy phù hợp | Cách kiểm tra |
| --- | --- | --- |
| HTTP filter chain | Method, URL, role/scope của endpoint | MockMvc với filter bật, test 401/403/200 |
| Method security | Ranh giới nghiệp vụ chung cho controller, job và caller khác | Direct bean call với @WithMockUser |
| Domain policy | Tenant membership, ownership, quyền trên resource/action | Fixture đổi tenant/owner, denied cases |
| Repository/DB | Tenant predicate, row-level security, dữ liệu cách ly tenant | Integration test truy vấn/DB thật |
| JWT/IdP | Authority mapping, issuer/audience, token expiry, revocation | Security test dùng token/chữ ký hoặc môi trường tích hợp |

Dùng cùng **RoleHierarchy** giúp thống nhất cách đánh giá role ở các điểm kiểm tra đã cấu hình. Nó **không tự thay thế** permission evaluator, tenant predicate, OAuth scopes, validation của JWT hay kiểm soát các đường gọi không qua Spring proxy.

### 10.2. Vấn đề thường gặp

- **Ghi ROLE_ sai:** **hasRole("MANAGER")**, không truyền **ROLE_MANAGER** vào hasRole khi API tự thêm prefix. Nếu dùng hasAuthority thì cung cấp nguyên chuỗi ROLE_MANAGER.
- **Chỉ khai báo hierarchy bean nhưng bỏ qua nơi tiêu thụ:** ở custom AuthorityAuthorizationManager cần wire roleHierarchy rõ; ở @PreAuthorize cần method expression handler phù hợp.
- **Gắn @PreAuthorize lên method nhưng quên @EnableMethodSecurity:** ứng dụng vẫn khởi động, authorization tại method không hoạt động như dự kiến.
- **Dùng @WithMockUser(roles={"ADMIN", "MANAGER"})** cho ca kế thừa: test như vậy **không chứng minh** ADMIN suy ra MANAGER. Trong ca hierarchy, chỉ cấp ROLE_ADMIN.
- **Chỉ test HTTP 403 của VIEWER:** method layer có thể bị lỗi nhưng HTTP đã chặn trước, khiến test xanh. Phải gọi trực tiếp service trong test tương ứng.
- **Chỉ kiểm role mà bỏ tenant/owner:** ADMIN có thể đọc nhầm dữ liệu; cấp vai trò cao không đồng nghĩa quyền của mọi tenant.
- **Dùng this.read(...) trong cùng bean:** self-invocation thường không đi qua Spring proxy; kiểm thử đường gọi thật nếu production có nó.
- **Dùng @AutoConfigureMockMvc(addFilters = false):** bỏ HTTP authorization ra khỏi kiểm thử; không thích hợp khi cần đối chiếu hai tầng.
- **Dùng nhiều SecurityFilterChain nhưng kiểm không đúng chain:** FilterChainProxy chọn chain đầu tiên khớp, không kết hợp tất cả chain.
- **Ghi hierarchy vòng tròn:** ví dụ A > B và B > A mâu thuẫn phân cấp. Hãy giữ đồ thị vai trò có ý nghĩa và tránh cycle.
- **Chỉ trả HTTP 200 rồi kết luận policy đúng:** phải assert body, owner, tenant, và negative tests cho thiếu quyền.

### 10.3. Khi hệ thống dùng OAuth2 và JWT

@WithMockUser chỉ mô phỏng tên và authorities, không kiểm claim mapping. Trong resource server, **SCOPE_reports.read** thường được suy ra từ claim scope bởi converter; role của tổ chức có thể đến từ claim riêng. Hãy viết test dùng JWT với đúng claims hoặc test HTTP token thật qua pipeline phù hợp; RoleHierarchy không tự chuyển role thành scope nếu bạn không khai báo quan hệ đó.

Nếu vai trò hoặc membership thay đổi sau khi login, JWT đã phát có thể giữ quyền cũ cho đến khi hết hạn hoặc được thu hồi bằng cơ chế khác. Cần kiểm thử **hiệu lực quyền sau revoke**, cache authorization và các node khác nhau theo hợp đồng nhất quán của sản phẩm. Đây là chủ đề riêng với việc kiểm tra hierarchy khi authorities đã có trong SecurityContext.

### 10.4. Tiêu chí nghiệm thu

- [ ] Một bean RoleHierarchy xác định ADMIN > MANAGER > VIEWER.
- [ ] HTTP AuthorizationManager và MethodSecurityExpressionHandler đều dùng bean đó.
- [ ] ADMIN chỉ được cấp ROLE_ADMIN trực tiếp nhưng vượt yêu cầu MANAGER ở HTTP **và** service.
- [ ] MANAGER hợp lệ; VIEWER bị từ chối ở cả HTTP lẫn lời gọi service trực tiếp.
- [ ] Anonymous bị yêu cầu xác thực theo HTTP Basic; route ngoài whitelist bị denyAll.
- [ ] ADMIN vẫn bị từ chối nếu sai owner, tenant hoặc report không tồn tại.
- [ ] Negative tests chứng minh thân service không chạy trước khi bị @PreAuthorize chặn.
- [ ] Mutation thiếu hierarchy ở một trong hai lớp làm ít nhất một test đỏ.
- [ ] Với hệ thống thực tế, kiểm tra thêm token claim mapping, nhiều chain và repository tenant filtering.

## 11. Tài liệu chính thức

- Spring Security — Authorization Architecture, mục **Hierarchical Roles**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — **Method Security** và custom MethodSecurityExpressionHandler: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Testing Method Security** (@WithMockUser): https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — **MockMvc Security Testing**: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html

**Điểm nhớ:** RoleHierarchy mô tả quan hệ **bao hàm role**. Muốn cùng một principal được quyết định nhất quán ở HTTP và service, hãy cấu hình hierarchy ở **cả hai điểm kiểm tra**, rồi test được phép **và** bị từ chối tại từng lớp. Role cao hơn vẫn không tự bỏ qua điều kiện tenant và ownership.