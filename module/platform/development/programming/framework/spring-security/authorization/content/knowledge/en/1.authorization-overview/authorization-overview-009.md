# Learning Path from Permission Model to Configuration, Testing, and Operations

## 1. Orientation: In What Order Should Authorization Be Learned?

Learning **authorization** in Spring Security is often inverted: starting with `hasRole("ADMIN")` or adding `@PreAuthorize`, and only afterward asking what the system actually wants to protect. This easily produces checks that are syntactically valid yet semantically wrong, such as "having edit permission" allowing someone to edit any customer's document.

A solid path starts from the **permission model**, turns the model into **executable decisions**, attaches them to **access points**, proves them through **testing**, and maintains correctness as the system **operates and evolves**.

```text
Business needs and assets to protect
               |
               v
[1] Permission model + allow/deny matrix
               |
               v
[2] Clear, independent authorization decision policy
               |
               v
[3] Configuration and enforcement points in Spring Security
               |
               v
[4] Authorization testing by function, object, and state
               |
               v
[5] Operations: grant/revoke permissions, observe, update policy
               |
               +-------- feedback on errors or policy changes --------+
                                                                      |
                                                                      v
                                             Return to permission model
```

This path is a **loop**, not a "configure once and forget" sequence. For example, when adding a "locked" state to a document, review the policy first, then adjust code, tests, and operational procedures.

### Learner outcomes

After this lesson, you should be able to:

- Translate business requirements into a clear permission matrix of **who – does what – on which object – under what conditions**.
- Distinguish authentication, functional permissions, object-level permissions, and access decisions.
- Configure HTTP gates and service/data gates in Spring Security.
- Prove via tests that a valid request is allowed and every invalid request is actually blocked.
- Describe how to handle permission changes, audit access decisions, dependency failures, and policy rollouts.

Short sequence: **Understand policy → Express policy → Enforce → Verify → Maintain**.

## 2. Foundations to Master Before Configuring

### 2.1. Authentication differs from authorization

- **Authentication:** which identity is sending the request? A valid `Authentication` may carry a principal and `GrantedAuthority` values.
- **Authorization:** is that principal allowed to perform the requested action on the specific resource under the current context?
- **Enforcement:** which component actually blocks the operation before the resource is read, modified, approved, or deleted?

In Spring Security, `SecurityFilterChain` can check HTTP rules, while method security can protect method invocations. Yet **both require the right policy** and checks against the actual object. A valid login session does not mean a user can operate on every object whose ID they can guess.

### 2.2. Concepts that must fit together cleanly

| Concept | Meaning | Example |
| --- | --- | --- |
| Subject (principal) | User or service with a trusted identity | User 10 |
| Action | Operation performed on a resource | `request:approve` |
| Resource | Object being accessed | Request 102 |
| Context | Conditions affecting the decision | Tenant 1, `PENDING` status |
| Role | Responsibility grouping of a subject | EDITOR, APPROVER |
| Functional permission (permission/authority) | Specific granted capability | `request:update` |
| Policy | Final conditions required to allow | Has permission, same tenant, not the creator |
| Enforcement point | Where the system obligates applying the decision | Filter, service, data query |

**RBAC** (role-based access control) is convenient for grouping common permissions. **ABAC** (attribute-based access control) expresses conditions by tenant, status, or department. Object permissions can also rely on ownership/sharing relationships. A real system usually combines these models; a role name alone cannot replace resource-level conditions.

Before learning Spring Security APIs, make sure you can answer: "Can someone with `ROLE_EDITOR` edit another team's record?". Without knowing **resource scope** and **business state**, the accurate answer is: **insufficient facts to allow**.

## 3. Step 1 — Modeling Permissions from a Real Problem

Use one running scenario: a **purchase request** management system. Each request has an ID, tenant, creator, and state `DRAFT`, `PENDING`, or `APPROVED`. The creator can edit drafts; someone with approval duties can approve pending requests, yet cannot self-approve their own request.

### 3.1. List resources, subjects, and actions

