# Verifying a Minimal HTTP Configuration with a Permission Matrix — Spring Security

> **Goal:** Starting from a concise HTTP authorization configuration, build a **user × request × expected outcome matrix**, run allowed and denied scenarios, and automate verification with **Spring Security Test + MockMvc**. This article uses Java 17+, Spring Boot 3.x, and Spring Security 6.x on the Servlet stack; examples are learning apps and do not contain a production database or business logic.

## 1. Why use a permission matrix instead of just reading configuration?

An `authorizeHttpRequests` block can look completely reasonable yet still harbor serious bugs:

- Broad rule `/api/**.authenticated()` placed before `/api/admin/**.hasRole("ADMIN")`, letting ordinary users into admin APIs.
- Testing only that an admin calling an admin endpoint returns 200 without testing that an under-privileged user must get 403.
- Using `hasRole("ADMIN")` when real accounts only have authority `ADMIN` instead of `ROLE_ADMIN`.
- Guarding `GET` while letting `POST`/`DELETE` slip through an overly broad rule.
- Using `anyRequest().permitAll()` as fallback, causing new endpoints to become public automatically.
- Testing `POST` without CSRF and wrongly concluding 403 came from authorization; or conversely, disabling CSRF just to make tests pass.

**A permission matrix** is a test specification independent of configuration code:

`expected(subject, httpMethod, path, context) → ALLOW / DENY`.

Over HTTP, you must also predict the **status** and **response** based on authentication mechanism. For example, HTTP Basic usually yields **401** when credentials are absent on a protected endpoint, **403** with a valid identity lacking permission, and **2xx** when allowed. With form login, unauthenticated requests may **302 redirect**. Do not treat 401/403 as two kinds of roles; they are HTTP handling outcomes after authentication/authorization filters.

**A high-quality verification must answer all four questions:**

1. Which rule **is selected** for a specific request?
2. Which authorities does the user **actually have**?
3. Is the expected result **allow or deny**, including when unauthenticated?
4. Do tests detect cases of **unintended access expansion**?

## 2. Illustrative problem: reporting API with 4 permission groups

Suppose an application has these endpoints:

| Request | Meaning | HTTP rule |
| --- | --- | --- |
| `GET /public/ping` | Public health check | `permitAll()` |
| `GET /api/me` | View the caller's own identity | `authenticated()` |
| `GET /api/reports/summary` | View summary report | `hasAuthority("report:read")` |
| `POST /api/reports` | Create report draft | `hasAuthority("report:write")` |
| `GET /api/admin/audit` | View administrative area | `hasRole("ADMIN")` |
| `GET /api/unknown` | Endpoint without approved policy | `anyRequest().denyAll()` |

To isolate the topic, we **do not use OAuth2/JWT, a database, or multiple SecurityFilterChains**. Sample users have specific authorities:

| Subject | Actual authority list | Role in this article |
| --- | --- | --- |
| **Anonymous** | Unauthenticated, no granted authorities | Tests 401/public access |
| **Alice** | `report:read` | Read-only reports |
| **Bob** | `report:read`, `report:write` | Read and create reports |
| **Carol** | `ROLE_ADMIN` | Admin only; **does not automatically** read/write reports |
| **Dave** | `ROLE_USER` | Plain logged-in user |

**Carol intentionally has only `ROLE_ADMIN`**. In Spring Security, `hasRole("ADMIN")` checks `ROLE_ADMIN` under the default prefix, and `ROLE_ADMIN` does not automatically grant `report:read` or `report:write`. If admins also need business permissions, grant those authorities or configure appropriate inheritance/rules.

**Shared assumptions of this article:** HTTP Basic is enabled, and `POST` endpoints use default CSRF protection. When the matrix says `POST` "meets CSRF conditions," the request carries a **valid** CSRF token. Missing-token scenarios are tested separately rather than mixed with role/permission policy.

## 3. Building the permission matrix before writing tests

### 3.1. Business-level ALLOW / DENY matrix

With the identities from section 2:

| Subject | Public GET | Me GET | Summary GET | Reports POST* | Admin GET | Unknown GET |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Anonymous** | ALLOW | DENY | DENY | DENY | DENY | DENY |
| **Alice** | ALLOW | ALLOW | ALLOW | DENY | DENY | DENY |
| **Bob** | ALLOW | ALLOW | ALLOW | ALLOW | DENY | DENY |
| **Carol** | ALLOW | ALLOW | DENY | DENY | ALLOW | DENY |
| **Dave** | ALLOW | ALLOW | DENY | DENY | DENY | DENY |

