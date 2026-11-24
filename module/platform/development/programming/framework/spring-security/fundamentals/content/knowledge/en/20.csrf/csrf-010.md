# Testing Requests with Valid, Invalid, and Missing Tokens

> **Module:** Spring Security – fundamentals  
> **Topic group:** CSRF  
> **Focus:** Build and run three test scenarios—**valid CSRF token**, **invalid CSRF token**, and **request missing a CSRF token**; prove that data-mutating requests are blocked before entering the controller when the token is invalid/missing. Examples use Spring MVC/Servlet and Spring Security 6.5 with Java 17+.

## 1. Learning Objectives

After this lesson, you can:

1. Explain CSRF and why browser auto-sent login session cookies can become a risk.
2. Distinguish the **server-expected token** from the **client-submitted token**.
3. Design three test cases against **the same HTTP method and endpoint**, varying only the CSRF token state.
4. Predict outcomes: a valid token lets the request proceed; invalid and missing tokens are rejected (by default usually **HTTP 403**).
5. Use Spring Security Test `csrf()`, `csrf().asHeader()`, and `csrf().useInvalidToken()` in `MockMvc`.
6. Verify **whether side effects occurred**, rather than asserting only the response status.
7. Practice with an HTTP client: fetch a token from the server, persist the session cookie, and send POSTs with valid/invalid/missing tokens in the same session.
8. Distinguish CSRF errors from **401 unauthenticated**, **403 insufficient permissions**, **session expiration**, **CORS**, validation errors, and business errors.
9. Understand test limits: MockMvc helpers do not replace browser/integration tests verifying session-bound tokens and cookie policies.

## 2. Problem: Having a Login Cookie Is Not Enough for Safe POSTs

Suppose Alice has logged into a payment website. Her browser holds a session cookie:

~~~http
Cookie: JSESSIONID=opaque-session-id
~~~

When Alice submits a POST from the official page, the browser typically attaches the cookie per cookie policy. Yet another website can also try to make Alice's browser send a request to the payment site. If the backend relies solely on the cookie without checking request origin/CSRF tokens, the action may execute against Alice's intent.

**Cross-Site Request Forgery (CSRF)** is an attack exploiting browsers automatically carrying held credentials (such as session cookies). Attackers do not necessarily need to know the session ID. What matters is that the victim's browser can **send a request carrying valid credentials** even though the action originated from an untrusted source.

CSRF tokens are one defense measure. The server supplies a value that legitimate clients can retrieve and echo back on state-changing requests. Another site cannot arbitrarily read that token if same-origin/CORS boundaries and application defenses are properly configured.

### Conceptual Example

~~~text
Alice logs into shop.example.test
  |
  +-- Browser auto-sends session Cookie to shop.example.test
  |
  +-- GET /transfer-form
  |      Server embeds valid CSRF token into form
  |
  +-- POST /transfer
         Cookie: JSESSIONID=...
         _csrf=<token from form>
         |
         v
      CsrfFilter:
         - does request require CSRF?
         - load expected token from repository
         - read actual token from request
         - compare / validate
         - valid -> enter controller
         - invalid/missing -> reject
~~~

Do not invent a policy like "merely having an `Origin` or `Referer` header is enough" without a threat model and strict validation design. Proper tokens, SameSite, Origin/Referer checks, and other measures complement one another.

## 3. Three Cases to Test

On the same endpoint `POST /api/counter/increment` with the same authenticated user, varying only CSRF:

| Test case | CSRF token in request | Result under default CSRF protection | Does controller run? |
| --- | --- | --- | --- |
| **Valid token** | Valid value matching session's repository/handler mechanism | Request **passes CsrfFilter**; if authz/business checks pass, **200** in demo | **Yes** |
| **Invalid token** | Token present yet altered, fake, or from another session | Usually **403 Forbidden** | **No** |
| **Missing token** | No CSRF parameter/header | Usually **403 Forbidden** | **No** |

**Important:** a "valid token" is only **permission to proceed**, not a guarantee the entire request returns 200. After `CsrfFilter`, Spring Security still checks whether the user is logged in/authorized; the controller can still return 400, 404, 409, or 500. Therefore run the three core tests with **the same authenticated user and permissions**, isolating only the CSRF variable.

Likewise, a `403` status **does not suffice to conclude a CSRF failure**: Spring Security can also return 403 for an authenticated user lacking an authority. Inspect test setup, exception class/trace, and where the request stopped.

