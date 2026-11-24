# Boundary Between Spring Security Mechanisms and Business Policy

> **Lesson in:** Spring Security - authorization → Authorization Landscape.
>
> **Objective:** After this lesson, you will distinguish "by what mechanism does Spring Security check permissions?" from "how does business logic decide who can do what on which data?", place each decision in the right layer, and verify that URL-level or general role permissions do not accidentally grant access to specific resources.

## 1. One Request, Two Different Questions

Suppose a document management application exposes `PATCH /api/documents/42`. User Alice logs in successfully and has the general permission `document:edit`. Is Alice allowed to edit document 42?

**Not yet determinable.** The `document:edit` permission only states that Alice is capable of performing the "edit document" operation type; the system still needs to know which organization the document belongs to, who owns it, whether Alice is authorized on that specific document, and whether the document's state allows this operation.

There are at least two decision layers:

1. **Security mechanism:** identifies the caller, retrieves authorities, blocks requests or method invocations according to configured rules, reports access-denied errors, and integrates enforcement points.
2. **Business authorization policy:** determines the conditions allowing *a specific action* on *a specific resource* in *a specific context*: owner, tenant, collaboration relationship, approval rights, workflow stage, approved exception rules.

Spring Security provides both enforcement points and hooks to plug in custom rules (e.g., `AuthorizationManager`, method security, `@PreAuthorize`). That does **not** mean the framework inherently knows rules like "once a document is approved, only compliance staff may unlock it". That rule must be explicitly modeled by the application team.

Further distinctions:

- **Authentication:** "Who is the caller?", is the login/token proof valid?
- **Authorization:** "Is this person allowed to perform this action on this object, in this context?".
- **Business invariant:** "Is the operation valid given the data state, regardless of who calls it?". For example, total amount cannot be negative. A state condition can participate in authorization if it changes *who* is allowed to do what; if it forbids everyone equally, it usually belongs to general business validation.

## 2. Responsibility Map: Which Layer Decides What?

| Concern | Spring Security / Security Adapter | Business Policy and Services |
| --- | --- | --- |
| Who is calling? | Authenticates session, HTTP Basic, JWT, or configured mechanism; provides `Authentication` | Maps trusted identity into an application-domain actor/tenant identifier |
| General permissions | Checks `hasAuthority`, `hasRole`, HTTP method, URL, or method | Defines what `document:edit` means in the document domain |
| Which data is accessed? | Does not inherently know who owns record 42 | Loads resources within tenant scope; checks owner, group, delegation, data scope |
| Which context is considered? | Provides check invocation points and required security data | Evaluates workflow state, relationships, time validity, exception rules |
| When denied? | Blocks via Spring Security mechanisms; orchestrates security errors | Returns clear deny decision or throws an exception matching the API contract |
| Who governs rule changes? | Configures interception layers and wiring to rules | Product/domain owner confirms rule semantics; dev team maintains tested policies |
| Preventing data leaks | Configures access paths, authentication/authorization at boundaries | Scopes queries, checks objects before disclosing, avoids filtering sensitive data only in UI |

**Principle:** anything that needs to understand owner, tenant, approval relationships, or entity state must be expressed as a business rule; Spring Security can invoke that rule at an appropriate enforcement point. "Using `@PreAuthorize`" is choosing an **enforcement mechanism**, while the expression or service called inside expresses the **policy content**.

A practical model for design is:

```text
Decision = Policy(actor, action, resource, context)
actor    = authenticated subject mapped to an application-domain identity
action   = business-meaningful action (view, edit, approve, refund, ...)
resource = real object to operate on (Document #42, Order #81, ...)
context  = tenant, relationships, state, time, and relevant facts
```

Do not reduce per-resource decisions solely to `Policy(role)` or `Policy(URL)`.

## 3. Check Flow in a Servlet Application

```text
HTTP request
   |
   v
Spring Security filter chain
   |-- authenticate caller (if the route requires it)
   |-- HTTP rules: block invalid requests or missing coarse-grained permissions
   v
Controller receives request (untrusted input data only)
   |
   v
Application service / use case
   |-- obtain trusted actor from security adapter
   |-- query data within valid tenant scope
   |-- apply domain authorization policy(actor, action, resource, context)
   |-- check other business invariants
   v
Execute business logic / save data / return result
```

With Servlet, `AuthorizationFilter` uses an `AuthorizationManager` to check requests. On denial, Spring Security may raise `AccessDeniedException`, and exception handling translates it into a response suitable for the configured authentication mechanism. Method security adds an interception point at Spring-managed bean method calls when enabled.

