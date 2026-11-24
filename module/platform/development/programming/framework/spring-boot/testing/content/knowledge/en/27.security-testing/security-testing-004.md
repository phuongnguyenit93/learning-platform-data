# CSRF Tokens and Distinguishing CSRF Errors from Authorization Errors in Spring Boot

In Spring Boot using **Spring Security**, two HTTP requests returning **403 Forbidden** may fail due to **two completely different mechanisms**:

- **CSRF** (*Cross-Site Request Forgery*): the request requires protection yet is **missing a token or sends an invalid token**, so `CsrfFilter` rejects it **before** it reaches the controller or has its access permissions evaluated.
- **Authorization**: the request passed the CSRF check, yet the active identity **lacks sufficient authority/role** to call the endpoint, so `AuthorizationFilter` or method security denies it.

Therefore, concluding “POST returned 403 so the user lacks the ADMIN role” is usually **unsupported**. Even a request from an ADMIN missing a CSRF token can receive 403. Conversely, a user with role USER sending a valid token can still receive 403 when the endpoint requires ADMIN.

This lesson belongs to the **Security** section of **Spring Boot - testing**. It covers CSRF mechanics with sessions/cookies, reading HTTP 401/403/302 by configuration, verifying filter layers, testing strategies with `MockMvc` and `spring-security-test`, missing/invalid/valid tokens, USER/ADMIN roles, GET/POST/PUT/DELETE methods, configurations for Bearer/SPA APIs, real-world error diagnosis, and a runnable **Java 17 + Spring Boot 3.5 + Spring Security 6.5 + JUnit Jupiter** Maven project.

> **Principle:** looking only at **HTTP status=403** is not enough to identify the root cause. Use a control request with a **valid token**, inspect authentication/authorities, and check **which exception/filter rejected the request** in a safe diagnostic environment.

## 1. CSRF is not authorization

### 1.1. Why are browsers vulnerable to CSRF?

Suppose a user is logged into `https://bank.example` via a **session cookie**. When they visit another malicious website, the browser can automatically send a request to the bank and **attach credentials via automatic browser behavior**, depending on SameSite/cookie/CORS/browser context. If the bank relies solely on the cookie to identify the user without protecting state-changing actions, the external site can **trigger unintended actions**.

```text
Victim browser
   |  (holding bank session cookie)
   |
   +--- attacker page triggers form POST /transfer
   |
   +--- browser sends bank cookie per cookie policy
   |
   v
Bank server
   |-- Authentication: valid cookie/session -> user is logged in
   |-- Authorization: user is permitted to transfer from own account
   |-- CSRF validation: missing/wrong anti-CSRF token -> BLOCKED
```

**CSRF protection** defends against a channel that **abuses automatically sent credentials**. It does not replace checking who may act on which object, transaction limits, ownership checks, or anti-fraud rules.

A CSRF token is typically an **unpredictable value** bound to a session or specific state mechanism. A legitimate client supplies the token in a hidden form field or header, while a cross-origin page cannot arbitrarily read that token when the application and browser security are configured properly. Spring Security compares the token from the request against the stored token.

**Never use a CSRF token as an access token**: a CSRF token does not prove identity, grant roles, or replace sessions/JWTs/permissions. Having a valid token without the ADMIN role must still result in 403 on administrative actions.

### 1.2. How does authorization differ from CSRF?

| Criterion | CSRF | Authentication | Authorization |
|---|---|---|---|
| Question | Did this state-changing request genuinely originate from a valid flow holding the token? | Who is calling? | What is that caller allowed to do? |
| Relies on | Token/cookie/session/repository/handler | Session, Basic, Bearer, form login... | Roles, authorities, ownership, policy |
| Typical component | `CsrfFilter` | Authentication filters / manager | `AuthorizationFilter`, `@PreAuthorize` |
| Request missing requirement | Usually **403** if CSRF is required | May be **401** or **302 login**, depending on entry point | Authenticated user lacking permission usually gets **403** |
| Fix | Send the right token, keep session/cookie in sync | Log in or provide valid credentials | Grant proper permissions / fix business rules, never fake roles |
| Never do | Disable all CSRF to fix tests | Hardcode fake users in production | Grant broad roles just to clear 403s in tests |

**401 is not guaranteed for every unauthenticated request**: with form login, Spring Security may **302 Redirect** to the login page; with Basic/Bearer, it is usually 401. For a POST **without a token**, `CsrfFilter` may reject with 403 **before** the authentication entry point decides 401/302.

## 2. How does the CSRF filter process requests?

