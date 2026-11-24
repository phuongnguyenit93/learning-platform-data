# Successful Login Without Function-Level Authorization Checks

## 1. The Problem: Authenticated Users Can Still Perform Unauthorized Actions

A user entering a valid username and password only proves that the system has **authenticated** their identity. Whether that person has permission to use a specific **function** — approving an invoice, exporting data, locking an account, updating prices, or deleting a report — is a separate **authorization** decision that must be enforced by the server for each sensitive operation.

A vulnerability arises when the application checks “is the user logged in?” but skips “is this person allowed to perform this operation?”. For example, a user who is only permitted to **view** reports can still successfully invoke the **publish** report operation because both functions sit behind the same **authenticated()** rule. Hiding the “Publish” button in the UI does not prevent HTTP requests from being sent directly.

This is a form of **Broken Function Level Authorization (BFLA)**, ranked by OWASP as **API5:2023** in the API Security Top 10. The consequences depend on the missed function: privilege escalation, unauthorized data reading/exporting, configuration changes, unauthorized approvals, data deletion, or operational disruption.

### Learning Objectives

After this lesson, you can:

1. Distinguish successful authentication from the decision to allow execution of a function.
2. Identify points where permission checks are easily missed: controllers, administrative endpoints mixed into regular APIs, new HTTP methods, reused services, and operations executed outside the UI.
3. Design an authorization matrix by **subject – operation – resource – condition** and define deny-by-default.
4. Protect functions at the HTTP layer using Spring Security and at the service layer using method security.
5. Test both **allowed** and **denied** cases, including requests coming from validly logged-in accounts.
6. Distinguish missing function-level permissions from missing permissions on a specific data object.

**Scope:** Java 17+, Spring Boot 3.x, Spring Security 6.x applications on Servlet/Spring MVC. The syntax and filters for Reactive/WebFlux applications differ in configuration, though the authorization principles are the same.

## 2. The Relationship Between Authentication, Function Permissions, and Data Permissions

Consider a reporting system with two actions:

- **Read report:** requires the **report:read** authority.
- **Publish report:** requires the **report:publish** authority.

An account with only `report:read` that logs in validly is **allowed to view** but **must be denied** when publishing.

~~~text
HTTP Request
  │
  ├── Valid authentication present?
  │     ├── No → handled by authentication entry point
  │     └── Yes
  │          │
  │          ├── Authorized to perform function? (report:publish)
  │          │      ├── No → deny, do not run business logic
  │          │      └── Yes
  │          │          │
  │          │          ├── Authorized for this object? (if applicable)
  │          │          │      ├── No → deny
  │          │          │      └── Yes → execute business logic
  │          │          │
  │          │          └── Record outcome for auditing
~~~

| Check | Question | Example |
| --- | --- | --- |
| Authentication | Who is sending the request? | User Alice is logged in |
| Function permission | Is Alice allowed to call the publish operation? | Does Alice have `report:publish`? |
| Object permission | Is Alice allowed to publish **report 42**? | Does the report belong to a tenant/department Alice is allowed to access? |
| Contextual condition | Are there additional conditions at invocation time? | Is the report still in DRAFT status? |

**BFLA** primarily occurs when checking the **action/function** is missing. **Broken Object Level Authorization (BOLA/IDOR)** occurs when an action is inherently valid, but the user can operate on an **object that does not belong to them**, for example changing the ID from their own report to someone else's report. Both types of vulnerabilities can appear simultaneously: having the `report:publish` permission does not mean being allowed to publish every report.

Similarly, Spring Security distinguishes **roles** (typically mapped to authorities with the `ROLE_` prefix) from **authorities** such as `report:publish`. When using `hasAuthority('report:publish')`, it checks that exact authority string; the framework does not automatically infer that any arbitrary role also has publish permission.

## 3. Common Symptoms and Root Causes

### 3.1. Configuration Only Requires Login

The following snippet is merely an **example of misconfiguration regarding function-level authorization**:

~~~java
// Illustrates an anti-pattern, not a recommended configuration.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports/**").authenticated()
    .anyRequest().authenticated()
);
~~~

This rule enforces authentication but **does not distinguish** GET for viewing a report from POST for publishing. If the controller has no other authorization step, a logged-in user with only read permission can still invoke the publish function.

