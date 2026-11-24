# authorizeRequests vs. authorizeHttpRequests and Execution Mechanism Changes

## 1. Overview and Learning Objectives

In Servlet-based Spring Security, `authorizeRequests` and `authorizeHttpRequests` both configure **HTTP access permissions** by path, HTTP method, and Authentication. The two DSLs share many superficially similar rules, yet **differ in execution mechanism**. Simply renaming a method is not enough to prove a safe migration.

This lesson explains the shift from `FilterSecurityInterceptor`, `AccessDecisionManager`, and `AccessDecisionVoter` to `AuthorizationFilter` and `AuthorizationManager`, clarifying changes in when Authentication is retrieved, rule ordering, and servlet dispatches. Examples focus on **Servlet** Spring Security, especially migrating Spring Security 5.x code to 6.x/7.x. WebFlux uses `ServerHttpSecurity.authorizeExchange` and `SecurityWebFilterChain`, and does not use the code below as-is.

By the end of this lesson, you will be able to:
- Distinguish the authorization enforcement components in the old and new configurations.
- Migrate `antMatchers`/`authorizeRequests` to `requestMatchers`/`authorizeHttpRequests` appropriate for your version.
- Understand first-match wins, `hasRole`/`hasAuthority`, `securityMatcher`, and multiple filter chains.
- Explain deferred Authentication lookup and how `AuthorizationFilter` checks each servlet dispatch.
- Migrate SpEL expressions and custom voters to the new API without inadvertently altering ALLOW/DENY decisions.
- Write security regression tests to verify behavior instead of merely trusting that the code compiles.

## 2. Comparing the Two Configuration Approaches

| Topic | `authorizeRequests` (legacy) | `authorizeHttpRequests` (new) |
|---|---|---|
| DSL | `HttpSecurity.authorizeRequests(...)` | `HttpSecurity.authorizeHttpRequests(...)` |
| Authorization filter | `FilterSecurityInterceptor` | `AuthorizationFilter` |
| Decision making | Metadata source + `ConfigAttribute` + `AccessDecisionManager` + `AccessDecisionVoter` | `AuthorizationManager` and request matchers |
| Authentication | Legacy interceptor mechanism typically needed to look up Authentication during decision processing | `Supplier<Authentication>`, retrieved only when a rule requires it |
| URL rules | `antMatchers`/`mvcMatchers` in 5.x versions | `requestMatchers`/`dispatcherTypeMatchers`, matcher semantics depend on version |
| Customization | Expression handler, voter, decision manager | `AuthorizationManager<RequestAuthorizationContext>`, bean-created managers, expression manager |
| Servlet dispatch | Behavior tied to `FilterSecurityInterceptor` and once-per-request configuration | `AuthorizationFilter` enforces authorization on dispatches handled by the filter chain |
| Version trend | Deprecated/legacy API | Standard choice for new Spring Security 6/7 configurations |

**Key point:** when using `authorizeHttpRequests`, Spring Security selects `AuthorizationFilter` instead of `FilterSecurityInterceptor` for that request authorization branch. This differs from merely changing DSL method names. Custom policies implemented via legacy voters/decision managers do **not automatically** become an `AuthorizationManager`.

### 2.1. Old flow

~~~text
HTTP request
  -> FilterChainProxy selects SecurityFilterChain
  -> security-context and authentication filters
  -> FilterSecurityInterceptor
       -> SecurityMetadataSource retrieves ConfigAttributes
       -> AccessDecisionManager aggregates voter results
       -> allow / deny decision
  -> DispatcherServlet if ALLOW
~~~

In this model, `AccessDecisionManager` could use strategies such as affirmative, consensus, or unanimous. An `AccessDecisionVoter` could return GRANT/DENY/ABSTAIN. How the manager combined decisions matters greatly during migration: replacing a set of voters with an arbitrary OR/AND easily alters policy.

### 2.2. New flow

~~~text
HTTP request / servlet dispatch
  -> FilterChainProxy selects SecurityFilterChain
  -> security-context / authentication filters
  -> ExceptionTranslationFilter
  -> AuthorizationFilter
       -> prepares Supplier<Authentication>
       -> AuthorizationManager receives request + supplier
       -> applies the first matching rule in DSL order
       -> ALLOW: continues filter chain
       -> DENY: throws AccessDeniedException
  -> DispatcherServlet if ALLOW
~~~