Resource: `PurchaseRequest`. Subjects: requester, approver, read-only viewer. Actions may include `read`, `update`, `submit`, `approve`. Each action needs its own permission and a concrete scope rule.

Initial matrix:

| Action | Functional Permission | Object Conditions | Valid Status |
| --- | --- | --- | --- |
| View | `request:read` | Same tenant and assigned view scope | Per business viewing rules |
| Edit | `request:update` | Same tenant, creator themselves | `DRAFT` |
| Submit | `request:submit` | Same tenant, creator themselves | `DRAFT` |
| Approve | `request:approve` | Same tenant, not the creator | `PENDING` |

This matrix reflects **the example's business assumptions**. If the system restricts viewers to their own department's records, add that condition to the "View" row; if approval delegation exists, describe the delegation relationship and expiration. Never apply this matrix to any system without confirming business rules.

### 3.2. Write policies as complete statements

Instead of writing "EDITOR can update", express it as:

> Allow editing a request when the subject is authenticated, active, has `request:update`, is in the same tenant as the request, is the request's creator, and the request is in `DRAFT` status.

For approval:

> Allow approving when the subject is authenticated, active, has `request:approve`, is in the same tenant, **is not the creator**, and the request is `PENDING`.

All other cases are denied. In particular: **missing information never self-allows**; **functional permission is only a necessary condition**; **someone who is both the creator and holds approve permission still cannot self-approve if policy forbids it**.

### 3.3. Specify trusted data sources

| Fact | Trusted Source | Source Never Trusted Directly |
| --- | --- | --- |
| User identity | Server-authenticated principal | Self-sent `userId` in JSON |
| Active permissions | Verified authorities or trusted policy service | Self-declared roles from client |
| Active tenant | Tenant with verified membership for the principal | Unverified `X-Tenant-Id` header |
| Owner and status | Record from trusted data store | `ownerId`/`status` fields sent by client to legitimize request |
| Sharing/delegation relationships | Controlled business data | List of IDs entered by the user |

The output of step 1 must be a **policy table approved by the business owner**, accompanied by allow/deny examples and exception handling. Move to the next step only when you can explain why every denied case is rejected. This is where **least privilege**, **deny by default**, and **no self-approval** are applied before writing framework code.

## 4. Step 2 — Turning the Model into an Easily Testable Decision Function

This step separates two questions: "Is the policy right?" and "Does Spring Security call the policy in the right place?". Start from plain Java logic, with explicit inputs and independently testable allow/deny outputs.

### 4.1. Standalone Java 17+ example

Save the entire program as `AuthorizationLearningPathDemo.java`. The example distills three actions—READ, EDIT, APPROVE. The SUBMIT action from the matrix is left as an extension exercise rather than smuggling assumptions into code unintentionally.

