# Choosing the Right Authorization Model and Avoiding Role Explosion

## 1. Scenario: Why Does the Number of Roles Grow Out of Control?

A document management system starts with three roles: **VIEWER**, **EDITOR**, **ADMIN**. After a few months, the business adds "only edit documents in your own department", "cannot approve documents you created", "only export data in your assigned region", "approval permission expires after 7 days", and "administrators only manage their own tenant".

An unsustainable approach is creating a new role for every case:

- `EDITOR_SALES`, `EDITOR_HR`, `EDITOR_FINANCE`.
- `EDITOR_SALES_NORTH`, `EDITOR_SALES_SOUTH`.
- `APPROVER_SALES_PENDING`, `APPROVER_SALES_TEMP_7D`.
- `TENANT_A_ADMIN`, `TENANT_B_ADMIN`, etc.

The role list quickly becomes unmanageable: users accumulate overlapping roles; new features demand more roles; an old role can accidentally grant too much access; no one is sure which roles are genuinely needed.

**Root problem:** roles—meant to describe **relatively stable responsibilities**—are turned into containers for every volatile resource, organizational, relationship, and temporal condition. When those dimensions combine, role variants grow exponentially.

This lesson guides choosing **RBAC**, **ABAC**, **ReBAC**, or a sensible combination based on real needs, keeping the role catalog lean while upholding *least privilege*, object-level checks, and *deny by default*.

### After This Lesson, You Should Be Able To

1. Recognize when RBAC is sufficient and when attributes or relationships are needed.
2. Distinguish role, permission, scope, resource relationship, and policy condition.
3. Design roles around business responsibilities, not individual records or temporary states.
4. Map the model to Spring Security using `GrantedAuthority`, request/method security, and object-level policies.
5. Follow a process to reduce redundant roles, test permissions, and govern policy changes.

## 2. Separate Concepts Properly Before Choosing a Model

| Concept | Meaning | Example | Do Not Confuse With |
| --- | --- | --- | --- |
| **Subject** | Requesting user, service, or actor | User `u42`, service `billing-worker` | Role |
| **Role** | Relatively stable responsibility group or access title | `DOCUMENT_EDITOR`, `PAYMENT_REVIEWER` | Per-owner, time, or single-document conditions |
| **Permission / authority** | Business action the system allows attempting | `document:read`, `document:edit`, `invoice:approve` | Default access across all resources |
| **Resource** | Target record or object | Document `d72`, invoice `i05` | General endpoint or action |
| **Scope** | Boundary where a permission applies | Tenant `alpha`, project `p9`, department `sales` | A permanent piece of the role name |
| **Relationship** | Link between subject and resource | Owner, assigned reviewer, project member | System-wide role |
| **Attribute** | Property of subject/resource/environment | `status=DRAFT`, `region=APAC`, MFA verified | A new role per value change |
| **Policy** | Rules evaluating and combining inputs | Editor + same tenant + owner + draft document | A plain list of roles |

For example, the statement "Alice may edit document `d72` because Alice has the editing capability, is the owner, is in the same tenant, the document is unlocked, and the system is not in read-only mode" spans multiple dimensions:

```text
Subject: Alice
Permission: document:edit
Role (permission source): DOCUMENT_EDITOR
Resource: document d72
Scope: tenant alpha
Relationship: Alice is owner of d72
Resource attribute: d72.status == DRAFT
Environment attribute: system.readOnly == false

ALLOW = sufficient permission
        AND valid scope
        AND matching relationship
        AND matching attributes/context
```

Roles are useful for grouping stable **permissions**. Resource- and context-based policies answer questions that depend on specific data. That is why someone can hold `document:edit` yet still be denied editing document `d73`.

**Never infer permissions from client-declared inputs.** `tenantId`, `ownerId`, `roles`, and `isAdmin` in request bodies/headers are not proof of access rights. The subject must come from a trusted authentication/authorization source; resource info must come from persistence or an authoritative source.

## 3. Access Control Models and When Each Fits

### 3.1. RBAC — Role-Based Access Control

**Idea:** grant permissions to roles, then assign roles to subjects. Users gain access to features via their roles.