## 4. How Are CSRF Tokens Generated and Matched?

In Servlet Spring Security, the central component is `CsrfFilter`, working with:

- `CsrfTokenRepository`: generates/stores/loads expected tokens. By default, Spring Security normally uses `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler`: exposes tokens to request attributes and decodes/reads client-submitted tokens.
- `XorCsrfTokenRequestAttributeHandler`: common default handler in Spring Security 6, encoding/masking response token values to mitigate BREACH.
- `AccessDeniedHandler`: handles missing/invalid CSRF tokens, normally returning 403.

Conceptual flow:

~~~text
POST request
   |
   v
CsrfFilter
   |
   +-- Does method need protection? (POST usually yes)
   |
   +-- CsrfTokenRepository.load/generate expected token
   |
   +-- CsrfTokenRequestHandler.resolve actual token
   |
   +-- Compare actual token against expected token
          |
          +--- valid --> filter chain proceeds
          |
          +--- invalid/missing --> reject, controller not called
~~~

Since Spring Security 6, token loading can be **deferred** (loaded only when needed), and tokens can be presented **XOR-masked**. Therefore do not assume the token visible in HTML/JSON matches byte-for-byte with the raw value stored in the session. If building an SPA reading tokens from cookies, check the SPA token handling docs for your exact version rather than copying Spring Security 5 configs.

### Where Can the Token Be Sent?

Under default conventions, Spring Security reads tokens from:

~~~http
POST /api/counter/increment HTTP/1.1
Cookie: JSESSIONID=...
X-CSRF-TOKEN: <valid token>
~~~

or with an HTML form:

~~~http
POST /api/counter/increment HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...

_csrf=<valid token>
~~~

Default parameter name is normally `_csrf`, default header name is normally `X-CSRF-TOKEN` (and some setups use `X-XSRF-TOKEN` per handler/repository). **Get exact names from `CsrfToken.getHeaderName()` and `getParameterName()`** if customized.

Tokens must not be auto-attached by browsers to requests from every source like session cookies. Legitimate clients must fetch tokens from valid pages/forms or CSRF endpoints and actively place them in headers/parameters. That establishes the anti-CSRF boundary.

## 5. Which HTTP Methods Require a Token by Default?

With default configuration:

| HTTP method | CSRF token normally required? | Things to remember |
| --- | --- | --- |
| GET | No | Must be used for reads, zero side effects |
| HEAD | No | Not used to mutate data |
| OPTIONS | No | Typically used for preflight or metadata |
| TRACE | No | Normally restricted/disabled |
| POST | **Yes** | Create/write data |
| PUT | **Yes** | Replace/update data |
| PATCH | **Yes** | Partial update |
| DELETE | **Yes** | Delete data |

Rules can be adjusted via `csrf.requireCsrfProtectionMatcher(...)` or `csrf.ignoringRequestMatchers(...)`, though concrete security justification is needed. **Never transfer money, delete accounts, or place orders via GET** relying on GET needing no token. Default CSRF protection cannot fix a side-effecting GET design flaw.

## 6. Preparing the Java 17 + Spring Boot Demo

Let's build a simple app with an in-memory counter:

- `GET /api/csrf`: returns the Spring Security token for the current session.
- `GET /api/counter`: reads the current count without changing state.
- `POST /api/counter/increment`: increments the counter by one. Requires `USER` role and a valid CSRF token.
- HTTP Basic is used to test authentication cleanly in `curl`. The app keeps CSRF protection **enabled**, since the lesson's goal is testing CSRF.

**Why use HTTP Basic in the demo?** It makes sending username/password from `curl` easy without building a login form. Browsers can replay cached Basic credentials automatically, so CSRF still needs evaluation whenever browsers can send ambient credentials. For pure server-to-server APIs sending manual Bearer tokens, the threat model can differ. Do not turn this Basic demo into a universal recommendation for all APIs.

Environment: **JDK 17+**, **Maven 3.9+**, **Spring Boot 3.5.7 / Spring Security 6.5.x**, Servlet/Spring MVC app.

### Project Tree

~~~text
csrf-three-cases/
  pom.xml
  src/main/java/com/example/csrfcases/
    CsrfCasesApplication.java
    SecurityConfig.java
    CounterService.java
    CounterController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/csrfcases/
    CsrfCasesTests.java
~~~

### 6.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>csrf-three-cases</artifactId>
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
~~~

### 6.2. File CsrfCasesApplication.java

