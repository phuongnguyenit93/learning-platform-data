# Reading the Filter List and Identifying the Selected SecurityFilterChain in Spring Security Servlet

> **Scope:** Java 17+, Spring Boot 3, and Spring Security 6 on the **Servlet stack**. This guide focuses on **diagnosing the path of an HTTP request**: which filters participate, why a `SecurityFilterChain` is selected, how to read logs and filter lists, how to verify with tests, and how to distinguish chain-selection bugs from authentication/authorization errors. This is not a guide on WebFlux (`SecurityWebFilterChain`).
>
> **Core principle:** `FilterChainProxy` iterates through `SecurityFilterChain` instances **in order**, selects **the first chain whose `RequestMatcher` matches the request**, and runs only the filters of that chain. It does not merge filters from all matching chains. Therefore, you must know **each chain's matcher**, **chain order**, and **the filter list inside the selected chain** before concluding whether a request is properly protected by Spring Security.

## 1. Why Is Reading the Filter List Important?

A single application may simultaneously serve:

- `/api/**`: REST endpoints accepting HTTP Basic or Bearer tokens, typically returning `401` when unauthenticated.
- `/admin/**`: administrative endpoints requiring a dedicated role or scope.
- `/login` and traditional web pages: form login, `HttpSession`, and CSRF.
- `/public/**`: readable by unauthenticated users, yet still requiring security headers.
- `/actuator/**` or a separate servlet: some endpoints reside in a different servlet context or filter chain.

Common diagnostic questions:

1. Why does an unauthenticated `GET /api/orders` **redirect 302 to `/login`** instead of returning 401?
2. Why does an `oauth2ResourceServer(...)` configuration not process a Bearer token on a specific URL?
3. Why does an endpoint return **403** even though the user has a valid `Authentication`?
4. Why do static resources not receive CSP/HSTS/security headers?
5. Why does a custom filter run twice, run in the wrong order, or not run at all?
6. Why does `requestMatchers("/api/**").permitAll()` not mean every `/api/**` request enters the “API chain”?
7. Why is a URL not covered by any chain even though the application has `anyRequest().authenticated()`?

To answer these, do not look only at the controller, exception handler, or a single `authorizeHttpRequests` line. You must trace **container filter → FilterChainProxy → selected SecurityFilterChain → ordered security filters → authorization → MVC**.

## 2. Architecture: DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain

Typical Spring Security Servlet model:

```text
Client
  |
  v
Servlet container's FilterChain
  |
  +-- Some application/container filters (the order varies)
  |
  +-- DelegatingFilterProxy
  |      bean name: springSecurityFilterChain
  |               |
  |               v
  |         FilterChainProxy
  |            |
  |            +-- SecurityFilterChain #1
  |            |     RequestMatcher: /api/**
  |            |     Filters: [SecurityContextHolderFilter,
  |            |               HeaderWriterFilter, ...,
  |            |               BasicAuthenticationFilter,
  |            |               ExceptionTranslationFilter,
  |            |               AuthorizationFilter]
  |            |
  |            +-- SecurityFilterChain #2
  |            |     RequestMatcher: /admin/**
  |            |     Filters: [context, headers, form login, ...]
  |            |
  |            +-- SecurityFilterChain #3
  |                  RequestMatcher: any request
  |                  Filters: [context, headers, form login, ...]
  |            |
  |            +--> FIRST MATCHING CHAIN ONLY
  |
  +-- Remaining servlet filters
  |
  v
DispatcherServlet -> HandlerMapping -> Controller
```

**`DelegatingFilterProxy`** is the bridge between the Servlet filter lifecycle and the Spring `ApplicationContext`: it looks up a Spring-managed bean, usually named `springSecurityFilterChain`.

**`FilterChainProxy`** is the filter representing Spring Security. It owns the list of `SecurityFilterChain` instances and determines which chain will handle a request. Security filters inside a chain are typically not registered directly as individual servlet filters.

**`SecurityFilterChain`** represents two pieces of information:
- Chain selection condition: `matches(HttpServletRequest)`.
- Ordered list of filters: `getFilters()`.

Commonly encountered filters (illustrative examples only, not guaranteed for every configuration):
- `DisableEncodeUrlFilter`;
- `WebAsyncManagerIntegrationFilter`;
- `SecurityContextHolderFilter`;
- `HeaderWriterFilter`;
- `CsrfFilter`;
- `LogoutFilter`;
- `UsernamePasswordAuthenticationFilter` when using form login;
- `BasicAuthenticationFilter` when HTTP Basic is enabled;
- `BearerTokenAuthenticationFilter` when OAuth2 Resource Server is enabled;
- `AnonymousAuthenticationFilter`;
- `ExceptionTranslationFilter`;
- `AuthorizationFilter`.

