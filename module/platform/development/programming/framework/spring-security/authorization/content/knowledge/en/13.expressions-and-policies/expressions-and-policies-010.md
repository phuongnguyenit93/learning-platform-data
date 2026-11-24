# Boundaries Between Authorization, Input Validation, and Business Invariants

> **Scope:** Spring Security – authorization, **Expressions and policies** group. This lesson separates three questions commonly conflated in Java/Spring applications: **who is allowed to act?**, **is the input valid?**, and **does the current business state allow the action?** The content uses Spring Boot Servlet, Spring Security method security, Jakarta Bean Validation, and Java 17+ examples. Specific choices must be adapted to each application's API contract and domain model.

## 1. Learning objectives

After this lesson, you will be able to:

1. Classify a rule as **authorization**, **input validation**, **business invariant**, or an overlapping rule.
2. Place each check in the right layer: security filter/method, DTO/controller, service/domain, and database.
3. Predict differences among requests rejected for missing permission, invalid data, and state conflicts; explain when HTTP 400, 401, 403, 404, and 409 can appear.
4. Design check ordering to avoid data leakage, prevent partial updates, and preserve atomicity under concurrent access.
5. Test both HTTP and service call paths, including cases where one request violates multiple checks.

## 2. Three questions, three meanings

Suppose an invoice management application lets users approve invoices.

**Authorization** answers: *is the current subject allowed to perform this action on this resource?* For example: an employee holds authority `invoice:approve` and may only approve invoices within their assigned scope. Inputs are trusted identity/authorities and resource context; failure is typically a **deny** decision.

**Validation** answers: *does the submitted data match expected types, formats, structure, and input constraints?* For example: the approval reason must not be blank and has max length 120 characters; the ID must be positive. Data can be invalid even when the sender is an administrator.

**Business rule / invariant** answers: *is the action valid given the domain's current state and workflow?* For example: only `DRAFT` invoices may be approved; an already `APPROVED` invoice cannot be approved again; adjusted totals must not exceed a business threshold. This is a domain validity rule, not simply a granted permission.

Consider a `POST /api/invoices/42/approve` request:

| Scenario | Question checked | Classification |
| --- | --- | --- |
| Sender lacks `invoice:approve` | Allowed to use the approval feature? | Feature-level permission |
| Sender has approval permission, yet invoice belongs to another user/tenant | Allowed to act on **this** resource? | Resource-level permission |
| `reason = "   "` or 200 characters long | Does the payload satisfy input constraints? | Validation |
| Invoice is already `APPROVED` | Can it transition state again? | Business invariant |
| Invoice does not exist | Was the requested resource found? | Resource lookup; response also depends on security policy |
| Subject has permission, valid payload, invoice is `DRAFT` | All three layers pass | Can execute, while still enforcing transaction/concurrency |

**A 403 result does not prove the payload is valid; a 400 result does not prove the caller is authorized.** Each layer answers a distinct question.

### 2.1. Do not classify solely by annotation name

- `@PreAuthorize`, `AuthorizationManager`, and `hasAuthority(...)` typically represent **authorization**.
- `@Valid`, `@NotBlank`, `@Size`, and `@Positive` typically represent **validation**.
- `if (invoice.status() != DRAFT)` or `invoice.approve()` typically represent **business rules**.
- `@Transactional`, optimistic locking, and DB constraints maintain consistency, yet **do not replace** the three checks above.

Putting a condition in the wrong layer can leave the API seemingly functional while returning misleading status codes, leaking data, or breaking reuse from jobs/message listeners.

## 3. Layer-by-layer responsibility boundaries

~~~text
HTTP client
   |
   v
SecurityFilterChain
   |  authentication, CSRF (when applicable), URL/feature permissions
   v
Controller + binding + Bean Validation
   |  parse JSON, @Valid, size/format
   v
Service's Spring proxy
   |  @PreAuthorize / AuthorizationManager: invocation permissions
   v
Service + Domain
   |  load resource within trusted scope
   |  object/tenant/ownership permissions, DRAFT status, invariants
   v