Spring Security documentation describes `AuthorizationFilter` as sitting near the end of the security filter chain by default. Authentication and other protective filters execute beforehand; `AuthorizationFilter` itself is responsible for **HTTP authorization decisions**, not creating new users, verifying JWT signatures, or implementing authentication providers.

If denied, `ExceptionTranslationFilter` handles `AccessDeniedException` using the configured `AuthenticationEntryPoint` or `AccessDeniedHandler`. Therefore, 401/403/302 responses depend on the login mechanism and client state: HTTP Basic or Bearer APIs usually return **401** when unauthenticated and **403** when authenticated but lacking permission; form login may redirect, and CSRF can cause a 403 independently of URL rules.

## 3. Deferred Authentication: Why Can permitAll Be Faster?

`AuthorizationManager` receives Authentication as a `Supplier<Authentication>`. When the rule is `permitAll` or `denyAll`, the manager already has a fixed result and **does not need to access the Authentication supplier** for that authorization decision. If the rule is `authenticated`, `hasRole`, `hasAuthority`, or a custom user-dependent policy, the manager then invokes the supplier.

~~~text
GET /public/help
  -> matches permitAll
  -> ALLOW without retrieving Authentication for authorization

GET /admin/report
  -> matches hasRole("ADMIN")
  -> supplier.get() to retrieve Authentication
  -> checks GrantedAuthority
  -> ALLOW or DENY
~~~

The benefit is avoiding unnecessary Authentication/session loading on certain public requests. However, `permitAll` **does not exclude the URL from the filter chain**: a custom authentication filter may still process headers/tokens before authorization; an invalid token can still be rejected by the authentication layer. Conversely, `web.ignoring()` removes the request completely from the Spring Security filter chain and may omit security headers as well. For static resources, Spring Security documentation prefers `permitAll` over `ignoring` unless there is a specific reason.

Do not interpret "deferred Authentication" as "skipping authentication" or "auto-caching permissions": a custom manager can still trigger DB/network queries if it loads data during evaluation.

## 4. Legacy Configuration: Spring Security 5.7 Illustration

Example in the historical style of Spring Security 5.7 (code **only for a 5.x baseline**; `antMatchers` was removed from the standard DSL in 6.x):

~~~java
@Configuration
@EnableWebSecurity
class LegacySecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeRequests(auth -> auth
                .antMatchers("/public/**", "/actuator/health").permitAll()
                .antMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyRole("ANALYST", "ADMIN")
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Rules: public and health are permitted without requiring a role; GET reports require ANALYST/ADMIN; /admin requires ADMIN; everything else requires login. `hasRole("ADMIN")` compares against authority `ROLE_ADMIN` by default, whereas `hasAuthority("ADMIN")` requires the exact string `ADMIN`. This is the easiest way to introduce policy bugs when migrating between role-based and authority-based code.

The snippet above is a configuration class inside an application with Spring Security dependencies and corresponding imports; it cannot be run with a standalone JDK `java` command.

## 5. New Configuration: Spring Security 6.x

The following class illustrates the migrated version on Java 17+ with necessary imports. It can be placed into a Spring Boot 3.x application with Spring Security; actual routes and Authentication data sources must be configured in the project.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyRole("ANALYST", "ADMIN")
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Minimal changes include `authorizeRequests` → `authorizeHttpRequests` and `antMatchers` → `requestMatchers` according to the target API version. This is an **equivalent target in policy intent**, yet still requires testing URL matching/dispatchers/chain selection. Do not add `csrf().disable()` just to make a demo run easily: browser/session applications need CSRF, while stateless APIs require a dedicated assessment of token mechanisms and threat models.

Do not casually switch `.anyRequest().authenticated()` to `permitAll()`, or switch all endpoints to ADMIN just to make tests pass; such changes require explicit business approval.

### 5.1. Version 7.x and legacy Access API

Per the Spring Security 7 migration guide, legacy Access API components such as `AccessDecisionManager` and `AccessDecisionVoter` were moved to the optional `spring-security-access` module. Projects still directly using legacy APIs may need to declare:

~~~groovy
dependencies {
    implementation("org.springframework.security:spring-security-access")
}
~~~

This is a compatibility path during dependency upgrades, **not** a way to turn `authorizeRequests` into a recommended API for new code. Once migrated to `AuthorizationManager`, there is no need to add the legacy module just because the application has HTTP authorization. Consult documentation for the exact running version/BOM because matcher behavior and APIs continue evolving across 6.x/7.x.

## 6. First-Match Wins and Rule-Ordering Vulnerabilities

`authorizeHttpRequests` evaluates rules in **declaration order**. The first matching rule decides; the framework does not automatically look for a "most specific" path rule further down.

**Correct:**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

**Wrong and dangerous:**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").authenticated()
    .requestMatchers("/admin/**").hasRole("ADMIN")
)
~~~

