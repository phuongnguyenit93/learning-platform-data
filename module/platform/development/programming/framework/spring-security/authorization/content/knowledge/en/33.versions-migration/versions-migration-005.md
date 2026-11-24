# Migrating @EnableGlobalMethodSecurity to @EnableMethodSecurity

## 1. Context and Objectives

In older Spring Security applications, method-level authorization was typically enabled with `@EnableGlobalMethodSecurity`. In the modern method security architecture, Spring Security recommends `@EnableMethodSecurity`. This is a change in **how method protection is activated and executed**, not merely an annotation rename. The flags enabling each annotation family, custom expression configurations, and authorization enforcement mechanics all require review.

This lesson focuses on migrating a Spring Boot/Spring Security application using legacy method security to the new configuration without **inadvertently over-granting permissions or breaking valid functionality**. Examples target Java 17+, Spring Boot 3.x, and Spring Security 6.x. If the application still runs on Boot 2.x/Security 5.x, verify your running version; changing the annotation alone does not complete a Spring Framework/Jakarta upgrade.

Expected outcomes:

- Recognize default differences for `prePostEnabled`, `securedEnabled`, and `jsr250Enabled`.
- Write an `@EnableMethodSecurity` configuration matching your existing policy.
- Preserve exact semantics of `@PreAuthorize`, `@PostAuthorize`, `@Secured`, and `@RolesAllowed`.
- Know when to migrate extensions from `GlobalMethodSecurityConfiguration` and legacy voters/metadata to `AuthorizationManager` or modern method-security beans.
- Test directly against Spring-managed beans for both allowed and denied cases.
- Identify pitfalls around proxies, self-invocation, role prefixes, SpEL parameters, transaction ordering, and data authorization scope.

## 2. Comparing the Two Annotations

The legacy configuration typically looks like:

```java
import org.springframework.security.config.annotation.method.configuration
        .EnableGlobalMethodSecurity;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableGlobalMethodSecurity(
        prePostEnabled = true,
        securedEnabled = true,
        jsr250Enabled = true
)
public class LegacyMethodSecurityConfig {
}
```

In the corresponding application with the new configuration:

```java
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableMethodSecurity(
        prePostEnabled = true,
        securedEnabled = true,
        jsr250Enabled = true
)
public class MethodSecurityConfig {
}
```

These two examples share the intent of **enabling the same three annotation families**, yet customized security logic and business regressions still must be verified. If the old configuration enabled different flags, **do not copy the example mechanically**.

| Item | Legacy `@EnableGlobalMethodSecurity` | Modern `@EnableMethodSecurity` | Migration Impact |
| --- | --- | --- | --- |
| Default `prePostEnabled` | `false` | **`true`** | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` annotations may begin executing even if not previously enabled |
| Default `securedEnabled` | `false` | `false` | Must declare `securedEnabled = true` if using `@Secured` |
| Default `jsr250Enabled` | `false` | `false` | Must declare `jsr250Enabled = true` if using JSR-250 `@RolesAllowed`, `@PermitAll`, `@DenyAll` |
| Underlying mechanism | Typically tied to legacy method security components like metadata sources, voters, and `AccessDecisionManager` | Based on `AuthorizationManager` and annotation-specific interceptors | Legacy extensions must be evaluated for replacement; do not assume old overrides still take effect |
| Enabling method security | Via legacy configuration | Via new configuration, registering corresponding interceptors | Remove duplicate configurations and test that proxies are actually applied |
| URL/HTTP rules | Separate from method authorization | Remains separate from method authorization | Changing annotations does not replace `SecurityFilterChain`, and vice versa |

**The most easily overlooked difference is that `prePostEnabled` defaults from `false` to `true`.** For example, an old application might only have:

```java
@EnableGlobalMethodSecurity(securedEnabled = true)
```

To preserve approximately the same scope of previously activated annotations when migrating to the new annotation, state it explicitly:

```java
@EnableMethodSecurity(
        prePostEnabled = false,
        securedEnabled = true
)
```

If the intent is to start using `@PreAuthorize` in the same upgrade, you can leave `prePostEnabled = true`, but that is an **intentional policy change** and requires additional tests. Do not let the new default accidentally activate annotations that were previously inactive.

## 3. Annotations and Interpreting Permissions During an Upgrade

### 3.1. `@PreAuthorize` and `@PostAuthorize`

`@PreAuthorize` evaluates an expression **before invoking the method**. For example:

```java
@PreAuthorize("hasAuthority('DOCUMENT_EDIT')")
public void updateDocument(UUID documentId, String content) {
    // Checking per-document permissions is still necessary if policy requires it.
}
```

`@PostAuthorize` evaluates an expression after the method returns; `returnObject` can be referenced in the expression. However, it **does not roll back side effects** that already happened inside the method. Do not use post-checks to guard data writes, message publishing, or external API calls with irreversible effects.

`@PreFilter` and `@PostFilter` filter collection elements by an expression condition when enabled. Because these annotations alter input or returned data, post-upgrade tests must check element counts and scopes, not just HTTP status codes.

Example of a resource-based permission check:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentDto readDocument(UUID documentId) {
    return repository.loadForView(documentId);
}
```

