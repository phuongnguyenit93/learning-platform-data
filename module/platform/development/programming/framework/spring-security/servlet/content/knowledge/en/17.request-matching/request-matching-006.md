# PathPatternRequestMatcher and Version Compatibility Conditions

> **Scope:** Spring Security on the **Servlet stack**, Java 17+, Spring Boot 3.x / Spring Security 6.x, and migrating to newer versions. This lesson focuses on `org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher`: its role, path syntax, builder usage, differences from `AntPathRequestMatcher` / `MvcRequestMatcher`, `contextPath`–`servletPath` boundaries, version compatibility requirements, changes in URL matching, and testing approaches. **Do not assume PathPatternRequestMatcher is present in every Spring Security 6.x release.** The Spring example is code for a project with full dependencies; the Java 17 example in the final section runs standalone.

## 1. Where Does RequestMatcher Sit in HTTP Security?

`RequestMatcher` answers a narrow question: **does the current HTTP request satisfy an identification condition?** The condition may involve path, HTTP method, servlet path, or other request components depending on the implementation.

In Spring Security Servlet, matchers are used at at least two levels:

~~~text
Client HTTP request
         |
         v
FilterChainProxy
   |-- SecurityFilterChain #1  -- securityMatcher: /api/**
   |         |
   |         +-- CSRF, authentication, authorization, ...
   |               |
   |               +-- authorizeHttpRequests
   |                   GET  /api/orders/{id} -> ORDER_READ
   |                   POST /api/orders/{id} -> ORDER_WRITE
   |                   anyRequest()         -> denyAll
   |
   |-- SecurityFilterChain #2  -- match remaining
   |         |
   |         +-- web/session/fallback policy
   |
   v
Controller if passed through security filters
~~~

These two levels are very different:

- `http.securityMatcher(...)` decides **which SecurityFilterChain** covers the request. If no chain matches, the request may pass through without Spring Security filters, depending on configuration.
- `authorizeHttpRequests(...).requestMatchers(...)` decides **which authorization rule** applies **inside the selected chain**.
- A `RequestMatcher` can be used at either level, but where it is placed changes its effect. Replacing `securityMatcher` with `requestMatchers` is not just renaming an API.
- A `RequestMatcher` **does not authenticate users itself**, does not check roles/scopes itself, and does not guarantee a controller route exists. Only the authorization manager evaluates `Authentication` and rules once the request matches.

For example, if HTTP URL `/api/orders/42` matches the matcher but the user lacks `ORDER_READ`, the matcher still behaved properly; **authorization** is what decides whether the request may proceed.

## 2. Why Does Spring Security Have Multiple Path Matcher Types?

The Spring ecosystem historically used character-based path matching (`AntPathMatcher` and `AntPathRequestMatcher`) and Spring MVC routing integration (`MvcRequestMatcher` with `HandlerMappingIntrospector`). Modern Spring Framework provides `PathPatternParser` / `PathPattern` to pre-parse URL patterns and then match structurally by path segments rather than legacy string comparisons.

`PathPatternRequestMatcher` belongs to **Spring Security Web Servlet** and builds on Spring Framework's `PathPattern` mechanism. Benefits of this approach:

- Uses a pre-parsed path pattern model optimized for request-path matching.
- Clear segment syntax, handling wildcards and path variables under more consistent rules.
- Easy declaration of explicit **HTTP method + path** matchers so authorization does not unintentionally open write methods.
- Aligns with the evolution of Spring MVC / Spring Security away from legacy Ant-style matchers.

**False assumption:** "Switching to PathPatternRequestMatcher automatically makes every endpoint secure." You still need proper chain matching, proper rules, trusted `GrantedAuthority` sources, suitable CSRF/session policies, and object-level permission checks at the service layer.

## 3. Version Applicability Conditions: Check Before Writing Imports

This is the core point of the lesson.

| Environment | Status / Recommended Handling |
| --- | --- |
| Spring Security 6.0–6.4 | Do not assume class `PathPatternRequestMatcher` exists. Use the matcher API **supported by that version**, e.g., `requestMatchers(...)` suited for MVC/Servlet; re-evaluate semantics when migrating. |
| Spring Security 6.5.x | `PathPatternRequestMatcher` is available in newer releases of the 6.x line; you can use **explicit matchers** with its corresponding builder API. Verify the exact 6.5.x release and actual resolved dependency. |
| Spring Security 7.x | Newer API direction favors `PathPattern`-based matchers; older matchers may be replaced or unsupported compared to 6.x. When upgrading major versions, read that version's migration guide and run regression tests. |
| Spring Boot 3.x | Boot 3.x does **not equal** "Security 6.5". Different Boot minor versions manage different Security 6.x releases. Examples using `PathPatternRequestMatcher` only compile when the Security dependency actually includes the class. |
| Spring Boot 4.x or custom dependency management | Do not blindly infer APIs from the Boot version; verify the actual versions of `spring-security-web` and `spring-security-config`. |

