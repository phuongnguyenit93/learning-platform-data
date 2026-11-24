# AuthorizationManagers.allOf, anyOf, and Semantics When No Decision Is Made

> **Scope:** Spring Security – authorization, **Custom AuthorizationManager** group. This lesson explains how to compose multiple `AuthorizationManager`s using `AuthorizationManagers.allOf(...)`, `anyOf(...)`, and specifically the case where delegates **make no decision** (*abstain*). Main examples use Spring Security 6.5+ (overloads with a default decision for all-abstain appeared in 6.3), Spring Boot Servlet, and Java 17+. Final behavior depends on your actual library version, so verify against your active dependencies.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the three states of an `AuthorizationManager`: **GRANT**, **DENY**, and **ABSTAIN**; avoid confusing `null` with `false`.
2. Accurately predict the outcome of `allOf` and `anyOf` with multiple managers, when all abstain, and when the manager list is empty.
3. Use `allOf(AuthorizationDecision, ...)` and `anyOf(AuthorizationDecision, ...)` overloads to specify a fallback decision.
4. Understand why a delegate returning `null` can cause an **unintended grant** inside `allOf`.
5. Design custom managers with a clear domain of applicability, returning DENY when a checked resource lacks data; adopt a "deny by default" policy.
6. Write tests for web/request integration and for the composition logic itself, including short-circuit evaluation.

## 2. What Decisions Does an AuthorizationManager Produce?

`AuthorizationManager<T>` evaluates whether an authenticated principal is permitted to interact with a protected object of type `T`. `T` can be `RequestAuthorizationContext` (Servlet URL rules), `MethodInvocation` (permissions on method calls), or a custom object.

The central method in modern Spring Security:

~~~java
// Conceptual signature of the modern API (Spring Security 6.4+/7.x).
AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        T object);
~~~

`AuthorizationResult` exposes `isGranted()`. In Spring Security 6.5, `authorize(...)` is a default method and the older `check(...)` is deprecated; in Spring Security 7.x, new code targets `authorize(...)`. Do not build new designs heavily tied to the legacy `check` API.

Three states when evaluating a delegate:

| State | Typical return value | Meaning |
| --- | --- | --- |
| **GRANT** | `new AuthorizationDecision(true)` | The delegate evaluated and allowed |
| **DENY** | `new AuthorizationDecision(false)` | The delegate evaluated and denied |
| **ABSTAIN** | `null` | The delegate **made no decision**, e.g., the rule does not apply |

**ABSTAIN is not DENY.** A delegate saying "I have no opinion" differs from "I disallow." A composite manager is allowed to apply a default decision when every delegate abstains.

`AuthorizationManager#verify(...)` invokes the authorization check and throws `AccessDeniedException` upon receiving a **negative decision**. Never treat `null` from a custom manager as a denial mechanism; explicitly return `new AuthorizationDecision(false)` when blocking is required.

### 2.1. Example Policy That May Abstain

A system has two resource types: `/api/orders/**` and `/api/reports/**`. A custom manager for reports only takes responsibility for certain calls. When outside its domain, a design may return `null` so another manager decides.

~~~java
// Excerpt: RequestAuthorizationContext is a Servlet type.
// For use in a Spring Security project; not a standalone JDK program.
AuthorizationManager<RequestAuthorizationContext> reportOnly =
        (authentication, context) -> {
            String path = context.getRequest().getRequestURI();
            if (!path.startsWith("/api/reports/")) {
                return null; // ABSTAIN: report rule does not apply
            }

            Authentication current = authentication.get();
            boolean canRead = current != null
                    && current.getAuthorities().stream()
                        .anyMatch(a -> "report:read".equals(a.getAuthority()));
            return new AuthorizationDecision(canRead);
        };
~~~

Important: returning `null` only makes sense when there truly is **another responsible delegate or router**. If a composite is attached to a sensitive URL and every delegate abstains, an unintended grant can occur.

## 3. allOf: Combining with AND, Yet Abstains Are Ignored

Basic declaration:

~~~java
AuthorizationManager<T> composite =
        AuthorizationManagers.allOf(managerA, managerB, managerC);
~~~

**Actual semantics** of the overload without a custom default:

1. Evaluates managers in the order passed.
2. If any delegate returns **DENY**, the composite result is **DENY** immediately; subsequent delegates may not be invoked.
3. Delegates returning `null` (**ABSTAIN**) are skipped.
4. If at least one delegate returns GRANT and none return DENY, the composite returns **GRANT**.
5. If **all abstain**, the composite returns **GRANT** by default.
6. If **no managers are passed**, `allOf()` also returns **GRANT**.

