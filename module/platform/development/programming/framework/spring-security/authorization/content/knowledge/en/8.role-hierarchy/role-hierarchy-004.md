# Wiring Role Hierarchy into AuthorizationManager by Version

## 1. The problem: role hierarchy is declared, yet rules still deny?

In Spring Security, many applications have hierarchical roles: administrators can perform some staff actions, and staff can read viewer data. Instead of assigning every lower role directly to every user, we define a **role hierarchy**.

Example:

```text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_READER
    |
    v
report:read

ROLE_AUDITOR
    |
    v
audit:view
```

The arrow means **the role/authority above implies the authority below**. If a user is directly granted `ROLE_ADMIN`, a hierarchy-aware check can treat that user as also having `ROLE_MANAGER`, `ROLE_READER`, and `report:read`.

However, a very common problem occurs:

1. The application declares a `RoleHierarchy` bean.
2. HTTP rules use `.hasAuthority("report:read")`; method annotations use `@PreAuthorize("hasRole('READER')")`.
3. The user only has `ROLE_ADMIN` in `Authentication.getAuthorities()`.
4. Some requests/methods are allowed while others return 403.

The root cause can be **different `AuthorizationManager` instances using different hierarchy configurations, a custom manager not applying the hierarchy at all, or configuration APIs changing across Spring Security versions**.

This lesson focuses on **wiring the role hierarchy into the right decision point**, specifically distinguishing Spring Security 6.x and 7.x, rather than stopping at how to write the `ROLE_ADMIN > ROLE_USER` string.

### Decision chain to understand

```text
Trusted identity source (DB / IdP / JWT / session)
                  |
                  v
Authentication
  direct authorities: [ROLE_ADMIN]
                  |
                  v
AuthorizationManager
  + RoleHierarchy wired properly?
                  |
         +--------+--------+
         |                 |
        Yes               No
         |                 |
         v                 v
  Reachable authorities   Direct authorities only
  [ROLE_ADMIN, ...]        [ROLE_ADMIN]
         |                 |
         v                 v
  hasRole("READER")       hasRole("READER")
       true                    false
```

**Important:** a hierarchy is a way to **evaluate which authorities are reachable from granted permissions**, not a mutation that permanently rewrites the base permission set stored in the identity source. `Authentication.getAuthorities()` may still return only `ROLE_ADMIN` even when the manager uses the hierarchy to permit `ROLE_READER`.

## 2. Understanding RoleHierarchy, GrantedAuthority, and AuthorizationManager

| Component | Responsibility | Example |
| --- | --- | --- |
| `GrantedAuthority` | A verified authority attached to a principal | `ROLE_ADMIN` |
| `RoleHierarchy` | Computes reachable authorities via implication relationships | `ROLE_ADMIN > ROLE_READER` |
| `RoleHierarchyImpl` | Standard implementation of `RoleHierarchy` | `fromHierarchy(...)` |
| `AuthorityAuthorizationManager<T>` | Evaluates role/authority requirements against `Authentication` | `hasRole("READER")` |
| `AuthorizationManager<T>` | Decision contract over a protected target | Request or method invocation |
| `RequestMatcherDelegatingAuthorizationManager` | Selects a manager per URL/method during HTTP authorization | `/api/reports/**` |
| `DefaultMethodSecurityExpressionHandler` | Builds SpEL context for `@PreAuthorize`, `@PostAuthorize` | `hasAuthority('report:read')` |
| `AuthorizationManagerFactory<T>` | Creates managers with shared config in Spring Security 7.0+ | `hasRole(...)`, `hasAuthority(...)` |
| `Authentication` | Carries principal and authorities produced by authentication | `ROLE_ADMIN`, `SCOPE_reports.read` |

A role hierarchy **is not** an identity source. It does not verify tokens, look up users, know record owners, or guarantee that someone authorized in tenant A is also authorized in tenant B.

### 2.1. Arrow direction matters

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_READER
ROLE_READER > report:read
```

This means:

- A holder of `ROLE_ADMIN` implies `ROLE_MANAGER`, `ROLE_READER`, and `report:read`.
- A holder of `ROLE_MANAGER` implies `ROLE_READER` and `report:read`; **not** `ROLE_ADMIN`.
- A holder of `ROLE_READER` implies `report:read`; **not** management permissions.
- A holder of only `report:read` does not thereby gain `ROLE_READER`.

Hierarchy is **transitive**: if A implies B and B implies C, then A implies C. Never write relationships backwards, as that causes real privilege escalation.

### 2.2. `hasRole` vs. `hasAuthority`

With the default role prefix:

- `hasRole("ADMIN")` normally checks for `ROLE_ADMIN`.
- `hasRole("READER")` normally checks for `ROLE_READER`.
- `hasAuthority("ROLE_READER")` checks for the exact name `ROLE_READER`.
- `hasAuthority("report:read")` checks for the exact name `report:read`.
- `hasAuthority("SCOPE_reports.read")` checks for the exact name `SCOPE_reports.read`, which is not equivalent to `report:read`.

A **properly hierarchy-wired** manager can evaluate authorities reachable along the graph. A manager without a hierarchy may only inspect direct authorities. Therefore, verify not only **string names**, but also **which manager executes the check**.

Do not habitually pass `hasRole("ROLE_ADMIN")` into default APIs that prepend `ROLE_` automatically. Consistently use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")`. If the app overrides the prefix via `GrantedAuthorityDefaults` or a custom factory, make sure role names, mappers, and the hierarchy stay synchronized.

### 2.3. Roles and permissions can coexist in the hierarchy

Not every node has to carry the `ROLE_` prefix. Spring Security's method security documentation includes an equivalent example:

```text
ROLE_ADMIN > permission:read
```