In the wrong version, a request to `/admin/report` matches `/**` first, rendering the ADMIN rule ineffective; any regular logged-in user is allowed. `requestMatchers("/**")` is used here as an ordering bug example; many DSL versions also reject configuring rules after `anyRequest()` at build time.

| Request | Principal | Correct Rule | Wrong Rule |
|---|---|---|---|
| GET /public/help | Anonymous | ALLOW | Requires authentication |
| GET /admin/report | ROLE_USER | DENY | ALLOW — security flaw |
| GET /admin/report | ROLE_ADMIN | ALLOW | ALLOW |
| GET /profile | ROLE_USER | ALLOW | ALLOW |

Place specific matchers first and fallbacks last; `anyRequest().denyAll()` suits an "undeclared routes are blocked" policy, whereas `authenticated()` suits systems where logged-in users may access remaining URLs. This is a policy choice, not a mandatory one-sided default.

### 6.1. HTTP method ordering

Example:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyRole("ANALYST", "ADMIN")
.requestMatchers("/api/reports/**")
    .hasRole("ADMIN")
.anyRequest().authenticated()
~~~

GET reports allow ANALYST/ADMIN, while POST/PATCH/DELETE match the second rule requiring ADMIN. Do not assume a GET rule automatically covers POST. For CORS, configure preflight `OPTIONS` properly per your architecture; do not resolve preflight errors by opening `permitAll("/**")`.

## 7. AuthorizationFilter Checks Multiple Servlet Dispatches

A critical migration point is that `AuthorizationFilter` evaluates **every dispatch** handled by the Spring Security filter chain, including `REQUEST`, `FORWARD`, `ERROR`, and `INCLUDE`. One HTTP request can produce multiple dispatches:

~~~text
GET /report          REQUEST -> authorization -> Controller
    forward /view    FORWARD -> authorization -> View rendering

GET /fails           REQUEST -> authorization -> Controller throws
    dispatch /error  ERROR   -> authorization -> Error rendering
~~~

If rules block `/error` or a view path during FORWARD, migration can trigger unexpected 403s, masking the original error. Depending on your MVC architecture and threat model, consider permitting the necessary dispatcher types:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
            DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

This is a fragment inside a Servlet 6.x configuration, not a standalone class. **Do not blindly add permitAll for every dispatch.** `dispatcherTypeMatchers(ERROR, FORWARD).permitAll()` is scoped by **dispatch type**, which is broader than a single URL; if the application exposes sensitive content during secondary dispatches, define a specific policy and test it separately. Also check actual dispatcher mapping/filter registration: a rule cannot protect a dispatch excluded from the filter chain.

`permitAll` for ERROR/FORWARD does not mean opening the original public URL; the initial REQUEST must still pass its own policy when entering the security chain properly.

## 8. securityMatcher, requestMatchers, and Multiple Filter Chains

Three easily confused concepts:
- `http.securityMatcher("/api/**")`: **Does this SecurityFilterChain apply** to the request?
- `authorizeHttpRequests(...).requestMatchers("/api/admin/**")`: **Does the rule inside the selected chain** match the request?
- `anyRequest()`: fallback for requests **belonging to the current chain**; it does not protect URLs outside the chain's scope.

With multiple `SecurityFilterChain`s, Spring Security selects the **first matching chain** in priority order. If no chain matches, the request may go unprotected by Spring Security; therefore, include a fallback chain when the system must protect all URLs.

Example (two methods in a configuration class, with relevant Spring imports):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
    return http.build();
}
~~~

The `denyAll` fallback pattern actively blocks undeclared URLs; it is unsuitable as-is for applications with public pages outside `/api`. In real applications, configure login/CSRF/session/CORS per chain; multiple `HttpSecurity` configurations can produce differences in security context and entry points.

### 8.1. Version-dependent path matchers

