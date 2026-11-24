# Testing meta-annotations, role hierarchy, and PermissionEvaluator in Spring Security

## 1. Objectives and context

At the service layer, checking access is not limited to confirming a user is logged in. A method may be protected by a **meta-annotation** containing a @PreAuthorize rule, accept a role via a **role hierarchy**, or decide access per object using a **PermissionEvaluator**. This lesson focuses on writing tests to prove both **allowed** and **denied** cases, while catching situations where security configuration is not actually applied.

After this lesson, you will be able to:

1. Write JUnit 5 tests for Spring-managed services using @EnableMethodSecurity and @PreAuthorize.
2. Test security meta-annotations in **application code**; while reusing @WithMockUser meta-annotations for **test fixtures**.
3. Prove that privileges inherit from ROLE_ADMIN down to ROLE_MANAGER and then ROLE_VIEWER in a role hierarchy, and prove the reverse direction is not granted.
4. Test PermissionEvaluator by resource, identifier, and action; distinguish the two overloads of hasPermission.
5. Recognize "false-green" tests caused by calling an object directly without passing through a proxy or only writing allowed scenarios.

**Scope:** method security for Spring MVC/Servlet or synchronous services, Java 17+, Spring Security 6.x/7.x. This lesson does not replace HTTP endpoint testing and does not apply verbatim to reactive method security.

## 2. Authorization decision model

Spring Security enforces @PreAuthorize when a method is invoked through the **Spring AOP proxy** of a managed bean. It retrieves Authentication from SecurityContext, evaluates the SpEL expression, and invokes the method body only if the condition passes. When denied, direct service tests through a proxy typically receive AccessDeniedException (or a subclass); do not equate this Java exception with HTTP 403, because 403 is produced by the web request handling layer.

~~~text
JUnit 5 + Spring Test
       │
       ├── @WithMockUser / @WithMockAdmin
       │        └── populate Authentication into SecurityContext
       │
       └── call service bean through Spring AOP proxy
                     │
                     └── @PreAuthorize / meta-annotation
                               │
                               ├── hasAuthority(...) → matching authority
                               ├── hasRole(...)      → role + role hierarchy
                               └── hasPermission(...) → PermissionEvaluator
                                         │
                                    allow / deny
~~~

The three mechanisms address different problems:

| Mechanism | What to test | Business question |
| --- | --- | --- |
| Security meta-annotation | Is the custom annotation recognized and enforced? | Can only users with approval authority approve invoices? |
| Role hierarchy | Does a higher role inherit lower roles without inheriting in reverse? | Can ADMIN view features meant for VIEWER? |
| PermissionEvaluator | Does the decision depend on the right user, resource, and action? | Can Alice read document 42, while not being allowed to read 43? |

**Distinguish the two types of meta-annotations:** An annotation carrying @PreAuthorize (such as @CanApprove) protects **production code**. An annotation carrying @WithMockUser (such as @WithMockAdmin) only sets up **Authentication in tests**. Passing a test with a privileged user does not prove protection is active on the service; there must be at least one test expecting denial.

## 3. Setting up the method testing environment

In a Spring Boot 3.x / Java 17+ project using Gradle, the following dependencies are required (Spring Boot manages compatible versions):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

If the project already includes these dependencies, do not add them again. Spring Security Test integrates with Spring TestContext via WithSecurityContextTestExecutionListener. @SpringJUnitConfig creates an ApplicationContext for JUnit Jupiter, automatically registers default TestExecutionListeners, and prepares and cleans up SecurityContext for each test. **@WithMockUser does not need real accounts**; if code expects a principal of an application-specific UserDetails type, use @WithUserDetails with a real UserDetailsService, or create a custom @WithSecurityContext.

Create a file **src/test/java/demo/authorization/MethodSecurityLessonTest.java** with the complete contents below. The Spring configuration for the test is declared right inside the class, so no running web application is needed. The example uses roles ADMIN > MANAGER > VIEWER and an intentionally simple document read rule for illustration; in a real application, replace it with a trusted authorization source.

~~~java
package demo.authorization;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.Serializable;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MethodSecurityLessonTest.SecurityConfig.class)
class MethodSecurityLessonTest {

