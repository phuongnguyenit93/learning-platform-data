# Regression Testing with a Permission Matrix When Adding New Endpoints or Actions

> Knowledge article for Spring Security (Servlet/MVC), Java 17+, Spring Boot 3.x, and JUnit 5. Goal: when adding an API or action, prove that **new permissions match the specification** and **permissions for all existing actions remain intact**. A single test checking "ADMIN succeeds" is never enough.

## 1. What Is a Permission Matrix and Why Does It Prevent Regressions?

A permission matrix defines the expected decision for every combination of **principal × role/authority × HTTP method + endpoint/action × resource × context**. It is an agreed specification reviewed with business/policy owners and must be authored **independently** of the code enforcing permissions.

Bugs that can appear when adding `POST /archive`:

- **Privilege escalation:** the `APPROVER` role accidentally gains archive permission due to an overly broad URL rule or relaxed role policy.
- **BOLA/IDOR:** `EDITOR` may only archive their own documents, yet can swap the path ID to archive someone else's document.
- **Regression on old functionality:** modifying `SecurityFilterChain` causes `GET /documents/{id}` or `POST /approve` to lock out valid callers or inadvertently open access.
- **Leaks/side effects:** the request returns 403, yet a database write or event emission already occurred before rejection.

Suppose we have two documents: `doc-a` owned by `alice`, and `doc-b` owned by `bob`. Three actions:

| Action | Endpoint | Status |
| --- | --- | --- |
| Read | `GET /api/documents/{id}` | Existing |
| Approve | `POST /api/documents/{id}/approve` | Existing |
| Archive | `POST /api/documents/{id}/archive` | **Newly added** |

**Assumed policy for this example** (requests in the table below use username `alice`; "own" = `doc-a`, "other" = `doc-b`):

| Role | Read own | Read other | Approve own | Approve other | Archive own | Archive other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `VIEWER` | 200 | 403 | 403 | 403 | 403 | 403 |
| `EDITOR` | 200 | 403 | 403 | 403 | 200 | 403 |
| `APPROVER` | 200 | 200 | 200 | 200 | 403 | 403 |
| `ADMIN` | 200 | 200 | 200 | 200 | 200 | 200 |

The "archive" columns represent the new requirement; **all four existing read/approve columns must continue to be tested** after adding the action. Never assume `APPROVER` can archive merely because it can approve. This table describes a sample business contract, not built-in Spring Security roles.

Add boundary cases with dedicated expectations:

| Condition | Example Expectation |
| --- | --- |
| Anonymous GET read | 401 (HTTP Basic requires authentication) |
| Anonymous POST archive with valid CSRF | 401 |
| Logged in, but wrong role/owner | 403 |
| ADMIN reads non-existent ID | 404 |
| ADMIN invokes unsupported DELETE | 403 due to default-deny |
| ADMIN POST archive missing CSRF token | 403 (sample app keeps default CSRF protection) |
| `bob` / EDITOR archives `doc-b` | 200 |

**401, 403, and 404 represent distinct contracts:** 401 typically indicates missing authentication; 403 indicates insufficient authorization; 404 indicates resource not found. Some systems intentionally return 404 instead of 403 to hinder resource ID enumeration. Finalize the real system's policy before writing expectations. Do not treat this example's status codes as mandatory rules for every API/JWT.

## 2. Which Boundaries Must Be Tested?

Protection flow for a Spring Servlet request:

```text
Client: method + path + identity + (CSRF if needed)
          |
          v
SecurityFilterChain
  - undeclared path/method -> deny
  - missing authentication -> 401 in HTTP Basic example
          |
          v
Controller -> Spring bean/proxy -> @PreAuthorize
                                  - wrong role/owner -> 403
                                  - authorized -> invoke method
                                           |
                                           v
                                      Service/Repository
                                        - ID not found -> 404
                                        - success -> data/side effects
```

Separate three layers: **request authorization** (`authorizeHttpRequests`), **method/resource authorization** (`@PreAuthorize`, `@EnableMethodSecurity`), and **business effect** (DB changes, events, audits). Matching `.authenticated()` on a route does not mean every role is allowed in the service. Conversely, testing `new DocumentService()` directly bypasses the proxy and skips annotations altogether.