```java
import java.util.Set;

public class AuthorizationLearningPathDemo {
    enum Action { READ, EDIT, APPROVE }
    enum Status { DRAFT, PENDING, APPROVED }

    record Actor(
        long userId,
        long tenantId,
        Set<String> permissions,
        boolean active
    ) {}

    record PurchaseRequest(
        long id,
        long tenantId,
        long authorId,
        Status status
    ) {}

    static boolean allowed(
        Actor actor,
        Action action,
        PurchaseRequest request
    ) {
        // Missing identity/object, disabled, or different tenant:
        // deny by default.
        if (actor == null || action == null || request == null
                || !actor.active()
                || actor.tenantId() != request.tenantId()) {
            return false;
        }

        return switch (action) {
            case READ ->
                actor.permissions().contains("request:read");
            case EDIT ->
                actor.permissions().contains("request:update")
                    && actor.userId() == request.authorId()
                    && request.status() == Status.DRAFT;
            case APPROVE ->
                actor.permissions().contains("request:approve")
                    && actor.userId() != request.authorId()
                    && request.status() == Status.PENDING;
        };
    }

    static void show(String scenario, boolean result) {
        System.out.println(scenario + ": " + result);
    }

    public static void main(String[] args) {
        Actor author = new Actor(
            10, 1, Set.of("request:read", "request:update"), true
        );
        Actor approver = new Actor(
            20, 1, Set.of("request:read", "request:approve"), true
        );
        Actor outsider = new Actor(
            30, 2, Set.of("request:read", "request:approve"), true
        );
        Actor authorWithApprove = new Actor(
            10, 1, Set.of("request:approve"), true
        );

        PurchaseRequest draft =
            new PurchaseRequest(101, 1, 10, Status.DRAFT);
        PurchaseRequest pending =
            new PurchaseRequest(102, 1, 10, Status.PENDING);

        show("author edits own draft",
            allowed(author, Action.EDIT, draft));
        show("author cannot self-approve",
            allowed(authorWithApprove, Action.APPROVE, pending));
        show("approver approves pending",
            allowed(approver, Action.APPROVE, pending));
        show("approver cannot approve draft",
            allowed(approver, Action.APPROVE, draft));
        show("other tenant cannot read",
            allowed(outsider, Action.READ, pending));
        show("missing principal is denied",
            allowed(null, Action.READ, pending));
        show("approver cannot edit draft",
            allowed(approver, Action.EDIT, draft));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AuthorizationLearningPathDemo.java
java AuthorizationLearningPathDemo
```

Expected output:

```text
author edits own draft: true
author cannot self-approve: false
approver approves pending: true
approver cannot approve draft: false
other tenant cannot read: false
missing principal is denied: false
approver cannot edit draft: false
```

Interpretation: the first case is allowed because permission, owner, tenant, and status all match. The creator cannot self-approve even if granted `request:approve`. A valid approver can only approve pending requests; they do not have permission to edit drafts. Callers from other tenants and requests missing a principal are both denied.

This is a **learning model**, not a full production policy. In a real application, `Actor` must be constructed from a verified identity; permissions and status can change; and approval must maintain consistency with the data store and concurrent updates.

### 4.2. Step 2 completion criteria

Ask these questions for every rule: which inputs determine the result? Is there any path that allows when data is missing? Are other tenants blocked before returning data? Does the outcome depend on client-declared data? Can two users with the same role but different object relationships receive different results?

A policy meets requirements when:

- Every allow branch is expressed explicitly, and all other branches deny.
- The decision function is simple enough to read and test independently.
- Logic like "admin can do anything" or varying tenant conditions is not scattered across controllers.
- **Policy decision** is cleanly separated from **enforcement action** and **returned HTTP status code**.

## 5. Step 3 — Binding Policy into Spring Security at the Right Boundaries

Learn configuration from the outside in: **HTTP → business methods → data/objects**. Each layer guards against a different class of mistakes.

### 5.1. HTTP gate (Servlet)

Below is an **illustrative configuration in a Spring Boot Servlet application using Spring Security 6**, requiring the app to have its own authentication mechanism. Strings like `request:read`, `request:update`... must actually appear in the principal's `GrantedAuthority` after authentication.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/health/public")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/requests/*")
                .hasAuthority("request:read")
            .requestMatchers(HttpMethod.PATCH, "/api/requests/*")
                .hasAuthority("request:update")
            .requestMatchers(HttpMethod.POST, "/api/requests/*/submit")
                .hasAuthority("request:submit")
            .requestMatchers(HttpMethod.POST, "/api/requests/*/approve")
                .hasAuthority("request:approve")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Meaning of the rules:

- Only confirmed public status endpoints use `permitAll()`; unlisted routes are denied by `denyAll()`.
- Match both path and HTTP method, so "read" permission does not accidentally become "edit" permission.
- `hasAuthority("request:approve")` checks only **functional permission**. It does not yet know which tenant the request belongs to, who created it, or whether it is `PENDING`.
- Matcher ordering and any other `SecurityFilterChain` beans must be inspected together. An overly broad rule placed before a narrow rule can break the policy.
- This sample does not intentionally configure CSRF, CORS, sessions, or JWT. Design those according to your actual client/authentication style; never mechanically disable CSRF when the app uses cookies or sessions.