Both layers add value:

- **HTTP-level:** fails fast and cheaply on public/internal routes, HTTP methods, and broad permissions. For example, someone without `document:edit` cannot enter the edit endpoint.
- **Method-level:** controls use case/service invocations even when logic is called from multiple endpoints; can invoke a policy bean.
- **Domain/application-level:** checks after knowing the real entity and context; shared with batch processes, message consumers, or entry points outside HTTP.

Layers can be combined, yet never assume that merely enabling `@EnableMethodSecurity` automatically protects all services: the application must attach rules to methods or configure suitable advisors/managers. Spring Boot Starter Security does not turn on method-level authorization automatically.

## 4. HTTP Configuration Is the "Front Door", Not Ownership Rules

The example below illustrates **part of a configuration** for Spring Boot 3 / Spring Security 6 (Servlet). The application must configure the real authentication mechanism and required beans itself; this snippet is not a standalone runnable app.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("document:edit")
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Meaning:

- Rules on HTTP method + URL are **entry conditions**, e.g., Alice needs `document:edit` to send PATCH.
- Those rules **do not determine** whether Alice is allowed to edit document `42`.
- `anyRequest().denyAll()` prevents undeclared routes from being accidentally allowed; grant public access only to routes designed to be public.
- Within a single `authorizeHttpRequests`, **matcher order matters**: the first matching rule applies. Never place `/api/**.authenticated()` before specific rules and expect later rules to run.
- `hasRole("EDITOR")` normally checks an authority with the `ROLE_` prefix; `hasAuthority("document:edit")` checks the exact authority string. Mapping for roles, JWT scopes, and permissions must be defined consistently—never guess solely from names.
- HTTP rules do not handle CSRF, authentication methods, or tokens by themselves; for state-changing endpoints in session/cookie apps, design CSRF properly per architecture. Do not disable CSRF just to make a PATCH example work.

Common design mistake: opening `/api/documents/**` to all logged-in users and assuming that because document IDs are hard to guess, others cannot access them. This is a **Broken Object Level Authorization (BOLA/IDOR)** risk: an attacker swaps `42` for another document ID, and missing checks at the data layer permit unauthorized access.

## 5. Business Policy Must Receive Full Actor, Action, Resource, and Context

Suppose the rule for editing a document title is:

1. Caller has permission `document:edit`.
2. Caller and document are in the same tenant.
3. Caller is the owner (or a user granted edit sharing per an agreed policy).
4. Document is still in `DRAFT` state; unlocking or revising an approved document is a **separate use case** with its own permissions and workflow.

Using only `hasAuthority("document:edit")` skips conditions 2–4. Comparing only the owner skips permissions and tenant. All relevant conditions must be evaluated; whenever data is missing or permissions cannot be verified, **deny by default**.

The **standalone** Java 17+ snippet below illustrates a minimal policy. The example intentionally allows only the owner to edit; sharing rules can be extended into a dedicated relationship, rather than speculatively adding an "admin always allowed" clause.

```java
import java.util.Set;

public class PolicyBoundaryDemo {

    record Actor(String userId, String tenantId, Set<String> permissions) {
        boolean hasPermission(String permission) {
            return permissions.contains(permission);
        }
    }

    record Document(String ownerId, String tenantId, String status) {}

    static boolean mayEdit(Actor actor, Document document) {
        return actor.hasPermission("document:edit")
            && actor.tenantId().equals(document.tenantId())
            && actor.userId().equals(document.ownerId())
            && "DRAFT".equals(document.status());
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "shop-a", Set.of("document:edit"));

        System.out.println("own draft: " +
            mayEdit(alice, new Document("alice", "shop-a", "DRAFT")));
        System.out.println("other owner: " +
            mayEdit(alice, new Document("bob", "shop-a", "DRAFT")));
        System.out.println("other tenant: " +
            mayEdit(alice, new Document("alice", "shop-b", "DRAFT")));
        System.out.println("approved: " +
            mayEdit(alice, new Document("alice", "shop-a", "APPROVED")));
    }
}
```

Save as `PolicyBoundaryDemo.java` and run:

```bash
javac PolicyBoundaryDemo.java
java PolicyBoundaryDemo
```

Expected output:

```text
own draft: true
other owner: false
other tenant: false
approved: false
```

Key lesson: **same Alice, same authority, different outcomes because resource and context differ**. In a real system, actor and document must come from trusted sources; this standalone example only verifies decision logic, without authentication, database, or HTTP.

## 6. Where Should Policy Live in a Real Project?

