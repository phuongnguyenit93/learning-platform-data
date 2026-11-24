# AuthorizationFilter and the Position of Access Control Checks in Spring Security Servlet

## 1. What problem does AuthorizationFilter solve?

In a Servlet application using Spring Security, **authentication** and **authorization** are two distinct decisions:

- **Authentication:** does the request represent a verified user or principal? If so, what are their identity and authorities?
- **Authorization:** is this request permitted to access a specific resource given its current identity/authorities?

`AuthorizationFilter` is a **Servlet Filter** in the Spring Security chain responsible for enforcing **HTTP request-level authorization rules**. It typically receives a decision from an `AuthorizationManager<ServletRequest>`, then:

1. **Allow:** calls `chain.doFilter(request, response)` so the request continues to subsequent filters or the application.
2. **Deny:** throws an exception of the `AccessDeniedException` family; upstream security exception handling can turn the exception into HTTP 401, HTTP 403, or a redirect according to configuration.

It **does not authenticate usernames/passwords itself**, is not a controller, and **does not directly decide the 401/403 status in every case**. Producing the final response usually involves collaboration among other components such as `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`.

This lesson focuses on the mechanics of `AuthorizationFilter`, its position in the Servlet filter pipeline, and how `authorizeHttpRequests` rules affect requests.

## 2. Position in filter architecture: checking permissions before entering the endpoint

Spring Security integrates with the Servlet container through a filter chain. A typical **conceptual** flow looks like this:

```text
HTTP request
  |
  v
Servlet container FilterChain
  |
  v
DelegatingFilterProxy ("springSecurityFilterChain")
  |
  v
FilterChainProxy
  |  selects first SecurityFilterChain matching request
  v
[SecurityContext / authentication-related filters]
  |
  v
[AnonymousAuthenticationFilter, if configured]
  |
  v
ExceptionTranslationFilter
  |  wraps downstream filters to handle security exceptions
  v
AuthorizationFilter
  |  evaluates authorizeHttpRequests rules
  +---- DENY ---> AccessDeniedException
  |                ^
  |                | handled by ExceptionTranslationFilter
  |                +--> entry point / access denied handler
  |
  +---- ALLOW ---> chain.doFilter(...)
                    |
                    v
              remainder of the chain
                    |
                    v
              DispatcherServlet
                    |
                    v
              Controller / endpoint
```

The diagram shows **key positions and primary responsibilities**, not a complete list or immutable order across all versions/configurations. Authentication filters may differ across HTTP Basic, form login, bearer token, OAuth2, etc. Custom filters can also be added before or after `AuthorizationFilter`.

Three layers to keep separate:

| Component | Role |
| --- | --- |
| Servlet container `FilterChain` | Manages forwarding between Servlet Filters and the final target. |
| `FilterChainProxy` | Selects and runs **one** matching `SecurityFilterChain` from the configured list. |
| `SecurityFilterChain` | Holds the set of security filters applying to a group of requests; it is **not synonymous** with a `requestMatchers` rule. |
| `AuthorizationFilter` | Evaluates HTTP authorization at its position in the selected chain; proceeds if allowed. |
| `ExceptionTranslationFilter` | Catches authentication/authorization exceptions thrown by downstream components, converting them into a security response mechanism. |

In modern configurations using `authorizeHttpRequests`, `AuthorizationFilter` normally sits **near the end of the standard security filter chain**, after context/authentication setup filters and after `ExceptionTranslationFilter`. Saying "near the end" is more accurate than "always the last filter": there may be custom filters or other container filters, and the actual order must be verified against the running configuration.

### Why does `ExceptionTranslationFilter` sit before `AuthorizationFilter`?

When `AuthorizationFilter` detects insufficient permissions, it throws an `AccessDeniedException`-type exception. `ExceptionTranslationFilter` sitting upstream is wrapping the call to downstream filters, so it can catch the exception and choose an action:

- Principal is unauthenticated under the active mechanism: triggers `AuthenticationEntryPoint` (e.g., HTTP 401 with Basic/Bearer, or redirect to the login page with form login).
- Principal is authenticated yet lacks permissions: delegates to `AccessDeniedHandler` (usually returns HTTP 403).

