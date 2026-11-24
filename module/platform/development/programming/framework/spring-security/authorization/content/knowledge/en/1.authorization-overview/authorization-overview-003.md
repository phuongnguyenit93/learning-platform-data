# Subject, Resource, Action, and Context of an Authorization Decision

## 1. Objectives and Core Idea

After this lesson, you will be able to identify the four inputs to an authorization decision; distinguish an authenticated identity from permissions on a specific object; write policies that account for owner, tenant, business status, and context; and place checks in the right location in a Spring Security application.

**Authentication** answers: "Who is making the request?" **Authorization** answers: "Is this subject allowed to perform that action on that resource, under the current circumstances?" Logging in successfully does not mean being allowed to read or modify all data.

A check can be modeled as follows:

```text
Decision = authorize(Subject, Resource, Action, Context, Policy)

Subject  = who is requesting?
Resource = which object is affected?
Action   = what business operation?
Context  = which conditions apply?
Policy   = which rules decide ALLOW or DENY?
```

`Policy` is the set of rules used to evaluate the four inputs, not an input self-declared by the client. The final decision must be **enforced** before returning data or performing side effects. When trusted information is missing or no rule grants access, apply **deny by default**.

## 2. Four Components to Distinguish

| Component | Question to Answer | Example in a Document System | Trusted Source |
| --- | --- | --- | --- |
| **Subject (S)** | Who is making the request and what attributes/permissions does the subject have? | User `u17`, tenant `acme`, role `EDITOR`, active account | Verified `Authentication`; membership/permission data from the identity management system |
| **Resource (R)** | Which exact record, object, or data scope? | Document `doc-42`, belongs to tenant `acme`, owner `u17`, state `DRAFT` | Record/metadata loaded server-side from an authoritative data source |
| **Action (A)** | What exact operation is being proposed? | `READ`, `EDIT`, `DELETE`, `APPROVE`, `EXPORT` | API/use case/service that defines the operation and business semantics |
| **Context (C)** | What additional conditions hold at decision time? | MFA recently verified, read-only mode, time, session state, current organization | Server-verified signals; session/authentication; system and policy state |

### 2.1. Subject is not just a username

A `Subject` can be a user, service account, or machine actor. Depending on business needs, useful attributes include:

- Stable identity (`subjectId`), lock/disabled status, and session info.
- `GrantedAuthority`/roles such as `ROLE_ADMIN`, `document:read`; roles are **one piece of information about the subject**, not enough to conclude permissions on individual records.
- Tenant, group, department membership, delegation scope. If attributes are dynamic, fetch them from a sufficiently fresh source rather than assuming every old claim remains valid.

In Spring Security, `Authentication` typically carries the principal and `GrantedAuthority` instances. Additional authorization data may need to be looked up in the application. Do not trust `userId`, `roles`, or `tenantId` self-sent by the caller in the body/query/header; a claim can only be used as a trusted input when the token has been verified and the claim's semantics are accepted by the system.

### 2.2. Resource is the real object, not just an ID

`/api/documents/doc-42` only provides the identifier of the requested object. The server must look up the data to know who `doc-42` belongs to, which tenant it is in, and whether it has been locked/approved. Even a hard-to-guess UUID **does not replace** an authorization check.

A resource can be a DB row, file, transaction, data field, or result set. For lists, authorization also determines **which records appear**; you should not load all data and accidentally return out-of-scope objects.

### 2.3. Action must have clear business meaning

`GET` usually suggests a read action, but HTTP methods do not always fully describe business semantics. A `POST /documents/{id}/approve` is `APPROVE`, distinct from `EDIT`; an `EXPORT` action can be more sensitive than `READ`. You must check the right permission for the operation actually taking place, including batch APIs, message consumers, or internal jobs that do not go through an HTTP controller.

### 2.4. Context can change even when S, R, and A remain the same

Someone may have permission to edit a draft this morning yet be blocked from editing when the system enters read-only mode. Delete permission may require MFA; an approve command may only be valid within a time window or while the document is `PENDING`. Context must be determined at decision time and bound to the current request.

Clearly distinguish **security context** (e.g., MFA completed) from **business context** (e.g., accounting period closed). Do not rely solely on client-declared IP or headers to prove security conditions. Tenant can also be viewed as a subject/resource attribute or part of context; the essential requirement is consistent comparison from trusted sources.

## 3. From Four Components to a Decision

Example rules in a multi-tenant document management system:

1. Only active accounts are evaluated for access.
2. Subject and document must be in the **same tenant**.
3. `READ`: the owner **or** someone with the `AUDITOR` role in the tenant.
4. `EDIT`: the owner with the `EDITOR` role, document in `DRAFT` state, and the system not in read-only mode.
5. `DELETE`: someone with the `ADMIN` role in the tenant, document in `DRAFT` state, session passed MFA, and the system not in read-only mode.
6. All other cases: `DENY`. There is no "system-wide `ADMIN` bypassing tenant boundaries" in this example policy.

Compactly written:

```text
allow(S, R, A, C) =
    S.active
    AND sameTenant(S, R)
    AND NOT (C.readOnly AND A != READ)
    AND (
         (A == READ   AND (isOwner(S, R) OR hasRole(S, AUDITOR)))
      OR (A == EDIT   AND isOwner(S, R) AND hasRole(S, EDITOR) AND R.state == DRAFT)
      OR (A == DELETE AND hasRole(S, ADMIN) AND R.state == DRAFT AND C.mfaPassed)
    )
```

This is an **example policy for learning how to reason**, not a Spring Security default or a rule applicable to every product. In practice, approval permissions, sharing, data classification, legal rules, and organizational constraints can make the expression more complex.

### Scenario table

| Subject | Resource | Action | Context | Decision / Reason |
| --- | --- | --- | --- | --- |
| `u17`, `EDITOR`, tenant `acme` | Draft owned by `u17`, tenant `acme` | `READ` | Normal | **ALLOW** — same tenant, is owner |
| `u17`, `EDITOR`, tenant `acme` | Same draft | `EDIT` | Normal | **ALLOW** — owner + EDITOR + DRAFT |
| `u88`, `AUDITOR`, tenant `other` | Draft in tenant `acme` | `READ` | Normal | **DENY** — different tenant despite having role |
| `u17`, `EDITOR`, tenant `acme` | `APPROVED` document owned by `u17` | `EDIT` | Normal | **DENY** — state does not allow editing |
| `u21`, `ADMIN`, tenant `acme` | Draft in tenant `acme` | `DELETE` | MFA not passed | **DENY** — missing context condition |
| `u21`, `ADMIN`, tenant `acme` | Same draft | `DELETE` | MFA passed | **ALLOW** — satisfies all conditions |
| `u17`, `EDITOR`, tenant `acme` | Draft owned by `u17` | `EDIT` | System read-only | **DENY** — context blocks write operations |

The same person may be allowed `READ` yet denied `EDIT`; the same action may be allowed on their own document and denied on someone else's; the same S–R–A may change outcome when C changes.

## 4. Evaluation and Enforcement Flow in a Request

For `GET /api/documents/doc-42`:

1. **Authentication:** the server verifies the session or token and builds `Authentication`; if there is no valid identity and the endpoint requires login, the result is usually HTTP `401 Unauthorized`.
2. **Determine action:** the endpoint/use case confirms that `READ` is being requested.
3. **Load resource:** look up `doc-42` along with its owner, tenant, state, and required attributes. Never infer permission from a caller-supplied ID or tenant.
4. **Gather context:** e.g., current tenant membership, session/MFA, maintenance mode, or time constraints.
5. **Evaluate policy:** the authorization function checks all of S–R–A–C and produces `ALLOW` or `DENY` (optionally with a reason code for auditing).
6. **Enforce decision:** deny before exposing data or mutating state, or run business logic only when allowed. For an authenticated caller lacking permission, usually return `403 Forbidden`; sometimes an API intentionally returns `404 Not Found` to avoid disclosing an object's existence, following a consistent design.
7. **Audit appropriately:** record subject ID, resource ID, action, outcome, and reason code; avoid logging sensitive data, access tokens, and document contents.

```text
Request → Authentication → identify Action/Resource
                               ↓
                    load data and Context
                               ↓
                       Policy(S,R,A,C)
                        ┌──────┴──────┐
                      ALLOW          DENY
                        ↓              ↓
                     Execute     Block request
```

When querying lists, push tenant/permission filters into the data query (or filter safely before responding). If a business operation changes critical state between the check step and the write step, execute it with an appropriate transaction, conditional update, or lock to avoid **time of check vs. time of use** bugs.

## 5. Standalone Java 17+ Example

The example below implements the policy from section 3 in plain Java. `record` types hold input attributes; `Decision` represents the outcome. It separates decision-making from HTTP/framework code for easy unit testing.

Create the file `AuthorizationDecisionDemo.java`:

