# Endpoint Matrix by HTTP Method, Role, and Login State in Spring Security Servlet

## 1. The Problem: One Endpoint Has Multiple Outcomes Depending on Caller and HTTP Method

In Spring MVC, a path like `/api/orders/42` may support `GET`, `PUT`, and `DELETE`. Not all three operations require the same permission. An unauthenticated caller may be rejected, a `ROLE_MEMBER` account may only view/edit, while an `ROLE_ADMIN` administrator may delete. When using cookies/sessions, state-changing requests must also pass **CSRF** checks.

Therefore, the testing question is not merely "Does this URL return 200?", but:

> **Given HTTP method M, path P, authentication state S, authority set R, and extra security condition C, what must the application return and does it perform only the permitted effect?**

An endpoint matrix turns these decisions into an automated test contract, preventing cases where a URL is opened properly yet another HTTP method is accidentally left exposed, or only the admin happy path is tested while regular users are forgotten.

In this lesson we will:

- Build a matrix of **HTTP method × endpoint × anonymous/authenticated × role × CSRF**.
- Accurately distinguish **401 Unauthorized**, **403 Forbidden**, and success codes **200/201/204** in a concrete configuration.
- Write a `SecurityFilterChain` with **HTTP-method-scoped request matchers**, clear ordering, and default denial for undeclared paths.
- Build a **Java 17 + Spring Boot 3.3.5 + Spring Security 6 Servlet** application and test it with `@SpringBootTest`, `@AutoConfigureMockMvc`, `MockMvc`, and JUnit 5 parameterized tests.
- Test CSRF separately so a missing-token error is never confused with a missing-role error.
- Understand the limits of a URL matrix: object/tenant permissions, sessions, CORS, HEAD/OPTIONS, and method-level security require additional tests.

**Scope:** Spring Security on the **Servlet stack** with `authorizeHttpRequests`. The example uses **HTTP Basic** so 401/403 response statuses are clear in tests. Applications using form login or OAuth2 Login may redirect 302 for unauthenticated users; do not copy HTTP Basic expectations blindly into every project.

## 2. Two Crucial Axes: Method and Identity State

### 2.1. HTTP Method Changes the Meaning of a URL

| Method | Common purpose | May need CSRF in browser apps? | Example |
| --- | --- | --- | --- |
| `GET` | Read resource | No, provided it follows non-mutating semantics | `GET /api/orders/42` |
| `HEAD` | Fetch response metadata without body | No under default CSRF matcher | `HEAD /api/orders/42` |
| `POST` | Create resource / execute command | Yes, if using a context browsers auto-send like session cookies | `POST /api/orders` |
| `PUT` | Replace/update resource | Yes | `PUT /api/orders/42` |
| `PATCH` | Partially update resource | Yes | `PATCH /api/me` |
| `DELETE` | Delete resource | Yes | `DELETE /api/orders/42` |
| `OPTIONS` | Query supported methods/capabilities; browsers may send CORS preflight | Usually ignored by default CSRF, yet may need explicit CORS config | `OPTIONS /api/orders` |

Spring Security's `CsrfFilter` typically ignores **GET, HEAD, TRACE, and OPTIONS** under its default matcher, protecting the remaining methods. That does not make a data-mutating GET safe: GET must be designed read-only. Never use `GET /admin/delete?id=42` and rely on default CSRF not requiring a token.

**Same URL, different method may require different roles.** `requestMatchers(HttpMethod.GET, "/api/orders/*")` is not the same as `requestMatchers(HttpMethod.DELETE, "/api/orders/*")`. Also never assume `ROLE_ADMIN` implies `ROLE_MEMBER`; if a role hierarchy is desired, define it explicitly.

### 2.2. Login State Does Not Equal Permission

States to distinguish:

| State | Authentication/authorities | Testing meaning |
| --- | --- | --- |
| **Anonymous** | No authenticated user; Spring may set `AnonymousAuthenticationToken` | For endpoints requiring auth, HTTP Basic usually returns 401 |
| **Wrong credentials** | Tried Basic with wrong password, not authenticated | Usually 401 with HTTP Basic |
| **Authenticated MEMBER** | `ROLE_MEMBER` | Can access MEMBER routes, does not automatically hold ADMIN |
| **Authenticated ADMIN** | `ROLE_ADMIN` | Can access ADMIN routes, does not automatically hold `ROLE_MEMBER` |
| **Authenticated yet lacking role** | Logged in, insufficient permissions | Usually 403 from authorization |
| **Expired session / no cookie sent** | Current request lacks valid authentication | Like anonymous, depending on entry point |
| **Locked/disabled account** | Provider may reject login or an existing session may retain stale state | Test account status/revocation policies separately |

**A 403 status alone does not prove the role rule ran.** For a POST without a CSRF token, `CsrfFilter` can block the request before `AuthorizationFilter` checks roles. To test POST/PUT/PATCH/DELETE roles cleanly, **supply a valid CSRF token in the test** first, then write a separate test suite for missing/invalid CSRF.

## 3. Interpreting HTTP Statuses Per Configuration

