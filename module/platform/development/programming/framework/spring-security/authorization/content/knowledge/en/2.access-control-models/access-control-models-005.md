# Combining Roles, Permissions, and Data Conditions in One Policy

In real systems, a **role** rarely answers "can this person process this specific record right now?" on its own. A user may belong to the support team and hold refund approval permission, yet the request belongs to a different store, is unassigned to them, or exceeds their approval limit. An accurate authorization policy must combine **role + permission + resource data + trusted context**.

This lesson explains how to construct a unified decision, express `AND`/`OR` clearly, avoid accidentally creating privilege shortcuts, and apply that decision in a Spring Security servlet-stack application. The goal is business-level access control, not just writing a `hasRole` expression.

## 1. Each Layer of Information Answers a Different Question

| Factor | Meaning | Example in a Refund System |
| --- | --- | --- |
| **Role** | Which group/responsibility does the caller belong to? | `ROLE_SUPPORT`, `ROLE_FINANCE_MANAGER`. |
| **Permission** | What kind of operation can the caller perform? | `REFUND_READ`, `REFUND_APPROVE`, `REFUND_EXPORT`. |
| **Caller Attributes** | What limits and context does the caller have? | `tenantId`, employee ID, approval limit. |
| **Resource Attributes** | What data does the specific record carry? | Requester, assignee, status, amount, tenant. |
| **Conditions / Context** | Which general invariants must hold? | Authenticated, no self-approval, request still pending. |

A **role** is typically a way to manage permission groups at an organizational level. A **permission** is a privilege for a specific action; it may be granted via a role or directly per system policy. **Data conditions** decide whether that privilege applies to the *current object*.

For example, `ROLE_FINANCE_MANAGER` does not automatically mean "allowed to approve every request in every tenant". And `REFUND_APPROVE` does not automatically mean "allowed to approve requests regardless of amount and status".

In Spring Security, `Authentication.getAuthorities()` returns `GrantedAuthority` instances; both roles and permissions are commonly represented as string authorities. With default prefix configuration:

- `hasRole("SUPPORT")` checks for the authority `ROLE_SUPPORT`.
- `hasAuthority("REFUND_APPROVE")` checks for the exact authority `REFUND_APPROVE`.
- `hasAnyRole("SUPPORT", "FINANCE_MANAGER")` accepts either corresponding role.
- Mapping roles to permissions in the application is a **design decision**; Spring Security does not inherently know which business permissions `ROLE_SUPPORT` should contain.

Do not treat a role name as a data policy itself. Roles express responsibility groups; permissions express actions; conditions express **when and on which record** an action is valid.

## 2. Running Scenario: Approving a Refund Request

Suppose there is a multi-store (multi-tenant) system. Support staff and finance managers can both be granted `REFUND_APPROVE`, but their enforcement scope differs. For someone to approve a request, the system defines this illustrative policy:

1. The caller must be **authenticated** and hold the `REFUND_APPROVE` permission.
2. The refund request must be in the **same tenant** as the caller.
3. The request status must be **`PENDING`**.
4. The refund amount must not exceed the caller's **approval limit**; the limit comes from trusted server configuration/data.
5. The approver **must not also be the requester** (separation of duties).
6. One of two paths must hold: the employee has `ROLE_SUPPORT` **and is assigned to handle the request**, or has `ROLE_FINANCE_MANAGER` in the same tenant.

The policy can be written logically as:

~~~text
ALLOW =
    authenticated
    AND hasPermission(REFUND_APPROVE)
    AND (actor.tenantId == refund.tenantId)
    AND (refund.status == PENDING)
    AND (refund.amount <= actor.approvalLimit)
    AND (actor.id != refund.requesterId)
    AND (
         (hasRole(SUPPORT) AND actor.id == refund.assignedTo)
         OR hasRole(FINANCE_MANAGER)
    )

DENY = all remaining cases
~~~

Parentheses are critical. If miswritten as:

~~~text
(sharedConditions AND assignedSupport) OR financeManager
~~~

then the `financeManager` branch could **bypass tenant, status, limit, or the no-self-approval rule**. A branch letting a manager bypass a condition should exist only when the business specifies that exception *explicitly*. In this lesson, **every role must satisfy the shared conditions**.

This deliberately combines three ways of thinking:

- **RBAC:** only eligible role groups have a path to the operation.
- **Action-level permission:** `REFUND_APPROVE` differs from `REFUND_READ`; read access does not imply approval access.
- **ABAC/ReBAC:** tenant, amount, and status are attributes; "assigned to handle" and "not the requester" tie the caller to the specific resource.