**Milestone note:** this class was introduced in the **Spring Security 6.5** line; thus sample code with `PathPatternRequestMatcher.withDefaults()` may **fail to compile on Spring Security 6.4 or earlier**. If the build reports `cannot find symbol: PathPatternRequestMatcher`, check versions and dependencies first instead of inventing package names from an online snippet.

How to check resolved dependencies in a Maven project:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

Gradle example with the Java plugin:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

You can filter output for artifacts `spring-security-web`, `spring-security-config`, and `spring-security-core`. Command output varies per project; no fixed transcript is shown. When using Spring Boot dependency management/BOM, prefer managing **all Spring Security artifacts in lockstep**. Avoid bumping only `spring-security-web` to 6.5 while keeping an older `spring-security-config`, as that creates an untested combination.

Also distinguish **deprecation** from **removal**:

- "Deprecated in 6.x" means the IDE recommends migrating gradually; it does not mean the API suddenly vanishes in the current release.
- "Removed in a new major version" requires updating imports/configuration upon upgrading.
- Follow the **migration guide for your exact version** instead of guessing from an article written for another version.

### Library and Java Version Issues

PathPatternRequestMatcher resides in the Spring Security Web (Servlet) artifact. A missing class can be caused by:

1. Security version older than the milestone supporting it.
2. Missing `spring-security-web` dependency.
3. Stale IDE cache/language server dependency state.
4. BOM or dependency override causing a version mismatch between modules.
5. Coding for the WebFlux reactive stack instead of Servlet.

`PathPatternRequestMatcher` discussed here is a Servlet API. With Spring WebFlux, security chains and matchers use a different API (`ServerWebExchangeMatcher`); never copy Servlet imports directly into a reactive stack.

## 4. PathPattern Syntax: Thinking in Segments

Spring Framework's `PathPatternParser` supports useful pattern forms:

| Pattern | Intended Meaning |
| --- | --- |
| `/api/orders` | Matches the exact path. |
| `/api/orders/{id}` | Single segment representing variable `id`. |
| `/api/orders/*` | Single wildcard within one path segment. |
| `/api/orders/**` | Remaining path portion; used at the **end of a pattern**. |
| `/api/orders/{*rest}` | Captures the remaining path into a path variable (when needed). |
| `/files/{name:[a-z0-9-]+}` | Path variable with a regex constraint. |
| `/docs/?.pdf` | `?` represents a single character within a segment per supported syntax. |

Key difference from Ant-style patterns: **`**` and `{*variable}` may only appear at the end of a pattern** in `PathPattern`; this model prevents certain ambiguous mid-path matches.

Problematic example when migrating from Ant-style:

~~~text
/archives/**/download
~~~

Do not assume you can move that string verbatim to `PathPatternRequestMatcher`. In `PathPattern` syntax, `**` is not allowed in the middle of a pattern like that. Redesign the route/matcher, perhaps with multiple specific patterns or a clearer path structure, and test against real data.

### Distinguishing `*`, `**`, and `{id}`

- `{id}` represents a path variable; in `/orders/{id}`, the id value does not automatically prove ownership of the order.
- `*` matches characters within one segment, not arbitrarily across multiple slashes like `**`.
- `**` at the end can match path segments under the prefix; exact behavior at slash/trailing-slash boundaries depends on parser settings and must be tested.
- `{*rest}` captures multiple remaining segments for pattern matching, yet application code must still validate/separate permissions appropriately.
- `?` inside a pattern is a **single-character** wildcard, not a query string; an actual `?` in a URL after the path is the query delimiter and must not be put into a path pattern in normal usage.

Example:

~~~text
Request: GET /api/orders/42?tab=history

Path used for matching: /api/orders/42
Query string: tab=history

Pattern: /api/orders/{id}
=> matches path (if method also matches)
~~~

Using query parameters to control permissions is a separate issue: if a token/key is only authorized to view the user's own orders, a matching path and valid query syntax are **not enough** to allow reading another resource.

### Encoding, Slashes, and Case

For encoded paths, `%2F`, `;` (matrix parameters), Unicode normalization, repeated slashes, backslashes, and unusual characters, **never guess the match result from the raw URL string**. Servlet containers, firewalls, proxies, and PathPatternParser may canonicalize, block, or parse at different layers. Under strict firewall settings, dangerous requests may be rejected **before any matcher runs**.

Therefore, tests must verify against the real deployment environment and not rely on simplistic ideas like "decoding once is enough". In systems with custom `HttpFirewall`, path normalization, and proxy rewriting, test end-to-end.

## 5. Creating PathPatternRequestMatcher With the Builder

In Spring Security versions that support the class, such as Spring Security 6.5+, use the builder:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

// CODE SNIPPET inside a method of a Spring Security app supporting this API:
PathPatternRequestMatcher.Builder paths =
        PathPatternRequestMatcher.withDefaults();

RequestMatcher allApi = paths.matcher("/api/**");
RequestMatcher getOrder = paths.matcher(
        HttpMethod.GET, "/api/orders/{id}");