| Status | Meaning in tests | Inference to avoid |
| --- | --- | --- |
| **200 OK** | Request permitted and handler returned data | Does not prove resource ownership was checked if the controller has no ACL |
| **201 Created** | Handler created a resource and reported success | Real tests should also verify state/`Location`/headers where present |
| **204 No Content** | Handler succeeded with empty body | Not every PUT/PATCH/DELETE is required to return 204 |
| **302 Found** | Redirect, e.g., to the form-login page | Do not confuse with HTTP Basic 401; check `Location` |
| **401 Unauthorized** | Client is not validly authenticated and needs authentication | "Unauthorized" here mainly means **unauthenticated**, not "logged in with wrong role" |
| **403 Forbidden** | Server understood the request yet refused it, possibly for missing role or CSRF | Must identify which filter/condition rejected it |
| **404 Not Found** | Handler has no resource, or app deliberately hides existence of unauthorized items | Not always a routing bug; may be intentional information hiding |
| **405 Method Not Allowed** | MVC saw the route yet the handler does not support that method | If Security denies before MVC, you may get 401/403 instead of 405 |

In the HTTP Basic example below, requests **with CSRF supplied when required** follow these rules: anonymous access to a protected endpoint gets 401; authenticated caller lacking the role gets 403; caller with sufficient role gets 200, 201, or 204 depending on the handler. These results **are tied to the demo's configuration**, not a universal guarantee across all Spring Security apps.

When using `formLogin()`, unauthenticated browser GETs usually redirect to `/login`; with bearer-token APIs, 401 responses and `WWW-Authenticate` may carry different error info. If an app customizes `AuthenticationEntryPoint` or `AccessDeniedHandler`, update the matrix to match the real contract.

## 4. Designing a Matrix for a Sample API

The simulated app has two accounts:

- `member`: holds exact `ROLE_MEMBER`.
- `admin`: holds exact `ROLE_ADMIN`; **does not** hold `ROLE_MEMBER`.

Per-endpoint policy:

| Method | URL | `SecurityFilterChain` policy | Success result |
| --- | --- | --- | --- |
| GET | `/public/ping` | `permitAll()` | 200 |
| GET | `/api/me` | `authenticated()` | 200 |
| PATCH | `/api/me` | `authenticated()` | 204 |
| POST | `/api/orders` | `hasRole("MEMBER")` | 201 |
| GET | `/api/orders/{id}` | `hasAnyRole("MEMBER","ADMIN")` | 200 |
| PUT | `/api/orders/{id}` | `hasRole("MEMBER")` | 204 |
| DELETE | `/api/orders/{id}` | `hasRole("ADMIN")` | 204 |
| GET | `/admin/metrics` | `hasRole("ADMIN")` | 200 |
| Any other route/method | Any remaining URL | `denyAll()` | Denied |

Assuming a valid CSRF token for PATCH/POST/PUT/DELETE, the **expected status matrix** is:

| Method | URL | Anonymous | MEMBER | ADMIN |
| --- | --- | ---: | ---: | ---: |
| GET | `/public/ping` | 200 | 200 | 200 |
| GET | `/api/me` | 401 | 200 | 200 |
| PATCH | `/api/me` | 401 | 204 | 204 |
| POST | `/api/orders` | 401 | 201 | 403 |
| GET | `/api/orders/42` | 401 | 200 | 200 |
| PUT | `/api/orders/42` | 401 | 204 | 403 |
| DELETE | `/api/orders/42` | 401 | 403 | 204 |
| GET | `/admin/metrics` | 401 | 403 | 200 |
| POST | `/admin/metrics` (undeclared) | 401 | 403 | 403 |

On the last row, **POST** is not allowed by any rule even though **GET** on the same URL is readable by ADMIN. The request falls through to `anyRequest().denyAll()`. If you want 405 for unsupported methods instead of denying before MVC, design a different routing/authorization policy and test that decided outcome; never treat 405 as a default assumption.

The matrix should also include **CSRF test groups**, **wrong-role tests**, **object-level permission tests**, and **unsupported-case tests**. An Excel/Markdown table that never runs in CI quickly goes stale; section 8 turns every cell into an executable JUnit test.

## 5. Spring Security Rule Order: method + path + role

In `authorizeHttpRequests`, request matchers are normally evaluated **in declaration order**, applying the decision of the first matching matcher. Therefore, specific rules must precede broad rules.

~~~java
// Configuration snippet, not a standalone Java file.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping")
        .permitAll()
    .requestMatchers(HttpMethod.GET, "/api/me")
        .authenticated()
    .requestMatchers(HttpMethod.PATCH, "/api/me")
        .authenticated()
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasRole("MEMBER")
    .requestMatchers(HttpMethod.GET, "/api/orders/*")
        .hasAnyRole("MEMBER", "ADMIN")
    .requestMatchers(HttpMethod.PUT, "/api/orders/*")
        .hasRole("MEMBER")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/admin/metrics")
        .hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

