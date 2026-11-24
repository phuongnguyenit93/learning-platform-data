# Handling Exceptions in Custom Filters and Preventing Duplicate Authentication — Spring Security Servlet

A custom authentication filter can work fine in isolated tests yet cause hard-to-diagnose failures once integrated into Spring Security: a single request gets its credentials checked twice, failed login returns 500 instead of 401, the filter writes an HTTP response yet the controller still runs, or the filter throws `AuthenticationException` and nothing catches it properly.

In **Spring Security Servlet / Spring MVC**, solving this requires understanding **filter placement**, **exception boundaries**, **single execution per request/dispatch**, and **registering filters in the Servlet container versus the Spring Security filter chain**. You cannot just add `try/catch` or extend `OncePerRequestFilter` and assume every case is solved.

This lesson builds around the principle: **each request enters only the right security chain, the filter attempts authentication only when needed, errors have a clear handler owner, responses are never written twice, and authentication context never leaks to another request**. Examples use Spring Security 6.x (Servlet), Spring Boot 3.x, and Java 17+ as an illustrative baseline; real projects must check current versions and support policies before deploying.

## 1. Distinguishing Authentication Errors from Application and Authorization Errors

Three categories of situations have distinct typical HTTP statuses and must not all be funneled into the same handler:

| Situation | Typical Exception or State | Usually Appropriate Response |
|---|---|---|
| Request carries no credentials for a login-protected resource | No valid `Authentication` yet | 401 or redirect to login depending on client type and `AuthenticationEntryPoint` |
| Credentials sent but invalid | `BadCredentialsException`, `AuthenticationException` | 401 or failure redirect/response decided by authentication filter/handler |
| Valid credentials yet lacking permission | `AccessDeniedException` or denied authorization decision | 403 for authenticated user |
| Request missing CSRF token when required | CSRF filter rejects before or within chain | Typically 403, never disguised as wrong password |
| Database, I/O, bug, null pointer, or external system failure | Appropriate `DataAccessException`, `IOException`, `RuntimeException` | Server error handled by the right layer; do not mask all failures as "wrong password" |
| HTTP response already committed yet code keeps writing | Response lifecycle bug | Avoid writing/redirecting twice; log and diagnose exact commit point |

**401 Unauthorized** means a valid authentication requirement has not been met. **403 Forbidden** means the request reached a permission denial decision, or a protective filter such as CSRF rejected it. The status name 401 is slightly confusing; it does not mean the request passed authorization and was denied.

Never return 403 just for a wrong password, and never turn every unexpected exception into 401. Beyond HTTP semantics, keeping this distinction sharp makes monitoring and incident investigation accurate.

## 2. Filter Chain: Where Are Exceptions Thrown?

On the Servlet stack, requests typically traverse:

```text
HTTP request
  |
Servlet container filter chain
  |
DelegatingFilterProxy ("springSecurityFilterChain")
  |
FilterChainProxy
  |
  +-- selects matching SecurityFilterChain in order
        |
        +-- SecurityContextHolderFilter / other filters
        +-- custom authentication filter (depending on addFilter... position)
        +-- ExceptionTranslationFilter
        +-- AuthorizationFilter
        +-- controller/service
```

**This is a conceptual diagram**, not a fixed list or order for every application. Actual filters depend on enabled features and configured order.

Crucially: **`ExceptionTranslationFilter` only catches exceptions thrown inside the downstream processing it wraps.** If a custom authentication filter sits **before** `ExceptionTranslationFilter` and throws `AuthenticationException` before calling downstream, do not assume the downstream `ExceptionTranslationFilter` will catch that exception.

There are two common patterns:

1. **The authentication filter handles its own errors.** For a custom filter directly extending `OncePerRequestFilter`, catch `AuthenticationException` raised by its own authenticate call and invoke `AuthenticationEntryPoint` or `AuthenticationFailureHandler` per flow.
2. **The filter inherits built-in authentication mechanics.** `AbstractAuthenticationProcessingFilter` and subclasses such as `UsernamePasswordAuthenticationFilter` come with framework-supported `unsuccessfulAuthentication` and `AuthenticationFailureHandler` branches.

Therefore, answer before writing code: **which filter throws this exception, which filters sit before/after it, and who owns the response?** Never assume "Spring Security catches every `AuthenticationException` everywhere".

## 3. Proper try/catch Boundaries: Wrap Only the Authentication Attempt

A very common anti-pattern:

```java
try {
    Authentication result = authenticationManager.authenticate(candidate);
    SecurityContextHolder.getContext().setAuthentication(result);
    filterChain.doFilter(request, response);
} catch (AuthenticationException exception) {
    response.sendError(401);
}
```