```text
Alice --has role--> DOCUMENT_EDITOR
DOCUMENT_EDITOR --grants--> document:read
DOCUMENT_EDITOR --grants--> document:edit
```

**Fits when:** responsibility groups are stable and business permissions are fairly uniform across members of the same role—for instance, support staff can view tickets, accountants can draft vouchers.

**Strengths:** easy to explain, easy to review by function, group-level grant/revocation, minimal runtime condition evaluation.

**Limitations:** `DOCUMENT_EDITOR` alone does not know which document belongs to Alice, which tenant, or whether the document is `DRAFT` or `APPROVED`. Encoding those dimensions into role names causes *role explosion*. RBAC works well as a function-permission layer, yet is insufficient for many per-object decisions.

**When using it:** keep roles few with job-descriptive names; maintain clear `role → permission` mappings; add separate policies for tenant, owner, and state.

### 3.2. ABAC — Attribute-Based Access Control

**Idea:** decisions depend on attributes of the subject, resource, action, and environment/context, for example:

```text
ALLOW edit(document) WHEN
    user.enabled == true
    AND user.department == document.department
    AND document.status == DRAFT
    AND environment.readOnly == false
```

**Fits when:** access depends on document status, data classification, shift schedules, session trust level, region, deadlines, or frequently changing conditions.

**Strengths:** avoids creating roles for every combination; policies mirror business rules.

**Trade-offs:** policies can grow hard to reason about with too many attributes; requires standardizing attribute names, data sources, freshness, decision precedence, and condition-matrix testing. ABAC does not mean "cramming a giant expression into every controller".

### 3.3. ReBAC — Relationship-Based Access Control

**Idea:** relies on **relationships** between subject and resource, either direct or through groups/projects.

```text
Alice --ownerOf--> document d72
Bob   --reviewerOf--> document d72
Carol --memberOf--> project p9
document d72 --belongsTo--> project p9
```

**Fits when:** document sharing, team collaboration, project management, folder trees, ownership, assigned reviewers, group-inherited permissions, or multi-hop relationships.

**Strengths:** expresses "who can do what on which resource" more naturally than minting new roles per document.

**Trade-offs:** requires storing and querying relationships, understanding depth/inheritance and revocation rules; avoid circular queries or stale relationship data. With multi-tenant data, relationships must never cross tenant boundaries unintentionally.

### 3.4. ACL — Per-Object Access Control List

**Idea:** each object stores or references a table showing which users or groups hold which permissions. For example, `d72` has ACL `(alice, EDIT)`, `(team-review, READ)`.

**Fits when:** applications directly share individual files/documents with users or groups, exceptions are bounded, and a "shared with" view is needed.

**Trade-offs:** large ACLs become hard to maintain, inherited/group entries complicate evaluation, and list queries must filter by ACL. Never turn ACLs into system-wide per-document roles.

ACL is a **per-object permission representation**; it pairs naturally with ReBAC (group membership) and RBAC (function permissions).

### 3.5. Combining Multiple Models — Usually the Pragmatic Choice

There is no rule requiring "one model across the entire application". Example:

- **RBAC:** `DOCUMENT_EDITOR` grants `document:edit`.
- **Scope:** the permission applies only within tenants the user belongs to.
- **ReBAC:** the user must be the owner or an assigned member.
- **ABAC:** the document must be `DRAFT`, and the system not `readOnly`.
- **ACL (when needed):** specific users are shared read access to the document.

```text
                    ┌─────────────────────────┐
Request ----------->│ Has function permission?│
                    └────────────┬────────────┘
                                 │ yes
                    ┌────────────▼────────────┐
                    │ Valid tenant/scope?     │
                    └────────────┬────────────┘
                                 │ yes
                    ┌────────────▼────────────┐
                    │ Valid object relation?  │
                    └────────────┬────────────┘
                                 │ yes
                    ┌────────────▼────────────┐
                    │ Attributes/context OK?  │
                    └────────────┬────────────┘
                                 │ yes
                               ALLOW

If any step fails or cannot be verified → DENY.
```

