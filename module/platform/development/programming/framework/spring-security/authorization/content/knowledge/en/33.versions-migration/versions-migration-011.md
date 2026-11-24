# Verifying Role Hierarchy, Role Prefixes, and Default Annotations After Upgrading

> **Scope:** Spring Security Authorization — **Versions and Migration**. This lesson focuses on the risk of altered authorization results when upgrading Spring Security or migrating legacy configurations to `@EnableMethodSecurity`: role inheritance (`RoleHierarchy`), role prefixes (`ROLE_` or custom prefixes), and which annotations are actually enabled by default. The ultimate goal is an **automated ALLOW/DENY decision matrix** before and after the upgrade; never conclude that policy remains intact simply because the app compiles and boots.

## 1. Why Can a Version Upgrade Expose Permissions?

An application may still boot and controllers may still return JSON, yet authorization outcomes change:

- `ROLE_ADMIN` previously inherited `ROLE_MANAGER` and `ROLE_USER`; after a version upgrade, the custom `RoleHierarchy` is no longer wired into an authorization manager, causing admins to be denied (losing legitimate access).
- The app uses authority `APP_ADMIN`, but `hasRole('ADMIN')` in a new code path defaults to looking up `ROLE_ADMIN`, causing `403`; or inconsistent prefix edits unintentionally open access.
- Old config only enabled `@Secured`; switching to `@EnableMethodSecurity` without disabling pre/post causes dormant `@PreAuthorize` annotations to start taking effect.
- Conversely, switching to `@EnableMethodSecurity` while forgetting `securedEnabled=true` or `jsr250Enabled=true` leaves `@Secured`/`@RolesAllowed` unenforced in method security.
- A class with two different annotation families evaluates them sequentially; or a method-level annotation overrides a class-level annotation of the same family. If migration shifts annotation placement or type, check results can differ from expectations.
- Beans with secured methods bypass the Spring proxy (self-invocation, `new`, or different proxy settings), so annotations are never evaluated even though unit tests invoking Java methods directly still PASS.

**Do not assume every release shares the same APIs and defaults.** Record the exact tuple `Spring Boot version + Spring Security version + Java version`, read the migration guide for the exact version span, and run tests on the **actual classpath** of the upgraded build.

## 2. Concepts That Must Stay Distinct: Role, Authority, Prefix, Hierarchy

An **Authority** is a string inside `Authentication.getAuthorities()`, for example:

~~~text
ROLE_ADMIN
ROLE_MANAGER
ROLE_USER
invoice:read
APP_ADMIN
~~~

A **Role** is a convention commonly used in authorization expressions. Under Spring Security's standard default configuration, `hasRole('ADMIN')` checks authority `ROLE_ADMIN`; `hasAuthority('ROLE_ADMIN')` checks the exact string `ROLE_ADMIN`. `hasAuthority` never adds a prefix automatically.

| Expression / Data | With Default `ROLE_` Prefix | Result |
| --- | --- | --- |
| `hasRole('ADMIN')` | Authority `ROLE_ADMIN` | ALLOW |
| `hasRole('ADMIN')` | Only authority `ADMIN` | DENY |
| `hasAuthority('ADMIN')` | Only authority `ROLE_ADMIN` | DENY |
| `hasAuthority('ROLE_ADMIN')` | Authority `ROLE_ADMIN` | ALLOW |
| `hasAuthority('invoice:read')` | Authority `invoice:read` | ALLOW |
| `hasRole('USER')` | Only `ROLE_ADMIN`, **no hierarchy configured** | DENY |
| `hasRole('USER')` | `ROLE_ADMIN` with hierarchy `ADMIN > USER` properly wired | ALLOW |

`invoice:read` is not automatically a role, and having role `ADMIN` does not automatically grant every permission: only infer what **policy or hierarchy explicitly defines**. Never write tests assuming "ADMIN surely has all permissions."

### What does RoleHierarchy mean?

Example of a role tree:

~~~text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_USER
~~~

`ROLE_ADMIN > ROLE_MANAGER` means holding `ROLE_ADMIN` counts as holding `ROLE_MANAGER` within **authorization components configured to use the hierarchy**. The relation is transitive: `ADMIN` includes `MANAGER` and `USER`. It **does not permanently mutate** the original `Authentication.getAuthorities()` list; evaluators consult *reachable authorities* during decisions. Therefore, not seeing `ROLE_USER` when logging raw authorities does not by itself prove the hierarchy is broken.