## 3. Decision Table: Every Missing Condition Must Deny

Suppose `sue` has `ROLE_SUPPORT`, `REFUND_APPROVE`, belongs to `tenant-a`, limit 500; `mia` has `ROLE_FINANCE_MANAGER`, `REFUND_APPROVE`, belongs to `tenant-a`, limit 1,000. A request for 300 is `PENDING`, created by `customer-1` and assigned to `sue`.

| Caller and Variant | Result | Decisive Condition |
| --- | --- | --- |
| Sue approves assigned request, amount 300 | **ALLOW** | Sufficient role, permission, and all shared conditions. |
| Sue approves request assigned to Bob | **DENY** | Support role must match the assignee. |
| Mia approves request assigned to Bob, amount 300 | **ALLOW** | Manager branch is allowed without assignment; shared conditions still hold. |
| Sue has support role but lacks `REFUND_APPROVE` | **DENY** | Role alone is insufficient. |
| User has permission but only holds `ROLE_CUSTOMER` | **DENY** | Does not have an eligible branch role. |
| Sue approves amount 600 | **DENY** | Exceeds limit of 500. |
| Sue approves request from `tenant-b` | **DENY** | Different tenant. |
| Sue approves an already `APPROVED` request | **DENY** | Status does not allow re-approval. |
| Sue approves a request created by Sue herself | **DENY** | Violates no-self-approval rule. |
| Unauthenticated caller with matching permission data | **DENY** | Missing authentication condition. |

This table also illustrates that **permissions do not automatically expand data scope**. When the permission is present without a matching record relationship/attribute, the decision is still DENY. When the permission is missing, a valid role is still denied.

## 4. Mapping Roles to Permissions: When Should You Check Both?

Two valid design patterns exist, and they represent **two different policies**.

**Style A — roles grant permissions; policy checks permission and data.** For example, the system grants `REFUND_APPROVE` to authorized staff, whether via a role or another approved grant mechanism. The remaining rule is:

~~~text
authenticated AND REFUND_APPROVE AND dataConditions
~~~

Here, permission is the source of truth for the action. Re-checking `hasRole` is unnecessary if the business allows anyone granted that permission to use it within valid data scope. A role → permission table or `RoleHierarchy` can reduce long role expressions; ensure effective permissions are granted/represented accurately in `Authentication`.

**Style B — the business requires both belonging to an eligible role group and holding the permission.** For example, the approval workflow is strictly reserved for support or finance managers, even if another account were mistakenly granted `REFUND_APPROVE`. Then both role and permission must remain in the policy:

~~~text
authenticated
AND hasAnyRole(SUPPORT, FINANCE_MANAGER)
AND hasPermission(REFUND_APPROVE)
AND dataConditions
~~~

This lesson chooses **Style B** to illustrate coordinating all three layers. Adding `hasRole` to a rule just "to be safe" can cause unexpected denials when permissions are legitimately granted to a new role; conversely, omitting a role from a policy that genuinely requires group restriction can open a vulnerability. The choice must follow the **approved business rules**.

**Avoid arbitrary ORs:** `hasRole('ADMIN') || hasAuthority('REFUND_APPROVE')` lets the ADMIN role bypass the permission requirement. If an admin role should have approval rights, explicitly define that role as granting `REFUND_APPROVE` in the permission model, and still enforce mandatory data conditions. When a policy has legitimate exceptions, state the exception in a named branch and test that remaining conditions still hold.

## 5. A Runnable Pure Java 17+ Policy Function

The following example expresses the **final decision** without Spring dependencies, making it easy to verify logic before wiring it into web/service layers. Fields in `Actor` are treated as **server-authenticated/verified facts**. In real integration, never read `tenantId`, `roles`, `permissions`, or `approvalLimit` directly from an arbitrary client-sent request body.

Save with the exact filename **RefundAuthorizationDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.Set;

public class RefundAuthorizationDemo {
    enum Status { PENDING, APPROVED }

    record Actor(String id, String tenantId, Set<String> roles,
                 Set<String> permissions, BigDecimal approvalLimit,
                 boolean authenticated) {}

    record Refund(String tenantId, String requesterId, String assignedTo,
                  BigDecimal amount, Status status) {}

