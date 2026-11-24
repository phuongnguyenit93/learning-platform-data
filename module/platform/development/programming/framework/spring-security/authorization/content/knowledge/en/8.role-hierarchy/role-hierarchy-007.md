# Avoiding Cycles, Overly Broad Implication, and Unintended Admin Privileges

> **Module:** Spring Security – authorization  
> **Parent topic:** Role hierarchy  
> **Objective:** Design and test cycle-free role inheritance graphs; prevent a single `ROLE_A > ROLE_B` edge from unintentionally expanding wide sets of permissions; and control risks around administrative accounts, sensitive permissions, and per-object authorization.

## 1. The problem: a single new edge can grant many additional permissions

Suppose an order-processing application has four roles:

- `ROLE_VIEWER`: views regular orders.
- `ROLE_SUPPORT`: handles customer support; includes viewer permissions.
- `ROLE_ADMIN`: administers certain system features; includes support permissions.
- `ROLE_PRIVACY_OFFICER`: exports personal data under a separate process.

Planned hierarchy:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read

ROLE_PRIVACY_OFFICER > pii:export
~~~

The notation `A > B` reads **A implies B**. A holder of `ROLE_ADMIN` can be treated as having `ROLE_SUPPORT`, `ROLE_VIEWER`, and `order:read` **when the authorization mechanism uses this `RoleHierarchy`**. However, admin **does not automatically get `pii:export`**, because that permission belongs to a separate branch.

A seemingly minor edit:

~~~text
ROLE_SUPPORT > pii:export
~~~

suddenly gives both `ROLE_SUPPORT` **and every role above it**, including `ROLE_ADMIN`, the right to export personal data. This is **overly broad implication**. Nobody may have touched an `/export` endpoint, and nobody may have granted `pii:export` directly to admin, yet **a transitive path in the graph** escalated privileges anyway.

This lesson requires three capabilities:

1. Reading the **effective permission graph**, not only directly declared edges.
2. Detecting and preventing **cycles** such as `ADMIN > SUPPORT > VIEWER > ADMIN`.
3. Preserving **least privilege** and **separation of duties**: admin is not by default a super-subject holding every sensitive capability.

## 2. How does role hierarchy work in Spring Security?

In Spring Security, an `Authentication` carries a set of direct `GrantedAuthority` instances. For example, an account is granted:

~~~text
Authentication.getAuthorities():
  ROLE_ADMIN
~~~

`RoleHierarchy` represents how one authority/role implies other authorities. Key API:

~~~java
Collection<? extends GrantedAuthority>
getReachableGrantedAuthorities(
    Collection<? extends GrantedAuthority> authorities);
~~~

With the hierarchy:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read
~~~

an input of `ROLE_ADMIN` can expand to:

~~~text
ROLE_ADMIN
ROLE_SUPPORT
ROLE_VIEWER
order:read
~~~

This is the **transitive closure** of the graph. Configuration authors may see no direct edge `ROLE_ADMIN > order:read`, yet a path exists through two intermediate roles, putting that permission into the reachable set.

### 2.1. The `>` sign means “implies”, not HR org-chart rank

~~~text
ROLE_ADMIN > ROLE_USER
~~~

Technically, this means a user with `ROLE_ADMIN` also passes authorization checks that the hierarchy maps through `ROLE_USER`. It does **not** inherently mean every admin should perform every user's real-world actions.

For instance, viewing one's own profile is a reasonable “user-level” capability; however, “approving one's own transaction”, “exporting customer data without approval”, or “editing locked accounting records” should never be granted automatically to an admin merely because their title sounds higher.

### 2.2. Direct authorities and reachable authorities differ

Distinguish clearly:

| Concept | Example | Meaning |
|---|---|---|
| Direct granted authority | `ROLE_ADMIN` | Value placed on `Authentication` by the authentication mechanism |
| Hierarchy edge | `ROLE_ADMIN > ROLE_SUPPORT` | Relationship configured in `RoleHierarchy` |
| Reachable authority | `ROLE_VIEWER`, `order:read` | Authority visible after transitive expansion |
| Authorization decision | `hasAuthority("order:read")` | Concrete check at HTTP/method policy |
| Object-level authorization | “may read order 42 in tenant A” | Resource policy; never derived automatically from hierarchy |

Certain Spring Security mechanisms can use the hierarchy to evaluate policies; **never assume custom code calling `authentication.getAuthorities().contains(...)` sees expanded authorities**. Whenever code reads the direct authority collection, verify whether it applies `RoleHierarchy`.

## 3. Directed graphs: the root cause of privilege escalation

Treat each role/authority as a vertex and each `A > B` as a directed edge from A to B.

~~~text
ROLE_ADMIN
    |
    v
ROLE_SUPPORT
    |
    v
ROLE_VIEWER
    |
    v
order:read

ROLE_PRIVACY_OFFICER
    |
    v
pii:export
~~~

When someone is assigned `ROLE_ADMIN`, their effective authority set includes every vertex reachable along outgoing edges. Adding one new edge can affect **all ancestor vertices**, not just the vertex directly at the tail of that edge.

For example, adding:

~~~text
ROLE_SUPPORT > pii:export
~~~

