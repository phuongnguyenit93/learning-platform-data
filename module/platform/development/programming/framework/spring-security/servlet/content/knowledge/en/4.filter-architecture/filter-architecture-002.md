# FilterChainProxy and Its Role in Orchestrating Security Chains

In **Spring Security for Servlet applications**, `FilterChainProxy` is the central component that selects **one security filter chain** (`SecurityFilterChain`) for each HTTP request, then runs the security filters belonging to the selected chain. It is the junction between the Servlet container's `Filter` mechanism and Spring Security's multiple security configurations.

This lesson explains the position of `FilterChainProxy`, how it selects a chain in order, how filters execute, its relationship with authorization rules, and how to verify it with examples. Understanding this mechanism helps avoid two dangerous mistakes: configuring a chain that fails to cover an endpoint needing protection, or letting an overly broad chain shadow a specialized chain.

## 1. Four components and their distinct responsibilities

| Component | Which layer? | Primary responsibility |
| --- | --- | --- |
| Servlet container `FilterChain` | Servlet API | Sequentially invokes registered servlet filters; eventually can forward the request to a servlet, such as `DispatcherServlet`. |
| `DelegatingFilterProxy` | Spring Web / bridge | A servlet `Filter` invoked by the container, but delegates processing to a `Filter` bean in the Spring `ApplicationContext`. |
| `FilterChainProxy` | Spring Security | Holds the list of `SecurityFilterChain`s, finds the first chain matching the request, coordinates that chain's filters, and works with `HttpFirewall`. |
| `SecurityFilterChain` | Spring Security | Defines a chain's matcher and the list of security filters that will run if the chain is selected. |

In a typical Spring Security Servlet configuration, the bean named **`springSecurityFilterChain`** is `FilterChainProxy`. `DelegatingFilterProxy` is registered on the servlet container side and delegates to this bean. Spring Boot normally sets up the registration for the application when Spring Security is present; non-Boot Servlet applications may need to register `DelegatingFilterProxy` via Servlet/`WebApplicationInitializer` configuration.

High-level processing flow:

~~~text
HTTP request
    |
    v
Servlet container filter chain
    |
    v
DelegatingFilterProxy
    |  looks up and delegates to bean "springSecurityFilterChain"
    v
FilterChainProxy
    |  HttpFirewall inspects / wraps request
    |  iterates through SecurityFilterChains in order
    |  selects the FIRST CHAIN where matches(request) = true
    v
Selected SecurityFilterChain
    |
    +--> Security filter 1
    +--> Security filter 2
    +--> ...
    +--> AuthorizationFilter (when configured accordingly)
    |
    v
Remaining original Servlet FilterChain
    |
    v
DispatcherServlet / endpoint
~~~

The diagram depicts the **happy path**. A security filter has the right to halt processing, write a response, throw an exception, or redirect. In that case, the request does not necessarily reach the controller. When no `SecurityFilterChain` matches, `FilterChainProxy` continues to the original servlet chain without applying the security filter list of any security chain; you must never assume by default that such a request is protected by Spring Security.

## 2. Why is a FilterChainProxy needed instead of registering each filter individually?

If every authentication, CSRF, session, exception handling, and authorization filter were registered independently with the Servlet container, managing ordering, mutual dependencies, and URL scopes consistently would be very difficult. Spring Security centralizes them in `FilterChainProxy`:

1. **Single coordination point:** The Servlet container only needs to call the Spring Security bridge; Spring manages the internal filters.
2. **Proper ordering:** Security-related filters run in the sequence constructed by Spring Security, such as loading the security context before making authorization decisions.
3. **Multiple scoped policies:** APIs can use HTTP Basic and stateless sessions, while web pages use form login and sessions, each group belonging to its own `SecurityFilterChain`.
4. **Request inspection/normalization:** `HttpFirewall` handles suspicious request path forms and provides an appropriate request for chain selection.
5. **Spring integration:** Filters can be configured through `HttpSecurity`, dependency injection, and other Spring mechanisms.