Distinguish clearly:

- **Origin:** which authorities does the token/session/`UserDetailsService` supply?
- **Conversion:** how are `roles`/`scope` claims mapped into `GrantedAuthority`s?
- **Hierarchy expansion:** does `RoleHierarchy` interpret prefixes and relationships accurately?
- **Enforcement points:** do HTTP rules, `@PreAuthorize`, `@Secured`, and `@RolesAllowed` actually use the hierarchy?

Never conclude from a single test. A configuration might work for `@PreAuthorize` while not being consistently applied to HTTP matchers or custom `AuthorizationManager`s.

## 3. Method Security Defaults and Migration Traps

### 3.1. Old and new configurations differ in critical ways

`@EnableGlobalMethodSecurity` is the legacy configuration; `@EnableMethodSecurity` is the modern approach using `AuthorizationManager`. Spring Boot Starter Security **does not automatically enable method security** merely because the dependency is added.

In the modern configuration:

~~~java
@EnableMethodSecurity
class SecurityConfiguration {
}
~~~

- `prePostEnabled` defaults to **true**: enables `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`.
- `securedEnabled` defaults to **false**: `@Secured` is not processed unless explicitly enabled.
- `jsr250Enabled` defaults to **false**: `@RolesAllowed`, `@PermitAll`, and `@DenyAll` are not processed as JSR-250 unless enabled.
- **Unannotated methods** are not automatically protected by method security. Rely on HTTP deny-by-default or another boundary guard.
- When a method carries **multiple enabled annotations of different families**, checks run sequentially; to permit access, all must pass (AND logic).
- An annotation of the same family on a method can **override** the matching annotation on the class; do not assume class and method annotations of the same family always AND together.

| Configuration | `@PreAuthorize` | `@Secured` | `@RolesAllowed` |
| --- | --- | --- | --- |
| `@EnableMethodSecurity` | Enabled | Disabled | Disabled |
| `@EnableMethodSecurity(securedEnabled=true)` | Enabled | Enabled | Disabled |
| `@EnableMethodSecurity(jsr250Enabled=true)` | Enabled | Disabled | Enabled |
| `@EnableMethodSecurity(securedEnabled=true, jsr250Enabled=true)` | Enabled | Enabled | Enabled |
| `@EnableMethodSecurity(securedEnabled=true, prePostEnabled=false)` | Disabled | Enabled | Disabled |

**Migration example that must preserve legacy intent:** if previously using:

~~~java
@EnableGlobalMethodSecurity(securedEnabled = true)
class LegacyConfig {
}
~~~

and wanting to keep **only** the `@Secured` group without unexpectedly activating pre/post, the new configuration is:

~~~java
@EnableMethodSecurity(securedEnabled = true, prePostEnabled = false)
class NewConfig {
}
~~~

Do not mechanically switch to `@EnableMethodSecurity(securedEnabled=true)` assuming every annotation retains its prior status. Conversely, if the migration intentionally enables pre/post, document the change and test its impact on methods with old, previously unenforced annotations.

### 3.2. Distinguishing syntax and check timing

- `@PreAuthorize("hasRole('USER')")` checks **before** method execution; also supports SpEL over parameters.
- `@PostAuthorize(...)` checks **after** the method returns a result; never use it as the sole gate for operations that already wrote to a DB.
- `@Secured("ROLE_USER")` takes authority/role names in annotation format; in default configurations it usually writes out `ROLE_USER`, unlike `hasRole('USER')` syntax.
- `@RolesAllowed("USER")` is JSR-250; use `jakarta.annotation.security.RolesAllowed` on Spring Boot 3/Spring Security 6, not `javax.annotation.security.RolesAllowed` copied from legacy Java EE apps.
- `@PermitAll` and `@DenyAll` belong to JSR-250 when enabled; `@PermitAll` on a method may not mean bypassing another **active `@PreAuthorize`** or bypassing the HTTP filter chain. Never infer overall outcomes from a single annotation in isolation.
- For custom meta-annotations or annotations on interfaces/classes/methods, test each protected endpoint/service. Spring AOP has self-invocation limits; conflicting annotations across multiple interfaces can cause startup failures.

