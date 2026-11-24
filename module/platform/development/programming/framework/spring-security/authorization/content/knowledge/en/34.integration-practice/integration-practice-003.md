# Applying Role Hierarchy and Aligning Permissions Across HTTP and Service Layers

## 1. Practice Objectives

Systems often have hierarchical roles: **ADMIN** implies the permissions of **MANAGER**, and MANAGER implies the permissions of **VIEWER**. Spring Security supports **RoleHierarchy** so that a user granted only ROLE_ADMIN can still pass checks requiring ROLE_MANAGER or ROLE_VIEWER. However, a system may enforce authorization at **both the HTTP and service layers**. If the hierarchy is configured at only one layer, the same user may be permitted at HTTP yet denied when the controller calls the service, or vice versa.

This lesson belongs to the **Integration Practice** section of the **Spring Security – authorization** module. After this lesson, you will be able to:

1. Declare the role hierarchy **ROLE_ADMIN > ROLE_MANAGER > ROLE_VIEWER** and explain transitive inheritance.
2. Configure **the same RoleHierarchy** for HTTP authorization and for **@PreAuthorize** on services.
3. Test that a user with **ROLE_ADMIN** (without being directly granted ROLE_MANAGER) can still access endpoints requiring MANAGER and service methods requiring MANAGER.
4. Test that **ROLE_MANAGER** is permitted, **ROLE_VIEWER** is denied, and anonymous receives a challenge.
5. Verify that **role hierarchy does not bypass tenant/owner permissions**, even for ADMIN.
6. Compare HTTP **401/403/200** responses with the outcome of direct Java calls (**AccessDeniedException** or data).
7. Intentionally break one configuration layer to prove the test suite catches authorization drift between HTTP and service layers.

The illustrative code is a standalone project using **Java 17+, Spring Boot 3.5.7, Spring Security 6.x, Maven, JUnit 5, MockMvc**. The exercise focuses on servlet security; WebFlux is not used. Data and memberships are simulated in memory so no database is needed.

## 2. RoleHierarchy Mechanism and Common Misconceptions

We define:

~~~text
ROLE_ADMIN
   |
   v
ROLE_MANAGER
   |
   v
ROLE_VIEWER
~~~

The meaning of the **>** sign in Spring Security expressions is **implies**, not a lexicographical comparison of role names. With the levels above:

| Directly Granted Authority | Reachable Authorities via Hierarchy | Satisfies hasRole('MANAGER')? |
| --- | --- | --- |
| ROLE_ADMIN | ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER | Yes |
| ROLE_MANAGER | ROLE_MANAGER, ROLE_VIEWER | Yes |
| ROLE_VIEWER | ROLE_VIEWER | No |
| ROLE_AUDITOR (not in hierarchy) | ROLE_AUDITOR | No |

**Role hierarchy is one-directional:** MANAGER has VIEWER permissions, but VIEWER does not have MANAGER permissions; hierarchy does not create reverse permissions. This rule only expands how **authorities are matched** at checkpoints configured to use the hierarchy. It does not grant access to another user's documents and does not prove the user is a member of a tenant.

With the default prefix configuration:

- **hasRole('MANAGER')** is equivalent to checking authority **ROLE_MANAGER** after applying RoleHierarchy at that checkpoint.
- **hasAuthority('SCOPE_reports.read')** checks an exact authority name; the three-tier role hierarchy in this example **does not create** that scope. Do not confuse roles with OAuth scopes.
- **RoleHierarchy#getReachableGrantedAuthorities(...)** reports the authorities derived from the granted set; the derived authorities are not necessarily physically inserted into the Authentication or JWT.

### 2.1. HTTP and Service Are Two Separate Checkpoints

~~~text
MockMvc / HTTP request
         |
         v