**This is a broken illustrative snippet**, missing variable declarations/imports. It places `filterChain.doFilter(...)` **inside** the filter's own authentication catch block. If a downstream filter or method security throws `AuthenticationException`, the custom filter can mistakenly catch it and report "wrong API key" even though authentication just succeeded.

A more controllable pattern is:

```java
Authentication verified;
try {
    verified = authenticationManager.authenticate(candidate);
} catch (AuthenticationException invalidCredential) {
    SecurityContextHolder.clearContext();
    authenticationEntryPoint.commence(request, response, invalidCredential);
    return;
}

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

try {
    filterChain.doFilter(request, response);
} finally {
    SecurityContextHolder.clearContext();
}
```

**This snippet illustrates structure**, not a complete filter. `candidate` must be an untrusted authentication request; `authenticationEntryPoint` must be configured; downstream errors are left to the appropriate downstream components instead of being misclassified as provider errors.

Key invariants to maintain:

- Catch strictly `AuthenticationException` arising **from the authentication attempt you own**.
- After writing an error response, **`return`**: do not invoke the rest of the filter chain if the request was rejected.
- Clear `SecurityContextHolder` on failure to avoid retaining bad context in the current scope, while remembering Spring Security also manages holder lifecycle cleanup.
- In a **stateless** filter, never save authentication into `HttpSession` just to "fix" a subsequent request missing credentials.
- In **stateful** login, successful authentication also requires a session strategy and `SecurityContextRepository.saveContext(...)` per the standard flow. Do not copy a stateless snippet and expect browsers to stay logged in across sessions.

### Never Catch Every Exception as BadCredentialsException

`catch (Exception ex) { throw new BadCredentialsException("invalid"); }` can mask database timeouts, coding bugs, or system outages. As a result, users keep retrying passwords, monitoring misses server failures, and operations cannot distinguish credential errors from availability outages.

If an external identity provider/service throws an infrastructure exception, consider `AuthenticationServiceException` or a dedicated exception at the right layer and let the handler produce a non-leaking response. However, **never force every error into 401**: the system may need 503/5xx when the provider is down. Standardize the decision per API contract and test it.

Never log raw passwords/API keys/tokens in catch blocks. Log only request correlation IDs, normalized error categories, timestamps, trusted known user IDs, and minimal operational context.

## 4. OncePerRequestFilter: What Scope Does "Once" Mean?

`OncePerRequestFilter` is a Spring Framework base class that avoids running `doFilterInternal(...)` multiple times **within the same matching dispatch**, by setting a request attribute marker indicating the filter already ran. It exposes hooks:

- `shouldNotFilter(HttpServletRequest)`: skips requests outside the filter's scope.
- `shouldNotFilterAsyncDispatch()`: controls participation in async dispatches; typically skipped by default.
- `shouldNotFilterErrorDispatch()`: controls error dispatch handling; typically skipped by default.
- `doFilterInternal(...)`: implements the logic for requests the filter handles.

**Do not misinterpret:**

- Once does **not** mean authenticating only once for the entire login session.
- Every **new HTTP request** may still need re-authentication, especially in stateless APIs.
- A single request can involve distinct `REQUEST`, `ASYNC`, or `ERROR` dispatches; configuration and the Servlet container affect whether the filter is invoked.
- If you create **two distinct filter instances**, filters with different names/markers, or two different security chains handling the same request independently, no "global" lock automatically prevents duplicate authentication.
- If you register a filter in two places, `OncePerRequestFilter` may suppress certain duplicates within one dispatch, yet **does not turn duplicate registration into a safe design**. Execution order, handlers, and cleanup can still go wrong.

### Scope of shouldNotFilter

When custom authentication applies only to `/api/secure/**`, do not inspect credentials on `/api/public/**`, `/login`, static assets, or health endpoints. Blindly checking every request can cause public pages to return 401 simply because a browser carried a stale header.

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return !request.getServletPath().startsWith("/api/secure/");
}
```

This is a **method fragment**. For complex apps, use Spring Security matchers suited to path/method/context-path and multiple-chain configs; do not treat naive `startsWith` as equivalent to all MVC patterns. Overly broad matchers authenticate unnecessary endpoints; overly narrow matchers leave secret endpoints unprotected.

## 5. The Biggest Pitfall: Registering One Filter Twice

In Spring Boot Servlet, a class implementing `jakarta.servlet.Filter` declared as a **Spring bean** can be auto-registered by Boot into the **Servlet container filter chain**. At the same time, calling:

```java
http.addFilterBefore(customFilter, UsernamePasswordAuthenticationFilter.class);
```

also registers **that same filter in the Spring Security chain**. Careless combined configuration can place the filter in **two pipelines**:

```text
Servlet container
  |
  +-- customFilter (auto-registered as a Servlet Filter)
  |
  +-- DelegatingFilterProxy
           |
           +-- FilterChainProxy
                   |
                   +-- customFilter (added via addFilterBefore)
