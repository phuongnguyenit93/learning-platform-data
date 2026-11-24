# Distinguishing CSRF Errors from Insufficient-Permission Errors in Spring Security

> **Context:** Spring Security Servlet, Spring MVC, and HTTP requests. This lesson helps distinguish **403 from a missing/invalid CSRF token** from **403 from insufficient authorization permissions**, while also explaining **401 from unauthenticated requests**, how to identify the blocking filter, and how to write tests that prove the root cause. Examples use Java 17+, Spring Boot 3.5.x, and Spring Security 6.5.x.

## 1. Same HTTP 403, Why Can the Causes Be Completely Different?

Look at three requests to the same `POST /api/docs` endpoint:

| Request | Identity / permissions | CSRF token | Expected outcome | Cause |
| --- | --- | --- | --- | --- |
| A | Authenticated Bob, has `docs:write` | **Missing** | **403** | Blocked earlier by `CsrfFilter` |
| B | Authenticated Alice, only has `docs:read` | **Valid** | **403** | Denied by `AuthorizationFilter` |
| C | Authenticated Bob, has `docs:write` | **Valid** | **201** | Passed both CSRF and authorization |

Looking only at `403 Forbidden` in the first two rows is **not enough** to infer a permission error. In A, permissions were granted properly, yet the request failed the **Cross-Site Request Forgery** protection layer. In B, the request passed CSRF, yet lacked the required authority.

In the sample app's HTTP Basic setup, when sending no credentials yet including a valid CSRF token, a request to a protected endpoint typically returns **401 Unauthorized**. However, if **both unauthenticated and missing a CSRF token** on a POST, `CsrfFilter` can block before Spring Security handles authentication and return **403**. Therefore you cannot deduce "403 means already logged in".

**Three immediate diagnostic questions to ask:**

1. Does the request use **GET/HEAD/OPTIONS/TRACE** or **POST/PUT/PATCH/DELETE**?
2. Is CSRF protection enabled for that request, and does the token match the current session/context?
3. If CSRF passed, is the caller authenticated and holding the exact role/authority required by the HTTP rule?

## 2. CSRF and Authorization Protect Two Different Things

### 2.1. CSRF Prevents Forged Actions from Another Site

In a CSRF attack, the victim is logged into website A. The attacker tricks the browser into sending a state-changing request to A from website B. The browser may **automatically attach session cookies** (or certain other auto-sent credentials) so server A sees a valid session, even though the victim **did not intentionally initiate that operation**.

For instance, if a banking site allows profile changes via POST and checks only the login cookie, a malicious page can attempt to submit a form POST on the victim's behalf. A CSRF token is an additional signal that the attacker's page cannot easily obtain when server, browser, and client are properly configured.

**A CSRF token is not a role, permission, or access token.** Its purpose is proving the request does not rely solely on an automatically attached credential. CSRF protection does not decide whether Alice is allowed to write document 42.

### 2.2. Authorization Checks What Actions a Principal May Perform

Authorization asks: does this authenticated identity have `docs:write`, `ROLE_ADMIN`, the right tenant, and permission for the specific resource?

Example:

~~~java
// Fragment in authorizeHttpRequests:
.requestMatchers(HttpMethod.POST, "/api/docs")
    .hasAuthority("docs:write")
~~~

The matcher identifies **POST document creation**; the policy checks the literal authority `docs:write`. This rule does **not** issue a CSRF token itself nor replace `CsrfFilter`.

### 2.3. Two-Layer Protection Matrix

| CSRF gate (when applicable) | Authentication/authorization | Let request proceed? |
| --- | --- | --- |
| Fail | Not yet evaluated or unexamined | **No** |
| Pass | Unauthenticated when login is required | **No** (HTTP Basic typically 401) |
| Pass | Authenticated yet lacking permission | **No** (typically 403) |
| Pass | Authenticated with sufficient permission | **Yes**, then controller/service can still block per business rules |

CSRF is a **necessary condition within its scope of application**, not a sufficient condition to grant access. Likewise, having sufficient permissions does not permit bypassing CSRF when the app enables that protection layer.

## 3. Filter Flow: Why Can a Request Be Blocked Before Permission Checks?

