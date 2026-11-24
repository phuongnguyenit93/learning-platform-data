# Separation of Duties and Controlling Sensitive Actions

## 1. The Problem: One Person Should Not Execute an Entire High-Risk Workflow Alone

In a Spring Security application, authorization does not stop at "does this account have `ROLE_MANAGER` or `payment:approve`?". When an action can transfer funds, alter admin privileges, export sensitive data, or delete critical records, the system must also check the **requester**, **approver**, **specific object**, **workflow state**, **assigned scope**, and **approval evidence**.

Suppose an employee creates a payment request for 120 million VND. Because they wear multiple hats, they hold both creation and approval permissions. If the application checks only `hasAuthority("payment:approve")`, they can approve their own request. The function-level check passes as configured, yet the risk-control policy has failed.

**Separation of duties** (**SoD**) is the principle preventing one subject from holding or performing incompatible steps within the same workflow. Practically, it limits the chance of one person creating, approving, and completing a transaction without independent oversight.

A sound system needs two layers:

1. **Restrict granted permissions:** do not grant conflicting permissions to the same person when policy requires strict separation.
2. **Restrict how permissions are used:** even when someone legitimately holds multiple permissions, prevent using them to perform conflicting steps on the **same object or transaction**.

SoD does not replace authentication, authorization, or auditing. It is an **additional constraint on granting and exercising permissions**, especially valuable for sensitive actions.

### Before and After Picture

| Abuse-Prone Workflow | Controlled Workflow |
| --- | --- |
| A creates request → A self-approves → A executes payment | A creates request → B independently reviews → C executes once sufficiently approved |
| Admin A creates a privileged account and grants themselves access | A requests elevation → B approves scope/duration → system grants and logs |
| Manager edits payment details and confirms them alone | Editor and change approver are two distinct subjects |
| Checks only `approve` permission | Checks permission + relationship to creator + tenant + limit + state + evidence |

Learning objectives: understand forms of SoD, model policies, implement reliable guards in Spring Security, test forbidden actions, and govern controlled exceptions.

## 2. Concepts and Boundaries to Distinguish

### 2.1. Roles, Permissions, Duties, and Actions

- **Role:** a job responsibility group, e.g., `PAYMENT_CREATOR` or `PAYMENT_APPROVER`.
- **Permission / Authority:** a specific capability such as `payment:create`, `payment:submit`, `payment:approve`, `payment:execute`, `user:grant-privilege`.
- **Duty:** a meaningful workflow step, such as drafting, reviewing, approving, or executing.
- **Sensitive action:** an operation with major financial, data, access-control, or system-integrity impact.
- **Conflict constraint:** a rule forbidding combining two roles/permissions/duties within a defined scope.
- **Independent approval:** a decision made by an authorized subject who is not the requester or performer of an incompatible prior step.

For example, `ROLE_APPROVER` or authority `payment:approve` is only a function-level grant condition; **it does not automatically prove the approver is independent of the creator**. Identity must rely on a stable server-authenticated ID, not a client-supplied display name or email.

### 2.2. Static SoD vs. Dynamic SoD

**Static Separation of Duties (Static SoD, SSD):** restricts **assigning** conflicting roles/permissions to the same person.

Example: policy forbids one person from simultaneously holding `ROLE_AUDITOR` and `ROLE_AUDIT_SUBJECT_ADMIN`. At role-assignment time, the application must reject creating the conflicting combination. When role hierarchies or inherited permission groups exist, evaluate **effective permissions**, not only directly assigned roles.

**Dynamic Separation of Duties (Dynamic SoD, DSD):** restricts **performing** two conflicting duties within a session, workflow, or on the same object.

Example: an employee holds both `payment:create` and `payment:approve` due to shift rotation. They can create transaction X and approve transaction Y, but may not approve transaction X themselves. This rule is commonly called **maker–checker**.

| Criterion | Static SoD | Dynamic SoD |
| --- | --- | --- |
| Control target | Role/permission assignment | Performing actions, workflows, objects |
| Timing | When granting, changing, or inheriting permissions | At the moment a sensitive action is requested |
| Example | Never grant two conflicting roles simultaneously | Holds both permissions, cannot self-approve own request |
| Required data | Roles, authorities, hierarchies, conflict sets | Identity, creator, approval history, tenant, status, limits |
| Common mistake | Checking only directly assigned roles | Checking only roles while ignoring relationship to the transaction |

Do not force one model onto every organization. Static SoD is easier to reason about and administer but can reduce flexibility; dynamic SoD supports duty rotation yet requires accurate recording of state and actions.

