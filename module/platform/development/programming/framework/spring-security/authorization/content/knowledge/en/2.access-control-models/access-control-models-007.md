# Vertical Privilege Escalation and Horizontal Unauthorized Access

> **Module:** Spring Security – authorization  
> **Knowledge group:** Access control models

## 1. Context: Even Authenticated Users Can Access Without Proper Authorization

An invoice management application has three accounts:

- **An** is a regular employee, allowed to view invoices An is responsible for.
- **Binh** is also an employee, allowed to view Binh's invoices.
- **Chi** has permission to approve invoices in organization T1.

Two requests look similar yet fail along **two different dimensions**:

1. An sends a request to the **approve** feature reserved only for approvers: a lower-privileged user attempts to execute a higher-privileged action.
2. An calls the **view invoice** feature that An is allowed to use, but changes the ID to view Binh's private invoice: the user moves sideways to another user's resource at the same privilege level.

Both are **Broken Access Control** – missing or improperly enforced access controls. Merely checking `isAuthenticated()`, validating a token, hiding a UI button, or using hard-to-guess IDs is **insufficient**.

This lesson focuses on answering:

- How does *vertical privilege escalation* differ from *horizontal unauthorized access / horizontal privilege escalation*?
- How do function-level check failures and object-level check failures arise?
- How do you apply Spring Security at HTTP, method, and data layers to block both?
- What negative test suite must be designed to catch flaws before deployment?

## 2. Access Decision Model

A complete authorization request needs at least four pieces of information:

| Component | Question | Example |
|---|---|---|
| **Subject** | Who is making the request? Which tenant, what roles/permissions? | An, `tenant=T1`, `invoice:read` |
| **Action** | What do they want to do? | `read`, `update`, `approve`, `delete` |
| **Resource** | Which record or object is affected? | Invoice `INV-102`, owner Binh |
| **Context** | Do current conditions permit it? | `status=PENDING`, tenant, department, sharing policy |

Expressing the policy explicitly:

~~~text
ALLOW(subject, action, resource, context)
  = subject is authenticated
    AND subject is permitted to perform action
    AND subject is permitted to act on the specific resource
    AND all context conditions are satisfied
~~~

**Authentication** answers "who?". **Authorization** answers "what can they do on which object?". Roles, authorities, and token scopes can support **action checks**, but **do not by themselves prove** permission on a specific resource.