`documentPolicy` is an application-defined bean, not a built-in Spring Security API. It must verify the actor from the authenticated `Authentication`, the actor's permission relationship to the document, and the relevant tenant from an authoritative source. Never trust client-supplied `ownerId`, `role`, or `tenantId` as proof of authorization.

### 3.2. `@Secured`

When the project still uses:

```java
@Secured("ROLE_AUDITOR")
public AuditReport viewAudit() {
    // ...
}
```

The new configuration must set `securedEnabled = true` to activate this check. The string in `@Secured` is usually the literal authority, such as `ROLE_AUDITOR`; do not automatically assume it is transformed like the argument to `hasRole('AUDITOR')`. Verify the actual `GrantedAuthority`s granted to users and the configured role prefix.

If the `securedEnabled` flag is omitted, the annotation may not be enforced by the method-security infrastructure, leaving previously protected methods callable by unauthorized callers. Testing the **insufficient permission** case is mandatory.

### 3.3. `@RolesAllowed` and JSR-250 / Jakarta

Legacy applications may import:

```java
import javax.annotation.security.RolesAllowed;
```

When migrating the application to Spring Boot 3 / Spring Framework 6, the environment uses the Jakarta namespace:

```java
import jakarta.annotation.security.RolesAllowed;
```

Example snippet:

```java
@RolesAllowed("OPERATIONS")
public void executeOperations() {
    // ...
}
```

Requires `@EnableMethodSecurity(jsr250Enabled = true)`. With the common role prefix configuration, `@RolesAllowed("OPERATIONS")` checks the corresponding authority `ROLE_OPERATIONS`. Meanwhile, `@Secured("ROLE_OPERATIONS")` writes out the authority string explicitly. If the application configures a custom prefix, verify actual semantics via tests rather than assuming role strings always match.

`@PermitAll` and `@DenyAll` also belong to the JSR-250 group; when enabling this group, verify that annotations have the intended method scope. The `javax` → `jakarta` namespace migration is part of the platform upgrade, distinct from changing the enabling annotation itself.

### 3.4. Combining multiple annotations on a single method

Avoid stacking multiple authorization annotations from different families onto the same method without clearly establishing how they combine and interceptor ordering. For example, placing `@Secured` alongside `@PreAuthorize` on the same method can trigger multiple separate checks; do not assume they combine with OR just because each annotation lists roles. Consolidate into a single clear policy expression and test the expected outcome.

Sensitive public methods such as transferring ownership, approving documents, downloading files, exporting data, or managing roles require action- and resource-specific policies. A coarse-grained role is a necessary condition in some systems, but rarely sufficient to determine access to a specific document or tenant.

## 4. Controlled Migration Workflow

### Step 1 — Inventory all activation and usage points

In the real project, search for `@EnableGlobalMethodSecurity` and subclasses of `GlobalMethodSecurityConfiguration`. Identify which configuration is authoritative, the current values of `prePostEnabled`, `securedEnabled`, `jsr250Enabled`, proxy settings, and custom beans.