There are two common approaches, which can be combined while keeping a single source of truth for rules.

### Approach A — Service loads data then calls policy

This is usually the clearest choice when entity data, tenant, relationships across records, and transactions are needed.

```java
// Structural illustration code: Document, Actor, repository,
// DocumentPolicy, and exceptions are application-defined.
@Service
class DocumentService {
    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    DocumentService(DocumentRepository repository, DocumentPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:edit')")
    public void rename(UUID documentId, String title, Actor actor) {
        Document document = repository
            .findByIdAndTenantId(documentId, actor.tenantId())
            .orElseThrow(() -> new DocumentNotFoundException(documentId));

        if (!policy.mayRename(actor, document)) {
            throw new AccessDeniedException("Rename not allowed");
        }

        document.rename(title); // Document protects its own domain invariant.
    }
}
```

In this pattern:

- `@PreAuthorize` fails fast when general permission is missing.
- `findByIdAndTenantId` restricts the query to the **authenticated** tenant, rather than loading any record and accidentally returning data to another tenant.
- `DocumentPolicy` is where owner, collaboration, and state conditions are expressed. It can be unit-tested independently without starting a web server.
- `document.rename(...)` is responsible for domain invariants, such as valid title or allowed state transitions. Do not put every validation rule into the authorization policy.
- `@Transactional` keeps reading, checking, and updating inside the same transaction; under concurrent updates, add optimistic/pessimistic locking as required by the domain, since a transaction alone does not solve every race.
- The `Actor` parameter must be obtained by the **server** from the authenticated identity/trusted mapper and passed to the service; never accept actor, user ID, or tenant ID as arbitrary client-declared input.

This is an integration snippet, **not a standalone Java file**: compiling it requires a Spring application and the corresponding domain classes. Typical Spring imports include `@Service`, `@Transactional`, `@PreAuthorize`, and `AccessDeniedException`.

### Approach B — Method security calls a policy bean

When the interception point already has all necessary facts and rules need to be reused across multiple methods:

```java
@PreAuthorize("@documentAccess.canEdit(authentication, #documentId)")
public void editDocument(UUID documentId, EditCommand command) {
    // Process after authorization succeeds.
}
```

Here `documentAccess` is an application-written Spring bean; it maps `authentication` to a trusted actor, queries/checks the resource, and returns a boolean. `@EnableMethodSecurity` must be enabled for the annotation to apply.

**Important consideration:** If the policy bean queries the document and then the service queries it again, you risk checking against a different version of the data than what gets modified (race/time-of-check-time-of-use), increasing I/O, or scattering rules across multiple places. You can choose a service guard in the same transaction as Approach A, or design controlled, consistent pre-authorization. Avoid hiding complex business queries inside long, hard-to-test SpEL expressions.

**Proxy caveat:** Method security in Spring typically works via AOP interceptors/proxies. An internal call from one bean method to another on the same object (`this.method()`) can bypass the proxy and therefore skip `@PreAuthorize` on the target method. If rule integrity depends on this call, place the guard inside a use-case service that is always executed or route the call through another properly proxied bean. Meanwhile, jobs, consumers, or CLIs that do not pass through servlet filters must still be checked at the appropriate use-case point.

## 7. Trusted Identity: Never Infer Permissions from Client Data

A request may carry `documentId`, `tenantId`, `ownerId`, or `role`. These are **untrusted inputs** until verified:

- `documentId` helps locate the resource; by itself it does not prove permission on the resource.
- `ownerId` sent in JSON does not determine who the owner is; retrieve owner info from server-side data.
- `tenantId` in URL/headers may only be used as a selection context **after** verifying that the actor genuinely has access to that tenant. In multi-tenant systems, checking only owner ID without tenant can still leak across organizations.
- Roles/authorities must come from verified authentication/authorization sources (`SecurityContext`, tokens whose signature/issuer/audience are validated per config, server permission stores)—never trust a client claiming `"admin=true"`.
- For real actors, separate stable `subjectId` from mutable display names/emails; when acting for an organization on someone's behalf, represent actor, represented organization, and delegation rights explicitly instead of dropping context.

Many teams introduce a mapper like `AuthenticatedActorResolver` to translate `Authentication` into a domain-accurate `Actor`. Domain policies then receive only `Actor`, keeping policy logic independent of whether the actor came from a session, JWT, mTLS, or another security adapter.

## 8. Do Not Conflate Three Kinds of Rules

Example of a recently approved document:

| Rule | Nature | Where Should It Be Checked? |
| --- | --- | --- |
| Only users with `document:edit` may call the edit API | General functional permission | HTTP and/or method |
| Only owner or assigned editor may edit documents in the same tenant | Resource-level authorization | Application/domain policy |
| `APPROVED` documents cannot be edited directly; only the `revise` workflow creates a new version | Business lifecycle invariant/policy | Domain service and entity invariant |
| Only reviewers may approve `SUBMITTED` versions, and cannot self-approve their own document | State-, relationship-, and separation-of-duties-dependent authorization | Domain policy + domain invariant |

When a state condition determines *who* may perform an operation, it is part of authorization policy; when it determines *whether an operation is inherently invalid* for everyone, it is usually an invariant. Rules can relate to each other, yet must be articulated clearly to return accurate status codes and test the right failure reasons.

Never use "ADMIN bypasses everything" as a default. If an emergency bypass exists, policy must specify exactly which actor, which scope, reason, time limit, approval step, and mandatory audit.

## 9. Access Denial and the Meaning of 401, 403, 404

Common HTTP outcomes in REST APIs:

- **401 Unauthorized:** the request requires authentication yet lacks valid credentials per the API's mechanism (despite the name "Unauthorized", the meaning is usually unauthenticated).
- **403 Forbidden:** the identity is authenticated yet not allowed to perform the action. `AccessDeniedException` is typically routed through a handler in Spring Security; the application needs clear mapping if exceptions originate from domain/application services.
- **404 Not Found:** resource does not exist; multi-tenant systems sometimes use the same 404 response for "nonexistent or invisible" to avoid disclosing a resource's existence. This is a contract and anti-disclosure decision; do not randomly convert all denials into 404.
- **409 Conflict / 422 per contract:** the operation violates business state or invariant, *when the caller actually has permission to perform the action*; do not use a conflict response in place of a permission error.

Spring Security provides `AuthenticationEntryPoint` and `AccessDeniedHandler` to handle security error branches. Actual responses depend on application type, authentication mechanism, and configured exception handling; do not assume every application always returns the same JSON/body.

A safe order is typically: authenticate → determine actor and access scope → find resource within valid scope → check policy → check business invariants → update. Never return content, sensitive metadata, or detailed resource messages before checking permissions.

## 10. Controlling Permissions Even on List Queries

Not only `GET /documents/{id}` needs authorization; `GET /documents` can expose **hundreds of records** if you check only `hasAuthority("document:read")` while the query omits tenant/visibility conditions.

Approach:

1. At the boundary, check the capability to invoke the read function.
2. Build predicates/queries based on the trusted actor: tenant, owner, group membership, sharing rules.
3. Perform filtering in the database when possible, with proper indexes and consistency with single-record policies.
4. For paginated APIs, filter before `LIMIT/OFFSET` so out-of-scope records are neither included in results nor distort paging/counts.
5. Never load all sensitive data and filter in the frontend; nor treat `@PostFilter` on large datasets as a default substitute for secure queries.

For updates/deletes, consider actor-scoped repository queries and use version checks or locking when conditions may change concurrently. Policies must stay consistent across list view, detail view, editing, and export; avoid allowing export of data that the list screen blocks.

## 11. Design Mistakes That Can Lead to Privilege Escalation

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "Logged in means can view any ID" | IDOR/BOLA | Per-object + tenant policy + checks in service/repository |
| "Role=MANAGER has full access" | Cross-organization data leaks or workflow bypass | Scope permissions, resources, and domain exceptions |
| Trusting `ownerId`/`tenantId` from body/header | Spoofing subject or scope | Actor from trusted source; verify resource server-side |
| Guarding only in Controller | Batch jobs, event listeners, reused services can bypass | Guard at use-case/service and additional entry points |
| Placing `@PreAuthorize` only on internally self-called methods | AOP self-invocation can skip checks | Structure calls through proper proxies or always-executed policy guards |
| Rules scattered across long SpEL, controllers, repositories, and UI with differing variants | Policy drift, hard to audit | One named, well-tested policy, thin adapters |
| Checking data once then using a stale/uncontrolled copy | Race/TOCTOU, operating on wrong state | Appropriate transactions, scoped queries, versioning/locking |
| Filtering results after returning or in the browser | Information leaks, wrong counts/paging | Filter in queries and control every operation |
| Using `permitAll` to work around config errors | Critical endpoints become public | Identify root cause, declare intentional matchers, deny by default |
| Handling all errors as 403 | Masks auth failures, missing data, or validation errors | Separate authentication, authorization, resource, and invariant failures |