With a Servlet `SecurityFilterChain` having CSRF, HTTP Basic, and `authorizeHttpRequests` enabled, Spring Security documentation describes the conceptual order:

~~~text
HTTP request
   |
   v
CsrfFilter
   |-- Method/URL does not need CSRF -> proceed
   |-- Needs CSRF + missing/invalid token
   |       -> AccessDeniedHandler -> typically 403; STOP
   |-- Needs CSRF + valid token -> proceed
   |
   v
BasicAuthenticationFilter (or appropriate auth filter)
   |-- Missing/invalid credential -> entry point/challenge per config
   |-- Authentication succeeds -> Authentication
   |
   v
AuthorizationFilter
   |-- Rule allows -> controller/service
   |-- Rule denies -> AccessDeniedException -> 403
   |                      (or entry point if anonymous)
   v
Controller / method security / domain policy
~~~

The diagram intentionally lists only the relevant filters and is **not** a complete list. Actual ordering may contain many other filters, multiple `SecurityFilterChain`s, and customizations.

**Important details:**

- `CsrfFilter` checks the request's token when CSRF is required; if invalid, it can hand `AccessDeniedException` directly to **`AccessDeniedHandler`** and terminate the chain.
- Common CSRF exceptions are `MissingCsrfTokenException` and `InvalidCsrfTokenException`, both in the access-denied family. The actual exception name can depend on stored token state and client token state; there is **not always a one-to-one mapping** between "missing header" and exception class name.
- In `AuthorizationFilter`, insufficient permission can result in `AccessDeniedException`; `ExceptionTranslationFilter` participates in handling/routing to the entry point or denied handler.
- Because both branches can end with status **403**, a generic response may avoid exposing the cause to prevent security information leakage.

When debugging, what matters most is **which filter denied**, not just which HTTP status code was returned.

## 4. Which HTTP Methods Does Default CSRF Apply To?

Standard Servlet Spring Security enables CSRF protection by default and requires a token for **unsafe methods**.

| HTTP method | Needs CSRF token under default config? | Notes |
| --- | --- | --- |
| `GET` | No | Must be designed read-only with no side effects |
| `HEAD` | No | Semantics like GET but returns no body |
| `OPTIONS` | No | Typically related to CORS preflight |
| `TRACE` | No | Classified as safe by the default matcher, though TRACE should generally not be opened arbitrarily |
| `POST` | **Yes** | Usually creates resources, submits forms, or triggers operations |
| `PUT` | **Yes** | Usually replaces resources |
| `PATCH` | **Yes** | Usually partially updates |
| `DELETE` | **Yes** | Usually deletes resources |

These are **defaults**, and can differ if code configures `requireCsrfProtectionMatcher`, `ignoringRequestMatchers`, multiple chains, or disables CSRF.

Two very easily confused cases:

1. `POST /public/feedback` configured with `permitAll()` **can still require a CSRF token**, because `permitAll` belongs to authorization and does not disable `CsrfFilter`.
2. `GET /api/docs` with Alice having read permission **does not need a CSRF token** by default. Sending an invalid CSRF header on a GET usually does not trigger a CSRF denial because the filter does not enforce token checking for that request.

If a GET actually mutates state, that is an **HTTP design flaw**. Never use "GET does not need CSRF" as an excuse to build delete/money-transfer operations on GET. Switch to an appropriate method and protect it accordingly.

## 5. Where Is the Token Stored and Sent?

In Spring Security 6.5, CSRF protection has these components:

- `CsrfTokenRepository`: where the expected token is stored/loaded. Servlet defaults to `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler`: how the token is exposed to views/requests and how the client-sent value is extracted.
- `CsrfFilter`: decides which requests need token checks and compares the client token against the expected token.
- `AccessDeniedHandler`: handles missing/invalid tokens and prevents the request from proceeding.

Some client forms:

| Client type | Common usage |
| --- | --- |
| Server-rendered HTML form | Adds hidden input `_csrf` (typically supported by view/framework) |
| AJAX/SPA | Sends token via header, typically `X-CSRF-TOKEN` or `X-XSRF-TOKEN` depending on config |
| Cookie-based CSRF repository | `CookieCsrfTokenRepository` uses convention cookie `XSRF-TOKEN` and header `X-XSRF-TOKEN` |
| `MockMvc` tests | `.with(csrf())` or `.with(csrf().asHeader())` generates a valid token for tests |