Repository / DB
   |  WHERE tenant_id, update condition, version/lock, transaction
   v
Categorized result or error
~~~

This diagram shows **functional boundaries**, without guaranteeing that every Spring advisor runs in one fixed order. For instance, MVC can bind and validate controller arguments before a service call hits `@PreAuthorize`; `@Transactional` and method-security advisors have configurable ordering. Never rely on implicit ordering for safety.

On HTTP paths, the filter chain is usually the right place to reject unauthenticated or generally unauthorized requests early; controllers handle payload validation; services enforce resource-level permissions and invariants; the DB guarantees correctness under concurrent contention.

### 3.1. When is a rule security vs. business logic?

Genuine overlap exists. For example, "only a team lead may approve when the amount exceeds a threshold" refers to both **the approver's role** and **the invoice value**. Split it into meaningful parts:

~~~text
canApprove(actor, invoice):
  does actor have approve authority?
  same tenant and assigned?
  if invoice.amount > threshold: does actor have above-threshold approval permission?

businessPrecondition(invoice):
  is invoice still in DRAFT?
  is invoice unlocked in the accounting period?
  is related data still consistent?
~~~

Conditions based on **actor/authorities and target object** typically belong to authorization policy; conditions describing **valid domain state regardless of who calls** belong to domain invariants. Both can live in a domain service, yet keep naming, exception types, and tests distinct.

Note: business policies may also restrict "who may operate." Thus the boundary lies in **rule intent and failure semantics**, not a rigid split by keyword or class.

## 4. Authorization: feature-level and resource-level permissions

### 4.1. Feature-level permission

An invoice-approval endpoint can require the `invoice:approve` authority:

~~~java
// Snippet inside Spring Boot Servlet SecurityFilterChain configuration.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
        .hasAuthority("invoice:approve")
    .anyRequest().authenticated()
);
~~~

This is a **request-level** decision. URL permissions stop most unauthorized callers, yet do not prove a specific invoice belongs to their scope.

### 4.2. Method-level permission

Enable method security via `@EnableMethodSecurity`. The Spring Security starter **does not automatically enable** method-level authorization.

~~~java
// Snippet inside a Spring-managed service.
@PreAuthorize("hasAuthority('invoice:approve')")
public InvoiceView approve(long id, String reason) {
    // Resource-level conditions still need to be checked.
}
~~~

If `@PreAuthorize` fails, the method is never invoked. Annotations only apply when calls actually pass through Spring's interception mechanism, typically a proxy; internal `this.approve(...)` calls inside the same bean bypass the proxy.

### 4.3. Object and tenant permissions

"Alice may approve Alice's invoice" is a resource-level permission. Never accept a client-supplied `ownerId` or `tenantId` as proof of permission. The service must retrieve the actor from the trusted `SecurityContext`, fetch the resource from the repository within the proper tenant scope, and verify ACL/assignment against real data.

~~~java
// Code sketch inside service, assuming invoice is already loaded.
Authentication actor = SecurityContextHolder.getContext().getAuthentication();
if (actor == null || !invoice.owner().equals(actor.getName())) {
    throw new AccessDeniedException("Access denied");
}
~~~

With multi-tenancy, use a **stable identifier** from the token/identity provider rather than relying solely on display names; embed tenant constraints in queries and check at the service/data layers. To avoid revealing whether another tenant's resource exists, an API may intentionally return a uniform 404 for both missing and invisible resources. **HTTP 404 in this case still represents a security decision per the API contract**, not a validation error.

### 4.4. How many places need checks?

Layers play complementary roles:

- **Web:** closes sensitive routes, enforces authentication and coarse permissions, handles sessions/CSRF.
- **Service:** protects business actions regardless of invocation via HTTP, jobs, message consumers, or tests.
- **Repository/DB:** bounds data scope, ensures atomic updates, and prevents races.

Never treat hiding an "Approve" button in the UI as enforcement. Users can still call the API directly. Nor does SQL returning only owner-matched rows automatically mean every action on those rows is permitted.