```

Consequences can include:

- `doFilterInternal` or related callbacks run unexpectedly.
- Credentials get verified twice, increasing load on `AuthenticationManager` and downstream identity providers.
- The response gets written/committed or exceptions get handled in the second pass.
- One pass outside the Spring Security chain lacks the context/filter order/exception handlers present inside the chain.
- Login failures become hard to test because container filters outside the chain have a different lifecycle from security filters.

**Resolution:** decide whether the filter is managed **solely by Spring Security** or is an **independent container filter**. If you use `addFilterBefore` or `addFilterAfter` for an authentication filter, prevent Boot from auto-registering that bean in the Servlet container—for example via `FilterRegistrationBean.setEnabled(false)`; see the runnable project in section 8.

Never declare a filter as `@Component` or `@Bean` and also add it to the security chain while ignoring Boot's auto-registration. Never try to work around it with a global `static boolean alreadyAuthenticated` variable: that breaks concurrency, thread safety, request scoping, and multi-instance deployments.

## 6. Placing the Filter in the Right SecurityFilterChain, Not Just Picking addFilterBefore

Spring Security can have multiple `SecurityFilterChain`s with different `securityMatcher`s and `@Order`s. `FilterChainProxy` selects the **first matching chain**; it does not run all chains sequentially for the same request.

A cleanly scoped design:

```text
/api/**       -> API chain (custom header authentication, stateless)
/web/**       -> web chain (form login + HttpSession if present)
/other/**     -> fallback chain per deny/authenticated policy
```

For a dedicated API chain:

- `securityMatcher("/api/**")` defines which requests enter the chain.
- `shouldNotFilter(...)` decides which endpoints **inside the chain** need the custom filter.
- `authorizeHttpRequests(...)` enforces access rules after context is established.
- `addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)` inserts the filter at the corresponding position in Spring Security's filter order.

**Lacking a fallback chain** can leave URLs outside every `securityMatcher` unprotected by Spring Security. Conversely, adding the same filter instance to multiple chains with overlapping matchers does not turn it into two complementary auth steps; it mostly creates ownership confusion.

Verify actual chain ordering and selection via integration tests rather than guessing from bean method names.

## 7. Error Dispatch, Async Dispatch, and Committed Responses

A Servlet request can undergo several dispatch types:

| Dispatch | Characteristic | Risk When Custom Filter Is Uncontrolled |
|---|---|---|
| `REQUEST` | Initial request from client | Main authentication logic; must run once in scope |
| `ERROR` | Dispatch to error page after HTTP error/exception | Re-authenticating on error page, changing status, creating error loops |
| `ASYNC` | Resuming async request processing | Reading holder on wrong thread, re-running authentication unnecessarily |
| `FORWARD` | Internal forward to another resource | Matchers and filter dispatcher types may differ from original request |

**`OncePerRequestFilter` does not replace dispatcher-type configuration and security context propagation.** Default hook methods usually skip async/error dispatches, yet Servlet registrations, containers, and filter chains also govern whether requests reach the filter. If an API genuinely must guard ERROR/ASYNC dispatches, design and test explicitly rather than flipping hooks to `false` without reason.

Committed response pitfalls:

```java
response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
filterChain.doFilter(request, response);  // WRONG: continues after rejecting
```

Once a filter sends an error, it must `return`. Calling `sendError` can trigger an `ERROR` dispatch in the Servlet container, complicating routing. For stateless APIs with a simple 401 contract, you can call `response.setStatus(401)` and finish processing to avoid an unnecessary error dispatch; if JSON is needed, set the appropriate content type/body, write **once**, and never leak exception details.

Never write a body after `response.isCommitted()` is true. For requests that have already moved deep downstream, if an error happens after response commit, you cannot rely on an entry point or failure handler to write a fresh complete response; design commit timing carefully.

## 8. Complete Java 17+ Example: Custom Authentication, 401/403 Errors, and Avoiding Duplicate Registration

The example builds a small Spring Boot Servlet app with an API using header `X-Demo-Key`. **We do not use it as a production API key mechanism**: the hard-coded demo key is strictly for learning and lacks provisioning, rotation, revocation, scoping, replay/abuse controls, and secret management. In real products, **prefer standard mechanisms** like OAuth2 Resource Server/bearer tokens, mTLS, or audited API-key infrastructure.

Technical goals of the example:

- `DemoKeyFilter` extends `OncePerRequestFilter`.
- The filter attempts authentication only on `/api/secure/**`.
- Missing header: let authorization/entry point return 401; **do not attempt authentication**.
- Wrong header: provider throws `AuthenticationException`, filter catches within exact scope and returns 401; **controller does not run**.
- Valid header: sets valid authentication in `SecurityContextHolder`, downstream authorization checks roles.
- Authenticated yet missing ADMIN role: returns 403, **never mis-caught by the filter as a credential error**.
- Filter bean has **container auto-registration disabled** and participates only in the Spring Security chain.
- Tests count provider attempts and `doFilterInternal` invocations per request with headers, guarding against duplicate-registration regressions.

### 8.1. Project Structure

```text
custom-filter-demo/
├── pom.xml
└── src/
    ├── main/java/example/filterdemo/
    │   ├── FilterDemoApplication.java
    │   ├── DemoKeyAuthenticationProvider.java
    │   ├── DemoKeyFilter.java
    │   ├── ApiSecurityConfig.java
    │   └── ApiController.java
    └── test/java/example/filterdemo/
        └── DemoKeyFilterTest.java
```

### 8.2. pom.xml

The example uses **Spring Boot 3.3.5** and Java 17 solely as a reproducible baseline; do not claim this is the latest stable or still-supported release.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>custom-filter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent manages compatible Security and Framework versions. Never pin a mismatched `spring-security-web` version as a "quick fix" for filter ordering issues.

### 8.3. Entry Point

Create `src/main/java/example/filterdemo/FilterDemoApplication.java`:

```java
package example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
```

### 8.4. Demo-Only AuthenticationProvider

Create `src/main/java/example/filterdemo/DemoKeyAuthenticationProvider.java`:

```java
package example.filterdemo;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class DemoKeyAuthenticationProvider implements AuthenticationProvider {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();
    private final String keyVerifier = encoder.encode("demo-only-key");
    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Authentication authenticate(Authentication authentication) {
        attempts.incrementAndGet();

        Object candidate = authentication.getCredentials();
        if (!"demo-client".equals(authentication.getName())
                || !(candidate instanceof String presentedKey)
                || !encoder.matches(presentedKey, keyVerifier)) {
            throw new BadCredentialsException("Bad credentials");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
            "demo-client",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_API"))
        );
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
    }

    int attemptCount() {
        return attempts.get();
    }
}
```

In the demo, `demo-only-key` appears in source solely to build a fixture; it is not a production secret. Using BCrypt for verification **does not make a hard-coded secret secure**, nor does it replace key rotation and usage-limit policies. The provider neither logs nor returns credentials to clients.

Verification lives inside the provider; the filter does **not** compare passwords/API keys itself or mark an unverified token authenticated.

### 8.5. Single-Responsibility OncePerRequestFilter

Create `src/main/java/example/filterdemo/DemoKeyFilter.java`:

```java
package example.filterdemo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class DemoKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager authenticationManager;
    private final AtomicInteger invocations = new AtomicInteger();

    public DemoKeyFilter(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getServletPath().startsWith("/api/secure/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        invocations.incrementAndGet();
        String key = request.getHeader("X-Demo-Key");

        if (key == null) {
            // No credentials: let authorization/entry point decide.
            chain.doFilter(request, response);
            return;
        }

        Authentication verified;
        try {
            Authentication candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "demo-client", key
                );
            verified = authenticationManager.authenticate(candidate);
        } catch (AuthenticationException invalidCredential) {
            // Catch only authenticate(...) errors, DO NOT catch downstream errors.
            SecurityContextHolder.clearContext();
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    int invocationCount() {
        return invocations.get();
    }
}
```

Why does this order matter?

- Missing header: the filter does **not** issue pointless authentication requests. If the URL requires privileges, Spring Security authorization sends it to the entry point returning 401.
- Wrong header: `AuthenticationManager.authenticate` throws `AuthenticationException`, which the filter catches directly before response commit, returning 401 and halting.
- Valid header: the provider returns an Authentication with `ROLE_API`; a fresh context is set for downstream filters. Authorization can still deny if the endpoint requires `ROLE_ADMIN`.
- `chain.doFilter` sits **outside the AuthenticationException try/catch**, so errors in downstream filters/controllers are never misclassified as invalid credentials.
- `finally` clears the holder even if downstream throws an exception; Spring Security also runs security-context filter cleanup. This is a stateless demo, so **context is not saved to a session**.
- `AtomicInteger` counters only measure behavior in tests; never use them as security controls or system-wide counters in production.

For stateful authentication filters, the model differs: you may need `SessionAuthenticationStrategy`, `SecurityContextRepository.saveContext(...)`, and success/failure handlers. Never drop this stateless class into a session-based form-login flow and expect logins to survive redirects.

### 8.6. Security Configuration, Filter Bean, and Blocking Auto-Registration

Create `src/main/java/example/filterdemo/ApiSecurityConfig.java`:

```java
package example.filterdemo;

import java.util.List;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class ApiSecurityConfig {

    @Bean
    AuthenticationManager demoAuthenticationManager(
            DemoKeyAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    DemoKeyFilter demoKeyFilter(AuthenticationManager demoAuthenticationManager) {
        return new DemoKeyFilter(demoAuthenticationManager);
    }

    @Bean
    FilterRegistrationBean<DemoKeyFilter> disableContainerRegistration(
            DemoKeyFilter filter) {
        FilterRegistrationBean<DemoKeyFilter> registration =
            new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http, DemoKeyFilter filter)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/secure/admin").hasRole("ADMIN")
                .requestMatchers("/api/secure/**").hasRole("API")
                .anyRequest().denyAll())
            .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .build();
    }
}
```

**Important points in the configuration:**

1. The `DemoKeyFilter` bean is a Servlet `Filter`. Because it was added to the Spring Security chain via `addFilterBefore`, we declare `FilterRegistrationBean.setEnabled(false)` so Spring Boot **does not register the same bean as a standalone filter outside the security chain**.
2. The API chain has its own matcher and order 1. The order-2 fallback chain ensures non-API URLs **do not accidentally fall outside every chain**.
3. The stateless API uses only credentials explicitly sent via headers. Disabling CSRF **solely within this API chain** is an intentional choice for the header-token demo and **must never be copied to cookie/session form-login websites**. If browsers auto-send credentials via cookies, re-evaluate CSRF.
4. In this setup, API clients do not want HTML redirects: the authentication entry point returns 401. Access denied for principals lacking roles typically returns 403 via access-denied handling.
5. `ProviderManager` invokes only the demo provider for the filter's token. In real systems, never replace OAuth2 Resource Server or API-key infrastructure with a static-key dummy provider.
6. `hasRole("API")` checks authority `ROLE_API`; `hasRole("ADMIN")` requires `ROLE_ADMIN`. Never treat an authenticated user as automatically having all permissions.
7. `FilterRegistrationBean.setEnabled(false)` does not disable the filter inside the security chain: it disables only Boot's **container registration path**.

Some apps instantiate custom filters with `new` directly inside config (not as beans), or use custom `DelegatingFilterProxy` wiring. Adjust deduplication to the **actual registration path** instead of mechanically repeating every bean/method above.

### 8.7. Public and Protected Controller

Create `src/main/java/example/filterdemo/ApiController.java`:

```java
package example.filterdemo;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public/health")
    public String health() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/secure/data")
    public String data(Principal principal) {
        return "Hello, " + principal.getName();
    }

    @GetMapping("/api/secure/admin")
    public String admin(Principal principal) {
        return "ADMIN_ONLY: " + principal.getName();
    }
}
```

The controller neither inspects headers nor calls the manager again. That avoids **authenticating in the filter and then re-authenticating in the controller**. When business logic needs role/object-level authorization, place permission checks in the right security/service layer instead of passing raw credentials down to services for each method to re-verify.

### 8.8. Integration Tests for Exceptions and Duplicate Authentication

Create `src/test/java/example/filterdemo/DemoKeyFilterTest.java`:

```java
package example.filterdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoKeyFilterTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoKeyFilter filter;

    @Autowired
    DemoKeyAuthenticationProvider provider;

    @Test
    void publicEndpointSkipsCustomAuthentication() throws Exception {
        int before = filter.invocationCount();

        mvc.perform(get("/api/public/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));

        assertEquals(before, filter.invocationCount());
    }

    @Test
    void missingCredentialYieldsUnauthorized() throws Exception {
        int attempted = provider.attemptCount();

        mvc.perform(get("/api/secure/data"))
            .andExpect(status().isUnauthorized());

        assertEquals(attempted, provider.attemptCount());
    }

    @Test
    void invalidCredentialYieldsUnauthorized() throws Exception {
        int before = provider.attemptCount();

        mvc.perform(get("/api/secure/data").header("X-Demo-Key", "invalid"))
            .andExpect(status().isUnauthorized());

        assertEquals(before + 1, provider.attemptCount());
    }

    @Test
    void validCredentialAuthenticatesExactlyOnce() throws Exception {
        int beforeFilter = filter.invocationCount();
        int beforeProvider = provider.attemptCount();

        mvc.perform(get("/api/secure/data")
                .header("X-Demo-Key", "demo-only-key"))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, demo-client"));

        assertEquals(beforeFilter + 1, filter.invocationCount());
        assertEquals(beforeProvider + 1, provider.attemptCount());
    }

    @Test
    void authenticatedButWrongRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/secure/admin")
                .header("X-Demo-Key", "demo-only-key"))
            .andExpect(status().isForbidden());
    }

    @Test
    void requestWithoutCredentialDoesNotInheritPreviousContext()
            throws Exception {
        mvc.perform(get("/api/secure/data")
                .header("X-Demo-Key", "demo-only-key"))
            .andExpect(status().isOk());

        mvc.perform(get("/api/secure/data"))
            .andExpect(status().isUnauthorized());
    }
}
```

**Expected outcomes of the 6 tests in a proper environment**:

- Public GET succeeds without running the custom filter's `doFilterInternal`.
- Missing credentials lead to 401 via authorization/entry point, without calling the provider.
- Wrong key leads to 401 handled directly by the custom filter catching `AuthenticationException`, with the provider called once.
- Valid key leads to 200, with filter and provider each invoked **exactly once** for the test request.
- Valid key lacking ADMIN role leads to 403 via authorization, **not** mis-caught as a wrong key.
- A new request without the header does not reuse the previous request's `SecurityContext`.

Tests counting with `AtomicInteger` verify behavior on **the same test app running sequentially**; if tests run in parallel or concurrent traffic hits the app, bean-wide counters cannot use delta assertions without traffic isolation. This is an observability aid, not a production security contract.

### 8.9. Run Commands

Inside the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

With JDK 17+, Maven, and resolved dependencies, **6 tests are expected to pass**. Maven/Boot log lines depend on the environment; do not claim these as actually executed output. The demo uses port 8080 by default if available.

In another terminal:

```bash
curl -i http://localhost:8080/api/public/health
curl -i http://localhost:8080/api/secure/data
curl -i -H "X-Demo-Key: invalid" http://localhost:8080/api/secure/data
curl -i -H "X-Demo-Key: demo-only-key" http://localhost:8080/api/secure/data
curl -i -H "X-Demo-Key: demo-only-key" http://localhost:8080/api/secure/admin
```

Expected in order: `200 PUBLIC_OK`, `401`, `401`, `200 Hello, demo-client`, `403`. Never deploy this fixed sample token onto public networks; it is a fixture demonstrating exception and filter paths, not an API key management system.

## 9. When to Use AbstractAuthenticationProcessingFilter Instead of OncePerRequestFilter

If a custom filter represents an **interactive login endpoint** like posting a form or an authentication callback, extending `AbstractAuthenticationProcessingFilter` can be a better fit:

- `requiresAuthentication`/`RequestMatcher` identifies login requests.
- `attemptAuthentication` invokes the manager/provider and yields three outcomes: successful Authentication, `null` when incomplete, or `AuthenticationException`.
- `successfulAuthentication` coordinates session strategy, context repository, remember-me, and success handler.
- `unsuccessfulAuthentication` clears the holder and invokes the failure handler.

```java
@Override
public Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response) throws AuthenticationException {
    // Create untrusted token, call AuthenticationManager,
    // return authenticated Authentication or throw AuthenticationException.
}
```

This is only a **hook outline**, lacking a full method body/return and not a standalone compilable class. Customizing handlers to alter redirects or responses is usually cleaner than overriding `successfulAuthentication` just to write JSON.

When overriding success/failure hooks, remember that calling `super.successfulAuthentication(...)` or `super.unsuccessfulAuthentication(...)` matters: base-class logic handles `SecurityContext`, repositories, remember-me, events, and handlers. Skipping `super` without reproducing its contract can prevent context from saving or write responses twice.

Conversely, a filter reading credentials on every stateless API HTTP request usually fits `OncePerRequestFilter`, though if the framework already offers a standard filter such as `BearerTokenAuthenticationFilter`, use it instead of rewriting token parsing and validation.

## 10. Preventing Duplicate Authentication Is Not an Indefinite "Logged-In" Cache

Some people avoid repeated authentication by setting:

```java
private static boolean authenticated = false;
```

**Security and concurrency flaw**: a static flag spans the entire JVM, unbound to any request, principal, or client. One user logging in would treat other requests as authenticated, and multiple threads would race. Never use global flags to skip credential checks.

Another flawed idea is checking only:

```java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

if (current != null && current.isAuthenticated()) {
    // Skip authentication?
}
```

That is **also insufficient grounds** to apply mechanically: an anonymous token can technically report authenticated status; `isAuthenticated()` alone does not tell you which source produced the principal or whether it satisfies endpoint requirements. Any genuine optimization must verify chain, trusted authentication source, credentials, principal, and policy—never skipping token verification merely because the holder holds an object.

### Common Types of Duplicate Authentication

| Type of Duplication | Example | How to Prevent |
|---|---|---|
| Registering same filter in container and Security chain | Bean implements Filter + `addFilterBefore` | Disable container registration or pick a single place |
| Same request re-runs filter on async/error dispatch | Hooks or dispatcher mappings allow re-processing | Design around dispatcher types; use `OncePerRequestFilter` and test |
| Two different filters read the same credential | Custom bearer filter + standard Resource Server filter | Keep one source of truth; remove redundant filter |
| Both filter and controller call authenticate | Controller re-checks header after filter already did | Keep authentication in filter/provider; controller reads principal |
| Multiple chains with bad matchers and multiple filter instances | Inconsistent API chain + web chain config | Enforce clear `securityMatcher`/order and fallback chain |
| Client retries login POST | Client times out and resends | Idempotency and retry policies at application layer; never static flags |
| Both microservice gateway and backend validate tokens | Multiple trust boundaries may require independent verification | Do not skip backend checks merely because gateway saw the token |
| A new request to a stateless API | Client calls again with bearer/header credential | Re-authenticating every request may be required; this is **not a bad duplicate** |

Calling `AuthenticationManager.authenticate(...)` once **inside one filter** is not enough if another filter or controller also calls the manager. Root-cause control requires clear ownership boundaries and end-to-end integration tests.

## 11. Retries, Multi-Threading, Async, and Login Events

"Preventing duplicate authentication" has two semantic layers:

1. **Filter invocation mechanics:** avoiding erroneously running twice within the same request/dispatch due to double registration, misconfigured filter chains, or custom code calling authenticate at two layers.
2. **Business level:** users/clients may genuinely send **two HTTP requests** close together due to double-clicks, retries, load balancers, timeouts, or refreshes. `OncePerRequestFilter` does not deduplicate two independent requests.

If successful authentication has **side effects** such as sending email, creating audit records, emitting events, or issuing one-time tokens, design idempotency, transactional locks, or deduplication at the right business layer. Never use an unbounded `static Set<String> processedRequestIds` for deduplication: it leaks memory, breaks across multiple instances, and risks conflating users.

Questions to answer:

- Are client retries allowed on the login flow?
- If issuing one-time credentials, is token consumption atomic and replay-resistant?
- Can events/audits fire twice due to at-least-once delivery in message queues?
- On async dispatches, is `SecurityContext` properly propagated to worker threads?
- Once the response has committed, can anything still attempt a redirect or second success message?

**`OncePerRequestFilter`'s request attribute marker** only scopes filter execution within a request; it is not a distributed idempotency system. Systems issuing tokens or executing side-effectful transactions need dedicated mechanisms and retry testing.

## 12. Exception and Security Context Handling in Stateful Flows

The example in section 8 is a **stateless API**; every request sends headers and context is not saved to a session. For custom **form login/sessions**, after the provider verifies credentials, additional responsibilities apply:

```text
1. Receive login request with right method/path and check CSRF per policy.
2. AuthenticationManager.authenticate(untrustedToken).
3. SessionAuthenticationStrategy.onAuthentication(...).
4. Create new SecurityContext holding verified Authentication.
5. SecurityContextHolder.setContext(context).
6. SecurityContextRepository.saveContext(context, request, response).
7. SuccessHandler decides redirect/response.
8. On failure: clear context and invoke FailureHandler once.
```

In Spring Security 6, `SecurityContextHolderFilter` does not automatically save context changes made by custom code. If you forget `saveContext` in a hand-built flow, a 302 login success can be followed by an anonymous request. Do not mistake this for "the filter ran twice wrong": in session login, follow-up requests must restore authentication from the repository.

**Handle only `AuthenticationException` from the authentication attempt you own**; never catch `Exception` from the entire controller and turn it into a password error. If the session strategy rejects login with `SessionAuthenticationException`, the failure flow must handle it per policy. In standard form login code, `AbstractAuthenticationProcessingFilter` already structures these branches; prefer it when compatible with your protocol.

Avoid calling `sessionAuthenticationStrategy.onAuthentication(...)` or `securityContextRepository.saveContext(...)` a second time in a success handler when the standard filter already did so. A session strategy may rotate IDs or register sessions, so calling it twice can cause concurrency errors or spurious events.

## 13. Deeper Testing: What Else to Observe Beyond Status Codes?

**Status 401/403/200 alone does not prove a filter ran only once.** To prove it, test the exact boundaries:

1. **Filter invocation count:** each in-scope request executes `doFilterInternal` once in sequential tests.
2. **Provider attempt count:** a request with credentials invokes `AuthenticationManager.authenticate` exactly once.
3. **No duplicate servlet registration:** the same bean does not run outside the chain in uncontrolled order.
4. **Correct response ownership:** invalid credentials never enter controllers, never call downstream, never leak credentials, and never write responses twice.
5. **Wrong role is authorization failure:** authenticated requests lacking a role take the 403 branch instead of turning into `BadCredentialsException`.
6. **SecurityContext cleanup:** a subsequent request without credentials never reuses the prior request's principal.
7. **Request matching:** public routes do not force clients to supply dummy headers.
8. **Error/async dispatch:** configure and test explicitly if the app has async/error routes.
9. **Resilience:** provider timeouts/infrastructure exceptions are not mechanically turned into wrong-password errors.
10. **Load/concurrency:** measure behavior under concurrent requests without assuming demo counters or custom ThreadLocals are security boundaries.

A real integration test can also send requests through a container/embedded server to verify exact Servlet filter registration. `MockMvc` is very useful, yet does not simulate every reverse proxy and production servlet container error-dispatch setting. Therefore unit + `MockMvc` tests **and** real-container tests in deployment-like environments complement each other.

## 14. Checklist Before Shipping a Custom Filter to Production

- [ ] Identified Servlet stack, `FilterChainProxy`, the right `SecurityFilterChain`, and filter ordering.
- [ ] Filter has explicit matcher/path/method constraints instead of handling all endpoints indiscriminately.
- [ ] Credentials are verified by a trusted manager/provider; filter never marks untrusted input authenticated.
- [ ] `AuthenticationException` from authentication is handled at the exact boundary, without catching errors from the entire downstream chain.
- [ ] 401/403/5xx responses follow a clear contract; `return` after handling errors so responses are never written twice.
- [ ] Never log passwords, API keys, JWTs, session IDs, or raw credentials.
- [ ] Use `OncePerRequestFilter` appropriately for dispatcher types, without treating it as idempotency across HTTP requests.
- [ ] Never register the same filter in both the Servlet container and Spring Security; consider `FilterRegistrationBean.setEnabled(false)` for Spring bean Filters.
- [ ] Avoid two filters/parsers and controllers redundantly authenticating the same credential.
- [ ] `SecurityContextHolder` is set and cleared properly; if stateful, session strategy/context repository save at the right moment.
- [ ] Stateless APIs do not accidentally persist authentication into sessions or use static "already authenticated" flags.
- [ ] CSRF/sessions/HTTPS are designed around how clients send credentials, without disabling security globally to make tests pass.
- [ ] Tests cover 200, 401 (missing/invalid credentials), 403 (authenticated yet lacking permission), and no-credential follow-up requests.
- [ ] Provider/filter invocation counts and container registration/dispatch are tested in complex systems.
- [ ] Side effects of login/token issuance have dedicated retry/idempotency designs instead of relying on filter request markers.

### Self-Check Questions

**1.** A custom filter sits before `ExceptionTranslationFilter`, throws `BadCredentialsException`, and expects the downstream `ExceptionTranslationFilter` to always catch it. Is that right?  
**Answer:** No. Downstream components do not wrap upstream processing. Catch errors from `AuthenticationManager.authenticate` inside the filter or use Spring Security's supported authentication failure handler mechanism.

**2.** Why shouldn't `filterChain.doFilter(...)` sit inside a broad `try/catch(AuthenticationException)` block?  
**Answer:** Because downstream exceptions can be mistaken for the filter's credential errors, producing wrong statuses, handlers, and logs.

**3.** A Spring bean filter is both auto-registered by Boot and added via `http.addFilterBefore`. What is the risk?  
**Answer:** It can participate in both the container filter chain and the security filter chain, causing duplicate execution/uncontrolled ordering. Pick one registration place; for Filter beans used solely in the security chain, disable container registration appropriately.

**4.** Does `OncePerRequestFilter` ensure two independent retry HTTP requests are processed only once?  
**Answer:** No. It bounds internal calls within a single request/dispatch scope; multi-request idempotency/retry handling is a separate responsibility.

**5.** Valid credentials yet missing `ROLE_ADMIN`—should the API return 401 because the key is "not strong enough"?  
**Answer:** No. The credentials already verified identity; missing permissions is an authorization failure, typically returning 403.

**6.** Why didn't the example API save `SecurityContext` into `HttpSession`?  
**Answer:** It is designed as stateless; every request must carry credentials. Save into a session only when intended by a different protocol, such as stateful form login.

**7.** If login POST succeeds and the next request redirects back to the login page, must the filter have run twice?  
**Answer:** No. Custom login may have failed to save `SecurityContext` to the repository, or the client failed to retain the right session cookie.

**Conclusion:** Exception handling in custom authentication filters must happen at **the exact origin, with the right response owner, and the right status category**, while preventing duplicate authentication requires simultaneously controlling **matchers, chain selection, filter registration, dispatches, and single-source authentication**. `OncePerRequestFilter` helps bound execution within a request, while `FilterRegistrationBean` and clean security chain design prevent duplicate registration. For stateful flows or side effects, dedicated session persistence and idempotency are still required.