```java
import java.util.Set;

public class AuthorizationDecisionDemo {
    enum Action { READ, EDIT, DELETE }
    enum State { DRAFT, APPROVED }
    enum Decision { ALLOW, DENY }

    record Subject(
            String userId, String tenantId, Set<String> roles, boolean enabled) {
        Subject {
            roles = Set.copyOf(roles);
        }
    }

    record Document(
            String id, String tenantId, String ownerId, State state) {}

    record Context(boolean mfaPassed, boolean readOnly) {}

    static Decision decide(
            Subject subject, Document resource, Action action, Context context) {
        if (subject == null || resource == null
                || action == null || context == null) {
            return Decision.DENY;
        }
        if (!subject.enabled()
                || subject.tenantId() == null
                || resource.tenantId() == null
                || !subject.tenantId().equals(resource.tenantId())) {
            return Decision.DENY;
        }
        if (context.readOnly() && action != Action.READ) {
            return Decision.DENY;
        }

        boolean owner = subject.userId() != null
                && subject.userId().equals(resource.ownerId());

        return switch (action) {
            case READ -> (owner || subject.roles().contains("AUDITOR"))
                    ? Decision.ALLOW : Decision.DENY;
            case EDIT -> (owner
                    && subject.roles().contains("EDITOR")
                    && resource.state() == State.DRAFT)
                    ? Decision.ALLOW : Decision.DENY;
            case DELETE -> (subject.roles().contains("ADMIN")
                    && resource.state() == State.DRAFT
                    && context.mfaPassed())
                    ? Decision.ALLOW : Decision.DENY;
        };
    }

    public static void main(String[] args) {
        Subject alice = new Subject("u17", "acme", Set.of("EDITOR"), true);
        Subject bob = new Subject("u88", "other", Set.of("AUDITOR"), true);
        Subject admin = new Subject("u21", "acme", Set.of("ADMIN"), true);
        Document draft = new Document("doc-42", "acme", "u17", State.DRAFT);
        Document approved = new Document("doc-43", "acme", "u17", State.APPROVED);
        Context normal = new Context(false, false);
        Context withMfa = new Context(true, false);
        Context readOnly = new Context(false, true);

        System.out.println("owner-read="
                + decide(alice, draft, Action.READ, normal));
        System.out.println("owner-edit-draft="
                + decide(alice, draft, Action.EDIT, normal));
        System.out.println("other-tenant-read="
                + decide(bob, draft, Action.READ, normal));
        System.out.println("edit-approved="
                + decide(alice, approved, Action.EDIT, normal));
        System.out.println("delete-without-mfa="
                + decide(admin, draft, Action.DELETE, normal));
        System.out.println("delete-with-mfa="
                + decide(admin, draft, Action.DELETE, withMfa));
        System.out.println("edit-during-read-only="
                + decide(alice, draft, Action.EDIT, readOnly));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
```

Exact output:

```text
owner-read=ALLOW
owner-edit-draft=ALLOW
other-tenant-read=DENY
edit-approved=DENY
delete-without-mfa=DENY
delete-with-mfa=ALLOW
edit-during-read-only=DENY
```

Explanation:

- Alice's `EDITOR` role alone does not grant permission to edit every document; ownership, matching tenant, and `DRAFT` state are required.
- Bob has `AUDITOR` but is denied before checking read permission because of the different tenant.
- An admin can only delete a draft in the same tenant when `mfaPassed` is `true`.
- `readOnly` does not change subject/resource/action, yet turns the `EDIT` result into `DENY`.

In a real product, `Subject`/`Context` must be constructed from trusted server data, `Document` must come from persistence, and policies may need field-level permissions, data locks, delegation expiration, or additional business conditions.

## 6. Connecting to Spring Security

Spring Security helps **intercept calls** and provide `Authentication`/authorities; the application is responsible for modeling data and authorization rules per resource.

### 6.1. Request-level authorization: HTTP entry gate

In a Servlet application, `SecurityFilterChain` and `authorizeHttpRequests` typically protect endpoints at the request layer. Example method inside a `@Configuration` class with the proper imports:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(registry -> registry
            .requestMatchers("/api/documents/**").authenticated()
            .anyRequest().denyAll()
    ).build();
}
```

The snippet above requires callers to log in before reaching document paths. It **does not check** whether `doc-42` belongs to the appropriate tenant/owner or whether its state allows editing/deletion. Object-specific conditions need to be checked in the use case/service or a custom `AuthorizationManager` with sufficient data.

### 6.2. Method-level authorization: close to business logic and objects

Enable method security with `@EnableMethodSecurity` on a Spring configuration class. You can use `@PreAuthorize` to invoke a policy evaluation bean:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}

// Illustrative snippet inside a Spring-managed service:
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
```