`*` The `Reports POST` column assumes the request has a valid CSRF token, because testing **isolates authorization from CSRF**. Without a CSRF token, Spring Security can block `POST` **before** checking authorities. Never use a 403 from CSRF to conclude the `report:write` rule worked.

From this table we derive key security tests:

- Bob must be **allowed** `POST /api/reports` with valid CSRF; Alice must be **blocked** despite being logged in.
- Carol must be **allowed** to view admin, yet must be **blocked** on summary for lacking `report:read`.
- Dave must be **allowed** to view `/api/me` yet **denied** reports/admin.
- Any logged-in user calling `/api/unknown` is denied, proving the `denyAll()` fallback works.
- Anonymous can still call `/public/ping`; all remaining protected endpoints must deny.

### 3.2. Translating the matrix to HTTP statuses in the sample config

| Business outcome | Expected HTTP status in the example |
| --- | --- |
| Allowed `GET` | `200 OK` |
| Allowed report creation `POST` | `201 Created` — returned by the demo controller |
| Unauthenticated on protected API | `401 Unauthorized` — because HTTP Basic is used |
| Authenticated but lacking authority | `403 Forbidden` |
| Authenticated but hitting `denyAll()` rule | `403 Forbidden` |
| Sending `POST` without a valid CSRF token | `403 Forbidden` — **CSRF error**, does not prove authority check ran |

This is an **expected outcomes table specifically for the illustrative app**, not a claim that every Spring Security config yields these statuses. For endpoints without a controller, a denied URL can return 403 **before** Spring MVC returns 404. To verify the fallback reliably, we create an `/api/unknown` controller while still requiring security to block it.

### 3.3. The matrix should be a "contract" with the team

The matrix should be agreed upon **before** editing configuration; writing tests after observing current behavior risks blessing permission bugs as "expected outcomes." In particular, **negative tests** are as critical as positive tests. For example, putting an overly broad `authenticated()` first can still let many 200 tests pass, while 403 tests catch the bug.

When designing real APIs, you can add columns for `tenantId`, `ownerId`, data state, HTTP method, token type, permission expiration, and context conditions. The HTTP matrix here only tests **endpoint-level authorization**; it does not replace per-record permission checks.

## 4. Minimal `authorizeHttpRequests` configuration

Define in order: public → permission-protected sensitive endpoints → admin area → login-required endpoints → deny fallback.

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/reports/summary")
        .hasAuthority("report:read")
    .requestMatchers(HttpMethod.POST, "/api/reports")
        .hasAuthority("report:write")
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/me").authenticated()
    .anyRequest().denyAll()
);
~~~

This is a configuration **fragment** inside a `SecurityFilterChain`; complete code is in the next section.

**Explaining the exact order:**

1. `/public/ping` has an explicit ALLOW and needs no credentials.
2. `GET /api/reports/summary` requires the exact authority `report:read`.
3. `POST /api/reports` requires the exact authority `report:write`.
4. `/api/admin/**` via `hasRole("ADMIN")` requires `ROLE_ADMIN` in this example.
5. `/api/me` requires an authenticated identity.
6. `anyRequest().denyAll()` blocks URLs without a policy.

Spring Security evaluates `RequestMatcher → AuthorizationManager` pairs in **declaration order** and applies the **first matching rule**. There is no "try the next rule if the first rule denies" mechanism in this list. Therefore you **must not** put `requestMatchers("/api/**").authenticated()` before permission/admin rules: it could open all APIs too broadly to any logged-in user.

### Do not confuse similar-looking APIs

- `hasRole("ADMIN")`: matches role using the default `ROLE_` prefix convention.
- `hasAuthority("ROLE_ADMIN")`: matches the **literal** authority `ROLE_ADMIN`.
- `hasAuthority("report:read")`: matches **literal** `report:read`.
- `authenticated()`: authenticated user, **not** equivalent to having read/write permissions.
- `permitAll()`: intentionally opens a route; does not mean skipping the entire security filter chain.
- `denyAll()`: explicit denial.
- `anyRequest()`: fallback in the **currently selected `SecurityFilterChain`**, not an automatic policy across other chains.

## 5. Runnable Java 17+ Spring Boot application