In Spring Security, `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority by default; `hasAuthority("invoice:read")` compares the exact permission string. With a JWT Resource Server, an OAuth scope such as `invoices.read` is commonly mapped to `SCOPE_invoices.read`. Which permissions a role receives and which permissions apply to which invoices **is policy defined by the application**.

## 3. Vertical Privilege Escalation

### 3.1. Definition

**Vertical privilege escalation** occurs when a subject with a **lower privilege level** succeeds in performing an action or feature reserved for a **higher privilege level**, due to incomplete authorization checks.

Functional examples:

| Account | Valid Permission | Out-of-Bounds Action |
|---|---|---|
| Employee | `invoice:read` | `invoice:approve` |
| Approver | `invoice:approve` | `user:manage` |
| Regular user | View personal profile | Change another account's role or lock status |
| Operations staff | View summary reports | Access admin-only system configuration |

You do not have to "change your role to ADMIN" for it to count as vertical escalation. **Successfully executing a higher-privileged operation** is enough to show access control is broken.

### 3.2. Example: Approver API Left Improperly Open

Suppose the system exposes these endpoints:

~~~http
GET /api/invoices/101
POST /api/invoices/101/approve
~~~

Intended policy:

- `GET`: requires `invoice:read` and access to the specific invoice.
- `POST .../approve`: requires `invoice:approve`, same-tenant invoice, and an approvable state.

If the approval endpoint only requires "caller is logged in" without checking `invoice:approve`, regular employees can perform an action intended for approvers. This is a **function-level authorization flaw**, commonly called *Broken Function Level Authorization* (BFLA).

The flaw can exist across multiple layers:

- HTTP URL rules are overly broad or fail to cover a new endpoint.
- Service methods lack permission checks or are invoked via a flow bypassing controllers.
- Only hiding the "Approve" button in the UI without backend enforcement.
- Relying on a client-supplied `role` or `isAdmin` field.
- Calling a workflow step directly while the server fails to verify permissions and valid state transitions.

### 3.3. A Variant: Self-Escalation via Mass Assignment

Consider an API allowing users to update personal profile info. The application intends to allow editing `displayName` yet binds all fields from the request directly onto an entity also containing `role`, `enabled`, and `tenantId`.

~~~json
{
  "displayName": "An",
  "role": "ADMIN"
}
~~~

If the server accepts and persists `role` from an untrusted source, users can grant themselves higher privileges. This is an **uncontrolled mass assignment** flaw that can lead to privilege escalation. Prevent it with DTOs/allowlists of editable fields, explicit mapping, and separate authorization checks for sensitive fields. Removing the field from the UI alone **is not a protection**.

### 3.4. Root Cause

The system fails to verify **"is this subject permitted to invoke this privileged action?"** where the action executes. Having permission to view a resource does not imply permission to approve, delete, assign roles, or access admin functions.

## 4. Horizontal Unauthorized Access

### 4.1. Definition

**Horizontal unauthorized access** occurs when a subject accesses or modifies resources belonging to **another subject at the same privilege level**, even though they are permitted to use the feature being called.

Example with two employees sharing the `EMPLOYEE` role:

- An is allowed to read invoice `101`, owned by An.
- Binh is allowed to read invoice `102`, owned by Binh.
- An requests invoice `102`, and the system returns Binh's data.

An does not necessarily invoke an "admin" feature; **the read action is valid**, yet **the target object is wrong**. This is a per-object authorization flaw, called *Broken Object Level Authorization* (BOLA). Exposing data via object references without proper permission checks is commonly known as *Insecure Direct Object Reference* (IDOR).

### 4.2. Example: Checking Role While Skipping Owner

A flawed illustrative handler:

~~~java
// Illustrates the bug; do not copy into a real application.
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceDto getInvoice(long id) {
    Invoice invoice = repository.findById(id)
            .orElseThrow();
    return mapper.toDto(invoice);
}
~~~

Suppose `invoice:read` is granted to every employee. The annotation only answers **"does the user have general permission to read invoices?"**, while `findById(id)` does not verify whether the invoice belongs to an authorized owner or tenant. An employee can access someone else's invoice if they know or guess the ID.

Fix by defining a policy for the **specific object** and constraining queries by tenant/owner or granted relationships. Cover reads, updates, deletes, attachment downloads, exports, history, and related operations—not just a single endpoint.

### 4.3. Tenants and Sharing Relationships

Horizontal access does not happen only between two individuals. In multi-tenant SaaS, two organization admins may share the `TENANT_ADMIN` role, yet each may only administer resources inside their own tenant. If T1's admin reads T2's data, that is also a data boundary violation.

Conversely, user A accessing user B's data **is not always wrong**. B may have shared the record with A, or A may be assigned to handle it. In that case the system needs **server-verified relationship rules**: owner, shared user, authorized group, supervisor, organization permissions, etc.

Do not define overly rigid policies like "owner ID must always equal user ID" if the business genuinely supports sharing; nor should you drop object-level conditions entirely just because some roles need delegated access.

### 4.4. Hard-to-Guess IDs Do Not Replace Authorization Checks

Replacing numeric `101` with a UUID or random ID reduces ID guessing, but **does not grant authorization**. IDs can appear in URLs, logs, emails, share pages, or other payloads. If the API returns data whenever a valid ID is supplied, the system still suffers from BOLA.

The key rule is to **check the object on every request**, regardless of primary key format.

## 5. Quick Comparison of Both Escalation Dimensions

| Criterion | Vertical | Horizontal |
|---|---|---|
| Acting subject | User with fewer privileges than the target feature requires | User allowed to use the feature, lacking access to the target object |
| Boundary crossed | **Feature / privilege level** | **Ownership / tenant / resource relationship** |
| Missing check question | "Is this action permitted?" | "Is this action permitted on **this specific object**?" |
| Example | `EMPLOYEE` calls `approveInvoice` | An views Binh's private invoice |
| Typical controls | Permissions, roles, method/URL authorization, workflow guards | Resource policies, owner/tenant constraints, relationship checks |
| Common labels | BFLA, vertical privilege escalation | BOLA, IDOR, horizontal privilege escalation |

**Note:** Both dimensions can occur **simultaneously**. For example, a regular user both calls an unauthorized approval endpoint (vertical) and approves another tenant's invoice (horizontal). Or an admin holds broad privileges in their own tenant yet remains forbidden from cross-tenant operations. Therefore, never just compare role names; evaluate **policy over both action and object**.

## 6. Multi-Layer Defense Model in Spring Security

~~~text
HTTP request: principal + action + resource id
                     |
                     v
          Valid authentication?
                     |
                  no | yes
                     v
             401    URL/API rule
                    (scope/role/permission)
                        |
                     no | yes
                        v
                       403
                         v
             Service / use-case policy
             - business permission?
             - right tenant?
             - owner / shared / delegated?
             - valid state?
                         |
                     no | yes
                         v
                 403/404  data operation
                              |
                              v
                     200/201/204...
~~~

This diagram is conceptual: applications may use `404 Not Found` to avoid disclosing resource existence, provided the handling policy is consistent. `401` is typically for unauthenticated/invalid-token requests; `403` is typically for authenticated subjects lacking permission. Actual responses depend on the entry point, filter chain, and access-denied handler.

**Two independent yet coordinated check layers** are needed:

1. **Function-level authorization:** checks whether the caller is allowed to perform the action—for example, only matching roles/permissions may approve.
2. **Object-level authorization:** checks whether the specific object falls within authorized scope—for example, matching tenant, matching owner, valid share, valid state.

Checking at HTTP rejects early. Checking at service/use-case protects business logic when multiple controllers, jobs, event consumers, or internal flows invoke the same feature. Repository-level data filtering adds defense in depth, especially in multi-tenant systems.

## 7. Spring Security 6.x / Spring Boot 3.x Example

### 7.1. Blocking Privileged Operations at the HTTP Layer

The example below is a **configuration class inside a Spring Boot Servlet project with Spring Security and OAuth 2.0 Resource Server JWT properly configured**. It is not a standalone runnable Java program. Assume the Authorization Server issues scopes `invoices.read` and `invoices.approve`; the default JWT converter maps them to `SCOPE_*` authorities.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                    .hasAuthority("SCOPE_invoices.approve")
                .requestMatchers(HttpMethod.GET, "/api/invoices/*")
                    .hasAuthority("SCOPE_invoices.read")
                .anyRequest().denyAll()
        );

        http.oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Meaning and limitations:**

- A bearer of a token containing only `invoices.read` cannot invoke the approval endpoint without `SCOPE_invoices.approve`. This helps prevent part of **vertical escalation**.
- `SCOPE_invoices.approve` is a **token scope**, not necessarily the user's business approval permission. If the business also requires an `invoice:approve` role/permission, a corresponding policy/authority must also be checked.
- `GET .../{id}` only checks the token's read scope; **horizontal access** must still be blocked by checking the specific invoice.
- The default JWT converter **does not automatically turn custom role claims into `ROLE_ADMIN`**. To check roles/permissions beyond scopes, configure mapping from trusted sources or evaluate logic via a policy.
- `anyRequest().denyAll()` denies other unconfigured URLs. A complete application must explicitly declare other APIs, public/health endpoints if needed, and access token validation rules (issuer, audience per design).
- Never treat a matching URL rule as a reason to skip service-layer checks; future call paths may differ.

For applications using sessions/cookies instead of Bearer tokens, configure authentication and CSRF protection appropriately; the JWT snippet above is not guidance to disable CSRF across applications.

### 7.2. Enforcing Both Function and Object Permissions in the Service

With Spring-managed services and `@EnableMethodSecurity`, policies can sit directly on the use case:

~~~java
// Illustrates two methods of a Spring-managed service.
// invoicePolicy is an application-implemented bean.
@PreAuthorize(
    "hasAuthority('SCOPE_invoices.read') " +
    "and @invoicePolicy.canRead(authentication, #id)"
)
public InvoiceDto readInvoice(long id) {
    return invoiceQueryService.read(id);
}

@PreAuthorize(
    "hasAuthority('SCOPE_invoices.approve') " +
    "and @invoicePolicy.canApprove(authentication, #id)"
)
public void approveInvoice(long id) {
    invoiceCommandService.approve(id);
}
~~~

The snippet above **is not standalone**: `InvoiceDto`, both services, and the `invoicePolicy` bean belong to the application. The policy must verify **business roles/permissions**, tenant, ownership/delegation, and resource status using server data. Never treat `#id` as proof of access just because the client knows the ID.