### 2.3. Maker–Checker, Four-Eyes, Dual Control, and Multi-Level Approval

Related terms that are not strictly synonymous:

- **Maker–checker:** the initiator and the reviewer/approver are independent subjects; typically applied per specific object.
- **Four-eyes principle:** at least two independent people participate in reviewing an action; commonly implemented via maker–checker.
- **Dual control:** executing a sensitive step requires participation/approval from at least two authorized subjects per policy; may be simultaneous or staged.
- **Multi-level approval:** a transaction may have to pass two approvers, two organizational tiers, or one approver plus one operator. Two clicks by the same person **are not** two independent subjects.

Number of "approvals" and number of **distinct identities** are two different quantities. If "two approvers" are required, person B approving twice or two accounts controlled by one person undermines the control. Define independence organizationally: distinct user IDs, distinct teams, distinct reporting lines, distinct units, or absence of conflict of interest. A system can only verify relationships that are reliably managed and recorded.

### 2.4. Prevention, Detection, and Recovery

SoD is a **preventive** control: it blocks transactions before damage occurs. Audit logs, alerts, and reconciliation are **detective** controls: they uncover actions that occurred or were denied. Reversal/recovery is a **corrective** control when mistakes happen. Logging after money has moved never substitutes for approval checks before transfer.

SoD reduces the risk of single-actor abuse; it cannot eliminate multi-party collusion, compromised identities, or one person controlling multiple accounts. Strong authentication, identity governance, monitoring, and independent reconciliation remain essential.

## 3. Identifying Which Actions Require Stronger Protection

Not every API needs two approvers. Adding controls carries operational cost and can create bottlenecks if misplaced. Start by classifying impact and identifying a feature's "danger boundary".

| Action Category | Examples | Controls Commonly Considered |
| --- | --- | --- |
| Money and legal obligations | Fund transfers, large refunds, disbursement approval | Maker–checker, limits, multi-level approval, evidence logging |
| Access control changes | Creating admins, granting special privileges, role changes | Independent approval, temporary access, auditing |
| Sensitive data | Bulk exports, granting personal data access | Data scoping, risk-based approval, quotas |
| Critical configuration changes | Rotating secrets, disabling controls, editing approval rules | Requester distinct from approver, step-up authentication |
| Hard-to-reverse deletions/reversals | Permanent deletion, canceling settled transactions | Two-step confirmation, pending approval, recovery mechanism |
| Low-risk routine actions | Viewing public data, UI preferences | Standard authorization; do not require two people by default |

Distinguish **action sensitivity** from **data sensitivity**. Viewing a single record may need only read permission; exporting millions of records carries far higher risk even on the same data domain.

A sound policy should answer:

1. Who can **propose** the operation?
2. Who can **approve** it, and must they be independent of the proposer?
3. Are **two distinct approvers** or **two tiers** required?
4. When is **re-authentication or step-up MFA** required?
5. Who can **execute** after approval, and may they overlap with maker/approver?
6. What are the value limits, tenant, state, timing, and approval expiration rules?
7. If data changes after approval, is the prior approval still valid?

The final question is crucial: you cannot approve content A, allow editing it into content B, and still reuse A's approval.

## 4. Policy Design: Payment Transaction Example

Suppose the application has a `PaymentRequest` with trusted server-stored fields:

| Field | Meaning |
| --- | --- |
| `id` | Transaction ID |
| `tenantId` | Organization owning the transaction |
| `createdBy` | Creator ID, never freely editable from requests |
| `amountVnd`, `beneficiary` | Amount and beneficiary |
| `status` | DRAFT, PENDING, APPROVED, REJECTED, EXECUTED |
| `version` | Request version to prevent reusing stale approvals |
| `approvals` | Approval records with identity, timestamp, decision, and content version |
| `executedBy` | Subject executing once conditions are met |

### 4.1. Duty and Constraint Matrix

This is an **illustrative policy**, not a Spring Security default:

| Action | Authority | Key Conditions | Effect When Passed |
| --- | --- | --- | --- |
| Create draft | `payment:create` | Valid tenant, assigned scope | Create DRAFT with `createdBy` from principal |
| Edit draft | `payment:edit` | Same tenant, is creator, DRAFT | Update data, increment version |
| Submit for approval | `payment:submit` | Same tenant, is creator, DRAFT, valid data | DRAFT → PENDING, freeze content for review |
| Approve | `payment:approve` | Same tenant, not creator, within limit, PENDING, not already approved this round | Record approval event for current version |
| Reject | `payment:reject` | Same tenant, authorized, PENDING | PENDING → REJECTED, record reason |
| Execute | `payment:execute` | Same tenant, right scope, sufficient valid approvals, APPROVED | Execute once, update to EXECUTED |