**Create project:** use Spring Initializr or a Java 17+ compatible Spring Boot 3.x Maven project with dependencies:

- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-test` in test scope;
- `spring-security-test` in test scope to write `MockMvc` tests with `httpBasic()` and `csrf()` helpers.

There is no need to enable `@EnableMethodSecurity` because this example **only verifies HTTP authorization**. When using service-layer policies, design method/domain security separately.

Create file **`src/main/java/com/example/matrix/MatrixApplication.java`**:

~~~java
package com.example.matrix;

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
public class MatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatrixApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/summary")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("report:write")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Do not disable CSRF: POST in MockMvc tests will use csrf().
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("report:read", "report:write")
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
    static class DemoController {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/me")
        String me(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/api/reports/summary")
        String summary() {
            return "report summary";
        }

        @PostMapping("/api/reports")
        ResponseEntity<String> createReport() {
            // Illustrates permission check, does not persist a database record yet.
            return ResponseEntity.status(HttpStatus.CREATED)
                .body("report created");
        }

        @GetMapping("/api/admin/audit")
        String audit() {
            return "audit log";
        }

        @GetMapping("/api/unknown")
        String unknown() {
            // Real controller exists, yet must be blocked by denyAll() in security.
            return "must not be reached";
        }
    }
}
~~~

**Reading the authority grants:**

- Alice is created with `authorities("report:read")`, so she lacks `report:write` and `ROLE_ADMIN`.
- Bob has both `report:read` and `report:write`.
- Carol uses builder `roles("ADMIN")`, receiving `ROLE_ADMIN` per default prefix without automatically gaining report permissions.
- Dave uses `roles("USER")`, having only `ROLE_USER`.
- `httpBasic()` allows sending credentials via Basic header for the demo. Real applications must use HTTPS and never hard-code passwords.
- `PasswordEncoder` is BCrypt to store and match demo passwords properly.
- `anyRequest().denyAll()` blocks `/api/unknown` even though the controller exists.
- Spring Security has default CSRF protection in this Servlet setup. Hence a `POST` from `curl` lacking a CSRF token can return 403 even though Bob has `report:write`. We will use `MockMvc` with `csrf()` to verify permissions in a controlled way.

### Which outcome belongs to authorization, and which to the controller?

A `hasAuthority` rule yields **ALLOW** for Bob on `POST /api/reports`, yet the rule itself does not produce status 201. The `createReport()` controller is what **picks `201 Created`**. If the controller throws an exception or fails validation, the response may not be 201 even though authorization returned ALLOW. Thus permission tests should combine assertions on **status + body/side effects**, without confusing business constraints with HTTP policy.

## 6. Running manually: GETs first

From the Maven project root directory:

~~~bash
# macOS / Linux:
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt:
mvnw.cmd spring-boot:run
~~~

Once the app runs at `http://localhost:8080`:

~~~bash
# Public
curl -i http://localhost:8080/public/ping

# Anonymous => 401 on login-required endpoints
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/reports/summary

# User with read permission vs user without read permission
curl -i -u alice:demo123 http://localhost:8080/api/reports/summary
curl -i -u dave:demo000 http://localhost:8080/api/reports/summary

# Admin succeeds, ordinary user denied
curl -i -u carol:demo789 http://localhost:8080/api/admin/audit
curl -i -u bob:demo456 http://localhost:8080/api/admin/audit

# Fallback denyAll
curl -i -u carol:demo789 http://localhost:8080/api/unknown
~~~

Expected:

| Corresponding command | Status / body |
| --- | --- |
| Public anonymous | `200` / `pong` |
| `/api/me` anonymous | `401` |
| Summary anonymous | `401` |
| Summary Alice | `200` / `report summary` |
| Summary Dave | `403` |
| Admin Carol | `200` / `audit log` |
| Admin Bob | `403` |
| Unknown Carol | `403` |

### Why not use `curl -u bob:... -X POST` as sole evidence?

Because CSRF protection is enabled. On a POST request without a valid CSRF token, Spring Security can return **403 before reaching `AuthorizationFilter`**. That outcome **does not prove Bob lacks `report:write`**. The right testing approach is using `MockMvc` + `with(csrf())` to eliminate the confounding variable, then verifying 201 for Bob and 403 for under-privileged users.

