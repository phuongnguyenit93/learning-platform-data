# Adding Filters When Needed and Controlling Position and Scope

## 1. Problem Statement: Why Can a Functionally Correct Filter Still Cause Security Bugs?

In a Spring Security Servlet application, every HTTP request passes through multiple filters before reaching a controller. A filter can read headers, verify information, attach data to the request, log activity, reject requests, or process responses. When adding a new filter, **its position in the chain** and **which requests it runs on** are just as important as what it does.

For example, suppose a team wants to tag authenticated requests accessing `/api/private/**` so downstream components can inspect the tag:

- If the filter runs **before authentication**, it cannot yet trust `SecurityContext` to hold a real user.
- If the filter runs **after authorization**, it only tags requests that passed authorization; 401/403 requests rejected earlier will never reach that filter.
- If the filter is registered in both the **Servlet container** and `SecurityFilterChain`, it may run twice or in an unexpected order.
- If the filter accidentally applies to `/api/public/**`, `/site/**`, login, health checks, or CORS preflight, it can break flows that never needed it.
- If the filter rejects access improperly, 401/403 responses and exception handling may violate the intended design.

Therefore, the right approach is: **confirm a filter is truly needed → pick placement based on available data → restrict scope at the right layers → test both requests that must run and requests that must not run**.

This lesson focuses on **Spring Security Servlet with `HttpSecurity`, `SecurityFilterChain`, and `OncePerRequestFilter`**, using Java 17+ and Spring Boot 3.x / Spring Security 6.x. For WebFlux, use `SecurityWebFilterChain`, `ServerHttpSecurity`, and `WebFilter`; the Servlet classes in this lesson do not apply directly.

## 2. Understanding the Filter Chain Layers Before Adding a Custom Filter

Simplified flow of an HTTP request:

```text
Browser / HTTP client
        |
        v
Servlet container filter chain
        |
        +-- Servlet Filters registered by container/Boot
        |
        +-- DelegatingFilterProxy ("springSecurityFilterChain")
                  |
                  v
             FilterChainProxy
                  |
                  +-- selects FIRST matching SecurityFilterChain
                  |       |
                  |       +-- SecurityContext / headers / CSRF ...
                  |       +-- authentication filters
                  |       +-- anonymous processing filters
                  |       +-- ExceptionTranslationFilter
                  |       +-- AuthorizationFilter
                  |       +-- custom filter (if placed here)
                  |
                  v
             DispatcherServlet -> Controller
```

**Distinguish accurately:**

- `DelegatingFilterProxy` bridges the Servlet container's filter chain to the Spring bean `springSecurityFilterChain`.
- `FilterChainProxy` manages `SecurityFilterChain` beans and picks **the first chain with a matching RequestMatcher**; it does not stack every matching security chain together.
- Each `SecurityFilterChain` holds an ordered list of filters. Two chains can differ in authentication, CSRF, CORS, authorization, and custom filters.
- `AuthorizationFilter` enforces HTTP request authorization decisions when using `authorizeHttpRequests`.
- A filter placed **before** another filter will not see results produced by that downstream filter. A filter placed **after** another filter may never run if the upstream filter already terminated the request or threw an exception.

For this reason, do not infer placement merely from a custom filter's name or blindly copy `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` from another tutorial.

### 2.1. Key Landmarks for Choosing Placement

The diagram below illustrates a common **relative** order, not an immutable list of every filter across every configuration:

```text
SecurityContextHolderFilter
        |
exploit protections: CORS / CSRF / headers per config
        |
authentication filters (e.g., BasicAuthenticationFilter)
        |
AnonymousAuthenticationFilter
        |
ExceptionTranslationFilter
        |
AuthorizationFilter
        |
controller / Servlet
```

Specific applications also include filters for form login, logout, OAuth2, sessions, request cache, and more. The actual order is determined by the enabled configuration. Enable appropriate log levels only in development environments to observe the real chain.