Additional illustrative threshold rules:

- Under 100 million: requires at least **one approver with sufficient limit**, distinct from the creator.
- 100 million or above: requires **two distinct approvers**, both distinct from the creator; depending on the organization, the second may need a different management tier.
- Each person contributes at most **one decision** per transaction version; clicking twice cannot produce two approval signatures.
- The executor may have to differ from the maker/approvers if the workflow requires it. This is a **separate independence constraint** beyond approval count.
- If amount, beneficiary, or sensitive fields change after approval, **invalidate prior approvals and require re-approval**.

Thresholds are examples for practicing design; each organization must approve its own numbers and conditions.

### 4.2. State Is Part of the Policy

```text
DRAFT --(submit, maker)--> PENDING
PENDING --(reject, authorized user)--> REJECTED
PENDING --(enough independent approvals, matching version)--> APPROVED
APPROVED --(execute, valid permission and limits)--> EXECUTED

Forbidden:
  DRAFT -> EXECUTED
  PENDING -> EXECUTED without enough approvals
  EXECUTED -> APPROVED again
  PENDING -> self-approved by maker
```

When building APIs, never let clients send `status="APPROVED"` for the server to persist directly. State transitions must happen inside business methods enforcing permissions and conditions. An admin endpoint that "directly edits status" can become a bypass breaking all SoD.

### 4.3. Invariants to Uphold

Some invariants can be written as testable conditions:

```text
approval.approverId != payment.createdBy
approval.tenantId == payment.tenantId
approval.paymentVersion == payment.version
count(distinct validApproverId) >= requiredApproverCount(payment)
payment.status == APPROVED before execute
execute must not complete more than once for the same transaction version
```

Count approvers only after verifying each approval record was created via an authorized flow, remains valid, and binds to the **exact content version**. Never trust a list of approval IDs sent by the client.

### 4.4. Who Decides Permissions?

Distinguish clearly:

- **Subject (principal):** who is logged in? The identity provider or login mechanism verifies identity.
- **Permission:** what kind of action is allowed? Can be represented by `GrantedAuthority`.
- **Business constraints:** not the creator, same tenant, within limit, right status, no duplicate approval, no role conflict?
- **Final decision:** allow only when **all** mandatory conditions hold. When policy info is missing, deny by default.

RBAC expresses baseline permissions; ABAC/object relationships express tenant, amount, status, and approval history. SoD can use both kinds of conditions. No default Spring Security annotation automatically understands "not the creator of this transaction".

## 5. Standalone Java 17 Example: Is Approval Permitted?

This example intentionally separates logic from Spring so principles can be tested before framework integration. The program **evaluates** approval eligibility; it does not persist database updates and does not replace atomic transactions in real applications.

Save the file as `SeparationOfDutiesDemo.java`:

```java
import java.util.Set;

public class SeparationOfDutiesDemo {
    enum Status { DRAFT, PENDING, APPROVED, EXECUTED }

    record Actor(
        long id,
        long tenantId,
        Set<String> authorities,
        long approvalLimitVnd,
        boolean active
    ) {}

    record Payment(
        long id,
        long tenantId,
        long createdBy,
        long amountVnd,
        Status status,
        Set<Long> approvedBy
    ) {}

    static boolean canApprove(Actor actor, Payment payment) {
        return actor != null
            && payment != null
            && actor.active()
            && actor.authorities() != null
            && payment.approvedBy() != null
            && actor.authorities().contains("payment:approve")
            && actor.tenantId() == payment.tenantId()
            && actor.id() != payment.createdBy()
            && payment.status() == Status.PENDING
            && payment.amountVnd() >= 0
            && payment.amountVnd() <= actor.approvalLimitVnd()
            && !payment.approvedBy().contains(actor.id());
    }

    // Count only approver identities verified and stored by the server.
    // This method illustrates the count condition; it does not sign approvals itself.
    static boolean enoughApprovals(Payment payment) {
        if (payment == null || payment.approvedBy() == null) {
            return false;
        }
        int required = payment.amountVnd() >= 100_000_000 ? 2 : 1;
        return payment.approvedBy().size() >= required
            && !payment.approvedBy().contains(payment.createdBy());
    }

    public static void main(String[] args) {
        Actor maker = new Actor(
            10, 1, Set.of("payment:create", "payment:approve"),
            500_000_000, true
        );
        Actor reviewerA = new Actor(
            20, 1, Set.of("payment:approve"), 50_000_000, true
        );
        Actor reviewerB = new Actor(
            30, 1, Set.of("payment:approve"), 200_000_000, true
        );
        Actor otherTenant = new Actor(
            40, 2, Set.of("payment:approve"), 200_000_000, true
        );

        Payment small = new Payment(
            101, 1, 10, 40_000_000, Status.PENDING, Set.of()
        );
        Payment largeOneApproval = new Payment(
            102, 1, 10, 120_000_000, Status.PENDING, Set.of(20L)
        );
        Payment largeTwoApprovals = new Payment(
            102, 1, 10, 120_000_000, Status.PENDING, Set.of(20L, 30L)
        );
        Payment draft = new Payment(
            103, 1, 10, 40_000_000, Status.DRAFT, Set.of()
        );

        System.out.println("maker self-approve: "
            + canApprove(maker, small));
        System.out.println("independent reviewer: "
            + canApprove(reviewerA, small));
        System.out.println("reviewer over limit: "
            + canApprove(reviewerA, largeOneApproval));
        System.out.println("second independent reviewer: "
            + canApprove(reviewerB, largeOneApproval));
        System.out.println("cross tenant: "
            + canApprove(otherTenant, small));
        System.out.println("wrong status: "
            + canApprove(reviewerB, draft));
        System.out.println("one approval enough for large: "
            + enoughApprovals(largeOneApproval));
        System.out.println("two approvals enough for large: "
            + enoughApprovals(largeTwoApprovals));
        System.out.println("missing actor: "
            + canApprove(null, small));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SeparationOfDutiesDemo.java
java SeparationOfDutiesDemo
```