Upgrading the framework can alter annotation discovery, proxying, interface methods, expression evaluation, or interceptor composition. **A single test with an authorized caller** is insufficient to detect broadened permissions.

## 4. Role Prefixes: Must Stay Consistent from Authentication Source to Evaluator

The prefix is typically `ROLE_`. Components relying on prefixes may include:

1. Mapping from IdP/JWT/groups to `GrantedAuthority`, e.g., claim `admin` -> `ROLE_ADMIN`.
2. `@WithMockUser(roles = "ADMIN")` in tests creates authority `ROLE_ADMIN` by default.
3. Expressions `hasRole('ADMIN')` / `hasAnyRole(...)`.
4. `@Secured` or `@RolesAllowed` annotations.
5. `RoleHierarchy` and custom `AuthorizationManager`s.

**Common migration bug:**

~~~text
Token/Authentication authority: APP_ADMIN
Code after upgrade:           hasRole("ADMIN")
Default role prefix:          ROLE_
Authority it seeks:          ROLE_ADMIN
Result:                      DENY (403)
~~~

Or when someone updates token mapping to `ROLE_ADMIN` while legacy policies still expect `APP_ADMIN`, some APIs succeed while others get blocked.

In Spring Security 6.5, `GrantedAuthorityDefaults` declares a custom prefix. Declare the bean **static** early so method-security configuration sees it:

~~~java
// Snippet illustrating custom prefix config; do not place alongside
// the default ROLE_ config in the runnable example below.
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_");
}
~~~

When choosing `APP_`, adjust mappers, hierarchies, and corresponding expressions/annotations in sync. In tests, use:

~~~java
@WithMockUser(authorities = "APP_ADMIN")
~~~

Do not mistake `@WithMockUser(roles="ADMIN")` for automatically following custom `GrantedAuthorityDefaults`: the test annotation normally builds `ROLE_ADMIN` by its own convention. **Inspect actual raw authorities** instead of guessing.

An illustration for a **separate** custom-prefix and hierarchy config on Spring Security 6.5:

~~~java
// Snippet placed inside @Configuration of an app using APP_.
// Corresponding Spring imports are provided in the project.
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
    handler.setDefaultRolePrefix("APP_"); // API for 6.5 branch configuration
    return handler;
}
~~~

Note when moving to Spring Security 7.x: `setDefaultRolePrefix` on the expression handler is marked deprecated as of 7.0; 7.x documentation points toward `AuthorizationManagerFactory`. **Do not copy a 6.5 snippet verbatim assuming it remains the recommended customization path.** Align code with your exact target version, and test `hasRole`, `@Secured`, JSR-250, and request authorization independently. Legacy API names/classes may still exist while deprecated.

`hasAuthority("APP_ADMIN")` is a literal string, never automatically turned into `ROLE_ADMIN` or `APP_APP_ADMIN`. Do not swap `hasAuthority` for `hasRole` in a mechanical commit without auditing semantics.

## 5. Baseline Collection Checklist Before Upgrading

Before editing dependencies, record **evidence** from the current application. A solid baseline includes:

- Exact Spring Boot/Spring Security versions (from Maven dependency tree or Gradle dependencies), Java runtime, and annotation API versions.
- List of `SecurityFilterChain`s, `@EnableGlobalMethodSecurity`/`@EnableMethodSecurity`, and `@EnableReactiveMethodSecurity` if WebFlux is present.
- Configured beans for `RoleHierarchy`, `GrantedAuthorityDefaults`, `MethodSecurityExpressionHandler`, custom `AuthorizationManager`s, and legacy voters/`AccessDecisionManager`s.
- All `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter`, `@Secured`, `@RolesAllowed`, `@PermitAll`/`@DenyAll`, custom meta-annotations, and their placement on classes/interfaces/methods.
- Authority mappings from JWT/IdP/LDAP/DB. Identify exact raw strings in `Authentication.getAuthorities()`, including prefixes and casing.
- Matrix of who may perform what by function and object, including inherited roles, non-inherited roles, under-privileged callers, anonymous users, and cross-tenant callers.
- Proxy/transaction traits: beans actually managed by Spring; self-invocation that may bypass checks; unannotated methods.
- HTTP and service tests (including negative tests) run on the old version as a comparison baseline.