## 5. Validation: data must be valid, regardless of who calls

Input example:

~~~java
public record ApproveRequest(
        @NotBlank(message = "reason is required")
        @Size(max = 120, message = "reason is too long")
        String reason) {
}
~~~

With `jakarta.validation.constraints.NotBlank` and `Size`, a `null`/blank reason or one exceeding 120 characters is invalid. Placed at the request entry point:

~~~java
@PostMapping("/{id}/approve")
public InvoiceView approve(@PathVariable long id,
                           @Valid @RequestBody ApproveRequest request) {
    return service.approve(id, request.reason());
}
~~~

In Spring MVC, `@Valid @RequestBody` triggers Bean Validation when a provider is present; by default such constraint failures raise `MethodArgumentNotValidException` and HTTP 400. Malformed JSON can fail during deserialization even before Bean Validation. If the service is invoked from a CLI/job, `@Valid` on controller parameters **does not re-run automatically**; the service/domain must still guard essential preconditions.

Validation categories:

| Category | Examples | Nearest placement |
| --- | --- | --- |
| Type/structure | Valid JSON, required fields, parseable ID | HTTP binding/DTO |
| Size/format | `@NotBlank`, `@Size(max=120)`, `@Email` | DTO + Bean Validation |
| Cross-field input relations | `start <= end`, one-of-two options provided | Custom validator or value object |
| Validity outside HTTP | Positive amount, valid currency | Constructor/value object/service |
| DB constraints | NOT NULL, UNIQUE, CHECK | Database as last line of defense |

**Validation never decides access rights.** A request with `reason = "Reviewed"` is completely valid yet must still be denied if the user lacks `invoice:approve` or lacks access to the invoice.

Conversely, `@PreAuthorize("hasAuthority('invoice:approve')")` does not make `reason` valid, replace `@Size`, or sanitize bad input.

### 5.1. Avoid using validators to probe sensitive resources

A custom validator calling a repository to check "does invoice ID exist?" can trigger sensitive queries before authorization. Whenever a constraint depends on permissions and current resource state, check it at the service boundary under the proper security context and transaction. Separate structural validation (safe, permission-independent) from dynamic data checks (which can leak info if evaluated too early).

## 6. Business invariants: action and state conditions

Suppose the workflow is:

~~~text
DRAFT -> APPROVED
DRAFT -> CANCELLED
APPROVED -> (cannot be APPROVED again)
CANCELLED -> (cannot be APPROVED)
~~~

Even a user holding `invoice:approve` cannot make "approving an already approved invoice" valid by authority alone. The domain can return a **state conflict** error (e.g., 409 per REST contract), because the condition depends on current mutable state.

~~~java
// Domain logic sketch, not a standalone Java program.
if (invoice.status() != InvoiceStatus.DRAFT) {
    throw new InvoiceStateConflictException();
}
invoice.approve();
~~~

Distinction:

- **Rejected for missing permission:** changing the actor/authority could flip the decision.
- **Rejected because invoice is already APPROVED:** even switching the actor to an admin does not make a repeat approval valid, unless the business defines a dedicated override permission and workflow.
- **Rejected because reason is blank:** fixing the payload suffices if permission and state are already valid.

For payments, inventory, quotas, and concurrent approvals, invariants must be enforced at **atomic write time**, not just via a read-then-write `if`. Use transactions paired with pessimistic/optimistic locking, a version column, or conditional updates (e.g., `UPDATE ... WHERE status='DRAFT' AND version=?`); verify affected row counts. `@Transactional` alone **does not prevent all race conditions** and is not an authorization mechanism.

## 7. Check ordering: security, error messages, and side effects

A safe mental model is **check permissions on target data before revealing sensitive properties of that data**, while ensuring all invariants still hold at the exact moment of update.

A sensible order for an approval API:

1. Request passes authentication/CSRF/URL-level authorization.
2. MVC parses and checks payload shape (these steps may precede service-level authorization).
3. Method security blocks actors lacking the feature authority.
4. Service loads the resource within allowed scope; determines whether the actor has permission on the object; avoids disclosing hidden resources.
5. Checks business invariants on current state, then executes an atomic update.
6. Returns the result or appropriate error; logs/audits per policy without leaking secrets.

**There is no single "universal order" across all Spring apps.** Actual ordering depends on the filter chain, argument resolution, AOP advisors, transaction boundaries, and exception handlers. If 403 must take precedence over 400, place the guard in a layer that genuinely runs early enough (usually web/request level or policy before sensitive reads), rather than just adding an annotation and assuming order.

### 7.1. When a single request fails in multiple ways

Alice submits a blank reason for Bob's invoice without holding `invoice:approve`. Depending on where rules are enforced, the web filter may reject before reading the body; if enforcement is only on the service via method security, MVC may return 400 for invalid input before the service is invoked. That does not automatically indicate a security flaw, though it can violate a requirement to "confirm nothing about protected data." Write tests pinning the contract: unauthorized users must not infer existence or attributes of sensitive data from differing error messages.

### 7.2. Why not use `@PostAuthorize` to guard writes?

`@PostAuthorize` checks permission **after** the method body executes; if the method already committed to the DB, sent email, or called an external service, denying afterward cannot guarantee rollback. For mutating operations, favor `@PreAuthorize` plus object-level checks in the service before writing and atomic checks in the DB.

### 7.3. Notes on HTTP status codes

| Error and context | Common HTTP status | Key understanding |
| --- | --- | --- |
| Unauthenticated access to protected resource | 401 | Depends on authentication entry point; not automatic on every request |
| Authenticated yet lacking permission | 403 | Does not imply payload is invalid |
| Resource non-existent or intentionally hidden | 404 | Can be used to avoid disclosing existence |
| Invalid body/field | 400 | Common MVC default for `@Valid @RequestBody` |
| Domain constraint dependent on current state | 409 | Fits state conflicts; not every business error is 409 |
| Syntactically valid input violating semantic contract | 422 or 400 depending on API | No automatic universal mapping for all business rules |

A POST missing a **CSRF token** can return 403 even when the user holds the right authority and valid payload. CSRF protection is a request-safety concern, not a business state error. For APIs using HTTP sessions/cookies, keep CSRF protection enabled and supply tokens properly; MockMvc tests for unsafe methods need `with(csrf())`.

## 8. Spring Boot example: separating the three check groups

The example below builds a small application with in-memory storage to focus on decision boundaries:

- `SecurityFilterChain` + `@PreAuthorize` enforce authority `invoice:approve`.
- `@Valid ApproveRequest` validates input at the controller, and the service re-checks input invariants for non-HTTP callers.
- The service checks ownership against the current principal, intentionally returning 404 for both invisible and missing invoices.
- Only `DRAFT` transitions to `APPROVED`; other states return 409.
- `ConcurrentHashMap.compute` updates one key atomically in this in-memory demo. Real databases require transactions, concurrency control, tenant scoping, and constraints.

**`src/main/java/example/boundaries/BoundaryApplication.java`** — a single Java file for a Spring Boot Servlet project with the required dependencies:

~~~java
package example.boundaries;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.servlet.DispatcherType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                            .hasAuthority("invoice:approve")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // CSRF remains enabled by default; POST requires a valid CSRF token.
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo")
                        .authorities("invoice:approve").build(),
                User.withUsername("bob")
                        .password("{noop}demo")
                        .authorities("invoice:approve").build(),
                User.withUsername("viewer")
                        .password("{noop}demo")
                        .authorities("invoice:view").build());
        // {noop} is for learning only; real apps must use a secure password encoder.
    }
}

record ApproveRequest(
        @NotBlank @Size(max = 120) String reason) {
}

enum InvoiceStatus {
    DRAFT, APPROVED
}

record Invoice(long id, String owner, InvoiceStatus status, String reason) {
}

record InvoiceView(long id, InvoiceStatus status) {
}