adds `pii:export` to `ROLE_ADMIN`'s effective set as well. This may go far beyond the editor's intent: they thought they only granted it to support staff, when in fact they granted it to every role that implies `ROLE_SUPPORT`.

**Every new edge must be reviewed as a permission-granting change**, not a harmless org-chart edit.

### 3.1. Distinguish “higher” from “broader permissions”

In many organizations, an “ADMIN” title administers configuration yet **must not** approve payments, read confidential content, or perform sensitive audit operations. A linear hierarchy:

~~~text
ROLE_SUPER_ADMIN > ROLE_ADMIN > ROLE_MANAGER > ROLE_STAFF > ROLE_USER
~~~

implicitly assumes every role on the left can do **everything** roles on the right can do. That is a very strong assumption and breaks down whenever functions carry legal, privacy, business, or approval constraints.

A better design usually separates branches:

~~~text
ROLE_SUPPORT > ROLE_VIEWER
ROLE_FINANCE_APPROVER > payment:approve
ROLE_PRIVACY_OFFICER > pii:export
ROLE_INFRA_ADMIN > infra:configure
~~~

Branches do not have to live inside one master inheritance chain. Many sensitive permissions should be granted independently, with auditing and runtime conditions.

## 4. What is a cycle and why must it be avoided?

A **directed cycle** exists if starting from a vertex and following edges leads back to that same vertex:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > ROLE_ADMIN
~~~

Representation:

~~~text
ADMIN --> SUPPORT --> VIEWER --> ADMIN
  ^                            |
  +----------------------------+
~~~

Consequences:

- The meaning of “higher role implies lower role” collapses: a role at the bottom can reach the role at the top.
- A user granted only `ROLE_VIEWER` can reach `ROLE_ADMIN` along edges, depending on implementation and where hierarchy applies.
- Hard to review, hard to explain permissions, and hard to write expected tests.
- Custom graph traversal code without a visited check can enter an infinite loop.
- Some library versions/implementations detect and reject cyclic hierarchies; **never rely on that in place of pre-deployment config validation**.

### 4.1. Direct and indirect cycles

Two dangerous examples:

~~~text
# Self-cycle:
ROLE_USER > ROLE_USER

# Two-way cycle:
ROLE_A > ROLE_B
ROLE_B > ROLE_A
~~~

And longer cycles:

~~~text
ROLE_A > ROLE_B
ROLE_B > ROLE_C
ROLE_C > ROLE_D
ROLE_D > ROLE_A
~~~

A large graph can contain a cycle without any two adjacent lines forming a symmetric pair. Therefore regex searches for `A > B` and `B > A` are **insufficient**. You need a cycle-detection algorithm over the entire edge set.

### 4.2. A DAG is a useful design constraint

A role graph should ideally be a **DAG – Directed Acyclic Graph**, meaning a directed graph with no cycles.

A DAG enables:

1. Consistent interpretation of the “implies” direction.
2. Auditable computation of reachable authority sets.
3. Topological ordering and clean diagram visualization.
4. Impact review whenever a new edge is proposed.
5. Unit tests asserting a lower role cannot reach a higher role.

A DAG alone **does not guarantee safety**. A completely acyclic DAG can still contain overly broad edges like `ROLE_USER > payment:approve`. Always combine **cycle validation** with a **least-privilege audit**.

## 5. Spring Security config example: transparent hierarchy