It looks like AND when only GRANT/DENY appear, yet **it is not three-valued AND where abstain means deny**. This is a critical detail to remember: `allOf` where every delegate "doesn't know" **does not deny by itself**.

### Default allOf Decision Table

Notation: `G` = GRANT, `D` = DENY, `A` = ABSTAIN.

| Delegate results in order | `allOf(...)` returns | Reason |
| --- | --- | --- |
| `[G, G]` | G | All actual decisions agree |
| `[G, A]` | G | A is ignored, G remains |
| `[A, G]` | G | A is ignored, G remains |
| `[D, A]` | D | At least one DENY |
| `[A, D]` | D | At least one DENY |
| `[G, D]` | D | DENY blocks |
| `[A, A]` | **G** | All abstain → `allOf` default |
| `[]` | **G** | Empty list → `allOf` default |

**Risk:** suppose a tenant checker, ACL checker, and ownership checker all return `null` for a newly added unconfigured resource type. `AuthorizationManagers.allOf(...)` can return **GRANT**. If code assumes "I combined three rules with AND" without testing the abstain path, the system can bypass security barriers.

## 4. anyOf: Combining with OR and Default Fallback Is Deny

Declaration:

~~~java
AuthorizationManager<T> composite =
        AuthorizationManagers.anyOf(managerA, managerB, managerC);
~~~

Actual semantics:

1. Evaluates managers in the order passed.
2. If any delegate returns **GRANT**, the composite returns **GRANT** immediately without asking subsequent delegates.
3. Delegates returning `null` (**ABSTAIN**) are skipped.
4. If there is no GRANT and at least one **DENY**, the composite returns **DENY**.
5. If **all abstain**, the composite returns **DENY** by default.
6. If **there are no delegates**, `anyOf()` returns **DENY**.

### Default anyOf Decision Table

| Delegate results in order | `anyOf(...)` returns | Reason |
| --- | --- | --- |
| `[G, G]` | G | One GRANT exists |
| `[D, G]` | G | One GRANT wins under OR |
| `[G, D]` | G | GRANT short-circuits before D |
| `[G, A]` | G | One GRANT exists |
| `[A, G]` | G | One GRANT exists |
| `[D, A]` | D | A ignored, D remains |
| `[A, D]` | D | A ignored, D remains |
| `[D, D]` | D | Nobody GRANTed |
| `[A, A]` | **D** | All abstain → `anyOf` default |
| `[]` | **D** | Empty list → `anyOf` default |

**Do not misinterpret the Javadoc phrase "granted or abstained" as "one abstain is enough to allow."** In the implementation, `null` is ignored; when there is no explicit decision at all, the fallback applies. With `anyOf(DENY, ABSTAIN)`, the result is DENY.

### 4.1. Side-by-Side Comparison

| Delegate list | Default allOf | Default anyOf |
| --- | --- | --- |
| `[G, G]` | GRANT | GRANT |
| `[G, D]` | DENY | GRANT |
| `[G, A]` | GRANT | GRANT |
| `[D, A]` | DENY | DENY |
| `[A, A]` | **GRANT** | **DENY** |
| `[]` | **GRANT** | **DENY** |

The exact same **all-abstain** list can yield two opposite results. That is a feature of how composition works, not a Spring Security bug.

## 5. Setting the Default Decision When All Abstain

Since Spring Security **6.3**, overloads exist:

~~~java
AuthorizationManagers.allOf(
        new AuthorizationDecision(false), managerA, managerB);

AuthorizationManagers.anyOf(
        new AuthorizationDecision(false), managerA, managerB);
~~~

The first parameter is `allAbstainDefaultDecision`: **used only when no delegate returns an explicit decision** (including an empty list). This is a very suitable choice for sensitive policies that must **fail closed** when no manager claims responsibility.

| Configuration | When all delegates are A | When list is empty |
| --- | --- | --- |
| `allOf(managers...)` | GRANT | GRANT |
| `anyOf(managers...)` | DENY | DENY |
| `allOf(new AuthorizationDecision(false), managers...)` | **DENY** | **DENY** |
| `anyOf(new AuthorizationDecision(false), managers...)` | **DENY** | **DENY** |
| `allOf(new AuthorizationDecision(true), managers...)` | GRANT | GRANT |
| `anyOf(new AuthorizationDecision(true), managers...)` | GRANT | GRANT |

### 5.1. Fallback Does Not Mean Every Abstain Becomes DENY

Contrast two examples:

~~~java
// A is a manager that always abstains.
// G is a manager that returns GRANT.
AuthorizationManagers.allOf(new AuthorizationDecision(false), A, A);
// → DENY: all abstain, fallback is used