Avoid assuming that a configuration like the above is **always** vulnerable: the service/controller might have its own permission checks. The mistake is relying on `authenticated()` as if it already proved permission for every operation.

### 3.2. Only Hiding Buttons in the UI

~~~javascript
// Frontend illustration; this only controls the UI.
if (!currentUser.permissions.includes("report:publish")) {
    publishButton.hidden = true;
}
~~~

Permission data in the browser can be tampered with, and an HTTP client does not need to interact with a button. The frontend can improve user experience, but the **server** must verify permissions at the point of execution.

### 3.3. Same URL with Different HTTP Methods

`GET /api/reports/42` may be a read operation, whereas `POST /api/reports/42/publish` or `DELETE /api/reports/42` modifies data. If a rule only relies on a path prefix or omits the HTTP method, switching from a read request to a write request can bypass the intended rule.

Sensitive functions do not always have an `/admin` prefix. Paths like `/api/reports/export`, `/api/users/bulk-update`, or `/api/orders/approve` can reside in regular controllers. You must inventory by **business action**, not just by looking at URL names.

### 3.4. One Call Path Is Checked, Another Is Not

An operation can be invoked from an HTTP controller, queue consumer, scheduled job, admin command, or another service. Checking permissions solely in one controller is not enough to protect all call paths through the same service. It is necessary to identify the execution point responsible for checking the identity/permissions of each caller type, especially for background jobs using a service identity.

### 3.5. Expanding Functionality Without Updating Policy

Adding a new endpoint, API version, alias, or HTTP method while still relying on a generic `authenticated()` rule. This is why the **deny by default** rule and regression testing for undeclared paths bring tremendous value.

## 4. Defining Policy Before Writing Code

For a small reporting application, an illustrative permission policy is as follows:

| Subject | GET /api/reports/42 | POST /api/reports/42/publish | DELETE /api/reports/42 |
| --- | --- | --- | --- |
| Unauthenticated | Deny | Deny | Deny |
| READER with `report:read` | Allow | Deny | Deny |
| PUBLISHER with `report:publish` | Deny if missing `report:read` | Allow | Deny |
| Logged-in user without either permission | Deny | Deny | Deny |

This table intentionally separates **report:read** and **report:publish**: in a real product, a role might be granted both permissions or inherit them per policy, but one should not automatically assume someone with publish permission naturally has read permission.

Permission design practices:

1. **List functions** from business workflows: view, create, edit, approve, export, delete, restore, invite user, change permissions, bulk operations.
2. **Define least-privilege permissions** per action, e.g., `report:read` and `report:publish`; grant them only to the users or roles that need them.
3. **Attach policies to every entry point**: URI + HTTP method at the request layer; business methods at the service layer when protection against other call paths is needed.
4. **Deny by default** for endpoints/methods without explicitly declared permissions. When adding new functionality, actively add the policy.
5. **Check additional object conditions** after function permission: owner, tenant, data classification, workflow status, or compliance policy, if the business requires it.
6. **Write negative tests for each permission**: an account may log in validly yet must still be denied on functions not granted to it.

Policies must be checked server-side using a trusted `Authentication` and system-managed permission data. Do not use self-declared headers like `X-Role: ADMIN` or a `role` field in the JSON request as the source of authority without a secure verification step.

## 5. Configuring Spring Security: Function Checks at HTTP and Service Layers

### 5.1. HTTP Layer: Match Path, Method, and Specific Permission

A safer configuration must distinguish read/publish, check authorities, and deny the remaining paths:

~~~java
// Illustrative snippet; complete example and tests are in Section 6.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/*")
        .hasAuthority("report:read")
    .requestMatchers(HttpMethod.POST, "/api/reports/*/publish")
        .hasAuthority("report:publish")
    .anyRequest().denyAll()
);
~~~

Spring Security evaluates request matchers in declaration order and applies the **first matching matcher**. If `.requestMatchers("/api/**").authenticated()` is placed before specific permission rules, the overly broad rule can shadow the rules behind it. Keep specific rules first and the default rule at the end; test both ordering and overlapping patterns.

In the example, `*` represents a single path segment. The default `denyAll()` rule does not mean an application can never have public endpoints; if a public health check or login endpoint is needed, define an intentional exception and test it accordingly. With multiple `SecurityFilterChain`s, ensure the chain containing the policy is actually selected for the endpoint to be protected.