@RestController
@RequestMapping("/api/invoices")
class InvoiceController {
    private final InvoiceService service;

    InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @PostMapping("/{id}/approve")
    InvoiceView approve(@PathVariable long id,
                        @Valid @RequestBody ApproveRequest request) {
        return service.approve(id, request.reason());
    }
}

@Service
class InvoiceService {
    private final Map<Long, Invoice> invoices = new ConcurrentHashMap<>(
            Map.of(
                    1L, new Invoice(1L, "alice", InvoiceStatus.DRAFT, ""),
                    2L, new Invoice(2L, "bob", InvoiceStatus.DRAFT, ""),
                    3L, new Invoice(3L, "alice", InvoiceStatus.APPROVED,
                                   "Already approved")));

    @PreAuthorize("hasAuthority('invoice:approve')")
    public InvoiceView approve(long id, String reason) {
        // Guard preconditions even when service is called outside MVC.
        if (reason == null || reason.isBlank() || reason.length() > 120) {
            throw new InvalidReasonException();
        }

        Authentication actor =
                SecurityContextHolder.getContext().getAuthentication();

        Invoice updated = invoices.compute(id, (key, current) -> {
            // Intentionally do not reveal resources outside actor's scope.
            if (actor == null || current == null
                    || !current.owner().equals(actor.getName())) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Invoice not found");
            }

            // Invariant does not depend on Alice's or Bob's permissions.
            if (current.status() != InvoiceStatus.DRAFT) {
                throw new InvoiceStateConflictException();
            }

            return new Invoice(current.id(), current.owner(),
                    InvoiceStatus.APPROVED, reason);
        });

        return new InvoiceView(updated.id(), updated.status());
    }
}

@ResponseStatus(HttpStatus.BAD_REQUEST)
class InvalidReasonException extends RuntimeException {
    InvalidReasonException() {
        super("Invalid approval reason");
    }
}

@ResponseStatus(HttpStatus.CONFLICT)
class InvoiceStateConflictException extends RuntimeException {
    InvoiceStateConflictException() {
        super("Invoice must be DRAFT");
    }
}
~~~

**Gradle dependencies** for a project with the Spring Boot plugin and dependency management enabled:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Do not treat the block above as a standalone `build.gradle` file. Place the app inside a Spring Boot project configured with the plugin/Gradle wrapper; you can run `./gradlew bootRun` (or `gradlew.bat bootRun` on Windows). When calling POST from a browser/client with CSRF protection, fetch and send the CSRF token per the app's mechanism; never just send HTTP Basic expecting POST to succeed. The tests below use `with(csrf())` to verify.

### 8.1. Why not merge all three decisions into a single SpEL expression?

An expression like the following is an example of *what not to use by default*:

~~~java
// Conceptual counterexample, not a production API:
@PreAuthorize("hasAuthority('invoice:approve') "
        + "and @store.isDraft(#p0) "
        + "and #p1.length() <= 120")
~~~

It merges authority, DB state, and input length into a single "access denied" label; it can produce wrong HTTP status codes, report invalid input as missing permission, and check state **before** the actual write transaction. Keeping validation on DTOs/value objects and business state in services/domain makes behavior easier to explain, test, and handle. You can use a policy bean in `@PreAuthorize` for object permissions, yet define clearly which conditions truly belong to authorization.

### 8.2. Why use `ConcurrentHashMap.compute`?

If two requests approve invoice 1 concurrently, the per-key update runs atomically in this example, so only one sees `DRAFT` and transitions to `APPROVED`; the other hits `InvoiceStateConflictException`. **That is a property of the demo's map**, not the default behavior of a JPA entity loaded and saved separately. When moving to a database, use transactions and real version/lock/conditional-update coordination; never carry over in-memory assumptions verbatim.

### 8.3. Why does the wrong owner return 404?

In this example, the app intentionally avoids disclosing invoices that do not belong to the owner. Both "does not exist" and "not visible" return 404 once feature-level authority passes. Another application might choose 403 if callers are already permitted to know an object exists. Pick one policy and apply it consistently across detail, search, export, update, and download endpoints.

