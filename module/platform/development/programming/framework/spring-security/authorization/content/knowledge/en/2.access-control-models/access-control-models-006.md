# Function-Level vs. Object-Level Authorization

## 1. Lesson Objectives

In a secure system, whether a user **is allowed to invoke a feature** and whether they **are permitted to perform that feature on a specific object** are two distinct questions. Understanding the difference prevents overly broad access grants, especially when APIs accept document, order, account, or record IDs from callers.

After this lesson, you can:

- Distinguish **function-level authorization** from **object-level authorization**.
- Express policies combining both check layers and connect them to roles, action permissions, owners, tenants, and object states.
- Apply both layers to HTTP endpoints and business services in Spring Security.
- Identify, test, and mitigate **Broken Function Level Authorization (BFLA)** and **Broken Object Level Authorization (BOLA)**.
- Handle authorization separately for lists, search, background jobs, and changing resource states.

## 2. Distinguishing the Two Core Questions

**Function-level authorization:** "Does this user have the right to use `APPROVE_DOCUMENT`, `DELETE_USER`, or `EXPORT_REPORT` in the system?"

**Object-level authorization:** "Even if this user can invoke that feature, may they perform it on **document d42**, **user u13**, or **invoice i07**?"

```text
Request: Alice PATCH /documents/d42
                    |
          Is Alice authenticated?
                    |
            Does Alice have
           DOCUMENT_EDIT permission?    <-- function
                    |
           Can Alice edit
           this document d42?    <-- object
                    |
             Are applicable
            conditions still valid?
                    |
               Allow write
```

**Principle:** Allow the operation only when **every mandatory condition** passes. Having general action permission does not automatically permit acting on every record.

We can describe it as:

```text
ALLOW = authenticated(subject)
        AND canInvoke(subject, action)
        AND canAccess(subject, action, resource)
        AND contextAllows(subject, action, resource, context)
```

In real designs, object-level permission and contextual conditions may live in the same policy. Separating them here clarifies each check's responsibility rather than forcing four separate functions in code. If trusted data is missing or no policy permits access, the result must be **DENY**.

### 2.1. Comparison

| Perspective | Function-Level | Object-Level |
| --- | --- | --- |
| Question scope | An action type / use case | A specific object or set of objects |
| Common inputs | Principal, roles, permissions, requested feature | Principal, action, object ID and attributes, relationships, tenant, state |
| Examples | `document:edit`; `invoice:approve`; `user:delete` | Is caller the owner? Same tenant? Assigned reviewer? Invoice still `PENDING`? |
| Enforcement point | Request matcher, service method, application policy | Service/domain policy, conditional data query, custom authorization |
| Typical mistake | Unprivileged user can still call an admin endpoint | User with document read access swaps an ID to read someone else's document |
| Related API vulnerability | **BFLA** | **BOLA**, commonly known as IDOR in many contexts |
| Replaces the other layer? | **No** | **No** |

Example: Bob has `document:edit` as an editor. If Bob sends `PATCH /documents/d42`, checking only `document:edit` would let Bob edit **every** document. The object-level policy must verify that `d42` is within Bob's edit scope; it might require Bob to be the owner, in the same tenant, and the document to be a draft.

### 2.2. These Two Layers Are Not Identical to RBAC and ABAC

**RBAC** (role-based), **ABAC** (attribute-based), and **ReBAC** (relationship-based) describe **how permissions are modeled/decided**, whereas "function-level" and "object-level" describe the **scope of the authorization question**.

- Function-level checks can rely on `GrantedAuthority`, roles, department attributes, or shift schedules—not exclusively RBAC.
- Object-level checks can evaluate owner/collaborator groups (ReBAC), document classification/state/tenant (ABAC), or a user's role **within that specific resource**.
- A single policy can use RBAC, ABAC, and ReBAC together to answer both questions.

For instance, `ROLE_EDITOR` is a subject attribute; `ownerId == currentUserId` is a relationship with the object; `status == DRAFT` is an object attribute. They combine; neither layer automatically replaces the other.

## 3. Consistent Example: Multi-Tenant Document System

Suppose a document API has three features:

| Business Action | Illustrative Endpoint | Function Permission |
| --- | --- | --- |
| Read document | `GET /api/documents/{id}` | `document:read` |
| Edit document | `PATCH /api/documents/{id}` | `document:edit` |
| Approve document | `POST /api/documents/{id}/approve` | `document:approve` |

Define the object-level policy of this **hypothetical system** as follows:

1. **Baseline conditions:** account is active, object exists, and `subject.tenantId == document.tenantId`.
2. **Read (`READ`):** caller is the owner or assigned reviewer of that exact document.
3. **Edit (`EDIT`):** caller is the owner and the document is `DRAFT`.
4. **Approve (`APPROVE`):** caller is the assigned reviewer, is not the owner, and the document is `PENDING`.
5. All cases not matching the policy are denied; additional conditions such as revoked sessions, read-only system mode, or MFA are added when required by the business.

This is only a pedagogical model. In another product, read access might extend to shared users or same-tenant admins; approvals might have multiple levels. What matters is defining rules upfront, enforcing consistently across real paths, and never implicitly granting access just from a general role.

### 3.1. Decision Matrix

Suppose document `d42` belongs to tenant `alpha`, owner is Alice, reviewer is Ruth; `DRAFT` drafts can be edited, `PENDING` documents can be approved.

| Caller | Function Permission | Object/Action | Result | Deciding Layer |
| --- | --- | --- | --- | --- |
| Alice | `document:edit` | Edit Alice's draft `d42` | **ALLOW** | Both layers pass |
| Bob | `document:edit` | Edit Alice's draft `d42` | **DENY** | Has function permission but is not owner |
| Guest | Only `document:read` | Edit `d42` | **DENY** | Lacks edit function permission |
| Ruth | `document:approve` | Approve `d42` in `PENDING` state, Ruth is reviewer | **ALLOW** | Right permission, relationship, and state |
| Alice | `document:approve` | Approve `PENDING` document owned by Alice | **DENY** | Policy forbids self-approval |
| Eve in tenant `beta` | `document:read` | Read `d42` in tenant `alpha` | **DENY** | Wrong tenant scope |
| Ruth | `document:approve` | Approve `d42` while still `DRAFT` | **DENY** | Inappropriate object state |

In the table, **"function permission" only indicates the user may attempt a category of operation**. Permission on `d42` still requires independent evaluation using server-fetched metadata.

### 3.2. Why Client-Supplied IDs Do Not Prove Permission

Two requests:

```http
GET /api/documents/d42
GET /api/documents/d43
```

share the same endpoint, HTTP method, and user, yet can yield different outcomes. Owner, tenant, status, and assignee data must be queried from an authoritative source; **never trust** client-supplied `ownerId`, `tenantId`, or `isAdmin` in body/query/headers. Even an unguessable UUID is not an authorization mechanism. Clients can learn IDs from logs, URLs, notifications, or shared documents themselves.

## 4. Check Flow for an Operation

Suppose Bob tries to edit Alice's document:

1. **Authentication:** Verify session/token. Unauthenticated requests to login-protected resources usually receive `401 Unauthorized`.
2. **Identify function:** The API/use case requires `document:edit`; obtain `Authentication` or a verified subject with permissions. Missing function permission → deny.
3. **Load object:** Look up the document by `id`; trust only server-provided owner, tenant, reviewer, and status. Never let the API construct an "owner" from the request body.
4. **Check object and context:** On the loaded document, verify same tenant, owner relationship, and `DRAFT` status; check session/system-mode conditions if policy requires them.
5. **Execute:** Modify the document only after all checks pass. For authenticated users without permission, typically return `403 Forbidden`; under anti-disclosure designs, some APIs return `404 Not Found` to hide object existence, applied consistently.
6. **Audit:** Record user identifier, resource, action, outcome, and reason code at an appropriate level; avoid logging tokens or unnecessary sensitive data.

For critical state-changing actions, checks and updates must guard against **time-of-check/time-of-use**: a document could move from `DRAFT` to `APPROVED` between read and write. Use transactions, locks, or version/state-conditional updates depending on the system; a single check does not guarantee state remains unchanged.

If function permission fails, you can deny before fetching the object, saving work and avoiding accidental disclosure. Although step ordering may vary by architecture, the operation must always pass all required checks before causing side effects.

## 5. Standalone Java 17+ Example

The pure Java example below distinguishes denials from **missing function permission** versus **missing object permission**. Public APIs need not disclose detailed reasons to callers; reason codes can be written to internal audit logs.

Create file `FunctionObjectAuthorizationDemo.java`:

```java
import java.util.Set;

public class FunctionObjectAuthorizationDemo {

    enum Action { READ, EDIT, APPROVE }
    enum State { DRAFT, PENDING, APPROVED }
    enum Decision { ALLOW, DENY_FUNCTION, DENY_OBJECT }

    record Actor(
            String userId,
            String tenantId,
            Set<String> permissions,
            boolean enabled) {
        Actor {
            permissions = permissions == null
                    ? Set.of() : Set.copyOf(permissions);
        }
    }

    record Document(
            String id,
            String tenantId,
            String ownerId,
            String reviewerId,
            State state) {}

    static Decision authorize(Actor actor, Action action, Document document) {
        // Missing authentication info or valid action -> fail closed.
        if (actor == null || action == null || !actor.enabled()
                || actor.userId() == null) {
            return Decision.DENY_FUNCTION;
        }

        // Step 1: function-level permission.
        String requiredPermission = switch (action) {
            case READ -> "document:read";
            case EDIT -> "document:edit";
            case APPROVE -> "document:approve";
        };
        if (!actor.permissions().contains(requiredPermission)) {
            return Decision.DENY_FUNCTION;
        }

        // Step 2: permission on the specific object.
        if (document == null || actor.tenantId() == null
                || !actor.tenantId().equals(document.tenantId())) {
            return Decision.DENY_OBJECT;
        }

        boolean owner = actor.userId().equals(document.ownerId());
        boolean reviewer = actor.userId().equals(document.reviewerId());

        boolean objectAllowed = switch (action) {
            case READ -> owner || reviewer;
            case EDIT -> owner && document.state() == State.DRAFT;
            case APPROVE -> reviewer && !owner
                    && document.state() == State.PENDING;
        };

        return objectAllowed ? Decision.ALLOW : Decision.DENY_OBJECT;
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "alpha",
                Set.of("document:read", "document:edit", "document:approve"),
                true);
        Actor bob = new Actor("bob", "alpha",
                Set.of("document:read", "document:edit"), true);
        Actor ruth = new Actor("ruth", "alpha",
                Set.of("document:read", "document:approve"), true);
        Actor guest = new Actor("guest", "alpha",
                Set.of("document:read"), true);
        Actor eve = new Actor("eve", "beta",
                Set.of("document:read"), true);

        Document draft = new Document(
                "d42", "alpha", "alice", "ruth", State.DRAFT);
        Document pending = new Document(
                "d43", "alpha", "alice", "ruth", State.PENDING);

        System.out.println("owner-edits-own-draft="
                + authorize(alice, Action.EDIT, draft));
        System.out.println("editor-edits-other-draft="
                + authorize(bob, Action.EDIT, draft));
        System.out.println("viewer-tries-edit="
                + authorize(guest, Action.EDIT, draft));
        System.out.println("reviewer-approves-pending="
                + authorize(ruth, Action.APPROVE, pending));
        System.out.println("owner-approves-own="
                + authorize(alice, Action.APPROVE, pending));
        System.out.println("cross-tenant-read="
                + authorize(eve, Action.READ, draft));
        System.out.println("reviewer-approves-draft="
                + authorize(ruth, Action.APPROVE, draft));
        System.out.println("reviewer-reads-assigned="
                + authorize(ruth, Action.READ, draft));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac FunctionObjectAuthorizationDemo.java
java FunctionObjectAuthorizationDemo
```

Stdout output:

```text
owner-edits-own-draft=ALLOW
editor-edits-other-draft=DENY_OBJECT
viewer-tries-edit=DENY_FUNCTION
reviewer-approves-pending=ALLOW
owner-approves-own=DENY_OBJECT
cross-tenant-read=DENY_OBJECT
reviewer-approves-draft=DENY_OBJECT
reviewer-reads-assigned=ALLOW
```

Analyzing two easily confused results:

- Bob has `document:edit` like Alice, so he **passes** the function check but **fails** the object check because he is not the owner. The system still denies the write.
- Guest is a member of the same tenant but only has `document:read`. Lacking edit function permission, the system denies immediately regardless of ownership or object state.

`DENY_FUNCTION` and `DENY_OBJECT` are separated here to observe the mechanism in the example. They are not default Spring Security HTTP status codes. In real applications, translate them into appropriate denial responses without returning sensitive details about owner/tenant/reviewer.

## 6. Placing Both Check Layers in Spring Security

Spring Security provides `Authentication`, `GrantedAuthority`, request authorization, method security, and policy extension points. **It cannot know who owns a document** unless the application feeds object data into the decision process.

### 6.1. HTTP Gate: Permission to Use a Feature

