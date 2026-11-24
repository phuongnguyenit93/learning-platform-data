# Exact Match, Wildcards, and Path Variables

> **Scope:** Spring Security 6.x on the **Servlet stack**, Spring Boot 3.x, and Java 17+. This lesson explains how an HTTP request is matched against security rules using **exact paths**, **wildcards** (`*`, `**`), and **path variables** (`{id}`, `{id:regex}`). It distinguishes `securityMatcher` (selecting a `SecurityFilterChain`) from `requestMatchers` (selecting an authorization rule inside the chain), and highlights differences among `MvcRequestMatcher`, `AntPathRequestMatcher`, and `PathPatternRequestMatcher`. Includes a complete Spring Boot project with MockMvc tests, comparison tables, and a common-pitfalls checklist.

## 1. Matching Is the First Step of Authorization

An application may have routes such as:

```text
GET  /api/ping
GET  /api/books
GET  /api/books/42
GET  /api/books/42/chapters
POST /api/books
GET  /api/files/guide.json
GET  /api/admin/audit
GET  /external
```

Each route needs a clear policy: public route, login-required route, admin-only route, or denied route. Matching means **deciding which URL/method set the current HTTP request belongs to**. Authorization uses that result to apply permission requirements.

A small mistake in a pattern can become a vulnerability: if `/api/**` already has `permitAll()` while `/api/admin/**` is protected below it, the broad rule can prevent the admin rule from ever applying. Conversely, an overly narrow matcher causes the application to return 401/403 even though the controller defines the route.

### Questions to Answer Before Writing a Rule

1. What are the **path** and **HTTP method** of the actual request URL?
2. Is the pattern a literal, wildcard, variable, or regex-constrained variable?
3. Does the matcher use the **Spring MVC/PathPattern** engine or **Ant-style**?
4. Does the matcher select an **entire filter chain** or just an **authorization rule**?
5. Do two rules overlap, and which rule appears first?
6. If no rule matches, does the system deny by default?

## 2. Two Layers of Request Matching in Spring Security Servlet

Spring Security plugs into Servlet via `DelegatingFilterProxy`, typically delegating to `FilterChainProxy`. It can manage multiple `SecurityFilterChain` beans; each chain has its own filters and authorization rules.

```text
HTTP request
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    +--> SecurityFilterChain @Order(1)
    |       securityMatcher("/api/**")?
    |             |
    |             +--> match: select this chain
    |                       |
    |                       +--> Security filters
    |                       +--> AuthorizationFilter
    |                                |
    |                                +--> requestMatchers(...) in order
    |
    +--> SecurityFilterChain @Order(2)
            match-all fallback -> denyAll()
```

**Layer 1: `securityMatcher(...)`** decides **whether the request enters this SecurityFilterChain**. When multiple chains exist, Spring Security selects the first matching chain by priority order; it does not merge all matching chains.

**Layer 2: `authorizeHttpRequests(...requestMatchers(...))`** decides **which authorization rule applies after the chain is selected**. With request matcher delegation, **the first matching rule normally wins**; do not expect a more specific rule to override an earlier broad rule.

Example `GET /api/books/42`:

```text
securityMatcher("/api/**")             -> true
requestMatchers(GET, "/api/ping")       -> false
requestMatchers(GET, "/api/books")      -> false
requestMatchers(GET, "/api/books/{id}") -> true
                                         |
                                         v
                                    authenticated()
```

If a chain has `securityMatcher("/api/**")`, a `requestMatchers("/admin/**")` rule inside it **cannot protect `/admin/**`**, because that request never enters the API chain. You need another chain or an adjusted chain matcher.

## 3. Exact Match: Path Literals

An exact match uses a path without wildcards or variables. Example in configuration:

```java
// Fragment inside authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
```

This snippet binds the `/api/ping` path and HTTP method GET.

| Request | Matches GET `/api/ping` rule? |
| --- | --- |
| `GET /api/ping` | Yes |
| `GET /api/ping?debug=true` | Yes; query is not path |
| `GET /api/ping/extra` | No |
| `GET /api/pings` | No |
| `POST /api/ping` | No, due to method |
| `GET /API/ping` | Usually no, because default config is case-sensitive |

