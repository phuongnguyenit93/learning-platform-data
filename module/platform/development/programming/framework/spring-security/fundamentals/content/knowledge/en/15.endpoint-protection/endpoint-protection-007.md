# Chain-Selection Conditions Do Not Replace Rules Inside the Chain

## 1. The Problem: "Selecting a Chain" and "Allowing a Request" Are Two Different Decisions

In Spring Security Servlet, each `SecurityFilterChain` contains a group of security filters applied to matching HTTP requests. When multiple chains exist, Spring Security must decide **which request enters which chain** before the filters inside that chain handle authentication and authorization.

Two important questions must be answered **in order**:

1. **Chain selection:** Which `SecurityFilterChain` applies to this request? This is the responsibility of `FilterChainProxy` along with the chain-level matcher, typically configured via `http.securityMatcher(...)`.
2. **Permission check inside the selected chain:** Is the request allowed to access the endpoint? This is the responsibility of `http.authorizeHttpRequests(...)` with `requestMatchers(...)`, `authenticated()`, `hasAuthority(...)`, `permitAll()`, `denyAll()`, etc.

**Statement to remember:** `securityMatcher("/api/**")` means **"this chain is selected for requests within `/api/**`"**, **not** "anyone is allowed to access all of `/api/**`" or "every request under `/api/**` requires login." A chain-selection condition does not create authorization rules on its own.

Visualize it as:

~~~text
HTTP request
    |
    v
FilterChainProxy: evaluates SecurityFilterChains in priority order
    |
    |-- Does not match current chain --> try next chain
    |
    |-- Matches a chain ---------------> run only that chain's filters
                                           |
                                           v
                               Authentication / SecurityContext
                                           |
                                           v
                               AuthorizationFilter (when configured)
                                           |
                                           v
                               authorizeHttpRequests:
                                 requestMatchers(...) / anyRequest()
                                           |
                                   ALLOW or DENY
    |
    |-- Matches no chain at all -------> not protected by
                                         Spring Security filter chains
~~~

Note: if a request matched a chain yet **was denied inside that chain**, `FilterChainProxy` **does not retry** the next chain to look for a more permissive rule. Only when the **chain-selection condition does not match** is a later chain evaluated. A normal request is processed by the **first matching chain**, not a combination of permissions across all chains.

## 2. Distinguishing Three Matcher Levels

| Configuration | Role | Actual scope | Common mistake |
| --- | --- | --- | --- |
| `http.securityMatcher("/api/**")` | Selects the scope for an `HttpSecurity`/`SecurityFilterChain` | Only requests matching `/api/**` can be handled by this chain | Thinking merely declaring the selector already requires login |
| `http.authorizeHttpRequests(a -> a.requestMatchers("/api/admin/**").hasRole("ADMIN"))` | Defines endpoint access rules | Evaluated **only after the request has entered that chain** | Thinking the rule can "pull" requests outside the selector scope into the chain |
| `authorize.anyRequest().denyAll()` | Final rule for requests not matching specific rules | All **remaining requests inside the currently selected chain** | Thinking the API chain's `anyRequest()` protects the entire application |

Example with a chain having `securityMatcher("/api/**")`:

- `GET /api/reports/7`: can enter that chain. Internal rules decide allow or deny.
- `GET /api/users/5`: can also enter that chain; if there is no specific rule, the **API chain's** `anyRequest()` decides.
- `GET /admin/settings`: does not enter the API chain. A `requestMatchers("/admin/**")` placed *inside the API chain* cannot apply to this request.
- `GET /health`: does not enter the API chain; must be handled by another chain if you want Spring Security to protect/govern access.

Do not confuse `requestMatchers` inside `authorizeHttpRequests` with `securityMatchers`/`securityMatcher` at the `HttpSecurity` level: both APIs contain the word "matcher," yet they sit at **two different steps in the request flow**.

## 3. Execution Mechanism of Multiple `SecurityFilterChain`s

