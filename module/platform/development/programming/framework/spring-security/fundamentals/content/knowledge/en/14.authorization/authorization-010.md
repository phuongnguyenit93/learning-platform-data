# Changing Authorization Policies and Verifying Cross-Layer Consistency

## 1. Why Must Policy Changes Be Verified Across Layers?

In an application using Spring Security, an “allow or deny” decision may pass through many places: gateway or HTTP security filters, controllers, method security, business services, repositories, list APIs, background jobs, and even caches. Whenever an authorization rule changes, the system must ensure **every relevant execution path still follows the same business policy**. If you edit only one annotation or one URL matcher, another path may keep enforcing the old rule.

For example: the **approve invoice** feature previously allowed anyone with the `invoice:approve` authority to approve. The new policy requires all of the following:

- Holds the `invoice:approve` permission granted from a trusted source.
- The approver and the invoice belong to the same tenant.
- The approver is **not the creator** of the invoice (*separation of duties*).
- The invoice is in `PENDING` status.
- The invoice amount does not exceed the user's approval limit.

If the HTTP filter checks only the authority, that can still be **correct at the coarse filter layer**; yet the service must enforce the full new rule. If the HTTP endpoint is updated while a message consumer, batch job, or internal API still approves under the old rule, the system is inconsistent and has a business vulnerability.

**The goal of consistency verification** is: for the same subject, action, resource, and trusted context, **every execution path capable of producing a business outcome must reach the same allow/deny decision**. Every layer does not have to contain identical conditions: filters can reject early by authority, while services and data layers are responsible for fine-grained conditions.

## 2. Defining Exactly What “Policy Change” Means

Before touching code, define the policy as a verifiable contract:

~~~text
decision = authorize(subject, action, resource, context, policyVersion)

subject:     authenticated principal, authorities, tenant, trusted attributes
action:      business action, e.g. invoice:approve
resource:    specific invoice with id, tenant, creator, amount, status
context:     limit, subject-resource relationship, timestamp, workflow
policyVersion: active rule version
decision:    ALLOW or DENY, with internal reason code if needed
~~~

Use **one decision table** for the change from `v1` to `v2`:

| Scenario | v1: only `invoice:approve` | v2: new policy |
| --- | --- | --- |
| Has authority; same tenant; created by someone else; `PENDING`; within limit | Allow | Allow |
| Has authority, but invoice belongs to another tenant | Might be allowed under v1 (bug if tenant check missing) | Deny |
| Has authority, but self-approval | Allow | Deny |
| Has authority, but over limit | Allow | Deny |
| Has authority, but invoice is already `PAID` | Allowed if v1 did not check status | Deny |
| Lacks authority | Deny | Deny |

This table is the **expected specification** for the entire change. If the old policy already had tenant/status guards, record those exact conditions in the real change doc; `v1` here is intentionally simplified to show how to spot deltas.

During review, clearly answer:

1. **Affected targets**: which endpoints, methods, events, exports, list/search APIs, admin tools, or background tasks can perform the action?
2. **Decision data**: where do authority and tenant come from; which record provides creator, status, amount; is the limit verified on the server?
3. **What the new rule changes**: adding conditions, revoking permissions, expanding exceptions, changing privileges, or changing tenant scope?
4. **Failure modes**: how are missing authentication, missing records, missing metadata, stale caches, and policy-service errors handled?
5. **Activation and transition**: does the new policy take effect immediately, by config version, or by business effective time? How is the old version retired?

For missing or untrusted data, apply the **fail closed** principle: never infer permission from a `null` value, client-sent parameters, or policy-evaluation exceptions.

## 3. Map of Layers to Cross-Check