Next, list all annotation types actually in use: `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, `@Secured`, `@RolesAllowed`, `@PermitAll`, and `@DenyAll`. Watch for annotations on interfaces, classes, inherited methods, or project-defined meta-annotations.

Do not draw conclusions solely from an annotation appearing in source code: if the old config did not enable that family, the annotation might not have been enforced. Incorporate this into your test plan to avoid unexpected behavioral shifts.

### Step 2 — Document the current authorization contract

For each group of sensitive methods, record which actors are allowed and which must be denied. At minimum, include an unauthenticated principal, a user with the right role, a user with the wrong role, a user with the role whose target resource belongs to another user/tenant, an in-scope admin, and post-revocation cases.

Also verify permissions for the same action across different tenants/resources. If policy depends on business state (e.g., `DRAFT`, `PUBLISHED`, `LOCKED`), tests must cover both valid and invalid states.

### Step 3 — Switch configuration and preserve exact flags

Remove the old activation config from active configuration paths and replace it with `@EnableMethodSecurity` on a Spring-managed `@Configuration` class or on the `@SpringBootApplication` class. Write required flags explicitly. Do not keep two overlapping method-security configurations hoping the new one overrides the old one.

If the application only uses `@PreAuthorize`, you can typically write:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

In this case, `prePostEnabled = true` is enabled by default. If `@Secured` or JSR-250 is needed, enable the corresponding flags.

### Step 4 — Migrate legacy extensions

If the application previously extended `GlobalMethodSecurityConfiguration` to override `createExpressionHandler()`, `accessDecisionManager()`, or define custom voters, do not copy the override logic verbatim into a new class assuming it will be picked up automatically. `@EnableMethodSecurity` relies on `AuthorizationManager` components and new interceptors.

Common migration paths:

- **Custom expressions:** register a service bean to call from SpEL, e.g., `@PreAuthorize("@documentPolicy.canEdit(authentication, #id)")`. For custom `PermissionEvaluator`, `RoleHierarchy`, or trust resolvers, configure an appropriate `MethodSecurityExpressionHandler` bean and verify it is wired into the infrastructure.
- **Rules from legacy voters/metadata:** convert them into an `AuthorizationManager` at the appropriate interception point or a policy service called from annotations; re-verify `GRANT`/`DENY`/abstain semantics rather than assuming equivalence.
- **Expression root and parameter names:** check SpEL variables like `#id`, `#tenantId`, and `returnObject`. Parameter name metadata may depend on compiling with `-parameters` or parameter-naming annotations; if names fail to resolve, policies may receive `null` or fail.
- **Advice ordering:** check method-security interceptors alongside `@Transactional`, caching, and custom aspects; a pre-transaction check does not keep protecting access if owner/policy changes right before a write.

Example expression handler bean, illustrative only when the application **already has** its own `PermissionEvaluator`:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {

        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }
}
```

The corresponding imports are `org.springframework.security.access.PermissionEvaluator`, `org.springframework.security.access.expression.method.MethodSecurityExpressionHandler`, and `org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler`. The `@Bean static` method ensures this bean is published early before method security configuration initialization when needed. A `PermissionEvaluator` bean supplied by the application is required; this snippet is not standalone. Do not conclude that every custom voter maps to a `PermissionEvaluator` — map each extension according to its actual responsibility.

### Step 5 — Test before removing the legacy mechanism

Re-run authorization contract tests against the new configuration. Verify both that annotations take effect and that insufficient permissions are denied. Check cross-tenant resources, read-only permissions calling writes, self-invocation, methods invoked from async/batch flows, role changes between request and execution, and that logs do not leak data.

Do not rely solely on an HTTP controller already blocked at the filter chain: if the controller requires `authenticated()`, rejected anonymous requests can make tests **appear to pass even when method security is not enabled**. Invoke the service bean through its Spring proxy with principals having matching and non-matching authorities and assert true method-level behavior.

## 5. Complete Example in a Spring Boot 3 Application

The example below consists of Java files runnable inside a **working Spring Boot 3.x project with Java 17+**, not a standalone `javac` program because they depend on Spring Framework, Spring Security, Jakarta, and JUnit.

In a Gradle project with the Spring Boot plugin and dependency management already configured, ensure the appropriate dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

File `src/main/java/com/example/methodsecurity/MethodSecurityDemoApplication.java`:

```java
package com.example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity(
        prePostEnabled = true,
        securedEnabled = true,
        jsr250Enabled = true
)
public class MethodSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/methodsecurity/DocumentActions.java`:

```java
package com.example.methodsecurity;

