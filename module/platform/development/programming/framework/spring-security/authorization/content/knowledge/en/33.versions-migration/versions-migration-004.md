# AccessDecisionManager, AccessDecisionVoter, and Migrating to AuthorizationManager

> **Scope:** Spring Security – authorization, **Versions and Migration** group. This lesson explains the legacy permission-decision architecture, how to interpret votes accurately, and the migration path to `AuthorizationManager` when upgrading Spring Security. Integration test examples target Spring Boot 3.x, Spring Security 6.x, and Java 17+; Spring Security 7 differences are explicitly noted to avoid applying the wrong API.

## 1. Why Understand Both the Old and New Systems?

In long-lived Spring Security codebases, you may encounter the trio:

- `SecurityMetadataSource`: looks up `ConfigAttribute`s attached to a protected URL or method, such as `ROLE_ADMIN`.
- `AccessDecisionVoter<S>`: an individual policy that votes `GRANT`, `DENY`, or `ABSTAIN` on the target being accessed.
- `AccessDecisionManager`: aggregates votes from multiple voters and decides whether to allow access or throw `AccessDeniedException`.

In the modern architecture, `AuthorizationManager<T>` receives a `Supplier<Authentication>` and the protected target object, then returns the final decision. Spring Security provides built-in managers and policy composition utilities, so many applications no longer need custom voters or decision managers.

**Key takeaway:** migration is about **preserving security policy**, not just renaming interfaces. Choosing a different rule-combination strategy can allow someone who was previously denied to gain access. Before editing code, establish the exact voting rules—especially when voters disagree or when no voter casts a decision.

### Version boundaries

| Branch | What You Need to Know |
| --- | --- |
| Spring Security 5.x | Legacy APIs are still common, though `AuthorizationManager` became the replacement direction; `authorizeHttpRequests` appeared on the modernization path |
| Spring Security 6.x (e.g., Spring Boot 3.x) | Prefer `authorizeHttpRequests`, `@EnableMethodSecurity`, and `AuthorizationManager`. Legacy Access APIs may still exist in older code |
| Spring Security 6.4–6.5 | `AuthorizationManager.authorize(...)`/`AuthorizationResult` is the newer API; `check(...)` is deprecated in 6.5 though still an abstract method in 6.x |
| Spring Security 7.x | `AccessDecisionManager`, `AccessDecisionVoter`, and related Access APIs moved to the legacy `spring-security-access` module. `AuthorizationManager.authorize(...)` is the primary implementation point; `check(...)` is no longer an API to override |

**Do not mix the 6.x `check` signature with the 7.x `authorize` signature** in the same custom class and expect it to compile across all versions. The complete runnable example in Section 6 uses an `AuthorizationManager` lambda and built-in factories to minimize reliance on legacy signatures.

## 2. AccessDecisionManager and AccessDecisionVoter Architecture

### 2.1. Legacy decision flow

```text
HTTP request / method invocation
             │
             ▼
FilterSecurityInterceptor / MethodSecurityInterceptor (legacy)
             │
             ├─ SecurityMetadataSource
             │     └─ retrieve ConfigAttributes for URL/method
             │
             ▼
      AccessDecisionManager.decide(authentication, object, attributes)
             │
             ├─ RoleVoter                  ──► GRANT / DENY / ABSTAIN
             ├─ AuthenticatedVoter         ──► GRANT / DENY / ABSTAIN
             └─ CustomDomainVoter         ──► GRANT / DENY / ABSTAIN
             │
             ▼
      Vote aggregator (strategy)
             ├─ allow: proceed with request / invoke method
             └─ deny: AccessDeniedException
```

`Authentication` holds the identity and list of `GrantedAuthority`s. `secureObject` can be a request wrapped in `FilterInvocation` or the corresponding method invocation; `ConfigAttribute` represents policy metadata (roles, authentication state, expressions, or custom config). Do not confuse **authentication** (who the caller is) with **authorization** (whether the caller is allowed to do this).

Legacy signatures for **reading comprehension**, not a standalone program:

```java
// Legacy API; only for maintaining/migrating legacy code.
interface AccessDecisionManager {
    void decide(
        Authentication authentication,
        Object secureObject,
        Collection<ConfigAttribute> attributes)
        throws AccessDeniedException;

    boolean supports(ConfigAttribute attribute);
    boolean supports(Class<?> secureObjectType);
}

interface AccessDecisionVoter<S> {
    int vote(Authentication authentication,
             S secureObject,
             Collection<ConfigAttribute> attributes);

    boolean supports(ConfigAttribute attribute);
    boolean supports(Class<?> secureObjectType);
}
```

`supports(...)` lets the framework determine which metadata types and target object types a voter/manager handles. `vote(...)` must not invoke business methods or produce side effects; a voter's sole responsibility is making a decision. The code above shows **abbreviated illustrative signatures** from the actual interfaces—do not redeclare them in your project.

### 2.2. Three outcomes of a voter

| Vote | Meaning | What Must Not Be Inferred |
| --- | --- | --- |
| `ACCESS_GRANTED` (+1) | The voter grants access per the policy it represents | Does not mean the entire system will allow access |
| `ACCESS_DENIED` (-1) | The voter denies access per that policy | Can be overridden by an `AffirmativeBased` strategy if another voter grants |
| `ACCESS_ABSTAIN` (0) | The voter has no opinion/does not handle this rule | **Does not mean** allow |

A voter should abstain only if its policy does not apply or cannot evaluate the rule; if the policy applies and the caller lacks permission, the result is normally deny. For example, `RoleVoter` abstains when no `ConfigAttribute` carries its supported role prefix; when a role attribute applies and the user lacks the role, it denies.

When **all voters abstain**, default voting implementations normally deny (`allowIfAllAbstainDecisions=false`). Enabling all-abstain = allow just to "stop getting 403 errors" can open a vulnerability. During migration, always verify fallback policies and unmatched URLs/methods.

### 2.3. Three legacy vote-aggregation strategies

| Strategy | Principle | When Voter A GRANTs and Voter B DENYs |
| --- | --- | --- |
| `AffirmativeBased` | **At least one GRANT** allows access; deny does not veto grant | **ALLOW** |
| `UnanimousBased` | **Any DENY** denies access; if no DENY and at least one GRANT, allow | **DENY** |
| `ConsensusBased` | Compares GRANT vs. DENY counts; ties deny by default, with configurable tie-breaking | **DENY on tie**, per default configuration |

Abstain votes are ignored when tallying grants/denies; if **all abstain**, the configured all-abstain policy applies (deny by default). When a codebase customizes tie or all-abstain behavior, read the actual configuration and write matching tests.

Example: `RoleVoter` GRANTs because the user has an employee role; `AccountSuspendedVoter` DENYs because the account is locked. Under `AffirmativeBased`, a single GRANT means the locked user **may still be allowed access**. Under `UnanimousBased`, DENY blocks access. This illustrates why you cannot replace `AffirmativeBased` with a new combination without understanding business expectations.

**How to think when migrating:**

- "At least one policy allows" resembles logical OR, but deny/abstain behavior must be explicitly defined.
- "All required policies allow" resembles logical AND, especially when one policy acts as a veto such as suspended/tenant isolation.
- `ConsensusBased` "majority wins" does not map directly to `anyOf` or `allOf`; write a custom composite manager if the business genuinely still requires majority voting.
- A **veto** deny must never be placed in the same OR branch as a granting rule; prioritize the deny or separate it into a mandatory condition.

## 3. AuthorizationManager: Permission Decisions in the New API

### 3.1. General mechanism

```text
HTTP request
   │
   ▼
SecurityFilterChain
   │
   ▼
AuthorizationFilter (authorizeHttpRequests)
   │
   ▼
RequestMatcherDelegatingAuthorizationManager
   │
   ├─ which request matches?
   └─ apply AuthorizationManager<RequestAuthorizationContext>
        ├─ authentication: Supplier<Authentication> (fetched when needed)
        ├─ context: request + path variables if provided by matcher
        └─ result: allow / deny / abstain
             │
             ├─ deny  → AccessDeniedException → HTTP response handled by security
             └─ allow → continue chain → Controller / Service
```

At the method layer, `@EnableMethodSecurity` uses interceptors such as `AuthorizationManagerBeforeMethodInterceptor` and `AuthorizationManagerAfterMethodInterceptor` to evaluate before/after methods. `@PreAuthorize`, `@PostAuthorize`, `@Secured`, and JSR-250 are served by the appropriate managers/interceptors.