**Putting `requestMatchers("/api/**").authenticated()` first is wrong** if you want the specific `POST /api/orders` rule to require MEMBER: an ADMIN-only user or any logged-in user would hit the broad rule first, bypassing the role restriction. When using multiple `SecurityFilterChain` beans, you must also consider which chain is selected first (via `securityMatcher` and `@Order`), not just matcher order inside a chain.

`HttpMethod.GET`, `HttpMethod.POST`, `HttpMethod.PATCH`, etc. come from `org.springframework.http.HttpMethod`. In Spring Framework 6, `HttpMethod` is a **class with constants**, so do not write Java `switch` statements over it like the old enum; in tests you can use `HttpMethod.valueOf("GET")`.

**`hasRole("MEMBER")`** matches authority `ROLE_MEMBER`. **`hasAuthority("MEMBER")`** matches literal `MEMBER`. Do not mix the two unless defined explicitly. `hasAnyRole("MEMBER","ADMIN")` allows either one; in this example `ROLE_ADMIN` does not imply `ROLE_MEMBER`.

The `/api/orders/*` pattern in this illustration matches **a single ID segment**. If production has URLs with extra slashes, matrix variables, or special servlet paths, test the request matcher alongside MVC, the container, URL decoding, and proxies; never blindly trust a single `*` to cover all URL forms.

## 6. Complete Demo: Java 17 + Spring Boot 3.3.5 + Spring Security 6

Project structure:

~~~text
http-matrix-demo/
├── pom.xml
├── src/main/java/example/httpmatrix/HttpMatrixApplication.java
└── src/test/java/example/httpmatrix/HttpMatrixTests.java
~~~

The example **requires no database** and no external auth provider. It intentionally simulates only endpoints and HTTP statuses to focus on matrix testing. Production apps need per-order ownership checks, business transactions, persistence, and session management.

### 6.1. pom.xml

~~~xml
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
    <artifactId>http-matrix-demo</artifactId>
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
~~~

`spring-security-test` provides `csrf()`, `httpBasic()`, `user()`, and MockMvc support utilities. JUnit Jupiter/parameterized testing comes from `spring-boot-starter-test` in this setup. This is a Servlet project because `spring-boot-starter-web` uses Spring MVC, not WebFlux.

### 6.2. Spring Security and Endpoints to Test

**src/main/java/example/httpmatrix/HttpMatrixApplication.java**:

~~~java
package example.httpmatrix;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpMatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpMatrixApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("member")
                        .password("{noop}member-pass")
                        .roles("MEMBER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-pass")
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.PATCH, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST, "/api/orders")
                            .hasRole("MEMBER")
                        .requestMatchers(
                                HttpMethod.GET, "/api/orders/*")
                            .hasAnyRole("MEMBER", "ADMIN")
                        .requestMatchers(
                                HttpMethod.PUT, "/api/orders/*")
                            .hasRole("MEMBER")
                        .requestMatchers(
                                HttpMethod.DELETE, "/api/orders/*")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/admin/metrics")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/public/ping")
        Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }

        @PatchMapping("/api/me")
        ResponseEntity<Void> updateProfile() {
            return ResponseEntity.noContent().build();
        }

        @PostMapping("/api/orders")
        ResponseEntity<Map<String, String>> createOrder() {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "42"));
        }

        @GetMapping("/api/orders/{id}")
        Map<String, String> getOrder(@PathVariable String id) {
            return Map.of("id", id, "status", "created");
        }

        @PutMapping("/api/orders/{id}")
        ResponseEntity<Void> updateOrder(@PathVariable String id) {
            return ResponseEntity.noContent().build();
        }

        @DeleteMapping("/api/orders/{id}")
        ResponseEntity<Void> deleteOrder(@PathVariable String id) {
            return ResponseEntity.noContent().build();
        }

        @GetMapping("/admin/metrics")
        Map<String, Integer> metrics() {
            return Map.of("totalOrders", 1);
        }
    }
}
~~~

**Why does this configuration fit the matrix?**

- First, it matches method + path so the same `/api/orders/42` has distinct permissions for GET, PUT, and DELETE.
- `permitAll` applies only to **GET /public/ping**, not automatically opening all methods on `/public/ping`.
- `authenticated` covers GET/PATCH `/api/me`: both admin and member are allowed, while unauthenticated callers are blocked.
- `POST /api/orders` and `PUT /api/orders/*` allow only `ROLE_MEMBER`, not admin by default. This policy is chosen to illustrate that **roles are not inherited automatically**, not as a mandatory role design for every product.
- `DELETE /api/orders/*` and `GET /admin/metrics` require `ROLE_ADMIN`.
- `anyRequest().denyAll()` blocks undeclared methods/URLs, even if an MVC handler exists elsewhere.
- `httpBasic` produces 401 (unauthenticated) and 403 (authenticated but denied) easily testable over HTTP. With session login, anonymous responses might be 302.
- `csrf(Customizer.withDefaults())` preserves protection on unsafe methods. `permitAll` or `authenticated` does not disable CSRF.