**Actual presence and order** depend on the Spring Security version, DSL, login mechanism, session policy, and custom filters. Do not memorize a “standard” list and assume it always applies.

### 2.1. One Request Selects Only One Security Chain

Suppose there are three chains in order:

| Evaluation Order | SecurityFilterChain Matcher | Matching Requests |
| --- | --- | --- |
| 1 | `/api/**` | `/api/orders`, `/api/users` |
| 2 | `/admin/**` | `/admin/users` |
| 3 | `anyRequest` | Other requests such as `/login`, `/dashboard` |

For `GET /api/orders`, chain #1 matches and is selected. Spring Security **does not continue** running chain #2 or #3 even if a matcher in a later chain could also match.

If you put the `anyRequest` matcher first, it matches nearly every request entering the servlet chain and can “swallow” specialized chains behind it. The fact that the app still starts does not guarantee routes are protected as intended.

**Important consequence:** If a filter in chain #1 decides to proceed or return an error, Spring Security **does not** “try chain #2” afterward. The selected chain is not an automatic authentication fallback mechanism.

### 2.2. When No Chain Matches

If `FilterChainProxy` finds no `SecurityFilterChain` matching the request, Spring Security's filters are not applied to that request and it may proceed down to the Servlet application. This can leave an endpoint **unprotected by Spring Security** if no other safeguard exists.

Do not confuse this case with a chain whose matcher matches and is configured with `permitAll()`. With `permitAll`, the chain still runs: relevant security filters, headers, context, and other mechanisms can still participate.

In multi-chain applications, it is usually good practice to have a **catch-all fallback chain** at the end and test all critical URLs. If you intentionally leave a URL outside Spring Security, there must be a clear rationale and threat model.

## 3. Two Easily Confused Matcher Groups: securityMatcher and requestMatchers

### 3.1. securityMatcher Selects the **Chain**

`http.securityMatcher("/api/**")` determines **which requests can enter the SecurityFilterChain** built from that `HttpSecurity`.

Example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

Every request matching `/api/**` enters this chain unless already selected by an earlier-ordered chain. Inside it, `anyRequest().authenticated()` applies **only to requests selected by this chain**, not to every URL in the application.

### 3.2. requestMatchers Inside authorizeHttpRequests Sets **Authorization Rules**

`http.authorizeHttpRequests(auth -> auth.requestMatchers(...).permitAll())` is not an alternative syntax for `http.securityMatcher(...)`. It defines **authorization rules after a security chain has already been selected**.

Example:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Here:
- `securityMatcher("/api/**")` selects the chain.
- The `requestMatchers` inside `authorizeHttpRequests` check permissions for **paths within that chain**.
- If the request is `/dashboard`, the authorization rules above **never get a chance to run**.
- If the request is `/api/admin/42`, the API chain is selected and then the admin authorization rule is applied.

**Do not use `requestMatchers("/api/**").authenticated()` inside a catch-all chain expecting Spring Security to automatically transfer to a separate API chain.** Chain selection occurs **before** authorization inside the selected chain.

### 3.3. @Order and Declaration Order