In Spring Security 6.x/7.x, you can create a `RoleHierarchy` bean using string syntax:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
class RoleHierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_SUPPORT
                ROLE_SUPPORT > ROLE_VIEWER
                ROLE_VIEWER > order:read
                ROLE_PRIVACY_OFFICER > pii:export
                """);
    }
}
~~~

This is a **configuration class inside a Spring Security project**, not a standalone Java program. Text blocks require Java 15+, so Java 17 runs it when Spring dependencies are present.

Lines are interpreted as **left implies right**. A user directly assigned `ROLE_ADMIN` reaches `ROLE_SUPPORT`, `ROLE_VIEWER`, and `order:read`; they do not reach `pii:export` from this hierarchy.

### 5.1. Builder API

In Spring Security 6.3+, you can use the builder when working strictly with roles sharing the default `ROLE_` prefix:

~~~java
@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.withDefaultRolePrefix()
            .role("ADMIN").implies("SUPPORT")
            .role("SUPPORT").implies("VIEWER")
            .build();
}
~~~

The builder applies the default prefix, so `ADMIN` represents `ROLE_ADMIN` under this API. Check exact-version docs before using `withRolePrefix(...)` if the system changes prefixes.

When an edge implies a **non-role permission**, `RoleHierarchyImpl.fromHierarchy("ROLE_ADMIN > some:permission")` is easier to express and matches Spring Security's method authorization examples. However, that makes reviewing **role → permission** edges even more critical, since one edge can directly expose sensitive actions to many users.

### 5.2. ROLE_ and reading `hasRole`/`hasAuthority`

Suppose `Authentication` holds `ROLE_ADMIN` and the hierarchy defines:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
~~~

- `hasRole("VIEWER")` normally checks `ROLE_VIEWER` after applying the configured hierarchy.
- `hasAuthority("ROLE_VIEWER")` checks that exact authority string when the authorization manager/handler uses the hierarchy.
- `hasAuthority("order:read")` succeeds only if granted directly or expanded through a relevant hierarchy edge **and** the checker uses the hierarchy.
- `hasRole("ROLE_VIEWER")` may behave differently across expression APIs and managers; under default conventions, applications pass role names **without** the prefix to `hasRole`.

Never mix `ROLE_VIEWER`, `VIEWER`, `SCOPE_read`, and `order:read` casually. Define clear authority namespaces, and test prefix changes across Spring versions/configurations.

### 5.3. Activating hierarchy at the right checkpoints

Spring Security supports hierarchies across many HTTP/method authorization mechanisms, though exact configuration details depend on version.

For example, when using **pre/post method security expressions**, Spring Security documentation shows:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy roleHierarchy) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(roleHierarchy);
    return handler;
}
~~~

This snippet is a **fragment inside a configuration class**; method security also requires `@EnableMethodSecurity` and Spring-managed methods invoked through interceptors/proxies. Publish the method security handler bean early per your version's guidance.

For HTTP `authorizeHttpRequests` and custom `AuthorizationManager` types, verify **whether the manager uses the `RoleHierarchy` bean** in your exact Spring Security version. Spring Security 7.x also introduces `AuthorizationManagerFactory` to customize role hierarchy, prefix, and trust resolver. Never assume “a `RoleHierarchy` bean exists, so every custom helper uses it automatically”.

## 6. Risks of putting every permission into the hierarchy

Some teams write:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_USER
ROLE_USER > profile:read
ROLE_USER > orders:read
ROLE_SUPPORT > pii:export
ROLE_SUPPORT > refunds:approve
ROLE_ADMIN > users:manage
~~~

This graph **needs no cycle** to be dangerous:

- `ROLE_SUPPORT` gets `pii:export` and `refunds:approve`.
- `ROLE_ADMIN` implies `ROLE_SUPPORT`, so it inherits both sensitive permissions too.
- A user with `ROLE_ADMIN` can pass `hasAuthority("refunds:approve")` when managers apply the hierarchy, even if the designer thought admin meant only “system administration”.
- If controllers/services lack ownership/tenant/approval policies, permissions can be abused beyond intended scope.

### 6.1. A “before and after” comparison table

With the safe graph:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read
ROLE_PRIVACY_OFFICER > pii:export
~~~

| Direct role | order:read | pii:export | Meaning |
|---|---|---|---|
| `ROLE_VIEWER` | Yes | No | Read orders only |
| `ROLE_SUPPORT` | Yes | No | Inherits read permission |
| `ROLE_ADMIN` | Yes | No | Admin does not implicitly export PII |
| `ROLE_PRIVACY_OFFICER` | Not from this hierarchy | Yes | Separate PII handling branch |

After adding `ROLE_SUPPORT > pii:export`:

| Direct role | order:read | pii:export | Change |
|---|---|---|---|
| `ROLE_VIEWER` | Yes | No | Unchanged |
| `ROLE_SUPPORT` | Yes | **Yes** | Grants PII export |
| `ROLE_ADMIN` | Yes | **Yes** | **Indirectly grants access**, easy to overlook |
| `ROLE_PRIVACY_OFFICER` | Not from this hierarchy | Yes | Unchanged |

During reviews, do not ask only “which edge was added?”; ask “**which new permissions do all ancestor roles** of the edge source receive?”.

### 6.2. Functional permissions differ from per-record permissions

Even when `order:read` is intentionally implied, it **does not** let an admin read every order across every tenant. You must still evaluate:

- Tenant membership and organizational scope.
- Ownership or sharing relationships.
- Resource state, locks, and access expiration.
- Whether the object contains sensitive/PII data vs. regular data.
- Workflow conditions, such as dual approval.
- Strong authentication assurance, step-up/MFA, or trusted device checks.

Hierarchy answers “which effective authorities does the subject hold?”; resource policy answers “does that authority apply to **this resource**, **this action**, in **this context**?”.

## 7. Admin roles should not be “allowed to do everything”

A `ROLE_SUPER_ADMIN > ROLE_EVERYTHING` design looks convenient, yet easily lets **system administration** spill over into **business operations**.

Consider separating branches:

~~~text
ROLE_SUPPORT_LEAD > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > order:read

ROLE_FINANCE_APPROVER > payment:approve
ROLE_PRIVACY_OFFICER > pii:export
ROLE_INFRA_ADMIN > infra:configure
ROLE_USER_ADMIN > users:manage
~~~

Here:

- Support lead receives ordinary support permissions.
- Finance approver approves payments according to workflow rules.
- Privacy officer can export PII **when business conditions are satisfied**.
- Infra admin manages infrastructure without thereby becoming a finance approver.
- User admin manages accounts/roles within assigned scope without implicitly reading private business data.

This turns the hierarchy from a single role tower into a **responsibility-branched graph**.

### 7.1. Separation of duties – isolating critical responsibilities

Refund workflow example:

1. Employee A creates a refund request.
2. Authorized employee B approves it.
3. The system prevents A from approving a request A created, even if A holds an admin role.
4. Large transactions may require two distinct approvers.
5. Actions are audited and may require step-up authentication.

Checking `hasAuthority("refund:approve")` alone cannot enforce “approver must differ from creator”. That belongs in **object/context-level policy**.

**Never try to solve separation of duties with hierarchy alone.** Conversely, a hierarchy giving `refund:create` and `refund:approve` to the same role easily erodes independent checks.

### 7.2. Emergency/break-glass access

In some systems, emergency operators need special privileges. Rather than baking all sensitive permissions permanently into `ROLE_ADMIN`, use:

- A dedicated approval or escalation workflow.
- Short-lived temporary grants.
- Risk-based step-up authentication/MFA.
- Constrained action and resource scopes.
- Auditing, alerts, and post-incident review.
- Automatic expiration and revocation.

`ROLE_BREAK_GLASS` is not safe merely because of its name. Adding an edge so every admin implies it defeats the entire emergency-control design.

## 8. Cycles can turn low roles into high roles

Look at a broken configuration:

~~~text
ROLE_ADMIN > ROLE_SUPPORT
ROLE_SUPPORT > ROLE_VIEWER
ROLE_VIEWER > ROLE_ADMIN
~~~

If an authorization checker computes reachability on a graph without blocking cycles, then:

- Starting from `ROLE_ADMIN`, you reach `ROLE_SUPPORT` and `ROLE_VIEWER`.
- Starting from `ROLE_VIEWER`, a path also reaches `ROLE_ADMIN`.
- The meaning of a low/restricted role disappears: a viewer satisfies “admin reachable” checks.

**Practical warning:** current Spring Security implementations/versions may detect cycles during hierarchy construction or handle them differently; do not claim every version accepts them and grants access. From a **policy design** standpoint, any cyclic declaration must be treated as an error and blocked in the pipeline before deployment.

Write dedicated validation in CI or startup tests rather than relying on “this version happened to throw”. After upgrading Spring Security, re-test invalid config behavior; never disable tests just because one version threw an exception.

## 9. How to detect cycles in a graph

A standard approach is **three-state depth-first search**:

| Vertex state | Meaning |
|---|---|
| 0 / unvisited | Processing has not started |
| 1 / visiting | Currently on the active DFS stack |
| 2 / visited | Subgraph completed safely |

Rules:

1. For each unvisited vertex, mark it as visiting.
2. Traverse outgoing edges to child vertices.
3. If you encounter a **visiting** vertex (state 1), an edge loops back into the active path → **cycle**.
4. If you encounter a visited vertex (state 2), skip it as already verified.
5. Once all children finish, mark the vertex state 2.

Time complexity with adjacency lists is **O(V + E)** for V vertices and E edges. **Kahn's algorithm / topological sort** also detects cycles: if fewer than V vertices can be emitted in topological order, a cycle exists. Either method in CI suffices, provided tests cover self-loops, two-node cycles, and longer cycles.

### 9.1. Do not check cycles alone

After confirming the graph is a DAG, compute the transitive closure (effective privileges) for every directly assignable role and run:

- **Forbidden reachability**: which roles must strictly never reach which permissions?
- **Sensitive permission review**: did any role unexpectedly reach `payment:approve`, `pii:export`, or `users:grant-admin`?
- **Separation-of-duties review**: does any single role hold both create and approve rights for an action?
- **Privilege delta**: compare effective permissions before and after the pull request.
- **Orphan/missing rule**: do undeclared or misspelled roles/permissions cause unintended denials?
- **Path-independent coverage**: do endpoints still enforce service/object-level policies?

An acyclic graph containing `ROLE_EVERYONE > admin:grant` is still dangerous. Thus DAG validity is a **necessary structural condition**, never proof that the overall policy is sound.

## 10. Standalone Java 17: auditing the graph, detecting cycles, and catching over-broad grants

The following program runs in **standard Java without Spring**, helping illustrate graphs, transitive closure, and unexpected sensitive grants. It is not the source code of `RoleHierarchyImpl` and **does not replace** Spring integration tests. It uses `TreeMap`/`TreeSet` for deterministic output ordering.

Create `RoleGraphAuditDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class RoleGraphAuditDemo {
    static Map<String, Set<String>> graph(List<String> edges) {
        Map<String, Set<String>> result = new TreeMap<>();
        for (String edge : edges) {
            String[] parts = edge.split("\\s*>\\s*");
            if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
                throw new IllegalArgumentException("Invalid edge: " + edge);
            }
            result.computeIfAbsent(parts[0], key -> new TreeSet<>())
                    .add(parts[1]);
            result.computeIfAbsent(parts[1], key -> new TreeSet<>());
        }
        Map<String, Integer> state = new HashMap<>();
        for (String role : result.keySet()) {
            check(role, result, state);
        }
        return result;
    }

    static void check(String node, Map<String, Set<String>> edges,
                      Map<String, Integer> state) {
        if (state.getOrDefault(node, 0) == 1) {
            throw new IllegalArgumentException("Cycle at " + node);
        }
        if (state.getOrDefault(node, 0) == 2) {
            return;
        }
        state.put(node, 1);
        for (String next : edges.getOrDefault(node, Set.of())) {
            check(next, edges, state);
        }
        state.put(node, 2);
    }

    static Set<String> reachable(Map<String, Set<String>> graph, String start) {
        Set<String> found = new TreeSet<>();
        ArrayDeque<String> queue = new ArrayDeque<>();
        queue.add(start);
        while (!queue.isEmpty()) {
            String current = queue.removeFirst();
            if (found.add(current)) {
                queue.addAll(graph.getOrDefault(current, Set.of()));
            }
        }
        return found;
    }

    public static void main(String[] args) {
        List<String> safeEdges = List.of(
                "ROLE_ADMIN > ROLE_SUPPORT",
                "ROLE_SUPPORT > ROLE_VIEWER",
                "ROLE_VIEWER > order:read",
                "ROLE_PRIVACY_OFFICER > pii:export"
        );
        Map<String, Set<String>> safe = graph(safeEdges);
        System.out.println("SAFE admin: " + reachable(safe, "ROLE_ADMIN"));
        System.out.println("SAFE privacy: "
                + reachable(safe, "ROLE_PRIVACY_OFFICER"));
        System.out.println("SAFE admin may export PII: "
                + reachable(safe, "ROLE_ADMIN").contains("pii:export"));

        List<String> badEdges = new ArrayList<>(safeEdges);
        badEdges.add("ROLE_SUPPORT > pii:export");
        Map<String, Set<String>> bad = graph(badEdges);
        System.out.println("BAD admin may export PII: "
                + reachable(bad, "ROLE_ADMIN").contains("pii:export"));

        List<String> cyclicEdges = new ArrayList<>(safeEdges);
        cyclicEdges.add("ROLE_VIEWER > ROLE_ADMIN");
        try {
            graph(cyclicEdges);
            System.out.println("CYCLE unexpectedly accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("CYCLE blocked: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 RoleGraphAuditDemo.java
java RoleGraphAuditDemo
~~~

Verified output:

~~~text
SAFE admin: [ROLE_ADMIN, ROLE_SUPPORT, ROLE_VIEWER, order:read]
SAFE privacy: [ROLE_PRIVACY_OFFICER, pii:export]
SAFE admin may export PII: false
BAD admin may export PII: true
CYCLE blocked: Cycle at ROLE_ADMIN
~~~

### Interpreting the output

- **SAFE admin:** holds direct and reachable authorities, without `pii:export`.
- **SAFE privacy:** separate role holds `pii:export`, not inherited from admin.
- **SAFE admin may export PII: false:** negative test proving no hidden path grants the permission.
- **BAD admin may export PII: true:** adding just `ROLE_SUPPORT > pii:export` propagated the sensitive permission up to admin.
- **CYCLE blocked:** adding `ROLE_VIEWER > ROLE_ADMIN` created a cycle; DFS caught it by revisiting an active node.

This is an educational example: its parser reads a curated edge list using a simple `split`. When applying CI checks to real data, validate configuration format, reject malformed values, handle case/prefixes, duplicates, and role/permission sources. For large graphs or untrusted input, prefer iterative traversal to avoid deep recursion.

## 11. Testing with Spring Security: real reachable authorities

After testing the pure Java graph, add a test using **the real Spring Security dependency** rather than guessing API versions and role-prefix semantics.

JUnit 5 test example in a module with Spring Security:

~~~java
import java.util.Collection;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RoleHierarchyTest {
    private final RoleHierarchy hierarchy =
            RoleHierarchyImpl.fromHierarchy("""
                    ROLE_ADMIN > ROLE_SUPPORT
                    ROLE_SUPPORT > ROLE_VIEWER
                    ROLE_VIEWER > order:read
                    ROLE_PRIVACY_OFFICER > pii:export
                    """);

    private Set<String> effective(String role) {
        Collection<? extends GrantedAuthority> reached =
                hierarchy.getReachableGrantedAuthorities(
                        Set.of(new SimpleGrantedAuthority(role)));
        return reached.stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    void adminInheritsReadButNotPiiExport() {
        assertTrue(effective("ROLE_ADMIN").contains("order:read"));
        assertTrue(effective("ROLE_ADMIN").contains("ROLE_VIEWER"));
        assertFalse(effective("ROLE_ADMIN").contains("pii:export"));
    }

    @Test
    void viewerDoesNotBecomeAdmin() {
        assertFalse(effective("ROLE_VIEWER").contains("ROLE_ADMIN"));
    }

    @Test
    void privacyOfficerHasItsOwnPermission() {
        assertTrue(effective("ROLE_PRIVACY_OFFICER")
                .contains("pii:export"));
        assertFalse(effective("ROLE_PRIVACY_OFFICER")
                .contains("ROLE_ADMIN"));
    }
}
~~~

This is a **test class depending on JUnit 5 and Spring Security**, not a plain Java program. Expected results hold if your actual version provides the shown API. It verifies transitive closure in Spring's `RoleHierarchyImpl`, but does not yet prove HTTP rules or method interceptors at runtime **use that hierarchy**.

### 11.1. Integration tests for HTTP and method security

At the HTTP layer:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/orders/**").hasAuthority("order:read")
        .anyRequest().denyAll());
~~~

Once `RoleHierarchy` is properly wired into the authorization infrastructure, tests must confirm a user with only `ROLE_ADMIN` passes `order:read` **if that is the intended design**, yet cannot pass `pii:export`. Also, a user with only `ROLE_VIEWER` must be denied at `/api/admin/**`.

At the method layer:

~~~java
@PreAuthorize("hasAuthority('order:read')")
public OrderDto read(long id) {
    return orderService.read(id);
}
~~~

Enable `@EnableMethodSecurity`, configure the expression handler/hierarchy properly, invoke the service through its Spring proxy/interceptor (no self-invocation), and enforce per-object checks. Never assume annotations guard self-calls inside the same instance under proxy-based method security.

**Tests must run through the real security chain**, not only `getReachableGrantedAuthorities`. Never test with a mock user carrying every authority and claim hierarchy works; test users should hold **only direct roles** to genuinely prove transitivity.

## 12. Test matrix: unwanted permissions are the focus

| Test case | Direct authority | Policy check | Expected |
|---|---|---|---|
| Admin reads normal order | `ROLE_ADMIN` | `order:read` | Allow at role layer if hierarchy is wired properly |
| Viewer reads order | `ROLE_VIEWER` | `order:read` | Allow at role layer |
| Viewer hits admin URL | `ROLE_VIEWER` | `ROLE_ADMIN` | Deny |
| Support hits admin URL | `ROLE_SUPPORT` | `ROLE_ADMIN` | Deny |
| Admin exports PII data | `ROLE_ADMIN` | `pii:export` | **Deny** in the safe model |
| Privacy officer exports PII | `ROLE_PRIVACY_OFFICER` | `pii:export` | Allow at authority layer; still must satisfy workflow |
| Admin reads another tenant's order | `ROLE_ADMIN` | Permission + object policy | Deny without tenant scope |
| Creator self-approves | Role with `refund:approve` | Workflow separation-of-duties | Deny when policy forbids self-approval |
| Spoofed role in request | Header/body `ROLE_ADMIN` | Authentication | Untrusted |
| Cyclic hierarchy | Any | Build/CI validation | Reject configuration before release |
| Edge added exposing `pii:export` | `ROLE_ADMIN` | Effective-permission diff | Regression test must fail |
| Session/JWT missing permission update | Old authority | Recently revoked sensitive permission | Must obey revocation/freshness strategy |

**Do not test only allow cases.** The strongest defense against privilege escalation is **testing denies** across every unauthorized role, especially for high-risk permissions.

## 13. Applying in CI: audit graph changes like security API changes

A hierarchy testing pipeline should run in order:

~~~text
Read ROLE/permission edges from configuration
    |
    v
Validate syntax, prefixes, and valid role names
    |
    v
Build directed graph
    |
    +--> Detect self-loop / cycle --> FAIL BUILD
    |
    v
Compute reachable authorities for direct roles
    |
    +--> Compare against forbidden permissions --> FAIL BUILD
    |
    +--> Check separation-of-duties --> REVIEW/FAIL
    |
    +--> Diff before/after PR --> REPORT DELTA
    |
    v
Run Spring Security unit + HTTP/method integration tests
    |
    v
Security review with business owners
    |
    v
Deploy, runtime audit, and alert on permission changes
~~~

### 13.1. How do effective permissions change?

For each role `R`, compute:

~~~text
effective_before(R)
effective_after(R)

newly_granted(R) = effective_after(R) - effective_before(R)
removed(R)       = effective_before(R) - effective_after(R)
~~~

For example, a change adding `ROLE_SUPPORT > pii:export`:

~~~text
newly_granted(ROLE_SUPPORT) = {pii:export}
newly_granted(ROLE_ADMIN)   = {pii:export}
newly_granted(ROLE_VIEWER)  = {}
~~~

Key point: **reviewers must see every ancestor role** whose permissions expand. If tooling prints only the newly added direct edge, reviewers easily underestimate its blast radius.

### 13.2. Sensitive permissions list

You can maintain an explicit allowlist/denylist per policy:

~~~text
ROLE_ADMIN:
  FORBID pii:export
  FORBID refund:self_approve

ROLE_SUPPORT:
  FORBID user:grant_admin
  FORBID payment:approve

ROLE_VIEWER:
  FORBID write:orders
  FORBID pii:export
  FORBID infra:configure
~~~

This is a **policy illustration**, not standard Spring Security syntax. Actual permissions must be agreed upon by security and business teams. Never maintain a tiny blacklist assuming everything else is safe: you still need an **allowlist of permitted rights** and change reviews.

### 13.3. Approving privilege changes

Edits creating edges to `users:grant_admin`, `pii:export`, `payment:approve`, or `infra:configure` should require dedicated review, or even two approvers per organizational policy. Audit logs should record proposer, approver, affected roles, and test outcomes.

A “typo” in a hierarchy file can be just as dangerous a privilege change as editing a `@PreAuthorize` annotation. Code reviews must never treat hierarchy definitions as benign UI metadata.

## 14. Constraints poorly represented by role hierarchies

Hierarchies suit **static, global** permission relationships; they fall short for dynamic conditions:

| Condition | Why hierarchy is insufficient | How to handle |
|---|---|---|
| Tenant A user must not read tenant B | Roles carry no specific resource constraints | Service policy, tenant-scoped queries |
| Creator cannot self-approve | Depends on actor vs. record creator | Separation-of-duties policy |
| Approve only below a monetary threshold | Depends on transaction amount | Contextual authorization |
| Permission active only during shift | Depends on time / shift schedule | Dynamic policy, time-bound grants |
| Only MFA-verified admin performs risky action | Depends on authentication assurance | Step-up/MFA policy |
| User locked after login | Account state may have changed | Session/token revocation, real-time checks |
| No PII access except for specific purpose | Depends on access purpose/audit | Purpose-bound authorization, workflow |
| Requires two distinct approvals | Depends on events and distinct actors | Transaction workflow / approval service |

Roles/permissions can combine with `@PreAuthorize` or custom `AuthorizationManager`, keeping resource logic close to service/use-case boundaries. Never turn thousands of object IDs into thousands of roles/authorities inside a hierarchy.

### 14.1. When the system needs ABAC or ReBAC

When policies depend on subject, resource, context attributes, or relationships, consider **ABAC (Attribute-Based Access Control)** or **ReBAC (Relationship-Based Access Control)** alongside RBAC.

Example:

~~~text
allow read(order) if:
  actor authenticated
  AND actor has order:read
  AND actor.tenantId == order.tenantId
  AND (actor is owner OR actor is shared OR actor has special tenant-level permission)
~~~

The hierarchy can provide `order:read`, while tenant and relationship checks still run. A system admin should not automatically bypass every condition without an approved, audited request.

## 15. Unintended admin privileges: other escalation paths

Even when a DAG does not directly grant sensitive permissions, administrators can **indirectly** gain privileges if they hold overly broad account, role, configuration, or credential management permissions.

Examples:

- `ROLE_ADMIN > users:grant_role`: admin can grant themselves `ROLE_FINANCE_APPROVER` if the service does not block self-granting.
- `ROLE_ADMIN > policies:edit`: admin can alter authorization rules to grant themselves extra rights.
- `ROLE_ADMIN > token:mint`: can mint high-scope tokens if issuance policies are unlocked.
- `ROLE_ADMIN > audit:disable`: can suppress audit trails around sensitive actions.
- `ROLE_ADMIN > backup:download`: indirectly reads all data/PII via backups.
- `ROLE_ADMIN > users:impersonate`: can act under another principal if controls are missing.

Therefore an **effective privilege audit** must also examine **permissions that enable granting further permissions**, not only direct “read/write” permissions. Sometimes configuration management carries greater effective power than PII export.

### 15.1. Guardrails for granting and impersonation

Constraints worth enforcing:

1. User managers **must not escalate their own privileges** without an independent workflow.
2. Nobody can grant a role higher than their own delegated scope.
3. High-privilege grants require strong authentication and auditing.
4. Impersonation permissions carry strict scope/expiry and log both the original actor and the impersonated subject.
5. Disallow silent policy/audit edits or logging disablement.
6. Enforce checks at the **service layer** even if the UI hides admin buttons.
7. Never let gateway/client headers assert roles in place of authentication.
8. Break-glass accounts are constrained, monitored, and revoked per procedure.

These guardrails live in business logic and infrastructure; they do not appear automatically by putting `ROLE_ADMIN` into a hierarchy.

## 16. Runtime freshness: effective authorities may be stale

A system using sessions or JWTs:

~~~text
09:00  Lan logs in; authentication contains ROLE_ADMIN.
09:05  Hierarchy configuration is updated so ROLE_ADMIN implies a new permission.
09:07  Request arrives using the old ROLE_ADMIN authentication.
~~~

Depending on where the hierarchy is evaluated and when configuration reloads, the request may see the new permission even without changing the token/session, because the **new implication relationship** is evaluated at authorization time. Conversely, if authorities are materialized into tokens at issuance, old tokens retain old authorities until refresh.

This highlights that **changing a hierarchy is a runtime authorization change**, not merely a user data edit.

When revoking a permission:

- Verify the new hierarchy actually removes all reachable paths to that permission.
- Verify users were not also granted the permission directly outside the hierarchy.
- Inspect sessions/tokens, role caches, method security caches, and relevant `AuthorizationManager` instances.
- Design token lifetimes, revocation, or live permission sources when sensitive permissions require fast revocation.
- Verify all services run the same policy version, especially across microservices.

**Never equate** “updated role in database” with “all active requests lost access immediately”. Authentication storage and where hierarchy is applied determine permission freshness.

## 17. Signs of a problematic configuration

| Sign | Why it is concerning | Fix |
|---|---|---|
| Contains `ROLE_A > ROLE_A` | Self-cycle, nonsensical semantics | Block in CI |
| Contains `ADMIN > USER > ADMIN` | Cycle lets low roles reach high roles | Detect cycles, redesign |
| One role implies dozens of sensitive permissions across domains | Privilege creep | Split role branches, grant narrow permissions |
| `ROLE_ADMIN > ROLE_FINANCE_APPROVER` with no business need | Admin can approve payments | Remove edge, apply separate policy |
| `ROLE_USER > pii:export` | PII export exposed to large user base | Review grants and restrict |
| High role inherits every lower role | Breaks separation of duties | Group by responsibility |
| Only testing that admin can do everything | Misses low-role escalation | Add deny tests for viewer/support |
| Using one `users:manage` permission for all user operations | Enables self-admin grant | Split `users:view`, `users:update`, `roles:grant`, self-grant policy |
| Allowing role assignment via client header | Privilege spoofing | Authenticate from trusted sources |
| Hierarchy bean exists yet method checks ignore it | Behavior diverges from expectations | Test manager/handler integration |
| Skipping effective-permission inspection on edge edits | Overlooks transitive grants | Diff reachable sets for every role |
| JWT/session not refreshed on revocation | Stale access persists unexpectedly | Revocation/freshness strategy |
| Checking only roles without tenant/owner | BOLA/IDOR | Enforce per-resource policies |
| Stuffing every permission into hierarchy instead of object auth | Policy becomes overly static | ABAC/ReBAC/workflows |

## 18. Guide for reviewing a pull request that adds an edge

Suppose a PR contains this diff:

~~~diff
 ROLE_ADMIN > ROLE_SUPPORT
 ROLE_SUPPORT > ROLE_VIEWER
+ROLE_SUPPORT > pii:export
~~~

Reviewers should require answers to:

**A. Business justification:** Why do **all** support staff need `pii:export`? Are there legal/compliance rules governing personal data?

**B. Ancestor roles:** Which roles imply `ROLE_SUPPORT` directly or transitively? Are admin, supervisor, temporary roles, or service accounts included?

**C. Permission delta:** What is each role's new effective permission set? Did unintended people gain sensitive permissions?

**D. Object scope:** Does that permission allow exporting PII across all tenants, or does it require purpose, scope, expiration, and owner approval?

**E. Separation of duties:** Can someone holding that role grant permissions, approve exports, and execute exports without independent review?

**F. Testing:** Are there negative tests for regular admins, support, and viewers? Are cycle checks present? Are there integration tests against the real Spring Security version?

**G. Observability:** Are auditing, alerts on new permission usage, and rollback capability sufficient?

A PR is accepted **not merely because the build reports no cycle error**. It must prove the permission change is intentional and obeys least privilege.

## 19. Mandatory pre-release checklist

- [ ] Every edge `A > B` follows the agreed “A implies B” meaning across the model.
- [ ] Authority names, `ROLE_` prefixes, and permission strings are exact with no ambiguous collisions.
- [ ] The graph has no self-loops, two-way cycles, or multi-hop cycles.
- [ ] CI tooling computes transitive closure for every directly assignable role.
- [ ] A report lists **newly granted** permissions per role after changes.
- [ ] Sensitive permissions have dedicated allowlists and negative tests.
- [ ] Infrastructure admins are not implicitly approvers, auditors, or privacy officers.
- [ ] Accounts with grant/impersonation permissions are guarded against self-escalation.
- [ ] Dual-approval actions have dedicated service/workflow policies.
- [ ] Tenant/owner/relationship policies are enforced at the data layer.
- [ ] HTTP and method layers use the same version-appropriate hierarchy.
- [ ] Tests use direct roles and derived roles; avoid mocking users with all authorities pre-populated.
- [ ] Tests prove anonymous and low-privilege roles cannot access admin endpoints.
- [ ] Tests prove admin cannot use `pii:export` unless explicitly intended for admin.
- [ ] JWT/session/cache and revocation policies are verified.
- [ ] Auditing, monitoring, and rollback procedures exist for hierarchy changes.

**Short rule:** *No cycles, no overly broad implicit grants, no omnipotent default admin, and always check real resource permissions.*

## 20. Self-check questions

**1. Does `ROLE_ADMIN > ROLE_SUPPORT` mean support receives admin permissions?**  
No. The direction `>` means admin implies support, not the reverse.

**2. If `ROLE_SUPPORT > pii:export` is added, can admin receive that permission?**  
Yes, if admin implies support and the checker uses the hierarchy; the permission propagates transitively.

**3. Is an acyclic graph guaranteed to be safe?**  
No. A DAG can still grant `payment:approve` to an inappropriate role.

**4. Why must `ROLE_VIEWER > ROLE_ADMIN` in the hierarchy above be blocked?**  
It introduces a cycle allowing viewers to reach admin in the reachability model, breaking hierarchical boundaries.

**5. Where should cycle detection run?**  
In CI/startup validation via DFS/Kahn alongside configuration tests; do not wait for the first live request to fail.

**6. Why should an admin role not imply all permissions?**  
Because system configuration differs from financial approval, PII handling, auditing, and duties requiring separation.

**7. Does having `order:read` mean you can view all orders across all tenants?**  
No. Services must enforce per-resource, owner, and tenant checks.

**8. Does checking `authentication.getAuthorities()` alone guarantee seeing hierarchy-expanded authorities?**  
No. Direct authorities and reachable authorities differ; checkers must use the hierarchy properly.

**9. Do you need tests for a user granted only `ROLE_VIEWER`?**  
Yes. Negative tests proving viewer cannot reach admin catch reversed edges and cycles.

**10. Can editing the hierarchy affect existing sessions/JWTs?**  
Potentially, depending on whether hierarchy is evaluated at authorization time or authorities are materialized ahead of time. Test freshness and revocation.

## 21. Official references

- Spring Security – **Authorization Architecture**, *Hierarchical Roles* section and HTTP/method authorization integration: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **RoleHierarchyImpl JavaDoc**, `fromHierarchy`, `withDefaultRolePrefix`, `getReachableGrantedAuthorities`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security – **RoleHierarchy JavaDoc**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchy.html
- Spring Security – **Method Security**, especially role hierarchy and permission expressions: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Servlet Authentication Architecture**, `GrantedAuthority`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