RequestMatcher postOrder = paths.matcher(
        HttpMethod.POST, "/api/orders/{id}");
~~~

This is a **code snippet**, not a standalone Java class. The builder's `matcher(...)` method produces a `RequestMatcher` to pass into the DSL. Without a compatible Spring Security dependency, `javac` alone cannot compile it.

**Why use an explicit matcher object?**

- It makes the choice of `PathPattern` explicit instead of relying on DSL inference from strings.
- It reuses a clear path/method policy across `securityMatcher` and `authorizeHttpRequests`.
- It prevents dependency upgrades or adding/removing MVC from silently switching `requestMatchers("/...")` to another matcher implementation without the developer noticing.
- The matcher can be unit-tested before applying it to HTTP authorization.

However, **an explicit matcher does not replace verifying identity/authority sources**. To protect `GET /api/orders/42`, you need authorization rules such as `hasAuthority("ORDER_READ")` or a manager checking resource ownership, not just creating a matcher.

### Matchers With HTTP Method vs. Without HTTP Method

~~~java
RequestMatcher anyMethod = paths.matcher("/api/orders/{id}");
RequestMatcher getOnly = paths.matcher(
        HttpMethod.GET, "/api/orders/{id}");
~~~

Different purposes:

- `anyMethod` only checks the path; if used with `permitAll()`, it can open POST/DELETE on the same path as well.
- `getOnly` matches only `GET` at that path; POST must match another rule or fallback.
- A **method-agnostic** matcher can be useful in **chain selection** if both GET and POST API calls belong in the same security chain.
- For **write-operation authorization**, use method-specific matchers so READ permissions never cover WRITE endpoints.

**Never embed the HTTP method in the path string** like `"GET /api/orders/**"`; that is not valid syntax for matching methods. Use the overload taking `HttpMethod`.

## 6. Context Path, Servlet Path, and basePath Differ

A Java Servlet request has multiple parts:

~~~text
URL from client:
https://service.example.test/shop/mvc/api/orders/42?view=full

Context path: /shop              (application is deployed under /shop)
Servlet path: /mvc               (DispatcherServlet has prefix /mvc)
Remaining path: /api/orders/42   (depends on servlet mapping)
Query: view=full
~~~

Rules to remember:

- `contextPath` is not embedded into internal path patterns for `PathPatternRequestMatcher`. Patterns are usually written **relative to context path**, e.g. `/api/orders/{id}` when there is no servlet prefix.
- When DispatcherServlet is mapped with a **servlet path prefix**, know which base path the matcher uses. The builder provides `basePath(...)` to construct matchers with an appropriate servlet-path prefix.
- `basePath("/mvc")` is a servlet/URL routing prefix, **not an invitation to add contextPath**.
- Never take `request.getRequestURI()` and call `startsWith(...)` against a pattern; that comparison easily confuses context path, servlet path, encoding, and query strings.

Illustrative example when a Servlet is mapped at `/mvc/*`:

~~~java
// Illustrative CONFIGURATION SNIPPET:
// basePath applies to matchers created from this builder.
var mvcPaths = PathPatternRequestMatcher.withDefaults()
        .basePath("/mvc");

RequestMatcher readOrder = mvcPaths.matcher(
        HttpMethod.GET, "/api/orders/{id}");
~~~

If the application does not configure a servlet prefix, use the default `withDefaults()` builder as in section 9. **Do not mechanically copy `basePath("/mvc")` into a root-mapped app.**

In practice, an app may run under different context paths in dev/staging/prod, or a reverse proxy may rewrite prefixes. Tests should include:

1. Requests at app root.
2. Requests with a non-root contextPath.
3. Requests with a Servlet path prefix if configured.
4. Requests via a reverse proxy with proper trusted forwarded headers.
5. Escaped/unicode/trailing-slash paths per business requirements.

In particular, context path and servlet path can make a matcher look right in simple `MockHttpServletRequest` tests while failing on a real container. Use MockMvc/integration tests with servlet mappings matching production as closely as possible.

## 7. Keeping PathPatternParser Aligned With Spring MVC

`PathPatternRequestMatcher` uses `PathPattern` parsing logic. If Spring MVC / Servlet routing is configured with a non-default `PathPatternParser` (for example, case sensitivity or other path-matching options), the security matcher and MVC handler mapping may **disagree** on which paths are valid.

This leads to two kinds of bugs:

- **False deny:** The controller could serve the URL, but the security matcher does not consider it valid, yielding 403/401.
- **False permit:** Security allows it due to broader/different matcher normalization, while MVC routes the request to a sensitive handler under its own rules. This case is more dangerous when rules open too broadly.

Implementation principles:

- If MVC uses the standard default parser, `withDefaults()` is a sensible starting point for supported Security versions.
- If MVC uses a custom parser, inspect your version's API to build matchers with that same `PathPatternParser` and ensure the configuration is shared **intentionally**.
- Never invent a factory method or `@Bean` that does not exist in your Security release; check Javadoc/source for the **exact version**.
- Write tests proving requests **permitted by security** hit the expected controller handler and requests **blocked by policy** never reach sensitive handlers.