### Exact Does Not Mean Prefix

`/api/ping` does not match `/api/ping/extra`. Similarly, `/api/user` does not automatically match `/api/users`. If you only want one public endpoint, **use a literal** instead of opening `/api/**`.

### Path vs. Full URL

This is **not** the right way to write a path matcher:

```java
// Anti-pattern: Spring Security path matchers do not compare full URLs automatically.
.requestMatchers("https://example.com/api/ping").permitAll()
```

Configuration typically compares the request path in the Servlet/MVC context; it does not check host/port/scheme merely because that string appears in the matcher. If policy depends on host or tenant, design a dedicated `RequestMatcher` with proper trust boundaries for proxy/forwarded headers.

### Query Does Not Change the Path

`GET /api/books/42?lang=vi` and `GET /api/books/42?lang=en` share the same path. If permissions depend on a query parameter, separate logic is needed and you must verify that the parameter cannot be arbitrarily spoofed by the client to escalate privileges.

### Trailing Slash

`/api/ping` and `/api/ping/` **are not always equivalent**. With Spring MVC 6 / PathPatternParser, optional trailing-slash matching is no longer enabled by default as in some older setups. Always test against reality, especially when upgrading Spring Boot or when a reverse proxy rewrites paths.

## 4. Wildcards: `*`, `**`, `?`, and File Suffixes

Common syntax in Spring MVC PathPattern:

- `*`: matches **characters within a single path segment**; does not cross `/` into the next segment.
- `?`: wildcard symbol for **a single character within a segment** where supported by the engine; do not confuse it with the `?` separating a URL query string.
- `**`: matches **zero or more segments** at the **end of a pattern** according to `PathPatternParser`.
- `*.json`: matches a file name ending in `.json` within **a single segment**.
- `{*rest}`: captures multiple remaining segments at the end in PathPatternParser.

### 4.1. Path Matching Table

Assuming `PathPatternParser` with default configuration unchanged:

| Pattern | `/api/books` | `/api/books/42` | `/api/books/42/chapters` |
| --- | :---: | :---: | :---: |
| `/api/books` | Yes | No | No |
| `/api/books/*` | No | Yes | No |
| `/api/books/**` | Yes | Yes | Yes |
| `/api/books/{id}` | No | Yes | No |
| `/api/books/{id:[0-9]+}` | No | Yes | No |
| `/api/books/*/chapters` | No | No | Yes |

**Understand the exact scope:** `/api/books/**` also covers `/api/books/42/chapters/1` or `/api/books/private/reports`. If you only want a single book by id, `/api/books/{id}` is narrower and carries less risk of accidentally exposing subresources.

### 4.2. `*` Matches Only One Segment

```text
Pattern: /api/books/*

/api/books/42            -> match
/api/books/abc           -> match
/api/books/42/chapters   -> no match
/api/books               -> no match
```

`*` does not verify that `id` is numeric, does not infer user permissions, and does not match across slashes. If the system expects an integer, use a regex-constrained variable or validate input at the business layer.

### 4.3. `**` Can Match Multiple Segments

```text
Pattern: /api/books/**

/api/books                 -> match per PathPattern
/api/books/42              -> match
/api/books/42/chapters     -> match
/api/books/42/chapters/1   -> match
```

With `PathPatternParser`, `**` is only supported at the **end of a pattern** (similar to `{*path}`). Some historical Ant matchers supported `/**/` in the middle; **never copy that pattern verbatim to MVC/PathPattern** and assume it behaves identically.

### 4.4. `*.json` Does Not Open All .json Files at Every Level

`/api/files/*.json` can match `/api/files/guide.json`, but it does not match `/api/files/reports/guide.json` and does not match `/api/files/guide.txt`.

Even when a public route only allows `.json`, the file-reading layer still needs path-traversal protection, real file constraints, and object-level permission checks: a Security matcher only selects the URL, it does not perform filesystem authorization.

### 4.5. Wildcard `?` Differs From Query Separator `?`

In a path pattern, `?` represents one character per supported matcher syntax; in an HTTP URL, `?` separates the query string. For example, `/api/v1?debug=true` has path `/api/v1` and query `debug=true`. Never put a question mark in a path pattern expecting it to handle query conditions.