However, distinguish **declaring with full strings** from **using the role-prefixing builder**. If the goal is linking a role to arbitrary permissions like `report:read`, `RoleHierarchyImpl.fromHierarchy("ROLE_READER > report:read")` is direct and clear. The prefixed builder fits better when all nodes are **roles**.

## 3. Why is “by version” central here?

Spring Security's authorization APIs evolved across multiple generations. How a hierarchy is attached to managers, where managers are created, and how decision methods are invoked are not completely identical.

| Version group | Notable mechanism | Mindset when integrating hierarchy |
| --- | --- | --- |
| Classic Spring Security 5.x | `authorizeRequests`, `FilterSecurityInterceptor`, `AccessDecisionManager`/voters, and expression handlers | Verify the exact hierarchy consumer; do not copy modern configs |
| 6.0–6.2 | Prefers `authorizeHttpRequests` and `AuthorizationManager`; method security via `@EnableMethodSecurity` | Use APIs actually present in the locked version; do not assume newer builders exist |
| 6.3 | `RoleHierarchyImpl.withDefaultRolePrefix()`/`withRolePrefix()` introduced; manager wiring still uses 6.x APIs | Can declare `RoleHierarchy` and wire it explicitly into managers |
| 6.4–6.5 | `AuthorizationManager.authorize(...)`/new result types introduced; legacy `check(...)` still shown in 6.5 docs; HTTP/method hierarchy support | Inspect which managers are DSL-built, which are manual, and expression handlers |
| 7.0+ | Introduces `AuthorizationManagerFactory<T>` and `DefaultAuthorizationManagerFactory<T>` to configure created managers | Define factory/roleHierarchy per 7.x APIs; do not paste 6.x patterns verbatim |
 
**Do not mix 6.x and 7.x configuration patterns together via copy-paste.** They represent integration styles from different API models. In real implementations, check your dependency lockfile/Maven or Gradle build, confirm the exact Spring Security version, and choose one matching approach.

If a project is still on Spring Security 5.x or 6.0–6.2, check the exact Javadoc for that version before reaching for 6.3 builders or 7.0 factories. Never upgrade a framework version solely to copy a small snippet without a compatibility plan.

## 4. Declaring RoleHierarchyImpl properly

### 4.1. Full-string syntax: suited for roles and permissions

For Spring Security 6.3/6.5, for example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy("""
        ROLE_ADMIN > ROLE_MANAGER
        ROLE_MANAGER > ROLE_READER
        ROLE_READER > report:read
        """);
}
```

This is a **fragment inside a `@Configuration` class**, using a Java 17 text block; it requires the Spring Security dependency. It defines the relationships:

- `ROLE_ADMIN` has all permissions of `ROLE_MANAGER`.
- `ROLE_MANAGER` has all permissions of `ROLE_READER`.
- `ROLE_READER` has `report:read`.

`fromHierarchy(String)` accepts the definition as a string. Do not confuse `>` with Java's numeric comparison operator; this is hierarchy graph syntax parsed by Spring Security.

### 4.2. Role-prefixed builder: Spring Security 6.3+

When working strictly with roles sharing a prefix:

```java
RoleHierarchy hierarchy = RoleHierarchyImpl
    .withDefaultRolePrefix()
    .role("ADMIN").implies("MANAGER")
    .role("MANAGER").implies("READER")
    .build();
```

The default-prefix builder produces relationships equivalent to `ROLE_ADMIN > ROLE_MANAGER > ROLE_READER`. API docs confirm `withDefaultRolePrefix()` and `withRolePrefix(String)` were introduced in **6.3**.

**Do not** write `.role("READER").implies("report:read")` expecting a raw `report:read` permission without verifying how the builder applies prefixes; use `fromHierarchy` with full authority names or build an explicit mapping instead. The builder is not a generic tool for inferring arbitrary tenants or structured permissions.

### 4.3. Checking closure before wiring into managers

Observing the output:

```java
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