~~~java
package com.example.csrfcases;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfCasesApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfCasesApplication.class, args);
    }
}
~~~

### 6.3. File SecurityConfig.java

~~~java
package com.example.csrfcases;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf", "/api/counter")
                    .authenticated()
                .requestMatchers("/api/counter/increment")
                    .hasRole("USER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build()
        );
    }
}
~~~

**Explanation:**

- **CSRF is enabled.** Never use `csrf.disable()` to make tests "pass easily".
- Every request to `/api/counter/increment` requires role `USER` *and* must pass `CsrfFilter`.
- `HttpBasic` lets `curl` send credentials easily. `MockMvc` tests can use `user(...)` to establish test identity without verifying password encoding.
- In-memory `UserDetailsService` and hardcoded passwords are for demos only; production uses reliable user stores and secret management.
- `anyRequest().denyAll()` blocks all undeclared URLs so test endpoints do not become accidental public writes.
- No custom `CsrfTokenRepository` or `CsrfTokenRequestHandler` is configured, so the example follows the selected Spring Security version's defaults.

### 6.4. File CounterService.java

~~~java
package com.example.csrfcases;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class CounterService {

    private final AtomicInteger count = new AtomicInteger();

    public int current() {
        return count.get();
    }

    public int increment() {
        return count.incrementAndGet();
    }
}
~~~

`AtomicInteger` is purely in-memory state to observe side effects. In real systems, replace with database transactions and proper business authorization. This lesson intentionally uses a simple action to prove **rejected POSTs never increment the counter**.

### 6.5. File CounterController.java

~~~java
package com.example.csrfcases;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class CounterController {

    private final CounterService service;

    public CounterController(CounterService service) {
        this.service = service;
    }

    @GetMapping("/csrf")
    public Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName()
        );

        if (token == null) {
            throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "CSRF token not available"
            );
        }

        // getToken() forces deferred token retrieval/generation when needed.
        // Endpoint is for authenticated users only.
        return Map.of(
            "headerName", token.getHeaderName(),
            "parameterName", token.getParameterName(),
            "token", token.getToken()
        );
    }

    @GetMapping("/counter")
    public Map<String, Integer> current() {
        return Map.of("count", service.current());
    }

    @PostMapping("/counter/increment")
    public Map<String, Integer> increment() {
        return Map.of("count", service.increment());
    }
}
~~~

**Points to understand:**

- `CsrfToken.class.getName()` is a request attribute populated by Spring Security for the default handler. Calling `getToken()` evaluates the deferred token when needed.
- `/api/csrf` returns the token for **same-origin clients or test HTTP clients** to include in the next request. Never open CORS arbitrarily to foreign domains or expose tokens in logs.
- With the default `HttpSessionCsrfTokenRepository`, tokens are session-bound; clients must preserve the matching cookie/session on POSTs.
- Tokens in responses may be **XOR-masked**; send back the exact value returned by the server without decoding or hardcoding it.
- `GET /api/counter` does not alter state, whereas `POST /api/counter/increment` produces a clear side effect.

### 6.6. File application.properties

~~~properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

On localhost, the sample config uses HTTP for practice; real deployments need **HTTPS**, `Secure` cookies, and verifying proxy, domain/path, and SameSite policies. This lesson requires no custom cookie repository; it retains session-based defaults.

## 7. Automated Testing with MockMvc

Spring Security Test provides `SecurityMockMvcRequestPostProcessors.csrf`. This is the standard way to test CSRF in Servlet applications without manually crafting tokens/cookies per test.

### Three Main Helpers

~~~java
// Valid token via default request parameter:
.with(csrf())

// Valid token via HTTP header:
.with(csrf().asHeader())

// Intentionally send an invalid token:
.with(csrf().useInvalidToken())
~~~

These are fragments, not standalone Java programs. Place them inside `MockMvcRequestBuilders.post(...)`.

### 7.1. File CsrfCasesTests.java

