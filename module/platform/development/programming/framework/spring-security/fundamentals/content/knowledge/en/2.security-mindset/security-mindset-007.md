# Successful Authentication Does Not Mean Access to All Data

An application lets Mai log in successfully. Mai opens `GET /api/documents/101` and views her own document. If Mai changes the document ID to `102`, the application **must not automatically return document 102** just because Mai's account is logged in. That document may belong to An, belong to another organization, or be readable only by users with special privileges.

This is a core principle in Spring Security: **authentication proves identity according to the configured mechanism; authorization decides whether that identity may perform a specific operation on a specific resource**. A successful authentication is only one input to multiple security decisions.

This lesson moves from mindset to a per-record permission model, how to apply it with Spring Security, and a self-contained Java 17+ example. The central question is: **which exact data may a logged-in user view or modify, and who verifies that?**

## 1. Distinguishing Three Questions to Answer

Suppose a document management application has three users: Mai, An, and an organization administrator. Each document has an owner and belongs to a tenant (organization/data space).

| Question | Mechanism That Usually Answers | Example |
| --- | --- | --- |
| **Who are you?** | Authentication | Request belongs to Mai's authenticated account |
| **Which actions may you take?** | Function/permission-based authorization | Mai holds `DOC_READ` but not `DOC_DELETE` |
| **On which data may you do it?** | Resource- and context-based authorization | Mai may only read documents she owns within the current tenant |

Solving only the first two questions still lets the application leak data when users swap `documentId`, `userId`, `orderId`, or `tenantId` in URLs or request payloads.

An `Authentication` result typically carries a principal and `GrantedAuthority` items. It tells you the identity and privileges granted by the authentication mechanism; it **does not carry a built-in guarantee that every record in the database may be viewed**. The final decision also depends on action, object, ownership, tenant, and application policy.

~~~text
Request: GET /api/documents/102
                |
                v
  [1] Is there a trusted Authentication?
                |
        No --> require authentication
                |
               Yes
                v
  [2] Has DOC_READ authority?
                |
        No --> deny
                |
               Yes
                v
  [3] Is Document 102 within the
      permitted data scope?
      (tenant, owner, sharing, policy)
                |
        No --> deny / hide existence
                |
               Yes
                v
          Return permitted data
~~~

The key point at step [3] is **evaluating document 102 itself**. Steps [1] and [2] succeeding never replace the data-scope check.

## 2. From Broad Permissions to Per-Object Permissions

To design access control, distinguish three combinable layers of scope:

**Functional authorization.** Is the account allowed to invoke read, edit, delete, export report, or admin functions? For example, `DOC_READ` allows entering the document-reading function; `DOC_DELETE` is a separate permission. Read permission never implies edit permission.

**Object-level authorization.** Is this user allowed to read **document ID 102**? Even with the same `DOC_READ` permission, Mai and An may see two different sets of documents. The condition may be owning the document, having it shared with them, or being assigned to handle it.

**Data scope authorization.** Which organization, project, department, or group may the request access? An administrator of tenant A is not implicitly an administrator of tenant B's data. If `DOC_READ_ALL` is used in this example, it is explicitly defined as "read all documents **within one's own tenant**," not system-wide.

A minimal learning model:

| Caller | Authenticated | Authorities | Tenant | Document Owner | Document Tenant | Read? |
| --- | --- | --- | --- | --- | --- | --- |
| Mai | Yes | `DOC_READ` | A | Mai | A | Yes |
| Mai | Yes | `DOC_READ` | A | An | A | No |
| Admin A | Yes | `DOC_READ`, `DOC_READ_ALL` | A | An | A | Yes |
| Admin A | Yes | `DOC_READ`, `DOC_READ_ALL` | A | An | B | No |
| Unauthenticated guest | No | Insufficient | A | Mai | A | No |

This table is a **policy chosen for this example**, not a built-in Spring Security rule. In another product, documents might be shared with a group or made public; the policy must describe and enforce the matching sharing rules accurately.

### Do Not Treat a Role as Access to All Data

