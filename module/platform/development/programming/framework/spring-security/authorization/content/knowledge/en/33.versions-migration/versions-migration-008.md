# WebExpressionAuthorizationManager When Migrating Legacy SpEL Configurations

## 1. Context and Objectives

When upgrading a Servlet Spring Security application from `authorizeRequests`/`antMatchers`/`access(String)` to `authorizeHttpRequests`, one challenge is preserving the **Spring Expression Language (SpEL)** rules used to decide permissions on HTTP requests. Older examples might include `hasRole('ADMIN') and hasAuthority('report:read')`, comparing a username against a URL variable, or calling a Spring bean to decide access. The modern API uses **`AuthorizationManager`**; you can no longer assume the `.access(...)` DSL accepts a raw SpEL string directly.

`WebExpressionAuthorizationManager` serves as the adapter to **evaluate legacy web SpEL expressions within the `AuthorizationManager<RequestAuthorizationContext>` contract**. It lets you migrate rule by rule, keeping required behavior while building more testable policies. However, changing the API does not automatically preserve role semantics, path matching, bean resolvers, permission evaluators, rule ordering, or per-record access permissions.

After this lesson, you should be able to:

1. Identify the legacy and modern execution paths of a Servlet authorization decision.
2. Migrate an `access("...")` rule to `access(new WebExpressionAuthorizationManager("..."))` **for the right version**.
3. Know when to use the builder in Spring Security 7+, when to configure an expression handler, or when to replace SpEL with a dedicated `AuthorizationManager`.
4. Test **allow/deny** equivalence before and after upgrading, covering HTTP methods, paths, authorities, beans, dispatches, CSRF, and out-of-scope resources.
5. Maintain the **deny by default** principle, never turning complex rules into `authenticated()` just to make the configuration run.

The scope of this lesson is **Spring Security Servlet / HttpSecurity**, not WebFlux (WebFlux uses different `AuthorizationContext` types and filters) or `@PreAuthorize` in method security. The Spring snippets below are **integration fragments** requiring your project's dependencies/configuration/controllers; the standalone Java program in Section 11 tests a semantic truth matrix and does not run the real SpEL engine.

## 2. From FilterSecurityInterceptor to AuthorizationFilter

The legacy path typically wires URL rules through `FilterSecurityInterceptor` alongside a metadata source, `ConfigAttribute`, `AccessDecisionManager`, voters, or expressions. The modern path uses `AuthorizationFilter` and `AuthorizationManager<RequestAuthorizationContext>` to render request-based decisions:

~~~text
Legacy configuration (Spring Security 5.x and compatible lines)
  authorizeRequests()
    .antMatchers("/reports/**")
    .access("hasRole('ADMIN') and hasAuthority('report:read')")
       |
       v
  FilterSecurityInterceptor + expression/voter configuration

New configuration (Spring Security 6.x/7.x, Servlet)
  authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**")
    .access(new WebExpressionAuthorizationManager(
        "hasRole('ADMIN') and hasAuthority('report:read')")))
       |
       v
  AuthorizationFilter
       |
       v
  RequestMatcherDelegatingAuthorizationManager
       |
       v
  WebExpressionAuthorizationManager
       |
       v
  SpEL on RequestAuthorizationContext -> GRANTED/DENIED
~~~

Points to keep straight:

- **`requestMatchers` chooses which rule applies**, while **`AuthorizationManager` decides allow or deny** for the matched request. A faulty matcher can prevent a valid expression from ever running.
- `AuthorizationFilter` passes a **`Supplier<Authentication>`** and request details to the manager. Fetching authentication can be deferred for `permitAll`/`denyAll`.
- In the `authorizeHttpRequests` DSL, **the first rule matching the request is used**. Placing `/**` or `anyRequest()` too early shadows stricter rules further down.
- `WebExpressionAuthorizationManager` does not grant new authorities. It **checks** the authorities present in the `Authentication` produced by your login/JWT mechanism.
- Migrating at the request layer does not replace authorization in the service/repository layer: being able to reach an endpoint does not imply permission on every `documentId` or tenant.

## 3. Version-Based API Map: Avoid Mixing 6.x and 7.x Examples

