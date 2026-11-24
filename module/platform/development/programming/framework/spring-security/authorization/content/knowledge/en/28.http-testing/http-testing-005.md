# Testing Each HTTP Method on the Same Path

> **Scope:** Spring Security – authorization, **HTTP Testing** group. This lesson focuses on proving that **GET, POST, PUT, PATCH, and DELETE rules on the exact same URL** operate independently; properly handling caller permissions, CSRF, HTTP outcomes, and unpermitted methods. Examples use **Java 17+, Spring Boot 3.5.6, Spring Security 6.5.x, Servlet/Spring MVC, JUnit 5, MockMvc, and spring-security-test**.

## 1. Problem: Same URL Does Not Mean Same Permission

Suppose a document API places all operations on `/api/records/42`. Each HTTP method represents a different action:

| Same URL `/api/records/42` | Illustrative action | Required authority |
|---|---|---|
| `GET` | Read record | `records:read` |
| `POST` | Perform an additional creation action on the record | `records:create` |
| `PUT` | Replace record | `records:update` |
| `PATCH` | Partial update | `records:patch` |
| `DELETE` | Delete record | `records:delete` |

This is an example contract deliberately designed with **all five methods on one exact URL** to illustrate authorization. In real REST APIs, `POST` usually creates a resource under a collection (`POST /api/records`), while `PUT/PATCH/DELETE` act on a specific resource. Production route layout should reflect the domain properly; this lesson does not encourage forcing every API into this path shape.

Because the same path has different permissions, a passing test like `GET /api/records/42` **cannot prove** `DELETE /api/records/42` is protected. Tests must vary the method while **keeping the URL fixed**, then verify the required permission, response, and whether the controller is actually invoked when permitted.

### Two Decision Layers to Distinguish