Ask yourself before adding a filter:

1. Does it need to read `Authentication` or the user's roles? If so, place it after the relevant authentication mechanism has run.
2. Does it need to observe the authorization outcome? If so, place it **after `AuthorizationFilter`**, understanding that denied requests will not reach it.
3. Does it need to make access-denial decisions itself? Prefer `AuthorizationManager` then; if a filter must throw security exceptions, understand `ExceptionTranslationFilter` placement and 401/403 handling.
4. Is it already a built-in Spring Security protection? If so, configure the built-in DSL instead of rebuilding a filter.
5. Is it technical HTTP processing independent of the security chain (e.g., gateway tracing metadata) or logic tied to security context? The answer determines whether to use a standalone Servlet filter or a security filter.

## 3. When to Add a Filter vs. Use Another Extension Point

| Need | Usually appropriate extension point | Why |
| --- | --- | --- |
| Enable HTTP Basic, OAuth2 Resource Server, form login, CORS, CSRF, security headers | Built-in `HttpSecurity` DSL | Spring Security already manages ordering, exception integration, and standard behavior. |
| Authorization by role, authority, endpoint, tenant | `authorizeHttpRequests` with `AuthorizationManager`, or method-level security | Authorization rules belong in the authorization layer, easier to test and audit. |
| Custom protocol authentication genuinely lacking built-in support | `AuthenticationFilter` or custom filter collaborating with `AuthenticationManager`/`AuthenticationProvider` | Requires clear placement and authentication contract; do not cram token verification into an ad-hoc filter. |
| Mark/audit requests after passing authorization | Custom filter after `AuthorizationFilter`, placed in the matching chain | Can use `SecurityContext` and knows the request passed the HTTP authorization gate. |
| Record correlation IDs even for requests rejected before entering the security chain | Servlet filter/gateway registered before the security proxy | Goal must cover 401/403 responses and filters ahead of controllers. |
| Transform controller errors into JSON | `@RestControllerAdvice` / `ProblemDetail` | This is MVC handling; no custom filter needed to wrap every exception. |
| Pre/post-controller logic needing MVC handler metadata | `HandlerInterceptor` or MVC advice | Has clearer controller/handler context than a Servlet-level filter. |
| Input constraints, business validation | Bean Validation, services, and domain layer | Filters are not the default home for every business rule. |

A new filter adds another point that can impact security and performance. In particular, if the goal is simply "read a JWT and populate `SecurityContext`", check `oauth2ResourceServer(...).jwt(...)` first. Reimplementing signature verification, expiration, audience, issuer, and error handling yourself usually lowers security.

## 4. Three Layers That Control Filter **Execution Scope**

### 4.1. `securityMatcher` selects the entire security chain

`http.securityMatcher("/api/**")` sets the condition for **the entire `SecurityFilterChain`** to apply to `/api/**` paths. If a request does not match, `FilterChainProxy` tries the next chain.

Example:

```java
http.securityMatcher("/api/**");
```

A filter added to this chain **does not** run in the fallback chain serving `/site/**`. However, Servlet container filters independent of Spring Security may still run for both.