| Layer/entry point | What can it enforce? | Check when changing policy |
| --- | --- | --- |
| **Gateway / proxy** | Routing, partial auth, access limits | Can internal/direct paths to the service bypass the gateway? Gateway does not replace service resource checks |
| **HTTP `SecurityFilterChain`** | Early blocking by route, method, authority via `authorizeHttpRequests` | Matchers, ordering, HTTP methods, route aliases, `denyAll` on undeclared routes |
| **Controller** | Receives IDs, calls use cases, returns responses | Do not trust client-supplied `tenantId`/`role`/`userId`; no side endpoints bypassing the service |
| **Method security** | `@PreAuthorize`/`@PostAuthorize` on calls through Spring proxies | `@EnableMethodSecurity`, right methods and authorities, no reliance on self-invocation |
| **Application/service** | Business decisions and side effects | v2 rules must be checked before approving/deleting/transferring/publishing events |
| **Repository / DB** | Finding, filtering, updating records, pagination | List/get/update queries constrained by tenant and permission scope; transactions prevent TOCTOU |
| **Queue / scheduler / consumer** | Executes use cases without passing HTTP filters | Define service principal and call the same domain policy; do not assume unlimited privileges |
| **Cache / token / session** | Holds permissions, decisions, or data | When revoking/changing permissions, can TTL, invalidation, or policy version keep old grants alive? |
| **Frontend / BFF** | Shows/hides actions, sends requests | UI reflects new rules for good UX; backend remains the enforcement point |
| **Audit / monitoring** | Logs changes and decisions | Includes policy version, action, reason code, correlation ID; never logs secrets/tokens |

**Do not duplicate the same long set of conditions at every layer and edit each copy manually.** A sustainable architecture typically lets filters check coarse preconditions while a **domain policy service** serves as the authoritative decision maker for resources. Repositories add data constraints and atomicity. All execution paths producing side effects must pass equivalent enforcement.

## 4. Establishing One Reusable Policy Source

Suppose the new rule is:

~~~text
canApprove(actor, invoice) =
    actor authenticated
    AND actor.hasAuthority("invoice:approve")
    AND actor.tenant == invoice.tenant
    AND actor.id != invoice.creator
    AND invoice.status == PENDING
    AND invoice.amount <= actor.approvalLimit
~~~

Clearly separate **where the policy lives** from **where it is enforced**:

- **Policy definition**: decision criteria for the `approveInvoice` use case, with name, inputs, outcomes, version, and test matrix.
- **Policy decision point**: service or policy bean computing `ALLOW/DENY` from trusted data. This can be a Spring component, policy engine, or shared library depending on architecture.
- **Policy enforcement point**: filters, services, repository operations, and message handlers blocking the operation when the decision is `DENY`. These points **must call the policy** or apply guards proven equivalent.
- **Policy information point**: loads actor, roles/authorities, resource relationships, tenant, and state; never takes sensitive attributes from client-declared data.

An API checking only `hasAuthority("invoice:approve")` at HTTP is not necessarily wrong: that is a **necessary condition**. What is wrong is when the layer underneath fails to check tenant, separation of duties, state, and limit. Conversely, if the service already blocks properly, a frontend showing the wrong Approve button is just a UX bug—though still worth fixing for clarity.

### Recommended Responsibility Contract

~~~text
POST /api/invoices/{id}/approve
    |
    v
HTTP SecurityFilterChain
    |-- missing invoice:approve --------> DENY
    |
    v
InvoiceApplicationService.approve(id)
    |-- load trusted actor & invoice ---> policy.canApprove(...)
    |-- DENY ---------------------------> no DB change / no event published
    |
    v
Transaction + atomic update/row lock
    |-- 0 rows updated / state changed -> reject or conflict per contract
    |
    v
Commit -> publish event via post-commit guarantee
~~~

The message consumer flow uses the same `InvoiceApplicationService`, with a clearly defined service identity or delegated actor. It cannot rely on `SecurityFilterChain` since there is no HTTP request. Whenever a system principal is genuinely allowed to bypass certain conditions, there must be a **named, scoped, audited, and tested exception policy**; never quietly use `isAdmin` to bypass tenants.

## 5. Standalone Runnable Java 17 Example: One Policy for Two Entry Points

The snippet below is a simplified model showing consistency between HTTP and consumer paths. It is **not** a running Spring server: the two methods `http` and `message` simulate two entry points, both calling one pure Java `ApprovalPolicy`. `amount`/`limit` use integers in the same assumed unit to stay focused on authorization.

Create file **`PolicyChangeDemo.java`**:

~~~java
import java.util.Set;

record Reviewer(String id, String tenant, Set<String> authorities, int limit) {}
record Invoice(String id, String tenant, String creator, int amount, String status) {}