Spring Security Servlet uses `CsrfFilter` together with `CsrfTokenRepository` and `CsrfTokenRequestHandler`.

```text
HTTP request
   |
   v
SecurityFilterChain
   |
   v
CsrfFilter
   |
   +-- Does HTTP method need CSRF protection?
   |      |-- No (GET, HEAD, OPTIONS, TRACE by default)
   |      |          |
   |      |          +--> continue filter chain
   |      |
   |      +-- Yes (POST, PUT, PATCH, DELETE ... by default)
   |                 |
   |                 v
   |       Load expected token from repository
   |                 |
   |       Resolve submitted token from request
   |                 |
   |       Compare tokens?
   |         |-- Missing/wrong -> CsrfException
   |         |                      -> AccessDeniedHandler
   |         |                      -> 403
   |         |
   |         +-- Valid -> continue filter chain
   |
   v
Authentication / Authorization
   |
   +-- Not logged in -> AuthenticationEntryPoint -> 401/302 per config
   |
   +-- Authenticated but missing role/authority -> AccessDeniedException -> 403
   |
   +-- Authorized -> Controller / business service
```

### 2.1. Which HTTP methods require a token by default?

Spring Security Servlet **skips CSRF for GET, HEAD, TRACE, and OPTIONS** by default and checks all other methods; in REST applications these are typically POST, PUT, PATCH, and DELETE.

| Method | Requires CSRF by default? | Reason |
|---|---|---|
| `GET /api/admin/summary` | No | GET should be a safe/read-only operation |
| `HEAD /api/admin/summary` | No | Safe HTTP method |
| `OPTIONS /api/admin/tasks` | No | Usually preflight-related; authorization/CORS remain separate |
| `POST /api/admin/tasks` | **Yes** | Creates data |
| `PUT /api/admin/tasks/1` | **Yes** | Updates |
| `PATCH /api/admin/tasks/1` | **Yes** | Partial update |
| `DELETE /api/admin/tasks/1` | **Yes** | Deletes |
| `GET /api/delete?id=1` | No by default | **Broken design** if GET actually mutates state |

**Do not rely on “GET needs no CSRF” to let GET cause side effects.** HTTP method semantics are an essential part of security design. If an application has custom matchers, behavior can differ from the default table; tests must follow the actual `SecurityFilterChain`.

### 2.2. Where does the token live?

For HTML forms, the token may reside in a hidden input named `_csrf`; for JavaScript clients, it is commonly sent in the `X-CSRF-TOKEN` or `X-XSRF-TOKEN` header depending on the handler/repository mechanism.

```http
POST /api/admin/tasks HTTP/1.1
Cookie: JSESSIONID=session-example
X-CSRF-TOKEN: csrf-token-example
Content-Type: application/json

{"name":"create-report"}
```

This is an **illustrative HTTP request**, not a real token, and cannot be copied and run unless the token matches a server session. **The session cookie and token must belong to the same security context**; if the session times out or rotates, the old token can become invalid.

### 2.3. Two important CSRF exceptions

Spring Security provides:

- `org.springframework.security.web.csrf.CsrfException`: the base class for CSRF errors, a subclass of `AccessDeniedException`.
- `MissingCsrfTokenException`: cases where the expected token cannot be found in the repository.
- `InvalidCsrfTokenException`: the expected token does not match the client-supplied token.

**Do not assert “missing header is always `MissingCsrfTokenException`”**: Spring Security may have already generated/saved an expected token, so when a client omits the token, the actual exception is `InvalidCsrfTokenException`. When classifying causes, checking `instanceof CsrfException` is more reliable than inferring from messages or a specific subtype.

For authorization failures, you may see `AccessDeniedException` or a type such as `AuthorizationDeniedException` (depending on Spring Security version/path). Because `CsrfException` is also an `AccessDeniedException`, any code like `if (ex instanceof AccessDeniedException) { authorization }` will **misclassify CSRF**. Check `CsrfException` **first**, then classify remaining `AccessDeniedException` instances under authorization/access policy.

## 3. 403 is a symptom, not a root cause