The matrix must test both allows and denies. A negative POST test missing CSRF can return 403 even if role checks are completely broken: when testing role authorization, supply valid CSRF, and write separate tests for CSRF itself.

## 3. Runnable Example: 24 Matrix Cases + 6 Boundary Cases

This example uses **Spring Boot 3.x**, Java 17, Spring MVC, JUnit Jupiter, and `spring-security-test`; it avoids DB access to isolate the authorization focus. Paths/roles are simulated in memory while the filter chain and Spring method security execute inside a real test context.

Gradle dependencies if the project does not already include the starters; rely on the Spring Boot BOM/plugin for version management:

```groovy
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

Create `src/test/java/com/example/security/AuthorizationMatrixTest.java` with the complete contents below:

```java
package com.example.security;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthorizationMatrixTest.DemoApp.class)
@AutoConfigureMockMvc
class AuthorizationMatrixTest {

    @Autowired MockMvc mvc;

    // Each Case carries an expected value derived from the spec, not computed from Policy.
    record Case(String name, String verb, String path, String username,
                String role, int expectedStatus, String expectedBody) {}
    record PermissionRow(String role, int[] statuses) {}

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("accessMatrix")
    void allOldAndNewActionsRespectPermissionMatrix(Case c)
            throws Exception {

        MockHttpServletRequestBuilder request = switch (c.verb()) {
            case "GET" -> get(c.path());
            case "POST" -> post(c.path()).with(csrf());
            default -> throw new IllegalArgumentException(c.verb());
        };

        var result = mvc.perform(
                request.with(user(c.username()).roles(c.role())))
            .andExpect(status().is(c.expectedStatus()));

        // Successful cases must return the exact resource/action payload.
        if (c.expectedBody() != null) {
            result.andExpect(content().string(c.expectedBody()));
        }
    }

    static Stream<Case> accessMatrix() {
        // Order: read-own, read-other, approve-own, approve-other,
        // archive-own, archive-other. This is the reviewed SPEC.
        List<PermissionRow> spec = List.of(
            new PermissionRow("VIEWER",
                new int[] {200, 403, 403, 403, 403, 403}),
            new PermissionRow("EDITOR",
                new int[] {200, 403, 403, 403, 200, 403}),
            new PermissionRow("APPROVER",
                new int[] {200, 200, 200, 200, 403, 403}),
            new PermissionRow("ADMIN",
                new int[] {200, 200, 200, 200, 200, 200})
        );

        List<Case> cases = new ArrayList<>();
        for (PermissionRow row : spec) {
            for (int i = 0; i < 6; i++) {
                String id = i % 2 == 0 ? "doc-a" : "doc-b";
                String verb = i < 2 ? "GET" : "POST";
                String suffix = i < 2 ? ""
                    : i < 4 ? "/approve" : "/archive";
                String path = "/api/documents/" + id + suffix;
                int expected = row.statuses()[i];

                String expectedBody = expected == 200
                    ? (i < 2 ? "doc:"
                        : i < 4 ? "approved:" : "archived:") + id
                    : null;

                cases.add(new Case(
                    row.role() + "/" + suffix + "/" + id,
                    verb, path, "alice", row.role(),
                    expected, expectedBody));
            }
        }
        return cases.stream(); // 4 roles × 2 owner relations × 3 actions
    }