This is an **illustrative integration snippet, not a standalone Java program**: `Document`, `documentRepository`, and the `documentPolicy` bean are application components you must define yourself. The `documentPolicy.canRead(...)` bean needs to resolve the subject from `Authentication`, load the resource by `documentId`, determine trusted context, and evaluate the `READ` policy; never assume `isAuthenticated()` or `hasRole('USER')` implies permission to read any document.

Operations like `EDIT`, `DELETE`, and `APPROVE` must each have their own corresponding check. When authorization requires state synchronized with data writes, design transactions/conditional updates in the service or repository. Method security relies on Spring AOP/proxies: direct internal calls within the same bean may bypass the interceptor; place the authorization gate at the actual business boundary being called and protect alternative entry paths.

### 6.3. AuthorizationManager and policy models

In modern Spring Security architecture, `AuthorizationManager` handles decisions for requests/methods or wherever integrated. `GrantedAuthority` describes permissions attached to a subject; `hasRole`/`hasAuthority` matching is the simple case. For conditions depending on resource and context, the application must provide the appropriate data lookup and evaluation logic.

- **RBAC (role-based):** "`ADMIN` has delete permission" — easy to use, though roles alone are often too coarse.
- **ABAC (attribute-based):** "`EDITOR` may only edit `DRAFT` documents in the same tenant when not in read-only mode" — considers attributes of S, R, and C.
- **ReBAC/relationship:** "the requesting user is the owner/collaborator of the document" — considers the relationship between S and R.
- **Combined:** `sameTenant && (isOwner || canAudit)` or `role && state && mfa`. These policy styles complement one another; you do not have to pick only one.

## 7. Common Mistakes and How to Self-Check

| Mistake | Why It Is Dangerous | How to Fix It |
| --- | --- | --- |
| "Logged in, so can read any `/documents/{id}`" | Swapping IDs accesses someone else's document: **Broken Object Level Authorization (BOLA)** | Check permissions on **every requested object** |
| Checking only role, forgetting tenant/owner/state | Overly broad access, cross-tenant data leaks, or editing locked documents | Combine all four inputs per business policy |
| Trusting `ownerId`, `tenantId`, `isAdmin` from body/header | Clients can forge decision attributes | Obtain subject and resource/context from verified sources |
| Using `GET/POST` as a substitute for `READ/APPROVE` | Fails to protect the right business operation | Name actions explicitly and check at each use case |
| Querying a list first, returning all or paginating incorrectly before filtering | Data leaks, wrong total counts and pages for the user's permissions | Constrain query scope by tenant/permissions at the source |
| Checking before critical state changes, then writing based on stale state | Race conditions / changes after the check | Use appropriate transactions and conditional writes |
| Allowing when data is missing or no rule is found | Creates a bypass path | **Fail closed**: insufficient info → deny |
| Checking only in the controller/UI | Jobs, messages, or other endpoints can bypass it | Anchor checks at the service/use-case boundary and necessary data access points |

A minimal test suite should cover: same tenant/different tenant; owner/non-owner; with/without role; `DRAFT`/`APPROVED` state; with/without MFA; read-only mode; disabled account; nonexistent resource; requests via direct API, batch API, and internal call paths. Test **denied cases too**, avoiding happy-path-only testing.

## 8. Self-Check Questions

1. Alice has the `EDITOR` role and is in the same tenant as the document, but the document is owned by Bob. Is Alice allowed `EDIT` under section 3's policy? **No**: the owner relationship is missing.
2. Someone with `ADMIN` in a different tenant who has passed MFA—can they delete a draft? **No**: wrong tenant; the foundational condition already failed.
3. Same Alice, same draft document, same `EDIT`; why is it `ALLOW` normally yet `DENY` when read-only mode is enabled? **Context changed** even though subject, resource, and action stayed the same.
4. Why is `.requestMatchers("/api/documents/**").authenticated()` not enough? Because it checks access to the HTTP route without verifying **permissions on each individual resource** associated with an ID.

**Remember:** every meaningful authorization check must fully answer **who → on what → doing what → under what conditions**. Policy complexity depends on business requirements, but missing a necessary dimension can turn an authenticated endpoint into an access control vulnerability.

## References

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- OWASP API Security Top 10 (2023) — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