var reached = roleHierarchy.getReachableGrantedAuthorities(
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

With the graph above, `reached` contains `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_READER`, and `report:read`. Collection ordering should not be a test constraint; compare **sets of authority strings**.

This step only verifies the **graph is right**. It does not prove HTTP authorization or `@PreAuthorize` is using that hierarchy; those checkpoints must be tested separately.

### 4.4. Cycles, over-broad access, and validity

If cyclic relationships are written, such as A > B and B > A, the hierarchy cannot express a meaningful order. Implementations like `RoleHierarchyImpl` in documented versions detect cycles during graph construction and can throw a configuration exception.

Never try to “fix” it by suppressing errors or making every role imply admin. A hierarchy change is a **security policy change**; it requires code review, denied-access tests, and verification of who receives new indirect authorities.

## 5. Spring Security 6.x: wiring directly into AuthorityAuthorizationManager

This is an **explicit, easily testable** pattern for a manually constructed HTTP rule: build the manager, call `setRoleHierarchy(...)`, and pass it to `authorizeHttpRequests(...).access(...)`.

For Spring Security 6.5, the Javadoc of `AuthorityAuthorizationManager` confirms `setRoleHierarchy(RoleHierarchy)`. The 6.5 docs also describe hierarchy usage in `authorizeHttpRequests`. For managers you instantiate yourself, explicit configuration avoids guessing whether the framework automatically discovers the hierarchy bean for **that custom manager**.

### 5.1. Example configuring HTTP and method security with one hierarchy

This is a **Spring Security 6.5 / Spring Boot 3.x integration configuration class**, not a standalone Java program. It assumes the application has an appropriate authentication provider, report controller, and real business data.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableMethodSecurity
public class RoleHierarchySecurity6Config {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_READER
            ROLE_READER > report:read
            """);
    }

    // For @PreAuthorize/@PostAuthorize: configure the expression handler.
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy hierarchy) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(hierarchy);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RoleHierarchy hierarchy) throws Exception {

        AuthorityAuthorizationManager<RequestAuthorizationContext>
            reportReader =
                AuthorityAuthorizationManager.hasAuthority("report:read");

        // IMPORTANT WIRING POINT for a manually created manager.
        reportReader.setRoleHierarchy(hierarchy);

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET, "/api/reports", "/api/reports/**"
            ).access(reportReader)
            .requestMatchers(HttpMethod.GET, "/public/**")
                .permitAll()
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Step by step:

1. `RoleHierarchy` is **a single policy bean**. There is one graph definition in this example.
2. `reportReader` is an `AuthorityAuthorizationManager<RequestAuthorizationContext>` built with `hasAuthority("report:read")`.
3. `reportReader.setRoleHierarchy(hierarchy)` wires the graph into **this specific manager**. A user with direct authority `ROLE_ADMIN` can satisfy `report:read` via reachability.
4. `.access(reportReader)` uses the configured manager instead of letting the DSL create another manager that misses the hierarchy. This is the key integration point in the example.
5. `@EnableMethodSecurity` and `MethodSecurityExpressionHandler` configure hierarchy evaluation for method pre/post authorization expressions.
6. `anyRequest().denyAll()` closes undeclared URLs/methods **in this chain**; if using multiple chains, each still needs an appropriate fallback protecting the application.

**Scope note:** this configuration focuses solely on authorization. It includes no form login/JWT resource server, CSRF, CORS, error entry points, or object policies. Do not copy it to production assuming authentication is already handled.

### 5.2. Can `.access(reportReader)` be replaced with `.hasAuthority("report:read")`?

In certain versions and configurations, Spring Security supports discovering a `RoleHierarchy` bean for DSL-built managers. The 6.5 docs describe configuring hierarchy for HTTP. However, when building **an example guaranteeing that a specific manager has the hierarchy**, we explicitly pass the manager via `.access(...)`.

Distinguish clearly:

```text
requestMatchers(...).hasAuthority("report:read")
  -> DSL creates/chooses AuthorizationManager automatically
  -> must verify version and hierarchy injection mechanism

requestMatchers(...).access(reportReader)
  -> Uses the manager where we explicitly called setRoleHierarchy
  -> Behavior is easy to observe and unit test directly
```

Do not conclude that because the Spring context has a `RoleHierarchy` bean, **every custom `AuthorizationManager` in the codebase uses it automatically**. If a custom manager manually loops over `authentication.getAuthorities()` and compares strings, it has no hierarchy behavior unless its logic calls `RoleHierarchy` or is designed equivalently.

### 5.3. Testing the manager directly in Spring Security 6.x

JUnit fragment example (requires Spring Security and JUnit libraries; does not run standalone with `javac`):

```java
RoleHierarchy hierarchy = RoleHierarchyImpl.fromHierarchy("""
    ROLE_ADMIN > ROLE_MANAGER
    ROLE_MANAGER > ROLE_READER
    ROLE_READER > report:read
    """);

AuthorityAuthorizationManager<Object> manager =
    AuthorityAuthorizationManager.hasAuthority("report:read");

manager.setRoleHierarchy(hierarchy);

Authentication admin =
    new UsernamePasswordAuthenticationToken(
        "alice", "N/A",
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );

AuthorizationDecision decision =
    manager.check(() -> admin, new Object());

assertNotNull(decision);
assertTrue(decision.isGranted());
```

The test must import `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `AuthorizationDecision`, `RoleHierarchy`, `RoleHierarchyImpl`, `List`, and JUnit static assertions. In Spring Security 6.5, `check(...)` is still the API shown in the docs; **do not copy this test signature verbatim to 7.x when the API changes**.

Write a control test without calling `setRoleHierarchy`: if the user only holds `ROLE_ADMIN` and the manager checks raw `report:read`, the result is denied. That test neatly confirms **the exact difference caused by wiring the hierarchy**.

### 5.4. Method security in 6.x: another wiring point

If a service has:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView readReport(long reportId) {
    // Query scoped by tenant and object permissions.
}
```

then the same `roleHierarchy` must be supplied to method security expressions, e.g., via `DefaultMethodSecurityExpressionHandler#setRoleHierarchy` as in section 5.1. For `@Secured` and JSR-250, dedicated managers support hierarchies in corresponding versions; do not assume one expression handler bean automatically customizes all annotation types in every configuration.

If `@EnableMethodSecurity` is not enabled, `@PreAuthorize` has no effect merely from having Spring Security on the classpath. If a method is called via self-invocation inside the same instance, the Spring AOP proxy can also be bypassed. Test methods through the bean/proxy and continue enforcing tenant/owner rules at the data layer.

### 5.5. Hierarchy expands authorities without changing JWT data

If a Resource Server principal only carries `SCOPE_reports.read`, a hierarchy graph containing `ROLE_ADMIN > ...` will never synthesize `ROLE_ADMIN`. Conversely, a JWT with claim `roles:["ADMIN"]` does not automatically become `ROLE_ADMIN` without a proper claim-to-authority converter.

Separate the stages clearly:

```text
Verified JWT
 -> JwtAuthenticationConverter/authority mapper
 -> Direct Authentication authorities
 -> AuthorizationManager + RoleHierarchy
 -> permission decision
 -> resource policy (tenant/owner)
```

Never add a shortcut like “if the token contains any admin role text, grant ROLE_ADMIN” without verifying issuer, audience, claim trustworthiness, and an approved mapping table.

## 6. Spring Security 7.x: wiring hierarchy into AuthorizationManagerFactory

Spring Security **7.0 introduces `AuthorizationManagerFactory<T>`**, per the project's Authorization Architecture docs. Its goal is to provide a shared configuration point for managers created across request-based and method-based authorization, instead of calling setters manually on each DSL-created manager.

A standard implementation is `DefaultAuthorizationManagerFactory<T>`. It lets you configure:

- `RoleHierarchy`.
- Role prefix (commonly `ROLE_`).
- `AuthenticationTrustResolver` and other manager-creation settings per the actual API.

### 6.1. Factory configuration in Spring Security 7.x style

This is an **integration fragment for Spring Security 7.x**, separate from the 6.x configuration class above:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;

@Configuration
public class RoleHierarchySecurity7Config {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_READER
            ROLE_READER > report:read
            """);
    }

    @Bean
    <T> AuthorizationManagerFactory<T> authorizationManagerFactory(
            RoleHierarchy hierarchy) {

        DefaultAuthorizationManagerFactory<T> factory =
            new DefaultAuthorizationManagerFactory<>();
        factory.setRoleHierarchy(hierarchy);
        return factory;
    }
}
```

Per the 7.x docs: the factory is injected where Spring Security constructs standard `AuthorizationManager` instances. When using DSLs/annotations backed by that factory, they share a consistent hierarchy policy.

**Do not treat the factory bean as proof that every authorization checkpoint in the app is updated.** Manually constructed custom managers, customized expression handlers, `PermissionEvaluator`-based rules, data security, secondary library versions, or multi-config method security setups still need verification. For `@PreAuthorize` SpEL, the docs also cover configuring `MethodSecurityExpressionHandler` with the hierarchy; verify real behavior with integration tests rather than assuming the factory's presence in the context covers everything.

### 6.2. Manager decision API in 7.x

In 6.x, many tutorials use:

```java
AuthorizationDecision result =
    manager.check(authenticationSupplier, context);
