# Assets, Subjects, Resources, and Actions in an Application

Application security starts with understanding **what is being protected, who can act on it, which object they are accessing, and what action they want to perform**. The four concepts—**asset**, **subject**, **resource**, and **action/operation**—create a common language to define protection boundaries, design access rules, and assess risks. This is the foundational mindset before writing Spring Security configuration.

## 1. The Four Concepts and Their Relationships

| Concept | Question to Answer | Meaning | Example in an Order Management System |
| --- | --- | --- | --- |
| **Asset** | What is valuable and needs protection? | Data, capability, or state valuable to users/the organization; requires protecting confidentiality, integrity, and availability | Customer information, order amount, payment data trustworthiness, ability to place orders |
| **Subject** | Who or what component is requesting the action? | The identity participating in a security decision; can be a user, service, or system task | Alice, support staff, report export service |
| **Resource** | Which object is the action targeting? | A specific object or access point that can be protected by policy | Order `ORD-100`, `GET /api/orders/100`, invoice file, customer record |
| **Action/Operation** | What does the subject want to do with the resource? | The action to allow or deny; includes reading, creating, updating, deleting, and domain-specific operations | `read`, `update`, `cancel`, `refund`, `export` |

An authorization decision typically takes the form:

```text
can(subject, action, resource, context) -> ALLOW | DENY
```

Where `context` may include tenant, ownership relationship, resource state, time, network scope, sensitivity level, or business conditions. For example:

```text
can(Alice, READ, order#100, {tenant: "shop-a", owner: "Alice"})
can(Bob,    READ, order#100, {tenant: "shop-a", owner: "Alice"})
```

Two requests accessing the same resource with the same action can receive different results because **the subjects are different**. Even the same subject may be allowed to read an order but not allowed to refund that order.

Important distinction: **an asset is what has value and needs protection; a resource is the specific object or access point used to reach the asset**. One asset can appear across multiple resources: customer data exists in a database row, a lookup API, an Excel export file, a cache, and logs. Protecting one endpoint does not guarantee that every copy or every access path to the asset is safe.

## 2. Identifying Assets Before Writing Rules

An application can contain many types of assets:

- **Confidential data**: hashed passwords, tokens, API keys, phone numbers, addresses, payment history, contracts; access and leakage must be restricted.
- **High-integrity data**: product prices, balances, payment status, account permissions, approval history; unauthorized modification must be prevented.
- **System capability and availability**: ability to log in, complete orders, process payments, serve requests; must be protected against resource abuse and disruption.
- **Intangible business assets**: reputation, audit evidence, correctness of approval decisions; these assets depend on multiple technical components.

The three classic security properties help identify the impact when an asset is compromised:

| Property | Question | Incident Example |
| --- | --- | --- |
| **Confidentiality** | Can an unauthorized person see the data? | User A downloads User B's invoice |
| **Integrity** | Can an unauthorized person alter data or processes? | A regular user modifies payment price or self-approves a refund |
| **Availability** | Is the system/resource still usable when needed? | A critical API exhausts resources due to abusive requests |

An asset may require all three properties. For example, an account balance needs confidentiality, strict integrity, and availability during transactions. The level of protection must reflect the **impact if exploited**, not just table names or API paths.

### 2.1. Creating an Asset Inventory Table Useful for the Development Team

Instead of merely listing endpoints, record:

| Asset | Where It Appears | Key Risk | Business Owner | Typical Protection Rules |
| --- | --- | --- | --- | --- |
| Customer personal information | Database, detail API, CSV export, logs | Data leakage | Customer support department | Only the right account/authorized staff; restrict data exports |
| Refund status | Database, refund API, event queue | Fraudulent operation | Finance department | Check role, permission on the order, business limits, and audit |
| Login session | Cookie, session store | Session hijacking | System operations team | Secure cookies, HTTPS, session management, context-appropriate CSRF |
| Order processing capability | API, DB connection, queue | Service disruption | Order operations team | Rate limiting, timeouts, monitoring, and resource allocation |

Assets do not necessarily map one-to-one to resources. For example, customer personal data can leak through the `/customers/{id}` API, export features, error responses, or logs, so all data exposure points must be examined.

## 3. Subject: Who Is Requesting Permission?