1. **Spring Security – authorization:** `AuthorizationFilter` (when using `authorizeHttpRequests`) applies a `RequestMatcher` carrying both method and path. If authenticated but lacking the authority, the request typically receives **403 Forbidden**.
2. **Spring MVC – request mapping:** `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, and `@DeleteMapping` decide which handler can accept the method/path *after passing security*. If the method is unsupported by the controller after security lets it through, Spring MVC may return **405 Method Not Allowed**.

Meanwhile, **401 Unauthorized** (for example HTTP Basic requesting authentication) indicates the caller lacks valid authentication; **403 due to missing/invalid CSRF token** is another denial source that can occur before reaching authorization rules. Therefore, a single `status().isForbidden()` assertion does not guarantee the right authorization policy was tested.

## 2. Designing the Test Matrix Before Writing Code

We use three authenticated identities:

- **reader:** has `records:read`.
- **editor:** has `records:read`, `records:create`, `records:update`, `records:patch`, **without** `records:delete`.
- **admin:** has all five authorities.

For the same `/api/records/42`, the expected status matrix is:

| HTTP method | Reader | Editor | Admin | Why? |
|---|---:|---:|---:|---|
| GET | 200 | 200 | 200 | All three have `records:read` |
| POST | 403 | 200 | 200 | Reader lacks `records:create` |
| PUT | 403 | 200 | 200 | Reader lacks `records:update` |
| PATCH | 403 | 200 | 200 | Reader lacks `records:patch` |
| DELETE | 403 | 403 | 200 | Only admin has `records:delete` |

**Each `(method, user)` pair is an independent test case.** The matrix above has 5 × 3 = **15 cases**; state-changing method cases will include a **valid CSRF token** so only permission differences remain.

Additional checks outside the main matrix:

1. **Anonymous + GET** → HTTP 401 when the app uses HTTP Basic.
2. **Admin + POST without CSRF token** → HTTP 403 due to CSRF, despite having the authority.
3. **Admin + POST with CSRF token** → HTTP 200, proving the allow rule and controller mapping exist.
4. **HEAD/OPTIONS** have no authorization rule defined in the example → blocked by `anyRequest().denyAll()`, even for a user with many authorities. Different behavior when CORS/CSRF is enabled or explicit rules exist must be tested against the actual configuration.
5. **A GET request containing a query string** still uses the GET and path policy, because `requestMatchers(HttpMethod.GET, "...")` does not inspect query parameters automatically.

This is how tests are written from the intended policy. Avoid reading the implementation and generating tests that mirror every current branch; use a fixed matrix as a **security contract** so tests can catch regressions.

## 3. Principles for Configuring Method-Aware Authorization

In `SecurityFilterChain`, use the `requestMatchers(HttpMethod, String...)` overload:

```java
.requestMatchers(HttpMethod.GET,    "/api/records/*").hasAuthority("records:read")
.requestMatchers(HttpMethod.POST,   "/api/records/*").hasAuthority("records:create")
.requestMatchers(HttpMethod.PUT,    "/api/records/*").hasAuthority("records:update")
.requestMatchers(HttpMethod.PATCH,  "/api/records/*").hasAuthority("records:patch")
.requestMatchers(HttpMethod.DELETE, "/api/records/*").hasAuthority("records:delete")
.anyRequest().denyAll()
```

Essential points:

- **`HttpMethod.GET` matches only GET**, and does not automatically apply to POST, PUT, PATCH, or DELETE. Do not treat "same path" as "same rule".
- **`"/api/records/*"`** represents one segment after `/api/records/` in the example; tests use `/api/records/42`. When using MVC path matching, pay special attention to path variables, trailing slashes, servlet paths, and nested paths per the actual configuration.
- **Matcher order matters:** Spring Security evaluates rules in declaration order and uses **the first matching rule**. A path-only rule placed before a method-specific rule can swallow all methods.
- `hasAuthority("records:delete")` checks **the literal authority string**, without prepending `ROLE_`. `hasRole("ADMIN")`, by contrast, normally adds the `ROLE_` prefix; do not mix the two without understanding the mapping.
- `anyRequest().denyAll()` closes undeclared branches. When the app also has actuator, health, static resources, or CORS preflight, define policies for them intentionally; do not open all methods just to fix a failing test.
- The scope of `requestMatchers` applies only **within the selected `SecurityFilterChain`**. With multiple chains, check `securityMatcher` and chain ordering before drawing conclusions.

### Common Ordering Bug

**Wrong configuration:**

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/records/**").hasAuthority("records:read")
    .requestMatchers(HttpMethod.DELETE, "/api/records/*")
        .hasAuthority("records:delete")
    .anyRequest().denyAll()
)
```

The path-only rule at the top matches DELETE as well, so a reader holding `records:read` can pass the first rule and never reach the `records:delete` rule. This is an **HTTP-method privilege escalation** bug that the 15-case matrix catches: reader + DELETE unexpectedly succeeds.

**Right configuration:** place method-specific rules first, and put the broad fallback at the end. If a broad path rule exists, prove it does not grant access to unintended methods.

## 4. Runnable Project with Spring Boot

### 4.1. Directory Layout and Dependencies

```text
method-authorization-demo/
├── pom.xml
├── src/main/java/com/example/methodauth/
│   ├── MethodAuthorizationApplication.java
│   ├── SecurityConfig.java
│   └── RecordController.java
└── src/test/java/com/example/methodauth/
    └── HttpMethodAuthorizationTest.java
```

`pom.xml` uses Java 17 and Spring Boot 3.5.6 (managing compatible Spring Security versions via dependency management):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>method-authorization-demo</artifactId>
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

`spring-boot-starter-test` provides Spring Test, MockMvc, and JUnit Jupiter (including parameterized tests); `spring-security-test` provides `user()` and `csrf()`. The example uses HTTP Basic to observe 401/403 and intentionally **keeps default CSRF protection**.

### 4.2. Main Class

`src/main/java/com/example/methodauth/MethodAuthorizationApplication.java`:

```java
package com.example.methodauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodAuthorizationApplication.class, args);
    }
}
```

### 4.3. SecurityFilterChain: Five Permissions on the Same URL

`src/main/java/com/example/methodauth/SecurityConfig.java`:

```java
package com.example.methodauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/records/*")
                    .hasAuthority("records:read")
                .requestMatchers(HttpMethod.POST, "/api/records/*")
                    .hasAuthority("records:create")
                .requestMatchers(HttpMethod.PUT, "/api/records/*")
                    .hasAuthority("records:update")
                .requestMatchers(HttpMethod.PATCH, "/api/records/*")
                    .hasAuthority("records:patch")
                .requestMatchers(HttpMethod.DELETE, "/api/records/*")
                    .hasAuthority("records:delete")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .authorities("records:read")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password("{noop}editor123")
            .authorities(
                "records:read",
                "records:create",
                "records:update",
                "records:patch")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .authorities(
                "records:read",
                "records:create",
                "records:update",
                "records:patch",
                "records:delete")
            .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
```

**Explanation:** `UserDetailsService` creates sample users allowing testing via HTTP Basic. The `authorities(...)` values are literal strings. `"{noop}"` does not protect passwords and is **only for local runnable examples**; production requires a secure password encoder, a real identity source, and HTTPS.

We do not disable CSRF via `csrf(csrf -> csrf.disable())`. With cookies/sessions/HTTP Basic in browsers, CSRF protection has security value and tests must reflect that. If a real API uses cookie-independent Bearer tokens and a stateless design, the team can re-evaluate the CSRF policy under a threat model; removing CSRF is an architectural decision, not a trick to make tests pass.

### 4.4. Controller Clearly Distinguishing Methods

`src/main/java/com/example/methodauth/RecordController.java`:

```java
package com.example.methodauth;

import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/records/{id}")
public class RecordController {
    @GetMapping
    public Map<String, String> get(@PathVariable String id) {
        return Map.of("method", "GET", "id", id);
    }

    @PostMapping
    public Map<String, String> post(@PathVariable String id) {
        return Map.of("method", "POST", "id", id);
    }

    @PutMapping
    public Map<String, String> put(@PathVariable String id) {
        return Map.of("method", "PUT", "id", id);
    }

    @PatchMapping
    public Map<String, String> patch(@PathVariable String id) {
        return Map.of("method", "PATCH", "id", id);
    }

    @DeleteMapping
    public Map<String, String> delete(@PathVariable String id) {
        return Map.of("method", "DELETE", "id", id);
    }
}
```

Each handler returns a JSON body with two fields, `method` and `id`, helping tests verify **the right controller method was reached**, not just the status. The handlers intentionally do not update a database so the lesson isolates security behavior. In real APIs, POST/PUT/PATCH/DELETE must have proper data semantics, validation, per-record permissions, and transactions.

Because multiple mappings share one URL, defining only `@GetMapping` and sending a POST will not cause MVC to call GET. However, **Spring Security runs before MVC**; a method without a rule can be rejected by `denyAll()` with 403 before MVC ever has a chance to return 405.

## 5. Writing Executable Matrix Tests

### 5.1. Why Use `@SpringBootTest` and MockMvc?

`@SpringBootTest` + `@AutoConfigureMockMvc` boots the Spring application and integrates the Spring Security filter chain into MockMvc. This tests **the request matcher, configured authentication, CSRF, authorization filter, and MVC controller together**.

We intentionally use `with(user(...))` to create callers with specific authorities; there is no need to emit HTTP Basic credentials for every case. Limitation: `with(user(...))` **does not verify password hashing or `UserDetailsService`**. If you want to test real authentication, include an HTTP integration case via Basic or `httpBasic(...)`.

### 5.2. Complete Test Class

`src/test/java/com/example/methodauth/HttpMethodAuthorizationTest.java`:

```java
package com.example.methodauth;

import static org.junit.jupiter.params.provider.Arguments.arguments;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.ResultActions;

@SpringBootTest
@AutoConfigureMockMvc
class HttpMethodAuthorizationTest {
    private static final String PATH = "/api/records/42";

    @Autowired
    MockMvc mvc;

    private static UserDetails actor(String name) {
        return switch (name) {
            case "reader" -> User.withUsername("reader")
                .password("{noop}ignored")
                .authorities("records:read")
                .build();
            case "editor" -> User.withUsername("editor")
                .password("{noop}ignored")
                .authorities(
                    "records:read",
                    "records:create",
                    "records:update",
                    "records:patch")
                .build();
            case "admin" -> User.withUsername("admin")
                .password("{noop}ignored")
                .authorities(
                    "records:read",
                    "records:create",
                    "records:update",
                    "records:patch",
                    "records:delete")
                .build();
            default -> throw new IllegalArgumentException("Unknown actor: " + name);
        };
    }

    // Contract designed in section 2. Do not derive expectedStatus from the actual rules.
    static Stream<Arguments> accessMatrix() {
        return Stream.of(
            arguments(HttpMethod.GET,    "reader", 200),
            arguments(HttpMethod.GET,    "editor", 200),
            arguments(HttpMethod.GET,    "admin",  200),

            arguments(HttpMethod.POST,   "reader", 403),
            arguments(HttpMethod.POST,   "editor", 200),
            arguments(HttpMethod.POST,   "admin",  200),

            arguments(HttpMethod.PUT,    "reader", 403),
            arguments(HttpMethod.PUT,    "editor", 200),
            arguments(HttpMethod.PUT,    "admin",  200),

            arguments(HttpMethod.PATCH,  "reader", 403),
            arguments(HttpMethod.PATCH,  "editor", 200),
            arguments(HttpMethod.PATCH,  "admin",  200),

            arguments(HttpMethod.DELETE, "reader", 403),
            arguments(HttpMethod.DELETE, "editor", 403),
            arguments(HttpMethod.DELETE, "admin",  200)
        );
    }

    @ParameterizedTest(name = "{index}: {0} by {1} -> {2}")
    @MethodSource("accessMatrix")
    void samePathRespectsHttpMethod(
            HttpMethod method, String username, int expectedStatus)
            throws Exception {

        MockHttpServletRequestBuilder builder = request(method, PATH)
                .with(user(actor(username)));

        // Valid token so 403 cases reflect missing authority,
        // not blocked by CSRF before checking permissions.
        if (method == HttpMethod.POST
                || method == HttpMethod.PUT
                || method == HttpMethod.PATCH
                || method == HttpMethod.DELETE) {
            builder.with(csrf());
        }

        ResultActions result = mvc.perform(builder)
                .andExpect(status().is(expectedStatus));

        if (expectedStatus == 200) {
            result.andExpect(jsonPath("$.method").value(method.name()))
                  .andExpect(jsonPath("$.id").value("42"));
        }
    }

    @Test
    void anonymousGetRequiresAuthentication() throws Exception {
        mvc.perform(get(PATH))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfReturns403EvenWhenAuthorized() throws Exception {
        mvc.perform(post(PATH).with(user(actor("admin"))))
           .andExpect(status().isForbidden());

        mvc.perform(post(PATH)
                .with(user(actor("admin")))
                .with(csrf()))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.method").value("POST"));
    }

    static Stream<Arguments> unlistedMethods() {
        return Stream.of(
            arguments(HttpMethod.HEAD),
            arguments(HttpMethod.OPTIONS)
        );
    }

    @ParameterizedTest(name = "unlisted method {0} is denied")
    @MethodSource("unlistedMethods")
    void unlistedMethodsAreDeniedByFallback(HttpMethod method)
            throws Exception {
        mvc.perform(request(method, PATH).with(user(actor("admin"))))
           .andExpect(status().isForbidden());
    }

    @Test
    void queryStringDoesNotChangeGetPermission() throws Exception {
        mvc.perform(get(PATH)
                .queryParam("view", "summary")
                .with(user(actor("reader"))))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.method").value("GET"));
    }
}
```

**Number of test cases:** 15 test instances from the matrix, 1 anonymous case, 1 CSRF without/with token comparison, 2 unpermitted method cases, and 1 query string case — totaling **20 test executions** (in which the CSRF test performs two HTTP requests).

