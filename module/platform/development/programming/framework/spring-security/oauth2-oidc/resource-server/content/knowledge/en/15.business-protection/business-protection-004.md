# Checking Ownership, Tenant, and Resource Relationships

In a **Spring Security OAuth 2.0 Resource Server**, having a JWT access token with a valid signature containing `SCOPE_orders.read` **does not mean** the user is allowed to read **every order**. The token establishes identity and function-level access; permission to access **a specific record** must be evaluated based on **ownership, tenant, and the business relationship** between the caller and the resource.

This is the core problem of **object-level authorization**. An API that has enabled `authenticated()`, `hasAuthority(...)`, or `@PreAuthorize(...)` can still suffer from a **Broken Object Level Authorization (BOLA)** vulnerability—commonly manifested as **Insecure Direct Object Reference (IDOR)**—if data queries rely solely on a client-supplied ID without checking permissions on the object.

This lesson explains how to combine **OAuth 2.0 scopes**, identities from JWT/OIDC, **tenant isolation**, ownership, sharing, relationship-based authorization, and query constraints in a Spring Security Servlet Resource Server application.

## 1. Three Distinct Security Questions

Consider the request:

~~~http
GET /api/tenants/t-7/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

The Resource Server must answer:

1. **Authentication – Who is calling?** Is the JWT valid, is the issuer trusted, is the audience meant for the Orders API, is the token unexpired, and who is the subject/client?
2. **Function-level authorization – What may they do?** Does the token carry a scope like `orders.read`, or the role/authority required to read orders?
3. **Object-level authorization – On which resource may they do it?** Which tenant does order 123 belong to? Is the caller the owner, a member with an appropriate role, or someone granted a read share?

~~~mermaid
flowchart TD
    A["GET /tenants/t-7/orders/123"] --> B["JwtDecoder verifies token"]
    B --> C{"Valid signature / iss / aud / exp?"}
    C -- "No" --> X["401 Unauthorized"]
    C -- "Yes" --> D{"Has SCOPE_orders.read?"}
    D -- "No" --> Y["403 Forbidden"]
    D -- "Yes" --> E["Map (iss, sub) to internal user"]
    E --> F["Check active membership in tenant t-7"]
    F --> G["Query order by ID and tenant"]
    G --> H["Check owner / role / sharing"]
    H --> I{"Allowed to read this order?"}
    I -- "No" --> Z["403 or 404 per policy"]
    I -- "Yes" --> J["Return DTO containing only permitted fields"]
~~~

| Protection Layer | Example | If Missing |
| --- | --- | --- |
| Access token verification | Signature, issuer, audience, expiration | Accepts forged tokens, wrong-issuer tokens, or tokens issued for another purpose |
| Functional permissions | `SCOPE_orders.read` | Allows invoking operations without a granted scope |
| Object permissions | Owner, tenant membership, share | Reads/modifies another user's or another tenant's records |
| Field-level permissions | Redact cost price or PII when lacking permission | Leaks sensitive fields inside an otherwise authorized object |

**Scopes do not replace ownership. Tenant membership does not automatically mean owning every record in the tenant.** All conditions must be combined according to business policy.

## 2. Identity from JWT: How Far Can You Trust It?

Example JWT access token:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read orders.write",
  "tenant_id": "t-7"
}
~~~

This is merely an illustrative payload; being able to decode Base64URL strings does not prove a JWT is valid. **`JwtDecoder` must verify signature, issuer, audience, expiration, and applicable conditions before the application uses any claim for authorization.**

Values to distinguish:

| Value | Source | Role in Authorization |
| --- | --- | --- |
| Verified `iss` and `sub` | Access token via Resource Server | Identifies the subject within the issuer's scope |
| `scope`/`scp` | Token issued by Authorization Server | Functional permissions granted under the token contract |
| `tenant_id` in JWT | Claim provided by issuer | Can serve as tenant context if trusted and contract-compliant; does not replace current membership |
| `tenantId` in URL/body/header | Client-chosen/sent data | **Not proof** that the user belongs to the tenant |
| `ownerUserId` in request body | Client-controlled data | Must never be used on its own to establish ownership |
| Owner, membership, share in DB | Managed business data | Basis for determining current object permissions |

### Why Use the `(issuer, subject)` Pair?