Expected output (stdout):

```text
maker self-approve: false
independent reviewer: true
reviewer over limit: false
second independent reviewer: true
cross tenant: false
wrong status: false
one approval enough for large: false
two approvals enough for large: true
missing actor: false
```

Interpretation:

- The creator holds both permissions yet cannot approve their own transaction: **dynamic SoD**, distinct from forbidding simultaneous ownership of two permissions (static SoD).
- Reviewer A can approve the small request, but cannot approve the 120 million request because it exceeds their limit; A is also already in the large request's approval list.
- Reviewer B is in the same tenant, is not the creator, is active, has sufficient limit, and has not approved yet, so B can contribute the second approval.
- Cross-tenant, wrong status, and missing actor are all denied.
- A large request needs two distinct approver IDs. `Set<Long>` illustrates distinct counting; in production ensure approval records **are created through the guard and bound to the current content version**. Never read an arbitrary ID set from an HTTP request and treat it as sufficient approval.

This is intentionally a minimal model. Production implementations must consider management hierarchy, delegates, permission expiration, decision audit trails, step-up authentication, and concurrent changes in the data store.

## 6. Enforcing with Spring Security: Function Permissions and Per-Transaction Rules

The following examples use **Spring Security 6 on Servlet/Spring MVC**, matching common Spring Boot 3.x configuration. These are **application integration snippets** requiring corresponding domain classes, repositories, and authentication; they are not standalone compilable Java programs like section 5.

### 6.1. Guarding Right at HTTP with `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class PaymentSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/api/payments")
                .hasAuthority("payment:create")
            .requestMatchers(HttpMethod.POST, "/api/payments/*/submit")
                .hasAuthority("payment:submit")
            .requestMatchers(HttpMethod.POST, "/api/payments/*/approve")
                .hasAuthority("payment:approve")
            .requestMatchers(HttpMethod.POST, "/api/payments/*/execute")
                .hasAuthority("payment:execute")
            .requestMatchers(HttpMethod.POST, "/api/admin/privileges/grant")
                .hasAuthority("privilege:grant")
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

This configuration declares allowed operation types by authority and denies everything else by default. It **cannot distinguish** an approver from the creator of the same transaction, nor does it know limits or whether two approvals exist. Those conditions must be checked in the business and data layers.

These matchers are only examples of reviewed APIs; real systems must also add valid read/edit endpoints. Default `denyAll()` blocks unlisted endpoints, including read endpoints. Matcher ordering and scopes of any additional `SecurityFilterChain` beans must be checked carefully.

This sample configuration does not configure login, JWT, CORS, or CSRF policies. For cookie/session applications, never disable CSRF out of habit. If using an OAuth2/JWT resource server, verify that scope/claim-to-`GrantedAuthority` mapping matches the strings checked by `hasAuthority(...)`. `hasRole("APPROVER")` in default configuration checks `ROLE_APPROVER`; it is not equivalent to `hasAuthority("payment:approve")` unless mapped explicitly.

### 6.2. Guard in the Service