`ROLE_USER`, `ROLE_MANAGER`, and `ROLE_ADMIN` are role labels. In Spring Security, `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority by default (prefix is configurable); `hasAuthority("DOC_READ")` checks the exact permission string. Even when `hasRole("ADMIN")` passes, **administrative scope must still be defined**: system admin, tenant admin, or project admin?

Two identities with the same `ROLE_MANAGER` role can be assigned to different projects. A broad role or authority does not determine the owner, tenant, or sharing relationship of individual records.

## 3. Risks of Checking Only "Logged In"

A controller might look like this:

~~~java
// VULNERABILITY illustration, do not use in production applications.
@GetMapping("/api/documents/{id}")
public DocumentDto read(@PathVariable long id) {
    return documentService.findById(id);
}
~~~

If the security config only requires `anyRequest().authenticated()`, a valid user can try another ID. The authentication filter let the request through because the account is logged in, yet `findById(id)` never checked whether **the caller has rights to view that exact object**.

This is commonly called **IDOR** (Insecure Direct Object Reference), under **Broken Object Level Authorization (BOLA)**: the application lets users reference an object by ID without enforcing corresponding permissions. IDs do not have to be sequential numbers; using random UUIDs makes guessing harder but **does not replace authorization checks**.

Watch out for leakage paths beyond the "view detail" page:

- **GET a single record:** knowing someone else's ID and reading its contents.
- **GET list or search:** the API returns records from another tenant, including ID lists and metadata.
- **Record counts, pagination, statistics:** items are filtered yet `totalCount` still counts unauthorized records.
- **Edit/delete/state transition:** the user submits someone else's object ID in the URL or body.
- **CSV export, attachment download, history lookup:** secondary paths bypass rules enforced on the main screen.
- **Sensitive fields within the same record:** permission to read a document title does not imply permission to read internal prices, personal identifiers, or secret fields. This is also a property-level authorization concern.

A UI hiding a "Delete" button or omitting other users' documents only improves UX; **direct API requests must still be verified by the server**. Never trust browser-supplied `ownerId` or `tenantId` as proof of access.

## 4. Elements of an Authorization Decision

An access decision can be modeled as:

~~~text
ALLOW = policy(subject, action, resource, context)

subject  : verified principal, authorities, tenant, and attributes
action   : read / create / update / delete / approve / export
resource : specific record, file, report, data field
context  : owner relationship, sharing, state, tenant, timestamp...
~~~

Example document-reading policy in this lesson:

1. The subject is genuinely authenticated.
2. The subject holds the `DOC_READ` permission.
3. The document's tenant matches the subject's trusted tenant.
4. Within that tenant, the caller is the owner **or** holds `DOC_READ_ALL`.

If any mandatory condition fails, the decision is **deny**. The `DOC_READ_ALL` permission never bypasses the tenant check. An `UPDATE` action must have its own policy, such as a `DOC_EDIT` permission and appropriate owner/manager conditions.

Principles to remember:

- **Deny by default:** actions without a defined permission are not allowed automatically.
- **Least privilege:** grant only the minimum permissions needed for the job and required data scope.
- **Complete mediation:** every execution path that can access a resource must pass through the corresponding control.
- **Server-side enforcement:** trusted decisions happen on the server using verified data.

When a policy is missing, explicitly define who may view each class of data; do not patch around it by treating everyone who is logged in as qualified.

## 5. Self-Contained Java 17+ Example: Successful Login Can Still Be Denied

This example uses plain Java to illustrate the checks. It is a **policy model**, not a full authentication system: the `authenticated` flag and authorities are pre-populated for learning. In a real application, these values must come from a trusted authentication result.

Create `AuthorizationScopeDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public class AuthorizationScopeDemo {

    record User(
            String id,
            String tenant,
            boolean authenticated,
            Set<String> authorities
    ) {}

    record Document(long id, String owner, String tenant) {}

    static boolean canRead(User caller, Document document) {
        return caller.authenticated()
                && caller.authorities().contains("DOC_READ")
                && caller.tenant().equals(document.tenant())
                && (caller.id().equals(document.owner())
                    || caller.authorities().contains("DOC_READ_ALL"));
    }

    public static void main(String[] args) {
        User mai = new User("mai", "tenant-A", true, Set.of("DOC_READ"));
        User adminA = new User(
                "admin-a",
                "tenant-A",
                true,
                Set.of("DOC_READ", "DOC_READ_ALL"));
        User anonymous = new User(
                "guest", "tenant-A", false, Set.of("DOC_READ"));

        Document own = new Document(101, "mai", "tenant-A");
        Document another = new Document(102, "an", "tenant-A");
        Document otherTenant = new Document(103, "an", "tenant-B");

        System.out.println("Mai own=" + canRead(mai, own));
        System.out.println("Mai other=" + canRead(mai, another));
        System.out.println("Admin A other=" + canRead(adminA, another));
        System.out.println("Admin A other tenant="
                + canRead(adminA, otherTenant));
        System.out.println("Anonymous own=" + canRead(anonymous, own));

        List<Long> visibleIds = List.of(own, another, otherTenant)
                .stream()
                .filter(document -> canRead(mai, document))
                .map(Document::id)
                .toList();

        System.out.println("Mai visible IDs=" + visibleIds);
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac AuthorizationScopeDemo.java
java AuthorizationScopeDemo
~~~

Expected output:

~~~text
Mai own=true
Mai other=false
Admin A other=true
Admin A other tenant=false
Anonymous own=false
Mai visible IDs=[101]
~~~

Case-by-case breakdown:

- **Mai reads document 101:** authenticated, has `DOC_READ`, matching tenant, and is the owner → `true`.
- **Mai reads document 102:** still successfully authenticated and has `DOC_READ`, but owner is An and Mai lacks `DOC_READ_ALL` → `false`.
- **Admin A reads document 102:** has permission to read all documents in tenant A → `true`.
- **Admin A reads document 103:** despite having `DOC_READ_ALL`, tenant B is out of scope → `false`.
- **Unauthenticated guest reads document 101:** denied before checking ownership, even though the example deliberately put `DOC_READ` in the mock data.

The `filter` in the example only clarifies the displayed list. In applications with a database and large datasets, apply permission filters directly inside the allowed data query: that way pagination, totals, sorting, and resources fetched elsewhere all honor the same scope. Never load all confidential data into memory and rely on UI filtering as a security barrier.

## 6. Applying Across Layers in Spring Security

Spring Security helps verify identity and require permissions at multiple points. For record-level access, you typically combine **request rules** with **service/data policies**.

### 6.1. HTTP Layer: Checking Whether the Function May Be Called

Example Spring Security servlet configuration snippet using `SecurityFilterChain`:

~~~java
// Other imports and bean configuration omitted:
// @Bean SecurityFilterChain security(HttpSecurity http) throws Exception
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/documents/**")
            .hasAuthority("DOC_READ")
        .anyRequest().denyAll()
);
~~~

This example only allows GET requests to the documents area when `DOC_READ` is present, and denies remaining undeclared requests. **This URL rule does not know who owns document 101 or 102.** Therefore `GET /api/documents/102` still needs a business-layer check.

Rules in `authorizeHttpRequests` are evaluated in order, and the first matching rule decides. Put specific rules first and a catch-all rule last; never open `permitAll` on sensitive data areas just because a controller will check later.

### 6.2. Method Layer: Enforcing Permissions When Invoking Business Logic

Spring Security supports method security via `@EnableMethodSecurity` and `@PreAuthorize`. Once method security is configured and invoked through the proper interceptor mechanism, you can write:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public DocumentDto getDocument(long documentId) {
    // Method body must still filter permissions on documentId.
    return documentService.readAuthorized(documentId);
}
~~~

This is an **illustrative snippet inside a Spring app**, omitting class declarations, imports, beans, or the implementation of `readAuthorized`, so it does not run standalone. The method annotation requires the functional permission `DOC_READ` yet **does not automatically check ownership or tenant**; `readAuthorized` must do that.

You can express object-level permissions in a dedicated policy bean, such as `@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")`, provided method security is enabled, `documentPolicy` is registered, expression parameters resolve, and the policy method reads trusted info/attributes. That is one design approach when multiple places share a policy; Spring Security has no built-in `canRead` method tailored to your domain data.

Proxy note: with Spring AOP-based method security, calling an annotated method **from within the same object** (self-invocation) may bypass the interceptor. When designing security boundaries, check real call paths and place verification logic in reliably invoked services/policies; avoid treating annotations as decorative labels.

### 6.3. Data Layer: Restricting Objects Directly in the Query

The safe flow for a document-reading API is:

~~~text
Trusted Authentication
   -> extract verified userId, tenantId, and authorities
   -> check DOC_READ permission
   -> fetch data by documentId + tenantId + owner/sharing/extended read permission
   -> return DTO only for in-scope documents
~~~

An illustrative SQL query for this lesson's policy:

~~~sql
SELECT d.id, d.title, d.content
FROM documents d
WHERE d.id = :documentId
  AND d.tenant_id = :trustedTenantId
  AND (
       d.owner_user_id = :trustedUserId
       OR :canReadAllInsideTenant = TRUE
  );
~~~

Here the `trusted`-prefixed parameters must come from a server-verified context, never blindly from `?tenantId=` in the URL or the client's request body. `:canReadAllInsideTenant` is computed by the server against valid authorities after confirming the basic read permission. The SQL is conceptual: parameter syntax and booleans depend on the data-access layer and DBMS.

When no record is found within the allowed scope, the service can return a policy-appropriate error, such as `404 Not Found` to avoid disclosing the existence of unauthorized documents. For authenticated actions lacking permission, `403 Forbidden` is common. Whether to use 403 or 404 for out-of-scope objects must remain consistent with the system's security and UX requirements.

**Lists and pagination:** apply the exact same permission predicates to list queries, `COUNT`, reports, file exports, and search APIs. If `SELECT` filters by tenant yet `COUNT(*)` does not, total counts still leak information.

**Writing data:** write permission checks must bind to the exact object and current state. Under concurrent modifications, combine owner/tenant conditions into the `UPDATE`/`DELETE` statement or use appropriate transactions/locks to close the gap between checking and writing.

### 6.4. Why Have Both HTTP Rules and Business Checks?

The HTTP layer blocks unauthorized operations early. The method/service layer keeps rules close to actual behavior, even when services are invoked through alternative paths or multiple controllers. The data layer scopes the exact set of readable/modifiable records. The layers complement one another; policies across layers must agree.

Never rely solely on the frontend hiding paths, buttons, or obfuscating IDs. Also do not use `Authentication#getName()` as a business user ID if the system allows mutable display names or multiple providers with different naming conventions. Map trusted principals to stable internal application identifiers.

## 7. Authorization Dimensions to Keep Distinct

### 7.1. Horizontal Access: One User to Another User's Data

Two users share `ROLE_USER` but have different ownership. Mai may view Mai's orders, not An's orders. Functional permissions must not allow crossing ownership boundaries.

### 7.2. Vertical Access: Regular User to Administrative Privileges

A user holding `DOC_READ` must not invoke `DELETE /api/documents/101` without delete permission and matching conditions, even if they own the document. Likewise, an account in tenant A must not become tenant B's admin simply by changing a parameter.

### 7.3. Project and Tenant Scope

In multi-organization software, each record usually belongs to a tenant. Every query and operation must maintain tenant boundaries, including accounts holding admin roles within their own tenant. Reading files from object storage, running background jobs, or reading from caches must preserve this same scope.

### 7.4. Field-Level Permissions

Someone may be allowed to read a profile's name and status without being allowed to read `salary`, `personalIdentifier`, or internal keys. Enforce policies when building DTOs/responses or via queries selecting only permitted columns. Never return full entities hoping the UI will ignore sensitive fields.

## 8. HTTP Status Codes and Denial Handling

| Situation | Typical Meaning in Auth-Required APIs | Appropriate Response |
| --- | --- | --- |
| No valid authentication credentials | Required identity could not be established | Usually `401 Unauthorized` |
| Authenticated, lacking permission for action | Insufficient authority/policy | Usually `403 Forbidden` |
| Authenticated with general permission, object out of visibility scope | Not allowed to view that object's content | `403` or `404` per existence-hiding policy |
| Sufficient permission and object in scope | Operation allowed | `200`, `204`, or appropriate success status |

These are explanatory conventions, not a rigid mapping for every Spring Security setup; authentication entry points, access-denied handlers, protocols, and application policies can produce different responses.

When denying, avoid attaching blocked document content or sensitive details in error payloads. Internal logs can record decision traces (actor, action, safely handled resource identifier, outcome) for investigation, without printing passwords, tokens, or full private data.

## 9. Testing Must Cover "Logged In Successfully Yet Denied"

Testing only "unauthenticated is blocked" and "logged-in gets 200" is insufficient. Test at least:

| Test Case | Expected Result |
| --- | --- |
| Unauthenticated reads private document | Denied |
| Authenticated without `DOC_READ` | Denied |
| Authenticated with `DOC_READ`, reads own document | Allowed |
| Authenticated with `DOC_READ`, swaps to same-tenant user's ID | Denied unless sharing permission exists |
| Tenant A admin reads another user's document in Tenant A | Allowed if policy grants `DOC_READ_ALL` |
| Tenant A admin swaps to Tenant B ID | Denied |
| Has read permission yet calls edit/delete | Denied if write permission is missing |
| Calls list/search/count APIs | Sees only in-scope data and counts |
| Calls file download or report export API | Applies the same data restrictions |
| Operates on nonexistent or forbidden document | Leaks no unauthorized content |

Spring Security provides request/method testing utilities (e.g., MockMvc, `@WithMockUser`). However, a test that merely mocks authorities is usually **insufficient** to verify owner and tenant boundaries: prepare multiple accounts, multiple records across same/different tenants, and assert the exact response data. The most dangerous case is two users **both validly logged in**, where one accesses the other's data.

If using `@PreAuthorize`, verify method security is actually enabled and calls flow through the protection mechanism. If using tenant-scoped queries, test matching `documentId` conventions across different tenants; never treat request-supplied `tenantId` as trustworthy.

## 10. Misconceptions to Eliminate

1. **"Logged in means access to everything."** False: login authenticates identity; it does not establish permissions per resource.
2. **"The path already requires `authenticated()`, that's enough."** False for private data: you must check owner, tenant, and action permissions.
3. **"Having `ROLE_ADMIN` allows viewing every tenant."** False if the system scopes admin roles per organization.
4. **"Using UUIDs instead of numeric IDs eliminates IDOR."** False: once a UUID is known or obtained, permission checks are still required.
5. **"Hiding the button blocks the API."** False: clients can send requests directly.
6. **"Filtering the list on the frontend is enough."** False: data was already sent to the client before filtering.
7. **"If the controller checked it, everywhere calling the service is safe."** Not guaranteed: another call path may bypass the controller. Protect business logic at the proper boundary.
8. **"No document details are shown, so leaking total count is safe."** Not necessarily: counts, IDs, filenames, and metadata can also be sensitive.
9. **"Read permission implies edit permission."** False unless policy explicitly grants matching permissions.
10. **"Permission was checked before querying, so updating is always safe."** Not guaranteed: owner/state can change between check and write; guard conditions inside transactions or write statements as needed.

## 11. Self-Check Questions

**Question 1.** An and Mai both have `ROLE_USER` and `DOC_READ`. Why isn't Mai automatically allowed to read An's document?

*Answer:* Functional permission `DOC_READ` is only one condition. The policy must also check ownership/sharing and tenant of the requested document.

**Question 2.** Tenant A's admin has `DOC_READ_ALL`. Can they read Tenant B's documents?

*Answer:* Under this lesson's policy, no. "ALL" only expands owner scope inside Tenant A; the tenant check remains mandatory.

**Question 3.** If an API uses `requestMatchers("/api/**").authenticated()` and the controller calls `findById(id)`, what is missing?

*Answer:* Action permission and object-level scope checks for `id`, as well as protection for other call paths at the service/data layers.

**Question 4.** Can `tenantId` sent in the request body be treated as proof the user belongs to that tenant?

*Answer:* No. The server must determine allowed tenants from verified authentication info and trusted membership records. A client-requested tenant is only a parameter to validate against.

**Question 5.** Which case needs closer testing: an unauthenticated guest viewing a document, or two logged-in users reading each other's documents?

*Answer:* Both need testing; however, the second case is especially critical for catching object-level authorization bugs that ordinary login tests miss.

When designing a Spring Security API, do not stop at asking **"does this request have an Authentication?"**. Keep asking **"is this user allowed to perform that action on this exact record, field, tenant, and state?"**. Only when every mandatory condition holds should the application disclose or modify data.

### Reference Links

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