    @Test
    void bobEditorCanArchiveHisOwnDocument() throws Exception {
        mvc.perform(post("/api/documents/doc-b/archive")
                .with(user("bob").roles("EDITOR")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("archived:doc-b"));
    }

    @Test
    void anonymousReadIsUnauthorized() throws Exception {
        mvc.perform(get("/api/documents/doc-a"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousArchiveIsUnauthorized() throws Exception {
        mvc.perform(post("/api/documents/doc-a/archive").with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminCanReachNotFoundForUnknownDocument() throws Exception {
        mvc.perform(get("/api/documents/missing")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isNotFound());
    }

    @Test
    void undeclaredDeleteIsDeniedEvenToAdmin() throws Exception {
        mvc.perform(delete("/api/documents/doc-a")
                .with(user("root").roles("ADMIN")).with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeWithoutCsrfIsForbiddenEvenToAdmin() throws Exception {
        mvc.perform(post("/api/documents/doc-a/archive")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({
        SecuritySetup.class, DocumentPolicy.class,
        DocumentService.class, DocumentController.class
    })
    static class DemoApp {}

    @Configuration(proxyBeanMethods = false)
    static class SecuritySetup {
        @Bean
        SecurityFilterChain chain(HttpSecurity http) throws Exception {
            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET,
                        "/api/documents/{id}").authenticated()
                    .requestMatchers(HttpMethod.POST,
                        "/api/documents/{id}/approve",
                        "/api/documents/{id}/archive").authenticated()
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
            // Uses session/HTTP Basic; do not disable CSRF.
        }
    }

    @Component("documentPolicy")
    public static class DocumentPolicy {
        static final Map<String, String> OWNERS =
            Map.of("doc-a", "alice", "doc-b", "bob");

        private boolean hasRole(Authentication a, String role) {
            return a.getAuthorities().stream().anyMatch(
                x -> x.getAuthority().equals("ROLE_" + role));
        }

        public boolean canRead(Authentication a, String id) {
            return hasRole(a, "ADMIN") || hasRole(a, "APPROVER")
                || ((hasRole(a, "VIEWER") || hasRole(a, "EDITOR"))
                    && Objects.equals(OWNERS.get(id), a.getName()));
        }

        public boolean canApprove(Authentication a) {
            return hasRole(a, "APPROVER") || hasRole(a, "ADMIN");
        }

        public boolean canArchive(Authentication a, String id) {
            return hasRole(a, "ADMIN")
                || (hasRole(a, "EDITOR")
                    && Objects.equals(OWNERS.get(id), a.getName()));
        }
    }

    @Service
    public static class DocumentService {

        @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
        public String read(String id) {
            checkExists(id);
            return "doc:" + id;
        }

        @PreAuthorize("@documentPolicy.canApprove(authentication)")
        public String approve(String id) {
            checkExists(id);
            return "approved:" + id;
        }

        @PreAuthorize("@documentPolicy.canArchive(authentication, #p0)")
        public String archive(String id) {
            checkExists(id);
            return "archived:" + id;
        }

        private void checkExists(String id) {
            if (!DocumentPolicy.OWNERS.containsKey(id)) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
        }
    }

    @RestController
    @RequestMapping("/api/documents")
    public static class DocumentController {
        private final DocumentService service;

        public DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/{id}")
        public String read(@PathVariable String id) {
            return service.read(id);
        }

        @PostMapping("/{id}/approve")
        public String approve(@PathVariable String id) {
            return service.approve(id);
        }

        @PostMapping("/{id}/archive")
        public String archive(@PathVariable String id) {
            return service.archive(id);
        }
    }
}
```

Run from the project root with Gradle Wrapper:

```bash
./gradlew test --tests "com.example.security.AuthorizationMatrixTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.security.AuthorizationMatrixTest"
```

**Expected by code:** 24 parameterized test invocations plus 6 boundary cases = **30 passing cases**, assuming matching dependencies, compatible Java/Spring Boot, and no conflicting security configuration. These are expected assertions, not observed test-run logs. The article uses Spring Boot 3.x APIs; on Spring Boot 4.x, adjust `@AutoConfigureMockMvc` imports/auto-configuration to match the actual version.

Key design highlights:

1. `@SpringBootTest` + `@AutoConfigureMockMvc` run MVC and the Security filter inside the test ApplicationContext. `@EnableMethodSecurity` enables `@PreAuthorize` on the `DocumentService` **Spring bean**.
2. `@Import` explicitly registers the service/controller/policy. Constructing `new DocumentService()` manually will not trigger the same interceptor.
3. `@PreAuthorize("@documentPolicy...")` calls the policy bean; `#p0` addresses the first parameter positionally, avoiding reliance on the `-parameters` compiler flag.
4. User fixture `user("alice").roles("EDITOR")` creates authority `ROLE_EDITOR`; ownership also depends on `authentication.name`, so matching roles alone are not enough.
5. Policy POST tests supply valid `.with(csrf())`. The dedicated CSRF test intentionally omits the token and expects 403. In pure stateless OAuth2 Bearer APIs, the CSRF policy may differ.
6. `requestMatchers` evaluates **HTTP method + endpoint**; `.anyRequest().denyAll()` blocks undeclared routes. `@PreAuthorize` enforces business roles/ownership in the service.
7. `accessMatrix()` stores **independent expected values** as a `200/403` table. If someone loosens `DocumentPolicy.canArchive()` to allow `APPROVER`, the negative archive tests turn red.

## 4. Workflow for Adding New Endpoints/Actions Without Regressions

**Before coding:**

1. Define the verb, path, action name, resource, role/authority, ownership/tenant, resource state, and side effects. Explicitly list who is allowed and who is denied.
2. Start from the version-controlled baseline matrix; add columns/rows for the new action. **Keep expectations for existing actions unchanged** unless the business approved a permission change.
3. Author positive, negative, anonymous, foreign-owner, missing-resource, and unsupported-HTTP-method cases per risk. A new permission column without denial tests is a coverage gap.
4. Put the cases into `@MethodSource` or an equivalent data fixture. Never compute expected values from the policy under test.

**During implementation:**

5. Add the exact request matcher and `@PreAuthorize`/policy at the right boundary. For resource ownership, check the request's actual ID **inside the service or policy layer**, not merely static roles at the URL.
6. Verify matcher changes do not introduce overly permissive wildcards or invert rule ordering. With multiple `SecurityFilterChain` beans, confirm the route hits the intended chain.
7. When permissions guard side effects, verify the check runs **before** writing data or emitting events. If updates are transactional, test rollback behavior per policy.

**Before merging:**

8. Run the entire old-and-new permission regression suite; inspect the JUnit report rather than just the green count. If an expected result changes, require an explicitly reviewed business requirement.
9. Add integration tests with real repositories/events for data-mutating actions. Run with isolated fixtures; the database must return to baseline between tests.
10. Wire the suite into CI so PRs fail if any critical role/resource/action cell breaks.

For an archive action that changes DB state, add assertions beyond response-only demos:

| Case | HTTP | Post-request DB `status` | Archive Event |
| --- | --- | --- | --- |
| EDITOR archives own document | 200 | `ARCHIVED` | Exactly one event |
| EDITOR archives someone else's document | 403 | Remains `ACTIVE` | None |
| VIEWER archives own document | 403 | Remains `ACTIVE` | None |
| ADMIN archives existing document | 200 | `ARCHIVED` | Exactly one event |
| ADMIN archives non-existent ID | 404 | No record created/modified | None |

When a document is already `ARCHIVED`, add cases for idempotency, state conflict (`409`), or repeat-handling per contract. Never assume permissions depend only on role: tenant, ownership transfer, state, and timestamp can all change the decision.

## 5. Evaluating Matrix Coverage

The sample matrix covers **4 roles × 3 actions × 2 owner relations = 24** combinations, plus 6 boundary cases. In real projects, weigh these dimensions when scoping your regression suite:

| Dimension | Test Data | Risks Detected |
| --- | --- | --- |
| Principal/identity | Alice, Bob; distinct names/IDs | Hardcoded usernames or broken owner checks |
| Authority | Specific roles and permissions, multi-role | Wrong role/authority mapping, privilege escalation |
| Authentication | Anonymous, valid session, expired/invalid token | Broken auth mode or wrong 401/403 status |
| Resource | Own, foreign, cross-tenant, missing, varied states | IDOR/BOLA, tenant info leaks |
| Action | Read, approve, archive; new/old actions | Old permissions broken when adding new actions |
| HTTP | Verb, path, undeclared route, CSRF | Filter bypass or misconfigured matchers |
| Outcome | Status, payload, ID, DB/event/audit | Wrong document returned or side effects executed on 403 |

When dimensions grow too large, group by equivalence classes and use pairwise combinations for low-risk axes, while exhaustively covering paths that mutate data, cross tenants, read sensitive records, or manage permissions. A useful coverage metric is **how many matrix cells have independent assertions**, not raw test count.

To verify bug-detection power, on a scratch branch temporarily widen `canArchive()` to allow `APPROVER` or remove `@PreAuthorize` and run the suite. The corresponding negative cases must fail; then revert the temporary edit. Never perform security fault injection like this in production.

## 6. OAuth2/JWT, CSRF, and Differences in Test Identities

Spring Security Test's `user(...).roles(...)` injects a mock authentication into the request: it is well-suited for testing **authorization given existing roles**, yet **does not verify** JWT signatures, issuers, audiences, claim-to-authority converters, or tenant grants from an IdP.

In a Resource Server, write dedicated tests for JWTs/claims using `jwt()`:

```java
// Snippet inside a test that already has MockMvc and Resource Server config.
// Requires static import jwt from SecurityMockMvcRequestPostProcessors
// and import org.springframework.security.core.authority.SimpleGrantedAuthority.
mvc.perform(get("/api/documents/doc-a")
        .with(jwt().jwt(token -> token.subject("alice"))
                   .authorities(
                       new SimpleGrantedAuthority("ROLE_VIEWER"))))
    .andExpect(status().isOk());
```

`jwt().authorities(...)` **assigns authorities directly**, so it does not exercise a claim-to-authority converter. Add unit tests for the converter or integration tests validating real tokens against the real configuration when claim mapping is a risk. For cookies/sessions, CSRF is typically a boundary to test; for stateless Bearer APIs, the CSRF contract depends on configuration and threat model. Do not copy 403-on-missing-CSRF expectations from this example into an API intentionally configured differently.

## 7. Common Mistakes and How to Avoid Them

- **Testing only ADMIN:** add lower-role tests for both `own` and `other`, especially for new actions.
- **Asserting only 200 or `size()`:** check IDs, resource content, exact status codes, and side-effect data.
- **Deriving expected values from the policy under test:** use a matrix reviewed independently of the code.
- **Testing objects constructed via `new`:** `@PreAuthorize` via Spring AOP proxies is not triggered as it is on container-managed beans.
- **Disabling filters in MockMvc:** fails to prove `SecurityFilterChain`; configure and exercise real filters.
- **POST deny tests missing CSRF:** fail early with 403 due to CSRF, giving false green permission tests; supply valid tokens for role tests.
- **Confusing roles and authorities:** `roles("ADMIN")` produces `ROLE_ADMIN`, whereas `authorities("document:archive")` preserves the permission string verbatim.
- **Dropping old permission columns/rows:** new matchers can cause regressions on existing endpoints.
- **Not checking writes on denied requests:** 403 does not prove DB/events stayed unchanged.
- **Exposing new routes via broad wildcards:** if `anyRequest().authenticated()` or `permitAll()` accidentally covers sensitive paths, logged-in users pass the HTTP layer; enforce service policies and deny fallbacks.
- **Forgetting to distinguish 403 vs 404:** can leak resource existence or mismatch the contract.
- **Overlooking equivalent paths/verbs:** other REST versions, query parameters, nested resources, and multiple filter chains may route down different branches.

## 8. Acceptance Checklist

1. A pre-change policy table exists, is reviewed, and is stored alongside the code or spec docs.
2. The new action covers all roles and resource relationships; all legacy actions still run in regression.
3. Each case specifies `username`, role/authority, method, URL, resource, and expected status/payload.
4. Denial cases cover anonymous, lower roles, foreign owners, disallowed routes/methods, and CSRF/tokens per real setup.
5. HTTP/security interceptors are active in tests; `@EnableMethodSecurity` is enabled when testing `@PreAuthorize`.
6. For data-mutating actions, verify DB, events, and audits remain unchanged on denial.
7. CI blocks merges if any permission cell breaks. Changing an expected value requires an approved permission-change request.

## References

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security — CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [JUnit 5 — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)