A **subject** is the party performing or held accountable for an action. In modern applications, a subject can be:

1. **A user**: guest, employee, administrator, logged-in or unauthenticated user.
2. **An application/service**: one backend calling another backend using a service account, OAuth2 client, or workload identity.
3. **An automated process**: batch job, scheduler, or event consumer. An automated task also needs an appropriate identity and permission boundaries.

Distinguish between:

- **Actual actor/entity**: the human or component actually causing the action.
- **Claimed identity**: a value sent by the caller, such as `userId` in a request body; not trusted merely because it is present.
- **Authenticated principal**: an identity confirmed by the system through a valid mechanism; used as input for security decisions.
- **Authority/permission**: privileges granted to the principal; they describe what may be permitted, though resource-level conditions may still need checking.

In a Servlet application using Spring Security, the authentication result is represented by an `Authentication` object, usually stored in `SecurityContext`. `authentication.getName()` represents the name of the authenticated identity; `getAuthorities()` returns the assigned privileges. With some token mechanisms, the principal also carries claims or other stable identifiers. **Do not assume every application uses username as the data ownership key**: internal user IDs, token subjects, or tenants may require separate mapping.

A faulty trust boundary example:

```http
GET /api/orders/100
X-User-Id: alice
```

An `X-User-Id` header sent by the client does not prove the client is Alice. If the application treats this header as the authenticated subject, an attacker can replace it with `bob`. Obtain the subject from a trusted authentication mechanism and verify the signature, expiration, issuer, audience, or other conditions required for the token type in use.

### 3.1. Who Is the Subject in a CSRF Scenario?

If Alice's browser is logged in via a session cookie and a malicious page causes the browser to send a POST, the backend may see **principal Alice** because the cookie is attached automatically. However, the subject causing the action is not Alice intentionally clicking that feature. This is why **verifying identity** and **proving a state-changing request is legitimate** (e.g., a CSRF token when appropriate) are two separate checks.

## 4. Resource: The Object That Needs Control

Resources can exist at multiple levels:

| Level | Example | What to Check |
| --- | --- | --- |
| URL/API | `/api/admin/reports`, `/api/orders/{id}` | Is the request allowed to enter this feature/endpoint? |
| Record or object | Order `100` belonging to Alice, Tenant A | Does the caller have an ownership relationship or permission on this exact object? |
| Data field | `customer.email`, `order.discountRate` | Is viewing/editing each sensitive field permitted? |
| Document/file | PDF invoice, private image, export file | Is downloading, sharing, or generating an access link permitted? |
| Business capability | Issuing a refund, changing permissions, exporting all data | Is executing this sensitive function permitted? |
| Infrastructure | Admin console, secret, queue, storage bucket | Which identities can read/write/administer? |

**A URL is not the entire resource.** Two requests both go through `GET /api/orders/{id}` but point to two different records. An `authenticated()` rule on the URL only requires login; it does not automatically check whether a user owns that `orderId`.

A common vulnerability is **Broken Object Level Authorization (BOLA)**, often called IDOR when guessable or modifiable IDs are exposed: a valid user changes `/api/orders/100` to `/api/orders/101` and sees someone else's data. The core problem is **a missing authorization decision on the exact object**, not that the ID is easy to guess. Switching from sequential IDs to UUIDs may make enumeration harder but does not replace permission checks.

In multi-tenant systems, the same `orderId` may also require `tenantId` to identify the exact resource. The tenant must be derived from a trusted context; never treat a client-supplied `tenantId` parameter as proof that the caller belongs to that tenant.

## 5. Action: Distinguishing HTTP Methods from Business Actions

Common actions include `create`, `read`, `update`, `delete` (CRUD). However, real-world security also involves:

- `approve`: approving an order or request;
- `refund`: issuing a refund;
- `export`: bulk downloading data;
- `share`: granting access to others;
- `assign-role`: modifying access permissions;
- `rotate-key`: rotating keys;
- `cancel`: canceling a task or transaction.

Permissions cannot be fully inferred from the HTTP method alone:

- `GET /api/orders/100` reads one order; `GET /api/orders/export` can reveal thousands of orders and requires a different permission.
- `POST /api/orders/100/refund` is a conditional financial operation; it is not equivalent to a normal POST creating a resource.
- `PATCH /api/users/100` may edit profile info, but changing the `roles` field usually requires additional administrative privileges.
- `DELETE /api/orders/100` may be forbidden after payment, regardless of whether the caller has permission to delete draft orders.

Name permissions clearly by business behavior, such as `order:read:own`, `order:read:any`, `order:refund`, or `user:assign-role`. Permission names do not protect the application on their own; the server must actually enforce the policy where the action occurs.

## 6. Combining Subject, Resource, Action, and Context into a Policy

A security decision can be described as follows:

```text
Subject       = alice (authenticated, tenant-a)
Action        = READ
Resource      = order#100 (owner=alice, tenant=tenant-a)
Context       = application rules + order state
Policy        = sameTenant && (isOwner || hasPermission("order:read:any"))
Decision      = ALLOW
```

A policy based on attributes of the subject, resource, and context aligns closely with **Attribute-Based Access Control (ABAC)**. A policy based on roles, such as admin/user, aligns closely with **Role-Based Access Control (RBAC)**. Real systems often combine roles, permissions, ownership, tenant, object state, and business constraints.

### 6.1. Example Permission Matrix

Suppose Shop A has Alice (customer), Bob (customer), auditor (inspection staff), and Shop B has its own administrator. Order `ORD-100` belongs to Alice at Shop A.

| Subject | Resource | Action | Decision | Reason |
| --- | --- | --- | --- | --- |
| Alice | `ORD-100` | Read | Allow | Authenticated, same tenant, owns the order |
| Bob | `ORD-100` | Read | Deny | Same tenant but does not own it; lacks permission to view all orders |
| Shop A's Auditor | `ORD-100` | Read | Allow | Has `order:read:any` permission within Shop A |
| Shop A's Auditor | `ORD-100` | Update | Deny | Read permission does not include update permission |
| Shop B's Admin | `ORD-100` | Read | Deny | Wrong tenant, even though holding an admin role in another tenant |
| Anonymous guest | `ORD-100` | Read | Deny | Not authenticated |
| Alice | `ORD-100` | Refund | Deny without refund permission/condition | Ownership does not automatically grant permission for every action |

In this example, the `:any` permission is scoped **within the same tenant** only. Permissions for staff or administrators must be explicitly scoped; an `ADMIN` role does not implicitly cross tenant boundaries.

### 6.2. Order of Thinking When Designing a Decision

1. **Identify the asset:** if the action is wrongly allowed, which asset is affected, and which asset property is compromised?
2. **Verify the subject:** where does the principal come from, is it authenticated, and how are permissions/tenant verified?
3. **Identify the actual resource:** which record/file/object does the ID in the URL correspond to, and whom does it belong to?
4. **Identify the true action:** is this read, update, export, refund, or something else? Are there special risks?
5. **Evaluate the policy:** check role/authority, tenant, ownership, object state, and context; deny if no rule grants access.
6. **Enforce safely:** block before side effects occur; minimize information leakage in responses and logs.
7. **Test:** include allow cases and deny cases for missing login, wrong role, wrong owner, wrong tenant, and invalid state.

## 7. Standalone Java 17 Example: Modeling the Decision

The following example simulates order access decisions in memory without needing a framework or database. It shows how **subject, resource, action, and policy** work together. This is an exercise in authorization thinking, **not a production authentication system**: the `authenticated` flag and permissions are simulated with hardcoded data.

Create the file `AccessModel.java`:

```java
import java.util.Set;

public class AccessModel {

    record Subject(
        String userId,
        String tenantId,
        boolean authenticated,
        Set<String> permissions
    ) {}

    record OrderResource(String id, String tenantId, String ownerId) {}

    enum Action { READ, UPDATE, EXPORT }

    static boolean allowed(
        Subject subject,
        Action action,
        OrderResource resource
    ) {
        if (subject == null || !subject.authenticated()) {
            return false;
        }

        // Even the "any" permission is only valid within the same tenant.
        if (!subject.tenantId().equals(resource.tenantId())) {
            return false;
        }

        String permissionBase = switch (action) {
            case READ -> "order:read";
            case UPDATE -> "order:update";
            case EXPORT -> "order:export";
        };

        boolean anyInTenant = subject.permissions()
            .contains(permissionBase + ":any");

        boolean own = subject.userId().equals(resource.ownerId())
            && subject.permissions().contains(permissionBase + ":own");

        return anyInTenant || own;
    }

    static void show(
        String label,
        Subject subject,
        Action action,
        OrderResource resource
    ) {
        System.out.println(label + ": " + allowed(subject, action, resource));
    }

    public static void main(String[] args) {
        OrderResource order = new OrderResource("ORD-100", "shop-a", "alice");

        Subject alice = new Subject(
            "alice", "shop-a", true,
            Set.of("order:read:own", "order:update:own")
        );
        Subject bob = new Subject(
            "bob", "shop-a", true, Set.of("order:read:own")
        );
        Subject auditor = new Subject(
            "auditor", "shop-a", true, Set.of("order:read:any")
        );
        Subject otherTenantAdmin = new Subject(
            "admin", "shop-b", true, Set.of("order:read:any")
        );
        Subject anonymous = new Subject(
            "guest", "shop-a", false, Set.of("order:read:any")
        );

        show("Alice reads own", alice, Action.READ, order);
        show("Bob reads Alice's order", bob, Action.READ, order);
        show("Auditor reads", auditor, Action.READ, order);
        show("Auditor updates", auditor, Action.UPDATE, order);
        show("Other tenant admin reads", otherTenantAdmin, Action.READ, order);
        show("Anonymous reads", anonymous, Action.READ, order);
        show("Alice exports", alice, Action.EXPORT, order);
        show("Alice updates own", alice, Action.UPDATE, order);
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac AccessModel.java
java AccessModel
```

Expected output:

```text
Alice reads own: true
Bob reads Alice's order: false
Auditor reads: true
Auditor updates: false
Other tenant admin reads: false
Anonymous reads: false
Alice exports: false
Alice updates own: true
```

Explanation:

- Alice has the `order:read:own` permission and owns the order, so she can read it. Bob has the same permission but does not own it, so he is denied.
- Auditor only has the `order:read:any` permission, so they can read all orders **within Shop A**; lacking `order:update:any`, they cannot update them.
- The administrator in Shop B is blocked before the `:any` permission is even evaluated.
- An unauthenticated user is always denied in this policy, even if permissions were manually assigned to the `Subject` object.
- Alice can update her own order under this simplified model, though she might not be allowed to edit it once the order is paid; that is a contextual condition to add in a real system.

Try changing `order.ownerId` to `bob`, or replacing `Action.READ` with `Action.EXPORT`. The outcome changes based on the resource and action even though the caller's identity remains the same.

**Intentional limitations of this example:** the code does not verify passwords/tokens, does not execute transactions, has no database, and does not check order state. In a real application, identity/tenant/permission data must come from a trusted source, and object-level permissions must be checked on the server against fresh data and business policies.

## 8. Mapping the Four Concepts to Spring Security

In Spring Security Servlet, a sensible conceptual processing chain is:

```text
HTTP request
    |
    v
SecurityFilterChain
    |--> Appropriate request protection layers (e.g., CSRF)
    |--> Authentication -> SecurityContext (who?)
    |--> Request-level authorization (allowed to call endpoint?)
    v
Controller -> Service -> Repository
                |
                |--> Load resource by ID + tenant
                |--> Check ownership, permission, state (do what, to which object?)
                v
          Execute business logic / deny
```

This diagram illustrates responsibilities; the actual filter order is determined by Spring Security's mechanism/configuration. At the business layer, checks may reside in method security, services, policy components, or appropriately scoped database queries.

| Lesson Concept | Common Representation in Spring |
| --- | --- |
| Subject | `Authentication` and principal in `SecurityContext`; privileges from `GrantedAuthority` |
| Action | HTTP method in `requestMatchers`; or business actions in services such as `approve`, `refund` |
| Resource | Request URL, domain object `Order`/`Invoice`, record ID, file, tenant |
| Decision | `authorizeHttpRequests`, method security `@PreAuthorize`, or business policy |
| Asset to protect | Customer info, transactions, secrets, system state; defined by business design, not automatically inferred from annotations |

### 8.1. Path-Based Checks: Protecting the Entry Point