If using OAuth2 Resource Server, inspect the exact scope/claim-to-`GrantedAuthority` mapping. In standard configurations, scopes may become `SCOPE_`-prefixed authorities; use `hasAuthority("request:read")` only when the system actually grants an authority with that exact string.

In WebFlux applications, the corresponding mechanism lies in `SecurityWebFilterChain` and `authorizeExchange`. Authorization concepts remain the same, yet do not copy Servlet syntax verbatim to reactive apps.

### 5.2. Business method gate

Suppose the API is already gated by `request:approve`; the service layer still must evaluate tenant, creator, and state. You can place `@PreAuthorize("hasAuthority('request:approve')")` on the public entry point and invoke a policy component.

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApprovalService {
    private final PurchaseRequestRepository requests;
    private final CurrentActor currentActor;
    private final ApprovalPolicy policy;

    public ApprovalService(
            PurchaseRequestRepository requests,
            CurrentActor currentActor,
            ApprovalPolicy policy) {
        this.requests = requests;
        this.currentActor = currentActor;
        this.policy = policy;
    }

    @Transactional
    @PreAuthorize("hasAuthority('request:approve')")
    public void approve(long requestId) {
        var actor = currentActor.requireAuthenticated();
        var request = requests.findById(requestId)
            .orElseThrow(() -> new RequestNotFoundException(requestId));

        if (!policy.mayApprove(actor, request)) {
            throw new AccessDeniedException("Not allowed");
        }

        request.markApproved(actor.userId());
    }
}
```

This is **illustrative integration code**, requiring application-defined domain types `PurchaseRequestRepository`, `CurrentActor`, `ApprovalPolicy`, `RequestNotFoundException`, and the `PurchaseRequest` model. `CurrentActor` must use the system-authenticated principal; `ApprovalPolicy` implements the matrix from step 1. `markApproved` executes only after permissions are confirmed.

Important notes:

1. `@EnableMethodSecurity` enables method security support in the standard way; annotations like `@PreAuthorize` are typically enforced through a Spring AOP proxy. **Self-invocation** (one method calling another on the same instance) can bypass proxy checks.
2. `@Transactional` by itself **does not guarantee** avoiding races between state checks and writes. Depending on the data model, you need optimistic locking (e.g., a version column), explicit locking, or conditional updates `WHERE status = 'PENDING' ...` while checking affected row counts.
3. For search, pagination, and data export, filter **directly in the query** by tenant and user scope. Filtering after fetching all data or only hiding in the UI can leak content.
4. Methods may be called from other controllers, jobs, or internal components. You must know which path guarantees policy enforcement rather than relying solely on HTTP routes.

### 5.3. Role of each layer

| Layer | What Does It Solve? | What It Does Not Solve Alone |
| --- | --- | --- |
| `SecurityFilterChain` | Blocks inappropriate requests by URL/method/authority | Owner, tenant, or record state |
| Method security | Protects business operations shared across multiple callers | Concurrent updates and bulk data filtering |
| Object policy | Permissions on specific records and states | Forgotten paths if not invoked |
| Repository/transaction | Reads/writes only data within valid scope; maintains consistency | Unverified identity and permissions |

Output of step 3: for every action in the matrix, point out clearly **where functional permission is checked**, **where object-level permission is checked**, and **where data consistency is maintained**. If you cannot trace that path, configuration is incomplete.

## 6. Step 4 — Testing to Prove Correctness

Authorization testing differs from happy-path business testing: besides confirming valid operations work, you must actively test cases that **ought to be blocked**. A test returning 403 due to missing CSRF does not prove the policy blocked properly.

### 6.1. Turning the permission matrix into a test matrix

| Case | Principal/Authority | Object | Expectation |
| --- | --- | --- | --- |
| Author edits draft | Has `request:update` | Same tenant, same author, DRAFT | Allow |
| Stranger edits draft | Has `request:update` | Same tenant, different author | Deny |
| Approver approves request | Has `request:approve` | Same tenant, different author, PENDING | Allow |
| Author self-approves | Has `request:approve` | Same tenant, same author, PENDING | Deny |
| Approving draft | Has `request:approve` | DRAFT | Deny |
| Reading other tenant's record | Has `request:read` | Different tenant | Deny |
| Missing functional permission | Logged in, missing authority | Valid data | Deny |
| Unauthenticated | No valid principal | Any protected resource | Do not execute operation |
| Undeclared method or URL | Valid account | Path undefined in policy | Deny per default policy |
| Recently revoked permission | Principal no longer holds effective permission | Previously viewable data | Stop granting per system's revocation mechanism |

Test across different paths: detail read endpoints, lists, search, exports, uploads, async jobs, and internal service call points if they can touch the same resource.

### 6.2. Four testing layers to learn in order

**Layer 1 — Plain Java policy.** Test each rule with deterministic mock data, including nulls, other tenants, missing permissions, and other statuses. The standalone program in section 4 is the basic observation step; in a project, convert them into JUnit assertions.

**Layer 2 — HTTP security.** With Spring MVC/MockMvc and `spring-security-test`, verify matchers, unauthenticated status, missing authorities, and undeclared paths. For POST/PATCH/DELETE when CSRF is enabled, supply a valid CSRF token to test the actual **authorization decision**; otherwise a 403 may simply come from CSRF. An illustrative snippet placed **inside a test class configured with MockMvc, principal, and data**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Illustrates only the invocation inside a @Test with a mockMvc field.
mockMvc.perform(post("/api/requests/102/approve")
        .with(user("approver")
            .authorities(new SimpleGrantedAuthority("request:approve")))
        .with(csrf()))
    .andExpect(status().is2xxSuccessful());
```