RBAC answers "which features may be used?", ReBAC/ACL answers "on which objects?", and ABAC answers "under which conditions?". This organization is usually far more maintainable than encoding every variant as a role.

## 4. Choosing a Model Using Concrete Criteria

Start by writing the product's **action and resource matrix**. Never pick a policy technology before describing actual permissions.

| Requirement Characteristics | Recommended Approach | Reason |
| --- | --- | --- |
| Few user groups, clear features, few exceptions | Simple RBAC | Easy to govern and explain |
| Many tenants/branches with the same roles in each | **Scoped** RBAC + tenant checks | Avoids multiplying roles per tenant |
| Permissions by owner, assignee, team, parent/child | ReBAC or ACL + RBAC for features | Relationships belong in data, not role names |
| Permissions vary by state, classification, time, MFA | ABAC combined with function permissions | Conditions change frequently |
| Sharing specific users/groups per document | ACL or ReBAC model | Grants bound to specific objects |
| Many features plus rich data constraints | Hybrid RBAC + scope + ReBAC/ABAC | Separates stable permissions from dynamic rules |
| Complex policies shared across many products/services | Shared policy service/engine **only when genuinely needed** | Improves consistency, at the cost of ops, latency, and policy versioning |

Do not jump to a complex policy engine merely because role counts start growing: first check whether you are embedding tenant, state, or owner into role names. Conversely, do not cling to pure RBAC just for simplicity when the business mandates per-object checks.

### Six Questions to Finalize the Design

1. **What is stable?** Stable job responsibilities → roles; volatile states/relationships → policies.
2. **Do permissions apply system-wide or within a scope?** An `ADMIN` role might only be `tenant admin`, not `global admin`.
3. **Who owns the authoritative decision data?** Identity service manages users/roles; business services know object owner, state, and tenant.
4. **How fast must revocation take effect?** Roles/ACLs/relationships may live in caches/JWTs; refresh latency affects security.
5. **Who can explain the outcome?** Reason codes and tests are needed for each policy; hidden conditions complicate auditing.
6. **What is the query scale?** ReBAC/ACLs over millions of objects require properly indexed query/filtering strategies.

## 5. Role Explosion: Recognizing and Fixing the Root Cause

### 5.1. How Role Explosion Happens

Suppose an organization has:

- 4 departments.
- 3 operating regions.
- 3 data sensitivity levels.
- 3 action groups.

Creating one role per **combination** yields `4 × 3 × 3 × 3 = 108` roles before even adding record status, owner, time, or tenant. Each new value dimension multiplies combinations further.

There is no rule that "108 roles is always wrong": some large organizations genuinely have many roles. The red flag is creating distinct roles **solely for a data value**, a tenant, an object, or an expiration timestamp.

### 5.2. Warning Signs

- Roles share nearly identical permissions: `EDITOR_NORTH` and `EDITOR_SOUTH` differ only by region.
- Role names contain document/tenant IDs, dates, `DRAFT/PENDING` states, or individual account names.
- Every exception request spawns a new role; removing old roles risks breaking unknown groups.
- Users carry dozens of roles stitched together; auditors cannot tell which role drove a decision.
- "Temporary" full-access roles exist with no enforced expiration or verified scope.
- APIs scatter role-name string checks across layers instead of checking permissions/policies.
- New roles appear faster than actual organizational job titles/responsibilities.

### 5.3. Separate Dimensions Instead of Multiplying Combinations

**Explosion-prone design:**

```text
ROLE_EDITOR_TENANT_ALPHA_SALES_DRAFT
ROLE_EDITOR_TENANT_ALPHA_HR_DRAFT
ROLE_EDITOR_TENANT_BETA_SALES_DRAFT
ROLE_EDITOR_TENANT_BETA_HR_DRAFT
ROLE_EDITOR_TENANT_ALPHA_SALES_APPROVED
...
```

**Separated design:**

```text
Role: DOCUMENT_EDITOR
  └─ permission: document:edit

Membership/Scope:
  └─ user u42 belongs to tenant alpha, department sales

Resource:
  └─ d72.tenant = alpha
  └─ d72.department = sales
  └─ d72.owner = u42
  └─ d72.status = DRAFT

Policy:
  └─ canEdit = hasPermission("document:edit")
              AND sameTenant
              AND ownerOrAssignedEditor
              AND status == DRAFT
              AND NOT readOnly
```