Example Spring Boot 3 / Spring Security 6 Servlet configuration:

```java
@Configuration
@EnableMethodSecurity
class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

This is an **illustrative configuration snippet**, not a standalone Java file: it requires imports and dependencies for Spring Boot Web, Spring Security, a mechanism to provide users/authentication, and appropriate controllers/services. The example only shows that catalog GET is public, orders require login, and all remaining requests are denied by default. Spring Security normally enables CSRF protection in Servlet configuration; state-changing requests must satisfy CSRF when applicable.

Important: `authenticated()` does not automatically restrict `orderId` by user. If you stop here, a logged-in user can access someone else's ID unless the service checks object-level permissions.

### 8.2. Service-Level Checks: Protecting the Exact Resource

Once `@EnableMethodSecurity` is enabled, a service can invoke a policy to check the specific order being accessed:

```java
@PreAuthorize("@orderPolicy.canRead(authentication, #p0)")
public OrderDto getOrder(long orderId) {
    return orderService.loadOrder(orderId);
}
```

This is an **illustrative snippet**: the application needs a bean named `orderPolicy`, a `canRead(Authentication, long)` method, `OrderDto`, and an actual `orderService`. The reference `#p0` captures the method's first parameter; `authentication` is the identity in the Spring Security context. In a real application, the policy needs to:

1. Confirm the principal is authenticated and holds the corresponding permission;
2. Find or scope the order by the trusted tenant;
3. Compare the owner or permission to view all orders within the tenant;
4. Evaluate other business conditions if any;
5. Deny when the resource does not exist or permission is lacking.

Calling only `@PreAuthorize("isAuthenticated()")` on a method is still insufficient to prevent IDOR. Enforce protection at the layer that has full information about the object and across all execution paths, not only in the controller. For operations with state conditions or concurrent updates, check inside a transaction or use an appropriate conditional update statement to prevent state from changing between the check and the write (**time-of-check/time-of-use**).

Never treat `ownerId` or `tenantId` in the request body as proof of permission. For example, a client sending `{"ownerId":"alice"}` does not mean the calling subject is Alice.

## 9. From Concept Table to Threat Modeling

The four concepts also help raise questions about attack scenarios:

| Scenario | Threatened Asset | Involved Subject | Resource & Action | Required Control |
| --- | --- | --- | --- | --- |
| User changes URL ID to read someone else's order | Confidentiality of personal data | Logged-in user | Another owner's order, `read` | Server-side owner/tenant check |
| Employee can read an order but calls the refund API | Transaction integrity | Employee with `read` permission | Order, `refund` | Separate permission for refund, state/limit checks |
| Service in Tenant B sends a Tenant A resource ID | Tenant data isolation | Service account | Tenant A Order, `read/update` | Authenticate service and scope tenant from trusted context |
| External website forces browser to send POST | Data integrity | Attacker controlling requests from victim's browser | State-changing action | CSRF when using auto-attached credentials like cookies, along with authz |
| Exporting data beyond allowed scope | Bulk data confidentiality | Logged-in user/employee | Reports, `export` | Dedicated export permission, tenant filtering, audit logging, data limits |
| Automated task granted system-wide admin rights | Multiple assets | Service account | API, data, `read/write/admin` | Principle of least privilege, credential lifecycle, clear scoping |

An "authenticated" request can still be dangerous. During threat modeling, ask further: which subject can an attacker impersonate, which resource can they swap, which action can they invoke, which contextual condition can they exploit, and how does that affect the asset?

## 10. Design Mistakes to Catch Early

### 10.1. Defining Permissions Only by Global Role

A `hasRole("USER")` rule lets a user enter a group of APIs but does not answer "which records does this user have permission for?". Ownership, tenant, group relationships, and resource state must also be considered. A role is one input to a policy, not the entire policy.

### 10.2. Trusting Client-Supplied Attributes

`userId`, `tenantId`, `isAdmin`, and `permissions` in JSON bodies, query strings, or headers can all be tampered with. Verify identity/permissions from the authenticated principal and server-side data; treat client-sent fields solely as claims to be verified.

### 10.3. Ignoring Non-CRUD Actions