**You cannot send an arbitrary string** like `X-CSRF-TOKEN: test` and treat it as a valid token. The client value must match the server's expected token **in the right context**. With a session repository, the session cookie and token must correspond.

In Spring Security 6, *deferred CSRF tokens* and BREACH protection with randomized values are applied by default. SPAs using cookies, reading the token from JavaScript, and sending back a header may require configuring an appropriate request handler; do not merely add `CookieCsrfTokenRepository` and assume all login/logout/AJAX flows work.

**After login/logout**, old tokens may be cleared or need refreshing because the CSRF strategy changes with the authentication lifecycle. If the frontend keeps an old token and POSTs again, it can receive a 403 CSRF **even though the account is logged in and has full permissions**.

## 6. Diagnostic Matrix: Same Endpoint, Varying One Variable at a Time

Assume:

- `POST /api/docs` requires `hasAuthority("docs:write")`;
- CSRF is enabled for POST;
- Bob has `docs:write`;
- Alice only has `docs:read`;
- Carol only has `ROLE_ADMIN`;
- Dave has `ROLE_USER`;
- HTTP Basic is used for the example.

| Situation | Credential | CSRF | Authority | Expected outcome | Key reason |
| --- | --- | --- | --- | --- | --- |
| Bob creates document | Valid | Valid | Has `docs:write` | **201** | Both conditions met |
| Bob forgets CSRF | Valid | Missing | Has `docs:write` | **403** | CSRF precedes authorization |
| Bob sends wrong CSRF | Valid | Invalid | Has `docs:write` | **403** | CSRF fails |
| Alice creates document | Valid | Valid | Lacks `docs:write` | **403** | Authorization denies |
| Alice forgets CSRF | Valid | Missing | Lacks permission | **403** | Status alone cannot tell both are missing; CSRF blocks first |
| Carol has admin role | Valid | Valid | Only `ROLE_ADMIN` | **403** | Admin role does not imply literal permission |
| Anonymous with CSRF | None | Valid | None | **401** | After passing CSRF, protected endpoint requires authentication |
| Anonymous without CSRF | None | Missing | None | **403** | CSRF can block before HTTP Basic |

**Scientific verification rule:** to prove an error is **insufficient permission**, keep other factors valid (especially CSRF) and vary **only the authority**. To prove an error is due to **CSRF**, keep an identity with sufficient permission and vary **only the token**.

When both permission and CSRF are wrong, status code alone cannot diagnose the root cause; separate the variables in tests or use permitted tracing/logs.

## 7. Plain Java 17: Modeling Interception Order

This is a **standalone** example without Spring Security. The goal is distinguishing the **decision layer**: a 403 at step 1 differs from a 403 at step 3.

Create file **`CsrfVsAuthDemo.java`**:

~~~java
public class CsrfVsAuthDemo {

    static String decide(
            boolean csrfRequired,
            boolean validCsrf,
            boolean authenticated,
            boolean canWrite
    ) {
        if (csrfRequired && !validCsrf) {
            return "403 CSRF";
        }
        if (!authenticated) {
            return "401 AUTHENTICATION";
        }
        if (!canWrite) {
            return "403 AUTHORIZATION";
        }
        return "201 CREATED";
    }