An approval action must execute inside a real business boundary using trusted server data. Example:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentApprovalService {
    private final PaymentRepository payments;
    private final CurrentActor currentActor;
    private final PaymentPolicy policy;
    private final ApprovalRepository approvals;

    public PaymentApprovalService(
            PaymentRepository payments,
            CurrentActor currentActor,
            PaymentPolicy policy,
            ApprovalRepository approvals) {
        this.payments = payments;
        this.currentActor = currentActor;
        this.policy = policy;
        this.approvals = approvals;
    }

    @Transactional
    @PreAuthorize("hasAuthority('payment:approve')")
    public void approve(long paymentId) {
        var actor = currentActor.requireAuthenticated();
        var payment = payments.findByIdForUpdate(paymentId)
            .orElseThrow(() -> new PaymentNotFoundException(paymentId));

        if (!policy.canApprove(actor, payment)) {
            throw new AccessDeniedException("Approval denied");
        }

        approvals.insertDecision(
            payment.id(),
            payment.version(),
            actor.id(),
            "APPROVE"
        );
        if (policy.hasEnoughApprovals(payment)) {
            payment.markApproved();
        }
    }
}
```

This is **illustrative skeleton code**. `PaymentRepository`, `CurrentActor`, `PaymentPolicy`, `ApprovalRepository`, `PaymentNotFoundException`, and domain methods are application interfaces/classes to implement. `insertDecision` must prevent duplicate writes; `hasEnoughApprovals(payment)` in a real system must **re-read/re-count decisions after writing** within the same version and transaction. If `payment.approvals` was an in-memory collection loaded before insert, reload or update it consistently before counting rather than assuming the JPA entity auto-updated.

When using pessimistic locking with Spring Data JPA, the repository can provide a query like:

```java
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PaymentRepository
        extends JpaRepository<PaymentRequest, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from PaymentRequest p where p.id = :id")
    Optional<PaymentRequest> findByIdForUpdate(@Param("id") Long id);
}
```

Locking a record serializes updates in the same transaction when the database and transaction scope guarantee it; **it does not by itself protect counts if approval decisions live in another table without synchronizing on the same lock**. Combine a unique constraint on `(payment_id, version, approver_id)`, conditional state transitions, proper transactions, and idempotent design. If executing sends funds to an external system, guard against duplicate execution even when requests retry.

Optimistic locking with `@Version` can be used instead, but conflicts must be handled and conditions recomputed; never "blindly retry" in a way that executes an action unintentionally.

### 6.3. Prevent Bypassing Checkpoints

With method security, enable `@EnableMethodSecurity` and remember `@PreAuthorize` typically runs through a Spring AOP proxy. Calls from one method to another on the **same instance** can bypass the proxy (self-invocation). Design sensible public entry points, guard business services, and uphold invariants at the data layer rather than treating annotations as sufficient proof for every flow.

Inventory paths outside REST: message consumers, batch jobs, GraphQL, WebSockets, admin consoles, exports, ops scripts, and service accounts. An internal job should not be trusted by default merely because it skips HTTP filters. Each sensitive entry point must enforce an explicitly designed policy.

In particular, controllers must never accept `createdBy`, `approvedBy`, `tenantId`, or `status` and persist them directly as truth. If the client selects an active tenant, the system must verify the principal belongs to that tenant and has access to the resource.

### 6.4. Controlling the Permission-Granting Path (Static SoD)

To prevent granting two conflicting roles simultaneously, checks must run **at role assignment**, not only when the user calls an API. For example, policy forbids someone with `AUDITOR` from receiving administrative permissions over accounts they audit.

A checking pattern:

```text
grantRole(targetUser, candidateRole):
  1. Verify the requester has permission to grant this role.
  2. Load targetUser's current effective roles/permissions.
  3. Evaluate role hierarchy and conflicting permission groups.
  4. Deny if the new combination violates static SoD.
  5. If the permission is sensitive, require independent approval.
  6. Apply the change in a consistent transaction.
  7. Record audit: who requested, who approved, who was granted, and why.