Do not assume 5.x `antMatchers` and 6/7 `requestMatchers(String)` share identical path-matching mechanics. Matcher behavior can depend on version, classpath, Spring MVC/servlet mappings, and matcher builders. Newer Spring Security releases support matchers backed by `PathPatternRequestMatcher`. At minimum, test:
- `/admin`, `/admin/`, `/admin/a`, and nested paths.
- URLs with path variables, custom servlet paths, or context paths.
- HTTP methods GET/POST/OPTIONS/HEAD.
- Encoded/normalized paths within what the server/proxy permits.
- Multiple servlets, especially when MVC and another servlet coexist in one application.

Do not treat "similar-looking" URL strings as proof of zero regressions.

## 9. Expressions and Custom AccessDecisionVoters

### 9.1. Migrating SpEL when needed

Legacy configurations might use expressions combining roles and authorities:

~~~java
// Spring Security 5.x illustration
.antMatchers("/finance/**")
    .access("hasRole('FINANCE') and hasAuthority('reports:read')")
~~~

In the new DSL, `WebExpressionAuthorizationManager` can be used:

~~~java
.requestMatchers("/finance/**")
    .access(new WebExpressionAuthorizationManager(
            "hasRole('FINANCE') and hasAuthority('reports:read')"))
~~~

This is a fragment inside a Spring configuration with appropriate imports, not a standalone runnable file. When expressions are complex or depend on beans, consider migrating to a type-safe `AuthorizationManager<RequestAuthorizationContext>` for easier testing and reuse. Notably, **legacy custom expression handlers/bean resolvers are not necessarily wired automatically** when switching DSLs.

### 9.2. Do not map custom voters by name

Before migrating a voter, answer:
1. Does it check a role, IP, header, tenant, owner, or business policy?
2. Under what circumstances does it return GRANT/DENY/ABSTAIN?
3. How did the old decision manager combine multiple voters?
4. Is there any dependency on order, Authentication, or repository data?
5. How must the new manager decide ALLOW/DENY to be strictly equivalent?

Turning "one voter GRANT suffices" into "all conditions must be true" will over-block; conversely, OR-ing every condition can unintentionally open access. Write an authorization matrix of the old logic **before editing**. The new manager must fail closed when data, membership, tenant, or policy lookups fail.

Request authorization does not automatically replace **object-level authorization**. For instance, an ADMIN of tenant B is not allowed to read tenant A's documents merely because `/api/admin/**` passed. Owner, membership, tenant, and object-action checks in the service/domain layer remain mandatory.

## 10. Standalone Java 17: First-Match and Deferred Lookup

The following program simulates **the first-match rule principle** and `Supplier<Principal>`; it **does not use Spring Security internals**, does not start a server, and does not emulate servlet filters. This example is handy for checking logic before writing MockMvc tests.

~~~java
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class AuthorizationDslMigrationDemo {
    record Principal(Set<String> authorities) {}
    record Request(String method, String path) {}
    record Rule(Predicate<Request> matches,
                Predicate<Supplier<Principal>> permits) {}

    static boolean hasRole(Supplier<Principal> supplier, String role) {
        Principal principal = supplier.get();
        return principal != null
                && principal.authorities().contains("ROLE_" + role);
    }

    static boolean authorize(Request request, Supplier<Principal> supplier,
                             List<Rule> rules) {
        for (Rule rule : rules) {
            if (rule.matches().test(request)) {
                return rule.permits().test(supplier);
            }
        }
        return false;
    }

    static void check(String label, Request request, Principal principal,
                      List<Rule> rules, boolean expected, int expectedReads) {
        AtomicInteger reads = new AtomicInteger();
        Supplier<Principal> supplier = () -> {
            reads.incrementAndGet();
            return principal;
        };
        boolean actual = authorize(request, supplier, rules);
        if (actual != expected || reads.get() != expectedReads) {
            throw new AssertionError(label + ": actual=" + actual
                    + ", reads=" + reads.get());
        }
        System.out.println(label + ": " + (actual ? "ALLOW" : "DENY")
                + ", authenticationReads=" + reads.get());
    }

    public static void main(String[] args) {
        Rule publicPages = new Rule(
                r -> r.path().startsWith("/public/"), supplier -> true);
        Rule internal = new Rule(
                r -> r.path().startsWith("/internal/"), supplier -> false);
        Rule admin = new Rule(
                r -> r.path().startsWith("/admin/"),
                supplier -> hasRole(supplier, "ADMIN"));
        Rule authenticated = new Rule(
                r -> true, supplier -> supplier.get() != null);
        List<Rule> correctOrder = List.of(
                publicPages, internal, admin, authenticated);
        Principal user = new Principal(Set.of("ROLE_USER"));
        Principal administrator = new Principal(Set.of("ROLE_ADMIN"));

        check("public", new Request("GET", "/public/info"),
                null, correctOrder, true, 0);
        check("internal", new Request("GET", "/internal/status"),
                user, correctOrder, false, 0);
        check("admin denied", new Request("GET", "/admin/reports"),
                user, correctOrder, false, 1);
        check("member", new Request("GET", "/profile"),
                user, correctOrder, true, 1);
        check("admin allowed", new Request("GET", "/admin/reports"),
                administrator, correctOrder, true, 1);
        check("wrong ordering", new Request("GET", "/admin/reports"),
                user, List.of(authenticated, admin), true, 1);
    }
}
~~~

