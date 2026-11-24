# AndRequestMatcher, OrRequestMatcher, and NegatedRequestMatcher in Spring Security Servlet

## 1. Problem Statement and Goals

In Spring Security Servlet, a condition for applying a security policy is often more than just "path equals `/api/report`". We may need to combine multiple criteria:

- The request must use **GET** and belong to one of two URL groups: `/api/reports/**` or `/api/history/**`.
- The request must **not** belong to the internal branch `/api/reports/internal/**`.
- Internal URLs have a separate authorization rule for administrators.
- Other URLs must be denied if the application has not defined a policy for them.
- All condition combinations must be tested against real Servlet requests, not merely URL string `contains` checks.

Spring Security provides `RequestMatcher` and three implementations for composing conditions:

1. **`AndRequestMatcher`**: all component matchers must match.
2. **`OrRequestMatcher`**: at least one component matcher must match.
3. **`NegatedRequestMatcher`**: inverts the true/false result of a component matcher.

They help express rules intentionally, instead of writing a giant filter with nested `if` conditions. However, **a matcher only decides whether a request matches**; it does not authenticate users itself, does not grant permissions itself, and does not guarantee endpoint safety if placed in the wrong position.

This lesson focuses on **request matching** in Spring Security Servlet, including syntax, logical operations, integration with `authorizeHttpRequests`, `SecurityFilterChain` scope, and Java 17 testing.

## 2. What Is RequestMatcher?

`org.springframework.security.web.util.matcher.RequestMatcher` is an abstraction that accepts an `HttpServletRequest` and returns whether the request satisfies a condition.

Simple idea:

```java
// Core signature of RequestMatcher; this is illustrative, not redefining the library.
boolean matches(HttpServletRequest request);
```

A matcher can inspect relevant request attributes:

- Servlet path, path info, and context path depending on the implementation.
- HTTP method: `GET`, `POST`, `PUT`, `DELETE`, etc.
- Headers, content type, host, or other properties when building a custom matcher.
- Framework-dependent metadata, such as Spring MVC path rules when using an MVC-aware matcher.

Therefore, a request can be evaluated along multiple dimensions; never equate "request matcher" with "URL string starting with prefix X".

Example with `AntPathRequestMatcher`:

```java
RequestMatcher reports =
    new AntPathRequestMatcher("/api/reports/**");

RequestMatcher onlyGetApi =
    new AntPathRequestMatcher("/api/**", "GET");
```

These illustrative snippets require importing `RequestMatcher` and `AntPathRequestMatcher` from `org.springframework.security.web.util.matcher`. They are used inside Java methods or beans with Spring Security on the classpath, not as a standalone `javac` program.

`AntPathRequestMatcher` in the Spring Security 6.3.x example can match by pattern and optional method. Some newer Spring Security versions change recommendations or deprecate this matcher API; when upgrading, check the exact version's API docs and consider matchers using `PathPattern`/Spring MVC where appropriate.

### 2.1. A Matching Result Is Not Authentication

Suppose `reports.matches(request)` returns `true`. That only means the request lies within the specified path region; it does **not** guarantee:

- the request has an `Authentication`;
- the user holds authority `ROLE_READER`;
- the user owns the requested report;
- the CSRF token is valid;
- the method is permitted to execute;
- the controller will return 200.

In Spring Security, applying rules such as `.hasRole("READER")` or `.authenticated()` belongs in the authorization layer, after the request is identified by the matcher.

## 3. AndRequestMatcher: All Conditions Must Hold

`AndRequestMatcher` combines matchers using the **AND** operation:

```text
AND(A, B, C) == A && B && C
```

Example: match only when it is a GET **and** the path belongs to the reports area:

```java
RequestMatcher getReports = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new AntPathRequestMatcher("/api/reports/**")
);
```

| Request | GET in `/api/**`? | In `/api/reports/**`? | AND Result |
| --- | --- | --- | --- |
| GET `/api/reports/summary` | Yes | Yes | **true** |
| POST `/api/reports/summary` | No | Yes | false |
| GET `/api/history/list` | Yes | No | false |
| GET `/web/reports/summary` | No | No | false |

Combining path and method is very useful when one URL handles multiple HTTP methods with different access permissions per method. For example, GET can be a read-only operation, while POST creating a report must have its own authorization and CSRF policy.

### 3.1. AND Does Not Guarantee a Condition Set Is "Safe"

If we write `AND(isGet, isTrustedHeader)`, the result can still be insecure if the "trusted header" is attached by the client. The matcher only evaluates the given conditions; it does not verify business assumptions about trustworthiness.

Especially avoid matchers that check `X-User-Role: admin` as proof of authorization. Authorities must come from a trusted authentication/authorization source, not an arbitrary request header controlled by an attacker.

### 3.2. Behavior With Multiple Matchers

`AndRequestMatcher` typically evaluates components until it encounters a false condition; remaining conditions do not need evaluation to conclude. Never design matchers with side effects, because call counts and evaluation order are not a safe mechanism for executing business logic.

If you need to inspect database records or an external API to determine access, that logic usually belongs in an `AuthorizationManager` or a controlled domain service rather than a pure path/method `RequestMatcher`.

