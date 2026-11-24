# Principles of Least Privilege, Deny by Default, and Complete Mediation

## 1. The Big Picture: Why Do We Need Three Principles?

**Authentication** answers "Who are you?". **Authorization** answers "Given your current identity and context, which actions are you allowed to perform on which resources?". A logged-in user may still be forbidden from viewing a colleague's documents, editing a locked invoice, or reading another company's data.

An authorization decision typically must evaluate all five elements:

| Element | Question to Answer | Example |
| --- | --- | --- |
| Subject (principal) | Who is performing the action? | User 42, internal service A |
| Action | What do they want to do? | Read, create, edit, approve, delete |
| Resource | Which object is being acted upon? | Document 123, order 99 |
| Context | What are the current conditions? | Tenant, owner, record status |
| Policy | Under what conditions is it allowed? | Has read permission **and** belongs to the same tenant **and** has access to the document |

You can think of a decision as `allow = policy(principal, action, resource, context)`. Without sufficient information to prove access is allowed, deny it. Do not equate "logged in", "holds an admin role in part of the system", or "knows the object's ID" with "is authorized to access it".

The three principles work together:

1. **Least privilege:** each subject is granted only the permissions genuinely needed for its tasks, within the necessary scope and duration.
2. **Deny by default:** any action not explicitly allowed by policy is denied.
3. **Complete mediation:** every path that can reach a protected operation must pass an appropriate authorization check at the time of the operation.

The first principle narrows granted permissions; the second prevents accidental permissions from missing configuration; the third stops attackers from bypassing checks. All three must be enforced on the server side.

## 2. Least Privilege: Granting for the Right Task, Object, and Scope

### 2.1. From business needs to enforceable permissions

Suppose an application manages documents with three task groups:

| Business Role | View Documents in Assigned Scope | Create/Edit in Assigned Scope | Approve | User Administration |
| --- | :---: | :---: | :---: | :---: |
| Viewer | Yes | No | No | No |
| Editor | Yes | Yes | No | No |
| Approver | Yes | By specific task | Yes | No |
| Identity Admin | Only if additionally granted | Not by default | Not by default | Yes |

This is an **illustrative matrix**, not yet enough for real-world enforcement. "Permission to view" must still be bound to a specific set of documents: one's own, same organization, shared, or belonging to an assigned project. Functional permissions like `document:read` are only a necessary condition; data scope is another condition.

A controllable design:

- Split permissions by action, such as `document:read`, `document:create`, `document:update`, `document:approve`, `user:manage`. Never use a single "all-powerful" permission for every task.
- Attach scope: tenant, project, owner, shared groups, and object state.
- Grant permissions through managed roles or policies; have revocation processes when users change positions, leave the organization, or reach delegation expiration.
- For service accounts, grant only the necessary API scopes, resources, and lifetimes; do not use a shared admin key for tasks needing only read access.
- Separate sensitive duties when needed: the requester is not automatically the approver; privileged actions require an audit trail.

**Bad example:** a customer support account is given `ROLE_ADMIN` just to look up ticket status. If the account is compromised, an attacker can abuse many completely unrelated features.

**Better example:** the account has `ticket:read` and can only view tickets assigned to the support team; permissions to export all data or modify users are managed separately.

### 2.2. Roles, authorities, and object permissions are not the same

In Spring Security, an `Authentication` object can hold `GrantedAuthority` instances. `hasAuthority("document:read")` matches that exact authority. `hasRole("ADMIN")` under standard configuration checks an authority prefixed with `ROLE_`, namely `ROLE_ADMIN`; do not confuse the two forms.

Roles group permissions by job function; authorities/permissions express specific capabilities; attribute/object policies (such as owner/tenant) determine whether that permission applies to the requested resource. A role name does not automatically verify document ownership.

Both **functional-level** permission and **data-level** permission must be satisfied:

```text
Allow reading document 123
    = has authority document:read
      AND document 123 belongs to an allowed tenant
      AND user has permission on document 123
      AND document state permits reading
```

If the application permits sharing or exceptions, express them as testable policy branches. Do not scatter "if admin, skip all checks" conditions across multiple places.

## 3. Deny by Default: Open Only What Was Explicitly Decided

### 3.1. Allowlist policies

In an API, secure configuration starts by explicitly listing public routes/calls and the operations with corresponding permissions, then denying the rest. For example:

- `GET /health/public`: public because it returns only approved harmless status.
- `GET /api/documents/{id}`: requires `document:read` and a permission check on document `id`.
- `POST /api/documents`: requires `document:create` and checks tenant and input attributes.
- New endpoints, unconsidered HTTP methods, or undeclared admin paths: denied until an explicit rule is added.

Deny by default reduces the chance that a new endpoint becomes "accidentally public" when a developer forgets to add a rule. **Requiring login (`authenticated()`) is not a business permission:** it allows every logged-in user, whereas a task may be meant for only a small group.

Distinguish clearly:

| Situation | Policy Outcome |
| --- | --- |
| Explicit allow rule exists and all conditions hold | Allow |
| Matches no allow rule | Deny |
| Has functional permission but wrong tenant/owner | Deny |
| Missing data required to determine permission | Fail closed (deny safely) |
| Dependent authorization system unavailable | Do not assume allow; handle error safely |

"Fail closed" does not mean every technical error must return HTTP 403. An infrastructure error may require a 5xx status, yet **must not let a sensitive action proceed** without verifying permissions.

### 3.2. What should not be misunderstood?

- `permitAll()` is not a bug when used on resources **confirmed** to be public; the problem is broadening it excessively, such as `/api/**`.
- `anyRequest().authenticated()` can fit an application where every logged-in user is allowed to access all remaining endpoints; it cannot replace fine-grained permission checks for role-based business operations.
- Some systems have overlapping deny/allow exceptions. You must define clear precedence rather than randomly assuming "the last rule wins".
- Nonexistent resources and unauthorized resources sometimes both return 404 to avoid disclosing existence. Choosing 403 or 404 is a design decision; **the allow/deny decision must be right before choosing the status code**.

## 4. Complete Mediation: Blocking Bypass Paths

### 4.1. "Every access" means every entry point and every object

Checking permissions once at login only proves identity at that moment. During a session, a user may change permission groups, a document may change owner, a request may target another tenant, or an object may be locked. Therefore, relevant conditions must be re-evaluated on every operation.

Commonly overlooked paths:

| Path | Required Check |
| --- | --- |
| HTTP GET/POST/PATCH/DELETE | Permission by action and resource |
| Reading `/api/documents/123` then changing ID to 124 | Permission on object 124 itself (preventing IDOR/BOLA) |
| CSV export, file download, images/attachments, bulk download | Permission on every piece of exported data |
| GraphQL resolvers or WebSocket messages | Policy at the actual access point |
| Background jobs, event consumers, queues, internal commands | Execution identity and corresponding permissions; never assume "internal is trusted" |
| Service method called from another controller | Check at service boundary or data query, avoiding reliance solely on URLs |

**Example:** the UI hides the "Delete" button for regular users, yet they can still send `DELETE /api/documents/123` directly via HTTP. Hiding buttons is UX improvement, not an authorization mechanism.

**Example:** a list endpoint displays only tenant A's documents, while the detail endpoint uses `findById(id)`. A tenant A account can guess tenant B's IDs; the detail endpoint itself must enforce tenant and object permissions.

### 4.2. Checking close to where data is used

One way to reduce bugs is to push protective conditions into the query:

```text
Insufficient:
  SELECT ... FROM documents WHERE id = :id

Required (when the permission model is owner within tenant):
  SELECT ... FROM documents
  WHERE id = :id AND tenant_id = :tenantId AND owner_id = :userId
```