Roles stay stable when documents change state. When a user switches departments, update only their membership/scope; when a document changes owner or status, the user's roles do not change.

### 5.4. Use Permissions as the Interface Between Roles and Application Code

Avoid scattering checks like `if (role == "SALES_MANAGER_APAC")` across code. Instead, build a permission catalog describing business actions:

| Permission | Meaning |
| --- | --- |
| `document:read` | May request to read documents within authorized scope |
| `document:edit` | May request to edit valid documents |
| `document:approve` | May participate in document approval workflows |
| `document:export` | May export documents within allowed scope |
| `user:invite` | May invite users within administrative scope |

Map roles to permissions in one place with clear ownership. Owner, tenant, status, and MFA conditions should not become separate permissions for every combination.

**A note:** do not create per-ID permissions (`document:d72:edit`) when the need is primarily per-object access. Relationships/ACLs express that better. Only use parameterized permissions when the policy architecture has clear conventions, enforcement, and bounded cardinality.

## 6. Sustainable Authorization Design for Multi-Tenant Documents

Suppose the application has three relatively stable roles:

| Role | Base Permissions | Meaning |
| --- | --- | --- |
| `VIEWER` | `document:read` | May use the view feature |
| `EDITOR` | `document:read`, `document:edit` | May use view/edit features |
| `APPROVER` | `document:read`, `document:approve` | May use view/approve features |

**Note:** the roles in the table only express function permissions. Example object-level policy:

- Same tenant is a foundational condition for every operation.
- `READ`: user is the owner or assigned reviewer.
- `EDIT`: user is the owner, document is `DRAFT`, and the system is not read-only.
- `APPROVE`: user is the assigned reviewer, **not the owner**, document is `PENDING`, session satisfies MFA, and the system is not read-only.
- Missing any required permission or trusted data: `DENY`.

### Verification Examples

| Scenario | Function Permission | Scope / Relation / State | Decision |
| --- | --- | --- | --- |
| Alice (`EDITOR`) edits draft owned by Alice | Passes | Same tenant, owner, `DRAFT` | **ALLOW** |
| Bob (`EDITOR`) edits draft owned by Alice | Passes | Not owner | **DENY** |
| Alice (`VIEWER`) edits draft owned by Alice | Fails | Even though owner | **DENY** |
| Ruth (`APPROVER`) approves assigned `PENDING` doc with MFA | Passes | Same tenant, reviewer, MFA verified | **ALLOW** |
| Ruth approves document still in `DRAFT` | Passes | Wrong state | **DENY** |
| Eve (`EDITOR` in another tenant) attempts edit | Passes action type | Wrong tenant scope | **DENY** |
| Alice edits own draft while system is read-only | Passes | Context forbids writes | **DENY** |

This policy is only a learning example, **not a Spring Security default**. Another product might allow shared users to edit or allow exceptions for project admins. Define rules explicitly and test accurately rather than assuming role names grant full access.

### When One User Belongs to Multiple Tenants

Do not assign `ROLE_ADMIN_TENANT_1`, `ROLE_ADMIN_TENANT_2` per tenant when tenant counts grow. Store roles/permissions as **scoped memberships**:

```text
user_id  tenant_id  role
u42      alpha      EDITOR
u42      beta       VIEWER
u43      alpha      APPROVER
```

When a request arrives for document `d72`, the server verifies the subject's membership in `document.tenantId`, resolves permissions within **that exact tenant**, and then evaluates the object policy. Switching the "selected tenant" in the UI **must never** grant permissions for that tenant on its own. In single-tenant-per-user apps, membership can be simpler; what matters is unambiguous scope.

## 7. Standalone Java 17+: Few Roles While Still Controlling Objects Properly

The following example implements **three roles**, each mapped to stable permissions. Owner/reviewer relationships, tenant, state, and MFA are evaluated separately without creating roles per owner or state.