When there are multiple `SecurityFilterChain` beans, use `@Order` or a supported ordering mechanism to specify evaluation order:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception { ... }

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception { ... }
```

**Place specific chains first and broad catch-all chains last.** Do not rely on source file order, bean names, alphabetical order, or incidental behavior when multiple beans share the same priority. **Filter ordering inside a single chain** is managed by Spring Security according to its own filter ordering rules; do not confuse it with `@Order` on `SecurityFilterChain` beans.

## 4. Spring Security Servlet Example: API and Web Using Two Chains

This example can be used in a Spring Boot 3, Spring Security 6 project on Java 17+ with the `spring-boot-starter-web` and `spring-boot-starter-security` starters. Each file belongs in a package scanned by `@SpringBootApplication`; this is not standalone Java runnable with `javac` without Spring libraries.

### 4.1. SecurityConfig.java

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-test-only"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Here:
- **Chain 1** accepts only `/api/**` URLs; unauthenticated requests typically receive HTTP `401` via the HTTP Basic authentication entry point.
- **Chain 2** does not set a specific `securityMatcher`, so its matcher covers the remaining requests. Unauthenticated web requests typically redirect `302` to the login page.
- `/api/admin/**` requires role `ADMIN`; user `alice` only has role `USER`, so a valid Basic request is still denied with **403**.
- `/api/public/**` uses `permitAll` **within the API chain**, which does not mean bypassing all security filters.
- The configuration does not disable CSRF globally. The tests below use GET; for POST/PUT/DELETE, CSRF must be handled according to the credential mechanism. If an API chain uses HTTP Basic and browsers can automatically send Basic credentials, you must **evaluate CSRF** rather than disabling it automatically just because of the `/api` prefix.
- `httpBasic` and `formLogin` are two authentication mechanisms attached to **two different chains**, not an automatic fallback list on the same request.

**Practical note:** `/login` may use Spring Security's default generated login page; if you build your own page, the controller and static resources must have appropriate rules. Depending on the application context, additional filters created by Spring Boot or libraries may exist, but only filters inside the selected Spring Security chain participate through this mechanism.

### 4.2. DemoController.java

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public String publicPing() {
        return "pong";
    }

    @GetMapping("/api/orders")
    public String orders() {
        return "orders";
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "admin-report";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }
}
```

The responses only serve to test chain selection and authorization; they contain no real data. `/api/orders` defines no business permissions beyond authenticated; real projects require per-endpoint scope/ownership checks.

### 4.3. Expectations per URL

| Request | Selected Chain | Primary Authentication Filter | Typical Result |
| --- | --- | --- | --- |
| `GET /api/public/ping` without auth | API | `BasicAuthenticationFilter` present but no header | `200 pong` because `permitAll` |
| `GET /api/orders` without auth | API | HTTP Basic | `401`, usually `WWW-Authenticate: Basic` |
| `GET /api/orders` with valid Basic | API | HTTP Basic | `200 orders` |
| `GET /api/admin/report` with Alice/USER | API | HTTP Basic | `403` due to missing ADMIN |
| `GET /dashboard` without auth | Web fallback | Form login | `302` redirect to `/login` |
| `GET /dashboard` after valid form login | Web fallback | Session/authentication in web chain | `200 dashboard` |
| `GET /apiary` without auth | Web fallback | Form login | Usually redirects to `/login`; **not** the API chain |
| `GET /login` | Web fallback | Login page filters | Login page per config/version |
| `GET /not-found` authenticated | Web fallback | Web auth | Spring MVC may return 404; that does not mean no chain matched |

Distinguish **where the failure occurred**: `401`, `403`, or `302` may come from an authentication entry point or authorization; `404` means no route/controller exists after the filter chain let the request pass. Looking at status alone does not prove which chain was selected — combine it with logs, the filter inventory, and targeted tests.

## 5. Standalone Java 17: Simulating the First-Match Rule

This pure-JDK program illustrates **the algorithm for picking the first matching element**. It is **not an implementation of Spring Security's RequestMatcher**: it does not consider servlet context, URL decoding, path normalization, or HTTP firewall. Use it to understand the ordering principle, not as real security logic.

File `FirstMatchingChainDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public final class FirstMatchingChainDemo {
    record Rule(String name, Predicate<String> matches) {}

    static String selected(List<Rule> chains, String path) {
        for (Rule chain : chains) {
            if (chain.matches().test(path)) {
                return chain.name();
            }
        }
        return "<none>";
    }

    public static void main(String[] args) {
        List<Rule> ordered = List.of(
            new Rule("API", p -> p.startsWith("/api/")),
            new Rule("ADMIN", p -> p.startsWith("/admin/")),
            new Rule("WEB", p -> true)
        );

        for (String path : List.of(
                "/api/orders", "/admin/users", "/dashboard", "/apiary")) {
            System.out.println(path + " -> " + selected(ordered, path));
        }

        List<Rule> wrongOrder = List.of(
            new Rule("WEB", p -> true),
            new Rule("API", p -> p.startsWith("/api/"))
        );
        System.out.println("wrong-order: /api/orders -> " +
            selected(wrongOrder, "/api/orders"));
    }
}
```

Compile and run with JDK 17+:

```bash
javac FirstMatchingChainDemo.java
java FirstMatchingChainDemo
```

Exact stdout:

```text
/api/orders -> API
/admin/users -> ADMIN
/dashboard -> WEB
/apiary -> WEB
wrong-order: /api/orders -> WEB
```

Explanation: `/apiary` does **not** start with `/api/` in this simple model, so it falls into WEB. When the WEB matcher `p -> true` comes first, every path is “swallowed” before the API matcher gets a chance to run. In Spring Security, real path matchers are more complex and you must rely on the framework rather than `startsWith` to decide endpoint protection.

## 6. Reading the SecurityFilterChain List at Application Startup

You do not need to wait for a failing request to inspect chains. Spring Security builds `SecurityFilterChain` instances from the DSL, typically logging chain creation and listing matchers along with filter classes. Exact log content depends on the version.

There are two complementary approaches:
1. **Enable appropriate logging in test/dev environments** to observe chain configuration and request matching.
2. **Controlled access to `FilterChainProxy.getFilterChains()`** to print the matcher names and filters the app actually initialized.

### 6.1. Enabling Logging

In a controlled development/staging environment, configure:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
```

`TRACE` helps observe how Spring Security tries chains, which chain is selected, and which security filters execute. Exact message names, formatting, filter counts, and detailed order are **not stable across versions**; inspect actual logs rather than searching for one fixed literal string.

Typical message patterns you may see (**illustrative** only, not guaranteed output):

```text
Will secure ... with [ ... filter names ... ]
Trying to match request against ... 
Securing GET /api/orders
Invoking ... filter ...
```

Observe:
- Each chain's matcher and the order evaluated.
- Which chain matches **first**.
- Whether the expected authentication filter is present (`BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, `BearerTokenAuthenticationFilter`, ...).
- Whether `AuthorizationFilter` runs at the expected end of the protection flow.
- Whether the request is rejected by the HTTP firewall before reaching application routing.

**Do not enable broad TRACE/DEBUG in production just to inspect a username.** Logs can contain URLs/queries, identities, security details, and sometimes sensitive data written by custom filters. When debugging, use a safe environment, synthetic test requests, short retention, and **redact Authorization, Cookie, Set-Cookie, session IDs, and tokens**.

### 6.2. Spring Security Debug Mode

A diagnostic configuration available in development is:

```java
// Use only in local/test environments and only when debugging:
@EnableWebSecurity(debug = true)
```

This is an **illustrative annotation**, not a standalone class. Debug mode can provide useful request/chain information, but it is **not for production**; output can expose significant request data and add overhead. Disable it once diagnosis is complete.

Prefer a scoped `FilterChainProxy` logger if you only need to know which chain matched, then widen loggers if needed. Do not equate servlet container filter logs with `FilterChainProxy` logs.

### 6.3. Listing Chains via Java Code in Internal Environments

A `CommandLineRunner` enabled only for the `dev` profile can print the inventory at startup. File `SecurityChainInventory.java` (code **inside a Spring Boot application**, not standalone):

```java
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.DefaultSecurityFilterChain;

@Configuration
@Profile("dev")
public class SecurityChainInventory {
    private static final Logger log =
        LoggerFactory.getLogger(SecurityChainInventory.class);

    @Bean
    CommandLineRunner reportSecurityChains(
            @Qualifier("springSecurityFilterChain")
            FilterChainProxy proxy) {

        return args -> {
            int index = 0;
            for (SecurityFilterChain chain : proxy.getFilterChains()) {
                index++;

                String matcherDescription =
                    chain instanceof DefaultSecurityFilterChain known
                        ? known.getRequestMatcher().toString()
                        : chain.getClass().getName();

                String filterNames = chain.getFilters().stream()
                    .map(filter -> filter.getClass().getSimpleName())
                    .collect(Collectors.joining(" -> "));

                log.info("SECURITY CHAIN #{} matcher={}",
                    index, matcherDescription);
                log.info("SECURITY CHAIN #{} filters={}",
                    index, filterNames);
            }
        };
    }
}
```

**Meaning:**
- `getFilterChains()` returns the list of `SecurityFilterChain` instances held by `FilterChainProxy`, in the order actually used.
- `SecurityFilterChain.getFilters()` provides the chain's filter list, generally in the exact execution order within the chain.
- For `DefaultSecurityFilterChain`, `getRequestMatcher()` provides matcher details. The matcher's `toString()` is **diagnostic data**, not a stable contract format for automated parsers.
- Use `@Profile("dev")` only and **do not expose the inventory via a public endpoint**. Filter and matcher names reveal the application's internal protection structure.
- Never log `Authentication`, secrets, or raw HTTP headers in the inventory.

This listing answers **“which chains did the application build?”**, whereas to know **“which chain does a specific request match?”**, you still need per-request logging or calling `matches(request)` on a properly contextualized request.

### 6.4. Checking the Matching Chain Yourself in Internal Tests

One diagnostic technique in test environments is iterating the chain list directly:

```java
// Snippet inside a test/helper that already has FilterChainProxy proxy
// and HttpServletRequest request provided by the Servlet test/container.
int index = 0;
SecurityFilterChain chosen = null;

for (SecurityFilterChain chain : proxy.getFilterChains()) {
    index++;
    if (chain.matches(request)) {
        chosen = chain;
        System.out.println("first match #" + index);
        break;
    }
}

if (chosen != null) {
    for (jakarta.servlet.Filter filter : chosen.getFilters()) {
        System.out.println(filter.getClass().getSimpleName());
    }
} else {
    System.out.println("NO_SECURITY_CHAIN_MATCH");
}
```

This is a **snippet**, not a standalone Java file; imports and variables `proxy`, `request`, and `SecurityFilterChain` must exist in the test/helper. **Do not** construct a `MockHttpServletRequest` with wrong `servletPath`/`contextPath` and assume it matches identically to a real request.

An important difference: `FilterChainProxy` may apply `HttpFirewall` and evaluate matching on a **request already wrapped/normalized according to framework rules**. Calling `matches(rawRequest)` manually on an improperly constructed request is not strictly equivalent to the real HTTP flow. When a definitive conclusion is needed, verify with a **real request through the filter chain** and enable TRACE to observe the runtime selection.

## 7. Which Authentication Filters Appear Under Which Configurations?

Common indicators:

| Filter | Usually Paired With | Diagnostic Meaning |
| --- | --- | --- |
| `UsernamePasswordAuthenticationFilter` | Form login | Processes username/password submissions on the login processing URL |
| `BasicAuthenticationFilter` | `httpBasic` | Processes `Authorization: Basic ...` |
| `BearerTokenAuthenticationFilter` | `oauth2ResourceServer` | Extracts Bearer token and invokes the authentication pipeline |
| `OAuth2AuthorizationRequestRedirectFilter` | OAuth2 Login | Initiates redirect to the OAuth2 provider |
| `OAuth2LoginAuthenticationFilter` | OAuth2 Login | Processes callback/login authentication |
| `SecurityContextHolderFilter` | Security context lifecycle | Supplies context during the request, coordinating with the repository |
| `CsrfFilter` | CSRF enabled | Enforces CSRF checks on protected requests |
| `LogoutFilter` | Logout configuration | Detects logout requests and invokes logout handlers |
| `AnonymousAuthenticationFilter` | Anonymous authentication enabled | Represents anonymous principal when no Authentication is present |
| `ExceptionTranslationFilter` | Web security exception handling | Translates certain exceptions into authentication entry point / access denied responses |
| `AuthorizationFilter` | `authorizeHttpRequests` | Enforces the chain's authorization decisions |

**Do not read filter names mechanically:** for example, `BearerTokenAuthenticationFilter` being present does not mean every request carries a bearer token; `CsrfFilter` being present does not mean GET is blocked; `AuthorizationFilter` being present does not mean strict rules exist on every endpoint.

What must be verified is **whether the filter is in the selected chain**, **whether the request actually passes through the filter**, and **whether the corresponding step applies to that HTTP method/URL**.

### 7.1. Filter Order Inside a Chain

Spring Security has a built-in filter order. Several relationships are routinely important:
- The security context must be prepared before authorization uses `Authentication`.
- Authentication filters process credentials before final authorization makes a decision.
- `ExceptionTranslationFilter` coordinates translating authentication/authorization exceptions into appropriate HTTP responses.
- `AuthorizationFilter` is typically the final authorization step in many `authorizeHttpRequests` configurations.

When adding a custom filter, use `addFilterBefore`, `addFilterAfter`, or `addFilterAt` with an appropriate filter type and understand its actual position in the chain:

```java
// Illustrative snippet: filter type and position must be evaluated.
// http.addFilterBefore(customFilter, AuthorizationFilter.class);
```

**Do not** place `@Order` on a `@Component Filter` expecting it to be inserted into `FilterChainProxy` at a specific security position. Container filter `@Order` and security filter ordering are two separate layers.

### 7.2. Watch Out for Filters Registered Twice

When a custom `Filter` is a Servlet bean auto-registered by Spring Boot into the **container chain**, and is also added via `http.addFilterBefore(...)` to the **Spring Security chain**, the same logic can run twice or execute across two different lifecycles.

How to handle it:
1. Determine whether the filter is meant to be container-managed or a security filter.
2. If the filter should reside only in the Spring Security chain, prevent automatic registration as an outer servlet filter (for example, disable the bean's servlet registration with `FilterRegistrationBean#setEnabled(false)` when appropriate).
3. Inspect the filter name separately in the security inventory and in servlet filter registrations.
4. Test with a real request and count executions rather than relying solely on the initialized filter list.

`OncePerRequestFilter` helps avoid multiple runs across certain dispatches/lifecycles, but it is not a substitute for **registering in the right place** or properly handling `ASYNC`/`ERROR` dispatches.

## 8. Reading HTTP Symptoms to Narrow Down the Chain

### Case A: API Returns 302 Instead of 401

**Expected:** Unauthenticated `GET /api/orders` returns HTTP 401 from the API chain. **Actual:** 302 redirect to `/login`.

Check in order:
1. Does `/api/orders` actually match the API chain's `securityMatcher("/api/**")`?
2. Is there a catch-all chain ordered before the API chain?
3. Does the API chain configure `httpBasic` or `oauth2ResourceServer` matching the request type?
4. Is a custom `AuthenticationEntryPoint` redirecting to login?
5. Does the actual request have a `contextPath`, `servletPath`, or proxy rewrite different from the assumed path?

If a catch-all `formLogin` chain is selected first, API rules in a later chain **never run**. Fix by correcting chain order and testing both anonymous and authenticated requests.

### Case B: API Bearer Token “Is Not Processed”

Possible causes:
- The request matched a chain without `oauth2ResourceServer(...)`, so `BearerTokenAuthenticationFilter` is absent in that chain.
- The token was sent via the wrong source (query/cookie/header depending on resolver configuration).
- The resolver found the token, but JWT decoder/introspection rejected it (issuer, signature, expiry, audience).
- Authorization denied the request for missing scope/authority despite a valid token.

**Diagnose by layer:** chain selected → filter present → token extraction → authentication → authorization. Do not fix by enabling every token source or relaxing to `permitAll`.

### Case C: 403 Even Though Authenticated

There are at least two distinct groups of causes:
- `CsrfFilter` rejected an unsafe request with a missing or invalid CSRF token.
- `AuthorizationFilter` or method security denied access due to missing role/scope/permission for the resource.

A `403` response alone is **not enough** to identify the group. Check HTTP method, matcher, filter chain, logger, authentication state, and test case. If only POST fails in a web session app, check CSRF first. If GET `/api/admin/report` with a USER account fails with 403, check the `hasRole("ADMIN")` rule.

### Case D: Custom Filter Does Not Run

The chain matcher may not match; the custom filter may only be added to another chain; an earlier filter may have short-circuited the request; or the custom filter may be registered in the container chain at an unexpected order. Read the per-chain inventory and TRACE the request instead of blindly adding the same filter to every chain.

### Case E: Security Headers Are Missing

Check:
- Did the request go through `FilterChainProxy`?
- Did a chain match, or was it bypassed by `web.ignoring()` / a container rule?
- Is `HeaderWriterFilter` present and executed on the response?
- Does the filter write the header for that response type and HTTP scheme (e.g., HSTS only on HTTPS)?
- Did a CDN/reverse proxy alter headers or serve the response before reaching the backend?

**`permitAll` does not mean skipping headers.** If static resources still need CSP/nosniff (per policy), ensure requests pass through an appropriate chain.

### Case F: Spring MVC Returns 404, Mistaken for Missing Chain

If an anonymous request to `/unknown` is redirected to `/login` by the web chain, the chain **already** processed the request before MVC. Once authenticated, the same `/unknown` may return 404 because no handler is found. This is not a chain-matching bug.

### Case G: Request Rejected Before Matching

Spring Security's `HttpFirewall` can reject certain requests with unusual URLs (encoded slashes, semicolons, or disallowed characters/paths depending on firewall/config) via `RequestRejectedException`. Do not “fix” every such error by loosening the firewall so the matcher starts matching; evaluate the URL and threat model, and test normalization across proxies/containers. When the firewall rejects a request, do not assume `AuthorizationFilter` ran.

## 9. Verification Scenarios with MockMvc

This is a practical test suite in a Spring Boot project with `spring-boot-starter-test`, `spring-security-test`, and the `SecurityConfig`/`DemoController` classes from Section 4. HTTP Basic tests **go through the real filter** with headers built from test credentials; do not use `@WithMockUser` to prove the Basic filter checked passwords.

File `SecurityChainSelectionTests.java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainSelectionTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiUsesApiChainAndIsAccessible() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousApiGetsHttpBasicChallenge() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Basic")));
    }

    @Test
    void apiBasicCredentialsAuthenticate() throws Exception {
        mvc.perform(get("/api/orders")
                .with(httpBasic("alice", "demo-test-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("orders"));
    }

    @Test
    void apiRoleRuleDeniesOrdinaryUser() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("alice", "demo-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWebGetsLoginRedirect() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void similarPrefixDoesNotUseApiChain() throws Exception {
        mvc.perform(get("/apiary"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Run with Maven:

```bash
mvn -Dtest=SecurityChainSelectionTests test
```

Or with Gradle:

```bash
./gradlew test --tests SecurityChainSelectionTests
```

All six tests are expected to PASS with the Section 4 setup. **Do not assume JUnit prints application stdout in a fixed format**: test runners report results differently. These tests verify the characteristic HTTP behavior of the selected chain and authentication/authorization, but if two chains happen to produce identical responses, **status alone does not prove chain identity**. Add TRACE logs or inspect `getFilterChains()` to prove the filter inventory when stronger evidence is required.

### 9.1. Why Should HTTP Basic Tests Not Rely Only on @WithMockUser?

`@WithMockUser` / `with(user("alice"))` injects a mocked `Authentication` for the test, which can bypass username/password verification in `BasicAuthenticationFilter`. It is useful for testing authorization, but **does not prove the real Basic filter is present or working**. Likewise, for a Resource Server, `with(jwt())` mocks JWT authentication and **does not test real JWT signature decoding**.

When diagnosing a specific authentication filter, test all of:
- A request **without credentials**.
- A request **with real protocol headers/credentials**.
- Invalid credentials.
- Valid credentials lacking authority.
- A route outside the chain's matcher to prove the chain boundary.

### 9.2. Testing Chain Inventory and Order

You can write a unit/integration test that accesses the `FilterChainProxy` bean and iterates `getFilterChains()`:
- The number of chains in the context matches expectations; note that libraries or test profiles may add extra chains.
- The API chain's matcher precedes the **catch-all** web chain.
- The API filter list contains `BasicAuthenticationFilter`, and the web list contains `UsernamePasswordAuthenticationFilter`.
- If the app uses Bearer tokens, the corresponding chain contains `BearerTokenAuthenticationFilter`.
- No wrong authentication filter is placed inside a chain that does not accept that credential type.

Avoid hardcoding an **entire** list of filter class names and exact order from one version as a strict golden snapshot. Assert only key invariants; Spring Security upgrades may legitimately add or change filters.

### 9.3. Explicit Negative Tests for Requests Without a Chain

If you intentionally build narrow-scoped chains **without a fallback**, create a test endpoint and invoke it through the full MockMvc filter chain to verify whether it is protected. **Do not** leave sensitive endpoints outside all chains. An anonymous test request to a protected URL returning 200 is a signal to investigate, though if the controller or chain uses `permitAll` or has no security requirement, 200 alone is not enough to conclude why.

For production deployments, decide **which chain protects every critical request**, then test across the URL × method × user role matrix.

## 10. Diagnostic Workflow for Multiple SecurityFilterChains

A time-saving workflow:

1. **Identify the actual HTTP request:** method, path, servlet context, dispatcher type, scheme, proxy rewrite. Never log raw `Authorization`/`Cookie`.
2. **List security chains:** call `FilterChainProxy.getFilterChains()` or read chain-build logs; record matchers and order.
3. **Find the first matching chain:** inspect TRACE logs for the request; watch firewall behavior and path-matching rules.
4. **Read the selected chain's filter inventory:** is the required filter present? Are there custom filters? Is the order sensible?
5. **Separate authentication from authorization:** were token/credentials extracted and verified? Afterward, were roles/scopes sufficient?
6. **Check entry point / access denied behavior:** do 401, 302, and 403 match the API/web chain?
7. **Check HTTP method / CSRF:** GET succeeding while POST returns 403 may be CSRF, not the wrong chain.
8. **Check MVC routing:** passing security and getting 404/405 is at the handler/method layer, not an absence of filters.
9. **Check servlet filter registrations outside Spring Security:** duplicate filters, order, proxy headers, error dispatches.
10. **Run regression tests:** each matcher boundary must have at least one matching and one non-matching request; test both anonymous and authenticated cases.

The goal is producing evidence: **“request X selected chain #n, with filters F1..Fk; filter G authenticated/rejected for reason Y; authorization returned result Z”**, rather than “Spring Security didn't run”.

## 11. Path Matching and HTTP Firewall: Corners That Cause Wrong Conclusions

### 11.1. URLs Containing Query Parameters

`securityMatcher("/api/**")` matches HTTP paths according to matcher semantics, not by searching raw strings across the entire URL. A query like `?next=/api/admin` **does not turn** `/dashboard` into an API route. At the same time, proxies or containers may normalize URLs before Spring Security sees the request.

If writing a custom `RequestMatcher`, do not use `request.getRequestURI().contains("/api")` directly as security logic; you must account for context path, servlet path, pathInfo, URL decoding, and the HTTP firewall. Prefer built-in Spring Security/MVC matchers when appropriate.

### 11.2. /api/** vs. /apiary

`/api/**` represents a path structure, not an unconditional string prefix check for `"/api"`. `/apiary` is a different path. When encountering unusual routes, add negative tests such as `/apiary` to verify matchers are not overly broad.

### 11.3. Forward, Error, and Async Dispatches

Servlet containers have multiple dispatcher types: `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. Depending on filter registration settings and each filter's behavior, a request may traverse different dispatches. Do not conclude from a single log line that a filter “did not run” across every phase. Verify dispatcher types, `OncePerRequestFilter` lifecycle behavior, and security for error routes/async callbacks.

### 11.4. Context Path and Servlet Path

If an application runs under context path `/app`, an external URL `/app/api/orders` may correspond to the security-matched path `/api/orders` depending on matcher/Servlet mapping. Do not blindly write `securityMatcher("/app/api/**")` by copying the raw browser URL; verify which servlet path or path-within-application the matcher reads.

### 11.5. When Using PathPattern or MVC Matchers

Spring Security 6 provides several mechanisms to select `RequestMatcher` implementations based on the MVC/Servlet environment and configured matcher APIs. Do not compare a handwritten `startsWith` matcher with an MVC matcher and assume identical behavior. With multiple servlets or custom mappings, you may need to configure explicit matchers of the appropriate type and test servlet paths separately.

**Security diagnosis must not loosen matchers or the firewall just to get the desired status.** The right fix is clearly defining URL scope, testing path variants, and keeping an appropriate fallback chain.

## 12. Anti-Patterns and Fixes

### Anti-pattern A: Catch-All Before a Specialized Chain

```java
// ANTI-EXAMPLE:
@Bean
@Order(1)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
```

With this setup, the catch-all web chain comes first. The later API chain may **never be selected**. Fix: place the narrow-matcher API chain first and the catch-all web chain after it. If intending to use OAuth2 Resource Server, you also need proper `JwtDecoder`/issuer config and real JWT tests; this snippet only illustrates the **chain ordering error**, not a standalone runnable config.

### Anti-pattern B: Confusing securityMatcher with Authorization requestMatchers

```java
// Wrong intent if you want an independent API chain:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().permitAll());
```

This code **does not create a separate security chain for /api**. It only defines rules for the current chain. If the application also has a separate API chain bean, you must inspect each bean's matcher and order. Fix at the **chain-splitting level**, not just the rule level.

### Anti-pattern C: Diagnosing by Disabling Security

To “make testing easier”, a developer uses `web.ignoring()` or removes filters for the request, sees the endpoint return 200, and concludes the controller is fine. This **does not prove the security config is right** and can strip CSP/HSTS/CSRF. Use test users/tokens, debug/TRACE in a test environment, and keep intentional bypasses clearly separated.

### Anti-pattern D: Custom Filter Acting as Both Servlet Filter and Security Filter

A `@Component` filter can be auto-registered by Spring Boot in the container and then manually added to the security chain. Write a test counting executions and check registrations; do not attempt to solve it merely by tweaking `@Order` on the bean.

### Anti-pattern E: Logging Full Tokens to Inspect a Filter

Printing `Authorization: Bearer`, `Cookie: JSESSIONID`, or raw JWTs to “see what the filter saw” creates a leak vector. Instead log **filter name, redacted route, safe request ID, auth type, and outcome**, never credentials.

### Anti-pattern F: Looking Only at HTTP Status

The same 403 can come from CSRF or authorization. The same 302 can come from form login or a custom redirect. The same 404 can occur after security filters ran properly. Conclusions must be backed by **chain selection + filter inventory + runtime trace + tests**.

## 13. Investigation and Acceptance Checklist

- [ ] Confirm the `springSecurityFilterChain` bean is registered in the Servlet container via `DelegatingFilterProxy`; know where it is configured/registered.
- [ ] List all `SecurityFilterChain` beans with matchers and order, without guessing from bean names or code order.
- [ ] Place narrow-matcher chains before catch-all chains, with tests that detect a catch-all swallowing the API.
- [ ] Distinguish `securityMatcher` (selects chain) from `requestMatchers` inside `authorizeHttpRequests` (sets authorization rules).
- [ ] For a specific request, identify the **first matching** chain; do not combine filters from other chains.
- [ ] Inspect `getFilters()` on the selected chain; confirm Basic, Bearer, Form, CSRF, or custom filters are present per contract.
- [ ] Use controlled `FilterChainProxy` logging in dev/test; never enable verbose credential-exposing logs in production.
- [ ] Test at least one positive and one negative URL per matcher, including lookalike paths such as `/apiary`.
- [ ] Test anonymous, valid credentials, invalid credentials, and insufficient role/scope separately; distinguish 401, 302, and 403.
- [ ] Test GET and unsafe methods; do not assume 403 is authorization when it could be CSRF.
- [ ] Check servlet context/path, proxy rewrites, dispatcher types, and firewall if requests do not match as expected.
- [ ] Check for duplicate custom filter registrations across the container and security chain.
- [ ] Route static/public resources through an appropriate chain if headers are required; do not drop Spring Security filters unintentionally.
- [ ] For Resource Server, do not use `with(jwt())` to prove the decoder verified a real signed JWT.
- [ ] Evaluate filter order using Spring Security mechanisms, not only `@Order` on a servlet filter bean.
- [ ] Never expose filter inventories or traces on public endpoints, and never log raw tokens, Cookies, or session IDs.
- [ ] If any route matches no chain, verify whether that is an intentional decision or a protection gap.

**Conclusion:** When diagnosing Spring Security Servlet, start from **`FilterChainProxy`**, list **`SecurityFilterChain` instances in order**, find **the first matcher matching the request**, and then examine **the filter list and runtime behavior** of that specific chain. `securityMatcher` decides which chain a request enters; `authorizeHttpRequests().requestMatchers(...)` assigns permissions **inside that chain**. Combine inventory, TRACE logs, MockMvc, and real HTTP checks to distinguish wrong chains, missing filters, authentication failures, CSRF, authorization 403, and MVC 404 with hard evidence.