### 4.2. `requestMatchers` inside `authorizeHttpRequests` selects authorization rules

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/private/**").authenticated()
    .anyRequest().denyAll()
);
```

These matchers only decide **permissions** for requests already routed into the chain. They **do not automatically restrict** whether a custom filter in the same chain is invoked on public paths. If a filter sits before or after `AuthorizationFilter` and a public request has `permitAll`, the filter can still run for that request.

Therefore, **`permitAll()` does not mean "skip all filters"**. By contrast, `web.ignoring()` bypasses security filters altogether, stripping protections such as security headers. For public endpoints, usually keep them in the chain and use `permitAll()`.

### 4.3. `shouldNotFilter` narrows a custom `OncePerRequestFilter` itself

If a filter applies only to a narrow subset under `/api/**`, implement `shouldNotFilter(HttpServletRequest)` to return `true` to **skip** requests. This avoids running unnecessary logic even when the chain is broader.

Example:

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return !request.getServletPath().startsWith("/api/private/");
}
```

This rule applies to endpoints starting with `/api/private/` in the demo app, and skips `/api/public/**`. For apps with servlet mappings, multiple contexts, or complex matching needs, prefer a `RequestMatcher` designed/tested consistently with how Spring Security resolves URLs rather than relying on `contains(...)` or overly broad prefixes.

**Summary:** `securityMatcher` selects the chain, `requestMatchers` selects permission rules, and `shouldNotFilter` narrows where a custom filter runs inside the selected chain. These three do not replace one another.

## 5. Choosing `addFilterBefore`, `addFilterAfter`, `addFilterAt`

`HttpSecurity` provides insertion relative to **anchor filters**, without requiring you to compute "index 13" manually.

| API | Meaning | When to use |
| --- | --- | --- |
| `addFilterBefore(custom, AnchorFilter.class)` | Insert filter before the specified anchor. | Need to prepare data for the downstream anchor, or intervene before a check. |
| `addFilterAfter(custom, AnchorFilter.class)` | Insert filter after the specified anchor. | Need data/results produced by earlier filters. |
| `addFilterAt(custom, AnchorFilter.class)` | Place custom filter at the position reserved for a standard filter. | Only when genuinely altering how a standard mechanism works and the original filter is handled; do not assume it "automatically removes the old filter". |

**Goal-based examples:**

- To record requests that **already passed HTTP authorization**, you can use `addFilterAfter(custom, AuthorizationFilter.class)`.
- To run a custom check **before `AuthorizationFilter`** once `Authentication` is present, analyze `addFilterBefore(custom, AuthorizationFilter.class)`. This spot is normally after `ExceptionTranslationFilter` in common setups, though you must still verify the actual chain and exceptions.
- To create a new authentication type, place the filter in the authentication stage and integrate with `AuthenticationManager`/`SecurityContext`/entry point; never pick an anchor merely because it appeared in a blog post.
- To replace a standard filter at the same spot, prefer the official configuration DSL first. `addFilterAt` **is not a "complete replacement" guarantee** if the old mechanism still adds its own filter; remove/avoid duplicate registration via supported configuration.

**Position affects error handling:** `ExceptionTranslationFilter` primarily catches `AuthenticationException` and `AccessDeniedException` thrown **in the portion of the chain running after it**. If a custom filter throws those exceptions upstream of it, do not assume Spring Security will translate them into 401/403 properly. Design placement intentionally and write negative tests; for business errors, consider MVC or authorization instead of filters.

## 6. Java 17+ Example: Marking Private Requests After Authorization

Requirements:

- All `/api/**` requests belong to a high-priority **API security chain**.
- `GET /api/public/ping` allows public access.
- `GET /api/private/whoami` requires HTTP Basic login, after which the filter marks the request and stores the authenticated username in a **request attribute** for the controller to observe.
- `GET /site/home` belongs to the **fallback chain** and has no API filter.
- Unauthenticated API requests, forbidden paths, or public requests must not be marked by the filter.
- The example must keep CSRF and default HTTP protections enabled; do not disable protections just to make tests pass.

**Example limitations:** The `X-Demo-Filter: applied` header is only a learning/testing indicator, not a security proof for clients to trust. In real products, real auditing requires proper logging policies, data protection, and error handling. Sample accounts are for learning environments only.

### 6.1. Dependencies and Starter Application

A Spring Boot 3.x project with matching Gradle plugin/Java toolchain, using `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This snippet is the `dependencies` block in a Boot project that already has the Gradle plugin, **not a complete build file**. All following classes use package `demo.filterchain`.

File `src/main/java/demo/filterchain/FilterChainApplication.java`:

```java
package demo.filterchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterChainApplication.class, args);
    }
}
```

### 6.2. Writing a Narrowly Scoped `OncePerRequestFilter`

File `src/main/java/demo/filterchain/PrivateRequestMarkerFilter.java`:

```java
package demo.filterchain;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Example: only marks private requests that have passed HTTP authorization.
 * Do not use @Component or @Bean to avoid Boot auto-registering it in the container.
 */