```

Separating the **elevation requester**, **elevation approver**, and **recipient** may also require dynamic SoD. Never create silent exceptions for `ROLE_ADMIN`; break-glass privileges must be explicitly specified and audited separately.

## 7. Sensitive Actions Need Multi-Layer Controls

SoD is central, but not everything. When impact is high, add layers bound to the **specific action and content**.

### 7.1. Step-Up Authentication and Contextual Confirmation

Logged-in users may need re-authentication or MFA (step-up authentication) before approving large sums, granting admin privileges, or exporting sensitive data. Step-up authentication mitigates session hijacking, yet **does not prove approver independence**.

Approval prompts should display core details such as amount, beneficiary, tenant, creator, and effective scope. Showing only "Do you agree?" without binding the decision to a content version invites post-approval tampering.

### 7.2. Approvals Must Bind to Exact Content and Expiration

A decision record should include:

- Verified approver ID, plus effective permissions/scope at approval time.
- Transaction ID and **approved content version**, or a normalized content fingerprint where appropriate.
- Decision, timestamp, status, and reason (if needed).
- Expiration timestamp, approval type, and step-up authentication level if policy requires it.

If the amount or beneficiary changes after approval, the workflow must return to the appropriate confirmation step. A fingerprint is meaningful only when computed server-side from trusted normalized data and bound to the decision; **never trust client-sent hashes**.

### 7.3. Limits, Rate Restrictions, and Risk Triggers

Escalating controls can depend on amount, data classification, record count, new beneficiary accounts, unusual timing, or privileged actions. However, never use "low risk" to waive mandatory SoD constraints set by business policy.

For instance: below an approved threshold needs one approver distinct from the maker; above the threshold needs two independent approvers; transfers to a new beneficiary may require step-up authentication. Write these rules as testable policies rather than scattering them across controllers.

### 7.4. Privileged Accounts and Emergency Access

Occasionally systems need emergency (break-glass) handling when normal approval paths are unavailable. This is a **governed exception**, not a license to bypass all controls:

- The activator must hold clear authority, state a reason, and document the emergency.
- Privileges have narrow scope, short duration, and automatic expiration; allowed operations are restricted.
- Detailed logging, independent alerts, and post-incident review are mandatory.
- Never use a shared account as a substitute identity for two independent people.
- If policy forbids break-glass for a transaction type, the system must uphold that constraint even during emergencies.

Just-in-time privileges and periodic reviews reduce standing-privilege risk, yet still require controlling who can request and approve those privileges.

## 8. Testing: Proving Both Access Denial and Data Integrity

Testing that a valid transaction succeeds is necessary but insufficient. The most critical SoD cases are operations that look valid at the authority layer yet **must be denied because of relationships between subjects**.

### 8.1. Minimum Test Matrix

| Scenario | Expected | Invariant to Verify |
| --- | --- | --- |
| Creator with `payment:approve` self-approves | Deny | No Approval created |
| Approver != creator, same tenant, within limit | Allow | One decision recorded for exact version |
| Approver from another tenant with authority | Deny | No data leaked or decision recorded |
| Approver exceeds limit | Deny | Status unchanged |
| Approver submits a second time | Deny or idempotent per API contract | No duplicate approvals by same person |
| Two distinct identities approve a large request | Eligible if all rules hold | Exactly two independent records counted |
| Two accounts controlled by one person where policy forbids | Deny / route to review per identity model | Two accounts not treated as two independent people |
| Payment edited after approval round | Old approval invalidated | Cannot execute using stale approval |
| User with revoked permission attempts approval | Deny | No decision created |
| Two concurrent approve requests | Consistent outcome | No bypassed limits or duplicate records |
| Client sends fake `createdBy` | Ignored or denied per contract | Real principal/server data used |
| Secondary endpoint or job calls service directly | Equivalent protection | Cannot bypass via alternate channel |
| Caller lacks `payment:approve` | Deny | Payment/approval unchanged |
| Policy service/DB fails | Never allow automatically | No unauthorized execution occurs |

When two specific approval tiers are required, add tests for "two people at the same tier are still insufficient" and "expired delegate is no longer valid". Every constraint in the business matrix needs at least one passing case and one violating case.

### 8.2. Testing HTTP, Services, and Data

With Spring MVC, `MockMvc` and `spring-security-test` can verify matchers, authorities, authentication, and CSRF. Example **call placed inside a JUnit test class with MockMvc, controller, and proper fixtures**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Illustrative example inside a @Test method:
mockMvc.perform(post("/api/payments/101/approve")
        .with(user("maker")
            .authorities(new SimpleGrantedAuthority("payment:approve")))
        .with(csrf()))
    .andExpect(status().isForbidden());
```

In this illustration, `SimpleGrantedAuthority` is `org.springframework.security.core.authority.SimpleGrantedAuthority`; the test setup must map `maker` to the **actual creator ID** and matching fixture 101. A 403 proves SoD denial only when the request passes CSRF, the route exists, and the service genuinely rejects self-approval.

An HTTP test returning 403 **does not by itself prove** SoD works: 403 can also result from a missing CSRF token or wrong matcher. Tests must verify where denial occurred and inspect post-call state: no approval record, unchanged count, unchanged status and version.