`sub` identifies a subject **within the scope of an issuer**. Two different issuers can both emit `sub: "user-42"` for two completely different people. In systems supporting multiple issuers, map **(iss, sub)** to an **internal user ID**:

~~~text
Verified JWT
    iss = https://auth.example.com/realms/shop
    sub = user-42
           |
           v
    user_identity_mapping(issuer, subject, user_id)
           |
           v
    users.id (Internal ID)
           |
           +--> tenant_memberships.user_id
           +--> orders.owner_user_id
           +--> order_shares.grantee_user_id
~~~

Avoid using email or username as the default ownership key because they can change, collide, or follow different verification rules.

Specifically, with **Client Credentials**, a token may describe a **machine client** rather than a human user. Never assume every `sub` is a user owner; the API needs a separate policy based on client identity, tenant binding, and permitted service functions.

## 3. Tenant, Owner, and Relationship Model

An order system might have:

~~~text
Tenant(id)
  |-- TenantMembership(userId, tenantId, role, status)
  |-- Order(id, tenantId, ownerUserId, customerId, status)
  |       |-- OrderLine(id, orderId)
  |       |-- OrderAttachment(id, orderId)
  |       +-- OrderShare(orderId, granteeUserId, permission, expiresAt)
  +-- Customer(id, tenantId)

UserIdentity(issuer, subject) -> InternalUser(id)
~~~

Illustrative policy:

> A user can **read an order** when the access token is authenticated, carries scope `orders.read`, the user is an **active member** of the tenant containing the order, and the user is the owner **or** a manager of the tenant with order-reading rights **or** holds a currently valid READ share.

Logical expression:

~~~text
canReadOrder(actor, order) =
    tokenHasScope(actor, "orders.read")
    AND activeMember(actor.userId, order.tenantId)
    AND (
        order.ownerUserId == actor.userId
        OR hasTenantRole(actor.userId, order.tenantId, "ORDER_MANAGER")
        OR hasActiveShare(actor.userId, order.id, "READ")
    )
~~~

This is an **example policy**; another system might grant partners access via cross-tenant delegation or have finer-grained permission tiers. What matters is that each relationship has explicit **semantics, scope, validity, and permitted actions**.

| Relationship | Example | What Must Be Checked |
| --- | --- | --- |
| **Owner** | Person who owns the order | Owner ID in DB, status, and ownership-transfer policy |
| **Tenant member** | Employee of company t-7 | Active membership, matching tenant, valid role |
| **Manager** | Order manager for t-7 | Permissions inside the right tenant; never generalize to other tenants |
| **Sharing** | Owner shares order with B | Exact grantee, READ/EDIT permission, expiration, revoked flag |
| **Delegation** | Delegate authorized to approve | Delegator, scope, validity, and delegate's permissions |
| **Parent-child** | OrderLine of an Order | Child belongs to the authorized parent/tenant |
| **Assignment** | Staff assigned to customer | Active assignment, resource within assignment scope |
| **Service client** | Background job processing orders | Trusted client identity, tenant binding, functional scope, and service scope |

## 4. IDOR/BOLA Vulnerability: Checking Only Scope

Controller example:

~~~java
@GetMapping("/api/orders/{id}")
OrderDto getOrder(@PathVariable long id) {
    return orderRepository.findById(id)
        .map(OrderDto::from)
        .orElseThrow(OrderNotFoundException::new);
}
~~~

Even if Spring Security protects the endpoint:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

a caller holding the read scope can still try:

~~~text
GET /api/orders/101   -- user A's order
GET /api/orders/102   -- user B's order
GET /api/orders/201   -- order belonging to another tenant
~~~

If `findById(id)` does not constrain tenant and ownership, clients can read data simply by knowing the ID. This is a form of BOLA/IDOR. **Replacing numeric IDs with hard-to-guess UUIDs does not replace authorization**; IDs can leak via links, logs, emails, or other data.

BOLA can happen in any action: viewing details, updating, approving, transferring ownership, downloading files, exporting reports, deleting records, generating share links, searching, and even endpoints returning only counts/metadata.

## 5. Receiving the Authenticated Principal in Spring Security

With a JWT Resource Server, a controller can receive `Jwt` from Spring Security:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    OrderDto getOrder(
            @PathVariable String tenantId,
            @PathVariable long orderId,
            @AuthenticationPrincipal Jwt jwt) {
        return orders.readOrder(jwt, tenantId, orderId);
    }
}
~~~