**Security note:** `{noop}` stores plaintext passwords in the demo **strictly for testing**; production uses a `PasswordEncoder`, secure credential storage, and proper authentication policies. The demo PUT/DELETE controllers perform no DB mutations and have no owner/tenant checks; they illustrate route/status contracts, **not** a complete secure orders API. Real business logic must enforce ownership/ACLs at the service layer and verify actual data outcomes.

### 6.3. How to Run and Test Manually with curl

Requires a machine with JDK 17+ and Maven. From the `http-matrix-demo` directory:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
# Public endpoint: 200.
curl -i http://localhost:8080/public/ping

# Protected endpoint without credentials: 401 (HTTP Basic).
curl -i http://localhost:8080/api/me

# Member can read profile: 200.
curl -i -u member:member-pass \
  http://localhost:8080/api/me

# Member lacks admin permission: 403.
curl -i -u member:member-pass \
  http://localhost:8080/admin/metrics

# Admin can view metrics: 200.
curl -i -u admin:admin-pass \
  http://localhost:8080/admin/metrics

# Missing CSRF on unsafe method: 403, even for a member with the right role.
curl -i -u member:member-pass -X POST \
  http://localhost:8080/api/orders
~~~

`GET /api/me` as member returns JSON `{"username":"member"}`; `GET /admin/metrics` as admin returns `{"totalOrders":1}`. JSON field order is not guaranteed byte-for-byte. To test POST **with a CSRF token**, use a UI/client maintaining session and token or run the `MockMvc` tests in section 7. Never remove `CsrfFilter` just to make a curl POST return 201.

## 7. Building an Automated Runnable JUnit 5 Matrix

Instead of writing 27 near-identical methods, we model each **policy row** and generate three **caller scenarios**: `ANON`, `MEMBER`, `ADMIN`. The result is **9 rows × 3 identities = 27 test cases**.

**src/test/java/example/httpmatrix/HttpMatrixTests.java**:

~~~java
package example.httpmatrix;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpMatrixTests {

    @Autowired
    MockMvc mvc;

    record Rule(
            String method,
            String path,
            boolean includeCsrf,
            int anonymousStatus,
            int memberStatus,
            int adminStatus) {}

    record Scenario(
            String method,
            String path,
            boolean includeCsrf,
            String actor,
            int expectedStatus) {}

    // One row is the contract for method + URL, not 3 copy-pasted tests.
    static Stream<Scenario> matrix() {
        List<Rule> rules = List.of(
                new Rule(
                        "GET", "/public/ping", false,
                        200, 200, 200),
                new Rule(
                        "GET", "/api/me", false,
                        401, 200, 200),
                new Rule(
                        "PATCH", "/api/me", true,
                        401, 204, 204),
                new Rule(
                        "POST", "/api/orders", true,
                        401, 201, 403),
                new Rule(
                        "GET", "/api/orders/42", false,
                        401, 200, 200),
                new Rule(
                        "PUT", "/api/orders/42", true,
                        401, 204, 403),
                new Rule(
                        "DELETE", "/api/orders/42", true,
                        401, 403, 204),
                new Rule(
                        "GET", "/admin/metrics", false,
                        401, 403, 200),
                new Rule(
                        "POST", "/admin/metrics", true,
                        401, 403, 403)
        );

        return rules.stream().flatMap(r -> Stream.of(
                new Scenario(
                        r.method(), r.path(), r.includeCsrf(),
                        "ANON", r.anonymousStatus()),
                new Scenario(
                        r.method(), r.path(), r.includeCsrf(),
                        "MEMBER", r.memberStatus()),
                new Scenario(
                        r.method(), r.path(), r.includeCsrf(),
                        "ADMIN", r.adminStatus())
        ));
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("matrix")
    void authorizationMatrix(Scenario scenario) throws Exception {
        MockHttpServletRequestBuilder request =
                request(
                        HttpMethod.valueOf(scenario.method()),
                        scenario.path());

        // Authorization tests for unsafe methods require valid CSRF.
        // Do not mix missing CSRF into role-checking cases.
        if (scenario.includeCsrf()) {
            request.with(csrf());
        }

        if ("MEMBER".equals(scenario.actor())) {
            request.with(httpBasic("member", "member-pass"));
        } else if ("ADMIN".equals(scenario.actor())) {
            request.with(httpBasic("admin", "admin-pass"));
        }

        // ANON: do not send credentials.
        mvc.perform(request)
                .andExpect(status().is(scenario.expectedStatus()));
    }

    static Stream<Arguments> unsafeWithCredentials() {
        return Stream.of(
                Arguments.of(
                        "PATCH", "/api/me",
                        "member", "member-pass"),
                Arguments.of(
                        "POST", "/api/orders",
                        "member", "member-pass"),
                Arguments.of(
                        "PUT", "/api/orders/42",
                        "member", "member-pass"),
                Arguments.of(
                        "DELETE", "/api/orders/42",
                        "admin", "admin-pass")
        );
    }

    @ParameterizedTest
    @MethodSource("unsafeWithCredentials")
    void unsafeMethodWithoutCsrfIsForbidden(
            String method, String path, String username, String password)
            throws Exception {

        mvc.perform(request(HttpMethod.valueOf(method), path)
                        .with(httpBasic(username, password)))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfTokenIsForbidden() throws Exception {
        mvc.perform(request(HttpMethod.POST, "/api/orders")
                        .with(httpBasic("member", "member-pass"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidBasicPasswordIsUnauthenticated() throws Exception {
        mvc.perform(request(HttpMethod.GET, "/api/me")
                        .with(httpBasic("member", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void successfulGetReturnsExpectedIdentityAndData()
            throws Exception {
        mvc.perform(request(HttpMethod.GET, "/api/me")
                        .with(httpBasic("member", "member-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("member"));

        mvc.perform(request(HttpMethod.GET, "/api/orders/42")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("42"));
    }
}
~~~

**Run:**

~~~bash
mvn test
~~~

With the code and dependencies shown above, the suite is designed to contain **27 matrix cases** + **4 missing-CSRF cases** + **3 single tests**. They verify response statuses under the chosen contexts; the JSON assertions at the end ensure permitted requests genuinely reach the handlers returning expected data rather than receiving 200 from another interceptor.

To run **a single test class** with Maven Surefire:

~~~bash
mvn -Dtest=HttpMatrixTests test
~~~

Do not use `Thread.sleep()` or manually populate `SecurityContextHolder` per test. `@AutoConfigureMockMvc` in Spring Boot works with `spring-security-test` so requests traverse the `ApplicationContext`'s Security filter chain. `httpBasic(...)` adds a Basic Authorization header; it verifies authentication **through Spring Security's provider**, unlike `with(user(...))` or `@WithMockUser` which inject a simulated principal directly.

**The suite above is an example meant to compile/run in a project created from the described files; it is not a transcript of an execution on the reader's machine.** If you change `SecurityFilterChain`, role hierarchy, authentication entry point, or MVC routes, update expectations to match your intended policy.

## 8. Why Separate Authorization Tests from CSRF Tests?

Consider `POST /api/orders` restricted to MEMBER. There are four key combinations (plus anonymous cases):

| Caller | CSRF token | Expected | Reason |
| --- | --- | --- | --- |
| MEMBER | Valid | **201** | Passes both CSRF and MEMBER rule |
| MEMBER | Missing | **403** | `CsrfFilter` blocks, even with right role |
| MEMBER | Invalid | **403** | CSRF validation fails |
| ADMIN | Valid | **403** | Lacks `ROLE_MEMBER` in demo |
| ANON | Valid | **401** | Unauthenticated per HTTP Basic |
| ANON | Missing | Usually **403** before auth | Missing CSRF; do not use to infer role decision |

If you only write:

~~~java
mvc.perform(post("/api/orders")
        .with(httpBasic("admin", "admin-pass")))
    .andExpect(status().isForbidden());
~~~

then **the test does not prove ADMIN was rejected for lacking `ROLE_MEMBER`**. With CSRF enabled, a request without CSRF also gets 403. The right test for the role question must add `.with(csrf())`:

~~~java
mvc.perform(post("/api/orders")
        .with(httpBasic("admin", "admin-pass"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

And add a separate test:

~~~java
mvc.perform(post("/api/orders")
        .with(httpBasic("member", "member-pass")))
    .andExpect(status().isForbidden());
~~~

These snippets are **MockMvc test fragments**; full imports and setup are given in section 7. Isolating the variables "authenticated", "has role", and "valid CSRF" is essential for a meaningful matrix.

**CSRF depends on threat model context:** cookie/session apps easily have credentials auto-sent by browsers; Spring Security enables CSRF by default in Servlet. An API using only bearer tokens placed in the `Authorization` header may use a different design, yet never disable CSRF merely because an endpoint returns JSON or uses `permitAll()`. Base the decision on how clients authenticate, browser behavior, and cross-site submission vectors.

## 9. Anonymous, Wrong Role, Disabled Account, and Expired Session

### 9.1. Anonymous Is Not the Same as a Principal with Empty Roles

Spring Security can place an anonymous authentication in `SecurityContext` so principal-reading code behaves uniformly; however, `authenticated()` does not consider anonymous callers authenticated under Spring Security authorization rules. Hence a request lacking Basic credentials on a protected endpoint usually receives **401**.

An **authenticated user with empty roles** differs from anonymous: `authenticated()` may permit access to `/api/me`, whereas `hasRole("ADMIN")` denies with 403. When using `@WithMockUser(roles = {})`, understand you are creating an **authenticated principal with no roles**, not an anonymous caller.

### 9.2. Wrong Credentials

`httpBasic("member","wrong-pass")` checks the password via filter/provider and gets **401** when no other authentication succeeds. If a test also uses `@WithMockUser`, the mock principal can mask bad Basic credentials or create an unintended context; avoid mixing both mechanisms in the same test when asserting authentication failure.

### 9.3. Disabled or Locked Users

When an app checks `UserDetails.isEnabled()`, `isAccountNonLocked()`, an external IdP, or local status, add a row:

~~~text
GET /api/me | disabled account | 401 or failure per designed entry point
~~~

Do not assume every disabled account returns 403. Many providers reject directly at **authentication** and invoke `AuthenticationEntryPoint` to return 401/redirect. For existing sessions, changing account status in the database does not necessarily purge `SecurityContext` automatically; high-risk products need session revocation or periodic account-status checks.

### 9.4. Expired Sessions and Role Changes

With HTTP Basic in the demo, credentials are sent on every request; there is no browser-style "login session" to test in this matrix. When switching to session-based authentication, add states: no cookie, valid cookie, expired cookie, logout, session fixation protection, and stale cookie after privilege revocation.

Roles/permissions in `SecurityContext` can be a snapshot captured at login time; changing roles in the DB does not automatically update existing sessions immediately. Test according to business requirements and revocation policies.

## 10. A URL Matrix Does Not Replace Object-Level Authorization

A single GET endpoint permitted to MEMBER and ADMIN **does not guarantee** a user may read every order:

~~~text
GET /api/orders/42
  -> SecurityFilterChain:
       hasAnyRole("MEMBER", "ADMIN")
  -> OrderService:
       findById(42)
       check owner/tenant/status/ACL
       deny if not authorized for this exact order
~~~

The demo code has no database and skips the owner check; **do not carry this as-is to real data**. Once persistence is added, test at least:

| Identity | Object | Expected |
| --- | --- | --- |
| MEMBER Alice | Alice's order | 200 |
| MEMBER Alice | Bob's order in same tenant | 403 or 404 per policy |
| MEMBER Alice | Another tenant's order | 403 or 404, no metadata leaked |
| ADMIN | Valid order in assigned tenant | Per admin rules |
| ADMIN | Order outside tenant/admin scope | Denied if lacking global permission |
| Anonymous | Any private order | 401/redirect per entry point |

**URL roles** and **object-level authorization** must go together. If using `@PreAuthorize`, `PermissionEvaluator`, or a policy service like `orderAccess.canRead(authentication, orderId)`, test both calls through the Spring-managed proxy and HTTP requests through the controller. `@PreAuthorize` will not run if `@EnableMethodSecurity` is missing or if `new Service()` is invoked outside a proxy.

When reading data from request bodies, **never let clients supply owner/tenant and treat it as verified**. Extract identity from the trusted `Authentication` and compare against server-side metadata. Role tests without per-object permission checks can miss IDOR/BOLA vulnerabilities.

## 11. HEAD, OPTIONS, CORS Preflight, and Less Common Methods

### 11.1. HEAD

A `@GetMapping` handler in Spring MVC can support `HEAD` via framework mechanics. Nevertheless, **a Spring Security `HttpMethod.GET` rule is not automatically a `HEAD` rule**. If `HEAD /api/orders/42` needs the same read permission as GET, define an explicit policy and add a HEAD row to the matrix, asserting status and empty body. Never assume that protecting GET guarantees HEAD is protected properly.

### 11.2. OPTIONS and CORS Preflight

Browsers may send a preflight `OPTIONS` request with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` before a cross-origin request. Preflights usually **carry no login credentials**; when CORS is enabled, Spring must process CORS **before the authentication decision**, or else preflights get rejected even when the actual request is valid.

Preflight test example (only a **MockMvc fragment requiring matching CORS configuration**, not present in section 6's minimal app):

~~~java
mvc.perform(options("/api/orders")
        .header("Origin", "https://frontend.example.org")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
                "authorization,content-type"))
    .andExpect(status().isOk());
~~~

Do not add this 200 expectation to the current demo app because **the demo has not defined CORS**. Only when `http.cors(Customizer.withDefaults())` and a `CorsConfigurationSource` bean allow the origin/method/headers will preflights behave as designed. A valid preflight **does not** prove the actual `POST /api/orders` will pass roles, CSRF, or business validation. Conversely, `permitAll(HttpMethod.OPTIONS, "/**")` alone does not generate `Access-Control-Allow-*` headers and does not replace CORS configuration.

### 11.3. TRACE and Other Methods

`TRACE` may be disabled by the container/gateway before reaching Spring MVC; never assume a specific app status arbitrarily. When a method is unsupported, identify which layer rejects it (proxy, servlet container, Spring Security, Spring MVC) and check the appropriate response/headers. A default-deny policy helps avoid accidentally exposing new methods.

### 11.4. Extending Matchers for Servlet Path and Proxies

If an app uses `server.servlet.context-path`, multiple `DispatcherServlet` instances, multiple filter chains, or reverse-proxy path rewrites, test the URL Security actually receives. `requestMatchers` on Spring Security + MVC has path-matching semantics tied to servlet and matcher setup; never blindly prepend context paths to patterns or assume browser URLs match internal request paths. With multiple servlets, an explicit `MvcRequestMatcher.Builder` and servlet path may be required.

## 12. Organizing Matrices at System Scale

With hundreds of endpoints, maintaining a giant hand-written list of tests becomes cumbersome. An effective strategy:

1. **A single source of truth for the contract:** record path template, method, authentication requirement, roles/permissions, owner/tenant rule, CSRF/CORS requirements, and expected status.
2. **Group endpoints by policy:** public GET, user profile, member write, admin-only, cross-tenant, file download, webhooks, callbacks.
3. **Generate strongly typed tests:** like `Rule`/`Scenario` in section 7, so every policy row runs against standard identities. Avoid a helper that hides all request details.
4. **Cover negative cases:** anonymous, wrong role, empty roles, wrong tenant, revoked user, invalid/expired credentials, missing/invalid CSRF, undeclared methods.
5. **Check actual handler outcomes:** response body/headers and state/DB changes; checking status 200 alone can miss returning another user's data.
6. **Use integration tests where needed:** `WebTestClient` for WebFlux (different stack), `MockMvc` for Servlet MVC; for real cookies/redirects/filter dispatches/proxies/TLS, use an embedded server and HTTP client.
7. **Run tests in CI and review policy diffs:** changes to security matchers, role hierarchies, handler mappings, or HTTP methods should trigger corresponding test updates/reviews.

Matrices can live in Markdown, YAML, CSV, or Java code. If reading data externally, validate parsed values (method, role, status) and ensure untrusted content cannot inject code or open permissions. **You do not need every meaningless Cartesian combination**, yet every **distinct security risk** needs clear coverage, especially negative tests.

### 12.1. Defining Meaningful Coverage

Useful metrics:

| Scope | Verification question |
| --- | --- |
| Every public endpoint | Is anonymous allowed only on the intended methods? |
| Every protected endpoint | Is anonymous denied via the right entry point? |
| Every role rule | Are authorized roles allowed and wrong roles denied? |
| Every unsafe method | Is missing/invalid CSRF blocked where CSRF applies? |
| Every path template | Tested with valid IDs, malformed IDs, URL encoding, and alternate templates? |
| Every object ACL | Same-tenant vs cross-tenant, owner vs non-owner tested? |
| Every authentication type | Basic vs session vs bearer vs OIDC tested via its own flow? |
| Every internal dispatch | FORWARD/ERROR/ASYNC policies covered if used by the app? |
| Every API change | Does adding a new method trigger a default-deny test check? |

Counting tests alone is not enough: 100 happy-path tests still miss an accidental `permitAll()` on DELETE or a download path lacking ownership checks.

## 13. Common Mistakes When Matrix-Testing Endpoints

**Mistake 1 — Testing only URL without method.** `GET /api/orders/42` works for a role while `DELETE /api/orders/42` has a different rule. The matrix must include a method column.

**Mistake 2 — Testing wrong role on POST without adding CSRF.** 403 may come from `CsrfFilter`, so the test "passes" even when authorization is broken. To test roles, supply `with(csrf())`; test missing/invalid CSRF separately.

**Mistake 3 — Using only an admin account.** If every test uses high privileges, you never know whether MEMBER is allowed/denied properly. Test at least anonymous + low role + high role, plus empty roles where relevant.

**Mistake 4 — Assuming ADMIN always implies MEMBER.** In Spring Security, `ROLE_ADMIN` does not automatically add `ROLE_MEMBER`. Use `hasAnyRole` or a tested role hierarchy if policy calls for it.

**Mistake 5 — Using `@WithMockUser` to prove passwords work.** The annotation pre-populates authentication. When testing real authentication, pass credentials through filters/providers (`httpBasic`, form login, tokens) and test failure paths.

**Mistake 6 — Treating HTTP 200 as proof no data leaked.** URL-level roles are not enough; controllers/services may still return someone else's order. Add object-level ACL tests and verify response body/state.

**Mistake 7 — Putting a broad matcher first.** `/api/**.authenticated()` before member/admin rules prevents specific rules from ever being reached. Negative role tests catch this bug.

**Mistake 8 — Permitting all HTTP methods because a matcher omitted method.** `requestMatchers("/api/orders/**").permitAll()` can affect GET/PUT/DELETE. Specify `HttpMethod` whenever permissions differ by operation.

**Mistake 9 — Testing a nonexistent route and expecting 404 everywhere.** `denyAll()` can reject at Security before MVC ever returns 404/405. Understand which layer produces the response.

**Mistake 10 — Mixing session and Basic in one test without knowing which auth source ran.** A pre-populated `SecurityContext` can mask bad Basic credentials. Isolate each identity source and use fresh requests when needed.

**Mistake 11 — Ignoring HEAD/OPTIONS.** MVC can serve HEAD from GET, and browsers send OPTIONS for preflight; security matchers and CORS need dedicated tests when APIs use them.

**Mistake 12 — Disabling CSRF everywhere to make tests green.** CSRF is an independent control, especially with cookie-backed browser sessions. Tests must reflect the threat model rather than removing protection because fixtures lacked tokens.

**Mistake 13 — Static assets or `/error` accidentally hit by `denyAll`.** If an app has real login/static/error pages, list public routes explicitly and test those routes/dispatches; the minimal example only includes `/public/ping`.

**Mistake 14 — Confusing `hasRole` and `hasAuthority`.** `hasRole("MEMBER")` typically checks `ROLE_MEMBER`, while `hasAuthority("MEMBER")` requires literal `MEMBER`. Stay consistent across test principals and `SecurityFilterChain`.

**Mistake 15 — Skipping method security checks.** Controllers may have URL protection while services called by jobs/message listeners bypass web filters. For sensitive operations, test the service boundary and `@PreAuthorize` separately.

**Mistake 16 — Letting mock tests completely replace real deployment tests.** MockMvc does not verify proxy routing, HTTPS, session cookies, OAuth2 callbacks, or real browser CORS behavior. Add integration tests at the proper tier.

## 14. Practice Exercises

**Exercise 1.** Given `GET /api/orders/* -> hasAnyRole(MEMBER, ADMIN)` and `DELETE /api/orders/* -> hasRole(ADMIN)`, what statuses do anonymous, MEMBER, and ADMIN get when all other conditions are met?  
**Answer:** GET: 401/200/200. DELETE (with valid CSRF): 401/403/204 in the demo.

**Exercise 2.** Member calls `POST /api/orders` without a CSRF token and gets 403. Can you conclude member lacks POST permission?  
**No.** You must test with a valid CSRF token to separate authorization from CSRF.

**Exercise 3.** Can a user holding only `ROLE_ADMIN` enter a `hasRole("MEMBER")` route?  
**Not by default.** Only if the user holds `ROLE_MEMBER` or the system defines a role hierarchy/other authorization rule.

**Exercise 4.** Why is `POST /admin/metrics` denied even though `GET /admin/metrics` allows ADMIN?  
**Because** the rule matches only `HttpMethod.GET`; POST is undeclared and falls into deny-all.

**Exercise 5.** Does `with(user("alice").roles("MEMBER"))` verify Alice's password?  
**No.** It is a request post-processor creating an authenticated user. Only `httpBasic("alice", "password")` sends credentials through the Basic filter to validate them.

**Exercise 6.** HTTP Basic anonymous on a protected route returns 401, while a form-login app with the same rule redirects 302 to login. Which test is wrong?  
**Neither is necessarily wrong.** Different entry points yield different responses; align the matrix with the application's authentication mechanism.

**Exercise 7.** With the same `MEMBER` role, Alice accesses Bob's order. The role-based URL matrix passes; what is still missing?  
**Object-level authorization:** check owner/tenant/ACL from server-side data and add negative rejection tests.

**Exercise 8.** A browser sends a cookie-less CORS preflight OPTIONS; the POST endpoint requires `hasRole("MEMBER")`. Should preflight require MEMBER?  
**No.** CORS preflight must be processed before authentication when CORS is enabled; the actual POST still enforces authentication, authorization, and CSRF if applicable.

**Exercise 9.** A `@WithMockUser(roles = {})` test gets 200 on `/api/me`. Was an anonymous user just allowed?  
**No.** The mock principal is still authenticated despite having no roles; `authenticated()` differs from `hasRole`.

**Exercise 10.** Why does a DELETE test returning 204 not prove real data was deleted?  
**Because** the demo handler only returns a status with no persistence. Verify business state/transactions and authorization side effects in integration tests.

## 15. Checklist for Implementing a Reliable Endpoint Matrix

- **Inventory** real methods and paths of every API; pay attention to same URL with different permissions across GET/POST/PATCH/PUT/DELETE.
- **Define principal states**: anonymous, low/high authenticated roles, wrong credentials, no roles, and disabled/revoked/expired sessions where relevant.
- **Model policies**: `permitAll`, `authenticated`, role/authority, ownership/tenant, and default deny. Place specific matchers before broad matchers.
- **Specify response contracts**: 200/201/204 success; 401/302 unauthenticated per entry point; 403 insufficient permission/CSRF; 404/405 per rejection layer.
- **Isolate test variables**: supply valid CSRF when measuring roles on unsafe methods; test missing/invalid CSRF separately; never use 403 as missing-role evidence if CSRF was also missing.
- **Run data-driven tests**: at least anonymous + relevant roles per endpoint, asserting response/body/state rather than status alone.
- **Test negative methods**: undeclared methods, new URLs, path encoding, HEAD/OPTIONS, preflight when CORS is enabled; never widen public endpoints casually.
- **Check object permissions**: owner, tenant, resource status, data filtering, and service-level method security.
- **Isolate auth tests**: `httpBasic`/form login/bearer tests verify real authentication; `@WithMockUser` or `with(user())` serve policy-only tests.
- **Run in CI** and maintain the matrix whenever adding endpoints, changing roles, or splitting security filter chains; add container/proxy/session integration tests as needed.

**Conclusion:** Secure HTTP testing is more than checking one URL with one sufficiently privileged account. An **endpoint × HTTP method × login state × role × CSRF** matrix clearly exposes **who can do what under which conditions**, catching missing rules, misordered matchers, and authorization gaps. For real data, extend the matrix to **per-object ownership**, rather than relying solely on URL paths.