| Topic | Legacy Style | 6.x Direction | 7.x Direction |
| --- | --- | --- | --- |
| URL DSL | `authorizeRequests` | `authorizeHttpRequests` | `authorizeHttpRequests`; legacy API removed |
| Matcher | `antMatchers`/`mvcMatchers` per legacy config | `requestMatchers` with appropriate overloads/matchers | `requestMatchers`, noting current version's matcher/servlet path behavior |
| URL expression syntax | `.access("hasRole('ADMIN')")` | `.access(new WebExpressionAuthorizationManager("hasRole('ADMIN')"))` | Same constructor or builder `withDefaults().expression(...)` |
| Multiple expressions sharing handler | Legacy expression handler | `new WebExpressionAuthorizationManager(...)` and `setExpressionHandler(...)` if needed | `WebExpressionAuthorizationManager.withDefaults()` or `withExpressionHandler(...)`; old setter deprecated |
| Simple conditions | SpEL strings like `hasRole('ADMIN')` | `.hasRole("ADMIN")`, `.hasAuthority("...")` | Same, prefer type-safe APIs |
| Complex bean policies | `@webPolicy.check(authentication, request)` in SpEL | `.access((authentication, context) -> new AuthorizationDecision(...))` or handler with bean resolver | Prefer direct manager; builder bean supports bean references in expressions |

**API milestones:** `WebExpressionAuthorizationManager` has existed since Spring Security 5.8. `WebExpressionAuthorizationManager.Builder` and the `withDefaults()`/`withExpressionHandler(...)` factories were added in **7.0**, so **do not copy the builder into code running Spring Security 6.3/6.4/6.5**. In 6.5 there is `setExpressionHandler(...)`; in 7.0 that setter is marked deprecated in favor of the builder. Spring Security 7 also changes other `AuthorizationManager` APIs, such as dropping `check` for `authorize`: when implementing a manager manually, compile against your exact version.

Rely on the **actual dependency graph**, never infer Spring Security versions merely from online snippets or Spring Boot version numbers. Use BOMs/dependency-management plugins and check for transitive conflicts before migrating.

## 4. Migrating a Legacy SpEL Expression to `WebExpressionAuthorizationManager`

Suppose the legacy system has a reports page restricted to users who both hold `ROLE_ADMIN` and possess the `report:read` authority.

### Before: `authorizeRequests` style (legacy example, do not apply verbatim to 7.x)

~~~java
// Legacy Spring Security 5.x configuration fragment
http.authorizeRequests()
    .antMatchers("/reports/**")
        .access("hasRole('ADMIN') and hasAuthority('report:read')")
    .anyRequest().authenticated();
~~~

This is a historical fragment for semantic comparison. `and` requires **both** conditions. The same string with `or` would permit an actor holding only one permission, so changing the operator alters security policy.

### After: Java config for Spring Security 6.x and 7.x

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.expression.WebExpressionAuthorizationManager;