A read policy can be expressed as:

~~~text
canRead(authentication, invoiceId):
  actor = verified identity from authentication
  invoice = look up by invoiceId within valid tenant
  deny if invoice does not exist
  deny if actor lacks invoice:read permission
  allow if actor is owner or validly shared
  allow if actor has read-all-in-tenant permission
  deny in all remaining cases
~~~

An approval policy can require `invoice:approve`, same tenant, `status=PENDING`, and no violation of maker/approver separation (if required by business rules). **These rules are not built into Spring Security by default**; they must be decided and tested by the application.

**Two technical details easily missed:** parameter `#id` must be resolvable by method security (e.g., compiled with `-parameters` or explicitly annotated); direct internal calls to another method on the same instance can bypass the Spring AOP proxy so annotations do not run. Place essential constraints in services/repositories rather than relying entirely on a single guard point.

### 7.3. Constraining Data Queries by Tenant

An additional defense is baking the trusted tenant into queries instead of loading records globally by ID and forgetting to check:

~~~sql
SELECT id, tenant_id, owner_id, status
FROM invoice
WHERE id = :invoiceId
  AND tenant_id = :authenticatedTenantId;
~~~

If the policy allows only the owner to read, constrain further:

~~~sql
SELECT id, tenant_id, owner_id, status
FROM invoice
WHERE id = :invoiceId
  AND tenant_id = :authenticatedTenantId
  AND (
      owner_id = :authenticatedUserId
      OR :mayReadAnyInTenant = TRUE
  );