Specifically, `permitAll` only lets the request pass **that corresponding authorization step**; it does not mean disabling all filters or bypassing downstream business checks. Likewise, an endpoint protected by a URL matcher still needs data-level policies when ID parameters are present.

## 12. Organizing Code So Rules Can Change Without Breaking Mechanisms

A reference layout:

```text
security/
  SecurityConfig                 # endpoint guards, filter chain, method security
  AuthenticatedActorResolver    # Authentication -> trusted Actor
document/
  application/
    DocumentService             # load/scoping, policy check, transaction
  domain/
    Document
    DocumentPolicy              # canView, canRename, canApprove...
  persistence/
    DocumentRepository          # tenant/visibility-scoped queries
```

This is a responsibility diagram, not a mandatory package structure.

A good policy should have these traits:

- Action-expressing names: `canApproveInvoice` is clearer than `checkPermission`.
- Inputs representing full actor/action/resource/context without reading global requests directly when unnecessary.
- Decides deny when required relationships or facts are missing; a "failed to load policy" case must not default to allow.
- Separates data gathering from decision-making, especially for plain-Java unit testing.
- Invoked consistently across entry points; rule ownership lives in the business domain.
- Logs appropriate audit records (who, action, resource, outcome, safe reason); never log tokens, passwords, or sensitive data.
- When rules change, update the test matrix and contract before or alongside implementation.

Spring Security is not limited to role checks: `AuthorizationManager` allows plugging custom policies into request/method authorization. However, avoid turning framework mechanisms into the home for all business state; policies should still have independent APIs and tests.

## 13. Decision Tables and Testing Strategy

Example for the rule "an owner with `document:edit` may edit a draft in the same tenant":

| Actor Has Permission | Same Tenant | Is Owner | Status | Expectation |
| --- | --- | --- | --- | --- |
| Yes | Yes | Yes | DRAFT | ALLOW |
| No | Yes | Yes | DRAFT | DENY |
| Yes | No | Yes | DRAFT | DENY |
| Yes | Yes | No | DRAFT | DENY |
| Yes | Yes | Yes | APPROVED | DENY |
| Unauthenticated | — | — | DRAFT | Blocked at authentication layer before reaching policy |

Test at least three groups:

1. **Policy unit tests:** all allow/deny branches, cross-tenant, different owner, missing permission, other statuses, null/missing facts (per contract). This group has high value and runs fast.
2. **Method/service integration tests:** enable `@EnableMethodSecurity`, verify method guards genuinely apply via proxy, use cases cannot be bypassed via alternate entry points, repositories are properly tenant-scoped, transactions/versioning handle critical races.
3. **HTTP security tests:** with MockMvc or corresponding integration tests, verify anonymous/authenticated, HTTP method + URL, 401/403/404 per contract, matcher ordering, requests with/without CSRF token where applicable, and principal/token-to-Actor mapping.

Note that negative tests must confirm **the exact reason for denial**. For example, a test "cannot PATCH because not owner" might accidentally get 403 due to a missing CSRF token; asserting only HTTP 403 does not prove the owner policy works. Use fixtures with valid credentials/CSRF and vary only owner/tenant/status, while verifying that the record remains unchanged.

A quick self-evaluation: "A user has `document:edit`, is the document's owner, yet the document resides in a tenant where that user is no longer a member. May they edit it?" — **No**; ownership alone does not replace organizational scope checks. Next: "The document-reading API returns 404 instead of 403 when a document from another tenant is not visible; is a policy still needed?" — **Still needed**; response presentation never replaces database/service access-scope restrictions.

## 14. Checklist When Adding a New Use Case

1. Describe the action in business-domain language: view, edit, approve, refund, assign.
2. Identify trusted actor/tenant, the real resource, and all relationships to query.
3. Write the exact allow statement: **who**, **may do what**, **on which record**, **when**, and **which exceptions**.
4. Choose entry-point guards via HTTP/method security, then apply domain policy where accurate data is available.
5. Separate missing-permission conditions from business-invalid operation conditions; define error responses to avoid information leaks.
6. Apply across list/detail/export/background operations and concurrent transactions.
7. Build an allow/deny matrix and test negative paths intentionally before shipping the endpoint.

**Core mindset:** Spring Security handles authentication infrastructure, check pipelines, and access blocking; **the application must decide permission semantics based on caller, action, resource, and business context**. By putting these decisions into a clear policy, enforcing them at every entry point, and testing every condition, you will avoid most "has role yet still accesses wrong resource" bugs.

## Further Reading

- [Spring Security — Authorization (overview)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/index.html)
- [Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Servlet Architecture — Handling Security Exceptions](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