```

In Spring Security 7.x documentation, the contract centers on:

```java
AuthorizationResult result =
    manager.authorize(authenticationSupplier, context);
```

Both snippets are **fragments illustrating API differences**, not standalone Java programs, and require their respective type imports. Do not mass-replace `check` with `authorize` or vice versa across a project without checking your active version's signatures.

Distinguish:

- **Hierarchy configuration:** the graph and where it is attached to the factory/manager.
- **Decision execution:** `check(...)` vs. `authorize(...)` depending on version.
- **Result handling:** checking granted/denied, handling abstain/null results where applicable, and throwing/dispatching appropriate errors.

For new 7.x code, prefer the documented 7.x API; for active 6.5 projects, there is no need to prematurely rewrite everything around 7.x factories.

### 6.3. Prefix and role builder in 7.x

If using `DefaultAuthorizationManagerFactory.setRolePrefix(...)` with a value other than `ROLE_`, synchronize it with:

- `GrantedAuthority` names emitted by authentication converters/IdP mappers.
- How `hasRole(...)` evaluates inside created managers.
- `RoleHierarchyImpl.withRolePrefix(...)` or full-string graph definitions.
- Custom managers and policy rules across other layers.

Do not change the prefix in one place and expect all authorities to rename themselves automatically. When a hierarchy contains permissions like `report:read`, full-string definitions are usually less error-prone.

### 6.4. Why does a factory prevent “rule A knows hierarchy, rule B does not”?

When standard managers are created from one shared factory, hierarchy and prefix settings are managed centrally rather than calling setters per route. However:

- Custom managers bypassing the factory can still ignore the hierarchy.
- A `hasAuthority("report:approve")` manager does not magically permit admins unless the hierarchy defines a path to `report:approve`.
- Method security with a custom expression handler still needs review.
- Tenant and object-level permissions do not emerge from the role graph.

The factory **standardizes manager construction**; it does not replace modeling business policy accurately.

## 7. Comparing the two configuration styles from a security perspective

| Criterion | 6.x with explicit manager | 7.x with factory |
| --- | --- | --- |
| Integration unit | A specific `AuthorityAuthorizationManager<T>` | Central factory creating supported `AuthorizationManager<T>` instances |
| Graph wiring point | `manager.setRoleHierarchy(roleHierarchy)` | `factory.setRoleHierarchy(roleHierarchy)` |
| HTTP usage | `requestMatchers(...).access(manager)` | DSL managers built by the 7.x factory |
| Custom managers | Must wire or integrate explicitly | Custom managers outside the factory still need handling |
| Method security | Inspect `MethodSecurityExpressionHandler`/interceptors | Inspect factory and version-specific expression handling |
| Debugging 403 | Which manager ran? Does it have the hierarchy? | Which factory built the manager? Any custom override? |
| Testing | 6.x unit test `manager.check(...)` + MockMvc | 7.x manager/DSL tests via `authorize(...)` + MockMvc |
| What neither replaces | Identity trust, object authorization | Identity trust, object authorization |

The invariant similarity: **you still need a reviewed role hierarchy, trusted authentication, explicit permissions, and tests for both permit and deny**.

## 8. Standalone Java 17 simulation: verifying transitive permissions

To understand the exact algorithm conceptually, run this pure Java program. It requires no Spring Security; it models a role/authority graph and uses **BFS** to compute reachable authorities.

Save `RoleHierarchyManagerDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class RoleHierarchyManagerDemo {
    private static final Map<String, Set<String>> IMPLIES = Map.of(
        "ROLE_ADMIN", Set.of("ROLE_MANAGER"),
        "ROLE_MANAGER", Set.of("ROLE_READER"),
        "ROLE_READER", Set.of("report:read"),
        "ROLE_AUDITOR", Set.of("audit:view")
    );

    record Actor(String id, String tenantId, Set<String> granted) {}

    static Set<String> reachable(Set<String> granted) {
        if (granted == null) {
            return Set.of();
        }

        Set<String> result = new HashSet<>();
        Deque<String> pending = new ArrayDeque<>(granted);

        while (!pending.isEmpty()) {
            String authority = pending.removeFirst();
            if (result.add(authority)) {
                pending.addAll(
                    IMPLIES.getOrDefault(authority, Set.of())
                );
            }
        }

        return Set.copyOf(result);
    }

    static boolean hasAuthority(
            Actor actor, String required) {
        return actor != null
            && required != null
            && reachable(actor.granted()).contains(required);
    }

    static boolean canRead(
            Actor actor, String reportTenant) {
        return actor != null
            && reportTenant != null
            && reportTenant.equals(actor.tenantId())
            && hasAuthority(actor, "report:read");
    }

    static void display(String label, Set<String> granted) {
        System.out.println(
            label + ": " + new TreeSet<>(reachable(granted))
        );
    }

    public static void main(String[] args) {
        Actor admin = new Actor(
            "a", "tenant-A", Set.of("ROLE_ADMIN")
        );
        Actor manager = new Actor(
            "m", "tenant-A", Set.of("ROLE_MANAGER")
        );
        Actor reader = new Actor(
            "r", "tenant-A", Set.of("ROLE_READER")
        );
        Actor auditor = new Actor(
            "u", "tenant-A", Set.of("ROLE_AUDITOR")
        );

        display("admin effective", admin.granted());
        display("manager effective", manager.granted());
        display("auditor effective", auditor.granted());
        display("unknown effective", Set.of("ROLE_UNKNOWN"));

        System.out.println(
            "admin reads tenant-A: " + canRead(admin, "tenant-A")
        );
        System.out.println(
            "admin reads tenant-B: " + canRead(admin, "tenant-B")
        );
        System.out.println(
            "auditor reads tenant-A: " + canRead(auditor, "tenant-A")
        );
        System.out.println(
            "reader reads tenant-A: " + canRead(reader, "tenant-A")
        );
        System.out.println(
            "admin approves: "
                + hasAuthority(admin, "report:approve")
        );
    }
}
```

Run with JDK 17 or newer:

```bash
javac RoleHierarchyManagerDemo.java
java RoleHierarchyManagerDemo
```

Expected output:

```text
admin effective: [ROLE_ADMIN, ROLE_MANAGER, ROLE_READER, report:read]
manager effective: [ROLE_MANAGER, ROLE_READER, report:read]
auditor effective: [ROLE_AUDITOR, audit:view]
unknown effective: [ROLE_UNKNOWN]
admin reads tenant-A: true
admin reads tenant-B: false
auditor reads tenant-A: false
reader reads tenant-A: true
admin approves: false
```

Explanation:

1. The graph walks transitively from `ROLE_ADMIN` down to `report:read`, so admin gets read permission via the hierarchy even without being directly granted the permission string.
2. Auditor has `audit:view` but not `report:read`. Disjoint subgraphs never create permissions outside declared edges.
3. An unknown role in the graph still contains only itself; it never escalates to admin.
4. Admin has read permission but **not** `report:approve`, because no edge to it is declared in the example. A high role in one branch does not automatically imply every permission in the system.
5. Admin still cannot read tenant B's report despite having `report:read`: that is a condition **outside the hierarchy** and must be enforced per resource.
6. Wrapping with `TreeSet` when printing keeps authority ordering deterministic in stdout.

**Program limitations:** the illustrative BFS tracks visited nodes to avoid infinite loops, but does not detect configuration cycles like `RoleHierarchyImpl`; it has no real `Authentication`, JWT decoder, or Spring `AuthorizationManager`. Use it to study **reachability**, then test real managers and filters/methods in your Spring application.

## 9. Consistent integration across HTTP, method, and object permissions

### 9.1. HTTP and method security do not automatically share one manager

Suppose:

```text
HTTP rule: GET /api/reports/** -> hasAuthority("report:read")
Service:   @PreAuthorize("hasAuthority('report:read')")
User:      direct authorities [ROLE_ADMIN]
Hierarchy: ROLE_ADMIN > ROLE_READER > report:read
```

If the HTTP manager has the hierarchy while the method expression handler does not, a request can pass HTTP and fail with 403 at the service. Conversely, if method security knows the hierarchy while HTTP does not, the user gets rejected before reaching the service.

Therefore test **both layers separately**, not just `RoleHierarchy.getReachableGrantedAuthorities(...)` in a unit test. The goal is for a single principal and functional policy to carry identical authority meaning across every checkpoint.

### 9.2. A high role does not bypass object-level authorization

Suppose a user has `ROLE_ADMIN` and the hierarchy leads to `report:read`, yet report 17 belongs to another tenant. The final decision may be:

```text
ALLOW =
  authenticated
  AND reachedAuthority("report:read")
  AND sameTenant(principal, report)
  AND canReadThisReport(principal, report)
```

Never let admins read every tenant just because the word “ADMIN” sounds privileged. If the system genuinely has a global admin role, require explicit policies, approvals, auditing, MFA/step-up, and data-boundary tests.

### 9.3. SoD and sensitive permissions

A role hierarchy is an **implication relationship**, not a mechanism for handling role conflicts or separation of duties. If `ROLE_APPROVER > ROLE_CREATOR` in a workflow requiring creator and approver to be distinct individuals, the hierarchy expands functional authorities but **does not enforce** the “cannot self-approve” rule.

You must still check actor, creator, status/limits, and approval tiers at the service/transaction layer. Never invent a mega-role `ROLE_SUPERADMIN` implying all sensitive permissions just to silence 403 errors, as that constitutes a serious privilege change.

### 9.4. JWTs, groups, and multi-tenant policies

If the identity provider emits tenant-specific groups/roles:

- Map roles only after verifying issuer, audience, and claim source.
- Never map a tenant A role to a global application authority if the role's actual scope is only tenant A.
- Never treat a JWT scope `SCOPE_reports.read` and an app role `ROLE_READER` as synonyms unless an explicit policy mapping exists.
- Do not let a role hierarchy apply across all APIs/tenants when groups share names across different namespaces.
- When roles are embedded in sessions/JWTs, design revocation and caching separately; editing a hierarchy or group membership does not vanish existing tokens.

In fine-grained authorization systems, tenant-scoped permissions should be modeled in an explicit policy/permission store rather than crammed into a single context-free global hierarchy.

## 10. Testing to confirm which managers actually received the hierarchy

### 10.1. Functional matrix

| Direct principal | Expected hierarchy | Rule | Outcome when manager is wired properly |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | ADMIN ⇒ MANAGER ⇒ READER ⇒ `report:read` | `hasRole("MANAGER")` | Allow |
| `ROLE_ADMIN` | Same as above | `hasRole("READER")` | Allow |
| `ROLE_MANAGER` | MANAGER ⇒ READER ⇒ `report:read` | `hasAuthority("report:read")` | Allow |
| `ROLE_READER` | READER ⇒ `report:read` | `hasRole("ADMIN")` | Deny |
| `ROLE_AUDITOR` | AUDITOR ⇒ `audit:view` | `hasAuthority("report:read")` | Deny |
| `ROLE_UNKNOWN` | No edges | `hasRole("READER")` | Deny |
| `ROLE_ADMIN` | Same as above | `hasAuthority("report:approve")` | Deny |
| `ROLE_ADMIN` | Same as above | Read report in another tenant | Deny per object policy |
| Unauthenticated | No valid authorities | Protected report endpoint | Rejected |
| Valid role but inactive account | Depends on auth/account status | Protected report endpoint | Blocked per policy |

Each row holds **when the same graph and manager actually apply the hierarchy**. If behavior differs, inspect which manager is executing rather than hurriedly granting extra authorities to the principal.

### 10.2. Standalone graph test

With the `RoleHierarchy` bean:

```java
Set<String> reached = roleHierarchy
    .getReachableGrantedAuthorities(
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    )
    .stream()
    .map(GrantedAuthority::getAuthority)
    .collect(Collectors.toSet());

assertTrue(reached.contains("ROLE_MANAGER"));
assertTrue(reached.contains("ROLE_READER"));
assertTrue(reached.contains("report:read"));
assertFalse(reached.contains("report:approve"));
```

This is a **JUnit test fragment**; it requires importing `RoleHierarchy`, `SimpleGrantedAuthority`, `GrantedAuthority`, `List`, `Set`, `Collectors`, and assertions. It validates only the hierarchy definition and does not prove HTTP or method security applied it.

### 10.3. MockMvc verifying HTTP decisions

In a Spring MVC app with `spring-security-test`, simulate a principal carrying **only ROLE_ADMIN** to verify whether the `report:read` rule is satisfied via the hierarchy.

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Inside a @Test with MockMvc, controller, and report fixture:
mockMvc.perform(get("/api/reports/17")
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isOk());
```

This test returns 200 only when the controller, fixture, authentication, and object policy align; in production, report 17 must belong to Alice's scope. `user(...).roles("ADMIN")` creates `ROLE_ADMIN` in the test without assigning `ROLE_READER`. **If 200 succeeds purely because `ROLE_ADMIN` was expanded inside the manager**, that provides solid integration evidence.

Write control tests with `roles("READER")` or `roles("UNKNOWN")`; unauthorized authenticated users must receive 403 with zero side effects. For JWT resource server APIs, test helper `jwt()` mocks authorities without validating real signatures/audiences, so test the decoder separately.

### 10.4. Method security tests

Given a service bean annotated with:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView readReport(long id) { ... }
```

Invoke it directly through the Spring bean/proxy with `@WithMockUser(roles="ADMIN")`, `roles="READER"`, and `roles="AUDITOR"`. Do not test by instantiating the service with `new` outside the Spring context or self-invoking inside the same instance, as both can bypass the proxy.

If HTTP tests pass while method tests deny, inspect `MethodSecurityExpressionHandler#setRoleHierarchy` and your version's configuration beans. If method tests pass while HTTP denies, inspect the managers produced by the HTTP DSL, custom factories, and `.access(...)` rules.

### 10.5. Version upgrade tests

Before and after upgrading from 6.x to 7.x, the same test suite should cover:

1. Do higher-role users properly inherit lower-role permissions?
2. Do lower-role users **fail** to obtain higher-role permissions?
3. Do custom HTTP managers still apply the same hierarchy?
4. Do `@PreAuthorize`/`@Secured`/JSR-250 still enforce the expected rules?
5. Have any role prefixes changed, especially regarding `ROLE_` and `SCOPE_`?
6. Do tenant, owner, and approval workflows still block access when hierarchy expands functional permissions?
7. Are there any compile errors from missing `check`/`authorize` or factory APIs?
8. Did any rule accidentally degrade into `permitAll()` or plain `authenticated()` during config refactoring?
9. Did hierarchy edits expand the set of users holding sensitive permissions?
10. Do non-HTTP paths (jobs, message consumers) still enforce service policies?

## 11. Diagnosing 403 when hierarchy is already configured

Diagnosis should never be “add `ROLE_READER` to every admin user just to be safe”. Follow the chain:

```text
Principal from a trusted authentication source?
  |
  v
Authentication.getAuthorities() contains ROLE_ADMIN?
  |
  v
RoleHierarchy bean/graph has ADMIN > ... > report:read?
  |
  v
getReachableGrantedAuthorities([ROLE_ADMIN]) is right?
  |
  v
WHICH manager is executing at this checkpoint?
  |
  +-- HTTP DSL .hasAuthority(...)?
  +-- HTTP custom .access(manager)?
  +-- @PreAuthorize expression handler?
  +-- @Secured / JSR250?
  +-- Spring Security 7 factory?
  +-- Custom manager reading raw authorities directly?
  |
  v
Did that manager receive the same hierarchy?
  |
  v
Do the rule's role prefix and authority string match?
  |
  v
Does object policy (tenant/owner/status) allow it?
  |
  v
ALLOW / DENY and record appropriate reason
```

### 11.1. Common symptoms and causes

| Symptom | Possible cause | What to inspect |
| --- | --- | --- |
| `RoleHierarchy` test passes, HTTP 403 | HTTP manager missing hierarchy | Check `setRoleHierarchy`/factory/DSL |
| HTTP allows, `@PreAuthorize` denies | Method expression handler missing hierarchy | Check `@EnableMethodSecurity` and handler |
| Role `ADMIN` lacks `ROLE_ADMIN` | Naming/prefix mismatch | Compare `GrantedAuthority` against matcher |
| Manager grants low role high permissions | Reversed `>` edge or wrong mapping | Review graph and deny tests |
| `ROLE_ADMIN` does not imply `report:approve` | Graph has no edge to that permission | This may actually be the intended policy |
| JWT only has `SCOPE_reports.read` | No `ROLE_ADMIN` in authority source | Inspect JWT mapper and claim trust |
| Custom manager still returns 403 | Compares raw `Authentication.getAuthorities()` | Integrate hierarchy directly or use standard manager |
| Only one tenant gets 403 | Object policy/tenant scope | Never modify global hierarchy to bypass tenant checks |
| Compile/class error after upgrading to 7.x | Mixing 6.x and 7.x APIs | Pick the exact factory/authorize API for your version |
| Hierarchy updated but old sessions keep access | Sessions/tokens hold stale effective permissions | Implement proper refresh/revocation |
| 403 on POST despite correct role | Possible CSRF error | Isolate CSRF tests from authorization tests |

### 11.2. Proper logging without leaks

Minimal logs should record correlation ID, rule name, allow/deny outcome, verified issuer (if relevant), reason code, and tenant per policy. Never log raw JWTs, passwords, session cookies, or full sensitive claims. There is no need to dump the entire graph per request; version and audit the graph configuration separately.

## 12. Common mistakes and lessons learned

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Defining `RoleHierarchy` bean and trusting custom managers use it automatically | HTTP/method mismatch | Wire managers explicitly or use an appropriate factory, and test |
| Treating `AuthorityAuthorizationManager.setRoleHierarchy` as the sole 7.x API | Harder upgrades, ignoring new factory | Configure using your pinned version's API |
| Copying `AuthorizationManagerFactory` into 6.x | Class/API does not exist | Factory was introduced in 7.0 |
| Using 6.3 builder in older Spring Security | Compile failure | Check version and pick existing APIs |
| Calling `hasRole("ROLE_ADMIN")` under default conventions | Prefix mismatch/wrong contract | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Writing role hierarchy edges backwards | Low roles gain escalated access | Test both permit and deny |
| Mixing `SCOPE_` and `ROLE_` without mapping | Scopes misinterpreted as roles | Separate sources and transform authorities intentionally |
| Creating mega-roles to “stop 403s” | Unnecessary exposure | Design minimal permissions with security review |
| Relying on hierarchy to cross tenants | IDOR/BOLA | Enforce tenant/owner at service/data layers |
| Assuming hierarchy mutates `Authentication.getAuthorities()` | Confusion between direct and indirect authorities | Inspect `getReachableGrantedAuthorities` and managers |
| Looping over raw authorities in custom manager | Misses inheritance | Call `RoleHierarchy` or use standard managers |
| Unit testing the graph only | Unknown whether HTTP/method wired it | Integration test every checkpoint |
| Ignoring self-invocation | Method annotations skipped | Test through Spring AOP proxies |
| Cycles or unintended graph paths | Config error or tangled permissions | Validate DAG, fail fast on startup, review |
| Replacing SoD with hierarchy | Self-approval/workflow violations | Keep independent service policies |
| Revoking a group and assuming JWT/session changed immediately | Stale access persists until expiry | Use revocation/TTL/authority reload |
| Replacing failing rules with `authenticated()` | Exposes sensitive endpoints | Diagnose manager, prefix, CSRF, and object policies |

## 13. Practical implementation workflow

1. **Confirm the version.** Check Maven/Gradle dependency trees or the project BOM to confirm Spring Security 6.x vs. 7.x. Never guess from Spring Boot version names alone.
2. **Design the graph.** Define `ROLE_A > ROLE_B` and `ROLE_X > permission:y` edges with business owners; specify valid hierarchy levels and permissions that **must not** be inherited.
3. **Choose the graph construction API.** Spring 6.3+ offers the role-prefixed builder; `fromHierarchy(String)` is explicit for full authority strings.
4. **Integrate HTTP.** In Spring Security 6.x with manual managers, call `setRoleHierarchy` and pass them to `.access(...)`. In 7.x, configure the factory per docs and verify DSL managers actually use it.
5. **Integrate method security.** Enable `@EnableMethodSecurity`, configure the expression handler/manager appropriately, and test `@PreAuthorize`.
6. **Verify prefixes.** Keep `ROLE_` roles, `SCOPE_` JWT scopes, and raw permissions distinct.
7. **Preserve object policies.** Maintain tenant/owner/share/status/SoD rules; prevent the role graph from turning into unintended global access.
8. **Unit test the graph directly.** Confirm the reachable set matches expectations with no forbidden paths.
9. **Test HTTP + method layers.** Cover sufficient roles, lower roles, unknown roles, wrong tenants, unauthenticated users, and sensitive actions.
10. **Govern changes.** Role hierarchy is an access policy; require review, CI regression tests, auditing, and rollback readiness on deployment.
11. **Monitor and revoke.** Manage sessions/JWTs/caches, permission lifecycles, and audit trails; handle role revocations and graph updates cleanly.
12. **Re-verify after upgrades.** Read exact-version Javadocs for factories, `check/authorize` methods, and hierarchy-aware managers.

## 14. Practice exercises

### Exercise 1 — Predict transitive permissions

Given `ROLE_ADMIN > ROLE_MANAGER > ROLE_READER > report:read`, predict the effective authorities for a user with only `ROLE_MANAGER`. Identify authorities that are **not** inherited. Then run `RoleHierarchyManagerDemo.java` and compare.

### Exercise 2 — HTTP manager with vs. without hierarchy

On Spring Security 6.5, create two `AuthorityAuthorizationManager<Object>` instances both requiring `report:read`. Call `setRoleHierarchy` on only one of them. Test both with a principal carrying only `ROLE_ADMIN` and compare their decisions. Succeed when the test proves the difference comes from manager configuration.

### Exercise 3 — Method vs. HTTP divergence

Using a 6.5 setup, place `@PreAuthorize("hasAuthority('report:read')")` on a service. Create an HTTP test where an admin role passes HTTP, while the method denies if the expression handler is not wired. Fix the handler properly and run both tests. **Do not relax HTTP rules to make tests pass.**

### Exercise 4 — Try Spring Security 7 configuration

If your project is on 7.x, declare an `AuthorizationManagerFactory<T>` bean using `DefaultAuthorizationManagerFactory<T>.setRoleHierarchy(...)`. Test the same user and hierarchy across HTTP and method security; verify that custom checkpoints outside the factory are not automatically altered. Do not paste a 6.x config class into a 7.x project.

### Exercise 5 — Adding a sensitive permission

Suppose you plan to grant `report:approve` to the manager role. List the risks, indirectly affected users, impact on “creator differs from approver” workflows, deny tests, and rollback plan. Explain why adding one hierarchy edge can affect thousands of users without touching the membership table.

### Exercise 6 — Tenant and source authority checks

A tenant A admin holds `ROLE_ADMIN` and receives `report:read` via hierarchy. Write a `readReport(id)` policy that fetches reports only within the verified tenant. Test that a tenant B report is denied even when both HTTP and method managers allow the functional permission.

## 15. End-of-lesson self-check

1. **What does `RoleHierarchy` do?** Computes the set of authorities reachable from granted authorities via implication edges.
2. **Does declaring a hierarchy bean guarantee every custom manager uses it automatically?** No; you must verify which manager runs and how it is configured.
3. **What explicit wiring exists in Spring Security 6.x?** For `AuthorityAuthorizationManager`, call `setRoleHierarchy(...)`; pass `.access(manager)` so the HTTP rule uses that manager.
4. **What new components arrive in Spring Security 7.0+?** `AuthorizationManagerFactory<T>` and `DefaultAuthorizationManagerFactory<T>` for building managers with shared configuration.
5. **Which version introduced `withDefaultRolePrefix()`?** Per Javadoc, Spring Security 6.3.
6. **What does `hasRole("READER")` normally check?** `ROLE_READER` under default conventions, which can be satisfied indirectly when the manager applies a hierarchy.
7. **Does a holder of `ROLE_MANAGER` automatically gain `ROLE_ADMIN` under ADMIN > MANAGER?** No; implication flows downward only.
8. **Does having `ROLE_ADMIN` mean `Authentication.getAuthorities()` always contains `ROLE_READER`?** No; the hierarchy may only be evaluated inside the manager at check time.
9. **Does a JWT scope `SCOPE_reports.read` automatically become `ROLE_READER`?** No; an approved mapping is needed if policy intends to link them.
10. **Does a hierarchy replace tenant, owner, and separation-of-duties checks?** No.
11. **If HTTP allows a request while method security returns 403, what should you check?** Method expression handler/manager, role hierarchy wiring, prefixes, and object policies.
12. **Is testing `getReachableGrantedAuthorities` alone enough?** No; you must also test HTTP, method, and data layers.
13. **Should you add admin to every expression to silence 403s?** No; diagnose the root cause and preserve least privilege.
14. **Which users are affected by editing a hierarchy?** Any user whose roles reach the modified authorities, including transitively; run impact analysis and regression tests.
15. **What should you watch for when upgrading 6.x to 7.x?** Check the new factory, manager decision APIs, expression handlers, and ensure effective policy does not drift unintentionally.

**Remember:** defining `ROLE_ADMIN > ROLE_USER` is only the **relationship policy**. For inheritance to take effect, **the `AuthorizationManager` making the decision must actually use that hierarchy**. In 6.x you can wire it explicitly into `AuthorityAuthorizationManager` and the method expression handler; in 7.x `AuthorizationManagerFactory` unifies many managers. Regardless of version, hierarchy only resolves functional permissions **along declared inheritance paths**; it never replaces trusted authentication, tenant/object policies, SoD, or deny-case tests.

### Official references to verify by version

- [Spring Security 6.5 – Authorization Architecture / Hierarchical Roles](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 – AuthorityAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html)
- [Spring Security 6.5 – RoleHierarchyImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 7.0+ – Authorization Architecture / AuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 7.0+ – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)