Create file `AccessModelDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class AccessModelDemo {

    enum Action { READ, EDIT, APPROVE }
    enum State { DRAFT, PENDING, APPROVED }
    enum Decision { ALLOW, DENY_PERMISSION, DENY_SCOPE, DENY_POLICY }

    static final Map<String, Set<String>> ROLE_PERMISSIONS = Map.of(
            "VIEWER", Set.of("document:read"),
            "EDITOR", Set.of("document:read", "document:edit"),
            "APPROVER", Set.of("document:read", "document:approve")
    );

    record Subject(
            String userId,
            String tenantId,
            Set<String> roles,
            boolean active) {
        Subject {
            roles = roles == null ? Set.of() : Set.copyOf(roles);
        }
    }

    record Document(
            String id,
            String tenantId,
            String ownerId,
            String reviewerId,
            State state) {}

    record Context(boolean mfaVerified, boolean readOnly) {}

    static String requiredPermission(Action action) {
        return switch (action) {
            case READ -> "document:read";
            case EDIT -> "document:edit";
            case APPROVE -> "document:approve";
        };
    }

    static boolean hasPermission(Subject subject, String permission) {
        for (String role : subject.roles()) {
            Set<String> grants = ROLE_PERMISSIONS.get(role);
            if (grants != null && grants.contains(permission)) {
                return true;
            }
        }
        return false;
    }

    static Decision authorize(
            Subject subject, Document document, Action action, Context context) {
        if (subject == null || action == null || !subject.active()
                || subject.userId() == null) {
            return Decision.DENY_PERMISSION;
        }
        if (!hasPermission(subject, requiredPermission(action))) {
            return Decision.DENY_PERMISSION;
        }

        if (document == null || subject.tenantId() == null
                || !subject.tenantId().equals(document.tenantId())) {
            return Decision.DENY_SCOPE;
        }

        if (context == null || (context.readOnly() && action != Action.READ)) {
            return Decision.DENY_POLICY;
        }

        boolean owner = subject.userId().equals(document.ownerId());
        boolean reviewer = subject.userId().equals(document.reviewerId());

        boolean allowed = switch (action) {
            case READ -> owner || reviewer;
            case EDIT -> owner && document.state() == State.DRAFT;
            case APPROVE -> reviewer && !owner
                    && document.state() == State.PENDING
                    && context.mfaVerified();
        };

        return allowed ? Decision.ALLOW : Decision.DENY_POLICY;
    }

    public static void main(String[] args) {
        Subject alice = new Subject(
                "alice", "alpha", Set.of("EDITOR"), true);
        Subject bob = new Subject(
                "bob", "alpha", Set.of("APPROVER"), true);
        Subject guest = new Subject(
                "guest", "alpha", Set.of("VIEWER"), true);
        Subject eve = new Subject(
                "eve", "beta", Set.of("EDITOR"), true);

        Document draft = new Document(
                "d1", "alpha", "alice", "bob", State.DRAFT);
        Document pending = new Document(
                "d2", "alpha", "alice", "bob", State.PENDING);
        Document other = new Document(
                "d3", "alpha", "charlie", "bob", State.DRAFT);

        Context normal = new Context(false, false);
        Context mfa = new Context(true, false);
        Context readOnly = new Context(false, true);

        System.out.println("owner-edits-draft="
                + authorize(alice, draft, Action.EDIT, normal));
        System.out.println("editor-edits-other="
                + authorize(alice, other, Action.EDIT, normal));
        System.out.println("owner-edits-readonly="
                + authorize(alice, draft, Action.EDIT, readOnly));
        System.out.println("reviewer-approves-with-mfa="
                + authorize(bob, pending, Action.APPROVE, mfa));
        System.out.println("reviewer-approves-without-mfa="
                + authorize(bob, pending, Action.APPROVE, normal));
        System.out.println("reviewer-approves-draft="
                + authorize(bob, draft, Action.APPROVE, mfa));
        System.out.println("viewer-edits-draft="
                + authorize(guest, draft, Action.EDIT, normal));
        System.out.println("cross-tenant-edit="
                + authorize(eve, draft, Action.EDIT, normal));
        System.out.println("reviewer-reads-assigned="
                + authorize(bob, draft, Action.READ, normal));
        System.out.println("viewer-reads-unshared="
                + authorize(guest, draft, Action.READ, normal));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AccessModelDemo.java
java AccessModelDemo
```