    public static void main(String[] args) {
        System.out.println("Bob valid: "
            + decide(true, true, true, true));

        System.out.println("Bob missing token: "
            + decide(true, false, true, true));

        System.out.println("Alice valid token: "
            + decide(true, true, true, false));

        System.out.println("Alice missing token: "
            + decide(true, false, true, false));

        System.out.println("Anonymous valid token: "
            + decide(true, true, false, false));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac CsrfVsAuthDemo.java
java CsrfVsAuthDemo
~~~

**Exact stdout:**

~~~text
Bob valid: 201 CREATED
Bob missing token: 403 CSRF
Alice valid token: 403 AUTHORIZATION
Alice missing token: 403 CSRF
Anonymous valid token: 401 AUTHENTICATION
~~~

The program simulates a minimal pipeline and intentionally writes the cause into **internal output strings**. Real Spring Security does not promise to return strings `403 CSRF` or `403 AUTHORIZATION` in the HTTP response; it may just return the same 403 status. When adding extra filters, sessions, token repositories, or custom exception policies, exact ordering and responses must be tested per application.

## 8. Spring Boot Example: One API, Two Kinds of 403

### 8.1. Creating the Project

Create a Maven project using **Spring Boot 3.5.x**, Java 17+, and dependencies:

- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-test` in test scope;
- `spring-security-test` in test scope.

Use a single `SecurityFilterChain` for the entire demo to easily pinpoint the rejecting filter. HTTP Basic serves credential testing; real environments must use **HTTPS**. Never use demo passwords in production.

### 8.2. Complete Application Code

Create file **`src/main/java/com/example/csrfdiag/CsrfDiagnosisApplication.java`**:

~~~java
package com.example.csrfdiag;

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
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfDiagnosisApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfDiagnosisApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/info").permitAll()
                .requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/docs")
                    .hasAuthority("docs:read")
                .requestMatchers(HttpMethod.POST, "/api/docs")
                    .hasAuthority("docs:write")
                .requestMatchers(HttpMethod.POST, "/api/admin/review")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("docs:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("docs:read", "docs:write")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("ADMIN")
            .build();

        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol, dave);
    }

    @RestController
    static class Api {

        @GetMapping("/public/info")
        String publicInfo() {
            return "public info";
        }

        // Despite permitAll, POST is still subject to CSRF check.
        @PostMapping("/public/submit")
        String publicSubmit() {
            return "public submitted";
        }

        @GetMapping("/api/docs")
        String docs() {
            return "docs";
        }

        @PostMapping("/api/docs")
        ResponseEntity<String> createDoc() {
            // Demo does not write to database.
            return ResponseEntity.status(HttpStatus.CREATED)
                .body("doc created");
        }

        @PostMapping("/api/admin/review")
        String review() {
            return "reviewed";
        }

        @GetMapping("/api/profile")
        String profile(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/api/unlisted")
        String unlisted() {
            return "must not be reached";
        }
    }
}
~~~

**Configuration explanation:**

1. `.csrf(Customizer.withDefaults())` explicitly enables default CSRF protection. In this Servlet web configuration, CSRF is already enabled unless disabled/changed.
2. `GET /public/info` is a public endpoint needing no CSRF because GET is considered safe by default.
3. `POST /public/submit` has `permitAll()` yet **still requires a valid CSRF token**: this is an important distinguishing case.
4. `GET /api/docs` requires `docs:read` authority, needing no default CSRF token.
5. `POST /api/docs` requires **both valid CSRF and `docs:write`**.
6. `POST /api/admin/review` requires CSRF and `ROLE_ADMIN` due to `hasRole("ADMIN")`.
7. `GET /api/profile` requires login without extra business permissions.
8. `anyRequest().denyAll()` blocks unlisted routes, including `GET /api/unlisted` even though the controller exists.
9. User builder `roles("ADMIN")` grants `ROLE_ADMIN` to Carol; that does **not** grant `docs:write`.
10. All POSTs return demo responses only and write no data. If a controller uses a DB, resource-level authorization, input validation, transactions, and auditing remain necessary.

### 8.3. Expectations When Sending GET Requests

Run with Maven wrapper:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Once the server opens `http://localhost:8080`:

~~~bash
curl -i http://localhost:8080/public/info
curl -i http://localhost:8080/api/docs
curl -i -u alice:demo123 http://localhost:8080/api/docs
curl -i -u dave:demo000 http://localhost:8080/api/docs
curl -i -u dave:demo000 http://localhost:8080/api/profile
curl -i -u bob:demo456 http://localhost:8080/api/unlisted
~~~

| Request | Expectation |
| --- | --- |
| Public GET, anonymous | `200`, body `public info` |
| Docs GET, anonymous | `401` (HTTP Basic) |
| Docs GET, Alice | `200`, body `docs` |
| Docs GET, Dave | `403` due to missing `docs:read`, **not CSRF** |
| Profile GET, Dave | `200`, body `dave` |
| Unlisted GET, Bob | `403` due to `denyAll()`, **not CSRF** |

**GET can also receive 403 due to insufficient permission** while default CSRF does not check it. Thus, "every 403 is CSRF" is just as wrong as "every 403 is role".

### 8.4. Why Does a Simple curl POST Command Not Prove Permissions?

~~~bash
curl -i -u bob:demo456 -X POST http://localhost:8080/api/docs
~~~

The request above **has no CSRF token**, so even though Bob has `docs:write`, the normal result is **403 from CsrfFilter**. Do not fix this by granting `ROLE_ADMIN` or `docs:write` to Bob: he already has the needed permission!

With the default repository storing tokens in the session and Spring Security 6's token protection, using curl requires following the client/server flow to fetch the token, preserve the corresponding session/cookie, and submit the token properly. A `curl -u ... -X POST` command lacking CSRF cannot be treated as a complete authorization test.

To **isolate the variables**, the next section uses `MockMvc` and `spring-security-test`. The `csrf()` helper supplies a valid token in tests, not a way to bypass CSRF in a real app.

## 9. Spring Security Test: Proving Cause via Controlled Experiments

### 9.1. Test Dependencies

In `pom.xml`, ensure you have:

~~~xml
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
~~~

These elements belong inside `<dependencies>` in the POM. If `spring-boot-starter-test` is already present, do not duplicate it. The Spring Boot parent/BOM should manage versions of related artifacts.

### 9.2. Complete Test Class

Create file **`src/test/java/com/example/csrfdiag/CsrfDiagnosisTests.java`**:

~~~java
package com.example.csrfdiag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDiagnosisTests {

    @Autowired
    MockMvc mvc;

    @Test
    void writerWithValidCsrfCanCreate() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("doc created"));
    }