Document expected ALLOW/DENY **per business requirements**, not merely copying current behavior. If the old system had a vulnerability, "preserving old behavior" must not become the security goal. Every post-upgrade delta must be classified as: **intentional policy fix**, **accidental permission widening**, or **accidental permission tightening**.

## 6. Spring Security 6.5 Sample Configuration with Hierarchy and Three Annotation Families

Example runs in a **Spring Boot 3.x / Spring Security 6.5.x / Java 17** project; do not apply these imports/APIs verbatim to 7.x without checking the migration guide. It intentionally uses the default `ROLE_` prefix to establish a clear baseline before trying custom prefixes.

### 6.1. Maven dependencies

Project already has Spring Boot parent/BOM managing versions:

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

No HTTP controller is needed for method-security tests. If the real app exposes a web API, test `SecurityFilterChain` and HTTP statuses separately. `spring-security-test` provides `@WithMockUser`; Spring Boot starter test provides JUnit Jupiter/Spring Test.

### 6.2. Complete configuration

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

    // Spring Security 6.5: wire hierarchy into pre/post expression handler.
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

`ROLE_ADMIN > ROLE_MANAGER` and `ROLE_MANAGER > ROLE_USER` are two directed edges enabling **transitive** inheritance. Publishing a `RoleHierarchy` bean alone is no reason to skip checking each authorization manager; the example explicitly configures the expression handler for `@PreAuthorize`, and tests verify real outcomes. `@EnableMethodSecurity(securedEnabled=true,jsr250Enabled=true)` enables **all three** annotation families, preventing tests from "PASSING" because a mechanism is turned off.

### 6.3. Protected service

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

`PermissionService` is registered via `@Bean` in `UpgradeSecurityConfig` so Spring can create a method-security proxy. `notAnnotated()` intentionally demonstrates that **no annotation means no automatic method-security rule**; a real application must never treat this as a safe public endpoint merely because `@EnableMethodSecurity` is present.

### 6.4. Pre/post-upgrade authorization tests with JUnit

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
        // Observes real behavior; do not treat this as safe authorization.
        assertEquals("unguarded", service.notAnnotated());
    }
}
~~~

Run from the corresponding Spring Boot 3 Maven project directory:

~~~bash
./mvnw -Dtest=UpgradeMethodSecurityTest test
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd -Dtest=UpgradeMethodSecurityTest test
~~~

**Expected when properly configured on 6.5:** eight tests PASS; when run on a new version, any FAIL indicates an authorization behavior to investigate. Because there is no `System.out.println`, there is no fixed program stdout; Maven displays test/build status per the plugin version. This example verifies **method security inside a real Spring context**, without mocking the authorization evaluator itself.

If a `@Secured`/JSR-250 test unexpectedly denies `ROLE_ADMIN` while `@PreAuthorize` allows it, check **whether the hierarchy is used by each interceptor** in the running version. Do not "fix the test to PASS" by adding `ROLE_USER` onto the ADMIN user and masking a regression; in version-upgrade tests, keep input limited to `ROLE_ADMIN` alone so the hierarchy is genuinely exercised.

### 6.5. Expected matrix for the sample configuration

| Principal with Actual Authorities | `read()`/`hasRole(USER)` | `manage()`/`hasRole(MANAGER)` | `exportInvoice()` |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | ALLOW via hierarchy | ALLOW via hierarchy | DENY |
| `ROLE_MANAGER` | ALLOW via hierarchy | ALLOW | DENY |
| `ROLE_USER` | ALLOW | DENY | DENY |
| `ADMIN` (unprefixed) | DENY | DENY | DENY |
| `invoice:export` | DENY | DENY | ALLOW |
| No valid Authentication | DENY | DENY | DENY |

This is an **illustrative business baseline** for the example, not a default policy for every enterprise. Whatever permissions role ADMIN has beyond the hierarchy must be explicitly defined, never granted via `permitAll()` based on the role name.

## 7. Standalone Java 17 Program Illustrating Prefix and Transitive Hierarchy

To verify directly with `javac`/`java` without Spring, the following simulates the **concept** of reachable authorities and prefixes. It is **not a replica of Spring Security internals**; the `@SpringJUnitConfig` test above tests the real framework.

