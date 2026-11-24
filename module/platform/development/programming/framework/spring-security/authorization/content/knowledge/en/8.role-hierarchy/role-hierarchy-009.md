# Testing Direct Authorities, Derived Authorities, and Hierarchy Changes in Spring Security

## 1. Objective and real-world scenario

A reporting application has four roles:

- `ROLE_ADMIN`: administrator.
- `ROLE_MANAGER`: team manager.
- `ROLE_ANALYST`: analyst.
- `ROLE_VIEWER`: read-only viewer.

Initial policy states administrators can perform all manager operations, managers can perform analyst tasks, and analysts count as viewers. Certain roles also **imply** business permissions: analysts can read reports; managers can approve reports.

The development team updates the rule: **remove the inferred approval permission from ROLE_MANAGER**, while still letting users directly granted `report:approve` continue approving. If you only test that an admin opens the page successfully, that difference is very easy to miss.

This lesson focuses on **testing**, not just configuring `RoleHierarchy`. By the end, you will be able to:

1. Accurately distinguish **direct authorities** from **reachable/inherited authorities**.
2. Understand the direction and transitivity of `ROLE_A > ROLE_B`.
3. Write `RoleHierarchy.getReachableGrantedAuthorities(...)` unit tests covering both positive and negative cases.
4. Test that the hierarchy is actually applied in HTTP authorization and method security.
5. Distinguish `@WithMockUser(roles=...)` from `@WithMockUser(authorities=...)`.
6. Assess the impact of **adding, removing, reversing, or editing the hierarchy**.
7. Test permission revocation, stale JWTs/sessions, active runtime config, and cross-tenant objects.
8. Use a regression matrix to catch unintended privilege escalation before deployment.

**Technical scope:** Spring Security Servlet, Java 17+, `RoleHierarchyImpl`, `SecurityFilterChain`, `@EnableMethodSecurity`, JUnit 5, and Spring Security Test. Examples marked *fragment* belong inside a Spring Boot project with matching dependencies and controllers/services; the pure Java 17 section near the end is a standalone program.

## 2. The model: direct authorities vs. derived authorities

### 2.1. Source set D and effective set R(D)

Suppose at authentication time, an `Authentication` carries:

```text
Direct authorities D:
    ROLE_MANAGER
```

The role hierarchy declares:

```text
ROLE_ADMIN   > ROLE_MANAGER
ROLE_MANAGER > ROLE_ANALYST
ROLE_ANALYST > ROLE_VIEWER

ROLE_MANAGER > report:approve
ROLE_ANALYST > report:read
```

The `>` sign means the left role/authority **implies** the right one, not a numeric comparison and not “the role on the right is higher”. From source `ROLE_MANAGER`, the system can infer:

```text
Reachable authorities R(D):
    ROLE_MANAGER       (direct)
    ROLE_ANALYST       (inferred)
    ROLE_VIEWER        (inferred in two hops)
    report:approve     (inferred)
    report:read        (inferred via ROLE_ANALYST)
```

**The direct set stays inside the reachable set.** Per `RoleHierarchy`'s contract, `getReachableGrantedAuthorities(...)` returns directly assigned authorities **plus** all authorities reachable transitively.

Visualized as:

```text
ROLE_ADMIN
    │
    ▼
ROLE_MANAGER ──────► report:approve
    │
    ▼
ROLE_ANALYST ──────► report:read
    │
    ▼
ROLE_VIEWER
```

Arrows are **one-way only**. From `ROLE_VIEWER`, you **cannot** infer backwards to `ROLE_ANALYST`, `ROLE_MANAGER`, or `ROLE_ADMIN`.

### 2.2. Formula and testing implications

Let:

- `D` = set of authorities directly granted by the authentication source.
- `H` = configured hierarchy graph.
- `R_H(D)` = set of reachable authorities under hierarchy `H`, including `D`.
- `I_H(D) = R_H(D) \ D` = set of authorities **present solely by inference**.

A rule requiring authority `a` can allow when `a ∈ R_H(D)`, **provided the authorization checker actually uses RoleHierarchy H**. Not every piece of code reading `Authentication.getAuthorities()` expands it through the hierarchy.

Therefore, a solid test suite separates three assertions:

1. `Authentication.getAuthorities()` reflects **authorities assigned by the authentication source / test fixture**.
2. `RoleHierarchy.getReachableGrantedAuthorities(...)` computes graph closure properly.
3. Hierarchy-integrated HTTP/method authorization does or does not **rely on that closure** when evaluating access.

**Never use step 2 passing to assume step 3 is wired correctly.**

### 2.3. Why is role hierarchy not object authorization?

`ROLE_MANAGER > report:approve` may let a MANAGER pass the functional check `hasAuthority("report:approve")`. Yet report `r7` might belong to another tenant, be locked, or require two approvers. The hierarchy knows nothing about owner, tenant, state, or creator. Those rules must be enforced separately by method/domain authorization.

## 3. Baseline configuration for tests

### 3.1. RoleHierarchyImpl bean