@Configuration
class WebAuthorizationConfig {
    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/reports/**").access(
                new WebExpressionAuthorizationManager(
                    "hasRole('ADMIN') and hasAuthority('report:read')")
            )
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Key points to understand:

- `requestMatchers("/reports/**")` selects the target URLs. If the old rule also constrained `HttpMethod.GET`, explicitly specify the HTTP method in the new matcher; do not expose the rule to POST/DELETE.
- `.access(...)` here accepts an `AuthorizationManager<RequestAuthorizationContext>`, not the old string. `new WebExpressionAuthorizationManager(expression)` parses and evaluates the web expression.
- `hasRole('ADMIN')` normally checks `ROLE_ADMIN` per the default prefix; `hasAuthority('report:read')` checks the exact string. JWT converters/role hierarchies can affect actual authorities; test the authentication source too.
- `.anyRequest().denyAll()` is a fail-closed choice for the example. If the old contract only required authentication for other URLs, document the difference before deciding on `authenticated()`. **Migrate for equivalence first; harden intentionally afterward and test separately.**
- The snippet above only configures authorization; a real web app also needs form login/OAuth2 resource server, CSRF, CORS, session management, entry points, and controllers. Never treat this snippet as a "complete production config" without accounting for existing authentication.

### Simple expressions should become type-safe DSL rules

There is no need to retain SpEL for simple conditions:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/docs/**").hasAuthority("SCOPE_documents.read")
    .requestMatchers("/public/**").permitAll()
    .anyRequest().denyAll()
);
~~~

Besides reducing typos in SpEL strings, the DSL API clarifies permission structure. For rules requiring **multiple permissions simultaneously**, pick a composite manager (if supported by your version) or a dedicated policy instead of changing `and` into `hasAnyAuthority`/`hasAnyRole` ("any" APIs mean OR). Specifically, never replace `hasRole('ADMIN')` with `authenticated()` merely to avoid configuring a converter.

## 5. Spring Security 7+: Builder Helps Manage Multiple Expressions

Starting in 7.0, managers can be constructed via a builder:

~~~java
// Spring Security 7.0+; the Builder class does not exist in 6.x.
WebExpressionAuthorizationManager.Builder expressions =
    WebExpressionAuthorizationManager.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/ops/**").access(
        expressions.expression("hasRole('OPS') and isFullyAuthenticated()")
    )
    .requestMatchers("/users/{name}").access(
        expressions.expression("#name == authentication.name")
    )
    .anyRequest().denyAll()
);
~~~

`withDefaults()` creates a builder using the default web expression handler; `expression(String)` builds a manager for each expression. Using the builder does **not** fix flawed expressions, automatically enforce role/tenant checks, or make legacy rules safer. Its main benefits are centralizing handler configuration and providing a convenient migration path.

If expressions must reference Spring beans via `@policyBean`, the 7.x guide recommends **publishing the builder as a Spring bean** so Spring provides bean resolution:

~~~java
// Spring Security 7.0+: configuration fragment; requires a reportPolicy bean.
@Bean
WebExpressionAuthorizationManager.Builder webExpressions() {
    return WebExpressionAuthorizationManager.withDefaults();
}

@Bean
SecurityFilterChain web(HttpSecurity http,
        WebExpressionAuthorizationManager.Builder expressions)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").access(
            expressions.expression(
                "hasAuthority('report:read') and "
                + "@reportPolicy.canView(authentication, request)"
            )
        )
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

`reportPolicy.canView(Authentication, HttpServletRequest)` in the example is an **application bean contract** that must be implemented securely and return a boolean. Verify a bean named `reportPolicy` actually exists in the context, the resolver is wired properly, and untrusted query/header values are never relied upon as proof of permission. Never copy both `web(...)`/`webSecurityFilterChain(...)` methods from different examples into the same app as two `SecurityFilterChain`s accidentally covering the same scope; each snippet is an **independent option**.

In Spring Security 6.5, if bean references in SpEL must truly be retained, you can configure a `DefaultHttpSecurityExpressionHandler` typed for `RequestAuthorizationContext` and attach it to the manager:

~~~java
// Spring Security 6.5 code fragment; requires ApplicationContext context.
DefaultHttpSecurityExpressionHandler handler =
    new DefaultHttpSecurityExpressionHandler();
handler.setBeanResolver(new BeanFactoryResolver(context));

WebExpressionAuthorizationManager manager =
    new WebExpressionAuthorizationManager(
        "@reportPolicy.canView(authentication, request)");
manager.setExpressionHandler(handler);
~~~

The corresponding imports are `org.springframework.security.web.access.expression.DefaultHttpSecurityExpressionHandler`, `org.springframework.context.expression.BeanFactoryResolver`, and `org.springframework.security.web.access.expression.WebExpressionAuthorizationManager`. This is an intentional migration workaround; `setExpressionHandler` is deprecated in 7.x, so on 7.0+ use `withExpressionHandler(handler)` or a builder bean. Only configure a custom handler after confirming which legacy customizations genuinely need to stay.

**Common pitfall:** the legacy `DefaultWebSecurityExpressionHandler` works with `FilterInvocation`; `DefaultHttpSecurityExpressionHandler` is built for the new manager's `RequestAuthorizationContext`. Never force-cast or copy old handler configurations verbatim onto the new manager when the generic context differs. Re-wire role hierarchies, permission evaluators, bean resolvers, trust resolvers, and custom root methods against the proper version's API and test them.

## 6. When Should You Drop SpEL and Write an `AuthorizationManager`?

Spring Security recommends preferring managers or type-safe APIs when possible. An expression calling a bean such as:

~~~java
// Legacy: an expression mixing role and business policy
.access("hasRole('REVIEWER') and @reportPolicy.canView(authentication, request)")
~~~

can be converted into a dedicated manager with clean dependency injection and unit tests:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authentication.*;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Spring Security Java fragment, requires a real ReportPolicy interface.
final class ReportAccessManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ReportPolicy policy;

    ReportAccessManager(ReportPolicy policy) {
        this.policy = policy;
    }

    // The lambda version below is compatible with .access(...) in 6.x/7.x.
    // For directly implemented classes, the check/authorize signature must match the version.
    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {
        Authentication actor = authentication.get();
        boolean reviewer = actor.getAuthorities().stream()
            .anyMatch(a -> "ROLE_REVIEWER".equals(a.getAuthority()));
        return new AuthorizationDecision(
            reviewer && policy.canView(actor, context.getRequest()));
    }
}
~~~

**Important version note:** the `check(...)` example above uses the 6.x contract (in 7.x, `AuthorizationManager#check` was removed from the API; implement `authorize(...)` with the appropriate `AuthorizationResult` return type). To avoid mixing 6.x/7.x signatures during migration, you can use a **lambda** in the DSL for small managers, which works across both generations:

~~~java
// ReportPolicy is an injected bean; boolean canView(Authentication, HttpServletRequest)
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").access((authentication, context) -> {
        var actor = authentication.get();
        boolean reviewer = actor.getAuthorities().stream()
            .anyMatch(a -> "ROLE_REVIEWER".equals(a.getAuthority()));
        return new AuthorizationDecision(
            reviewer && reportPolicy.canView(actor, context.getRequest()));
    })
    .anyRequest().denyAll()
);
~~~

The lambda above does not depend on the abstract method name when compiled against the right Spring Security version; when building a standalone manager class, **do not** copy a 6.x `check(...)` example into 7.x. Calling `policy.canView` must genuinely enforce data scope. Never write `return new AuthorizationDecision(true)` just to make the configuration pass.

Prefer a dedicated manager class when decisions require multiple steps, I/O to a policy service, input validation, caching, auditing, and AND/OR combinations. For a single check like `hasRole('ADMIN')`, the `hasRole` DSL is simpler.

### Why not keep SpEL forever?

- Avoids runtime bean/variable typos and fragility to method signature or bean resolver changes.
- Centralizes domain policy with typed inputs/outputs and straightforward unit tests.
- Clearly controls how the principal is fetched from `Supplier<Authentication>` and how object permissions are verified.
- Simplifies reviewing the permission matrix when migrating many routes.
- Eliminates the risk of dynamic expressions built from user input (never pass client-controlled SpEL into `WebExpressionAuthorizationManager`).

Keep SpEL for the transition phase or when it expresses a clear, well-tested policy; decide whether to keep or rewrite based on complexity, not syntactic preference.

## 7. Preserving Accurate Web Expression Semantics

### 7.1. `hasRole`, `hasAuthority`, and authority sources

- `hasRole('ADMIN')` looks for `ROLE_ADMIN` by default; do not use `hasRole('ROLE_ADMIN')` to "fix" a prefix mismatch.
- `hasAuthority('SCOPE_reports.read')` checks the **exact** authority string. JWT OAuth scopes are typically mapped to `SCOPE_...` if the standard resource server converter remains in place.
- `hasAnyRole('ADMIN','EDITOR')` is OR; `hasRole('ADMIN') and hasRole('EDITOR')` is AND. Even if `hasAllAuthorities` exists in a newer DSL, verify version and exact behavior.
- A role hierarchy can make `ROLE_ADMIN` imply `ROLE_EDITOR`, yet custom legacy hierarchies are not automatically attached to every new expression handler. Compare decisions before and after using a user with an inherited role.
- A valid JWT is not enough: `GrantedAuthority` also depends on the converter. Test both scope-only tokens and role-bearing tokens; do not hardcode authorities in every test and skip testing the real converter.

### 7.2. `authentication`, `principal`, and authentication states

`authentication` is the `Authentication` provided by Spring Security in the evaluation context; `principal` is its principal. Helpers such as `isAuthenticated()`, `isAnonymous()`, `isRememberMe()`, and `isFullyAuthenticated()` carry distinct meanings. `isFullyAuthenticated()` excludes remember-me/anonymous per the trust resolver; mechanically changing it to `authenticated()` can allow requests the legacy policy blocked.

Test all groups: anonymous, form login, remember-me, bearer tokens, tokens lacking scopes, locked users, and `Authentication` built by custom providers. In stateless JWT apps, remember-me may be irrelevant, yet you should still document the old route's contract before removing a condition.

### 7.3. Variables in the URL

With a matcher that extracts path variables, an expression can compare names:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/profiles/{name}").access(
        new WebExpressionAuthorizationManager(
            "#name == authentication.name"))
    .anyRequest().denyAll()
);
~~~

`#name` in the expression is a **URI template variable** placed in context by the matcher, **not** a `?name=...` query parameter and not a controller magic argument. Test `/profiles/alice`, `/profiles/bob`, encoded paths, and case sensitivity per your active matcher. If migrating from `antMatchers` to `requestMatchers`/`PathPatternRequestMatcher` alters variable extraction, the expression may evaluate to false or read a different variable.

Note that comparing `authentication.name` to a path only makes sense when the path genuinely represents a normalized username. For resource IDs like `/documents/101`, **never** replace ownership policies with string comparisons; look up owner/tenant/ACL in the service layer.

### 7.4. Request metadata and policy beans

A legacy expression might use `request.method`, `request.remoteAddr`, `hasIpAddress(...)`, or `@webPolicy.check(authentication, request)`. When migrating, re-verify:

- `request` in a web expression is the `HttpServletRequest` of the protected request, not a DTO, method argument, or principal.
- Behind a proxy/load balancer, `remoteAddr` or `X-Forwarded-For` requires proper trusted-proxy configuration; **never** treat self-declared client headers as admin privileges.
- `@bean` references only work when the expression handler has a bean resolver wired. When switching to a builder or direct manager, confirm the bean is actually invoked.
- `hasPermission(...)` requires a `PermissionEvaluator` with a matching contract. Moving from `DefaultWebSecurityExpressionHandler` to `DefaultHttpSecurityExpressionHandler` requires re-attaching the evaluator and testing object permissions.
- Do not paste method security's `@PreAuthorize("#documentId...")` into a URL expression expecting a `#documentId` method parameter; those are two separate evaluation contexts.

### 7.5. Boolean expressions and deny-by-default

The string `hasRole('ADMIN') and hasAuthority('report:read')` allows **only when both are true**. Pay close attention to parentheses when mixing `and`/`or`:

~~~text
(hasRole('ADMIN') or hasRole('AUDITOR')) and hasAuthority('report:read')
~~~

is not equivalent to

~~~text
hasRole('ADMIN') or (hasRole('AUDITOR') and hasAuthority('report:read'))
~~~

The second expression lets ADMIN bypass `report:read`. Changing operator precedence or dropping parentheses during migration is a security modification. Likewise, `permitAll or ...` is always true, and `denyAll and ...` is always false. Never use `permitAll` as a "fallback" when an expression fails to parse.

## 8. Matchers, Filter Chains, and Dispatches Can Change Outcomes Even If SpEL Stays Identical

Preserving expression text alone is **not enough**. Actual decisions result from multiple layers:

~~~text
HTTP request
  ├─ Which SecurityFilterChain matches the request?
  ├─ First matching matcher/rule in authorizeHttpRequests?
  ├─ Which mechanism created the Authentication?
  ├─ Which authorities does the manager/expression check?
  ├─ Dispatcher type REQUEST/FORWARD/ERROR/ASYNC?
  └─ Does the service/object policy verify the real resource?
~~~

### Matcher ordering

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/public/**").permitAll()
    .requestMatchers("/admin/**").access(
        new WebExpressionAuthorizationManager(
            "hasRole('ADMIN') and isFullyAuthenticated()"))
    .anyRequest().denyAll()
);
~~~

Specific rules must precede broader ones. If `/admin/**` appears before `/admin/public/**`, the public rule is never selected. With multiple `SecurityFilterChain`s using `securityMatcher(...)` and `@Order`, verify **chain selection** before inspecting inner rules.

### HTTP methods and servlet paths

If legacy protected only `GET /reports/**` with an expression, do not accidentally apply the same rule to POST/DELETE, or conversely open write permissions by omitting the method from the matcher. With multiple servlets or custom servlet mappings, use version-appropriate matchers with explicit servlet paths; never assume `antMatchers`, `mvcMatchers`, regex, and `PathPatternRequestMatcher` behave identically. Spring Security 7 guides toward `PathPatternRequestMatcher` in many cases; check matcher alignment with controllers, context paths, trailing slashes, URL encoding, case, and dispatchers.

### Dispatches and static resources

`AuthorizationFilter` checks authorization on applicable dispatches, potentially including `FORWARD`/`ERROR`; a view render or error handler can start returning 403 after migration. If allowed by specification, configure dispatcher types explicitly:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

This is an **application-specific choice**: do not blindly permit all dispatches if error endpoints can emit sensitive data. Generally prefer `permitAll` for static resources over `web.ignoring()`, since ignoring skips the entire security filter chain and security headers.

### CSRF, 401/403, and authentication

When a POST integration test receives 403, the cause may be a missing CSRF token **before reaching the expression**. When GET receives 401, the caller may simply be unauthenticated, which does not prove the expression failed. Distinguish 401/403 by entry point, bearer token authentication, and policy; test with valid request methods + credentials + appropriate CSRF. Never disable CSRF app-wide just because a migration test returned 403.

## 9. Typical Migration Errors and Fixes

| Symptom | Common Cause | Verification and Fix |
| --- | --- | --- |
| `.access("...")` fails to compile | New DSL expects `AuthorizationManager` | Use `new WebExpressionAuthorizationManager("...")` or a type-safe manager |
| `withDefaults()` not found | Running Spring Security 6.x | Use the 6.x constructor; use the builder only on 7.0+ |
| `setExpressionHandler(...)` deprecated | Running on 7.x | Switch to builder `withExpressionHandler` or `withDefaults` as appropriate |
| Expression calling `@bean` fails | Missing bean resolver or wrong bean name | Check handler and Spring bean context; prefer calling bean directly in a manager |
| Cannot reuse legacy handler | `FilterInvocation` differs from `RequestAuthorizationContext` | Use `DefaultHttpSecurityExpressionHandler` for WebExpressionAuthorizationManager |
| User with `ROLE_ADMIN` gets 403 | Different converter, hierarchy, or prefix | Inspect `Authentication.getAuthorities()` and active role hierarchy |
| Under-privileged user gets through | `and` turned into `or`, broad matcher, or `authenticated()` fallback | Add negative tests per missing permission; check matcher order |
| `#name` does not resolve | Matcher does not extract URI template variables | Use the appropriate matcher and test real paths |
| Controller test passes yet cross-tenant access occurs | Only URL-level authority checked | Add resource-binding policy/service/query |
| 403 when rendering error/view | Authorization runs on secondary dispatch | Check dispatcher types; do not broaden arbitrarily |
| Same URL sometimes returns 200, sometimes 403 | Multiple filter chains/role hierarchy/different dispatches | Log selected chain, first matching rule, and principal |
| Tests only pass for admin | Missing denial, anonymous, or other HTTP method cases | Matrix test covering allow/deny and side effects |

A safe migrated configuration does not merely "start up." It must prove each route admits the **same set of permitted requests** per contract, or has explicitly reviewed security policy changes.

## 10. Before–After Test Matrix for Multi-Condition Rules

Suppose the original rule is:

~~~text
GET /reports/**:
    hasRole('ADMIN') and hasAuthority('report:read')
Other routes:
    denyAll
~~~

Create at minimum these actors:

| Actor/Authority | `ROLE_ADMIN` | `report:read` | GET `/reports/2026` | Reason |
| --- | --- | --- | --- | --- |
| Alice | Yes | Yes | ALLOW | Satisfies both permissions |
| Bob | Yes | No | DENY | Admin does not imply `report:read` |
| Carol | No | Yes | DENY | Permission alone is insufficient for the role |
| Dave | No | No | DENY | Missing both |
| Anonymous | No | No | DENY/401 per API | No accepted authentication |
| Alice on `/admin/**` | Yes | Yes | DENY | Does not match `/reports/**` |
| Alice doing POST on same path | Yes | Yes | Depends on method-constrained matcher | Document old and new contracts explicitly |

For a GET-only policy, add `.requestMatchers(HttpMethod.GET, "/reports/**")`. Test that `POST` is denied by `anyRequest().denyAll()`. If the legacy policy applied to all HTTP methods, do not restrict to GET-only without a business decision.

For an expression using `@reportPolicy.canRead(authentication, request)`, in addition to role/authority combinations, include cases for **same role but document belonging to another tenant**, revoked user permissions, nonexistent resources, internal policy service failure, and matchers receiving encoded URIs. Negative cases must assert both the response **and** absence of side effects.

## 11. Standalone Java 17: Verifying the AND/OR Preservation Matrix

This snippet illustrates locking expected decisions before altering rules. It **does not execute real Spring Security, SpEL, or HTTP matchers**, so it is solely an exercise in boolean semantics. Real configuration preservation must be verified using `MockMvc` in the next section.

Save as `PolicyMatrixDemo.java` and run:

~~~bash
javac PolicyMatrixDemo.java
java PolicyMatrixDemo
~~~

Java 17+ code:

~~~java
import java.util.List;
import java.util.Set;

public class PolicyMatrixDemo {
    record Actor(String name, Set<String> authorities) {}

    static boolean hasRole(Actor actor, String role) {
        return actor != null &&
            actor.authorities().contains("ROLE_" + role);
    }

    static boolean hasAuthority(Actor actor, String authority) {
        return actor != null &&
            actor.authorities().contains(authority);
    }

    static boolean legacyAnd(Actor actor) {
        return hasRole(actor, "ADMIN")
            && hasAuthority(actor, "report:read");
    }

    static boolean migratedAnd(Actor actor) {
        boolean admin = hasRole(actor, "ADMIN");
        boolean canRead = hasAuthority(actor, "report:read");
        return admin && canRead;
    }

    static boolean accidentalOr(Actor actor) {
        return hasRole(actor, "ADMIN")
            || hasAuthority(actor, "report:read");
    }

    public static void main(String[] args) {
        List<Actor> actors = List.of(
            new Actor("Alice", Set.of("ROLE_ADMIN", "report:read")),
            new Actor("Bob", Set.of("ROLE_ADMIN")),
            new Actor("Carol", Set.of("report:read")),
            new Actor("Dave", Set.of())
        );

        int agreements = 0;
        for (Actor actor : actors) {
            boolean expected = legacyAnd(actor);
            boolean actual = migratedAnd(actor);
            if (expected != actual) {
                throw new AssertionError("Mismatch for " + actor.name());
            }
            agreements++;
        }

        System.out.println("matched=" + agreements);
        System.out.println("Alice=" + migratedAnd(actors.get(0)));
        System.out.println("Bob=" + migratedAnd(actors.get(1)));
        System.out.println("Carol=" + migratedAnd(actors.get(2)));
        System.out.println("Dave=" + migratedAnd(actors.get(3)));
        System.out.println("OR-regression-Bob=" + accidentalOr(actors.get(1)));
    }
}
~~~

Exact stdout:

~~~text
matched=4
Alice=true
Bob=false
Carol=false
Dave=false
OR-regression-Bob=true
~~~

`OR-regression-Bob=true` demonstrates how a seemingly small change from AND to OR lets Bob in despite lacking `report:read`. Apply this matrix mindset to real security tests: capture expected decisions before rewriting, then confirm every case still holds. Do not treat this standalone program as proof that real Spring Security preserved the expression.

## 12. Spring Security Integration Tests: Verifying the Real Wiring

### 12.1. MockMvc must test DSL + filter chain + expression

Example **Spring Boot + Spring Security Test test skeleton**, assuming the app has a `GET /reports/2026` endpoint returning 200, a `SecurityFilterChain` bean applying the rule from Section 4, and `MockMvc` wired with security filters:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MigratedExpressionAuthorizationTest {
    @Autowired MockMvc mvc;

    @Test
    void adminWithReadAuthorityCanAccess() throws Exception {
        mvc.perform(get("/reports/2026")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ROLE_ADMIN"),
                    new SimpleGrantedAuthority("report:read"))))
            .andExpect(status().isOk());
    }

    @Test
    void adminWithoutReadAuthorityIsDenied() throws Exception {
        mvc.perform(get("/reports/2026")
                .with(user("bob").authorities(
                    new SimpleGrantedAuthority("ROLE_ADMIN"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithoutAdminRoleIsDenied() throws Exception {
        mvc.perform(get("/reports/2026")
                .with(user("carol").authorities(
                    new SimpleGrantedAuthority("report:read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Required static imports: `MockMvcRequestBuilders.get`; `SecurityMockMvcRequestPostProcessors.user`; `MockMvcResultMatchers.status`; JUnit Jupiter `@Test`; Spring Boot Test `@SpringBootTest` and `@AutoConfigureMockMvc`; and Spring Security `SimpleGrantedAuthority`. This is not a standalone Java class because it relies on a controller and real Spring context.

Do not habitually configure `@WithMockUser(roles={"ADMIN"}, authorities={"report:read"})`: `roles` and `authorities` should not be mixed that way; use `user(...).authorities(...)` to explicitly declare **all** expected authorities. Real HTTP status tests require a valid route/controller, otherwise a `404` from a missing route could be mistaken for an authorization denial.

### 12.2. Adding tests for path variables and beans

If a rule uses `#name == authentication.name`, test:

- Alice GET `/profiles/alice` → allow.
- Alice GET `/profiles/bob` → deny.
- Alice GET `/profiles/%61lice` → outcome per your app's matcher/encoding, never guess from raw strings.
- Add a negative case when the context lacks the expected variable.

If a rule uses `@reportPolicy.canView(...)`, use the real policy bean or a test double recording invocations (never unconditionally mock an allow result). Confirm the bean is called, resource ID and tenant are passed accurately, the policy denies mismatched owners, and policy errors do not degrade into `permitAll`.

### 12.3. Testing real authentication and security context

MockMvc `user(...)` tests requests with a synthetic `Authentication`; it verifies authorization logic once a principal exists, and **does not** verify JWT signatures, issuers, audiences, claim mapping, or real login filters. If the app uses an OAuth2 resource server, add tests with the appropriate decoder/token to prove real authorities. When adding CSRF rules or POST/PATCH/DELETE, supply a valid CSRF token when the goal is testing authorization, and keep separate CSRF tests.

### 12.4. Testing framework variants affecting semantics

- Run one suite on the old version and one after migrating, using the exact same case matrix and expected decisions.
- Overlapping matchers like `/reports/**` vs. `/reports/public/**`, multiple filter chains, and error/forward dispatches.
- Role hierarchy, custom prefixes, principal types, anonymous, remember-me, JWT scopes, bean policies, and evaluators if used.
- Cases for "both conditions true," "only one true," "neither true," unknown paths, wrong HTTP methods, and query/tenant tampering.
- For data access, verify both repository state and responses; a correct URL-level decision does not guarantee correct ownership checks.

## 13. Safe Step-by-Step Migration Checklist

1. **Inventory** all expressions from `authorizeRequests`, `access(String)`, XML `intercept-url`, and custom handlers. Record matchers, HTTP methods, servlet paths, filter chains, expressions, policy beans, role hierarchies, and expected allow/deny outcomes.
2. **Lock down the baseline** with matrix tests for sensitive routes before changing APIs. Include error dispatches, anonymous callers, exception mapping, and out-of-tenant data.
3. **Migrate the DSL** to `authorizeHttpRequests` and version-appropriate `requestMatchers`; preserve exact rule ordering, method restrictions, and fail-closed defaults.
4. **Preserve SpEL intentionally** using `new WebExpressionAuthorizationManager(expression)` on 6.x/7.x. Do not use `withDefaults()`/`Builder` in 6.x. On 7.x, consider the builder if it brings real benefits.
5. **Re-wire custom expression handlers** using the new API: role hierarchies, permission evaluators, bean resolvers, trust resolvers, and path-variable support. Do not copy handlers built for `FilterInvocation` verbatim.
6. **Simplify after tests pass**: replace pure `hasRole`/`hasAuthority` expressions with type-safe DSL calls; move complex business bean policies into dedicated managers. Re-run equivalence tests after every change.
7. **Run real HTTP tests** covering authentication, CSRF, request matchers, dispatches, and object-level authorization; verify denials produce zero side effects.
8. **Review policy changes** if you intend to tighten access, switch default `authenticated` to `denyAll`, alter matchers, or drop a role hierarchy. Those are intentional changes requiring new acceptance criteria, not lumped into a "behavior-preserving migration."
9. **Deploy with observability**: safely track 401/403 rates by route and role, audit authorization decisions, and never log access tokens/PII. Maintain a config rollback plan per your deployment workflow.

### Quick QA checklist before sign-off

- [ ] New `SecurityFilterChain` selects the right requests; the first matching rule has equivalent semantics.
- [ ] Each legacy SpEL rule migrated accurately to `WebExpressionAuthorizationManager` or an explicit manager; no accidental `and`/`or` swaps.
- [ ] Version-accurate config: constructor on 6.x/7.x, builder on 7.0+, no deprecated setters used without clear justification.
- [ ] `hasRole`/`hasAuthority`, prefixes, role hierarchy, and JWT converter match real `Authentication`s.
- [ ] Bean references, custom `PermissionEvaluator`s, and URI variables are wired properly.
- [ ] Methods/servlet paths/dispatcher types are accurate; static resources and error handlers operate under control.
- [ ] Anonymous, remember-me, missing scopes, missing roles, wrong methods, and unknown URLs all behave per contract.
- [ ] CSRF/401/403 behavior does not mask expression evaluation results.
- [ ] Requests targeting out-of-tenant/other-owner objects are denied even if the user holds URL-level authorities.
- [ ] No SpEL expression originates from client-supplied strings; parse errors or missing beans never open access.
- [ ] Before–after matrix tests yield equivalent results or explicitly reviewed policy changes.

**Conclusion:** `WebExpressionAuthorizationManager` is a reliable bridge to **evaluate legacy web SpEL within the new `AuthorizationManager` model**, yet migration quality rests on actual access decisions. Use the constructor on 6.x, consider the builder on 7.0+, preserve permissions/matchers/bean contexts, and replace complex expressions with type-safe managers once tests prove behavior.

### Official Documentation

- [Spring Security 6.5 — Authorize HttpServletRequests, Migrating Expressions](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): new DSL and expression migration for 6.x.
- [Spring Security 6.5 — WebExpressionAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/expression/WebExpressionAuthorizationManager.html): constructor, `setExpressionHandler`, `check`.
- [Spring Security 7.0 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html): managers, matching, builder, and bean policies.
- [Spring Security 7.0 — WebExpressionAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/access/expression/WebExpressionAuthorizationManager.html): `withDefaults`/`withExpressionHandler`, deprecated setter, 7.x API.
- [Spring Security 7 — What’s New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): AuthorizationManager changes and legacy API removals.
- [Spring Security — Testing Authorization](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authorization.html): using MockMvc to verify request permissions accurately.