Notes:

1. This `Jwt` comes from Resource Server authentication, **not a JSON body** submitted by the client.
2. `tenantId` and `orderId` in the path are caller-modifiable inputs. They **do not prove permission**.
3. This example uses the JWT path. With opaque access tokens, the principal may be `OAuth2AuthenticatedPrincipal`; applications should use a unified identity abstraction if supporting both authentication modes.
4. The decoder must enforce full issuer, audience, time, and profile policies before the application trusts the identity.

The service layer then maps `(iss, sub)` to an internal user and checks current permissions against the DB.

## 6. Service Checking Scope, Tenant, and Object Permissions

In modern Spring Security Servlet applications, method security can be enabled:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Service example:

~~~java
import java.util.Objects;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final UserIdentityRepository identities;
    private final TenantMembershipRepository memberships;
    private final OrderRepository orders;
    private final OrderShareRepository shares;

    public OrderService(
            UserIdentityRepository identities,
            TenantMembershipRepository memberships,
            OrderRepository orders,
            OrderShareRepository shares) {
        this.identities = identities;
        this.memberships = memberships;
        this.orders = orders;
        this.shares = shares;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(Jwt jwt, String tenantId, long orderId) {
        String issuer = Objects.requireNonNull(jwt.getIssuer()).toString();
        String subject = Objects.requireNonNull(jwt.getSubject());

        InternalUser actor = identities
            .findByIssuerAndSubject(issuer, subject)
            .orElseThrow(() -> new AccessDeniedException("Unknown principal"));

        TenantMembership membership = memberships
            .findActiveMembership(actor.getId(), tenantId)
            .orElseThrow(() -> new AccessDeniedException("Tenant denied"));

        Order order = orders.findByIdAndTenantId(orderId, tenantId)
            .orElseThrow(OrderNotFoundException::new);

        boolean owns = actor.getId().equals(order.getOwnerUserId());
        boolean manages = membership.hasRole("ORDER_MANAGER");
        boolean shared = shares.existsActiveReadShare(
            order.getId(), actor.getId());

        if (!(owns || manages || shared)) {
            throw new AccessDeniedException("Order denied");
        }

        return OrderDto.from(order);
    }
}
~~~

**The business-domain types in this example are application-defined placeholders**, including `UserIdentityRepository`, `TenantMembershipRepository`, `OrderRepository`, `OrderShareRepository`, `InternalUser`, `TenantMembership`, `Order`, `OrderDto`, and `OrderNotFoundException`. The snippet illustrates policy coordination, not built-in Spring Security classes.

Layers of defense:

- `@PreAuthorize` requires the `orders.read` scope.
- `findByIssuerAndSubject(...)` resolves the internal user from the verified issuer and subject.
- `findActiveMembership(...)` checks **current** membership in the requested tenant.
- `findByIdAndTenantId(...)` loads only orders belonging to that tenant.
- `owns || manages || shared` determines who can read the **specific order**.
- `OrderDto.from(order)` exposes only permitted API fields; sensitive fields require separate policies.

**Note on method security:** `@EnableMethodSecurity` must be active; calls must pass through the proper proxy. Self-invocation from one method to another on the same object can bypass proxy interception. Do not place protection solely in one controller if other workflows can call repositories or services directly.

## 7. Constraining Queries in the Repository

Avoid unconstrained queries:

~~~java
Order order = orderRepository.findById(orderId).orElseThrow();
~~~

In multi-tenant systems, scope at least by tenant:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByIdAndTenantId(Long id, String tenantId);

    @Query("""
        select o from Order o
        where o.id = :orderId
          and o.tenantId = :tenantId
          and o.ownerUserId = :userId
        """)
    Optional<Order> findOwnedOrder(
        @Param("orderId") Long orderId,
        @Param("tenantId") String tenantId,
        @Param("userId") Long userId
    );
}
~~~

`findByIdAndTenantId(...)` prevents leaking an order from another tenant even if the client guesses the ID. `findOwnedOrder(...)` adds ownership when an endpoint is strictly owner-only. For manager/share policies, add explicit conditional queries or check via the service.

**Never load multi-tenant data into Java and filter afterward**:

~~~java
// Poor design for lists and pagination.
List<Order> all = orderRepository.findAll();
return all.stream()
    .filter(o -> canRead(actor, o))
    .toList();
~~~

This wastes resources and increases the risk of leaking data via logs, exports, errors, or inconsistent pagination results. Push tenant and relationship predicates into the query whenever the contract allows.

SQL example listing orders where the actor is the owner or holds a READ share:

~~~sql
SELECT o.*
FROM orders o
WHERE o.tenant_id = :tenant_id
  AND (
       o.owner_user_id = :actor_id
       OR EXISTS (
           SELECT 1
           FROM order_shares s
           WHERE s.order_id = o.id
             AND s.grantee_user_id = :actor_id
             AND s.permission = 'READ'
             AND s.revoked_at IS NULL
             AND (s.expires_at IS NULL OR s.expires_at > CURRENT_TIMESTAMP)
       )
  )
ORDER BY o.id
LIMIT :page_size OFFSET :offset;
~~~

This query only illustrates the owner/share branches, assuming tenant membership has already been verified. For managers, add the appropriate branch; never add an overly broad `OR` condition that lets every tenant member read every order. Always use **parameter binding**, never string-concatenating `tenant_id` or `actor_id` into SQL.

**Count, search, autocomplete, download, and export** queries must enforce the same data limits. An endpoint returning merely the count of another tenant's orders still leaks information.

## 8. Tenant Context Is Not Proof of Membership

Common multi-tenant architectures include:

- **Shared schema:** tables contain `tenant_id`.
- **Schema per tenant:** each tenant uses its own schema.
- **Database per tenant:** each tenant uses its own database.

Storage layout does not replace authorization. Example request:

~~~http
GET /api/tenants/t-8/orders/201 HTTP/1.1
Authorization: Bearer <token-for-user-in-t-7>
~~~

If the user only has an active membership in `t-7`, the API must reject `t-8`, unless an explicit **cross-tenant delegation** policy is granted. An `X-Tenant-ID: t-8` header, `/tenants/t-8` path, or tenant-selection cookie only expresses **the client's requested context**, never granting permission.

A single user may belong to multiple tenants. When a UI lets a user "switch active tenant," the API must verify that the user is still a member of that tenant and query only resources within it. If a JWT carries a tenant-scoped claim, validate it per the issuer contract; actual permissions may still have changed since token issuance.

### Be Careful with TenantContext / ThreadLocal

Servlet containers reuse threads. If an application stores a tenant in a `ThreadLocal` and forgets to clear it after a request, a later request can inherit the wrong tenant. When using a tenant context, manage its lifecycle explicitly, clear it in `finally`, and handle async/thread propagation safely. In many cases, passing the verified tenant ID **explicitly** to services/repositories is easier to reason about and control.

## 9. Parent–Child Resource Relationships

A request may supply both a parent ID and a child ID:

~~~http
GET /api/orders/101/lines/999 HTTP/1.1
Authorization: Bearer <valid-access-token>
~~~

The API has verified that the caller may view order 101. However, if the code loading the line executes:

~~~java
OrderLine line = orderLineRepository.findById(999L)
    .orElseThrow(OrderLineNotFoundException::new);
~~~

then line 999 could belong to order 201 in another tenant. **Checking the parent does not prove the child ID belongs to that parent.**

Safer query:

~~~java
OrderLine line = orderLineRepository
    .findByIdAndOrderIdAndTenantId(lineId, orderId, tenantId)
    .orElseThrow(OrderLineNotFoundException::new);
~~~

Or:

~~~sql
SELECT l.*
FROM order_lines l
JOIN orders o ON o.id = l.order_id
WHERE l.id = :line_id
  AND o.id = :order_id
  AND o.tenant_id = :tenant_id;
~~~

Apply this to invoice lines, document versions, attachments, comments, payments, tasks, folders/files, parent-child organizations, and similar nested resources. **Update/delete** operations on child resources must check both action permissions and the actual child–parent–tenant relationship.

## 10. Sharing and Delegation Must Have Scope and Expiration

Sometimes the owner is not the only person allowed access. A system may support sharing, assignment, or delegation:

~~~text
order_shares(
    order_id,
    grantee_user_id,
    permission,      -- READ / EDIT / EXPORT
    created_by_user_id,
    expires_at,
    revoked_at
)
~~~