~~~java
package com.example.csrfcases;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfCasesTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    CounterService counter;

    @Test
    void correctTokenAsParameterAllowsMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(before + 1));

        assertEquals(before + 1, counter.current());
    }

    @Test
    void correctTokenAsHeaderAlsoAllowsMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER"))
                .with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(before + 1));

        assertEquals(before + 1, counter.current());
    }

    @Test
    void wrongTokenIsForbiddenWithoutMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.current());
    }

    @Test
    void missingTokenIsForbiddenWithoutMutation() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("learner").roles("USER")))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.current());
    }

    @Test
    void safeGetDoesNotRequireCsrfToken() throws Exception {
        mvc.perform(get("/api/counter")
                .with(user("learner").roles("USER")))
            .andExpect(status().isOk());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() throws Exception {
        mvc.perform(post("/api/counter/increment")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validCsrfDoesNotGrantMissingRole() throws Exception {
        int before = counter.current();

        mvc.perform(post("/api/counter/increment")
                .with(user("reader").roles("READER"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.current());
    }
}
~~~

### Test Logic Explanation

**Valid token test:** `.with(user("learner").roles("USER"))` fixes identity/authority. `.with(csrf())` supplies a valid token. The request reaches the controller and increments the counter by **exactly one**.

**Invalid token test:** same user and POST endpoint, yet invalid token. Must return 403 and leave `counter.current()` **unchanged**.

**Missing token test:** same authorized user, yet no token parameter/header. Must return 403 and leave counter **unchanged**.

**Header token test:** proves API header integration also works, not only HTML form parameters.

**GET test:** by default GET needs no CSRF because GET has no side effects.

**Missing authentication test:** a request with a valid token must still authenticate. In this HTTP Basic setup, expect 401. This shows CSRF **is not a login token**.

**Missing authority test:** a user with a valid token yet lacking `USER` still gets 403; never mislabel that as a CSRF error.

### Why Does State Verification Matter?

A test checking only:

~~~java
.andExpect(status().isForbidden())
~~~

does not prove state stayed unchanged. For instance, a buggy endpoint might update the database before returning 403 due to downstream logic. In the demo, asserting `assertEquals(before, counter.current())` ensures zero side effects occurred. In production, verify repository row counts, audit events, queues, outgoing HTTP calls, and business transactions.

### What MockMvc Helpers Do *Not* Test

`with(csrf())` is a test helper generating a valid token and attaching it to a mock request. It **does not prove** frontend browsers fetch tokens properly, cookies persist properly, CORS/SameSite align, or sessions stay consistent after login. Hence real HTTP/browser tests are covered later.

`with(user(...))` also bypasses HTTP Basic password checks; it establishes an authenticated user to isolate the CSRF variable. This is deliberate so all three cases share identical auth conditions. To test real Basic credentials, use `curl` or dedicated integration tests.

### Running Tests

~~~bash
mvn clean test
~~~

**Expectation:** All tests in `CsrfCasesTests` pass in a compatible environment. Counter state is shared across the Spring context, yet each test captures `before`, making tests **independent of JUnit execution order** (unless parallel execution mutates the counter concurrently).

This is educational code with complete files/paths/imports; the lesson **does not claim Maven was run or BUILD SUCCESS was observed**. When adapting to real projects, run tests with exact dependency versions and update any relevant security customizations.

## 8. Real HTTP Testing with curl: Valid, Invalid, Missing Tokens

This section demonstrates session-bound CSRF tokens in practice, beyond MockMvc request post-processors.

### 8.1. Startup

In the first terminal:

~~~bash
mvn spring-boot:run
~~~

Run commands in a second terminal. Requires `curl`; to parse tokens from JSON in shell, also use `jq`. On Windows PowerShell, use `curl.exe` instead of the `curl` alias, or use DevTools/Postman to supply tokens manually.

### 8.2. Fetching Token and Saving Session Cookie

~~~bash
TOKEN=$(curl -fsS \
  -u learner:demo123 \
  -c cookies.txt \
  http://localhost:8080/api/csrf | jq -r '.token')
~~~

Explanation:

- `-u learner:demo123` sends HTTP Basic credentials for the request.
- `-c cookies.txt` persists cookies returned by the server, including any created session cookie.
- `/api/csrf` returns the token; `jq -r '.token'` extracts just the token string without printing the full response.
- Variable `TOKEN` holds an anti-CSRF credential for subsequent requests. Never paste it into logs, tickets, or chats.
- Every POST below requires **the same cookie jar**; omitting `-b cookies.txt` can mismatch the session.

To inspect the server-configured header name, the JSON returns `headerName` and `parameterName`; the example defaults to `X-CSRF-TOKEN`.

### 8.3. Case 1 — Missing Token

~~~bash
curl -i \
  -u learner:demo123 \
  -b cookies.txt \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Expected:

~~~http
HTTP/1.1 403 Forbidden
~~~

Despite valid credentials and session cookie, the request **contains neither `_csrf` nor `X-CSRF-TOKEN`**, so `CsrfFilter` blocks it before the controller.

Read the counter:

~~~bash
curl -fsS -u learner:demo123 \
  -b cookies.txt http://localhost:8080/api/counter
~~~

Expected counter value **does not increase** because the previous request was rejected. Exact JSON depends on prior valid requests.

### 8.4. Case 2 — Invalid Token

~~~bash
curl -i \
  -u learner:demo123 \
  -b cookies.txt \
  -H "X-CSRF-TOKEN: deliberately-invalid" \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Expected:

~~~http
HTTP/1.1 403 Forbidden
~~~

Having a header does not mean the token is valid. Under the default handler, the submitted token must resolve and match the repository/session. An invented string is normally invalid, so the controller does not run and the counter stays unchanged.

Never test using real production tokens. Only use test environments with test credentials.

### 8.5. Case 3 — Valid Token

~~~bash
curl -i \
  -u learner:demo123 \
  -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

The body contains `{"count":...}` incremented by one. The cookie jar and token must belong to the same valid session. If 403 occurs, check whether the token came from the current active session rather than assuming a code bug.

**HTTP test summary table:**

| Case | Credentials | Session cookie | CSRF header | Expected status | Counter |
| --- | --- | --- | --- | --- | --- |
| Missing token | Valid | Same jar | None | 403 | Unchanged |
| Invalid token | Valid | Same jar | Fake value | 403 | Unchanged |
| Valid token | Valid | Same jar | Server-issued token | 200 | Increments by 1 |
| Token present, no auth | None | Per request | Valid token | Possibly 401 per Basic config | Unchanged |
| Token present, missing role | Another authenticated user | Matching session | Valid token | 403 | Unchanged |

For cases beyond the core three, HTTP status varies by entry point/filter chain. In this Basic-only demo, the goal of the three core cases is **isolating CSRF**: credentials and permissions stay valid.

### 8.6. Extra Case — Session A's Token Used with Session B

Default CSRF tokens bind to server sessions. Try two separate cookie jars:

~~~bash
TOKEN_A=$(curl -fsS -u learner:demo123 \
  -c session-a.txt \
  http://localhost:8080/api/csrf | jq -r '.token')

curl -fsS -u learner:demo123 \
  -c session-b.txt \
  http://localhost:8080/api/csrf > /dev/null

curl -i -u learner:demo123 \
  -b session-b.txt \
  -H "X-CSRF-TOKEN: $TOKEN_A" \
  -X POST \
  http://localhost:8080/api/counter/increment
~~~

Expect **403**, because token A is not session B's expected token. Ensure both jars start from a clean state without accidentally sending session A's cookie when creating B. This test is especially helpful when suspecting a frontend is reusing CSRF tokens from an expired session.

**Note:** Some systems use `CookieCsrfTokenRepository` or custom request handlers, so token/session binding must be checked against actual design. Never treat "every CSRF token in every app lives in `HttpSession`" as a universal law.

## 9. Testing with Browsers and DevTools

For apps with HTML forms, follow this observation workflow:

1. Log in on a browser profile and open the page containing the form.
2. Inspect Network → verify whether the HTML response contains hidden input `_csrf`; for SPAs, verify where the frontend fetches tokens.
3. Submit a valid POST with the token. Observe status and side effects.
4. In a dev environment, remove the hidden input/header and re-submit. Expect 403.
5. Replace the token with a bogus string. Expect 403.
6. Log out/log back in or let the session expire; fetch a fresh token per app mechanism, then POST. Old tokens may be invalid.
7. Use separate profiles/incognito windows to avoid mixing cookies/sessions across users.

**Do not equate seeing a cookie in DevTools with having a valid token.** `JSESSIONID` and CSRF tokens serve distinct purposes. With `HttpOnly`, JavaScript cannot read the session cookie directly, yet browsers still auto-send it when eligible. CSRF tokens must be actively submitted by clients per backend rules.

Never include screenshots containing real tokens or session IDs in public reports. Replace secrets with placeholders when sharing bugs.

## 10. Causes of 403 Beyond CSRF

A POST receiving **403** can stem from:

- Missing or invalid CSRF token;
- Authenticated user lacking required `ROLE_USER`/authority;
- Method-level security such as `@PreAuthorize` denying access;
- Tenant/owner/relationship policy denial;
- Custom filter/gateway/WAF rejection;
- Invalidated session/identity paired with custom exception handling;
- Other CSP/CORS/frontend error handling surfaced in UI without sharing the same root cause.

Hence good tests maintain **control variables**:

| Variable | How the three main cases must hold it |
| --- | --- |
| Endpoint | Same `POST /api/counter/increment` |
| HTTP method | POST for all three |
| Authentication | Same authenticated user |
| Authorities | Same `ROLE_USER` |
| Session | Same context/session in real HTTP tests |
| Request body | Identical; demo needs no body |
| CSRF token | Vary only valid / invalid / missing |
| Business outcome | Counter increments only in valid case |

If an invalid-token test simultaneously changes username, session, and endpoint, a 403 status cannot prove which layer rejected it.

### Understanding 401 vs. 403

- **401 Unauthorized:** request lacks or carries invalid authentication credentials, per HTTP authentication entry point.
- **403 Forbidden:** request is refused; may be due to CSRF or authenticated identity lacking permissions.
- A request **missing both login and CSRF** may be rejected by `CsrfFilter` before reaching Spring Security's authentication step. Therefore CSRF experiments should establish a valid user upfront.
- With form login, missing authentication usually causes a **302 redirect** instead of 401; never assume HTTP Basic's 401 applies to all apps.

## 11. Valid Token Still Failing: Key Scenarios

### 11.1. Token Belongs to an Expired Session

The client fetches token `T` while session `S1` is active; later `S1` times out and the new request lacks the matching session. The server holds a different expected token or none for the new session; `T` no longer matches.

**How to handle:** the frontend must fetch a fresh token whenever login/session state changes. Never persist old tokens indefinitely in `localStorage` and attach them to all future requests.

### 11.2. Logout and Re-Login

Spring Security clears/resets CSRF tokens on authentication success or logout success. With deferred tokens, frontends may need to actively fetch a new token after login/logout, especially in SPAs. Sending a pre-login token into a rotated session can yield 403.

**How to handle:** design `/csrf` or form rendering to issue fresh tokens as needed; test the flow login → fetch fresh token → POST.

### 11.3. XOR-Masked Tokens vs. Raw Cookie Tokens

Since Spring Security 6, the default `XorCsrfTokenRequestAttributeHandler` provides BREACH protection by adding randomness to tokens exposed to clients. If using `CookieCsrfTokenRepository` in an SPA, JavaScript may read the **plain value** from the cookie while the default handler expects a masked token along another path. That scenario requires a `CsrfTokenRequestHandler` strategy matching the SPA docs, not merely renaming headers.

The demo does not use `CookieCsrfTokenRepository`: tokens come from the request attribute in JSON, and the exact returned value is sent back in the header.

### 11.4. AJAX Forgetting Headers or Mismatching Header Names

The frontend might send `X-XSRF-TOKEN` while the backend expects `X-CSRF-TOKEN`, or a JSON body contains `"_csrf"` where the handler does not look. Verify `CsrfToken.getHeaderName()` and `getParameterName()`, how the frontend sends requests, and the active request handler.

Avoid stuffing tokens into URL query strings; URLs leak into logs/history.

### 11.5. Cookies Not Reaching the Server

Browsers may omit session cookies due to `SameSite`, `Secure`, `Domain`, `Path`, cross-site rules, or `fetch` credentials mode. Then a syntactically valid token fails to match the expected session.

Debug client-side via DevTools and server-side session correlation. Never log intact session IDs. Enable CORS/`credentials: include` only for designed, controlled cross-origin architectures; CORS never replaces CSRF.

### 11.6. Double-Submit Cookies or Custom Repositories

Some systems use cookie + header patterns with repositories other than `HttpSessionCsrfTokenRepository`. Exact requirements depend on how tokens are signed, bound to session/identity, and handled. Never copy session-bound test assumptions from default setups and wrongly conclude a custom repository is broken.

## 12. A CSRF Token Is Not an Authentication Token

A valid CSRF token **is neither a username/password** nor an OAuth2 access token. It proves the request carries an app-issued anti-CSRF token within the right session/context; it grants neither identity nor permissions.

Example:

~~~text
POST /api/counter/increment
  Authentication = anonymous
  CSRF token     = valid

Result: not permitted merely because the token is valid.
~~~

Similarly:

~~~text
POST /api/counter/increment
  Authentication = user:reader
  Authority      = ROLE_READER
  CSRF token     = valid

Result: still lacks ROLE_USER -> deny.
~~~

**Three separate checks:**

1. Authentication: who is the caller?
2. CSRF protection: does the state-changing request carry valid anti-cross-site-forgery proof?
3. Authorization: is the caller allowed to perform this action on this resource?

Add business validation and data-level authorization inside services too. Never drop those layers just because CSRF tests pass.

## 13. CSRF with Bearer-Token REST APIs

Not every API needs the exact same CSRF policy as a session-cookie app:

- **Browser session/cookie authentication:** normally needs CSRF protection since browsers auto-send cookies.
- **Browser-cached HTTP Basic:** must be treated as credentials browsers can auto-send; do not auto-exempt CSRF.
- **Server-to-server clients using explicitly attached Authorization Bearer tokens:** when zero ambient browser credentials exist and cookie auth is rejected, many systems configure stateless chains and may not need CSRF tokens on that API chain.
- **JWT stored in a cookie:** despite being a JWT, browsers can still auto-send the cookie; **CSRF must still be evaluated**.
- **Hybrid apps using both cookies and Bearer tokens:** evaluate each `SecurityFilterChain`/endpoint separately; never disable CSRF app-wide simply because one set of APIs uses Bearer tokens.

If choosing to omit CSRF on an API chain, document threat-model justification, confirm clients and auth never auto-send cross-site credentials, separate matchers clearly, and keep tests protecting remaining browser routes.

## 14. Building a Complete Test Checklist

For any sensitive POST/PUT/PATCH/DELETE endpoint, maintain a matrix:

| Test | Token | Authentication | Authorization | Expected |
| --- | --- | --- | --- | --- |
| Valid request | Valid | Valid | Authorized | Passes CSRF, business logic succeeds |
| Missing token | Missing | Valid | Authorized | 403, no mutation |
| Invalid token | Invalid | Valid | Authorized | 403, no mutation |
| Header token | Valid via header | Valid | Authorized | Succeeds like parameter if supported |
| Safe GET | None | Valid | Read authorized | Permitted, no mutation |
| Missing authentication | Valid | Missing | N/A | 401/redirect per auth mechanism |
| Missing authority | Valid | Valid | Missing | 403 from authorization |
| Expired session | Stale token | Invalid identity/session | N/A | Must not execute mutation |
| Token from session B | Mismatches A | Valid | Authorized | Rejected per default repository |
| Login/logout rotation | Stale token | Varies | N/A | Client must fetch fresh token |
| Cross-origin request | Cannot read token | Cookie per policy | N/A | Cannot succeed via ambient credentials alone |

**Acceptance criteria:** Zero data writes occur on requests with missing/invalid CSRF tokens, even with valid credentials. Tests must assert database/service state, not merely response codes.

## 15. Plain Java 17: Self-Checking Expected Outcomes

This is a standalone learning model, not a real CSRF implementation. Create `CsrfCaseSimulation.java`:

~~~java
import java.util.Objects;

public class CsrfCaseSimulation {
    static boolean accepted(String expected, String received) {
        return received != null && Objects.equals(expected, received);
    }

    public static void main(String[] args) {
        String sessionAToken = "demo-token-a";
        String sessionBToken = "demo-token-b";

        System.out.println("correct=" +
            accepted(sessionAToken, "demo-token-a"));
        System.out.println("wrong=" +
            accepted(sessionAToken, "invalid-token"));
        System.out.println("missing=" +
            accepted(sessionAToken, null));
        System.out.println("other-session=" +
            accepted(sessionBToken, "demo-token-a"));
    }
}
~~~

Run:

~~~bash
javac CsrfCaseSimulation.java
java CsrfCaseSimulation
~~~

Exact stdout:

~~~text
correct=true
wrong=false
missing=false
other-session=false
~~~

**This is solely a conceptual comparison.** Real applications must generate random tokens with vetted mechanisms, manage repositories, and use Spring Security's request handlers—including masking/deferred loading where appropriate. Never generate tokens from static strings or write custom filters replacing `CsrfFilter` in production.

## 16. Common Testing Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Valid POST test forgets `.with(csrf())` | Gets 403 even with right controller | Add valid token to positive test |
| Using `.with(csrf())` on every test including missing-token test | Stops testing negative case | Never attach csrf post-processor for missing-token tests |
| Changing user while changing token | Fails to isolate CSRF | Keep identical principal/authority/endpoint |
| Testing invalid token with another session's value without controlling sessions | Outcome depends on repository | Use `csrf().useInvalidToken()` or controlled session-bound integration tests |
| Asserting only HTTP 403 | Side effects may still have run | Assert state stayed unchanged |
| Seeing 403 and blaming CSRF | Could be access denied from role/tenant | Inspect filter/exception and test setup |
| Disabling CSRF to turn tests green | Defeats security goal | Keep CSRF and send valid tokens |
| Mutating on GET without needing tokens | Default CSRF does not guard GET | Keep GET read-only |
| Putting tokens in query strings | Leaks in logs/history | Header or form parameter |
| Hardcoding static CSRF tokens | Loses repository/session binding | Fetch tokens from server |
| Using pre-login session token after login | Token may have been cleared/rotated | Fetch fresh token |
| Sending raw token when handler expects masked | Spring Security 6 XOR/BREACH behavior | Follow version's handler/SPA docs |
| Omitting cookie jar in `curl` | Token mismatches session | `-c` on fetch, `-b` on POST |
| Thinking CORS replaces CSRF | CORS governs response reads and some preflight, not general CSRF defense | Apply proper CSRF protection/threat modeling |
| Thinking SameSite suffices everywhere | Same-site subdomains and browser quirks need assessment | Defense in depth |
| Disabling CSRF everywhere due to JWT | JWT in cookies remains ambient | Audit where tokens are stored and sent |
| Printing tokens/session IDs in debug logs | Exposes credentials | Redaction, request IDs, safe telemetry |

## 17. Exercises and Self-Check Questions

**Exercise 1:** Why can a POST with a valid `JSESSIONID` yet no CSRF token still return 403? Describe `CsrfFilter`'s role.

**Exercise 2:** Across three tests with the same `ROLE_USER` user, only one succeeds. Describe exactly how to configure `with(csrf())`, `with(csrf().useInvalidToken())`, and the missing-CSRF request.

**Exercise 3:** If both valid-token and invalid-token requests receive 403, what must you check before concluding CSRF config is broken?

**Exercise 4:** Why must you assert that the counter/database did not change in the invalid and missing token cases?

**Exercise 5:** After login, the frontend reuses a pre-login CSRF token and gets 403. Explain the effect of `CsrfAuthenticationStrategy` and deferred tokens, plus how to fix it.

**Exercise 6:** A user lacking `ROLE_USER` sends a POST with a valid CSRF token. What is the right outcome? Why cannot a valid token substitute for authorization?

**Exercise 7:** An API uses JWTs in `HttpOnly` cookies. Should CSRF be disabled simply because "we use JWT"? Explain.

**Exercise 8:** Given cookie jars A and B, A's token is sent with B. In the session-based demo, what must the server do? Why?

**Exercise 9:** Why do GETs need no token by default, yet GET must never delete data?

**Exercise 10:** Compare the benefits and limits of MockMvc CSRF helpers versus `curl`/browser integration tests.

### Answer Hints

1. Cookies only prove session/authentication; CSRF tokens provide separate proof against cross-site forged requests.
2. Valid: `.with(csrf())`; invalid: `.with(csrf().useInvalidToken())`; missing: omit `csrf()`.
3. Authentication, authorities, session, method/path, header/parameter names, repository, token lifecycle, and exception source.
4. Status 403 alone does not prove zero mutation occurred.
5. Old tokens may be cleared/rotated after authentication; fetch a fresh token from forms/endpoints post-login.
6. 403 due to missing permissions; CSRF tokens do not grant `ROLE_USER`.
7. No. Browsers auto-send cookies even when holding JWTs; CSRF must still be evaluated.
8. Reject tokens mismatched with the session/repository, performing zero mutation.
9. GET must be safe/read-only; writing on GET opens CSRF vulnerabilities and violates HTTP semantics.
10. MockMvc isolates/tests filters rapidly; HTTP/browser tests verify cookie jars, CSRF token delivery, session continuity, and real browser behavior.

## 18. Summary

**The best CSRF experiment starts with three requests identical in user, roles, method, endpoint, and session; differing only in token: valid, invalid, missing.**

- **Valid token:** passes `CsrfFilter`; if authn/authz/business checks pass, data writes occur.
- **Invalid token:** typically **403**, controller never runs, state unchanged.
- **Missing token:** typically **403**, controller never runs, state unchanged.

Use `MockMvc` to isolate Spring Security's guard logic and **real HTTP tests** to confirm frontend/cookies/sessions/tokens connect properly. CSRF tokens are one protection layer, **never replacing authentication or authorization**.

### Official Documentation

- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security 6.5 — Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [MDN — Cross-Site Request Forgery (CSRF)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF)