Therefore, **you should not manually register every Spring Security filter as a separate servlet filter**. They are already coordinated by `FilterChainProxy`. Having a custom filter both annotated with `@Component` so Spring Boot auto-registers it with the container and added via `http.addFilterBefore(...)` can cause the filter to run twice or in an unintended position.

`FilterChainProxy` does not replace the Servlet container, does not map controllers itself, and does not decide on its own who is allowed to access an endpoint. It selects the **filter chain**; deciding whether to allow a specific action belongs to filters such as `AuthorizationFilter` and authentication components.

## 3. SecurityFilterChain selection mechanism: first match

Each `SecurityFilterChain` has a `matches(HttpServletRequest)` method and a corresponding list of filters. Consider three ordered chains:

~~~text
1. apiChain       matcher: /api/**
2. adminChain     matcher: /admin/**
3. fallbackChain  matcher: any request
~~~

When the request is `GET /api/orders`, `FilterChainProxy`:

1. Checks `apiChain`'s matcher → **true**.
2. Selects **apiChain** immediately.
3. Does not evaluate `adminChain` or `fallbackChain` further to merge additional filters.
4. Executes `apiChain`'s filters in order.

When the request is `GET /reports`, the first two chains do not match; the fallback chain matches and is selected. When two matchers overlap, **only the first matching chain** is used; filters from all matching chains are not merged and executed.

The chain selection mechanism can be viewed in pseudocode:

~~~java
// Pseudocode illustrating chain selection behavior; not internal source code.
for (SecurityFilterChain candidate : securityFilterChainsInOrder) {
    if (candidate.matches(request)) {
        executeCandidateFilters(candidate, request, originalServletChain);
        return;
    }
}
continueOriginalServletChain(request);
~~~

`executeCandidateFilters` and `continueOriginalServletChain` here are merely descriptive names, **not callable APIs**. In practice, `FilterChainProxy` creates an internal forwarding mechanism over the filter list, such as a `VirtualFilterChain`.

### Standalone Java 17 simulation

The following example simulates solely the "first matching chain wins" principle and can compile without Spring. The `startsWith` function is only for simulation; **do not use this hand-written string logic to replace RequestMatcher in a real security application**.

~~~java
import java.util.List;
import java.util.function.Predicate;

public class FirstMatchingChainDemo {
    record Candidate(String name, Predicate<String> matcher) {}

    public static void main(String[] args) {
        List<Candidate> chains = List.of(
                new Candidate("apiChain",
                        path -> path.equals("/api") || path.startsWith("/api/")),
                new Candidate("fallbackChain", path -> true)
        );

        for (String path : List.of(
                "/api/public/ping", "/api/private", "/api2/private", "/dashboard")) {

            String selected = "NO CHAIN";
            for (Candidate chain : chains) {
                if (chain.matcher().test(path)) {
                    selected = chain.name();
                    break;
                }
            }
            System.out.println(path + " -> " + selected);
        }
    }
}
~~~

Save the code to `FirstMatchingChainDemo.java`, and run:

~~~bash
javac FirstMatchingChainDemo.java
java FirstMatchingChainDemo
~~~

Exact stdout:

~~~text
/api/public/ping -> apiChain
/api/private -> apiChain
/api2/private -> fallbackChain
/dashboard -> fallbackChain
~~~

If you move the fallback to the top of the list, every path selects fallback, so apiChain is never chosen. This is the classic ordering bug when configuring multiple `SecurityFilterChain`s.

## 4. Creating two security chains with HttpSecurity

The example below applies to **Spring Boot 3.x, Spring Security 6.x, Jakarta Servlet, and Java 17+**; this is code placed inside a Spring Boot project and cannot be run with `javac` alone without Spring dependencies. The API uses HTTP Basic and stateless sessions; the web pages have form login.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FilterChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().hasRole("API_USER"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/help").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Two `HttpSecurity` instances yield two independent `SecurityFilterChain`s.** `@Order(1)` is evaluated before `@Order(2)`. The API chain only takes effect for paths matching `/api/**`. The web chain **does not call `securityMatcher(...)`**, so by default it matches any request not already selected by an earlier chain, forming an explicit fallback.

Example URLs (assuming an empty context path, standard servlet mapping, and that the corresponding endpoints exist):

| Request | Selected chain | Rule in chain | Expected behavior if unauthenticated |
| --- | --- | --- | --- |
| `GET /api/public/ping` | `apiChain` | `permitAll()` | Enters endpoint; typically returns `200` if the controller succeeds. |
| `GET /api/private` | `apiChain` | `hasRole("API_USER")` | HTTP Basic entry point typically returns `401`. |
| `GET /dashboard` | `webChain` | `authenticated()` | Form login typically redirects `302` to the login page. |
| `GET /help` | `webChain` | `permitAll()` | Enters public endpoint. |
| `GET /api2/private` | `webChain` | `authenticated()` | Does not match `/api/**` pattern. |

With `hasRole("API_USER")`, Spring Security checks the `ROLE_API_USER` authority by default. If you want to check an authority by its exact name, you can use `hasAuthority("...")` with the appropriate name. An authentication provider and user accounts must be configured for real environments; Spring Boot may provide a default development user when no proper authentication is declared.

**Important point about defaults:** Once an application declares one or more `SecurityFilterChain` beans itself, do not rely on Spring Boot automatically adding a default chain to protect all requests. In standard configuration, the auto-configuration that creates the default chain backs off in favor of the application's configuration. You must ensure every endpoint needing protection is covered.

### How do securityMatcher and requestMatchers differ?

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

- `securityMatcher("/api/**")` answers: **is this chain selected for the request?**
- `requestMatchers("/api/public/**")` and `requestMatchers("/api/admin/**")` answer: **within the selected chain, which authorization policy applies?**
- `anyRequest()` is the fallback **within that chain**; it does not expand the `SecurityFilterChain`'s scope beyond `/api/**`.

There are two separate kinds of "first match": `FilterChainProxy` selects the **first matching SecurityFilterChain**; meanwhile `authorizeHttpRequests` applies the **first matching authorization rule** within the selected chain. Placing `requestMatchers("/api/**").permitAll()` before the `/api/admin/**` rule causes the admin rule to be shadowed inside the same chain, even though FilterChainProxy selected the right chain.

Matchers can inspect the HTTP method and other request details, depending on the `RequestMatcher` type. MVC-style, `PathPattern`-style, and Ant-style matchers across different Spring Security generations do not have identical semantics; especially when customizing the servlet path, identify the matcher type and test paths exactly as received by the application.

## 5. Inside the selected chain: filter ordering and forwarding

Once `FilterChainProxy` selects a `SecurityFilterChain`, it invokes the chain's security filters one by one via an internal `FilterChain`. Each filter has the general structure:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException {

    // Process before forwarding.
    chain.doFilter(request, response);
    // Process after downstream filter/servlet returns.
}
~~~

This is an **illustrative Servlet Filter method pattern**, requiring `jakarta.servlet.*` imports and a class implementing `Filter`. A filter may omit calling `chain.doFilter(...)` if it handles the response itself or rejects the request.

Some commonly encountered filters in Spring Security 6.x configurations (the actual list varies depending on enabled features and version):

| Filter | Role in the flow |
| --- | --- |
| `SecurityContextHolderFilter` or corresponding context management mechanism | Sets the security context for the request so downstream components access security information consistently. |
| `CsrfFilter` | Validates the CSRF token on requests requiring CSRF protection. |
| `UsernamePasswordAuthenticationFilter` | Processes form login when configured. |
| `BasicAuthenticationFilter` | Reads HTTP Basic credentials when configured. |
| `ExceptionTranslationFilter` | Translates `AuthenticationException`/`AccessDeniedException` thrown by downstream filters into the appropriate authentication entry point or access denied handler flow. |
| `AuthorizationFilter` | Enforces authorization decisions for the request according to `authorizeHttpRequests` configuration. |

The table describes **roles**, without claiming every filter exists in every chain or that the table order is the complete execution order. Authentication, exception handling, and authorization filters must be ordered appropriately as provided by Spring Security; do not arbitrarily alter ordering via manual Servlet filter registration.

A filter performing checks normally must call `chain.doFilter(...)` so the rest can run. Conversely, if authentication fails or authorization is denied, a filter may trigger an entry point/handler, write the response, and stop processing. Accordingly:

- `401 Unauthorized` typically means the request requires authentication credentials but has not been authenticated via the appropriate mechanism.
- `403 Forbidden` typically indicates the request met the authentication requirement but lacks sufficient permissions, or was rejected by another mechanism such as CSRF.
- `302 Found` may be a redirect to a form login page; this is common behavior for a chain using `formLogin()`.

Do not infer backwards **from status code alone** which chain `FilterChainProxy` selected. For instance, `403` could be caused by `CsrfFilter` stopping the request before authorization rules execute. Combine logging and tests to pinpoint the cause.

### Why does permitAll not mean skipping the chain?

If `/api/public/ping` matches `apiChain` and then the `permitAll()` rule, `FilterChainProxy` **still runs the selected security filter chain**. Security headers, CSRF, session/context, or custom filters can still participate depending on configuration; only that rule's authorization decision is to permit.

By contrast, `WebSecurityCustomizer` with `web.ignoring().requestMatchers(...)` excludes paths from the security filter mechanism (typically meant for resources that genuinely need no security processing). Do not confuse `ignoring()` with `permitAll()`: ignored paths do not receive the chain's security features. For public endpoints that still need security headers, configuring `permitAll()` inside an appropriate chain is usually preferred.

## 6. What does HttpFirewall do before selecting a chain?

`FilterChainProxy` works with `HttpFirewall` (the common default is `StrictHttpFirewall`) to inspect and wrap the request before selecting a chain. The goal is to prevent unusual path representations from causing security matchers and MVC/Servlet routing to interpret the path differently.

For example, paths containing semicolons, suspicious segments, or disallowed encoded characters can be rejected by the firewall with `RequestRejectedException` before reaching the controller. Which specific cases are rejected depends on the firewall configuration, servlet container, and Spring Security version. After processing, request/response wrappers can be cleaned up, restoring appropriate state for the remaining servlet filters.

What to do when a request is blocked: check the original URL, proxy policies, error logs, and firewall rules. **Do not broadly disable firewall checks just to make an unusual URL work**; if an exception needs to be configured, understand the risk and test equivalent path variations.

## 7. Adding a custom filter without running it twice

A practical need is adding a timing/tracing filter for the API chain. You can implement it using `OncePerRequestFilter`, then add an instance of the filter to `HttpSecurity` at an explicit position. The following example omits `@Component` on the filter to avoid Spring Boot automatically registering the filter additionally at the servlet container level:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiTimingFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(ApiTimingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMillis =
                    (System.nanoTime() - started) / 1_000_000;
            log.debug("API {} {} completed in {} ms",
                    request.getMethod(),
                    request.getRequestURI(),
                    elapsedMillis);
        }
    }
}
~~~

Insert this filter into the API chain defined in section 4 with the following call **before `return http.build()`**:

~~~java
http.addFilterBefore(
        new ApiTimingFilter(),
        org.springframework.security.web.access.intercept.AuthorizationFilter.class
);
~~~

This is an example of inserting before a filter whose order position is known to Spring Security. In practice, the insertion point must be chosen according to what information the custom filter needs: before authentication there is usually no principal yet; after authentication it can use the authenticated context; before authorization it can observe the request before it gets blocked. If configuring a different authentication mechanism, verify the filters and actual ordering built.

**Note on `OncePerRequestFilter`:** the name refers to a guarantee within a corresponding filter dispatch, not that a business-level HTTP request can only pass through the filter once across all async/error dispatches, proxies, and duplicate registrations. If the filter is a DI-managed Spring bean that Boot might auto-register in the servlet container, configure a `FilterRegistrationBean` to disable container registration for that filter when intending to use it solely inside a security chain.

Do not log Authorization headers, bearer tokens, passwords, cookies, or secrets. `getRequestURI()` may contain sensitive information in the path in some applications, so follow your actual logging policy.

## 8. Testing the selected chain

To give the Spring example in section 4 real endpoints, add a sample controller in the same application:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/private")
    public String privateApi() {
        return "private";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }

    @GetMapping("/help")
    public String help() {
        return "help";
    }
}
~~~

In a project with `spring-boot-starter-test`, `spring-security-test`, and MockMvc configured with Spring Security integration, test the behavior branches:

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
class FilterChainRoutingTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void firstMatchingChainControlsBehavior() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/private"))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/api/private")
                        .with(user("reader").roles("API_USER")))
                .andExpect(status().isOk());

        mockMvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

The assertions rely on **this exact two-chain configuration, the sample controller, unauthenticated GET requests, and MockMvc actually having the Spring Security filter**. When there are additional filters, custom entry points, context paths, controller behaviors, or exception handlers, the statuses may differ; update tests according to your application's contract. For `POST/PUT/DELETE` requests, handle CSRF properly in tests: a stateless API or `permitAll()` does not automatically disable `CsrfFilter`.

You can test with `curl` after running the Spring Boot application:

~~~bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/private
curl -i http://localhost:8080/dashboard
~~~

In the sample configuration, the first request typically returns `200` with body `pong`; the second typically returns `401` (HTTP Basic); the third typically returns `302` toward form login. These are conditional expectations, not stdout from a standalone Java program.

### Reading logs when the wrong chain is selected

When diagnosing, enable logging in development or test environments:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.intercept=TRACE
~~~

Depending on the version, log lines can show which request is being secured, which filters are invoked, or authorization details. Do not write assertions depending on internal log wording: log messages can change across versions.

Check in order: the path reaching the application **after the reverse proxy**, servlet context/servlet mapping, HTTP method, `RequestMatcher` type, `SecurityFilterChain` order, `securityMatcher` matcher, and then `requestMatchers` rules inside the chain. When 401/403 occurs, also check the authentication entry point, exception handling, and CSRF.

## 9. Configuration mistakes to recognize

### Mistake A: Only having an API chain, missing a fallback

~~~java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}
~~~

With only the bean above configured, a `/admin/panel` request does not match `/api/**`; `FilterChainProxy` applies no security filters from this chain. If there is no other chain, that endpoint is **not protected by a Spring Security filter chain**, even though the configuration contains `anyRequest().authenticated()`. You must add an appropriate fallback or design a chain that protects the entire application.

### Mistake B: Broad chain placed before narrow chain

~~~java
// Anti-pattern in ordering:
@Order(1)  // chain with any-request matcher
@Order(2)  // chain with only /api/** matcher
~~~

The snippet above is **annotated pseudocode**, not a valid Java class. The first chain is always selected; the API chain behind it never gets a chance to run. Place specialized chains first and the fallback chain last, and write tests confirming URLs in both scopes.

### Mistake C: Placing an authorization rule for a URL outside the chain's scope

~~~text
securityMatcher("/api/**")
    authorize:
        /admin/** -> hasRole("ADMIN")
        anyRequest -> authenticated()
~~~

For an `/admin/users` endpoint outside `/api/**`, the `/admin/**` rule in the API chain has no effect because that chain is never selected. Fix this in the chain selection scope or arrange another chain with the corresponding rule.

### Mistake D: Assuming permitAll skips security filters

`permitAll()` only changes the authorization decision for the matched rule. It does not guarantee that CSRF, custom filters, or other HTTP policies stop running. For example, a `POST` request to a public URL may still return `403` due to a missing CSRF token when CSRF protection is active.

### Mistake E: Registering the same custom filter in two places

Adding a custom filter to a security chain while also letting Boot auto-register it as an independent servlet filter can cause duplicate processing, duplicate logs, or incorrect positioning. Choose the registration mechanism explicitly. If a container-level filter is needed, understand its impact on all requests, including requests outside security chains.

### Mistake F: Modifying URLs or relaxing the firewall to make a matcher match

If a matcher does not match due to context path, servlet mapping, proxy rewrite, or URL encoding, identify the **actual request** and use an appropriate matcher. Avoid stripping paths manually, decoding arbitrarily, or disabling `StrictHttpFirewall` broadly.

## 10. Self-check exercises

**Exercise 1.** Chains in order: `apiChain("/api/**")`, `healthChain("/actuator/health")`, `fallbackChain(any)`. Which chain does `/actuator/health` enter?

**Answer:** `healthChain`. The API chain does not match, `healthChain` matches and stops the search, without running `fallbackChain`'s filters. If `fallbackChain` were placed first, the result would become `fallbackChain`.

**Exercise 2.** There is only `securityMatcher("/api/**")`, with `anyRequest().denyAll()` inside. Is `/reports` blocked by that `denyAll()` rule?

**Answer:** No, because the chain does not match the request. `denyAll()` only takes effect within the selected chain. If there is no other chain, Spring Security does not enforce that rule for `/reports`.

**Exercise 3.** Request `POST /api/public/orders` matches `apiChain` with `permitAll()`, yet returns `403`. What could cause this?

**Answer:** It could be due to a missing or invalid CSRF token when `CsrfFilter` is enabled, or another filter or specific configuration. `permitAll()` does not remove all security filters, so inspect the actual filter chain and logs before concluding the matcher is wrong.

**Exercise 4.** A custom filter is declared with `@Component` and also added to the chain via `addFilterBefore`. Why might logs appear twice?

**Answer:** Spring Boot can register the `Filter` bean directly with the Servlet container, while Spring Security also invokes that filter inside its chain. Avoid duplicate registration or disable auto-registration at the container level if you only want the filter inside a security chain.

**Exercise 5.** Two `SecurityFilterChain`s both match `/api/private`. Do the filters of both chains run?

**Answer:** No. `FilterChainProxy` selects the first matching chain in order and runs only that chain's filter list.

## 11. Checklist when reading or designing filter architecture

- Locate `DelegatingFilterProxy` / the `springSecurityFilterChain` bean and know where it routes requests into `FilterChainProxy`.
- List all `SecurityFilterChain` beans along with each chain's `@Order` and `securityMatcher`.
- Ensure specific chains precede broad chains; explicitly verify a fallback covers endpoints needing protection.
- Distinguish **chain selection** from **authorization rule selection**; both are order-based but operate at two different layers.
- Inspect every enabled filter and the placement of custom filters; do not register duplicates between the Servlet container and Spring Security.
- Test matching/non-matching URLs, HTTP methods, permissions, CSRF, context path, proxies, and 401/403/302 response mechanisms.
- Use controlled logging, keep `HttpFirewall` intact, and never infer security posture from a single status code.

**Key takeaway:** `DelegatingFilterProxy` is the bridge, `FilterChainProxy` is the **chain selector and coordinator**, `SecurityFilterChain` holds the filters to be executed, and filters such as `AuthorizationFilter` make authorization decisions according to configured rules. This model explains why **chain order and matcher scope are core parts of Servlet application security**.