Real models may allow shared users or other roles. In that case, queries/policies must express all allowed branches accurately and reject out-of-scope access. Fetching a resource first and "filtering in the UI" is too late.

For **write** operations, ensure permissions and state conditions remain valid when the write occurs, especially under concurrent updates. Depending on the data, use transactions, locks, version checks, or conditional UPDATE statements; checking first and writing unconditionally creates a time-of-check to time-of-use (TOCTOU) gap. A transaction alone does not guarantee eliminating every race condition unless an appropriate isolation/locking mechanism is chosen.

### 4.3. Which layers should hold checks?

1. **HTTP layer:** filter unauthenticated traffic, public endpoints, and coarse-grained permissions by method/path.
2. **Service method layer:** block sensitive business actions, even when invoked from multiple controllers.
3. **Data access / object policy layer:** enforce tenant, owner, sharing, status, and record-specific permissions.

These layers complement one another. You do not need to duplicate every condition verbatim at every layer, but every path to an operation must pass through at least one complete, trustworthy check for that operation. Never rely on the frontend, client-declared role/tenant data, or a helper function that can be bypassed.

## 5. Applying in Spring Security (Servlet, Spring Security 6)

### 5.1. Protecting HTTP routes with `SecurityFilterChain`

This is **illustrative integration code for a Spring Boot Servlet application**, not a standalone runnable Java program. Assume an authentication mechanism is configured and business permissions have been mapped to `GrantedAuthority` inside `Authentication`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/health/public").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.POST, "/api/documents/**")
                .hasAuthority("document:create")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("document:update")
            .requestMatchers(HttpMethod.DELETE, "/api/documents/**")
                .hasAuthority("document:delete")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Meaning:

- The `requestMatchers(...)` list declares the reviewed routes/methods; `anyRequest().denyAll()` closes all remaining routes.
- The `document:read` authority is only the **first gate**. Reading `/api/documents/123` still requires checking that document 123 is within the allowed scope.
- Matcher order can affect which rule is chosen: declare specific rules before broad rules. If there are multiple `SecurityFilterChain` beans, inspect the full scope of all chains so no endpoint is missed.
- The example omits login, JWT tokens, CORS, and CSRF configuration. Those mechanisms must be configured properly for the client type; do not arbitrarily disable CSRF for session/cookie-based apps. Spring Security Reactive/WebFlux uses `SecurityWebFilterChain` and `authorizeExchange`, not the Servlet configuration above verbatim.

When using a JWT/OAuth2 resource server, pay attention to mapping claims/scopes into authorities. For example, default config typically maps scopes to `SCOPE_<scope>`; `hasAuthority("document:read")` succeeds only when the system **actually** grants that exact authority string. Never assume a token field automatically turns into the desired Java permission.

### 5.2. Checking permissions at the business and data layers

Suppose documents must belong to the same tenant and be owned by the user. The service layer can enforce the authorization condition at the read point; the snippet below is **illustrative code**, requiring application types `Document`, `DocumentRepository`, `CurrentUser`, and `DocumentView`.

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;
    private final CurrentUser currentUser;

    public DocumentService(DocumentRepository documents,
                           CurrentUser currentUser) {
        this.documents = documents;
        this.currentUser = currentUser;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(Long id) {
        Long tenantId = currentUser.tenantId();
        Long userId = currentUser.userId();

        Document document = documents
            .findByIdAndTenantIdAndOwnerId(id, tenantId, userId)
            .orElseThrow(() -> new DocumentNotFoundException(id));

        return DocumentView.from(document);
    }
}
```

Here `@PreAuthorize` blocks callers lacking the functional permission, while the conditional query excludes documents outside the tenant or not owned by the caller. A repository implementation might declare:

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    Optional<Document> findByIdAndTenantIdAndOwnerId(
        Long id, Long tenantId, Long ownerId);
}
```

If documents can be shared among multiple users, replace the `ownerId` filter with the right object-level authorization policy for your business domain; do not treat this narrow example as an absolute rule. `CurrentUser` must obtain identity/tenant authenticated and verified by the server—never take a client-sent `tenantId` at face value.

**Key reminder when using `@PreAuthorize`:** method security must be enabled (e.g., `@EnableMethodSecurity`); the common mechanism relies on Spring AOP proxies. A call from one method to another on the **same instance** (self-invocation) can bypass the proxy, so do not rely on that annotation as the sole protection if another call path skips it. Object rules must sit on a boundary that is genuinely enforced, such as a public service called through a proxy and/or data-scoped queries.

### 5.3. Standalone Java 17 practice

The small program below has no Spring dependencies. It models a "has permission, same tenant, and right owner" policy to demonstrate that **a single satisfied condition alone is not enough to grant access**.

Save as `AuthorizationPrinciplesDemo.java`:

```java
import java.util.Set;

public class AuthorizationPrinciplesDemo {
    record User(long id, long tenantId, Set<String> permissions) {}
    record Document(long id, long tenantId, long ownerId) {}

    static boolean canRead(User user, Document document) {
        return user != null
            && document != null
            && user.permissions().contains("document:read")
            && user.tenantId() == document.tenantId()
            && user.id() == document.ownerId();
    }

    public static void main(String[] args) {
        User alice = new User(10, 7, Set.of("document:read"));
        User bob = new User(20, 7, Set.of("document:read"));
        User noPermission = new User(10, 7, Set.of());

        Document aliceDoc = new Document(1, 7, 10);
        Document otherTenantDoc = new Document(2, 8, 10);

        System.out.println(canRead(alice, aliceDoc));
        System.out.println(canRead(bob, aliceDoc));
        System.out.println(canRead(alice, otherTenantDoc));
        System.out.println(canRead(noPermission, aliceDoc));
    }
}
```

Compile and run:

```bash
javac AuthorizationPrinciplesDemo.java
java AuthorizationPrinciplesDemo
```

Exact output (stdout):

```text
true
false
false
false
```

Line-by-line explanation: Alice satisfies all conditions for her own document; Bob has the same permission but does not own the document; Alice does not belong to the second document's tenant; the last user is Alice by identity yet had her permission revoked. The function returns `false` on null inputs, illustrating deny-by-default when subject or resource is missing. In a real system, policies must also handle sharing, document state, delegation, and identity integrity.

## 6. Testing Authorization with Both Allowed and Denied Cases

Testing only "admin calls API and succeeds" is insufficient. Every sensitive operation needs at least the following representative cases:

| Test Case | Condition | Expectation |
| --- | --- | --- |
| Valid access | Right authority, tenant, object permission | Allowed |
| Unauthenticated | No valid identity | Operation not processed; usually 401 or redirect to login per app mechanism |
| Missing functional permission | Logged in but lacks `document:read` | Denied, usually 403 |
| Wrong owner | Has `document:read` but document belongs to someone else | Denied; may be 403 or 404 per disclosure policy |
| Wrong tenant | Has authority and knows ID, but different tenant | Denied |
| New endpoint/method | No rule declared for path or HTTP verb | Denied by default |
| Revoked permission | After revocation, perform next operation | No longer allowed per system's permission-refresh model |
| Alternative entry points | Exports, batch jobs, consumers, other service calls | Cannot bypass checks |

With Spring MVC, write integration tests using `MockMvc` and `spring-security-test` (e.g., `@WithMockUser`, `csrf()`); the illustrative snippet below assumes the configuration from section 5 and proper security setup loaded into the test:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Inside a test with a MockMvc instance named mockMvc:
mockMvc.perform(get("/api/documents/123")
        .with(user("reader").authorities(
            new org.springframework.security.core.authority.SimpleGrantedAuthority(
                "document:read"))))
    .andExpect(status().isNotFound()); // Example: document 123 is outside reader's scope

mockMvc.perform(get("/api/documents/123")
        .with(user("viewer").authorities(
            new org.springframework.security.core.authority.SimpleGrantedAuthority(
                "another:permission"))))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/admin/unknown")
        .with(user("reader")))
    .andExpect(status().isForbidden());
```

These are **illustrative statements placed inside a test**, not a standalone Java class. The 404 result in the first case holds only if test data and handlers are configured to hide document existence; depending on application policy, another denial status code may be valid. Do not write tests relying solely on HTTP status codes while forgetting to assert that no data was returned and no write occurred.

Combine unit tests for policy functions, integration tests for `SecurityFilterChain` and service layers, and tests that swap IDs, switch tenants, and change HTTP methods. Pay special attention to testing differences between users with the same role yet different data scopes.

## 7. Common Mistakes and Fixes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Hiding buttons only in the UI | API can be called directly | Enforce permissions on the server |
| Using only `authenticated()` for every API | Any logged-in user can call sensitive functions | Split authorities by action |
| Checking role without checking ID/tenant | Leaks or modifies others' objects (IDOR/BOLA) | Object policies and data-scoped queries |
| Ending rule is `permitAll()` or too broad | New endpoints become accidentally open | Explicit public rules, default `denyAll()` |
| Trusting `userId`/`tenantId` from request | Clients can claim another identity/scope | Use authenticated identity and server-verified data |
| Checking only at login or page render | Permissions and resources can change, other call paths exist | Check at each sensitive operation |
| Relying solely on annotations when self-invocation occurs | Call paths exist that bypass proxies | Protect at real service boundaries and the data layer |
| Forgetting exports, background jobs, batches | Access paths exist outside regular controllers | Inventory all entry points and test alternative paths |
| Retaining permissions after role change or expiration | Privilege creep over time | Use expirations, reviews, and revocation |
| Assuming JWT claims = authorities | Rules may check the wrong or missing string | Verify actual claim/scope → `GrantedAuthority` mapping |

Logging helps detect anomalous behavior, yet never replaces allow/deny decisions. Logs should include subject, action, normalized target object, outcome, and correlation ID; avoid logging tokens or unnecessary sensitive data.

## 8. Applying This to a New Feature

1. **Identify object and action:** who wants to perform what operation on which resource, in which tenant/context?
2. **Write the minimal allow policy:** functional permission, object scope, state, and approved business exceptions. Explicitly state denial cases.
3. **Place checks at every access path:** HTTP, service methods, data queries, jobs, exports. Do not rely on UI or unmapped tokens/claims.
4. **Close undefined cases:** default-deny matchers, unprivileged accounts cannot escalate themselves, missing policy data never passes through.
5. **Test by matrix:** right person, wrong person, different tenant, missing permission, unauthenticated, swapped ID, swapped HTTP verb, revoked permission; ensure no unauthorized data or side effects occur.
6. **Manage permission lifecycle:** who grants, who approves, when it expires, how to revoke, and how to investigate denied access.

### Self-check

- An employee has `document:read` yet reads a document in another tenant. Which principles require blocking this? **Least privilege by object scope** and **complete mediation**.
- A new `PATCH /api/documents/{id}` endpoint has no rule yet. What is the safe handling? **Deny by default**, until permissions are explicitly defined.
- The UI already hides the "Delete" button. Does the delete API still need to check permissions? **Yes**; the frontend is not a security boundary.
- A query has only `WHERE id = :id` even though the API already checked a general permission. What is missing? **Tenant/owner restrictions or object sharing policy**.
- When the system cannot determine permissions due to corrupted policy data, should a sensitive operation proceed? **No**; fail closed and handle the error appropriately.

**Remember:** "What can be done" must be granted minimally; "what is not explicitly granted" must be denied; and "whether it is allowed on this object right now" must be verified on every path that can actually perform the operation.