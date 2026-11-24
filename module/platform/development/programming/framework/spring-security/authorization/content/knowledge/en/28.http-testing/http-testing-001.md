# Translating an Authorization Matrix into Allow and Deny Cases in HTTP Testing

A Spring Security application can have multiple types of users and multiple endpoints: viewers can read, editors can create, administrators can delete. If we only test one successful request per API, it is easy to miss situations where **an unauthorized user can still access it**. Conversely, only testing `403 Forbidden` does not prove that an authorized user can actually use the feature.

A systematic approach is to translate the **authorization matrix** into a suite of HTTP test cases with independent expectations: which requests are **allowed**, which requests are **denied**, what **status** they receive, and whether any **data mutation** occurs.

This lesson focuses on **Spring Security authorization at the Servlet/MVC layer**, using Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5, and MockMvc. The examples build a small runnable application with integration tests; they then explain how to extend this to resource-level, tenant-level, and real-world endpoint permissions.

## 1. Understanding the Authorization Matrix Before Writing Tests

A row in an authorization matrix is not just "role A calls endpoint B". Expectations are affected by the following dimensions:

| Test dimension | Question to lock down |
| --- | --- |
| Actor | Is the request anonymous, `READER`, `EDITOR`, `ADMIN`, a service account, or an expired token? |
| HTTP method | Do `GET`, `POST`, `PUT`, `PATCH`, `DELETE` have separate rules? |
| Path/resource | Which record does `/api/docs/{id}` point to; who is the owner/tenant? |
| Authentication | Valid credentials, no credentials, invalid, or expired? |
| Authority and role | Does it use `DOC_READ`, `DOC_WRITE`, `DOC_ADMIN`, or `ROLE_ADMIN`? |
| Context | What state is the resource in; does the subject own it; is it the same tenant? |
| Expected decision | Allow or deny according to **business requirements**? |
| HTTP status/contract | When allowed: 200/201/204; when denied: 401/403 or a 404 policy hiding existence? |
| Side effects | Does a denied request create, modify, delete data, or emit events? |

**The matrix must originate from approved permission requirements**, not by copying the current `SecurityFilterChain` logic and treating that result as truth. If tests derive expectations from the very rule under test, a faulty rule change can cause both the logic and the tests to be wrong at the same time while still passing.

In Spring Security:

- `hasAuthority("DOC_WRITE")` checks for the exact authority named `DOC_WRITE`.
- `hasRole("ADMIN")` normally checks for the authority `ROLE_ADMIN`, not the authority `ADMIN`.
- `ROLE_ADMIN` **does not automatically imply** `DOC_READ` or `DOC_WRITE` unless the application grants those authorities or explicitly configures an inheritance mechanism.
- An unauthenticated request to a resource requiring login typically receives **401** in HTTP Basic/Bearer REST APIs (or a redirect when using form login); an authenticated request lacking permission typically receives **403**.
- `AccessDeniedException` does not always mean HTTP 403: Spring Security also considers the anonymous/authenticated state when translating it into a response.
- CSRF can block `POST`/`PUT`/`PATCH`/`DELETE` with 403 **before** reaching the authorization check branch; authorization tests need to provide a valid CSRF token if the configuration enables CSRF.

## 2. Permission Policy Example: Documents and Audit Page

Suppose the API has three test accounts:

| Actor | Granted authorities |
| --- | --- |
| Anonymous | No logged-in Authentication |
| `reader` | `ROLE_READER`, `DOC_READ` |
| `editor` | `ROLE_EDITOR`, `DOC_READ`, `DOC_WRITE` |
| `admin` | `ROLE_ADMIN`, `DOC_READ`, `DOC_WRITE`, `DOC_ADMIN` |

Endpoint list and expectations:

- `GET /api/public`: public, no login required, returns 200.
- `GET /api/docs/42`: requires `DOC_READ`, returns 200 if allowed.
- `POST /api/docs`: requires `DOC_WRITE`, returns 201 if the document is created.
- `DELETE /api/docs/42`: requires `DOC_ADMIN`, returns 204 if deleted successfully.
- `GET /api/admin/audit`: requires `ROLE_ADMIN`, returns 200 if allowed.

From five endpoints × four actors, create a 20-cell test table:

| Request | Anonymous | `reader` | `editor` | `admin` |
| --- | ---: | ---: | ---: | ---: |
| `GET /api/public` | **200** | **200** | **200** | **200** |
| `GET /api/docs/42` | **401** | **200** | **200** | **200** |
| `POST /api/docs` | **401** | **403** | **201** | **201** |
| `DELETE /api/docs/42` | **401** | **403** | **403** | **204** |
| `GET /api/admin/audit` | **401** | **403** | **403** | **200** |

This is the **example's specification**, not a default HTTP table applicable to every application. The example uses HTTP Basic so anonymous requests to protected endpoints expect 401. With form login, the status for the same situation may be a 302 redirect; with resource-hiding designs, some denials may be mapped to 404 per product requirements.

Rules for interpreting each cell:

- **Allow case**: status matches the permitted action (`200`, `201`, `204`), and if there are side effects, the side effects are correct.
- **Deny case due to unauthenticated**: HTTP 401; if using Basic, verify the `WWW-Authenticate` challenge.
- **Deny case due to missing permission**: HTTP 403; must not create/delete the document even if the request has a valid payload.
- **Public case**: anonymous must be able to access; authenticated users must not be arbitrarily blocked either.
- **Default deny**: undeclared paths/methods are not automatically allowed. Dedicate separate tests for the catch-all matcher.

In total, the matrix above has 11 allow cases and 9 deny cases. These numbers are only for cross-checking the test rows in **this specific example**; in real systems, the number of cases scales with actors, HTTP methods, resource contexts, and business policies.

## 3. Workflow for Translating a Matrix into Test Cases

### Step 1 — Lock down the specification source

Clearly state the actor, method, path pattern, required permission, expected behavior, and exception policy. In particular, distinguish **endpoint-level** permissions from **record-level** permissions:

- `GET /api/docs/{id}` being allowed by `DOC_READ` at the URL layer may not be sufficient; it might also require `doc.tenantId == principal.tenantId` or `doc.ownerId == principal.id`.
- An actor having both `DOC_READ` and `ROLE_ADMIN` is not automatically exempt from tenant checks if business rules forbid it.
- Denying cross-tenant objects might require 403 or returning 404 to limit exposing existence; the expectation must come from policy, not guesswork.

### Step 2 — Create at least one independent request per cell

A case consists of `caseId`, `method`, `path`, `actor`, fixture conditions, expected status, and side effects. For example:

```text
DOC_READ_ANON       GET     /api/docs/42    anonymous  -> 401
DOC_READ_READER     GET     /api/docs/42    reader     -> 200
DOC_CREATE_READER   POST    /api/docs       reader     -> 403
DOC_CREATE_EDITOR   POST    /api/docs       editor     -> 201
DOC_DELETE_EDITOR   DELETE  /api/docs/42    editor     -> 403
DOC_DELETE_ADMIN    DELETE  /api/docs/42    admin      -> 204
```

Do not merge "reader can read" and "reader cannot delete" into a single assertion; those are **two different expectations**. Use meaningful test names so that when one cell fails, the report pinpoints the exact failing actor × action.

### Step 3 — Fixture data must be deterministic

Create accounts, authorities, owners/tenants, records, and states so that every run has identical conditions. With HTTP Basic, `reader`/`editor`/`admin` can be in-memory accounts in tests. With JWT, tests can use the `jwt()` request post-processor to simulate claims, but separate tests for the decoder/signature/expiry are still needed if you want to verify **real authentication**.

For state-changing methods, provide a valid CSRF token in authorization test cases **when CSRF is enabled**, and add a separate test proving that requests without CSRF are rejected. Do not conclude "reader lacks permission" from a 403 caused by a missing CSRF token.

### Step 4 — Verify the complete outcome

Besides status, consider `WWW-Authenticate`, `Location`, `Content-Type`, error body/schema, returned objects, auditing, logs, and **absence of side effects**. A deny test that only checks status can still miss a "wrote to DB before returning 403" bug.

### Step 5 — Guard against coverage gaps

Test separately: no credentials; invalid credentials; valid credentials lacking permission; out-of-list roles/authorities; different methods on the same path; nested paths; different resource owner/tenant; ordered matchers; multiple `SecurityFilterChain`s; anonymous vs remember-me if used by the system; CSRF and relevant async/error dispatches.

## 4. Runnable Java 17+ Example