A simple setup using modern Spring Security's `fromHierarchy` API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
public class HierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_MANAGER
                ROLE_MANAGER > ROLE_ANALYST
                ROLE_ANALYST > ROLE_VIEWER
                ROLE_MANAGER > report:approve
                ROLE_ANALYST > report:read
                """);
    }
}
```

This is a configuration class **inside a Spring Boot project**. The passed string declares each `source authority > implied authority` edge; `report:read` and `report:approve` are application-defined **permission strings**, not class names or built-in rights.

`RoleHierarchyImpl.fromHierarchy(...)` is convenient when expressing the whole graph as text. Recent versions recommend it over the older no-arg constructor and deprecated `setHierarchy(...)`.

### 3.2. Role-style builder in Spring Security 6.3+

When the hierarchy contains only `ROLE_`-prefixed roles, you can write:

```java
RoleHierarchy hierarchy = RoleHierarchyImpl.withDefaultRolePrefix()
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("ANALYST")
        .role("ANALYST").implies("VIEWER")
        .build();
```

`withDefaultRolePrefix()` and `withRolePrefix(String)` arrived in Spring Security **6.3**. For our baseline containing permissions `report:read` and `report:approve`, `fromHierarchy` is clearer and avoids confusion over the builder prepending role prefixes.

**Note:** `ROLE_` is the default convention; `hasRole("MANAGER")` normally looks up `ROLE_MANAGER`. `hasAuthority("ROLE_MANAGER")` checks the exact written string. If the system changes the prefix, synchronize the authority source, builder, HTTP, and method security. Never change only one place and assume the whole hierarchy works.

### 3.3. Do not turn every permission into a role just because of >

A hierarchy can link authority strings like:

```text
ROLE_ANALYST > report:read
```

yet `report:read` does **not** become `ROLE_report:read`. Tests should check `hasAuthority("report:read")` directly. An HTTP rule `hasRole("report:read")` expects `ROLE_report:read` under the default prefix and is not equivalent.

Name things clearly:

```text
ROLE_ADMIN          = role
ROLE_MANAGER        = role
ROLE_ANALYST        = role
ROLE_VIEWER         = role
report:read         = permission
report:approve      = permission
```

With JWTs, a scope like `reports.read` is mapped by the default converter to `SCOPE_reports.read`, **not automatically equal** to `report:read`. If the auth source supplies JWT scopes, align the mapping before testing the hierarchy.

## 4. Matrix of source authorities and derived authorities

Under baseline hierarchy `H0`:

| Direct D | ROLE_VIEWER | ROLE_ANALYST | ROLE_MANAGER | ROLE_ADMIN | report:read | report:approve |
| --- | --- | --- | --- | --- | --- | --- |
| `ROLE_ADMIN` | Inferred | Inferred | Inferred | **Direct** | Inferred | Inferred |
| `ROLE_MANAGER` | Inferred | Inferred | **Direct** | No | Inferred | Inferred |
| `ROLE_ANALYST` | Inferred | **Direct** | No | No | Inferred | No |
| `ROLE_VIEWER` | **Direct** | No | No | No | No | No |
| `ROLE_SUPPORT` | No | No | No | No | No | No |
| `report:read` | No | No | No | No | **Direct** | No |
| `ROLE_VIEWER` + `report:approve` | **Direct** | No | No | No | No | **Direct** |

Here “No” means absent from the reachable set under **H0** from the listed direct set. It does not mean the permission could not come from another independent mechanism.

What must be tested?

- **Transitivity:** ADMIN implies VIEWER despite no direct ADMIN→VIEWER edge.
- **No reverse inference:** VIEWER never implies ADMIN.
- **Independence between roles and permissions:** holding `report:read` directly does not grant `ROLE_ANALYST`.
- **Not limited to roles:** `ROLE_MANAGER` also implies `report:approve`.
- **Combining multiple sources:** multiple direct authorities produce the union of their closures.
- **No unconfigured grants:** `ROLE_SUPPORT` receives no report permissions unless configured.

**Key test rule:** include at least one user with **only a high role**, one with **only a low role**, one with a **direct permission**, and one **completely unrelated**.

## 5. Unit testing RoleHierarchy.getReachableGrantedAuthorities

### 5.1. Test closure without asserting return order

JUnit 5 + AssertJ example inside a project with `spring-security-core`, JUnit, and AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class RoleHierarchyUnitTest {

    private final RoleHierarchy hierarchy =
            RoleHierarchyImpl.fromHierarchy("""
                    ROLE_ADMIN > ROLE_MANAGER
                    ROLE_MANAGER > ROLE_ANALYST
                    ROLE_ANALYST > ROLE_VIEWER
                    ROLE_MANAGER > report:approve
                    ROLE_ANALYST > report:read
                    """);

    private Set<String> reachable(String... direct) {
        var authorities = java.util.Arrays.stream(direct)
                .map(SimpleGrantedAuthority::new)
                .toList();

        return hierarchy.getReachableGrantedAuthorities(authorities)
                .stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    void adminIncludesDirectAndTransitiveAuthorities() {
        assertThat(reachable("ROLE_ADMIN")).containsExactlyInAnyOrder(
                "ROLE_ADMIN",
                "ROLE_MANAGER",
                "ROLE_ANALYST",
                "ROLE_VIEWER",
                "report:read",
                "report:approve");
    }

    @Test
    void analystDoesNotGainManagerOrApprove() {
        assertThat(reachable("ROLE_ANALYST"))
                .containsExactlyInAnyOrder(
                        "ROLE_ANALYST", "ROLE_VIEWER", "report:read");
    }

    @Test
    void directPermissionDoesNotImplyRole() {
        assertThat(reachable("report:read"))
                .containsExactlyInAnyOrder("report:read");
    }

    @Test
    void multipleDirectAuthoritiesAreCombined() {
        assertThat(reachable("ROLE_VIEWER", "report:approve"))
                .containsExactlyInAnyOrder(
                        "ROLE_VIEWER", "report:approve");
    }

    @Test
    void unrelatedRoleDoesNotGetReportRights() {
        assertThat(reachable("ROLE_SUPPORT"))
                .containsExactlyInAnyOrder("ROLE_SUPPORT");
    }
}
```

Use `containsExactlyInAnyOrder` because `RoleHierarchy` returns a `Collection` with no guaranteed order. Converting to `Set<String>` eliminates ordering concerns and expresses the authority set contract cleanly.

### 5.2. Do not check only “has permission” while omitting “lacks permission”

A test asserting `ROLE_ADMIN` includes `ROLE_VIEWER` still passes if someone accidentally adds:

```text
ROLE_VIEWER > report:approve
```

and lets viewers approve reports. Always write **negative assertions** for lower roles:

```java
@Test
void viewerCannotApprove() {
    assertThat(reachable("ROLE_VIEWER"))
            .doesNotContain("report:approve", "ROLE_ADMIN");
}
```

Role hierarchy tests are **security tests**; negative cases are just as important as positive ones.

### 5.3. Proving direct and inferred are two distinct sets

```java
@Test
void directIsNotAutomaticallyExpandedInAuthentication() {
    var raw = Set.of("ROLE_MANAGER");
    var expanded = reachable("ROLE_MANAGER");

    assertThat(raw).containsExactly("ROLE_MANAGER");
    assertThat(expanded).contains(
            "ROLE_MANAGER", "ROLE_ANALYST",
            "ROLE_VIEWER", "report:read", "report:approve");
}
```

This snippet compares a simulated source set against the expanded set; to test a real `Authentication`, construct a `UsernamePasswordAuthenticationToken` or use `@WithMockUser` and inspect `getAuthorities()` on the test principal. Do not cite this snippet as claiming every `Authentication` provider always stores roles identically.

## 6. Why does @WithMockUser not prove the hierarchy is being applied?

### 6.1. @WithMockUser(roles=...) sets direct roles

Example:

```java
@WithMockUser(roles = "MANAGER")
```

normally creates a test `Authentication` with the direct authority:

```text
ROLE_MANAGER
```

It **does not insert** `ROLE_ANALYST`, `ROLE_VIEWER`, `report:approve`, or `report:read` into `Authentication.getAuthorities()`. Derived authorities must be resolved by `RoleHierarchy` inside **hierarchy-integrated authorization checkers**.

Conversely:

```java
@WithMockUser(authorities = "report:approve")
```

grants the exact direct permission `report:approve`. This is a vital test verifying that hierarchy edits do not accidentally strip **directly assigned** permissions.

### 6.2. Two different assertions can be true simultaneously

For a `ROLE_MANAGER` user:

```text
authentication.getAuthorities():
    [ROLE_MANAGER]

roleHierarchy.getReachableGrantedAuthorities(...):
    [ROLE_MANAGER, ROLE_ANALYST, ROLE_VIEWER,
     report:approve, report:read]
```

Both are true. If a custom service writes:

```java
boolean allowed = authentication.getAuthorities()
        .stream()
        .anyMatch(a -> a.getAuthority().equals("report:read"));
```

it can return `false` for the manager even when `@PreAuthorize("hasAuthority('report:read')")` in the same hierarchy-wired system allows it. That custom code inspects only direct authorities **without consulting the hierarchy**.

**Do not guess between the two behaviors:** specify whether policy checks direct or effective authorities and test the right component. When identical semantics are needed, use a consistently configured `AuthorizationManager`/`RoleHierarchy`.

### 6.3. Only grant the source authority in tests

Avoid doing this:

```java
@WithMockUser(authorities = {
    "ROLE_MANAGER", "ROLE_ANALYST",
    "ROLE_VIEWER", "report:approve", "report:read"
})
```

and concluding hierarchy works because the report-reading method passes. That test **manually assigned every derived permission**; even if the hierarchy were deleted completely, the test would still pass.

To test inference, **assign only the direct role**:

```java
@WithMockUser(roles = "MANAGER")
```

and assert that endpoints/methods requiring `report:read` or `report:approve` succeed in an environment with the hierarchy registered.

## 7. Testing HTTP authorization with RoleHierarchy

### 7.1. Start with an explicit manager calling setRoleHierarchy

In Spring Security **6.5**, `AuthorityAuthorizationManager` provides `setRoleHierarchy(RoleHierarchy)`. Using an explicit manager clearly tests whether hierarchy is applied rather than relying on ambiguous global wiring.

Integration config class example:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class ReportHttpSecurityConfig {

    @Bean
    SecurityFilterChain reportChain(HttpSecurity http,
                                    RoleHierarchy roleHierarchy)
            throws Exception {

        AuthorityAuthorizationManager<RequestAuthorizationContext> read =
                AuthorityAuthorizationManager.hasAuthority("report:read");
        read.setRoleHierarchy(roleHierarchy);

        AuthorityAuthorizationManager<RequestAuthorizationContext> approve =
                AuthorityAuthorizationManager.hasAuthority("report:approve");
        approve.setRoleHierarchy(roleHierarchy);

        return http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.GET, "/api/reports", "/api/reports/*")
                    .access(read)
                .requestMatchers(
                        HttpMethod.POST, "/api/reports/*/approve")
                    .access(approve)
                .anyRequest().denyAll()
        ).build();
    }
}
```

**This is a Spring Security Servlet class meant for a project containing authentication providers, controllers, and the `RoleHierarchy` bean from section 3**. It omits login/session/JWT and CSRF setup. For POST requests, if CSRF is enabled, tests must send a valid CSRF token so a CSRF 403 is not confused with a hierarchy denial.

`AuthorityAuthorizationManager` with `setRoleHierarchy(...)` is available in 6.5; newer releases add factory-based hierarchy management. When adapting for Spring Security 7+, check exact-version Javadocs and follow that release's recommended configuration.

### 7.2. Why not just use hasRole("MANAGER") on every route?

An API often requires a **permission** rather than a role:

- `GET /api/reports/r7` requires `report:read`.
- `POST /api/reports/r7/approve` requires `report:approve`.
- `GET /api/admin/users` requires `ROLE_ADMIN`.

Role hierarchy lets higher roles imply matching permissions, but only when **the authorization manager uses the hierarchy**. A `hasRole("MANAGER")` check on HTTP and `hasAuthority("report:read")` on a method can express two complementary policies; never assume they stay equivalent if the graph changes.

### 7.3. Essential HTTP matrix

| Test principal (direct) | GET /api/reports/r7 | POST /api/reports/r7/approve |
| --- | --- | --- |
| `ROLE_ADMIN` | Allow via HTTP rule | Allow via HTTP rule |
| `ROLE_MANAGER` | Allow (inferred) | Allow (inferred) |
| `ROLE_ANALYST` | Allow (inferred) | Deny |
| `ROLE_VIEWER` | Deny | Deny |
| `ROLE_SUPPORT` | Deny | Deny |
| `report:read` | Allow (direct) | Deny |
| `report:approve` | Deny | Allow (direct) |

This table reflects **hierarchy H0 and the managers from section 7.1**. Controllers/services can still deny if the report is missing, belongs to another tenant, or is in an invalid state.

### 7.4. Rule-based MockMvc integration tests

Fragment inside `@SpringBootTest` + `@AutoConfigureMockMvc`, assuming test controllers return success statuses:

```java
@Test
@WithMockUser(roles = "MANAGER")
void managerCanReadThroughInheritedPermission() throws Exception {
    mockMvc.perform(get("/api/reports/r7"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(roles = "ANALYST")
void analystCannotApprove() throws Exception {
    mockMvc.perform(post("/api/reports/r7/approve").with(csrf()))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser(authorities = "report:approve")
void directlyGrantedPermissionCanApprove() throws Exception {
    mockMvc.perform(post("/api/reports/r7/approve").with(csrf()))
            .andExpect(status().isOk());
}
```

**Important note:** tests expecting `200` **only** succeed if a real handler exists, fixture `r7` is permitted, method/service rules do not block it, and the controller returns 200. If the API returns 204 or 202, assert accordingly. With `@WebMvcTest`, import the security config and `RoleHierarchy` bean into the slice; otherwise pass/fail results do not reflect production behavior.

These snippets are not standalone test files; add imports, `MockMvc` injection, and an appropriately scoped test class.

### 7.5. Testing that admin access does not open backwards

Add an endpoint:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

and test that `ROLE_MANAGER`, `ROLE_ANALYST`, and `ROLE_VIEWER` are all denied. However, placing the admin matcher after `/api/**.authenticated()` lets the broader matcher shadow it; test **first-match ordering** rather than just testing one manager in isolation.

## 8. Method security: testing @PreAuthorize and verifying the handler uses hierarchy

### 8.1. Enabling and configuring in the right place

Spring Security supports method checks such as:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView view(String reportId) {
    return reportRepository.loadVisible(reportId);
}
```

For `ROLE_ANALYST` to satisfy `report:read` via hierarchy, the `MethodSecurityExpressionHandler` backing `@PreAuthorize` must be configured with the matching `RoleHierarchy`.

Per Spring Security docs, add:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class ReportMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
```

The `static @Bean` declaration follows Spring Security guidance so the handler registers before method-security infrastructure initializes. This config requires the `RoleHierarchy` bean from section 3. If the application uses factories or other method annotations (`@Secured`, JSR-250), verify wiring for your exact version and annotation type.

### 8.2. Testing invocation through the Spring proxy

Spring-managed service example:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportPolicyProbe {

    @PreAuthorize("hasAuthority('report:read')")
    public String read() {
        return "read-ok";
    }

    @PreAuthorize("hasAuthority('report:approve')")
    public String approve() {
        return "approve-ok";
    }
}
```

Test this bean **by injecting it from the Spring context** and invoking methods through the proxy:

```java
@Test
@WithMockUser(roles = "ANALYST")
void analystReadsWithInheritedPermission() {
    assertThat(reportPolicyProbe.read()).isEqualTo("read-ok");
    assertThatThrownBy(() -> reportPolicyProbe.approve())
            .isInstanceOf(AccessDeniedException.class);
}
```

This fragment requires `@SpringBootTest` or a matching method-security test context, AssertJ, `AccessDeniedException`, and injected `ReportPolicyProbe`. In real service methods, still enforce object and tenant checks.

**Self-invocation:** calling `this.read()` from another method on the same object may bypass the method-security proxy and invalidate test conclusions. Tests should call the **proxied bean** externally.

### 8.3. When HTTP passes yet method fails

A user with `ROLE_MANAGER` calls `GET /api/reports/r7`:

1. HTTP manager called `setRoleHierarchy` → sees inferred `report:read` → allows.
2. Method handler **missed `setRoleHierarchy`** → sees only direct `ROLE_MANAGER` → `hasAuthority('report:read')` fails.

This is a **mismatch between HTTP and method security configuration**, not a broken role hierarchy. Only tests exercising both layers catch it.

Conversely, testing only methods without HTTP routes can miss an unprotected matcher or wrong filter chain.

## 9. Distinguishing unit tests, policy integration tests, and end-to-end tests

| Test layer | What it proves | What it does **not** prove by itself |
| --- | --- | --- |
| `RoleHierarchyImpl` unit test | Graph H computes expected reachable sets | Whether HTTP/method interceptors use H |
| `AuthorityAuthorizationManager` test | Manager uses H to grant/deny permission | Whether route matchers/Servlet chain pick it |
| `@PreAuthorize` test via Spring context | Method-security handler actually checks H | Whether HTTP URLs are protected |
| MockMvc + Spring Security | Filter chain/matchers/auth and handler per test setup | Production gateways or JWT converters if mocked |
| HTTP integration with real token/session | Auth provider/converter + security + controller cooperate | Long-term race/revocation or all tenants |
| Regression test on changing H | Effective permissions shift by exact delta | Data/object-level policies if untested |

A high-quality suite spans **multiple layers** — each layer need not repeat every case, yet at least one allow flow and one deny flow should traverse real Spring wiring.

### 9.1. Avoid tautological tests

Common pitfall:

```java
var hierarchy = RoleHierarchyImpl.fromHierarchy(
        "ROLE_MANAGER > report:approve");
var expanded = hierarchy.getReachableGrantedAuthorities(
        List.of(new SimpleGrantedAuthority("ROLE_MANAGER")));

assertThat(expanded).isNotEmpty();
```

`isNotEmpty` is weak: merely retaining the direct `ROLE_MANAGER` makes it pass even if the `report:approve` edge is broken. Assert **the entire expected set or specific target permissions**, along with permissions that **must not** be included.

### 9.2. Security tests are contracts, not setup snapshots

Distinguish clearly:

- “`ROLE_MANAGER` **must** be able to approve in the baseline.”
- “`ROLE_MANAGER` **can no longer** approve after the change request.”
- “Users with **direct** `report:approve` can still approve.”
- “`ROLE_VIEWER` **never** becomes admin.”

These are business contracts. Tests that merely snapshot a config file without expressing intent easily get updated to match bugs.

## 10. Changing the hierarchy: compute the delta before editing code

### 10.1. Two versions: H0 and H1

Initial hierarchy H0:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_ANALYST
ROLE_ANALYST > ROLE_VIEWER
ROLE_MANAGER > report:approve
ROLE_ANALYST > report:read
```

Business change: **managers should no longer automatically approve reports**. Hierarchy H1:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_ANALYST
ROLE_ANALYST > ROLE_VIEWER
ROLE_ANALYST > report:read
```

In H1, `ROLE_MANAGER > report:approve` is removed. With no other path to `report:approve`, users holding only `ROLE_MANAGER` or `ROLE_ADMIN` both **lose the derived approve permission**. This often surprises teams: because ADMIN is above MANAGER, ADMIN loses that permission too unless another edge exists.

### 10.2. Permission change matrix must include transitive roles

| Direct principal | report:read H0 → H1 | report:approve H0 → H1 | Meaning |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | ALLOW → ALLOW | **ALLOW → DENY** | ADMIN loses inferred approve |
| `ROLE_MANAGER` | ALLOW → ALLOW | **ALLOW → DENY** | Intended target of change |
| `ROLE_ANALYST` | ALLOW → ALLOW | DENY → DENY | Unchanged |
| `ROLE_VIEWER` | DENY → DENY | DENY → DENY | No new exposure |
| `ROLE_MANAGER` + `report:approve` | ALLOW → ALLOW | **ALLOW → ALLOW** | Direct permission preserved |
| `report:approve` | DENY → DENY | **ALLOW → ALLOW** | Direct permission independent of edge |
| `ROLE_SUPPORT` | DENY → DENY | DENY → DENY | Unrelated |

Always test **roles above the removed edge** (ADMIN), not only the role directly on the edge (MANAGER). That is the nature of transitive closure: removing one edge can revoke permissions from multiple ancestor roles.

### 10.3. Do not add ADMIN > report:approve without authorization

If business intends for ADMIN to keep approving after MANAGER loses it, that requires an **explicit policy decision**:

```text
ROLE_ADMIN > report:approve
```

added to H1, or granting the permission directly to authorized admins. That is a business/policy decision, not a default “fix failing test” tweak. Likewise, approval rights may require two independent users or SoD rather than being granted implicitly to all admins.

## 11. Writing regression tests for hierarchy changes

### 11.1. Testing H0 and H1 in the same unit test

JUnit 5 template:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class RoleHierarchyChangeTest {

    private final RoleHierarchy before = RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_ANALYST
            ROLE_ANALYST > ROLE_VIEWER
            ROLE_MANAGER > report:approve
            ROLE_ANALYST > report:read
            """);

    private final RoleHierarchy after = RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_ANALYST
            ROLE_ANALYST > ROLE_VIEWER
            ROLE_ANALYST > report:read
            """);

    private boolean reaches(
            RoleHierarchy graph, String wanted, String... direct) {
        var source = java.util.Arrays.stream(direct)
                .map(SimpleGrantedAuthority::new).toList();

        return graph.getReachableGrantedAuthorities(source).stream()
                .anyMatch(a -> wanted.equals(a.getAuthority()));
    }

    @Test
    void managerLosesInheritedApproveButKeepsRead() {
        assertThat(reaches(before, "report:approve", "ROLE_MANAGER"))
                .isTrue();
        assertThat(reaches(after, "report:approve", "ROLE_MANAGER"))
                .isFalse();

        assertThat(reaches(before, "report:read", "ROLE_MANAGER"))
                .isTrue();
        assertThat(reaches(after, "report:read", "ROLE_MANAGER"))
                .isTrue();
    }

    @Test
    void adminAlsoLosesApproveTransitively() {
        assertThat(reaches(before, "report:approve", "ROLE_ADMIN"))
                .isTrue();
        assertThat(reaches(after, "report:approve", "ROLE_ADMIN"))
                .isFalse();
    }

    @Test
    void directApproveIsNotRevokedByRemovingHierarchyEdge() {
        assertThat(reaches(after, "report:approve",
                "ROLE_MANAGER", "report:approve")).isTrue();
        assertThat(reaches(after, "report:approve",
                "report:approve")).isTrue();
    }

    @Test
    void viewerNeverGainsAdmin() {
        assertThat(reaches(before, "ROLE_ADMIN", "ROLE_VIEWER"))
                .isFalse();
        assertThat(reaches(after, "ROLE_ADMIN", "ROLE_VIEWER"))
                .isFalse();
    }
}
```

**Important:** this test class constructs H0/H1 **locally inside the test** to verify the delta. It does not prove the deployed system loaded H1. Pair it with integration tests loading the real application context and new configuration.

### 11.2. Single-edge mutation tests

Mutations worth testing or reviewing:

1. Removing `ROLE_MANAGER > report:approve`.
2. Reversing `ROLE_MANAGER > ROLE_ANALYST` into `ROLE_ANALYST > ROLE_MANAGER`.
3. Adding `ROLE_VIEWER > report:approve`.
4. Removing `ROLE_ANALYST > report:read`.
5. Introducing a typo `ROLE_ANALYST` → `ROLE_ANALYTICS`.
6. Changing case `report:approve` → `REPORT:APPROVE`.
7. Adding an edge that accidentally opens an alternate path back to an old permission.
8. Creating a cycle, e.g. `ROLE_VIEWER > ROLE_ADMIN` while ADMIN already implies VIEWER.

**Not every mutation is a valid configuration.** Modern `RoleHierarchyImpl` detects cycles during graph construction and can throw an exception; tests should confirm application startup rejects invalid hierarchies. Never rely on “the framework will pick a safe path” when a graph contains cycles.

### 11.3. Positive delta, negative delta, and invariants

When reviewing a hierarchy change, define:

- **Positive delta:** which permissions are intentionally newly granted?
- **Negative delta:** which permissions are intentionally revoked?
- **Invariant:** which permissions must remain unchanged, including direct permissions?
- **Forbidden invariant:** which permissions must strictly never appear for lower roles?
- **Side effect:** does the change expose or block other ancestor roles via transitivity?

For every critical role or authority group, test partially at the graph layer and partially against real endpoints/methods.

## 12. Does a new hierarchy take effect immediately for logged-in users?

### 12.1. Editing a YAML/text file does not update the running bean

`RoleHierarchyImpl.fromHierarchy(...)` builds an instance from the definition at startup. Authorization managers and expression handlers may hold **references to that instance**. Editing the hierarchy text on disk while the app is running does not automatically reload every bean or recompute closures.

**Most predictable deployment strategy:** update config, run tests, redeploy/restart instances, and verify all authorization consumers use H1. If dynamic runtime updates are genuinely required, build a **controlled, atomic reload**: validate the new graph, swap consumers, invalidate related caches, log policy versions, and avoid split-brain windows across nodes.

Do not call the deprecated `setHierarchy(...)` as a multithreaded runtime “hot reload” without analyzing synchronization, references, and consistency.

### 12.2. Changing the hierarchy differs from revoking direct roles

Suppose Alice still holds direct `ROLE_MANAGER` from her session/JWT:

- With **H0** active: Alice infers `report:approve`.
- With **H1** actually active at authorization: Alice no longer infers `report:approve`.
- If Alice also holds direct `report:approve` in `Authentication`: Alice **still has approve access** under permission rules despite deleting the H0 edge.
- If sessions/JWTs carry stale roles/permissions, enforce dedicated token/session revocation policies.

Tests must ask clearly whether you are “changing the hierarchy” or “changing user authorities”. Both can look identical on one endpoint while behaving differently elsewhere.

### 12.3. JWTs and sessions introduce stale authorities

A signed JWT can embed scopes/roles as of token issuance. When a user's database role is later revoked, an unexpired token can still authenticate with **stale claims** unless revocation, introspection, or short refresh cycles are enforced. Session-based authentication can likewise cache old authorities.

A new role hierarchy does not alter claims inside issued tokens. When H1 removes an edge, derived permissions computed from direct roles at authorization time change; permissions already embedded **directly** in the token remain intact. For sensitive actions, test revocation at both the hierarchy layer and the active authentication source.

### 12.4. Multi-instance/microservice consistency

If service A runs H1 while service B still runs H0, the same MANAGER role can approve on B while being denied on A. Always:

- Version the deployed policy/hierarchy.
- Roll out policy changes across nodes in a controlled manner.
- Enforce authorization inside the service that owns the data/side effects.
- Run regression tests and monitor/audit sensitive permissions during rollout.
- Never treat frontend role hierarchies as the source of truth.

## 13. Spring Security 6.5 and 7.x: picking the right testing API

### 13.1. Stable closure computation APIs

Across 6.5 and 7.x, `RoleHierarchyImpl.fromHierarchy(...)` and `RoleHierarchy.getReachableGrantedAuthorities(...)` remain central to unit tests. `withDefaultRolePrefix()`/`withRolePrefix()` arrived in 6.3; `setHierarchy(...)` and the no-arg constructor are deprecated in 6.5.

Never guess API names from Spring Boot versions without checking the dependency tree; Boot manages Spring Security versions via BOM/parent. When maintaining modules on different versions, compile and test each module against its exact version.

### 13.2. HTTP authorization manager in 6.5

In 6.5, `AuthorityAuthorizationManager` supports:

```java
var manager = AuthorityAuthorizationManager
        .<RequestAuthorizationContext>hasAuthority("report:read");
manager.setRoleHierarchy(roleHierarchy);
```

This pattern lets a test verify the **manager itself** is wired with the graph, not just that a bean exists in the Spring context. When using `authorizeHttpRequests(...).hasAuthority(...)` directly, check your version's documentation to see how the hierarchy reaches DSL-created managers.

### 13.3. Spring Security 7 introduces AuthorizationManagerFactory

Spring Security 7.0 introduces `AuthorizationManagerFactory<T>` and `DefaultAuthorizationManagerFactory<T>`, allowing centralized configuration of `RoleHierarchy` and `rolePrefix` for factory-created managers. Sketch:

```java
DefaultAuthorizationManagerFactory<RequestAuthorizationContext> factory =
        new DefaultAuthorizationManagerFactory<>();
factory.setRoleHierarchy(roleHierarchy);

AuthorizationManager<RequestAuthorizationContext> reader =
        factory.hasAuthority("report:read");
```

This is a **Spring Security 7.x fragment**; it requires appropriate imports and an existing `roleHierarchy` instance. Verify factory hierarchy application wherever the factory is used. Never assume a hand-written custom `AuthorizationManager` reads the factory bean or expands authorities automatically.

### 13.4. Method-security expression handler is a separate wiring point

For `@PreAuthorize` expressions, configuring `DefaultMethodSecurityExpressionHandler#setRoleHierarchy` is the documented Spring Security pattern. Other method mechanisms like `@Secured` or JSR-250 have dedicated authorization managers, so verify version-specific configuration for each. **Never assume having a `RoleHierarchy` bean makes every custom authorization check understand the graph.**

### 13.5. Do not confuse AuthorizationResult with reachable authorities

`AuthorizationResult`/`AuthorizationDecision` represents the allow/deny outcome of a check. `getReachableGrantedAuthorities` produces the **effective authority set**. They belong to different layers:

```text
Direct authorities
        │
        ▼
RoleHierarchy computes reachable authorities
        │
        ▼
AuthorizationManager checks required authority
        │
        ▼
AuthorizationResult / decision: granted or denied
```

A test asserting only `AuthorizationDecision(true)` cannot tell whether access came from a direct authority or the hierarchy unless the fixture and graph are constructed to distinguish them.

## 14. Role of object-level permissions and separation of duties

### 14.1. Role hierarchy does not grant access to every resource

With `ROLE_MANAGER > report:approve`, a manager holds the **functional permission**. Yet approving a report may also require:

```text
ALLOW_APPROVE =
    authenticated
    AND effectiveAuthorities contains "report:approve"
    AND report.tenantId = principal.tenantId
    AND report.status = WAITING_FOR_APPROVAL
    AND report.creatorId != principal.userId
```

This is business policy pseudocode, not a built-in Java/Spring method. In particular, “cannot self-approve one's own report” is **separation of duties** and cannot be inferred from a role hierarchy.

### 14.2. Passing a role hierarchy test does not mean approval succeeds

A test showing `ROLE_MANAGER` infers `report:approve` proves functional permission only. Approval integration tests must also verify:

- Report belongs to the same tenant or a permitted cross-tenant policy exists.
- Report is in an approvable state.
- User is not the creator when self-approval is forbidden.
- Roles revoked prior to saving are handled per policy.
- Audit logs capture who approved and under which policy version.

When the hierarchy changes, endpoint tests must assert **zero side effects** on denial, such as zero updated rows and no emitted approval events.

### 14.3. Do not broaden lower roles just to simplify tests

Some projects create overly broad hierarchies:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
ROLE_USER > report:read
ROLE_USER > report:approve
```

This gives every USER approval power even though most screens only need read access. Keep sensitive permissions on edges/grants with explicit business approval rather than abusing hierarchy as a substitute for a proper permission model.

## 15. Standalone Java 17 example: verifying closure and policy delta

To understand the mechanics without Spring, the following program uses pure Java 17 to simulate an authority graph. It:

- Accepts a `Map<String, Set<String>>` representing `source -> included authorities` edges.
- Traverses the graph and collects **direct + reachable authorities** across multiple hops.
- Evaluates read and approve permissions **before and after the change**.
- Proves **direct `report:approve` is not lost** when removing the derived edge.
- Prints clear string output without faking any Spring classes.

**This is a conceptual demo** and does not replace `RoleHierarchyImpl` (Spring also handles graph validation, role prefixes, and authorization integration). Never put this mini implementation into production.

Create `HierarchyRegressionDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class HierarchyRegressionDemo {

    static Set<String> reachable(
            Map<String, Set<String>> graph,
            Set<String> direct) {

        Set<String> result = new HashSet<>(direct);
        ArrayDeque<String> queue = new ArrayDeque<>(direct);

        while (!queue.isEmpty()) {
            String current = queue.removeFirst();
            for (String next : graph.getOrDefault(current, Set.of())) {
                if (result.add(next)) {
                    queue.addLast(next);
                }
            }
        }
        return result;
    }

    static String status(
            Map<String, Set<String>> graph,
            Set<String> direct,
            String required) {
        return reachable(graph, direct).contains(required)
                ? "ALLOW" : "DENY";
    }

    static void show(
            String label,
            Map<String, Set<String>> graph,
            Set<String> direct) {

        System.out.println(label + "-read="
                + status(graph, direct, "report:read"));
        System.out.println(label + "-approve="
                + status(graph, direct, "report:approve"));
    }

    public static void main(String[] args) {
        Map<String, Set<String>> before = Map.of(
                "ROLE_ADMIN", Set.of("ROLE_MANAGER"),
                "ROLE_MANAGER",
                    Set.of("ROLE_ANALYST", "report:approve"),
                "ROLE_ANALYST",
                    Set.of("ROLE_VIEWER", "report:read"));

        Map<String, Set<String>> after = Map.of(
                "ROLE_ADMIN", Set.of("ROLE_MANAGER"),
                "ROLE_MANAGER", Set.of("ROLE_ANALYST"),
                "ROLE_ANALYST",
                    Set.of("ROLE_VIEWER", "report:read"));

        Set<String> manager = Set.of("ROLE_MANAGER");
        Set<String> admin = Set.of("ROLE_ADMIN");
        Set<String> viewer = Set.of("ROLE_VIEWER");
        Set<String> managerWithDirectApprove =
                Set.of("ROLE_MANAGER", "report:approve");

        show("before-manager", before, manager);
        show("after-manager", after, manager);
        show("before-admin", before, admin);
        show("after-admin", after, admin);
        show("after-viewer", after, viewer);
        show("after-manager-direct", after, managerWithDirectApprove);

        System.out.println("manager-direct=" + manager);
        System.out.println("manager-reachable-after="
                + new TreeSet<>(reachable(after, manager)));
        System.out.println("viewer-is-admin="
                + reachable(after, viewer).contains("ROLE_ADMIN"));
    }
}
```

Run with JDK 17 or newer:

```bash
javac HierarchyRegressionDemo.java
java HierarchyRegressionDemo
```

**Expected stdout**, since `Set.of("ROLE_MANAGER")` has one element and `TreeSet` sorts the final display:

```text
before-manager-read=ALLOW
before-manager-approve=ALLOW
after-manager-read=ALLOW
after-manager-approve=DENY
before-admin-read=ALLOW
before-admin-approve=ALLOW
after-admin-read=ALLOW
after-admin-approve=DENY
after-viewer-read=DENY
after-viewer-approve=DENY
after-manager-direct-read=ALLOW
after-manager-direct-approve=ALLOW
manager-direct=[ROLE_MANAGER]
manager-reachable-after=[ROLE_ANALYST, ROLE_MANAGER, ROLE_VIEWER, report:read]
viewer-is-admin=false
```

### 15.1. Why is this a useful regression test?

- In `before`, MANAGER holds `report:approve` **solely via the hierarchy edge**.
- In `after`, removing manager→approve strips approval from both MANAGER and ADMIN while preserving read access.
- A principal directly granted `report:approve` retains approval despite edge removal.
- Viewer never infers admin; arrow direction holds.
- `Set<String> direct` is never mutated into the expanded set; both concepts stay separated across all layers.

### 15.2. Why does the demo not treat cycles as valid?

The loop uses `result.add(next)` to avoid infinite looping on cyclic graphs, yet **that only guarantees the demo algorithm terminates** — it does not make a cyclic authority graph valid policy. Real `RoleHierarchyImpl` detects cycles; applications must reject invalid configurations at startup.

### 15.3. Security limitations of the demo

This is a pure Java graph closure function with no Spring `Authentication`, Servlet, JWT, session, role prefix, CSRF, method interceptors, or object checks. Real projects must test **`RoleHierarchyImpl`** and authorization managers directly as shown earlier rather than treating this simulation as production truth.

## 16. Common pitfalls when testing role hierarchies

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Closure unit test passes, API returns 403 | HTTP manager ignores `RoleHierarchy` or different matcher matched | Check `setRoleHierarchy`/factory/chain and active rule |
| HTTP GET passes while `@PreAuthorize` fails | `MethodSecurityExpressionHandler` missing H | Register version-appropriate handler and test via Spring proxy |
| `@WithMockUser` MANAGER shows only `ROLE_MANAGER` | Those are direct authorities, not closure | Test `getReachable...` or the authorization decision |
| Inheritance test still passes even with hierarchy removed | Fixture manually granted all permissions | Assign only direct roles in inheritance tests |
| Removed manager→approve yet admin still approves | Another edge, direct permission, or node still on H0 | Trace alternate reachable paths, raw auth, and policy version |
| Removed edge yet client still approves | Session/JWT holds stale direct permission, or node runs H0 | Inspect tokens/sessions, reload/restart, rollout |
| Tests check only 200 without testing DENY | Low roles may be exposed | Add negative matrix and no-side-effect assertions |
| Reversed `>` causes unexpected privilege growth | Misread `>` direction | Draw the graph before writing config |
| `hasRole("ROLE_MANAGER")` fails | `hasRole` prepends `ROLE_` automatically | Use `hasRole("MANAGER")` or `hasAuthority` with full name |
| `hasAuthority("report:read")` fails | Casing/prefix/claim mapping mismatch | Compare exact authority strings and test converter |
| `@Bean RoleHierarchy` exists yet custom manager does not expand | Custom manager iterates `getAuthorities` directly | Wire hierarchy into manager/factory or use another policy |
| `@WebMvcTest` differs from production | Slice missing security config/beans | Import required config or use `@SpringBootTest` |
| Method security misses self-invocation | Internal call bypasses proxy | Invoke from another bean through proxy |
| Edge changed yet runtime unchanged | Bean/manager/caches not reloaded | Controlled restart or atomic policy swap |
| Cycle in graph | Edges form a role loop | Fail startup and require graph review |
| Tenant A admin accesses tenant B | Role hierarchy does not check object scope | Enforce domain authorization and multi-tenant tests |
| Security test returns 403 due to CSRF | POST missing token when CSRF is active | Include `with(csrf())` in permission tests |

### 16.1. Five-step diagnostic workflow

1. **Inspect actual direct authorities** from the test principal or authentication converter (without logging credentials/tokens).
2. **Compute closure** using the exact `RoleHierarchy` instance in use.
3. **Identify the authorization checkpoint**: HTTP matcher/manager, method handler, or custom service.
4. **Verify integration**: does that checkpoint use the right hierarchy instance/config? Any other chain/proxy involved?
5. **Cross-check active policy version and authority sources**: sessions/JWTs, caches, stale nodes, or alternate edges reaching the permission.

Never “fix” an unexplained denial by granting `ROLE_ADMIN` to all users or switching to `anyRequest().permitAll()`.

## 17. Pre-deployment regression checklist

**Permission design:**

- [ ] Canonical role/permission names and consistent prefixes: `ROLE_ADMIN`, `ROLE_MANAGER`, `report:read`, `report:approve`.
- [ ] Every `A > B` edge reflects a business rule: A implies B, never backwards.
- [ ] Graph has no cycles, typos, or unintended transitive paths exposing permissions.
- [ ] A role→permission table distinguishes direct grants from derived ones.
- [ ] Object-level controls (tenant/owner/state/SoD) are enforced separately.

**Unit tests:**

- [ ] Exact closure tests for ADMIN/MANAGER/ANALYST/VIEWER.
- [ ] Tests for an unrelated role, a direct permission, and multiple direct authorities.
- [ ] Transitivity tests: ADMIN implies VIEWER and `report:read`.
- [ ] Negative tests: VIEWER never becomes ADMIN; ANALYST cannot approve.
- [ ] **H0→H1** tests: lost permissions, preserved permissions, and direct approve still working.

**Integration tests:**

- [ ] HTTP authorization manager/factory actually uses `RoleHierarchy`.
- [ ] `MethodSecurityExpressionHandler` actually uses `RoleHierarchy`.
- [ ] `@WithMockUser` assigns strictly the direct role when proving inheritance.
- [ ] POST/PATCH tests include valid CSRF tokens when CSRF is enabled.
- [ ] `SecurityFilterChain`, `RequestMatcher`, and AOP proxies are active during tests.
- [ ] 403/deny/no-side-effect cases are tested, not just 200 happy paths.
- [ ] Production JWT/session converters and raw authorities are tested with realistic claims.

**Changes and operations:**

- [ ] Policy delta table covers all affected source roles (including ADMIN above edited edges).
- [ ] Sensitive permissions are never re-granted simply to make new tests pass.
- [ ] Deployment/restart/reload strategy is defined for the hierarchy and all consumers.
- [ ] Stale sessions/JWTs, caches, and role revocations are tested per threat model.
- [ ] All nodes/services are verified to run the same policy version.
- [ ] Sensitive actions have proper auditing and rollback procedures.
- [ ] Non-HTTP paths are reviewed: scheduled jobs, event consumers, and service calls.

## 18. Self-check questions

**Question 1.** With `ROLE_ADMIN > ROLE_MANAGER > ROLE_ANALYST > ROLE_VIEWER`, is a user with only `ROLE_ADMIN` treated as VIEWER?

**Answer:** Yes, in authorization components configured to use the hierarchy. The authority is inferred across multiple edges. `Authentication.getAuthorities()` may still contain only direct `ROLE_ADMIN`.

**Question 2.** Can `ROLE_VIEWER` imply `ROLE_ADMIN`?

**Answer:** No. The `>` arrow runs from higher role to implied role with no reverse inference.

**Question 3.** Does `@WithMockUser(roles="MANAGER")` automatically add `report:approve` to raw authorities?

**Answer:** No. It creates the direct role inside `Authentication`. Hierarchy-aware authorization computes the derived permission from the graph; tests must not inject it manually into the fixture.

**Question 4.** `getReachableGrantedAuthorities(...)` unit tests pass, yet the API returns 403. Does that prove the hierarchy itself is broken?

**Answer:** Not yet. The HTTP manager may not use the hierarchy, another route matcher/chain may have matched, CSRF may block first, or a service/object policy denied it. Test the exact enforcement point.

**Question 5.** If `ROLE_MANAGER > report:approve` is removed, does only manager lose approve or does admin lose it too?

**Answer:** If no alternate path exists and admin has no direct `report:approve`, **both ADMIN and MANAGER** lose the approval derived through the removed edge.

**Question 6.** After removing that edge, Alice holds direct authorities `ROLE_MANAGER` and `report:approve`. Can Alice still approve?

**Answer:** Yes, under `hasAuthority("report:approve")` because her direct permission remains, assuming all other conditions pass. Revoking a direct permission requires updating the authority source.

**Question 7.** Can you conclude `ROLE_MANAGER` has `report:read` solely by inspecting `Authentication.getAuthorities()`?

**Answer:** No, if `Authentication` holds only direct roles. You must compute closure with H or evaluate through a hierarchy-integrated authorization component.

**Question 8.** Why should you not use `@WithMockUser(authorities={"ROLE_MANAGER","report:read"})` to prove hierarchy derives read access?

**Answer:** Because the permission was directly granted, the test still passes even when the hierarchy is inactive. Grant only `ROLE_MANAGER` in inference tests.

**Question 9.** After editing hierarchy text on disk, are all server nodes guaranteed to apply it immediately?

**Answer:** No. Beans/managers may still hold the old graph. Use deployment/restart or a synchronized, validated, tested reload mechanism.

**Question 10.** Can a user with derived `report:approve` approve another tenant's report?

**Answer:** No. Hierarchy only resolves functional permissions; domain policies must still verify tenant, owner, report status, and business constraints.

**Question 11.** Why must derived-permission tests include **negative** cases?

**Answer:** A wrong or reversed edge can grant permissions to lower roles. Checking only admin access misses such privilege escalation.

**Question 12.** In Spring Security 7, which API helps inject `RoleHierarchy` into centrally created managers?

**Answer:** `DefaultAuthorizationManagerFactory` exposes `setRoleHierarchy(...)`. Ensure your code actually uses the factory; custom managers do not inherit it automatically unless integrated.

**Conclusion:** To test role hierarchies properly, pinpoint **direct inputs**, the **permission graph**, the **reachable set**, and the **authorization checkpoints that actually consume that set**. Whenever the graph changes, write regression tests for **new grants, revoked grants, preserved grants, and forbidden escalations**. Ensure HTTP and method configurations share the same hierarchy, guard against stale tokens/instances, and keep tenant/owner checks at the service layer.

## Official references

- Spring Security — Authorization Architecture, Hierarchical Roles: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security — Method Security, RoleHierarchy and expression handler: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — RoleHierarchyImpl Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security 7.0 — RoleHierarchyImpl API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security 6.5 — AuthorityAuthorizationManager, setRoleHierarchy: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- Spring Security 7.0 — DefaultAuthorizationManagerFactory: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/DefaultAuthorizationManagerFactory.html
- Spring Security — MockMvc integration tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — @WithMockUser test annotation: https://docs.spring.io/spring-security/reference/servlet/test/method.html