`AuthorizationManager<T>` is a typed abstraction over the protected target (e.g., `RequestAuthorizationContext` or `MethodInvocation`), letting policies inspect both actor and resource/arguments. `Supplier<Authentication>` defers fetching Authentication until truly needed, benefiting `permitAll`/`denyAll` and user-independent rules.

### 3.2. Result types and abstain

In the 6.4+ and 7.x lines, the new API conceptually looks like:

```java
// Excerpt of modern API concept, not a standalone Java file.
AuthorizationResult authorize(
    Supplier<Authentication> authentication,
    T secureObject);
```

`new AuthorizationDecision(true)` means allow, `new AuthorizationDecision(false)` means deny; `null` can represent "abstain" for implementations that permit it. `AuthorizationManager.verify(...)` uses the result to throw `AccessDeniedException` on a deny decision. **Do not assume abstain = deny or abstain = allow across every composition mechanism.** For instance, `AuthorizationManagers.allOf/anyOf` overloads have rules for when all abstain or the list is empty; choose an explicit fallback and test the case where no policy matches.

When using `@PreAuthorize`/`@PostAuthorize`, Spring Security usually creates the appropriate managers automatically; write custom managers only when policy is genuinely complex, needs domain data, or integrates with external authorization systems.

### 3.3. Old-to-new mapping

| Legacy | Modern Equivalent | What Semantics Must Be Preserved? |
| --- | --- | --- |
| `FilterSecurityInterceptor` + `authorizeRequests(...)` | `AuthorizationFilter` + `authorizeHttpRequests(...)` | Matcher order, fallbacks, dispatchers, status codes |
| `SecurityMetadataSource` / `ConfigAttribute` | `RequestMatcher`/config DSL, manager receiving context | URL/method scope, path variables, resource ownership |
| `AccessDecisionVoter` | One `AuthorizationManager<T>` per policy | Grant/deny/abstain, vetoes, and input data |
| `AffirmativeBased` | `AuthorizationManagers.anyOf(...)` or explicit OR policy | Whether one grant overrides a deny; all-abstain fallback |
| `UnanimousBased` | `AuthorizationManagers.allOf(...)` or explicit AND policy | Whether one deny vetoes; all-abstain fallback |
| `ConsensusBased` | Tested custom composite policy | Ties, majority, abstain handling |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Which annotations are actually enabled and proxy behavior |
| `MethodSecurityInterceptor` | Before/after method authorization interceptors | Pre/post evaluation timing, side effects, self-invocation |
| Custom expression voter | `WebExpressionAuthorizationManager` or type-safe manager | SpEL semantics, bean names, role prefix, principal/resource context |

There is no safe universal "find/replace" across all these pairs. For example, `hasRole("ADMIN")` normally checks authority `ROLE_ADMIN`, whereas `hasAuthority("ADMIN")` checks the exact string `ADMIN`; swapping them carelessly causes false denials or false allows.

## 4. Controlled, Layer-by-Layer Migration

### Step 1 – Capture the running policy

Inventory all uses of `AccessDecisionManager`, `AccessDecisionVoter`, `SecurityMetadataSource`, `FilterSecurityInterceptor`, `MethodSecurityInterceptor`, `@EnableGlobalMethodSecurity`, and `authorizeRequests`. Record URL patterns/methods, HTTP methods, matcher order, roles, scopes, owner/tenant rules, business states, and tie/all-abstain/veto configurations. Do not assume every voter depends solely on roles.

For policies like "account locked," "suspended," "different tenant," or "edit own resource only," determine whether **deny is an absolute veto**. Test every sensitive case before migrating.

### Step 2 – Migrate HTTP rules

**Legacy** example, for identification only (illustrative snippet, not a standalone buildable app):

```java
http.authorizeRequests()
    .antMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

New Spring Security 6.x example (inside `@Bean SecurityFilterChain`):

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/reports/**").hasAuthority("report:read")
    .anyRequest().denyAll()
);
```

On the new line, do not rely on legacy `antMatchers`. Use `requestMatchers(...)` for the right web context (Servlet), distinguishing `securityMatcher` — which selects the chain — from `requestMatchers` — which selects a rule inside the chain. Rules in `authorizeHttpRequests` are evaluated **in declaration order**, so place specific matchers before broad ones. Choose `denyAll` fallback if you want "open only listed routes"; if the application previously used `authenticated` for remaining routes, switching to `denyAll` is an **intentional policy change** requiring testing and review.