Save to `AuthorizationDslMigrationDemo.java` and run with JDK 17 or later:

~~~bash
javac --release 17 AuthorizationDslMigrationDemo.java
java AuthorizationDslMigrationDemo
~~~

Exact stdout (actually compiled with `javac --release 17` and executed successfully):

~~~text
public: ALLOW, authenticationReads=0
internal: DENY, authenticationReads=0
admin denied: DENY, authenticationReads=1
member: ALLOW, authenticationReads=1
admin allowed: ALLOW, authenticationReads=1
wrong ordering: ALLOW, authenticationReads=1
~~~

`public` and `internal` decide without invoking the supplier; `admin denied`/`admin allowed` check `ROLE_` permissions after obtaining the principal. `wrong ordering` intentionally places the authenticated fallback at the start of the list, resulting in a **wrong ALLOW** on `/admin/reports` for `ROLE_USER`. This is a scenario that must be caught in regression tests.

In production, Authentication has multiple states (anonymous, remember-me, authenticated), JWTs, and filter chains that differ from this Java SE model. The simulation code does not replace security integration tests.

## 11. HTTP Testing to Prove a Safe Migration

Use Spring Security test + MockMvc or equivalent integration tests to verify **actual results** on existing endpoints. The following example is a **fragment inside a test class** that already has `MockMvc mvc`, imports, and corresponding controller mappings:

~~~java
@Test
void publicEndpointIsOpen() throws Exception {
    mvc.perform(get("/public/help"))
       .andExpect(status().isOk());
}

@Test
void userCannotAccessAdmin() throws Exception {
    mvc.perform(get("/admin/reports").with(user("alice").roles("USER")))
       .andExpect(status().isForbidden());
}

@Test
void adminCanAccessAdmin() throws Exception {
    mvc.perform(get("/admin/reports").with(user("operator").roles("ADMIN")))
       .andExpect(status().isOk());
}

@Test
void anonymousMustAuthenticateForProfile() throws Exception {
    mvc.perform(get("/profile"))
       .andExpect(status().isUnauthorized()); // assumes HTTP Basic API
}
~~~

A 200 test depends on a real controller existing and returning success; if the route does not exist, you may get 404 even when the filter allows it through. Testing 401 fits entry points like HTTP Basic/Bearer; form login usually redirects with 302. For POST/PUT/DELETE in CSRF-enabled apps, tests need a valid CSRF token to separate CsrfFilter rejections from authorization rejections.

### 11.1. Critical regression matrix