Create a Spring Boot 3.x application in package `com.example.authorization`. Use the dependencies **Spring Web**, **Spring Security**, **Spring Boot Test**, and **Spring Security Test**. With Gradle, for example `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

Add `settings.gradle`:

```groovy
rootProject.name = 'authorization-matrix-demo'
```

### 4.1. Permission Configuration Aligned with the Matrix

File `src/main/java/com/example/authorization/AuthorizationMatrixApplication.java`:

```java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationMatrixApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationMatrixApplication.class, args);
    }
}
```

File `src/main/java/com/example/authorization/SecurityConfig.java`:

```java
package com.example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/docs/*")
                    .hasAuthority("DOC_READ")
                .requestMatchers(HttpMethod.POST, "/api/docs")
                    .hasAuthority("DOC_WRITE")
                .requestMatchers(HttpMethod.DELETE, "/api/docs/*")
                    .hasAuthority("DOC_ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_READER", "DOC_READ")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_EDITOR", "DOC_READ", "DOC_WRITE")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_ADMIN", "DOC_READ",
                             "DOC_WRITE", "DOC_ADMIN")
                .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
```

Explanation:

- `requestMatchers(HttpMethod.GET, "/api/docs/*")` and `requestMatchers(HttpMethod.DELETE, "/api/docs/*")` have **different policies on the same path**. Therefore, you must not test only GET and assume DELETE is protected.
- `.hasAuthority("DOC_ADMIN")` requires the exact `DOC_ADMIN`. `.hasRole("ADMIN")` requires `ROLE_ADMIN` by convention. `admin` in the example is granted both, but that is a fixture decision, not automatic permission inheritance.
- `.anyRequest().denyAll()` denies undeclared requests by default. Matchers are evaluated in order and **only the first matching rule** is applied; place specific rules before broad rules.
- `.httpBasic(...)` creates a real authentication path to test anonymous, valid Basic credentials, and invalid credentials. `InMemoryUserDetailsManager` with hardcoded passwords is for learning examples only.
- CSRF remains enabled by default; `POST`/`DELETE` tests will use `.with(csrf())` so an authorization case does not accidentally become a CSRF case.
- Spring Security's default typically returns a **401 Basic challenge** when unauthenticated; authenticated cases lacking permission return **403**.

### 4.2. A Service to Observe Side Effects

File `src/main/java/com/example/authorization/MutationCounter.java`:

```java
package com.example.authorization;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class MutationCounter {
    private final AtomicInteger mutations = new AtomicInteger();

    public void recordMutation() {
        mutations.incrementAndGet();
    }

    public int count() {
        return mutations.get();
    }
}
```

`MutationCounter` is only to demonstrate testing **no data mutation** when a request is blocked. In a real project, replace it with repository queries, outbox, audit events, or appropriate business state.

File `src/main/java/com/example/authorization/DocumentController.java`:

```java
package com.example.authorization;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final MutationCounter counter;

    public DocumentController(MutationCounter counter) {
        this.counter = counter;
    }

    @GetMapping("/api/public")
    public Map<String, String> publicPage() {
        return Map.of("result", "public");
    }

    @GetMapping("/api/docs/{id}")
    public Map<String, String> read(@PathVariable String id) {
        return Map.of("id", id);
    }

    @PostMapping("/api/docs")
    public ResponseEntity<Map<String, String>> create() {
        counter.recordMutation();
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", "new"));
    }

    @DeleteMapping("/api/docs/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        counter.recordMutation();
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/admin/audit")
    public Map<String, String> audit() {
        return Map.of("result", "audit");
    }
}
```

The controller does not check roles itself; security rules block requests before invoking the controller. Side effects are placed in the controller for this lesson; real applications may have validation, service authorization, transactions, or per-record checks.

### 4.3. Converting All 20 Cells into Parameterized HTTP Tests

File `src/test/java/com/example/authorization/AuthorizationMatrixTest.java`:

```java
package com.example.authorization;

import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMatrixTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MutationCounter counter;

    record AccessCase(
            String caseId,
            String method,
            String path,
            String actor,
            int expectedStatus) {
    }

    // Expectations are copied from the business matrix, not inferred from SecurityConfig.
    static Stream<AccessCase> permissionMatrix() {
        return Stream.of(
            new AccessCase("PUBLIC_ANON", "GET", "/api/public", null, 200),
            new AccessCase("PUBLIC_READER", "GET", "/api/public", "reader", 200),
            new AccessCase("PUBLIC_EDITOR", "GET", "/api/public", "editor", 200),
            new AccessCase("PUBLIC_ADMIN", "GET", "/api/public", "admin", 200),

            new AccessCase("READ_ANON", "GET", "/api/docs/42", null, 401),
            new AccessCase("READ_READER", "GET", "/api/docs/42", "reader", 200),
            new AccessCase("READ_EDITOR", "GET", "/api/docs/42", "editor", 200),
            new AccessCase("READ_ADMIN", "GET", "/api/docs/42", "admin", 200),

            new AccessCase("CREATE_ANON", "POST", "/api/docs", null, 401),
            new AccessCase("CREATE_READER", "POST", "/api/docs", "reader", 403),
            new AccessCase("CREATE_EDITOR", "POST", "/api/docs", "editor", 201),
            new AccessCase("CREATE_ADMIN", "POST", "/api/docs", "admin", 201),

            new AccessCase("DELETE_ANON", "DELETE", "/api/docs/42", null, 401),
            new AccessCase("DELETE_READER", "DELETE", "/api/docs/42", "reader", 403),
            new AccessCase("DELETE_EDITOR", "DELETE", "/api/docs/42", "editor", 403),
            new AccessCase("DELETE_ADMIN", "DELETE", "/api/docs/42", "admin", 204),

            new AccessCase("AUDIT_ANON", "GET", "/api/admin/audit", null, 401),
            new AccessCase("AUDIT_READER", "GET", "/api/admin/audit", "reader", 403),
            new AccessCase("AUDIT_EDITOR", "GET", "/api/admin/audit", "editor", 403),
            new AccessCase("AUDIT_ADMIN", "GET", "/api/admin/audit", "admin", 200)
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("permissionMatrix")
    void enforcesEachExpectedDecision(AccessCase c) throws Exception {
        MockHttpServletRequestBuilder request = switch (c.method()) {
            case "GET" -> get(c.path());
            case "POST" -> post(c.path());
            case "DELETE" -> delete(c.path());
            default -> throw new IllegalArgumentException(c.method());
        };

        if (c.actor() != null) {
            request.with(httpBasic(c.actor(), "demo-pass"));
        }

        // This case tests authorization; CSRF is always valid for writes.
        if (!"GET".equals(c.method())) {
            request.with(csrf());
        }

        int before = counter.count();

        mvc.perform(request)
            .andExpect(status().is(c.expectedStatus()));

        // 201/204 are the two successful write actions in the demo.
        int expectedMutations = c.expectedStatus() == 201
                || c.expectedStatus() == 204 ? 1 : 0;
        assertEquals(before + expectedMutations, counter.count(),
                c.caseId() + " changed state unexpectedly");
    }

    @Test
    void anonymousProtectedRequestReceivesBasicChallenge()
            throws Exception {
        mvc.perform(get("/api/docs/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void wrongBasicPasswordDoesNotBecomeAuthorized() throws Exception {
        mvc.perform(get("/api/docs/42")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedWriterStillNeedsCsrfForPost() throws Exception {
        int before = counter.count();

        mvc.perform(post("/api/docs")
                .with(httpBasic("editor", "demo-pass")))
            .andExpect(status().isForbidden());

        assertEquals(before, counter.count());
    }

    @Test
    void unlistedRouteIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedMethodIsNotAccidentallyAuthorized() throws Exception {
        mvc.perform(get("/api/docs")
                .with(httpBasic("editor", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Conditions for the tests to work:

1. `@SpringBootTest` initializes the real security configuration and controller of the learning app; `@AutoConfigureMockMvc` provides `MockMvc` with the filter chain registered.
2. `.with(httpBasic(...))` sends Basic credentials to the security filter, testing a more realistic authentication path than just attaching `@WithMockUser`. The accounts exist only in the example in-memory user store.
3. `.with(csrf())` adds a valid CSRF token for `POST`/`DELETE`, so the result reflects the **authorization decision**; the `authorizedWriterStillNeedsCsrfForPost` test isolates CSRF behavior.
4. `status().is(c.expectedStatus())` compares the value from the matrix against the actual HTTP status.
5. `counter.count()` before/after ensures 401/403 does not mutate data in this simple model; with real transactions, check the DB and event/audit log.
6. `permissionMatrix()` has exactly 20 test cases matching the order of the permission table. Loosening or tightening a rule incorrectly will fail at least one case if the matrix is an independent specification.
7. The template includes both **allow** and **deny** for every protected action. It also tests invalid Basic credentials, missing CSRF, undeclared paths, and undeclared methods.

Do not use `.standaloneSetup(controller)` alone and conclude authorization has been tested: that setup can bypass Spring Security filters. If building MockMvc manually instead of letting Boot auto-configure it, you must integrate Spring Security, for example `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build()`.

### 4.4. Run Commands and Expected Results

Run:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

`@ParameterizedTest` executes 20 runs from `Stream<AccessCase>` and there are 5 additional `@Test` methods. Under the stated configuration, the expectation is **25 passing test runs**; do not claim PASS without actually running the command in a project with dependencies.

Run the application and test with cURL:

```bash
./gradlew bootRun
curl -i http://localhost:8080/api/docs/42
curl -i -u reader:demo-pass http://localhost:8080/api/docs/42
curl -i -u reader:demo-pass -X DELETE http://localhost:8080/api/docs/42
curl -i -u admin:demo-pass http://localhost:8080/api/admin/audit
```

For the GET requests above, the expected results in order are **401, 200, 403, 200**. Specifically, the `DELETE` command without an appropriate CSRF token can also fail with **403 due to CSRF**, so the cURL commands do not prove the exact reason why DELETE was rejected. To isolate authorization for write actions, use MockMvc `.with(csrf())` as in the tests. If you want `POST`/`DELETE` from a real client to succeed, design and supply a valid CSRF token according to the application's session/cookie and authentication model. Do not disable CSRF just to make the cURL example shorter.

## 5. Avoiding False-Positive Tests Due to Environment Setup

**A 200 request does not guarantee the permissions are right.** You must verify that the test is running the entire security chain and that the actor actually carries the expected authorities. The following mistakes are very common:

- `@WithMockUser(roles = "ADMIN")` only assigns `ROLE_ADMIN`; it does not implicitly assign `DOC_ADMIN`. If an endpoint requires `hasAuthority("DOC_ADMIN")`, you must pass that exact authority.
- `@WithMockUser` and `.with(user(...))` are useful for fast authorization tests, but **do not prove** that passwords/JWTs are validated properly. When you want to test HTTP authentication as well, use Basic credentials or the appropriate token mechanism.
- A 403 test on POST that forgets a valid CSRF token does not prove the `DOC_WRITE` rule works.
- Testing only with an account that has every authority will not catch over-permissive authorization bugs. You need at least one actor **outside** the policy for every action.
- MockMvc tests using `standaloneSetup` without attaching `FilterChainProxy` can return 200 even if production blocks with 403.
- Using `.anyRequest().authenticated()` for all URLs may let `reader` access unspecified actions. If the policy is *deny by default*, test undeclared paths/methods.
- Tests that copy the exact implementation logic to compute expected status lead to circular testing. Treat the approved matrix as independent test data.
- Asserting only status without asserting side effects can miss bugs that create/delete before being blocked.
- Reversing the order of specific matchers and broad matchers can render specific rules ineffective. Spring Security evaluates rules in order and applies the first match.
- Failing to distinguish 401/403 can hide login redirect bugs or permission leaks. With form login or a 404 policy, update expectations per the actual contract.

## 6. Extending the Matrix to Record-Level, Owner, and Tenant Permissions

A simple HTTP matrix is the baseline. In real applications, **the same actor and endpoint** can yield different results depending on the resource:

| Contextual case | Fixture and policy | Illustrative expectation |
| --- | --- | --- |
| Owner reads document | `readerA` has `DOC_READ`, `ownerId=readerA`, same tenant | 200 |
| Another user reads private document | `readerB` has `DOC_READ`, different owner, no share permission | 403 or 404 per specification |
| Cross-tenant access | Actor has `DOC_READ`, mismatched `tenantId` | Deny; status per anti-enumeration policy |
| Admin overrides owner | Only when business rules allow and tenant boundary remains valid | 200 |
| Non-existent document | ID missing in repository | 404 |
| Invalid/missing token | Unauthenticated | Typically 401 for Basic/Bearer REST |

For this problem, you must add service-layer or method authorization policies, such as an `AuthorizationManager`/`@PreAuthorize` using owner/tenant data loaded from a trusted source. **Do not trust client-supplied `ownerId`/`tenantId`** and use it directly to grant access. An independent test must seed at least two owners and two tenants, then verify each case.

Conceptual example using method authorization (illustrative snippet; requires implementing `documentPolicy` and enabling `@EnableMethodSecurity` in a real app):

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentDto readDocument(@P("documentId") long documentId) {
    return documentService.get(documentId);
}
```

This is **not a standalone Java file**; `@PreAuthorize` comes from `org.springframework.security.access.prepost.PreAuthorize`, `@P` comes from `org.springframework.security.core.parameters.P`. In integration tests, verify `readDocument` with the same actor against a `documentId` belonging to a different owner, a different tenant, and the same owner. Testing only the URL permission `DOC_READ` is not enough to prove there are no IDOR/BOLA (*Broken Object Level Authorization*) flaws.

In addition, consider resource state (`DRAFT`, `PUBLISHED`, `LOCKED`), operation (read/update/delete), OAuth2 scopes, and permission precedence/deny overrides if required by business rules. Do not mechanically multiply every dimension into a massive test count: first ensure **every distinct security decision** has positive/negative cases, then add representative boundary pairs.

## 7. Managing Test Coverage and Quality

You can use a product-specific permission tracking table:

| Case ID | Method/path | Actor/fixture | Expected | Actual | Evidence |
| --- | --- | --- | --- | --- | --- |
| `DOC_CREATE_READER` | `POST /api/docs` | `reader` + valid CSRF | 403, no DB write | From CI | MockMvc + repository assertion |
| `DOC_CREATE_EDITOR` | `POST /api/docs` | `editor` + valid CSRF | 201, one new record | From CI | MockMvc + repository assertion |
| `DOC_READ_OTHER_TENANT` | `GET /api/docs/42` | `readerB` other tenant | 403/404 per contract | From CI | Two-tenant test fixture |
| `UNLISTED_DELETE` | `DELETE /api/unknown` | `admin` + valid CSRF | Deny by default | From CI | Matcher coverage |

Three indicators to track:

1. **Matrix coverage**: number of decisions with tests divided by total approved decisions in scope. For example, section 2 has 20/20 concrete cells.
2. **Negative coverage**: every permission-gated action has an anonymous case and at least one authenticated actor **lacking permission**. Testing only anonymous can miss overly broad permissions for internal users.
3. **Behavior coverage**: allow cases verify the expected response and effects; deny cases verify **no side effects**, no data leakage, and correct status/headers.

When adding a role, authority, endpoint, HTTP method, or resource state, update **the matrix first**, then update the tests. If a test fails due to a new policy, review the permission requirement with the responsible owner; do not change expectations just to turn CI green.

## 8. Self-Check Questions

1. Why do we need both 200 and 403 tests for `GET /api/docs/42`? Because the 200 test confirms an authorized user can access it; the 403 test confirms someone lacking `DOC_READ` cannot read it.
2. Why might anonymous and `reader` receive two different statuses when calling `DELETE /api/docs/42`? Anonymous requires authentication (typically 401); `reader` is authenticated but lacks `DOC_ADMIN` (403), provided the test's CSRF is valid.
3. Why must `.with(csrf())` be added to `POST`/`DELETE` tests? So that when CSRF protection is enabled, authorization tests are not misled by a 403 caused by CSRF.
4. How does `hasRole("ADMIN")` differ from `hasAuthority("DOC_ADMIN")`? The first requires `ROLE_ADMIN` by default, while the second requires the exact `DOC_ADMIN`.
5. Why is a 403 status test alone not enough to prove safety? Because the request might have performed state mutations before the error was handled; you must inspect the DB/events/counter.
6. Why can two users who both have `DOC_READ` still be allowed/disallowed from reading the same ID? Because owner/tenant/resource-state policies may enforce additional conditions beyond path permissions.
7. Why does a test suite that derives expectations from `SecurityConfig` easily miss bugs? Because if the configuration is wrong, the expectation-generating logic can copy the same mistake; the business specification must be independent of the implementation.

## Official Documentation

- [Authorize HTTP Requests — Spring Security](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring MVC Test Integration — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [MockMvc Test Setup — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Running as a User in MockMvc — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [CSRF Testing — Spring Security](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Testing Method Security — Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)