Do not infer HTTP 401/403 from Java expressions alone: anonymous callers may be routed to login/401 depending on the entry point, while authenticated callers lacking permissions normally get 403; verify the filter chain and app setup with `MockMvc`.

### Step 3 – Migrate method security

```java
// Legacy:
@EnableGlobalMethodSecurity(prePostEnabled = true)

// Modern:
@EnableMethodSecurity
```

`@EnableMethodSecurity` enables pre/post annotations by default; if the codebase uses `@Secured` or JSR-250 (`@RolesAllowed`), enable the corresponding flags (`securedEnabled = true`, `jsr250Enabled = true`) and check behavioral parity. The Spring Boot security starter **does not automatically enable** method security merely by being on the classpath.

Example of a permission- and resource-based method policy (illustrative snippet, requires an actual `documentPolicy` bean):

```java
@PreAuthorize("hasAuthority('document:write') "
    + "and @documentPolicy.canEdit(authentication, #p0)")
public void editDocument(long documentId, String newTitle) {
    // Write to DB after authorization passes; real services also need
    // tenant and concurrency checks at the repository/SQL layer.
}
```

Use `#p0` to avoid depending on the Java compiler retaining parameter names. Ensure invocations **go through the Spring-managed proxy**; `this.editDocument(...)` on the same bean can bypass advice. For writes, `@PostAuthorize` runs after the method body and must not replace a pre-mutation gate.

### Step 4 – Replace voters with managers for equivalent policies

A custom `AccessDecisionVoter` checking "user is suspended" can usually be replaced by an `AuthorizationManager<RequestAuthorizationContext>`. With the new policy, there is no need to recreate `ConfigAttribute` just to return the three legacy constants. Use a type-safe context and return an `AuthorizationDecision`.

Example using a lambda to keep source compatibility across Spring Security 6.x (`check` SAM) and 7.x (`authorize` SAM) on their respective branches, as long as framework dependencies and generic signatures match the compiler target:

```java
// Placed in @Configuration; this snippet illustrates a custom bean.
@Bean
AuthorizationManager<RequestAuthorizationContext> activeAccount() {
    return (authentication, context) -> {
        Authentication user = authentication.get();
        boolean active = user != null
            && user.isAuthenticated()
            && !"suspended".equals(user.getName());
        return new AuthorizationDecision(active);
    };
}
```

This is a **hardcoded demo rule**, not a production account-status check. In production, use a trusted data source (user/account repository or policy service), accounting for caching/revocation, timeouts, error policies, and ensuring disabled users or tenant restrictions are not bypassed. Call `authentication.get()` only when needed; do not force early retrieval if identity is unnecessary.

If you have both "must have `report:read`" **and** "account is not suspended," they are **AND** conditions. Using `anyOf` lets a read-permission grant pass despite a suspended-account deny — repeating the `AffirmativeBased` pitfall. Use `allOf` or a policy with an explicit deny veto, plus a test for a suspended account that still holds a valid role/scope.

### Step 5 – Temporary adapters are possible, but finish the migration

While many voters/domain policies cannot yet be migrated simultaneously, an `AuthorizationManager` adapter can invoke `AccessDecisionManager.decide(...)` and map the outcome:

```java
// Migration pseudocode: requires a metadata source matching the object type.
try {
    oldManager.decide(authentication, secureObject, attributes);
    return new AuthorizationDecision(true);
} catch (AccessDeniedException denied) {
    return new AuthorizationDecision(false);
}
```

An adapter for a **single voter** must map all three values: `ACCESS_GRANTED → true`, `ACCESS_DENIED → false`, `ACCESS_ABSTAIN → null`. Do not map abstain to true, and do not coerce every exception into "deny"; convert only `AccessDeniedException` as designed, letting other system errors surface or handling them under an explicit fail-closed policy.

Adapters must mind input types: request managers typically receive `RequestAuthorizationContext`, whereas legacy voters may expect `FilterInvocation`/`ConfigAttribute`. Do not force-cast or synthesize mismatched metadata. Verify runtime types and prove parity with tests. Once new policies are verified, remove the adapter and legacy dependencies.