| Case | Authentication | CSRF | Authority | Typical outcome |
|---|---|---|---|---|
| GET public | Anonymous | Not required | Public | **200** |
| GET admin | Anonymous | Not required | Missing authentication | **401** (in demo config) |
| GET admin | USER | Not required | Missing ADMIN | **403 authorization** |
| GET admin | ADMIN | Not required | Has ADMIN | **200** |
| POST admin | Anonymous | **Missing** | Role not yet evaluated | **403 CSRF** |
| POST admin | USER | **Missing** | Role not yet evaluated | **403 CSRF** |
| POST admin | USER | **Invalid token** | Role not yet evaluated | **403 CSRF** |
| POST admin | USER | **Valid token** | Missing ADMIN | **403 authorization** |
| POST admin | ADMIN | **Missing token** | Role not yet evaluated | **403 CSRF** |
| POST admin | ADMIN | **Valid token** | Has ADMIN | **201** |
| POST admin | Anonymous | **Valid token** | No authentication | **401** (in demo config) |

The **401** statuses above come from the example's `AuthenticationEntryPoint` intentionally returning 401. A website using form login may redirect with 302. In an app with multiple filter chains, rule matching also affects the outcome. **Never diagnose by status code alone**, even when both are 403.

### Control test to distinguish the two 403s

To find out why a USER POST to admin returns 403:

1. Send POST as USER **without** CSRF -> 403. This shows CSRF *could* be blocking it, without proving authorization.
2. Send the **same POST** as USER with a **valid token** -> still 403. CSRF passed, so the cause now lies in **role/authorization or another policy**.
3. Send the same POST as ADMIN with a valid token -> 201. This proves the endpoint and test token are valid and the role rule is active.
4. Send POST as ADMIN **omitting the token** -> 403. This proves the **ADMIN role does not bypass CSRF**.

Never “fix” a 403 in an authorization test by **disabling CSRF application-wide**. Supply a valid token on the request to **isolate the authorization layer**, then test permissions independently.

## 4. Spring Security 6.5 and CSRF token repositories

By default, Spring Security uses `HttpSessionCsrfTokenRepository` to store tokens in the session, with deferred loading and a request attribute handler. Exact behavior depends on your configuration:

- **Server-rendered forms**: templates can read the token from request attributes or via form tag helpers.
- **REST AJAX using session cookies**: JavaScript must obtain the token securely and send the header on state-changing requests.
- **`CookieCsrfTokenRepository`**: the server can store the CSRF token in the `XSRF-TOKEN` cookie, which browser frontend code reads when permitted and returns as `X-XSRF-TOKEN`. Only use `withHttpOnlyFalse()` if JavaScript genuinely needs to read the cookie and the tradeoff is accepted, not out of habit for every cookie.
- **Spring Security 6.x XOR/BREACH protection**: `XorCsrfTokenRequestAttributeHandler` masks the token when rendering. The raw token in the cookie does not automatically share the same representation as a masked token. For SPAs, configure the request handler per the official guide instead of merely adding a cookie repository and expecting every header to work.
- **Login/logout/session rotation**: Spring Security may clear/rotate the old CSRF token after authentication or logout success; SPAs need to **fetch a fresh token** before the next POST.
- **Session timeout**: a token tied to an expired session becomes invalid. A 403 here does not mean a role was revoked.

A common mistake: the frontend receives the `XSRF-TOKEN` cookie yet forgets to send the `X-XSRF-TOKEN` header, sends a token from **another session**, or the browser omits the cookie due to `SameSite`/domain/path/Secure/credentials policy. The symptom is typically 403 on POST even though GET succeeds.

### CORS and SameSite do not replace CSRF

- **CORS** controls whether JavaScript from another origin may read responses or issue certain cross-origin requests; it **does not prevent all CSRF**. An HTML form can submit a request without reading the response.
- **SameSite** cookies are a mitigation layer, but should not replace full CSRF design for apps relying on automatic credentials.
- **Authorization** answers who may do what; **CSRF** answers whether a state-changing request carries sufficient anti-cross-site-forgery proof.

CSRF tokens are not an invariable rule for every API: base the decision on **client types and credential mechanisms**, not merely HTTP status codes or JSON format.

## 5. Runnable Java 17 / Spring Boot 3.5 example: distinguishing 403 causes with MockMvc

We create a minimal Spring MVC application:

- `GET /api/public/ping`: no login required.
- `GET /api/admin/summary`: requires role ADMIN, **no CSRF required**.
- `POST /api/admin/tasks`: requires role ADMIN **and** a CSRF token.
- `PUT /api/admin/tasks/7`, `DELETE /api/admin/tasks/7`: also unsafe methods.
- Tests use `.with(user("...").roles(...))` to simulate authentication **per request**; no real login API is invoked.
- Tests use `.with(csrf())`, `.with(csrf().asHeader())`, and `.with(csrf().useInvalidToken())` from `spring-security-test` to verify tokens.
- The demo config adds a **diagnostic header `X-Demo-Denial`** distinguishing `CsrfException` from other denials. This header is **strictly for learning/testing**; **never expose security policy internals in production responses**. Production should log category/correlation ID internally and return a uniform 403 body.