In this example, `SimpleGrantedAuthority` is `org.springframework.security.core.authority.SimpleGrantedAuthority`; the 2xx outcome holds only when the real fixture has request 102 in `PENDING`, the user belongs to the right tenant and is not the author, and the controller/service implements the operation successfully. This is **not a standalone runnable program** and cannot replace tests with real data.

**Layer 3 — Service and data.** Invoke the service layer from valid paths to prove object checks still apply; verify queries never leak records from other tenants; verify transactions do not mutate state when denied. Test concurrent updates: two users approving the same request, permissions/tenant changing between operations, or the object changing state right before the write command.

**Layer 4 — End-to-end business flow.** Run the journey create → edit → submit → approve → view result with the appropriate identities. After each action, check both **HTTP result**, **actual persisted data**, and **audit events** if applicable.

### 6.3. Reading test results accurately

- **401** usually indicates an unauthenticated request to an API; some interactive apps may redirect to login.
- **403** usually indicates an identified request denied permission; CSRF can also produce 403.
- **404** is sometimes used intentionally for out-of-scope resources to avoid disclosing existence.
- **5xx** may reflect a policy service failure, yet sensitive operations **must never be allowed when permissions cannot be verified**.

Do not hard-bind one HTTP status code to every scenario. The crucial test assertion is **no sensitive data returned and no unauthorized business side effect**. When a test fails, pinpoint the failing layer (matcher, authority mapping, object policy, data store, CSRF) before fixing.

Output of step 4: a test matrix covering both allowed and denied cases, stable tests, proof of post-request data state, and the ability to catch new bypass paths.

## 7. Step 5 — Operating Policies and Permissions Over Time

A policy that is right today can become wrong after staffing changes, tenant restructuring, new resource statuses, or approval flow updates. Authorization requires operational processes like any other security control.

### 7.1. Granting, changing, and revoking permissions

**Granting:** identify who approves grant requests, the required tasks, the minimal permission list, tenant/resource scope, and duration. Service accounts receive only permissions for their job, never admin privileges by default.

**Role or responsibility changes:** revoke old permissions before or alongside granting new ones; never accumulate roles simply from job history. Conduct periodic access reviews and clean up expired special permissions.