| Scenario | Expected |
|---|---|
| Anonymous GET public URL | ALLOW |
| Anonymous GET protected URL | Authentication entry point |
| ROLE_USER GET /admin/reports | DENY |
| ROLE_ADMIN GET /admin/reports | ALLOW |
| ROLE_ANALYST GET /api/reports/1 | ALLOW if matching the GET rule |
| ROLE_ANALYST POST /api/reports/1 | Per POST rule; do not infer from GET |
| User with literal authority ADMIN but missing ROLE_ADMIN | DENY with `hasRole("ADMIN")` |
| /admin and /admin/ | Per verified URL matcher contract |
| FORWARD to view | Not unexpectedly DENIED, or DENIED if that is the policy |
| ERROR dispatch after exception | Returns original error per contract, does not turn into 403 |
| Multiple chains: /api/** and /web/** | Selects the right chain and does not miss requests |
| URL outside all chains | Protected by the defined fallback |
| Custom voter/manager | ALLOW/DENY results equivalent to the previous version |
| ADMIN of tenant B accesses tenant A document | DENY at object/service layer |
| Rejected POST | No database side effects; also verify CSRF |

When a test encounters 403, inspect the cause: AuthorizationFilter, `CsrfFilter`, method security, or a business exception. Do not rely on status 403 alone as definitive proof that a role policy works properly.

### 11.2. Operational metrics to compare

On the same request dataset, measure the count of DENIED requests, SecurityContext/Authentication loads on public URLs, repeated requests on ERROR/FORWARD, latency, and queries triggered by custom managers. Deferred Authentication does not guarantee every custom manager saves I/O. If a custom policy queries the database per request/tenant, check indexes, cache invalidation, and service-layer permissions.

## 12. Common Mistakes and Fixes

- **Renaming methods only:** ignoring the `FilterSecurityInterceptor` → `AuthorizationFilter` shift. Inspect the actual filter chain, custom voters, and dispatcher types.
- **Forgetting to remove or migrate custom voters:** policies protecting tenant/IP disappear. Migrate them to `AuthorizationManager` or use a controlled legacy path.
- **Broad rule placed before narrow rule:** `/**` authenticated before `/admin/**` lets regular users into admin. Place specific rules first and test negative cases.
- **Confusing `securityMatcher` with `requestMatchers`:** assuming `anyRequest` inside the `/api` chain also protects `/web`. Add a fallback chain if needed.
- **Thinking `permitAll` skips filters:** it only skips the permission check at authorization; an authentication filter can still reject invalid input.
- **Using `web.ignoring` for all static assets:** bypasses security headers/other filters; consider `permitAll`.
- **Seeing `/error` 403 and opening `/**`:** examine ERROR dispatch and define an appropriate policy instead of making every URL public.
- **Wrong role prefix:** `hasRole("ADMIN")` checks `ROLE_ADMIN` by default, while `hasAuthority("ADMIN")` checks `ADMIN`.
- **Not testing methods/servlet paths:** matcher semantics can differ across versions; test boundaries, HTTP verbs, and multi-servlet setups.
- **Equating HTTP authorization with object permissions:** passing `/api/**` is insufficient to read another tenant's resource.
- **Fixing CSRF 403s by disabling CSRF globally:** separate CSRF and authorization tests, and decide based on auth architecture.
- **Using 5.x APIs in a 6.x project or dropping legacy modules when moving to 7.x:** verify versions/BOM and perform real replacements; do not mix snippets across majors.

## 13. Practical Migration Workflow

1. **Inventory:** record Spring Security/Boot versions, `SecurityFilterChain`s, role prefixes, authentication entry points, custom voters/expressions, filter ordering, and servlet/dispatcher mappings.
2. **Establish baseline:** build a matrix of URL + HTTP method + principal + expected decision/status, covering public/admin/error/view/tenant and denial scenarios.
3. **Minimal migration:** switch the DSL to `authorizeHttpRequests`/`requestMatchers`, preserving policy intent, order, and fallback; upgrade APIs to match the exact version.
4. **Handle special cases:** migrate custom voters to `AuthorizationManager`; check SpEL managers, `dispatcherTypeMatchers`, `securityMatcher`, URL matchers, and custom filters.
5. **Regression:** run integration tests for 401/403/302, dispatches, CSRF, path/method boundaries, multiple chains, object/tenant policies, and side effects.
6. **Observe:** enable safe logging/metrics to identify which chain matched, why a request was DENIED, Authentication load counts, and latency impact.
7. **Remove legacy:** once all tests pass and policies are equivalent, remove unused legacy dependencies/beans; on Spring Security 7 with no legacy Access APIs left, `spring-security-access` is unnecessary.

## 14. Official Documentation

- Spring Security 6.5 — Authorize HTTP Servlet Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorize HTTP Servlet Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Java Configuration / SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Servlet Authorization Migration 7.x: https://docs.spring.io/spring-security/reference/migration/servlet/authorization.html
- Spring Blog — Access API Moves to Spring Security Access: https://spring.io/blog/2025/09/09/access-api-moves-to-spring-security-access/

**Remember:** `authorizeHttpRequests` brings an execution model based on `AuthorizationFilter` and `AuthorizationManager`, which can defer Authentication lookup while also evaluating multiple servlet dispatches. A proper migration must verify **unchanged authorization semantics** across requests, chains, methods, tenants, and resources—especially DENY cases.