`ExceptionTranslationFilter` **is not the component making access control decisions**. It translates exceptions into appropriate responses; `AuthorizationFilter` / `AuthorizationManager` is what checks the HTTP request rules in this case.

## 3. Which steps does AuthorizationFilter perform?

For a request that has entered the selected security filter chain, the process can be understood as follows:

1. Upstream filters set up `SecurityContext` and process the configured authentication mechanism; when appropriate, an `AnonymousAuthenticationToken` may appear for unauthenticated requests.
2. `AuthorizationFilter` has access to `HttpServletRequest` (via the `ServletRequest` interface) and a way to obtain the current `Authentication`.
3. `AuthorizationManager<ServletRequest>` evaluates the request against rules such as `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, or a custom policy.
4. If **allowed**, `AuthorizationFilter` calls `chain.doFilter`; the controller has a chance to run if downstream components do not block it.
5. If **denied**, it **does not** invoke the rest of the chain along that branch and the security exception propagates upward to be handled.

A **simplified** illustration, not literal framework source code:

```java
// Pseudocode illustrating the idea, not a standalone Java class.
AuthorizationResult result =
    authorizationManager.authorize(authenticationSupplier, request);

if (result != null && !result.isGranted()) {
    throw new AccessDeniedException("Forbidden");
}

chain.doFilter(request, response);
```

**Note on APIs:** Spring Security versions differ in exact result types, methods, and exceptions. The example above only illustrates the two ALLOW/DENY branches; do not copy it to replace `AuthorizationFilter`'s implementation. Some policy mechanisms represent decisions using types such as `AuthorizationDecision` / `AuthorizationResult`; use the API matching your actual dependency.

### Obtaining Authentication can be lazy

The authorization system can accept a `Supplier<Authentication>`, avoiding fetching `Authentication` immediately if a rule does not need an identity. For instance, a request matching `permitAll()` can be permitted without accessing `Authentication` during the decision. This explains why "permitted" and "authenticated" are completely different.

**`permitAll()` allows the request past this HTTP authorization step; it does not prove the request is logged in, nor does it skip the entire security filter chain.**

## 4. Where are rules selected: `securityMatcher` vs. `requestMatchers`

There are **two crucial matching levels**, very easy to confuse:

**Level 1 – Chain selection:** `FilterChainProxy` evaluates `SecurityFilterChain`s in configured order and uses the **first chain matching the request**. For example, a chain with `http.securityMatcher("/api/**")` applies only to that path group.

**Level 2 – Rule selection within the chain:** The selected chain's `AuthorizationFilter` relies on the `AuthorizationManager` built by `authorizeHttpRequests` to apply the corresponding rule, such as `requestMatchers("/admin/**").hasRole("ADMIN")`. Under typical sequential matcher configuration, the **first matching rule** applies.

```text
Incoming request: GET /admin/panel
     |
     v
FilterChainProxy:
  chain #1 securityMatcher("/api/**")      -> no match
  chain #2 (fallback for other requests) -> match
     |
     v
AuthorizationFilter of chain #2:
  requestMatchers("/public/**") -> no match
  requestMatchers("/admin/**")  -> match, requires ROLE_ADMIN
  anyRequest().authenticated() -> not evaluated
```

If **no SecurityFilterChain matches**, the request does not pass through Spring Security's security filter chain at that proxy location; as a result, the endpoint may be unprotected by Spring Security. Thus when configuring multiple chains, verify the covered request area and define an appropriate fallback.

`securityMatcher(...)` and `requestMatchers(...)` have distinct roles: the former restricts **the scope of the entire security chain**, while the latter defines **authorization rules inside the selected chain**.

## 5. Modern rules with `authorizeHttpRequests`

In Spring Security 6.x with Spring Boot 3.x applications, HTTP authorization declarations typically use the DSL:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

This is a **configuration snippet belonging to a `@Configuration` class**, requiring imports for `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, and the corresponding Spring Boot/Spring Security environment. A complete runnable example is in the next section.

How to read the rules:

- `/public/**`: anyone can pass the HTTP authorization step, including anonymous users.
- `/admin/**`: requires authority `ROLE_ADMIN`; `hasRole("ADMIN")` checks the authority with the default `ROLE_` prefix.
- `anyRequest().authenticated()`: remaining requests require an authenticated principal as defined by Spring Security.
- `httpBasic(...)`: enables HTTP Basic so the example has a clear challenge mechanism when unauthenticated.