    @Test
    void sameWriterWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void sameWriterWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithValidCsrfStillCannotCreate() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("alice", "demo123"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWithValidCsrfNeedsAuthentication() throws Exception {
        mvc.perform(post("/api/docs")
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousWithoutCsrfCanGetCsrfForbiddenFirst() throws Exception {
        mvc.perform(post("/api/docs"))
            .andExpect(status().isForbidden());
    }

    @Test
    void permitAllDoesNotSkipCsrf() throws Exception {
        mvc.perform(post("/public/submit"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/public/submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("public submitted"));
    }

    @Test
    void correctAuthorityAndInvalidCsrfHeaderStillFail()
            throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf().asHeader().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfHeaderAndCorrectAuthoritySucceed()
            throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "demo456"))
                .with(csrf().asHeader()))
            .andExpect(status().isCreated());
    }

    @Test
    void getDoesNotNeedCsrfButStillNeedsReadAuthority()
            throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/docs")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isForbidden());
    }

    @Test
    void badPasswordWithValidCsrfIsUnauthorized() throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("bob", "wrong-password"))
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRoleDoesNotImplyDocsWritePermission()
            throws Exception {
        mvc.perform(post("/api/docs")
                .with(httpBasic("carol", "demo789"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/admin/review")
                .with(httpBasic("carol", "demo789"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("reviewed"));
    }

    @ParameterizedTest
    @CsvSource({
        // principal,password,method,path,expected HTTP status
        "anonymous,none,GET,/public/info,200",
        "anonymous,none,GET,/api/docs,401",
        "anonymous,none,POST,/public/submit,200",
        "anonymous,none,POST,/api/docs,401",
        "alice,demo123,GET,/api/docs,200",
        "alice,demo123,POST,/api/docs,403",
        "bob,demo456,GET,/api/docs,200",
        "bob,demo456,POST,/api/docs,201",
        "carol,demo789,GET,/api/docs,403",
        "carol,demo789,POST,/api/docs,403",
        "carol,demo789,POST,/api/admin/review,200",
        "dave,demo000,GET,/api/profile,200",
        "dave,demo000,GET,/api/docs,403",
        "dave,demo000,POST,/api/docs,403",
        "bob,demo456,GET,/api/unlisted,403"
    })
    void expectedAuthorizationWhenCsrfIsValid(
            String principal, String password,
            String method, String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder request =
            "POST".equals(method) ? post(path) : get(path);

        if (!"anonymous".equals(principal)) {
            request.with(httpBasic(principal, password));
        }

        // Keep CSRF valid to isolate permission checks.
        if ("POST".equals(method)) {
            request.with(csrf());
        }

        mvc.perform(request)
            .andExpect(status().is(expected));
    }
}
~~~

**Lessons from each experiment:**

- **Bob + valid token = 201**, the same Bob **missing token = 403** and **invalid token = 403** → proves the CSRF layer acts independently of `docs:write`.
- **Alice + valid token = 403** → once CSRF failure is eliminated, `docs:write` is still missing, so it is an authorization failure.
- **Anonymous + valid token = 401** on a protected endpoint → isolates the unauthenticated case.
- **`permitAll` + POST missing CSRF = 403**, yet `permitAll` + POST valid CSRF = 200 → `permitAll` does not disable `CsrfFilter`.
- **GET Alice = 200, GET Dave = 403** even without CSRF → pure authorization failure on a safe method.
- **Carol `ROLE_ADMIN`** only accesses admin POST, lacking `docs:write` → roles are not conflated with permissions.
- The matrix test injects a **valid token** into every POST to compare policies fairly; missing/invalid token tests are kept separate.

`@SpringBootTest` and `@AutoConfigureMockMvc` use the application's real web/security configuration inside the test environment. `httpBasic` adds the Basic header to the request; `csrf()` is a `RequestPostProcessor` helping generate a valid test token. This test does not open a TCP server like curl, and results will reflect any additional filter chains, exception handlers, or configurations added to the project.

### 9.3. Running and Verifying

~~~bash
# macOS/Linux
./mvnw test

# Windows PowerShell / Command Prompt
mvnw.cmd test
~~~

Expectation: all tests pass, Maven exits with code 0, with no failures/errors. Log output, timestamps, and duration depend on the environment. Never fabricate passing logs without actually running the tests.

**A single 403 test does not prove the cause.** Value lies in test pairs differing by **one variable** (token or authority), combined with knowledge of filter order and log evidence.

## 10. Why Can You Not Conclude from the Response Body or Headers?

An application may customize `AccessDeniedHandler`, `AuthenticationEntryPoint`, error controllers, reverse proxies, or API error envelopes. Then both CSRF and authorization can return:

~~~json
{"status":403,"message":"Forbidden"}
~~~

The body above **does not state the cause**. Conversely, if an application deliberately returns internal error codes like `CSRF_MISSING` or `PERMISSION_DENIED`, that is trustworthy only if designed and tested on the server. Do not infer from frontend-chosen field names or a generic error body.

### Distinguishing 401 and 403 in Context

- **401**: usually missing/invalid authentication, and the server may send `WWW-Authenticate` with HTTP Basic.
- **403**: the request reached a denial mechanism; could be CSRF, missing permission, role, account policy, method security, or another filter.
- **302 redirect**: common with form login when authentication is required.
- **404 or 403**: an app may intentionally hide the existence of sensitive resources depending on design.
- **5xx**: technical failures of a permission-checking service must fail closed; never turn them into ALLOW.

HTTP status helps point the investigation, **without replacing server-side inspection**.

## 11. Procedure for Debugging 403 in a Real Application

When the frontend reports "logged in yet POST still returns 403", diagnose in this order:

1. **Capture request details** in an appropriate environment: method, URL after reverse proxy, context path, content type, whether cookie/session is present, whether CSRF header is present, auth type, timestamp/correlation ID. **Never log plaintext passwords, session IDs, or real tokens.**
2. **Identify the first matching SecurityFilterChain** for the URL. With multiple chains, each chain can configure `csrf`, `httpBasic`, `formLogin`, and authorization differently.
3. **Check whether the request falls under CSRF requirements.** By default POST/PUT/PATCH/DELETE require a token; GET does not, though custom matchers can change this.
4. **Read controlled logs** for `org.springframework.security.web.csrf.CsrfFilter` and package `org.springframework.security`. Enable DEBUG/TRACE temporarily only in suitable environments; prevent logs from leaking secrets.
5. **If suspecting CSRF:** inspect token repository (session/cookie), header/parameter name, session cookie accompanying the request, token refresh after login/logout, SPA request handler, and BREACH/XOR handling if any.
6. **If CSRF passed:** inspect authentication (principal, whether authenticated successfully) and **actual authorities** in `Authentication#getAuthorities()`. Compare against `hasRole/hasAuthority` policy, exact prefixes, and HTTP method.
7. **Check the first matching rule** in `authorizeHttpRequests`, including `denyAll` fallback. A broad rule placed before a sensitive rule can yield wrong outcomes.
8. **Check method/domain layers:** `@PreAuthorize`, tenant, ownership, record status, policy services, CORS, CSRF, and custom filters can all deny independently.
9. **Write controlled-comparison tests:** keep user with sufficient permission yet missing/invalid token; keep valid token yet user lacking permission; test anonymous with valid token; test GET without token.
10. **Never fix by disabling CSRF or switching to `permitAll`** without evaluating the threat model and true cause.

### Table of Common Symptoms

| Observation | What to check first | Do not jump to conclusions |
| --- | --- | --- |
| GET with authorized user is 200, POST with same user is 403 | CSRF token and POST action permission | "Role was not granted" |
| POST with Bob missing token 403, adding valid token 201 | CSRF error | "Bob's permissions are flaky" |
| POST with Alice having valid token still 403 | `docs:write`, owner/tenant, rule order | "CSRF must be broken" |
| POST to `permitAll` still 403 | CSRF filter runs independently | "permitAll doesn't work" |
| Anonymous POST missing token 403 yet adding token gives 401 | CSRF precedes authentication | "403 always means authenticated" |
| Only SPA right after login/logout gets 403 | Stale token, cookie/session, handler, token rotation | "Grant user higher role" |
| Both GET and POST get 403 for account | Authorization, chain selection, custom filter | "CSRF is the only cause" |
| POST missing token still returns 201 | Was CSRF disabled/ignored? Different chain? | "So the system must be secure" |

## 12. Do Not Disable CSRF Arbitrarily — Nor Apply It Mechanically

CSRF is especially important when **the browser automatically sends credentials** to the server, such as session cookies. A REST API using bearer tokens actively attached by clients in the `Authorization` header has a different risk model; still, one should not say "REST never needs CSRF" or "JWT is automatically immune to CSRF" if the JWT is stored in a cookie and sent automatically with requests.

### 12.1. Cases Where a Narrow Exception May Be Considered

A server-to-server webhook verified by HMAC signature, using no browser auto-sent credentials, can be evaluated for **not needing CSRF** on that exact endpoint. Assess the threat model, signature verification, replay protection, and invalid-request rejection.

Example **fragment** configuring a narrow exception:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/api/webhooks/provider-a")
);
~~~

This snippet **must not** be applied unconditionally and is insufficient to protect the webhook without independent signature/authentication verification. In multi-chain apps, verify which chain receives the request. Never use an overly broad matcher like `/api/**` to skip CSRF if any endpoints inside are called from browsers with cookies.

### 12.2. Dangerous Wrong Fixes

~~~java
// Do not use as a universal "403 fix":
http.csrf(csrf -> csrf.disable());

// Do not use to work around missing permissions:
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll()
);
~~~

These two measures change **different protection layers** and can introduce vulnerabilities. When a CSRF token fails, fix token issuance/storage/submission or define exact request types permitted to omit CSRF. When permissions are missing, evaluate policy and grant permissions according to business logic rather than opening every endpoint.

### 12.3. Other Protections Do Not Replace CSRF or Authorization

- **CORS** governs response reading and certain cross-origin requests in browsers; proper CORS config **does not replace** CSRF protection.
- `SameSite`, `Secure`, and `HttpOnly` cookies reduce risk in some models, yet do not replace permission policies and require evaluating browser/client interactions.
- **HTTPS** protects the transport channel; it does not prove a request was intentionally sent by the victim.
- **Password/OTP/MFA** protect authentication; valid login does not prove every state-changing request was intentional.
- **CSRF tokens** do not prevent IDOR/BOLA: every object ID still requires permission, tenant/ownership, and data-scope checks.

## 13. Extending the Matrix for Applications with Real Data

After separating CSRF and authorization at HTTP, real apps must verify permissions on **specific resources**:

| Request | CSRF | Authentication | Permission | Domain constraint | Outcome |
| --- | --- | --- | --- | --- | --- |
| Bob POSTs new document | Valid | Bob | `docs:write` | Valid tenant | ALLOW |
| Bob POSTs new document | Missing | Bob | `docs:write` | Valid tenant | DENY at CSRF |
| Alice POSTs new document | Valid | Alice | Lacks `docs:write` | No further check needed | DENY at authorization |
| Bob PATCHes another tenant's document | Valid | Bob | Has `docs:write` | Different tenant | DENY at domain |
| Anonymous GETs private document | Not required | Anonymous | Unauthenticated | No need to check | Typically 401/redirect |
| Bob GETs private document after revocation | Not required | Bob | `docs:read` | Ownership/share grant revoked | DENY at domain |

When using `@PreAuthorize` or a custom `AuthorizationManager` for domain logic, keep instance- and tenant-level tests, not only type-level HTTP rule tests. For writes, check record state inside an appropriate transaction; for `LIST/SEARCH`, filter by permitted scope directly in the query to avoid leaking data via results or pagination.

This lesson focuses on distinguishing **the source of 403**, so the demo code intentionally omits tenant/ownership implementation. Do not interpret passing CSRF and `hasAuthority` tests as proof the application is comprehensively secure.

## 14. Self-Check Questions

**Question 1.** Bob has `docs:write`, sends a POST missing a CSRF token, and gets 403. Should we grant more roles?  
**Answer:** No. First check `CsrfFilter`, the token repository, and the client; permissions are already sufficient in the example.

**Question 2.** Alice has only `docs:read`, POST with a valid CSRF token still gets 403. First possibility?  
**Answer:** Missing `docs:write`; also check HTTP rules and domain policies. Do not blame CSRF once the token is verified.

**Question 3.** An anonymous POST hits `permitAll()` yet lacks a CSRF token; can it return 403?  
**Answer:** Yes. `permitAll` belongs to authorization and does not automatically exempt CSRF.

**Question 4.** Anonymous POST to a protected endpoint: missing CSRF → 403, valid CSRF → 401. Why?  
**Answer:** `CsrfFilter` can block before authentication; once past CSRF, HTTP Basic demands a valid identity.

**Question 5.** GET with logged-in Dave lacking `docs:read` returns 403; is it CSRF?  
**Answer:** Normally no, because GET does not require CSRF by default. This is a permission error or another blocking mechanism.

**Question 6.** In MockMvc, how do you supply a valid token and an invalid token?  
**Answer:** `.with(csrf())` and `.with(csrf().useInvalidToken())`; you can also test via header using `csrf().asHeader()`.

**Question 7.** With a valid CSRF token, can a user call any API?  
**Answer:** No. They must still be authenticated and hold the right permission/role, resource, and tenant.

**Question 8.** Every time an SPA finishes login/logout, the next POST gets 403. What to check?  
**Answer:** Token refresh/clearing, whether cookies/sessions changed, how the SPA fetches/sends the new token, repository, and request handler.

**Question 9.** Why shouldn't you look at response `{"status":403}` to conclude it is CSRF?  
**Answer:** Both CSRF and authorization can share 403 and the same error envelope. Use filter logs or controlled-comparison tests.

**Question 10.** Must a cookie-independent bearer-token API disable CSRF?  
**Answer:** No. Evaluate whether the browser sends credentials automatically, cookie/token storage, client flows, and threat model. Never decide from the API name alone.

**Question 11.** Carol has `ROLE_ADMIN` without `docs:write`; is a POST with valid CSRF allowed?  
**Answer:** Not in the example; `hasAuthority("docs:write")` checks the exact string and does not assume admin holds every permission.

**Question 12.** Can you prove an authorization error using a POST request missing CSRF?  
**Answer:** No. Supply a valid token and compare users with and without permission; otherwise CSRF blocked before permissions were evaluated.

**Remember:** **403 is not a single cause**, it is an HTTP outcome. For state-changing requests, check **CSRF token**, then **authentication**, then **authorization** in the right filter/chain, and finally resource-specific policies. Controlled tests varying **one factor at a time** are the surest way to separate error sources.

## Official Documentation

- Spring Security 6.5 — Cross Site Request Forgery (CSRF): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — Servlet Architecture (order of `CsrfFilter`, authentication, and authorization): https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Security 6.5 — Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — `CsrfFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfFilter.html
- Spring Security 6.5 — `MissingCsrfTokenException` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/MissingCsrfTokenException.html
- Spring Security 6.5 — `InvalidCsrfTokenException` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/InvalidCsrfTokenException.html
