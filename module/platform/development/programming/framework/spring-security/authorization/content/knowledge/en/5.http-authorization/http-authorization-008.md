# Multiple SecurityFilterChains, @Order, and the Risk of Unmatched Requests

> **Module:** Spring Security – authorization  
> **Group:** HTTP Authorization  
> **Focus:** `FilterChainProxy` selecting **one** `SecurityFilterChain` by `RequestMatcher` and `@Order`; differences between `securityMatcher` and `requestMatchers`; consequences when a request matches no chain; fallback configuration and test suites preventing URL gaps.

## 1. The problem to recognize immediately

A Java application has three groups of endpoints:

- `/api/**`: customer APIs, using HTTP Basic or Bearer token.
- `/admin/**`: administrative APIs, requiring `ROLE_ADMIN`.
- `/public/**`: public content; plus `/actuator/**`, `/error`, and less-noticed URLs.

The development team configures:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"));
    return http.build();
}
~~~

At a glance it looks like there is "authorization for API" and "authorization for admin." However, **a `GET /public/status` request matches neither chain**. If the application has a controller serving data at that path, it can execute **without passing through the security filters of a Spring Security `SecurityFilterChain`**.

This is not `denyAll()` or `authenticated()` behavior. It is a **filter chain coverage gap**: HTTP authorization rules are never evaluated at all because the request is never handed to a matching chain.

Core principle of this article:

**Multiple `SecurityFilterChain`s do not automatically form a mesh protecting all URLs. You must prove every important request matches the right chain and provide a fallback chain covering all remaining requests.**

## 2. Three selection layers commonly conflated

To understand and debug a request, separate three questions:

| Layer | Who decides? | Question | Example |
|---|---|---|---|
| **Chain selection** | `FilterChainProxy` based on `SecurityFilterChain.matches(request)` | Which chain handles the request? | `/api/orders` belongs to API chain |
| **Rule selection in chain** | `AuthorizationManager` configured by `authorizeHttpRequests` | Inside the selected chain, which URL/method rule matches first? | `GET /api/reports/**` needs `reports:read` |
| **Filter & business execution** | Filters in the chain + controller/service | How are authentication, CSRF, authorization, method policy, and owner/tenant handled? | User lacking permission gets denied |

Visualization:

~~~text
HTTP request
     |
     v
DelegatingFilterProxy / springSecurityFilterChain
     |
     v
FilterChainProxy
     |
     +--> Chain @Order(1): securityMatcher("/api/**") ?
     |             |
     |        matches --> SELECT API chain; STOP chain selection
     |
     +--> Chain @Order(2): securityMatcher("/admin/**") ?
     |             |
     |        matches --> SELECT ADMIN chain; STOP chain selection
     |
     +--> Chain @Order(99): default matcher (all requests)?
                   |
              matches --> SELECT FALLBACK chain; STOP chain selection
                                 |
                                 v
                    Filters of the selected chain
                                 |
                                 v
                    authorizeHttpRequests rules
                                 |
                                 v
                         Controller/service
~~~

Only the **first matching chain** executes. Spring Security **does not concatenate filters from chain A and chain B**, does not take the last rule of chain A and continue to chain B's rules, and does not apply two security configurations to the same request.

If there is no fallback and neither A nor B matches, `FilterChainProxy` has no matching `SecurityFilterChain` to apply to that request. Other application filters, reverse proxies, or other protections may still exist, yet **that must not be treated as automatic Spring Security authorization**.

## 3. What is `SecurityFilterChain`?

Each `SecurityFilterChain` defines two things:

1. **A chain-level `RequestMatcher`**: which requests fall within the chain's scope?
2. **A list of security filters** to run when the chain is selected: e.g., filters for security context, authentication, CSRF, exception translation, and authorization; exact details depend on configuration.

Chains can differ in login mechanism, session management, CSRF, CORS, authentication entry point, exception handling, URL policies, and custom filters.

Architectural example:

~~~text
Chain A: /api/**
    JWT authentication (if configured)
    API-oriented CSRF strategy
    AuthorizationFilter: token scopes / API permissions

Chain B: /admin/**
    HTTP Basic or form login
    Admin-oriented CSRF strategy
    AuthorizationFilter: ROLE_ADMIN

Chain C: all remaining requests
    Public endpoints permitted with permitAll
    Unrecognized URLs: denyAll
~~~

**There is no step "if chain A lets it pass, chain B checks further."** The selected chain is its own protective boundary. This is both a benefit (separating authentication mechanisms by area) and a risk (missing chains, wrong ordering, or a broad chain shadowing a narrow chain).

## 4. How are `securityMatcher` and `requestMatchers` different?

This is the single most important distinction during code review:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

- `http.securityMatcher("/api/**")`: **chain-level entry gate**. Requests outside `/api/**` do not enter this chain; internal rules **never get a chance to run**.
- `authorizeHttpRequests(...).requestMatchers("/api/public/**")`: **rule inside the chain**. The rule only applies if the request has already matched the chain.
- `anyRequest().authenticated()`: catches **remaining requests inside the selected chain**, and does not automatically protect the whole application.

Comparison:

| Configuration | Scope | Purpose |
|---|---|---|
| `http.securityMatcher("/api/**")` | Entire chain | Selects the filter set and policy dedicated to `/api/**` |
| `http.authorizeHttpRequests(...requestMatchers("/api/admin/**"))` | Rule inside chain | Selects permission condition for requests matching URL/method |
| `anyRequest().denyAll()` inside API chain | Remainder **of the API chain** | Denies APIs not matching specific rules |
| Chain without `securityMatcher` | Matches all requests by default | Suitable as a final fallback |

**Common trap:** putting `anyRequest().denyAll()` inside a chain with `securityMatcher("/api/**")` and assuming every non-API URL will be denied. In reality, `/debug/config` never enters the API chain; an internal API fallback cannot block it.

### 4.1. Chain scope and rule scope must align

The following example contains a rule **that will never be used**:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

`/admin/**` lies outside `/api/**`, so the ADMIN role rule does not protect `/admin/**`. It does not cause `securityMatcher`'s scope to expand automatically.

Place the admin rule in a chain that can receive `/admin/**` requests, or deliberately widen the chain-level matcher and re-check ordering, rather than merely adding `requestMatchers` inside.

### 4.2. What does "not calling `securityMatcher`" mean?

By default, `HttpSecurity` creates a chain whose matcher covers all requests. Calling `securityMatcher(...)` replaces that default scope with your chosen scope. Thus a `SecurityFilterChain` bean **without `securityMatcher`** is the standard choice for a catch-all. Do not interpret "no matcher declared = the chain matches nothing."

## 5. `@Order` is the priority order between chains

Spring Security evaluates multiple chains in **priority order**; `@Order` on chain beans specifies that order. Lower order numbers have higher priority:

~~~java
@Bean
@Order(1)
SecurityFilterChain highPriority(HttpSecurity http) throws Exception {
    // ...
}

@Bean
@Order(2)
SecurityFilterChain lowerPriority(HttpSecurity http) throws Exception {
    // ...
}
~~~

If a request matches both, `@Order(1)` is selected; `@Order(2)` is **not invoked afterward**.

Example:

~~~text
@Order(1)  securityMatcher("/api/admin/**")
@Order(2)  securityMatcher("/api/**")
@Order(99) no securityMatcher (catch-all)

GET /api/admin/users --> chain 1
GET /api/orders      --> chain 2
GET /about           --> chain 99
~~~

### 5.1. Wrong order creates functional vulnerabilities

~~~java
// WRONG when /api/admin/** must require the ADMIN role.
@Bean
@Order(1)
SecurityFilterChain broadApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"));
    return http.build();
}
~~~

`GET /api/admin/users` matches chain 1 first → rule only requires login. **Chain 2 does not run even though it has `hasRole("ADMIN")`.** This is a case of **vertical privilege escalation** due to misordered chain priority.

Fix by placing narrow, sensitive chains first:

~~~text
@Order(1) /api/admin/**  --> hasRole("ADMIN")
@Order(2) /api/**        --> regular API rules
@Order(99) all other URLs --> public allowlist, remaining denyAll
~~~

### 5.2. A catch-all placed too early can also shadow every chain

~~~java
// WRONG: this chain matches everything before the admin chain.
@Bean
@Order(1)
SecurityFilterChain earlyFallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().permitAll());
    return http.build();
}
~~~

If there is an `@Order(2)` admin chain, the admin chain may never be used because the fallback claims every request at order 1.

**Conclusion:** "having a fallback" is not enough; **the fallback must be evaluated after** specialized chains. A trailing fallback with `denyAll` acts as a safety net for undeclared URLs; a leading fallback with `permitAll` can nullify the entire design.

### 5.3. Do not rely on accidental ordering

Do not rely on method declaration order in a file or Spring class-scanning order to infer priority. When multiple chains have overlapping matchers, declare `@Order` explicitly, avoid duplicate priorities, and write integration tests proving the intended chain is selected.

A chain without `@Order` is normally evaluated after beans with assigned priority. Even so, **putting an explicit `@Order(99)`** on the fallback can make the design easier to review if all prior chains are controlled. When starters/libraries contribute configs, inspect the actual beans as well.

## 6. The biggest risk: requests matching no chain at all

Consider the configuration:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain admin(HttpSecurity http) throws Exception {
    http.securityMatcher("/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"));
    return http.build();
}
~~~

Analysis:

| Request | Matching chain | Consequence |
|---|---|---|
| `GET /api/orders` | API | HTTP authorization requires login |
| `GET /admin/users` | ADMIN | HTTP authorization requires `ROLE_ADMIN` |
| `GET /public/news` | **None** | Not protected by an appropriate Spring Security `SecurityFilterChain` |
| `GET /actuator/env` | **None** | Very dangerous if the endpoint is exposed and lacks other protection |
| `POST /internal/recalculate` | **None** | Can reach controller without any security rule running |
| `GET /error` | **None** | Error-handling behavior may differ from expectations |

**Important point:** "no chain" does **not** necessarily return 200; the route might not exist and return 404, a reverse proxy might block it, or a custom servlet filter might guard it. Yet if a controller genuinely exists with no other protection, the endpoint can be reached without Spring Security permissions.

When no chain applies, protections belonging to a Spring Security filter chain—such as authentication, HTTP authorization, CSRF, and security headers set by that chain—are not applied in the usual way. This is a **coverage gap** and cannot be fixed simply by changing `hasRole` inside existing chains.

### 6.1. Why `anyRequest().denyAll()` inside the API chain cannot save you

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().denyAll());
~~~

`GET /admin/users` never matches `/api/**`, so it never enters the API chain's `AuthorizationFilter`. `anyRequest` only has meaning **after** a chain has been selected.

To cover the entire application, you need a chain matching the remaining URLs, typically **a fallback without `securityMatcher`**.

### 6.2. Do not confuse with `web.ignoring()`

`web.ignoring()` actively bypasses security filtering for the selected matcher; `permitAll()` **keeps the request flowing through the security chain** while requiring no authority at the HTTP rule.

- **No chain matches**: likely an unintended configuration gap.
- **`web.ignoring()`**: deliberately excludes a URL from Spring Security filters; requires risk assessment.
- **`permitAll()`**: public at the authorization rule level, still inside the chain.

For most static/public resources, Spring Security documentation recommends preferring `permitAll` over excluding them from the security chain so protections like security headers and appropriate filters remain active.

## 7. Three-chain configuration pattern with safe fallback

This is a **Spring Boot 3.x / Spring Security 6.x Servlet-stack integration sample**, not a standalone JDK Java program. It requires Spring Web and Spring Security dependencies, user/authentication provider configuration, and real controllers.

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
public class MultiChainSecurityConfig {

    // Chain 1: regular APIs.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Chain 2: administrative area.
    @Bean
    @Order(2)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Chain 3: no securityMatcher => matches every request
    // not claimed by the two preceding chains.
    @Bean
    @Order(99)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**")
                    .permitAll()
                .anyRequest().denyAll()
        );

        return http.build();
    }
}
~~~

### Part-by-part analysis

- **API chain** claims only `/api/**`. GET report endpoints need the exact `report:read` authority; public GET APIs need no login at the HTTP rule; other APIs within `/api/**` require authentication. For greater safety, other sensitive APIs should require dedicated permissions rather than `authenticated()` alone.
- **ADMIN chain** claims only `/admin/**`, requiring `ROLE_ADMIN` under the default `hasRole("ADMIN")` convention. Having the ADMIN role does not automatically prove permission on specific resources.
- **FALLBACK chain** declares no `securityMatcher`, so by default it receives all remaining URLs; permits GET `/public/**`, and denies everything else with `denyAll()`.
- **Ordering** `@Order(1)`, `@Order(2)`, `@Order(99)` ensures the fallback does not shadow API/admin.
- **No coverage gap** at the `SecurityFilterChain` level when all three beans are properly registered. Still, test in practice: other library chains, multiple servlet contexts, or path rewriting may exist.
- **Each chain has its own filter set**. They do not automatically inherit authentication configuration from another chain. The fallback chain contains only what is configured/defaulted on that chain; it does not automatically get HTTP Basic because the first two chains declared it.

**Important:** this example illustrates rule placement for a known architecture, not a copy-paste config for every project. HTTP Basic requires HTTPS, a trusted credential provider, and properly encoded passwords. Apps using Bearer JWTs should configure `oauth2ResourceServer().jwt()` on the right chain, verify issuer/audience/scopes, and manage sessions/CSRF per client type. Never disable CSRF globally just to "make an example run."

### 7.1. `@Order(99)` is not an "absolute last priority"

If another chain bean has `@Order(100)`, it will be shadowed by the fallback first; thus no new bean should sit after the catch-all. Ordering is an **application-wide contract** that must be governed whenever modules are added.

In small projects, a fallback **without `@Order`** is typically evaluated by Spring Security after chains with explicit orders. Either way, have tests guarding against a new chain getting shadowed.

## 8. Routing table: where is each URL protected?

With the three-chain config above, assuming typical path matchers and corresponding methods:

| Request | Winning chain | HTTP rule inside chain | Notes |
|---|---|---|---|
| `GET /api/public/faq` | API | `permitAll` | Still passes through API chain filters |
| `GET /api/reports/2026` | API | `hasAuthority("report:read")` | Does not replace report data-level checks |
| `POST /api/reports` | API | `authenticated` | Does not match GET-specific rule; review if write permission is needed |
| `GET /admin/users` | ADMIN | `hasRole("ADMIN")` | Not claimed by API chain |
| `GET /public/about` | FALLBACK | `permitAll` | No login required at HTTP rule |
| `POST /public/about` | FALLBACK | `denyAll` | Because only GET is public |
| `GET /actuator/health` | FALLBACK | `denyAll` | To expose health, add a narrow rule as needed |
| `GET /error` | FALLBACK | `denyAll` | Evaluate `ERROR` dispatcher behavior |
| `GET /unknown` | FALLBACK | `denyAll` | Closes undeclared URLs |
| `GET /api` | **Needs testing** | Depends on exact matcher semantics | `/api` and `/api/` may differ depending on configuration |

The table only shows **chain selection + rule authorization**. It does not guarantee HTTP 200, 401, 403, or 404. Final outcomes also depend on controllers, authentication entry points, CSRF, CORS, and business policies.

**Pitfall to avoid:** assuming `/api/**` always matches `/api`, `/api/`, trailing slashes, URL-encoded strings, or servlet context paths identically across versions/configs. Matcher implementations (MVC/Ant/PathPattern, servlet mappings, firewall) can vary. Test real boundary paths in your system.

## 9. Another mistake: fallback has a rule, but sits in the wrong chain

Consider the code:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll());
    return http.build();
}
~~~

It looks like it has `/public/**` and `denyAll`, yet:

- `/public/**` **does not belong to** `/api/**`, so the `permitAll` rule has no effect.
- URLs `/admin/**`, `/internal/**`, and `/public/**` all risk having **no chain** if this is the sole chain.
- `anyRequest().denyAll()` only blocks remaining `/api/**` requests.

To ensure public routes get proper security headers/filters, put the rule in an **unrestricted fallback chain** or a dedicated public chain matched appropriately, while still keeping a global fallback.

## 10. Filter-provided endpoints: `/login` and `/logout`

An easily missed detail when narrowing a chain:

~~~java
http.securityMatcher("/secured/**")
    .formLogin(Customizer.withDefaults());
~~~

Default `formLogin` may register endpoints like `GET /login` and `POST /login`. Yet the chain only claims `/secured/**`, so `/login` URLs **do not match this chain**. The login page or login-processing endpoint provided by the security filter may **not exist** in scope, leading to 404 or denial by the fallback.

You cannot simply put `permitAll()` on `/login` inside the `/secured/**` chain and expect it to work; the request still fails the **chain matcher**.

Solution in form-login apps: ensure login/logout URLs reside inside the scope of the chain containing the corresponding filters, e.g.:

~~~java
http.securityMatcher("/secured/**")
    .formLogin(form -> form
        .loginPage("/secured/login")
        .loginProcessingUrl("/secured/login")
        .permitAll()
    )
    .logout(logout -> logout
        .logoutUrl("/secured/logout")
        .logoutSuccessUrl("/secured/login?logout")
        .permitAll()
    );
~~~

When configuring `loginPage("/secured/login")`, the application must **provide an appropriate GET login page**; Spring Security's filter handles POST login per configuration. Do not confuse filter-provided login URLs with application controllers. Logout paths, CSRF, success/failure redirects, form action URLs, and `securityMatcher` must all align and be tested.

Another chain might catch `/login`, yet **it will not trigger the login filter of the skipped chain**.

## 11. Do not assume filters are shared across chains

Possible configurations:

~~~text
/api/**:
  httpBasic or bearer token
  stateless session policy (if designed)
  AuthorizationFilter checking API permissions

/admin/**:
  form login / session or httpBasic
  CSRF, session management for admin UI
  AuthorizationFilter checking ROLE_ADMIN

fallback:
  public URLs permitted per allowlist
  undeclared URLs denyAll
~~~

Mechanisms can differ completely. Consequently:

- If HTTP Basic is enabled **only in the API chain**, requests entering the ADMIN chain do not necessarily have that HTTP Basic authentication filter.
- If JWT Resource Server is enabled **only in the API chain**, Bearer tokens sent to the ADMIN chain are not guaranteed to be verified by the ADMIN chain.
- If the ADMIN chain uses sessions, do not assume the same stateless behavior as the API.
- If CSRF protection is adjusted in one chain, do not assume that adjustment applies across all chains.
- Exception entry points and access-denied behavior can differ: the same missing permission may yield 401/403/redirect depending on chain.
- Service-layer method security remains another defensive layer, yet **should never justify leaving URLs without a chain**.

**Design rule:** split chains only when different authentication/filters/policies are genuinely needed. If only URL permissions differ while sharing the same protection model, **one `SecurityFilterChain`** with multiple `requestMatchers` can be simpler and less risky.

## 12. Comparing designs: safe, dangerous, and deceptive

| Design | Outcome | Assessment |
|---|---|---|
| One default chain + `requestMatchers` + `anyRequest().denyAll()` | All requests match the default chain; rules decide | Simple, easy to audit |
| API chain `/api/**` + ADMIN chain `/admin/**`, **no fallback** | Other URLs may skip Spring Security chains | Dangerous if endpoints exist outside scopes |
| API chain + ADMIN chain + trailing catch-all `denyAll` | Covers undeclared URLs | Appropriate when multiple security models are needed |
| Catch-all `permitAll` `@Order(1)` before ADMIN | ADMIN chain may be completely shadowed | Very dangerous |
| Broad API `/api/**` prioritized before narrow `/api/admin/**` | Narrow chain does not run for admin APIs | Ordering bug |
| Using `web.ignoring` for paths needing authentication | Disables security filtering on that path | Wrong tool |
| `anyRequest().denyAll()` in a chain matching only `/api/**` | Blocks extra APIs but leaves non-API URLs unprotected | Not a system-wide fallback |
| Having a fallback placed after a default match-all chain | Fallback is never selected | Needs matcher/priority review |
| Using only `authenticated` for sensitive APIs | Login alone passes the HTTP layer | Needs permissions and object policies |

**Structural recommendation:** the more chains you have, the more "intersections" arise among matchers, ordering, CSRF, login URLs, and exception handlers. Avoid creating multiple chains merely to group endpoints neatly if one chain with clear rules suffices.

## 13. How to verify "no matching chain" with tests?

Do not test only that valid endpoints return 200. Tests must cover **areas outside matchers** and prove they are protected properly.

### 13.1. Coverage matrix before coding

Draft a "request → expected chain → rule" table:

| Group | Sample request | Expected chain | Expected outcome |
|---|---|---|---|
| Public API | `GET /api/public/faq` | API | Passes HTTP rule even when anonymous |
| Sensitive API | `GET /api/reports/2026` | API | Missing `report:read` → denied |
| Other API | `POST /api/orders` | API | Requires authentication and CSRF per policy |
| Admin | `GET /admin/users` | ADMIN | Regular user → denied; admin → passes HTTP rule |
| Public content | `GET /public/about` | FALLBACK | Passes HTTP rule |
| Undeclared | `GET /debug/threads` | FALLBACK | Denied |
| System health | `GET /actuator/health` | FALLBACK or dedicated chain | Per operational policy |
| Login/logout URLs | `GET /login`, `POST /login` | Chain containing login filter | Login flow works properly |
| Error/forward URLs | `/error`, `ERROR`/`FORWARD` dispatchers | Expected chain | Error handling works without opening bypasses |
| Boundary paths | `/api`, `/api/`, `/api//reports` | Chain chosen by real matcher | No unexpected gaps |

Each group should be tested with anonymous users, regular users, and appropriately privileged users where relevant.

### 13.2. MockMvc: testing access on real endpoints

A test sample in a **Spring Boot MVC project with Spring Security Test**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChainCoverageTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unknownUrlMustBeRejectedByFallback() throws Exception {
        mvc.perform(get("/debug/threads"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotEnterAdmin() throws Exception {
        mvc.perform(get("/admin/users")
                    .with(user("lan").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReachExistingAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/users")
                    .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk());
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/about"))
                .andExpect(status().isOk());
    }
}
~~~

**Preconditions:** `/admin/users` and `/public/about` must actually exist and return HTTP 200 when permitted; fallback and access-denied handlers must produce 403 for those requests. This test sample **does not run standalone**; it needs Spring Boot Test + Spring Security Test, controllers, and complete security config.

**More important than status 403:** if `/debug/threads` has no controller, it can also return **404 when no security chain exists**. Testing status on a **nonexistent** URL creates a false sense of security. When proving coverage, use a test endpoint with a real handler or inspect chain matchers directly and ensure invalid requests cannot access data.

### 13.3. Inspecting chain matchers directly

You can write an integration test fetching the list of `SecurityFilterChain`s managed by `FilterChainProxy`, building a `MockHttpServletRequest` with representative URLs/methods, counting how many chains have `matches(request) == true`, and asserting the **first matching chain** is the expected one.

Target:

~~~text
GET /api/orders      -> selected API
GET /admin/users     -> selected ADMIN
GET /public/about    -> selected FALLBACK
GET /debug/threads   -> selected FALLBACK, denyAll
POST /internal/ops   -> selected FALLBACK, denyAll
~~~

Having multiple chains match a request is not an error if specialized chains precede the fallback; only the **first** chain is used. What must be verified is that **no important request matches 0 chains**, and no overly broad chain is evaluated before a stricter chain.

To trust the result, the test must construct `MockHttpServletRequest` with full details like `contextPath`, `servletPath`/`pathInfo`, and `dispatcherType` matching the app's matchers/servlet mappings. With MVC or PathPattern matchers, prefer MockMvc integration tests to mirror the runtime environment accurately.

### 13.4. Especially valuable negative tests

1. **Shadowed narrow chain**: User with `ROLE_USER` tries `/api/admin/users` and must be denied, even if the broad API chain lets logged-in users through.
2. **Gap outside all chains**: Add a sensitive test endpoint outside `/api/**`/`/admin/**`; verify the fallback truly blocks anonymous callers.
3. **Order shifts**: Temporarily add an `@Order(0)` bean in config tests to detect shadowing risks, or assert bean order in architecture tests.
4. **Different HTTP methods**: Permitting GET must not imply POST/DELETE on the same path share the same permission.
5. **Generated login/logout endpoints**: If a chain uses form login, GET/POST login genuinely enters the right chain.
6. **Exception paths**: Error-handling pages respond properly without redirect loops or widened permissions.
7. **Actuator**: Any enabled actuator endpoint must have an explicit policy; test actual deployment environments, not only default config.
8. **Proxy rewrites/context paths**: The path Spring sees can differ from the public URL; test via gateway or integration environment if routing rewrites paths.

## 14. Routing tests differ from data authorization tests

A request can match the right chain and pass the HTTP rule yet **still not be allowed to operate on a resource**.

Example `GET /api/reports/2026`:

~~~text
1. Chain selected = API
2. HTTP rule = hasAuthority("report:read")
3. Principal has report:read => passes HTTP authorization
4. Service policy:
      correct tenant?
      granted access on this report?
      data within allowed scope?
5. Repository restricts by tenant/owner
~~~

Therefore **two independent test layers** are needed:

- **Chain coverage tests**: select the right chain and rule for URL/method/dispatcher.
- **Object authorization tests**: two users with the same role cannot read each other's resources; tenant A cannot read tenant B.

Never drop service policies because a fallback exists, and never accept a chain coverage gap because service policies exist.

## 15. Standalone Java 17: simulating first-chain selection

The following program uses **plain Java** to simulate `@Order` and "first matching chain wins." This is **not Spring Security source code** and does not execute filters, authentication, CSRF, or real matchers. `startsWith` is only used to clarify prefix-based chain selection.

Create file `ChainSelectionDemo.java`:

~~~java
import java.util.Comparator;
import java.util.List;

public class ChainSelectionDemo {
    record Chain(int order, String name, String prefix, String policy) {
        boolean matches(String path) {
            return "*".equals(prefix) || path.startsWith(prefix);
        }
    }

    static String select(String path, List<Chain> chains) {
        return chains.stream()
                .sorted(Comparator.comparingInt(Chain::order))
                .filter(chain -> chain.matches(path))
                .findFirst()
                .map(chain -> chain.name() + " [" + chain.policy() + "]")
                .orElse("NO_CHAIN");
    }

    static void show(String label, String path, List<Chain> chains) {
        System.out.println(label + ": " + select(path, chains));
    }

    public static void main(String[] args) {
        List<Chain> incomplete = List.of(
                new Chain(1, "API", "/api/", "AUTHENTICATED"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN")
        );

        show("gap /public", "/public/info", incomplete);
        show("api /api/orders", "/api/orders", incomplete);
        show("admin /admin/audit", "/admin/audit", incomplete);

        List<Chain> covered = List.of(
                new Chain(1, "API", "/api/", "AUTHENTICATED"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN"),
                new Chain(99, "FALLBACK", "*", "DENY_ALL")
        );
        show("safe /public", "/public/info", covered);

        List<Chain> wrongOrder = List.of(
                new Chain(1, "EARLY_CATCH_ALL", "*", "PERMIT_ALL"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN")
        );
        show("wrong /admin", "/admin/audit", wrongOrder);

        List<Chain> unsorted = List.of(
                new Chain(99, "FALLBACK", "*", "DENY_ALL"),
                new Chain(2, "ADMIN", "/admin/", "ROLE_ADMIN"),
                new Chain(1, "API", "/api/", "AUTHENTICATED")
        );
        show("unsorted input /admin", "/admin/audit", unsorted);
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac --release 17 ChainSelectionDemo.java
java ChainSelectionDemo
~~~

Exact output:

~~~text
gap /public: NO_CHAIN
api /api/orders: API [AUTHENTICATED]
admin /admin/audit: ADMIN [ROLE_ADMIN]
safe /public: FALLBACK [DENY_ALL]
wrong /admin: EARLY_CATCH_ALL [PERMIT_ALL]
unsorted input /admin: ADMIN [ROLE_ADMIN]
~~~

Interpretation:

- **`NO_CHAIN`**: no chain claimed `/public/info` in the list lacking a fallback. In real Spring Security, the equivalent situation is **no Spring Security chain protecting the request**; no HTTP status can be inferred from this alone.
- **`API`** and **`ADMIN`**: URLs belong to specialized matchers.
- **`FALLBACK [DENY_ALL]`**: URLs outside the first two chains still have a chain to evaluate and deny. The output only reflects the **configured policy**, without executing authentication.
- **`EARLY_CATCH_ALL [PERMIT_ALL]`**: an open fallback placed first shadows the admin chain; this is an obvious risk.
- **`unsorted input`**: independent of List element order, because the simulation sorts by order before selecting. In real Spring Security, ordering is handled by the framework via registration and `@Order` on beans.

Extension exercise: modify the `covered` list so `/api/admin/**` has an order-0 chain with `ROLE_ADMIN`. Test that the narrow chain must precede the broad API chain to avoid being shadowed.

## 16. Debugging when a URL is not blocked as expected

Do not look only at `hasRole`/`denyAll`. Trace in order:

1. **What request does Spring actually receive?** Do method, path, context path, servlet mapping, and dispatcher type differ from the external proxy URL?
2. **Is `FilterChainProxy` registered and active?** Is Spring Security configured for this servlet context? Are any paths excluded by `web.ignoring`?
3. **How many `SecurityFilterChain` beans exist?** List all beans/`@Order`/matchers; do not inspect only one config class.
4. **Which chain matches first?** Does an overly broad matcher or early priority shadow a specialized chain?
5. **Is there a fallback chain?** Does it truly have no restrictive `securityMatcher`? Is it evaluated after specialized chains?
6. **What are the rules inside the chain?** `requestMatchers`, `anyRequest`, method/dispatcher, and rule order.
7. **Do that chain's authentication filters work?** Are JWT, HTTP Basic, form login, session, custom providers, and entry points in the right chain?
8. **Are there CSRF/CORS or method security errors?** A 403 does not necessarily come from an authorization rule; a 404 does not prove an endpoint is protected.
9. **Are there object-level constraints?** Right role with wrong owner/tenant must still be denied by business policy.
10. **What do negative tests show?** Are anonymous users, regular users, cross-tenant users, and URLs outside every prefix all tested?

### Logging for investigation

You can enable Spring Security DEBUG/TRACE logging in dev/test environments to observe request protection and which filter chain is likely selected:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Exact logs depend on version and configuration. **Never leave verbose security logging enabled in production**, never log raw credentials/access tokens, and never treat logs as a substitute for integration tests. In gateway/proxy environments, also observe the request path at the Servlet layer after rewriting.

## 17. Common mistakes and fixes

| Mistake | Risk | Remediation |
|---|---|---|
| Declaring two narrow chains without a fallback | Other URLs bypass Spring Security filter chains | Catch-all chain at the end |
| Assuming `anyRequest().denyAll()` in API chain protects the whole app | URLs outside `securityMatcher` slip through | Distinguish chain matchers from rule matchers |
| Placing `/api/**` chain before `/api/admin/**` | Admin chain is shadowed | Give specialized chains higher priority |
| Catch-all `permitAll` before other chains | Nullifies all subsequent chains | Put fallback last, keep public allowlist narrow |
| Putting `/admin/**` rule inside a chain matching only `/api/**` | Rule never executes | Place rule in a chain whose matcher covers it |
| Thinking chain B adds filters to chain A | Missing CSRF/auth mechanism/authorization | Configure full policies per chain |
| Testing only existing/200 endpoints without testing out-of-scope URLs | Misses chain coverage gaps | Negative tests with real handlers and matchers |
| Relying on 404 to conclude access is blocked | 404 may simply mean no route exists | Distinguish 404 from security denial |
| Attaching `formLogin` to `/secured/**` chain while leaving default `/login` | Login URL is outside the chain, may 404 | Customize login/logout URLs within chain scope |
| Leaving `/actuator/**` outside all chains | Exposes operational endpoints when enabled | Explicit actuator policy, test deployment environment |
| Ignoring `ERROR`/`FORWARD` dispatches | Error pages may be blocked or mis-policied | Test dispatchers and guard internal routes |
| Using `authenticated()` for all sensitive APIs | Regular users can perform unauthorized actions | Roles/permissions + object policies |
| Relying on Boot defaults without inspecting beans | Expected fallback may not exist | Audit actual chain beans |
| Multiple chains with the same order without verifying precedence | Chain choice depends on ambiguous order | Explicit `@Order` and tests |

## 18. Pre-merge design checklist

For every PR adding or modifying a `SecurityFilterChain`:

- [ ] List **all** active chains, their chain-level matchers, and `@Order` values.
- [ ] Verify narrower, more sensitive chains take priority before broader chains.
- [ ] Ensure there is **one trailing catch-all fallback**, unrestricted by `securityMatcher`, if the goal is protecting the entire Servlet app.
- [ ] Fallback defaults to `denyAll` or an equally strict rule; public URLs are a narrow, justified allowlist.
- [ ] Do not let a broad-matcher chain with `permitAll`/`authenticated` shadow sensitive chains.
- [ ] Explicitly identify which chain handles `/login`, `/logout`, `/error`, static resources, actuator, CORS preflight, and API documentation.
- [ ] Ensure authentication, CSRF, session, CORS, and exception handling are **accurate within each chain**.
- [ ] Test boundary paths `/api`, `/api/`, trailing slashes, context paths, and proxy rewrites where applicable.
- [ ] Test anonymous, authenticated users, under-privileged users, and high-role users; not just happy paths.
- [ ] Test a sensitive endpoint outside all declared prefixes to prove the fallback blocks it.
- [ ] Never trust the HTTP layer to replace object-level policies on tenant/owner.
- [ ] Include regression tests whenever adding a new chain or changing `@Order`.

**One-line review rule:** *Every request must enter the right chain; every chain must enforce the right permissions; undeclared requests must be intentionally blocked.*

## 19. Self-check questions

**1. There are two chains `/api/**` and `/admin/**`, both ending with `anyRequest().denyAll()`. Is `GET /debug` guaranteed to be denied by Spring Security?**  
You cannot conclude yes. Without another fallback chain, the request matches no chain, so neither `denyAll` rule is evaluated.

**2. How do `securityMatcher` and `requestMatchers` differ?**  
`securityMatcher` decides **whether this entire chain applies to the request**; `requestMatchers` decides **which authorization rule applies inside the selected chain**.

**3. If `@Order(1)` has matcher `/api/**` and `@Order(2)` has matcher `/api/admin/**`, which chain does an admin request match?**  
`@Order(1)` first. `@Order(2)` is not invoked afterward, even though its matcher also matches.

**4. Can you just add `anyRequest().denyAll()` to the API chain to plug URL gaps?**  
No. You need another chain whose matcher covers remaining URLs, usually a final catch-all.

**5. Is an `@Order(1)` catch-all with `permitAll` safe if the `@Order(2)` admin chain has `hasRole("ADMIN")`?**  
No. The catch-all shadows the admin chain. The admin rule is never evaluated.

**6. Why might a chain matching only `/secured/**` with `formLogin` return 404 on `GET /login`?**  
Because the filter-provided endpoint falls outside the chain-level matcher. Customize login URLs into scope and provide a login page if using a custom login page.

**7. Does `GET /public/faq` returning 404 prove the URL is blocked by Spring Security?**  
No. It may simply be a nonexistent route; verify the actual chain and security decision.

**8. Should you use multiple chains just to separate `/api/admin/**` from `/api/users/**` if both share the same authentication mechanism?**  
Not required. One chain using different `requestMatchers` is usually simpler; multiple chains fit when separate filter sets/authentication mechanisms are needed.

**9. If a request passes the API chain with the right role, does that guarantee permission to read another user's invoice?**  
No. You need policies by owner/tenant/permission on the specific resource.

**10. What is the most important test for this lesson?**  
Verify that **requests outside all declared matchers** are still protected by the fallback; and verify that **narrow chains are not shadowed by earlier broad chains**.

## 20. Official references

- Spring Security – **Java Configuration / Multiple HttpSecurity Instances / Choosing securityMatcher or requestMatchers / SecurityFilterChain Endpoints**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security – **Servlet Architecture / Multiple SecurityFilterChain / FilterChainProxy**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – **Testing with MockMvc**: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security – **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