**In production**, how CSRF tokens are supplied depends on the application (session/cookie/token repository and client). Do not disable CSRF globally just to make `curl` requests pass easily. For stateless token-based APIs, decide on enabling/disabling CSRF based on threat modeling and browser auto-credential behavior, not on slogans like "REST has no CSRF."

## 7. Automating the matrix with MockMvc and HTTP Basic

### 7.1. Adding test dependencies

Check that `pom.xml` already includes `spring-boot-starter-test` (usually added by Initializr when test is selected). Add `spring-security-test` with the compatible version managed by Boot's Spring Security BOM:

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

These dependency snippets are **child elements of `<dependencies>` in `pom.xml`**, not a complete XML file. If the project already has starter-test, do not duplicate it.

### 7.2. Complete test class running with the application

Create file **`src/test/java/com/example/matrix/HttpAuthorizationMatrixTest.java`**:

~~~java
package com.example.matrix;

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
class HttpAuthorizationMatrixTest {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest(name = "{index}: {0} {2} {3} -> {4}")
    @CsvSource({
        // username, password, method, path, expected HTTP status
        "anonymous,none,GET,/public/ping,200",
        "anonymous,none,GET,/api/me,401",
        "anonymous,none,GET,/api/reports/summary,401",
        "anonymous,none,POST,/api/reports,401",
        "anonymous,none,GET,/api/admin/audit,401",
        "anonymous,none,GET,/api/unknown,401",

        "alice,demo123,GET,/public/ping,200",
        "alice,demo123,GET,/api/me,200",
        "alice,demo123,GET,/api/reports/summary,200",
        "alice,demo123,POST,/api/reports,403",
        "alice,demo123,GET,/api/admin/audit,403",
        "alice,demo123,GET,/api/unknown,403",

        "bob,demo456,GET,/public/ping,200",
        "bob,demo456,GET,/api/me,200",
        "bob,demo456,GET,/api/reports/summary,200",
        "bob,demo456,POST,/api/reports,201",
        "bob,demo456,GET,/api/admin/audit,403",
        "bob,demo456,GET,/api/unknown,403",

        "carol,demo789,GET,/public/ping,200",
        "carol,demo789,GET,/api/me,200",
        "carol,demo789,GET,/api/reports/summary,403",
        "carol,demo789,POST,/api/reports,403",
        "carol,demo789,GET,/api/admin/audit,200",
        "carol,demo789,GET,/api/unknown,403",

        "dave,demo000,GET,/public/ping,200",
        "dave,demo000,GET,/api/me,200",
        "dave,demo000,GET,/api/reports/summary,403",
        "dave,demo000,POST,/api/reports,403",
        "dave,demo000,GET,/api/admin/audit,403",
        "dave,demo000,GET,/api/unknown,403"
    })
    void fullMatrix(
            String username,
            String password,
            String httpMethod,
            String path,
            int expectedStatus
    ) throws Exception {
        MockHttpServletRequestBuilder request =
            "POST".equals(httpMethod) ? post(path) : get(path);

        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }

        // Valid token to measure POST permission without confusing CSRF 403.
        if ("POST".equals(httpMethod)) {
            request.with(csrf());
        }

        mvc.perform(request)
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void bobCanCreateWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("bob", "demo456"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("report created"));
    }

    @Test
    void bobPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("bob", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminDoesNotAutomaticallyHaveReportPermission() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void fallbackDeniesEvenAnAdmin() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedEndpointReturnsPrincipal() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("dave", "demo000")))
            .andExpect(status().isOk())
            .andExpect(content().string("dave"));
    }

    @Test
    void unexpectedMethodOnReportCollectionIsDenied() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Why choose `httpBasic()` instead of only `@WithMockUser`?** `httpBasic()` sends a Basic header in the MockMvc request so the configured authentication with demo users actually participates in granting `GrantedAuthority`s. `@WithMockUser` is very handy for testing individual rules, yet it does not verify the password encoder or `UserDetailsService` authority mapping. Both techniques have their place; for this article, testing via sample credentials builds higher confidence.

**Test notes:** `MockMvc` passes through the Spring Security filter chain without opening a TCP server like `curl`. `csrf()` supplies a valid request token for testing; it does **not** mean production clients can forge tokens. The 401/403 assertions assume the **sample application's** HTTP Basic configuration and Spring Security filter chain.

### 7.3. Running the tests

~~~bash
# macOS / Linux
./mvnw test