A path matcher does not inspect query strings or request bodies. If those fields govern access, check them in separate service/application policies rather than trying to hack a path pattern to express every condition.

## 8. Combining With authorizeHttpRequests: Rule Order

Suppose we want:

- GET `/api/orders/{id}`: requires `ORDER_READ`.
- POST `/api/orders/{id}`: requires `ORDER_WRITE`.
- GET `/api/status`: public.
- Other `/api/**` requests: deny-all.

~~~java
// CONFIGURATION SNIPPET inside SecurityFilterChain:
var path = PathPatternRequestMatcher.withDefaults();

http.securityMatcher(path.matcher("/api/**"))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(path.matcher(
            HttpMethod.GET, "/api/status")).permitAll()
        .requestMatchers(path.matcher(
            HttpMethod.GET, "/api/orders/{id}"))
            .hasAuthority("ORDER_READ")
        .requestMatchers(path.matcher(
            HttpMethod.POST, "/api/orders/{id}"))
            .hasAuthority("ORDER_WRITE")
        .anyRequest().denyAll());
~~~

Reading each layer:

1. `securityMatcher("/api/**")` selects the chain for the API; it does not grant access to every request under the prefix.
2. Matchers inside `authorizeHttpRequests` also take the HTTP method.
3. `anyRequest().denyAll()` applies to requests that matched the chain without hitting any earlier authorization rule.
4. If a URL **does not match** this security chain, `anyRequest()` inside the chain **does not cover** that URL. Another chain or fallback policy is required.

### Security Chain Order

With multiple `SecurityFilterChain` beans using `@Order`, the first chain whose matcher matches is selected. An overly broad `/**` chain placed ahead of `/api/**` can force API requests through unwanted browser policies.