When checking a share, the API must:

1. Confirm the share belongs to the **exact order**, exact grantee, and exact tenant/context.
2. Confirm the permission covers the **current action**; READ does not imply EDIT or APPROVE.
3. Verify the share is **not revoked and not expired**.
4. Verify tenant membership or cross-tenant policy rules.
5. If access depends on a delegator, verify the delegation remains valid per business rules.

If a user was just removed from a tenant while their access token still has 15 minutes remaining, the token may still pass authentication. Yet revoked membership must take effect according to the live authorization update policy. For rapid permission revocation, read membership/shares from the DB or a policy service with appropriate caching/invalidation, rather than relying solely on stale token claims.

## 11. Avoiding Mass Assignment on Owner and Tenant

Suppose an API receives this body:

~~~json
{
  "title": "New order",
  "tenantId": "t-8",
  "ownerUserId": "another-user",
  "status": "APPROVED"
}
~~~

If the server binds all request fields directly onto an entity, the client can set its own owner or tenant and breach permission boundaries. This is a form of **mass assignment / broken object authorization**.

Remediation:

- Use DTOs exposing **only the fields the caller is allowed to edit**, such as `title` and `note`.
- Determine owner/tenant from server-side logic after verifying identity and membership.
- Changing owner, changing tenant, approving, and sharing must be **separate actions** with their own permissions.
- Check workflow state; a user allowed to edit a `DRAFT` order is not implicitly allowed to edit an `APPROVED` order.

Example skeleton:

~~~java
public record UpdateOrderRequest(String title, String note) {}

@PreAuthorize("hasAuthority('SCOPE_orders.write')")
@Transactional
public void updateOrder(
        Jwt jwt, String tenantId, long orderId, UpdateOrderRequest request) {

    // 1. Resolve actor from (iss, sub).
    // 2. Check tenant membership.
    // 3. Load Order by (orderId, tenantId).
    // 4. Check owner/manager/share relationship for EDIT action.
    // 5. Allow edits only in permitted states, e.g., DRAFT.
    // 6. Validate and update title/note.
    // NEVER assign owner, tenant, or APPROVED from client input.
}
~~~

This snippet illustrates the order of checks, not a complete implementation.

## 12. Preventing TOCTOU When Permissions or Resources Change Concurrently

**Time-of-check to time-of-use** happens when an authorization check result is no longer valid by the time the update executes:

~~~text
10:00:00  API verifies user A may edit order 101
10:00:01  Admin revokes share or moves order to another tenant
10:00:02  API writes order based on the stale check result
~~~

Defensive techniques:

- Check and update inside an appropriate **transaction**.
- Use **optimistic locking** with `@Version` when concurrent changes must be detected.
- For sensitive operations, execute a **conditional update** filtering by tenant, owner/relationship, status, and version.
- Use appropriate DB locks if stronger consistency is required.
- Never emit events, emails, payments, or external system updates **before** permissions and business rules are confirmed.

Conditional update example when only the owner may edit a `DRAFT` order:

~~~sql
UPDATE orders
SET title = :title,
    version = version + 1
WHERE id = :order_id
  AND tenant_id = :tenant_id
  AND owner_user_id = :actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
~~~

Treat the update as successful only when **affected rows equals 1**. If 0 rows are affected, the record may not exist, permission may be missing, or the version may have changed; return an error per policy without leaking another tenant's details. The condition above is an **owner-only example policy** and must be adapted if managers or EDIT share grantees are permitted.

A transaction alone does not create authorization if the query omits tenant/owner checks. Conversely, checking permissions outside a transaction may be insufficient for sensitive operations under race conditions.

## 13. Centralizing Policies with a Policy Service

With Spring Method Security, object checks can live in a policy bean:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "@orderAccess.canRead(authentication, #tenantId, #orderId)"
)
public OrderDto readOrder(String tenantId, long orderId) {
    return orderService.readWithScopedQuery(tenantId, orderId);
}
~~~

`orderAccess` is an application-defined bean. It can map the principal to an actor, check membership, ownership, and shares. Some systems use `PermissionEvaluator` with `hasPermission(...)`; newer Spring Security versions also offer `AuthorizationManager` for HTTP/method authorization.