SecurityFilterChain
  GET /api/tenants/*/reports/*
  -> AuthorityAuthorizationManager.hasRole("MANAGER")
  -> uses RoleHierarchy
         |
         v
ReportController
         |
         v
ReportService.read(...) via Spring proxy
  -> @PreAuthorize("hasRole('MANAGER') and domainPolicy")
  -> MethodSecurityExpressionHandler uses RoleHierarchy
         |
         v
ReportRepository
~~~

Success condition for the endpoint in this example:

~~~text
ALLOW =
   authenticated
   AND httpHasRole("MANAGER")
   AND serviceHasRole("MANAGER")
   AND memberOf(principal, tenant)
   AND reportExists(tenant, reportId)
   AND reportOwner(tenant, reportId) == principal
~~~

HTTP **permitting** only means proceeding to the controller; **@PreAuthorize still checks**. Conversely, a direct Java call to the service bypasses the security filter chain, yet method security still checks when the bean is invoked through a Spring proxy. We use the **same MANAGER role threshold** in both places to intentionally create a consistent contract, while tenant/owner is protected separately in the service.

### 2.2. Why Must Both Be Configured Explicitly?

In Spring Security 6.x, **AuthorityAuthorizationManager** has a **setRoleHierarchy** method. A RoleHierarchy bean should not be assumed to guarantee every custom AuthorizationManager applies the hierarchy; for manually created managers, this example **calls setRoleHierarchy explicitly**.

For **@PreAuthorize**, **DefaultMethodSecurityExpressionHandler** must receive the RoleHierarchy. We declare a **static MethodSecurityExpressionHandler** bean so Spring publishes the handler before initializing method security configuration. This approach is recommended by the official documentation.

If you only configure the HTTP manager, ADMIN may pass the URL check yet be denied by @PreAuthorize because they lack ROLE_MANAGER directly. If you only configure the method handler, ADMIN may be valid in the service yet blocked at HTTP. The test suite will catch both cases.

## 3. Preparing the Maven Project

Directory structure:

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

**pom.xml**: web starter for HTTP/JSON, security starter for authorization, test starter + spring-security-test for JUnit/MockMvc/@WithMockUser.

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

**HierarchyApplication.java**: @EnableMethodSecurity enables pre/post method security. Spring Boot does not automatically enable @PreAuthorize from starter-security alone.

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

## 4. Shared Configuration for HTTP and Method Security

**SecurityConfiguration.java** is the centerpiece file of this lesson:

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

    // Single permission map: ADMIN implies MANAGER; MANAGER implies VIEWER.
    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
            "ROLE_ADMIN > ROLE_MANAGER\nROLE_MANAGER > ROLE_VIEWER"
        );
    }

    // Must apply the hierarchy to the expression handler for @PreAuthorize.
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }

    // The manager used at HTTP must also receive the same RoleHierarchy.
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

**Read these three parts carefully:**

1. **roleHierarchy()** returns a RoleHierarchy bean with relationship strings carrying the ROLE_ prefix. There is no need to assign ROLE_MANAGER/ROLE_VIEWER directly to the ADMIN test user.
2. **methodSecurityExpressionHandler(...)** attaches the hierarchy to the expression evaluator used by @PreAuthorize. A static @Bean is needed so the bean is published early; if the handler is omitted, ADMIN's call can be blocked by the service even though HTTP allowed it through.
3. **reportsHttpAccess(...)** uses **AuthorityAuthorizationManager.hasRole("MANAGER")** and then calls **setRoleHierarchy**. If this call is omitted, ADMIN will not automatically match ROLE_MANAGER in the HTTP manager.
4. **securityFilterChain(...)** applies reportsHttpAccess only to GET requests matching the report path; all remaining URLs are denied by default. The narrow matcher sits above the denyAll fallback.

**Note:** a static @Bean is different from requiring the protected method to be static; @PreAuthorize is still placed on an **instance method** of a Spring service proxy. With multiple SecurityFilterChains, remember that a request passes through **only the first matching chain** (by securityMatcher and @Order), never combining chains together. This example intentionally uses a single chain to eliminate chain-ordering confusion.

HTTP Basic is used to test that anonymous receives HTTP 401. The 401/403 outcome may differ when you switch to a Bearer/JWT resource server or a custom AuthenticationEntryPoint. Endpoints are read-only via GET so no CSRF token is needed; when adding POST/PATCH/DELETE, check CSRF according to the authentication mechanism used.

## 5. Data and Domain Policy

Role hierarchy only resolves the **role threshold**; to read a document, the user must also be a member of the tenant and the owner. This part **cannot be inferred from ROLE_ADMIN alone**.

Test data:

| Tenant | Report ID | Owner | Body |
| --- | --- | --- | --- |
| acme | q1 | alice | ACME Q1 for alice |
| acme | private | bob | ACME confidential for bob |
| beta | q1 | alice | BETA Q1 for alice |

Membership: **alice ∈ acme**, **bob ∈ acme, beta**. Report **beta/q1** has owner alice even though alice does not belong to beta, helping catch owner checks that skip tenant membership.

**Report.java**:

~~~java
package com.example.hierarchy;

public record Report(
    String tenantId, String reportId, String owner, String body
) {
}
~~~

**ReportKey.java**: uses both tenantId and reportId so two tenants with the same ID are not confused.

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

**ReportPolicy.java**: fail-closed policy when authentication is missing, tenant is not in membership, or report does not exist/is not owned by caller. Method is public so SpEL can invoke it from the annotation.

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

**ReportService.java**: requires both role MANAGER (including derived from ADMIN) and the domain policy. The counter helps tests detect if the method body executes before being denied.

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

Using **#p0/#p1** accesses tenantId/reportId by position, regardless of whether parameter names are preserved by the compiler. Every call through the Spring-managed ReportService proxy evaluates @PreAuthorize before the read body. The **invocationCount** method is illustrative; in real systems you can use spies/metrics to track side effects.

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

The controller injects the Spring service, so @PreAuthorize executes. Do not instantiate ReportService with **new** or call protected methods via self-invocation. If a background worker calls the service directly, the domain policy still protects it because enforcement lives on the service rather than only on the URL.

## 6. Expected Matrix: Cross-Checking Two Layers

In all tests below, **ROLE_ADMIN is the only directly granted authority** for the ADMIN tests, without adding ROLE_MANAGER. That way, the tests genuinely verify role hierarchy.

| User | Direct Authorities | HTTP Checks MANAGER | Service Checks MANAGER + Domain | HTTP Outcome |
| --- | --- | --- | --- | --- |
| alice | ROLE_ADMIN | Allow via hierarchy | Allow via hierarchy + owner/tenant | 200 + matching body |
| alice | ROLE_MANAGER | Allow | Allow | 200 + matching body |
| alice | ROLE_VIEWER | Deny | Deny | 403 |
| anonymous | None | Challenge | Not called | 401 |
| alice reading acme/private | ROLE_ADMIN | Allow | Deny because owner=bob | 403 |
| alice reading beta/q1 | ROLE_ADMIN | Allow | Deny because not in beta | 403 |
| alice reading acme/missing | ROLE_ADMIN | Allow | Deny because report does not exist | 403 |
| bob reading acme/private | ROLE_MANAGER | Allow | Allow because owner and tenant match | 200 |

Important point: an HTTP 403 response **does not by itself prove** method security is denying because the request could have been blocked by the filter chain. That is why the test suite includes both **direct service calls** and cases where ADMIN is accepted by HTTP yet denied by the domain policy in the service.

## 7. HTTP and Service Integration Test Suite

**RoleHierarchyIntegrationTest.java**: uses @SpringBootTest + @AutoConfigureMockMvc to keep the real filter chain, method proxy, RoleHierarchy, and policy. @WithMockUser sets **exactly one direct role/authority**, without adding inherited roles. Tests share the Spring context and reset the counter before each run.

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
        // beta/q1 has owner=alice, but alice is not a member of beta.
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

### Explaining the Results

- **hierarchyIsTransitive** verifies ADMIN implies MANAGER and VIEWER from the **real bean**, rather than checking role names in code.
- **adminInheritsManagerAtHttpAndService** is the core test: the user only has ROLE_ADMIN yet gets HTTP 200 and accurate data, proving **the HTTP manager and method handler share the hierarchy**. If either layer is missing, this test fails.
- **adminInheritsManagerOnDirectServiceCall** isolates the service from the URL, proving @PreAuthorize applies the hierarchy.
- **managerCanReadAtBothLayers** proves the directly required role still works, avoiding configs that only accept ADMIN.
- **viewerCannotPassHttpManagerThreshold** and **viewerCannotPassDirectServiceManagerThreshold** prove lower tiers do not inherit higher tiers; HTTP denial must occur before the service body runs.
- **anonymousIsChallengedAtHttpLayer** confirms HTTP Basic 401.
- **adminDoesNotBypassOwnership**, **adminDoesNotBypassTenantMembership**, and **missingReportIsDeniedByDomainPolicy** prove a higher role only meets the role threshold and cannot read arbitrary resources.
- **managerCanReadOwnReportAsBob** checks that the policy works with another principal and their real document.
- **unknownRouteIsDeniedByDefault** confirms the denyAll fallback.

In the deny branches, **invocationCount() == 0** makes clear the method body never executed. This is a property of @PreAuthorize, not a general guarantee for @PostAuthorize. In the allow branches, we also assert JSON body, tenant, and owner, avoiding tests that check only status 200 while returning cross-tenant data.

## 8. Running the Practice Exercise

Requires JDK 17 or higher and Maven. In the directory containing pom.xml:

~~~bash
java -version
mvn -version
mvn test
~~~

With matching configuration and code, expect **12 tests, 0 failures, 0 errors**. Spring context startup log lines and execution time depend on the environment. You can run just the test class:

~~~bash
mvn -Dtest=RoleHierarchyIntegrationTest test
~~~

**No need to run a web server on a real port**: MockMvc processes requests inside the Spring test context. @WithMockUser supplies Authentication for tests; it does not verify login, database user records, or real JWT tokens.

If you need to inspect Spring method security specifically during debugging, enable logging for the relevant package in test config; never use “presence of a log line” as a primary assertion because logs can change across versions.

## 9. Intentionally Creating Conflicts and Observing Red Tests

After all tests pass, introduce only **one fault at a time**, re-run Maven, and then restore the code. The mutations below are **intentionally broken** examples and must not remain in an application project.

### 9.1. Removing Hierarchy at HTTP

In **reportsHttpAccess**, temporarily remove:

~~~java
manager.setRoleHierarchy(roleHierarchy);
~~~

**adminInheritsManagerAtHttpAndService** will be denied at HTTP because the authentication only has ROLE_ADMIN while the manager requires ROLE_MANAGER without using the hierarchy. **adminInheritsManagerOnDirectServiceCall** still passes because the method handler continues using the hierarchy. This is proof of **configuration drift between the two layers**.

### 9.2. Removing Hierarchy at Method Security

Keep the HTTP manager but remove the **methodSecurityExpressionHandler** bean or remove **handler.setRoleHierarchy(roleHierarchy)**. Then HTTP lets ADMIN through, yet **@PreAuthorize hasRole('MANAGER')** no longer infers MANAGER from ADMIN. Both ADMIN-permitted tests fail, and **adminInheritsManagerOnDirectServiceCall** specifically pinpoints the fault at the service layer.

### 9.3. Changing the HTTP or Service Threshold

If HTTP requires MANAGER while the service is changed to:

~~~java
@PreAuthorize(
    "hasRole('ADMIN') and @reportPolicy.canRead(authentication, #p0, #p1)"
)
~~~

A ROLE_MANAGER user can pass HTTP yet gets denied by the service. **managerCanReadAtBothLayers** fails. If the HTTP threshold is changed to VIEWER, **viewerCannotPassHttpManagerThreshold** fails because VIEWER passes HTTP while the method still blocks it. A test asserting only 403 can give a false positive when the service blocks instead of HTTP; combine direct per-layer tests or test the HTTP AuthorizationManager directly to isolate the cause.

### 9.4. Removing Owner or Tenant Checks

If ReportPolicy returns true for every ADMIN role without checking membership/owner, **adminDoesNotBypassOwnership** and **adminDoesNotBypassTenantMembership** must fail. Role hierarchy is not an admin bypass mechanism. If business rules want a dedicated override permission, declare that policy explicitly and write both allow and deny tests.

### 9.5. Removing @EnableMethodSecurity or Instantiating Service with new

If you delete @EnableMethodSecurity or construct ReportService outside Spring, @PreAuthorize is not enforced. **viewerCannotPassDirectServiceManagerThreshold** and domain denials will catch the bug. Do not replace **the annotated service itself** with @MockBean/@MockitoBean in this test, as doing so may remove the real security proxy.

## 10. Advanced Cross-Checking in Real Systems

### 10.1. Policy Ownership Table

| Layer | Appropriate Policy Content | How to Test |
| --- | --- | --- |
| HTTP filter chain | Endpoint method, URL, role/scope | MockMvc with filters enabled, test 401/403/200 |
| Method security | Shared business boundary for controllers, jobs, and other callers | Direct bean call with @WithMockUser |
| Domain policy | Tenant membership, ownership, resource/action permissions | Fixtures varying tenant/owner, denied cases |
| Repository/DB | Tenant predicate, row-level security, tenant-isolated data | Integration test querying a real DB |
| JWT/IdP | Authority mapping, issuer/audience, token expiry, revocation | Security tests using tokens/signatures or integration env |

Using the same **RoleHierarchy** unifies how roles are evaluated across configured checkpoints. It **does not replace** permission evaluators, tenant predicates, OAuth scopes, JWT validation, or protecting call paths that do not go through a Spring proxy.

### 10.2. Common Pitfalls

- **Wrong ROLE_ usage:** **hasRole("MANAGER")**, do not pass **ROLE_MANAGER** into hasRole when the API automatically adds the prefix. If using hasAuthority, supply the literal string ROLE_MANAGER.
- **Declaring the hierarchy bean without wiring consumers:** on a custom AuthorityAuthorizationManager, wire roleHierarchy explicitly; on @PreAuthorize, provide the proper method expression handler.
- **Adding @PreAuthorize to methods while forgetting @EnableMethodSecurity:** the app still starts, yet method authorization does not execute as expected.
- **Using @WithMockUser(roles={"ADMIN", "MANAGER"})** for inheritance cases: such a test **does not prove** ADMIN implies MANAGER. In hierarchy tests, grant only ROLE_ADMIN.
- **Testing only HTTP 403 for VIEWER:** the method layer might be broken while HTTP already blocked the call, keeping the test green. Call the service directly in a dedicated test.
- **Checking only roles while skipping tenant/owner:** ADMIN could read the wrong data; holding a higher role does not mean access to every tenant.
- **Calling this.read(...) within the same bean:** self-invocation typically bypasses the Spring proxy; test real call paths if production uses them.
- **Using @AutoConfigureMockMvc(addFilters = false):** removes HTTP authorization from testing; unsuitable when cross-checking two layers.
- **Using multiple SecurityFilterChains while checking the wrong chain:** FilterChainProxy picks the first matching chain, rather than combining all chains.
- **Writing circular hierarchies:** e.g., A > B and B > A creates contradictory hierarchies. Keep the role graph meaningful and acyclic.
- **Observing HTTP 200 and concluding the policy is right:** assert the body, owner, tenant, and negative tests for insufficient privileges.

### 10.3. When the System Uses OAuth2 and JWT

@WithMockUser only simulates username and authorities; it does not test claim mapping. In a resource server, **SCOPE_reports.read** is typically derived from the scope claim by a converter; organization roles may come from a separate claim. Write tests using JWTs with realistic claims or test real HTTP tokens through the full pipeline; RoleHierarchy does not convert roles into scopes unless you declare that relationship.

If roles or memberships change after login, an already issued JWT may retain old permissions until expiration or revocation via another mechanism. Test **permission effectiveness after revocation**, authorization caches, and multiple nodes according to the product's consistency contract. That is separate from checking hierarchy once authorities are already in SecurityContext.

### 10.4. Acceptance Criteria

- [ ] One RoleHierarchy bean defines ADMIN > MANAGER > VIEWER.
- [ ] Both HTTP AuthorizationManager and MethodSecurityExpressionHandler use that bean.
- [ ] ADMIN is granted only ROLE_ADMIN directly yet passes the MANAGER threshold at HTTP **and** service.
- [ ] MANAGER succeeds; VIEWER is denied at both HTTP and direct service calls.
- [ ] Anonymous receives an authentication challenge via HTTP Basic; routes outside the whitelist hit denyAll.
- [ ] ADMIN is still denied on wrong owner, wrong tenant, or nonexistent report.
- [ ] Negative tests prove the service body does not run before @PreAuthorize blocks it.
- [ ] Mutating either layer to omit the hierarchy causes at least one test to fail.
- [ ] For real systems, additionally verify token claim mapping, multiple chains, and repository tenant filtering.

## 11. Official Documentation

- Spring Security — Authorization Architecture, section **Hierarchical Roles**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — **Method Security** and custom MethodSecurityExpressionHandler: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Testing Method Security** (@WithMockUser): https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — **MockMvc Security Testing**: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html

**Key takeaway:** RoleHierarchy describes a **role-implication** relationship. To evaluate the same principal consistently across HTTP and service layers, configure the hierarchy at **both checkpoints**, and test both permitted **and** denied cases at each layer. A higher role still never bypasses tenant and ownership constraints.