~~~text
Order(1): /api/** -> API matcher and ORDER_READ/WRITE policy
Order(2): remaining -> denyAll or web security policy
~~~

Do not write `/api/**` and assume it also matches `/internal/api/**` or a mis-injected proxy prefix. If two entry points are needed, declare both clearly in deployment policy and test each entry point.

### requestMatchers Order Inside a Chain

In a standard request registry, **the first rule matching the request** selects the authorization manager. Therefore:

~~~java
// COUNTER-EXAMPLE: overly broad, every GET /api/orders/... gets
// permitAll before the ORDER_READ rule is evaluated.
.requestMatchers(path.matcher(
    HttpMethod.GET, "/api/**")).permitAll()
.requestMatchers(path.matcher(
    HttpMethod.GET, "/api/orders/{id}"))
    .hasAuthority("ORDER_READ")
~~~

The right approach is specific rules first, general/fallback rules last. Never place `anyRequest().authenticated()` early expecting role-specific rules below it to still run.

## 9. Spring Boot 3 + Spring Security 6.5+ Project: Complete Example

The following example **requires a `spring-security-web` dependency supporting `PathPatternRequestMatcher`**, specifically Security **6.5+** or a corresponding newer release. If your Boot project still resolves Security 6.4 or earlier, **do not copy this code expecting it to build**. Upgrade dependencies using a tested BOM, or use the matcher solution available in that version.

### 9.1. Dependencies

Use Spring Initializr to generate a **Servlet web** project on JDK 17+. Required:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-test     (test scope)
spring-security-test        (test scope)
~~~

Depending on Boot minor version, pick a release bundling compatible Security 6.5+. Do not arbitrarily mix Spring Boot 3 libraries with Spring Security 7 artifacts just to get the class. The code here keeps CSRF enabled on the test API to show that **POST authorization** and **CSRF** are two distinct layers.

Place Java sources under `src/main/java/com/example/pathmatcher/` and tests under `src/test/java/com/example/pathmatcher/`.

### 9.2. SecurityConfig.java

~~~java
package com.example.pathmatcher;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-demo-only"))
                .authorities("ORDER_READ")
                .build();

        UserDetails writer = User.withUsername("writer")
                .password(encoder.encode("writer-demo-only"))
                .authorities("ORDER_WRITE")
                .build();

        return new InMemoryUserDetailsManager(reader, writer);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        PathPatternRequestMatcher.Builder paths =
                PathPatternRequestMatcher.withDefaults();

        http
            // Select API chain first; this matcher does not grant permissions.
            .securityMatcher(paths.matcher("/api/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(paths.matcher(
                    HttpMethod.GET, "/api/status")).permitAll()

                .requestMatchers(paths.matcher(
                    HttpMethod.GET, "/api/orders/{id}"))
                    .hasAuthority("ORDER_READ")

                .requestMatchers(paths.matcher(
                    HttpMethod.POST, "/api/orders/{id}"))
                    .hasAuthority("ORDER_WRITE")

                // Deny API requests without an explicit rule.
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Do not disable CSRF in this example: POST requires a token.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Key takeaways:

- `@Order(1)` and `@Order(2)` order **the SecurityFilterChain beans**, not the rules inside `authorizeHttpRequests`.
- Builder `withDefaults()` creates explicit PathPattern matchers without relying on Spring MVC's `HandlerMappingIntrospector`.
- Method-specific matchers clarify read/write permissions, while the chain matcher accepts `/api/**` so all API requests share the same filter set.
- `.anyRequest().denyAll()` is a safe policy for unapproved URLs/methods.
- The fallback bean includes no authentication mechanism, so requests outside `/api/**` are rejected; if the app needs a web UI, design a second chain with its own login/session/CSRF and authorization rules.
- `httpBasic(...)` serves demo and simple testing purposes. Production may use OAuth2 resource server / JWT, provided token signature, issuer, audience, and scopes are verified properly.
- `reader` only has `ORDER_READ`, and `writer` only has `ORDER_WRITE`; a general permission does not implicitly include another permission.
- Use demo passwords only on localhost/tests; never commit real credentials in source code.

### 9.3. OrderController.java

~~~java
package com.example.pathmatcher;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/status")
    public String status() {
        return "ready";
    }

    @GetMapping("/api/orders/{id}")
    public String readOrder(@PathVariable String id) {
        return "read:" + id;
    }

    @PostMapping("/api/orders/{id}")
    public String updateOrder(@PathVariable String id) {
        // Demo: does not actually modify DB.
        return "write:" + id;
    }
}
~~~

**Note on resource-level authorization:** the matcher only knows the path matches `/api/orders/{id}`; it does not prove the reader is authorized to view **this specific order id**. In production, the service must verify owner/tenant/permissions before reading or writing the record. Never treat a client-supplied ID as "trusted" just because it matches a regex or path pattern.

### 9.4. PathMatcherApplication.java

~~~java
package com.example.pathmatcher;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathMatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathMatcherApplication.class, args);
    }
}
~~~

Place all classes in the same package or within `@SpringBootApplication` component-scan scope. Do not declare another default chain with a broader matcher and higher `@Order` priority than this API chain.

### 9.5. Running the Demo

With a Maven Wrapper project resolving Security 6.5+ and Java 17+:

~~~bash
./mvnw spring-boot:run
~~~

Public request:

~~~bash
curl -i http://localhost:8080/api/status
~~~

Read-permission request (localhost demo credentials only):

~~~bash
curl -i -u reader:reader-demo-only \
  http://localhost:8080/api/orders/42
~~~

Expected logical result when running the server: `GET /api/status` returns `200` with body `ready`; `GET /api/orders/42` with reader returns `200`, body `read:42`. Writer **does not automatically have ORDER_READ**, so calling the read endpoint as writer lacks permission and normally returns `403`.

No fixed HTTP headers stdout is shown because headers depend on server, entry point, and container. Command-line `curl -u` can expose passwords in process lists/history; use fake credentials only on localhost. Use proper secret handling in production.

Do not hastily run `curl -X POST` and conclude the Security rule is wrong upon seeing 403: POST still has to pass **CsrfFilter** in this example. The MockMvc suite in the next section separates the two conditions.

## 10. MockMvc: Testing PathPattern, HTTP Method, and Real Authorization

Create `src/test/java/com/example/pathmatcher/PathPatternAuthorizationTest.java`:

~~~java
package com.example.pathmatcher;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PathPatternAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void statusIsPublicInsideApiChain() throws Exception {
        mvc.perform(get("/api/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void readerMayReadSingleSegmentOrderId() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("read:42"));
    }

    @Test
    void writerPermissionDoesNotImplyRead() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postUsesSeparateWritePermission() throws Exception {
        mvc.perform(post("/api/orders/42")
                .with(csrf())
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("write:42"));

        mvc.perform(post("/api/orders/42")
                .with(csrf())
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postStillNeedsCsrf() throws Exception {
        mvc.perform(post("/api/orders/42")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void extraPathSegmentCannotMatchSingleIdPattern()
            throws Exception {
        mvc.perform(get("/api/orders/42/extra")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void queryStringIsNotAnotherPathSegment() throws Exception {
        mvc.perform(get("/api/orders/42")
                .queryParam("view", "history")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("read:42"));
    }

    @Test
    void methodsOutsideDeclaredPolicyAreDenied() throws Exception {
        mvc.perform(delete("/api/orders/42")
                .with(csrf())
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCannotReadPrivateOrder() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Test explanation:**

1. `statusIsPublic...` verifies a matcher inside the API chain still allows a public route.
2. `readerMayRead...` checks a path with a single `id` segment and `ORDER_READ` authority.
3. `writerPermissionDoesNotImplyRead` proves `ORDER_WRITE` does not grant `ORDER_READ`.
4. `postUsesSeparateWritePermission` verifies the **POST matcher differs from the GET matcher**, using `.with(csrf())` to ensure 200/403 comes from authorization.
5. `postStillNeedsCsrf` shows matching HTTP method/path/permission is not enough when CSRF is active.
6. `extraPathSegment...` ensures `/api/orders/{id}` does not accidentally match an extra `/extra` segment; the `denyAll` fallback blocks it before MVC.
7. `queryStringIsNotAnotherPathSegment` shows query parameters are not part of the path pattern, though the controller must still validate query semantics if they affect business logic.
8. `methodsOutsideDeclaredPolicy...` proves WRITE permission for POST does not grant DELETE.
9. `anonymousCannotRead...` verifies the Basic authentication entry point; in a form-login app, the unauthenticated response may be a redirect rather than 401.

**Do not treat a 403 status as sufficient proof:** if a POST test lacks CSRF, `CsrfFilter` can reject it before `AuthorizationFilter`. When testing security matchers, include CSRF so requests reach the authorization layer when asserting role/authority rules.

When upgrading Spring Security or changing MVC path matching mode, run all of these tests alongside encoded, trailing-slash, servlet-prefix, and forwarded-header tests. Tests in a simulated MockMvc environment **do not prove every proxy/container canonicalizes URLs identically**; end-to-end requests remain valuable.

Run:

~~~bash
./mvnw test
~~~

Do not fabricate Maven stdout and do not claim tests actually ran just because the code looks valid. This lesson provides the test code and expectations; actual execution results depend on resolved dependencies and proper app configuration.

## 11. Migrating From AntPathRequestMatcher and MvcRequestMatcher

### 11.1. Step 1 — Inventory All Actual Matchers

Search configuration code for:

~~~text
AntPathRequestMatcher
MvcRequestMatcher
requestMatchers("...")
securityMatcher("...")
logoutRequestMatcher(...)
csrf().ignoringRequestMatchers(...)
FilterChainProxy / SecurityFilterChain
PathPatternRequestMatcher
~~~

Do not replace only rules inside `authorizeHttpRequests` while overlooking `securityMatcher`, logout, CSRF exemptions, request cache, web ignoring, custom filters, and forwarding logic. Those places may use different matcher implementations, leading to inconsistent URL handling.

### 11.2. Step 2 — Check Versions First

If using Spring Security 6.3/6.4, do **not** change imports to `PathPatternRequestMatcher` expecting the IDE to add the dependency automatically. Inspect the BOM, versions, and compatibility, and decide:

- Keep the supported matcher configuration and write regression tests.
- Or upgrade Spring Boot / Spring Security on a tested path, then migrate matchers to the new API.

Never upgrade a single Security artifact in isolation just to silence an import error.

### 11.3. Step 3 — Translate Semantics, Not Just Class Names

Example Ant-style rule:

~~~text
/reports/**/download
~~~