## 5. Path Variables `{id}` and Regex `{id:regex}`

Spring MVC controller route:

```java
@GetMapping("/api/books/{id}")
public String book(@PathVariable String id) {
    return "book-" + id;
}
```

In URL `/api/books/42`, the variable `id` is `42`. Security can use a matching pattern:

```java
// Fragment when MvcRequestMatcher.Builder mvc is available:
.requestMatchers(mvc.pattern(
        HttpMethod.GET, "/api/books/{id}"))
.authenticated()
```

`{id}` only describes **one path segment**; it does not check data types, does not query the database, and **does not check whether the user owns the record**.

### 5.1. Regex-Constrained Variable

`/api/books/{id:[0-9]+}` requires the `id` segment to consist of one or more digits:

```text
/api/books/42       -> match
/api/books/007      -> match
/api/books/abc      -> no match
/api/books/42/abc   -> no match
```

This syntax is compatible with `PathPatternParser` in Spring MVC. Regex only helps classify requests; it does not prove the id exists or that the user may access it. For numeric ids with leading zeros or length limits, the application still needs dedicated validation/service policies.

### 5.2. Controller Variables and Security Variables Can Differ

A controller might define `@GetMapping("/api/books/{id}")` while security only permits numeric `{id:[0-9]+}`. Then `GET /api/books/abc` has an **MVC handler if it reaches the controller**, yet Security can block the request **before the controller runs** because it does not match the permitted rule.

This is an intentional choice when it fits business rules. Conversely, a security pattern broader than the controller can expose new endpoints accidentally placed under the same prefix.

### 5.3. Request Path Variables in Custom Authorization

When `MvcRequestMatcher` extracts variables, `RequestAuthorizationContext.getVariables()` can supply that map to `AuthorizationManager`. This helps check resources by id/tenant or principal name.

Pseudocode illustrating the contract, **not** production security logic:

```java
// requestMatchers(mvc.pattern(GET, "/api/users/{username}/profile"))
// .access((authenticationSupplier, context) -> {
//     String usernameFromUrl = context.getVariables().get("username");
//     Authentication current = authenticationSupplier.get();
//
//     // Must check authenticated and non-anonymous, then verify
//     // username/tenant/ownership against server-side policy before granting.
//     return new AuthorizationDecision(/* allowed after validation */);
// });
```

Never check a client-sent `userId` merely by comparing it against another client-supplied header. With multi-tenancy and delegated access, permissions must rely on the verified principal and server-side data. This is essential for preventing **IDOR/BOLA**.

## 6. Matcher Type Determines Semantics: MVC, Ant, or PathPattern

Important APIs:

| API/class | Common Use | Notes |
| --- | --- | --- |
| `MvcRequestMatcher` | When matching should align with Spring MVC | Uses `HandlerMappingIntrospector`; understands context path and servlet path |
| `AntPathRequestMatcher` | Legacy systems using Ant patterns | Syntax/normalization can differ from MVC, especially `**` |
| `PathPatternRequestMatcher` | Spring Security versions supporting direct PathPattern matching | Parser must stay consistent with app; `**` only at the end |
| Custom `RequestMatcher` | Host, tenant, header, query, or other conditions | Must review trust boundaries, encoding, and routing |

In the Boot 3.3.5 example below, we **explicitly** instantiate `MvcRequestMatcher.Builder` with `HandlerMappingIntrospector`. This avoids guessing which engine the `requestMatchers(String...)` overload selects based on classpath/version.

### 6.1. String Overloads Can Depend on the Environment

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

Spring Security can select a matcher suited to Spring MVC when MVC is on the classpath, but with multiple Servlet registrations or custom MVC configs, use explicit matchers to clarify intent and reduce confusion. Do not assume one version's default behavior applies to every project.

### 6.2. Avoid Mixing URL Matching With Inconsistent MVC Routing

If MVC parses a path using `PathPatternParser` while Security manually uses `AntPathRequestMatcher` with different rules, the following can happen:

- MVC routes the request to an admin endpoint while Security matches a different public rule;
- A trailing slash is accepted by MVC but not by Security;
- Encoded or semicolon paths are handled differently by one layer than the other;
- A pattern like `/**/admin` is valid in one engine but invalid in the other;
- The servlet path is counted twice or skipped.

**Goal:** protected paths must be interpreted consistently across every layer involved in identity and authorization decisions. Test boundary requests and keep firewall policies tight.

### 6.3. Servlet Path and Context Path

Context path is the prefix when an app is deployed under a context, e.g. the browser calls `/shop/api/books/42` while the application has route `/api/books/42`. Servlet matchers usually do not need `/shop` added manually because the container separates the context path.

If `DispatcherServlet` is mounted at servlet path `/app`, you may need:

```java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector)
                .servletPath("/app");

RequestMatcher matcher =
        mvc.pattern("/api/books/{id}");
```

This is a fragment; imports for `MvcRequestMatcher`, `HandlerMappingIntrospector`, and `RequestMatcher` are required. Interpret patterns as relative to the builder's servlet path. Do not confuse `server.servlet.context-path` with `spring.mvc.servlet.path`.

## 7. Constraining HTTP Methods

These two policies are **not equivalent**:

```java
.requestMatchers("/api/books").permitAll()
```

```java
.requestMatchers(HttpMethod.GET, "/api/books").permitAll()
```

The first form can match multiple methods on that path; the second matches only GET. If `POST /api/books` creates data, a path-only `permitAll` rule can unintentionally open access if other protective layers change.

Example:

```java
.requestMatchers(mvc.pattern(HttpMethod.GET, "/api/books"))
.permitAll()

.requestMatchers(mvc.pattern(HttpMethod.POST, "/api/books"))
.hasRole("EDITOR")
```

**HEAD and OPTIONS:** Spring MVC can support HEAD via a GET mapping, but an `HttpMethod.GET` matcher does not automatically match HEAD. CORS preflight is usually OPTIONS; configure `http.cors(...)`/MVC CORS properly rather than using a broad `permitAll OPTIONS /**` without understanding request origins.

**CSRF:** if an API relies on session cookies or browser-sent credentials, state-changing requests may require a CSRF token. A CSRF 403 is independent of `hasRole`. When testing an allowed `POST`, add `with(csrf())` to verify the role rule instead of accidentally proving only that CSRF is blocking it.

## 8. Rule Ordering: First Match Wins

Anti-pattern:

```java
// WRONG: broad rule renders the admin rule below ineffective.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
```

For `GET /api/admin/audit`, the `/api/**` rule already matches first and can allow **any authenticated user** in. There is no automatic selection of the most specific matcher overriding configuration order.