    static boolean canApprove(Actor actor, Refund refund) {
        if (actor == null || refund == null || !actor.authenticated()) {
            return false;
        }
        if (!actor.tenantId().equals(refund.tenantId())
                || !actor.permissions().contains("REFUND_APPROVE")
                || refund.status() != Status.PENDING
                || refund.amount().compareTo(actor.approvalLimit()) > 0
                || actor.id().equals(refund.requesterId())) {
            return false;
        }
        boolean assignedSupport = actor.roles().contains("ROLE_SUPPORT")
                && actor.id().equals(refund.assignedTo());
        boolean financeManager = actor.roles().contains("ROLE_FINANCE_MANAGER");
        return assignedSupport || financeManager;
    }

    public static void main(String[] args) {
        Actor sue = new Actor("sue", "tenant-a",
                Set.of("ROLE_SUPPORT"), Set.of("REFUND_APPROVE"),
                new BigDecimal("500"), true);
        Actor mia = new Actor("mia", "tenant-a",
                Set.of("ROLE_FINANCE_MANAGER"), Set.of("REFUND_APPROVE"),
                new BigDecimal("1000"), true);
        Actor noPermission = new Actor("ned", "tenant-a",
                Set.of("ROLE_SUPPORT"), Set.of(),
                new BigDecimal("500"), true);
        Actor noEligibleRole = new Actor("lee", "tenant-a",
                Set.of("ROLE_CUSTOMER"), Set.of("REFUND_APPROVE"),
                new BigDecimal("500"), true);
        Actor anonymous = new Actor("guest", "tenant-a",
                Set.of("ROLE_SUPPORT"), Set.of("REFUND_APPROVE"),
                new BigDecimal("500"), false);

        Refund assigned = new Refund("tenant-a", "customer-1", "sue",
                new BigDecimal("300"), Status.PENDING);
        Refund unassigned = new Refund("tenant-a", "customer-1", "bob",
                new BigDecimal("300"), Status.PENDING);
        Refund expensive = new Refund("tenant-a", "customer-1", "sue",
                new BigDecimal("600"), Status.PENDING);
        Refund foreignTenant = new Refund("tenant-b", "customer-1", "sue",
                new BigDecimal("300"), Status.PENDING);
        Refund alreadyApproved = new Refund("tenant-a", "customer-1", "sue",
                new BigDecimal("300"), Status.APPROVED);
        Refund selfApproval = new Refund("tenant-a", "sue", "sue",
                new BigDecimal("300"), Status.PENDING);

        System.out.println("Support assigned: " + canApprove(sue, assigned));
        System.out.println("Support unassigned: " + canApprove(sue, unassigned));
        System.out.println("Manager unassigned: " + canApprove(mia, unassigned));
        System.out.println("Missing permission: " + canApprove(noPermission, assigned));
        System.out.println("Ineligible role: " + canApprove(noEligibleRole, assigned));
        System.out.println("Above limit: " + canApprove(sue, expensive));
        System.out.println("Cross tenant: " + canApprove(sue, foreignTenant));
        System.out.println("Already approved: " + canApprove(sue, alreadyApproved));
        System.out.println("Self approval: " + canApprove(sue, selfApproval));
        System.out.println("Anonymous: " + canApprove(anonymous, assigned));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac RefundAuthorizationDemo.java
java RefundAuthorizationDemo
~~~

Output:

~~~text
Support assigned: true
Support unassigned: false
Manager unassigned: true
Missing permission: false
Ineligible role: false
Above limit: false
Cross tenant: false
Already approved: false
Self approval: false
Anonymous: false
~~~

Observe how the policy is structured: the function rejects requests violating **shared conditions** first, then evaluates the two **role branches**. `&&` defines jointly mandatory conditions; `||` defines two permitted paths **within the shared scope**. When adding a new role, deliberately add a matching branch and test cases; do not bypass prior conditions.

The example uses `BigDecimal.compareTo` instead of `double` comparisons for money to avoid binary floating-point comparison bugs. The `record` model is immutable example data; in real systems fetch the **current** status and amount from the database rather than relying on a client-supplied copy.

## 6. Integrating the Policy into Spring Security: HTTP, Method, and Resource Layers

A clear implementation in Spring Boot 3 / Spring Security 6 on the servlet stack separates responsibilities:

| Location | What It Blocks | What Not to Expect |
| --- | --- | --- |
| **HTTP authorization** | Routes requiring login/baseline permissions. | Does not know record status or assignee before loading data. |
| **Method security** | Permission to invoke business actions, e.g., eligible roles and `REFUND_APPROVE`. | A simple authority expression is not enough to decide on a specific object. |
| **Domain policy in service** | Tenant, amount, limit, assignment relationship, status, anti-self-approval. | Cannot trust client-declared attributes; must use trusted data. |

**HTTP-layer guard configuration** — snippet for a Spring project with the corresponding dependencies; not a standalone Java program:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/refunds/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Corresponding imports include `@Configuration`, `@Bean` from Spring Framework; `@EnableMethodSecurity`, `HttpSecurity`, and `SecurityFilterChain` from Spring Security. In the configuration above, `authenticated()` is **only a general gate**: it has no tenant, owner, or amount condition yet. For APIs with public endpoints, declare them explicitly before `anyRequest().denyAll()`. CSRF, session, or bearer token authentication configuration must be completed according to the application type; do not infer it from this short snippet.

**Method security** attaches role and permission rules to service methods:

~~~java
@PreAuthorize("""
    hasAnyRole('SUPPORT', 'FINANCE_MANAGER')
    and hasAuthority('REFUND_APPROVE')
    """)
@Transactional
public void approveRefund(long requestId) {
    ActorContext actor = currentActor.requireAuthenticated();
    RefundEntity refund = repository
            .findByIdAndTenantId(requestId, actor.tenantId())
            .orElseThrow(() -> new EntityNotFoundException("Refund not found"));

    if (!refundPolicy.canApprove(actor, refund)) {
        throw new AccessDeniedException("Refund approval denied");
    }

    refund.approveBy(actor.userId());
}
~~~

This is an **illustrative excerpt inside a Spring-managed service**, not a standalone Java class: `ActorContext`, `currentActor`, `RefundEntity`, `repository`, and `refundPolicy` are application-defined; imports for `@PreAuthorize`, `@Transactional`, and `AccessDeniedException` are needed in the real class. `currentActor` must be built from a trusted security context and server data; `repository.findByIdAndTenantId` must filter by tenant in the query. `refundPolicy.canApprove` should enforce the **entire policy**, including role/permission, so the business layer retains the rules if invoked via another path.

`@EnableMethodSecurity` must be enabled explicitly; Spring Boot Starter Security does not turn on method security automatically. `@PreAuthorize` operates via Spring AOP: **internal calls between two methods on the same instance** generally bypass the proxy, so do not rely solely on annotations to uphold critical business invariants. Re-checking inside the service/policy prevents gaps when call paths change.

**Why load the object before deciding?** Because with only `requestId` in `@PreAuthorize`, we lack trusted data to evaluate `PENDING`, `assignedTo`, and amount. Calling a policy bean from `@PreAuthorize` is possible if the bean loads data itself, but consider duplicate query cost and the risk of data changing between check and update. For update operations, checking state and applying the change inside one transaction is usually easier to control.

In the pattern above, callers lacking role/permission are rejected before the service runs. Callers with general permission who violate record conditions are rejected by the policy after loading data. If the object belongs to another tenant, the tenant-scoped query yields "not found", avoiding accidental disclosure of another tenant's records. Choosing `403` vs `404` responses in that case must be applied consistently across the API design.

## 7. Combining Policies Without Creating Logic Gaps

Think of each condition as a `boolean` predicate. Instead of a SpEL expression dozens of operators long, group meaningful predicates:

~~~text
sharedConditions(actor, refund):
  authenticated && permission && sameTenant && pending
  && withinLimit && noSelfApproval

roleScope(actor, refund):
  (supportRole && assignedToActor) || financeManagerRole

canApprove(actor, refund):
  sharedConditions(actor, refund) && roleScope(actor, refund)
~~~

Points to watch when modifying policies:

- **Every ALLOW path must pass shared constraints.** Use explicit parentheses for `AND` and `OR`; never rely on operator precedence memory.
- **Roles are not unconditional permissions.** A role with many permissions still needs tenant, state, and limit constraints.
- **Never grant permissions from client-supplied names.** Users can send fake `role=ADMIN` or `tenantId`. The server must read permissions from verified identity/session/token data and load objects from the data store.
- **Avoid duplicating policy logic.** Annotations can guard early, but the core data decision should live in one reusable policy function. If controller, service, and job logic drift out of sync, the same record can get conflicting outcomes.
- **Avoid implicit privilege expansion via new roles.** If a new role is allowed to approve, define its permissions, resource scope, and limits explicitly. Update the decision table and corresponding negative cases.
- **Least privilege and deny by default.** If no valid ALLOW path matches, deny; never assume "logged-in users can act".
- **Do not make update decisions from stale data.** Roles/permissions can be revoked; status and limits can change after the screen opens. Depending on security requirements, refresh permissions and read data close to write time.

Another framework-level approach is composing `AuthorizationManager` instances (such as `allOf`/`anyOf`) for decisions where managers have enough context. That helps with general authorization, but does not automatically solve loading the exact object and enforcing data invariants. For complex business rules, a policy service with clear inputs and outputs is usually easier to read and test.

## 8. Transactions, Concurrency, and Revoked Permissions

Authorization is not just about rendering UI buttons. Suppose two employees send approval requests simultaneously:

1. Both read `PENDING` status.
2. Both pass the policy.
3. Without concurrency control, both could trigger unintended approval/payout side effects.

To preserve the "approve once" invariant, combine the policy with **transactions**, **optimistic locking** (`@Version`), or **conditional update statements** such as `WHERE status = 'PENDING'`; check the actual affected row count before triggering financial side effects. Checks and updates must sit close together transactionally. Correct authorization with a non-atomic write is still unsafe.

In multi-tenant systems, scope queries at the data store whenever possible—for example by `id` **and** `tenantId`, especially for list queries. Filtering record-by-record after fetching everything can leak data via responses, pagination, statistics, or caches.

Authorities in a JWT can reflect permissions at token issuance time. If the system requires **near-instant revocation**, long-lived tokens carrying only a permission snapshot may fall short; consider short-lived tokens, dynamic permission lookups, or session/token revocation mechanisms. This rule applies regardless of `hasRole` or `hasAuthority` syntax.

## 9. Testing the Full Role × Permission × Data Combination

The best tests do not merely verify that ADMIN or SUPPORT succeeds. From the policy table, build variants testing each condition and key combinations:

| Test Group | Required Cases |
| --- | --- |
| **Authentication** | Unauthenticated, locked/invalid account, expired session. |
| **Role** | Eligible role, ineligible role even with permission, unapproved new role. |
| **Permission** | Has approval permission, read-only permission, revoked permission. |
| **Tenant** | Same tenant, different tenant, attempted tenant ID tampering in request. |
| **Relationship** | Assigned support, unassigned support, same-tenant manager. |
| **Status** | PENDING, APPROVED, CANCELLED, or non-transitionable states. |
| **Limit** | Below, exactly equal to, and above limit; never use `double` for money. |
| **Separation of duties** | Approver is also the requester. |
| **Call paths** | HTTP, internal service calls, background jobs, other endpoints sharing the workflow. |
| **Concurrency** | Two competing approval requests on the same record; only one valid update succeeds. |

Tests can be split into **unit tests for the pure policy** (fast, covering all branches), **service and repository integration tests** (verifying tenant, transactions, locking), and **HTTP/method security tests** (401/403 or 404 convention, annotations, authority mapping). With Spring Security Test, `@WithMockUser` helps test roles/authorities, yet you still need record fixtures in different states; mocking roles alone does not prove data conditions are right.

Test **near-miss cases missing exactly one condition**: has role but lacks permission; has permission but wrong tenant; right tenant but unassigned; everything valid except over limit. These expose `OR` vs `AND` mistakes and missing data checks far better than happy-path tests alone.

## 10. Common Pitfalls and Expressing Policies Clearly

1. **Writing only `hasRole('MANAGER')`** and letting them edit any object. → Add action permissions and object checks in the business layer.
2. **Writing only `hasAuthority('REFUND_APPROVE')`** when the spec also mandates specific role groups. → Add the role-group constraint *if* the business truly requires it.
3. **`roleA || permissionB && dataCondition` without parentheses.** → Express policies as named predicates and test every ALLOW branch.
4. **Treating `ROLE_ADMIN` as an implicit bypass for tenant and status.** → Only permit explicitly documented and tested exceptions.
5. **Trusting `ownerId`/`tenantId`/`approvalLimit` sent from the frontend.** → Derive identity from authentication and permission/resource data from the server.
6. **Putting policies only in controllers.** → Bind checks to the business operation and reuse across all entry points.
7. **Guarding only at `@PreAuthorize`, then updating stale data.** → Verify data conditions close to writes with transactions and concurrency protection.
8. **Testing only ALLOW cases.** → Every mandatory component needs at least one DENY case; also test combined branches and concurrency.

A vague requirement like "finance staff can approve refunds" must become a testable statement: **"An authenticated user with `REFUND_APPROVE`, holding either assigned SUPPORT or FINANCE_MANAGER role, may only approve PENDING requests within their own tenant, within their approval limit, and not created by themselves."** That policy lets you write decision tables, policy functions, Spring configs, and tests without inventing permissions outside the specification.

**Key takeaway:** roles define responsibility paths, permissions define actions, and data/relationships/context narrow the target object and execution timing. When combining them, keep **shared conditions outside**, **role paths inside parentheses**, enforce decisions on the server, and default to **DENY** when all rules are not satisfied.

### References

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