Create a file **`RoleContractDemo.java`**:

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

Run:

~~~bash
javac --release 17 RoleContractDemo.java
java RoleContractDemo
~~~

**Exact stdout:**

~~~text
ADMIN inherited USER: true
Without hierarchy USER: false
Raw ADMIN equals ROLE_ADMIN: false
APP_ADMIN with APP_ prefix: true
~~~

`reachable` expands transitively until reaching a fixed point, even across multi-level hierarchies. It does not mutate `rawAdmin`, mirroring the idea that raw authorities in Authentication and derived authorities during evaluation are two separate concepts. Still, **never use this function in place of a Spring authorization manager** in production; rules around anonymous callers, expressions, method proxies, JSR-250, and framework errors require integration testing.

## 8. Verifying Default Annotations When Changing Configuration

### Enable the exact annotation groups

If the codebase uses all three groups, declare it explicitly:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

If only the legacy `@Secured` group was used and you want to preserve exact pre-upgrade behavior:

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true,
    jsr250Enabled = false
)
~~~

For `@PreAuthorize`, `prePostEnabled=false` causes that annotation **not to be intercepted** by the default pre/post group; enable it if pre/post is needed. For `@Secured` and `@RolesAllowed`, failing to enable them means they **create no method gate via that mechanism**. This is especially dangerous when tests only assert "authorized user succeeds" without asserting "unauthorized user is blocked."

### Evaluation order and class-level annotations

~~~java
@PreAuthorize("hasRole('USER')")
public class ExampleService {

    // Same-type @PreAuthorize on the method can override
    // class-level @PreAuthorize; it does not automatically AND.
    @PreAuthorize("hasRole('ADMIN')")
    public String adminAction() {
        return "ok";
    }
}
~~~

This is an illustrative snippet, not a class from the sample project. If a business rule requires both `USER` and `ADMIN`, state it explicitly in a single expression, or enforce it via business policy instead of expecting inheritance to automatically AND them.

Conversely, when a method carries both `@Secured("ROLE_USER")` and `@PreAuthorize("hasAuthority('invoice:export')")`, and **both groups are enabled**, checks apply sequentially (both must be satisfied). Interceptor ordering can affect exceptions or transactions, though you must never rely on ordering to bypass permissions.

### JSR-250 and the Jakarta namespace

In Spring Boot 3, imports should be:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

If migrating from Java EE/Boot 2 still imports `javax.annotation.security.RolesAllowed`, update to `jakarta.annotation.security.RolesAllowed` per supported dependencies. Do not assume that compiling with a legacy library guarantees the newer Spring Security version recognizes that annotation.

### Reactive vs. Servlet differences

WebFlux apps use `@EnableReactiveMethodSecurity`, `Mono`/`Flux`, and Reactor Context; Servlet apps use `@EnableMethodSecurity` and standard method proxies. Do not copy a synchronous `@SpringJUnitConfig` example into a reactive app and assume authorization is verified upon subscription. For reactive, add `StepVerifier` and test `ReactiveSecurityContextHolder` propagation.

## 9. Regression Matrix to Run on a Real Codebase

The matrix should be encoded as tests and run with the same fixtures on both **before** and **after** versions:

| Case | Raw Authority | Rule to Check | Expected |
| --- | --- | --- | --- |
| 1. Direct role | `ROLE_USER` | `hasRole('USER')` | ALLOW |
| 2. Single-hop inheritance | `ROLE_MANAGER` | `hasRole('USER')` | ALLOW if hierarchy configured |
| 3. Transitive inheritance | `ROLE_ADMIN` | `hasRole('USER')` | ALLOW if full hierarchy configured |
| 4. No reverse inference | `ROLE_USER` | `hasRole('ADMIN')` | DENY |
| 5. Wrong prefix | `ADMIN` | `hasRole('ADMIN')` with `ROLE_` prefix | DENY |
| 6. Custom prefix | `APP_ADMIN` | `hasRole('ADMIN')` with `APP_` | ALLOW |
| 7. Literal authority | `invoice:read` | `hasAuthority('invoice:read')` | ALLOW |
| 8. Role does not imply permission | `ROLE_ADMIN` | `hasAuthority('invoice:read')` | DENY unless granted by hierarchy/policy |
| 9. `@Secured` | `ROLE_USER` | `@Secured("ROLE_USER")` | ALLOW if enabled |
| 10. `@Secured` negative | Lacks `ROLE_USER` | Same method | DENY if enabled |
| 11. JSR-250 | `ROLE_USER` | `@RolesAllowed("USER")` | ALLOW if enabled and prefix matches |
| 12. JSR-250 negative | Lacks `ROLE_USER` | Same method | DENY if enabled |
| 13. Pre/post default | User lacks permission | `@PreAuthorize(...)` | DENY if `prePostEnabled` |
| 14. Unannotated method | Any user | No method gate | Must have another boundary guard if sensitive |
| 15. Different class/method | Different roles | Annotations on class and method | Verify precedence per expected rules |
| 16. Proxy bypass | Caller via `this.method()` | Internal protected method | Detect risk and fix call path |
| 17. HTTP API | Under-privileged user | `SecurityFilterChain` | Appropriate `401`/`403`, zero data leaked |
| 18. Object/tenant | User has role but wrong owner | Service/domain policy | DENY independent of hierarchy |