**Why are these tests more reliable than a standalone 403 test?**

1. For POST/PUT/PATCH/DELETE, `with(csrf())` creates a proper valid token supported by Spring Security Test. If reader gets 403 in this matrix, it is not due to an intentionally missing CSRF token.
2. For admin, every valid method receives **200 and the matching JSON method**, proving requests reach the right MVC handler.
3. The separate test without CSRF for admin proves **same permission with changed CSRF token changes the outcome**.
4. HEAD and OPTIONS are disallowed by the illustrative policy, even though Spring MVC can automatically support HEAD from GET and return the `Allow` header for OPTIONS.
5. Query strings do not alter method-based authorization; if a policy depends on query/body, another check mechanism at the appropriate layer is needed, not just a URL matcher.

### 5.3. Running the Tests

Open a terminal in the folder containing `pom.xml`:

```bash
mvn test
```

When all cases pass, Maven exits cleanly (`exit code 0`) and JUnit reports zero failures/errors. The class/case counts printed in Maven logs depend on Surefire configuration; rely on assertion results rather than assuming an exact stdout line from the plugin.

To run the application standalone:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
# Reader has read permission; expect HTTP 200.
curl -i -u reader:reader123 http://localhost:8080/api/records/42

# Unauthenticated; HTTP Basic typically returns HTTP 401.
curl -i http://localhost:8080/api/records/42