public final class PrivateRequestMarkerFilter extends OncePerRequestFilter {
    public static final String REQUEST_PRINCIPAL =
            PrivateRequestMarkerFilter.class.getName() + ".principal";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getServletPath().startsWith("/api/private/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        // In this example, the filter is placed after AuthorizationFilter;
        // unauthorized requests are rejected before reaching here.
        String principal = authentication == null
                ? "not-available"
                : authentication.getName();

        request.setAttribute(REQUEST_PRINCIPAL, principal);
        response.setHeader("X-Demo-Filter", "applied");

        chain.doFilter(request, response);
    }
}
```

**Points to understand:**

1. `OncePerRequestFilter` reduces duplicate execution within **a matching dispatch pass**; it marks requests as filtered, though it does not promise "across the entire request lifecycle, including async/error dispatches, strictly once ever". Hooks `shouldNotFilterAsyncDispatch` and `shouldNotFilterErrorDispatch` serve specific roles when handling those dispatches.
2. `shouldNotFilter` returns `true` to skip. For `/api/public/ping`, the filter neither reads the context nor adds the header.
3. The filter **must not** be `@Component` or declared as a `Filter` bean in this example; Spring Boot can auto-register Servlet filter beans outside Spring Security, causing extra execution or wrong ordering.
4. `Authentication` is read from `SecurityContextHolder` after the authorization anchor; on allowed private requests, an authenticated identity is present. Do not treat `authentication.isAuthenticated()` alone as a substitute for authorization: anonymous tokens can also carry that flag depending on configuration.
5. `chain.doFilter(request, response)` passes control onward. Omitting this line blocks downstream filters/Servlets, unless the filter intentionally terminates the request and has already written a proper response.
6. In the example, only the username is stored in a request attribute on the same request; **never turn a client-supplied name into an identity**, and never put sensitive data into test headers.

### 6.3. Choosing the Right Chain and Filter Position

File `src/main/java/demo/filterchain/SecurityConfig.java`:

```java
package demo.filterchain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/private/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .addFilterAfter(
                new PrivateRequestMarkerFilter(),
                AuthorizationFilter.class
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/site/home").permitAll()
            .anyRequest().denyAll()
        );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("READER")
                .build()
        );
    }
}
```

Explaining each boundary:

- `@Order(1)` evaluates the `/api/**` chain first. If a request is `/api/private/whoami`, this chain is selected and `fallbackSecurity` does not run afterward.
- `securityMatcher("/api/**")` limits the scope of the entire API chain. `requestMatchers("/api/private/**").authenticated()` is an authorization rule **inside** that chain.
- `.addFilterAfter(..., AuthorizationFilter.class)` ensures the custom filter sits after `AuthorizationFilter` in the security chain order. If the request is unauthorized, the filter is not called in the normal flow because `AuthorizationFilter` rejects it first.
- `httpBasic(...)` is used in the example only for easy authentication testing. An app using Bearer/JWT should configure Resource Server and corresponding tests.
- `fallbackSecurity` **does not use `securityMatcher`**, so it handles all remaining requests and applies `denyAll` by default. If you omit a fallback, requests matching no `SecurityFilterChain` could pass through unprotected by Spring Security.
- The configuration does not call `csrf.disable()`. State-changing requests remain subject to default CSRF rules where applicable; the example only uses `GET`.

**Do not treat this example as a production credential-security template:** static passwords in source code are strictly for learning; real environments use secure identity and secret management, TLS, and proper access controls.

### 6.4. Controller Consuming the Marker Added by the Filter

File `src/main/java/demo/filterchain/DemoController.java`:

```java
package demo.filterchain;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("result", "pong");
    }

    @GetMapping("/api/private/whoami")
    public Map<String, Object> whoami(
            Authentication authentication,
            HttpServletRequest request
    ) {
        Object atFilter = request.getAttribute(
                PrivateRequestMarkerFilter.REQUEST_PRINCIPAL
        );
        return Map.of(
            "user", authentication.getName(),
            "filterApplied", atFilter != null,
            "principalAtFilter", atFilter == null ? "" : atFilter.toString()
        );
    }

    @GetMapping("/site/home")
    public String home() {
        return "site home";
    }
}
```

When authenticated user `reader` calls `GET /api/private/whoami`, the expected JSON contains these values:

```json
{
  "user": "reader",
  "filterApplied": true,
  "principalAtFilter": "reader"
}
```

JSON field order is not guaranteed because `Map.of` does not guarantee iteration order. To verify, assert by field name (e.g., JSONPath) rather than comparing a JSON string with a fixed order.

For `GET /api/public/ping`, the filter is skipped, yet the endpoint still passes through the API security chain and other protective filters in that chain. For `GET /site/home`, the filter is absent because the URL belongs to a different chain.

## 7. Required Testing: Both In-Scope and Out-of-Scope Paths

File `src/test/java/demo/filterchain/FilterPlacementTests.java`:

```java
package demo.filterchain;

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
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class FilterPlacementTests {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedPrivateRequestRunsFilterAfterAuthorization()
            throws Exception {
        mvc.perform(
                get("/api/private/whoami")
                    .with(httpBasic("reader", "demo-password"))
            )
            .andExpect(status().isOk())
            .andExpect(header().string("X-Demo-Filter", "applied"))
            .andExpect(jsonPath("$.user").value("reader"))
            .andExpect(jsonPath("$.filterApplied").value(true))
            .andExpect(jsonPath("$.principalAtFilter").value("reader"));
    }

    @Test
    void unauthenticatedPrivateRequestIsRejectedBeforeCustomFilter()
            throws Exception {
        mvc.perform(get("/api/private/whoami"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void wrongPasswordIsRejectedBeforeCustomFilter() throws Exception {
        mvc.perform(
                get("/api/private/whoami")
                    .with(httpBasic("reader", "wrong-password"))
            )
            .andExpect(status().isUnauthorized())
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void publicApiRequestSkipsCustomFilter() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("pong"))
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void fallbackChainDoesNotContainApiFilter() throws Exception {
        mvc.perform(get("/site/home"))
            .andExpect(status().isOk())
            .andExpect(content().string("site home"))
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void unknownApiRouteIsDeniedWithoutRunningFilter()
            throws Exception {
        mvc.perform(
                get("/api/not-allowed")
                    .with(httpBasic("reader", "demo-password"))
            )
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }
}
```

This is a Spring Boot integration test with MockMvc, requiring `spring-security-test` and Spring Security filters registered in MockMvc. `@AutoConfigureMockMvc` integrates registered filters under Spring Boot's defaults; if you build MockMvc standalone, attach the chain properly and retest.

Run from the root of a Spring Boot project with the wrapper:

```bash
./gradlew test --tests demo.filterchain.FilterPlacementTests
```

The expected result when configured properly is **6 tests PASS**. The lesson provides code and tests runnable in a compatible Boot project; "6 tests PASS" is the expected verification outcome when the learner runs the command, not a claim that the program was executed inside this document.

Test explanation table:

| Request | Authentication | Selected chain | Custom filter? | Expected status |
| --- | --- | --- | --- | --- |
| `GET /api/private/whoami` | Valid Basic | API | **Yes**, marks after authorization | 200 |
| `GET /api/private/whoami` | None | API | **No**, blocked earlier | 401 |
| `GET /api/private/whoami` | Invalid Basic | API | **No**, authentication failed | 401 |
| `GET /api/public/ping` | None | API | **No**, due to `shouldNotFilter` | 200 |
| `GET /site/home` | None | Fallback | **No**, filter not in chain | 200 |
| `GET /api/not-allowed` | Valid Basic | API | **No**, `denyAll` denies first | 403 |

**Distinguishing what is tested:** the unauthenticated private test proves placement after authorization; the public test proves path-based filtering; the site test proves scoping by `SecurityFilterChain`; the unknown-route test proves `anyRequest().denyAll()` is not accidentally bypassed by the custom filter.

Never test only a single successful request and conclude the filter is placed properly. The most dangerous bugs usually occur on paths where it **must not run**.

## 8. How to Inspect Filter Order in a Running Application

Besides tests, Spring Security can log the configured filter list when DEBUG logging is enabled at startup. Development-only config example, `src/main/resources/application.yml`:

```yaml
logging:
  level:
    org.springframework.security.web.DefaultSecurityFilterChain: DEBUG
```

Read log lines like `"Will secure ... with [...]"` to see which filters belong to each `SecurityFilterChain`. Confirm:

- `PrivateRequestMarkerFilter` appears only in the `/api/**` chain, not in the fallback chain.
- Inside the API chain, the custom filter appears after `AuthorizationFilter` as intended.
- There are no duplicate instances registered by both the Servlet container and Spring Security.
- Authentication mechanisms and HTTP protections are enabled as designed.

When you need to understand **which filters a request actually traverses**, enable appropriate Spring Security observability on a staging/test environment and inspect request logs; never enable verbose logging in production without evaluating risks of exposing tokens, cookies, credentials, or sensitive traffic.

Note: appearing in the startup list only proves filter configuration; it **does not prove** the filter runs for every URL or every dispatch type. End-to-end behavior must be verified with real HTTP tests and endpoint behavior.

## 9. Avoiding Double Filter Registration in Spring Boot

A common trap:

```java
@Component
public class MyFilter extends OncePerRequestFilter {
    // ...
}

// In SecurityConfig:
http.addFilterAfter(myFilter, AuthorizationFilter.class);
```

An object implementing `Filter` registered via `@Component` or `@Bean` can automatically become a **Spring Boot Servlet filter**. If you also add it to `HttpSecurity`, you have registered the filter in **two filter-chain systems**. Depending on dispatchers and `OncePerRequestFilter` tracking, this can cause duplicate execution, wrong ordering, or subtle bugs; never take "I only saw one log line" as conclusive proof there is no duplicate registration.

There are two options:

**Option A — simplest if no dependency injection is needed:** instantiate directly when building the security chain, like `new PrivateRequestMarkerFilter()` in the example. Do not annotate with `@Component` or declare a bean for that instance.

**Option B — if the filter needs dependency injection:** declare the filter as a Spring bean while explicitly disabling Servlet container registration. The snippet below **replaces how the filter is declared in the example**; do not use both options at once:

```java
@Bean
PrivateRequestMarkerFilter privateRequestMarkerFilter() {
    return new PrivateRequestMarkerFilter();
}

@Bean
FilterRegistrationBean<PrivateRequestMarkerFilter> disableServletFilter(
        PrivateRequestMarkerFilter filter
) {
    FilterRegistrationBean<PrivateRequestMarkerFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

Add the corresponding import:

```java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
```

And in `SecurityFilterChain`, inject the filter bean as a parameter of the configuration method and use it:

```java
.addFilterAfter(filter, AuthorizationFilter.class)
```

`FilterRegistrationBean#setEnabled(false)` prevents Boot from registering the bean as a standalone Servlet filter; `HttpSecurity` still adds that same instance into the security chain. Use this approach when injection is needed and verify there is no duplicate registration via configuration/logs/tests.

**Never add a filter with `@WebFilter`, Servlet `FilterRegistrationBean`, and `HttpSecurity` simultaneously unless you have an explicit design for each registration layer.**

## 10. Edge Cases to Decide Up Front

### 10.1. Filters performing authentication or authorization

The example only observes requests after authorization. If a custom filter **must reject** a request, do not casually do:

```java
if (!allowed) {
    throw new RuntimeException("blocked");
}
```

A generic exception like that can turn into a 500 error, leak details, or bypass authentication response contracts. If it is an access-control problem, prefer declaring an `AuthorizationManager` in `authorizeHttpRequests` or at the method-security layer. If the filter must produce an `Authentication`, use standard authentication components and place it before authorization; check interactions with anonymous, security context persistence, exception entry points, Basic/Bearer, and sessions.

For a filter that intentionally throws `AccessDeniedException`, place it in the section of the chain wrapped by `ExceptionTranslationFilter` if you expect 401/403 to be handled by the default mechanism. Do not assume every exception at every position is translated by Spring Security.

### 10.2. CORS preflight and public endpoints

`OPTIONS` preflight requests may not carry cookies or sessions. A custom filter requiring `Authentication` for every `/api/**` request can easily block preflight by mistake and cause browsers to report CORS errors. Use built-in `cors(...)` configuration, handle CORS in the right position, and scope custom filters to the endpoints/methods that truly need them. Never create a "bypass all security" rule just to fix an OPTIONS request.

Paths such as `/login`, `/logout`, OAuth2 callbacks, webhooks, actuator, and error handlers need separate review. If `securityMatcher` is too narrow, endpoints generated by a security filter itself may fall outside that chain and stop working as expected; URL rules for login/logout must align with chain scope.

### 10.3. Servlet dispatch types: REQUEST, ASYNC, ERROR, FORWARD

`OncePerRequestFilter` provides hooks to control whether it runs on async/error dispatches. By default it often skips some dispatches; never promise a filter runs strictly once across every situation. If you must protect or observe async processing, test thread hops, error dispatches, forwards, and already-committed responses.

`SecurityContextHolder` normally uses thread-bound context in Servlet apps. Across thread boundaries, authentication data or MDC does not automatically propagate to async work; use proper context-propagation utilities rather than storing `Authentication` in static fields or uncleaned ThreadLocals.

### 10.4. Reading the body, mutating requests or responses

Draining `request.getInputStream()` in a filter can prevent controllers from reading the body. To inspect payloads, design proper wrappers and size limits, and handle sensitive/streaming data carefully. Never log raw `Authorization`, `Cookie`, passwords, session IDs, or tokens. When modifying the response body or status in a filter, check whether the response is already committed.

### 10.5. Multiple SecurityFilterChains and precedence

If you have an `/api/admin/**` chain with `@Order(1)` and an `/api/**` chain with `@Order(2)`, admin requests enter **the first chain** and do not continue into the second. A filter added only to the broader API chain **does not automatically apply** to the admin chain matched earlier. Therefore, audit each chain independently: matchers, filters, default permissions, login endpoints, and fallbacks.

Lacking a catch-all fallback chain can let unmatched URLs **bypass Spring Security**. While this can be an intentional choice in certain infrastructures, normal applications should have a final chain covering everything with an explicit policy.

## 11. Design Process and Acceptance Test Suite

Before adding a filter to an application:

1. **Describe the requirement.** What event must the filter handle? What data does it need? Why can existing CORS/CSRF/authentication/authorization DSLs, interceptors, or services not fulfill it?
2. **Choose placement with justification.** Identify milestones completed before the filter runs: context, CSRF, authentication, authorization. Pick `addFilterBefore` or `addFilterAfter` relative to a specific filter.
3. **Define scope.** Explicitly list allowed URLs/methods/dispatchers; use `securityMatcher`, `requestMatchers`, and `shouldNotFilter` in their proper roles without conflating them.
4. **Register only once.** Decide whether the filter is a bean or an inline instance; verify Spring Boot auto-registration and container filters.
5. **Preserve request flow.** Call `chain.doFilter` at the right time; if rejecting, return the proper status and handle exceptions safely. Avoid silent drops or swallowing security exceptions.
6. **Test both directions.** Include cases where the filter must run, must not run, unauthenticated, insufficient permissions, CORS preflight, paths outside the chain, and error/async dispatches if relevant.
7. **Verify operations.** Inspect the filter list at DEBUG and request traces in a test environment; measure latency, check for sensitive logs, and assess deployment risks.

Sample acceptance matrix:

| Test category | Expected outcome |
| --- | --- |
| Protected path, valid account | Filter runs in right order, expected `SecurityContext` data is present. |
| Same path unauthenticated or bad credentials | 401 per authentication mechanism; post-authorization filter does not run. |
| Same path authenticated but lacking permissions | 403; filter after `AuthorizationFilter` does not run. |
| Public URL in the same chain | Matches policy; custom filter is skipped via `shouldNotFilter`. |
| URL outside the chain | Custom filter is not present in the selected chain. |
| Endpoint with no explicit allow rule | `denyAll` or defined fallback policy; never unexpectedly public. |
| CORS preflight, login, logout, callbacks | Not misblocked by custom filter; specific policies are tested. |
| Async/error dispatch if supported | No unexpected gaps or duplicate logic; context handled properly. |
| Startup configuration | Single registration in the intended system, exact position, no duplicate Servlet filter. |
| Integration, performance, and logging | Does not consume request body, leak tokens, add excessive latency, or corrupt responses. |

## 12. Common Mistakes

- **"Just put it before `UsernamePasswordAuthenticationFilter`."** This anchor does not fit every filter type or every authentication scheme. Choose based on which events must happen before/after.
- **Confusing `securityMatcher` with `requestMatchers`.** One selects the chain; the other selects authorization rules within the chain. Neither automatically restricts a custom filter by itself.
- **Believing `permitAll()` disables all filters.** It only allows the request past the authorization rule; CSRF, headers, and custom filters can still run.
- **Declaring the same filter as a bean and adding it to `HttpSecurity` without checking Boot auto-registration.** Easily causes duplicate runs or wrong ordering.
- **Relying on `OncePerRequestFilter` to conclude it can never run twice across any dispatcher.** Understand dispatch types and test in practice.
- **Placing a filter that needs user identity before authentication steps.** Principal data may be empty, anonymous, or untrusted.
- **Throwing security exceptions outside `ExceptionTranslationFilter`'s scope and expecting automatic 401/403 translation.** Results may differ from expectations.
- **Placing a filter after authorization and expecting it to log every 401/403.** Early-rejected requests never reach it; design a different observation point.
- **Using a custom filter instead of built-in authorization rules.** Permissions become hard to audit and easily conflict with `@PreAuthorize` or HTTP rules.
- **Missing a fallback chain.** Some URLs may remain unprotected.
- **Testing only the happy path.** Fails to catch filters misbehaving on public URLs, callbacks, preflight, or other chains.
- **Reading bodies or logging secrets in a filter.** Easily breaks controllers or leaks security data.

**Practical conclusion:** a custom filter is only "right" when you can prove **why it is needed**, **which milestone it runs before/after**, **which requests it runs on and which it skips**, and **that it creates no bypass around other security mechanisms**. Ordering and scope must be tested as part of the filter's own functionality.

## Reference Documentation

- Spring Security 6.5 — [Servlet Architecture, SecurityFilterChain and Adding Filters](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html).
- Spring Security 6.5 — [Java Configuration, Multiple SecurityFilterChains and securityMatcher](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html).
- Spring Security 6.5 — [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html).
- Spring Framework — [OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html).
- Spring Boot — [Servlet Filters and FilterRegistrationBean](https://docs.spring.io/spring-boot/reference/web/servlet.html).