Exporting data, issuing refunds, granting permissions, activating accounts, and rotating security keys carry different risks even when all use POST/PATCH. Define dedicated permissions and business conditions per action.

### 10.4. Blocking Only in the UI or in One Controller

Hiding the “Delete” button is not authorization. Another client can still call HTTP directly. Even after protecting a controller, jobs, message consumers, or other internal services may invoke the same business logic; enforce policies at the appropriate boundary and protect all entry points.

### 10.5. Using Hard-to-Guess IDs Instead of Authorization

UUIDs, random numbers, or long URLs do not prove permission. If a user obtains an ID via logs, shared links, or error displays, the backend must still verify ownership and tenant.

### 10.6. Treating “ADMIN” as Unlimited Power

Admins usually have an **administrative scope**: a store, a department, or an organization. If privileges accidentally cross tenants, the blast radius when one account is compromised increases sharply. Special system privileges must have clearly defined boundaries.

### 10.7. Leaking Information Through Responses and Logs

An API may return 403 to protect data yet still leak a customer's name through an error message or log. When avoiding disclosure of whether a resource exists, the application can choose a policy-appropriate response, such as 404 for unauthorized objects. Logs should record caller ID, action, resource type, outcome, timestamp, and correlation ID without logging secrets or unnecessary sensitive data.

### 10.8. Authorizing Correctly at Read Time but Failing at Write Time

Permissions can change or an order can transition state while a request is running. For sensitive tasks, permission checks and data mutations should follow transaction boundaries and appropriate concurrency controls. Also re-verify at critical state transitions.

## 11. Design and Testing Checklist

Before putting an endpoint or business flow into production, answer:

- **Asset:** what data/state is valuable? How are confidentiality, integrity, and availability affected?
- **Subject:** who can call it? Where are identity/authority/tenant verified from?
- **Resource:** which record, file, data field, or capability does the request reference? Where are the tenant/owner boundaries?
- **Action:** is this specifically `read`, `update`, `approve`, `refund`, or `export`? Are there state conditions?
- **Policy:** who is allowed, for which object, under what conditions? Is it deny-by-default or are any rules overly broad?
- **Enforcement:** at which layer is the check performed? Do all execution paths invoking the business logic share the same control? Are there race condition risks?
- **Negative testing:** are anonymous, wrong role, wrong owner, wrong tenant, invalid state, and wrong action type rejected?
- **Other defenses:** are CSRF, validation, rate limiting, auditing, cookie/transport/header protections, and export limits needed?

A minimal test matrix for `GET /api/orders/{id}` includes: Alice reads Alice's order (allow), Bob reads Alice's order (deny), Tenant B user reads Tenant A's order (deny), anonymous calls API (deny). For `POST /api/orders/{id}/refund`, also include cases for missing refund permission, order ineligible for refund, and invalid CSRF request under cookie-based mechanisms.

## 12. Self-Check

**Question 1.** Which category does customer balance data belong to: asset or resource? What is an endpoint returning the balance?

**Question 2.** Two users both have `ROLE_USER`. Why can't you just use `hasRole("USER")` to allow them to view any `/api/orders/{id}`?

**Question 3.** An employee has permission to view all orders in Shop A. Does that automatically allow the employee to export all orders or view Shop B's orders?

**Question 4.** A client sends `{"userId":"alice","isAdmin":true}`. Can these fields be used as authenticated identity and permissions?

**Question 5.** Do two GET endpoints `/api/orders/100` and `/api/orders/export` necessarily share the same permission just because both use GET?

**Question 6.** In a session-cookie application, a forged POST sent by the browser while the user is logged in involves what issue besides authorization?

**Suggested Answers:**

1. Balance data is the asset to protect; the endpoint and specific record/document containing the balance are the resources/access paths to the asset.
2. Because a role only describes broad privileges and does not verify the relationship to the exact object; you must check owner, tenant, or business conditions.
3. No. Read permission does not implicitly include export or cross-tenant access.
4. No. Those are client-claimed data; the server must use the authenticated principal/authorities and trusted data.
5. No. Export has its own scope, impact, and business permission.
6. You must consider CSRF protection when credentials are attached automatically by the browser; a request with a valid principal does not prove the user intentionally submitted that request.

### Further Reading

- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [OWASP API Security – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