final class ApprovalPolicy {
    static boolean allow(Reviewer user, Invoice invoice) {
        return user != null && invoice != null
                && user.authorities().contains("invoice:approve")
                && user.tenant().equals(invoice.tenant())
                && !user.id().equals(invoice.creator())
                && invoice.amount() <= user.limit()
                && "PENDING".equals(invoice.status());
    }
}

public class PolicyChangeDemo {
    static boolean http(Reviewer user, Invoice invoice) {
        return ApprovalPolicy.allow(user, invoice);
    }

    static boolean message(Reviewer user, Invoice invoice) {
        return ApprovalPolicy.allow(user, invoice);
    }

    public static void main(String[] args) {
        Reviewer reviewer = new Reviewer("bob", "t1", Set.of("invoice:approve"), 1000);
        Reviewer noPermission = new Reviewer("bob", "t1", Set.of(), 1000);
        Invoice eligible = new Invoice("i1", "t1", "alice", 700, "PENDING");
        Invoice own = new Invoice("i2", "t1", "bob", 700, "PENDING");
        Invoice expensive = new Invoice("i3", "t1", "alice", 1500, "PENDING");
        Invoice otherTenant = new Invoice("i4", "t2", "alice", 700, "PENDING");
        Invoice paid = new Invoice("i5", "t1", "alice", 700, "PAID");

        System.out.println("HTTP eligible: " + http(reviewer, eligible));
        System.out.println("Message eligible: " + message(reviewer, eligible));
        System.out.println("Own invoice: " + http(reviewer, own));
        System.out.println("Over limit: " + http(reviewer, expensive));
        System.out.println("Other tenant: " + message(reviewer, otherTenant));
        System.out.println("Already paid: " + http(reviewer, paid));
        System.out.println("No authority: " + http(noPermission, eligible));
    }
}
~~~

Run with **JDK 17 or later**:

~~~bash
javac --release 17 PolicyChangeDemo.java
java PolicyChangeDemo
~~~

**Verified stdout:**

~~~text
HTTP eligible: true
Message eligible: true
Own invoice: false
Over limit: false
Other tenant: false
Already paid: false
No authority: false
~~~

The first and second lines are both `true` because both entry points invoke the **exact same logic**. The remaining five cases cover the deny conditions: self-approval, over limit, cross-tenant, wrong state, and missing authority. If someone modifies `http` to check only the authority without updating `message`, tests comparing both entry points on the same fixture will catch the divergence.

In a real application, `Reviewer` details must be resolved from `Authentication` and a trusted authorization system; `Invoice` must be loaded from a repository. Never let the client choose `limit`, `tenant`, `creator`, or `status`. If a policy depends on time, organization, currency, lock state, or delegated permissions, those attributes must all be loaded and checked.

## 6. Applying in Spring Security: Request Rules, Method Rules, and Services

### 6.1. HTTP Rules Block Coarse Operations

**Illustrative** configuration example for Spring Security Servlet, placed in an application with Spring Web and Spring Security installed:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                    .hasAuthority("invoice:approve")
                .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Meaning: approval POSTs must have the exact authority `invoice:approve`; all other requests are blocked in this **illustrative security chain**. Real applications must declare additional valid endpoints, authentication/sessions or Bearer JWT, and configuration for the chosen stack. `@EnableMethodSecurity` enables method-level annotations. For cookie/session-based applications, `POST` remains subject to CSRF protection as configured; do not disable CSRF just to test an API.

**Ordering rule:** specific `requestMatchers` must be evaluated before `anyRequest`; matchers with wrong method/path or misordered security chains can create vulnerabilities or false rejections. Check route aliases, versioned mappings, path variables, and admin controllers too.

### 6.2. Service Policy Is the Resource-Level Decision Point

The snippet below is an **integration outline in a Spring application**, using application-defined types (`InvoiceRepository`, `ActorResolver`, `InvoicePolicy`); **not a standalone compilable program**:

~~~java
@Service
class InvoiceApprovalService {
    private final InvoiceRepository repository;
    private final ActorResolver actorResolver;
    private final InvoicePolicy policy;