AuthorizationManagers.allOf(new AuthorizationDecision(false), G, A);
// → GRANT: there is already a GRANT, A is ignored; fallback does NOT run
~~~

**This is the most dangerous misconception:** `allOf(DENY_DEFAULT, permissionManager, tenantManager)` **does not force** `tenantManager` to return GRANT. If `permissionManager` returns GRANT and `tenantManager` returns `null`, the composite still returns GRANT.

Therefore, if **every condition is mandatory**, that condition's custom manager must return an explicit decision for every call within its protected scope. Missing tenant, missing ACL record, unparseable ID, or disconnected policy service must follow an explicit policy (usually DENY or a securely handled error) rather than silently ABSTAINing.

### 5.2. When to Use Default GRANT?

The overload accepts `new AuthorizationDecision(true)`. Use it only when *business intent* explicitly determines that if no manager applies, access is allowed (e.g., an explicitly categorized public zone). Never default-fallback to GRANT for unrouted resources or an under-configured policy system.

## 6. Short-Circuiting: Not Every Manager Is Invoked

A composite manager can stop as soon as it sees a decisive result:

~~~text
allOf(G, G, D, expensivePolicy)
     G  G  D  does not call expensivePolicy
             -> DENY

anyOf(D, A, G, expensivePolicy)
     D  A  G  does not call expensivePolicy
             -> GRANT
~~~

Consequences of this behavior:

- Placing **cheap, decisive** checks first can reduce latency.
- Do not put mandatory side effects (such as an audit "that must run every time") inside a delegate assuming it will always execute.
- When logging/debugging, never infer from a missing log line that a manager returned GRANT or DENY: it may **never have been evaluated**.
- If a custom policy calls an external service, define how network errors/timeouts are handled; never automatically convert an **infrastructure failure** into ABSTAIN and accidentally grant via `allOf`.
- With `anyOf`, a GRANT on one branch can permit access even if another branch returns DENY. That is right for OR, yet **wrong** for a condition like "locked accounts are always denied." For mandatory deny rules, use `allOf(requiredAccountActive, anyOf(roleA, roleB))`.

### Example: Mandatory Condition Plus Alternatives

Requirement: the user **must be active** and **must hold** either `invoice:read` **or** `invoice:audit`.

~~~java
// Illustrative excerpt inside a Spring Security application.
// T = RequestAuthorizationContext or MethodInvocation depending on where it is used.
AuthorizationManager<T> policy = AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        activeAccountManager,
        AuthorizationManagers.anyOf(
                new AuthorizationDecision(false),
                invoiceReadManager,
                invoiceAuditManager));
~~~

`activeAccountManager` must return DENY for locked accounts, never ABSTAIN for an account it is responsible for checking. The remaining managers must also have well-defined scopes. Do not write `anyOf(activeAccount, hasAuthority)` if a locked account must veto all other permissions.

## 7. Standalone Java 17 Program to Inspect the Decision Table

The following program **faithfully simulates the three-state composition algorithm**; it does not claim to be Spring Security source code and requires no Spring libraries. Its purpose is to let learners run it, swap result orders, and observe fallback behavior.

Save as `CompositionTruthTableDemo.java`:

~~~java
public class CompositionTruthTableDemo {
    enum Vote { GRANT, DENY, ABSTAIN }

    static Vote allOf(Vote onAllAbstain, Vote... votes) {
        boolean anyGrant = false;
        for (Vote vote : votes) {
            if (vote == Vote.DENY) {
                return Vote.DENY;
            }
            if (vote == Vote.GRANT) {
                anyGrant = true;
            }
        }
        return anyGrant ? Vote.GRANT : onAllAbstain;
    }

    static Vote anyOf(Vote onAllAbstain, Vote... votes) {
        boolean anyDeny = false;
        for (Vote vote : votes) {
            if (vote == Vote.GRANT) {
                return Vote.GRANT;
            }
            if (vote == Vote.DENY) {
                anyDeny = true;
            }
        }
        return anyDeny ? Vote.DENY : onAllAbstain;
    }