### Step 6 – Spring Security 7 branch

If upgrading to Spring Security 7 while still needing to run legacy Access APIs temporarily, add the dependency **only while code still uses it**:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-access'
}
```

Spring Security 7 moves `AccessDecisionManager`, `AccessDecisionVoter`, and related Access APIs into this module. Use dependency management/BOM matching the framework version; do not pull a 6.x jar to supply missing 7.x classes. This is a **temporary compatibility step**, not a new architecture to imitate. When writing a custom `AuthorizationManager` class in 7.x, override `authorize(...)` per the current API; in 6.x, check the `check(...)` interface of the running version. Lambdas/factories reduce source-level differences.

## 5. Critical Scenario: The Suspended Gate Must Hold Veto Power

Suppose the system requires:

- Users must hold the exact authority `report:read` to read reports.
- A `suspended` account must be denied **even if its token still carries old authorities**.
- Admin routes require `ROLE_ADMIN`.
- All unregistered routes are denied.

Legacy had voter A returning `GRANT` for `report:read` and voter B returning `DENY` for suspended. If the strategy was `AffirmativeBased`, the outcome could be **ALLOW** even though business rules require DENY. When migrating, select a policy that expresses the **correct** condition and include a test proving a suspended actor cannot access it.

Desired logical expression:

```text
allowReports(actor) =
    actor.isAuthenticated
    AND actor.hasAuthority("report:read")
    AND NOT actor.isSuspended

allowAdmin(actor) =
    actor.hasAuthority("ROLE_ADMIN")

fallback = denyAll
```

If locked accounts are determined via DB/cache instead of username, swap only the **trusted status source**; never alter the AND/veto semantics.

## 6. Complete Integration Example: Spring Security 6.x / Spring Boot 3.x

An executable test of a real `SecurityFilterChain` via `MockMvc`, with a custom `AuthorizationManager` lambda and `AuthorizationManagers.allOf`. Uses Java 17+, JUnit 5, and Spring Security Test. No legacy `AccessDecisionManager` classes needed.

### 6.1. Dependencies for a Gradle module with the Spring Boot plugin/BOM

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If the runtime already includes the starters, add only what is missing; avoid duplicate declarations. With Spring Boot 3.x, avoid pinning Security to a version differing from the BOM. Because the following tests only use GET, CSRF protection does not cause denials; in real APIs, state-changing operations also need CSRF handling when using cookies/sessions.

Create **a single file** `src/test/java/example/security/AuthorizationMigrationTest.java`:

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthorizationMigrationTest.App.class)
@AutoConfigureMockMvc
class AuthorizationMigrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({SecurityConfig.class, ApiController.class})
    static class App {}

    @Configuration
    @EnableWebSecurity
    static class SecurityConfig {

        @Bean
        AuthorizationManager<RequestAuthorizationContext> activeAccount() {
            // Demo rule: "suspended" represents a locked account.
            // Lambda keeps test code free of overriding check()/authorize()
            // differently across Security branches.
            AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

            return (authentication, context) -> {
                Authentication actor = authentication.get();
                boolean active = actor != null
                    && actor.isAuthenticated()
                    && !trustResolver.isAnonymous(actor)
                    && !"suspended".equals(actor.getName());

                return new AuthorizationDecision(active);
            };
        }

        @Bean
        SecurityFilterChain apiSecurity(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> activeAccount
        ) throws Exception {

            AuthorizationManager<RequestAuthorizationContext> canReadReport =
                AuthorizationManagers.allOf(
                    activeAccount,
                    AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasAuthority("report:read")
                );

            http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .access(canReadReport)
                .requestMatchers(HttpMethod.GET, "/api/admin/status")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            );
            http.httpBasic(Customizer.withDefaults());

            return http.build();
        }
    }

    @RestController
    static class ApiController {
        @GetMapping("/api/reports/{id}")
        String report(@PathVariable long id) {
            return "report:" + id;
        }

        @GetMapping("/api/admin/status")
        String adminStatus() {
            return "admin:ok";
        }
    }

    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void scopeAndActiveAccountCanRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isOk())
            .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(username = "suspended", authorities = "report:read")
    void suspendedAccountIsDeniedEvenWithScope() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void activeButMissingScopeIsDenied() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminRoleCanCallAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:ok"));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminRoleDoesNotImplyReportScope() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void unmatchedRouteIsDeniedByFallback() throws Exception {
        mvc.perform(get("/api/unlisted"))
            .andExpect(status().isForbidden());
    }
}
```