    // Application meta-annotation: real rule on methods.
    @Target({ElementType.METHOD, ElementType.TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @PreAuthorize("hasAuthority('invoice:approve')")
    public @interface CanApprove {}

    // Test meta-annotation: a reusable mock identity.
    @Target({ElementType.METHOD, ElementType.TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @WithMockUser(username = "chief", roles = "ADMIN")
    public @interface WithMockAdmin {}

    public static class LessonService {

        @CanApprove
        public String approveInvoice() {
            return "approved";
        }

        @PreAuthorize("hasRole('VIEWER')")
        public String viewReport() {
            return "report";
        }

        // #p0 is the first parameter, independent of the -parameters compiler flag.
        @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
        public String readDocument(Long id) {
            return "document:" + id;
        }
    }

    // Only Alice can read Document 42. This is a mock policy for testing.
    static class DemoDocumentPermissionEvaluator implements PermissionEvaluator {

        @Override
        public boolean hasPermission(
                Authentication auth, Object domainObject, Object permission) {
            // This lesson tests the id + type variant; safely deny
            // the variant that receives a domain object directly.
            return false;
        }

        @Override
        public boolean hasPermission(
                Authentication auth, Serializable id, String type, Object permission) {
            return auth != null
                    && auth.isAuthenticated()
                    && "alice".equals(auth.getName())
                    && Long.valueOf(42L).equals(id)
                    && "Document".equals(type)
                    && "read".equals(permission);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class SecurityConfig {

        @Bean
        LessonService lessonService() {
            return new LessonService();
        }

        // static so the expression handler bean is published early
        // before method security configurations are initialized.
        @Bean
        static MethodSecurityExpressionHandler methodSecurityExpressionHandler() {
            var handler = new DefaultMethodSecurityExpressionHandler();
            handler.setRoleHierarchy(RoleHierarchyImpl.fromHierarchy(
                    "ROLE_ADMIN > ROLE_MANAGER\nROLE_MANAGER > ROLE_VIEWER"));
            handler.setPermissionEvaluator(
                    new DemoDocumentPermissionEvaluator());
            return handler;
        }
    }

    @Autowired
    LessonService service; // Bean wrapped by Spring with a security proxy.

    @Test
    @WithMockUser(authorities = "invoice:approve")
    void metaAnnotationAllowsExpectedAuthority() {
        assertEquals("approved", service.approveInvoice());
    }

    @Test
    @WithMockAdmin
    void metaAnnotationStillDeniesAdminWithoutApproveAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> service.approveInvoice());
    }

    @Test
    @WithMockAdmin
    void adminInheritsViewerRole() {
        assertEquals("report", service.viewReport());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCanViewReportDirectly() {
        assertEquals("report", service.viewReport());
    }

    @Test
    @WithMockUser(roles = "GUEST")
    void guestDoesNotInheritViewerRole() {
        assertThrows(AccessDeniedException.class,
                () -> service.viewReport());
    }

    @Test
    @WithMockUser(username = "alice")
    void permissionEvaluatorAllowsMatchingUserAndDocument() {
        assertEquals("document:42", service.readDocument(42L));
    }

    @Test
    @WithMockUser(username = "bob")
    void permissionEvaluatorDeniesOtherUser() {
        assertThrows(AccessDeniedException.class,
                () -> service.readDocument(42L));
    }

    @Test
    @WithMockUser(username = "alice")
    void permissionEvaluatorDeniesOtherDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.readDocument(43L));
    }
}
~~~

**Run:** At the root of a Gradle project with wrapper, run:

~~~bash
./gradlew test --tests "demo.authorization.MethodSecurityLessonTest"
~~~

On Windows/PowerShell use the equivalent command **.\gradlew.bat test --tests "demo.authorization.MethodSecurityLessonTest"**. Expected: **8 tests pass**, with no stdout printed by the test code itself. Counts and statuses are reported by JUnit/Gradle; do not copy a fixed log snippet verbatim because logs depend on runner versions and settings.

If using a Spring Boot 4 / Spring Security 7 project, apply the test dependencies matching your project; the example here assumes only a Boot 3.x project already configured for JUnit Jupiter tests. The method security testing concept is the same, though framework and starter versions should be checked when migrating projects.

## 4. Interpreting and proving results per mechanism

### 4.1. Security meta-annotations

@CanApprove combines @PreAuthorize with the policy hasAuthority('invoice:approve'). Spring Security scans meta-annotations so calling **service.approveInvoice()** through the proxy must be governed just as if @PreAuthorize were placed directly.

- **Allow path:** @WithMockUser(authorities = "invoice:approve") grants the right GrantedAuthority, so approveInvoice returns the string **approved**.
- **Deny path:** @WithMockAdmin creates user chief with ROLE_ADMIN, yet the current hierarchy configuration does not imply invoice:approve from ROLE_ADMIN; therefore the call must throw AccessDeniedException.
- **Significance:** If the denial test unexpectedly passes, suspect that @EnableMethodSecurity is inactive, the method is unproxied, the annotation has the wrong target/retention, or the test invoked a manually instantiated object with new.

@WithMockAdmin is a **test meta-annotation**: it wraps @WithMockUser(username = "chief", roles = "ADMIN") to avoid repeating fixture data. You can wrap @WithUserDetails or @WithSecurityContext inside an annotation as needed. Avoid confusing test annotations with production policies; they act at two different stages.

**Checking annotations:** @Retention(RUNTIME) is required so the framework sees metadata at runtime. @Target must include METHOD/TYPE matching where it is placed. If a custom meta-annotation takes parameters for SpEL interpolation, verify quotes and the interpolated expression; do not assume every custom annotation is automatically understood.

### 4.2. Role hierarchy

Roles here form a chain:

~~~text
ROLE_ADMIN ⇒ ROLE_MANAGER ⇒ ROLE_VIEWER
~~~

The symbol ⇒ means the role on the left **implies** the role on the right when the authorization evaluator computes reachable authorities; it does not require the initial Authentication to store the lower authorities explicitly.

- chief with roles="ADMIN" is granted only ROLE_ADMIN by @WithMockUser, yet passes hasRole('VIEWER') because the handler has RoleHierarchyImpl wired in.
- VIEWER passes the condition directly without inheritance.
- GUEST is denied because it is not in the inheritance chain. Likewise, VIEWER cannot imply MANAGER or ADMIN.

With default configuration, **hasRole('VIEWER')** checks for **ROLE_VIEWER**. In @WithMockUser, **roles = "ADMIN"** automatically adds ROLE_, while **authorities = "invoice:approve"** keeps the exact string; do not write roles="ROLE_ADMIN" and do not assume every authority is a role.

**Why not just declare a RoleHierarchy bean?** @PreAuthorize expressions are evaluated by MethodSecurityExpressionHandler; the example explicitly attaches the role hierarchy to DefaultMethodSecurityExpressionHandler so results are testable. Other authorization mechanisms, such as @Secured and JSR-250, have their own integration mechanisms; test the exact annotation you use. Do not infer from hasRole working in an HTTP filter that the method-layer configuration is already right.

**To raise difficulty:** add tests for MANAGER→VIEWER allowed, VIEWER→MANAGER denied, and a multi-branch hierarchy. If you modify the role chain, update both allowed and denied tests to avoid accidentally broadening privileges.

### 4.3. PermissionEvaluator

The expression **hasPermission(#p0, 'Document', 'read')** passes to PermissionEvaluator: the caller's Authentication, the id in the first parameter, the resource type name **Document**, and the action **read**.

The interface has two overloads serving two expression forms:

| SpEL | Executed overload | Data to verify |
| --- | --- | --- |
| hasPermission(#document, 'read') | hasPermission(Authentication, Object, Object) | Domain object and permission |
| hasPermission(#p0, 'Document', 'read') | hasPermission(Authentication, Serializable, String, Object) | Id, object type, and permission |

In the sample code, the domain-object overload intentionally returns **false**. Never return **true** by default or overlook this overload when the application uses it. In a real application, both overloads must align on the same ownership/ACL policy, including when the resource is null, id does not exist, permission is invalid, or the user lacks access.

**The three resource tests** in the example guard three separate axes:

1. Alice + Document#42 + read ⇒ allowed.
2. Bob + Document#42 + read ⇒ denied, despite identical id and action.
3. Alice + Document#43 + read ⇒ denied, despite identical user and action.

To be more thorough in a real system, add tests switching **read→write**, switching type **Document→Report**, nonexistent id, null, access after revocation, and delegated user permissions. Maintain a **default-deny** policy for unrecognized cases.

**Why is mocking Authentication alone insufficient?** PermissionEvaluator decides access based on domain data. @WithMockUser only creates mock identity/authorities, not permission records in a database. For evaluator unit tests, use controllable mock data and assert valid/invalid combinations; for integration tests, use repositories/fixtures verifying real owner/tenant/ACL relationships. Avoid test fixtures that depend on wall-clock time, live accounts, or real environment data.

## 5. Test matrix and acceptance criteria

| Code | Input condition | Call | Outcome |
| --- | --- | --- | --- |
| M1 | authority invoice:approve | approveInvoice() | Allowed |
| M2 | ROLE_ADMIN, without invoice:approve | approveInvoice() | Denied |
| H1 | ROLE_ADMIN | viewReport() | Allowed via hierarchy |
| H2 | ROLE_VIEWER | viewReport() | Allowed directly |
| H3 | ROLE_GUEST | viewReport() | Denied |
| P1 | alice, id=42 | readDocument(42) | Allowed |
| P2 | bob, id=42 | readDocument(42) | Denied |
| P3 | alice, id=43 | readDocument(43) | Denied |

For each security rule, include at minimum one **allow** test and one **deny** test. Tests that check only the returned string when allowed cannot detect that the interceptor was turned off. One independent diagnostic check is verifying **AopUtils.isAopProxy(service)**; in this lesson, the denial tests are stronger evidence because they must fail if LessonService is invoked directly without protection.

You can add separate unit tests for DemoDocumentPermissionEvaluator to assert the policy independent of a Spring context, then use the service tests above to prove the handler wiring actually calls the evaluator. Both test levels complement each other: a correct privilege algorithm is not enough if wiring is missing, and correct wiring is not enough if the privilege algorithm is flawed.

## 6. Common pitfalls and fixes

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| Underprivileged user can still call service | Missing @EnableMethodSecurity; called via new; self-invocation via this; proxy not applied | Obtain bean from ApplicationContext, add deny tests, inspect AOP proxy |
| ADMIN fails VIEWER check | RoleHierarchy not attached to right expression handler, wrong ROLE_ prefix, test config differs | Check ROLE_ADMIN > ROLE_VIEWER and MethodSecurityExpressionHandler bean |
| hasPermission always denies | setPermissionEvaluator omitted; no matching evaluator by default; wrong overload invoked | Set breakpoints in both overloads; check id/type/permission |
| @WithMockUser test passes but production fails on principal | Mock principal is standard User, not custom type | Use @WithUserDetails or @WithSecurityContext matching real principal |
| Deny test reports wrong exception type | Mixing HTTP context with service call; or no Authentication | Clarify whether call goes through proxy or MockMvc; test at right layer |
| Results vary by execution order | Tests mutate SecurityContext or shared permission data without cleanup | Use Spring Test listener, independent fixtures, reset mocks/DB |
| Misunderstanding roles vs. authorities | roles auto-adds ROLE_, authorities preserves exact string | Assert authorities produced by test annotation directly |
| Service test runs without hitting controller | Testing only method layer, not HTTP chain | Add separate MockMvc integration test if mapping and HTTP status need verification |

**Warning about self-invocation:** If a method inside the same bean calls **this.securedMethod()**, the call may bypass the AOP proxy and skip the target method's annotation. Tests calling through the injected bean accurately reflect method security; service design should avoid internal calls bypassing proxies or adopt an appropriate architecture.

**Warning about HTTP tests:** @WithMockUser in Spring Test binds SecurityContext to the test thread. It suits bean calls and many MockMvc tests configured with Spring Security; it does not automatically transfer identity to a real HTTP server running on another thread. For end-to-end tests, authenticate the HTTP request itself.

**Warning about versions and APIs:** @EnableMethodSecurity is the modern configuration replacing @EnableGlobalMethodSecurity. If using @Secured/JSR-250, enable their corresponding modes; do not assume @PreAuthorize evaluation rules apply by default to every annotation. When using another Spring Security version, check that version's docs on RoleHierarchy and handlers.

## 7. Extended practice exercises

Modify the test suite in the following order; add at least one denial test in each step before considering the feature complete:

1. Add method **exportReport()** requiring MANAGER; verify ADMIN and MANAGER are allowed and VIEWER is denied.
2. Create meta-annotation **@CanReadDocument** wrapping hasPermission with the id parameter; verify the rule triggers just as when @PreAuthorize is placed directly.
3. Extend the evaluator so documents have **owner**, **tenantId**, and a set of **allowedActions**; test same-tenant user, cross-tenant user, owner, non-owner, and ungranted write permission. Prefer deterministic fixtures over live data connections.
4. Write a test intentionally calling **new LessonService().viewReport()** and observe why it is unprotected; then keep primary tests using the proxied bean.
5. Add separate endpoint tests with MockMvc if the service is invoked through a controller, comparing HTTP-layer blocking with method-layer blocking.

**Self-assessment:** Have you proved the rules execute through the proxy? Do you have both allow and deny cases for meta-annotations, hierarchy, and PermissionEvaluator? Are test fixtures isolated? If you change one authority/role/id, do tests fail as predicted? Only when you can answer yes to all of these does the suite genuinely protect authorization changes.

## 8. Reference documentation

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Authorization Architecture / Hierarchical Roles: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — PermissionEvaluator API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html