With Spring MVC/Servlet, `SecurityFilterChain` can guard endpoints via `authorizeHttpRequests`. The snippet below belongs in a `@Configuration` class with required imports; it is a **Spring integration fragment**, not a standalone Java program:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(authorize -> authorize
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

These matchers illustrate **function-level** protection. Matcher selection and endpoint structure must match the real API design; any secured route not matching a rule falls into `denyAll()`. This is not yet a solution for permissions on `/api/documents/d42`.

`hasAuthority("document:edit")` checks the exact authority string granted in `Authentication`. Do not assume every `ROLE_EDITOR` automatically becomes `document:edit`: role → permission mapping must be defined explicitly at the authority source or policy.

### 6.2. Service/Method: The Object Boundary

Enable method security with `@EnableMethodSecurity` on a configuration class. Then check both action and object with `@PreAuthorize`:

```java
// A method in a Spring-managed @Service.
// "documentAccess" is an application-defined policy bean.
@PreAuthorize("hasAuthority('document:edit') and " +
        "@documentAccess.canEdit(authentication, #documentId)")
public void editDocument(String documentId, EditDocumentCommand command) {
    documentRepository.updateDocument(documentId, command);
}
```

Here `documentAccess.canEdit(authentication, documentId)` is a method **the application must write** to: read the subject from `Authentication`; load the exact document; check tenant, owner, status, and context; and return a boolean. `EditDocumentCommand` and `documentRepository` are also illustrative components to implement in the project.

Technical notes:

- In SpEL, `#documentId` must have an accessible parameter name; use compiler configuration that retains parameter names (such as `-parameters`) or annotate parameters using Spring Security's naming mechanism.
- Method security normally runs via a Spring AOP proxy; **self-invocation** (a method in the same bean directly calling an annotated method) can bypass the interceptor. Protect clear public service boundaries and other entry paths.
- If you load the document to authorize and then load it again to write, beware of race conditions. For critical mutating commands, consider a single service transaction that loads/checks/updates the same object with state constraints on write.
- `@PreAuthorize` should be a **consistent gate**, though a single annotation is insufficient if multiple endpoints/jobs/consumers share the business logic.

### 6.3. When Object Logic Needs Rich Data

A clean organization has the service execute sequentially: load authoritative resource → check function permission → check object policy → execute business logic. **Pseudocode** example:

```text
editDocument(actor, documentId, change):
    requireAuthority(actor, "document:edit")
    document = repository.getDocument(documentId)
    requireSameTenant(actor, document)
    requireOwner(actor, document)
    requireState(document, DRAFT)
    repository.updateIfVersionAndStateMatch(document, change)
```

Nonexistent objects are handled separately per contract. Conditions like `requireOwner` and `requireState` are **application rules**, not inferred automatically by Spring Security. Depending on architecture, wrap them in a policy bean, custom `AuthorizationManager`, or domain service; any choice must ensure every path is protected.

## 7. Object-Level Authorization for Lists, Search, and Bulk APIs

For `GET /api/documents`, there is no single `{id}` to check. The safe approach is to **restrict visible records directly in the query**, then paginate, count, and return results.

For example, if the read policy allows only the owner or reviewer in the same tenant:

```sql
SELECT *
FROM documents
WHERE tenant_id = :tenantId
  AND (owner_id = :userId OR reviewer_id = :userId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
```

Before running the query, the API must still check the `document:read` function permission. `:tenantId` and `:userId` must come from the authenticated and verified subject, not arbitrary input. This query only illustrates expressing the policy and does not automatically handle sharing, ACLs, soft-deletes, or field-level permissions if the product enforces those rules.

Easily missed points:

- **Pagination/count:** filtering objects after pagination or returning `totalCount` for the whole tenant skews results and leaks information.
- **Export/report/search:** holding `document:export` still does not permit exporting data outside the authorized resource set.
- **Bulk update/delete:** every ID in the batch must be checked or the command must enforce write conditions upholding the same policy. Clearly define all-or-nothing vs. partial success; never silently skip unauthorized IDs.
- **Indirect access:** file attachments, download URLs, thumbnails, audit views, notifications, caches, and background jobs must enforce the same access scope.
- **Field-level sensitivity:** permission to read a document does not necessarily allow viewing every field of that document. When needed, add a property/field-level authorization layer to control response content.

## 8. BFLA and BOLA: Two Distinct Vulnerability Classes

### 8.1. Broken Function Level Authorization (BFLA)

**Scenario:** a regular user with a valid account can call `DELETE /api/users/u12` or `POST /api/documents/d42/approve`, which are meant for privileged roles. The UI may hide the button while the endpoint fails to check authority.

- **Root causes:** UI-only authorization; missing rules on endpoints/services; misordered or overly broad matchers; checking only `authenticated()` for privileged features.
- **Mitigation:** define an action and authority catalog; enforce on the server; use `denyAll`/deny-by-default; test HTTP methods, legacy routes, internal APIs, and admin functions.

### 8.2. Broken Object Level Authorization (BOLA)

**Scenario:** Alice is allowed to call `GET /api/invoices/{id}` for her own invoice. She swaps `{id}` to Bob's invoice and the server still returns data because it only checked `invoice:read`.

- **Root causes:** the endpoint checks function permission but omits owner, shared relationship, or organizational scope of the **target record**.
- **Mitigation:** enforce per-object checks over subject + action + resource; filter queries appropriately; maintain tenant isolation across layers as needed.

BFLA and BOLA often appear **together**. For example, a "export customer report" endpoint allows any user to call it (BFLA), then reads all customers across tenants (BOLA). Fixing only one layer leaves the other vulnerable.

## 9. Testing Authorization Design Along Both Dimensions

Build a **permission matrix** for every critical business action. Minimum cases:

| Test Case | Function Permission | Object Permission | Expected |
| --- | --- | --- | --- |
| Valid authority, valid owner/tenant/state | Yes | Yes | `ALLOW` |
| Missing authority, is owner | No | Yes | `DENY` |
| Has authority, different owner | Yes | No | `DENY` |
| Has authority, different tenant | Yes | No | `DENY` |
| Has authority, valid owner, wrong state | Yes | No | `DENY` |
| Missing both | No | No | `DENY` |
| Invalid token/session | Unauthenticated | Any | Rejected at authentication |
| Nonexistent resource | Possibly | Unverifiable | Error per API contract, no data leak |
| Same permission, different IDs | Yes | Varies per ID | Each ID receives the right outcome |

Real-world test suites must cover **HTTP/controllers**, **direct service calls**, **lists**, **count queries**, **batches**, and **jobs/message consumers** if those paths exist. For certain actions, test state transitions between check and write to prevent acting on stale state.

Never test solely with a super-privileged admin account: it misses the distinction between lacking function permission and lacking resource permission. Use at least two subjects in the same tenant, one subject in another tenant, two objects with different owners, and multiple states.

## 10. Common Pitfalls

1. **"Logged in is enough":** `authenticated()` only confirms identity; it grants neither feature permissions nor record permissions.
2. **"Having ADMIN role bypasses all limits":** a role may be **tenant admin**, not global admin. Document authority scope explicitly.
3. **"Using random UUIDs means no need to check ownership":** hard-to-guess IDs do not prevent leaks via URLs, caches, logs, or shared links.
4. **"Hiding the button protects the feature":** the client is not a trust boundary; enforce on the server.
5. **"Checking only in the controller":** internal methods, consumers, and jobs can bypass controllers.
6. **"Filtering after fetching the list is enough":** count, pagination, cache, and serialization may already leak data.
7. **"Checking only when the task starts":** the object may transition state, change owner, or have permissions revoked before write.
8. **"Trusting whichever tenant the client claims":** unverified claims/bodies/headers cannot be trusted; enforce cross-tenant boundaries server-side.
9. **"Returning 403 for everything is enough":** design 401, 403, and 404 handling carefully and limit details in errors/audits so existence or object attributes are not leaked.
10. **"Adding one `@PreAuthorize` finishes everything":** you still need proper parameters, policy bean, proxy invocation, transactions, and coverage across all entry points.

## 11. Self-Check Questions

**Question 1.** Bob has `document:edit` but does not own `d42`. Can he edit it?

**No.** Bob passes the function check but fails the object check (under the example policy in section 3).

**Question 2.** Alice owns `d42` but lacks `document:approve`. Can she approve it if the document is `PENDING`?

**No.** Object/ownership rights do not replace function-level permission. Moreover, the example policy forbids owners from approving their own documents even if granted the authority.

**Question 3.** The `GET /api/documents` API has `hasAuthority('document:read')`. Is that enough to return all documents?

**No.** You must still restrict records by tenant, owner/reviewer relationship, or actual sharing policy. Pagination, count, and export must follow the same authorized scope.

**Question 4.** Does an `ALLOW` result for document `d42` apply by default to `d43`?

**No.** An object-level decision applies to one specific resource, action, and context; attributes of two objects may differ.

**Remember:** *being allowed to use a feature* and *being allowed to use that feature on a specific record* are complementary requirements. Ensure both are enforced on the server before reading sensitive data or mutating state.

## References

- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- OWASP API Security Top 10 (2023), API1 Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API Security Top 10 (2023), API5 Broken Function Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