**Order is critically important.** Declaring a general matcher before a narrow matcher lets the general rule shadow the narrow rule, or the DSL may reject invalid rules after `anyRequest()`. Put specific rules first and `anyRequest()` last.

### `hasRole` and `hasAuthority`

- `hasRole("ADMIN")`: using the default role prefix, requires authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")`: checks the exact string `ROLE_ADMIN`, usually equivalent to the example above.
- `hasAuthority("ADMIN")`: checks exact `ADMIN`, **not equivalent** if the user only has `ROLE_ADMIN`.
- `authenticated()`: checks authenticated status, **does not mean** having admin permissions.

The default prefix can be reconfigured; in real projects, inspect the actual authorities in `Authentication` and the application's policy.

## 6. Spring Boot 3 + Java 17 example: verifying allowed and denied requests

The example comprises a minimal Servlet application using Spring MVC, one `SecurityFilterChain`, three endpoints, and `MockMvc` tests. All test requests are **GET** to focus on `AuthorizationFilter` without mixing in CSRF checks for state-changing operations.

Directory structure:

```text
authorization-filter-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          security/
            AuthorizationDemoApplication.java
            SecurityConfig.java
            EndpointController.java
    test/
      java/
        demo/
          security/
            AuthorizationFlowTest.java
```

### 6.1. Dependencies

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>authorization-filter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

This is a specific Spring Boot 3.x version using Java 17. Run in a Maven project with JDK 17+ and Maven installed; Maven downloads dependencies on first run if not yet cached.

### 6.2. Startup class

`src/main/java/demo/security/AuthorizationDemoApplication.java`:

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
```

### 6.3. Authorization configuration

`src/main/java/demo/security/SecurityConfig.java`:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

This configuration creates a default security chain for web requests; the `authorizeHttpRequests` DSL causes the HTTP authorization mechanism to use `AuthorizationFilter`. This is an **HTTP Basic example to observe results**; real applications can substitute form login, OAuth2 Resource Server, or another authentication mechanism while still requiring authorization rules.

### 6.4. Three easily observable endpoints

`src/main/java/demo/security/EndpointController.java`:

```java
package demo.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EndpointController {

    @GetMapping("/public/ping")
    String publicPing() {
        return "public";
    }

    @GetMapping("/private/ping")
    String privatePing() {
        return "private";
    }

    @GetMapping("/admin/ping")
    String adminPing() {
        return "admin";
    }
}
```

### 6.5. Testing with MockMvc and simulated accounts

`src/test/java/demo/security/AuthorizationFlowTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void privateEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/private/ping"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void privateEndpointAllowsAuthenticatedUser() throws Exception {
        mvc.perform(get("/private/ping")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("private"));
    }

    @Test
    void adminEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/admin/ping"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminEndpointDeniesOrdinaryUser() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminEndpointAllowsAdmin() throws Exception {
        mvc.perform(get("/admin/ping")
                .with(user("alice").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }
}
```

The `user("...").roles("...")` calls are **simulated principals in the test** created by `spring-security-test`, avoiding storing real passwords in the example. `@AutoConfigureMockMvc` configures MockMvc integrated with the application's Servlet Filters. Calling `get(...)` sends a request through the HTTP MVC test pipeline, rather than invoking controller methods directly.

In the directory containing `pom.xml`, run:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` executes the six tests; if configured properly, all six assertions succeed. Maven output includes environment/timing info, so there is **no fixed stdout** to copy verbatim. `mvn spring-boot:run` starts the server so you can try GET `http://localhost:8080/public/ping`. The public request body result is `public`; response status is 200. For an unauthenticated request to `/private/ping`, HTTP Basic configuration returns 401. No production accounts are configured in this example; the test accounts **do not automatically become accounts that can log in via HTTP Basic outside tests**.

### 6.6. Table explaining the six test scenarios