When using SpEL or annotations:

- Avoid querying the DB repeatedly for each item in a list (**N+1 authorization queries**).
- Ensure the resource **being used** is the exact same resource **that was checked**.
- Do not skip tenant scoping in the repository just because an annotation performs a boolean check.
- Method security proxies may not intercept self-invocation.
- Other entry points such as batch jobs, event consumers, and internal APIs must enforce the same policies when acting on the same data.

A maintainable design often uses a **policy service** for decisions and a **scoped repository** for queries/writes, backed by transactions and auditing as needed.

## 14. 403 or 404 When Unauthorized?

| HTTP Status | Intended Meaning |
| --- | --- |
| **401 Unauthorized** | Request lacks a valid access token or authentication failed |
| **403 Forbidden** | Principal is authenticated but not permitted to perform the operation |
| **404 Not Found** | API did not find the resource within allowed scope, or intentionally avoids revealing another tenant's/user's resource |

For example, `findByIdAndTenantId(101, "t-7")` returns empty if order 101 actually belongs to `t-8`. The API can return **404** without confirming order 101 exists in another tenant. This helps reduce enumeration, but it must be applied consistently without leaking via bodies, timing, counts, or error messages.

**403 and 404 are not completely interchangeable.** Choosing which status to return is part of the security and API contract; internal logs/audits can still record the exact reason at an authorized level without exposing it to the caller.

## 15. Testing Object Permissions

You cannot prove object-level authorization solely by testing with a valid JWT carrying the read scope. You need real data and relationships in a test database.

Suppose:

- A and B belong to tenant `t-7`.
- C belongs to tenant `t-8`.
- Order 101 belongs to `t-7`, owner A.
- Order 102 belongs to `t-7`, owner B.
- Order 201 belongs to `t-8`, owner C.

| Caller and Token | Request | Example Policy Expectation |
| --- | --- | --- |
| A with `orders.read` | Read order 101 in `t-7` | Allow |
| A with `orders.read` | Read order 102 in `t-7` | Deny unless shared/manager |
| A with `orders.read` | Read order 201 in `t-8` | Deny: tenant mismatch |
| A missing `orders.read` | Read order 101 owned by A | 403: missing functional permission |
| A using expired JWT | Read order 101 | 401: invalid token |
| B granted READ share on order 101 | Read order 101 | Allow while share is valid |
| B has READ share revoked | Read order 101 | Deny |
| B holds only READ share | Edit order 101 | Deny without EDIT permission |
| Manager of `t-7` | Read order 102 in `t-7` | Allow if policy grants manager access |
| Manager of `t-7` | Read order 201 in `t-8` | Deny: role does not cross tenants |
| A | Read line of order 201 under order 101 path | Deny/404: parent-child relation mismatch |
| A | List/export `t-7` orders | Return only permitted resources, including counts and metadata |

For write operations, tests must verify **DB records were not modified** after a denied request; returning 403 after a side effect already occurred is broken protection.

### Distinguishing Test Layers

| Test Type | Can Verify | Does Not Prove on Its Own |
| --- | --- | --- |
| `@WithMockUser` / method security test | Authority/role expressions | JWT signature, issuer/audience, real identity mapping |
| `jwt()` MockMvc post-processor | HTTP authorization with a mock JWT principal | Usually bypasses real `JwtDecoder`/JWS signatures |
| Service + repository integration test | Ownership, membership, shares, scoped queries | HTTP Bearer filter/decoder |
| End-to-end test with JWT signed by test keys | Combines token validation, scope, and object-level policy | Requires properly managed relational test fixtures |

Example MockMvc test for object permissions (requires seeded test data and Spring Security Test imports):