## 4. OrRequestMatcher: Only One Condition Needs to Hold

`OrRequestMatcher` combines matchers using the **OR** operation:

```text
OR(A, B, C) == A || B || C
```

Example of a group covering both reports and history:

```java
RequestMatcher reportOrHistory = new OrRequestMatcher(
    new AntPathRequestMatcher("/api/reports/**"),
    new AntPathRequestMatcher("/api/history/**")
);
```

| Request | Match reports? | Match history? | OR Result |
| --- | --- | --- | --- |
| GET `/api/reports/summary` | Yes | No | **true** |
| GET `/api/history/list` | No | Yes | **true** |
| GET `/api/other` | No | No | false |
| GET `/web/history/list` | No | No | false |

When two or more URL groups share the same authorization policy, `OrRequestMatcher` can group them into a single matcher instead of duplicating rules across multiple places.

### 4.1. Broader ORs Require Careful Review

Suppose while protecting a report-reading area, we accidentally write:

```java
RequestMatcher tooBroad = new OrRequestMatcher(
    new AntPathRequestMatcher("/api/reports/**"),
    new AntPathRequestMatcher("/**")
);
```

Because `/**` is too broad, most requests match even if they do not belong to reports. If `tooBroad` is paired with `permitAll()`, the application can unintentionally open access.

**Review rule:** inspect each OR branch individually, especially wildcards, broad prefixes, encoded paths, or paths with unusual separators.

### 4.2. OR Does Not Override URL Ordering Rules

In `authorizeHttpRequests`, an OR matcher can match many URLs, yet the chosen rule is still the **first** matching rule in the list. If an overly broad public rule appears before an internal rule, the configuration can accidentally permit internal routes.

## 5. NegatedRequestMatcher: Negating a Condition

`NegatedRequestMatcher` takes a `RequestMatcher` and inverts its result:

```text
NOT(A) == !A
```

Example:

```java
RequestMatcher notInternalReports =
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    );
```

Results:

- GET `/api/reports/summary` → true.
- GET `/api/reports/internal/plan` → false.
- GET `/api/other` → **true**.
- GET `/web/home` → **true**.

The last two cases are what people commonly overlook. **Negating one path branch does not automatically restrict to the rest of that same branch.** "Not belonging to internal reports" can include the website, other APIs, and URLs outside the intended scope.

### 5.1. Safer Negation: Pair With a Positive Scope

Instead of:

```java
// DANGEROUS if used as a permitAll matcher without a positive scope:
RequestMatcher notInternal =
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    );
```

First define the allowed region, then exclude within it:

```java
RequestMatcher readReportsExceptInternal = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new AntPathRequestMatcher("/api/reports/**"),
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    )
);
```

Then a GET `/api/other` is **not** passed through because it falls outside the positive reports scope, even though it satisfies NOT internal.

### 5.2. Negation Does Not Grant Higher Privilege

`NOT(internalPath)` is not `hasRole("READER")`. It only determines that the request does not belong to the internal path; authorization must still attach the appropriate role, authentication, or policy requirement.

For multi-tenant applications, a `NOT(/admin/**)` matcher cannot replace checking whether the user has access to a resource by owner/tenant in the service layer.

## 6. Combining All Three Matchers: GET AND (reports OR history) AND NOT internal

This is the core case of this lesson:

- Method must be GET.
- URL is inside `/api/reports/**` **or** `/api/history/**`.
- URL is not inside `/api/reports/internal/**`.
- The rule for the internal area is separate and prioritized before the general read rule.

Expression:

```text
READ_ALLOWED_PATH(request) =
    isGetApi(request)
    AND (
        inReports(request)
        OR inHistory(request)
    )
    AND NOT inInternalReports(request)
```

Matcher configuration:

```java
RequestMatcher readArea = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new OrRequestMatcher(
        new AntPathRequestMatcher("/api/reports/**"),
        new AntPathRequestMatcher("/api/history/**")
    ),
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    )
);
```

### 6.1. User-Independent Logic Test Table