    // Constructor injection omitted in the illustrative snippet.
    @Transactional
    @PreAuthorize("hasAuthority('invoice:approve')")
    public void approve(String invoiceId) {
        var actor = actorResolver.currentActor();
        var invoice = repository.findForUpdate(invoiceId)
                .orElseThrow(() -> new InvoiceNotFoundException(invoiceId));

        if (!policy.canApprove(actor, invoice)) {
            throw new AccessDeniedException("Invoice approval denied");
        }

        invoice.approve();
        // Persist inside transaction; publish business event after commit if needed.
    }
}
~~~

This code only illustrates where to place the check: before the state change, inside a transaction boundary with locking or an equivalent update mechanism. Production code needs constructors, imports, repository/policy implementations, and a trusted actor resolver. Another option is `@PreAuthorize("@invoicePolicy.canApprove(authentication, #p0)")` to call a policy bean by ID; the policy must then load the resource data. However, **never assume annotation checks and DB writes are automatically atomic**: AOP advisor/transaction ordering and concurrent updates must still be explicitly designed.

Points easily missed:

- `@PreAuthorize` on a Spring bean is usually enforced via a proxy. Calling a method on the same bean via `this.someMethod()` can **bypass** proxy security advice.
- `@EnableMethodSecurity` must be enabled for method security; annotations on objects created manually with `new` outside Spring management will not produce the expected enforcement.
- `hasRole("APPROVER")` by default convention checks authority `ROLE_APPROVER`; `hasAuthority("invoice:approve")` matches the exact string. When changing role → permission mappings, inspect where `GrantedAuthority` is created as well.
- `@PostAuthorize` or post-query filtering is unsuitable for protecting operations that already wrote data or emitted events; place checks **before** side effects.
- If a consumer or scheduler calls a service without an HTTP `SecurityContext`, define that task's actor, granted permissions, and how it invokes the policy. Never “spoof” a user actor from an unverified event field.

An HTTP request blocked at the filter may return 403 early; a request passing the filter yet denied by business policy must also stop the operation. **The two denial points do not need to share the exact same exception class**, as long as business decisions and side effects remain consistent and the API contract is standardized.

## 7. Repository and Transaction: Consistency Means Data Is Protected Too

### 7.1. Reading a Single Record and Reading Lists

Changing a policy from “having authority allows reading” to “read only invoices in the same tenant” requires both forms:

~~~sql
-- Query a single invoice (illustrative).
SELECT id, tenant_id, created_by, amount, status
FROM invoices
WHERE id = :invoiceId
  AND tenant_id = :trustedTenantId;
~~~

~~~sql
-- List query: scope must apply before LIMIT/OFFSET.
SELECT id, tenant_id, created_by, amount, status
FROM invoices
WHERE tenant_id = :trustedTenantId
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

`:trustedTenantId` must come from an authenticated identity or trusted tenant-resolution service, **not** a value the client can arbitrarily set. If viewing also depends on membership/ownership, add those predicates to the query per the real domain model; never fetch all records and filter in the UI or after pagination. `count` endpoints, search, exports, summary reports, and joins must honor the same data scope; otherwise users can observe out-of-scope counts, metadata, or pages.

### 7.2. Writing Data and Race Conditions

Checking `invoice.status == PENDING` before writing is insufficient if another transaction approves the invoice after the check. To preserve invariants, lock the record appropriately or use an **atomic conditional update**:

~~~sql
-- SQL sketch; parameters come from trusted policy context.
UPDATE invoices
SET status = 'APPROVED'
WHERE id = :invoiceId
  AND tenant_id = :trustedTenantId
  AND created_by <> :trustedActorId
  AND status = 'PENDING'
  AND amount <= :trustedApprovalLimit;
~~~

Before this statement, the service layer must still verify the `invoice:approve` authority, identify a valid actor, and ensure the policy applies properly to the invoice. Afterward, check the **affected row count**: `1` means the update succeeded; `0` must be handled per the API contract (not found, lost permission, state conflict...) and **must not publish an approval-succeeded event**. Systems using events/outbox must ensure side effects occur only when the transaction commits.