Better ordering:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
```

### Literal vs. Variable Overlap

`/api/users/me` can also match `/api/users/{id}` with `id="me"`. If the literal `/me` has a different policy from the variable route `/{id}`, place the literal first or use regex and an appropriate authorization manager.

### Fallback Deny and Chain Coverage

`anyRequest().denyAll()` only protects **within the selected chain**. If you only define a chain with `securityMatcher("/api/**")` without a chain covering all remaining requests, routes outside the API may **not be protected by Spring Security**.

That is why the complete example includes a priority chain for `/api/**` and a match-all fallback chain for deny-by-default. `@Order` on beans orders the chains, **not** the authorization rules inside them.

## 9. Spring Boot Project: Exact, Wildcard, Variable, and Method

Uses **Java 17+**, Spring Boot **3.3.5** (Spring Security 6.x), Gradle **8.5**. The demo has two local users:

- `reader / readerPass!` with `ROLE_READER`.
- `editor / editorPass!` with `ROLE_EDITOR`.

These accounts and passwords are **for this lesson only**, not production secrets. Passwords are hashed with BCrypt.

URL Policy:

| Request | Permission |
| --- | --- |
| `GET /api/ping` | Public, literal exact |
| `GET /api/books` | Public, literal exact |
| `GET /api/files/*.json` | Public, filename wildcard |
| `GET /api/books/{id:[0-9]+}` | Authenticated, single numeric segment id |
| `GET /api/books/*/chapters` | `ROLE_EDITOR`, one segment |
| `GET /api/admin/**` | `ROLE_EDITOR`, all sub-levels |
| `POST /api/books` | `ROLE_EDITOR` + CSRF |
| All remaining requests | Deny |

### 9.1. File Tree and Gradle

```text
request-matcher-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    ApiController.java
  src/test/java/demo/
    RequestMatcherTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'request-matcher-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 9.2. DemoApplication

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 9.3. SecurityConfig

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

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
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("readerPass!"))
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("editorPass!"))
                .roles("EDITOR")
                .build();

        return new InMemoryUserDetailsManager(reader, editor);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector);

        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/ping")).permitAll()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/books")).permitAll()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/files/*.json")).permitAll()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/books/{id:[0-9]+}"))
                        .authenticated()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/books/*/chapters"))
                        .hasRole("EDITOR")
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/admin/**"))
                        .hasRole("EDITOR")
                .requestMatchers(mvc.pattern(
                        HttpMethod.POST, "/api/books"))
                        .hasRole("EDITOR")
                .anyRequest().denyAll());

        http.httpBasic(Customizer.withDefaults());

        // Keep CSRF enabled; POST requires a valid CSRF token.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Explanation:**

1. `@Order(1)` applies only to `/api/**`. `@Order(2)` is a catch-all fallback permitting no non-API requests unless a dedicated policy is designed.
2. `MvcRequestMatcher.Builder` uses `HandlerMappingIntrospector`, so authorization matching aligns with Spring MVC semantics in the project. This avoids relying on the dynamic selection of String overloads.
3. `HttpMethod.GET` and `POST` prevent a public GET rule from accidentally applying to POST.
4. `{id:[0-9]+}` uses a regex constraint; `GET /api/books/abc` is denied by the last rule even though the controller could map it.
5. `/api/files/*.json` only makes filenames ending in `.json` within one segment public.
6. `/api/admin/**` only allows users with `ROLE_EDITOR`. `hasRole("EDITOR")` automatically checks authority `ROLE_EDITOR`; the account's `roles("EDITOR")` matches.
7. `httpBasic` lets MockMvc exercise real authentication instead of a pre-mocked Principal.
8. CSRF stays enabled; `POST` needs a token. For a production API using browser cookies and CORS, analyze the threat model instead of disabling CSRF carelessly.

### 9.4. ApiController

`src/main/java/demo/ApiController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/books")
    public String books() {
        return "books";
    }

    @GetMapping("/api/books/{id}")
    public String book(@PathVariable String id) {
        return "book-" + id;
    }

    @GetMapping("/api/books/{id}/chapters")
    public String chapters(@PathVariable String id) {
        return "chapters-" + id;
    }

    @PostMapping("/api/books")
    public String createBook() {
        return "created";
    }

    @GetMapping("/api/files/{name}")
    public String file(@PathVariable String name) {
        return "file-" + name;
    }

    @GetMapping("/api/admin/{action}")
    public String admin(@PathVariable String action) {
        return "admin-" + action;
    }

    @GetMapping("/external")
    public String external() {
        return "external";
    }
}
```

**Observation:** the controller has mapping `GET /api/books/{id}`, which is broader than Security's `GET /api/books/{id:[0-9]+}` rule. That means requests with alphabetic ids are **denied first by Security** and never reach the controller. In a real system, keep policies and routes aligned and test thoroughly instead of introducing unnecessary discrepancies.

### 9.5. MockMvc Tests

`src/test/java/demo/RequestMatcherTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestMatcherTest {

    @Autowired
    MockMvc mvc;

    @Test
    void exactPublicEndpointsAreAccessible() throws Exception {
        mvc.perform(get("/api/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
        mvc.perform(get("/api/books"))
                .andExpect(status().isOk())
                .andExpect(content().string("books"));
    }

    @Test
    void exactMatchDoesNotOpenAChildPath() throws Exception {
        mvc.perform(get("/api/ping/extra")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void numericPathVariableRequiresLogin() throws Exception {
        mvc.perform(get("/api/books/42"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/books/42")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("book-42"));
    }

    @Test
    void nonNumericPathVariableIsDeniedBeforeMvc() throws Exception {
        mvc.perform(get("/api/books/abc")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void oneSegmentWildcardDoesNotOpenNestedRoutes() throws Exception {
        mvc.perform(get("/api/books/42/chapters")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/books/42/chapters")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("chapters-42"));
        mvc.perform(get("/api/books/42/chapters/extra")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void suffixWildcardOnlyAllowsJson() throws Exception {
        mvc.perform(get("/api/files/guide.json"))
                .andExpect(status().isOk())
                .andExpect(content().string("file-guide.json"));
        mvc.perform(get("/api/files/guide.txt")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminDoubleStarStillChecksRole() throws Exception {
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-audit"));
    }

    @Test
    void postHasDifferentPolicyAndNeedsCsrf() throws Exception {
        mvc.perform(post("/api/books")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/books")
                        .with(httpBasic("reader", "readerPass!"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/books")
                        .with(httpBasic("editor", "editorPass!"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("created"));
    }

    @Test
    void fallbackChainBlocksOutsideApi() throws Exception {
        mvc.perform(get("/external")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void queryDoesNotAlterExactPath() throws Exception {
        mvc.perform(get("/api/ping").param("debug", "true"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
```

**Expected result:** 10 tests PASS with the demo project/configuration. The tests intentionally use `httpBasic(...)` so requests go through real authentication logic. For `denyAll` URLs, the tests send valid credentials so **403** (authenticated but denied) is expected; if anonymous, the HTTP Basic entry point may return **401** instead of 403. That is different from a 403 due to a missing CSRF token.

**Aspects tested:**

- Exact literals do not open child paths.
- Regex variables only allow numeric ids and require authentication.
- `*` matches only one segment, not nested paths.
- `*.json` does not open other file extensions.
- `**` covers admin URLs while still requiring the role.
- `GET` and `POST` on the same path have different policies, with CSRF still active.
- Fallback chain denies routes outside `/api/**`.
- Query string does not alter the exact path matcher's result.

### 9.6. Running and Testing With curl

```bash
gradle test
gradle bootRun
```

If using the Gradle Wrapper: run `./gradlew test`/`./gradlew bootRun` (macOS/Linux) or `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows).

```bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/api/books/42
curl -i -u reader:readerPass! \
     http://localhost:8080/api/books/42
curl -i -u reader:readerPass! \
     http://localhost:8080/api/admin/audit
curl -i -u editor:editorPass! \
     http://localhost:8080/api/admin/audit
curl -i http://localhost:8080/api/files/guide.json
```

Expected statuses in order: `200`, `401`, `200`, `403`, `200`, `200`. You do not need to match the actual BCrypt hash because it uses a random salt. Localhost HTTP is **for practice only**; Basic credentials in production must travel over HTTPS.

With CSRF enabled in the demo, a direct POST without a CSRF token can return **403**. `with(csrf())` in MockMvc is a test-request helper, not advice to hardcode tokens into real HTTP clients.

## 10. Edge Cases That Easily Cause Security Bypasses

### 10.1. Trailing Slash

`/api/books/42` and `/api/books/42/` can behave differently under Spring MVC 6 defaults. When upgrading versions or adding canonical URL redirects, test both Security and MVC. Never widen a matcher just to "fix" a trailing slash.

### 10.2. URL Encoding and Firewall

`%2F`, `%2e`, `..`, double slashes, semicolons/matrix variables, Unicode normalization, and encoded percent signs can be handled differently by proxies, containers, MVC, and Security. `StrictHttpFirewall` can reject unusual requests before authorization.

Do not relax the firewall to let dangerous requests through without understanding how the same path is decoded and normalized across **all** layers. A mismatch between routing and security patterns can expose unintended data.

### 10.3. Context Path, Servlet Path, Forwarded Prefix

An application deployed at `/myapp` has browser URL `/myapp/api/books`, yet matchers typically only need `/api/books` because the container manages the context path. Meanwhile `spring.mvc.servlet.path` differs from context path; `MvcRequestMatcher.Builder.servletPath(...)` may be needed depending on the setup.

A reverse proxy may rewrite URIs or add `X-Forwarded-Prefix`. Configure forwarded header handling only from trusted proxies and test the path **that the Servlet container actually receives**, not just the URL shown in the browser.

### 10.4. Controller Mapping Is Not Data Access Permission

A path `/api/orders/{id}` only selects an endpoint; it does not check whether the order belongs to the principal. Use trusted object-level authorization and tenant binding in services/authorization managers; do not assume `hasRole("USER")` prevents IDOR/BOLA.

### 10.5. Not Every Request Belongs to the API Chain

`/actuator/**`, `/error`, static files, and internal forwards can lie outside the `/api/**` matcher. You need a fallback chain or dedicated policy for endpoints actually in use, and must verify dispatcher types and how error handling interacts with Security. Do not exclude paths from Spring Security via `web.ignoring()` when you only need `permitAll()` while keeping security filters and headers active.

### 10.6. HTTP Methods and CORS

CORS preflight `OPTIONS` can arrive before the actual GET/POST request. A GET-only matcher does not match OPTIONS. Configure CORS in Spring Security/MVC with trusted origins and allowed methods, rather than opening "all OPTIONS" unconditionally and forgetting to review it. With browser cookies/API tokens, CSRF and CORS are separate concerns: CORS governs cross-origin JS reading/sending per policy, while CSRF protects state-changing requests.

## 11. Layer-by-Layer Troubleshooting

If a URL returns 401/403 when you expected 200 (or vice versa), check in order:

1. Method + URI path in the actual request; do not confuse with query parameters.
2. Context path, servlet path, and proxy-rewritten paths.
3. Which `SecurityFilterChain` is selected, `securityMatcher`, and chain `@Order`.
4. Matcher type: `MvcRequestMatcher`, Ant, or PathPattern; is it compatible with MVC?
5. Which rule matches first in `authorizeHttpRequests`; is a broad rule shadowing a specific rule?
6. Does `*` match strictly one segment; is `**` placed validly at the end of the pattern?
7. Do `{id}`/`{id:regex}` match the actual URL data?
8. Are HTTP methods GET/POST/PUT/DELETE/HEAD/OPTIONS specified accurately?
9. `authenticated()`, `hasRole`/`hasAuthority`, object ownership, and tenant policies.
10. Is CSRF causing POST to return 403; have you tested with a valid token to isolate the error?
11. Did Security block before MVC, or did MVC itself return 404/405?
12. StrictHttpFirewall, encoded URIs, trailing slashes, and CORS/proxy headers.
13. Is there a fallback chain covering every path that needs protection?
14. Regression tests: anonymous, reader, and editor against positive and negative URLs.

You can temporarily enable DEBUG in development:

```properties
logging.level.org.springframework.security=DEBUG
```

Never log Authorization headers, tokens, cookies, or session IDs. A log line like `"Securing GET..."` only shows that the filter chain is running; it does not prove the right authorization rule was chosen.

## 12. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `/api/**` authenticated before `/api/admin/**` hasRole | Admin rule never runs | Place specific rules first |
| `securityMatcher("/api/**")` while trying to protect `/admin/**` inside | Request never enters the API chain | Add an appropriate chain/fallback |
| `/api/books/**` instead of `/api/books/{id}` | Exposes all subresources | Narrow the pattern |
| Mistaking `*` for multiple path segments | Deeper URLs match unexpectedly | Distinguish `*` and `**` |
| `requestMatchers("/api/books").permitAll()` for GET/POST | Can accidentally open POST | Constrain `HttpMethod` |
| Assuming `{id}` enforces a numeric ID | Rule accepts letters too | Use regex constraints and validate |
| Assuming `{id}` checks ownership | IDOR/BOLA | Object/tenant-level authorization |
| MVC uses PathPattern while Security arbitrarily uses Ant | Routing/authorization mismatch | Align matching semantics |
| Missing fallback chain | URLs outside the chain may be unprotected | Add a catch-all chain |
| Testing only 200 without testing 403/401 | Overly broad rules go unnoticed | Test roles/anonymous/negative cases |
| Seeing 403 on POST and assuming hasRole worked | Actually blocked by CSRF | Test `with(csrf())` and roles separately |
| Putting full URLs in path matchers | Pattern does not match | Use paths only; handle host policies separately |
| Mixing up context path and servlet path | Pattern has extra or missing prefix | Test real deployment setup |
| Relaxing StrictHttpFirewall to allow encoded slashes | Increases bypass risk | Standardize on canonical URIs |
| Having a regex route without service data checks | Missing resource permissions | Validate and check ownership |

## 13. Policy Design Checklist

- [ ] Clearly identify paths, HTTP methods, and endpoints requiring protection.
- [ ] Prefer exact paths before opening broad wildcards.
- [ ] `*` for one segment; `**` for multiple trailing segments under PathPattern.
- [ ] `{id}` does not imply numeric or ownership; use regex/authorization accordingly.
- [ ] Matcher type matches the Spring MVC parser and actual Servlet mapping.
- [ ] `securityMatcher` accurately covers the chain's intended routes.
- [ ] `requestMatchers` ordered from specific rules to broad rules.
- [ ] Include a match-all fallback `SecurityFilterChain` when needed.
- [ ] Use `anyRequest().denyAll()` in chains intended to deny by default.
- [ ] Constrain HTTP methods; plan for HEAD/OPTIONS/CORS.
- [ ] Keep CSRF enabled when the threat model requires it; test POST with valid CSRF.
- [ ] Test trailing slashes, encoding, queries, forwarded prefixes, and custom servlet paths.
- [ ] Enforce object-level authorization for resources by id/tenant.
- [ ] Test both anonymous and multiple roles on sensitive URLs.
- [ ] Never rely solely on happy paths or CSRF-triggered 403s to claim permissions are correct.

## 14. Exercises and Self-Check

**Exercises:**

1. Make only `GET /api/ping` public, while `GET /api/ping/extra` is not public.
2. Allow logged-in users to view `GET /api/books/{id:[0-9]+}`; deny `/api/books/abc`.
3. Use `/api/files/*.json` to make only single-segment `.json` filenames public.
4. Use `/api/admin/**` for role `ADMIN` and place it before the broad `/api/**`.
5. Distinguish GET/POST on `/api/books`; use a CSRF token when testing POST.
6. Set chain `securityMatcher("/api/**")` and fallback deny for `/external`.
7. For `/api/users/{userId}/orders/{orderId}`, add owner/tenant checks beyond URL matching.
8. Deploy the app with context path `/myapp` and verify route matchers still work properly.
9. Compare an Ant pattern using `**` in the middle against PathPatternParser and write migration tests.
10. Add regression tests to ensure a new route at `/api/admin/reports` is not opened by another public rule.

**Self-Check Questions:**

1. Does `/api/books` match `/api/books/42`? **No.**
2. How does `*` differ from `**`? **One segment** versus **multiple remaining segments** in PathPattern syntax.
3. Does `{id}` force the id to be numeric? **No**; use regex such as `{id:[0-9]+}` if needed.
4. Does `{id}` guarantee the user owns the record? **No**; data/authorization checks are needed.
5. Does query `?lang=vi` affect an exact path matcher? **No**, if the matcher only inspects the path.
6. When two rules overlap, which wins? **The first matching rule** in the authorization configuration.
7. How does `securityMatcher` differ from `requestMatchers`? **Chain selection** versus **authorization rule selection**.
8. What if no SecurityFilterChain matches? The request may **not be protected by Spring Security**.
9. Does a public GET make POST on the same path public? **Not when the HTTP method is explicitly constrained**.
10. Will a path that matches no rule definitely return 404? **No**; Security can block it before MVC.
11. Why align the MVC and Security path engines? To prevent **routing and authorization mismatches**.
12. Should you use a broad `permitAll("/api/**")` and hope every controller checks permissions itself? **No**; it is easy to miss endpoints and expose data.

**Key takeaway:** Exact matchers target a single route; `*` matches one segment; `**` matches multiple trailing segments in `PathPattern`; `{id}`/`{id:regex}` describe URLs rather than granting ownership. **`securityMatcher` selects the `SecurityFilterChain`, and `requestMatchers` selects the authorization rule**. Both must have the right order, right HTTP method, right matching engine, and tests covering valid and malformed URLs. Deny by default and apply object-level authorization where needed.