~~~

`authenticatedTenantId`, `authenticatedUserId`, and `mayReadAnyInTenant` **must be computed server-side from verified identity and permissions**; never let client-supplied values create a bypass condition. The SQL above illustrates the idea; schema/binding details depend on the real system.

For state-changing operations, check and update atomically in a transaction under concurrency—for example, updating only invoices in the same tenant still in `PENDING` state. Avoid "checked – state changed – still wrote" (*time-of-check/time-of-use*) flaws.

## 8. Java 17 Practice: One Policy Blocking Both Attack Directions

The example below is a **pure Java program, compilable standalone**, simulating a document policy. It deliberately separates action permissions from owner/tenant. Permission strings are simulated data, not actual Spring Security `GrantedAuthority` instances.

Create file `AccessControlDemo.java`:

~~~java
import java.util.Set;

public class AccessControlDemo {

    record Actor(String id, String tenant, Set<String> permissions) {
    }

    record Document(
            String id, String tenant, String owner, String status) {
    }

    static boolean allows(Actor actor, String action, Document document) {
        // Data boundary: do not allow cross-tenant access.
        if (!actor.tenant().equals(document.tenant())) {
            return false;
        }

        return switch (action) {
            case "read" -> actor.permissions().contains("document:read")
                    && (actor.id().equals(document.owner())
                    || actor.permissions().contains(
                            "document:read:any-in-tenant"));

            case "approve" -> actor.permissions().contains("document:approve")
                    && document.status().equals("PENDING");

            default -> false; // Deny unknown actions by default.
        };
    }

    static void show(String label, boolean decision) {
        System.out.println(label + ": " + decision);
    }