The example uses `@SpringBootTest(webEnvironment=MOCK)` with `@AutoConfigureMockMvc`, loading the **demo app's real `SecurityFilterChain`** into MockMvc. No external network server, Docker, or database is needed.

### 5.1. Directory tree

```text
csrf-authorization-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── DemoSecurityConfig.java
    │   └── DemoAdminController.java
    └── test/java/com/example/csrf/
        └── CsrfAuthorizationTest.java
```

### 5.2. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>csrf-authorization-demo</artifactId>
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

**Why separate dependencies?** `spring-boot-starter-security` provides the filter chain and authorization, while **`spring-security-test`** provides `csrf()`, `user()`, `@WithMockUser`, and MockMvc support. Without this specialized test dependency, static imports like `SecurityMockMvcRequestPostProcessors.csrf` will not compile. The Boot parent manages compatible versions; do not randomly pin Spring Security 7 with Boot 3.5.

### 5.3. Application

File **`src/main/java/com/example/csrf/CsrfDemoApplication.java`**:

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
```

The application includes the embedded servlet stack and scans controllers/configs under the same package. JUnit tests initialize MockMvc through the Spring test context without opening a real TCP port.

### 5.4. Real SecurityFilterChain for the demo

File **`src/main/java/com/example/csrf/DemoSecurityConfig.java`**:

```java
package com.example.csrf;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfException;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class DemoSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // Keep CSRF enabled per Spring Security default.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                // Fix 401 for anonymous in this example.
                // Form login in other apps may redirect 302.
                .authenticationEntryPoint((request, response, cause) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED))
                .accessDeniedHandler((request, response, denied) -> {
                    // Header ONLY FOR DIAGNOSTICS IN DEMO/TEST.
                    // Never expose failure sub-categories in prod.
                    String category = denied instanceof CsrfException
                            ? "csrf" : "authorization";
                    response.setHeader("X-Demo-Denial", category);
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN);
                }));

        return http.build();
    }
}
```

**Why does the handler distinguish both types accurately?** Spring Security 6.5's `CsrfConfigurer` picks up the `AccessDeniedHandler` configured via `ExceptionHandlingConfigurer` for `CsrfFilter`; authorization failures pass through `ExceptionTranslationFilter` with the same handler. Here we check `denied instanceof CsrfException` **first**, then classify other denials. The handler **does not alter permissions**; it only reports status.

**Never ship the `X-Demo-Denial` header from this example into production as a habit**: public responses can leak control internals. In real systems, record logs/metrics **server-side** by category/correlation ID and keep response messages neutral. The lesson uses the header purely for direct, easy-to-follow assertions.

**About roles:** `hasRole("ADMIN")` expects authority `ROLE_ADMIN`, not bare `ADMIN`. `user("...").roles("ADMIN")` in tests creates the prefixed authority. If your domain uses custom authorities, use `hasAuthority("...")` and simulate the corresponding token/claims.

**About authentication:** the lesson provides no login form/API. The `user()` helper places a mock authenticated principal into the security context to test roles rather than simulating real password/JWT verification. Production must configure an authentication mechanism suited to its requirements.

### 5.5. Public and administrative controller

File **`src/main/java/com/example/csrf/DemoAdminController.java`**:

```java
package com.example.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoAdminController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/admin/summary")
    public String adminSummary() {
        return "admin-summary";
    }

    @PostMapping("/admin/tasks")
    public ResponseEntity<String> createTask() {
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body("task-created");
    }

    @PutMapping("/admin/tasks/7")
    public String updateTask() {
        return "task-updated";
    }

    @DeleteMapping("/admin/tasks/7")
    public ResponseEntity<Void> deleteTask() {
        return ResponseEntity.noContent().build();
    }
}
```

The controller does not touch a database or perform real side effects. We intentionally isolate security filter behavior from JPA/service logic so a 403 error is not confused with a unique constraint or transaction rollback. The hardcoded `/7` path serves demonstration purposes only and is not production API design.

### 5.6. MockMvc integration tests: 14 independent cases

File **`src/test/java/com/example/csrf/CsrfAuthorizationTest.java`**:

```java
package com.example.csrf;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class CsrfAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicGetDoesNotNeedAuthenticationOrCsrf() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void anonymousAdminGetGets401NotCsrf403() throws Exception {
        mvc.perform(get("/api/admin/summary"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserAdminGetFailsAuthorization() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "authorization"));
    }

    @Test
    void adminGetSucceedsWithoutCsrf() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-summary"));
    }

    @Test
    void anonymousPostWithoutCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks"))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void ordinaryUserPostWithoutCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void ordinaryUserWithInvalidCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("alice").roles("USER"))
                .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void ordinaryUserWithValidCsrfStillGetsAuthorization403()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("alice").roles("USER"))
                .with(csrf()))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "authorization"));
    }

    @Test
    void adminPostWithValidCsrfParameterCreatesTask()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN"))
                .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("task-created"));
    }

    @Test
    void adminPostWithValidCsrfHeaderCreatesTask()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN"))
                .with(csrf().asHeader()))
                .andExpect(status().isCreated())
                .andExpect(content().string("task-created"));
    }

    @Test
    void adminPostWithoutCsrfStillGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void adminPostWithInvalidCsrfGetsCsrf403() throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(user("root").roles("ADMIN"))
                .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }

    @Test
    void anonymousWithValidCsrfStillNeedsAuthentication()
            throws Exception {
        mvc.perform(post("/api/admin/tasks")
                .with(csrf()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminPutWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(put("/api/admin/tasks/7")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        "X-Demo-Denial", "csrf"));
    }
}
```

**There are 14 independent `@Test` methods.** The tests cover anonymous, USER, and ADMIN; valid, missing, and invalid CSRF tokens; and GET, POST, and PUT methods. `DELETE` also requires CSRF by default, and a test similar to `PUT` can be added for the delete endpoint (DELETE is not needed to prove the current tests).

### 5.7. Interpreting the 14 test cases and outcomes

| Group | Case | What it proves |
|---|---|---|
| Safe method | GET public anonymous | No auth/CSRF needed on public endpoint |
| Authentication | GET admin anonymous | 401 from demo `AuthenticationEntryPoint`, not CSRF |
| Authorization | GET admin USER | 403 **authorization**, GET needs no token |
| Authorization pass | GET admin ADMIN | 200, role rule works |
| CSRF priority | POST anonymous no token | 403 **csrf** before authorization |
| CSRF priority | POST USER no token | 403 **csrf** even though user also lacks role |
| CSRF invalid | POST USER wrong token | 403 **csrf**, not conflated with role |
| Isolated authZ | POST USER valid token | 403 **authorization** after passing CSRF |
| Success | POST ADMIN token in parameter | 201 Created |
| Success | POST ADMIN token via header | 201 Created |
| Role does not replace CSRF | POST ADMIN no token | 403 **csrf** |
| Invalid CSRF as ADMIN | POST ADMIN wrong token | 403 **csrf** |
| Isolated authN | POST anonymous valid token | 401 per entry point config |
| Unsafe method | PUT ADMIN no token | 403 **csrf**, even with sufficient role |

**Do not assert status alone:** the lesson uses a diagnostic header derived from the exception class so tests identify the branch, while keeping **control tests with valid tokens**. When bringing this logic to production, drop the public header and replace it with **server-side** logs/metrics, keeping equivalent role/token tests.

**Do not treat `csrf()` as login simulation:** `csrf()` generates a valid request token in MockMvc security tests. It does not prove a real browser received a cookie/token and sent it back for the right session. `user()` creates a mock principal without checking passwords, SSO, or JWT parsing. Those flows require additional integration/end-to-end tests via an HTTP client or browser.

### 5.8. How to run

Requires **JDK 17+**, Maven, and no Docker:

```bash
mvn test
mvn -Dtest=CsrfAuthorizationTest test
```

If the project includes the Maven Wrapper, use `./mvnw test` or `mvnw.cmd test` on Windows. With the complete setup above, expect **Tests run: 14, Failures: 0, Errors: 0**. There is no fixed business stdout; Surefire/JUnit/Spring Boot may log context initialization.

The example is **code reviewed against Spring Boot 3.5 / Spring Security 6.5 APIs**, not a claim that Maven was executed while authoring this text. When applying in practice, run Maven on the project and verify behavior against your application's actual configuration and filters.

## 6. When is CSRF unnecessary or in need of API-specific configuration?

### 6.1. Browser session + cookies

For websites authenticated with session cookies, CSRF **should normally remain enabled** for unsafe methods. Browser POSTs attach cookies per cookie policy, making anti-CSRF tokens an important line of defense. Never remove CSRF globally just to fix tests missing `.with(csrf())`.

### 6.2. APIs using Bearer tokens in the Authorization header

An API serving solely non-browser clients, or a frontend sending Bearer tokens **explicitly placed in the `Authorization` header** **without using browser-auto-attached credentials**, has a different CSRF model. You may configure `csrf.disable()` for that specific chain/endpoint once threat modeling confirms CSRF is no longer a risk from ambient credentials.

**“Stateless” alone is not enough to automatically disable CSRF.** HTTP Basic credentials and certain cookie/authentication schemes can be sent automatically by browsers even if the backend creates no server session. If a Bearer token is stored **in a cookie** and sent automatically by the browser, CSRF risk remains relevant. Do not rely solely on `SessionCreationPolicy.STATELESS` or JSON responses to drop CSRF.

Example scoping CSRF off for a group of endpoints **genuinely free of browser credentials**:

```java
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/api/machine/**"));
```

This is only a snippet inside an `HttpSecurity` configuration, not a complete class. Only ignore paths that are threat-modeled and properly authenticated; **never wildcard `/api/**` carelessly** while browser sessions are shared. With multiple `SecurityFilterChain` beans, verify which chain matches first so you do not accidentally drop CSRF on session endpoints.

### 6.3. SPAs fetching tokens via cookies

Spring Security offers `CookieCsrfTokenRepository.withHttpOnlyFalse()` when JavaScript truly needs to read the token cookie. With Spring Security 6.x, configure a **request handler compatible with XOR/BREACH** and a **token refresh mechanism after login/logout**. Simply setting a cookie repository does not prove an SPA can submit valid tokens: the server-rendered token in the request attribute may be masked, the cookie holds the raw value, and the client must send the right header.

**SPA checklist:** proper `SameSite`/`Secure`/`HttpOnly` policy, accurate cookie domain/path, matching credentials mode and CORS, fetching a fresh token after authentication/logout, never logging tokens, session still active, and testing **two real requests** (fetch token then send unsafe request) using the same cookie jar.

## 7. Common pitfalls when distinguishing 401/403

| Symptom | Likely cause | How to verify |
|---|---|---|
| Public GET 200, authenticated POST 403 | Missing/invalid CSRF token | Send valid token in same session; check `CsrfException` |
| ADMIN POST 403 yet ADMIN GET 200 | CSRF applies to POST, skips GET | Add `csrf()` to POST while keeping same role |
| USER POST 403 even with CSRF | Missing authority or other access policy | Compare with ADMIN + valid token; inspect `AuthorizationFilter`/method security |
| USER GET admin 403 | Authorization, as GET needs no CSRF by default | Check `ROLE_ADMIN`/`hasRole("ADMIN")` |
| Anonymous GET admin 302 | Form login entry point | Do not treat 302 as CSRF; supply valid login/credentials |
| Anonymous POST admin 403 | CSRF filter may block before auth entry point | Check token; try anonymous + valid token as control |
| MockMvc request missing `csrf()` | Test setup omitted token, not a production bug | Add `.with(csrf())` when testing authorization on unsafe methods |
| `csrf().useInvalidToken()` returns 403 | Proper CSRF enforcement | Assert CSRF branch; do not conclude missing role |
| API sent cookie yet still gets 403 | Missing CSRF header or wrong cookie/session | Inspect cookie jar/header, session rotation, masked/raw token |
| First POST after login/logout gets 403 | Old CSRF token cleared/rotated, SPA did not refresh | Fetch fresh token after authentication/logout |
| PUT/PATCH/DELETE 403, GET 200 | Unsafe HTTP methods require CSRF | Test tokens for each method |
| HTTP 401 from JWT API | Unauthenticated, expired token/bad signature | Check authentication entry point/JWT; do not call it CSRF |
| HTTP 403 from JWT API | Missing scope/role, or CSRF if enabled on chain | Inspect security chain and exception root cause |
| CORS preflight fails | Cross-origin browser policy/filter order | Inspect OPTIONS/CORS config; do not guess “disable CSRF” |
| JSON POST gets 403 | CSRF does not apply only to form encoding | Check session/cookie/CSRF policy; content type does not disable CSRF |
| Client gets 403 after session timeout | Expected token no longer belongs to session | Reauthenticate/refresh token and retry safely |
| Controller/`@PreAuthorize` 403 | Method security denial | Send valid CSRF then inspect method authorization |
| Test uses `roles("ADMIN")` yet config checks `hasAuthority("ADMIN")` | Role creates `ROLE_ADMIN`, mismatching `ADMIN` | Align role/authority conventions |
| Calling `csrf.disable()` so all tests pass | Hides vulnerability for browser sessions | Keep CSRF, fix test tokens and scope config properly |

### 7.1. Diagnostic workflow for a real 403

1. **Inspect method and URL**: GET or POST/PUT/PATCH/DELETE? Does the path belong to the expected `SecurityFilterChain`?
2. **Check authentication**: is the session valid, and which principal/roles/authorities exist in `SecurityContext`? Never log raw credentials or tokens.
3. **Check CSRF**: was the token sent in the expected header/parameter, matching the session/cookie, and not rotated/expired?
4. **Run a control request**: same principal, same endpoint, adding a **valid token**. If it shifts from a CSRF 403 to an authorization 403, both conditions fail, just in a different order.
5. **Inspect denial exception**: is there a `CsrfException`, `InvalidCsrfTokenException`, or `MissingCsrfTokenException`? Otherwise inspect authorization rules, method security, and resource ownership.
6. **Inspect logs/filter chain safely**: enable Spring Security DEBUG/TRACE in test environments without logging sensitive headers/tokens in production.
7. **Lock it down with regression tests**: add both negative token tests and positive token + role tests; never stop at a single `isForbidden()` assertion.

### 7.2. Notes on inspecting logs

You can enable test logging:

```properties
logging.level.org.springframework.security=DEBUG
```

In diagnostic environments you may selectively raise specific loggers to TRACE, while guarding against logging sensitive data. Log **correlation IDs, sanitized request method/path, pseudonymized user IDs, error categories, security rule names, or filter names** — never write raw session cookies, Bearer tokens, CSRF tokens, or PII into CI artifacts.

If you install a custom `AccessDeniedHandler`, classify **`CsrfException` before `AccessDeniedException`** as shown in the example. A 403 returned by a business handler does not necessarily originate from Spring Security; check response writers and controller advice outside the security chain as well.

## 8. Deeper testing with browsers, MockMvc, and WebFlux

### 8.1. MockMvc tests SecurityFilterChain, not a real browser

`MockMvc` + `spring-security-test` excels at **filter behavior**, request matchers, CSRF token validation, role checks, and controller mappings without TCP. However, `with(csrf())` and `user()` **inject test state directly**; they do not prove:

- A real HTML form renders the hidden token field.
- Browsers store cookies/sessions properly without leaking tokens cross-origin.
- An SPA reads cookies properly and sends headers after login/logout.
- An authentication provider verifies real passwords/SSO/JWT signatures.
- Reverse proxies/CORS/SameSite and HTTPS work as in production.

For session-based websites, add an **HTTP/browser roundtrip test**: perform a GET to acquire a session and CSRF token, keep the cookie jar, POST without a token -> 403; POST with token + session -> succeeds if role suffices; logout/login rotates the token, and retrying the old token fails. For OAuth2 APIs, test authentication/claims separately.

### 8.2. With WebFlux

Spring Security WebFlux uses `SecurityWebFilterChain`, `ServerHttpSecurity`, and `CsrfWebFilter`, rather than `HttpSecurity` Servlet filters. The matching test tool is `WebTestClient` with Spring Security reactive test configurers:

```java
webTestClient.mutateWith(
        SecurityMockServerConfigurers.mockUser("alice")
                .roles("ADMIN"))
        .mutateWith(SecurityMockServerConfigurers.csrf())
        .post()
        .uri("/api/admin/tasks")
        .exchange()
        .expectStatus().isCreated();
```

This is a **snippet**, not a standalone runnable file: it requires `WebTestClient`, `spring-security-test`, a WebFlux endpoint/config, and `import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers`. Do not copy Servlet `MockMvc.with(csrf())` directly into `WebTestClient`. The default reactive CSRF repository usually binds to `WebSession`, though cookie/token handler semantics must be checked per version.

### 8.3. Test slices vs full context

- **`@WebMvcTest`**: tests controllers and the Spring MVC slice; ensure the **real `SecurityFilterChain` or an intentionally imported config** is loaded. Replacing security with a non-representative mock/fake means passing tests do not prove real policy.
- **`@SpringBootTest` + `@AutoConfigureMockMvc`**: loads the real Spring Security config in the context, testing filters + controllers without opening TCP. This is the lesson's approach.
- **`@SpringBootTest(webEnvironment=RANDOM_PORT)`**: tests real HTTP sockets, cookie jars/sessions/redirects, and browser semantics when end-to-end verification is needed.
- **Unit testing method security**: tests `@PreAuthorize` or ownership policies with an appropriate security context, **not to be confused with CSRF**.

## 9. Self-check practice

Before checking the answers, predict the responses under the demo configuration (401 entry point, 403 denied):

| Request | Prediction |
|---|---|
| GET `/api/admin/summary` anonymous | **401** |
| GET `/api/admin/summary` USER | **403 authorization** |
| GET `/api/admin/summary` ADMIN | **200** |
| POST `/api/admin/tasks` ADMIN, missing CSRF | **403 csrf** |
| POST `/api/admin/tasks` USER, valid CSRF | **403 authorization** |
| POST `/api/admin/tasks` ADMIN, valid CSRF | **201** |
| POST `/api/admin/tasks` anonymous, valid CSRF | **401** |
| POST `/api/admin/tasks` USER, invalid CSRF | **403 csrf** |
| PUT `/api/admin/tasks/7` ADMIN, missing CSRF | **403 csrf** |

Explanation: unsafe requests pass through `CsrfFilter` first; only when the token is valid do they reach authentication/authorization. The ADMIN role does not prove a valid token. A valid token does not prove an authenticated principal. Safe GETs are not blocked by CSRF by default, yet remain subject to authorization.

### “Quick fixes” you must never apply

- **Disabling CSRF globally** just to make POST tests return 201.
- **Removing `hasRole`** so users stop receiving 403.
- **Making every test user ADMIN** to avoid writing denial cases.
- **Putting `csrf()` on every request**, including negative tests meant to prove missing tokens fail.
- **Catching every `AccessDeniedException` and logging “permission denied”** without separating `CsrfException`.
- **Seeing 401 in one system and assuming another also returns 401**, even when form login redirects with 302.
- **Logging CSRF tokens or copying/pasting them from tests into production**.
- **Switching to Bearer tokens while leaving tokens inside auto-sent cookies** and concluding “stateless means no CSRF”.
- **Adding `CookieCsrfTokenRepository.withHttpOnlyFalse()` without considering the XOR handler, session rotation, cookie attributes, and SPA token refresh**.

## 10. Checklist before declaring security tests PASS

- [ ] I have identified the browser credential mechanism (session cookie, Basic, Bearer header/cookie) and CSRF requirements.
- [ ] I distinguish **authentication**, **authorization**, and **CSRF**.
- [ ] GET/HEAD/OPTIONS/TRACE are handled per policy; GET is never used to mutate state.
- [ ] POST/PUT/PATCH/DELETE have negative tests for missing/invalid tokens when CSRF is enabled on the chain.
- [ ] For unsafe methods, permission tests always supply a **valid CSRF token** so CSRF does not mask authorization failures.
- [ ] The same endpoint has ADMIN/USER controls paired with valid/missing/invalid tokens.
- [ ] I do not conclude 403 is a role failure from status code alone.
- [ ] Exceptions classify `CsrfException` before other denials.
- [ ] For anonymous requests, I know whether 401 or 302 applies per entry point; CSRF can still return 403 first.
- [ ] I verify `ROLE_ADMIN` vs `ADMIN` accurately and do not confuse `hasRole` with `hasAuthority`.
- [ ] `spring-security-test` is in test dependencies, and mock users are not treated as proof of real login/JWT verification.
- [ ] MockMvc includes security filters using a chain configuration close to production.
- [ ] For SPAs, tokens come from the same session/cookie, masked/raw handling matches, and tokens refresh after login/logout.
- [ ] I do not disable CSRF for browser apps just to make tests green.
- [ ] If an API omits CSRF, I have a threat model proving no ambient credentials exist, rather than relying only on “stateless/JSON”.
- [ ] I never log CSRF tokens, session cookies, Bearer tokens, or sensitive details.
- [ ] With multiple filter chains or `@PreAuthorize`, I have pinpointed where denials originate.
- [ ] I understand MockMvc's limits compared to HTTP/browser end-to-end tests.
- [ ] I run `mvn test` against the project's actual Spring Security/Boot versions and never stop at a single passing 403 test.

**Conclusion:** CSRF and authorization can both return **403** yet differ in **conditions, filters, fixes, and tests**. Always structure tests around **“same user with missing/invalid/valid token”** and **“same valid token with USER/ADMIN”** to reveal the exact order of checks. **The right role never substitutes for a token; a valid token never substitutes for a role.** Only omit CSRF on APIs whose credential model has been properly evaluated.

### Official references

- [Spring Security 6.5 — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Servlet Architecture and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security 6.5 — CsrfConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