# Windows PowerShell / Command Prompt
mvnw.cmd test
~~~

With the proper dependencies and test class and no other edits, all matrix cases **are expected to pass**. To confirm the case count, `@CsvSource` contains **30 rows** (5 subjects × 6 requests), plus 7 additional `@Test` methods. Do not rely on a fixed displayed total count if different Maven Surefire/JUnit versions format reports differently; inspect individual case results and the exit code.

**Do not fabricate test output:** the demo omits fixed timestamps, execution durations, dependency versions, and log line counts. After running for real, **exit code 0** and a report with zero failed/error tests constitute the primary proof.

## 8. Reading each matrix row as evidence

Even when an entire test table passes, you still need to know **why** each result matters.

### 8.1. Anonymous on public and protected routes

- Anonymous calls `GET /public/ping` → **200** due to `permitAll()`.
- Anonymous calls `GET /api/me` → **401** due to `authenticated()` with HTTP Basic.
- Anonymous calls `GET /api/reports/summary` → **401** because there is no valid identity to check `report:read`.
- Anonymous calls `POST /api/reports` in the test with `csrf()` → **401**, observing authentication/authorization rather than CSRF.
- Anonymous calls `/api/unknown` → hits `denyAll()`. With HTTP Basic, `ExceptionTranslationFilter` can invoke the entry point for anonymous callers, yielding **401**; on authenticated accounts, this case is checked separately and returns **403**.

### 8.2. Alice and Bob: testing specialized permissions

- Alice has `report:read` → Summary GET **200**.
- Alice lacks `report:write` → Reports POST **403** (even with a valid CSRF token).
- Bob has both → Summary GET **200** and Reports POST **201**.
- Bob calls Reports POST **without** a CSRF token → **403**; this is why a test observing only 403 can mislead. You need **Bob + valid CSRF = 201** to prove the write rule works.

### 8.3. Carol: admin does not automatically hold all permissions

- Carol `ROLE_ADMIN` → Admin GET **200**.
- Carol lacks `report:read` → Summary GET **403**.
- Carol lacks `report:write` → Reports POST **403**.

This protects the system from assuming "admin always has every permission" when policy has not defined it that way. If business needs admins to read reports, **grant the authority explicitly** or design a tested combined rule rather than inserting `permitAll()`.

### 8.4. Dave: login does not equal business permissions

- Dave has `ROLE_USER` → `GET /api/me` **200**.
- Dave lacks `report:read`, `report:write`, and `ROLE_ADMIN` → all three sensitive API groups return **403**.

If Dave unexpectedly gets 200 on Summary, likely a broad `/api/**.authenticated()` matcher shadowed the report rule or another config granted wrong permissions.

### 8.5. Fallback

`GET /api/unknown` has a controller yet **no permit rule**: every authenticated user must get **403** thanks to `anyRequest().denyAll()`. That is an especially critical test guarding against future new routes added by the team.

## 9. Checking rule ordering and shadowing risk

An error-prone configuration:

~~~java
// DO NOT USE — solely to recognize the bug.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/reports/summary")
        .hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

Putting `/api/**.authenticated()` first causes:

- Logged-in Dave to pass the HTTP check for `/api/admin/audit`.
- Logged-in Dave to pass the HTTP check for Summary GET.
- Admin/report rules below to become **unreachable** for those requests.

**Negative tests** `Dave Summary GET = 403` and `Dave Admin GET = 403` catch this regression immediately. Tests like "Bob Summary = 200" or "Carol Admin = 200" are **insufficient** to detect the bug.

Another broken variant:

~~~java
// DO NOT USE: fallback allows everything.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/ping").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().permitAll()
);
~~~

If configured this way, `/api/unknown` and any undeclared route get **ALLOW**. Fallback tests for users and anonymous callers will catch this bug.

**Review rule:** whenever a broader matcher can match the same request as a specific matcher, put the specific rule first or clarify the design. Spring Security does not automatically choose the "nicest" matcher; it **applies the first match**.

## 10. Testing by HTTP method: GET and POST are not equivalent

Two requests sharing a prefix can need totally different permissions:

| HTTP request | Business action | Required authority |
| --- | --- | --- |
| `GET /api/reports/summary` | Read summary | `report:read` |
| `POST /api/reports` | Create report | `report:write` |
| `GET /api/reports` | Undeclared in this article | Fallback DENY |
| `DELETE /api/reports/42` | Not yet permitted | Fallback DENY |