You cannot assume this pattern moves straight to PathPattern and is accepted by the parser, because mid-pattern `**` is restricted. Redesign the route to place wildcards at the end or use clearer individual patterns. Then list allowed/disallowed URLs per business rules and test them.

**Do not** replace it with `/reports/**` and `permitAll` just to "avoid parser errors" — that widens access scope and can introduce a vulnerability.

### 11.4. Step 4 — Reconcile Servlet Mappings With MVC

Legacy `MvcRequestMatcher` leveraged Spring MVC handler-matching info via `HandlerMappingIntrospector`. When moving to explicit `PathPatternRequestMatcher`, you must ensure `basePath` and parser alignment with MVC yourself. If the app has multiple servlets, `/mvc`, `/api`, or custom servlets, test every mapping rather than assuming one builder covers every servlet.

### 11.5. Step 5 — Enforce Per-Method Permissions

Convert:

~~~java
// Old config overly broad on HTTP method:
.requestMatchers("/orders/**").hasAuthority("ORDER_READ")
~~~

into separate rules:

~~~java
// Conceptual example when builder paths is available:
.requestMatchers(paths.matcher(
    HttpMethod.GET, "/orders/{id}")).hasAuthority("ORDER_READ")
.requestMatchers(paths.matcher(
    HttpMethod.POST, "/orders/{id}")).hasAuthority("ORDER_WRITE")
.requestMatchers(paths.matcher("/orders/**")).denyAll()
~~~

**This is a snippet inside authorizeHttpRequests**, not a standalone Java class. If the API supports PATCH/DELETE, define dedicated permissions. Account for CSRF and object-ID authorization as well.

### 11.6. Step 6 — Regression Tests Before and After

To evaluate migration, prepare a **truth table** for matchers:

| Request | Rule | Expected |
| --- | --- | --- |
| GET `/api/orders/42` | `GET /api/orders/{id}` | Match |
| POST `/api/orders/42` | `GET /api/orders/{id}` | No match |
| GET `/api/orders/42/extra` | `GET /api/orders/{id}` | No match |
| GET `/api/orders/42?tab=1` | `GET /api/orders/{id}` | Matches path |
| GET `/api/status` | `GET /api/status` | Match |
| DELETE `/api/orders/42` | `POST /api/orders/{id}` | No match |
| GET `/api/orders/42/` | `GET /api/orders/{id}` | Depends on trailing-separator policy/parser; test in practice |
| GET `/api/orders/%2F` | `GET /api/orders/{id}` | Depends on container/firewall/parser; never guess from raw URL |