Output:

```text
owner-edits-draft=ALLOW
editor-edits-other=DENY_POLICY
owner-edits-readonly=DENY_POLICY
reviewer-approves-with-mfa=ALLOW
reviewer-approves-without-mfa=DENY_POLICY
reviewer-approves-draft=DENY_POLICY
viewer-edits-draft=DENY_PERMISSION
cross-tenant-edit=DENY_SCOPE
reviewer-reads-assigned=ALLOW
viewer-reads-unshared=DENY_POLICY
```

**Takeaways:**

- Alice and Eve both hold the `EDITOR` role, yet Eve is denied due to a different tenant. No `EDITOR_ALPHA` and `EDITOR_BETA` roles are needed for this example.
- Alice can only edit drafts she owns. When a document changes state, **no new role is needed**.
- Bob holding `APPROVER` must still be the assigned reviewer and satisfy MFA/state rules.
- Guest has `document:read` via role yet cannot read documents not shared with or assigned to them.

`DENY_PERMISSION`, `DENY_SCOPE`, and `DENY_POLICY` are **illustrative codes for learning and auditing**, not built-in Spring Security response codes or classes. Do not expose internal resource/relationship details to unauthorized callers.

The example uses a single `tenantId` on `Subject` to keep the code brief. Multi-tenant products must resolve **per-tenant memberships** from trusted sources as shown in section 6. `Map.of` role mapping is sample data; real systems manage it via controlled configuration or permission stores.

## 8. Integrating with Spring Security by Responsibility Layer

### 8.1. Roles and GrantedAuthority

Spring Security provides `Authentication` and `GrantedAuthority` sets. Depending on how permissions are issued, a role may appear as `ROLE_EDITOR`, while a functional permission appears as `document:edit`.

- `hasRole("EDITOR")` typically checks `ROLE_EDITOR` under the default prefix convention.
- `hasAuthority("document:edit")` checks the exact authority `document:edit`; Spring Security **does not automatically map** business role `EDITOR` to this permission unless configured by the application.

When many features share a permission catalog, one option is resolving roles/scoped memberships during authentication or in a permission service, producing the corresponding authorities. However, identity, membership, and scope can change after a token is issued; data needing fast revocation requires an up-to-date validation strategy.

### 8.2. HTTP Layer: Allow Invoking Only Permitted Features

This is a **Spring MVC/Servlet configuration fragment**, not a standalone Java program. It requires appropriate imports and a `@Configuration` class:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/*")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                .hasAuthority("document:edit")
            .requestMatchers(HttpMethod.POST, "/api/documents/*/approve")
                .hasAuthority("document:approve")
            .anyRequest().denyAll()
    ).build();
}
```

This layer answers "is calling this operation permitted?". It **does not know** `document.ownerId`, `document.tenantId`, or `document.status` without application logic retrieving the resource and evaluating the policy.

For other endpoints such as list, export, delete, batch, or admin, define explicit matchers/features instead of assuming the rules above protect all routes.

### 8.3. Business Layer: Checking Objects, Relationships, and Attributes

Enable method security with `@EnableMethodSecurity`. You can invoke a policy bean with `@PreAuthorize`:

```java
// Illustrative snippet inside a Spring-managed @Service.
@PreAuthorize("hasAuthority('document:edit') and " +
        "@documentPolicy.canEdit(authentication, #documentId)")