    public static void main(String[] args) {
        Document target = new Document("D-100", "T1", "alice", "PENDING");

        Actor alice = new Actor(
                "alice", "T1", Set.of("document:read"));

        Actor bob = new Actor(
                "bob", "T1", Set.of("document:read"));

        Actor approver = new Actor(
                "carol", "T1",
                Set.of("document:read", "document:read:any-in-tenant",
                        "document:approve"));

        Actor anotherTenant = new Actor(
                "dave", "T2",
                Set.of("document:read", "document:read:any-in-tenant",
                        "document:approve"));

        show("Alice reads own", allows(alice, "read", target));
        show("Bob reads Alice", allows(bob, "read", target));
        show("Alice approves", allows(alice, "approve", target));
        show("Carol approves", allows(approver, "approve", target));
        show("Dave approves T1", allows(anotherTenant, "approve", target));
        show("Unknown action", allows(approver, "delete", target));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac AccessControlDemo.java
java AccessControlDemo
~~~

Expected output:

~~~text
Alice reads own: true
Bob reads Alice: false
Alice approves: false
Carol approves: true
Dave approves T1: false
Unknown action: false
~~~

**Branch-by-branch analysis:**

- **Alice reads her own document:** has `document:read`, right owner, right tenant → allowed.
- **Bob reads Alice's document:** same read permission level but wrong owner → denies **horizontal access**.
- **Alice approves the document:** lacks `document:approve` → denies **vertical escalation**.
- **Carol approves:** has approval permission, right tenant, and `PENDING` status → allowed.
- **Dave approves T1's document:** has approval permission yet belongs to T2 → denies **cross-tenant access**.
- **Undeclared action:** `default` branch returns false, demonstrating **deny by default**.

This program only illustrates **decision logic** without authentication, JWT, transactions, database, or concurrency control. In real applications, permissions and tenants must be constructed from trusted sources; policies may also need sharing conditions, separation of duties, or unit-scoped approvers.

## 9. Design Rules to Prevent Recurring Flaws

### 9.1. Never Trust Client-Declared Privilege Data

Never take `role`, `tenantId`, `userId`, or `isAdmin` from query parameters/body/headers as the sole source of authority. Clients can modify those values. Use verified authentication, server-managed memberships/roles, and authoritative resource data.

Similarly, a valid access token with scope `read` is not proof of permission to read **every** object; token scope and per-record permission must be evaluated separately. When one service receives tokens from another service, validate audience/issuer and distinguish service privileges from end-user privileges.

### 9.2. Guard Every Entry Point and Every Object

Records can be exposed across many surfaces:

- Detail views, lists, search, and exports.
- Updates, approvals, cancellations, deletions, and state changes.
- Attachment downloads, history views, and child resources.
- Batch endpoints, GraphQL resolvers, WebSockets, jobs, and event consumers.
- Admin UIs and APIs sharing the same service.

If one path enforces the policy while another skips it, callers can reach data via the unguarded path. Place policies close to use cases and share them across equivalent entry points; never push all responsibility onto the UI or gateway.

### 9.3. Limit Privileges and Fail Closed

- Pick specific permissions; never grant `ADMIN` for read-only tasks.
- When subject/resource/policy info is missing: deny, never allow by default.
- Never treat secret-looking ID formats as an access-control mechanism.
- Avoid overly broad wildcard patterns and never put `permitAll()` on sensitive operations.
- Never assume a high role in tenant A grants access to tenant B.
- When intentionally allowing global system admins across tenants, enforce a **dedicated policy**, auditing, and explicit tests.

### 9.4. Never Expose Data Before Making the Authorization Decision

Checking permissions only after building DTOs or right before frontend rendering can leak data via logs, caches, or serialization. Check at query time or before returning results. For lists, tenant/owner filters must apply in the query itself, not only via Java filtering after loading the entire table.

Caches must also be keyed with proper scope; caching invoice details solely by ID while ignoring tenant/user can leak data across callers even if the endpoint performs partial checks.

## 10. Designing Negative Tests: Testing What the System **Must Deny**

Build test fixtures with **genuinely distinct** accounts and records:

~~~text
Alice: USER, tenant T1, has document:read
Bob:   USER, tenant T1, has document:read
Carol: APPROVER, tenant T1, has document:approve
Dave:  APPROVER, tenant T2, has document:approve

D-100: owner=Alice, tenant=T1, status=PENDING
D-200: owner=Bob,   tenant=T1, status=PENDING
D-300: owner=Dave,  tenant=T2, status=PENDING
~~~

| Scenario | Expected | Flaw Caught If Allowed |
|---|---|---|
| Alice reads D-100 | Allow | Function check too strict if blocked |
| Alice reads D-200 | **Deny** | Horizontal / BOLA |
| Alice reads D-300 | **Deny** | Cross-tenant / BOLA |
| Alice calls approve API on D-100 | **Deny** | Vertical / BFLA |
| Carol approves D-100 in T1 | Allow if other conditions hold | Correct permission check |
| Carol approves D-300 in T2 | **Deny** | Cross-tenant |
| Client sends `role=ADMIN` in request | Does not alter permissions | Trusting client / mass assignment |
| Token lacks required scope | **Deny** | Missing token scope enforcement |
| Already `APPROVED` record re-approved | **Deny** per workflow | Missing state constraint |
| `id` parameter swapped between two users | Each request re-checks the object | BOLA if reusing prior ID's decision |

Be sure to test **HTTP methods, use cases, and query results**. Testing with only an admin account will never catch horizontal access. Passing happy-path tests alone does not prove invalid cases are blocked.

In Spring Security projects, use Spring Security Test/MockMvc to verify HTTP paths and method security. `@WithMockUser` simulates users/authorities; when verifying a JWT Resource Server, test real token/scope mapping separately because mock users do not prove JWT converters and validators work. For service or repository tests, use records with different owners/tenants to verify per-resource policies.

Mind **403 vs. 404**: some applications deliberately return 404 for out-of-scope records to hide existence; assert according to system policy while ensuring confidential data is **never returned**. Never treat an arbitrary HTTP error as proof enough if the response body already leaked data.

## 11. Subtle Mistakes in Large Systems

| Mistake | Consequence |
|---|---|
| Treating `authenticated` as enough | Regular users can invoke high-privilege features |
| Putting `hasRole` only on controllers | Services, jobs, or other entry points bypass rules |
| Using only `hasAuthority("invoice:read")` for read-by-ID | Same-role users read records they do not own |
| Omitting tenant filters in repositories | Cross-organization access even when the UI picks the right tenant |
| Trusting client-chosen `tenantId` | Users can pick another tenant themselves |
| Leaving sensitive entity fields unprotected on updates | Mass assignment elevates roles / swaps owners |
| Checking permission first, updating later without concurrency control | Record changes state between the two steps |
| Caching responses solely by resource ID | Returns another user's/tenant's data |
| Relying on `@PreAuthorize` on self-invoked methods in the same bean | Proxy advice may not execute |
| Testing only HTTP 200 with admin | Missing vertical/horizontal denials go undetected |
| Switching to UUIDs and skipping authorization | Hard-to-guess IDs do not equal authorization |
| Logging full tokens and sensitive payloads on denial | Out-of-band information leaks |

A practical distinction: **button visibility** and **permission enforcement** are two separate responsibilities. The UI should hide or disable actions to avoid confusing users, but the server is always the final decision point.

## 12. Checklist When Reviewing a New Endpoint

Example PR adding `POST /api/invoices/{id}/approve`:

1. **Authentication:** who is calling? Is the token/session valid?
2. **Action:** which permission/role/scope is required for "approve"? Where is it checked?
3. **Data:** which invoice, which tenant, is it an object the subject is allowed to approve?
4. **Workflow:** which states can transition to APPROVED? Must the approver differ from the creator?
5. **Trust sources:** do user ID, role, tenant, and permissions come from the server or client-supplied data?
6. **Other call paths:** is this method called from any other controller/job/event? Is the policy enforced consistently?
7. **Data defense:** are queries tenant-scoped? Do updates handle transactions/state conditions?
8. **Testing:** are there tests for regular users attempting approval, same-level users viewing others' records, cross-tenant admins, missing scopes, and invalid states?
9. **Observability:** do audit logs record subject, action, resource, tenant, outcome, and reason at an appropriate level without logging tokens/secrets?

If the answers to **"is this action permitted?"** or **"is it permitted on this exact record?"** are unclear, the policy is not ready.

## 13. Summary and Self-Check

**Key points to remember:**

- **Vertical privilege escalation:** crossing a **privilege/function level**; e.g., a regular employee approves an invoice.
- **Horizontal unauthorized access:** crossing an **object boundary** within the same privilege level; e.g., an employee reads a colleague's invoice.
- **BFLA** relates to broken function checks; **BOLA/IDOR** relates to broken object checks. Both can occur together.
- **Spring Security URL/method authorization** is a key guard; **service policies and scoped data queries** enforce per-resource access.
- **Deny by default, least privilege, server-side enforcement, negative tests** are core principles throughout.

**Practice questions:**

1. An has `invoice:read` and reads Binh's invoice via another ID. What flaw is this? **Horizontal/BOLA**: reading is allowed, but the record is out of scope.
2. An lacks `invoice:approve` yet calls the approve API successfully. What flaw is this? **Vertical/BFLA**: executing a higher-privileged operation.
3. Can tenant T1's admin view tenant T2's records by default? **No**: high title in T1 does not grant cross-tenant access.
4. Does replacing numeric IDs with UUIDs fix BOLA? **No**: per-object authorization must still be checked.
5. Is `hasAuthority("SCOPE_invoices.read")` enough to return an invoice by ID? **No**: token scope does not replace owner/tenant and business policy checks.
6. If you test an API only with an admin account, which test group do you miss? **Denial tests**: regular users invoking admin features, same-role users accessing each other's resources, and cross-tenant access.

### References

- Spring Security – Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP API Security Top 10 (2023): https://owasp.org/API-Security/editions/2023/en/0x11-t10/