**Do not replace method-specific rules with `requestMatchers("/api/reports/**").authenticated()` above them.** Because matching that broad pattern first lets merely logged-in users pass through the entire HTTP authorization flow.

For real write operations, you generally also need:

- Checking whether the user has permission on the **resource instance** (tenant, owner, status).
- CSRF if authenticating via session/cookie and the browser auto-sends credentials.
- Input validation, idempotency/transactions, auditing, race-condition protection, and not leaking data through errors.
- Testing all relevant methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, including unsupported methods.

In the demo, `POST` returns 201 without **persisting data**. Do not interpret the example as a production reporting service.

## 11. Testing 403 from CSRF vs 403 from missing permission

In Spring Security Servlet, the CSRF filter usually handles HTTP methods not considered "safe." A request such as:

~~~bash
curl -i -u bob:demo456 -X POST http://localhost:8080/api/reports
~~~

can return **403** for lacking a valid CSRF token, **even though** Bob has `report:write`. Looking only at status and concluding "Bob lacks permission" confuses a **request-protection filter** with an **authorization rule**.

Two tests serve different purposes:

~~~java
// Permission test: supply a valid CSRF token.
mvc.perform(post("/api/reports")
        .with(httpBasic("bob", "demo456"))
        .with(csrf()))
    .andExpect(status().isCreated());

// CSRF test: intentionally omit token.
mvc.perform(post("/api/reports")
        .with(httpBasic("bob", "demo456")))
    .andExpect(status().isForbidden());
~~~

A good test suite needs both **Bob with token succeeding creation** and **Alice with token yet lacking authority being blocked**. The tokenless test only proves CSRF protection is active.

For APIs not using cookies/sessions where clients explicitly attach bearer tokens in headers, the threat model can differ. Never disable CSRF application-wide just because you are using REST; evaluate credential sources and browser support.

## 12. Real-world matrix: separating HTTP, method, and data

Suppose a user with `report:read` calls `GET /api/reports/{id}`. HTTP may return **ALLOW** for the endpoint type, yet the user must not necessarily read **every report**. Multi-layered protection model:

~~~text
Request GET /api/reports/42
    |
    v
HTTP authorization: authenticated + report:read?
    |  DENY -> block
    v  ALLOW
Method/domain authorization: does report 42 belong to a valid tenant/owner?
    |  DENY -> block
    v  ALLOW
Load/read permitted data -> Response
~~~

If the app has multi-tenancy or sensitive data, expand the test matrix:

| User | Permission | Report | Tenant/owner | Expected |
| --- | --- | --- | --- | --- |
| Alice | `report:read` | Report 42 | Same tenant and shared | ALLOW |
| Alice | `report:read` | Report 99 | Different tenant | DENY |
| Dave | Lacks `report:read` | Report 42 | Even same tenant | DENY |
| Bob | `report:write` | Report 42 | Locked state | DENY for edits if policy forbids |

The sample config **does not automatically perform** tenant/owner/state checks. This is an **extension direction**; do not assume the HTTP matrix verified per-record authorization.

For `LIST/SEARCH`, filter data scope directly in the query; blocking a single ID only after loading the whole list can leak data through results, pagination, or record counts.

## 13. When there are multiple SecurityFilterChains

The sample article uses **one chain** to keep the proof simple. With multiple chains, there are **two first-match layers**:

1. `FilterChainProxy` selects the **first `SecurityFilterChain`** whose matcher matches the request, evaluated in priority order such as `@Order`.
2. Inside the selected chain, `AuthorizationFilter` applies the **first matching rule** of `authorizeHttpRequests`.

`http.securityMatcher("/api/**")` limits the scope of **the whole chain**; whereas `authorizeHttpRequests().requestMatchers("/api/admin/**")` only classifies requests **inside the already-selected chain**.

If you only have a `securityMatcher("/api/**")` chain, other URLs may go unprotected by Spring Security if no fallback chain exists. `anyRequest().denyAll()` inside the API chain **does not cover** URLs outside `/api/**`.

When scaling a real app to multiple chains, add a **Selected Chain** column to the matrix and write integration tests for URLs matching both chains, only one chain, or neither chain. Never assume chains "add permissions together" for the same request.

## 14. A repeatable review workflow

To verify a new HTTP config or after any change:

1. **List endpoints and methods**: public, login, resource read/write, admin, fallback.
2. **List sample identities**: anonymous, regular user, read-only, writer, admin; specify literal authorities.
3. **Lock down the ALLOW/DENY matrix** with business and security owners **before writing tests**.
4. **Translate into expected statuses** for the active auth mechanism; separate CSRF, validation, and controller responses.
5. **Write specific rules first, deny fallback last**; avoid duplicate or overly broad matchers.
6. **Write positive and negative tests** across every matcher intersection.
7. **Intentionally misorder rules** on a scratch branch or local test to confirm negative tests catch the bug (*mutation thought experiment*); never deploy broken config.
8. **Re-run the suite** whenever adding endpoints, roles, permissions, filter chains, or changing authentication mechanisms.
9. **Inspect test failure logs** to distinguish failures from HTTP authorization, authentication, CSRF, controllers, and domain policies.
10. **Never change expectations just to turn tests green**: every matrix change must be approved by business policy.

### Quick checklist

- Does every critical endpoint have a suitable matcher without shadowed ordering?
- Are `ROLE_ADMIN` and `report:read`/`report:write` granted exactly as tabulated?
- Do public routes have intentional `permitAll()` with no `denyAll()` ahead of them?
- Are new/undeclared endpoints denied by the fallback?
- Are anonymous, 401, wrong password, 403 missing role/authority, and valid 200/201 all tested?
- For POST, are both **valid CSRF** and **missing CSRF** tested?
- Is it tested that the admin role does **not** automatically hold all permissions?
- Is there extra tenant/owner protection for sensitive data?
- If multiple filter chains exist, do we know which chain is selected?
- Are sample data and passwords kept separate from production config?

## 15. Self-assessment

**Question 1.** Dave is logged in and has only `ROLE_USER`. What is expected for `GET /api/me`?  
**Answer:** **200**, because the `authenticated()` rule requires no other business permission.

**Question 2.** Dave calls `GET /api/reports/summary`?  
**Answer:** **403**, for lacking `report:read`, even though logged in.

**Question 3.** Carol has `ROLE_ADMIN`. Can Carol automatically call `POST /api/reports`?  
**Answer:** **No** under the sample policy; `report:write` is a separate authority that has not been granted.

**Question 4.** Bob sends a POST with the right `report:write` yet lacks a CSRF token?  
**Answer:** **403** can come from the CSRF filter; you cannot conclude the write permission is wrong. Supply a valid CSRF token when verifying authorization.

**Question 5.** Anonymous calls `/api/reports/summary` under HTTP Basic?  
**Answer:** **401**, because protected routes need authentication to evaluate authorities.

**Question 6.** A `/api/unknown` controller exists without an allow rule. Can it be accessed?  
**Answer:** No. `anyRequest().denyAll()` blocks it; for authenticated users, this example returns **403**.

**Question 7.** What happens if `requestMatchers("/api/**").authenticated()` is placed before `/api/admin/**.hasRole("ADMIN")`?  
**Answer:** The admin rule is shadowed; ordinary logged-in users can pass the HTTP authorization layer for the admin area.

**Question 8.** Why is testing "Carol reaches admin = 200" insufficient?  
**Answer:** Because an overly broad rule would also give Carol 200; you must test "Bob/Dave reaching admin = 403" to prove only admins are allowed.

**Question 9.** Do `@WithMockUser(authorities = "report:read")` and `httpBasic("alice","demo123")` prove the exact same thing?  
**Answer:** Not entirely. Mock users pre-build Authentication; HTTP Basic goes through credential processing and the user/authority source. Combine both testing styles sensibly.

**Question 10.** Has the HTTP matrix already proved Alice can only read reports belonging to her own tenant?  
**Answer:** Not yet. HTTP rules control endpoints/permissions. You must add data-level checks and tests by tenant/ownership for resource instances.

**Remember:** **The permission matrix is the test contract for HTTP authorization**. Correct configuration requires properly ordered matchers, explicit authorities, default deny, and tests for both **proper ALLOW** and **proper DENY**. For `POST`, permission verification must be **isolated from CSRF** to avoid false conclusions.

## Official documentation

- Spring Security — Authorize HTTP Requests (first-match, authorization methods, and default deny): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Test with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Java Configuration (`SecurityFilterChain` and `securityMatcher`): https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Method Security (protecting business logic behind HTTP): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