Run from the corresponding Gradle module:

```bash
./gradlew test --tests "example.security.AuthorizationMigrationTest"
```

On Windows use `gradlew.bat`; in multi-project builds you may need task `:module-path:test`. **Expected: 6 tests PASS** when using the Spring Boot 3.x dependencies and configuration above. JUnit assertions verify HTTP statuses/responses; this is not a `main` program with fixed stdout.

### 6.2. Reading test results to understand the policy

| Test | Authentication | Expected | Meaning |
| --- | --- | --- | --- |
| `scopeAndActiveAccountCanRead` | Alice, `report:read` | 200 + `report:42` | Has required authority and is not suspended |
| `suspendedAccountIsDeniedEvenWithScope` | Suspended, `report:read` | 403 | **Deny veto** still overrides scope grant |
| `activeButMissingScopeIsDenied` | Bob, `ROLE_USER` | 403 | Being active does not grant `report:read` scope |
| `adminRoleCanCallAdminRoute` | Admin, `ROLE_ADMIN` | 200 + `admin:ok` | `hasRole("ADMIN")` checks the role prefix |
| `adminRoleDoesNotImplyReportScope` | Admin, `ROLE_ADMIN` | 403 | Roles and authorities are distinct unless hierarchy is configured |
| `unmatchedRouteIsDeniedByFallback` | Alice, `report:read` | 403 | `anyRequest().denyAll()` locks down undeclared endpoints |

Note that `@WithMockUser` constructs a mock Authentication for testing and **does not test real login/JWT/session handling or revocation**. Using username `"suspended"` is a hardcoded status marker to test composition; production code needs a trusted account-status lookup policy and explicit repository error handling.

### 6.3. Why not use `anyOf`?

If written incorrectly:

```java
AuthorizationManager<RequestAuthorizationContext> unsafe =
    AuthorizationManagers.anyOf(
        activeAccount,
        AuthorityAuthorizationManager
            .<RequestAuthorizationContext>hasAuthority("report:read")
    );
```

then a suspended user **who still has `report:read`** can be permitted because the scope branch allows (OR), even though the `activeAccount` branch denies. `allOf` in the main example accurately expresses **both conditions are required**. This logic distinction matters more than renaming classes.

Using `allOf`/`anyOf` does not automatically solve **tenant/owner** policies: checking specific resources requires verifying resource IDs from context and trusted principals, or checking in the service/repository layer. Do not trust an unauthenticated `X-Tenant` request header. Furthermore, Spring Security versions may differ in all-abstain behavior relative to your policy; test the case where no delegate renders a decision and configure an explicit fallback.

## 7. Thorough Migration Testing Beyond the HTTP Example

| Risk | Mandatory Regression Test |
| --- | --- |
| Legacy `AffirmativeBased` allowed despite DENY | Case with one voter granting and one denying; verify against the **approved** policy |
| `ConsensusBased` with custom tie-breaking | Grant/deny/abstain counts and ties, including when no voter applies |
| Missing metadata causing all voters to abstain | URLs/methods without rules must hit a safe fallback |
| Matcher order changes | Narrow matchers evaluated first; unmatched URLs and dispatcher types tested |
| Role prefix/hierarchy differences | `ROLE_ADMIN`, `ADMIN`, `hasRole`, `hasAuthority` semantics not swapped |
| Resource belongs to another tenant | Denied even with valid functional scope; no cross-tenant data impact |
| New method security not enabled | Via proxy: `@PreAuthorize` denies before method body; self-invocation cases identified |
| Altered transactions/side effects | Verify DB state and outbound effects, not just 403 |
| Locked/revoked account | Denied even when bearer/session retains stale authorities |
| Different Security branches | Build/test on the actual version, since `check`/`authorize` signatures differ |

Distinguish **pure policy tests** (calling managers directly, asserting `isGranted()`) from **integration tests** (going through filter chains/service proxies). Both have value: unit tests easily cover many vote combinations; integration tests prove matchers and advisors are actually active. For HTTP, test both anonymous and fully authenticated callers when required by contract; for services, verify boundary exceptions translate into expected HTTP responses.