## 9. Testing all three boundaries

Test requests via `MockMvc` to verify interactions across the filter chain, validation, and service AOP. The file below is an **integration test** for the app above. `@DirtiesContext` creates fresh in-memory state per test for isolation; this is convenient for docs, though slower than dedicated fixtures.

**`src/test/java/example/boundaries/BoundaryApplicationTest.java`**:

~~~java
package example.boundaries;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class BoundaryApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void validInputWithPermissionAndDraftSucceeds() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));
    }

    @Test
    @WithMockUser(username = "viewer", authorities = "invoice:view")
    void featurePermissionIsRequired() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void blankReasonIsValidationError() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"   \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void otherOwnersInvoiceIsHidden() throws Exception {
        mvc.perform(post("/api/invoices/2/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void alreadyApprovedInvoiceIsBusinessConflict() throws Exception {
        mvc.perform(post("/api/invoices/3/approve")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isConflict());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void postWithoutCsrfFailsBeforeBusiness() throws Exception {
        mvc.perform(post("/api/invoices/1/approve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"Reviewed\"}"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Meaning of the test suite:**

| Test | Checkpoint | Result |
| --- | --- | --- |
| Alice approves ID 1, valid reason | Permission + validation + invariant all pass | 200 |
| Viewer missing authority | Filter chain blocks before business | 403 |
| Alice sends blank reason | DTO Bean Validation | 400 |
| Alice sends Bob's ID 2 | Resource permission under hiding policy | 404 |
| Alice approves already-APPROVED ID 3 | State invariant | 409 |
| Alice sends POST without CSRF | Request protection independent of business | 403 |

Additions needed in a real project: concurrent request tests, service calls through proxy, security context in background jobs, tenant isolation, versioned DB updates, transaction rollback, and anti-enumeration 404/403 policy tests. When testing service validation outside HTTP, invoke the service through a Spring bean with mock authentication; never test annotations via `new InvoiceService()` and assume method security ran.

## 10. Standalone Java 17: comparing outcomes of the three failure types

This snippet only illustrates **decision classification**, without emulating Spring filters or proxies. Save as `BoundaryDemo.java`:

~~~java
import java.util.Set;

public class BoundaryDemo {
    static String approve(String user, Set<String> authorities,
                          String owner, String reason, boolean draft) {
        if (!authorities.contains("invoice:approve")
                || !user.equals(owner)) {
            return "DENIED";
        }
        if (reason == null || reason.isBlank() || reason.length() > 120) {
            return "INVALID";
        }
        if (!draft) {
            return "CONFLICT";
        }
        return "APPROVED";
    }

    public static void main(String[] args) {
        Set<String> permissions = Set.of("invoice:approve");
        System.out.println(approve("alice", permissions,
                "alice", "Reviewed", true));
        System.out.println(approve("bob", permissions,
                "alice", "Reviewed", true));
        System.out.println(approve("alice", permissions,
                "alice", " ", true));
        System.out.println(approve("alice", permissions,
                "alice", "Reviewed", false));
    }
}
~~~

Run with Java 17+:

~~~bash
javac --release 17 BoundaryDemo.java
java BoundaryDemo
~~~

**Exact** stdout:

~~~text
APPROVED
DENIED
INVALID
CONFLICT
~~~

Varying `user`, `reason`, and `draft` shows one operation can fail for three independent reasons. Checking `DENIED` first in the example is an **order-of-evaluation policy choice**, not evidence that every web framework checks in this order.

## 11. Common design mistakes

### 11.1. Confusing "invalid" with "unauthorized"

Throwing `AccessDeniedException` for a blank `reason` tells the client it lacks permission when fixing the payload is the real cure. This causes confusing UX and noisy security audit logs. Use a validation exception, and raise access denied only when actor/permission conditions truly fail.

### 11.2. Stuffing business state into roles

The rule "an invoice may only be approved while DRAFT" is not a `ROLE_DRAFT` authority; invoice state changes independently of caller identity. Express it as a domain transition or clearly named policy; if only a special admin may override, model that as a **separate action with distinct permission** and invariants.

### 11.3. Checking `@Valid` only at the controller

Jobs, message listeners, or other services may invoke the business service directly. Domain invariants and value-object validation must still be enforced at the reusable layer; never rely on an HTTP controller always being present.

### 11.4. Checking ownership only in controllers or UI

Another endpoint invoking the same service may accidentally omit the check. Protect with method/security policies in the service or domain authorization close to the resource; filter queries by tenant and test non-HTTP paths too.

### 11.5. Reading state then writing without concurrency control

Two requests both observe `DRAFT`, transition to `APPROVED`, and emit events twice. Use transactions with locks/versions/conditional updates, and manage API idempotency. A Java `if` statement does not provide DB atomicity.

### 11.6. Using `@PostAuthorize` for updates

Permission is evaluated after the method body, so side effects may already have occurred. Prefer pre-checks plus data-bound checks at write time. Never expect an exception to roll back already-sent emails, external API calls, or published events.

### 11.7. Returning full error details to unauthorized users

For example, "Bob's Invoice 42 is already APPROVED" leaks both owner and status to a user who should not see them. Decide between 403 and 404, separate internal logs from client responses, and put sensitive details only in proper audit channels. Never expose stack traces, principal tokens, or SQL through exception handlers.

### 11.8. Turning every business conflict into 403

If a user has permission and a valid payload yet the invoice is locked, returning 403 misleads the client into requesting extra permissions. A 409 or consistent domain error code communicates the needed client action far more clearly. For async/batch work, define per-item or all-or-nothing statuses by contract instead of forcing HTTP semantics blindly.

### 11.9. Treating single-layer testing as sufficient

Service tests using `@WithMockUser` do not prove the filter chain, CSRF, and DTO validation; controller tests mocking the service do not exercise the Spring security proxy. Write focused tests per layer plus end-to-end integration tests to catch ordering bugs or missing interceptors.

## 12. How to choose the boundary for a new rule

When adding a requirement, ask in order:

1. **Does it depend on identity, permission groups, tenant, or the subject's rights on an object?** If yes, write a clearly named authorization policy; failures must carry deny semantics.
2. **Can validity be determined solely from input data and field contracts?** If yes, use validation, favoring immutable types/value objects for core constraints.
3. **Does it depend on system state, transactions, inventory, quotas, or state transitions?** If yes, place it in domain/service invariants; guard at actual write time.
4. **Does the rule span multiple categories?** Split into named predicates, preserve distinct error semantics, and combine only at the execution point.
5. **What data could leak before permission checks?** Display/validate only what the user is permitted to know; use consistent status codes and error messages for hidden resources.
6. **Is there concurrency or retry?** Use transactions, versions/locks/unique constraints/idempotency keys; test races and rollbacks.

### Scenario exercise

User `alice` holds authority `invoice:approve` and submits reason "OK" for invoice 5. Invoice 5 belongs to another tenant and has status `APPROVED`. Which check must stop the request before saying "already APPROVED"?

**Answer:** check invoice/tenant permissions before revealing status. You can return a consistent 404 for invisible resources. Even with a valid reason and feature-level authority, Alice still lacks permission on invoice 5; do not disclose the `APPROVED` status detail.

If invoice 5 belonged to Alice's authorized tenant/scope, then the `APPROVED` invariant blocks re-approval; the API may return 409. If the reason were blank, Bean Validation could return 400 before the service reads state, depending on the configured pipeline. Only when all three pass is the update allowed, with atomicity guaranteed by the DB.

## Official Documentation

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request-level authorization and `AuthorizationManager`.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interception, denial exceptions.
- [Spring Framework – `@RequestBody` + Bean Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): `@Valid`, `MethodArgumentNotValidException`, and default 400 responses.
- [Spring Security – CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` on MockMvc for unsafe HTTP methods.
- [Spring Framework – Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy boundaries, rollback, and transaction semantics.