**Distinguish test levels:**

- **Matcher test:** matcher returns true/false on properly constructed requests.
- **Security chain test:** which chain the request enters and which authorization rule is chosen.
- **Controller test:** which handler the request actually routes to.
- **Deployment test:** whether proxy, context path, servlet path, forwarded headers, and URL encoding align with intent.

A "successful migration" where the build is green yet rules permit wrong URLs/methods is still a security failure.

## 12. Common Pitfalls: Regex, Trailing Slashes, Fallbacks, and Path Variables

### 12.1. PathPattern Is Not a Raw Java String Regex

The pattern `/orders/{id}` is not directly equivalent to regex `/orders/(.*)`, because regex `.*` can consume slashes. Segment-based syntax is the purpose of `PathPattern`. If a variable genuinely needs regex, use `{id:...}` **according to supported parser syntax** and test with real inputs.

When the parser encounters an invalid pattern, let the application **fail fast** at matcher construction rather than catching the exception and falling back to a broader pattern "just to make it run".

### 12.2. Trailing Slashes Are Not Optional by Default

Do not expect `/api/orders/42` and `/api/orders/42/` to always behave the same. Spring Framework configuration, versions, and parsers can change this behavior, especially when migrating from older matchers. For clear UX, pick canonical routes and redirect/canonicalize under control, avoiding widening policies with broad wildcards.

### 12.3. Matching a Path Does Not Mean Permission to View the Object

`GET /api/orders/{id}` can match with `id=42`. Yet:

- May a user who only has `ORDER_READ` view **order 42**?
- Which tenant does the order belong to?
- Is the user in the right organization/owner?
- Is the resource still in a readable state?

These questions belong to **service/resource-level authorization**, which a path matcher alone cannot solve. For example, the service loads the `Order` and verified principal, checking owner/tenant before returning or modifying data.

### 12.4. Do Not Derive Authorities From Path Variables

An attacker can request `/api/orders/ROLE_ADMIN`. Path variable `id` is URL input, **not** a `GrantedAuthority`. Never read `id` to construct principals or roles. Authentication must come from trusted sources; authority checks must run against verified permissions.

### 12.5. Do Not Use Path Matchers in Place of a CSRF Firewall

A matching `POST /api/orders/{id}` from a user with `ORDER_WRITE` can still be rejected by CSRF. In browser-session apps, that is proper when POST lacks a token; never disable CSRF to "fix" a 403. Conversely, a valid CSRF token does not mean the user has WRITE permission.

### 12.6. Multiple Filters and Request Dispatches

A request may go through forward/error/async dispatches where URLs are represented differently depending on the servlet container. With custom filters and multiple dispatcher types, verify matchers handle dispatch types properly and ensure internal routes do not skip authorization when forwarded to another handler. Never fix a 403 by placing a broad `permitAll("/**")`.

## 13. Standalone Java 17: Simulating Path and Method Boundaries

The following `PathPolicyDemo.java` **does not implement PathPatternParser**, is not a real `RequestMatcher`, does not decode URLs, and does not claim to support all Spring syntax details. It merely clarifies "GET requires READ, POST requires WRITE, the path has only one id segment, and query is not path".

~~~java
public final class PathPolicyDemo {

    static String choose(String method, String path) {
        if ("GET".equals(method) && "/api/status".equals(path)) {
            return "PUBLIC";
        }

        String[] segments = path.split("/", -1);

        // "/api/orders/42" -> ["", "api", "orders", "42"].
        boolean oneId = segments.length == 4
                && segments[0].isEmpty()
                && "api".equals(segments[1])
                && "orders".equals(segments[2])
                && !segments[3].isEmpty();

        if (oneId && "GET".equals(method)) {
            return "ORDER_READ";
        }
        if (oneId && "POST".equals(method)) {
            return "ORDER_WRITE";
        }
        return "NO_MATCH";
    }

    static void inspect(String method, String path) {
        System.out.println(method + " " + path
                + " -> " + choose(method, path));
    }

    public static void main(String[] args) {
        inspect("GET", "/api/status");
        inspect("GET", "/api/orders/42");
        inspect("POST", "/api/orders/42");
        inspect("DELETE", "/api/orders/42");
        inspect("GET", "/api/orders/42/extra");
        inspect("GET", "/api/orders/");
    }
}
~~~

Run on JDK 17+:

~~~bash
javac PathPolicyDemo.java
java PathPolicyDemo
~~~

**Exact** stdout:

~~~text
GET /api/status -> PUBLIC
GET /api/orders/42 -> ORDER_READ
POST /api/orders/42 -> ORDER_WRITE
DELETE /api/orders/42 -> NO_MATCH
GET /api/orders/42/extra -> NO_MATCH
GET /api/orders/ -> NO_MATCH
~~~