Each `SecurityFilterChain` bean has its own `RequestMatcher` to determine whether it applies to a request. `FilterChainProxy` iterates through the list of chains in order, selecting the **first** chain whose matcher returns true.

Typically:

- `@Order(1)` takes precedence over `@Order(2)`.
- A bean without `@Order` normally sits after higher-priority beans.
- Configuring `securityMatcher(...)` replaces the chain's default selector (which by default matches every request).
- A chain without `securityMatcher(...)` usually acts as a **catch-all/fallback**.
- Once selected, only that chain's filters run; filters and separate rules configured on other chains are not "merged in."
- If no chain matches, the request is not subject to the protection of Spring Security filter chains. The application may still have other protection mechanisms, but you should not rely on them implicitly.

Two-chain example:

~~~text
Chain A: @Order(1), securityMatcher("/api/**")
Chain B: no securityMatcher (fallback for all remaining requests)

GET /api/reports/7  -> Chain A (even though Chain B could also match)
GET /health         -> Chain B
GET /unknown        -> Chain B
~~~

**Chain selection order** is completely different from **rule selection order inside a chain**:

- `FilterChainProxy`: first matching chain in `SecurityFilterChain` order.
- `authorizeHttpRequests`: first matching rule in `requestMatchers(...)`/`anyRequest()` order inside the **selected chain**.

These two layers may both inspect HTTP paths, yet they serve two different purposes. Each layer needs separate testing.

## 4. Proper Servlet Spring Security Configuration Example with Fallback