public void editDocument(String documentId, EditDocumentCommand command) {
    documentRepository.update(documentId, command);
}
```

The application must define `documentPolicy`, `EditDocumentCommand`, `documentRepository`, and `canEdit`. The policy bean is responsible for receiving the authenticated subject, loading the document from a trusted data store, and verifying tenant/membership, owner/state, and runtime conditions. If multiple objects have different policies, each use case must invoke the policy for its exact action.

**Implementation notes:**

1. `#documentId` in SpEL requires parameter names available at runtime (e.g., compiled with `-parameters` or using parameter-name annotations).
2. Proxy-based method security can be bypassed when one method in a bean directly calls another method on itself (*self-invocation*). Choose clear service boundaries and protect job/consumer paths too, not just controllers.
3. For writes, consider the window between checking and updating the resource. If status, owner, or permissions can change, use transactions, optimistic locking, conditional update predicates, or appropriate locks.
4. Scope queries by tenant and visibility at the data source whenever possible, especially for lists/pagination; never filter late after computing counts or serializing sensitive fields.
5. **Deny by default:** missing authority, missing membership, missing data, or unmatched rules must block access. Never fall back to "logged in means allowed".

### 8.4. When Do You Need a Dedicated Policy Engine?

A small service with a few dozen rules stays clean with Java functions and tests. When many applications share policies and need versioned policies, decision explanations, and cross-service data exchange, consider separating the **Policy Decision Point (PDP)** from the **Policy Enforcement Point (PEP)**:

```text
PEP (controller/service/repository boundary)
  └── sends Subject + Action + Resource + Context to PDP
        └── PDP evaluates versioned policy
              └── ALLOW / DENY (+ internal reason code)
  └── PEP enforces or denies
```

Whether the policy lives in the same JVM or an external service, the **PEP must actually enforce blocking**; a policy call must never be skipped on timeout/error. With an external PDP service, account for latency, availability, integrity of supplied inputs, caching, and failure handling.

## 9. Controlling Roles Without Compromising Security

### 9.1. Least Privilege and Separation of Duties

Permissions should match only the current job; `EDITOR` does not automatically need `document:delete`, `user:invite`, or `document:approve`.

For sensitive workflows, **separation of duties (SoD)** requires that one person cannot complete the entire cycle alone. For example, a record creator cannot approve their own record. Two forms exist:

- **Static SoD:** prevents one user from simultaneously holding two conflicting roles when organizational policy forbids it.
- **Dynamic SoD:** a user may hold multiple capabilities yet cannot approve a transaction they created themselves. This is a resource/relationship condition at execution time, not just a role rule.

Creating a `CREATOR_WHO_CANNOT_APPROVE_OWN` role per document type causes role bloat; the "not the creator" constraint belongs in business policy.

### 9.2. Hierarchy and Role Composition: Use with Control

Role hierarchies allow nested permission sets: e.g., `EDITOR` includes `VIEWER` permissions. This reduces duplication, yet if senior roles inherit everything unchecked, least privilege and SoD quickly break.

Introduce hierarchies only when inclusion relationships are genuinely stable. Avoid treating `ADMIN` as "may bypass owner/tenant/state" unless explicitly approved. Document **role scope** and the meaning of inherited permissions clearly.

### 9.3. Temporary Exceptions and Emergency Access

If an individual needs approval access for 2 days, prefer a **scoped grant + expiration + reason + approver** rather than creating a role named `APPROVER_TEMP_TWO_DAYS_USER42`. Policies must enforce expiration and revocation; audit logs must capture who granted access, when, and within what scope.

Emergency ("break glass") access requires dedicated policies, step-up authentication, and thorough auditing. Never use an unbounded admin role as the default workaround.

### 9.4. Revocation, Caches, and Tokens

If roles/permissions live in long-lived JWTs, removing a role on the server does not immediately strip permissions from still-valid tokens. Likewise, cached policy decisions can keep returning `ALLOW` after a document changes owner.

Decide **revocation latency requirements** per permission upfront. Options include short-lived tokens, fresh membership lookups, invalidation/versioning, appropriate cache TTLs, or execution-time state checks for sensitive actions. This is a risk-based architectural choice; there is no single TTL "safe for every system".

### 9.5. Policy Explainability and Auditing

Maintain traceability for:

- Subject, action, resource ID, tenant/scope, and outcome.
- Which permission allowed or blocked feature usage.
- Which policy rule decided `ALLOW`/`DENY`; policy version.
- Revocations, membership/ACL updates, exception grants, and approvers.