import jakarta.annotation.security.RolesAllowed;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentActions {

    @PreAuthorize("hasAuthority('DOC_WRITE')")
    public String edit(String id) {
        return "edited:" + id;
    }

    @Secured("ROLE_AUDITOR")
    public String viewAudit() {
        return "audit";
    }

    @RolesAllowed("OPERATIONS")
    public String executeOperations() {
        return "operations";
    }
}
```

The three methods use three different annotation families, making it clear why the configuration must enable all three flags.

File `src/test/java/com/example/methodsecurity/DocumentActionsTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class DocumentActionsTest {

    @Autowired
    private DocumentActions actions;

    @Test
    @WithMockUser(authorities = "DOC_WRITE")
    void preAuthorizeAllowsCorrectAuthority() {
        assertEquals("edited:d-1", actions.edit("d-1"));
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void preAuthorizeDeniesWrongAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> actions.edit("d-1"));
    }

    @Test
    @WithMockUser(roles = "AUDITOR")
    void securedAnnotationIsEnabled() {
        assertEquals("audit", actions.viewAudit());
    }

    @Test
    @WithMockUser(roles = "OPERATIONS")
    void jsr250AnnotationIsEnabled() {
        assertEquals("operations", actions.executeOperations());
    }

    @Test
    @WithMockUser(roles = "USER")
    void jsr250DeniesWrongRole() {
        assertThrows(AccessDeniedException.class,
                () -> actions.executeOperations());
    }
}
```

In a Gradle project with a wrapper, run:

```bash
./gradlew test --tests 'com.example.methodsecurity.DocumentActionsTest'
```

On Windows PowerShell use the corresponding wrapper:

```powershell
.\gradlew.bat test --tests 'com.example.methodsecurity.DocumentActionsTest'
```

**Expected test result:** all five tests pass. The two tests with `assertThrows` confirm actors lacking permissions are denied; the other three confirm `@PreAuthorize`, `@Secured`, and JSR-250 actually allow authorized actors. This is the expectation when running in a Boot/Security environment compatible with the sample configuration and code; it is not fixed stdout printed by `java`.

If `securedEnabled = true` is omitted, the `securedAnnotationIsEnabled` test above is **insufficient to catch the bug**, because an unprotected method still returns `"audit"`. Add a dedicated negative test for `@Secured`:

```java
@Test
@WithMockUser(roles = "USER")
void securedDeniesWrongRole() {
    assertThrows(AccessDeniedException.class, actions::viewAudit);
}
```

This test belongs **in the same `DocumentActionsTest` class**. Likewise, if `jsr250Enabled = true` is omitted, `jsr250DeniesWrongRole` catches that `@RolesAllowed` is not enforced. If pre/post configuration is omitted, `preAuthorizeDeniesWrongAuthority` catches that failure. With the negative test added for `@Secured`, the sample suite has six test cases.

From there, expand to methods with real resource/tenant policies: `@WithMockUser` only simulates a security context, and does not verify JWT signature verification, JWT authority converters, or real HTTP paths. When testing production systems, add `MockMvc`/security filter integration tests and real repository data checks.

## 6. Common Pitfalls After Changing Annotations

### 6.1. Method invoked internally so the proxy does not run

Under standard Spring AOP proxy mode, method security annotations apply when calls pass **through the Spring-managed proxy**. A method on the same bean calling `this.adminAction()` bypasses the proxy, so annotations on `adminAction` may not be enforced.

Example not to rely on:

```java
@Service
public class OperationsService {

    public void doWork() {
        this.deleteSensitiveRecord(); // Self-invocation bypasses the proxy.
    }