The following example targets a Spring Boot application using Spring Web (Servlet) and Spring Security with Java 17+. This is an **integrated configuration class inside a Spring project**, not a standalone Java program run directly with `javac`. Endpoints and authorities are solely examples of design.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class EndpointSecurityConfiguration {

    // First chain: applies only to paths starting with /api/.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("report:write")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Fallback chain: evaluated when the API chain does not match.
    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/health").permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Reading accurately step by step:

**A. Selecting the chain with `securityMatcher`.** For `GET /api/reports/42`, `FilterChainProxy` selects `apiChain` because the path matches `/api/**`. The fallback is not used for this request. For `GET /health`, the API chain does not match, so the fallback is evaluated.

**B. Authorization inside `apiChain`.** `GET /api/reports/42` requires the exact authority `report:read`. `POST /api/reports/42` requires `report:write`. Another request such as `DELETE /api/reports/42` or `GET /api/unknown` does not match the first two rules, hits `anyRequest().denyAll()`, and is denied.

**C. Authorization inside `fallbackChain`.** Only `GET /health` gets `permitAll()`; remaining requests not claimed by the API chain hit `denyAll()`. They **do not "loop back" to the API chain**.

**D. Filters and other security mechanisms.** The example configures HTTP Basic for the API, yet a POST request can still be subject to **CSRF protection** under default settings; holding `report:write` does not mean every POST is guaranteed to succeed. A stateless token API application needs authentication, session management, and CSRF configured to match its real client model rather than disabling CSRF just so an example returns 200.

**E. Real application configuration.** You must add valid routes, an authentication provider/JWT/session, required security chains, and business-object permissions. `hasAuthority("report:read")` only checks read capability by authority; reading report ID 42 may also require matching tenant/owner in a service or repository. Do not use a single authority to skip per-resource data checks.

### 4.1. Why Does `anyRequest().denyAll()` in the API Chain Make Sense?

In the example above, the `/api/**` selector states that *these requests use the API filter set*. The final `denyAll()` rule states that *any kind of API endpoint without an explicitly declared permission is denied*. These are two complementary policies.

If `denyAll()` is replaced with `authenticated()`, remaining API URLs **are allowed at the HTTP authorization layer** for any authenticated user, unless a specific rule blocks them. Sometimes that is a valid requirement; in sensitive APIs, proactively inventory routes opened by this fallback.

If `authorizeHttpRequests` is omitted altogether, only the selector and other filters remain configured; **the selector by itself is not a rule requiring authentication or authorization**. Therefore, review both chain selection and authorization configuration thoroughly.

## 5. Prediction Table for the Configuration's Results

The table below describes the **HTTP-layer authorization decision** for the example. The final outcome of a real request also depends on authentication, CSRF, whether the endpoint exists, and business checks.

| Request | Principal/authority | Selected chain | Internal rule | Authorization decision |
| --- | --- | --- | --- | --- |
| `GET /api/reports/7` | Logged in, has `report:read` | `apiChain` | GET reports → `hasAuthority("report:read")` | **ALLOW** |
| `GET /api/reports/7` | Logged in, lacks `report:read` | `apiChain` | GET reports | **DENY** |
| `POST /api/reports/7` | Only has `report:read` | `apiChain` | POST reports → `hasAuthority("report:write")` | **DENY** |
| `POST /api/reports/7` | Has `report:write` | `apiChain` | POST reports | **ALLOW** at authorization step; other filters may block |
| `DELETE /api/reports/7` | Has both read/write | `apiChain` | `anyRequest().denyAll()` | **DENY** |
| `GET /api/unknown` | Has `report:read` | `apiChain` | `anyRequest().denyAll()` | **DENY** |
| `GET /health` | Not logged in | `fallbackChain` | `permitAll()` | **ALLOW** |
| `GET /profile` | Logged in, has all API authorities | `fallbackChain` | `denyAll()` | **DENY** |
| `POST /health` | Not logged in | `fallbackChain` | `denyAll()` (does not match GET) | **DENY** |

**Important:** `DENY` in the table is the outcome at the rule, not tied by default to a fixed HTTP status code. For endpoints requiring authentication, missing authentication usually leads to an entry point (e.g., HTTP Basic returns 401), while authenticated but missing authority usually yields 403. If CSRF fails, the result can also be 403 even with the right authority. A `permitAll()` rule does not disable CSRF, other filters, or controller validation.

## 6. Two Ordering Bugs to Distinguish

### 6.1. Ordering Bug **Between Chains**

Suppose an application wants a stronger mechanism for `/api/admin/**` but writes:

~~~java
@Bean
@Order(1)
SecurityFilterChain broadApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    // General API filters and rules...
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/admin/**");
    // Stricter admin filters and rules...
    return http.build();
}
~~~

This is an **illustration of an ordering bug**, not a complete configuration. The request `GET /api/admin/users` matches `/api/**` in the first chain, so the second `adminApi` chain **is never selected** for that request. There is no automatic mechanism to "escalate" to the admin chain when the first chain's rules fail.

**Fix:** give the specialized `/api/admin/**` chain higher priority, such as `@Order(1)`, place the general `/api/**` chain at `@Order(2)`, and put a catch-all last. Each chain must still declare authorization inside.

### 6.2. Ordering Bug **Between Internal Rules**

The snippet below is wrong because the general rule precedes the specific rule:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
    );
~~~

This is an **anti-pattern example**, not a recommended configuration. The `/api/**` rule already matches `/api/admin/users` before `hasRole("ADMIN")` is evaluated, keeping the specialized rule from taking effect as intended. Some versions/configurations may warn or reject unreachable rules after an overly broad matcher; regardless, general-before-specific ordering is a design error.

**Fix:** place `requestMatchers("/api/admin/**").hasRole("ADMIN")` before the general matcher; end with `anyRequest().denyAll()` or an appropriate permission fallback. Ordering between *chains* and ordering between *rules* are both critical and **cannot substitute for each other**.

## 7. Configurations Easy to Misinterpret

### Case A — Selecting Only a Chain Without Defining Permissions

~~~java
http.securityMatcher("/api/**")
    .httpBasic(Customizer.withDefaults());
~~~

This snippet only states that HTTP Basic is an authentication mechanism in the API chain; it **does not automatically define** that every API request requires a principal, role, or authority. Other security filters in the chain may still operate, so do not interpret this as "turning off all security"; yet do not treat it as having protected endpoints with authorization rules.

Declare permissions intentionally, for example:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

This requires login for requests inside the API chain; if the API requires per-operation authorities, replace with appropriate `requestMatchers(...).hasAuthority(...)` rules before the final rule.

### Case B — Internal Rule Outside the Selector's Scope

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().permitAll()
    );
~~~

`/admin/**` sits outside `/api/**`, so this admin rule **is never evaluated for `/admin/**`** in the chain above. `anyRequest().permitAll()` applies only to requests **that entered the API chain**, permitting all remaining API endpoints at the HTTP authorization layer. Without a fallback chain, `/admin/**` may not be protected by any Spring Security filter chain at all.

Solution: adjust the selector to cover the required scope, or place the admin rule in a chain with the appropriate selector; add a catch-all and test every route. Do not "patch" by adding rules to the wrong chain.

### Case C — A Scoped Chain While Forgetting a Fallback

~~~java
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );
    return http.build();
}
~~~

If this is the application's **only chain**, `/api/**` is governed, while requests like `/admin`, `/actuator/health`, and `/files` are not selected by this chain. When **no other chain matches**, Spring Security filter chains do not protect those requests. Having `anyRequest().authenticated()` inside `onlyApi` does not change the `/api/**` scope.

A common solution is to add a **fallback chain without `securityMatcher`**, explicitly govern genuinely public endpoints that must be open, and use `denyAll` or `authenticated` for the rest per system policy.

### Case D — Treating `permitAll` and Bypassing Spring Security as the Same

`permitAll()` is a decision at the **authorization** step of the selected chain. Other filters can still execute (headers, CSRF, security context...). Conversely, a request matching no chain does not go through `FilterChainProxy` security filters at all. Nor should it be confused with `web.ignoring()`, which bypasses the security filter layer for matching requests and has different consequences for headers/observability. When opening a public endpoint, usually prefer `permitAll()` inside the appropriate chain.

## 8. Special Note: Filters That Provide Endpoints Themselves

Some Spring Security filters directly handle endpoints like login/logout. For example, `formLogin()` can provide `POST /login`; if a chain selects only `/secured/**`, then `/login` does not match that chain. The result may be **404** because the login-processing filter does not run for paths outside the selector.

~~~text
Chain accepts only /secured/** and has formLogin()
POST /login          -> does not match this chain
POST /secured/login  -> works only if login URLs were customized accordingly
~~~

Depending on context, configure `loginPage("/secured/login")` and `loginProcessingUrl("/secured/login")`, or place login in another chain with an appropriate matcher. Similarly, check exact paths for logout, OAuth2 authorization/callbacks, token endpoints, or filter-provided authentication mechanisms.

**Lesson:** adjusting `securityMatcher` can push filter-provided endpoints **outside the chain's scope**, even when `authorizeHttpRequests` rules look reasonable. Testing login/logout/callbacks is a separate task, not just testing REST controllers.

## 9. Runnable Java 17 Simulation: Select Chain First, Select Rule Second

The plain Java example below simulates the **two-layer principle** with two chains and ordered rules. This is a **teaching model**; it does not simulate full `FilterChainProxy`, real request matchers, authentication mechanisms, CSRF, or HTTP status codes.

Create file **`ChainSelectionDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class ChainSelectionDemo {
    record Request(String method, String path, boolean authenticated,
                   Set<String> authorities) {}
    record Rule(String name, Predicate<Request> pathMatches,
                Predicate<Request> allow) {}
    record Chain(String name, Predicate<Request> selector, List<Rule> rules) {}

    static String decide(Request request, List<Chain> chains) {
        for (Chain chain : chains) {
            if (!chain.selector().test(request)) continue;
            for (Rule rule : chain.rules()) {
                if (rule.pathMatches().test(request)) {
                    return chain.name() + " / " + rule.name() + " -> "
                            + (rule.allow().test(request) ? "ALLOW" : "DENY");
                }
            }
            return chain.name() + " / no authorization rule";
        }
        return "NO CHAIN MATCHED";
    }

    public static void main(String[] args) {
        Predicate<Request> isReport = r -> r.path().startsWith("/api/reports/");
        List<Chain> chains = List.of(
            new Chain("api", r -> r.path().startsWith("/api/"), List.of(
                new Rule("GET report:read",
                    r -> r.method().equals("GET") && isReport.test(r),
                    r -> r.authorities().contains("report:read")),
                new Rule("POST report:write",
                    r -> r.method().equals("POST") && isReport.test(r),
                    r -> r.authorities().contains("report:write")),
                new Rule("api denyAll", r -> true, r -> false)
            )),
            new Chain("fallback", r -> true, List.of(
                new Rule("health permitAll", r -> r.path().equals("/health"),
                    r -> true),
                new Rule("fallback denyAll", r -> true, r -> false)
            ))
        );
        System.out.println(decide(new Request("GET", "/api/reports/7", true,
            Set.of("report:read")), chains));
        System.out.println(decide(new Request("GET", "/api/reports/7", true,
            Set.of()), chains));
        System.out.println(decide(new Request("POST", "/api/reports/7", true,
            Set.of("report:read")), chains));
        System.out.println(decide(new Request("POST", "/api/reports/7", true,
            Set.of("report:write")), chains));
        System.out.println(decide(new Request("GET", "/api/unknown", true,
            Set.of("report:read")), chains));
        System.out.println(decide(new Request("GET", "/health", false,
            Set.of()), chains));
        System.out.println(decide(new Request("GET", "/profile", true,
            Set.of("report:read")), chains));
    }
}
~~~

Compile and run with JDK 17 or later in the directory containing the file:

~~~bash
javac --release 17 ChainSelectionDemo.java
java ChainSelectionDemo
~~~

**Exact stdout (verified):**

~~~text
api / GET report:read -> ALLOW
api / GET report:read -> DENY
api / POST report:write -> DENY
api / POST report:write -> ALLOW
api / api denyAll -> DENY
fallback / health permitAll -> ALLOW
fallback / fallback denyAll -> DENY
~~~

What to observe:

1. The first four requests all use the `api` chain, yet produce different outcomes due to authorities and HTTP methods.
2. `GET /api/unknown` still selects the `api` chain; because it matches no report rule, it hits `api denyAll`. **It does not fall back to fallback**.
3. `GET /health` does not match the `api` selector, so it selects `fallback` and is opened by `health permitAll`.
4. `GET /profile` also selects fallback, but hits `fallback denyAll`.
5. The predicates in the demo use simple `startsWith`; real-world Spring Security uses `RequestMatcher` and context-dependent path matching rules. Do not use this simulation snippet as a production security engine.

If you delete the fallback chain in the model, requests outside `/api/**` return `NO CHAIN MATCHED`. That is what to watch out for when configuring a scope-limiting `securityMatcher` in Spring Security.

## 10. How to Test to Prove Selectors Do Not Replace Rules

With Spring MVC, typically use `MockMvc` with `spring-security-test` and the real security filter chain for testing. Do not test only a single authorized user; verify **both `(chain, rule)` pairs** and denial cases.

### 10.1. Core Test Matrix

| Test | Entry path | Simulated authority | Expected |
| --- | --- | --- | --- |
| API chain selected properly | GET `/api/reports/7` | `report:read` | Passes API chain HTTP authorization |
| API rule blocks missing permission | GET `/api/reports/7` | Authenticated user without `report:read` | Denied |
| Method distinction | POST `/api/reports/7` | Only `report:read` | Denied |
| POST rule | POST `/api/reports/7` | `report:write` | Passes authorization; test CSRF/side effects separately |
| No API rule | DELETE `/api/reports/7` | User with read/write | Blocked by `denyAll` |
| Public fallback | GET `/health` | Anonymous | Passes `permitAll` |
| Fallback deny | GET `/profile` | Authenticated user | Blocked by `denyAll` |
| Out-of-scope selector | GET `/admin` | Admin | Not selected by API chain; fallback decides |
| Specific vs. general path | GET `/api/admin/users` | Regular user | Only the ordered matching chain decides; does not "drop" to later chain |
| Filter endpoint | POST login/callback | Per auth flow | Only the filter chain actually matching that path handles it |
| Scope without fallback | GET `/unknown` | Anonymous | Detects requests protected by no chain |

Prepare sample controllers/routes and an appropriate user store/test principal. For POST/PUT/DELETE requests, add a CSRF token in tests **if the configuration enables CSRF**, to distinguish CSRF failures from authorization failures. With HTTP Basic authentication, use the test request helper or real header if testing that mechanism.

### 10.2. Assertions to Include

- Verify which chain a route enters, especially with multiple `@Order` values and nested selectors.
- Verify a matching rule in the first chain **does not fall through to the second chain** when permissions fail.
- Test non-existent resources, resources owned by another tenant/owner, and undeclared HTTP methods. URL rules cannot replace business checks.
- Verify no side effects occur when a request is denied: database rows are not updated, events are not emitted, responses do not leak data.
- Verify filter-created endpoints: login, logout, OAuth2 callbacks; avoid testing only controllers.
- Verify intentionally public routes like health/static still pass through the appropriate chain and get `permitAll`, rather than accidentally matching no chain.
- When changing a selector, run regression tests for all primary and fallback routes; when changing rules, test boundaries between role permissions.

A test showing only HTTP 200 or 403 is **not enough** to know the real reason: 403 may come from CSRF or method policy; 200 may occur because the endpoint accidentally fell outside Spring Security. Combine response assertions, chain-selection logs, and authority-swapping tests.

## 11. Debugging When Requests Hit the Wrong Chain or Right Chain with Wrong Permissions

Follow this order:

1. **Confirm the actual path and method** arriving at the server. Check context path, servlet path, reverse proxy rewrites, API version prefixes, and HTTP method. Wrong path assumptions break matcher alignment.
2. **List `SecurityFilterChain` beans in `@Order` sequence** and each chain's actual selector. Identify the first chain matching the request. Do not guess from bean names alone.
3. **Inspect configuration inside the selected chain**: whether `authorizeHttpRequests` is declared, `requestMatchers` order, `anyRequest` fallback, `hasRole` vs. `hasAuthority`, and where `permitAll`/`denyAll` are attached.
4. **Check principal and authorities** after authentication: `hasRole("ADMIN")` looks for `ROLE_ADMIN` by default; `hasAuthority("report:read")` matches the exact string `report:read`.
5. **Classify the denial source**: missing authentication, missing authority, CSRF, method security, business policy, or missing controller; each source has a different fix.
6. **Enable safe logging in development** when needed, e.g., `logging.level.org.springframework.security=DEBUG`; `FilterChainProxy` and authorization filter messages help trace execution. Do not enable sensitive logging or log tokens/passwords in production.
7. **Re-run the test matrix** after modifying selectors or rules; specifically test requests matching two nested selectors, requests outside all selectors, and authentication callback endpoints.

Use integration tests to observe requests through the real filter chain. Do not mock `AuthorizationManager` directly and conclude chain ordering is correct: unit testing permission decisions **does not replace** chain-selection testing.

## 12. Common Misconceptions and Fixes

| Misconception | Why it is wrong | Fix |
| --- | --- | --- |
| "Having `securityMatcher("/api/**")` means the API already requires login" | The selector only picks the chain | Declare `authorizeHttpRequests` explicitly with `authenticated`/authorities/deny |
| "`requestMatchers("/admin/**")` inside the API chain will protect `/admin/**`" | `/admin/**` is outside the chain's selector | Put the rule in the right chain or change the selector intentionally |
| "`anyRequest().denyAll()` in the API chain protects every route" | `anyRequest` only evaluates requests that entered the API chain | Add a fallback chain for other requests |
| "If denied in the first chain, Spring tries the next chain" | Next chain is tried **only when the selector does not match** | Fix the rule in the selected chain; do not rely on fallthrough |
| "An `/api/admin/**` chain ordered after `/api/**` still protects admin" | The broad chain catches the request first | Place specific selectors first |
| "Putting `/api/**` rule before `/api/admin/**` rule is fine" | Broad rule catches requests first | Place detailed rules first and fallback last |
| "`permitAll` completely skips security filters" | It is only an authorization grant rule | Let requests pass through the chain when headers/CSRF/context are needed |
| "Having `httpBasic` or `formLogin` implies URL authorization is right" | Authentication and authorization are two responsibilities | Explicitly specify authorization policy for each scope |
| "Passing the URL rule means any record can be read" | URL permissions are insufficient for ownership/tenant checks | Use per-resource domain/method/repository policies |
| "POST with the right authority getting 403 means the matcher is wrong" | It may be CSRF or another rule | Inspect security flow and test with valid CSRF |
| "Requests outside every chain are protected by default" | Without a fallback, no chain matches | Configure a policy-compliant catch-all chain and test |

## 13. Checklist for Reviewing a Multi-Chain Configuration

- [ ] Each `SecurityFilterChain` has a clearly described selector scope and proper priority order.
- [ ] A fallback chain protects requests not claimed by specialized chains.
- [ ] Nested selectors are ordered from specific to general.
- [ ] Every chain has `authorizeHttpRequests` or an intentionally designed and verified authorization mechanism.
- [ ] Internal rules target only requests that can enter their chain.
- [ ] Rules go from specific to general, ending with an appropriate `anyRequest`.
- [ ] Undeclared routes are not accidentally granted access.
- [ ] `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, and `denyAll` are clearly distinguished.
- [ ] Filter-provided login/logout/callback paths fall inside the right chain.
- [ ] CSRF, sessions, HTTP Basic/JWT, and filter sets are reviewed per chain.
- [ ] Tests prove changing selectors cannot bypass rules and changing rules does not drop endpoints outside all chains.
- [ ] Business-level record checks exist wherever URL-only checks are insufficient.

### Self-Check Questions

**Question 1.** A chain has `securityMatcher("/api/**")` and `authorizeHttpRequests(auth -> auth.anyRequest().authenticated())`. Is a `GET /admin` request blocked by this `authenticated()` rule?

**Answer:** No. `/admin` does not enter the `/api/**` chain, so that chain's `anyRequest()` is never evaluated. The outcome depends on other chains; if no chain matches, the request is not protected by Spring Security filter chains.

**Question 2.** There are two chains: `@Order(1) /api/**` and `@Order(2) /api/admin/**`. Which chain does `/api/admin/users` select?

**Answer:** The `/api/**` chain at `@Order(1)` matches first, so it is selected. The admin chain behind it is not used. Fix by placing the admin selector first.

**Question 3.** With `securityMatcher("/api/**")`, is adding `requestMatchers("/api/reports/**").hasAuthority("report:read")` enough to protect the rest of the API endpoints?

**Answer:** Not yet conclusive. You must inspect the chain's **final rule**: `anyRequest().denyAll()` blocks other endpoints; `authenticated()` opens them to all logged-in users; lacking an authorization policy can let unintended behavior slip through.

**Key message:** `securityMatcher` routes requests to **which security filter set** runs; `requestMatchers` and `anyRequest` inside `authorizeHttpRequests` decide **what permissions requests in that chain need**. Protect both the **chain-selection scope** and the **in-chain authorization rules**, and always provide a fallback for requests not claimed by specialized chains.

### Official Reference Documentation

- Spring Security — Java Configuration, Multiple HttpSecurity Instances and Choosing securityMatcher or requestMatchers: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Authorize HttpServletRequests, Security Matchers: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Architecture / Security Filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