Exercise: change `inspect("POST", "/api/orders/42")` to `inspect("PUT", "/api/orders/42")`. The result becomes `NO_MATCH` because the policy has no PUT rule. This is a **request classification** example; it does not verify credentials, check authorities, or run the Spring HTTP pipeline. The `ORDER_READ`/`ORDER_WRITE` strings in this program are **rule labels**, not claims that a user holds those permissions.

## 14. Knowledge Check Questions

**Q1. Is PathPatternRequestMatcher available in every Spring Security 6.0–6.4 release?** No. This API belongs to newer releases starting from 6.5; verify your actual `spring-security-web` dependency.

**Q2. Can you immediately import PathPatternRequestMatcher when using Spring Boot 3.x?** You cannot infer it from the Boot major version alone. Check which Spring Security version your Boot minor manages or what explicit dependency management resolves.

**Q3. Do `securityMatcher` and `requestMatchers` serve the same function?** No. One selects the security chain, while the other selects the authorization rule inside the chain.

**Q4. Does `PathPattern` allow `/files/**/download` like an Ant pattern?** Do not assume so. In PathPattern, `**` is only valid at the end of a pattern; redesign and test.

**Q5. Does `PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.GET, "/orders/{id}")` match POST?** No. It constrains GET; POST needs a separate matcher if required by business rules.

**Q6. Does `/orders/{id}` automatically check whether the user owns that order id?** No. It only identifies the path/variable; resource-based permissions belong in deeper service/authorization logic.

**Q7. When an app is deployed at context path `/shop`, should you prepend `/shop` to every pattern?** Do not do so mechanically. Matchers usually evaluate paths relative to the context path; distinguish servlet prefixes and use `basePath` when appropriate.

**Q8. Why is a green build after migration not enough?** Path patterns may match differently, security chains may change order, CSRF exemptions may widen, or authorization rules may match wrongly. You need a truth table and integration tests.

**Q9. In `GET /api/orders/42?view=full`, is the query part of `PathPattern`?** The query string is not part of the path matcher in normal usage; add business-layer checks if query values affect permissions.

**Q10. If POST returns 403, can you conclude `PathPatternRequestMatcher` did not match?** No. The CSRF filter may block first, or the matcher matched while `hasAuthority` denied it. Test with valid CSRF, the right principal, and the matched chain.

**Q11. When URLs contain `%2F` or semicolons, can you determine from raw URLs whether the parser allows them?** No. Containers, firewalls, proxies, decoders, and parsers all interact; end-to-end tests are required.

**Q12. Why are explicit matchers helpful during version upgrades?** They make the intended implementation and path grammar clear, reducing reliance on DSL auto-inference; you still need tests and proper dependency management.

## 15. Pre-Release Checklist

- [ ] Identified actual `spring-security-web`, `spring-security-config`, Spring Framework, and Boot versions; never guessed from project name.
- [ ] If `PathPatternRequestMatcher` is needed, confirmed the active Security release supports it (6.5+ or equivalent).
- [ ] Distinguished Servlet security from WebFlux.
- [ ] Every `securityMatcher` accurately matches the chain to protect, with a fallback policy for requests outside the API chain.
- [ ] `authorizeHttpRequests` matchers separate GET/POST/PUT/PATCH/DELETE where impact differs.
- [ ] Specific rules precede broad wildcards; `anyRequest().denyAll()` guards unapproved methods/URLs when architecturally appropriate.
- [ ] Patterns verified against `PathPattern` syntax; no mid-pattern `**` copied verbatim from Ant.
- [ ] `contextPath`, `servletPath`, and `basePath` are properly understood and tested under prefix deployments.
- [ ] If MVC uses a custom parser, security matchers and handler mappings share aligned semantics or consistent testing.
- [ ] Tests cover path variables, extra segments, query strings, trailing slashes, and unusual URLs per the threat model.
- [ ] CSRF is tested independently for browser cookie sessions; never disabled to work around failing POST tests.
- [ ] Users/authorities are verified server-side; path matchers are never used to grant roles or skip resource ownership.
- [ ] Positive/negative HTTP tests exist via MockMvc, plus deployment tests when proxies/encoding apply.
- [ ] Never look only at 403/404 status without identifying the cause: CSRF, authentication entry point, matcher, rule, or controller mapping.
- [ ] Never use overly broad URL wildcards/`permitAll` to mask parser errors or version mismatches.
- [ ] When upgrading Spring Security major versions, reviewed the corresponding migration guide and ran security regression tests.

**Conclusion:** `PathPatternRequestMatcher` is the **PathPattern**-based HTTP request matching mechanism in **Spring Security Servlet** for versions supporting this API. Its main value is expressing **path + method** accurately and aligning path logic, yet it **does not replace authorization**. Before using it, check **version compatibility**, **PathPattern syntax**, **contextPath/servletPath**, **security chain ordering**, **CSRF**, and real tests. Never migrate Ant/MVC matchers to PathPattern by simply renaming classes.