    @PreAuthorize("hasAuthority('RECORD_DELETE')")
    public void deleteSensitiveRecord() {
        // ...
    }
}
```

Place permission boundaries on a bean/service invoked externally through a proxy, or structure the design so the check point actually executes. Tests must exercise the real business path rather than calling only the annotated method directly. Private methods, non-proxied methods, or incompatible `final`/proxy setups can also prevent method security from applying as expected.

### 6.2. Overlapping old and new configurations

When both `@EnableGlobalMethodSecurity` and `@EnableMethodSecurity` remain in concurrently active configurations, the application risks creating overlapping infrastructure/interceptors or hard-to-diagnose behavior. Establish a single source enabling method security and remove the legacy path once the new one is verified.

### 6.3. Forgetting a flag and losing protection

Changing `@EnableGlobalMethodSecurity(securedEnabled = true, jsr250Enabled = true)` to `@EnableMethodSecurity` disables `@Secured` and `@RolesAllowed` by default, while enabling `@PreAuthorize` by default. This is a double shift: it can silently drop protection on legacy endpoints while activating previously dormant checks. A test suite containing only happy-path tests for valid users will miss this.

### 6.4. Confusing roles and authorities

`hasRole('ADMIN')` typically checks authority `ROLE_ADMIN`, whereas `hasAuthority('ADMIN')` checks the exact string `ADMIN`. `@Secured("ROLE_ADMIN")` and `@RolesAllowed("ADMIN")` represent prefixes differently. Inspect actual `GrantedAuthority`s from your principal/role converter and check `GrantedAuthorityDefaults`/role hierarchy settings if customized.

### 6.5. Wrong SpEL parameter names

If `@PreAuthorize("@policy.canUpdate(authentication, #id)")` is used without compiler parameter names retained/resolved, the expression may fail to receive the right ID. With modern Java, configure the compiler `-parameters` flag as needed; parameter-name annotations supported by your API can also be used. After migrating, test expression methods using varied parameter types, nulls, overloaded methods, and interface proxies if present.

### 6.6. Assuming URL protection also protects methods

`SecurityFilterChain` using `authorizeHttpRequests` protects HTTP flows; method security protects bean invocations. Internal jobs, event consumers, or tests may call services without passing through URL filters. Conversely, protected methods do not automatically configure CSRF, session management, authentication mechanisms, or HTTP mappings. Both are needed when business requirements call for them.

### 6.7. Believing pre-authorization preserves permissions until write time

`@PreAuthorize` at time T0 does not lock the document until transaction commit. If the owner, tenant membership, or state changes before T1 writes data, the policy check may already be stale. For operations needing up-to-date write-time permissions, use conditional UPDATE/optimistic versioning/locking and proper transactions; `@PostAuthorize` also does not roll back non-DB side effects.

### 6.8. Caching permission results without sufficient scope

If a custom expression `@policy.canRead(...)` uses caching, ensure cache keys include the verified subject, tenant, resource, action, and necessary policy/revision versions. Changing annotations will not fix a decision cache shared between Alice and Bob, or a stale ALLOW after role revocation. Verify proper interaction between cache proxies and security proxies with hit/miss and revocation tests.

### 6.9. Migrating mistakenly to reactive configuration

For reactive/WebFlux applications, Spring Security uses its own reactive method security activation (`@EnableReactiveMethodSecurity`) and reactive security context. Do not switch a reactive application to `@EnableMethodSecurity` simply because of the new annotation name, and do not rely on thread-local `SecurityContextHolder` as the default security source for a Reactive pipeline. This lesson targets imperative/servlet method security; reactive apps must follow their dedicated mechanism.

## 7. Pre- and Post-Upgrade Regression Test Matrix

| Scenario | Behavior to Verify |
| --- | --- |
| `@PreAuthorize` with right authority | Method executes and returns expected result |
| `@PreAuthorize` missing authority | Denied, with no business side effects |
| `@Secured` with right role | Allowed when `securedEnabled = true` |
| `@Secured` wrong role | Denied; test must fail if the annotation group was forgotten |
| `@RolesAllowed` right/wrong role | Both allow and deny work properly when `jsr250Enabled = true` |
| Pre/post annotations not enabled in old config | Explicitly decide whether to enable or set `prePostEnabled=false`; no silent changes |
| Custom role prefix and authority converter | `ROLE_X`, `X`, and expressions follow the real contract |
| Resource-based policy | Valid role still cannot access someone else's document |
| Different tenant | No access to out-of-scope tenant resources, even with a valid ID |
| Self-invocation | Real business flow does not bypass permission checks |
| Methods via interface/implementation/proxy | Annotations placed where Spring actually recognizes them |
| SpEL parameter-dependent data | `#documentId` and `#tenantId` resolve accurately |
| Custom expression/PermissionEvaluator | Custom policy still runs and receives the right actor/resource |
| Methods with transactions/caching/aspects | Permission checked at the right point; no invalid events emitted on denial |
| Unauthenticated vs. authenticated-but-denied | Distinguish authentication failures from authorization failures per API contract |
| Multiple method-security configurations | No duplicate interceptors or disabled protection paths |
| Batch, async, scheduler flows | Explicit principal/context/authorization without relying on HTTP filters |
| Role/owner changes mid-processing | No unauthorized writes under revoked permissions per contract |