Service tests should invoke real business entry points through the corresponding security configuration. Pure `PaymentPolicy` tests catch logic bugs quickly; real integration tests verify transactions, data constraints, concurrency, and method security. Avoid mocking repositories so heavily that SQL or unique constraint errors never surface.

### 8.3. Testing Concurrency and Recovery

Two approval requests can arrive nearly simultaneously; if both read "no approvals yet" and then write, the system can miscount or create duplicate rows. Test with real transactions and production-like data to guarantee:

- The same principal cannot create two decisions for the same transaction/version.
- Two distinct users are recorded cleanly in proper workflow order.
- Only valid states transition; execution never runs twice on client retries.
- Version changes invalidate approvals tied to older versions.
- When the DB fails, no partial "approved" state allows funds to transfer.

For calls to external systems, a database transaction alone cannot automatically undo a payment-provider transaction. Idempotency keys, outbox/inbox patterns, explicit processing states, and reconciliation may be required so commands are neither sent twice nor lost. This is part of **safe execution of sensitive actions**, not just permission checking.

### 8.4. Distinguishing Error Codes from Authorization Decisions

- **401** is typically used when an API requires authentication and no valid identity is present.
- **403** is typically used when authenticated but lacking permission or violating SoD.
- **404** may be used to avoid disclosing the existence of out-of-scope objects.
- **409** may fit when status/version changed or an approval decision already exists.
- **5xx** indicates a technical failure and must never default to allow when the authorization service fails.

HTTP codes are part of the API contract; what must always be verified is that **no policy-violating action executed**, regardless of response design.

## 9. Operations: Controlling Risk as Permissions and Organizations Evolve

An SoD policy can erode over time when staff switch teams, new roles inherit extra permissions, admins receive emergency access, or approval workflows change. Operations must keep constraints intact.

### 9.1. Permission Lifecycle Management

- **Before granting:** check effective-role conflicts, requester and approver, tenant scope, and permission expiration.
- **During use:** check relationship to the transaction at action time; log creator, approver, and content version.
- **On role/duty transfer:** revoke no-longer-needed permissions; review inherited roles and special privileges.
- **When permissions are revoked:** ensure subsequent decisions observe the updated effective permissions per the system's session/token/cache model. If a still-valid JWT carries old permissions, updating the DB **does not automatically invalidate the old JWT**; use an appropriate strategy such as short-lived tokens, dynamic lookups, or session revocation.
- **Periodic reviews:** reconcile actual roles against conflict rules; detect users holding both maker and checker permissions in forbidden scopes or single users controlling multiple shared accounts.

### 9.2. Audit Logs

An approval or denial event should log at minimum:

| Data | Why Needed |
| --- | --- |
| Timestamp, correlation/request ID | Correlate one transaction across services |
| Principal and business identity | Who acted |
| Tenant, resource, evaluated version | Which object/content was reviewed |
| Action and decision | Proposed, approved, rejected, or executed |
| Standardized denial reason code | Detect SoD violations, wrong tenant, expiration, exceeded limits |
| Policy version and authentication type | Explain the decision at that point in time |
| Execution status | Distinguish "approved" from "funds transferred / data deleted" |

Avoid logging tokens, cookies, secrets, full account numbers, or unnecessary sensitive payloads. Restrict read access and prevent log tampering; investigations fail if subjects under review can delete or alter evidence.

### 9.3. Alerts and Additional Controls

Monitor rates of denied self-approvals, over-limit approval attempts, repeated retries on a transaction, sensitive role changes, unusual new approvers, and emergency-mode frequency. Alerts should distinguish honest user mistakes from dangerous patterns to reduce noise.

SoD does not prevent collusion on its own; add transaction reconciliation, anomaly detection, maker–approver relationship checks, org-hierarchy checks, and data access limits. Depending on regulations, require approvers from a different unit or an independent control team.

### 9.4. Changing Policies Safely

When changing approval thresholds, adding approval tiers, or reorganizing teams:

1. Describe the change as an explicit policy and assess impact on in-flight items.
2. Update grant conditions, effective permissions, object checks, and state transitions.
3. Define whether PENDING items follow old or new rules; if needed, require controlled re-approval.
4. Write tests for exceptions and denial paths; run concurrency tests against a real database.
5. Deploy with monitoring on error codes, alerts, audits, and rollback capability.
6. Re-verify all invariants post-deploy: no self-approval, right tenant, right limits, enough independent people, exact version.

Never hotfix issues by adding `if (isAdmin) allow` outside the policy. Security policies must have clear ownership, rationale, and verification.