Keep access tokens, unnecessary PII, and document contents out of logs. Client error responses can be `403` or `404` per API contract, while internal reasons should not leak externally by default.

## 10. Process for Reducing Role Explosion in an Existing Project

Replacing legacy roles requires care so valid access is not accidentally revoked nor unauthorized access opened. A structured workflow:

1. **Inventory:** list actual roles, permissions, check sites, usage frequency, and owners. Identify roles differing only by tenant, project, region, owner, state, or duration.
2. **Define business rules:** document actions/resources and who may perform them under what conditions. Build a permission matrix before changing code.
3. **Separate permissions:** group stable actions such as `document:edit`, `document:approve`; keep roles aligned with real responsibilities.
4. **Extract scope/relationships/attributes:** move tenant membership, owner, reviewer, state, and MFA into appropriate policies and data sources.
5. **Audit legacy grants:** review allowed and denied cases; identify where legacy roles over-granted permissions.
6. **Run safe parallel evaluation:** run the new policy in shadow evaluation mode when appropriate to compare decisions without using shadow results to grant access. Avoid logging sensitive data.
7. **Controlled cutover:** update role → permission mappings and enforcement points within clear boundaries; ensure endpoints, services, batches, and background jobs follow the same policy.
8. **Clean up redundant roles:** remove old roles only after accounts are migrated and tests/post-checks pass; monitor unexpected `DENY` rates and audit logs.
9. **Establish long-term governance:** assign an owner for the permission catalog, periodically review unused roles, assign policy owners, and version changes.

**Key judgment:** reducing role count is not an isolated goal. The goal is a **model that is understandable, accurate, and maintainable**. A system with 20 well-designed roles can be better than one forced down to 3 roles where every endpoint carries untestable custom exceptions.

## 11. Testing the Chosen Model

### 11.1. Permission Test Matrix

| Test Case | Function Permission | Scope / Relation / Attributes | Expected |
| --- | --- | --- | --- |
| Editor edits own draft in right tenant | Yes | Passes | `ALLOW` |
| Editor edits someone else's draft | Yes | Not owner | `DENY` |
| Viewer edits own draft | Missing edit permission | Passes owner | `DENY` |
| Editor edits document in another tenant | Yes | Wrong tenant | `DENY` |
| Editor edits approved document | Yes | Wrong state | `DENY` |
| Assigned approver approves `PENDING` with MFA | Yes | Passes | `ALLOW` |
| Assigned approver lacks MFA | Yes | Missing context condition | `DENY` |
| Inactive user / revoked membership | Invalidated | Any | `DENY` |
| Nonexistent / unloadable resource | Possibly | Unverifiable | Deny per API contract |
| Unrecognized role | No | Any | `DENY` |

Beyond policy unit tests, write integration tests for request filters/method interceptors and service execution paths. In particular test list pagination/total counts, batch jobs, mid-request owner/state changes, cache invalidation on revocation, and Spring AOP self-invocation behavior.

### 11.2. Self-Check Questions

1. **The company adds a new tenant; do we need a `EDITOR_NEW_TENANT` role?** Usually no. If editorial duties are unchanged, keep `EDITOR` and enforce tenant membership/scope.
2. **Two users share the `EDITOR` role; one can edit a document while the other is denied. Is that a contradiction?** No. Roles grant feature permissions; per-resource decisions also depend on owner, tenant, state, and context.
3. **Where does "creators cannot approve their own documents" belong?** In the policy evaluating the relationship between subject and document/transaction, alongside separate approval-permission checks.
4. **Is RBAC useless if a project uses ABAC?** No. RBAC can maintain a stable function-permission layer while ABAC handles dynamic conditions.
5. **Should `ALLOW` for `document:edit` be cached forever?** No. Outcomes can depend on document state, relationships, memberships, and revoked permissions.

**Remember:** use **roles** for relatively stable responsibilities, **permissions** for actions, **scope** for boundaries, **relationships/attributes** for per-object conditions, and **policies** to combine them. A well-designed authorization system answers "who can do what on which object, under what conditions, and why" without minting a new role for every scenario.

## References

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- NIST RBAC Project: https://csrc.nist.gov/projects/role-based-access-control