    public static void main(String[] args) {
        System.out.println("allOf(G,A)=" +
                allOf(Vote.GRANT, Vote.GRANT, Vote.ABSTAIN));
        System.out.println("allOf(A,A)=" +
                allOf(Vote.GRANT, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("allOf(A,A) fallback DENY=" +
                allOf(Vote.DENY, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("anyOf(D,A)=" +
                anyOf(Vote.DENY, Vote.DENY, Vote.ABSTAIN));
        System.out.println("anyOf(A,A)=" +
                anyOf(Vote.DENY, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("anyOf(A,A) fallback GRANT=" +
                anyOf(Vote.GRANT, Vote.ABSTAIN, Vote.ABSTAIN));
        System.out.println("allOf()=" + allOf(Vote.GRANT));
        System.out.println("anyOf()=" + anyOf(Vote.DENY));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CompositionTruthTableDemo.java
java CompositionTruthTableDemo
~~~

**Exact stdout:**

~~~text
allOf(G,A)=GRANT
allOf(A,A)=GRANT
allOf(A,A) fallback DENY=DENY
anyOf(D,A)=DENY
anyOf(A,A)=DENY
anyOf(A,A) fallback GRANT=GRANT
allOf()=GRANT
anyOf()=DENY
~~~

Try replacing `Vote.ABSTAIN` with `Vote.DENY` in `allOf(G,A)`: whenever a DENY is present, the result becomes DENY regardless of fallback. Replace it with `Vote.GRANT` in `anyOf(D,A)`: with one GRANT present, the result becomes GRANT.

**Simulation boundary:** in real Spring Security, each delegate returns `AuthorizationResult` or `null`. The composite result may be a decision type carrying metadata; the simulation logic only tracks `isGranted()` and does not simulate exceptions, AOP, or the filter chain.

## 8. Example Calling AuthorizationManagers Directly in a Spring Security App

This snippet runs **inside a project that already has `spring-security-core` 6.5+** (which may come from Spring Boot Starter Security). Unlike the JDK example above, this code calls Spring Security's own factory rather than implementing the algorithm itself.

Create `src/main/java/demo/composition/CompositionManagerDemo.java`:

~~~java
package demo.composition;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorizationResult;

public class CompositionManagerDemo {
    static final AuthorizationManager<String> GRANT =
            (authentication, object) -> new AuthorizationDecision(true);

    static final AuthorizationManager<String> DENY =
            (authentication, object) -> new AuthorizationDecision(false);

    static final AuthorizationManager<String> ABSTAIN =
            (authentication, object) -> null;

    static String result(AuthorizationManager<String> manager) {
        AuthorizationResult decision = manager.authorize(() -> null, "resource");
        return decision == null ? "ABSTAIN"
                : decision.isGranted() ? "GRANT" : "DENY";
    }

    public static void main(String[] args) {
        System.out.println("allOf G,A: " +
                result(AuthorizationManagers.allOf(GRANT, ABSTAIN)));
        System.out.println("allOf A,A: " +
                result(AuthorizationManagers.allOf(ABSTAIN, ABSTAIN)));
        System.out.println("allOf A,A deny fallback: " +
                result(AuthorizationManagers.allOf(
                        new AuthorizationDecision(false), ABSTAIN, ABSTAIN)));
        System.out.println("anyOf D,A: " +
                result(AuthorizationManagers.anyOf(DENY, ABSTAIN)));
        System.out.println("anyOf A,A: " +
                result(AuthorizationManagers.anyOf(ABSTAIN, ABSTAIN)));
        System.out.println("anyOf A,A grant fallback: " +
                result(AuthorizationManagers.anyOf(
                        new AuthorizationDecision(true), ABSTAIN, ABSTAIN)));
        System.out.println("not(A): " +
                result(AuthorizationManagers.not(ABSTAIN)));
    }
}
~~~

**Expected output when run on a compatible Spring Security 6.5+/7.x runtime:**

~~~text
allOf G,A: GRANT
allOf A,A: GRANT
allOf A,A deny fallback: DENY
anyOf D,A: DENY
anyOf A,A: DENY
anyOf A,A grant fallback: GRANT
not(A): ABSTAIN
~~~

You can run the main class using your project's classpath, such as an IDE or a configured Gradle `JavaExec` task. **You cannot compile this file alone with `javac CompositionManagerDemo.java` without Spring Security JARs on the classpath.**

Why pass `() -> null` for `Supplier<Authentication>` in the demo? The three delegates `GRANT`, `DENY`, and `ABSTAIN` intentionally **do not read Authentication** in order to isolate composition logic. Real applications must receive the `Authentication` populated by the framework and handle null/anonymous appropriately. Never copy this null supplier into production policies.

### 8.1. 6.5 and 7.x Compatibility Notes

- `AuthorizationManagers.allOf`/`anyOf` have existed since Spring Security 5.8; **overloads accepting an `AuthorizationDecision` first appeared in 6.3**.
- `AuthorizationManager#authorize(...)` appeared in 6.4; in 6.5 the interface still retains deprecated `check(...)`. The lambdas in the example return `AuthorizationDecision`, which matches all modern target signatures; Spring Security 7.x targets `authorize(...)`.
- When migrating an application from 5.8 or 6.2 to 6.3+, verify the version before copying overloads with a fallback parameter.
- When upgrading Spring Security, test the real authorization contract rather than relying on compilation alone: **abstain and empty-manager** cases have clear security consequences.

## 9. Realistic Servlet Example: Both Read Permission and Tenant Match Required

Endpoint requirement: `GET /api/invoices` is accessible only when:

1. The caller has the `invoice:read` authority.
2. The tenant requested by the client **is actually the tenant assigned to the principal**.

Condition (2) must never abstain when the tenant is missing. Passing a tenant via header is only an **untrusted selector**; the manager compares it against server-side data bound to the principal. In the example, the actor→tenant map is hardcoded for clarity; real systems must query a trusted identity/ACL source rather than trusting headers to grant access.

Create `src/main/java/demo/authorization/CompositeAuthorizationApplication.java` in a Spring Boot Servlet project:

~~~java
package demo.authorization;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CompositeAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompositeAuthorizationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        AuthorizationManager<RequestAuthorizationContext> canRead =
                AuthorityAuthorizationManager.hasAuthority("invoice:read");

        // Server-side data in the demo, never taken from the client.
        Map<String, String> assignedTenant = Map.of(
                "alice", "tenant-a",
                "bob", "tenant-b");

        AuthorizationManager<RequestAuthorizationContext> sameTenant =
                (authentication, context) -> {
                    Authentication current = authentication.get();
                    String tenantFromRequest =
                            context.getRequest().getHeader("X-Tenant");
                    String tenantForActor = current == null
                            ? null
                            : assignedTenant.get(current.getName());

                    boolean allowed = tenantForActor != null
                            && tenantForActor.equals(tenantFromRequest);
                    // Missing tenant / unmapped => explicit DENY.
                    return new AuthorizationDecision(allowed);
                };

        AuthorizationManager<RequestAuthorizationContext> policy =
                AuthorizationManagers.allOf(
                        new AuthorizationDecision(false),
                        canRead,
                        sameTenant);

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/invoices")
                            .access(policy)
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("invoice:read").build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("invoice:read").build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read").build());
    }
}

@RestController
class InvoiceController {
    private final Map<String, List<String>> invoices = Map.of(
            "tenant-a", List.of("INV-A-1", "INV-A-2"),
            "tenant-b", List.of("INV-B-1"));

    @GetMapping("/api/invoices")
    List<String> list(@RequestHeader("X-Tenant") String tenant) {
        // Policy already verified the tenant selector before reaching the controller.
        return invoices.getOrDefault(tenant, List.of());
    }
}
~~~

**Dependencies** in an application with the Spring Boot Gradle plugin and dependency management enabled:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This block is part of an existing project's `build.gradle`, not a complete Gradle file. `{noop}` passwords are **for demo use only**; production applications must use a secure password encoder. The application can be run with `./gradlew bootRun` (Unix) or `gradlew.bat bootRun` (Windows) with the appropriate Spring Boot wrapper and dependencies.

If the app is running on `localhost:8080`, you can try:

~~~bash
curl -i -u alice:demo -H "X-Tenant: tenant-a" http://localhost:8080/api/invoices
curl -i -u alice:demo -H "X-Tenant: tenant-b" http://localhost:8080/api/invoices
curl -i -u viewer:demo -H "X-Tenant: tenant-a" http://localhost:8080/api/invoices
curl -i -u bob:demo -H "X-Tenant: tenant-b" http://localhost:8080/api/invoices
~~~

| Caller | Authority | Tenant header | Result |
| --- | --- | --- | --- |
| Alice | `invoice:read` | `tenant-a` | 200, only tenant-a list |
| Alice | `invoice:read` | `tenant-b` | 403 due to sameTenant DENY |
| Viewer | Only `profile:read` | `tenant-a` | 403 due to canRead DENY |
| Bob | `invoice:read` | `tenant-b` | 200, only tenant-b list |
| Alice | `invoice:read` | Missing `X-Tenant` | 403 due to sameTenant DENY |
| Unauthenticated | No authenticated principal | `tenant-a` | Usually 401 with HTTP Basic |

Note: `allOf` stops at the first DENY, so when Viewer lacks `invoice:read`, `sameTenant` may not be called. This is not a test bug; it is short-circuit design.

### 9.1. Why Does sameTenant Return DENY Instead of ABSTAIN?

Suppose someone mistakenly writes:

~~~java
// Counterexample: abstain when tenant is missing.
if (tenantFromRequest == null) {
    return null;
}
~~~

With Alice having `invoice:read`, `canRead` returns GRANT. `sameTenant` abstains, and `allOf(new AuthorizationDecision(false), canRead, sameTenant)` still returns **GRANT**. The DENY fallback **does not save you** because not all delegates abstained. Afterward, the controller might return 400 on a missing required header, yet on another controller lacking that guard, unintended data could be exposed.

Fix: a mandatory rule within an endpoint's scope must return `new AuthorizationDecision(false)` when it cannot verify the tenant; controllers, repositories, and the business layer should also enforce data scoping. Avoid confusing "insufficient information" with "rule does not apply."

### 9.2. Using a Manager in the DSL Does Not Automatically Protect All Callers

`SecurityFilterChain` and `RequestAuthorizationContext` apply only to requests passing through the Servlet filter chain. A background job invoking a repository/service will not automatically run URL authorization. For data requiring protection across every invocation path, enforce ACL/tenant policies at the service/data layer, e.g., with method security or an interceptor using a properly configured `AuthorizationManager<MethodInvocation>`. A manager variable declared in a bean **does not automatically turn into an annotation**.

## 10. Spring Boot Testing via MockMvc

Create `src/test/java/demo/authorization/CompositeAuthorizationApplicationTest.java` (same package as the application):

~~~java
package demo.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CompositeAuthorizationApplicationTest {
    @Autowired MockMvc mvc;

    @Test
    void aliceCanReadAssignedTenant() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("alice", "demo"))
                    .header("X-Tenant", "tenant-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0]").value("INV-A-1"));
    }

    @Test
    void aliceCannotReadAnotherTenant() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("alice", "demo"))
                    .header("X-Tenant", "tenant-b"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingRequiredAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("viewer", "demo"))
                    .header("X-Tenant", "tenant-a"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingTenantIsDeniedByPolicy() throws Exception {
        mvc.perform(get("/api/invoices")
                    .with(SecurityMockMvcRequestPostProcessors
                            .httpBasic("alice", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/invoices")
                    .header("X-Tenant", "tenant-a"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Run tests with the project's Gradle wrapper. The 401/403 expectations here depend on HTTP Basic, the filter chain, and exception handling in the demo. Projects with custom authentication entry points/handlers may return different status codes. These are **integration tests** and do not replace unit tests for composition algorithms.

### 10.1. Additional Unit Tests Needed for Custom Managers

Besides MockMvc, test `manager.authorize(authenticationSupplier, context)` directly to verify:
- Returns GRANT when the policy verifies all conditions.
- Returns DENY when tenant, ACL, owner, or required data cannot be verified.
- Returns ABSTAIN only when the target lies outside its domain **and** a proper responsible router exists.
- If a delegate throws an exception, the outcome is never silently turned into ABSTAIN.
- Invoke delegates with side effects/logging to observe whether short-circuiting skips them.

Decision-table test suites should specifically include both **all abstain** and **empty manager list** cases. Testing only GRANT/DENY while forgetting `null` misses the core point of this lesson.

## 11. Composing Managers in Method Security

`AuthorizationManager<T>` is generic; `allOf`/`anyOf` factories are not limited to URLs. In method security, the protected object is usually `MethodInvocation`; you can build:

~~~java
// Type-level excerpt: only builds the manager, AOP interceptor not yet registered.
AuthorizationManager<MethodInvocation> securedMethod =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false),
                methodAuthorityManager,
                methodOwnershipManager);
~~~

To execute automatically, wire the manager into an appropriate interception mechanism, such as `AuthorizationManagerBeforeMethodInterceptor` or an existing method security policy. Do not assume `.access(policy)` configured on a URL applies when a service is invoked from a queue or scheduled job.

In method security, `@PreAuthorize("hasAuthority('invoice:read')")` expresses a single permission differently from `AuthorizationManagers.allOf(...)`. When complex, reusable custom logic is needed, a manager can help; when rules are simple, annotations/DSL are often easier to read. Either way, if a mandatory check cannot evaluate, never ABSTAIN hoping the composite will deny on its own.

**Distinguish undecided from unauthenticated:** `authentication.get() == null` or an anonymous principal does not inherently yield ABSTAIN. If a rule requires an authenticated user and lacks a trusted identity, return DENY or let the authentication layer handle it per contract; do not cast an "I have no opinion" vote into `allOf`.

## 12. not(...) and Cases Beyond GRANT/DENY

`AuthorizationManagers.not(manager)` inverts a decided result:

| Delegate | `not(delegate)` |
| --- | --- |
| GRANT | DENY |
| DENY | GRANT |
| ABSTAIN | **ABSTAIN** |

Thus `not(abstainingManager)` still makes **no decision**. The final result when placing `not(...)` inside `allOf`/`anyOf` still depends on how the composite handles the all-abstain scenario.

Do not treat exceptions as a fourth state equivalent to ABSTAIN. A delegate may throw when a policy provider is unavailable; that is a failure path requiring a safety and observability strategy. Never catch all exceptions and return `null` unless you genuinely intend to declare "no decision" and have verified the fallback cannot cause privilege escalation.

### 12.1. Example of an Error-Handling Mistake

~~~java
// Counterexample: infrastructure failure swallowed into ABSTAIN.
AuthorizationManager<RequestAuthorizationContext> externalAcl =
        (authentication, context) -> {
            try {
                return new AuthorizationDecision(
                        remoteAclService.isAllowed(authentication.get(),
                                context.getRequest()));
            } catch (Exception ignored) {
                return null; // DANGEROUS inside allOf
            }
        };
~~~

This illustrative snippet depends on the application's `remoteAclService` and is **not a complete file**. If another authority checker returns GRANT, `allOf` can GRANT even though the ACL service failed. Distinguish "does not apply," "no ACL record found," and "infrastructure unreachable." Choose a fail-closed contract with logging/correlation and proper retry/circuit-breaker policies that never produce unintended grants.

## 13. How to Design Structured Policies

A useful principle is splitting predicates into two groups:

- **Mandatory conditions (must):** active account, same tenant, valid owner, unlocked, feature permission. Design so every in-scope request returns GRANT or DENY. Combine with `allOf`.
- **Alternative options (may satisfy by one):** holds `invoice:read` **or** `invoice:audit`, belongs to approver group A **or** holds a valid delegation. Combine with `anyOf`.

Structural example:

~~~text
allOf(
  accountActive,                      // required
  sameTenant,                         // required
  anyOf(invoiceRead, invoiceAudit)    // either permission
)
~~~

In a real application, `accountActive` and `sameTenant` must never abstain for a request within their scope. If a policy list is loaded dynamically from configuration, validate **empty lists** at startup; an empty `allOf()` defaults to GRANT. If configuration is missing, failing startup or defaulting to deny is far safer than silently allowing access.

### 13.1. Avoid Encoding Policies as "No Result = Agree"

Use clear naming:
- `isTenantAllowed` returns an explicit decision boolean.
- `isApplicableToRequest` determines scope when routing is needed.
- `authorize(...)` returns `null` only when the manager genuinely is not responsible.

Separate **selecting which policy applies** from **deciding access**. Once a request matcher router selects a specific manager, that manager should normally produce a definite decision. Do not rely on having three managers that can all abstain on a sensitive request.

### 13.2. Tracking Reasons and Metadata

`AuthorizationDecision` only holds a granted boolean; other `AuthorizationResult` types or application implementations can carry extra details. When a composite evaluates, some delegates may be skipped due to short-circuiting. If auditing needs to explain "who denied for what reason," design logging/decision tracing so it does not expose PII, tokens, or internal permissions to clients. Never assume every delegate will always record an audit entry.

## 14. Real-World Mistakes to Avoid

### Mistake 1: "AND with all abstains will DENY"

False for default `AuthorizationManagers.allOf(managers...)`: all abstain returns **GRANT**. Test all-abstain and empty-list cases, and consider the DENY-fallback overload.

### Mistake 2: "Passing default DENY forces every manager to GRANT"

False: the default is used **only if all** abstain. `allOf(DENY_DEFAULT, GRANT, ABSTAIN)` returns GRANT. For mandatory conditions, return explicit DENY when data is missing.

### Mistake 3: "ABSTAIN is basically false"

False: `null` differs from `AuthorizationDecision(false)`. When any branch returns DENY in `allOf`, the composite is blocked; when a branch returns ABSTAIN, that branch is skipped.

### Mistake 4: "anyOf(DENY, ABSTAIN) will GRANT because one branch abstained"

False: there is no GRANT and there is a DENY, so the composite returns DENY. `anyOf` does not treat a single ABSTAIN as a pass.

### Mistake 5: "No managers means no permission"

An empty `anyOf()` indeed returns DENY, yet an empty `allOf()` returns GRANT. Never build policies from dynamic lists without validating manager counts/types.

### Mistake 6: "There's a manager requiring an active account, OR is still fine"

`anyOf(activeAccount, hasAuthority)` allows access if either returns GRANT, even when the other returns DENY. If an active account is mandatory, place it outside the OR and use AND.

### Mistake 7: "Every manager runs so it can write audit logs"

Composites short-circuit. Never place mandatory side effects inside authorization functions. Centralized logging/auditing should hook into the final decision and whichever policies were actually evaluated.

### Mistake 8: "Missing tenant means the tenant rule doesn't apply"

If the route accesses tenant-scoped data, the tenant check is mandatory. Returning null due to a missing header/ID can widen access. Return DENY when scope cannot be verified, and validate payloads separately if needed.

### Mistake 9: "Network errors to the policy engine can default to abstain"

Do not do this. Choose fail closed or explicit error handling per your threat model. Swallowing timeouts into `null` easily turns `allOf` into an allow when another rule returns GRANT.

### Mistake 10: "Composite result equals the HTTP response"

A composite only decides authorization; mapping to 401/403/404 depends on the filter chain, authentication entry point, exception translation, and API policy. For non-HTTP method security, there may simply be a service exception.

### Mistake 11: "Read behavior from one version and apply to every version"

Fallback overloads were added in 6.3; the `authorize` API in 6.4. Check runtime dependencies, matching Javadoc, and lock behavior with tests.

## 15. QA Matrix Recommended Before Release

| Case | Default allOf | Default anyOf | Expected to test |
| --- | --- | --- | --- |
| All GRANT | GRANT | GRANT | happy path |
| One DENY, rest GRANT | DENY | GRANT | AND/OR semantics |
| One DENY, rest ABSTAIN | DENY | DENY | abstain neither vetoes nor unlocks |
| One GRANT, rest ABSTAIN | GRANT | GRANT | abstain is ignored |
| All ABSTAIN | **GRANT** | **DENY** | default fallback |
| Zero managers | **GRANT** | **DENY** | empty policy config |
| Default DENY + all ABSTAIN | DENY | DENY | overload from 6.3 |
| Default DENY + one GRANT and ABSTAINs | GRANT | GRANT | fallback does not intervene |
| Delegate throws exception | No normal successful result | No normal successful result | fail closed / exception handling |
| Order G,D vs D,G | Only managers up to blocking result run | Only managers up to blocking result run | short-circuiting |
| Missing mandatory tenant/owner/ACL | DENY by responsible manager | Depends on OR structure | no data leakage |
| Manager list from config is empty | Startup fail or explicit DENY | Explicit DENY | config validation |

Do not use this table as an excuse to allow empty decisions. Every endpoint/feature must define a **fail closed** policy when rules do not apply, data is missing, or configuration is broken.

## 16. Applied Exercises

**Scenario 1:** An application composes `allOf(hasReadPermission, optionalAclCheck)`. Alice has `report:read`. `optionalAclCheck` returns `null` because the ACL table is missing. Can Alice view the report?

**Answer:** With default `allOf`, yes: `hasReadPermission` returns GRANT, ACL returns ABSTAIN, result is GRANT. If ACL is a **mandatory** barrier, this design is unsafe; the ACL checker must return DENY when permission cannot be verified, or the policy must be restructured.

**Scenario 2:** Does switching to `allOf(new AuthorizationDecision(false), hasReadPermission, optionalAclCheck)` fix Scenario 1?

**Answer:** **No.** One delegate still returns GRANT, so the "all abstain" fallback is not used. The DENY fallback applies only when **every** delegate abstains.

**Scenario 3:** Does `anyOf(managerA, managerB)` with `A=DENY` and `B=ABSTAIN` allow access?

**Answer:** No. There is no GRANT and there is a DENY, so it returns DENY.

**Scenario 4:** All delegates ABSTAIN; replacing `allOf` with `anyOf` without changing the managers. Result?

**Answer:** Shifts from default GRANT to default DENY. Better yet, design mandatory conditions to return explicit decisions and write tests so you never rely on accidental abstains.

**Scenario 5:** What structure should be used for the rule "active account AND (editor OR admin)"?

**Answer:** `allOf(activeManager, anyOf(editorManager, adminManager))`. `activeManager` must return DENY when locked; never put it inside `anyOf` alongside roles and let another role override the lock.

## Official Documentation

- [Spring Security API – AuthorizationManagers](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf`, fallback overloads from 6.3, `not`, and abstain behavior.
- [Spring Security API – AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize`, `verify`, deprecated `check`.
- [Spring Security Reference – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `AuthorizationManager` model, built-in managers, and authorization decisions.
- [Spring Security Reference – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): configuring `SecurityFilterChain`, `authorizeHttpRequests`, and request `AuthorizationManager`s.
- [Spring Security Reference – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): applying authorization inside Spring services.