## 10. Common Pitfalls and Root-Cause Fixes

| Mistake | Why Dangerous | Root-Cause Fix |
| --- | --- | --- |
| Checking `ROLE_APPROVER` and approving immediately | Roles do not identify who created the record | Check `createdBy != approverId` and all object conditions |
| Static SoD checking only directly assigned roles | Conflicting permissions can come from inherited roles | Check effective permissions and conflict matrices at grant time |
| Counting two clicks as two approvers | One person produces multiple decisions | Enforce unique identity per transaction/version |
| Comparing client-sent names/emails to identify users | Data can change or be spoofed | Use stable internal IDs from principal/server data |
| Forgetting tenant constraints | Users in other orgs with function permission approve | Verify tenant and resource relationships |
| Allowing amount edits after approval without re-approval | Prior approval no longer applies to new content | Bind decisions to version and invalidate on data edits |
| Counting approvals in stale in-memory state | Pre-insert list may omit newly inserted records | Sync state or re-query count inside transaction |
| Relying on `@PreAuthorize` over self-invocation | Call paths bypass the proxy | Place guards on real service entry points and data layer |
| Ignoring concurrent approvals | Duplicate records, exceeded limits, invalid state transitions | Transactions, constraints, locking/versioning, idempotency |
| Treating MFA as a second approver | One person authenticating twice is still one person | Keep strong auth separate from SoD |
| Leaving emergency permissions open forever | Exceptions become permanent bypasses | Narrow scope, expiration, alerts, and review |
| Checking only in the web UI | Other APIs or jobs can still act | Enforce in business/data layers on every path |
| Assuming enough approvals means "safely executed" | External calls can duplicate or drop results | State guards, idempotency, and reconciliation |

## 11. Practice by Level

### Level 1 — Distinguish Static and Dynamic SoD

Draw two matrices: one for role pairs that cannot be co-assigned, and one for steps that cannot be performed by the same person on one transaction. Answer: "Does holding both `payment:create` and `payment:approve` always violate SoD?". **Not necessarily**: static SoD may forbid holding both; dynamic SoD may allow holding both while forbidding self-approval on the same transaction.

### Level 2 — Prove in Java

Run `SeparationOfDutiesDemo.java`. Add a `requiresIndependentDepartment` field and an actor department attribute; add a rule requiring maker and approver to belong to different departments when policy demands it. Create allow and deny cases without breaking existing cases.

### Level 3 — Build an Approval API

Build `POST /api/payments/{id}/approve` with an explicit authority, server-derived principal, tenant/limit/maker checks, and version-bound decision persistence. Test two users with the same authority but different relationships to the transaction. Attempt sending a fake `createdBy` in the body and verify it does not alter the decision.

### Level 4 — Prevent Race Conditions

Send two concurrent requests from the same approver and two requests from two distinct approvers. Prove no duplicate records occur, approver count is exact, and the state machine only makes valid transitions. If calling external systems, add retry and idempotency tests.

### Level 5 — Privileged Access and Operations

Design a request workflow for `privilege:grant`: requester, approver, recipient, scope/duration, and auditing. Describe break-glass mode and at least two alerts to detect. Explain what happens if an approver leaves the company or loses permissions while an item is pending.

## 12. End-of-Lesson Self-Check

1. **Why can a user with `payment:approve` still be denied?** Because of constraints on distinct creator, same tenant, valid status, limit, approval history, and version.
2. **How does static SoD differ from dynamic SoD?** Static SoD forbids configuring conflicting permissions; dynamic SoD forbids combining conflicting actions within a session/workflow/object.
3. **Do two Approve clicks by the same user count as two independent approvals?** No. Distinct identities and independence context must be verified per policy.
4. **Does one person completing MFA twice satisfy four-eyes?** No; MFA authenticates the same person, not a second person.
5. **Can a payment execute if the beneficiary changes after enough approvals?** Prior approvals cannot be reused as-is; the new content must be re-confirmed per policy.
6. **Why are HTTP permission checks insufficient?** HTTP lacks full transaction history, tenant, creator, limit, and state; other entry points also exist.
7. **Does using a transaction alone stop all concurrent approval bugs?** No. Locking or versioning, data constraints, and proper transaction boundaries are also needed.
8. **What must the system do when policy evaluation fails for a sensitive action?** Never allow by default; return an appropriate error and preserve data invariants.

**Remember:** separation of duties controls **who can combine which steps, on which object, and at what time**. When implementing with Spring Security, start from business conflicts, express them as server-verified conditions, place guards on real execution paths, and verify by testing that no one can self-create, self-approve, and self-execute outside policy.