| Request | Principal in test | Selected rule | Expected result |
| --- | --- | --- | --- |
| GET `/public/ping` | Anonymous | `permitAll` | 200, body `public` |
| GET `/private/ping` | Anonymous | `authenticated` | 401 with HTTP Basic |
| GET `/private/ping` | Has `ROLE_USER` | `authenticated` | 200, body `private` |
| GET `/admin/ping` | Anonymous | `hasRole("ADMIN")` | 401 with HTTP Basic |
| GET `/admin/ping` | Has `ROLE_USER` | `hasRole("ADMIN")` | 403 |
| GET `/admin/ping` | Has `ROLE_ADMIN` | `hasRole("ADMIN")` | 200, body `admin` |

The table above describes **results for this specific HTTP Basic configuration**, not a claim that every Spring Security application returns the same codes: for example, form login may redirect to a login page.

## 7. Why are 401 and 403 not written directly by AuthorizationFilter?

Consider two requests to `/admin/ping` in the example:

**A. Unauthenticated:** the manager denies because the principal lacks the required authority. The authorization exception propagates up to `ExceptionTranslationFilter`, where the authentication mechanism determines login must be initiated. With HTTP Basic, `AuthenticationEntryPoint` can produce a `401 Unauthorized` response with the appropriate Basic challenge.

**B. Logged in with `ROLE_USER`:** the request lacks `ROLE_ADMIN`, yet the principal does not need a fresh login challenge under normal policy. `AccessDeniedHandler` handles insufficient permissions and returns `403 Forbidden`.

This means a **DENY** decision at `AuthorizationFilter` can lead to different responses depending on `Authentication` and the handlers. Reading `AccessDeniedException` in logs alone is not enough to determine the final status code.

Conversely, when **ALLOW**, the request still traverses further steps. Passing `AuthorizationFilter` **does not guarantee an eventual 200**: the controller might return 404/500, the method could be denied by method security, or other filters could block the request.

## 8. Things AuthorizationFilter does not do

### 8.1. Does not replace authentication filters

`UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, bearer-token filters, and corresponding authentication mechanisms process credentials as configured. `AuthorizationFilter` uses the established state to check HTTP access policies. An unauthenticated request matching `permitAll` can still proceed.

### 8.2. Does not replace CSRF protection

`permitAll()` does not mean every other filter will ignore the request. For instance, a state-changing **POST** can be rejected by `CsrfFilter` for missing a token, even if the path is `permitAll()`. This is not evidence that `AuthorizationFilter` altered its own policy.

When debugging, distinguish errors from `AuthorizationFilter`, `CsrfFilter`, authentication filters, or controllers. Never disable CSRF application-wide just to "fix" an unexplained 403 response.

### 8.3. Does not replace method security

`AuthorizationFilter` checks requests at the web layer, before executing the controller in normal flow. If the system also enables method security (e.g., `@EnableMethodSecurity` and `@PreAuthorize`), method checks occur when calling the protected method. A request can pass `AuthorizationFilter` yet still be denied at the method, and the exception can be translated into an appropriate HTTP response by security infrastructure.

HTTP rules and method rules complement each other; do not infer that allowing at one layer automatically bypasses the other layer.

### 8.4. Does not manage all SecurityFilterChains by itself

An application with multiple `SecurityFilterChain`s may separate API/public/admin groups. `FilterChainProxy` selects a chain, and only then does `AuthorizationFilter` inside that chain act. Hence, to know which rules govern a request, **identify the matching chain first**.

## 9. Two configuration levels affecting where permission checks run

### 9.1. Authorization at the end of the selected chain

In most standard DSL configurations, authentication/security context is established before `AuthorizationFilter`. This makes sense because rules like `hasRole("ADMIN")` require authority data.

However, if you add a custom filter running **after** `AuthorizationFilter`, that filter only receives requests permitted past the HTTP checkpoint; running afterward does not prove other security rules have finished. Conversely, a filter placed **before** `AuthorizationFilter` can process requests before HTTP authorization decisions occur.

Adding a custom filter should have a clear purpose and position. Do not put a filter producing a success response before authorization and accidentally bypass the entire permission check.

### 9.2. Multiple security chains and fallback

Example illustrating a **different configuration**, not to be pasted alongside section 6's `SecurityConfig` without intentionally replacing it:

```java
@Configuration
public class MultipleChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain internal(HttpSecurity http) throws Exception {
        http.securityMatcher("/internal/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain rest(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

The snippet requires importing `Configuration`, `Bean`, `Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` and is used in a project with the corresponding Spring Security dependencies. For `GET /internal/report`, the `@Order(1)` chain matches and requires `ROLE_OPS`; a `GET /other` request goes to the fallback chain, requiring only authentication. `anyRequest()` inside each chain **does not expand** that chain's `securityMatcher` scope.

If there is no fallback chain covering `/other`, Spring Security will not apply those chain filters to that request. An application with strict security requirements should inspect all paths thoroughly, including routes without controllers, rather than assuming "AuthorizationFilter is definitely on every request".

### 9.3. Legacy FilterSecurityInterceptor

In older Spring Security configurations, you may encounter `FilterSecurityInterceptor` tied to the `authorizeRequests` DSL and legacy authorization checks. With modern `authorizeHttpRequests`, `AuthorizationFilter` together with `AuthorizationManager` is the core model. When reading project logs or source, **check which filter type is actually registered**, rather than treating both names as the same instance or forcing every version onto the same pipeline.

## 10. Dispatcher types: the same HTTP request can still be checked multiple times

Servlets have multiple dispatch types, such as `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. Whether a filter runs on a specific dispatch depends on Servlet container/Spring Boot registration, security configuration, and dispatch conditions.

When `AuthorizationFilter` is invoked on another dispatch, permission checks **may run again**. For example, a request allowed into a controller might later be forwarded to a view page with different rules. Error handling might dispatch to `/error`; if the security chain applies to `ERROR` and your rules require authentication, the error page could also be blocked.

You can configure permitting necessary dispatchers **after considering application scope**:

```java
// Placed inside HttpSecurity's authorizeHttpRequests DSL:
.dispatcherTypeMatchers(
    DispatcherType.FORWARD,
    DispatcherType.ERROR
).permitAll()
```

This is a **configuration fragment**, requiring `jakarta.servlet.DispatcherType` to be imported and placed appropriately in the matcher chain before `anyRequest()`. Permitting all FORWARD/ERROR is a specific security decision, not a default directive for every project: if a forward can reach sensitive content, evaluate the policy accordingly. Do not toggle dispatcher rules based on an assumption that an HTTP request passes through security only once.

## 11. `permitAll()` is not the same as ignoring Spring Security

There is a difference between:

- **`requestMatchers("/public/**").permitAll()`:** the request still enters the selected `SecurityFilterChain`; `AuthorizationFilter` permits it at the HTTP authorization step, while other filters can run as usual.
- **Ignoring configured via `WebSecurityCustomizer#ignoring`:** matching requests can skip the entire security filter chain; this also loses capabilities provided by security filters, such as setting certain security headers.

In most cases when making an endpoint public while maintaining general HTTP security mechanisms, `permitAll()` expresses the policy more cleanly. Skipping the entire security chain requires a specific architectural justification.

## 12. Diagnosing a rejected request at the right stage

When encountering a 401/403 request or a controller not running, investigate in causal order:

1. **Identify the actual request:** method, path, context path, dispatcher type, and authentication state. Never put passwords, session identifiers, or bearer tokens into logs.
2. **Identify the selected SecurityFilterChain:** if multiple chains exist, inspect `securityMatcher` and `@Order`; do not jump straight into `requestMatchers` of a chain that did not match.
3. **Identify the filter producing the block:** did it reach `AuthorizationFilter`? Or did `CsrfFilter`, an authentication filter, or a custom filter terminate earlier?
4. **Identify the authorization rule:** does the request match `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, or a fallback? Verify matcher order and actual authorities (e.g., `ROLE_ADMIN`).
5. **Trace the DENY outcome:** did the exception reach `ExceptionTranslationFilter`? Which component is the active `AuthenticationEntryPoint` or `AccessDeniedHandler`? This explains 401/403/302 differences.
6. **If ALLOW yet still failing:** inspect downstream components, method security, controllers, exception handling, and subsequent dispatches.

In development environments, you can enable logs to observe the processing pipeline:

```properties
logging.level.org.springframework.security=DEBUG
```

DEBUG logs are helpful though they may not show every granular decision; TRACE level can provide more detail. When handling real data, inspect log contents to avoid leaking sensitive info and enable verbose levels only in appropriately controlled environments.

### Very common misconceptions

| Misconception | Corrected understanding |
| --- | --- |
| "AuthorizationFilter runs before all authentication filters." | In a typical modern chain, authentication/context filters run ahead of it; verify actual order if custom filters exist. |
| "AuthorizationFilter writes status 401 or 403 directly." | It evaluates permissions and can throw an exception. Exception translation/entry point/handler decide the final response. |
| "Having `permitAll` means the request bypasses all security." | It only allows past the corresponding HTTP authorization step; CSRF, headers, and other filters can still apply. |
| "`hasRole("ADMIN")` checks authority `ADMIN`." | By default it checks `ROLE_ADMIN`. |
| "`authenticated` means access to all endpoints." | It only requires authentication; endpoints with specific role/authority rules can still deny. |
| "`anyRequest` applies across every chain in the application." | It applies inside the `SecurityFilterChain` being configured, after chain selection conditions. |
| "An HTTP request is checked for permissions exactly once." | Consider dispatcher types, multiple dispatches, and filter registrations. |
| "AuthorizationFilter allowing means the controller definitely returns 200." | Downstream there can still be other filters, method security, exceptions, or non-200 responses. |
| "HTTP 403 is always a missing role." | CSRF, custom filters, or controllers can also return 403. Trace where the decision actually occurred. |

## 13. Flow-reasoning exercises

**Scenario 1 – Two different permissions.** A user with authority `ROLE_USER` sends `GET /admin/ping`. The rule is `hasRole("ADMIN")` and the app uses HTTP Basic. Does `AuthorizationFilter` allow or deny? Usual status?

**Answer:** Denies due to missing `ROLE_ADMIN`. Since the principal is authenticated, `ExceptionTranslationFilter` and `AccessDeniedHandler` typically produce 403. Do not conclude 401 merely because the user "could not get in".

**Scenario 2 – A public request.** An anonymous user calls `GET /public/ping` matching `permitAll()`. Does `AuthorizationFilter` authenticate the anonymous user into a valid account before entering the controller?

**Answer:** No. `permitAll` allows without requiring an authenticated identity. The request continues down the chain; do not treat this step as a login mechanism.

**Scenario 3 – Matcher inside an unselected chain.** Chain #1 has `securityMatcher("/api/**")` and defines `requestMatchers("/admin/**").hasRole("ADMIN")` inside. Is `GET /admin/ping` subject to this admin rule?

**Answer:** No, because chain #1 does not match `/admin/ping`. Determine whether another chain matches; matchers inside an unselected chain do not evaluate this request.

**Scenario 4 – GET works, POST gets 403.** The same `/public/update` path is configured with `permitAll`; GET works, but POST without a CSRF token returns 403. Did AuthorizationFilter ignore `permitAll`?

**Answer:** Unfounded. `CsrfFilter` can block the POST before the HTTP authorization checkpoint. Identify the filter raising the error rather than "fixing" policy by arbitrarily disabling CSRF.

**Scenario 5 – Reached controller yet still denied.** A request passes `AuthorizationFilter`, yet a service method with `@PreAuthorize` denies it. Is there a contradiction?

**Answer:** No. Those are two different checkpoints: HTTP request-level and method-level. Passing the first layer does not remove checks at the second layer.

## 14. Key takeaways to apply

- `AuthorizationFilter` performs **HTTP request authorization**, typically via `AuthorizationManager<ServletRequest>`, and only calls `chain.doFilter` when the request is permitted.
- It operates **inside the SecurityFilterChain selected by FilterChainProxy**; `securityMatcher` selects the chain, `requestMatchers` selects the policy within the chain.
- With the `authorizeHttpRequests` DSL, place specific matchers before `anyRequest`. Verify the exact `ROLE_` prefix when using `hasRole`.
- **Upstream `ExceptionTranslationFilter`** handles security exceptions from downstream filters; 401, 403, or redirects depend on the authentication mechanism and handlers.
- `permitAll()` does not skip all security filters, does not replace CSRF, does not authenticate users itself, and does not guarantee a 200 response.
- Debug in the order **selected chain → blocking filter → matcher/policy → principal/authority → exception translation → response**, while accounting for dispatcher types, custom filters, and method security.