**Revoking permissions:** understand propagation mechanics. If permissions are embedded in a long-lived self-contained JWT, updating the server's permission table **does not automatically** alter already-issued tokens. Consider short-lived tokens, dynamic permission lookups, revocation lists, versioned sessions, or validity mechanisms matching the risk level. Whatever you choose, measure actual revocation latency in tests.

**Emergency access:** if temporary privilege elevation exists, require an authorized approver, reason, short duration, and separate audit logs; never let emergency accounts become a permanent shortcut.

### 7.2. Observing allow and deny decisions

Audit logs should record enough information for investigation without exposing secrets:

| Field | Purpose |
| --- | --- |
| Timestamp, request/correlation ID | Correlate events belonging to the same request |
| Principal or service identifier | Who requested |
| Action and suitable resource identifier | What they attempted to do |
| Verified tenant/scope | Under which context they requested |
| Outcome and controlled reason code | Allowed, denied, dependency error |
| Policy version | Which rules were active |

Never log raw tokens, cookies, passwords, or full contents of sensitive resources just for "easy debugging". Protect logs and limit retention according to system requirements.

Monitor **spikes in denials**, **anomalies on endpoints after deployment**, **policy evaluation latency**, and **error rates from dependent services**. Many 403 responses may just be normal forbidden attempts being blocked; alerts need context to reduce false positives.

### 7.3. Reliability, performance, and consistency

- **Policy service failure:** for sensitive actions, if evaluation fails, do not let them pass. Return an appropriate technical error rather than pretending it is always a missing-permission error.
- **Permission caching:** consider tenant, principal, action, resource, policy version, status, and expiration. Caching solely by user ID easily returns wrong decisions for another resource/tenant. Provide invalidation or short TTLs when permissions are revoked.
- **Concurrency:** check-then-write can use stale data; apply appropriate transactions, locks, versioning, or conditional updates for sensitive actions.
- **Non-HTTP channels:** jobs, message consumers, internal RPCs, and batch/export tasks do not automatically inherit HTTP filters. They also need identity and policies at their entry points.
- **Performance:** avoid calling a permission service N unnecessary times across large lists; optimize scoped queries, yet never use performance as an excuse to skip object checks.

### 7.4. Shipping a new policy to production

A permission change should follow this pipeline:

```text
Business requirement change
  -> update policy matrix, confirmed by domain owner
  -> update policy + matchers + service + data
  -> add tests for new permissions and existing denial paths
  -> run integration tests and impact review
  -> deploy with monitoring for errors, 401/403, audit logs
  -> verify valid cases still work and forbidden cases remain blocked
```

Prepare a rollback plan in case a new policy blocks legitimate users or unintentionally widens access. When an unprotected entry point is discovered, fix it across **the policy model**, **enforcement paths**, and **regression tests**, not just by patching a quick `if` into a controller.

Output of step 5: an **operational process with clear ownership**: how permission changes are approved, how revocation works, what data supports tracing, which metrics detect failures, and how deployments are verified.

## 8. Shortcuts That Commonly Lead to Bugs

| Shortcut Skipping Steps | Consequence | What Needs to Be Learned Instead |
| --- | --- | --- |
| Writing `hasRole("ADMIN")` before a matrix | One role covers many unrelated tasks | Resource, action, and least-privilege modeling |
| Enabling `authenticated()` for every endpoint | Logged-in users can invoke tasks outside their duties | Functional permissions, deny by default |
| Checking only the URL, not the record | Swapping IDs reads/edits others' resources (IDOR/BOLA) | Object-level permissions, tenant, owner, status |
| Writing annotations without understanding proxies | Self-invocation can bypass method security | AOP boundaries and the real invoked service |
| Testing only one admin succeeding | Misses missing-permission, cross-tenant, self-approval cases | Test matrix with both allow and deny cases |
| Testing POST returning 403 while forgetting CSRF | Mistakes a CSRF failure for a working policy | Distinguishing HTTP filters from authorization checks |
| Approving based on previously read state | Concurrent requests can corrupt state | Transactions, versioning, conditional updates |
| Revoking a role yet trusting old JWTs expire immediately | Permissions stay active until token/session is handled | Revocation mechanics and validity lifetimes |
| Caching allow decisions by user while omitting resource/tenant | Decision for object A gets applied to object B | Context-accurate cache keys and invalidation |
| Logs missing identity/rule or logging raw tokens | Hard to investigate or leaks sensitive data | Safe audit logging |