**Do not enable both legacy and modern interceptors on the same URL/method without understanding ordering**, as this can double-check, alter semantics, or complicate diagnostics. Layer-by-layer migration with clear coverage evidence is far less risky.

## 8. Common Upgrade Pitfalls

### "Changing `authorizeRequests` to `authorizeHttpRequests` is enough"

The new API uses `AuthorizationFilter` and `AuthorizationManager`, but matchers, fallbacks, dispatchers, custom policies, method annotations, and exception handling also matter. If the old decision chain had custom voters, changing the DSL alone does not carry that logic over.

### "If one voter denies, access is definitely denied"

False under `AffirmativeBased` if another voter grants. When deny must act as a veto, use explicit AND/veto logic and test grant+deny combinations. Do not translate every voter list into OR.

### "Abstain means allow"

`ACCESS_ABSTAIN` means the voter renders no decision. `null` in `AuthorizationManager` can likewise represent abstain; the final outcome depends on wrappers/composition/fallbacks. Never default to allow when no rule matches.

### "Using `hasRole('ADMIN')` is equivalent to `hasAuthority('ADMIN')`"

By default, `hasRole("ADMIN")` checks `ROLE_ADMIN`; `hasAuthority("ADMIN")` checks exact `ADMIN`. When upgrading, verify `GrantedAuthority` values and prefixes/hierarchies.

### "Having `spring-boot-starter-security` automatically enables method security"

False. `@EnableMethodSecurity` is required to apply method annotations in standard configurations. Tests must invoke the Spring proxy bean; do not use `new Service()` to prove advice.

### "Security 7 removed AccessDecisionManager, so just add `spring-security-access` and keep the old code forever"

The legacy module is strictly a transitional bridge. For new code, write `AuthorizationManager`/policy services; remove the dependency once legacy classes are gone. If builds fail on 7, check both artifacts/modules **and** API signatures.

### "Checking for 403 is enough"

A 403 can originate from multiple places: matchers, method security, exception handlers. When policies guard mutations, also test DB/queue/email side effects, owner/tenant scopes, and transaction boundaries; do not assume an exception automatically rolls back already-dispatched side effects.

## 9. Migration Acceptance Checklist

- [ ] Inventory exists of legacy voters/decision managers/config attributes and affected routes/methods.
- [ ] Truth table exists for allow/deny/abstain, ties, all-abstain, and veto policies.
- [ ] Appropriate built-in or custom managers selected; `anyOf`/`allOf` reflect the **approved business policy**.
- [ ] `authorizeHttpRequests` matches HTTP methods/paths in the right order with an explicit fallback; `securityMatcher` is not confused.
- [ ] `@EnableMethodSecurity` and `@Secured`/JSR-250 flags configured as needed; tested through proxies.
- [ ] Object/tenant permissions and account statuses were not lost while replacing voters.
- [ ] Regression tests cover grant+deny, all-abstain, role prefixes, suspended accounts, unknown routes, anonymous callers, and side effects.
- [ ] Documentation and dependencies align with Spring Security 6.x or 7.x; `spring-security-access` is present only while legacy usage remains.
- [ ] Tested directly on the target deployment version; adapters, voters, and old configs removed after parity and desired permissions were verified.

**Conclusion:** `AccessDecisionManager` aggregates results from multiple `AccessDecisionVoter`s using a strategy; `AuthorizationManager` expresses permission decisions directly and composes policies clearly. What must remain intact during migration is **who is allowed to perform which action on which resource**, including when conditions conflict or when none apply.

## Official Documentation for Version Cross-Checking

- [Spring Security 7 – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, adapters, and the legacy voting model.
- [Spring Security 7 – Authorization Migration](https://docs.spring.io/spring-security/reference/migration/servlet/authorization.html): `spring-security-access` module and upgrade guidance.
- [Spring Security 7 – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `AuthorizationFilter`, matcher order, and DSL.
- [Spring Security 7 – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, before/after method interceptors.
- [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): reference for reading 6.x codebases.
- [Spring Security 6.5 – AuthorizationManager Java API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `check`/`authorize` in 6.x.