### 5.2. Service Layer: Protecting Business Actions

~~~java
// Inside a Spring-managed service, with @EnableMethodSecurity.
@PreAuthorize("hasAuthority('report:publish')")
public String publish(long reportId) {
    return "published:" + reportId;
}
~~~

`@EnableMethodSecurity` activates method security interceptors; `@PreAuthorize` checks permissions **before invoking the method body**. This is especially valuable when the service is used by multiple controllers or other call paths that still hold an appropriate `Authentication` context.

**Limitations of Spring AOP:** method security typically relies on proxies. Calling `new Service()` or calling from another method on the same object via `this.` can bypass the interceptor. Do not write a test that only calls a manually instantiated object and conclude the policy works. For background tasks without a logged-in user, clearly design the service identity and authorization flow rather than arbitrarily creating default admin privileges.

### 5.3. HTTP 401 and 403 Are Not Two Types of Permissions

- **401 Unauthorized:** typically indicates a request without valid authentication credentials in APIs using HTTP Basic/Bearer authentication.
- **403 Forbidden:** typically indicates authenticated, but lacking sufficient permission to perform the function.
- **302 Redirect:** may appear in applications using form login, when an unauthenticated request is redirected to the login page.
- **404 Not Found:** sometimes used intentionally to avoid disclosing the existence of a resource, though 404 itself does not prove the policy checked permissions properly.

Do not write tests relying solely on 401/403 while ignoring the actual authentication configuration. Especially for POST/PUT/PATCH/DELETE, **CSRF** is an independent check: a missing CSRF token can return 403 even when function permissions are correct, masking authorization test errors. When testing POST operations using cookies/sessions, provide a valid CSRF token if the application enables CSRF, then verify authorization.

## 6. Runnable Spring Boot 3.x / Java 17+ Example with JUnit 5

The following example contains the controller, service, security configuration, and tests right inside **a single test file**. It can be placed into a Spring Boot 3.x project with Gradle and compatible dependencies. There is no real database or DB writes; the code keeps deterministic outputs to focus on policy.

### 6.1. Required Dependencies

~~~groovy
// Inside dependencies of a Spring Boot 3.x project with plugins already configured.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

No database or real accounts need to be created. `@WithMockUser` from Spring Security Test provides a mock `Authentication` with authorities specified by the test. HTTP Basic is enabled specifically in the fixture so the unauthenticated case returns 401 and can be tested.

### 6.2. Complete Test File

Create **src/test/java/demo/authorization/FunctionAuthorizationTest.java**:

~~~java
package demo.authorization;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest(classes = FunctionAuthorizationTest.App.class)
@AutoConfigureMockMvc
class FunctionAuthorizationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    static class App {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports/*")
                        .hasAuthority("report:read")
                    .requestMatchers(HttpMethod.POST,
                            "/api/reports/*/publish")
                        .hasAuthority("report:publish")
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults());

            // Keep default CSRF. POST tests use .with(csrf()).
            return http.build();
        }

        @Bean
        ReportService reportService() {
            return new ReportService();
        }

        @Bean
        ReportController reportController(ReportService service) {
            return new ReportController(service);
        }
    }

    // Service bean created/proxied by Spring to enforce @PreAuthorize.
    static class ReportService {

        @PreAuthorize("hasAuthority('report:read')")
        public String read(long id) {
            return "report:" + id;
        }

        @PreAuthorize("hasAuthority('report:publish')")
        public String publish(long id) {
            return "published:" + id;
        }
    }

    @RestController
    @RequestMapping("/api/reports")
    static class ReportController {
        private final ReportService service;

        ReportController(ReportService service) {
            this.service = service;
        }

        @GetMapping("/{id}")
        String read(@PathVariable("id") long id) {
            return service.read(id);
        }

        @PostMapping("/{id}/publish")
        String publish(@PathVariable("id") long id) {
            return service.publish(id);
        }
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService service;

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void loggedInReaderCannotPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherCanPublish() throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("published:42"));
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void publisherWithoutReadPermissionCannotRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void unexpectedHttpMethodIsDenied() throws Exception {
        mvc.perform(delete("/api/reports/42").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void authenticatedUserWithoutPermissionCannotPublish()
            throws Exception {
        mvc.perform(post("/api/reports/42/publish").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void directServiceCallCannotBypassMethodSecurity() {
        assertThrows(AccessDeniedException.class,
                () -> service.publish(42L));
    }

    @Test
    @WithMockUser(authorities = "report:publish")
    void serviceAllowsAuthorizedPublisher() {
        assertEquals("published:42", service.publish(42L));
    }
}
~~~

**Run in a Spring Boot 3.x Gradle project configured with Java 17+ and JUnit 5:**

~~~bash
./gradlew test --tests "demo.authorization.FunctionAuthorizationTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "demo.authorization.FunctionAuthorizationTest"
~~~

**Expected result:** **10 tests pass**. This is expected from the fixture logic, not a recorded Gradle execution log. HTTP results verified by MockMvc: 200 for the two authorized endpoint calls, 401 for the two unauthenticated calls, 403 for requests lacking permission or with an unallowed HTTP method; the last two tests call the service directly and verify `@PreAuthorize`. There is no fixed stdout because the tests do not print to the console.

**Notes for reuse:** This is a standalone fixture in test code, using `@SpringBootConfiguration` with `@EnableAutoConfiguration` to build a minimal application context and `@Bean` to explicitly register the controller/service. Production applications may use `@SpringBootApplication`, `@RestController`, `@Service`, and configure `SecurityFilterChain` in separate files; beans must still be registered in the Spring container. Spring Boot 4 / Spring Security 7 may differ in starters, minimum Java version, or test configuration; consult the documentation for your exact version before copying the file verbatim.

## 7. Explaining the Tests: Why Successful Login Is Not Enough

### 7.1. The Most Important Case: Valid Account Lacking Permission

The **loggedInReaderCannotPublish** test provides an `Authentication` with the `report:read` authority. This user **is logged in** and holds a valid read permission. MockMvc sends `POST /api/reports/42/publish` with a valid CSRF token, yet the POST rule requires `report:publish`, so it receives **403**. The test directly demonstrates that successful authentication does not automatically grant function permissions.

If you replace the POST rule with `authenticated()` and remove `@PreAuthorize` on the service, this deny test will no longer protect the operation; that is a clear example of the defect to catch. If you only write `anonymousCannotPublish`, the application could still suffer from a bug allowing **every logged-in account** to publish while the anonymous test remains green.

### 7.2. Testing an Authorized User

The **publisherCanPublish** test uses the `report:publish` authority, sends POST with CSRF, and expects 200 with content `published:42`. Both the HTTP rule and `@PreAuthorize` on the service allow it, so the controller call succeeds.

Testing permissions only for denial without allowed cases can lead to locking down all functionality. **Both positive and negative tests** are needed to verify the policy is right.

### 7.3. Testing That Other Permissions Are Not Inferred

The **publisherWithoutReadPermissionCannotRead** test illustrates that an account with only `report:publish` does not automatically possess `report:read`. Having a production role hold both authorities must come from explicit permission assignment or role hierarchy configuration, not an implicit assumption.

### 7.4. Testing Unlisted HTTP Methods

The **unexpectedHttpMethodIsDenied** test sends DELETE to the same path for a logged-in user. Because there is no allow rule for DELETE, **anyRequest().denyAll()** blocks the request before business logic executes. This is an important check when adding endpoints or accidentally creating new mappings.

### 7.5. Testing the Service to Avoid Missing Other Call Paths

The **directServiceCallCannotBypassMethodSecurity** test retrieves `ReportService` from the Spring context. It calls `publish` directly through the bean and still receives `AccessDeniedException` when holding only `report:read`. The test confirms the service protection layer operates independently of whether an HTTP request is blocked.

If you manually instantiate **new ReportService()**, the Spring AOP interceptor has no opportunity to apply and the method body can be invoked despite lacking permissions. Therefore, method security tests must invoke a Spring-managed bean (or test authorization decision logic separately in unit tests), rather than inferring security behavior from a manually instantiated object.

## 8. Security Test Map by Entry Point

| Scenario | Expected Test | Defect Detected |
| --- | --- | --- |
| Unauthenticated call to sensitive function | Blocked by authentication mechanism | Missing authentication |
| Logged in with read-only permission calling write operation | 403 / denied | Classic **BFLA** |
| User with write permission calling write operation | Succeeds | Proves functionality still works |
| Same endpoint with a different HTTP method | Denied if not granted | Overly broad rule / missing method check |
| New API version/alias of a sensitive operation | Same policy or deny by default | Missed entry point |
| Calling service via bean from another path | Same authorization decision | Controller-only protection |
| User allowed to call function but changes ID to another object | Denied if not owner / not granted | **BOLA**, additional check needed |
| Bulk operation containing both valid and invalid items | Blocked or processed per item per policy | Missing permissions on bulk elements |
| Permission revoked while session is still active | Denied per new effective policy | Stale permissions in cache/token |
| Disabled account or mismatched tenant | Denied at designated checkpoint | Missed contextual condition |

The tests earlier in the lesson are **functional authorization tests**. Object-level, multi-tenant, revoked-permission, and bulk tests are additional layers needed when the business domain actually supports them. Do not cram all logic into a long SpEL expression that is hard to audit; move complex policies into an independently tested authorization bean.

## 9. How to Implement in Real Systems

### 9.1. Identify the Source of Truth for Permissions

Permissions can be managed in an IAM, a relational user–role–permission database, or a centralized policy system. Regardless of the choice, every request must use a trusted identity and an authorization decision that can be explained and audited.

**Roles (RBAC)** fit common functional permissions like `ADMIN`, `EDITOR`, `APPROVER`. **Authorities/permissions** represent specific actions such as `report:publish`. **Attribute-Based Access Control (ABAC)** or resource policies suit tenants, owners, project groups, or record statuses. They can be combined, but the meaning of each permission must be clearly documented rather than letting each controller interpret it differently.

### 9.2. Enforce Authorization Near Where Operations Mutate Data

For high-impact commands, place an authorization check at the HTTP boundary and another at the business execution point when the service can be reused. Rules must apply before side effects occur (DB writes, sending notifications, publishing events, calling external services). If the policy depends on data state that can change concurrently, make the decision within the same transaction or using a conditional update operation to avoid checking stale state and then writing against new state.

**Illustrative** business logic example:

~~~java
// Design idea, not a standalone Java program.
@PreAuthorize("hasAuthority('report:publish')")
public void publish(long reportId) {
    Report report = repository.findById(reportId).orElseThrow();
    policy.requireCanPublish(
        currentPrincipal(), report.getTenantId(), report.getStatus());
    repository.publishIfStillDraft(reportId, report.getVersion());
}
~~~

This snippet highlights two layers of conditions: **being allowed to use the publish function** and **being allowed to publish a specific report in a valid state**. The `repository`, `policy`, and `currentPrincipal` functions are hypothetical components that need to be implemented and tested according to the real project.

### 9.3. Do Not Use System Privileges as Caller Privileges

Background tasks or service-to-service calls lack an interactive user session. They need their own service identity and least-privilege permissions; if executing on behalf of a user, the delegation context and allowed scope must be defined. Do not automatically run sensitive commands with admin privileges simply because the task did not originate from a web controller.

### 9.4. Permission Changes Must Take Effect by Design

If a JWT or session holds authorities for a long duration, permission revocation is not necessarily reflected immediately on every request. Design TTLs, token refresh, dynamic permission lookup, permission versioning, or session revocation based on the sensitivity of the function. Add tests for an account whose publish permission was just revoked; storing permissions in a token and trusting them forever by default is insufficient.

### 9.5. Log for Investigation Without Leaking Data

Record audit logs with **user/service identity, action, safe resource ID, allow/deny decision, timestamp, and correlation ID**. Avoid logging passwords, bearer tokens, or sensitive data. Monitor repeated denials on administrative functions or sensitive actions; detection does not replace server-side permission checks.

## 10. Misconceptions That Make Test Suites Falsely Green

| Practice | Why It Is Insufficient | Replace With |
| --- | --- | --- |
| Only testing unauthenticated access | Fails to detect privilege escalation by valid accounts | Add `logged-in-but-forbidden` tests |
| Relying only on frontend button state | Does not protect the endpoint | Check authority on the backend |
| Only adding `anyRequest().authenticated()` | Every logged-in user passes under the same condition | Use `hasAuthority`/`hasRole` per operation |
| Matching `/**` before detailed rules | The first rule can block subsequent rules | Place specific matchers before the default rule |
| Only testing GET, not POST/DELETE | Misses data-modifying operations | Matrix of route × method × actor |
| Testing POST without CSRF token when CSRF is on | 403 may come from CSRF, not proving authorization | Use `.with(csrf())` in MockMvc |
| Tests calling `new Service()` | Bypasses proxy, `@PreAuthorize` does not run | Inject Spring bean and test directly |
| Forgetting `@EnableMethodSecurity` | Annotations may not be applied | Enable method security, add deny tests |
| Checking function permission without owner/tenant check | BOLA/IDOR may still exist | Check object-level permissions |
| Using `@WithMockUser` as proof of production roles | Tests supply mock authorities, not verifying IAM mapping | Test role/claim → authority mapping separately |
| Treating every error as HTTP 403 | Hard to distinguish unauthenticated from unauthorized | Test properly per authentication entry point |
| Believing only changing URLs is privilege escalation | HTTP methods, aliases, and internal call paths also matter | Inventory all entry points and tasks |

**Remember:** CSRF, CORS, authentication, and authorization are distinct mechanisms. CORS does not prevent non-browser HTTP clients from sending requests; a valid CSRF token does not grant publish permission; successful login does not grant publish permission either. Security filters must address each objective explicitly.

## 11. Review Process for a New or Existing Function

You can use the following checklist during code reviews and before release:

1. **Name the business action.** E.g., “publish report” instead of just seeing POST.
2. **Identify allowed subjects.** What is the minimum permission, which role owns it, and are there status/tenant conditions?
3. **Find every legitimate entry point.** Current endpoints, aliases, API versions, internal controllers, event handlers, and task commands.
4. **Verify the enforcement mechanism.** Rule matches exact method/path, proper order, service protected when needed, `denyAll` default for undeclared paths.
5. **Test allow/deny pairs.** Authorized user succeeds; **logged-in user lacking permission** is blocked before business impact.
6. **Test boundaries.** Unexpected URLs, unexpected methods, recently revoked permissions, cross-tenant resources, and bulk operations.
7. **Check operations.** Denial logs, traceability, and how permissions are changed/revoked when needed.
8. **Attach regression tests to the function.** When modifying a controller or adding routes, update the corresponding tests and permission matrix.

Do not check only the 403 status code; for functions with side effects, confirm **data state does not change** when the request is denied. Measure actual outcomes such as record count, record status, or emitted event count in a deterministic fixture. An API returning an error after already writing data still fails security requirements.

## 12. Practice Exercises

**Scenario A — Admin endpoint mixed into regular APIs.** The application has `POST /api/users/{id}/disable`, but `SecurityFilterChain` only requires `authenticated()`. Define the **user:disable** permission, add the exact rule, and test that a logged-in `USER` account gets 403 while a granted account succeeds. Do not judge sensitivity solely by whether the URL contains the word `admin`.

**Scenario B — Data export function.** `GET /api/reports/export` can perform a sensitive task despite using HTTP GET. Create a separate `report:export` permission, require server-side permission checks, and test that `report:read` does not automatically grant export permission. Classify sensitivity by **action**, not just by HTTP method.

**Scenario C — Function and data permissions.** A user has `report:publish` and is only allowed to publish reports for tenant A. Design tests so they succeed in publishing a resource belonging to tenant A, but are denied for a report of tenant B. This is object-level control alongside BFLA.

**Scenario D — Service call paths.** Add a second controller that also calls `ReportService.publish`. Prove that a test calling the service bean directly still denies when lacking permission, then verify the new endpoint does not accidentally bypass the policy.

**Scenario E — Regression.** Intentionally replace the POST rule with `authenticated()` **only in an isolated learning environment**, keep `@PreAuthorize` on the service, and observe which tests still block. Next, also remove `@PreAuthorize` in the learning fixture and see the deny test fail. Restore the correct configuration. This exercise helps distinguish the value of each test layer and avoids thinking one green test proves every call path is safe.

**Self-assessment questions:** Which rule can still deny an account that has logged in validly? If the system adds a new HTTP method, how does the default rule handle it? If the controller has the right permissions but the service is called through another path, are permissions still checked? Have you checked both function-level and object-level permissions?

## 13. Official References

- OWASP API Security Top 10 — API5:2023 Broken Function Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Spring MVC Test Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Method Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html
