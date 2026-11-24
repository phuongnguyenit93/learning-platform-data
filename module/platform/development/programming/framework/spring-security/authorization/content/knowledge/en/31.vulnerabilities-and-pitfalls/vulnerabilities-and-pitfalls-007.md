# Hiding Buttons in the UI Without Server-Side Controls

> **Category:** Mistakes and vulnerabilities in Spring Security authorization. **Problem:** the frontend hides or disables a feature, yet the backend endpoint/service still accepts unauthorized requests. **Principle:** the UI only assists user experience; every request must be authenticated and authorized by the backend for both the *action* and the *specific resource*.

## 1. Scenario: The Button Is Invisible Yet the API Can Still Be Called

Suppose a report management system has:

- `an` owns report `101` and has the `report:read` permission.
- `binh` owns report `102`.
- A reviewer is granted both `report:read` and the elevated permission `report:read:any`.

The React UI only displays the button/link when the permissions from the user session contain `report:read`:

~~~jsx
// UI control only; not a security boundary.
function ReportActions({ reportId, permissions }) {
  const canRead = permissions.includes("report:read");
  return canRead
    ? <a href={"/reports/" + reportId}>View report</a>
    : null;
}
~~~

Even if the button is hidden, the user's browser can still send requests using DevTools, or the user can use curl/Postman to call the API directly:

~~~http
GET /api/reports/102 HTTP/1.1
Host: example.test
Authorization: Bearer <access-token-of-an>
~~~

The HTTP snippet above illustrates an application with a valid Bearer token; the Spring Boot application example later uses HTTP Basic for easier testing, so do not assume a Bearer header automatically works in that program.

If the backend only checks “is logged in” and queries `reports.findById(102)` without checking record permissions, `an` can read `binh`'s report. Changing the ID can also lead to approving, editing, or deleting someone else's report. This is **Broken Access Control** and specifically **BOLA/IDOR**: missing object-level authorization.

Two questions must be distinguished:

1. **Function-level:** is the principal allowed to invoke the read, edit, approve, or delete report function?
2. **Object-level:** is the principal allowed to perform that function on **the report with the requested ID**?

Hiding a button in the UI proves neither. Even when the backend uses `hasAuthority("report:read")`, the system still suffers from IDOR if a user permitted to read their own reports can read someone else's.

## 2. Why UI Guards, CSS, and Route Guards Are Not Enough

The frontend runs in an environment the user can observe and control. A user can:

- Call endpoints directly, bypassing buttons or pages.
- Alter path/query/body, e.g., `/api/reports/101` to `/api/reports/102`.
- Modify `role`, `permissions`, `isAdmin`, or `ownerId` in JavaScript/runtime/request.
- Replay a previously successful request or write a custom HTTP client.
- Use alternative endpoints (mobile API, GraphQL, batch/export, legacy URLs), even if the current menu does not mention them.

Therefore, **do not trust** client-sent fields such as `isAdmin=true`, `ownerId`, or `tenantId` to make authorization decisions. The server must verify identity through a trusted mechanism (verified session/token) and then check real permissions and the accessed resource.

The frontend should still hide/disable buttons: it reduces confusion and improves UX. However, never call it “function protected” if the API still lacks authorization.

## 3. Vulnerable Code: Identifying Before Fixing

The following snippet is **intentionally unsafe**, illustrating only a Spring MVC controller lacking object-level authorization:

~~~java
// VULNERABLE: assumes the user is logged in,
// but does not check whether they have permission to read the specific id.
@GetMapping("/api/reports/{id}")
public Report view(@PathVariable long id) {
    return repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
}
~~~

Another dangerous variant for a write function:

~~~java
// VULNERABLE: permission from request body is untrusted.
@PostMapping("/api/reports/{id}/approve")
public void approve(@PathVariable long id,
                    @RequestBody ApproveRequest body) {
    if (body.isAdmin()) {
        reportService.approve(id);
    }
}
~~~

Any client can set `isAdmin=true` on its own. Never check authorization by “whether the button is visible”, “whether the UI sent `isAdmin`”, or “whether the user knows a secret URL”. The server must check against the `Authentication` established by the security filter chain, then verify owner/tenant/object state.

## 4. Designing the Fix: Defense in Depth

A secure design has three layers of checks:

- **Authentication:** identity/principal from session, HTTP Basic, JWT/OIDC… verified by the server.
- **Endpoint authorization:** `SecurityFilterChain` with `authorizeHttpRequests`/`requestMatchers` specifies which authorities may call each HTTP method and path.
- **Business/resource authorization:** service/domain policy checks owner, tenant, assigned relationships, status, and special permissions on the record before reading or modifying it.