**How to test:** construct independent data and authorized/unauthorized principals; invoke Spring-managed beans via proxy; assert both exceptions/HTTP statuses and DB state, audit/outbox/side effects; for write methods, include at least one integration test using a real DB and architecture-accurate transactions/locking. In web tests, HTTP 401/403 depends on the authentication entry point, exception translation, and filter configuration; do not assume identical status codes across every method-call context.

Run tests prior to migration as a baseline, switch configs, re-run the same suite, and add cases for newly enabled flags. If differences arise, determine whether they are intentional policy changes or regressions—never "fix" them by disabling method security altogether.

## 8. When to Keep, Migrate, or Remove Legacy Extensions?

**Using standard annotations only:** if the app only uses `@PreAuthorize`/`@Secured`/JSR-250 and never overrode `GlobalMethodSecurityConfiguration`, migration can be concise: swap the config, enable the exact flags, and run tests.

**Custom `PermissionEvaluator` or expression handler:** declare the appropriate method security beans; do not merely change imports and lose expression roots, permission lookups, or role hierarchies. If custom policy can be expressed more cleanly via a bean expression like `@policy.canAct(authentication, #resourceId)`, consider simplifying the extension mechanism while keeping the contract intact.

**Custom voters, AccessDecisionManager, or metadata source:** this is an architectural change. Redesign around `AuthorizationManager` or appropriate interception, comparing grant/deny/abstain logic and policy ordering. No one-to-one annotation rename guarantees every custom voter is preserved.

**Special AOP/AspectJ protection mechanisms:** verify `proxyTargetClass`, mode, pointcuts, advice ordering, and test at runtime. Only switch to AspectJ or alter proxy strategies with clear justification and infrastructure; do not introduce weaving casually during a routine upgrade.

**Components outside the Spring container:** annotations do not protect objects instantiated via `new`. Bring services under Spring management or place authorization at the boundary actually invoked; migration does not fix missing proxies.

## 9. Completion Checklist

1. Identified all active method-security configurations; removed legacy activation paths upon migrating.
2. Compared the `prePostEnabled` default and `securedEnabled`/`jsr250Enabled` flags against pre-upgrade policy; enabled/disabled explicitly.
3. Migrated JSR-250 imports to Jakarta in Boot 3 environments while ensuring matching dependencies.
4. Audited custom expressions, evaluators, role hierarchies, voters, and `AuthorizationManager` wiring.
5. Checked proxies/self-invocation, SpEL parameter names, internal calls, transactions, and caching.
6. Tested both allow **and** deny on Spring-managed beans for every annotation family.
7. Tested owner/tenant/resource/status authorization and verified no data writes occur on denial.
8. Tested permissions across non-HTTP flows, stale caches, and concurrency where business logic requires it.
9. Ran integration tests for sensitive APIs, documented intentional policy changes, and verified zero unintended regressions.

**Key point to remember:** `@EnableMethodSecurity` is the modern choice for imperative method security in Spring Security; `prePostEnabled` is enabled by default, whereas `@Secured` and JSR-250 are **not**. A successful migration must preserve accurate ALLOW/DENY decisions for real actors, resources, and actions — and prove it with tests — rather than stopping once the app boots after renaming an annotation.