Expectations depend on **business policy** and configuration. This table frames the questions to test; never auto-convert everything to ALLOW just to achieve green tests.

Beyond standard cases, also check:

- `@WithMockUser(roles="ADMIN")` vs. `@WithMockUser(authorities="ROLE_ADMIN")` vs. `@WithMockUser(authorities="ADMIN")`.
- Prefixes are exact, case-sensitive strings; never silently rewrite tokens.
- Whether two annotations on a class/interface conflict and cause startup errors.
- `final`/`private` methods, self-invocation, interface proxies vs. class proxies; tests invoke the **real bean** rather than `new`.
- Whether Spring Expression Language parameters (`#p0`, `#id`) still resolve properly when compiler flags or versions change.
- Are HTTP and method rules consistent? Role hierarchy in HTTP must not be assumed to match method security without testing.
- Are permission caches, JWT authority mappings, custom authentication converters, IdP groups, and OAuth2 scope mappings (often `SCOPE_`) affected?

## 10. Controlled Version Upgrade Workflow

**Step 1 — Capture baseline:** lock current Maven/Gradle dependencies and build; export reports on versions, configurations, annotation groups, hierarchies, and raw authorities from test fixtures. Save the baseline decision matrix.

**Step 2 — Declare semantic diff:** before editing, describe exact rules expected to change. For example, "`@PreAuthorize` was previously disabled and is now enabled" is a policy change needing business-owner sign-off. Never bundle unintended security policy shifts into a PR labeled solely "upgrade dependency."

**Step 3 — Update APIs intentionally:** migrate `@EnableGlobalMethodSecurity` to `@EnableMethodSecurity` with explicit flags. Switch JSR imports to Jakarta when upgrading to Boot 3. Verify role hierarchy beans/handlers/factories match the version. On Spring Security 7.x, audit `AuthorizationManagerFactory` and deprecated prefix customization APIs; never treat a 6.5 snippet as the default answer for 7.x.

**Step 4 — Run tests at method and HTTP layers:** protect real records and services, test both allow and deny, and include a case where ADMIN carries only `ROLE_ADMIN` to prove hierarchy. If JUnit passes only because `ROLE_USER` was manually assigned too, the test fails to prove inheritance.

**Step 5 — Compare decisions:** capture a request/fixture dataset (without secrets), run old and new versions in test environments, and output `before/after` by principal/action/resource. Inspect every `DENY -> ALLOW` for privilege escalation risk; for `ALLOW -> DENY`, confirm legitimate workflows are not blocked.

**Step 6 — Canary and observe:** roll out to stable cohorts, monitor `403`s by route/role/cohort, business errors, authorization latency, `AuthorizationDeniedEvent`s where appropriate, and active policy/config versions. Never log raw JWTs or sensitive data.

**Step 7 — Roll back if mismatched:** revert to the approved compatible artifact/config build. Never revert only the dependency while leaving the new version's prefix/hierarchy mappings behind. Verify the whole cluster and re-run the matrix; if the old version contained a known vulnerability, apply a hotfix/deny-safe policy instead of automatically reopening dangerous permissions.

### "Definition of Done" for authorization upgrades