Memorizing APIs will not fix the mistakes above. The goal is understanding **where permissions originate**, **where permissions are evaluated**, **where actions are blocked**, and **how to prove the system blocked accurately**.

## 9. Hands-On Path from Easy to Hard

### Exercise 1 — Matrix (without Spring)

Build a table for a feature with two tenants, three permissions, and three statuses. Write at least eight scenarios, including users with the same role in different tenants, users with permission but wrong status, and users forbidden from self-approving. **Done** when no scenario requires guessing the outcome.

### Exercise 2 — Plain Java decision evaluator

Extend `AuthorizationLearningPathDemo`: add `Action.SUBMIT` and the rule "author has `request:submit`, same tenant, active, status DRAFT". Add valid and blocked cases. **Done** when code compiles, output matches the matrix, and no branch self-allows when data is missing.

### Exercise 3 — Spring Security HTTP

Map each action to an HTTP method, endpoint, and authority. End with `anyRequest().denyAll()`. Verify which routes are public, which require identity, and which require specific permissions. **Done** when changing an HTTP method or hitting an undeclared URL does not accidentally open access.

### Exercise 4 — Resource-level gate

Put tenant/author/status logic into a policy component used by the service. Ensure detail reads, list reads, and write operations cannot bypass it. **Done** when two users with the same permission yet different resource rights receive different outcomes matching the matrix.

### Exercise 5 — Testing and negative cases

Write policy unit tests, HTTP tests with valid identity/CSRF, service tests, and database assertions after denied operations. Add tenant-switching, ID-guessing, revoked-permission, and concurrent-approval tests. **Done** when tests catch at least one version of code with a tenant or state check intentionally removed.

### Exercise 6 — Operations

Describe how to grant and revoke `request:approve`, what audit details to log, the fallback policy when the permission service fails, and how to monitor a rule-change rollout. **Done** when you can explain who is accountable, when permissions take effect, when revocation completes, and where to look up evidence.

## 10. Completion Map: What Does Each Stage Leave Behind?

| Stage | Artifact Needed | Verification Question Before Moving to Next Stage |
| --- | --- | --- |
| 1. Model | Permission matrix and allow/deny scenarios | Are actor, action, resource, and context all fully described? |
| 2. Policy | Decision function and standalone tests | Is any allow branch missing a required condition? |
| 3. Configuration | HTTP, method, data check points, and path map | Can any entry path to the feature evade checks? |
| 4. Testing | Test matrix, fixtures, and result evidence | Do denied cases guarantee zero side effects? |
| 5. Operations | Grant/revoke process, audit, monitoring, change handling | When permissions change or dependencies fail, how does the system stay safe? |

### End-of-lesson self-check

1. Why not start solely with `hasRole("ADMIN")`? Because it does not yet describe actions, objects, scope, or business states; a role does not replace a permission matrix.
2. Is having `request:approve` enough to approve every record? No; tenant, creator, status, and business conditions must still be evaluated.
3. Why are check layers outside HTTP needed? Because services may be called via other paths and permissions depend on specific objects, not just URLs.
4. Why is a POST returning 403 insufficient to prove an authorization test works? Because CSRF or another mechanism can also cause 403; you must verify the denial point and data state.
5. Does revoking a role in the database immediately invalidate already-issued JWTs? Not necessarily; appropriate validity and revocation mechanisms are required.
6. When adding a new business state, which part must be updated first? Start from the model and policy, then update enforcement, tests, and operations.

**Remember:** a feature has complete authorization when permissions are **accurately defined**, **enforced across every real access path**, **proven by tests for both allow and deny**, and **supported by processes that preserve correctness as data, users, or policies change**.