~~~java
mockMvc.perform(get("/api/tenants/t-7/orders/101")
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://auth.example.com/realms/shop")
                .subject("user-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/tenants/t-8/orders/201")
        .with(jwt()
            .jwt(jwt -> jwt
                .issuer("https://auth.example.com/realms/shop")
                .subject("user-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());
~~~

This snippet **illustrates the example with pre-seeded data**; if the API intentionally returns 404 to hide resource existence, the second test expectation would be 404. The `jwt()` post-processor builds a mock authentication and does not prove signatures/issuers were verified by a real decoder.

### Commonly Missed Checks

- Test **cross-tenant** access using users with the same role in different tenants.
- Test **cross-user** access within the same tenant when viewing is owner-only.
- Test shares that are **active, expired, revoked**, and READ vs. EDIT.
- Test **ownership transfer** and locked/removed user memberships.
- Test **parent-child mismatches** when both IDs exist individually but are unrelated.
- Test **list, search, export, count, and download**, not only detail views.
- Test concurrent updates and **affected DB row counts**.
- Test error payloads and messages to ensure no cross-tenant data leaks.

## 16. Defense in Depth: Database RLS and Auditing

Some multi-tenant applications use **Row-Level Security (RLS)**, such as in PostgreSQL, to restrict DB rows by tenant and actor. This is a useful extra defense layer, not a replacement for application policies:

- A tenant context left on a pooled connection with improper lifecycle cleanup can leak into another request.
- A database role with RLS-bypass privileges can disable policy enforcement.
- RLS checking only tenant can still miss owner/share rules.
- A batch job or separate service might connect with different credentials and query past the policy.

When using RLS, define database roles, transaction scopes, session variables, reset/cleanup behavior, and special access paths carefully. RLS should serve as **defense in depth**, not an excuse to skip user–resource relationship checks.

Appropriate logging/auditing should record request IDs, internal actor IDs, tenant, action, resource ID, `ALLOW/DENY` outcome, and high-level reason. **Never log raw access tokens, refresh tokens, secrets, or another tenant's private data.** For actions like approve, export, ownership transfer, or break-glass access, audits must capture everything needed for traceability.

## 17. Common Misconceptions

**"A JWT with `SCOPE_orders.read` means all orders can be viewed."** No. Scopes only authorize operations at a functional level; tenant and per-order relationships must still be constrained.

**"UUIDs are unguessable so no owner check is needed."** No. IDs can leak, and security must never depend solely on hiding identifiers.

**"A user belongs to tenant t-7 so they can read everything in t-7."** Not automatically. Policies may require ownership or shares; tenant membership is just one condition.

**"`ROLE_ADMIN` administers all tenants."** No, unless the system explicitly grants global authority. Roles usually apply to a specific tenant or resource scope.

**"Checking the parent order is enough; any child line ID is fine."** Wrong. You must verify the line belongs to the exact order/tenant and the caller has rights to the line.

**"The `tenant_id` claim in a token always reflects current membership."** Not necessarily. Membership can be revoked while a token remains unexpired; handle stale data with appropriate refresh/invalidation policies.

**"`@PreAuthorize` protects every call."** Not if method security is disabled, self-invocation bypasses the proxy, or another code path goes straight to the DB.

**"Clients can pick owner/tenant when creating an order."** No. Owner/tenant relationships must be assigned server-side or validated through a separately authorized operation.

**"403 is always better than 404."** No. For out-of-scope resources, 404 can help prevent existence disclosure. Establish a consistent contract and proper internal auditing.

## 18. Mental Model for Protecting a Business Endpoint

Before returning or modifying a resource:

1. **Identify the principal:** use a verified token, issuer + subject, or client identity; map to an internal actor.
2. **Identify the action:** READ, WRITE, DELETE, EXPORT, SHARE, APPROVE, TRANSFER, or another operation.
3. **Check scope/authority:** does the token carry the required functional privilege?
4. **Determine the resource's real tenant:** from system-managed data, not just request paths or headers.
5. **Verify current membership:** is the actor permitted to operate in that tenant?
6. **Verify relationship:** owner, manager, assignment, sharing, delegation, or parent–child relationship.
7. **Check state:** has the share/relationship been revoked or expired, or has the resource changed state?
8. **Constrain queries and writes:** tenant predicates, actor/relationship checks, transactions, optimistic locking, and affected row counts.
9. **Filter output data:** field-level policies, list results, reports, counts, and error messages.
10. **Enforce across all paths:** HTTP, background jobs, event consumers, internal services, and export endpoints.

**Key point:** a valid JWT tells you **who is calling** and which privileges were granted at the token level. Deciding whether to allow reading or modifying **a specific resource** must rely on **trusted identity + functional scope + tenant isolation + current owner/share/relationship + business state**. Stopping BOLA/IDOR lies in **data authorization rules and properly constrained queries**, not just `authenticated()` or unguessable IDs.