- Exact target version, dependency lock/BOM, and migration notes documented.
- Explicitly documented which annotations were enabled/disabled by default **before and after**.
- `RoleHierarchy` works transitively from a single root authority, including both HTTP and method layers if both are used.
- Role prefixes are consistent across IdP/JWT mappers, `@WithMockUser`, `hasRole`, `@Secured`, `@RolesAllowed`, and custom managers.
- Negative tests via real Spring proxies all PASS, including owner/tenant and anonymous cases.
- Zero unapproved `DENY -> ALLOW` shifts; legitimate 403s distinguished from regressions.
- Canary results recorded and rollback plan verified.

## 11. Troubleshooting Common Errors

| Post-Upgrade Symptom | Likely Cause | Diagnosis and Fix |
| --- | --- | --- |
| Admin gets 403 on `hasRole('USER')` | Hierarchy not wired into handler/manager | Test `ROLE_ADMIN` alone; check `RoleHierarchy` and evaluator for exact version |
| `hasRole('ADMIN')` denies `ADMIN` | Default `ROLE_` prefix | Check raw authorities and align mappers/prefixes |
| Custom prefix works on methods but fails on HTTP | HTTP authorization manager configured differently | Test request-level separately; use version-appropriate factory/custom manager |
| `@Secured` suddenly stops blocking | Forgot `securedEnabled=true` | Enable explicitly and include negative tests verifying denial |
| `@RolesAllowed` stops blocking | Forgot `jsr250Enabled=true` or legacy namespace import | Enable JSR-250 and use Jakarta matching Boot version |
| `@PreAuthorize` unexpectedly blocks requests | `@EnableMethodSecurity` enables pre/post by default | Confirm whether intentional policy change; if keeping old behavior, set `prePostEnabled=false` |
| Multiple annotations tighten access | Sequential interceptors | Verify AND semantics and class/method/interface annotations |
| Tests pass even when annotations are disabled | Tested only authorized users | Add negative tests with under-privileged users |
| Annotated method is not blocked | Called via `new`, self-invocation, proxy/`final` method | Test Spring bean injected via proxy; split services if needed |
| Custom prefix breaks `@WithMockUser(roles=...)` | Mock `roles` normally generates `ROLE_*` | Use `authorities` matching the actual prefix |
| Major upgrade causes compile errors | API/package changes, deprecations | Read exact migration guide; update configuration for target version |
| User with valid role reads another user's object | Checked only role, missing object policy | Keep owner/tenant checks independent of hierarchy |

## 12. End-of-Lesson Assessment Checklist

- [ ] Understand that a role in an expression differs from an authority string in `Authentication`.
- [ ] Distinguish `hasRole`/`hasAuthority` and understand the `ROLE_` default.
- [ ] Understand `ROLE_ADMIN > ROLE_MANAGER > ROLE_USER` is a transitive relation, not mutating raw authorities.
- [ ] Verified role hierarchy across **every interceptor type actually in use**.
- [ ] Know `@EnableMethodSecurity` defaults: `prePostEnabled=true`, `securedEnabled=false`, `jsr250Enabled=false`.
- [ ] Know that migrating from `@EnableGlobalMethodSecurity` can change which annotation groups are active.
- [ ] Know to import `jakarta.annotation.security.RolesAllowed` for Boot 3 instead of copying `javax`.
- [ ] Tested `@WithMockUser(roles=...)` and `authorities=...` separately, including negative tests.
- [ ] All method-protection tests invoke beans through Spring proxies.
- [ ] Ran the before/after comparison matrix across versions, covering HTTP, services, and owner/tenant.
- [ ] Every ALLOW/DENY change reviewed with a canary/rollback plan.

## Official Documentation

- [Spring Security 6.5 — Authorization Architecture: Role Prefix & Hierarchy](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 7.x — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 7.x — Method Security & migration](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — API GrantedAuthorityDefaults](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/core/GrantedAuthorityDefaults.html)

**Extended exercise:** convert the sample project to policy `APP_ADMIN > APP_MANAGER > APP_USER` with prefix `APP_` and run the same matrix on your active Spring Security version. Then intentionally test a configuration missing `jsr250Enabled` and one missing the hierarchy handler to observe negative or inheritance tests failing. Report exact ALLOW/DENY changes, pinpointing whether the cause was authority mapping, prefix, hierarchy, or annotation enablement.