**There can be multiple technical embodiments of the same invariant** (domain policy plus an enforcing SQL condition to prevent state races). That is not a reason to drop one; instead, name the same rule in the specification and test them in sync. When changing a condition such as `amount <= limit` into a more complex approval tier, update both the domain policy and the data-update guard, or use another transaction mechanism guaranteeing the same semantics.

### 7.3. Distinguishing DENY From NOT_FOUND and CONFLICT

Returning `403 Forbidden`, `404 Not Found`, or `409 Conflict` depends on the API contract, resource-existence hiding strategy, and failure cause. A system may intentionally return 404 when the user must not learn a resource exists. Regardless of HTTP status code, the mandatory result is **no content leaked and no mutations written when the policy denies**. When unauthenticated, a Bearer API typically uses 401; 403 fits authenticated callers lacking permission. Never write tests checking only status codes while ignoring data or side effects.

## 8. Non-HTTP Execution Paths and Policy-Change Consequences

Not every action starts at a controller:

- **Message consumer**: receives `invoiceId` from a queue. The ID only identifies the resource; it is not proof the event emitter was allowed to approve. The consumer must verify the service actor/delegation, policy, and current resource state.
- **Scheduled job**: periodic runs may operate across multiple tenants. Define the service account, tenant scope, allowed actions, and any exception policy; never grant global privileges by default just because it “runs internally”.
- **GraphQL/gRPC/internal REST**: the same business logic may be invoked over other protocols. Never rely solely on an HTTP matcher if the service has multiple entry points.
- **Import/bulk operations**: each row may have a different owner/tenant. One coarse permission check before a batch does not replace per-resource scope checks.
- **UI/BFF**: disable or hide the Approve button per the new policy to prevent confusing failures, while remembering users can still call the API directly. UI is always only a presentation convenience.
- **Cached data or search indexes**: stale copies can return data whose permissions were revoked; verify authorization at response time or scope caches provably by permission/tenant.

An important test is **calling the use case with the same actor and invoice from at least two entry points**. Business outcomes must match, even if HTTP rejects early with 403 while a background job reports a different business error. Specifically verify that denied paths **do not update the DB, publish domain events, or send approval notifications**.

## 9. Role/Authority Changes, Tokens, and Caches: How Long Do “Old Permissions” Survive?

Many policy changes involve more than editing `@PreAuthorize`. For instance, an admin removes Bob's `invoice:approve` authority while Bob holds a JWT still valid for 30 minutes. If the app uses JWT claims as the source of authorities until expiration, Bob can keep exercising the old authority until the token expires, **unless** the system has an appropriate revocation or real-time permission check.

Identify every state-holding layer:

| State source | Risk when policy changes | How to control |
| --- | --- | --- |
| JWT carrying roles/authorities | Unexpired token retains revoked permissions | Tune TTL, revocation/version checks, or authority lookup per revocation requirements |
| Session / `Authentication` | Permissions loaded from an earlier session | Refresh/re-authentication/invalidation on critical permission changes |
| Authorization decision cache | Old `ALLOW` reused after policy update | Key by subject/action/resource/context/version; appropriate TTL and invalidation |
| Entity, list, search caches | Cross-tenant data / stale state | Scope keys properly, verify permissions on return, invalidate on ownership changes |
| App replicas running mixed versions | Replica A permits, replica B denies | Synchronized rollouts, intentional compatibility windows, policy version monitoring |
| Database replica / eventual consistency | Decision based on stale state | For sensitive actions, check against a transaction-consistent source; never trust lagging replicas |

A **policy version** (e.g., `invoice-approval-v2`) is a label for tracing and synchronization; it does not make tokens or caches safe by itself. Whenever changing rules, know where decisions might still run the old version. When immediate revocation is required, design fresh checks before executing actions; relying on long-lived unexpired tokens will fall short.

Audit logs should capture policy ID/version, actor ID, action, resource ID, tenant, outcome, and internal reason code per data-protection rules. Avoid logging raw tokens, passwords, detailed financial data, or unnecessary sensitive content.

## 10. Three-Level Consistency Verification

### 10.1. Policy Unit Tests

Unit tests must assert both allowed cases and every denied condition. Every condition change needs at least one “single failing condition” case to prove the exact guard works:

| Test case | Authority | Tenant | Creator | Status | Amount/limit | Expected |
| --- | --- | --- | --- | --- | --- | --- |
| Eligible | Yes | Match | Different actor | PENDING | 700/1000 | ALLOW |
| Permission revoked | No | Match | Different actor | PENDING | 700/1000 | DENY |
| Cross-tenant | Yes | Mismatch | Different actor | PENDING | 700/1000 | DENY |
| Self approval | Yes | Match | Same actor | PENDING | 700/1000 | DENY |
| Over limit | Yes | Match | Different actor | PENDING | 1500/1000 | DENY |
| Already finalized | Yes | Match | Different actor | PAID | 700/1000 | DENY |
| Missing actor/resource | Unknown | — | — | — | — | DENY |

Also test exact limit boundaries (`1000/1000` allowed if using `<=`), missing attributes, role mappings, Unicode characters in IDs if applicable, and same resource ID across different tenants. Tests should express policy **v2** explicitly, rather than copy-pasting the implementation into expected results.

### 10.2. Entry-Point and Data Integration Tests

With Spring MVC + `spring-security-test`, mock principals with the right authorities, call each HTTP method/path via `MockMvc` (with CSRF tokens when required), and also test services via public beans and consumer/job handlers. Verify:

1. Unauthenticated / lacking-authority requests are blocked at HTTP.
2. Requests with authority but wrong tenant, self-approval, wrong status, or over limit are blocked at the service.
3. Valid user succeeds **exactly once**; repeated requests do not approve a second time.
4. On deny, DB data, outbox, and related side effects **remain unchanged**.
5. List, search, count, and export share the same scope; swapping IDs in URLs cannot read/write others' records.
6. Method security takes effect via Spring proxies; test self-invocation paths if present in the architecture.
7. Both HTTP and message paths with identical trusted inputs reach the same decision.
8. Changing roles/permissions or activating a new policy version does not let data/decision caches grant revoked permissions.

**Status codes alone do not prove correctness.** An API returning 200 while leaking another tenant's record is still broken; an API returning 403 after mutating the DB is also broken. During test review, inspect response, DB state, events/outbox, and post-rollback behavior.

### 10.3. Cross-Layer Contract/Consistency Tests

Maintain a **shared scenario set** (v2 decision table) used as fixtures across relevant layers. Tests do not need to force HTTP filters and services to always return the exact same error type; they only need to verify the final observable outcome honors the contract.

~~~text
Scenario: reviewer=bob, tenant=t1, authority=invoice:approve
Resource: creator=alice, tenant=t2, status=PENDING, amount=700

HTTP route permission check: PASS (valid authority)
Domain policy: DENY (cross-tenant)
Persistence mutation: 0 rows
API observable outcome: not approved and no data leaked
Async consumer outcome: not approved for the same resource
Cache/audit: no ALLOW recorded for the new policy
~~~

In CI, you can build an actor × action × resource × entry-point matrix compared against a **shared expected decision**, while exercising multiple security chains/route aliases. Identify which endpoints a rule change affects; write meaningful tests per checkpoint rather than thousands of tests repeating the same mocked implementation.

## 11. Safe Policy-Change Rollout Process

### Phase A — Design and Review

1. Document business requirements, actor, action, resource, context, version, and effective time. Distinguish **revoking permissions**, **adding conditions**, and **expanding permissions**, because their impacts differ.
2. Build before/after decision matrices and agree on `ALLOW/DENY`, 401/403/404/409, exceptions, returned data, and side effects.
3. Enumerate all entry points and processing flows; identify the primary decision point and transaction/data guards.
4. Audit risks of tenant violations, horizontal/vertical escalation, stale tokens/caches, service-account privileges, and consumers still on the old version.
5. Define who may change policies, approval/versioning workflows, and how config changes are audited; editing a policy is itself a protected action.

### Phase B — Code Changes and Testing

1. Update the **domain policy** first as the source of truth; if permission names change, intentionally update authority mappings.
2. Review filter matchers, method annotations, and all entry points. Ensure deny-by-default where appropriate and no service shortcuts.
3. Update repository scoping, conditional updates/locking, cache invalidation, and consumers. The new policy must align with current data constraints.
4. Run unit matrices, integration tests, and negative tests. Verify DB/event state after denied requests.
5. Audit code paths with `permitAll`, `hasRole`, `hasAuthority`, `@PreAuthorize`, `@PostAuthorize`, direct repository access, service-account overrides, and anywhere client `tenantId` could be trusted.