| HTTP request | GET /api/** | Reports OR history | NOT internal | Composite |
| --- | --- | --- | --- | --- |
| GET `/api/reports/summary` | true | true | true | **true** |
| GET `/api/history/list` | true | true | true | **true** |
| POST `/api/reports/summary` | false | true | true | false |
| GET `/api/reports/internal/plan` | true | true | false | false |
| GET `/api/other` | true | false | true | false |
| GET `/web/reports/summary` | false | false | true | false |

Note that the composite result **does not ask which user is making the request**. A request for which the matcher returns true must still pass through an authorization rule, such as `hasAnyRole("READER", "ADMIN")`.

### 6.2. Reasoning With De Morgan's Laws

Identities that help review complex expressions:

```text
NOT (A OR B) == (NOT A) AND (NOT B)
NOT (A AND B) == (NOT A) OR (NOT B)
```

For example, "belongs to neither reports nor history" is `NOT(OR(reports,history))`. It is equivalent to `AND(NOT(reports), NOT(history))`, **not** `OR(NOT(reports), NOT(history))`.

A De Morgan mistake can cause a rule to match the very paths you meant to exclude. Testing against a true/false matrix catches this more reliably than inspecting the expression by eye.

### 6.3. Simplification and Naming Rules

Instead of hard-to-read inline nested classes inside `authorizeHttpRequests`, give variables meaningful names:

- `apiGet`;
- `reportOrHistory`;
- `notInternal`;
- `readArea`.

Variable names should reflect **request conditions**, not claim "user is allowed". For example, `readArea` still needs a role policy attached; never name it `authorizedReader` when the variable only has type RequestMatcher.

## 7. Combining With authorizeHttpRequests: Matcher vs. Authorization

Spring Security 6 uses `authorizeHttpRequests` to configure authorization rules for HTTP requests. Conceptual mechanism:

```text
HTTP request
     |
     v
FilterChainProxy selects SecurityFilterChain
     |
     v
Authentication filters / SecurityContext
     |
     v
AuthorizationFilter
     |
     +-- iterate registered rules in order
     +-- find the first request matcher returning true
     +-- run that rule's AuthorizationManager
     |
     +-- granted -> request proceeds
     +-- denied -> exception handling/entry point
```

A rule has two distinct parts:

```java
.requestMatchers(readArea).hasAnyRole("READER", "ADMIN")
```

- `requestMatchers(readArea)` decides **whether the request belongs to this area**.
- `hasAnyRole(...)` decides **whether the current Authentication has permission to enter that area**.

Therefore distinguish:

| Tool | Question It Answers |
| --- | --- |
| `AndRequestMatcher`/`OrRequestMatcher`/`NegatedRequestMatcher` | Does this request satisfy these HTTP conditions? |
| `hasRole`/`hasAuthority`/`authenticated` | Does the current identity satisfy the authorization policy? |
| `AuthenticationProvider`/`PasswordEncoder` | Is the proof of identity/password valid? |
| Controller/service ownership check | Does the user have permission to operate on **this specific record**? |

**Do not confuse matching with granting.** If you enable `.permitAll()` on a broad composite matcher, every matching request will pass that HTTP authorization rule regardless of user, unless another protective mechanism intervenes.

### 7.1. First-Matching Rule Order

Example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(new AntPathRequestMatcher("/api/reports/internal/**"))
        .hasRole("ADMIN")
    .requestMatchers(readArea)
        .hasAnyRole("READER", "ADMIN")
    .anyRequest().denyAll()
);
```

This is a configuration fragment assuming `readArea` exists. Internal comes before the general read rule to clearly express higher privilege. Even though the composite already excludes internal via NOT, this order makes the policy easy to review and avoids fragile dependence on a single matcher.

If reversed so a broader general rule **without NOT** sits above the internal rule, internal requests could hit the general policy prematurely. **Two rules with overlapping URLs do not combine with AND automatically**; the first matching rule is chosen.

### 7.2. denyAll Fallback

`.anyRequest().denyAll()` ensures undefined routes are not allowed by default. In real web applications, explicitly permit public URLs such as static assets, error pages, and health endpoints as required. In the sample API project, only `GET /api/public/status` is public.

## 8. securityMatcher and requestMatchers: Two Different Layers

Both use the `RequestMatcher` type, yet their meaning depends on where they are attached:

- `http.securityMatcher(...)` determines **whether a SecurityFilterChain processes the request**.
- `authorizeHttpRequests(...).requestMatchers(...)` determines **which authorization rule applies inside the selected chain**.

Suppose there are two chains:

```text
@Order(1) API chain:
    securityMatcher("/api/**")
    Basic authentication
    HTTP authorization rules, including readArea

@Order(2) Web fallback:
    formLogin
    HTML session / other web routes
```

`FilterChainProxy` selects the first matching chain. When a `/api/reports/summary` request enters the API chain, the web chain **does not run afterward**. If a custom API matcher has an overly broad NOT and the API chain sits before the web fallback, it can pick the wrong chain for web URLs.

Example of a **dangerous scope error**:

```java
// Do not use as the API chain matcher if the goal is only to cover /api/**:
http.securityMatcher(
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/internal/**")
    )
);
```

That matcher matches almost every URL outside `/api/internal/**`, including `/web/home`. If placed on a high-priority chain, it can hijack web requests meant for form login.

Better reasoning: use positive scope `/api/**` and AND with genuinely necessary exceptions, or keep the API chain matcher simple with `securityMatcher("/api/**")` and place complex authorization matchers **inside the chain**.

## 9. Choosing Path Matchers and HTTP Methods: Practical Notes

### 9.1. Pattern vs. URI, Query, and Servlet Path

For example, pattern `/api/reports/**` is a path matcher; a query string like `?sort=date` is not part of the path under common `AntPathRequestMatcher` semantics.

In a simple test:

```text
GET /api/reports/summary?sort=date
path evaluated by matcher: /api/reports/summary
query: sort=date
```

When the app runs under a context path like `/myapp`, distinguish `requestURI`, `contextPath`, `servletPath`, and `pathInfo` per implementation. Never take `request.getRequestURI()` and compare directly against `"/api/..."` ignoring context path.

`AntPathRequestMatcher` in the example matches against the Servlet API path (typically `servletPath + pathInfo`); test carefully if `DispatcherServlet` is not mapped at `/`, or if a proxy rewrites paths.

### 9.2. AntPathRequestMatcher Is Version-Sensitive

The hands-on example uses Spring Boot 3.3.5 (Spring Security 6.3.x) and `AntPathRequestMatcher` for transparent syntax. In newer Spring Security versions, matcher APIs/recommendations may change. When upgrading:

- Consult the official documentation for your exact version.
- Consider `MvcRequestMatcher` or `PathPatternRequestMatcher` where appropriate.
- Verify results with contextPath, servletPath, URL encoding, trailing slashes, and path variables.
- Do not migrate a pattern from Ant to PathPattern assuming completely identical semantics.

**Security depends on the path the server actually processes**, not merely how a pattern looks in code.

### 9.3. Method Matchers Match Requests, They Are Not a CSRF Policy

`new AntPathRequestMatcher("/api/**", "GET")` only matches GET. It does not enable/disable CSRF itself and does not govern whether POST can mutate data. With HTTP Basic on APIs, browsers may automatically resend credentials in certain scenarios; CSRF policy for state-changing endpoints must be evaluated against the threat model.

The sample below **only declares GET endpoints**, keeps default CSRF protection intact, and does not claim statelessness as sufficient reason to disable CSRF.

### 9.4. Avoid Custom Matchers Doing Dangerous Work

A good RequestMatcher should be **fast, deterministic, and side-effect-free**, reading only necessary request attributes.

Do not:

- Read and consume the one-shot request body so the controller can no longer read it.
- Query a database or external API on every request just to decide path matching.
- Grant permissions based on unverified, client-supplied headers.
- Run expensive regexes against unbounded attacker-controlled input.
- Log raw Authorization headers, cookies, or session IDs while debugging.
- Replace Servlet/Spring MVC normalization logic inconsistently.

## 10. Runnable Spring Boot 3.3.5 + Java 17 Example

The application models a report-reading API. Policy:

1. `GET /api/public/status` allows anonymous access.
2. `GET /api/reports/internal/**` is for `ROLE_ADMIN` only.
3. `GET /api/reports/**` or `GET /api/history/**`, excluding `/api/reports/internal/**`, is for `ROLE_READER` or `ROLE_ADMIN`.
4. All other requests are rejected by `denyAll`.
5. Authentication uses HTTP Basic with in-memory users to exercise matcher logic.

### 10.1. Directory Structure

```text
request-matcher-composition/
  pom.xml
  src/
    main/java/example/matcher/
      MatcherApplication.java
      SecurityConfig.java
      ApiController.java
    test/java/example/matcher/
      MatcherIntegrationTest.java
```

### 10.2. pom.xml

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

    <groupId>example</groupId>
    <artifactId>request-matcher-composition</artifactId>
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

### 10.3. Startup Class

File `src/main/java/example/matcher/MatcherApplication.java`:

```java
package example.matcher;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatcherApplication.class, args);
    }
}
```

### 10.4. SecurityConfig.java: AND, OR, NOT in HTTP Authorization

File `src/main/java/example/matcher/SecurityConfig.java`:

```java
package example.matcher;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.NegatedRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    static RequestMatcher readAreaMatcher() {
        RequestMatcher getApi =
            new AntPathRequestMatcher("/api/**", "GET");

        RequestMatcher reportOrHistory = new OrRequestMatcher(
            new AntPathRequestMatcher("/api/reports/**"),
            new AntPathRequestMatcher("/api/history/**")
        );

        RequestMatcher notInternal = new NegatedRequestMatcher(
            new AntPathRequestMatcher("/api/reports/internal/**")
        );

        return new AndRequestMatcher(
            getApi, reportOrHistory, notInternal
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    new AntPathRequestMatcher("/api/public/status", "GET")
                ).permitAll()
                .requestMatchers(
                    new AntPathRequestMatcher("/api/reports/internal/**")
                ).hasRole("ADMIN")
                .requestMatchers(readAreaMatcher())
                    .hasAnyRole("READER", "ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Demo data only has GET; keep default CSRF.
        return http.build();
    }
}
```

Notable points:

- `readAreaMatcher()` builds a **composite matcher**; on its own it does not know whether the user is a reader or an admin.
- `new OrRequestMatcher(...)` permits either reports or history.
- `new NegatedRequestMatcher(...)` excludes internal reports from the general read branch.
- `new AndRequestMatcher(...)` requires simultaneously the GET method, belonging to reports/history, and being non-internal.
- The internal rule comes before the general read rule and requires `ROLE_ADMIN`.
- `hasAnyRole("READER", "ADMIN")` is the authorization check, not part of RequestMatcher.
- `anyRequest().denyAll()` enforces **deny by default**. New routes must be declared with explicit rules.
- `STATELESS` and `NullSecurityContextRepository` indicate HTTP Basic requests do not rely on a prior login session; each request sends credentials when needed.
- `NullRequestCache` disables saving URLs for HTML redirects. Unauthenticated API calls return a Basic challenge (401), not form login.
- CSRF policy for write endpoints is not designed in this lesson; do not copy a pure GET API config into a production POST setup without evaluation.

### 10.5. Controller Defining Test Endpoints

File `src/main/java/example/matcher/ApiController.java`:

```java
package example.matcher;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public/status")
    String status() {
        return "status:ok";
    }

    @GetMapping("/api/reports/summary")
    String summary(Authentication authentication) {
        return "reports:" + authentication.getName();
    }

    @GetMapping("/api/history/list")
    String history(Authentication authentication) {
        return "history:" + authentication.getName();
    }

    @GetMapping("/api/reports/internal/plan")
    String internal(Authentication authentication) {
        return "internal:" + authentication.getName();
    }
}
```

The controller does not make its own permission checks via `if (path.startsWith(...))`. HTTP authorization happens before the controller receives the request. In a real application, when a controller looks up a report by ID, ownership/tenant checks must be added in the service.

### 10.6. MockMvc Integration Tests

File `src/test/java/example/matcher/MatcherIntegrationTest.java`:

```java
package example.matcher;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MatcherIntegrationTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequest request(String method, String path) {
        MockHttpServletRequest request =
            new MockHttpServletRequest(method, path);

        // AntPathRequestMatcher uses Servlet path/pathInfo to match.
        request.setServletPath(path);
        return request;
    }

    @Test
    void andRequiresAllConditions() {
        RequestMatcher matcher = SecurityConfig.readAreaMatcher();

        assertTrue(matcher.matches(
            request("GET", "/api/reports/summary")));

        assertFalse(matcher.matches(
            request("POST", "/api/reports/summary")));

        assertFalse(matcher.matches(
            request("GET", "/api/other")));
    }

    @Test
    void orMatchesEitherArea() {
        RequestMatcher matcher = SecurityConfig.readAreaMatcher();

        assertTrue(matcher.matches(
            request("GET", "/api/reports/summary")));

        assertTrue(matcher.matches(
            request("GET", "/api/history/list")));
    }

    @Test
    void negationExcludesInternalReports() {
        RequestMatcher matcher = SecurityConfig.readAreaMatcher();

        assertFalse(matcher.matches(
            request("GET", "/api/reports/internal/plan")));

        assertTrue(matcher.matches(
            request("GET", "/api/reports/summary")));
    }

    @Test
    void notAloneWouldBeTooBroad() {
        RequestMatcher notInternal =
            new org.springframework.security.web.util.matcher
                .NegatedRequestMatcher(
                    new org.springframework.security.web.util.matcher
                        .AntPathRequestMatcher(
                            "/api/reports/internal/**")
                );

        // Negating one specific URL still matches paths outside the API.
        assertTrue(notInternal.matches(
            request("GET", "/web/home")));

        // But AND with positive path scope does not match outside the API.
        assertFalse(SecurityConfig.readAreaMatcher().matches(
            request("GET", "/web/home")));
    }

    @Test
    void queryStringDoesNotChangePathMatch() {
        MockHttpServletRequest request =
            request("GET", "/api/reports/summary");
        request.setQueryString("sort=date");

        assertTrue(SecurityConfig.readAreaMatcher().matches(request));
    }

    @Test
    void anonymousCanReadPublicStatus() throws Exception {
        mvc.perform(get("/api/public/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("status:ok"));
    }

    @Test
    void anonymousReportGetsBasicChallenge() throws Exception {
        MvcResult response = mvc.perform(
                get("/api/reports/summary"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge = response.getResponse()
            .getHeader("WWW-Authenticate");
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void readerCanReadReportsAndHistory() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports:reader"));

        mvc.perform(get("/api/history/list")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("history:reader"));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("reader", "wrong-demo")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotOpenInternalPlan() throws Exception {
        mvc.perform(get("/api/reports/internal/plan")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenInternalPlan() throws Exception {
        mvc.perform(get("/api/reports/internal/plan")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("internal:admin"));
    }

    @Test
    void unknownPathIsDeniedEvenForAuthenticatedReader()
            throws Exception {
        mvc.perform(get("/api/other")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isForbidden());
    }
}
```

The tests have two clear layers:

1. **Boolean testing of RequestMatcher** with `MockHttpServletRequest`: path and method; OR for reports/history, NOT excluding internal, positive scope preventing NOT from opening too broadly.
2. **HTTP integration tests** with `MockMvc` through the Spring Security filter chain: 200 for public/authorized routes, 401 for missing/wrong Basic credentials, 403 for an authenticated reader lacking permissions or requests outside rules.

Using `httpBasic("reader", "...")` sends an actual Basic header, instead of `.with(user("reader"))` which creates a mock principal and skips password verification.

**The tests do not measure load or matcher performance.** If performance evaluation is needed, benchmark in an appropriate environment and avoid matchers with external resource lookups.

### 10.7. Running Maven and Observing Results

With JDK 17+ and Maven, inside the `request-matcher-composition` directory:

```bash
mvn test
mvn spring-boot:run
```

If dependencies and environment match, **12 tests are expected to pass**. This is an expectation from the source code, not an actual Maven output run here. Test/build logs do not have a fixed stdout.

You can test with `curl` against the **demo localhost**:

```bash
curl -i http://localhost:8080/api/public/status
curl -i http://localhost:8080/api/reports/summary
curl -i -u reader:reader-demo http://localhost:8080/api/reports/summary
curl -i -u reader:reader-demo http://localhost:8080/api/history/list
curl -i -u reader:reader-demo http://localhost:8080/api/reports/internal/plan
curl -i -u admin:admin-demo http://localhost:8080/api/reports/internal/plan
curl -i -u reader:reader-demo http://localhost:8080/api/other
```

**Do not use unencrypted HTTP with real credentials.** `curl -u` puts passwords on the command line where they can leak via shell history or process listings; only use illustrative passwords on a learning machine.

Expected result table:

| Request | Result | Reason |
| --- | --- | --- |
| GET `/api/public/status` anonymous | 200 `status:ok` | Public rule |
| GET `/api/reports/summary` anonymous | 401 + Basic challenge | Composite matches, but missing authentication |
| GET `/api/reports/summary` reader Basic | 200 `reports:reader` | AND/OR/NOT matches and `ROLE_READER` |
| GET `/api/history/list` reader Basic | 200 `history:reader` | Second OR branch matches |
| GET `/api/reports/internal/plan` reader Basic | 403 | Internal rule is admin-only |
| GET `/api/reports/internal/plan` admin Basic | 200 `internal:admin` | Internal rule and valid role |
| GET `/api/other` reader Basic | 403 | Matches no specific rule, `denyAll` |
| GET `/api/reports/summary` wrong Basic password | 401 | Authentication rejected before access check |

## 11. Standalone Java 17: Writing an AND, OR, NOT Model Yourself

To see the truth table without Spring Boot or Maven, we can create a plain Java 17 program. It illustrates boolean composition, and **does not replace** `RequestMatcher` or Spring Security's Servlet path semantics.

Create `CompositeMatcherLogicDemo.java`:

```java
public class CompositeMatcherLogicDemo {

    @FunctionalInterface
    interface Match {
        boolean matches(String method, String path);
    }

    static Match and(Match... conditions) {
        return (method, path) -> {
            for (Match condition : conditions) {
                if (!condition.matches(method, path)) {
                    return false;
                }
            }
            return true;
        };
    }

    static Match or(Match... conditions) {
        return (method, path) -> {
            for (Match condition : conditions) {
                if (condition.matches(method, path)) {
                    return true;
                }
            }
            return false;
        };
    }

    static Match not(Match condition) {
        return (method, path) ->
            !condition.matches(method, path);
    }

    static boolean inside(String path, String root) {
        return path.equals(root) || path.startsWith(root + "/");
    }

    public static void main(String[] args) {
        Match get = (method, path) -> "GET".equals(method);
        Match api = (method, path) -> inside(path, "/api");
        Match reports = (method, path) ->
            inside(path, "/api/reports");
        Match history = (method, path) ->
            inside(path, "/api/history");
        Match internal = (method, path) ->
            inside(path, "/api/reports/internal");

        Match readArea = and(get, api,
            or(reports, history), not(internal));

        String[][] cases = {
            {"GET", "/api/reports/summary"},
            {"GET", "/api/history/list"},
            {"POST", "/api/reports/summary"},
            {"GET", "/api/reports/internal/plan"},
            {"GET", "/api/other"},
            {"GET", "/web/home"}
        };

        for (String[] sample : cases) {
            System.out.printf("%s %s -> %b%n",
                sample[0], sample[1],
                readArea.matches(sample[0], sample[1]));
        }
    }
}
```

Compile and run:

```bash
javac CompositeMatcherLogicDemo.java
java CompositeMatcherLogicDemo
```

**Exact** stdout with Java 17:

```text
GET /api/reports/summary -> true
GET /api/history/list -> true
POST /api/reports/summary -> false
GET /api/reports/internal/plan -> false
GET /api/other -> false
GET /web/home -> false
```

This program intentionally simplifies a request to two strings `method` and `path`. It does not understand servlet context paths, URL decoding, proxy rewriting, HTTP headers, PathPattern, or sessions. The Maven/MockMvc section above is what tests Spring Security Servlet's actual `RequestMatcher`.

## 12. Other Useful Designs

### 12.1. Public GET for Multiple Paths, Excluding Internal

Suppose an application allows anonymous GET to public endpoints under `/api/public/**` and `/api/docs/**`, but excludes `/api/docs/internal/**`. You can use:

```java
RequestMatcher publicGet = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new OrRequestMatcher(
        new AntPathRequestMatcher("/api/public/**"),
        new AntPathRequestMatcher("/api/docs/**")
    ),
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/docs/internal/**")
    )
);
```

When registering:

```java
// Illustration inside authorizeHttpRequests, not a standalone program:
.requestMatchers(publicGet).permitAll()
```

This is a **sensitive** case, because `permitAll` waives login requirements for all matching requests. Directly test `/api/docs/internal/secret`, `/api/other`, and all state-changing methods. Never put an OR containing `/**`.

### 12.2. Selecting a Dedicated Filter Chain for an API Area

Suppose you want a dedicated chain for API GET reports/history, while other APIs sit in a fallback. When using a composite inside `securityMatcher`, analyze:

- Does a POST request to the same URL enter another chain and remain protected?
- Is there an appropriate fallback chain for `/api/reports/internal/**`?
- Where does `/api/reports/internal/**` go when excluded from the current chain?
- Do URLs matching no chain bypass Spring Security protection?
- Do form login/HTTP Basic/CSRF and entry points on the selected chain provide the right experience?

If only authorization rules differ within the same API, it is **usually simpler** to keep one API chain `securityMatcher("/api/**")` and use composite matchers in `authorizeHttpRequests` as in the sample lesson. Only split into multiple chains when authentication, sessions, entry points, or filter composition truly differ.

### 12.3. Method Matchers Are Not a Write-Safety Policy

For instance, a GET-only matcher prevents accidentally applying a general read rule to POST, yet does not guarantee all write operations are safe. State-changing endpoints need the right method, authentication, authorization, CSRF protection where appropriate, input validation, ownership checks, and idempotency/transactions as required.

A `POST /api/reports/**` rule can use a separate method matcher and `hasRole("EDITOR")`, while still checking the validity of the authentication source and actual data writes in the service.

## 13. Security and Reviewing Matcher Expressions

### 13.1. Checklist Against Over-Broadening Scope

- Does every `NegatedRequestMatcher` used with `permitAll` or a chain matcher have a sufficiently narrow **positive scope**?
- Does any branch of `OrRequestMatcher` have an overly broad wildcard?
- Does a GET matcher accidentally apply to POST/PUT/DELETE?
- Does an internal URL fall into a broader public rule due to matcher order?
- Are appropriate `denyAll`/`authenticated` fallbacks and complete chain coverage in place?
- With multiple security chains, which chain does `FilterChainProxy` select first?
- Are queries, path encoding, trailing slashes, context paths, and servlet paths tested?
- Are public static/health/error URLs blocked unintentionally?
- When enabling `permitAll`, do you distinguish "no Authentication required" from "skips security filters"?

### 13.2. Path Authorization Does Not Replace Object-Level Authorization

Suppose `GET /api/reports/812` matches `readArea` and the user has `ROLE_READER`. Are they guaranteed permission to view report 812? **No**: the report might belong to another tenant.

Check permissions on the specific resource at the business layer—for instance, the service fetches the report by owner/tenant and verifies the user. Protecting `/api/reports/**` at the HTTP level alone does not solve IDOR/BOLA.

### 13.3. Matcher Behavior With Unusual Requests

Encoded URLs, double slashes, semicolon/matrix parameters, case sensitivity, and proxy/container normalization can create discrepancies between the path the matcher sees and the route the handler processes. Avoid writing custom matchers on raw URIs using `startsWith` without canonicalization and path-segment boundary checks.

With Spring MVC, choose and test matchers compatible with framework routing. Some Spring Security firewall settings may reject dangerous requests before matchers run; never rely solely on a dev example to claim all encoded paths are handled identically in production.

### 13.4. Observability Without Leaking Secrets

You can enable debug logging in development:

```properties
logging.level.org.springframework.security=DEBUG
```

To understand why a request does not reach a controller, inspect the security chain, matched rule, authentication state, and response status. Never log raw cookies, passwords, Authorization headers, session IDs, or access tokens. A "wrong" matcher may simply be the request entering a different chain, rather than broken AND/OR/NOT boolean logic.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `NegatedRequestMatcher(internal)` directly with `permitAll` | Permits paths outside the intended region | AND with a clear positive scope |
| Using OR instead of AND between path and method | GET outside path or POST inside path can match | Use AND(method, scope) |
| Confusing `NOT(A OR B)` with `NOT A OR NOT B` | Exclusion logic violates De Morgan's law | Use NOT(OR(...)) or AND(NOT A, NOT B) |
| Putting `/**` inside an OR branch | Composite matcher becomes too broad | Review wildcards, use specific paths |
| Placing general `permitAll` before internal rule | Internal paths can become public | Put specialized matchers first, test rule order |
| Placing `anyRequest` before specific rules | Later rules fail to run or config errors | Keep fallback at the end |
| Thinking matcher true means the user is authorized | Skips Authentication/authorities | Pair with an appropriate `AuthorizationManager` |
| Using client-set `X-Role` header to verify admin | Clients can spoof privileges | Use Authentication from trusted sources |
| Hand-rolled `startsWith("/api/report")` | `/api/report-evil` can also match | Use an appropriate path-aware matcher |
| Matching raw requestURI without context path | Breaks when deployed under a subpath | Use Servlet-aware matchers, test context/servlet paths |
| Thinking queries are part of Ant path patterns | Semantically wrong tests | Distinguish query and path |
| Combining matchers without testing HTTP statuses | Authentication/entry point may differ from expectation | Test both `matches` and MockMvc |
| Testing only with an admin user | Fails to catch reader accessing internal paths | Test anonymous/reader/admin |
| Changing matcher implementation during upgrade without testing | Trailing slash/encoded path semantics differ | Pin version, run boundary integration tests |
| Using matchers with side effects | Unpredictable behavior, body/DB errors | Keep matchers pure request predicates |
| Using an overly broad composite as `securityMatcher` | API chain swallows web requests | Restrict chain with positive API scope |
| Thinking stateless + HTTP Basic never needs CSRF | Browsers can auto-send Basic credentials | Evaluate CSRF per client and threat model |
| Missing fallback chain/rule | URLs may go unprotected or get wrong permissions | Design chain coverage and proper fallbacks |
| Assuming path matchers sufficiently protect resource IDs | IDOR/BOLA can occur | Add owner/tenant authorization |
| Logging raw Authorization headers to debug matchers | Leaks credentials | Log only safe paths/traces/decisions |

## 15. Systematic Workflow to Debug a Mis-Matched Request

1. **Verify the actual URL and method**, not just what the developer expected. Browsers may send `HEAD`/`OPTIONS` or follow other redirects.
2. **Verify the SecurityFilterChain**: `securityMatcher`, `@Order`, fallback chain, and authentication mechanism.
3. **Inspect each component matcher**: GET? reports? history? internal? Record boolean results in a controlled test.
4. **Check parentheses in AND/OR/NOT**. `AND(GET, OR(A,B), NOT(C))` differs from `OR(AND(GET,A),B,NOT(C))`.
5. **Distinguish matcher false from authorization denied**. A false matcher lets later rules apply; a true matcher can still yield 401/403 if credentials/roles are missing.
6. **Check `requestMatchers` order** in `authorizeHttpRequests`; the first matching rule is used.
7. **Check API path vs. servlet path**, context path, proxy rewrites, and encoding.
8. **Check what wildcards actually match**, especially `/**`, `/api/**`, and nested paths.
9. **Check the authentication scheme**: Basic 401, form login 302, or custom JSON 401 is not decided by the matcher alone.
10. **Check CSRF on POST**, and do not confuse a CSRF HTTP 403 with a matcher/role denial.
11. **Check permissions on the resource ID** in the service even when HTTP rules grant access.
12. **Check regression tests** for internal URLs, unknown URLs, other methods, anonymous callers, and low-authority users.
13. **Compare framework versions** if behavior changed after upgrading matchers.
14. **Never expose raw credentials** in logs during investigation.

## 16. Self-Check Exercises

**Q1.** Does `AND(GET, reports)` match `POST /api/reports/summary`?

**Answer:** No. The path matches but the method is not GET, so AND returns false.

**Q2.** Does `OR(reports, history)` match `GET /api/history/list`?

**Answer:** Yes, because one matching OR branch is enough.

**Q3.** Does `NOT(internalReports)` match `GET /web/home`?

**Answer:** Yes. `/web/home` does not belong to `internalReports`, so negation returns true. That is why a positive scope must be added to avoid over-matching.

**Q4.** A composite matcher matches GET reports and the user is not logged in. Can they access the data automatically?

**Answer:** No. The matcher only selects the rule; authorization can still require authenticated/role and return a Basic challenge or form login.

**Q5.** Why is placing `/api/**.permitAll()` before `/api/reports/internal/**.hasRole("ADMIN")` dangerous?

**Answer:** Because the first matching rule decides authorization; the broad matcher ahead can permit internal paths before the admin rule is evaluated.

**Q6.** Are `NOT(A OR B)` and `OR(NOT A, NOT B)` equivalent?

**Answer:** No. `NOT(A OR B)` equals `AND(NOT A, NOT B)` by De Morgan's law.

**Q7.** When deploying at context path `/app`, should you compare `getRequestURI().startsWith("/api/")` directly?

**Answer:** Do not rely on that without handling the context path. Use an appropriate Servlet/MVC matcher and test the full environment.

**Q8.** Two SecurityFilterChain beans both match a request; which one runs?

**Answer:** `FilterChainProxy` selects the first matching chain according to configuration order. It does not run all chains sequentially to combine rules.

**Q9.** A matcher returns true for `/api/reports/812` and the user has `ROLE_READER`. Is the user automatically allowed to view another tenant's report?

**Answer:** No. Object-level authorization at the service/ownership/tenant layer is required, not just path and role checks.

**Q10.** If you want anonymous GET under `/api/public/**` except `/api/public/internal/**`, what should you write?

**Answer:** An `AndRequestMatcher` containing a GET matcher, a positive public path matcher, and a `NegatedRequestMatcher` for internal. Then attach `permitAll` if the policy is truly public, position sensitive rules appropriately, and test boundaries.

## 17. Key Takeaways

- `AndRequestMatcher` is **AND**: all conditions must hold.
- `OrRequestMatcher` is **OR**: at least one condition must hold.
- `NegatedRequestMatcher` is **NOT**: inverts one matcher's result.
- A standalone negation easily **matches too broadly outside the intended scope**, so pair it with a positive path/method scope.
- Boolean-composed matchers only answer "**does the request belong to this group?**"; `authorizeHttpRequests` and `AuthorizationManager` answer "**is the user authorized?**".
- HTTP rules use the **first matching matcher**; with multiple security chains, `securityMatcher` selects the chain and `requestMatchers` selects the rule inside that chain.
- Never overlook HTTP methods, query vs. path, servlet context paths, matcher versions, URL normalization, and object-level permissions.
- Test `matches` directly with Servlet requests and also test **200/401/403** responses via `MockMvc` to catch AND/OR/NOT composition bugs, rule ordering errors, and authority mistakes.