Use **deny by default** for unlisted endpoints. Place critical checks in the service so alternative entry points (new controllers, other APIs, jobs, handlers) cannot easily bypass them. Spring Security supports `@EnableMethodSecurity` and `@PreAuthorize` on Spring beans; calls must pass through the Spring proxy. Instantiating services manually with `new` or self-invocation `this.protectedMethod()` can skip the interceptor.

| Scenario | Typical HTTP Outcome |
| --- | --- |
| No valid login credentials | `401 Unauthorized` for HTTP authentication APIs, or login redirect depending on config |
| Authenticated but lacking function permission | `403 Forbidden` |
| Has function permission but wrong owner/tenant | `403` or `404` per policy against existence disclosure |
| Authorized and record exists | `200 OK` on read |
| Authorized but record does not exist | `404 Not Found` |

HTTP status is the **result after checking**, not a substitute for authorization. Never return partial sensitive data and rely on the frontend to hide it.

## 5. Complete Practice Lab: Spring Boot, Java 17+, Spring MVC

Example built with **Spring Boot 3.x / Spring Security 6.x**, Java 17+. The demo API has only `GET /api/reports/{id}`; data lives in memory to focus on owner checks. In real deployments, replace the data source with a DB filtered by tenant/owner and replace the demo authentication mechanism with an appropriate configuration.

### 5.1. Maven Dependencies

Inside a Spring Boot Maven project with parent or BOM configured:

~~~xml
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
~~~

### 5.2. Enabling Method/Service Protection

Create `src/main/java/com/example/authorization/AuthorizationDemoApplication.java`:

~~~java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` is **not enabled by default** merely by adding Spring Security Starter. It registers method-security interceptors so `@PreAuthorize` operates on beans.

### 5.3. HTTP Authorization: Deny by Default

Create `src/main/java/com/example/authorization/SecurityConfig.java`:

~~~java
package com.example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/*")
                    .hasAuthority("report:read")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

`GET /api/reports/{id}` requires the **exact string** authority `report:read`; other requests are denied. HTTP Basic is used to test 401 responses simply, not as a recommendation to use username/password Basic in every production environment. This demo only has GET so CSRF does not need to be disabled; keep default CSRF for unsafe methods when adding write features. `hasRole('ADMIN')` typically corresponds to authority `ROLE_ADMIN`, distinct from `hasAuthority('ADMIN')`.

### 5.4. Model and Repository

Create `src/main/java/com/example/authorization/Report.java`:

~~~java
package com.example.authorization;

public record Report(long id, String owner, String title) {
}
~~~

Create `src/main/java/com/example/authorization/ReportRepository.java`:

~~~java
package com.example.authorization;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class ReportRepository {

    private final Map<Long, Report> reports = Map.of(
            101L, new Report(101L, "an", "Bao cao cua An"),
            102L, new Report(102L, "binh", "Bao cao cua Binh")
    );

    public Optional<Report> findById(long id) {
        return Optional.ofNullable(reports.get(id));
    }
}
~~~

Fixed data allows testing IDOR: `an` and `binh` both have records with different owners. `Map.of` is immutable; the example does not implement update operations.

### 5.5. Checking Permission Against the Exact Report

Create `src/main/java/com/example/authorization/ReportPolicy.java`:

~~~java
package com.example.authorization;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {

    private final ReportRepository repository;

    public ReportPolicy(ReportRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long id) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return repository.findById(id)
                .map(report ->
                        report.owner().equals(authentication.getName())
                        || authentication.getAuthorities().stream()
                                .anyMatch(a ->
                                        "report:read:any".equals(a.getAuthority())))
                .orElse(false);
    }
}
~~~

The policy reads the username from the `Authentication` established by Spring Security. A user can read when they **are the owner**, or when the backend granted the elevated authority `report:read:any`. That permission does not magically appear when a client alters a JS variable. For a non-existent record, the policy returns `false`; the example intentionally returns 403 from method security rather than disclosing resource existence.

### 5.6. Service Protecting Both Function and Object

Create `src/main/java/com/example/authorization/ReportService.java`:

~~~java
package com.example.authorization;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('report:read') and @reportPolicy.canRead(authentication, #p0)"
    )
    public Report read(long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Report not found"));
    }
}
~~~

`#p0` is the first parameter (`id`) of the method in SpEL; it does not depend on whether the Java compiler records parameter name metadata. The `and` expression requires **both** `report:read` and permission on the ID. The `report:read:any` authority lifts the owner restriction but **does not** substitute for `report:read`. `ResponseStatusException(404)` acts as a fallback if data disappears after the check or when another policy permits lookup yet the record is gone.

### 5.7. Controller Calling the Protected Service

Create `src/main/java/com/example/authorization/ReportController.java`:

~~~java
package com.example.authorization;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Report view(@PathVariable long id) {
        return service.read(id);
    }
}
~~~

The controller does not read `isAdmin` or `ownerId` from the browser to grant access. It calls a Spring bean via dependency injection; the Spring method-security proxy protects the call even if more controllers are added later.

## 6. Testing Direct API Attacks with MockMvc

The tester **does not need to see or click frontend buttons**. Tests send requests directly to the endpoint with different identities/permissions and try changing IDs. `@SpringBootTest` + `@AutoConfigureMockMvc` runs the real `SecurityFilterChain`; `@WithMockUser` sets a mock identity for authorization testing.

Create `src/test/java/com/example/authorization/ReportSecurityIntegrationTest.java`:

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService service;

    @Test
    void anonymousGets401() throws Exception {
        mvc.perform(get("/api/reports/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:write")
    void missingReadAuthorityGets403() throws Exception {
        mvc.perform(get("/api/reports/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void ownerCanReadOwnRecord() throws Exception {
        mvc.perform(get("/api/reports/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.owner").value("an"));
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void changingIdCannotReadAnotherOwnersRecord() throws Exception {
        mvc.perform(get("/api/reports/102"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
            username = "reviewer",
            authorities = {"report:read", "report:read:any"})
    void reviewerMayReadWithExplicitElevatedAuthority() throws Exception {
        mvc.perform(get("/api/reports/102"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("binh"));
    }

    @Test
    @WithMockUser(username = "reviewer", authorities = "report:read:any")
    void elevatedObjectAuthorityAloneIsInsufficient() throws Exception {
        mvc.perform(get("/api/reports/102"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void serviceItselfAlsoEnforcesOwnerPolicy() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(102L));
    }
}
~~~

Command from the root directory of a Maven project with the dependencies above declared:

~~~bash
./mvnw -Dtest=ReportSecurityIntegrationTest test
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -Dtest=ReportSecurityIntegrationTest test
~~~

**Expected result:** all **7 tests PASS** when the project is configured properly. Tests have no `System.out.println` so there is no custom program stdout to predict; Maven output varies by plugin/version. This is expected from the sample logic, not a report of an actual Maven run.

| Case | Context/Path | Expectation |
| --- | --- | --- |
| Unauthenticated | GET `/api/reports/101` | `401` with HTTP Basic |
| Logged in, missing `report:read` | `an` GET `101` | `403` |
| Sufficient permission and right owner | `an` GET `101` | `200`, JSON owner `an` |
| Function permission present, wrong owner | `an` GET `102` | `403` |
| Reviewer granted both authorities | `reviewer` GET `102` | `200`, owner `binh` |
| Reviewer with only `report:read:any` | GET `102` | `403` |
| Bypass HTTP, call service directly | `an` calls `service.read(102)` | `AccessDeniedException` |

The test suite highlights **negative testing**: the absence of a button in the UI has nothing to do with blocking requests. The final test also catches the mistake of protecting only the controller while forgetting rules at the service. `@WithMockUser` does not verify real passwords/JWTs; separate tests are needed for login/token mechanisms.

## 7. Other Mechanisms Do Not Replace Server Authorization

| Mechanism | What It Does | Limitation |
| --- | --- | --- |
| UI hiding/disabling buttons | UX, prevents accidental clicks | Direct requests can still be sent |
| Frontend route guard | Screen navigation | Does not protect APIs |
| Authentication | Verifies identity | Does not grant unlimited permissions on every object |
| `SecurityFilterChain` | Protects HTTP endpoints, methods, paths | Does not inherently know each ID's owner/tenant |
| `@PreAuthorize`/domain policy | Authorization based on principal and business rules | Requires method security enabled, proxy not bypassed |
| CORS | Restricts cross-origin scripts in browsers | Does not block curl/Postman or same-origin users |
| CSRF | Protects state-changing requests when browsers auto-send credentials | Does not replace role/owner authorization |
| JWT validation | Verifies token validity and relevant claims | Does not automatically grant access to all records |
| WAF/API gateway | Filters/constrains access at the perimeter | Usually unaware of per-object policies in the DB |

If a JWT contains `role` or `scope` signed by the token issuer, the backend can trust those claims **after validating signature, issuer, audience, expiry…** per application requirements; however, it must still check permission on `reportId`. Never trust a JWT decoded by the client in JS, or trust an unverified `isAdmin` field.

## 8. When Adding POST/PUT/DELETE Operations

Write and delete actions require authorities **distinct from read** as well as status/owner policies. Example snippet (not part of the standalone GET project above):

~~~java
@PreAuthorize(
    "hasAuthority('report:approve') and " +
    "@reportPolicy.canApprove(authentication, #p0)"
)
public void approve(long id) {
    // Update status only after authorization passes.
}
~~~

You must write a real `canApprove` method before using the snippet. Approval policy might require the user to be assigned, in the right tenant, in an approvable status, and not self-approving their own document. Never infer approve permission from seeing a button or having read permission.

Practices needed when going to production:

- **Constrain DB queries** using verified identity, e.g., `WHERE id = :id AND tenant_id = :trustedTenantId`; for ownership, add owner predicates or dedicated policy logic. Never use client-supplied `tenantId` as a trusted value.
- **Avoid TOCTOU:** between check and update, owner/status may change; consider conditional updates, optimistic locking, transactions, and row-count checks.
- **Bulk/list/export:** check permissions on every record; never return all reports and let JavaScript filter them, because the data has already leaked in the response.
- **Files/download:** do not merely hide download links; endpoints or signed download URLs must enforce resource authorization and expiration.
- **Cache:** cache keys must include principal/tenant when data depends on permissions; never reuse another user's cached response.
- **Audit:** log principal, action, ID, allow/deny result per data policy; never log credentials or sensitive content.
- **CSRF:** maintain proper protection for unsafe HTTP methods when browsers use sessions/cookies or auto-sent credentials; never disable CSRF to “fix 403” without understanding the authentication model.

## 9. Common Mistakes and How to Fix Them

**Only `anyRequest().authenticated()`.** Any logged-in user can call the API without function/owner checks. Fix with method/path rules and object-level policies.

**Only `hasRole('USER')`.** Every regular user has this role; user A can access record B. Check owner/tenant alongside function permissions.

**Permissions live solely in the UI.** Hiding buttons, disabling controls, CSS `display:none`, or route guards do not block HTTP requests; the backend must make the decision.

**Permissions live solely in the controller.** New controllers, message handlers, or other service methods can bypass them; move core policies to the business layer and write direct service tests.

**`@PreAuthorize` has no effect.** Verify `@EnableMethodSecurity`, Spring proxies, and avoid self-invocation. Never manually instantiate `new` for protected services.

**Sending owner/tenant from the client to decide access.** Request body/query/headers can be forged; always verify against server-side principal and domain data.

**Returning the full dataset and filtering on the frontend.** The API response still carries unauthorized data. Filter at the query/server layer before serialization.

**Confusing 401/403/404.** HTTP status depends on rules; tests must show whether an action was permitted and whether unauthorized data was exposed. 404 can be used to limit existence disclosure, but changing status codes never replaces policy.

**Testing only allowed flows.** Add anonymous, missing-permission, wrong-owner, wrong-tenant, non-existent ID, elevated-permission, bulk, and direct-service tests.

**Confusing CORS/CSRF with authorization.** CORS does not stop intentional API clients; CSRF does not decide who owns a report.

## 10. Process for Auditing a Feature with Hidden Buttons

1. Identify the exact HTTP method/path the button calls, what ID/body it sends, and what side effects it causes.
2. List function permissions and resource policies: owner, tenant, reviewer, status.
3. Test HTTP **without the UI** using MockMvc or an API client as anonymous, under-privileged, authorized, wrong-owner, and cross-tenant users.
4. Inspect `SecurityFilterChain` config and service/domain authorization; policies must take identity from trusted authentication.
5. Add negative tests proving responses contain no unauthorized data and the database remains unchanged when denied.
6. Check alternative entry points: GraphQL, batch, export, file URLs, jobs, legacy APIs, new endpoints.
7. Once the backend is secure, keep UI button-hiding to improve UX, aligned with `403`/`404` error handling.

### Review Checklist

- [ ] Hiding/disabling buttons is not treated as a security control.
- [ ] Every endpoint has authentication and proper function-level authorization.
- [ ] Every resource enforces required owner/tenant/status checks.
- [ ] Never trust `isAdmin`, `ownerId`, or `tenantId` from the client.
- [ ] Deny-by-default and service/domain-layer guards are in place.
- [ ] No bypasses via self-invocation/proxy issues or alternative APIs.
- [ ] Tests exist for anonymous, missing permission, wrong owner, right owner, and elevated permissions.
- [ ] POST/PUT/DELETE, bulk/export/cache/file download have dedicated policies.
- [ ] No data is disclosed before the server decides allow.

## Official Documentation and References

- [Spring Security — HTTP Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing with MockMvc and @WithMockUser](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [OWASP API Security Top 10:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Top 10 — Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/)

**Self-practice exercise:** add an approval endpoint allowed only for users with `report:approve` who are assigned to that specific report. Write tests for missing authority, wrong resource, right resource, and client sending `isAdmin=true`. The server itself must deny the first three unauthorized requests regardless of whether the frontend hides or shows the button.