### Phase C — Deployment and Monitoring

1. Plan transitions if multiple replicas, old tokens, or old schemas remain active. Never unintentionally widen permissions during a compatibility window.
2. Deploy the policy version with appropriate metrics/logs; monitor deny rates, routes, reason codes, tenants, instance distributions, and consumers.
3. Use feature flags or shadow evaluation when risk is high: **shadow decisions only observe/log**, never permitting an action when the active policy denies. Avoid sending sensitive data to shadow logs.
4. Verify key cases post-deploy, especially old tokens, caches, revoked roles, queued messages, and concurrent state transitions.
5. Prepare rollback aligned with the business contract: rolling back code can restore newly revoked permissions, so assess risks before reverting. For emergency revocations, prefer fail-closed denial modes rather than reopening permissions blindly.

## 12. Common Mistakes When Editing Only One Layer

| Mistake | Symptom | How to detect and fix |
| --- | --- | --- |
| Fixed URL rule, forgot service | API A blocks, yet job/API B still approves | Test the same policy scenario across all entry points; move detailed decisions into the service |
| Fixed `@PreAuthorize`, forgot self-invocation | Calls via controller are blocked, calls within the same bean bypass proxy | Test public bean paths; adjust boundary or enforce policy inside use case |
| Checked only authority without checking resource | Swapping ID reads/approves another tenant's data | Cross-tenant/ownership negative tests; scope repository |
| Fixed get-by-id but forgot list/export/count | Cannot read specific invoice ID yet sees list/metadata | Test every query form and pagination |
| Relied on UI to hide button | Manual API call still succeeds | Backend must verify every call |
| Skipped consumer as “internal” | Queued messages execute old permissions | Define service actor and invoke the same domain policy |
| Cache or JWT keeps old permissions | Revoked role still approves | Check TTL, revocation/versioning, invalidation |
| Checked policy before transaction then wrote later | Two workers approve the same invoice; state changes between check and update | Transaction locks or atomic conditional updates |
| Confused `hasRole` and `hasAuthority` | User has permission yet gets unexpected 403, or mapping over-grants | Audit actual `GrantedAuthority` values and `ROLE_` prefix |
| Policy changed without deny tests | Only happy-path passes in CI | Decision matrix for every new condition and entry point |
| Broadened fallback on policy-service failure | Losing connection to permissions allows everyone | Fail closed, return proper errors, monitor and retry safely |
| Rolled back to old policy without assessment | Revoked permissions reopen | Review rollbacks as independent authorization changes |

## 13. Pull Request Review Checklist for Authorization Changes

Answer **Yes/No**, with test paths or concrete evidence:

- [ ] `actor + action + resource + context` spec and v1/v2 comparison table exist.
- [ ] Roles/authorities are issued from trusted sources and mapped consistently.
- [ ] Route matchers, method annotations, and all relevant entry points were reviewed.
- [ ] Per-resource rules live in service/domain policy and execute before side effects.
- [ ] Repository query/list/count/export and updates are scoped by proper permission and tenant.
- [ ] Transactions or atomic updates protect state against races.
- [ ] Consumers/jobs/admin endpoints have explicit actors and policies.
- [ ] Token/session/cache/policy version behavior matches effective-time requirements.
- [ ] Tests exist for both ALLOW and DENY, covering cross-tenant, ownership, missing permission, wrong state, and races.
- [ ] Tests prove DENY causes zero DB/outbox/event mutations.
- [ ] API responses and audit logs record accurate outcomes without leaking sensitive data.
- [ ] Rollout/rollback plan prevents unintentionally reopening permissions.

**Learning conclusion:** “Cross-layer consistency” does not mean copying the exact same `hasAuthority` line everywhere. It means proving that **every execution path produces or honors a single policy decision**, from coarse permissions at HTTP, resource conditions in services, down to data constraints and side effects inside transactions. When policies change, **decision tables and cross-layer test suites** are the tools that catch places still running old rules.

### Official Reference Documentation

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