# Reader attempts DELETE: usually 403, but do not use this command
# to prove the authorization rule because default CSRF also blocks.
curl -i -X DELETE -u reader:reader123 http://localhost:8080/api/records/42
```

When calling `POST/PUT/PATCH/DELETE` with curl, you must perform the proper **CSRF token exchange** per the application's configured mechanism; a command with only HTTP Basic credentials is **not enough** to prove the user lacks permission. The MockMvc `with(csrf())` cases above are the controlled security testing method in this lesson.

On Windows PowerShell, use `curl.exe` to avoid the `curl` alias to another cmdlet. Do not put demo passwords into CI scripts or shell history in real systems.

## 6. Interpreting 200, 401, 403, 404, and 405 Correctly

The HTTP status alone is not enough to conclude the cause. For the same path and method:

| Status | First interpretation | Check next |
|---|---|---|
| **200** | Request passed security and the handler succeeded | Verify response body `method`, controller was called, and no bypass path exists |
| **401** | Entry point requires authentication (HTTP Basic) | Check credentials, session/token, `AuthenticationEntryPoint` |
| **403** | Permission denied **or** CSRF/another filter blocked | Is `csrf()` valid? Are `Authentication` and authorities correct? |
| **404** | No matching route/resource, or hidden per app policy | Check URL, base path, servlet path, controller mapping |
| **405** | MVC matches the path but does not support that method | Only visible if security lets the request pass to MVC |

For example: if a controller only has `@GetMapping("/api/items/{id}")` and security policy allows POST to that path, POST can return 405 because there is no `@PostMapping`. If security denies POST first, HTTP 403 appears and cannot be used to conclude whether the controller has a POST handler.

### Watch Out for HEAD and OPTIONS

Spring MVC has special behavior: `@GetMapping` usually supports **HEAD** automatically; **OPTIONS** can be handled by MVC to return the list of methods via the `Allow` header. However, the security matcher `HttpMethod.GET` **is not equivalent** to `HttpMethod.HEAD`, and an OPTIONS request is not automatically allowed just because MVC supports OPTIONS.

In the example, `anyRequest().denyAll()` blocks both HEAD and OPTIONS for authenticated users before reaching MVC. That is **the result of the policy under test**, not a rule that every project must follow.

When building cross-origin browser APIs, **CORS preflight** is usually an OPTIONS request with `Origin` and `Access-Control-Request-Method`. You must configure CORS alongside the security chain appropriately so preflight is handled before authentication-requiring rules; enabling `cors(...)` or allowing OPTIONS must be based on an approved origin/method/header policy. Test CORS preflight **separately** from an ordinary OPTIONS request, as the two cases are not equivalent.

## 7. Quick Triage When Tests Fail

A sequence that avoids fixing the wrong thing:

1. **Identify exact URL and HTTP method.** `GET` and `POST` on the same path string are two different requests. Check trailing slashes, context path, servlet path, URL encoding, and proxy rewrites.
2. **Check authentication.** With `with(user(...))`, the principal has specific authorities; with real Basic, valid credentials are required. 401 is an authentication or entry point issue, not necessarily a role issue.
3. **Check CSRF before assuming an authorization bug.** For POST/PUT/PATCH/DELETE in apps with CSRF protection enabled, add `with(csrf())` in authorization tests; write **another test** specifically verifying missing/invalid tokens are blocked.
4. **Check method + path matchers.** Do not let `requestMatchers("/api/records/**")` match before a dedicated DELETE rule. First matching rule wins.
5. **Check literal authorities.** `hasAuthority("records:delete")` requires that exact `GrantedAuthority`; `roles("ADMIN")` creates `ROLE_ADMIN`, not `records:delete`.
6. **Check the selected chain.** With multiple `SecurityFilterChain`s, `securityMatcher` may route the request to a different chain; `anyRequest()` is only the fallback of the current chain.
7. **Check MVC mapping.** If security allows it yet 404/405 occurs, inspect `@RequestMapping` and method annotations; do not add arbitrary permissions to mask routing bugs.
8. **Check dispatchers and filters outside security.** Some requests trigger `ERROR`, `FORWARD`, or get blocked by a reverse proxy; tests should reflect the real pipeline.

For debugging, you can raise Spring Security logging in a **controlled test environment**, but avoid logging credentials, cookies, tokens, or sensitive payloads. Do not turn on system-wide TRACE in production to explain a 403 case.

## 8. Boundary Testing and Edge Cases

The primary matrix covers supported operations; real systems need additional risk-based cases.

### 8.1. Users with No Authorities and Unauthenticated Users

- **Authenticated without any `records:*`:** all five methods must be denied (with valid CSRF on mutation requests); this is the "default-deny for lowest role" test.
- **Anonymous:** with HTTP Basic, protected requests can return 401. If form login is configured, an HTTP 302 redirect to login is normal; 401 assertions must match the authentication mechanism.
- **Misspelled/wrong-case authority:** `records:Delete` differs from `records:delete`. Testing exact literal authorities catches mapping bugs.

### 8.2. Resource-Level Authorization

`records:read` only proves a **functional capability**; it does not automatically prove reader can view someone else's record 42. For an "only the owner can edit/delete" policy, add **object-level authorization** checks at the service/method layer or an appropriate `AuthorizationManager`. Tests must cover both own records and other users' records, using the same HTTP method and authority.

Supplementary table example:

| User | Method | Record ID | Expectation |
|---|---|---|---|
| Editor owning record | PATCH | Own | Allow if domain policy permits |
| Non-owner Editor | PATCH | Someone else's | 403 or existence-hiding result per design |
| Admin | DELETE | Managed record | Allow if domain policy permits |

This is an **illustration of an extended policy**, not built-in behavior from `hasAuthority(...)` in the example.

### 8.3. Method Overrides and Client/Proxy Differences

Some apps have `_method` mechanisms, proxy rewrites, or gateways supporting HTTP method overrides. If enabled, verify that the **effective method at the security filter** and the method **MVC receives** are consistent; avoid cases where a gateway allows POST while the backend interprets DELETE. In production-like environments, run integration tests through the gateway to catch discrepancies across layers. Never assume the framework enables all override styles automatically.

### 8.4. CORS, Other Filter Chains, and Unsupported Method Errors

- `OPTIONS` requests with preflight headers must be tested against real CORS config, not used as a stand-in for plain OPTIONS.
- `HEAD` may be handled by Spring MVC via GET, yet still needs an explicit security policy.
- `TRACE`/`CONNECT` should normally be disabled or blocked at the appropriate server/gateway; do not probe production directly without reason and authorization.
- If `DELETE` is absent from the controller, security policy can still block with 403 before MVC; to assert 405, construct a scenario that **passes security** and has no handler for that method.

### 8.5. Bypass Testing and Rule Order

A very valuable extra regression test is verifying **reader + DELETE returns 403** even though reader holds `records:read`. This case fails if someone accidentally inserts `.requestMatchers("/api/records/**").hasAuthority("records:read")` ahead of the DELETE rule, catching a dangerous config change.

Additionally, test neighboring paths such as `/api/records/42/history` if the app has nested resources, because `*` and `**` have different matcher scopes. Never assume child endpoints are protected like parent endpoints without tests.

## 9. Common Bugs and Fixes

| Symptom | Typical cause | Fix |
|---|---|---|
| Reader POST 403 even with `records:create` | Test missing/invalid CSRF token | Use `with(csrf())` to test authorization; write a separate test for CSRF |
| Reader DELETE returns 200 despite lacking delete permission | Broad path matcher placed before DELETE matcher | Move method-specific rules earlier, keep `anyRequest().denyAll()` |
| Editor PATCH 403 while PUT 200 | Missing `records:patch` grant or missing PATCH rule | Check literal authority and method-based rule order |
| Admin DELETE 404/405 instead of 200 | Security likely passed; controller path/method is wrong | Check `@DeleteMapping` and actual route |
| Unauthenticated test expected 403, got 401 | HTTP Basic uses `AuthenticationEntryPoint` | Separate anonymous tests (401) from authenticated-missing-permission tests (403) |
| GET 200, HEAD 403 | Rule matches only GET; fallback denies HEAD | Write explicit HEAD policy if app needs HEAD |
| OPTIONS preflight blocked | CORS not configured with the filter chain | Test real preflight and configure CORS properly; avoid careless `permitAll` |
| MockMvc test bypasses security and every request returns 200 | Standalone MockMvc built without attaching Spring Security filters | Use `@SpringBootTest` + `@AutoConfigureMockMvc` or `springSecurity()` |
| Test checks only status 200 and hits the wrong handler unnoticed | Missing body/side-effect assertions | Assert `$.method` and expected business outcomes |
| GET policy works yet production has a bypass | Gateway/servlet path/chain differs from MockMvc | Add HTTP integration tests through server/gateway in a controlled environment |
| Test matrix derives expectations from the implementation | Tests mirror existing logic and miss config bugs | Use an independent policy table approved by product/security |

## 10. Lesson Completion Checklist

- [ ] Have **a single URL** and at least five methods (GET, POST, PUT, PATCH, DELETE) to distinguish.
- [ ] `SecurityFilterChain` defines rules by **method + path** with a `denyAll` fallback at the end.
- [ ] Test matrix covers **authorized and unauthorized** cases for each method.
- [ ] Mutation tests **include valid CSRF** when the goal is testing authorization.
- [ ] Have a dedicated test showing **missing CSRF gets 403 even when the user has permission**.
- [ ] Have anonymous tests matching the auth mechanism; in the HTTP Basic demo → 401.
- [ ] Allowed-case responses verify **the right controller method**, not just status.
- [ ] Never conflate **403 from security/CSRF** with **405 from MVC mapping**.
- [ ] HEAD and OPTIONS are evaluated separately; CORS preflight has its own policy if the API serves browsers.
- [ ] If multiple chains, method overrides, owner-based permissions, or gateways exist, add tests along real paths.
- [ ] Every rule change re-runs the matrix to catch privilege-escalation regressions.

## Official Documentation

- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): rule order, matching by HTTP method, `anyRequest().denyAll()`, and testing.
- [Spring Security – CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): using `with(csrf())`/invalid CSRF tokens in MockMvc.
- [Spring Security – MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `with(user(...))` and `@WithMockUser`.
- [Spring Security – Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): integrating the security filter chain into MockMvc.
- [Spring Framework – Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `@GetMapping`, `@PostMapping`, HEAD/OPTIONS support, and HTTP method mapping.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): handling preflight before requiring authentication.
